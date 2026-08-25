# ---------------------------------------------------------------------------
# Vendored into d4t on 2026-07-27.
# Source projects/files:
#   - PEAR: pear/core/attributes.py (snr -> snr_signed, the canonical
#     e-beam SNR primitive)
#   - Perspective-Combination (Fusi3): perscomb/core/ebeam_snr.py
#     (calculate_roi_snr -> roi_snr)
#   - Perspective-Combination (Fusi3): perscomb/core/perspective_combine.py
#     (compute_snr_map, _center_gaussian_mask -> center_gaussian_mask)
# Adaptations (agreed friction fixes):
#   - snr_signed(target_pixels, ref_pixels) vendored from PEAR as the single
#     canonical SNR primitive: (mean_target - mean_ref) / std_ref, signed.
#     Other modules must reference this function rather than re-deriving it.
#   - roi_snr takes a plain pixel rect (x, y, w, h) tuple instead of the
#     ebeam_snr.ROIRegion dataclass (intentionally not vendored) and returns
#     a RoiSnrResult dataclass instead of a dict. It reports BOTH the signed
#     SNR (via the snr_signed primitive) and the absolute SNR (snr_abs, the
#     original dict's 'snr' value); all other statistics keep the original
#     formulas (contrast, contrast_ratio, edge_sharpness, dvi are computed
#     exactly as before, with dvi based on the absolute SNR).
#   - compute_snr_map originally returned an undocumented (uint8_map, raw_max)
#     tuple despite an ndarray annotation. It now returns a SnrMapResult
#     dataclass: map_float is the normalized float32 map in [0, 1] (the same
#     values the old uint8 map encoded, before the *255 quantization) and
#     snr_max is the raw pre-normalization SNR maximum. .to_uint8() reproduces
#     the old uint8 output exactly. window_size / clip_sigma / clip_percentile
#     / exclude_border parameters and behavior are unchanged.
#   - Algorithm behavior otherwise unchanged.
# ---------------------------------------------------------------------------
"""SNR metrics for e-beam defect imaging.

Canonical SNR definition (PEAR): ``(mean_target - mean_reference) /
std_reference`` — signed, so a defect darker than its background yields a
negative SNR. :func:`snr_signed` is the single canonical primitive; every
other SNR in this package derives from it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

_EPS = 1e-9


def snr_signed(target_pixels: np.ndarray, ref_pixels: np.ndarray) -> float:
    """E-beam SNR: ``(mean_target - mean_reference) / std_reference``.

    The canonical signed SNR primitive (PEAR definition). Returns 0.0 when
    either pixel set is empty or the reference is flat (std < 1e-9).
    """
    t = np.asarray(target_pixels, dtype=np.float64).ravel()
    r = np.asarray(ref_pixels, dtype=np.float64).ravel()
    if t.size == 0 or r.size == 0:
        return 0.0
    sd = float(r.std())
    if sd < _EPS:
        return 0.0
    return (float(t.mean()) - float(r.mean())) / sd


# ---------------------------------------------------------------------------
# ROI SNR (adapted from ebeam_snr.calculate_roi_snr)
# ---------------------------------------------------------------------------

# NOTE: `roi_snr()`（ROI 對「周邊 margin 背景」的訊噪比）與它的
# `RoiSnrResult` 在 2026-08-21 連同 `roi_snr` 卡一起刪掉了。
# 使用者：「原來的 SNR 那張卡請幫我拿掉整個程式碼刪掉避免混淆 —— 我需要的是
# GL 比對的 SNR」。現在 SNR 只有一個出處：`algo.glv.compare_pixels`，
# 而它的參照是**使用者接的那一塊**（畫布上有線），不是自動長出來的一圈 margin。
#
# ⚠ **2026-08-25：Z-map 卡（`steps/snr_map.py`）刪掉了，這個模組留著。**
# `snr_signed` 是這個 repo 帶正負號慣例的**規範出處** —— GLV 卡的 `snr` 統計量
# 照它做（見 `algo/glv.py`），而 `tests/test_steps.py` 就在斷言它還在。
# `compute_snr_map` 現在只剩 `tests/test_snr.py` 一個呼叫者：那正是這種模組被
# 當成死碼順手清掉的狀態（同 `algo/period.py` / `algo/golden.py` 那條規矩，
# 見 `d4t/ui/scope.py`）—— **要刪它請先把上面那個慣例搬個家。**

@dataclass
class SnrMapResult:
    """Local SNR map result.

    Attributes
    ----------
    map_float : float32 map normalized to [0, 1] (clip-sigma capped, then
                scaled by the clip_percentile value); same values the legacy
                uint8 map encoded, without the *255 quantization.
    snr_max   : Raw (pre-clip, pre-normalization) SNR maximum in sigma units.
    """
    map_float: np.ndarray
    snr_max: float

    def to_uint8(self) -> np.ndarray:
        """Return the legacy 0-255 uint8 rendering of the map."""
        return (np.clip(self.map_float, 0.0, 1.0) * 255).astype(np.uint8)


def compute_snr_map(
    diff_image: np.ndarray,
    window_size: int = 31,
    clip_sigma: float = 3.0,
    clip_percentile: float = 99.5,
    exclude_border: int = 16
) -> SnrMapResult:
    """Compute local SNR map highlighting areas with strong signal.

    Parameters
    ----------
    exclude_border : int
        Pixels within this margin are zeroed before peak detection.
        cv2.filter2D uses BORDER_REFLECT_101 by default, which causes
        artificially low variance (and therefore inflated SNR) near
        image edges. Setting this to >= window_size avoids false peaks.
    """
    if diff_image is None or diff_image.size == 0:
        return SnrMapResult(np.zeros((100, 100), dtype=np.float32), 0.0)

    img_f = diff_image.astype(np.float32)
    if img_f.max() > 1.5:
        img_f = img_f / 255.0

    if window_size % 2 == 0:
        window_size += 1

    kernel = np.ones((window_size, window_size), np.float32) / (window_size * window_size)

    local_mean = cv2.filter2D(img_f, -1, kernel)
    local_sq_mean = cv2.filter2D(img_f ** 2, -1, kernel)
    local_var = local_sq_mean - local_mean ** 2
    local_var = np.maximum(local_var, 1e-6)
    local_std = np.sqrt(local_var)

    global_mean = np.mean(img_f)
    snr = np.abs(local_mean - global_mean) / (local_std + 1e-6)

    # Zero out border region to suppress edge artifacts from reflected padding
    if exclude_border > 0:
        h, w = snr.shape
        snr[:exclude_border, :] = 0
        snr[h - exclude_border:, :] = 0
        snr[:, :exclude_border] = 0
        snr[:, w - exclude_border:] = 0

    snr_clipped = np.clip(snr, 0, clip_sigma)
    if clip_percentile is not None:
        scale = float(np.percentile(snr_clipped, clip_percentile))
    else:
        scale = float(clip_sigma)
    if scale < 1e-6:
        scale = float(clip_sigma)

    # Capture raw SNR max before normalization
    raw_snr_max = float(snr.max())

    snr_normalized = np.clip(snr_clipped / scale, 0, 1).astype(np.float32)

    return SnrMapResult(map_float=snr_normalized, snr_max=raw_snr_max)


# ---------------------------------------------------------------------------
# Center ROI Gaussian mask
# ---------------------------------------------------------------------------

def center_gaussian_mask(shape: Tuple[int, int], sigma_ratio: float = 0.35) -> np.ndarray:
    """Return a Gaussian weight mask centered on the image.

    Parameters
    ----------
    shape : (H, W)
    sigma_ratio : fraction of min(H, W) used as Gaussian sigma (default 0.35)

    Returns
    -------
    float32 array in [0, 1], peak = 1.0 at image center.
    """
    H, W = shape
    cy, cx = H / 2.0, W / 2.0
    sigma = min(H, W) * sigma_ratio
    Y, X = np.ogrid[:H, :W]
    mask = np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2.0 * sigma ** 2))
    return mask.astype(np.float32)
