# F48 驗收：就地改 bin —— **只在畫面上**（2026-08-28）。
"""F27 §5 把「表格能不能就地改 bin」列為待定調，理由寫得很清楚：那會讓
Results 這一頁從「看結果」變成「編結果」，而那是兩件事。

使用者 2026-08-28 定調的是一個**折中**：「只在畫面上，標成手動改過」。
所以這一支測試守的不是「改得動」（那很容易），而是**改了之後那個值哪裡都
去不了**：

* 匯出（CSV／Excel／KLARF／SQLite）拿到的仍然是引擎判的那個 bin；
* 原本那份 result dict 一個鍵都沒有多；
* 再跑一批，記號就沒了（那些記號講的是上一批的數字）。

⚠ **最後一條是刻意的行為，不是漏掉的持久化。** 寫在這裡是為了讓下一個看到
「改完再跑就不見了」的人知道那是決定，不是 bug。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.export.report import write_csv          # noqa: E402


def _import_qt(g):
    from PySide6.QtWidgets import QApplication
    from d4t.ui import results_table as rt_mod
    from d4t.ui import theme as theme_mod
    g.update(QApplication=QApplication, rt_mod=rt_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


def _results():
    """三顆：兩顆判得出 bin，一顆整個失敗（沒有 bin）。"""
    return [
        {"defect_id": "1", "ok": True, "error": None, "score": 0.9, "bin": 5,
         "features": {"glv_median": 12.0}},
        {"defect_id": "2", "ok": True, "error": None, "score": 0.1, "bin": 0,
         "features": {"glv_median": 3.0}},
        {"defect_id": "3", "ok": False, "error": "boom", "score": None,
         "bin": None, "features": {}},
    ]


@pytest.fixture()
def table(qapp):
    t = rt_mod.ResultsTable()
    t.set_results(_results())
    yield t
    t.deleteLater()


def _row_of(table, did):
    return table._model.row_of(did)


# --------------------------------------------------------------------------- #
# 1. 改得動，而且畫面上讀得出「從幾改成幾」
# --------------------------------------------------------------------------- #
def test_the_cell_says_both_numbers(table):
    """`3 (was 5)` —— 兩個數字都在格子裡。

    只寫新值配一個記號的話，「引擎判 5、我說是 3」這句話要停滑鼠才讀得到，
    而那正是這一欄現在在講的整件事。
    """
    assert table.set_bin_override(_row_of(table, "1"), 3) is True
    assert table.cell_text(_row_of(table, "1"), "bin") == "3 (was 5)"
    # 沒改過的那一顆一個字都沒變
    assert table.cell_text(_row_of(table, "2"), "bin") == "0"


def test_a_defect_the_engine_could_not_bin_says_manual(table):
    """引擎沒判出來的那一顆不能寫一個假的 ``was``。"""
    assert table.set_bin_override(_row_of(table, "3"), 7) is True
    assert table.cell_text(_row_of(table, "3"), "bin") == "7 (manual)"


def test_typing_the_original_value_back_removes_the_mark(table):
    """改回引擎判的那個值＝反悔，不是再蓋一層。

    使用者要取消的時候唯一想得到的動作就是把原本那個數字打回去 ——
    那時候留著一個「手動改成 5（原本 5）」的記號只是雜訊。
    """
    row = _row_of(table, "1")
    table.set_bin_override(row, 3)
    assert table.bin_overrides() == {"1": 3}
    table.set_bin_override(row, 5)              # 5 就是引擎判的
    assert table.bin_overrides() == {}
    assert table.cell_text(row, "bin") == "5"


def test_sorting_follows_the_hand_written_value(table):
    """畫面上寫 3，就要排在 3 那一群 —— 兩件事只有一個出處（`_cell`）。"""
    table.set_bin_override(_row_of(table, "1"), 0)   # 5 → 0
    table.sortByColumn(table.columns().index("bin"), rt_mod.Qt.AscendingOrder)
    assert table._model.defect_id_at(0) in ("1", "2")
    assert table._model.defect_id_at(1) in ("1", "2")


# --------------------------------------------------------------------------- #
# 2. 那個值哪裡都去不了（這一組才是這支測試存在的理由）
# --------------------------------------------------------------------------- #
def test_the_export_never_sees_it(table, tmp_path):
    """**匯出的位元組要逐位元組相同。**

    這一條用的是「先寫一份、改完再寫一份、比 bytes」而不是「檢查有沒有那個
    鍵」—— 後者會漏掉任何一條「UI 順手把值寫回 result」的路。
    """
    rows = _results()
    before = tmp_path / "before.csv"
    write_csv(rows, str(before))
    baseline = before.read_bytes()

    t = table
    t.set_results(rows)                     # 同一批 dict 進表
    t.set_bin_override(_row_of(t, "1"), 3)
    t.set_bin_override(_row_of(t, "2"), 9)

    after = tmp_path / "after.csv"
    write_csv(rows, str(after))
    assert after.read_bytes() == baseline, "手動改的 bin 流進 CSV 了"


def test_the_original_result_dicts_are_untouched(table):
    """model 拿的是 `dict(r)` 淺拷貝，所以外面那份**逐鍵不變**。

    ⚠ 比的是整份 dict，不是只問 ``OVERRIDE_KEY`` 在不在：拷貝哪天沒了的話，
    真正會發生的事是有人把 ``bin`` 直接蓋掉 —— 而只問新鍵的那條測試看不見它。
    """
    import copy
    rows = _results()
    pristine = copy.deepcopy(rows)
    table.set_results(rows)
    table.set_bin_override(_row_of(table, "1"), 3)
    table.set_bin_override(_row_of(table, "3"), 7)
    assert rows == pristine, rows


def test_a_new_run_clears_the_marks(table):
    """再跑一批 → 記號沒了（刻意的：那些記號講的是上一批的數字）。"""
    table.set_bin_override(_row_of(table, "1"), 3)
    assert table.bin_overrides()
    table.set_results(_results())
    assert table.bin_overrides() == {}


def test_clearing_them_by_hand_reports_how_many(table):
    table.set_bin_override(_row_of(table, "1"), 3)
    table.set_bin_override(_row_of(table, "2"), 4)
    seen = []
    table.bin_overrides_changed.connect(seen.append)
    assert table.clear_bin_overrides() == 2
    assert seen == [0]


# --------------------------------------------------------------------------- #
# 3. 不准踩到既有的手勢
# --------------------------------------------------------------------------- #
def test_the_existing_mouse_gestures_still_mean_what_they_meant(table):
    """單擊判定欄 = 問「為什麼」、雙擊 = 去看那一顆。

    Qt 的 edit trigger 是**整張表**的設定，所以 `DoubleClicked` 或
    `SelectedClicked` 一加上去，同一個手勢就會同時開回溯面板跟一個編輯框。
    這一條把「只能用 EditKeyPressed」釘住。
    """
    from PySide6.QtWidgets import QAbstractItemView
    assert table.editTriggers() == QAbstractItemView.EditKeyPressed

    asked, opened = [], []
    table.trace_requested.connect(asked.append)
    table.defect_activated.connect(opened.append)
    idx = table._model.index(_row_of(table, "1"),
                             table.columns().index("bin"))
    table._on_click(idx)
    table._on_double_click(idx)
    assert asked == ["1"] and opened == ["1"]


def test_only_the_bin_column_is_editable(table):
    """別的欄一格都不准改 —— 這一頁仍然是「看結果」。"""
    from PySide6.QtCore import Qt
    for i, name in enumerate(table.columns()):
        flags = table._model.flags(table._model.index(0, i))
        editable = bool(flags & Qt.ItemIsEditable)
        assert editable == (name == "bin"), name
