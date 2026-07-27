# ---------------------------------------------------------------------------
# Vendored into FlexADC on 2026-07-27.
# Source project: Perspective-Combination (Fusi3)
# Source file:    perscomb/core/perspective_combine.py
#                 (functions _normalize_image, _percentile_range,
#                  _normalize_image_with_range, _percentile_range_glv_masked,
#                  constant _GLV_MASK_MIN_PIXELS)
# Adaptations:
#   - Leading underscores dropped from function names (public API).
#   - _GLV_MASK_MIN_PIXELS exported as GLV_MASK_MIN_PIXELS.
#   - No Qt / UI dependencies (source module had none in these functions).
#   - Algorithm behavior unchanged.
# ---------------------------------------------------------------------------
"""Robust percentile-based image normalization primitives.

All functions operate on grayscale ndarrays and map intensities into the
[0, 1] float range using percentile anchoring (default P2/P98), optionally
restricted to a GLV (gray-level value) band so that the normalization scale
is anchored to a specific pattern's brightness distribution.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

# Minimum masked pixels required; fall back to full-image if below.
GLV_MASK_MIN_PIXELS = 50


def normalize_image(img: np.ndarray) -> np.ndarray:
    """Normalize image to 0-1 float range using robust percentile scaling."""
    if img is None or img.size == 0:
        return img

    img_f = img.astype(np.float32)
    p2, p98 = np.percentile(img_f, [2, 98])
    rng = p98 - p2
    if rng < 1e-6:
        rng = 1.0

    normalized = (img_f - p2) / rng
    return np.clip(normalized, 0, 1)


def percentile_range(img: np.ndarray, low: float = 2.0, high: float = 98.0) -> Tuple[float, float]:
    """Return percentile range for normalization."""
    if img is None or img.size == 0:
        return 0.0, 1.0
    img_f = img.astype(np.float32)
    p_low, p_high = np.percentile(img_f, [low, high])
    if (p_high - p_low) < 1e-6:
        p_high = p_low + 1.0
    return float(p_low), float(p_high)


def normalize_image_with_range(img: np.ndarray, p2: float, p98: float) -> np.ndarray:
    """Normalize image to 0-1 using provided percentile range."""
    if img is None or img.size == 0:
        return img
    rng = p98 - p2
    if rng < 1e-6:
        rng = 1.0
    normalized = (img.astype(np.float32) - p2) / rng
    return np.clip(normalized, 0, 1)


def percentile_range_glv_masked(
    img: np.ndarray,
    glv_low: int,
    glv_high: int,
    low: float = 2.0,
    high: float = 98.0,
) -> Tuple[float, float]:
    """Return P2/P98 computed only from pixels whose value falls in [glv_low, glv_high].

    Statistics are derived exclusively from pixels inside the specified GLV range
    (e.g. MG: 110-145, EPI: 200-255) so that the normalization scale is anchored
    to the brightness distribution of that specific pattern, not the full image.

    If fewer than GLV_MASK_MIN_PIXELS pixels satisfy the mask, the function
    falls back to full-image percentile_range to avoid degenerate results.

    Args:
        img:      Input image (float32, values 0-255, already inverted if needed).
        glv_low:  Lower bound of GLV mask range (inclusive, 0-255).
        glv_high: Upper bound of GLV mask range (inclusive, 0-255).
        low:      Low percentile (default 2.0).
        high:     High percentile (default 98.0).

    Returns:
        (p_low, p_high) computed from the masked pixel subset.
    """
    if img is None or img.size == 0:
        return 0.0, 1.0

    img_f = img.astype(np.float32)
    mask = (img_f >= float(glv_low)) & (img_f <= float(glv_high))
    masked_pixels = img_f[mask]

    if masked_pixels.size < GLV_MASK_MIN_PIXELS:
        # Not enough pixels in the specified range — fall back to full-image percentile.
        return percentile_range(img_f, low, high)

    p_low, p_high = np.percentile(masked_pixels, [low, high])
    if (p_high - p_low) < 1e-6:
        p_high = p_low + 1.0
    return float(p_low), float(p_high)
