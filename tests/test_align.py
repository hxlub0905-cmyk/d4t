"""Tests for adept.core.algo.align (vendored 2026-07-27).

Sign convention under test: target(x, y) == base(x - dx, y - dy) — the target
content sits dx px right / dy px down of the base content, and every backend
must return that same (+dx, +dy).
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from adept.core.algo.align import (
    AlignResult,
    apply_alignment,
    alignment_overlap_slices,
    calculate_alignment,
    calculate_alignment_robust,
    ncc_score,
    parabola_subpx,
    template_align_nm,
)

ALL_METHODS = ["phase", "hybrid", "ncc", "ecc", "template"]

TRUE_DX, TRUE_DY = 4, -3  # planted integer shift (right 4, up 3)


def _base_image(size: int = 160) -> np.ndarray:
    rng = np.random.default_rng(42)
    img = (rng.random((size, size)) * 255).astype(np.float32)
    return cv2.GaussianBlur(img, (0, 0), 3)


def _shift_int(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """target(x, y) = base(x - dx, y - dy) via periodic roll."""
    return np.roll(np.roll(img, dx, axis=1), dy, axis=0)


def _shift_subpx(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """target(x, y) = base(x - dx, y - dy) via linear-interp warp."""
    h, w = img.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


@pytest.mark.parametrize("method", ALL_METHODS)
def test_every_backend_recovers_planted_integer_shift(method):
    base = _base_image()
    target = _shift_int(base, TRUE_DX, TRUE_DY)
    res = calculate_alignment(base, target, method=method, search_radius=8)
    assert isinstance(res, AlignResult)
    # Same sign AND same magnitude for every backend (±0.5 px)
    assert abs(res.dx_subpixel - TRUE_DX) <= 0.5, (method, res.dx_subpixel)
    assert abs(res.dy_subpixel - TRUE_DY) <= 0.5, (method, res.dy_subpixel)
    assert res.dx == TRUE_DX
    assert res.dy == TRUE_DY


@pytest.mark.parametrize("method", ["phase", "template"])
def test_subpixel_shift_recovered(method):
    base = _base_image()
    dx, dy = 2.4, -1.7
    target = _shift_subpx(base, dx, dy)
    res = calculate_alignment(base, target, method=method, search_radius=8)
    assert abs(res.dx_subpixel - dx) <= 0.3, (method, res.dx_subpixel)
    assert abs(res.dy_subpixel - dy) <= 0.3, (method, res.dy_subpixel)


def test_apply_alignment_inverts_planted_shift():
    base = _base_image()
    target = _shift_int(base, TRUE_DX, TRUE_DY)
    aligned = apply_alignment(target, TRUE_DX, TRUE_DY)
    inner = (slice(12, -12), slice(12, -12))
    assert float(np.abs(aligned[inner] - base[inner]).mean()) < 1e-3


@pytest.mark.parametrize("method", ALL_METHODS)
def test_flat_image_guard_no_crash(method):
    flat = np.full((64, 64), 128.0, dtype=np.float32)
    res = calculate_alignment(flat, flat.copy(), method=method, search_radius=8)
    assert res.status == 'fail'
    assert res.dx == 0 and res.dy == 0

    # Direct call of the phase backend must be guarded too
    res2 = calculate_alignment_robust(flat, flat.copy(), search_radius=8)
    assert res2.status == 'fail'


def test_overlap_slices_consistency():
    base = _base_image(96)
    target = _shift_int(base, 5, 2)
    by, bx, ty, tx = alignment_overlap_slices(base.shape[:2], 5, 2)
    # Overlap regions must contain the same scene content -> NCC ~ 1
    assert ncc_score(base[by, bx], target[ty, tx]) > 0.99
    # Negative shifts produce valid, equal-sized slices as well
    by, bx, ty, tx = alignment_overlap_slices((96, 96), -5, -2)
    assert (by.stop - by.start) == (ty.stop - ty.start)
    assert (bx.stop - bx.start) == (tx.stop - tx.start)


def test_template_align_nm_anchor_correction_signs():
    # Synthetic GDS-like template: bright rectangles on dark background.
    tmpl = np.zeros((128, 128), dtype=np.uint8)
    tmpl[30:60, 20:50] = 200
    tmpl[80:100, 70:110] = 200
    tmpl = cv2.GaussianBlur(tmpl, (5, 5), 1.0)
    # SEM structure sits (ex, ey) = (+5, -3) px from the template position.
    sem = np.roll(np.roll(tmpl, 5, axis=1), -3, axis=0)

    dx_nm, dy_nm, score, used_r = template_align_nm(sem, tmpl, nm_per_px=2.0,
                                                    search_radius_px=10)
    # Anchor correction: x negated (GDS anchor x decreases to move right),
    # y follows image-down: (-ex * nm, +ey * nm) = (-10, -6).
    assert score > 0.8
    assert used_r == 10
    assert abs(dx_nm - (-10.0)) <= 1.0
    assert abs(dy_nm - (-6.0)) <= 1.0


def test_template_align_nm_flat_guard():
    flat = np.full((64, 64), 100, dtype=np.uint8)
    dx_nm, dy_nm, score, _ = template_align_nm(flat, flat, 1.0, 8)
    assert (dx_nm, dy_nm, score) == (0.0, 0.0, 0.0)


def test_parabola_subpx_peak_offset():
    res = np.zeros((5, 5), dtype=np.float32)
    res[2, 1], res[2, 2], res[2, 3] = 0.5, 1.0, 0.7  # peak pulled toward +x
    off = parabola_subpx(res, 2, 2, axis=0)
    assert 0.0 < off < 0.5
    # Border peak -> 0.0 (no fit possible)
    assert parabola_subpx(res, 0, 2, axis=0) == 0.0
