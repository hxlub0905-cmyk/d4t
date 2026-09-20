# 分數分佈那張圖 — 從 widgets.py 搬出來 2026-09-08 (U7).
"""``HistogramWidget`` —— 分數分佈長條圖 ＋ 可拖曳的門檻線 ＋ 可點擊的長條。

**秒回是它的立身條件**：拖曳時持續發 ``threshold_changed``（上層用
`viewmodel.rebin` 只重算 bin 數，不重跑影像），放開才發
``threshold_committed``（那時候才寫回 model）。使用者是一邊拖一邊看分佈決定
門檻的，中間卡一下那條線就不能用了。

U7 那一刀。這一份是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme
from .feature_text import _fmt_number
from .theme import TOKENS

__all__ = ["HistogramWidget"]





# --------------------------------------------------------------------------- #
# 5. HistogramWidget
# --------------------------------------------------------------------------- #
class HistogramWidget(QWidget):
    """分數分佈長條圖 + 可拖曳的門檻線 + 可點擊的長條。

    資料來自 ``viewmodel.histogram(scores)``（edges 有 n+1 個、counts 有 n 個）。
    拖曳時持續發 ``threshold_changed``（上層用 ``viewmodel.rebin`` 秒回 bin 數），
    放開才發 ``threshold_committed``（上層才把值寫回 model / 重算）。

    「點一根長條」與「拖門檻」怎麼分（別改成用計時器）
    ------------------------------------------------
    兩件事都從同一顆左鍵 press 開始，所以**在放開的那一刻**才決定它是哪一種：

    ===========================================  ==========================
    放開時的狀況                                  結果
    ===========================================  ==========================
    滑鼠移動 > :data:`_CLICK_SLOP` px             拖門檻 → ``threshold_committed``
    press 落在門檻線 ±:data:`_HANDLE_PX` px 內    拖門檻（原地放開 = 重新確認門檻）
    以上皆非，且點在某根長條上                     ``bar_clicked(lo, hi)``，
                                                  **門檻退回按下去之前的值**
    ===========================================  ==========================

    最後一種情況會補發一次 ``threshold_changed(舊值)``，讓上層拖曳中的即時
    bin 摘要跟著還原 —— 點長條**不會**動到門檻，也不會發 committed。
    """

    threshold_changed = Signal(float)
    threshold_committed = Signal(float)

    #: 橫軸切幾格（＝畫 ``X_TICKS + 1`` 個刻度）。F117 E4：以前只有兩端，
    #: 而「門檻該設哪」是一個位置的問題 —— 兩個端點答不出「這一堆落在哪」。
    X_TICKS = 4
    #: 點一根長條：``(lo, hi)`` 是那根長條的分數區間（Studio 用來篩 Gallery）。
    bar_clicked = Signal(float, float)

    _EMPTY_TEXT = "(Score distribution appears after a trial run)"
    # 上緣留 20px 給門檻線的標籤（「門檻 3.5」畫在圖面之上，不壓到長條）
    _M_LEFT, _M_RIGHT, _M_TOP, _M_BOTTOM = 46.0, 14.0, 20.0, 30.0
    _SUMMARY_H = 18.0
    #: 按下點與門檻線的距離在這個範圍內 → 視為抓著門檻把手，不是點長條。
    _HANDLE_PX = 6.0
    #: 按下到放開的水平位移超過這個值 → 視為拖曳，不是點擊。
    _CLICK_SLOP = 3.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._edges: List[float] = []
        self._counts: List[int] = []
        #: 每根長條的 ``[(顏色, 顆數), …]``（見 `set_segments`）；None = 單色。
        self._segments: Optional[List[List[Any]]] = None
        self._threshold: Optional[float] = None
        #: 判定樹在這個數字上切過的那幾刀（F117 E4）。見 `set_cuts`。
        self._cuts: List[Any] = []
        self._bin_text = ""
        self._dragging = False
        self._hover_bin = -1
        # 點擊 vs 拖曳的判定用（見 class docstring）
        self._press_x: Optional[float] = None
        self._press_threshold: Optional[float] = None
        self._press_on_handle = False
        self._moved = False
        self._marker: Optional[float] = None
        self._marker_label = ""
        self._interactive = True
        self._empty_text = self._EMPTY_TEXT

    # -- public API --------------------------------------------------------
    def set_segments(self, segments: Optional[Sequence[Sequence[Any]]]) -> None:
        """每一根長條**照類別分段染色**（R2 第二半，2026-08-24）。

        ``segments[i]`` 是第 i 根長條的 ``[(顏色, 顆數), …]``，由下往上疊；
        傳 ``None`` 回到單色。

        為什麼值得這樣畫：這張圖回答的問題是「這個數字分不分得開」，而
        **分得開誰**才是使用者真正在問的 —— 一根單色的長條答不出「這一段裡
        是哪一類」。染色之後兩座駝峰各是什麼顏色，一眼就是答案。

        ⚠ 分段的總和**不必**等於 ``counts``：算不出這個數字的那幾顆不會出現在
        任何一段裡（F19：算不出來的那一格不寫），而長條的高度仍然照 ``counts``
        —— 差額畫成中性色，那才是誠實的（「這一段裡有幾顆我說不出是哪一類」）。
        """
        self._segments = None if segments is None else [
            [(str(c), int(n)) for c, n in (seg or [])] for seg in segments]
        self.update()

    def segments(self) -> Optional[List[List[Any]]]:
        return None if self._segments is None else [list(x) for x in self._segments]

    def set_data(self, edges: Sequence[float], counts: Sequence[int]) -> None:
        """``edges`` / ``counts`` 直接吃 ``viewmodel.histogram()`` 的回傳值。"""
        edges = [float(e) for e in (edges or [])]
        counts = [int(c) for c in (counts or [])]
        if len(edges) != len(counts) + 1 or not counts:
            edges, counts = [], []
        self._edges, self._counts = edges, counts
        self._segments = None       # 新資料 = 舊的分段一定不再對得上
        if self._threshold is not None:
            self._threshold = self._clamp(self._threshold)
        self.update()

    def set_cuts(self, cuts: Optional[Sequence[Sequence[Any]]]) -> None:
        """判定樹**在這個數字上切過的那幾刀**（F117 E4）。

        ``[(值, "glv_max > 42"), …]``；``None`` / 空 = 一刀都不畫。

        為什麼值得畫：這張圖回答的是「這個特徵分不分得開、門檻該設哪」，
        而判定樹上**已經有一個答案**了 —— 看不到它的話，使用者是在一張沒有
        參考線的圖上重新猜一次。

        ⚠ **跟 `set_threshold` 是兩件事**：門檻是二元那條**拖得動**的線，
        這幾刀是樹上的，唯讀（要改要去樹上改）。所以它們長得不一樣：門檻是
        粗虛線，這幾刀是細的點線。
        """
        self._cuts = [(float(v), str(t or "")) for v, t in (cuts or [])]
        self.update()

    def cuts(self) -> List[Any]:
        return list(self._cuts)

    def set_marker(self, value: Optional[float], label: str = "") -> None:
        """畫一條**不能拖**的標記線（F18：「這一顆落在哪裡」）。

        跟門檻線刻意長得不一樣（虛線、另一個顏色）：一條看起來能拖、拖了卻
        什麼都不會發生的線，比沒有線更糟。
        """
        try:
            self._marker = None if value is None else float(value)
        except (TypeError, ValueError):
            self._marker = None
        self._marker_label = str(label or "")
        self.update()

    def marker(self) -> Optional[float]:
        return self._marker

    def set_interactive(self, on: bool) -> None:
        """門檻線拖不拖得動。

        看「分數」以外的特徵時是 ``False`` —— 門檻是**分數**的門檻，在別的
        特徵上拖它會寫回一個跟畫面無關的值。那種互動是這個 repo 反覆在避免的
        「跑得完、有反應、而且是錯的」。
        """
        self._interactive = bool(on)
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def is_interactive(self) -> bool:
        return self._interactive

    def set_empty_text(self, text: str) -> None:
        self._empty_text = str(text or self._EMPTY_TEXT)
        self.update()

    def set_threshold(self, value: Optional[float]) -> None:
        """設定門檻線位置（不發訊號；程式設定不應該回頭觸發自己）。"""
        self._threshold = None if value is None else self._clamp(float(value))
        self.update()

    def threshold(self) -> Optional[float]:
        return self._threshold

    def set_bin_summary(self, bins: Optional[Dict[int, int]],
                        extra: str = "") -> None:
        """``{0: 812, 1: 96}`` -> 「bin 0=812   bin 1=96」。

        ``extra`` 接在後面（Phase 1：有 ground truth 時的正確率／抓漏／誤殺）。
        它跟 bin 數同一行，因為使用者是**同時**在看這兩件事：拖門檻線的時候，
        「幾顆進了哪一邊」與「這樣判準不準」要一起變，分成兩處就得來回看。
        """
        parts = []
        if bins:
            parts.append("   ".join("bin %s=%s" % (k, bins[k])
                                    for k in sorted(bins)))
        if str(extra or "").strip():
            parts.append(str(extra).strip())
        self._bin_text = "      ".join(parts)
        self.update()

    def bin_summary_text(self) -> str:
        return self._bin_text

    def has_data(self) -> bool:
        return bool(self._counts) and sum(self._counts) > 0

    def bar_range(self, index: int) -> Optional[Tuple[float, float]]:
        """第 ``index`` 根長條的分數區間 ``(lo, hi)``；超出範圍回 None。"""
        i = int(index)
        if not self._counts or not (0 <= i < len(self._counts)):
            return None
        return (float(self._edges[i]), float(self._edges[i + 1]))

    # -- geometry ----------------------------------------------------------
    def _plot_rect(self) -> QRectF:
        extra = self._SUMMARY_H if self._bin_text else 0.0
        w = max(20.0, self.width() - self._M_LEFT - self._M_RIGHT)
        h = max(20.0, self.height() - self._M_TOP - self._M_BOTTOM - extra)
        return QRectF(self._M_LEFT, self._M_TOP, w, h)

    def _span(self) -> Tuple[float, float]:
        if not self._edges:
            return 0.0, 1.0
        lo, hi = self._edges[0], self._edges[-1]
        return (lo, hi if hi > lo else lo + 1.0)

    def _x_at(self, value: float) -> float:
        lo, hi = self._span()
        r = self._plot_rect()
        return r.left() + (float(value) - lo) / (hi - lo) * r.width()

    def _value_at(self, x: float) -> float:
        lo, hi = self._span()
        r = self._plot_rect()
        t = 0.0 if r.width() <= 0 else (float(x) - r.left()) / r.width()
        return self._clamp(lo + t * (hi - lo))

    def _clamp(self, v: float) -> float:
        lo, hi = self._span()
        if not self._edges:
            return float(v)
        return float(min(max(v, lo), hi))

    def _bar_at(self, x: float) -> int:
        if not self._counts:
            return -1
        r = self._plot_rect()
        if x < r.left() or x > r.right():
            return -1
        n = len(self._counts)
        i = int((x - r.left()) / max(1e-9, r.width()) * n)
        return int(min(max(i, 0), n - 1))

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        p.setBrush(QColor(TOKENS["bg_panel"]))
        p.drawRoundedRect(frame, 7, 7)

        if not self.has_data():
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(self.rect(), Qt.AlignCenter, self._empty_text)
            p.end()
            return

        r = self._plot_rect()
        small = QFont(p.font())
        small.setPixelSize(theme.font_px("font_tiny"))
        p.setFont(small)

        # 座標軸（低調的細線）
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))
        p.drawLine(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom()))

        ymax = max(self._counts) or 1
        n = len(self._counts)
        bw = r.width() / n
        bar = QColor(theme.seg_hex("algo"))
        hover = QColor(TOKENS["accent_active"])
        p.setPen(Qt.NoPen)
        for i, c in enumerate(self._counts):
            if c <= 0:
                continue
            bh = c / float(ymax) * r.height()
            x = r.left() + i * bw
            w = max(1.0, bw - 1.0)
            segs = (self._segments[i]
                    if self._segments is not None and i < len(self._segments)
                    else None)
            if not segs or i == self._hover_bin:
                # 滑鼠指著的那一根整根反白 —— 那一刻使用者問的是「這一根是
                # 哪個區間、幾顆」，不是「裡面有幾類」。
                p.setBrush(hover if i == self._hover_bin else bar)
                p.drawRect(QRectF(x + 0.5, r.bottom() - bh, w, bh))
                continue
            # 由下往上疊。分段加起來少於 c 的那個差額留在最上面畫成中性色 ——
            # 它是「這一段裡有幾顆我說不出是哪一類」，不該假裝屬於某一類。
            y = r.bottom()
            for colour, n in list(segs) + [
                    (TOKENS["seg_disabled"], c - sum(n for _c, n in segs))]:
                if n <= 0:
                    continue
                h = n / float(ymax) * r.height()
                p.setBrush(QColor(colour))
                p.drawRect(QRectF(x + 0.5, y - h, w, h))
                y -= h

        # 刻度文字
        lo, hi = self._span()
        p.setPen(QColor(TOKENS["text_hint"]))
        p.drawText(QRectF(r.left() - self._M_LEFT + 2, r.top() - 6,
                          self._M_LEFT - 6, 14),
                   Qt.AlignRight | Qt.AlignVCenter, str(ymax))
        p.drawText(QRectF(r.left() - self._M_LEFT + 2, r.bottom() - 7,
                          self._M_LEFT - 6, 14),
                   Qt.AlignRight | Qt.AlignVCenter, "0")
        # ⚠ **只有兩端的刻度讀不出中間**（F117 E4）：使用者要問的是
        # 「門檻該設哪」，而那是一個**位置**的問題 —— 兩個端點答不出「這一堆
        # 大概落在哪」。五格（四個內點）是量過的折衷：再多就開始互相擠。
        for i in range(self.X_TICKS + 1):
            frac = i / float(self.X_TICKS)
            value = lo + (hi - lo) * frac
            x = r.left() + r.width() * frac
            p.setPen(QColor(TOKENS["border_default"]))
            p.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() + 3))
            p.setPen(QColor(TOKENS["text_hint"]))
            # 兩端靠邊、中間置中 —— 不然第一個與最後一個會被畫出格子外。
            box = QRectF(x - 30, r.bottom() + 2, 60, 14)
            align = (Qt.AlignLeft if i == 0 else
                     Qt.AlignRight if i == self.X_TICKS else Qt.AlignHCenter)
            if i == 0:
                box = QRectF(r.left(), r.bottom() + 2, 60, 14)
            elif i == self.X_TICKS:
                box = QRectF(r.right() - 60, r.bottom() + 2, 60, 14)
            p.drawText(box, align | Qt.AlignVCenter, "%.3g" % value)

        # 判定樹切過的那幾刀（F117 E4）—— **畫在門檻線之前**：能拖的那條
        # 要在最上面（同下面標記線那一段的理由）。
        for value, text in self._cuts:
            if not (lo <= value <= hi):
                continue          # 切在圖外：畫在邊上會讓人以為就切在那裡
            cx = self._x_at(value)
            pen = QPen(QColor(TOKENS["text_hint"]), 1)
            pen.setStyle(Qt.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(cx, r.top()), QPointF(cx, r.bottom()))
            if text:
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(text) + 4
                tx = min(max(cx + 3, r.left()),
                         max(r.left(), r.right() - tw))
                p.setPen(QColor(TOKENS["text_hint"]))
                p.drawText(QRectF(tx, r.bottom() + 15, tw, 14),
                           Qt.AlignLeft | Qt.AlignVCenter, text)

        # 門檻線
        if self._threshold is not None:
            x = self._x_at(self._threshold)
            pen = QPen(QColor(TOKENS["accent_active"]), 2)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(x, r.top() - 3), QPointF(x, r.bottom() + 3))
            p.setPen(QColor(TOKENS["accent_active"]))
            label = "threshold %s" % _fmt_number(self._threshold)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label) + 4
            tx = min(max(x + 3, r.left()), max(r.left(), r.right() - tw))
            p.drawText(QRectF(tx, r.top() - self._M_TOP + 2, tw,
                              self._M_TOP - 4),
                       Qt.AlignLeft | Qt.AlignVCenter, label)

        # 「這一顆在哪裡」的標記線（F18）。虛線 + 另一個顏色，而且**畫在
        # 門檻線之後** —— 兩條同時在的時候，能拖的那條要在上面。
        if self._marker is not None:
            mx = self._x_at(self._marker)
            p.setPen(QPen(QColor(TOKENS["danger_text"]), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(mx, r.top() - 3), QPointF(mx, r.bottom() + 3))
            if self._marker_label:
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(self._marker_label) + 4
                tx = min(max(mx + 3, r.left()), max(r.left(), r.right() - tw))
                p.setPen(QColor(TOKENS["danger_text"]))
                p.drawText(QRectF(tx, r.top() - self._M_TOP + 2, tw,
                                  self._M_TOP - 4),
                           Qt.AlignLeft | Qt.AlignVCenter, self._marker_label)

        # bin 摘要
        if self._bin_text:
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(r.left(), r.bottom() + 16, r.width(),
                              self._SUMMARY_H),
                       Qt.AlignLeft | Qt.AlignVCenter, self._bin_text)
        p.end()

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # Qt hook
        if e.button() != Qt.LeftButton or not self.has_data():
            return
        if not self._interactive:
            # 看別的特徵時整張圖是唯讀的：門檻是**分數**的門檻（見
            # `set_interactive`）。點長條篩 Gallery 也一起關掉 —— 那個篩選
            # 用的是分數區間。
            return
        pos = QPointF(e.position())
        if not self._plot_rect().adjusted(-6, -6, 6, 6).contains(pos):
            return
        self._dragging = True
        self._press_x = float(pos.x())
        self._press_threshold = self._threshold
        self._press_on_handle = (
            self._threshold is not None
            and abs(pos.x() - self._x_at(self._threshold)) <= self._HANDLE_PX)
        self._moved = False
        self._set_from_mouse(pos.x())
        e.accept()

    def mouseMoveEvent(self, e) -> None:  # Qt hook
        if not self._interactive:
            return
        pos = QPointF(e.position())
        if self._dragging:
            if (self._press_x is not None
                    and abs(pos.x() - self._press_x) > self._CLICK_SLOP):
                self._moved = True
            self._set_from_mouse(pos.x())
            return
        self._update_hover(pos)

    def mouseReleaseEvent(self, e) -> None:  # Qt hook
        if not self._dragging:
            return
        self._dragging = False
        idx = -1 if self._press_x is None else self._bar_at(self._press_x)
        rng = self.bar_range(idx)
        if not self._moved and not self._press_on_handle and rng is not None:
            self._restore_press_threshold()
            self.bar_clicked.emit(float(rng[0]), float(rng[1]))
            return
        if self._threshold is not None:
            self.threshold_committed.emit(float(self._threshold))

    def _restore_press_threshold(self) -> None:
        """點長條：門檻退回按下去之前的值（並補一次 changed 讓上層還原顯示）。"""
        old = self._press_threshold
        self._threshold = None if old is None else self._clamp(float(old))
        self.update()
        if self._threshold is not None:
            self.threshold_changed.emit(float(self._threshold))

    def leaveEvent(self, _e) -> None:  # Qt hook
        if self._hover_bin != -1:
            self._hover_bin = -1
            self.setToolTip("")
            self.update()

    def _set_from_mouse(self, x: float) -> None:
        value = self._value_at(x)
        if self._threshold is None or value != self._threshold:
            self._threshold = value
            self.update()
        self.threshold_changed.emit(float(value))

    def _update_hover(self, pos: QPointF) -> None:
        idx = -1
        if self.has_data() and self._plot_rect().contains(pos):
            idx = self._bar_at(pos.x())
        if idx == self._hover_bin:
            return
        self._hover_bin = idx
        if idx < 0:
            self.setToolTip("")
        else:
            a, b = self._edges[idx], self._edges[idx + 1]
            self.setToolTip("score %.3g–%.3g: %d defects"
                            % (a, b, self._counts[idx]))
        self.update()
