# F24 ③：判定樹的編輯互動。
"""鎖住編輯層的六條性質：

1. `ensure_tree`：rules → 等價鏈狀樹（無損），而且 **rules 清空**（兩個都在
   是 `ambiguous-decision`）。
2. 樹的 setter 用路徑指節點；改 when／改葉子／加一步／插一步／拿掉一步。
3. 「加一步」原本那一類**留著**（掛在新步驟的 no 邊），新葉子拿一個沒用過
   的 bin（同 `add_rule` 的規則）。
4. 「拿掉一步」＝它的 no 邊接回上游（F24 §6）。
5. undo 一步回得來（樹進了 `_decide_snapshot`，F24 ① 就鎖了 —— 這裡鎖的是
   編輯動作真的各記一步）。
6. 面板：菱形＝Question + Yes/No 兩列；沒跑過 batch 那一行一個字都不畫。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Let, Rule, TreeLeaf, TreeStep, rules_to_tree,
)
from d4t.ui.viewmodel import RecipeModel  # noqa: E402


def _model_with_rules() -> RecipeModel:
    m = RecipeModel()
    m.decide = DecideSpec(
        let=[Let(name="contrast", expr="a * 2")],
        rules=[Rule(when="contrast > 100", bin=3, label="big"),
               Rule(when="contrast > 30", bin=2, label="mid")],
        otherwise_bin=0, otherwise_label="nuisance", score="contrast")
    m.clear_history()
    return m


def _model_with_tree() -> RecipeModel:
    m = _model_with_rules()
    m.ensure_tree()
    m.clear_history()
    return m


# --------------------------------------------------------------------------- #
# model（headless，不用 Qt）
# --------------------------------------------------------------------------- #
def test_ensure_tree_converts_and_clears_the_rules():
    m = _model_with_rules()
    want = rules_to_tree(m.decide)
    m.ensure_tree()
    assert m.decide.tree == want
    assert m.decide.rules == []              # 兩個都在是 ambiguous-decision
    before = m.decide.tree
    m.ensure_tree()                          # 第二次是 no-op
    assert m.decide.tree is before


def test_tree_node_walks_by_path():
    m = _model_with_tree()
    assert isinstance(m.tree_node(""), TreeStep)
    assert m.tree_node("y") == TreeLeaf(bin=3, label="big")
    assert m.tree_node("ny") == TreeLeaf(bin=2, label="mid")
    assert m.tree_node("nn") == TreeLeaf(bin=0, label="nuisance")
    assert m.tree_node("yy") is None         # 葉子下面沒有東西


def test_set_tree_when_touches_only_that_step():
    m = _model_with_tree()
    m.set_tree_when("n", "contrast > 55")
    assert m.tree_node("n").when == "contrast > 55"
    assert m.tree_node("").when == "contrast > 100"


def test_set_tree_leaf_edits_bin_and_label():
    m = _model_with_tree()
    m.set_tree_leaf("y", bin=7, label="huge")
    assert m.tree_node("y") == TreeLeaf(bin=7, label="huge")


def test_split_keeps_the_old_class_on_the_no_side():
    m = _model_with_tree()
    old = m.tree_node("y")
    m.split_tree_leaf("y")
    step = m.tree_node("y")
    assert isinstance(step, TreeStep) and step.when == ""
    assert step.no == old                    # 原本那一類留著
    fresh = step.yes
    assert isinstance(fresh, TreeLeaf)
    assert fresh.bin not in {0, 2, 3}        # 沒用過的 bin


def test_insert_above_hangs_the_subtree_on_the_no_side():
    m = _model_with_tree()
    old_root = m.tree_node("")
    m.insert_tree_step_above("")
    root = m.tree_node("")
    assert isinstance(root, TreeStep) and root.when == ""
    assert root.no == old_root
    assert isinstance(root.yes, TreeLeaf)


def test_remove_step_reconnects_the_no_side():
    m = _model_with_tree()
    no_side = m.tree_node("n")
    m.remove_tree_step("")
    assert m.tree_node("") == no_side


def test_every_edit_is_one_undo_step():
    m = _model_with_tree()
    base = m.decide.tree
    m.set_tree_when("", "contrast > 99")
    m.split_tree_leaf("y")
    assert m.tree_node("") .when == "contrast > 99"
    m.undo()
    assert isinstance(m.tree_node("y"), TreeLeaf)     # split 回去了
    assert m.tree_node("").when == "contrast > 99"    # when 還在
    m.undo()
    assert m.decide.tree == base


def test_feature_owners_maps_lets_to_the_entry_card():
    m = _model_with_tree()
    owners = m.feature_owners()
    assert owners.get("contrast") == ""      # let 中間值 → 入口卡


def test_algo_cards_are_shelved_not_deleted():
    """F24 ④：`feature_math` / `feature_fill` 收進 `HIDDEN_STEPS` ——
    卡片庫看不到、registry 照拿得到（舊 recipe 照跑）。"""
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline import get_step
    from d4t.ui.scope import HIDDEN_STEPS, visible_steps

    assert "feature_math" in HIDDEN_STEPS and "feature_fill" in HIDDEN_STEPS
    shown = {d["key"] for d in visible_steps(
        [{"key": k} for k in ("feature_math", "feature_fill", "glv_stats")])}
    assert shown == {"glv_stats"}
    assert get_step("feature_math") is not None
    assert get_step("feature_fill") is not None


# --------------------------------------------------------------------------- #
# 面板（要 Qt）
# --------------------------------------------------------------------------- #
def _import_qt(g):
    from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox

    from d4t.ui import theme as theme_mod
    from d4t.ui.tree_panel import TreePanel
    g.update(QApplication=QApplication, QLineEdit=QLineEdit,
             QSpinBox=QSpinBox, theme_mod=theme_mod, TreePanel=TreePanel)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


def _texts(panel):
    from PySide6.QtWidgets import QLabel
    return [w.text() for w in panel.findChildren(QLabel)]


def test_the_panel_shows_question_and_both_sides(qapp):
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")
    edits = panel.findChildren(QLineEdit)
    assert any(e.text() == "contrast > 100" for e in edits)
    texts = _texts(panel)
    assert any("Yes" in t for t in texts) and any("No" in t for t in texts)
    # yes 邊是葉子 → 名字可編；no 邊是另一步 → 一句摘要
    assert any(e.text() == "big" for e in edits)
    assert any("contrast > 30" in t for t in texts)


def test_no_batch_line_before_a_run(qapp):
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.set_counts(None)
    panel.show_path("")
    assert not any("arrive here" in t for t in _texts(panel))


def test_the_batch_line_reads_the_flow_counts(qapp):
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.set_counts({"": 47, "y": 11, "n": 36})
    panel.show_path("")
    assert any("47 arrive here" in t and "11 yes" in t and "36 no" in t
               for t in _texts(panel))


def test_editing_the_question_writes_the_model(qapp):
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")
    edit = next(e for e in panel.findChildren(QLineEdit)
                if e.text() == "contrast > 100")
    edit.textEdited.emit("contrast > 88")
    assert m.tree_node("").when == "contrast > 88"


def test_a_leaf_panel_edits_the_class(qapp):
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("y")
    edit = next(e for e in panel.findChildren(QLineEdit)
                if e.text() == "big")
    edit.textEdited.emit("huge")
    assert m.tree_node("y").label == "huge"
    spin = panel.findChildren(QSpinBox)[0]
    spin.valueChanged.emit(7)
    assert m.tree_node("y").bin == 7
