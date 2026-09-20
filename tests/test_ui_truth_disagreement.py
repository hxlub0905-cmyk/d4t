# F117 E1：判定跟答案對不上的那幾列要自己跳出來（2026-09-20）。
"""走查記的：有 ground truth 時上面寫著 `missed 4`，但表上有 `truth` 欄卻
**沒有把那四列標出來** —— 要自己逐列比。

而「逐列比」正是這張表存在的理由該替他做掉的事。

⚠ **判準跟正確率那一行是同一條**（`export/report._confusion` 的預設：
``bin != 0`` 算「判定為真缺陷」）。兩邊各訂一套的那天，表上紅著的列數會跟
上面寫的數字對不起來，而沒有人知道哪一個是對的。

⚠ **字也要講**（U13）：紅色對色覺缺陷者不可分辨，而這一欄正是「這一顆判對
了沒」唯一的答案。顏色是第二個通道，不是唯一的。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                          # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from d4t.ui import theme as theme_mod                  # noqa: E402
from d4t.ui.results_table import (                     # noqa: E402
    TRUTH_COLUMN, ResultsTablePane,
)

#: 五種情況各一顆：判對、漏抓、誤殺、沒標、跑失敗。
ROWS = [
    {"defect_id": "1", "ok": True, "score": 9.0, "bin": 1, "features": {}},
    {"defect_id": "2", "ok": True, "score": 0.1, "bin": 0, "features": {}},
    {"defect_id": "3", "ok": True, "score": 8.0, "bin": 1, "features": {}},
    {"defect_id": "4", "ok": True, "score": 0.2, "bin": 0, "features": {}},
    {"defect_id": "5", "ok": False, "score": None, "bin": None, "features": {}},
]
TRUTH = {"1": True, "2": True, "3": False, "5": True}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def model(qapp):
    pane = ResultsTablePane()
    pane.table.set_results(ROWS, truth=TRUTH)
    yield pane.table.model()
    pane.deleteLater()


def _truth_index(model, row):
    return model.index(row, model._columns.index(TRUTH_COLUMN))


# --------------------------------------------------------------------------- #
# 1. 哪幾列算判錯
# --------------------------------------------------------------------------- #
def test_it_finds_the_two_that_disagree(model):
    assert [model.disagrees(r) for r in range(model.rowCount())] \
        == [False, True, True, False, False]


def test_a_defect_that_never_ran_is_not_a_wrong_verdict(model):
    """⚠ 第 5 顆標了 real、而它**跑失敗了** —— 那不是判錯，是沒得比。

    把它算成判錯的話，正確率那一行與這裡會開始吵架 —— 而使用者會去查一個
    不存在的問題。
    """
    assert model.disagrees(4) is False


def test_an_unlabelled_defect_is_not_a_wrong_verdict(model):
    """沒標答案的那一顆（第 4 顆）也不是判錯。"""
    assert model.disagrees(3) is False


# --------------------------------------------------------------------------- #
# 2. 畫面上看得出來 —— 而且不只靠顏色
# --------------------------------------------------------------------------- #
def test_the_cell_says_what_went_wrong_in_words(model):
    """⚠ **U13**：顏色是第二個通道，字才是第一個。"""
    assert model.data(_truth_index(model, 1), Qt.DisplayRole) \
        == "real · called nuisance"
    assert model.data(_truth_index(model, 2), Qt.DisplayRole) \
        == "nuisance · called real"
    # 判對的那一顆照舊只寫答案 —— 每一列都加一句的話那句話就沒人看了。
    assert model.data(_truth_index(model, 0), Qt.DisplayRole) == "real"


def test_the_cell_is_painted_too(model):
    """顏色是冗餘的第二個訊號，不是唯一的。"""
    assert model.data(_truth_index(model, 1), Qt.BackgroundRole) is not None
    assert model.data(_truth_index(model, 0), Qt.BackgroundRole) is None


def test_the_tooltip_explains_the_two_sides(model):
    tip = model.data(_truth_index(model, 1), Qt.ToolTipRole)
    assert "bin 0" in tip and "nuisance" in tip and "real" in tip


# --------------------------------------------------------------------------- #
# 3. 數字在表頭上，跟底下紅著的格子是同一份
# --------------------------------------------------------------------------- #
def test_the_header_says_how_many(model):
    col = model._columns.index(TRUTH_COLUMN)
    head = model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
    assert head == "truth (2 wrong)"
    assert head.count("2") == 1
    # 表頭的數字 == 真的紅著的格子數（各算一次的那天它們會分岔）。
    assert model.wrong_count() == sum(
        1 for r in range(model.rowCount())
        if model.data(_truth_index(model, r), Qt.BackgroundRole) is not None)


def test_no_answers_means_no_count_in_the_header(qapp):
    """一顆都沒標的時候表頭就是 `truth` —— 不要掛一個永遠是 0 的數字。"""
    pane = ResultsTablePane()
    try:
        pane.table.set_results(ROWS, truth={})
        m = pane.table.model()
        col = m._columns.index(TRUTH_COLUMN)
        assert m.headerData(col, Qt.Horizontal, Qt.DisplayRole) == "truth"
    finally:
        pane.deleteLater()
