#!/usr/bin/env python3
# ADEPT synthetic-data helpers — authored 2026-07-28 (M4-2).
"""合成影像的共用零件（`make_sample.py` 與 `make_sample_rsem.py` 共用）。

這裡只放「畫圖案」與「種缺陷」這兩件純函式的事，沒有任何 IO；
兩支產生器各自負責自己的 KLARF 格式與檔案佈局。

★ 這些函式的數值行為必須保持穩定 ★
`tests/test_make_sample.py` 有「同 seed → TIFF 位元組完全相同」的鎖定測試，
改動任何一行都會改變既有合成 lot 的像素值。要調整請另開新函式，別就地改。
"""
from __future__ import annotations

import numpy as np

# 缺陷型別（ground_truth.json 的 "type" 欄位用同一組字串）
REAL_TYPES = ("bright_blob", "dark_blob", "bridge")
NUISANCE_TYPE = "none"


def rounded_square_tile(pitch: int) -> np.ndarray:
    """一格圓角方塊 cell（float32，暗底 60 / 亮方塊 200，1px 軟邊）。"""
    p = int(pitch)
    c = (p - 1) / 2.0
    yy, xx = np.mgrid[0:p, 0:p]
    xx = xx - c
    yy = yy - c
    half = p * 0.30          # 方塊半寬
    rad = max(1.0, p * 0.15)  # 圓角半徑
    qx = np.abs(xx) - (half - rad)
    qy = np.abs(yy) - (half - rad)
    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    d = outside + inside - rad          # 圓角方塊 signed distance
    t = np.clip(0.5 - d, 0.0, 1.0)      # 1px 軟邊
    return (60.0 + t * (200.0 - 60.0)).astype(np.float32)


def pattern(size: int, pitch: int, off_x: int, off_y: int,
            tile: np.ndarray) -> np.ndarray:
    """以 (off_x, off_y) 相位取出 size×size 的週期圖案：P(x,y)=T((y+off_y)%p,(x+off_x)%p)。

    相位是「從鋪好的大圖上換個位置裁切」，不是重新取樣 ——
    所以裁出來的圖仍然是嚴格週期為 pitch 的晶格（Golden Cell 疊圖的前提）。
    """
    p = int(pitch)
    reps = size // p + 2
    big = np.tile(tile, (reps, reps))
    oy = off_y % p
    ox = off_x % p
    return big[oy:oy + size, ox:ox + size].copy()


def plant_anomaly(img: np.ndarray, kind: str, rng: np.random.Generator,
                  pitch: int) -> None:
    """在圖上就地種一個缺陷（靠近中心、振幅 >= 50）。"""
    h, w = img.shape
    amp = float(rng.uniform(55.0, 95.0))            # 振幅保證 >= 50
    cx = w / 2.0 + float(rng.uniform(-0.1, 0.1)) * w
    cy = h / 2.0 + float(rng.uniform(-0.1, 0.1)) * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    if kind in ("bright_blob", "dark_blob"):
        sigma = float(rng.uniform(1.8, 3.5))
        bump = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma ** 2))
        img += (amp if kind == "bright_blob" else -amp) * bump.astype(np.float32)
    else:  # bridge：連接相鄰 cell 的短亮線（水平或垂直）
        length = max(4.0, 1.8 * pitch)
        thick = 1.2
        if rng.random() < 0.5:
            du, dv = xx - cx, yy - cy       # 水平線
        else:
            du, dv = yy - cy, xx - cx       # 垂直線
        along = np.clip(np.abs(du) - length / 2.0, 0.0, None)
        dist = np.hypot(along, np.abs(dv))
        line = np.clip(1.0 - (dist - thick), 0.0, 1.0)
        img += amp * line.astype(np.float32)
