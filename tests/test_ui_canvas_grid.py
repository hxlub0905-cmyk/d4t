# 點陣底要說實話（F79）。
"""背景那層點以前是**純裝飾**，而它長得像對齊參考。

量出來的：間距 `GRID` 是 22，而版面用的是另外一組數字 —— 欄距
`NODE_W + COL_GAP` = 320（320 / 22 = 14.55）、列距「卡片高 + `ROW_GAP`」= 90
（90 / 22 = 4.09）。兩組都不整除，所以按了「排整齊」之後**卡片的角落落在點與
點之間，而且每一列偏移的量還不一樣**。

這不是「看起來差一點」的問題：畫布上唯一那個說「這裡有一套對齊」的東西，指的
是一套不存在的對齊。使用者說不出哪裡怪，只會說不夠俐落。

所以這個檔案問三件事：

1. **格線與版面是同一套**（欄距、列距都是 `GRID` 的倍數）—— 這是給下一個要改
   `NODE_W` / `COL_GAP` / `ROW_GAP` 的人的絆線。
2. **排出來的卡片真的落在點上**（自動排版與「排整齊」都算）。
3. **拖曳會吸附，`setPos` 不會** —— 後者是別的程式碼重現位置的路，量化它就
   不再是 identity。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from d4t.ui import canvas as canvas_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
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
    """開一份**有幾張卡**的畫布。

    F11 Enhance-4 之後開窗是空白畫布，而這一輪問的每一件事都要有卡片才問得
    出來 —— 接三張、拉兩條線，剛好夠出現「同一列」與「換行」兩種情況。
    """
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1200, 700)
    win.show()
    qapp.processEvents()
    src = first_source(win)
    prev = src
    for _ in range(3):
        nid = win.add_card_after(prev, "denoise")
        win._on_edge_added(prev, nid, "test")
        prev = nid
    qapp.processEvents()
    assert len(win.pipeline.node_ids()) >= 4
    yield win
    win.close()


def _on_grid(v):
    step = canvas_mod.GRID
    return abs(v / step - round(v / step)) < 1e-6


# --------------------------------------------------------------------------- #
# 1. 格線與版面是同一套（絆線）
# --------------------------------------------------------------------------- #
def test_the_column_pitch_is_a_whole_number_of_grid_cells(qapp):
    """**這條是給下一個改卡片尺寸的人的。**

    欄距是 `NODE_W + COL_GAP`。它一旦不是 `GRID` 的倍數，整張畫布的卡片就會
    一欄一欄地漂離點陣底 —— 而畫面上不會有任何錯誤，只會慢慢變得不整齊。
    """
    pitch = canvas_mod.NODE_W + canvas_mod.COL_GAP
    assert _on_grid(pitch), (
        "欄距 %g 不是 GRID(%g) 的倍數 —— 卡片會一欄一欄漂離點陣底"
        % (pitch, canvas_mod.GRID))


def test_a_row_of_cards_is_pushed_up_to_the_next_line_never_down(qapp):
    """列距是「這一列最高的卡 + 間距」，往下取整會讓最高那張貼到下一列去。"""
    step = canvas_mod.GRID
    for raw in (1.0, step - 0.5, step, step + 0.1, 3 * step, 90.0):
        out = canvas_mod.on_grid(raw)
        assert _on_grid(out), "on_grid(%g) = %g 不在格線上" % (raw, out)
        assert out >= raw, "on_grid(%g) = %g 往下取整了" % (raw, out)
        assert out - raw < step, "on_grid(%g) = %g 進位過頭" % (raw, out)


def test_the_background_dots_and_the_layout_read_the_same_number(window):
    """間距只能有一個家。

    以前背景讀的是 `PipelineCanvas.GRID`（22），而版面誰都沒讀 —— 兩套各自
    演化，於是「背景說的對齊」與「版面做的對齊」對不起來。
    """
    assert not hasattr(canvas_mod.PipelineCanvas, "GRID"), (
        "類別上又長出一個私有的 GRID —— 間距會再度分成兩份")
    assert window.pipeline._pitch is not None
    assert _on_grid(window.pipeline._pitch), (
        "列距 %g 不在格線上" % window.pipeline._pitch)


# --------------------------------------------------------------------------- #
# 2. 排出來的卡真的落在點上
# --------------------------------------------------------------------------- #
def test_every_card_the_layout_places_lands_on_a_dot(window):
    """自動排版（載入一份 recipe 就跑的那一次）。"""
    off = []
    for nid in window.pipeline.node_ids():
        pos = window.pipeline.node_item(nid).pos()
        if not (_on_grid(pos.x()) and _on_grid(pos.y())):
            off.append((nid, pos.x(), pos.y()))
    assert off == [], "這些卡的左上角不在點上：%s" % off


def test_tidy_up_puts_every_card_back_on_a_dot(window, qapp):
    """「排整齊」是使用者唯一會主動按的整理鍵 —— 按完必須真的整齊。"""
    from PySide6.QtCore import QPointF

    nid = window.pipeline.node_ids()[0]
    window.pipeline.node_item(nid).setPos(QPointF(137.0, 249.0))
    window.pipeline.tidy()
    qapp.processEvents()

    off = []
    for other in window.pipeline.node_ids():
        pos = window.pipeline.node_item(other).pos()
        if not (_on_grid(pos.x()) and _on_grid(pos.y())):
            off.append((other, pos.x(), pos.y()))
    assert off == [], "排整齊之後還有卡不在點上：%s" % off


# --------------------------------------------------------------------------- #
# 3. 拖曳會吸附，setPos 不會
# --------------------------------------------------------------------------- #
def _drag(view, item, dx, dy):
    """把一張卡從中心拖 ``(dx, dy)``（真的派送三顆滑鼠事件）。

    不能只設 `_dragging` 再 `setPos` —— 那樣驗的是旗標，不是使用者的動作，
    而這一輪要問的正好是「這一下是不是從手來的」。
    """
    vp = view.viewport()
    centre = item.scenePos() + QPointF(canvas_mod.NODE_W / 2.0,
                                       canvas_mod.NODE_H / 2.0)
    for etype, scene_pt, button, buttons in (
            (QEvent.MouseButtonPress, centre, Qt.LeftButton, Qt.LeftButton),
            (QEvent.MouseMove, centre + QPointF(dx, dy),
             Qt.NoButton, Qt.LeftButton),
            (QEvent.MouseButtonRelease, centre + QPointF(dx, dy),
             Qt.LeftButton, Qt.NoButton)):
        pt = QPointF(view.mapFromScene(scene_pt))
        glob = QPointF(vp.mapToGlobal(pt.toPoint()))
        QApplication.sendEvent(
            vp, QMouseEvent(etype, pt, glob, button, buttons, Qt.NoModifier))


def test_a_card_you_drag_lands_on_a_dot(window, qapp):
    """拖到哪都會吸到最近的點上 —— 那是點陣底存在的理由。"""
    view = window.pipeline
    nid = view.node_ids()[0]
    item = view.node_item(nid)
    before = item.pos()

    _drag(view, item, 37.0, 23.0)          # 刻意挑一個不在格線上的位移
    qapp.processEvents()

    after = item.pos()
    assert (after.x(), after.y()) != (before.x(), before.y()), \
        "卡片根本沒被拖動，這條測試沒有在測東西"
    assert _on_grid(after.x()) and _on_grid(after.y()), \
        "拖完停在 (%g, %g)，不在點上" % (after.x(), after.y())


def test_setting_a_position_in_code_is_kept_exactly(window):
    """**`setPos` 不准量化。**

    它是別的程式碼**重現**一個位置的路：彈出視窗要跟主畫布擺在一樣的地方、
    重建畫布要把使用者拖好的佈局放回去。那條路一旦量化就不再是 identity ——
    存 333 讀回 340、再存 340……每重建一次漂一格。這跟鐵則 9
    （`to_json_dict → from_json_dict` 必須是 identity）是同一種 bug，
    只是這裡漂的是像素不是分數。
    """
    from PySide6.QtCore import QPointF

    item = window.pipeline.node_item(window.pipeline.node_ids()[0])
    for _ in range(3):                      # 來回幾次：漂移是累積出來的
        item.setPos(QPointF(333.0, 444.0))
        assert (round(item.pos().x()), round(item.pos().y())) == (333, 444), \
            "setPos 被吸到格線上了：%s" % item.pos()
