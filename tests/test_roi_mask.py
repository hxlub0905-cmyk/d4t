# F8c 驗收：ROI mask 影像流 + 只用 mask 內像素的正規化（2026-08-14 核准的 (c)）。
"""動機：跨 patch 比 EPI 的 GLV 時，**MG 佔多少面積是隨 crop 變的**（64px 的
patch 一根 MG 進出畫面就是 12%）。整張圖的 percentile 因此逐顆漂 —— 同一片
EPI，隔壁多一根 MG，正規化完就變一個值。

計畫書 §7 的驗收條件寫死在最後一支測試裡：**crop 讓 MG 面積變動時，
「只用 EPI 正規化」的 EPI 亮度分散度要比「整張圖」收斂** —— 收斂不了的話
這個功能就不該收（回報，不硬做）。
"""
from __future__ import annotations

import numpy as np
import pytest

import adept.core.steps  # noqa: F401 — 註冊卡片
from adept.core.pipeline.context import Context
from adept.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec, validate
from adept.core.pipeline.step import REGISTRY, StepError, get_step

H = W = 128


def _ctx_with_regions() -> Context:
    ctx = Context(images={"test": np.full((H, W), 100, np.uint8)})
    # 兩塊不相鄰的區域（正規化座標）
    ctx.set_roi("epi", (0.0, 0.0, 0.25, 1.0))          # 左邊 32px 直條
    ctx.set_roi("mg", (0.75, 0.0, 0.25, 0.5))          # 右上 32x64
    return ctx


# --------------------------------------------------------------------------- #
# 1. roi_mask 卡本體
# --------------------------------------------------------------------------- #
def test_the_mask_is_the_union_of_the_named_regions():
    ctx = _ctx_with_regions()
    step = get_step("roi_mask")()
    step.run(ctx, {"regions": "epi, mg", "source": "test", "out": "mask"})
    mask = ctx.images["mask"]
    assert mask.shape == (H, W)
    assert set(np.unique(mask)) <= {0, 255}, "mask 只能有 0 與 255 兩種值"
    assert mask[:, :32].all(), "epi 那一條要整塊在 mask 裡"
    assert mask[:64, 96:].all(), "mg 那一塊也要在 —— 多名字是聯集"
    assert not mask[64:, 96:].any(), "mg 下方不在任何區域裡"


def test_the_card_declares_its_contract():
    cls = get_step("roi_mask")
    p = {"regions": "epi,mg", "source": "diff", "out": "m"}
    assert cls.resolve_reads(p) == ["diff"]
    assert cls.resolve_writes(p) == ["m"]
    assert cls.resolve_regions_in(p) == ["epi", "mg"]


def test_an_empty_regions_box_is_not_configured():
    """空的 regions 是合法的 str，但跑起來是全 0 的 mask ——
    參數合法 ≠ 設定完成（F7-13），要在 lint 就講。"""
    cls = get_step("roi_mask")
    issues = cls.configuration_issues({"regions": ""})
    assert issues and "region" in issues[0].lower()
    assert cls.configuration_issues({"regions": "epi"}) == []


def test_a_region_nobody_defines_is_caught_by_lint():
    rec = Recipe(
        recipe_id="t", routes={"ebi_patch": ["load", "m"]},
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "m": RecipeNode("m", "roi_mask", {"regions": "nope"})},
        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}))
    codes = {i.code for i in validate(rec, registry=REGISTRY)}
    assert "unknown-region" in codes


def test_an_empty_mask_warns_instead_of_failing():
    """regions 留空硬跑（lint 會擋，但擋不住 CLI 直接執行）：
    全 0 的 mask 要講一聲，不能安靜地讓下游「看起來有在用」。"""
    ctx = Context(images={"test": np.full((H, W), 100, np.uint8)})
    step = get_step("roi_mask")()
    step.run(ctx, {"regions": "", "source": "test", "out": "mask"})
    assert not ctx.images["mask"].any()
    assert any("no pixels" in w for w in ctx.meta.get("warnings", []))


# --------------------------------------------------------------------------- #
# 2. Normalize 的「Use only」
# --------------------------------------------------------------------------- #
def _epi_mg_patch(gain: float = 1.0, mg_cols: int = 32) -> np.ndarray:
    """左邊 EPI（緩慢的 100–120 斜坡）、右邊 mg_cols 欄 MG（230）。"""
    img = np.empty((H, W), np.float32)
    ramp = np.linspace(100.0, 120.0, W)[None, :].repeat(H, axis=0)
    img[:] = ramp
    if mg_cols > 0:
        img[:, W - mg_cols:] = 230.0
    return np.clip(img * gain, 0, 255).astype(np.uint8)


def _run_normalize(ctx: Context, **extra) -> None:
    params = {"streams": "test", "method": "percentile",
              "p_low": 2.0, "p_high": 98.0}
    params.update(extra)
    get_step("normalize")().run(ctx, params)


def test_the_range_is_measured_inside_the_mask_but_applied_everywhere():
    img = _epi_mg_patch()
    epi = np.zeros((H, W), np.uint8)
    epi[:, :W - 32] = 255                             # 只有 EPI 在 mask 裡

    ctx_whole = Context(images={"test": img.copy()})
    _run_normalize(ctx_whole)
    ctx_masked = Context(images={"test": img.copy(), "epi_mask": epi})
    _run_normalize(ctx_masked, use_within="epi_mask")

    def epi_span(out):
        area = out[:, :W - 32].astype(np.float32)
        return float(area.max() - area.min())

    # 整張圖量範圍：MG 的 230 撐大了範圍，EPI 的 20 階被壓扁
    assert epi_span(ctx_whole.images["test"]) < 80
    # 只從 EPI 量：EPI 自己的 2–98 百分位撐滿 0–255
    assert epi_span(ctx_masked.images["test"]) > 200
    # 套用是整張圖 —— MG 沒有被跳過，只是被夾到上限
    assert ctx_masked.images["test"][:, W - 16:].min() >= 250


def test_a_mask_of_the_wrong_size_is_a_step_error():
    ctx = Context(images={"test": _epi_mg_patch(),
                          "epi_mask": np.zeros((64, 64), np.uint8)})
    with pytest.raises(StepError) as err:
        _run_normalize(ctx, use_within="epi_mask")
    assert "Size like" in str(err.value), "訊息要指得出路在哪"


def test_an_all_zero_mask_falls_back_to_the_whole_image_and_says_so():
    img = _epi_mg_patch()
    ctx = Context(images={"test": img.copy(),
                          "epi_mask": np.zeros((H, W), np.uint8)})
    _run_normalize(ctx, use_within="epi_mask")
    ctx_plain = Context(images={"test": img.copy()})
    _run_normalize(ctx_plain)
    assert np.array_equal(ctx.images["test"], ctx_plain.images["test"])
    assert any("no pixels" in w for w in ctx.meta.get("warnings", []))


def test_normalize_declares_the_mask_as_a_read():
    cls = get_step("normalize")
    reads = cls.resolve_reads({"streams": "test", "method": "percentile",
                               "use_within": "epi_mask"})
    assert "epi_mask" in reads, "lint 的 missing-image 靠這個宣告"


# --------------------------------------------------------------------------- #
# 3. 計畫書 §7 的驗收：分散度要真的收斂
# --------------------------------------------------------------------------- #
def test_masked_normalize_shrinks_the_epi_spread_across_crops():
    """「一根 MG 進出畫面」（計畫書 §7 的原話）時，「只用 EPI 正規化」的
    EPI 平均亮度分散度要比「整張圖」收斂。沒收斂的話這個功能不該收 ——
    這支測試就是那句話的可執行版。

    整張圖的 percentile 最痛的不是 MG 面積 12% ↔ 24% 那種變動（p98 兩邊都
    落在 MG 上，反而穩），是 MG 面積**跨過百分位門檻**的那一下：0% ↔ 12%
    之間某處，p98 從「EPI 的頂」翻成「MG 的 230」，整個拉伸範圍跳掉，
    同一片 EPI 的輸出值從 ~130 掉到 ~20。而那正是 crop 造成的：
    條紋在畫面邊緣進進出出。
    """
    rng = np.random.default_rng(7)
    spread_whole, spread_masked = [], []
    # MG 從不在畫面裡（0）到一根完整的條紋（32 欄 = 25%），外加 ±3% 的
    # 整體增益漂移。0 → 2 → 4 欄之間 p98 的落點就翻掉了。
    for mg_cols, gain in [(0, 0.97), (2, 1.0), (4, 1.03),
                          (16, 0.99), (32, 1.02)]:
        img = _epi_mg_patch(gain=gain, mg_cols=mg_cols)
        img = np.clip(img.astype(np.float32)
                      + rng.normal(0, 1.0, img.shape), 0, 255).astype(np.uint8)
        epi_cols = W - 48                       # 這一欄之前永遠是 EPI
        epi = np.zeros((H, W), np.uint8)
        epi[:, :epi_cols] = 255

        ctx_a = Context(images={"test": img.copy()})
        _run_normalize(ctx_a)
        spread_whole.append(float(ctx_a.images["test"][:, :epi_cols].mean()))

        ctx_b = Context(images={"test": img.copy(), "epi_mask": epi})
        _run_normalize(ctx_b, use_within="epi_mask")
        spread_masked.append(float(ctx_b.images["test"][:, :epi_cols].mean()))

    sd_whole = float(np.std(spread_whole))
    sd_masked = float(np.std(spread_masked))
    assert sd_masked < sd_whole * 0.5, (
        "只用 EPI 量範圍沒有讓 EPI 的亮度更穩定（whole=%.2f masked=%.2f）——"
        "這個功能的存在理由不成立" % (sd_whole, sd_masked))
