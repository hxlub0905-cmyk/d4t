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
#   - ADDED (F11 Enhance-1): every method takes an optional `mask`. The
#     statistics (mean/std, percentiles, histograms) are then measured from
#     the masked pixels only, while the resulting mapping is still applied to
#     the WHOLE image -- same split as normalize's `use_within`, and for the
#     same reason (see `_masked` below). Passing mask=None reproduces the
#     vendored behaviour byte for byte.
#   - Algorithm behavior otherwise unchanged.
# ---------------------------------------------------------------------------
"""Histogram matching of grayscale SEM images (8-bit and 16-bit).

Match a source image's brightness/contrast to a reference image using one of
three methods, selectable through the ``MATCH_FN`` dispatch table:

- ``"exact"``      : CDF-inversion exact histogram matching.
- ``"linear"``     : mean/std shift-and-scale (preserves histogram shape).
- ``"percentile"`` : P2/P98 linear stretch (robust to outliers).
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def _masked(img: np.ndarray, mask: Optional[np.ndarray]) -> np.ndarray:
    """量統計用的那群像素（``mask`` 為 None＝整張圖）。

    為什麼「量」與「套用」要分開（跟 ``normalize`` 的 ``use_within`` 同一個理由）
    ------------------------------------------------------------------------
    一張 patch 上「背景」的面積是隨裁切浮動的 —— 64px 的 patch 裡一根 Metal Gate
    進出畫面就是 12% 的面積差。拿整張圖的統計去對齊亮度，同一片 EPI 只因為隔壁
    多了一根 MG，對齊完就變一個值。mask 讓「拿來對齊的那群像素」跨 patch 是同一
    種圖案。

    **套用永遠是整張圖**：mask 外的像素也要跟著同一個映射走，否則影像會在 mask
    邊界上出現一道人工的階梯 —— 那道階梯會被下游當成邊緣訊號。
    """
    a = np.asarray(img)
    if mask is None:
        return a
    m = np.asarray(mask)
    if m.shape[:2] != a.shape[:2]:
        return a
    sel = a[m > 0]
    return sel if sel.size else a


def match_histogram_exact(source: np.ndarray, reference: np.ndarray,
                          mask: Optional[np.ndarray] = None) -> np.ndarray:
    """CDF-based exact histogram matching.

    Maps the source histogram to match the reference histogram exactly
    via cumulative distribution function inversion.
    Supports 8-bit and 16-bit grayscale.

    ``mask``: build both histograms from the masked pixels only; the resulting
    look-up table is still applied to every pixel (see :func:`_masked`).
    """
    src_dtype = source.dtype
    max_val = 65536 if src_dtype == np.uint16 else 256

    src_hist, _ = np.histogram(_masked(source, mask).flatten(),
                               bins=max_val, range=(0, max_val))
    ref_hist, _ = np.histogram(_masked(reference, mask).flatten(),
                               bins=max_val, range=(0, max_val))

    src_cdf = src_hist.cumsum().astype(np.float64)
    ref_cdf = ref_hist.cumsum().astype(np.float64)
    src_cdf /= src_cdf[-1]
    ref_cdf /= ref_cdf[-1]

    mapping = np.interp(src_cdf, ref_cdf, np.arange(max_val)).astype(src_dtype)
    return mapping[source]


def match_histogram_linear(source: np.ndarray, reference: np.ndarray,
                           mask: Optional[np.ndarray] = None) -> np.ndarray:
    """Linear normalisation — shift & scale so mean/std match reference.

    Preserves the original histogram *shape* while aligning brightness
    and contrast.  Most natural-looking result for SEM images.

    ``mask``: measure mean/std from the masked pixels only; the shift-and-scale
    is still applied to every pixel (see :func:`_masked`).
    """
    src_dtype = source.dtype
    max_val = 65535 if src_dtype == np.uint16 else 255

    src_f = source.astype(np.float64)
    ref_f = reference.astype(np.float64)

    src_stat = _masked(src_f, mask)
    ref_stat = _masked(ref_f, mask)
    s_mean, s_std = src_stat.mean(), src_stat.std()
    r_mean, r_std = ref_stat.mean(), ref_stat.std()

    if s_std < 1e-6:
        return source.copy()

    result = (src_f - s_mean) * (r_std / s_std) + r_mean
    return np.clip(result, 0, max_val).astype(src_dtype)


def match_histogram_percentile(source: np.ndarray, reference: np.ndarray,
                               low: float = 2.0, high: float = 98.0,
                               mask: Optional[np.ndarray] = None) -> np.ndarray:
    """Percentile-based linear stretch.

    Maps the [P_low, P_high] range of the source to match that of the
    reference.  More robust to outliers than mean/std.

    ``mask``: take both percentile pairs from the masked pixels only; the
    stretch is still applied to every pixel (see :func:`_masked`).
    """
    src_dtype = source.dtype
    max_val = 65535 if src_dtype == np.uint16 else 255

    src_f = source.astype(np.float64)
    ref_f = reference.astype(np.float64)

    s_lo, s_hi = np.percentile(_masked(src_f, mask), [low, high])
    r_lo, r_hi = np.percentile(_masked(ref_f, mask), [low, high])

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
