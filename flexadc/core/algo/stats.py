# Vendored into FlexADC on 2026-07-27.
# Source project: PEAR — pear/core/analysis.py
#   (group_outliers, cohens_d, attribute_separability)
# Adaptations:
#   - Split the statistics helpers out of PEAR's analysis module; ROI and
#     roi_metric are imported from the sibling vendored module
#     `flexadc.core.algo.glv` instead of pear.core.attributes.
#   - No algorithmic changes.
"""组间/组内统计 — outlier detection and group separability, vendored from PEAR.

* ``group_outliers``          — Tukey IQR outliers within each ROI group.
* ``cohens_d``                — standardized mean difference of two samples.
* ``attribute_separability``  — η² (eta squared), fraction of a metric's
  variance explained by group membership.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from flexadc.core.algo.glv import ROI, roi_metric


def group_outliers(image: np.ndarray, rois: List[ROI], mid: str,
                   k: float = 1.5) -> set:
    """rids that are Tukey outliers of ``mid`` *within their own group*.

    A value outside ``[Q1 − k·IQR, Q3 + k·IQR]`` is an outlier. Groups with
    fewer than 4 ROIs (too few for a stable IQR) are skipped.
    """
    out: set = set()
    by_gid: Dict[str, List[ROI]] = {}
    for r in rois:
        by_gid.setdefault(r.gid, []).append(r)
    for grs in by_gid.values():
        if len(grs) < 4:
            continue
        vals = np.array([roi_metric(image, r, mid) for r in grs],
                        dtype=np.float64)
        q1, q3 = float(np.percentile(vals, 25)), float(np.percentile(vals, 75))
        iqr = q3 - q1
        if iqr <= 1e-12:
            continue
        lo, hi = q1 - k * iqr, q3 + k * iqr
        for r, v in zip(grs, vals):
            if v < lo or v > hi:
                out.add(r.rid)
    return out


def cohens_d(a, b) -> Optional[float]:
    """Standardized mean difference (a − b) / pooled_sd. None if degenerate."""
    a = np.asarray(a, dtype=np.float64)
    a = a[np.isfinite(a)]
    b = np.asarray(b, dtype=np.float64)
    b = b[np.isfinite(b)]
    if a.size < 2 or b.size < 2:
        return None
    na, nb = a.size, b.size
    sp2 = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
    sp = float(np.sqrt(sp2))
    if sp < 1e-12:
        return None
    return float((a.mean() - b.mean()) / sp)


def attribute_separability(groups_vals) -> Optional[float]:
    """η² (variance of a metric explained by group) in [0, 1]; higher = better
    separation between groups. Needs 2+ non-empty groups with spread."""
    arrs = [np.asarray(v, dtype=np.float64) for v in groups_vals]
    arrs = [a[np.isfinite(a)] for a in arrs]
    arrs = [a for a in arrs if a.size]
    if len(arrs) < 2:
        return None
    allv = np.concatenate(arrs)
    if allv.size < 2:
        return None
    grand = float(allv.mean())
    ss_total = float(((allv - grand) ** 2).sum())
    if ss_total < 1e-12:
        return 0.0
    ss_between = float(sum(a.size * (float(a.mean()) - grand) ** 2 for a in arrs))
    return max(0.0, min(1.0, ss_between / ss_total))
