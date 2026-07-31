# ADEPT Studio — 每張卡自己的儀表 (F7-17).
"""選一張卡，右下角就換成**那張卡的儀表**。

為什麼不是一塊通用面板
----------------------
右下角本來是一張「特徵 / 數值」表：`blob_dist_center 11.170`、`blob_snr 255`。
問題不是它佔位子，是**那些數字沒有辦法判讀** —— 11.17 是大還是小？255 是不是
飽和了？一個數字單獨存在，回答不了使用者真正在問的問題。

而使用者在問的問題**每張卡都不一樣**：調 Align 的時候他要知道「搜尋半徑夠不夠
大」，調 Denoise 的時候他要知道「我有沒有把訊號一起磨掉」。同一塊面板放同一種
東西，對兩者都答非所問。

挑選原則
--------
面板不高（約 200 px），所以每張卡**只放一件事**。挑的標準是：

    這張卡最常見的失敗模式是什麼，而那個失敗**在單顆畫面上看不出來**。

看得出來的（影像整個黑掉）不需要面板；看不出來的才需要。Align 就是典型：
每一顆都「有對到啊」，只有把整批的位移畫在一起，才看得出來一半的點貼在搜尋框
的邊上 —— 那些顆根本沒對準，只是被半徑截斷了。

三條約定
--------
1. **依 ``Step.key`` 註冊**（``INSPECTORS``）。沒註冊的卡就用原本的特徵表，
   所以加一張新卡不必動這個檔案 —— 維持「import 就出現」那條規則。
2. **畫的是引擎算出來的那一份**。要嘛來自 ``ctx.meta``（step 卡自己放進去的，
   同 ``roi_profile``），要嘛來自 ``trial_results``（跑完的整批結果）。
   UI 不自己重算一次 —— 不然畫面上的東西跟真的跑出來的有機會不一樣。
3. **沒有資料時說得出「為什麼沒有」**，而不是一片空白。最常見的原因是
   「還沒跑過」，那句話要直接寫在面板上。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from .theme import TOKENS

__all__ = ["Inspector", "AlignInspector", "EnhanceInspector",
           "MeasureInspector", "InputInspector",
           "ProfileInspector", "TemplateInspector",
           "INSPECTORS", "inspector_for"]


class Inspector(QWidget):
    """卡片儀表的共同介面。

    ``set_context()`` 一次餵齊三種來源：這張卡的參數、**這一顆**的結果、
    以及**整批**的結果。子類自己決定要用哪些 —— 但不准自己去跑 pipeline。
    """

    #: 面板標題（顯示在切換列上）。
    title = "Card"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.params: Dict[str, Any] = {}
        self.result: Dict[str, Any] = {}
        self.batch: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {}
        self.feature_names: List[str] = []
        self.shown_streams: List[str] = []
        self.node_id = ""
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_context(self, node_id: str, params: Optional[Dict[str, Any]] = None,
                    result: Optional[Dict[str, Any]] = None,
                    batch: Optional[Sequence[Dict[str, Any]]] = None,
                    meta: Optional[Dict[str, Any]] = None,
                    feature_names: Optional[Sequence[str]] = None,
                    shown_streams: Optional[Sequence[str]] = None) -> None:
        self.node_id = str(node_id or "")
        self.params = dict(params or {})
        self.result = dict(result or {})
        self.batch = [dict(r) for r in (batch or [])]
        self.meta = dict(meta or {})
        #: 預覽區**現在正在看**哪幾條流（並排比對打開時是左右那兩條）。
        #: 儀表要跟著畫面走：畫面上兩張圖，底下就該是兩張直方圖。
        self.shown_streams = [str(s) for s in (shown_streams or []) if s]
        #: 這張卡**自己**產出哪些特徵（含 output_prefix）。解析要用卡片庫，
        #: 那是 Studio 的事 —— 儀表只負責畫。
        self.feature_names = [str(f) for f in (feature_names or [])]
        self.update()

    # -- 子類覆寫 -----------------------------------------------------------
    def summary(self) -> str:
        """一行文字摘要。**測試與狀態列讀這個**，不去讀畫素。"""
        return ""

    def has_data(self) -> bool:
        return False

    def empty_reason(self) -> str:
        """沒有資料時要說的話 —— 空白面板本身不是訊息。"""
        return "Run a trial to fill this in."

    # -- 共用小工具 ---------------------------------------------------------
    def feature_values(self, name: str) -> List[float]:
        """整批裡某個特徵的值（跳過失敗與缺值的顆）。"""
        out: List[float] = []
        for r in self.batch:
            v = (r.get("features") or {}).get(name)
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if not (math.isnan(f) or math.isinf(f)):
                out.append(f)
        return out

    def this_value(self, name: str) -> Optional[float]:
        v = (self.result.get("features") or {}).get(name)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if (math.isnan(f) or math.isinf(f)) else f

    def _frame(self, p: QPainter) -> QRectF:
        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(QRectF(self.rect()), QColor(TOKENS["bg_surface"]))
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.drawRoundedRect(rect, 4, 4)
        return rect.adjusted(8, 8, -8, -8)

    def _say_empty(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QColor(TOKENS["text_disabled"]))
        p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, self.empty_reason())

    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        p = QPainter(self)
        rect = self._frame(p)
        if not self.has_data():
            self._say_empty(p, rect)
        else:
            self.paint_body(p, rect)
        p.end()

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        """子類畫這裡（``rect`` 已經扣掉外框與留白）。"""


class AlignInspector(Inspector):
    """Align：**整批的位移散佈圖**，加上搜尋半徑的方框。

    為什麼是這一張圖
    ----------------
    對位失敗在單顆上看不出來 —— 每一顆都「有對到啊」，因為演算法一定會回一個
    位移。真正的失敗是**位移被搜尋半徑截斷**：真實偏移 12 px、半徑設 8，
    那顆回報 8，而 8 是一個看起來完全正常的數字。

    把整批畫在一起，這件事變成一眼可見：**點貼在方框的邊上**。而且它是可以照做
    的 —— 把 Search radius 調大再跑一次就好。

    資料來自 ``trial_results`` 的 ``align_dx`` / ``align_dy``（引擎算的），
    方框來自這張卡的 ``search_radius`` 參數。UI 不自己算對位。
    """

    title = "Alignment"

    #: 距離邊界多近算「貼在邊上」（像素）。次像素對位會落在 7.9 這種值上，
    #: 用嚴格相等會什麼都抓不到。
    _EDGE_TOL = 0.75

    def radius(self) -> float:
        try:
            return float(self.params.get("search_radius", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def points(self) -> List[Tuple[float, float]]:
        xs = self.feature_values("align_dx")
        ys = self.feature_values("align_dy")
        n = min(len(xs), len(ys))
        return list(zip(xs[:n], ys[:n]))

    def at_the_limit(self) -> int:
        """有幾顆的位移貼在搜尋框的邊上（= 很可能根本沒對準）。"""
        r = self.radius()
        if r <= 0:
            return 0
        edge = r - self._EDGE_TOL
        return sum(1 for x, y in self.points()
                   if abs(x) >= edge or abs(y) >= edge)

    def has_data(self) -> bool:
        return bool(self.points())

    def empty_reason(self) -> str:
        return ("Run a trial to see how far every defect had to move to line "
                "up. One defect cannot tell you whether the search radius is "
                "big enough — the whole batch can.")

    def summary(self) -> str:
        pts = self.points()
        if not pts:
            return ""
        r = self.radius()
        far = max(max(abs(x), abs(y)) for x, y in pts)
        text = ("%d defects · largest shift %.1f px · search radius %.0f px"
                % (len(pts), far, r))
        stuck = self.at_the_limit()
        if stuck:
            text += ("  ⚠ %d of them sit on the search limit — those did not "
                     "really line up, they ran out of room. Raise “Search "
                     "radius” and run again." % stuck)
        return text

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
        pts = self.points()
        r = max(self.radius(), max((max(abs(x), abs(y)) for x, y in pts),
                                   default=1.0), 1.0)
        span = r * 1.15
        # 正方形，而且**置中** —— dx 與 dy 必須同一個尺度（不然圓形的散佈看起來
        # 像橢圓，使用者會以為某一軸偏得比較多），但靠左擺會讓十字跑到面板左邊。
        side = min(rect.width(), rect.height())
        plot = QRectF(rect.left() + (rect.width() - side) / 2.0,
                      rect.top() + (rect.height() - side) / 2.0, side, side)
        cx, cy = plot.center().x(), plot.center().y()
        scale = (side / 2.0) / span

        def to_px(dx: float, dy: float) -> QPointF:
            # 螢幕的 y 往下為正，位移的 y 往上為正 —— 不翻的話整張圖上下顛倒，
            # 而使用者是拿它跟影像對照的。
            return QPointF(cx + dx * scale, cy - dy * scale)

        # 十字與搜尋框
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0, Qt.DashLine))
        p.drawLine(QPointF(plot.left(), cy), QPointF(plot.right(), cy))
        p.drawLine(QPointF(cx, plot.top()), QPointF(cx, plot.bottom()))

        rad = self.radius()
        if rad > 0:
            box = QRectF(to_px(-rad, rad), to_px(rad, -rad))
            stuck = self.at_the_limit()
            p.setPen(QPen(QColor(TOKENS["danger_text"] if stuck
                                 else TOKENS["accent"]), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawRect(box)
            # 說明放在方框**下面**：上面那條帶子已經有 dy 的軸標，
            # 兩個東西擠在同一列會疊字（實測疊成一團看不懂）。
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(box.left(), box.bottom() + 1, box.width(), 14),
                       Qt.AlignRight | Qt.AlignVCenter,
                       "search radius %.0f px" % rad)

        # 每一顆一個點；貼在邊上的用警示色（那些才是要看的）
        edge = rad - self._EDGE_TOL if rad > 0 else float("inf")
        normal = QColor(TOKENS["accent"])
        normal.setAlpha(150)
        bad = QColor(TOKENS["danger_text"])
        p.setPen(Qt.NoPen)
        for x, y in pts:
            p.setBrush(QBrush(bad if (abs(x) >= edge or abs(y) >= edge)
                              else normal))
            p.drawEllipse(to_px(x, y), 2.6, 2.6)

        # 目前這一顆：空心大圈，看得出「我在哪」
        tx, ty = self.this_value("align_dx"), self.this_value("align_dy")
        if tx is not None and ty is not None:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.6))
            p.drawEllipse(to_px(tx, ty), 5.0, 5.0)

        # 座標軸要標 —— 不標的話這是一張幾何圖形，不是量測結果。
        # 兩個字都畫水平的：旋轉過的字連箭頭一起轉，「dy ↑」會變成「dy ←」。
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(plot.right() - 60, cy + 2, 58, 13),
                   Qt.AlignRight | Qt.AlignVCenter, "dx (px)")
        p.drawText(QRectF(cx + 4, plot.top(), 60, 13),
                   Qt.AlignLeft | Qt.AlignVCenter, "dy (px)")


class EnhanceInspector(Inspector):
    """Enhance 九張卡共用：**同一條流的 before / after 直方圖 + 削平計數**。

    為什麼是這一張圖
    ----------------
    Enhance 的失敗是安靜的。對比拉大之後「看起來變乾淨了」，但背景被壓成全黑、
    缺陷的邊界也一起被吃掉 —— 而**後面每一張量測卡都吃這個結果**。

    削平（畫素貼在 0 或 255）是唯一能量化「我毀掉了多少」的東西：那些畫素之間的
    差異永遠回不來了。所以這裡除了兩條分布，還直接把「多少 % 被壓到底 / 頂」
    講成一句話。

    資料來自引擎（``ctx.meta['stream_change']``，預覽時才記）—— UI 不自己再套
    一次那些演算法，不然畫面上的曲線跟真的算出來的有機會不一樣。
    """

    title = "Before / after"

    #: 削平多少才值得警告。**不是 0** —— 原圖本來就可能有幾顆全黑的畫素，
    #: 而每次都喊狼來了跟不喊一樣沒有用。實測 1% 以下肉眼看不出差別。
    WARN_CLIP = 0.01

    def stream(self) -> str:
        """這張卡的主要輸出流（也就是要比 before/after 的那一條）。

        F7-20 起 Enhance 卡的參數是 ``streams``（一串，逗號分隔），所以這裡取
        第一條。``target`` / ``source`` 留著是為了舊 recipe 與非 Enhance 的卡。

        ⚠ 一張卡吃兩條流的時候，這個面板目前只畫得出第一條 —— 兩條各一組
        before/after 是 F7-19 畫布那一半的事（計畫書 §23.7）。
        """
        raw = str(self.params.get("streams") or self.params.get("target")
                  or self.params.get("source") or "test")
        first = raw.split(",")[0].strip()
        return first or "test"

    def streams(self) -> List[str]:
        """這張卡處理的每一條流（``streams`` 是逗號分隔的一串）。"""
        raw = str(self.params.get("streams") or self.params.get("target")
                  or self.params.get("source") or "test")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        return keys or ["test"]

    def panes(self) -> List[str]:
        """要畫幾張直方圖、各是哪一條流。

        **跟著預覽畫面走**：並排比對打開時畫面上是兩張圖，底下就該是兩張
        直方圖，而且左右順序一樣 —— 使用者是拿它們互相對照的，順序對不上就
        每次都要重新認一次哪張配哪張。

        只取這張卡真的動過的流：並排的右邊可能是 ``diff``（這張 Enhance 卡沒
        碰過它），那畫一張空的圖只是佔位子。都沒有的話退回這張卡的第一條流。
        """
        changes = dict(self.meta.get("stream_change") or {})
        mine = self.streams()
        if self.shown_streams:
            picked = [s for s in self.shown_streams if s in changes]
            if picked:
                return picked
        return [s for s in mine if s in changes] or mine[:1]

    def record(self, key: Optional[str] = None) -> Dict[str, Any]:
        changes = dict(self.meta.get("stream_change") or {})
        return dict(changes.get(key or self.stream()) or {})

    def has_data(self) -> bool:
        return any(bool(self.record(k).get("before"))
                   and bool(self.record(k).get("after"))
                   for k in self.panes())

    def empty_reason(self) -> str:
        return ("Select a defect to see what this card does to “%s” — the "
                "grey levels before it ran and after." % self.stream())

    def clipped(self, key: Optional[str] = None) -> Tuple[float, float]:
        rec = self.record(key)
        return (float(rec.get("clipped_low", 0.0)),
                float(rec.get("clipped_high", 0.0)))

    def added_clipping(self, key: Optional[str] = None) -> Tuple[float, float]:
        """**這張卡自己**新增的削平（原圖本來就黑掉的部分不算它的帳）。"""
        rec = self.record(key)
        lo = float(rec.get("clipped_low", 0.0)) - float(rec.get("was_clipped_low", 0.0))
        hi = float(rec.get("clipped_high", 0.0)) - float(rec.get("was_clipped_high", 0.0))
        return (max(0.0, lo), max(0.0, hi))

    def summary(self) -> str:
        if not self.has_data():
            return ""
        panes = self.panes()
        bits = []
        worst = 0.0
        for key in panes:
            lo, hi = self.clipped(key)
            bits.append("“%s” %.1f%% at black, %.1f%% at white"
                        % (key, lo * 100.0, hi * 100.0))
            alo, ahi = self.added_clipping(key)
            worst = max(worst, alo, ahi)
        text = " · ".join(bits)
        alo = ahi = worst
        if max(alo, ahi) >= self.WARN_CLIP:
            text += ("  ⚠ this card flattened %.1f%% of the patch onto the "
                     "ends of the scale — those pixels no longer differ from "
                     "each other, and every measure card downstream reads "
                     "them as identical." % (max(alo, ahi) * 100.0))
        return text

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
        panes = self.panes()
        if not panes:
            return
        # 並排比對打開時畫兩張 —— 左右的順序跟畫面上兩張圖一樣。
        gap = 14.0
        w = (rect.width() - gap * (len(panes) - 1)) / float(len(panes))
        for i, key in enumerate(panes):
            box = QRectF(rect.left() + i * (w + gap), rect.top(), w, rect.height())
            self._paint_one(p, box, key, with_axis_title=(i == 0))

    def _paint_one(self, p: QPainter, rect: QRectF, key: str,
                   with_axis_title: bool) -> None:
        """一條流的 before/after 直方圖。

        軸要講得出自己是什麼
        --------------------
        使用者原話：「histogram 我有點看不太懂，橫軸是 GLV 縱軸是 pixel counts？
        細線是什麼？」—— 三個問題，三個都是**畫面上沒寫**。以前只有兩端的
        ``black`` / ``white`` 跟一句 ``outline = before · filled = after``，
        而那句話要先知道 outline 指的是那條細線才讀得懂。

        現在：橫軸寫 ``gray level  0 → 255``、縱軸寫 ``pixels``，圖例直接**畫**
        一小段細線與一小塊實心方塊配上字，不要求使用者把名詞對應到圖形。
        """
        rec = self.record(key)
        head = QRectF(rect.left(), rect.top(), rect.width(), 13)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(head, Qt.AlignLeft | Qt.AlignVCenter, "“%s”" % key)
        if with_axis_title:
            p.drawText(head, Qt.AlignRight | Qt.AlignVCenter, "pixels ↑")

        before = [float(v) for v in rec.get("before") or []]
        after = [float(v) for v in rec.get("after") or []]
        if not before and not after:
            p.drawText(rect, Qt.AlignCenter, "no record for this stream")
            return
        n = max(len(before), len(after))
        # **高度用平方根。** 削平會在兩端堆出兩根極高的柱子（六成的畫素都在那裡），
        # 線性刻度下其餘的分布會被壓成一條貼著底的線 —— 而那正是要比較的形狀。
        # 平方根保住高低順序，又讓中間看得見。
        before = [math.sqrt(v) for v in before]
        after = [math.sqrt(v) for v in after]
        top = max(max(before or [1.0]), max(after or [1.0]), 1.0)

        plot = QRectF(rect.left(), rect.top() + 20,
                      rect.width(), max(20.0, rect.height() - 52))
        bw = plot.width() / float(n)

        def bars(vals: List[float], col: QColor, filled: bool) -> None:
            p.setPen(Qt.NoPen if filled else QPen(col, 1.4))
            p.setBrush(QBrush(col) if filled else Qt.NoBrush)
            path_pts = []
            for i, v in enumerate(vals):
                h = (v / top) * plot.height()
                x = plot.left() + i * bw
                if filled:
                    p.drawRect(QRectF(x, plot.bottom() - h, max(1.0, bw - 0.6), h))
                else:
                    path_pts.append(QPointF(x + bw / 2.0, plot.bottom() - h))
            if not filled and len(path_pts) > 1:
                for a, b in zip(path_pts, path_pts[1:]):
                    p.drawLine(a, b)

        # after 是實心的（那是現在的樣子），before 只畫輪廓 —— 兩個都實心會
        # 疊成一團看不出誰是誰。
        faint = QColor(TOKENS["text_disabled"])
        bar = QColor(TOKENS["accent"])
        bar.setAlpha(170)
        bars(before, faint, False)
        bars(after, bar, True)

        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))

        # 兩端的削平：把貼在 0 / 255 的那一格標成警示色，不然它只是一根高柱子
        lo, hi = self.clipped(key)
        alo, ahi = self.added_clipping(key)
        for frac, added, at_left in ((lo, alo, True), (hi, ahi, False)):
            if frac <= 0.0005:
                continue
            col = QColor(TOKENS["danger_text"] if added >= self.WARN_CLIP
                         else TOKENS["warning"])
            x = plot.left() if at_left else plot.right() - bw
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            p.drawRect(QRectF(x, plot.top() - 6, max(2.0, bw), 4))

        # 橫軸：兩端的 0 / 255 加上中間那句「這是什麼軸」。
        axis = QRectF(rect.left(), plot.bottom() + 1, rect.width(), 13)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(axis, Qt.AlignLeft | Qt.AlignVCenter, "0 black")
        p.drawText(axis, Qt.AlignRight | Qt.AlignVCenter, "white 255")
        p.drawText(axis, Qt.AlignCenter, "gray level")

        # 圖例：**畫**一段細線與一塊實心方塊，不要只寫「outline / filled」——
        # 那要求使用者先把名詞對回圖形，而那正是他卡住的地方。
        self._paint_legend(p, QRectF(rect.left(), axis.bottom() + 1,
                                     rect.width(), 14), faint, bar)

    @staticmethod
    def _paint_legend(p: QPainter, box: QRectF, line_col: QColor,
                      fill_col: QColor) -> None:
        y = box.center().y()
        x = box.left()
        p.setPen(QPen(line_col, 1.4))
        p.drawLine(QPointF(x, y), QPointF(x + 12, y))
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(x + 16, box.top(), 60, box.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, "before")
        x += 74
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill_col))
        p.drawRect(QRectF(x, y - 4, 12, 8))
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(x + 16, box.top(), 60, box.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, "after")


class ProfileInspector(Inspector):
    """`roi_profile`：投影曲線 + 找到的轉折 + 選中的那一段。

    這一塊是 F7-11 就做好的（``widgets.ProfilePanel``），只是當時直接掛在預覽
    面板上 —— 也就是一條**跟儀表機制平行的路**。兩條路並存的下場是：加新面板的
    人不知道該走哪一條，然後兩邊各長一半。所以把它收進來，畫的還是同一個元件。

    「敏感度要調多少」對不會寫 code 的人是沒有答案的問題，除非他看得到曲線、
    看得到目前抓到幾條線、看得到線落在哪 —— 沒有這個面板，那張卡就只是另一個
    要盲填的數字。
    """

    title = "Profile"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        from .widgets import ProfilePanel

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = ProfilePanel(self)
        # 原本掛在預覽面板上時它是**固定高**（那裡的高度是搶來的）。搬進儀表
        # 之後那一格本來就是給它的，不撐開的話曲線只佔下半截、上面一片空白。
        self.panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self.panel)

    def region(self) -> str:
        return str(self.params.get("roi_out") or "")

    def set_context(self, *a, **kw) -> None:   # noqa: D102
        super().set_context(*a, **kw)
        profiles = dict(self.meta.get("profiles") or {})
        name = self.region()
        self.panel.set_data(name, profiles.get(name))

    def has_data(self) -> bool:
        return bool(self.panel.has_data())

    def summary(self) -> str:
        return self.panel.summary()

    def paintEvent(self, _e) -> None:          # noqa: D102 - 內容由子元件畫
        pass


class TemplateInspector(Inspector):
    """`roi_template`：三道閘門各自過了沒，以及這張 patch 對到哪個相位。

    為什麼是這三根柱子
    ------------------
    定位失敗的時候，卡片只講「定不出來，退回整張圖」。但那有三個完全不同的
    原因，而**處置完全不同**：

    * **match 太低** —— 模板不對（或這批圖跟建模板那張差太多）；
    * **certainty 太低** —— 對得上的位置不只一個（週期性太強或門檻太緊）；
    * **structure 太低** —— **這張 patch 上根本沒有東西可比**。這個不是要調
      參數，是本來就該退回整張圖。

    分不出來的話，使用者會一直去調前兩個門檻，而問題其實在第三個。
    """

    title = "Match"

    _GATES = (("match", "score", "min_score", 1.0),
              ("certainty", "margin", "min_margin", 1.0),
              ("structure", "structure", "min_structure", 40.0))

    def record(self) -> Dict[str, Any]:
        templates = dict(self.meta.get("templates") or {})
        name = str(self.params.get("roi_out") or "")
        return dict(templates.get(name) or (
            list(templates.values())[0] if len(templates) == 1 else {}))

    def has_data(self) -> bool:
        return bool(self.record())

    def empty_reason(self) -> str:
        if not str(self.params.get("template") or "").strip():
            return ("No template yet — build one from a full-size image, then "
                    "this panel shows why each defect did or did not match.")
        return "Select a defect to see how well it matched the template."

    def gates(self) -> List[Tuple[str, float, float, bool]]:
        """``(名稱, 量到的值, 門檻, 過了沒)``。"""
        rec = self.record()
        out = []
        for label, key, param, _full in self._GATES:
            got = float(rec.get(key, 0.0) or 0.0)
            need = float(self.params.get(param, 0.0) or 0.0)
            out.append((label, got, need, got >= need))
        return out

    def failing(self) -> List[str]:
        return [g[0] for g in self.gates() if not g[3]]

    def summary(self) -> str:
        rec = self.record()
        if not rec:
            return ""
        if rec.get("ok"):
            return ("matched at phase %d,%d · %s"
                    % (int(rec.get("phase_x", 0)), int(rec.get("phase_y", 0)),
                       " · ".join("%s %.2f" % (g[0], g[1])
                                  for g in self.gates())))
        bad = self.failing()
        why = {
            "structure": ("this patch has nothing to match — it sits inside "
                          "one material. That is not a setting to fix; the "
                          "region falls back to the whole image, which is the "
                          "right answer here."),
            "certainty": ("more than one position fits equally well. Lower "
                          "“Minimum certainty” only if you can live with a "
                          "coin flip."),
            "match": ("the patch does not look like the template. Check the "
                      "template was built from this layer."),
        }
        first = bad[0] if bad else "match"
        return "could not place the region — %s: %s" % (first, why[first])

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
        gates = self.gates()
        row_h = min(30.0, rect.height() / (len(gates) + 1))
        for i, ((label, got, need, ok), (_l, _k, _p, full)) in enumerate(
                zip(gates, self._GATES)):
            band = QRectF(rect.left(), rect.top() + i * row_h,
                          rect.width(), row_h - 4)
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(band.left(), band.top(), 76, band.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, label)

            bar = QRectF(band.left() + 80, band.top() + band.height() / 2 - 5,
                         max(20.0, band.width() - 150), 10)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(TOKENS["hover_warm_strong"])))
            p.drawRoundedRect(bar, 3, 3)
            frac = max(0.0, min(1.0, got / full if full else 0.0))
            p.setBrush(QBrush(QColor(TOKENS["success"] if ok
                                     else TOKENS["danger_text"])))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(),
                                     max(2.0, bar.width() * frac),
                                     bar.height()), 3, 3)
            # 門檻線：沒有它，柱子的長度沒有意義（多長才算夠？）
            nx = bar.left() + bar.width() * max(0.0, min(1.0, need / full
                                                         if full else 0.0))
            p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.4))
            p.drawLine(QPointF(nx, bar.top() - 3), QPointF(nx, bar.bottom() + 3))

            p.setPen(QColor(TOKENS["text_primary"]))
            p.drawText(QRectF(bar.right() + 8, band.top(), 62, band.height()),
                       Qt.AlignRight | Qt.AlignVCenter, "%.2f" % got)

        rec = self.record()
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(rect.left(), rect.bottom() - 14, rect.width(), 14),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   "cell %d × %d px · phase %d,%d · line = the threshold"
                   % (int(rec.get("cell_w", 0)), int(rec.get("cell_h", 0)),
                      int(rec.get("phase_x", 0)), int(rec.get("phase_y", 0))))


class MeasureInspector(Inspector):
    """量測卡共用：**這張卡自己產出的每個數字，整批長什麼樣、這一顆站在哪。**

    為什麼是這一張圖
    ----------------
    `blob_dist_center 11.170` 單獨存在回答不了任何問題。而調一張量測卡的時候，
    要問的其實是：**我把參數設成這樣，量出來的東西分不分得開？**

    分布回答得了：擠成一根柱子 = 這個特徵對這批資料沒有鑑別力（不管門檻設哪裡
    都一樣）；分成兩坨 = 有東西可以分。而「這一顆在哪裡」讓使用者把畫面上看到
    的缺陷跟數字連起來 —— 那是他唯一能校準自己直覺的方式。

    只列**這張卡的**特徵（`Step.resolve_features`，含 output_prefix），
    不是整份 feature 表 —— 那是 ADC 的事，不是這張卡的事。
    """

    title = "Spread"

    #: 一次畫幾條。面板不高，六條以上每一條就只剩幾個畫素高。
    MAX_ROWS = 5
    BINS = 28

    def rows(self) -> List[str]:
        names = [n for n in self.feature_names if self.feature_values(n)]
        return names[:self.MAX_ROWS]

    def has_data(self) -> bool:
        return bool(self.rows())

    def empty_reason(self) -> str:
        return ("Run a trial to see how this card's numbers are spread across "
                "the batch. One value on its own cannot tell you whether it "
                "separates anything.")

    def percentile_of(self, name: str) -> Optional[float]:
        """這一顆在整批裡的百分位（0–100）。"""
        vals = self.feature_values(name)
        here = self.this_value(name)
        if not vals or here is None:
            return None
        below = sum(1 for v in vals if v < here)
        return 100.0 * below / float(len(vals))

    def summary(self) -> str:
        names = self.rows()
        if not names:
            return ""
        flat = [n for n in names if self._is_flat(n)]
        text = "%d values over %d defects" % (len(names),
                                              len(self.feature_values(names[0])))
        here = [n for n in names if self.percentile_of(n) is not None
                and self.percentile_of(n) >= 95.0]
        if here:
            text += ("  ·  this defect is in the top 5%% for %s"
                     % ", ".join(here))
        if flat:
            text += ("  ⚠ %s barely varies across the batch — no threshold on "
                     "it will separate anything." % ", ".join(flat))
        return text

    def _is_flat(self, name: str) -> bool:
        """整批幾乎同一個值 = 這個特徵對這批資料沒有鑑別力。"""
        vals = self.feature_values(name)
        if len(vals) < 4:
            return False
        lo, hi = min(vals), max(vals)
        if hi - lo <= 0:
            return True
        mid = (abs(lo) + abs(hi)) / 2.0 or 1.0
        return (hi - lo) / mid < 0.01

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
        names = self.rows()
        row_h = rect.height() / float(len(names))
        for i, name in enumerate(names):
            band = QRectF(rect.left(), rect.top() + i * row_h,
                          rect.width(), row_h - 2)
            self._paint_row(p, band, name)

    def _paint_row(self, p: QPainter, band: QRectF, name: str) -> None:
        vals = self.feature_values(name)
        lo, hi = min(vals), max(vals)
        if hi <= lo:
            hi = lo + 1.0

        label = QRectF(band.left(), band.top(), 116, band.height())
        p.setPen(QColor(TOKENS["text_secondary"]))
        fm = p.fontMetrics()
        p.drawText(label, Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(name, Qt.ElideRight, int(label.width()) - 4))

        value = QRectF(band.right() - 74, band.top(), 74, band.height())
        here = self.this_value(name)
        p.setPen(QColor(TOKENS["text_primary"]))
        p.drawText(value, Qt.AlignRight | Qt.AlignVCenter,
                   "—" if here is None else _fmt(here))

        plot = QRectF(label.right() + 4, band.top() + 2,
                      value.left() - label.right() - 10,
                      max(6.0, band.height() - 6))
        if plot.width() < 20:
            return

        counts = [0] * self.BINS
        for v in vals:
            k = int((v - lo) / (hi - lo) * (self.BINS - 1))
            counts[max(0, min(self.BINS - 1, k))] += 1
        top = max(counts) or 1
        bw = plot.width() / float(self.BINS)
        col = QColor(TOKENS["accent"])
        col.setAlpha(150)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        for k, c in enumerate(counts):
            h = (c / float(top)) * plot.height()
            p.drawRect(QRectF(plot.left() + k * bw, plot.bottom() - h,
                              max(1.0, bw - 0.5), h))

        # 這一顆在哪裡 —— 沒有這條線，分布只是一張統計圖，跟眼前這顆缺陷無關。
        #
        # 會落在範圍外是**正常的**：改了參數之後預覽會立刻重算，而整批還是上一次
        # 跑的。那時候把線畫到圖外（會蓋到旁邊的文字）比不畫更糟，所以夾回邊界
        # 並且畫成箭頭 —— 「在這個方向的外面」也是一個答案。
        if here is not None:
            frac = (here - lo) / (hi - lo)
            outside = frac < 0.0 or frac > 1.0
            x = plot.left() + min(1.0, max(0.0, frac)) * plot.width()
            p.setPen(QPen(QColor(TOKENS["danger_text"]), 1.6))
            p.drawLine(QPointF(x, plot.top() - 2), QPointF(x, plot.bottom() + 2))
            if outside:
                p.setBrush(QBrush(QColor(TOKENS["danger_text"])))
                p.setPen(Qt.NoPen)
                tip = -5.0 if frac < 0.0 else 5.0
                mid = (plot.top() + plot.bottom()) / 2.0
                # QPolygonF，不是三個散的 QPointF —— 後者在 PySide6 綁到別的
                # overload，直接 segfault（不是例外，是整個行程掛掉）。
                p.drawPolygon(QPolygonF([QPointF(x + tip, mid),
                                         QPointF(x, mid - 4.0),
                                         QPointF(x, mid + 4.0)]))


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 1000 or (a and a < 0.01):
        return "%.3g" % v
    return "%.3f" % v if a < 100 else "%.1f" % v


class InputInspector(Inspector):
    """Load images：**哪一頁變成哪一條流**，以及每一頁載進來長什麼樣。

    頁序已經確認（2026-07-30）
    --------------------------
    「每顆 defect 的第一張是 test、第二張是 ref」曾經是這個專案第一條待廠內
    驗證的假設；使用者已經確認就是這個順序，所以它現在是**約定**，不是猜測。

    面板留著，因為約定成立不代表每一份檔案都照著走 —— 三頁以上、單頁、或
    ``channel_order`` 被改過的資料集，配對關係仍然只有這裡看得到。而它要回答的
    問題也換了一個：**這兩張圖比得起來嗎**（整體亮度差很多就得先正規化）。

    資料來自 Load 卡放進 ``ctx.meta['input']`` 的那一份 —— 也就是引擎**實際載
    進來的東西**，不是 UI 從檔名猜的。
    """

    title = "Input"

    def info(self) -> Dict[str, Any]:
        return dict(self.meta.get("input") or {})

    def pages(self) -> List[Dict[str, Any]]:
        return [dict(d) for d in (self.info().get("pages") or [])]

    def has_data(self) -> bool:
        return bool(self.pages())

    def empty_reason(self) -> str:
        return ("Select a defect to see which page of the TIFF became which "
                "image stream.")

    def summary(self) -> str:
        pages = self.pages()
        if not pages:
            return ""
        info = self.info()
        bits = ["defect %s" % (info.get("defect_id") or "?")]
        die = info.get("die") or []
        if len(die) == 2:
            bits.append("die %d,%d" % (int(die[0]), int(die[1])))
        if info.get("nm_per_px"):
            bits.append("%.2f nm/px" % float(info["nm_per_px"]))
        else:
            # 量測一律 pixel；換算是 Export 那一刻的事，而且由使用者填。
            # （以前這裡說「CD 的 nm 值會是 0」—— 那個 0 已經不存在了。）
            bits.append("measured in pixels — set nm/px when you export")
        return " · ".join(bits)

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
        pages = self.pages()
        head = QRectF(rect.left(), rect.top(), rect.width(), 15)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(head, Qt.AlignLeft | Qt.AlignVCenter,
                   "page → stream        size        mean grey")

        row_h = min(20.0, max(14.0, (rect.height() - 18) / max(1, len(pages))))
        means = [d.get("mean") for d in pages if d.get("mean") is not None]
        spread = (max(means) - min(means)) if len(means) > 1 else 0.0
        for i, d in enumerate(pages):
            y = rect.top() + 18 + i * row_h
            band = QRectF(rect.left(), y, rect.width(), row_h)
            page = d.get("page")
            p.setPen(QColor(TOKENS["text_primary"]))
            p.drawText(QRectF(band.left(), band.top(), 150, band.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "%s → %s" % ("page %d" % page if page is not None
                                    else "file", d.get("channel", "?")))
            shape = d.get("shape") or []
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(band.left() + 150, band.top(), 90, band.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "%d × %d" % (shape[1], shape[0]) if len(shape) == 2 else "—")
            mean = d.get("mean")
            p.drawText(QRectF(band.left() + 240, band.top(), 70, band.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "—" if mean is None else "%.1f" % mean)

        if spread >= 8.0:
            # 兩張本來就該長得幾乎一樣（同一個位置、同一次掃描）。差很多不會讓
            # 對位掛掉，但會讓相減的殘差整片偏掉 —— 而那看起來像訊號。
            # 頁序已經確認，所以這裡講的是處置（先正規化），不是叫人去懷疑配對。
            p.setPen(QColor(TOKENS["warning"]))
            p.drawText(QRectF(rect.left(), rect.bottom() - 14, rect.width(), 14),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "mean grey differs by %.0f between pages — normalise "
                       "before comparing" % spread)


#: step key -> 儀表。沒列在這裡的卡用原本的特徵表（見模組說明的約定 1）。
#:
#: Enhance 的卡共用同一個儀表：它們做的事不同，但**要回答的問題是同一個**
#: （我把資訊弄掉了嗎）。F7-20 把九張併成四張，所以這裡只剩四個 key ——
#: 少的那五個不是被拿掉，是變成 ``normalize`` / ``tone`` 的一個下拉選項。
INSPECTORS: Dict[str, type] = {
    "load_patch": InputInspector,
    "roi_profile": ProfileInspector,
    "roi_template": TemplateInspector,
    "align": AlignInspector,
    "tone": EnhanceInspector,
    "normalize": EnhanceInspector,
    "denoise": EnhanceInspector,
    "flatten": EnhanceInspector,
    "glv_stats": MeasureInspector,
    "cd_measure": MeasureInspector,
    "focus_quality": MeasureInspector,
    "roi_snr": MeasureInspector,
    "cell_period": MeasureInspector,
    "blob_segment": MeasureInspector,
}


def inspector_for(step_key: str) -> Optional[type]:
    return INSPECTORS.get(str(step_key or ""))
