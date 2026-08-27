"""演算法模組（純 numpy/cv2，零 Qt）— vendored from KLIP/GLAS/MMH/PEAR/CPE/Fusi³."""
from __future__ import annotations

from .normalize import (
    normalize_image, percentile_range, normalize_image_with_range,
    percentile_range_glv_masked,
)
from .histmatch import (
    match_histogram_exact, match_histogram_linear, match_histogram_percentile,
    MATCH_FN, compute_histogram, image_stats,
)
from .align import (
    AlignResult, apply_alignment, calculate_alignment, calculate_alignment_robust,
    ncc_score, parabola_subpx, template_align_nm,
)
from .snr import (
    snr_signed, compute_snr_map, SnrMapResult,
    center_gaussian_mask,
)
from .roi import NamedROI, ROIStats, MultiROISet, pixel_rect_to_norm
from .glv import glv_value, glv_stats, default_metrics, roi_patch, group_snr, pixel_hist, summarize
from .period import estimate_period, PeriodResult
from .golden import tile_coords, stack_cells, ghosting_score, stack_agreement
from .quality import check_lap_quality, compute_quality, DEFAULT_LAP_THRESHOLD
from .edge import (
    EdgePoint, ScanLine, ScanResult, CRITERIA, TARGETS, AXES,
    find_edges, pair_across, measure_line, scan, choose_axis,
    threshold_level, profile_noise, edge_quality,
)
from .shape import (
    BlobResult, measure_blob, feret, pick_levels, equivalent_diameter,
    roundness,
)
from . import subpixel
