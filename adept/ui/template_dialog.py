# ADEPT Studio — 從大圖建 Golden Cell 模板 (F7-12).
"""``TemplateDialog`` —— 匯入一張大圖 → 量週期 → 疊出模板 → 存進 recipe。

為什麼這一步一定要有畫面
------------------------
模板法整條路唯一會**安靜壞掉**的地方是「週期估錯」：估錯了，疊出來的 cell 會
糊掉，而糊掉的模板會讓後面每一顆都對錯 —— 但畫面上不會有錯誤訊息，
只會有一批看起來很正常、其實量錯位置的數字。

所以這個對話框把判斷材料**全部攤開**：量到的週期、疊了幾格、疊出來長什麼樣，
以及一個銳利度分數（``ghosting_score``，repo 裡本來就有）。使用者不需要懂
那個分數怎麼算 —— 他只要看得到「疊出來的圖是清楚的還是糊的」。

大圖不進 recipe，模板才進
-------------------------
按下「Use this template」寫進 recipe 的是**模板本身**（base64 純文字），
不是大圖的路徑。recipe 要能寄給別人；存路徑的話，圖被搬走、被換掉、下個月有人
用了另一張大圖，結果會安靜地變。
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from adept.core.algo import template as algo_template
from adept.core.ingest.imageio import load_gray

from .theme import TOKENS
from .widgets import _qimage_from_uint8

__all__ = ["TemplateDialog", "CellView"]

#: 模板預覽最長邊放大到幾 px（一個 cell 通常只有幾十 px，原尺寸看不清楚）。
_PREVIEW = 260


class CellView(QWidget):
    """把一個 cell 放大顯示，並把使用者標的框畫上去。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cell: Optional[np.ndarray] = None
        self._box = (0.0, 0.0, 1.0, 1.0)
        self.setMinimumSize(_PREVIEW, 140)

    def set_cell(self, cell: Optional[np.ndarray]) -> None:
        self._cell = None if cell is None else np.asarray(cell)
        self.update()

    def set_box(self, norm_rect) -> None:
        self._box = tuple(float(v) for v in norm_rect)
        self.update()

    def has_cell(self) -> bool:
        return self._cell is not None and self._cell.size > 0

    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(TOKENS["image_backdrop"]))
        if not self.has_cell():
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "(no template yet - pick a full-size image)")
            p.end()
            return

        cell = self._cell
        h, w = cell.shape[:2]
        scale = min(self.width() / float(w), self.height() / float(h))
        dw, dh = w * scale, h * scale
        ox, oy = (self.width() - dw) / 2.0, (self.height() - dh) / 2.0

        # 放大時關平滑：SEM 的小圖要看得出方格（同 ImageView 的理由）
        pm = QPixmap.fromImage(_qimage_from_uint8(cell))
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawPixmap(QRectF(ox, oy, dw, dh), pm, QRectF(pm.rect()))

        bx, by, bw, bh = self._box
        p.setPen(QPen(QColor(TOKENS["accent"]), 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(ox + bx * dw, oy + by * dh,
                          max(1.0, bw * dw), max(1.0, bh * dh)))
        p.end()


class TemplateDialog(QDialog):
    """匯入大圖 → 疊模板 → 確認品質 → 寫回卡片。"""

    accepted_template = Signal(str, str)        # (encoded cell, locate_axis)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Build template from a full-size image")
        self.resize(560, 520)
        self.cell: Optional[algo_template.GoldenCell] = None
        self._source_path = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        intro = QLabel(
            "Pick one full-size image from the same inspection recipe. The "
            "repeating cell is measured from it and stored inside your recipe, "
            "so the recipe stays a single file - the image itself is only "
            "needed here.", self)
        intro.setObjectName("paramHint")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        row = QHBoxLayout()
        self.btn_pick = QPushButton("Choose image…", self)
        self.btn_pick.setObjectName("primary")
        self.btn_pick.clicked.connect(self._on_pick)
        row.addWidget(self.btn_pick)
        self.path_label = QLabel("(no image chosen)", self)
        self.path_label.setObjectName("paramHint")
        row.addWidget(self.path_label, 1)
        outer.addLayout(row)

        self.view = CellView(self)
        outer.addWidget(self.view, 1)

        self.report = QLabel("", self)
        self.report.setObjectName("paramHint")
        self.report.setWordWrap(True)
        outer.addWidget(self.report)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Ok).setText("Use this template")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self._set_ready(False)

    # ---- 對外（測試也走這條，不必真的開檔案對話框）------------------------
    def load_image(self, image: Any, name: str = "") -> bool:
        """吃一張大圖，量週期、疊模板、把證據寫上畫面。"""
        arr = np.asarray(image)
        if arr.size == 0:
            self._fail("that image is empty")
            return False

        gc = algo_template.build_golden_cell(arr)
        self.cell = gc
        self._source_path = str(name or "")
        self.path_label.setText(self._source_path or "(image)")

        if gc.cell.size == 0:
            self.view.set_cell(None)
            self._fail("; ".join(gc.warnings) or "no repeating cell was found")
            return False

        self.view.set_cell(gc.cell)
        self.view.set_box((0.0, 0.0, 1.0, 1.0))
        self._set_ready(True)
        self.report.setText(self.summary())
        return True

    def summary(self) -> str:
        """一行摘要 —— 判斷材料全部攤開（測試也讀這個，不必去讀畫素）。"""
        gc = self.cell
        if gc is None or gc.cell.size == 0:
            return ""
        axis = {(True, False): "across", (False, True): "down",
                (True, True): "both ways"}[gc.periodic]
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
        """按得下「Use this template」嗎（用明確狀態，不要問 widget）。"""
        return bool(self._ready)

    # ---- 內部 -------------------------------------------------------------
    def _set_ready(self, ready: bool) -> None:
        self._ready = bool(ready)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self._ready)

    def _fail(self, why: str) -> None:
        self._set_ready(False)
        self.report.setText("Could not build a template: %s." % why)

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
        self.accepted_template.emit(self.encoded(), self.locate_axis())
        self.accept()
