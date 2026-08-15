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
                          "enabled": true},
                "decide": {"step": "adc",
                           "params": {"expr": "snr_max * sqrt(area_px)",
                                      "threshold": 3.0}}},
      "edges": [["subtract","snr"]]
    }

**判定沒有自己的欄位** —— 它是一張卡（``steps/adc.py``），跟其他卡一樣站在
route 上。F9 Phase 3d 之前這裡有一個固定的 ``"score"`` 區塊，一份 recipe 只能有
一套標準、而且它不在畫布上；現在一份 recipe 想放幾張判定卡就放幾張（每條分支
一張，門檻各自調）。**舊檔案的 ``score`` 區塊仍讀得進來**，載入時遷移成每條
route 尾端的一張 ``adc`` 卡（見 :func:`_migrate_score_block`）。

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
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from .expression import ExpressionError, parse_expression
from .step import CATEGORY_ADC, ParamError, Step, REGISTRY

__all__ = [
    "RecipeError", "RecipeNode", "Recipe",
    "Issue", "execution_order", "validate", "edge_pair",
]


class RecipeError(ValueError):
    """Recipe 結構性錯誤（循環、未知 route、JSON 缺欄位…）。"""


def _app_version() -> str:
    """現在跑的這一版 ADEPT。"""
    from adept import __version__
    return str(__version__)


def _version_tuple(text: str):
    """``"0.2.1"`` → ``(0, 2, 1)``；比不出來回 ``None``（就不硬說誰新誰舊）。"""
    parts = []
    for chunk in str(text or "").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def version_skew(recipe_version: str) -> str:
    """這份 recipe 是不是**比現在這個程式新**存的；是的話回一句白話，否則空字串。

    講得出這句話，「unknown parameters」才有正確的意思。沒有它，使用者看到的
    是「這份檔案壞了」，於是他會去重做一份 recipe —— 而該做的是更新程式。
    """
    theirs = str(recipe_version or "").strip()
    if not theirs:
        return ""
    mine = _app_version()
    if theirs == mine:
        return ""
    a, b = _version_tuple(theirs), _version_tuple(mine)
    if a is not None and b is not None and a <= b:
        return ""                      # 檔案比較舊 → 遷移的事，不是版本落差
    return ("This recipe was saved by ADEPT %s and this build is %s — update "
            "ADEPT on this machine before using it." % (theirs, mine))


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


# ---------------------------------------------------------------------------
# 舊 recipe 相容遷移（F9 Phase 3d）：``score`` 固定欄位 → 一張判定卡
# ---------------------------------------------------------------------------
#: 遷移出來的判定卡叫什麼（撞名時後面接 route 名）。
_MIGRATED_ADC_ID = "decide"


def _migrate_score_block(nodes: Dict[str, "RecipeNode"],
                         routes: Dict[str, List[str]],
                         sd: Dict[str, Any]) -> None:
    """舊檔案的 ``score`` 區塊 → 每條 route 尾端一張 ``adc`` 卡。

    為什麼是**每條 route 一張**而不是共用一張：``score`` 那個欄位本來就是
    「這份 recipe 的唯一標準」，共用一張確實等價 —— 但遷移完的圖是使用者接下來
    要**編**的東西，而共用的那一張會讓「改 rsem 的門檻」順手改掉 patch 的。
    一條分支一張是這一輪整件事的重點，遷移就照那個形狀給。

    判準是「這個 dict 有沒有 ``score`` 這個鍵」—— ``to_json_dict()`` 已經不寫它，
    所以 round-trip 回來的 dict 不會再被遷移一次（那個坑見 CLAUDE.md §7 的
    ``subtract.b`` 那一列）。
    """
    params = {
        "expr": str(sd.get("expr", "") or ""),
        "threshold": float(sd.get("threshold", 0.0) or 0.0),
        "bin_below": int(dict(sd.get("bins") or {}).get("below", 0)),
        "bin_above": int(dict(sd.get("bins") or {}).get("above", 1)),
        "label": "",
    }
    for k in sorted(routes):
        nid = _MIGRATED_ADC_ID
        n = 1
        while nid in nodes:
            nid = "%s_%s" % (_MIGRATED_ADC_ID, k) if n == 1 else \
                  "%s_%s%d" % (_MIGRATED_ADC_ID, k, n)
            n += 1
        nodes[nid] = RecipeNode(id=nid, step="adc", params=dict(params))
        routes[k] = list(routes[k]) + [nid]


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


# ---------------------------------------------------------------------------
# 舊 recipe 相容遷移（F7-20）：合併卡片 + 主流參數改名 streams
# ---------------------------------------------------------------------------
#: 舊 step key → (新 key, 主流參數的舊名, 要補上的固定參數, 參數改名表)
#:
#: 四張 Normalize 卡與三張 tone 卡在 F7-20 各自併成一張，方法變成一個下拉。
#: 遷移要做的事有三件：換 key、把主流參數改名成 ``streams``、把「是哪一張卡」
#: 這個資訊變成 ``method`` 的值。
#:
#: 為什麼要遷移而不是直接不認得：跟 §22.6 同一個理由 —— recipe 是使用者存在
#: 磁碟上、拿來交接的檔案，認不得等於「工具壞了」。
_MERGED_CARDS: Dict[str, tuple] = {
    # 舊 key:          (新 key,      主流舊名,    固定參數,                   改名表)
    "percentile_norm": ("normalize", "source", {"method": "percentile"}, {}),
    "glv_mask_norm":   ("normalize", "source", {"method": "glv_band"}, {}),
    "local_contrast":  ("normalize", "target", {"method": "local"}, {}),
    # hist_match 的舊 ``method``（exact/linear/percentile）跟合併後的方法選擇
    # 撞名，所以改叫 match_method。
    "hist_match":      ("normalize", "moving", {"method": "match"},
                        {"method": "match_method"}),
    "brightness_contrast": ("tone", "target", {}, {}),
    "gamma":               ("tone", "target", {}, {}),
    "invert":              ("tone", "target", {"invert": True}, {}),
}

#: 沒有合併、但主流參數一起改名成 ``streams`` 的卡（F7-19）。
_RENAMED_STREAM_PARAM: Dict[str, str] = {
    "denoise": "target",
    "flatten": "target",
}


#: 改過名的**參數值**：``(step, param) -> {舊值: 新值}``。
#:
#: F8 第一版的 ``roi_cross`` 只有兩層灰階，所以「要哪一組」是 ``dark`` /
#: ``bright``。實際的 layout 常常三層以上（站點回報 MG 約 220、EPI 約 180），
#: 二分法把那兩層併在一起，於是規則改成排名。舊檔案的兩個值仍然說得通
#: —— 它們就是排名的兩端。
#:
#: 為什麼是遷移而不是把舊值留在 choices 裡：留著的話下拉選單會有兩個意思一樣
#: 的選項，而使用者不知道該挑哪個。**相容性是檔案格式的事，不是 UI 的事。**
_RENAMED_VALUES: Dict[Tuple[str, str], Dict[str, str]] = {
    ("roi_cross", "vertical_select"): {"dark": "darkest", "bright": "brightest"},
    ("roi_cross", "horizontal_select"): {"dark": "darkest", "bright": "brightest"},
}


def _predates_subtract_b_default(app_version: Any) -> bool:
    """這份 JSON 是「``subtract`` 改預設值之前」存的嗎（見 ``from_json_dict``）。

    判準是 **``app_version`` 這一欄在不在**，不是版本號大小 —— 版本號現在還是
    ``0.1.0.dev0``，比不出 8/14 之前或之後。而「有沒有這一欄」剛好夠用：

    * 真正的舊檔案（手寫的、或這一欄出現之前存的）**沒有**這一欄 → 要補。
    * 這一欄出現之後由 Studio 存的檔案，參數一律寫滿，``b`` 本來就在裡面
      → 補不補都一樣。
    * ``to_json_dict()`` **一定**會寫這一欄，所以任何 round-trip 回來的
      dict（``run_batch`` 送進 worker 的那份）都不會被誤認成舊檔案 ——
      那正是這個判準要擋的那件事。

    型別上收 ``Any``：這個值是從 JSON 來的，別人手改過什麼都有可能。
    """
    return not str(app_version or "").strip()


def _migrate_renamed_values(nodes: Dict[str, "RecipeNode"]) -> None:
    """把改過名的參數**值**換成新的（就地改寫 nodes）。"""
    for nid, node in list(nodes.items()):
        params = dict(node.params)
        touched = False
        for (step, name), mapping in _RENAMED_VALUES.items():
            if node.step != step or name not in params:
                continue
            new = mapping.get(str(params[name]))
            if new is not None:
                params[name] = new
                touched = True
        if touched:
            nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                    enabled=node.enabled)


def _migrate_merged_cards(nodes: Dict[str, "RecipeNode"]) -> None:
    """把 F7-20 之前的卡片名與參數名換成合併後的（就地改寫 nodes）。

    ⚠ 這一道**必須跑在 :func:`_migrate_also_apply` 之後**：那一道會把
    ``also_apply`` 展開成好幾張**舊 key** 的卡，展開出來的那幾張也要一起換名。
    先展開再收合看起來繞了一圈，但遷移鏈要一段一段接 —— 寫一條
    「``also_apply`` 直接變 ``streams``」的捷徑只有舊檔案會走到，
    永遠不會有人在上面測試。
    """
    for nid, node in list(nodes.items()):
        params = dict(node.params)
        merged = _MERGED_CARDS.get(node.step)
        if merged is not None:
            new_key, primary_name, fixed, renames = merged
            for old, new in renames.items():
                if old in params:
                    params[new] = params.pop(old)
            if primary_name in params:
                params["streams"] = params.pop(primary_name)
            for k, v in fixed.items():
                params.setdefault(k, v)
            nodes[nid] = RecipeNode(id=node.id, step=new_key, params=params,
                                    enabled=node.enabled)
            continue
        primary_name = _RENAMED_STREAM_PARAM.get(node.step)
        if primary_name is not None and primary_name in params:
            params["streams"] = params.pop(primary_name)
            nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                    enabled=node.enabled)


@dataclass
class Recipe:
    """一份完整 recipe（單一 JSON 檔可互傳）。"""
    recipe_id: str
    routes: Dict[str, List[str]]      # dataset kind → 依序的節點 id（v1 線性）
    nodes: Dict[str, RecipeNode]
    version: int = 1
    author: str = ""
    description: str = ""
    edges: List[List[str]] = field(default_factory=list)  # 額外 DAG 邊
    #: **哪一版的 ADEPT 存的**（存檔時自動填；舊檔案沒有這欄，是空字串）。
    #:
    #: 為什麼需要：開發在家用機、執行在公司機，而公司機是用複製檔案更新的
    #: （`AGENTS.md`），所以兩邊的版本本來就會不同步。一份新版存的 recipe 在
    #: 舊版上打開，看到的是「unknown parameters: ['…']」—— 那句話的意思是
    #: 「這份檔案壞了」，但真正的情況是「我的程式舊了」。差一個字，使用者會去
    #: 重做一份 recipe 而不是去更新程式。
    #: 新建的 recipe 就是「這一版寫的」，所以預設值是現在這一版 ——
    #: 空字串保留給**舊檔案**（那些檔案是真的沒有這個欄位）。
    app_version: str = field(default_factory=_app_version)

    # ---- JSON serde -------------------------------------------------------
    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "version": int(self.version),
            # 存檔時一律寫**現在這一版**（不是讀進來的那一版）——
            # 這個欄位要回答的是「這個檔案是誰寫的」。
            "app_version": _app_version(),
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
        }

    @classmethod
    def from_json_dict(cls, d: Dict[str, Any]) -> "Recipe":
        if not isinstance(d, dict):
            raise RecipeError(f"the top level of a recipe JSON must be an object "
                              f"(dict), got {type(d).__name__}")
        missing = [k for k in ("recipe_id", "routes", "nodes") if k not in d]
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

        routes ={str(k): [str(x) for x in v] for k, v in dict(d["routes"]).items()}

        # 一條線有兩種寫法（F9 Phase 3a 起）：
        #   ["a", "b"]                          兩端的預設埠（既有檔案都是這種）
        #   ["a", "match", "b", "in"]           **講明從哪個埠出去、進哪個埠**
        # 後者是條件分流存得起來的前提：一張卡有 match / else 兩個出口，
        # 只寫 ["r", "x"] 說不出這條線是從哪一個出去的。
        edges: List[List[str]] = []
        for e in (d.get("edges") or []):
            e = list(e)
            if len(e) not in (2, 4):
                raise RecipeError(
                    "an edge must be [from, to] or [from, from_port, to, to_port]; "
                    "got: %r" % (e,))
            edges.append([str(x) for x in e])

        # 舊 recipe（F7-18 之前）的 also_apply / anchor：展開成一張卡一條流。
        # 做在這裡而不是各張卡的 validate_params 裡，因為它會**增加節點**——
        # 那是 recipe 層級的事，一張卡看不到自己以外的東西。
        _migrate_also_apply(nodes, routes)
        # 再把合併掉的卡片名／參數名換過來（順序不可顛倒，見函式 docstring）。
        _migrate_merged_cards(nodes)
        # 最後把改過名的**參數值**換掉（F8：兩層的 dark/bright → 排名）。
        _migrate_renamed_values(nodes)
        # subtract 的預設 b 於 2026-08-14 從 ref_aligned 改成 ref（patch 本來
        # 就對齊）。檔案裡**沒寫** b 的 subtract 是照舊預設蓋的 —— Studio 存檔
        # 一律把參數寫滿，省略只會出現在改版前的檔案（或手寫檔）。不補的話，
        # 一份「align → subtract」的舊 recipe 會安靜地跳過對位，分數整批變掉
        # —— dual-route e2e 當場從 22/24 掉到 18/24。既有 recipe 一份都不能
        # 被改變行為：載入時把舊預設寫回去。
        #
        # ⚠ **只對「改版之前存的檔案」做。**（2026-08-15 修）
        #
        # 這一道以前是無條件的，判準是「這個 dict 缺了 b」。那跟「這是一份舊
        # 檔案」只在**檔案**這條路上等價 —— 而 ``from_json_dict`` 還有第二個
        # 呼叫者：``batch.run_batch`` 把 recipe 序列化送進 worker，worker 再
        # 反序列化回來。於是一份程式化建立、``subtract`` 沒寫 ``b`` 的 recipe：
        #
        #     workers <= 1（同進程）  → b = "ref"（卡片預設）
        #     workers >= 2（子進程）  → b = "ref_aligned"（被這一道補的）
        #
        # 同一份 recipe、同一批資料，換一個 ``--workers`` 就換一組分數，而且
        # 兩邊都跑得完、都有數字。``run_batch`` 在 ``n <= 1`` 時也走循序路徑，
        # 所以連「跑一顆」與「跑兩顆」都會不一樣。
        #
        # ``app_version`` 正好是真正的判準：**新版寫出來的檔案一定有這一欄**
        # （``to_json_dict`` 固定填現在這一版），所以「沒有這一欄」就是
        # 「改版之前存的」。round-trip 回來的 dict 帶著版本，不再被誤認成舊檔。
        if _predates_subtract_b_default(d.get("app_version", "")):
            for node in nodes.values():
                if node.step == "subtract" and "b" not in node.params:
                    node.params["b"] = "ref_aligned"

        # 判定從固定欄位變成一張卡（F9 Phase 3d）。**放在所有遷移的最後**：
        # 前面幾道會增刪節點與改 route，而這一道要接在 route 的尾巴上。
        sd = d.get("score")
        if isinstance(sd, dict) and "expr" in sd:
            _migrate_score_block(nodes, routes, sd)

        return cls(
            recipe_id=str(d["recipe_id"]),
            routes=routes,
            nodes=nodes,
            app_version=str(d.get("app_version", "") or ""),
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

def edge_pair(e: Any) -> Optional[Tuple[str, str]]:
    """一條線的 ``(來源節點, 目的節點)``，兩種寫法都認得。

    ``["a", "b"]`` → ``("a", "b")``；
    ``["a", "match", "b", "in"]`` → ``("a", "b")``（埠名在這裡不重要 ——
    要排執行順序只需要知道誰在誰前面）。看不懂的形狀回 ``None``。
    """
    e = list(e or ())
    if len(e) == 2:
        return (str(e[0]), str(e[1]))
    if len(e) == 4:
        return (str(e[0]), str(e[2]))
    return None


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
        pair = edge_pair(e)               # 兩種寫法都收（見 from_json_dict）
        if pair is not None and pair[0] in node_set and pair[1] in node_set:
            pair_edges.add(pair)          # 自迴圈也收進來 → Kahn 會偵測為循環

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
                      issues: List[Issue], nid: str,
                      skew: str = "") -> Dict[str, Any]:
    """驗證參數；壞參數記 Issue 並改用預設值，讓後續模擬檢查照常進行。

    ``skew`` 有值時附在訊息後面 —— 「認不得這個參數」最常見的原因不是檔案壞了，
    是**這台的程式比較舊**（開發機與公司機是靠複製檔案同步的，見 AGENTS.md）。
    """
    try:
        return step_cls.validate_params(raw)
    except ParamError as e:
        detail = str(e)
        if skew:
            detail = "%s  %s" % (detail, skew)
        issues.append(Issue(
            code="bad-param", level="error", node_id=nid,
            title="Invalid parameter", detail=detail))
        try:
            return step_cls.validate_params(None)  # 全預設值
        except ParamError:  # pragma: no cover — 預設值本身壞掉屬程式錯誤
            return {}


def validate(recipe: Recipe, kind: Optional[str] = None,
             registry: Optional[Dict[str, Type[Step]]] = None) -> List[Issue]:
    """lint 式驗證：收集**所有**問題後一次回傳（不會 raise）。

    檢查項（code）：unknown-step / bad-param / not-configured / unknown-node /
    unknown-route / cycle / missing-image / unknown-region / requires-ref /
    no-decision（warning）/ unknown-feature（warning）/
    feature-collision（warning）。
    """
    if registry is None:
        registry = REGISTRY
    issues: List[Issue] = []

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
    # 認不得的參數 / 認不得的卡片，最常見的原因是**這台的程式比較舊**。
    skew = version_skew(getattr(recipe, "app_version", ""))
    clean_params: Dict[str, Dict[str, Any]] = {}
    for nid, node in recipe.nodes.items():
        step_cls = registry.get(node.step)
        if step_cls is None:
            issues.append(Issue(
                code="unknown-step", level="error", node_id=nid,
                title=f"Unknown card '{node.step}'",
                detail=(f"step '{nid}' uses '{node.step}', which is not in the "
                        f"card library; available cards: {sorted(registry)}"
                        + (f"  {skew}" if skew else ""))))
            continue
        clean_params[nid] = _clean_params_for(step_cls, node.params, issues,
                                              nid, skew)

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

    # ---- 每條 route：unknown-node / cycle / reads 模擬 / requires_ref ----
    #: route → 這條路上有沒有踩到判定卡（見 route 迴圈末尾的 no-decision）。
    is_decided: Dict[str, bool] = {}
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
            if k == "rsem" and step_cls.resolve_requires_ref(p) \
                    and "ref" not in avail:
                issues.append(Issue(
                    code="requires-ref", level="error", node_id=nid,
                    title=f"step '{nid}' needs a reference image",
                    detail=f"'{node.step}' needs ref, but a single-image rsem "
                           f"input has none and no upstream card produces "
                           f"'ref' (currently provided: {sorted(avail)})"))
            # 具名區域走跟影像流一樣的檢查（F7-9）。沒有這一段的話，
            # 「量測卡指到沒人定義的區域」在跑之前是看不出來的 ——
            # 名字打錯要等執行期 StepError，而更慘的是安靜地退回量整張圖 ——
            # 跑得完、有數字、且是錯的。
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

            # 判定卡的分數式子只能用**它上游**產出的特徵（F9 Phase 3d）。
            # 這一段以前是整份 recipe 一次檢查（那時候分數是固定欄位，只有一
            # 個），現在每張判定卡各自檢查、而且是拿**走到這裡為止**累積的特徵
            # 比 —— 一張排在量測前面的判定卡，答案本來就不該算得出來。
            if getattr(step_cls, "category", "") == CATEGORY_ADC:
                if not is_decided.get(k):
                    is_decided[k] = True
                try:
                    dexpr = parse_expression(str(p.get("expr", "") or ""))
                except ExpressionError:
                    dexpr = None      # 已由 not-configured 講過，不重複講
                if dexpr is not None:
                    unknown = sorted(dexpr.variables - feats)
                    if unknown:
                        issues.append(Issue(
                            code="unknown-feature", level="warning", node_id=nid,
                            title="Score expression uses unknown features",
                            detail=f"route '{k}': the variables {unknown} are "
                                   f"not among the features produced upstream "
                                   f"of this card ({sorted(feats)}), so the "
                                   f"score may not be computable at run time"))

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

        # 整條 route 走完都沒有一張判定卡 → 這批跑得完，但**每一顆都沒有結論**
        # （score/bin 留 None，見 ``engine._judge``）。是 warning 不是 error：
        # 只想看特徵、拿 CSV 出去自己算的人是合法的用法。
        if not is_decided.get(k):
            issues.append(Issue(
                code="no-decision", level="warning", node_id=None,
                title=f"route '{k}' never reaches a Decide card",
                detail=f"route '{k}' measures features but nothing turns them "
                       f"into a score, so every defect will come out without a "
                       f"score or a bin. Add a Decide card at the end of the "
                       f"branch if you want a verdict."))

    return issues
