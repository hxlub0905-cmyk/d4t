# F7-19 驗收（畫布那一半）：在畫布上接得出「兩條流都做」。
"""使用者第八輪回饋：

> 「USER 還是沒辦法隨意在畫布上連線，例如我在 Load image 後放上 Normalize 卡，
>   我先在畫布上連 test，但我也想將 ref 牽線過去時，會變成只牽 ref 過去；
>   如果要牽兩條必須點選後方卡片然後 source 兩個都勾才行。
>   **我希望是能夠互相連動的。**」

F7-18 把「同一對節點再拉一條線」定義成**取代**（「我改變主意了，這張卡改做
ref」）。那在「一張卡一條流」的世界裡是對的，因為那時候一張卡本來就只能做一條。
F7-20 讓一張卡吃 N 條流之後，那個語意就變成擋路的了：畫布上做得出來的最多只有
一條，第二條要回控制列去勾 —— 而那正是 F7-18 想拿掉的東西。

所以規則改成**看參數型別**：

* ``image_keys``（一串流）→ **累加**。先拉 test 再拉 ref = 兩張都做。
* ``image_key``（單一具名角色，``subtract`` 的 a / b）→ **取代**。
  往 a 再拉一條是「改接別的」，不是「a 有兩條」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    g["QPointF"] = QPointF

    from adept.ui import canvas as canvas_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1200, 700)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 累加：先拉 test 再拉 ref = 兩張都做
# --------------------------------------------------------------------------- #
def test_wiring_a_second_stream_adds_it_instead_of_replacing(window):
    """使用者原話的那個情境，逐字重演一次。"""
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize")

    window.pipeline.link_to(src, nid, port=0)          # test
    assert window.model.nodes[nid].params["streams"] == "test"

    window.pipeline.link_to(src, nid, port=1)          # ref —— 以前這裡會蓋掉
    assert window.model.nodes[nid].params["streams"] == "test,ref"
    assert "test" in window.status_text() and "ref" in window.status_text()


def test_the_second_line_actually_appears_on_the_canvas(window):
    """接上去要看得見。畫布不能說謊 —— 那是 F7-18 起就在守的東西。

    線的數量是從「兩端共用的影像流」推出來的（``_ports_between``），所以
    ``streams`` 一多一條，那條線就自己出現了，不必另外記。
    """
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize")
    window.pipeline.link_to(src, nid, port=0)
    a, b = window.pipeline.card(src), window.pipeline.card(nid)
    assert window.pipeline._ports_between(a, b) == [0]

    window.pipeline.link_to(src, nid, port=1)
    a, b = window.pipeline.card(src), window.pipeline.card(nid)
    assert window.pipeline._ports_between(a, b) == [0, 1], \
        "兩條流都接上了，畫布上就要有兩條線"


def test_wiring_the_same_stream_twice_changes_nothing(window):
    """重複拉同一條不該把它加兩次（``test,test`` 會讓那張卡做兩遍）。"""
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize")
    window.pipeline.link_to(src, nid, port=0)
    window.pipeline.link_to(src, nid, port=0)
    assert window.model.nodes[nid].params["streams"] == "test"


def test_both_streams_then_get_the_same_settings(window):
    """累加買到的東西：兩條流吃**同一組設定**，所以它們還比得起來。

    這是「成對的卡各自漂移」那個安靜失敗的結構性解法（計畫書 §22.7 第一條）。
    """
    from adept.core.pipeline import get_step

    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize")
    window.pipeline.link_to(src, nid, port=0)
    window.pipeline.link_to(src, nid, port=1)
    window.model.set_param(nid, "p_low", 5.0)

    params = window.model.nodes[nid].params
    cls = get_step("normalize")
    assert cls.resolve_writes(cls.validate_params(params)) == ["test", "ref"]
    assert float(params["p_low"]) == 5.0        # 一組參數，不是兩組


# --------------------------------------------------------------------------- #
# 2. 角色埠仍然是取代
# --------------------------------------------------------------------------- #
def test_a_role_port_is_still_replaced_not_accumulated(window):
    """``subtract`` 的 a / b 是**角色**：數量固定、接錯位置就算錯。

    往 a 再拉一條的意思是「改接別的」。如果這裡也累加，``a`` 會變成
    ``test,ref`` —— 一個 ``image_key`` 塞了兩個名字，那張卡執行時會找不到
    那條流，而使用者完全看不出自己做錯了什麼。
    """
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "subtract")
    before = dict(window.model.nodes[nid].params)

    window.pipeline.link_to(src, nid, port=0)
    window.pipeline.link_to(src, nid, port=1)
    after = window.model.nodes[nid].params
    for key in ("a", "b"):
        assert "," not in str(after[key]), key
    # subtract 沒有主流參數，連線不該亂改它的 a / b
    assert after == before


# --------------------------------------------------------------------------- #
# 3. 兩條流的卡照樣跑得動（接完就能按試跑）
# --------------------------------------------------------------------------- #
def test_a_two_stream_card_runs(window, tmp_path):
    """接完兩條線之後直接跑，兩條流都要真的被處理到。"""
    import numpy as np

    from adept.core.pipeline import get_step
    from adept.core.pipeline.context import Context

    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize")
    window.pipeline.link_to(src, nid, port=0)
    window.pipeline.link_to(src, nid, port=1)

    row = np.linspace(0, 120, 64).astype(np.uint8)
    ctx = Context(images={"test": np.tile(row, (64, 1)),
                          "ref": np.tile(row // 2, (64, 1))})
    get_step("normalize")().run(ctx, window.model.nodes[nid].params)
    assert ctx.images["test"].max() == 255
    assert ctx.images["ref"].max() == 255


# --------------------------------------------------------------------------- #
# 4. 並排比對：左 test 右 ref，底下兩張直方圖
# --------------------------------------------------------------------------- #
def test_compare_defaults_to_test_on_the_left_and_ref_on_the_right(window, tmp_path):
    """使用者原話：「開啟 Compare（雙圖模式）就是預設左側 test 右側 ref」。

    以前左邊跟著「這張卡處理哪條流」走，所以點一張做 ref 的卡就變成左 ref
    右 test —— 每點一張卡都要重認一次哪邊是哪邊，而並排的用途正是互相對照。
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from make_sample import generate

    out = generate(str(tmp_path / "lotC"), n=4, seed=11)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize", "ref")   # 一張做 ref 的卡
    window.select_node(nid)
    window.refresh_preview(sync=True)

    assert window.set_compare(True) is True
    assert window.stream_combo.currentText() == "test"
    assert window.stream_combo_b.currentText() == "ref"


def test_compare_shows_one_histogram_per_image(window, tmp_path):
    """畫面上兩張圖，底下就要兩張直方圖，而且左右順序一樣。"""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from make_sample import generate

    out = generate(str(tmp_path / "lotD"), n=4, seed=12)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize")
    window.pipeline.link_to(src, nid, port=1)          # 兩條流都接上
    window.select_node(nid)
    window.refresh_preview(sync=True)

    insp = window.inspector()
    assert insp.panes() == ["test"], "沒開並排時就一張"

    window.set_compare(True)
    window.refresh_preview(sync=True)
    assert window.inspector().panes() == ["test", "ref"]
    assert "“test”" in window.inspector().summary()
    assert "“ref”" in window.inspector().summary()


def test_the_histogram_says_what_its_axes_are(qapp):
    """使用者原話：「histogram 我有點看不太懂，橫軸是 GLV 縱軸是 pixel counts？
    細線是什麼？」—— 三個問題，三個都是畫面上沒寫。

    用畫素比對太脆弱，所以這裡驗的是**那些字真的被畫出去了**：把面板 render
    到 pixmap 的同時攔下每一次 drawText。
    """
    from PySide6.QtGui import QColor, QPixmap

    from adept.ui import inspectors as insp_mod

    insp = insp_mod.EnhanceInspector()
    insp.resize(420, 220)
    insp.set_context("tone", params={"streams": "test"}, meta={"stream_change": {
        "test": {"before": [3, 9, 4], "after": [1, 12, 3],
                 "clipped_low": 0.0, "clipped_high": 0.0,
                 "was_clipped_low": 0.0, "was_clipped_high": 0.0}}})

    drawn = []
    real = insp_mod.QPainter.drawText

    def spy(self, *a):
        for x in a:
            if isinstance(x, str):
                drawn.append(x)
        return real(self, *a)

    insp_mod.QPainter.drawText = spy
    try:
        pm = QPixmap(insp.size())
        pm.fill(QColor("#ffffff"))
        insp.render(pm)
    finally:
        insp_mod.QPainter.drawText = real

    text = " | ".join(drawn)
    assert "gray level" in text, "橫軸要講得出自己是什麼"
    assert "pixels" in text, "縱軸也要"
    assert "black" in text and "white" in text
    # 「細線是什麼」要用圖例回答，而且是畫一段線配一個字，不是叫人對應名詞
    assert "before" in text and "after" in text
    assert "outline" not in text, "不要再用 outline / filled 這種要先翻譯的字"


# --------------------------------------------------------------------------- #
# 5. 兩個打磨（F7-21 第二批）
# --------------------------------------------------------------------------- #
def test_the_node_does_not_say_the_same_thing_twice(window):
    """副標已經印 ``test ref → test ref``，摘要就不要再印 ``streams=test,ref``。

    第三行是拿來放「這張卡被設定成什麼」的（門檻、方法、半徑）。被一個跟上面
    那行同義的字佔掉，等於少了一行資訊。
    """
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize")
    window.pipeline.link_to(src, nid, port=1)
    assert window.model.nodes[nid].params["streams"] == "test,ref"

    node = window.model.nodes[nid]
    summary = window._node_summary(node, shown=["test", "ref"])
    assert "streams" not in summary

    # 但**沒有**被副標講到的設定仍然要出現 —— 這一行不是「什麼都不印」。
    window.model.set_param(nid, "p_low", 7.0)
    summary = window._node_summary(window.model.nodes[nid],
                                   shown=["test", "ref"])
    assert "p_low" in summary


def test_a_stream_the_subtitle_does_not_mention_is_still_shown(window):
    """借範圍的那條流不在 reads→writes 那一行裡，所以它要留在摘要中。"""
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "normalize", "ref")
    window.model.set_param(nid, "range_from", "test")
    summary = window._node_summary(window.model.nodes[nid], shown=["ref"])
    assert "range_from" in summary


def test_the_clipping_mark_sits_on_the_bar_it_is_about(qapp):
    """削平標記要長在被標記的那根柱子上。

    以前它是畫在圖的**正上方**一小塊色塊 —— 離它在講的那根柱子有半張圖那麼遠，
    於是看起來像一個獨立的裝飾：看得到，但看不出來在指什麼。

    這裡驗的是「警示色出現在最左／最右那一格的柱子範圍內」，用畫素數，
    不去斷言確切座標（那會鎖死版面）。
    """
    from PySide6.QtGui import QColor, QImage

    from adept.ui import inspectors as insp_mod
    from adept.ui import theme as theme_module

    warn = QColor(theme_module.TOKENS["danger_text"]).rgb()
    insp = insp_mod.EnhanceInspector()
    insp.resize(300, 200)
    # 六成畫素壓在黑端 → 一定要標出來
    insp.set_context("tone", params={"streams": "test"}, meta={"stream_change": {
        "test": {"before": [1, 5, 5, 1], "after": [30, 2, 2, 1],
                 "clipped_low": 0.6, "clipped_high": 0.0,
                 "was_clipped_low": 0.0, "was_clipped_high": 0.0}}})
    img = QImage(insp.size(), QImage.Format_RGB32)
    img.fill(QColor("#ffffff"))
    insp.render(img)

    cols = [x for x in range(img.width()) for y in range(img.height())
            if img.pixel(x, y) == warn]
    assert cols, "削平了六成，畫面上要看得到警示色"
    # 警示色只出現在左邊那一小段（最左那一格），不是散在整張圖上
    assert max(cols) < img.width() * 0.35, \
        "標記要貼在最左那根柱子上，不是飄在別的地方"


# --------------------------------------------------------------------------- #
# 6. n8n 化第二批（F7-22）：畫布拿整欄、線上的 ×、排整齊
# --------------------------------------------------------------------------- #
def test_the_settings_pane_is_open_by_default_and_collapsible(window):
    """D 案（2026-08-14 使用者拍板）：畫布會 zoom、又有彈出視窗，平面上
    只需要中上一塊 —— 設定**預設攤開**、拿大頭。F7-22 的「雙擊才攤開」
    因此退役：雙擊仍然可以把收起來的設定重新攤開，但那不再是唯一入口。
    """
    assert window.params_open() is True, "設定預設攤開（D 案）"

    src = window.model.node_order[0]
    window.select_node(src)
    assert window.param_form.step_key() == "load_patch"

    window.set_params_open(False)          # 「現在只想看流程」
    assert window.params_open() is False

    window.pipeline.card(src).mouseDoubleClickEvent(_FakeDouble())
    assert window.params_open() is True, "雙擊把收起來的設定重新攤開"
    assert window.selected_node == src


class _FakeDouble:
    """QGraphicsSceneMouseEvent 的替身（只用到 accept()）。"""

    def accept(self):
        pass


def test_a_line_can_be_cut_where_it_is(window):
    """接錯線的人要看得到怎麼斷開。

    選起來按 Delete 本來就做得到，但畫面上沒有任何東西講出這件事 —— 刪除的
    入口要長在被刪的那條線上面。
    """
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "denoise")
    assert window.model.has_edge(src, nid) is True

    edge = next(e for e in window.pipeline._edges
                if e.pair() == (src, nid))
    assert edge.acceptHoverEvents() is True
    # × 畫在線的中點，而 boundingRect 一定要蓋得住它（不然移開會留殘影）
    assert edge.boundingRect().contains(edge.cut_center())
    assert edge.cut_hit(edge.cut_center()) is True
    assert edge.cut_hit(edge.cut_center() + QPointF(40, 40)) is False


def test_route_order_has_no_lines_at_all(window):
    """route 順序的金色虛線 2026-08-14 退役（使用者：「會混淆」）——
    畫布上只有使用者拉的線，每一條都有 ×。"""
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "denoise")
    pairs = {e.pair() for e in window.pipeline._edges}
    assert pairs == set(window.model.edges), \
        "畫布上的線要恰好等於使用者拉的 edges"


def test_tidy_puts_the_cards_back_on_the_grid(window):
    """節點拖得動，拖過就亂了 —— 而以前只能自己一個個搬回去。"""
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "denoise")
    item = window.pipeline.card(nid)
    before = item.pos()
    item.setPos(before.x() + 321.0, before.y() + 234.0)
    assert item.pos() != before

    window.pipeline.tidy()
    assert item.pos() == before, "排整齊要把它放回自動排版的位置"


def test_a_card_can_be_dragged_from_the_library_onto_the_canvas(window):
    """「Add」是**工具決定位置**（接在選著的那張後面）；拖是**使用者決定位置**。

    兩個都留著 —— n8n 兩種都有，而第一次用的人多半先看到按鈕。
    """
    from PySide6.QtCore import QMimeData

    from adept.ui.widgets import CARD_MIME

    before = list(window.model.node_order)
    entry = window.library.entry("denoise")
    assert entry is not None

    mime = QMimeData()
    mime.setData(CARD_MIME, entry.step_key.encode("utf-8"))
    window.pipeline.card_dropped.emit("denoise", 640.0, 320.0)

    order = window.model.node_order
    assert len(order) == len(before) + 1
    nid = window.selected_node
    assert window.model.nodes[nid].step == "denoise"
    item = window.pipeline.card(nid)
    # 落在放開的地方（節點以中心對齊落點）
    assert abs(item.pos().x() + canvas_mod.NODE_W / 2.0 - 640.0) < 1.0
    assert abs(item.pos().y() + canvas_mod.NODE_H / 2.0 - 320.0) < 1.0


def test_only_a_card_drag_is_accepted(window):
    """自訂 MIME 型別，不是純文字 —— 不然從別的視窗拖一段字進來也會變成新增卡片。"""
    from adept.ui.widgets import CARD_MIME

    assert CARD_MIME.startswith("application/")
    assert window.pipeline.acceptDrops() is True


# --------------------------------------------------------------------------- #
# 7. 工具列整理（F7-22）
# --------------------------------------------------------------------------- #
def test_the_toolbar_is_grouped_not_one_long_row(window):
    """七顆等權重的鈕排成一列，讀起來是一串 —— 使用者得逐顆讀完才知道要按哪顆。

    分成「檔案｜起手與輸出｜復原｜…｜說明・主題｜試跑」，段與段之間一條分隔線。
    """
    actions = window.toolbar.actions()
    seps = [i for i, a in enumerate(actions) if a.isSeparator()]
    assert len(seps) >= 3, "至少要三條分隔線（四段）"

    def index_of(widget):
        for i, a in enumerate(actions):
            if window.toolbar.widgetForAction(a) is widget:
                return i
        raise AssertionError("not on the toolbar: %r" % widget)

    # 檔案那段在最前面，試跑在最後面
    assert index_of(window.btn_open_klarf) < seps[0]
    # 試跑那一段在最後面。F7-23 起它是兩顆（主體 + ▾），而 F7-24 第二輪把那
    # 兩顆包進同一個容器 —— 中間只留 1px，讓它讀起來是「一件事的兩個半邊」
    # 而不是兩顆不相干的按鈕。所以工具列上的最後一格是那個容器。
    assert index_of(window.trial_group) == len(actions) - 1
    assert window.btn_trial.parent() is window.trial_group
    assert window.btn_trial_more.parent() is window.trial_group
    # Help 與主題被移到右邊（在撐開的空白之後），不再混在檔案操作裡
    assert index_of(window.btn_help) > index_of(window.btn_export)
    assert index_of(window.btn_help) > index_of(window.btn_undo)


def test_undo_has_a_button_not_only_a_shortcut(window):
    """F7-16 給了 Ctrl+Z，但工具列上沒有對應的鈕。

    目標使用者是不寫 code 的工程師 —— 「這個軟體能不能反悔」不該只寫在
    快捷鍵裡。而且沒得退的時候要**看得出來**沒得退。
    """
    assert window.btn_undo.isEnabled() is False
    assert "Nothing to undo" in window.btn_undo.toolTip()
    assert window.btn_redo.isEnabled() is False

    src = window.model.node_order[0]
    window.add_card_after(src, "denoise")
    assert window.btn_undo.isEnabled() is True
    assert "Ctrl+Z" in window.btn_undo.toolTip(), "tooltip 要帶快捷鍵"

    window.btn_undo.click()
    assert window.btn_redo.isEnabled() is True
    assert window.model.node_order == [src]


def test_adding_one_card_is_one_undo(window):
    """使用者做的是**一個**動作，所以復原也該是一步。

    加一張卡在 model 上其實是三個動作（add_step → set_param 指影像流 →
    add_edge）。各記一步的話，按一次 Ctrl+Z 會看到**卡還在但線不見了** ——
    那比不能復原更糟，因為畫面上出現了他從來沒有做出來過的東西。

    這件事以前沒人發現，是因為工具列上根本沒有復原鈕（只有快捷鍵）。
    """
    src = window.model.node_order[0]
    before = list(window.model.node_order)
    before_edges = list(window.model.edges)

    window.add_card_after(src, "denoise", "ref")
    assert len(window.model.node_order) == len(before) + 1

    assert window.undo() is True
    assert window.model.node_order == before, "一次就要回到原狀"
    assert list(window.model.edges) == before_edges
