# 回歸：畫布上連線的「斷開」×，按下去要真的斷得掉。
"""使用者回報：

> 「我在 n8n like 的 UI 節點做操作時，發現按下字卡間的線的 X 時，
>   **時常會沒有反應**。」

F7-22 已經有一條測試（``test_ui_f7_19_wiring.py::test_a_line_can_be_cut_where_it_is``）
在守這顆 ×，而它是綠的 —— 因為它問的是**幾何**：×的圓心在不在
``boundingRect`` 裡、``cut_hit(圓心)`` 是不是 True。那兩件事從頭到尾都成立。

沒被問到的是**那一下滑鼠到底送給了誰**。兩個獨立的原因讓它送錯：

1. **上游那張卡的命中區蓋住了 ×。** ``_NodeItem.boundingRect`` 為了讓埠標籤
   （畫在卡片右緣**之外**）重繪得到而加寬了 56px，而 ``QGraphicsItem`` 預設的
   ``shape()`` 就是 ``boundingRect()`` —— 於是那 56px 空白也變成卡片的命中區。
   兩欄相距 96px，相鄰欄那條線的中點正好落在上游卡右緣 +48px，還在裡面。
   hover 會**穿過**不收 hover 的圖元（卡片不收），所以 × 畫得出來、使用者看得到；
   **按下不會穿過**，z 值大的卡片（0）贏過連線（-1），那一下變成「選取上游那張卡」。
2. **畫出來的 × 比線的命中區大。** ``shape()`` 只是把線加粗到 10px（兩側各 5px），
   而 × 的半徑是 8、``cut_hit`` 收到 10。瞄準圓周那一圈就落在 shape 外面，
   而且滑鼠一走進去 hover 就結束、× 當場消失。

所以這個檔案裡的每一條都**真的派送一顆滑鼠事件**，問的是「使用者做了這個動作，
recipe 有沒有改變」，而不是「幾何算對了嗎」。看得到的東西要按得到 ——
那是一個關於**事件送到哪裡**的問題，量座標量不出來。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from adept.ui import canvas as canvas_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QEvent=QEvent, QPointF=QPointF, Qt=Qt, QMouseEvent=QMouseEvent,
             QApplication=QApplication, canvas_mod=canvas_mod,
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
    win.show()
    yield win
    win.close()


def _click_scene(view, scene_pos):
    """在畫布的某個**場景座標**上完整點一下（移動 → 按下 → 放開）。

    移動那一顆不能省：× 只在 hover 的時候存在，而使用者本來就是「先把滑鼠
    移過去、看到 × 出現、才按下去」。離屏平台上自己建構事件比 ``QTest`` 可靠
    （既有測試也是這樣做的）。
    """
    vp = view.viewport()
    pt = QPointF(view.mapFromScene(scene_pos))
    glob = QPointF(vp.mapToGlobal(pt.toPoint()))
    for etype, button, buttons in (
            (QEvent.MouseMove, Qt.NoButton, Qt.NoButton),
            (QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton),
            (QEvent.MouseButtonRelease, Qt.LeftButton, Qt.NoButton)):
        QApplication.sendEvent(
            vp, QMouseEvent(etype, pt, glob, button, buttons, Qt.NoModifier))


def _wired_pair(window, step_key="denoise"):
    """接一張卡出來，回 ``(上游 id, 下游 id, 那條實線)``。"""
    src = window.model.node_order[0]
    nid = window.add_card_after(src, step_key)
    assert window.model.has_edge(src, nid) is True
    edge = next(e for e in window.pipeline._edges
                if e.pair() == (src, nid))
    return src, nid, edge


# --------------------------------------------------------------------------- #
# 1. 按下去要真的斷掉（原始的 bug）
# --------------------------------------------------------------------------- #
def test_clicking_the_cut_button_actually_disconnects(window):
    """使用者原話的那個動作：把滑鼠移到 × 上、按下去。"""
    src, nid, edge = _wired_pair(window)

    _click_scene(window.pipeline, edge.cut_center())

    assert window.model.has_edge(src, nid) is False, (
        "按在 × 的正中央，那條線還在 —— 那一下被別人收走了")
    assert "Disconnected" in window.status_text()


def test_the_upstream_card_does_not_swallow_the_click(window):
    """這是上一條為什麼會壞：中點落在上游卡**隱形的**命中區裡。

    症狀之所以難查，是因為畫面上真的有東西動了 —— 上游那張卡被選起來，
    而使用者盯著的是那條沒斷掉的線。
    """
    src, nid, edge = _wired_pair(window)
    centre = edge.cut_center()
    card = window.pipeline.node_item(src)

    # 前提：中點確實在那張卡的 boundingRect 裡（不然這條測試沒有在測東西）
    assert card.sceneBoundingRect().contains(centre), (
        "版面變了，這條測試要重挑一個中點")

    # 而它**不在**卡片的命中區裡 —— 命中區只到卡片本體 + 埠的抓取半徑
    assert card.shape().contains(card.mapFromScene(centre)) is False

    items = window.pipeline.scene().items(centre)
    assert isinstance(items[0], canvas_mod._EdgeItem), (
        "最上面的應該是那條線，實際是 %s" % type(items[0]).__name__)

    window.select_node(nid)
    _click_scene(window.pipeline, centre)
    assert window.selected_node != src, "那一下變成選取上游那張卡了"


def test_the_whole_drawn_x_is_clickable_not_just_its_middle(window):
    """畫出來的圓有多大，按得到的就要有多大。

    ×的半徑是 8，而線的 shape 只加粗到兩側各 5px —— 中間差的那幾 px 是圓
    **四分之一以上**的面積。瞄到那裡不只是沒反應：滑鼠一離開 shape，hover 就
    結束、× 當場消失，看起來像「這顆鈕會躲」。
    """
    from PySide6.QtCore import QPointF as _P

    for dx, dy in ((0, -canvas_mod._CUT_R), (0, canvas_mod._CUT_R),
                   (-canvas_mod._CUT_R, 0), (canvas_mod._CUT_R, 0)):
        src, nid, edge = _wired_pair(window)
        target = edge.cut_center() + _P(dx, dy)
        assert edge.shape().contains(target), (
            "(%+d,%+d) 畫得出來卻不在命中區裡" % (dx, dy))
        _click_scene(window.pipeline, target)
        assert window.model.has_edge(src, nid) is False, (
            "按在 × 的 (%+d,%+d) 沒有反應" % (dx, dy))


def test_the_cut_area_and_the_hit_test_read_the_same_number(window):
    """``cut_hit`` 與 ``shape`` 用同一個 ``CUT_GRAB`` —— 兩份定義遲早會分岔，
    而分岔的症狀正是「時好時壞」。"""
    _, _, edge = _wired_pair(window)
    grab = edge.CUT_GRAB
    from PySide6.QtCore import QPointF as _P

    inside = edge.cut_center() + _P(grab - 0.5, 0)
    outside = edge.cut_center() + _P(grab + 4.0, 0)
    assert edge.cut_hit(inside) is True and edge.shape().contains(inside)
    assert edge.cut_hit(outside) is False
    # boundingRect 仍然蓋得住整顆圓（不然移開會留殘影 —— §7 那條老坑）
    assert edge.boundingRect().contains(inside)


def test_a_card_parked_on_top_of_the_line_does_not_hide_the_cut_button(window):
    """節點是拖得動的，所以「線的中點會不會被某張卡蓋到」不是設計時算得完的事。

    線平常畫在卡片底下（卡片才是主角），於是被蓋住的那顆 × 既看不見也按不到。
    滑鼠移上來的那一條**抬到卡片之上** —— 使用者正在瞄的就是它。
    """
    src, nid, edge = _wired_pair(window)
    centre = edge.cut_center()
    resting = edge.zValue()

    # 把另一張卡直接停在中點上（使用者拖一下就會發生的事）
    parked = window.pipeline.node_item(nid)
    parked.setPos(centre.x() - canvas_mod.NODE_W / 2.0,
                  centre.y() - canvas_mod.NODE_H / 2.0)
    centre = edge.cut_center()          # 路徑跟著端點動了，重取一次
    parked.setPos(centre.x() - canvas_mod.NODE_W / 2.0,
                  centre.y() - canvas_mod.NODE_H / 2.0)
    centre = edge.cut_center()
    assert parked.shape().contains(parked.mapFromScene(centre)), (
        "這條測試要的前提是那張卡真的壓在中點上")
    assert resting < parked.zValue(), "沒 hover 的線應該在卡片底下"

    _click_scene(window.pipeline, centre)
    assert window.model.has_edge(src, nid) is False, (
        "×被卡片蓋住就按不到了")


# --------------------------------------------------------------------------- #
# 2. 縮小命中區不能把卡片本身弄壞（這一版最容易造成的回歸）
# --------------------------------------------------------------------------- #
def test_the_card_itself_is_still_clickable(window):
    """卡片本體照樣點得到、點了就選起來。"""
    src, nid, _ = _wired_pair(window)
    item = window.pipeline.node_item(nid)
    window.select_node(src)

    body = item.sceneBoundingRect()
    _click_scene(window.pipeline,
                 item.scenePos() + QPointF(canvas_mod.NODE_W / 2.0,
                                           canvas_mod.NODE_H / 2.0))
    assert window.selected_node == nid, "點卡片中央應該選起來（%s）" % body


def test_the_ports_are_still_grabbable(window):
    """從輸出埠拉線是畫布的主要動作 —— 命中區縮小之後它要原封不動。

    埠畫出來只有 5px，命中半徑是 ``_PORT_GRAB``（15）；縮小 shape 時如果沒把
    這一圈算進去，使用者會發現「線拉不出來了」。
    """
    src, _, _ = _wired_pair(window)
    item = window.pipeline.node_item(src)
    for i, anchor in enumerate(item.out_anchors_local()):
        assert item.out_port_at(anchor) == i
        assert item.shape().contains(anchor), (
            "第 %d 個輸出埠不在命中區裡" % i)
        # 埠的抓取圈往外凸出卡片，那一圈也要點得到（拉線的人瞄的是圓點外圍）
        assert item.shape().contains(
            anchor + QPointF(canvas_mod._PORT_GRAB - 1.0, 0.0))
    assert item.shape().contains(item.in_port_local()), "輸入埠"


def test_the_bounding_rect_still_covers_the_port_labels(window):
    """**命中區縮小了，重繪範圍不准跟著縮。**

    埠標籤（test / ref）畫在卡片右緣之外，boundingRect 少算就會留殘影 ——
    這個坑在 F7-8 / F7-9 / F7-14 踩過三次。這一版的重點正是「這兩個範圍是
    兩件事」，所以兩邊都要鎖。
    """
    src, _, _ = _wired_pair(window)
    item = window.pipeline.node_item(src)
    labelled = [n for n in item.out_names() if n]
    assert labelled, "Input 卡本來就該有具名的輸出埠"

    br = item.boundingRect()
    for anchor in item.out_anchors_local():
        # 標籤畫在埠右邊 _PORT_LABEL_W 那塊
        assert br.contains(anchor + QPointF(canvas_mod._PORT_LABEL_W - 12, 0))
    assert br.width() > item.shape().boundingRect().width(), (
        "重繪範圍本來就該比命中區大 —— 那正是這個 bug 的來源")
