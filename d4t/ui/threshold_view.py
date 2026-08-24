# d4t Studio — 判定那一刀的兩個看得見的東西（草案 1／2，2026-08-24）。
"""**在挑門檻，就要看得到分布。**

判定面板一直是這樣的：一個數字框、一根沒有刻度的滑桿、底下兩行灰字說「幾顆
說 yes」。使用者拖的時候不知道自己在 60 還是 200 —— 唯一的回饋是那個數字本身，
而那正是「先想好一個數字再輸入」那個反過來的順序（F7-8 對滑桿講過同一句話）。

這一份把那件事補上，兩個元件：

* :class:`ThresholdHistogram` —— 這一步流到的顆在那個數字上的分布，門檻是圖上
  一條**拖得動**的線，兩側染成 yes／no 的顏色。
* :class:`SplitBar` —— 這一刀切出來的兩堆有多大，寬度就是顆數。

為什麼是新模組
--------------
`CLAUDE.md` §4：**一塊新的面板／畫布元件＝一個新模組**。這兩個都是自繪元件，
而 `tree_panel.py` 是接線的地方。

⚠ **資料一律由呼叫端餵，這裡不碰 model。** 兩個元件都只認「一串數字」與
「一個門檻」—— 它們不知道 recipe、不知道樹、也不知道現在編的是哪一步。
那是刻意的：`rows_reaching` 已經把「流到這一步的顆」算出來了，抄第二份判斷
出來的那一份會漂（這個 repo 最怕的形狀）。
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .theme import TOKENS

__all__ = ["SplitBar", "ThresholdHistogram"]

#: 直方圖切幾格。太多會在窄欄裡變成一排毛刺，太少看不出形狀。
#: 24 是「430px 的欄寬下每格還有 15px 以上」與「24 顆的批次仍看得出分布」的折衷。
BINS = 24

#: 圖的高度（px）。夠看出形狀，又不會把面板吃掉 —— 它上面還有三格控制項、
#: 下面還有兩個分支與一列動作。
PLOT_H = 64


def _hex(token: str, fallback: str) -> str:
    return str(TOKENS.get(token, fallback))


def _yes_color() -> QColor:
    """yes 那一側的顏色 —— 跟畫布上分支的顏色同一組（`tree_scene`）。"""
    return QColor(_hex("chip_good_text", "#2f7a52"))


def _no_color() -> QColor:
    return QColor(_hex("text_secondary", "#5b6472"))


class SplitBar(QWidget):
    """這一刀切出來的兩堆：**寬度就是顆數**。

    取代的是兩行講同一件事的灰字（「11 of the 24 … say yes」與
    「24 arrive here → 11 yes · 13 no」隔著 100px 各講一次）。一條有寬度的
    橫條回答的是同一個問題，但它**掃一眼就知道這一刀切得均不均** ——
    而那正是調門檻的人真正在看的東西。

    ``yes`` / ``no`` 是顆數。兩個都是 0（還沒跑過）→ 什麼都不畫（F18：
    不顯示 0，一個「0 of 0」比沒有更糟）。
    """

    #: 條的高度。跟一行文字差不多 —— 它是在取代一行文字。
    HEIGHT = 22

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._yes = 0
        self._no = 0
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_counts(self, yes: int, no: int) -> None:
        self._yes, self._no = max(0, int(yes)), max(0, int(no))
        self.setVisible(bool(self._yes or self._no))
        self.update()

    def counts(self) -> Tuple[int, int]:
        return self._yes, self._no

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt
        total = self._yes + self._no
        if total <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        wy = w * (self._yes / float(total))

        p.setPen(Qt.NoPen)
        p.setBrush(_yes_color())
        p.drawRect(QRectF(0, 0, wy, h))
        p.setBrush(_no_color())
        p.drawRect(QRectF(wy, 0, w - wy, h))

        # 數字寫在自己那一段裡面。塞不下就不寫 —— 一個被切一半的數字
        # 比沒有數字更糟（F19 學到的那一條）。
        font = p.font()
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.5))
        p.setFont(font)
        p.setPen(QPen(QColor("#ffffff")))
        for x0, width, n in ((0.0, wy, self._yes), (wy, w - wy, self._no)):
            if n <= 0:
                continue
            box = QRectF(x0 + 7, 0, max(0.0, width - 10), h)
            if box.width() >= p.fontMetrics().horizontalAdvance(str(n)):
                p.drawText(box, Qt.AlignVCenter | Qt.AlignLeft, str(n))
        p.end()


class ThresholdHistogram(QWidget):
    """這一步流到的顆在某個數字上的分布，門檻是一條**拖得動**的線。

    * 門檻左右染成 no／yes（或反過來，看運算子的方向）；
    * 兩端寫出實際的最小／最大值 —— 使用者拖的時候要知道自己在哪個量級；
    * 門檻的位置寫在線上，而且**跟數字框是同一個值**（拖圖就是改那一格）。

    ⚠ **門檻可以被拖出資料的範圍**，而那是刻意的。`_slider_range` 的說明講過
    同一件事：「大於 12」在這批最大只有 9 的時候仍然是一條完全合法的規則
    —— 那正是怎麼寫一條今天抓不到、明天出事才抓得到的規則。所以圖的橫軸會
    在門檻跑出去的時候跟著撐開，而不是把門檻夾回來。
    """

    #: 使用者拖動門檻（回傳新的值）。
    threshold_changed = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._values: List[float] = []
        self._threshold = 0.0
        self._above_is_yes = True
        self._dragging = False
        self.setFixedHeight(PLOT_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.SizeHorCursor)
        self.setMouseTracking(True)

    # ---- 資料 --------------------------------------------------------------
    def set_data(self, values: Sequence[float], threshold: float,
                 above_is_yes: bool = True) -> None:
        """``values`` 是流到這一步的那些顆在這個數字上的值。

        空的（沒跑過、或那個數字這一批沒有）→ 整個元件藏起來，呼叫端會改為
        說一句「跑一次試跑就會有分布」。**不要畫一張空圖** —— 一張沒有資料的
        分布圖看起來跟「這批真的什麼都沒有」一模一樣。
        """
        self._values = [float(v) for v in values
                        if isinstance(v, (int, float))]
        self._threshold = float(threshold)
        self._above_is_yes = bool(above_is_yes)
        self.setVisible(len(self._values) >= 1)
        self.update()

    def set_threshold(self, value: float) -> None:
        """數字框動了 → 線跟著走（不發訊號，避免兩邊互相回彈）。"""
        self._threshold = float(value)
        self.update()

    def span(self) -> Optional[Tuple[float, float]]:
        """橫軸的範圍（含門檻）。沒有資料回 ``None``。"""
        if not self._values:
            return None
        lo, hi = min(self._values), max(self._values)
        if hi <= lo:
            pad = abs(lo) * 0.5 or 1.0
            lo, hi = lo - pad, hi + pad
        else:
            pad = (hi - lo) * 0.06
            lo, hi = lo - pad, hi + pad
        # 門檻拖出資料範圍時撐開橫軸，而不是把門檻夾回來（見類別說明）。
        return min(lo, self._threshold), max(hi, self._threshold)

    # ---- 座標 --------------------------------------------------------------
    def _x_of(self, value: float) -> float:
        rng = self.span()
        if rng is None or rng[1] <= rng[0]:
            return 0.0
        return (value - rng[0]) / (rng[1] - rng[0]) * float(self.width())

    def _value_at(self, x: float) -> float:
        rng = self.span()
        if rng is None or self.width() <= 0:
            return self._threshold
        frac = min(1.0, max(0.0, float(x) / float(self.width())))
        return rng[0] + frac * (rng[1] - rng[0])

    # ---- 互動 --------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt
        if event.button() == Qt.LeftButton and self._values:
            self._dragging = True
            self._emit_at(event.position().x())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 — Qt
        if self._dragging:
            self._emit_at(event.position().x())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt
        self._dragging = False

    def _emit_at(self, x: float) -> None:
        value = self._value_at(x)
        self._threshold = value
        self.update()
        self.threshold_changed.emit(value)

    # ---- 畫 ----------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 — Qt
        rng = self.span()
        if rng is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        axis_y = h - 12.0

        counts = [0] * BINS
        lo, hi = rng
        width = (hi - lo) or 1.0
        for v in self._values:
            k = int((v - lo) / width * BINS)
            counts[min(BINS - 1, max(0, k))] += 1
        peak = max(counts) or 1

        xt = self._x_of(self._threshold)
        col_w = w / BINS
        p.setPen(Qt.NoPen)
        for i, n in enumerate(counts):
            if n <= 0:
                continue
            x0 = i * col_w
            centre = lo + (i + 0.5) * width / BINS
            is_yes = (centre > self._threshold) if self._above_is_yes \
                else (centre < self._threshold)
            colour = _yes_color() if is_yes else _no_color()
            colour.setAlpha(210 if is_yes else 120)
            bar_h = (n / float(peak)) * (axis_y - 4.0)
            p.setBrush(colour)
            p.drawRect(QRectF(x0 + 1.0, axis_y - bar_h, max(1.0, col_w - 2.0),
                              bar_h))

        p.setPen(QPen(QColor(_hex("border_default", "#e3e6eb")), 1))
        p.drawLine(QPointF(0, axis_y), QPointF(w, axis_y))

        # 門檻：一條線 ＋ 一個抓得住的把手。
        accent = QColor(_hex("accent", "#3574d6"))
        p.setPen(QPen(accent, 2))
        p.drawLine(QPointF(xt, 0), QPointF(xt, axis_y))
        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        handle = QPainterPath()
        handle.addEllipse(QPointF(xt, 5.0), 4.5, 4.5)
        p.drawPath(handle)

        font = p.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2.0))
        p.setFont(font)
        p.setPen(QPen(QColor(_hex("text_secondary", "#5b6472"))))
        p.drawText(QRectF(0, axis_y, w * 0.4, 12),
                   Qt.AlignLeft | Qt.AlignVCenter, _fmt(lo))
        p.drawText(QRectF(w * 0.6, axis_y, w * 0.4, 12),
                   Qt.AlignRight | Qt.AlignVCenter, _fmt(hi))
        p.end()


def _fmt(value: float) -> str:
    """軸上的數字：短到讀得完，又不騙人。"""
    v = float(value)
    if abs(v) >= 1000 or (v and abs(v) < 0.01):
        return "%.3g" % v
    return ("%.0f" % v) if abs(v) >= 100 else ("%.1f" % v)
