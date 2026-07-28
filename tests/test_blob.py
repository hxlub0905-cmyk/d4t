"""Tests for adept.core.algo.blob (vendored 2026-07-27)."""
from __future__ import annotations

import numpy as np

from adept.core.algo.blob import DefectROI, segment_defects


def _float_snr_map():
    """Normalized [0, 1] float map (SnrMapResult.map_float shape) with two blobs."""
    rng = np.random.default_rng(21)
    snr = rng.uniform(0.0, 0.05, size=(160, 160)).astype(np.float32)
    snr[40:48, 60:68] = 0.9    # strong blob, 8x8 at (x=60, y=40)
    snr[100:105, 120:125] = 0.6  # weaker blob, 5x5 at (x=120, y=100)
    return snr


def test_finds_planted_blobs_with_float_map():
    snr = _float_snr_map()
    rois = segment_defects(snr, diff_image=snr, min_area=4, snr_threshold=100)
    assert len(rois) == 2
    assert all(isinstance(r, DefectROI) for r in rois)

    strong = rois[0]
    # Strong blob located at the planted position
    assert abs(strong.cx - 63.5) <= 2.0
    assert abs(strong.cy - 43.5) <= 2.0
    # Approximate area (morphological open/close may trim corners)
    assert 50 <= strong.area <= 78
    assert strong.bbox == (strong.x, strong.y, strong.w, strong.h)
    assert 58 <= strong.x <= 61 and 38 <= strong.y <= 41

    weak = rois[1]
    assert abs(weak.cx - 122.0) <= 2.0
    assert abs(weak.cy - 102.0) <= 2.0
    assert 12 <= weak.area <= 30


def test_sorted_by_snr_descending():
    snr = _float_snr_map()
    rois = segment_defects(snr, diff_image=snr, min_area=4, snr_threshold=100)
    values = [r.snr_value for r in rois]
    assert values == sorted(values, reverse=True)
    # snr_value is reported on the legacy 0-255 map scale
    assert abs(rois[0].snr_value - 0.9 * 255) <= 3.0
    assert abs(rois[1].snr_value - 0.6 * 255) <= 3.0


def test_uint8_map_equivalent_to_float_map():
    snr = _float_snr_map()
    u8 = (np.clip(snr, 0, 1) * 255).astype(np.uint8)
    rois_f = segment_defects(snr, diff_image=snr, min_area=4, snr_threshold=100)
    rois_u = segment_defects(u8, diff_image=snr, min_area=4, snr_threshold=100)
    assert len(rois_f) == len(rois_u)
    for rf, ru in zip(rois_f, rois_u):
        assert rf.bbox == ru.bbox
        assert rf.area == ru.area


def test_min_area_filters_small_components():
    snr = _float_snr_map()
    rois = segment_defects(snr, diff_image=snr, min_area=40, snr_threshold=100)
    assert len(rois) == 1  # the 5x5 blob is filtered out


def test_empty_map_returns_empty_list():
    assert segment_defects(np.array([]), np.array([])) == []
