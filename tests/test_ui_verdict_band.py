# 判定段：跑完之後第一個問題「每一類各幾顆」（R3，2026-08-24）。
"""使用者：「目前的 results panel 太簡略了」。

這一份鎖住的是**數字從哪裡來**與**什麼時候不畫**：

* 一列是**一片葉子**，不是一個 bin —— 兩片葉子共用同一個 bin 是合法的，
  而使用者取的兩個名字都要看得到；
* 順序跟畫布上的樹一樣，而且**重跑不會跳**；
* 「算不出來」的那幾顆是**兩種**不同的事故，各自一列，而且沒有的時候不出現；
* 沒有 ground truth 就**整欄不畫**，不是畫一排「—」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, TreeLeaf, TreeStep,
)
from d4t.ui import theme as theme_mod  # noqa: E402
from d4t.ui.verdict_band import (  # noqa: E402
    FAILED_KEY, UNBINNED_KEY, VerdictBand, verdict_rows,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _tree():
    """兩問三葉。**`bright` 與 `dim` 刻意共用 bin 2** —— 見上面那一條。"""
    return DecideSpec(let=[], rules=[], otherwise_bin=0, otherwise_label="",
                      score="", tree=TreeStep(
        when="glv > 50",
        yes=TreeLeaf(bin=2, label="bright"),
        no=TreeStep(when="mad > 3",
                    yes=TreeLeaf(bin=2, label="dim"),
                    no=TreeLeaf(bin=0, label="nuisance"))))


def _r(i, glv, mad, ok=True, bin_=0):
    return {"defect_id": str(i), "ok": ok, "bin": None if bin_ is None else bin_,
            "score": 0.0, "features": {"glv": float(glv), "mad": float(mad)}}


def _batch():
    return ([_r(i, 90, 0, bin_=2) for i in range(5)]            # bright
            + [_r(10 + i, 10, 9, bin_=2) for i in range(3)]     # dim
            + [_r(20 + i, 10, 0, bin_=0) for i in range(7)])    # nuisance


# --------------------------------------------------------------------------- #
# 資料
# --------------------------------------------------------------------------- #
def test_two_leaves_sharing_a_bin_are_two_rows():
    """**一列是一片葉子，不是一個 bin。**

    `bright` 與 `dim` 寫回 KLARF 的都是 bin 2，但它們是使用者分開命名的兩類
    —— 照 bin 合併會把其中一個名字弄不見，而那正是使用者自己打的字。
    """
    rows = verdict_rows(_tree(), _batch())
    names = [r["name"] for r in rows]
    assert names == ["bright", "dim", "nuisance"], names
    assert [r["count"] for r in rows] == [5, 3, 7]
    assert [r["bin"] for r in rows] == [2, 2, 0]


def test_the_order_follows_the_canvas_and_does_not_move_between_runs():
    """順序照樹走，不照顆數 —— 照顆數排的話重跑一次列會跳，讀起來像結構變了。"""
    first = [r["key"] for r in verdict_rows(_tree(), _batch())]
    lopsided = _batch() + [_r(30 + i, 10, 0, bin_=0) for i in range(40)]
    second = [r["key"] for r in verdict_rows(_tree(), lopsided)]
    assert first == second == ["y", "ny", "nn"]


def test_the_counts_add_up_to_the_batch():
    """守恆：每一列加起來 = 這一批（含算不出來的那幾顆）。"""
    batch = _batch() + [_r(90, 0, 0, ok=False), _r(91, 0, 0, bin_=None)]
    rows = verdict_rows(_tree(), batch)
    assert sum(r["count"] for r in rows) == len(batch)


def test_the_two_kinds_of_could_not_classify_are_two_rows():
    """卡片出錯 vs 判定給不出 bin 是**兩種不同的事故**，講在一起就查不下去。"""
    batch = _batch() + [_r(90, 0, 0, ok=False), _r(91, 0, 0, bin_=None)]
    rows = {r["key"]: r for r in verdict_rows(_tree(), batch)}
    assert rows[FAILED_KEY]["count"] == 1
    assert rows[UNBINNED_KEY]["count"] == 1
    assert rows[FAILED_KEY]["ids"] == ["90"]
    assert rows[UNBINNED_KEY]["ids"] == ["91"]


def test_nothing_went_wrong_means_no_row_for_it():
    """F18：不顯示 0。一列「a card errored 0」比沒有那一列更糟。"""
    keys = [r["key"] for r in verdict_rows(_tree(), _batch())]
    assert FAILED_KEY not in keys and UNBINNED_KEY not in keys


def test_an_empty_class_still_gets_a_row():
    """**沒有東西掉進去的那一類要留著。**

    那是 recipe 的結構（使用者畫的樹上有這一格），不是這一批的統計 ——
    而「這一類這批一顆都沒有」正是他要知道的事之一。
    """
    only_bright = [_r(i, 90, 0, bin_=2) for i in range(4)]
    rows = verdict_rows(_tree(), only_bright)
    assert [r["count"] for r in rows] == [4, 0, 0]


def test_purity_needs_ground_truth():
    truth = {"0": {"is_real": True}, "1": {"is_real": True},
             "2": {"is_real": False}, "20": {"is_real": False}}
    rows = {r["key"]: r for r in verdict_rows(_tree(), _batch(), truth)}
    assert (rows["y"]["labelled"], rows["y"]["real"]) == (3, 2)
    assert (rows["nn"]["labelled"], rows["nn"]["real"]) == (1, 0)
    plain = verdict_rows(_tree(), _batch())
    assert all(r["labelled"] == 0 for r in plain)


def test_a_recipe_without_a_tree_falls_back_to_bins():
    """二元 score 的老路仍然要答得出「每一類幾顆」。"""
    rows = verdict_rows(None, _batch())
    assert [(r["name"], r["count"]) for r in rows] == [("bin 0", 7), ("bin 2", 8)]


# --------------------------------------------------------------------------- #
# 畫出來
# --------------------------------------------------------------------------- #
def _texts(w):
    return [x.text() for x in w.findChildren(QLabel) if x.text()]


def test_the_band_hides_itself_before_a_run(qapp):
    band = VerdictBand()
    band.set_rows([])
    assert band.isHidden(), "沒跑過卻留了一塊空白的標題"
    band.set_rows(verdict_rows(_tree(), _batch()))
    assert not band.isHidden()


def test_the_class_name_is_the_main_thing_and_the_bin_is_its_number(qapp):
    band = VerdictBand()
    band.set_rows(verdict_rows(_tree(), _batch()))
    texts = _texts(band)
    for name in ("bright", "dim", "nuisance"):
        assert name in texts, texts
    assert "bin 2" in texts and "bin 0" in texts, texts


def test_the_purity_column_is_absent_without_ground_truth(qapp):
    """沒有 ground truth 就整欄不畫 —— 一排「—」會佔掉版面，而且每次都在
    提醒使用者少了一個他可能根本沒有的東西。"""
    band = VerdictBand()
    band.set_rows(verdict_rows(_tree(), _batch()))
    assert not [t for t in _texts(band) if "real" in t], _texts(band)

    truth = {str(i): {"is_real": i < 5} for i in range(30)}
    band.set_rows(verdict_rows(_tree(), _batch(), truth))
    assert [t for t in _texts(band) if "real" in t], _texts(band)


def test_the_bar_width_is_the_count(qapp):
    from d4t.ui.verdict_band import _Bar

    band = VerdictBand()
    band.set_rows(verdict_rows(_tree(), _batch()))
    fracs = [b.fraction() for b in band.findChildren(_Bar)]
    assert fracs == [5 / 15, 3 / 15, 7 / 15], fracs


def test_clicking_a_class_reports_it_and_clicking_again_clears(qapp):
    band = VerdictBand()
    band.set_rows(verdict_rows(_tree(), _batch()))
    got = []
    band.class_selected.connect(got.append)
    band._on_row_clicked("ny")
    assert band.selected() == "ny" and got == ["ny"]
    band._on_row_clicked("ny")
    assert band.selected() == "" and got == ["ny", ""]


def test_a_selection_that_stops_existing_is_dropped(qapp):
    """樹改了之後那一類可能不在了 —— 留著一個指不到東西的篩選會讓 Gallery
    永遠是空的，而使用者看不到任何原因。"""
    band = VerdictBand()
    band.set_rows(verdict_rows(_tree(), _batch()))
    band.select("ny")
    assert band.selected() == "ny"
    band.set_rows(verdict_rows(None, _batch()))
    assert band.selected() == ""
