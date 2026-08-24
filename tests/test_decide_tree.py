# F24 ①：判定樹（decide.tree）
"""這一份鎖住的是**多步驟判定（decision tree）**，以及它跟 F22 平面規則的關係。

使用者定調（F24）：「ADC 也在畫布上呈現」「希望它是多步驟判定
（decision tree like）」。引擎這一半先做；畫布是第 ② 期。

測六件事：

1. 樹走得對（每一條 yes/no 組合都走到該到的葉子）；
2. **每一顆記下走過的路徑**，而且路徑跟 bin 一致（走 path 重算一次必同）；
3. **平面規則清單就是一條鏈狀樹**：`rules_to_tree` 轉出來的樹，在值網格上
   跟 rules 逐點同 bin 同 label —— 這是「F24 不是換掉 F22，是一般化」的證明；
4. round-trip 是 identity（鐵則 9），而且**只寫在用的那一種**（樹模式不寫
   rules/otherwise —— 兩個都寫出去，讀回來就是 ambiguous-decision，
   一份自己存的檔案不該把自己弄壞）；
5. 寫壞的樹**在讀檔當場擋**（不是安靜退回老路）；
6. `rules` 與 `tree` 並存是 `ambiguous-decision` 的 error；太深是 warning。
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import validate  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.engine import _eval_score  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Recipe, RecipeError, RecipeNode, Rule, ScoreSpec,
    TreeLeaf, TreeStep, rules_to_tree,
)


def _recipe(decide):
    return Recipe(
        recipe_id="t",
        routes={"ebi_patch": ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", {})},
        score=ScoreSpec(expr="", threshold=0.0, bins={"below": 0, "above": 1}),
        decide=decide,
    )


def _ctx(**feats):
    c = Context(images={})
    c.add_features(feats)
    return c


#: F24 mockup 的那棵樹（跟實跑 48 顆的 recipe 同形）。
TREE = TreeStep(
    when="missing > 0",
    yes=TreeLeaf(bin=9, label="not measurable"),
    no=TreeStep(
        when="contrast > 120",
        yes=TreeLeaf(bin=3, label="big particle"),
        no=TreeStep(
            when="contrast > 30",
            yes=TreeLeaf(bin=2, label="particle"),
            no=TreeStep(
                when="brightness > 6",
                yes=TreeLeaf(bin=1, label="faint"),
                no=TreeLeaf(bin=0, label="nuisance"),
            ),
        ),
    ),
)
DECIDE_TREE = DecideSpec(tree=TREE, score="contrast")


# --------------------------------------------------------------------------- #
# 1. 樹走得對
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("feats,want_bin,want_label,want_path", [
    ({"missing": 1.0, "contrast": 0.0, "brightness": 0.0}, 9,
     "not measurable", ["yes"]),
    ({"missing": 0.0, "contrast": 150.0, "brightness": 0.0}, 3,
     "big particle", ["no", "yes"]),
    ({"missing": 0.0, "contrast": 60.0, "brightness": 0.0}, 2,
     "particle", ["no", "no", "yes"]),
    ({"missing": 0.0, "contrast": 10.0, "brightness": 8.0}, 1,
     "faint", ["no", "no", "no", "yes"]),
    ({"missing": 0.0, "contrast": 10.0, "brightness": 2.0}, 0,
     "nuisance", ["no", "no", "no", "no"]),
])
def test_the_tree_walks_to_the_right_leaf(feats, want_bin, want_label,
                                          want_path):
    ctx = _ctx(**feats)
    score, got = _eval_score(_recipe(DECIDE_TREE), ctx)
    assert got == want_bin
    assert ctx.meta["decide"]["label"] == want_label
    assert ctx.meta["decide"]["path"] == want_path
    assert score == pytest.approx(feats["contrast"])


# --------------------------------------------------------------------------- #
# 2. 路徑跟 bin 一致（走 path 重算一次必同）
# --------------------------------------------------------------------------- #
def _replay(tree, path):
    node = tree
    for step in path:
        node = node.yes if step == "yes" else node.no
    assert isinstance(node, TreeLeaf), "path 沒有走到葉子"
    return node.bin


@pytest.mark.parametrize("missing", [0.0, 1.0])
@pytest.mark.parametrize("contrast", [0.0, 31.0, 121.0])
@pytest.mark.parametrize("brightness", [0.0, 7.0])
def test_the_recorded_path_replays_to_the_same_bin(missing, contrast,
                                                   brightness):
    ctx = _ctx(missing=missing, contrast=contrast, brightness=brightness)
    _, got = _eval_score(_recipe(DECIDE_TREE), ctx)
    assert _replay(TREE, ctx.meta["decide"]["path"]) == got


# --------------------------------------------------------------------------- #
# 3. 平面規則清單＝鏈狀樹（F24 的立論，用值網格驗）
# --------------------------------------------------------------------------- #
RULES = DecideSpec(
    rules=[Rule("missing > 0", 9, "not measurable"),
           Rule("contrast > 120", 3, "big particle"),
           Rule("contrast > 30", 2, "particle"),
           Rule("brightness > 6", 1, "faint")],
    otherwise_bin=0, otherwise_label="nuisance", score="contrast")


def test_rules_convert_to_an_equivalent_chain_tree():
    """同一組特徵值，走 rules 與走轉出來的樹，bin 與 label 逐點相同。

    這一條是「F24 不是換掉 F22，是一般化」的證明 —— 它一紅，舊 recipe 的
    自動遷移就不是無損的。
    """
    chained = DecideSpec(tree=rules_to_tree(RULES), score="contrast")
    grid = itertools.product([0.0, 1.0], [0.0, 31.0, 121.0, 200.0],
                             [0.0, 6.0, 7.0])
    for m, c, b in grid:
        ctx_r = _ctx(missing=m, contrast=c, brightness=b)
        ctx_t = _ctx(missing=m, contrast=c, brightness=b)
        _, bin_r = _eval_score(_recipe(RULES), ctx_r)
        _, bin_t = _eval_score(_recipe(chained), ctx_t)
        assert bin_r == bin_t, (m, c, b)
        assert (ctx_r.meta["decide"]["label"]
                == ctx_t.meta["decide"]["label"]), (m, c, b)


def test_empty_rules_convert_to_the_otherwise_leaf():
    empty = DecideSpec(rules=[], otherwise_bin=7, otherwise_label="all")
    assert rules_to_tree(empty) == TreeLeaf(bin=7, label="all")


# --------------------------------------------------------------------------- #
# 4. round-trip 是 identity，而且只寫在用的那一種
# --------------------------------------------------------------------------- #
def test_a_tree_recipe_round_trips_unchanged():
    r = _recipe(DECIDE_TREE)
    once = r.to_json_dict()
    assert Recipe.from_json_dict(once).to_json_dict() == once
    assert Recipe.from_json_dict(once).decide.tree == TREE


def test_the_json_carries_only_the_shape_in_use():
    tree_json = _recipe(DECIDE_TREE).to_json_dict()["decide"]
    assert "tree" in tree_json
    assert "rules" not in tree_json and "otherwise" not in tree_json, \
        "兩個都寫出去，讀回來就是 ambiguous-decision —— 自己存的檔案把自己弄壞"
    rules_json = _recipe(RULES).to_json_dict()["decide"]
    assert "rules" in rules_json and "tree" not in rules_json


def test_a_rules_recipe_still_reads_exactly_as_before():
    """F22 的寫法照讀不誤 —— 遷移判準是「舊東西在不在」（鐵則 9）。"""
    once = _recipe(RULES).to_json_dict()
    back = Recipe.from_json_dict(once)
    assert back.decide.tree is None
    assert back.decide.rules == RULES.rules


# --------------------------------------------------------------------------- #
# 5. 寫壞的樹在讀檔當場擋
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    {"when": "a > 1", "yes": {"bin": 1}},                 # 少了 no
    {"when": "a > 1", "bin": 2, "yes": {"bin": 1},
     "no": {"bin": 0}},                                   # 又是步驟又是葉子
    {"label": "x"},                                       # 兩個都不是
    "not a dict",
])
def test_a_broken_tree_is_refused_at_read_time(bad):
    raw = _recipe(DECIDE_TREE).to_json_dict()
    raw["decide"]["tree"] = bad
    with pytest.raises(RecipeError):
        Recipe.from_json_dict(raw)


# --------------------------------------------------------------------------- #
# 6. lint
# --------------------------------------------------------------------------- #
def test_rules_and_tree_together_is_an_error():
    both = DecideSpec(tree=TREE, rules=list(RULES.rules), score="contrast")
    codes = {i.code for i in validate(_recipe(both)) if i.level == "error"}
    assert "ambiguous-decision" in codes, codes


def test_a_tree_only_recipe_is_clean():
    issues = [i for i in validate(_recipe(DECIDE_TREE)) if i.level == "error"]
    assert not issues, issues
    codes = {i.code for i in validate(_recipe(DECIDE_TREE))}
    assert "no-rules" not in codes, "有樹的時候不要喊沒規則"


def test_a_very_deep_tree_is_a_warning_not_an_error():
    node = TreeLeaf(bin=0, label="")
    for i in range(20):
        node = TreeStep(when="a > %d" % i, yes=TreeLeaf(bin=1, label=""),
                        no=node)
    issues = validate(_recipe(DecideSpec(tree=node)))
    assert "deep-tree" in {i.code for i in issues}
    assert not [i for i in issues if i.level == "error"]


def test_a_step_whose_question_does_not_parse_is_an_error():
    bad = DecideSpec(tree=TreeStep(when="a >", yes=TreeLeaf(bin=1, label=""),
                                   no=TreeLeaf(bin=0, label="")))
    codes = {i.code for i in validate(_recipe(bad)) if i.level == "error"}
    assert "bad-rule" in codes, codes


# --------------------------------------------------------------------------- #
# undo 快照帶得動樹（Studio 那一半的地基）
# --------------------------------------------------------------------------- #
def test_the_editor_snapshot_carries_the_tree():
    """漏掉的話，一份判定樹 recipe 在 Studio 裡按一次 undo，樹就安靜地消失。"""
    from d4t.ui.viewmodel import _decide_restore, _decide_snapshot
    back = _decide_restore(_decide_snapshot(DECIDE_TREE))
    assert back == DECIDE_TREE
