# d4t Studio — 設定區裡那一格「這條線接的是什麼」（F68，2026-09-01）。
"""接線插槽：**設定區的那一格 ＝ 畫布上的那顆埠**。

取代 `widgets._wiring_display`（一個唯讀的 ``QLineEdit``）。使用者
2026-09-01：「UI 會讓人看不懂，不管是上方畫布設定跟下方的卡片詳細設定
（**尤其是下方**）」。量得出來的三件事：

1. 那一格是**唯讀的 QLineEdit，而且沒有任何專屬樣式**（`#wiringDisplay` 在
   `theme.py` 一條規則都沒有）——套的是通用輸入框樣式，點下去還會亮 focus
   框。**看起來就是可以打字**，而打不進去。
2. 沒接線時只有一句 placeholder，**沒說接了會怎樣、不接又會怎樣**。
3. F67 之後一張 GLV 卡上有**四格**這種東西（`Measure on` / `Region` /
   `Ref region` / `Ref image`），前兩格灰的、後兩格灰的而且是空的。

這一格因此長成三段，每一段修掉上面一條：

* **左邊一個符號**，跟畫布上那顆埠**同形狀同色**（圓＝影像流、菱形＝區域；
  空心＝參照那一顆）。「這一格就是那顆埠」不必讀字就看得出來。
* **中間講現在接的是什麼，而且沒接線不是空白**——講後果（``the whole
  image`` / ``no reference — absolute numbers only`` / 紅字 ``not connected``）。
* **右邊一顆按鈕**：列出上游真的產得出來的東西，選了就建那條線。

> **線仍然是唯一的儲存。** 這一格不記任何東西，選了之後發一個訊號，由
> `StudioWindow` 走**跟畫布拉線完全同一條路**（`_connect_region` /
> `_on_edge_added`）——所以 undo、`rename_fallout`、健檢全部原樣繼承。
> 這只反轉 F12 §2「改要回畫布上拉線」那半句，而它有先例：F10-7 就是因為
> 同一條規則擋住真實需求（`Write result to` 改不了名）而被縮小過一次。

樣板抄的是既有的 `TemplateField` / `CellRoisField`（按鈕 ＋ 從值解出來的
摘要 ＋ 空值紅字）——repo 裡唯一「唯讀狀態＋行動入口同一格」的形狀，
所以這裡沒有發明新機制。
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMenu, QPushButton,
                               QSizePolicy, QWidget)

from .theme import TOKENS, group_hex
from .region_words import PORT_HOVER, role_of

__all__ = ["WiringSlot", "slot_words", "PortDot"]

#: 這一格在講哪一種埠。跟畫布的 `canvas._draw_port` 是同一組概念，
#: 而**形狀與顏色也要一樣** —— 兩邊各畫各的話，「這一格＝那顆埠」就沒了。
IMAGE, REGION = "image", "region"


def slot_words(kind: str, value: str, *, is_reference: bool,
               required: bool) -> tuple:
    """這一格中間要寫什麼 → ``(主要那句, 灰字補充, 是不是紅字)``。

    **沒接線不是空白，是講後果** —— 三種空狀態講的是三件不同的事：

    ===========================  =============================================
    量測用的埠、而且非接不可     ``not connected`` （紅字：這張卡跑不起來）
    量測區域沒接                 ``the whole image``（合法，而且是預設行為）
    參照沒接                     ``no reference`` （合法：只報絕對值）
    ===========================  =============================================

    接了線的時候，區域那一格會補一句**角色**（``the defect's box`` /
    ``the other boxes = the reference``）—— 字典是 `region_words.PORT_HOVER`，
    跟畫布上那顆埠的 hover **同一份**（F44 建的；兩份會在兩個畫面上長出兩種
    說法）。
    """
    text = str(value or "").strip()
    if text:
        note = ""
        if kind == REGION:
            names = [n.strip() for n in text.split(",") if n.strip()]
            if len(names) == 1:
                note = PORT_HOVER.get(role_of(names[0]), "")
            elif len(names) > 1:
                note = "measured one by one, each with its own prefix"
        return text.replace(",", ", "), note, False
    if required:
        return "not connected", "this card cannot run yet", True
    if is_reference:
        return ("no reference", "absolute numbers only", False)
    if kind == REGION:
        return "the whole image", "no region wired in", False
    return "nothing wired in", "", False


class PortDot(QWidget):
    """畫布上那顆埠，畫在設定區裡。**同形狀、同色**（圓／菱形、實心／空心）。"""

    def __init__(self, kind: str, is_reference: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._kind = str(kind)
        self._ref = bool(is_reference)
        self.setFixedSize(16, 16)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def paintEvent(self, e) -> None:            # noqa: D102 - Qt hook
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(group_hex("region") if self._kind == REGION
                     else TOKENS["canvas_edge"])
        c = QPointF(self.width() / 2.0, self.height() / 2.0)
        r = 5.5 if self._kind == REGION else 5.0
        pen = QPen(col, 1.4)
        if self._ref:
            # 參照那一顆畫**虛線邊**（跟區域線的虛線同一個語彙）—— 畫布上
            # 用同一招把兩顆菱形分開，兩邊要一致。
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QBrush(Qt.NoBrush))
        if self._kind == REGION:
            path = QPainterPath()
            path.moveTo(c.x(), c.y() - r)
            path.lineTo(c.x() + r, c.y())
            path.lineTo(c.x(), c.y() + r)
            path.lineTo(c.x() - r, c.y())
            path.closeSubpath()
            p.drawPath(path)
        else:
            p.drawEllipse(c, r, r)
        p.end()


class WiringSlot(QWidget):
    """一格接線：符號 ＋ 現在接的是什麼 ＋ 一顆「換」。

    ``wire_requested(name)``：使用者從選單挑了一個上游的區域／影像流。
    ``show_requested()``：使用者要求「在畫布上指給我看」。
    兩個訊號都**不改任何東西** —— 動線的是 `StudioWindow`。
    """

    wire_requested = Signal(str)
    show_requested = Signal()

    def __init__(self, kind: str, value: str = "", *,
                 is_reference: bool = False, required: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._kind = str(kind)
        self._ref = bool(is_reference)
        self._required = bool(required)
        self._value = str(value or "")
        self._choices: List[str] = []

        self.setObjectName("wiringSlot")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 4, 3)
        lay.setSpacing(7)

        self.dot = PortDot(self._kind, is_reference, self)
        lay.addWidget(self.dot, 0, Qt.AlignVCenter)

        self.text = QLabel("", self)
        self.text.setObjectName("wiringValue")
        lay.addWidget(self.text, 0, Qt.AlignVCenter)

        self.note = QLabel("", self)
        self.note.setObjectName("paramHint")
        lay.addWidget(self.note, 1, Qt.AlignVCenter)

        self.button = QPushButton("", self)
        self.button.setProperty("variant", "secondary")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self._open_menu)
        lay.addWidget(self.button, 0, Qt.AlignVCenter)

        self.set_text(self._value)

    # -- 值 ----------------------------------------------------------------
    def text_value(self) -> str:
        return self._value

    def set_text(self, value: str) -> None:
        self._value = str(value or "")
        main, note, bad = slot_words(self._kind, self._value,
                                     is_reference=self._ref,
                                     required=self._required)
        self.text.setText(main)
        self.text.setStyleSheet(
            "font-size:12px;%s"
            % (" color:%s; font-weight:600;" % TOKENS["danger_text"] if bad
               else (" color:%s;" % TOKENS["text_hint"] if not self._value
                     else " color:%s; font-weight:600;" % TOKENS["text_primary"])))
        self.note.setText(("· " + note) if note else "")
        self.button.setText("Change ▾" if self._value else "Connect ▾")
        what = "region" if self._kind == REGION else "image stream"
        self.setToolTip(
            "Which %s this card works on. Pick one here, or drag a line on "
            "the canvas - both do the same thing, and the line is what gets "
            "saved." % what)

    def set_choices(self, names: Sequence[str]) -> None:
        """選單裡有哪些 —— **上游真的產得出來的那些**（由 Studio 給）。"""
        self._choices = [str(n) for n in names if str(n).strip()]

    # -- 選單 ---------------------------------------------------------------
    def _open_menu(self) -> None:
        menu = QMenu(self)
        if self._choices:
            for name in self._choices:
                act = menu.addAction(name)
                act.setCheckable(True)
                act.setChecked(name == self._value)
                act.triggered.connect(
                    lambda _c=False, n=name: self.wire_requested.emit(n))
        else:
            # **空的要講出為什麼**（同 ParamForm 的 `_EMPTY_HINTS`）——
            # 一個什麼都沒有的選單讀起來像壞掉。
            act = menu.addAction(
                "nothing upstream produces a %s yet"
                % ("region" if self._kind == REGION else "stream"))
            act.setEnabled(False)
        if self._value:
            menu.addSeparator()
            menu.addAction("Show it on the canvas").triggered.connect(
                lambda _c=False: self.show_requested.emit())
        menu.exec(self.button.mapToGlobal(self.button.rect().bottomLeft()))
