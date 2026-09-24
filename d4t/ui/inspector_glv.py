# d4t Studio — Gray level 卡的儀表（2026-09-24 從 inspectors.py 拆出）.
"""`glv_stats` 的面板：這一顆的灰階分布、區域對比與 worst-box。註冊在 `inspectors.INSPECTORS`。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPen,
    QPolygonF,
)

from ..core.algo import glv as algo_glv
from . import region_words, theme
from .inspector_base import (
    Inspector,
    _fmt,
    _short_number,
    paint_note_header,
)
from .theme import TOKENS, region_hex


class GlvInspector(Inspector):
    """Gray level：**這一顆量到的分布**，勾選的統計量標在上面（F18 第 2 步）。

    為什麼換掉 Spread（使用者 2026-08-21）
    -------------------------------------
    原話：「我不太喜歡要跑完才有 Spread 的設計，他是很重要，但他不應該被放在
    這邊，因為他在 run 之前都是空的。」而那句話有程式碼上的證據：

    ==============================  ====================  ================
    儀表                            資料從哪來            什麼時候有東西
    ==============================  ====================  ================
    `EnhanceInspector`              ``ctx.meta``          **預覽就有**
    `MeasureInspector`（Spread）    ``trial_results``     跑完一批才有
    ==============================  ====================  ================

    同一塊面板、同一個位置、兩種資料生命週期。這一張走的是前者：引擎在
    ``ctx.meta["glv_hist"]`` 留了每一塊的直方圖，所以**選到卡片的那一刻就有東西**。

    整批的資訊沒有消失，它縮成底下一條 8 px 的帶子（這一顆落在整批的哪裡），
    而「這個特徵分不分得開」那個問題搬去 Results —— 那裡本來就是「跑完才看」
    的地方，而且門檻拉得動（見 `ui/results.py`）。

    畫什麼
    ------
    * 一塊區域一條直方圖（最多 :data:`MAX_ROWS` 條，多的收成一句話）
    * 勾選到的統計量畫成刻度：**中心那一類畫實線，其餘畫短刻度** ——
      十個標記全畫成一樣的線的話，圖上會是一排看不出誰是誰的柵欄
    * 標題右邊是 ``n=… px · …% saturated`` —— 「這塊還能不能信」的兩個數字，
      而 patch 的 ROI 常常只有幾百個像素
    """

    title = "GLV"          # 跟卡片庫上的名字一致（2026-08-25 改名）

    #: 一次畫幾條分布。面板不高，四條以上每一條就只剩幾個畫素。
    MAX_ROWS = 3
    #: 底下那條「這一顆在整批的哪裡」的帶子有多高（跑過才畫）。
    BAND_H = 14.0
    #: 一個**位置**、畫整條實線的那幾個。
    CENTRE_MARKS = ("glv_median", "glv_p50", "glv_mean", "glv_trim")
    #: 一個**位置**、畫貼著底的短刻度的那幾個。
    POSITION_MARKS = ("glv_min", "glv_max", "glv_q")
    #: 一個**寬度**（不是位置）—— 畫成中心兩側的一段淡帶，見 :meth:`_paint_marks`。
    WIDTH_MARKS = ("glv_mad", "glv_std", "glv_iqr")

    # -- 資料 ---------------------------------------------------------------
    def rows(self) -> List[Dict[str, Any]]:
        """引擎留下的每一塊（`glv_stats._note_distribution` 寫的）。"""
        raw = self.meta.get("glv_hist")
        return [dict(r) for r in raw][:self.MAX_ROWS] if isinstance(raw, list) else []

    def has_data(self) -> bool:
        return bool(self.rows())

    def empty_reason(self) -> str:
        return ("Wire an image into this card and it will show the gray levels "
                "it measured, with the statistics you ticked marked on them.")

    def summary(self) -> str:
        rows = self.rows()
        if not rows:
            return ""
        bits = []
        for r in rows:
            where = r.get("region") or r.get("stream") or "whole image"
            bits.append("%s: %d px" % (where, int(r.get("n") or 0)))
        text = "  ·  ".join(bits)
        gated = [r for r in rows if r.get("thin")]
        if gated:
            # 使用者自己設了「至少要幾個像素」，而這一顆沒過 —— 那不是警告，
            # 是這張卡在照他說的做，所以講法是陳述句。
            text += ("  ·  under the minimum you set, so this defect's gray "
                     "levels are blank")
        thin = [r for r in rows if int(r.get("n") or 0) < self.THIN_PX
                and not r.get("thin")]
        if thin:
            # **樣本數太少的時候要講出來。** patch 的 ROI 常常只有幾百個像素，
            # 而在那個數量下離散度本身沒有意義 —— 而畫面上以前沒有任何地方
            # 說得出這件事。
            text += ("  ⚠ %s under %d pixels — spread statistics are not "
                     "reliable that thin."
                     % (", ".join(str(r.get("region") or r.get("stream") or "it")
                                  for r in thin), self.THIN_PX))
        hot = [r for r in rows if float(r.get("sat") or 0.0) > self.SAT_WARN]
        if hot:
            text += ("  ⚠ %.0f%% of the pixels sit at 0 or 255 — whatever was "
                     "in them is already gone."
                     % (100.0 * max(float(r.get("sat") or 0.0) for r in hot)))
        worst = [r for r in rows
                 if isinstance(r.get("worst"), dict) and r.get("worst")]
        if worst:
            w = worst[0]["worst"]
            text += ("  ·  odd box out: #%d at %.1fσ"
                     % (int(w.get("i", -1)), float(w.get("score") or 0.0)))
        return text

    #: 少於這麼多像素就講一句話（見 :meth:`summary`）。
    THIN_PX = 400
    #: 貼在 0/255 的比例超過這個就講一句話。
    SAT_WARN = 0.02

    # -- 標題（使用者 2026-08-21：「要更詳細一點」）--------------------------
    def _pairs(self) -> Dict[str, str]:
        """區域名 -> 它跟誰比（引擎在 ``ctx.meta["compares"]`` 留的那一份）。"""
        out: Dict[str, str] = {}
        for rec in (self.meta.get("compares") or {}).values():
            if isinstance(rec, dict):
                out[str(rec.get("target") or "")] = str(rec.get("reference") or "")
        return out

    @staticmethod
    def _intent_name(region: str) -> str:
        """接了 ``_center`` 時用意圖語言講那一塊（PR-2；字典住 `region_words`，
        跟畫布的埠 hover 同一份）。原名括號保留 —— 意圖語言是翻譯不是改名，
        使用者要對得回畫布上那顆埠。"""
        phrase = region_words.INTENT_PHRASE.get(region_words.role_of(region))
        return "%s (%s)" % (phrase, region) if phrase else region

    def tab_title(self) -> str:
        rows = self.rows()
        if not rows:
            return self.title
        pairs = self._pairs()
        first = rows[0]
        who = str(first.get("region") or "the image")
        if len(rows) > 1:
            return "%s · %d regions" % (self.title, len(rows))
        versus = pairs.get(who)
        if versus:
            # 「誰跟誰比」比「在哪條流上」重要 —— 兩個都塞得下的話字會太長，
            # 而流名在比較的那一邊已經寫出來了（`epi_others @ ref`）。
            return "%s · %s vs %s" % (self.title, self._intent_name(who),
                                      versus)
        return "%s · %s on %s" % (self.title, self._intent_name(who),
                                  str(first.get("stream") or "?"))

    def tab_tooltip(self) -> str:
        rows = self.rows()
        if not rows:
            return self.empty_reason()
        pairs = self._pairs()
        bits = []
        for r in rows:
            raw = str(r.get("region") or "the whole image")
            line = "%s on %s" % (self._intent_name(raw),
                                 r.get("stream") or "?")
            if pairs.get(raw):
                line += "  compared against %s" % pairs[raw]
            if int(r.get("boxes") or 0) > 1:
                line += "  (%d boxes, one at a time)" % int(r.get("boxes") or 0)
            bits.append(line)
        marks = sorted((rows[0].get("marks") or {}))
        if marks:
            bits.append("showing: " + ", ".join(marks))
        return "\n".join(bits)

    # -- 畫 -----------------------------------------------------------------
    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        rows = self.rows()
        if not rows:
            self._say_empty(p, rect)
            return
        body = rect
        band = None
        if self._batch_marks(rows[0]):
            body = QRectF(rect.left(), rect.top(), rect.width(),
                          rect.height() - self.BAND_H - 4)
            band = QRectF(rect.left(), body.bottom() + 4, rect.width(),
                          self.BAND_H)
        row_h = body.height() / float(len(rows))
        for i, r in enumerate(rows):
            self._paint_row(p, QRectF(body.left(), body.top() + i * row_h,
                                      body.width(), row_h - 3), r, i)
        if band is not None:
            self._paint_batch_band(p, band, rows[0])

    def _colour(self, index: int) -> QColor:
        """一塊區域一個顏色 —— **跟影像上的疊框、模板編輯器同一組**。

        不同一組的話，使用者在畫面上認得的那個綠色 ROI1，到了這裡是別的顏色，
        而沒有任何東西說得出它們是同一個。
        """
        return QColor(region_hex(index))

    def _label_rows(self) -> List[Dict[str, Any]]:
        return list(self.rows())

    def _paint_row(self, p: QPainter, band: QRectF, row: Dict[str, Any],
                   index: int) -> None:
        counts = [max(0, int(c)) for c in (row.get("bins") or [])]
        if not counts or band.height() < 12:
            return
        colour = self._colour(index)

        label = self._row_label(row)
        versus = self._pairs().get(str(row.get("region") or ""))
        tail = ""
        if versus:
            # **虛線那條就是它** —— 標題上的這一段用同一個顏色寫（見下面
            # 那個兩段式的 drawText），不然畫面上沒有任何東西說得出那條線是誰。
            tail = "  vs  " + versus
        worst = row.get("worst") if isinstance(row.get("worst"), dict) else {}
        judge_note = (row.get("judge")
                      if isinstance(row.get("judge"), dict) else {})
        if int(row.get("boxes") or 0) > 1:
            # 一格一格量的時候畫的是**典型那一格**，而畫面必須說出這件事 ——
            # 不說的話這條分布看起來像整個區域的，那是兩個不同的東西。
            if worst:
                # 贏家（F32/PR-2）：影像上描四邊的那一格。「typical #N vs
                # odd #K (X.Xσ) of M」—— 跟 `worst_*` 特徵同一份 meta，不重算。
                judge = str(worst.get("judge") or "")
                label += "  ·  typical #%d vs odd #%d (%.1fσ) of %d%s" % (
                    int(row.get("box") or 0), int(worst.get("i", -1)),
                    float(worst.get("score") or 0.0),
                    int(row.get("boxes") or 0),
                    (" by %s" % judge[4:] if judge.startswith("glv_")
                     else (" by %s" % judge if judge else "")))
            else:
                label += "  ·  typical box #%d of %d" % (
                    int(row.get("box") or 0), int(row.get("boxes") or 0))
        # 共用 header（PR-2 2f）：來源流 · 區域 · n · 可信度旗標。
        head_h = paint_note_header(
            p, band, row, colour=colour, label=label, tail=tail,
            tail_colour=QColor(TOKENS[self.REF_TOKEN]),
            trust="%.1f%% saturated" % (100.0 * float(row.get("sat") or 0.0)))

        # 逐框判準值帶（PR-2 2c）要一條自己的高度 —— 從 plot 那裡分。
        judge_h = (self.BAND_H + 2.0
                   if judge_note and judge_note.get("values") else 0.0)
        plot = QRectF(band.left(), band.top() + head_h + 1, band.width(),
                      max(8.0, band.height() - head_h - 12 - judge_h))
        top = max(counts) or 1
        bw = plot.width() / float(len(counts))
        fill = QColor(colour)
        fill.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill))
        for k, c in enumerate(counts):
            h = (c / float(top)) * plot.height()
            p.drawRect(QRectF(plot.left() + k * bw, plot.bottom() - h,
                              max(1.0, bw - 0.4), h))
        p.setPen(QColor(TOKENS["border_default"]))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))

        # 0 與 255 —— 橫軸是灰階，而**每一條的尺都一樣**（不像 Spread 那邊
        # 每一排各有各的單位），所以刻度寫兩端就夠。
        axis = QRectF(plot.left(), plot.bottom() + 1, plot.width(), 11)
        p.setPen(QColor(TOKENS["text_hint"]))
        p.drawText(axis, Qt.AlignLeft | Qt.AlignVCenter, "0")
        p.drawText(axis, Qt.AlignRight | Qt.AlignVCenter, "255")

        self._paint_reference(p, plot, row)
        self._paint_worst_overlay(p, plot, worst)
        self._paint_marks(p, plot, row, colour)
        if judge_h:
            self._paint_judge_band(
                p, QRectF(band.left(), axis.bottom() + 2, band.width(),
                          self.BAND_H),
                judge_note)

    def _paint_worst_overlay(self, p: QPainter, plot: QRectF,
                             worst: Dict[str, Any]) -> None:
        """worst 那一格的分布**疊在 typical 上**（PR-2 2c）。

        同一把 0–255 的尺、各自正規化到自己的峰（同 `_paint_reference` 的
        理由：兩塊像素數常差幾十倍）。實線、danger 色 —— worst 是**嫌疑人**
        不是背景，背景（虛線、次要色）留給參照。資料是引擎在挑 worst 的那
        一次計算裡順手留的（`glv_stats._measure_each_box`），這裡不重算。
        """
        counts = [max(0, int(c)) for c in ((worst or {}).get("bins") or [])]
        if not counts or plot.height() < 10:
            return
        ink = QColor(TOKENS["danger_text"])
        top = max(counts) or 1
        bw = plot.width() / float(len(counts))
        pts = [QPointF(plot.left() + (k + 0.5) * bw,
                       plot.bottom() - (c / float(top)) * plot.height())
               for k, c in enumerate(counts)]
        pen = QPen(ink, 1.2)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF(pts))

    def _paint_judge_band(self, p: QPainter, band: QRectF,
                          judge: Dict[str, Any]) -> None:
        """逐框判準值帶（PR-2 2c）：一格一點、基準虛線、worst 加圈。

        畫的是 worst 選拔**真的比過的那串數字**（`judge_note`，>512 格時
        引擎已取樣並記 `sampled`）—— 不是面板自己再量一次。
        """
        vals = [float(v) for v in (judge.get("values") or [])]
        boxes = [int(b) for b in (judge.get("boxes") or [])]
        if not vals or band.height() < 8:
            return
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        pad = 6.0
        mid = band.center().y() + 2.0

        def to_x(v: float) -> float:
            return band.left() + pad + (v - lo) / span * (band.width() - 2 * pad)

        stat = str(judge.get("stat") or "")
        caption = "each box by %s%s" % (
            stat[4:] if stat.startswith("glv_") else stat,
            " (sampled)" if judge.get("sampled") else "")
        p.setPen(QColor(TOKENS["text_hint"]))
        f = p.font()
        f.setPixelSize(theme.font_px("font_small"))
        p.setFont(f)
        p.drawText(band, Qt.AlignLeft | Qt.AlignTop, caption)

        base = QColor(TOKENS["text_secondary"])
        p.setPen(QPen(base, 1.0, Qt.DashLine))
        bx = to_x(float(judge.get("median") or 0.0))
        p.drawLine(QPointF(bx, band.top() + 1), QPointF(bx, band.bottom() - 1))

        dot = QColor(TOKENS["text_secondary"])
        dot.setAlpha(170)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(dot))
        worst_box = int(judge.get("worst_box", -1))
        worst_at = None
        for v, b in zip(vals, boxes):
            x = to_x(v)
            p.drawEllipse(QPointF(x, mid), 1.6, 1.6)
            if b == worst_box:
                worst_at = x
        if worst_at is not None:
            ring = QColor(TOKENS["danger_text"])
            p.setPen(QPen(ring, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(worst_at, mid), 4.0, 4.0)

    #: 參照那條分布用什麼顏色（虛線、次要色）—— 它是**背景**，量的那一塊才是
    #: 主角，所以不搶顏色。
    REF_TOKEN = "text_secondary"

    #: 相對量在圖上寫成什麼（`cmp_delta_median` → `Δ median`）。
    CMP_SHORT = {"delta": "Δ", "abs_delta": "|Δ|", "ratio": "ratio",
                 "percent": "%", "contrast": "contrast", "snr": "SNR",
                 "tstat": "t", "pct_rank": "rank", "overlap": "overlap",
                 "spread_ratio": "MAD ratio"}
    #: 圖上最多寫幾個（其餘在特徵表上）。
    CMP_MAX = 3
    #: 這幾個帶方向 —— 正負號要寫出來（`Δ +26` 與 `Δ −26` 是兩種缺陷）。
    SIGNED = ("delta", "contrast", "percent")
    #: 寫哪幾個、什麼順序 —— 「差多少」「這個差大不大」「兩邊像不像」。
    CMP_ORDER = ("delta", "snr", "overlap", "abs_delta", "contrast", "ratio",
                 "pct_rank", "tstat", "percent", "spread_ratio")

    def _paint_reference(self, p: QPainter, plot: QRectF,
                         row: Dict[str, Any]) -> None:
        """把參照那一塊的分布**疊在同一把尺上**（使用者 2026-08-21）。

        原話：「Feature 左側的 histogram 我還是沒有很滿意（相對／絕對？）」。
        面板本來只畫「這一塊自己」，而這張卡有一半在做的事是比較 —— 相對的
        那一半以前只是特徵表上的幾個數字，而數字答不出「這個差在不在雜訊裡」。
        兩條分布疊起來一眼就看得出來。

        三個刻意的選擇：

        * 參照畫**外框虛線**、不填色 —— 填兩塊色的話上面那一塊會被蓋住，而
          被蓋住的正好是量的那一塊（主角）。
        * 兩條**各自**正規化到自己的最高點。橫軸（灰階）是共用的尺，縱軸不是
          —— 參照常常是 target 的幾十倍大，照原始計數畫的話 target 會被壓成
          貼著底的一條線。
        * 兩邊的統計量各畫一條線，中間那一段就是 ``delta``：**那個數字在圖上
          的長度**，而不是另一個要自己想像的量。
        """
        ref = row.get("ref")
        if not isinstance(ref, dict):
            return
        counts = [max(0, int(c)) for c in (ref.get("bins") or [])]
        if not counts or plot.height() < 10:
            return
        ink = QColor(TOKENS[self.REF_TOKEN])
        top = max(counts) or 1
        bw = plot.width() / float(len(counts))
        pts = [QPointF(plot.left() + (k + 0.5) * bw,
                       plot.bottom() - (c / float(top)) * plot.height())
               for k, c in enumerate(counts)]
        # 先鋪一層很淡的底再描虛線：只有虛線的話，那條高對比的曲線會比**量的
        # 那一塊**（淡色的長條）還搶眼 —— 而主角是後者。
        wash = QColor(ink)
        wash.setAlpha(26)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(wash))
        p.drawPolygon(QPolygonF(
            [QPointF(plot.left(), plot.bottom())] + pts
            + [QPointF(plot.right(), plot.bottom())]))
        pen = QPen(ink, 1.0, Qt.DashLine)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF(pts))

        self._paint_gap(p, plot, ref, ink)
        text = self._compare_caption(ref)
        if text:
            # **寫在座標軸那一列的正中間**：圖裡面已經有兩條分布、兩條 stat
            # 的線與那一段 Δ，再壓一行字上去就是誰都讀不到。左右兩端是 0 與
            # 255，中間本來就空著。
            p.setPen(ink)
            p.drawText(QRectF(plot.left(), plot.bottom() + 1, plot.width(), 11),
                       Qt.AlignHCenter | Qt.AlignVCenter, text)

    def _paint_gap(self, p: QPainter, plot: QRectF, ref: Dict[str, Any],
                   ink: QColor) -> None:
        """兩邊的 stat 各一條線，中間拉一段 —— 那一段的長度就是 ``delta``。

        勾了好幾個統計量的時候只畫**第一個**：十條線疊在一張 40 px 高的圖上
        會變成一排看不出誰是誰的柵欄（同 `_paint_marks` 的老問題）。
        """
        here, there = ref.get("here") or {}, ref.get("marks") or {}
        stat = next((k for k in here if k in there), "")
        if not stat:
            return
        try:
            a, b = float(here[stat]), float(there[stat])
        except (TypeError, ValueError):
            return
        if not (0.0 <= a <= 255.0 and 0.0 <= b <= 255.0):
            return
        y = plot.top() + 5.0
        xa = plot.left() + (a / 255.0) * plot.width()
        xb = plot.left() + (b / 255.0) * plot.width()
        p.setPen(QPen(ink, 1.0, Qt.DotLine))
        p.drawLine(QPointF(xb, plot.top()), QPointF(xb, plot.bottom()))
        p.setPen(QPen(ink, 1.2))
        p.drawLine(QPointF(xa, y), QPointF(xb, y))
        for x, d in ((xa, 1 if xb > xa else -1), (xb, -1 if xb > xa else 1)):
            p.drawLine(QPointF(x, y), QPointF(x + 3.0 * d, y - 2.5))
            p.drawLine(QPointF(x, y), QPointF(x + 3.0 * d, y + 2.5))

    @classmethod
    def _compare_caption(cls, ref: Dict[str, Any]) -> str:
        """圖上那一行相對量（``Δ +23.4 · SNR 5.1 · overlap 0.02``）。

        **數字是引擎算的那一份**（`ref["values"]` 就是寫進特徵表的東西）——
        面板不自己再算一次，不然畫面上的數字跟寫出去的有機會不一樣。
        """
        values = ref.get("values") or {}
        # 哪個名字是哪個 metric，**卡片寫 note 的時候一起講了**
        # （`glv_stats.cmp_feature_specs` → ``ref["metrics"]``，PR-3）。
        # 舊 meta 沒有那張表就整行跳過 —— 不回頭猜字串。
        metrics = ref.get("metrics") or {}
        rows: List[Tuple[int, str, float]] = []
        for name, value in values.items():
            metric = str((metrics.get(str(name)) or {}).get("metric") or "")
            if metric not in cls.CMP_SHORT:
                continue
            try:
                rows.append((cls.CMP_ORDER.index(metric)
                             if metric in cls.CMP_ORDER else 99,
                             cls.CMP_SHORT[metric], float(value),
                             metric in cls.SIGNED))
            except (TypeError, ValueError):
                continue
        rows.sort(key=lambda t: t[0])
        seen: List[str] = []
        out: List[str] = []
        for _order, short, value, signed in rows:
            if short in seen:
                continue        # 同一個 metric 勾了好幾個統計量 -> 只寫第一個
            seen.append(short)
            out.append("%s %s" % (short, _short_number(value, signed)))
            if len(out) >= cls.CMP_MAX:
                break
        return "  ·  ".join(out)

    def _paint_marks(self, p: QPainter, plot: QRectF, row: Dict[str, Any],
                     colour: QColor) -> None:
        """把勾選到的統計量標在這條分布上 —— **用它自己的形狀**。

        這是整塊面板最容易說謊的地方。三種統計量在灰階軸上的意思完全不同：

        ==========================  ==========================================
        中位數 / 平均 / 修剪平均     一個**位置** → 整條實線
        最小 / 最大 / 分位數         一個**位置** → 貼著底的短刻度
        MAD / 標準差 / IQR           一個**寬度** → 中心兩側的一段淡帶
        ==========================  ==========================================

        第三種畫成一條線的話（第一版就是），`glv_mad = 65` 會在灰階 65 的地方
        畫一條線 —— 那裡什麼都沒有，而畫面上沒有任何東西說得出那條線是假的。
        寬度沒有中心可以掛的時候（只勾了 MAD、沒勾中位數）就**不畫** ——
        「這個數字沒有畫得出來的位置」是一個誠實的答案。

        剩下那幾個（偏度、峰度、熵、雙峰、飽和比例、亮度佔比）的單位根本不是
        灰階，一律不畫；它們的值在特徵表上。唯一的例外是 ``glv_above<NN>``：
        畫的是**那個門檻**（虛線），不是它的值 —— 門檻真的在灰階軸上。
        """
        marks = {str(k): v for k, v in (row.get("marks") or {}).items()}
        ink = QColor(theme.readable_on(colour.name(), TOKENS["bg_surface"]))

        def as_gray(mid):
            try:
                v = float(marks[mid])
            except (KeyError, TypeError, ValueError):
                return None
            return v if 0.0 <= v <= 255.0 else None

        def x_at(v):
            return plot.left() + (v / 255.0) * plot.width()

        centre = next((as_gray(m) for m in sorted(marks)
                       if m.startswith(self.CENTRE_MARKS)
                       and as_gray(m) is not None), None)

        # 先畫寬度（淡帶），線才不會被蓋掉。
        for mid in sorted(marks):
            if not mid.startswith(self.WIDTH_MARKS) or centre is None:
                continue
            w = as_gray(mid)
            if w is None or w <= 0:
                continue
            lo, hi = max(0.0, centre - w), min(255.0, centre + w)
            wash = QColor(ink)
            wash.setAlpha(46)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(wash))
            p.drawRect(QRectF(x_at(lo), plot.top() + plot.height() * 0.30,
                              x_at(hi) - x_at(lo), plot.height() * 0.70))
            p.setBrush(Qt.NoBrush)

        for mid in sorted(marks):
            if mid.startswith(self.CENTRE_MARKS):
                v = as_gray(mid)
                if v is None:
                    continue
                p.setPen(QPen(ink, 1.6))
                p.drawLine(QPointF(x_at(v), plot.top()),
                           QPointF(x_at(v), plot.bottom()))
            elif mid.startswith(self.POSITION_MARKS):
                v = as_gray(mid)
                if v is None:
                    continue
                p.setPen(QPen(ink, 1.1))
                p.drawLine(QPointF(x_at(v), plot.bottom() - plot.height() * 0.34),
                           QPointF(x_at(v), plot.bottom()))
            else:
                thr = algo_glv.above_of(mid)      # glv_above<NN>：畫門檻不畫值
                if thr is None:
                    continue
                p.setPen(QPen(ink, 1.1, Qt.DashLine))
                p.drawLine(QPointF(x_at(float(thr)), plot.top()),
                           QPointF(x_at(float(thr)), plot.bottom()))
        p.setPen(Qt.NoPen)

    # -- 整批那一條帶子 -----------------------------------------------------
    def _batch_marks(self, row: Dict[str, Any]) -> Optional[Tuple[str, float, float]]:
        """(特徵名, 這一顆的值, 百分位) —— 沒跑過整批就回 None。"""
        prefix = str(row.get("prefix") or "")
        for mid in sorted((row.get("marks") or {})):
            name = "%s_%s" % (prefix, mid) if prefix else mid
            vals = self.feature_values(name)
            here = self.this_value(name)
            if len(vals) >= 2 and here is not None:
                below = sum(1 for v in vals if v < here)
                return (name, here, 100.0 * below / float(len(vals)))
        return None

    def _paint_batch_band(self, p: QPainter, box: QRectF,
                          row: Dict[str, Any]) -> None:
        """整批的資訊縮成一條帶子：**這一顆落在整批的哪裡**。

        它跑完才有，所以它不能是這塊面板的主體 —— 那正是 Spread 搬家的理由。
        一條帶子放得下的東西剛好就是它真正回答得了的問題。
        """
        got = self._batch_marks(row)
        if not got:
            return
        name, here, pct = got
        p.setPen(QColor(TOKENS["text_hint"]))
        text = "%s = %s · top %d%% of the batch" % (
            name, _fmt(here), int(round(100.0 - pct)))
        left = QRectF(box.left(), box.top(), box.width() * 0.62, box.height())
        p.drawText(left, Qt.AlignLeft | Qt.AlignVCenter, text)

        track = QRectF(box.right() - box.width() * 0.34, box.center().y() - 3,
                       box.width() * 0.34, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(TOKENS["border_default"])))
        p.drawRoundedRect(track, 3, 3)
        x = track.left() + (pct / 100.0) * track.width()
        p.setBrush(QBrush(QColor(TOKENS["danger_text"])))
        p.drawEllipse(QRectF(x - 3.5, track.center().y() - 3.5, 7, 7))
        p.setBrush(Qt.NoBrush)
