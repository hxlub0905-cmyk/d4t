# Vendored into ADEPT on 2026-07-27.
# Source project: PEAR — file: pear/core/analysis.py (function `load_image`,
# the CJK-path-safe np.fromfile + cv2.imdecode grayscale loader).
# Adaptations:
#   - added `from __future__ import annotations` (ADEPT convention)
#   - renamed load_image -> load_gray (algorithm/behavior unchanged:
#     BGRA/BGR -> gray, non-uint8 (e.g. uint16) -> MINMAX-normalized uint8)
#   - added save_gray() / save_rgb() counterparts via cv2.imencode +
#     ndarray.tofile so writing is CJK-path safe too (cv2.imwrite is not).
"""影像 IO（CJK 路徑安全）。

cv2.imread / cv2.imwrite 在 Windows 上吃不到含中日韓字元的路徑；
一律改走 np.fromfile + cv2.imdecode（讀）與 cv2.imencode + tofile（寫）。
"""
from __future__ import annotations

import os

import cv2
import numpy as np


# --------------------------------------------------------------------------- #
# Image IO (CJK-path safe)
# --------------------------------------------------------------------------- #
def load_gray(path: str) -> np.ndarray:
    """Load an image as 8-bit single-channel grayscale (CJK-path safe)."""
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        raise IOError(f"could not read file: {path}")
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError(f"could not decode image: {path}")
    if img.ndim == 3:
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


def _encode_and_write(path: str, arr: np.ndarray) -> None:
    """cv2.imencode + ndarray.tofile：CJK 路徑安全的寫檔（副檔名決定格式）。"""
    ext = os.path.splitext(path)[1]
    if not ext:
        raise ValueError(f"cannot infer image format (no extension): {path}")
    ok, buf = cv2.imencode(ext, arr)
    if not ok:
        raise IOError(f"could not encode image for: {path}")
    buf.tofile(path)


def save_gray(path: str, arr: np.ndarray) -> None:
    """Save a single-channel (grayscale) image (CJK-path safe)."""
    a = np.asarray(arr)
    if a.ndim == 3 and a.shape[2] == 1:
        a = a[:, :, 0]
    if a.ndim != 2:
        raise ValueError(f"save_gray expects a 2-D array, got shape {a.shape}")
    _encode_and_write(path, a)


def save_rgb(path: str, arr: np.ndarray) -> None:
    """Save an RGB (H, W, 3) image (CJK-path safe).

    Input is RGB channel order; cv2 encodes BGR, so the channels are
    swapped before encoding.
    """
    a = np.asarray(arr)
    if a.ndim != 3 or a.shape[2] != 3:
        raise ValueError(f"save_rgb expects an (H, W, 3) array, got shape {a.shape}")
    _encode_and_write(path, cv2.cvtColor(a, cv2.COLOR_RGB2BGR))
