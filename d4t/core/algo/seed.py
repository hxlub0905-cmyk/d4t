# d4t algorithm library — authored 2026-09-17 (F103).
"""從**使用者標的一格**量週期：找它的每一個複本，複本之間的間距就是週期。

為什麼要有第二種量法
--------------------
`period.estimate_period` 走的是一維投影 ＋ FFT ＋ 自相關。它假設三件事：layout 是
曼哈頓的、一張圖裡只有一種 cell、沒有東西蓋住。三個假設各有一種破法（交錯排列的
cell 投影後週期變一半；兩種 pitch 混在一張圖投影混成一條；斜幾度的 layout 投影
變糊）—— 而破掉的時候它**仍然回一個數字**，信心值不一定掉到門檻以下。

這一支不做任何假設：使用者在圖上框**一格**，用 NCC（`cv2.TM_CCOEFF_NORMED`，
對亮度／對比免疫，同 `template.match_patch`）在整張圖上找這一格的每一個複本，
跟它**同一列**的複本之間的間距是 X 週期、**同一行**的是 Y 週期。答案直接來自
「這一格在圖上重複了幾次、隔多遠」—— 那正是使用者問的問題。

它回答的另一件事是**原點**：使用者框的那一格的左上角就是格線的起點。所以疊出來
的 cell 長得跟他框的那一塊一樣（`build_golden_cell` 吃 ``origin``，並且**不做**
上升邊錨定 —— 地標是他選的）。

不假裝
------
* 同一列找不到至少 :data:`MIN_COPIES` 個複本的那一軸＝**沒有週期**（回 ``None``），
  不拿兩個點硬算一個數字。
* 間距彼此不一致（相差超過 1 px 的比例太高）會反映在 ``confidence``（0–100 ＝
  一致的比例），對話框照實印出來。
* 框裡沒有結構（幾乎是平的）直接說，不去比對。

複本數可能上萬（7680² 的圖、40 px 的 cell 是 36,000 個）。這裡只用**跟框同一列
／同一行**的複本算週期 —— O(n)，而且那正是「隔壁那幾格離我多遠」的意思；總數
仍然回報（``n_copies``），那是「這一格真的在整張圖上重複」的證據。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from .template import _gray_u8

__all__ = ["SeedResult", "period_from_seed", "MIN_COPIES", "MIN_SCORE"]

#: 同一列（行）至少要有這麼多個複本（含框的那一格）才算量到週期。
MIN_COPIES = 3
#: NCC 低於這個的不算複本。框的那一格自己是 1.0；合成資料上真的複本 0.9 以上、
#: 雜訊處 0.3 以下，所以中間有很寬的餘裕。
MIN_SCORE = 0.6


@dataclass
class SeedResult:
    """`period_from_seed` 的答案。``px``／``py`` 是 ``None`` ＝ 那一軸沒有週期。"""

    px: Optional[int] = None
    py: Optional[int] = None
    confidence_x: float = 0.0
    confidence_y: float = 0.0
    #: 框的左上角（影像像素）—— 格線的原點就是它。
    origin: Tuple[int, int] = (0, 0)
    #: 整張圖上找到幾個複本（含框的那一格）。
    n_copies: int = 0
    #: 用來量 X／Y 週期的那幾個（同一列／同一行的）。
    n_row: int = 0
    n_col: int = 0
    #: 每個複本的 ``(x, y, score)``（最多 :data:`MAX_LISTED` 個，給畫面標出來用）。
    copies: List[Tuple[int, int, float]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def periodic(self) -> Tuple[bool, bool]:
        return (self.px is not None, self.py is not None)


#: `copies` 最多列幾個（畫面標記用；週期的計算不受這個限制）。
MAX_LISTED = 5000


def _clamp(rect: Tuple[int, int, int, int], shape: Tuple[int, int]
           ) -> Optional[Tuple[int, int, int, int]]:
    h, w = int(shape[0]), int(shape[1])
    x, y, cw, ch = (int(v) for v in rect)
    x0, y0 = max(0, min(x, w)), max(0, min(y, h))
    x1, y1 = max(0, min(x + cw, w)), max(0, min(y + ch, h))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


#: 一條線上 NCC ≥ `min_score` 的比例超過這個，那一軸是**平的**（垂直條紋的 Y 軸：
#: 框往上下滑到哪裡都一樣像）—— 平的軸沒有週期，NMS 在上面找到的「峰」只是
#: 視窗大小的倒影。合成資料上：有週期的軸 0.07，平的軸 1.00。
FLAT_ABOVE = 0.5


def _line_peaks(line: np.ndarray, min_score: float, min_gap: int) -> np.ndarray:
    """一條 NCC 剖面上的峰（局部極大、≥ min_score、彼此至少隔 ``min_gap``）。"""
    v = np.asarray(line, dtype=np.float32)
    n = v.size
    if n < 3:
        return np.zeros(0, dtype=np.int64)
    inner = v[1:-1]
    cand = np.nonzero((inner >= v[:-2]) & (inner >= v[2:]) & (inner >= min_score))[0] + 1
    if cand.size == 0:
        return cand.astype(np.int64)
    # 由高到低貪婪抑制：一個複本只留一個峰（雜訊會讓一個峰裂成兩個相鄰的）。
    keep: List[int] = []
    for i in cand[np.argsort(-v[cand], kind="stable")]:
        if all(abs(int(i) - k) >= min_gap for k in keep):
            keep.append(int(i))
    return np.asarray(sorted(keep), dtype=np.int64)


def _spacing(line: np.ndarray, min_score: float, min_gap: int
             ) -> Tuple[Optional[int], float, int, bool]:
    """框那一列（行）的 NCC 剖面 → ``(週期, 一致比例 0–100, 用了幾個峰, 平不平)``。

    週期是**相鄰**峰間距的中位數；一致比例是間距落在中位數 ±1 px 內的比例。
    """
    v = np.asarray(line, dtype=np.float32)
    if v.size and float(np.mean(v >= min_score)) > FLAT_ABOVE:
        return None, 0.0, 0, True
    xs = _line_peaks(v, min_score, min_gap)
    if xs.size < MIN_COPIES:
        return None, 0.0, int(xs.size), False
    d = np.diff(xs)
    med = int(round(float(np.median(d))))
    if med < 2:
        return None, 0.0, int(xs.size), False
    agree = float(np.mean(np.abs(d - med) <= 1))
    return med, round(100.0 * agree, 1), int(xs.size), False


def period_from_seed(image: Any, rect: Tuple[int, int, int, int],
                     min_score: float = MIN_SCORE) -> SeedResult:
    """``rect=(x, y, w, h)`` 是使用者框的一格（影像像素）。見模組說明。"""
    gray = _gray_u8(image)
    out = SeedResult()
    if gray.ndim != 2 or gray.size == 0:
        out.warnings.append("the image is empty")
        return out
    box = _clamp(rect, gray.shape[:2])
    if box is None:
        out.warnings.append("the box is outside the image or too small")
        return out
    x0, y0, sw, sh = box
    out.origin = (x0, y0)
    seed = gray[y0:y0 + sh, x0:x0 + sw]
    if float(seed.std()) < 1.0:
        out.warnings.append("the box you marked has no structure in it - "
                            "draw it around one repeating cell")
        return out
    h, w = gray.shape[:2]
    if sw >= w or sh >= h:
        out.warnings.append("the box covers the whole image - one cell is "
                            "smaller than that")
        return out

    surf = cv2.matchTemplate(gray.astype(np.float32), seed.astype(np.float32),
                             cv2.TM_CCOEFF_NORMED)
    # 非極大值抑制：以框的一半當視窗，一個複本只留一個峰。
    ky, kx = max(3, sh // 2) | 1, max(3, sw // 2) | 1
    dil = cv2.dilate(surf, np.ones((ky, kx), np.uint8))
    hit = (surf >= dil - 1e-6) & (surf >= float(min_score))
    ys, xs = np.nonzero(hit)
    scores = surf[ys, xs]
    # 框的那一格自己一定在（分數 1.0）；NMS 偶爾會把它跟鄰居合掉，補回來。
    if not np.any((np.abs(xs - x0) <= 1) & (np.abs(ys - y0) <= 1)):
        xs = np.append(xs, x0)
        ys = np.append(ys, y0)
        scores = np.append(scores, 1.0)
    out.n_copies = int(xs.size)
    order = np.argsort(-scores)[:MAX_LISTED]
    out.copies = [(int(xs[i]), int(ys[i]), float(scores[i])) for i in order]

    # 週期看**框那一列／那一行**的剖面（一維、O(n)、而且正是「隔壁那幾格離我
    # 多遠」的意思）。上面的二維峰只拿來數複本、給畫面標記。
    out.px, out.confidence_x, out.n_row, flat_x = _spacing(
        surf[y0, :], float(min_score), max(2, sw // 2))
    out.py, out.confidence_y, out.n_col, flat_y = _spacing(
        surf[:, x0], float(min_score), max(2, sh // 2))

    for axis, p, n, flat in (("across", out.px, out.n_row, flat_x),
                             ("down", out.py, out.n_col, flat_y)):
        if p is not None:
            continue
        if flat:
            out.warnings.append(
                "the marked cell looks the same wherever it slides %s, so "
                "there is no period that way (a stripe layout)" % axis)
        else:
            out.warnings.append(
                "found only %d cop%s of the marked cell %s, so there is no "
                "period that way (at least %d are needed)"
                % (n, "y" if n == 1 else "ies", axis, MIN_COPIES))
    if out.px is None and out.py is None:
        out.warnings.append("the marked cell does not repeat in this image")
    for axis, conf, n in (("across", out.confidence_x, out.n_row),
                          ("down", out.confidence_y, out.n_col)):
        if n >= MIN_COPIES and conf < 70.0:
            out.warnings.append(
                "the spacing between copies %s is uneven (%.0f%% agree) - "
                "the box may not be exactly one cell, or the layout is not a "
                "regular grid" % (axis, conf))
    return out
