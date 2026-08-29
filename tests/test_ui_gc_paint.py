# -*- coding: utf-8 -*-
"""F61：在 Golden Cell 上畫出「缺陷可能在哪」。

使用者 2026-08-28：「不僅僅只是製造 inner spacer，而是使用者可以利用 GC 的
方式（**反正都是回推**），畫出 defect 可能在的位置，UI 去隨機產生。」

這一支守三件事，而**三件都是「畫面看起來對、位置其實錯」的形狀**：

1. **視窗座標 ↔ 影像座標**。中間隔著一個縮放倍率與一段置中的留白，弄錯的話
   使用者塗在 A 點、遮罩記在 B 點 —— 而畫面上兩者都紅紅的，看不出差別。
2. **拖快的時候中間要補起來**。滑鼠事件是離散的，只在事件位置蓋章的話畫出來
   是一串點，而使用者以為自己畫了一條線。
3. **遮罩住在 GC 座標系**，所以它跟著週期鋪出去 —— 那正是「回推」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

pytest.importorskip("PySide6")


def _import_qt(g):
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from d4t.ui import gc_paint, theme
    g.update(QApplication=QApplication, QMouseEvent=QMouseEvent, QEvent=QEvent,
             QPoint=QPoint, QPointF=QPointF, Qt=Qt, gp=gc_paint, theme=theme)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    yield app


@pytest.fixture
def view(qapp):
    v = gp.GcPaintView()
    v.resize(420, 260)
    v.set_gc(np.full((40, 60), 128, np.uint8))
    yield v
    v.deleteLater()


def _press(v, x, y):
    ox, oy = v.origin(); s = v.scale()
    pt = QPointF(ox + x * s, oy + y * s)
    e = QMouseEvent(QEvent.MouseButtonPress, pt, pt, Qt.LeftButton,
                    Qt.LeftButton, Qt.NoModifier)
    v.mousePressEvent(e)


def _move(v, x, y):
    ox, oy = v.origin(); s = v.scale()
    pt = QPointF(ox + x * s, oy + y * s)
    e = QMouseEvent(QEvent.MouseMove, pt, pt, Qt.LeftButton, Qt.LeftButton,
                    Qt.NoModifier)
    v.mouseMoveEvent(e)


def _release(v, x, y):
    ox, oy = v.origin(); s = v.scale()
    pt = QPointF(ox + x * s, oy + y * s)
    e = QMouseEvent(QEvent.MouseButtonRelease, pt, pt, Qt.LeftButton,
                    Qt.NoButton, Qt.NoModifier)
    v.mouseReleaseEvent(e)


# --------------------------------------------------------------------------- #
# 1. 座標
# --------------------------------------------------------------------------- #
def test_widget_coordinates_round_trip_to_image_coordinates(view):
    """每一個影像畫素的中心，換算回去要是它自己。"""
    ox, oy = view.origin()
    s = view.scale()
    h, w = 40, 60
    for y in range(0, h, 7):
        for x in range(0, w, 11):
            centre = QPoint(int(ox + (x + 0.5) * s), int(oy + (y + 0.5) * s))
            assert view.to_image(centre) == (x, y)


def test_a_click_outside_the_image_is_ignored(view):
    assert view.to_image(QPoint(0, 0)) is None or view.origin() == (0, 0)
    far = QPoint(view.width() + 50, view.height() + 50)
    assert view.to_image(far) is None
    before = view.painted_pixels()
    view.mousePressEvent(QMouseEvent(
        QEvent.MouseButtonPress, QPointF(far), QPointF(far), Qt.LeftButton,
        Qt.LeftButton, Qt.NoModifier))
    assert view.painted_pixels() == before


def test_the_stroke_lands_where_it_was_drawn(view):
    """畫在 (10, 5) 就要記在 (10, 5) —— 而不是差一個留白。"""
    view.set_radius(0)
    _press(view, 10, 5)
    _release(view, 10, 5)
    m = view.mask()
    assert m[5, 10]
    assert m.sum() == 1, "只按一下卻塗到 %d 個畫素" % m.sum()


# --------------------------------------------------------------------------- #
# 2. 拖快的時候
# --------------------------------------------------------------------------- #
def test_a_fast_drag_leaves_a_line_not_a_string_of_dots(view):
    """⚠ 滑鼠事件是離散的：兩次事件之間可以隔十幾個畫素。"""
    view.set_radius(0)
    _press(view, 5, 5)
    _move(view, 35, 5)              # 一口氣跳 30 個畫素
    _release(view, 35, 5)
    m = view.mask()
    assert m[5, 5:36].all(), "中間斷掉了 —— 畫出來是一串點不是一條線"
    assert not m[5, 4] and not m[5, 36]


def test_erase_takes_it_back(view):
    view.set_radius(1)
    _press(view, 20, 20); _release(view, 20, 20)
    assert view.painted_pixels() > 0
    view.set_mode(gp.MODE_ERASE)
    _press(view, 20, 20); _release(view, 20, 20)
    assert view.painted_pixels() == 0


def test_a_rectangle_fills_its_whole_area(view):
    view.set_mode(gp.MODE_RECT)
    _press(view, 10, 10)
    _move(view, 19, 14)
    _release(view, 19, 14)
    m = view.mask()
    assert m[10:15, 10:20].all()
    assert m.sum() == 5 * 10


# --------------------------------------------------------------------------- #
# 3. 遮罩本身
# --------------------------------------------------------------------------- #
def test_changing_the_gc_clears_the_mask(view):
    """換了圖案，畫在舊圖案上的位置沒有意義 —— 留著它比清掉更糟。"""
    _press(view, 10, 10); _release(view, 10, 10)
    assert view.painted_pixels() > 0
    view.set_gc(np.zeros((30, 30), np.uint8))
    assert view.painted_pixels() == 0
    assert view.mask().shape == (30, 30)


def test_the_mask_is_a_copy_not_the_live_array(view):
    """外面改到回傳的那一份，不可以動到畫布裡的。"""
    _press(view, 3, 3); _release(view, 3, 3)
    m = view.mask()
    m[:] = True
    assert view.painted_pixels() < m.size


def test_seeding_from_the_auto_sites_paints_them(view):
    n = view.seed_from_sites([(5, 5), (50, 30)], radius=1)
    assert n == 2 * 9                     # 兩個 3×3
    assert view.mask()[5, 5] and view.mask()[30, 50]


def test_a_mask_of_the_wrong_shape_is_refused(view):
    assert view.set_mask(np.ones((7, 7), bool)) is False
    assert view.painted_pixels() == 0


# --------------------------------------------------------------------------- #
# 4. 回推：遮罩 → 落點
# --------------------------------------------------------------------------- #
def test_the_mask_becomes_the_candidate_sites(view):
    """畫布與 backend 之間的介面只有這一句話（`sites_from_mask`）。"""
    import make_lot_from_gc as gcl

    view.set_mode(gp.MODE_RECT)
    _press(view, 10, 10)
    _move(view, 12, 11)
    _release(view, 12, 11)
    sites = gcl.sites_from_mask(view.mask())
    assert sorted(sites) == sorted(
        [(x, y) for x in range(10, 13) for y in range(10, 12)])


def test_painting_more_makes_that_area_more_likely(view):
    """塗得大 = 被抽中的機會高。**不必另外做權重**，那是逐畫素抽樣的性質。"""
    import make_lot_from_gc as gcl

    view.set_mode(gp.MODE_RECT)
    _press(view, 0, 0); _move(view, 9, 9); _release(view, 9, 9)      # 100 px
    _press(view, 40, 30); _move(view, 41, 30); _release(view, 41, 30)  # 2 px
    sites = gcl.sites_from_mask(view.mask())
    big = len([1 for x, y in sites if x < 10 and y < 10])
    assert big == 100 and len(sites) == 102
