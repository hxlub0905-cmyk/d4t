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


# ``refine_period`` / ``candidate_periods`` were deleted on 2026-08-27 (F40).
# They came in with the vendored module and never gained a production caller —
# ``estimate_period`` finds the period by autocorrelation and never asks this
# module anything.  Measured before deleting: ``refine_period`` starting from
# 26 walks to 20 when the truth is 28, because it ranks candidates by the
# sharpness of the stack, and sharpness is not alignment (see the module
# docstring above).  Keeping a broken helper alive for its own test is how a
# wrong answer waits for a first caller.
