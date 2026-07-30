# ADEPT pipeline engine — authored 2026-07-28 (M1).
"""Recipe 模型：DAG JSON serde、執行順序（拓撲排序）、lint 式驗證。

Recipe JSON 形狀（見 docs/plans/F0-master-plan.md §3.4）：

.. code-block:: json

    {
      "recipe_id": "M1_EBI_bridge", "version": 3, "author": "HX",
      "description": "...",
      "routes": {"ebi_patch": ["load","align","subtract","snr"],
                 "rsem":      ["load","golden","subtract","snr"]},
      "nodes": {"align": {"step": "align", "params": {"method": "phase"},
                          "enabled": true}},
      "edges": [["subtract","snr"]],
      "score": {"expr": "snr_max * sqrt(blob_area)", "threshold": 3.0,
                "bins": {"below": 0, "above": 1}}
    }

- v1 每條 route 是線性鏈；``edges`` 是額外的 DAG 邊（v2 自由畫布備用）。
  執行順序 = route 相鄰對邊 ∪ edges（限制在該 route 內）的 Kahn 拓撲排序，
  平手時依 route 位置決定（deterministic）。
- 驗證走 lint 模式（KLIP ``Issue`` 結構）：一次列出**所有**問題，
  不是碰到第一個就停。
"""
from __future__ import annotations

import heapq
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Type

from .expression import ExpressionError, parse_expression
from .step import ParamError, Step, REGISTRY

__all__ = [
    "RecipeError", "RecipeNode", "ScoreSpec", "Recipe",
    "Issue", "execution_order", "validate",
]


class RecipeError(ValueError):
    """Recipe 結構性錯誤（循環、未知 route、JSON 缺欄位…）。"""


# ---------------------------------------------------------------------------
# 資料模型
# ---------------------------------------------------------------------------
@dataclass
class RecipeNode:
    """pipeline 上的一張卡：``id`` 節點名、``step`` 卡片 key、``params`` 參數。"""
    id: str
    step: str
    params: Dict[str, Any]
    enabled: bool = True


@dataclass
class ScoreSpec:
    """ADC 判定段：score 表達式 + 門檻 + bin 對應（{"below": 0, "above": 1}）。"""
    expr: str
    threshold: float
    bins: Dict[str, int]


# ---------------------------------------------------------------------------
# 舊 recipe 相容遷移（F7-18）：``also_apply`` → 一張卡一條流
# ---------------------------------------------------------------------------
#: 哪些卡片以前有 ``also_apply``，以及它們的主要影像流參數叫什麼。
_ALSO_APPLY_CARDS: Dict[str, str] = {
    "percentile_norm": "source",
    "glv_mask_norm": "source",
    "denoise": "target",
    "flatten": "target",
    "local_contrast": "target",
    "brightness_contrast": "target",
    "gamma": "target",
}

#: 這兩張卡另外還有 ``anchor``：``source`` = 其他流借主流量出來的拉伸範圍。
#: 那個能力現在叫 ``range_from``（一條影像流的名字），所以遷移得動兩個參數。
_ANCHOR_CARDS = ("percentile_norm", "glv_mask_norm")


def _fresh_id(taken: Dict[str, Any], base: str) -> str:
    nid = base
    i = 2
    while nid in taken:
        nid = "%s_%d" % (base, i)
        i += 1
    return nid


def _migrate_also_apply(nodes: Dict[str, "RecipeNode"],
                        routes: Dict[str, List[str]]) -> None:
    """把 ``also_apply`` 展開成一張卡一條流（就地改寫 nodes 與 routes）。

    為什麼要遷移而不是直接不認得
    ----------------------------
    ``also_apply`` 是使用者存在磁碟上的 recipe 裡的字，而 recipe 是拿來交接的
    東西。認不得它會讓一份跑得好好的檔案在升級之後變成 ``unknown parameters``
    —— 對不會寫 code 的人那就是「工具壞了」。

    為什麼順序看 ``anchor``
    -----------------------
    ``anchor="source"`` 的語意是「ref 用 **test 原本的** 灰階範圍」。拆成兩張卡
    之後，如果 test 那張先跑，它會把 test 拉成 0–255，ref 那張再去借就借到
    「拉伸後」的範圍 —— 數字不一樣，而畫面上兩者都是一張看起來正常的圖。
    所以 ``anchor="source"`` 時把借範圍的那幾張排在**前面**，此時主流還沒被改過，
    輸出與舊版逐位元組相同。``anchor="self"`` 沒有這個相依，維持原順序。
    """
    extra: Dict[str, tuple] = {}          # 原節點 id -> (新節點 ids, 要不要排前面)
    for nid, node in list(nodes.items()):
        primary_name = _ALSO_APPLY_CARDS.get(node.step)
        if primary_name is None:
            continue
        params = dict(node.params)
        if "also_apply" not in params and "anchor" not in params:
            continue
        also_raw = params.pop("also_apply", "")
        anchor = params.pop("anchor", None)
        primary = str(params.get(primary_name, "") or "")
        also: List[str] = []
        for tok in str(also_raw or "").split(","):
            tok = tok.strip()
            if tok and tok != primary and tok not in also:
                also.append(tok)
        borrow = node.step in _ANCHOR_CARDS and str(anchor or "source") == "source"
        if node.step in _ANCHOR_CARDS:
            params.setdefault("range_from", "")
        node.params = params

        made: List[str] = []
        for stream in also:
            new_id = _fresh_id(nodes, "%s_%s" % (nid, stream))
            p = dict(params)
            p[primary_name] = stream
            if node.step in _ANCHOR_CARDS:
                p["range_from"] = primary if borrow else ""
            nodes[new_id] = RecipeNode(id=new_id, step=node.step, params=p,
                                       enabled=node.enabled)
            made.append(new_id)
        if made:
            extra[nid] = (made, borrow)

    if not extra:
        return
    for k, route in list(routes.items()):
        out: List[str] = []
        for nid in route:
            made, first = extra.get(nid, ([], False))
            if first:
                out.extend(made)
                out.append(nid)
            else:
                out.append(nid)
                out.extend(made)
        routes[k] = out


@dataclass
class Recipe:
    """一份完整 recipe（單一 JSON 檔可互傳）。"""
    recipe_id: str
    routes: Dict[str, List[str]]      # dataset kind → 依序的節點 id（v1 線性）
    nodes: Dict[str, RecipeNode]
    score: ScoreSpec
    version: int = 1
    author: str = ""
    description: str = ""
    edges: List[List[str]] = field(default_factory=list)  # 額外 DAG 邊

    # ---- JSON serde -------------------------------------------------------
    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "version": int(self.version),
            "author": self.author,
            "description": self.description,
            "routes": {k: list(v) for k, v in self.routes.items()},
            "nodes": {
                nid: {
                    "step": n.step,
                    "params": dict(n.params),
                    "enabled": bool(n.enabled),
                }
                for nid, n in self.nodes.items()
            },
            "edges": [list(e) for e in self.edges],
            "score": {
                "expr": self.score.expr,
                "threshold": float(self.score.threshold),
                "bins": dict(self.score.bins),
            },
        }

    @classmethod
    def from_json_dict(cls, d: Dict[str, Any]) -> "Recipe":
        if not isinstance(d, dict):
            raise RecipeError(f"the top level of a recipe JSON must be an object "
                              f"(dict), got {type(d).__name__}")
        missing = [k for k in ("recipe_id", "routes", "nodes", "score") if k not in d]
        if missing:
            raise RecipeError(f"recipe JSON is missing required fields: {missing}")

        nodes: Dict[str, RecipeNode] = {}
        for nid, nd in dict(d["nodes"]).items():
            if not isinstance(nd, dict) or "step" not in nd:
                raise RecipeError(f"step '{nid}' has no 'step' field")
            nodes[str(nid)] = RecipeNode(
                id=str(nid),
                step=str(nd["step"]),
                params=dict(nd.get("params") or {}),
                enabled=bool(nd.get("enabled", True)),
            )

        sd = d["score"]
        if not isinstance(sd, dict) or "expr" not in sd:
            raise RecipeError(
                "the score block must be an object containing 'expr'")
        score = ScoreSpec(
            expr=str(sd["expr"]),
            threshold=float(sd.get("threshold", 0.0)),
            bins={str(k): int(v) for k, v in dict(sd.get("bins") or {}).items()},
        )

        routes = {str(k): [str(x) for x in v] for k, v in dict(d["routes"]).items()}

        edges: List[List[str]] = []
        for e in (d.get("edges") or []):
            e = list(e)
            if len(e) != 2:
                raise RecipeError(f"an edge must be [from, to] — two step ids; got: {e}")
            edges.append([str(e[0]), str(e[1])])

        # 舊 recipe（F7-18 之前）的 also_apply / anchor：展開成一張卡一條流。
        # 做在這裡而不是各張卡的 validate_params 裡，因為它會**增加節點**——
        # 那是 recipe 層級的事，一張卡看不到自己以外的東西。
        _migrate_also_apply(nodes, routes)

        return cls(
            recipe_id=str(d["recipe_id"]),
            routes=routes,
            nodes=nodes,
            score=score,
            version=int(d.get("version", 1)),
            author=str(d.get("author", "")),
            description=str(d.get("description", "")),
            edges=edges,
        )

    def save(self, path: Any) -> None:
        """寫入 JSON 檔（utf-8、indent=2、atomic ``.tmp`` + ``os.replace``）。"""
        path = str(path)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_json_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Any) -> "Recipe":
        with open(str(path), "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_json_dict(d)


# ---------------------------------------------------------------------------
# 執行順序（Kahn 拓撲排序，平手依 route 位置 → deterministic）
# ---------------------------------------------------------------------------
def execution_order(recipe: Recipe, kind: str) -> List[str]:
    """回傳 ``kind`` 這條 route 的節點執行順序。

    邊 = route 相鄰對（load→norm→align…）∪ 顯式 ``edges``（兩端都在該
    route 內才算）。循環或未知 kind → :class:`RecipeError`。
    """
    if kind not in recipe.routes:
        raise RecipeError(
            f"unknown input-type route '{kind}'; this recipe only defines: "
            f"{sorted(recipe.routes)}")
    route = list(recipe.routes[kind])
    if not route:
        return []
    pos = {nid: i for i, nid in enumerate(route)}
    node_set = set(route)

    pair_edges: Set[tuple] = set()
    for a, b in zip(route, route[1:]):
        pair_edges.add((a, b))
    for e in recipe.edges:
        if len(e) == 2 and e[0] in node_set and e[1] in node_set:
            pair_edges.add((e[0], e[1]))  # 自迴圈也收進來 → Kahn 會偵測為循環

    indeg = {n: 0 for n in route}
    adj: Dict[str, List[str]] = {n: [] for n in route}
    for a, b in pair_edges:
        adj[a].append(b)
        indeg[b] += 1

    heap = [pos[n] for n in route if indeg[n] == 0]
    heapq.heapify(heap)
    out: List[str] = []
    while heap:
        n = route[heapq.heappop(heap)]
        out.append(n)
        for m in sorted(adj[n], key=lambda x: pos[x]):
            indeg[m] -= 1
            if indeg[m] == 0:
                heapq.heappush(heap, pos[m])
    if len(out) != len(route):
        stuck = [n for n in route if n not in out]
        raise RecipeError(
            f"route '{kind}' has a cycle in its step connections, so no "
            f"execution order can be determined; stuck steps: {stuck}")
    return out


# ---------------------------------------------------------------------------
# lint 式驗證（KLIP Issue 風格：一次列出所有問題）
# ---------------------------------------------------------------------------
@dataclass
class Issue:
    """一條驗證發現：``level`` 為 "error" 或 "warning"。"""
    code: str
    level: str
    node_id: Optional[str]
    title: str
    detail: str


def _clean_params_for(step_cls: Type[Step], raw: Dict[str, Any],
                      issues: List[Issue], nid: str) -> Dict[str, Any]:
    """驗證參數；壞參數記 Issue 並改用預設值，讓後續模擬檢查照常進行。"""
    try:
        return step_cls.validate_params(raw)
    except ParamError as e:
        issues.append(Issue(
            code="bad-param", level="error", node_id=nid,
            title="Invalid parameter", detail=str(e)))
        try:
            return step_cls.validate_params(None)  # 全預設值
        except ParamError:  # pragma: no cover — 預設值本身壞掉屬程式錯誤
            return {}


def validate(recipe: Recipe, kind: Optional[str] = None,
             registry: Optional[Dict[str, Type[Step]]] = None) -> List[Issue]:
    """lint 式驗證：收集**所有**問題後一次回傳（不會 raise）。

    檢查項（code）：unknown-step / bad-param / not-configured / unknown-node /
    unknown-route / cycle / missing-image / unknown-region / requires-ref /
    score-expr / unknown-feature（warning）/ feature-collision（warning）/
    bad-bins。
    """
    if registry is None:
        registry = REGISTRY
    issues: List[Issue] = []

    # ---- bins 必須含 below / above ----
    bins = recipe.score.bins or {}
    for key in ("below", "above"):
        if key not in bins:
            issues.append(Issue(
                code="bad-bins", level="error", node_id=None,
                title="Incomplete bin settings",
                detail=f"score.bins has no '{key}' (both below and above bin "
                       f"values are required); it currently has: "
                       f"{sorted(bins)}"))

    # ---- 要檢查哪些 route ----
    if kind is not None:
        if kind not in recipe.routes:
            issues.append(Issue(
                code="unknown-route", level="error", node_id=None,
                title=f"Unknown input-type route '{kind}'",
                detail=f"this recipe only defines routes: "
                       f"{sorted(recipe.routes)}"))
            kinds: List[str] = []
        else:
            kinds = [kind]
    else:
        kinds = list(recipe.routes)

    # ---- 每個節點：step 存在？參數合法？----
    clean_params: Dict[str, Dict[str, Any]] = {}
    for nid, node in recipe.nodes.items():
        step_cls = registry.get(node.step)
        if step_cls is None:
            issues.append(Issue(
                code="unknown-step", level="error", node_id=nid,
                title=f"Unknown card '{node.step}'",
                detail=f"step '{nid}' uses '{node.step}', which is not in the "
                       f"card library; available cards: {sorted(registry)}"))
            continue
        clean_params[nid] = _clean_params_for(step_cls, node.params, issues, nid)

        # 參數全部合法，卡片還是可能**沒設定完**（F7-13）。空字串的模板是完全
        # 合法的 str —— 但那張卡跑起來每一顆都會失敗，而以前要跑過一次才知道。
        try:
            unset = list(step_cls.configuration_issues(clean_params[nid]))
        except Exception:                       # noqa: BLE001 — 卡片自己的程式
            unset = []
        for msg in unset:
            issues.append(Issue(
                code="not-configured", level="error", node_id=nid,
                title=f"{step_cls.label} is not set up yet", detail=str(msg)))

    # ---- score 表達式解析 ----
    expr = None
    try:
        expr = parse_expression(recipe.score.expr)
    except ExpressionError as e:
        issues.append(Issue(
            code="score-expr", level="error", node_id=None,
            title="Score expression failed to parse", detail=str(e)))

    # ---- 每條 route：unknown-node / cycle / reads 模擬 / requires_ref ----
    for k in kinds:
        route = recipe.routes[k]
        for nid in route:
            if nid not in recipe.nodes:
                issues.append(Issue(
                    code="unknown-node", level="error", node_id=nid,
                    title=f"route '{k}' refers to a step that does not exist: "
                          f"'{nid}'",
                    detail=f"nodes has no '{nid}'; defined steps: "
                           f"{sorted(recipe.nodes)}"))
        try:
            order = execution_order(recipe, k)
        except RecipeError as e:
            issues.append(Issue(
                code="cycle", level="error", node_id=None,
                title=f"route '{k}' has a cycle in its step connections",
                detail=str(e)))
            continue

        # reads-satisfaction 模擬：seed = 第一張啟用卡（load 卡）的 writes；
        # 之後每張卡 reads 必須 ⊆ 累積 writes。停用節點跳過（與 runtime 一致）。
        avail: Set[str] = set()
        feats: Set[str] = {"score"}
        regions: Set[str] = set()
        #: feature 名 -> 第一個產出它的節點。特徵是**扁平的全域命名空間**，
        #: 所以兩張同型別的量測卡（例如量兩個 ROI 的 glv_stats）會寫同一組名字，
        #: 後面那張安靜地蓋掉前面那張 —— 跑得完、有數字、少一半。
        feat_owner: Dict[str, str] = {}
        first = True
        for nid in order:
            node = recipe.nodes.get(nid)
            if node is None or not node.enabled:
                continue
            step_cls = registry.get(node.step)
            if step_cls is None:
                continue  # 已記 unknown-step
            p = clean_params.get(nid, {})
            if first:
                # 第一張卡（load）：reads / requires_ref 不檢查；
                # writes 用 kind-aware 宣告（load 卡依資料型別決定會有哪些流）
                avail |= set(step_cls.resolve_writes_for_kind(p, k))
                for f in step_cls.resolve_features(p):
                    feat_owner.setdefault(f, nid)
                feats |= set(step_cls.resolve_features(p))
                regions |= set(step_cls.resolve_regions_out(p))
                first = False
                continue
            missing = [x for x in step_cls.resolve_reads(p) if x not in avail]
            if missing:
                issues.append(Issue(
                    code="missing-image", level="error", node_id=nid,
                    title=f"step '{nid}' is missing an upstream image",
                    detail=f"route '{k}': it needs image streams {missing}, but "
                           f"upstream only provides {sorted(avail)}"))
            if k == "rsem" and getattr(step_cls, "requires_ref", False) \
                    and "ref" not in avail:
                issues.append(Issue(
                    code="requires-ref", level="error", node_id=nid,
                    title=f"step '{nid}' needs a reference image",
                    detail=f"'{node.step}' needs ref, but a single-image rsem "
                           f"input has none and no upstream card produces "
                           f"'ref' (currently provided: {sorted(avail)})"))
            # 具名區域走跟影像流一樣的檢查（F7-9）。沒有這一段的話，
            # 「量測卡指到沒人定義的區域」在跑之前是看不出來的 ——
            # 名字打錯要等執行期 StepError，而預設的 'blob' 少了上游的
            # Blob 卡更慘：它會安靜地退回量整張圖，跑得完、有數字、且是錯的。
            missing_roi = [x for x in step_cls.resolve_regions_in(p)
                           if x not in regions]
            if missing_roi:
                issues.append(Issue(
                    code="unknown-region", level="error", node_id=nid,
                    title=f"step '{nid}' uses a region nobody defines",
                    detail=f"route '{k}': it measures region(s) {missing_roi}, "
                           f"but no upstream card defines them (currently "
                           f"defined: {sorted(regions)}). Add a Region card "
                           f"upstream, or clear the roi parameter to measure "
                           f"the whole image."))

            # 特徵撞名：後面的卡會安靜地蓋掉前面的（Context.add_feature 允許
            # 覆寫，只在 meta 留紀錄）。最典型的踩法是「量兩個 ROI」——
            # 兩張 glv_stats 都寫 glv_mean，跑完只剩後面那張的值，而分數表達式
            # 完全沒有辦法指到前面那一個。這是**警告**不是 error：同名覆寫有時
            # 是刻意的（例如重跑一次 normalize），但它必須看得見。
            for f in step_cls.resolve_features(p):
                owner = feat_owner.get(f)
                if owner is not None and owner != nid:
                    issues.append(Issue(
                        code="feature-collision", level="warning", node_id=nid,
                        title=f"step '{nid}' overwrites the feature '{f}'",
                        detail=f"route '{k}': '{f}' is already produced by "
                               f"'{owner}'; the later value wins and the earlier "
                               f"one cannot be referenced from the score "
                               f"expression at all. Give one of the two cards a "
                               f"different output name if you need both."))
                else:
                    feat_owner.setdefault(f, nid)

            avail |= set(step_cls.resolve_writes(p))
            feats |= set(step_cls.resolve_features(p))
            regions |= set(step_cls.resolve_regions_out(p))

        # score 變數 ⊆ 此 route 會產出的特徵 ∪ {"score"}（僅警告）
        if expr is not None:
            unknown = sorted(expr.variables - feats)
            if unknown:
                issues.append(Issue(
                    code="unknown-feature", level="warning", node_id=None,
                    title="Score expression uses unknown features",
                    detail=f"route '{k}': the variables {unknown} are not among "
                           f"the features this route produces ({sorted(feats)}), "
                           f"so the score may not be computable at run time"))

    return issues
