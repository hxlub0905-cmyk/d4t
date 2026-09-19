# -*- coding: utf-8 -*-
# d4t chart settings dialog — authored 2026-09-07 (F87).
"""PEAR 那個 **Chart settings** 對話框的 d4t 版。

版型：一列一個東西，屬性橫著擺
------------------------------
PEAR 那個對話框的價值有一半在排列方式 —— **「刻度上的數字」是一列，
它的大小／粗體／顏色橫著排在同一列上**。攤成「字級」「粗體」「顏色」
三列的話，讀的人要先在腦裡把它們兜回同一個東西才看得懂。

所以列怎麼分不是這一份決定的，是 `core.pipeline.chart_style.ROWS` ——
那是「這一組設定怎麼分群」，跟畫面用什麼元件無關（同 `decide_tree` 的立場）。
這一份只負責**把那張表變成 widget**。

三條規矩
--------
1. **上下界只有一份** —— 每一格的範圍問 `chart_style.bounds()`，不在這裡抄。
   抄一份的那天，使用者打得進一個滑桿拉不到的值（或反過來）。
2. **顏色的預設是「自動」不是某個色碼** —— 空字串＝跟著區域色走。所以每一
   格顏色是「一顆色塊 ＋ 一顆 ×」：× 才是回到自動的路，而它要**看得見**
   （藏在右鍵裡的功能對不會寫 code 的人等於不存在）。
3. **沒顯示的覆寫要留著** —— 使用者把熱圖取消勾選之後再來調設定，熱圖的
   標題不該被這個對話框安靜地清掉。它們原封不動搬回輸出（`_extra`）。
"""
from __future__ import annotations
from d4t.core.log import swallowed

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.export import uniformity_charts as uc
from ..core.pipeline import chart_spec as cspec
from ..core.pipeline import chart_style as cs
from . import fit_screen, geometry
from .uniformity_window import ChartView, chart_style_for
from .theme import TOKENS, region_hex
from .widgets import ChoiceChips, apply_button_cursors, small_button

__all__ = ["ChartSettingsDialog", "ColourButton"]

#: 只收整數的那幾格（柱子數、刻度數）—— 「24.5 根柱子」沒有意思。
_INT_KEYS = ("bins", "xticks", "yticks")

#: 每一格旁邊那一句（tooltip）。**每一格都要有一句**（鐵則 3 的精神：
#: 這裡不是 ParamSpec，但看的人是同一批）。
_TIPS: Dict[str, str] = {
    "tick_size": "How big the numbers along the axes are.",
    "tick_bold": "Make those numbers bold.",
    "tick_color": "Colour of those numbers. Empty follows the theme.",
    "axis_size": "How big the axis names and the chart frame text are.",
    "axis_bold": "Make the axis names bold.",
    "axis_color": "Colour of the axis names. Empty follows the theme.",
    "point_size": "Radius of the dot drawn for each box.",
    "point_color": "Colour of those dots. Empty follows each region's colour.",
    "line_width": "Thickness of the trend line, the median line and the box "
                  "outlines.",
    "line_color": "Colour of those lines. Empty follows each region's colour.",
    "value_name": "What the value axis is called. Empty uses the metric's "
                  "own name.",
    "bins": "How many bars the histogram is cut into.",
    "xticks": "How many labelled ticks along the bottom.",
    "yticks": "How many labelled ticks up the side.",
    "points": "Draw a dot for every box. Turn it off when there are hundreds "
              "of boxes and they smear together.",
    "whiskers": "Draw the whiskers on the box plot.",
    "percent": "Histogram shows share of boxes instead of a count. Use it "
               "when two regions have very different box counts.",
    "equal_cells": "Draw the heat map as a plain grid - every cell the same "
                   "size, one slot per row and column. That is what a die map "
                   "looks like, and it is what makes two cells comparable at "
                   "a glance. Turn it off to draw each cell true to scale "
                   "(area then follows the spacing, which this chart is not "
                   "measuring). The heat painted on the image is always true "
                   "to scale - it has to line up with the picture.",
    "map_values": "Print the number inside each heat map cell, where the cell "
                  "is wide enough to hold it.",
    "ramp": "Which colour scale is used wherever colour stands for a number - "
            "the heat map's cells and a scatter coloured by a statistic.",
    "yscale": "A log axis when the numbers span decades - sizes, counts. "
              "Zero and negatives have no place on one, so those points are "
              "not drawn and the axis name says how many.",
    "slot_order": "Sort the bars (or boxes) by their value instead of "
                  "leaving them in the axis's own order.",
    "ref_lines": "Spec limits, drawn as dashed lines across the chart. One "
                 "or more numbers separated by commas; give one a name with "
                 "USL=132. They land on the value axis, so the heat map "
                 "does not have them.",
    "lock": "Pin the value scale to the range below, so two runs can be put "
            "side by side. Off means every chart picks its own range - which "
            "is right for one run and misleading for two.",
    "lo": "Bottom of the locked value scale.",
    "hi": "Top of the locked value scale.",
}

#: 每張圖那五格在畫面上的字。
_PER_LABELS: Dict[str, str] = {
    "title": "Title",
    "xlabel": "Bottom axis name",
    "ylabel": "Side axis name",
    "xticks": "Ticks across",
    "yticks": "Ticks up the side",
}

_PER_TIPS: Dict[str, str] = {
    "title": "Line of text above this chart. Empty uses the chart's name.",
    "xlabel": "Name of the bottom axis on this chart.",
    "ylabel": "Name of the side axis on this chart.",
    "xticks": "How many labelled ticks along the bottom of this chart.",
    "yticks": "How many labelled ticks up the side of this chart.",
}


class ColourButton(QWidget):
    """一顆色塊 ＋ 一顆 ×。空字串＝**自動**（跟著區域色／主題走）。"""

    #: 值變了（即時預覽接這個）。
    changed = Signal(str)

    #: 色塊最小寬度 —— 高度是 QSS 的事，這一個是「`auto` 四個字要放得下」。
    SWATCH_W = 58

    def __init__(self, value: str = "", tip: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._value = str(value or "")
        # **尺寸交給 QSS 的 `shape`，不寫在這裡**（F7-23：以前六個呼叫端各自
        # 寫死一組，於是同一種視覺語言沒有兩顆一樣大）。這裡只說寬一點的那顆
        # 至少要放得下 `auto` 那四個字。
        self.swatch = small_button("", tip=tip, shape="wide", parent=self)
        self.swatch.setMinimumWidth(self.SWATCH_W)
        self.swatch.clicked.connect(self._pick)
        self.clear_btn = small_button(
            "\u00d7", tip="Back to the automatic colour", shape="square",
            parent=self)
        self.clear_btn.clicked.connect(lambda: self.set_value(""))
        lay.addWidget(self.swatch, 0)
        lay.addWidget(self.clear_btn, 0)
        lay.addStretch(1)
        self.setMinimumWidth(self.SWATCH_W + 4 + 24)
        self._paint()          # 建構時只畫，不發訊號（還沒有人接）

    def value(self) -> str:
        return self._value

    def set_value(self, text: str) -> None:
        text = str(text or "")
        if text == self._value:
            return
        self._value = text
        self._paint()
        self.changed.emit(self._value)

    #: 兩顆都自己帶底 —— QSS 的 ``ghost`` 是**透明**的，套在這裡的話
    #: 「auto」那一格讀起來像一行字，而它是按得下去的東西（推廣鐵則：
    #: 看不出是按鈕的按鈕等於沒有）。
    _FRAME = "border:1px solid %s;border-radius:4px;" % TOKENS["border_input"]

    def _paint(self) -> None:
        if self._value:
            self.swatch.setText("")
            self.swatch.setStyleSheet("background:%s;%s"
                                      % (self._value, self._FRAME))
        else:
            self.swatch.setText("auto")
            self.swatch.setStyleSheet(
                "background:%s;color:%s;%s"
                % (TOKENS["bg_surface"], TOKENS["text_hint"], self._FRAME))
        self.clear_btn.setEnabled(bool(self._value))
        self.clear_btn.setStyleSheet(
            "background:%s;color:%s;%s"
            % (TOKENS["bg_surface"],
               TOKENS["text_primary"] if self._value
               else TOKENS["text_disabled"], self._FRAME))

    def _pick(self) -> None:
        start = QColor(self._value) if self._value else QColor(region_hex(0))
        got = QColorDialog.getColor(start, self, "Pick a colour")
        if got.isValid():
            self.set_value(got.name())


def _esc(text: str) -> str:
    """QLabel 吃 rich text，所以標題要跳脫（`&` 在名字裡出現過就會吃掉字）。"""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _chips(key: str, parent: Optional[QWidget] = None) -> "BoolChips":
    """`BOOL_CHIPS` 的一列 → 一個 `BoolChips`。"""
    off, on, off_help, on_help = BOOL_CHIPS[str(key)]
    return BoolChips(off, on, _chip_on(key, cs.DEFAULTS[str(key)]),
                     helps={"off": off_help, "on": on_help}, parent=parent)


def _choice(key: str, parent: Optional[QWidget] = None) -> QWidget:
    """`CHOICE_CHIPS` 的一列 → 一排膠囊（三顆以上）。"""
    rows = CHOICE_CHIPS[str(key)]
    return ChoiceChips([r[0] for r in rows], [r[2] for r in rows],
                       str(cs.DEFAULTS[str(key)]),
                       helps={r[0]: r[3] for r in rows},
                       labels={r[0]: r[1] for r in rows}, parent=parent)


def _caption(text: str, parent: QWidget) -> QLabel:
    lab = QLabel(str(text), parent)
    lab.setObjectName("paramHint")
    return lab


def _number(key: str, parent: QWidget) -> QWidget:
    """一格數字 —— 範圍問 `chart_style.bounds()`，不在這裡寫死。"""
    lo, hi = cs.bounds(key) or (0.0, 1.0)
    if key in _INT_KEYS:
        box = QSpinBox(parent)
        box.setRange(int(lo), int(hi))
        box.setValue(int(cs.DEFAULTS[key]))
    else:
        box = QDoubleSpinBox(parent)
        box.setDecimals(1)
        box.setSingleStep(0.5)
        box.setRange(float(lo), float(hi))
        box.setValue(float(cs.DEFAULTS[key]))
    box.setFixedWidth(78)
    if _TIPS.get(key):
        box.setToolTip(_TIPS[key])
    return box


def _num_value(box: QWidget) -> Any:
    v = box.value()
    return int(v) if isinstance(box, QSpinBox) else round(float(v), 4)


class BoolChips(QWidget):
    """一個開關 → **一排兩顆膠囊（圖 + 字）**（F87 第十刀）。

    使用者 2026-09-07：「如果可以也能以膠囊方式呈現(like GLV card)」。

    這是 F68 那條規矩搬進這個對話框：**一格選項＝一排膠囊，不是一個勾選框**。
    理由跟卡片那邊一字不差 —— 勾選框把「另一個選項是什麼」藏起來了：
    `Whiskers` 不打勾會變成什麼樣子？打勾的人心裡要自己補一張圖。攤成兩顆之
    後，兩種答案本身就是畫面，而**圖是掃視時的錨點、字才是意思**。

    值仍然是一個 bool（recipe 那一格一個位元都沒有變）—— 這一支只是把它包成
    `ChoiceChips` 認得的兩個字。
    """

    toggled = Signal(bool)

    def __init__(self, off: Tuple[str, str], on: Tuple[str, str],
                 value: bool = False, helps: Optional[Dict[str, str]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        from .widgets import ChoiceChips

        self._off_word, self._on_word = str(off[0]), str(on[0])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        said = dict(helps or {})
        self.chips = ChoiceChips(
            [self._off_word, self._on_word], [str(off[1]), str(on[1])],
            self._on_word if value else self._off_word,
            helps={self._off_word: said.get("off", ""),
                   self._on_word: said.get("on", "")}, parent=self)
        self.chips.changed.connect(self._on_changed)
        lay.addWidget(self.chips)
        lay.addStretch(1)
        # ⚠ **兩顆要排在同一列上。** `_ChipFlow.sizeHint` 講的是「最寬的**那一
        # 顆**」（對一排十幾顆的統計量膠囊是對的：它本來就要換行），而這裡只有
        # 兩顆、而且它們是同一個問題的兩個答案 —— 分成兩行讀起來像兩件事。
        # 所以把兩顆的寬度加起來當下限。
        wide = sum(c.width() for c in
                   (self.chips.chip(self._off_word),
                    self.chips.chip(self._on_word)) if c is not None)
        if wide:
            self.chips.setMinimumWidth(wide + 8)

    # -- 長得像 QCheckBox（對話框其餘部分因此不必分兩種寫法）----------------
    def isChecked(self) -> bool:  # Qt 的命名
        return self.chips.text() == self._on_word

    def setChecked(self, on: bool) -> None:  # Qt 的命名
        # ⚠ **要自己發訊號。** `ChoiceChips.set_text` 是程式設值那一條路，
        # 它刻意不發 `changed`（不然載入一份 recipe 會被當成使用者改了）。
        # 而 `QCheckBox.setChecked` **會**發 `toggled` —— 這一支要長得像
        # QCheckBox，那條差別就得在這裡補平，不然「程式設值不重畫」會變成
        # 「這一格沒有反應」。踩過：即時預覽對每一顆膠囊都沒反應。
        if bool(on) == self.isChecked():
            return
        self.chips.set_text(self._on_word if on else self._off_word)
        self.toggled.emit(bool(on))

    def _on_changed(self, _text: str) -> None:
        self.toggled.emit(self.isChecked())


#: 每一個開關那兩顆膠囊：``鍵: ((關的字, 圖), (開的字, 圖), 關的說明, 開的說明)``。
#:
#: ⚠ **兩顆都要說得出自己是什麼** —— 這一族的價值就在「不打勾會變成什麼樣子」
#: 本來看不見。所以 off 那一顆不是「不要」，是**它自己那個樣子的名字**。
BOOL_CHIPS: Dict[str, Any] = {
    "point_fill": (("Hollow", "mark_hollow"), ("Filled", "mark_solid"),
                   "Rings - overlapping points stay countable.",
                   "Solid dots - easier to see on a projector."),
    "points": (("No marks", "dots_off"), ("A mark per box", "dots_on"),
               "Just the trend line. Use it when there are hundreds of boxes "
               "and the marks smear together.",
               "Draw a mark for every box."),
    "whiskers": (("Box only", "whisk_off"), ("With whiskers", "whisk_on"),
                 "The box alone - the middle half and the median.",
                 "Add the whiskers out to the furthest box within 1.5x the "
                 "spread."),
    "percent": (("Count", "bars_count"), ("Share", "bars_pct"),
                "Bar height is how many boxes fell in that bin.",
                "Bar height is the share of that region's boxes - which is "
                "what makes two regions of different size comparable."),
    "equal_cells": (("True to scale", "cells_true"),
                    ("Same size", "cells_equal"),
                    "Each cell reaches the midline to its neighbours, so its "
                    "area follows the spacing.",
                    "A plain grid, one slot per row and column - what a die "
                    "map looks like, and what makes two cells comparable."),
    "map_values": (("Colour only", "cells_plain"),
                   ("Show the value", "cells_values"),
                   "Just the colours.",
                   "Print the number inside each cell that is wide enough to "
                   "hold it."),
    "lock": (("Auto", "range_auto"), ("Locked", "range_locked"),
             "Every chart picks its own range - right for one run.",
             "Pin the scale to the range below, so two runs can be read side "
             "by side."),
    "yscale": (("Plain", "scale_linear"), ("Log", "scale_log"),
               "Equal steps up the axis - right when the numbers are all of "
               "a size.",
               "Each step is ten times the last. Use it when the numbers "
               "span decades (sizes, counts) and a plain axis squashes them "
               "all onto one line. Zero and negatives are not drawn - the "
               "axis name says how many were left out."),
    "ramp": (("One colour", "ramp_mono"), ("Rainbow", "ramp_rainbow"),
             "Light to dark in one colour - the order reads straight off the "
             "page, and it survives being printed in grey.",
             "Blue through red. Easier to name a cell by its colour, but the "
             "steps between the colours are not equal, so a rainbow invents "
             "edges that are not in the numbers."),
}

#: `BOOL_CHIPS` 裡**值不是 bool** 的那幾格：``鍵 -> (關的值, 開的值)``。
#: 沒列的就是 ``(False, True)``。
#:
#: ⚠ **為什麼不給它自己一張表**：那一格的長相、說明、圖示與那七格一字不差，
#: 差別只有「這個開關對應到哪兩個值」。多開一張表就是多開一個家，而
#: `test_every_setting_has_a_home_on_the_page` 守的正是「一格設定只有一個家」。
CHIP_VALUES: Dict[str, Tuple[Any, Any]] = {"ramp": ("", "rainbow"),
                                           "yscale": ("", "log")}

#: 三顆以上的那幾格（`BoolChips` 只裝得下兩顆）：
#: ``鍵 -> ((值, 字, 圖示, 一句話), …)``。
#:
#: ⚠ 為什麼不做成下拉：同 F68 那條規矩 —— 一格選項是一排膠囊。三顆還在
#: 「攤開比藏起來好」的範圍裡（`ChoiceChips` 自己會換行）。
CHOICE_CHIPS: Dict[str, Tuple[Tuple[str, str, str, str], ...]] = {
    "slot_order": (
        ("", "As they come", "sort_none",
         "They keep the order the axis has (region order, column order…)."),
        ("asc", "Low to high", "sort_asc",
         "Shortest bar first."),
        ("desc", "High to low", "sort_desc",
         "Tallest first - “which is worst” becomes the first thing you "
         "see."),
    ),
}


def _chip_on(key: str, value: Any) -> bool:
    """那一格現在的值 → 膠囊是不是在「開」那一顆上。"""
    pair = CHIP_VALUES.get(str(key))
    return str(value) == str(pair[1]) if pair else bool(value)


def _chip_value(key: str, on: bool) -> Any:
    """膠囊 → 那一格要存回去的值。"""
    pair = CHIP_VALUES.get(str(key))
    return pair[1 if on else 0] if pair else bool(on)


def _sample_notes() -> List[Dict[str, Any]]:
    """預覽用的樣本 —— **兩個區域、有斜率、有一顆離群**。

    為什麼不是隨便一組數字：這幾格設定要調的東西各自需要不同的東西才看得出
    來 —— 顏色要**兩群**、`slope` 那條線要有斜度、盒鬚的鬚要有離群點、
    直方圖的柱數要有足夠的框。一組平的資料會讓半數設定「看起來沒反應」。

    ⚠ **格子數要少**：預覽只有 380×210，12 欄的話一格只剩 20 px —— 那個
    尺寸下什麼都看不出來，而「每一格裡印出值」那一格會**看起來沒反應**
    （它有一條「放不下就不印」的規矩，印一半的數字比不印糟）。
    3×3 兩群 = 6 欄，一格約 40 px，剛好放得下一個數字。

    ⚠ **兩個統計量，不是一個**：散佈圖的兩條軸是兩個不同的欄，而拿同一欄
    畫兩次得到的是一條 45° 直線 —— 那張預覽看起來像壞了。
    """
    notes: List[Dict[str, Any]] = []
    for k, (name, base, x0) in enumerate(
            (("region A", 112.0, 40), ("region B", 124.0, 340))):
        n = 9
        vals = [base + 1.4 * (i % 3) + 2.6 * (i // 3) for i in range(n)]
        vals[4] += 6.0 if k == 0 else -5.0          # 一顆離群，鬚才看得出來
        # 跟 `value` 有關係但不是它的一份（散佈圖才有東西可讀）。
        spread = [2.0 + 0.35 * (v - base) + (0.8 if i % 2 else -0.4)
                  for i, v in enumerate(vals)]
        notes.append({"region": name, "prefix": name, "spread": {
            "stats": {"value": vals, "spread": spread},
            "cx": [float(x0 + 80 * (i % 3)) for i in range(n)],
            "cy": [float(40 + 80 * (i // 3)) for i in range(n)],
            "rects": [[x0 + 80 * (i % 3), 40 + 80 * (i // 3), 56, 56]
                      for i in range(n)],
            "boxes": list(range(n))}})
    return notes


def _sample_series() -> Dict[str, Any]:
    """樣本的 series（四張老圖吃這一份）。"""
    from ..core.export import uniformity_charts as uc

    return uc.chart_series(_sample_notes(), "value")


#: 樣本資料上的散佈圖畫哪兩欄。**樣本一定要畫得出東西** —— 一個永遠停在
#: 「pick x and y」的分頁，使用者調的每一格看起來都沒有反應（真的踩過：
#: `Title` 那一格在那張分頁上完全沒有效果，因為那張圖根本沒在畫）。
SAMPLE_SPEC = '{"color":"region","mark":"point","x":"value","y":"spread"}'


def _sample_frame() -> Any:
    """樣本的長表（散佈圖吃這一份）—— **跟 series 同一組 notes**。

    各造一份的話，同一個預覽區裡兩張圖畫的是兩批不同的資料，而那正是這整個
    功能最貴的那種 bug 的縮小版。
    """
    from ..core.export import chart_frame

    return chart_frame.build_frame(_sample_notes())


class ChartSettingsDialog(QDialog):
    """改 `chart_style` 那一格。``value()`` 回**格式化過的字串**。

    模態 —— 這裡沒有「一邊拉一邊看」（曲線編輯器那個理由不成立：這些是
    離散的設定，不是拖出來的形狀），而套用之後彈出視窗會當場重畫。
    """

    #: 每一張預覽至少多高（再矮就只剩一團色塊）。
    PREVIEW_H = 210
    #: 預覽的長寬比（寬 ÷ 高）—— 見 `ChartView.ASPECT`。
    PREVIEW_ASPECT = 4.0 / 3.0

    def __init__(self, look: str = "", kinds: Optional[Sequence[str]] = None,
                 parent: Optional[QWidget] = None,
                 series: Optional[Dict[str, Any]] = None,
                 axis: str = uc.AXIS_X, words: bool = True,
                 frame: Any = None, spec: str = ""):
        super().__init__(parent)
        #: 右半要不要「每張圖自己的字」（`Step.chart_words`）。一次畫好幾張
        #: 同一種圖的卡片（`Write report`）沒有那件事 —— 一組標題套到五張上
        #: 等於什麼都沒說。
        self._words = bool(words)
        #: profile 沿哪一個軸（只影響那一張）—— 卡片上那一格說了算。
        self._axis = str(axis or uc.AXIS_X)
        #: 預覽吃的那一顆。沒給就用內建的樣本 —— 一個**空**的預覽區讀起來是
        #: 「壞了」，而使用者調的是外觀，樣本足以看出每一格的效果。
        #: 是不是樣本會寫在預覽上方（不然他會以為那是自己的資料）。
        self._series = dict(series or {})
        self._is_sample = not (self._series.get("groups") or [])
        if self._is_sample:
            self._series = _sample_series()
        #: 散佈圖那一張的預覽要的兩份（長表 ＋ 角色配置）。沒有的時候
        #: 那一格畫出來是一句說得出原因的話，不是一張空白（`chart_draw`）。
        if frame is not None:
            self._frame = frame
            self._spec = str(spec or "")
        else:
            # 樣本自己配一份角色 —— 見 `SAMPLE_SPEC`。⚠ 只在**沒有資料**的
            # 時候：有資料而還沒挑欄的人要看到那句「pick x and y」，不是一張
            # 畫著別的欄的圖。
            self._frame = _sample_frame()
            self._spec = str(spec or "") or SAMPLE_SPEC
        self._live = True
        self.setWindowTitle("Chart settings")
        self.setModal(True)
        # ⚠ **高度要裝得下左半那三塊**（量出來 809）。以前是 680，於是對話框
        # 一打開就有捲軸，而捲軸底下正好是那幾格膠囊 —— 使用者要先發現有東西
        # 在下面才找得到它們。
        fit_screen.fit(self, 1180, 940)
        geometry.restore(self, "chart_settings")      # F117 I16

        self._kinds: List[str] = [k for k in (kinds if kinds is not None
                                              else uc.CHARTS) if k in uc.CHARTS]
        try:
            style = cs.parse_style(look)
        except cs.ChartStyleError:
            style = {}
        # 沒顯示在這個對話框上的每張圖覆寫（見檔頭第 3 條）——原封不動帶回去。
        self._extra = {k: v for k, v in style.items()
                       if "." in str(k) and str(k).split(".", 1)[0]
                       not in self._kinds}

        self.globals: Dict[str, QWidget] = {}
        self.per: Dict[str, Dict[str, QWidget]] = {}
        self.views: Dict[str, ChartView] = {}
        #: 每一格旁邊那個標題（藏一列要連它一起藏）。
        self._labels: Dict[str, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        what = ("How this chart looks" if len(self._kinds) == 1
                else "How these %d charts look" % len(self._kinds))
        head = QLabel(
            "%s. Everything here travels with the recipe, so the next run - "
            "and anyone you hand the recipe to - gets the same charts."
            % what, self)
        head.setWordWrap(True)
        head.setObjectName("paramHint")
        root.addWidget(head)

        # **兩欄。** 一欄疊下來的話「每張圖自己的字」整段落在摺線底下 ——
        # 而那正是使用者指名要的那一段（標題、軸名）。左邊是「四張圖共用的
        # 長相」，右邊是「這一張自己的字」，兩句話各佔一欄。
        body = QWidget(self)
        inner = QHBoxLayout(body)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(12)

        # ⚠ **只有左半捲。** 以前整個 body 在一個 `QScrollArea` 裡，於是拉一
        # 個滑桿要往下捲，而捲下去圖就出畫面了 —— 那正好毀掉即時預覽存在的
        # 理由（使用者 2026-09-08 回報的第二件）。設定捲動，圖不動。
        panel = QWidget(body)
        left = QVBoxLayout(panel)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)
        left.addWidget(self._look_group(panel))
        left.addWidget(self._numbers_group(panel))
        left.addWidget(self._scale_group(panel))
        left.addStretch(1)
        scroll = QScrollArea(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(panel)
        # ⚠ **左半不准橫著捲。** 一列一個設定的欄位被擠窄的話，最右邊那顆
        # 回到 auto 的 `×` 就切掉了 —— 而那是唯一一條回到「跟著區域色走」的
        # 路（`ColourButton` 的說明）。寬度不夠就讓對話框長，不要切內容。
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(panel.sizeHint().width()
                               + scroll.verticalScrollBar().sizeHint().width()
                               + 4)
        # ⚠ **右半要比左半寬。** 左半是「一列一個設定」，寬度由標籤與數字框
        # 決定，多給它的空間全是空白；右半那一格是**圖**，而圖是這個對話框
        # 真正要看的東西。第一版反過來（3:2），於是預覽只有 394 px 寬。
        inner.addWidget(scroll, 2)
        right = self._per_chart_group(body)
        # 分頁列擠到要出捲動箭頭的話，第四張圖（Heat map）就藏起來了 ——
        # 一張看不到的分頁等於那張圖的標題改不了。
        right.setMinimumWidth(430)
        inner.addWidget(right, 3)

        root.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        reset = QPushButton("Reset to defaults", self)
        reset.setToolTip("Put every setting on this page back to the way it "
                         "started. Nothing is written until you press OK.")
        reset.clicked.connect(self.reset)
        buttons.addButton(reset, QDialogButtonBox.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.set_value(style)
        self._hide_rows_that_do_not_apply()
        self._connect_live()
        self.refresh_preview()
        apply_button_cursors(self)

    def done(self, result: int) -> None:   # Qt hook
        """關掉時記住大小（F117 I16）。

        ⚠ **`done` 而不是 `closeEvent`**：`accept` / `reject` 兩條路都走這
        裡，而按 Esc 關掉的對話框不一定收得到 `closeEvent`。掛錯地方的症狀
        是「用滑鼠關掉會記得，按 Esc 關掉不會」—— 那種不一致使用者只會覺得
        它壞了。
        """
        geometry.remember(self, "chart_settings")
        super().done(int(result))

    def _hide_rows_that_do_not_apply(self) -> None:
        """只畫盒鬚圖的卡片不必看到「直方圖切幾根柱」（`GLOBAL_APPLIES`）。

        ⚠ **收起來不等於清掉**：那幾格仍然在 `self.globals` 裡，所以值照樣
        round-trip 回去 —— 把 Heat map 取消勾選再勾回來，設定要還在。
        """
        try:
            mark = str(cspec.parse_spec(self._spec)["mark"])
        except Exception:  # 顯示用，不能擋畫面
            mark = cspec.MARK_POINT
        for key in list(self.globals):
            # ⚠ 走 `uc.applies` 而不是自己讀 `GLOBAL_APPLIES` —— `CHART_CUSTOM`
            # 那一張還要看它**現在畫成哪一種記號**（散點沒有鬚）。各讀一份
            # 的那天，收起來的與真的沒有作用的會是兩組不一樣的東西。
            if not any(uc.applies(key, k, mark) for k in self._kinds):
                self._set_row_visible(key, False)

    def _set_row_visible(self, key: str, on: bool) -> None:
        w = self.globals.get(key)
        if w is None:
            return
        w.setVisible(bool(on))
        lab = self._labels.get(key)
        if lab is not None:
            lab.setVisible(bool(on))

    # -- 即時預覽 -----------------------------------------------------------
    def _connect_live(self) -> None:
        """每一格改動 → 重畫預覽。

        ⚠ **逐個型別接**，不要用一支泛用的 ``QWidget.changed`` —— Qt 沒有那個
        東西，而漏接一種的下場是那一格「調了沒反應」，比沒有預覽更糟
        （使用者會以為那個設定壞了）。有一條測試逐格檢查每一個 widget 都接上
        了（`test_every_editor_moves_the_preview`）。
        """
        for w in list(self.globals.values()) + [
                e for f in self.per.values() for e in f.values()]:
            if isinstance(w, ColourButton):
                w.changed.connect(self.refresh_preview)
            elif isinstance(w, (QCheckBox, BoolChips)):
                w.toggled.connect(self.refresh_preview)
            elif isinstance(w, ChoiceChips):
                w.changed.connect(self.refresh_preview)
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(self.refresh_preview)
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.valueChanged.connect(self.refresh_preview)

    def set_series(self, series: Optional[Dict[str, Any]]) -> None:
        """換一份預覽資料（`Chart look` 那一列由 Studio 餵這一顆的）。"""
        got = dict(series or {})
        self._is_sample = not (got.get("groups") or [])
        self._series = _sample_series() if self._is_sample else got
        self.refresh_preview()

    def refresh_preview(self, *_a) -> None:
        """把現在畫面上的設定畫成圖。**壞值不准擋路** —— 使用者正在打字，
        中途一定會經過打不完的狀態。"""
        if not self._live or not self.views:
            return
        try:
            style = self.value()
        except Exception:  # 見 docstring
            swallowed("chart_settings.refresh_preview")
            return
        metric = str(self._series.get("metric") or "")
        for kind, view in self.views.items():
            try:
                # **跟寫出去的走同一支**（`chart_style_for`）。直接叫
                # `chart_style.style_for` 的那一版少了卡片那一半，於是
                # `Name of the value axis` 那一格在預覽上完全沒有反應。
                view.set_data(self._series,
                              chart_style_for(style, kind, self._axis, metric),
                              frame=self._frame, spec=self._spec)
            except Exception:  # 鐵則 7 的 UI 版
                swallowed("chart_settings.refresh_preview")
                continue

    # -- 版型 ---------------------------------------------------------------
    def _section(self, title: str, parent: QWidget) -> QFrame:
        box = QFrame(parent)
        box.setObjectName("card")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        lab = QLabel(str(title), box)
        lab.setObjectName("inspectorHeader")
        lay.addWidget(lab)
        return box

    def _look_group(self, parent: QWidget) -> QFrame:
        """`chart_style.ROWS` → 一列一個東西，屬性橫著擺。"""
        box = self._section("Text, dots and lines", parent)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        # **同一種東西要在同一欄**：`Data points` 只有兩格，而它的「colour」
        # 若跟著往左靠，就會落在上面兩列的「bold」底下 —— 四列讀起來像四種
        # 不同的表。所以顏色固定在最後一欄，其餘的由左往右填。
        slots = max(len(props) for _t, props in cs.ROWS)
        for r, (title, props) in enumerate(cs.ROWS):
            name = QLabel(str(title), box)
            name.setMinimumWidth(96)
            grid.addWidget(name, r, 0)
            left = 0
            for key, column in props:
                if key.endswith("_color"):
                    i = slots - 1
                else:
                    i = left
                    left += 1
                grid.addWidget(_caption(column, box), r, 1 + i * 2)
                if key.endswith("_color"):
                    w = ColourButton(cs.DEFAULTS[key], _TIPS.get(key, ""), box)
                elif key in cs.DEFAULTS and isinstance(cs.DEFAULTS[key], bool):
                    w = QCheckBox("", box)
                    w.setToolTip(_TIPS.get(key, ""))
                else:
                    w = _number(key, box)
                self.globals[key] = w
                grid.addWidget(w, r, 2 + i * 2)
        grid.setColumnStretch(1 + slots * 2, 1)
        box.layout().addLayout(grid)
        return box

    def _row(self, grid: QGridLayout, r: int, key: str, title: str,
             owner: QWidget, editor: QWidget) -> None:
        lab = QLabel(self._row_title(key, title), owner)
        lab.setMinimumWidth(160)
        lab.setWordWrap(True)
        if _TIPS.get(key):
            lab.setToolTip(_TIPS[key])
            editor.setToolTip(_TIPS[key])
        grid.addWidget(lab, r, 0)
        grid.addWidget(editor, r, 1)
        grid.setColumnStretch(2, 1)
        self.globals[key] = editor
        self._labels[key] = lab

    def _reaches(self, key: str) -> List[str]:
        """這一格改得到畫面上哪幾張圖（`uc.applies` 是唯一的判準）。"""
        try:
            mark = str(cspec.parse_spec(self._spec)["mark"])
        except Exception:  # 顯示用，不能擋畫面
            mark = cspec.MARK_POINT
        return [k for k in self._kinds if uc.applies(key, k, mark)]

    def _row_title(self, key: str, title: str) -> str:
        """標題 ＋ **這一格影響哪幾張圖**（影響全部就不加）。

        使用者 2026-09-07：「不同 chart 可設定的應該要不一樣?」

        左半這幾格名義上是「共用的」，但**共用不等於每一張都吃得到** ——
        `Histogram bars` 只有直方圖用得到、`Markers` 只有 profile。
        `GLOBAL_APPLIES` 本來就知道這件事（不適用的整列收起來），但四張圖都
        勾著的時候每一列都在，而畫面上沒有說哪一列管哪一張 —— 於是使用者在
        Box plot 分頁上看著「Histogram bar height」，只能自己猜。

        只有**一張圖**在畫面上的時候不加：那時候每一列都是那張圖的。
        """
        if len(self._kinds) <= 1:
            return str(title)
        mine = [uc.CHART_LABELS.get(k, k) for k in self._reaches(key)]
        if len(mine) >= len(self._kinds):
            return str(title)          # 這一格四張都吃得到
        # **標題已經說了就不要再說一次**：`Heat map cells` 底下再掛一行
        # `Heat map` 是噪音，而噪音會讓真正需要那行的幾列（`Markers`、
        # `Ticks across`）也被跳過不讀。
        low = str(title).lower()
        mine = [m for m in mine if m.lower() not in low]
        if not mine:
            return str(title)
        # 尾巴要**看得出是註解不是標題** —— 同一個字級同一個顏色的話，
        # 「Box plot / Box plot」讀起來像兩行標題（第一版就是那樣）。
        return ("%s<br><span style='color:%s;font-size:11px'>%s</span>"
                % (_esc(str(title)), TOKENS["text_hint"], _esc(" · ".join(mine))))

    def _numbers_group(self, parent: QWidget) -> QFrame:
        box = self._section("What is drawn", parent)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        name = QLineEdit(box)
        name.setPlaceholderText("the metric's own name")
        self._row(grid, 0, "value_name", "Name of the value axis", box, name)
        self._row(grid, 1, "bins", "Histogram bars", box, _number("bins", box))
        self._row(grid, 2, "xticks", "Ticks across",
                  box, _number("xticks", box))
        self._row(grid, 3, "yticks", "Ticks up the side",
                  box, _number("yticks", box))
        # **一排膠囊，不是一個勾選框**（見 `BoolChips`）。
        self._row(grid, 4, "point_fill", "Markers", box, _chips("point_fill"))
        self._row(grid, 5, "points", "Marks on the profile",
                  box, _chips("points"))
        self._row(grid, 6, "whiskers", "Box plot", box, _chips("whiskers"))
        self._row(grid, 7, "percent", "Histogram bar height",
                  box, _chips("percent"))
        self._row(grid, 8, "equal_cells", "Heat map cells",
                  box, _chips("equal_cells"))
        self._row(grid, 9, "map_values", "Heat map labels",
                  box, _chips("map_values"))
        self._row(grid, 10, "ramp", "When colour means a number",
                  box, _chips("ramp"))
        refs = QLineEdit(box)
        refs.setPlaceholderText("none - e.g. USL=132, LSL=112")
        self._row(grid, 11, "ref_lines", "Spec limits", box, refs)
        self._row(grid, 12, "yscale", "The value axis", box, _chips("yscale"))
        self._row(grid, 13, "slot_order", "Bar and box order",
                  box, _choice("slot_order"))
        box.layout().addLayout(grid)
        return box

    def _scale_group(self, parent: QWidget) -> QFrame:
        box = self._section("Value scale", parent)
        why = QLabel(
            "Leave this off for one run. Turn it on when two runs have to be "
            "read side by side - otherwise each chart picks its own range and "
            "two bars of the same height mean different things.", box)
        why.setWordWrap(True)
        why.setObjectName("paramHint")
        box.layout().addWidget(why)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        lock = _chips("lock")
        self._row(grid, 0, "lock", "How the range is picked", box, lock)
        self._row(grid, 1, "lo", "Bottom", box, _number("lo", box))
        self._row(grid, 2, "hi", "Top", box, _number("hi", box))
        for key in ("lo", "hi"):
            self.globals[key].setDecimals(3)
            self.globals[key].setSingleStep(1.0)
        lock.toggled.connect(self._sync_lock)
        box.layout().addLayout(grid)
        return box

    def _sync_lock(self, on: bool) -> None:
        for key in ("lo", "hi"):
            self.globals[key].setEnabled(bool(on))

    def _per_chart_group(self, parent: QWidget) -> QWidget:
        box = self._section("Each chart's own words" if self._words
                            else "Preview", parent)
        if self._is_sample:
            said = QLabel("Previews below use sample data - your run's "
                          "numbers are not loaded here.", box)
            said.setWordWrap(True)
            said.setObjectName("paramHint")
            box.layout().addWidget(said)
        tabs = QTabWidget(box)
        # 四張分頁一定要同時看得見 —— 捲動箭頭後面那一張的標題就改不到了。
        tabs.setUsesScrollButtons(False)
        for kind in self._kinds:
            page = QWidget(tabs)
            grid = QGridLayout(page)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)
            fields: Dict[str, QWidget] = {}
            keys = ([k for k in cs.PER_CHART_KEYS
                     if k in uc.PER_CHART_APPLIES.get(kind, cs.PER_CHART_KEYS)]
                    if self._words else [])
            for r, key in enumerate(keys):
                lab = QLabel(_PER_LABELS.get(key, key), page)
                lab.setMinimumWidth(120)
                lab.setToolTip(_PER_TIPS.get(key, ""))
                if key in ("xticks", "yticks"):
                    lo, hi = cs.bounds(key) or (2.0, 20.0)
                    w = QSpinBox(page)
                    # 最小值 −1 當「沒有覆寫」——  specialValueText 讓那一格
                    # 說出來，而不是留一個看起來像 1 的數字。
                    w.setRange(int(lo) - 1, int(hi))
                    w.setSpecialValueText("same for all")
                    w.setValue(int(lo) - 1)
                    w.setFixedWidth(120)
                else:
                    w = QLineEdit(page)
                    w.setPlaceholderText("the chart decides")
                w.setToolTip(_PER_TIPS.get(key, ""))
                grid.addWidget(lab, r, 0)
                grid.addWidget(w, r, 1)
                fields[key] = w
            grid.setColumnStretch(1, 1)
            # **即時預覽**（使用者 2026-09-07：「Chart setting 我是希望能支援
            # 即時 preview（在編輯器內就可以預覽）」）。放在**這一張圖自己的
            # 分頁裡**：你在改 Box plot 的標題，那張 Box plot 就在正下方。
            # 全域那幾格（字級、顏色、線寬）也會當場反映在這一張上。
            # ⚠ **釘住長寬比**（`ChartView.ASPECT`）。以前這裡只給了一個
            # 最小高度再 `setRowStretch(..., 1)`，於是它吃掉分頁裡所有垂直
            # 空間，被拉成 390 寬 × 655 高的直條 —— 而 SVG 是照那個尺寸產的，
            # 盒鬚圖因此變成一根直條，第二個盒子掉到摺線下面。
            view = ChartView(kind, page, aspect=self.PREVIEW_ASPECT)
            view.setMinimumHeight(self.PREVIEW_H)
            grid.addWidget(view, len(keys), 0, 1, 2)
            # **不給 stretch** —— 高度由寬度決定（`heightForWidth`）。
            grid.setRowStretch(len(keys) + 1, 1)
            self.views[kind] = view
            self.per[kind] = fields
            tabs.addTab(page, uc.CHART_LABELS.get(kind, kind))
        box.layout().addWidget(tabs, 1)
        return box

    # -- 值 -----------------------------------------------------------------
    def set_value(self, style: object) -> None:
        """把一份設定放進畫面上。缺的鍵＝預設（`chart_style.DEFAULTS`）。"""
        d = style if isinstance(style, dict) else cs.parse_style(style)
        # 灌值的時候先關掉預覽：二十幾格各觸發一次，畫面會抖一下，而中途那
        # 幾張畫的是**半套**設定。最後統一畫一次。
        was, self._live = self._live, False
        for key, w in self.globals.items():
            got = d.get(key, cs.DEFAULTS[key])
            if isinstance(w, ColourButton):
                w.set_value(str(got or ""))
            elif isinstance(w, (QCheckBox, BoolChips)):
                w.setChecked(_chip_on(key, got))
            elif isinstance(w, ChoiceChips):
                w.set_text(str(got or ""))
            elif isinstance(w, QLineEdit):
                w.setText(str(got or ""))
            else:
                w.setValue(int(got) if isinstance(w, QSpinBox) else float(got))
        self._sync_lock(bool(self.globals["lock"].isChecked()))
        for kind, fields in self.per.items():
            for key, w in fields.items():
                got = d.get("%s.%s" % (kind, key))
                if isinstance(w, QSpinBox):
                    w.setValue(int(got) if got is not None else w.minimum())
                else:
                    w.setText(str(got or ""))
        self._live = was
        self.refresh_preview()

    def reset(self) -> None:
        """全部回預設 —— **包含收起來的那些覆寫**（按鈕上就是這樣寫的）。"""
        self._extra = {}
        self.set_value({})

    def value(self) -> str:
        """畫面上的東西 → `chart_style` 那一格的字串（只含跟預設不一樣的）。"""
        out: Dict[str, Any] = dict(self._extra)
        for key, w in self.globals.items():
            if isinstance(w, ColourButton):
                out[key] = w.value()
            elif isinstance(w, (QCheckBox, BoolChips)):
                out[key] = _chip_value(key, bool(w.isChecked()))
            elif isinstance(w, (ChoiceChips, QLineEdit)):
                # `ChoiceChips` 的介面就是 `text()` / `set_text()`（它本來就
                # 是 `chip_choice` 那一格的編輯器）—— 所以這兩種走同一支。
                out[key] = w.text().strip()
            else:
                out[key] = _num_value(w)
        for kind, fields in self.per.items():
            for key, w in fields.items():
                if isinstance(w, QSpinBox):
                    if w.value() > w.minimum():
                        out["%s.%s" % (kind, key)] = int(w.value())
                else:
                    text = w.text().strip()
                    if text:
                        out["%s.%s" % (kind, key)] = text
        return cs.format_style(out)
