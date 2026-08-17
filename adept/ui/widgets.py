# ADEPT Studio widget library — authored 2026-07-28 (M3).
# ImageView 的 zoom/pan 骨架 vendored from: PEAR/pear/ui/image_view.py（去掉 ROI 編輯）。
"""Studio 的六個可重用元件 —— 全部「資料驅動」，**不碰引擎**。

設計約束（很重要，別破壞）：

1. 這裡的元件只吃 dict / list / ndarray，只發 Signal。任何一個元件都不會
   import ``adept.core``、不會跑 pipeline、不會開檔案。組裝與呼叫引擎是
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QMimeData, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDrag,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QHeaderView,
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

from . import theme
from .theme import TOKENS

__all__ = [
    "ImageView",
    "ParamForm",
    "LibraryPanel",
    "HistogramWidget",
    "FeatureTable",
    "VerdictChip",
    "TemplateField",
    "to_uint8",
    "small_button",
    "apply_button_cursors",
    "restyle",
    "IconButton",
    "GLYPH_ICONS",
    "draw_glyph_icon",
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


#: 按鈕上畫得出來的圖示（F7-23 第四輪）。名字是**這顆鈕在做什麼**，
#: 不是它長什麼樣 —— 呼叫端說 ``"fit"``，不說「兩端帶箭頭的斜線」。
GLYPH_ICONS = (
    "undo", "redo", "theme", "prev", "next", "play", "chevron_down",
    "zoom_in", "zoom_out", "fit", "tidy", "up", "down", "close",
    # 工具列那五顆（F7-24）＋ 兩個沒有 KLARF 的入口（F11 Input-2／Input-3）
    "folder", "document", "save", "templates", "export", "stack",
    "folder_open",
    # 畫布彈出視窗（F8-UI D 案）
    "popout",
)


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


def _paint_glyph(widget: QWidget, name: str, side: str = "center") -> None:
    """把 ``name`` 畫到 ``widget`` 上（給 icon 按鈕的 ``paintEvent`` 用）。

    顏色取自 **widget 自己的 palette**，而 palette 的 ``ButtonText`` 是 Qt 從
    QSS 的 ``color`` 解析出來的 —— 所以換膚、變灰（``:disabled`` 那條）全部
    自動跟著，這裡不必知道任何 token 名字，也不必在換主題時被誰通知。
    """
    from PySide6.QtGui import QPalette

    r = widget.contentsRect()
    size = max(9.0, min(float(min(r.width(), r.height())), 15.0))
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
        #: 量測尺按著時的那一條帶（axis, 起, 迄；影像像素）。見 :meth:`set_measure`。
        self._measure: Optional[Tuple[str, float, float]] = None

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
                    focus: int = -1) -> None:
        """把 ROI 框疊在影像上（**正規化**座標 ``(nx, ny, nw, nh)``）。

        為什麼要疊在這裡而不是只有「跨顆檢視」那個視窗
        ----------------------------------------------
        定位卡的參數是**一邊拖一邊看**決定的（F7-8 那條：「先想好一個數字再
        輸入」那個順序是反的）。框只出現在另一個要按鈕、要跑完一批才看得到的
        視窗裡，等於把這件事變成「改一次、跑一次、再回來看」——
        而敏感度這種參數要試十幾次。

        座標用正規化的，所以縮放平移都跟著影像走，換一顆 patch 尺寸也不用重算。
        ``focus`` 是要特別標出來的那一個（交會定位的 ``_center``：缺陷所在的
        那一塊），畫成實線＋角標，其餘畫細線 —— 一堆一模一樣的框看不出哪個是
        「這一顆」的。
        """
        self._overlay = [tuple(float(v) for v in r) for r in (rects or [])
                         if r is not None and len(tuple(r)) == 4]
        self._overlay_focus = int(focus)
        self.update()

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

    def _paint_overlay(self, p: QPainter) -> None:
        if self._pixmap is None or not self._overlay:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        s = self._scale or 1.0
        accent = QColor(TOKENS["accent"])
        # 框在小 patch 上會很細，所以線寬不隨縮放變薄（**框是給人看的標記，
        # 不是影像內容**）；但也不要粗到把 5px 的框整個蓋掉。
        thin = QPen(accent, 1.0)
        thin.setCosmetic(True)
        thick = QPen(QColor(TOKENS["danger_text"]), 1.8)
        thick.setCosmetic(True)
        p.setBrush(Qt.NoBrush)
        for i, (nx, ny, nw, nh) in enumerate(self._overlay):
            r = QRectF(self._offset.x() + nx * iw * s,
                       self._offset.y() + ny * ih * s,
                       max(1.0, nw * iw * s), max(1.0, nh * ih * s))
            p.setPen(thick if i == self._overlay_focus else thin)
            p.drawRect(r)

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
        self._paint_measure(p)
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
        top.addWidget(self.name_label)

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

    _EMPTY = "(select a Profile card to see its curve)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data: Dict[str, Any] = {}
        self._name = ""
        self._ruler: Optional[Tuple[float, float]] = None
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
        self._end_ruler()
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
        p.drawText(QRectF(rect.left() + 6, rect.top() + 2, rect.width() - 12, 14),
                   Qt.AlignVCenter | Qt.AlignLeft, self.summary())
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
                 parent: Optional[QWidget] = None):
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

    def choice_names(self) -> List[str]:
        return [b.text() for b in self._boxes]

    def _on_toggled(self, _checked: bool) -> None:
        if not self._emitting:
            self.changed.emit(self.text())


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

    def __init__(self, value: str = "", parent: Optional[QWidget] = None,
                 min_rows: int = 0):
        super().__init__(parent)
        self._edits: List[QLineEdit] = []
        self._emitting = False
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

        self._add_btn = QPushButton("Add another image", self)
        self._add_btn.setProperty("variant", "secondary")
        self._add_btn.setToolTip(
            "Add a row for one more image. A defect with five images "
            "(one BSE plus four SE, say) needs five rows.")
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
        rows = max(len(self._DEFAULTS), max(pairs) if pairs else 0,
                   self._min_rows)
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

    def set_min_rows(self, n: int) -> None:
        """這批資料一顆有幾張圖 —— 列數至少排到這麼多（不動已經填的名字）。"""
        self._min_rows = max(0, int(n))
        self.set_text(self.text())

    # -- 內部 ----------------------------------------------------------------
    def _default_name(self, index: int) -> str:
        if index < len(self._DEFAULTS):
            return self._DEFAULTS[index]
        return "img%d" % (index + 1)

    def _add_row(self, emit: bool = True) -> None:
        i = len(self._edits)
        label = QLabel("Image %d" % (i + 1), self)
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

        self.button = QPushButton("Build template from a full-size image…", self)
        self.button.setProperty("variant", "secondary")
        self.button.setToolTip(
            "Measure the repeating cell from one full-size image and store it "
            "inside this recipe. The image is only needed here — the recipe "
            "stays a single file you can hand to someone else.")
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
        self.button.setText("Build template from a full-size image…"
                            if not self._value else "Rebuild template…")

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
                "text). Mark the region on it with the four Region sliders "
                "below." % (w, h, len(self._value) / 1024.0))


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

    _EMPTY_TEXT = "(Pick a card from the library, or select a step in the pipeline)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._rows: Dict[str, _ParamRow] = {}
        #: 目前這批資料**一顆有幾張圖**（0 = 沒有資料）。只有 `channel_map` 的
        #: 編輯器用得到它 —— 但它是「資料的事實」而不是「這張卡的參數」，
        #: 所以放在表單上（一份資料一次）而不是塞進 `set_step` 的簽章。
        self._image_count = 0
        #: 小標題：``section 名 -> [QLabel]`` 與 ``參數名 -> section 名``。
        #: 整組都被 ``show_when`` 藏起來時，標題也要跟著不見 —— 一個底下什麼
        #: 都沒有的標題比沒有標題更讓人以為畫面壞了。
        self._sections: Dict[str, List[QWidget]] = {}
        self._section_of: Dict[str, str] = {}
        #: 標了 ``advanced`` 的那幾列（預設收起來）。
        self._advanced: set = set()
        #: 目前這張卡每個參數的值 —— ``show_when`` 要靠它判斷哪幾列該在。
        self._values: Dict[str, Any] = {}
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
            if isinstance(row.editor, ChannelMapField):
                row.editor.set_min_rows(n)

    def set_step(self, describe: Optional[Dict[str, Any]],
                 current_params: Optional[Dict[str, Any]] = None,
                 stream_choices: Optional[Sequence[str]] = None) -> None:
        """重建表單。``describe=None`` -> 顯示提示語（未選節點）。"""
        current_params = dict(current_params or {})
        streams = [str(s) for s in (stream_choices or [])]
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
            spec = row.spec.get("show_when")
            shown = True
            if spec:
                ctrl, values = str(spec[0]), [str(v) for v in spec[1]]
                shown = str(self._values.get(ctrl, "")) in values
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

    def _shown_by_rules(self, name: str) -> bool:
        """撇開「進階收起來了」這件事，這一列本身算不算數（``show_when``）。"""
        row = self._rows.get(name)
        spec = None if row is None else row.spec.get("show_when")
        if not spec:
            return row is not None
        return str(self._values.get(str(spec[0]), "")) in [str(v) for v in spec[1]]

    def _make_editor(self, spec: Dict[str, Any], value: Any,
                     streams: Sequence[str]) -> QWidget:
        name = str(spec.get("name", ""))
        ptype = str(spec.get("type", "str"))
        unit = str(spec.get("unit", "") or "")
        lo, hi = spec.get("min"), spec.get("max")

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
            w.setDecimals(3)
            w.setRange(float(lo) if lo is not None else -1e9,
                       float(hi) if hi is not None else 1e9)
            span = None if (lo is None or hi is None) else float(hi) - float(lo)
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
            # 現在這一格只**顯示**目前接進來的是哪幾條，改要回畫布上拉線。
            return _wiring_display("" if value is None else str(value))

        if ptype == "multi_choice":
            w = MultiChoicePicker([str(c) for c in (spec.get("choices") or [])],
                                  "" if value is None else str(value))
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "channel_map":
            w = ChannelMapField("" if value is None else str(value),
                                min_rows=self._image_count)
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "template":
            w = TemplateField("" if value is None else str(value))
            # 值不是在這裡編的（模板是一張影像）——按鈕只是把請求往上送，
            # 由 Studio 開對話框，成交之後照一般的路徑寫回參數。
            w.build_requested.connect(lambda n=name: self.action_requested.emit(n))
            return w

        if ptype == "image_key" and spec.get("direction") != "out":
            # 同上（F9-6）：來源是接線的結果，不是這裡填的。
            #
            # ⚠ **只有輸入是唯讀的**（F10-7）。`write result to`（`out`）型別
            # 一樣是 image_key，但它是這張卡**吐出去**的那條流的名字 —— 那是
            # 使用者自己取的名字，不是接線的結果，唯讀等於「不給改」。
            # F9-6 那時候還沒有 `direction`，所以只能連輸出一起鎖住；使用者
            # 回報「Write result to 沒辦法改名（不給輸入）」就是這個。
            return _wiring_display("" if value is None else str(value))

        w = QLineEdit()
        w.setText("" if value is None else str(value))
        w.textChanged.connect(lambda t, n=name: self._emit(n, str(t)))
        return w


# --------------------------------------------------------------------------- #
# 2b. CurveEditor —— 自己拉的色調曲線（F7-8）
# --------------------------------------------------------------------------- #
def _wiring_display(text: str) -> QWidget:
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
    這是本檔唯一一處 import ``adept.core``，理由就是這個 —— 而且它是純運算、
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
    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        from ..core.algo.curve import curve_lut

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        p.setBrush(QColor(TOKENS["image_backdrop"]))
        p.drawRoundedRect(r, 5, 5)

        plot = self._plot_rect()
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

    def open_dialog(self) -> "CurveDialog":
        dlg = CurveDialog(self.editor.text(), self)
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
    else:                               # adc / 其他：打勾
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
CARD_MIME = "application/x-adept-card"


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
        self.count.setAlignment(Qt.AlignHCenter)
        self.count.setObjectName("stageCount")
        lay.addWidget(self.count)
        self.setProperty("active", "false")

    def set_count(self, n: int) -> None:
        self.count.setText("" if n <= 0 else str(int(n)))

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

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.group)
        super().mousePressEvent(e)


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

    #: 顯示順序與標題。id 對應 ``pipeline/step.py`` 的 ``GROUP_*``。
    GROUPS = (
        ("input", "Input", "Load this defect's images"),
        ("enhance", "Enhance", "Image in, image out"),
        ("region", "ROI", "Decide where to look"),
        ("compare", "Compare", "Two images in, difference out"),
        ("measure", "Measure", "Image + region in, numbers out"),
        ("adc", "ADC", "Numbers in, score and bin out"),
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

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search cards…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Filter the card library by name or description")
        self.search.textChanged.connect(self._on_search)
        wrap = QWidget(self.panel)
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(6, 6, 8, 4)
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
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 8)
            box.setSpacing(1)
            self._body.addLayout(box)
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
                item = _LibraryItem(d, colour, self._host)
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
        self._threshold: Optional[float] = None
        self._bin_text = ""
        self._dragging = False
        self._hover_bin = -1
        # 點擊 vs 拖曳的判定用（見 class docstring）
        self._press_x: Optional[float] = None
        self._press_threshold: Optional[float] = None
        self._press_on_handle = False
        self._moved = False

    # -- public API --------------------------------------------------------
    def set_data(self, edges: Sequence[float], counts: Sequence[int]) -> None:
        """``edges`` / ``counts`` 直接吃 ``viewmodel.histogram()`` 的回傳值。"""
        edges = [float(e) for e in (edges or [])]
        counts = [int(c) for c in (counts or [])]
        if len(edges) != len(counts) + 1 or not counts:
            edges, counts = [], []
        self._edges, self._counts = edges, counts
        if self._threshold is not None:
            self._threshold = self._clamp(self._threshold)
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
            p.drawText(self.rect(), Qt.AlignCenter, self._EMPTY_TEXT)
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
            p.setBrush(hover if i == self._hover_bin else bar)
            p.drawRect(QRectF(x + 0.5, r.bottom() - bh, max(1.0, bw - 1.0), bh))

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
    """數值 -> 好讀字串：整數不拖小數點、一般值 3 位、極小值退回有效位數。"""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "∞" if f > 0 else "-∞"
    if f == int(f) and abs(f) < 1e12:
        return str(int(f))
    if 0 < abs(f) < 5e-4:
        return "%.3g" % f
    return "%.3f" % f


class FeatureTable(QTableWidget):
    """特徵 / 數值 兩欄表；``score`` 永遠釘在最後一列且用粗體。"""

    _SCORE = "score"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Feature", "Value"])
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        head = self.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)

    def set_features(self, features: Optional[Dict[str, Any]],
                     highlight: Iterable[str] = ()) -> None:
        """填表。``highlight`` 內的特徵名會用 accent 底色標出（例：分數用到的）。"""
        features = dict(features or {})
        hi = set(highlight or ())
        names = [k for k in features if k != self._SCORE]
        if self._SCORE in features:
            names.append(self._SCORE)

        self.setRowCount(len(names))
        for row, name in enumerate(names):
            is_score = name == self._SCORE
            key_item = QTableWidgetItem(str(name))
            val_item = QTableWidgetItem(_fmt_number(features[name]))
            val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if is_score:
                font = key_item.font()
                font.setBold(True)
                key_item.setFont(font)
                val_item.setFont(font)
                key_item.setForeground(QColor(TOKENS["accent_active"]))
                val_item.setForeground(QColor(TOKENS["accent_active"]))
            if name in hi:
                bg = QColor(TOKENS["accent_bg"])
                key_item.setBackground(bg)
                val_item.setBackground(bg)
            self.setItem(row, 0, key_item)
            self.setItem(row, 1, val_item)

    def feature_names(self) -> List[str]:
        return [self.item(r, 0).text() for r in range(self.rowCount())
                if self.item(r, 0) is not None]

    def value_text(self, name: str) -> Optional[str]:
        for r in range(self.rowCount()):
            key = self.item(r, 0)
            if key is not None and key.text() == name:
                val = self.item(r, 1)
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
