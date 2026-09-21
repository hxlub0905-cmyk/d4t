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
    rows = ph.pitch_rows(_M(), ph.AXIS_AUTO, 2.5)
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
    win._on_done(algo_template.measure_period(img), None, "")
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
    rows = ph.pitch_rows(_M(), ph.AXIS_AUTO, 0.0, (120.0, None))
    assert rows[0][1] == "120"
    assert rows[0][3] != "92 / 100", "不准沿用量到的那個分數"
    assert rows[1][3] == "93 / 100", "沒改的那一軸照樣講它量到的信心"


def test_a_typed_period_with_no_score_says_so_instead_of_faking_one(ph):
    """還算不出分數的時候（還沒載圖）寫 ``yours``，**不寫 0**。"""
    rows = ph.pitch_rows(_M(), ph.AXIS_AUTO, 0.0, (120.0, None), (None, None))
    assert rows[0][3] == ph.CONF_TYPED


def test_a_typed_period_gets_its_own_score_when_there_is_one(ph):
    """使用者 2026-09-21：「自定義 period 右上可否也能算 confidence？」

    可以 —— 但那是**對他打的那個數字重問一次**的分數（`confidence_at`），
    不是量出來那個數字的分數。
    """
    rows = ph.pitch_rows(_M(), ph.AXIS_AUTO, 0.0, (120.0, None), (41.0, None))
    assert rows[0][3] == "41 / 100"


def test_a_typed_period_is_believed_even_where_the_measurement_was_not(ph):
    """使用者明講的一律相信 —— 否則畫面上會變成「我改了，但它不理我」。"""
    rows = ph.pitch_rows(_M(px=60.0, conf_x=11.0), ph.AXIS_AUTO, 0.0, (60.0, None))
    assert rows[0][1] == "60", "信心 11 但他自己打的，就該用"


def test_a_typed_period_is_converted_too(ph):
    rows = ph.pitch_rows(_M(), ph.AXIS_AUTO, 2.5, (120.0, None))
    assert rows[0][2] == "0.300 µm"


def test_typing_a_period_redraws_the_grid_at_once(win, ph):
    """同軸向那一條：**不能等相位搜尋回來**（見 `_on_override`）。"""
    from d4t.core.algo import template as algo_template

    img = tiles(px=60, py=44)
    win.set_image(img, "synthetic.tif")
    win._on_done(algo_template.measure_period(img), None, "")
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
    win._on_done(algo_template.measure_period(img), None, "")
    win.chips_axis.set_text(ph.AXIS_Y)
    win._on_axis(ph.AXIS_Y)

    assert win._flags() == (False, True)
    assert win.rows()[0][1] == ph.PITCH_NOT_USED
    # 只切橫線 ⇒ 一格 = 整張寬 × 44 ⇒ 格子數 = 480 // 44 = 10。
    # **畫出來的格子數要跟表格說的那一軸對得上** —— 兩邊各算各的那天，
    # 畫面會同時說兩件事。
    assert win.view.overlay_count() == 480 // 44


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
    _ready(win)
    win.spin_nm.setValue(2.5)
    text = win.answer_text()
    assert "X 60 px" in text and "0.150 µm" in text, text
    win.copy_answer()
    from PySide6.QtGui import QGuiApplication
    assert QGuiApplication.clipboard().text() == text


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
    answer_y = win.lab_big.mapTo(win, win.lab_big.rect().topLeft()).y()
    copy_y = win.btn_copy.mapTo(win, win.btn_copy.rect().topLeft()).y()
    units_y = win.spin_nm.mapTo(win, win.spin_nm.rect().topLeft()).y()
    assert answer_y < copy_y < units_y, (answer_y, copy_y, units_y)


def test_the_copy_button_says_what_it_will_copy(win, ph):
    """另一半答案：**tooltip 裡有那一行字本人**，不是「複製 pitch」。"""
    img = tiles(px=60, py=44)
    win.set_image(img, "a.tif")
    win._on_done(*_run(win, img), "")
    assert win.answer_text() in win.btn_copy.toolTip(), win.btn_copy.toolTip()


def test_typing_does_not_recompute_on_every_keystroke(win, ph):
    """使用者 2026-09-21：「我要輸入 45，但當我輸入到 4，就會強制 trigger 算 4」。

    ⚠ 中途那一次不只是浪費（疊一次格子是幾百毫秒），它還會**在畫面上閃一個
    錯的答案** —— 而這個視窗的全部內容就是那一個答案。
    """
    for sp in (win.spin_px, win.spin_py, win.spin_nm):
        assert not sp.keyboardTracking(), sp.objectName() or sp.suffix()


def test_force_both_says_how_it_differs_from_auto(ph):
    """使用者 2026-09-21：「Auto 跟 X+Y 差在哪裡？」

    差別是真的存在的（Auto 會丟掉信心不夠的那一軸），但 `X + Y` 這個字
    **只講了它做什麼，沒講它跟 Auto 差在哪** —— 而一個看不出差別的選項是
    一個陷阱，不是一個選擇。
    """
    assert ph.AXIS_LABELS[ph.AXIS_BOTH] == "Force both"
    assert "Auto" in ph.AXIS_HELP[ph.AXIS_BOTH]


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
