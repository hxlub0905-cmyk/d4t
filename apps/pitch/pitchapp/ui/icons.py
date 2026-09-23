# Studio 自繪的按鈕圖示 — 從 widgets.py 搬出來 2026-09-08 (U7).
"""**按鈕上那些圖是畫出來的，不是圖檔** —— 這一份就是畫它們的地方。

為什麼搬出來
------------
`CLAUDE.md` §4 早就指名了：「切 `widgets.py` 那幾群自繪圖示最好拆、風險最低」。
那句話的前置條件（黃金值三份全綠）2026-08-23 就成立了，而 F90 那把規模的尺
2026-09-08 把 `widgets.py` 凍在 7,140 行 —— 24 個不相干的類別擠在一支。

這一刀是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。

⚠ **兩族圖，兩個家。** 這裡是**按鈕**上的圖（`GLYPH_ICONS`，一顆鈕一張）；
設定區那些**膠囊**上的圖住在 `ui/glyphs.py`（F68 第二輪，五十幾張）。
兩族由 :data:`GLYPH_ICONS` 那張表接起來，所以呼叫端只認得一個名字。

⚠ **顏色不寫死**：`_paint_glyph` 取的是 **widget 自己的 palette**，而那是 Qt
從 QSS 解析出來的 —— 換膚、變灰全部自動跟著。
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF,
)
from PySide6.QtWidgets import QPushButton, QWidget

from . import glyphs
from . import theme

__all__ = [
    "GLYPH_ICONS", "METRIC_GLYPHS", "draw_glyph_icon", "draw_metric_glyph",
    "IconButton", "GlyphButton", "restyle", "apply_button_cursors",
]




#: 按鈕上畫得出來的圖示（F7-23 第四輪）。名字是**這顆鈕在做什麼**，
#: 不是它長什麼樣 —— 呼叫端說 ``"fit"``，不說「兩端帶箭頭的斜線」。
GLYPH_ICONS = (
    "undo", "redo", "theme", "prev", "next", "play", "chevron_down",
    "zoom_in", "zoom_out", "fit", "tidy", "up", "down", "close",
    # 工具列那五顆（F7-24）＋ 沒有 KLARF 的入口（F11 Input-2／Input-3）
    "folder", "document", "save", "templates", "export", "stack",
    "folder_open", "layers",
    # ⚠ ``stack``（F11）與 ``raw``（F113）**目前沒有人用**：2026-09-18 那一輪
    # `Open stack…` 拿掉、`Open raw…` 併進 `Open images…`。留著是因為畫一個
    # 字形的成本在「想清楚它跟隔壁那顆怎麼分辨」，不在那幾行 —— 而底下
    # ``folder_stack`` 的說明正是拿這兩個當對照。要再開一個入口時它們就在。
    "raw",
    # F110：DOE 那個入口（`Open conditions…`）—— **資料夾裡還有資料夾**。
    # 三顆 Open 並排，所以它的輪廓要跟另外兩顆都不一樣：它是唯一畫成
    # 「一個資料夾裝著兩個小資料夾」的。
    "folder_stack",
    # F85：**一張大圖**。現在是 `welcome.py` 在用（入口那邊 2026-09-18 併掉了）。
    # 唯一內部有東西的那一個 —— 外框空的話它跟 `stack` 的最上層一樣。
    "image",
    # F85：`Write charts` 的「profile 沿哪一個軸」。兩顆並排，差別是
    # **箭頭的方向**，而底下那條軸線相同 —— 那是它們是同一個問題的兩個答案。
    "axis_x", "axis_y",
    # 畫布彈出視窗（F8-UI D 案）
    "popout",
    # 在 Golden Cell 上標區域的四支工具（F11 Region-1 第二輪）。名字說的是
    # **這支工具怎麼產生框**，四個輪廓刻意各不相同 —— 它們並排在同一列上，
    # 分不出來的話那一列等於四顆一樣的鈕。
    "roi_drag", "roi_click", "roi_array", "roi_paint", "roi_cursor",
    "trash",
    # 對齊（F11 Region-1 第四輪）。六顆並排，所以**基準線的位置**就是它們唯一
    # 的差別 —— 那條線畫粗、被對齊的方塊畫細，一眼看得出誰對到誰。
    "align_left", "align_center", "align_right",
    "align_top", "align_middle", "align_bottom",
    # Profile 卡的三個下拉改成圖示（F11 Region-2）。每一個都是**一張小小的
    # 版圖**：兩根直條紋 × 一條橫條紋，把那個選項會放框的地方點亮。使用者的話
    # 是「能用圖就用圖」—— 而 `beside_vertical` 這種詞講的正好就是一個形狀。
    "place_crossing", "place_beside_v", "place_beside_h",
    "place_between_v", "place_between_h",
    "side_both", "side_start", "side_end",
    "fill_fill", "fill_skip", "fill_skip_clear",
    # 「這張圖的圖案往哪個方向跑」（F11 Region-2c）—— 同一套小版圖，
    # 亮的是**在看的那個方向**。
    "dir_both", "dir_upright", "dir_flat",
    # 「要量的是亮的那條還是暗的那條」（F19）。同一套小版圖，**實心的那一條就是
    # 要量的那一條** —— 這個問題問的是樣品，而樣品長什麼樣正好畫得出來。
    "target_auto", "target_bright", "target_dark",
    # 「量的是一條線還是一團東西」（F19 第二批）。這兩顆**不是**同一套小版圖：
    # 它們畫的就是那兩種樣品本身，而那正是這個岔路在問的事。
    "shape_line", "shape_blob",
    # Pitch helper 的工具列（F120）。四顆都是「這顆鈕在做什麼」，不是它長什麼
    # 樣 —— 而四顆並排，所以輪廓要各不相同：
    #   `paste`  一塊夾板（上緣一個夾子）   `copy`  兩張疊著的紙
    #   `crop`   兩支交錯的直角尺           `ruler` 一把帶刻度的尺
    # ⚠ `ruler` 是**斜的**：另外三顆都是正的方塊，而一把斜放的尺在一排小圖示
    # 裡是唯一一個對角線的輪廓 —— 16 px 下那是最容易認出來的差別。
    "paste", "copy", "crop", "ruler",
# ⚠ 上面這一族是**按鈕**上的圖；設定區那些**膠囊**上的圖住在 `ui/glyphs.py`
# （F68 第二輪，五十幾張 —— 塞回這裡只會讓這個檔案更難動，而 CLAUDE.md §4
# 早就指名這幾群自繪圖示最好拆）。兩族由這張表接起來，所以呼叫端（與那條
# 「每一顆都要畫得出東西」的測試）只認得 `GLYPH_ICONS` 一個名字。
) + glyphs.CHIP_ICONS


def draw_glyph_icon(p: QPainter, name: str, size: float, color: str,
                    dark: bool = False) -> None:
    """在 ``p`` 的目前原點畫一個 ``size`` × ``size`` 的按鈕圖示。

    為什麼不用字元（F7-23 第四輪）
    ------------------------------
    這些位置本來放的是 ``↶ ↷ ◐ ◀ ▶ − + ⤢ ⌗ ↑ ↓ ✕ ▾``。問題不是它們醜，是
    **廠內機器是 Windows，而 Segoe UI 蓋不到其中好幾個**（``⤢`` U+2922、
    ``⌗`` U+2317、``↶↷`` U+21B6/B7 都要退到 Segoe UI Symbol）。退字型的結果是
    同一排按鈕裡每顆字的大小與 baseline 都不一樣，最壞是豆腐框 —— 而**我們在
    這裡看不到**（開發機不是那台）。

    這跟 :func:`draw_group_icon` 是同一條路，理由也一樣：repo 只放純文字檔
    （見 ``docs/HANDOVER.md`` §5），而用 QPainter 連「要不要把圖檔加進版控」
    這個問題都不用問，顏色還直接吃呼叫端給的值（所以換膚、變灰全部自動跟著）。

    ``dark`` 只有 ``theme`` 這一顆用得到：主題鈕以前不管在哪個主題都是同一個
    ``◐``，看不出**現在是哪一個**、也看不出按下去會變成什麼。
    """
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), max(1.2, size / 9.0))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    w = h = float(size)
    m = w / 6.0
    n = str(name)

    def triangle(points):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

    if n in ("undo", "redo"):
        # 一個 U 形迴轉 + 箭頭。redo 是把 undo **左右翻過來**畫的，兩顆因此
        # 永遠對稱 —— 分開手繪的話遲早會差一兩個畫素，而它們就並排放著。
        #
        # 15px 下線要細（``size/11``）：原本用 ``size/9`` 的弧糊成一塊，
        # 看起來像個實心的月牙而不是一支箭。
        if n == "redo":
            p.translate(w, 0.0)
            p.scale(-1.0, 1.0)
        thin = QPen(QColor(color), max(1.1, size / 11.0))
        thin.setCapStyle(Qt.RoundCap)
        thin.setJoinStyle(Qt.RoundJoin)
        p.setPen(thin)
        box = QRectF(m, h * 0.26, w - 2 * m, h * 0.44)
        p.drawArc(box, 0, 180 * 16)                 # 上半圈
        left = QPointF(box.left(), box.center().y())
        p.drawLine(QPointF(box.right(), box.center().y()),
                   QPointF(box.right(), h - m))     # 右邊的尾巴
        a = w * 0.15
        p.drawLine(left, QPointF(left.x() - a * 0.8, left.y() - a))
        p.drawLine(left, QPointF(left.x() + a * 0.8, left.y() - a))
        p.setPen(pen)
        if n == "redo":
            p.scale(-1.0, 1.0)
            p.translate(-w, 0.0)
    elif n == "theme":
        # 半實心圓。**實心的那一半跟著目前的主題翻面** —— 不然這顆鈕在兩個
        # 主題下長得一模一樣，等於沒有回答「現在是哪一個」。
        box = QRectF(m, m, w - 2 * m, h - 2 * m)
        p.drawEllipse(box)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawPie(box, (90 if dark else -90) * 16, 180 * 16)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
    elif n in ("prev", "next", "play"):
        cx, cy = w / 2, h / 2
        a = w * (0.26 if n == "play" else 0.24)
        b = h * 0.30
        if n == "prev":
            triangle(((cx + a, cy - b), (cx + a, cy + b), (cx - a, cy)))
        else:
            triangle(((cx - a, cy - b), (cx - a, cy + b), (cx + a, cy)))
    elif n in ("up", "down", "chevron_down"):
        cx = w / 2
        a = w * 0.26
        top, bot = h * 0.40, h * 0.62
        if n == "up":
            p.drawLine(QPointF(cx - a, bot), QPointF(cx, top))
            p.drawLine(QPointF(cx + a, bot), QPointF(cx, top))
        else:
            p.drawLine(QPointF(cx - a, top), QPointF(cx, bot))
            p.drawLine(QPointF(cx + a, top), QPointF(cx, bot))
    elif n == "close":
        p.drawLine(QPointF(m, m), QPointF(w - m, h - m))
        p.drawLine(QPointF(w - m, m), QPointF(m, h - m))
    elif n in ("zoom_in", "zoom_out"):
        p.drawLine(QPointF(m, h / 2), QPointF(w - m, h / 2))
        if n == "zoom_in":
            p.drawLine(QPointF(w / 2, m), QPointF(w / 2, h - m))
    elif n == "fit":
        # 四個角的取景括號 —— 比原本的 ``⤢`` 更說得出「整個看得完」，
        # 而且跟 Region 卡的圖示是同一種語言（``draw_group_icon`` 的 region）。
        # 括號要**短**：0.26 的長度在 15px 下兩隻手臂幾乎接起來，看起來就是一個
        # 缺了幾格的矩形，不是四個角。
        c = w * 0.17
        for x0, y0, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1),
                               (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            p.drawLine(QPointF(x0, y0), QPointF(x0 + c * dx, y0))
            p.drawLine(QPointF(x0, y0), QPointF(x0, y0 + c * dy))
    elif n == "tidy":
        # 2×2 的方格：「把卡片排回格線上」。**實心**的 —— 描邊版在 15px 下
        # 線比方格中間的空隙還粗，四個框糊成一團。
        side = (w - 2 * m) * 0.40
        gap = (w - 2 * m) - 2 * side
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        for i in (0, 1):
            for j in (0, 1):
                p.drawRect(QRectF(m + i * (side + gap), m + j * (side + gap),
                                  side, side))
    elif n == "popout":
        # 左下一個小框 + 往右上飛的箭頭：「在自己的視窗打開」。兩筆都粗、
        # 都直 —— 15px 下任何斜的小箭頭頭都會糊，所以箭頭頭用兩條短直線。
        box_side = (w - 2 * m) * 0.62
        p.drawRect(QRectF(m, h - m - box_side, box_side, box_side))
        ax0 = m + box_side * 0.55
        ay0 = h - m - box_side * 0.55
        ax1, ay1 = w - m, m
        p.drawLine(QPointF(ax0, ay0), QPointF(ax1, ay1))
        head = (w - 2 * m) * 0.38
        p.drawLine(QPointF(ax1, ay1), QPointF(ax1 - head, ay1))
        p.drawLine(QPointF(ax1, ay1), QPointF(ax1, ay1 + head))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
    elif n == "shape_line":
        # 一條有方向的帶子，加兩個箭頭說「量的是橫過去的那一段」。
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawRect(QRectF(w * 0.36, m, w * 0.28, h - 2 * m))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        y = h * 0.5
        p.drawLine(QPointF(m, y), QPointF(w - m, y))
        a = w * 0.10
        for x, d in ((m, 1), (w - m, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + a * d, y - a * 0.8))
            p.drawLine(QPointF(x, y), QPointF(x + a * d, y + a * 0.8))
    elif n == "shape_blob":
        # 一團沒有方向的東西。**刻意不是圓** —— 圓看起來像一個按鈕，而這顆要
        # 說的正是「形狀不規則」。
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        blob = QPolygonF([
            QPointF(w * 0.30, h * 0.16), QPointF(w * 0.66, h * 0.10),
            QPointF(w * 0.86, h * 0.36), QPointF(w * 0.78, h * 0.70),
            QPointF(w * 0.48, h * 0.88), QPointF(w * 0.16, h * 0.66),
            QPointF(w * 0.12, h * 0.34)])
        p.drawPolygon(blob)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
    elif n == "paste":
        # 一塊夾板：外框 ＋ 上緣一個夾子。跟 `document`（一張紙、右上折角）
        # 的差別就在那個夾子 —— 兩顆都是「一個長方形」，而那是唯一的區別。
        p.drawRect(QRectF(m, h * 0.24, w - 2 * m, h - h * 0.24 - m))
        p.drawRect(QRectF(w * 0.36, h * 0.12, w * 0.28, h * 0.16))
    elif n == "copy":
        # 兩張紙錯開疊著 —— 「同一個東西多了一份」，而那正是複製。
        p.drawRect(QRectF(m, m, w * 0.52, h * 0.52))
        p.drawRect(QRectF(w * 0.32, h * 0.32, w * 0.52, h * 0.52))
    elif n == "crop":
        # 兩支交錯的直角尺（攝影上的裁切記號）：它們圍出來的那一塊就是留下來
        # 的。⚠ 不畫成「一個框」—— 那會跟 `roi_drag` 撞，而那一顆是畫區域的。
        p.drawPolyline(QPolygonF([
            QPointF(w * 0.28, m), QPointF(w * 0.28, h - m * 1.4),
            QPointF(w - m, h - m * 1.4)]))
        p.drawPolyline(QPolygonF([
            QPointF(m, w * 0.28), QPointF(h - m * 1.4, w * 0.28),
            QPointF(h - m * 1.4, w - m)]))
    elif n == "ruler":
        # 一把斜放的尺：長邊 ＋ 三道刻度。**斜的**是刻意的（見 GLYPH_ICONS 的
        # 說明）—— 這一排裡唯一的對角線輪廓。
        p.save()
        p.translate(w * 0.5, h * 0.5)
        p.rotate(-38.0)
        p.translate(-w * 0.5, -h * 0.5)
        body = QRectF(m * 0.4, h * 0.36, w - m * 0.8, h * 0.28)
        p.drawRect(body)
        thin = QPen(QColor(color), max(1.0, size / 12.0))
        thin.setCapStyle(Qt.RoundCap)
        p.setPen(thin)
        for f in (0.3, 0.5, 0.7):
            x = body.left() + body.width() * f
            p.drawLine(QPointF(x, body.top()),
                       QPointF(x, body.top() + body.height() * 0.5))
        p.setPen(pen)
        p.restore()
    elif n.startswith(("place_", "side_", "fill_", "dir_", "target_")):
        _draw_profile_glyph(p, n, w, h, color, pen)
    elif n in glyphs.CHIP_ICONS:
        glyphs.draw_chip_icon(p, n, w, color)
    elif n == "roi_cursor":
        # 一支箭頭游標：**選**已經有的框（不是畫新的）。
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([
            QPointF(m, m), QPointF(m, h - m * 1.2),
            QPointF(m + w * 0.24, h - m * 2.2),
            QPointF(m + w * 0.40, h - m * 0.4),
            QPointF(m + w * 0.56, h - m * 0.9),
            QPointF(m + w * 0.40, h * 0.58), QPointF(w - m * 1.4, h * 0.52)]))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
    elif n == "trash":
        # 垃圾桶：桶身 + 蓋子 + 提把。**不用 ✕** —— 這一列上 ✕ 是「關閉」。
        p.drawLine(QPointF(m, h * 0.30), QPointF(w - m, h * 0.30))
        p.drawLine(QPointF(w * 0.40, h * 0.30), QPointF(w * 0.40, h * 0.18))
        p.drawLine(QPointF(w * 0.60, h * 0.30), QPointF(w * 0.60, h * 0.18))
        p.drawLine(QPointF(w * 0.40, h * 0.18), QPointF(w * 0.60, h * 0.18))
        p.drawLine(QPointF(m + w * 0.10, h * 0.30),
                   QPointF(m + w * 0.16, h - m))
        p.drawLine(QPointF(w - m - w * 0.10, h * 0.30),
                   QPointF(w - m - w * 0.16, h - m))
        p.drawLine(QPointF(m + w * 0.16, h - m), QPointF(w - m - w * 0.16, h - m))
    elif n.startswith("align_"):
        # 一條粗的基準線 + 兩個對到它的方塊。六顆的差別只有線在哪一邊。
        side = n[len("align_"):]
        vertical = side in ("left", "center", "right")
        rule = QPen(QColor(color), max(1.6, size / 7.0))
        rule.setCapStyle(Qt.RoundCap)
        bars = ((w * 0.62, h * 0.20), (w * 0.38, h * 0.20))    # (長, 厚)
        if vertical:
            lx = {"left": m, "center": w / 2.0, "right": w - m}[side]
            p.setPen(rule)
            p.drawLine(QPointF(lx, m * 0.7), QPointF(lx, h - m * 0.7))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            for i, (blen, bthk) in enumerate(bars):
                y0 = h * (0.30 if i == 0 else 0.58)
                x0 = {"left": lx, "center": lx - blen / 2.0,
                      "right": lx - blen}[side]
                p.drawRect(QRectF(x0, y0, blen, bthk))
        else:
            ly = {"top": m, "middle": h / 2.0, "bottom": h - m}[side]
            p.setPen(rule)
            p.drawLine(QPointF(m * 0.7, ly), QPointF(w - m * 0.7, ly))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            for i, (blen, bthk) in enumerate(bars):
                x0 = w * (0.30 if i == 0 else 0.58)
                y0 = {"top": ly, "middle": ly - blen / 2.0,
                      "bottom": ly - blen}[side]
                p.drawRect(QRectF(x0, y0, bthk, blen))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
    elif n == "roi_drag":
        # 一個虛線框 + 右下角的游標：**拉出來的**框。
        p.setPen(QPen(QColor(color), max(1.1, size / 11.0), Qt.DashLine))
        p.drawRect(QRectF(m, m, (w - 2 * m) * 0.72, (h - 2 * m) * 0.72))
        p.setPen(pen)
        tip = QPointF(m + (w - 2 * m) * 0.72, m + (h - 2 * m) * 0.72)
        p.drawLine(tip, QPointF(tip.x() + w * 0.16, tip.y() + h * 0.16))
    elif n == "roi_click":
        # 一個實框 + 中心的十字：**點一下，框長在游標中心**。
        box = QRectF(m, h * 0.24, w - 2 * m, h * 0.52)
        p.drawRect(box)
        c = box.center()
        a = w * 0.13
        p.drawLine(QPointF(c.x() - a, c.y()), QPointF(c.x() + a, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - a), QPointF(c.x(), c.y() + a))
    elif n == "roi_array":
        # 一排三個等距的框：**一次長一整排**。跟 ``roi_click`` 的差別就是
        # 「一個」與「一排」，那正是兩支工具的差別。
        side = (w - 2 * m) * 0.22
        gap = ((w - 2 * m) - 3 * side) / 2.0
        for i in range(3):
            p.drawRect(QRectF(m + i * (side + gap), h * 0.28, side, h * 0.44))
    elif n == "roi_paint":
        # 幾格點亮的方格：**一顆一顆點像素**。用實心小方塊而不是筆刷 ——
        # 畫出來的東西是像素，不是筆觸。
        side = (w - 2 * m) / 3.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        for i, j in ((0, 1), (1, 0), (1, 1), (2, 1), (1, 2)):
            p.drawRect(QRectF(m + i * side + side * 0.12,
                              m + j * side + side * 0.12,
                              side * 0.76, side * 0.76))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
    elif n in ("axis_x", "axis_y"):
        # 一條軸 ＋ 一個往那個方向的箭頭。兩顆並排時唯一的差別是方向，
        # 所以軸線本身刻意一模一樣（換了長相的話，使用者要比對兩件事）。
        if n == "axis_x":
            a, b = QPointF(m, h * 0.72), QPointF(w - m, h * 0.72)
            tip = (QPointF(w - m - w * 0.16, h * 0.72 - h * 0.12),
                   QPointF(w - m - w * 0.16, h * 0.72 + h * 0.12))
        else:
            a, b = QPointF(w * 0.28, h - m), QPointF(w * 0.28, m)
            tip = (QPointF(w * 0.28 - w * 0.12, m + h * 0.16),
                   QPointF(w * 0.28 + w * 0.12, m + h * 0.16))
        p.drawLine(a, b)
        p.drawLine(b, tip[0])
        p.drawLine(b, tip[1])
    elif n == "image":
        # 一張圖：外框 + 裡面一道山稜和一顆太陽（F85 Input-6）。
        # 四顆 Open 鈕的輪廓要各不相同（F7-24 的同一條）—— ``folder`` 與
        # ``folder_open`` 上緣有頁籤、``stack`` 是三個錯開的方框，
        # 這一個是**唯一內部有東西的**：外框空的話它跟 stack 的最上層一樣。
        p.drawRect(QRectF(m, h * 0.22, w - 2 * m, h * 0.56))
        p.drawPolyline(QPolygonF([
            QPointF(m + w * 0.06, h * 0.66),
            QPointF(w * 0.42, h * 0.40),
            QPointF(w - m - w * 0.06, h * 0.66)]))
        p.drawEllipse(QPointF(w * 0.68, h * 0.36), w * 0.06, w * 0.06)
    elif n == "folder":
        p.drawLine(QPointF(m, h * 0.30), QPointF(w * 0.44, h * 0.30))
        p.drawLine(QPointF(w * 0.44, h * 0.30), QPointF(w * 0.54, h * 0.42))
        p.drawRect(QRectF(m, h * 0.42, w - 2 * m, h * 0.42))
    elif n == "folder_open":
        # 打開的資料夾：後片是方的、前片往外斜。跟 ``folder``（關著的）並排時
        # 差別在**前片的斜邊** —— 每顆 Open 鈕的輪廓要各不相同（F7-24）。
        p.drawLine(QPointF(m, h * 0.32), QPointF(w * 0.44, h * 0.32))
        p.drawLine(QPointF(w * 0.44, h * 0.32), QPointF(w * 0.54, h * 0.44))
        p.drawLine(QPointF(m, h * 0.32), QPointF(m, h * 0.80))
        p.drawLine(QPointF(w * 0.54, h * 0.44), QPointF(w - m, h * 0.44))
        # 前片：從左下往右斜出去
        p.drawLine(QPointF(m, h * 0.80), QPointF(w - m * 0.6, h * 0.80))
        p.drawLine(QPointF(w - m, h * 0.44), QPointF(w - m * 0.6, h * 0.80))
    elif n == "raw":
        # 一格一格的裸資料：外框 + 裡面一片棋盤格 —— 唯一畫成「格子」的那一個。
        p.drawRect(QRectF(m, h * 0.20, w - 2 * m, h * 0.60))
        cw = (w - 2 * m) / 4.0
        ch = h * 0.60 / 3.0
        for r in range(3):
            for c in range(4):
                if (r + c) % 2:
                    continue
                p.fillRect(QRectF(m + c * cw, h * 0.20 + r * ch, cw, ch),
                           p.pen().color())
    elif n == "folder_stack":
        # 一個資料夾裝著兩個小資料夾 —— DOE：一個子目錄一顆、裡面是 condition。
        # 跟 ``folder``／``folder_open`` 的差別是**裡面有東西**，跟 ``stack``
        # 的差別是**外面有容器**（stack 是同一個東西的好幾層）。
        p.drawLine(QPointF(m, h * 0.26), QPointF(w * 0.40, h * 0.26))
        p.drawLine(QPointF(w * 0.40, h * 0.26), QPointF(w * 0.50, h * 0.38))
        p.drawRect(QRectF(m, h * 0.38, w - 2 * m, h * 0.46))
        inner = (w - 2 * m) * 0.34
        for x in (m + (w - 2 * m) * 0.10, m + (w - 2 * m) * 0.54):
            p.drawRect(QRectF(x, h * 0.52, inner, h * 0.22))
    elif n == "stack":
        # 三張疊起來的紙 —— 「一個檔案裡有好幾張圖」（F11 Input-2）。
        # 跟 ``folder`` 對比得出來：folder 是容器，stack 是**同一個東西的好幾層**。
        step = h * 0.16
        side = w - 2 * m - step * 2
        for i in (2, 1, 0):
            p.drawRect(QRectF(m + step * i, m + step * (2 - i), side, side))
    elif n == "layers":
        # 三片**平放**的層 —— GDS 的 layout label map（F11 Region-3）。
        #
        # 跟 ``stack`` 要分得出來，而它們講的東西其實很近（都是「好幾層」）：
        # ``stack`` 是三個**正面**的方框（同一張圖的好幾頁），``layers`` 是三個
        # **側看**的菱形（疊在一起的版圖層）。差別落在輪廓的長寬比上 ——
        # 15px 下方框是方的、菱形是扁的，一眼分得出來。
        for i in range(3):
            cy = m + h * 0.16 + (h - 2 * m - h * 0.32) * i / 2.0
            p.drawPolygon(QPolygonF([
                QPointF(w / 2, cy - h * 0.14), QPointF(w - m, cy),
                QPointF(w / 2, cy + h * 0.14), QPointF(m, cy)]))
    elif n == "document":
        fold = w * 0.26
        p.drawLine(QPointF(m + w * 0.06, m), QPointF(w - m - fold, m))
        p.drawLine(QPointF(w - m - fold, m), QPointF(w - m - w * 0.06, m + fold))
        p.drawLine(QPointF(w - m - w * 0.06, m + fold),
                   QPointF(w - m - w * 0.06, h - m))
        p.drawLine(QPointF(w - m - w * 0.06, h - m), QPointF(m + w * 0.06, h - m))
        p.drawLine(QPointF(m + w * 0.06, h - m), QPointF(m + w * 0.06, m))
    elif n in ("save", "export"):
        # 一對：``save`` 是箭頭**進**托盤（存到磁碟），``export`` 是箭頭**出**
        # 托盤（送出去）。方向相反，形狀一樣 —— 兩顆並排時對比得出來。
        tray_y = h - m
        p.drawLine(QPointF(m, tray_y - h * 0.12), QPointF(m, tray_y))
        p.drawLine(QPointF(m, tray_y), QPointF(w - m, tray_y))
        p.drawLine(QPointF(w - m, tray_y), QPointF(w - m, tray_y - h * 0.12))
        a = w * 0.17
        if n == "save":
            tip = QPointF(w / 2, h * 0.62)
            p.drawLine(QPointF(w / 2, m), tip)
            p.drawLine(tip, QPointF(w / 2 - a, tip.y() - a))
            p.drawLine(tip, QPointF(w / 2 + a, tip.y() - a))
        else:
            tip = QPointF(w / 2, m)
            p.drawLine(QPointF(w / 2, h * 0.62), tip)
            p.drawLine(tip, QPointF(w / 2 - a, tip.y() + a))
            p.drawLine(tip, QPointF(w / 2 + a, tip.y() + a))
    elif n == "templates":
        # 一疊卡：範本庫是**一堆現成的 pipeline**，不是一張圖。
        #
        # 第一版畫成「外框 + 三條橫線」，在 15px 下三條線的間距比線本身還細，
        # 整個糊成一塊實心格子，而且跟 ``document`` 太像。
        off = w * 0.17
        p.drawLine(QPointF(m + off, m), QPointF(w - m, m))
        p.drawLine(QPointF(w - m, m), QPointF(w - m, h - m - off))
        p.drawRect(QRectF(m, m + off, w - 2 * m - off, h - 2 * m - off))
    else:
        raise ValueError("unknown icon: %r (known: %s)"
                         % (name, ", ".join(GLYPH_ICONS)))


def _draw_profile_glyph(p: QPainter, name: str, w: float, h: float,
                        color: str, pen: QPen) -> None:
    """Profile 卡那三個下拉的圖示：一張小版圖，把會放框的地方點亮。

    共用的畫法：**條紋畫成淡的底**（它們是背景 —— 「哪裡有材質」），
    **框畫成實心的亮塊**（那才是這個選項在講的東西）。十一顆並排時唯一的差別
    就是亮塊在哪，而那正好就是這些選項唯一的差別。

    ⚠ **這些圖要在 21 px 下讀得出來。** 第一版畫得很細（薄框 ``w*0.07`` ＝
    1.5 px、兩根直條紋加一條橫帶），render 出來五個 ``place`` 幾乎一模一樣 ——
    在這個尺寸下，「精確」跟「看得懂」是衝突的，而看得懂才是這一輪的目標。
    所以每一塊都不小於邊長的 1/5，細節能砍就砍。
    """
    faint = QColor(color)
    faint.setAlpha(58)
    solid = QColor(color)

    def blk(x0, y0, x1, y1, on):
        p.setPen(Qt.NoPen)
        p.setBrush(solid if on else faint)
        p.drawRect(QRectF(x0 * w, y0 * h, (x1 - x0) * w, (y1 - y0) * h))

    if name.startswith("place_"):
        if name == "place_crossing":
            blk(0.34, 0.05, 0.66, 0.95, False)          # 直的
            blk(0.05, 0.34, 0.95, 0.66, False)          # 橫的
            blk(0.34, 0.34, 0.66, 0.66, True)           # 交會處
        elif name == "place_beside_v":
            blk(0.40, 0.05, 0.60, 0.95, False)
            blk(0.14, 0.30, 0.36, 0.70, True)
            blk(0.64, 0.30, 0.86, 0.70, True)
        elif name == "place_beside_h":
            blk(0.05, 0.40, 0.95, 0.60, False)
            blk(0.30, 0.14, 0.70, 0.36, True)
            blk(0.30, 0.64, 0.70, 0.86, True)
        elif name == "place_between_v":
            blk(0.06, 0.05, 0.26, 0.95, False)
            blk(0.74, 0.05, 0.94, 0.95, False)
            blk(0.32, 0.05, 0.68, 0.95, True)
        else:                                            # between_horizontal
            blk(0.05, 0.06, 0.95, 0.26, False)
            blk(0.05, 0.74, 0.95, 0.94, False)
            blk(0.05, 0.32, 0.95, 0.68, True)
    elif name.startswith("dir_"):
        # 這一組畫的是**條紋本身**（不是框）：亮的那一組就是「在看的」。
        # 所以 `dir_both` 是兩組都亮、單向的那兩顆有一組退成淡的 ——
        # 淡的那一組還在，因為「另一個方向我不看」跟「另一個方向不存在」
        # 是兩件事，而使用者要挑的正是前者。
        up = name in ("dir_both", "dir_upright")
        flat = name in ("dir_both", "dir_flat")
        bars = [((0.08, 0.05, 0.30, 0.95), up), ((0.70, 0.05, 0.92, 0.95), up),
                ((0.05, 0.08, 0.95, 0.30), flat), ((0.05, 0.70, 0.95, 0.92), flat)]
        # 淡的先畫：半透明的塊疊在實心的上面會把它糊掉一角，而那一角正好是
        # 兩組交會的地方 —— 也就是這幾顆圖示最該乾淨的位置。
        for rect, on in sorted(bars, key=lambda t: bool(t[1])):
            blk(rect[0], rect[1], rect[2], rect[3], on)
    elif name.startswith("target_"):
        # 三條橫帶，**實心的那一條就是要量的那一條**。
        #
        # 為什麼不是畫一個「亮」跟一個「暗」的方塊：那要求使用者先判斷「畫面上
        # 比較亮的是哪一塊」，而在 21 px 的按鈕上兩塊灰階分不出來。改成「哪一條
        # 被選起來」之後，三顆的差別是**位置**，那在小尺寸下讀得出來。
        if name == "target_bright":
            blk(0.05, 0.06, 0.95, 0.30, False)
            blk(0.05, 0.38, 0.95, 0.62, True)          # 中間那條 = 亮帶
            blk(0.05, 0.70, 0.95, 0.94, False)
        elif name == "target_dark":
            blk(0.05, 0.06, 0.95, 0.30, True)          # 兩側是亮的
            blk(0.05, 0.38, 0.95, 0.62, False)         # 中間那條 = 暗帶
            blk(0.05, 0.70, 0.95, 0.94, True)
        else:                                          # target_auto：兩種都可以
            blk(0.05, 0.06, 0.46, 0.30, False)
            blk(0.05, 0.38, 0.46, 0.62, True)
            blk(0.05, 0.70, 0.46, 0.94, False)
            blk(0.54, 0.06, 0.95, 0.30, True)
            blk(0.54, 0.38, 0.95, 0.62, False)
            blk(0.54, 0.70, 0.95, 0.94, True)
    elif name.startswith("side_"):
        # 跟 place_beside_v 的差別刻意做在**高度**：這裡的塊是滿高的
        blk(0.42, 0.05, 0.58, 0.95, False)
        if name in ("side_both", "side_start"):
            blk(0.18, 0.05, 0.38, 0.95, True)
        if name in ("side_both", "side_end"):
            blk(0.62, 0.05, 0.82, 0.95, True)
    else:
        # 三格，中間那一根**不見了**。畫的是「哪幾格拿得到框」——
        # 那才是這個參數真正在決定的事。
        # 缺的那一格畫成**虛線外框**而不是淡色實心：淡色實心在 21 px 下讀起來
        # 仍然是一根，於是 fill 與 skip 長得一樣（render 出來確認過）。
        def ghost(x0, x1):
            p.setPen(QPen(QColor(color), max(1.0, w / 20.0), Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(x0 * w, 0.06 * h, (x1 - x0) * w, 0.88 * h))

        if name == "fill_fill":
            blk(0.08, 0.05, 0.30, 0.95, True)
            blk(0.39, 0.05, 0.61, 0.95, True)           # 補上去的那一根
            blk(0.70, 0.05, 0.92, 0.95, True)
        elif name == "fill_skip":
            blk(0.08, 0.05, 0.30, 0.95, True)
            ghost(0.39, 0.61)                            # 缺的那一根：沒有框
            blk(0.70, 0.05, 0.92, 0.95, True)
        else:                                            # skip_clear
            # 鄰居**朝向缺口的那半邊**也不要 —— 所以兩根都只剩外側一半
            blk(0.08, 0.05, 0.19, 0.95, True)
            ghost(0.39, 0.61)
            blk(0.81, 0.05, 0.92, 0.95, True)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


#: 統計量的小圖（F18，2026-08-21）。名字是**圖形**的名字，不是 metric id ——
#: `glv_q90` / `glv_q25` / `glv_p50` 是無限多個 id，但它們在分布上標的是同一
#: 件事（一條線切在某個位置），所以共用 ``percentile`` 這張圖。
#: id → 圖的對照住在 :data:`METRIC_GROUPS`。
METRIC_GLYPHS = (
    "median", "mean", "trimmed",
    "mad", "std", "iqr",
    "min", "max", "percentile",
    "skew", "kurtosis", "entropy", "bimodality",
    "above", "saturated",
    # 「再加一顆」那種膠囊用的：它是**動作**不是統計量，所以它不畫分布。
    "plus",
    # 「跟誰比」那一排（F18 補課，2026-08-21 使用者：「Compare 跟 absolute
    # 一樣重要，而且它的面板 UI 沒有 Statistics 那麼漂亮，可以改成切換式」）。
    #
    # 前三個直接畫**那個運算的符號**（Δ / ÷ / %）—— 它們是這三個數字的名字，
    # 識別度比任何示意圖都高，而且跟分布那一族一看就不同族。後兩個畫的是
    # 「差距 ÷ 散布」那個比例本身。
    "delta", "ratio", "percent", "snr", "tstat",
    # F18 補課第二輪（使用者 2026-08-21：「我覺得 Report 要有更多統計量可以
    # 量」）。前兩個仍然畫**運算的符號**（|Δ| / 半黑半白的圓 = 對比），後三個
    # 畫的是它們各自比的東西：名次、兩條分布疊多少、兩段散布誰長。
    "abs_delta", "contrast", "pct_rank", "overlap", "spread_ratio",
    # CD 那張卡的三顆（F19）。第一顆仍然是「淡的是分布、實的是這個統計量」那套
    # 語言；後兩顆**刻意跳出那套** —— LER 講的不是一條分布，是一條邊在抖，而把
    # 它畫成第四張分布圖會讓它跟 ``std`` 在 19 px 下變成同一張圖。
    "range", "ler_a", "ler_b",
    # 團那一支（F19 第二批）。這一族**整族跳出「淡的是分布」那套語言** ——
    # 它們講的是一個形狀的性質，不是一條分布上的一段，所以五顆都畫在同一團
    # 輪廓上，差別在**標出來的是哪一部分**（填滿的內部／一個等面積的圓／最長
    # 的弦／最窄的夾／周長）。
    "area", "deq", "feret_max", "feret_min", "roundness",
)


def _poly_area(poly: "QPolygonF") -> float:
    """多邊形的面積（鞋帶公式）。只給 ``deq`` 那顆圖示畫等面積圓用。"""
    n = poly.count()
    total = 0.0
    for i in range(n):
        a, b = poly.at(i), poly.at((i + 1) % n)
        total += a.x() * b.y() - b.x() * a.y()
    return total / 2.0


def _extreme_pair(pts, longest: bool = True):
    """一組點裡最遠（或最近）的兩個。只給圖示用，所以直接兩兩比。"""
    best = None
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if best is None or (d > best[0] if longest else d < best[0]):
                best = (d, a, b)
    return (best[1], best[2]) if best else ((0.0, 0.0), (0.0, 0.0))


def _blob_outline(pad: float, bw: float, bh: float) -> "QPolygonF":
    """這一族共用的那一團輪廓（0..1 的控制點打到 ``pad``/``bw``/``bh`` 上）。

    **五顆用同一團**：差別要落在「標了哪裡」，而不是「畫了不同的東西」——
    形狀也不一樣的話，眼睛會先去比形狀，那就看不出它們是同一族的了。
    """
    pts = [(0.30, 0.86), (0.66, 0.92), (0.88, 0.62), (0.78, 0.24),
           (0.46, 0.10), (0.14, 0.32), (0.10, 0.66)]
    return QPolygonF([QPointF(pad + x * bw, pad + (1 - y) * bh)
                      for x, y in pts])


def _dist_curve(peak: float = 1.0, twin: bool = False,
                skew: bool = False) -> List[Tuple[float, float]]:
    """一條分布曲線的取樣點（x、y 都是 0..1，y 往上）。"""
    pts: List[Tuple[float, float]] = []
    n = 26
    for i in range(n + 1):
        x = i / float(n)
        if twin:
            y = (math.exp(-((x - 0.28) ** 2) / 0.012)
                 + math.exp(-((x - 0.72) ** 2) / 0.012))
        elif skew:
            t = max(1e-3, x)                      # 對數常態：峰靠左、長尾在右
            y = math.exp(-((math.log(t / 0.30)) ** 2) / 0.26) / t
        else:
            y = math.exp(-((x - 0.5) ** 2) / (0.036 / max(0.35, peak)))
        pts.append((x, y))
    top = max(q[1] for q in pts) or 1.0
    return [(x, min(1.0, y / top)) for x, y in pts]


def draw_metric_glyph(p: QPainter, name: str, size: float, color: str,
                      dim: str) -> None:
    """在 ``p`` 的目前原點畫一個 ``size`` × ``size`` 的統計量圖示。

    共通語言（F18）
    ---------------
    **淡的那條線是分布本身，實的那一筆才是這個統計量在講的東西。**
    十五張圖的差別只在「實的那一筆標在哪」—— 而那正好就是這些統計量彼此唯一
    的差別。使用者因此不需要知道 MAD 的定義：他看得到它在圖上是哪一段。

    為什麼不是純文字的膠囊
    ----------------------
    十六顆一模一樣的膠囊在掃視時沒有錨點：要找「離散」那一群，眼睛只能一個字
    一個字讀過去。小圖給了那個錨點，而且它**教**了一件事 —— 這一段的使用者是
    製程工程師，不是統計學家。

    ⚠ **這些圖要在 19 px 下讀得出來**（膠囊裡就是那個尺寸）。第一版有六顆是
    廢的：``mean`` 只是「``median`` 沒填色」、``trimmed`` 的虛線在那個尺寸下
    整條不見、``skew`` 的箭頭搶戲而不對稱的山根本看不出來、``percentile`` 跟
    ``median`` 幾乎一樣。逐顆 render 出來看過才改成現在這樣，而
    `tests/test_ui_widgets.py` 有一條在 19 px 下兩兩比畫素的測試守著。
    """
    p.setRenderHint(QPainter.Antialiasing, True)
    w = h = float(size)
    pad = w * 0.10
    bw, bh = w - 2 * pad, h - 2 * pad
    faint, solid = QColor(dim), QColor(color)
    thin = QPen(faint, max(1.0, size / 14.0))
    bold = QPen(solid, max(1.3, size / 10.0))
    bold.setCapStyle(Qt.RoundCap)

    def poly_of(pts):
        return QPolygonF([QPointF(pad + x * bw, pad + (1 - y) * bh)
                          for x, y in pts])

    def curve(pts, pen=None):
        p.setPen(pen or thin)
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(poly_of(pts))

    def vline(fx, pen=None):
        p.setPen(pen or bold)
        p.drawLine(QPointF(pad + fx * bw, pad), QPointF(pad + fx * bw, pad + bh))

    def band(fa, fb):
        c = QColor(solid)
        c.setAlpha(80)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.drawRect(QRectF(pad + fa * bw, pad + bh * 0.18,
                          (fb - fa) * bw, bh * 0.82))

    def fill_under(pts, fa, fb):
        pl = [QPointF(pad + fa * bw, pad + bh)]
        pl += [QPointF(pad + x * bw, pad + (1 - y) * bh)
               for x, y in pts if fa <= x <= fb]
        pl.append(QPointF(pad + fb * bw, pad + bh))
        c = QColor(solid)
        c.setAlpha(95)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.drawPolygon(QPolygonF(pl))

    def arrow_span(fa, fb):
        y = pad + bh * 0.86
        p.setPen(bold)
        p.drawLine(QPointF(pad + fa * bw, y), QPointF(pad + fb * bw, y))
        a = w * 0.09
        for fx, d in ((fa, 1), (fb, -1)):
            x = pad + fx * bw
            p.drawLine(QPointF(x, y), QPointF(x + a * d, y - a * 0.8))
            p.drawLine(QPointF(x, y), QPointF(x + a * d, y + a * 0.8))

    n = str(name)
    if n == "median":
        pts = _dist_curve()
        curve(pts)
        fill_under(pts, 0.0, 0.5)            # 一半的面積 —— 中位數的定義
        vline(0.5)
    elif n == "mean":
        curve(_dist_curve())
        p.setPen(bold)                        # 天平：橫桿 + 支點（重心）
        y = pad + bh * 0.70
        p.drawLine(QPointF(pad + 0.10 * bw, y), QPointF(pad + 0.90 * bw, y))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(solid))
        p.drawPolygon(QPolygonF([
            QPointF(pad + 0.50 * bw, y),
            QPointF(pad + 0.50 * bw - w * 0.19, pad + bh),
            QPointF(pad + 0.50 * bw + w * 0.19, pad + bh)]))
    elif n == "trimmed":
        pts = _dist_curve()
        curve(pts)
        fill_under(pts, 0.26, 0.74)           # 只有中段算數
        p.setPen(QPen(solid, max(1.2, size / 11.0)))
        for fx in (0.26, 0.74):               # 兩端被剪掉的地方
            x = pad + fx * bw
            p.drawLine(QPointF(x, pad + bh * 0.10), QPointF(x, pad + bh))
    elif n == "mad":
        curve(_dist_curve())
        band(0.34, 0.66)                      # 中位數兩側的一段：離散度
    elif n == "std":
        curve(_dist_curve())
        arrow_span(0.26, 0.74)
        vline(0.5, QPen(faint, max(1.0, size / 14.0), Qt.DotLine))
    elif n == "iqr":
        curve(_dist_curve())
        p.setPen(bold)                        # 箱形圖的箱子
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(pad + 0.30 * bw, pad + bh * 0.34, 0.40 * bw, bh * 0.42))
        p.drawLine(QPointF(pad + 0.50 * bw, pad + bh * 0.34),
                   QPointF(pad + 0.50 * bw, pad + bh * 0.76))
    elif n in ("min", "max"):
        curve(_dist_curve())
        vline(0.12 if n == "min" else 0.88)   # 差別只有線靠哪一邊
    elif n == "percentile":
        # 一條線切在某個位置，左邊那一塊填起來 = 「這麼多比例的像素比它暗」。
        # 跟 ``median`` 的差別只有線在哪 —— 而中位數正是 P50，所以那個相似
        # 是對的。
        pts = _dist_curve()
        curve(pts)
        fill_under(pts, 0.0, 0.72)
        vline(0.72)
    elif n == "plus":
        # **動作，不是統計量**（「再加一個分位數」），所以不畫分布。
        # 這一顆一定要跟 ``percentile`` 分得開：加出來的那顆膠囊會選著，
        # 而兩顆並排在同一列上。
        p.setPen(QPen(solid, max(1.6, size / 8.0), Qt.SolidLine, Qt.RoundCap))
        cx, cy = pad + bw / 2, pad + bh / 2
        a = bw * 0.30
        p.drawLine(QPointF(cx - a, cy), QPointF(cx + a, cy))
        p.drawLine(QPointF(cx, cy - a), QPointF(cx, cy + a))
    elif n == "skew":
        curve(_dist_curve(skew=True), bold)   # 峰靠左、尾巴拖到右邊
    elif n == "kurtosis":
        curve(_dist_curve(peak=0.35))         # 淡的：矮胖的那一條
        curve(_dist_curve(peak=2.4), bold)    # 實的：尖瘦的那一條
    elif n == "entropy":
        p.setPen(Qt.NoPen)                    # 高低不齊的一排 —— 亂度
        p.setBrush(QBrush(solid))
        hs = (0.35, 0.85, 0.20, 0.65, 0.45, 0.95, 0.30)
        cw = bw / len(hs)
        for i, hh in enumerate(hs):
            p.drawRect(QRectF(pad + i * cw + cw * 0.16, pad + bh * (1 - hh),
                              cw * 0.68, bh * hh))
    elif n == "bimodality":
        curve(_dist_curve(twin=True))
        p.setPen(bold)                        # 中間的谷 —— 兩種材質的界線
        p.drawLine(QPointF(pad + 0.5 * bw, pad + bh * 0.30),
                   QPointF(pad + 0.5 * bw, pad + bh))
    elif n == "above":
        pts = _dist_curve()
        curve(pts)
        fill_under(pts, 0.58, 1.0)            # 門檻**右邊**那一塊
        # 虛線 = 這條線可以自己調（``glv_above<NN>``）。
        vline(0.58, QPen(solid, max(1.2, size / 11.0), Qt.DashLine))
    elif n == "delta":
        # Δ —— 兩塊的差。實心三角形，19 px 下比描邊清楚。
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(solid))
        p.drawPolygon(QPolygonF([
            QPointF(pad + bw / 2, pad + bh * 0.06),
            QPointF(pad + bw * 0.06, pad + bh * 0.94),
            QPointF(pad + bw * 0.94, pad + bh * 0.94)]))
    elif n == "ratio":
        # ÷ —— 一條橫線加上下兩點。
        p.setPen(QPen(solid, max(1.5, size / 9.0), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(pad + bw * 0.08, pad + bh / 2),
                   QPointF(pad + bw * 0.92, pad + bh / 2))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(solid))
        r = bw * 0.11
        for fy in (0.20, 0.80):
            p.drawEllipse(QRectF(pad + bw / 2 - r, pad + bh * fy - r, 2 * r, 2 * r))
    elif n == "percent":
        # % —— 兩個小圈加一條斜線。
        p.setPen(QPen(solid, max(1.3, size / 11.0)))
        p.setBrush(Qt.NoBrush)
        r = bw * 0.16
        p.drawEllipse(QRectF(pad + bw * 0.06, pad + bh * 0.06, 2 * r, 2 * r))
        p.drawEllipse(QRectF(pad + bw * 0.94 - 2 * r, pad + bh * 0.94 - 2 * r,
                             2 * r, 2 * r))
        p.setPen(QPen(solid, max(1.4, size / 10.0), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(pad + bw * 0.88, pad + bh * 0.10),
                   QPointF(pad + bw * 0.12, pad + bh * 0.90))
    elif n in ("snr", "tstat"):
        # 「差距 ÷ 散布」那個**比例**本身：上面一條長的雙箭頭（差多遠），
        # 底下一段短的實心帶（參照的格子彼此差多少）。兩者的長度比就是 snr。
        y_gap = pad + bh * (0.24 if n == "snr" else 0.18)
        p.setPen(bold)
        p.drawLine(QPointF(pad + bw * 0.08, y_gap), QPointF(pad + bw * 0.92, y_gap))
        a = bw * 0.13
        for fx, d in ((0.08, 1), (0.92, -1)):
            x = pad + fx * bw
            p.drawLine(QPointF(x, y_gap), QPointF(x + a * d, y_gap - a * 0.7))
            p.drawLine(QPointF(x, y_gap), QPointF(x + a * d, y_gap + a * 0.7))
        band = QColor(solid)
        band.setAlpha(190)          # 19 px 下太淡就整條不見了
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(band))
        y_sd = pad + bh * (0.62 if n == "snr" else 0.50)
        p.drawRect(QRectF(pad + bw * 0.36, y_sd, bw * 0.28, bh * 0.16))
        if n == "tstat":
            # 多一排格子：**幾格**也算進去。
            p.setBrush(QBrush(solid))
            side = bw * 0.16
            for i in range(4):
                p.drawRect(QRectF(pad + bw * 0.10 + i * side * 1.28,
                                  pad + bh * 0.80, side, side))
        p.setBrush(Qt.NoBrush)
    elif n == "abs_delta":
        # |Δ| —— 三角形描邊（`delta` 是實心的），兩側各一根絕對值的直槓。
        p.setPen(QPen(solid, max(1.2, size / 11.0)))
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF([
            QPointF(pad + bw * 0.50, pad + bh * 0.14),
            QPointF(pad + bw * 0.22, pad + bh * 0.86),
            QPointF(pad + bw * 0.78, pad + bh * 0.86)]))
        p.setPen(QPen(solid, max(1.3, size / 10.0), Qt.SolidLine, Qt.RoundCap))
        for fx in (0.06, 0.94):
            p.drawLine(QPointF(pad + fx * bw, pad + bh * 0.08),
                       QPointF(pad + fx * bw, pad + bh * 0.92))
    elif n == "contrast":
        # 半黑半白的圓 —— 對比這件事最老的那張圖。
        box = QRectF(pad + bw * 0.06, pad + bh * 0.06, bw * 0.88, bh * 0.88)
        p.setPen(QPen(solid, max(1.2, size / 11.0)))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(box)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(solid))
        p.drawPie(box, 90 * 16, 180 * 16)
    elif n == "pct_rank":
        # 一排格子（參照的那些）加一根站在它們右邊的實心標記 —— 「排第幾」。
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(faint))
        hs = (0.30, 0.44, 0.36, 0.52)
        cw = bw * 0.17
        for i, hh in enumerate(hs):
            p.drawRect(QRectF(pad + i * cw, pad + bh * (1 - hh),
                              cw * 0.66, bh * hh))
        p.setBrush(QBrush(solid))
        p.drawRect(QRectF(pad + bw * 0.76, pad + bh * 0.10, bw * 0.20, bh * 0.90))
    elif n == "overlap":
        # 兩個相交的圓，中間那片填起來 = 兩條分布共用的部分。
        r = bw * 0.30
        cy = pad + bh * 0.50
        a = QRectF(pad + bw * 0.02, cy - r, 2 * r, 2 * r)
        b = QRectF(pad + bw * 0.98 - 2 * r, cy - r, 2 * r, 2 * r)
        pa, pb = QPainterPath(), QPainterPath()
        pa.addEllipse(a)
        pb.addEllipse(b)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(solid))
        p.drawPath(pa.intersected(pb))
        # 兩個圈**不用 `faint`**：19 px 下 `#bcbcbc` 的一圈在白底上等於不見，
        # 而剩下的那片交集看起來只是一顆點。
        ring = QColor(solid)
        ring.setAlpha(120)
        p.setPen(QPen(ring, max(1.1, size / 12.0)))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(a)
        p.drawEllipse(b)
    elif n == "spread_ratio":
        # 兩段長短不同的散布（上長下短）—— 它們的**比**就是這個數字。
        p.setPen(bold)
        for fy, fa, fb in ((0.30, 0.06, 0.94), (0.74, 0.34, 0.66)):
            y = pad + bh * fy
            p.drawLine(QPointF(pad + fa * bw, y), QPointF(pad + fb * bw, y))
            for fx in (fa, fb):                # 兩端的擋頭
                x = pad + fx * bw
                p.drawLine(QPointF(x, y - bh * 0.11), QPointF(x, y + bh * 0.11))
    elif n == "saturated":
        curve(_dist_curve())
        p.setPen(Qt.NoPen)                    # 貼在頂端的那一根
        p.setBrush(QBrush(solid))
        p.drawRect(QRectF(pad + 0.90 * bw, pad + bh * 0.10, bw * 0.10, bh * 0.90))
    elif n == "range":
        # 整條分布的兩端 —— 跟 ``std`` 的差別是箭頭拉到**底**，因為 range 講的
        # 正是「最極端的兩顆之間」，而那是它跟任何離散度指標唯一的差別。
        curve(_dist_curve())
        arrow_span(0.06, 0.94)
    elif n in ("ler_a", "ler_b"):
        # 一條**在抖的邊**，另一側墊一塊淡的（哪一邊是「裡面」看得出來）。
        # 左右鏡像 = 兩條邊。
        #
        # **刻意跳出「淡的是分布、實的是這個統計量」那套語言**：LER 量的不是一
        # 條分布，是一條邊自己的位置在跳。畫成第四張分布圖的話，它跟 ``std``
        # 在 19 px 下是同一張圖，而那正是這一族小圖存在的理由。
        left = (n == "ler_a")
        fx = 0.34 if left else 0.66
        c = QColor(faint)
        c.setAlpha(70)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        x0 = pad + (0.0 if left else (fx + 0.12) * bw)
        span = ((fx - 0.12) if left else (1.0 - fx - 0.12)) * bw
        p.drawRect(QRectF(x0, pad, max(0.0, span), bh))
        p.setPen(bold)
        p.setBrush(Qt.NoBrush)
        wob = [(fx + (0.08 if (i % 2) else -0.08), 0.03 + i * 0.188)
               for i in range(6)]
        p.drawPolyline(poly_of(wob))
    elif n in ("area", "deq", "feret_max", "feret_min", "roundness"):
        # 同一團輪廓，差別在標出來的是哪一部分（見 :func:`_blob_outline`）。
        blob = _blob_outline(pad, bw, bh)
        filled = QColor(solid)
        filled.setAlpha(95 if n == "area" else 45)
        p.setPen(QPen(faint if n == "area" else bold.color(),
                      max(1.0, size / 13.0)))
        p.setBrush(QBrush(filled))
        p.drawPolygon(blob)
        p.setBrush(Qt.NoBrush)
        p.setPen(bold)
        if n == "deq":
            # 一個**等面積的圓**疊上去 —— 「跟它一樣大的圓有多寬」。
            r = math.sqrt(abs(_poly_area(blob)) / math.pi)
            p.drawEllipse(blob.boundingRect().center(), r, r)
        elif n in ("feret_max", "feret_min"):
            pts = [(blob.at(i).x(), blob.at(i).y()) for i in range(blob.count())]
            if n == "feret_max":
                a, b = _extreme_pair(pts, longest=True)
                p.drawLine(QPointF(*a), QPointF(*b))
            else:
                # 最窄的那一夾：兩條平行線貼著輪廓的上下
                rect = blob.boundingRect()
                for fy in (0.30, 0.70):
                    y = rect.top() + fy * rect.height()
                    p.drawLine(QPointF(rect.left(), y),
                               QPointF(rect.right(), y))
        elif n == "roundness":
            # 周長本身畫粗 —— roundness 問的是「這一圈相對於它圍住的面積」。
            p.setPen(QPen(solid, max(1.6, size / 8.0)))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(blob)
    else:
        raise ValueError("unknown metric glyph: %r (known: %s)"
                         % (name, ", ".join(METRIC_GLYPHS)))
    p.setPen(bold)
    p.setBrush(Qt.NoBrush)


def _paint_glyph(widget: QWidget, name: str, side: str = "center") -> None:
    """把 ``name`` 畫到 ``widget`` 上（給 icon 按鈕的 ``paintEvent`` 用）。

    顏色取自 **widget 自己的 palette**，而 palette 的 ``ButtonText`` 是 Qt 從
    QSS 的 ``color`` 解析出來的 —— 所以換膚、變灰（``:disabled`` 那條）全部
    自動跟著，這裡不必知道任何 token 名字，也不必在換主題時被誰通知。
    """
    from PySide6.QtGui import QPalette

    r = widget.contentsRect()
    # 圖示的大小跟著鈕走，但**只有大鈕才放大**（F11 Region-1 第四輪）：
    # 24 px 的鈕維持 15 px 的圖示（既有的每一顆都是那個比例），30 px 以上的
    # 工具鈕才放到 21 —— 使用者回報「圖示只佔一半，蠻醜的」，那是把大鈕配
    # 小圖示的結果。門檻式而不是等比，是為了讓既有的鈕逐像素不變。
    side_px = float(min(r.width(), r.height()))
    size = (max(9.0, min(side_px, 15.0)) if side_px < 30.0
            else max(21.0, min(side_px * 0.62, 40.0)))
    colour = widget.palette().color(QPalette.ButtonText).name()
    p = QPainter(widget)
    if side == "left":
        # 用 ``rect()`` 而不是 ``contentsRect()``：QSS 樣式下的 contentsRect
        # **尺寸**扣掉了 padding，但**原點仍然是 (0, 0)** —— 它不是一個可以拿來
        # 定位的框。而圖示要畫的正是被 padding 撐開的那一塊。
        size = min(size, 14.0)
        x = widget.rect().left() + 7.0
        y = widget.rect().center().y() - size / 2.0 + 0.5
    else:
        x = r.center().x() - size / 2.0 + 0.5
        y = r.center().y() - size / 2.0 + 0.5
    p.translate(x, y)
    draw_glyph_icon(p, name, size, colour, dark=theme.current_theme() == "dark")
    p.end()


class _GlyphMixin(object):
    """給按鈕加一個自繪圖示。文字仍然可以有（``side="left"`` 時畫在左邊）。"""

    def _init_glyph(self, name: str, side: str = "center") -> None:
        if name not in GLYPH_ICONS:
            raise ValueError("unknown icon: %r" % (name,))
        self._glyph_name = name
        self._glyph_side = side
        if side != "left":
            # 沒有文字的按鈕對讀螢幕軟體與 Qt 的測試工具是空的。tooltip 已經
            # 寫了那句話，直接拿來當名字，不要再發明第二份說明。
            self.setAccessibleName(self.toolTip() or name)
            self.setProperty("glyph", "true")
        else:
            self.setProperty("hasGlyph", "true")

    def glyph_name(self) -> str:
        return getattr(self, "_glyph_name", "")

    def paintEvent(self, e) -> None:  # Qt hook
        super().paintEvent(e)
        _paint_glyph(self, self._glyph_name, self._glyph_side)


class IconButton(_GlyphMixin, QPushButton):
    """小的圖示按鈕（畫布縮放列、節點卡的移動/刪除、換 defect）。"""

    def __init__(self, icon: str, tip: str = "",
                 parent: Optional[QWidget] = None,
                 kind: str = "ghost"):
        QPushButton.__init__(self, "", parent)
        self.setObjectName("cardButton")
        self.setProperty("shape", "square")
        self.setProperty("kind", str(kind))
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(str(tip))
        self._init_glyph(icon)


class GlyphButton(_GlyphMixin, QPushButton):
    """**有文字、左邊帶一個自繪圖示**的一般按鈕（F120）。

    `IconButton` 是「只有圖示」的那一種（工具列上的小方鈕）；工具列上那種
    「圖示 ＋ 一個字」的組合在這之前只有 `studio_layout` 的 `_GlyphToolButton`
    做得到，而它是 `QToolButton`，套不進一排 `QPushButton` 裡（框線、高度、
    hover 全部是另一套 QSS）。

    ⚠ 左邊那一格的空間是 QSS 的 ``[hasGlyph="true"]`` 撐出來的（`_init_glyph`
    會設），不是這裡調 padding —— 兩邊各調一次的話遲早會差幾個像素，而它們
    就並排放著。
    """

    def __init__(self, icon: str, text: str = "", tip: str = "",
                 parent: Optional[QWidget] = None):
        QPushButton.__init__(self, str(text), parent)
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(str(tip))
        self._init_glyph(icon, "left" if text else "center")


def restyle(widget: QWidget) -> None:
    """屬性改了之後重新套一次 QSS。

    Qt **不會**自己重算：``setProperty("active", True)`` 只是存一個值，選擇器
    ``[active="true"]`` 要等下一次 polish 才會生效。少了這一步的症狀是
    「狀態明明改了，畫面沒動」—— 而且不報錯。
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def apply_button_cursors(root: QWidget) -> int:
    """把 ``root`` 底下每一顆按鈕的游標設成手指，回傳處理了幾顆。

    以前這是每個呼叫端自己記得要做的事，結果只做到一半 —— 工具列、卡片庫、
    節點卡有，Stop、Open KLARF…、輸出精靈的四顆、畫布縮放列全都沒有。
    「滑過去有沒有變手指」是使用者判斷「這能不能點」的第一個訊號，
    不該取決於寫那一行的人當天有沒有想到。

    所以改成**規則**：一個視窗建好之後掃一次。勾選框與單選鈕不算 ——
    它們是 ``QAbstractButton`` 但慣例上維持箭頭。
    """
    from PySide6.QtWidgets import QToolButton

    n = 0
    for w in root.findChildren(QWidget):
        if isinstance(w, (QPushButton, QToolButton)):
            w.setCursor(Qt.PointingHandCursor)
            n += 1
    return n
