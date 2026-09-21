"""`ui/pitch_helper.py` —— 丟一張圖進去，回答它的 cell period（F120）。

分兩半，而那不是為了整齊：

* **純函式那一半**（`axis_flags` / `px_text` / `nm_text` / `pitch_rows` /
  `lattice_periods`）不碰任何 widget，所以軸向 × 有沒有 nm × 量不量得到的排列
  組合可以各斷言一次，**不必為了讀一行字開一次視窗**；
* **視窗那一半**只驗接線：圖進得去、軸向改了畫面跟著改、格線畫得出來。

⚠ 這個檔案要 Qt，所以檔名是 `test_ui_*`（核心批在沒有 Qt 函式庫的機器上也要
綠 —— `tests/test_no_qt.py` 守著那一條）。
"""
from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture(scope="module")
def ph():
    """lazy import：收集期不准把 Qt 拉進來。"""
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from d4t.ui import pitch_helper
    return pitch_helper


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def tiles(px: int = 60, py: int = 44, w: int = 600, h: int = 480,
          seed: int = 3) -> np.ndarray:
    """直條 × 橫帶交叉的重複 layout（固定種子）。"""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    col = (x % px) < px * 0.42
    row = (y % py) < py * 0.5
    img = 55 + 55 * col + 45 * row + 40 * (col & row)
    return np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(np.uint8)


class _M:
    """假的 `MeasuredPeriod`（純函式那一半只讀這幾個欄位）。"""

    def __init__(self, px=60.0, py=44.0, conf_x=92.0, conf_y=93.0, stagger=0.0):
        self.px, self.py = px, py
        self.conf_x, self.conf_y = conf_x, conf_y
        self.stagger, self.notes = stagger, []


# --------------------------------------------------------------------------- #
# 1. 軸向：使用者說了算（使用者 2026-09-21「也能支援純 X 純 Y」）
# --------------------------------------------------------------------------- #
def test_auto_uses_both_axes_when_both_are_confident(ph):
    assert ph.axis_flags(ph.AXIS_AUTO, 60, 44, 92, 93) == (True, True)


def test_auto_drops_an_axis_it_is_not_confident_about(ph):
    """**「量到一個數字」不等於「真的有週期」** —— 純雜訊也會被找出一個假週期
    （實測信心 20 上下）。Auto 那一關就是為了它。"""
    assert ph.axis_flags(ph.AXIS_AUTO, 60, 44, 92, 20) == (True, False)


@pytest.mark.parametrize("axis,want", [("x", (True, False)), ("y", (False, True))])
def test_one_axis_only_cuts_one_way(ph, axis, want):
    assert ph.axis_flags(axis, 60, 44, 92, 93) == want


def test_an_explicit_axis_is_believed_even_when_the_confidence_is_low(ph):
    """使用者明講的一律相信 —— 同 `build_golden_cell` 的 ``given`` 規則。"""
    assert ph.axis_flags(ph.AXIS_X, 60, 44, 11, 93) == (True, False)
    assert ph.axis_flags(ph.AXIS_BOTH, 60, 44, 11, 12) == (True, True)


def test_an_explicit_axis_cannot_invent_a_period_that_was_never_measured(ph):
    """相信使用者 ≠ 變出一個沒有量到的數字。``p < 2`` 仍然是沒有。"""
    assert ph.axis_flags(ph.AXIS_BOTH, 60, 0, 90, 90) == (True, False)
    assert ph.axis_flags(ph.AXIS_X, 0, 44, 90, 90) == (False, False)


def test_an_axis_that_is_not_used_spans_the_whole_image(ph):
    """一維 layout：那一軸一格就是整張影像（同 `build_golden_cell`）。

    自己再發明一套的話，畫面上的格線跟引擎用的格子會差一個量。
    """
    assert ph.lattice_periods((480, 600), 60, 44, (True, False)) == (60.0, 480.0)
    assert ph.lattice_periods((480, 600), 60, 44, (False, True)) == (600.0, 44.0)


# --------------------------------------------------------------------------- #
# 2. 數字 → 字（px 是答案，nm 是換算）
# --------------------------------------------------------------------------- #
def test_a_fractional_period_keeps_its_decimal(ph):
    """79.5 對 79 在 4000 px 上差 25 px —— ``%d`` 會安靜截斷它。"""
    assert ph.px_text(79.5, True) == "79.5"
    assert ph.px_text(80.0, True) == "80"


def test_an_axis_the_user_switched_off_says_so_instead_of_going_blank(ph):
    """**那一軸其實量到了。** 藏起來的話使用者會以為它量不到，
    然後回頭去查一個不存在的問題。"""
    assert ph.px_text(44.0, False) == ph.PITCH_NOT_USED


def test_nothing_measured_is_a_dash_not_a_zero(ph):
    assert ph.px_text(0.0, True) == ph.PITCH_UNSET


def test_without_a_pixel_size_there_is_no_nanometre_column(ph):
    """⚠ **不是 `0 nm`** —— 那看起來像一個量出來的答案（`nm_per_px` 在 KLARF
    裡沒有來源，見 docs/FAB-VALIDATION.md 假設 #2）。"""
    assert ph.nm_text(60.0, True, 0.0) == ""


def test_with_a_pixel_size_the_nanometres_appear(ph):
    assert ph.nm_text(60.0, True, 2.5) == "150 nm"
    assert ph.nm_text(60.0, True, 20.0) == "1,200 nm"


def test_an_unused_axis_has_no_nanometres_either(ph):
    assert ph.nm_text(44.0, False, 2.5) == ""


def test_the_table_says_both_axes_and_their_confidence(ph):
    rows = ph.pitch_rows(_M(), ph.AXIS_AUTO, 2.5)
    assert [r[0] for r in rows] == ["Across (X)", "Down (Y)"]
    assert [r[1] for r in rows] == ["60", "44"]
    assert [r[2] for r in rows] == ["150 nm", "110 nm"]
    assert rows[0][3] == "92 / 100"


def test_the_table_follows_the_axis_choice(ph):
    rows = ph.pitch_rows(_M(), ph.AXIS_X, 2.5)
    assert rows[0][1] == "60" and rows[1][1] == ph.PITCH_NOT_USED
    # 信心那一欄**照樣講** —— 它量到了，只是你沒有用它。
    assert rows[1][3] == "93 / 100"


# --------------------------------------------------------------------------- #
# 3. 視窗：接線
# --------------------------------------------------------------------------- #
@pytest.fixture
def win(app, ph):
    w = ph.PitchHelperWindow()
    yield w
    w.close()


def test_it_opens_with_no_answer_rather_than_a_zero(win, ph):
    assert [r[1] for r in win.rows()] == [ph.PITCH_UNSET, ph.PITCH_UNSET]


def test_an_image_goes_in_and_the_pitch_comes_out(win, ph):
    """端到端（同步走一次，不用執行緒）：量到的要跟產生它的參數一樣。"""
    from d4t.core.algo import period as algo_period
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")           # ask_crop=False
    m = algo_template.measure_period(img)
    flags = ph.axis_flags(win.axis(), m.px, m.py, m.conf_x, m.conf_y)
    ux, uy = ph.lattice_periods(img.shape[:2], m.px, m.py, flags)
    origin = algo_period.choose_origin(img.shape, int(round(ux)), int(round(uy)),
                                       image=img)
    win._on_done(m, origin, "")

    assert [r[1] for r in win.rows()] == ["60", "44"]
    assert win.view.overlay_count() > 0, "格線要畫出來（預設開著）"


def test_switching_the_axis_redraws_the_grid_at_once(win, ph):
    """⚠ **這一條是一個真的 bug 的回歸測試**（F120，預覽時抓到）。

    第一版按下「X only」之後，表格立刻寫 `not used`，而圖上的**橫線還在**
    —— 重畫排在相位搜尋（好幾秒）後面。畫面同時在說兩件相反的事，
    而使用者會相信圖。
    """
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), (0.0, 0.0), "")
    both = win.view.overlay_count()

    win.chips_axis.set_text(ph.AXIS_X)
    win._on_axis(ph.AXIS_X)
    assert win.view.overlay_count() < both, (
        "切成 X only 之後格子數要變少（一格 = pitch × 整張高度）—— "
        "沒變表示格線還是上一個軸向的那一份")
    assert win.rows()[1][1] == ph.PITCH_NOT_USED


def test_hiding_the_grid_leaves_the_image_alone(win, ph):
    from d4t.core.algo import template as algo_template

    img = tiles()
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), (0.0, 0.0), "")
    win.chk_grid.setChecked(False)
    assert win.view.overlay_count() == 0
    assert win.view.has_image(), "藏格線不是藏圖"


def test_a_new_image_clears_the_previous_answer(win, ph):
    """**對著新圖顯示舊答案**是這個視窗最糟的失敗方式 —— 它只有一個輸出。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(algo_template.measure_period(img), (0.0, 0.0), "")
    assert win.rows()[0][1] == "60"

    win.set_image(tiles(px=30, py=30, seed=7), "b.tif")
    assert [r[1] for r in win.rows()] == [ph.PITCH_UNSET, ph.PITCH_UNSET]


def test_cropping_changes_which_pixels_are_measured(win, ph):
    """裁切不是裝飾：半邊 pitch 不同的圖，裁一半要給出不同的答案。"""
    from d4t.core.algo import template as algo_template

    left, right = tiles(px=40, w=400), tiles(px=24, w=400, seed=9)
    img = np.hstack([left, right])
    win.set_image(img, "two_halves.tif")
    win._crop = (0, 0, 400, img.shape[0])
    win._apply_crop()
    assert win._work.shape[1] == 400
    m = algo_template.measure_period(win._work)
    assert round(float(m.px)) == 40, "裁下來那一塊的 pitch 才是答案"


def test_the_notes_say_something_even_when_there_is_nothing_to_say(win, ph):
    """一個空框答不出「是沒問題，還是它根本沒跑？」—— 而那兩件事長得一樣。"""
    from d4t.core.algo import template as algo_template

    img = tiles()
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), (0.0, 0.0), "")
    assert win.notes.toPlainText().strip(), "沒有 note 的時候也要講一句"


def test_every_axis_chip_is_one_of_the_known_values(win, ph):
    """膠囊是從 `AXES` 長出來的，不是一張手寫的清單。"""
    for value in ph.AXES:
        assert win.chips_axis.chip(value) is not None
    assert set(ph.AXIS_LABELS) == set(ph.AXES) == set(ph.AXIS_HELP)
    assert len(ph.AXIS_ICONS) == len(ph.AXES)


def test_the_axis_icons_are_real_icons(ph):
    """打錯一個圖示名字的話那顆膠囊會是空的，而畫面上看起來只是「有點怪」。"""
    from d4t.ui import icons
    for name in ph.AXIS_ICONS:
        assert name in icons.GLYPH_ICONS, name


# --------------------------------------------------------------------------- #
# 4. 入口
# --------------------------------------------------------------------------- #
def test_the_cli_has_a_pitch_subcommand():
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "d4t" / "__main__.py"
    text = src.read_text(encoding="utf-8")
    assert 'add_parser("pitch"' in text
    assert "from d4t.ui.pitch_helper import run as pitch_run" in text


def test_the_crop_dialog_can_say_what_the_button_does(app):
    """`CropDialog` 的 OK 鈕不再寫死「Stack from this box」—— helper 不疊圖，
    那句話在這裡是假的（而分叉出第二個裁切對話框會讓「框怎麼變成像素」
    有兩個家）。"""
    from d4t.ui.crop_dialog import CropDialog
    from PySide6.QtWidgets import QDialogButtonBox

    d = CropDialog(tiles(), "x.tif", None, None, ok_text="Measure from this box")
    try:
        assert d.buttons.button(QDialogButtonBox.Ok).text() == "Measure from this box"
    finally:
        d.close()


def test_the_crop_dialog_still_defaults_to_the_template_wording(app):
    """反向：模板那條路一個字都沒變（原功能不動，F120 的前提）。"""
    from d4t.ui.crop_dialog import CropDialog
    from PySide6.QtWidgets import QDialogButtonBox

    d = CropDialog(tiles(), "x.tif", None, None)
    try:
        assert d.buttons.button(QDialogButtonBox.Ok).text() == "Stack from this box"
    finally:
        d.close()
