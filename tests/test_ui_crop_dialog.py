"""F102：疊模板之前先框一塊（`ui/crop_dialog.py` ＋ `TemplateDialog` 的接線）。

使用者 2026-09-17：「載入 template 的大圖，可以選擇要不要 crop 想要的部分之後再
進行計算」。這裡盯三件事：框拉出來就是那幾個像素（座標不會偏）、疊進去的**只有**
那一塊、以及「從哪一塊疊的」有攤在摘要上。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_ui_template_dialog import (  # noqa: E402,F401 — qapp 是 fixture
    PERIOD, _move, _press, _release, big_image, qapp,
)

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from d4t.ui import crop_dialog as crop_mod  # noqa: E402
from d4t.ui import template_dialog as tpl_mod  # noqa: E402


# ---------------------------------------------------------------------------
# 1. 純函式：框 → 像素
# ---------------------------------------------------------------------------
def test_crop_array_cuts_exactly_that_box_and_clamps_to_the_image():
    img = np.arange(20 * 30, dtype=np.uint8).reshape(20, 30)
    assert crop_mod.crop_array(img, None) is img
    sub = crop_mod.crop_array(img, (5, 2, 10, 8))
    assert sub.shape == (8, 10) and sub[0, 0] == img[2, 5]
    assert crop_mod.crop_array(img, (25, 15, 100, 100)).shape == (5, 5)
    assert crop_mod.crop_array(img, (40, 40, 5, 5)).shape == (20, 30)   # 全在外面＝沒裁


def test_clamp_rect_drops_a_box_too_small_to_mean_anything():
    assert crop_mod.clamp_rect((0, 0, 3, 3), (100, 100)) is None
    assert crop_mod.clamp_rect((-5, -5, 20, 20), (100, 100)) == (0, 0, 15, 15)
    assert crop_mod.clamp_rect((90, 90, 50, 50), (100, 100)) == (90, 90, 10, 10)


# ---------------------------------------------------------------------------
# 2. 畫布：拉的框就是那幾個影像像素
# ---------------------------------------------------------------------------
def _pt(x, y):
    from PySide6.QtCore import QPointF
    return QPointF(float(x), float(y))


def _view(qapp, shape=(240, 320)):
    v = crop_mod.CropView()
    v.resize(shape[1], shape[0])            # 1:1，座標不用換算
    v.set_image(np.zeros(shape, np.uint8))
    return v


def test_a_dragged_box_lands_on_those_image_pixels(qapp):
    v = _view(qapp)
    got = []
    v.rect_changed.connect(got.append)
    _press(v, _pt(10, 20)); _move(v, _pt(60, 50)); _release(v, _pt(110, 80))
    assert v.box() == (10, 20, 100, 60)
    assert got[-1] == (10, 20, 100, 60)


def test_dragging_backwards_and_off_the_edge_still_gives_a_box(qapp):
    v = _view(qapp)
    _press(v, _pt(300, 200)); _release(v, _pt(-40, -40))
    assert v.box() == (0, 0, 300, 200)


def test_a_click_without_a_drag_is_not_a_box(qapp):
    v = _view(qapp)
    _press(v, _pt(50, 50)); _release(v, _pt(52, 51))
    assert v.box() is None


def test_the_dialog_answers_box_whole_or_nothing(qapp):
    dlg = crop_mod.CropDialog(np.zeros((240, 320), np.uint8), "big.tif")
    from PySide6.QtWidgets import QDialog, QDialogButtonBox
    ok = dlg.buttons.button(QDialogButtonBox.Ok)
    assert ok.isEnabled() is False                  # 沒框不能「從這一塊疊」
    assert "whole image" in dlg.size_label.text()
    dlg.view.set_box((10, 10, 100, 50))
    assert ok.isEnabled() is True
    assert dlg.size_label.text() == "Box 100 x 50 px at (10, 10)"
    assert dlg.box() == (10, 10, 100, 50)
    dlg._on_whole()
    assert dlg.box() is None and dlg.result() == QDialog.Accepted


# ---------------------------------------------------------------------------
# 3. 模板對話框：疊進去的只有那一塊，而且摘要說了
# ---------------------------------------------------------------------------
def _image_with_junk_on_the_right() -> np.ndarray:
    img = big_image()
    img[:, PERIOD * 4:] = np.random.default_rng(3).normal(120, 6, (240, PERIOD * 4))
    return img


def test_the_crop_is_what_gets_stacked_and_the_summary_says_so(qapp):
    dlg = tpl_mod.TemplateDialog()
    assert dlg.load_image(_image_with_junk_on_the_right(), "LOT_full.tif",
                          crop=(0, 0, PERIOD * 4, 240)) is True
    assert dlg.crop() == (0, 0, PERIOD * 4, 240)
    assert dlg._source.shape == (240, PERIOD * 4)          # 疊的是那一塊
    assert dlg._full.shape == (240, PERIOD * 8)            # 原料還在
    assert "cell %d" % PERIOD in dlg.summary()
    assert "cropped to %d x 240 px at (0, 0)" % (PERIOD * 4) in dlg.summary()
    assert "cropped" in dlg.path_label.text()
    assert dlg.btn_crop.isEnabled() is True


def test_a_box_covering_the_whole_image_is_no_crop(qapp):
    dlg = tpl_mod.TemplateDialog()
    assert dlg.load_image(big_image(), "x.tif", crop=(0, 0, 10000, 10000)) is True
    assert dlg.crop() is None
    assert "cropped" not in dlg.summary()


def test_restacking_keeps_the_crop(qapp):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(_image_with_junk_on_the_right(), "x.tif", crop=(0, 0, PERIOD * 4, 240))
    dlg.spin_cell_w.setValue(PERIOD * 2)
    assert dlg.restack() is True
    assert dlg.crop() == (0, 0, PERIOD * 4, 240)
    assert dlg._source.shape == (240, PERIOD * 4)
    assert "cell %d" % (PERIOD * 2) in dlg.summary()


def test_crop_first_asks_before_stacking_and_cancel_changes_nothing(qapp, monkeypatch):
    dlg = tpl_mod.TemplateDialog()
    asked = []
    answers = iter([False, (0, 0, PERIOD * 4, 240), None])
    monkeypatch.setattr(dlg, "_ask_crop",
                        lambda img, name, initial: (asked.append(initial), next(answers))[1])
    img = _image_with_junk_on_the_right()

    dlg.chk_crop.setChecked(False)
    assert dlg.take_image(img, "x.tif") is True         # 沒勾：不問，整張疊
    assert asked == [] and dlg.crop() is None

    dlg.chk_crop.setChecked(True)
    assert dlg.take_image(img, "x.tif") is False        # 取消：什麼都不動
    assert asked == [None] and dlg.crop() is None and "Cancelled" in dlg.report.text()
    assert dlg.take_image(img, "x.tif") is True         # 框了：疊那一塊
    assert dlg.crop() == (0, 0, PERIOD * 4, 240)
    # 事後再按 Crop…：帶著上一個框去問；回「整張」就回到整張
    assert dlg._on_crop() is True
    assert asked[-1] == (0, 0, PERIOD * 4, 240) and dlg.crop() is None


def test_a_template_read_back_from_the_recipe_cannot_be_cropped(qapp):
    src = tpl_mod.TemplateDialog()
    src.load_image(big_image(), "x.tif")
    dlg = tpl_mod.TemplateDialog()
    assert dlg.load_encoded(src.encoded(), "x") is True
    assert dlg.btn_crop.isEnabled() is False
    assert dlg._on_crop() is False
    assert "Pick a full-size image first" in dlg.tool_hint.text()


# ---------------------------------------------------------------------------
# 6. 真的畫一次（2026-09-17 使用者回報：還沒拉框就 `fillRect(None)` 炸）
# ---------------------------------------------------------------------------
def _paints(widget) -> None:
    """逼 Qt 走一次 `paintEvent`（headless 下 `show()` 不會畫，`grab()` 會）。"""
    widget.resize(320, 240)
    pm = widget.grab()
    assert not pm.isNull()


def test_the_crop_view_paints_with_no_image_no_box_and_a_box(qapp):
    v = crop_mod.CropView()
    _paints(v)                                       # 沒有圖
    v.set_image(np.zeros((240, 320), np.uint8))
    _paints(v)                                       # 有圖、還沒拉框（炸的那個情形）
    v.set_box((10, 10, 50, 50))
    _paints(v)                                       # 有框
    assert v.rect().width() == 320                   # Qt 自己的 rect() 沒被蓋掉


def test_the_dialogs_paint(qapp):
    _paints(crop_mod.CropDialog(np.zeros((240, 320), np.uint8), "x.tif"))
    _paints(crop_mod.CropDialog(np.zeros((240, 320), np.uint8), "x.tif",
                                mode=crop_mod.MODE_SEED))
    from d4t.ui import lattice_dialog as lat_mod
    _paints(lat_mod.LatticeDialog(np.zeros((240, 320), np.uint8), 40, 240, (7, 0),
                                  (True, False)))
