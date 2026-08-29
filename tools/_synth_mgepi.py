#!/usr/bin/env python3
# d4t synthetic-data helpers: the MG × EPI layout — authored 2026-08-28 (F58).
"""**直的 MG 壓在橫的 EPI 上，六根一個週期、第三根缺席。**

`_synth.py` 那兩個圖案（圓角方格、兩組正交條紋）是**教科書式**的：嚴格週期、
每一根都在。使用者 2026-08-28 帶了一張真的 Golden Cell 進來，而真的 layout
差在三件事，每一件都會讓演算法走到不同的分支：

1. **週期不是一根，是六根** —— 而 `algo/period.estimate_period` 找的是最小的
   自相似位移。六根一個週期的圖案上，「一根的 pitch」與「真正的週期」差六倍。
2. **第三根缺席**，所以那個週期**不對稱**。缺席那一格的兩側 space 併成一塊
   特別寬的暗區 —— 相位搜尋唯一能咬住的地標就是它。
3. **要量的東西不是線也不是 space，是它們的交界**（inner space）：MG 與
   space 之間那一小條，而且只在 EPI 亮帶上才算數。缺陷都在那裡。

⚠ **這裡的數字是「有代表性的整數」，不是那張 GC 的轉錄。** 量到的是
pitch≈29.3 / EPI≈33.5；寫進來的是 30 / 34。理由是鐵則 8 的精神：合成資料要
撐得起演算法的每一條分支，但不必是一份可以拿去對照真實 layer 的尺寸表。
要對得更準就改參數，那本來就是 :class:`Geometry` 存在的理由。

★ 這一支跟 `_synth.py` 一樣，數值行為要穩定 ★
`tests/test_synth_mgepi.py` 有「同 seed → 位元組相同」的鎖定測試。
要調整請加參數或另開函式，別就地改預設值。
"""
from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple

import numpy as np

__all__ = ["Geometry", "GEOMETRY", "Levels", "LEVELS",
           "frame", "inner_space_boxes",
           "golden_cell", "plant_inner_space_defect", "REAL_TYPES"]

#: 這個圖案上「真的缺陷」有哪幾種。`_synth.REAL_TYPES` 的三種在這裡沒有意義
#: —— bridge 要橋接的是**相鄰的 MG**，而 blob 要落在 inner space 上，
#: 兩者都是這個 layout 才有的形狀。
REAL_TYPES = ("bright_blob", "dark_blob", "bridge", "missing_line")


class Geometry(NamedTuple):
    """一份 layout 的尺寸。全部是像素，而且**可以是小數**。

    `mg_pitch` 是一根 MG 到下一根，`mg_width` 是 MG 本身有多寬 ——
    兩者的差就是 space。`core_width` 是 space 正中央那一條比較亮的細線
    （真圖上看得到，寬度約 space 的 1/4）。
    """
    mg_pitch: float = 30.0        # 一根 MG 到下一根
    mg_width: float = 14.0        # MG 線本身的寬度
    core_width: float = 4.0       # space 正中央那一條亮芯
    epi_pitch: float = 34.0       # EPI 橫帶的週期
    period: int = 6               # 幾根 MG 是一個 layout 週期
    absent: int = 2               # 週期裡第幾根不見（0-based → 第 3 根）
    edge: float = 2.6             # 邊緣的軟化寬度（px）
    # ⚠ ``edge`` 不是為了好看。真的那張 GC 是**疊出來的**（很多個 cell 平均），
    # 邊緣本來就跨 2–3 px；把它畫成階梯的話 `algo/edge` 的次像素定位沒有東西
    # 可以定，而那正是 CD 那張卡要練的事。量真圖的轉場寬度取的是 2.6。


#: 預設的那一份（見模組說明為什麼是整數）。
GEOMETRY = Geometry()

class Levels(NamedTuple):
    """每一種材質的 ``(EPI 暗帶上的灰階, EPI 亮帶上的灰階)``。

    ⚠ **為什麼是「每種材質一對」而不是一個整體的亮度增益。** 第一版把整張圖
    寫成 ``x 剖面 × EPI 增益``，而量真的那張 GC 之後那是錯的：

    =============  ======  ======  ======
    材質            EPI亮   EPI暗    比值
    =============  ======  ======  ======
    MG 線            224     126     0.56
    space            183      12     0.07
    space 亮芯        164      16     0.10
    缺席的寬暗區        47      33     0.70
    =============  ======  ======  ======

    **space 幾乎全黑，MG 線只掉一半** —— 一個共同的乘法增益做不出這件事。
    物理上也本來就不該：**MG 壓在 EPI 上**（`_synth.line_grid` 的檔頭早就寫了
    這句話），所以 MG 覆蓋的地方看到的是 MG，只有 space 才看得到底下的 EPI 帶
    亮或不亮。把它寫成「每種材質自己的一對灰階，EPI 在兩者之間插值」之後，
    四個比值自然就對了。
    """
    mg: Tuple[float, float] = (125.0, 225.0)        # MG 線
    space: Tuple[float, float] = (15.0, 185.0)      # 兩根 MG 之間
    core: Tuple[float, float] = (20.0, 165.0)       # space 正中央那條亮芯
    absent: Tuple[float, float] = (30.0, 50.0)      # 缺席那一根的位置


#: 預設的灰階（量真的那張 GC 取的整數，見 :class:`Levels`）。
LEVELS = Levels()


def _smooth(d: np.ndarray, edge: float) -> np.ndarray:
    """帶軟邊的階梯：``d`` 是「離邊界多遠（內部為正）」。"""
    return np.clip(d / max(1e-6, float(edge)) + 0.5, 0.0, 1.0)


def _x_masks(w: int, geo: Geometry, phase_x: float):
    """``(MG 線, 亮芯, 缺席的寬暗區)`` 三張 0–1 的遮罩，長度 ``w``。

    ``phase_x`` 是**整個週期**的相位（不是一根的），單位是像素。patch 以缺陷
    為中心裁切，所以每顆的相位不同 —— 那是這類資料的本質。
    """
    x = np.arange(int(w), dtype=np.float32) + float(phase_x)
    span = geo.mg_pitch * geo.period
    u = np.mod(x, span)                       # 週期內的位置
    g = np.floor(u / geo.mg_pitch).astype(np.int32)   # 第幾根
    t = u - g * geo.mg_pitch                  # 這一根內的位置
    gone = g == int(geo.absent) % int(geo.period)

    line = _smooth(t, geo.edge) * _smooth(geo.mg_width - t, geo.edge)
    line = np.where(gone, 0.0, line)

    # **缺席的那一根照樣有亮芯** —— 真圖上那塊寬暗區之後緊接著就是一條亮芯
    # （量到的 run-length 是 `暗18 中3 亮5 中5`）。不見的是**線**，不是整格。
    mid = (geo.mg_width + geo.mg_pitch) / 2.0
    core = _smooth(geo.core_width / 2.0 - np.abs(t - mid), geo.edge)

    # 缺席的那一根：它**原本的位置**變成一塊更暗的區（比線本身寬一點，
    # 因為兩側的 space 沒有線把它們隔開了）。
    pad = geo.edge * 1.5
    wide = np.where(gone, _smooth(t + pad, geo.edge)
                    * _smooth(geo.mg_width + pad - t, geo.edge), 0.0)
    return line.astype(np.float32), core.astype(np.float32), wide.astype(np.float32)


def _epi(h: int, geo: Geometry, phase_y: float) -> np.ndarray:
    """EPI 帶：0（帶與帶之間）… 1（帶的正中央）。

    真圖上這條是**平滑**的（raised cosine），不是方波 —— 而那不是美觀問題：
    方波的話 inner space 的邊界會落在一個階梯上，`algo/edge` 的次像素定位
    就沒有東西可以定。
    """
    y = np.arange(int(h), dtype=np.float32) + float(phase_y)
    return (0.5 - 0.5 * np.cos(2.0 * np.pi * y / float(geo.epi_pitch))
            ).astype(np.float32)


def frame(h: int, w: int, geo: Geometry = GEOMETRY,
          phase_x: float = 0.0, phase_y: float = 0.0,
          lv: Levels = LEVELS) -> np.ndarray:
    """一張乾淨的 MG×EPI 影像（float32，未加雜訊）。

    合成順序＝物理順序：先鋪 space（看得到底下的 EPI），再蓋亮芯，
    最後把 MG 線**壓上去**（`_synth.line_grid` 的老規矩：金屬壓在磊晶上）。
    缺席那一根的位置改鋪它自己那一對灰階。
    """
    line, core, wide = _x_masks(int(w), geo, phase_x)
    e = _epi(int(h), geo, phase_y)[:, None]

    def band(pair: Tuple[float, float]) -> np.ndarray:
        return pair[0] + e * (pair[1] - pair[0])

    img = band(lv.space) + np.zeros((1, int(w)), dtype=np.float32)
    img = img + core[None, :] * (band(lv.core) - img)
    img = img + wide[None, :] * (band(lv.absent) - img)
    img = img + line[None, :] * (band(lv.mg) - img)
    return img.astype(np.float32)


def golden_cell(geo: Geometry = GEOMETRY,
                periods_x: int = 1, periods_y: int = 2) -> np.ndarray:
    """**一個完整週期**的 tile（uint8）—— 拿去當 Golden Cell 模板的那一張。

    x 是 ``period`` 根 MG，y 預設兩個 EPI 週期（真的那張 GC 就是兩排）。
    相位 0 = 週期從第一根 MG 的左緣開始，所以缺席的那一根落在正中間偏左 ——
    跟真圖一樣，而**那塊寬暗區就是相位搜尋唯一咬得住的地標**。
    """
    w = int(round(geo.mg_pitch * geo.period * max(1, int(periods_x))))
    h = int(round(geo.epi_pitch * max(1, int(periods_y))))
    return np.clip(frame(h, w, geo), 0.0, 255.0).astype(np.uint8)


def inner_space_boxes(h: int, w: int, geo: Geometry = GEOMETRY,
                      phase_x: float = 0.0, phase_y: float = 0.0,
                      box_w: float = 3.0,
                      box_h: Optional[float] = None) -> List[Tuple[int, int, int, int]]:
    """**要量的那些小條**：MG↔space 的交界 × EPI 亮帶，``(x, y, w, h)`` 像素。

    一根 MG 有左右兩個交界，所以一個週期上有 ``2 × (period − 1)`` 條
    （缺席的那一根沒有交界 —— 它不在）。缺陷都種在這裡。

    ⚠ **順序是規格**：由左而右、同一欄由上而下。下游（合成 recipe 的
    `regions`、`_center` 是哪一塊）靠它對得起來。
    """
    bh = float(geo.epi_pitch * 0.4 if box_h is None else box_h)
    bw = float(box_w)
    span = geo.mg_pitch * geo.period
    # EPI **亮**帶的中心。⚠ `_epi` 是 ``0.5 − 0.5·cos``，所以亮的地方是
    # ``y + phase_y ≡ epi_pitch/2``，**不是** ``≡ 0`` —— 第一版寫成 0，於是
    # 每一個框都落在最暗的那一列上（而它照樣吐得出看起來正常的數字）。
    ys: List[int] = []
    k0 = int(np.floor(phase_y / geo.epi_pitch)) - 1
    for k in range(k0, k0 + int(h / geo.epi_pitch) + 3):
        yc = (k + 0.5) * geo.epi_pitch - phase_y
        y0 = int(round(yc - bh / 2.0))
        if 0 <= y0 and y0 + bh <= h:
            ys.append(y0)
    xs: List[int] = []
    g0 = int(np.floor(-phase_x / geo.mg_pitch)) - 1
    for gi in range(g0, g0 + int(w / geo.mg_pitch) + 3):
        if gi % int(geo.period) == int(geo.absent) % int(geo.period):
            continue                     # 這一根不在，沒有交界
        left = gi * geo.mg_pitch - phase_x
        for edge_x in (left, left + geo.mg_width):
            x0 = int(round(edge_x - bw / 2.0))
            if 0 <= x0 and x0 + bw <= w:
                xs.append(x0)
    del span
    return [(x0, y0, int(round(bw)), int(round(bh)))
            for x0 in sorted(set(xs)) for y0 in sorted(set(ys))]


def plant_inner_space_defect(img: np.ndarray, kind: str,
                             rng: "np.random.Generator",
                             geo: Geometry = GEOMETRY,
                             phase_x: float = 0.0,
                             phase_y: float = 0.0,
                             lv: Levels = LEVELS) -> Tuple[int, int]:
    """在**離中心最近的那一條 inner space** 上種一個缺陷。回傳 ``(x, y)``。

    為什麼一定要落在 inner space 上：使用者 2026-08-28 說「defect 都在這邊」。
    種在別處的合成資料會讓「量 inner space」這件事看起來沒有用 ——
    而那是這份 layout 唯一要量的東西。

    ``missing_line`` 是這個 layout 才有的一種：**一整根 MG 不見了**。
    它不是「一個亮點」，所以任何只看局部對比的做法都抓不到它。
    """
    h, w = img.shape
    amp = float(rng.uniform(55.0, 95.0))
    boxes = inner_space_boxes(h, w, geo, phase_x, phase_y)
    if not boxes:
        cx, cy = w / 2.0, h / 2.0
    else:
        cx0, cy0 = w / 2.0, h / 2.0
        x0, y0, bw, bh = min(
            boxes, key=lambda b: (b[0] + b[2] / 2.0 - cx0) ** 2
            + (b[1] + b[3] / 2.0 - cy0) ** 2)
        cx = x0 + bw / 2.0 + float(rng.uniform(-0.5, 0.5))
        cy = y0 + bh / 2.0 + float(rng.uniform(-bh / 3.0, bh / 3.0))

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if kind == "missing_line":
        # 把最近的那一根 MG 抹掉 —— 讓那一條**退回成 space**。
        #
        # ⚠ 要減掉多少是**逐列不同**的：MG 與 space 的差在 EPI 亮帶上只有
        # 40，在帶與帶之間是 110（見 `Levels`）。第一版減一個常數 40，於是
        # 在暗列上那根線還亮著 —— 一根「不見了」的線在半數的列上還在，
        # 而每一個下游數字都照樣算得出來。
        gi = int(round((cx + phase_x) / geo.mg_pitch))
        left = gi * geo.mg_pitch - phase_x
        d = np.minimum(xx - left, left + geo.mg_width - xx)
        e = _epi(int(h), geo, phase_y)[:, None]
        lo = lv.mg[0] - lv.space[0]
        hi = lv.mg[1] - lv.space[1]
        img -= (lo + e * (hi - lo)) * _smooth(d, geo.edge)
    elif kind == "bridge":
        # 橫跨 space 把兩根 MG 接起來（所以長度就是 space 的寬度）。
        length = max(3.0, geo.mg_pitch - geo.mg_width)
        along = np.clip(np.abs(xx - cx) - length / 2.0, 0.0, None)
        dist = np.hypot(along, np.abs(yy - cy))
        img += amp * np.clip(1.0 - (dist - 1.2), 0.0, 1.0).astype(np.float32)
    else:
        sigma = float(rng.uniform(1.4, 2.6))
        bump = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma ** 2))
        img += (amp if kind == "bright_blob" else -amp) * bump.astype(np.float32)
    return int(round(cx)), int(round(cy))
