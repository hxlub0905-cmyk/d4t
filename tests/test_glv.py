"""Tests for d4t.core.algo.glv (vendored from PEAR)."""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.algo.glv import (
    GLV_STATS,
    ROI,
    default_metrics,
    glv_stats,
    glv_value,
    group_snr,
    metric_formula,
    metric_label,
    pixel_hist,
    quantile_of,
    roi_patch,
    summarize,
)


@pytest.fixture()
def patch():
    rng = np.random.default_rng(1234)
    return rng.integers(0, 256, size=(20, 30)).astype(np.uint8)


def test_glv_stats_known_array(patch):
    f = patch.astype(np.float64).ravel()
    s = glv_stats(patch)
    assert set(s) == set(GLV_STATS)
    assert s["glv_mean"] == pytest.approx(f.mean())
    assert s["glv_median"] == pytest.approx(np.median(f))
    assert s["glv_q25"] == pytest.approx(np.percentile(f, 25))
    assert s["glv_q75"] == pytest.approx(np.percentile(f, 75))
    assert s["glv_std"] == pytest.approx(f.std())
    assert s["glv_min"] == pytest.approx(f.min())
    assert s["glv_max"] == pytest.approx(f.max())


def test_dynamic_quantile_glv_q30(patch):
    f = patch.astype(np.float64).ravel()
    assert quantile_of("glv_q30") == 30
    assert quantile_of("glv_mean") is None
    assert quantile_of("glv_qxx") is None
    assert glv_value(patch, "glv_q30") == pytest.approx(np.percentile(f, 30))
    assert metric_label("glv_q30") == "GLV Q30"
    assert metric_formula("glv_q30") == "30th percentile"
    # fixed ids still resolve through the fixed tables
    assert metric_label("glv_mean") == "GLV mean"
    assert metric_formula("glv_mean") == "mean(gray)"
    # unknown id falls through untouched
    assert metric_label("bogus") == "bogus"
    assert glv_value(patch, "bogus") == 0.0


def test_empty_patch_guards():
    empty = np.array([], dtype=np.uint8)
    assert glv_value(empty, "glv_mean") == 0.0
    assert glv_value(empty, "glv_q30") == 0.0
    assert all(v == 0.0 for v in glv_stats(empty).values())
    counts, edges = pixel_hist(empty, bins=16)
    assert counts.sum() == 0 and len(edges) == 17
    s = summarize(np.array([]))
    assert s["n"] == 0 and s["mean"] == 0.0


def test_roi_patch_clipping_and_outside():
    img = np.arange(100, dtype=np.uint8).reshape(10, 10)
    p = roi_patch(img, (2, 3, 4, 5))
    assert p.shape == (5, 4)
    assert p[0, 0] == img[3, 2]
    # partially outside -> clipped
    p2 = roi_patch(img, (-2, -2, 4, 4))
    assert p2.shape == (2, 2)
    # fully outside -> None
    assert roi_patch(img, (50, 50, 5, 5)) is None
    assert roi_patch(img, (0, 0, 0, 0)) is None


def test_group_snr_signed_convention():
    img = np.full((40, 40), 100, dtype=np.float64)
    rng = np.random.default_rng(0)
    img += rng.normal(0, 5, img.shape)
    img[5:15, 5:15] += 60.0    # bright target region
    rois = [
        ROI(1, "g", (5, 5, 10, 10)),     # target
        ROI(2, "g", (25, 5, 10, 10)),
        ROI(3, "g", (5, 25, 10, 10)),
        ROI(4, "g", (25, 25, 10, 10)),
    ]
    s = group_snr(img, rois, target_rid=1)
    assert s is not None
    # manual (mu_T - mu_R) / sigma_R over pooled reference pixels
    tp = img[5:15, 5:15]
    ref = np.concatenate([img[5:15, 25:35].ravel(), img[25:35, 5:15].ravel(),
                          img[25:35, 25:35].ravel()])
    expect = (tp.mean() - ref.mean()) / ref.std()
    assert s == pytest.approx(expect)
    assert s > 0  # brighter target -> positive (signed convention)
    # darker target -> negative
    img2 = img.copy()
    img2[5:15, 5:15] -= 120.0
    assert group_snr(img2, rois, target_rid=1) < 0
    # guards: no target / no reference
    assert group_snr(img, rois, target_rid=99) is None
    assert group_snr(img, [rois[0]], target_rid=1) is None


def test_default_metrics():
    assert default_metrics() == ["glv_mean", "glv_median"]


# --------------------------------------------------------------------------- #
# F18（2026-08-21）：robust／形狀／計數那三群
# --------------------------------------------------------------------------- #
def test_robust_and_shape_metrics_match_their_formulas(patch):
    """新的每一顆都要**等於它自己 tooltip 上寫的那條公式**。

    這些值會被打進分數表達式，所以「大概是那個意思」不夠 —— 而 MAD 特別
    值得釘住：文獻上常見的是 1.4826×MAD（拿來估 σ 的那個），d4t 用的是
    **原始的** MAD，因為它要給製程工程師讀成「典型偏離中位數幾階灰階」。
    """
    f = patch.astype(np.float64).ravel()
    z = (f - f.mean()) / f.std()

    assert glv_value(patch, "glv_mad") == pytest.approx(
        np.median(np.abs(f - np.median(f))))
    assert glv_value(patch, "glv_iqr") == pytest.approx(
        np.percentile(f, 75) - np.percentile(f, 25))
    assert glv_value(patch, "glv_skew") == pytest.approx((z ** 3).mean())
    assert glv_value(patch, "glv_kurt") == pytest.approx((z ** 4).mean() - 3.0)
    assert glv_value(patch, "glv_above128") == pytest.approx((f > 128).mean())
    assert glv_value(patch, "glv_sat_frac") == pytest.approx(
        ((f <= 0) | (f >= 255)).mean())

    # 熵：0..255 每一階一個 bin，單位是 bit（所以 8 bit 的均勻分布 = 8）
    flat_uniform = np.arange(256, dtype=np.uint8)
    assert glv_value(flat_uniform, "glv_entropy") == pytest.approx(8.0)


def test_trimmed_mean_actually_drops_the_outlier():
    """修剪平均要真的把兩端丟掉 —— 這是它存在的唯一理由。"""
    base = np.full(100, 100.0)
    base[0] = 255.0                       # 一顆 hot pixel
    assert glv_value(base, "glv_mean") > 101.0
    assert glv_value(base, "glv_trim10") == pytest.approx(100.0)
    # 0% = 不修剪，逐字等於平均（邊界不要特例化成別的東西）
    assert glv_value(base, "glv_trim0") == pytest.approx(base.mean())


def test_bimodality_separates_one_hill_from_two():
    """`glv_bimodality` 是拿來自檢的：ROI 裡混了兩種材質時要看得出來。"""
    rng = np.random.default_rng(7)
    one_hill = rng.normal(120, 12, 4000)
    two_hills = np.concatenate([rng.normal(70, 8, 2000),
                                rng.normal(180, 8, 2000)])
    # 0.555 是均勻分布的值，慣例上以它當「像是兩座山」的線
    assert glv_value(one_hill, "glv_bimodality") < 0.555
    assert glv_value(two_hills, "glv_bimodality") > 0.555


def test_a_flat_or_empty_patch_never_produces_nan():
    """整塊同一個值是**正常**的（飽和的 patch 上很常見），不能毒到整列特徵。

    鐵則 7 的算式版：單顆出錯不得殺掉整批，而一個 NaN 進了分數表達式就是
    那種「跑得完、有數字、而且是錯的」。
    """
    for patch_ in (np.full((8, 8), 40.0), np.array([], dtype=np.uint8)):
        for mid in ("glv_std", "glv_mad", "glv_iqr", "glv_skew", "glv_kurt",
                    "glv_entropy", "glv_bimodality", "glv_sat_frac",
                    "glv_trim10", "glv_above128"):
            v = glv_value(patch_, mid)
            assert np.isfinite(v), "%s on a flat/empty patch gave %r" % (mid, v)
            # 熵在全平的時候是 0，不是 -0.0（CSV 上的 "-0.0" 讀起來像個負的量）
            assert not (v == 0.0 and np.copysign(1.0, v) < 0), mid


def test_the_numbered_ids_refuse_a_number_that_makes_no_sense():
    """``glv_trim60``（兩端各去 60%）不是打錯字就是誤解，兩者都要擋。"""
    from d4t.core.algo.glv import above_of, trim_of

    assert trim_of("glv_trim10") == 10
    assert trim_of("glv_trim49") == 49
    assert trim_of("glv_trim60") is None      # 兩端加起來超過 100%
    assert trim_of("glv_trimx") is None
    assert above_of("glv_above200") == 200
    assert above_of("glv_above300") is None   # 灰階只到 255
    assert above_of("glv_mean") is None
    assert metric_label("glv_trim10") == "GLV trimmed mean 10%"
    assert metric_formula("glv_above200") == "share of pixels with gray > 200"


# --------------------------------------------------------------------------- #
# 逐框比較的分數（F31）—— leave-one-out 的快路要跟暴力版逐位元組相同
# --------------------------------------------------------------------------- #
def test_odd_box_scores_match_the_brute_force_leave_one_out():
    """O(N log N) 的分組算法對上 `np.delete` 的逐格暴力版，逐位元組相同。

    重複值、奇偶長度、常數陣列都要過 —— leave-one-out 中位數的位移規則
    正是在這些邊界上寫錯的。
    """
    from d4t.core.algo.glv import odd_box_scores

    rng = np.random.default_rng(7)
    cases = [rng.normal(100, 5, n) for n in (2, 3, 4, 5, 10, 101)]
    cases += [rng.choice([1.0, 2.0, 3.5, 7.0, 100.0], size=n)
              for n in (4, 9, 50)]
    cases += [np.full(6, 42.0)]
    for v in cases:
        score, base, spread = odd_box_scores(v)
        for i in range(v.size):
            others = np.delete(v, i)
            b = float(np.median(others))
            s = max(1.4826 * float(np.median(np.abs(others - b))), 1.0)
            assert base[i] == b
            assert spread[i] == s          # 已含地板
            assert score[i] == abs(float(v[i]) - b) / s


def test_odd_box_scores_needs_two_boxes():
    from d4t.core.algo.glv import odd_box_scores

    for v in ([], [5.0]):
        score, base, spread = odd_box_scores(v)
        assert score.size == base.size == spread.size == 0


def test_the_spread_floor_is_one_gray_level():
    """全同的其他格 → spread 踩地板 1（灰階是量化的），score 不爆掉。"""
    from d4t.core.algo.glv import odd_box_scores

    score, _base, spread = odd_box_scores([100.0, 100.0, 100.0, 160.0])
    assert spread[3] == 1.0
    assert score[3] == 60.0


def test_robust_spread_matches_its_formula():
    from d4t.core.algo.glv import robust_spread

    v = np.array([1.0, 2.0, 3.0, 4.0, 100.0])
    med = np.median(v)
    assert robust_spread(v) == pytest.approx(
        1.4826 * np.median(np.abs(v - med)))
    assert robust_spread([7.0]) == 0.0
