# F17-④：「一顆」與「整批」是同一個模型的兩個尺度。
"""在此之前這件事是一個布林 ``is_batch`` —— 而布林答不出「還有第三種嗎」。

宣告成**尺度**之後，兩層是同一份 recipe 的 DAG：都用同一支 `execution_order`
排序（F17-① 之後那是純粹的線拓樸），差別只在餵進去的是一顆 defect 還是整批的
結果表。

⚠ **「試跑不寫」不能因為統一而消失**（使用者 2026-08-20 定調）。統一的是
**宣告**，不是**入口**：`run_batch` 只跑、`run_batch_steps` 才寫，而試跑那條路
根本不叫後者。那兩條守門測試在 `tests/test_batch_steps.py`，這一份不重複。

這一份鎖住四件事：

1. ``scale`` 與 ``is_batch`` **永遠是同一句話**，而且**兩個方向都通**
   （舊卡片直接寫 ``is_batch = True`` 仍然認得 —— 判準是「舊東西在不在」）；
2. 兩層都由同一支 `execution_order` 排序；
3. 逐顆那一層**跳過**整批的卡（而且跳過不是報錯）；
4. **整批的卡是 end point** —— 從它拉一條線出去是 error，因為那條線永遠不會
   有資料。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.recipe import (  # noqa: E402
    Edge, Recipe, RecipeNode, ScoreSpec, execution_order, validate,
)
from d4t.core.pipeline.step import (  # noqa: E402
    CATEGORY_ALGO, REGISTRY, SCALE_DEFECT, SCALE_LOT, Step, register_step,
)

KIND = "ebi_patch"


def _codes(issues):
    return [i.code for i in issues]


# --------------------------------------------------------------------------- #
# 1. scale 與 is_batch 是同一句話（兩個方向）
# --------------------------------------------------------------------------- #
def test_declaring_the_scale_sets_is_batch():
    class NewStyle(Step):
        key = "t_scale_new"
        label = "新寫法"
        category = CATEGORY_ALGO
        help = "測試用"
        scale = SCALE_LOT

    assert NewStyle.is_batch is True


def test_declaring_is_batch_sets_the_scale():
    """**舊卡片與外掛的相容路徑。**

    只做另一個方向的話，一張還沒遷移的卡會宣告 `is_batch` 卻被引擎當成逐顆的
    —— 而它的 `run()` 通常是一句「這張卡不該這樣跑」，於是**每一顆都失敗**。
    """
    class OldStyle(Step):
        key = "t_scale_old"
        label = "舊寫法"
        category = CATEGORY_ALGO
        help = "測試用"
        is_batch = True

    assert OldStyle.scale == SCALE_LOT


def test_the_default_is_one_defect_at_a_time():
    class Plain(Step):
        key = "t_scale_plain"
        label = "一般"
        category = CATEGORY_ALGO
        help = "測試用"

    assert Plain.scale == SCALE_DEFECT and Plain.is_batch is False


def test_every_registered_card_agrees_with_itself():
    """自動套用到 registry 裡每一張卡 —— 兩個欄位不能各說各話。"""
    for key, cls in sorted(REGISTRY.items()):
        assert cls.is_batch == (cls.scale == SCALE_LOT), key
        assert cls.scale in (SCALE_DEFECT, SCALE_LOT), (key, cls.scale)


def test_a_bad_scale_is_refused_at_registration():
    with pytest.raises(ValueError) as e:
        @register_step
        class Bad(Step):
            key = "t_scale_bad"
            label = "壞的"
            category = CATEGORY_ALGO
            help = "測試用"
            scale = "每個禮拜一次"

            def run(self, ctx, params):
                return ctx
    assert "scale" in str(e.value)
    REGISTRY.pop("t_scale_bad", None)


def test_describe_carries_the_scale():
    """UI / CLI 的卡片列表看得到它 —— 不然「這張卡什麼時候跑」只存在程式碼裡。"""
    from d4t.core.pipeline.step import get_step
    assert get_step("output_report").describe()["scale"] == SCALE_LOT
    assert get_step("glv_stats").describe()["scale"] == SCALE_DEFECT


# --------------------------------------------------------------------------- #
# 2 & 3. 兩層同一支排序；逐顆那一層跳過整批的卡
# --------------------------------------------------------------------------- #
def _recipe(edges=()):
    return Recipe(
        recipe_id="t", routes={KIND: ["load", "glv", "csv"]},
        edges=[Edge(*e) for e in edges],
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "glv": RecipeNode("glv", "glv_stats", {"source": "test"}),
               "csv": RecipeNode("csv", "output_report",
                                 {"folder": "/tmp/x", "contents": "table"})},
        score=ScoreSpec(expr="1", threshold=1.0,
                        bins={"below": 0, "above": 1}))


def test_both_layers_use_the_same_order():
    """整批那一層**不是另一套排序** —— 它跑的是同一份 DAG 的一個子集。"""
    rec = _recipe([("load", "glv", "test", "source")])
    order = execution_order(rec, KIND)
    lot = [n for n in order if REGISTRY[rec.nodes[n].step].scale == SCALE_LOT]
    assert lot == ["csv"]
    assert order.index("glv") < order.index("csv")


def test_a_single_defect_run_skips_the_lot_layer(tmp_path):
    """跳過**不是報錯**：一份含 Output 卡的 recipe 在單顆預覽上要跑得完
    （那是使用者調參數的畫面）。這一條與 `tests/test_batch_steps.py` 呼應。"""
    from d4t.core.pipeline import run_defect
    from d4t.core.ingest.dataset import load_dataset
    sys.path.insert(0, str(REPO / "tools"))
    from make_sample import generate

    lot = generate(str(tmp_path / "lot"), n=2, seed=7)
    item = load_dataset(lot["klarf"]).items[0]
    csv = tmp_path / "out.csv"
    rec = _recipe([("load", "glv", "test", "source")])
    rec.nodes["csv"].params["path"] = str(csv)
    res = run_defect(rec, item, KIND)
    assert res.ok, res.error
    assert not csv.exists(), "單顆跑不該寫出任何東西"


# --------------------------------------------------------------------------- #
# 4. 整批的卡是 end point
# --------------------------------------------------------------------------- #
def test_a_line_out_of_a_lot_card_is_an_error():
    """使用者 2026-08-20 定調 Output 段「他就是個 end point」。

    在此之前那件事只是「這幾張卡的 `resolve_writes` 剛好是空的」—— 一份手寫的
    recipe 照樣可以從它拉一條線出去，而那條線**永遠不會有資料**（整批那一層在
    所有結果收齊之後才跑，它下游的逐顆卡早就跑完了）。症狀會是「畫布上有一條
    線，但下游那張卡什麼都沒收到」。
    """
    rec = _recipe([("csv", "glv", "x", "source")])
    issues = validate(rec)
    assert "batch-card-has-downstream" in _codes(issues)
    bad = [i for i in issues if i.code == "batch-card-has-downstream"][0]
    assert bad.node_id == "csv" and bad.level == "error"
    assert "glv" in bad.detail


def test_a_normal_recipe_does_not_trip_it():
    rec = _recipe([("load", "glv", "test", "source")])
    assert "batch-card-has-downstream" not in _codes(validate(rec))
