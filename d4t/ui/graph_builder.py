# -*- coding: utf-8 -*-
# d4t graph builder — authored 2026-09-07 (F88 第二刀).
"""**哪一欄放到哪一個角色上** —— `chart_spec` 那一格的編輯器。

為什麼它是插槽，不是一張圖表清單（計畫書 `docs/history/plans/F88-graph-builder.md` §5）
--------------------------------------------------------------------------
JMP 的 Graph Builder 之所以好用，是因為使用者想的是「我要看 A 跟 B 的關係」，
不是「我要一張散佈圖」。**先挑欄、圖自己長出來**比「先挑圖、再回答它問的
幾個問題」少一步猜測，而那一步正是不會寫 code 的製程工程師卡住的地方。

⚠ **這裡只挑欄，不決定長相。** 字級、線寬、顏色、鎖定範圍全都住在
`chart_style`（`Chart settings…` 那個對話框）。兩份分家的理由跟
`chart_spec` 模組說明上那一段一字不差：**畫什麼**與**長什麼樣**是兩個問題，
而把它們塞進同一個對話框的那天，那個對話框會變成一張沒有人讀得完的表。

⚠ **選單是從資料長出來的**（`Frame.columns`），不是一張寫死的清單。
所以這一份不認得 `glv_median` 這種字 —— 換一個 metric、換一張量測卡，
選單自己會變。寫死一份的那天，使用者的欄位在選單上找不到。

⚠ **預覽跟寫出去的走同一支** `build_chart_svg`（同 `ChartSettingsDialog`）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
    QVBoxLayout, QWidget,
)

from ..core.export import chart_draw
from ..core.export.chart_frame import COLUMNS_FIXED, column_label
from ..core.export import uniformity_charts as uc
from ..core.pipeline import chart_spec as cspec
from . import fit_screen
from .uniformity_window import ChartView, chart_style_for
from .widgets import ChoiceChips, small_button
from . import buttons as buttons_mod

__all__ = ["GraphBuilderDialog", "NONE_WORD", "PICK_WORD", "SpecEditor"]

#: 「空著」那一格顯示的字。**不是空白** —— 一個空的下拉讀起來是「壞了」。
NONE_WORD = "(none)"

#: 非有不可的那幾格**還沒挑**時顯示的字。跟 :data:`NONE_WORD` 是兩件事：
#: 「不用」是一個決定，「還沒挑」不是 —— 而兩個都對應到空字串，所以
#: `missing_roles` 說得出「這張圖還缺什麼」。
#:
#: ⚠ **不要拿第一欄當預設。** 第一版就是那樣：打開對話框，X 與 Y 都自動
#: 落在 `region` 上，於是一張沒有人設定過的圖看起來像設定好了 ——
#: 而它畫出來是一團疊在同一個點上的圓。
PICK_WORD = "(pick one)"

#: 哪幾個角色只吃數字。類別（區域名、第幾列、第幾欄）落在 X 上是有意思的
#: （一排點），落在**大小**上不是 —— 「region B 比 region A 大」沒有意義。
NUMERIC_ONLY = (cspec.ROLE_SIZE,)

#: 每一種記號的圖示（`ui.glyphs`）。**一格選項＝一排膠囊（圖 + 字）**，
#: 不是下拉 —— 這是 F68 那條規矩，而它在這裡尤其站得住腳：三種記號講的正是
#: 「這張圖長什麼形狀」，那本來就畫得出來。
#:
#: ⚠ **盒子與格子借的是既有的兩張圖**（`whisk_on` / `cells_equal`）。它們畫的
#: 正是這兩種記號，而 `ui.glyphs` 是一套**共用的字彙**，不是一張一對一的表 ——
#: 再畫兩張長得幾乎一樣的圖，維護的人以後要猜哪一張才是「真的那個盒子」。
MARK_ICONS = {cspec.MARK_POINT: "mark_dots",
              cspec.MARK_LINE: "mark_line",
              cspec.MARK_BAR: "mark_bars",
              cspec.MARK_BOX: "whisk_on",
              cspec.MARK_CELL: "cells_equal"}


class SpecEditor(QWidget):
    """一排記號 ＋ 四個角色，一列一個下拉。``spec()`` 回**格式化過的字串**。"""

    #: 記號換了 —— 呼叫端要重畫預覽（下拉自己的 `currentTextChanged` 蓋不到
    #: 這一顆，而換記號會改變整張圖的長相）。
    changed = Signal()

    def __init__(self, spec: str = "", columns: Optional[Sequence[str]] = None,
                 parent: Optional[QWidget] = None,
                 numeric: Optional[Sequence[str]] = None,
                 labels: Optional[Dict[str, str]] = None,
                 fixed: Optional[Sequence[str]] = None):
        super().__init__(parent)
        #: 欄名 → 給人看的字。**這一張表自己的**（`Frame.labels`）——
        #: 一列一格框跟一列一顆 defect 是兩套欄名，共用一張表的話，
        #: 跨顆那張圖的 `die_x` 會顯示成它的鍵。
        #:
        #: ⚠ 名字是 `_col_labels` 不是 `_labels` —— 後者已經是「角色那幾個
        #: `QLabel`」了（`_sync_roles` 用它收放列）。撞名的症狀是
        #: `addItem(QLabel, str)`，而那是一句看不懂的 TypeError。
        self._col_labels: Dict[str, str] = dict(
            labels if labels is not None else {})
        #: 哪幾欄是「表自己的欄」（排在使用者量出來的那幾欄後面）。
        self._fixed = tuple(fixed if fixed is not None else COLUMNS_FIXED)
        self._cols = [str(c) for c in (columns or ())]
        # 沒說哪幾欄是數字就當全部都是 —— 少一份資料不該讓選單變空的。
        self._numeric = ([str(c) for c in numeric]
                         if numeric is not None else list(self._cols))
        try:
            got = cspec.parse_spec(spec)
        except cspec.ChartSpecError:
            got = dict(cspec.EMPTY)
        self._mark = str(got.get("mark") or cspec.MARK_POINT)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self.boxes: Dict[str, QComboBox] = {}
        self._labels: Dict[str, QLabel] = {}
        row = 0

        # ⚠ **只有一種記號的時候不問。** 一格答了也沒用的設定比沒有那一格更糟
        # （第二刀就是這樣：那時 `MARKS` 只有 `point`）。
        self.marks: Optional[ChoiceChips] = None
        if len(cspec.MARKS) > 1:
            lab = QLabel("Drawn as", self)
            self.marks = ChoiceChips(
                list(cspec.MARKS),
                [MARK_ICONS.get(m, "mark_dots") for m in cspec.MARKS],
                self._mark, helps=dict(cspec.MARK_HELP),
                labels=dict(cspec.MARK_LABELS), parent=self)
            self.marks.changed.connect(self._on_mark)
            grid.addWidget(lab, row, 0)
            grid.addWidget(self.marks, row, 1)
            row += 1

        for role in cspec.ROLES:
            lab = QLabel(_role_word(role), self)
            lab.setToolTip(cspec.ROLE_HELP[role])
            self._labels[role] = lab
            box = QComboBox(self)
            box.setToolTip(cspec.ROLE_HELP[role])
            for text in self._choices(role):
                # ⚠ **看到的是白話，存回去的是欄名**（`itemData`）。
                # 顯示的字直接當值的話，`Box centre X (px)` 會被寫進 recipe。
                # 那兩個佔位符的值是**空字串** —— 「還沒挑」與「不用」在
                # `chart_spec` 那一側本來就都是空的。
                box.addItem(self._shown(text),
                            "" if text in (NONE_WORD, PICK_WORD) else text)
            want = str(got.get(role) or "")
            box.setCurrentIndex(max(0, box.findData(want) if want else 0))
            self.boxes[role] = box
            grid.addWidget(lab, row, 0)
            grid.addWidget(box, row, 1)
            row += 1
        if not self.boxes:                      # pragma: no cover — 封閉字彙
            grid.addWidget(QLabel("nothing to set up here", self), 0, 0, 1, 2)
        self._grid = grid
        self._sync_roles()

    def _on_mark(self, mark: str) -> None:
        self._mark = str(mark)
        self._sync_roles()
        self.changed.emit()

    def _sync_roles(self) -> None:
        """換了記號 → **用不到的角色收起來**（`chart_spec.USES`）。

        ⚠ 收起來**不等於清掉**：把記號換成折線再換回來，原本挑的「大小」
        還在（同 `ChartSettingsDialog` 那條「沒顯示的覆寫要留著」）。
        欄位留在 widget 上，只是不顯示 —— 而 :meth:`spec` 會問 `uses`，
        所以存出去的那一份不會帶著一個這種記號用不到的角色。
        """
        for role, box in self.boxes.items():
            on = cspec.uses({"mark": self._mark}, role)
            box.setVisible(on)
            lab = self._labels.get(role)
            if lab is not None:
                lab.setVisible(on)

    def _shown(self, name: str) -> str:
        """一欄在下拉裡顯示的字。那兩個佔位符原樣顯示。"""
        if name in (NONE_WORD, PICK_WORD):
            return name
        return self._col_labels.get(name) or column_label(name)

    def _ordered(self, pool: Sequence[str]) -> List[str]:
        """**量出來的東西排最上面**，位置與大小那幾格幾何欄排後面。

        混在同一張字母序清單裡的話，`glv_median`（他要的）跟 `w`（框有多寬，
        幾乎沒有人要畫）長得一樣重要 —— 而清單愈長，那件事愈貴。
        """
        mine = [c for c in pool if c not in self._fixed]
        rest = [c for c in pool if c in self._fixed]
        return mine + rest

    def _choices(self, role: str) -> List[str]:
        """這一個角色挑得到哪幾欄。

        第一格是「還沒挑」（見 :data:`PICK_WORD` / :data:`NONE_WORD`）——
        必填的那幾個角色講的是「還沒挑」，選填的講的是「不用」。
        """
        pool = (self._numeric if role in NUMERIC_ONLY else self._cols)
        return ([PICK_WORD if role in cspec.REQUIRED.get(self._mark, ())
                 else NONE_WORD] + self._ordered(pool))

    def set_spec(self, text: str) -> None:
        """整份換掉（預設那一排按下去走這裡）。**發一次 `changed`**，不是
        每一格各發一次 —— 中途那幾次畫的是半套設定，畫面會抖一下。"""
        try:
            got = cspec.parse_spec(text)
        except cspec.ChartSpecError:
            return
        blocked = [w.blockSignals(True) for w in self.boxes.values()]
        try:
            self._mark = str(got.get("mark") or cspec.MARK_POINT)
            if self.marks is not None:
                self.marks.set_text(self._mark)
            for role, box in self.boxes.items():
                want = str(got.get(role) or "")
                if want:
                    # ⚠ **`findData` 不是 `findText`** —— 顯示的是白話
                    # （`Box centre X (px)`），存的是欄名（`x`）。
                    at = box.findData(want)
                    if at >= 0:
                        box.setCurrentIndex(at)
                        continue
                box.setCurrentIndex(0)          # 「還沒挑」／「不用」
        finally:
            for box, was in zip(self.boxes.values(), blocked):
                box.blockSignals(was)
        self._sync_roles()
        self.changed.emit()

    def set_role(self, role: str, column: str) -> bool:
        """把一個角色指到某一欄上（**用欄名，不是畫面上那個字**）。

        呼叫端（與測試）要的是「把 Y 指到 `glv_mean`」，而畫面上那一格寫的
        可能是 `Box centre X (px)` —— 兩者的橋只有這一支。
        """
        box = self.boxes.get(str(role))
        if box is None:
            return False
        at = box.findData(str(column))
        if at < 0:
            return False
        box.setCurrentIndex(at)
        return True

    def spec(self) -> str:
        out: Dict[str, Any] = {"mark": self._mark}
        for role, box in self.boxes.items():
            # 用不到的角色由 `format_spec` 丟掉（規則只有一份，住在那裡）——
            # 這裡照樣把每一格填進去，那是「收起來不等於清掉」的另一半：
            # 換回散點時原本挑的「大小」還在畫面上。
            out[role] = str(box.currentData() or "")
        return cspec.format_spec(out)


def _role_word(role: str) -> str:
    """角色的名字。**不是那個鍵** —— ``x`` 對製程工程師不是一句話。"""
    return {cspec.ROLE_X: "Across the bottom",
            cspec.ROLE_Y: "Up the side",
            cspec.ROLE_COLOR: "Colour means",
            cspec.ROLE_SIZE: "Size means",
            # F117 G6：少了這一個，那一列印的是鍵（``facet``）——
            # 而那個字連英文母語者都不一定知道它在圖表上是什麼意思。
            cspec.ROLE_FACET: "Split into panels by"}.get(str(role), str(role))


class _PresetRow(QWidget):
    """一排「從這個開始」的膠囊（`chart_draw.PRESETS`）。

    ⚠ 這一排**不是設定**，是起點：按下去把下面每一格填好，然後使用者接著
    改。所以它不記住「現在選的是哪一個」—— 改了一格之後就不再是那個預設了，
    而一顆亮著的膠囊會說謊。
    """

    picked = Signal(str)

    def __init__(self, frame: Any = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._frame = frame
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.buttons: Dict[str, QWidget] = {}
        for name, why, _template in chart_draw.PRESETS:
            # ⚠ `kind="icon"` 是為了**看得出它是按鈕**。預設的 `ghost` 是
            # 透明的，而這一排底下就是設定區 —— render 出來看，五顆讀起來像
            # 一排標題而不是五顆按得下去的東西（`ColourButton` 的「auto」那
            # 一格踩過同一個）。
            btn = small_button(name, shape="wide", tip=why, parent=self,
                               kind="icon")
            btn.clicked.connect(lambda _c=False, n=name: self.picked.emit(n))
            # 那一顆做不出來就**按不下去**（沒有統計量可放）—— 一顆按了沒有
            # 反應的鈕比沒有那顆鈕更糟（推廣鐵則）。
            btn.setEnabled(bool(chart_draw.preset_spec(name, frame)))
            lay.addWidget(btn, 0)
            self.buttons[name] = btn
        lay.addStretch(1)
        # **一顆都做不出來的時候要講話**（F117 G6）。五顆灰掉的鈕讀起來像
        # 一排標題，而使用者不知道那是「壞了」還是「還不能按」—— 而真正的
        # 原因幾乎一定是同一個：還沒有數字可以放上去。
        # ⚠ 停用的 widget **收不到 tooltip**，所以那句話一定要寫在畫面上。
        self.hint = QLabel(
            "Run a trial first - these fill themselves in from the numbers "
            "it measures.", self)
        self.hint.setObjectName("paramHint")
        self.hint.setWordWrap(True)
        self.hint.setVisible(not any(b.isEnabled()
                                     for b in self.buttons.values()))
        lay.addWidget(self.hint, 0)

    def first_spec(self) -> str:
        """打開時落在哪一個 —— **第一個做得出來的**。一顆都做不出來（那一顆
        沒有量出任何統計量）就回空字串，讓下面那幾格停在「還沒挑」。"""
        for name, _why, _template in chart_draw.PRESETS:
            got = chart_draw.preset_spec(name, self._frame)
            if got:
                return got
        return ""


class GraphBuilderDialog(QDialog):
    """`SpecEditor` ＋ **一張跟著改的預覽**。``value()`` 回那一格的新字串。"""

    #: 預覽那一塊的高度（跟 `ChartSettingsDialog.PREVIEW_H` 同一個尺度）。
    PREVIEW_H = 260
    #: 長寬比 —— **跟 `ChartSettingsDialog` 同一個數字**（`ChartView.ASPECT`）。
    #: 兩個對話框畫的是同一種東西，比例不一樣的話同一張圖在兩邊長得不一樣。
    PREVIEW_ASPECT = 4.0 / 3.0

    def __init__(self, spec: str = "", frame: Any = None,
                 parent: Optional[QWidget] = None, look: str = "",
                 metric: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Chart")
        self.setModal(True)
        fit_screen.fit(self, 720, 780)
        self._frame = frame
        self._look = str(look or "")
        self._metric = str(metric or "")

        cols = list(getattr(frame, "columns", ()) or ())
        numeric = list(getattr(frame, "numeric_columns", lambda: cols)())
        labels = dict(getattr(frame, "labels", None) or {})
        fixed = [c for c in cols if c not in chart_draw.metric_columns(frame)]

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        head = QLabel("Start from one of these, then change any row below. "
                      "The chart follows what you pick.", self)
        head.setObjectName("paramHint")
        head.setWordWrap(True)
        root.addWidget(head)

        # **打開時一定是一個預設，不是一片空白**（計畫書 §5）—— graph builder
        # 最容易讓不寫 code 的人卡住的就是「面前一張白紙」（推廣鐵則）。
        self.presets = _PresetRow(self._frame, self)
        self.presets.picked.connect(self._use_preset)
        root.addWidget(self.presets)

        start = str(spec or "") or self.presets.first_spec()
        self.editor = SpecEditor(start, cols, self, numeric=numeric,
                                 labels=labels, fixed=fixed)
        root.addWidget(self.editor)
        for box in self.editor.boxes.values():
            box.currentTextChanged.connect(self.refresh_preview)
        # 換記號也要重畫 —— 那顆膠囊改的是整張圖的長相，不只是一格。
        self.editor.changed.connect(self.refresh_preview)

        self.view = ChartView(uc.CHART_CUSTOM, self,
                              aspect=self.PREVIEW_ASPECT)
        self.view.setMinimumHeight(self.PREVIEW_H)
        root.addWidget(self.view, 0)
        root.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons_mod.mark_primary(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh_preview()

    def _use_preset(self, name: str) -> None:
        got = chart_draw.preset_spec(name, self._frame)
        if got:
            self.editor.set_spec(got)

    def refresh_preview(self, *_a) -> None:
        """**畫不出來就讓它說出原因** —— `chart_draw` 已經會畫那句話
        （「pick x and y to draw this chart」），所以這裡什麼都不擋。"""
        self.view.set_data(
            {}, chart_style_for(self._look, uc.CHART_CUSTOM, uc.AXIS_X,
                                self._metric),
            frame=self._frame, spec=self.editor.spec())

    def value(self) -> str:
        return self.editor.spec()
