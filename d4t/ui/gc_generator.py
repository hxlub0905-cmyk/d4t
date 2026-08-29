# d4t Studio：從一張 Golden Cell 產一整批資料 — authored 2026-08-28 (F60).
"""**貼一張 GC 進來，產一整批擬真資料。**

使用者 2026-08-28：「你可以製作一個產生器嗎（包含 UI）？如果我以後有其他
類似的 GC 也可以直接貼進去，模擬產生。」關鍵字是**貼**與**其他**：

* **貼** —— 從剪貼簿直接 `Ctrl+V`（截圖就能用），不必先存檔。
  另外三條路一起給：開影像檔、開 recipe（從 `gc2:` 那一格取）、貼字串。
* **其他** —— 所以這個視窗**不認識任何一種 layout**。週期是量出來的，
  缺陷落點也是量出來的（見 `tools/make_lot_from_gc.py`）。換一張 GC、換一個
  世代，這裡一行都不用改。

⚠ **這一支只做「介面」**：量週期、鋪圖、種缺陷、寫兩份 lot 全部住在
`tools/make_lot_from_gc.py`。同一件事只有一個家（`CLAUDE.md` §0）——
而那一家已經有 12 條測試守著。

⚠ **`tools/` 不是安裝進來的套件**，所以是**延遲 import** ＋ 把 repo 的
`tools/` 補進 `sys.path`。那不是這裡發明的例外：`studio.generate_demo_lot`
（合成資料的另一支）走的是同一條路，理由也一樣（順便省掉 tifffile 的成本，
不按這顆鈕的人不必付）。

開法：``python -m d4t simgen``，或 Studio 的工具列（沒有 —— 見下）。

> **刻意不放進 Studio 的工具列。** 那條工具列已經滿到把「Results」擠進 Qt
> 的 overflow 過一次（F48）。這是**造資料**的視窗，不是分析流程的一步，
> 開一個獨立視窗比多一顆鈕誠實。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

from . import theme
from .gc_paint import (
    MODE_BRUSH, MODE_ERASE, MODE_RECT, GcPaintView,
)
from .widgets import to_uint8

__all__ = ["GcGeneratorWindow", "load_backend", "qimage_to_gray"]

#: 預覽用的鋪圖大小（夠看出「缺席的那一根」重複幾次，又不必等）。
PREVIEW = 420


def load_backend():
    """延遲 import `tools/make_lot_from_gc.py`（見模組說明）。"""
    tools_dir = str(Path(__file__).resolve().parents[2] / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import make_lot_from_gc as backend      # noqa: E402 — 刻意延遲
    return backend


# --------------------------------------------------------------------------- #
# 影像轉換
# --------------------------------------------------------------------------- #
def qimage_to_gray(img: QImage) -> Optional[np.ndarray]:
    """剪貼簿上的 QImage → uint8 灰階 2D。空的或壞的回 ``None``。

    ⚠ **一定要先轉成 ``Format_Grayscale8``**。截圖多半是 ARGB32，而它的
    `bits()` 是 BGRA 四個 byte 一組 —— 直接 reshape 成 (h, w) 會拿到
    「寬度四倍、內容是交錯通道」的東西，而那**看起來仍然像一張圖**
    （條紋狀），只是每一個數字都不對。
    """
    if img is None or img.isNull():
        return None
    g = img.convertToFormat(QImage.Format_Grayscale8)
    h, w = g.height(), g.width()
    if h < 4 or w < 4:
        return None
    # bytesPerLine 可能有 padding，逐列切出真正的 w 個 byte。
    buf = np.frombuffer(bytes(g.constBits()), dtype=np.uint8)
    stride = g.bytesPerLine()
    return buf[:h * stride].reshape(h, stride)[:, :w].copy()


def _pixmap(arr: np.ndarray, box: int) -> QPixmap:
    """uint8 2D → 塞得進 ``box`` 見方的 QPixmap（保持長寬比）。"""
    a = np.ascontiguousarray(to_uint8(arr))
    h, w = a.shape
    img = QImage(a.data, w, h, w, QImage.Format_Grayscale8).copy()
    return QPixmap.fromImage(img).scaled(
        box, box, Qt.KeepAspectRatio, Qt.SmoothTransformation)


# --------------------------------------------------------------------------- #
# 背景執行緒
# --------------------------------------------------------------------------- #
class _GenWorker(QThread):
    """跑 `generate()`。**不在 GUI 執行緒跑** —— 50 張 1000² 要好幾秒。"""

    tick = Signal(int, int)
    done = Signal(object, str)          # (結果 dict 或 None, 訊息)

    def __init__(self, backend, kwargs: Dict[str, Any], parent=None):
        super().__init__(parent)
        self._backend = backend
        self._kwargs = dict(kwargs)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:               # noqa: D102 - Qt hook
        def progress(i: int, n: int) -> bool:
            self.tick.emit(int(i), int(n))
            return not self._stop
        try:
            out = self._backend.generate(progress=progress, **self._kwargs)
        except KeyboardInterrupt:
            self.done.emit(None, "Stopped — nothing was written.")
        except Exception as e:           # noqa: BLE001 — 講出來，不要吞掉
            self.done.emit(None, "Failed: %s" % e)
        else:
            self.done.emit(out, "")


# --------------------------------------------------------------------------- #
# 主視窗
# --------------------------------------------------------------------------- #
class GcGeneratorWindow(QMainWindow):
    """貼一張 GC → 看鋪出來長怎樣 → 產兩份 lot。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simulate a lot from a Golden Cell — d4t")
        self._gc: Optional[np.ndarray] = None
        self._worker: Optional[_GenWorker] = None
        self._backend = None

        root = QWidget(self)
        self.setCentralWidget(root)
        grid = QGridLayout(root)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(10)

        grid.addWidget(self._source_box(), 0, 0)
        grid.addWidget(self._period_box(), 1, 0)
        grid.addWidget(self._preview_box(), 0, 1, 2, 1)
        grid.addWidget(self._params_box(), 2, 0)
        grid.addWidget(self._run_box(), 2, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(1, 1)
        self.resize(980, 760)
        self._sync()

    # -- 版面 ---------------------------------------------------------------
    def _source_box(self) -> QWidget:
        box = QGroupBox("1 · The Golden Cell", self)
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self.btn_paste = QPushButton("Paste image  (Ctrl+V)", box)
        self.btn_paste.setToolTip("Paste a Golden Cell from the clipboard — a screenshot works")
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        self.btn_open = QPushButton("Open image…", box)
        self.btn_open.clicked.connect(self.open_image)
        self.btn_recipe = QPushButton("Open recipe…", box)
        self.btn_recipe.setToolTip("Take it from a recipe's template field (the gc2:… string)")
        self.btn_recipe.clicked.connect(self.open_recipe)
        for b in (self.btn_paste, self.btn_open, self.btn_recipe):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        lay.addWidget(QLabel("…or paste the gc2: string here:", box))
        self.txt_gc = QPlainTextEdit(box)
        self.txt_gc.setPlaceholderText("gc2:205x73:205x73:eJx…")
        self.txt_gc.setMaximumHeight(56)
        self.txt_gc.textChanged.connect(self._gc_text_changed)
        lay.addWidget(self.txt_gc)

        self.lbl_gc = QLabel("No Golden Cell yet", box)
        self.lbl_gc.setAlignment(Qt.AlignCenter)
        self.lbl_gc.setMinimumHeight(120)
        self.lbl_gc.setFrameShape(QFrame.StyledPanel)
        lay.addWidget(self.lbl_gc)
        self.lbl_gc_info = QLabel("", box)
        self.lbl_gc_info.setWordWrap(True)
        lay.addWidget(self.lbl_gc_info)
        return box

    def _period_box(self) -> QWidget:
        box = QGroupBox("2 · Period", self)
        lay = QVBoxLayout(box)
        form = QFormLayout()
        self.sp_px = QDoubleSpinBox(box)
        self.sp_py = QDoubleSpinBox(box)
        for sp in (self.sp_px, self.sp_py):
            sp.setRange(4.0, 100000.0)
            sp.setDecimals(2)
            sp.setSingleStep(0.5)
            sp.valueChanged.connect(self._refresh_preview)
        form.addRow("Across (px)", self.sp_px)
        form.addRow("Down (px)", self.sp_py)
        lay.addLayout(form)
        self.btn_measure = QPushButton("Measure again", box)
        self.btn_measure.clicked.connect(self._measure)
        lay.addWidget(self.btn_measure)
        self.lbl_warn = QLabel("", box)
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setObjectName("hint")
        lay.addWidget(self.lbl_warn)
        lay.addStretch(1)
        return box

    def _preview_box(self) -> QWidget:
        """畫「缺陷可能在哪」的那一塊 ＋ 鋪出來的預覽（F61）。

        **畫在一個週期上就等於畫在每一個重複上**（使用者：「反正都是回推」），
        所以塗的是 GC 那張小圖，而下面的預覽即時顯示它鋪開之後的樣子。
        """
        box = QGroupBox("3 · Where defects can appear", self)
        lay = QVBoxLayout(box)

        tools = QHBoxLayout()
        self.grp_mode = QButtonGroup(box)
        self.rb_brush = QRadioButton("Brush", box)
        self.rb_rect = QRadioButton("Rectangle", box)
        self.rb_erase = QRadioButton("Erase", box)
        self.rb_brush.setChecked(True)
        for rb, mode in ((self.rb_brush, MODE_BRUSH), (self.rb_rect, MODE_RECT),
                         (self.rb_erase, MODE_ERASE)):
            self.grp_mode.addButton(rb)
            rb.toggled.connect(
                lambda on, m=mode: on and self.paint.set_mode(m))
            tools.addWidget(rb)
        tools.addSpacing(12)
        tools.addWidget(QLabel("Size", box))
        self.sl_brush = QSlider(Qt.Horizontal, box)
        self.sl_brush.setRange(0, 12)
        self.sl_brush.setValue(2)
        self.sl_brush.setMaximumWidth(110)
        self.sl_brush.valueChanged.connect(
            lambda v: self.paint.set_radius(int(v)))
        tools.addWidget(self.sl_brush)
        tools.addStretch(1)
        lay.addLayout(tools)

        self.paint = GcPaintView(box)
        self.paint.setMinimumHeight(150)
        self.paint.changed.connect(self._refresh_preview)
        lay.addWidget(self.paint, 1)

        row = QHBoxLayout()
        self.btn_auto = QPushButton("Fill the inner spaces", box)
        self.btn_auto.setToolTip(
            "Start from the boundaries it found by itself, then edit")
        self.btn_auto.clicked.connect(self._seed_auto)
        self.btn_clear = QPushButton("Clear", box)
        self.btn_clear.clicked.connect(self.paint.clear)
        row.addWidget(self.btn_auto)
        row.addWidget(self.btn_clear)
        row.addStretch(1)
        lay.addLayout(row)

        self.lbl_prev = QLabel("Paste a Golden Cell to see this", box)
        self.lbl_prev.setAlignment(Qt.AlignCenter)
        self.lbl_prev.setMinimumSize(PREVIEW, 210)
        self.lbl_prev.setFrameShape(QFrame.StyledPanel)
        lay.addWidget(self.lbl_prev, 1)
        self.lbl_sites = QLabel("", box)
        lay.addWidget(self.lbl_sites)
        return box

    def _seed_auto(self) -> None:
        """把自動量到的 inner space 塗進去 —— 從一張白紙開始畫太難。"""
        if self._gc is None:
            return
        self.paint.seed_from_sites(self._be().inner_space_sites(self._gc),
                                   radius=max(1, self.sl_brush.value()))

    def _params_box(self) -> QWidget:
        box = QGroupBox("4 · How much to make", self)
        form = QFormLayout(box)
        self.sp_images = QSpinBox(box); self.sp_images.setRange(1, 5000)
        self.sp_images.setValue(50)
        self.sp_size = QSpinBox(box); self.sp_size.setRange(64, 8192)
        self.sp_size.setValue(1000); self.sp_size.setSingleStep(100)
        self.sp_defects = QSpinBox(box); self.sp_defects.setRange(1, 200000)
        self.sp_defects.setValue(3000)
        self.sp_patch = QSpinBox(box); self.sp_patch.setRange(16, 1024)
        self.sp_patch.setValue(81)
        self.sp_real = QSpinBox(box); self.sp_real.setRange(0, 100)
        self.sp_real.setValue(50); self.sp_real.setSuffix(" %")
        self.sp_noise = QDoubleSpinBox(box); self.sp_noise.setRange(0.0, 60.0)
        self.sp_noise.setValue(6.0)
        self.sp_seed = QSpinBox(box); self.sp_seed.setRange(0, 10 ** 6)
        self.sp_seed.setValue(11)
        form.addRow("RSEM images", self.sp_images)
        form.addRow("Image size (px)", self.sp_size)
        form.addRow("Patches (defects)", self.sp_defects)
        form.addRow("Patch size (px)", self.sp_patch)
        form.addRow("Real defects", self.sp_real)
        form.addRow("Noise σ", self.sp_noise)
        form.addRow("Seed", self.sp_seed)
        return box

    def _run_box(self) -> QWidget:
        box = QGroupBox("5 · Write it out", self)
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self.ed_out = QLineEdit(box)
        self.ed_out.setPlaceholderText("Output folder…")
        btn = QPushButton("Browse…", box)
        btn.clicked.connect(self._browse)
        row.addWidget(self.ed_out, 1)
        row.addWidget(btn)
        lay.addLayout(row)

        self.btn_go = QPushButton("Generate", box)
        self.btn_go.setObjectName("primary")
        self.btn_go.clicked.connect(self._go)
        self.btn_stop = QPushButton("Stop", box)
        self.btn_stop.clicked.connect(self._stop)
        run = QHBoxLayout()
        run.addWidget(self.btn_go, 1)
        run.addWidget(self.btn_stop)
        lay.addLayout(run)

        self.bar = QProgressBar(box)
        self.bar.setVisible(False)
        lay.addWidget(self.bar)
        self.lbl_result = QLabel("", box)
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.lbl_result)
        lay.addStretch(1)
        return box

    # -- GC 來源 -------------------------------------------------------------
    def paste_from_clipboard(self) -> bool:
        """`Ctrl+V`：剪貼簿上的圖或 `gc2:` 字串都吃。"""
        cb = QGuiApplication.clipboard()
        arr = qimage_to_gray(cb.image())
        if arr is not None:
            return self.set_gc(arr, "pasted image")
        text = str(cb.text() or "").strip()
        if text[:4] in ("gc1:", "gc2:"):
            self.txt_gc.setPlainText(text)
            return self._gc is not None
        self._say("The clipboard holds neither an image nor a gc2: string.")
        return False

    def keyPressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.matches(getattr(e, "Paste", None) or 0) or (
                e.key() == Qt.Key_V and e.modifiers() & Qt.ControlModifier):
            if not self.txt_gc.hasFocus():
                self.paste_from_clipboard()
                return
        super().keyPressEvent(e)

    def open_image(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a Golden Cell image", "",
            "Images (*.png *.tif *.tiff *.bmp *.jpg);;All files (*)")
        if not path:
            return False
        img = QImage(path)
        arr = qimage_to_gray(img)
        if arr is None:
            self._say("Could not read that image file.")
            return False
        return self.set_gc(arr, os.path.basename(path))

    def open_recipe(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a recipe", "", "Recipe (*.json);;All files (*)")
        if not path:
            return False
        try:
            arr = self._be().load_gc(recipe_path=path)
        except SystemExit as e:              # load_gc 用 SystemExit 講話
            self._say(str(e))
            return False
        except Exception as e:               # noqa: BLE001
            self._say("Could not read that recipe: %s" % e)
            return False
        return self.set_gc(arr, os.path.basename(path))

    def _gc_text_changed(self) -> None:
        text = self.txt_gc.toPlainText().strip()
        if text[:4] not in ("gc1:", "gc2:"):
            return
        from show_template import decode_template      # tools/，已在 path 上
        self._be()
        got = decode_template(text)
        if got is None:
            self._say("That string will not decode — wrong format, or truncated on the way in.")
            return
        px, w, h, _ = got
        self.set_gc(np.frombuffer(px, dtype=np.uint8).reshape(h, w).copy(),
                    "pasted gc2: string")

    def set_gc(self, arr: np.ndarray, where: str = "") -> bool:
        """換一張 GC：畫出來、量週期、更新預覽。"""
        if arr is None or arr.ndim != 2 or min(arr.shape) < 8:
            self._say("That image is too small to show any repeat.")
            return False
        self._gc = np.ascontiguousarray(arr.astype(np.uint8))
        self.lbl_gc.setPixmap(_pixmap(self._gc, 260))
        # 畫布跟著換（它會把遮罩清掉 —— 換了圖案，畫在舊圖案上的位置沒有意義），
        # 然後**預先塗上自動量到的那些**：從一張白紙開始畫太難，使用者要改的
        # 是一份已經接近的東西。
        self.paint.set_gc(self._gc)
        h, w = self._gc.shape
        self.lbl_gc_info.setText(
            "%s — %d×%d, grey %d–%d" % (where or "GC", w, h,
                                       int(self._gc.min()), int(self._gc.max())))
        self._measure()
        self._seed_auto()
        return True

    # -- 週期 ---------------------------------------------------------------
    def _measure(self) -> None:
        if self._gc is None:
            return
        px, py = self._be().periods(self._gc)
        for sp, v in ((self.sp_px, px), (self.sp_py, py)):
            sp.blockSignals(True)
            sp.setValue(float(v))
            sp.blockSignals(False)
        h, w = self._gc.shape
        # 不到兩個週期寬的 GC 量不準是**原理上**的事，見 backend 的說明。
        thin = [name for name, span, n in (("across", px, w), ("down", py, h))
                if n < 2.0 * span]
        self.lbl_warn.setText(
            # ⚠ 這裡是 QLabel 不是 Markdown —— 星號會原樣印出來。
            ("⚠ This cell is under two periods wide %s, so the measured "
             "number may or may not be right — telling them apart needs two "
             "of the absent positions in view. If you know the answer, type "
             "it above." % " and ".join(thin)) if thin else
            "Measured. Type over it to change — a multiple tiles just as well, the number does not have to be the smallest.")
        self._refresh_preview()

    # -- 預覽 ---------------------------------------------------------------
    def _refresh_preview(self) -> None:
        if self._gc is None:
            self._sync()
            return
        be = self._be()
        px, py = float(self.sp_px.value()), float(self.sp_py.value())
        big = be.tile(self._gc, PREVIEW, PREVIEW, px, py)
        shown = to_uint8(big)
        # **使用者塗的那一塊也照同一個週期鋪開** —— 那正是「回推」：他在一個
        # 週期上畫一筆，大圖上每一個重複都會有。用的是跟 `tile` 同一組
        # (px, py)，所以畫面上看到的就是 `generate` 會種的地方。
        mask = self.paint.mask()
        n_px = 0
        if mask is not None and mask.any():
            n_px = int(mask.sum())
            gh, gw = mask.shape
            tiled = np.zeros((PREVIEW, PREVIEW), dtype=bool)
            gy = 0.0
            while gy < PREVIEW:
                gx = 0.0
                while gx < PREVIEW:
                    y0, x0 = int(round(gy)), int(round(gx))
                    hh = min(gh, PREVIEW - y0)
                    ww = min(gw, PREVIEW - x0)
                    if hh > 0 and ww > 0:
                        tiled[y0:y0 + hh, x0:x0 + ww] |= mask[:hh, :ww]
                    gx += px
                gy += py
            shown = shown.copy()
            # 塗到的地方提亮而不是塗白：底下的圖案要看得見，使用者是**對著
            # 圖案**在判斷自己塗對了沒有。
            shown[tiled] = np.clip(shown[tiled].astype(np.int16) + 70, 0, 255
                                   ).astype(np.uint8)
        self.lbl_prev.setPixmap(_pixmap(shown, PREVIEW))
        self.lbl_sites.setText(
            "%d pixels painted — that is where defects can land"
            % n_px if n_px else
            "Nothing painted yet — draw where defects can appear, "
            "or press “Fill the inner spaces”")
        self._sync()

    # -- 產生 ---------------------------------------------------------------
    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Where to write")
        if path:
            self.ed_out.setText(path)

    def _go(self) -> None:
        if self._gc is None or not self.ed_out.text().strip():
            return
        kwargs = dict(
            out_dir=self.ed_out.text().strip(), gc=self._gc,
            images=int(self.sp_images.value()), size=int(self.sp_size.value()),
            defects=int(self.sp_defects.value()),
            patch=int(self.sp_patch.value()),
            real_frac=float(self.sp_real.value()) / 100.0,
            noise=float(self.sp_noise.value()), seed=int(self.sp_seed.value()),
            period_x=float(self.sp_px.value()),
            period_y=float(self.sp_py.value()),
            sites=self._be().sites_from_mask(self.paint.mask()))
        self.bar.setRange(0, int(self.sp_images.value()))
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self.lbl_result.setText("")
        self._worker = _GenWorker(self._be(), kwargs, self)
        self._worker.tick.connect(self._on_tick)
        self._worker.done.connect(self._on_done)
        self._worker.start()
        self._sync()

    def _stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()

    def _on_tick(self, i: int, n: int) -> None:
        self.bar.setValue(int(i))

    def _on_done(self, out: Optional[Dict[str, Any]], msg: str) -> None:
        self.bar.setVisible(False)
        self._worker = None
        if out is None:
            self.lbl_result.setText(msg)
        else:
            self.lbl_result.setText(
                "✓ %d RSEM images (%s)\n✓ %d patches (%s)\n\n"
                "⚠ A Golden Cell may be fab pattern, so this data is as "
                "sensitive as the original images — do not commit it."
                % (len(out["rsem_images"]), out["rsem_klarf"],
                   out["patch_count"], out["patch_klarf"]))
        self._sync()

    # -- 雜項 ---------------------------------------------------------------
    def _be(self):
        if self._backend is None:
            self._backend = load_backend()
        return self._backend

    def _say(self, msg: str) -> None:
        self.lbl_result.setText(msg)

    def _sync(self) -> None:
        """按鈕的狀態只從**明確的狀態**推導（不問 widget，見 `PITFALLS.md`）。"""
        busy = self._worker is not None
        ready = (self._gc is not None and bool(self.ed_out.text().strip())
                 and self.paint.painted_pixels() > 0)
        self.btn_go.setEnabled(ready and not busy)
        self.btn_stop.setEnabled(busy)
        for b in (self.btn_paste, self.btn_open, self.btn_recipe,
                  self.btn_measure, self.btn_auto, self.btn_clear):
            b.setEnabled(not busy)
        self.paint.setEnabled(not busy)

    def closeEvent(self, e) -> None:         # noqa: D102 - Qt hook
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(3000)
        super().closeEvent(e)


def run(argv=None) -> int:
    """``python -m d4t simgen`` 的進入點。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(list(argv or []))
    theme.apply_theme(app)
    win = GcGeneratorWindow()
    win.show()
    return int(app.exec())
