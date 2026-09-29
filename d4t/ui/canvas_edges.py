# d4t UI — authored 2026-09-19 (F116 第 6 步).
"""**畫布上拉一條線／剪一條線，在 model 上是什麼意思**（鐵則 10 的主場）。

為什麼自己一個模組（`CLAUDE.md` §4：`studio.py` 留給接線，不留給內容）：
計畫書把這一塊猜成「本質上就是接線」，**量出來不是**：437 行裡，六支規則型的
方法就佔 284 行（`_point_at_stream` 75、`_apply_edge_removed` 69、
`_connect_region` 47、`connect` 40、`unpoint_stream` 27、`_param_for_stream` 26），
真正的 handler 只有 67 行。那 284 行寫的是**規則**：

* 一條線從哪顆輸出埠出發，決定下游那張卡的哪一格指到哪條流（F7-18）；
* **一個輸入埠只能有一條線** —— 舊線讓位（`_drop_conflicting_edges`），
  不然引擎查來源的 key 撞在一起，`dict` 後寫的贏，而那個順序畫布上看不出來
  （`docs/PITFALLS.md` 第 66 列：跑得完、有數字、而且是錯的）；
* **區域線住在 `recipe.edges` 裡**，`roi="epi"` 那一格是從線水合出來的，判準只有
  `recipe.is_region_edge`（`_connect_region` / `_apply_edge_removed`）——
  F42 之前它不在 edges 裡，於是量測卡先跑、`ctx.rois` 是空的、安靜地退回量整張圖
  （PITFALLS 第 36 列）；
* **拉一條線 = 一步復原**：在 model 上它其實是三個動作，各記一步的話按一次
  Ctrl+Z 會停在「線接上了但那張卡還沒改成處理它」這種使用者從來沒做出過的畫面。

**形狀**：模組層函式吃 `win`（同 `ui/studio_layout.py`、`ui/open_dialogs.py`、
`ui/region_check.py`）—— 這一族**沒有任何自己的狀態**，全部讀寫 `win.model`。

**行為零改動**（F116 §1）：本體逐字搬，只把 `self` 換成 `win`。
族外叫得到的那幾支改成公開名（`on_edge_added`、`connect`、`on_edge_removed`…），
而 `StudioWindow` 上的門面**留著舊名字** —— 所以 191 處引用 `_on_edge_added`
的測試一個字都不用改。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from d4t.core.pipeline import ParamError, get_step
from d4t.core.pipeline.step import NUMBERS, RESULTS
from d4t.core.pipeline.recipe import Edge, is_data_edge, is_region_edge

from . import card_menu
from . import edit_plan
from . import wording

if TYPE_CHECKING:                      # 只給型別看：這一支不 import studio
    from .studio import StudioWindow


def _point_at_stream(win: "StudioWindow", node_id: str, stream: str,
                     accumulate: bool = False, param: str = "") -> str:
    """把 ``node_id`` 的輸入接上 ``stream``（回一句給狀態列的話）。

    這是「用節點表達要對哪一張圖做」的實作點：使用者從 ``ref`` 那顆輸出埠
    拉一條線過來，講的就是**這張卡也做 ref**。以前那句話只能在控制列的
    下拉裡講，畫布只表達得出先後順序 —— 於是 test 是主角、ref 是附帶。

    **累加還是取代，看參數型別**（F7-19）：

    - ``image_keys``（一串流，例如 Enhance 卡的 ``streams``）且
      ``accumulate=True`` → **累加**。先拉 test 再拉 ref 的意思是「兩張都
      做」，不是「改成只做 ref」。這正是使用者說的「希望是能夠互相連動
      的」—— 以前第二條線把第一條的設定蓋掉，於是畫布上做不出「兩條都
      接」，得回控制列去勾。
    - ``image_key``（單一具名角色，例如 ``subtract`` 的 ``a`` / ``b``）→
      **取代**。往 ``a`` 再拉一條是「改接別的」，不是「a 有兩條」。

    ``accumulate`` 由呼叫端決定，而它的判準是**這條線是不是新的依賴**：

    - **第一條線**（``add_edge`` 成功）→ 取代。卡片預設的 ``streams="test"``
      是規格的預設值，不是使用者拉的線；把 ref 累加上去的話，他拉了一條卻
      得到兩條，而畫布就說謊了。
    - **同一對節點的第二條線**（``has_edge``）→ 累加。那才是「這條也接上」。
    - 從卡片庫加一張新卡（``add_card_after``）→ 取代，理由同第一條。

    累加不必回頭處理畫線：畫布的線數是從「兩端共用的影像流」推出來的
    （``_ports_between``），``streams`` 一多一條，那條線就自己出現了。
    """
    node = win.model.nodes.get(str(node_id))
    if node is None or not stream:
        return ""
    try:
        specs = {p.name: p for p in get_step(node.step).params}
    except KeyError:                       # pragma: no cover
        return ""
    # F10：落點由呼叫端給（使用者放開滑鼠的那一格）。沒給才自己挑。
    names = [param] if param else [
        sp.name for sp in get_step(node.step).input_specs()]
    for name in names:
        spec = specs.get(name)
        if spec is None or spec.type not in ("image_key", "image_keys"):
            continue
        # 這就是這張卡吃影像流的那個參數 = 這條線的 ``dst_in``（F9-5b）。
        #
        # ⚠ **那件事不在這一支做**：`_connect` 早就把它交給 `add_edge` 了
        # （`dst_in=plan.param`），而且是在呼叫這裡**之前**。順序有意義 ——
        # 參數的預設值本來就等於那條流時，下面會提早 return（沒有東西要
        # 改），但線還是接在這個參數上。落在這一支的話那條線在引擎眼裡就是
        # 「沒指定」，於是退回用「執行順序上最後一個寫它的人」推 ——
        # 分支當場失效。
        #
        # 這裡以前還有一個 `win._bound_param = name`（上下各一次）——
        # 那是那個舊機制的殘留：**寫了三次、一次都沒有被讀過**。真相搬到
        # 邊上之後它就只是一個會讓人以為「有人在用它」的欄位。2026-09-08 刪。
        current = str(node.params.get(name, "") or "")
        if spec.type == "image_keys" and accumulate:
            keys = [k.strip() for k in current.split(",") if k.strip()]
            if stream in keys:
                return ""
            keys.append(stream)
            value, joined = ",".join(keys), True
        else:
            if current == stream:
                return ""
            value, joined = stream, False
        try:
            win.model.set_param(str(node_id), name, value)
        except ParamError:                 # pragma: no cover — 值就是流名
            return ""
        if joined and "," in value:
            return (" — “%s” now works on %s (same settings for both)"
                    % (node_id, " and ".join(value.split(","))))
        return " — “%s” now works on %s" % (node_id, stream)
    return ""

def _producers_of(win: "StudioWindow", stream: str) -> List[str]:
    """哪些卡片（用預設參數）會產出 ``stream``。

    ⚠ **實作住 `ui/edit_plan.py`**（U6）：它是圖編輯語意的一部分，而那一族
    必須在沒有 QApplication 的情況下問得出來。這裡只是轉呼叫。
    """
    return edit_plan.producers_of(win.model, stream)

def unmet_needs(win: "StudioWindow", node_id: str) -> str:
    """剛加的卡少了什麼上游 —— 講成一句可以照做的話（含前導空白）。

    ⚠ 實作住 `ui/edit_plan.py`（同上）。
    """
    return edit_plan.unmet_needs(win.model, node_id)

def _drop_conflicting_edges(win: "StudioWindow", src: str, dst: str, stream: str,
                            param: str) -> str:
    """拿掉「跟這條新線搶同一個輸入」的舊線；回一句給狀態列的話。

    ⚠ **判準住 `edit_plan.conflicting_edges`**（U6）—— 那是引擎正確性的
    一半（F9-7「一個輸入埠只能有一條線」），而它現在問得起來而不必開視窗。
    這裡只剩「真的拿掉」與「說一句話」。
    """
    return _drop_edges(
        win, edit_plan.conflicting_edges(win.model, src, dst, stream, param))

def _drop_edges(win: "StudioWindow", losers: Sequence[Any]) -> str:
    """把讓位的那幾條線真的拿掉；回一句給狀態列的話（沒有就回空字串）。

    ⚠ **兩個埠都要指名**（B1，2026-08-24）。兩張卡之間可以有好幾條並排的
    線（F9-9），而它們可能落在**不同的輸入格**上 —— 只帶 `src_out` 的話
    `remove_edge` 的語意是「符合這個 src_out 的**全部**」，於是剪一條會剪掉
    一整排。

    實測：`load.test → subtract.a` 與 `load.test → subtract.b` 兩條並存時，
    把別的卡接到 `b` 會**連 `a` 那條一起剪掉** —— 沒有人碰過 `a`，而 `a` 的
    參數還留著 `test`：畫布上沒有線、卡片卻還指著那條流，於是引擎退回
    「執行順序上最後一個寫它的人」用猜的。線性時猜得中、分岔時猜錯，
    而且跑得完、有數字（F9／F10 整整兩輪在防的形狀）。

    ⚠ **不可以寫 `e.src_out or None`。** 空字串在 `remove_edge` 裡本來就是
    「精確比對空埠」，`or None` 會把它變成「全部」—— 那正是上面那個洞的
    第二階。
    """
    losers = list(losers or [])
    for e in losers:
        win.model.remove_edge(e.src, e.dst, src_out=e.src_out,
                               dst_in=e.dst_in)
    if not losers:
        return ""
    return (" (replacing the line from %s)"
            % ", ".join(sorted({e.src for e in losers})))


def on_edge_added(win: "StudioWindow", src: str, dst: str, stream: str = "",
                   dst_in: str = "") -> None:
    """拉一條線。會造成循環時 model 回 False —— 那條線就不會出現。

    擋在這裡（而不是等執行時報錯）是刻意的：使用者看到的是「這條線拉不
    起來」，不是「拉起來之後整條 pipeline 壞掉」。

    ``stream`` 是**線從哪個輸出埠出發**（F7-18）。從 ref 那顆埠拉過去，
    意思就是「這張卡做在 ref 上」，所以下游那張卡的主要輸入跟著改。
    以前這件事只能在控制列的下拉裡講，於是同一個動作在畫布上做不完。

    兩個節點之間**已經有線**也照樣要處理那句話：先從 test 拉、再從 ref 拉
    是很正常的操作（「我改變主意了，這張卡要做在 ref 上」），而以前它只會
    得到一句「already connected」然後什麼都沒發生 —— 看起來就像畫布不准
    你碰 ref。

    **拉一條線 = 一步復原**（F9-7）。在 model 上它其實是三個動作
    （add_edge → set_param →（有時）拿掉搶同一個輸入的舊線），各記一步
    的話按一次 Ctrl+Z 會停在「線接上了但那張卡還沒改成處理它」這種中間
    狀態 —— 使用者從來沒有做出過那個畫面。

    ⚠ 這一段以前寫著 ``add_edge → set_param → set_edge_ports → …``，
    而 `set_edge_ports` 從 F9-9 起就沒有人叫了（那一輪改成「加線的時候
    就把埠一起帶進去」，因為補埠只找得到一對節點之間的第一條線，
    兩條並排的線會補錯）。留著一個描述不存在流程的說明比沒有說明更糟 ——
    它就寫在那段程式碼的正上方。
    """
    src, dst, stream = str(src), str(dst), str(stream or "")
    with win.model.compound("connect"):
        connect(win, src, dst, stream, str(dst_in or ""))

def data_ports(info: Dict[str, Any], model: Any, node_id: str,
               step_cls: Any, unwired: bool) -> None:
    """畫布上這張卡的**資料埠**（F123 期 2）：加進 Studio 組好的那份 info。

    * 入埠：Decision 的 ``numbers``、Output 的 ``results``（``accepts`` 講它收
      哪幾種線 —— Output 兩種都收，拖線時亮哪幾顆埠看它）。
    * 出埠：寫數字的卡一顆 ``numbers``、Decision 一顆 ``results``。還沒接上
      來源的卡不長（F10：前後都是空的）。
    * 副標：有資料線接進來才講（``numbers → results``）；沒有就照舊說
      ``(not connected)`` —— 那正是實情。

    住在這裡而不是 `studio.py`：這件事從頭到尾都是線的事，而 `studio.py`
    那一格只准往下（CLAUDE.md §4）。
    """
    if step_cls is None:
        return
    for port in step_cls.data_inputs:
        info["inputs"].append({
            "name": port, "label": port, "stream": "", "role": "",
            "kind": port,
            "accepts": [RESULTS, NUMBERS] if port == RESULTS else [port]})
    out = "" if unwired else step_cls.data_output(model.nodes[node_id].params)
    info["data_out"] = out
    if step_cls.data_inputs and any(
            e.dst == node_id and is_data_edge(e, model.nodes)
            for e in model.edges):
        info["reads"] = list(info.get("reads") or []) + list(step_cls.data_inputs)
        if out:
            info["produces"] = [out]


def remove_card(win: "StudioWindow", node_id: str) -> None:
    """刪掉一張卡（F117 J4 把它從 `studio.py` 搬過來）。

    **為什麼住在這裡**：這件事從頭到尾都是線的事 —— 剪掉它餵出去的每一條、
    把下游那幾格空出來、算一份補線的提議。`studio.py` 留給接線（CLAUDE.md §4），
    而它那一格是 `HARD_CAPS`：要往它加東西，先從它手上搬走等量的東西。
    """
    node_id = str(node_id)
    if node_id == win.model.decision_node() and not _drop_the_tree(win):
        return
    # 刪掉一張卡 = 把它餵出去的每一條線都剪掉（F10-5）。下游那幾格要跟著
    # 空出來，否則它們指著一條再也沒有人產出的流 —— 跟按 × 剪掉是同一件事，
    # 所以走同一條路（`_unpoint_stream`），不要在這裡另寫一份。
    with win.model.compound("remove-card"):
        for e in [e for e in win.model.edges if e.src == node_id]:
            # **區域線跳過**（F42 B2）：它現在也住在 `model.edges` 裡，而
            # 它那一格是**水合**出來的 —— 在線還在的時候先把它清掉，
            # 「參數 ＝ 線說的」那條不變量就當場破了（而它是常開的斷言）。
            # `model.remove` 拿掉線之後水合會把它空出來，這裡不必動它。
            if is_region_edge(e, win.model.nodes) or is_data_edge(
                    e, win.model.nodes):
                continue                  # 資料線沒有下游那一格要空（F123）
            unpoint_stream(win, e.dst, e.src_out, e.dst_in)
        # 區域線**不必**在這裡處理了（F42 B2）：它現在是一條真的 Edge，
        # 而 `RecipeModel.remove` 刪卡時本來就會把它兩端的線一起拿掉 ——
        # 拿掉之後水合就把下游那幾格空出來。以前它是從參數推導的，
        # 所以「把那一格空掉」非得在這裡自己做一次不可。
        name = wording.card(win.model, node_id)   # 先取名，移除之後查不到
        # 誰還指著它產出的數字（F122）—— 同樣要在刪之前問。
        fallout = win.model.removal_fallout(node_id)
        # **補線的提議要在刪之前算**（F117 J4）—— 刪完之後那幾條線已經
        # 不在 model 裡了，算不出「本來接到哪」。
        plan = win.model.bridge_plan(node_id)
        win.model.remove(node_id)
    if win.selected_node == node_id:
        win.selected_node = None
        win.param_form.set_step(None, {}, [])
    if getattr(win.model, "decide", None) is None:
        win.show_param_page()     # 右邊不留一個判定已經不在的編輯面板
    tail = (" " + " ".join(fallout)) if fallout else ""
    if plan:
        # ⚠ **提議，不是自動接**（鐵則 10：畫布上每一條線都是使用者拉
        # 的）。按下去才成真，而按下去的是使用者。
        win._status_next_step(
            "Removed “%s” — %d line%s went with it.%s" % (
                name, len(plan), "" if len(plan) == 1 else "s", tail),
            "Reconnect", lambda: bridge(win, plan),
            tip="Wire what fed “%s” straight into what it fed." % name)
    elif fallout:
        win._status("Removed “%s”.%s" % (name, tail))
    else:
        win._status("Removed “%s”" % name)


def _drop_the_tree(win: "StudioWindow") -> bool:
    """刪 Decision 卡＝拿掉整棵判定樹 —— **先問過**（2026-08-25 起的規矩）。

    底下掛著使用者自己畫的整棵樹，而刪卡的重量看起來跟刪一張 Denoise 一樣。
    復原回得來（一步），但「一個 Delete 把三層樹默默吃掉」不是那個鍵該有的重量。
    """
    from PySide6.QtWidgets import QMessageBox

    from .tree_scene import display_tree, layout_cells

    d = getattr(win.model, "decide", None)
    if d is None:
        return True
    n = sum(1 for c in layout_cells(display_tree(d), d) if c.get("kind") == "leaf")
    answer = QMessageBox.question(
        win, "Remove the decision?",
        "This takes the whole decision off the canvas - %d class%s and every "
        "question that sorts into them.\n\nUndo brings it back."
        % (n, "" if n == 1 else "es"),
        QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
    return answer == QMessageBox.Yes


def bridge(win: "StudioWindow", plan) -> int:
    """把 :meth:`RecipeModel.bridge_plan` 算出來的那幾條線接起來（F117 J4）。

    **走跟使用者拉線同一條路**（:func:`connect`）—— 不是 `model.add_edge`。
    接一條線在 model 上是好幾個動作（加線、把下游那一格指到這條流、擠掉搶同
    一個輸入的舊線），而那些規矩住在 `edit_plan` 裡。從這裡另開一條捷徑，等於
    讓「一鍵補線」接出來的線跟手拉的線**不一樣** —— 而畫布上看起來會一模一樣。

    整批算**一步復原**：使用者按的是一顆鈕，Ctrl+Z 就該退回按之前。
    """
    rows = list(plan or [])
    if not rows:
        return 0
    with win.model.compound("bridge"):
        for src, src_out, dst, dst_in in rows:
            connect(win, str(src), str(dst), str(src_out or ""),
                    str(dst_in or ""))
    return len(rows)


def connect(win: "StudioWindow", src: str, dst: str, stream: str,
             dst_in: str = "") -> None:
    """使用者拉了一條線 —— **決定住 `edit_plan`，這裡只負責做與說**（U6）。

    ⚠ **順序有意義，所以它留在這裡**：`add_edge` 會因為成環而失敗，而
    失敗的那條線**不該留下任何痕跡** —— 尤其不是「那張卡安靜地改成做 ref
    了」。把 mutation 也包進計畫裡就得在那邊把 model 模擬一遍，那是把一個
    難的東西換成兩份會漂的東西。
    """
    plan = edit_plan.plan_connect(win.model, src, dst, stream, dst_in)
    if plan.kind == edit_plan.REJECT:
        win._status(plan.reject, "error")
        return
    # **「已經接過了」兩側共用一關**（U6）：以前影像那一側問的是
    # `has_line`、區域那一側問的是「這個名字在不在那一格裡」，兩句話寫在
    # 兩個地方。現在兩個都由 `plan.already` 回答 —— 而它們本來就是同一個
    # 問題（使用者剛做的這個動作有沒有改變任何東西）。
    if plan.already:
        win._status(plan.already)
        return
    if plan.kind == edit_plan.REGION:
        _connect_region(win, src, dst, stream, plan)
        return
    if plan.kind == edit_plan.DATA:
        # 數字線與結果線（F123 期 2）：一條線就是全部，沒有參數要指、沒有舊線
        # 要擠掉（一顆資料埠接很多條）。成環由 `add_edge` 擋。
        if win.model.add_edge(src, dst, src_out=stream, dst_in=plan.param):
            win._status("Connected %s → %s (%s)" % (src, dst, stream))
        else:
            win._status("Cannot connect %s → %s — that would make the "
                        "pipeline loop back on itself." % (src, dst), "error")
        return
    if not win.model.add_edge(src, dst, src_out=stream,
                               dst_in=plan.param):
        win._status("Cannot connect %s → %s — that would make the "
                     "pipeline loop back on itself." % (src, dst), "error")
        return
    # 影像流在**線真的接起來之後**才改（見上面那段 ⚠）。同一對節點的第二
    # 條線是「這條也接上」（累加），不是「改接別的」。
    note = _point_at_stream(win, dst, stream, accumulate=plan.accumulate,
                                 param=plan.param)
    # **一個輸入埠只能有一條線**：新的這條贏，舊的那條拿掉（F9-7）。
    dropped = _drop_edges(win, plan.conflicts)
    # **接完線就把這張卡填到「看得到結果」為止**（F11 Region-3 第五輪）。
    # 加卡的時候也跑過一次，但那時候還沒有線 —— 而「接上 layout labels」
    # 正是使用者期待畫面上出現東西的那一刻。
    win._autofill_new_card(dst)
    win._resync_params(dst)
    win._status("Connected %s → %s%s%s" % (src, dst, note, dropped))

# ---- 區域線（F12）-----------------------------------------------------
def _is_region_param(win: "StudioWindow", node_id: str, param: str) -> bool:
    """``node_id`` 的 ``param`` 那一格吃的是具名區域嗎。

    ⚠ 實作住 `ui/edit_plan.py`（U6）—— 這裡只是轉呼叫。
    """
    return edit_plan.is_region_param(win.model, node_id, param)

def _line_kind(win: "StudioWindow", node_id: str, name: str) -> str:
    """從 ``node_id`` 的哪一顆埠拉出來的 —— 影像還是區域。

    ⚠ 實作住 `ui/edit_plan.py`（同上）。
    """
    return edit_plan.line_kind(win.model, node_id, name)

def _connect_region(win: "StudioWindow", src: str, dst: str, name: str,
                    plan: Any) -> None:
    """把 ``dst`` 的區域那一格接上 ``src`` 定義的區域 ``name``。

    **擋得住什麼、哪幾條舊線讓位，全部由 `edit_plan.plan_connect` 決定**
    （U6）—— 這裡只剩「真的動 model」與「說一句話」，而那兩件事的順序
    有意義（見 `_connect` 那段 ⚠）。
    """
    param = plan.param
    node = win.model.nodes.get(dst)
    spec = next((sp for sp in get_step(node.step).region_input_specs()
                 if sp.name == param), None)
    current = str(node.params.get(param, "") or "")
    keys = [k.strip() for k in current.split(",") if k.strip()]
    # **從一個變成兩個時，把自動填的那個名字收回**（F13-⑥）。
    # 接第一條線時 `_autofill_output_prefix` 會把輸出名填成那個區域
    # （F7-11），而第二條線一來，每個數字本來就會帶自己的區域名 ——
    # 兩個加起來是 `epi_epi_glv_mean`。判準是「它正好等於原本那一個
    # 區域的名字」＝ 那正是自動填會寫的值；使用者自己打過的字不動。
    multi = spec is not None and spec.type == "region_keys"
    if multi and len(keys) == 1 and \
            str(node.params.get("output_prefix", "")) == keys[0]:
        try:
            win.model.set_param(dst, "output_prefix", "")
        except ParamError:                 # pragma: no cover
            pass
    # **改名的連帶影響要在值變之前先記下來**（F37 A2）。以前它是
    # `set_param` 的回傳值，而 F42 B2 之後值是**水合**出來的 —— 那一格不再
    # 由這裡寫，所以「動之前長什麼樣」也要由這裡自己抱著。
    before = dict(node.params)
    if not win.model.add_edge(src, dst, src_out=name, dst_in=param):
        win._status("Cannot connect %s → %s — that would make the "
                     "pipeline loop back on itself." % (src, dst), "error")
        return
    # **單一角色的區域埠一條線**（F12 §7-②）：`region_key` 那一格只放得下
    # 一個名字，所以第二條線是「改接別的」不是「這個也算」。判準住
    # `edit_plan.region_conflicts`。
    _drop_edges(win, plan.conflicts)
    value = str(win.model.nodes[dst].params.get(param, "") or "")
    # 挑了區域就順手把輸出名填成區域的名字（F7-11）—— 拉線跟在設定區挑
    # 是同一個動作，所以走同一條路。
    win._autofill_output_prefix(dst, param, value)
    says = win.model.rename_fallout(dst, before,
                                     win.model.nodes[dst].params)
    win._resync_params(dst)
    say_fallout(win, says, "“%s” now measures %s (defined by “%s”)."
                      % (dst, value.replace(",", " and "), src))

def say_fallout(win: "StudioWindow", says: List[str], otherwise: str = "") -> None:
    """改名的連帶影響優先於「接好了」那句話（F37 A2）。

    量測卡的前綴是條件式的，所以在一張既有的卡上多接一條區域線，它寫的
    每一個名字都會改（``glv_median`` → ``epi_glv_median`` ＋
    ``mg_glv_median``），而分數表達式、判定樹、Output 卡的 ``rank_by``
    裡指著舊名字的字不會跟著改。

    使用者只做了一個動作，下游三個地方同時失效 —— 而在這之前，畫面上唯一
    的訊息是「接好了」。所以有連帶影響的時候，**那句話蓋過成功訊息**
    （紅字），沒有的時候才報成功。

    ⚠ 這一句是**當下**的提醒，不是唯一的防線：`stale-feature-ref` 這條
    lint 會讓那張卡在畫布上一直掛著警示標記，直到有人處理它。狀態列的字
    會被下一個動作蓋掉，而那正是它不能是唯一防線的理由。
    """
    if says:
        # **誤操作後的三秒鐘，是使用者最不想去找 Ctrl+Z 的三秒鐘**（X6）。
        # 他正在讀這句話，所以反悔的路要在這句話旁邊。Ctrl+Z 照樣在 ——
        # 這顆鈕只是把已經做得到的事縮短成一次點擊。
        win._status_next_step(
            " ".join(says), "Undo", win.undo, "error",
            "Undo that change (Ctrl+Z)")
    elif otherwise:
        win._status(otherwise)

def _param_for_stream(win: "StudioWindow", node_id: str) -> str:
    """線沒有指定落點時，這條線該接哪一格輸入（沒有輸入回空字串）。

    F10 起**正常路徑不會走到這裡** —— 使用者放開滑鼠的位置就是落點。
    這是給程式化拉線（測試、之後可能的自動排版）用的退路，判準是
    「第一個**還空著**的輸入」：接第二條線時它自然落到還沒接的那一格，
    而不是又去蓋掉第一格。

    以前這裡是一張寫死的名單（``streams`` → ``target`` → ``source``），
    於是 ``subtract`` 的 ``a`` / ``b`` 永遠只挑得到 —— 兩顆輸入的卡在畫布上
    根本分不開。名單也不會自己認得之後加的卡。
    """
    node = win.model.nodes.get(str(node_id))
    if node is None:
        return ""
    try:
        specs = [sp for sp in get_step(node.step).input_specs()
                 if sp.visible_for(node.params)]
    except KeyError:                       # pragma: no cover
        return ""
    if not specs:
        return ""
    for spec in specs:
        if not str(node.params.get(spec.name, "") or "").strip():
            return spec.name
    return specs[0].name

def on_edge_removed(win: "StudioWindow", src: str, dst: str, stream: str = "",
                     dst_in: str = "") -> None:
    """剪掉一條線 —— **收尾一定要重讀設定欄**（見 :meth:`_resync_params`）。

    用一層外殼而不是在每個 ``return`` 前面加一行：這支底下有五條分支
    （區域線／瞄得到那一條／退回整對／舊格式…），而漏掉其中一條的症狀是
    「大部分時候會跟上」—— 那種 bug 查起來最貴。
    """
    try:
        _apply_edge_removed(win, src, dst, stream, dst_in)
    finally:
        win._resync_params(dst)

def _apply_edge_removed(win: "StudioWindow", src: str, dst: str, stream: str = "",
                        dst_in: str = "") -> None:
    """剪掉一條線。``stream`` 是剪刀瞄的那一條（F9-9），``dst_in`` 是它
    進到下游的哪一格（F10）。

    兩張卡之間可以有兩條並排的線，所以**剪一條**跟剪掉整個依賴是兩件事。
    瞄不到特定那條（舊格式的線沒有埠）就退回拿掉整對。

    **剪掉線就是拿掉來源**（F10）：線是唯一的來源，所以那一格要跟著空掉。
    不空的話畫布會反過來說謊 —— 畫面上線沒了，卡片卻還指著那條流，而且
    照樣跑得出數字。使用者回報的原話是「把線按 X 清掉，後方卡片的 Node
    不會跟著清掉」。
    """
    src, dst, stream = str(src), str(dst), str(stream or "")
    dst_in = str(dst_in or "")
    # 剪之前先問清楚這條線落在哪一格 —— 剪完就查不到了。
    # **這一段要排在區域那條岔路前面**（F42 B2）：區域線現在也是一條真的
    # Edge，所以「這是不是區域線」的答案就藏在剛問出來的那個 ``dst_in`` 裡。
    if not dst_in:
        for e in win.model.edges:
            if (e.src == src and e.dst == dst
                    and (not stream or e.src_out == stream)):
                dst_in = e.dst_in
                break
    # **區域線現在是一條真的 Edge**（F42 B2）：剪它跟剪影像線一樣，
    # 而「那一格跟著空掉」是水合的自然結果（`RecipeModel._hydrate_regions`）
    # —— 不必在這裡另外清一次。以前它沒有 Edge 可刪，所以清參數就是全部。
    if dst_in and is_data_edge(Edge(src, dst, stream, dst_in),
                               win.model.nodes):
        # 數字線與結果線（F123 期 2）：一條就是一條，剪掉它不動任何參數。
        if win.model.remove_edge(src, dst, src_out=stream or None,
                                 dst_in=dst_in):
            win._status("Disconnected %s → %s (%s)" % (src, dst, stream))
        return
    if _is_region_param(win, dst, dst_in):
        node = win.model.nodes.get(dst)
        before = dict(node.params) if node is not None else {}
        with win.model.compound("disconnect"):
            gone = win.model.remove_edge(
                src, dst, src_out=stream or None, dst_in=dst_in)
        if not gone:
            win._status("%s → %s is not connected on %s."
                         % (src, dst, stream or "that region"))
            return
        says = win.model.rename_fallout(
            dst, before, win.model.nodes[dst].params)
        left = str(win.model.nodes[dst].params.get(dst_in, "") or "")
        note = ((" — “%s” has no region on “%s” now" % (dst, dst_in))
                if not left else
                " — “%s” now measures %s" % (dst, left.replace(",", " and ")))
        note += ("  " + " ".join(says)) if says else ""
        win._status("Disconnected %s → %s on %s%s"
                     % (src, dst, stream or "that region", note))
        return
    with win.model.compound("disconnect"):
        one = stream and win.model.remove_edge(
            src, dst, src_out=stream, dst_in=dst_in or None)
        # **知道是哪一格就用它**（B5，2026-08-24）。上面那一段已經從線本身
        # 問出了 ``dst_in``，但沒有流名時 ``stream and …`` 整條短路掉，於是
        # 直接跳到最後那個「拿掉整對」—— 兩張卡之間有兩條並排的線時
        # （F9-9 起是正常的接法），使用者按一把剪刀會斷兩條。
        if not one and dst_in:
            one = win.model.remove_edge(src, dst, dst_in=dst_in)
            if one:
                note = unpoint_stream(win, dst, stream, dst_in)
                win._status("Disconnected %s → %s%s" % (src, dst, note))
                return
        if one:
            note = unpoint_stream(win, dst, stream, dst_in)
            win._status("Disconnected %s → %s on %s%s"
                         % (src, dst, stream, note))
        # 兩個埠都問不出來（舊格式的線沒有埠）→ 拿掉整對。那是刻意的：
        # 瞄不到特定那一條的時候，「全部拿掉」至少是可預期的。
        elif win.model.remove_edge(src, dst):
            note = unpoint_stream(win, dst, stream, dst_in)
            win._status("Disconnected %s → %s%s" % (src, dst, note))

def unpoint_stream(win: "StudioWindow", node_id: str, stream: str,
                    param: str = "") -> str:
    """線剪掉了 → 那條流也要從下游卡的參數裡拿掉（回一句給狀態列的話）。

    不拿掉的話畫布會**反過來說謊**：畫面上那條線沒了，卡片卻還在處理它
    （`streams=test,ref` 一個字都沒變）。這是 F9-7「接線時參數跟著改」的
    另一半。

    ⚠ **「那一格會變成什麼」住 `edit_plan.plan_unpoint`**（U6）—— 含那兩個
    F10 拿掉的保留條款、以及「區域那一格不歸這裡管」。這裡只剩寫值與說話。
    """
    plan = edit_plan.plan_unpoint(win.model, node_id, stream, param)
    if not plan.change:
        return ""
    try:
        says = win.model.set_param(str(node_id), plan.param, plan.value)
    except ParamError:                     # pragma: no cover — 值就是流名
        return ""
    # 影像流那一側同理（接第二條流也會把名字加上流名前綴）。這一支回的是
    # 一段**接在成功訊息後面**的字，所以連帶影響也接在同一句話上 ——
    # 而不是另外開一個要有人記得去消費的欄位。
    tail = ("  " + " ".join(says)) if says else ""
    if not plan.value:
        return " — “%s” has no input on “%s” now%s" % (
            node_id, plan.label, tail)
    return " — “%s” now works on %s%s" % (node_id, " and ".join(
        plan.value.split(",")), tail)


def on_link_dropped(win: "StudioWindow", src: str, kind: str, stream: str,
                     x: float, y: float,
                     pick: Optional[str] = None) -> Optional[str]:
    """線拖到空白處放開 → 只列接得上的卡；挑了就加在那裡並把線接上
    （F99 P1-1）。線是使用者拉的，所以這不是「加卡順手接線」。
    """
    keys = card_menu.compatible(win.library.step_keys(), kind)

    def add(step_key: str) -> None:
        win._on_card_dropped(str(step_key), float(x), float(y))
        nid = win.selected_node
        if not nid:
            return
        dst_in = card_menu.input_param_for(str(step_key), kind)
        on_edge_added(win, str(src), nid, str(stream), dst_in)

    if pick is not None:
        add(str(pick))
        return win.selected_node
    from PySide6.QtGui import QCursor
    menu = card_menu.build_menu(
        win, keys, add, flat=True,
        title="Connect “%s” to a new card" % (stream or kind))
    card_menu.pick_at(menu, QCursor.pos())
    return None
