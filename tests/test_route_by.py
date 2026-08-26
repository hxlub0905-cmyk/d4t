# F23 期1：分流（route_by）—— 不同 CLASSNUMBER 走不同的卡片。
"""這一份鎖住分流的六條性質（`docs/history/plans/F23-route-by.md` §10 的驗收）：

1. **嚴格附加**（鐵則 9）：沒有 `route_by` 的 recipe 一個位元都不動 ——
   JSON 沒有那個鍵、round-trip 是 identity、features 裡沒有 `route_taken`。
2. **逐顆走對路**：值對上 map 走 map、對不上走 default、default 留空＝
   那一顆失敗（訊息講出值 X 不在對照表裡）。值先 strip 再比。
3. **B 路的顆真的沒跑 A 路的卡**：B 路的結果**沒有** A 路才有的特徵
   （證明是沒跑，不是跑了丟掉）。
4. **route_taken 每顆都在**（F19：自動做的決定要是一個畫得出分布的數字），
   而且只在 `route_by` 存在時出現。
5. **workers=1 與 workers=2 逐項相同**（鐵則 9 的分流版：route_by 要活著
   走過 to_json_dict → from_json_dict 進 worker）。
6. **快取冷跑＝熱跑**，而且**兩條 route 的簽章不同**（換 route 不會拿到
   隔壁那條路快取住的影像）。
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
    Recipe, RecipeError, RecipeNode, RouteBy, ScoreSpec, image_segment_signature,
    resolve_route, run_batch, run_batch_steps, run_defect, validate,
)

KIND = "ebi_patch"


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    """CLASSNUMBER 照 ground truth 填（REAL=1、NUISANCE=2）—— 分流的合成資料。"""
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("routeby")), n=8, seed=7,
                    class_by_truth=True)


@pytest.fixture()
def dataset(lot):
    """每條測試自己一份（run_batch 會就地填 `fields`，不能讓測試互相污染）。"""
    return load_dataset(lot["klarf"])


def _recipe(route_by=None, **extra_nodes):
    """兩條 route：A 量 glv_max、B 量 glv_mean —— 特徵名不同，才證得出
    「B 路的顆沒有 A 路的特徵」是真的沒跑。"""
    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        "glv_a": RecipeNode("glv_a", "glv_stats",
                            {"source": "test", "metrics": "glv_max"}),
        "glv_b": RecipeNode("glv_b", "glv_stats",
                            {"source": "test", "metrics": "glv_mean"}),
    }
    nodes.update(extra_nodes)
    return Recipe(
        recipe_id="t",
        routes={"a_route": ["load", "glv_a"], "b_route": ["load", "glv_b"]},
        nodes=nodes,
        score=ScoreSpec(expr="1.0", threshold=0.5, bins={"below": 0, "above": 1}),
        route_by=route_by)


def _rb(**over):
    kw = dict(column="CLASSNUMBER",
              map={"1": "a_route", "2": "b_route"}, default="")
    kw.update(over)
    return RouteBy(**kw)


def _plain_recipe():
    """沒有分流的對照組（單 route，kind 選路）。"""
    return Recipe(
        recipe_id="t", routes={KIND: ["load", "glv"]},
        nodes={
            "load": RecipeNode("load", "load_patch", {}),
            "glv": RecipeNode("glv", "glv_stats",
                              {"source": "test", "metrics": "glv_max"}),
        },
        score=ScoreSpec(expr="glv_max", threshold=1.0,
                        bins={"below": 0, "above": 1}))


def _truth(lot):
    import json
    with open(lot["ground_truth"], encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# 1. 嚴格附加（鐵則 9）
# --------------------------------------------------------------------------- #
def test_a_recipe_without_route_by_writes_no_such_key():
    d = _plain_recipe().to_json_dict()
    assert "route_by" not in d


def test_round_trip_is_identity_with_and_without_route_by():
    for recipe in (_plain_recipe(), _recipe(route_by=_rb(default="b_route"))):
        d1 = recipe.to_json_dict()
        d2 = Recipe.from_json_dict(d1).to_json_dict()
        assert d1 == d2


def test_route_by_survives_the_worker_serde_path():
    r2 = Recipe.from_json_dict(_recipe(route_by=_rb()).to_json_dict())
    assert r2.route_by == _rb()


def test_no_route_by_means_no_route_taken_feature(dataset):
    res = run_defect(_plain_recipe(), dataset.items[0], KIND)
    assert res.ok, res.error
    assert "route_taken" not in res.features


def test_broken_route_by_json_is_refused_at_read():
    base = _plain_recipe().to_json_dict()
    for bad in ("not a dict",
                {},                                   # 缺 column 與 map
                {"column": "CLASSNUMBER"},            # 缺 map
                {"column": "CLASSNUMBER", "map": ["1", "a"]}):  # map 不是物件
        d = dict(base)
        d["route_by"] = bad
        with pytest.raises(RecipeError):
            Recipe.from_json_dict(d)


# --------------------------------------------------------------------------- #
# 2. resolve_route 的語意
# --------------------------------------------------------------------------- #
class _Item:
    def __init__(self, fields):
        self.defect_id = "x"
        self.fields = fields


def test_resolve_route_without_route_by_is_just_the_kind():
    assert resolve_route(_plain_recipe(), _Item({}), KIND) == (KIND, "", "kind")


def test_resolve_route_map_hit_strips_the_value():
    recipe = _recipe(route_by=_rb())
    assert resolve_route(recipe, _Item({"CLASSNUMBER": " 1 "}), KIND) == \
        ("a_route", "1", "map")


def test_resolve_route_miss_goes_to_default_when_set():
    recipe = _recipe(route_by=_rb(default="b_route"))
    assert resolve_route(recipe, _Item({"CLASSNUMBER": "7"}), KIND) == \
        ("b_route", "7", "default")


def test_resolve_route_miss_without_default_is_none():
    recipe = _recipe(route_by=_rb())
    route, value, how = resolve_route(recipe, _Item({"CLASSNUMBER": "7"}), KIND)
    assert route is None and value == "7" and how == "miss"


def test_the_column_name_is_normalized_to_upper_case_on_read():
    d = _recipe(route_by=_rb()).to_json_dict()
    d["route_by"]["column"] = " classnumber "
    assert Recipe.from_json_dict(d).route_by.column == "CLASSNUMBER"


# --------------------------------------------------------------------------- #
# 3. lint
# --------------------------------------------------------------------------- #
def _codes(issues, level=None):
    return sorted(i.code for i in issues
                  if level is None or i.level == level)


def test_map_to_a_nonexistent_route_is_an_error():
    recipe = _recipe(route_by=_rb(map={"1": "no_such_route"}))
    assert "bad-route-by" in _codes(validate(recipe), "error")


def test_default_to_a_nonexistent_route_is_an_error():
    recipe = _recipe(route_by=_rb(default="no_such_route"))
    assert "bad-route-by" in _codes(validate(recipe), "error")


def test_an_empty_map_is_an_error():
    recipe = _recipe(route_by=_rb(map={}))
    assert "bad-route-by" in _codes(validate(recipe), "error")


def test_an_unreachable_route_is_a_warning():
    recipe = _recipe(route_by=_rb(map={"1": "a_route"}))   # b_route 沒人指到
    issues = validate(recipe)
    assert "route-not-reachable" in _codes(issues, "warning")
    assert _codes(issues, "error") == []


def test_a_clean_route_by_recipe_validates_even_with_the_dataset_kind():
    """route_by 覆蓋 kind 選路：kind 不在 routes 裡**不是**錯（F23 §4.2）。"""
    recipe = _recipe(route_by=_rb())
    issues = validate(recipe, kind=KIND)
    assert _codes(issues, "error") == [], [
        (i.code, i.detail) for i in issues if i.level == "error"]


def test_without_route_by_an_unknown_kind_is_still_an_error():
    """上一條放行的是 route_by；老路的 unknown-route 一個字都不能鬆。"""
    assert "unknown-route" in _codes(validate(_plain_recipe(), kind="rsem"),
                                     "error")


def test_two_routes_with_the_same_card_but_different_settings_get_a_note():
    """F23 §5 選項 A 的配套：`routes-drift` 是 warning（刻意不同正是分流的
    目的），detail 講**差在哪幾格**。"""
    recipe = _recipe(route_by=_rb())      # glv_a / glv_b：metrics 不同
    hits = [i for i in validate(recipe) if i.code == "routes-drift"]
    assert len(hits) == 1 and hits[0].level == "warning"
    assert "glv_max" in hits[0].detail and "glv_mean" in hits[0].detail


def test_identical_settings_across_routes_do_not_drift():
    recipe = _recipe(route_by=_rb())
    recipe.nodes["glv_b"] = RecipeNode("glv_b", "glv_stats",
                                       {"source": "test",
                                        "metrics": "glv_max"})
    assert not [i for i in validate(recipe) if i.code == "routes-drift"]


def test_only_the_wiring_differing_is_not_drift():
    """影像流參數不比（兩條 route 各接各的流本來就不同）。"""
    recipe = _recipe(route_by=_rb())
    recipe.nodes["glv_b"] = RecipeNode("glv_b", "glv_stats",
                                       {"source": "diff",
                                        "metrics": "glv_max"})
    assert not [i for i in validate(recipe) if i.code == "routes-drift"]


def test_without_route_by_multi_route_recipes_do_not_drift():
    """kind 選路的多 route（ebi_patch/rsem）兩條路不同設定是常態，不是漂。"""
    recipe = _recipe(route_by=None)
    assert not [i for i in validate(recipe) if i.code == "routes-drift"]


# --------------------------------------------------------------------------- #
# 4. 逐顆走對路（引擎，run_batch 自動補欄）
# --------------------------------------------------------------------------- #
def test_every_defect_takes_the_route_its_class_says(lot, dataset):
    recipe = _recipe(route_by=_rb())
    rows = run_batch(recipe, dataset, workers=1)
    truth = _truth(lot)
    assert len(rows) == 8
    for r in rows:
        assert r["ok"], (r["defect_id"], r["error"])
        is_real = truth[r["defect_id"]]["is_real"]
        if is_real:                       # CLASSNUMBER=1 → a_route → glv_max
            assert "glv_max" in r["features"]
            assert "glv_mean" not in r["features"], \
                "B 路的卡在 A 路的顆上跑了"
        else:                             # CLASSNUMBER=2 → b_route → glv_mean
            assert "glv_mean" in r["features"]
            assert "glv_max" not in r["features"], \
                "A 路的卡在 B 路的顆上跑了"


def test_route_taken_is_always_written_and_plots_as_a_number(lot, dataset):
    recipe = _recipe(route_by=_rb())
    rows = run_batch(recipe, dataset, workers=1)
    truth = _truth(lot)
    keys = sorted(recipe.routes)          # ["a_route", "b_route"]
    for r in rows:
        assert "route_taken" in r["features"]
        want = keys.index("a_route" if truth[r["defect_id"]]["is_real"]
                          else "b_route")
        assert r["features"]["route_taken"] == float(want)


def test_hand_set_fields_win_over_the_klarf_column(dataset):
    """每一顆都已經有這一欄 → run_batch 一個位元都不動（測試靠這個手排路線）。"""
    for item in dataset.items:
        item.fields = {"CLASSNUMBER": "9"}
    recipe = _recipe(route_by=_rb(map={"9": "b_route"}))
    rows = run_batch(recipe, dataset, workers=1)
    assert all(r["ok"] for r in rows)
    assert all("glv_mean" in r["features"] for r in rows)


def test_unmapped_values_fall_into_the_default_route(dataset):
    for item in dataset.items:
        item.fields = {"CLASSNUMBER": "7"}
    recipe = _recipe(route_by=_rb(default="b_route"))
    rows = run_batch(recipe, dataset, workers=1)
    assert all(r["ok"] for r in rows)
    assert all("glv_mean" in r["features"] for r in rows)


def test_unmapped_values_without_a_default_fail_that_defect_with_a_reason(
        dataset):
    for item in dataset.items:
        item.fields = {"CLASSNUMBER": "7"}
    recipe = _recipe(route_by=_rb())
    rows = run_batch(recipe, dataset, workers=1)
    for r in rows:
        assert not r["ok"]
        assert "CLASSNUMBER" in r["error"] and "'7'" in r["error"], r["error"]


# --------------------------------------------------------------------------- #
# 5. workers=1 與 workers=2 逐項相同（鐵則 9 的分流版）
# --------------------------------------------------------------------------- #
def _canon(rows):
    """traces 帶著牆鐘時間（ms），逐項比對要去掉它 —— 其餘全部要相同。"""
    keys = ("defect_id", "ok", "error", "features", "score", "bin")
    return [{k: r.get(k) for k in keys} for r in rows]


def test_workers_1_and_2_agree_item_by_item(lot):
    recipe = _recipe(route_by=_rb())
    r1 = run_batch(recipe, load_dataset(lot["klarf"]), workers=1)
    r2 = run_batch(recipe, load_dataset(lot["klarf"]), workers=2)
    assert _canon(r1) == _canon(r2)


# --------------------------------------------------------------------------- #
# 6. 快取：冷跑＝熱跑；兩條 route 的簽章不同
# --------------------------------------------------------------------------- #
def test_cold_and_warm_cache_runs_agree(lot, tmp_path):
    recipe = _recipe(route_by=_rb())
    cache = str(tmp_path / "cache")
    cold = run_batch(recipe, load_dataset(lot["klarf"]), workers=1,
                     cache_dir=cache)
    warm = run_batch(recipe, load_dataset(lot["klarf"]), workers=1,
                     cache_dir=cache)
    assert _canon(cold) == _canon(warm)
    assert all(r["ok"] for r in cold)


def test_the_two_routes_have_different_cache_signatures():
    recipe = _recipe(route_by=_rb())
    assert image_segment_signature(recipe, "a_route") != \
        image_segment_signature(recipe, "b_route")


# --------------------------------------------------------------------------- #
# 7. 跨顆那一層：route_by 存在時每條 route 的 Output 卡都跑、共用的只跑一次
# --------------------------------------------------------------------------- #
def test_a_shared_output_card_runs_exactly_once_across_routes(dataset,
                                                              tmp_path):
    out_dir = tmp_path / "out"
    recipe = _recipe(route_by=_rb(),
                     out=RecipeNode("out", "output_report",
                                    {"folder": str(out_dir),
                                     "contents": "table"}))
    recipe.routes = {"a_route": ["load", "glv_a", "out"],
                     "b_route": ["load", "glv_b", "out"]}
    rows = run_batch(recipe, dataset, workers=1)
    bctx = run_batch_steps(recipe, dataset, rows)
    assert bctx.errors == {}, bctx.errors
    assert bctx.outputs == [str(out_dir)], "共用的 Output 卡要正好跑一次"
    # 寫兩次不是「再保險一次」，是覆寫 —— 所以要看**內容**：一份表列完
    # 兩條 route 的每一顆，正好一次。
    lines = (out_dir / "defects.csv").read_text(
        encoding="utf-8-sig").splitlines()
    assert len(lines) == len(rows) + 1


def test_each_routes_own_output_card_runs(dataset, tmp_path):
    pa, pb = tmp_path / "a", tmp_path / "b"
    recipe = _recipe(route_by=_rb(),
                     out_a=RecipeNode("out_a", "output_report",
                                      {"folder": str(pa),
                                       "contents": "table"}),
                     out_b=RecipeNode("out_b", "output_report",
                                      {"folder": str(pb),
                                       "contents": "table"}))
    recipe.routes = {"a_route": ["load", "glv_a", "out_a"],
                     "b_route": ["load", "glv_b", "out_b"]}
    rows = run_batch(recipe, dataset, workers=1)
    bctx = run_batch_steps(recipe, dataset, rows)
    assert bctx.errors == {}, bctx.errors
    assert sorted(bctx.outputs) == sorted([str(pa), str(pb)])


# --------------------------------------------------------------------------- #
# 8. 合成資料：class_by_truth 是選配，預設一個位元組都沒變
# --------------------------------------------------------------------------- #
def test_class_by_truth_is_opt_in(tmp_path, lot):
    from make_sample import generate
    plain = generate(str(tmp_path / "plain"), n=8, seed=7)
    with open(plain["klarf"], encoding="utf-8") as f:
        assert " 0 2 " in f.read()        # CLASSNUMBER 仍是 0（IMAGECOUNT 2）
    truth = _truth(lot)
    ds = load_dataset(lot["klarf"])
    for item in ds.items:
        want = "1" if truth[item.defect_id]["is_real"] else "2"
        assert item.tags.get("classnumber") == want
