"""M1 驗收：Recipe JSON serde、execution_order、lint 式 validate。

本檔的 dummy Step 不進全域 REGISTRY —— 一律以 registry= 參數顯式傳入
validate()，避免與並行開發中的 flexadc/core/steps/ 相互干擾。
"""
from __future__ import annotations

import json

import pytest

from flexadc.core.pipeline import (
    CATEGORY_ALGO,
    CATEGORY_IMAGE,
    ParamSpec,
    Recipe,
    RecipeError,
    RecipeNode,
    ScoreSpec,
    Step,
    execution_order,
    validate,
)


# ---------------------------------------------------------------------------
# dummy 卡片（僅供本測試檔；不註冊進 REGISTRY）
# ---------------------------------------------------------------------------
class TLoadPair(Step):
    key = "t_load_pair"
    label = "測試載入（test+ref）"
    category = CATEGORY_IMAGE
    help = "測試用：寫入 test 與 ref 影像流"
    writes = ["test", "ref"]

    def run(self, ctx, params):
        return ctx


class TLoadSingle(Step):
    key = "t_load_single"
    label = "測試載入（單張）"
    category = CATEGORY_IMAGE
    help = "測試用：只寫入 test 影像流"
    writes = ["test"]

    def run(self, ctx, params):
        return ctx


class TSubtract(Step):
    key = "t_subtract"
    label = "測試相減"
    category = CATEGORY_IMAGE
    help = "測試用：test - ref → diff"
    reads = ["test", "ref"]
    writes = ["diff"]

    def run(self, ctx, params):
        return ctx


class TSnr(Step):
    key = "t_snr"
    label = "測試 SNR"
    category = CATEGORY_ALGO
    help = "測試用：從 diff 量 snr_max"
    reads = ["diff"]
    features_out = ["snr_max"]
    params = [ParamSpec("k", "int", 3, "視窗大小", min=1, max=9)]

    def run(self, ctx, params):
        return ctx


class TNeedsRef(Step):
    key = "t_needs_ref"
    label = "測試需 ref"
    category = CATEGORY_IMAGE
    help = "測試用：requires_ref 卡"
    reads = ["test"]
    writes = ["aligned"]
    requires_ref = True

    def run(self, ctx, params):
        return ctx


REG = {c.key: c for c in (TLoadPair, TLoadSingle, TSubtract, TSnr, TNeedsRef)}


def make_recipe(**kw):
    base = dict(
        recipe_id="unit_test",
        routes={"ebi_patch": ["load", "sub", "snr"]},
        nodes={
            "load": RecipeNode("load", "t_load_pair", {}),
            "sub": RecipeNode("sub", "t_subtract", {}),
            "snr": RecipeNode("snr", "t_snr", {"k": 5}),
        },
        score=ScoreSpec(expr="snr_max * 2", threshold=3.0,
                        bins={"below": 0, "above": 1}),
        version=2,
        author="unit",
        description="單元測試 recipe",
        edges=[],
    )
    base.update(kw)
    return Recipe(**base)


def codes(issues):
    return [i.code for i in issues]


# ---------------------------------------------------------------------------
# JSON serde
# ---------------------------------------------------------------------------
def test_json_round_trip_dict():
    r = make_recipe(edges=[["load", "snr"]])
    d = r.to_json_dict()
    r2 = Recipe.from_json_dict(d)
    assert r2 == r
    assert r2.to_json_dict() == d          # round-trip stable
    json.dumps(d)                          # 可序列化


def test_json_defaults_filled():
    d = {
        "recipe_id": "min",
        "routes": {"ebi_patch": ["load"]},
        "nodes": {"load": {"step": "t_load_pair"}},
        "score": {"expr": "1", "threshold": 0.5, "bins": {"below": 0, "above": 1}},
    }
    r = Recipe.from_json_dict(d)
    assert r.version == 1
    assert r.author == ""
    assert r.description == ""
    assert r.edges == []
    assert r.nodes["load"].enabled is True
    assert r.nodes["load"].params == {}
    assert r.nodes["load"].id == "load"


def test_json_missing_required_field():
    with pytest.raises(RecipeError):
        Recipe.from_json_dict({"recipe_id": "x"})


def test_save_load_atomic(tmp_path):
    r = make_recipe()
    p = tmp_path / "recipe.json"
    r.save(p)
    assert p.exists()
    assert not (tmp_path / "recipe.json.tmp").exists()   # atomic：tmp 已 replace
    r2 = Recipe.load(p)
    assert r2 == r
    # utf-8 中文 description 不會壞
    raw = p.read_text(encoding="utf-8")
    assert "單元測試" in raw


# ---------------------------------------------------------------------------
# execution_order
# ---------------------------------------------------------------------------
def test_execution_order_chain():
    r = make_recipe()
    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]


def test_execution_order_extra_edge_consistent():
    # 額外邊與鏈一致 → 順序不變
    r = make_recipe(edges=[["load", "snr"]])
    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]


def test_execution_order_edge_outside_route_ignored():
    # 邊的端點不在該 route 內 → 不影響
    r = make_recipe(edges=[["ghost", "snr"], ["load", "ghost"]])
    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]


def test_execution_order_cycle_raises():
    r = make_recipe(edges=[["snr", "load"]])
    with pytest.raises(RecipeError):
        execution_order(r, "ebi_patch")


def test_execution_order_unknown_kind_raises():
    r = make_recipe()
    with pytest.raises(RecipeError):
        execution_order(r, "no_such_kind")


# ---------------------------------------------------------------------------
# validate — 每個 issue code
# ---------------------------------------------------------------------------
def test_validate_clean_recipe_no_issues():
    r = make_recipe()
    assert validate(r, registry=REG) == []


def test_validate_unknown_step():
    r = make_recipe()
    r.nodes["sub"] = RecipeNode("sub", "nope_step", {})
    issues = validate(r, registry=REG)
    assert "unknown-step" in codes(issues)
    bad = [i for i in issues if i.code == "unknown-step"][0]
    assert bad.node_id == "sub"
    assert bad.level == "error"


def test_validate_bad_param():
    r = make_recipe()
    r.nodes["snr"] = RecipeNode("snr", "t_snr", {"k": 99})     # max=9
    issues = validate(r, registry=REG)
    assert "bad-param" in codes(issues)
    # 壞參數改用預設值繼續模擬 → 不應誤報 missing-image
    assert "missing-image" not in codes(issues)


def test_validate_bad_param_unknown_name():
    r = make_recipe()
    r.nodes["snr"] = RecipeNode("snr", "t_snr", {"nope": 1})
    assert "bad-param" in codes(validate(r, registry=REG))


def test_validate_unknown_node_in_route():
    r = make_recipe(routes={"ebi_patch": ["load", "ghost", "snr"]})
    r.nodes.pop("sub")
    issues = validate(r, registry=REG)
    assert "unknown-node" in codes(issues)


def test_validate_unknown_route_kind():
    r = make_recipe()
    issues = validate(r, kind="no_such_kind", registry=REG)
    assert "unknown-route" in codes(issues)


def test_validate_cycle():
    r = make_recipe(edges=[["snr", "load"]])
    issues = validate(r, registry=REG)
    assert "cycle" in codes(issues)


def test_validate_missing_image():
    # snr 讀 diff，但沒有 subtract 卡產 diff
    r = make_recipe(routes={"ebi_patch": ["load", "snr"]})
    issues = validate(r, registry=REG)
    assert "missing-image" in codes(issues)
    bad = [i for i in issues if i.code == "missing-image"][0]
    assert bad.node_id == "snr"
    assert "diff" in bad.detail


def test_validate_first_node_reads_unchecked():
    # 第一張啟用卡（load 卡）的 reads 不檢查（它從 dataset 拿資料）
    r = make_recipe(routes={"ebi_patch": ["sub"]},
                    nodes={"sub": RecipeNode("sub", "t_subtract", {})},
                    score=ScoreSpec(expr="1", threshold=0.0,
                                    bins={"below": 0, "above": 1}))
    issues = validate(r, registry=REG)
    assert "missing-image" not in codes(issues)


def test_validate_requires_ref_on_rsem():
    r = make_recipe(
        routes={"rsem": ["load1", "align"]},
        nodes={
            "load1": RecipeNode("load1", "t_load_single", {}),
            "align": RecipeNode("align", "t_needs_ref", {}),
        },
        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}),
    )
    issues = validate(r, kind="rsem", registry=REG)
    assert "requires-ref" in codes(issues)
    # 上游有產 ref（t_load_pair）→ 不報
    r.nodes["load1"] = RecipeNode("load1", "t_load_pair", {})
    issues = validate(r, kind="rsem", registry=REG)
    assert "requires-ref" not in codes(issues)


def test_validate_requires_ref_not_flagged_on_ebi_patch():
    r = make_recipe(
        routes={"ebi_patch": ["load", "align"]},
        nodes={
            "load": RecipeNode("load", "t_load_pair", {}),
            "align": RecipeNode("align", "t_needs_ref", {}),
        },
        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}),
    )
    assert "requires-ref" not in codes(validate(r, registry=REG))


def test_validate_score_expr_parse_error():
    r = make_recipe(score=ScoreSpec(expr="snr_max *", threshold=1.0,
                                    bins={"below": 0, "above": 1}))
    issues = validate(r, registry=REG)
    assert "score-expr" in codes(issues)


def test_validate_unknown_feature_warning():
    r = make_recipe(score=ScoreSpec(expr="snr_max * mystery_feat", threshold=1.0,
                                    bins={"below": 0, "above": 1}))
    issues = validate(r, registry=REG)
    warn = [i for i in issues if i.code == "unknown-feature"]
    assert len(warn) == 1
    assert warn[0].level == "warning"
    assert "mystery_feat" in warn[0].detail


def test_validate_score_var_allowed():
    # "score" 本身永遠是合法變數（bin 條件常用）
    r = make_recipe(score=ScoreSpec(expr="snr_max + score * 0", threshold=1.0,
                                    bins={"below": 0, "above": 1}))
    assert "unknown-feature" not in codes(validate(r, registry=REG))


def test_validate_bad_bins():
    r = make_recipe(score=ScoreSpec(expr="snr_max", threshold=1.0,
                                    bins={"below": 0}))
    issues = validate(r, registry=REG)
    assert "bad-bins" in codes(issues)


def test_validate_disabled_node_skipped_in_simulation():
    # subtract 停用 → snr 的 diff 拿不到 → missing-image（與 runtime 一致）
    r = make_recipe()
    r.nodes["sub"].enabled = False
    issues = validate(r, registry=REG)
    assert "missing-image" in codes(issues)


def test_validate_collects_multiple_issues_at_once():
    r = make_recipe(
        routes={"ebi_patch": ["load", "ghost", "snr"]},
        score=ScoreSpec(expr="1 +", threshold=1.0, bins={}),
    )
    r.nodes.pop("sub")
    r.nodes["load"] = RecipeNode("load", "no_such_step", {})
    got = set(codes(validate(r, registry=REG)))
    assert {"unknown-node", "unknown-step", "score-expr", "bad-bins"} <= got
