"""F104（UI）：「Grid」開關 —— 把引擎真的用的格線鋪回原圖、可開可關。

使用者 2026-09-17：「Check on the image 改成類似格線的開關按鈕，可以開啟顯示或關閉
顯示格線」。盯三件事：畫的是引擎那組格子、開關兩個方向都動、視窗自己關掉開關要彈回。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_ui_template_dialog import (  # noqa: E402,F401 — qapp 是 fixture
    PERIOD, big_image, qapp,
)

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from d4t.core.algo import golden  # noqa: E402
from d4t.ui import lattice_dialog as lat_mod  # noqa: E402
from d4t.ui import template_dialog as tpl_mod  # noqa: E402


def test_lattice_boxes_follow_the_engine_grid_and_cap_the_count():
    boxes, total = lat_mod.lattice_boxes((240, 320), 40, 240, (7, 0), (True, False))
    assert total == len(golden.tile_coords((240, 320), 40, 240, (7, 0))) == 7
    assert boxes[0] == (7 / 320, 0.0, 40 / 320, 1.0)
    boxes, total = lat_mod.lattice_boxes((1000, 1000), 10, 10, (0, 0), (True, True), cap=50)
    assert total == 10000 and len(boxes) == 50
    cx = [b[0] + b[2] / 2 for b in boxes]
    assert all(abs(c - 0.5) < 0.06 for c in cx)          # 留的是離中心最近的


def test_the_toggle_is_off_and_disabled_until_a_template_is_stacked(qapp):
    dlg = tpl_mod.TemplateDialog()
    assert dlg.btn_grid.isCheckable() and not dlg.btn_grid.isEnabled()
    assert dlg.grid_window() is None
    dlg.load_image(big_image(), "x.tif")
    assert dlg.btn_grid.isEnabled() and not dlg.btn_grid.isChecked()
    assert dlg.grid_window() is None                     # 沒開就不建


def test_switching_on_shows_the_engine_grid_and_off_hides_it(qapp):
    dlg = tpl_mod.TemplateDialog()
    img = big_image()
    dlg.load_image(img, "x.tif")
    dlg.btn_grid.setChecked(True)
    win = dlg.grid_window()
    assert win is not None and win.isVisible()
    gc = dlg.cell
    assert win.total == len(golden.tile_coords(img.shape, gc.px, gc.py, gc.origin))
    assert win.view.overlay_count() == win.total
    assert "%d px across (no period down)" % PERIOD in win.caption.text()
    dlg.btn_grid.setChecked(False)
    assert not win.isVisible()
    dlg.btn_grid.setChecked(True)
    assert win.isVisible() and dlg.grid_window() is win  # 同一個視窗，不重建


def test_restacking_updates_the_grid_while_it_is_on(qapp):
    dlg = tpl_mod.TemplateDialog()
    img = big_image()
    dlg.load_image(img, "x.tif")
    dlg.btn_grid.setChecked(True)
    win = dlg.grid_window()
    dlg.spin_cell_w.setValue(PERIOD * 2)
    dlg.restack()
    assert win.total == len(golden.tile_coords(img.shape, PERIOD * 2, 240, dlg.cell.origin))


def test_closing_the_window_flips_the_toggle_back(qapp):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "x.tif")
    dlg.btn_grid.setChecked(True)
    win = dlg.grid_window()
    win.reject()                                          # Close／Esc
    assert not dlg.btn_grid.isChecked()
    dlg.btn_grid.setChecked(True)
    win.close()                                           # ✕
    assert not dlg.btn_grid.isChecked()


def test_a_template_read_back_from_the_recipe_has_no_grid(qapp):
    src = tpl_mod.TemplateDialog()
    src.load_image(big_image(), "x.tif")
    dlg = tpl_mod.TemplateDialog()
    assert dlg.load_encoded(src.encoded(), "x") is True
    assert not dlg.btn_grid.isEnabled() and not dlg.btn_grid.isChecked()


def test_the_grid_window_paints(qapp):
    win = lat_mod.LatticeDialog(np.zeros((240, 320), np.uint8), 40, 240, (7, 0),
                                (True, False))
    win.resize(320, 240)
    assert not win.grab().isNull()
