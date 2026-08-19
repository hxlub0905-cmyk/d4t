"""Tests for d4t.core.algo.subpixel (vendored from MMH cmg_recipe)."""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.algo.subpixel import (
    SubpixelResult,
    aggregate_values,
    compute_sample_xs,
    refine_xedge_subpixel,
    refine_xedge_subpixel_batch,
    refine_xedge_threshold_crossing,
    refine_xedge_threshold_crossing_batch,
    refine_yedge_subpixel,
    refine_yedge_subpixel_batch,
    refine_yedge_threshold_crossing,
    refine_yedge_threshold_crossing_batch,
)

Y_TRUE = 30.4
H = W = 64


@pytest.fixture(scope="module")
def yedge_image():
    """Smooth (sigmoid) horizontal step edge at sub-pixel row Y_TRUE."""
    yy = np.arange(H, dtype=np.float64)
    prof = 30.0 + 200.0 / (1.0 + np.exp(-(yy - Y_TRUE) / 1.5))
    return np.tile(prof[:, None], (1, W)).astype(np.uint8)


@pytest.fixture(scope="module")
def xedge_image(yedge_image):
    """The same edge rotated: vertical step edge at sub-pixel column Y_TRUE."""
    return np.ascontiguousarray(yedge_image.T)


def test_scalar_gradient_recovers_subpixel_edge(yedge_image):
    res = refine_yedge_subpixel(yedge_image, x_center=32, y_guess=30.0)
    assert isinstance(res, SubpixelResult)
    assert res.fallback_reason == ""
    assert abs(res.y_refined - Y_TRUE) < 0.3
    assert res.shift_px == pytest.approx(res.y_refined - 30.0)
    assert res.peak_strength > 0.0
    assert 0.0 <= res.second_peak_ratio < 1.0


def test_scalar_threshold_crossing_recovers_subpixel_edge(yedge_image):
    res = refine_yedge_threshold_crossing(yedge_image, x_center=32, y_guess=30.0)
    assert res.fallback_reason == ""
    assert abs(res.y_refined - Y_TRUE) < 0.3


def test_batch_threshold_crossing_recovers_subpixel_edge(yedge_image):
    xs = list(range(10, 50))
    # smooth_k=1 skips the cumsum smoothing so the batch TC is unbiased
    out = refine_yedge_threshold_crossing_batch(
        yedge_image, xs, y_guess=30.0, smooth_k=1)
    vals = [v for v in out if v is not None]
    assert len(vals) == len(xs)
    assert abs(float(np.mean(vals)) - Y_TRUE) < 0.3


def test_batch_gradient_valid_and_consistent(yedge_image):
    xs = list(range(10, 50))
    out = refine_yedge_subpixel_batch(yedge_image, xs, y_guess=30.0)
    vals = [v for v in out if v is not None]
    assert len(vals) == len(xs)
    # identical columns -> identical refined values
    assert max(vals) - min(vals) < 1e-9
    # stays inside the proximity window of the guess
    assert all(abs(v - 30.0) <= 5.0 for v in vals)
    # out-of-image sample positions come back as None, in order
    out2 = refine_yedge_subpixel_batch(yedge_image, [-5, 32, 999], 30.0)
    assert out2[0] is None and out2[2] is None and out2[1] is not None


def test_flat_profile_sets_fallback_reason():
    flat = np.full((H, W), 50, dtype=np.uint8)
    r1 = refine_yedge_subpixel(flat, x_center=32, y_guess=30.0)
    r2 = refine_yedge_threshold_crossing(flat, x_center=32, y_guess=30.0)
    assert r1.fallback_reason == "flat_profile"
    assert r2.fallback_reason == "flat_profile"
    # fallback returns the guess untouched with zeroed diagnostics
    assert r1.y_refined == 30.0 and r1.shift_px == 0.0
    assert r1.peak_strength == 0.0 and r1.second_peak_ratio == 0.0
    # batch versions signal failure with None
    assert refine_yedge_subpixel_batch(flat, [10, 20], 30.0) == [None, None]
    assert refine_yedge_threshold_crossing_batch(flat, [10, 20], 30.0) == [None, None]


def test_invalid_image_fallback():
    res = refine_yedge_subpixel(None, x_center=5, y_guess=5.0)
    assert res.fallback_reason == "invalid_image"


def test_xedge_wrappers_agree_with_transposed_yedge(yedge_image, xedge_image):
    ry = refine_yedge_subpixel(yedge_image, x_center=32, y_guess=30.0)
    rx = refine_xedge_subpixel(xedge_image, y_center=32, x_guess=30.0)
    assert rx == ry  # NamedTuple equality: identical refined coord + diagnostics

    ty = refine_yedge_threshold_crossing(yedge_image, x_center=32, y_guess=30.0)
    tx = refine_xedge_threshold_crossing(xedge_image, y_center=32, x_guess=30.0)
    assert tx == ty
    assert abs(tx.y_refined - Y_TRUE) < 0.3  # refined X coordinate

    samples = list(range(10, 50))
    by = refine_yedge_subpixel_batch(yedge_image, samples, 30.0)
    bx = refine_xedge_subpixel_batch(xedge_image, samples, 30.0)
    assert bx == by
    cy = refine_yedge_threshold_crossing_batch(yedge_image, samples, 30.0)
    cx = refine_xedge_threshold_crossing_batch(xedge_image, samples, 30.0)
    assert cx == cy


def test_compute_sample_xs():
    assert compute_sample_xs(3, 8, "all") == [3, 4, 5, 6, 7]
    xs = compute_sample_xs(0, 21, 5)
    assert len(xs) == 5
    assert xs[0] == 0 and xs[-1] == 20
    assert xs == sorted(xs)
    assert compute_sample_xs(5, 5, "all") == []
    assert compute_sample_xs(0, 3, 10) == [0, 1, 2]  # N capped at range size


def test_aggregate_values():
    vals = [1.0, 2.0, 3.0, 10.0]
    assert aggregate_values(vals, "median") == 2.5
    assert aggregate_values(vals, "mean") == 4.0
    assert aggregate_values(vals, "min") == 1.0
    assert aggregate_values(vals, "max") == 10.0
    assert aggregate_values(vals, "unknown") == 2.5  # default: median
    assert aggregate_values([], "mean") == 0.0
