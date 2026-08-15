"""M1 驗收：Recipe JSON serde、execution_order、lint 式 validate。

本檔的 dummy Step 不進全域 REGISTRY —— 一律以 registry= 參數顯式傳入
validate()，避免與並行開發中的 adept/core/steps/ 相互干擾。
"""
from __future__ import annotations

import json

import pytest

from adept.core.pipeline import (
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


# --------------------------------------------------------------------------- #
# 版本落差：新版存的 recipe 在舊版打開（兩台機器靠複製檔案同步，見 AGENTS.md）
# --------------------------------------------------------------------------- #
def test_a_saved_recipe_records_which_build_wrote_it():
    """沒有這個欄位的話，「認不得這個參數」就沒有線索可以判斷是檔案新還是程式舊。"""
    from adept import __version__

    rec = _mini_recipe() if "_mini_recipe" in globals() else None
    if rec is None:                     # 這一支測試檔的既有 helper 名稱不一定
        from adept.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec
        rec = Recipe(recipe_id="v", routes={"ebi_patch": ["a"]},
                     nodes={"a": RecipeNode("a", "load_patch", {})},
                     score=ScoreSpec(expr="1", threshold=0.0,
                                     bins={"below": 0, "above": 1}))
    assert rec.to_json_dict()["app_version"] == __version__


def test_an_older_build_says_the_program_is_old_not_the_file_broken():
    """使用者實際會看到的那句話。

    公司機是用複製檔案更新的，所以兩邊版本本來就會不同步。一份新版存的 recipe
    在舊版上打開，訊息若只有 ``unknown parameters: ['…']``，使用者的結論是
    「這份檔案壞了」—— 於是他會去重做一份 recipe，而該做的是更新程式。
    """
    from adept.core.pipeline.recipe import (Recipe, RecipeNode, ScoreSpec,
                                            validate, version_skew)

    rec = Recipe(
        recipe_id="future", routes={"ebi_patch": ["load", "x"]},
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "x": RecipeNode("x", "normalize",
                               {"streams": "test", "brand_new_knob": 3})},
        score=ScoreSpec(expr="1", threshold=0.0,
                        bins={"below": 0, "above": 1}),
        app_version="99.0.0")           # 「比較新的那一版」寫的

    import adept.core.steps  # noqa: F401 — 這一支要用真的卡片庫
    from adept.core.pipeline.step import REGISTRY

    detail = " ".join(i.detail for i in validate(rec, registry=REGISTRY)
                      if i.code == "bad-param")
    assert "brand_new_knob" in detail, "還是要指名是哪個參數"
    assert "99.0.0" in detail and "update ADEPT" in detail


def test_an_older_file_is_not_reported_as_skew():
    """檔案比較舊是**遷移**的事，不是版本落差 —— 不要對著它喊狼來了。"""
    from adept.core.pipeline.recipe import version_skew

    assert version_skew("0.0.1") == ""
    assert version_skew("") == ""            # 舊檔案根本沒有這個欄位
    assert "update ADEPT" in version_skew("99.0.0")


def test_an_unparseable_version_does_not_crash():
    """版本字串長什麼樣不歸我們管（別人手改過、或未來換了格式）。"""
    from adept.core.pipeline.recipe import version_skew

    for weird in ("beta", "v2-rc1", "…", None):
        version_skew(weird)                  # 不丟例外就好


def test_an_old_subtract_without_b_still_uses_the_aligned_ref():
    """subtract 的預設 b 於 2026-08-14 改成 ref。省略 b 的檔案是照舊預設
    （ref_aligned）蓋的 —— 載入遷移要把它寫回去，否則一份「align →
    subtract」的舊 recipe 會**安靜地跳過對位**，分數整批變掉。"""
    from adept.core.pipeline.recipe import Recipe

    d = {"recipe_id": "old", "version": 1,
         "routes": {"ebi_patch": ["load", "al", "sub"]},
         "nodes": {"load": {"step": "load_patch", "params": {}},
                   "al": {"step": "align", "params": {}},
                   "sub": {"step": "subtract", "params": {"op": "subtract"}}},
         "score": {"expr": "1", "threshold": 0.0,
                   "bins": {"below": 0, "above": 1}}}
    rec = Recipe.from_json_dict(d)
    assert rec.nodes["sub"].params["b"] == "ref_aligned"
    # 有寫 b 的檔案（新版 Studio 一律寫滿）原樣保留
    d["nodes"]["sub"]["params"]["b"] = "ref"
    assert Recipe.from_json_dict(d).nodes["sub"].params["b"] == "ref"


def test_a_recipe_round_trip_does_not_pick_up_the_old_subtract_default():
    """遷移只能對**檔案**做，不能對 round-trip 做。

    ``run_batch`` 把 recipe 序列化送進 worker、worker 再反序列化回來。這一道
    遷移以前的判準是「這個 dict 缺了 b」，於是那趟 round-trip 也被當成一份
    舊檔案：同一份 recipe 在 ``workers=1`` 是 ``b="ref"``（卡片預設）、在
    ``workers=4`` 變成 ``b="ref_aligned"`` —— 換一個 ``--workers`` 就換一組
    分數，而且兩邊都跑得完、都有數字。
    """
    from adept.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec

    r = Recipe(recipe_id="in-memory",
               routes={"ebi_patch": ["load", "sub"]},
               nodes={"load": RecipeNode("load", "load_patch", {}),
                      "sub": RecipeNode("sub", "subtract", {"a": "test"})},
               score=ScoreSpec("1", 0.0, {"below": 0, "above": 1}))
    assert "b" not in r.nodes["sub"].params

    worker_side = Recipe.from_json_dict(r.to_json_dict())
    assert "b" not in worker_side.nodes["sub"].params, (
        "round-trip 補了 b —— 平行批次會跟循序批次算出不一樣的分數")
