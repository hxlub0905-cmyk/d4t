# F117 A4／C1／I8／B3：讀得到（2026-09-20）。
"""四條走查，同一個病灶：**畫面上最重要的那個東西被次要的東西擠掉了。**

* **A4** Tune 的畫布只剩約 300 px 高，七張卡縮到 50%，副標與埠名讀不到 ——
  而同一份 recipe 在 Build 的 61% 是讀得到的。
* **C1** Features 面板的**數值**被長說明推到可視範圍外：第一眼只看到名字與
  說明，而數字正是那個面板存在的理由。
* **I8** 參數區的段標比它底下的欄位名**小**——一個比內容小的標題讀起來像
  註腳，眼睛會從它上面滑過去。
* **B3** 卡片說明一行截斷，而一行的省略號看不出後面還有多少。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel     # noqa: E402

from d4t.ui import theme as theme_mod                  # noqa: E402
from d4t.ui import workbench as wb                     # noqa: E402
from d4t.ui.feature_panel import (                     # noqa: E402
    NAME_W, VALUE_W, FeaturePanel, panel_model,
)
from d4t.ui.fields import _HintLabel, _wrap_elided     # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


# --------------------------------------------------------------------------- #
# A4：Tune 的畫布分得到的高度
# --------------------------------------------------------------------------- #
def test_the_tune_canvas_gets_about_half(qapp):
    """⚠ **那個數字是評審給的，不是我挑的。**

    走查量到 Tune 的畫布縮到 50%、而 Build 的 61% 讀得到。縮放大致跟受限的
    那一邊成正比，50% → 61% 是 ×1.22，`0.40 × 1.22 ≈ 0.49`。
    """
    assert wb.CANVAS_SHARE_TUNE >= 0.48


def test_the_small_screen_floor_did_not_move(qapp):
    """⚠ **保底那一格沒有跟著動。**

    它是小螢幕的最後一道防線（768 高的螢幕上 200 就是上一輪評審說的 35%），
    而這一輪問的是「預設分得夠不夠」，不是「最壞能多壞」。
    """
    assert wb.CANVAS_MIN_PX == 200


def test_the_image_never_pushes_the_gauges_below_the_settings(qapp):
    """⚠ **這兩個數字是綁在一起的，而綁在一起的理由是 U8。**

    儀表住在右欄的下格、設定區住在中欄的下格，而 U8 的驗收是「那兩塊左右
    相鄰、同一條視線」。儀表的上緣＝影像的高度，設定區的上緣＝畫布的高度 ——
    影像佔得比畫布多的那一刻，儀表整塊掉到設定區下面去。

    A4 把畫布從 0.40 升到 0.50 的時候，這件事當場被
    `test_ui_layout_modes::test_they_are_actually_side_by_side_on_screen`
    抓到了 —— 那一條真的去量座標，所以它抓得到。這一條是同一件事的便條：
    **動其中一個就要想到另一個。**
    """
    assert wb.IMAGE_SHARE_TUNE < wb.CANVAS_SHARE_TUNE


# --------------------------------------------------------------------------- #
# C1：數值看得到
# --------------------------------------------------------------------------- #
def test_the_value_is_visible_without_scrolling_sideways(qapp):
    """**數字是這個面板存在的理由** —— 它不能排在一段可長可短的說明後面。"""
    panel = FeaturePanel()
    panel.resize(320, 240)
    try:
        panel.set_model(panel_model({"glv_median": 118.42}, {}))
        panel.show()
        qapp.processEvents()
        labels = [w for w in panel.findChildren(QLabel) if w.text()]
        by_text = {w.text(): w for w in labels}
        assert "118.42" in by_text, [w.text() for w in labels]
        value = by_text["118.42"]
        right = value.mapTo(panel, value.rect().topRight()).x()
        assert right <= panel.width(), \
            "值的右緣跑出面板外了（要橫捲才看得到 —— 那就是 C1）"
    finally:
        panel.deleteLater()


def test_the_columns_have_a_width_so_the_values_line_up():
    """名字有最小寬度，值才排得成一欄。

    ⚠ 它是**最小**不是固定：比 `NAME_W` 長的名字照樣把自己那一列的值往右推
    —— 截名字比讓值跳更糟，而名字是使用者要打進分數表達式的字。
    """
    assert NAME_W >= 120 and VALUE_W >= 60


# --------------------------------------------------------------------------- #
# I8：段標不比它底下的東西小
# --------------------------------------------------------------------------- #
def test_a_heading_is_not_smaller_than_what_it_heads(qapp):
    """一個比內容小的標題讀起來像註腳，眼睛會從它上面滑過去。"""
    css = theme_mod.build_stylesheet()
    assert "QLabel#paramSection" in css, "找不到那一段 —— 這條測試沒在測東西"
    block = css.split("QLabel#paramSection")[1].split("}")[0]
    size = int(block.split("font-size:")[1].split("px")[0].strip())
    body = int(str(theme_mod.TOKENS["font_body"]).replace("px", ""))
    assert size >= body, "段標 %dpx 比欄位名 %dpx 小" % (size, body)


# --------------------------------------------------------------------------- #
# B3：卡片說明兩行
# --------------------------------------------------------------------------- #
LONG = ("Measure gray level statistics inside each region - the mean, the "
        "spread, and how far the odd box is from the others.")


def _hint(qapp, text, width, lines=2):
    """一個**真的是那個寬度**的 `_HintLabel`。

    ⚠ **`resize()` 對一個從來沒有 `show()` 過的 widget 不會送出 resizeEvent**
    （Qt 把它延到第一次顯示）。第一版的這幾條就是這樣：`resize(260, 40)` 之後
    量到的其實是**出生時那個 640 px**，而 640 剛好也折成兩行 —— 測試是綠的，
    而它量的不是它說的那個東西。

    這跟 F117 D4 那次「字界」符號被吃掉是同一類的錯：**一條只會綠的測試比沒有測試
    糟，它讓人以為那件事有人在看。**
    """
    lab = _HintLabel(text, max_lines=lines)
    lab.show()
    lab.resize(width, 40)
    qapp.processEvents()
    return lab


def test_a_long_card_help_gets_two_lines(qapp):
    lab = _hint(qapp, LONG, 260)
    one = _hint(qapp, LONG, 260, lines=1)
    try:
        assert len(lab.text().splitlines()) == 2, lab.text()
        # 兩行看得到的字要比一行多（不然這一輪什麼都沒買到）。
        assert len(lab.text()) > len(one.text())
    finally:
        lab.deleteLater()
        one.deleteLater()


def test_a_short_one_is_left_alone(qapp):
    lab = _hint(qapp, "Short one.", 260)
    try:
        assert lab.text() == "Short one."
        assert "…" not in lab.text()
    finally:
        lab.deleteLater()


def test_it_still_says_there_is_more(qapp):
    """⚠ 兩行**不是**「全部都看得到」—— 放不下的還是要有省略號。

    沒有那個記號的話，被切掉的那半句看起來像作者只寫了半句。

    ⚠ **寬度從字型算出來，不寫死 px**：字型換一個，寫死的那個數字就換一個
    意思，而這一條要問的是「放不下的時候」。
    """
    lab = _HintLabel(LONG, max_lines=2)
    narrow = max(60, lab.fontMetrics().horizontalAdvance(LONG) // 6)
    lab.deleteLater()
    lab = _hint(qapp, LONG, narrow)
    try:
        assert lab.text().endswith("…"), lab.text()
    finally:
        lab.deleteLater()


def test_it_breaks_between_words_not_inside_one(qapp):
    """⚠ Qt 硬切的結果看起來像畫面壞掉（`canvas._draw_elided` 記過同一件事）。"""
    lab = _hint(qapp, LONG, 260)
    try:
        first = lab.text().splitlines()[0]
        assert LONG.startswith(first), "第一行不是原句的字首 —— 切在字中間了"
        assert not first.endswith(" ")
    finally:
        lab.deleteLater()


def test_the_wrapper_handles_nothing_gracefully(qapp):
    lab = _hint(qapp, "", 260)
    try:
        assert lab.text() == ""
        assert _wrap_elided("", lab.fontMetrics(), 100, 2) == ""
    finally:
        lab.deleteLater()
