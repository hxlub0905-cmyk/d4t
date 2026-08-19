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
