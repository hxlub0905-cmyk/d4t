# ADEPT Studio view-model — authored 2026-07-28 (M3). Qt-free（可 headless 測試）.
"""Studio 的編輯狀態模型：UI 元件只做顯示與轉發，所有 recipe 編輯邏輯集中在這裡。

- ``RecipeModel``：包住一條 route 的可變編輯模型（v1 Studio 一次編一條 route）。
  add/remove/move/set_param 全部走 ParamSpec 驗證；`to_recipe()` 產出可存檔/可跑的
  Recipe。任何變更會呼叫 listeners（UI 拿來刷新）。
- 直方圖/門檻工具函數：`histogram()`、`rebin()` —— 拖門檻線秒回的純計算部分。
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from adept.core.pipeline import (
    Edge, ParamError, Recipe, RecipeNode, ScoreSpec, get_step, validate,
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
        #: 畫布上的線。F9-5b 起存的是 core 的 :class:`~adept.core.pipeline.Edge`
        #: （帶埠），不再是一對節點 —— 埠決定**資料從哪來**，而不只是先後順序。
        self.edges: List[Edge] = []
        self.expr = "0"
        self.threshold = 0.0
        self.bins = {"below": 0, "above": 1}
        self.dirty = False
        self._listeners: List[Callable[[], None]] = []
        #: 復原堆疊（F7-16）。整個編輯狀態的快照，不是「反向操作」——
        #: recipe 小（幾十個節點、純 JSON 值），存整份既簡單又不會漏掉
        #: 副作用（``add_edge`` 會重排 ``node_order``、``set_param`` 會連帶
        #: 補上相依預設值），而反向操作要為每一種變動各寫一次「怎麼倒回去」，
        #: 每加一個新動作就多一個會忘記的地方。
        self._undo: List[Dict[str, Any]] = []
        self._redo: List[Dict[str, Any]] = []
        #: 「同一個參數連續調整算一次」的鍵（滑桿拖一下會發幾十次 set_param）。
        self._coalesce: Optional[str] = None
        #: 「這一整段算一步復原」用的深度計數（見 :meth:`compound`）。
        self._compound_depth = 0
        self._compound_pushed = False

    #: 復原最多記幾步。這是記憶體的保險，不是體驗上的取捨 ——
    #: 沒有人會連按 60 次 Ctrl+Z，但一個沒有上限的堆疊在長 session 裡會一直長。
    UNDO_DEPTH = 60

    #: 新 recipe 的起手卡。每一條 pipeline 都得先有影像才有得做，所以空白畫布
    #: 上第一件事一定是「加 Input」—— 那不是一個選擇，是一個儀式。
    #: 試用回饋（F7-9）原話：「一開始預設畫布上就應該有 load image 這個節點」。
    STARTER_STEP = "load_patch"

    @classmethod
    def starter(cls, kind: str = "ebi_patch") -> "RecipeModel":
        """開新檔用的模型：畫布上已經放好 Input 卡，而且不算「改過」。

        ``dirty`` 特意還原成 ``False`` —— 使用者什麼都還沒做，關窗時不該被問
        「要存檔嗎」。
        """
        m = cls(kind=kind)
        try:
            m.add_step(cls.STARTER_STEP)
        except KeyError:                 # pragma: no cover — 卡片庫壞了才會發生
            pass
        m.dirty = False
        m.clear_history()      # 起手卡不是「使用者做過的一步」，Ctrl+Z 不該退掉它
        return m

    # ---- listener ---------------------------------------------------------
    def add_listener(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _changed(self) -> None:
        self.dirty = True
        for fn in list(self._listeners):
            fn()

    # ---- 復原 / 重做（F7-16）-----------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """整個編輯狀態的深拷貝（純 Python 值，可以直接比較）。"""
        return {
            "kind": self.kind, "recipe_id": self.recipe_id,
            "author": self.author, "description": self.description,
            "version": self.version,
            "node_order": list(self.node_order),
            "nodes": {nid: (n.step, dict(n.params), bool(n.enabled))
                      for nid, n in self.nodes.items()},
            "edges": [Edge(e.src, e.dst, e.src_out, e.dst_in)
                      for e in self.edges],
            "expr": self.expr, "threshold": self.threshold,
            "bins": dict(self.bins),
        }

    def restore(self, snap: Dict[str, Any]) -> None:
        """把狀態換成某一份快照（不發 listener，呼叫端負責）。"""
        self.kind = snap["kind"]
        self.recipe_id = snap["recipe_id"]
        self.author = snap["author"]
        self.description = snap["description"]
        self.version = snap["version"]
        self.node_order = list(snap["node_order"])
        self.nodes = {nid: RecipeNode(id=nid, step=step, params=dict(params),
                                      enabled=enabled)
                      for nid, (step, params, enabled) in snap["nodes"].items()}
        self.edges = list(snap["edges"])
        self.expr = snap["expr"]
        self.threshold = snap["threshold"]
        self.bins = dict(snap["bins"])

    @contextmanager
    def compound(self, name: str = "compound"):
        """把這個區塊裡的所有改動合併成**一步**復原（F7-22）。

        「加一張卡」在 model 上其實是好幾個動作：``add_step`` → ``set_param``
        （指到那條影像流）→ ``add_edge``。各記一步的話，使用者加了一張卡、
        按一次 Ctrl+Z，看到的是**卡還在但線不見了**這種中間狀態 ——
        那比不能復原更糟，因為畫面上出現了他從來沒有做出來過的東西。

        ``coalesce`` 解不了這件事：它比對的是「改的是不是同一個東西」，
        而這裡本來就是三個不同的東西。
        """
        if self._compound_depth == 0:
            self._compound_pushed = False
        self._compound_depth += 1
        try:
            yield
        finally:
            self._compound_depth -= 1
            if self._compound_depth == 0:
                self._coalesce = None

    def _push_undo(self, coalesce: Optional[str] = None) -> None:
        """在改動**之前**記一步。

        ``coalesce`` 是「這次改的是哪一個東西」。同一個東西連續改（拖滑桿、
        在輸入框裡打字）只記第一次 —— 不然按一次 Ctrl+Z 只會退回一個畫素，
        使用者得按四十次才回得到動之前的樣子，那等於沒有復原。
        """
        if self._compound_depth > 0:
            # 一整段只記最前面那一次（見 :meth:`compound`）。
            if self._compound_pushed:
                return
            self._compound_pushed = True
        elif coalesce is not None and coalesce == self._coalesce and self._undo:
            return
        self._coalesce = coalesce
        self._undo.append(self.snapshot())
        if len(self._undo) > self.UNDO_DEPTH:
            self._undo.pop(0)
        self._redo.clear()

    def end_coalescing(self) -> None:
        """「這一段連續調整結束了」（換節點、換參數、存檔時呼叫）。"""
        self._coalesce = None

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self.restore(self._undo.pop())
        self.end_coalescing()
        self._changed()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self.restore(self._redo.pop())
        self.end_coalescing()
        self._changed()
        return True

    def clear_history(self) -> None:
        """開新檔／載入檔案之後：在那之前的事情不屬於這一份 recipe。"""
        self._undo.clear()
        self._redo.clear()
        self.end_coalescing()

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
        self._push_undo()
        node_id = self._new_id(step_key)
        # **剛加進來的卡前後都是空的**（F10，使用者定調 2026-08-17）：
        # 全預設之後把每一格輸入清掉。畫布上沒有線，這張卡就沒有來源 ——
        # 而在這之前，一張新卡帶著 ``source="diff"`` 這種預設值進來，畫布照著
        # 畫出一個 `diff` 輸入埠、引擎照著去全域名字表拿圖，於是「還沒接線」
        # 跟「接好了」跑出來的數字**一模一樣**（實測逐項相同）。
        #
        # 清的是**這一張卡的值**，不是卡片的 ``default`` —— 後者是規格的預設
        # 值，手寫 recipe 省略那一格時仍然要有東西可用。
        params = step_cls.validate_params(step_cls.cleared_inputs())
        self.nodes[node_id] = RecipeNode(id=node_id, step=step_key, params=params)
        if at is None:
            self.node_order.append(node_id)
        else:
            self.node_order.insert(max(0, min(at, len(self.node_order))), node_id)
        self._changed()
        return node_id

    def remove(self, node_id: str) -> None:
        """拿掉一張卡 —— **連同碰到它的每一條線**（F10-5）。

        以前只刪節點，線留在 ``edges`` 裡指著一個不存在的節點。平常看不出來
        （畫布只畫兩端都還在的線、``execution_order`` 也會過濾掉），直到
        **新卡拿到同一個自動編號**：``_new_id`` 看到 ``roi_cross`` 沒人用就
        再發一次，那條殘留的線於是接到了一張使用者從來沒有接過的新卡。

        使用者回報的原話：「刪掉 Profile 這整個 Card 後，再 add new card
        profile，DAG 畫布上線還會殘留。」而且那條線是**假的** —— 新卡的來源
        參數是空的，畫布與設定當場互相矛盾。

        改名為「殘留」不足以形容：那條線會被存進 recipe、會進快取簽章、也會
        被引擎當成明講的來源。所以它必須在刪卡的同一步就消失。
        """
        if node_id in self.nodes:
            self._push_undo()
            del self.nodes[node_id]
            self.node_order = [n for n in self.node_order if n != node_id]
            self.edges = [e for e in self.edges
                          if e.src != node_id and e.dst != node_id]
            order = self._topological_order(self.edges)
            if order is not None:
                self.node_order = order
            self._changed()

    def move(self, node_id: str, delta: int) -> None:
        if node_id not in self.node_order or delta == 0:
            return
        i = self.node_order.index(node_id)
        j = max(0, min(len(self.node_order) - 1, i + delta))
        if i != j:
            self._push_undo()
            self.node_order.insert(j, self.node_order.pop(i))
            self._changed()

    def set_enabled(self, node_id: str, enabled: bool) -> None:
        node = self.nodes.get(node_id)
        if node is not None and node.enabled != bool(enabled):
            self._push_undo()
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
            self._push_undo("param:%s:%s" % (node_id, name))
            node.params = clean
            self._changed()

    # ---- score ------------------------------------------------------------
    def set_expr(self, expr: str) -> None:
        if expr != self.expr:
            self._push_undo("expr")
            self.expr = expr
            self._changed()

    def set_threshold(self, thr: float) -> None:
        thr = float(thr)
        if thr != self.threshold:
            self._push_undo("threshold")
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
        for a, b in ((e.src, e.dst) for e in edges):
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
        return any(e.src == str(src) and e.dst == str(dst) for e in self.edges)

    def has_line(self, src: str, dst: str, src_out: str = "",
                 dst_in: str = "") -> bool:
        """**這一條**線（含兩端的埠）已經在了嗎。

        跟 :meth:`has_edge` 的差別就是 F9-9 那件事：兩張卡之間可以有好幾條線，
        所以「已經連著了」要問到埠，不能只問到節點。
        """
        src, dst = str(src), str(dst)
        return any(e.src == src and e.dst == dst
                   and e.src_out == str(src_out or "")
                   and e.dst_in == str(dst_in or "") for e in self.edges)

    def add_edge(self, src: str, dst: str, src_out: str = "",
                 dst_in: str = "") -> bool:
        """連一條線。會造成循環（或自迴圈／整條一模一樣）就**不做事並回 False**。

        ``src_out`` / ``dst_in`` 是埠（F9-5b）：從哪顆輸出埠拉的、落在下游卡的
        哪個參數。填了的話引擎就照這條線送資料（而不是照「執行順序上最後一個
        寫這條流的人」推）—— 那是分支成立的條件。

        **一對節點之間可以有好幾條線**（F9-9，使用者定調：「餵圖是節點跟節點間
        在處理的，卡片只負責把餵進來的 source 處理完丟出去，所以可以多連一、
        也可以一連多」）。以前這裡看到同一對節點就回 False，於是從 Load 先拉
        ``test`` 再拉 ``ref`` 時第二條只能去**覆寫**第一條的埠 —— 參數上兩條流
        都在，但只有一條線帶得出它從哪來，另一條退回「執行順序上最後一個寫它
        的人」猜。線性時猜的跟真的一樣，分支時猜錯。

        所以「重複」的判準是**整條線**（兩個節點 + 兩個埠），不是兩個節點。
        """
        src, dst = str(src), str(dst)
        if src == dst or src not in self.nodes or dst not in self.nodes:
            return False
        if self.has_line(src, dst, src_out, dst_in):
            return False
        new = Edge(src=src, dst=dst, src_out=str(src_out or ""),
                   dst_in=str(dst_in or ""))
        order = self._topological_order(self.edges + [new])
        if order is None:
            return False                     # 循環 —— 擋在這裡，不讓它進 model
        self._push_undo()
        self.edges.append(new)
        self.node_order = order
        self._changed()
        return True

    def set_edge_ports(self, src: str, dst: str, src_out: str = "",
                       dst_in: str = "") -> bool:
        """補上一條**還沒有埠**的線的埠。

        分成兩步是因為 Studio 的順序是「先確定線接得起來（不成環），**再**去改
        下游卡的參數」—— 而 ``dst_in`` 是那一步才知道的（要看那張卡的哪個參數
        吃影像流）。線沒接起來就不該留下任何痕跡。

        F9-9 起優先挑**埠是空的**那一條：一對節點之間可以有好幾條線，補埠只該
        補到剛加的那條沒有埠的上面，不可以去改已經有埠的鄰居。
        """
        src, dst = str(src), str(dst)
        idx = [i for i, e in enumerate(self.edges)
               if e.src == src and e.dst == dst]
        if not idx:
            return False
        blank = [i for i in idx if not self.edges[i].src_out
                 and not self.edges[i].dst_in]
        i = blank[0] if blank else idx[0]
        e = self.edges[i]
        self.edges[i] = Edge(src=src, dst=dst,
                             src_out=str(src_out or e.src_out),
                             dst_in=str(dst_in or e.dst_in))
        return True

    def remove_edge(self, src: str, dst: str,
                    src_out: Optional[str] = None,
                    dst_in: Optional[str] = None) -> bool:
        """拿掉線。``src_out=None`` = 這兩張卡之間**全部**；給了就只拿那一條。

        剪刀（線上的 ×）給的是 ``src_out``（F9-9）—— 兩張卡之間可能有兩條並排
        的線，剪掉「使用者瞄的那一條」跟剪掉「兩條」是完全不同的事。
        """
        src, dst = str(src), str(dst)

        def hit(e: Edge) -> bool:
            return (e.src == src and e.dst == dst
                    and (src_out is None or e.src_out == str(src_out))
                    and (dst_in is None or e.dst_in == str(dst_in)))

        keep = [e for e in self.edges if not hit(e)]
        if len(keep) == len(self.edges):
            return False
        self._push_undo()
        self.edges = keep
        order = self._topological_order(self.edges)
        if order is not None:
            self.node_order = order
        self._changed()
        return True

    def edges_of(self, node_id: str) -> List[Edge]:
        nid = str(node_id)
        return [e for e in self.edges if nid in (e.src, e.dst)]

    def edge_pairs(self) -> List[Tuple[str, str]]:
        """哪兩張卡之間有線（**去重**：一對節點之間可能有好幾條）。"""
        out: List[Tuple[str, str]] = []
        for e in self.edges:
            if (e.src, e.dst) not in out:
                out.append((e.src, e.dst))
        return out

    def edge_lines(self) -> List[Tuple[str, str, str, str]]:
        """畫布要畫的每一條線：``(來源, 目的, 從哪顆輸出埠, 進哪個輸入參數)``。

        埠沒填的線回空字串 —— 畫布看到空字串就退回舊的推導（兩端共用哪幾條流
        就畫幾條），既有 recipe 的畫面因此一個畫素都沒變。

        第四欄是 F10 加的：兩條線接進同一張卡的**不同**輸入（``subtract`` 的
        a 與 b）時，畫布要知道各自進哪一顆埠，否則兩條線疊在同一個點上 ——
        而那正是使用者要在畫布上讀到的東西。
        """
        return [(e.src, e.dst, e.src_out, e.dst_in) for e in self.edges]

    # ---- Recipe 互轉 -------------------------------------------------------
    def to_recipe(self) -> Recipe:
        return Recipe(
            recipe_id=self.recipe_id,
            routes={self.kind: list(self.node_order)},
            edges=list(self.edges),
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
        # F9-1：core 的邊帶埠了（``Edge``），UI 這一層還是「一對節點」——
        # 埠要到 F9-5 才由畫布產生。轉換只在這個邊界做，UI 內部不必知道。
        m.edges = [e for e in (recipe.edges or [])
                   if e.src in in_route and e.dst in in_route]
        m.nodes = {nid: RecipeNode(id=nid, step=n.step, params=dict(n.params),
                                   enabled=n.enabled)
                   for nid, n in recipe.nodes.items() if nid in set(m.node_order)}
        m.expr = recipe.score.expr
        m.threshold = float(recipe.score.threshold)
        m.bins = dict(recipe.score.bins)
        m.dirty = False
        m.clear_history()
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


def accuracy_at(results: Sequence[Dict[str, Any]], threshold: float,
                bins: Optional[Dict[str, int]] = None,
                ground_truth: Optional[Dict[Any, Any]] = None
                ) -> Optional[Dict[str, Any]]:
    """這個門檻下的正確率／抓漏率／誤殺率；沒有 ground truth 回 ``None``。

    為什麼要有這個函式（Phase 1）
    ----------------------------
    調參迴圈裡使用者拖著門檻線看直方圖，但直方圖只講得出「分佈」——
    **講不出「這樣調是變好還變壞」**。而「分類準確度」正是這個工具的 KPI。
    沒有它，「engine 用好了」是一個不可驗證的命題：改完一張卡只知道測試沒紅，
    不知道判得更準還是更差。

    重算走 :func:`~adept.core.export.summarize`（跟 CLI／Excel 報表同一份邏輯，
    不另外寫一份會漂移的），只是先把 bin 按新門檻換掉 —— **不重跑任何影像**，
    所以拖門檻線是即時的。
    """
    if not ground_truth or not results:
        return None
    from adept.core.export import summarize

    bins = bins or {"below": 0, "above": 1}
    rebinned = []
    for r in results:
        s_ = r.get("score")
        if s_ is None or (isinstance(s_, float)
                          and (math.isnan(s_) or math.isinf(s_))):
            b = None
        else:
            b = bins["below"] if float(s_) < threshold else bins["above"]
        rebinned.append({"defect_id": r.get("defect_id"), "ok": r.get("ok", True),
                         "bin": b, "score": s_})
    return summarize(rebinned, ground_truth=ground_truth).get("ground_truth")


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
