# ---------------------------------------------------------------------------
# Vendored into FlexADC on 2026-07-27.
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

@dataclass
class RoiSnrResult:
    """SNR and supporting statistics for one defect ROI.

    Attributes
    ----------
    snr_signed      : (mu_defect - mu_background) / sigma_background, signed
                      (canonical e-beam definition; negative for dark defects).
    snr_abs         : |snr_signed| clipped to [0, 1e6] (legacy 'snr' value).
    defect_mean/std : Statistics inside the defect rect.
    background_mean/std : Statistics of the surrounding background ring.
    contrast        : |defect_mean - background_mean|.
    contrast_ratio  : defect_mean / background_mean.
    edge_sharpness  : Mean Sobel gradient magnitude inside the defect rect.
    dvi             : Defect Visibility Index = snr_abs * sqrt(|contrast_ratio|).
    """
    snr_signed: float
    snr_abs: float
    defect_mean: float
    defect_std: float
    background_mean: float
    background_std: float
    contrast: float
    contrast_ratio: float
    edge_sharpness: float
    dvi: float


def roi_snr(
    image: np.ndarray,
    rect_px: Tuple[int, int, int, int],
    background_margin: int = 20
) -> Optional[RoiSnrResult]:
    """Calculate SNR for a defect ROI.

    SNR = (mu_defect - mu_background) / sigma_background

    Args:
        image: Grayscale image as numpy array.
        rect_px: Defect region of interest as a pixel-space (x, y, w, h) tuple.
        background_margin: Pixels to expand around ROI for background estimation.

    Returns:
        RoiSnrResult with SNR and related statistics, or None if failed.
    """
    if image is None:
        return None

    h, w = image.shape[:2]
    rx, ry, rw, rh = rect_px

    # Validate ROI bounds
    x1, y1 = max(0, int(rx)), max(0, int(ry))
    x2, y2 = min(w, int(rx) + int(rw)), min(h, int(ry) + int(rh))

    if x2 <= x1 or y2 <= y1:
        return None

    # Extract defect region
    defect_region = image[y1:y2, x1:x2].astype(np.float32)

    if defect_region.size == 0:
        return None

    # Calculate defect statistics with numerical overflow protection
    defect_mean = float(np.clip(np.mean(defect_region), -1e6, 1e6))
    defect_std = float(np.clip(np.std(defect_region), 0, 1e6))

    # Define background region (expanded area around ROI, excluding ROI itself)
    bg_x1 = max(0, x1 - background_margin)
    bg_y1 = max(0, y1 - background_margin)
    bg_x2 = min(w, x2 + background_margin)
    bg_y2 = min(h, y2 + background_margin)

    # Create mask for background (expanded region minus defect region)
    bg_mask = np.zeros((bg_y2 - bg_y1, bg_x2 - bg_x1), dtype=bool)
    bg_mask[:, :] = True

    # Mask out the defect region
    inner_x1 = x1 - bg_x1
    inner_y1 = y1 - bg_y1
    inner_x2 = x2 - bg_x1
    inner_y2 = y2 - bg_y1
    bg_mask[inner_y1:inner_y2, inner_x1:inner_x2] = False

    background_region = image[bg_y1:bg_y2, bg_x1:bg_x2].astype(np.float32)
    background_values = background_region[bg_mask]

    if background_values.size < 10:
        # Not enough background pixels, use whole expanded region
        background_values = background_region.flatten()

    # Calculate background statistics with numerical overflow protection
    background_mean = float(np.clip(np.mean(background_values), -1e6, 1e6))
    background_std = float(np.clip(np.std(background_values), 0, 1e6))

    # Signed SNR via the canonical primitive; absolute SNR keeps the original
    # clipped formula for backward compatibility.
    snr_signed_val = float(np.clip(snr_signed(defect_region, background_values), -1e6, 1e6))
    if background_std < 1e-8 or not np.isfinite(background_std):
        snr_abs = 0.0
    else:
        contrast_value = abs(defect_mean - background_mean)
        snr_abs = float(np.clip(contrast_value / background_std, 0, 1e6))

    # Calculate Contrast Ratio with numerical stability
    if abs(background_mean) > 1e-8 and np.isfinite(background_mean):
        contrast_ratio = float(np.clip(defect_mean / background_mean, -1e6, 1e6))
    else:
        contrast_ratio = 0.0

    # Calculate Edge Sharpness (using Sobel gradient magnitude at ROI boundary)
    try:
        # Get the defect patch for edge analysis
        defect_patch = image[y1:y2, x1:x2]
        if defect_patch.size > 0 and defect_patch.shape[0] >= 3 and defect_patch.shape[1] >= 3:
            sobel_x = cv2.Sobel(defect_patch, cv2.CV_64F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(defect_patch, cv2.CV_64F, 0, 1, ksize=3)
            gradient_mag = np.sqrt(sobel_x ** 2 + sobel_y ** 2)
            edge_sharpness = float(np.clip(np.mean(gradient_mag), 0, 1e6))
        else:
            edge_sharpness = 0.0
    except Exception:
        edge_sharpness = 0.0

    # Calculate DVI (Defect Visibility Index) with numerical protection
    try:
        if contrast_ratio > 0 and np.isfinite(contrast_ratio):
            sqrt_contrast = np.sqrt(abs(contrast_ratio))
            dvi = float(np.clip(snr_abs * sqrt_contrast, 0, 1e6))
        else:
            dvi = float(np.clip(snr_abs, 0, 1e6))
    except (ValueError, OverflowError):
        dvi = float(np.clip(snr_abs, 0, 1e6))

    # Final validation of all return values
    contrast = float(np.clip(abs(defect_mean - background_mean), 0, 1e6))

    return RoiSnrResult(
        snr_signed=snr_signed_val,
        snr_abs=snr_abs,
        defect_mean=defect_mean,
        defect_std=defect_std,
        background_mean=background_mean,
        background_std=background_std,
        contrast=contrast,
        contrast_ratio=contrast_ratio,
        edge_sharpness=edge_sharpness,
        dvi=dvi,
    )


# ---------------------------------------------------------------------------
# Local SNR map (adapted from perspective_combine.compute_snr_map)
# ---------------------------------------------------------------------------

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
