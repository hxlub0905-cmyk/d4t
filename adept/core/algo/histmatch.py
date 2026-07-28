# ---------------------------------------------------------------------------
# Vendored into ADEPT on 2026-07-27.
# Source project: Perspective-Combination (Fusi3)
# Source file:    histogram_match_tool.py (pure-core block, lines ~45-166:
#                 match_histogram_exact, match_histogram_linear,
#                 match_histogram_percentile, _MATCH_FN, compute_histogram,
#                 image_stats)
# Adaptations:
#   - Qt (PySide6) and matplotlib imports removed; only the pure-numpy core
#     is vendored. UI method-label constants dropped.
#   - Dispatch table renamed _MATCH_FN -> MATCH_FN and re-keyed by short
#     method ids: "exact", "linear", "percentile" (was UI display strings).
#   - Algorithm behavior unchanged.
# ---------------------------------------------------------------------------
"""Histogram matching of grayscale SEM images (8-bit and 16-bit).

Match a source image's brightness/contrast to a reference image using one of
three methods, selectable through the ``MATCH_FN`` dispatch table:

- ``"exact"``      : CDF-inversion exact histogram matching.
- ``"linear"``     : mean/std shift-and-scale (preserves histogram shape).
- ``"percentile"`` : P2/P98 linear stretch (robust to outliers).
"""
from __future__ import annotations

from typing import Tuple

import numpy as np


def match_histogram_exact(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """CDF-based exact histogram matching.

    Maps the source histogram to match the reference histogram exactly
    via cumulative distribution function inversion.
    Supports 8-bit and 16-bit grayscale.
    """
    src_dtype = source.dtype
    max_val = 65536 if src_dtype == np.uint16 else 256

    src_hist, _ = np.histogram(source.flatten(), bins=max_val, range=(0, max_val))
    ref_hist, _ = np.histogram(reference.flatten(), bins=max_val, range=(0, max_val))

    src_cdf = src_hist.cumsum().astype(np.float64)
    ref_cdf = ref_hist.cumsum().astype(np.float64)
    src_cdf /= src_cdf[-1]
    ref_cdf /= ref_cdf[-1]

    mapping = np.interp(src_cdf, ref_cdf, np.arange(max_val)).astype(src_dtype)
    return mapping[source]


def match_histogram_linear(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Linear normalisation — shift & scale so mean/std match reference.

    Preserves the original histogram *shape* while aligning brightness
    and contrast.  Most natural-looking result for SEM images.
    """
    src_dtype = source.dtype
    max_val = 65535 if src_dtype == np.uint16 else 255

    src_f = source.astype(np.float64)
    ref_f = reference.astype(np.float64)

    s_mean, s_std = src_f.mean(), src_f.std()
    r_mean, r_std = ref_f.mean(), ref_f.std()

    if s_std < 1e-6:
        return source.copy()

    result = (src_f - s_mean) * (r_std / s_std) + r_mean
    return np.clip(result, 0, max_val).astype(src_dtype)


def match_histogram_percentile(source: np.ndarray, reference: np.ndarray,
                               low: float = 2.0, high: float = 98.0) -> np.ndarray:
    """Percentile-based linear stretch.

    Maps the [P_low, P_high] range of the source to match that of the
    reference.  More robust to outliers than mean/std.
    """
    src_dtype = source.dtype
    max_val = 65535 if src_dtype == np.uint16 else 255

    src_f = source.astype(np.float64)
    ref_f = reference.astype(np.float64)

    s_lo, s_hi = np.percentile(src_f, [low, high])
    r_lo, r_hi = np.percentile(ref_f, [low, high])

    if (s_hi - s_lo) < 1e-6:
        return source.copy()

    scale = (r_hi - r_lo) / (s_hi - s_lo)
    result = (src_f - s_lo) * scale + r_lo
    return np.clip(result, 0, max_val).astype(src_dtype)


# Dispatch table: method id -> matching function
MATCH_FN = {
    "exact": match_histogram_exact,
    "linear": match_histogram_linear,
    "percentile": match_histogram_percentile,
}


def compute_histogram(image: np.ndarray, bins: int = 256) -> Tuple[np.ndarray, np.ndarray]:
    """Return (counts, bin_edges) for a grayscale image."""
    max_val = 65536 if image.dtype == np.uint16 else 256
    counts, edges = np.histogram(image.flatten(), bins=bins, range=(0, max_val))
    return counts, edges


def image_stats(image: np.ndarray) -> dict:
    """Compute summary statistics for a grayscale image."""
    flat = image.astype(np.float64).ravel()
    p2, p50, p98 = np.percentile(flat, [2, 50, 98])
    return {
        "mean": flat.mean(),
        "std": flat.std(),
        "min": flat.min(),
        "max": flat.max(),
        "P2": p2,
        "median": p50,
        "P98": p98,
    }
