"""M1 驗收：Recipe JSON serde、execution_order、lint 式 validate。

本檔的 dummy Step 不進全域 REGISTRY —— 一律以 registry= 參數顯式傳入
validate()，避免與並行開發中的 d4t/core/steps/ 相互干擾。
"""
from __future__ import annotations

import json

import pytest

from d4t.core.pipeline import (
    Edge,
    CATEGORY_ALGO,
    CATEGORY_IMAGE,
    ParamSpec,
    Recipe,
    RecipeError,
    RecipeNode,
    RECIPE_VERSION,
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
        version=RECIPE_VERSION,
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
    r = make_recipe(edges=[Edge("load", "snr")])
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
    # 沒寫 ``version`` = 舊檔案（F42 B3 之前的每一份都是），所以它會走一次
    # 區域遷移，然後被標成**現在這一版** —— 不然每一次送進 worker 都會再遷移
    # 一次，而遷移改了版本號，那一對就不再是 identity（鐵則 9）。
    assert r.version == RECIPE_VERSION
    assert r.author == ""
    assert r.description == ""
    assert r.edges == []
    assert r.nodes["load"].enabled is True
    assert r.nodes["load"].params == {}
    assert r.nodes["load"].id == "load"


def test_json_missing_required_field():
    with pytest.raises(RecipeError):
        Recipe.from_json_dict({"recipe_id": "x"})


def test_load_reads_utf8_json(tmp_path):
    """從磁碟讀一份 recipe。

    ⚠ 這裡**刻意自己寫檔案**而不是用 ``Recipe.save``（2026-08-26 回來了）——
    要驗的是「讀得懂磁碟上的 JSON」，用 save 寫的話這一支就只證明了自己跟
    自己相容。存檔那一半在 `tests/test_recipe_save.py`。
    """
    r = make_recipe()
    p = tmp_path / "recipe.json"
    p.write_text(json.dumps(r.to_json_dict(), ensure_ascii=False, indent=2),
                 encoding="utf-8")
    r2 = Recipe.load(p)
    assert r2 == r
    assert "單元測試" in p.read_text(encoding="utf-8")   # utf-8 中文不會壞


def test_a_json_round_trip_changes_nothing():
    """``to_json_dict`` → ``from_json_dict`` 必須是 identity。

    這不是「序列化好棒棒」那種形式測試 —— **``run_batch`` 就是用這一對把
    recipe 送進 worker 行程的**。它一旦不是 identity，同一份 recipe 在
    ``workers=1`` 與 ``workers=2`` 下就會算出不同的答案，而兩邊都跑得完、
    都有數字。

    真的發生過（2026-08-14 到 2026-08-16）：有一道遷移看到 subtract 沒寫 ``b``
    就補上 ``ref_aligned``，於是記憶體裡的 recipe 比 ``test - ref``、
    繞過 JSON 的那份比 ``test - ref_aligned``，glv_max 50 vs 43。
    遷移只能靠「舊東西在不在」判斷，不能靠「新東西不在」——
    後者分不出「舊檔案」與「新 recipe 用新預設」。
    """
    r = make_recipe()
    again = Recipe.from_json_dict(json.loads(json.dumps(r.to_json_dict())))
    assert again == r
    for nid, node in r.nodes.items():
        assert again.nodes[nid].params == node.params, nid


def test_a_subtract_without_an_explicit_b_keeps_the_card_default():
    """省略參數 = 用卡片當下的預設，讀檔不可以幫它填一個別的值。"""
    d = {
        "recipe_id": "omit",
        "routes": {"ebi_patch": ["load", "sub"]},
        "nodes": {"load": {"step": "load_patch", "params": {}},
                  "sub": {"step": "subtract", "params": {}}},
        "score": {"expr": "1", "threshold": 0.0},
    }
    r = Recipe.from_json_dict(d)
    assert r.nodes["sub"].params == {}, "讀檔不該無中生有塞參數進去"


# ---------------------------------------------------------------------------
# Edge —— 線帶埠（F9-1）
# ---------------------------------------------------------------------------
def test_an_old_two_item_edge_still_loads():
    """F9 之前的 ``[src, dst]`` 要讀得進來，埠留空 = 還沒指定。

    判斷依據是「**長度就是 2**」—— 舊東西**在**，不是新東西不在（鐵則 9）。
    """
    d = {
        "recipe_id": "old_edges",
        "routes": {"ebi_patch": ["load", "sub", "snr"]},
        "nodes": {"load": {"step": "t_load_pair"}, "sub": {"step": "t_subtract"},
                  "snr": {"step": "t_snr"}},
        "edges": [["load", "snr"]],
        "score": {"expr": "1", "threshold": 0.5, "bins": {"below": 0, "above": 1}},
    }
    r = Recipe.from_json_dict(d)
    assert r.edges == [Edge(src="load", dst="snr", src_out="", dst_in="")]
    # 讀進來之後寫出去就是新格式，而**執行順序沒有變**
    assert r.to_json_dict()["edges"] == [["load", "", "snr", ""]]
    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]


def test_an_edge_with_ports_round_trips():
    r = make_recipe(edges=[Edge("load", "sub", src_out="ref", dst_in="b")])
    d = r.to_json_dict()
    assert d["edges"] == [["load", "ref", "sub", "b"]]
    assert Recipe.from_json_dict(d) == r
    assert Recipe.from_json_dict(d).to_json_dict() == d


def test_an_edge_of_the_wrong_shape_is_refused_loudly():
    """三個欄位的邊沒有意義 —— 與其猜，不如當場講出格式。"""
    for bad in ([["a"]], [["a", "b", "c"]], [["a", "b", "c", "d", "e"]]):
        d = {
            "recipe_id": "bad_edge",
            "routes": {"ebi_patch": ["load"]},
            "nodes": {"load": {"step": "t_load_pair"}},
            "edges": bad,
            "score": {"expr": "1", "threshold": 0.5, "bins": {"below": 0, "above": 1}},
        }
        with pytest.raises(RecipeError):
            Recipe.from_json_dict(d)


def test_ports_do_not_change_the_execution_order_yet():
    """F9-1 換的是**形狀**不是語意：埠填了什麼都不影響誰先跑。

    這條是 F9-1 的驗收條件本身 —— 這一段如果動到執行順序，
    ``tools/freeze_golden.py --check`` 就會整批不同，而那才是真正的災難
    （跑得動、但答案悄悄變了）。埠要到 F9-2 才開始有作用。
    """
    plain = make_recipe(edges=[Edge("load", "snr")])
    ported = make_recipe(edges=[Edge("load", "snr", src_out="ref", dst_in="b")])
    assert execution_order(plain, "ebi_patch") == execution_order(ported, "ebi_patch")


# ---------------------------------------------------------------------------
# execution_order
# ---------------------------------------------------------------------------
def test_execution_order_chain():
    r = make_recipe()
    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]


def test_execution_order_extra_edge_consistent():
    # 額外邊與鏈一致 → 順序不變
    r = make_recipe(edges=[Edge("load", "snr")])
    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]


def test_execution_order_edge_outside_route_ignored():
    # 邊的端點不在該 route 內 → 不影響
    r = make_recipe(edges=[Edge("ghost", "snr"), Edge("load", "ghost")])
    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]


def test_execution_order_cycle_raises():
    """真的循環：兩條線互指。

    F17-① 之前這一條寫的是**一條**往回的線（`snr → load`），而它之所以是
    循環，靠的是 route 相鄰對那串隱含邊。隱含邊拿掉之後，一條往回的線只是
    「這兩張卡的順序跟排版相反」—— 那是合法的（見下一條）。
    """
    r = make_recipe(edges=[Edge("snr", "load"), Edge("load", "snr")])
    with pytest.raises(RecipeError):
        execution_order(r, "ebi_patch")


def test_one_backward_line_is_not_a_cycle_any_more(): 
    """**F17-① 唯一的行為改變**：線與 route 排列相反的 recipe。

    以前它是 `cycle` 錯誤 —— 一份完全合理的 pipeline 因為卡片在畫布上的左右
    位置而開不起來。現在**線說了算**，排版只在沒有線的時候當平手依據。
    """
    r = make_recipe(edges=[Edge("snr", "load")])
    order = execution_order(r, "ebi_patch")
    assert order.index("snr") < order.index("load")


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
    # 真的循環要兩條線互指（F17-①：一條往回的線不再是循環）。
    r = make_recipe(edges=[Edge("snr", "load"), Edge("load", "snr")])
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


def test_entry_card_reads_unchecked_but_a_consumer_is_checked_wherever_it_sits():
    """**入口是「不吃影像流的卡」，不是「排第一個的卡」**（F11 Input-0）。

    以前這一條叫 `test_validate_first_node_reads_unchecked`，斷言的是位置：
    route 上第一張卡的 reads 不檢查。那是線性 route 時代的定義，而它讓
    **一份 recipe 只能有一個 image source**（見 `Step.is_source` 的說明）。

    改成看宣告之後，兩個方向都要成立：入口卡（沒有輸入埠也沒有 reads）的
    reads 不檢查；而一張**會吃影像流**的卡排在第一個也照樣被檢查 ——
    只有一張 subtract 的 recipe 真的沒有影像來源，那句話該講出來。
    """
    only_a_consumer = make_recipe(
        routes={"ebi_patch": ["sub"]},
        nodes={"sub": RecipeNode("sub", "t_subtract", {})},
        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}))
    assert "missing-image" in codes(validate(only_a_consumer, registry=REG))

    with_an_entry = make_recipe(
        routes={"ebi_patch": ["load", "sub"]},
        nodes={"load": RecipeNode("load", "t_load_pair", {}),
               "sub": RecipeNode("sub", "t_subtract", {})},
        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}))
    assert "missing-image" not in codes(validate(with_an_entry, registry=REG))


# ---------------------------------------------------------------------------
# 多個 image source 入口（F11 Input-0）
# ---------------------------------------------------------------------------
class TLoadSidecar(Step):
    """第二個入口：與 defect 一一對應的外部檔案（GLAS 的 label map 那種）。"""
    key = "t_load_sidecar"
    label = "測試載入（sidecar）"
    category = CATEGORY_IMAGE
    help = "測試用：寫入 layout_label 影像流（不吃任何影像流）"
    writes = ["layout_label"]

    def run(self, ctx, params):
        return ctx


class TMaskConsumer(Step):
    key = "t_mask_consumer"
    label = "測試吃 mask"
    category = CATEGORY_ALGO
    help = "測試用：吃 layout_label 與 diff，量一個數字"
    reads = ["layout_label", "diff"]
    features_out = ["masked_mean"]

    def run(self, ctx, params):
        return ctx


REG2 = dict(REG, t_load_sidecar=TLoadSidecar, t_mask_consumer=TMaskConsumer)


def _two_entry_recipe(**kw):
    """patch 的頁 + sidecar 兩個入口，會合到一張吃 mask 的量測卡。"""
    base = dict(
        recipe_id="two_entries",
        routes={"ebi_patch": ["load", "mask_src", "sub", "measure"]},
        nodes={
            "load": RecipeNode("load", "t_load_pair", {}),
            "mask_src": RecipeNode("mask_src", "t_load_sidecar", {}),
            "sub": RecipeNode("sub", "t_subtract", {}),
            "measure": RecipeNode("measure", "t_mask_consumer", {}),
        },
        score=ScoreSpec(expr="masked_mean", threshold=1.0,
                        bins={"below": 0, "above": 1}),
        version=RECIPE_VERSION, author="unit", description="兩個入口", edges=[],
    )
    base.update(kw)
    return Recipe(**base)


def test_a_recipe_can_have_two_image_source_entries():
    """兩個入口的 recipe：兩張的 writes 都算進來，lint 一句話都不說。

    以前第二張入口卡會被當成普通卡：它沒有輸入埠所以躲過 not-connected，
    但它的 writes 只拿得到非 kind-aware 的宣告 —— 於是下游那張吃
    `layout_label` 的卡會收到一句**假的** missing-image。
    """
    issues = validate(_two_entry_recipe(), registry=REG2)
    assert codes(issues) == [], [(i.code, i.title, i.detail) for i in issues]


def test_the_second_entry_is_an_entry_even_when_it_sits_last():
    """入口是宣告出來的事，不是位置 —— 把 sidecar 那張排到最後也一樣。

    排最後只是「畫布上的順序」；它照樣不吃任何影像流，所以照樣是入口。
    （吃它的那張卡在它前面，所以那一張會缺圖 —— 那是**順序**的問題，
    lint 講的也正是那一句，不是「這張卡沒有來源」。）
    """
    r = _two_entry_recipe(
        routes={"ebi_patch": ["load", "sub", "measure", "mask_src"]})
    issues = validate(r, registry=REG2)
    assert [i.code for i in issues] == ["missing-image"]
    bad = issues[0]
    assert bad.node_id == "measure" and "layout_label" in bad.detail


def test_is_source_looks_at_declarations_not_at_position_or_values():
    """`Step.is_source` 的三條判準各自被驗到（F11 Input-0）。"""
    assert TLoadPair.is_source() and TLoadSidecar.is_source()
    # 有 reads 但沒有輸入埠的舊風格卡 **不是**入口 —— 只看埠的話
    # missing-image 整條檢查會安靜失效。
    assert not TSubtract.is_source()
    assert not TMaskConsumer.is_source()
    # 真的卡片：只有 load_patch 是入口。
    from d4t.core.pipeline.step import REGISTRY
    import d4t.core.steps            # noqa: F401  (註冊全部卡片)
    sources = sorted(k for k, c in REGISTRY.items() if c.is_source())
    # 三張 Input 卡（F11 Input-4：一種 source 一張卡）——其餘的卡都吃影像流。
    # `load_sidecar`（F11 Region-3）也是 source：它的輸入不是影像流，是 ingest
    # 掛在 `DefectItem.sidecars` 上的附加檔，所以畫布上它沒有輸入埠。
    # `pair_source`（F15）同理：它的輸入是**另一份掛上來的 lot**，不是流。
    assert sources == ["load_patch", "load_sidecar", "load_single",
                       "pair_source"], sources


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
    from d4t import __version__

    rec = _mini_recipe() if "_mini_recipe" in globals() else None
    if rec is None:                     # 這一支測試檔的既有 helper 名稱不一定
        from d4t.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec
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
    from d4t.core.pipeline.recipe import (Recipe, RecipeNode, ScoreSpec,
                                            validate, version_skew)

    rec = Recipe(
        recipe_id="future", routes={"ebi_patch": ["load", "x"]},
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "x": RecipeNode("x", "normalize",
                               {"streams": "test", "brand_new_knob": 3})},
        score=ScoreSpec(expr="1", threshold=0.0,
                        bins={"below": 0, "above": 1}),
        app_version="99.0.0")           # 「比較新的那一版」寫的

    import d4t.core.steps  # noqa: F401 — 這一支要用真的卡片庫
    from d4t.core.pipeline.step import REGISTRY

    detail = " ".join(i.detail for i in validate(rec, registry=REGISTRY)
                      if i.code == "bad-param")
    assert "brand_new_knob" in detail, "還是要指名是哪個參數"
    assert "99.0.0" in detail and "update d4t" in detail


def test_an_older_file_is_not_reported_as_skew():
    """檔案比較舊是**遷移**的事，不是版本落差 —— 不要對著它喊狼來了。"""
    from d4t.core.pipeline.recipe import version_skew

    assert version_skew("0.0.1") == ""
    assert version_skew("") == ""            # 舊檔案根本沒有這個欄位
    assert "update d4t" in version_skew("99.0.0")


def test_an_unparseable_version_does_not_crash():
    """版本字串長什麼樣不歸我們管（別人手改過、或未來換了格式）。"""
    from d4t.core.pipeline.recipe import version_skew

    for weird in ("beta", "v2-rc1", "…", None):
        version_skew(weird)                  # 不丟例外就好


def test_reading_a_recipe_never_invents_a_parameter():
    """讀檔**不可以**幫任何一張卡填一個檔案裡沒有的參數值。

    這條測試取代 ``test_an_old_subtract_without_b_still_uses_the_aligned_ref``
    （2026-08-14 → 2026-08-16）。那道遷移的用意是保住舊檔行為：subtract 的預設
    從 ``ref_aligned`` 改成 ``ref``，所以「檔案裡沒寫 b」就補回 ``ref_aligned``。

    用意對，判斷依據錯 —— 它靠的是**新 key 缺席**，而「舊檔案靠舊預設」跟
    「新 recipe 靠新預設」從缺一個 key 分不出來。實際後果：
    ``to_json_dict`` → ``from_json_dict`` 不再是 identity，而 ``run_batch``
    正是用這一對把 recipe 送進 worker，於是 ``workers=1`` 與 ``workers=2``
    算出不同的分數（glv_max 50 vs 43），兩邊都跑得完、都有數字。

    見 ``test_a_json_round_trip_changes_nothing`` 與 ``from_json_dict`` 裡的
    「遷移的鐵則」那段註解。
    """
    from d4t.core.pipeline.recipe import Recipe

    d = {"recipe_id": "old", "version": 1,
         "routes": {"ebi_patch": ["load", "al", "sub"]},
         "nodes": {"load": {"step": "load_patch", "params": {}},
                   "al": {"step": "align", "params": {}},
                   "sub": {"step": "subtract", "params": {"op": "subtract"}}},
         "score": {"expr": "1", "threshold": 0.0,
                   "bins": {"below": 0, "above": 1}}}
    rec = Recipe.from_json_dict(d)
    assert rec.nodes["sub"].params == {"op": "subtract"}, \
        "檔案裡只寫了 op，讀完就該只有 op"
    # 有寫 b 的檔案原樣保留
    d["nodes"]["sub"]["params"]["b"] = "ref"
    assert Recipe.from_json_dict(d).nodes["sub"].params["b"] == "ref"


# --------------------------------------------------------------------------- #
# F37：改名遷移要走完四條路（2026-08-26）
# --------------------------------------------------------------------------- #
def _old_style_recipe(tmp_path):
    """一份**舊名字**的 recipe，四個地方各引用一次。"""
    import json

    d = {
        "recipe_id": "f37_migration",
        "version": 1,
        "routes": {"ebi_patch": ["load", "roi", "glv", "img", "bp"]},
        "nodes": {
            "load": {"step": "load_patch", "params": {}},
            "roi": {"step": "roi_reference",
                    "params": {"method": "stripes in the image",
                               "source": "test", "roi_out": "band"}},
            "glv": {"step": "glv_stats",
                    "params": {"source": "test", "roi": "band",
                               "metrics": "glv_median",
                               "across_boxes": "each box"}},
            # ③ Output 卡的參數值 —— 這一條以前**沒有人走**
            "img": {"step": "output_image",
                    "params": {"folder": "/tmp/f37", "limit": 5,
                               "rank_by": "worst_score"}},
            "bp": {"step": "output_boxplot",
                   "params": {"path": "/tmp/f37.html",
                              "features": "worst_score, cd_median, score_median"}},
        },
        # ① 分數表達式
        "score": {"expr": "worst_score * 2 + score_spread",
                  "bins": {"below": 0, "above": 1}, "threshold": 1.0},
        # ② 判定樹
        "decide": {"tree": {"when": "worst_value > 3",
                            "yes": {"bin": 1, "name": "hot"},
                            "no": {"bin": 0, "name": "ok"}}},
    }
    path = tmp_path / "old.json"
    path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return path


def test_renaming_a_feature_moves_every_place_that_refers_to_it(tmp_path):
    """F37：``worst_*`` → ``glv_worst_*`` 的遷移要走完每一條路。

    以前只有分數表達式與判定段（曾經還有 `feature_math` 的算式，而那張卡
    2026-08-27 刪了）。**參數值**那一條沒有人走，而漏掉它的症狀特別壞，
    因為**它跑得完**：
    `rank_by` 指到一個不存在的數字時，出圖卡排不出順序就安靜地退回檔案順序，
    於是使用者拿到 N 張正常的圖，而「最值得看的那 N 顆」完全沒有發生
    （F30 修過一次的那個 bug，只是這次的來源是遷移）。

    ⚠ **把 `from_json_dict` 裡的 `_rename_in_node_params(nodes, renames)`
    那一行拿掉，這支測試會紅。**
    """
    rc = Recipe.load(str(_old_style_recipe(tmp_path)))

    # ① 分數表達式
    assert rc.score.expr == "glv_worst_score * 2 + glv_worst_score_spread"
    # ② 判定樹
    assert rc.decide.tree.when == "glv_worst_value > 3"
    # ③ 單獨一格特徵名（`feature_key`）
    assert rc.nodes["img"].params["rank_by"] == "glv_worst_score"
    # ④ 一串特徵名（`feature_keys`）—— 沒改到的那一項連空白都不該動
    #
    # ⚠ 那一格在 F38 改名了（`features` → `plot_features`，因為它跟併進來的
    # `include_features` 在同一張卡上）。**改名跟這支測試守的事是兩件** ——
    # 這裡問的仍然是「特徵名有沒有換到」，只是要去新的那一格問。
    assert (rc.nodes["bp"].params["plot_features"]
            == "glv_worst_score, cd_median, glv_worst_score_median")


def test_the_rename_is_idempotent_so_round_trip_is_still_identity(tmp_path):
    """遷移的判準是「舊東西在不在」（鐵則 9），所以第二次跑必須是 no-op。

    不是這樣的話 ``to_json_dict → from_json_dict`` 就不是 identity，而那條路
    正是 `run_batch` 送 recipe 進 worker 走的 —— ``workers=1`` 與 ``workers=2``
    會算出不同的分數。真的發生過（見這個檔案上面那一段）。
    """
    rc = Recipe.load(str(_old_style_recipe(tmp_path)))
    once = rc.to_json_dict()
    twice = Recipe.from_json_dict(once).to_json_dict()
    assert once == twice


def test_a_sentinel_that_is_not_a_feature_name_is_left_alone(tmp_path):
    """``rank_by`` 的預設值 ``score`` 是**哨兵**，不是特徵名 —— 不准被改寫。

    這正是那一格用「整格比對」而不是識別字比對的理由：`_renamed_idents` 會在
    任何字串裡找識別字，而哨兵值長得就像一個名字。
    """
    import json

    path = _old_style_recipe(tmp_path)
    d = json.loads(path.read_text(encoding="utf-8"))
    d["nodes"]["img"]["params"]["rank_by"] = "score"
    path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    rc = Recipe.load(str(path))
    assert rc.nodes["img"].params["rank_by"] == "score"
