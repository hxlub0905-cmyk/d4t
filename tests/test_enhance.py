# F7-10 驗收：空間性 artifact 的處理（背景／條紋／局部對比／邊緣保留去噪）。
"""這一輪的每一張卡都對應一種 E-beam patch 上**真實會有**的假訊號。

所以測試斷言的不是「函式跑得動」，而是**那個假訊號真的被拿掉了，而缺陷還在**。
「處理完之後缺陷也不見了」對這個工具是最糟的失敗 —— 它跑得完、有數字、
而且會漏抓；只驗形狀與 dtype 是抓不到的。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import enhance as algo_enhance  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402

DEFECT = (slice(30, 34), slice(30, 34))
QUIET = (slice(20, 24), slice(30, 34))     # 同一欄、沒有缺陷的地方


def _patch(gradient: float = 0.0, stripe_row: int = -1, defect: float = 40.0,
           noise: float = 6.0, seed: int = 0) -> np.ndarray:
    """合成一張帶指定 artifact 的 patch。"""
    rng = np.random.default_rng(seed)
    img = rng.normal(120.0, noise, (64, 64)).astype(np.float32)
    if gradient:
        img += np.linspace(0.0, gradient, 64)[None, :]
    if stripe_row >= 0:
        img[stripe_row, :] += 25.0
    if defect:
        img[DEFECT] += defect
    return img


def _contrast(img: np.ndarray) -> float:
    """缺陷相對於同一欄安靜處的高度。"""
    return float(np.mean(img[DEFECT]) - np.mean(img[QUIET]))


# --------------------------------------------------------------------------- #
# 1. 演算法：假訊號要不見，缺陷要留著
# --------------------------------------------------------------------------- #
def test_background_removal_flattens_the_gradient_and_keeps_the_defect():
    """charging 的亮度梯度在 test 與 ref 上不會一樣，所以它整片留在 diff 上。"""
    img = _patch(gradient=60.0)
    out = algo_enhance.remove_background(img, 31)

    before = float(np.ptp(np.mean(img, axis=0)))
    after = float(np.ptp(np.mean(out, axis=0)))
    assert after < before * 0.2, "梯度沒有被拿掉（%.1f -> %.1f）" % (before, after)
    assert _contrast(out) > 0.8 * _contrast(img), "缺陷跟著背景一起被減掉了"
    # 亮度基準要留著，否則下游每一個灰階門檻都要重調
    assert abs(float(out.mean()) - float(img.mean())) < 1.0


def test_destripe_removes_a_scan_line_without_inventing_one_at_the_defect():
    """用中位數而不是平均值：一顆夠大的缺陷會把該列的平均帶偏，
    校正時就在缺陷那一列造出一條**反向的假條紋**。"""
    img = _patch(stripe_row=10)
    out = algo_enhance.remove_stripes(img, axis=0)

    excess_before = float(img[10].mean() - img[9].mean())
    excess_after = float(out[10].mean() - out[9].mean())
    assert excess_before > 20.0                      # 前提：條紋真的在
    assert abs(excess_after) < 3.0, "條紋沒被拉平"

    assert _contrast(out) > 0.8 * _contrast(img), "缺陷被條紋校正吃掉了"
    # 缺陷所在的列（30-33）不可以被壓下去 —— 那就是平均值版本會犯的錯
    rows = [float(out[r].mean() - np.median(out)) for r in range(30, 34)]
    assert min(rows) > -3.0, "缺陷那幾列被反向校正了：%s" % rows


def test_destripe_handles_both_directions():
    img = _patch(defect=0.0)
    img[:, 12] += 25.0                                # 垂直條紋
    out = algo_enhance.remove_stripes(img, axis=1)
    assert abs(float(out[:, 12].mean() - out[:, 11].mean())) < 3.0


def test_clahe_lifts_contrast_inside_a_dark_area():
    """全域拉伸做不到這件事：暗區的對比是被亮區的分布決定的。"""
    img = np.zeros((64, 64), np.float32)
    img[:, :32] = 40.0            # 暗半邊
    img[:, 32:] = 200.0           # 亮半邊
    img[10:14, 10:14] += 8.0      # 暗區裡的微弱缺陷

    raw = float(img[10:14, 10:14].mean() - img[20:24, 10:14].mean())
    out = algo_enhance.clahe(img, 2.0, 8)
    lifted = float(out[10:14, 10:14].mean() - out[20:24, 10:14].mean())
    assert lifted > 1.5 * raw, "暗區缺陷沒有被拉起來（%.1f -> %.1f）" % (raw, lifted)


def test_morph_residual_keeps_small_features_and_drops_large_ones():
    img = _patch(gradient=60.0, defect=40.0)
    out = algo_enhance.morph_residual(img, 15)
    assert _contrast(out) > 0.7 * _contrast(img)
    assert float(np.ptp(np.mean(out, axis=0))) < 0.4 * float(np.ptp(np.mean(img, axis=0)))


def test_black_hat_finds_dark_defects():
    img = _patch(defect=0.0)
    img[DEFECT] -= 40.0
    out = algo_enhance.morph_residual(img, 15, dark=True)
    assert float(out[DEFECT].mean()) > float(out[QUIET].mean()) + 20.0


@pytest.mark.parametrize("method", ["bilateral", "nlm"])
def test_edge_preserving_denoise_keeps_a_small_defect_that_median_destroys(method):
    """這是加這兩個方法的**唯一**理由，所以直接拿 median 當對照。

    median 對「比核心小的亮點」是毀滅性的 —— 而那正好就是我們要找的東西。
    """
    import cv2

    rng = np.random.default_rng(1)
    img = rng.normal(120.0, 6.0, (64, 64)).astype(np.float32)
    img[30:33, 30:33] += 45.0            # 3x3 的小缺陷，比 5x5 核心還小

    def amp(a):
        return float(a[30:33, 30:33].mean() - np.median(a))

    fn = getattr(algo_enhance, method)
    kept = amp(fn(img, 5 if method == "bilateral" else 7))
    killed = amp(cv2.medianBlur(img, 5))
    assert killed < 0.25 * amp(img), "前提：median 確實會抹掉它"
    assert kept > 0.8 * amp(img), "%s 沒有保住缺陷（%.1f vs 原始 %.1f）" % (
        method, kept, amp(img))

    # 而且它真的有在去雜訊（不是原封不動回傳）
    flat_before = float(img[:20, :20].std())
    flat_after = float(fn(img, 5 if method == "bilateral" else 7)[:20, :20].std())
    assert flat_after < 0.8 * flat_before


def test_the_noise_estimate_is_what_makes_strength_portable():
    """``strength`` 的單位是「這張圖自己的雜訊 σ」，不是灰階常數。

    給常數的話，同一組參數換一台機台、換一個曝光就完全不對 —— 而使用者只會
    覺得是自己參數調錯。所以先量出 σ，再用它當尺度。
    """
    rng = np.random.default_rng(7)
    for true_sigma in (3.0, 6.0, 15.0):
        img = rng.normal(120.0, true_sigma, (64, 64)).astype(np.float32)
        est = algo_enhance.noise_sigma(img)
        assert abs(est - true_sigma) < 0.25 * true_sigma, \
            "σ 估計不準（真值 %.1f，估到 %.2f）" % (true_sigma, est)

    # 同一個 strength 在吵與不吵的兩張圖上，都要保住缺陷且都要降噪
    for true_sigma in (3.0, 12.0):
        img = rng.normal(120.0, true_sigma, (64, 64)).astype(np.float32)
        img[30:33, 30:33] += 45.0
        out = algo_enhance.bilateral(img, 5, strength=1.0)
        amp_in = float(img[30:33, 30:33].mean() - np.median(img))
        amp_out = float(out[30:33, 30:33].mean() - np.median(out))
        assert amp_out > 0.8 * amp_in
        assert float(out[:20, :20].std()) < 0.8 * float(img[:20, :20].std())


def test_enhance_helpers_survive_degenerate_input():
    """全黑、單一值、空圖 —— 不可以 crash，也不可以回 NaN。"""
    for img in (np.zeros((8, 8), np.float32),
                np.full((8, 8), 7.0, np.float32),
                np.zeros((0, 0), np.float32)):
        for out in (algo_enhance.clahe(img),
                    algo_enhance.remove_background(img, 5),
                    algo_enhance.remove_stripes(img, 0),
                    algo_enhance.morph_residual(img, 5),
                    algo_enhance.bilateral(img, 5),
                    algo_enhance.nlm(img, 7)):
            assert out.shape == img.shape
            assert not np.any(np.isnan(out))


# --------------------------------------------------------------------------- #
# 2. 卡片：只加了兩張，其餘走既有卡片的下拉
# --------------------------------------------------------------------------- #
def _run(key: str, ctx: Context, **params) -> Context:
    return get_step(key)().run(ctx, params)


def test_only_two_new_cards_were_added_for_six_new_abilities():
    """「不要開太多卡片」—— 相似的能力要放在同一張卡的下拉裡。"""
    flatten = get_step("flatten").describe()
    methods = {p["name"]: p for p in flatten["params"]}["method"]["choices"]
    # 背景平坦化 / 去條紋（兩個方向）/ top-hat / black-hat = 一張卡五個選項
    assert set(methods) == {"background", "stripes_h", "stripes_v",
                            "bright_spots", "dark_spots"}

    # 邊緣保留去噪塞進既有的 Denoise，不另開卡（F11 Enhance-2 的孤立壞點也是）
    denoise = {p["name"]: p for p in get_step("denoise").describe()["params"]}
    assert set(denoise["method"]["choices"]) == {"median", "gaussian",
                                                 "bilateral", "nlm",
                                                 "hot_pixels"}

    # 雙流運算塞進既有的 Compare 卡，不另開卡
    sub = {p["name"]: p for p in get_step("subtract").describe()["params"]}
    assert set(sub["op"]["choices"]) == {"subtract", "ratio", "max", "min", "mean"}


def test_the_new_cards_are_in_the_enhance_stage_and_visible_in_the_gui():
    from d4t.ui.scope import visible_steps

    for key in ("flatten", "normalize"):
        assert get_step(key).resolve_group() == "enhance"
    keys = [d["key"] for d in visible_steps(
        [get_step(k).describe() for k in ("flatten", "normalize")])]
    assert keys == ["flatten", "normalize"]


@pytest.mark.parametrize("method", ["background", "stripes_h", "stripes_v",
                                    "bright_spots", "dark_spots"])
def test_flatten_card_runs_every_method_on_test_and_ref(method):
    ctx = Context(images={"test": _patch(gradient=40.0),
                          "ref": _patch(gradient=40.0, defect=0.0, seed=2)})
    # 一張卡一條流（F7-18）：兩張圖都要處理就放兩張卡。
    _run("flatten", ctx, streams="test", method=method, size=21)
    _run("flatten", ctx, streams="ref", method=method, size=21)
    for key in ("test", "ref"):
        assert ctx.images[key].dtype == np.float32
        assert ctx.images[key].shape == (64, 64)
        assert not np.any(np.isnan(ctx.images[key]))


def test_flatten_only_touches_its_own_stream():
    ctx = Context(images={"test": _patch(gradient=40.0),
                          "ref": _patch(gradient=40.0, seed=3)})
    before = ctx.images["ref"].copy()
    _run("flatten", ctx, streams="test", method="background")
    assert np.array_equal(ctx.images["ref"], before), "沒接進來的流不可以被動到"
    assert not np.array_equal(ctx.images["test"], before)


def test_local_contrast_card_runs():
    ctx = Context(images={"test": _patch(), "ref": _patch(seed=4)})
    _run("normalize", ctx, method="local", streams="test", clip_limit=3.0, tiles=4)
    assert ctx.images["test"].dtype == np.float32
    assert float(ctx.images["test"].std()) > 0.0


def test_pointing_a_card_at_a_stream_that_does_not_exist_says_so():
    """指到不存在的流是**錯誤**，不是警告 —— 那張卡什麼都沒做，而使用者以為做了。"""
    from d4t.core.pipeline.step import StepError

    ctx = Context(images={"test": _patch()})
    with pytest.raises(StepError) as e:
        _run("flatten", ctx, streams="ghost", method="background")
    assert "ghost" in str(e.value)


@pytest.mark.parametrize("method", ["median", "gaussian", "bilateral", "nlm"])
def test_denoise_card_runs_every_method(method):
    ctx = Context(images={"test": _patch(), "ref": _patch(seed=5)})
    _run("denoise", ctx, streams="test", method=method, ksize=5, strength=1.0)
    assert ctx.images["test"].shape == (64, 64)
    assert not np.any(np.isnan(ctx.images["test"]))


@pytest.mark.parametrize("op,expect", [
    ("subtract", 40.0), ("ratio", 1.0), ("max", 100.0), ("min", 60.0),
    ("mean", 80.0),
])
def test_compare_card_supports_every_two_stream_operation(op, expect):
    a = np.full((8, 8), 100.0, np.float32)
    b = np.full((8, 8), 60.0, np.float32)
    ctx = Context(images={"a": a, "b": b})
    _run("subtract", ctx, a="a", b="b", op=op, out="r")
    got = float(ctx.images["r"].mean())
    if op == "ratio":
        assert got == pytest.approx(100.0 / 60.0, rel=1e-3)
    else:
        assert got == pytest.approx(expect, rel=1e-3)
    assert ctx.images["r"].dtype == np.float32


def test_ratio_never_produces_infinities():
    """inf 會一路帶到分數，最後變成「分數是 nan」的 defect ——
    而使用者完全看不出是哪一步造成的。"""
    ctx = Context(images={"a": np.full((8, 8), 100.0, np.float32),
                          "b": np.zeros((8, 8), np.float32)})
    _run("subtract", ctx, a="a", b="b", op="ratio", out="r")
    assert np.all(np.isfinite(ctx.images["r"]))


def test_subtract_keeps_its_original_behaviour_by_default():
    """既有 recipe 一份都不能被改變行為。

    2026-08-14 起 subtract 的預設 b 是 ``ref``（patch 本來就對齊）——
    新卡走新預設；**舊檔案**（省略 b 的）由 recipe 載入遷移補回
    ``ref_aligned``，行為不變（見 test_recipe 的遷移測試）。"""
    a = np.full((8, 8), 60.0, np.float32)
    b = np.full((8, 8), 100.0, np.float32)
    ctx = Context(images={"test": a, "ref": b})
    _run("subtract", ctx)                       # 全預設（新：b=ref）
    assert float(ctx.images["diff"].mean()) == pytest.approx(40.0)   # absolute


# --------------------------------------------------------------------------- #
# F7-20：正規化的四種做法收成一張卡；參數跟著方法出現／消失
# --------------------------------------------------------------------------- #
def test_normalize_is_one_card_with_every_method_in_the_family():
    """使用者原話：「他們都是正規化，放在一起讓 user 勾選用哪一種即可」。

    每一種方法解決的都是同一個問題（把灰階重新映射好讓兩張圖比得起來），差別只在
    拉伸範圍怎麼決定。卡片庫多一列，使用者就要多讀一段說明才知道該用哪一個 ——
    所以 F11 Enhance-2 的 zscore 也是這張卡的一個選項，不是第五張 Enhance 卡。
    """
    from d4t.core.pipeline import REGISTRY, get_step

    enhance = sorted(k for k, v in REGISTRY.items() if v.group == "enhance")
    assert enhance == ["denoise", "flatten", "normalize", "tone"]
    for gone in ("percentile_norm", "glv_mask_norm", "hist_match",
                 "local_contrast", "brightness_contrast", "gamma", "invert"):
        assert gone not in REGISTRY, gone

    methods = {p.name: p for p in get_step("normalize").params}["method"]
    assert methods.choices == ["percentile", "zscore", "glv_band", "match",
                               "local"]


@pytest.mark.parametrize("method,shown,hidden", [
    ("percentile", ("p_low", "p_high", "range_from"), ("glv_low", "tiles", "reference")),
    ("zscore", ("target_level", "target_spread", "range_from", "use_within"),
     ("p_low", "glv_low", "tiles", "reference")),
    ("glv_band", ("glv_low", "glv_high", "range_from"), ("p_low", "tiles", "reference")),
    ("match", ("reference", "match_method", "use_within"),
     ("p_low", "glv_low", "tiles", "range_from", "target_level")),
    ("local", ("clip_limit", "tiles"),
     ("p_low", "glv_low", "reference", "range_from", "use_within",
      "target_spread")),
])
def test_only_the_parameters_that_apply_are_shown(method, shown, hidden):
    """``show_when``：選了 CLAHE 的時候 ``p_low`` 根本不是這張卡的一部分。

    以前的替代方案是在 help 裡寫「（stripe 方法用不到）」—— 那是一句道歉，
    不是一個設計，而且使用者還是得自己判斷「那它算不算數」。
    """
    from d4t.core.pipeline import get_step

    specs = {p.name: p for p in get_step("normalize").params}
    params = {"method": method}
    for name in shown:
        assert specs[name].visible_for(params) is True, name
    for name in hidden:
        assert specs[name].visible_for(params) is False, name
    # streams / method 本身永遠在
    assert specs["streams"].visible_for(params) is True
    assert specs["method"].visible_for(params) is True


def test_normalize_only_needs_a_ref_when_it_is_matching():
    """``requires_ref`` 跟著方法走，不是跟著卡走。

    用常數的話，rsem route 上只要放了 Normalize 就會被誤判成缺 ref ——
    而那四種方法裡只有一種真的要另一張圖。
    """
    from d4t.core.pipeline import get_step

    cls = get_step("normalize")
    assert cls.resolve_requires_ref(cls.validate_params({"method": "match"})) is True
    for m in ("percentile", "glv_band", "local"):
        assert cls.resolve_requires_ref(cls.validate_params({"method": m})) is False


def test_a_card_processes_every_stream_wired_into_it():
    """F7-19：接幾條就處理幾條，出來也是那幾條。"""
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    ctx = Context(images={"test": _patch(), "ref": _patch(seed=5)})
    before_ref = ctx.images["ref"].copy()
    cls = get_step("normalize")
    assert cls.resolve_writes(cls.validate_params({"streams": "test,ref"})) == \
        ["test", "ref"]
    cls().run(ctx, {"streams": "test,ref"})
    assert not np.array_equal(ctx.images["ref"], before_ref), "ref 也要被處理到"
    assert ctx.images["test"].max() == 255 and ctx.images["ref"].max() == 255


def test_matching_leaves_the_reference_alone_even_if_it_is_listed():
    """把 reference 對齊到它自己是 no-op，但那會讓人以為它被處理過了。"""
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    ctx = Context(images={"test": _patch(), "ref": _patch(seed=9)})
    before = ctx.images["ref"].copy()
    get_step("normalize")().run(
        ctx, {"streams": "test,ref", "method": "match", "reference": "ref"})
    assert np.array_equal(ctx.images["ref"], before)


def test_tone_applies_its_knobs_in_a_fixed_order():
    """亮度／gamma／反相是可以**同時**做的，所以它們是旋鈕不是四選一。

    順序固定（亮度 → gamma/曲線 → 反相），因為可調的話同一組數字會有六種
    結果，而畫面上看不出來是哪一種。
    """
    from d4t.core.steps.tone import (apply_brightness_contrast, apply_gamma,
                                       apply_invert)
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    img = _patch()
    ctx = Context(images={"test": img.copy()})
    get_step("tone")().run(ctx, {"streams": "test", "brightness": 10.0,
                                 "gamma": 0.7, "invert": True})
    expect = apply_invert(apply_gamma(
        apply_brightness_contrast(img, 10.0, 1.0), 0.7))
    assert np.array_equal(ctx.images["test"], expect)
