# F117 I15：Results 的第一欄不跟著橫捲走（2026-09-20）。
"""走查記的：表頭本來就固定，但 ``defect`` 那一欄會跟著橫捲出畫面。

**一列數字沒有 id 就只是一列數字** —— 使用者正在做的事（「這一顆為什麼判成
這樣」）在那一刻斷掉了。Qt 沒有內建的凍結欄，標準解法是疊第二個 view 上去
（`ui/frozen_column.py`）。

⚠ **共用 selection model 是關鍵的那一半**：各自一份的話，點左邊那一欄選到的
列跟右邊亮起來的不是同一列 —— 而那是一個「看起來只是有點怪」的錯。
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
from d4t.ui.results_table import ResultsTablePane      # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _rows(n=100):
    return [{"defect_id": str(i), "ok": True, "score": float(i), "bin": i % 2,
             "features": {"glv_max": float(i), "glv_min": float(i) / 2,
                          "area_px": float(i) * 3}} for i in range(n)]


@pytest.fixture()
def pane(qapp):
    p = ResultsTablePane()
    p.resize(500, 160)
    p.table.set_results(_rows())
    p.show()
    qapp.processEvents()
    yield p
    p.deleteLater()


# --------------------------------------------------------------------------- #
# 1. 它真的是同一份資料的第二個視窗
# --------------------------------------------------------------------------- #
def test_it_shares_the_model_and_the_selection(pane):
    """⚠ **selection 共用**，不然左右兩邊會亮不同的列。"""
    fz, table = pane.frozen, pane.table
    assert fz.model() is table.model()
    assert fz.selectionModel() is table.selectionModel()


def test_it_shows_only_the_first_column_and_the_host_keeps_it(pane):
    """⚠ **主表那一欄照樣留著**（不 `setColumnHidden`）。

    藏起來的話它的寬度就不再參與版面，而右邊的內容會往左滑到凍結欄底下。
    """
    fz, table = pane.frozen, pane.table
    shown = [c for c in range(table.model().columnCount())
             if not fz.isColumnHidden(c)]
    assert shown == [fz.column()]
    assert not table.isColumnHidden(fz.column())


# --------------------------------------------------------------------------- #
# 2. 上下綁在一起、左右不綁
# --------------------------------------------------------------------------- #
def test_scrolling_down_moves_both(pane):
    bar = pane.table.verticalScrollBar()
    assert bar.maximum() > 0, "前提：這一批要多到捲得動"
    bar.setValue(12)
    assert pane.frozen.verticalScrollBar().value() == 12
    # 反過來也要（使用者的滾輪可能停在凍結那一欄上）。
    pane.frozen.verticalScrollBar().setValue(30)
    assert bar.value() == 30


def test_scrolling_sideways_leaves_it_where_it_is(pane, qapp):
    """**這就是 I15 那一條。** 橫捲到第五欄，`defect` 還在原地。"""
    fz = pane.frozen
    before = fz.geometry()
    bar = pane.table.horizontalScrollBar()
    if bar.maximum() <= 0:
        pytest.skip("這個寬度下沒有橫向捲動可測")
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert fz.geometry() == before, "凍結欄跟著橫捲跑掉了"
    assert fz.horizontalScrollBar().value() == 0


# --------------------------------------------------------------------------- #
# 3. 跟著主表一起重排
# --------------------------------------------------------------------------- #
def test_resizing_the_pane_keeps_it_glued(pane, qapp):
    """⚠ 接法是**包住 `resizeEvent`**，不是叫呼叫端記得呼叫 `sync()`。

    「記得呼叫」那一版會在某一條沒人想到的路徑上漏掉，而症狀是凍結的那一欄
    停在錯的寬度上 —— 看起來像畫面裂了。
    """
    fz = pane.frozen
    pane.resize(900, 420)
    qapp.processEvents()
    assert fz.height() > 0
    assert fz.width() == pane.table.columnWidth(fz.column())


def test_widening_the_first_column_widens_the_frozen_one(pane, qapp):
    fz = pane.frozen
    pane.table.setColumnWidth(fz.column(), 140)
    qapp.processEvents()
    assert fz.width() == 140
    assert fz.columnWidth(fz.column()) == 140


def test_it_hides_itself_when_the_column_is_hidden(pane, qapp):
    """那一欄被摺起來的時候（`visible_columns`），凍結的那一層也要收。"""
    fz = pane.frozen
    pane.table.setColumnHidden(fz.column(), True)
    fz.sync()
    assert fz.isHidden()
    pane.table.setColumnHidden(fz.column(), False)
    fz.sync()
    assert not fz.isHidden()


def test_selecting_in_one_shows_in_the_other(pane, qapp):
    """點凍結欄的一列 = 點主表的同一列（共用 selection 的實際效果）。"""
    pane.frozen.selectRow(4)
    qapp.processEvents()
    picked = {i.row() for i in pane.table.selectionModel().selectedRows()}
    assert picked == {4}
    assert pane.table.selectionModel().currentIndex().row() == 4
    assert pane.frozen.selectionBehavior() == pane.table.selectionBehavior() \
        == pane.table.SelectionBehavior.SelectRows
