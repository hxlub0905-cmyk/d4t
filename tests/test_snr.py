"""Tests for flexadc.core.algo.snr (vendored 2026-07-27)."""
from __future__ import annotations

import numpy as np

from flexadc.core.algo.snr import (
    RoiSnrResult,
    SnrMapResult,
    center_gaussian_mask,
    compute_snr_map,
    roi_snr,
    snr_signed,
)


def _image_with_patch(bg_mean: float, patch_value: float, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.clip(rng.normal(bg_mean, 5.0, size=(120, 120)), 0, 255)
    img[40:50, 40:50] = patch_value
    return img.astype(np.float32)


def test_snr_signed_primitive():
    rng = np.random.default_rng(3)
    ref = rng.normal(50.0, 5.0, size=500)
    target = np.full(100, 60.0)
    val = snr_signed(target, ref)
    assert 1.0 < val < 3.0  # (60-50)/5 = 2 nominal

    # Dark target -> negative
    assert snr_signed(np.full(100, 40.0), ref) < 0

    # Flat reference or empty inputs -> 0.0
    assert snr_signed(target, np.full(100, 50.0)) == 0.0
    assert snr_signed(np.array([]), ref) == 0.0


def test_roi_snr_bright_on_dark_positive():
    img = _image_with_patch(bg_mean=50.0, patch_value=150.0)
    res = roi_snr(img, (40, 40, 10, 10), background_margin=15)
    assert isinstance(res, RoiSnrResult)
    assert res.snr_signed > 5.0
    assert res.snr_abs > 5.0
    assert abs(res.snr_abs - abs(res.snr_signed)) < 1e-3
    assert res.defect_mean > res.background_mean
    assert res.contrast > 50.0
    assert res.contrast_ratio > 1.5
    assert res.dvi > 0.0
    assert res.edge_sharpness >= 0.0


def test_roi_snr_dark_on_bright_negative():
    img = _image_with_patch(bg_mean=200.0, patch_value=20.0)
    res = roi_snr(img, (40, 40, 10, 10), background_margin=15)
    assert res.snr_signed < -5.0
    assert res.snr_abs > 5.0
    assert abs(res.snr_abs - abs(res.snr_signed)) < 1e-3
    assert res.defect_mean < res.background_mean


def test_roi_snr_invalid_rect_returns_none():
    img = _image_with_patch(50.0, 150.0)
    assert roi_snr(None, (0, 0, 10, 10)) is None
    assert roi_snr(img, (200, 200, 10, 10)) is None  # fully outside


def _diff_with_blob(seed: int = 9):
    """Flat noise plus a plateau blob wider than the SNR window.

    The local-SNR formula divides by the local std, so a blob narrower than
    the window inflates its own denominator; a plateau larger than the window
    keeps the window at the blob center noise-only and yields a strong peak.
    """
    rng = np.random.default_rng(seed)
    diff = 0.5 + rng.normal(0.0, 0.02, size=(200, 200)).astype(np.float32)
    yy, xx = np.mgrid[:200, :200]
    disk = ((xx - 120) ** 2 + (yy - 80) ** 2) <= 12 ** 2
    diff[disk] += 0.3
    return np.clip(diff, 0, 1).astype(np.float32), (120, 80)


def test_snr_map_peak_at_planted_blob():
    diff, (bx, by) = _diff_with_blob()
    res = compute_snr_map(diff, window_size=15, clip_sigma=3.0,
                          clip_percentile=None, exclude_border=16)
    assert isinstance(res, SnrMapResult)
    assert res.map_float.dtype == np.float32
    assert res.map_float.shape == diff.shape
    assert res.map_float.min() >= 0.0 and res.map_float.max() <= 1.0
    assert res.snr_max > 3.0

    py, px = np.unravel_index(int(np.argmax(res.map_float)), res.map_float.shape)
    assert abs(px - bx) <= 8
    assert abs(py - by) <= 8

    # Border must be zeroed
    assert float(res.map_float[:16, :].max()) == 0.0
    assert float(res.map_float[:, -16:].max()) == 0.0


def test_snr_map_result_to_uint8_range():
    diff, _ = _diff_with_blob()
    res = compute_snr_map(diff)  # default params incl. clip_percentile=99.5
    u8 = res.to_uint8()
    assert u8.dtype == np.uint8
    assert u8.shape == diff.shape
    assert int(u8.min()) == 0
    assert int(u8.max()) == 255  # percentile scaling saturates the peak
    # Quantization consistency with the float map
    np.testing.assert_array_equal(
        u8, (np.clip(res.map_float, 0, 1) * 255).astype(np.uint8))


def test_snr_map_empty_input():
    res = compute_snr_map(np.array([]))
    assert res.map_float.shape == (100, 100)
    assert res.snr_max == 0.0
    assert res.to_uint8().max() == 0


def test_center_gaussian_mask():
    mask = center_gaussian_mask((51, 81))
    assert mask.dtype == np.float32
    assert mask.shape == (51, 81)
    assert mask.min() >= 0.0 and mask.max() <= 1.0
    # Peak at the image center
    py, px = np.unravel_index(int(np.argmax(mask)), mask.shape)
    assert abs(py - 25) <= 1 and abs(px - 40) <= 1
