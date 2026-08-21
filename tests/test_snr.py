"""Tests for d4t.core.algo.snr (vendored 2026-07-27).

⚠ `roi_snr()`（ROI 對周邊 margin 背景）與它的三支測試在 2026-08-21 連同
`roi_snr` 卡一起刪掉了 —— 使用者：「原來的 SNR 那張卡請幫我拿掉整個程式碼
刪掉避免混淆，我需要的是 GL 比對的 SNR」。這一份剩下的是 Z-map 用的那幾支，
以及帶正負號慣例的規範出處 `snr_signed`。
"""
from __future__ import annotations

import numpy as np

from d4t.core.algo.snr import (
    SnrMapResult,
    center_gaussian_mask,
    compute_snr_map,
    snr_signed,
)

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
