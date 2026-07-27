"""Tests for flexadc.core.algo.normalize (vendored 2026-07-27)."""
from __future__ import annotations

import numpy as np

from flexadc.core.algo.normalize import (
    GLV_MASK_MIN_PIXELS,
    normalize_image,
    normalize_image_with_range,
    percentile_range,
    percentile_range_glv_masked,
)


def _rng():
    return np.random.default_rng(1234)


def test_normalize_image_output_range():
    img = (_rng().random((80, 80)) * 255).astype(np.float32)
    out = normalize_image(img)
    assert out.min() >= 0.0
    assert out.max() <= 1.0
    # Bulk of pixels must actually use the range (P2/P98 anchoring)
    assert out.max() > 0.9
    assert out.min() < 0.1


def test_normalize_image_constant_no_crash():
    img = np.full((32, 32), 77.0, dtype=np.float32)
    out = normalize_image(img)
    assert np.all(out >= 0.0) and np.all(out <= 1.0)


def test_percentile_range_and_with_range_roundtrip():
    img = (_rng().random((64, 64)) * 200 + 20).astype(np.float32)
    p_lo, p_hi = percentile_range(img)
    assert p_lo < p_hi
    out = normalize_image_with_range(img, p_lo, p_hi)
    assert out.min() >= 0.0 and out.max() <= 1.0
    # Same anchors as normalize_image -> identical result
    np.testing.assert_allclose(out, normalize_image(img), atol=1e-5)


def test_glv_masked_uses_only_in_band_pixels():
    rng = _rng()
    # Background population 0-50, pattern population 110-145, outliers at 250.
    bg = rng.uniform(0, 50, size=6000)
    band = rng.uniform(110, 145, size=2500)
    outliers = np.full(100, 250.0)
    img = np.concatenate([bg, band, outliers]).astype(np.float32)
    rng.shuffle(img)
    img = img.reshape(86, 100)

    p_lo, p_hi = percentile_range_glv_masked(img, 110, 145)
    # Anchors must come exclusively from the in-band population
    assert 110.0 <= p_lo <= 145.0
    assert 110.0 <= p_hi <= 145.0
    assert p_lo < p_hi

    # Full-image percentile is dominated by the background population
    full_lo, full_hi = percentile_range(img)
    assert full_lo < 60.0
    assert p_lo > full_lo


def test_glv_masked_fallback_when_too_few_pixels():
    rng = _rng()
    img = rng.uniform(0, 50, size=(50, 50)).astype(np.float32)
    # Only 10 pixels inside the band -> below GLV_MASK_MIN_PIXELS -> fallback
    img.flat[:10] = 120.0
    assert 10 < GLV_MASK_MIN_PIXELS
    masked = percentile_range_glv_masked(img, 110, 145)
    full = percentile_range(img)
    assert masked == full
