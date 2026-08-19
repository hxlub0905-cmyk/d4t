# d4t algorithm library — authored 2026-08-18 (F11 Region-3 第 3 步).
"""一張 **label map** 的一層 → 一組**精確的**矩形。

d4t 的具名區域是「一組軸對齊矩形」，而 GLAS 給的是一張整數 label 圖
（0 = 背景、1..N = 第 N 層）。這個模組只做那個轉換，不認識卡片、不碰 Qt。

為什麼是**精確拆解**而不是取 bounding box
-----------------------------------------
一個 L 形的 bounding box 會**框到別的材質**，而它照樣吐得出一個看起來完全正常
的灰階值。站點的 layout 是 Manhattan 的，所以 rectilinear 的區域拆成矩形是
**等價不是近似** —— 拆得出來就沒有理由用一個會出錯的近似。

（GLAS 的 label 是 ``cv2.fillPoly`` 畫的、**沒有 LINE_AA**，所以邊界是乾淨的
整數階梯，不會有半透明的邊讓「這個像素算不算」變成一個判斷。）

兩個數字，兩個問題
------------------
* **rectangles** —— d4t 真的要存幾個框。
* **pieces（連通元件）** —— 「一份」有幾個。

它們差很多的時候，意思是那一層**正被後面畫的層切碎**
（GLAS 的 ``render_label_image`` 是 ``lbl[m > 0] = id``，後畫的蓋掉先畫的）。

實測（1000×1000，2026-08-18）
-----------------------------
| 形狀 | pieces | rectangles |
|---|---|---|
| 密集 line/space | 39 | 39 |
| 同上，被另一層橫向切碎 | 975 | 975 |
| 45° 斜帶（fillPoly 的 1px 階梯邊）| 10 | **5 295** |
| contact 陣列 6×6/14 | 5 184 | 5 184 |

所以「一層幾個矩形」的實際範圍是**幾十到約五千**，而斜邊是唯一會爆的東西
（一個 45° 的邊每一列都是一個矩形 —— 那是精確的代價，不是 bug）。
下游的成本（同一天量的，1000×1000）：N=1 000 約 3 ms、N=10 000 約 60 ms、
N=50 000 約 280 ms **而且是每張量測卡每顆各一次**。卡片的預設上限就是照這組
數字定的（見 `steps/roi_from_mask.py`）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

__all__ = ["MaskError", "MAX_RUNS", "decompose", "layer_ids"]

#: 一層最多允許幾個水平 run。超過就**擋下來並講清楚**，不是慢慢跑。
#:
#: 為什麼要有這條線：拆解本身是 O(run 數)，而棋盤格那種病態輸入會產生
#: 幾十萬個 run —— 那時候「跑很久」跟「當掉」對使用者是同一件事，而且他不會
#: 知道發生什麼。實際資料量到的最壞是約 5 000（45° 斜邊），所以這條線離真實
#: 用途很遠，它擋的是「這張圖不是 label map」那一類的意外。
MAX_RUNS = 200_000


class MaskError(Exception):
    """label 圖本身有問題（形狀不對、碎到不像 label map）。"""


def layer_ids(label: Any) -> List[int]:
    """這張圖裡出現過哪些**非零**的值（= 有像素的層）。"""
    arr = np.asarray(label)
    return [int(v) for v in np.unique(arr) if int(v) != 0]


def _runs(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """一層的水平 run，向量化。回傳 ``(row, x0, x1)`` 三個等長陣列。

    做法是在左右各補一欄 0 再取列方向的差分：``+1`` 是一段的開頭、``-1`` 是
    結尾。純 numpy —— 1000×1000 逐像素跑 Python 迴圈要好幾秒，而這條路徑
    **每一顆 defect 都會走**。
    """
    h, w = mask.shape[:2]
    padded = np.zeros((h, w + 2), np.int8)
    padded[:, 1:-1] = mask.astype(np.int8)
    d = np.diff(padded, axis=1)
    ys, x0 = np.nonzero(d == 1)
    _ye, x1 = np.nonzero(d == -1)
    return ys, x0, x1


def decompose(label: Any, value: int) -> Tuple[List[Tuple[int, int, int, int]],
                                               List[int]]:
    """一層 → ``(矩形清單, 每個矩形屬於第幾個連通元件)``。

    矩形是**精確**的（聯集起來逐像素等於 ``label == value``），依「離影像中心
    遠近」排序 —— 卡片要砍上限時砍掉的才是最外圍的那些。

    連通元件用 **4-連通**，而且是以 run 為單位做 union-find（不是逐像素）：
    一層有幾千個 run，逐像素的話是一百萬次。
    """
    arr = np.asarray(label)
    if arr.ndim != 2:
        raise MaskError(
            "the label map must be a single-channel image (this one has %d "
            "dimensions); each pixel value IS a layer number, so merging "
            "channels would blend ids into values that do not exist."
            % arr.ndim)
    h, w = arr.shape[:2]
    ys, x0, x1 = _runs(arr == int(value))
    n = int(ys.size)
    if n == 0:
        return [], []
    if n > MAX_RUNS:
        raise MaskError(
            "layer %d breaks into %d horizontal runs, past the %d limit. That "
            "is far more fragmented than any real layout (the worst measured "
            "is about 5,000), so this is almost certainly not a label map - "
            "check the image stream is the *_label.png and not a photo."
            % (int(value), n, MAX_RUNS))

    # ---- 往下合併成矩形（同一段 [x0, x1) 接在上一列的同一段下面）------------
    rects: List[Tuple[int, int, int, int]] = []
    rect_run: List[int] = []                 # 每個矩形的**第一個** run 索引
    open_at: Dict[Tuple[int, int], int] = {}  # (x0, x1) -> 矩形索引
    open_row: Dict[Tuple[int, int], int] = {}
    run_rect = np.empty(n, np.int64)
    for i in range(n):
        row, a, b = int(ys[i]), int(x0[i]), int(x1[i])
        key = (a, b)
        if open_at.get(key) is not None and open_row.get(key) == row - 1:
            k = open_at[key]
            x, y, bw, bh = rects[k]
            rects[k] = (x, y, bw, bh + 1)
            open_row[key] = row
        else:
            k = len(rects)
            rects.append((a, row, b - a, 1))
            rect_run.append(i)
            open_at[key] = k
            open_row[key] = row
        run_rect[i] = k

    # ---- 連通元件（4-連通，以 run 為單位）----------------------------------
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    row_start: Dict[int, int] = {}
    for i in range(n):
        row_start.setdefault(int(ys[i]), i)
    for i in range(n):
        row = int(ys[i])
        j = row_start.get(row - 1)
        if j is None:
            continue
        a, b = int(x0[i]), int(x1[i])
        while j < n and int(ys[j]) == row - 1:
            if int(x0[j]) < b and a < int(x1[j]):
                union(i, j)
            elif int(x0[j]) >= b:
                break
            j += 1

    roots: Dict[int, int] = {}
    piece_of: List[int] = [0] * len(rects)
    for i in range(n):
        r = find(i)
        if r not in roots:
            roots[r] = len(roots)
        piece_of[int(run_rect[i])] = roots[r]

    # ---- 依離中心遠近排序（砍上限時砍掉的是最外圍的）-----------------------
    cx, cy = w / 2.0, h / 2.0
    order = sorted(range(len(rects)),
                   key=lambda k: ((rects[k][0] + rects[k][2] / 2.0 - cx) ** 2
                                  + (rects[k][1] + rects[k][3] / 2.0 - cy) ** 2))
    return [rects[k] for k in order], [piece_of[k] for k in order]


def drop_small_pieces(rects, piece_of, min_area: int
                      ) -> Tuple[List[Tuple[int, int, int, int]], List[int], int]:
    """把面積小於 ``min_area`` 的**整個連通元件**丟掉。

    為什麼是丟整塊而不是丟小矩形：一個 L 形拆出來的兩個矩形裡有一個可能很小，
    但它是那一塊的一部分 —— 丟掉它會把區域挖掉一角，而數字看起來仍然正常。
    要丟就丟一整塊（那才是「這一塊太小，量不出東西」）。

    回傳 ``(留下的矩形, 對應的元件編號, 丟掉幾塊)``。
    """
    if min_area <= 0:
        return list(rects), list(piece_of), 0
    area: Dict[int, int] = {}
    for (x, y, w, h), p in zip(rects, piece_of):
        area[p] = area.get(p, 0) + int(w) * int(h)
    keep = {p for p, a in area.items() if a >= int(min_area)}
    out_r, out_p = [], []
    for rect, p in zip(rects, piece_of):
        if p in keep:
            out_r.append(rect)
            out_p.append(p)
    return out_r, out_p, len(area) - len(keep)


def to_normalised(rects, shape) -> List[Tuple[float, float, float, float]]:
    """像素矩形 → 0–1 正規化 ``(nx, ny, nw, nh)``。

    **一律正規化**：label 圖的尺寸不保證等於下游那張影像，而寫死像素座標的
    recipe 換一個尺寸就錯位（F7-4 的坑）。
    """
    h, w = float(shape[0]), float(shape[1])
    return [(x / w, y / h, bw / w, bh / h) for x, y, bw, bh in rects]
