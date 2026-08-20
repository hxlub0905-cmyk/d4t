# d4t M4 端到端驗收 — authored 2026-07-28.
"""M4 驗收：**同一份 recipe 吃兩種輸入**。

- EBI patch（KLARF + multi-page TIFF，機台附 test/ref）走 ebi_patch route：
  相減 → 去噪 → Z-map → CD → GLV
- Review SEM（KLARF + 每顆一張圖，**沒有 ref**）走 rsem route：
  直接量單張影像（Z-map → CD → GLV）

兩條 route 共用的是 **ADC 那一段**（同一條分數表達式、同一個門檻）。

★ 2026-08-20（F16）：rsem 那條 route 換掉了，而且它不再是準確率的證據 ★
--------------------------------------------------------------------
以前 rsem 靠 `pattern_ref`（2026-08-18 之前叫 `golden_cell`）從單張影像的重複
pattern 疊一張 ref 出來，於是它也有 `diff` 可以量 —— 分類正確率 24/24。
使用者 2026-08-20 定調「這項功能完全沒用，請直接拿掉」，那張卡因此刪掉了。

**代價是這條 route 的準確率證據跟著消失**，而且比 2026-08-18 記的那個
「12/24 ＝猜銅板」更明確 —— 2026-08-20 重量了 seed 11 / 3 / 21，三次都是
**12/24，而且是因為它把每一顆都判成 bin 0**（那 24 顆裡正好 12 顆沒有缺陷）。
原因是分數的尺度變了：量 diff 時 `(glv_max-glv_median)/(glv_std+0.5)` 落在 5–30，
直接量單張影像時落在 2.5 上下，而門檻是 4.2。

**這不是把門檻調一下就會好的事**：單張影像上這三個統計量描述的是「這張圖的
對比長什麼樣」，不是「哪裡跟旁邊不一樣」—— 沒有 ref 就沒有後者。要讓這條 route
再有意義，得等 Region 段圈出區域、由 `Compare regions` 去比（那是使用者現在的
RSEM 路線），而那需要一份帶 ROI 的 fixture，不是這份最小 recipe 的工作。

所以下面的 rsem 斷言只問「跑得完、每一顆都有完整的特徵向量、算得出分數」——
**不問正確率**。假裝那個數字還在，比明講它沒了更糟。

ebi_patch 那條的準確率斷言原封不動。
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

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import load_dataset   # noqa: E402
from d4t.core.pipeline import Recipe, run_dataset, validate  # noqa: E402

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


def test_both_routes_end_in_the_same_adc(recipe):
    """兩條 route 共用的是 **ADC 那一段**：同一條分數表達式、同一個門檻。

    F16 之前這裡斷言的是「影像段也共用」（align / sub / dn / snr / cd 五個節點）
    —— 那件事靠的是 `pattern_ref` 幫 rsem 造一張 ref 出來，讓它也走得了相減
    那條路。那張卡拿掉之後**那句話就不成立了**，而 recipe 只剩一個共用點：
    `score`。

    這一條仍然是 M4 的驗收（「一份 recipe 吃得下兩種輸入」），只是它現在守的是
    真正還成立的那一半 —— 兩條 route 各自量各自的，最後由**同一個判定**收尾。
    """
    ebi, rsem = recipe.routes["ebi_patch"], recipe.routes["rsem"]
    assert ebi and rsem and ebi != rsem
    # 兩條都吐得出分數表達式要的那三個變數（名字相同 → 同一條表達式適用）
    for var in ("glv_max", "glv_median", "glv_std"):
        assert var in recipe.score.expr, var
    assert recipe.score.bins == {"below": 0, "above": 1}
    # 而「ref 從哪來」這件事在 rsem 上已經沒有答案了：它不再有相減那一段。
    assert "sub" in ebi and "sub" not in rsem
    assert not any(recipe.nodes[n].step == "pattern_ref" for n in rsem), \
        "pattern_ref 已於 F16 刪除，不該再出現在任何 route 上"


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

    # 每顆都要有完整特徵向量（供報表與 ML 備料）—— 兩條 route 都要。
    for r in results:
        for key in ("glv_max", "glv_median", "glv_std", "cd_x_px", "score"):
            assert key in r.features, f"{r.defect_id} 缺 {key}"

    if expect_kind != "ebi_patch":
        # rsem：**只問跑得完、算得出分數**（見模組 docstring）。
        # 它的準確率證據隨著 `pattern_ref` 一起消失了（F16），這裡不假裝還有。
        return

    gt = json.loads(Path(lot["ground_truth"]).read_text(encoding="utf-8"))
    correct = sum(1 for r in results if (r.bin == 1) == gt[r.defect_id]["is_real"])
    # 實測 seed 7 為 24/24；跨 seed 平均 ~95%，門檻留餘裕。
    # 20 而不是原本的 21：這份測試用的 recipe 在 F8 第五輪失去了它的 ROI 卡
    # （``roi_define`` 隨著 ROI 收斂成 Profile / Template / GDS 被拿掉），
    # 現在量的是整張圖 —— 少了聚焦，準確率本來就會掉一點。
    assert correct >= 20, f"{expect_kind} 分類正確 {correct}/24"


def test_the_rsem_route_measures_the_single_image_directly(recipe, rsem_lot):
    """RSEM 沒有 ref，而 F16 之後也**沒有任何卡片造得出 ref** —— 所以它直接量。

    這一條取代了以前的 `test_rsem_route_builds_its_own_reference`。那一條守的是
    「`pattern_ref` 疊得出一張同尺寸的 ref，於是這條 route 也有 diff」，而那張卡
    2026-08-20 拿掉了（使用者：「完全沒用」）。

    現在要守的是**這條 route 沒有安靜地退化**：它不該產生 ref 或 diff（產生了
    就表示有人又把某張卡接上來卻沒人發現），而它量的那張圖就是載進來的那一張。
    """
    from d4t.core.pipeline import run_defect

    ds = load_dataset(rsem_lot["klarf"])
    res = run_defect(recipe, ds.items[0], "rsem", keep_context=True)
    assert res.ok, res.error
    ctx = res.context
    assert "ref" not in ctx.images and "diff" not in ctx.images, \
        "rsem 這條 route 不該有 ref/diff（沒有卡片造得出來）：%s" % sorted(ctx.images)
    assert "test" in ctx.images, sorted(ctx.images)
    # 量出來的東西要真的來自那張圖（Z-map 的峰值不是常數）
    assert "snr_max" in res.features
    assert res.features["glv_std"] > 0.0
