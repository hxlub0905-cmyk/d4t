"""F103（UI）：「Mark one cell…」與「Check on the image…」接進模板對話框。

核心那一層的承諾在 `tests/test_seed_period.py`；這裡盯的是接線：按了之後週期與原點
真的從那一格來、摘要講了「從你標的那一格」、格線檢視畫的是引擎真的用的那組格子。
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
from tests.test_seed_period import squares  # noqa: E402

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from d4t.core.algo import golden  # noqa: E402
from d4t.ui import crop_dialog as crop_mod  # noqa: E402
from d4t.ui import lattice_dialog as lat_mod  # noqa: E402
from d4t.ui import template_dialog as tpl_mod  # noqa: E402


# ---------------------------------------------------------------------------
# 1. 標一格
# ---------------------------------------------------------------------------
def test_the_seed_dialog_has_its_own_wording_and_no_whole_image_button(qapp):
    dlg = crop_mod.CropDialog(np.zeros((100, 100), np.uint8), mode=crop_mod.MODE_SEED)
    assert dlg.windowTitle() == "Mark one cell"
    assert dlg.btn_whole.isVisible() is False
    assert "draw one around one cell" in dlg.size_label.text()
    from PySide6.QtWidgets import QDialogButtonBox
    assert dlg.buttons.button(QDialogButtonBox.Ok).text() == "Use this as the cell"


def test_marking_a_cell_sets_the_period_and_the_origin_from_that_box(qapp, monkeypatch):
    dlg = tpl_mod.TemplateDialog()
    img = squares()                                 # 32 × 24，兩軸都有週期
    assert dlg.load_image(img, "grid.tif") is True
    assert dlg.btn_seed.isEnabled() and dlg.btn_lattice.isEnabled()
    monkeypatch.setattr(dlg, "_ask_seed", lambda image, name, initial: (37, 69, 32, 24))
    assert dlg._on_seed() is True
    assert dlg.seed() == (37, 69, 32, 24)
    gc = dlg.cell
    assert (gc.px, gc.py) == (32, 24)
    assert gc.origin == (37 % 32, 69 % 24) and gc.anchor == (0, 0)
    assert "period from the cell you marked" in dlg.summary()
    assert "copies found" in dlg.summary()
    assert "spacing agrees across 100%, down 100%" in dlg.summary()
    # 疊出來的 cell 就是他框的那一塊
    assert float(np.abs(img[69:93, 37:69] - gc.cell.astype(np.float32)).mean()) < 8.0


def test_restacking_keeps_the_marked_origin(qapp, monkeypatch):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(squares(), "grid.tif")
    monkeypatch.setattr(dlg, "_ask_seed", lambda *_a: (37, 69, 32, 24))
    dlg._on_seed()
    dlg.spin_cell_w.setValue(64)
    assert dlg.restack() is True
    assert dlg.seed() == (37, 69, 32, 24)
    assert dlg.cell.px == 64 and dlg.cell.origin == (37 % 64, 69 % 24)
    assert "period from the cell you marked" in dlg.summary()


def test_a_box_that_does_not_repeat_is_refused_with_the_reason(qapp, monkeypatch):
    dlg = tpl_mod.TemplateDialog()
    img = squares()
    img[:60, :] = np.random.default_rng(5).normal(120, 6, (60, img.shape[1]))
    dlg.load_image(img, "grid.tif")
    before = dlg.cell
    monkeypatch.setattr(dlg, "_ask_seed", lambda *_a: (5, 5, 30, 30))   # 雜訊區
    assert dlg._on_seed() is False
    assert "does not repeat" in dlg.report.text()
    assert dlg.cell is before                        # 什麼都不動
    assert dlg.seed() is None


def test_cancelling_and_a_template_from_the_recipe_cannot_mark_a_cell(qapp, monkeypatch):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "x.tif")
    monkeypatch.setattr(dlg, "_ask_seed", lambda *_a: False)
    assert dlg._on_seed() is False and dlg.seed() is None
    other = tpl_mod.TemplateDialog()
    assert other.load_encoded(dlg.encoded(), "x") is True
    assert other.btn_seed.isEnabled() is False and other.btn_lattice.isEnabled() is False
    assert other._on_seed() is False
    assert "Pick a full-size image first" in other.tool_hint.text()


def test_a_new_crop_forgets_the_seed(qapp, monkeypatch):
    """框是裁切後的座標；換一塊之後它指的地方不存在了。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(squares(), "grid.tif")
    monkeypatch.setattr(dlg, "_ask_seed", lambda *_a: (37, 69, 32, 24))
    dlg._on_seed()
    monkeypatch.setattr(dlg, "_ask_crop", lambda *_a: (0, 0, 160, 120))
    assert dlg._on_crop() is True
    assert dlg.seed() is None and dlg.crop() == (0, 0, 160, 120)


# ---------------------------------------------------------------------------
# 2. 格線鋪回原圖
# ---------------------------------------------------------------------------
def test_lattice_boxes_follow_the_engine_grid_and_cap_the_count():
    boxes, total = lat_mod.lattice_boxes((240, 320), 40, 240, (7, 0), (True, False))
    assert total == len(golden.tile_coords((240, 320), 40, 240, (7, 0))) == 7
    assert boxes[0] == (7 / 320, 0.0, 40 / 320, 1.0)
    boxes, total = lat_mod.lattice_boxes((1000, 1000), 10, 10, (0, 0), (True, True), cap=50)
    assert total == 10000 and len(boxes) == 50
    # 留的是離中心最近的
    cx = [b[0] + b[2] / 2 for b in boxes]
    assert all(abs(c - 0.5) < 0.06 for c in cx)


def test_the_check_view_draws_the_grid_the_template_uses(qapp):
    dlg = tpl_mod.TemplateDialog()
    img = big_image()
    dlg.load_image(img, "x.tif")
    view = dlg._on_lattice()
    assert view is not None and view.isVisible()
    gc = dlg.cell
    assert view.total == len(golden.tile_coords(img.shape, gc.px, gc.py, gc.origin))
    assert view.view.overlay_count() == view.total
    assert "%d px across (no period down)" % PERIOD in view.caption.text()
    assert "%d cells" % view.total in view.caption.text()
    # 改了尺寸再按：同一個視窗、新的格子
    dlg.spin_cell_w.setValue(PERIOD * 2)
    dlg.restack()
    again = dlg._on_lattice()
    assert again is view
    assert view.total == len(golden.tile_coords(img.shape, PERIOD * 2, 240, dlg.cell.origin))


def test_the_check_view_needs_an_image(qapp):
    dlg = tpl_mod.TemplateDialog()
    assert dlg._on_lattice() is None
    assert "Stack a template from an image first" in dlg.tool_hint.text()
