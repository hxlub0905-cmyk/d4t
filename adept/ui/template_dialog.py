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

from .cell_canvas import CellCanvas, region_color
from .theme import TOKENS
from .widgets import apply_button_cursors

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
        self.resize(1000, 700)
        self.cell: Optional[algo_template.GoldenCell] = None
        self._source_path = ""
        self._ready = False
        self._syncing = False
        self._from_recipe = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)
        outer.addWidget(self._build_source_row())

        split = QSplitter(Qt.Horizontal, self)
        self.canvas = CellCanvas(self)
        self.canvas.boxes_changed.connect(self._on_boxes_changed)
        self.canvas.selection_changed.connect(self._on_canvas_selection)
        self.canvas.array_anchors_changed.connect(self._on_anchors)
        split.addWidget(self.canvas)
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
        apply_button_cursors(self)

    # ---- 版面 ---------------------------------------------------------------
    def _build_source_row(self) -> QWidget:
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QHBoxLayout()
        self.btn_pick = QPushButton("Rebuild from a full-size image…", box)
        self.btn_pick.setObjectName("primary")
        self.btn_pick.clicked.connect(self._on_pick)
        row.addWidget(self.btn_pick)
        self.path_label = QLabel("(no image chosen)", box)
        self.path_label.setObjectName("paramHint")
        row.addWidget(self.path_label, 1)
        lay.addLayout(row)

        self.report = QLabel("", box)
        self.report.setObjectName("paramHint")
        self.report.setWordWrap(True)
        lay.addWidget(self.report)
        return box

    def _build_side_panel(self) -> QWidget:
        panel = QWidget(self)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(self._build_region_group())
        lay.addWidget(self._build_box_group(), 1)
        lay.addWidget(self._build_array_group())
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
        g = QGroupBox("Rectangles in this region", self)
        lay = QVBoxLayout(g)
        hint = QLabel("Drag on the cell to draw one. A region can be several "
                      "rectangles — that is how “the EPI minus where the MG "
                      "crosses it” is expressed.", g)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.box_table = QTableWidget(0, 4, g)
        self.box_table.setHorizontalHeaderLabels(["x", "y", "w", "h"])
        self.box_table.verticalHeader().setVisible(False)
        self.box_table.currentCellChanged.connect(self._on_table_row)
        self.box_table.itemChanged.connect(self._on_table_edited)
        lay.addWidget(self.box_table, 1)

        self.box_units = QLabel("", g)
        self.box_units.setObjectName("paramHint")
        lay.addWidget(self.box_units)

        row = QHBoxLayout()
        self.btn_del_box = QPushButton("Delete rectangle", g)
        self.btn_del_box.setProperty("variant", "secondary")
        self.btn_del_box.clicked.connect(lambda: self.canvas.delete_selected())
        row.addWidget(self.btn_del_box)
        row.addStretch(1)
        lay.addLayout(row)
        return g

    def _build_array_group(self) -> QWidget:
        """一次長一整片等距的框（使用者定的 multi add）。"""
        g = QGroupBox("Multi add — a whole row or grid at once", self)
        lay = QVBoxLayout(g)
        hint = QLabel("Pulling twenty stripes one at a time drifts, and drift "
                      "does not show on screen — it shows in the numbers. Here "
                      "the spacing is worked out from the two anchors.", g)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        grid = QHBoxLayout()
        self.spin_w = self._spin(g, 1, 4096, 8, "Box W (px)")
        self.spin_h = self._spin(g, 1, 4096, 8, "Box H (px)")
        self.spin_nx = self._spin(g, 1, 512, 4, "Across")
        self.spin_ny = self._spin(g, 1, 512, 1, "Down")
        for label, spin in (("W", self.spin_w), ("H", self.spin_h),
                            ("across", self.spin_nx), ("down", self.spin_ny)):
            grid.addWidget(QLabel(label, g))
            grid.addWidget(spin)
            spin.valueChanged.connect(self._on_array_params)
        grid.addStretch(1)
        lay.addLayout(grid)

        row = QHBoxLayout()
        self.btn_array = QPushButton("Start", g)
        self.btn_array.setProperty("variant", "secondary")
        self.btn_array.clicked.connect(self.toggle_array)
        row.addWidget(self.btn_array)
        self.btn_array_ok = QPushButton("Add them", g)
        self.btn_array_ok.setObjectName("primary")
        self.btn_array_ok.clicked.connect(self.commit_array)
        self.btn_array_ok.setEnabled(False)
        row.addWidget(self.btn_array_ok)
        row.addStretch(1)
        lay.addLayout(row)

        self.array_hint = QLabel("", g)
        self.array_hint.setObjectName("paramHint")
        self.array_hint.setWordWrap(True)
        lay.addWidget(self.array_hint)
        return g

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
    def load_image(self, image: Any, name: str = "") -> bool:
        """吃一張大圖，量週期、疊模板、把證據寫上畫面。"""
        arr = np.asarray(image)
        if arr.size == 0:
            self._fail("that image is empty")
            return False

        gc = algo_template.build_golden_cell(arr)
        self.cell = gc
        self._from_recipe = False
        self._source_path = str(name or "")
        self.path_label.setText(self._source_path or "(image)")

        if gc.cell.size == 0:
            self.canvas.set_cell(None)
            self._fail("; ".join(gc.warnings) or "no repeating cell was found")
            return False

        self.canvas.set_cell(gc.cell)
        self._set_ready(True)
        self.report.setText(self.summary())
        self._refresh_units()
        if not self.canvas.regions():
            self.add_region()
        return True

    def load_encoded(self, text: str, axis: str = "x") -> bool:
        """把**已經存在 recipe 裡**的模板載回來（不必再挑一次大圖）。

        為什麼一定要有這條路：回來調框是最常見的第二次操作，而重挑一次大圖會
        **重算模板** —— 相位可能落在另一個地標上，於是使用者原本標好的框全部
        平移了，而畫面上不會有錯誤訊息（``build_golden_cell`` 的錨定說明）。
        所以「回來改框」與「重建模板」必須是兩個不同的動作。

        重建才有的證據（疊了幾格、銳利度）這條路拿不到 —— **不編造**，
        摘要照實說它是從 recipe 讀回來的。
        """
        cell = algo_template.decode_cell(str(text or ""))
        if cell is None or cell.size == 0:
            return False
        px, py = int(cell.shape[1]), int(cell.shape[0])
        self.cell = algo_template.GoldenCell(
            cell=cell, px=px, py=py,
            periodic_x=str(axis) in ("x", "both"),
            periodic_y=str(axis) in ("y", "both"))
        self._from_recipe = True
        self._source_path = ""
        self.path_label.setText("(the template stored in this recipe)")
        self.canvas.set_cell(cell)
        self._set_ready(True)
        self.report.setText(self.summary())
        self._refresh_units()
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
            return ("cell %d x %d px · repeats %s · read back from this recipe "
                    "- rebuild it from an image if this batch looks different"
                    % (gc.px, gc.py, axis))
        bits = ["cell %d x %d px" % (gc.px, gc.py),
                "repeats %s" % axis,
                "stacked from %d cells" % gc.n_cells,
                "sharpness %.0f / 100" % gc.ghosting]
        if gc.ghosting < 40.0:
            bits.append("- the stack looks blurred, which usually means the "
                        "period was measured wrong; a blurred template will "
                        "mis-place the region on every defect")
        for w in gc.warnings:
            if "arbitrary" in w:
                bits.append("- " + w)
        return " · ".join(bits)

    def locate_axis(self) -> str:
        gc = self.cell
        if gc is None:
            return "x"
        return {(True, False): "x", (False, True): "y",
                (True, True): "both"}.get(gc.periodic, "x")

    def encoded(self) -> str:
        gc = self.cell
        return "" if gc is None else algo_template.encode_cell(gc.cell)

    def is_ready(self) -> bool:
        """按得下「Use this setup」嗎（用明確狀態，不要問 widget）。"""
        return bool(self._ready)

    # ---- 區域 ---------------------------------------------------------------
    def add_region(self, name: str = "") -> str:
        """加一個區域（預設 ROI1、ROI2…），並選取它。"""
        regions = self.canvas.regions()
        if len(regions) >= MAX_REGIONS:
            self.array_hint.setText("At most %d regions on one card."
                                    % MAX_REGIONS)
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

    # ---- 陣列工具 -----------------------------------------------------------
    def toggle_array(self) -> None:
        if self.canvas.array_active():
            self.canvas.cancel_array()
        else:
            self.canvas.start_array(*self._array_params())
        self._refresh_array_ui()

    def commit_array(self) -> int:
        n = self.canvas.commit_array()
        self._refresh_array_ui()
        self._refresh_boxes()
        return n

    def _array_params(self) -> Tuple[float, float, int, int]:
        """把 px 的框大小換成「相對於一格」—— 使用者想的是 px，存的是比例。"""
        h, w = self.canvas.cell_shape()
        return (self.spin_w.value() / float(w), self.spin_h.value() / float(h),
                self.spin_nx.value(), self.spin_ny.value())

    def _on_array_params(self) -> None:
        if self.canvas.array_active():
            self.canvas.update_array(*self._array_params())
        self._refresh_array_ui()

    def _on_anchors(self, _n: int) -> None:
        self._refresh_array_ui()

    def _refresh_array_ui(self) -> None:
        active = self.canvas.array_active()
        anchors = self.canvas.array_anchor_count()
        self.btn_array.setText("Cancel" if active else "Start")
        self.btn_array_ok.setEnabled(active and anchors >= 2)
        n = len(self.canvas.array_preview()) if active else 0
        self.btn_array_ok.setText("Add %d rectangles" % n if n else "Add them")
        if not active:
            self.array_hint.setText("")
        elif anchors == 0:
            self.array_hint.setText(
                "Click where the FIRST rectangle's centre goes (top-left).")
        elif anchors == 1:
            self.array_hint.setText(
                "Now click where the LAST rectangle's centre goes "
                "(bottom-right). Esc cancels.")
        else:
            self.array_hint.setText(
                "%d rectangles, evenly spaced between the two crosshairs. "
                "Click again to move the first anchor." % n)

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
        h, w = self.canvas.cell_shape()
        scale = (w, h, w, h)
        vals = []
        for c in range(4):
            cell = self.box_table.item(row, c)
            try:
                vals.append(float(cell.text()) / float(scale[c]))
            except (AttributeError, ValueError):
                self._refresh_boxes()
                return
        self.canvas.replace_box(row, tuple(vals))

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
        h, w = self.canvas.cell_shape()
        scale = (w, h, w, h)
        self.box_table.setRowCount(len(boxes))
        for r, box in enumerate(boxes):
            for c in range(4):
                self.box_table.setItem(
                    r, c, QTableWidgetItem("%.1f" % (box[c] * scale[c])))
        self.box_table.setCurrentCell(self.canvas.selected_box(), 0)
        self._syncing = False
        self.btn_del_box.setEnabled(bool(boxes))
        self._refresh_units()

    def _refresh_units(self) -> None:
        h, w = self.canvas.cell_shape()
        self.box_units.setText(
            "pixels of one cell (%d × %d px). Positions are fractions of a "
            "cell in the recipe, not of the patch." % (w, h))

    # ---- 內部 ---------------------------------------------------------------
    def _set_ready(self, ready: bool) -> None:
        self._ready = bool(ready)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self._ready)

    def _fail(self, why: str) -> None:
        self._set_ready(False)
        self.report.setText("Could not build a template: %s." % why)

    def _say(self, text: str) -> None:
        self.array_hint.setText(text)

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


def _swatch(color: QColor):
    """區域清單前面的色塊 —— 顏色是它在畫布上的身分。"""
    from PySide6.QtGui import QIcon, QPainter

    pm = QPixmap(12, 12)
    pm.fill(QColor(TOKENS["bg_surface"]))
    p = QPainter(pm)
    p.fillRect(1, 1, 10, 10, color)
    p.end()
    return QIcon(pm)
