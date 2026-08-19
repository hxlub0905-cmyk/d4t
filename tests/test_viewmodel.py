# d4t M3 viewmodel 測試（Qt-free）— authored 2026-07-28.
from __future__ import annotations

from pathlib import Path

import pytest

import d4t.core.steps  # noqa: F401 — 註冊卡片
from d4t.core.pipeline import ParamError, Recipe
from d4t.ui.viewmodel import RecipeModel, histogram, rebin

RECIPE = Path(__file__).resolve().parent / "fixtures" / "recipes" / "die_to_die_basic.json"


def test_build_route_by_mouse_ops():
    m = RecipeModel(kind="ebi_patch")
    changes = []
    m.add_listener(lambda: changes.append(1))
    a = m.add_step("load_patch")
    b = m.add_step("normalize")
    c = m.add_step("align")
    assert m.node_order == [a, b, c] and changes
    # 重複 key → 唯一 id
    d = m.add_step("align")
    assert d == "align2"
    m.move(d, -1)
    assert m.node_order == [a, b, d, c]
    m.remove(d)
    assert m.node_order == [a, b, c]
    m.set_enabled(b, False)
    assert m.nodes[b].enabled is False


def test_param_validation_rejects_bad_value():
    m = RecipeModel()
    m.add_step("load_patch")
    n = m.add_step("snr_map")
    m.set_param(n, "window", 15)
    assert m.nodes[n].params["window"] == 15
    with pytest.raises(ParamError):
        m.set_param(n, "window", 999)          # 超出上限
    assert m.nodes[n].params["window"] == 15   # 不落地


def test_available_streams_and_features():
    m = RecipeModel(kind="ebi_patch")
    load = m.add_step("load_patch")
    m.add_step("align")
    sub = m.add_step("subtract")
    snr = m.add_step("snr_map")
    streams = m.available_streams(before_node=sub)
    assert "test" in streams and "ref" in streams and "ref_aligned" in streams
    feats = m.available_features()
    assert "snr_max" in feats and "align_dx" in feats
    assert "snr_max" not in m.available_features(upto_node=sub)
    assert m.category_of(load) == "image" and m.category_of(snr) == "algo"


def test_roundtrip_with_example_recipe():
    recipe = Recipe.load(str(RECIPE))
    m = RecipeModel.from_recipe(recipe)
    assert m.kind == "ebi_patch" and not m.dirty
    out = m.to_recipe()
    assert out.routes["ebi_patch"] == recipe.routes["ebi_patch"]
    assert out.score.expr == recipe.score.expr
    issues = m.validate()
    assert not [i for i in issues if i.level == "error"]
    m.set_threshold(60.0)
    assert m.dirty and m.to_recipe().score.threshold == 60.0


def test_histogram_and_rebin():
    edges, counts = histogram([1, 2, 2, 3, 10], n_bins=9)
    assert len(edges) == 10 and sum(counts) == 5
    assert histogram([])[1] == [0]
    out = rebin([1.0, 2.0, 60.0, None, float("nan")], threshold=50.0)
    assert out == {0: 2, 1: 1}
