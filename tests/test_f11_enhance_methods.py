"""F11 Enhance-2：三個新方法（median 背景、孤立壞點、zscore）。

三個都是**既有卡片的一個下拉選項**，不是新卡片 —— 使用者的問題還是原來那一個
（「背景不平」「這張圖太雜」「兩張圖比不起來」），差別只在願意付什麼代價。

每一個都在回答一個具體的、實測出來的失敗：

| 方法 | 原本那條路壞在哪 |
|---|---|
| `flatten` 的 median 背景 | 高斯是加權平均，缺陷**一定**有一部分被算進背景然後被減掉 |
| `denoise` 的 hot_pixels | median 磨整張圖 —— 只有幾顆壞點時，被磨掉的邊緣正是要拿來量 CD 的 |
| `normalize` 的 zscore | percentile 釘端點，所以「一個灰階代表多少變異」逐張都不同 |
"""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.algo import enhance as algo_enhance
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import get_step
import d4t.core.steps  # noqa: F401 - 註冊卡片
from d4t.core.steps._util import CLIP_FRAC, PAIR_FEATURES


def _ctx(**images) -> Context:
    ctx = Context()
    for k, v in images.items():
        ctx.set_image(k, v)
    return ctx


def _run(key: str, ctx: Context, **params) -> Context:
    return get_step(key)().run(ctx, params)


def _bg_with_defect(amp: float = 60.0, side: int = 4, n: int = 64,
                    seed: int = 2) -> np.ndarray:
    """一張有平滑梯度、雜訊、與一顆亮缺陷的 patch。"""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n]
    img = 110.0 + 0.35 * x + 0.2 * y + rng.normal(0.0, 3.0, (n, n))
    c = n // 2
    img[c:c + side, c:c + side] += amp
    return np.clip(img, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# ⑤ median 背景估計
# --------------------------------------------------------------------------- #
def test_the_gaussian_background_eats_part_of_the_defect_and_median_does_not():
    """**這一支就是這個方法存在的理由**（量出來的，不是推論）。

    同一張圖、同一個 size，只換背景估計法。高斯是加權平均，所以缺陷自己會把它
    位置上的背景估計抬高 —— 減完之後缺陷的振幅少了那一塊。中位數只看排序中間
    那一個，缺陷佔核心面積不到一半就完全影響不到它。
    """
    img = _bg_with_defect(amp=60.0, side=4)
    c = 32
    peak = {}
    for est in ("gaussian", "median"):
        out = _run("flatten", _ctx(test=img.copy()), streams="test",
                   method="background", size=21, keep_level=True,
                   estimator=est)
        arr = np.asarray(out.images["test"], dtype=np.float32)
        # 缺陷區的殘差高度 vs 背景區的殘差高度
        peak[est] = float(arr[c:c + 4, c:c + 4].mean() - np.median(arr))
    assert peak["median"] > peak["gaussian"] * 1.05, peak
    # 而且中位數留下來的振幅要接近真的振幅（高斯明顯短少）
    assert peak["median"] > 0.9 * 60.0, peak
    assert peak["gaussian"] < 0.9 * 60.0, peak


def test_the_median_background_still_removes_the_gradient():
    """留住缺陷不能是「什麼都沒做」—— 梯度該拿掉的還是要拿掉。"""
    img = _bg_with_defect(amp=0.0)
    before = np.asarray(img, dtype=np.float32)
    out = _run("flatten", _ctx(test=img.copy()), streams="test",
               method="background", size=21, keep_level=True,
               estimator="median")
    after = np.asarray(out.images["test"], dtype=np.float32)
    # 左右兩半的亮度差 = 梯度殘留
    def tilt(a):
        return abs(float(a[:, :20].mean() - a[:, -20:].mean()))
    assert tilt(after) < 0.35 * tilt(before), (tilt(before), tilt(after))


def test_median_filtering_works_at_any_kernel_size():
    """cv2 的 float 路只支援 ksize 3/5，而背景核心是 21、31 這種數字。"""
    f = np.linspace(0, 255, 64 * 64, dtype=np.float32).reshape(64, 64)
    for k in (3, 5, 21, 31):
        out = algo_enhance.median_blur_f32(f, k)
        assert out.shape == f.shape and out.dtype == np.float32
        assert np.isfinite(out).all()


def test_a_flat_image_has_no_background_to_estimate():
    out = algo_enhance.median_blur_f32(np.full((16, 16), 7.0, np.float32), 9)
    assert np.allclose(out, 7.0)


def test_the_estimator_only_shows_up_for_the_background_method():
    """去條紋與 top-hat 根本沒有「背景估計法」這件事。"""
    spec = [s for s in get_step("flatten").params if s.name == "estimator"][0]
    assert spec.visible_for({"method": "background"}) is True
    assert spec.visible_for({"method": "stripes_h"}) is False
    assert spec.visible_for({"method": "bright_spots"}) is False


def test_the_default_estimator_keeps_every_existing_recipe_identical():
    """舊 recipe 沒有 `estimator` 這個鍵 —— 它必須還是走高斯那條路。"""
    img = _bg_with_defect()
    old = _run("flatten", _ctx(test=img.copy()), streams="test",
               method="background", size=21, keep_level=True)
    new = _run("flatten", _ctx(test=img.copy()), streams="test",
               method="background", size=21, keep_level=True,
               estimator="gaussian")
    assert np.array_equal(np.asarray(old.images["test"]),
                          np.asarray(new.images["test"]))


# --------------------------------------------------------------------------- #
# ⑥ 孤立壞點
# --------------------------------------------------------------------------- #
def _speckled(n: int = 48, seed: int = 4):
    rng = np.random.default_rng(seed)
    img = np.clip(120.0 + rng.normal(0.0, 5.0, (n, n)), 0, 255).astype(np.uint8)
    bad = [(10, 10), (20, 30), (40, 5)]
    for i, (y, x) in enumerate(bad):
        img[y, x] = 255 if i % 2 == 0 else 0
    return img, bad


def test_it_replaces_the_damaged_pixels_and_nothing_else():
    """**「其餘一個都不動」是這個方法的全部價值**，所以逐位元組比。"""
    img, bad = _speckled()
    out = _run("denoise", _ctx(test=img.copy()), streams="test",
               method="hot_pixels", ksize=3, threshold=4.0)
    arr = np.asarray(out.images["test"])
    changed = np.asarray(np.nonzero(arr != np.asarray(img))).T
    assert sorted(map(tuple, changed.tolist())) == sorted(bad)


def test_it_reports_how_many_it_replaced():
    """調 threshold 時這是唯一看得到的回饋（影像上看不出少了幾顆亮點）。"""
    img, bad = _speckled()
    out = _run("denoise", _ctx(test=img.copy()), streams="test",
               method="hot_pixels", ksize=3, threshold=4.0)
    assert out.features["hot_px_frac"] == pytest.approx(len(bad) / float(img.size))


def test_the_number_is_declared_only_for_this_method():
    """兩種方法問的是不同的問題，所以各報自己那一個。

    「換掉的比例」對平滑法恆等於 1（它動的是每一個畫素），「磨掉幾個 σ」對只換
    三顆畫素的方法趨近於 0 —— 一個永遠是同一個值的欄位只會佔 CSV 的寬度。
    """
    cls = get_step("denoise")
    assert cls.resolve_features({"streams": "test", "method": "hot_pixels"}) == [
        CLIP_FRAC, "hot_px_frac"]
    assert cls.resolve_features({"streams": "test", "method": "median"}) == [
        CLIP_FRAC, "removed_over_noise"]
    # 多流時前綴規則跟其他數字一樣（F10-3），而 pair 那兩個不帶前綴
    assert cls.resolve_features({"streams": "test,ref", "method": "hot_pixels"}) == [
        "test_" + CLIP_FRAC, "test_hot_px_frac",
        "ref_" + CLIP_FRAC, "ref_hot_px_frac"] + list(PAIR_FEATURES)


def test_replacing_a_lot_of_pixels_says_so():
    """門檻壓到 1σ 就不是「孤立壞點」了 —— 那是在吃真的結構，而影像上看不出來。"""
    img, _ = _speckled()
    out = _run("denoise", _ctx(test=img.copy()), streams="test",
               method="hot_pixels", ksize=3, threshold=1.0)
    assert out.features["hot_px_frac"] > 0.005
    said = " ".join(out.meta.get("warnings") or [])
    assert "eating real structure" in said


def test_a_real_defect_survives_the_default_threshold():
    """4σ 的預設值不能把一顆 4x4 的缺陷當成壞點刮掉。"""
    img = _bg_with_defect(amp=60.0, side=4)
    out = _run("denoise", _ctx(test=img.copy()), streams="test",
               method="hot_pixels", ksize=3, threshold=4.0)
    arr = np.asarray(out.images["test"], dtype=np.float32)
    core = arr[32:36, 32:36]
    assert float(core.mean()) > float(np.median(arr)) + 40.0


def test_the_threshold_is_in_units_of_this_image_s_own_noise():
    """同一件事在安靜的 lot 與吵的 lot 上要是同一個字（見 noise_sigma 的理由）。

    兩張圖：同樣的一顆壞點、雜訊差 4 倍。壞點相對於雜訊都是「離譜」，
    所以兩張都要換掉；而**只有**那一顆被換掉。
    """
    for sigma in (2.0, 8.0):
        rng = np.random.default_rng(9)
        img = np.clip(120.0 + rng.normal(0.0, sigma, (48, 48)), 0, 255).astype(np.uint8)
        img[24, 24] = 255
        out = _run("denoise", _ctx(test=img.copy()), streams="test",
                   method="hot_pixels", ksize=3, threshold=4.0)
        arr = np.asarray(out.images["test"])
        assert arr[24, 24] != 255, sigma
        assert np.count_nonzero(arr != np.asarray(img)) == 1, sigma


def test_a_noiseless_image_does_not_get_every_pixel_replaced():
    """σ ≈ 0 的合成圖：沒有那道 1 GLV 的地板，門檻會變 0 而整張圖都算「不一樣」。"""
    img = np.full((32, 32), 100, np.uint8)
    img[5, 5] = 200
    out = _run("denoise", _ctx(test=img.copy()), streams="test",
               method="hot_pixels", ksize=3, threshold=4.0)
    arr = np.asarray(out.images["test"])
    assert np.count_nonzero(arr != np.asarray(img)) == 1


# --------------------------------------------------------------------------- #
# ⑦ zscore
# --------------------------------------------------------------------------- #
def _zs(img, **extra):
    out = _run("normalize", _ctx(test=img.copy()), streams="test",
               method="zscore", **extra)
    return np.asarray(out.images["test"], dtype=np.float32), out


def test_zscore_puts_the_background_and_one_noise_level_where_asked():
    arr, _ = _zs(_bg_with_defect(amp=0.0))
    centre, spread = algo_enhance.robust_level_spread(arr)
    assert centre == pytest.approx(128.0, abs=1.5)
    assert spread == pytest.approx(32.0, rel=0.1)


def test_the_defect_does_not_move_the_scale():
    """**這是 zscore 用中位數/MAD 而不是平均/標準差的理由**（量出來的）。

    平均與標準差會被缺陷帶著跑：一顆 60 GLV、16 畫素的缺陷讓 64x64 patch 的標準差
    從 5.0 變 6.2（24% 是缺陷貢獻的）。那會讓**兩顆大小不同的缺陷被套上不同的
    縮放** —— 正是正規化要消除的東西。
    """
    scales = []
    for amp in (0.0, 60.0, 120.0):
        arr, _ = _zs(_bg_with_defect(amp=amp, side=4))
        scales.append(algo_enhance.robust_level_spread(arr)[1])
    assert max(scales) - min(scales) < 1.0, scales


def test_two_images_with_different_brightness_become_comparable():
    """「兩張圖比得起來」是這個家族的本業，所以要真的比一次。"""
    rng = np.random.default_rng(6)
    a = np.clip(90.0 + rng.normal(0.0, 4.0, (48, 48)), 0, 255).astype(np.uint8)
    b = np.clip(180.0 + rng.normal(0.0, 12.0, (48, 48)), 0, 255).astype(np.uint8)
    ctx = _ctx(test=a, ref=b)
    _run("normalize", ctx, streams="test,ref", method="zscore")
    ta = np.asarray(ctx.images["test"], dtype=np.float32)
    tb = np.asarray(ctx.images["ref"], dtype=np.float32)
    assert abs(float(np.median(ta) - np.median(tb))) < 2.0
    diff = float(np.abs(ta - tb).mean())
    raw = float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())
    assert diff < raw / 2.0, (diff, raw)


def test_zscore_borrows_the_basis_like_the_others():
    """`range_from` 那條路是共用的一份，不是每個方法各寫一次。

    ⚠ 這一條以前還問 ``use_within``（一條 mask 流）。**2026-09-02 那一格拿掉了**
    —— 產得出 mask 流的 ``roi_mask`` 刪了，留著就是一個接不到東西的埠。
    共用的那一份（``_measure_from``）**還在**，它現在共用的是「量哪一張」。
    """
    rng = np.random.default_rng(8)
    a = np.clip(90.0 + rng.normal(0.0, 4.0, (32, 32)), 0, 255).astype(np.uint8)
    b = np.clip(180.0 + rng.normal(0.0, 4.0, (32, 32)), 0, 255).astype(np.uint8)

    own, _ = _zs(a)
    borrowed = np.asarray(_run("normalize", _ctx(test=a.copy(), other=b),
                               streams="test", method="zscore",
                               range_from="other").images["test"],
                          dtype=np.float32)
    assert not np.array_equal(own, borrowed), "借來的基準沒有生效"

    cls = get_step("normalize")
    assert cls.resolve_reads({"streams": "test", "method": "zscore",
                              "range_from": "other"}) == ["test", "other"]
    # 那一格真的不在了 —— 塞進去是硬錯，而遷移正是為了讓舊檔不撞上它。
    with pytest.raises(Exception):
        cls().validate_params({"streams": "test", "method": "zscore",
                               "use_within": "m"})


def test_a_completely_flat_image_is_not_a_division_by_zero():
    """σ = 0 的時候只搬位置、不縮放 —— inf 會一路活到某個量測卡才變 nan。"""
    arr, out = _zs(np.full((16, 16), 77, np.uint8))
    assert np.isfinite(arr).all()
    assert float(arr.mean()) == pytest.approx(128.0, abs=1.0)


def test_opening_the_spread_too_far_flattens_the_tails_and_says_so():
    """代價要講出來，而它已經有一個名字了（`clip_frac`，F11 Enhance-1）。"""
    arr, out = _zs(_bg_with_defect(amp=0.0), target_spread=96.0)
    assert out.features[CLIP_FRAC] > 0.0
