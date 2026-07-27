"""Tests for flexadc.core.algo.roi (vendored 2026-07-27)."""
from __future__ import annotations

import numpy as np

from flexadc.core.algo.roi import (
    MultiROISet,
    NamedROI,
    ROIStats,
    pixel_rect_to_norm,
)

SHAPE = (200, 300)  # (H, W)


def _named(norm_rect, roi_type='reference'):
    return NamedROI(id='x', label='X', roi_type=roi_type,
                    color_bgr=(255, 255, 0), norm_rect=norm_rect)


def test_pixel_norm_roundtrip():
    rect = (30, 40, 50, 60)
    norm = pixel_rect_to_norm(rect, SHAPE)
    assert all(0.0 <= v <= 1.0 for v in norm)
    back = _named(norm).to_pixel_rect(SHAPE)
    assert back == rect


def test_pixel_rect_to_norm_clamps_out_of_bounds():
    # Rect extends past the right/bottom edge -> size clamped
    norm = pixel_rect_to_norm((280, 190, 50, 40), SHAPE)
    back = _named(norm).to_pixel_rect(SHAPE)
    assert back == (280, 190, 20, 10)
    # Negative origin -> clamped to 0
    norm2 = pixel_rect_to_norm((-10, -5, 40, 30), SHAPE)
    back2 = _named(norm2).to_pixel_rect(SHAPE)
    assert back2 == (0, 0, 40, 30)


def test_to_pixel_rect_clamps_norm_overflow():
    # norm_rect spilling past 1.0 gets clamped to the image bounds
    roi = _named((0.95, 0.9, 0.2, 0.2))
    x, y, w, h = roi.to_pixel_rect(SHAPE)
    assert (x, y) == (285, 180)
    assert x + w <= SHAPE[1]
    assert y + h <= SHAPE[0]
    assert w >= 1 and h >= 1


def test_crop_matches_pixel_rect():
    img = np.arange(SHAPE[0] * SHAPE[1], dtype=np.float32).reshape(SHAPE)
    roi = _named(pixel_rect_to_norm((30, 40, 50, 60), SHAPE))
    crop = roi.crop(img)
    assert crop.shape == (60, 50)
    assert crop[0, 0] == img[40, 30]


def test_shifted_offset_math():
    rs = MultiROISet()
    rid = rs.add_roi((0.2, 0.3, 0.1, 0.1))
    ref_shape = (100, 200)  # (H, W)
    shifted = rs.shifted(dx=30, dy=-15, ref_shape=ref_shape)
    nx, ny, nw, nh = shifted.get_by_id(rid).norm_rect
    assert abs(nx - (0.2 + 30 / 200)) < 1e-9
    assert abs(ny - (0.3 - 15 / 100)) < 1e-9
    assert (nw, nh) == (0.1, 0.1)
    # Original set untouched
    assert rs.get_by_id(rid).norm_rect == (0.2, 0.3, 0.1, 0.1)


def test_shifted_clamps_at_edges():
    rs = MultiROISet()
    rid = rs.add_roi((0.85, 0.1, 0.1, 0.1))
    shifted = rs.shifted(dx=50, dy=0, ref_shape=(100, 200))
    nx, ny, nw, nh = shifted.get_by_id(rid).norm_rect
    assert abs(nx - 0.9) < 1e-9  # clamped to 1.0 - nw, size preserved
    assert (nw, nh) == (0.1, 0.1)


def test_generate_grid_count_and_positions():
    rs = MultiROISet()
    rects = rs.generate_grid(
        anchor_tl_norm=(0.1, 0.1),
        anchor_br_norm=(0.9, 0.9),
        cols=3,
        rows=2,
        roi_w_px=20,
        roi_h_px=20,
        img_shape=(200, 200),
    )
    assert len(rects) == 3 * 2
    # First rect centered on the top-left anchor
    nx, ny, nw, nh = rects[0]
    assert abs(nx - (0.1 * 200 - 10) / 200) < 1e-9
    assert abs(ny - (0.1 * 200 - 10) / 200) < 1e-9
    assert (nw, nh) == (20 / 200, 20 / 200)
    # Last rect centered on the bottom-right anchor
    nx_l, ny_l, _, _ = rects[-1]
    assert abs(nx_l - (0.9 * 200 - 10) / 200) < 1e-9
    assert abs(ny_l - (0.9 * 200 - 10) / 200) < 1e-9
    # Grid generation does not add ROIs to the set
    assert len(rs) == 0


def test_exactly_one_target_invariant():
    rs = MultiROISet()
    ref_id = rs.add_roi((0.1, 0.1, 0.1, 0.1))
    t1 = rs.add_roi((0.3, 0.3, 0.1, 0.1), roi_type='target')
    t2 = rs.add_roi((0.5, 0.5, 0.1, 0.1), roi_type='target')

    targets = [r for r in rs.rois if r.roi_type == 'target']
    assert len(targets) == 1
    assert targets[0].id == t2
    assert rs.get_by_id(t1).roi_type == 'reference'

    # Promoting another ROI keeps the invariant
    assert rs.set_target(ref_id)
    targets = [r for r in rs.rois if r.roi_type == 'target']
    assert len(targets) == 1
    assert targets[0].id == ref_id
    assert rs.get_target().id == ref_id
    assert len(rs.get_references()) == 2

    # Demote the target -> no target at all
    assert rs.set_reference(ref_id)
    assert rs.get_target() is None


def test_roistats_from_pixels():
    rng = np.random.default_rng(2)
    px = rng.normal(100, 10, size=(20, 20))
    st = ROIStats.from_pixels(px)
    assert st.pixel_count == 400
    assert abs(st.mean - float(px.mean())) < 0.1
    assert st.p2 < st.median < st.p98
    empty = ROIStats.from_pixels(np.array([]))
    assert empty.pixel_count == 0
