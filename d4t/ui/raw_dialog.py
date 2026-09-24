# `.raw` 的版面一次填完、當場看得到 — authored 2026-09-24.
"""**`.raw` 要怎麼讀：一張表單＋即時預覽。**

`.raw` 裡沒有任何一個 byte 在講寬高或位元深度（見 `core/ingest/rawfile.py`），
所以檔案大小推不出答案時非問不可。以前那一段是**連跳四個小對話框**（寬 → 高 →
檔頭 → 位元深度），全部填完才讀檔，而填錯的下場是回到第一格重來 —— 或者更糟，
讀出一張斜掉的圖。

這一支把四格放在同一個畫面上，旁邊兩個常駐的回答：

1. **對不對得上檔案大小**（逐位元組；對不上就講差多少）。這是「填錯了」最常見
   的樣子，所以沒對上之前 OK 鈕是灰的 —— `read_raw` 反正也會拒讀。
2. **照這組設定讀出來長什麼樣**。大小對得上不代表填對（寬高對調、檔頭多算幾
   byte 都湊得出同一個大小），而那種錯一眼就看得出來：圖會是斜紋。

⚠ 預覽**只讀縮圖需要的那幾列**（`np.memmap` 加跨步切片），不整張讀進來 ——
一張 16k × 16k 的 16-bit `.raw` 是 512 MB，而使用者每按一次上下鍵都會重畫。
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from d4t.core.ingest.rawfile import RawSpec

from . import strings
from .image_view import _qimage_from_uint8, to_uint8

__all__ = ["RawLayoutDialog", "PREVIEW_SIDE", "MAX_SIDE"]

#: 預覽框的邊長（px）。縮圖只讀這麼多列／行。
PREVIEW_SIDE = 280

#: 手填寬高的上限（純粹是個欄位上界，不是產品限制）。
MAX_SIDE = 65536


class RawLayoutDialog(QDialog):
    """寬／高／檔頭／位元深度一次填，底下即時告訴你對不對。

    ``initial`` 給了就從那一組開始（通常是檔案大小推出來的第一個猜測）。
    接受之後用 :meth:`spec` 拿答案。
    """

    def __init__(self, probe: str, initial: Optional[RawSpec] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._probe = str(probe)
        self._size = os.path.getsize(self._probe)
        self.setWindowTitle(strings.tr("How is this .raw laid out?"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        intro = QLabel(strings.tr(
            "%s is %d bytes. A .raw file does not say its own size, so fill "
            "it in - the picture below shows the file read this way."
        ) % (os.path.basename(self._probe), self._size), self)
        intro.setWordWrap(True)
        lay.addWidget(intro)

        row = QHBoxLayout()
        form = QFormLayout()
        self.sp_width = QSpinBox(self)
        self.sp_width.setRange(1, MAX_SIDE)
        self.sp_height = QSpinBox(self)
        self.sp_height.setRange(1, MAX_SIDE)
        self.sp_header = QSpinBox(self)
        self.sp_header.setRange(0, max(0, min(self._size, 2 ** 31 - 1)))
        self.cb_bits = QComboBox(self)
        self.cb_bits.addItem(strings.tr("16-bit (2 bytes per pixel)"), 16)
        self.cb_bits.addItem(strings.tr("8-bit (1 byte per pixel)"), 8)
        form.addRow(strings.tr("Width (pixels across)"), self.sp_width)
        form.addRow(strings.tr("Height (pixels down)"), self.sp_height)
        form.addRow(strings.tr("Header (bytes to skip)"), self.sp_header)
        form.addRow(strings.tr("Bit depth"), self.cb_bits)
        self.btn_fit_height = QPushButton(
            strings.tr("Height from file size"), self)
        self.btn_fit_height.setProperty("variant", "secondary")
        self.btn_fit_height.setToolTip(strings.tr(
            "Work out the height from the width, header and bit depth "
            "you filled in."))
        self.btn_fit_height.clicked.connect(self.fit_height)
        form.addRow("", self.btn_fit_height)
        row.addLayout(form)

        self.preview = QLabel(self)
        self.preview.setFixedSize(PREVIEW_SIDE, PREVIEW_SIDE)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setObjectName("placeholder")
        row.addWidget(self.preview)
        lay.addLayout(row)

        self.lbl_check = QLabel(self)
        self.lbl_check.setObjectName("paramHint")
        self.lbl_check.setWordWrap(True)
        lay.addWidget(self.lbl_check)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.btn_ok = self.buttons.button(QDialogButtonBox.Ok)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        start = initial or RawSpec(width=1024, height=1024)
        self.sp_width.setValue(int(start.width))
        self.sp_height.setValue(int(start.height))
        self.sp_header.setValue(int(start.header))
        self.cb_bits.setCurrentIndex(0 if int(start.bits) == 16 else 1)
        for sp in (self.sp_width, self.sp_height, self.sp_header):
            sp.valueChanged.connect(self._refresh)
        self.cb_bits.currentIndexChanged.connect(self._refresh)
        self._refresh()

    # ---- 對外 -------------------------------------------------------------
    def spec(self) -> RawSpec:
        return RawSpec(width=self.sp_width.value(),
                       height=self.sp_height.value(),
                       header=self.sp_header.value(),
                       bits=int(self.cb_bits.currentData()))

    def matches(self) -> bool:
        return self.spec().nbytes() == self._size

    def fit_height(self) -> None:
        """用寬、檔頭、位元深度把高算出來（除得盡才填，除不盡就講）。"""
        s = self.spec()
        per_row = s.width * (1 if s.bits == 8 else 2)
        left = self._size - s.header
        if left > 0 and left % per_row == 0 and left // per_row <= MAX_SIDE:
            self.sp_height.setValue(left // per_row)
        else:
            self._say(strings.tr(
                "No whole number of rows fits: %d bytes after the header is "
                "not a multiple of %d bytes per row. Check the width, the "
                "header or the bit depth.") % (left, per_row), error=True)

    # ---- 內部 -------------------------------------------------------------
    def _say(self, text: str, error: bool) -> None:
        self.lbl_check.setText(text)
        self.lbl_check.setProperty("error", "true" if error else "false")
        self.lbl_check.style().unpolish(self.lbl_check)
        self.lbl_check.style().polish(self.lbl_check)

    def _refresh(self, *_args) -> None:
        s = self.spec()
        want = s.nbytes()
        ok = want == self._size
        self.btn_ok.setEnabled(ok)
        if ok:
            self._say(strings.tr(
                "✓ Matches the file size. If the picture shows diagonal "
                "stripes, the width is wrong even though the size fits."),
                error=False)
        else:
            self._say(strings.tr(
                "This layout needs %d bytes, but the file is %d bytes "
                "(%+d). The width, height, header or bit depth is off.")
                % (want, self._size, self._size - want), error=True)
        self._draw_preview(s if ok else None)

    def _draw_preview(self, s: Optional[RawSpec]) -> None:
        if s is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(strings.tr("No preview until the size fits"))
            return
        try:
            mm = np.memmap(self._probe, dtype=np.dtype(s.dtype), mode="r",
                           offset=int(s.header),
                           shape=(int(s.height), int(s.width)))
            step = max(1, -(-max(s.height, s.width) // PREVIEW_SIDE))
            thumb = np.array(mm[::step, ::step])
            del mm
        except (OSError, ValueError) as e:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(strings.tr("Could not read the file: %s") % e)
            return
        self.preview.setText("")
        self.preview.setPixmap(QPixmap.fromImage(
            _qimage_from_uint8(to_uint8(thumb))).scaled(
                PREVIEW_SIDE, PREVIEW_SIDE, Qt.KeepAspectRatio,
                Qt.SmoothTransformation))
