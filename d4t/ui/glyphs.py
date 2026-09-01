# d4t Studio — 設定區那些膠囊上的小圖（F68 第二輪，2026-09-01）。
"""膠囊圖示：**一格選項在問什麼**，畫成一張 19 px 的小圖。

使用者 2026-09-01：「同時請整理所有卡片，我認為設定區都要變成這樣
icon 膠囊 + 文字，並且**視覺模型可能要接近**會比較好。」

為什麼是一個新模組
------------------
`widgets.py` 已經很大，而 `CLAUDE.md` §4 早就指名「那幾群自繪圖示最好拆、
風險最低」。這一輪一次加五十幾張圖 —— 全部塞回去只會讓那個檔案更難動。
`widgets.draw_glyph_icon` 仍然是**唯一的入口**（它會把這一族轉進來），
所以呼叫端一行都不用改。

共通文法（「視覺模型要接近」就是這一段）
----------------------------------------
1. **淡的是原本就在那裡的東西**（影像、圖案、所有的框），
   **實心的才是這個選項在講的那件事**。這條是 F11 Region-2 那一族傳下來的。
2. **同一排的差別做在位置與形狀，不做在粗細。** 19 px 下線的粗細分不出來
   （F11 Region-2 render 過確認）。
3. **一排裡的每一顆共用同一個底**：同一族的圖疊在一起要看得出是同一件事的
   幾種答案，而不是幾張不相干的插圖。
4. **只有畫得出來的才畫。** 「這個選項長什麼樣」答不出來的時候，圖是裝飾，
   而裝飾會讓使用者以為那裡有意思可以讀（膠囊上還有字，字才是意思）。

⚠ 所有名字都要進 :data:`CHIP_ICONS`，而 `widgets.GLYPH_ICONS` 會把它接起來
—— `tests/test_ui_f7_23_buttons.py` 會把每一顆都畫一次，畫出來幾乎是空的就
擋下來。
"""
from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

__all__ = ["CHIP_ICONS", "draw_chip_icon"]

#: 這一族的每一顆。**分組寫，而且註解說的是那一排在問什麼** ——
#: 名字本身只說「這顆畫的是什麼」，說不出它為什麼存在。
CHIP_ICONS = (
    # GLV：一個區域裡的那些格子（F68 第一輪）
    "boxes_pooled", "boxes_each",
    "odd_darker", "odd_brighter", "odd_either",
    "pair_each", "pair_pooled",
    # Normalize：亮度要拉到哪裡（都畫在同一張直方圖上）
    "norm_percentile", "norm_zscore", "norm_band", "norm_match", "norm_local",
    # Normalize：兩張圖的分布要怎麼對上（都畫成一條對應曲線）
    "hist_exact", "hist_linear", "hist_pct",
    # 兩張卡共用的兩種估計方式（Denoise 的濾波、Flatten 的背景）
    "op_median", "op_gaussian",
    # Denoise：雜訊要怎麼處理（都畫在同一張有雜點的影像上）
    "dn_hot", "dn_bilateral", "dn_nlm",
    # Flatten：要拿掉的是什麼（都畫在同一張影像上，實心的就是要拿掉的東西）
    "fl_background", "fl_stripes_h", "fl_stripes_v",
    "fl_bright_spots", "fl_dark_spots",
    # Image Combination：兩張圖怎麼合成一張（畫的是那個運算的符號）
    "op_subtract", "op_ratio", "op_max", "op_min", "op_mean",
    # Pair：兩份資料的同一顆怎麼認出來
    "match_position", "match_id", "match_order",
    # Region：哪裡該長得一樣，是從哪裡知道的
    "src_stripes", "src_cell", "src_layout",
    # Region：要用第幾亮／第幾暗的那一組（同一張亮度階梯，選中的那一格伸出去）
    "rank_bright1", "rank_bright2", "rank_bright3",
    "rank_dark1", "rank_dark2", "rank_dark3", "rank_all",
    # Region：哪一個框是缺陷所在的那一個
    "pick_centre", "pick_none",
    # CD：邊在哪裡（都畫在同一條邊的亮度剖面上）
    "crit_threshold", "crit_gradient", "crit_fit",
    # Output：圖檔格式、其他框畫不畫、KLARF 怎麼寫回
    "fmt_jpeg", "fmt_png",
    "drawn_all", "drawn_none", "drawn_near",
    "klarf_inplace", "klarf_annotate", "klarf_topn",
    # Align（收起來的那張卡）：兩張圖是怎麼對上的
    "al_phase", "al_hybrid", "al_ncc", "al_ecc", "al_template",
)

#: 「原本就在那裡的東西」的透明度。跟 `widgets._draw_profile_glyph` 同一個值
#: —— 兩族並排在同一個面板上，淡的程度不一樣的話會看起來像兩套東西。
FAINT_ALPHA = 58


class _Pad(object):
    """一張正規化到 0–1 的畫布：座標寫比例，這裡換成像素。

    每一顆圖示都只用這幾支（塊、點、線、折線）—— 工具少，畫出來的東西就自然
    像同一套（那正是「視覺模型要接近」要的）。
    """

    def __init__(self, p: QPainter, w: float, h: float, color: str):
        self.p, self.w, self.h = p, w, h
        self.solid = QColor(color)
        self.faint = QColor(color)
        self.faint.setAlpha(FAINT_ALPHA)

    def ink(self, on: bool) -> QColor:
        return self.solid if on else self.faint

    def blk(self, x0: float, y0: float, x1: float, y1: float,
            on: bool = True) -> None:
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(self.ink(on))
        self.p.drawRect(QRectF(x0 * self.w, y0 * self.h,
                               (x1 - x0) * self.w, (y1 - y0) * self.h))

    def dot(self, cx: float, cy: float, r: float, on: bool = True) -> None:
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(self.ink(on))
        self.p.drawEllipse(QPointF(cx * self.w, cy * self.h),
                           r * self.w, r * self.w)

    def line(self, x0: float, y0: float, x1: float, y1: float,
             on: bool = True, width: float = 0.09,
             dashed: bool = False) -> None:
        pen = QPen(self.ink(on), max(1.0, width * self.w))
        if dashed:
            pen.setStyle(Qt.DotLine)
        self.p.setPen(pen)
        self.p.setBrush(Qt.NoBrush)
        self.p.drawLine(QPointF(x0 * self.w, y0 * self.h),
                        QPointF(x1 * self.w, y1 * self.h))

    def poly(self, pts: List[Tuple[float, float]], on: bool = True,
             width: float = 0.09) -> None:
        path = QPainterPath()
        path.moveTo(pts[0][0] * self.w, pts[0][1] * self.h)
        for x, y in pts[1:]:
            path.lineTo(x * self.w, y * self.h)
        self.p.setPen(QPen(self.ink(on), max(1.0, width * self.w)))
        self.p.setBrush(Qt.NoBrush)
        self.p.drawPath(path)

    def frame(self, x0: float, y0: float, x1: float, y1: float,
              on: bool = True, width: float = 0.07) -> None:
        self.p.setPen(QPen(self.ink(on), max(1.0, width * self.w)))
        self.p.setBrush(Qt.NoBrush)
        self.p.drawRect(QRectF(x0 * self.w, y0 * self.h,
                               (x1 - x0) * self.w, (y1 - y0) * self.h))

    #: 一張淡的直方圖（Normalize 那一排共用的底）。回傳每根的 x 中心。
    HIST = (0.16, 0.34, 0.62, 0.92, 0.70, 0.44, 0.22)

    def hist(self, on: bool = False, x0: float = 0.06, x1: float = 0.94,
             base: float = 0.92, top: float = 0.10) -> List[float]:
        n = len(self.HIST)
        step = (x1 - x0) / n
        xs = []
        for i, tall in enumerate(self.HIST):
            bx = x0 + i * step
            self.blk(bx, base - (base - top) * tall, bx + step * 0.78,
                     base, on)
            xs.append(bx + step * 0.39)
        return xs


def draw_chip_icon(p: QPainter, name: str, size: float, color: str) -> None:
    """在 ``p`` 的目前原點畫一張 ``size`` × ``size`` 的膠囊小圖。

    呼叫端請走 `widgets.draw_glyph_icon`（同一個入口，同一張名字表）。
    """
    if name not in CHIP_ICONS:
        raise ValueError("unknown chip icon: %r" % (name,))
    g = _Pad(p, float(size), float(size), color)
    _DRAW[name](g)
    p.setPen(Qt.NoPen)
    p.setBrush(Qt.NoBrush)


# --------------------------------------------------------------------------- #
# GLV：一個區域裡的那些格子
# --------------------------------------------------------------------------- #
def _boxes_pooled(g: _Pad) -> None:
    # 四格**擠成一塊**：格子還在（縫是背景色，在任何底色上都成立），但四格
    # 長得一模一樣 —— 「它們被當成同一堆像素」。
    for x in (0.08, 0.51):
        for y in (0.08, 0.51):
            g.blk(x, y, x + 0.41, y + 0.41, True)


def _boxes_each(g: _Pad) -> None:
    # 四格**分開**，其中一格是實心的 —— 那就是「挑出來的那一格」。
    g.blk(0.08, 0.08, 0.45, 0.45, False)
    g.blk(0.55, 0.08, 0.92, 0.45, True)
    g.blk(0.08, 0.55, 0.45, 0.92, False)
    g.blk(0.55, 0.55, 0.92, 0.92, False)


def _odd(g: _Pad, down: bool, up: bool) -> None:
    # 一條基準線 ＋ 幾根從線上長出來的柱子。**偏出去的那一根往哪跑**就是這一
    # 顆在講的事：往下＝比較暗、往上＝比較亮、兩根＝兩邊都算。
    g.line(0.04, 0.5, 0.96, 0.5, False, 0.06)
    g.blk(0.10, 0.44, 0.28, 0.56, False)
    if down and up:
        g.blk(0.36, 0.50, 0.54, 0.92, True)
        g.blk(0.62, 0.08, 0.80, 0.50, True)
        return
    g.blk(0.36, 0.44, 0.54, 0.56, False)
    if down:
        g.blk(0.62, 0.50, 0.80, 0.92, True)
    else:
        g.blk(0.62, 0.08, 0.80, 0.50, True)


def _pair_each(g: _Pad) -> None:
    # 上下各三格，**中間那一對牽起來** —— 「第 i 格對第 i 格」。
    for x, on in ((0.06, False), (0.41, True), (0.76, False)):
        g.blk(x, 0.06, x + 0.18, 0.34, on)
        g.blk(x, 0.66, x + 0.18, 0.94, on)
    g.line(0.50, 0.34, 0.50, 0.66, True, 0.07)


def _pair_pooled(g: _Pad) -> None:
    # 上面三格，下面**一整條** —— 每一格對的都是同一個數字。
    for x in (0.06, 0.41, 0.76):
        g.blk(x, 0.06, x + 0.18, 0.34, False)
        g.line(x + 0.09, 0.34, x + 0.09, 0.66, False, 0.05)
    g.blk(0.06, 0.66, 0.94, 0.94, True)


# --------------------------------------------------------------------------- #
# Normalize：亮度要拉到哪裡（同一張直方圖，差別在**動到哪一段**）
# --------------------------------------------------------------------------- #
def _norm_percentile(g: _Pad) -> None:
    # 兩端各切一刀，中間那段拉開。
    g.hist(False)
    g.line(0.18, 0.04, 0.18, 0.96, True, 0.08)
    g.line(0.82, 0.04, 0.82, 0.96, True, 0.08)


def _norm_zscore(g: _Pad) -> None:
    # 平均值釘在中間、散布釘成固定寬度：一條中線 ＋ 一段左右對稱的跨距。
    g.hist(False)
    g.line(0.50, 0.04, 0.50, 0.74, True, 0.08)
    g.blk(0.26, 0.82, 0.74, 0.94, True)


def _norm_band(g: _Pad) -> None:
    # 只用**落在某一段灰階裡**的像素：中間那幾根實心，兩側維持淡的。
    xs = g.hist(False)
    g.hist(True, x0=0.06 + (0.88 / 7) * 2, x1=0.06 + (0.88 / 7) * 5)
    g.line(0.06 + (0.88 / 7) * 2, 0.04, 0.06 + (0.88 / 7) * 2, 0.96,
           True, 0.06)
    g.line(0.06 + (0.88 / 7) * 5, 0.04, 0.06 + (0.88 / 7) * 5, 0.96,
           True, 0.06)
    del xs


def _norm_match(g: _Pad) -> None:
    # 不決定範圍，**照著另一條流的分布**：同一個駝峰畫兩次，一淡一實，
    # 只差在位置 —— 「把這一條搬到那一條上面去」。
    hump = [(0.00, 0.90), (0.10, 0.80), (0.20, 0.34), (0.30, 0.26),
            (0.42, 0.62), (0.52, 0.88)]
    g.poly([(x + 0.04, y) for x, y in hump], False, 0.10)
    g.poly([(x + 0.44, y) for x, y in hump], True, 0.10)


def _norm_local(g: _Pad) -> None:
    # 一格一格自己拉（CLAHE）：四格，每一格有自己的一小段。
    for x in (0.06, 0.54):
        for y in (0.06, 0.54):
            g.frame(x, y, x + 0.40, y + 0.40, False, 0.06)
            g.blk(x + 0.09, y + 0.24, x + 0.31, y + 0.33, True)


# --------------------------------------------------------------------------- #
# Normalize：兩張圖的分布怎麼對上（同一條「對應曲線」）
# --------------------------------------------------------------------------- #
def _hist_exact(g: _Pad) -> None:
    # 完全一樣：一條照著分布彎的曲線（不是直線 —— 那正是它跟 linear 的差別）。
    g.line(0.06, 0.94, 0.94, 0.06, False, 0.05)
    g.poly([(0.08, 0.92), (0.30, 0.78), (0.46, 0.36), (0.66, 0.26),
            (0.92, 0.08)], True, 0.10)


def _hist_linear(g: _Pad) -> None:
    # 只對平均值與散布：一條直線。
    g.poly([(0.08, 0.92), (0.92, 0.08)], True, 0.10)


def _hist_pct(g: _Pad) -> None:
    # 對 P2–P98：同一條直線，但兩端切掉。
    g.poly([(0.08, 0.92), (0.92, 0.08)], False, 0.08)
    g.poly([(0.26, 0.74), (0.74, 0.26)], True, 0.11)
    g.line(0.26, 0.60, 0.26, 0.88, True, 0.06)
    g.line(0.74, 0.12, 0.74, 0.40, True, 0.06)


# --------------------------------------------------------------------------- #
# 兩張卡共用的兩種估計方式
# --------------------------------------------------------------------------- #
def _op_median(g: _Pad) -> None:
    # 3×3 的窗，**中間那一格被換掉** —— 中位數濾波在做的就是這件事。
    for i in range(3):
        for j in range(3):
            on = (i == 1 and j == 1)
            g.blk(0.08 + i * 0.29, 0.08 + j * 0.29,
                  0.08 + i * 0.29 + 0.23, 0.08 + j * 0.29 + 0.23, on)


def _op_gaussian(g: _Pad) -> None:
    # 加權平均：越靠中間越重（三層方框，中間實心）。
    g.blk(0.08, 0.08, 0.92, 0.92, False)
    g.blk(0.24, 0.24, 0.76, 0.76, False)
    g.blk(0.38, 0.38, 0.62, 0.62, True)


# --------------------------------------------------------------------------- #
# Denoise：雜訊怎麼處理（同一張有雜點的影像）
# --------------------------------------------------------------------------- #
def _dn_hot(g: _Pad) -> None:
    # 只動**那幾顆離譜的**：四顆雜點裡圈起來的那一顆才是要換掉的。
    g.blk(0.06, 0.06, 0.94, 0.94, False)
    for cx, cy in ((0.26, 0.30), (0.68, 0.24), (0.36, 0.74)):
        g.dot(cx, cy, 0.06, False)
    g.dot(0.66, 0.68, 0.09, True)
    g.frame(0.52, 0.54, 0.80, 0.82, True, 0.07)


def _dn_bilateral(g: _Pad) -> None:
    # 磨平雜訊但**留住邊**：一半亮一半暗，中間那條邊是實心的。
    g.blk(0.06, 0.06, 0.48, 0.94, False)
    g.line(0.50, 0.04, 0.50, 0.96, True, 0.10)
    g.blk(0.52, 0.06, 0.94, 0.94, False)
    g.dot(0.26, 0.30, 0.06, False)
    g.dot(0.74, 0.70, 0.06, False)


def _dn_nlm(g: _Pad) -> None:
    # 去別的地方找**長得一樣的一塊**來平均：兩塊一樣的小方框牽起來。
    g.blk(0.06, 0.06, 0.94, 0.94, False)
    g.frame(0.10, 0.14, 0.38, 0.42, True, 0.08)
    g.frame(0.60, 0.56, 0.88, 0.84, True, 0.08)
    g.line(0.38, 0.42, 0.60, 0.56, True, 0.06)


# --------------------------------------------------------------------------- #
# Flatten：要拿掉的是什麼（同一張影像，實心的就是要拿掉的東西）
# --------------------------------------------------------------------------- #
def _fl_background(g: _Pad) -> None:
    # 一片緩緩變亮的底：四條越來越實的直帶。
    for i in range(4):
        col = QColor(g.solid)
        col.setAlpha(int(FAINT_ALPHA + (255 - FAINT_ALPHA) * (i / 3.0)))
        g.p.setPen(Qt.NoPen)
        g.p.setBrush(col)
        g.p.drawRect(QRectF((0.06 + i * 0.22) * g.w, 0.14 * g.h,
                            0.20 * g.w, 0.72 * g.h))


def _fl_stripes_h(g: _Pad) -> None:
    for y in (0.10, 0.44, 0.78):
        g.blk(0.06, y, 0.94, y + 0.14, True)


def _fl_stripes_v(g: _Pad) -> None:
    for x in (0.10, 0.44, 0.78):
        g.blk(x, 0.06, x + 0.14, 0.94, True)


def _fl_bright_spots(g: _Pad) -> None:
    # 留下**比這個尺寸小的亮東西**：一張淡的底 ＋ 一顆實心的點。
    g.blk(0.06, 0.06, 0.94, 0.94, False)
    g.dot(0.50, 0.50, 0.17, True)


def _fl_dark_spots(g: _Pad) -> None:
    # 同一張圖，反過來：亮的那顆是實心的圓，暗的那顆是一個**圈**（一個洞）。
    #
    # ⚠ 不要用 ``CompositionMode_Clear`` 去「挖」—— 那會把膠囊自己的底色一起
    # 挖掉（第一版真的挖出一個黑洞）。這一族只准往上加墨，不准擦。
    g.blk(0.06, 0.06, 0.94, 0.94, False)
    g.p.setPen(QPen(g.solid, max(1.0, 0.12 * g.w)))
    g.p.setBrush(Qt.NoBrush)
    g.p.drawEllipse(QPointF(0.50 * g.w, 0.50 * g.h), 0.14 * g.w, 0.14 * g.w)


# --------------------------------------------------------------------------- #
# Image Combination：兩張圖怎麼變一張（畫那個運算的符號）
# --------------------------------------------------------------------------- #
def _two_images(g: _Pad) -> None:
    """兩張圖擺在兩邊 —— 這一排五顆共用的底，中間留給那個運算。"""
    g.blk(0.02, 0.26, 0.28, 0.74, False)
    g.blk(0.72, 0.26, 0.98, 0.74, False)


def _op_subtract(g: _Pad) -> None:
    _two_images(g)
    g.blk(0.34, 0.44, 0.66, 0.56, True)                  # 減號


def _op_ratio(g: _Pad) -> None:
    _two_images(g)
    g.dot(0.50, 0.28, 0.07, True)                        # 除號
    g.blk(0.34, 0.45, 0.66, 0.55, True)
    g.dot(0.50, 0.72, 0.07, True)


def _op_max(g: _Pad) -> None:
    _two_images(g)
    g.poly([(0.34, 0.66), (0.50, 0.32), (0.66, 0.66)], True, 0.11)


def _op_min(g: _Pad) -> None:
    _two_images(g)
    g.poly([(0.34, 0.34), (0.50, 0.68), (0.66, 0.34)], True, 0.11)


def _op_mean(g: _Pad) -> None:
    # 平均 = 兩張**疊在一起**：中間那一塊是兩邊都有的地方。
    g.blk(0.02, 0.26, 0.58, 0.74, False)
    g.blk(0.42, 0.26, 0.98, 0.74, False)
    g.blk(0.42, 0.26, 0.58, 0.74, True)


# --------------------------------------------------------------------------- #
# Pair：兩份資料的同一顆怎麼認出來
# --------------------------------------------------------------------------- #
def _match_position(g: _Pad) -> None:
    # 座標上最近的那一顆：一個容差圈，圈裡一顆實心。
    g.frame(0.06, 0.06, 0.94, 0.94, False, 0.06)
    g.p.setPen(QPen(g.solid, max(1.0, 0.07 * g.w), Qt.DotLine))
    g.p.setBrush(Qt.NoBrush)
    g.p.drawEllipse(QPointF(0.46 * g.w, 0.52 * g.h), 0.28 * g.w, 0.28 * g.w)
    g.dot(0.46, 0.52, 0.09, True)
    g.dot(0.80, 0.20, 0.07, False)


def _match_id(g: _Pad) -> None:
    # 兩邊同一個號碼：兩張小牌子 ＋ 中間一個等號。
    g.blk(0.04, 0.24, 0.34, 0.76, False)
    g.blk(0.66, 0.24, 0.96, 0.76, False)
    g.blk(0.40, 0.38, 0.60, 0.47, True)
    g.blk(0.40, 0.55, 0.60, 0.64, True)


def _match_order(g: _Pad) -> None:
    # 第一顆對第一顆：兩排點，一條一條平接。
    for i, y in enumerate((0.16, 0.50, 0.84)):
        g.dot(0.12, y, 0.08, i == 0)
        g.dot(0.88, y, 0.08, i == 0)
        g.line(0.20, y, 0.80, y, i == 0, 0.05)


# --------------------------------------------------------------------------- #
# Region：哪裡該長得一樣，是從哪裡知道的
# --------------------------------------------------------------------------- #
def _src_stripes(g: _Pad) -> None:
    # 影像裡的條紋：卡片自己找得到，框長在條紋上。
    for x in (0.08, 0.40, 0.72):
        g.blk(x, 0.06, x + 0.20, 0.94, False)
    g.blk(0.40, 0.34, 0.60, 0.66, True)


def _src_cell(g: _Pad) -> None:
    # 自己在一格 cell 上標一次：一個框 ＋ 四個角的標記。
    g.frame(0.06, 0.06, 0.94, 0.94, False, 0.07)
    g.blk(0.30, 0.30, 0.70, 0.70, True)
    for x in (0.06, 0.86):
        for y in (0.06, 0.86):
            g.blk(x, y, x + 0.08, y + 0.08, True)


def _src_layout(g: _Pad) -> None:
    # 版圖的一層：兩層錯開的方框，實心的是選中的那一層。
    g.frame(0.04, 0.24, 0.66, 0.86, False, 0.07)
    g.blk(0.34, 0.10, 0.96, 0.72, True)


# --------------------------------------------------------------------------- #
# Region：第幾亮／第幾暗的那一組
#
# 同一張「亮度階梯」：六格由亮到暗（左邊那條漸層說明哪一端是亮的），
# **選中的那一格伸出去**。位置就是答案 —— 六顆並排時唯一的差別。
# --------------------------------------------------------------------------- #
def _rank(g: _Pad, idx: int, every: bool = False) -> None:
    n = 6
    pitch = 0.86 / n
    for i in range(n):
        y = 0.07 + i * pitch
        on = every or (i == idx)
        g.blk(0.30 if not on else 0.30, y, 0.96 if on else 0.66,
              y + pitch * 0.62, on)
    # 左邊那條由淡到實的柱子 = 由亮到暗（哪一端是亮的，這條說了算）
    for i in range(n):
        col = QColor(g.solid)
        col.setAlpha(int(FAINT_ALPHA + (255 - FAINT_ALPHA) * (i / (n - 1.0))))
        g.p.setPen(Qt.NoPen)
        g.p.setBrush(col)
        g.p.drawRect(QRectF(0.06 * g.w, (0.07 + i * pitch) * g.h,
                            0.16 * g.w, pitch * 0.62 * g.h))


# --------------------------------------------------------------------------- #
# Region：哪一個框是缺陷所在的那一個
# --------------------------------------------------------------------------- #
def _pick(g: _Pad, centre: bool) -> None:
    for i in range(3):
        for j in range(3):
            on = centre and i == 1 and j == 1
            g.blk(0.08 + i * 0.29, 0.08 + j * 0.29,
                  0.08 + i * 0.29 + 0.23, 0.08 + j * 0.29 + 0.23, on)


# --------------------------------------------------------------------------- #
# CD：邊在哪裡（同一條邊的亮度剖面）
# --------------------------------------------------------------------------- #
_EDGE = [(0.06, 0.82), (0.26, 0.78), (0.44, 0.52), (0.62, 0.24), (0.94, 0.18)]


def _crit_threshold(g: _Pad) -> None:
    # 亮度**穿過某個高度**的地方。
    g.poly(_EDGE, False, 0.09)
    g.line(0.04, 0.52, 0.96, 0.52, True, 0.07)
    g.dot(0.44, 0.52, 0.10, True)


def _crit_gradient(g: _Pad) -> None:
    # **變化最快**的地方：剖面下面那根最高的柱子。
    g.poly(_EDGE, False, 0.09)
    g.blk(0.36, 0.60, 0.52, 0.96, True)
    g.blk(0.20, 0.84, 0.32, 0.96, False)
    g.blk(0.56, 0.80, 0.68, 0.96, False)


def _crit_fit(g: _Pad) -> None:
    # 拿一條 S 曲線去**配整段斜坡**：實線是配出來的，點是量到的。
    g.poly(_EDGE, True, 0.10)
    for x, y in ((0.20, 0.86), (0.36, 0.64), (0.54, 0.32), (0.76, 0.14)):
        g.dot(x, y, 0.07, False)


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _fmt_jpeg(g: _Pad) -> None:
    # 壓縮過的圖：一張圖，右下角糊成一塊一塊。
    g.frame(0.06, 0.06, 0.94, 0.94, False, 0.07)
    g.blk(0.16, 0.16, 0.48, 0.48, True)
    g.blk(0.52, 0.52, 0.84, 0.84, False)


def _fmt_png(g: _Pad) -> None:
    # 每一個像素都照畫的樣子：一張圖，格子是清清楚楚的。
    g.frame(0.06, 0.06, 0.94, 0.94, False, 0.07)
    for i in range(3):
        for j in range(3):
            if (i + j) % 2 == 0:
                g.blk(0.16 + i * 0.23, 0.16 + j * 0.23,
                      0.16 + i * 0.23 + 0.20, 0.16 + j * 0.23 + 0.20, True)


def _drawn(g: _Pad, mode: str) -> None:
    # 中間那一格永遠是**贏的那一格**（畫粗）；差別在**其他格畫不畫**。
    for i in range(3):
        for j in range(3):
            near = abs(i - 1) + abs(j - 1) <= 1
            if i == 1 and j == 1:
                continue
            if mode == "none" or (mode == "near" and not near):
                continue
            g.frame(0.06 + i * 0.30, 0.06 + j * 0.30,
                    0.06 + i * 0.30 + 0.24, 0.06 + j * 0.30 + 0.24,
                    False, 0.05)
    g.frame(0.36, 0.36, 0.60, 0.60, True, 0.10)


def _klarf_inplace(g: _Pad) -> None:
    # 就地改那一份：一份檔案，只有幾個位元組是實心的。
    g.frame(0.16, 0.06, 0.84, 0.94, False, 0.07)
    g.blk(0.26, 0.24, 0.74, 0.33, False)
    g.blk(0.26, 0.46, 0.74, 0.55, True)
    g.blk(0.26, 0.68, 0.74, 0.77, False)


def _klarf_annotate(g: _Pad) -> None:
    # 另存一份：左邊原檔（淡的、不動），右邊新的多了兩欄。
    g.frame(0.04, 0.10, 0.42, 0.90, False, 0.07)
    g.frame(0.58, 0.10, 0.96, 0.90, True, 0.07)
    g.blk(0.66, 0.28, 0.88, 0.37, True)
    g.blk(0.66, 0.52, 0.88, 0.61, True)


def _klarf_topn(g: _Pad) -> None:
    # 只留分數最高的幾顆：一份清單，上面兩列是實心的。
    g.frame(0.16, 0.06, 0.84, 0.94, False, 0.07)
    g.blk(0.26, 0.20, 0.74, 0.30, True)
    g.blk(0.26, 0.38, 0.74, 0.48, True)
    g.blk(0.26, 0.56, 0.60, 0.66, False)
    g.blk(0.26, 0.74, 0.60, 0.84, False)


# --------------------------------------------------------------------------- #
# Align（收起來的那張卡）：兩張圖是怎麼對上的
# --------------------------------------------------------------------------- #
def _al_phase(g: _Pad) -> None:
    # 整張圖一次算出位移：兩條錯開的波。
    g.poly([(0.06, 0.34), (0.28, 0.12), (0.50, 0.34), (0.72, 0.12),
            (0.94, 0.34)], False, 0.09)
    g.poly([(0.06, 0.86), (0.28, 0.64), (0.50, 0.86), (0.72, 0.64),
            (0.94, 0.86)], True, 0.09)


def _al_hybrid(g: _Pad) -> None:
    # 跟 phase 一樣，只是多走一趟：同兩條波 ＋ 一個中間的落點。
    _al_phase(g)
    g.dot(0.50, 0.50, 0.10, True)


def _al_ncc(g: _Pad) -> None:
    # 每一個位置都試一次：滿滿的格點，命中的那一格是實心的。
    for i in range(3):
        for j in range(3):
            g.dot(0.20 + i * 0.30, 0.20 + j * 0.30, 0.07,
                  i == 1 and j == 2)


def _al_ecc(g: _Pad) -> None:
    # 一次一次逼近：三個越縮越小的框。
    g.frame(0.06, 0.06, 0.94, 0.94, False, 0.06)
    g.frame(0.22, 0.22, 0.78, 0.78, False, 0.06)
    g.frame(0.38, 0.38, 0.62, 0.62, True, 0.09)


def _al_template(g: _Pad) -> None:
    # 拿中間那一小塊去比對。
    g.frame(0.06, 0.06, 0.94, 0.94, False, 0.06)
    g.blk(0.34, 0.34, 0.66, 0.66, True)


#: 名字 → 畫它的那支。**這張表就是 `CHIP_ICONS` 的實作**，兩邊由
#: `test_ui_chip_icons` 對得起來（少一支的症狀是那顆膠囊直接 ValueError）。
_DRAW = {
    "boxes_pooled": _boxes_pooled,
    "boxes_each": _boxes_each,
    "odd_darker": lambda g: _odd(g, True, False),
    "odd_brighter": lambda g: _odd(g, False, True),
    "odd_either": lambda g: _odd(g, True, True),
    "pair_each": _pair_each,
    "pair_pooled": _pair_pooled,
    "norm_percentile": _norm_percentile,
    "norm_zscore": _norm_zscore,
    "norm_band": _norm_band,
    "norm_match": _norm_match,
    "norm_local": _norm_local,
    "hist_exact": _hist_exact,
    "hist_linear": _hist_linear,
    "hist_pct": _hist_pct,
    "op_median": _op_median,
    "op_gaussian": _op_gaussian,
    "dn_hot": _dn_hot,
    "dn_bilateral": _dn_bilateral,
    "dn_nlm": _dn_nlm,
    "fl_background": _fl_background,
    "fl_stripes_h": _fl_stripes_h,
    "fl_stripes_v": _fl_stripes_v,
    "fl_bright_spots": _fl_bright_spots,
    "fl_dark_spots": _fl_dark_spots,
    "op_subtract": _op_subtract,
    "op_ratio": _op_ratio,
    "op_max": _op_max,
    "op_min": _op_min,
    "op_mean": _op_mean,
    "match_position": _match_position,
    "match_id": _match_id,
    "match_order": _match_order,
    "src_stripes": _src_stripes,
    "src_cell": _src_cell,
    "src_layout": _src_layout,
    "rank_bright1": lambda g: _rank(g, 0),
    "rank_bright2": lambda g: _rank(g, 1),
    "rank_bright3": lambda g: _rank(g, 2),
    "rank_dark3": lambda g: _rank(g, 3),
    "rank_dark2": lambda g: _rank(g, 4),
    "rank_dark1": lambda g: _rank(g, 5),
    "rank_all": lambda g: _rank(g, -1, every=True),
    "pick_centre": lambda g: _pick(g, True),
    "pick_none": lambda g: _pick(g, False),
    "crit_threshold": _crit_threshold,
    "crit_gradient": _crit_gradient,
    "crit_fit": _crit_fit,
    "fmt_jpeg": _fmt_jpeg,
    "fmt_png": _fmt_png,
    "drawn_all": lambda g: _drawn(g, "all"),
    "drawn_none": lambda g: _drawn(g, "none"),
    "drawn_near": lambda g: _drawn(g, "near"),
    "klarf_inplace": _klarf_inplace,
    "klarf_annotate": _klarf_annotate,
    "klarf_topn": _klarf_topn,
    "al_phase": _al_phase,
    "al_hybrid": _al_hybrid,
    "al_ncc": _al_ncc,
    "al_ecc": _al_ecc,
    "al_template": _al_template,
}
