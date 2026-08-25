# F11 Region-4：三張「找 ROI」的卡，對每一個區域寫出**同一組**數字。
"""使用者 2026-08-18：

> 「我認為各種找／給定 ROI 的方法，理想上輸出的東西要接近⋯⋯現在不是不能用，
>   而是現在有點像大家資料結構不一樣。」

在這之前三張卡各寫各的：**Profile 一個區域數字都沒有**、Template 三個
（`present` / `others_present` / `edge_dropped`）、GDS 四個（`present` / `pieces` /
`area_px` / `clipped`）。於是下游（分數表達式、`Compare regions`、報表）**得先
知道這個區域是誰找的**，才問得出「它有沒有落在這一顆上」—— 那正是漏出去的地方。

這一份鎖的就是那件事：**同一組五個、每一個區域都有、而且宣告的就是真的寫的。**
不鎖的是卡片自己的診斷（`match_score` / `cross_pitch_x_px` / `layout_ok`）——
那些答的是「這一次定位可不可信」，而不同方法的可信度指標本來就不一樣，硬統一
會變成假的。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import template as algo_template  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.step import REGISTRY  # noqa: E402
from d4t.core.steps._util import REGION_FACTS  # noqa: E402
from tests.region_cards import region_card  # noqa: E402

PERIOD = 40
PATCH = 32


# --------------------------------------------------------------------------- #
# 三張卡各跑一次，回傳 (features, 宣告的 features, 宣告的區域)
# --------------------------------------------------------------------------- #
def _stripes(h=96, w=96, pitch=16) -> np.ndarray:
    img = np.full((h, w), 40, np.uint8)
    for x in range(0, w, pitch):
        img[:, x:x + pitch // 2] = 200
    for y in range(0, h, pitch):
        img[y:y + pitch // 2, :] = 160
    return img


def _big(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((240, 240), np.float32)
    for x in range(0, 240, PERIOD):
        img[:, x:x + PERIOD // 2] = 190.0
    img += rng.normal(0, 2.0, img.shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def _run_profile():
    ctx = Context(images={"ref": _stripes()})
    p = region_card("roi_cross").validate_params(
        {"source": "ref", "roi_out": "epi", "place": "crossing"})
    region_card("roi_cross")().run(ctx, p)
    return ctx, region_card("roi_cross").resolve_features(p), \
        region_card("roi_cross").resolve_regions_out(p)


def _run_template():
    cell = algo_template.build_golden_cell(_big()).cell
    frozen = algo_template.encode_cell(cell)
    ctx = Context(images={"ref": _big()[100:100 + PATCH, 0:PATCH]})
    p = region_card("roi_template").validate_params(
        {"source": "ref", "template": frozen, "regions": "epi: 0.1,0,0.3,1",
         "locate_axis": "x"})
    region_card("roi_template")().run(ctx, p)
    return ctx, region_card("roi_template").resolve_features(p), \
        region_card("roi_template").resolve_regions_out(p)


def _run_gds():
    lab = np.zeros((40, 40), np.uint8)
    lab[2:10, 2:10] = 1
    lab[20:30, 20:30] = 1
    lab[2:10, 20:30] = 2
    ctx = Context(images={"layout_label": lab})
    p = get_step("roi_reference").validate_params(
        {"method": "layout layers", "label_source": "layout_label",
         "layers": "1:epi, 2:mg"})
    get_step("roi_reference")().run(ctx, p)
    return ctx, get_step("roi_reference").resolve_features(p), \
        get_step("roi_reference").resolve_regions_out(p)


RUNNERS = {"Profile": _run_profile, "Template": _run_template,
           "Reference regions · GDS": _run_gds}


# --------------------------------------------------------------------------- #
# 1. 五個數字，每一張卡、每一個區域
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("label", sorted(RUNNERS))
def test_every_declared_region_gets_the_same_five_numbers(label):
    ctx, declared, regions = RUNNERS[label]()
    assert regions, "%s 應該吐得出區域" % label
    for name in regions:
        for fact in REGION_FACTS:
            key = "%s_%s" % (name, fact)
            assert key in ctx.features, "%s 少寫了 %s" % (label, key)
            assert key in declared, "%s 寫了 %s 卻沒宣告" % (label, key)


@pytest.mark.parametrize("label", sorted(RUNNERS))
def test_what_it_declares_is_what_it_writes(label):
    """宣告多了也是錯的 —— lint 與 UI 都靠這張清單，而它一旦不準就沒人相信它。"""
    ctx, declared, _regions = RUNNERS[label]()
    assert set(ctx.features) == set(declared), \
        "%s：宣告與實寫不一致 %s" % (label,
                                    sorted(set(ctx.features) ^ set(declared)))


def test_the_five_names_are_the_same_set_across_the_three_cards():
    """下游拿一個區域名就問得出五件事，**不必知道是誰找的** —— 這是整件事的目的。"""
    per_card = {}
    for label, run in RUNNERS.items():
        ctx, _declared, regions = run()
        got = set()
        for name in regions:
            got |= {k[len(name) + 1:] for k in ctx.features
                    if k.startswith(name + "_")
                    and k[len(name) + 1:] in REGION_FACTS}
        per_card[label] = got
    assert all(v == set(REGION_FACTS) for v in per_card.values()), per_card


# --------------------------------------------------------------------------- #
# 2. 數字的意思
# --------------------------------------------------------------------------- #
def test_present_and_boxes_and_area_come_from_what_was_really_stored():
    """不是卡片記的一份 —— 卡片自己算的很容易跟真的存進去的不一致。"""
    ctx, _d, _r = _run_gds()
    for name in ("epi", "mg"):
        assert ctx.features["%s_boxes" % name] == float(ctx.roi_count(name))
        rects = ctx.roi_rects(name, (40, 40))
        assert ctx.features["%s_area_px" % name] == float(
            sum(w * h for _x, _y, w, h in rects))
        assert ctx.features["%s_present" % name] == 1.0
    # epi 是兩塊、mg 是一塊 —— 面積與框數要分得出來
    assert ctx.features["epi_boxes"] == 2.0 and ctx.features["mg_boxes"] == 1.0


def test_a_region_that_is_not_on_this_defect_says_present_zero():
    lab = np.zeros((40, 40), np.uint8)
    lab[2:10, 2:10] = 1                        # 只有第 1 層，沒有第 2 層
    ctx = Context(images={"layout_label": lab})
    p = get_step("roi_reference").validate_params(
        {"method": "layout layers", "label_source": "layout_label",
         "layers": "1:epi, 2:mg"})
    get_step("roi_reference")().run(ctx, p)
    assert ctx.features["epi_present"] == 1.0
    assert ctx.features["mg_present"] == 0.0
    assert ctx.features["mg_boxes"] == 0.0
    assert ctx.features["mg_area_px"] == 0.0


def test_the_fallback_to_the_whole_image_is_not_reported_as_present():
    """定不出位置時 Profile／Template 會退回整張圖當保險。

    框在（下游有東西可以量），但**那不是那個區域** —— 所以 ``present = 0`` 而
    ``boxes = 1``。兩個數字合起來講出「有東西可以量，但它不是你要的那個」，
    而那是一個數字答不了的。這一條同時鎖住**兩張卡的答案一樣**。
    """
    for source in (np.full((64, 64), 120, np.uint8),):
        ctx = Context(images={"ref": source})
        p = region_card("roi_cross").validate_params(
            {"source": "ref", "roi_out": "epi"})
        region_card("roi_cross")().run(ctx, p)
        assert ctx.features["locate_ok"] == 0.0
        assert ctx.features["epi_present"] == 0.0
        assert ctx.features["epi_boxes"] == 1.0, "保險的那一個框應該還在"

    cell = algo_template.build_golden_cell(_big()).cell
    ctx = Context(images={"ref": np.full((PATCH, PATCH), 120, np.uint8)})
    p = region_card("roi_template").validate_params(
        {"source": "ref", "template": algo_template.encode_cell(cell),
         "regions": "epi: 0.1,0,0.3,1"})
    region_card("roi_template")().run(ctx, p)
    assert ctx.features["locate_ok"] == 0.0
    assert ctx.features["epi_present"] == 0.0


def test_clipped_and_edge_dropped_are_zero_when_nothing_was_dropped():
    for label in RUNNERS:
        ctx, _d, regions = RUNNERS[label]()
        for name in regions:
            assert ctx.features["%s_clipped" % name] == 0.0, (label, name)
            assert ctx.features["%s_edge_dropped" % name] == 0.0, (label, name)


def test_clipped_fires_when_the_box_limit_bites():
    """被上限砍掉的區域**仍然算得出一個很正常的灰階值** —— 所以要有旗標。"""
    n = 30
    lab = np.array([[1 if x <= y else 0 for x in range(n)] for y in range(n)],
                   np.uint8)
    ctx = Context(images={"layout_label": lab})
    p = get_step("roi_reference").validate_params(
        {"method": "layout layers", "label_source": "layout_label",
         "layers": "1:epi", "max_boxes": 5})
    get_step("roi_reference")().run(ctx, p)
    assert ctx.features["epi_clipped"] == 1.0
    assert ctx.features["epi_boxes"] == 5.0


def test_a_whole_family_shares_clipped_and_edge_dropped():
    """``<n>`` / ``<n>_center`` / ``<n>_others`` 三個名字拿到同一個值。

    重複是刻意的：下游手上只有**一個**名字（使用者在 `Compare regions` 上挑的
    那一個），它必須不必知道那是不是衍生名。
    """
    ctx, _d, regions = _run_profile()
    fam = [r for r in regions if r.startswith("epi")]
    assert len(fam) >= 2, fam
    for fact in ("clipped", "edge_dropped"):
        vals = {ctx.features["%s_%s" % (r, fact)] for r in fam
                if "%s_%s" % (r, fact) in ctx.features}
        assert len(vals) == 1, (fact, vals)


# --------------------------------------------------------------------------- #
# 3. 誰算「找 ROI 的卡」—— 新加一張也要照這組來
# --------------------------------------------------------------------------- #
def test_a_new_roi_card_cannot_quietly_invent_its_own_set():
    """任何吐區域的卡，宣告裡就必須有那五個 —— 不然這件事會再漂回去。

    判準是「**它吐不吐區域**」（`resolve_regions_out`），不是一張寫死的卡片清單：
    寫死的清單在下一張卡加進來時不會叫。
    """
    missing = []
    checked = []
    for key, cls in sorted(REGISTRY.items()):
        try:
            params = cls.validate_params({})
        except Exception:                      # noqa: BLE001 — 要外部資料的卡
            continue
        regions = list(cls.resolve_regions_out(params) or ())
        if not regions:
            # 預設參數下吐不出區域的卡（`roi_template` 要模板、`roi_reference`
            # 要層對照表）—— 它們由上面那三條逐張跑過，這裡掃不到是正常的。
            continue
        checked.append(key)
        declared = set(cls.resolve_features(params) or ())
        for name in regions:
            for fact in REGION_FACTS:
                if "%s_%s" % (name, fact) not in declared:
                    missing.append("%s: %s_%s" % (key, name, fact))
    assert not missing, "這幾張卡吐區域卻沒宣告那五個數字：%s" % missing
    # **這一條不准變成空跑的**：掃不到任何一張卡的時候它永遠是綠的，而那正是
    # 「加了一張卡卻沒人叫」的樣子。
    assert checked, "一張卡都沒掃到 —— 這條測試已經沒有在測任何東西"
