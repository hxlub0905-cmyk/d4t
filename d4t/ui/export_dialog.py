# d4t Studio 輸出精靈 — authored 2026-07-28 (M5-3).
"""``ExportDialog`` —— 把一批試跑/全跑結果寫成 KLARF / 報表 / 疊圖。

這是 M5 的「出口」：Gallery 與直方圖讓工程師**看**懂這批結果，這支對話框讓
他把結果**交出去**（回寫 KLARF 給 review 站、出報表給主管、出疊圖當證據）。

三個區塊
--------

(a) **KLARF 寫回** —— 三選一，每個模式都附一行白話：

    ==========================  ====================================================
    ``就地改欄（無損）``          只改既有欄位（CLASSNUMBER / ROUGHBINNUMBER /
    inplace                     FINEBINNUMBER / DSIZE），沒被改到的 byte 與原檔
                                逐位元組相同。**這份 KLARF 沒有的欄位，控制項會
                                變灰並寫明原因**（絕不默默略過）。
    ``另存新檔（含分數欄）``      追加 ADCSCORE / ADCCLASS（可再選特徵欄），
    annotate                    影像區塊仍留在列尾。
    ``Top-N 另存``               依分數由高到低只留前 N 顆（或 >= 門檻），
    topn                        可重新編號 DEFECTID。
    ==========================  ====================================================

    ★ **「預覽變更」是硬性關卡** ★ ——「寫出」在按過預覽之前是灰的。預覽走
    :func:`~d4t.core.export.plan_writeback`（乾跑，不寫任何檔案），把
    :class:`~d4t.core.export.WriteBackPlan` 翻成白話（會改幾列、動到哪些欄、
    新增哪些欄、輸出幾列）再加上檔案健檢的 ✓ / △ / ✗ 三種行。任何一個設定被
    改動 → 計畫作廢、「寫出」立刻變回灰的（使用者看到的一定是**這一版設定**
    的後果）。

(b) **報表** —— CSV（feature vector）／ Excel（三頁報告），各自的輸出路徑。

(c) **Overlay 影像** —— 依分數由高到低取前 N 顆，逐顆
    :func:`~d4t.core.export.render_overlay` → :func:`~d4t.core.export.write_png`。

執行緒
------
所有實際寫檔都在 :class:`ExportWorker`（沿用 ``workers.py`` 的一次性 QThread
樣式）裡跑，GUI 不卡；進度條吃 ``progress(done, total, 說明)``。
真正的工作是 Qt-free 的模組層函式 :func:`run_export_job`，所以測試可以完全
同步地跑它（``dialog.run_export(sync=True)``）。

錯誤
----
:class:`~d4t.core.export.ExportError` 一律翻成一個看得懂的訊息框
（互動路徑）或 :meth:`ExportDialog.error_text`（同步路徑）——
**永遠不讓使用者看到 traceback**（推廣鐵則）。
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from d4t.core.export import (
    ExportError,
    apply_writeback,
    feature_keys,
    pick_overlay_results,
    plan_writeback,
    render_overlay,
    write_csv,
    write_excel,
    write_png,
)

from .widgets import apply_button_cursors
from .workers import _ThreadedWorker  # 同一套一次性 QThread 樣式（別另外發明一種）

__all__ = [
    "ExportDialog", "ExportWorker", "run_export_job",
    "INPLACE_COLUMNS", "MODES", "MODE_LABELS", "MODE_HELP",
    "OVERLAY_PREFIX", "DEFAULT_SIZE_FEATURE", "DEFAULT_SIZE_SCALE",
]

#: 寫回模式（順序 = 畫面上的順序）。
MODES = ("inplace", "annotate", "topn")

MODE_LABELS = {
    "inplace": "Edit in place (lossless)",
    "annotate": "Save as new file (with score columns)",
    "topn": "Top-N as new file",
}

MODE_HELP = {
    "inplace": "Only touches columns this KLARF already has; every other byte is identical to the original.",
    "annotate": "Writes a new KLARF with extra ADCSCORE / ADCCLASS columns; the original is untouched.",
    "topn": "Writes a new KLARF keeping only the highest-scoring defects (or those above a threshold).",
}

#: inplace 模式支援的四個目標欄位（實際有沒有這一欄，看載入的 KLARF）。
INPLACE_COLUMNS = ("CLASSNUMBER", "ROUGHBINNUMBER", "FINEBINNUMBER", "DSIZE")

#: 這兩欄是「bin 寫去哪」的二選一（core 的 inplace 一次只吃一個 bin 欄）。
_BIN_COLUMNS = ("ROUGHBINNUMBER", "FINEBINNUMBER")

#: DSIZE 預設寫哪個特徵。
#:
#: pipeline 全程用 pixel（2026-07-30 決定，見 ``d4t/core/steps/cd.py``），
#: 所以這裡預設也是 px 的那個特徵；要寫成物理尺寸的話由使用者在下面那格填
#: nm/px。以前預設是 ``cd_x_nm``，而那個值**每一顆都是 0** —— 它有來源了才
#: 該回來當預設。
DEFAULT_SIZE_FEATURE = "cd_x_px"

#: DSIZE 的換算係數預設（1 = 原樣寫 pixel，不換算）。
DEFAULT_SIZE_SCALE = 1.0

#: 疊圖檔名前綴。
OVERLAY_PREFIX = "overlay_"

_NO_BIN_COL = "(do not write a bin column)"
_LEVEL_MARK = {"error": "✗", "warn": "△", "info": "✓"}


# --------------------------------------------------------------------------- #
# Qt-free：真正做事的部分（背景執行緒與測試都走這裡）
# --------------------------------------------------------------------------- #
def _safe_name(text: Any) -> str:
    """defect_id → 可以當檔名的字串。"""
    out = []
    for ch in str(text):
        out.append(ch if (ch.isalnum() or ch in "-_") else "_")
    return "".join(out) or "unknown"


def _sources_of(dataset: Any) -> Dict[str, Any]:
    """掛在這份資料上的第二（第三…）份，整理成引擎吃的形狀（F15）。"""
    from d4t.core.ingest import pair_source

    return pair_source.sources_for_run(dataset) if dataset is not None else {}


def _overlay_images(item: Any, recipe: Any, kind: str,
                    sources: Optional[Dict[str, Any]] = None
                    ) -> Tuple[Dict[str, Any], Dict[str, Any], Any]:
    """一顆 defect 的疊圖素材 ``(images, features, blobs)``。

    有 recipe 就跑一次 :func:`~d4t.core.pipeline.run_defect`（``keep_context``），
    這樣 diff / blobs 都在，疊圖才是「機器看到的東西」；跑不出影像（或沒有
    recipe）就退回直接讀原始 channel（test → single → 第一個有的）。
    """
    from d4t.core.pipeline import run_defect     # 延後匯入：對話框開啟才需要

    if recipe is not None and item is not None:
        r = run_defect(recipe, item, str(kind), keep_context=True,
                       sources=dict(sources or {}))
        ctx = getattr(r, "context", None)
        images = dict(getattr(ctx, "images", {}) or {}) if ctx is not None else {}
        if images:
            blobs = (ctx.meta or {}).get("blobs") if ctx is not None else None
            return images, dict(getattr(r, "features", {}) or {}), blobs

    channels = list(getattr(item, "images", {}) or {})
    images = {}
    for ch in channels:
        try:
            images[ch] = item.load(ch)
        except Exception:            # noqa: BLE001 — 單顆讀不出來不該殺掉整批
            continue
    return images, {}, None


def _overlay_label(result: Dict[str, Any]) -> str:
    """疊圖左上角那一行（cv2 的字型沒有中文，這裡刻意只用 ASCII）。"""
    parts = ["#%s" % result.get("defect_id", "?")]
    s = result.get("score")
    if s is not None:
        try:
            parts.append("score=%.3f" % float(s))
        except (TypeError, ValueError):
            pass
    b = result.get("bin")
    if b is not None:
        parts.append("bin=%d" % int(b))
    return "  ".join(parts)


def run_export_job(spec: Dict[str, Any],
                   progress: Optional[Callable[[int, int, str], None]] = None
                   ) -> Dict[str, Any]:
    """真的寫檔（**Qt-free**）。回傳摘要 dict，:class:`ExportError` 直接往外丟。

    ``spec``::

        {
          "klarf":   {"doc":…, "results":[…], "mode":"annotate",
                      "out_path":"…", "opts":{…}}          # 或 None
          "csv":     "path.csv" 或 None,
          "excel":   {"path":…, "recipe":…, "ground_truth":…} 或 None,
          "overlay": {"dir":…, "results":[…], "items":{id: DefectItem},
                      "recipe":…, "kind":"ebi_patch"} 或 None,
          "results": [...]        # csv / excel 用的結果
        }

    回傳 ``{"outputs": [路徑…], "notes": [白話…], "plan": WriteBackPlan|None,
    "n_overlays": int, "n_overlay_failed": int}``。
    """
    spec = dict(spec or {})
    results = list(spec.get("results") or [])
    outputs: List[str] = []
    notes: List[str] = []
    plan = None

    steps = [k for k in ("klarf", "csv", "excel", "overlay") if spec.get(k)]
    total = max(1, len(steps))
    done = 0

    def tick(msg: str) -> None:
        if progress is not None:
            progress(done, total, msg)

    tick("Preparing export…")

    kl = spec.get("klarf")
    if kl:
        tick("Writing KLARF…")
        plan = apply_writeback(kl["doc"], list(kl.get("results") or results),
                               str(kl["mode"]), str(kl["out_path"]),
                               **dict(kl.get("opts") or {}))
        outputs.append(str(kl["out_path"]))
        notes.append("KLARF (%s): %d rows changed, %d rows written."
                     % (MODE_LABELS.get(plan.mode, plan.mode),
                        plan.n_rows_changed, plan.n_rows_out))
        done += 1

    csv_path = spec.get("csv")
    if csv_path:
        tick("Writing CSV…")
        outputs.append(write_csv(results, str(csv_path)))
        notes.append("CSV: %d detail rows." % len(results))
        done += 1

    xl = spec.get("excel")
    if xl:
        tick("Writing Excel…")
        path = write_excel(results, str(xl["path"]),
                           recipe=xl.get("recipe"),
                           ground_truth=xl.get("ground_truth"))
        outputs.append(path)
        notes.append("Excel: Summary / Details / Feature stats worksheets.")
        done += 1

    ov = spec.get("overlay")
    n_ok = n_fail = 0
    if ov:
        rows = list(ov.get("results") or [])
        items = dict(ov.get("items") or {})
        out_dir = str(ov["dir"])
        recipe = ov.get("recipe")
        kind = str(ov.get("kind") or "")
        total = max(1, len(steps) - 1 + len(rows))
        sources = dict(ov.get("sources") or {})
        for i, r in enumerate(rows, 1):
            did = str(r.get("defect_id", ""))
            tick("Overlay %d / %d (#%s)" % (i, len(rows), did))
            item = items.get(did)
            try:
                images, feats, blobs = _overlay_images(item, recipe, kind,
                                                       sources)
                if not images:
                    n_fail += 1
                    continue
                merged = dict(feats)
                merged.update(r.get("features") or {})
                panel = render_overlay(images, merged, blobs=blobs,
                                       label=_overlay_label(r))
                write_png(panel, os.path.join(
                    out_dir, "%s%s.png" % (OVERLAY_PREFIX, _safe_name(did))))
            except ExportError:
                raise
            except Exception:        # noqa: BLE001 — 單顆畫不出來不該殺掉整批
                n_fail += 1
            else:
                n_ok += 1
                done += 1
        outputs.append(out_dir)
        notes.append("Overlays: %d written to %s." % (n_ok, out_dir))
        if n_fail:
            notes.append("Skipped %d defects whose overlay could not be drawn (usually unreadable images)."
                         % n_fail)

    if progress is not None:
        progress(total, total, "Done")
    return {"outputs": outputs, "notes": notes, "plan": plan,
            "n_overlays": n_ok, "n_overlay_failed": n_fail}


# --------------------------------------------------------------------------- #
# 背景工作
# --------------------------------------------------------------------------- #
class ExportWorker(_ThreadedWorker):
    """在背景跑 :func:`run_export_job`。

    訊號：``progress(done, total, 說明)``、``done(dict)``、``failed(str)``。
    失敗訊息已經是白話（:class:`ExportError` 的訊息原樣帶出），UI 直接顯示即可。
    """

    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def start(self, spec: Dict[str, Any]) -> bool:
        """開背景執行緒輸出；已有工作在跑時回傳 False（不排隊）。"""
        if self.is_running():
            return False
        payload = dict(spec or {})

        def emit_progress(d: int, t: int, msg: str) -> None:
            self.progress.emit(int(d), int(t), str(msg))

        def job() -> None:
            try:
                out = run_export_job(payload, emit_progress)
            except ExportError as e:
                self.failed.emit(str(e))
            except Exception as e:      # noqa: BLE001 — UI 邊界，一律翻成訊息
                self.failed.emit("%s: %s" % (type(e).__name__, e))
            else:
                self.done.emit(out)

        self._start_job(job)
        return True


# --------------------------------------------------------------------------- #
# 對話框
# --------------------------------------------------------------------------- #
class ExportDialog(QDialog):
    """輸出精靈（KLARF 寫回 / 報表 / 疊圖）。

    測試友善 API（完全不開檔案對話框、不跳訊息框）::

        dlg = ExportDialog(results, doc=doc, dataset=ds, recipe=recipe)
        dlg.set_mode("inplace")
        dlg.column_control("DSIZE").isEnabled()      # 這份 KLARF 沒這欄 → False
        dlg.column_hint("DSIZE")                     # 為什麼不能選
        dlg.preview_plan()                           # 乾跑 → 計畫書文字
        dlg.plan_text()                              # 白話 + ✓/△/✗
        dlg.btn_write.isEnabled()                    # 預覽成功後才是 True
        dlg.run_export(sync=True)                    # 真的寫（同步）
    """

    #: 輸出完成（不論同步或背景）—— 主視窗接這個更新狀態列。
    exported = Signal(object)

    def __init__(self, results: Sequence[Dict[str, Any]],
                 doc: Any = None, *,
                 dataset: Any = None,
                 recipe: Any = None,
                 ground_truth: Optional[Dict[Any, Any]] = None,
                 default_dir: Optional[str] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export…")
        self.setMinimumSize(720, 560)

        self.results: List[Dict[str, Any]] = list(results or [])
        self.doc = doc
        self.dataset = dataset
        self.recipe = recipe
        self.ground_truth = ground_truth
        self._plan: Any = None
        self._plan_text = ""
        self._error_text = ""
        self._summary: Optional[Dict[str, Any]] = None
        self._interactive = False        # True = 使用者按按鈕（可以跳訊息框）
        # 組介面的過程中 setChecked() 會觸發 toggled，但那時候別的 widget 還沒
        # 生出來 —— 這面旗子讓所有 slot 在組裝期間安靜地跳過。
        self._building = True
        self._col_controls: Dict[str, QAbstractButton] = {}
        self._col_hints: Dict[str, QLabel] = {}

        self._features = feature_keys(self.results)
        self._columns = [str(c) for c in (getattr(doc, "defect_columns", None) or [])]
        self._dir = str(default_dir or self._guess_dir())
        self._stem = self._guess_stem()

        self.worker = ExportWorker(self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)

        self._build_ui()
        self._building = False
        self._sync_mode_pages()
        self._update_write_enabled()

    # ==================================================================== #
    # 預設值
    # ==================================================================== #
    def _guess_dir(self) -> str:
        src = getattr(self.doc, "source_path", None)
        if src:
            return os.path.dirname(os.path.abspath(str(src)))
        return os.getcwd()

    def _guess_stem(self) -> str:
        src = getattr(self.doc, "source_path", None)
        if src:
            return os.path.splitext(os.path.basename(str(src)))[0]
        return "d4t"

    def _default_path(self, suffix: str) -> str:
        return os.path.join(self._dir, self._stem + suffix)

    # ==================================================================== #
    # 介面
    # ==================================================================== #
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        head = QLabel("This batch has %d defect results — what would you like to export?" % len(self.results),
                      self)
        head.setObjectName("paramTitle")
        outer.addWidget(head)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(10)
        lay.addWidget(self._build_klarf_group())
        lay.addWidget(self._build_report_group())
        lay.addWidget(self._build_overlay_group())
        lay.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        outer.addWidget(self.progress_bar)

        self.status_label = QLabel("", self)
        self.status_label.setObjectName("paramHint")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        buttons = QDialogButtonBox(self)
        self.btn_write = QPushButton("Write", self)
        self.btn_write.setObjectName("primary")
        self.btn_write.setToolTip("Unlocked once you have pressed “Preview changes”")
        self.btn_write.clicked.connect(self._on_write_clicked)
        self.btn_close = QPushButton("Close", self)
        self.btn_close.clicked.connect(self.reject)
        buttons.addButton(self.btn_write, QDialogButtonBox.AcceptRole)
        buttons.addButton(self.btn_close, QDialogButtonBox.RejectRole)
        outer.addWidget(buttons)
        apply_button_cursors(self)

    # ---- (a) KLARF ------------------------------------------------------
    def _build_klarf_group(self) -> QWidget:
        box = QGroupBox("(a) Write back to KLARF", self)
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        self.chk_klarf = QCheckBox("Write the ADC verdict back to KLARF", box)
        self.chk_klarf.setChecked(self.doc is not None)
        self.chk_klarf.setEnabled(self.doc is not None)
        if self.doc is None:
            self.chk_klarf.setToolTip("No KLARF loaded — nothing to write back to.")
            hint = QLabel("(No KLARF loaded — use “Open KLARF…” in the main window first)", box)
            hint.setObjectName("paramHint")
            lay.addWidget(self.chk_klarf)
            lay.addWidget(hint)
        else:
            lay.addWidget(self.chk_klarf)
        self.chk_klarf.toggled.connect(self._invalidate_plan)

        self.mode_group = QButtonGroup(box)
        self.mode_buttons: Dict[str, QRadioButton] = {}
        for mode in MODES:
            rb = QRadioButton(MODE_LABELS[mode], box)
            rb.setToolTip(MODE_HELP[mode])
            self.mode_group.addButton(rb)
            self.mode_buttons[mode] = rb
            lay.addWidget(rb)
            help_label = QLabel("    " + MODE_HELP[mode], box)
            help_label.setObjectName("paramHint")
            help_label.setWordWrap(True)
            lay.addWidget(help_label)
            rb.toggled.connect(self._on_mode_toggled)
        self.mode_buttons["inplace"].setChecked(True)

        self.page_inplace = self._build_inplace_page(box)
        self.page_annotate = self._build_annotate_page(box)
        self.page_topn = self._build_topn_page(box)
        for page in (self.page_inplace, self.page_annotate, self.page_topn):
            lay.addWidget(page)

        row = QHBoxLayout()
        row.addWidget(QLabel("Output file", box))
        self.edit_klarf_out = QLineEdit(self._default_path("_adc.001"), box)
        self.edit_klarf_out.setToolTip("Where the new KLARF goes (the original is not overwritten by default)")
        self.edit_klarf_out.textChanged.connect(self._invalidate_plan)
        row.addWidget(self.edit_klarf_out, 1)
        btn = QPushButton("Browse…", box)
        btn.clicked.connect(self._pick_klarf_out)
        row.addWidget(btn)
        lay.addLayout(row)

        prow = QHBoxLayout()
        self.btn_preview = QPushButton("Preview changes", box)
        self.btn_preview.setToolTip("Dry run: shows exactly how many rows and "
                                    "which columns change. “Write” unlocks "
                                    "afterwards.")
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        prow.addWidget(self.btn_preview)
        prow.addStretch(1)
        lay.addLayout(prow)

        self.plan_view = QTextEdit(box)
        self.plan_view.setReadOnly(True)
        self.plan_view.setMinimumHeight(150)
        self.plan_view.setPlaceholderText(
            "Press “Preview changes” to see what this would do (no file is written).")
        lay.addWidget(self.plan_view)
        return box

    def _column_row(self, parent: QWidget, name: str,
                    control: QAbstractButton, what: str) -> QWidget:
        """一列欄位選擇器：控制項 + 白話說明；欄位不存在就變灰並寫明原因。"""
        row = QWidget(parent)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(control)
        hint = QLabel("", row)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        if name in self._columns:
            hint.setText(what)
        else:
            control.setEnabled(False)
            control.setChecked(False)
            hint.setText("This KLARF has no “%s” column — use “Save as new file "
                         "(with score columns)” to add one." % name)
            control.setToolTip(hint.text())
        h.addWidget(hint, 1)
        self._col_controls[name] = control
        self._col_hints[name] = hint
        return row

    def _build_inplace_page(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 2, 2, 2)
        lay.setSpacing(4)

        head = QLabel("Which existing columns should the verdict go into? (none selected = output identical to the original)",
                      page)
        head.setObjectName("paramHint")
        head.setWordWrap(True)
        lay.addWidget(head)

        self.chk_class_col = QCheckBox("CLASSNUMBER", page)
        self.chk_class_col.toggled.connect(self._invalidate_plan)
        lay.addWidget(self._column_row(page, "CLASSNUMBER", self.chk_class_col,
                                       "Write the bin into the class column (the one downstream review stations read most)."))

        self.rb_no_bin_col = QRadioButton(_NO_BIN_COL, page)
        self.rb_no_bin_col.setChecked(True)
        self.rb_no_bin_col.setToolTip("Only one bin column can be written at a time (a limit of the KLARF writer)")
        self.rb_no_bin_col.toggled.connect(self._invalidate_plan)
        lay.addWidget(self.rb_no_bin_col)

        self.bin_col_group = QButtonGroup(page)
        self.bin_col_group.addButton(self.rb_no_bin_col)
        for name, what in (
                ("ROUGHBINNUMBER", "Write the bin into the coarse bin column."),
                ("FINEBINNUMBER", "Write the bin into the fine bin column.")):
            rb = QRadioButton(name, page)
            rb.toggled.connect(self._invalidate_plan)
            self.bin_col_group.addButton(rb)
            lay.addWidget(self._column_row(page, name, rb, what))

        self.chk_size_col = QCheckBox("DSIZE", page)
        self.chk_size_col.toggled.connect(self._invalidate_plan)
        lay.addWidget(self._column_row(
            page, "DSIZE", self.chk_size_col, "Write the measured size feature into the size column."))

        srow = QHBoxLayout()
        srow.addWidget(QLabel("   Size feature", page))
        self.size_feature_combo = QComboBox(page)
        self.size_feature_combo.setToolTip("Which feature value goes into DSIZE")
        for name in (self._features or [DEFAULT_SIZE_FEATURE]):
            self.size_feature_combo.addItem(name)
        if DEFAULT_SIZE_FEATURE in self._features:
            self.size_feature_combo.setCurrentText(DEFAULT_SIZE_FEATURE)
        self.size_feature_combo.currentIndexChanged.connect(self._invalidate_plan)
        srow.addWidget(self.size_feature_combo, 1)
        lay.addLayout(srow)

        # 換算係數：pipeline 量出來的是 pixel，DSIZE 想寫物理尺寸的話，
        # 「一個 pixel 是幾 nm」只有站點自己知道 —— 所以是一格輸入，不是
        # 一個猜出來的值。1 = 原樣寫 pixel。
        krow = QHBoxLayout()
        krow.addWidget(QLabel("   × scale", page))
        self.size_scale_spin = QDoubleSpinBox(page)
        self.size_scale_spin.setDecimals(4)
        self.size_scale_spin.setRange(0.0001, 1e6)
        self.size_scale_spin.setValue(DEFAULT_SIZE_SCALE)
        self.size_scale_spin.setToolTip(
            "Multiplied into the size feature before it is written. Features "
            "are measured in pixels, so enter your nm per pixel to write "
            "nanometres. Leave it at 1 to write pixels.")
        self.size_scale_spin.valueChanged.connect(self._invalidate_plan)
        krow.addWidget(self.size_scale_spin, 1)
        lay.addLayout(krow)

        scale_hint = QLabel(
            "Measurements are in pixels. Enter nm per pixel here if DSIZE "
            "should be in nanometres — 1 writes the pixel value.", page)
        scale_hint.setObjectName("paramHint")
        scale_hint.setWordWrap(True)
        lay.addWidget(scale_hint)
        return page

    def _build_annotate_page(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 2, 2, 2)
        lay.setSpacing(4)

        head = QLabel("Adds two columns: ADCSCORE (score) and ADCCLASS (bin). "
                      "Pick any extra feature columns below.", page)
        head.setObjectName("paramHint")
        head.setWordWrap(True)
        lay.addWidget(head)

        self.feature_list = QListWidget(page)
        self.feature_list.setToolTip("Each ticked feature becomes its own KLARF column")
        self.feature_list.setMaximumHeight(140)
        for name in self._features:
            it = QListWidgetItem(str(name), self.feature_list)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
        if not self._features:
            self.feature_list.setEnabled(False)
            empty = QLabel("(this batch has no features to pick from)", page)
            empty.setObjectName("paramHint")
            lay.addWidget(self.feature_list)
            lay.addWidget(empty)
        else:
            lay.addWidget(self.feature_list)
        self.feature_list.itemChanged.connect(lambda _i: self._invalidate_plan())
        return page

    def _build_topn_page(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 2, 2, 2)
        lay.setSpacing(4)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Keep top", page))
        self.spin_topn = QSpinBox(page)
        self.spin_topn.setRange(0, 1000000)
        self.spin_topn.setValue(min(100, max(1, len(self.results))))
        self.spin_topn.setToolTip("Keep this many defects by descending score; 0 = use the score threshold below instead")
        self.spin_topn.valueChanged.connect(self._invalidate_plan)
        row1.addWidget(self.spin_topn)
        row1.addStretch(1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_min_score = QCheckBox("Use a score threshold (>=) instead", page)
        self.chk_min_score.setToolTip("Tick to keep every defect whose score is greater than or equal to this value")
        self.chk_min_score.toggled.connect(self._invalidate_plan)
        row2.addWidget(self.chk_min_score)
        self.spin_min_score = QDoubleSpinBox(page)
        self.spin_min_score.setDecimals(3)
        self.spin_min_score.setRange(-1e9, 1e9)
        self.spin_min_score.valueChanged.connect(self._invalidate_plan)
        row2.addWidget(self.spin_min_score)
        row2.addStretch(1)
        lay.addLayout(row2)

        self.chk_renumber = QCheckBox("Renumber DEFECTID as 1, 2, 3…", page)
        self.chk_renumber.setChecked(True)
        self.chk_renumber.setToolTip(
            "Keeping a subset leaves gaps in the ids; tick to renumber. Note: "
            "TIFF page numbers are not renumbered (this tool never touches the "
            "original images).")
        self.chk_renumber.toggled.connect(self._invalidate_plan)
        lay.addWidget(self.chk_renumber)

        self.chk_topn_annotate = QCheckBox("Also add ADCSCORE / ADCCLASS columns", page)
        self.chk_topn_annotate.setChecked(True)
        self.chk_topn_annotate.toggled.connect(self._invalidate_plan)
        lay.addWidget(self.chk_topn_annotate)
        return page

    # ---- (b) 報表 --------------------------------------------------------
    def _build_report_group(self) -> QWidget:
        box = QGroupBox("(b) Reports", self)
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        self.chk_csv = QCheckBox("CSV details (one row per defect, all features)", box)
        self.chk_csv.toggled.connect(self._on_any_output_toggled)
        lay.addWidget(self.chk_csv)
        self.edit_csv_out, csv_row = self._path_row(
            box, self._default_path("_features.csv"), "Choose where the CSV goes",
            self._pick_csv_out)
        lay.addLayout(csv_row)

        self.chk_excel = QCheckBox("Excel report (Summary / Details / Feature stats)", box)
        self.chk_excel.toggled.connect(self._on_any_output_toggled)
        lay.addWidget(self.chk_excel)
        self.edit_excel_out, xl_row = self._path_row(
            box, self._default_path("_report.xlsx"), "Choose where the Excel file goes",
            self._pick_excel_out)
        lay.addLayout(xl_row)
        return box

    # ---- (c) 疊圖 --------------------------------------------------------
    def _build_overlay_group(self) -> QWidget:
        box = QGroupBox("(c) Overlay images", self)
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        self.chk_overlay = QCheckBox("Write overlay PNGs", box)
        self.chk_overlay.toggled.connect(self._on_any_output_toggled)
        lay.addWidget(self.chk_overlay)

        row = QHBoxLayout()
        row.addWidget(QLabel("Draw at most", box))
        self.spin_overlay_limit = QSpinBox(box)
        self.spin_overlay_limit.setRange(1, 100000)
        self.spin_overlay_limit.setValue(min(50, max(1, len(self.results))))
        self.spin_overlay_limit.setToolTip("Draw this many defects by descending score (drawing is slow)")
        row.addWidget(self.spin_overlay_limit)
        row.addStretch(1)
        lay.addLayout(row)

        self.edit_overlay_dir, orow = self._path_row(
            box, os.path.join(self._dir, "overlay"), "Choose the overlay output folder",
            self._pick_overlay_dir)
        lay.addLayout(orow)

        hint = QLabel("Overlays re-run the pipeline to obtain diff; without a recipe only the raw image is drawn.",
                      box)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return box

    def _path_row(self, parent: QWidget, default: str, tip: str,
                  slot: Callable[[], None]) -> Tuple[QLineEdit, QHBoxLayout]:
        row = QHBoxLayout()
        edit = QLineEdit(default, parent)
        edit.setToolTip(tip)
        row.addWidget(edit, 1)
        btn = QPushButton("Browse…", parent)
        btn.setToolTip(tip)
        btn.clicked.connect(slot)
        row.addWidget(btn)
        return edit, row

    # ==================================================================== #
    # 模式切換 / 計畫作廢
    # ==================================================================== #
    def _on_mode_toggled(self, _checked: bool) -> None:
        if self._building:
            return
        self._sync_mode_pages()
        self._invalidate_plan()

    def _sync_mode_pages(self) -> None:
        mode = self.mode()
        self.page_inplace.setVisible(mode == "inplace")
        self.page_annotate.setVisible(mode == "annotate")
        self.page_topn.setVisible(mode == "topn")

    def _on_any_output_toggled(self, _checked: bool = False) -> None:
        if self._building:
            return
        self._update_write_enabled()

    def _invalidate_plan(self, *_args: Any) -> None:
        """任何設定被動過 → 之前的預覽作廢，「寫出」立刻鎖回去。"""
        if self._building:
            return
        if self._plan is not None or self._plan_text:
            self.plan_view.setPlainText(
                "Settings changed — press “Preview changes” again to confirm what this version would do.")
        self._plan = None
        self._plan_text = ""
        self._update_write_enabled()

    def _update_write_enabled(self) -> None:
        has_report = bool(self.chk_csv.isChecked() or self.chk_excel.isChecked()
                          or self.chk_overlay.isChecked())
        if self._klarf_enabled():
            self.btn_write.setEnabled(self._plan is not None)
        else:
            self.btn_write.setEnabled(has_report)

    def _klarf_enabled(self) -> bool:
        return bool(self.doc is not None and self.chk_klarf.isChecked())

    # ==================================================================== #
    # 對外（測試 / 主視窗都走這裡）
    # ==================================================================== #
    def mode(self) -> str:
        """目前選的寫回模式。"""
        for name, rb in self.mode_buttons.items():
            if rb.isChecked():
                return name
        return MODES[0]

    def set_mode(self, mode: str) -> bool:
        """切換寫回模式（認不得的模式回 False，不炸）。"""
        mode = str(mode)
        rb = self.mode_buttons.get(mode)
        if rb is None:
            return False
        rb.setChecked(True)
        self._sync_mode_pages()
        return True

    def column_control(self, name: str) -> Optional[QAbstractButton]:
        """inplace 模式中某個欄位的控制項（欄位不存在時它是 disabled 的）。"""
        return self._col_controls.get(str(name))

    def column_enabled(self, name: str) -> bool:
        ctrl = self.column_control(name)
        return bool(ctrl is not None and ctrl.isEnabled())

    def column_hint(self, name: str) -> str:
        """該欄位旁邊那一行白話說明（欄位不存在時說明為什麼不能選）。"""
        lbl = self._col_hints.get(str(name))
        return "" if lbl is None else lbl.text()

    def klarf_columns(self) -> List[str]:
        """載入的 KLARF 實際有的 defect 欄位。"""
        return list(self._columns)

    def feature_names(self) -> List[str]:
        """annotate 可選的特徵欄名（= 這批結果出現過的特徵）。"""
        return list(self._features)

    def selected_features(self) -> List[str]:
        out = []
        for i in range(self.feature_list.count()):
            it = self.feature_list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.text())
        return out

    def set_selected_features(self, names: Sequence[str]) -> None:
        want = {str(n) for n in (names or [])}
        for i in range(self.feature_list.count()):
            it = self.feature_list.item(i)
            it.setCheckState(Qt.Checked if it.text() in want else Qt.Unchecked)

    def set_output_path(self, kind: str, path: Any) -> bool:
        """設定輸出路徑（``klarf`` / ``csv`` / ``excel`` / ``overlay``）。"""
        edits = {"klarf": self.edit_klarf_out, "csv": self.edit_csv_out,
                 "excel": self.edit_excel_out, "overlay": self.edit_overlay_dir}
        edit = edits.get(str(kind))
        if edit is None:
            return False
        edit.setText(str(path))
        return True

    def output_path(self, kind: str) -> str:
        edits = {"klarf": self.edit_klarf_out, "csv": self.edit_csv_out,
                 "excel": self.edit_excel_out, "overlay": self.edit_overlay_dir}
        edit = edits.get(str(kind))
        return "" if edit is None else edit.text().strip()

    def plan(self) -> Any:
        """最近一次成功預覽的 :class:`WriteBackPlan`（沒有就是 None）。"""
        return self._plan

    def plan_text(self) -> str:
        """計畫書的白話文字（預覽失敗或還沒預覽時為空字串）。"""
        return self._plan_text

    def error_text(self) -> str:
        """最近一次的錯誤訊息（白話；沒有錯誤就是空字串）。"""
        return self._error_text

    def summary(self) -> Optional[Dict[str, Any]]:
        """最近一次輸出的摘要 dict。"""
        return self._summary

    def summary_text(self) -> str:
        return self.status_label.text()

    # ---- 預覽 ------------------------------------------------------------
    def writeback_options(self) -> Dict[str, Any]:
        """目前畫面設定 → :func:`plan_writeback` / :func:`apply_writeback` 的選項。"""
        mode = self.mode()
        if mode == "inplace":
            opts: Dict[str, Any] = {}
            if self.chk_class_col.isChecked():
                opts["class_col"] = "CLASSNUMBER"
            for name in _BIN_COLUMNS:
                ctrl = self._col_controls.get(name)
                if ctrl is not None and ctrl.isChecked():
                    opts["bin_col"] = name
                    break
            if self.chk_size_col.isChecked():
                opts["size_col"] = "DSIZE"
                opts["size_feature"] = self.size_feature_combo.currentText()
                opts["size_scale"] = float(self.size_scale_spin.value())
            return opts
        if mode == "annotate":
            return {"extra_features": self.selected_features()}
        n = int(self.spin_topn.value())
        opts = {"renumber": bool(self.chk_renumber.isChecked()),
                "include_annotations": bool(self.chk_topn_annotate.isChecked())}
        if self.chk_min_score.isChecked():
            opts["n"] = 0
            opts["min_score"] = float(self.spin_min_score.value())
        else:
            opts["n"] = n
        if self.chk_topn_annotate.isChecked():
            opts["extra_features"] = self.selected_features()
        return opts

    def preview_plan(self) -> Any:
        """乾跑 :func:`plan_writeback`，把計畫書渲染成白話；失敗回 None。

        成功之後「寫出」才會開放 —— 使用者一定先看過會發生什麼事。
        """
        self._error_text = ""
        if not self._klarf_enabled():
            self._fail("Nothing to write back — tick “Write the ADC verdict back to KLARF” first.")
            return None
        try:
            plan = plan_writeback(self.doc, self.results, self.mode(),
                                  **self.writeback_options())
        except ExportError as e:
            self._plan = None
            self._plan_text = ""
            self.plan_view.setPlainText("✗ These settings cannot be written:\n\n%s" % e)
            self._fail(str(e))
            self._update_write_enabled()
            return None
        except Exception as e:          # noqa: BLE001 — UI 邊界，絕不吐 traceback
            self._plan = None
            self._plan_text = ""
            msg = "%s: %s" % (type(e).__name__, e)
            self.plan_view.setPlainText("✗ Preview failed:\n\n%s" % msg)
            self._fail(msg)
            self._update_write_enabled()
            return None

        self._plan = plan
        self._plan_text = describe_plan(plan, self.output_path("klarf"))
        self.plan_view.setPlainText(self._plan_text)
        self.status_label.setText("Preview done — check the plan above, then press “Write”.")
        self._update_write_enabled()
        return plan

    def _on_preview_clicked(self) -> None:
        self._interactive = True
        try:
            self.preview_plan()
        finally:
            self._interactive = False

    # ---- 寫出 ------------------------------------------------------------
    def export_spec(self) -> Dict[str, Any]:
        """目前畫面設定 → :func:`run_export_job` 吃的 spec。"""
        spec: Dict[str, Any] = {"results": self.results, "klarf": None,
                                "csv": None, "excel": None, "overlay": None}
        if self._klarf_enabled():
            spec["klarf"] = {
                "doc": self.doc,
                "results": self.results,
                "mode": self.mode(),
                "out_path": self.output_path("klarf"),
                "opts": self.writeback_options(),
            }
        if self.chk_csv.isChecked():
            spec["csv"] = self.output_path("csv")
        if self.chk_excel.isChecked():
            spec["excel"] = {"path": self.output_path("excel"),
                             "recipe": self.recipe,
                             "ground_truth": self.ground_truth}
        if self.chk_overlay.isChecked():
            items = {}
            for it in list(getattr(self.dataset, "items", []) or []):
                items[str(getattr(it, "defect_id", ""))] = it
            spec["overlay"] = {
                "dir": self.output_path("overlay"),
                "results": pick_overlay_results(
                    self.results, int(self.spin_overlay_limit.value())),
                "items": items,
                "recipe": self.recipe,
                "kind": str(getattr(self.dataset, "kind", "")),
                # 掛在 main 上的第二份（F15）—— 疊圖是**跑一次 pipeline** 畫的，
                # 所以它跟預覽、跟批次一樣需要那一份，不然有配對卡的 recipe
                # 會在這裡失敗，而失敗的樣子是「疊圖退回原始影像」。
                "sources": _sources_of(self.dataset),
            }
        return spec

    def run_export(self, sync: bool = False) -> Optional[Dict[str, Any]]:
        """開始輸出。``sync=True`` 直接在呼叫端跑完（測試 / CLI 用）。

        回傳摘要 dict（同步）或 None（非同步已排入背景，或前置檢查沒過）。
        """
        self._error_text = ""
        self._summary = None
        if self._klarf_enabled() and self._plan is None:
            self._fail("Press “Preview changes” first to see what would happen.")
            return None
        spec = self.export_spec()
        if not any(spec.get(k) for k in ("klarf", "csv", "excel", "overlay")):
            self._fail("Nothing is selected for export.")
            return None
        for key, label in (("csv", "CSV"), ("excel", "Excel")):
            target = spec.get(key)
            path = target if isinstance(target, str) else (target or {}).get("path")
            if target and not str(path or "").strip():
                self._fail("%s is selected but no output path was given." % label)
                return None
        if spec.get("klarf") and not str(spec["klarf"]["out_path"] or "").strip():
            self._fail("KLARF write-back is selected but no output path was given.")
            return None

        if sync:
            try:
                out = run_export_job(spec)
            except ExportError as e:
                self._fail(str(e))
                return None
            except Exception as e:      # noqa: BLE001 — UI 邊界
                self._fail("%s: %s" % (type(e).__name__, e))
                return None
            self._on_done(out)
            return out

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)         # 忙碌動畫，收到第一筆進度就換
        self.btn_write.setEnabled(False)
        if not self.worker.start(spec):
            self.status_label.setText("An export is already running — please wait.")
            return None
        self.status_label.setText("Exporting…")
        return None

    def _on_write_clicked(self) -> None:
        self._interactive = True
        try:
            self.run_export(sync=False)
        finally:
            self._interactive = False

    # ---- worker 回呼 -----------------------------------------------------
    def _on_progress(self, done: int, total: int, msg: str) -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, max(1, int(total)))
        self.progress_bar.setValue(max(0, min(int(done), int(total))))
        self.status_label.setText(str(msg))

    def _on_done(self, summary: Any) -> None:
        self._summary = dict(summary or {})
        self.progress_bar.setVisible(False)
        outputs = list(self._summary.get("outputs") or [])
        notes = list(self._summary.get("notes") or [])
        text = "Export finished:\n" + "\n".join("· " + n for n in notes)
        if outputs:
            text += "\nFiles:\n" + "\n".join("   " + p for p in outputs)
        self.status_label.setText(text)
        self._update_write_enabled()
        self.exported.emit(self._summary)
        if self._interactive:
            QMessageBox.information(self, "Export finished", text)

    def _on_failed(self, msg: str) -> None:
        self.progress_bar.setVisible(False)
        self._update_write_enabled()
        self._fail(str(msg))

    def _fail(self, msg: str) -> None:
        """錯誤一律翻成白話：同步路徑存起來，互動路徑跳訊息框。"""
        self._error_text = str(msg)
        self.status_label.setText("⚠ %s" % msg)
        if self._interactive:
            QMessageBox.warning(self, "Cannot export", str(msg))

    # ---- 檔案對話框（測試不走這條路）--------------------------------------
    def _pick_klarf_out(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export KLARF", self.output_path("klarf"),
            "KLARF (*.001 *.klarf *.txt);;All files (*)")
        if path:
            self.set_output_path("klarf", path)

    def _pick_csv_out(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", self.output_path("csv"), "CSV (*.csv);;All files (*)")
        if path:
            self.set_output_path("csv", path)

    def _pick_excel_out(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Excel", self.output_path("excel"),
            "Excel (*.xlsx);;All files (*)")
        if path:
            self.set_output_path("excel", path)

    def _pick_overlay_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Choose the overlay output folder", self.output_path("overlay"))
        if path:
            self.set_output_path("overlay", path)

    # ---- 關窗 ------------------------------------------------------------
    def closeEvent(self, event) -> None:      # noqa: D102 - Qt hook
        try:
            self.worker.stop()
        except Exception:                     # noqa: BLE001 — 關窗不准擋路
            pass
        super().closeEvent(event)


# --------------------------------------------------------------------------- #
# 計畫書 → 白話（Qt-free，方便單獨測）
# --------------------------------------------------------------------------- #
def describe_plan(plan: Any, out_path: str = "") -> str:
    """:class:`WriteBackPlan` → 使用者看得懂的一段字。

    健檢結果用三種符號：``✓`` 沒問題 / ``△`` 提醒 / ``✗`` 會出事。
    """
    mode = getattr(plan, "mode", "?")
    lines = ["Mode: %s" % MODE_LABELS.get(mode, mode)]
    if out_path:
        lines.append("Output file: %s" % out_path)
    lines.append("")
    lines.append("Rows changed: %d defects." % int(getattr(plan, "n_rows_changed", 0)))
    touched = list(getattr(plan, "columns_touched", []) or [])
    added = list(getattr(plan, "columns_added", []) or [])
    lines.append("Existing columns touched: %s" % (", ".join(touched) if touched else "(none)"))
    lines.append("Columns added: %s" % (", ".join(added) if added else "(none)"))
    lines.append("The output file will have %d defect rows." % int(getattr(plan, "n_rows_out", 0)))

    notes = list(getattr(plan, "notes", []) or [])
    if notes:
        lines.append("")
        lines.append("Notes:")
        lines.extend("· %s" % n for n in notes)

    lines.append("")
    lines.append("Output health check:")
    issues = list(getattr(plan, "issues", []) or [])
    if not issues:
        lines.append("✓ No problems found.")
    for it in issues:
        level = str(getattr(it, "level", "info"))
        mark = _LEVEL_MARK.get(level, "△")
        title = str(getattr(it, "title", ""))
        count = int(getattr(it, "count", 0) or 0)
        head = "%s %s" % (mark, title)
        if count:
            head += "(%d entries)" % count
        lines.append(head)
        detail = str(getattr(it, "detail", "") or "").strip()
        if detail:
            lines.append("    %s" % detail)
    return "\n".join(lines)
