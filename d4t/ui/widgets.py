# d4t Studio widget library — authored 2026-07-28 (M3).
# ImageView 的 zoom/pan 骨架 vendored from: PEAR/pear/ui/image_view.py（去掉 ROI 編輯）。
"""Studio 的六個可重用元件 —— 全部「資料驅動」，**不碰引擎**。

設計約束（很重要，別破壞）：

1. 這裡的元件只吃 dict / list / ndarray，只發 Signal。任何一個元件都不會
   import ``d4t.core``、不會跑 pipeline、不會開檔案。組裝與呼叫引擎是
   main window / worker 的事。
2. 顏色一律走 ``theme.TOKENS`` / ``theme.seg_color``，不寫死 hex。
3. 每個參數的白話 ``help`` 一定要看得到（``ParamForm`` 的第二行提示）—— 推廣鐵則。

元件一覽：

- :class:`ImageView`        ndarray 檢視器（滾輪縮放、拖曳平移、雙擊 fit）
- :class:`ParamForm`        由 ``Step.describe()`` 自動生成的參數表單
- :class:`LibraryPanel`     三段式卡片庫（影像／算法／ADC）
- :class:`HistogramWidget`  分數分佈 + 可拖曳門檻線 + 可點擊長條（``bar_clicked``）
- :class:`FeatureTable` / :class:`VerdictChip`  特徵表與判定 chip
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import (QEvent, QMimeData, QPointF, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QTextDocument,
    QDrag,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QIcon,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.algo import glv as algo_glv
from . import glyphs
from . import region_words
from . import theme
from .numbers import format_feature_value
from .theme import TOKENS, region_hex

#: 標記的**角色** → 主題的哪一個顏色權杖（F33）。
#:
#: `Step.overlay_marks` 的 ``labels`` 平常是**具名區域**的名字（顏色因此跟影像
#: 上那個區域的框一模一樣）。``!`` 開頭的是**角色**而不是名字 —— 沿用
#: `decide_tree` 的 ``!failed`` / ``!unbinned`` 那個慣例，而區域名是識別字，
#: 不可能撞到。
#:
#: **卡片說角色，這裡挑顏色**：core 不得 import Qt，而「紅色是什麼紅」是主題的
#: 事。報表用的是同一組語言 —— 框紅、十字綠（`core/export/overlay.py` 的
#: `BOX_COLOR` / `AIM_COLOR`），所以同一顆 defect 在畫面上與在報表上，
#: **紅的永遠是「對到哪」、綠的永遠是「瞄準哪」**，而 `mark_alert` /
#: `mark_aim` 兩個權杖的值跟那兩個常數逐位元組相同。
#:
#: ⚠ **不要用介面的 `danger` / `success`**：那兩個是放在面板上的顏色（要跟白底
#: 相處，所以偏暗偏濁），而這些記號畫在**使用者的影像**上，還要跟
#: `REGION_COLORS` 分得開 —— 疊圖上其餘的框穿的正是那一組。`danger`（#d05a4c）
#: 跟第 8 個區域色（#f08a5f）只差 ΔE 19.9，一整排橘框裡它認不出來。
#: 這條有測試守著（`test_a_mark_role_never_wears_a_region_colour`）。
MARK_ROLE_TOKENS = {
    "!match": "mark_alert",  # 小圖真的對到的那一塊
    "!aim": "mark_aim",      # 機台瞄準的那一點
    "!worst": "mark_alert",  # 逐框比較挑出來的那一格（紅粗框，見下）
}

#: 有些角色要**畫粗**（預設 1.6）。角色 → 線寬。
#:
#: `!worst` 是使用者 2026-09-01 定的：「我傾向異常的那格用**紅框**（或不同
#: 顏色）的**加粗框**把它框出來」。
#:
#: ⚠ **第一版畫琥珀（照抄報表的 `ROI_WINNER_COLOR`），而它在畫面上幾乎看不
#: 出來** —— render 出來才發現：`theme.REGION_COLORS` 裡有 ``#f0b429``（琥珀）
#: 與 ``#f08a5f``（橘），而區域框穿的正是那一組。報表沒有這個問題，因為那張圖
#: 上其餘的框是鋼青色、紅色被「量到的那一塊」佔著。
#:
#: 所以規矩不是「跟報表同一個顏色」，是**在自己這張圖上不會跟旁邊撞**：
#: 螢幕上其餘的框穿區域色（含琥珀橘），紅色沒有人用；報表上紅色有人用，
#: 其餘的框是鋼青，琥珀沒有人用。兩張圖各自挑得出最響的那一個。
#: 加粗那一半兩邊一致（報表 2–3 px、這裡 2.6 px）—— 那是這個記號真正的
#: 共同語言：**最異常的那一格是唯一一個粗框**。
MARK_ROLE_WEIGHTS = {
    "!worst": 2.6,
}

__all__ = [
    "ImageView",
    "ParamForm",
    "LibraryPanel",
    "HistogramWidget",
    "FeatureTable",
    "feature_html",
    "VerdictChip",
    "TemplateField",
    "to_uint8",
    "small_button",
    "apply_button_cursors",
    "restyle",
    "IconButton",
    "GLYPH_ICONS",
    "draw_glyph_icon",
    "draw_metric_glyph",
    "METRIC_GLYPHS",
    "METRIC_GROUPS",
    "MetricChips",
    "FilterChip",
    "metric_face",
    "feature_unit",
    "VARIANT_GLOSS",
]


# --------------------------------------------------------------------------- #
# 按鈕的兩個小工具（F7-23 第二輪）
# --------------------------------------------------------------------------- #
def small_button(text: str, tip: str = "", parent: Optional[QWidget] = None,
                 shape: str = "square", kind: str = "ghost") -> QPushButton:
    """一顆小按鈕（卡片控制、畫布縮放、換 defect、Card/Features 切換）。

    **尺寸不在這裡填。** ``shape`` 只說「方的還是帶文字的」，實際邊長由 QSS 的
    ``control_sm`` 決定 —— 以前六個呼叫端各自寫死一組尺寸（22×22、24×22、
    30×22、寬 28、寬 40、高 20），於是同一種視覺語言沒有兩顆一樣大。

    ``kind="icon"`` 給浮在畫布或影像上的那幾顆一個自己的底：那裡沒有卡片當
    底色，透明的按鈕要滑到才看得出是按鈕（同 F7-13 給工具列加邊框的理由）。
    """
    b = QPushButton(text, parent)
    b.setObjectName("cardButton")
    b.setProperty("shape", str(shape))
    b.setProperty("kind", str(kind))
    b.setCursor(Qt.PointingHandCursor)
    if tip:
        b.setToolTip(str(tip))
    return b


class FilterChip(QPushButton):
    """一顆可移除的條件 chip：``排序：score ↓  ✕``。點一下就把該條件拿掉。

    PR-3 從 `gallery._Chip` 升格搬來（結果表的維度過濾也要 chip，而同一種
    視覺語言只能有一份）。objectName 沿用 ``galleryChip`` —— 外觀的家在 QSS 的
    ``QPushButton#galleryChip``（F7-23 第三輪），名字跟著搬會讓兩邊各長一份
    樣式。
    """

    def __init__(self, text: str, tip: str, parent: Optional[QWidget] = None):
        # ``×`` 是 U+00D7（Latin-1），不是 U+2715 那個 Dingbats 的 ``✕`` ——
        # 後者在 Windows 上要退到 Segoe UI Symbol（F7-23 第四輪）。
        super().__init__("%s  ×" % text, parent)
        self.setObjectName("galleryChip")
        self.label_text = text
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tip)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


def clear_layout_parked(layout, graveyard: list) -> None:
    """把 ``layout`` 裡的 widget 全部拿下來 —— **停放，不銷毀**（F25）。

    為什麼不能直接 ``setParent(None)``
    ---------------------------------
    這幾個面板（判定、判定樹的一步、分流）是「改一格就整段重建」的：
    使用者動了某一格 → 那一格的訊號寫進 model → model 的 listener 打回來
    → 面板重建 → **舊的那一格就是正在發訊號的那一個**。

    ``setParent(None)`` 之後 Python 就是它唯一的持有者，而 layout item 一丟
    參考數歸零 → C++ 物件當場解構 —— 而 Qt 的訊號還在那個物件的堆疊上。
    那是 use-after-free：跑得完的時候什麼事都沒有，跑不完的時候是**閃退**，
    而且跟平台的事件流有關（offscreen 重現不出來，真機上「有機會」發生）。
    使用者 2026-08-24 回報的正是這個形狀：「輸入 bin 有機會閃退」。

    所以這裡只做兩件事：把它藏起來、把它從版面上拿掉，**參考留著**。
    真正的解構排到下一輪 event loop（那時候訊號早就返回了）。

    ``graveyard`` 是呼叫端持有的一個 list —— 停屍間必須活得比這一次事件久，
    所以它不能是這支函式裡的區域變數。
    """
    from PySide6.QtCore import QTimer

    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is None:
            sub = item.layout()
            if sub is not None:
                clear_layout_parked(sub, graveyard)
            continue
        w.hide()
        w.setParent(None)
        graveyard.append(w)
    if graveyard:
        # 排到下一輪：這一輪的訊號返回之後才真的釋放。
        QTimer.singleShot(0, graveyard.clear)


#: 按鈕上畫得出來的圖示（F7-23 第四輪）。名字是**這顆鈕在做什麼**，
#: 不是它長什麼樣 —— 呼叫端說 ``"fit"``，不說「兩端帶箭頭的斜線」。
GLYPH_ICONS = (
    "undo", "redo", "theme", "prev", "next", "play", "chevron_down",
    "zoom_in", "zoom_out", "fit", "tidy", "up", "down", "close",
    # 工具列那五顆（F7-24）＋ 兩個沒有 KLARF 的入口（F11 Input-2／Input-3）
    "folder", "document", "save", "templates", "export", "stack",
    "folder_open", "layers",
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
    elif n == "folder":
        p.drawLine(QPointF(m, h * 0.30), QPointF(w * 0.44, h * 0.30))
        p.drawLine(QPointF(w * 0.44, h * 0.30), QPointF(w * 0.54, h * 0.42))
        p.drawRect(QRectF(m, h * 0.42, w - 2 * m, h * 0.42))
    elif n == "folder_open":
        # 打開的資料夾：後片是方的、前片往外斜。跟 ``folder``（關著的）並排時
        # 差別在**前片的斜邊** —— 三顆 Open 鈕的輪廓要各不相同（F7-24）。
        p.drawLine(QPointF(m, h * 0.32), QPointF(w * 0.44, h * 0.32))
        p.drawLine(QPointF(w * 0.44, h * 0.32), QPointF(w * 0.54, h * 0.44))
        p.drawLine(QPointF(m, h * 0.32), QPointF(m, h * 0.80))
        p.drawLine(QPointF(w * 0.54, h * 0.44), QPointF(w - m, h * 0.44))
        # 前片：從左下往右斜出去
        p.drawLine(QPointF(m, h * 0.80), QPointF(w - m * 0.6, h * 0.80))
        p.drawLine(QPointF(w - m, h * 0.44), QPointF(w - m * 0.6, h * 0.80))
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

    def paintEvent(self, e) -> None:       # noqa: D102 - Qt hook
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


# --------------------------------------------------------------------------- #
# numpy -> Qt
# --------------------------------------------------------------------------- #
def to_uint8(arr: np.ndarray) -> np.ndarray:
    """任意 ndarray -> 可顯示的 uint8。

    * ``uint8`` 直接用（不做任何拉伸，patch 的原始灰階就是原始灰階）。
    * 其他型別（float32 的 diff / snr_map、int16 …）走 min–max 自動拉伸；
      NaN / ±Inf 不參與統計，最後補 0（不會整張變白或炸掉）。
    """
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        return np.ascontiguousarray(a)
    f = np.asarray(a, dtype=np.float64)
    finite = np.isfinite(f)
    if not finite.any():
        return np.zeros(f.shape, dtype=np.uint8)
    lo = float(f[finite].min())
    hi = float(f[finite].max())
    if hi <= lo:
        scaled = np.zeros(f.shape, dtype=np.float64)
    else:
        scaled = (f - lo) * (255.0 / (hi - lo))
    scaled = np.where(finite, scaled, 0.0)
    return np.ascontiguousarray(np.clip(scaled, 0.0, 255.0).astype(np.uint8))


def _qimage_from_uint8(arr: np.ndarray) -> QImage:
    """uint8 (H,W) / (H,W,3) / (H,W,4) -> QImage（deep copy，不依賴原 buffer）。"""
    a = np.ascontiguousarray(arr)
    if a.ndim == 2:
        h, w = a.shape
        img = QImage(a.data, w, h, w, QImage.Format_Grayscale8)
    elif a.ndim == 3 and a.shape[2] == 3:
        h, w, _ = a.shape
        img = QImage(a.data, w, h, 3 * w, QImage.Format_RGB888)
    elif a.ndim == 3 and a.shape[2] == 4:
        h, w, _ = a.shape
        img = QImage(a.data, w, h, 4 * w, QImage.Format_RGBA8888)
    else:
        raise ValueError(f"Unsupported image shape: {a.shape}")
    return img.copy()


# --------------------------------------------------------------------------- #
# 1. ImageView
# --------------------------------------------------------------------------- #
def _focus_set(focus: Any) -> frozenset:
    """``focus`` → 要畫滿的那幾條線的 index。

    吃一個 index（大多數卡片：一條代表線）或**一串** index（一個記號不只一條
    線 —— GLV 的贏家格是一個 X）。``-1`` / 空的 = 一條都不特別畫。
    """
    if focus is None:
        return frozenset()
    if isinstance(focus, (int, float)) and not isinstance(focus, bool):
        i = int(focus)
        return frozenset() if i < 0 else frozenset((i,))
    try:
        return frozenset(int(v) for v in focus if int(v) >= 0)
    except (TypeError, ValueError):      # noqa: BLE001 — 顯示用，不能擋畫面
        return frozenset()


class ImageView(QWidget):
    """ndarray 檢視器：滾輪對游標縮放、拖曳平移、雙擊 fit。

    放大到 1:1 以上時關掉平滑取樣（nearest-neighbour），缺陷 patch 的像素要
    看得出方格 —— 這是看 SEM 小圖的基本要求。
    """

    zoom_changed = Signal(float)
    cursor_info = Signal(str)          # "x 12  y 30  ·  gray 187"（離開時空字串）
    #: 縮放**或**平移之後的完整檢視狀態（scale, offset）。
    #: 並排比對兩張圖時，兩邊靠這個訊號互相跟隨 —— 沒有連動的並排沒有意義，
    #: 使用者得手動把兩邊拖到同一個位置才比得起來。
    view_changed = Signal(float, QPointF)

    _MIN_SCALE = 0.02
    _MAX_SCALE = 60.0
    _EMPTY_TEXT = "(no image)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(240, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._image: Optional[np.ndarray] = None      # 顯示用的 uint8
        self._pixmap: Optional[QPixmap] = None
        self._scale = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._auto_fit = True                         # 尺寸變動時是否自動重 fit
        self._panning = False
        self._pan_start = QPointF()
        self._pan_offset = QPointF()
        #: 疊在影像上的 ROI 框（正規化座標）。見 :meth:`set_overlay`。
        self._overlay: List[Tuple[float, float, float, float]] = []
        self._overlay_focus = -1
        #: 每個框屬於哪一個具名區域（跟 ``_overlay`` 等長）。空字串 = 不分。
        self._overlay_labels: List[str] = []
        #: 區域名 -> 顏色索引，依**第一次出現**的順序。畫圖例時也走這一份。
        self._overlay_order: List[str] = []
        #: 回溯面板點了哪個區域（PR-3）：命中的框全強度、其餘降 alpha。
        #: **不 overload focus** —— 顏色=哪塊、粗細=缺陷格、alpha=你問的那塊。
        self._overlay_emphasis: List[str] = []
        #: 量測標記（F19）：線段、每條線上的點、要畫粗的那一條。見 :meth:`set_marks`。
        self._marks: List[Any] = []
        #: 這一組標記要不要畫滿（`Step.marks_solid`）。
        self._marks_solid = False
        self._mark_points: List[Any] = []
        self._mark_focus: frozenset = frozenset()
        #: 每一條標記屬於哪一個具名區域（跟 ``_marks`` 等長；空字串 = 不分色）。
        self._mark_labels: List[str] = []
        #: 量測尺按著時的那一條帶（axis, 起, 迄；影像像素）。見 :meth:`set_measure`。
        self._measure: Optional[Tuple[str, float, float]] = None
        #: 選取的卡片上那個「以像素為單位」的參數有多大（大小, 標籤）。
        #: 見 :meth:`set_kernel_hint`。
        self._kernel: Optional[Tuple[float, str]] = None

    # -- public API --------------------------------------------------------
    def set_image(self, arr: Optional[np.ndarray]) -> None:
        """設定影像；``None`` 清空並顯示「（無影像）」。

        第一次拿到影像（或尺寸換了）會自動 fit；同尺寸的重繪保留目前的縮放/平移，
        調參數時視野不會被重設。
        """
        if arr is None:
            self._image = None
            self._pixmap = None
            self._auto_fit = True
            self.update()
            return
        u8 = to_uint8(arr)
        old_shape = None if self._image is None else self._image.shape[:2]
        self._image = u8
        self._pixmap = QPixmap.fromImage(_qimage_from_uint8(u8))
        if old_shape != u8.shape[:2]:
            self.fit()
        else:
            self.update()

    def has_image(self) -> bool:
        return self._image is not None

    def image(self) -> Optional[np.ndarray]:
        return self._image

    def scale(self) -> float:
        return self._scale

    def zoom_percent(self) -> int:
        return int(round(self._scale * 100))

    def fit(self) -> None:
        """整張影像置中縮放到剛好塞進畫布（留 4% 邊）。"""
        self._auto_fit = True
        if self._pixmap is None:
            return
        vw, vh = max(1, self.width()), max(1, self.height())
        iw, ih = self._pixmap.width(), self._pixmap.height()
        if iw <= 0 or ih <= 0:
            return
        self._scale = float(np.clip(min(vw / iw, vh / ih) * 0.96,
                                    self._MIN_SCALE, self._MAX_SCALE))
        self._offset = QPointF((vw - iw * self._scale) / 2.0,
                               (vh - ih * self._scale) / 2.0)
        self.update()
        self.zoom_changed.emit(self._scale)
        self.view_changed.emit(self._scale, QPointF(self._offset))

    def zoom_by(self, factor: float, anchor: Optional[QPointF] = None) -> None:
        """以 ``anchor``（畫布座標，預設中心）為定點縮放。"""
        if self._pixmap is None:
            return
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        ia = self._to_image(anchor)
        new_scale = float(np.clip(self._scale * factor,
                                  self._MIN_SCALE, self._MAX_SCALE))
        if new_scale == self._scale:
            return
        self._scale = new_scale
        self._offset = QPointF(anchor.x() - ia.x() * self._scale,
                               anchor.y() - ia.y() * self._scale)
        self._auto_fit = False
        self.update()
        self.zoom_changed.emit(self._scale)
        self.view_changed.emit(self._scale, QPointF(self._offset))

    def set_view(self, scale: float, offset: QPointF) -> None:
        """直接套用另一張圖的檢視狀態（並排比對時用）。

        **不回發 view_changed** —— 兩邊互相跟隨會無限來回。跟隨是單向的，
        由發起操作的那一邊推過去。
        """
        s = float(np.clip(float(scale), self._MIN_SCALE, self._MAX_SCALE))
        if s == self._scale and QPointF(offset) == self._offset:
            return
        self._scale = s
        self._offset = QPointF(offset)
        self._auto_fit = False
        self.update()

    def view_state(self) -> Tuple[float, QPointF]:
        return self._scale, QPointF(self._offset)

    def zoom_in(self) -> None:
        self.zoom_by(1.25)

    def zoom_out(self) -> None:
        self.zoom_by(1 / 1.25)

    # -- transforms --------------------------------------------------------
    def set_overlay(self, rects: Optional[Sequence[Sequence[float]]],
                    focus: int = -1,
                    labels: Optional[Sequence[str]] = None) -> None:
        """把 ROI 框疊在影像上（**正規化**座標 ``(nx, ny, nw, nh)``）。

        為什麼要疊在這裡而不是只有「跨顆檢視」那個視窗
        ----------------------------------------------
        定位卡的參數是**一邊拖一邊看**決定的（F7-8 那條：「先想好一個數字再
        輸入」那個順序是反的）。框只出現在另一個要按鈕、要跑完一批才看得到的
        視窗裡，等於把這件事變成「改一次、跑一次、再回來看」——
        而敏感度這種參數要試十幾次。

        座標用正規化的，所以縮放平移都跟著影像走，換一顆 patch 尺寸也不用重算。
        ``focus`` 是要特別標出來的那一個（交會定位的 ``_center``：缺陷所在的
        那一塊），畫成粗線＋角標，其餘畫細線 —— 一堆一模一樣的框看不出哪個是
        「這一顆」的。

        ``labels`` 是每個框屬於**哪一個具名區域**（跟 ``rects`` 等長）。
        給了就一個區域一個顏色，並在左上角畫一份圖例（F11 Region 第八輪，
        使用者回報「Image Stream 顯示上顏色 overlay 重疊會同個顏色（藍色）」）。

        為什麼一定要分色：Region-1 之後**一張卡可以標好幾個區域**，而這裡把它們
        全部攤平成一串框，全部畫成 accent 藍。兩個區域疊在一起的時候畫面上就只是
        一團藍線 —— 而使用者要判斷的正是「哪一塊是 ROI1、哪一塊是 ROI2」。
        顏色跟模板編輯器**同一組**（`theme.REGION_COLORS`）：他在對話框裡把
        ROI1 畫成綠色的，到了 patch 上它就要還是綠色的。

        角色分工：**顏色 = 哪一個區域，線寬與角標 = 哪一塊是缺陷那一塊。**
        兩個問題各佔一個視覺維度，不要用同一個維度回答兩次（這是「焦點框以前
        畫成紅色」被換掉的原因 —— 紅色會被讀成第三個區域）。
        """
        self._overlay = [tuple(float(v) for v in r) for r in (rects or [])
                         if r is not None and len(tuple(r)) == 4]
        self._overlay_focus = int(focus)
        names = [str(v) for v in (labels or [])]
        # 長度對不上就整組不分色 —— 錯位的顏色比沒有顏色糟得多（它會**指錯**
        # 區域，而畫面上沒有任何東西透露這件事）。
        self._overlay_labels = (names if len(names) == len(self._overlay)
                                else [""] * len(self._overlay))
        order: List[str] = []
        for n in self._overlay_labels:
            if n and n not in order:
                order.append(n)
        self._overlay_order = order
        # 換一組框＝上一個「你問的那塊」不再成立（框可能已經是別張卡的）。
        self._overlay_emphasis = []
        self.update()

    def set_overlay_emphasis(self, names: Optional[Sequence[str]]) -> None:
        """把某幾個區域**點亮**（其餘的框降 alpha）—— 回溯面板「點一項亮那
        一塊」用（PR-3）。`set_overlay` 會清掉它：換一組框之後舊的強調指的
        可能已經是別張卡的區域。"""
        self._overlay_emphasis = [str(n) for n in (names or []) if str(n)]
        self.update()

    def overlay_emphasis(self) -> List[str]:
        """現在點亮的區域名（測試讀這個，不去讀畫素）。"""
        return list(self._overlay_emphasis)

    def set_marks(self, lines: Optional[Sequence[Any]] = None,
                  points: Optional[Sequence[Any]] = None,
                  focus: Any = -1,
                  labels: Optional[Sequence[str]] = None,
                  solid: bool = False) -> None:
        """把**量測標記**疊在影像上（正規化座標）。

        ``lines`` 是 ``[[(x0, y0), (x1, y1)], …]``，``points[i]`` 是第 i 條線段
        上的點。``focus`` 是要畫粗的那一條（代表值那一條）—— **也可以是一串**
        （一個記號本來就可能不只一條線）。

        ⚠ **不只一條那件事是踩出來的**：GLV 的贏家格畫的是一個 **X**，而 X 是
        兩條線；`focus` 只認得一個 index 的時候，第二條落在 alpha 70、1px 那
        一組 —— 於是畫面上那一格中間是**一條斜線**，不是一個 X。使用者
        2026-09-01 看著截圖問「框中間有一條斜線?」。而當時的測試**把那個形狀
        寫死了**（`assert focus == 1  # X 的第一條`）：測試守住的是 bug 的形狀，
        不是那句「畫一個 X」的意圖。

        為什麼跟 :meth:`set_overlay` 分開
        ---------------------------------
        框回答的是「recipe 說要看哪裡」，標記回答的是「這一顆**真的量到了**
        什麼」—— 後者只有跑過才有，而且它是逐顆變的。混在同一支裡的話，
        「框還在但標記消失了」這個最有用的狀態（這顆量不出來）就講不出來。

        資料由**卡片自己**交出來（`Step.overlay_marks`）：meta 的形狀是那張卡的
        事，UI 只負責畫。所以下一張量測卡不必再發明一套。

        ``solid`` 是**那張卡說的**（`Step.marks_solid`）：交出來的是少少幾條
        結構線（一個框、一個十字）而不是幾十條掃描線時，淡化不是在減少雜訊，
        是在藏起唯一的資訊。預設 False —— CD 與 GLV 都**刻意**靠淡化。

        ``labels`` 是每一條標記屬於**哪一個具名區域**，而顏色**沿用框那一組的
        順序**（:meth:`set_overlay` 已經排好的 ``_overlay_order``）—— 各自從
        自己那邊數的話，同一塊區域的框是綠的、量它的那些線卻是橘的，而畫面上
        沒有任何東西說得出它們是同一塊。沒給 labels 就整組畫 accent。

        兩條保險跟 :meth:`set_overlay` 一字不差：座標正規化（縮放平移、換一顆
        patch 都跟著走），而**長度對不上就整組不畫** —— 錯位的標記會指向錯的
        地方，而畫面上沒有任何東西透露那件事。
        """
        segs = [[(float(a[0]), float(a[1])), (float(b[0]), float(b[1]))]
                for a, b in (lines or []) if a is not None and b is not None]
        pts = [[(float(x), float(y)) for x, y in (grp or [])]
               for grp in (points or [])]
        names = [str(v) for v in (labels or [])]
        self._marks = segs
        self._marks_solid = bool(solid)
        self._mark_points = pts if len(pts) == len(segs) else []
        self._mark_labels = (names if len(names) == len(segs)
                             else [""] * len(segs))
        for n in self._mark_labels:
            if n and n not in self._overlay_order:
                self._overlay_order.append(n)
        self._mark_focus = _focus_set(focus)
        self.update()

    def clear_marks(self) -> None:
        self.set_marks([], [], -1, [])

    def mark_legend(self) -> List[Tuple[str, str]]:
        """標記用到的 ``[(區域名, 顏色 hex), …]``。測試與狀態列讀這個。"""
        index_of = {n: i for i, n in enumerate(self._overlay_order)}
        out: List[Tuple[str, str]] = []
        for n in self._mark_labels:
            if n and n in index_of and n not in [k for k, _c in out]:
                out.append((n, region_hex(index_of[n])))
        return out

    def mark_count(self) -> int:
        """畫了幾條量測線。測試與狀態列讀這個，不去讀畫素。"""
        return len(self._marks)

    def overlay_legend(self) -> List[Tuple[str, str]]:
        """圖例：``[(區域名, 顏色 hex), …]``，依第一次出現的順序。

        測試與狀態列讀這個，不去讀畫素。
        """
        return [(n, region_hex(i)) for i, n in enumerate(self._overlay_order)]

    def legend_visible(self) -> bool:
        """圖例現在畫不畫得出來（測試讀這個，不去讀畫素）。

        **兩個以上的區域才畫** —— 只有一個的時候那個顏色沒有在跟誰對比，
        一行字只是擋住影像。
        """
        return len(self._overlay_order) >= 2

    def overlay_count(self) -> int:
        """現在疊了幾個框（測試與狀態列讀這個，不去讀畫素）。"""
        return len(self._overlay)

    def set_measure(self, axis: str, start: float, end: float) -> None:
        """曲線面板上的量測尺按著時，在影像上標出**同一段**（F8 量測尺）。

        為什麼影像上也要標
        ------------------
        曲線面板上的一段只是「第 40 到第 74 個取樣點」。使用者要判斷的是
        「我量到的是不是兩根 MG 的距離」—— 那個問題只有看影像答得出來。
        少了這條同步標記，量測尺量到的東西就得靠腦補對回圖上。

        座標是**影像像素**（投影曲線一個取樣點 = 一個像素列／行，所以兩者
        就是同一個索引）。``axis`` 為 ``"x"`` 時標的是兩條垂直線之間，
        ``"y"`` 是兩條水平線之間。
        """
        axis = str(axis or "")
        if axis not in ("x", "y"):
            self.clear_measure()
            return
        a, b = float(start), float(end)
        self._measure = (axis, min(a, b), max(a, b))
        self.update()

    def clear_measure(self) -> None:
        """放開量測尺 —— 標記跟著消失（它是「現在正在量」的回饋，不是註記）。"""
        if self._measure is not None:
            self._measure = None
            self.update()

    def measure_span(self) -> Optional[Tuple[str, float, float]]:
        """現在標著的那一段（沒有就 None）。測試與狀態列讀這個。"""
        return self._measure

    def set_kernel_hint(self, size_px: float, label: str = "") -> None:
        """把「這個核心有多大」畫在影像上（F11 Enhance-UI-A）。

        為什麼這一格要有
        ----------------
        ``flatten`` 的 *Scale to remove* 與 ``denoise`` 的 *Filter size* 的
        help 裡唯一的規則是**跟缺陷比**：前者要「明顯大於」，後者（hot_pixels）
        要「貼著」。而畫面上原本沒有任何尺度參考 —— 使用者只能猜像素數，
        或者去數影像的邊長。

        這跟 F7-8「把 min/max 填好，滑桿是免費的」是同一條：**使用者是一邊看
        影像一邊決定值的**，所以那個參考就該在影像上，不是在 help 裡。

        畫在**影像正中央**：patch 是以缺陷為中心裁的（`ARCHITECTURE.md`），
        所以正中央就是要比大小的那個東西。大張的 RSEM 影像上中央不是缺陷，
        但要比的是「這個框 vs 畫面上的結構」，位置不影響那個判斷。

        方框而不是圓：高斯／中位數的鄰域就是方的。形態學那幾個是橢圓，但**範圍**
        一樣 —— 而使用者要判斷的是範圍。
        """
        n = float(size_px)
        if not np.isfinite(n) or n <= 0:
            self.clear_kernel_hint()
            return
        self._kernel = (n, str(label or ""))
        self.update()

    def clear_kernel_hint(self) -> None:
        if self._kernel is not None:
            self._kernel = None
            self.update()

    def kernel_hint(self) -> Optional[Tuple[float, str]]:
        """現在畫著的核心大小（沒有就 None）。測試讀這個，不去讀畫素。"""
        return self._kernel

    def _paint_overlay(self, p: QPainter) -> None:
        if self._pixmap is None or not self._overlay:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        s = self._scale or 1.0
        index_of = {n: i for i, n in enumerate(self._overlay_order)}
        plain = QColor(TOKENS["accent"])
        p.setBrush(Qt.NoBrush)
        for i, (nx, ny, nw, nh) in enumerate(self._overlay):
            name = self._overlay_labels[i] if i < len(self._overlay_labels) else ""
            col = QColor(region_hex(index_of[name])) if name in index_of else plain
            if self._overlay_emphasis and name not in self._overlay_emphasis:
                # 沒被問到的框退到背景 —— 淡，但還在（它們是脈絡，不是雜訊）。
                col.setAlphaF(0.28)
            r = QRectF(self._offset.x() + nx * iw * s,
                       self._offset.y() + ny * ih * s,
                       max(1.0, nw * iw * s), max(1.0, nh * ih * s))
            focused = (i == self._overlay_focus)
            # 框在小 patch 上會很細，所以線寬不隨縮放變薄（**框是給人看的標記，
            # 不是影像內容**）；但也不要粗到把 5px 的框整個蓋掉。
            pen = QPen(col, 1.9 if focused else 1.0)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawRect(r)
            if focused:
                self._paint_focus_ticks(p, r, pen)
        self._paint_overlay_legend(p)

    def _paint_focus_ticks(self, p: QPainter, r: QRectF, pen: QPen) -> None:
        """缺陷那一塊的四個角標。

        以前這件事是用**紅色**講的。分色之後不能再那樣：紅色會被讀成「第三個
        區域」，而它其實跟區域無關。角標是純幾何的記號，跟任何區域顏色都不衝突
        —— 而且在框小到只剩幾個像素、線寬看不出差別的時候，它仍然看得見。
        """
        tick = max(3.0, min(7.0, min(r.width(), r.height()) * 0.35))
        wide = QPen(pen)
        wide.setWidthF(pen.widthF() + 0.9)
        p.setPen(wide)
        for x, dx in ((r.left(), 1.0), (r.right(), -1.0)):
            for y, dy in ((r.top(), 1.0), (r.bottom(), -1.0)):
                p.drawLine(QPointF(x, y), QPointF(x + dx * tick, y))
                p.drawLine(QPointF(x, y), QPointF(x, y + dy * tick))
        p.setPen(pen)

    def _paint_overlay_legend(self, p: QPainter) -> None:
        """左上角的圖例。**兩個以上的區域才畫** —— 只有一個的時候，那個顏色
        沒有在跟誰對比，一行字只是擋住影像。"""
        if not self.legend_visible():
            return
        legend = self.overlay_legend()
        f = QFont(p.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        fm = QFontMetricsF(f)
        pad, sw, gap, line = 5.0, 8.0, 5.0, fm.height() + 3.0
        width = max(fm.horizontalAdvance(n) for n, _c in legend) + sw + gap
        box = QRectF(6.0, 6.0, width + pad * 2, line * len(legend) + pad * 2)
        chip = QColor(TOKENS["bg_surface"])
        chip.setAlpha(205)
        p.setPen(Qt.NoPen)
        p.setBrush(chip)
        p.drawRoundedRect(box, 3.0, 3.0)
        for i, (name, hexcol) in enumerate(legend):
            y = box.top() + pad + line * i
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(hexcol))
            p.drawRect(QRectF(box.left() + pad, y + line / 2 - sw / 2, sw, sw))
            p.setPen(QColor(TOKENS["text_primary"]))
            p.drawText(QRectF(box.left() + pad + sw + gap, y, width, line),
                       Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setBrush(Qt.NoBrush)

    def _paint_marks(self, p: QPainter) -> None:
        """掃描線很淡、邊點是實心的小圓，代表那一條加粗。

        **點比線重要**：使用者要判斷的是「邊被判在哪」，線只是告訴他那個判斷
        是在哪一列上做的。所以線畫到幾乎看不見，點畫滿。
        """
        if self._pixmap is None or not self._marks:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        s_ = self._scale or 1.0
        ox, oy = self._offset.x(), self._offset.y()

        def at(pt) -> QPointF:
            return QPointF(ox + pt[0] * iw * s_, oy + pt[1] * ih * s_)

        index_of = {n: i for i, n in enumerate(self._overlay_order)}
        plain = QColor(TOKENS["accent"])

        def role_of(i: int) -> str:
            return (self._mark_labels[i] if i < len(self._mark_labels) else "")

        def colour_of(i: int) -> QColor:
            name = role_of(i)
            token = MARK_ROLE_TOKENS.get(name)
            if token:
                return QColor(TOKENS[token])
            return (QColor(region_hex(index_of[name])) if name in index_of
                    else plain)

        strong = self._marks_solid
        for i, (a, b) in enumerate(self._marks):
            focused = (i in self._mark_focus) or strong
            col = colour_of(i)
            if not focused:
                col = QColor(col)
                col.setAlpha(70)
            heavy = MARK_ROLE_WEIGHTS.get(role_of(i))
            pen = QPen(col, heavy if (heavy and focused)
                       else (2.2 if strong else (1.6 if focused else 1.0)))
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(at(a), at(b))
        p.setPen(Qt.NoPen)
        for i, grp in enumerate(self._mark_points):
            focused = (i in self._mark_focus) or strong
            col = colour_of(i)
            if not focused:
                col = QColor(col)
                col.setAlpha(70)
            p.setBrush(QBrush(col))
            r = 2.6 if focused else 1.5
            for pt in grp:
                p.drawEllipse(at(pt), r, r)
        p.setBrush(Qt.NoBrush)

    def _paint_measure(self, p: QPainter) -> None:
        """量測尺按著時的那一條帶：兩條綠線 + 中間一層很淡的綠。

        畫在 ROI 框**之後**，因為它是「使用者手上正在做的事」—— 被框壓住的話
        就得先找它在哪。顏色跟框刻意不同色相（框是 accent，尺是綠）：兩者同時
        在畫面上，而「哪一條是我剛剛拉的」不能只靠深淺分辨。
        """
        if self._pixmap is None or self._measure is None:
            return
        axis, a, b = self._measure
        iw, ih = self._pixmap.width(), self._pixmap.height()
        s = self._scale or 1.0
        if axis == "x":
            band = QRectF(self._offset.x() + a * s, self._offset.y(),
                          max(1.0, (b - a) * s), ih * s)
        else:
            band = QRectF(self._offset.x(), self._offset.y() + a * s,
                          iw * s, max(1.0, (b - a) * s))
        green = QColor(TOKENS["success"])
        fill = QColor(green)
        fill.setAlpha(48)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawRect(band)
        pen = QPen(green, 1.6)
        pen.setCosmetic(True)          # 縮到很小時線不能跟著消失
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if axis == "x":
            for x in (band.left(), band.right()):
                p.drawLine(QPointF(x, band.top()), QPointF(x, band.bottom()))
        else:
            for y in (band.top(), band.bottom()):
                p.drawLine(QPointF(band.left(), y), QPointF(band.right(), y))

    def _paint_kernel(self, p: QPainter) -> None:
        """核心大小的方框：虛線 + 一個寫著幾像素的標籤。

        虛線是刻意的：ROI 框（實線 accent）與量測尺（實線綠）都是「資料上的東西」，
        這一個是**尺規**。三者可能同時在畫面上，而使用者要分得出哪一個是他剛剛
        拖出來的。
        """
        if self._pixmap is None or self._kernel is None:
            return
        n, label = self._kernel
        s = self._scale or 1.0
        iw, ih = self._pixmap.width(), self._pixmap.height()
        side = n * s
        cx = self._offset.x() + iw * s / 2.0
        cy = self._offset.y() + ih * s / 2.0
        box = QRectF(cx - side / 2.0, cy - side / 2.0, side, side)
        col = QColor(TOKENS["min_accent"])
        pen = QPen(col, 1.4, Qt.DashLine)
        pen.setCosmetic(True)          # 縮很小的時候線不能跟著消失
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(box)
        if not label:
            return
        # 標籤貼在框的上緣外側；框比畫布還大時（核心開到比影像大）就貼回畫布內，
        # 不然那個數字會被裁掉 —— 而「核心比整張圖還大」正是最需要看到它的時候。
        tw, th = 74.0, 14.0
        ty = box.top() - th - 2.0
        if ty < 2.0:
            ty = min(self.height() - th - 2.0, box.top() + 2.0)
        p.setPen(col)
        p.drawText(QRectF(box.center().x() - tw / 2.0, ty, tw, th),
                   Qt.AlignCenter, label)

    def _to_image(self, p: QPointF) -> QPointF:
        s = self._scale or 1.0
        return QPointF((p.x() - self._offset.x()) / s,
                       (p.y() - self._offset.y()) / s)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        # 中性灰底：不隨主題變，也不讓背景偏移對灰階的判斷（見 theme 的
        # image_backdrop 說明）
        p.setBrush(QColor(TOKENS["image_backdrop"]))
        p.drawRoundedRect(rect, 6, 6)
        if self._pixmap is None:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(self.rect(), Qt.AlignCenter, self._EMPTY_TEXT)
            p.end()
            return
        # scale > 1 -> nearest neighbour（像素銳利）；縮小才用平滑取樣（防摩爾紋）
        p.setRenderHint(QPainter.SmoothPixmapTransform, self._scale <= 1.0)
        target = QRectF(self._offset.x(), self._offset.y(),
                        self._pixmap.width() * self._scale,
                        self._pixmap.height() * self._scale)
        p.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self._paint_overlay(p)
        self._paint_marks(p)
        self._paint_measure(p)
        self._paint_kernel(p)
        p.end()

    # -- interaction -------------------------------------------------------
    def wheelEvent(self, e) -> None:
        if self._pixmap is None:
            return
        delta = e.angleDelta().y()
        if delta == 0:
            return
        self.zoom_by(1.15 if delta > 0 else 1 / 1.15, QPointF(e.position()))
        e.accept()

    def mousePressEvent(self, e) -> None:
        if self._pixmap is None:
            return
        if e.button() in (Qt.LeftButton, Qt.MiddleButton, Qt.RightButton):
            self._panning = True
            self._pan_start = QPointF(e.position())
            self._pan_offset = QPointF(self._offset)
            self._auto_fit = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:
        pos = QPointF(e.position())
        if self._panning:
            self._offset = self._pan_offset + (pos - self._pan_start)
            self.update()
            self.view_changed.emit(self._scale, QPointF(self._offset))
            return
        self._emit_cursor(pos)

    def mouseReleaseEvent(self, _e) -> None:
        if self._panning:
            self._panning = False
            self.unsetCursor()

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.fit()

    def leaveEvent(self, _e) -> None:
        self.cursor_info.emit("")

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self._auto_fit:
            self.fit()

    def _emit_cursor(self, pos: QPointF) -> None:
        if self._image is None:
            self.cursor_info.emit("")
            return
        ip = self._to_image(pos)
        x, y = int(math.floor(ip.x())), int(math.floor(ip.y()))
        h, w = self._image.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            v = self._image[y, x]
            gray = int(v) if np.ndim(v) == 0 else int(np.mean(v))
            self.cursor_info.emit(f"x {x}  y {y}  ·  gray {gray}")
        else:
            self.cursor_info.emit("")


# --------------------------------------------------------------------------- #
# 2. ParamForm
# --------------------------------------------------------------------------- #
#: 浮點滑桿的內部刻度數。滑桿只吃 int，所以 min..max 一律映射到 0..這個數。
#: 1000 格對 gamma（0.1–5）約是 0.005 一格 —— 拖起來連續，又不會抖到看不出。
_SLIDER_TICKS = 1000

#: 整數參數的滑桿上限跨度。超過這個跨度就不給滑桿（一格好幾十，拖了也沒用），
#: 留純數字框比較誠實。
_SLIDER_MAX_INT_SPAN = 5000


class _HintLabel(QLabel):
    """列面上那句「非讀不可」的字（錯誤／不生效註記）。

    歷史：F7-15 它是常駐的參數說明（一行、hover 攤開），2026-08-14 說明整段
    搬進 tooltip —— hover 攤開/收合跟著滑鼠此起彼落地閃，比一面牆更亂。
    現在這個 label 平常是隱藏的，只在「有一句話必須讀完」時出現，而且出現
    就是整段（``set_expanded(True)``）。收合模式留著給還需要它的呼叫端；
    收合時切字自己算（``elidedText``），不交給 Qt 裁 —— Qt 會硬切在字的
    中間，看起來像畫面壞掉（同 canvas 的 ``_draw_elided``）。
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("paramHint")
        self._full = str(text)
        self._expanded = False
        self.setWordWrap(False)
        self._sync()

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = str(text)
        self._sync()

    def set_expanded(self, expanded: bool) -> None:
        if bool(expanded) != self._expanded:
            self._expanded = bool(expanded)
            self._sync()

    def is_expanded(self) -> bool:
        return self._expanded

    def resizeEvent(self, e) -> None:          # noqa: D102 - Qt hook
        super().resizeEvent(e)
        if not self._expanded:
            self._sync()

    def _sync(self) -> None:
        if self._expanded:
            self.setWordWrap(True)
            super().setText(self._full)
            return
        self.setWordWrap(False)
        w = max(40, self.width())
        super().setText(self.fontMetrics().elidedText(
            self._full, Qt.ElideRight, w))


#: 這幾種編輯器是**一整塊**，不是一行 —— 它們那一列的名字要對齊到最上面。
#:
#: 為什麼要列出來而不是量 widget 的高度：``sizeHint`` 在建構的當下還沒定案
#: （膠囊要排版完才知道會不會換行），量到的會是一個還沒長好的數字。
_BLOCK_EDITORS = ("metric_chips", "metric_choice", "multi_choice",
                  "chip_choice", "curve", "template",
                  "channel_map", "cell_rois")


class _ParamRow(QFrame):
    """一個參數 = 一列（名稱 + 滑桿 + 數字框）。說明住在 tooltip 裡。

    為什麼有上下界的數字都配一支滑桿（F7-8）
    ----------------------------------------
    「gamma 要填多少」對不會寫 code 的人是個沒有答案的問題 —— 他要的是
    **一邊拖一邊看圖**。數字框逼人先想好一個數字再輸入，那個順序是反的。

    數字框沒有被拿掉，是刻意的：滑桿負責找到大概的位置，數字框負責記錄與
    重現（recipe 是要交接給別人的）。兩邊雙向綁定，改哪一邊另一邊都會跟上。

    說明文字為什麼不畫在列的下面（2026-08-14，取代 F7-15 的 hover 攤開）
    ------------------------------------------------------------------
    F7-15 把說明收成一行、hover 才攤開 —— 但攤開/收合跟著滑鼠此起彼落，
    使用者的形容是「移過去會顯示、移走又消失，很亂」。說明整段搬進
    tooltip（整列都感應，停上去就看得到全文），列面上只留兩種**非讀不可**
    的字：紅色錯誤（驗證擋下來的原因）與「這一格現在不生效」的調淡註記。
    那兩種不是說明，是狀態 —— 出現就攤開整段，不玩收合。
    """

    def __init__(self, spec: Dict[str, Any], editor: QWidget,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.spec = spec
        self.editor = editor
        self.slider: Optional[QSlider] = None
        self._dim_note = ""
        self.setObjectName("paramRow")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 6)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        # 顯示名優先用 ``label``（F7-9）。``name`` 是 recipe JSON 的鍵，
        # 對使用者來說 ``range_from`` 不是一句話，"Borrow range from" 才是。
        self.name_label = QLabel(str(spec.get("label") or spec.get("name", "")))
        self.name_label.setObjectName("paramLabel")
        self.name_label.setMinimumWidth(104)
        # **重複自己的小標題的那個名字要拿掉。** CD 的膠囊那一格 `label` 與
        # `section` 都是 "Report"，於是畫面上同一個字出現兩次 —— 而下面那條
        # 對齊的規矩會讓它落在群組區塊的**中間那一列**旁邊，讀起來像是一個叫
        # 「Report」的群（截圖出來才看到：Size 的第二排看起來屬於它）。
        # 比對前先剝掉小標題的編號（"3 · Compare with" → "Compare with"，
        # F32）：編號是段落的座標不是名字，留著比的話「段標題正下方再寫一次
        # 同名列標籤」這種重複只有沒編號的段抓得到。
        label_txt = str(spec.get("label") or "").strip()
        section_txt = re.sub(r"^\d+\s*·\s*", "",
                             str(spec.get("section") or "").strip())
        self._label_is_echo = bool(label_txt and label_txt == section_txt)
        if self._label_is_echo:
            self.name_label.hide()
        else:
            top.addWidget(self.name_label)
        # **一整塊的編輯器，名字要對齊到最上面。** 垂直置中的話那個名字會落在
        # 區塊中間的某一列上，而那一列有它自己的意思（群名、第幾條曲線…）。
        if str(spec.get("type") or "") in _BLOCK_EDITORS:
            top.setAlignment(self.name_label, Qt.AlignTop)
            self.name_label.setContentsMargins(0, 6, 0, 0)
        if str(spec.get("type") or "") == "chip_choice":
            # **長的列名要換行，不要把膠囊擠扁**（F68 第二輪）。
            # 「Take the up-and-down stripes that are」把那一列的名字撐到
            # 三百多 px，剩給七顆膠囊的寬度不到一半 —— 它們於是排成五排
            # 參差不齊的東西（render 出來才看到）。名字是一欄，膠囊是一塊。
            self.name_label.setWordWrap(True)
            self.name_label.setMaximumWidth(152)

        self.slider = _make_slider(spec, editor)
        if self.slider is not None:
            top.addWidget(self.slider, 1)
            editor.setMaximumWidth(96)
            top.addWidget(editor, 0)
        else:
            top.addWidget(editor, 1)
        lay.addLayout(top)

        self.hint = _HintLabel(str(spec.get("help", "")), self)
        self.hint.setProperty("error", "false")
        # 出現的時候一定是「必須讀完的一句話」（錯誤／不生效註記），
        # 所以永遠整段攤開；平常整列收起來只有一行高。
        self.hint.set_expanded(True)
        self.hint.hide()
        lay.addWidget(self.hint)

        # 說明全文住在 tooltip：整列（含名稱與空白處）都感應得到。
        tip = str(spec.get("help", ""))
        if tip:
            self.setToolTip(tip)
            self.name_label.setToolTip(tip)

    def set_error(self, msg: Optional[str]) -> None:
        if msg:
            self.hint.set_full_text("⚠ " + str(msg))
            self.hint.setProperty("error", "true")
            self.hint.setStyleSheet(
                "color:%s; font-size:11px; font-weight:600;" % TOKENS["danger_text"])
            self.hint.show()
        else:
            self.hint.setProperty("error", "false")
            self._show_dim_note_or_hide()
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)

    def has_error(self) -> bool:
        return self.hint.property("error") == "true"

    def hint_visible(self) -> bool:
        """列面上現在有沒有一句攤開的字（**明確狀態**，不問 ``isVisible()``）。"""
        return not self.hint.isHidden()

    def set_dimmed(self, dimmed: bool, why: str = "") -> None:
        """把整列調淡（值還在、還能改，只是現在不生效）。

        用在「另一個參數接管了這一個」的情況 —— 例如畫了曲線之後 gamma
        就不再被用到。不 disable 是刻意的：使用者可能只是想比較兩種做法，
        把它鎖死會逼他先把曲線拉平才改得動 gamma。
        """
        self.setProperty("dimmed", "true" if dimmed else "false")
        self.setEnabled(True)
        self.name_label.setStyleSheet(
            "color:%s;" % (TOKENS["text_disabled"] if dimmed
                           else TOKENS["text_primary"]))
        self._dim_note = str(why) if (dimmed and why) else ""
        if not self.has_error():
            self._show_dim_note_or_hide()

    def _show_dim_note_or_hide(self) -> None:
        """沒有錯誤的時候，列面上唯一可能出現的字是「不生效」註記。"""
        if self._dim_note:
            self.hint.set_full_text("· " + self._dim_note)
            self.hint.setStyleSheet("color:%s; font-size:11px; font-style:italic;"
                                    % TOKENS["text_disabled"])
            self.hint.show()
        else:
            self.hint.set_full_text(str(self.spec.get("help", "")))
            self.hint.setStyleSheet("color:%s; font-size:11px;" % TOKENS["text_hint"])
            self.hint.hide()


def _make_slider(spec: Dict[str, Any], editor: QWidget) -> Optional[QSlider]:
    """有上下界的 int / float 參數 → 一支跟數字框雙向綁定的滑桿。

    回 ``None`` 表示這個參數不適合滑桿（沒界、跨度是 0、或整數跨度大到
    一格好幾十）。這樣新卡片只要把 min/max 填好就自動有滑桿，
    不必逐張卡去 UI 這邊登記。
    """
    ptype = str(spec.get("type", ""))
    lo, hi = spec.get("min"), spec.get("max")
    if ptype not in ("int", "float") or lo is None or hi is None:
        return None
    lo, hi = float(lo), float(hi)
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return None

    s = QSlider(Qt.Horizontal)
    s.setObjectName("paramSlider")
    s.setToolTip(str(spec.get("help", "")))
    guard = {"busy": False}

    if ptype == "int":
        if hi - lo > _SLIDER_MAX_INT_SPAN:
            return None
        s.setRange(int(lo), int(hi))
        s.setValue(int(editor.value()))

        def from_slider(v: int) -> None:
            if guard["busy"]:
                return
            guard["busy"] = True
            editor.setValue(int(v))
            guard["busy"] = False

        def from_box(v: int) -> None:
            if guard["busy"]:
                return
            guard["busy"] = True
            s.setValue(int(v))
            guard["busy"] = False
    else:
        s.setRange(0, _SLIDER_TICKS)
        span = hi - lo

        def to_tick(v: float) -> int:
            return int(round((float(v) - lo) / span * _SLIDER_TICKS))

        s.setValue(to_tick(editor.value()))

        def from_slider(v: int) -> None:      # noqa: F811 — 兩型別各一份
            if guard["busy"]:
                return
            guard["busy"] = True
            editor.setValue(lo + (float(v) / _SLIDER_TICKS) * span)
            guard["busy"] = False

        def from_box(v: float) -> None:       # noqa: F811
            if guard["busy"]:
                return
            guard["busy"] = True
            s.setValue(to_tick(v))
            guard["busy"] = False

    # 兩邊互相回寫會無限來回（float 還會因為取整而每次都差一點點），
    # 所以用 guard 擋住「因我而起的那一次回呼」。
    s.valueChanged.connect(from_slider)
    editor.valueChanged.connect(from_box)
    return s


class ProfilePanel(QWidget):
    """投影定位的曲線面板（F7-11）：曲線、轉折線、選中的那一段、中心線。

    為什麼這張卡沒有這個面板就不成立
    --------------------------------
    「敏感度要調多少」對不會寫 code 的人是一個沒有答案的問題 —— 除非他看得到
    曲線、看得到目前抓到幾條線、看得到抓到的線是不是落在他預期的地方。
    沒有這個面板，這張卡就只是另一個要盲填的數字。

    **畫的資料來自引擎那一次計算**（step 卡把它放進 ``ctx.meta["profiles"]``），
    UI 不自己再算一次。不然「畫面上的框」跟「真的量下去的框」會不一樣，
    而那種 bug 幾乎不可能靠肉眼發現。
    """

    #: 量測尺按著時，這一段量到哪裡（axis, 起, 迄；單位是**影像像素**）。
    #: 上面那張影像靠它同步標出同一段 —— 見 :meth:`ImageView.set_measure`。
    measure_changed = Signal(str, float, float)
    #: 放開了。標記要跟著消失，它是「現在正在量」的回饋不是註記。
    measure_ended = Signal()
    #: 「把量到的間距填進參數格」（axis, pitch, 第二個 pitch）。
    #: 使用者原話：「有辦法自動 measure 填入左側數值嗎」。曲線本來就知道答案，
    #: 而要他看著面板上的數字再手動打一次，是在製造一個可以打錯的機會。
    pitch_requested = Signal(str, float, float)
    #: 「用這一種材質」（axis, select 的值）—— 使用者**點了曲線上的一根條紋**。
    #:
    #: 為什麼這件事要能用點的（F11 Region-2b）：使用者的話是「能用圖就用圖」，
    #: 而 ``second_brightest`` 這個詞本身不告訴他任何事 —— 「哪一組是第二亮的」
    #: 是一個只有看圖才答得出來的問題，而圖就在這裡。分群由引擎給
    #: （``algo/grid.band_groups``），面板不自己分。
    select_requested = Signal(str, str)

    _EMPTY = "(select a Profile card to see its curve)"

    #: 每一群的底色（依群號輪流）。用**顏色**而不是深淺：深淺會跟曲線下面的
    #: 灰階混在一起，而這裡要講的是「這幾根是同一種東西」。
    GROUP_COLORS = ("#3574d6", "#c2871f", "#7a68a6", "#3f9d6b", "#d05a4c")

    #: 拖多少個取樣點以內算「點一下」而不是「拖了一段」。
    CLICK_SLOP = 1.5

    #: 底部那條分群色帶有多高（畫面像素）。
    GROUP_BAR = 5.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data: Dict[str, Any] = {}
        self._name = ""
        self._ruler: Optional[Tuple[float, float]] = None
        self._pressed_at: Optional[float] = None
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(
            "Gray level projected along the scan direction.\n\n"
            "The thin upright lines are the edges found in this image. The "
            "shaded blocks are the stripes the card will actually use - which "
            "is not the same thing: the edges are refined to sub-pixel, and if "
            "you filled in a pitch the stripes are then snapped onto that "
            "regular grid. So the blocks can sit a pixel or two off the lines, "
            "and the summary says how far.\n\n"
            "The dashed line marked 'defect' is the middle of the patch, which "
            "is where the tool put the defect - a marker, not a setting.\n\n"
            "Click a stripe to use that material — the colours are the groups "
            "the card found, and the solid one is the group it is using now.\n\n"
            "Press and drag across the curve to measure: the green band shows "
            "the same stretch on the image above, and the readout gives the "
            "distance in pixels - and the pitch, if you dragged across more "
            "than one stripe. Let go to clear it.")

        # 「量給我填」。浮在面板上（同 kind="icon" 那幾顆的理由：這裡沒有卡片
        # 當底色）。只有在**它會改變什麼**的時候才出現 —— 見 _sync_button。
        # ⚠ shape 一定要 "wide"：square 的 QSS 是 max-width 22px，文字按鈕
        # 放進去只剩「Use 4…」—— 使用者回報「只看得到一半的數字」就是它。
        self._fill_btn = small_button("", shape="wide", kind="icon",
                                      parent=self)
        self._fill_btn.setVisible(False)
        self._fill_btn.clicked.connect(self._request_pitch)

    # -- public ------------------------------------------------------------
    def set_data(self, name: str, data: Optional[Dict[str, Any]]) -> None:
        self._name = str(name or "")
        self._data = dict(data or {})
        self._sync_button()
        self._end_ruler()
        self.setCursor(Qt.CrossCursor if self.has_data() else Qt.ArrowCursor)
        self.update()

    def has_data(self) -> bool:
        return bool(self._data.get("profile"))

    # -- 「量給我填」 ------------------------------------------------------
    def measured_pitches(self) -> Tuple[float, float]:
        """這條曲線量到的間距（第二個是 0 代表不交錯）。"""
        return (float(self._data.get("pitch_measured") or 0.0),
                float(self._data.get("pitch_measured_2") or 0.0))

    def fill_button_text(self) -> str:
        """按鈕上的字（空字串 = 這時候不該有按鈕）。"""
        a, b = self.measured_pitches()
        if a < 2.0:
            return ""
        used = [float(v) for v in (self._data.get("pitches_used") or [])]
        want = [round(v, 1) for v in ((a, b) if b >= 2.0 else (a,))]
        if [round(v, 1) for v in used] == want:
            return ""            # 已經是這個值了 —— 按了什麼都不會變
        return ("Use %s px" % " / ".join("%.1f" % v for v in want))

    def _request_pitch(self) -> None:
        a, b = self.measured_pitches()
        if a >= 2.0:
            self.pitch_requested.emit(self.axis(), a, b if b >= 2.0 else 0.0)

    def _sync_button(self) -> None:
        text = self.fill_button_text()
        self._fill_btn.setText(text)
        self._fill_btn.setVisible(bool(text))
        self._fill_btn.setToolTip(
            "Put the spacing measured on this curve into the pitch box for "
            "this direction. Use it when you do not know the pitch from the "
            "layout - once it is filled in, the card can check what it finds, "
            "fill in stripes that were too faint, and lock on from a single "
            "stripe." if text else "")
        if text:
            self._fill_btn.adjustSize()
            self._place_button()

    def _place_button(self) -> None:
        b = self._fill_btn
        b.move(max(2, self.width() - b.width() - 10), 4)

    def resizeEvent(self, e) -> None:      # noqa: D102 - Qt hook
        super().resizeEvent(e)
        self._place_button()

    # -- ruler (F8) --------------------------------------------------------
    def axis(self) -> str:
        """這條曲線是哪一軸的投影（``"x"`` 直的條紋／``"y"`` 橫的）。"""
        return str(self._data.get("axis") or "")

    def ruler_span(self) -> Optional[Tuple[float, float]]:
        """量測尺現在夾住的那一段（起 ≤ 迄，影像像素）；沒在量就 None。"""
        if self._ruler is None:
            return None
        a, b = self._ruler
        return (min(a, b), max(a, b))

    def ruler_text(self) -> str:
        """量測尺的讀數。

        為什麼不只講「幾個像素」
        ----------------------
        使用者拉這一把的目的多半是**問出 pitch**（他不知道 pitch 是多少，
        所以才要量）。而「量一個週期」是所有量法裡最不準的一種 —— 兩端各差
        一個像素，pitch 就差兩個。橫跨好幾根條紋再除以根數，誤差就被根數除掉。
        所以只要這一段裡有兩根以上抓到的條紋，就順便把 pitch 算給他。
        """
        span = self.ruler_span()
        if span is None:
            return ""
        a, b = span
        bits = ["%.1f px" % (b - a)]
        mids = self._centers_in(a, b)
        if len(mids) >= 2:
            bits.append("%d stripes" % len(mids))
            bits.append("pitch %.1f px" % ((mids[-1] - mids[0]) / (len(mids) - 1)))
        return " · ".join(bits)

    def groups(self) -> List[int]:
        """每一段屬於第幾群（引擎算的，見 ``algo/grid.band_groups``）。"""
        return [int(g) for g in (self._data.get("groups") or [])]

    def group_rules(self) -> Dict[int, str]:
        """群號 → 要填進 ``select`` 的值。"""
        return {int(k): str(v)
                for k, v in (self._data.get("group_rules") or {}).items()}

    def group_at(self, index: float) -> Optional[int]:
        """曲線上第 ``index`` 個取樣點落在哪一群（不在任何段裡回 ``None``）。"""
        bands = self._data.get("bands") or []
        groups = self.groups()
        if len(groups) != len(bands):
            return None
        for (a, b), g in zip(bands, groups):
            if float(a) <= float(index) <= float(b):
                return int(g)
        return None

    def rule_at(self, index: float) -> str:
        """點在這裡的話，``select`` 要填什麼（沒有答案就空字串）。"""
        g = self.group_at(index)
        return self.group_rules().get(g, "") if g is not None else ""

    def _centers_in(self, a: float, b: float) -> List[float]:
        """這一段裡有幾根條紋的**中心**（用中心不用邊，邊有升有降會多算一倍）。"""
        bands = self._data.get("selected") or self._data.get("bands") or []
        out = []
        for band in bands:
            try:
                mid = (float(band[0]) + float(band[1])) / 2.0
            except (TypeError, IndexError, ValueError):
                continue
            if a <= mid <= b:
                out.append(mid)
        return sorted(out)

    def _plot_rect(self) -> QRectF:
        """曲線畫在哪一塊。

        **繪製與命中判定共用這一個** —— 兩邊各自算一次的話，量測尺會跟曲線
        差幾個像素，而那種偏差肉眼看不出來卻會讓讀數一直是錯的。
        """
        return QRectF(self.rect()).adjusted(6, 6, -6, -6).adjusted(4, 16, -4, -4)

    def _index_at(self, x: float) -> float:
        """widget 的 x 座標 → 曲線上的取樣點（= 影像像素）。"""
        n = len(self._data.get("profile") or [])
        plot = self._plot_rect()
        if n < 2 or plot.width() <= 0:
            return 0.0
        t = (float(x) - plot.left()) / plot.width()
        return max(0.0, min(float(n - 1), t * (n - 1)))

    def _end_ruler(self) -> None:
        if self._ruler is not None:
            self._ruler = None
            self.measure_ended.emit()
            self.update()

    def _emit_ruler(self) -> None:
        span = self.ruler_span()
        if span is not None:
            self.measure_changed.emit(self.axis(), span[0], span[1])

    def mousePressEvent(self, e) -> None:          # noqa: D102 - Qt hook
        if e.button() != Qt.LeftButton or not self.has_data():
            return
        i = self._index_at(e.position().x())
        self._ruler = (i, i)
        self._pressed_at = i          # 放開時用來分辨「點一下」與「拖了一段」
        self._emit_ruler()
        self.update()
        e.accept()

    def mouseMoveEvent(self, e) -> None:           # noqa: D102 - Qt hook
        if self._ruler is None:
            return
        self._ruler = (self._ruler[0], self._index_at(e.position().x()))
        self._emit_ruler()
        self.update()
        e.accept()

    def mouseReleaseEvent(self, e) -> None:        # noqa: D102 - Qt hook
        if e.button() != Qt.LeftButton or self._ruler is None:
            return
        span = abs(self._ruler[1] - self._ruler[0])
        at = self._pressed_at
        self._end_ruler()
        # **點一下 = 選這一種材質；拖一段 = 量尺。** 同一個手勢兩種意思會很糟，
        # 所以用「有沒有移動」分開 —— 那是使用者本來就分得出來的兩件事，
        # 而尺本來就要拖過一段才有意義（0 寬的尺量不出東西）。
        if span <= self.CLICK_SLOP and at is not None:
            rule = self.rule_at(at)
            if rule:
                self.select_requested.emit(self.axis(), rule)
        e.accept()

    def summary(self) -> str:
        """一行文字摘要（測試與狀態列都用這個，不用去讀畫素）。"""
        if not self.has_data():
            return ""
        d = self._data
        if d.get("selected"):
            # 交會定位：講的是「這個方向抓到幾根條紋、間距多少」——
            # 而不是「挑了哪一段」，因為它一整排都要。
            bits = ["%s · %d stripes" % (self._name, len(d["selected"]))]
            pitch = float(d.get("pitch_used") or 0.0)
            if pitch > 0:
                bits.append("pitch %.1f px" % pitch)
            if d.get("width_fixed"):
                # 只有**給定**的線寬才講。量到的線寬畫面上已經看得到（就是塗
                # 起來的那幾段有多寬），而給定的那個是使用者填進去的假設 ——
                # 假設要看得到才驗得了。
                bits.append("width %.1f px (given)"
                            % float(d.get("width_used") or 0.0))
            filled = int(d.get("filled") or 0)
            if filled:
                # 這幾根影像上看不到，是靠已知 pitch 推出來的。框仍然對，
                # 但「憑什麼對」換了一個依據 —— 使用者有權知道。
                bits.append("%d filled in" % filled)
            shift = float(d.get("snap_shift") or 0.0)
            if shift >= 0.5:
                # 使用者原話：「藍框跟線有時候會 shift」。它是刻意的（次像素
                # 精修 + 對齊到你給的 pitch），但沒講出來就只是「怪」，
                # 而「怪」的下一步通常是去亂調敏感度。
                bits.append("snapped %.1f px" % shift)
            if d.get("pitch_disagrees"):
                # 最重要的一句 —— 它是「這一顆能不能信」的答案。放在
                # confidence 前面，因為那個數字在這種失敗上反而更高。
                bits.append("⚠ measured %.0f%% of the pitch you gave"
                            % (float(d.get("pitch_ratio") or 0.0) * 100.0))
            trust = str(d.get("trust_note") or "")
            if trust:
                # 最重要的一句：這個方向的定位不能信，而且**為什麼**。
                # 它排在最前面 —— 後面那些數字在這種失敗上全都看起來正常。
                bits = [bits[0], "⚠ " + trust]
            note = str(d.get("pitch_note") or "")
            if note:
                # 給了 pitch 卻沒有用 —— 這件事一定要講。使用者會以為那格
                # 生效了，然後拿一份其實是「照影像自己量」的結果去跑整批。
                bits.append("pitch not used: %s" % note)
            blocked = len(d.get("blocked") or ())
            if blocked:
                # 「這一格我故意不放」跟「這一格我沒找到」在畫面上長得一模一樣。
                # 少了這句，使用者會以為那裡定位失敗，然後去調敏感度。
                bits.append("%d left out" % blocked)
            bits.append("confidence %.1f" % float(d.get("confidence", 0.0)))
            return " · ".join(bits)
        picked = d.get("picked")
        where = ("none" if not picked
                 else "%d-%d px" % (int(picked[0]), int(picked[1])))
        return ("%s · %d boundaries · %d sections · picked %s · confidence %.1f"
                % (self._name, len(d.get("transitions") or []),
                   len(d.get("bands") or []), where,
                   float(d.get("confidence", 0.0))))

    # -- paint -------------------------------------------------------------
    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        p.fillRect(QRectF(self.rect()), QColor(TOKENS["bg_surface"]))
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.drawRoundedRect(rect, 4, 4)

        prof = [float(v) for v in (self._data.get("profile") or [])]
        if len(prof) < 2:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(rect, Qt.AlignCenter, self._EMPTY)
            p.end()
            return

        n = len(prof)
        raw = [float(v) for v in (self._data.get("raw") or [])]
        lo = min(min(prof), min(raw) if raw else min(prof))
        hi = max(max(prof), max(raw) if raw else max(prof))
        span = max(hi - lo, 1e-6)
        plot = self._plot_rect()

        def to_x(i: float) -> float:
            return plot.left() + plot.width() * (float(i) / max(1, n - 1))

        def to_y(v: float) -> float:
            return plot.bottom() - plot.height() * ((v - lo) / span)

        # 選中的段：先畫底色，曲線才會壓在上面。
        # ``picked`` 是一段（投影定位），``selected`` 是**好幾段**（交會定位
        # 的那一組條紋）—— 兩者都畫得出來，因為只畫其中一段的話，面板就會
        # 少講「這張卡其實用到了這一整排」。
        shaded = self._data.get("selected")
        if not shaded:
            one = self._data.get("picked")
            shaded = [one] if one else []
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TOKENS["accent_bg"]))
        for band in shaded:
            x0, x1 = to_x(int(band[0])), to_x(int(band[1]))
            p.drawRect(QRectF(x0, plot.top(), max(1.0, x1 - x0), plot.height()))

        # **底部的一條色帶：每一群一個顏色**（F11 Region-2b）。
        #
        # 「哪一組是第二亮的」是一個只有看圖才答得出來的問題，而
        # ``second_brightest`` 這個詞本身不告訴使用者任何事 —— 所以把分群畫出來。
        # 分群是引擎算的（``algo/grid.band_groups``），面板不自己分。
        #
        # 為什麼是**底部一條細帶**而不是整段上色：整段上色會把「現在用的是哪
        # 一組」那個既有的塗色淹掉（實測：塗滿之後兩者只剩 alpha 的差別），
        # 而且畫面會變得很吵。色帶回答「有幾種、哪一種是哪一種」，塗色回答
        # 「現在用的是哪一種」—— 兩個問題，兩個位置。
        bands = self._data.get("bands") or []
        groups = self.groups()
        if len(groups) == len(bands) and bands:
            picked_group = self._data.get("group_picked")
            p.setPen(Qt.NoPen)
            for band, g in zip(bands, groups):
                on = (g == picked_group)
                col = QColor(self.GROUP_COLORS[int(g) % len(self.GROUP_COLORS)])
                # 沒被選中的那幾群要**很淡**：空隙那一群通常最寬，照一樣的濃度
                # 畫會把整條色帶佔滿，而真正要看的「現在用哪一組」反而變成幾根
                # 小點（render 出來確認過）。
                col.setAlpha(255 if on else 70)
                p.setBrush(col)
                x0, x1 = to_x(float(band[0])), to_x(float(band[1]))
                th = self.GROUP_BAR if on else self.GROUP_BAR * 0.45
                p.drawRect(QRectF(x0, plot.bottom() - th,
                                  max(1.0, x1 - x0), th))

        # 晶格上**故意不用**的那幾格（那裡是別的材質）。畫成斜線而不是另一種
        # 底色：它跟選中的段是同一排上的東西，差別在「用不用」，而兩塊實心色
        # 只說得出「這是兩種東西」。
        blocked = self._data.get("blocked") or []
        if blocked:
            hatch = QColor(TOKENS["text_secondary"])
            hatch.setAlpha(90)
            p.setPen(QPen(hatch, 1.0))
            for band in blocked:
                x0, x1 = to_x(float(band[0])), to_x(float(band[1]))
                r = QRectF(x0, plot.top(), max(1.0, x1 - x0), plot.height())
                p.save()
                p.setClipRect(r)
                x = r.left() - r.height()
                while x < r.right():
                    p.drawLine(QPointF(x, r.bottom()),
                               QPointF(x + r.height(), r.top()))
                    x += 4.0
                p.restore()

        # 平滑前的曲線畫在後面當對照 —— 使用者才看得出平滑吃掉了多少
        if len(raw) == n:
            p.setPen(QPen(QColor(TOKENS["border_input"]), 1.0))
            p.setBrush(Qt.NoBrush)
            path = QPainterPath(QPointF(to_x(0), to_y(raw[0])))
            for i in range(1, n):
                path.lineTo(QPointF(to_x(i), to_y(raw[i])))
            p.drawPath(path)

        p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.6))
        path = QPainterPath(QPointF(to_x(0), to_y(prof[0])))
        for i in range(1, n):
            path.lineTo(QPointF(to_x(i), to_y(prof[i])))
        p.drawPath(path)

        # 中心線 = 缺陷的位置（patch 是以缺陷為中心裁的）。
        # **標上字**：它是一條參考線不是一個控制項，而使用者問過「這條線我是
        # 可以做操作的嗎」—— 一條沒有說明的虛線看起來就像可以拖的東西。
        p.setPen(QPen(QColor(TOKENS["text_secondary"]), 1.0, Qt.DashLine))
        cx = to_x((n - 1) / 2.0)
        p.drawLine(QPointF(cx, plot.top()), QPointF(cx, plot.bottom()))
        f = p.font()
        f.setPointSizeF(max(6.0, f.pointSizeF() - 2.0))
        p.setFont(f)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(cx + 3, plot.bottom() - 12, 64, 11),
                   Qt.AlignLeft | Qt.AlignVCenter, "defect")

        p.setPen(QPen(QColor(TOKENS["accent"]), 1.4))
        for t in (self._data.get("transitions") or []):
            # **不要 int()**：轉折位置是次像素的，而條紋的幾何用的就是它。
            # 在這裡捨掉等於畫面上的線跟塗色的方塊差半格，而那半格沒有任何
            # 解釋 —— 使用者會以為是定位歪了。
            x = to_x(float(t))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        self._paint_ruler(p, plot, to_x)

        p.setPen(QColor(TOKENS["text_secondary"]))
        f = p.font()
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        strip = QRectF(rect.left() + 6, rect.top() + 2, rect.width() - 12, 14)
        p.drawText(strip, Qt.AlignVCenter | Qt.AlignLeft, self.summary())
        # 斜線的圖例（PR-2）：畫在同一條 14px 摘要帶的**右側**（那裡是空的，
        # 零幾何改動）。畫一小塊真的斜線 —— 「▨」那種字元在不同字型上長不
        # 一樣，而畫的這一塊跟圖上的斜線是**同一支筆**。會撞到左邊的摘要字
        # 就整組不畫（圖例是輔助，摘要是主角）。
        if self._data.get("blocked"):
            legend = region_words.LEFT_OUT_LEGEND
            fm = QFontMetricsF(p.font())
            need = 12.0 + 4.0 + fm.horizontalAdvance(legend)
            used = fm.horizontalAdvance(self.summary())
            if used + 12.0 + need <= strip.width():
                sw = QRectF(strip.right() - need, strip.top() + 3.0, 12.0, 8.0)
                hatch = QColor(TOKENS["text_secondary"])
                hatch.setAlpha(90)
                p.save()
                p.setPen(QPen(hatch, 1.0))
                p.setClipRect(sw)
                x = sw.left() - sw.height()
                while x < sw.right():
                    p.drawLine(QPointF(x, sw.bottom()),
                               QPointF(x + sw.height(), sw.top()))
                    x += 4.0
                p.restore()
                p.setPen(QColor(TOKENS["text_secondary"]))
                p.drawText(
                    QRectF(sw.right() + 4.0, strip.top(),
                           strip.right() - sw.right() - 4.0, strip.height()),
                    Qt.AlignVCenter | Qt.AlignLeft, legend)
        p.end()

    def _paint_ruler(self, p: QPainter, plot: QRectF, to_x) -> None:
        """量測尺：兩條綠線、中間一層淡綠、加上讀數。

        綠色是刻意跟畫面上其他東西**換一個色相**的：曲線是墨色、轉折線是
        accent、選中的段是 accent 的淡底 —— 量測尺再從那一家挑一個色階的話，
        「哪一條是我剛剛拉的」就只剩深淺可分，而深淺會被主題與縮放吃掉。
        """
        rul = self.ruler_span()
        if rul is None:
            return
        x0, x1 = to_x(rul[0]), to_x(rul[1])
        green = QColor(TOKENS["success"])
        if x1 - x0 >= 1.0:
            fill = QColor(green)
            fill.setAlpha(40)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRect(QRectF(x0, plot.top(), x1 - x0, plot.height()))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(green, 1.4))
        for x in (x0, x1):
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        text = self.ruler_text()
        if not text:
            return
        f = p.font()
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        w = QFontMetricsF(f).horizontalAdvance(text) + 8.0
        # 讀數貼著自己量的那一段（不要放到面板角落 —— 兩條曲線各有一把尺，
        # 放在固定位置的話讀數就得先對回是哪一把）；但不准跑出畫面外。
        left = min(max(plot.left(), min(x0, x1) + 3.0), plot.right() - w)
        p.setPen(green)
        p.drawText(QRectF(left, plot.top() + 1, w, 12),
                   Qt.AlignLeft | Qt.AlignVCenter, text)


class StreamPicker(QWidget):
    """``image_keys`` 參數的編輯器：上游每一條影像流一個勾選框（F7-9）。

    為什麼不是一個輸入框
    --------------------
    「一串影像流」如果是自由文字，三個問題一次到齊 —— 使用者不知道**可以填
    什麼**（流名從來沒有列出來過）、不知道**填了會怎樣**、打錯了也不會被擋。
    勾選框把這三件事一次解掉：能填的就是列出來的那幾個。

    F7-18 之後沒有內建卡片用這個型別
    --------------------------------
    唯一用它的是 Enhance 卡的 ``also_apply``，而那件事已經拆成節點了：
    **一張卡一條流**，要對 ref 也做就再放一張卡接到 ref。留著這個編輯器是因為
    「一串影像流」仍然是 ``ParamSpec`` 的合法型別（見 ``step.PARAM_TYPES``），
    自訂卡片用得到；拿掉它等於要求下一張這種卡自己刻一個表單元件。

    值的格式是逗號分隔字串；recipe 裡指到「現在的 pipeline 沒有這條流」的名字
    也會列出來並勾著，不會因為看不到就被靜靜刪掉。
    """

    changed = Signal(str)

    _EMPTY_TEXT = "(no upstream stream yet — add an Input card first)"

    def __init__(self, streams: Sequence[str], value: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._boxes: List[QCheckBox] = []
        self._emitting = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        picked = [t.strip() for t in str(value or "").split(",") if t.strip()]
        names: List[str] = []
        for name in list(streams) + picked:      # 上游的在前，recipe 帶來的在後
            name = str(name)
            if name and name not in names:
                names.append(name)

        for name in names:
            box = QCheckBox(name, self)
            box.setChecked(name in picked)
            box.toggled.connect(self._on_toggled)
            lay.addWidget(box)
            self._boxes.append(box)
        if not names:
            hint = QLabel(self._EMPTY_TEXT, self)
            hint.setObjectName("paramHint")
            lay.addWidget(hint)
        lay.addStretch(1)

    def text(self) -> str:
        """目前的值（逗號分隔，順序同勾選框）。"""
        return ",".join(b.text() for b in self._boxes if b.isChecked())

    def set_text(self, value: str) -> None:
        picked = {t.strip() for t in str(value or "").split(",") if t.strip()}
        self._emitting = True
        try:
            for box in self._boxes:
                box.setChecked(box.text() in picked)
        finally:
            self._emitting = False

    def stream_names(self) -> List[str]:
        return [b.text() for b in self._boxes]

    def _on_toggled(self, _checked: bool) -> None:
        if not self._emitting:
            self.changed.emit(self.text())


class MultiChoicePicker(QWidget):
    """``multi_choice`` 參數的編輯器：固定選項的勾選網格（2026-08-14）。

    使用者的原話：「支援的量測數值希望是選的而不是用打的。」自由文字的三個
    問題跟 ``StreamPicker`` 那邊一模一樣 —— 不知道能填什麼、不知道填了會怎樣、
    打錯不會被擋。差別只在選項是**卡片宣告的**（``ParamSpec.choices``），
    不是上游流。排成一欄三格的網格 —— 九個統計量排成一橫列會把表單撐爆。

    recipe 帶進來、不在清單上的值（手寫的 ``glv_q37``）照樣列出來並勾著 ——
    看不到就被靜靜刪掉，是最糟的一種「幫忙」。
    """

    changed = Signal(str)
    _PER_ROW = 3

    def __init__(self, choices: Sequence[str], value: str = "",
                 parent: Optional[QWidget] = None, empty_hint: str = ""):
        super().__init__(parent)
        self._boxes: List[QCheckBox] = []
        self._emitting = False

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)

        picked = [t.strip() for t in str(value or "").split(",") if t.strip()]
        names: List[str] = []
        for name in list(choices) + picked:      # 卡片宣告的在前，recipe 的在後
            name = str(name)
            if name and name not in names:
                names.append(name)
        for i, name in enumerate(names):
            box = QCheckBox(name, self)
            box.setChecked(name in picked)
            box.toggled.connect(self._on_toggled)
            grid.addWidget(box, i // self._PER_ROW, i % self._PER_ROW)
            self._boxes.append(box)
        # **一個都沒有的時候要講話**（F15-2）。選項是執行期來的（那一份 KLARF
        # 有哪些欄），所以「還沒掛第二份」是一個正常狀態 —— 而它畫出來是一塊
        # 空白，讀起來像壞掉。
        if not self._boxes and empty_hint:
            hint = QLabel(str(empty_hint), self)
            hint.setEnabled(False)
            hint.setWordWrap(True)
            grid.addWidget(hint, 0, 0, 1, self._PER_ROW)

    def text(self) -> str:
        """目前的值（逗號分隔，順序同勾選框）。"""
        return ",".join(b.text() for b in self._boxes if b.isChecked())

    def set_text(self, value: str) -> None:
        picked = {t.strip() for t in str(value or "").split(",") if t.strip()}
        self._emitting = True
        try:
            for box in self._boxes:
                box.setChecked(box.text() in picked)
        finally:
            self._emitting = False

    def set_choices(self, choices: Sequence[str],
                    value: Optional[str] = None) -> None:
        """換一批選項（F15-2）。``value=None`` = 保留目前勾的。

        為什麼是「換內容」而不是「重建整張表單」：使用者剛在隔壁那一格打字，
        整張重建會把游標搶走。
        """
        keep = self.text() if value is None else str(value)
        grid = self.layout()
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._boxes = []
        picked = [t.strip() for t in keep.split(",") if t.strip()]
        names: List[str] = []
        for name in list(choices) + picked:
            name = str(name)
            if name and name not in names:
                names.append(name)
        self._emitting = True
        try:
            for i, name in enumerate(names):
                box = QCheckBox(name, self)
                box.setChecked(name in picked)
                box.toggled.connect(self._on_toggled)
                grid.addWidget(box, i // self._PER_ROW, i % self._PER_ROW)
                self._boxes.append(box)
        finally:
            self._emitting = False

    def choice_names(self) -> List[str]:
        return [b.text() for b in self._boxes]

    def _on_toggled(self, _checked: bool) -> None:
        if not self._emitting:
            self.changed.emit(self.text())


#: metric id -> (分群, 短標籤, 小圖)。**引擎說有哪些，UI 說長什麼樣**：
#: 「有哪些統計量」的唯一出處是 ``ParamSpec.choices``（卡片宣告的），這裡只
#: 補上分群與怎麼畫。兩份漂開會被 `tests/test_ui_widgets.py` 擋下來。
#:
#: 分群的順序＝畫面上的順序，而它是一句話：**中心 → 離散 → 端點 → 形狀 →
#: 計數**。十四顆平鋪是一面牆；分群之後使用者只要先決定「我要問的是中心還是
#: 離散」，而那個問題他答得出來。
METRIC_GROUPS: Dict[str, Tuple[str, str, str]] = {
    "glv_median": ("Center", "Median", "median"),
    "glv_mean": ("Center", "Mean", "mean"),
    "glv_p50": ("Center", "Median (P50)", "median"),
    "glv_trim10": ("Center", "Trimmed mean", "trimmed"),
    "glv_mad": ("Spread", "MAD", "mad"),
    "glv_std": ("Spread", "Std dev", "std"),
    "glv_iqr": ("Spread", "IQR", "iqr"),
    "glv_min": ("Ends", "Min", "min"),
    "glv_max": ("Ends", "Max", "max"),
    "glv_skew": ("Shape", "Skew", "skew"),
    "glv_kurt": ("Shape", "Kurtosis", "kurtosis"),
    "glv_entropy": ("Shape", "Entropy", "entropy"),
    "glv_bimodality": ("Shape", "Bimodality", "bimodality"),
    "glv_above128": ("Counts", "Above 128", "above"),
    "glv_sat_frac": ("Counts", "Saturated %", "saturated"),
    # 「跟誰比」那一排 —— 同一個 widget、同一種膠囊（F18 補課，2026-08-21）。
    # 使用者：「Compare 跟 absolute 一樣重要，而且它的 Metric 面板 UI 也沒有
    # Statistics 那麼漂亮，我覺得可以改成切換式」。
    #
    # **分成三群不是分成一群**（F18 補課第二輪，使用者：「我覺得 Report 要有
    # 更多統計量可以量」）：九顆膠囊排成一列的時候，「哪幾個需要參照的格子」
    # 這件事在畫面上看不出來 —— 而它正是「為什麼我的 snr 是空的」的答案。
    "delta": ("Difference", "Difference", "delta"),
    "abs_delta": ("Difference", "|Difference|", "abs_delta"),
    "ratio": ("Difference", "Ratio", "ratio"),
    "percent": ("Difference", "Percent", "percent"),
    "contrast": ("Difference", "Contrast", "contrast"),
    "snr": ("Vs boxes", "SNR", "snr"),
    "tstat": ("Vs boxes", "t-stat", "tstat"),
    "pct_rank": ("Vs boxes", "Rank %", "pct_rank"),
    "overlap": ("Distributions", "Overlap", "overlap"),
    "spread_ratio": ("Distributions", "Spread ratio", "spread_ratio"),
    # CD 的 Report（F19）。**分三群不是分成一群**，理由跟上面那一段一字不差：
    # Roughness 那一群只有在量測線夠多的時候才有意義，而那件事在一排攤平的
    # 膠囊上看不出來 —— 它正是「為什麼我的 LER 是 0」的答案。
    "cd_median": ("Width", "Median", "median"),
    "cd_mean": ("Width", "Mean", "mean"),
    "cd_min": ("Width", "Narrowest", "min"),
    "cd_max": ("Width", "Widest", "max"),
    "cd_range": ("Width", "Widest - narrowest", "range"),
    "cd_std": ("Roughness", "LWR (sigma)", "std"),
    "ler_a_std": ("Roughness", "LER one side", "ler_a"),
    "ler_b_std": ("Roughness", "LER other side", "ler_b"),
    "cd_dev": ("Vs target", "Off target", "delta"),
    "cd_dev_frac": ("Vs target", "Off target %", "percent"),
    # CD 的無方向那一支（F19 第二批）。群名用 ``Size`` / ``Outline`` ——
    # **不要用 ``Shape``**，那個字在上面已經是 GLV 的偏度那一群了。
    "cd_area_px": ("Size", "Area", "area"),
    "cd_deq": ("Size", "Equivalent diameter", "deq"),
    "cd_feret_max": ("Size", "Widest across", "feret_max"),
    "cd_feret_min": ("Size", "Narrowest across", "feret_min"),
    # ``aspect`` 重用 ``ratio``：它**本來就是**一個比值，而多畫一顆長得像
    # 「兩個 Feret」的圖示只會跟上面那兩顆撞在一起。
    "cd_aspect": ("Outline", "Long / short", "ratio"),
    "cd_roundness": ("Outline", "Roundness", "roundness"),
}

#: 分群的顯示順序。不在 :data:`METRIC_GROUPS` 裡的 id（手寫 recipe 的
#: ``glv_q37``、``glv_trim05``…）落在最後一群 —— **列出來並且勾著**，因為
#: 「看不到就被靜靜刪掉」是最糟的一種幫忙（同 `MultiChoicePicker` 的老規矩）。
METRIC_GROUP_ORDER = ("Center", "Spread", "Ends", "Shape", "Counts",
                      "Difference", "Vs boxes", "Distributions",
                      "Width", "Roughness", "Vs target",
                      "Size", "Outline", "Other")


def metric_face(mid: str) -> Tuple[str, str, str]:
    """一個 metric id 的（分群, 短標籤, 小圖）—— 沒登記過的也答得出來。"""
    known = METRIC_GROUPS.get(mid)
    if known:
        return known
    q = algo_glv.quantile_of(mid)
    if q is not None:
        return ("Ends", "P%d" % q, "percentile")
    t = algo_glv.trim_of(mid)
    if t is not None:
        return ("Center", "Trimmed %d%%" % t, "trimmed")
    a = algo_glv.above_of(mid)
    if a is not None:
        return ("Counts", "Above %d" % a, "above")
    return ("Other", mid, "percentile")


class _ChipBase(QFrame):
    """一顆膠囊：小圖 + 短標籤，點一下切換選/不選。

    為什麼是自繪而不是 QCheckBox + QSS：選中的狀態要用**階段色**（量測段的
    橙），而那個顏色是算出來的（`theme.group_hex` / `readable_on`），不是主題
    的一個 token —— 走 QSS 的話每換一次主題都要重寫一次樣式表字串。

    這個基底只認得**一顆膠囊長什麼樣**（尺寸、字級、選中的畫法）。「小圖是
    哪一張、字寫什麼、tooltip 講什麼」由子類決定：統計量那一族
    （:class:`_MetricChip`）畫的是分布上的一筆，設定區那一族
    （:class:`_ChoiceChip`）畫的是按鈕圖示。**兩族共用同一個外觀是刻意的**
    —— 使用者 2026-09-01：「我希望設定欄這邊也是能像下方一樣膠囊 icon 配文字，
    這樣 user 比較會有感覺。」抄第二份出來的那份會漂移（這個 repo 記過三次），
    所以外觀只有這一份。
    """

    toggled = Signal(str, bool)

    H = 30
    GLYPH = 19
    #: ⚠ **字級要用 px 並且同時寫進 stylesheet**：QSS 的 ``* { font-size: 13px }``
    #: 會蓋掉 ``setFont``，於是「量寬度用的字」與「畫出來的字」不是同一個 ——
    #: 症狀是膠囊右邊被切掉（第一版的 “Trimmed mean” 少了半個 n）。
    FONT_PX = 11

    #: 虛線框（「這裡還沒有東西」）—— 只有「再加一顆」那種膠囊會打開。
    dashed = False

    #: **按了不自己改狀態**：發出訊號，勾不勾由呼叫端下一次重畫時決定。
    #: 用在 preset 那一排（「照這個意思把線接好」）—— 那一排再按一次不該把它
    #: 取消（取消要回到哪個狀態？沒有答案），而套不上的時候畫面要停在真實
    #: 狀態上，不是停在使用者按下去的那一顆。
    momentary = False

    def __init__(self, mid: str, label: str, colour: str,
                 checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.mid = str(mid)
        self.label = str(label)
        self.colour = str(colour)
        self._checked = bool(checked)
        self._hover = False
        self.setObjectName("metricChip")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self.H)
        f = QFont(self.font())
        f.setPixelSize(self.FONT_PX)
        self.setFont(f)
        self.setStyleSheet("font-size: %dpx;" % self.FONT_PX)
        self.setFixedWidth(int(11 + self.GLYPH + 7
                               + QFontMetricsF(f).horizontalAdvance(self.label)
                               + 15))
        self.setAccessibleName(self.label)

    def draw_glyph(self, p: QPainter, ink: QColor, dim: QColor) -> None:
        """畫這一顆的小圖（子類實作）。"""
        raise NotImplementedError

    # -- 狀態 ---------------------------------------------------------------
    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, on: bool) -> None:
        self._checked = bool(on)
        self.update()

    def set_colour(self, colour: str) -> None:
        self.colour = str(colour)
        self.update()

    # -- Qt hooks -----------------------------------------------------------
    def enterEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        self._hover = False
        self.update()

    def mousePressEvent(self, e) -> None:  # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.click()

    def click(self) -> None:
        """切換這一顆（測試直接呼叫這支，不模擬滑鼠）。

        **灰掉的時候什麼都不做。** Qt 只擋得住滑鼠事件；直接呼叫這支的路
        （測試、鍵盤）擋不到，而「按了灰的鈕居然生效」是最難查的那種。
        """
        if not self.isEnabled():
            return
        if self.momentary:
            self.toggled.emit(self.mid, True)
            return
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self.mid, self._checked)

    def changeEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.type() == QEvent.EnabledChange:
            self.setCursor(Qt.PointingHandCursor if self.isEnabled()
                           else Qt.ArrowCursor)
            self.update()
        super().changeEvent(e)

    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = r.height() / 2.0
        if not self.isEnabled():
            # 灰掉 = **這一格現在還不能答**（例：roi 那條線還沒接）。
            # 選中的那一顆**照樣看得出是選中的**（它是現在的狀態，不是一個
            # 待選項）—— 只是整顆退色。
            bg = QColor(self.colour if self._checked else TOKENS["bg_surface"])
            if self._checked:
                bg.setAlpha(16)
            border = QColor(self.colour if self._checked
                            else TOKENS["border_default"])
            if self._checked:
                border.setAlpha(110)
            ink = QColor(TOKENS["text_disabled"])
            dim = QColor(ink)
            dim.setAlpha(90)
        elif self._checked:
            bg = QColor(self.colour)
            bg.setAlpha(42 if self._hover else 30)
            border = QColor(self.colour)
            border.setAlpha(200)
            ink = QColor(theme.readable_on(self.colour, TOKENS["bg_surface"]))
            dim = QColor(ink)
            dim.setAlpha(85)
        else:
            bg = QColor(TOKENS["hover_warm"] if self._hover
                        else TOKENS["bg_surface"])
            border = QColor(TOKENS["border_default"])
            ink = QColor(TOKENS["text_secondary"])
            dim = QColor(TOKENS["text_hint"])
            dim.setAlpha(110)
        pen = QPen(border, 1.4 if (self._checked and self.isEnabled()) else 1.0)
        if self.dashed:
            pen.setStyle(Qt.DashLine)     # 虛線 = 這裡還沒有東西，按了才長出來
        p.setBrush(QBrush(bg))
        p.setPen(pen)
        p.drawRoundedRect(r, rad, rad)
        p.save()
        p.translate(11, (self.height() - self.GLYPH) / 2.0)
        self.draw_glyph(p, ink, dim)
        p.restore()
        p.setPen(ink)
        p.drawText(QRectF(11 + self.GLYPH + 7, 0, self.width(), self.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, self.label)
        p.end()


class _MetricChip(_ChipBase):
    """統計量那一族的膠囊：小圖是**這個統計量標在分布上的哪一筆**。"""

    #: 「再加一顆」的那種膠囊被按了（``adder_label`` 有值時才會發）。
    add_clicked = Signal(str)

    def __init__(self, mid: str, colour: str, checked: bool = False,
                 parent: Optional[QWidget] = None,
                 adder_label: str = ""):
        if adder_label:
            # 這一顆是**動作**不是統計量：虛線框、永遠不是「選中」。
            group, label, glyph = "", str(adder_label), "plus"
        else:
            group, label, glyph = metric_face(str(mid))
        super().__init__(mid, label, colour, checked, parent)
        self.group, self.glyph = group, glyph
        self.adder = self.dashed = bool(adder_label)
        # tooltip = 這個統計量到底算什麼（引擎那一份公式，不要再寫第二份）。
        self.setToolTip("Add one and pick the number" if self.adder else
                        "%s — %s" % (algo_glv.metric_label(self.mid),
                                     algo_glv.metric_formula(self.mid)))

    def click(self) -> None:               # noqa: D102 - 見基底
        if self.adder:
            self.add_clicked.emit(self.mid)
            return
        super().click()

    def draw_glyph(self, p: QPainter, ink: QColor, dim: QColor) -> None:
        draw_metric_glyph(p, self.glyph, float(self.GLYPH), ink.name(),
                          dim.name())


class _ChoiceChip(_ChipBase):
    """設定區那一族的膠囊：小圖是**這個選項在做什麼**（`GLYPH_ICONS`）。

    值就是 ``mid``（recipe 裡那個字），字是 :func:`_spell` 拼出來的 ——
    所以加一個選項不必再維護第二張「值 → 顯示名」的表。
    """

    def __init__(self, value: str, icon: str, colour: str,
                 checked: bool = False, parent: Optional[QWidget] = None,
                 tip: str = "", label: str = ""):
        super().__init__(value, str(label or "") or _spell(value), colour,
                         checked, parent)
        self.icon = str(icon)
        self.setToolTip(str(tip or ""))

    def draw_glyph(self, p: QPainter, ink: QColor, dim: QColor) -> None:
        draw_glyph_icon(p, self.icon, float(self.GLYPH), ink.name())


class _ChipFlow(QWidget):
    """一群膠囊，寬度不夠就換行（QLayout 排不出「換行」，所以自己排）。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        #: 膠囊**與**「+ Percentile」那種鈕都排在這裡 —— 它們在同一列上，
        #: 分開排的話換行的位置會兩邊各算各的。
        self._items: List[QWidget] = []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def add(self, item: QWidget) -> None:
        item.setParent(self)
        item.show()
        self._items.append(item)
        self._relayout()

    def chips(self) -> List["_ChipBase"]:
        return [c for c in self._items if isinstance(c, _ChipBase)]

    def _relayout(self, width: Optional[int] = None) -> None:
        w = int(width or self.width() or 320)
        x = y = 0
        for c in self._items:
            if x and x + c.width() > w:
                x = 0
                y += _ChipBase.H + 5
            c.move(x, y)
            x += c.width() + 5
        self.setFixedHeight(y + _ChipBase.H if self._items else 0)

    def resizeEvent(self, e) -> None:      # noqa: D102 - Qt hook
        self._relayout(e.size().width())
        super().resizeEvent(e)

    #: ⚠ **要自己講寬度。** 這一族的高度是排完版才知道的，所以 `_relayout`
    #: 只設了 `setFixedHeight` —— 而寬度沒有人講的話 `sizeHint` 是 0，
    #: 於是放進一個沒有 stretch 的 layout（判定面板那一列）時整塊被壓成 0 px
    #: 寬：膠囊都在、也都 `isVisible()`，但畫面上什麼都沒有（2026-09-01
    #: render 出來才看到）。ParamForm 那邊看不出來，因為它是 `addWidget(w, 1)`。
    def sizeHint(self) -> QSize:           # noqa: D102 - Qt hook
        return QSize(max([c.width() for c in self._items] or [0]) or 120,
                     max(self.height(), _ChipBase.H))

    def minimumSizeHint(self) -> QSize:    # noqa: D102 - Qt hook
        return QSize(max([c.width() for c in self._items] or [0]),
                     _ChipBase.H)


class MetricChips(QWidget):
    """``metric_chips`` 參數的編輯器：分群的膠囊 + 「會變成哪幾個 feature」。

    值的格式跟 :class:`MultiChoicePicker` **一字不差**（逗號分隔的 id），所以
    recipe JSON 沒有變 —— 換掉的只有長相。為什麼要換（F18，使用者：「metric
    部分的 UI 我希望更漂亮一點」）：

    * **分群**讓十四顆不再是一面牆；
    * **小圖**給了掃視時的錨點，而且它教了一件事（見 :func:`draw_metric_glyph`）；
    * **底下那一行**把勾選變成 feature 名講出來 —— 那些名字會被打進分數表達式，
      所以它們不能只活在文件裡。

    ``+ Percentile`` 與 ``+ Above`` 是**動作**不是統計量：按下去問一個數字，
    長出一顆 ``glv_q<NN>`` / ``glv_above<NN>``。以前要在自由文字裡自己打
    ``glv_q37``，而打錯只會安靜地少一個 feature。
    """

    changed = Signal(str)

    #: 「再加一顆」的兩個動作：(按鈕字, 問句, 下限, 上限, id 模板)。
    _ADDERS = (
        ("Percentile", "Which percentile? (0-100)", 0, 100, "glv_q%d", 90),
        ("Above", "Count pixels brighter than? (0-255)", 0, 255,
         "glv_above%d", 200),
    )

    def __init__(self, choices: Sequence[str], value: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._choices = [str(c) for c in (choices or [])]
        self._chips: List[_MetricChip] = []
        self._flows: Dict[str, _ChipFlow] = {}
        self._emitting = False

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(9)
        self._grid.setVerticalSpacing(6)
        self._grid.setColumnStretch(1, 1)

        self.count = QLabel("", self)
        self.count.setObjectName("paramHint")
        self.count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._grid.addWidget(self.count, 0, 1)

        self.out = QLabel("", self)
        self.out.setObjectName("paramHint")
        self.out.setWordWrap(True)

        self._build(value)

    # -- public API ---------------------------------------------------------
    def text(self) -> str:
        """目前的值（逗號分隔）。**順序＝畫面上的順序**，不是點選的順序 ——
        同一組勾選每次都要產生同一個字串，不然一份 recipe 會因為使用者點的
        先後而長得不一樣（而它進得了快取簽章）。"""
        return ",".join(c.mid for c in self._chips if c.is_checked())

    def set_text(self, value: str) -> None:
        picked = {t.strip() for t in str(value or "").split(",") if t.strip()}
        unknown = [m for m in picked
                   if m not in [c.mid for c in self._chips]]
        if unknown:                       # recipe 帶進來的手寫 id
            self._build(str(value or ""))
            return
        self._emitting = True
        try:
            for c in self._chips:
                c.set_checked(c.mid in picked)
        finally:
            self._emitting = False
        self._sync_labels()

    def chip(self, mid: str) -> Optional["_MetricChip"]:
        """某一顆膠囊（測試點它、Studio 高亮它用）。"""
        for c in self._chips:
            if c.mid == str(mid):
                return c
        return None

    def picked(self) -> List[str]:
        return [c.mid for c in self._chips if c.is_checked()]

    def choice_names(self) -> List[str]:
        """畫面上列得出來的每一顆（同 :meth:`MultiChoicePicker.choice_names`）。

        **不含**「+ Percentile…」那種膠囊 —— 它們是動作，不是可以勾的統計量。
        """
        return [c.mid for c in self._chips]

    def refresh_colour(self) -> None:
        colour = theme.group_hex("measure")
        for c in self._chips:
            c.set_colour(colour)

    # -- internals ----------------------------------------------------------
    def _build(self, value: str) -> None:
        while self._grid.count() > 1:
            item = self._grid.takeAt(1)
            w = item.widget()
            if w is not None and w is not self.count and w is not self.out:
                w.setParent(None)
                w.deleteLater()
        self._chips = []
        self._flows = {}

        picked = [t.strip() for t in str(value or "").split(",") if t.strip()]
        # 卡片宣告的在前、recipe 帶來的在後（同 MultiChoicePicker 的規矩）。
        ids: List[str] = []
        for mid in list(self._choices) + picked:
            if mid and mid not in ids:
                ids.append(mid)

        colour = theme.group_hex("measure")
        by_group: Dict[str, List[str]] = {}
        for mid in ids:
            by_group.setdefault(metric_face(mid)[0], []).append(mid)
        # 「再加一顆」是 GLV 統計量專屬的（分位數、亮度門檻）。這個 widget 也
        # 服務「跟誰比」那一格，而在那裡長出一顆 `+ Percentile…` 只會是一顆
        # 按了會加出一個那張表不認得的值的鈕。
        adders = any(str(m).startswith("glv_") for m in ids)

        # 群名那一欄有多寬**由最長的那個群名決定**，不是一個寫死的數字。
        # 以前是 46 px，剛好裝得下 Statistics 的五個群（Center…Counts）——
        # 而 Report 分成三群之後，「Difference」與「Distributions」在畫面上
        # 是「ifference」與「ributions」。同一種 QSS 的字級也要進度量
        # （`* { font-size: 13px }` 會蓋掉 `setFont`，那是膠囊那邊踩過的坑）。
        gf = QFont(self.font())
        gf.setPixelSize(10)
        gm = QFontMetricsF(gf)
        shown = [g for g in METRIC_GROUP_ORDER
                 if (by_group.get(g) or (adders and g == "Ends"))]
        label_w = (max([46] + [int(gm.horizontalAdvance(g)) + 4 for g in shown])
                   if len(by_group) > 1 else 46)

        row = 1
        for group in METRIC_GROUP_ORDER:
            members = by_group.get(group) or []
            if not members and not (adders and group == "Ends"):
                continue
            # 只有一群的時候不印群名（「跟誰比」那一格就是這種）—— 那一列的
            # 標籤已經寫了「Report」，旁邊再擺一個「Compare」只是一個沒有在
            # 分辨任何東西的字。
            lbl = QLabel(group if len(by_group) > 1 else "", self)
            lbl.setObjectName("metricGroup")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
            # 字級**兩邊都設**（QFont 與 QSS）：`* { font-size: 13px }` 會蓋掉
            # `setFont`，所以只設 QFont 的話畫出來是 13 px；只設 QSS 的話
            # `lbl.fontMetrics()` 量的是 13 px 而畫出來是 10 px —— 兩種都會讓
            # 「這個字裝得下嗎」的答案跟畫面不一致（膠囊那邊踩過同一個坑）。
            lbl.setFont(gf)
            lbl.setFixedWidth(label_w)
            lbl.setStyleSheet("color:%s; font-size:10px; padding-top:8px;"
                              % TOKENS["text_hint"])
            flow = _ChipFlow(self)
            for mid in members:
                c = _MetricChip(mid, colour, mid in picked, flow)
                c.toggled.connect(self._on_toggled)
                flow.add(c)
                self._chips.append(c)
            # 「再加一顆」的膠囊跟著它產生的東西放：分位數在 Ends、亮度在
            # Counts。做成**同一種膠囊**（虛線框）而不是一顆按鈕 —— 那一列上
            # 混一顆長得不一樣的鈕，讀起來像是它跟旁邊那些不是同一件事。
            for text, question, lo, hi, tmpl, start in self._ADDERS:
                if not adders or metric_face(tmpl % start)[0] != group:
                    continue
                b = _MetricChip("+" + tmpl, colour, False, flow,
                                adder_label=text + "…")
                b.add_clicked.connect(
                    lambda _m="", q=question, a=lo, z=hi, t=tmpl, s=start:
                    self._add_number(q, a, z, t, s))
                flow.add(b)
            self._grid.addWidget(lbl, row, 0)
            self._grid.addWidget(flow, row, 1)
            self._flows[group] = flow
            row += 1

        self._grid.addWidget(self.out, row, 1)
        self._sync_labels()

    def _add_number(self, question: str, lo: int, hi: int, tmpl: str,
                    start: int) -> None:
        n, ok = QInputDialog.getInt(self, "Add a statistic", question,
                                    start, lo, hi, 1)
        if not ok:
            return
        mid = tmpl % int(n)
        existing = self.chip(mid)
        if existing is not None:              # 已經有了 -> 勾起來就好
            existing.set_checked(True)
        else:
            self._build(",".join(self.picked() + [mid]))
        self._emit()

    def _on_toggled(self, _mid: str, _on: bool) -> None:
        if not self._emitting:
            self._emit()

    def _emit(self) -> None:
        self._sync_labels()
        self.changed.emit(self.text())

    def _sync_labels(self) -> None:
        names = self.picked()
        self.count.setText("%d picked" % len(names))
        # **這一行是「會變成哪幾個 feature」**，不是「你勾了什麼」的複述：
        # 接了區域的時候引擎會加上區域名前綴（`epi_glv_median`），而那件事
        # 這裡不知道 —— 所以只講字尾，並且由 help 說明前綴。
        self.out.setText("→  " + (", ".join(names) if names
                                  else "nothing picked yet"))


class MetricPick(MetricChips):
    """``metric_choice`` 參數的編輯器：**單選**版膠囊（F32）。

    跟 :class:`MetricChips` 同一種膠囊、同一個「+ Percentile…」——
    差別只有三件：值是**一個** id、點一顆會把其他的關掉、恆有一顆選著
    （取消最後一顆等於留下一個空值，而空值會在 validate 被換回預設 ——
    看起來像「取消沒有生效」，不如一開始就不准）。

    為什麼不是下拉：GLV 的統計量在這張卡的其他格都是帶小圖的膠囊，
    同一個東西在同一張卡上兩種長相，使用者要學兩次（F18 的理由原封不動）。
    """

    def text(self) -> str:
        picked = [c.mid for c in self._chips if c.is_checked()]
        return picked[0] if picked else ""

    def _on_toggled(self, mid: str, on: bool) -> None:
        if self._emitting:
            return
        if on:
            self._emitting = True
            try:
                for c in self._chips:
                    if c.mid != mid:
                        c.set_checked(False)
            finally:
                self._emitting = False
        elif not any(c.is_checked() for c in self._chips):
            # 恆有一顆選著：把它勾回來、值沒變、不 emit。
            self._emitting = True
            try:
                got = self.chip(mid)
                if got is not None:
                    got.set_checked(True)
            finally:
                self._emitting = False
            return
        self._emit()

    def _add_number(self, question: str, lo: int, hi: int, tmpl: str,
                    start: int) -> None:
        n, ok = QInputDialog.getInt(self, "Add a statistic", question,
                                    start, lo, hi, 1)
        if not ok:
            return
        mid = tmpl % int(n)
        if self.chip(mid) is None:
            self._build(mid)          # 重建：宣告的照列，而只有這一顆選著
        else:
            self._emitting = True
            try:
                for c in self._chips:
                    c.set_checked(c.mid == mid)
            finally:
                self._emitting = False
        self._emit()

    def _sync_labels(self) -> None:
        got = self.text()
        self.count.setText("")        # 單選沒有「N picked」好講
        self.out.setText("→  the odd box is judged by %s"
                         % (got or "nothing yet"))


class ChoiceChips(QWidget):
    """``chip_choice`` 參數的編輯器：**一排膠囊，選一顆**（F68 第二輪）。

    使用者 2026-09-01：「我希望設定欄這邊也是能像下方一樣膠囊 icon 配文字，
    這樣 user 比較會有感覺。」

    為什麼不是下拉選單（跟 :class:`MetricChips` 同一個理由，只是換一格）
    ------------------------------------------------------------------
    下拉選單把選項**藏起來**：使用者要先按開才知道有幾個、分別是什麼，而這
    幾格問的是「這張卡要怎麼找缺陷」—— 那是他每一次調參數都要重看一遍的事。
    攤成一排膠囊之後，選項本身就是畫面，而選中的那一顆帶著階段色。

    為什麼不是「只有圖、名字退到 tooltip」（F11 Region-2 的 ``IconChoice``，
    2026-09-01 拿掉）
    ------------------------------------------------------------------
    那一族的理由是「那個詞講的就是一個畫得出來的形狀」（``beside_vertical``、
    CD 的一條線／一團東西）—— 圖給完了，字是多的。而使用者看了整個設定區之後
    的判斷相反：「**我認為設定區都要變成這樣 icon 膠囊 + 文字，並且視覺模型
    可能要接近會比較好**」。同一個面板上兩種長相，使用者要學兩次；
    **圖是掃視時的錨點，字才是意思**。所以現在只有這一種。

    值的格式跟 ``choice`` **一字不差**（就是那個字），所以 recipe JSON 沒有變。
    """

    changed = Signal(str)

    def __init__(self, choices: Sequence[str], icons: Sequence[str],
                 value: str = "", helps: Optional[Dict[str, str]] = None,
                 parent: Optional[QWidget] = None,
                 labels: Optional[Dict[str, str]] = None):
        super().__init__(parent)
        helps = dict(helps or {})
        labels = dict(labels or {})
        colour = theme.group_hex("measure")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._flow = _ChipFlow(self)
        lay.addWidget(self._flow)

        self._chips: List[_ChoiceChip] = []
        self._value = str(value or "")
        for name, icon in zip([str(c) for c in choices],
                              [str(i) for i in icons]):
            c = _ChoiceChip(name, icon, colour, name == self._value,
                            self._flow, tip=helps.get(name) or "",
                            label=labels.get(name) or "")
            c.toggled.connect(self._on_toggled)
            self._flow.add(c)
            self._chips.append(c)

    # -- ParamForm 那一側看到的介面（跟其他編輯器一樣是 text/set_text）------
    def text(self) -> str:
        return self._value

    def set_text(self, value: str) -> None:
        # 認不得的值（手寫 recipe）**不要偷偷改掉**：一顆都不亮，比亮錯一顆
        # 誠實（這一條是從 `IconChoice` 帶過來的，那個 widget 已經不在了）。
        self._value = str(value or "")
        for c in self._chips:
            c.set_checked(c.mid == self._value)

    def chip(self, value: str) -> Optional[_ChoiceChip]:
        """某一顆膠囊（測試點它用）。"""
        for c in self._chips:
            if c.mid == str(value):
                return c
        return None

    def _on_toggled(self, mid: str, on: bool) -> None:
        """**恆有一顆選著**：再點選中的那一顆不會把它關掉。

        取消最後一顆等於留下一個空值，而空值在 ``validate_params`` 會被換回
        預設 —— 看起來像「我點了但沒有反應」（同 :class:`MetricPick`）。
        """
        if not on:
            got = self.chip(mid)
            if got is not None:
                got.set_checked(True)
            return
        self.set_text(mid)
        self.changed.emit(self._value)


class ChannelMapField(QWidget):
    """``channel_map`` 參數的編輯器：一張「第幾張圖 → 叫什麼」的小表（F11 Input-1）。

    為什麼不是文字框
    ----------------
    值長這樣：``1:se1, 2:bse, 3:se2, 4:se3, 5:se4``。五列以上的時候，一行逗號
    字串**數不清位置** —— 而「哪一張是 BSE」正是這個參數唯一要回答的問題
    （使用者的資料是 1 BSE + 4 SE，BSE 固定在第 2 張）。數錯一格的後果不是
    語法錯誤，是 BSE 的數字被寫在 SE 的名字上：跑得完、有數字、而且是錯的。

    所以排成一列一張圖：**左邊是位置（程式寫的，不能打錯）、右邊是名字**。
    空著的那一列就是「這一張不命名」，而 placeholder 就寫出它不命名時會叫什麼
    （``test`` / ``ref`` / ``img3``…）—— 那是現行行為，使用者看得到自己在改什麼。
    """

    changed = Signal(str)

    #: 沒有命名時 ingest 會給的名字（``ingest/dataset.py::_channel_name``）。
    #: 這裡只是**顯示**用的 placeholder，真正的命名規則仍然只有 ingest 那一份。
    _DEFAULTS = ("test", "ref")

    #: 一列代表什麼 —— **三句話而已，資料形狀完全一樣**（整數 → 名字，空的就是
    #: 不要）。所以是一個旗標而不是第二個 widget：抄第二份出來的那份一定會漂移。
    _WORDS = {
        "images": ("Image %d", "Add another image",
                   "Add a row for one more image. A defect with five images "
                   "(one BSE plus four SE, say) needs five rows."),
        "labels": ("Layer %d", "Add another layer",
                   "Add a row for one more layout layer. The rows normally "
                   "come from the GLAS export — use this only if a layer is "
                   "missing from it."),
    }

    def __init__(self, value: str = "", parent: Optional[QWidget] = None,
                 min_rows: int = 0, row_kind: str = "images"):
        super().__init__(parent)
        self._edits: List[QLineEdit] = []
        self._emitting = False
        self._row_kind = str(row_kind)
        self._words = self._WORDS.get(self._row_kind, self._WORDS["images"])
        #: 這批資料**一顆有幾張圖**（0 = 還不知道）。列數至少排到這個數 ——
        #: 使用者要回答「哪一張是 BSE」的時候，唯一需要的事實就是「有幾張」，
        #: 而那個數字在資料載進來的那一刻就知道了（F11 Input-1 的尾巴）。
        self._min_rows = max(0, int(min_rows))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(2)
        outer.addLayout(self._grid)

        self._add_btn = QPushButton(self._words[1], self)
        self._add_btn.setProperty("variant", "secondary")
        self._add_btn.setToolTip(self._words[2])
        self._add_btn.clicked.connect(lambda: self._add_row(emit=True))
        outer.addWidget(self._add_btn, 0, Qt.AlignLeft)

        self.set_text(value)

    # -- 值 ------------------------------------------------------------------
    def text(self) -> str:
        """目前的值。**空白的列直接跳過** —— 那一張就是「不命名」。"""
        out = []
        for i, edit in enumerate(self._edits):
            name = edit.text().strip()
            if name:
                out.append("%d:%s" % (i + 1, name))
        return ", ".join(out)

    def set_text(self, value: str) -> None:
        pairs = {}
        for chunk in str(value or "").replace(";", ",").split(","):
            item = chunk.strip()
            if ":" in item:
                left, right = item.split(":", 1)
                try:
                    pairs[int(left.strip())] = right.strip()
                except ValueError:          # 壞值由 core 的 parse 負責報錯
                    continue
        floor = 0 if self._row_kind == "labels" else len(self._DEFAULTS)
        rows = max(floor, max(pairs) if pairs else 0, self._min_rows)
        self._emitting = True
        try:
            while len(self._edits) < rows:
                self._add_row(emit=False)
            for i, edit in enumerate(self._edits):
                edit.setText(pairs.get(i + 1, ""))
        finally:
            self._emitting = False

    def row_count(self) -> int:
        return len(self._edits)

    def row_kind(self) -> str:
        """一列代表什麼（``"images"`` / ``"labels"``）。"""
        return self._row_kind

    def set_min_rows(self, n: int) -> None:
        """這批資料一顆有幾張圖 —— 列數至少排到這麼多（不動已經填的名字）。"""
        self._min_rows = max(0, int(n))
        self.set_text(self.text())

    # -- 內部 ----------------------------------------------------------------
    def _default_name(self, index: int) -> str:
        if self._row_kind == "labels":
            # 空著 = **這一層不要**（不是「用預設名」）—— 兩者差很多，
            # 所以 placeholder 要講的是後果，不是一個假的名字。
            return "(no region for this layer)"
        if index < len(self._DEFAULTS):
            return self._DEFAULTS[index]
        return "img%d" % (index + 1)

    def _add_row(self, emit: bool = True) -> None:
        i = len(self._edits)
        label = QLabel(self._words[0] % (i + 1), self)
        label.setObjectName("paramHint")
        edit = QLineEdit(self)
        edit.setPlaceholderText(self._default_name(i))
        edit.textChanged.connect(self._on_edited)
        self._grid.addWidget(label, i, 0)
        self._grid.addWidget(edit, i, 1)
        self._edits.append(edit)
        if emit and not self._emitting:
            self._on_edited("")

    def _on_edited(self, _text: str) -> None:
        if not self._emitting:
            self.changed.emit(self.text())


class TemplateField(QWidget):
    """``template`` 參數的編輯器：一顆「建一個」的按鈕 + 一行摘要（F7-13）。

    為什麼不是文字框
    ----------------
    模板的值有六千多個字元，而且**沒有人能用打的**（它是一張影像的內容）。
    給它一個文字框有三個後果：空的時候看起來像「還沒填的欄位」，而真正的入口
    在半個螢幕外的另一塊面板上；填了之後那個框變成一整片 base64；而且它是
    可編輯的 —— 一個放不下、也編輯不了的值配一個文字框，等於邀請使用者去改它。

    這裡改成：**按鈕就在這一列**（它是這個參數的值從哪來，不是預覽的動作），
    欄位本身只回答「現在有沒有模板、是什麼樣的模板」。
    """

    build_requested = Signal()

    _EMPTY = "No template yet — this card cannot run until you build one."

    def __init__(self, value: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        # ``&&`` 見 `set_text`（Qt 會把單一個 ``&`` 當助憶鍵吃掉）。
        self.button = QPushButton("Edit template && regions…", self)
        self.button.setProperty("variant", "secondary")
        self.button.setToolTip(
            "Measure the repeating cell from one full-size image, then draw "
            "the regions on that cell. Both are stored inside this recipe — "
            "the image is only needed here, so the recipe stays a single "
            "file you can hand to someone else.")
        self.button.clicked.connect(self.build_requested.emit)
        lay.addWidget(self.button, 0, Qt.AlignLeft)

        self.summary = QLabel("", self)
        self.summary.setObjectName("paramHint")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        self._value = ""
        self.set_text(value)

    def text(self) -> str:
        return self._value

    def set_text(self, value: str) -> None:
        self._value = str(value or "")
        self.summary.setText(self.describe())
        # 「還沒有模板」不是說明文字，是**這張卡現在跑不了**。用同一種灰字講，
        # 它就沉進下面那段說明裡了。
        self.summary.setStyleSheet(
            "color:%s; font-size:11px;%s"
            % (TOKENS["text_hint"] if self.has_template() else TOKENS["danger_text"],
               "" if self.has_template() else " font-weight:600;"))
        # ⚠ ``&&`` 不是筆誤：Qt 把單一個 ``&`` 當成助憶鍵的記號吃掉，畫出來
        # 少一個 ``&`` 又多一條底線（``Build template _regions…``）。
        # 同一個坑 2026-08-24 在「Run all & write」上被使用者指出來，
        # `tests/test_ui_button_labels.py` 現在會掃出所有的。
        self.button.setText("Build template && regions…" if not self._value
                            else "Edit template && regions…")

    def has_template(self) -> bool:
        return bool(self._value.strip())

    def describe(self) -> str:
        """一行白話：現在存的是什麼。**摘要是解出來的，不是記在旁邊的**——
        記在旁邊的欄位會跟真正的值走散，而走散時畫面上看起來完全正常。"""
        if not self.has_template():
            return self._EMPTY
        try:
            from ..core.algo.template import decode_cell

            cell = decode_cell(self._value)
        except Exception:                       # noqa: BLE001 — 顯示用
            cell = None
        if cell is None or getattr(cell, "size", 0) == 0:
            return ("A template is stored, but it cannot be read back. "
                    "Build it again.")
        h, w = cell.shape[:2]
        return ("Stored in this recipe: one cell of %d × %d px (%.1f kB of "
                "text). The regions below are drawn on it." 
                % (w, h, len(self._value) / 1024.0))


def glyph_icon(name: str, size: int = 16, color: str = "") -> QIcon:
    """自繪圖示 → 一個 `QIcon`（給 `QComboBox` 的每一項用，2026-09-01）。

    為什麼下拉的項目要圖而不是換成一排膠囊（使用者：「ADC 的設定頁面是不是也
    加入一些 icon 會比較好」）：判定樹那一列是 ``[數字 ▾][運算子 ▾][值]``，
    而那一欄的寬度是使用者拖的（實測預設 437 px）。六顆比較運算子的膠囊擠不
    進去 —— 但**收起來的下拉照樣看得到現在選的那一顆的圖**，這是下拉唯一比
    膠囊強的地方。

    顏色預設吃主題的主要文字色；面板重建時會重畫，所以換主題跟得上。
    """
    px = QPixmap(int(size), int(size))
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    try:
        draw_glyph_icon(p, str(name), float(size),
                        str(color or TOKENS["text_primary"]))
    finally:
        p.end()
    return QIcon(px)


def region_dot_icon(index: int, size: int = 12) -> QIcon:
    """第 ``index`` 個具名區域的**顏色點**（下拉的每一項前面那一顆）。

    同一個顏色在三個畫面上講同一件事：影像上那個框、Feature 表名字的上標、
    判定段下拉的這一點。各自從自己那邊挑顏色的話，同一塊區域在三個地方是三
    個顏色 —— 而顏色指錯區域比沒有顏色糟得多（`_util.CURRENT_REGION_INDEX`
    的註解寫過同一句）。
    """
    px = QPixmap(int(size), int(size))
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(region_hex(int(index))))
    r = size * 0.34
    p.drawEllipse(QPointF(size / 2.0, size / 2.0), r, r)
    p.end()
    return QIcon(px)


def _spell(value: str) -> str:
    """``beside_vertical`` → ``Beside vertical``（沒有指定顯示名時的拼法）。

    ⚠ **只動第一個字母**，不要用 ``str.capitalize()`` —— 它會把**其餘的字全部
    轉小寫**，於是 ``a cell I mark myself`` 在畫面上變成「a cell **i** mark
    myself」。那是使用者自己寫的一句話，被一支拼字函式改掉了。

    拼不對的那幾個（``zscore`` / ``nlm`` / ``topn``…）走 `ParamSpec.choice_labels`
    —— 那張表**只放例外**，不是把整排值再抄一份。
    """
    text = str(value).replace("_", " ").strip()
    return text[:1].upper() + text[1:]


class CellRoisField(QWidget):
    """``cell_rois`` 參數的編輯器：一顆按鈕 + 現在標了什麼（F11 Region-1）。

    為什麼是**唯讀**的摘要而不是文字框
    ----------------------------------
    同 ``image_key`` 那條（F9-6，使用者定調「他會很亂連」）：框的來源只有一個
    —— 畫在 cell 上。給它一個文字框的話同一件事有兩個入口，而兩邊很容易對不
    起來；更糟的是那串字的座標**相對於一格 cell**，離開那張圖就沒有意義，
    所以打得進去的自由文字正是最容易打出「跑得完、有數字、而且是錯的」的地方。

    唯讀不等於藏起來：這一格仍然要看得到現在標了哪些區域、各幾塊。
    """

    edit_requested = Signal()

    _EMPTY = "No regions yet — this card cannot run until you draw one."

    def __init__(self, value: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self.button = QPushButton("Draw regions on the cell…", self)
        self.button.setProperty("variant", "secondary")
        self.button.setToolTip(
            "The boxes are drawn on the repeating cell, not on a patch: they "
            "have to hold for the whole batch, and a patch is a different crop "
            "for every defect.")
        self.button.clicked.connect(self.edit_requested.emit)
        lay.addWidget(self.button, 0, Qt.AlignLeft)

        self.summary = QLabel("", self)
        self.summary.setObjectName("paramHint")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        self._value = ""
        self.set_text(value)

    def text(self) -> str:
        return self._value

    def set_text(self, value: str) -> None:
        self._value = str(value or "")
        self.summary.setText(self.describe())
        self.summary.setStyleSheet(
            "color:%s; font-size:11px;%s"
            % (TOKENS["text_hint"] if self.has_regions() else TOKENS["danger_text"],
               "" if self.has_regions() else " font-weight:600;"))

    def has_regions(self) -> bool:
        return bool(self._value.strip())

    def describe(self) -> str:
        """**摘要是解出來的，不是記在旁邊的** —— 記在旁邊的會跟真正的值走散。"""
        if not self.has_regions():
            return self._EMPTY
        from ..core.pipeline.cellrois import CellRoiError, parse_cell_rois

        try:
            regions = parse_cell_rois(self._value)
        except CellRoiError as e:
            return "These regions cannot be read back: %s" % e
        return "  ·  ".join(
            "%s (%d rectangle%s)" % (n, len(b), "" if len(b) == 1 else "s")
            for n, b in regions)


#: 「數字 → 誰算的」那份清單的分隔（跟 `viewmodel.ViewModel.FEATURE_LABEL_SEP`
#: 是同一個字）。**拆開的規矩只有這一份** —— 抄第二份出來的那份會漂。
FEATURE_LABEL_SEP = "\t"


def split_labelled(item: Any) -> "tuple":
    """``"cd_median\tCD"`` → ``("cd_median", "CD")``；沒有標籤就回空字串。

    前半是**要插進算式的字**，後半只是給人看的 —— 插錯半邊的話，使用者會得到
    一個永遠指不到的變數名，而錯誤要等跑起來才出現。
    """
    text = str(item or "")
    name, _sep, label = text.partition(FEATURE_LABEL_SEP)
    return name.strip(), label.strip()


class ParamForm(QWidget):
    """由 ``Step.describe()`` 的 ParamSpec dict 自動長出來的參數表單。

    ``set_step(describe, current_params, stream_choices)`` 一次重建整張表；
    使用者改動任何欄位 -> ``param_edited(name, value)``（值已 coerce 成該型別）。
    上層驗證失敗時呼叫 ``show_error(name, msg)`` 把那一列的說明變紅字。
    """

    param_edited = Signal(str, object)
    #: 「這個參數的值要用別的方式產生」（目前只有 template）。表單不知道那是
    #: 什麼對話框 —— 它只負責把請求送上去，由 Studio 決定要開什麼。
    action_requested = Signal(str)
    #: 使用者在一格接線插槽上挑了一個上游的區域／影像流：``(參數名, 名字)``。
    #: **這裡不改任何東西** —— `StudioWindow` 接到之後走跟畫布拉線同一條路
    #: （F68；線仍然是唯一的儲存）。
    wire_requested = Signal(str, str)
    #: 「在畫布上指給我看」：``(參數名,)``。
    wire_show_requested = Signal(str)
    #: **入口卡的「資料從哪來」**（F14-1）：按下去要開檔案對話框。
    #: 同樣地，表單不知道那是哪一種來源 —— 它送出去，Studio 決定開什麼。
    source_requested = Signal()
    #: 「我要量什麼」三選（PR-2 2a）：使用者按了哪個 preset 的 id。
    #: 表單不知道 preset 會動什麼 —— 動線動格的腦袋在 model。
    intent_chosen = Signal(str)

    _EMPTY_TEXT = "(Pick a card from the library, or select a step in the pipeline)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._rows: Dict[str, _ParamRow] = {}
        #: 目前這批資料**一顆有幾張圖**（0 = 沒有資料）。只有 `channel_map` 的
        #: 編輯器用得到它 —— 但它是「資料的事實」而不是「這張卡的參數」，
        #: 所以放在表單上（一份資料一次）而不是塞進 `set_step` 的簽章。
        self._image_count = 0
        #: 目前掛上的 GLAS 匯出**有幾層**（0 = 沒掛）。`channel_map` 的
        #: `row_kind="labels"` 靠它排列數 —— 使用者打開那一格時，第一個要知道
        #: 的是「這份匯出有哪幾層」，而那在掛上去的那一刻就知道了。
        self._label_count = 0
        #: 這張卡吃進來的那條流的灰階分布（墊在曲線後面，見 `set_histogram`）。
        self._hist: List[float] = []
        #: 小標題：``section 名 -> [QLabel]`` 與 ``參數名 -> section 名``。
        #: 整組都被 ``show_when`` 藏起來時，標題也要跟著不見 —— 一個底下什麼
        #: 都沒有的標題比沒有標題更讓人以為畫面壞了。
        self._sections: Dict[str, List[QWidget]] = {}
        self._section_of: Dict[str, str] = {}
        #: 標了 ``advanced`` 的那幾列（預設收起來）。
        self._advanced: set = set()
        #: 目前這張卡每個參數的值 —— ``show_when`` 要靠它判斷哪幾列該在。
        self._values: Dict[str, Any] = {}
        #: 執行期才知道的選單（F15-2）：``{RUNTIME_CHOICES 的鍵: [選項]}``。
        self._dynamic: Dict[str, List[str]] = {}
        #: 上游定義了哪些具名區域（F11 Region-1）。
        self._regions: List[str] = []
        #: 插槽選單的內容（F68）：``{"region": [...], "image": [...]}``。
        self._wiring: Dict[str, List[str]] = {}
        self._describe: Optional[Dict[str, Any]] = None
        self._building = False
        #: 進階參數收起來了嗎（**追明確狀態**，不問 widget —— docs/PITFALLS.md）。
        #: 換一張卡就收回去：上一張卡展開過不代表這一張也要。
        self._advanced_open = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)          # 8px 節奏（F8-UI）

        self._title = QLabel("")
        self._title.setObjectName("paramTitle")
        # 卡片自己的一句話。收成一行（放不下就 ``像這樣…``）、全文住 tooltip
        # —— 跟參數列同一個決定（2026-08-14）：說明是查閱用的，不佔版面。
        self._step_help = _HintLabel("")
        self._step_help.setObjectName("paramStepHelp")
        outer.addWidget(self._title)
        outer.addWidget(self._step_help)

        # 「這張卡的資料從哪來」（F14-1，使用者定調：工具列那幾顆 Open
        # 「會混淆」）。入口長在**讀那份資料的那張卡上** —— 以前它在工具列，
        # 而畫布上那張 Load 卡完全不會說它讀的是哪個檔案：同一件事兩個地方，
        # 而畫布是說謊的那一個。
        self._source_row = QWidget(self)
        self._source_row.setObjectName("sourceRow")
        srow = QHBoxLayout(self._source_row)
        srow.setContentsMargins(2, 0, 8, 0)
        srow.setSpacing(8)
        self._source_btn = QPushButton("", self._source_row)
        self._source_btn.setObjectName("primary")
        self._source_btn.setCursor(Qt.PointingHandCursor)
        self._source_btn.clicked.connect(self.source_requested.emit)
        self._source_note = QLabel("", self._source_row)
        self._source_note.setObjectName("paramHint")
        self._source_note.setWordWrap(True)
        srow.addWidget(self._source_btn)
        srow.addWidget(self._source_note, 1)
        self._source_shown = False
        self._source_row.setVisible(False)
        outer.addWidget(self._source_row)

        # 「我要量什麼」三選（PR-2 2a；目前只有 GLV 用）。跟 `_source_row`
        # 同一個位置學（scroll 區上方 —— 意圖在參數之前）。**preset 不是
        # 參數**：這裡只畫鈕、發 id，動線動格的腦袋在 `RecipeModel
        # .apply_glv_intent`。表單保持不認識 model。
        self._intent_row = QWidget(self)
        self._intent_row.setObjectName("intentRow")
        irow = QVBoxLayout(self._intent_row)
        # 上緣留白：卡片那句說明的下緣與這一排的標題（14px/700）之間原本只有
        # 版面的 8px，兩行字擠在一起（F68 截圖上看得到）。
        irow.setContentsMargins(2, 6, 8, 4)
        irow.setSpacing(2)
        self._intent_title = QLabel("", self._intent_row)
        self._intent_title.setObjectName("paramTitle")
        irow.addWidget(self._intent_title)
        btns = QHBoxLayout()
        btns.setSpacing(6)
        # 最後那一格彈簧**建一次就好**：膠囊靠左排（跟設定區每一排一樣），
        # 沒有它的話 QHBoxLayout 會把多出來的寬度攤在膠囊之間 —— 三顆固定寬度
        # 的東西被推得老遠，看起來不像同一排。
        btns.addStretch(1)
        self._intent_btns: Dict[str, "_ChoiceChip"] = {}
        self._intent_btn_row = btns
        irow.addLayout(btns)
        self._intent_note = QLabel("", self._intent_row)
        self._intent_note.setObjectName("paramHint")
        self._intent_note.setWordWrap(True)
        irow.addWidget(self._intent_note)
        self._intent_shown = False           # 追明確狀態（PITFALLS：isVisible
        self._intent_row.setVisible(False)   # 在視窗 show 之前恆為 False）
        outer.addWidget(self._intent_row)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._form = QVBoxLayout(self._host)
        self._form.setContentsMargins(2, 2, 8, 2)
        self._form.setSpacing(2)
        self._placeholder = QLabel(self._EMPTY_TEXT)
        self._placeholder.setObjectName("placeholder")
        self._placeholder.setWordWrap(True)
        self._form.addWidget(self._placeholder)
        # 「還有幾格」的入口。放在**進階那幾列的上面**（插在它們之前），
        # 這樣按下去展開的東西就在按鈕底下 —— 不必回頭找。
        self._advanced_btn = QPushButton("", self._host)
        self._advanced_btn.setObjectName("advancedToggle")
        self._advanced_btn.setCursor(Qt.PointingHandCursor)
        self._advanced_btn.setVisible(False)
        self._advanced_btn.clicked.connect(self.toggle_advanced)
        self._form.addWidget(self._advanced_btn)
        self._form.addStretch(1)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

        self.set_step(None, {}, [])

    # -- public API --------------------------------------------------------
    def set_source_action(self, label: str = "", note: str = "",
                          tooltip: str = "") -> None:
        """入口卡上那一排「資料從哪來」。``label=""`` = 這張卡沒有這一排。

        note 講的是**現在載的是什麼**（`LOT_SYN.001 · 12 defects`）——
        鈕本身只說得出「可以換一份」，而使用者第一個要確認的是「我現在看的
        是哪一份」。
        """
        label = str(label or "")
        self._source_btn.setText(label)
        self._source_btn.setToolTip(str(tooltip or ""))
        self._source_note.setText(str(note or ""))
        # **追明確狀態**：`isVisible()` 在視窗 show 之前恆為 False，
        # 那個坑這個 repo 踩過（見 docs/PITFALLS.md）。
        self._source_shown = bool(label)
        self._source_row.setVisible(self._source_shown)

    def has_source_action(self) -> bool:
        """這張卡有沒有那一排「資料從哪來」。"""
        return bool(getattr(self, "_source_shown", False))

    def set_intent_row(self, title: str = "",
                       options: Sequence[Tuple[str, str, str]] = (),
                       current_id: str = "", note: str = "",
                       enabled: bool = True) -> None:
        """卡最上面的「我要量什麼」三選（PR-2 2a）。``title=""`` = 沒有這排。

        ``options`` 是 ``(id, 顯示字, 一句話, 圖示名)``；``current_id`` 對不上
        任何 id（例 ``"custom"``）就一顆都不勾 —— **不強制改**，自訂是一個合法
        的狀態。``enabled=False``（roi 還沒接線）時整排灰掉，note 講原因。

        **長相跟設定區的膠囊一模一樣**（F68 第三輪，使用者：「最上方的
        What do I want to measure 也是」）。它問的是同一種問題（幾個答案挑
        一個），長成另一種東西只會讓人以為那是別的機制 —— 而它其實正是底下
        那幾格的捷徑：三顆膠囊的圖就是它們會設成的那幾格的圖。
        """
        title = str(title or "")
        # 重建（選項是呼叫端給的，張數可能變）。
        #
        # ⚠ **`deleteLater()` 不夠，要先 `setParent(None)`。** 延遲刪除要等
        # 事件圈的 DeferredDelete 那一趟，而在那之前那幾顆**還在畫面上**，
        # 停在上一次版面給它們的位置 —— 這一排是有 stretch 的，面板一換寬度
        # 位置就變，於是舊的那幾顆變成疊在標題與新膠囊上的鬼影
        # （F68 第三輪 render 出來才看到；以前是 QPushButton 時同一個 bug，
        # 只是每次寬度都一樣所以完美重疊，看不出來）。
        for btn in self._intent_btns.values():
            self._intent_btn_row.removeWidget(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._intent_btns = {}
        self._intent_title.setText(title)
        colour = theme.group_hex("measure")
        if title:
            for iid, label, help_line, icon in options:
                chip = _ChoiceChip(str(iid), str(icon), colour,
                                   str(iid) == str(current_id),
                                   self._intent_row, tip=str(help_line),
                                   label=str(label))
                chip.momentary = True          # 見 `_ChipBase.momentary`
                chip.setEnabled(bool(enabled))
                # **不是 toggle**：這一排是 preset，按下去等於「照這個意思
                # 把線接好」，而**再按一次不該把它取消**（取消要回到哪個狀態？
                # 沒有答案）。所以只接「按了」，勾不勾由 `current_id` 決定。
                chip.toggled.connect(
                    lambda _v, _on, i=str(iid): self.intent_chosen.emit(i))
                self._intent_btn_row.insertWidget(len(self._intent_btns),
                                                  chip)   # 彈簧留在最後
                self._intent_btns[str(iid)] = chip
        self._intent_note.setText(str(note or ""))
        self._intent_note.setVisible(bool(note))
        self._intent_shown = bool(title)
        self._intent_row.setVisible(self._intent_shown)

    def has_intent_row(self) -> bool:
        return bool(getattr(self, "_intent_shown", False))

    def intent_buttons(self) -> Dict[str, "_ChoiceChip"]:
        """測試 API：id → 那一顆膠囊。"""
        return dict(self._intent_btns)

    def source_button(self) -> QPushButton:
        """那顆鈕本身（訊息裡引到的名字要跟它一字不差 —— 有測試在擋）。"""
        return self._source_btn

    def set_image_count(self, n: int) -> None:
        """告訴表單「這批資料一顆有幾張圖」（F11）。

        `channel_map` 的表格會照它排列數 —— 使用者打開那一格時，第一個要知道的
        事實就是「有幾張」，而那個數字在資料載進來的那一刻就知道了。
        """
        n = max(0, int(n))
        if n == self._image_count:
            return
        self._image_count = n
        for row in self._rows.values():
            if isinstance(row.editor, ChannelMapField) \
                    and row.editor.row_kind() == "images":
                row.editor.set_min_rows(n)

    def set_label_count(self, n: int) -> None:
        """告訴表單「掛上的 GLAS 匯出有幾層」（F11 Region-3）。

        跟 :meth:`set_image_count` 同一個形狀，而且**兩者不可以互相蓋掉** ——
        一張 recipe 上可能同時有 `load_patch`（一列一張圖）與 `roi_reference`
        （一列一層）兩個 `channel_map`，用同一個數字去排兩者的列數，其中一邊
        一定是錯的。
        """
        n = max(0, int(n))
        if n == self._label_count:
            return
        self._label_count = n
        for row in self._rows.values():
            if isinstance(row.editor, ChannelMapField) \
                    and row.editor.row_kind() == "labels":
                row.editor.set_min_rows(n)

    def set_histogram(self, counts: Optional[Sequence[float]]) -> None:
        """這張卡吃進來的那條流長什麼樣（F11 Enhance-UI-C）。

        只有曲線欄位用得到它。跟 :meth:`set_image_count` 同一個形狀：這是
        **資料的事實**而不是這張卡的參數，所以放在表單上，不塞進 `set_step`
        的簽章（那會讓每一個呼叫端都得知道有這回事）。

        重建表單時會被清掉，所以上層在 `set_step` 之後要再餵一次 —— 那是
        Studio 的 `_refresh_curve_backdrop`。
        """
        self._hist = list(counts or [])
        for row in self._rows.values():
            if isinstance(row.editor, CurveField):
                row.editor.set_histogram(self._hist)

    def histogram(self) -> List[float]:
        return list(self._hist)

    def set_step(self, describe: Optional[Dict[str, Any]],
                 current_params: Optional[Dict[str, Any]] = None,
                 stream_choices: Optional[Sequence[str]] = None,
                 region_choices: Optional[Sequence[str]] = None,
                 dynamic_choices: Optional[Dict[str, Sequence[str]]] = None
                 ) -> None:
        """重建表單。``describe=None`` -> 顯示提示語（未選節點）。

        ``region_choices`` 是**上游定義了哪些具名區域**（F11 Region-1）。
        跟 ``stream_choices`` 同一個理由：那些名字程式知道，就不該讓使用者用打的。

        ``dynamic_choices`` 是**執行期才知道的選單**（F15-2），
        ``{RUNTIME_CHOICES 的鍵: [選項]}`` —— 現在掛了哪幾份第二 source、
        那一份的一顆有哪幾張圖、那一份的 KLARF 有哪些欄。同一個理由的第三次：
        程式知道的名字不該讓使用者用打的。Studio 是唯一知道答案的人，所以答案
        從這裡傳進來，而不是讓元件自己去問（`widgets` 不認得 `Dataset`）。
        """
        current_params = dict(current_params or {})
        # 換卡先把「我要量什麼」那排清掉（同 `set_source_action` 的規矩：
        # 這排是**這張卡**的，別張卡不出現）—— 要顯示的話 Studio 在
        # `set_step` 之後自己 set 回來。
        self.set_intent_row("")
        # **沒填的那幾格用預設值補上**（F30）。`show_when` 問的是「另外那一格
        # 現在是什麼」，而引擎那一邊看到的永遠是 `validate_params` 補完的一份
        # —— 這裡不補的話，一張剛加進來、參數還是空的卡，它的 `method` 在
        # 面板眼裡是空字串，於是**每一格都被判定為不該顯示**，整張卡看起來
        # 是空的。實測就是這樣發現的（四張 Region 卡收成一張之後）。
        for spec in (describe or {}).get("params") or []:
            current_params.setdefault(str(spec.get("name")), spec.get("default"))
        streams = [str(s) for s in (stream_choices or [])]
        self._regions = [str(r) for r in (region_choices or [])]
        self._dynamic = {str(k): [str(v) for v in (vals or [])]
                         for k, vals in dict(dynamic_choices or {}).items()}
        self._describe = describe
        self._building = True
        try:
            self._clear_rows()
            if not describe:
                self._title.setText("")
                self._title.setVisible(False)
                self._step_help.set_full_text("")
                self._step_help.setVisible(False)
                self._placeholder.setVisible(True)
                return
            self._title.setText(str(describe.get("label")
                                    or describe.get("key") or ""))
            self._title.setVisible(True)
            step_help = str(describe.get("help", ""))
            self._step_help.set_full_text(step_help)
            self._step_help.setToolTip(step_help)
            self._step_help.setVisible(bool(step_help))
            self._placeholder.setVisible(False)
            self._values = {}
            self._advanced = set()
            self._advanced_open = False
            section = None
            for spec in describe.get("params", []):
                name = str(spec.get("name", ""))
                # 小標題：換組的時候插一行（F8 第三輪）。參數清單的**順序**就是
                # 分組，所以卡片作者不必額外宣告什麼 —— 把同一組的排在一起就好。
                want = str(spec.get("section", "") or "")
                if want != section:
                    section = want
                    if want:
                        head = QLabel(want, self._host)
                        head.setObjectName("paramSection")
                        self._form.insertWidget(self._form.count() - 1, head)
                        self._sections.setdefault(want, []).append(head)
                value = current_params.get(name, spec.get("default"))
                self._values[name] = value
                editor = self._make_editor(spec, value, streams)
                editor.setToolTip(str(spec.get("help", "")))
                row = _ParamRow(spec, editor, self._host)
                self._form.insertWidget(self._form.count() - 1, row)
                self._rows[name] = row
                if want:
                    self._section_of[name] = want
                if bool(spec.get("advanced")):
                    self._advanced.add(name)
        finally:
            self._building = False
        self._sync_visible_rows()
        self._sync_curve_override()
        # 參數列是**選到哪張卡才長出來的**，所以視窗建好時掃的那一次抓不到
        # 它們（模板鈕、曲線的兩顆…）。每次重建之後再掃一次。
        apply_button_cursors(self)

    def _sync_curve_override(self) -> None:
        """曲線一旦不是 y=x，就把 ``gamma`` 那列調淡並說明原因。

        規則本身寫在 ``steps/tone.py``（曲線接管 gamma）。這裡只是**讓它看得
        見** —— 不然使用者會拉了曲線又去動 gamma，然後發現 gamma 沒有反應。
        """
        curve_row = None
        for name, row in self._rows.items():
            if str(row.spec.get("type", "")) == "curve":
                curve_row = row
                break
        if curve_row is None:
            return
        active = not curve_row.editor.is_identity()
        gamma = self._rows.get("gamma")
        if gamma is not None and not gamma.has_error():
            gamma.set_dimmed(active, "Not used while a custom curve is drawn.")

    def step_key(self) -> Optional[str]:
        return None if not self._describe else str(self._describe.get("key"))

    def advanced_open(self) -> bool:
        """進階那幾列現在攤開了嗎（**明確狀態**，不問 widget）。"""
        return bool(self._advanced_open)

    def advanced_names(self) -> List[str]:
        """這張卡有哪幾列是進階的。"""
        return [n for n in self._rows if n in self._advanced]

    def toggle_advanced(self) -> None:
        self.set_advanced_open(not self._advanced_open)

    def set_advanced_open(self, open_: bool) -> None:
        self._advanced_open = bool(open_)
        self._sync_visible_rows()

    def section_names(self) -> List[str]:
        """這張卡分了哪幾組小標題（依出現順序）。"""
        return list(self._sections)

    def section_visible(self, name: str) -> bool:
        """某一組的標題現在看不看得到（**追明確狀態**，不問 ``isVisible()`` ——
        視窗還沒 show 之前那個恆為 False，見 docs/PITFALLS.md）。"""
        heads = self._sections.get(str(name)) or []
        return bool(heads) and all(not h.isHidden() for h in heads)

    def param_names(self) -> List[str]:
        return list(self._rows)

    def row_visible(self, name: str) -> bool:
        """那一列現在看不看得到（**明確狀態**，不問 ``isVisible()``）。"""
        row = self._rows.get(str(name))
        return bool(row is not None and not row.isHidden())

    def values(self) -> Dict[str, Any]:
        """目前表單上每一格的值（收起來的那幾格照樣在 —— 這是顯示規則）。"""
        return dict(self._values)

    def advanced_button_text(self) -> str:
        return str(self._advanced_btn.text())

    def advanced_button_visible(self) -> bool:
        return bool(self._advanced_names_now())

    def _advanced_names_now(self) -> List[str]:
        """按下去會出現的那幾格 —— 被 ``show_when`` 排除的不算。"""
        return [n for n in self._rows
                if n in self._advanced and self._shown_by_rules(n)]

    def editor(self, name: str) -> Optional[QWidget]:
        row = self._rows.get(name)
        return None if row is None else row.editor

    def slider(self, name: str) -> Optional[QSlider]:
        """那一列的滑桿（沒有上下界的參數沒有滑桿，回 ``None``）。"""
        row = self._rows.get(name)
        return None if row is None else row.slider

    def hint_text(self, name: str) -> str:
        """那一列的說明**全文**。

        不是 ``hint.text()`` —— 收起來的時候那是切過的字（``像這樣…``），
        而問「說明寫了什麼」的人要的從來不是「畫面上現在放得下多少」。"""
        row = self._rows.get(name)
        return "" if row is None else row.hint.full_text()

    def show_error(self, name: str, msg: str) -> None:
        """把 ``name`` 那一列的說明換成紅色錯誤訊息。"""
        row = self._rows.get(name)
        if row is not None:
            row.set_error(msg)

    def clear_errors(self) -> None:
        """所有列還原成白話說明（灰字）。"""
        for row in self._rows.values():
            if row.has_error():
                row.set_error(None)

    def has_error(self, name: str) -> bool:
        row = self._rows.get(name)
        return bool(row is not None and row.has_error())

    # -- internals ---------------------------------------------------------
    def _clear_rows(self) -> None:
        for row in self._rows.values():
            self._form.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = {}
        for heads in self._sections.values():
            for head in heads:
                self._form.removeWidget(head)
                head.setParent(None)
                head.deleteLater()
        self._sections, self._section_of = {}, {}
        self._advanced = set()

    def _emit(self, name: str, value: Any) -> None:
        if self._building:
            return
        self._values[name] = value
        # 改了控制別人的那一格（例如 Normalize 的 method）→ 立刻重算哪幾列該在。
        self._sync_visible_rows()
        self.param_edited.emit(name, value)

    def _sync_visible_rows(self) -> None:
        """依 ``show_when`` 顯示／隱藏各列（F7-20）。

        為什麼是隱藏而不是變淡：``_sync_curve_override`` 的「變淡」講的是
        「這一格還在，只是現在沒有作用」—— 使用者可能想把曲線拉直再用 gamma。
        ``show_when`` 講的是**完全不同的另一件事**：選了 CLAHE 的時候
        ``p_low`` 根本不是這張卡的一部分，留在畫面上只會讓人問「那它算不算數」。
        """
        for name, row in self._rows.items():
            # **規則住在 core**（`step.param_visible`）—— 這裡以前自己又寫了
            # 一次同樣的判斷，而兩份會漂：漂掉的症狀是「設定區看得到某一格，
            # 但引擎當它不存在」，使用者填了一個沒有作用的值而畫面上不會說。
            from ..core.pipeline.step import param_visible
            shown = param_visible(row.spec.get("show_when"), self._values)
            # 兩個規則是 **and**：進階的那一列被 show_when 排除掉的時候，
            # 展開進階也不該把它變出來（那一列在這個方法下根本不算數）。
            if name in self._advanced and not self._advanced_open:
                shown = False
            row.setVisible(shown)

        n = len(self._advanced_names_now())
        self._advanced_btn.setVisible(n > 0)
        # 講**幾格**，不要只講「進階」：使用者要判斷的是「我漏看了什麼」，
        # 而一個沒有數字的標籤答不出那個問題。
        self._advanced_btn.setText(
            "Hide %d more settings" % n if self._advanced_open
            else "Show %d more settings" % n)

        # 整組都藏起來時標題也要不見 —— 一個底下什麼都沒有的標題，
        # 比沒有標題更讓人以為畫面壞了。
        alive = {}
        for name, row in self._rows.items():
            sec = self._section_of.get(name)
            if sec:
                alive[sec] = alive.get(sec, False) or row.isVisibleTo(self)
        for sec, heads in self._sections.items():
            for head in heads:
                head.setVisible(alive.get(sec, True))

    def set_dynamic_choices(self,
                            dynamic: Optional[Dict[str, Sequence[str]]]) -> None:
        """換一批執行期選單（F15-2），**不重建表單**。

        重建會把游標搶走 —— 而這件事最常發生的時機正是「使用者剛在
        “Source name” 那一格打字」。所以這裡只換那幾格的**內容**，而且
        **跳過現在有游標的那一格**（它的內容就是使用者正在打的字）。
        """
        self._dynamic = {str(k): [str(v) for v in (vals or [])]
                         for k, vals in dict(dynamic or {}).items()}
        for name, row in self._rows.items():
            choices = self._runtime_choices(row.spec)
            if choices is None:
                continue
            w = row.editor
            if w is None or w.hasFocus():
                continue
            if isinstance(w, MultiChoicePicker):
                w.set_choices(choices)
            elif isinstance(w, QComboBox):
                line = w.lineEdit()
                if line is not None and line.hasFocus():
                    continue
                text = w.currentText()
                w.blockSignals(True)
                try:
                    w.clear()
                    w.addItems(choices)
                    w.setCurrentText(text)
                finally:
                    w.blockSignals(False)

    def _shown_by_rules(self, name: str) -> bool:
        """撇開「進階收起來了」這件事，這一列本身算不算數（``show_when``）。"""
        from ..core.pipeline.step import param_visible
        row = self._rows.get(name)
        if row is None:
            return False
        # **同一支規則**（`step.param_visible`）—— 這裡是第二個自己寫一份的
        # 地方，而兩份會漂：漂掉的症狀是同一列在兩個問句下有兩個答案。
        return param_visible(row.spec.get("show_when"), self._values)

    #: `choices_from` 的鍵 → 空清單時那一格要說的話。**空清單是正常狀態**
    #: （還沒掛第二份），而它畫出來是一塊空白 —— 留白讀起來像壞掉。
    _EMPTY_HINTS = {
        "sources": "No second lot open yet — use the button above.",
        "source_images": "Open the second lot to see its images.",
        "source_columns": "Open the second lot to see its KLARF columns.",
    }

    def _wiring_slot(self, name: str, spec: Dict[str, Any],
                     value: Any) -> QWidget:
        """一格接線（F68）—— 見 `d4t/ui/wiring_slot.py`。

        「非接不可」看的是 `ParamSpec.required_input` 的同一個判準（預設值指得
        出一條流的就是主要輸入）—— 這裡拿 describe 過的 dict，所以自己算一次
        同一句話：**有預設值的影像輸入**才是紅字的那一種。
        """
        from .wiring_slot import IMAGE, REGION, WiringSlot

        ptype = str(spec.get("type", ""))
        kind = REGION if ptype in ("region_key", "region_keys") else IMAGE
        required = (kind == IMAGE
                    and bool(str(spec.get("default", "") or "").strip()))
        w = WiringSlot(kind, "" if value is None else str(value),
                       is_reference=str(spec.get("role", "")) == "reference",
                       required=required)
        w.set_choices(self._wiring_choices(kind))
        w.wire_requested.connect(
            lambda picked, n=name: self.wire_requested.emit(n, picked))
        w.show_requested.connect(
            lambda n=name: self.wire_show_requested.emit(n))
        return w

    def _wiring_choices(self, kind: str) -> List[str]:
        """插槽選單裡有哪些（Studio 用 :meth:`set_wiring_choices` 餵）。"""
        return list(self._wiring.get(str(kind), ()))

    def set_wiring_choices(self, regions: Sequence[str] = (),
                           streams: Sequence[str] = ()) -> None:
        """告訴表單「**到這張卡為止**上游產得出哪些區域／影像流」（F68）。

        跟 `set_dynamic_choices` 一樣，這是**執行期才知道**的東西，所以由
        Studio 餵；差別是它不必等使用者打字，換一張卡就算一次。
        """
        from .wiring_slot import IMAGE, REGION

        self._wiring = {REGION: [str(r) for r in regions],
                        IMAGE: [str(x) for x in streams]}
        for row in self._rows.values():
            w = row.editor
            if hasattr(w, "set_choices") and hasattr(w, "wire_requested"):
                ptype = str(row.spec.get("type", ""))
                w.set_choices(self._wiring[
                    REGION if ptype in ("region_key", "region_keys") else IMAGE])

    def _runtime_choices(self, spec: Dict[str, Any]) -> Optional[List[str]]:
        """這一格的選項是**執行期來的**嗎（F15-2）。不是就回 None。

        認得旗標但拿不到清單（Studio 還沒實作那一個鍵）→ 回**空 list**，
        不是 None：那一格仍然是選單，只是現在是空的 —— 而空的會講出為什麼。
        """
        key = str(spec.get("choices_from", "") or "")
        if not key:
            return None
        return list(self._dynamic.get(key, ()))

    def _make_expr_editor(self, name: str, value: Any,
                          kind: str = "expr") -> QWidget:
        """算式那一格：一個文字框 ＋ 一支「插入數字 ▾」（F21-B）。

        清單來自 ``dynamic_choices["features"]``，項目是
        ``"名字\t誰算的"``（見 `split_labelled`）。拿不到清單的時候它仍然是
        一個**完全可用的文字框** —— 那正是 Studio 以外的地方（測試、將來的
        別的宿主）會遇到的情況，而少一支下拉不該讓那一格不能填。
        """
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        edit = QLineEdit()
        edit.setText("" if value is None else str(value))
        edit.setPlaceholderText("e.g. glv_max - glv_median" if kind == "expr"
                                else "e.g. cd_median, cd_min")
        edit.textEdited.connect(lambda t, n=name: self._emit(n, str(t)))
        lay.addWidget(edit)

        items = list(self._dynamic.get("features", ()))
        combo = QComboBox()
        combo.addItem("Insert a number…" if items
                      else "No numbers upstream yet")
        combo.setEnabled(bool(items))
        for it in items:
            fname, owner = split_labelled(it)
            if not fname:
                continue
            combo.addItem("%s   —   %s" % (fname, owner) if owner else fname,
                          fname)
        combo.setToolTip("Pick one of the numbers the cards above work out - "
                         "it is put in at the cursor.")
        combo.activated.connect(
            lambda i, c=combo, e=edit, n=name, k=kind:
            self._insert_feature(i, c, e, n, k))
        lay.addWidget(combo)
        return box

    def _insert_feature(self, index: int, combo: QComboBox,
                        edit: QLineEdit, name: str,
                        kind: str = "expr") -> None:
        """把選到的數字送進那一格，然後把下拉撥回標題那一列。

        ``expr`` 插在**游標的位置**（式子中間常常要補一個名字）；
        ``feature_keys`` **接在後面**並補一個逗號（那一格是一串名字，插在中間
        會把別人的名字剖成兩半）。同一支下拉、兩種送進去的方式 —— 差別由那一格
        的型別決定，不由使用者記得。
        """
        if int(index) <= 0:
            return
        token = str(combo.itemData(int(index)) or "")
        combo.setCurrentIndex(0)
        if not token:
            return
        text = edit.text()
        if kind == "feature_keys":
            have = [x.strip() for x in text.split(",") if x.strip()]
            if token in have:            # 已經在裡面就不重複加
                return
            new_text = ", ".join(have + [token])
            pos = len(new_text)
        else:
            pos = max(0, min(edit.cursorPosition(), len(text)))
            new_text = text[:pos] + token + text[pos:]
            pos = pos + len(token)
        edit.setText(new_text)
        edit.setCursorPosition(pos)
        self._emit(name, new_text)

    def _make_editor(self, spec: Dict[str, Any], value: Any,
                     streams: Sequence[str]) -> QWidget:
        name = str(spec.get("name", ""))
        ptype = str(spec.get("type", "str"))
        unit = str(spec.get("unit", "") or "")
        lo, hi = spec.get("min"), spec.get("max")
        runtime = self._runtime_choices(spec)

        if runtime is not None and ptype == "str":
            # **可編輯的**下拉（F15-2）：清單是現在載了什麼，但值仍然可以是一個
            # 還沒載進來的名字 —— recipe 是在資料掛上來**之前**讀進來的，鎖死
            # 選單等於「開一份寫好的 recipe 會把那一格清空」。
            w = QComboBox()
            w.setEditable(True)
            w.addItems(runtime)
            w.setCurrentText("" if value is None else str(value))
            hint = self._EMPTY_HINTS.get(str(spec.get("choices_from") or ""), "")
            if not runtime and hint and w.lineEdit() is not None:
                w.lineEdit().setPlaceholderText(hint)
            w.currentTextChanged.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype in ("expr", "feature_keys"):
            # 算式／一串數字名 ＋ 一支「插入數字 ▾」（F21-B）。**不是**可編輯
            # 的下拉：使用者要打的是一個式子（或一串名字），不是從清單裡挑一個
            # 值 —— 下拉只負責把名字送進去，省掉「記得拼對」這件事。
            return self._make_expr_editor(name, value, kind=ptype)

        if ptype == "int":
            w = QSpinBox()
            w.setRange(int(lo) if lo is not None else -10 ** 9,
                       int(hi) if hi is not None else 10 ** 9)
            if unit:
                w.setSuffix(" " + unit)
            w.setValue(_safe_int(value))
            w.valueChanged.connect(lambda v, n=name: self._emit(n, int(v)))
            return w

        if ptype == "float":
            w = QDoubleSpinBox()
            span = None if (lo is None or hi is None) else float(hi) - float(lo)
            w.setDecimals(_float_decimals(lo, span, value))
            w.setRange(float(lo) if lo is not None else -1e9,
                       float(hi) if hi is not None else 1e9)
            w.setSingleStep(0.01 if (span is not None and span <= 2.0) else 0.1)
            if unit:
                w.setSuffix(" " + unit)
            w.setValue(_safe_float(value))
            w.valueChanged.connect(lambda v, n=name: self._emit(n, float(v)))
            return w

        if ptype == "bool":
            w = QCheckBox("Enabled")
            w.setChecked(bool(value))
            w.toggled.connect(lambda v, n=name: self._emit(n, bool(v)))
            return w

        if ptype == "choice":
            # ⚠ **現在沒有任何一張卡走這一支**（F68 第二輪把每一格選項都換成
            # `chip_choice`，使用者：「設定區都要變成這樣 icon 膠囊 + 文字」）。
            # 型別留著，因為「這一排的選項畫不出圖」是有可能的 —— 那時候硬畫
            # 一張圖是裝飾，而裝飾會讓使用者以為那裡有意思可以讀。
            # 真的要用的人會先撞到 `test_no_card_anywhere_still_shows_a_bare_dropdown`，
            # 那正是停下來想一下的地方。
            w = QComboBox()
            choices = [str(c) for c in (spec.get("choices") or [])]
            w.addItems(choices)
            text = str(value)
            if text in choices:
                w.setCurrentIndex(choices.index(text))
            w.currentTextChanged.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "curve":
            w = CurveField()
            w.set_text("" if value is None else str(value))
            w.curve_changed.connect(lambda t, n=name: self._emit(n, str(t)))
            w.curve_changed.connect(lambda _t: self._sync_curve_override())
            return w

        if ptype == "image_keys" and spec.get("direction") != "out":
            # F9-6：**來源只在畫布上決定**（使用者定調）。以前這裡是一排勾選框，
            # 於是同一件事有兩個入口 —— 拉線會改它、勾選框也會改它 —— 而畫布上
            # 那條線與這裡的勾選很容易對不起來（使用者的原話是「他會很亂連」）。
            # F68：那一格從「假的輸入框」變成**插槽**——同一顆埠的形狀、
            # 沒接線時講後果、而且可以直接挑一個上游的流（挑了之後由 Studio
            # 走跟拉線同一條路，線仍然是唯一的儲存）。
            return self._wiring_slot(name, spec, value)

        if ptype in ("region_key", "region_keys"):
            # F12：**區域的來源也只在畫布上決定**，跟影像流一模一樣。
            #
            # 以前這裡是下拉／勾選框（F11 Region-1）—— 那已經解掉「打錯字要跑
            # 一次 lint 才知道」的問題，但它留下第二個入口：畫布上沒有任何線
            # 表示這張卡用了上游的區域，而拿掉那張 Region 卡，量測卡會**安靜地
            # 改量整張圖**。使用者的話是「但我還是這樣怪怪的」。
            #
            # 現在區域在畫布上是一顆菱形埠 + 一條虛線，這一格只顯示接的是什麼。
            # 理由與 F9-6 對 image_keys 做的事逐字相同（「他會很亂連」）。
            # F68：改成插槽（見上面那一格的說明）。
            return self._wiring_slot(name, spec, value)

        if ptype == "multi_choice":
            choices = (runtime if runtime is not None
                       else [str(c) for c in (spec.get("choices") or [])])
            w = MultiChoicePicker(
                choices, "" if value is None else str(value),
                empty_hint=self._EMPTY_HINTS.get(
                    str(spec.get("choices_from") or ""), ""))
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "metric_chips":
            # `multi_choice` 的第二種長相（F18）—— **值的格式一字不差**。
            w = MetricChips([str(c) for c in (spec.get("choices") or [])],
                            "" if value is None else str(value))
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "metric_choice":
            # 單選版（F32）—— 值是一個 id，膠囊長相跟上面同一套。
            w = MetricPick([str(c) for c in (spec.get("choices") or [])],
                           "" if value is None else str(value))
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "channel_map":
            kind = str(spec.get("row_kind") or "images")
            w = ChannelMapField(
                "" if value is None else str(value),
                min_rows=(self._label_count if kind == "labels"
                          else self._image_count),
                row_kind=kind)
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "chip_choice":
            # `choice` 的第二種長相（F68 第二輪）—— **值的格式一字不差**，
            # 換掉的只有長相（同 metric_chips 對 multi_choice 做的事）。
            w = ChoiceChips([str(c) for c in (spec.get("choices") or [])],
                            [str(i) for i in (spec.get("icons") or [])],
                            "" if value is None else str(value),
                            spec.get("choice_help") or {},
                            labels=spec.get("choice_labels") or {})
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "cell_rois":
            w = CellRoisField("" if value is None else str(value))
            # 值不是在這裡編的（框畫在 cell 上）——按鈕只是把請求往上送。
            w.edit_requested.connect(lambda n=name: self.action_requested.emit(n))
            return w

        if ptype == "template":
            w = TemplateField("" if value is None else str(value))
            # 值不是在這裡編的（模板是一張影像）——按鈕只是把請求往上送，
            # 由 Studio 開對話框，成交之後照一般的路徑寫回參數。
            w.build_requested.connect(lambda n=name: self.action_requested.emit(n))
            return w

        if ptype == "image_key" and spec.get("direction") != "out":
            # F68：同上（單一角色的影像埠，例如「Ref image」）。
            # 同上（F9-6）：來源是接線的結果，不是這裡填的。
            #
            # ⚠ **只有輸入是唯讀的**（F10-7）。`write result to`（`out`）型別
            # 一樣是 image_key，但它是這張卡**吐出去**的那條流的名字 —— 那是
            # 使用者自己取的名字，不是接線的結果，唯讀等於「不給改」。
            # F9-6 那時候還沒有 `direction`，所以只能連輸出一起鎖住；使用者
            # 回報「Write result to 沒辦法改名（不給輸入）」就是這個。
            return self._wiring_slot(name, spec, value)

        w = QLineEdit()
        w.setText("" if value is None else str(value))
        w.textChanged.connect(lambda t, n=name: self._emit(n, str(t)))
        return w


# --------------------------------------------------------------------------- #
# 2b. CurveEditor —— 自己拉的色調曲線（F7-8）
# --------------------------------------------------------------------------- #
def _float_decimals(lo: Any, span: Optional[float], value: Any) -> int:
    """一個浮點欄位要顯示幾位小數（F68）。

    以前一律 3 位，於是「超過幾 σ」印成 ``0.000 σ``、「靠邊幾 px」印成
    ``0.000 px`` —— 三位小數在那些欄位上不是精度，是雜訊（而且讓人以為
    那一格需要那麼細）。

    規矩跟**已經存在的** step 一樣看範圍（`setSingleStep` 那一行）：

    * 下界是一個**小於 1 的正數** → 3 位。那種欄位本來就在細部
      （``nm_per_px`` 的 0.01、``gamma`` 的 0.1），砍掉小數位會讓它填不進去。
    * 範圍 ≤ 2 → 3 位（``min_score`` 的 −1…1 那種）。
    * 其餘 → 1 位（px、%、σ、灰階）。

    ⚠ **但顯示不准比 recipe 裡的值粗**：手寫 recipe 填了 ``2.55`` 的話，
    位數要夠寫得出它 —— 不然畫面上是 ``2.6``，而那是一個安靜的謊
    （QDoubleSpinBox 會把值捨進它的位數）。
    """
    if lo is not None and 0.0 < abs(float(lo)) < 1.0:
        want = 3
    elif span is not None and span <= 2.0:
        want = 3
    else:
        want = 1
    try:
        text = ("%.6f" % float(value)).rstrip("0")
        have = len(text.split(".")[1]) if "." in text else 0
    except (TypeError, ValueError):
        have = 0
    return max(want, min(have, 6))


def _wiring_display(text: str) -> QWidget:      # pragma: no cover - F68 之後沒人叫
    """「這條流從哪來」的**唯讀**顯示（F9-6）。

    為什麼是唯讀：來源改成**只在畫布上決定**。以前參數表單也能改，於是同一件事
    有兩個入口，而兩邊很容易對不起來 —— 使用者的原話是「他會很亂連」。

    唯讀不等於藏起來：這一格仍然要**看得到現在接的是什麼**，否則使用者得回畫布
    上一條一條線去數。空的時候講出「還沒接」而不是留白 —— 留白讀起來像壞掉。
    """
    w = QLineEdit()
    w.setText(str(text) if str(text).strip() else "")
    w.setPlaceholderText("not wired yet — drag a line on the canvas")
    w.setReadOnly(True)
    w.setToolTip("Set by the lines on the canvas. Drag from an output port to "
                 "change what this card works on.")
    w.setObjectName("wiringDisplay")
    w.setCursor(Qt.ArrowCursor)
    return w


class CurveEditor(QWidget):
    """可拖曳的色調曲線編輯器。橫軸 = 輸入灰階，縱軸 = 輸出灰階，兩軸都 0–1。

    操作（右下角就寫著，不用先看說明）
    ----------------------------------
    * 拖控制點 = 改曲線；
    * 在空白處按左鍵 = 加一個控制點；
    * 對控制點右鍵（或雙擊）= 刪掉它。頭尾兩點刪不掉，
      因為曲線必須覆蓋整個灰階範圍。

    **畫出來的線就是影像上套的線** —— 這裡呼叫的是 core 的
    ``algo.curve.curve_lut``，跟 ``gamma`` 卡執行時用的是同一個函式。
    UI 自己再實作一份插值是很容易發生的事，那會讓使用者看到的和跑出來的不一樣。
    這是本檔唯一一處 import ``d4t.core``，理由就是這個 —— 而且它是純運算、
    不碰引擎，沒有違反「元件不跑 pipeline」的約束。
    """

    curve_changed = Signal(str)

    _PAD = 10.0                 # 邊界留白（點拖到角落時還抓得到）
    _HIT = 9.0                  # 控制點的點擊半徑（螢幕像素）
    _DOT = 4.0

    def __init__(self, parent: Optional[QWidget] = None, compact: bool = True):
        super().__init__(parent)
        from ..core.pipeline.curve import IDENTITY, parse_curve

        self._parse = parse_curve
        self._points: List[Tuple[float, float]] = list(parse_curve(IDENTITY))
        self._drag: Optional[int] = None
        self._compact = bool(compact)
        #: 墊在曲線後面的直方圖（引擎算的那一份，見 :meth:`set_histogram`）。
        self._hist: List[float] = []
        self.setMinimumSize(QSize(150, 130 if compact else 300))
        if not compact:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip("Drag to bend · click to add a point · "
                        "right-click a point to remove it")

    # -- public API --------------------------------------------------------
    def text(self) -> str:
        from ..core.pipeline.curve import format_curve
        return format_curve(self._points)

    def points(self) -> List[Tuple[float, float]]:
        return list(self._points)

    def set_text(self, text: str, emit: bool = False) -> bool:
        """從控制點字串載入。字串壞掉時**保持原樣並回 False**。

        參數表單是「打字即生效」的，使用者打到一半必然出現不合法的中間狀態；
        那時候把曲線清成 y=x 會讓他辛苦拉的線消失。
        """
        try:
            pts = self._parse(text)
        except ValueError:
            return False
        self._points = list(pts)
        self.update()
        if emit:
            self.curve_changed.emit(self.text())
        return True

    def reset(self) -> None:
        from ..core.pipeline.curve import IDENTITY
        self.set_text(IDENTITY, emit=True)

    def is_identity(self) -> bool:
        from ..core.pipeline.curve import is_identity
        return is_identity(self._points)

    def set_histogram(self, counts: Optional[Sequence[float]]) -> None:
        """把**這張圖進來時**的灰階分布墊在曲線後面（F11 Enhance-UI-C）。

        為什麼要墊
        ----------
        曲線的橫軸是「輸入灰階」，而使用者不知道哪一段灰階**真的有畫素**。
        於是常見的兩種白工：在一個空的區間上把線拉得很陡（畫面完全沒變化），
        或者反過來，把所有畫素都在的那一小段壓平（一動就整片糊掉）。
        Photoshop 的 Curves 就是這個形狀，所以對「不會寫 code 但會修圖」的
        使用者是零學習成本。

        資料是**引擎算的那一份**（``ctx.meta['stream_change'][流]['before']``），
        UI 不自己再壓一次直方圖 —— 不然畫面上的分布跟真的跑出來的有機會不一樣。
        ``None`` / 空 = 沒有東西可墊（還沒跑過預覽），那就只畫格線。
        """
        vals = [float(v) for v in (counts or [])
                if float(v) == float(v) and float(v) >= 0.0]
        self._hist = vals
        self.update()

    def histogram(self) -> List[float]:
        """現在墊著的那一份（測試讀這個，不去讀畫素）。"""
        return list(self._hist)

    # -- 座標轉換 ----------------------------------------------------------
    def _plot_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(self._PAD, self._PAD,
                                            -self._PAD, -self._PAD)

    def _to_px(self, x: float, y: float) -> QPointF:
        r = self._plot_rect()
        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def _to_unit(self, p: QPointF) -> Tuple[float, float]:
        r = self._plot_rect()
        w = max(1.0, r.width())
        h = max(1.0, r.height())
        return (float(np.clip((p.x() - r.left()) / w, 0.0, 1.0)),
                float(np.clip((r.bottom() - p.y()) / h, 0.0, 1.0)))

    def _hit(self, p: QPointF) -> Optional[int]:
        for i, (x, y) in enumerate(self._points):
            if (self._to_px(x, y) - p).manhattanLength() <= self._HIT * 1.6:
                return i
        return None

    # -- painting ----------------------------------------------------------
    def _paint_histogram(self, p: QPainter, plot: QRectF) -> None:
        """墊在曲線後面的分布：很淡的實心柱，高度用平方根。

        平方根跟 Enhance 儀表用的是同一個理由：兩端的削平會堆出極高的柱子，
        線性刻度下其餘的分布會被壓成一條貼著底的線 —— 而那正是要看的形狀。
        """
        vals = self._hist
        if not vals:
            return
        top = max(vals)
        if top <= 0:
            return
        h = [math.sqrt(v / top) for v in vals]
        bw = plot.width() / float(len(h))
        col = QColor(TOKENS["text_disabled"])
        col.setAlpha(70)               # 背景就是背景：看得到形狀，不搶曲線
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        for i, v in enumerate(h):
            bar = v * plot.height()
            if bar <= 0.0:
                continue
            p.drawRect(QRectF(plot.left() + i * bw, plot.bottom() - bar,
                              max(1.0, bw), bar))

    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        from ..core.algo.curve import curve_lut

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        p.setBrush(QColor(TOKENS["image_backdrop"]))
        p.drawRoundedRect(r, 5, 5)

        plot = self._plot_rect()
        # 直方圖先畫 —— 它是**背景**。畫在曲線之後的話它會蓋住曲線，
        # 而曲線才是使用者在操作的東西。
        self._paint_histogram(p, plot)
        grid = QColor(TOKENS["border_default"])
        grid.setAlpha(120)
        p.setPen(QPen(grid, 1))
        for i in range(1, 4):
            f = i / 4.0
            p.drawLine(self._to_px(f, 0.0), self._to_px(f, 1.0))
            p.drawLine(self._to_px(0.0, f), self._to_px(1.0, f))

        # y = x 參考線（虛線）—— 使用者隨時看得出自己偏離了多少
        ref = QPen(QColor(TOKENS["text_disabled"]), 1, Qt.DashLine)
        p.setPen(ref)
        p.drawLine(self._to_px(0.0, 0.0), self._to_px(1.0, 1.0))

        accent = QColor(theme.seg_hex("image"))
        n = max(24, int(plot.width()))
        lut = curve_lut(self._points, n)
        p.setPen(QPen(accent, 2.0))
        prev = self._to_px(0.0, float(lut[0]))
        for i in range(1, n):
            cur = self._to_px(i / (n - 1.0), float(lut[i]))
            p.drawLine(prev, cur)
            prev = cur

        p.setPen(QPen(QColor(TOKENS["bg_surface"]), 1.5))
        p.setBrush(accent)
        for x, y in self._points:
            c = self._to_px(x, y)
            p.drawEllipse(c, self._DOT, self._DOT)
        p.end()

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        pos = QPointF(e.position())
        idx = self._hit(pos)
        if e.button() == Qt.RightButton:
            if idx is not None:
                self._remove(idx)
            return
        if e.button() != Qt.LeftButton:
            return
        if idx is None:
            idx = self._insert(*self._to_unit(pos))
            if idx is None:
                return
        self._drag = idx
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:       # noqa: D102 - Qt hook
        if self._drag is None:
            return
        x, y = self._to_unit(QPointF(e.position()))
        i = self._drag
        if i == 0:
            x = 0.0                       # 頭尾的 x 鎖住：曲線必須從 0 到 1
        elif i == len(self._points) - 1:
            x = 1.0
        else:
            # 不准越過鄰居 —— 越過去就不是函數了（同一個輸入兩個輸出）
            x = float(np.clip(x, self._points[i - 1][0] + 0.01,
                              self._points[i + 1][0] - 0.01))
        self._points[i] = (x, y)
        self.update()
        self.curve_changed.emit(self.text())

    def mouseReleaseEvent(self, _e) -> None:   # noqa: D102 - Qt hook
        if self._drag is not None:
            self._drag = None
            self.setCursor(Qt.CrossCursor)

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: D102 - Qt hook
        idx = self._hit(QPointF(e.position()))
        if idx is not None:
            self._remove(idx)

    def _insert(self, x: float, y: float) -> Optional[int]:
        """在 x 的位置插一個控制點；太靠近既有點就不插（會變成不合法的曲線）。"""
        if any(abs(px - x) < 0.02 for px, _py in self._points):
            return None
        self._points.append((x, y))
        self._points.sort(key=lambda pt: pt[0])
        self.update()
        self.curve_changed.emit(self.text())
        return self._points.index((x, y))

    def _remove(self, idx: int) -> None:
        if idx <= 0 or idx >= len(self._points) - 1:
            return                       # 頭尾刪不掉
        del self._points[idx]
        self.update()
        self.curve_changed.emit(self.text())


class CurveField(QWidget):
    """參數表單裡的曲線欄位：小張的編輯器 + ``Reset`` / ``Enlarge…``。

    小張的可以直接拉（常見的微調不用開視窗），要做細活再按 ``Enlarge…``
    開一張大的。兩邊改的是同一組控制點。
    """

    curve_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self.editor = CurveEditor(self)
        self.editor.curve_changed.connect(self._on_changed)
        lay.addWidget(self.editor)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(5)
        self.reset_button = QPushButton("Reset to y = x", self)
        self.reset_button.setToolTip("Put the curve back to a straight line "
                                     "(the gamma slider takes over again)")
        self.reset_button.clicked.connect(self.editor.reset)
        self.enlarge_button = QPushButton("Enlarge…", self)
        self.enlarge_button.setToolTip("Open a big curve canvas")
        self.enlarge_button.clicked.connect(self.open_dialog)
        bar.addWidget(self.reset_button)
        bar.addWidget(self.enlarge_button)
        bar.addStretch(1)
        lay.addLayout(bar)

    def text(self) -> str:
        return self.editor.text()

    def set_text(self, text: str, emit: bool = False) -> bool:
        return self.editor.set_text(text, emit=emit)

    def is_identity(self) -> bool:
        return self.editor.is_identity()

    def set_histogram(self, counts: Optional[Sequence[float]]) -> None:
        """把這張圖的灰階分布墊在曲線後面（見 `CurveEditor.set_histogram`）。"""
        self._hist = list(counts or [])
        self.editor.set_histogram(counts)
        dlg = getattr(self, "_dialog", None)
        if dlg is not None and dlg.isVisible():
            dlg.editor.set_histogram(counts)

    def histogram(self) -> List[float]:
        return self.editor.histogram()

    def open_dialog(self) -> "CurveDialog":
        dlg = CurveDialog(self.editor.text(), self)
        # 放大的那一張也要墊 —— 「做細活」正是最需要知道哪一段有畫素的時候。
        dlg.editor.set_histogram(getattr(self, "_hist", []))
        dlg.curve_changed.connect(self._adopt)
        dlg.show()
        self._dialog = dlg          # 保住參照，不然 show() 之後會被 GC
        return dlg

    def _adopt(self, text: str) -> None:
        if self.editor.set_text(text):
            self.curve_changed.emit(self.editor.text())

    def _on_changed(self, text: str) -> None:
        self.curve_changed.emit(text)


class CurveDialog(QDialog):
    """放大版的曲線畫布。非模態 —— 一邊拉曲線一邊看主視窗的預覽更新。"""

    curve_changed = Signal(str)

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Tone curve")
        self.setModal(False)
        self.resize(420, 460)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        head = QLabel("Input gray level across, output up. Drag a point to "
                      "bend the curve; click an empty spot to add one; "
                      "right-click a point to remove it.", self)
        head.setWordWrap(True)
        head.setObjectName("paramHint")
        lay.addWidget(head)

        self.editor = CurveEditor(self, compact=False)
        self.editor.set_text(text)
        self.editor.curve_changed.connect(self.curve_changed)
        lay.addWidget(self.editor, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        reset = QPushButton("Reset to y = x", self)
        reset.clicked.connect(self.editor.reset)
        buttons.addButton(reset, QDialogButtonBox.ResetRole)
        buttons.rejected.connect(self.close)
        lay.addWidget(buttons)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if (math.isnan(f) or math.isinf(f)) else f


# --------------------------------------------------------------------------- #
# 3. LibraryPanel
# --------------------------------------------------------------------------- #
def draw_group_icon(p: QPainter, group: str, color: str, size: float) -> None:
    """在 ``p`` 的目前原點畫一個 ``size`` × ``size`` 的階段圖示。

    **抽成自由函式**，是為了讓左側 rail 的按鈕、卡片庫的區塊標題、以及畫布上的
    節點卡三處共用完全相同的圖形 —— 使用者在 rail 上看到的尺，在節點上看到的
    也要是同一把尺，不然「圖示」就只是裝飾而不是語言。

    不吃任何圖檔：repo 有「只放純文字檔」的不變量（公司機 DLP 會擋含二進位的
    壓縮檔，見 ``docs/HANDOVER.md`` §5）。``.svg`` 其實是純文字、過得了 DLP，
    但用 QPainter 連「要不要把圖檔加進版控」這個問題都不用問，而且顏色直接吃
    token —— 換主題時圖示自動跟著變。
    """
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), max(1.2, size / 11.0))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    w = h = float(size)
    m = w / 7.5                       # 邊界留白，隨尺寸縮放
    g = str(group)

    if g == "input":                    # 匣子 + 往下的箭頭
        p.drawRect(QRectF(m, h * 0.55, w - 2 * m, h * 0.45 - m))
        p.drawLine(QPointF(w / 2, m), QPointF(w / 2, h * 0.46))
        p.drawLine(QPointF(w / 2 - w * 0.16, h * 0.30), QPointF(w / 2, h * 0.46))
        p.drawLine(QPointF(w / 2 + w * 0.16, h * 0.30), QPointF(w / 2, h * 0.46))
    elif g == "enhance":                # 亮度：半實心圓
        p.drawEllipse(QRectF(m, m, w - 2 * m, h - 2 * m))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPie(QRectF(m, m, w - 2 * m, h - 2 * m), -90 * 16, 180 * 16)
    elif g == "region":                 # 取景框（四個角）+ 中心點
        c = w * 0.24
        for x0, y0, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1),
                               (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            p.drawLine(QPointF(x0, y0), QPointF(x0 + c * dx, y0))
            p.drawLine(QPointF(x0, y0), QPointF(x0, y0 + c * dy))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        r = w * 0.11
        p.drawEllipse(QRectF(w / 2 - r, h / 2 - r, 2 * r, 2 * r))
    elif g == "compare":                # 兩個交疊的方框
        side = w - 2 * m - w * 0.2
        p.drawRect(QRectF(m, m, side, side))
        p.drawRect(QRectF(m + w * 0.2, m + w * 0.2, side, side))
    elif g == "measure":                # 尺（一條線 + 刻度）
        base = h - m
        p.drawLine(QPointF(m, base), QPointF(w - m, base))
        for i in range(4):
            x = m + i * (w - 2 * m) / 3.0
            p.drawLine(QPointF(x, base),
                       QPointF(x, base - (h * 0.40 if i % 2 == 0 else h * 0.23)))
    elif g == "search":                 # 放大鏡（rail 上的搜尋鈕，不是流程階段）
        r = w * 0.29
        p.drawEllipse(QRectF(m, m, 2 * r, 2 * r))
        p.drawLine(QPointF(m + 2 * r * 0.86, m + 2 * r * 0.86),
                   QPointF(w - m, h - m))
    # ⚠ **這裡以前還有一顆 ``g == "algo"`` 的 Σ 圖示，2026-08-28 刪掉了**（F48）。
    # 它畫的是卡片庫的 Algo 那一段，而那一段 F24 §5 就從 `GROUPS` 拿掉、
    # F48 連 `GROUP_ALGO` 這個常數一起刪了 —— `GroupIcon` 只被兩個地方叫
    # （rail 的 StageButton 與區塊標題），兩邊的 gid 都來自 `LibraryPanel.GROUPS`，
    # 所以那一支 `elif` 再也走不到。**不是把它留成便利貼**：這個檔案裡的
    # 圖示是一段一顆，而「有圖示、沒有那一段」正好是下一個人會照著加卡的形狀。
    elif g == "adc":                    # 標籤：給這顆 defect 一個 bin
        # ADC 這一段的產物是 score + **bin**，而「貼上一個分類」就是標籤。
        # 尖的那一頭讓輪廓在 15 px 下仍然不像任何一個方框（region 是四個角、
        # compare 是兩個疊起來的框）。
        p.drawPolygon(QPolygonF([
            QPointF(m, h * 0.26), QPointF(w * 0.62, h * 0.26),
            QPointF(w - m, h / 2), QPointF(w * 0.62, h - h * 0.26),
            QPointF(m, h - h * 0.26)]))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        r = w * 0.075                   # 標籤上的孔。實心的 —— 15 px 下描邊會糊掉
        p.drawEllipse(QRectF(m + w * 0.14 - r, h / 2 - r, 2 * r, 2 * r))
    elif g == "output":                 # 敞口的托盤 + 往外走的箭頭
        # 跟 ``input`` 是**一對**（跟 glyph 的 save / export 同一種對比）：
        # 一樣是托盤加箭頭，差別在**箭頭往哪走**，而那正好是這兩段唯一的差別。
        # 托盤這裡是**敞口的**（只有左、下、右三邊）—— input 那個是封起來的
        # 方匣（東西掉進去），output 是東西離開的地方，所以上緣不封。
        base = h - m
        p.drawLine(QPointF(m, h * 0.62), QPointF(m, base))
        p.drawLine(QPointF(m, base), QPointF(w - m, base))
        p.drawLine(QPointF(w - m, base), QPointF(w - m, h * 0.62))
        p.drawLine(QPointF(w / 2, h * 0.60), QPointF(w / 2, m))
        a = w * 0.17
        p.drawLine(QPointF(w / 2, m), QPointF(w / 2 - a, m + a))
        p.drawLine(QPointF(w / 2, m), QPointF(w / 2 + a, m + a))
    else:                               # 沒見過的 group：打勾（保底，不是某一段）
        p.drawLine(QPointF(m, h * 0.52), QPointF(w * 0.42, h - m))
        p.drawLine(QPointF(w * 0.42, h - m), QPointF(w - m, m))


class GroupIcon(QWidget):
    """:func:`draw_group_icon` 的 widget 包裝（給 rail 與區塊標題用）。"""

    _SIZE = 15

    def __init__(self, group: str, color: str, parent: Optional[QWidget] = None,
                 size: Optional[int] = None):
        super().__init__(parent)
        self.group = str(group)
        self.color = str(color)
        self._SIZE = int(size or self._SIZE)
        self.setFixedSize(self._SIZE, self._SIZE)

    def set_color(self, color: str) -> None:
        self.color = str(color)
        self.update()

    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        p = QPainter(self)
        draw_group_icon(p, self.group, self.color, float(self._SIZE))
        p.end()


#: 從卡片庫拖出去時帶的 MIME 型別（F7-22）。用自訂型別而不是純文字：
#: 純文字會讓「從別的視窗拖一段字進畫布」也變成新增卡片。
CARD_MIME = "application/x-d4t-card"


class _LibraryItem(QFrame):
    """卡片庫的一列：名稱 + hover 才出現的「Add」；雙擊也能加入。

    ``set_missing(streams)`` 會把「上游還沒產出它要的影像流」這件事顯示成
    一個灰字 badge（例：``needs diff``）並把整列調淡 —— 但**仍然可以加**。
    卡片庫的順序不等於執行順序，使用者可能先放卡再補上游；擋著不給加只會
    讓人以為工具壞了。
    """

    activated = Signal(str)

    def __init__(self, describe: Dict[str, Any], color: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.step_key = str(describe.get("key", ""))
        self.reads = [str(r) for r in (describe.get("reads") or ())]
        self.setObjectName("libItem")
        self.setCursor(Qt.PointingHandCursor)
        self._base_tip = (str(describe.get("help", ""))
                          or str(describe.get("label", "")))
        if describe.get("requires_ref"):
            self._base_tip += " (needs a ref image)"
        self.setToolTip(self._base_tip)
        self.setProperty("missing", "false")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 6, 3)
        lay.setSpacing(6)

        self.dot = QFrame()
        self.dot.setFixedSize(5, 5)
        self.dot.setStyleSheet("background:%s; border-radius:2px;" % color)
        lay.addWidget(self.dot)

        self.label = QLabel(str(describe.get("label") or self.step_key))
        self.label.setToolTip(self._base_tip)
        lay.addWidget(self.label, 1)

        self.badge = QLabel("")
        self.badge.setObjectName("libBadge")
        self.badge.setVisible(False)
        self.missing: List[str] = []
        lay.addWidget(self.badge)

        self.add_button = small_button(
            "Add", "Append this card to the end of the pipeline", shape="wide")
        self.add_button.clicked.connect(
            lambda: self.activated.emit(self.step_key))
        self.add_button.setVisible(False)
        lay.addWidget(self.add_button)

    # -- 前置條件 badge -----------------------------------------------------
    def set_missing(self, missing: Sequence[str]) -> None:
        """``missing`` = 這張卡要讀、但上游還沒有的影像流。"""
        missing = [str(m) for m in (missing or ())]
        self.missing = list(missing)
        self.setProperty("missing", "true" if missing else "false")
        restyle(self)
        if missing:
            self.badge.setText("needs %s" % ", ".join(missing))
            self.badge.setVisible(True)
            self.setToolTip(
                "%s\n\nNot available yet: this card reads %s, which nothing "
                "upstream produces so far. You can still add it — the pipeline "
                "order is up to you."
                % (self._base_tip, ", ".join(missing)))
        else:
            self.badge.setVisible(False)
            self.setToolTip(self._base_tip)

    def badge_text(self) -> str:
        """目前的 badge 文字（沒有就空字串）。

        看的是 :attr:`missing` 而不是 ``badge.isVisible()`` —— 視窗還沒 show()
        之前 Qt 的可見性一律是 False，headless 測試會全部誤判。
        """
        return self.badge.text() if self.missing else ""

    def enterEvent(self, e) -> None:      # noqa: D102 - Qt hook
        self.add_button.setVisible(True)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:      # noqa: D102 - Qt hook
        self.add_button.setVisible(False)
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:   # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.activated.emit(self.step_key)

    # -- 拖到畫布上（F7-22）-------------------------------------------------
    #
    # 「Add」是**工具決定位置**（接在選著的那張後面）；拖是**使用者決定位置**。
    # 兩個都留著：n8n 兩種都有，而且第一次用的人多半先看到按鈕。
    def mousePressEvent(self, e) -> None:         # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self._press_at = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:          # noqa: D102 - Qt hook
        start = getattr(self, "_press_at", None)
        if start is None or not (e.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(e)
        if (e.pos() - start).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(e)
        self._press_at = None
        self.start_drag()

    def start_drag(self) -> None:
        """開始把這張卡拖出去（測試直接呼叫這支，不模擬滑鼠軌跡）。"""
        mime = QMimeData()
        mime.setData(CARD_MIME, self.step_key.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec(Qt.CopyAction)


class StageButton(QFrame):
    """左側 rail 的一顆大按鈕：icon + 階段名 + 卡片數。

    這是 F7-7 的要求：**先用大 icon 分功能，按下去才帶出裡面的小功能。**
    六個階段一次全展開，等於一開始就把 15 張卡攤在使用者面前 ——
    那正是「太瑣碎」的來源。
    """

    clicked = Signal(str)

    _ICON = 30

    def __init__(self, group: str, title: str, subtitle: str, colour: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.group = str(group)
        self.setObjectName("stageButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("%s — %s" % (title, subtitle))
        self._colour = colour
        self._active = False

        self.setFixedWidth(58)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 7, 2, 5)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignHCenter)

        self.icon = GroupIcon(self.group, colour, self, size=self._ICON)
        lay.addWidget(self.icon, 0, Qt.AlignHCenter)

        self.label = QLabel(title, self)
        self.label.setAlignment(Qt.AlignHCenter)
        self.label.setStyleSheet("font-size:9px; font-weight:600;")
        lay.addWidget(self.label)

        self.count = QLabel("", self)
        self.count.setAlignment(Qt.AlignCenter)
        self.count.setObjectName("stageCount")
        lay.addWidget(self.count, 0, Qt.AlignHCenter)
        self._style_count()
        self.setProperty("active", "false")

    def _style_count(self) -> None:
        """「有幾張卡」那個數字的顏色（F13-3）。

        **階段色，沒有網底**（使用者第二輪定調：「不要有網底色，單純數字的
        顏色即可」）。顏色由 `theme.count_color` 算在 rail 的底色上 ——
        它會把字推到過得了 AA 為止，所以淺色主題不會像以前那樣看不見。

        顏色本身就講完了「這是這一段的東西」：它跟上面那個圖示、卡片庫的圓點、
        畫布上那塊圖示磚是同一個。
        """
        self.count.setStyleSheet(
            "background:transparent; color:%s; font-size:9px; font-weight:600;"
            % theme.count_color(self.group))

    def set_count(self, n: int) -> None:
        self.count.setText("" if n <= 0 else str(int(n)))
        # 空的時候不要留一塊有底色的小方塊。
        self.count.setVisible(n > 0)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.setProperty("active", "true" if self._active else "false")
        restyle(self)

    def is_active(self) -> bool:
        return self._active

    def refresh_colour(self, colour: str) -> None:
        # 這裡**只剩**階段色（那是每一顆各自的顏色，不是主題的）。底色、邊框、
        # 圓角、hover、選中都在 QSS 裡了。
        self._colour = colour
        self.icon.set_color(colour)
        self._style_count()          # 藥丸的兩個顏色也是算出來的（F13-3）

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.group)
        super().mousePressEvent(e)


def column_header(title: str, parent: Optional[QWidget] = None) -> QLabel:
    """一欄工作區的小標題（F13-4）。

    主視窗有四個直欄，而以前它們之間只有一條 splitter —— **沒有任何東西說
    「這一欄是什麼」**。使用者要靠內容反推自己在看哪一塊，而那件事在他還不熟
    的時候正是最貴的。

    刻意做得很輕（10px、大寫、字距拉開、`text_hint`）：它是一個**地標**不是
    一個標題列，佔的高度要小到不值得為它讓出畫面。
    """
    lbl = QLabel(str(title).upper(), parent)
    lbl.setObjectName("columnHeader")
    return lbl


class LibraryPanel(QWidget):
    """卡片庫：依**流程階段**分組（F7-3），每組一個 QPainter 畫的 icon + 標題。

    為什麼不再依 ``category`` 分
    ----------------------------
    ``category``（影像／算法）描述的是「這張卡吐什麼型別」——那是引擎的分類
    （快取切點、驗證順序）。使用者要的是「我想幹嘛」，所以改用 ``group``：

        Input → Enhance → Region → Compare → Measure → ADC

    讀起來是一句話，而且每段有一條機械可判定的規則（見 ``pipeline/step.py``）。

    另外兩件讓 17 列不再瑣碎的事：

    * **搜尋框** —— 打字即時過濾（比對名稱、key 與說明）。
    * **前置條件 badge** —— ``set_available_streams()`` 之後，
      上游還沒產出所需影像流的卡會標成 ``needs diff`` 並調淡。
    """

    add_requested = Signal(str)
    #: 卡片區展開/收起（``True`` = 展開）。主視窗據此縮放左欄寬度 ——
    #: 收起來時整欄只留 rail，工作區才真的變寬。
    panel_toggled = Signal(bool)

    #: 顯示順序與標題。id 對應 ``pipeline/step.py`` 的 ``GROUP_*``，而**順序必須
    #: 與那邊的 ``GROUP_ORDER`` 逐項相同** —— 兩份表是同一件事的兩半（這裡多帶
    #: 給人看的標題與副標），而它們漂開的話卡片庫的順序會跟引擎講的不一樣。
    #: ``tests/test_ui_f16_stages.py`` 鎖著。
    GROUPS = (
        ("input", "Input", "Load this defect's images"),
        ("enhance", "Enhance", "Image in, image out"),
        ("region", "ROI", "Decide where to look"),
        ("measure", "Measure", "Image + region in, numbers out"),
        # Algo 那一列拿掉了（F24 §5，使用者 2026-08-24 點頭）：算式、補值、
        # 跨顆換算全部住進判定（working numbers），這一段清空之後留著只是
        # 一個永遠空白的抽屜。
        ("compare", "Compare", "Two images in, difference out"),
        ("adc", "ADC", "Numbers in, score and bin out"),
        ("output", "Output", "The end of the line - write it somewhere"),
    )
    _ORDER = tuple(g for g, _t, _s in GROUPS)
    _EMPTY_TEXT = "(no cards in this section)"
    _NO_MATCH_TEXT = "(no card matches)"

    #: group -> 所屬的三段式 segment。**顏色不再從這裡取**（F7-9 起走
    #: ``theme.group_hex``，六個階段各一個色相）；這份對照留著是因為
    #: 「這個階段屬於哪一段」在說明文字與排序上仍然成立。
    _GROUP_SEG = {"input": "image", "enhance": "image", "region": "algo",
                  "compare": "image", "measure": "algo", "adc": "adc"}

    #: 直式 icon rail 的寬度（收起來時整個 panel 就縮到只剩這條）。
    RAIL_W = 66
    #: 展開時卡片區至少要多寬（卡名 + badge 放得下）。
    PANEL_W = 190

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items: Dict[str, _LibraryItem] = {}
        self._describes: Dict[str, Dict[str, Any]] = {}
        self._section_boxes: Dict[str, QVBoxLayout] = {}
        self._sections: Dict[str, QWidget] = {}
        self._headers: Dict[str, QWidget] = {}
        self._icons: Dict[str, GroupIcon] = {}
        self._available: List[str] = []
        self._query = ""
        self._shown_groups: List[str] = []

        self._open_group: Optional[str] = None

        # 版面：**直式 rail（左）｜ 卡片區（右）**。
        # F7-8：像工作列一樣由上而下，點了 icon 才顯示裡面的卡 ——
        # 這樣左邊的操作區平常是乾淨的。
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.rail = QWidget(self)
        self.rail.setObjectName("stageRail")
        self.rail.setFixedWidth(self.RAIL_W)
        rail_lay = QVBoxLayout(self.rail)
        rail_lay.setContentsMargins(2, 6, 2, 6)
        rail_lay.setSpacing(2)
        self.stage_buttons: Dict[str, StageButton] = {}
        for gid, title, subtitle in self.GROUPS:
            btn = StageButton(gid, title, subtitle, theme.group_hex(gid),
                              self.rail)
            btn.clicked.connect(self.toggle_group)
            rail_lay.addWidget(btn)
            self.stage_buttons[gid] = btn
        rail_lay.addStretch(1)

        # 搜尋鈕留在 rail 上（不是在 panel 裡）—— panel 收起來時搜尋框跟著藏，
        # 沒有這顆就再也打不開搜尋了。
        self.search_button = StageButton(
            "search", "Search", "Find a card by name or description",
            TOKENS["text_secondary"], self.rail)
        self.search_button.clicked.connect(lambda _g: self.focus_search())
        rail_lay.addWidget(self.search_button)
        outer.addWidget(self.rail)

        # 右邊：搜尋 + 卡片清單（收起來時整塊隱藏）
        self.panel = QWidget(self)
        panel_lay = QVBoxLayout(self.panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(0)

        # 地標自己不帶內距 —— 這裡用跟搜尋框同一組邊界（左 6 / 右 8），
        # 兩者才會對齊在同一條線上。
        head_wrap = QWidget(self.panel)
        hw = QHBoxLayout(head_wrap)
        hw.setContentsMargins(8, 6, 8, 0)
        self.header = column_header("Library", head_wrap)
        hw.addWidget(self.header)
        panel_lay.addWidget(head_wrap)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search cards…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Filter the card library by name or description")
        self.search.textChanged.connect(self._on_search)
        wrap = QWidget(self.panel)
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(6, 2, 8, 4)
        wl.addWidget(self.search)
        panel_lay.addWidget(wrap)

        self._scroll = QScrollArea(self.panel)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._body = QVBoxLayout(self._host)
        self._body.setContentsMargins(6, 2, 8, 6)
        self._body.setSpacing(2)

        for gid, title, subtitle in self.GROUPS:
            self._body.addWidget(self._make_header(gid, title, subtitle))
            # 卡片列裝在**一個自己的 widget 裡**，而不是直接 addLayout 一個
            # QVBoxLayout（F17）。收起來的那七段要真的不佔位置：
            # 一個藏起來的 widget 在父層 layout 裡是零，但一個**空的巢狀
            # layout 不是** —— 它的 contentsMargins（這裡是下緣 8 px）照算。
            # 於是「展開哪一段」會決定那一段往下掉多少：Input 的標題貼在最上面，
            # Output 的被前面七段各推 8 px，整整低了 56 px。使用者看到的就是
            # 「點 Input 跟點 Output 帶出來的高度不一樣」。
            body = QWidget(self._host)
            body.setObjectName("libSection")
            box = QVBoxLayout(body)
            box.setContentsMargins(0, 0, 0, 8)
            box.setSpacing(1)
            self._body.addWidget(body)
            self._sections[gid] = body
            self._section_boxes[gid] = box

        self._body.addStretch(1)
        self._scroll.setWidget(self._host)
        panel_lay.addWidget(self._scroll, 1)
        outer.addWidget(self.panel, 1)

        self.set_steps([])
        self.toggle_group(self._ORDER[0])       # 開窗先展開 Input

    # -- 區塊標題（icon + 標題，取代舊的填滿色塊）---------------------------
    def _make_header(self, gid: str, title: str, subtitle: str) -> QWidget:
        colour = theme.group_hex(gid)
        head = QWidget(self)
        head.setObjectName("libSectionHeader")
        head.setProperty("group", gid)
        head.setToolTip(subtitle)
        lay = QHBoxLayout(head)
        lay.setContentsMargins(4, 8, 4, 2)
        lay.setSpacing(7)

        icon = GroupIcon(gid, colour, head)
        icon.setToolTip(subtitle)
        lay.addWidget(icon)
        self._icons[gid] = icon

        lbl = QLabel(title, head)
        lbl.setObjectName("libSectionTitle")
        lbl.setToolTip(subtitle)
        lbl.setStyleSheet("color:%s; font-weight:700; font-size:11px;"
                          % TOKENS["text_secondary"])
        lay.addWidget(lbl)
        lay.addStretch(1)
        self._headers[gid] = head
        return head

    # -- public API --------------------------------------------------------
    def set_steps(self, steps: Sequence[Dict[str, Any]]) -> None:
        """用 ``Step.describe()`` 的 dict 清單重建整個卡片庫。"""
        self._clear()
        self._describes = {str(d.get("key", "")): dict(d) for d in (steps or [])}
        by_group: Dict[str, List[Dict[str, Any]]] = {g: [] for g in self._ORDER}
        for d in steps or []:
            gid = str(d.get("group") or "") or "enhance"
            by_group.setdefault(gid, []).append(d)

        for gid in self._ORDER:
            box = self._section_boxes[gid]
            entries = by_group.get(gid, [])
            if not entries:
                box.addWidget(self._empty_label(self._EMPTY_TEXT))
                continue
            colour = theme.group_hex(gid)
            for d in entries:
                item = _LibraryItem(d, colour, self._sections[gid])
                item.activated.connect(self.add_requested)
                box.addWidget(item)
                self._items[item.step_key] = item
        for gid, btn in self.stage_buttons.items():
            btn.set_count(len(by_group.get(gid, [])))
        self._apply_filter()
        self._apply_badges()

    def set_available_streams(self, streams: Sequence[str]) -> None:
        """告訴卡片庫「目前 pipeline 到最後為止產出了哪些影像流」。

        據此標出前置條件未滿足的卡。傳空清單 = 不知道（badge 全清）。
        """
        self._available = [str(s) for s in (streams or [])]
        self._apply_badges()

    def entry(self, step_key: str) -> Optional[_LibraryItem]:
        """取得某張卡片的那一列（給主視窗做 highlight／給測試點擊）。"""
        return self._items.get(step_key)

    def step_keys(self) -> List[str]:
        return list(self._items)

    def visible_step_keys(self) -> List[str]:
        """目前**看得到**的卡（搜尋過濾之後）。

        同樣用明確狀態（``_matches``）而不是 ``isVisible()``，理由見
        :meth:`_LibraryItem.badge_text`。
        """
        return [k for k in self._items
                if self._matches(k)
                and self._group_open(str((self._describes.get(k) or {})
                                         .get("group") or ""))]

    def section_titles(self) -> List[str]:
        return [lbl.text() for lbl in self.findChildren(QLabel)
                if lbl.objectName() == "libSectionTitle"]

    def visible_section_titles(self) -> List[str]:
        """搜尋之後還有卡片的區塊標題（順序同 :data:`GROUPS`）。"""
        return [title for gid, title, _sub in self.GROUPS
                if gid in self._shown_groups]

    # -- 展開 / 收合（F7-7）--------------------------------------------------
    def toggle_group(self, group: Optional[str]) -> None:
        """點同一顆再點一次 = 收起來；點別顆 = 換過去（一次只開一段）。

        傳 ``None`` 直接全部收起來（測試 / 外部呼叫用）。訊號帶過來的是
        ``str``，所以這裡不能用 ``str(group)`` 一律轉字串 —— ``str(None)``
        會變成 ``"None"``，看起來像一個真的存在的段名。
        """
        gid = None if group is None else str(group)
        self._open_group = None if (gid is None or self._open_group == gid) else gid
        for g, btn in self.stage_buttons.items():
            btn.set_active(g == self._open_group)
        self._sync_panel()
        self._apply_filter()

    def panel_open(self) -> bool:
        """卡片區現在是展開的嗎（收起來時只剩 rail）。

        用明確狀態而不是 ``isVisible()`` —— 視窗還沒 show 之前 ``isVisible()``
        一律是 False，那會讓「收起來了嗎」在建構期永遠答錯。
        """
        return self._open_group is not None or bool(self._query)

    def _sync_panel(self) -> None:
        """展開狀態 -> panel 顯示 + 本身的最小寬度 + 通知外面重排欄寬。"""
        show = self.panel_open()
        self.panel.setVisible(show)
        self.setMinimumWidth(self.RAIL_W + (self.PANEL_W if show else 0))
        self.panel_toggled.emit(show)

    def open_group(self) -> Optional[str]:
        """目前展開的是哪一段（都收起來時回 None）。"""
        return self._open_group

    def set_query(self, text: str) -> None:
        """程式化設定搜尋字串（測試 / 外部呼叫用）。"""
        self.search.setText(str(text or ""))

    def focus_search(self) -> None:
        """展開卡片區並把游標放進搜尋框（rail 上的放大鏡鈕）。"""
        if not self.panel_open():
            self.toggle_group(self._ORDER[0])
        self.search.setFocus(Qt.OtherFocusReason)
        self.search.selectAll()

    def refresh_colors(self) -> None:
        """換主題之後重新取色（icon 與圓點都是自繪/內嵌樣式）。"""
        for gid, icon in self._icons.items():
            icon.set_color(theme.group_hex(gid))
        for gid, btn in self.stage_buttons.items():
            btn.refresh_colour(theme.group_hex(gid))
        self.search_button.refresh_colour(TOKENS["text_secondary"])

    # -- internals ---------------------------------------------------------
    def _empty_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("libEmpty")
        lbl.setStyleSheet("color:%s; font-size:11px; padding-left:12px;"
                          % TOKENS["text_disabled"])
        return lbl

    def _on_search(self, text: str) -> None:
        self._query = str(text or "").strip().lower()
        self._sync_panel()
        self._apply_filter()

    def _matches(self, key: str) -> bool:
        if not self._query:
            return True
        d = self._describes.get(key) or {}
        hay = " ".join([key, str(d.get("label", "")), str(d.get("help", "")),
                        str(d.get("group", ""))]).lower()
        return all(tok in hay for tok in self._query.split())

    def _group_open(self, gid: str) -> bool:
        """搜尋中 = 跨全部階段找；沒搜尋 = 只看展開的那一段。"""
        return True if self._query else (gid == self._open_group)

    def _apply_filter(self) -> None:
        """過濾卡片；沒展開的階段整段收起來。"""
        for key, item in self._items.items():
            gid = str((self._describes.get(key) or {}).get("group") or "")
            item.setVisible(self._matches(key) and self._group_open(gid))
        shown: List[str] = []
        for gid, head in self._headers.items():
            box = self._section_boxes[gid]
            hit = False
            opened = self._group_open(gid)
            for i in range(box.count()):
                w = box.itemAt(i).widget()
                if isinstance(w, _LibraryItem):
                    hit = hit or (self._matches(w.step_key) and opened)
                elif isinstance(w, QLabel):
                    # 空區塊的提示語只在該段展開、且沒搜尋時顯示
                    show = opened and not self._query
                    w.setVisible(show)
                    hit = hit or show
            head.setVisible(hit)
            # 標題與卡片列是一起出現、一起消失的（見建構式裡的說明）：
            # 只藏標題的話，收起來的那一段仍然會用它 layout 的下緣把後面的
            # 每一段往下推。
            self._sections[gid].setVisible(hit)
            if hit:
                shown.append(gid)
        self._shown_groups = [g for g in self._ORDER if g in shown]

    def _apply_badges(self) -> None:
        avail = set(self._available)
        for key, item in self._items.items():
            if not self._available:
                item.set_missing(())
                continue
            item.set_missing([r for r in item.reads if r not in avail])

    def _clear(self) -> None:
        self._items = {}
        for box in self._section_boxes.values():
            while box.count():
                item = box.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()


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
        small.setPointSize(8)
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
        p.drawText(QRectF(r.left(), r.bottom() + 2, r.width() / 2, 14),
                   Qt.AlignLeft, "%.3g" % lo)
        p.drawText(QRectF(r.center().x(), r.bottom() + 2, r.width() / 2, 14),
                   Qt.AlignRight, "%.3g" % hi)

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
    def mousePressEvent(self, e) -> None:   # noqa: D102 - Qt hook
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

    def mouseMoveEvent(self, e) -> None:    # noqa: D102 - Qt hook
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

    def mouseReleaseEvent(self, e) -> None:  # noqa: D102 - Qt hook
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

    def leaveEvent(self, _e) -> None:       # noqa: D102 - Qt hook
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


# --------------------------------------------------------------------------- #
# 6. FeatureTable / VerdictChip
# --------------------------------------------------------------------------- #
def _fmt_number(value: Any) -> str:
    """數值 → 好讀字串。

    ⚠ **F52 起它只是 `numbers.format_feature_value` 的別名。** 以前這裡是
    自己一份（整數捷徑 ＋ ``%.3f`` ＋極小值 ``%.3g``），而
    `gallery._fmt_score` 是**同一份抄第二次然後漂開的**。實測的下場：
    ``99.995`` 在結果表上是 ``100``、在這張單顆特徵表上是 ``99.995`` ——
    使用者在 Results 看到一顆是 100，點進去變成 99.995，會以為自己點錯顆。

    名字留著是因為這個檔案裡有好幾個呼叫端（門檻標籤、特徵表）。
    """
    return format_feature_value(value)

#: 絕對量 / 相對量 —— :func:`feature_gloss` 回的第一個值。
FEATURE_ABSOLUTE = "absolute"
FEATURE_RELATIVE = "relative"


def feature_gloss(name: str, about: Optional[Dict[str, str]] = None,
                  spec: Optional[Any] = None) -> Tuple[str, str]:
    """一個特徵名 →（絕對量／相對量／空的, 一句話說它是什麼）。

    F18 補課第三輪（使用者 2026-08-21）：「我認為 feature 中絕對量的跟相對量
    的還是要分類好（不然不清楚命名規則會很痛苦），或者 Feature 的功能 UI
    顯示需要再優化」。

    PR-3 起吃 ``spec``（`FeatureSpec` —— 名字誕生處宣告的身分）：相對／絕對
    看 ``family``、統計量是 ``metric``、cmp 比的是哪個統計量在 ``stat``。
    **沒有 spec 就留白，不猜** —— 以前這裡拆 ``cmp_``/``glv_`` 字串用最長
    比對把 metric 猜回來，而那正是「拆特徵字串猜語意」禁令要清掉的一處。

    說明的內容不是在這裡發明的：絕對量走 `algo.glv.metric_formula`（公式的
    家），相對量走 :data:`METRIC_GROUPS` 的短標籤（膠囊的家）。抄第二份出來
    的那一份一定會漂（`CLAUDE.md` §0）。

    ``about`` 是「跟誰比」——名字裡沒有那件事（``epi_cmp_delta_median`` 不講
    mg），所以由呼叫端從引擎的 ``meta["compares"]`` 帶進來。
    """
    if spec is None:
        return "", ""
    text = str(name or "")
    ref = str((about or {}).get(text, "") or "")
    family = str(getattr(spec, "family", "") or "")
    if family == "cmp":
        label = metric_face(spec.metric)[1] if spec.metric \
            else (spec.base or text)
        body = label if not spec.stat else "%s of %s" % (label, spec.stat)
        return FEATURE_RELATIVE, _with_variant(
            spec, body + " vs %s" % (ref or "the reference"))
    if family == "glv":
        mid = str(spec.metric or spec.base or "")
        # **先問卡片**（F76）：`metric_formula` 只認得統計量，而這一族裡有
        # 一整批不是統計量（`glv_worst_*` / `glv_boxes*`）—— 它們以前落到
        # 最後那個 `metric_face`，印出來就是自己的 id。
        body = _card_says(spec) or algo_glv.metric_formula(mid)
        if body == "—":
            body = metric_face(mid)[1]
        return FEATURE_ABSOLUTE, _with_variant(spec, body)
    # 其餘的一句話**由卡片自己說**（`Step.FEATURE_HELP`，2026-09-01）。
    # 在這裡補一張表是最快的做法，也是最錯的：那句話會跟卡片本人的說明漂開，
    # 而漂開的時候畫面上看起來完全正常（`CLAUDE.md` §0）。
    said = _card_says(spec)
    return (FEATURE_ABSOLUTE, _with_variant(spec, said)) if said else ("", "")


#: 變體怎麼**改寫**那個量的說明（F76，2026-09-02）。``%s`` 是那個量自己的
#: 那一句（`metric_formula` 或卡片的 `FEATURE_HELP`）。
#:
#: 為什麼一定要有這一層：`feature_gloss` 以前只讀 `spec.metric`，於是
#: ``glv_median_typical`` / ``_outlier`` / ``_outlier_box`` / ``_worst``
#: 四列的說明**一字不差**（都寫 ``median(gray)``）—— 而 ``_outlier_box``
#: 的值根本不是灰階，它是一個框號。實測：出貨的 `rsem-worst-box` 上有 97 個
#: 特徵的說明跟別的特徵完全相同。
#:
#: ⚠ **`_outlier` 跟 `_worst` 常常不是同一格**（實測 24 顆：judge 那個量
#: 24/24 相同，其他量只有 2–5/24）。使用者 2026-09-02 的原話是「反而這樣會
#: 誤導別人以為他是最 worst 的」—— 所以這兩句話要**明講它們在挑哪一格**，
#: 那是名字上唯一沒有的資訊。
VARIANT_GLOSS = {
    "typical": "%s - the middle one across all the boxes",
    "outlier": "%s - on the box furthest out on this statistic alone, "
               "which is often not the one the judge picked",
    "outlier_box": "which box was furthest out on this statistic alone "
                   "(%s)",
    "worst": "%s - on the box the judge picked as the odd one out",
    "nm": "%s, in nanometres",
    "nm2": "%s, in square nanometres",
    "raw": "%s, before it was scaled against the batch",
    "rescued": "%s - kept under this name because a later card wrote over it",
}


def _with_variant(spec: Any, body: str) -> str:
    """把變體那句話套上去（沒有變體、或不認得的變體就原樣回）。"""
    pattern = VARIANT_GLOSS.get(str(getattr(spec, "variant", "") or ""))
    return (pattern % body) if (pattern and body) else body


def feature_unit(spec: Any) -> str:
    """這個數字的單位 —— **問卡片，不猜**（F76，2026-09-02）。

    先看變體（`step.VARIANT_UNITS`：``_outlier_box`` 的值是框號，不是那個
    量），再看那張卡的 `Step.feature_units`。查不到就**留白** —— 一個猜錯的
    單位比沒有單位糟得多（同 `feature_gloss` 的退化原則）。
    """
    if spec is None:
        return ""
    from ..core.pipeline.step import VARIANT_UNITS

    var = str(getattr(spec, "variant", "") or "")
    if var in VARIANT_UNITS:
        return VARIANT_UNITS[var]
    try:
        from ..core.pipeline import get_step

        table = get_step(str(getattr(spec, "card", "") or "")).feature_units()
    except Exception:                      # noqa: BLE001 — 顯示用，不能擋畫面
        return ""
    for key in (getattr(spec, "metric", ""), getattr(spec, "base", ""),
                getattr(spec, "name", "")):
        got = str(table.get(str(key or ""), "") or "")
        if got:
            return got
    return ""


def _card_says(spec: Any) -> str:
    """``spec`` 的那張卡怎麼形容這個數字（查不到就空字串）。"""
    try:
        from ..core.pipeline import get_step

        table = get_step(str(getattr(spec, "card", "") or "")).feature_help()
    except Exception:                      # noqa: BLE001 — 顯示用，不能擋畫面
        return ""
    for key in (getattr(spec, "base", ""), getattr(spec, "metric", ""),
                getattr(spec, "name", "")):
        got = str(table.get(str(key or ""), "") or "")
        if got:
            return got
    return ""


#: ⚠ 這裡以前有一張 `_ABS_GLOSS`（`glv_pixels` / `glv_ok` 兩條）。
#: **F76 刪掉了** —— 那兩句話現在住在 GLV 卡的 `FEATURE_HELP` 上，跟同一族
#: 其他十二句在一起。留兩份的話它們會漂，而漂開的時候畫面上看起來完全正常。


#: 一個特徵名拆好之後，畫在畫面上要用哪些角色（F37 A4，2026-08-26）。
#:
#: 使用者 2026-08-26：「值可否用上下標　更清楚　配合顏色」。
#:
#: 三個角色，而**每一個都對應名字裡真的存在的一段**（拆解由卡片給，見
#: `Step.feature_parts`）：
#:
#: =========  =========  ==================================================
#: 主體       正常大小   ``glv_median`` —— 家族 tag ＋ 統計量
#: 區域       **上標**   ``epi`` —— 顏色取自 `theme.region_hex`
#: 影像流     **下標**   ``test``
#: =========  =========  ==================================================
#:
#: 為什麼區域是上標而不是下標：一份 recipe 常常只有一條流、卻有好幾個區域，
#: 所以區域是**比較常出現、也比較需要一眼分辨**的那一個，而上標的位置比下標
#: 顯眼。挑一個然後從此不變 —— 兩種都成立，會出錯的是兩邊各挑一個。
#:
#: ⚠ **顏色不是在這裡發明的。** `theme.region_hex(index)` 同時是影像上那個
#: ROI 框的顏色與畫布上區域埠的顏色（`MultiSourceStep.CURRENT_REGION_INDEX`
#: 用同一個序）—— 三個地方同一個顏色，而來源只有一份。各自挑一份的話，
#: "top,bot" 在一邊是 0/1、在另一邊是 1/0，而**顏色指錯區域比沒有顏色糟得多**。
FEATURE_SUP = "region"
FEATURE_SUB = "stream"


def feature_html(name: str, parts: Optional[Dict[str, Any]] = None) -> str:
    """一個特徵名 → 要畫的那一小段 HTML（拆不出來就是原樣的純文字）。

    純函式，沒有 Qt —— 所以「畫成什麼樣」測得起來，不必開一個視窗。
    """
    text = _escape(str(name or ""))
    got = dict(parts or {})
    base = str(got.get("base", "") or "")
    if not base:
        return text
    out = [_escape(base)]
    region = str(got.get(FEATURE_SUP, "") or "")
    if region:
        colour = theme.region_hex(int(got.get("region_index", 0) or 0))
        out.append('<sup style="color:%s"><b>%s</b></sup>'
                   % (colour, _escape(region)))
    stream = str(got.get(FEATURE_SUB, "") or "")
    if stream:
        out.append('<sub style="color:%s">%s</sub>'
                   % (TOKENS["text_hint"], _escape(stream)))
    own = str(got.get("own", "") or "")
    if own:
        # 使用者自己取的名字**不縮小也不上下標**：它是他打的字，不是軟體
        # 推出來的一段 —— 兩者在畫面上要分得出來。
        out.append(' <span style="color:%s">%s</span>'
                   % (TOKENS["text_secondary"], _escape(own)))
    return "".join(out)


def _escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


class _FeatureNameDelegate(QStyledItemDelegate):
    """第一欄用 rich text 畫（上下標＋顏色）。

    為什麼要一個 delegate：``QTableWidgetItem`` 只吃純文字，而 Unicode 的上標
    只有幾個字母有（``ᵃᵇᶜ``）—— 區域名是使用者取的任意識別字，湊不出來。
    """

    #: item 上放 HTML 的那個角色（純文字仍然放在 DisplayRole，所以複製、
    #: 搜尋、測試讀到的都還是**打得進分數表達式的那一串**）。
    HTML_ROLE = Qt.UserRole + 7

    def paint(self, painter, option, index) -> None:
        html = index.data(self.HTML_ROLE)
        if not html:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""                       # 文字交給 QTextDocument 畫
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setDocumentMargin(0)
        doc.setHtml('<span style="color:%s">%s</span>'
                    % (opt.palette.text().color().name(), html))
        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget)
        painter.save()
        painter.translate(rect.left(),
                          rect.top() + max(0.0, (rect.height()
                                                 - doc.size().height()) / 2.0))
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        html = index.data(self.HTML_ROLE)
        size = super().sizeHint(option, index)
        if not html:
            return size
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setDocumentMargin(0)
        doc.setHtml(html)
        # 上下標會把行高撐高一點點 —— 讓欄寬跟著真的畫出來的寬度走，
        # 否則名字會被截成 `test_epi_hot_glv_m…`（而那正是這一輪要治的病）。
        return QSize(int(doc.idealWidth()) + 12, max(size.height(),
                                                     int(doc.size().height())))


class FeatureTable(QTableWidget):
    """特徵 / 它是什麼 / 數值 三欄表；``score`` 永遠釘在最後一列且用粗體。

    中間那一欄是 F18 補課第三輪加的（使用者：「目前只有縱向空間被用到，
    橫向空間幾乎沒有 —— Feature 右側就只有 Value 還到最右邊」）。它放的是
    :func:`feature_gloss` 翻出來的那一句話，而**絕對量與相對量用顏色分**：
    相對量是強調色，絕對量是次要色。名字的規則因此不必先背。
    """

    _SCORE = "score"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, 3, parent)
        self.setHorizontalHeaderLabels(["Feature", "What it is", "Value"])
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        head = self.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        # 第一欄用 rich text 畫（上下標＋顏色，F37 A4）。**只有第一欄** ——
        # 值那一欄要保持等寬對齊，說明那一欄本來就是一句話。
        self._name_delegate = _FeatureNameDelegate(self)
        self.setItemDelegateForColumn(0, self._name_delegate)
        self._specs: Dict[str, Any] = {}

    #: 一個分組（F13-1 的 ①）：``title`` 是**哪張卡產出的**、``color`` 是那張卡
    #: 的階段色、``names`` 是這一組裡的特徵、``collapsed`` 決定一開始收不收。
    #: 呼叫端（Studio）算好再交過來 —— 這個 widget 不去問 model 也不去問引擎。
    _HEADER_ROLE = Qt.UserRole + 1

    def set_features(self, features: Optional[Dict[str, Any]],
                     highlight: Iterable[str] = (),
                     sections: Optional[Sequence[Dict[str, Any]]] = None,
                     about: Optional[Dict[str, str]] = None,
                     specs: Optional[Dict[str, Any]] = None) -> None:
        """填表。``highlight`` 內的特徵名會用 accent 底色標出（例：分數用到的）。

        ``sections`` 是**分組**（F13-1 ①，2026-08-19 使用者：「feature 的顯示
        太陽春了不易閱讀」）。一條平的 name/value 清單裡，``n_channels`` 跟
        ``snr_max`` 長得一模一樣 —— 而它們一個是「這張卡讀了幾頁」、一個是
        會決定 bin 的量測值。

        **分組不是我發明的規則**：引擎本來就記著每個特徵是哪張卡寫的
        （`meta["feature_owner"]`），卡片也早就宣告了哪些是診斷數字
        （`Step.diagnostic_features`）。這裡只是把已經知道的事顯示出來。

        沒給 ``sections`` 就是舊行為（一條平的清單）—— CLI、報表、既有測試
        都還走那條路。
        """
        features = dict(features or {})
        hi = set(highlight or ())
        self._about = dict(about or {})
        # 名字的身分是**卡片宣告的**（`resolve_feature_specs`，PR-3）——
        # 沒給就照原樣顯示整串、說明留白。少一點資訊，不會是錯的資訊。
        self._specs = dict(specs or {})
        rows: List[Tuple[str, Any]] = []          # ("head"/"row", 內容)
        if sections:
            seen = set()
            for sec in sections:
                names = [n for n in (sec.get("names") or [])
                         if n in features and n != self._SCORE and n not in seen]
                # 同一張卡底下**絕對量在前、相對量在後**（其餘保持原順序）。
                # 兩者交錯的話，那一段要一行一行讀才知道自己在看哪一種。
                # 「哪個是相對量」看宣告的 ``family``，不再拆名字。
                names.sort(key=lambda n: 1 if getattr(
                    self._specs.get(n), "family", "") == "cmp" else 0)
                if not names:
                    continue
                seen.update(names)
                rows.append(("head", sec))
                rows.extend(("row", n) for n in names)
            rest = [n for n in features
                    if n not in seen and n != self._SCORE]
            if rest:
                rows.append(("head", {"title": "Other", "color": "",
                                      "names": rest}))
                rows.extend(("row", n) for n in rest)
        else:
            rows.extend(("row", n) for n in features if n != self._SCORE)
        if self._SCORE in features:
            rows.append(("row", self._SCORE))

        self.clearSpans()
        self.setRowCount(len(rows))
        current: Optional[QTableWidgetItem] = None
        collapsed = False
        for row, (kind, payload) in enumerate(rows):
            if kind == "head":
                current = self._fill_header(row, payload)
                collapsed = bool(payload.get("collapsed"))
                self.setRowHidden(row, False)
                continue
            name = str(payload)
            self._fill_row(row, name, features[name], name in hi,
                           name == self._SCORE)
            self.setRowHidden(row, collapsed and name != self._SCORE)
        self._header_rows = [r for r, (k, _p) in enumerate(rows) if k == "head"]

    def _fill_header(self, row: int, sec: Dict[str, Any]) -> QTableWidgetItem:
        """一列分組標題（橫跨兩欄，點一下收合）。"""
        title = str(sec.get("title") or "")
        colour = str(sec.get("color") or "") or TOKENS["text_secondary"]
        n = len([x for x in (sec.get("names") or [])])
        item = QTableWidgetItem("%s%s  ·  %d" % (
            "▸ " if sec.get("collapsed") else "▾ ", title, n))
        font = item.font()
        font.setBold(True)
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.0))
        item.setFont(font)
        item.setData(self._HEADER_ROLE, True)
        item.setForeground(QColor(theme.readable_on(
            colour, theme.mix_hex(colour, TOKENS["bg_surface"], 0.14))))
        item.setBackground(QColor(theme.mix_hex(
            colour, TOKENS["bg_surface"], 0.14)))
        self.setItem(row, 0, item)
        for col in (1, 2):
            self.setItem(row, col, QTableWidgetItem(""))
            self.item(row, col).setBackground(QColor(theme.mix_hex(
                colour, TOKENS["bg_surface"], 0.14)))
        self.setSpan(row, 0, 1, 3)
        return item

    def _fill_row(self, row: int, name: str, value: Any,
                  highlighted: bool, is_score: bool) -> None:
        key_item = QTableWidgetItem(str(name))
        spec = (getattr(self, "_specs", None) or {}).get(str(name))
        # **純文字仍然是 DisplayRole** —— 複製、搜尋、測試讀到的都還是那一串
        # 打得進分數表達式的字。HTML 只是它的長相（拆解 = ``spec.parts()``，
        # 跟 `Step.feature_parts` 同一個形狀、同一個產地）。
        html = feature_html(str(name), spec.parts() if spec is not None
                            else None)
        if html != _escape(str(name)):
            key_item.setData(_FeatureNameDelegate.HTML_ROLE, html)
        kind, gloss = feature_gloss(str(name), getattr(self, "_about", None),
                                    spec)
        about_item = QTableWidgetItem(gloss)
        # **絕對量與相對量用顏色分**（使用者要的第二種分類）：相對量走強調色，
        # 絕對量走次要色。文字本身也講得出來（`… vs mg`），所以不是只靠顏色。
        about_item.setForeground(QColor(
            TOKENS["accent_active"] if kind == FEATURE_RELATIVE
            else TOKENS["text_hint"]))
        small = about_item.font()
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1.0))
        about_item.setFont(small)
        val_item = QTableWidgetItem(_fmt_number(value))
        val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # **單位在懸停上**（F76 刀 2）。這一欄同時裝著灰階 0–255、幾個 σ、
        # 像素座標、框號與布林旗標，而它們長得一模一樣 —— 那正是使用者
        # 2026-09-02 的「後面帶的數值好亂」。⚠ 這裡刻意**不改顯示字串**：
        # 值那一欄要保持等寬對齊，而單位該有的位置是列尾的一格
        # （F76 刀 4 的新面板）。這一輪先讓它有得問。
        unit = feature_unit(spec)
        if unit:
            val_item.setToolTip("unit: %s" % unit)
        if is_score:
            font = key_item.font()
            font.setBold(True)
            key_item.setFont(font)
            val_item.setFont(font)
            key_item.setForeground(QColor(TOKENS["accent_active"]))
            val_item.setForeground(QColor(TOKENS["accent_active"]))
        if highlighted:
            bg = QColor(TOKENS["accent_bg"])
            key_item.setBackground(bg)
            about_item.setBackground(bg)
            val_item.setBackground(bg)
        self.setItem(row, 0, key_item)
        self.setItem(row, 1, about_item)
        self.setItem(row, 2, val_item)

    def about_text(self, name: str) -> Optional[str]:
        """中間那一欄寫了什麼（測試與工具讀得到）。"""
        for r in range(self.rowCount()):
            key = self.item(r, 0)
            if key is not None and not self.is_header_row(r) \
                    and key.text() == name:
                item = self.item(r, 1)
                return None if item is None else item.text()
        return None

    def is_header_row(self, row: int) -> bool:
        item = self.item(int(row), 0)
        return bool(item is not None and item.data(self._HEADER_ROLE))

    def toggle_section(self, row: int) -> None:
        """收合／展開某一組（點標題那一列）。"""
        if not self.is_header_row(row):
            return
        item = self.item(row, 0)
        text = item.text()
        opening = text.startswith("▸")
        item.setText(("▾" if opening else "▸") + text[1:])
        for r in range(row + 1, self.rowCount()):
            if self.is_header_row(r):
                break
            key = self.item(r, 0)
            if key is not None and key.text() == self._SCORE:
                continue
            self.setRowHidden(r, not opening)

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        row = self.rowAt(int(e.position().y()) if hasattr(e, "position")
                         else int(e.y()))
        if row >= 0 and self.is_header_row(row):
            self.toggle_section(row)
            e.accept()
            return
        super().mousePressEvent(e)

    def section_titles(self) -> List[str]:
        """每一組的標題（測試與狀態列讀得到；不含那個 ▾ 與計數）。"""
        out: List[str] = []
        for r in range(self.rowCount()):
            if self.is_header_row(r):
                text = self.item(r, 0).text()
                out.append(text[2:].split("  ·  ")[0])
        return out

    def feature_names(self) -> List[str]:
        """表上的**特徵**（分組標題不算 —— 它不是一個特徵）。"""
        return [self.item(r, 0).text() for r in range(self.rowCount())
                if self.item(r, 0) is not None and not self.is_header_row(r)]

    def value_text(self, name: str) -> Optional[str]:
        for r in range(self.rowCount()):
            key = self.item(r, 0)
            if key is not None and key.text() == name:
                val = self.item(r, 2)
                return None if val is None else val.text()
        return None


class VerdictChip(QLabel):
    """判定 chip：``bin 1 · ≥門檻`` / ``bin 0 · <門檻`` / ``—``。

    ``is_real_style=True`` 時色彩語意反轉：bin 1 代表「這是真缺陷」，是壞消息
    （紅），bin 0 是乾淨（綠）。預設（False）則照「過門檻 = 好」來配色。
    文字兩種模式都一樣，只有顏色換邊。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(112)
        self.setMinimumHeight(28)
        self._bin: Optional[int] = None
        self.set_verdict(None)

    def set_verdict(self, bin_value: Optional[Any] = None,
                    is_real_style: bool = False) -> None:
        try:
            b = None if bin_value is None else int(bin_value)
        except (TypeError, ValueError):
            b = None
        self._bin = b
        if b is None:
            text, tone = "—", "neutral"
        elif b == 1:
            text = "bin 1 · ≥ threshold"
            tone = "bad" if is_real_style else "good"
        elif b == 0:
            text = "bin 0 · < threshold"
            tone = "good" if is_real_style else "bad"
        else:
            text, tone = "bin %d" % b, "neutral"
        bg = TOKENS["chip_%s_bg" % tone]
        fg = TOKENS["chip_%s_text" % tone]
        border = TOKENS["chip_%s_border" % tone]
        self.setText(text)
        self.setProperty("tone", tone)
        self.setStyleSheet(
            "background:%s; color:%s; border:1px solid %s; border-radius:8px;"
            "padding:4px 12px; font-weight:700;" % (bg, fg, border))

    def verdict(self) -> Optional[int]:
        return self._bin

    def tone(self) -> str:
        return str(self.property("tone"))
