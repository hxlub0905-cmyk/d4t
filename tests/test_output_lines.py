# F123 期 3：Output 自己的輸入（2026-09-29）。
"""Output 卡也是照**線**拿東西，不是照名字撿：

1. **Write comparison** 的左右兩張圖是真的影像埠 —— 線接哪一張卡的哪一顆埠，
   拿的就是那一張卡當時吐的那一份（`engine.image_through_line`），不是整份結果裡
   「最後一個寫這個名字的人」。
2. **Write charts** 只畫它上游那幾張 GLV 量的框（`output._upstream_notes`）。
3. Output 卡用名字吃的數字，產出它的卡不在上游 → 講出來
   （`output-number-not-upstream`），不然那一欄會安靜地整排空白。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import run_defect, validate  # noqa: E402
from d4t.core.pipeline.engine import image_through_line  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    Edge, Recipe, RecipeNode, ScoreSpec,
)
from d4t.core.pipeline.step import NUMBERS, RESULTS, get_step  # noqa: E402
from d4t.core.steps.output import _upstream_notes  # noqa: E402

KIND = "ebi_patch"


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    from make_sample import generate
    lot = generate(str(tmp_path_factory.mktemp("outlines")), n=2, seed=3)
    return load_dataset(lot["klarf"])


def _comparison(main_from="load"):
    """Input → Tone（**就地**改 test）→ Decision → Write comparison。

    左邊那顆埠接的是 ``main_from`` 的 ``test``：接 Input 的話要拿到**原圖**，
    而整份結果裡叫 ``test`` 的那一份是 Tone 改過的。
    """
    nodes = {"load": RecipeNode("load", "load_patch", {}),
             "tone": RecipeNode("tone", "tone", {"streams": "test",
                                                 "gamma": 2.0}),
             "dec": RecipeNode("dec", "decision", {}),
             "out": RecipeNode("out", "output_char",
                               {"folder": "/tmp/x", "main_stream": "test",
                                "pair_stream": "ref"})}
    edges = [Edge("load", "tone", "test", "streams"),
             Edge(main_from, "out", "test", "main_stream"),
             Edge("load", "out", "ref", "pair_stream"),
             Edge("dec", "out", RESULTS, RESULTS)]
    return Recipe(recipe_id="cmp", routes={KIND: list(nodes)}, nodes=nodes,
                  edges=edges, score=ScoreSpec(expr="", threshold=0.0,
                                               bins={}))


# --------------------------------------------------------------------------- #
# 1. Write comparison：照線拿圖
# --------------------------------------------------------------------------- #
def test_the_comparison_pictures_are_image_ports():
    cls = get_step("output_char")
    names = [p.name for p in cls.input_specs()]
    assert names == ["main_stream", "pair_stream"]
    assert cls.params[[p.name for p in cls.params].index(
        "pair_stream")].required_input({}), "右邊那張是這張卡的重點"


def test_the_left_picture_is_the_one_the_line_points_at(dataset):
    recipe = _comparison("load")
    item = dataset.items[0]
    ctx = run_defect(recipe, item, KIND, keep_context=True).context
    raw = ctx._produced[("load", "test")]
    toned = ctx.images["test"]
    assert not np.array_equal(raw, toned), "前提：Tone 真的改了 test"
    got = image_through_line(recipe, ctx, item, "out", "main_stream", KIND)
    assert np.array_equal(got, raw), "接 Input 的線拿到的是 Tone 之後那張"

    recipe = _comparison("tone")
    ctx = run_defect(recipe, item, KIND, keep_context=True).context
    got = image_through_line(recipe, ctx, item, "out", "main_stream", KIND)
    assert np.array_equal(got, ctx._produced[("tone", "test")])


def test_an_unconnected_left_picture_is_none(dataset):
    recipe = _comparison("load")
    recipe.nodes["out"].params["main_stream"] = ""
    item = dataset.items[0]
    ctx = run_defect(recipe, item, KIND, keep_context=True).context
    assert image_through_line(recipe, ctx, item, "out", "main_stream",
                              KIND) is None


# --------------------------------------------------------------------------- #
# 2. Write charts：只畫上游那幾張 GLV 的框
# --------------------------------------------------------------------------- #
class _Bctx:
    def __init__(self, recipe, node_id):
        self.recipe, self.node_id = recipe, node_id


def test_the_charts_draw_only_the_boxes_of_the_gray_level_cards_upstream():
    recipe = Recipe(recipe_id="c", routes={KIND: ["g1", "g2", "out"]},
                    nodes={"g1": RecipeNode("g1", "glv_stats", {}),
                           "g2": RecipeNode("g2", "glv_stats", {}),
                           "out": RecipeNode("out", "output_uniformity", {})},
                    edges=[Edge("g1", "out", NUMBERS, RESULTS)],
                    score=ScoreSpec(expr="", threshold=0.0, bins={}))
    notes = [{"node": "g1", "region": "a"}, {"node": "g2", "region": "b"},
             {"region": "old"}]
    kept = _upstream_notes(_Bctx(recipe, "out"), notes)
    assert [n["region"] for n in kept] == ["a", "old"], \
        "g2 不在上游；沒記是誰量的（舊快照）留著"


# --------------------------------------------------------------------------- #
# 3. 用名字吃的數字要在上游
# --------------------------------------------------------------------------- #
def _report(rank_by, *extra):
    nodes = {"load": RecipeNode("load", "load_patch", {}),
             "glv": RecipeNode("glv", "glv_stats",
                               {"source": "test", "metrics": "glv_max"}),
             "cd": RecipeNode("cd", "cd_measure", {"source": "test"}),
             "dec": RecipeNode("dec", "decision", {}),
             "out": RecipeNode("out", "output_report",
                               {"folder": "/tmp/x", "rank_by": rank_by})}
    edges = [Edge("load", "glv", "test", "source"),
             Edge("load", "cd", "test", "source"),
             Edge("glv", "dec", NUMBERS, NUMBERS),
             Edge("dec", "out", RESULTS, RESULTS)] + list(extra)
    return Recipe(recipe_id="r", routes={KIND: list(nodes)}, nodes=nodes,
                  edges=edges, score=ScoreSpec(expr="glv_max", threshold=1.0,
                                               bins={"below": 0, "above": 1}))


def _warned(recipe):
    return [i for i in validate(recipe, kind=KIND)
            if i.code == "output-number-not-upstream"]


def test_a_column_from_a_card_that_is_not_wired_in_is_called_out():
    got = _warned(_report("cd_median"))
    assert got and got[0].level == "warning" and got[0].node_id == "out"
    assert "cd_median" in got[0].names
    assert not _warned(_report("cd_median",
                               Edge("cd", "out", NUMBERS, RESULTS)))
    assert not _warned(_report("glv_max")), "GLV 經 Decision 在上游"
