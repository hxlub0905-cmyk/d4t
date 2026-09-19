# F117 G8：圖的視窗不准安靜地畫別張卡的數字（2026-09-20）。
"""走查記的是「選著 GLV 卡開均勻度圖表視窗是空白」。重現之後是**兩件事**：

1. **空狀態沒講怎麼辦。** 還沒跑過試跑的時候四張圖都是空的，而那一行字只寫
   ``Nothing to plot yet`` —— 講完了「是什麼」，沒講「接下來按什麼」。四張空
   圖配一句沒有下一步的話，讀起來像壞掉了（推廣鐵則）。
2. **停在別張卡的數字上，而畫面上一個字都沒說。** 這個視窗只有「Charts
   folder」那張卡餵得動；選了別張卡之後 `_refresh_charts_window` 安靜地
   ``return``，於是視窗還亮著、還畫著上一張卡的數字。那正是這個 repo 記過
   七次的「跑得完、有數字、而且是錯的」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

from d4t.ui import studio as studio_mod               # noqa: E402
from d4t.ui import theme as theme_mod                 # noqa: E402
from d4t.ui.uniformity_window import UniformityWindow  # noqa: E402

RECIPE = REPO / "recipes" / "one-image-uniformity.json"
SERIES = {"metric": "glv_mean",
          "groups": [{"name": "cells", "values": [1.0, 2.0, 3.0]}]}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def win(qapp):
    w = UniformityWindow()
    yield w
    w.deleteLater()


# --------------------------------------------------------------------------- #
# 1. 空的時候要講下一步
# --------------------------------------------------------------------------- #
def test_an_empty_window_says_what_to_press_next(win):
    win.set_context({})
    text = win.head.text()
    assert "Nothing to plot yet" in text
    assert "run a trial" in text, \
        "講完了「是什麼」沒講「怎麼辦」—— 四張空圖配這句話讀起來像壞掉了"


# --------------------------------------------------------------------------- #
# 2. 畫的是誰的數字要說出來
# --------------------------------------------------------------------------- #
def test_it_says_whose_numbers_are_on_screen(win):
    win.set_context(SERIES, metric="glv_mean")
    following = win.head.text()
    assert "glv_mean" in following and "from" not in following

    win.set_stale("Charts folder")
    assert "Charts folder" in win.head.text()
    assert "select that card" in win.head.text()
    # 數字**沒有變** —— 錯的不是資料，是它看起來像在講現在選的那一張卡。
    assert "1 region(s), 3 box(es)" in win.head.text()


def test_feeding_it_again_means_it_caught_up(win):
    win.set_context(SERIES, metric="glv_mean")
    win.set_stale("Charts folder")
    assert win.stale_owner() == "Charts folder"
    win.set_context(SERIES, metric="glv_mean")   # 又有人餵它了
    assert win.stale_owner() == "", "餵了新資料還說自己過期，那句話就沒人信了"


def test_nothing_to_plot_beats_the_stale_note(win):
    """兩句都成立的時候講**空的**那一句 —— 使用者的下一步是跑試跑。"""
    win.set_context({})
    win.set_stale("Charts folder")
    assert "run a trial" in win.head.text()
    assert "select that card" not in win.head.text()


# --------------------------------------------------------------------------- #
# 3. 接上主視窗：選別張卡 → 視窗自己說出來
# --------------------------------------------------------------------------- #
def test_selecting_another_card_marks_the_window_stale(qapp):
    w = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert w.load_recipe_path(str(RECIPE), sync=True)
        w.select_node("charts")
        w.gauges._on_charts_requested()
        chart_win = w.gauges._charts_window
        assert chart_win is not None and chart_win.stale_owner() == ""

        w.select_node("glv")          # GLV 餵不動這個視窗
        assert chart_win.stale_owner(), \
            "選了別張卡，視窗還畫著上一張的數字而一個字都沒說"
    finally:
        w.close()
