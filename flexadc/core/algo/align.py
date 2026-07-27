# ---------------------------------------------------------------------------
# Vendored into FlexADC on 2026-07-27.
# Source projects/files:
#   - Perspective-Combination (Fusi3): perscomb/core/perspective_combine.py
#       (_apply_alignment, _alignment_overlap_slices, _ncc_score,
#        _calculate_alignment_scores, _calculate_alignment_ncc,
#        _calculate_alignment_ecc, _calculate_alignment_template,
#        _calculate_alignment)
#   - Perspective-Combination (Fusi3): perscomb/core/ebeam_snr.py
#       (AlignResult, _preprocess_for_align, calculate_alignment_robust)
#   - GLAS: glas/core/fine_align.py
#       (fine_align_one, _parabola_subpx)
# Adaptations:
#   - Leading underscores dropped from vendored public helper names
#     (apply_alignment, alignment_overlap_slices, ncc_score, parabola_subpx);
#     backend implementations stay private, dispatched via calculate_alignment.
#   - Normalization helpers imported from flexadc.core.algo.normalize instead
#     of module-local copies.
#   - SIGN FIX in the ECC backend: cv2.findTransformECC warps the input image
#     with WARP_INVERSE_MAP internally, i.e. warped(x) = target(x + t), so the
#     converged translation t equals (+dx, +dy) in this module's convention.
#     The original code seeded the warp with (-dx, -dy) and returned
#     dx = -t.x / dy = -t.y, which produced a shift with the OPPOSITE sign of
#     the phase/ncc/template backends (verified empirically on planted
#     shifts). The vendored version seeds with (+dx, +dy) and returns
#     dx = +t.x / dy = +t.y so all backends share one convention.
#   - Flat-image guard added: calculate_alignment and
#     calculate_alignment_robust return a zero-shift 'fail' AlignResult when
#     either input is constant (std < 1e-9); previously cv2.phaseCorrelate on
#     an all-zero edge map could yield NaN and crash int(round(...)).
#   - GLAS fine_align_one renamed template_align_nm; its "cv2 is None" import
#     guard removed (cv2 is a hard dependency of this package).
#   - Explicit .astype(np.float32) added before cv2.warpAffine in the scoring
#     paths (normalize_image upcasts to float64 via np.percentile).
#   - Algorithm behavior otherwise unchanged.
# ---------------------------------------------------------------------------
"""Image-to-image translation alignment backends for SEM defect imaging.

(dx, dy) SIGN CONVENTION (all ``calculate_alignment*`` backends)
----------------------------------------------------------------
The returned shift is the displacement of **target relative to base**, in
image pixel coordinates with +x = right (columns) and +y = down (rows):

    target(x, y) == base(x - dx, y - dy)

i.e. if the target's content appears ``dx`` pixels to the right of and ``dy``
pixels below the same content in the base image, every backend ("phase",
"hybrid", "ncc", "ecc", "template") returns positive ``(dx, dy)``.
Consequently ``apply_alignment(target, dx, dy)`` shifts the target content
back by ``(-dx, -dy)`` and registers it onto the base image.

Exception: :func:`template_align_nm` (vendored from GLAS) does NOT return an
image-space (dx, dy); it returns a GDS overlay *anchor correction* in
nanometres, where the x component is negated (GDS anchor x decreases to move
the overlay right) and y follows the image-down direction. See its docstring.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np

from .normalize import normalize_image


@dataclass
class AlignResult:
    """Result of robust alignment process."""
    dx: int
    dy: int
    score_phase: float
    score_ncc: float
    score_residual: float
    final_score: float
    status: str  # 'ok', 'warn', 'fail'
    method: str  # 'phase', 'ncc', 'fallback'
    # Sub-pixel precision offsets (default to integer values for backward compat)
    dx_subpixel: float = 0.0
    dy_subpixel: float = 0.0


def apply_alignment(image: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Apply sub-pixel translation to image using affine warp (INTER_LINEAR).

    Shifts the image content by (-dx, -dy): given ``target(x, y) == base(x -
    dx, y - dy)``, ``apply_alignment(target, dx, dy)`` registers the target
    onto the base.
    """
    if image is None:
        return None

    h, w = image.shape[:2]
    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
    aligned = cv2.warpAffine(image, M, (w, h),
                             flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)
    return aligned


def alignment_overlap_slices(shape: Tuple[int, int], dx: int, dy: int) -> Tuple[slice, slice, slice, slice]:
    """Return slices for overlapping regions given a shift.

    Returns ``(base_y, base_x, target_y, target_x)`` such that
    ``base[base_y, base_x]`` and ``target[target_y, target_x]`` cover the same
    scene content when the target is displaced by ``(dx, dy)`` relative to the
    base (see module docstring for the sign convention).
    """
    h, w = shape
    if dx >= 0:
        base_x = slice(0, w - dx)
        target_x = slice(dx, w)
    else:
        base_x = slice(-dx, w)
        target_x = slice(0, w + dx)

    if dy >= 0:
        base_y = slice(0, h - dy)
        target_y = slice(dy, h)
    else:
        base_y = slice(-dy, h)
        target_y = slice(0, h + dy)

    return base_y, base_x, target_y, target_x


def ncc_score(a: np.ndarray, b: np.ndarray) -> float:
    """Compute normalized cross-correlation score between two same-shape arrays."""
    a_mean = float(np.mean(a))
    b_mean = float(np.mean(b))
    a_z = a - a_mean
    b_z = b - b_mean
    denom = float(np.sqrt(np.sum(a_z ** 2) * np.sum(b_z ** 2))) + 1e-6
    return float(np.sum(a_z * b_z) / denom)


def _calculate_alignment_scores(
    base: np.ndarray,
    target: np.ndarray,
    dx: int,
    dy: int,
    phase_score: float = 0.0,
    method: str = "phase"
) -> Tuple[float, float, float]:
    """Calculate NCC, residual, and final score for a given shift."""
    base_norm = normalize_image(base.astype(np.float32))
    target_norm = normalize_image(target.astype(np.float32))
    aligned_target = apply_alignment(target_norm.astype(np.float32), dx, dy)
    residual = float(np.mean(np.abs(base_norm - aligned_target)))
    score_residual = max(0.0, 1.0 - residual * 2.0)

    by, bx, ty, tx = alignment_overlap_slices(base_norm.shape[:2], dx, dy)
    if by.stop <= by.start or bx.stop <= bx.start:
        score_ncc = 0.0
    else:
        score_ncc = (ncc_score(base_norm[by, bx], target_norm[ty, tx]) + 1.0) / 2.0

    if method == "ncc":
        final_score = (0.6 * score_ncc + 0.4 * score_residual) * 100.0
    else:
        final_score = (0.4 * phase_score + 0.6 * score_residual) * 100.0

    return score_ncc, score_residual, final_score


# ---------------------------------------------------------------------------
# Phase-correlation backend (vendored from ebeam_snr.py)
# ---------------------------------------------------------------------------

def _preprocess_for_align(img: np.ndarray) -> np.ndarray:
    """Preprocess image for alignment (Robust Norm + Sobel)."""
    if img is None:
        return None

    img_f = img.astype(np.float32)
    # Robust normalization (5th-95th percentile)
    p5, p95 = np.percentile(img_f, [5, 95])
    rng = p95 - p5
    if rng < 1e-6:
        rng = 1.0
    img_n = np.clip((img_f - p5) / rng, 0, 1)

    # Sobel Edge Detection
    # Ensure explicit float32 for OpenCV compatibility
    gx = cv2.Sobel(img_n.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(img_n.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)

    # Normalize magnitude
    mmax = mag.max()
    if mmax > 1e-6:
        mag /= mmax

    return mag


def _is_flat(img: np.ndarray) -> bool:
    """True when the image is constant (no signal for any alignment backend)."""
    return float(np.std(img.astype(np.float32))) < 1e-9


def calculate_alignment_robust(
    base: np.ndarray,
    target: np.ndarray,
    search_radius: int = 40
) -> AlignResult:
    """Layered robust alignment strategy.

    Strategy:
    1. Preprocess (Edge map) to ignore brightness diffs.
    2. Phase Correlation (Layer 1) for fast translation estimate.
    3. Verification & Grading.
    """
    if base is None or target is None:
        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')

    if _is_flat(base) or _is_flat(target):
        # Flat-image guard: phase correlation on a zero edge map is undefined.
        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')

    h, w = base.shape[:2]

    # Performance guard for very large images:
    # phaseCorrelate runs FFT internally, so runtime grows quickly with image size.
    # Downsample to a working resolution, then scale sub-pixel shift back.
    max_dim = max(h, w)
    align_max_dim = 2048
    scale_x = 1.0
    scale_y = 1.0
    if max_dim > align_max_dim:
        down = align_max_dim / float(max_dim)
        work_w = max(64, int(round(w * down)))
        work_h = max(64, int(round(h * down)))
        scale_x = w / float(work_w)
        scale_y = h / float(work_h)
    else:
        work_w = w
        work_h = h

    # 1. Preprocessing
    base_edge = _preprocess_for_align(base)
    target_edge = _preprocess_for_align(target)
    if (work_w, work_h) != (w, h):
        base_edge = cv2.resize(base_edge, (work_w, work_h), interpolation=cv2.INTER_AREA)
        target_edge = cv2.resize(target_edge, (work_w, work_h), interpolation=cv2.INTER_AREA)

    # 2. Phase Correlation (Layer 1)
    # Create Hanning window to reduce edge effects
    hann = cv2.createHanningWindow((work_w, work_h), cv2.CV_32F)
    (dx_p, dy_p), response_p = cv2.phaseCorrelate(base_edge, target_edge, window=hann)

    # Convert working-resolution shift back to original coordinates.
    dx_p *= scale_x
    dy_p *= scale_y

    # Convert phase shift (target->base)
    # cv2.phaseCorrelate returns shift of src2 relative to src1.
    # So dx, dy is the shift.

    # 3. Residual Verification
    # Shift target edge back by (-dx, -dy)
    M = np.float32([[1, 0, -(dx_p / scale_x)], [0, 1, -(dy_p / scale_y)]])
    aligned_edge = cv2.warpAffine(target_edge, M, (work_w, work_h), flags=cv2.INTER_LINEAR)

    # Calculate residual (Difference in overlap area)
    diff = np.abs(base_edge - aligned_edge)
    # Ignore border regions affected by shift
    border = 5 + int(max(abs(dx_p / scale_x), abs(dy_p / scale_y)))
    if border < work_h // 2 and border < work_w // 2:
        valid_diff = diff[border:-border, border:-border]
    else:
        valid_diff = diff

    residual_mean = float(np.mean(valid_diff))
    score_residual = max(0.0, 1.0 - residual_mean * 2.0)  # Heuristic scaling

    # 4. Composite Score
    # Weights: Phase=0.4, NCC/Legacy=0.0 (using residual instead), Residual=0.6
    final_score = (0.4 * response_p + 0.6 * score_residual) * 100.0

    # 5. Grading
    status = 'ok'
    if final_score < 75:
        status = 'warn'
    if final_score < 55:
        status = 'fail'

    # Limit shift to search radius
    if abs(dx_p) > search_radius or abs(dy_p) > search_radius:
        # If phase corr says huge shift, it might be wrong (or just huge).
        # Report it but warn.
        status = 'warn'

    return AlignResult(
        dx=int(round(dx_p)),
        dy=int(round(dy_p)),
        score_phase=float(response_p),
        score_ncc=0.0,  # Not computed yet
        score_residual=score_residual,
        final_score=final_score,
        status=status,
        method='phase',
        dx_subpixel=float(dx_p),
        dy_subpixel=float(dy_p),
    )


# ---------------------------------------------------------------------------
# NCC backend
# ---------------------------------------------------------------------------

def _calculate_alignment_ncc(
    base: np.ndarray,
    target: np.ndarray,
    search_radius: int = 40
) -> AlignResult:
    """NCC alignment with coarse-to-fine search for efficiency.

    Uses a two-stage approach:
    1. Coarse search with step=4 over full radius
    2. Fine search with step=1 in ±4 pixel neighborhood around best

    This reduces computation from ~6561 to ~400 NCC evaluations.
    """
    if base is None or target is None:
        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')

    base_f = normalize_image(base.astype(np.float32))
    target_f = normalize_image(target.astype(np.float32))
    h, w = base_f.shape[:2]

    def search_best(cx, cy, radius, step):
        best_score = -1.0
        best_dx, best_dy = cx, cy
        for dy in range(cy - radius, cy + radius + 1, step):
            for dx in range(cx - radius, cx + radius + 1, step):
                by, bx, ty, tx = alignment_overlap_slices((h, w), dx, dy)
                if by.stop <= by.start or bx.stop <= bx.start:
                    continue
                score = ncc_score(base_f[by, bx], target_f[ty, tx])
                if score > best_score:
                    best_score = score
                    best_dx = dx
                    best_dy = dy
        return best_dx, best_dy, best_score

    # Stage 1: Coarse search (step=4)
    coarse_step = 4
    coarse_dx, coarse_dy, _ = search_best(0, 0, search_radius, coarse_step)

    # Stage 2: Fine search (step=1) around coarse result
    fine_radius = coarse_step
    best_dx, best_dy, best_score = search_best(coarse_dx, coarse_dy, fine_radius, 1)

    # Stage 3: Parabolic sub-pixel refinement on the NCC surface
    # Fit parabola along each axis at the integer peak.
    def _ncc_at(ddx, ddy):
        by, bx, ty, tx = alignment_overlap_slices((h, w), ddx, ddy)
        if by.stop <= by.start or bx.stop <= bx.start:
            return -1.0
        return ncc_score(base_f[by, bx], target_f[ty, tx])

    def _parabolic_offset(f_neg, f_0, f_pos):
        denom = 2.0 * (f_pos - 2.0 * f_0 + f_neg)
        if abs(denom) < 1e-8:
            return 0.0
        return -(f_pos - f_neg) / denom

    dx_sub = best_dx + _parabolic_offset(
        _ncc_at(best_dx - 1, best_dy),
        best_score,
        _ncc_at(best_dx + 1, best_dy),
    )
    dy_sub = best_dy + _parabolic_offset(
        _ncc_at(best_dx, best_dy - 1),
        best_score,
        _ncc_at(best_dx, best_dy + 1),
    )

    aligned_target = apply_alignment(target_f.astype(np.float32), dx_sub, dy_sub)
    residual = float(np.mean(np.abs(base_f - aligned_target)))
    score_residual = max(0.0, 1.0 - residual * 2.0)
    score_ncc = (best_score + 1.0) / 2.0
    final_score = (0.6 * score_ncc + 0.4 * score_residual) * 100.0

    status = 'ok'
    if final_score < 75:
        status = 'warn'
    if final_score < 55:
        status = 'fail'

    return AlignResult(
        dx=int(best_dx),
        dy=int(best_dy),
        score_phase=0.0,
        score_ncc=score_ncc,
        score_residual=score_residual,
        final_score=final_score,
        status=status,
        method='ncc',
        dx_subpixel=float(dx_sub),
        dy_subpixel=float(dy_sub),
    )


# ---------------------------------------------------------------------------
# ECC backend
# ---------------------------------------------------------------------------

def _calculate_alignment_ecc(
    base: np.ndarray,
    target: np.ndarray,
    search_radius: int = 40
) -> AlignResult:
    """ECC (Enhanced Correlation Coefficient) alignment.

    Strategy:
    1. Run Phase Correlation for a fast initial shift estimate.
    2. Refine with cv2.findTransformECC on percentile-normalised grayscale.
       ECC's criterion is inherently invariant to affine intensity changes
       (brightness + contrast), so Sobel edge-map preprocessing is not needed
       and would actually hurt convergence (sparse maps → near-zero gradients).
    3. Accept the ECC result only when it stays within search_radius; otherwise
       fall back to the Phase estimate.
    4. Score with NCC + residual (same weights as NCC method).
    """
    if base is None or target is None:
        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')

    # Step 1: Phase initial estimate
    phase_result = calculate_alignment_robust(base, target, search_radius)

    # Step 2: Normalise to float32 [0, 1].  ECC already handles contrast /
    # brightness differences, so plain percentile normalisation is sufficient.
    # Cast explicitly: normalize_image upcasts to float64 due to numpy
    # percentile, but findTransformECC only accepts CV_8U or CV_32F.
    base_f = normalize_image(base.astype(np.float32)).astype(np.float32)
    target_f = normalize_image(target.astype(np.float32)).astype(np.float32)

    # findTransformECC warps the input (target) with WARP_INVERSE_MAP, i.e.
    # warped(x) = target(x + t); a target displaced by (+dx, +dy) therefore
    # converges to t = (+dx, +dy). Seed with the phase estimate directly.
    # (Sign fixed during vendoring — see file header.)
    warp_matrix = np.float32([
        [1.0, 0.0, phase_result.dx_subpixel],
        [0.0, 1.0, phase_result.dy_subpixel],
    ])

    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
        100,   # max iterations
        1e-4,  # convergence epsilon
    )

    dx_ecc = phase_result.dx_subpixel
    dy_ecc = phase_result.dy_subpixel

    try:
        # Use positional arguments for broader OpenCV version compatibility.
        _cc, warp_out = cv2.findTransformECC(
            base_f, target_f, warp_matrix, cv2.MOTION_TRANSLATION, criteria,
        )
        dx_candidate = float(warp_out[0, 2])
        dy_candidate = float(warp_out[1, 2])
        # Accept only when ECC stayed within the expected search range.
        if abs(dx_candidate) <= search_radius and abs(dy_candidate) <= search_radius:
            dx_ecc = dx_candidate
            dy_ecc = dy_candidate
    except cv2.error:
        pass  # keep Phase fallback

    dx_ecc = float(np.clip(dx_ecc, -search_radius, search_radius))
    dy_ecc = float(np.clip(dy_ecc, -search_radius, search_radius))

    # Score using NCC + residual on aligned overlap
    score_ncc, score_residual, final_score = _calculate_alignment_scores(
        base, target, int(round(dx_ecc)), int(round(dy_ecc)),
        phase_score=0.0, method='ncc',
    )

    status = 'ok'
    if final_score < 75:
        status = 'warn'
    if final_score < 55:
        status = 'fail'

    return AlignResult(
        dx=int(round(dx_ecc)),
        dy=int(round(dy_ecc)),
        score_phase=phase_result.score_phase,
        score_ncc=score_ncc,
        score_residual=score_residual,
        final_score=final_score,
        status=status,
        method='ecc',
        dx_subpixel=dx_ecc,
        dy_subpixel=dy_ecc,
    )


# ---------------------------------------------------------------------------
# Template-matching backend
# ---------------------------------------------------------------------------

def _calculate_alignment_template(
    base: np.ndarray,
    target: np.ndarray,
    search_radius: int = 40,
) -> AlignResult:
    """Template-matching alignment using a centre-crop template.

    Strategy:
    1. Crop the centre (image − 2×search_radius) region of the normalised
       base as the template; this avoids border scan-artifacts common in SEM.
    2. Run cv2.matchTemplate(TM_CCOEFF_NORMED) against the full normalised
       target.  OpenCV uses FFT internally → O(N log N), comparable to Phase.
    3. Sub-pixel precision via parabolic fit on the correlation peak,
       identical to the NCC method.
    4. Fall back to Phase when the image is too small for the search radius.
    """
    if base is None or target is None:
        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')

    h, w = base.shape[:2]
    sr = search_radius

    # Guard: template must be at least 8 px in each dimension
    if h <= 2 * sr + 8 or w <= 2 * sr + 8:
        return calculate_alignment_robust(base, target, sr)

    # Normalise to float32 [0, 1]; cast explicitly to float32 because
    # normalize_image upcasts to float64 (numpy percentile returns float64)
    # and matchTemplate only accepts CV_8U or CV_32F.
    base_f = normalize_image(base.astype(np.float32)).astype(np.float32)
    target_f = normalize_image(target.astype(np.float32)).astype(np.float32)

    # Template = centre crop of base; result_map shape = (2*sr+1, 2*sr+1)
    template = base_f[sr: h - sr, sr: w - sr]
    result_map = cv2.matchTemplate(target_f, template, cv2.TM_CCOEFF_NORMED)

    # Peak location → integer shift
    _, best_score, _, max_loc = cv2.minMaxLoc(result_map)
    peak_x, peak_y = max_loc          # (col, row) in result_map
    best_dx = peak_x - sr             # shift in x (cols)
    best_dy = peak_y - sr             # shift in y (rows)

    # Parabolic sub-pixel refinement along each axis
    def _val(x: int, y: int) -> float:
        if 0 <= y < result_map.shape[0] and 0 <= x < result_map.shape[1]:
            return float(result_map[y, x])
        return -1.0

    def _parabolic_offset(f_neg: float, f_0: float, f_pos: float) -> float:
        denom = 2.0 * (f_pos - 2.0 * f_0 + f_neg)
        if abs(denom) < 1e-8:
            return 0.0
        return -(f_pos - f_neg) / denom

    dx_sub = best_dx + _parabolic_offset(
        _val(peak_x - 1, peak_y), best_score, _val(peak_x + 1, peak_y)
    )
    dy_sub = best_dy + _parabolic_offset(
        _val(peak_x, peak_y - 1), best_score, _val(peak_x, peak_y + 1)
    )

    # Final composite score (NCC on aligned overlap + residual)
    score_ncc, score_residual, final_score = _calculate_alignment_scores(
        base, target, int(round(dx_sub)), int(round(dy_sub)),
        phase_score=0.0, method='ncc',
    )

    status = 'ok'
    if final_score < 75:
        status = 'warn'
    if final_score < 55:
        status = 'fail'

    return AlignResult(
        dx=int(round(dx_sub)),
        dy=int(round(dy_sub)),
        score_phase=float(best_score),
        score_ncc=score_ncc,
        score_residual=score_residual,
        final_score=final_score,
        status=status,
        method='template',
        dx_subpixel=float(dx_sub),
        dy_subpixel=float(dy_sub),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def calculate_alignment(
    base: np.ndarray,
    target: np.ndarray,
    method: str = "phase",
    search_radius: int = 40
) -> AlignResult:
    """Select alignment method.

    ``method`` is one of "phase", "hybrid" (alias of phase), "ncc", "ecc",
    "template"; unknown values fall back to "phase". All backends return the
    shift in the module-level (dx, dy) convention (see module docstring).
    """
    method_norm = (method or "phase").lower()
    if base is not None and target is not None and (_is_flat(base) or _is_flat(target)):
        # Flat-image guard: no backend can extract a shift from a constant image.
        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')
    if method_norm in ("phase", "hybrid"):
        return calculate_alignment_robust(base, target, search_radius)
    if method_norm == "ncc":
        return _calculate_alignment_ncc(base, target, search_radius)
    if method_norm == "ecc":
        return _calculate_alignment_ecc(base, target, search_radius)
    if method_norm == "template":
        return _calculate_alignment_template(base, target, search_radius)
    return calculate_alignment_robust(base, target, search_radius)


# ---------------------------------------------------------------------------
# GLAS template alignment (SEM ↔ GDS overlay anchor correction)
# ---------------------------------------------------------------------------

def parabola_subpx(res: np.ndarray, bx: int, by: int, axis: int) -> float:
    """Sub-pixel peak offset (∈ [-1, 1]) from a 3-point parabola fit around
    the score-map peak along ``axis`` (0 = x, 1 = y)."""
    h, w = res.shape
    if axis == 0:
        if bx <= 0 or bx >= w - 1:
            return 0.0
        a, b, c = float(res[by, bx - 1]), float(res[by, bx]), float(res[by, bx + 1])
    else:
        if by <= 0 or by >= h - 1:
            return 0.0
        a, b, c = float(res[by - 1, bx]), float(res[by, bx]), float(res[by + 1, bx])
    denom = a - 2.0 * b + c
    if denom == 0.0:
        return 0.0
    off = 0.5 * (a - c) / denom
    return off if abs(off) <= 1.0 else 0.0


def template_align_nm(sem_img: np.ndarray, template_full: np.ndarray,
                      nm_per_px: float, search_radius_px: float) -> tuple:
    """Refine the SEM↔GDS alignment by template matching (plan M4b).

    ``template_full`` is the synthetic POI rendered at the *expected* (coarse)
    position, the same size as ``sem_img``. Its centre is cropped (leaving a
    ``search_radius_px`` border) and slid over the SEM with
    ``TM_CCOEFF_NORMED``; the peak's displacement from the centred position is
    the residual misalignment. Returns ``(dx_nm, dy_nm, score, used_radius_px)``
    where ``(dx_nm, dy_nm)`` is the correction to add to the overlay anchor so
    the GDS lands on the SEM structure.

    NOTE: unlike calculate_alignment, the return value is a GDS *anchor
    correction* in nanometres, not an image-space (dx, dy): if the SEM
    structure sits (ex, ey) pixels right/down of the template, this returns
    ``(-ex * nm_per_px, +ey * nm_per_px, score, r)`` (image x is right, GDS x
    is right, so anchor.x decreases to shift the overlay right; image y is
    down, GDS y is up, so anchor.y increases to shift the overlay down).
    """
    H, W = sem_img.shape[:2]
    if template_full.shape[:2] != (H, W):
        raise ValueError("template must match the SEM image size")
    r = int(round(search_radius_px))
    r = max(1, min(r, (min(H, W) - 1) // 2))
    tmpl = np.ascontiguousarray(template_full[r:H - r, r:W - r])
    sem = np.ascontiguousarray(sem_img)
    if tmpl.size == 0 or float(tmpl.std()) < 1e-6 or float(sem.std()) < 1e-6:
        return 0.0, 0.0, 0.0, r          # flat template/image → no signal
    res = cv2.matchTemplate(sem.astype(np.uint8), tmpl.astype(np.uint8),
                            cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    bx, by = int(maxloc[0]), int(maxloc[1])
    sx = parabola_subpx(res, bx, by, 0)
    sy = parabola_subpx(res, bx, by, 1)
    ex = (bx + sx) - r            # SEM structure offset from GDS, +x = right
    ey = (by + sy) - r            # +y = down (image row)
    # Anchor correction: move the overlay onto the SEM structure. Image x is
    # right, GDS x is right (so anchor.x decreases to shift right); image y is
    # down, GDS y is up (so anchor.y increases to shift down).
    return (-ex * nm_per_px, ey * nm_per_px, float(maxv), r)
