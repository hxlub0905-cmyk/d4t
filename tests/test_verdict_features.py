# PR-1：判定用到哪些特徵（`core/pipeline/verdict_features.py`）。
"""結果表分層的資料來源。四個邊界各一條（工作單 1a），加上「診斷宣告 ⊆ 真的
產出」的 registry 全掃 —— 逐張列舉的測試會在加第 18 張卡的那天安靜地留下一個
沒被測到的角落，所以照 `test_ui_canvas_invariants` 的規矩掃整個 REGISTRY。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from d4t.core.pipeline import get_step
from d4t.core.pipeline.recipe import (
    DecideSpec, Edge, Let, Recipe, RecipeNode, Rule, ScoreSpec,
)
from d4t.core.pipeline.step import REGISTRY
from d4t.core.pipeline.verdict_features import (
    ENGINE_LABEL, bound_specs, diagnostic_alarm_map, diagnostic_columns,
    features_in_verdict,
)
import d4t.core.steps  # noqa: F401 - 註冊卡片


def _recipe(nodes, kind="ebi_patch", score="0", decide=None, edges=()):
    return Recipe(
        recipe_id="vf_test",
        routes={kind: [n[0] for n in nodes]},
        nodes={n[0]: RecipeNode(n[0], n[1], dict(n[2]),
                                enabled=(len(n) < 4 or n[3]))
               for n in nodes},
        score=ScoreSpec(expr=score, threshold=0.0,
                        bins={"below": 0, "above": 1}),
        version=2, author="unit", description="vf",
        decide=decide, edges=[Edge(*e) for e in edges])


LOAD = ("load", "load_patch", {})


# --------------------------------------------------------------------------- #
# 1a 的四條邊界
# --------------------------------------------------------------------------- #
def test_a_name_nobody_produces_is_still_in_the_set():
    """判定引用了一個沒人產出的名字 → 照樣入集合。

    一個看得到的空欄比默默消失好：打錯的名字就是使用者要看見的錯。
    """
    r = _recipe([LOAD], decide=DecideSpec(
        rules=[Rule(when="nosuch > 1", bin=1, label="odd")]))
    assert "nosuch" in features_in_verdict(r, "ebi_patch")


def test_score_only_recipe_uses_the_expression_variables():
    r = _recipe([LOAD], score="glv_median + 2 * cd_n")
    got = features_in_verdict(r, "ebi_patch")
    assert set(got) >= {"glv_median", "cd_n"}
    # 沒有 decide 的 recipe 不會憑空長出判定樹的名字
    assert "nosuch" not in got


def test_let_names_are_expanded_not_listed():
    """let 中間名不是欄位 —— 展開成底層特徵，巢狀也一樣。"""
    r = _recipe([LOAD], decide=DecideSpec(
        let=[Let(name="bright", expr="glv_median + glv_mad"),
             Let(name="odd", expr="bright * cd_n")],
        rules=[Rule(when="odd > 3", bin=1, label="odd")]))
    got = features_in_verdict(r, "ebi_patch")
    assert {"glv_median", "glv_mad", "cd_n"} <= set(got)
    for name in ("bright", "odd", "bright_missing", "odd_raw"):
        assert name not in got, "%s 是 let 的中間名，不是欄位" % name


def test_disabled_cards_do_not_contribute():
    out = ("rep", "output_report", {"rank_by": "cd_median"})
    on = _recipe([LOAD, out])
    off = _recipe([LOAD, out + (False,)])
    assert "cd_median" in features_in_verdict(on, "ebi_patch")
    assert "cd_median" not in features_in_verdict(off, "ebi_patch")


def test_computed_per_route():
    """route 各自算：Output 卡只在其中一條 route 上。"""
    r = _recipe([LOAD, ("rep", "output_report", {"rank_by": "cd_median"})])
    r.routes["rsem"] = ["load"]
    assert "cd_median" in features_in_verdict(r, "ebi_patch")
    assert "cd_median" not in features_in_verdict(r, "rsem")


def test_the_order_is_the_order_of_reference():
    """1b 的欄序就是引用順序 —— 樹先問的排前面。"""
    r = _recipe([LOAD], decide=DecideSpec(
        rules=[Rule(when="cd_n > 1", bin=1, label="a"),
               Rule(when="glv_median > 9", bin=2, label="b")]))
    got = features_in_verdict(r, "ebi_patch")
    assert got.index("cd_n") < got.index("glv_median")


# --------------------------------------------------------------------------- #
# 診斷宣告的鐵測試（registry 全掃 + 反空洞）
# --------------------------------------------------------------------------- #
#: 預設值之外還要掃的參數組 —— 宣告是條件式的（`min_pixels` / `across_boxes`
#: / `shape`），只掃預設值等於沒掃那幾個分支。
VARIANTS = [
    ("glv_stats", {"source": "test", "min_pixels": 10}),
    ("glv_stats", {"source": "test", "across_boxes": "each box"}),
    ("glv_stats", {"source": "test", "min_pixels": 5,
                   "across_boxes": "each box", "roi": "epi,mg"}),
    ("cd_measure", {"source": "test", "shape": "blob"}),
    ("cd_measure", {"source": "a,b", "output_prefix": "x"}),
]


def _cases():
    for key in REGISTRY:
        yield key, None
    for key, params in VARIANTS:
        yield key, params


@pytest.mark.parametrize(("key", "params"), list(_cases()),
                         ids=["%s-%s" % (k, "default" if p is None else "variant")
                              for k, p in _cases()])
def test_diagnostics_are_a_subset_of_what_each_card_produces(key, params):
    """每張卡、每組代表參數：diagnostics ⊆ resolve_features、
    alarm 名 ⊆ diagnostics —— 宣告出來的名字必須真的會產出。"""
    cls = REGISTRY[key]
    p = cls.validate_params(params)
    produced = set(cls.resolve_features(p))
    diag = set(cls.diagnostic_features(p))
    alarms = cls.diagnostic_alarms(p)
    assert diag <= produced, \
        "%s 宣告了不會產出的診斷：%s" % (key, sorted(diag - produced))
    assert {n for n, _ in alarms} <= diag, \
        "%s 的警示名不在診斷宣告裡：%s" % (
            key, sorted({n for n, _ in alarms} - diag))
    for _, bad in alarms:
        assert isinstance(bad, bool)


def test_somebody_actually_declares_diagnostics():
    """反空洞：上面那條不是因為大家都宣告空集合而恆綠。"""
    glv = get_step("glv_stats")
    assert glv.diagnostic_features({"source": "test"}) != []
    assert glv.diagnostic_alarms(
        glv.validate_params({"source": "test", "min_pixels": 10})
    ) == [("glv_ok", False)], "glv_ok 的極性是「0 = 不能信」"
    cd = get_step("cd_measure")
    assert cd.diagnostic_features(cd.validate_params({"source": "test"})) != []
    assert cd.diagnostic_alarms(
        cd.validate_params({"source": "test", "shape": "blob"})
    ) == [("cd_touches_edge", True)], "cd_touches_edge 的極性是「1 = 只是下限」"


# --------------------------------------------------------------------------- #
# 聚合三支：alarm map / 診斷欄 / 分組都來自宣告
# --------------------------------------------------------------------------- #
def test_alarm_map_and_diagnostic_columns_come_from_declarations():
    r = _recipe([LOAD, ("m1", "glv_stats",
                        {"source": "test", "min_pixels": 10})])
    assert diagnostic_alarm_map(r, "ebi_patch") == {"glv_ok": False}
    cols = diagnostic_columns(r, "ebi_patch")
    assert "glv_pixels" in cols and "glv_ok" in cols


def test_rescued_names_count_as_diagnostics_too():
    """兩張 Enhance 卡都寫 `clip_frac`，engine 把先寫的救成帶前綴的名字 ——
    那一份也是診斷（跟 `studio._feature_sections` 同一個理由）。"""
    r = _recipe([LOAD,
                 ("n1", "normalize", {"streams": "test"}),
                 ("n2", "normalize", {"streams": "test"})])
    cols = diagnostic_columns(r, "ebi_patch")
    assert "clip_frac" in cols
    # 兩張卡的前綴撞在一起（都寫 test）→ 全部退回節點 id（engine 的規則）
    assert "n1_clip_frac" in cols and "n2_clip_frac" in cols


def test_bound_specs_follow_the_producing_card_in_execution_order():
    r = _recipe([LOAD,
                 ("m1", "glv_stats", {"source": "test"}),
                 ("m2", "cd_measure", {"source": "test"})])
    by = {b.spec.name: b for b in bound_specs(r, "ebi_patch")}
    assert by["glv_median"].node_id == "m1"
    assert by["cd_n"].node_id == "m2"
    order = [b.node_id for b in bound_specs(r, "ebi_patch") if b.node_id]
    assert order.index("m1") < order.index("m2")


def test_a_colliding_name_belongs_to_the_card_whose_value_wins():
    """**這一條 2026-08-28 翻面了（F51），而翻面的方向就是那個 bug。**

    原本寫的是「撞名的裸名歸**第一個**產出者」。那句話跟引擎相反 ——
    `engine._rescue_overwritten_features` 是**後寫的贏**：最後一張卡的值留在
    ``glv_median``，被蓋掉的那幾張各被救成 ``<前綴>_glv_median``。

    照舊的說法，結果表會把 ``glv_median`` 分到 m1 底下、回溯面板點下去跳到
    m1 —— 而畫面上那個數字是 m2 算的。**跑得完、有數字、而且是錯的。**

    尺在 `tests/test_feature_names_match_the_engine.py`：真的跑一次引擎，
    拿它的 keys 當基準。
    """
    r = _recipe([LOAD,
                 ("m1", "glv_stats", {"source": "test"}),
                 ("m2", "glv_stats", {"source": "ref"})])
    by = {b.spec.name: b for b in bound_specs(r, "ebi_patch")}
    assert by["glv_median"].node_id == "m2", "裸名要歸最後寫它的那張卡"
    # 被蓋掉的那一張沒有消失 —— 它有一個帶前綴的身分（同引擎的救援）。
    rescued = [n for n in by if n.endswith("glv_median") and n != "glv_median"]
    assert rescued and by[rescued[0]].node_id == "m1", rescued


def test_duplicate_card_labels_carry_the_node_id():
    r = _recipe([LOAD,
                 ("m1", "glv_stats", {"source": "test"}),
                 ("m2", "glv_stats", {"source": "ref"})])
    pairs = {(b.node_id, b.label) for b in bound_specs(r, "ebi_patch")
             if b.node_id in ("m1", "m2")}
    labels = [label for _nid, label in pairs]
    assert len(labels) == len(set(labels)), "同名卡要帶 id 才分得開"


def test_the_engine_group_declares_the_verdicts_own_names():
    r = _recipe([LOAD], decide=DecideSpec(
        let=[Let(name="bright", expr="glv_median", fill="-1"),
             Let(name="z", expr="bright", scale="z")],
        rules=[Rule(when="bright > 1", bin=1, label="odd")]))
    by = {b.spec.name: b for b in bound_specs(r, "ebi_patch")}
    for name in ("decide_unanswered", "bright", "bright_missing",
                 "z", "z_raw"):
        assert name in by, name
        assert by[name].node_id == "" and by[name].label == ENGINE_LABEL
        assert by[name].spec.family == "engine"
    assert by["bright_missing"].spec.variant == "missing"
    assert by["z_raw"].spec.variant == "raw"
    # score **有算式才宣告** —— 這份 decide 沒填 score，引擎不會寫那一格。
    assert "score" not in by


def test_score_is_declared_only_when_an_expression_exists():
    r = _recipe([LOAD], score="glv_median + 1")
    by = {b.spec.name: b for b in bound_specs(r, "ebi_patch")}
    assert by["score"].label == ENGINE_LABEL, "有算式就宣告（反空洞）"


def test_rescued_diagnostic_names_get_a_spec_too():
    """跟 `diagnostic_columns` 報的是同一個名字、variant='rescued'。"""
    r = _recipe([LOAD,
                 ("n1", "normalize", {"streams": "test"}),
                 ("n2", "normalize", {"streams": "test"})])
    by = {b.spec.name: b for b in bound_specs(r, "ebi_patch")}
    cols = set(diagnostic_columns(r, "ebi_patch"))
    assert "n1_clip_frac" in by and "n1_clip_frac" in cols
    assert by["n1_clip_frac"].spec.variant == "rescued"
    assert by["n1_clip_frac"].node_id == "n1"


# --------------------------------------------------------------------------- #
# F76 刀 1：一個區域一個顏色 —— 序由畫布上那幾條區域線給
# --------------------------------------------------------------------------- #
def test_one_region_gets_one_colour_no_matter_which_card_wrote_the_number():
    """**同一個區域名，在任兩張卡底下都要拿到同一個 `region_index`。**

    `region_index` 決定顏色，而顏色同時是影像上那個 ROI 框的顏色。改之前它由
    每張卡各自算（`_util.region_spec_maker` 的 ``regions.index(region)``），
    而那兩個序不是同一個序 —— 出貨的 rsem-worst-box 上實測：

        between_columns  由 ROI 卡寫的特徵 → 0（綠）
        between_columns  由 GLV 卡寫的特徵 → 1（琥珀）

    ROI 卡一次只定義一個家族，自己那份的序永遠是 0；GLV 卡接了三條線是 0/1/2。
    於是同一塊在同一張表上有兩種顏色，而影像上那個框只有一種
    —— `CLAUDE.md` §3「顏色指錯區域比沒有顏色糟得多」、鐵則 10。
    """
    recipe = Recipe.load(Path(__file__).resolve().parent.parent
                         / "recipes" / "rsem-worst-box.json")
    by_region: Dict[str, set] = {}
    for b in bound_specs(recipe, "rsem"):
        if b.spec.region:
            by_region.setdefault(str(b.spec.region), set()).add(
                int(b.spec.region_index))
    assert by_region, "這份 recipe 本來就有三個區域，抓不到就是這條測試空轉了"
    bad = {r: sorted(v) for r, v in by_region.items() if len(v) != 1}
    assert not bad, "同一個區域拿到不只一個顏色：%s" % bad


def test_the_region_order_is_the_order_of_the_wires():
    """序**由線給**，不是由執行順序、也不是由字母序。

    量測卡的 ``roi`` 那一格是從線水合出來的，所以那張卡的迴圈序
    （`MultiSourceStep.CURRENT_REGION_INDEX` —— 疊圖上框的顏色用的就是它）
    逐字就是這幾條線在 ``recipe.edges`` 裡的順序。照線編，畫面跟影像才對得上。
    """
    from d4t.core.pipeline.verdict_features import _regions_in_wiring_order

    recipe = Recipe.load(Path(__file__).resolve().parent.parent
                         / "recipes" / "rsem-worst-box.json")
    order = _regions_in_wiring_order(recipe)
    assert order == {"on_pattern": 0, "between_columns": 1, "between_rows": 2}, \
        order
    # 而 bound_specs 用的就是它
    seen = {str(b.spec.region): int(b.spec.region_index)
            for b in bound_specs(recipe, "rsem") if b.spec.region}
    assert seen == order


def test_a_region_that_is_on_no_wire_still_gets_its_own_number():
    """家族成員（``<n>_center`` / ``<n>_others``）不在線上，但仍然一名一號。

    退化原則：線上沒有的名字接在後面照第一次出現的順序 —— **不可以**擠成
    同一個號（那就是這一刀在修的病的鏡像）。
    """
    from d4t.core.pipeline.verdict_features import _regions_in_wiring_order

    recipe = Recipe.load(Path(__file__).resolve().parent.parent
                         / "recipes" / "rsem-worst-box.json")
    order = dict(_regions_in_wiring_order(recipe))
    for extra in ("on_pattern_center", "on_pattern_others"):
        order.setdefault(extra, len(order))
    assert len(set(order.values())) == len(order), order
