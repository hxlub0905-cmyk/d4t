# ADEPT Studio — 建 Golden Cell 模板 + 在上面標區域 (F7-12；F11 Region-1 重寫).
"""``TemplateDialog`` —— 匯入大圖 → 疊模板 → **在模板上畫區域** → 存進 recipe。

為什麼建模板與標區域在同一個對話框
----------------------------------
它們是同一件事的兩半：框的座標是**相對於那一格 cell** 的，所以少了 cell 那張圖，
四個 0–1 的數字沒有任何意義。以前 cell 只在建模板的時候出現一次，按下
「Use this template」就關掉了 —— 而 Studio 的狀態列這時候還會說「現在用
Region left/top/width/height 滑桿把區域標在 cell 上」，叫使用者去標一張已經
不在畫面上的圖（F11 §3.3.1 第 2 項）。**參照物不在場**才是那四個數字難用的原因。

為什麼這一步一定要有畫面
------------------------
模板法整條路唯一會**安靜壞掉**的地方是「週期估錯」：估錯了，疊出來的 cell 會
糊掉，而糊掉的模板會讓後面每一顆都對錯 —— 但畫面上不會有錯誤訊息，
只會有一批看起來很正常、其實量錯位置的數字。

所以這裡把判斷材料**全部攤開**：量到的週期、疊了幾格、疊出來長什麼樣，
以及一個銳利度分數（``ghosting_score``）。使用者不需要懂那個分數怎麼算 ——
他只要看得到「疊出來的圖是清楚的還是糊的」。

大圖不進 recipe，模板才進
-------------------------
寫進 recipe 的是**模板本身**（base64 純文字）與**框的座標**，不是大圖的路徑。
recipe 要能寄給別人；存路徑的話，圖被搬走、被換掉、下個月有人用了另一張大圖，
結果會安靜地變。

cell 多大由使用者決定
---------------------
週期是量出來的，但**使用者有時候要一個 2× 的大 cell**（他的原話）——
例如兩根 MG 才構成他要比的那個單元。所以量出來的週期是**預設值不是結論**：
「Cell size」那兩格填的是週期，改了按重疊就重算。``build_golden_cell`` 本來就
吃明講的 ``px``/``py``（那時候它不做信心檢查 —— 使用者說的不是猜的）。

畫面上文字要少
--------------
第一版把每支工具寫成一句話擺在畫面上，使用者回報「目前介面文字太多」。現在
四支工具是四顆圖示鈕（說明退到 tooltip），矩形的數字表收進一顆按鈕後面 ——
**那張表是校對用的，不是操作用的**，而操作的東西才該常駐。

畫布上怎麼操作、為什麼在 cell 上可以拖而在 patch 上不行 —— 見 ``cell_canvas``。
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from adept.core.algo import template as algo_template
from adept.core.ingest.imageio import load_gray
from adept.core.pipeline.cellrois import (
    CellRoiError, MAX_REGIONS, format_cell_rois, parse_cell_rois,
)

from .cell_canvas import (
    TOOL_ARRAY, TOOL_CLICK, TOOL_CURSOR, TOOL_DRAG, TOOL_PAINT, CellCanvas,
    region_color,
)
from .theme import TOKENS
from .widgets import IconButton, apply_button_cursors, restyle

__all__ = ["TemplateDialog"]

#: 新區域的預設名（ROI1、ROI2…）—— 使用者的原話就是這個命名。
_NAME_STEM = "ROI"


class TemplateDialog(QDialog):
    """匯入大圖 → 疊模板 → 在 cell 上畫區域 → 寫回卡片。"""

    #: (encoded cell, locate_axis, regions string)
    accepted_setup = Signal(str, str, str)
    #: 「這組框在整批上成不成立」—— 由 Studio 開既有的跨顆檢視（F7-11）
    check_across_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Template & regions")
        self.resize(1320, 880)
        self.cell: Optional[algo_template.GoldenCell] = None
        self._source_path = ""
        self._ready = False
        self._syncing = False
        self._from_recipe = False
        self._source: Optional[np.ndarray] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)
        outer.addWidget(self._build_source_row())

        split = QSplitter(Qt.Horizontal, self)
        left = QWidget(self)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)
        self.canvas = CellCanvas(self)
        self.canvas.boxes_changed.connect(self._on_boxes_changed)
        self.canvas.selection_changed.connect(self._on_canvas_selection)
        self.canvas.boxes_changed.connect(lambda *_a: self._refresh_tool_ui())
        self.canvas.selection_changed.connect(lambda *_a: self._refresh_tool_ui())
        self.canvas.array_anchors_changed.connect(self._on_anchors)
        self.canvas.regions_changed.connect(self._refresh_regions)
        left_lay.addWidget(self._build_tool_row())
        left_lay.addWidget(self.canvas, 1)
        split.addWidget(left)
        split.addWidget(self._build_side_panel())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        outer.addWidget(split, 1)

        outer.addWidget(self._build_view_row())

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Ok).setText("Use this setup")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self._set_ready(False)
        self._refresh_regions()
        self._on_tool_params()
        self.set_tool(TOOL_CURSOR)
        apply_button_cursors(self)

    # ---- 版面 ---------------------------------------------------------------
    def _build_source_row(self) -> QWidget:
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QHBoxLayout()
        self.btn_pick = QPushButton("Rebuild from image…", box)
        self.btn_pick.setObjectName("primary")
        self.btn_pick.clicked.connect(self._on_pick)
        row.addWidget(self.btn_pick)

        # cell 多大由使用者決定：量出來的週期是**預設值不是結論**
        for label, tip in (("Cell W", "One cell is this wide, in image pixels. "
                                      "Measured from the image, but you can "
                                      "override it — two periods per cell is a "
                                      "normal thing to want."),
                           ("Cell H", "One cell is this tall, in image pixels.")):
            lab = QLabel(label, box)
            lab.setObjectName("paramHint")
            lab.setToolTip(tip)
            row.addWidget(lab)
        self.spin_cell_w = self._spin(box, 2, 8192, 40, "Cell width in image pixels")
        self.spin_cell_h = self._spin(box, 2, 8192, 40, "Cell height in image pixels")
        row.insertWidget(row.count() - 1, self.spin_cell_w)
        row.addWidget(self.spin_cell_h)

        self.btn_double = QPushButton("×2", box)
        self.btn_double.setProperty("variant", "secondary")
        self.btn_double.setMaximumWidth(44)
        self.btn_double.setToolTip("Double both, then re-stack — a 2× cell.")
        self.btn_double.clicked.connect(self._on_double)
        row.addWidget(self.btn_double)

        self.btn_restack = QPushButton("Re-stack", box)
        self.btn_restack.setProperty("variant", "secondary")
        self.btn_restack.setToolTip(
            "Stack the cell again at this size. The regions you already drew "
            "keep their fractions of a cell, so a 2× cell moves them - check "
            "them afterwards.")
        self.btn_restack.clicked.connect(self.restack)
        row.addWidget(self.btn_restack)

        row.addStretch(1)
        self.path_label = QLabel("(no image chosen)", box)
        self.path_label.setObjectName("paramHint")
        row.addWidget(self.path_label)
        lay.addLayout(row)

        self.report = QLabel("", box)
        self.report.setObjectName("paramHint")
        self.report.setWordWrap(True)
        lay.addWidget(self.report)
        return box

    def _on_double(self) -> None:
        """兩軸各自加倍 —— 但**只加倍真的有週期的那一軸**。

        一維的 layout（垂直條紋）在 Y 上沒有週期，那一軸的「一格」就是整張影像
        的高度。把它乘二會得到一個比原圖還高的 cell，而且 ``build_golden_cell``
        會因為「使用者明講的一律相信」把那一軸當成有週期 —— 於是 ``locate_axis``
        從 ``x`` 變成 ``both``，定位開始在一個沒有相位的方向上搜尋。實測過
        （240 px 高的圖疊出 480 px 高的 cell）。
        """
        if self.spin_cell_w.isEnabled():
            self.spin_cell_w.setValue(min(8192, self.spin_cell_w.value() * 2))
        if self.spin_cell_h.isEnabled():
            self.spin_cell_h.setValue(min(8192, self.spin_cell_h.value() * 2))
        self.restack()

    def restack(self) -> bool:
        """用現在這兩格的尺寸重新疊一次模板。

        要有原圖才做得到 —— 從 recipe 讀回來的模板只有結果，沒有原料。
        那時候講清楚要先重新選一張圖，不要讓那顆鈕按下去沒反應。

        沒有週期的那一軸傳 ``None``（＝再量一次，結果仍然是「整張影像的高度」）
        —— 見 :meth:`_on_double`。
        """
        if self._source is None:
            self._say("Pick a full-size image first — re-stacking needs the "
                      "original image, and this template was read back from "
                      "the recipe.")
            return False
        gc = self.cell
        px = self.spin_cell_w.value() if (gc is None or gc.periodic_x) else None
        py = self.spin_cell_h.value() if (gc is None or gc.periodic_y) else None
        return self.load_image(self._source, self._source_path, px=px, py=py)

    def _build_side_panel(self) -> QWidget:
        panel = QWidget(self)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(self._build_region_group())
        lay.addWidget(self._build_box_group(), 1)
        return panel

    def _build_region_group(self) -> QWidget:
        g = QGroupBox("Regions", self)
        lay = QVBoxLayout(g)
        self.region_list = QListWidget(g)
        self.region_list.currentRowChanged.connect(self._on_region_row)
        self.region_list.itemChanged.connect(self._on_region_renamed)
        self.region_list.setMaximumHeight(130)
        lay.addWidget(self.region_list)

        row = QHBoxLayout()
        for text, slot, tip in (
                ("Add", self.add_region,
                 "A second region on the same cell — for example EPI and MG."),
                ("Rename", self._begin_rename,
                 "The name becomes part of every feature this region "
                 "produces, so it has to read like a variable name."),
                ("Delete", self.delete_region, "Remove this region.")):
            b = QPushButton(text, g)
            b.setProperty("variant", "secondary")
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        return g

    def _build_box_group(self) -> QWidget:
        """這個區域現在有幾塊，以及一顆「打開數字表」的鈕。

        表格本身**不常駐**（使用者：「表格部分建議不顯示，放在一個按鈕裡打開來
        可編輯」）—— 它是校對用的，而操作是在畫布上做的。常駐的是「有幾塊」，
        因為那是唯一需要一眼看到的狀態。
        """
        g = QGroupBox("Rectangles", self)
        lay = QVBoxLayout(g)
        lay.setSpacing(6)

        self.box_count = QLabel("", g)
        lay.addWidget(self.box_count)

        row = QHBoxLayout()
        self.btn_table = QPushButton("Edit numbers…", g)
        self.btn_table.setProperty("variant", "secondary")
        self.btn_table.setToolTip(
            "The same rectangles as numbers, in whole cell pixels — for "
            "checking and nudging, not for drawing.")
        self.btn_table.clicked.connect(self.open_box_table)
        row.addWidget(self.btn_table)
        row.addStretch(1)
        lay.addLayout(row)

        # 表格活在一個彈出視窗裡，而那個視窗**在這裡就建好**（隱藏著）。
        #
        # 為什麼不等第一次按下去才建：widget 一旦以 self 為 parent 又不在任何
        # layout 裡，Qt 就把它畫在 (0, 0) —— 使用者回報的「視窗左上角出現
        # 『Whole pixels of on…』字樣」就是那個。**沒有家的 widget 不是隱形的，
        # 它是畫在左上角的。**
        self._table_dialog = QDialog(self)
        self._table_dialog.setWindowTitle("Rectangles — whole cell pixels")
        self._table_dialog.resize(380, 460)
        tlay = QVBoxLayout(self._table_dialog)

        self.box_units = QLabel("", self._table_dialog)
        self.box_units.setObjectName("paramHint")
        self.box_units.setWordWrap(True)
        tlay.addWidget(self.box_units)

        self.box_table = QTableWidget(0, 4, self._table_dialog)
        self.box_table.setHorizontalHeaderLabels(["x", "y", "w", "h"])
        self.box_table.verticalHeader().setVisible(False)
        self.box_table.currentCellChanged.connect(self._on_table_row)
        self.box_table.itemChanged.connect(self._on_table_edited)
        tlay.addWidget(self.box_table, 1)

        close = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal,
                                 self._table_dialog)
        close.rejected.connect(self._table_dialog.hide)
        tlay.addWidget(close)
        return g

    def open_box_table(self) -> QDialog:
        """數字表的彈出視窗（同一份資料，開幾次都是同一個）。"""
        self._refresh_boxes()
        self._table_dialog.show()
        self._table_dialog.raise_()
        return self._table_dialog

    #: 五支工具：(key, 圖示, 標題, tooltip)
    _TOOLS = (
        (TOOL_CURSOR, "roi_cursor", "Select",
         "Pick rectangles: click one, Ctrl+click to add, or drag a box round "
         "several. Drag a selected one to move the whole group."),
        (TOOL_DRAG, "roi_drag", "Draw",
         "Drag out a new rectangle. Its handles resize it."),
        (TOOL_CLICK, "roi_click", "Click add",
         "Click to drop one rectangle of the size below, centred where you "
         "clicked."),
        (TOOL_ARRAY, "roi_array", "Multi add",
         "Click the centre of the first rectangle, then the centre of the "
         "last one; the ones in between are spaced evenly."),
        (TOOL_PAINT, "roi_paint", "Paint pixels",
         "Drag to light up individual cell pixels. On release they are merged "
         "into the fewest rectangles that cover them."),
    )

    #: 對齊：(how, 圖示, tooltip)。要先選兩個以上。
    _ALIGN = (
        ("left", "align_left", "Line their left edges up"),
        ("center", "align_center", "Line their centres up, left to right"),
        ("right", "align_right", "Line their right edges up"),
        ("top", "align_top", "Line their top edges up"),
        ("middle", "align_middle", "Line their centres up, top to bottom"),
        ("bottom", "align_bottom", "Line their bottom edges up"),
    )

    #: 工具鈕的邊長。使用者回報第一版「蠻醜的」—— 24 px 的鈕配 14 px 的圖示，
    #: 圖示只佔一半，看起來像沒畫完。34 讓圖示有地方可以呼吸。
    _TOOL_BTN = 34

    def _icon_button(self, parent, icon: str, tip: str, slot,
                     checkable: bool = False) -> IconButton:
        b = IconButton(icon, tip, parent, kind="ghost")
        b.setCheckable(checkable)
        # 大小由 QSS 的 ``[shape="tool"]`` 決定，不是 setFixedSize —— QSS 的
        # ``max-width`` 會蓋過去，而那正是第一版量出來只有 26 px 的原因。
        b.setProperty("shape", "tool")
        b.clicked.connect(slot)
        return b

    def _build_tool_row(self) -> QWidget:
        """圖示工具列。**畫面上不放句子** —— 說明在 tooltip（使用者：文字太多）。"""
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(3)

        self.tool_buttons = {}
        for key, icon, title, tip in self._TOOLS:
            b = self._icon_button(box, icon, "%s — %s" % (title, tip),
                                  lambda _c=False, k=key: self.set_tool(k),
                                  checkable=True)
            row.addWidget(b)
            self.tool_buttons[key] = b
        row.addWidget(_separator(box))

        self.btn_undo = self._icon_button(
            box, "undo", "Undo the last change to the rectangles (Ctrl+Z)",
            self.undo)
        row.addWidget(self.btn_undo)
        self.btn_del_sel = self._icon_button(
            box, "trash", "Delete the selected rectangles (Del)",
            self.delete_selected)
        row.addWidget(self.btn_del_sel)
        row.addWidget(_separator(box))

        self.align_buttons = {}
        for how, icon, tip in self._ALIGN:
            b = self._icon_button(
                box, icon, "%s. Select two or more first." % tip,
                lambda _c=False, h=how: self.align_selection(h))
            row.addWidget(b)
            self.align_buttons[how] = b
        row.addWidget(_separator(box))

        self.spin_w = self._spin(box, 1, 4096, 8, "Rectangle width, in cell pixels")
        self.spin_h = self._spin(box, 1, 4096, 8, "Rectangle height, in cell pixels")
        self.spin_nx = self._spin(box, 1, 512, 4, "How many across, end to end")
        self.spin_ny = self._spin(box, 1, 512, 1, "How many down, end to end")
        for label, spin in (("W", self.spin_w), ("H", self.spin_h),
                            ("×", self.spin_nx), ("↓", self.spin_ny)):
            lab = QLabel(label, box)
            lab.setObjectName("paramHint")
            row.addWidget(lab)
            row.addWidget(spin)
            spin.valueChanged.connect(self._on_tool_params)
        row.addStretch(1)

        self.btn_array_ok = QPushButton("Add them", box)
        self.btn_array_ok.setObjectName("primary")
        self.btn_array_ok.clicked.connect(self.commit_array)
        self.btn_array_ok.setEnabled(False)
        row.addWidget(self.btn_array_ok)
        lay.addLayout(row)

        self.tool_hint = QLabel("", box)
        self.tool_hint.setObjectName("paramHint")
        self.tool_hint.setWordWrap(True)
        lay.addWidget(self.tool_hint)
        return box

    # ---- 工具列的動作 -------------------------------------------------------
    def set_tool(self, key: str) -> None:
        self.canvas.set_tool(key)
        self._refresh_tool_ui()

    def undo(self) -> bool:
        ok = self.canvas.undo()
        self._refresh_regions()
        self._refresh_tool_ui()
        return ok

    def delete_selected(self) -> bool:
        ok = self.canvas.delete_selected()
        self._refresh_tool_ui()
        return ok

    def align_selection(self, how: str) -> int:
        n = self.canvas.align_selection(how)
        self._refresh_tool_ui()          # 先重畫，_say 才不會被它蓋掉
        if not n:
            self._say("Select two or more rectangles first — align moves them "
                      "to the edges of what you selected.")
        return n

    def toggle_array(self) -> None:
        """（保留給既有呼叫端）在陣列工具與游標之間切換。"""
        self.set_tool(TOOL_CURSOR if self.canvas.tool() == TOOL_ARRAY
                      else TOOL_ARRAY)

    def commit_array(self) -> int:
        n = self.canvas.commit_array()
        self._refresh_tool_ui()
        self._refresh_boxes()
        return n

    def _on_tool_params(self) -> None:
        self.canvas.set_box_size(self.spin_w.value(), self.spin_h.value())
        self.canvas.set_array_counts(self.spin_nx.value(), self.spin_ny.value())
        self._refresh_tool_ui()

    def _on_anchors(self, _n: int) -> None:
        self._refresh_tool_ui()

    def _refresh_tool_ui(self) -> None:
        tool = self.canvas.tool()
        for key, btn in self.tool_buttons.items():
            btn.setProperty("active", "true" if key == tool else "false")
            btn.setChecked(key == tool)
            restyle(btn)
        for spin in (self.spin_nx, self.spin_ny):
            spin.setEnabled(tool == TOOL_ARRAY)
        for spin in (self.spin_w, self.spin_h):
            spin.setEnabled(tool in (TOOL_ARRAY, TOOL_CLICK))

        picked = len(self.canvas.selection())
        self.btn_undo.setEnabled(self.canvas.can_undo())
        self.btn_del_sel.setEnabled(picked > 0)
        for b in self.align_buttons.values():
            b.setEnabled(picked >= 2)

        anchors = self.canvas.array_anchor_count()
        n = len(self.canvas.array_preview()) if tool == TOOL_ARRAY else 0
        self.btn_array_ok.setEnabled(tool == TOOL_ARRAY and anchors >= 2)
        self.btn_array_ok.setText("Add %d" % n if n else "Add them")
        self.tool_hint.setText(self._tool_hint(tool, anchors, n, picked,
                                               self.canvas.array_pitch()))

    @staticmethod
    def _tool_hint(tool: str, anchors: int, n: int, picked: int = 0,
                   pitch: Tuple[int, int] = (0, 0)) -> str:
        if tool == TOOL_ARRAY:
            if anchors == 0:
                return "Click the centre of the FIRST rectangle (top-left)."
            if anchors == 1:
                return ("Now click the centre of the LAST one (bottom-right). "
                        "Esc cancels.")
            px, py = pitch
            bits = ["%d rectangles" % n]
            if px:
                bits.append("pitch %d px across" % px)
            if py:
                bits.append("pitch %d px down" % py)
            return " · ".join(bits) + " — every gap is the same."
        if tool == TOOL_PAINT:
            return "Drag over pixels; they merge into rectangles on release."
        if tool == TOOL_CLICK:
            return "Click to drop one rectangle, centred on the pointer."
        if tool == TOOL_CURSOR:
            if picked >= 2:
                return "%d selected — the align buttons move them to the " \
                       "edges of the selection." % picked
            return ("Click a rectangle, Ctrl+click to add, or drag a box round "
                    "several. Right-drag anywhere to pan.")
        return "Drag out a rectangle. Right-drag anywhere to pan."

    @staticmethod
    def _spin(parent, lo: int, hi: int, value: int, tip: str) -> QSpinBox:
        s = QSpinBox(parent)
        s.setRange(lo, hi)
        s.setValue(value)
        s.setToolTip(tip)
        s.setMaximumWidth(78)
        return s

    def _build_view_row(self) -> QWidget:
        box = QWidget(self)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        for text, slot in (("−", lambda: self.canvas.zoom_by(1 / 1.3)),
                           ("+", lambda: self.canvas.zoom_by(1.3)),
                           ("Fit", self.canvas.fit)):
            b = QPushButton(text, box)
            b.setProperty("variant", "secondary")
            b.setMaximumWidth(52)
            b.clicked.connect(slot)
            row.addWidget(b)

        self.chk_tile = QCheckBox("Show neighbouring cells", box)
        self.chk_tile.setChecked(True)
        self.chk_tile.setToolTip(
            "The cell repeats, and its origin sits on the strongest edge — so "
            "the thing you want to box often straddles the seam. With the "
            "neighbours drawn you can see that it is continuous.")
        self.chk_tile.toggled.connect(self.canvas.set_tiled)
        row.addWidget(self.chk_tile)
        row.addStretch(1)

        self.btn_check = QPushButton("Check across defects…", box)
        self.btn_check.setProperty("variant", "secondary")
        self.btn_check.setToolTip(
            "These settings have to hold for the whole batch, not for one "
            "defect. This opens the same boxes drawn on many patches at once.")
        self.btn_check.clicked.connect(self.check_across_requested.emit)
        row.addWidget(self.btn_check)
        return box

    # ---- 對外（測試也走這條，不必真的開檔案對話框）------------------------
    def load_image(self, image: Any, name: str = "",
                   px: Optional[int] = None, py: Optional[int] = None) -> bool:
        """吃一張大圖，量週期、疊模板、把證據寫上畫面。

        ``px``/``py`` 留空 = 從影像自己量（第一次都是這樣）；填了就照使用者說的
        疊 —— 「有時候會需要 2× 大 cell」。明講的尺寸 ``build_golden_cell`` 一律
        相信，不做信心檢查（那是使用者說的，不是猜的）。
        """
        arr = np.asarray(image)
        if arr.size == 0:
            self._fail("that image is empty")
            return False

        gc = algo_template.build_golden_cell(arr, px=px, py=py)
        self.cell = gc
        self._from_recipe = False
        self._source = arr
        self._source_path = str(name or "")
        self.path_label.setText(self._source_path or "(image)")

        if gc.cell.size == 0:
            self.canvas.set_cell(None)
            self._fail("; ".join(gc.warnings) or "no repeating cell was found")
            return False

        self.canvas.set_cell(gc.cell)
        self._set_ready(True)
        self.report.setText(self.summary())
        self._sync_cell_size()
        self._refresh_units()
        if not self.canvas.regions():
            self.add_region()
        self._refresh_tool_ui()
        return True

    def _sync_cell_size(self) -> None:
        """把量到（或使用者指定）的尺寸放回那兩格，別讓它們各說各話。"""
        gc = self.cell
        if gc is None or gc.cell.size == 0:
            return
        self._syncing = True
        self.spin_cell_w.setValue(int(gc.cell.shape[1]))
        self.spin_cell_h.setValue(int(gc.cell.shape[0]))
        # 沒有週期的那一軸不給改：它的「一格」就是整張影像，那不是一個可以
        # 挑的尺寸。鎖起來並講出原因，比讓人改了發現沒反應好。
        for spin, ok, axis in ((self.spin_cell_w, gc.periodic_x, "across"),
                               (self.spin_cell_h, gc.periodic_y, "down")):
            spin.setEnabled(bool(ok))
            spin.setToolTip("One cell is this many image pixels %s." % axis
                            if ok else
                            "This image has no period %s, so one cell spans "
                            "the whole image that way — there is no size to "
                            "choose." % axis)
        self._syncing = False

    def load_encoded(self, text: str, axis: str = "x") -> bool:
        """把**已經存在 recipe 裡**的模板載回來（不必再挑一次大圖）。

        為什麼一定要有這條路：回來調框是最常見的第二次操作，而重挑一次大圖會
        **重算模板** —— 相位可能落在另一個地標上，於是使用者原本標好的框全部
        平移了，而畫面上不會有錯誤訊息（``build_golden_cell`` 的錨定說明）。
        所以「回來改框」與「重建模板」必須是兩個不同的動作。

        重建才有的證據（疊了幾格、銳利度）這條路拿不到 —— **不編造**，
        摘要照實說它是從 recipe 讀回來的。
        """
        # `decode_template` 兩種標籤都讀（舊的 gc1 沒有自週期，`encoded()`
        # 會在存回去的時候補上）。
        decoded = algo_template.decode_template(str(text or ""))
        cell = decoded[0] if decoded else None
        if cell is None or cell.size == 0:
            return False
        px, py = int(cell.shape[1]), int(cell.shape[0])
        self.cell = algo_template.GoldenCell(
            cell=cell, px=px, py=py,
            periodic_x=str(axis) in ("x", "both"),
            periodic_y=str(axis) in ("y", "both"))
        self._from_recipe = True
        self._source = None
        self._source_path = ""
        self.path_label.setText("(the template stored in this recipe)")
        self.canvas.set_cell(cell)
        self._set_ready(True)
        self.report.setText(self.summary())
        self._sync_cell_size()
        self._refresh_units()
        self._refresh_tool_ui()
        return True

    def set_regions_text(self, text: str) -> None:
        """把卡片上存的區域字串載進畫布（打壞的字串當成空的，不要擋住編輯）。"""
        try:
            regions = parse_cell_rois(text)
        except CellRoiError:
            regions = []
        self.canvas.set_regions(regions)
        self.canvas.set_current_region(0)
        self._refresh_regions()

    def regions_text(self) -> str:
        return format_cell_rois(self.canvas.regions())

    def set_patch_size(self, size: Optional[Tuple[int, int]]) -> None:
        """一顆 defect 看得到多大（``(h, w)``）—— 不知道就傳 ``None``。"""
        self.canvas.set_patch_size(size)

    def summary(self) -> str:
        """一行摘要 —— 判斷材料全部攤開（測試也讀這個，不必去讀畫素）。"""
        gc = self.cell
        if gc is None or gc.cell.size == 0:
            return ""
        axis = {(True, False): "across", (False, True): "down",
                (True, True): "both ways"}[gc.periodic]
        if self._from_recipe:
            return " · ".join(
                ["cell %d x %d px" % (gc.px, gc.py), "repeats %s" % axis,
                 "read back from this recipe - rebuild it from an image if "
                 "this batch looks different"] + self._self_repeat_note())
        bits = ["cell %d x %d px" % (gc.px, gc.py),
                "repeats %s" % axis,
                "stacked from %d cells" % gc.n_cells,
                "sharpness %.0f / 100" % gc.ghosting]
        bits.extend(self._self_repeat_note())
        if gc.ghosting < 40.0:
            bits.append("- the stack looks blurred, which usually means the "
                        "period was measured wrong; a blurred template will "
                        "mis-place the region on every defect")
        for w in gc.warnings:
            if "arbitrary" in w:
                bits.append("- " + w)
        return " · ".join(bits)

    def self_period(self) -> Tuple[int, int]:
        """這個 cell 自己重複的單元（cell 像素）—— 存進模板字串的那一組。"""
        gc = self.cell
        if gc is None or gc.cell.size == 0:
            return (0, 0)
        return algo_template.cell_self_period(gc.cell)

    def _self_repeat_note(self) -> List[str]:
        """cell 是自己的 k 倍時講一句話 —— **不要等跑完 200 顆才發現**。

        使用者可以把 cell 取成 2×（他要的）。那時候一顆 patch **分不出自己在
        哪一份上**，而那件事只有在「兩份上標的區域不一樣」時才要緊。確定度
        本身已經處理掉了（摺在自週期上，見 ``algo/template.match_patch``），
        所以這裡不是警告，是一句要讓他知道的事實。
        """
        gc = self.cell
        if gc is None or gc.cell.size == 0:
            return []
        sx, sy = self.self_period()
        h, w = gc.cell.shape[:2]
        kx = w // sx if sx and w % sx == 0 else 1
        ky = h // sy if sy and h % sy == 0 else 1
        if kx <= 1 and ky <= 1:
            return []
        times = kx * ky
        return ["this cell holds %d copies of a %d x %d px repeat, so a patch "
                "cannot tell which copy it is on - fine if you mark the same "
                "thing on each, not fine if they differ" % (times, sx, sy)]

    def locate_axis(self) -> str:
        gc = self.cell
        if gc is None:
            return "x"
        return {(True, False): "x", (False, True): "y",
                (True, True): "both"}.get(gc.periodic, "x")

    def encoded(self) -> str:
        gc = self.cell
        if gc is None:
            return ""
        # 自週期一起存進字串：它是模板的性質，一份模板只有一個答案，而
        # ``run_defect`` 是逐顆呼叫的（見 algo/template.encode_cell）。
        return algo_template.encode_cell(gc.cell, self.self_period())

    def is_ready(self) -> bool:
        """按得下「Use this setup」嗎（用明確狀態，不要問 widget）。"""
        return bool(self._ready)

    # ---- 區域 ---------------------------------------------------------------
    def add_region(self, name: str = "") -> str:
        """加一個區域（預設 ROI1、ROI2…），並選取它。"""
        regions = self.canvas.regions()
        if len(regions) >= MAX_REGIONS:
            self._say("At most %d regions on one card." % MAX_REGIONS)
            return ""
        taken = {n for n, _b in regions}
        new = str(name or "")
        if not new:
            i = 1
            while "%s%d" % (_NAME_STEM, i) in taken:
                i += 1
            new = "%s%d" % (_NAME_STEM, i)
        regions.append((new, []))
        self.canvas.set_regions(regions)
        self.canvas.set_current_region(len(regions) - 1)
        self._refresh_regions()
        return new

    def delete_region(self) -> None:
        regions = self.canvas.regions()
        row = self.canvas.current_region()
        if not (0 <= row < len(regions)):
            return
        regions.pop(row)
        self.canvas.set_regions(regions)
        self.canvas.set_current_region(min(row, max(0, len(regions) - 1)))
        self._refresh_regions()

    def rename_region(self, name: str) -> bool:
        """改名；名字不合法或撞名就回 False 並講一句話（鐵則 4）。"""
        regions = self.canvas.regions()
        row = self.canvas.current_region()
        if not (0 <= row < len(regions)):
            return False
        new = str(name).strip()
        others = [n for i, (n, _b) in enumerate(regions) if i != row]
        try:
            parse_cell_rois("%s: 0,0,1,1" % new)
        except CellRoiError as e:
            self._say(str(e))
            return False
        if new in others:
            self._say("There is already a region called '%s'." % new)
            return False
        regions[row] = (new, regions[row][1])
        self.canvas.set_regions(regions)
        self.canvas.set_current_region(row)
        self._refresh_regions()
        return True

    def _begin_rename(self) -> None:
        item = self.region_list.currentItem()
        if item is not None:
            self.region_list.editItem(item)

    def _on_region_renamed(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        if not self.rename_region(item.text()):
            self._refresh_regions()          # 名字沒改成 -> 畫面要退回去

    def _on_region_row(self, row: int) -> None:
        if self._syncing or row < 0:
            return
        self.canvas.set_current_region(row)
        self._refresh_boxes()

    # ---- 框的清單 -----------------------------------------------------------
    def _on_boxes_changed(self, _region: int, _boxes: list) -> None:
        self._refresh_boxes()

    def _on_canvas_selection(self, _region: int, index: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.box_table.setCurrentCell(index, 0)
        self._syncing = False

    def _on_table_row(self, row: int, _c: int, _pr: int, _pc: int) -> None:
        if not self._syncing and row >= 0:
            self.canvas.select_box(row)

    def _on_table_edited(self, item: QTableWidgetItem) -> None:
        """數字打進去要跟畫布一致 —— 兩邊是同一份資料，不是兩份。"""
        if self._syncing:
            return
        row = item.row()
        regions = self.canvas.regions()
        ri = self.canvas.current_region()
        if not (0 <= ri < len(regions)) or not (0 <= row < len(regions[ri][1])):
            return
        vals = []
        for c in range(4):
            cell = self.box_table.item(row, c)
            try:
                vals.append(int(round(float(cell.text()))))
            except (AttributeError, ValueError):
                self._refresh_boxes()      # 打了不是數字的字 -> 退回去
                return
        self.canvas.replace_box(row, self.canvas.from_px(vals))

    # ---- 同步 ---------------------------------------------------------------
    def _refresh_regions(self) -> None:
        self._syncing = True
        self.region_list.clear()
        for i, (name, boxes) in enumerate(self.canvas.regions()):
            item = QListWidgetItem("%s  ·  %d" % (name, len(boxes)))
            item.setData(Qt.UserRole, name)
            item.setText(name)
            item.setForeground(region_color(i))
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setIcon(_swatch(region_color(i)))
            self.region_list.addItem(item)
        self.region_list.setCurrentRow(self.canvas.current_region())
        self._syncing = False
        self._refresh_boxes()

    def _refresh_boxes(self) -> None:
        self._syncing = True
        regions = self.canvas.regions()
        ri = self.canvas.current_region()
        boxes = regions[ri][1] if 0 <= ri < len(regions) else []
        self.box_table.setRowCount(len(boxes))
        for r, box in enumerate(boxes):
            for c, v in enumerate(self.canvas.to_px(box)):
                self.box_table.setItem(r, c, QTableWidgetItem("%d" % v))
        self.box_table.setCurrentCell(self.canvas.selected_box(), 0)
        self._syncing = False
        name = regions[ri][0] if 0 <= ri < len(regions) else "—"
        self.box_count.setText(
            "%s: %d rectangle%s" % (name, len(boxes),
                                    "" if len(boxes) == 1 else "s"))
        self._refresh_units()

    def _refresh_units(self) -> None:
        h, w = self.canvas.cell_shape()
        self.box_units.setText(
            "Whole pixels of one cell (%d × %d px). In the recipe they are "
            "stored as fractions of a cell — not of the patch." % (w, h))

    # ---- 內部 ---------------------------------------------------------------
    def _set_ready(self, ready: bool) -> None:
        self._ready = bool(ready)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self._ready)

    def _fail(self, why: str) -> None:
        self._set_ready(False)
        self.report.setText("Could not build a template: %s." % why)

    def _say(self, text: str) -> None:
        """一句話回饋（改名撞名、re-stack 沒有原圖…）—— 講在工具列下面那一行。"""
        self.tool_hint.setText(text)

    def _on_pick(self) -> None:            # pragma: no cover — 需要真的開檔案總管
        path, _f = QFileDialog.getOpenFileName(
            self, "Choose a full-size image", "",
            "Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp);;All files (*)")
        if not path:
            return
        try:
            img = load_gray(path)
        except Exception as e:             # noqa: BLE001 — UI 邊界
            self._fail("%s: %s" % (type(e).__name__, e))
            return
        self.load_image(img, path)

    def _on_accept(self) -> None:
        if not self.is_ready():
            return
        empty = [n for n, boxes in self.canvas.regions() if not boxes]
        if empty:
            # 空的區域存不進 recipe（``parse_cell_rois`` 會擋），而使用者八成
            # 只是還沒畫。講出來、讓他決定，不要安靜地丟掉。
            keep = QMessageBox.question(
                self, "Regions with no rectangles",
                "%s ha%s no rectangles yet and will not be saved. Go back and "
                "draw them?" % (", ".join(empty), "s" if len(empty) == 1 else "ve"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if keep == QMessageBox.Yes:
                return
        self.accepted_setup.emit(self.encoded(), self.locate_axis(),
                                 self.regions_text())
        self.accept()


def _separator(parent: QWidget) -> QWidget:
    """工具列上的一條細分隔線 —— 把「畫」「改」「排」三組分開。"""
    line = QFrame(parent)
    line.setFrameShape(QFrame.VLine)
    line.setFixedWidth(9)
    line.setStyleSheet("color:%s;" % TOKENS["border_default"])
    return line


def _swatch(color: QColor):
    """區域清單前面的色塊 —— 顏色是它在畫布上的身分。"""
    from PySide6.QtGui import QIcon, QPainter

    pm = QPixmap(12, 12)
    pm.fill(QColor(TOKENS["bg_surface"]))
    p = QPainter(pm)
    p.fillRect(1, 1, 10, 10, color)
    p.end()
    return QIcon(pm)
