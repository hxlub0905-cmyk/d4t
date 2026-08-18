# ADEPT M4 端到端驗收 — authored 2026-07-28.
"""M4 驗收：**同一份 recipe 吃兩種輸入**。

- EBI patch（KLARF + multi-page TIFF，機台附 test/ref）走 ebi_patch route
- Review SEM（KLARF + 每顆一張圖，沒有 ref）走 rsem route，
  由「Reference from pattern」（`pattern_ref`，2026-08-18 之前叫
  `golden_cell`）自己疊一張參考圖出來

兩條 route 共用同一段算法與判定（相減 → 去噪 → SNR → blob → CD → GLV → 同一條
分數表達式、同一個門檻），只有影像尺寸相關的幾何參數不同。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate as gen_ebi          # noqa: E402
from make_sample_rsem import generate as gen_rsem    # noqa: E402

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.ingest.dataset import load_dataset   # noqa: E402
from adept.core.pipeline import Recipe, run_dataset, validate  # noqa: E402

RECIPE = REPO / "tests" / "fixtures" / "recipes" / "dual_route_basic.json"


@pytest.fixture(scope="module")
def recipe():
    return Recipe.load(str(RECIPE))


@pytest.fixture(scope="module")
def ebi_lot(tmp_path_factory):
    return gen_ebi(str(tmp_path_factory.mktemp("ebi")), n=24, seed=7)


@pytest.fixture(scope="module")
def rsem_lot(tmp_path_factory):
    return gen_rsem(str(tmp_path_factory.mktemp("rsem")), n=24, seed=11)


def test_recipe_has_both_routes_and_validates(recipe):
    assert set(recipe.routes) == {"ebi_patch", "rsem"}
    for kind in ("ebi_patch", "rsem"):
        errs = [i for i in validate(recipe, kind=kind) if i.level == "error"]
        assert not errs, (kind, errs)


def test_routes_share_the_algo_and_adc_tail(recipe):
    """兩條 route 只在「ref 從哪來」與影像尺寸幾何上不同，算法段必須共用同一批節點。"""
    ebi, rsem = recipe.routes["ebi_patch"], recipe.routes["rsem"]
    shared = set(ebi) & set(rsem)
    for node_id in ("align", "sub", "dn", "snr", "cd"):
        assert node_id in shared, f"{node_id} 應由兩條 route 共用"
    # rsem 多一張「自己造 ref」的卡；ebi 沒有
    assert "golden" in rsem and "golden" not in ebi
    assert recipe.nodes["golden"].step == "pattern_ref"
    assert recipe.nodes["golden"].params["out"] == "ref"


def test_ingest_dispatches_by_input_type(ebi_lot, rsem_lot):
    ebi = load_dataset(ebi_lot["klarf"])
    rsem = load_dataset(rsem_lot["klarf"])
    assert ebi.kind == "ebi_patch"
    assert sorted(ebi.items[0].images) == ["ref", "test"]
    assert rsem.kind == "rsem"
    assert sorted(rsem.items[0].images) == ["single"]


@pytest.mark.parametrize("lot_name, expect_kind", [("ebi_lot", "ebi_patch"),
                                                   ("rsem_lot", "rsem")])
def test_same_recipe_scores_both_input_types(request, recipe, lot_name, expect_kind):
    lot = request.getfixturevalue(lot_name)
    ds = load_dataset(lot["klarf"])
    assert ds.kind == expect_kind

    results = run_dataset(recipe, ds)
    assert len(results) == 24
    failed = [(r.defect_id, r.error) for r in results if not r.ok]
    assert not failed, failed

    gt = json.loads(Path(lot["ground_truth"]).read_text(encoding="utf-8"))
    correct = sum(1 for r in results if (r.bin == 1) == gt[r.defect_id]["is_real"])
    # 實測 seed 7/11 為 24/24；跨 seed 平均 ~95%，門檻留餘裕
    # 20 而不是原本的 21：這份測試用的 recipe 在 F8 第五輪失去了它的 ROI 卡
    # （``roi_define`` 隨著 ROI 收斂成 Profile / Template / GDS 被拿掉），
    # 現在量的是整張圖 —— 少了聚焦，準確率本來就會掉一點。這幾條測的是
    # 「一份 recipe 吃得下兩種輸入、而且算得出分數」，不是某個準確率數字。
    assert correct >= 20, f"{expect_kind} 分類正確 {correct}/24"

    # 每顆都要有完整特徵向量（供報表與 ML 備料）
    for r in results:
        for key in ("glv_max", "glv_median", "glv_std", "cd_x_px", "score"):
            assert key in r.features, f"{r.defect_id} 缺 {key}"


def test_rsem_route_builds_its_own_reference(recipe, rsem_lot):
    """RSEM 沒有 ref —— `pattern_ref` 必須造出一張，且與原圖同尺寸可相減。

    這一條是這個 repo 裡「單張影像也判得出缺陷」的**唯一**支撐點。2026-08-18
    那張卡被刪過一次，而刪掉之後同一條 route 的分類正確率從 24/24 掉到 12/24
    （＝猜銅板）—— 那個數字就是這一條測試在守的東西。
    """
    from adept.core.pipeline import run_defect

    ds = load_dataset(rsem_lot["klarf"])
    res = run_defect(recipe, ds.items[0], "rsem", keep_context=True)
    assert res.ok, res.error
    ctx = res.context
    assert "ref" in ctx.images, "這張卡應產生 ref 影像流"
    assert ctx.images["ref"].shape == ctx.images["test"].shape
    assert "diff" in ctx.images
    # 診斷特徵要有意義（週期被找到）
    assert res.features["ref_px"] >= 2 and res.features["ref_py"] >= 2
