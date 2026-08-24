# F22-UI：判定面板（多類別）＋ 每個 bin 的純度
"""這一份鎖住的是**多類別在 Studio 上真的能編輯**，以及它旁邊那些數字。

在這之前，`decide` 只能手寫 JSON。

測六件事：

1. 面板有兩種樣子（一個門檻／一串規則），而且**一次只有一種** ——
   引擎那邊兩者並存是 `ambiguous-decision` 的 error；
2. 切成多類別時**現有的門檻會被翻成第一條規則**（那是使用者調了半天的成果）；
3. 加／刪／換順序都走 model，而**換順序就是換優先權**；
4. **打字不重建** —— 重建會把游標從正在打的那一格搶走；
5. 每一條規則旁邊的顆數是 **bin 的顆數**，而且**還沒跑過就不顯示**；
6. `bin_purity`（report）算得對，而它是多類別唯一量得出來的東西。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.export.report import summarize  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def panel(qapp):
    from d4t.ui.decide_panel import DecidePanel
    from d4t.ui.viewmodel import RecipeModel
    m = RecipeModel()
    m.expr = "glv_max"
    m.threshold = 3.0
    p = DecidePanel()
    p.set_model(m)
    p.set_features(["glv_max\tGray level", "cd_deq\tCD"])
    return p


def _texts(p, cls):
    return [w.text() for w in p.findChildren(cls)]


# --------------------------------------------------------------------------- #
# 1 & 2. 兩種樣子，一次一種；切過去不丟工作成果
# --------------------------------------------------------------------------- #
def test_it_starts_on_the_two_bin_threshold(panel):
    from PySide6.QtWidgets import QDoubleSpinBox
    assert not panel.mode.isChecked()
    spin = panel.findChild(QDoubleSpinBox)
    assert spin is not None and spin.value() == pytest.approx(3.0)


def test_switching_turns_the_threshold_into_the_first_rule(panel):
    m = panel._model
    panel.mode.setChecked(True)
    assert m.decide is not None
    assert len(m.decide.rules) == 1
    assert "glv_max" in m.decide.rules[0].when and "3" in m.decide.rules[0].when
    assert m.decide.score == "glv_max"
    # **並存是 error**，所以切過去要把舊那一格清掉
    assert not str(m.expr).strip()


def test_switching_back_leaves_a_usable_expression(panel):
    m = panel._model
    panel.mode.setChecked(True)
    panel.mode.setChecked(False)
    assert m.decide is None
    assert str(m.expr).strip(), "切回去之後那一格不能是空的（空的解析不出來）"


def test_only_one_of_the_two_is_on_screen(panel):
    from PySide6.QtWidgets import QDoubleSpinBox
    panel.mode.setChecked(True)
    assert panel.findChild(QDoubleSpinBox) is None, "多類別那一種沒有門檻格"


# --------------------------------------------------------------------------- #
# 3. 加／刪／換順序
# --------------------------------------------------------------------------- #
def test_adding_a_rule_picks_a_bin_nobody_is_using(panel):
    m = panel._model
    panel.mode.setChecked(True)
    m.add_rule()
    bins = [r.bin for r in m.decide.rules] + [m.decide.otherwise_bin]
    assert len(bins) == len(set(bins)), bins


def test_moving_a_rule_changes_which_one_wins(panel):
    """**換順序就是換優先權** —— 所以它是一個第一級的動作，不是排版。"""
    m = panel._model
    panel.mode.setChecked(True)
    m.add_rule()
    m.set_rule(1, when="glv_max > 0", label="catch-all")
    first_before = m.decide.rules[0].label
    m.move_rule(1, -1)
    assert m.decide.rules[0].label == "catch-all" != first_before


def test_removing_a_rule_removes_exactly_one(panel):
    m = panel._model
    panel.mode.setChecked(True)
    m.add_rule(); m.add_rule()
    n = len(m.decide.rules)
    m.remove_rule(1)
    assert len(m.decide.rules) == n - 1


def test_the_lot_of_it_round_trips_through_a_recipe(panel):
    m = panel._model
    panel.mode.setChecked(True)
    m.add_let(); m.set_let(0, name="contrast", expr="glv_max * cd_deq")
    m.add_rule(); m.set_rule(1, when="contrast > 10", bin=5, label="big")
    r = m.to_recipe()
    assert r.decide == m.decide
    from d4t.core.pipeline import Recipe
    assert Recipe.from_json_dict(r.to_json_dict()).decide == m.decide


# --------------------------------------------------------------------------- #
# 4. 打字不重建
# --------------------------------------------------------------------------- #
def test_typing_does_not_rebuild_and_steal_the_cursor(panel, qapp):
    """重建會把游標從正在打的那一格搶走。

    這個 repo 記過同一個形狀 —— `set_dynamic_choices` 就是為了它才「只換內容、
    跳過有游標的那一格」。
    """
    from PySide6.QtWidgets import QLineEdit
    panel.mode.setChecked(True)
    panel.show()
    qapp.processEvents()
    edits = panel.findChildren(QLineEdit)
    assert edits
    edits[0].setFocus()
    qapp.processEvents()
    if not edits[0].hasFocus():
        pytest.skip("這個平台沒有給焦點（offscreen 有時如此）")
    assert panel._typing() is True
    before = edits[0]
    panel.set_counts({0: 3, 1: 4})        # 外面餵進來的重建請求
    assert panel.findChildren(QLineEdit)[0] is before, "打字時被重建了"
    assert panel._stale is True, "跳過的重建要記著，等焦點離開再補"


def test_a_structural_change_does_rebuild(panel):
    from PySide6.QtWidgets import QLineEdit
    panel.mode.setChecked(True)
    before = panel.findChildren(QLineEdit)
    panel._restructure(panel._model.add_rule)
    assert len(panel.findChildren(QLineEdit)) > len(before)


# --------------------------------------------------------------------------- #
# 5. 顆數
# --------------------------------------------------------------------------- #
def test_before_a_run_there_are_no_counts(panel):
    panel.mode.setChecked(True)
    assert panel._count_label(0) is None, "沒跑過就不要顯示 0 —— 那會被讀成「一顆都沒有」"


def test_the_count_says_which_quantity_it_is(panel):
    """它是 **bin 的顆數**，不是「這條規則抓到幾顆」—— 兩條規則可以共用一個 bin。"""
    panel.mode.setChecked(True)
    panel.set_counts({3: 11}, purity=[{"bin": 3, "purity": 1.0}])
    lab = panel._count_label(3)
    assert lab is not None
    assert "bin 3" in lab.text() and "11" in lab.text()
    assert "100%" in lab.text()
    assert "bin" in lab.toolTip()


# --------------------------------------------------------------------------- #
# 6. 純度（report）
# --------------------------------------------------------------------------- #
def _rows(pairs):
    return [{"defect_id": str(i), "ok": True, "bin": b, "score": 0.0,
             "features": {}} for i, (b, _real) in enumerate(pairs)]


def test_purity_counts_real_and_nuisance_per_bin():
    pairs = [(3, True), (3, True), (2, True), (2, False), (0, False)]
    gt = {str(i): {"is_real": real} for i, (_b, real) in enumerate(pairs)}
    got = {r["bin"]: r for r in summarize(_rows(pairs), ground_truth=gt)["bin_purity"]}
    assert got[3]["n"] == 2 and got[3]["purity"] == pytest.approx(1.0)
    assert got[2]["n"] == 2 and got[2]["purity"] == pytest.approx(0.5)
    assert got[0]["n_real"] == 0 and got[0]["n_nuisance"] == 1


def test_an_unlabelled_bin_has_no_purity_rather_than_zero():
    """沒有分母不等於零純度 —— 跟 CLI 的 `_pct` 是同一條規矩。"""
    rows = _rows([(7, True)])
    got = summarize(rows, ground_truth={"nope": {"is_real": True}})["bin_purity"]
    row = next(r for r in got if r["bin"] == 7)
    assert row["purity"] is None and row["n_unlabelled"] == 1


def test_bins_come_back_biggest_first():
    pairs = [(0, False), (5, True), (2, True)]
    gt = {str(i): {"is_real": r} for i, (_b, r) in enumerate(pairs)}
    order = [r["bin"] for r in summarize(_rows(pairs), ground_truth=gt)["bin_purity"]]
    assert order == [5, 2, 0], order


def test_no_ground_truth_means_no_purity_block():
    assert "bin_purity" not in summarize(_rows([(1, True)]))
