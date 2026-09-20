# F117 E2：縮圖的色條與它的圖例講同一件事（2026-09-20）。
"""走查記的是「色條沒有圖例」。**複查後那一半已經成立**：判定列
（`VerdictBand`）就在同一個視窗的最上面、而且不在 splitter 裡（拖不掉），
一列一個類別、帶著顏色、名字、bin 與顆數 —— 那就是圖例。

⚠ **但它只有在兩邊顏色真的一樣的時候才是圖例。** 而那正是會安靜漂掉的東西：
兩邊都走 `decide_tree.leaf_color`，可是 bin 0 那一格的顏色是**呼叫端給的**
（畫面要主題的 `seg_disabled`、報表要自己的 `NUISANCE_HEX`）。有人在其中
一邊少傳一個參數，圖例就開始說謊 —— 而畫面上看起來完全正常。

這一支就是那道關。

⚠ 寫這一條的時候我自己先踩了一次：第一版的探針叫的是
`core.pipeline.decide_tree.verdict_rows`（核心那一份），量出來「不一樣」——
而真正在畫面上跑的是 `ui.verdict_band.verdict_rows`（它會補主題那兩個顏色）。
**量錯對象的探針會給出一個很有說服力的錯誤答案。**
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

from d4t.core.pipeline.recipe import (                # noqa: E402
    DecideSpec, TreeLeaf, TreeStep,
)
from d4t.ui import theme as theme_mod                 # noqa: E402
from d4t.ui.gallery import bin_hex, caption_lines_of  # noqa: E402
from d4t.ui.verdict_band import verdict_rows          # noqa: E402


def _decide():
    return DecideSpec(tree=TreeStep(
        when="x > 1",
        yes=TreeLeaf(bin=1, label="a spot stands out", outcome="bad"),
        no=TreeStep(when="y > 2",
                    yes=TreeLeaf(bin=2, label="two spots", outcome="bad"),
                    no=TreeLeaf(bin=0, label="nothing stands out",
                                outcome="good"))))


def _tiles():
    return [{"defect_id": "1", "ok": True, "bin": 1, "score": 9.0,
             "cls": "a spot stands out", "features": {}},
            {"defect_id": "2", "ok": True, "bin": 2, "score": 5.0,
             "cls": "two spots", "features": {}},
            {"defect_id": "3", "ok": True, "bin": 0, "score": 0.1,
             "cls": "nothing stands out", "features": {}}]


@pytest.fixture(scope="module", params=["light", "dark"])
def qapp(request):
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, request.param)
    yield app
    theme_mod.apply_theme(app, "light")


# --------------------------------------------------------------------------- #
# 1. 圖例真的對得上
# --------------------------------------------------------------------------- #
def test_every_tile_colour_is_in_the_legend(qapp):
    """**一個 bin 一個顏色，兩個地方同一個。**

    不一樣的那天，使用者照著判定列的顏色去縮圖牆上找，會找到錯的那一群。
    """
    band = {int(r["bin"]): str(r["colour"]).lower()
            for r in verdict_rows(_decide(), _tiles())
            if r.get("bin") is not None}
    assert band, "前提：判定列真的畫得出幾列"
    for item in _tiles():
        assert bin_hex(item).lower() == band[int(item["bin"])], \
            "bin %s：縮圖 %s ≠ 判定列 %s" % (item["bin"], bin_hex(item),
                                           band[int(item["bin"])])


def test_the_nuisance_bin_is_the_one_that_drifts(qapp):
    """⚠ **bin 0 那一格的顏色是呼叫端給的** —— 這一條盯著它。

    兩邊都走 `leaf_color`，但那一格不是調色盤算出來的：畫面要主題的
    `seg_disabled`，報表要 `NUISANCE_HEX`。少傳一個參數，圖例就開始說謊。
    """
    from d4t.core.pipeline import decide_tree
    from d4t.ui.theme import TOKENS

    zero = {"defect_id": "0", "ok": True, "bin": 0, "score": 0.0,
            "features": {}}
    assert bin_hex(zero).lower() == str(TOKENS["seg_disabled"]).lower()
    assert bin_hex(zero).lower() != decide_tree.NUISANCE_HEX.lower(), \
        "換主題之後這一條要跟著換 —— 兩個一樣的話這個測試沒有在測東西"


# --------------------------------------------------------------------------- #
# 2. 顏色不是唯一的通道
# --------------------------------------------------------------------------- #
def test_the_tile_writes_the_class_and_the_bin_in_words(qapp):
    """色盲、投影機、黑白列印都要讀得到（這一頁本來就有的規矩）。"""
    top, sub = caption_lines_of(_tiles()[0])
    assert top == "a spot stands out"
    assert "bin 1" in sub and "#1" in sub


def test_a_failed_defect_is_not_a_class(qapp):
    """跑失敗的那一顆要一眼看得出來，而且它不假裝自己是一個類別（R6）。"""
    top, sub = caption_lines_of({"defect_id": "9", "ok": False, "bin": None,
                                 "features": {}})
    assert top == "FAILED" and sub == "#9"
