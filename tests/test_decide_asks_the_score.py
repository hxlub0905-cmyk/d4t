# F122 期 1：樹上問 `score` —— 整批跑與 Re-run 要是同一個答案。
"""**同一份 recipe、同一批數字，只能分出一種 bin。**

2026-09-29 以前，引擎在判定**之後**才算分數，而 lint 讓樹問 ``score``：

* 整批跑：那一題問不出來 → 答「否」；
* Re-run（`batch.redecide`，整批換算也走它）：上一次的分數還躺在存下來的
  features 裡 → 答得出來。

這一份鎖三件事：分數在判定之前算（樹問得到它）、重判時上一次的 ``score`` /
``decide_unanswered`` 不准留下來冒充這一次的、lint 只在**真的有分數表達式**時
讓樹問它。順帶鎖同一支 lint 的另外三句話（F122 期 1 一起修的）。
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import DataProfile  # noqa: E402
from d4t.core.pipeline.batch import rerun_decision  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.engine import _eval_score  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Let, Recipe, RecipeNode, ScoreSpec, TreeLeaf, TreeStep,
)
from d4t.core.pipeline.recipe_schema import RouteBy  # noqa: E402
from d4t.core.pipeline.recipe_validate import validate  # noqa: E402


def _recipe(when="score > 5", score="glv_median * 2", **decide):
    return Recipe(
        recipe_id="t", routes={"ebi_patch": ["load", "glv"]},
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "glv": RecipeNode("glv", "glv_stats",
                                 {"source": "test", "metrics": "glv_median"})},
        score=ScoreSpec(expr="", threshold=0.0, bins={"below": 0, "above": 1}),
        decide=DecideSpec(tree=TreeStep(when=when,
                                        yes=TreeLeaf(bin=1, label="hot"),
                                        no=TreeLeaf(bin=0, label="quiet")),
                          score=score, **decide))


def _full_run(recipe, values):
    """引擎那條路：每一顆從乾淨的 context 起算（= 整批跑）。"""
    rows = []
    for i, v in enumerate(values):
        ctx = Context(images={})
        ctx.add_features({"glv_median": v})
        score, b = _eval_score(recipe, ctx)
        rows.append({"defect_id": "d%d" % i, "ok": True, "error": None,
                     "features": dict(ctx.features), "score": score, "bin": b,
                     "traces": [{"node_id": "glv", "ok": True, "ms": 1.0}]})
    return rows


# --------------------------------------------------------------------------- #
# 引擎：分數在判定之前
# --------------------------------------------------------------------------- #
def test_the_tree_can_ask_the_score():
    rows = _full_run(_recipe(), [1.0, 4.0])          # score = 2, 8
    assert [r["bin"] for r in rows] == [0, 1]
    assert [r["features"]["decide_unanswered"] for r in rows] == [0.0, 0.0]


def test_a_full_run_and_a_rerun_give_the_same_bins():
    recipe = _recipe()
    rows = _full_run(recipe, [1.0, 4.0, 10.0])
    again = copy.deepcopy(rows)
    rerun_decision(recipe, again)
    assert [r["bin"] for r in again] == [r["bin"] for r in rows]


def test_a_rerun_does_not_answer_with_last_times_score():
    """**反向**：拿掉分數表達式之後重判，上一次的分數不准冒充這一次的 ——
    整批跑的時候那一題問不出來，Re-run 也要問不出來。"""
    rows = _full_run(_recipe(), [10.0])               # score = 20 → bin 1
    assert rows[0]["bin"] == 1
    no_score = _recipe(score="")
    rerun_decision(no_score, rows)
    fresh = _full_run(no_score, [10.0])
    assert rows[0]["bin"] == fresh[0]["bin"] == 0
    assert "score" not in rows[0]["features"]
    assert rows[0]["score"] is None
    assert rows[0]["features"]["decide_unanswered"] == 1.0


# --------------------------------------------------------------------------- #
# lint：樹看得到 score 的條件、題目的用字
# --------------------------------------------------------------------------- #
def _unknown(recipe, data=None):
    return [i for i in validate(recipe, "ebi_patch", data=data)
            if i.code == "unknown-feature"]


def test_the_lint_lets_the_tree_ask_the_score_only_when_there_is_one():
    assert not _unknown(_recipe())
    said = _unknown(_recipe(score=""))
    assert said and said[0].names == ("score",)


def test_a_let_cannot_see_the_score():
    """分數在 let **之後**算 —— let 問它，每一顆都會失敗。"""
    r = _recipe(when="x > 1", let=[Let(name="x", expr="score")])
    said = _unknown(r)
    assert said and "fail" in said[0].detail


def test_a_question_on_a_missing_number_says_no_not_fail():
    said = _unknown(_recipe(when="nosuch > 1"))
    assert said
    assert "answered 'no'" in said[0].detail
    assert "will fail" not in said[0].detail
    routed = _unknown(_recipe(when="nosuch > 1", unanswered_bin=99))
    assert "bin 99" in routed[0].detail


def test_route_taken_is_known_when_the_recipe_routes():
    r = _recipe(when="route_taken > 0")
    r.routes["rsem"] = ["load", "glv"]
    r.route_by = RouteBy(column="CLASSNUMBER", map={"1": "ebi_patch"},
                         default="rsem")
    names = [n for i in validate(r) if i.code == "unknown-feature"
             for n in i.names]
    assert "route_taken" not in names


def _data(has_klarf, columns=()):
    return DataProfile(kind="ebi_patch" if has_klarf else "folder",
                       n_items=3, images_min=2, images_max=2,
                       image_names=("test", "ref"), has_klarf=has_klarf,
                       columns=tuple(columns))


def test_a_klarf_column_says_carry_it_or_that_there_is_no_klarf():
    r = _recipe(when="CLASSNUMBER == 3")
    carry = _unknown(r, _data(True, ["CLASSNUMBER", "XREL"]))
    assert "Carry these columns" in carry[0].detail
    none = _unknown(r, _data(False))
    assert "this data has no KLARF" in none[0].detail
    assert "this data has no KLARF" not in _unknown(r)[0].detail  # 不知道資料就不講
