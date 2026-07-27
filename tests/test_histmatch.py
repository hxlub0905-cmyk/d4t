"""Tests for flexadc.core.algo.histmatch (vendored 2026-07-27)."""
from __future__ import annotations

import numpy as np

from flexadc.core.algo.histmatch import (
    MATCH_FN,
    compute_histogram,
    image_stats,
    match_histogram_exact,
    match_histogram_linear,
    match_histogram_percentile,
)


def _images():
    rng = np.random.default_rng(7)
    src = np.clip(rng.normal(100, 20, size=(120, 120)), 0, 255).astype(np.uint8)
    ref = np.clip(rng.normal(150, 10, size=(120, 120)), 0, 255).astype(np.uint8)
    return src, ref


def test_linear_matches_mean_and_std():
    src, ref = _images()
    out = match_histogram_linear(src, ref)
    assert out.dtype == src.dtype
    assert abs(float(out.mean()) - float(ref.mean())) < 2.0
    assert abs(float(out.std()) - float(ref.std())) < 2.0


def test_exact_matches_cdf():
    src, ref = _images()
    out = match_histogram_exact(src, ref)
    assert out.dtype == src.dtype
    # Quantiles of the matched image must track the reference quantiles
    for q in (10, 25, 50, 75, 90):
        assert abs(float(np.percentile(out, q)) - float(np.percentile(ref, q))) <= 3.0


def test_percentile_robust_to_outliers():
    src, ref = _images()
    src = src.copy()
    # Inject 1% hot-pixel outliers at full scale
    rng = np.random.default_rng(11)
    idx = rng.choice(src.size, size=src.size // 100, replace=False)
    src.flat[idx] = 255
    out = match_histogram_percentile(src, ref)
    # The P2/P98 anchors of the result must land on the reference anchors
    assert abs(float(np.percentile(out, 2)) - float(np.percentile(ref, 2))) <= 3.0
    assert abs(float(np.percentile(out, 98)) - float(np.percentile(ref, 98))) <= 3.0


def test_dispatch_table():
    src, ref = _images()
    assert set(MATCH_FN.keys()) == {"exact", "linear", "percentile"}
    for name, fn in MATCH_FN.items():
        out = fn(src, ref)
        assert out.shape == src.shape
        assert out.dtype == src.dtype


def test_compute_histogram_and_stats():
    src, _ = _images()
    counts, edges = compute_histogram(src)
    assert counts.sum() == src.size
    assert len(counts) == 256
    assert len(edges) == 257

    stats = image_stats(src)
    for key in ("mean", "std", "min", "max", "P2", "median", "P98"):
        assert key in stats
    assert stats["P2"] <= stats["median"] <= stats["P98"]
