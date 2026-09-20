# X2：在畫面上標真缺陷／誤報 — authored 2026-09-08.
"""``ground_truth.json`` 以前只能用手打 —— 而目標使用者不會寫 code。

驗收條件是「**從零開始標 20 顆，關窗重開後準確率那一行有數字，而且那個檔
CLI 的 ``run --ground-truth`` 直接吃得下**」。所以這一支盯的是三件事：

1. 寫出去的**格式**跟自動撿的那一份逐字相同（不然這裡等於發明了第二種答案卷）；
2. 「我不確定」不是 nuisance —— 拿掉標記與標成誤報在正確率上是兩件事；
3. 標完之後**畫面上真的有變化**（那一欄寫著 real / nuisance，正確率跟著動）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication              # noqa: E402

from d4t.core.export import summarize                   # noqa: E402
from d4t.ui import theme as theme_mod                   # noqa: E402
from d4t.ui import truth_marks                          # noqa: E402
from d4t.ui.results import ResultsWindow                # noqa: E402
from d4t.ui.results_table import TRUTH_COLUMN           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


def _rows(n: int = 4):
    return [{"defect_id": str(i), "ok": True, "score": float(i),
             "bin": i % 2, "features": {"glv_median": float(i)}}
            for i in range(n)]


# --------------------------------------------------------------------------- #
# 檔案那一半（純函式，不用開視窗）
# --------------------------------------------------------------------------- #
def test_what_it_writes_is_what_the_auto_pickup_reads(tmp_path):
    """**同一種答案卷**，不是第二種。"""
    path = str(tmp_path / truth_marks.FILENAME)
    truth_marks.write(path, truth_marks.merge(None, {"1": True, "2": False}))
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"1": {"is_real": True}, "2": {"is_real": False}}

    # 而 CLI／報表那條路讀得懂它（同一支 `summarize`）。
    g = summarize([{"defect_id": "1", "ok": True, "bin": 1},
                   {"defect_id": "2", "ok": True, "bin": 0}],
                  ground_truth=data)["ground_truth"]
    assert g["n_evaluated"] == 2 and g["accuracy"] == 1.0


def test_marking_keeps_fields_it_does_not_understand(tmp_path):
    """別的工具寫的欄位原封留著 —— 這一份沒有資格決定它們不重要。"""
    before = {"7": {"is_real": False, "type": "particle", "by": "somebody"}}
    after = truth_marks.merge(before, {"7": True})
    assert after["7"] == {"is_real": True, "type": "particle",
                          "by": "somebody"}


def test_not_sure_removes_the_label_rather_than_saying_nuisance():
    """「我還沒看」與「我看過，是誤報」在正確率上是兩件完全不同的事。"""
    data = truth_marks.merge(None, {"3": True})
    assert truth_marks.merge(data, {"3": None}) == {}


def test_the_write_is_atomic_and_leaves_no_tmp_behind(tmp_path):
    path = str(tmp_path / truth_marks.FILENAME)
    truth_marks.write(path, {"1": {"is_real": True}})
    assert os.path.isfile(path)
    assert not os.path.exists(path + ".tmp"), "鐵則 5：.tmp 要被 replace 掉"


def test_emptying_the_labels_writes_an_empty_file_not_a_stale_one(tmp_path):
    """最後一個標記拿掉之後，舊答案不可以在下次開窗時復活。"""
    path = str(tmp_path / truth_marks.FILENAME)
    truth_marks.write(path, truth_marks.merge(None, {"1": True}))
    truth_marks.write(path, truth_marks.merge({"1": {"is_real": True}},
                                              {"1": None}))
    assert truth_marks.read(path) == {}


def test_counts_ignore_entries_it_cannot_read():
    data = {"1": {"is_real": True}, "2": {"is_real": False},
            "3": {"note": "no answer here"}}
    assert truth_marks.counts(data) == {"labelled": 2, "real": 1,
                                        "nuisance": 1}


def test_where_the_file_goes_for_a_lot_without_a_klarf(tmp_path):
    """沒有 KLARF 的兩種輸入退到**第一張影像的資料夾**（使用者眼中的那批資料）。"""
    class _Ref:
        path = str(tmp_path / "imgs" / "a.png")

    class _Item:
        images = {"single": _Ref()}

    class _DS:
        klarf = None
        items = [_Item()]

    assert truth_marks.path_for(_DS()) == str(
        tmp_path / "imgs" / truth_marks.FILENAME)


# --------------------------------------------------------------------------- #
# 畫面那一半
# --------------------------------------------------------------------------- #
def test_the_column_only_exists_when_the_host_says_there_is_an_answer_sheet(qapp):
    """不餵 ``truth`` ＝ 以前的行為逐字不變（別的宿主與舊測試踩著它）。"""
    win = ResultsWindow()
    win.set_table(_rows())
    assert TRUTH_COLUMN not in win.table.columns()
    win.set_table(_rows(), truth={})
    assert TRUTH_COLUMN in win.table.columns()
    win.close()


def test_pressing_r_and_n_says_which_defects_and_what(qapp):
    """R / N / U → 一份 ``{defect_id: True|False|None}``，**表自己不寫檔**。"""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    win = ResultsWindow()
    win.set_table(_rows(), truth={})
    seen = []
    win.truth_marked.connect(lambda m: seen.append(dict(m)))

    table = win.table.table
    table.select_defect("2")
    for key in (Qt.Key_R, Qt.Key_N, Qt.Key_U):
        table.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, key,
                                      Qt.NoModifier, ""))
    assert seen == [{"2": True}, {"2": False}, {"2": None}]
    win.close()


def test_a_marked_row_says_so_on_screen(qapp):
    """標完之後畫面上要**看得出來**是哪幾顆 —— 不然標到第 20 顆會重複標。"""
    win = ResultsWindow()
    win.set_table(_rows(), truth={"1": {"is_real": True},
                                  "3": {"is_real": False}})
    texts = [win.table.cell_text(r, TRUTH_COLUMN)
             for r in range(win.table.row_count())]
    # ⚠ 第 4 列是 bin 1（判定說「真缺陷」）而答案是 nuisance —— **那一格
    # 現在自己說出對不上**（F117 E1）。以前它只寫 `nuisance`，而「判定跟
    # 答案對不上」要使用者自己逐列比才看得出來。
    assert texts == ["", "real", "", "nuisance · called real"], texts
    # ⚠ **而且那一欄要真的看得到**：它在收合層裡（`visible_columns`）——
    # 落在「All measurements」摺疊區的話，使用者標完什麼都不會發生。
    assert TRUTH_COLUMN in win.table.visible_column_names()
    win.close()


def test_marking_nothing_selected_does_nothing(qapp):
    win = ResultsWindow()
    win.set_table(_rows(), truth={})
    seen = []
    win.truth_marked.connect(lambda m: seen.append(m))
    win.table.table.clearSelection()
    assert win.table.mark_selected(True) is False
    assert seen == []
    win.close()


# --------------------------------------------------------------------------- #
# 從頭到尾（驗收條件本身）
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("mark")), n=6, seed=11)


def test_marking_in_studio_writes_the_file_beside_the_klarf(qapp, lot,
                                                            tmp_path):
    """驗收條件：標完之後那個檔在 KLARF 旁邊，而正確率那一行有數字。

    這一批本來就有一份 ``ground_truth.json``（`make_sample` 寫的），所以先把
    它搬走 —— 要驗的是**從零開始標**。
    """
    import shutil
    from d4t.ui import studio as studio_mod

    folder = os.path.dirname(lot["klarf"])
    gt_path = os.path.join(folder, truth_marks.FILENAME)
    shutil.move(gt_path, str(tmp_path / "kept.json"))

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.load_dataset_path(lot["klarf"], sync=True) is True
        assert win.ground_truth is None, "搬走了還撿得到？"

        ids = [str(it.defect_id) for it in win.dataset.items[:3]]
        win._on_truth_marked({ids[0]: True, ids[1]: False, ids[2]: True})

        assert os.path.isfile(gt_path), "答案卷沒有寫到 KLARF 旁邊"
        on_disk = truth_marks.read(gt_path)
        assert truth_marks.counts(on_disk) == {"labelled": 3, "real": 2,
                                               "nuisance": 1}
        # 而下一次開窗自動撿得到它 —— 那條路一個字都沒有改。
        assert win._load_ground_truth_beside(lot["klarf"]) == gt_path
        assert truth_marks.counts(win.ground_truth)["labelled"] == 3
    finally:
        win.close()
