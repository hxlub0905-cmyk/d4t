# Vendored into ADEPT on 2026-07-27.
# Source project: cell-period-estimator —
#   cell_period_estimator/core/period_core.py (vendored wholesale)
# Adaptations:
#   - Module vendored unchanged (pure NumPy/OpenCV, no Qt in the source).
#   - `choose_origin` was the source's (0, 0) stub; ADEPT M4-1 replaced it
#     with a real phase search (sub-sampled scan over [0, px) x [0, py),
#     ranked by the stacked cell's raw Laplacian variance).  The old
#     three-argument call still returns (0, 0) — `image` is opt-in.
#   - No other algorithmic changes.
"""Period estimation core.

Pure NumPy / OpenCV — no Qt imports here so the algorithms can be used
headlessly (tests, batch processing) without a display server.

The estimation strategy, per axis:

1. Two 1-D projections are computed:
   * an *intensity* projection (mean brightness along the other axis),
     high-pass detrended to suppress slow illumination gradients, and
   * a *gradient* projection (median of ``|Sobel|`` along the other axis).
2. The period is estimated from the **intensity** projection.  The
   fundamental dominates the intensity spectrum, which avoids the
   half-period "edge doubling" that gradient projections suffer from
   (every cell edge produces two gradient peaks).
3. An rFFT picks the strongest peak inside the adaptive ``[lo, hi]``
   search band to get a coarse candidate period.  A normalized
   autocorrelation with parabolic sub-pixel interpolation cross-checks
   and refines it, then applies harmonic correction.
4. A modulation gate rejects nearly flat axes (e.g. the orthogonal axis
   of a line/space pattern) so that noise normalized to unit scale is
   not mistaken for a real period.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

# An axis whose intensity projection has a standard deviation below this
# (in 8-bit grey levels) is considered featureless / not periodic.
_MODULATION_STD_FLOOR = 0.5


@dataclass
class AxisSpectrum:
    """FFT spectrum for a single axis, in *period* (not frequency) units."""

    periods: np.ndarray
    magnitude: np.ndarray
    peak_period: Optional[float] = None

    def normalized_magnitude(self) -> np.ndarray:
        """Magnitude scaled to ``[0, 1]`` for plotting."""
        mag = np.asarray(self.magnitude, dtype=np.float64)
        if mag.size == 0:
            return mag
        peak = float(mag.max())
        if peak <= 0:
            return np.zeros_like(mag)
        return mag / peak


@dataclass
class PeriodResult:
    """Outcome of :func:`estimate_period`."""

    px: Optional[int]
    py: Optional[int]
    confidence_x: float
    confidence_y: float
    axis_mode: str
    peak_strength_x: float
    peak_strength_y: float
    spectrum_x: AxisSpectrum
    spectrum_y: AxisSpectrum
    candidates: List[Tuple[Optional[int], Optional[int]]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _to_gray(image: np.ndarray) -> np.ndarray:
    """Return a float64 single-channel copy of ``image``."""
    arr = np.asarray(image)
    if arr.ndim == 3:
        if arr.shape[2] == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
        else:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return arr.astype(np.float64)


def _highpass(profile: np.ndarray, win: int) -> np.ndarray:
    """Subtract an edge-padded moving average (high-pass detrend).

    Edge padding avoids the spurious ramps a zero-padded average would
    introduce at the profile boundaries.
    """
    n = profile.size
    win = int(win)
    if win < 3:
        return profile - profile.mean()
    if win % 2 == 0:
        win += 1
    win = min(win, n if n % 2 == 1 else n - 1)
    if win < 3:
        return profile - profile.mean()
    pad = win // 2
    padded = np.pad(profile, pad, mode="edge")
    kernel = np.ones(win, dtype=np.float64) / win
    moving = np.convolve(padded, kernel, mode="valid")
    return profile - moving[: n]


def _autocorr(x: np.ndarray) -> np.ndarray:
    """Normalized autocorrelation (lag 0 == 1.0) for non-negative lags."""
    x = x - x.mean()
    n = x.size
    full = np.correlate(x, x, mode="full")
    ac = full[n - 1:]
    if ac.size == 0 or ac[0] == 0:
        return np.zeros_like(ac)
    return ac / ac[0]


def _parabolic(values: np.ndarray, idx: int) -> Tuple[float, float]:
    """Sub-pixel peak location around integer index ``idx`` of ``values``."""
    if idx <= 0 or idx >= values.size - 1:
        return float(idx), float(values[idx])
    ym1, y0, yp1 = values[idx - 1], values[idx], values[idx + 1]
    denom = ym1 - 2.0 * y0 + yp1
    if denom == 0:
        return float(idx), float(y0)
    delta = 0.5 * (ym1 - yp1) / denom
    delta = float(np.clip(delta, -1.0, 1.0))
    peak = y0 - 0.25 * (ym1 - yp1) * delta
    return idx + delta, float(peak)


def _search_band(min_period: Optional[int], max_period: Optional[int],
                 length: int) -> Tuple[int, int]:
    """Adaptive ``[lo, hi]`` period band for an axis of given length."""
    lo = max(2, int(min_period) if min_period else 4)
    hi = min(int(max_period) if max_period else length // 2, length // 2)
    if hi < lo:
        hi = lo
    return lo, hi


def _analyze_axis(intensity: np.ndarray, lo: int, hi: int,
                  strength_threshold: float
                  ) -> Tuple[Optional[int], float, float, AxisSpectrum, List[str]]:
    """Estimate the period of one axis from its intensity projection.

    Returns ``(period, confidence_0_100, peak_strength_0_1, spectrum,
    warnings)``.  ``period`` is ``None`` when no reliable period is found.
    """
    warnings: List[str] = []
    n = intensity.size
    empty = AxisSpectrum(np.array([]), np.array([]), None)

    if n < 8 or hi <= lo:
        return None, 0.0, 0.0, empty, warnings

    # Modulation gate: a nearly flat projection has no real period.
    if float(intensity.std()) < _MODULATION_STD_FLOOR:
        return None, 0.0, 0.0, empty, warnings

    detrended = _highpass(intensity, max(3, n // 4))
    detrended = detrended - detrended.mean()
    if not np.any(detrended):
        return None, 0.0, 0.0, empty, warnings

    # --- rFFT: coarse candidate period --------------------------------- #
    spectrum = np.abs(np.fft.rfft(detrended))
    ks = np.arange(1, spectrum.size)
    periods_all = n / ks
    mags_all = spectrum[1:]
    band = (periods_all >= lo) & (periods_all <= hi)
    if not np.any(band):
        return None, 0.0, 0.0, empty, warnings

    band_periods = periods_all[band]
    band_mags = mags_all[band]
    order = np.argsort(band_periods)  # ascending period for a tidy spectrum
    spec = AxisSpectrum(band_periods[order], band_mags[order], None)

    p_fft = float(band_periods[np.argmax(band_mags)])

    # --- autocorrelation: locate the fundamental period ---------------- #
    # The intensity FFT peak can fall on a harmonic when the cell content
    # is rich (a strong feature inside every cell repeats at sub-cell
    # frequencies).  The autocorrelation is the more reliable arbiter of
    # the *fundamental*: we pick the strongest local maximum in the lag
    # band, which skips both the monotonic high-correlation region near
    # lag 0 and the harmonic dips.
    ac = _autocorr(detrended)

    def ac_at(lag: float) -> float:
        li = int(round(lag))
        if 1 <= li < ac.size:
            return float(ac[li])
        return -1.0

    lo_l = max(2, lo)
    hi_l = min(ac.size - 2, hi)
    if hi_l <= lo_l:
        return None, 0.0, 0.0, spec, warnings

    best_lag, best_val = None, -np.inf
    for lag in range(lo_l, hi_l + 1):
        if ac[lag] >= ac[lag - 1] and ac[lag] >= ac[lag + 1] and ac[lag] > best_val:
            best_lag, best_val = lag, ac[lag]
    if best_lag is None:  # no clear peak; fall back to the FFT hint
        best_lag = int(np.clip(round(p_fft), lo_l, hi_l))
    period, strength = _parabolic(ac, best_lag)

    # --- harmonic correction ------------------------------------------- #
    p_int = int(round(period))
    if ac_at(2 * period) > 1.15 * ac_at(period):
        period = 2.0 * period
        strength = ac_at(period)
        warnings.append("doubled period (fundamental at 2x)")
    elif p_int % 2 == 0 and ac_at(p_int // 2) >= 0.9 * ac_at(period):
        period = period / 2.0
        strength = ac_at(period)
        warnings.append("halved period (sub-cell at p/2)")

    period_int = int(round(period))
    spec.peak_period = float(period_int)
    strength = float(np.clip(strength, 0.0, 1.0))

    if period_int < lo or strength < strength_threshold:
        return None, round(strength * 100.0, 1), strength, spec, warnings

    confidence = round(float(np.clip(strength, 0.0, 1.0)) * 100.0, 1)
    return period_int, confidence, strength, spec, warnings


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def estimate_period(image: np.ndarray,
                    min_period: Optional[int] = None,
                    max_period: Optional[int] = None,
                    strength_threshold: float = 0.18) -> PeriodResult:
    """Estimate the repeating cell period of ``image``.

    Parameters
    ----------
    image:
        Greyscale or colour image (``np.ndarray``).
    min_period, max_period:
        Optional bounds on the period search, in pixels.  Defaults adapt
        to the image size.
    strength_threshold:
        Minimum normalized autocorrelation strength (0..1) required to
        accept a period on an axis.
    """
    gray = _to_gray(image)
    h, w = gray.shape[:2]

    # Intensity projections: mean brightness along the orthogonal axis.
    prof_x = gray.mean(axis=0)   # varies along X, length == width
    prof_y = gray.mean(axis=1)   # varies along Y, length == height

    # Gradient projections (median |Sobel|) — computed per the spec; the
    # period itself is taken from the intensity projection.
    sob_x = np.abs(cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3))
    sob_y = np.abs(cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3))
    _grad_x = np.median(sob_x, axis=0)
    _grad_y = np.median(sob_y, axis=1)

    lo_x, hi_x = _search_band(min_period, max_period, w)
    lo_y, hi_y = _search_band(min_period, max_period, h)

    px, conf_x, str_x, spec_x, warn_x = _analyze_axis(
        prof_x, lo_x, hi_x, strength_threshold)
    py, conf_y, str_y, spec_y, warn_y = _analyze_axis(
        prof_y, lo_y, hi_y, strength_threshold)

    has_x, has_y = px is not None, py is not None
    if has_x and has_y:
        axis_mode = "XY"
    elif has_x:
        axis_mode = "X"
    elif has_y:
        axis_mode = "Y"
    else:
        axis_mode = "NONE"

    warnings = list(warn_x) + list(warn_y)
    if axis_mode == "NONE":
        warnings.append("no periodic structure detected")

    candidates = _build_candidates(px, py, lo_x, hi_x, lo_y, hi_y)

    return PeriodResult(
        px=px, py=py,
        confidence_x=conf_x, confidence_y=conf_y,
        axis_mode=axis_mode,
        peak_strength_x=str_x, peak_strength_y=str_y,
        spectrum_x=spec_x, spectrum_y=spec_y,
        candidates=candidates,
        warnings=warnings,
    )


def _build_candidates(px: Optional[int], py: Optional[int],
                      lo_x: int, hi_x: int, lo_y: int, hi_y: int
                      ) -> List[Tuple[Optional[int], Optional[int]]]:
    """Harmonic alternatives around the primary period for review."""
    out: List[Tuple[Optional[int], Optional[int]]] = []
    seen = set()

    def x_ok(v):
        return v is not None and lo_x <= v <= hi_x

    def y_ok(v):
        return v is not None and lo_y <= v <= hi_y

    def add(a, b):
        a = int(a) if a is not None else None
        b = int(b) if b is not None else None
        if a is not None and not x_ok(a):
            return
        if b is not None and not y_ok(b):
            return
        key = (a, b)
        if key in seen or key == (None, None):
            return
        seen.add(key)
        out.append(key)

    add(px, py)
    if px is not None:
        add(px // 2, py)
        add(2 * px, py)
    if py is not None:
        add(px, py // 2)
        add(px, 2 * py)
    if px is not None and py is not None:
        add(px // 2, py // 2)
        add(2 * px, 2 * py)
    return out


def _origin_axis_candidates(period: int, span: int, max_side: int) -> List[int]:
    """Candidate origins along one axis (sub-sampled when ``period`` is big).

    Returns ``[0]`` when fewer than two whole cells fit along the axis —
    a single row/column of cells carries no phase information and some
    offsets would leave no complete cell at all.
    """
    if span < 2 * period:
        return [0]
    step = 1 if period <= max_side else -(-period // max_side)  # ceil division
    return list(range(0, period, step))


def choose_origin(shape: Tuple[int, ...], px: Optional[int], py: Optional[int],
                  image: Optional[np.ndarray] = None,
                  method: str = "mean",
                  max_evals: int = 256,
                  refine: int = 2) -> Tuple[int, int]:
    """Return the grid origin (top-left of the cell lattice) — phase search.

    Convention
    ----------
    The returned ``(ox, oy)`` is the **lattice origin in pixels**, with
    ``0 <= ox < px`` and ``0 <= oy < py``.  Feed it straight to the
    ``origin=`` argument of :func:`adept.core.algo.golden.tile_coords` /
    :func:`~adept.core.algo.golden.stack_cells`: cell ``(i, j)`` then
    covers ``x in [ox + i*px, ox + (i+1)*px)`` and
    ``y in [oy + j*py, oy + (j+1)*py)``.  Equivalently: cropping the
    image so that it starts at ``(ox, oy)`` puts the lattice in phase,
    after which every ``px`` / ``py`` pixels is a cell boundary.  Cells
    that would run past the right/bottom border are dropped by
    ``tile_coords``, so a larger origin simply wastes a little of the
    image — it never shifts the answer's meaning.

    What is optimised
    -----------------
    Each candidate origin is scored with
    ``golden.ghosting_score(golden.stack_cells(...))[1]`` — the **raw
    Laplacian variance** of the stacked cell.  **Higher is better**
    (sharper stack = the cells landed on top of each other; a mis-phased
    lattice smears structure across the cell border and the stack loses
    contrast).  Ranking by the raw variance rather than the saturating
    0..100 score matches :func:`golden.refine_period`; the 0..100 score
    clips near the top and would lose the ordering.

    ``method="mean"`` is used for scoring by default because the mean is
    deliberately the phase-sensitive stack (the median hides small
    misalignments), even when the caller later stacks with the median.

    Search cost
    -----------
    The full grid is ``px * py`` offsets, which explodes for large
    periods.  The scan is sub-sampled per axis so that at most
    ``max_evals`` (~256) offsets are evaluated, then refined by a
    ``±refine`` pixel neighbourhood scan around the coarse winner.

    Guards (never raises, never returns an out-of-range origin)
    ----------------------------------------------------------
    ``image is None`` (backward-compatible call), ``px``/``py`` missing
    or ``< 2``, a flat/constant image, or an image smaller than one cell
    all return ``(0, 0)``.  An axis with fewer than two whole cells is
    pinned to origin 0 (there is nothing to compare against).
    """
    from . import golden  # local import: keeps algo modules cycle-free

    if image is None:
        return (0, 0)
    try:
        px_i, py_i = int(px), int(py)   # type: ignore[arg-type]
    except (TypeError, ValueError):
        return (0, 0)
    if px_i < 2 or py_i < 2:
        return (0, 0)

    gray = _to_gray(image)
    if gray.ndim != 2 or gray.size == 0:
        return (0, 0)
    h, w = gray.shape[:2]
    if h < py_i or w < px_i:          # not even one whole cell
        return (0, 0)
    if float(gray.std()) < 1e-6:      # flat image: every phase is identical
        return (0, 0)

    max_side = max(2, int(np.sqrt(max(int(max_evals), 4))))
    xs = _origin_axis_candidates(px_i, w, max_side)
    ys = _origin_axis_candidates(py_i, h, max_side)
    if xs == [0] and ys == [0]:
        return (0, 0)

    def score(ox: int, oy: int) -> float:
        stacked = golden.stack_cells(gray, px_i, py_i, method=method,
                                     origin=(ox, oy))
        return float(golden.ghosting_score(stacked)[1])

    best_ox, best_oy, best_lv = 0, 0, -np.inf
    for oy in ys:
        for ox in xs:
            lv = score(ox, oy)
            if lv > best_lv:           # strict > → first winner wins (deterministic)
                best_lv, best_ox, best_oy = lv, ox, oy

    # Local refinement around the coarse winner (only where we sub-sampled).
    refine = max(0, int(refine))
    if refine and (len(xs) < px_i or len(ys) < py_i):
        rx = [best_ox] if xs == [0] else [(best_ox + d) % px_i
                                          for d in range(-refine, refine + 1)]
        ry = [best_oy] if ys == [0] else [(best_oy + d) % py_i
                                          for d in range(-refine, refine + 1)]
        for oy in ry:
            for ox in rx:
                lv = score(ox, oy)
                if lv > best_lv:
                    best_lv, best_ox, best_oy = lv, ox, oy

    return (int(best_ox) % px_i, int(best_oy) % py_i)
