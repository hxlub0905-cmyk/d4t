# Vendored into d4t on 2026-07-27.
# Source project: cell-period-estimator —
#   cell_period_estimator/core/stacking.py (vendored wholesale)
# Adaptations:
#   - Module vendored unchanged (pure NumPy/OpenCV, no Qt in the source).
#   - No algorithmic changes.
"""Golden-Cell stacking, sharpness, and stacking agreement.

Pure NumPy / OpenCV.  Given a period ``(px, py)`` these helpers tile the
image into cells and average / median them into a single "Golden Cell".

⚠ **Two different questions, two different functions** (F40, 2026-08-27).
The vendored module docstring used to say "when the period is correct the
cells align and the stack is sharp; when it is wrong the cells drift and
the stack ghosts (blurs), which is what the sharpness metrics quantify."
**The last clause is false**, and it cost this project a silently useless
warning for months:

``ghosting_score``
    "How much edge energy is in *this one image*."  It never sees the
    cells that went into the stack, so it cannot tell "sharp because the
    cells aligned" from "sharp because two ghosts each contributed an
    edge".  Its value scales with contrast, noise and cell size, so it is
    only meaningful **relative to another stack of the same image**.
``stack_agreement``
    "Did the cells actually agree with each other."  Dimensionless,
    comparable across images, and 0 when they agree no better than
    chance.  This is the one to threshold against a fixed number.

Measured, on a line/space pattern (period 40) — the shape no test covered
until F40:

============================  ==========  ==============  ============
                              correct 40  half-period 60  pure noise
============================  ==========  ==============  ============
``ghosting_score`` (0..100)   43.0        **37.3–76.1**   **up to 99.4**
``stack_agreement`` (0..1)    0.24–0.99   **0.000**       0.003
============================  ==========  ==============  ============

The pure-noise column is the one to remember: an image with *nothing to
stack* scored 99.4 / 100 "sharpness" at σ=60, because noise is edges.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np


# --------------------------------------------------------------------------- #
# 疊得算不算糊：**一個門檻，一個家**
# --------------------------------------------------------------------------- #
# ⚠ 這個常數 2026-09-22 從 `ui/template_dialog.py` 搬到這裡（F120 第十七輪）。
# 它是 `stack_agreement` 的門檻，本來就該住在那支旁邊 —— 而它待在一支 1,300
# 行的 Qt 對話框裡的代價是：`pitch_helper` 為了**一個 float** 得把整支對話框
# import 進來。那條線寫在 `docs/plans/F120-pitch-helper.md` §28 的拆解清單上，
# 而它是清單裡唯一一條「真的該剪」的。`template_dialog` 現在從這裡轉出去，
# 所以 `template_dialog.BLURRED_BELOW` 這個名字照樣在。
#: 一致性低於這個值就講「疊出來是糊的」（`golden.stack_agreement`，0–1）。
#:
#: **這個數字是量出來的，不是挑的**（F40）。正確的週期在 repo 自己的擬真產生器
#: （`tools/make_mgepi_real.render_die`）上落在 0.89–0.97；條紋圖上六種對比／
#: 雜訊組合落在 0.24–0.99。不成比例的錯週期（47、42、38）是 0.00–0.08，
#: 純雜訊 0.003。0.5 因此放行全部擬真的，唯一擋下的正確案例是「對比 0.25 ＋
#: 雜訊 20」的 0.243 —— 那個 stack 本來就不該被信任。
#:
#: ⚠ **這一條抓的是「格子對不上」，不是「週期挑錯了」——三種壞法有三個機制，
#: 不要指望一個數字全包**（量過的，方波條紋、真值 40）：
#:
#: =====================  ==========  =========================================
#: 壞法                   agreement   誰抓它
#: =====================  ==========  =========================================
#: 不成比例的週期（47）    0.000       **這一條**
#: 完全沒有東西可疊        0.003       **這一條**
#: cell 是 k 倍（80）      0.995       `cell_self_period` 的 k× 提示（而且 2×
#:                                    的 cell 是**合法的**，使用者要得到）
#: 一半／1.5 倍（20、60）  0.69–0.93   `estimate_period` 的諧波修正（自相關那
#:                                    一層），以及 60 也會觸發 k× 提示
#: =====================  ==========  =========================================
#:
#: 對稱性高的圖案上，半週期的格子彼此**真的**蠻像的 —— 0.93 是誠實的回答，
#: 不是漏抓。那一題屬於上游。
#:
#: ⚠ 這個門檻**只能**跟 `agreement` 比。以前它掛在 `ghosting`（銳利度）上，
#: 而那個量沒有正規化 —— 見模組說明。
BLURRED_BELOW = 0.5


def _to_gray(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 3:
        if arr.shape[2] == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
        else:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return arr


def tile_coords(shape: Tuple[int, ...], px: int, py: int,
                origin: Tuple[int, int] = (0, 0)) -> List[Tuple[int, int]]:
    """Top-left ``(x, y)`` of every *complete* cell.

    Cells that would run past the image border are skipped.  This is the
    single source of truth for cell placement used by both stacking and
    period refinement.
    """
    h, w = shape[:2]
    # 原點也收成整數：`GoldenCell.origin` 從 F105 起可以是小數（原圖座標），
    # 而 `range` 吃到 float 會炸。整數進來就是恆等，逐位元組不變。
    ox, oy = int(origin[0]), int(origin[1])
    px, py = int(px), int(py)
    if px < 1 or py < 1:
        return []
    xs = range(ox, w - px + 1, px)
    ys = range(oy, h - py + 1, py)
    return [(x, y) for y in ys for x in xs]


def cell_origins(shape: Tuple[int, ...], px: float, py: float,
                 origin: Tuple[float, float] = (0.0, 0.0)
                 ) -> List[Tuple[float, float]]:
    """小數週期版的 :func:`tile_coords`：每一個**完整**格子的左上角 ``(x, y)``。

    F105：週期可以是 79.5 這種數（見 `template.build_golden_cell`）。格子的
    位置是 ``origin + (i·px, k·py)``，而不是整數步進 —— 79.5 對 79 在 4000 px
    上差 25 px，格線就是這樣「靠邊會滑」的。

    整數參數時逐元素等於 ``tile_coords``（測試釘著）；回傳的是 float，
    **拿去切片之前要自己決定怎麼取整** —— 疊圖不走這裡（疊圖先把影像重採樣成
    整數 pitch 再走 ``tile_coords``），這一支是給格線檢視與「幾格」用的。
    """
    h, w = int(shape[0]), int(shape[1])
    fx, fy = float(px), float(py)
    if not (fx >= 1.0 and fy >= 1.0) or h < 1 or w < 1:
        return []
    ox, oy = float(origin[0]), float(origin[1])
    out: List[Tuple[float, float]] = []
    # 跟 `tile_coords` 一樣：右／下超出影像的那一格不算。用 1e-9 吃掉
    # 「i·px 剛好等於邊界」的浮點誤差，免得整數參數時少一格。
    ny = int(np.floor((h - oy - fy) / fy + 1e-9)) + 1 if h - oy >= fy else 0
    nx = int(np.floor((w - ox - fx) / fx + 1e-9)) + 1 if w - ox >= fx else 0
    for k in range(max(0, ny)):
        y = oy + k * fy
        for i in range(max(0, nx)):
            out.append((ox + i * fx, y))
    return out


def stack_cells(image: np.ndarray, px: int, py: int, method: str = "mean",
                origin: Tuple[int, int] = (0, 0),
                sample_n: Optional[int] = None, seed: int = 0) -> np.ndarray:
    """Stack all (or ``sample_n`` random) cells into one ``(py, px)`` image.

    ``method="mean"`` (default) is sensitive to phase error and makes
    ghosting obvious; ``method="median"`` is robust to sparse defects.
    """
    gray = _to_gray(image)
    px, py = int(px), int(py)
    coords = tile_coords(gray.shape, px, py, origin)
    if not coords:
        return np.zeros((max(py, 1), max(px, 1)), dtype=np.uint8)

    if sample_n is not None and 0 < sample_n < len(coords):
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(coords), size=sample_n, replace=False)
        coords = [coords[i] for i in idx]

    if method != "median" and sample_n is None:
        # **平均那條路不要把每一格各切一份出來**（F86，2026-09-07）。
        #
        # 原本的寫法是 `np.stack([...每一格...])` 再對 axis 0 取平均，而那個
        # 中間陣列是「格數 × py × px × 8 bytes」—— 7680×7680 的圖上是
        # **469 MB**，配一次 0.33 秒。`choose_origin` 的相位搜尋要疊 281 次，
        # 所以整整 93 秒花在配置與丟棄同一塊記憶體上（實測 130 s／張，而且
        # 是在 UI 執行緒上跑）。
        #
        # reshape 成 ``(ny, py, nx, px)`` 再對 (0, 2) 取平均是**同一組數字的
        # 同一個平均**，只是不必把它們搬到別的地方去加。實測**逐位元組相同**
        # （`tests/test_period_golden.py` 釘著），而且 7 倍快。
        #
        # ⚠ 只走得了 ``mean`` 而且沒有抽樣：中位數要看得到每一格
        # （那正是它對稀疏缺陷免疫的原因），抽樣挑的格子不連續，兩者都
        # reshape 不出來。
        ox, oy = int(origin[0]), int(origin[1])
        h, w = gray.shape[:2]
        nx, ny = (w - ox) // px, (h - oy) // py
        block = gray[oy:oy + ny * py, ox:ox + nx * px]
        stacked = block.reshape(ny, py, nx, px).mean(axis=(0, 2),
                                                     dtype=np.float64)
        return np.clip(stacked, 0, 255).astype(np.uint8)

    cells = np.stack([
        gray[y:y + py, x:x + px].astype(np.float64) for (x, y) in coords
    ])
    if method == "median":
        stacked = np.median(cells, axis=0)
    else:
        stacked = cells.mean(axis=0)
    return np.clip(stacked, 0, 255).astype(np.uint8)


def ghosting_score(stacked: np.ndarray) -> Tuple[float, float, float]:
    """Quantify the sharpness of a stacked cell.

    Returns ``(score_0_100, laplacian_var, edge_contrast)``.  ``score``
    is a saturating 0..100 mapping for display; ``laplacian_var`` is the
    raw (unsaturated) value callers should rank by.

    ⚠ **What this is not** (F40).  It takes *one* image and asks how much
    high-frequency energy is in it.  It never sees the cells that were
    stacked, so it cannot answer "did they align" — and the two questions
    genuinely come apart: a mis-phased stack superimposes two copies and
    so carries *two* sets of edges, which **raises** this number.  Use
    :func:`stack_agreement` for "did they align".

    It is also **not comparable across images**: the value scales with
    contrast, noise and cell size.  ``0..100`` looks like a percentage
    and is not one — pure noise reaches 99.4 at σ=60.  Rank two stacks of
    the *same* image with it; never compare it to a fixed threshold.
    """
    g = stacked.astype(np.float64)
    if g.size == 0:
        return 0.0, 0.0, 0.0
    lap_var = float(cv2.Laplacian(g, cv2.CV_64F).var())
    gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    edge_contrast = float(np.hypot(gx, gy).mean())
    # Saturating map: high lap_var -> sharp -> approaches 100.
    score = float(np.clip(100.0 * (1.0 - np.exp(-lap_var / 200.0)), 0.0, 100.0))
    return score, lap_var, edge_contrast


def stack_agreement(image: np.ndarray, px: int, py: int,
                    origin: Tuple[int, int] = (0, 0)) -> float:
    """Did the cells actually agree with each other?  ``0``..``1`` (F40).

    ``1`` = every cell landed on top of the others; ``0`` = they agree no
    better than an unrelated pile of pixels.  Unlike :func:`ghosting_score`
    this is dimensionless, so it is the one that may be compared against a
    fixed threshold.

    How
    ---
    Cells that align average into something that keeps its structure;
    cells that do not average into mush.  So compare the variance of the
    stack against the variance of a typical single cell::

        a = var(mean(cells)) / mean(var(cell_i))        # in (1/n, 1]

    ⚠ **The ``1/n`` floor has to come off.**  ``n`` unrelated cells still
    leave ``var(mean) ≈ var(cell)/n`` behind, so a small image that only
    fits two cells scores 0.5 for *any* period.  Measured on the repo's
    own synthetic die (81×81, two cells): pure noise is ``0.499`` before
    the correction and ``0.000`` after it.  Without this the threshold
    would mean something different on every image size — which is exactly
    the bug this function exists to replace.

    Returns ``0.0`` when fewer than two whole cells fit (nothing was
    stacked, so nothing agreed) or when the cells are flat.
    """
    gray = _to_gray(image)
    px, py = int(px), int(py)
    coords = tile_coords(gray.shape, px, py, origin)
    cells = [gray[y:y + py, x:x + px].astype(np.float64) for (x, y) in coords]
    cells = [c for c in cells if c.shape == (py, px)]
    n = len(cells)
    if n < 2:
        return 0.0
    per_cell = float(np.mean([float(c.var()) for c in cells]))
    if per_cell < 1e-9:                 # a flat crop agrees with itself
        return 0.0                      # trivially — that is not evidence
    stacked_var = float(np.stack(cells).mean(axis=0).var())
    raw = stacked_var / per_cell
    floor = 1.0 / float(n)
    return float(np.clip((raw - floor) / (1.0 - floor), 0.0, 1.0))


# ``refine_period`` / ``candidate_periods`` were deleted on 2026-08-27 (F40).
# They came in with the vendored module and never gained a production caller —
# ``estimate_period`` finds the period by autocorrelation and never asks this
# module anything.  Measured before deleting: ``refine_period`` starting from
# 26 walks to 20 when the truth is 28, because it ranks candidates by the
# sharpness of the stack, and sharpness is not alignment (see the module
# docstring above).  Keeping a broken helper alive for its own test is how a
# wrong answer waits for a first caller.
