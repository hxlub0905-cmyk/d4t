# d4t Studio — Enhance 卡的儀表（2026-09-24 從 inspectors.py 拆出）.
"""Tone／Normalize／Denoise／Flatten 共用的面板。註冊在 `inspectors.INSPECTORS`。"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPen,
)

from ..core.steps._util import CLIP_FRAC, PAIR_FEATURES
from ..core.steps.denoise import HOT_FRAC, REMOVED_OVER_NOISE
from .inspector_base import (
    Inspector,
    paint_note_header,
)
from .theme import TOKENS


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

    def stream_feature_name(self, key: Optional[str], name: str) -> str:
        """這一條流的某個診斷特徵**叫什麼**（多流才有前綴，F10-3）。"""
        k = key or self.stream()
        return ("%s_%s" % (k, name)) if len(self.streams()) > 1 else name

    def stream_feature(self, key: Optional[str], name: str) -> Optional[float]:
        """這一條流的某個診斷特徵值（**兩條以上才有流名前綴**，F10-3）。

        前綴規則在引擎那邊（`MultiStreamStep.run`）與這裡各寫了一次，而寫錯的
        那一半是安靜的（面板就只是不印那一行）—— 所以有一支測試從真實預覽走完
        整條路，不是只餵假資料。
        """
        return self.this_value(self.stream_feature_name(key, name))

    def pushed_out(self, key: Optional[str] = None) -> Optional[float]:
        """引擎量到的「算出來超出 0–255、被壓回來」的比例（F11 Enhance-1）。

        **跟 :meth:`clipped` 是兩件事**，所以講法也不一樣：

        - ``clipped``：輸出裡有多少畫素**坐在** 0 或 255。原圖本來就有的黑也算
          進來，而且直方圖上看得到（兩端那根染色的柱子）。
        - ``pushed_out``：這張卡**算出了值域以外的值**（實測 ``stripes_h`` 會
          到 261.5）。那些資訊在存進影像流之前就被壓掉了，所以直方圖上**看不到**
          —— 兩端的柱子只長高一點點，看起來跟原本就有的黑沒兩樣。

        數字來自引擎（``clip_frac`` 特徵，`MultiStreamStep.run` 寫的），UI 不自己
        再量一次。多流時特徵名帶流名前綴 —— 跟量測卡同一條規則（F10-3）。
        """
        return self.stream_feature(key, CLIP_FRAC)

    def replaced(self, key: Optional[str] = None) -> Optional[float]:
        """``denoise`` 的 hot_pixels 換掉了多少比例（F11 Enhance-2）。

        **這是使用者調 `threshold` 時唯一看得到的回饋**：門檻壓低到開始吃真的缺陷
        時，影像上看不出來（少了幾顆亮點而已），但這個數字會跳。
        """
        return self.stream_feature(key, HOT_FRAC)

    def sigma(self, key: Optional[str] = None) -> Optional[float]:
        """這一條流的雜訊 σ（只有 Denoise 卡量，F11 Enhance-1）。

        為什麼要露出來：``strength`` 的單位就是它（「濾掉幾個 σ 的擾動」），
        而在這之前使用者是在調一個「以某個他看不到的數字為單位」的旋鈕。
        來自 ``ctx.meta['noise_sigma']``（`denoise.note_stream` 寫的）。
        """
        table = self.meta.get("noise_sigma") or {}
        try:
            v = float(table[str(key or self.stream())])
        except (KeyError, TypeError, ValueError):
            return None
        return None if (math.isnan(v) or math.isinf(v)) else v

    def removed_over_noise(self, key: Optional[str] = None) -> Optional[float]:
        """磨掉的東西有幾個 σ（`denoise` 的平滑法，F11 Enhance-UI-E）。

        ≈1 = 磨掉的量級就是雜訊（想要的）；≫1 = 連結構一起磨掉了。這是
        ``strength`` / ``ksize`` 那兩個旋鈕唯一的問題，而**兩種結果在單顆畫面上
        都「看起來乾淨了」** —— 那正是它需要一個數字的理由。
        """
        return self.stream_feature(key, REMOVED_OVER_NOISE)

    #: 兩條流差多少就算「還不能比」。**經驗值，不是定理** —— 面板同時把實際數字
    #: 印出來，使用者自己看得到它離這條線多遠。
    #: 5 個灰階的整片偏移在 diff 上是看得見的一塊；起伏差 1.5 倍表示同一個門檻
    #: 在兩張圖上抓到的東西不一樣多。
    PAIR_LEVEL_OK = 5.0
    PAIR_RATIO_OK = 1.5

    def pair(self) -> Optional[Tuple[float, float]]:
        """這張卡處理的前兩條流**還有多像**（F11 Enhance-UI-B）。

        回 ``(背景差幾個灰階, 起伏差幾倍)``，只有一條流時回 None。
        可比性是 `subtract` 的前提，而「不可比」在畫面上長得像「兩張圖本來就不
        一樣」—— 一張比較亮的 ref 減出來的 diff 整片偏移，看起來就像一個大面積
        的缺陷。
        """
        if len(self.streams()) < 2:
            return None
        delta = self.this_value(PAIR_FEATURES[0])
        ratio = self.this_value(PAIR_FEATURES[1])
        if delta is None or ratio is None:
            return None
        return (delta, ratio)

    def batch_pushed_out(self, key: Optional[str] = None) -> List[float]:
        """**整批**每一顆被壓回值域的比例（F11 Enhance-UI-H）。

        為什麼一定要有整批的那一版
        --------------------------
        這是 `AlignInspector` 教過的那一課：Enhance 的失敗是**「某幾顆」**的事。
        調參數的人看的是第 1 顆，而出問題的是第 57 顆 —— 單顆的數字永遠只回答
        那一顆，不管它多準。

        資料來自 ``trial_results``（引擎跑出來的整批），所以不必再跑一次。
        """
        return self.feature_values(self.stream_feature_name(key, CLIP_FRAC))

    def batch_over_limit(self, key: Optional[str] = None) -> Tuple[int, int]:
        """整批裡**有幾顆**壓掉超過 1%（回 ``(超過的, 總共)``）。"""
        vals = self.batch_pushed_out(key)
        return (sum(1 for v in vals if v > self.WARN_CLIP), len(vals))

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
            # 直方圖看不到的兩個數字，就寫在它旁邊（σ 是旋鈕的單位；
            # pushed_out 是「這張卡把資訊推到值域外」而那在圖上看不出來）。
            extra = []
            sig = self.sigma(key)
            if sig is not None:
                extra.append("noise σ ≈ %.1f" % sig)
            hot = self.replaced(key)
            if hot is not None:
                extra.append("%.2f%% replaced as hot/dead pixels"
                             % (hot * 100.0))
            rem = self.removed_over_noise(key)
            if rem is not None:
                extra.append("removed %.1f× the noise" % rem)
            out = self.pushed_out(key)
            if out is not None and out >= 0.0005:
                extra.append("%.1f%% computed outside 0–255 and clipped back"
                             % (out * 100.0))
            if extra:
                bits[-1] += " (%s)" % ", ".join(extra)
            alo, ahi = self.added_clipping(key)
            worst = max(worst, alo, ahi)
        text = " · ".join(bits)
        alo = ahi = worst
        if max(alo, ahi) >= self.WARN_CLIP:
            text += ("  ⚠ this card flattened %.1f%% of the patch onto the "
                     "ends of the scale — those pixels no longer differ from "
                     "each other, and every measure card downstream reads "
                     "them as identical." % (max(alo, ahi) * 100.0))
        pair = self.pair()
        if pair is not None:
            keys = self.streams()
            delta, ratio = pair
            text += ("  ·  “%s” vs “%s” now: %.1f gray levels apart, spread "
                     "%.2f×" % (keys[0], keys[1], delta, ratio))
            if delta > self.PAIR_LEVEL_OK or ratio > self.PAIR_RATIO_OK:
                text += (" — still not comparable, so the difference image "
                         "will show that gap as if it were a defect")
        over, total = self.batch_over_limit(panes[0] if panes else None)
        if over:
            # **這一句講的是別的顆**，所以它要講「幾顆之中的幾顆」而不是一個比例
            # —— 使用者接下來要做的事是去看那幾顆。
            text += ("  ⚠ %d of the %d defects in the last trial lost more "
                     "than 1%% this way — the one on screen is not the worst "
                     "case." % (over, total))
        return text

    #: 整批那條走勢圖的高度（含標籤）。面板只有 ~200px，所以它必須很薄 ——
    #: 它回答的是一個是非題（「有沒有別的顆更糟」），不是一張要細看的圖。
    _STRIP_H = 22.0

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        panes = self.panes()
        if not panes:
            return
        # 共用 header（PR-2 2f）：來源流 · n · 這張卡壓掉多少（可信度旗標）。
        rec = self.record(panes[0]) or {}
        clip = (float(rec.get("clipped_low") or 0.0)
                + float(rec.get("clipped_high") or 0.0))
        head_h = paint_note_header(
            p, rect, {"stream": panes[0],
                      "n": int(sum(rec.get("after") or []))},
            colour=QColor(TOKENS["text_primary"]),
            trust="%.1f%% clipped" % (100.0 * clip) if clip else "")
        rect = QRectF(rect.left(), rect.top() + head_h + 1, rect.width(),
                      rect.height() - head_h - 1)
        # 整批的走勢圖佔底下一條，**只有真的有整批資料時才佔位子**（跑過一次
        # trial 之前它是空的，而一條空的軸線只是雜訊）。
        body = rect
        strip = None
        if self.batch_pushed_out(panes[0]):
            body = QRectF(rect.left(), rect.top(), rect.width(),
                          max(40.0, rect.height() - self._STRIP_H))
            strip = QRectF(rect.left(), body.bottom(), rect.width(),
                           self._STRIP_H)
        # 並排比對打開時畫兩張 —— 左右的順序跟畫面上兩張圖一樣。
        gap = 14.0
        w = (body.width() - gap * (len(panes) - 1)) / float(len(panes))
        for i, key in enumerate(panes):
            box = QRectF(body.left() + i * (w + gap), body.top(), w, body.height())
            self._paint_one(p, box, key, with_axis_title=(i == 0))
        if strip is not None:
            self._paint_batch_strip(p, strip, panes[0])

    def _paint_batch_strip(self, p: QPainter, rect: QRectF, key: str) -> None:
        """整批的 ``clip_frac``：一顆一根，超過 1% 的那幾根染警示色。

        為什麼是逐顆一根、而不是一個分布直方圖
        --------------------------------------
        使用者接下來要做的事是**去看那幾顆**，所以橫軸要是「第幾顆」——
        分布圖答得出「有幾顆很糟」，但答不出「是哪幾顆」。
        """
        vals = self.batch_pushed_out(key)
        if not vals:
            return
        label = "clip across %d defects" % len(vals)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(rect.left(), rect.top(), rect.width(), 12),
                   Qt.AlignLeft | Qt.AlignVCenter, label)
        over = sum(1 for v in vals if v > self.WARN_CLIP)
        if over:
            p.setPen(QColor(TOKENS["danger_text"]))
            p.drawText(QRectF(rect.left(), rect.top(), rect.width(), 12),
                       Qt.AlignRight | Qt.AlignVCenter,
                       "%d over 1%%" % over)
        plot = QRectF(rect.left(), rect.top() + 12, rect.width(),
                      max(4.0, rect.height() - 13))
        # 刻度固定從 0 起、上界是 max 與 1% 的較大者 —— 全部都很小的時候不要把
        # 0.01% 放大成滿格（那看起來像是出了事）。
        top = max(max(vals), self.WARN_CLIP)
        bw = plot.width() / float(len(vals))
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))
        p.setPen(Qt.NoPen)
        warn = QColor(TOKENS["danger_text"])
        ok = QColor(TOKENS["accent"])
        ok.setAlpha(150)
        for i, v in enumerate(vals):
            h = (v / top) * plot.height() if top > 0 else 0.0
            if v <= 0.0:
                continue
            p.setBrush(QBrush(warn if v > self.WARN_CLIP else ok))
            p.drawRect(QRectF(plot.left() + i * bw, plot.bottom() - h,
                              max(1.0, bw - 0.5), max(1.0, h)))

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

        # 兩端的削平：把貼在 0 / 255 的那一格**整根柱子**染成警示色。
        #
        # 以前是在圖的正上方畫一小塊色塊。那個位置離它在講的那根柱子有半張圖那麼
        # 遠，於是它看起來像是一個獨立的裝飾 —— 使用者看得到它，但看不出來它在指
        # 什麼。標記要長在被標記的東西上面。
        lo, hi = self.clipped(key)
        alo, ahi = self.added_clipping(key)
        for frac, added, at_left in ((lo, alo, True), (hi, ahi, False)):
            if frac <= 0.0005:
                continue
            col = QColor(TOKENS["danger_text"] if added >= self.WARN_CLIP
                         else TOKENS["warning"])
            idx = 0 if at_left else (len(after) - 1)
            h = ((after[idx] / top) * plot.height()) if 0 <= idx < len(after) else 0.0
            x = plot.left() if at_left else plot.right() - bw
            w = max(1.0, bw - 0.6)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            if h > 0:
                p.drawRect(QRectF(x, plot.bottom() - h, w, h))
            # 柱子再矮也要看得見，所以柱頂再壓一小塊（柱高 0 時它就是全部）。
            cap = QRectF(x, plot.bottom() - max(h, 3.0) - 3.0, max(3.0, w), 3.0)
            p.drawRect(cap)

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
