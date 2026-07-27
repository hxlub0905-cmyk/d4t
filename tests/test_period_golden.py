"""Tests for flexadc.core.algo.period and .golden (vendored from
cell-period-estimator)."""
from __future__ import annotations

import numpy as np
import pytest

from flexadc.core.algo.golden import (
    candidate_periods,
    ghosting_score,
    refine_period,
    stack_cells,
    tile_coords,
)
from flexadc.core.algo.period import choose_origin, estimate_period

PX, PY = 24, 32


@pytest.fixture(scope="module")
def grid_image():
    """Synthetic 2-D cell grid: bright rectangle per (PX x PY) cell + noise."""
    rng = np.random.default_rng(42)
    h, w = 320, 288
    img = np.full((h, w), 40, np.float64)
    for y0 in range(0, h - PY + 1, PY):
        for x0 in range(0, w - PX + 1, PX):
            img[y0 + 8:y0 + 24, x0 + 6:x0 + 18] = 200
    img += rng.normal(0, 3, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def line_space_image():
    """Vertical line/space pattern: period 20 along X, flat along Y."""
    rng = np.random.default_rng(43)
    img = np.full((256, 256), 30, np.float64)
    for x0 in range(0, 256, 20):
        img[:, x0:x0 + 10] = 220
    img += rng.normal(0, 2, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_estimate_period_grid_xy(grid_image):
    r = estimate_period(grid_image)
    assert r.axis_mode == "XY"
    assert r.px is not None and abs(r.px - PX) <= 1
    assert r.py is not None and abs(r.py - PY) <= 1
    assert r.confidence_x > 50 and r.confidence_y > 50
    assert (r.px, r.py) == r.candidates[0]


def test_estimate_period_line_space_x_only(line_space_image):
    r = estimate_period(line_space_image)
    assert r.axis_mode == "X"
    assert r.px is not None and abs(r.px - 20) <= 1
    assert r.py is None


def test_estimate_period_flat_none():
    flat = np.full((64, 64), 128, dtype=np.uint8)
    r = estimate_period(flat)
    assert r.axis_mode == "NONE"
    assert r.px is None and r.py is None
    assert "no periodic structure detected" in r.warnings


def test_correct_period_stacks_sharper(grid_image):
    good = stack_cells(grid_image, PX, PY)
    bad = stack_cells(grid_image, PX + 3, PY + 3)
    assert good.shape == (PY, PX)
    _, lap_good, edge_good = ghosting_score(good)
    score_bad, lap_bad, edge_bad = ghosting_score(bad)
    assert lap_good > 2.0 * lap_bad     # ghosting blurs the wrong-period stack
    assert edge_good > edge_bad
    score_good = ghosting_score(good)[0]
    assert score_good > score_bad


def test_refine_period_recovers_truth(grid_image):
    bpx, bpy, blv = refine_period(grid_image, PX - 2, PY - 2, search=4)
    assert (bpx, bpy) == (PX, PY)
    assert blv > 0


def test_tile_coords_complete_cells_only(grid_image):
    coords = tile_coords(grid_image.shape, PX, PY)
    h, w = grid_image.shape
    assert len(coords) == (w // PX) * (h // PY)
    assert all(x + PX <= w and y + PY <= h for x, y in coords)
    assert tile_coords(grid_image.shape, 0, 5) == []


def test_stack_cells_deterministic_sampling(grid_image):
    a = stack_cells(grid_image, PX, PY, sample_n=10, seed=5)
    b = stack_cells(grid_image, PX, PY, sample_n=10, seed=5)
    assert np.array_equal(a, b)


def test_candidate_periods_and_origin():
    cands = candidate_periods(PX, PY, lo=4, hi=128)
    assert cands[0] == (PX, PY)
    assert len(cands) == len(set(cands))
    assert all(4 <= a <= 128 and 4 <= b <= 128 for a, b in cands)
    assert (PX // 2, PY // 2) in cands and (2 * PX, 2 * PY) in cands
    # choose_origin is the documented (0, 0) stub until the M4 phase search
    assert choose_origin((320, 288), PX, PY) == (0, 0)
