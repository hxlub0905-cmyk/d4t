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
    # Compare：兩張圖怎麼比（畫的是那個運算的符號）
    "op_subtract", "op_ratio", "op_normalized", "op_over_sigma",
    # Compare：亮的與暗的怎麼處理
    "sign_abs", "sign_signed", "sign_split",
    # Image Combination：好幾張怎麼併成一張（F110 從上面那一排拆出來）
    "op_max", "op_min", "op_mean", "op_trimmed",
    # Pair：兩份資料的同一顆怎麼認出來
    "match_position", "match_id", "match_order",
    # Region：哪裡該長得一樣，是從哪裡知道的
    "src_stripes", "src_cell", "src_layout",
    # Region：要用第幾亮／第幾暗的那一組（同一張亮度階梯，選中的那一格伸出去）
    "rank_bright1", "rank_bright2", "rank_bright3",
    "rank_dark1", "rank_dark2", "rank_dark3", "rank_all",
    # Region：哪一個框是缺陷所在的那一個
    "pick_centre", "pick_none",
    # 判定：這一類是好消息還是壞消息（F119）
    "news_good", "news_review", "news_none",
    # CD：邊在哪裡（都畫在同一條邊的亮度剖面上）
    "crit_threshold", "crit_gradient", "crit_fit",
    # Focus index：OP-301 那四個步驟跑在哪一張圖上（同一張影像，
    # 實心的是**在量的那個東西**：一整片灰階 vs 兩片之間那條邊）
    "iqi_pixel", "iqi_gradient",
    # Output：圖檔格式、其他框畫不畫、KLARF 怎麼寫回
    "fmt_jpeg", "fmt_png",
    "drawn_all", "drawn_none", "drawn_near",
    "klarf_inplace", "klarf_annotate", "klarf_topn",
    # Align（收起來的那張卡）：兩張圖是怎麼對上的
    "al_phase", "al_hybrid", "al_ncc", "al_ecc", "al_template",
    # 判定：這個數字要怎麼用（照原值／跟整批比）
    "scale_raw", "scale_z", "scale_pct",
    # 判定：比較運算子。同一條數線，差別在**箭頭往哪、端點實不實心**
    "cmp_gt", "cmp_ge", "cmp_lt", "cmp_le", "cmp_eq", "cmp_ne",
    # 判定還沒設定時那一塊：**畫的是畫布上真的長那樣的東西**
    # （菱形＝一個問題、托盤＝一個類別）
    "adc_number", "adc_question", "adc_tray",
    # Chart settings（F87 第十刀）：**這張圖要長成哪一種**。
    # 每一排兩顆，差別做在形狀不做在粗細（同 §2 的規矩）。
    "mark_hollow", "mark_solid",          # 記號空心還是實心
    "dots_off", "dots_on",                # 一格框畫不畫記號
    "whisk_off", "whisk_on",              # 盒鬚圖的鬚
    "bars_count", "bars_pct",             # 直方圖的高度是次數還是比例
    "cells_equal", "cells_true",          # 熱圖每一格一樣大還是照實鋪
    "cells_plain", "cells_values",        # 熱圖每一格印不印值
    "range_auto", "range_locked",         # 數值範圍自己挑還是鎖死
    "ramp_mono", "ramp_rainbow",          # 顏色代表大小時走單色階還是彩虹
    # Graph builder（F88 第三刀）：**這張圖用哪一種記號**。
    "mark_dots", "mark_line", "mark_bars",
    # F89-5：值那一軸的尺、以及長條要不要照值排
    "scale_linear", "scale_log",
    "sort_none", "sort_asc", "sort_desc",
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


def _op_normalized(g: _Pad) -> None:
    # 正規化差 = 差**除以和**：上面一條減號、下面一條加號，中間一條分隔線。
    _two_images(g)
    g.blk(0.36, 0.30, 0.64, 0.38, True)                  # 減號（分子）
    g.blk(0.34, 0.47, 0.66, 0.53, True)                  # 分隔線
    g.blk(0.36, 0.62, 0.64, 0.70, True)                  # 加號的橫
    g.blk(0.46, 0.58, 0.54, 0.74, True)                  # 加號的直


def _op_over_sigma(g: _Pad) -> None:
    # 「差了幾個 σ」= 減號底下一條分隔線，下面是分布的那一座小山。
    _two_images(g)
    g.blk(0.36, 0.32, 0.64, 0.40, True)                  # 減號（分子）
    g.blk(0.34, 0.47, 0.66, 0.53, True)                  # 分隔線
    g.poly([(0.36, 0.74), (0.43, 0.60), (0.50, 0.58),
            (0.57, 0.60), (0.64, 0.74)], True, 0.07)     # 分母：一座鐘形


def _sign_abs(g: _Pad) -> None:
    # 取絕對值 = 亮的與暗的**都往同一邊**：兩支箭頭指向同一條基線的上方。
    g.blk(0.04, 0.74, 0.96, 0.80, True)                  # 基線
    g.poly([(0.20, 0.66), (0.32, 0.30), (0.44, 0.66)], True, 0.09)
    g.poly([(0.56, 0.66), (0.68, 0.30), (0.80, 0.66)], True, 0.09)


def _sign_signed(g: _Pad) -> None:
    # 留正負號 = 一支往上、一支往下，基線在中間。
    g.blk(0.04, 0.47, 0.96, 0.53, True)                  # 基線
    g.poly([(0.20, 0.42), (0.32, 0.12), (0.44, 0.42)], True, 0.09)
    g.poly([(0.56, 0.58), (0.68, 0.88), (0.80, 0.58)], True, 0.09)


def _sign_split(g: _Pad) -> None:
    # 拆兩條 = 兩個**分開的框**，一個裝往上的、一個裝往下的。
    g.blk(0.02, 0.06, 0.46, 0.94, False)
    g.blk(0.54, 0.06, 0.98, 0.94, False)
    g.poly([(0.12, 0.62), (0.24, 0.32), (0.36, 0.62)], True, 0.09)
    g.poly([(0.64, 0.38), (0.76, 0.68), (0.88, 0.38)], True, 0.09)


def _op_trimmed(g: _Pad) -> None:
    # 修剪平均 = 五張裡**兩端各丟掉一張**：中間三條實心、兩端兩條空心。
    for i, solid in enumerate((False, True, True, True, False)):
        x = 0.06 + i * 0.19
        g.blk(x, 0.24, x + 0.13, 0.76, solid)


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
# 判定：這一類是好消息還是壞消息（F119）
# --------------------------------------------------------------------------- #
#
# ⚠ **打勾與驚嘆號是畫出來的，不是字**。F7-23 擋的是「拿 ``✓``／``✕`` 這種
# 字元當圖示」—— 廠內的 Segoe UI 蓋不到那一族，退字型的下場是大小與 baseline
# 都不一樣，最壞是豆腐框。這一支整族存在的理由就是繞過那件事：同樣的形狀，
# 用向量畫，每一台畫出來都一樣。
def _news_good(g: _Pad) -> None:
    g.poly([(0.18, 0.54), (0.40, 0.76), (0.82, 0.26)], True, 0.13)


def _news_review(g: _Pad) -> None:
    g.blk(0.43, 0.14, 0.57, 0.60)
    g.dot(0.50, 0.79, 0.075)


def _news_none(g: _Pad) -> None:
    g.blk(0.18, 0.44, 0.82, 0.56)


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
# IQI：那四個步驟跑在哪一張圖上（F115）
#
# 共用的底是**一張左右分成兩半的影像**（一邊亮一邊暗）。兩顆的差別只在
# 「哪一部分是實心的」—— §1 那條規矩：淡的是原本就在那裡的東西，實心的才是
# 這個選項在講的那件事。
# --------------------------------------------------------------------------- #
def _iqi_base(g: _Pad) -> None:
    g.frame(0.06, 0.06, 0.94, 0.94, False, 0.07)


def _iqi_pixel(g: _Pad) -> None:
    # 量的是**亮度本身**：半張圖實心地填起來（那一整片灰階就是要量的東西）。
    _iqi_base(g)
    g.blk(0.14, 0.14, 0.50, 0.86, True)


def _iqi_gradient(g: _Pad) -> None:
    # 量的是**邊**：同一張圖，兩半都留淡的，只有中間那條交界是實心的。
    _iqi_base(g)
    g.blk(0.14, 0.14, 0.50, 0.86, False)
    g.line(0.50, 0.14, 0.50, 0.86, True, 0.13)


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
    """中間那一格永遠是**贏的那一格**；差別在**其他格畫不畫**。

    ⚠ 其他格畫成**淡的實心塊**而不是細框：19 px 下 1 px 的框幾乎看不見，
    於是三顆長得一樣（render 出來才看到 —— 同 `fill_*` 那一族踩過的坑）。
    """
    for i in range(3):
        for j in range(3):
            if i == 1 and j == 1:
                continue
            near = abs(i - 1) + abs(j - 1) <= 1
            if mode == "none" or (mode == "near" and not near):
                continue
            g.blk(0.04 + i * 0.32, 0.04 + j * 0.32,
                  0.04 + i * 0.32 + 0.24, 0.04 + j * 0.32 + 0.24, False)
    g.blk(0.36, 0.36, 0.60, 0.60, True)


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


# --------------------------------------------------------------------------- #
# 判定：這個數字要怎麼用
#
# 三顆共用同一個底（**一批 defect 的分布**），差別在「這一顆被放在哪一把尺
# 上」—— 那正是這一格在問的事。
# --------------------------------------------------------------------------- #
_BATCH = [(0.06, 0.74), (0.20, 0.66), (0.34, 0.30), (0.50, 0.22),
          (0.66, 0.42), (0.82, 0.66), (0.94, 0.74)]


def _scale_raw(g: _Pad) -> None:
    # 照原值：一條刻度尺，這一顆站在上面。
    g.line(0.04, 0.62, 0.96, 0.62, False, 0.07)
    for x in (0.12, 0.30, 0.48, 0.66, 0.84):
        g.line(x, 0.62, x, 0.76, False, 0.05)
    g.blk(0.56, 0.24, 0.70, 0.62, True)


def _scale_z(g: _Pad) -> None:
    # 跟整批比：分布畫出來，這一顆離中心幾個 σ。
    g.poly(_BATCH, False, 0.08)
    g.line(0.50, 0.16, 0.50, 0.94, False, 0.06)
    g.blk(0.74, 0.34, 0.86, 0.94, True)


def _scale_pct(g: _Pad) -> None:
    # 排名：一疊由低到高，選中的那一階實心。
    for i, y in enumerate((0.74, 0.54, 0.34, 0.14)):
        g.blk(0.10, y, 0.34 + i * 0.18, y + 0.14, i == 2)


# --------------------------------------------------------------------------- #
# 判定：比較運算子
#
# 同一條數線 ＋ 一個門檻點。**箭頭往哪 = 哪一邊算過**，
# **端點實不實心 = 含不含等於** —— 數學課本上就是這麼畫的，不必再學一次。
# --------------------------------------------------------------------------- #
def _cmp(g: _Pad, arrows: str, filled: bool) -> None:
    """一條數線 ＋ 一個門檻點。

    ``arrows`` 是**哪一邊算過**（``right`` / ``left`` / ``both`` / ``""``），
    ``filled`` 是**含不含等於**（實心＝含）。數學課本上就是這麼畫的，所以
    這六顆不必再學一次；而它們並排時唯一的差別正好就是那兩件事。
    """
    y, x0 = 0.54, 0.50
    g.line(0.04, y, 0.96, y, False, 0.07)
    ends = {"right": ((0.94, -0.13),), "left": ((0.06, 0.13),),
            "both": ((0.94, -0.13), (0.06, 0.13))}.get(arrows, ())
    for tip, d in ends:
        g.line(x0, y, tip, y, True, 0.11)
        g.line(tip, y, tip + d, y - 0.17, True, 0.09)
        g.line(tip, y, tip + d, y + 0.17, True, 0.09)
    # 空心那顆畫大一點、線細一點 —— 19 px 下 0.11 半徑配 0.09 的筆幾乎沒有
    # 洞，於是「含不含等於」這個唯一的差別看不出來（render 出來才看到）。
    g.p.setPen(QPen(g.solid, max(1.0, (0.09 if filled else 0.07) * g.w)))
    g.p.setBrush(g.solid if filled else QColor(255, 255, 255, 0))
    r = 0.115 if filled else 0.145
    if not filled:
        g.p.setBrush(Qt.NoBrush)
    g.p.drawEllipse(QPointF(x0 * g.w, y * g.h), r * g.w, r * g.w)


# --------------------------------------------------------------------------- #
# 判定：還沒設定時那一塊在講什麼
#
# ⚠ 這三顆畫的是**畫布上真的長那樣的東西**：判定樹的一步是一個菱形、一個類別
# 是一個托盤（`ui/tree_scene.py`）。空狀態教的是那個畫面，不是另一套比喻 ——
# 教錯的比喻要學兩次。
# --------------------------------------------------------------------------- #
def _adc_number(g: _Pad) -> None:
    # 一疊量出來的數字，挑其中一個。
    for i, y in enumerate((0.10, 0.34, 0.58, 0.82)):
        g.blk(0.10, y, 0.90 if i == 1 else 0.66, y + 0.14, i == 1)


def _adc_question(g: _Pad) -> None:
    # 一個菱形，兩條路出去。
    path = QPainterPath()
    c, r = 0.42, 0.30
    pts = [(c, c - r), (c + r, c), (c, c + r), (c - r, c)]
    path.moveTo(pts[0][0] * g.w, pts[0][1] * g.h)
    for x, y in pts[1:]:
        path.lineTo(x * g.w, y * g.h)
    path.closeSubpath()
    g.p.setPen(QPen(g.solid, max(1.0, 0.09 * g.w)))
    g.p.setBrush(Qt.NoBrush)
    g.p.drawPath(path)
    g.line(c, c + r, c, 0.88, False, 0.07)
    g.line(c + r, c, 0.90, c, False, 0.07)


def _adc_tray(g: _Pad) -> None:
    # 三個托盤，缺陷掉進其中一個。
    g.blk(0.04, 0.60, 0.32, 0.94, False)
    g.blk(0.36, 0.60, 0.64, 0.94, True)
    g.blk(0.68, 0.60, 0.96, 0.94, False)
    g.dot(0.50, 0.24, 0.11, True)
    g.line(0.50, 0.36, 0.50, 0.56, True, 0.07)


# --------------------------------------------------------------------------- #
# Chart settings：這張圖要長成哪一種（F87 第十刀）
#
# 使用者 2026-09-07：「如果可以也能以膠囊方式呈現(like GLV card)」。
# 這一族的底都是**同一張小圖表**（一條基線＋幾個資料點），選項的差別畫在那
# 張圖上 —— 那正是 §3 說的「一排裡的每一顆共用同一個底」。
# --------------------------------------------------------------------------- #
def _marker(g: _Pad, solid: bool) -> None:
    # 三顆記號落在一條淡的線上。**實不實心**就是這一排在問的事。
    g.line(0.06, 0.72, 0.94, 0.72, False, 0.06)
    for cx, cy in ((0.22, 0.62), (0.5, 0.42), (0.78, 0.26)):
        if solid:
            g.dot(cx, cy, 0.11, True)
        else:
            g.p.setPen(QPen(g.solid, max(1.0, 0.07 * g.w)))
            g.p.setBrush(Qt.NoBrush)
            g.p.drawEllipse(QPointF(cx * g.w, cy * g.h), 0.11 * g.w,
                            0.11 * g.w)


def _dots(g: _Pad, on: bool) -> None:
    # 一條趨勢線一定在；**點在不在**是這一排的差別。
    g.poly([(0.08, 0.80), (0.5, 0.50), (0.92, 0.22)], True, 0.08)
    for cx, cy in ((0.08, 0.80), (0.5, 0.50), (0.92, 0.22)):
        g.dot(cx, cy, 0.10, on)


def _whisk(g: _Pad, on: bool) -> None:
    # 一個盒子（實心框）＋ 中位線。**上下那兩根鬚在不在**是差別。
    g.frame(0.26, 0.36, 0.74, 0.72, True, 0.08)
    g.line(0.26, 0.54, 0.74, 0.54, True, 0.09)
    if on:
        g.line(0.5, 0.08, 0.5, 0.36, True, 0.07)
        g.line(0.5, 0.72, 0.5, 0.94, True, 0.07)
        g.line(0.36, 0.08, 0.64, 0.08, True, 0.07)
        g.line(0.36, 0.94, 0.64, 0.94, True, 0.07)


def _bars(g: _Pad, pct: bool) -> None:
    """同一組柱子，差別是**有沒有一個「滿格」當分母**。

    次數：三根高低不一，站在基線上。
    比例：同樣三根，但每一根外面套一個淡的**滿格**框 —— 那就是「佔幾成」的
    畫法（第一版把三根都畫到頂再加一條頂線，而那條線跟柱頂重疊，等於沒畫）。
    """
    g.line(0.04, 0.92, 0.96, 0.92, False, 0.06)
    for i, h in enumerate((0.34, 0.86, 0.56)):
        x = 0.14 + i * 0.27
        if pct:
            g.blk(x, 0.08, x + 0.19, 0.92, False)      # 滿格＝100%
        g.blk(x, 0.92 - h * 0.84, x + 0.19, 0.92, True)


def _cells(g: _Pad, equal: bool) -> None:
    # 2×2 的磚。**一樣大** vs **大小不一**（照實鋪：間距決定面積）。
    if equal:
        for x in (0.08, 0.52):
            for y in (0.08, 0.52):
                g.blk(x, y, x + 0.40, y + 0.40, True)
        return
    g.blk(0.08, 0.08, 0.46, 0.38, True)
    g.blk(0.58, 0.08, 0.92, 0.52, True)
    g.blk(0.08, 0.50, 0.46, 0.92, True)
    g.blk(0.58, 0.64, 0.92, 0.92, True)


def _cell_values(g: _Pad, values: bool) -> None:
    # 2×2 的磚（淡的，因為磚不是這一排在問的事）；**格子裡有沒有字**才是。
    for x in (0.08, 0.52):
        for y in (0.08, 0.52):
            g.blk(x, y, x + 0.40, y + 0.40, False)
    if values:
        for x in (0.14, 0.58):
            for y in (0.24, 0.68):
                g.blk(x, y, x + 0.28, y + 0.08, True)


def _mark_dots(g: _Pad) -> None:
    # 四顆散開的空心點 —— **不排成一條線**（排成線就變成折線圖那一顆了）。
    for x, y in ((0.18, 0.70), (0.40, 0.34), (0.62, 0.60), (0.84, 0.20)):
        g.dot(x, y, 0.10, False)


def _mark_line(g: _Pad) -> None:
    # 一條折線，轉折處有點 —— 「照順序連起來」就是這一顆在說的事。
    pts = ((0.12, 0.74), (0.38, 0.40), (0.62, 0.56), (0.88, 0.18))
    for i in range(len(pts) - 1):
        g.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], True, 0.09)
    for x, y in pts:
        g.dot(x, y, 0.07, True)


def _mark_bars(g: _Pad) -> None:
    # 四根從同一條基線長上來的長條 —— **基線要看得見**，那正是長條圖跟其他
    # 兩種的差別（高度是從哪裡量的）。
    for i, top in enumerate((0.52, 0.22, 0.64, 0.36)):
        x = 0.12 + i * 0.21
        g.blk(x, top, x + 0.14, 0.84, True)
    g.line(0.08, 0.86, 0.92, 0.86, True, 0.06)


def _scale_kind(g: _Pad, log: bool) -> None:
    # 一條軸 ＋ 幾個刻度。**線性**是等距，**log** 是愈往上愈密 —— 那正是
    # 那條軸在做的事，而它畫得出來。
    g.line(0.16, 0.10, 0.16, 0.90, True, 0.07)
    stops = ((0.90, 0.70, 0.50, 0.30, 0.10) if not log
             else (0.90, 0.56, 0.36, 0.23, 0.12))
    for y in stops:
        g.line(0.16, y, 0.42, y, True, 0.06)


def _sort_bars(g: _Pad, order: str) -> None:
    # 三根長條。**沒排**是高低不一，**asc** 由矮到高，**desc** 反過來 ——
    # 差別做在形狀，不做在別的地方（同這一排其他圖示）。
    tops = {"asc": (0.62, 0.42, 0.18),
            "desc": (0.18, 0.42, 0.62)}.get(order, (0.44, 0.16, 0.60))
    for i, top in enumerate(tops):
        x = 0.14 + i * 0.26
        g.blk(x, top, x + 0.18, 0.88, True)
    g.line(0.08, 0.90, 0.92, 0.90, True, 0.05)


def _ramp(g: _Pad, rainbow: bool) -> None:
    # 一條色階。**單色**是一路變深的四段；**彩虹**是四段各自跳一次
    # （差別做在「有沒有台階」而不是顏色 —— 這一排圖示只有一種墨色）。
    n = 4
    for i in range(n):
        x = 0.08 + i * (0.84 / n)
        if rainbow:
            # 高低交錯：讀起來是「一段一段跳」，那正是彩虹階的問題。
            top = 0.24 if i % 2 else 0.52
            g.blk(x, top, x + 0.84 / n - 0.03, 0.86, True)
        else:
            # 一路長高：讀起來是「由淺到深」。
            g.blk(x, 0.80 - i * 0.16, x + 0.84 / n - 0.03, 0.86, True)


def _range(g: _Pad, locked: bool) -> None:
    # 一條軸。**auto** 是兩端開口的箭頭；**locked** 是兩端被夾住的短槓。
    g.line(0.10, 0.5, 0.90, 0.5, True, 0.08)
    if locked:
        g.line(0.10, 0.18, 0.10, 0.82, True, 0.10)
        g.line(0.90, 0.18, 0.90, 0.82, True, 0.10)
        return
    g.poly([(0.30, 0.26), (0.08, 0.5), (0.30, 0.74)], True, 0.08)
    g.poly([(0.70, 0.26), (0.92, 0.5), (0.70, 0.74)], True, 0.08)


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
    "op_normalized": _op_normalized,
    "op_over_sigma": _op_over_sigma,
    "sign_abs": _sign_abs,
    "sign_signed": _sign_signed,
    "sign_split": _sign_split,
    "op_max": _op_max,
    "op_min": _op_min,
    "op_mean": _op_mean,
    "op_trimmed": _op_trimmed,
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
    "news_good": _news_good,
    "news_review": _news_review,
    "news_none": _news_none,
    "pick_centre": lambda g: _pick(g, True),
    "pick_none": lambda g: _pick(g, False),
    "crit_threshold": _crit_threshold,
    "crit_gradient": _crit_gradient,
    "crit_fit": _crit_fit,
    "iqi_pixel": _iqi_pixel,
    "iqi_gradient": _iqi_gradient,
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
    "scale_raw": _scale_raw,
    "scale_z": _scale_z,
    "scale_pct": _scale_pct,
    "cmp_gt": lambda g: _cmp(g, "right", False),
    "cmp_ge": lambda g: _cmp(g, "right", True),
    "cmp_lt": lambda g: _cmp(g, "left", False),
    "cmp_le": lambda g: _cmp(g, "left", True),
    "cmp_eq": lambda g: _cmp(g, "", True),
    "cmp_ne": lambda g: _cmp(g, "both", False),
    "mark_hollow": lambda g: _marker(g, False),
    "mark_solid": lambda g: _marker(g, True),
    "dots_off": lambda g: _dots(g, False),
    "dots_on": lambda g: _dots(g, True),
    "whisk_off": lambda g: _whisk(g, False),
    "whisk_on": lambda g: _whisk(g, True),
    "bars_count": lambda g: _bars(g, False),
    "bars_pct": lambda g: _bars(g, True),
    "cells_equal": lambda g: _cells(g, True),
    "cells_true": lambda g: _cells(g, False),
    "cells_plain": lambda g: _cell_values(g, False),
    "cells_values": lambda g: _cell_values(g, True),
    "range_auto": lambda g: _range(g, False),
    "range_locked": lambda g: _range(g, True),
    "ramp_mono": lambda g: _ramp(g, False),
    "ramp_rainbow": lambda g: _ramp(g, True),
    "mark_dots": _mark_dots,
    "mark_line": _mark_line,
    "mark_bars": _mark_bars,
    "scale_linear": lambda g: _scale_kind(g, False),
    "scale_log": lambda g: _scale_kind(g, True),
    "sort_none": lambda g: _sort_bars(g, ""),
    "sort_asc": lambda g: _sort_bars(g, "asc"),
    "sort_desc": lambda g: _sort_bars(g, "desc"),
    "adc_number": _adc_number,
    "adc_question": _adc_question,
    "adc_tray": _adc_tray,
}
