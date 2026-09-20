# F117 E4：分布圖看得出刻度，也看得出判定切在哪裡（2026-09-20）。
"""走查記的三件：**只有 min/max 刻度、沒有圖例、沒畫判定門檻**。

複查之後是兩件：

* **圖例已經有了** —— 判定列（`VerdictBand`）就在同一個視窗最上面，一列一個
  類別帶著顏色（`tests/test_ui_tile_legend.py` 守著兩邊顏色一致）。
* **門檻**：看「Score」的時候那條拖得動的線本來就在。缺的是**看別的數字的
  時候**：這張圖問的正是「這個特徵分不分得開、門檻該設哪」，而判定樹上
  **已經有一個答案**了 —— 看不到它，使用者是在一張沒有參考線的圖上重新猜。

⚠ **樹上那幾刀與門檻線長得不一樣，而且不能混**：門檻拖得動（二元那一條），
樹上的刀唯讀（要改去樹上改）。一條看起來能拖、拖了卻什麼都不會發生的線，
比沒有線更糟 —— 這一頁本來就寫著這句話。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from d4t.core.pipeline.decide_tree import cuts_on     # noqa: E402
from d4t.core.pipeline.recipe import (                # noqa: E402
    DecideSpec, Rule, TreeLeaf, TreeStep,
)


def _tree():
    return DecideSpec(tree=TreeStep(
        when="glv_max > 42",
        yes=TreeStep(when="glv_max > 90",
                     yes=TreeLeaf(bin=2, label="big"),
                     no=TreeLeaf(bin=1, label="spot")),
        no=TreeLeaf(bin=0, label="clean")))


# --------------------------------------------------------------------------- #
# 1. 哪幾刀切在這個數字上（純函式，不用 Qt）
# --------------------------------------------------------------------------- #
def test_it_finds_every_cut_on_that_number_top_down():
    assert cuts_on(_tree(), "glv_max") == [(42.0, "glv_max > 42"),
                                           (90.0, "glv_max > 90")]


def test_another_number_has_no_cuts():
    assert cuts_on(_tree(), "glv_min") == []
    assert cuts_on(_tree(), "") == []
    assert cuts_on(None, "glv_max") == []


def test_the_same_value_twice_is_drawn_once():
    """兩條問句切在同一個位置 —— 畫兩條重疊的線只是把它畫粗。"""
    d = DecideSpec(tree=TreeStep(
        when="a > 5",
        yes=TreeLeaf(bin=1),
        no=TreeStep(when="a > 5", yes=TreeLeaf(bin=2), no=TreeLeaf(bin=0))))
    assert cuts_on(d, "a") == [(5.0, "a > 5")]


def test_a_rules_list_is_read_too():
    """舊寫法（平面規則）也要看得到 —— 它是樹的特例，不是另一種東西。"""
    d = DecideSpec(rules=[Rule(when="a > 3", bin=1),
                          Rule(when="b > 9", bin=2)])
    assert cuts_on(d, "a") == [(3.0, "a > 3")]
    assert cuts_on(d, "b") == [(9.0, "b > 9")]


def test_a_condition_nobody_can_place_is_not_guessed():
    """⚠ **複合條件拆不出一個位置，而猜一個畫上去比不畫糟得多。**

    那條線會被當成真的 —— 使用者照著它調門檻，而它指的地方不存在。
    """
    d = DecideSpec(tree=TreeStep(when="(a > 5) * (b < 2)",
                                 yes=TreeLeaf(bin=1), no=TreeLeaf(bin=0)))
    assert cuts_on(d, "a") == []
    assert cuts_on(d, "b") == []


# --------------------------------------------------------------------------- #
# 2. 畫面：刻度與那幾刀
# --------------------------------------------------------------------------- #
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

from d4t.ui import theme as theme_mod                 # noqa: E402
from d4t.ui.histogram import HistogramWidget          # noqa: E402
from d4t.ui.results import ResultsWindow              # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def test_the_axis_has_more_than_its_two_ends(qapp):
    """⚠ 兩個端點答不出「這一堆大概落在哪」，而那正是要問的。"""
    assert HistogramWidget.X_TICKS >= 4


def test_the_cuts_are_read_only_state_on_the_widget(qapp):
    w = HistogramWidget()
    try:
        assert w.cuts() == []
        w.set_cuts([(42.0, "glv_max > 42")])
        assert w.cuts() == [(42.0, "glv_max > 42")]
        w.set_cuts(None)
        assert w.cuts() == []
    finally:
        w.deleteLater()


def test_the_results_window_draws_the_tree_cuts_for_the_shown_number(qapp):
    win = ResultsWindow()
    try:
        rows = [{"defect_id": str(i), "ok": True, "bin": i % 3,
                 "score": float(i), "features": {"glv_max": float(i * 10)}}
                for i in range(10)]
        win.set_table(rows)
        win.set_features(["glv_max"], default="glv_max")
        win.set_verdict(_tree(), rows)
        assert win.histogram.cuts() == [(42.0, "glv_max > 42"),
                                        (90.0, "glv_max > 90")]

        # ⚠ 看「Score」的時候不畫：那一格有自己**拖得動**的門檻線，兩種線
        # 混在一起會讓人以為樹上那幾刀也拖得動。
        win.show_feature(win.SCORE)
        assert win.histogram.cuts() == []
    finally:
        win.close()
