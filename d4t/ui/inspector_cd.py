# d4t Studio — CD 卡的儀表（2026-09-24 從 inspectors.py 拆出）.
"""`cd_measure` 的面板：剖面圖與邊緣（F19）。註冊在 `inspectors.INSPECTORS`。"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetricsF,
    QPainter,
    QPen,
    QPolygonF,
)

from ..core.steps.cd import _BLOB_REASONS as _CD_BLOB_REASONS
from ..core.steps.cd import reasons_in_words as _cd_reasons_in_words
from .inspector_base import (
    Inspector,
    paint_note_header,
    row_labels,
)
from .theme import TOKENS, region_hex


class CdInspector(Inspector):
    """CD：**這一條線的剖面**、每條線量到多寬、以及這一顆站在整批的哪裡（F19）。

    為什麼主角是剖面圖
    ------------------
    CD 是所有量測裡最特別的一種：**數字錯了從數字上完全看不出來，從圖上一眼就
    看得出來**（掃描線壓在錯的結構上、切到轉角、跨過兩根線）。所以這張面板的
    第一格是計量儀器的那個經典畫面 —— 曲線、判準那條橫線、兩個交點 ——
    它不需要任何說明文件就講完了整張卡的語義：判準是什麼、邊被判在哪、為什麼是
    這個數字。

    **參數面板存在的目的，是讓這張圖看起來對。**

    第二格是**粗糙度的圖**，不只是一個 σ：頸縮發生在結構的哪一段看得到，而那是
    ``cd_min`` 那個數字答不出來的。第三格重用 `MeasureInspector` 的分布圖。

    資料從 ``ctx.meta["cd"]`` 來（`cd_measure._note` 寫的）—— 跟
    `GlvInspector` 同一條路，所以**選到卡片的那一刻就有東西**，不必先跑一批。
    """

    title = "CD"

    #: 剖面圖佔的寬度比例。它是主角，所以拿走一半。
    PROFILE_W = 0.46
    #: 每條線的寬度那一格佔的比例（剩下的給整批分布）。
    WOBBLE_W = 0.24
    #: 剖面圖在量到的那一對兩側各留幾倍的寬度（見 :meth:`_profile_window`）。
    PROFILE_MARGIN = 1.1
    #: 圖底下那一行「尺有多長」的字佔多高 —— **畫圖之前要先扣掉它**。
    SCALE_ROW = 14.0
    #: 一次畫幾個區域。面板不高，四列以上每一列的曲線就只剩幾個畫素
    #: （跟 `GlvInspector.MAX_ROWS` 同一個理由、同一個數字）。
    MAX_ROWS = 3
    #: 兩列之間留多少（分隔線畫在正中間）。
    ROW_GAP = 8.0

    # -- 資料 ---------------------------------------------------------------
    def notes(self) -> List[Dict[str, Any]]:
        """這張卡在這一顆上留下的每一份（一條流 × 一個區域一份）。

        **順序跟接線的順序一樣**（``region_index``），不是照名字排序 ——
        面板一列一個區域、而顏色是照 ``region_index`` 給的，照名字排的話
        "top,bot" 會畫成「橘的在上、綠的在下」，跟影像上的框反過來。
        """
        raw = self.meta.get("cd")
        if not isinstance(raw, dict):
            return []
        out = []
        for prefix in sorted(raw):
            note = raw[prefix]
            if isinstance(note, dict):
                out.append(dict(note, prefix=str(prefix)))
        out.sort(key=lambda n: (int(n.get("region_index", 0) or 0),
                                str(n.get("prefix", ""))))
        return out

    def _label_rows(self) -> List[Dict[str, Any]]:
        return self.notes()

    def note(self) -> Optional[Dict[str, Any]]:
        got = self.notes()
        return got[0] if got else None

    def has_data(self) -> bool:
        return self.note() is not None

    def empty_reason(self) -> str:
        return ("Run a trial to see the profile this card is measuring, where "
                "it put the two edges, and how the width varies along the "
                "structure.")

    def where(self) -> str:
        note = self.note() or {}
        region = str(note.get("region") or "whole image")
        stream = str(note.get("stream") or "")
        return "%s @ %s" % (region, stream) if stream else region

    def tab_title(self) -> str:
        notes = self.notes()
        if not notes:
            return "CD"
        if len(notes) > 1:
            # 面板現在**每一個區域都畫**，所以標題不能只叫其中一個的名字
            # （`GlvInspector.tab_title` 同一句話、同一個理由）。
            return "CD · %d regions" % len(notes)
        return "CD · %s" % self.where()

    def colour(self, note: Optional[Dict[str, Any]] = None) -> str:
        """這一份要畫成什麼顏色 —— **跟影像上那個區域的框同一個**。

        既有的規矩（`GlvInspector._colour` 立下的）：一個具名區域一個顏色，
        而疊框、模板編輯器、GLV 面板三個地方用同一組 `theme.REGION_COLORS`。
        CD 一開始整張畫 accent 藍，於是**同一塊區域在 GLV 面板上是綠的、在
        CD 面板上是藍的、而影像上的框又是綠的** —— 三個地方講同一件事，畫面上
        卻看不出它們有關係。

        索引由卡片給（``note["region_index"]``），不是這裡從自己那邊數的 ——
        兩邊各數各的話，"top,bot" 在一邊是 0/1、在另一邊（照名字排序）是 1/0，
        而**顏色指錯區域比沒有顏色糟得多**。
        """
        note = (self.note() if note is None else note) or {}
        if not str(note.get("region") or ""):
            # **量整張圖的時候沒有區域，也就沒有那個區域的顏色。**
            # 影像上的標記在這個情況畫 accent（`ImageView._paint_marks`：沒有
            # labels 就整組 accent），面板照樣畫 `region_hex(0)` 的綠的話，
            # 同一件事在兩邊又是兩個顏色 —— 那正是這條規矩要擋的東西。
            return str(TOKENS["accent"])
        return region_hex(int(note.get("region_index", 0) or 0))

    def is_blob(self, note: Optional[Dict[str, Any]] = None) -> bool:
        """這一顆走的是無方向那一支嗎（F19 第二批）。"""
        note = (self.note() if note is None else note) or {}
        return str(note.get("shape")) == "blob"

    def tab_tooltip(self) -> str:
        note = self.note()
        if note is None:
            return ""
        if self.is_blob():
            return ("area and calipers of the %s blob, cut at %.0f"
                    % (note.get("target_used") or "?", note.get("level", 0.0)))
        return ("%s edges, measured along %s, on the %s band"
                % (note.get("criterion", "?"), note.get("axis", "?"),
                   note.get("target_used") or note.get("target", "?")))

    def summary(self) -> str:
        """一行 —— 接了幾個區域就講幾個，各自冠上自己的名字。

        以前這裡只講第一個、後面補一句 ``+N more``，而「+1 more」說不出那一個
        是量到了還是量不到 —— 面板既然每一列都畫了，這一行也要每一個都講。
        """
        notes = self.notes()
        if len(notes) > 1:
            pairs = list(zip(row_labels(notes), notes))[:self.MAX_ROWS]
            return "  |  ".join("%s: %s" % (lab, self._one_summary(n))
                                for lab, n in pairs)
        return self._one_summary(notes[0]) if notes else ""

    def _one_summary(self, note: Dict[str, Any]) -> str:
        """一個區域那一段（多區域的時候會冠上區域名，見 :meth:`summary`）。"""
        if note is None:
            return ""
        if str(note.get("shape")) == "blob":
            return self._blob_summary(note)
        widths = [float(v) for v in (note.get("widths") or [])]
        n, total = int(note.get("n", 0)), int(note.get("lines", 0))
        if not widths:
            # **失敗時這一行比任何圖都有用** —— 它是使用者唯一會讀的東西。
            why = _cd_reasons_in_words(note.get("reasons") or {})
            return ("no width here — %s (0 of %d lines)"
                    % (why or "no pair of edges found", total)) if total else ""
        med = sorted(widths)[len(widths) // 2]
        sd = math.sqrt(sum((v - sum(widths) / len(widths)) ** 2
                           for v in widths) / len(widths))
        bits = ["CD %.2f px" % med, "sigma %.2f" % sd,
                "%d/%d lines" % (n, total),
                str(note.get("criterion") or ""), str(note.get("axis") or "")]
        return "  ·  ".join([b for b in bits if b])

    def _blob_summary(self, note: Dict[str, Any]) -> str:
        """團那一支的一行。失敗時講**為什麼**，成功時講量到什麼與可不可信。"""
        if not note.get("ok"):
            why = _CD_BLOB_REASONS.get(str(note.get("reason")),
                                       str(note.get("reason") or "unknown"))
            return "no size here — %s" % why
        bits = ["area %d px" % int(note.get("area", 0)),
                "%.1f × %.1f px" % (float(note.get("feret_max", 0.0)),
                                    float(note.get("feret_min", 0.0))),
                "at %.0f°" % float(note.get("feret_angle", 0.0))]
        if int(note.get("pieces", 1)) > 1:
            # **它挑了一團**，而那是使用者該知道的
            bits.append("%d blobs, measured the middle one"
                        % int(note.get("pieces", 1)))
        if note.get("touches_edge"):
            bits.append("⚠ touches the edge — a lower bound")
        return "  ·  ".join(bits)

    # -- 畫 -----------------------------------------------------------------
    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        """**接了幾個區域就畫幾列**（每列一個顏色）。

        以前這裡只畫 ``notes()[0]``，而那一份是**照名字排序**的第一個 ——
        於是接兩個區域的時候，影像上兩塊都畫了標記，面板卻只講其中一塊，
        而且沒有任何東西說得出另一塊去了哪。最糟的形狀是那一塊剛好量不到：
        圖上的輪廓在 B 區、面板卻在講 A 區的「什麼都沒有」。

        `GlvInspector` 早就是這樣畫的（一塊區域一條分布），這裡只是跟上。
        """
        notes = self.notes()
        if not notes:
            self._say_empty(p, rect)
            return
        shown = notes[:self.MAX_ROWS]
        # 共用 header（PR-2 2f）：來源流 · 區域 · n · 可信度旗標。整個面板
        # 一條（多列時每列自己的名字照舊在第一格上）——只加標題，主體不動。
        first = shown[0]
        blob = self.is_blob(first)
        head_h = paint_note_header(
            p, rect, {"stream": first.get("stream", ""),
                      "n": (int(first.get("area") or 0) if blob
                            else int(first.get("n") or 0))},
            colour=QColor(self.colour(first)),
            label=self._row_label(first),
            trust=("" if first.get("ok", True)
                   else str(first.get("reason") or "not measured")),
            unit="px" if blob else "line(s)")
        rect = QRectF(rect.left(), rect.top() + head_h + 1, rect.width(),
                      rect.height() - head_h - 1)
        row_h = rect.height() / float(len(shown))
        for i, note in enumerate(shown):
            body = QRectF(rect.left(), rect.top() + i * row_h, rect.width(),
                          row_h - (self.ROW_GAP if len(shown) > 1 else 0.0))
            if i:
                self._paint_row_divider(p, body.top() - self.ROW_GAP / 2.0, rect)
            self._paint_one(p, body, note, first=(i == 0),
                            solo=(len(shown) == 1))

    def _paint_one(self, p: QPainter, rect: QRectF, note: Dict[str, Any],
                   first: bool = True, solo: bool = True) -> None:
        """一個區域那一列 —— 三格並排，跟以前一模一樣。

        疊起來的時候**第一格的小標題換成區域名**（畫成那個區域的顏色）：
        每一列因此自己說得出自己是誰，而顏色與名字是同一個地方講的。
        第二、三格的小標題只畫在最上面那一列 —— 它們是**欄位名**，一列一份
        只是噪音，而每一列本來就只有一百來個畫素高。
        """
        gap = 10.0
        pw = rect.width() * self.PROFILE_W
        ww = rect.width() * self.WOBBLE_W
        blob = self.is_blob(note)
        head = (None if solo
                else (self._row_label(note), QColor(self.colour(note))))
        firsts = (("Levels in this region" if blob else "Profile of one line")
                  if solo else "")
        others = (first or solo)
        one = QRectF(rect.left(), rect.top(), pw, rect.height())
        second = QRectF(rect.left() + pw + gap, rect.top(), ww - gap,
                        rect.height())
        third = QRectF(rect.left() + pw + ww + gap, rect.top(),
                       rect.width() - pw - ww - gap, rect.height())
        # 三格之間各畫一條很淡的直線。**三張圖並排而沒有界線的話，眼睛會把
        # 隔壁那一格的線讀進來** —— 尤其中間那一格的橫軸跟左邊那一格完全不是
        # 同一件事（一個是灰階、一個是寬度）。
        self._paint_divider(p, one.right() + gap / 2.0, rect)
        self._paint_divider(p, second.right() + gap / 2.0, rect)
        if blob:
            # 直方圖 ＋ 判準那條線是剖面圖的**同義詞**：它一樣回答
            # 「為什麼是這個數字」。
            self._paint_levels(p, one, note, caption=firsts, head=head)
            self._paint_outline(p, second, note,
                                caption="Outline" if others else "")
            self._paint_batch(p, third, note, name="cd_area_px",
                              caption="Area across the batch" if others else "")
            return
        self._paint_profile(p, one, note, caption=firsts, head=head)
        self._paint_wobble(p, second, note,
                           caption=("Each line · band = 1 sigma"
                                    if others else ""))
        self._paint_batch(p, third, note,
                          caption="Across the batch" if others else "")

    @staticmethod
    def _paint_divider(p: QPainter, x: float, rect: QRectF) -> None:
        pen = QPen(QColor(TOKENS["border_default"]), 1.0)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawLine(QPointF(x, rect.top() + 2.0), QPointF(x, rect.bottom() - 2.0))

    @staticmethod
    def _paint_row_divider(p: QPainter, y: float, rect: QRectF) -> None:
        """兩個區域之間那一條 —— 直的分隔線在列與列之間是連著的，
        沒有這一條的話上下兩列讀起來像同一張圖被切成兩半。"""
        pen = QPen(QColor(TOKENS["border_default"]), 1.0)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    def _caption(self, p: QPainter, rect: QRectF, text: str,
                 head: Optional[Tuple[str, QColor]] = None) -> QRectF:
        """小標題，回剩下可以畫的那一塊。

        ``head`` 是「這一列是哪個區域」——畫在最前面、用那個區域的顏色。
        給了 ``head`` 就一定佔一行（即使 ``text`` 是空的），因為那一行是這一列
        的身分，不是裝飾。
        """
        if head is None and not text:
            return rect
        # ⚠ 這一行要**照字型自己的高度**留，不能寫死 13 px：區域名裡的底線畫在
        # 基線底下，13 px 的框把它切掉，於是 ``band_a_center`` 在畫面上是
        # 「band a center」—— 而那不是同一個名字（它在 CSV 上是有底線的那個）。
        row = QRectF(rect.left(), rect.top(), rect.width(),
                     max(13.0, QFontMetricsF(p.font()).height()))
        if head is not None:
            name, colour = head
            p.setPen(QColor(colour))
            p.drawText(row, Qt.AlignLeft | Qt.AlignVCenter, name)
            used = QFontMetricsF(p.font()).horizontalAdvance(name) + 8.0
            row = QRectF(row.left() + used, row.top(),
                         max(0.0, row.width() - used), row.height())
        if text:
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(row, Qt.AlignLeft | Qt.AlignVCenter, text)
        used = row.height() + 2.0
        return QRectF(rect.left(), rect.top() + used, rect.width(),
                      rect.height() - used)

    def _paint_profile(self, p: QPainter, rect: QRectF, note: Dict[str, Any],
                       caption: str = "Profile of one line",
                       head: Optional[Tuple[str, QColor]] = None) -> None:
        """曲線 ＋ 判準那條橫線 ＋ 兩個交點 ＋ 中間標著量到多寬。

        **只畫量到的那一段前後**（見 :data:`PROFILE_MARGIN`），不是整條剖面。
        一張 128 px 的 patch 上有八個一模一樣的週期，整條畫出來的話那兩個交點
        淹在裡面 —— 而這一格的**唯一**工作就是「邊被判在哪」。
        """
        body = self._caption(p, rect, caption, head)
        prof = note.get("profile") or {}
        values = [float(v) for v in (prof.get("values") or [])]
        if len(values) < 3 or body.height() < 24:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(body, Qt.AlignCenter | Qt.TextWordWrap,
                       "no line here measured a pair of edges")
            return
        n = len(values)
        x0, x1 = self._profile_window(prof, n)
        seen = values[int(x0):int(x1) + 1] or values
        lo, hi = min(seen), max(seen)
        span = (hi - lo) or 1.0
        width = max(1.0, float(x1 - x0))

        def at(x: float, v: float) -> QPointF:
            return QPointF(body.left() + ((x - x0) / width) * body.width(),
                           body.bottom() - ((v - lo) / span) * body.height())

        # 判準那條橫線先畫（曲線要壓在它上面）
        level = prof.get("level")
        if level is not None:
            y = at(0.0, float(level)).y()
            pen = QPen(QColor(TOKENS["text_disabled"]), 1.0, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(body.left(), y), QPointF(body.right(), y))
        p.setPen(QPen(QColor(self.colour(note)), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([at(i, values[i])
                                  for i in range(int(x0), int(x1) + 1)]))

        a, b = prof.get("a"), prof.get("b")
        if a is None or b is None:
            return
        a, b = float(a), float(b)
        # 兩個交點：一條到底的點線 + 實心圓（「邊被判在這裡」）
        p.setPen(QPen(QColor(self.colour(note)), 1.0, Qt.DotLine))
        for x in (a, b):
            vx = at(x, hi).x()
            p.drawLine(QPointF(vx, body.top()), QPointF(vx, body.bottom()))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self.colour(note))))
        for x in (a, b):
            centre = (level if level is not None
                      else values[max(0, min(n - 1, int(round(x))))])
            p.drawEllipse(at(x, float(centre)), 3.0, 3.0)
        p.setBrush(Qt.NoBrush)
        # 兩個交點之間拉一條有擋頭的量測線，數字寫在它上面 —— **那才是這張圖
        # 在講的東西**。第一版把數字壓在曲線正中間，剛好落在訊號上。
        left, right = at(min(a, b), hi).x(), at(max(a, b), hi).x()
        y = body.bottom() - 6.0
        p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.2))
        p.drawLine(QPointF(left, y), QPointF(right, y))
        for x in (left, right):
            p.drawLine(QPointF(x, y - 3.0), QPointF(x, y + 3.0))
        p.drawText(QRectF(min(left, right) - 30.0, y - 24.0,
                          abs(right - left) + 60.0, 15.0),
                   Qt.AlignHCenter | Qt.AlignBottom, "%.2f px" % abs(b - a))

    def _profile_window(self, prof: Dict[str, Any], n: int):
        """剖面圖要畫哪一段 ``(x0, x1)``（整數索引，含兩端）。

        以量到的那一對為中心，兩側各留 :data:`PROFILE_MARGIN` 倍的寬度 ——
        留白是為了看得到「邊的外面長什麼樣」（平台平不平、是不是緊鄰著另一個
        結構），那正是判斷「這一對配對得對不對」要看的東西。
        """
        a, b = prof.get("a"), prof.get("b")
        if a is None or b is None:
            return 0, n - 1
        a, b = float(a), float(b)
        pad = max(4.0, abs(b - a) * self.PROFILE_MARGIN)
        x0 = int(max(0, math.floor(min(a, b) - pad)))
        x1 = int(min(n - 1, math.ceil(max(a, b) + pad)))
        return (0, n - 1) if x1 - x0 < 4 else (x0, x1)

    def _paint_wobble(self, p: QPainter, rect: QRectF, note: Dict[str, Any],
                      caption: str = "Each line · band = 1 sigma") -> None:
        """每條線量到多寬 —— **粗糙度的圖**，縱軸是沿著結構的位置。

        一個 σ 說得出「有多不齊」，說不出「哪一段不齊」。頸縮在這張圖上是一個
        往內凹的缺口，而那是 ``cd_min`` 那個數字答不出來的事。
        """
        # ⚠ 這一格只有兩百像素寬。第一版把「band = 1 sigma」跟範圍寫在同一行，
        # 於是畫出來是「85 - 25.76 px · band = 1 sig」—— **兩端都被截掉**，而
        # 被截掉的正好是最需要讀的那兩個數字。說明搬到標題（那裡寬得多）。
        body = self._caption(p, rect, caption)
        widths = [float(v) for v in (note.get("widths") or [])]
        if len(widths) < 2 or body.height() < 24:
            return
        # **底下那一行字自己的位置要先扣掉。** 第一版把範圍寫在 `body` 的下緣，
        # 而曲線畫滿整個 `body` —— 兩個疊在一起（截圖出來才看到）。
        plot = QRectF(body.left(), body.top(), body.width(),
                      body.height() - self.SCALE_ROW)
        lo, hi = min(widths), max(widths)
        span = (hi - lo) or 1.0
        # 太窄的話把尺撐開一點，不然逐點的抖動會被畫成滿版的鋸齒
        if span < 0.5:
            mid = (lo + hi) / 2.0
            lo, hi, span = mid - 0.25, mid + 0.25, 0.5

        def at(v: float, i: int) -> QPointF:
            return QPointF(plot.left() + ((v - lo) / span) * plot.width(),
                           plot.top() + (i / max(1.0, len(widths) - 1.0))
                           * plot.height())

        srt = sorted(widths)
        med = srt[len(srt) // 2]
        mean = sum(widths) / len(widths)
        sd = math.sqrt(sum((v - mean) ** 2 for v in widths) / len(widths))
        # ±σ 墊成一條淡帶：**沒有它，一條很齊的線跟一條很糙的線長得一樣**
        # （橫軸是自動縮放的，3 px 的散布也會撐滿整格）。
        if sd > 0:
            band = QColor(self.colour(note))
            band.setAlpha(38)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(band))
            x_lo = at(max(lo, med - sd), 0).x()
            x_hi = at(min(hi, med + sd), 0).x()
            p.drawRect(QRectF(x_lo, plot.top(), max(1.0, x_hi - x_lo),
                              plot.height()))
            p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(TOKENS["text_disabled"]), 1.0, Qt.DashLine))
        p.drawLine(QPointF(at(med, 0).x(), plot.top()),
                   QPointF(at(med, 0).x(), plot.bottom()))
        p.setPen(QPen(QColor(self.colour(note)), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([at(v, i) for i, v in enumerate(widths)]))
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(body.left(), body.bottom() - self.SCALE_ROW,
                          body.width(), self.SCALE_ROW),
                   Qt.AlignHCenter | Qt.AlignVCenter,
                   "%.1f - %.1f px" % (min(widths), max(widths)))

    def _paint_levels(self, p: QPainter, rect: QRectF, note: Dict[str, Any],
                      caption: str = "Levels in this region",
                      head: Optional[Tuple[str, QColor]] = None) -> None:
        """區域的灰階直方圖 ＋ 判準那條線 —— **剖面圖的同義詞**。

        它回答的是同一個問題：**為什麼是這個數字**。門檻切在直方圖的哪裡看得
        見，所以「切太多／切太少」不必先跑一批才發現。
        """
        body = self._caption(p, rect, caption, head)
        hist = note.get("hist") or {}
        counts = [max(0, int(c)) for c in (hist.get("counts") or [])]
        if not counts or body.height() < 24:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(body, Qt.AlignCenter | Qt.TextWordWrap,
                       "nothing measured in this region")
            return
        lo, hi = float(hist.get("lo", 0.0)), float(hist.get("hi", 1.0))
        span = (hi - lo) or 1.0
        # 縱軸取 log：背景那一根通常是前景的幾百倍高，線性軸上前景會整個不見。
        heights = [math.log1p(c) for c in counts]
        peak = max(heights) or 1.0
        bw = body.width() / float(len(counts))
        faint = QColor(self.colour(note))
        faint.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(faint))
        for i, val in enumerate(heights):
            h = (val / peak) * (body.height() - 14.0)
            p.drawRect(QRectF(body.left() + i * bw, body.bottom() - h,
                              max(1.0, bw - 1.0), h))
        p.setBrush(Qt.NoBrush)

        def at(v: float) -> float:
            return body.left() + ((float(v) - lo) / span) * body.width()

        for key, style in (("bg", Qt.DotLine), ("fg", Qt.DotLine)):
            if note.get(key) is None:
                continue
            p.setPen(QPen(QColor(TOKENS["text_disabled"]), 1.0, style))
            x = at(note[key])
            p.drawLine(QPointF(x, body.top()), QPointF(x, body.bottom()))
        if note.get("level") is not None:
            p.setPen(QPen(QColor(self.colour(note)), 1.6))
            x = at(note["level"])
            p.drawLine(QPointF(x, body.top()), QPointF(x, body.bottom()))
        # ⚠ 這裡**不要**再印一次面積。第一版把 ``area %d px`` 右對齊在這一格的
        # 上緣，而它緊貼著隔壁那一格的標題 —— 截圖出來讀起來像是「Outline」那
        # 一格的標題，而摘要那一行本來就已經寫了同一句話。
        # （第一版還有一個更糟的：它是**無條件**印的，所以量不到的那一顆上面
        #  寫著「area 0 px」，而 0 是一個看起來很像答案的答案 —— 這張卡的
        #  規矩 3，截圖時才看到自己犯了它。）

    def _paint_outline(self, p: QPainter, rect: QRectF, note: Dict[str, Any],
                       caption: str = "Outline") -> None:
        """那一團的輪廓與最長的弦 —— 面板上這一格回答「形狀長什麼樣」。

        座標是**整張影像**的正規化座標，所以這裡先縮到輪廓自己的框上；
        **等比例**縮（不要拉伸），不然一條細棒會被畫成一團圓的。
        """
        body = self._caption(p, rect, caption)
        pts = [(float(x), float(y)) for x, y in (note.get("outline") or [])]
        if len(pts) < 3 or body.height() < 24:
            if body.height() >= 24:
                p.setPen(QColor(TOKENS["text_disabled"]))
                p.drawText(body, Qt.AlignCenter | Qt.TextWordWrap,
                           "nothing was outlined here")
            return
        xs = [x for x, _y in pts]
        ys = [y for _x, y in pts]
        w = max(1e-9, max(xs) - min(xs))
        h = max(1e-9, max(ys) - min(ys))
        scale = min((body.width() - 6.0) / w, (body.height() - 6.0) / h)
        ox = body.center().x() - (min(xs) + w / 2.0) * scale
        oy = body.center().y() - (min(ys) + h / 2.0) * scale

        def at(pt) -> QPointF:
            return QPointF(ox + pt[0] * scale, oy + pt[1] * scale)

        fill = QColor(self.colour(note))
        fill.setAlpha(60)
        p.setPen(QPen(QColor(self.colour(note)), 1.3))
        p.setBrush(QBrush(fill))
        p.drawPolygon(QPolygonF([at(pt) for pt in pts]))
        p.setBrush(Qt.NoBrush)
        chord = [(float(x), float(y)) for x, y in (note.get("chord") or [])]
        if len(chord) == 2:
            p.setPen(QPen(QColor(self.colour(note)), 1.6))
            p.drawLine(at(chord[0]), at(chord[1]))

    def _paint_batch(self, p: QPainter, rect: QRectF, note: Dict[str, Any],
                     name: str = "cd_median",
                     caption: str = "Across the batch") -> None:
        """整批的分布 ＋ 這一顆在哪 —— 跑過才有東西（同 `MeasureInspector`）。

        ``name`` 是裸的 base；完整特徵名查卡片寫在 note 裡的
        ``feature_names``（`cd.py` 在**組名字的同一個迴圈**記的，PR-3）——
        面板不再自己把 prefix 拼回去。舊 meta 沒有那張表就退回裸 base。
        """
        name = str((note.get("feature_names") or {}).get(name) or name)
        values = self.feature_values(name)
        # 右邊留一點：分布是雙峰的時候最右邊那一根會貼著外框，讀起來像被切掉。
        body = self._caption(p, QRectF(rect.left(), rect.top(),
                                       max(10.0, rect.width() - 4.0),
                                       rect.height()), caption)
        if len(values) < 3 or body.height() < 24:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(body, Qt.AlignCenter | Qt.TextWordWrap,
                       "run a trial to compare this defect with the rest")
            return
        lo, hi = min(values), max(values)
        span = (hi - lo) or 1.0
        # 三格裡只有這一格沒說過自己的軸跨多少 —— 而「這一顆在整批的哪裡」
        # 沒有尺就只是一條線的位置。
        plot = QRectF(body.left(), body.top(), body.width(),
                      body.height() - self.SCALE_ROW)
        bins = [0] * 20
        for v in values:
            bins[min(19, int((v - lo) / span * 19.999))] += 1
        peak = max(bins) or 1
        bw = plot.width() / 20.0
        p.setPen(Qt.NoPen)
        faint = QColor(self.colour(note))
        faint.setAlpha(110)
        p.setBrush(QBrush(faint))
        for i, c in enumerate(bins):
            h = (c / float(peak)) * plot.height()
            p.drawRect(QRectF(plot.left() + i * bw, plot.bottom() - h,
                              max(1.0, bw - 1.0), h))
        p.setBrush(Qt.NoBrush)
        here = self.this_value(name)
        if here is not None:
            x = plot.left() + ((here - lo) / span) * plot.width()
            p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.6))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(body.left(), body.bottom() - self.SCALE_ROW,
                          body.width(), self.SCALE_ROW),
                   Qt.AlignHCenter | Qt.AlignVCenter,
                   "%.1f - %.1f px  (%d)" % (lo, hi, len(values)))
