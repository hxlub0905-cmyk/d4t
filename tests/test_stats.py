"""Tests for flexadc.core.algo.stats (vendored from PEAR analysis)."""
from __future__ import annotations

import numpy as np

from flexadc.core.algo.glv import ROI
from flexadc.core.algo.stats import (
    attribute_separability,
    cohens_d,
    group_outliers,
)


def test_group_outliers_catches_planted_outlier():
    img = np.zeros((60, 120), dtype=np.uint8)
    # 6 ROIs in one group with a genuine spread of means; rid=4 planted far out
    means = {1: 96, 2: 100, 3: 104, 4: 250, 5: 98, 6: 102}
    rois = [ROI(rid, "g1", (5 + 18 * i, 10, 12, 12)) for i, rid in
            enumerate([1, 2, 3, 4, 5, 6])]
    for r in rois:
        x, y, w, h = r.rect
        img[y:y + h, x:x + w] = means[r.rid]
    out = group_outliers(img, rois, "glv_mean")
    assert out == {4}


def test_group_outliers_skips_small_groups():
    rng = np.random.default_rng(7)
    img = np.clip(rng.normal(100, 3, (40, 80)), 0, 255).astype(np.uint8)
    rois = [ROI(1, "g", (2, 2, 8, 8)), ROI(2, "g", (20, 2, 8, 8)),
            ROI(3, "g", (40, 2, 8, 8))]
    img[2:10, 40:48] = 255       # extreme, but group has < 4 ROIs
    assert group_outliers(img, rois, "glv_mean") == set()


def test_cohens_d_well_separated():
    rng = np.random.default_rng(11)
    a = rng.normal(0.0, 1.0, 50)
    b = rng.normal(10.0, 1.0, 50)
    d = cohens_d(a, b)
    assert d is not None
    assert abs(d) > 5.0
    assert d < 0  # a below b -> negative (a - b) / sp
    # symmetric sign flip
    assert cohens_d(b, a) > 5.0


def test_cohens_d_degenerate():
    assert cohens_d([1.0], [2.0, 3.0]) is None            # too few samples
    assert cohens_d([1.0, 1.0], [1.0, 1.0]) is None       # zero pooled sd


def test_attribute_separability_high_eta2():
    rng = np.random.default_rng(3)
    g1 = rng.normal(0.0, 1.0, 40)
    g2 = rng.normal(10.0, 1.0, 40)
    eta2 = attribute_separability([g1, g2])
    assert eta2 is not None
    assert eta2 > 0.9


def test_attribute_separability_overlapping_low():
    rng = np.random.default_rng(4)
    g1 = rng.normal(0.0, 1.0, 200)
    g2 = rng.normal(0.0, 1.0, 200)
    eta2 = attribute_separability([g1, g2])
    assert eta2 is not None
    assert eta2 < 0.05


def test_attribute_separability_guards():
    assert attribute_separability([[1.0, 2.0]]) is None        # single group
    assert attribute_separability([[], []]) is None            # empty groups
    assert attribute_separability([[5.0, 5.0], [5.0, 5.0]]) == 0.0  # no spread
