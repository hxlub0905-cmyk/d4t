# Vendored into d4t on 2026-07-27.
# Source project: PEAR — file: pear/core/analysis.py (function `load_image`,
# the CJK-path-safe np.fromfile + cv2.imdecode grayscale loader).
# Adaptations:
#   - added `from __future__ import annotations` (d4t convention)
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
def load_raw(path: str) -> np.ndarray:
    """Load an image as single-channel grayscale **keeping its dtype** (F11).

    為什麼要有這一支（而不是都走 :func:`load_gray`）
    ------------------------------------------------
    ``load_gray`` 對非 8-bit 的輸入會做 **per-image MINMAX 拉伸**（vendored 自
    PEAR 的行為）。那對「拿一張圖來看」是對的，對**量測**是錯的：每張圖各自
    拉伸之後，兩張圖之間就不再可比 —— 而 ``test − ref`` 的整個前提就是可比。
    實測過：把同一張圖的亮度砍半再載入，平均值一模一樣（127.5 vs 127.5）。

    所以 pipeline 的資料一律走這一支（``DefectItem.load``），位元深度的處置由
    上層決定並**講出來**，不在讀檔的時候偷偷決定。
    """
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
    return img


def load_exact(path: str) -> np.ndarray:
    """Load an image **exactly as stored** — no channel collapse, no stretch.

    為什麼 :func:`load_raw` 不夠（F11 Region-3 第 2 步，實測抓到的）
    ---------------------------------------------------------------
    ``load_raw`` 對三通道的輸入會 ``cvtColor(BGR2GRAY)``。對 SEM 影像那是對的
    （彩色的 SEM 圖轉灰階不損失什麼），但對 **label map 是致命的**：那張圖的
    像素值**是**層號，而 BGR 加權平均會把 1、2、3 混成一堆不存在的值 ——
    **而且不會報錯**。

    真實的風險不是假設的：GLAS 匯出時 ``<id>_label.png`` 旁邊就放著
    ``<id>_label_view.png``（同一顆的三通道上色預覽）。指錯一個檔名，整批的
    區域就會落在錯的地方，而畫面上每一個數字看起來都很正常。

    所以附加檔走這一支，**通道數的判斷留給上層**（`steps/load_sidecar.py` 會
    把三通道當成錯誤並講出它多半是哪個檔案）—— 讀檔這一層不准替使用者決定。
    """
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        raise IOError(f"could not read file: {path}")
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError(f"could not decode image: {path}")
    return img


def load_gray(path: str) -> np.ndarray:
    """Load an image as 8-bit single-channel grayscale (CJK-path safe).

    ⚠ 非 8-bit 的輸入會被 **per-image MINMAX** 拉成 0–255 —— 那是「給人看」
    的轉換，**兩張圖之間不再可比**。要量測的資料請走 :func:`load_raw`
    （``DefectItem.load`` 就是）。
    """
    img = load_raw(path)
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
