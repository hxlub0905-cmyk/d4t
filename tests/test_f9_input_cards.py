# F9 Phase 3d 第三批：輸入變卡片、``routes`` 退場（2026-08-15）。
"""「這條 pipeline 吃什麼資料」是**畫布上第一張卡的身分**，不是一個 JSON 欄位。

以前那件事寫在 ``Recipe.routes`` 的鍵上 —— 一個使用者從來沒看過的地方，
而它同時決定了三件事：跑哪幾張卡、卡片的埠長什麼樣（``load_patch`` 一張卡
吃所有型別，吐什麼要看 kind）、以及 Studio 能不能開這份檔案。

現在一種資料型別一張 Input 卡（``accepts_kinds``），``order`` 只說順序，
從每一張 Input 卡切一段。
"""
from __future__ import annotations

import json

import pytest

import adept.core.steps  # noqa: F401 — 卡片註冊是 import 的副作用

from adept.core.pipeline import (
    Recipe, RecipeNode, accepted_kinds, execution_order, get_step,
    pipeline_segments, route_for_kind, validate,
)
from adept.core.pipeline.recipe import RecipeError


# --------------------------------------------------------------------------- #
# 1. Input 卡自己說吃什麼
# --------------------------------------------------------------------------- #
def test_each_input_type_has_its_own_card():
    assert get_step("load_patch").accepts_kinds == ("ebi_patch",)
    assert get_step("load_single").accepts_kinds == ("rsem", "folder")


def test_an_input_card_says_what_it_writes_without_being_told_the_kind():
    """§5d.3 那個坑的根：以前埠算了兩次，而編譯期知道 kind、執行期不知道。

    線接到 ``load.single``、執行期卻吐在 ``load.test`` 上 —— 整條下游安靜地
    不跑。現在每張 Input 卡吐什麼是寫死的，那個分岔不存在了。
    """
    from adept.core.pipeline.graph import stream_ports

    for key, expect in (("load_patch", ("test", "ref")),
                        ("load_single", ("single", "test"))):
        cls = get_step(key)
        assert cls.resolve_writes({"channels": "auto"}) == list(expect)
        _ins, outs = stream_ports(cls, {"channels": "auto"})
        assert outs == expect          # 埠 = 那幾條流，不必問 kind


def test_ordinary_cards_are_not_inputs():
    """``accepts_kinds`` 非空就是「一條 pipeline 的起點」—— 別讓它長在別處。"""
    for key in ("normalize", "align", "subtract", "glv_stats", "adc"):
        assert get_step(key).accepts_kinds == ()


# --------------------------------------------------------------------------- #
# 2. order + Input 卡 = 跑哪幾張
# --------------------------------------------------------------------------- #
def _two_pipelines() -> Recipe:
    return Recipe(
        recipe_id="two",
        order=["p_load", "p_glv", "s_load", "s_glv"],
        nodes={
            "p_load": RecipeNode("p_load", "load_patch", {}),
            "p_glv": RecipeNode("p_glv", "glv_stats", {}),
            "s_load": RecipeNode("s_load", "load_single", {}),
            "s_glv": RecipeNode("s_glv", "glv_stats", {}),
        })


def test_one_recipe_can_hold_several_pipelines():
    rec = _two_pipelines()
    assert pipeline_segments(rec) == [["p_load", "p_glv"], ["s_load", "s_glv"]]
    assert route_for_kind(rec, "ebi_patch") == ["p_load", "p_glv"]
    assert route_for_kind(rec, "rsem") == ["s_load", "s_glv"]
    assert accepted_kinds(rec) == ["ebi_patch", "folder", "rsem"]


def test_execution_order_only_runs_the_matching_pipeline():
    rec = _two_pipelines()
    assert execution_order(rec, "ebi_patch") == ["p_load", "p_glv"]
    assert execution_order(rec, "rsem") == ["s_load", "s_glv"]


def test_a_kind_nobody_accepts_says_what_this_recipe_does_take():
    rec = _two_pipelines()
    del rec.nodes["s_load"], rec.nodes["s_glv"]
    rec.order = ["p_load", "p_glv"]
    with pytest.raises(RecipeError) as e:
        execution_order(rec, "rsem")
    assert "rsem" in str(e.value) and "ebi_patch" in str(e.value)


def test_a_recipe_with_no_input_card_at_all_says_so():
    rec = Recipe(recipe_id="headless", order=["glv"],
                 nodes={"glv": RecipeNode("glv", "glv_stats", {})})
    codes = [i.code for i in validate(rec, kind="ebi_patch")]
    assert "no-input" in codes
    with pytest.raises(RecipeError):
        execution_order(rec, "ebi_patch")


# --------------------------------------------------------------------------- #
# 3. 舊檔案（routes）照樣載得進來
# --------------------------------------------------------------------------- #
def _legacy_two_routes() -> dict:
    """兩條 route **共用** 中間那幾個節點 —— 舊模型天生長這樣。"""
    return {
        "recipe_id": "legacy2",
        "routes": {"ebi_patch": ["load", "glv"],
                   "rsem": ["load", "golden", "glv"]},
        "nodes": {
            "load": {"step": "load_patch", "params": {}},
            "golden": {"step": "golden_cell", "params": {"out": "ref"}},
            "glv": {"step": "glv_stats", "params": {}},
        },
    }


def test_an_old_routes_file_becomes_one_order_plus_input_cards():
    rec = Recipe.from_json_dict(_legacy_two_routes())
    segs = pipeline_segments(rec)
    assert len(segs) == 2, segs
    # 起手卡各換成對的變體 —— 舊檔案兩條 route 共用同一張 ``load_patch``
    assert rec.nodes[segs[0][0]].step == "load_patch"
    assert rec.nodes[segs[1][0]].step == "load_single"
    assert route_for_kind(rec, "ebi_patch") == segs[0]
    assert route_for_kind(rec, "rsem") == segs[1]


def test_nodes_shared_by_two_old_routes_are_split_into_one_copy_each():
    """共用的那一張會讓「改 rsem 的門檻」順手改掉 patch 的。"""
    rec = Recipe.from_json_dict(_legacy_two_routes())
    ebi = route_for_kind(rec, "ebi_patch")
    rsem = route_for_kind(rec, "rsem")
    assert not (set(ebi) & set(rsem))
    # 複製出來的是**內容相同的另一份**，不是同一個物件
    assert len([n for n in rec.nodes.values() if n.step == "glv_stats"]) == 2


def test_saving_writes_order_and_never_routes():
    rec = Recipe.from_json_dict(_legacy_two_routes())
    out = rec.to_json_dict()
    assert "routes" not in out
    assert out["order"] == list(rec.order)


def test_a_round_trip_is_stable():
    """遷移過的檔案再讀一次不會再遷移一次（沒有 ``routes`` 就沒有觸發條件）。"""
    rec = Recipe.from_json_dict(_legacy_two_routes())
    again = Recipe.from_json_dict(json.loads(json.dumps(rec.to_json_dict())))
    assert again.order == rec.order
    assert sorted(again.nodes) == sorted(rec.nodes)
    assert [n.step for n in again.nodes.values()] == \
           [n.step for n in rec.nodes.values()]


def test_a_file_with_neither_order_nor_routes_is_rejected():
    with pytest.raises(RecipeError):
        Recipe.from_json_dict({"recipe_id": "x", "nodes": {}})


# --------------------------------------------------------------------------- #
# 4. 產品範圍：吃不下的 Input 卡不該出現在卡片庫
# --------------------------------------------------------------------------- #
def test_the_library_only_offers_input_cards_this_build_can_run():
    """一張只吃 RSEM 的 Input 卡出現在只支援 patch 的 build 裡，使用者拉得
    出來、接得完，然後跑起來每一顆都失敗。"""
    from adept.core.pipeline import list_steps
    from adept.ui import scope

    described = [s.describe() for s in list_steps()]
    keys = [d["key"] for d in scope.visible_steps(described)]
    assert "load_patch" in keys
    assert "load_single" not in keys


def test_turning_rsem_back_on_brings_its_input_card_back(monkeypatch):
    """收起來的成本是零、回復的成本是一個字串 —— 這條鎖住後半句。"""
    from adept.core.pipeline import list_steps
    from adept.ui import scope

    monkeypatch.setattr(scope, "SUPPORTED_KINDS", ("ebi_patch", "rsem"))
    described = [s.describe() for s in list_steps()]
    keys = [d["key"] for d in scope.visible_steps(described)]
    assert "load_single" in keys
