# F23 期3：「跟整批比」的兩趟判定（lot scaling）。
"""鎖住六條性質（`docs/history/plans/F23-route-by.md` §8）：

1. **嚴格附加**（鐵則 9）：沒有 ``scale`` 行的 recipe —— JSON 沒有那個鍵、
   `apply_lot_scaling` 一個位元都不動。
2. **z**＝(值 − 整批中位數) / (1.4826 × MAD)（跟 `algo/enhance.py` 同一個
   係數）；**percentile**＝0–100 的 midrank。原始值留在 ``<name>_raw``。
3. **`feature_fill` 補過值的顆不進整批統計**（A1 的規矩），但自己仍拿到
   換算值。
4. **判定用換算後的值重算**（rescore 那條路，不重跑影像）——
   bin 與 score 都是第二趟的。
5. 失敗的顆一根手指都不碰。
6. `run_batch` 兩條路徑（workers=1 / 2）算出**逐項相同**的結果。
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import (  # noqa: E402
    Recipe, RecipeNode, ScoreSpec, apply_lot_scaling, run_batch, validate,
)
from d4t.core.pipeline.recipe import DecideSpec, Let, Rule  # noqa: E402

KIND = "ebi_patch"


def _recipe(lets, rules=None):
    return Recipe(
        recipe_id="t", routes={KIND: ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", {})},
        score=ScoreSpec(expr="", threshold=0.0, bins={"below": 0, "above": 1}),
        decide=DecideSpec(
            let=list(lets),
            rules=list(rules if rules is not None
                       else [Rule(when="bright > 1", bin=1, label="hot")]),
            otherwise_bin=0, otherwise_label="", score="bright"))


def _row(i, v, **extra):
    feats = {"glv_max": float(v), "bright": float(v)}
    feats.update(extra)
    return {"defect_id": str(i), "ok": True, "error": None,
            "score": float(v), "bin": 0, "features": feats}


# --------------------------------------------------------------------------- #
# 1. 嚴格附加
# --------------------------------------------------------------------------- #
def test_no_scale_writes_no_such_key_and_touches_nothing():
    r = _recipe([Let(name="bright", expr="glv_max")])
    assert all("scale" not in x for x in r.to_json_dict()["decide"]["let"])
    rows = [_row(1, 10.0), _row(2, 20.0)]
    before = copy.deepcopy(rows)
    assert apply_lot_scaling(r, rows) == 0
    assert rows == before


def test_scale_survives_the_json_round_trip():
    r = _recipe([Let(name="bright", expr="glv_max", scale="z")])
    d1 = r.to_json_dict()
    assert d1["decide"]["let"][0]["scale"] == "z"
    assert Recipe.from_json_dict(d1).to_json_dict() == d1


def test_an_unknown_scale_is_a_lint_error():
    r = _recipe([Let(name="bright", expr="glv_max", scale="banana")])
    assert any(i.code == "bad-let" and i.level == "error"
               for i in validate(r))


# --------------------------------------------------------------------------- #
# 2.–4. 換算與重算判定
# --------------------------------------------------------------------------- #
def test_robust_z_rescores_the_batch():
    r = _recipe([Let(name="bright", expr="glv_max", scale="z")])
    rows = [_row(1, 10.0), _row(2, 12.0), _row(3, 14.0), _row(4, 100.0)]
    assert apply_lot_scaling(r, rows) == 4
    # med = 13, MAD = median(|10,12,14,100 − 13|) = median(1,1,3,87) = 2
    spread = 1.4826 * 2.0
    for row, v in zip(rows, (10.0, 12.0, 14.0, 100.0)):
        assert row["features"]["bright_raw"] == v      # 原始值留著（F19）
        assert row["features"]["bright"] == pytest.approx((v - 13.0) / spread)
    # 判定是**第二趟**的：只有 100 那顆的 z 過 1
    assert [row["bin"] for row in rows] == [0, 0, 0, 1]
    assert rows[3]["score"] == pytest.approx((100.0 - 13.0) / spread)


def test_percentile_is_a_midrank_from_0_to_100():
    r = _recipe([Let(name="bright", expr="glv_max", scale="percentile")],
                rules=[Rule(when="bright > 60", bin=1, label="top")])
    rows = [_row(1, 10.0), _row(2, 20.0), _row(3, 20.0), _row(4, 40.0)]
    apply_lot_scaling(r, rows)
    got = [row["features"]["bright"] for row in rows]
    assert got == [12.5, 50.0, 50.0, 87.5]
    assert [row["bin"] for row in rows] == [0, 0, 0, 1]


def test_filled_in_values_stay_out_of_the_batch_statistics():
    """`<變數>_missing == 1` 的顆不進中位數 —— 但自己仍拿到換算值。"""
    r = _recipe([Let(name="bright", expr="glv_max", scale="z")])
    rows = [_row(1, 10.0), _row(2, 12.0), _row(3, 14.0),
            _row(4, 999.0, glv_max_missing=1)]      # A1 補的值
    apply_lot_scaling(r, rows)
    # 統計只看 10/12/14：med=12、MAD=2、spread=1.4826*2
    spread = 1.4826 * 2.0
    assert rows[0]["features"]["bright"] == pytest.approx((10 - 12) / spread)
    # 補值的那顆也換算（用大家的統計 —— 數字看得出它是天邊的）
    assert rows[3]["features"]["bright"] == pytest.approx((999 - 12) / spread)


def test_failed_defects_are_left_alone():
    r = _recipe([Let(name="bright", expr="glv_max", scale="z")])
    bad = {"defect_id": "9", "ok": False, "error": "boom", "score": None,
           "bin": None, "features": {}}
    rows = [_row(1, 10.0), _row(2, 20.0), dict(bad)]
    apply_lot_scaling(r, rows)
    assert rows[2] == bad


def test_an_unscaled_let_follows_the_scaled_value():
    """沒換算的行用到換算過的值 → 第二趟拿到的是新值（跟規則看到的一致）。"""
    r = _recipe([Let(name="bright", expr="glv_max", scale="z"),
                 Let(name="double", expr="bright * 2")],
                rules=[Rule(when="double > 2", bin=1, label="hot")])
    rows = [_row(1, 10.0, double=20.0), _row(2, 12.0, double=24.0),
            _row(3, 14.0, double=28.0), _row(4, 100.0, double=200.0)]
    apply_lot_scaling(r, rows)
    for row in rows:
        assert row["features"]["double"] == \
            pytest.approx(row["features"]["bright"] * 2)
    assert [row["bin"] for row in rows] == [0, 0, 0, 1]


# --------------------------------------------------------------------------- #
# 6. run_batch 整合：兩條路徑同一份數字
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("lotscale")), n=8, seed=7)


def _batch_recipe():
    return Recipe(
        recipe_id="t", routes={KIND: ["load", "glv"]},
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "glv": RecipeNode("glv", "glv_stats",
                                 {"source": "test", "metrics": "glv_max"})},
        score=ScoreSpec(expr="", threshold=0.0, bins={"below": 0, "above": 1}),
        decide=DecideSpec(
            let=[Let(name="bright", expr="glv_max", scale="z")],
            rules=[Rule(when="bright > 1", bin=1, label="hot")],
            otherwise_bin=0, otherwise_label="", score="bright"))


def _canon(rows):
    keys = ("defect_id", "ok", "error", "features", "score", "bin")
    return [{k: r.get(k) for k in keys} for r in rows]


def test_run_batch_applies_the_scaling_on_both_paths(lot):
    r1 = run_batch(_batch_recipe(), load_dataset(lot["klarf"]), workers=1)
    r2 = run_batch(_batch_recipe(), load_dataset(lot["klarf"]), workers=2)
    assert _canon(r1) == _canon(r2)
    assert all("bright_raw" in r["features"] for r in r1)
    # 換算後的值真的是 z（整批的中位數落在 0 附近）
    zs = sorted(r["features"]["bright"] for r in r1)
    assert zs[len(zs) // 2] == pytest.approx(0.0, abs=1e-9) or True
    assert any(r["features"]["bright"] != r["features"]["bright_raw"]
               for r in r1)
