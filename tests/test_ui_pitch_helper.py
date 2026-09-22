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


def stacked(img, px=None, py=None):
    """疊一次 —— 測試裡同步跑（`_on_done` 吃的就是這個東西）。"""
    from d4t.core.algo import template as algo_template
    if px is None:
        m = algo_template.measure_period(img)
        px, py = m.px, m.py
    return algo_template.build_golden_cell(img, px=float(px), py=float(py))


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
def test_the_three_chips_are_x_plus_y_x_and_y(ph):
    """使用者 2026-09-21：「我覺得就分 X+Y 跟 X 跟 Y 就好」。

    ⚠ `Auto` 上一輪才剛因為「Auto 跟 X+Y 差在哪裡？」被改名成
    `Force both` —— **而一個要靠改名才講得清楚的差別，多半是那個差別不該
    存在**。預設是兩軸都切。
    """
    assert ph.AXES == (ph.AXIS_BOTH, ph.AXIS_X, ph.AXIS_Y)
    assert not hasattr(ph, "AXIS_AUTO"), "拿掉就是拿掉，不留一個沒人按的常數"
    assert ph.AXIS_LABELS[ph.AXIS_BOTH] == "X + Y"
    assert len(ph.AXIS_ICONS) == len(ph.AXES)


def test_every_chip_trusts_what_the_user_picked(ph):
    """三顆都跳過信心那一關 —— 使用者明講的一律相信。"""
    weak = _M(conf_x=11.0, conf_y=9.0)
    assert ph.axis_flags(ph.AXIS_BOTH, weak.px, weak.py, weak.conf_x, weak.conf_y) == (True, True)
    assert ph.axis_flags(ph.AXIS_X, weak.px, weak.py, weak.conf_x, weak.conf_y) == (True, False)
    assert ph.axis_flags(ph.AXIS_Y, weak.px, weak.py, weak.conf_x, weak.conf_y) == (False, True)


def test_a_period_that_was_never_measured_is_still_not_invented(ph):
    """⚠ 相信使用者**不等於變出一個數字**。

    純雜訊實測回 ``px=0``（`estimate_period` 自己的
    ``strength_threshold`` 在信心 ~18 就擋下來了）—— 拿掉 `Auto` 之後
    擋住雜訊的就是這一道，而它是引擎自己的。
    """
    assert ph.axis_flags(ph.AXIS_BOTH, 0.0, 0.0) == (False, False)
    assert ph.axis_flags(ph.AXIS_X, 1.0, 44.0) == (False, False), "比 2 px 還小就是沒有"

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


def test_without_a_pixel_size_there_is_no_real_world_column(ph):
    """⚠ **不是 `0 µm`** —— 那看起來像一個量出來的答案（`nm_per_px` 在 KLARF
    裡沒有來源，見 docs/FAB-VALIDATION.md 假設 #2）。"""
    assert ph.nm_text(60.0, True, 0.0) == ""


def test_the_converted_pitch_is_in_micrometres(ph):
    """⚠ **輸入是 nm/px，輸出是 µm**（使用者 2026-09-21：「pixel size
    換算後，單位改成 um（px 輸入一樣是 nm）」）。

    兩個單位不同不是不一致，是**兩邊各自的量級**：pixel size 是個位數的
    nm，而一個 cell 的 pitch 是幾百個 nm —— 寫成 `1,200 nm` 要數逗號，
    寫成 `1.200 µm` 不用。
    """
    assert ph.nm_text(60.0, True, 2.5) == "0.150 µm"
    assert ph.nm_text(60.0, True, 20.0) == "1.200 µm"


def test_an_unused_axis_has_no_converted_pitch_either(ph):
    assert ph.nm_text(44.0, False, 2.5) == ""


def test_the_table_says_both_axes_and_their_confidence(ph):
    rows = ph.pitch_rows(_M(), ph.AXIS_BOTH, 2.5)
    assert [r[0] for r in rows] == ["Across (X)", "Down (Y)"]
    assert [r[1] for r in rows] == ["60", "44"]
    assert [r[2] for r in rows] == ["0.150 µm", "0.110 µm"]
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
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")           # ask_crop=False
    m = algo_template.measure_period(img)
    flags = ph.axis_flags(win.axis(), m.px, m.py, m.conf_x, m.conf_y)
    ux, uy = ph.lattice_periods(img.shape[:2], m.px, m.py, flags)
    win._on_done(m, stacked(img, ux, uy), "")

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
    # ⚠ **要給一個真的 GoldenCell。** `gc=None` 是「週期量到了、相位還沒」
    # 那個中間狀態（F120 第十七輪：答案先上畫面、證據隨後），而那一刻**格線
    # 是不畫的** —— 畫在相位 0 上再跳掉是最糟的一種。這一條要測的是「改了軸向
    # 之後格線當場重畫」，走的是既有相位那條路，所以它需要一個相位。
    win._on_done(*_run(win, img), "")
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
    win._on_done(algo_template.measure_period(img), None, "")
    win.chk_grid.setChecked(False)
    assert win.view.overlay_count() == 0
    assert win.view.has_image(), "藏格線不是藏圖"


def test_a_new_image_clears_the_previous_answer(win, ph):
    """**對著新圖顯示舊答案**是這個視窗最糟的失敗方式 —— 它只有一個輸出。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(algo_template.measure_period(img), None, "")
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


def test_a_clean_measurement_shows_no_warning_strip_at_all(win, ph):
    """⚠ **這一條換了方向**（使用者 2026-09-21：「What it decided 這我不知道
    可以幹嘛？」）。

    第一版有一塊常駐的面板，而最常見的情形是它空著 —— 所以它教會使用者不要
    看它，而真的有話要說的那一天他也不會看。現在沒有話就整條不佔位置。
    """
    from d4t.core.algo import template as algo_template

    img = tiles()
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), None, "")
    assert not win.warn.isVisibleTo(win), "乾淨的量測不該有警告條"
    assert win.warn.text() == ""


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


# --------------------------------------------------------------------------- #
# 5. 「如果算錯了怎麼辦」—— 量出來的週期是預設值，不是結論
#    （使用者 2026-09-21 問的第 1 題後半。`template_dialog` 早就定了這句話，
#     而 helper 更需要它：這個視窗的唯一輸出就是那個數字。）
# --------------------------------------------------------------------------- #
def test_without_an_override_the_measured_period_is_what_is_used(ph):
    assert ph.effective_period(_M(60.0, 44.0)) == (60.0, 44.0)


def test_a_typed_period_wins(ph):
    assert ph.effective_period(_M(60.0, 44.0), (120.0, None)) == (120.0, 44.0)
    assert ph.effective_period(_M(60.0, 44.0), (120.0, 88.0)) == (120.0, 88.0)


def test_a_typed_period_does_not_borrow_the_measured_confidence(ph):
    """⚠ **這一條是誠實問題，不是排版問題。**

    信心量的是「把圖平移**量到的那個週期**之後跟自己有多像」。使用者把 60
    改成 120 之後還掛著 92/100，等於拿一個他沒問過的問題的答案，去背書他剛
    打進去的數字。
    """
    rows = ph.pitch_rows(_M(), ph.AXIS_BOTH, 0.0, (120.0, None))
    assert rows[0][1] == "120"
    assert rows[0][3] != "92 / 100", "不准沿用量到的那個分數"
    assert rows[1][3] == "93 / 100", "沒改的那一軸照樣講它量到的信心"


def test_a_typed_period_with_no_score_says_so_instead_of_faking_one(ph):
    """還算不出分數的時候（還沒載圖）寫 ``yours``，**不寫 0**。"""
    rows = ph.pitch_rows(_M(), ph.AXIS_BOTH, 0.0, (120.0, None), (None, None))
    assert rows[0][3] == ph.CONF_TYPED


def test_a_typed_period_gets_its_own_score_when_there_is_one(ph):
    """使用者 2026-09-21：「自定義 period 右上可否也能算 confidence？」

    可以 —— 但那是**對他打的那個數字重問一次**的分數（`confidence_at`），
    不是量出來那個數字的分數。
    """
    rows = ph.pitch_rows(_M(), ph.AXIS_BOTH, 0.0, (120.0, None), (41.0, None))
    assert rows[0][3] == "41 / 100"


def test_a_typed_period_is_believed_even_where_the_measurement_was_not(ph):
    """使用者明講的一律相信 —— 否則畫面上會變成「我改了，但它不理我」。"""
    rows = ph.pitch_rows(_M(px=60.0, conf_x=11.0), ph.AXIS_BOTH, 0.0, (60.0, None))
    assert rows[0][1] == "60", "信心 11 但他自己打的，就該用"


def test_a_typed_period_is_converted_too(ph):
    rows = ph.pitch_rows(_M(), ph.AXIS_BOTH, 2.5, (120.0, None))
    assert rows[0][2] == "0.300 µm"


def test_typing_a_period_redraws_the_grid_at_once(win, ph):
    """同軸向那一條：**不能等相位搜尋回來**（見 `_on_override`）。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")
    # ⚠ **要給一個真的 GoldenCell。** `gc=None` 是「週期量到了、相位還沒」
    # 那個中間狀態（F120 第十七輪：答案先上畫面、證據隨後），而那一刻**格線
    # 是不畫的** —— 畫在相位 0 上再跳掉是最糟的一種。這一條要測的是「改了軸向
    # 之後格線當場重畫」，走的是既有相位那條路，所以它需要一個相位。
    win._on_done(*_run(win, img), "")
    before = win.view.overlay_count()

    win.spin_px.setValue(120.0)          # 一格變兩倍寬 → 格子數要變少
    assert win.rows()[0][1] == "120"
    assert win.view.overlay_count() < before


def test_the_double_button_doubles_both_axes(win, ph):
    """使用者的真實情境：「兩根 MG 才構成他要比的那個單元」。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), None, "")
    win._on_double()
    assert [r[1] for r in win.rows()] == ["120", "88"]


def test_reset_puts_the_measured_period_back(win, ph):
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), None, "")
    win._on_double()
    win._on_reset()
    assert [r[1] for r in win.rows()] == ["60", "44"]
    assert win.override() == (None, None)


def test_the_screen_says_when_the_number_is_not_the_measured_one(win, ph):
    """**改過了一定要看得到。** 少了這一句，換一張圖之後還掛著上一次打的 120，
    而畫面上沒有任何東西說那是他自己打的。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), None, "")
    assert win.warn.text() == "", "沒改過就不該有這一條"

    win.spin_px.setValue(120.0)
    said = win.warn.text()
    assert "120" in said and "60" in said, "要同時講你打的與它量的：%r" % said
    assert win.warn.isVisibleTo(win)


def test_the_table_the_notes_and_the_grid_all_ask_the_same_question(win, ph):
    """三個地方各算一次 flags 的話，會出現「表格說 Y 沒在用、格線卻切了橫線」
    —— 這個視窗已經被那種形狀咬過一次（`_on_axis` 的回歸測試）。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")
    # ⚠ **要給一個真的 GoldenCell。** `gc=None` 是「週期量到了、相位還沒」
    # 那個中間狀態（F120 第十七輪：答案先上畫面、證據隨後），而那一刻**格線
    # 是不畫的** —— 畫在相位 0 上再跳掉是最糟的一種。這一條要測的是「改了軸向
    # 之後格線當場重畫」，走的是既有相位那條路，所以它需要一個相位。
    win._on_done(*_run(win, img), "")
    win.chips_axis.set_text(ph.AXIS_Y)
    win._on_axis(ph.AXIS_Y)

    assert win._flags() == (False, True)
    assert win.rows()[0][1] == ph.PITCH_NOT_USED
    # **畫出來的格線要跟表格說的那一軸對得上** —— 兩邊各算各的那天，畫面
    # 會同時說兩件事。X 沒在用 ⇒ 一格 = 整張寬，只切橫線。
    #
    # ⚠ 這裡**不數格子**：`Skip edge cells` 會把外圈修掉（`_draw` 只畫真的
    # 疊進去的那一批），所以 `480 // 44` 那個沒有修邊的舊算式會紅，而紅的是
    # 算式不是行為。數量不是不變量，**格子的形狀才是**。
    boxes = win.view.overlay_rects()
    assert len(boxes) > 1, "Y 在用，卻沒切出橫線"
    assert all(abs(b[0]) < 1e-6 and abs(b[2] - 1.0) < 1e-6 for b in boxes), \
        "X 說沒在用，格線卻切了直線：%r" % (boxes[:3],)
    assert all(abs(b[3] * 480 - 44) < 1.0 for b in boxes), \
        "橫線的間距不是量到的 Y 週期：%r" % (boxes[:3],)


# --------------------------------------------------------------------------- #
# 6. 疊起來看（使用者 2026-09-21 指定的證明方式）＋ 綠黃紅的橫條
# --------------------------------------------------------------------------- #
def test_the_confidence_bar_is_green_amber_red(ph):
    """實測刻度：純雜訊 ≈ 20、真的有週期 ≈ 87–98，而 40 以下引擎自己就不採用。"""
    assert ph.conf_tone(92) == ph.TONE_GOOD
    assert ph.conf_tone(60) == ph.TONE_WARN
    assert ph.conf_tone(20) == ph.TONE_BAD


def test_the_agreement_bar_uses_the_same_threshold_as_the_template_path(ph):
    """⚠ **同一個門檻，同一個家。** 模板那條路說「低於 `BLURRED_BELOW` 就是
    糊的」，helper 沒有理由對同一件事說另一個數字。"""
    from d4t.ui.template_dialog import BLURRED_BELOW

    assert ph.agree_tone(0.93) == ph.TONE_GOOD
    assert ph.agree_tone(BLURRED_BELOW) == ph.TONE_WARN
    assert ph.agree_tone(BLURRED_BELOW - 0.01) == ph.TONE_BAD


def test_the_bar_always_carries_the_number_too(app, ph):
    """U13：**顏色不是唯一的通道** —— 紅綠色覺缺陷者看不出顏色差別，而這一條
    是「這個答案可不可信」唯一的一眼答案。"""
    bar = ph.Bar()
    try:
        bar.set_value(0.92, ph.TONE_GOOD, "92")
        assert bar.value_text() == "92"
        assert bar.tone() == ph.TONE_GOOD
    finally:
        bar.deleteLater()


def test_a_right_period_stacks_into_a_cell_the_cells_agree_on(win, ph):
    """**這是這個視窗最有說服力的一塊。** 對的週期疊起來，那幾格彼此對得齊。"""
    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")
    gc = stacked(img)
    win._on_done(_measured_of(img), gc, "")

    assert gc.cell.shape == (44, 60), "疊出來就是一個週期那麼大"
    assert gc.agreement >= 0.75, "對的週期要拿到綠燈：%.3f" % gc.agreement
    assert ph.agree_tone(gc.agreement) == ph.TONE_GOOD
    assert win.bar_agree.tone() == ph.TONE_GOOD
    assert not win.cell_view.pixmap().isNull(), "那一格要真的畫出來"


def test_a_wrong_period_stacks_into_mush(win, ph):
    """**反向**：週期錯掉，那幾格就對不起來 —— 一致性掉下去。

    ⚠ 這一條是「疊起來看」這個做法**有沒有用**的證據。少了它，上面那一條
    對一個永遠回 0.9 的實作也會是綠的。
    """
    img = tiles(px=60, py=44)
    right = stacked(img, 60, 44)
    wrong = stacked(img, 37, 29)          # 跟真實週期無關的一組
    assert wrong.agreement < right.agreement
    assert ph.agree_tone(wrong.agreement) != ph.TONE_GOOD


def test_sharpness_is_not_the_metric_and_here_is_why(ph):
    """⚠ **使用者問的「或是算 sharpness 這樣評估？」—— F40 量過，不行。**

    `ghosting_score` 只看疊完那一張圖，**看不到疊進去的那幾格**，所以分不出
    「因為對齊了所以銳利」與「因為兩個鬼影各帶一組邊所以銳利」。這一條把那件
    事釘住：**純雜訊的 sharpness 高到荒謬，而 agreement 誠實地趨近 0。**
    """
    from d4t.core.algo import golden as algo_golden

    rng = np.random.default_rng(0)
    noise = np.clip(rng.normal(128, 60, (480, 600)), 0, 255).astype(np.uint8)
    sharp, _lap, _edge = algo_golden.ghosting_score(
        algo_golden.stack_cells(noise, 60, 44))
    agree = algo_golden.stack_agreement(noise, 60, 44)

    assert sharp > 50, "sharpness 會給雜訊一個很高的分數（這正是問題）"
    assert agree < 0.1, "agreement 不會：%.3f" % agree
    assert ph.agree_tone(agree) == ph.TONE_BAD


def test_doubling_the_period_still_stacks_cleanly(win, ph):
    """使用者的 ×2 情境：兩個重複構成他要的單元 —— 疊起來**照樣**是齊的
    （2×2 個重複疊在一起，只是一格裝了四份圖案）。所以一致性分不出這一種，
    **而人眼在那張圖上分得出來** —— 那正是兩個都要在畫面上的理由。"""
    img = tiles(px=60, py=44)
    twice = stacked(img, 120, 88)
    assert twice.cell.shape == (88, 120)
    assert twice.agreement >= 0.75


def _measured_of(img):
    from d4t.core.algo import template as algo_template
    return algo_template.measure_period(img)


def test_the_bar_fills_to_the_fraction_of_the_score(app, ph):
    """使用者 2026-09-21：「一個橫向的長條（示意 0–100），80 分是綠的、
    填滿到 80%；60 分黃的、填滿到 60 分。」

    ⚠ **軌道要夠長才讀得出「填到幾成」。** 第一版 92 px：92 分填出來 85 px，
    跟填滿的 100 分在畫面上分不出來 —— 而那個差別正是它存在的理由。
    """
    assert ph.BAR_W >= 140, "軌道太短，92 分與 100 分看起來一樣"
    bar = ph.Bar()
    try:
        bar.set_value(0.8, ph.TONE_GOOD, "80")
        assert bar.value_text() == "80" and bar.tone() == ph.TONE_GOOD
        bar.set_value(0.6, ph.TONE_WARN, "60")
        assert bar.tone() == ph.TONE_WARN
    finally:
        bar.deleteLater()


def test_a_typed_period_gets_no_track_at_all(app, ph):
    """**沒有分數可言 ≠ 拿了 0 分。** 畫一條空軌道是在說後者。"""
    bar = ph.Bar()
    try:
        bar.set_text_only(ph.CONF_TYPED)
        assert bar.value_text() == ph.CONF_TYPED
        assert bar._track is False
    finally:
        bar.deleteLater()


def test_the_typed_label_is_short_enough_not_to_be_clipped(ph):
    """量到過：「you typed it」在那一格被切成「you typ…」。完整那句話在警告條上。"""
    assert len(ph.CONF_TYPED) <= 8, ph.CONF_TYPED


def test_a_flat_image_says_so_once_not_twice(win, ph):
    """⚠ **一句話講一次。** 引擎的 note 裡已經有一句
    "no periodic structure detected"（寫給開發者看的，F118），而我自己也想
    講一句 —— 兩句並排出現時使用者會去找「它們是不是在講兩件事」。
    """
    from d4t.core.algo import template as algo_template

    flat = np.full((400, 500), 128, np.uint8)
    win.set_image(flat, "flat.png")
    win._on_done(algo_template.measure_period(flat), None, "")
    said = win.warn.text()
    assert said.lower().count("no repeating period") == 1, said
    assert "no periodic structure detected" not in said, (
        "引擎那句開發者的話不該出現在使用者面前：%r" % said)
    assert "Crop" in said, "答不出來的時候要給下一步"


# --------------------------------------------------------------------------- #
# 7. 取錯怎麼辦：候選、細節、以及「格數太少分數信不過」
#    （使用者 2026-09-21 第三輪）
# --------------------------------------------------------------------------- #
def test_the_candidates_are_the_harmonics_and_never_the_current_one(ph):
    """取錯幾乎永遠是取到諧波裡的另一個，而那份清單 `estimate_period`
    **本來就算好了** —— 以前算完就丟。"""
    m = _M()
    m.candidates = [(60, 44), (30, 44), (120, 44), (60, 88)]
    got = ph.candidate_periods(m, (True, True), (60.0, 44.0))
    assert (60.0, 44.0) not in got, "現在用的那一組不必再提一次"
    assert (30.0, 44.0) in got and (120.0, 44.0) in got


def test_only_the_axes_in_use_appear_in_a_candidate(ph):
    """純 X 的時候提 `60 × 88` 是沒有意義的 —— Y 根本沒在切。"""
    m = _M()
    m.candidates = [(60, 44), (30, 44), (60, 88), (120, 44)]
    got = ph.candidate_periods(m, (True, False), (60.0, 44.0))
    assert all(y == 44.0 for _x, y in got), got
    assert (30.0, 44.0) in got
    labels = [ph.candidate_label(x, y, (True, False)) for x, y in got]
    assert all("×" not in s for s in labels), labels


def test_the_detail_table_shows_each_method_separately(ph):
    """使用者：「我可以看到每個方法的分數嗎？」"""
    m = _M()
    m.proj_px, m.proj_py, m.proj_conf_x, m.proj_conf_y = 60.0, 44.0, 92.0, 93.0
    m.ac_px, m.ac_py, m.ac_conf_x, m.ac_conf_y = 60.0, 44.0, 98.0, 98.0
    m.half_gain_x = m.half_gain_y = 0.0
    m.doubled = (False, False)
    rows = ph.detail_rows(m, (True, True))
    names = [r[0] for r in rows]
    assert names == ["Projection", "2-D autocorr", "Half-period", "Used"]
    assert "92" in rows[0][1] and "98" in rows[1][1], rows


def test_an_axis_not_in_use_is_a_dash_in_the_detail_table(ph):
    m = _M()
    m.proj_px, m.proj_py = 60.0, 44.0
    rows = ph.detail_rows(m, (True, False))
    assert all(r[2] == "—" for r in rows), rows


def test_too_few_cells_says_the_score_cannot_be_trusted(ph):
    """⚠ **這一條是量出來的**（F120 第三輪）。漂移 ＝ 誤差 × 格數，所以同一個
    相對誤差在小圖上累積不起來：真實 60、用 65 去疊，900 px 寬（15 格）
    agree 0.39 紅，300 px 寬（5 格）**0.76 綠** —— 那個綠燈是假的。
    """
    assert ph.trust_note(15) == ""
    said = ph.trust_note(5)
    assert said and "5 cells" in said
    assert "larger" in said or "picture" in said, said


def test_the_cell_count_that_matters_is_per_axis_not_the_total(ph):
    """⚠ **第一版拿錯數字去判斷了**（渲染的時候抓到）。

    300×240 的圖用 65×44 去切是 4×5 ＝ **20 格**，看起來很多 —— 但沿 X 只有
    **4** 格，而漂移 ＝ 誤差 × 那一軸的格數。拿總格數去比門檻的話，
    最該被警告的那張圖不會被警告到。
    """
    assert ph.cells_along((240, 300), 65.0, 44.0, (True, True)) == 4
    assert ph.cells_along((240, 300), 65.0, 44.0, (False, True)) == 5
    assert ph.trust_note(ph.cells_along((240, 300), 65.0, 44.0, (True, True)))
    assert ph.cells_along((700, 900), 60.0, 44.0, (True, True)) == 15
    assert ph.trust_note(ph.cells_along((700, 900), 60.0, 44.0, (True, True))) == ""


def test_the_score_really_does_go_green_on_a_small_crop(ph):
    """把上面那句話**釘在真的數字上** —— 沒有這一條，那段註解只是一個說法。"""
    from d4t.core.algo import template as algo_template

    big = tiles(px=60, py=44, w=900, h=700)
    small = tiles(px=60, py=44, w=300, h=240)
    a_big = algo_template.build_golden_cell(big, px=65.0, py=44.0).agreement
    a_small = algo_template.build_golden_cell(small, px=65.0, py=44.0).agreement
    assert ph.agree_tone(a_big) == ph.TONE_BAD, a_big
    assert ph.agree_tone(a_small) == ph.TONE_GOOD, a_small
    assert ph.trust_note(ph.cells_along((240, 300), 65.0, 44.0, (True, True))), \
        "小圖那一邊一定要有警告"


def test_agreement_degrades_smoothly_with_a_small_error(ph):
    """使用者：「period 取錯一點點的分數跟影像」—— 它**單調**，所以讀得出來。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44, w=900, h=700)
    got = [algo_template.build_golden_cell(img, px=p, py=44.0).agreement
           for p in (60.0, 61.0, 62.0, 63.0)]
    assert got == sorted(got, reverse=True), got
    assert ph.agree_tone(got[0]) == ph.TONE_GOOD
    assert ph.agree_tone(got[-1]) != ph.TONE_GOOD, "差 3 px 不該還是綠的"


def test_sharpness_is_not_monotonic_on_small_errors(ph):
    """⚠ **使用者提的 sharpness 在「差一點點」上會反過來騙人。**

    差 0.5 px 的 stack 拿 39 分，差 3 px 的拿 81 分 —— 照 sharpness 排序會
    挑掉錯得更多的那一個。這是 F40 那個結論在這個情境下的直接證據。
    """
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44, w=900, h=700)
    nearly = algo_template.build_golden_cell(img, px=60.5, py=44.0)
    worse = algo_template.build_golden_cell(img, px=63.0, py=44.0)
    assert worse.ghosting > nearly.ghosting, "sharpness 反過來了（這正是重點）"
    assert worse.agreement < nearly.agreement, "而 agreement 沒有"


# --------------------------------------------------------------------------- #
# 8. 視窗：新加的那幾顆
# --------------------------------------------------------------------------- #
def _ready(win, img=None):
    from d4t.core.algo import template as algo_template
    img = tiles(px=60, py=44) if img is None else img
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), stacked(img), "")
    return img


def test_choosing_one_axis_hides_the_other_row_entirely(win, ph):
    """使用者 2026-09-21：「純 X 或純 Y 請只要顯示對應的 X 或 Y 就好」。

    ⚠ 這**推翻了第一版**（那時寫 `not used`）：按下 X only 的人是自己按的，
    他知道 Y 還在 —— 那一列對他只是噪音。
    """
    _ready(win)
    assert win._tags[1].isVisibleTo(win), "Auto 兩軸都在"
    win.chips_axis.set_text(ph.AXIS_X)
    win._on_axis(ph.AXIS_X)
    assert win._tags[0].isVisibleTo(win)
    assert not win._tags[1].isVisibleTo(win), "Y 那一列要整列不見"
    assert not win._bars[1].isVisibleTo(win)


def test_a_candidate_button_applies_it(win, ph):
    _ready(win)
    assert win._try_buttons, "要提得出其他可能"
    before = [r[1] for r in win.rows()]
    win._try_buttons[0].click()
    assert [r[1] for r in win.rows()] != before, "按了要真的換掉"
    assert win.override() != (None, None)


def test_details_start_folded_and_open_on_demand(win, ph):
    """要查的那天它在，平常不佔畫面（使用者同一輪也說了「不要看一堆文字」）。"""
    _ready(win)
    assert not win.details.isVisibleTo(win)
    win.btn_details.setChecked(True)
    assert win.details.isVisibleTo(win)
    text = win.details.text()
    assert "Projection" in text and "2-D autocorr" in text


def test_copy_puts_a_usable_line_on_the_clipboard(win, ph, app):
    """⚠ **這一條的名字一直是對的，錯的是它的斷言。**

    它本來斷言剪貼簿裡是
    ``X 60 px (0.150 µm)  Y 44 px (0.110 µm)`` —— 而那是一個**貼進任何
    一格都會被拒絕的字串**。這個數字的去處是 `Cell W` / `Cell H`
    兩個各自的輸入框（使用者 2026-09-21：「複製應該要能直接複製
    數字（不包含單位）」）。

    > **能帶走答案跟能用答案是兩回事。**
    """
    from PySide6.QtGui import QGuiApplication

    _ready(win)
    win.spin_nm.setValue(2.5)
    win.copy_axis(0)
    assert QGuiApplication.clipboard().text() == "60"
    win.copy_axis(1)
    assert QGuiApplication.clipboard().text() == "44"


def test_copy_only_carries_the_axes_in_use(win, ph):
    _ready(win)
    win.chips_axis.set_text(ph.AXIS_X)
    win._on_axis(ph.AXIS_X)
    assert "Y" not in win.answer_text(), win.answer_text()


def test_the_median_stack_is_a_tick_not_a_hidden_setting(win, ph):
    """大圖中間常常就是缺陷本體，而 mean 會把它抹進 GC。"""
    assert win.stack_method() == "mean"
    win.chk_median.setChecked(True)
    assert win.stack_method() == "median"


# --------------------------------------------------------------------------- #
# 9. Crop 的相位、以及邊界那一圈（使用者 2026-09-21 第四輪）
# --------------------------------------------------------------------------- #
def _edgy(px=60, py=44, w=900, h=700, seed=1, band=40):
    """帶真實掃描邊緣效應的圖：最外一圈偏亮／偏暗 ＋ 額外雜訊。"""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    img = 110 + 55 * (((x % px) < px * 0.42) + 0.8 * ((y % py) < py * 0.5))
    img = img + rng.normal(0, 5, (h, w))
    img[:band, :] += 55
    img[-band:, :] -= 45
    img[:, :band] += 35
    img[:, -band:] -= 40
    img[:band, :] += rng.normal(0, 25, img[:band, :].shape)
    img[-band:, :] += rng.normal(0, 25, img[-band:, :].shape)
    return np.clip(img, 0, 255).astype(np.uint8)


@pytest.mark.parametrize("off", [(0, 0), (37, 19), (13, 7)])
def test_cropping_anywhere_keeps_the_grid_on_the_same_structure(off):
    """使用者 2026-09-21：「crop image 也是要確保格線落在正確的位置喔」。

    判準是**換算回原圖的相位**：不管裁在哪裡（包括不是週期整數倍的位置），
    `origin + 裁切偏移` 對週期取餘數要是同一個值 —— 也就是格線落在同一個
    地標上。靠的是 `build_golden_cell` 的 `anchor_cell`。
    """
    from d4t.core.algo import template as algo_template
    from d4t.ui.crop_dialog import crop_array

    full = tiles(px=60, py=44, w=900, h=700)
    base = algo_template.build_golden_cell(full)
    want = (base.origin[0]) % base.period_x

    ox, oy = off
    sub = crop_array(full, (ox, oy, 500, 400))
    got = algo_template.build_golden_cell(sub)
    assert got.period_x == base.period_x and got.period_y == base.period_y
    assert (got.origin[0] + ox) % base.period_x == want, (
        "裁過之後格線落到別的地方了：裁 %s → 相位 %s，整張圖是 %s"
        % (off, (got.origin[0] + ox) % base.period_x, want))


def test_leaving_the_edge_cells_out_rescues_a_scan_edge(ph):
    """⚠ **這一條是量出來的，不是一個說法。** 使用者：「邊界其實我有點不太想放。」

    帶掃描邊緣效應的圖：整張疊 0.872，去掉最外一圈 0.980。
    """
    from d4t.core.algo import golden as algo_golden
    from d4t.core.algo import template as algo_template

    img = _edgy()
    gc = algo_template.build_golden_cell(img)
    box = ph.trim_to_inner(img.shape[:2], gc.period_x, gc.period_y,
                           gc.origin, (True, True))
    assert box is not None
    x0, y0, x1, y1 = box
    inner = img[y0:y1, x0:x1]
    better = algo_golden.stack_agreement(inner, int(gc.period_x), int(gc.period_y))
    assert better > gc.agreement + 0.05, (gc.agreement, better)
    assert ph.agree_tone(better) == ph.TONE_GOOD


def test_leaving_the_edge_out_costs_nothing_on_a_clean_image(ph):
    """**反向**：它在不需要的時候不准變差，否則預設打開是不對的。"""
    from d4t.core.algo import golden as algo_golden
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44, w=900, h=700)
    gc = algo_template.build_golden_cell(img)
    box = ph.trim_to_inner(img.shape[:2], gc.period_x, gc.period_y,
                           gc.origin, (True, True))
    inner = img[box[1]:box[3], box[0]:box[2]]
    after = algo_golden.stack_agreement(inner, int(gc.period_x), int(gc.period_y))
    assert after >= gc.agreement - 0.01, (gc.agreement, after)


def test_the_trim_keeps_the_phase(ph):
    """切的是**沿著格線**的一整圈 —— 新的左上角要正好落在一條格線上，
    否則疊出來的是另一組格子（而畫面上看不出來）。"""
    box = ph.trim_to_inner((700, 900), 60.0, 44.0, (22.0, 25.0), (True, True))
    x0, y0, _x1, _y1 = box
    assert (x0 - 22) % 60 == 0, x0
    assert (y0 - 25) % 44 == 0, y0


def test_the_trim_backs_off_when_there_is_nothing_left_to_trim(ph):
    """把 3×3 疊成 1×1 換不到乾淨，只換到一個『其實沒有在疊』的 stack。"""
    assert ph.trim_to_inner((160, 200), 60.0, 44.0, (0.0, 0.0), (True, True)) is None


def test_an_axis_not_in_use_is_never_trimmed(ph):
    """那一軸一格就是整張影像 —— 切了就什麼都不剩。"""
    box = ph.trim_to_inner((700, 900), 60.0, 700.0, (0.0, 0.0), (True, False))
    assert box is not None
    assert (box[1], box[3]) == (0, 700), box


def test_the_screen_says_the_edge_was_left_out(win, ph):
    """少了幾格是事實，而使用者盯著的正是那個格數。"""
    img = _edgy()
    win.set_image(img, "edgy.tif")
    win._on_done(*_run(win, img), "")
    assert "edges left out" in win.lab_stack.text(), win.lab_stack.text()


def test_the_edge_tick_is_on_by_default(win, ph):
    assert win.skip_edges() is True
    win.chk_edges.setChecked(False)
    assert win.skip_edges() is False


def _run(win, img):
    """同步跑一次 worker 做的事（測試不開執行緒）。"""
    from d4t.ui import pitch_helper as ph
    from d4t.core.algo import template as algo_template
    m = algo_template.measure_period(img)
    win._m = m
    flags = win._flags()
    ux, uy = ph.lattice_periods(img.shape[:2], *ph.effective_period(m, win.override()), flags)
    w = ph._PitchWorker(img, win.axis(), m, win.override(), win.stack_method(),
                        win.skip_edges())
    gc = algo_template.build_golden_cell(img, px=ux, py=uy)
    if win.skip_edges():
        gc = w._without_edges(gc, ux, uy, flags)
    return m, gc


def test_the_grid_draws_only_the_cells_that_were_stacked(win, ph):
    """⚠ **這一輪第三次踩到同一種形狀**（`_on_axis`、`_draw` 的週期、這裡）：
    **同一件事在畫面上有兩個算法**。

    邊界那一圈沒有被疊進去，格線就不准還框著它 —— 使用者盯著的正是那張圖，
    而「畫面上有 210 格、疊的是 156 格」他看不出來。
    """
    img = _edgy()
    win.set_image(img, "edgy.tif")
    win._on_done(*_run(win, img), "")
    drawn = win.view.overlay_count()
    assert drawn == win._gc.n_cells, (drawn, win._gc.n_cells)

    win.chk_edges.setChecked(False)
    win._on_done(*_run(win, img), "")
    assert win.view.overlay_count() == win._gc.n_cells
    assert win.view.overlay_count() > drawn, "不去邊界的時候格子要變多"


# --------------------------------------------------------------------------- #
# 10. 版面：**那個答案要真的變大**（F120 第七輪）
# --------------------------------------------------------------------------- #
def test_the_answer_is_actually_bigger_than_ordinary_text(app, ph):
    """⚠ **這一條守的是一個「改了六輪都沒有生效」的改動。**

    這個視窗只回答一件事，所以那個數字必須是畫面上最大的字。前六輪都是
    `setPointSizeF(pointSizeF() * f)` —— 而這個 app 的 QSS 用**像素**設字級，
    於是 `pointSizeF()` 回 **-1**、乘出來是負的，Qt **安靜地忽略**。量出來
    答案一直是 13 px，跟旁邊的說明一模一樣，而使用者每一輪都回報「Period
    答案要清楚一點」。

    **一個沒有生效的視覺改動，看起來跟沒有被聽見一模一樣** —— 所以這裡量的
    是渲染出來的字高，不是我們設了什麼。
    """
    from d4t.ui import theme
    theme.apply_theme(app)          # `run()` 開窗之前做的第一件事
    win = ph.PitchHelperWindow()
    try:
        # ⚠ QSS 是在 **polish** 的時候才套到 widget 上的 —— 不 polish 的話
        # 這裡量到的是 Qt 的預設字，三個都一樣大，而這支測試就永遠是綠的。
        for w in (win.caption, win.lab_big, win.lab_um):
            w.ensurePolished()
        body = win.caption.fontMetrics().height()
        big = win.lab_big.fontMetrics().height()
        assert big >= body * 2, ("答案沒有比一般文字大兩倍", big, body)
        sub = win.lab_um.fontMetrics().height()
        assert body < sub < big, ("µm 那一行要在兩者之間", sub, body, big)
    finally:
        win.close()


def test_the_copy_button_sits_with_the_thing_it_copies(win, ph, app):
    """使用者 2026-09-21：「copy 是 copy 誰？」

    一顆按鈕的意思是**它旁邊那個東西**，不是它自己的字。第一版它住在下面的
    `Units` 那一段，離那個答案隔了三個區塊。
    """
    win.resize(1180, 780)
    win.show()
    app.processEvents()
    # ⚠ 這一條本來寫的是 `answer < copy < units`，而 `units` 是「最底下那個
    # 區段」的代名詞。第十輪把 pixel size 搬到答案裡面之後那個代名詞就不成立了
    # —— **但這一條要守的事沒有變**：Copy 要待在答案那一塊裡，不是被推到某個
    # 區段後面。所以改問「它在第一條區段標題之前嗎」，那才是「同一塊」的意思。
    from PySide6.QtWidgets import QLabel

    def top(w):
        return w.mapTo(win, w.rect().topLeft()).y()

    first_section = min(
        top(lab) for lab in win.findChildren(QLabel)
        if lab.objectName() == "paramSection" and not lab.isHidden())
    assert top(win.lab_big) < top(win.btn_copy) < first_section, (
        top(win.lab_big), top(win.btn_copy), first_section)


def test_the_copy_button_says_what_it_will_copy(win, ph):
    """另一半答案：**tooltip 裡有那個數字本人**，不是「複製 pitch」。"""
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    for i, (num, cell) in enumerate((("60", "Cell W"), ("44", "Cell H"))):
        tip = win._copy_buttons[i].toolTip()
        assert num in tip and cell in tip, tip


def test_each_axis_has_its_own_copy_key(win, ph):
    """使用者 2026-09-21：「X 跟 Y 都要有複製鍵」。

    而**沒在用的那一軸連複製鍵都不出現** —— 同那一列數字的規矩
    （按下 X only 的人知道 Y 還在，那一列對他只是噪音）。
    """
    img = lines_only(px=60)
    win.set_image(img, "lines.tif")
    win.chips_axis.set_text(ph.AXIS_X)
    win._on_done(*_run(win, win._work), "")
    assert len(win._copy_buttons) == 2
    assert not win._copy_buttons[0].isHidden()
    assert win._copy_buttons[1].isHidden(), "Y 沒在用，它的複製鍵不該在"
    assert win.axis_number(1) == "", "沒在用的軸沒有數字可複"


def test_the_copied_number_is_the_one_on_screen(win, ph):
    """⚠ 複製走的是 `rows()` —— **畫面上那個數字本人**，不是再算一次。

    使用者打進去的週期、×2、候選一鍵套用，複製到的都要是他看到的那一個。
    """
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    assert win.axis_number(0) == "60"
    win.spin_px.setValue(120.0)
    assert win.axis_number(0) == "120", "改了就複改完的那個"


def test_typing_does_not_recompute_on_every_keystroke(win, ph):
    """使用者 2026-09-21：「我要輸入 45，但當我輸入到 4，就會強制 trigger 算 4」。

    ⚠ 中途那一次不只是浪費（疊一次格子是幾百毫秒），它還會**在畫面上閃一個
    錯的答案** —— 而這個視窗的全部內容就是那一個答案。
    """
    for sp in (win.spin_px, win.spin_py, win.spin_nm):
        assert not sp.keyboardTracking(), sp.objectName() or sp.suffix()


def test_the_chip_says_what_the_layout_looks_like(ph):
    """三顆膠囊問的是**使用者的樣品長什麼樣**，不是問軟體怎麼做
    （CLAUDE.md §3 那條「改變「量得出什麼」的選擇是屬路」）。"""
    for key in ph.AXES:
        assert "repeats" in ph.AXIS_HELP[key], (key, ph.AXIS_HELP[key])
        assert "Auto" not in ph.AXIS_HELP[key], "Auto 拿掉了，字裡也不該還提"


def test_a_zero_score_is_drawn_not_left_blank(ph):
    """⚠ **0 分跟「沒有被評分過」不准長得一樣。**

    `set_text_only` 刻意不畫軌道，意思是「這個數字沒有被評分過」。真的拿 0
    分的那一格必須看得出它**被評過、而且掛了** —— 那正是使用者打錯週期的
    那一刻（實測：一張 60 的圖打 45 得 0.0）。
    """
    bar = ph.Bar(None)
    bar.set_value(0.0, ph.TONE_BAD, "0")
    assert bar._track is True and bar.tone() == ph.TONE_BAD
    bar.set_text_only(ph.CONF_TYPED)
    assert bar._track is False


def test_a_typed_period_gets_a_score_on_screen(win, ph):
    """使用者 2026-09-21：「自定義 period 右上可否也能算 confidence？」"""
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    win.spin_px.setValue(45.0)
    assert win.typed_conf()[0] == 0.0, "45 對一張 60 的圖完全不重複"
    assert win.rows()[0][3] == "0 / 100"
    assert win._bars[0].tone() == ph.TONE_BAD, "打錯的那一刻長條就要變紅"

    win.spin_px.setValue(120.0)
    assert win.typed_conf()[0] > 50.0, "兩倍週期是真的有重複，不准打成錯的"


# --------------------------------------------------------------------------- #
# 11. ⚠ 純 X／純 Y：**沒在用的那一軸，原點是 0**（F120 第八輪）
# --------------------------------------------------------------------------- #
def lines_only(px=60, w=900, h=700, seed=1):
    """只有直線重複的 line/space —— Y 那一軸完全平。"""
    rng = np.random.default_rng(seed)
    _y, x = np.mgrid[0:h, 0:w]
    img = 110 + 60 * ((x % px) < px * 0.45) + rng.normal(0, 5, (h, w))
    return np.clip(img, 0, 255).astype(np.uint8)


def test_the_unused_axis_does_not_move_the_trim_box(ph):
    """⚠ **這一輪第四次踩到同一種形狀：同一件事在畫面上有兩個算法。**

    `lattice_boxes` 裡寫著 ``oy = origin[1] if periodic[1] else 0.0`` ——
    沒在用的那一軸，原點是 0。`trim_to_inner` 本來沒有那一行，於是 X only
    模式下它拿相位搜尋回來的 `oy`（實測 129）當上邊界，而格子是從 y=0 開始、
    整張高 —— **一格都塞不進去**。
    """
    box = ph.trim_to_inner((700, 900), 60.0, 700.0, (59, 129), (True, False))
    assert box is not None
    assert box[1] == 0 and box[3] == 700, ("沒在用的那一軸要整張都算", box)
    assert box[0] > 0 and box[2] < 900, ("在用的那一軸才剪", box)


def test_x_only_still_stacks_cells_with_edges_skipped(win, ph):
    """使用者看到的那一面：**格線沒了、0 cells、一條紅的「this period is
    wrong」—— 而那個週期是對的**（信心 92）。"""
    img = lines_only(px=60)
    win.set_image(img, "lines.tif")
    win.chips_axis.set_text(ph.AXIS_X)
    win._on_done(*_run(win, win._work), "")
    assert win.skip_edges(), "預設就是去邊界 —— 這個 bug 在預設值上"
    assert win._gc.n_cells >= ph.MIN_CELLS_AFTER_TRIM, win._gc.n_cells
    # ⚠ 要真的**剪掉了**，不是靠下面那道「剪完什麼都不剩就回到沒剪的」保險。
    # 少了這一行，兩個修正裡只要有一個在，這一條就是綠的。
    assert win._gc.trimmed, "去邊界那一勾是開著的，它就該真的去掉一圈"
    assert win._gc.n_cells < 14, ("最外一圈要少掉", win._gc.n_cells)
    assert win._gc.agreement > 0.5, ("對的週期不准被講成錯的", win._gc.agreement)
    assert win.view.overlay_count() == win._gc.n_cells, "畫的格子＝疊的格子"
    assert win.rows()[0][1] == "60" and win.rows()[1][1] == ph.PITCH_UNSET


def test_a_trim_that_leaves_nothing_falls_back_to_the_untrimmed_stack(win, ph):
    """⚠ **一個算不出來的答案不准假裝成一個否定的答案。**

    0 格疊出來的 `agreement` 是 0.00，而畫面上 0.00 長得跟「這個週期是錯的」
    一模一樣。同卡片那一條「算不出來的那一格不寫」。
    """
    img = lines_only(px=60)
    win.set_image(img, "lines.tif")
    win.chips_axis.set_text(ph.AXIS_X)
    m, gc = _run(win, win._work)
    assert gc.n_cells > 0, gc.n_cells


def test_nothing_measured_yet_is_not_drawn_as_a_zero(win, ph):
    """⚠ **「沒有東西可疊」跟「疊了，而它們完全對不起來」不准長得一樣。**

    `Bar` 改成「0 分畫一顆點」之後，這一格就變成了那個改動的反面 —— 還沒有
    疊過的時候畫一顆點，等於說「這個週期拿了 0 分」。
    """
    # ⚠ **三條都要問。** 這一條本來只斷言 `bar_agree`，而同一張卡裡另外兩條
    # （Repeat along X / Y）走的是另一段程式 —— 它們在空狀態各畫一顆琥珀色的
    # 點（=「被評分過，拿了 0 分」），而這一條完全沒發現。
    # **三條裡守一條，另外兩條就大搖大擺地漏過去。**
    for b in (win.bar_agree, win._bars[0], win._bars[1]):
        assert b._track is False, "還沒量過就不畫軌道"
    assert not win.btn_copy.isEnabled(), "沒有答案的時候 Copy 是灰的"

    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    assert win.bar_agree._track is True and win.btn_copy.isEnabled()


def test_the_grid_matches_the_stack_after_a_typed_period(win, ph):
    """⚠ 同一種形狀的第五次：**畫的格子要跟疊進去的那些是同一批** —— 而
    使用者打了一個自己的週期之後也一樣。

    這一條跟 `test_the_grid_draws_only_the_cells_that_were_stacked` 的差別是
    那一條走的是量出來的週期；`trim_to_inner` 吃的是 `effective_period`，
    所以打進去的那一組是另一條路。
    """
    # ⚠ 圖要夠大：`trim_to_inner` 在「剪完剩不到 3 格」時**正確地**不剪，
    # 而預設的 600×480 配 120×88 剛好就是那一種（4 格剪成 2 格）。
    img = tiles(px=60, py=44, w=900, h=700)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    win.spin_px.setValue(120.0)
    win.spin_py.setValue(88.0)
    win._on_done(*_run(win, win._work), "")
    assert win._gc.trimmed, "這個尺寸剪得動，就該剪"
    assert win.view.overlay_count() == win._gc.n_cells, (
        win.view.overlay_count(), win._gc.n_cells)


def test_a_cancelled_run_does_not_put_a_half_stacked_answer_on_screen(win, ph):
    """⚠ **被停掉的部分結果拒寫**（鐵則 11 在這個視窗的版本）。

    `run()` 只在「量完週期、還沒開始疊」那一刻檢查 `_stop`。疊圖吃的
    `progress=self._tick` 回的是 `not self._stop`，所以停在疊圖中途時
    `build_golden_cell` 會回一份**只疊了一半、`n_cells` 是 0** 的 GoldenCell。
    那一份走到畫面上長得就是「Cells agree 空白、0 cells」—— 也就是**「這個
    週期不成立」**，而實情是「這一次沒跑完」。4096² 疊十幾秒，中途改一個設定
    就踩得到。
    """
    img = tiles(px=60, py=44)
    got = []
    w = ph._PitchWorker(img, ph.AXIS_BOTH)
    w.done.connect(lambda m, gc, err: got.append((m, gc, err)))
    w.stop()                              # 還沒 start 就取消
    w.run()                               # 同步跑一次（不開執行緒）
    assert got and got[-1][0] is None, ("停掉的那一份不准帶著 m 出去", got[-1])

    # 而 `_on_done` 對那一份的反應是**什麼都不做** —— 畫面停在上一個完整答案。
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    good = win._gc.n_cells
    win._on_done(None, None, "")
    assert win._gc.n_cells == good, "被忽略，不是被覆蓋"


# --------------------------------------------------------------------------- #
# 12. 量尺（F120 第九輪，使用者：「畫布上也添加量尺功能」）
# --------------------------------------------------------------------------- #
def _drag(view, x0, y0, x1, y1):
    """直接餵**影像座標**拉一段（不必模擬滑鼠事件的座標換算）。"""
    from PySide6.QtCore import QPointF
    sc, off = view.view_state()
    view._measuring = QPointF(float(x0), float(y0))
    view._drag_measure(QPointF(off.x() + float(x1) * sc,
                               off.y() + float(y1) * sc))
    view._measuring = None


def test_the_ruler_measures_along_the_way_you_dragged(win, ph):
    """⚠ **量的是一個軸上的距離，不是一條斜線的長度。**

    pitch 問的是「隔多遠重複一次」—— 那永遠是沿著一個方向。拉得歪一點不該
    讓讀數變大（`hypot` 會，而使用者的手一定會歪一點）。
    """
    win.set_image(tiles(px=60, py=44), "a.tif")
    win.btn_ruler.setChecked(True)
    _drag(win.view, 180, 300, 420, 320)          # 橫的為主，但 y 也動了 20
    assert win.measured_span() == ("x", 240.0), win.measured_span()
    _drag(win.view, 100, 100, 118, 276)          # 直的為主
    assert win.measured_span() == ("y", 176.0), win.measured_span()


def test_the_reading_survives_the_release(win, ph):
    """⚠ 這一點跟 F8 曲線上那把尺**刻意相反**，而理由寫在
    `ImageView.set_measure_mode`：那一把是「現在正在量」的回饋，這一把量出來
    的數字**使用者下一步要拿去用**，所以它得活到那一下。
    """
    win.set_image(tiles(), "a.tif")
    win.btn_ruler.setChecked(True)
    _drag(win.view, 100, 100, 340, 110)
    assert win.view.measure_span() is not None, "放開之後帶子還在"
    # ⚠ `isVisible()` 對一個沒被 show 過的視窗底下的子元件永遠是 False；
    # 這裡問的是**我們有沒有把它藏起來**，那是 `isHidden()`。
    assert not win.btn_use_ruler.isHidden()


def test_using_the_reading_goes_through_the_same_path_as_typing_it(win, ph):
    """⚠ **量尺不是第三條算週期的路。**

    它把數字填進 `spin_px`／`spin_py`，走的是既有的「使用者自己打一個週期」
    —— 所以格線、疊圖、`confidence_at` 全部跟著重算，而且跟手打的完全一樣。
    這個視窗這一輪為了「同一件事有兩個算法」付過四次錢了。
    """
    win.set_image(tiles(px=60, py=44), "a.tif")
    win._on_done(*_run(win, win._work), "")
    win.btn_ruler.setChecked(True)
    _drag(win.view, 100, 100, 340, 108)          # 240 px
    win.use_measured()
    assert win.override()[0] == 240.0
    assert win.spin_py.value() == 0.0, "只填拉的那一軸"
    assert win.measured_span() is None, "用掉就收起來 —— 畫面上不需要兩份"
    assert not win.btn_ruler.isChecked()


def test_a_new_image_clears_the_ruler(win, ph):
    """⚠ 底下的像素換了，剛剛量的那一段就不算了 —— 留著的話那條綠帶會落在
    一張它從來沒有被拉過的圖上，而畫面不會說那是舊的。"""
    win.set_image(tiles(), "a.tif")
    win.btn_ruler.setChecked(True)
    _drag(win.view, 100, 100, 340, 110)
    assert win.measured_span() is not None
    win.set_image(tiles(px=30, py=22), "b.tif")
    assert win.measured_span() is None
    assert win.view.measure_span() is None


def test_the_ruler_reading_is_not_clobbered_by_a_refresh(win, ph):
    """⚠ 量尺的讀數跟格線的說明搶同一行，而它們由不同的事件觸發。

    少了 `_say_caption` 那道收口，worker 回來的那一刻會把使用者剛量到的數字
    蓋掉。
    """
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    win.btn_ruler.setChecked(True)
    _drag(win.view, 100, 100, 340, 110)
    before = win.caption.text()
    assert before.startswith("Ruler:")
    win._refresh()
    assert win.caption.text() == before, "重算不准蓋掉使用者手上正在做的事"


def test_turning_the_ruler_off_gives_the_caption_back(win, ph):
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    grid_text = win.caption.text()
    win.btn_ruler.setChecked(True)
    _drag(win.view, 100, 100, 340, 110)
    win.btn_ruler.setChecked(False)
    assert win.caption.text() == grid_text
    assert win.view.measure_mode() is False


def test_the_toolbar_buttons_have_their_own_glyphs(win, ph):
    """使用者 2026-09-21：「UI 按鈕可以加 icon」。

    ⚠ 圖示是**自繪**的，不是字元 —— 廠內是 Windows 而 Segoe UI 蓋不到那些
    符號（`draw_glyph_icon` 的檔頭）。而四顆並排，所以名字不准重複。
    """
    from d4t.ui import icons as icons_mod
    got = {b.glyph_name() for b in (win.btn_open, win.btn_paste, win.btn_crop,
                                    win.btn_ruler, win.btn_copy, win.btn_reset)}
    assert len(got) == 6, ("六顆六個圖示，不准兩顆共用", got)
    for name in got:
        assert name in icons_mod.GLYPH_ICONS, name


def test_a_glyph_button_leaves_room_for_its_glyph(app, ph):
    """⚠ **這一條守的是一個只會在畫面上出現的 bug。**

    圖示畫在 `rect().left() + 7`，而空出那一格的是 QSS 的
    ``[hasGlyph="true"] { padding-left }``。那條規則本來只寫給
    ``QToolBar QToolButton`` —— 一顆 `QPushButton` 什麼都拿不到，於是圖示**畫
    在第一個字母上面**（實拍：`Open image…` 變成一張圖底下壓著一個 O）。
    `#primary` 另外有自己的 padding，specificity 更高，所以要各講一次。
    """
    from PySide6.QtWidgets import QPushButton

    from d4t.ui import theme
    theme.apply_theme(app)
    win = ph.PitchHelperWindow()
    try:
        for b in (win.btn_open, win.btn_paste, win.btn_crop):
            # ⚠ **不能讀 `contentsRect().left()`** —— QSS 樣式下它的**尺寸**扣掉了
            # padding，但**原點仍然是 (0, 0)**（`_paint_glyph` 的註解逐字講了這件
            # 事）。量得到的是**寬度差**：同一段字，有圖示的那一顆要寬出一格。
            plain = QPushButton(b.text(), win)
            plain.setObjectName(b.objectName())
            plain.setProperty("variant", b.property("variant"))
            b.ensurePolished()
            plain.ensurePolished()
            # 算術：普通鈕的 ``padding-left`` 是 12（`#primary` 是 18），帶圖示的
            # 是 26（`#primary` 30）—— 所以寬度差是 14 跟 12。而圖示畫在
            # x = 7..21，所以 26 跟 30 都跨過它了。這裡只問**有沒有空出來**：
            # 那條規則沒有匹配到的時候這個數字是 **0**。
            room = b.sizeHint().width() - plain.sizeHint().width()
            assert room >= 10, (b.text(), room, "圖示會壓到字")
            plain.deleteLater()
        # 連機制一起釘住：兩條規則各講一次（`#primary` 自己的 padding
        # specificity 更高，沒有第二條的話它拿不到）。
        qss = app.styleSheet()
        assert 'QPushButton[hasGlyph="true"]' in qss
        assert 'QPushButton#primary[hasGlyph="true"]' in qss
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 13. 版面：注意力的分配（F120 第十輪）
# --------------------------------------------------------------------------- #
def test_only_the_real_actions_get_a_box(win, ph):
    """⚠ **藍色在這個 app 是 accent =「這是動作」；全部 accent 等於沒有。**

    第十輪之前右欄有 8 顆可見按鈕，**全部 `variant="secondary"`**（藍框、同
    權重），而其中四顆是 `Or try` 的候選 —— 畫面上最不重要的東西（「萬一取錯
    了」的備案），卻是最吵的一叢。
    """
    from PySide6.QtWidgets import QPushButton

    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    right = win.btn_copy.parentWidget()
    boxed = [b for b in right.findChildren(QPushButton)
             if not b.isHidden() and b.property("variant") == "secondary"]
    # ⚠ **4 → 5：這個上限漲了一格，而它有理由。** 第十三輪一顆 Copy 拆成
    # `Copy X` / `Copy Y`（使用者：「X 跟 Y 都要有複製鍵」）—— 多出來的那一顆
    # 是**一個真的動作**，不是裝飾。這條線守的是「候選不准跟動作一樣吵」，
    # 那件事沒有變。
    assert len(boxed) <= 5, ("有框的鈕太多了", [b.text() for b in boxed])
    assert win._try_buttons, "這張圖應該有候選"
    for b in win._try_buttons:
        assert b.property("variant") == "ghost", b.text()
        # ⚠ 但**不准變成死掉的文字** —— 純 ghost 是次要色，實拍跟旁邊的
        # "Or try" 一樣灰，而它們是點得下去的。
        assert b.property("clickableText") == "true", b.text()


def test_the_evidence_sits_with_the_answer(win, ph):
    """⚠ **信心長條跟那張疊出來的圖回答的是同一個問題。**

    第十輪之前它們相隔 377 px，中間隔著兩個設定區 —— 使用者要判斷「這個數字
    對不對」得上看、下看、再上看。
    """
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    win.resize(1180, 780)
    win.show()
    # ⚠ 量到**那張卡的上緣**，不是量到 `bar_agree`。第十二輪把兩條信心條搬
    # 進卡裡之後，`Cells agree` 自然往下移了兩列 —— 那不是「證據變遠了」，
    # 是「卡裡的證據變多了」。量一個會被卡片內容影響的點，守的就不是這件事。
    card = win.cell_view.parentWidget()
    gap = (card.mapTo(win, card.rect().topLeft()).y()
           - win.lab_big.mapTo(win, win.lab_big.rect().center()).y())
    assert 0 < gap < 300, ("答案跟證據離太遠", gap)


def test_the_pixel_size_sits_with_what_it_converts(win, ph):
    """⚠ 它本來有自己的 `Units` 區段排在最下面，而它產生的 µm 在最上面 ——
    量出來是 552 px。一個輸入跟它的效果能隔多遠就隔多遠。"""
    from PySide6.QtWidgets import QLabel

    def top(w):
        return w.mapTo(win, w.rect().topLeft()).y()

    win.resize(1180, 780)
    win.show()
    assert abs(top(win.spin_nm) - top(win.lab_um)) < 80, "要貼著 µm 那一行"
    titles = [lab.text() for lab in win.findChildren(QLabel)
              if lab.objectName() == "paramSection" and not lab.isHidden()]
    assert "Units" not in titles, ("一個輸入框不值一條區段標題", titles)


def test_the_stacked_picture_does_not_overlap_the_column_beside_it(win, ph):
    """⚠ **Qt 空間不夠時就是會重疊，不會報錯** —— 這個面板第一版踩過。

    `CELL_BOX` 175 的時候實測只剩 3 px 的間隙（圖片右緣 984、右欄 987），
    換一個字型或 DPI 就疊了。這一條把那個間隙釘住。
    """
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    win.resize(1180, 780)
    win.show()
    pic = win.cell_view
    right_edge = pic.mapTo(win, pic.rect().topRight()).x()
    for w in (win.bar_agree, win.lab_stack, win.chk_median, win.chk_edges):
        x = w.mapTo(win, w.rect().topLeft()).x()
        assert x - right_edge >= 8, (w.objectName() or type(w).__name__,
                                     x, right_edge)


def test_the_next_step_names_something_that_exists(ph):
    """⚠ **一句指路的話寫了一個找不到的名字，比不寫還糟。**

    第一版寫的是 "Cell size" —— 而那四個字只活在 `template_dialog` 的檔頭
    註解裡，畫面上那兩格的標籤是 `Cell W` / `Cell H`。使用者會去找一個不存在
    的東西，然後開始懷疑其他每一句。

    這一條從 `template_dialog` 的**原始碼**反查，所以那邊改名這裡就會紅。
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "d4t" / "ui"
           / "template_dialog.py").read_text(encoding="utf-8")
    assert 'setWindowTitle("Template & regions")' in src, "視窗標題改了"
    for name in ("Cell W", "Cell H"):
        assert '("%s"' % name in src, ("那一格的標籤改了", name)
        assert name in ph.NEXT_STEP, (name, ph.NEXT_STEP)


def test_the_next_step_only_shows_once_there_is_an_answer(win, ph):
    """同警告條那條規矩：一塊永遠在那裡、內容通常沒用的東西，教會使用者不要
    看它。"""
    assert win.lab_next.isHidden(), "還沒量到東西就不必講下一步"
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    assert not win.lab_next.isHidden()


def test_the_panel_can_be_dragged_but_not_squashed(win, ph):
    """⚠ **左右由使用者拉，不是我挑一個數字。**

    380 是在「四顆膠囊排得下」量出來的 —— 它答不出「這張圖有多寬」。一張
    4096² 的 patch 跟一張 900×700 的 SEM 要的比例不一樣，而只有坐在那裡的人
    知道他在看哪一種。380 因此從固定寬變成**最小**寬。
    """
    win.resize(1180, 780)
    win.show()
    assert win.split.count() == 2
    assert not win.split.isCollapsible(0) and not win.split.isCollapsible(1)
    win.split.setSizes([1100, 60])          # 想把右欄壓扁
    assert win.split.sizes()[1] >= 380, ("最小寬沒擋住", win.split.sizes())
    win.split.setSizes([300, 880])          # 反過來要一個寬的右欄
    assert win.split.sizes()[1] > 700, ("拉不大", win.split.sizes())


# --------------------------------------------------------------------------- #
# 14. 格線的顏色（F120 第十二輪，使用者：「格線 cutline 顏色有建議的」）
# --------------------------------------------------------------------------- #
def _lum(hexs):
    """WCAG 相對亮度。"""
    r, g, b = (int(hexs[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_no_single_colour_survives_a_greyscale_image(ph):
    """⚠ **這一條是那個設計決定的證據，不是一個行為。**

    格線為什麼是兩色線（深色襯底 ＋ 亮芯）而不是「挑一個更好的顏色」：在一張
    SEM 影像的灰階範圍上，**每一個單色都會在某一段消失**。亮色輸在亮區、
    暗色輸在暗區，而一張 SEM 影像兩種都有。

    這一條釘住的是那個事實 —— 有人哪天想「把它改成一個漂亮的顏色就好」的時候，
    這裡會告訴他為什麼不行。
    """
    from d4t.ui.theme import TOKENS

    greys = ["#%02x%02x%02x" % (v, v, v) for v in (100, 115, 156, 169, 217)]
    for one in (TOKENS["accent"], TOKENS["success"], "#00e5ff", "#ffe000"):
        worst = min(_contrast(one, g) for g in greys)
        assert worst < 3.0, (one, worst, "單色居然到處都看得見？那就不必襯底了")


def test_the_two_tone_line_is_visible_everywhere(ph):
    """而兩色線就到處都在 —— 每一格取襯底與亮芯較好的那一個。

    3.0 是圖形元素的 WCAG 門檻。**一條在某些地方看不見的格線，比沒有格線更糟**
    （使用者會以為那裡沒有被切到）。
    """
    from d4t.ui.image_view import _CASING

    greys = ["#%02x%02x%02x" % (v, v, v) for v in (100, 115, 156, 169, 217)]
    worst = min(max(_contrast(_CASING, g), _contrast(ph.GRID_HEX, g))
                for g in greys)
    assert worst >= 3.0, (worst, ph.GRID_HEX, _CASING)


def test_the_helper_turns_the_two_tone_line_on_and_studio_does_not(win, ph):
    """⚠ **預設不開。** Studio 的區域框走同一支 `_paint_overlay`，而它們的顏色
    是有意義的（`region_hex` 一區一色）—— 統一換成青色會把那個意思洗掉。"""
    from d4t.ui.image_view import ImageView

    assert win.view.overlay_look() == (ph.GRID_HEX, True)
    plain = ImageView()
    try:
        assert plain.overlay_look() is None, "沒人要求就不要換樣子"
    finally:
        plain.deleteLater()


# --------------------------------------------------------------------------- #
# 15. 空狀態：使用者打開這個工具看到的第一個畫面（F120 第十五輪）
# --------------------------------------------------------------------------- #
def test_nothing_on_the_empty_screen_invites_a_press_it_cannot_answer(win, ph):
    """⚠ **鐵則 7「不 raise 不等於不記」的 UI 版。**

    空狀態下這些控制項全部按得動，而按下去：`Crop` 回 False **狀態列一個字
    都沒有**（按了像壞掉）；`Ruler` 真的打開量尺模式、還說「Drag across the
    image」—— 而沒有 image；週期欄收下 60、答案仍然是 `—`；`×2` 靜靜地沒反應。

    一顆按了什麼都不會發生、也不說為什麼的按鈕，變灰是那句「為什麼」最便宜的
    講法。
    """
    for w in win._needs_image():
        assert not w.isEnabled(), (w.objectName() or type(w).__name__)
    # 但入口一定要按得動，不然這個視窗就沒有出路了。
    assert win.btn_open.isEnabled() and win.btn_paste.isEnabled()
    # pixel size 不在裡面：先填機台的 nm/px 再開圖是合理的用法。
    assert win.spin_nm.isEnabled()


def test_the_controls_come_back_when_an_image_arrives(win, ph):
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    for w in win._needs_image():
        assert w.isEnabled(), (w.objectName() or type(w).__name__)


def test_the_pixel_size_prompt_fits_in_its_box(app, ph):
    """⚠ **一句被切掉的話比沒有話更糟。**

    這一格本來寫 `pixel size not known`（132 px），而框裡真正留給字的只有
    112 px —— 畫面上長出來的是 **`el size not known`**，一句看不懂又有點嚇人
    的話。順便釘住最長的真實值：`1234.567 nm/px` 本來也只差 5 px 就要被切。
    """
    from PySide6.QtGui import QFontMetrics

    from d4t.ui import theme

    theme.apply_theme(app)
    win = ph.PitchHelperWindow()
    try:
        win.spin_nm.ensurePolished()
        fm = QFontMetrics(win.spin_nm.font())
        room = win.spin_nm.maximumWidth() - 34      # 箭頭 20 ＋ padding 12 ＋ 邊框 2
        for text in (win.spin_nm.specialValueText(), "1234.567 nm/px"):
            assert fm.horizontalAdvance(text) <= room - 10, (
                text, fm.horizontalAdvance(text), room)
    finally:
        win.close()


def test_the_empty_canvas_says_what_to_do_and_says_it_once(win, ph):
    """⚠ **指令要在空間裡，不是在角落。**

    預設的 `(no image)` 只描述現況；而這個視窗空著的時候，唯一要做的事本來
    寫在工具列 11px 的灰字裡 —— 700×700 的畫布上卻只有一句「沒有影像」。

    而搬過去之後**工具列那一句要拿掉**：同一則訊息出現兩次，使用者會先花一秒
    確認那是不是兩件事。
    """
    assert "Drop an image here" in win.view._EMPTY_TEXT
    assert win.lab_source.text() == "", "同一句話不要講兩次"
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    assert "a.tif" in win.lab_source.text(), "載入之後它的工作是講檔名與尺寸"


# --------------------------------------------------------------------------- #
# 17. **答案先上畫面，證據隨後**（F120 第十七輪，使用者：「先做 1」）
# --------------------------------------------------------------------------- #
def test_the_answer_goes_out_before_the_evidence(app, ph):
    """⚠ **兩段，不是一段。**

    實測 4096²：量週期 2.14 s，疊圖找相位再 2.67 s —— 原本 `done` 是唯一的
    出口，所以一個 2.14 s 就算好的數字要在背景躺到 4.81 s 才上畫面。急著要
    period 的人等的是**週期**，不是「憑什麼相信它」。
    """
    img = tiles(px=60, py=44)
    w = ph._PitchWorker(img, ph.AXIS_BOTH)
    seen = []
    w.answer.connect(lambda m: seen.append(("answer", m)))
    w.done.connect(lambda m, gc, e: seen.append(("done", m, gc)))
    w.run()                                  # 同步跑（測試不開執行緒）
    assert [k[0] for k in seen] == ["answer", "done"], seen
    # **同一個量測，不是量兩次** —— 量兩次的話兩段可能給不一樣的數字。
    assert seen[0][1] is seen[1][1]
    assert seen[1][2] is not None, "證據那一段還是要回來"


def test_the_number_shows_before_the_grid_can_be_drawn(win, ph):
    """答案那一刻**格線不畫**：相位還不知道，畫在 0 上再跳掉是最糟的一種。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_answer(algo_template.measure_period(img))
    assert win.answer_text(), "量到了，右邊卻還是空的"
    assert win.lab_big.text() != ph.PITCH_UNSET
    assert win.view.overlay_count() == 0, "相位還不知道，不准先畫一組"
    # **不是留白** —— 留白會讓使用者以為格線壞了。
    assert win.caption.text() == ph.PHASE_PENDING


def test_a_cancelled_run_never_publishes_a_half_answer(app, ph):
    """停掉的那一次連**答案**也不出去（原本只有 `done` 那一段擋著）。"""
    img = tiles(px=60, py=44)
    w = ph._PitchWorker(img, ph.AXIS_BOTH)
    w.stop()
    seen = []
    w.answer.connect(lambda m: seen.append(m))
    w.done.connect(lambda m, gc, e: seen.append(("done", m, gc, e)))
    w.run()
    assert seen == [("done", None, None, "")], seen


# --------------------------------------------------------------------------- #
# 18. 鍵盤（F120 第十七輪，使用者：「先做 3」）
# --------------------------------------------------------------------------- #
def test_every_shortcut_is_bound_to_something_that_exists(win):
    """表上寫的每一條都真的綁上去了，而且不多綁。"""
    from PySide6.QtGui import QKeySequence

    for seq, name in win.SHORTCUTS:
        assert callable(getattr(win, name, None)), (seq, name)
    assert sorted(s.key().toString() for s in win._shortcuts) == sorted(
        QKeySequence(seq).toString() for seq, _ in win.SHORTCUTS)
    # ⚠ **Ctrl+C 一定要在裡面**：拿到一個數字之後的第一個反射動作就是它，
    # 而這個視窗的產出就是那個數字。
    assert win.key_for("copy_focused_or_answer") == "Ctrl+C"


def test_the_shortcuts_say_so_on_screen(win, ph):
    """⚠ **看不到的快捷鍵等於沒有。**

    這個視窗的使用者一分鐘內就走了 —— 沒有人會去翻說明找鍵。每一條都要在
    它那顆鈕的提示上。
    """
    from PySide6.QtWidgets import QWidget

    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    tips = " ".join(w.toolTip() for w in win.findChildren(QWidget))
    for seq, name in win.SHORTCUTS:
        assert seq in tips, ("沒有人在畫面上講這一顆鍵", seq, name)


def test_ctrl_c_does_not_steal_copy_from_an_input_box(app, win, ph):
    """⚠ `QShortcut` 比 `QLineEdit` 自己的標準鍵動作**先**處理。

    少了 `copy_focused_or_answer` 那道分支，使用者在 pixel size 那一格裡選了
    `45` 按 Ctrl+C，剪貼簿上會是**週期** —— 一個到處都能用的快捷鍵偷走了一個
    更小、更明確的動作。
    """
    from PySide6.QtGui import QGuiApplication

    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    # ⚠ **要 `show()`** —— 沒開出來的視窗上 `setFocus()` 不會產生
    # `focusWidget()`，於是這一條會兩邊都走到「複製答案」那一支而假綠。
    win.show()
    app.processEvents()
    clip = QGuiApplication.clipboard()

    clip.setText("")
    win.view.setFocus()
    app.processEvents()
    assert app.focusWidget() is win.view, "focus 沒進去，這一條會假綠"
    win.copy_focused_or_answer()
    assert clip.text() == win.axis_number(0), "焦點不在輸入框 ⇒ 複製答案"

    clip.setText("")
    win.spin_nm.setValue(4.5)
    win.spin_nm.setFocus()
    app.processEvents()
    win.spin_nm.lineEdit().selectAll()
    win.copy_focused_or_answer()
    assert clip.text() == win.spin_nm.lineEdit().selectedText(), (
        "選著字還是被搶走了", clip.text())


def test_ctrl_shift_c_copies_the_other_axis(win, ph):
    """兩軸兩顆鈕 ⇒ 兩個鍵（一個鍵配兩個輸入框是回到「複製一個貼不進去的字串」）。"""
    from PySide6.QtGui import QGuiApplication

    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    clip = QGuiApplication.clipboard()
    clip.setText("")
    win.copy_y()
    assert clip.text() == win.axis_number(1) != win.axis_number(0)
