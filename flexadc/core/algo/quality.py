# Vendored into FlexADC on 2026-07-27.
# Source project: MMH
#   - src/core/image_quality.py          (check_lap_quality, DEFAULT_LAP_THRESHOLD)
#   - tools/image_quality_checker.py     (pure block ~lines 46-97: _load_gray,
#     compute_quality — Qt GUI/worker code NOT vendored)
# Adaptations:
#   - ZERO Qt: only the pure metric functions were extracted from the
#     image_quality_checker tool.
#   - `compute_quality` now accepts EITHER a np.ndarray (grayscale or
#     colour) OR a filesystem path; paths are loaded with a CJK-safe
#     np.fromfile + cv2.imdecode inline (the source used cv2.imread,
#     which fails on non-ASCII paths on Windows).
#   - `_load_gray` kept as a private helper, rewritten around the CJK-safe
#     decode; grayscale conversion / uint8 normalization behavior kept.
#   - No changes to the metric math (Laplacian variance, Tenengrad,
#     FFT high-frequency ratio) or to check_lap_quality.
"""Image quality screening for SEM images.

Primary metric: Laplacian variance after medianBlur(5).
  - medianBlur removes salt-and-pepper / shot noise so isolated pixels are
    not mistaken for genuine high-frequency edges.
  - Laplacian variance reflects true edge sharpness across the image.

`compute_quality` additionally reports Tenengrad (mean squared Sobel
gradient) and the FFT high-frequency ratio (fraction of spectral energy
outside the inner 35 % radius).

Typical PASS thresholds for well-focused SEM images:
  Laplacian var  >  100   (adjust to your magnification / pixel size)
  Tenengrad      > 1000   (optional)
  FFT HF ratio   >  0.05  (optional)
"""

from __future__ import annotations

from typing import Optional, Union

import cv2
import numpy as np

DEFAULT_LAP_THRESHOLD: float = 145.0


def check_lap_quality(img: np.ndarray) -> float:
    """Return Laplacian variance of *img* after median pre-filtering.

    Parameters
    ----------
    img : uint8 grayscale ndarray

    Returns
    -------
    float
        Laplacian variance; higher = sharper. Compare against a threshold
        (e.g. DEFAULT_LAP_THRESHOLD) to decide PASS/FAIL.
    """
    denoised = cv2.medianBlur(img, 5)
    lap = cv2.Laplacian(denoised.astype(np.float64), cv2.CV_64F)
    return float(lap.var())


def _to_gray_u8(img: np.ndarray) -> np.ndarray:
    """Coerce an ndarray to uint8 single-channel grayscale."""
    if img.ndim == 3:
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


def _load_gray(path: str) -> Optional[np.ndarray]:
    """Load *path* as uint8 grayscale, CJK-path safe. None on failure."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except (OSError, IOError):
        return None
    if data.size == 0:
        return None
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    return _to_gray_u8(img)


def compute_quality(image: Union[np.ndarray, str]) -> dict:
    """Return dict with laplacian_var, tenengrad, fft_hf_ratio (all float).

    ``image`` may be a np.ndarray (grayscale or colour) or a filesystem
    path (str / os.PathLike); paths are loaded CJK-safely via
    np.fromfile + cv2.imdecode.
    """
    if isinstance(image, np.ndarray):
        img = _to_gray_u8(image)
    else:
        img = _load_gray(str(image))
    if img is None:
        return {"error": "Cannot load image", "laplacian_var": 0.0,
                "tenengrad": 0.0, "fft_hf_ratio": 0.0}

    # Pre-process: median blur (ksize=5) to suppress salt-and-pepper noise
    # before sharpness metrics are evaluated — avoids noise being mistaken
    # for genuine high-frequency edge content.
    img = cv2.medianBlur(img, 5)

    # 1. Laplacian variance
    lap = cv2.Laplacian(img.astype(np.float64), cv2.CV_64F)
    laplacian_var = float(lap.var())

    # 2. Tenengrad (Sobel-based)
    gx = cv2.Sobel(img.astype(np.float64), cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(img.astype(np.float64), cv2.CV_64F, 0, 1, ksize=3)
    tenengrad = float(np.mean(gx**2 + gy**2))

    # 3. FFT high-frequency ratio (outer spectrum energy)
    h, w = img.shape
    fft = np.fft.fft2(img.astype(np.float64))
    fft_shift = np.fft.fftshift(fft)
    mag = np.abs(fft_shift)
    cy, cx = h // 2, w // 2
    # inner radius = 35 % of half-diagonal → keeps DC and low-freq
    r_inner = min(cy, cx) * 0.35
    ys, xs = np.ogrid[:h, :w]
    dist = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
    total_energy = float(mag.sum()) + 1e-9
    hf_energy = float(mag[dist > r_inner].sum())
    fft_hf_ratio = hf_energy / total_energy

    return {
        "laplacian_var": laplacian_var,
        "tenengrad":     tenengrad,
        "fft_hf_ratio":  fft_hf_ratio,
        "error":         "",
    }
