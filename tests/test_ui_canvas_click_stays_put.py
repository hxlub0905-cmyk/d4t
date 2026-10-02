# 2026-10-02：點卡片不准讓卡片跑掉、雙擊不准跳出空白視窗。
"""使用者回報兩件事（2026-10-02）：

* 「在畫布上快速點單張卡兩下，會快速跳出好幾個空白視窗顯示然後關掉」——
  設定面板在同一回合被重建兩次（雙擊＝選到＋啟用），第一次塞進去的每一列被
  `setParent(None)` 拆下來時沒先 `hide()`，Qt 排好的「顯示」落在一個沒有父視窗
  的 widget 上，它就是一個空白頂層視窗。GLV 卡量到 16 個。
* 「點卡片時有時候會亂排版（跑到畫布上很遠的地方）」—— 選到卡就捲進視野
  （F117 A3）發生在滑鼠**還按著**的時候，Qt 把那一下重播成移動；雙擊攤開設定
  會重設分隔比例、Decision 收合會重算畫布範圍，同一個機制。實測 y 600 → 1088。

這幾條都是**真的送滑鼠事件**到 viewport 上去量，不是叫 `select_node`。
`QTest.mouseDClick` 在 PySide6 6.11 只送雙擊事件不送按放，所以自己建構整串。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import first_source  # noqa: E402

pytest.importorskip("PySide6")


def _import_qt(g):
    from PySide6.QtCore import QEvent, QObject, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QWidget

    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QEvent=QEvent, QObject=QObject, QPointF=QPointF, Qt=Qt,
             QMouseEvent=QMouseEvent, QApplication=QApplication, QWidget=QWidget,
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
    win.resize(1100, 650)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def _send(view, scene_pos, steps):
    """對 viewport 送一串滑鼠事件；``steps`` 是 ``(type, button, buttons, dx, dy)``。"""
    vp = view.viewport()
    for etype, button, buttons, dx, dy in steps:
        pt = QPointF(view.mapFromScene(scene_pos)) + QPointF(dx, dy)
        glob = QPointF(vp.mapToGlobal(pt.toPoint()))
        QApplication.sendEvent(
            vp, QMouseEvent(etype, pt, glob, button, buttons, Qt.NoModifier))
    QApplication.processEvents()


def _press_release(view, scene_pos):
    _send(view, scene_pos, (
        (QEvent.MouseMove, Qt.NoButton, Qt.NoButton, 0, 0),
        (QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton, 0, 0),
        (QEvent.MouseButtonRelease, Qt.LeftButton, Qt.NoButton, 0, 0)))


def _double_click(view, scene_pos, jitter=0):
    """按、放、雙擊、（手抖一個像素）、放 —— 使用者真的做的那一串。"""
    _send(view, scene_pos, (
        (QEvent.MouseMove, Qt.NoButton, Qt.NoButton, 0, 0),
        (QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton, 0, 0),
        (QEvent.MouseButtonRelease, Qt.LeftButton, Qt.NoButton, 0, 0),
        (QEvent.MouseButtonDblClick, Qt.LeftButton, Qt.LeftButton, 0, 0),
        (QEvent.MouseMove, Qt.NoButton, Qt.LeftButton, jitter, jitter),
        (QEvent.MouseButtonRelease, Qt.LeftButton, Qt.NoButton, jitter, jitter)))


def _inside(item):
    """卡片本體裡靠左上的一點（避開埠與邊緣）。"""
    r = item.sceneBoundingRect()
    return QPointF(r.left() + 30, r.top() + 14)


def _stray_window_spy(keep):
    """數**不是主視窗**的頂層 widget 被顯示了幾次。

    類別定義在函式裡：Qt 是 fixture 裡才 import 的（收集期不准碰 Qt，
    `tests/test_no_qt.py`），模組層沒有 `QObject` 這個名字。
    """
    class _Spy(QObject):
        def __init__(self):
            super().__init__()
            self.hits = []

        def eventFilter(self, obj, ev):  # Qt hook
            if ev.type() == QEvent.Show and isinstance(obj, QWidget) \
                    and obj.isWindow() and obj is not keep:
                self.hits.append(type(obj).__name__)
            return False

    return _Spy()


# --------------------------------------------------------------------------- #
# 1. 雙擊不跳空白視窗
# --------------------------------------------------------------------------- #
def test_double_clicking_a_card_opens_no_stray_windows(window, qapp):
    window.layout_modes.apply("tune")
    src = first_source(window)
    nid = window.add_card_after(src, "glv_stats")
    window.select_node(nid)                 # 面板先長出來（使用者前一下點過它）
    qapp.processEvents()
    item = window.pipeline.node_item(nid)

    spy = _stray_window_spy(window)
    qapp.installEventFilter(spy)
    try:
        _double_click(window.pipeline, _inside(item))
        qapp.processEvents()
    finally:
        qapp.removeEventFilter(spy)
    assert spy.hits == [], "雙擊跳出了空白視窗：%s" % spy.hits
    assert window.selected_node == nid


# --------------------------------------------------------------------------- #
# 2. 按在靠邊的卡上，卡不動、畫布不捲
# --------------------------------------------------------------------------- #
def test_pressing_a_card_at_the_edge_of_the_view_does_not_move_it(window, qapp):
    """反向驗過（2026-10-02）：把 `select_card` 換回「一律捲」，同一串事件讓卡片從
    (194, 100) 跑到 (557, 239) —— 前一下點在別張卡上是必要條件（Qt 拿上一次按下
    的位置算位移），所以這裡先點一下輸入卡。"""
    src = first_source(window)
    nid = window.add_card_after(src, "denoise")
    view = window.pipeline
    item = view.node_item(nid)
    _press_release(view, _inside(view.node_item(src)))     # 使用者的前一下
    # 把那張卡擺到剛好跨出視窗右緣的位置 —— `ensureVisible(80, 80)` 會想捲
    right_scene_x = view.mapToScene(view.viewport().width(), 0).x()
    w = item.sceneBoundingRect().width()
    item.setPos(right_scene_x - w * 0.5, item.pos().y())
    qapp.processEvents()
    before = (item.pos().x(), item.pos().y())
    hbar = view.horizontalScrollBar().value()

    _press_release(view, _inside(item))

    assert (item.pos().x(), item.pos().y()) == pytest.approx(before, abs=0.5), (
        "按一下（沒有移動滑鼠）卡片就跑了：%s → %s" % (before, item.pos()))
    assert view.horizontalScrollBar().value() == hbar, "按在卡上那一下不該捲動"
    assert window.selected_node == nid, "但要選到"


def test_selecting_from_elsewhere_still_scrolls_the_card_into_view(window, qapp):
    """反向：不是按在卡上的選取（Results、問題清單）照舊捲進視野。"""
    src = first_source(window)
    nid = window.add_card_after(src, "denoise")
    view = window.pipeline
    item = view.node_item(nid)
    item.setPos(view.mapToScene(view.viewport().width(), 0).x() + 400, item.pos().y())
    qapp.processEvents()
    hbar = view.horizontalScrollBar().value()
    window.select_node(nid)
    qapp.processEvents()
    assert view.horizontalScrollBar().value() != hbar


# --------------------------------------------------------------------------- #
# 3. 雙擊不重設分隔比例、不推走卡片（一般卡與 Decision 卡）
# --------------------------------------------------------------------------- #
def test_double_click_keeps_the_splitter_and_the_card_where_they_were(window, qapp):
    lay = window.layout_modes
    lay.apply("tune")
    src = first_source(window)
    nid = window.add_card_after(src, "denoise")
    qapp.processEvents()
    total = lay.total()
    lay.column.setSizes([int(total * 0.8), total - int(total * 0.8)])
    qapp.processEvents()
    sizes = list(lay.column.sizes())
    item = window.pipeline.node_item(nid)
    before = (item.pos().x(), item.pos().y())

    _double_click(window.pipeline, _inside(item), jitter=1)

    assert list(lay.column.sizes()) == sizes, "雙擊把使用者拖好的分隔比例重設了"
    assert (item.pos().x(), item.pos().y()) == pytest.approx(before, abs=0.5)
    assert lay.open is True


def test_double_clicking_the_decision_card_does_not_move_it(window, qapp):
    window.layout_modes.apply("tune")
    src = first_source(window)
    did = window.add_card_after(src, "decision")
    assert did == window.model.decision_node()
    item = window.pipeline.node_item(did)
    assert item is not None
    before = (item.pos().x(), item.pos().y())
    collapsed = window.pipeline.tree_collapsed()

    _double_click(window.pipeline, _inside(item), jitter=1)

    assert window.pipeline.tree_collapsed() is (not collapsed), "雙擊要真的切收合"
    assert (item.pos().x(), item.pos().y()) == pytest.approx(before, abs=0.5)
    # 放開之後卡片要能再拖（雙擊那一下關掉的可拖曳要回來）
    from PySide6.QtWidgets import QGraphicsItem
    assert bool(item.flags() & QGraphicsItem.ItemIsMovable)


def test_set_open_twice_keeps_the_user_splitter(window, qapp):
    lay = window.layout_modes
    lay.apply("tune")
    total = lay.total()
    lay.column.setSizes([int(total * 0.7), total - int(total * 0.7)])
    sizes = list(lay.column.sizes())
    assert lay.set_open(True) is True
    assert list(lay.column.sizes()) == sizes
