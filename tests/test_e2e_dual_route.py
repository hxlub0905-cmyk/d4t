# ADEPT M4 端到端驗收 — authored 2026-07-28.
"""M4 驗收：**同一份 recipe 吃兩種輸入**。

- EBI patch（KLARF + multi-page TIFF，機台附 test/ref）走 ebi_patch route
- Review SEM（KLARF + 每顆一張圖，沒有 ref）走 rsem route

2026-08-18：rsem 那條 route 不再合成參考圖
------------------------------------------
使用者把 `golden_cell` 刪掉了（「他就是 template」）。那張卡是這個 repo 裡
**唯一**能從單張週期性影像疊出一張 ref 的東西 —— 拿掉之後，rsem 那條 route
沒有 ref、因此沒有 diff，只能量圖本身（Z-map：單張影像唯一算得出「哪裡突出」
的卡）。

**量到的結果分不出真假缺陷，而這裡照實寫。** 實測（seed 11、24 顆）每一個特徵
的 real 與 nuisance 完全重疊，最好的 `snr_max` 只有 d≈0.8；換成
`roi_cross` + `roi_compare` 的區域路線也一樣（d≈0.75）。所以這一份的 rsem 段
**沒有準確率斷言** —— 掛一個「>= 12/24」在上面比沒有更糟，那是猜銅板的分數，
而它會讓人以為這條路還在做原本那件事。

它守的仍然是兩件真的事：**同一份 recipe 吃得下第二種輸入**，以及
**那條路的數字不會偷偷變**（`tests/fixtures/golden/dual_route_basic__make_sample_rsem.json`）。
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


def test_the_two_routes_share_the_input_and_the_adc_tail(recipe):
    """共用的是**兩頭**：載入與判定。中間那一段分岔了，而那是有原因的。

    以前這一條斷言 `align` / `sub` / `dn` / `snr` / `cd` 五個節點都共用 ——
    因為兩條 route 都做得出 `diff`（rsem 那條靠 `golden_cell` 自己疊 ref）。
    `golden_cell` 刪掉之後 rsem 沒有 diff 了，所以那五個共用不回來：
    **一個節點一組參數，而「讀 diff」與「讀 test」是不同的參數。**

    共用的門檻因此降到真正還共用的東西上，而那才是這份 fixture 的重點：
    同一條分數表達式、同一個門檻，判定兩種輸入。

    （載入那一張**不共用而且不該共用**：`_migrate_split_load_cards` 會把單張那條
    route 上的 `load_patch` 換成它自己的一張 `load_single` —— 就地改掉共用的那
    一張會把 patch 那條弄壞，見 `recipe.py` 那支函式的 ⚠。）
    """
    ebi, rsem = recipe.routes["ebi_patch"], recipe.routes["rsem"]
    shared = set(ebi) & set(rsem)
    assert "norm" in shared, "正規化那一張兩條 route 共用"
    assert recipe.nodes[rsem[0]].step == "load_single"
    assert recipe.nodes[ebi[0]].step == "load_patch"
    # 判定只有一份（`score` 不分 route）—— 那就是「同一份 recipe」的意思。
    assert recipe.score.expr and recipe.score.threshold is not None
    # rsem 那條沒有 ref，所以沒有相減，也沒有任何節點讀得到 diff。
    assert "sub" in ebi and "sub" not in rsem
    for node_id in rsem:
        params = recipe.nodes[node_id].params
        assert "diff" not in str(params.values()), \
            f"{node_id} 在 rsem 這條 route 上讀 diff，但這條路做不出 diff"


def test_ingest_dispatches_by_input_type(ebi_lot, rsem_lot):
    ebi = load_dataset(ebi_lot["klarf"])
    rsem = load_dataset(rsem_lot["klarf"])
    assert ebi.kind == "ebi_patch"
    assert sorted(ebi.items[0].images) == ["ref", "test"]
    assert rsem.kind == "rsem"
    assert sorted(rsem.items[0].images) == ["single"]


@pytest.mark.parametrize("lot_name, expect_kind", [("ebi_lot", "ebi_patch"),
                                                   ("rsem_lot", "rsem")])
def test_same_recipe_runs_on_both_input_types(request, recipe, lot_name,
                                              expect_kind):
    """兩種輸入都跑得完，而且每一顆都拿得到完整的特徵向量。

    **準確率只斷言 ebi 那條**，理由見模組說明：rsem 那條失去了合成 ref，
    量到的東西分不出真假缺陷，而掛一個猜銅板等級的門檻會讓人以為它還在做
    原本那件事。
    """
    lot = request.getfixturevalue(lot_name)
    ds = load_dataset(lot["klarf"])
    assert ds.kind == expect_kind

    results = run_dataset(recipe, ds)
    assert len(results) == 24
    failed = [(r.defect_id, r.error) for r in results if not r.ok]
    assert not failed, failed

    # 每顆都要有完整特徵向量（供報表與 ML 備料）
    for r in results:
        for key in ("glv_max", "glv_median", "glv_std", "cd_x_px", "score"):
            assert key in r.features, f"{r.defect_id} 缺 {key}"


def test_the_patch_route_still_separates_real_from_nuisance(recipe, ebi_lot):
    """有 ref 的那條路要真的分得出來 —— 這是整份 fixture 唯一的準確率斷言。"""
    ds = load_dataset(ebi_lot["klarf"])
    results = run_dataset(recipe, ds)
    gt = json.loads(Path(ebi_lot["ground_truth"]).read_text(encoding="utf-8"))
    correct = sum(1 for r in results if (r.bin == 1) == gt[r.defect_id]["is_real"])
    # 20 而不是原本的 21：這份測試用的 recipe 在 F8 第五輪失去了它的 ROI 卡
    # （``roi_define`` 隨著 ROI 收斂成 Profile / Template / GDS 被拿掉），
    # 現在量的是整張圖 —— 少了聚焦，準確率本來就會掉一點。
    assert correct >= 20, f"ebi_patch 分類正確 {correct}/24"


def test_the_single_image_route_has_no_reference_and_says_so(recipe, rsem_lot):
    """單張那條路**沒有 ref 也沒有 diff** —— 這一條把那件事釘住。

    它不是一句抱怨：`golden_cell` 之後如果有人補回「單張影像的參考圖」那個能力
    （Region 段的 GDS 路線、或別的），這一條會紅，而那正是該回來重寫這份
    fixture 的時候。
    """
    from adept.core.pipeline import run_defect

    ds = load_dataset(rsem_lot["klarf"])
    res = run_defect(recipe, ds.items[0], "rsem", keep_context=True)
    assert res.ok, res.error
    ctx = res.context
    assert "ref" not in ctx.images and "diff" not in ctx.images
    # 單張影像上唯一算得出「哪裡突出」的東西：Z-map。
    assert "snr_map" in ctx.images
    assert res.features["snr_max"] > 0
