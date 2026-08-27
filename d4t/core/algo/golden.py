# Vendored into d4t on 2026-07-27.
# Source project: cell-period-estimator —
#   cell_period_estimator/core/stacking.py (vendored wholesale)
# Adaptations:
#   - Module vendored unchanged (pure NumPy/OpenCV, no Qt in the source).
#   - No algorithmic changes.
"""Golden-Cell stacking, sharpness, and stacking agreement.

Pure NumPy / OpenCV.  Given a period ``(px, py)`` these helpers tile the
image into cells and average / median them into a single "Golden Cell".

⚠ **Two different questions, two different functions** (F40, 2026-08-27).
The vendored module docstring used to say "when the period is correct the
cells align and the stack is sharp; when it is wrong the cells drift and
the stack ghosts (blurs), which is what the sharpness metrics quantify."
**The last clause is false**, and it cost this project a silently useless
warning for months:

``ghosting_score``
    "How much edge energy is in *this one image*."  It never sees the
    cells that went into the stack, so it cannot tell "sharp because the
    cells aligned" from "sharp because two ghosts each contributed an
    edge".  Its value scales with contrast, noise and cell size, so it is
    only meaningful **relative to another stack of the same image**.
``stack_agreement``
    "Did the cells actually agree with each other."  Dimensionless,
    comparable across images, and 0 when they agree no better than
    chance.  This is the one to threshold against a fixed number.

Measured, on a line/space pattern (period 40) — the shape no test covered
until F40:

============================  ==========  ==============  ============
                              correct 40  half-period 60  pure noise
============================  ==========  ==============  ============
``ghosting_score`` (0..100)   43.0        **37.3–76.1**   **up to 99.4**
``stack_agreement`` (0..1)    0.24–0.99   **0.000**       0.003
============================  ==========  ==============  ============

The pure-noise column is the one to remember: an image with *nothing to
stack* scored 99.4 / 100 "sharpness" at σ=60, because noise is edges.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np


def _to_gray(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 3:
        if arr.shape[2] == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
        else:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return arr


def tile_coords(shape: Tuple[int, ...], px: int, py: int,
                origin: Tuple[int, int] = (0, 0)) -> List[Tuple[int, int]]:
    """Top-left ``(x, y)`` of every *complete* cell.

    Cells that would run past the image border are skipped.  This is the
    single source of truth for cell placement used by both stacking and
    period refinement.
    """
    h, w = shape[:2]
    ox, oy = origin
    px, py = int(px), int(py)
    if px < 1 or py < 1:
        return []
    xs = range(ox, w - px + 1, px)
    ys = range(oy, h - py + 1, py)
    return [(x, y) for y in ys for x in xs]


def stack_cells(image: np.ndarray, px: int, py: int, method: str = "mean",
                origin: Tuple[int, int] = (0, 0),
                sample_n: Optional[int] = None, seed: int = 0) -> np.ndarray:
    """Stack all (or ``sample_n`` random) cells into one ``(py, px)`` image.

    ``method="mean"`` (default) is sensitive to phase error and makes
    ghosting obvious; ``method="median"`` is robust to sparse defects.
    """
    gray = _to_gray(image)
    px, py = int(px), int(py)
    coords = tile_coords(gray.shape, px, py, origin)
    if not coords:
        return np.zeros((max(py, 1), max(px, 1)), dtype=np.uint8)

    if sample_n is not None and 0 < sample_n < len(coords):
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(coords), size=sample_n, replace=False)
        coords = [coords[i] for i in idx]

    cells = np.stack([
        gray[y:y + py, x:x + px].astype(np.float64) for (x, y) in coords
    ])
    if method == "median":
        stacked = np.median(cells, axis=0)
    else:
        stacked = cells.mean(axis=0)
    return np.clip(stacked, 0, 255).astype(np.uint8)


def ghosting_score(stacked: np.ndarray) -> Tuple[float, float, float]:
    """Quantify the sharpness of a stacked cell.

    Returns ``(score_0_100, laplacian_var, edge_contrast)``.  ``score``
    is a saturating 0..100 mapping for display; ``laplacian_var`` is the
    raw (unsaturated) value callers should rank by.

    ⚠ **What this is not** (F40).  It takes *one* image and asks how much
    high-frequency energy is in it.  It never sees the cells that were
    stacked, so it cannot answer "did they align" — and the two questions
    genuinely come apart: a mis-phased stack superimposes two copies and
    so carries *two* sets of edges, which **raises** this number.  Use
    :func:`stack_agreement` for "did they align".

    It is also **not comparable across images**: the value scales with
    contrast, noise and cell size.  ``0..100`` looks like a percentage
    and is not one — pure noise reaches 99.4 at σ=60.  Rank two stacks of
    the *same* image with it; never compare it to a fixed threshold.
    """
    g = stacked.astype(np.float64)
    if g.size == 0:
        return 0.0, 0.0, 0.0
    lap_var = float(cv2.Laplacian(g, cv2.CV_64F).var())
    gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    edge_contrast = float(np.hypot(gx, gy).mean())
    # Saturating map: high lap_var -> sharp -> approaches 100.
    score = float(np.clip(100.0 * (1.0 - np.exp(-lap_var / 200.0)), 0.0, 100.0))
    return score, lap_var, edge_contrast


def stack_agreement(image: np.ndarray, px: int, py: int,
                    origin: Tuple[int, int] = (0, 0)) -> float:
    """Did the cells actually agree with each other?  ``0``..``1`` (F40).

    ``1`` = every cell landed on top of the others; ``0`` = they agree no
    better than an unrelated pile of pixels.  Unlike :func:`ghosting_score`
    this is dimensionless, so it is the one that may be compared against a
    fixed threshold.

    How
    ---
    Cells that align average into something that keeps its structure;
    cells that do not average into mush.  So compare the variance of the
    stack against the variance of a typical single cell::

        a = var(mean(cells)) / mean(var(cell_i))        # in (1/n, 1]

    ⚠ **The ``1/n`` floor has to come off.**  ``n`` unrelated cells still
    leave ``var(mean) ≈ var(cell)/n`` behind, so a small image that only
    fits two cells scores 0.5 for *any* period.  Measured on the repo's
    own synthetic die (81×81, two cells): pure noise is ``0.499`` before
    the correction and ``0.000`` after it.  Without this the threshold
    would mean something different on every image size — which is exactly
    the bug this function exists to replace.

    Returns ``0.0`` when fewer than two whole cells fit (nothing was
    stacked, so nothing agreed) or when the cells are flat.
    """
    gray = _to_gray(image)
    px, py = int(px), int(py)
    coords = tile_coords(gray.shape, px, py, origin)
    cells = [gray[y:y + py, x:x + px].astype(np.float64) for (x, y) in coords]
    cells = [c for c in cells if c.shape == (py, px)]
    n = len(cells)
    if n < 2:
        return 0.0
    per_cell = float(np.mean([float(c.var()) for c in cells]))
    if per_cell < 1e-9:                 # a flat crop agrees with itself
        return 0.0                      # trivially — that is not evidence
    stacked_var = float(np.stack(cells).mean(axis=0).var())
    raw = stacked_var / per_cell
    floor = 1.0 / float(n)
    return float(np.clip((raw - floor) / (1.0 - floor), 0.0, 1.0))


def refine_period(image: np.ndarray, px: int, py: int, search: int = 6,
                  method: str = "mean") -> Tuple[int, int, float]:
    """Neighbourhood scan around ``(px, py)`` for the sharpest stack.

    Candidates are ranked by the **raw** Laplacian variance (not the
    saturating 0..100 score, which would clip and lose ordering near the
    top).  Returns ``(best_px, best_py, best_lap_var)``.
    """
    gray = _to_gray(image)
    px, py = int(px), int(py)
    search = int(search)

    best_px, best_py, best_lv = px, py, -1.0
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            cpx, cpy = px + dx, py + dy
            if cpx < 2 or cpy < 2:
                continue
            coords = tile_coords(gray.shape, cpx, cpy)
            if len(coords) < 4:
                continue
            stacked = stack_cells(gray, cpx, cpy, method=method)
            lv = float(cv2.Laplacian(stacked.astype(np.float64),
                                     cv2.CV_64F).var())
            if lv > best_lv:
                best_lv, best_px, best_py = lv, cpx, cpy
    return best_px, best_py, best_lv


def candidate_periods(px: int, py: int, lo: int, hi: int
                      ) -> List[Tuple[int, int]]:
    """Period candidates around the primary ``(px, py)``.

    Includes the primary plus per-axis and combined half/double
    harmonics, filtering out-of-range and duplicate entries.
    """
    out: List[Tuple[int, int]] = []
    seen = set()

    def add(a, b):
        a, b = int(a), int(b)
        if not (lo <= a <= hi and lo <= b <= hi):
            return
        if (a, b) in seen:
            return
        seen.add((a, b))
        out.append((a, b))

    add(px, py)             # primary
    add(px // 2, py)        # px/2
    add(2 * px, py)         # 2px
    add(px, py // 2)        # py/2
    add(px, 2 * py)         # 2py
    add(px // 2, py // 2)   # half
    add(2 * px, 2 * py)     # double
    return out
