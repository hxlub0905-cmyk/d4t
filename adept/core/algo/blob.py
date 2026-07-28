# ---------------------------------------------------------------------------
# Vendored into ADEPT on 2026-07-27.
# Source project: Perspective-Combination (Fusi3)
# Source file:    perscomb/core/perspective_combine.py
#                 (DefectROI, segment_defects)
# Adaptations:
#   - segment_defects now also accepts a float SNR map in [0, 1] (e.g.
#     snr.SnrMapResult.map_float): float maps with max <= 1.5 are scaled by
#     255 before thresholding, reproducing the legacy uint8 path exactly.
#     uint8 maps and 0-255-scaled float maps behave as before.
#   - DefectROI gains a `bbox` property returning (x, y, w, h).
#   - Algorithm behavior otherwise unchanged.
# ---------------------------------------------------------------------------
"""Defect segmentation from a local SNR map (connected-component labeling)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class DefectROI:
    """Bounding box and metrics for a single detected defect region."""
    x: int
    y: int
    w: int
    h: int
    cx: float                # centroid x
    cy: float                # centroid y
    area: int                # pixel count
    mean_signal: float       # mean diff_image value inside bbox
    snr_value: float         # max SNR inside bbox (0-255 map scale)
    aspect_ratio: float      # w / h
    dist_to_center: float    # Euclidean distance from image center (pixels)

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Bounding box as a pixel-space (x, y, w, h) tuple."""
        return (self.x, self.y, self.w, self.h)


def _snr_map_to_uint8(snr_map: np.ndarray) -> np.ndarray:
    """Coerce an SNR map to the 0-255 uint8 scale used for thresholding.

    Accepts the legacy uint8 map, a float map already on the 0-255 scale, or
    a normalized float map in [0, 1] (SnrMapResult.map_float), which is
    scaled by 255 to reproduce the legacy quantization.
    """
    if snr_map.dtype == np.uint8:
        return snr_map
    map_f = snr_map.astype(np.float32)
    if map_f.size > 0 and float(map_f.max()) <= 1.5:
        map_f = map_f * 255.0
    return np.clip(map_f, 0, 255).astype(np.uint8)


def segment_defects(
    snr_map: np.ndarray,
    diff_image: np.ndarray,
    min_area: int = 4,
    snr_threshold: Optional[float] = None,
) -> List[DefectROI]:
    """Segment defect regions from SNR map using adaptive thresholding.

    Parameters
    ----------
    snr_map : uint8 SNR map (0-255) or float map in [0, 1]
              (e.g. SnrMapResult.map_float)
    diff_image : float32 or uint8 difference image (same shape as snr_map)
    min_area : minimum connected-component area (pixels) to keep
    snr_threshold : manual SNR threshold (0-255 map scale); if None, Otsu is used

    Returns
    -------
    List of DefectROI sorted by snr_value descending.
    """
    if snr_map is None or snr_map.size == 0:
        return []

    snr_u8 = _snr_map_to_uint8(snr_map)

    # Threshold
    if snr_threshold is not None:
        thresh_val = int(np.clip(snr_threshold, 0, 255))
        _, binary = cv2.threshold(snr_u8, thresh_val, 255, cv2.THRESH_BINARY)
    else:
        # Otsu on non-border region
        _, binary = cv2.threshold(snr_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Morphological clean-up: remove isolated noise, fill small gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    # Connected components
    n_labels, labels, stats_cc, centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )

    H, W = snr_map.shape[:2]
    img_cx, img_cy = W / 2.0, H / 2.0

    diff_f = diff_image.astype(np.float32)
    if diff_f.max() > 1.5:
        diff_f = diff_f / 255.0

    rois: List[DefectROI] = []
    for label_idx in range(1, n_labels):  # skip background (label 0)
        area = int(stats_cc[label_idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue

        bx = int(stats_cc[label_idx, cv2.CC_STAT_LEFT])
        by = int(stats_cc[label_idx, cv2.CC_STAT_TOP])
        bw = int(stats_cc[label_idx, cv2.CC_STAT_WIDTH])
        bh = int(stats_cc[label_idx, cv2.CC_STAT_HEIGHT])
        cx_roi = float(centroids[label_idx, 0])
        cy_roi = float(centroids[label_idx, 1])

        mask_roi = (labels[by:by + bh, bx:bx + bw] == label_idx)
        diff_crop = diff_f[by:by + bh, bx:bx + bw]
        snr_crop = snr_u8[by:by + bh, bx:bx + bw].astype(np.float32)

        mean_sig = float(diff_crop[mask_roi].mean()) if mask_roi.any() else 0.0
        snr_val = float(snr_crop[mask_roi].max()) if mask_roi.any() else 0.0
        aspect = bw / max(bh, 1)
        dist = float(np.hypot(cx_roi - img_cx, cy_roi - img_cy))

        rois.append(DefectROI(
            x=bx, y=by, w=bw, h=bh,
            cx=cx_roi, cy=cy_roi,
            area=area,
            mean_signal=mean_sig,
            snr_value=snr_val,
            aspect_ratio=aspect,
            dist_to_center=dist,
        ))

    rois.sort(key=lambda r: r.snr_value, reverse=True)
    return rois
