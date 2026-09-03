# Vendored into d4t on 2026-07-27.
# Source project: MMH — src/core/recipes/cmg_recipe.py (generic sub-pixel
#   edge-refinement machinery ONLY; the CMG recipe/pipeline classes were
#   NOT vendored).
# Vendored functions (public names, leading underscore dropped):
#   gaussian_filter1d, gaussian_filter1d_2d, smooth_strip_2d, extract_strip,
#   refine_yedge_threshold_crossing_batch, refine_yedge_subpixel_batch,
#   refine_yedge_threshold_crossing, refine_yedge_subpixel,
#   SubpixelResult, compute_sample_xs, aggregate_values
# Adaptations:
#   - Renamed _SubpixelResult -> SubpixelResult and made every extracted
#     helper public (underscore prefixes dropped).
#   - Also vendored the scalar refine_yedge_subpixel /
#     refine_yedge_threshold_crossing (they define the SubpixelResult
#     contract incl. fallback_reason; the batch versions mirror them).
#   - ADDED thin X-edge wrappers (refine_xedge_*) that transpose the
#     input, delegate to the Y-edge implementations, and return results
#     in original-image coordinates. New code, not in MMH.
#   - Y-edge algorithm semantics kept byte-for-byte (incl. the batch
#     versions' np.diff-based gradient and cumsum smoothing, which differ
#     from the scalar np.gradient/np.convolve versions by a small
#     systematic offset — intentional, behavior preserved).
#   - ZERO Qt; pure NumPy/OpenCV.
"""Sub-pixel edge refinement (亚像素边缘精修), vendored from MMH's CMG recipe.

Axis convention
---------------
A **Y-edge** is a *horizontal* boundary: intensity varies along the Y
(row) axis. The ``refine_yedge_*`` functions take column positions
(``sample_xs`` / ``x_center``) and a row guess ``y_guess``, and return
refined sub-pixel **row** coordinates.

An **X-edge** is a *vertical* boundary: intensity varies along the X
(column) axis. The ``refine_xedge_*`` wrappers take row positions
(``sample_ys`` / ``y_center``) and a column guess ``x_guess``, transpose
the image, delegate to the Y-edge implementation, and return refined
sub-pixel **column** coordinates in the original image frame (a
transpose maps X-edges onto Y-edges, so coordinates come back directly;
no further transformation is required).

Two refinement methods are provided:

* *gradient sub-pixel* (``refine_*_subpixel*``): dominant |gradient|
  peak with quality gates + quadratic interpolation;
* *threshold crossing* (``refine_*_threshold_crossing*``): linear
  interpolation of the crossing of ``I_min + range * threshold_frac``
  (industry standard: 50 % of local contrast).
"""

from __future__ import annotations

from typing import List, NamedTuple, Optional

import cv2
import numpy as np


class SubpixelResult(NamedTuple):
    """Return value from refine_yedge_subpixel() / refine_yedge_threshold_crossing().

    fallback_reason is "" on success; one of the reason codes below on failure:
      "invalid_image"      – image is None or wrong ndim
      "small_window"       – search window < 3 rows
      "flat_profile"       – profile contrast < 1 DN
      "weak_gradient"      – peak gradient below relative threshold
      "ambiguous_peak"     – two comparable peaks detected
      "no_crossing"        – threshold not crossed anywhere in window (TC only)
      "proximity_violation"– refined position too far from y_guess
    """
    y_refined: float
    fallback_reason: str
    peak_strength: float       # peak_val / p_range  (0 on fallback)
    second_peak_ratio: float   # second_val / peak_val  (0 on fallback)
    shift_px: float            # y_refined - y_guess  (0 on fallback)


# --------------------------------------------------------------------------- #
# filtering / strip helpers
# --------------------------------------------------------------------------- #
def _gaussian_kernel(sigma: float) -> np.ndarray:
    k = max(3, int(6 * sigma) | 1)          # odd kernel, at least 3 wide
    x = np.arange(k, dtype=np.float64) - k // 2
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    return kernel / kernel.sum()


def gaussian_filter1d(profile: np.ndarray, sigma: float) -> np.ndarray:
    """Apply a 1-D Gaussian LPF using numpy convolution (no scipy dependency).

    **邊界補的是端點值，不是 0**（``mode='edge'``）。``np.convolve`` 的
    ``mode='same'`` 補零，於是剖面的頭尾兩端被拉向 0 —— 那在梯度上是一道
    **假的、而且通常是全剖面最強的**轉折。

    後果不是「頭尾兩格不準」而已：``algo.edge.find_edges`` 的偵測門檻是
    **相對的**（``0.35 × 該剖面最大梯度``），所以那道假梯度會把門檻整個墊高，
    於是**真正的邊被安靜地丟掉** —— 剖面兩端的材質對比越強，被丟掉的越多。
    2026-08-22 在 MG extrusion 的合成資料上量到：凸出量對設計值的回歸斜率
    0.079、R² 0.030（等於完全沒有量到），改成 edge padding 之後是 0.917 / 0.792。
    症狀是那幾列回 ``open_edge``，而 ``open_edge`` 看起來完全像「結構被框切掉了」。

    同一份檔案裡 :func:`smooth_strip_2d` 一直都是 ``mode='edge'``；
    MMH 那幾支則是用一個 ``k//2+1`` 的 margin 把被汙染的樣本排除掉
    （見 :func:`refine_yedge_gradient_peak` 的 Step 7）。也就是說這件事
    這個 repo 早就知道，只有這一支漏掉 —— 而 ``algo.edge`` 沒有那個 margin。
    """
    kernel = _gaussian_kernel(sigma)
    pad = kernel.size // 2
    padded = np.pad(np.asarray(profile, dtype=np.float64), (pad, pad), mode='edge')
    return np.convolve(padded, kernel, mode='valid')


def gaussian_filter1d_2d(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Apply per-column Gaussian LPF on a 2-D array (axis=0), pure numpy.

    邊界處理與 :func:`gaussian_filter1d` 一致（見那一支的說明）——
    兩支對同一件事給出不同答案，是最難發現的那種錯。
    """
    kernel = _gaussian_kernel(sigma)
    pad = kernel.size // 2
    result = np.zeros_like(arr, dtype=np.float64)
    for col in range(arr.shape[1]):
        padded = np.pad(arr[:, col].astype(np.float64), (pad, pad), mode='edge')
        result[:, col] = np.convolve(padded, kernel, mode='valid')
    return result


def smooth_strip_2d(strip: np.ndarray, k: int) -> np.ndarray:
    """Per-column moving average on a 2-D strip, pure numpy.

    k is forced to the nearest odd integer ≥ 3 internally.
    Returns shape (n_rows - 1, n_cols) for any k > 1 after forcing, or
    (n_rows, n_cols) unchanged when k ≤ 1.  The one-row loss is intentional:
    edge crossings always occur well inside the search window.
    """
    if k <= 1:
        return strip
    k = k | 1
    pad = np.pad(strip, ((k // 2, k // 2), (0, 0)), mode='edge')
    cs = np.cumsum(pad, axis=0, dtype=np.float64)
    return (cs[k:] - cs[:-k]) / k


def extract_strip(
    image: np.ndarray,
    sample_xs: list,
    y_guess: float,
    search_half: int,
    smooth_k: int,
    profile_lpf_sigma: float,
) -> tuple:
    """Extract, LPF-filter, and smooth a 2-D strip for all valid sample_xs.

    Returns (strip, y_lo, valid_mask) where
      strip      – shape (window_height, n_valid_cols), dtype float64
      y_lo       – int, top row of the search window
      valid_mask – list[bool], True where sample_xs[i] is inside the image
    """
    h, w = image.shape[:2]
    y_lo = max(0, int(round(y_guess)) - search_half)
    y_hi = min(h, int(round(y_guess)) + search_half + 1)

    valid_mask = [0 <= x < w for x in sample_xs]
    valid_xs = [x for x, ok in zip(sample_xs, valid_mask) if ok]

    strip = image[y_lo:y_hi, valid_xs].astype(np.float64)

    if profile_lpf_sigma > 0.0:
        strip = gaussian_filter1d_2d(strip, profile_lpf_sigma)

    strip = smooth_strip_2d(strip, smooth_k)

    return strip, y_lo, valid_mask


# --------------------------------------------------------------------------- #
# batch Y-edge refinement
# --------------------------------------------------------------------------- #
def refine_yedge_threshold_crossing_batch(
    image: np.ndarray,
    sample_xs: list,
    y_guess: float,
    search_half: int = 10,
    proximity: int = 8,
    smooth_k: int = 3,
    threshold_frac: float = 0.5,
    profile_lpf_sigma: float = 0.0,
) -> list:
    """Vectorised TC refinement: one 2-D strip extraction for all sample_xs.

    Returns list[float | None] of length len(sample_xs).
    """
    if not sample_xs or image is None or image.ndim < 2:
        return [None] * len(sample_xs)

    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h = img.shape[0]
    y_lo_check = max(0, int(round(y_guess)) - search_half)
    y_hi_check = min(h, int(round(y_guess)) + search_half + 1)
    if y_hi_check - y_lo_check < 3:
        return [None] * len(sample_xs)

    strip, y_lo, valid_mask = extract_strip(
        img, sample_xs, y_guess, search_half, smooth_k, profile_lpf_sigma
    )
    if strip.shape[0] < 2 or strip.shape[1] == 0:
        return [None] * len(sample_xs)

    col_min = strip.min(axis=0)
    col_max = strip.max(axis=0)
    col_range = col_max - col_min
    threshold = col_min + col_range * threshold_frac

    centered = strip - threshold[np.newaxis, :]
    signs = np.sign(centered)
    cross_mask = (signs[:-1] * signs[1:]) <= 0   # shape (n-1, n_cols)

    results_valid: list = []
    for col_idx in range(strip.shape[1]):
        if col_range[col_idx] < 1.0:
            results_valid.append(None)
            continue
        cross_rows = np.where(cross_mask[:, col_idx])[0]
        if len(cross_rows) == 0:
            results_valid.append(None)
            continue
        best_crossing = None
        best_dist = float('inf')
        thr = threshold[col_idx]
        for i in cross_rows:
            a_val = strip[i, col_idx]
            b_val = strip[i + 1, col_idx]
            denom = b_val - a_val
            frac = (thr - a_val) / denom if abs(denom) > 1e-12 else 0.5
            crossing = float(y_lo) + i + max(0.0, min(1.0, frac))
            dist = abs(crossing - y_guess)
            if dist < best_dist:
                best_dist = dist
                best_crossing = crossing
        if best_crossing is None or abs(best_crossing - y_guess) > proximity:
            results_valid.append(None)
        else:
            results_valid.append(best_crossing)

    results: list = []
    valid_iter = iter(results_valid)
    for ok in valid_mask:
        results.append(next(valid_iter) if ok else None)
    return results


def refine_yedge_subpixel_batch(
    image: np.ndarray,
    sample_xs: list,
    y_guess: float,
    search_half: int = 10,
    proximity: int = 5,
    smooth_k: int = 5,
    min_grad_frac: float = 0.10,
    peak_ratio_thr: float = 0.60,
    profile_lpf_sigma: float = 0.0,
) -> list:
    """Vectorised Gradient refinement: one 2-D strip extraction for all sample_xs.

    Mirrors the scalar refine_yedge_subpixel logic (gradient peak + quadratic
    interpolation + peak dominance check) but extracts one 2-D strip and
    computes the abs-gradient array across all columns simultaneously.

    Returns list[float | None] of length len(sample_xs).
    """
    if not sample_xs or image is None or image.ndim < 2:
        return [None] * len(sample_xs)

    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h = img.shape[0]
    y_lo_check = max(0, int(round(y_guess)) - search_half)
    y_hi_check = min(h, int(round(y_guess)) + search_half + 1)
    n = y_hi_check - y_lo_check
    if n < 3:
        return [None] * len(sample_xs)

    strip, y_lo, valid_mask = extract_strip(
        img, sample_xs, y_guess, search_half, smooth_k, profile_lpf_sigma
    )
    if strip.shape[0] < 2 or strip.shape[1] == 0:
        return [None] * len(sample_xs)

    n_s = strip.shape[0]   # may be n-1 after smoothing
    col_min = strip.min(axis=0)
    col_max = strip.max(axis=0)
    col_range = col_max - col_min   # shape (n_cols,)

    # Vectorised absolute gradient: shape (n_s-1, n_cols)
    abs_grad = np.abs(np.diff(strip, axis=0))

    # Search margins (match scalar version: margin = k//2 + 1)
    k = smooth_k | 1
    margin = max(1, k // 2 + 1)
    lo_m = margin
    hi_m = max(lo_m + 1, n_s - margin)

    results_valid: list = []
    for col_idx in range(strip.shape[1]):
        p_range = col_range[col_idx]
        if p_range < 1.0:
            results_valid.append(None)
            continue

        min_grad_abs = min_grad_frac * p_range
        search_slice = abs_grad[lo_m:hi_m, col_idx]
        if len(search_slice) < 1:
            results_valid.append(None)
            continue

        peak_in_slice = int(np.argmax(search_slice))
        peak_val = float(search_slice[peak_in_slice])
        peak_local = peak_in_slice + lo_m

        if peak_val < min_grad_abs:
            results_valid.append(None)
            continue

        # Peak dominance check (exclusion zone matches scalar)
        _excl_r = k // 2 + 2
        _excl_l = k // 2 + 1
        mask = np.ones(len(search_slice), dtype=bool)
        excl_lo = max(0, peak_in_slice - _excl_l)
        excl_hi = min(len(search_slice), peak_in_slice + _excl_r)
        mask[excl_lo:excl_hi] = False
        second_val = float(search_slice[mask].max()) if mask.any() else 0.0
        if mask.any() and second_val > peak_ratio_thr * peak_val:
            results_valid.append(None)   # ambiguous_peak
            continue

        # Quadratic subpixel interpolation on gradient peak
        col_grad = abs_grad[:, col_idx]
        if 0 < peak_local < n_s - 2:
            a = col_grad[peak_local - 1]
            b = col_grad[peak_local]
            c = col_grad[peak_local + 1]
            denom = a - 2.0 * b + c
            delta = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
            peak_sub = float(peak_local) + delta
        else:
            peak_sub = float(peak_local)

        peak_sub = max(0.0, min(float(n_s - 1), peak_sub))
        refined = float(y_lo) + peak_sub

        if abs(refined - y_guess) > proximity:
            results_valid.append(None)
            continue

        results_valid.append(refined)

    results: list = []
    valid_iter = iter(results_valid)
    for ok in valid_mask:
        results.append(next(valid_iter) if ok else None)
    return results


# --------------------------------------------------------------------------- #
# scalar Y-edge refinement (SubpixelResult contract)
# --------------------------------------------------------------------------- #
def refine_yedge_subpixel(
    image: np.ndarray,
    x_center: float,
    y_guess: float,
    half_col: int = 3,
    search_half: int = 10,
    proximity: int = 5,
    smooth_k: int = 5,
    min_grad_frac: float = 0.10,
    peak_ratio_thr: float = 0.60,
    profile_lpf_sigma: float = 0.0,
) -> SubpixelResult:
    """Refine a Y-edge position to subpixel precision using gradient-based detection.

    Extracts a narrow column profile from the raw grayscale image around
    (x_center, y_guess), finds the dominant gradient peak with quality checks,
    and applies quadratic subpixel interpolation.

    Constraints enforced:
    - Relative gradient threshold (min_grad_frac × profile contrast range)
    - Peak dominance: rejects profiles with multiple comparable peaks
    - Proximity: refined result must lie within ±proximity px of y_guess
    - Search window strictly bounded to ±search_half px of y_guess

    Returns SubpixelResult with fallback_reason="" on success, or a reason
    code string on failure (y_refined == y_guess in that case).
    """
    def _fallback(reason):
        return SubpixelResult(y_guess, reason, 0.0, 0.0, 0.0)

    if image is None or image.ndim < 2:
        return _fallback("invalid_image")

    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = img.shape

    # Step 1: narrow column strip around x_center
    x0 = max(0, int(x_center) - half_col)
    x1 = min(w, int(x_center) + half_col + 1)
    if x1 - x0 < 1:
        return _fallback("invalid_image")

    # Step 2: Y search window strictly bounded to ±search_half px
    y_lo = max(0, int(round(y_guess)) - search_half)
    y_hi = min(h, int(round(y_guess)) + search_half + 1)
    n = y_hi - y_lo
    if n < 3:
        return _fallback("small_window")

    # Step 3: 1D profile — mean intensity over X strip
    profile = img[y_lo:y_hi, x0:x1].astype(np.float64).mean(axis=1)

    # Step 3b: optional Gaussian LPF pre-filter (applied before moving-average)
    if profile_lpf_sigma > 0.0:
        profile = gaussian_filter1d(profile, profile_lpf_sigma)

    # Step 4: relative gradient threshold — profile must have visible contrast
    p_range = float(profile.max() - profile.min())
    if p_range < 1.0:           # essentially flat region → no edge to find
        return _fallback("flat_profile")
    min_grad_abs = min_grad_frac * p_range

    # Step 5: moving-average smoothing
    k = smooth_k | 1            # ensure odd kernel
    if n >= k:
        kernel = np.ones(k, dtype=np.float64) / k
        profile = np.convolve(profile, kernel, mode='same')

    # Step 6: absolute gradient
    abs_grad = np.abs(np.gradient(profile))

    # Step 7: search interior only (avoid convolution boundary artefacts).
    # Margin must be k//2+1 so that abs_grad values that depend on zero-padded
    # smoothed samples are excluded (np.convolve 'same' contaminates k//2 samples
    # on each side, and np.gradient then propagates one more index outward).
    margin = max(1, k // 2 + 1)
    lo_m = margin
    hi_m = min(max(lo_m + 1, n - margin), n)
    search_slice = abs_grad[lo_m:hi_m]
    if len(search_slice) < 1:
        return _fallback("small_window")

    peak_in_slice = int(np.argmax(search_slice))
    peak_local = peak_in_slice + lo_m
    peak_val = abs_grad[peak_local]

    # Step 8: relative gradient threshold check
    if peak_val < min_grad_abs:
        return _fallback("weak_gradient")

    # Step 9: peak dominance check.
    # A smoothed step edge creates a gradient plateau of width ≈ k-1 samples, so
    # the exclusion zone must be wide enough to cover it: ±(k//2+1) from the peak.
    _excl_r = k // 2 + 2   # half-width on the right (exclusive upper bound offset)
    _excl_l = k // 2 + 1   # half-width on the left
    mask = np.ones(len(search_slice), dtype=bool)
    excl_lo = max(0, peak_in_slice - _excl_l)
    excl_hi = min(len(search_slice), peak_in_slice + _excl_r)
    mask[excl_lo:excl_hi] = False
    second_val = float(search_slice[mask].max()) if mask.any() else 0.0
    if mask.any() and second_val > peak_ratio_thr * peak_val:
        return _fallback("ambiguous_peak")  # multiple peaks of similar height

    # Step 10: quadratic subpixel interpolation on gradient peak
    if 0 < peak_local < n - 1:
        a = abs_grad[peak_local - 1]
        b = abs_grad[peak_local]
        c = abs_grad[peak_local + 1]
        denom = a - 2.0 * b + c
        delta = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
        peak_sub = float(peak_local) + delta
    else:
        peak_sub = float(peak_local)

    # Clamp to search window
    peak_sub = max(0.0, min(float(n - 1), peak_sub))
    refined = float(y_lo) + peak_sub

    # Step 11: proximity constraint — refined must stay close to initial guess
    if abs(refined - y_guess) > proximity:
        return _fallback("proximity_violation")

    peak_strength = peak_val / (p_range + 1e-12)
    ratio = second_val / peak_val if peak_val > 0 else 0.0
    return SubpixelResult(refined, "", peak_strength, ratio, refined - y_guess)


def refine_yedge_threshold_crossing(
    image: np.ndarray,
    x_center: float,
    y_guess: float,
    half_col: int = 3,
    search_half: int = 10,
    proximity: int = 8,
    smooth_k: int = 3,
    threshold_frac: float = 0.5,
    profile_lpf_sigma: float = 0.0,
) -> SubpixelResult:
    """Refine a Y-edge by finding where intensity crosses a threshold level.

    threshold = I_min + (I_max - I_min) * threshold_frac

    I_max and I_min are the extrema of the smoothed 1D profile within the
    search window.  The crossing closest to y_guess is returned.  Industry
    standard uses threshold_frac=0.5 (50 % of the local contrast range).

    Fallback reasons (y_refined == y_guess on failure):
      "invalid_image"      – image None or wrong ndim
      "small_window"       – search window < 3 rows
      "flat_profile"       – profile contrast < 1 DN
      "no_crossing"        – threshold not crossed anywhere in window
      "proximity_violation"– closest crossing too far from y_guess
    """
    def _fallback(reason):
        return SubpixelResult(y_guess, reason, 0.0, 0.0, 0.0)

    if image is None or image.ndim < 2:
        return _fallback("invalid_image")

    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = img.shape

    # Step 1: narrow column strip
    x0 = max(0, int(x_center) - half_col)
    x1 = min(w, int(x_center) + half_col + 1)
    if x1 - x0 < 1:
        return _fallback("invalid_image")

    # Step 2: Y search window
    y_lo = max(0, int(round(y_guess)) - search_half)
    y_hi = min(h, int(round(y_guess)) + search_half + 1)
    n = y_hi - y_lo
    if n < 3:
        return _fallback("small_window")

    # Step 3: 1D profile — mean intensity over X strip
    profile = img[y_lo:y_hi, x0:x1].astype(np.float64).mean(axis=1)

    # Step 3b: optional Gaussian LPF pre-filter (applied before moving-average)
    if profile_lpf_sigma > 0.0:
        profile = gaussian_filter1d(profile, profile_lpf_sigma)

    # Step 4: contrast check
    p_range = float(profile.max() - profile.min())
    if p_range < 1.0:
        return _fallback("flat_profile")

    # Step 5: moving-average smoothing
    k = smooth_k | 1
    if n >= k:
        kernel = np.ones(k, dtype=np.float64) / k
        profile = np.convolve(profile, kernel, mode='same')

    # Step 6: threshold level from smoothed profile extrema
    i_max = float(profile.max())
    i_min = float(profile.min())
    threshold = i_min + (i_max - i_min) * threshold_frac

    # Step 7: find all crossings, keep the one closest to y_guess
    best_crossing: Optional[float] = None
    best_dist = float('inf')
    for i in range(n - 1):
        a, b_val = profile[i], profile[i + 1]
        # Crossed when the two samples straddle the threshold (or one equals it)
        if (a - threshold) * (b_val - threshold) <= 0:
            denom = b_val - a
            t = (threshold - a) / denom if abs(denom) > 1e-12 else 0.5
            t = max(0.0, min(1.0, t))
            crossing = float(y_lo) + i + t
            dist = abs(crossing - y_guess)
            if dist < best_dist:
                best_dist = dist
                best_crossing = crossing

    if best_crossing is None:
        return _fallback("no_crossing")

    # Step 8: proximity constraint
    if abs(best_crossing - y_guess) > proximity:
        return _fallback("proximity_violation")

    contrast = (i_max - i_min) / (i_max + 1e-12)
    return SubpixelResult(best_crossing, "", contrast, 0.0, best_crossing - y_guess)


# --------------------------------------------------------------------------- #
# sampling / aggregation helpers
# --------------------------------------------------------------------------- #
def compute_sample_xs(x_start: int, x_end: int, mode) -> List[int]:
    """Return list of x positions to sample in [x_start, x_end).

    mode: "all" → every integer; int N → N evenly spaced positions.
    """
    xs = list(range(int(x_start), int(x_end)))
    if not xs:
        return xs
    if mode == "all" or not isinstance(mode, int):
        return xs
    N = max(1, min(int(mode), len(xs)))
    if N >= len(xs):
        return xs
    indices = [int(round(i)) for i in np.linspace(0, len(xs) - 1, N)]
    return [xs[i] for i in indices]


def aggregate_values(vals: list, method: str) -> float:
    """Aggregate float list using method: median/mean/min/max."""
    if not vals:
        return 0.0
    m = method.lower()
    if m == "mean":
        return float(np.mean(vals))
    if m == "min":
        return float(np.min(vals))
    if m == "max":
        return float(np.max(vals))
    return float(np.median(vals))  # default: median


# --------------------------------------------------------------------------- #
# X-edge wrappers (d4t additions — thin transpose adapters)
# --------------------------------------------------------------------------- #
def _transpose_gray(image: np.ndarray) -> Optional[np.ndarray]:
    """Grayscale-convert (if colour) then transpose. None passes through."""
    if image is None or getattr(image, "ndim", 0) < 2:
        return image
    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return np.ascontiguousarray(img.T)


def refine_xedge_subpixel(image: np.ndarray, y_center: float, x_guess: float,
                          **kwargs) -> SubpixelResult:
    """X-edge counterpart of :func:`refine_yedge_subpixel`.

    Transposes the image and delegates; ``y_refined``/``shift_px`` in the
    returned SubpixelResult are X (column) coordinates of the original image.
    """
    return refine_yedge_subpixel(_transpose_gray(image), y_center, x_guess,
                                 **kwargs)


def refine_xedge_threshold_crossing(image: np.ndarray, y_center: float,
                                    x_guess: float, **kwargs) -> SubpixelResult:
    """X-edge counterpart of :func:`refine_yedge_threshold_crossing`."""
    return refine_yedge_threshold_crossing(_transpose_gray(image), y_center,
                                           x_guess, **kwargs)


def refine_xedge_subpixel_batch(image: np.ndarray, sample_ys: list,
                                x_guess: float, **kwargs) -> list:
    """X-edge counterpart of :func:`refine_yedge_subpixel_batch`.

    ``sample_ys`` are row positions; the returned list holds refined X
    (column) coordinates (or None) in the original image frame.
    """
    return refine_yedge_subpixel_batch(_transpose_gray(image), sample_ys,
                                       x_guess, **kwargs)


def refine_xedge_threshold_crossing_batch(image: np.ndarray, sample_ys: list,
                                          x_guess: float, **kwargs) -> list:
    """X-edge counterpart of :func:`refine_yedge_threshold_crossing_batch`."""
    return refine_yedge_threshold_crossing_batch(_transpose_gray(image),
                                                 sample_ys, x_guess, **kwargs)
