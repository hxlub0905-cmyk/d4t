# ADEPT M4 端到端驗收 — authored 2026-07-28.
"""M4 驗收：**同一份 recipe 吃兩種輸入**。

- EBI patch（KLARF + multi-page TIFF，機台附 test/ref）走 ebi_patch route
- Review SEM（KLARF + 每顆一張圖，沒有 ref）走 rsem route，
  由 Golden Cell 卡自己疊一張參考圖出來

兩條 route 共用同一段算法與判定（相減 → 去噪 → SNR → 區域 → CD → GLV → 同一條
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
from adept.core.pipeline import (
    Recipe, accepted_kinds, route_for_kind, run_dataset, validate,
)  # noqa: E402

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


def test_recipe_takes_both_input_types_and_validates(recipe):
    # ``load_single`` 同時吃 rsem 與 folder（一顆一張圖，來源不同而已），
    # 所以這裡問的是「兩種都吃得下」，不是「剛好只吃這兩種」。
    assert {"ebi_patch", "rsem"} <= set(accepted_kinds(recipe))
    for kind in ("ebi_patch", "rsem"):
        errs = [i for i in validate(recipe, kind=kind) if i.level == "error"]
        assert not errs, (kind, errs)


def test_each_input_type_gets_its_own_chain(recipe):
    """兩條 pipeline，各自一份節點 —— **共用結束了**（F9 Phase 3d）。

    這份 fixture 是舊格式（``routes``），兩條 route 有 8 個共用節點。載入時
    ``_migrate_routes`` 把共用的那幾個複製成一段一份，因為共用的那一張會讓
    「改 rsem 的門檻」順手改掉 patch 的 —— 跟判定卡「每條分支一張」是同一個
    理由。行為不變（下面那支 e2e 是證明），變的是它們現在改得動而不互相干擾。
    """
    ebi = route_for_kind(recipe, "ebi_patch")
    rsem = route_for_kind(recipe, "rsem")
    assert not (set(ebi) & set(rsem)), "兩條 pipeline 不該再共用節點"

    # 起手卡各自是對的那一張 Input 卡
    assert recipe.nodes[ebi[0]].step == "load_patch"
    assert recipe.nodes[rsem[0]].step == "load_single"

    # rsem 多一張 Golden Cell 卡（自己造 ref）；ebi 沒有
    golden = [nid for nid in rsem if recipe.nodes[nid].step == "golden_cell"]
    assert golden and not [nid for nid in ebi
                           if recipe.nodes[nid].step == "golden_cell"]
    assert recipe.nodes[golden[0]].params["out"] == "ref"


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
    """RSEM 沒有 ref —— Golden Cell 必須造出一張，且與原圖同尺寸可相減。"""
    from adept.core.pipeline import run_defect

    ds = load_dataset(rsem_lot["klarf"])
    res = run_defect(recipe, ds.items[0], "rsem", keep_context=True)
    assert res.ok, res.error
    ctx = res.context
    assert "ref" in ctx.images, "Golden Cell 應產生 ref 影像流"
    assert ctx.images["ref"].shape == ctx.images["test"].shape
    assert "diff" in ctx.images
    # Golden Cell 的診斷特徵要有意義（週期被找到）
    assert res.features["golden_px"] >= 2 and res.features["golden_py"] >= 2
