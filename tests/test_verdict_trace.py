# PR-3：判定重放（`core/pipeline/verdict_trace.py`）。
"""三條立身規矩各有測試：**不重算**（SAFE /0 的值照抄 features）、
**lot-scaled 不重放**（換算後 leaf_bin 仍對）、**缺值標名字**。
壓軸是逐列與引擎一致（合成批 rules + tree 各一）—— 重放器最怕的就是
「跟引擎走的不是同一條路而畫面上看不出來」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import (  # noqa: E402
    Recipe, RecipeNode, ScoreSpec, apply_lot_scaling, run_batch,
)
from d4t.core.pipeline import decide_tree  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Let, Rule, TreeLeaf, TreeStep,
)
from d4t.core.pipeline.verdict_trace import (  # noqa: E402
    valued_text, verdict_trace,
)

KIND = "ebi_patch"


def _recipe(decide=None, score=""):
    return Recipe(
        recipe_id="trace_t", routes={KIND: ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", {})},
        score=ScoreSpec(expr=score, threshold=1.0,
                        bins={"below": 0, "above": 1}),
        decide=decide)


# --------------------------------------------------------------------------- #
# valued_text：pos 替換
# --------------------------------------------------------------------------- #
def test_valued_text_replaces_every_occurrence_of_a_repeated_variable():
    assert valued_text("a + a * 2", {"a": 3.0}) == "3 + 3 * 2"


def test_valued_text_is_immune_to_substring_name_collisions():
    """`a` 是 `abs_a` 的子字串 —— pos 定位各換各的，字串替換法會換壞。"""
    assert valued_text("abs_a - a", {"a": 1.0, "abs_a": 2.0}) == "2 - 1"


def test_valued_text_marks_a_missing_variable():
    assert valued_text("a + b", {"a": 3.0}) == "3 + ?"
    assert valued_text("a + b", {"a": 3.0}, missing_mark="∅") == "3 + ∅"


def test_valued_text_keeps_functions_and_shows_compact_numbers():
    got = valued_text("max(x, 0.125)", {"x": 42.34567})
    assert got == "max(42.35, 0.125)"


def test_valued_text_returns_broken_expressions_unchanged():
    assert valued_text("a +* b", {"a": 1.0}) == "a +* b"
    assert valued_text("", {}) == ""


# --------------------------------------------------------------------------- #
# 立身規矩一：不重算 —— SAFE /0 的值照抄 features
# --------------------------------------------------------------------------- #
def test_the_safe_division_value_is_read_not_recomputed():
    """引擎的 SAFE 語意是 /0→0（`expression.py`）。重放器**照抄** features
    裡的 0，valued 只做替換（"5 / 0"）—— 自己算的那份會炸或算出 inf。"""
    r = _recipe(decide=DecideSpec(
        let=[Let(name="q", expr="x / y")],
        rules=[Rule(when="q > 1", bin=1, label="hot")]))
    t = verdict_trace(r, KIND, {"x": 5.0, "y": 0.0, "q": 0.0})
    (let,) = t.lets
    assert let.value == 0.0                      # 引擎寫的，不是重算的
    assert let.valued == "5 / 0"                 # 替換歸替換，值歸值
    assert t.leaf_bin == 0 and t.path == "n"


# --------------------------------------------------------------------------- #
# let 重放：巢狀帶值、fill、缺值
# --------------------------------------------------------------------------- #
def test_nested_lets_are_valued_layer_by_layer():
    r = _recipe(decide=DecideSpec(
        let=[Let(name="bright", expr="glv_median + glv_mad"),
             Let(name="odd", expr="bright * cd_n")],
        rules=[Rule(when="odd > 3", bin=1, label="odd")]))
    feats = {"glv_median": 40.0, "glv_mad": 2.5,
             "bright": 42.5, "odd": 85.0, "cd_n": 2.0}
    t = verdict_trace(r, KIND, feats)
    assert t.mode == "rules"
    a, b = t.lets
    assert (a.name, a.valued, a.value) == ("bright", "40 + 2.5", 42.5)
    # 第二層看得到第一層的**值** —— features 是判定後快照，中間名都在。
    assert (b.name, b.valued, b.value) == ("odd", "42.5 * 2", 85.0)
    assert t.leaf_bin == 1 and t.path == "y"


def test_a_filled_let_says_so_and_a_missing_input_is_named():
    r = _recipe(decide=DecideSpec(
        let=[Let(name="bright", expr="glv_median", fill="-1")],
        rules=[Rule(when="bright > 0", bin=1, label="hot")]))
    # 這一顆 glv_median 沒人產出：引擎補了 fill、寫 bright_missing=1。
    t = verdict_trace(r, KIND, {"bright": -1.0, "bright_missing": 1.0})
    (let,) = t.lets
    assert let.filled and let.fill == "-1"
    assert let.missing_vars == ("glv_median",)
    assert let.valued == "?"
    # 同一顆、有量到的那天：不算 filled。
    t2 = verdict_trace(r, KIND, {"glv_median": 5.0, "bright": 5.0,
                                 "bright_missing": 0.0})
    assert not t2.lets[0].filled
    assert t2.lets[0].missing_vars == ()


# --------------------------------------------------------------------------- #
# 立身規矩二：lot-scaled 不重放
# --------------------------------------------------------------------------- #
def test_a_lot_scaled_let_is_not_recomputed():
    """`apply_lot_scaling` 之後 features 裡是 z 值。重放器**不重算**那一行
    （鏡射 batch.redecide:414-418）—— 重算會拿到換算前的值、樹走錯邊。"""
    r = _recipe(decide=DecideSpec(
        let=[Let(name="bright", expr="glv_max", scale="z")],
        rules=[Rule(when="bright > 1", bin=1, label="hot")]))
    rows = [{"defect_id": str(i), "ok": True, "error": None, "score": v,
             "bin": 0, "features": {"glv_max": v, "bright": v}}
            for i, v in enumerate((10.0, 12.0, 14.0, 100.0))]
    assert apply_lot_scaling(r, rows) == 4
    assert [row["bin"] for row in rows] == [0, 0, 0, 1]   # 第二趟判的
    for row in rows:
        t = verdict_trace(r, KIND, row["features"])
        assert t.leaf_bin == row["bin"]
        (let,) = t.lets
        assert let.scaled
        assert let.value == row["features"]["bright"]          # z 值
        assert let.raw == row["features"]["bright_raw"]        # 原始值
        assert let.value != let.raw                            # 真的換算過


# --------------------------------------------------------------------------- #
# score-only 與 none
# --------------------------------------------------------------------------- #
def test_score_only_recipes_get_a_valued_expression_and_missing_names():
    r = _recipe(score="glv_median + nosuch")
    t = verdict_trace(r, KIND, {"glv_median": 7.0, "score": 0.0, "bin": 0.0})
    assert t.mode == "score"
    assert t.score_expr == "glv_median + nosuch"
    assert t.score_valued == "7 + ?"
    assert t.missing == ("nosuch",)
    assert t.score == 0.0 and t.leaf_bin == 0
    assert t.threshold == 1.0 and t.bins == {"below": 0, "above": 1}


def test_no_decide_and_no_expression_is_mode_none():
    t = verdict_trace(_recipe(), KIND, {"glv_median": 7.0})
    assert t.mode == "none"
    assert t.lets == () and t.steps == () and t.leaf_bin is None
    # 非數字的值在門口就被濾掉（同 batch.redecide 的過濾）
    t2 = verdict_trace(_recipe(), KIND, {"a": 1, "b": "x", "c": True})
    assert t2.features == {"a": 1.0}


# --------------------------------------------------------------------------- #
# rules 模式：rule_index
# --------------------------------------------------------------------------- #
def test_rule_index_points_at_the_matching_rule():
    r = _recipe(decide=DecideSpec(
        rules=[Rule(when="a > 10", bin=2, label="big"),
               Rule(when="a > 1", bin=1, label="small")],
        otherwise_bin=0, otherwise_label="rest"))
    t = verdict_trace(r, KIND, {"a": 5.0})
    assert (t.rule_index, t.path, t.leaf_bin, t.leaf_label) == (1, "ny", 1,
                                                                "small")
    t2 = verdict_trace(r, KIND, {"a": 0.0})
    assert (t2.rule_index, t2.path, t2.leaf_bin) == (-1, "nn", 0)
    assert t2.leaf_label == "rest"
    t3 = verdict_trace(r, KIND, {"a": 99.0})
    assert (t3.rule_index, t3.path) == (0, "y")


def test_a_step_that_cannot_be_asked_answers_no_and_names_the_gap():
    r = _recipe(decide=DecideSpec(
        rules=[Rule(when="nosuch > 0", bin=2, label="ghost"),
               Rule(when="a > 1", bin=1, label="hot")]))
    t = verdict_trace(r, KIND, {"a": 5.0})
    assert t.steps[0].answer == "no"
    assert t.steps[0].missing == ("nosuch",)
    assert t.steps[0].valued == "? > 0"
    assert t.missing == ("nosuch",)
    assert t.leaf_bin == 1


# --------------------------------------------------------------------------- #
# 壓軸：逐列與引擎一致（rules + tree 各一）
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("tracelot")), n=8, seed=13)


def _batch_recipe(decide):
    return Recipe(
        recipe_id="trace_batch", routes={KIND: ["load", "glv"]},
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "glv": RecipeNode("glv", "glv_stats",
                                 {"source": "test", "metrics": "glv_max"})},
        score=ScoreSpec(expr="", threshold=0.0, bins={"below": 0, "above": 1}),
        decide=decide)


RULES_DECIDE = DecideSpec(
    let=[Let(name="bright", expr="glv_max")],
    rules=[Rule(when="nosuch > 0", bin=2, label="ghost"),
           Rule(when="bright > 222.5", bin=1, label="hot")],
    otherwise_bin=0, otherwise_label="rest", score="bright")

TREE_DECIDE = DecideSpec(
    let=[Let(name="bright", expr="glv_max")],
    tree=TreeStep(when="bright > 222.5",
                  yes=TreeLeaf(bin=1, label="hot"),
                  no=TreeStep(when="nosuch > 0",
                              yes=TreeLeaf(bin=2, label="ghost"),
                              no=TreeLeaf(bin=0, label="ok"))),
    score="bright")


@pytest.mark.parametrize("decide", [RULES_DECIDE, TREE_DECIDE],
                         ids=["rules", "tree"])
def test_every_row_replays_to_what_the_engine_decided(lot, decide):
    r = _batch_recipe(decide)
    rows = run_batch(r, load_dataset(lot["klarf"]), workers=1)
    assert rows and all(row["ok"] for row in rows)
    tree = decide_tree.display_tree(decide)
    bins = set()
    for row in rows:
        feats = row["features"]
        t = verdict_trace(r, KIND, feats)
        bins.add(t.leaf_bin)
        assert t.leaf_bin == row["bin"]
        assert t.path == decide_tree._path_of(tree, feats)
        # 引擎每一題各記一次（不去重）—— 逐步缺值的總數要對上那個數。
        assert sum(len(s.missing) for s in t.steps) \
            == feats["decide_unanswered"]
        assert t.score == feats["score"]
        assert "?" not in t.lets[0].valued        # glv_max 每顆都量得到
    assert len(bins) > 1, "反空洞：這一批要真的走出不只一種判法"
