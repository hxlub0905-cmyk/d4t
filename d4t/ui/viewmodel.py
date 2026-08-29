# d4t Studio view-model — authored 2026-07-28 (M3). Qt-free（可 headless 測試）.
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

from dataclasses import replace

from d4t.core.pipeline.expression import parse_expression
from d4t.core.pipeline import (
    Edge, ParamError, Recipe, RecipeNode, RouteBy, ScoreSpec, get_step,
    validate,
)
from d4t.core.pipeline.recipe import (RECIPE_VERSION, DecideSpec, Let, Rule,
                                      TreeLeaf, TreeStep, _tree_from_json,
                                      _tree_to_json, feature_referrers,
                                      region_edge_values, rules_to_tree)
from d4t.core.steps._util import centre_name, others_name
from d4t.core.steps.glv_stats import EACH_BOX, POOLED, REF_NONE, REF_REGION

#: GLV 卡最上面那三顆「我要量什麼」（PR-2 2a）。**preset 不是參數**：recipe
#: 沒有新欄位，選了只動 roi / reference_region 兩條線與 reference /
#: across_boxes 兩格 —— 存出來的 JSON 跟手拉線、手填格的逐位元組相同。
#: （id, 顯示字, 一句話）；字在這裡一份，ParamForm 只負責畫。
GLV_INTENTS: Tuple[Tuple[str, str, str], ...] = (
    ("defect_box", "The defect's box",
     "Measure the centred box, judged against the other boxes."),
    ("oddest_box", "The most unusual box",
     "Measure every box and report the odd one out."),
    ("region_stats", "The whole region",
     "Pool every box into one pile of pixels."),
)

#: 比對不上任何 preset 時顯示的狀態 id。
GLV_INTENT_CUSTOM = "custom"

#: bin 編號的上限。**它的用途是「別讓數字框變成一格自由文字」，不是「分類碼
#: 應該多大」** —— 後者是廠決定的，不是我們。
#:
#: 以前四個數字框各自寫死 ``setRange(0, 999)``，而**引擎與 KLARF 寫回都沒有
#: 這個上限**（``CLASSNUMBER`` 就是一個整數欄）。廠內的分類碼四五位數很常見，
#: 於是「打 1200 進去變成 999」—— 安靜地改掉使用者填的分類碼，而寫回是不可逆的。
#: 跟導引式問題那一格數字框同一個形狀（A1，2026-08-24）：一個我們自己發明出來、
#: 而且擋得住真實用法的上限。
MAX_BIN = 999999


def _decide_snapshot(d: "DecideSpec") -> Dict[str, Any]:
    """判定段的純值快照（undo 堆用）—— 跟 `Recipe.to_json_dict` 同一個形狀。

    ⚠ **樹也要進來**（F24）。漏掉的話，一份判定樹 recipe 在 Studio 裡按一次
    undo，樹就安靜地消失 —— 而畫面上看起來只是「回到上一步」。
    """
    return {
        "let": [(x.name, x.expr, str(getattr(x, "scale", "") or ""),
                 str(getattr(x, "fill", "") or ""))
                for x in d.let],
        "rules": [(r.when, int(r.bin), r.label) for r in d.rules],
        "otherwise": (int(d.otherwise_bin), d.otherwise_label),
        "score": d.score,
        "tree": None if d.tree is None else _tree_to_json(d.tree),
    }


def _decide_restore(snap: Optional[Dict[str, Any]]) -> Optional["DecideSpec"]:
    if not snap:
        return None
    ob, ol = snap.get("otherwise") or (0, "")
    tree = snap.get("tree")
    return DecideSpec(
        let=[Let(*row) for row in snap.get("let") or []],
        rules=[Rule(w, int(b), l) for w, b, l in snap.get("rules") or []],
        otherwise_bin=int(ob), otherwise_label=str(ol),
        score=str(snap.get("score", "") or ""),
        tree=None if tree is None else _tree_from_json(tree))


def is_a_constant_expression(text: Any) -> bool:
    """這段文字對**每一顆 defect 都給同一個答案**嗎（空的也算）。

    存在的理由是一個 bug（U1，2026-08-24）
    -------------------------------------
    ``RecipeModel`` 全新時 ``expr = "0"`` —— 那是**二元門檻那條老路的佔位值**
    （`__init__` 與 :meth:`use_decide` ``(False)`` 都塞它）。而 :meth:`use_decide`
    以前只問「``expr`` 是不是空的」，於是那個佔位值被翻成一條規則：

        Rule(when="0 >= 0", bin=1)      ← 對每一顆都成立

    後果有三層，而使用者只看得到最後一層：起手問題是一個永遠成立的假條件
    （整批全走 yes、第二類永遠是空的）；它**解析不成單純的比較**，所以
    `TreePanel` 退回表達式框，**F25 一整輪做的導引式編輯器（挑數字 ▾ ／
    比什麼 ▾ ／多少 ＋ 滑桿）在最常見的那條路徑上根本不會出現**；而因為
    沒有顆流到 no 邊，下一步的滑桿也拿不到分布。

    判準是「**用不用得到至少一個量出來的數字**」而不是「是不是字串 ``"0"``」：
    ``"1"``、``"2*3"`` 一樣不是一條判定線。

    ⚠ **解析不出來的不算常數。** 那是使用者打到一半或打錯的東西，
    是他的工作成果 —— :meth:`use_decide` 的立場一直是「調了半天的那個門檻
    不該因為換一個檢視就沒了」，所以壞掉的表達式照樣翻成規則（跑起來會
    在判定那一步報錯，而那句話講得出是哪裡錯）。
    """
    body = str(text or "").strip()
    if not body:
        return True
    try:
        return not parse_expression(body).variables
    except Exception:          # noqa: BLE001 — 壞表達式是使用者的東西，留著
        return False


class RecipeModel:
    """單一 route 的 recipe 編輯模型（預設 kind="ebi_patch"）。"""

    def __init__(self, kind: str = "ebi_patch") -> None:
        self.kind = kind
        self.recipe_id = "untitled"
        self.author = ""
        self.description = ""
        #: 新建的 recipe 就是**這一版**寫的（F42 B3）。留在 1 的話，Studio 存出
        #: 去的每一份檔案都會宣稱自己是舊格式，於是下次打開再跑一次遷移。
        self.version = RECIPE_VERSION
        self.node_order: List[str] = []            # route 順序（= 拓撲順序）
        self.nodes: Dict[str, RecipeNode] = {}
        #: 顯式的節點連線（F7-6 畫布）。``node_order`` 仍然是執行順序，
        #: 但有 edges 時它由拓撲排序算出來，不再是「使用者加卡片的順序」。
        #: ``execution_order`` 的邊**只**來自 ``edges``（F17-①）；route 的排列
        #: 是 Kahn 的平手依據 —— 所以「把 route 寫成拓撲順序」仍然是對的，
        #: 而且沒有線的卡片照排列跑，畫面與執行一致。
        #: （這裡以前寫的是「引擎本來就是 route 相鄰對 ∪ edges」，F17-① 之後
        #: 那句話不成立了。）
        #: 畫布上的線。F9-5b 起存的是 core 的 :class:`~d4t.core.pipeline.Edge`
        #: （帶埠），不再是一對節點 —— 埠決定**資料從哪來**，而不只是先後順序。
        self.edges: List[Edge] = []
        self.expr = "0"
        self.threshold = 0.0
        #: 多類別判定（F22-UI）。``None`` = 這份 recipe 走 ``expr + threshold``
        #: 那條二元的老路。兩者**不能並存**（`validate` 的 `ambiguous-decision`），
        #: 所以切換是「換一種」而不是「多一種」—— 見 :meth:`use_decide`。
        self.decide: Optional[DecideSpec] = None
        #: 分流（F23 期2）。``None`` = 照舊用 kind 選路。編輯器在判定欄上方。
        self.route_by: Optional[RouteBy] = None
        #: **這個 model 一次只編一條 route**（F23 §6 第一期不動的那條），
        #: 其他 route 的排列／專屬節點／線原樣抱著 —— `to_recipe` 時合併回去。
        #: 少了這三份，載入一份分流 recipe 再試跑，**其他 route 會安靜地消失**
        #: （`to_recipe` 只寫得出正在編的那一條），而分流跑起來每一顆走不到的
        #: route 都是一句 unknown-route 的失敗。
        self._other_routes: Dict[str, List[str]] = {}
        self._other_nodes: Dict[str, RecipeNode] = {}
        self._other_edges: List[Edge] = []
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

    #: **一顆一張影像**的資料型別 → 起手卡要換成 `load_single`（F11 Input-4）。
    #: 一種 source 一張卡，所以「哪一張卡是起手卡」也跟著資料走 —— 給單張資料
    #: 放一張 `load_patch`，畫布上會冒出兩顆埠而資料只有一張圖。
    SINGLE_IMAGE_STARTERS = {"rsem": "load_single", "folder": "load_single"}

    @classmethod
    def starter_step_for(cls, kind: str) -> str:
        """這種資料的起手卡是哪一張。"""
        return cls.SINGLE_IMAGE_STARTERS.get(str(kind or ""), cls.STARTER_STEP)

    @classmethod
    def starter(cls, kind: str = "ebi_patch") -> "RecipeModel":
        """開新檔用的模型：**空白畫布**，而且不算「改過」。

        為什麼不預先放一張 Input 卡（F11 Enhance-4，使用者定調）
        -------------------------------------------------------
        F7-9 起開窗就有一張 `load_patch`。那時候只有一張載入卡，所以「先幫你放
        好」是純粹的好意；F11 Input-4 把它拆成兩張（`load_patch` 一顆好幾張 /
        `load_single` 一顆一張）之後，預先放一張就是**替使用者決定了他還沒決定
        的事** —— 而猜錯的那一半在畫布上看起來完全正常（兩顆埠 vs 一顆埠）。

        使用者原話：「Load image 卡片改成預設沒有（user 可以選擇要 Load images
        or Load one image），add 才會出現。」

        載入資料的時候 Studio 仍然會**照資料的型別**補上那一張（見
        `studio._adopt_source_for`）—— 那時候「哪一張」已經不是猜的，是資料說的。

        ``dirty`` 特意還原成 ``False`` —— 使用者什麼都還沒做，關窗時不該被問
        「要存檔嗎」。
        """
        m = cls(kind=kind)
        m.dirty = False
        m.clear_history()
        return m

    # ---- listener ---------------------------------------------------------
    def add_listener(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _changed(self) -> None:
        self.dirty = True
        if self.CHECK_REGION_INVARIANT:
            self._assert_regions_match_edges()
        for fn in list(self._listeners):
            fn()

    #: **測試期自我檢查**：每一次 :meth:`_changed` 都重新問一次「每一格區域參數
    #: 是不是正好等於線說的」（F42 B2）。`tests/conftest.py` 一律打開它。
    #:
    #: 為什麼要一條常開的斷言，而不是幾條測試：方案 B 的整個安全性建立在
    #: 「參數只有一個家」上，而**破壞它的方式是加一條新路徑**（一個忘了水合的
    #: 新入口），不是改壞既有的那五條。既有測試不會走那條新路徑，所以只有
    #: 「每一次改動都問一次」抓得到 —— 那正是這個 repo 記過六次的形狀。
    #:
    #: 正式執行時是關的：它會在每一次改動上再掃一次整份 recipe。
    CHECK_REGION_INVARIANT = False

    def _assert_regions_match_edges(self) -> None:
        """有線的那幾格，值 ≠ 線說的 → 當場 ``AssertionError``。

        **沒有線的那一格不問** —— 那個狀態是合法的，而且有兩種來歷，兩種都要
        留著：B3 之前的舊檔案（參數是唯一的儲存），以及打錯字的名字
        （`unknown-region` 那條 lint 守著的東西）。見 :meth:`_hydrate_regions`。

        真正危險的是**兩邊都有、而且說的不一樣**：畫布指著一張卡，引擎給的是
        另一張卡的框，而兩邊都跑得完。這一條問的正好只有那個。
        """
        for (nid, pname), expect in region_edge_values(
                self.nodes, self.edges).items():
            got = str(self.nodes[nid].params.get(pname, "") or "")
            assert got == expect, (
                "region parameter %r on %r is %r but the lines say %r — "
                "something changed a region parameter without going through "
                "RecipeModel._hydrate_regions()" % (pname, nid, got, expect))

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
            "decide": None if self.decide is None else _decide_snapshot(self.decide),
            "bins": dict(self.bins),
            # 分流（F23 期2）。**其他 route 也要進快照** —— 少了的話 undo 一步
            # 會把「載入時抱著的另一條 route」安靜地丟掉。
            "route_by": None if self.route_by is None else
                (self.route_by.column, dict(self.route_by.map),
                 self.route_by.default),
            "other_routes": {k: list(v)
                             for k, v in self._other_routes.items()},
            "other_nodes": {nid: (n.step, dict(n.params), bool(n.enabled))
                            for nid, n in self._other_nodes.items()},
            "other_edges": list(self._other_edges),
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
        self.decide = _decide_restore(snap.get("decide"))
        rb = snap.get("route_by")
        self.route_by = None if rb is None else RouteBy(
            column=str(rb[0]), map=dict(rb[1]), default=str(rb[2]))
        self._other_routes = {k: list(v)
                              for k, v in (snap.get("other_routes") or {}).items()}
        self._other_nodes = {
            nid: RecipeNode(id=nid, step=step, params=dict(params),
                            enabled=enabled)
            for nid, (step, params, enabled)
            in (snap.get("other_nodes") or {}).items()}
        self._other_edges = list(snap.get("other_edges") or [])
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
        # **不信任快照裡的區域參數**（F42 B2）。快照存的是兩份東西（線與參數），
        # 而它們講的是同一件事 —— 只要有一條路徑寫錯了一邊，復原就會把那個
        # 不一致原樣端回畫面上，而且從此活下去。線是唯一的儲存，所以復原之後
        # 重算一次；一致的時候這是 no-op。
        self._hydrate_regions()
        self.end_coalescing()
        self._changed()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self.restore(self._redo.pop())
        self._hydrate_regions()            # 同 :meth:`undo`
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
            gone = [(e.dst, e.dst_in) for e in self.edges
                    if e.src == node_id and e.dst_in]
            self.edges = [e for e in self.edges
                          if e.src != node_id and e.dst != node_id]
            order = self._topological_order(self.edges)
            if order is not None:
                self.node_order = order
            # 這張卡定義的區域，下游那幾格要跟著空出來（F42 B2）——
            # 線都拿掉了，水合自然做到。以前區域線是從參數推導的，所以
            # `studio._on_remove_requested` 非得自己再清一次不可。
            self._hydrate_regions(emptied=gone)
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

    def set_param(self, node_id: str, name: str, value: Any) -> List[str]:
        """設定單一參數；不合法 → raise ParamError（UI 顯示訊息、值不落地）。

        回一串「這次改動讓哪些下游指空了」的話（見 :meth:`rename_fallout`）。
        **呼叫端可以整串忽略** —— 絕大多數呼叫者就是這樣，而那是對的：那句話
        只有在使用者剛動過線的時候才值得講。
        """
        node = self.nodes[node_id]
        step_cls = get_step(node.step)
        before = dict(node.params)
        trial = dict(node.params)
        trial[name] = value
        clean = step_cls.validate_params(trial)   # 整組重驗（含相依預設）
        if clean == node.params:
            return []
        spec = next((sp for sp in step_cls.params if sp.name == name), None)
        old_name = str(node.params.get(name, "") or "")
        new_name = str(clean.get(name, "") or "")
        # ⚠ **不要**用 ``compound`` 包住這一段。``compound`` 會讓 ``_push_undo``
        # 走「一整段只推一次」那條路，於是繞過 ``coalesce`` —— 拖一次滑桿發的
        # 幾十次 set_param 會各記一步，按 Ctrl+Z 只退回一個畫素
        # （`test_one_ctrl_z_undoes_a_whole_slider_drag` 抓到的）。
        # 這裡本來就只推一次，改名連帶動到的東西都在那一次之後。
        self._push_undo("param:%s:%s" % (node_id, name))
        node.params = clean
        # **改輸出流的名字 = 沿著線把下游一起帶走**（F10-6）。
        #
        # `write result to` 改成 GGG 之後，下游那張卡的 `source` 還寫著 `diff`、
        # 線上的 `src_out` 也還是 `diff` —— 於是使用者只是幫一條流取個好記的
        # 名字，整條 pipeline 就斷了（lint 報 missing-image）。而他從畫布上看到
        # 的是「線還在」，因為線是照節點畫的。
        #
        # 名字是**顯示用的標籤**，線才是接線的事實（見 `Edge.dst_in` 的說明）。
        # 所以改名不該動到「誰接誰」，只該讓兩端的標籤跟著換。
        if spec is not None and spec.is_output() and old_name and new_name:
            self._rename_stream(node_id, old_name, new_name)
        fallout = self.rename_fallout(node_id, before, clean)
        self._changed()
        return fallout

    def rename_fallout(self, node_id: str, before: Dict[str, Any],
                       after: Dict[str, Any]) -> List[str]:
        """這一次改動讓這張卡**不再產出**哪些名字，而誰還指著它們（F37 A2）。

        為什麼需要它：量測卡的前綴是**條件式的**（`MultiSourceStep.stream_prefix`
        ／`region_prefix` 只在超過一個的時候才加）。所以在一張既有的卡上多接
        一條區域線，它寫的每一個名字都會改：

            glv_median  →  epi_glv_median  ＋  mg_glv_median

        而分數表達式、判定樹、Output 卡的 ``rank_by`` 裡指著舊名字的那幾個字
        **不會跟著改**。使用者只做了一個動作（拉一條線），下游三個地方同時
        失效 —— 而在這之前，畫面上沒有任何東西說得出那件事。

        條件式前綴本身**沒有被改掉**（那要遷移每一份既有 recipe 加重凍三份
        黃金值）。危險的不是它，是「改名是安靜的」—— 這一支只修那一件事。

        回的是一串可以直接顯示的句子。剪掉一條線走的是同一條路（名字從兩個
        變回一個），所以反過來也講得出來。
        """
        node = self.nodes.get(str(node_id))
        if node is None:
            return []
        try:
            step_cls = get_step(node.step)
            gone = [n for n in step_cls.resolve_features(before)
                    if n not in set(step_cls.resolve_features(after))]
        except Exception:                  # noqa: BLE001 — 顯示用，壞了就不講
            return []
        out: List[str] = []
        for name in gone:
            where = feature_referrers(
                name, self.nodes, score_expr=str(self.expr or ""),
                decide=self.decide, skip=str(node_id))
            if where:
                out.append("“%s” is no longer produced — %s still refer%s to it."
                           % (name, " and ".join(where),
                              "" if len(where) > 1 else "s"))
        return out

    def _rename_stream(self, node_id: str, old: str, new: str) -> None:
        """某張卡的輸出流改名 → 從它出發的線與下游的來源參數一起改。"""
        for i, e in enumerate(list(self.edges)):
            if e.src != str(node_id) or e.src_out != old:
                continue
            self.edges[i] = Edge(src=e.src, dst=e.dst, src_out=new,
                                 dst_in=e.dst_in)
            dst = self.nodes.get(e.dst)
            if dst is None or not e.dst_in:
                continue
            try:
                dst_spec = {sp.name: sp for sp in
                            get_step(dst.step).params}[e.dst_in]
            except KeyError:                   # pragma: no cover
                continue
            cur = str(dst.params.get(e.dst_in, "") or "")
            if dst_spec.type == "image_keys":
                keys = [new if k.strip() == old else k.strip()
                        for k in cur.split(",") if k.strip()]
                value = ",".join(keys)
            elif cur == old:
                value = new
            else:
                continue
            try:
                dst.params = get_step(dst.step).validate_params(
                    dict(dst.params, **{e.dst_in: value}))
            except ParamError:                 # pragma: no cover — 值就是流名
                continue

    # ---- score ------------------------------------------------------------
    # ---- 多類別判定（F22-UI）---------------------------------------------
    #
    # 為什麼 setter 這麼細（一條規則一支）而不是「整包換掉」：undo 是**逐步**
    # 的（`_push_undo` 每次改動存一份），整包換掉的話「改了第 3 條的門檻」跟
    # 「重排了規則」在 undo 堆上長得一模一樣。
    def use_decide(self, on: bool) -> None:
        """切成多類別／切回二元門檻。**兩者不能並存**（`ambiguous-decision`）。

        切成多類別時把現有的 `expr` + `threshold` **翻成兩條規則**，而不是丟掉
        —— 使用者調了半天的那個門檻是他的工作成果。切回去時反過來不還原：
        多類別的規則翻不回一個門檻（那是有損的），所以那一邊只留一句話。
        """
        if on == (self.decide is not None):
            return
        self._push_undo()
        if on:
            expr = str(self.expr or "").strip()
            # **常數不是門檻**（U1，2026-08-24）—— 見 `is_a_constant_expression`。
            # 這裡以前問的是「``expr`` 是不是空的」，而全新 recipe 的 ``expr``
            # 是佔位值 ``"0"``，於是每一份新 recipe 都從一條 ``0 >= 0`` 開始。
            real = expr and not is_a_constant_expression(expr)
            rules = []
            if real:
                rules.append(Rule(when="%s >= %g" % (expr, float(self.threshold)),
                                  bin=int(self.bins.get("above", 1)), label=""))
            self.decide = DecideSpec(
                let=[], rules=rules,
                otherwise_bin=int(self.bins.get("below", 0)), otherwise_label="",
                score=expr if real else "")
            self.expr = ""          # 並存是 error，所以這一格要清掉
        else:
            self.decide = None
            if not str(self.expr or "").strip():
                self.expr = "0"
        self._changed()

    def _edit_decide(self, **kw) -> None:
        if self.decide is None:
            return
        self._push_undo()
        self.decide = replace(self.decide, **kw)
        self._changed()

    def set_let(self, i: int, name: Optional[str] = None,
                expr: Optional[str] = None,
                scale: Optional[str] = None,
                fill: Optional[str] = None) -> None:
        if self.decide is None or not (0 <= i < len(self.decide.let)):
            return
        cur = self.decide.let[i]
        new = Let(name=cur.name if name is None else str(name),
                  expr=cur.expr if expr is None else str(expr),
                  scale=(str(getattr(cur, "scale", "") or "")
                         if scale is None else str(scale)),
                  fill=(str(getattr(cur, "fill", "") or "")
                        if fill is None else str(fill)))
        if new == cur:
            return
        rows = list(self.decide.let); rows[i] = new
        self._edit_decide(let=rows)

    def add_let(self) -> None:
        if self.decide is None:
            return
        self._edit_decide(let=list(self.decide.let) + [Let(name="", expr="")])

    def remove_let(self, i: int) -> None:
        if self.decide is None or not (0 <= i < len(self.decide.let)):
            return
        rows = list(self.decide.let); rows.pop(i)
        self._edit_decide(let=rows)

    def set_rule(self, i: int, when: Optional[str] = None,
                 bin: Optional[int] = None, label: Optional[str] = None) -> None:
        if self.decide is None or not (0 <= i < len(self.decide.rules)):
            return
        cur = self.decide.rules[i]
        new = Rule(when=cur.when if when is None else str(when),
                   bin=cur.bin if bin is None else int(bin),
                   label=cur.label if label is None else str(label))
        if new == cur:
            return
        rows = list(self.decide.rules); rows[i] = new
        self._edit_decide(rules=rows)

    def add_rule(self) -> None:
        if self.decide is None:
            return
        used = {r.bin for r in self.decide.rules} | {self.decide.otherwise_bin}
        nxt = next(b for b in range(1, 1000) if b not in used)
        self._edit_decide(rules=list(self.decide.rules) + [Rule("", nxt, "")])

    def remove_rule(self, i: int) -> None:
        if self.decide is None or not (0 <= i < len(self.decide.rules)):
            return
        rows = list(self.decide.rules); rows.pop(i)
        self._edit_decide(rules=rows)

    def move_rule(self, i: int, delta: int) -> None:
        """**換順序就是換優先權** —— 所以它是一個第一級的動作，不是排版。"""
        if self.decide is None:
            return
        rows = list(self.decide.rules)
        j = i + int(delta)
        if not (0 <= i < len(rows)) or not (0 <= j < len(rows)) or delta == 0:
            return
        rows[i], rows[j] = rows[j], rows[i]
        self._edit_decide(rules=rows)

    def set_otherwise(self, bin: Optional[int] = None,
                      label: Optional[str] = None) -> None:
        if self.decide is None:
            return
        kw = {}
        if bin is not None and int(bin) != self.decide.otherwise_bin:
            kw["otherwise_bin"] = int(bin)
        if label is not None and str(label) != self.decide.otherwise_label:
            kw["otherwise_label"] = str(label)
        if kw:
            self._edit_decide(**kw)

    def set_decide_score(self, expr: str) -> None:
        if self.decide is not None and str(expr) != self.decide.score:
            self._edit_decide(score=str(expr))

    # ---- 判定樹（F24 ③）---------------------------------------------------
    #
    # 樹上的一步用**路徑**指（``""`` = 根、``"y"`` / ``"n"`` 一路往下）——
    # 節點是 frozen dataclass，同一片葉子可以出現兩次，路徑才是唯一的身分。
    # 每一支 setter 都是「整棵換掉」（`_tree_replace` 沿路重建）：樹很小
    # （lint 在 16 層就警告），而 immutable 的節點沒有第二種寫法。
    def ensure_tree(self) -> None:
        """`rules` 模式 → 等價鏈狀樹（無損，F24 ① 的測試釘住了）。

        畫布上點一個菱形開始編輯的那一刻呼叫 —— 編輯動作只有樹的形狀，
        rules 清單表達不了「yes 接另一步」。轉了之後 serde 只寫 `tree`
        （`Recipe.to_json_dict`），舊寫法從此離開這份 recipe —— 那是使用者
        動手改樹的那一刻，不是打開檔案的那一刻（鐵則 9：讀檔不改檔）。
        """
        if self.decide is None or self.decide.tree is not None:
            return
        self._edit_decide(tree=rules_to_tree(self.decide), rules=[])

    def tree_node(self, path: str) -> Any:
        """路徑指到的節點（不存在回 ``None``）。"""
        if self.decide is None or self.decide.tree is None:
            return None
        node = self.decide.tree
        for ch in str(path):
            if isinstance(node, TreeLeaf):
                return None
            # **只認 y 與 n**（B4，2026-08-24）。以前是 ``ch == "y"`` 否則走
            # ``no`` —— 一個壞掉的路徑不會回 None，會安靜地指到一個**真實但
            # 錯的節點**，而編輯操作就會改到那裡。今天路徑全部由 UI 產生所以
            # 碰不到，但「壞輸入指到一個合法的東西」正是這個 repo 最怕的形狀。
            if ch not in ("y", "n"):
                return None
            node = node.yes if ch == "y" else node.no
        return node

    @staticmethod
    def _tree_replace(node: Any, path: str, new: Any) -> Any:
        """路徑指到的那個節點換成 ``new``，回傳新的樹。

        ⚠ 呼叫端（`_edit_tree`）一律先用 :meth:`tree_node` 確認路徑指得到
        東西才叫這一支 —— 所以這裡不必再擋一次，但也**不可以**把「不是 y」
        當成 n（見 :meth:`tree_node` 的說明）。
        """
        if not path:
            return new
        if path[0] == "y":
            return replace(node, yes=RecipeModel._tree_replace(
                node.yes, path[1:], new))
        return replace(node, no=RecipeModel._tree_replace(
            node.no, path[1:], new))

    def _edit_tree(self, path: str, new: Any) -> None:
        if self.decide is None or self.decide.tree is None:
            return
        self._edit_decide(tree=self._tree_replace(self.decide.tree,
                                                  str(path), new))

    def _fresh_bin(self) -> int:
        """一個還沒被任何葉子用掉的 bin（跟 `add_rule` 同一個規則）。

        用光了回 :data:`MAX_BIN` **而不是拋例外** —— 這一支以前是
        ``next(b for b in range(1, 1000) ...)``，找不到會漏出一個
        ``StopIteration``，而它會在一顆按鈕的 handler 裡冒出來。
        """
        used = {int(self.decide.otherwise_bin)} if self.decide else set()

        def walk(node: Any) -> None:
            if isinstance(node, TreeLeaf):
                used.add(int(node.bin))
                return
            walk(node.yes)
            walk(node.no)

        if self.decide is not None and self.decide.tree is not None:
            walk(self.decide.tree)
        if self.decide is not None:
            used |= {int(r.bin) for r in self.decide.rules}
        return next((b for b in range(1, MAX_BIN + 1) if b not in used),
                    MAX_BIN)

    def set_tree_when(self, path: str, when: str) -> None:
        node = self.tree_node(path)
        if not isinstance(node, TreeStep) or str(when) == node.when:
            return
        self._edit_tree(path, replace(node, when=str(when)))

    def set_tree_leaf(self, path: str, bin: Optional[int] = None,
                      label: Optional[str] = None) -> None:
        node = self.tree_node(path)
        if not isinstance(node, TreeLeaf):
            return
        new = TreeLeaf(bin=node.bin if bin is None else int(bin),
                       label=node.label if label is None else str(label))
        if new != node:
            self._edit_tree(path, new)

    def split_tree_leaf(self, path: str) -> None:
        """把一片葉子換成一個新菱形（mockup：「加一步」）。

        原本那一類**留著**（掛在新步驟的 no 邊）—— 跟「在 otherwise 前面
        加一條規則」同一個形狀：新問題答 yes 的走新的類，其他照舊。
        """
        node = self.tree_node(path)
        if not isinstance(node, TreeLeaf):
            return
        self._edit_tree(path, TreeStep(
            when="", yes=TreeLeaf(bin=self._fresh_bin(), label=""), no=node))

    def insert_tree_step_above(self, path: str) -> None:
        """在這一步**前面**插一個新問題（原本的子樹整個掛在 no 邊）。"""
        node = self.tree_node(path)
        if node is None:
            return
        self._edit_tree(path, TreeStep(
            when="", yes=TreeLeaf(bin=self._fresh_bin(), label=""), no=node))

    def remove_tree_step(self, path: str) -> None:
        """拿掉一步：它的 **no 邊接回上游**（F24 §6 定的規則）。

        yes 那一邊跟著消失 —— 呼叫端（面板）在 yes 是一整個子樹時要先問過
        使用者；model 不擋，因為「問」是 UI 的事，而 undo 一步就回得來。
        """
        node = self.tree_node(path)
        if not isinstance(node, TreeStep):
            return
        self._edit_tree(path, node.no)

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
        """route（到 upto_node 為止，含）會產出的特徵名，供表達式下拉。

        **沒有人填 nm/px 就不列 nm 的那一份**（2026-08-20）。量測卡一律宣告
        `cd_x_nm` 那一組（它看不到 Load 卡上填了什麼），但下拉是使用者**會去
        點**的東西 —— 點了一個永遠不會出現的名字，recipe 就會在跑起來的時候
        每一顆都失敗。這裡看得到每一張卡，所以這句話在這裡回答。
        """
        feats: List[str] = []
        known = self.nm_per_px_is_known()
        for _nid, _cls, s in self._declared_specs(upto_node):
            # PR-3 起 nm 的孿生看**宣告的身分**（``variant``），不再拆字尾
            # —— 使用者自己取的 ``output_prefix`` 以 ``_nm`` 結尾時，
            # 字尾判斷會把真的量砍掉。
            if not known and s.variant in ("nm", "nm2"):
                continue
            if s.name not in feats:
                feats.append(s.name)
        return feats

    def _declared_specs(self, upto_node: Optional[str] = None,
                        include_upto: bool = True):
        """route 上啟用卡片宣告的 spec（`resolve_feature_specs`），執行序逐個。

        三份清單（`available_features` / `labelled_features` /
        `feature_owners`）共用**這一個**迴圈 —— 「哪些名字、歸誰」的答案
        只能有一份，以前是三段手抄。
        """
        for nid in self.node_order:
            node = self.nodes[nid]
            if not node.enabled:
                continue
            if nid == upto_node and not include_upto:
                # **這張卡自己的輸出不能列進來**（F21-B，實跑截圖抓到）：
                # `Feature math` 的清單裡出現 `defect_score`，而那正是它自己
                # 要寫出去的名字 —— 點下去就是 `defect_score = defect_score`。
                # 引擎擋得住（`unknown-feature-input`），但**讓使用者點一個
                # 保證壞掉的選項，本身就是 bug**（推廣鐵則）。
                return
            step_cls = get_step(node.step)
            for s in step_cls.resolve_feature_specs(node.params):
                yield nid, step_cls, s
            if nid == upto_node:
                return


    #: 「數字 → 誰算的」清單裡，名字與來源之間的分隔（F21-B）。
    #: 一個字串裝兩件事是刻意的：``ParamForm`` 的執行期選單是
    #: ``Dict[str, List[str]]``，為了一個標籤去改那個型別，會動到每一個
    #: 用 ``choices_from`` 的地方。**拆開的規矩只有一份**（`split_labelled`）。
    FEATURE_LABEL_SEP = "\t"

    def labelled_features(self, upto_node: Optional[str] = None,
                          include_upto: bool = True) -> List[str]:
        """`available_features` 的每一項後面接上**誰算的**（F21-B）。

        格式是 ``"cd_median\tCD"`` —— 前半是要插進算式的字，後半只是給人看的。
        兩件事同一份來源（同一個迴圈），所以它們不會漂。

        ``include_upto=False`` 時**連 `upto_node` 自己的輸出都不列** ——
        給「這張卡的算式可以用哪些數字」用的（一張卡不能吃自己還沒寫的東西）。

        為什麼要有「誰算的」：一份 recipe 可以有兩張 `Gray level`（量兩個區域），
        那時候光看 `glv_mad` 這個名字選不出要哪一個。名字自帶前綴的只有**撞名
        被蓋掉**的那一份（F17-②）—— 沒撞名的時候仍然只有一個短名。
        """
        out: List[str] = []
        known = self.nm_per_px_is_known()
        for nid, step_cls, s in self._declared_specs(upto_node, include_upto):
            if not known and s.variant in ("nm", "nm2"):
                continue
            label = str(getattr(step_cls, "label", "") or
                        self.nodes[nid].step)
            if not any(x.split(self.FEATURE_LABEL_SEP, 1)[0] == s.name
                       for x in out):
                out.append(s.name + self.FEATURE_LABEL_SEP + label)
        return out

    def feature_owners(self) -> Dict[str, str]:
        """特徵名 → 產出它的**節點 id**（幽靈線／淡線用，F24 ④）。

        ⚠ **它是 `verdict_features.bound_specs` 的投影，不是第三份實作**
        （F51，2026-08-28）。

        以前這裡有自己的迴圈（`_declared_specs`，第一個宣告的人贏），而
        「誰產出這個特徵」因此有**三份**答案：引擎（真相）、`bound_specs`
        （結果表用）、這一支（淡線用）。實測那三份對不上：這一支知道 23 個
        名字、`bound_specs` 知道 34 個，差的 11 個是**救援名與引擎特徵**
        （`score`、`decide_unanswered`）。後果很具體 —— 整個工具最常見的那
        一條淡線「報表照 `score` 排序」**一條都畫不出來**，因為這張表裡沒有
        `score`。

        `bound_specs` 住在 core、比較完整，而且有一把對照引擎的尺
        （`tests/test_feature_names_match_the_engine.py`）。所以留它、
        刪這一支的迴圈。**判定段 `let` 與引擎特徵的 node id 仍然是空字串**
        （畫布上那張入口卡沒有 node id）—— 那個約定 `bound_specs` 本來就
        一模一樣，所以呼叫端一個字都不用改。
        """
        from d4t.core.pipeline.verdict_features import bound_specs

        try:
            recipe = self.to_recipe()
        except Exception:              # noqa: BLE001 — 顯示層，壞了就不畫線
            return {}
        return {b.spec.name: b.node_id
                for b in bound_specs(recipe, self.kind)}

    def nm_per_px_is_known(self) -> bool:
        """有沒有任何一張卡填了 nm/px（`_util.nm_per_px_spec`）。"""
        for node in self.nodes.values():
            if not node.enabled:
                continue
            try:
                if float(node.params.get("nm_per_px", 0) or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def available_streams(self, before_node: Optional[str] = None) -> List[str]:
        """到 before_node（不含）為止累積的影像流名，供 image_key 參數下拉。"""
        streams: List[str] = []
        for nid in self.node_order:
            if nid == before_node:
                break
            node = self.nodes[nid]
            if not node.enabled:
                continue
            step_cls = get_step(node.step)
            # kind-aware 是卡片自己的宣告，不是位置的事（F11 Input-0）——
            # 兩張入口卡的時候，第二張也要算得出它真的會產出哪幾條流。
            ws = step_cls.resolve_writes_for_kind(node.params, self.kind)
            for w in ws:
                if w not in streams:
                    streams.append(w)
        return streams

    def available_regions(self, before_node: Optional[str] = None) -> List[str]:
        """到 before_node（不含）為止定義了哪些具名區域，供下拉用（F11 Region-1）。

        跟 :meth:`available_streams` 是同一個形狀，因為問題是同一個：使用者要打
        的字必須跟上游卡片的輸出**一字不差**，而打錯的時候 lint 要跑一次才講。
        程式本來就知道上游定義了什麼 —— 那就不該讓他用打的（同 F9-6 的理由）。
        """
        regions: List[str] = []
        for nid in self.node_order:
            if nid == before_node:
                break
            node = self.nodes[nid]
            if not node.enabled:
                continue
            for r in get_step(node.step).resolve_regions_out(node.params):
                if r and r not in regions:
                    regions.append(r)
        return regions

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
        # 區域線也在這裡（F42 B2）——「用哪個區域」現在是線說的，參數跟著走。
        # ⚠ ``node_order`` 上面那一行已經重排過了：區域線進了 edges，所以它
        # **會影響排版**（以前不會，因為它根本不在 edges 裡）。那是對的 ——
        # 它一直都是一條真的依賴，只是以前畫布看得到、引擎看不到。
        self._hydrate_regions()
        self._changed()
        return True

    def set_edge_ports(self, src: str, dst: str, src_out: str = "",
                       dst_in: str = "") -> bool:
        """補上一條**還沒有埠**的線的埠。

        ⚠ **目前沒有任何呼叫者**（2026-08-24 全 repo 查過）。F9-9 把
        `studio._connect` 改成「先算出埠、加線的時候一起帶進去」之後，
        這條兩步的路就沒事做了 —— 理由見下面那段：補埠只挑得到一對節點之間
        的某一條，而兩條並排的線分不出該補哪一條。

        留著而不刪掉是因為它是 model 的公開 API，而「收起來的成本是零、
        刪掉的成本要先量」（`CLAUDE.md` §5 那張表）。要刪的話直接刪，
        沒有東西會壞。

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
        gone = [(e.dst, e.dst_in) for e in self.edges
                if hit(e) and e.dst_in]
        self.edges = keep
        order = self._topological_order(self.edges)
        if order is not None:
            self.node_order = order
        # **剪掉線就是拿掉來源**（F10）：剛剪掉線的那幾格由剩下的線說了算，
        # 沒有剩下的就空掉。以前這件事由 `studio._unpoint_stream` 做，
        # 現在區域線是一條真的 Edge，所以它是水合的自然結果（F42 B2）。
        self._hydrate_regions(emptied=gone)
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

    # ---- 區域線（F12；F42 B2 起存進 edges）--------------------------------
    def _hydrate_regions(self, emptied: Sequence[Tuple[str, str]] = ()) -> None:
        """區域參數的值 **＝ 落在它身上的線說的**（F42 B2）。

        **全程式只有這一支做這件事。** 方案 B 之後「用哪個區域」的儲存是那條
        線的 ``src_out``，參數是它的呈現 —— 兩份各存一次的話它們會漂，而 F9
        記過的六個「跑得完、有數字、而且是錯的」有一半是這個形狀。
        五個入口都走它：載檔、拉線、剪線、undo／redo、刪卡。

        ``emptied`` 是**這一次剛被拿掉線的那幾格** ``(節點, 參數)``。
        沒列進來的格子**只填不清**，而那個不對稱是刻意的：

        * 一格「有值、但沒有線」是 B3 之前**每一份既有 recipe** 的樣子 ——
          那時候參數是它唯一的儲存。在這裡清掉等於載入舊檔案就安靜地少量一塊。
        * 同一個狀態也是**打錯字**的樣子（``roi="epi_"``，沒有人定義它）。
          清掉的話 `unknown-region` 那條 lint 就永遠問不到了，而它守的正是
          「量測卡安靜地改量整張圖」（F7-9）—— 這一輪不該把它換成一句更差的話。
        * 但**剪掉線就是拿掉來源**（F10）：那一格要跟著空掉，不然畫面上線沒了、
          卡片還在量那一塊。剪的時候我們知道是哪一格，所以那幾格由線說了算。

        兩種講法在 B3 之後會合而為一：那時候每一格**指得到來源**的區域參數都
        有線，只剩打錯字的那種留著一個沒有線的值 —— 而那正是我們要它留著的。
        """
        want: Dict[Tuple[str, str], str] = dict(
            region_edge_values(self.nodes, self.edges))
        for key in emptied:
            # **只有區域那幾格**。剪掉的線大多是影像線，而影像那一格由
            # `studio._unpoint_stream` 管（它還要判斷剪掉的是一串裡的哪一條）
            # —— 在這裡一併清空的話，剪一條 `subtract.b` 的線會讓那一格空掉
            # **兩次**，其中一次繞過了那支判斷。實測會斷：畫布上有線、那一格
            # 是空的（`test_ui_canvas_truth` 抓到）。
            nid, pname = str(key[0]), str(key[1])
            node = self.nodes.get(nid)
            if node is None:
                continue
            try:
                specs = get_step(node.step).region_input_specs()
            except Exception:                  # noqa: BLE001 — 認不得的卡不管
                continue
            if any(sp.name == pname for sp in specs):
                want.setdefault((nid, pname), "")
        for (nid, pname), value in want.items():
            node = self.nodes.get(nid)
            if node is None:
                continue
            if str(node.params.get(pname, "") or "") == value:
                continue
            try:
                node.params = get_step(node.step).validate_params(
                    dict(node.params, **{pname: value}))
            except (ParamError, KeyError):     # pragma: no cover — 值就是區域名
                continue

    def region_outputs(self, node_id: str) -> List[str]:
        """這張卡右邊有哪些**區域埠**：自己定義的 ＋ **原樣送出的**。

        「同進同出」（F9-6 對影像做的規則，2026-08-19 使用者要求套到區域上：
        「區域線應該也要 follow 圖像線一樣，前進後出」）—— 接進來的區域，卡片
        後面也接得出去，否則量測卡就是一條死路：兩張卡要量同一個區域時，第二張
        只能回頭去接那張 Region 卡，而那條線會橫跨整張畫布。

        **這是畫布的事，不是引擎的事**：`ctx.rois` 本來就是全域的，一個區域被
        定義之後每一張後面的卡都用得到。這裡只是把那件事畫出來，
        `resolve_regions_out`（引擎的宣告）一個字都沒有變 —— 副標印的仍然是
        「這張卡**真的產出**什麼」（`regions_produced`）。
        """
        node = self.nodes.get(str(node_id))
        if node is None:
            return []
        try:
            step_cls = get_step(node.step)
            out = [str(r) for r in step_cls.resolve_regions_out(node.params) if r]
            passed = [str(r) for r in step_cls.resolve_regions_in(node.params) if r]
        except Exception:                  # noqa: BLE001 — 顯示用，壞了就空著
            return []
        return out + [r for r in passed if r not in out]

    # ---- GLV「我要量什麼」三選（PR-2 2a）----------------------------------
    #
    # 為什麼腦袋在 model 不在表單：``roi`` 是**線水合**的（`to_json_dict`
    # 還會把跟線一致的值省略），所以 preset 填 roi ＝ 改區域線的埠 ——
    # 而線、參數、undo 都住在這裡。表單只畫三顆鈕、發一個 id。
    def _glv_region_edges(self, node_id: str, param: str) -> List[Edge]:
        nid = str(node_id)
        return [e for e in self.edges
                if e.dst == nid and e.dst_in == str(param)]

    def glv_intent(self, node_id: str) -> str:
        """這張 GLV 卡現在對得上哪個 preset（對不上回 ``"custom"``）。

        **偵測永不改 recipe** —— 「自訂」是一個顯示狀態，不是要被修正的錯。
        """
        node = self.nodes.get(str(node_id))
        if node is None or node.step != "glv_stats":
            return GLV_INTENT_CUSTOM
        roi_edges = self._glv_region_edges(node_id, "roi")
        if len(roi_edges) != 1:
            return GLV_INTENT_CUSTOM         # 沒接（或接了好幾條）都是自訂
        wired = str(roi_edges[0].src_out)
        base = wired
        for suffix in ("_center", "_others"):
            if base.endswith(suffix):
                base = base[:-len(suffix)]
        producer = str(roi_edges[0].src)
        ref = str(node.params.get("reference", REF_NONE) or REF_NONE)
        boxes = str(node.params.get("across_boxes", POOLED) or POOLED)
        ref_edges = self._glv_region_edges(node_id, "reference_region")
        if (wired == centre_name(base) and ref == REF_REGION
                and boxes == POOLED and len(ref_edges) == 1
                and ref_edges[0].src == producer
                and str(ref_edges[0].src_out) == others_name(base)):
            return "defect_box"
        if wired == base and not ref_edges:
            if ref == REF_NONE and boxes == EACH_BOX:
                return "oddest_box"
            if ref == REF_NONE and boxes == POOLED:
                return "region_stats"
        return GLV_INTENT_CUSTOM

    def apply_glv_intent(self, node_id: str, intent: str) -> bool:
        """套一個 preset：只動 roi / reference_region 的線與 reference /
        across_boxes 兩格，**一次 Ctrl+Z 全還原**（compound）。

        preset (1) 是使用者 2026-08-27 拍板的**現行正確寫法**：roi 接
        `<n>_center`、reference="another region"、reference_region 接
        `<n>_others`（兩條虛線、同一個 producer）—— 工作單字面的
        REF_OTHERS+_center 會派生出沒人產的 `<n>_center_others`，不用。
        套不上（沒有 roi 線、producer 沒那顆埠）回 False，什麼都不動。
        """
        nid = str(node_id)
        node = self.nodes.get(nid)
        if node is None or node.step != "glv_stats":
            return False
        roi_edges = self._glv_region_edges(nid, "roi")
        if len(roi_edges) != 1:
            return False
        producer = str(roi_edges[0].src)
        base = str(roi_edges[0].src_out)
        for suffix in ("_center", "_others"):
            if base.endswith(suffix):
                base = base[:-len(suffix)]
        ports = set(self.region_outputs(producer))

        want_roi = {"defect_box": centre_name(base),
                    "oddest_box": base, "region_stats": None}
        if str(intent) not in want_roi:
            return False
        roi_port = want_roi[str(intent)]
        if roi_port is not None and roi_port not in ports:
            return False
        if str(intent) == "defect_box" and others_name(base) not in ports:
            return False

        with self.compound("glv-intent:%s" % nid):
            if roi_port is not None:
                for e in list(self._glv_region_edges(nid, "roi")):
                    self.remove_edge(e.src, nid, e.src_out, "roi")
                self.add_edge(producer, nid, roi_port, "roi")
            # 藏起來的參數掛著線＝畫布說謊 —— 不是 defect_box 就把參照線清掉。
            for e in list(self._glv_region_edges(nid, "reference_region")):
                self.remove_edge(e.src, nid, e.src_out, "reference_region")
            if str(intent) == "defect_box":
                self.add_edge(producer, nid, others_name(base),
                              "reference_region")
                self.set_param(nid, "reference", REF_REGION)
                self.set_param(nid, "across_boxes", POOLED)
            elif str(intent) == "oddest_box":
                self.set_param(nid, "reference", REF_NONE)
                self.set_param(nid, "across_boxes", EACH_BOX)
            else:
                self.set_param(nid, "reference", REF_NONE)
                self.set_param(nid, "across_boxes", POOLED)
        return True

    def region_producer(self, name: str,
                        before_node: Optional[str] = None) -> str:
        """誰定義了區域 ``name``（沒有人回空字串）。

        ⚠ **F42 B4 起這一支在 `d4t/` 底下沒有呼叫者了**，而它是刻意留著的
        （工作單指名保留）。它原本的消費者 `region_lines()` 在 B4 刪掉 ——
        區域線現在是真的 Edge，畫布直接讀 `edge_lines()`。

        留著的理由是它回答的問題還在，而且**核心那一份還在用同一個語意**：
        `recipe._region_producer` 是遷移補線時找來源的那一支，兩邊逐字相同
        （「上游最後一個」）。這一支是它在 UI 側的對照 ——
        要動那個語意的時候，兩邊要一起動。

        便利貼：`tests/test_ui_region_hydration.py::
        test_the_ui_and_the_core_agree_on_who_defines_a_region`。

        **取上游最後一個**，跟引擎一致：``Context.set_roi`` 明文同名覆寫，所以
        兩張卡都叫 ``epi`` 時，量測卡量到的是後面那張寫的框。

        ⚠ **那個撞名本身現在是 error**（F42 B0 的 ``duplicate-region``）——
        所以在一份健檢乾淨的 recipe 上「最後一個」＝「唯一一個」，這一支跟
        引擎不可能給出不同的答案。以前它只是「區域的 fact 特徵會撞」那一條
        warning，而 warning 擋不住一條指著第一張卡、卻拿到第二張卡的框的線。

        「最後一個」也涵蓋**原樣送出**的卡（見 :meth:`region_outputs`）——
        三張卡串著量同一個區域時，線是一段一段接的，不是三條都從最前面那張
        Region 卡拉出來（那正是影像流的畫法）。
        """
        name = str(name or "").strip()
        if not name:
            return ""
        owner = ""
        for nid in self.node_order:
            if nid == before_node:
                break
            node = self.nodes.get(nid)
            if node is None or not node.enabled:
                continue
            # **原樣送出的也算**（同進同出）：線要從使用者拉的那顆埠出發，
            # 而他拉的是上一張卡右邊那顆，不是三張卡以前那張 Region 卡的。
            if name in self.region_outputs(nid):
                owner = nid
        return owner

    # ---- Recipe 互轉 -------------------------------------------------------
    def to_recipe(self) -> Recipe:
        # 其他 route 原樣寫回去（F23 期2）。**正在編的這一條贏**：兩條 route
        # 共用的節點（load）以編輯中的版本為準 —— 使用者改的就是它。
        routes = {k: list(v) for k, v in self._other_routes.items()}
        routes[self.kind] = list(self.node_order)
        nodes = {nid: RecipeNode(id=nid, step=n.step, params=dict(n.params),
                                 enabled=n.enabled)
                 for nid, n in self._other_nodes.items()}
        nodes.update({nid: RecipeNode(id=nid, step=n.step,
                                      params=dict(n.params), enabled=n.enabled)
                      for nid, n in self.nodes.items()})
        return Recipe(
            recipe_id=self.recipe_id,
            routes=routes,
            edges=list(self.edges) + [e for e in self._other_edges
                                      if e not in self.edges],
            nodes=nodes,
            score=ScoreSpec(expr=self.expr, threshold=self.threshold,
                            bins=dict(self.bins)),
            decide=self.decide,
            route_by=self.route_by,
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
        m.decide = getattr(recipe, "decide", None)
        # 分流與**沒在編的那幾條 route**（F23 期2）：原樣抱著，`to_recipe`
        # 合併回去。共用的節點在 `m.nodes`（上面那行收了），這裡只留其他
        # route 專屬的。
        m.route_by = getattr(recipe, "route_by", None)
        m._other_routes = {rk: list(v) for rk, v in recipe.routes.items()
                           if rk != k}
        m._other_nodes = {nid: RecipeNode(id=nid, step=n.step,
                                          params=dict(n.params),
                                          enabled=n.enabled)
                          for nid, n in recipe.nodes.items()
                          if nid not in in_route}
        m._other_edges = [e for e in (recipe.edges or [])
                          if not (e.src in in_route and e.dst in in_route)]
        m.bins = dict(recipe.score.bins)
        # 區域線推回它落在的那一格（F42 B2）。**只填不清** —— 舊檔案的區域
        # 參數還沒有線，那一格是它唯一的儲存（見 :meth:`_hydrate_regions`）。
        m._hydrate_regions()
        m.dirty = False
        m.clear_history()
        return m

    # ---- 分流（F23 期2）----------------------------------------------------
    def route_keys(self) -> List[str]:
        """這份 recipe 所有的 route 鍵（正在編的排最前面）。"""
        return [self.kind] + sorted(self._other_routes)

    def set_route_by(self, column: str, mapping: Dict[str, str],
                     default: str = "") -> None:
        """整包換掉 ``route_by``（編輯器一格一格改，最後長的就是這一包）。"""
        new = RouteBy(column=str(column).strip().upper(),
                      map={str(k).strip(): str(v) for k, v in mapping.items()},
                      default=str(default))
        if new == self.route_by:
            return
        self._push_undo()
        self.route_by = new
        self._changed()

    def clear_route_by(self) -> None:
        if self.route_by is None:
            return
        self._push_undo()
        self.route_by = None
        self._changed()

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

    重算走 :func:`~d4t.core.export.summarize`（跟 CLI／Excel 報表同一份邏輯，
    不另外寫一份會漂移的），只是先把 bin 按新門檻換掉 —— **不重跑任何影像**，
    所以拖門檻線是即時的。
    """
    if not ground_truth or not results:
        return None
    from d4t.core.export import summarize

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
