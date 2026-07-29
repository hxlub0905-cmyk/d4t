# ADEPT Studio view-model — authored 2026-07-28 (M3). Qt-free（可 headless 測試）.
"""Studio 的編輯狀態模型：UI 元件只做顯示與轉發，所有 recipe 編輯邏輯集中在這裡。

- ``RecipeModel``：包住一條 route 的可變編輯模型（v1 Studio 一次編一條 route）。
  add/remove/move/set_param 全部走 ParamSpec 驗證；`to_recipe()` 產出可存檔/可跑的
  Recipe。任何變更會呼叫 listeners（UI 拿來刷新）。
- 直方圖/門檻工具函數：`histogram()`、`rebin()` —— 拖門檻線秒回的純計算部分。
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from adept.core.pipeline import (
    ParamError, Recipe, RecipeNode, ScoreSpec, get_step, validate,
)


class RecipeModel:
    """單一 route 的 recipe 編輯模型（預設 kind="ebi_patch"）。"""

    def __init__(self, kind: str = "ebi_patch") -> None:
        self.kind = kind
        self.recipe_id = "untitled"
        self.author = ""
        self.description = ""
        self.version = 1
        self.node_order: List[str] = []            # route 順序（= 拓撲順序）
        self.nodes: Dict[str, RecipeNode] = {}
        #: 顯式的節點連線（F7-6 畫布）。``node_order`` 仍然是執行順序，
        #: 但有 edges 時它由拓撲排序算出來，不再是「使用者加卡片的順序」。
        #: 引擎那邊 ``execution_order`` 本來就是「route 相鄰對 ∪ edges」，
        #: 所以把 route 寫成拓撲順序與 edges 併存，語意一致且向後相容。
        self.edges: List[Tuple[str, str]] = []
        self.expr = "0"
        self.threshold = 0.0
        self.bins = {"below": 0, "above": 1}
        self.dirty = False
        self._listeners: List[Callable[[], None]] = []

    # ---- listener ---------------------------------------------------------
    def add_listener(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _changed(self) -> None:
        self.dirty = True
        for fn in list(self._listeners):
            fn()

    # ---- 節點操作 ----------------------------------------------------------
    def _new_id(self, step_key: str) -> str:
        base = step_key
        if base not in self.nodes:
            return base
        i = 2
        while f"{base}{i}" in self.nodes:
            i += 1
        return f"{base}{i}"

    def add_step(self, step_key: str, at: Optional[int] = None) -> str:
        step_cls = get_step(step_key)          # 未知 key 會 raise KeyError
        node_id = self._new_id(step_key)
        params = step_cls.validate_params({})  # 全預設
        self.nodes[node_id] = RecipeNode(id=node_id, step=step_key, params=params)
        if at is None:
            self.node_order.append(node_id)
        else:
            self.node_order.insert(max(0, min(at, len(self.node_order))), node_id)
        self._changed()
        return node_id

    def remove(self, node_id: str) -> None:
        if node_id in self.nodes:
            del self.nodes[node_id]
            self.node_order = [n for n in self.node_order if n != node_id]
            self._changed()

    def move(self, node_id: str, delta: int) -> None:
        if node_id not in self.node_order or delta == 0:
            return
        i = self.node_order.index(node_id)
        j = max(0, min(len(self.node_order) - 1, i + delta))
        if i != j:
            self.node_order.insert(j, self.node_order.pop(i))
            self._changed()

    def set_enabled(self, node_id: str, enabled: bool) -> None:
        node = self.nodes.get(node_id)
        if node is not None and node.enabled != bool(enabled):
            node.enabled = bool(enabled)
            self._changed()

    def set_param(self, node_id: str, name: str, value: Any) -> None:
        """設定單一參數；不合法 → raise ParamError（UI 顯示訊息、值不落地）。"""
        node = self.nodes[node_id]
        step_cls = get_step(node.step)
        trial = dict(node.params)
        trial[name] = value
        clean = step_cls.validate_params(trial)   # 整組重驗（含相依預設）
        if clean != node.params:
            node.params = clean
            self._changed()

    # ---- score ------------------------------------------------------------
    def set_expr(self, expr: str) -> None:
        if expr != self.expr:
            self.expr = expr
            self._changed()

    def set_threshold(self, thr: float) -> None:
        thr = float(thr)
        if thr != self.threshold:
            self.threshold = thr
            self._changed()

    # ---- 查詢（給 UI 下拉）--------------------------------------------------
    def category_of(self, node_id: str) -> str:
        return get_step(self.nodes[node_id].step).category

    def available_features(self, upto_node: Optional[str] = None) -> List[str]:
        """route（到 upto_node 為止，含）會產出的特徵名，供表達式下拉。"""
        feats: List[str] = []
        for nid in self.node_order:
            node = self.nodes[nid]
            if not node.enabled:
                continue
            step_cls = get_step(node.step)
            for f in step_cls.resolve_features(node.params):
                if f not in feats:
                    feats.append(f)
            if nid == upto_node:
                break
        return feats

    def available_streams(self, before_node: Optional[str] = None) -> List[str]:
        """到 before_node（不含）為止累積的影像流名，供 image_key 參數下拉。"""
        streams: List[str] = []
        first = True
        for nid in self.node_order:
            if nid == before_node:
                break
            node = self.nodes[nid]
            if not node.enabled:
                continue
            step_cls = get_step(node.step)
            if first:
                ws = step_cls.resolve_writes_for_kind(node.params, self.kind)
                first = False
            else:
                ws = step_cls.resolve_writes(node.params)
            for w in ws:
                if w not in streams:
                    streams.append(w)
        return streams

    # ---- 連線（F7-6）------------------------------------------------------
    def _topological_order(self, edges: List[Tuple[str, str]]) -> Optional[List[str]]:
        """依 edges 的拓撲排序；有循環回 ``None``。

        同層之間**維持目前 ``node_order`` 的相對順序** —— 使用者拉一條線不該
        讓畫面上其他節點無關地跳動。
        """
        rank = {nid: i for i, nid in enumerate(self.node_order)}
        indeg = {nid: 0 for nid in self.nodes}
        succ: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for a, b in edges:
            if a in indeg and b in indeg:
                succ[a].append(b)
                indeg[b] += 1
        ready = sorted([n for n, d in indeg.items() if d == 0],
                       key=lambda n: rank.get(n, 1 << 30))
        out: List[str] = []
        while ready:
            n = ready.pop(0)
            out.append(n)
            for m in succ[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    ready.append(m)
            ready.sort(key=lambda x: rank.get(x, 1 << 30))
        return out if len(out) == len(self.nodes) else None

    def has_edge(self, src: str, dst: str) -> bool:
        """這兩個節點之間已經有線了嗎。

        給 UI 分辨「拉不起來（會成環）」與「本來就連著了」用 —— 對使用者來說
        那是兩件完全不同的事，混成同一句話會讓成功的操作看起來像失敗。
        """
        return (str(src), str(dst)) in self.edges

    def add_edge(self, src: str, dst: str) -> bool:
        """連一條線。會造成循環（或自迴圈／重複）就**不做事並回 False**。"""
        src, dst = str(src), str(dst)
        if src == dst or src not in self.nodes or dst not in self.nodes:
            return False
        if (src, dst) in self.edges:
            return False
        order = self._topological_order(self.edges + [(src, dst)])
        if order is None:
            return False                     # 循環 —— 擋在這裡，不讓它進 model
        self.edges.append((src, dst))
        self.node_order = order
        self._changed()
        return True

    def remove_edge(self, src: str, dst: str) -> bool:
        pair = (str(src), str(dst))
        if pair not in self.edges:
            return False
        self.edges.remove(pair)
        order = self._topological_order(self.edges)
        if order is not None:
            self.node_order = order
        self._changed()
        return True

    def edges_of(self, node_id: str) -> List[Tuple[str, str]]:
        nid = str(node_id)
        return [e for e in self.edges if nid in e]

    # ---- Recipe 互轉 -------------------------------------------------------
    def to_recipe(self) -> Recipe:
        return Recipe(
            recipe_id=self.recipe_id,
            routes={self.kind: list(self.node_order)},
            edges=[list(e) for e in self.edges],
            nodes={nid: RecipeNode(id=nid, step=n.step, params=dict(n.params),
                                   enabled=n.enabled)
                   for nid, n in self.nodes.items()},
            score=ScoreSpec(expr=self.expr, threshold=self.threshold,
                            bins=dict(self.bins)),
            version=self.version, author=self.author, description=self.description,
        )

    @classmethod
    def from_recipe(cls, recipe: Recipe, kind: Optional[str] = None) -> "RecipeModel":
        k = kind or (sorted(recipe.routes)[0] if recipe.routes else "ebi_patch")
        m = cls(kind=k)
        m.recipe_id = recipe.recipe_id
        m.author = recipe.author
        m.description = recipe.description
        m.version = recipe.version
        m.node_order = list(recipe.routes.get(k, []))
        in_route = set(m.node_order)
        m.edges = [(str(a), str(b)) for a, b in (recipe.edges or [])
                   if str(a) in in_route and str(b) in in_route]
        m.nodes = {nid: RecipeNode(id=nid, step=n.step, params=dict(n.params),
                                   enabled=n.enabled)
                   for nid, n in recipe.nodes.items() if nid in set(m.node_order)}
        m.expr = recipe.score.expr
        m.threshold = float(recipe.score.threshold)
        m.bins = dict(recipe.score.bins)
        m.dirty = False
        return m

    def validate(self):
        return validate(self.to_recipe(), kind=self.kind)


# ---------------------------------------------------------------------------
# 直方圖 / 門檻工具（純計算；HistogramWidget 與「拖門檻秒回」用）
# ---------------------------------------------------------------------------

def histogram(scores: Sequence[float], n_bins: int = 24,
              ) -> Tuple[List[float], List[int]]:
    """回傳 (bin 邊界 n_bins+1 個, 各 bin 計數)。空輸入 → ([0,1], [0])。"""
    vals = [float(s) for s in scores
            if s is not None and not (math.isnan(s) or math.isinf(s))]
    if not vals:
        return [0.0, 1.0], [0]
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        hi = lo + 1.0
    width = (hi - lo) / n_bins
    edges = [lo + i * width for i in range(n_bins + 1)]
    counts = [0] * n_bins
    for v in vals:
        i = min(int((v - lo) / width), n_bins - 1)
        counts[i] += 1
    return edges, counts


def rebin(scores: Sequence[Optional[float]], threshold: float,
          bins: Optional[Dict[str, int]] = None) -> Dict[int, int]:
    """依門檻重算 bin 計數（拖門檻線時即時呼叫；不觸碰影像）。"""
    bins = bins or {"below": 0, "above": 1}
    out: Dict[int, int] = {}
    for s in scores:
        if s is None or (isinstance(s, float) and (math.isnan(s) or math.isinf(s))):
            continue
        b = bins["below"] if float(s) < threshold else bins["above"]
        out[b] = out.get(b, 0) + 1
    return out
