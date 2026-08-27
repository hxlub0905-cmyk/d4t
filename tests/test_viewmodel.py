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
    n = m.add_step("denoise")
    m.set_param(n, "ksize", 5)
    assert m.nodes[n].params["ksize"] == 5
    with pytest.raises(ParamError):
        m.set_param(n, "ksize", 999)           # 超出上限
    assert m.nodes[n].params["ksize"] == 5     # 不落地


def test_available_streams_and_features():
    m = RecipeModel(kind="ebi_patch")
    load = m.add_step("load_patch")
    m.add_step("align")
    sub = m.add_step("subtract")
    glv = m.add_step("glv_stats")
    streams = m.available_streams(before_node=sub)
    assert "test" in streams and "ref" in streams and "ref_aligned" in streams
    feats = m.available_features()
    assert "glv_median" in feats and "align_dx" in feats
    assert "glv_median" not in m.available_features(upto_node=sub)
    assert m.category_of(load) == "image" and m.category_of(glv) == "algo"


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


def test_the_nm_numbers_are_only_offered_when_someone_says_how_big_a_pixel_is():
    """量測卡**一律宣告** `cd_median_nm` 那一組（它看不到 Load 卡上填了什麼）。

    但下拉是使用者**會去點**的東西 —— 點了一個永遠不會出現的名字，recipe 就
    會在跑起來的時候每一顆都失敗。這裡看得到每一張卡，所以這句話在這裡回答。
    """
    m = RecipeModel(kind="ebi_patch")
    load = m.add_step("load_patch")
    m.add_step("subtract")
    m.add_step("cd_measure")

    assert not m.nm_per_px_is_known()
    feats = m.available_features()
    assert "cd_median" in feats
    assert "cd_median_nm" not in feats

    m.set_param(load, "nm_per_px", 1.5)
    assert m.nm_per_px_is_known()
    feats = m.available_features()
    assert "cd_median" in feats                    # pixel 那一份沒有被換掉
    assert "cd_median_nm" in feats

    m.set_param(load, "nm_per_px", 0.0)            # 清掉就收回去
    assert "cd_median_nm" not in m.available_features()


# --------------------------------------------------------------------------- #
# 一張卡不能吃自己還沒寫的東西
#
# 2026-08-27（Phase 3）從 `test_ui_f21_expr_picker.py` 搬過來。原本用
# `feature_math` 觸發（那張卡刪掉了），改用 `glv_stats` 的 `judge` —— 那一格
# 問的是同一件事：**清單裡不可以出現這張卡自己要寫出去的名字。**
# 它是 `include_upto=False` 全 repo 唯一的守門人。
# --------------------------------------------------------------------------- #
def test_a_card_does_not_offer_its_own_output():
    """點下去就是 `x = x`。引擎擋得住（`unknown-feature-input`），但**讓使用者
    點一個保證壞掉的選項本身就是 bug**（推廣鐵則）。

    這是把 Studio 跑起來、把選單印出來才看到的 —— 元件測試看不到，因為清單是
    Studio 填的。
    """
    m = RecipeModel()
    m.add_step("glv_stats")
    second = m.add_step("glv_stats")
    m.set_param(second, "output_prefix", "mine")
    inclusive = [x.split("\t", 1)[0]
                 for x in m.labelled_features(upto_node=second)]
    exclusive = [x.split("\t", 1)[0]
                 for x in m.labelled_features(upto_node=second,
                                              include_upto=False)]
    mine = [x for x in inclusive if x.startswith("mine_")]
    assert mine, "前提：第二張卡真的會寫出 mine_* 這幾個名字"
    assert not [x for x in exclusive if x.startswith("mine_")], exclusive
    assert set(exclusive) < set(inclusive), "上游的那些還是要在"
