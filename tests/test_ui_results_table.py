# 逐顆的表（R7，2026-08-24）—— 200 顆的時候一牆縮圖掃不動。
"""使用者：「目前的 results panel 太簡略了」。

這一份鎖住的是：

* 欄位跟 CSV **同一份來源**（不是抄第二份 —— 抄的那一份會漂，而漂掉的時候
  「畫面上的表」與「匯出的檔案」是兩個不同的東西）；
* **算不出來的那一格留白**，不是 0、也不是 NaN（F19 那一條）；
* 排序時 ``None`` **一律排到最後**，不管升冪降冪；
* 失敗的那幾顆看得見，而且說得出**為什麼**；
* 這張表是**唯讀**的（「看結果」與「編結果」是兩件事）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QApplication  # noqa: E402

from d4t.core.export.report import BASE_COLUMNS, feature_keys  # noqa: E402
from d4t.ui import theme as theme_mod  # noqa: E402
from d4t.ui.results_table import ResultsTable, table_columns  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _results():
    return [
        {"defect_id": "1", "ok": True, "bin": 2, "score": 0.42,
         "features": {"glv": 90.0, "mad": 1.25}},
        {"defect_id": "2", "ok": True, "bin": 0, "score": 0.10,
         "features": {"glv": 10.0}},                       # mad 沒量到
        {"defect_id": "3", "ok": False, "bin": None, "score": None,
         "error": "subtract: shapes differ", "features": {}},
    ]


def _table(qapp, results=None, names=None):
    t = ResultsTable()
    t.set_results(_results() if results is None else results,
                  {"1": "bright", "2": "nuisance"} if names is None else names)
    return t


# --------------------------------------------------------------------------- #
# 欄位
# --------------------------------------------------------------------------- #
def test_the_columns_come_from_the_same_place_as_the_csv():
    """``defect_id · error · score · bin`` ＋ 特徵欄，全部來自 `report`。

    抄第二份的那一份會漂，而漂掉的時候使用者看到的表跟他匯出的檔案是兩個
    不同的東西 —— 而他不會知道是哪一個錯了。
    """
    cols = table_columns(_results())
    for c in BASE_COLUMNS:
        if c == "ok":
            continue        # 0/1 那一欄在畫面上是雜訊（顏色與 error 講同一件事）
        assert c in cols, (c, cols)
    for f in feature_keys(_results()):
        assert f in cols, (f, cols)


def test_the_class_column_sits_next_to_the_id():
    """**它是這一顆判成了什麼**，跟 id 一起看才有意義。

    排在最後面等於要橫向捲過整排特徵才看得到 —— 而那正是使用者第一個想知道
    的東西（R5 在縮圖上做的是同一件事）。
    """
    cols = table_columns(_results())
    assert cols[cols.index("defect_id") + 1] == "class"


def test_the_class_name_is_the_one_the_user_typed(qapp):
    t = _table(qapp)
    assert [t.cell_text(i, "class") for i in range(3)] == \
        ["bright", "nuisance", ""]


# --------------------------------------------------------------------------- #
# 沒量到的那一格
# --------------------------------------------------------------------------- #
def test_a_number_that_was_not_measured_is_blank(qapp):
    """**留白，不是 0、也不是 NaN**（F19）。

    0 是一個量到的值，而「沒量到」不是 —— 兩件事在同一欄裡分不出來的話，
    照那一欄排序、算平均、畫分布全部都會錯。
    """
    t = _table(qapp)
    assert t.cell_text(1, "mad") == ""
    assert t.cell_text(0, "mad") == "1.25"


@pytest.mark.parametrize("order,first", [(Qt.AscendingOrder, "10"),
                                         (Qt.DescendingOrder, "90")])
def test_missing_values_sort_last_either_way(qapp, order, first):
    """「沒量到」不是一個小的值。

    排在最前面的話，一張照數字排的表最上面全部是空白格 —— 而使用者要看的
    正是最大／最小的那幾顆。跟 Gallery 同一條規矩。
    """
    t = _table(qapp)
    t._model.sort(t.columns().index("mad"), order)
    col = [t.cell_text(i, "mad") for i in range(t.row_count())]
    assert col[-1] == "", col
    t._model.sort(t.columns().index("glv"), order)
    assert t.cell_text(0, "glv") == first
    assert t.cell_text(t.row_count() - 1, "glv") == ""


# --------------------------------------------------------------------------- #
# 失敗的那幾顆
# --------------------------------------------------------------------------- #
def test_a_failed_defect_says_why(qapp):
    """引擎每一顆都留了原因（鐵則 7）—— 而那份東西以前只有 CSV 看得到。"""
    t = _table(qapp)
    assert t.cell_text(2, "error") == "subtract: shapes differ"


def test_a_failed_row_is_coloured(qapp):
    """一張幾百列的表上，只有一欄變色是找不到的。"""
    from PySide6.QtGui import QColor

    t = _table(qapp)
    m = t._model
    ok_colour = m.data(m.index(0, 0), Qt.ForegroundRole)
    bad_colour = m.data(m.index(2, 0), Qt.ForegroundRole)
    assert ok_colour is None, "正常的那幾列不該被上色"
    assert isinstance(bad_colour, QColor)


# --------------------------------------------------------------------------- #
# 這張表是唯讀的
# --------------------------------------------------------------------------- #
def test_the_table_is_read_only(qapp):
    """「看到判錯的那一顆就地改掉」很自然，但那會讓這一頁從**看結果**變成
    **編結果** —— 而那是兩件事，還沒定調。"""
    t = _table(qapp)
    assert t.editTriggers() == QAbstractItemView.NoEditTriggers
    idx = t._model.index(0, t.columns().index("bin"))
    assert not (t._model.flags(idx) & Qt.ItemIsEditable)


def test_double_clicking_a_row_asks_to_go_and_look_at_that_defect(qapp):
    t = _table(qapp)
    got = []
    t.defect_activated.connect(got.append)
    t._on_double_click(t._model.index(1, 0))
    assert got == ["2"]


def test_selecting_by_id_finds_the_row_wherever_it_moved(qapp):
    t = _table(qapp)
    t._model.sort(t.columns().index("glv"), Qt.AscendingOrder)
    assert t.select_defect("1") is True
    assert t.selected_ids() == ["1"]
    assert t.select_defect("nope") is False


def test_an_empty_batch_is_an_empty_table(qapp):
    t = ResultsTable()
    t.set_results([], {})
    assert t.row_count() == 0 and t.columns()
