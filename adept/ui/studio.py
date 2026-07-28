# ADEPT Studio 主視窗 — authored 2026-07-28 (M3 收尾).
"""``StudioWindow`` —— 把 M3 的元件、view-model 與背景工作接成一台可用的機器。

版面（全部用 QSplitter，使用者拉得動）::

    ┌ 工具列：開啟 KLARF／Recipe／存檔／範本 ｜ 試跑筆數 ▶試跑 ▶全跑 ┐
    ├──────────┬──────────────────────┬──────────────────────────────┤
    │ 卡片庫    │ 流程（PipelinePanel） │ 預覽：◀ ▶ 缺陷選單            │
    │ Library  │ ──────────────────── │      影像流下拉               │
    │ ~230px   │ 參數表單 / 分數編輯   │      ImageView                │
    │          │ （QStackedWidget）    │      特徵表 + 判定 chip       │
    ├──────────┴──────────────────────┴──────────────────────────────┤
    │ 分數分佈直方圖（可拖門檻線）                                      │
    ├─────────────────────────────────────────────────────────────────┤
    │ 狀態列：進度 / 訊息                                              │
    └─────────────────────────────────────────────────────────────────┘

三條資料流（別搞混）
--------------------
1. **編輯流**：UI 事件 → :class:`~adept.ui.viewmodel.RecipeModel` 的方法 →
   model 通知 listener → 主視窗刷新 Pipeline/Score 顯示 + 排一次**去抖動
   （300ms）**的預覽。UI 元件自己**不改** model，也不直接呼叫引擎。
2. **預覽流**：:class:`~adept.ui.workers.PreviewWorker` 算一顆 defect →
   ``ready`` → 填影像流下拉 / ImageView / 特徵表 / 判定 chip。
3. **試跑流**：:class:`~adept.ui.workers.TrialWorker` 跑 N 顆 →
   ``done`` → 直方圖 + bin 摘要 + 狀態列統計。

門檻的「秒回」路徑很重要：拖曳中只用 :func:`~adept.ui.viewmodel.rebin`
重算 bin 數（**不寫 model、不重跑**），放開才 ``set_threshold``。

測試友善 API（完全不開對話框，見 tests/test_ui_studio_smoke.py）：
:meth:`StudioWindow.load_dataset_path` / :meth:`~StudioWindow.load_recipe_path` /
:meth:`~StudioWindow.load_template` / :meth:`~StudioWindow.select_node` /
:meth:`~StudioWindow.set_defect_index` / :meth:`~StudioWindow.refresh_preview` /
:meth:`~StudioWindow.run_trial` / :meth:`~StudioWindow.save_recipe_path`。
每個進入點都自我保護：沒有資料集 / 流程是空的 → 狀態列提示，不丟例外。
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import adept.core.steps  # noqa: F401 — 觸發卡片註冊（Qt-free、便宜）
from adept.core.pipeline import ParamError, Recipe, get_step, list_steps

from .viewmodel import RecipeModel, histogram, rebin
from .widgets import (
    FeatureTable,
    HistogramWidget,
    ImageView,
    LibraryPanel,
    ParamForm,
    PipelinePanel,
    VerdictChip,
)
from .workers import DatasetLoadWorker, PreviewWorker, TrialWorker

__all__ = ["StudioWindow", "TEMPLATE_RECIPE", "DEFAULT_CACHE_DIR"]

#: 卡片庫「ADC 判定」段固定顯示的 Score / Bin 項目。它不是 registry 裡的
#: step（每條 pipeline 天生就有一張 ScoreSpec），但三段式的心智模型要完整 ——
#: 使用者要能在庫裡看到「影像 → 算法 → ADC 判定」三段都有東西。點它 = 去編輯分數。
_SCORE_LIBRARY_KEY = "__score__"
_SCORE_LIBRARY_ENTRY = {
    "key": _SCORE_LIBRARY_KEY,
    "label": "Score / Bin",
    "category": "adc",
    "help": "把量到的特徵組成分數，並用門檻分 bin —— 每條 pipeline 固定有一張，點此編輯。",
    "requires_ref": False,
    "params": [],
    "reads": [],
    "writes": [],
    "features_out": ["score"],
}

#: 「載入範本」讀的檔案（repo 內的 die-to-die 範例）。
TEMPLATE_RECIPE = Path(__file__).resolve().parents[2] / "examples" / "recipes" \
    / "die_to_die_basic.json"

#: 試跑用的影像段快取位置（跨次試跑重用，第二次調參會明顯變快）。
DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".adept", "cache")

#: GUI 試跑用幾個 worker。None = 依 CPU 核心數自動。
#:
#: 歷史：這裡一度必須寫死 1 —— ``run_batch(workers>1)`` 會開
#: ``ProcessPoolExecutor``，而在 fork 為預設啟動法的平台（Linux）上，從
#: :class:`~PySide6.QtCore.QThread`（``TrialWorker`` 就是）裡 fork 會**穩定死鎖**
#: （子行程繼承其他執行緒持有的鎖，卡在啟動階段，progress 一筆都不發）。
#: 已於 ``batch._pool_context()`` 修正：主執行緒仍用 fork（CLI/script 免寫
#: ``if __name__ == "__main__"`` 保護），非主執行緒自動改用 spawn。
#: 迴歸測試見 ``tests/test_batch_thread_safety.py``。
TRIAL_WORKERS = None

#: model 變動 → 重算預覽 的去抖動間隔（毫秒）。拖 spinbox 不會每格都重算。
PREVIEW_DEBOUNCE_MS = 300

_FEATURE_PLACEHOLDER = "插入特徵 ▾"
_SCORE_HELP = ("分數是一條算式，變數就是上面流程產出的特徵名（例："
               "snr_max、blob_area、glv_max）。分數 ≥ 門檻 → bin 1，"
               "否則 bin 0。可用 + - * / ( ) 與 sqrt / abs / min / max。")


def _fmt(value: Any) -> str:
    """參數摘要用的短字串（float 去掉多餘的 0）。"""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return ("%g" % value)
    return str(value)


class StudioWindow(QMainWindow):
    """ADEPT Studio 主視窗（M3 最終組裝）。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ADEPT Studio")

        # ---- 狀態 ---------------------------------------------------------
        self.model = RecipeModel()
        self.dataset: Optional[Any] = None
        self.trial_scores: List[float] = []
        self.defect_index: int = 0
        self.selected_node: Optional[str] = None
        self.recipe_path: Optional[str] = None

        self._preview_images: Dict[str, Any] = {}
        self._last_result: Optional[Any] = None
        self._user_stream: Optional[str] = None   # 使用者親手挑的影像流（會被保留）
        self._syncing = False            # 程式在寫 widget（別回頭觸發 model）
        self._trial_t0 = 0.0

        # ---- 背景工作 ------------------------------------------------------
        self.dataset_worker = DatasetLoadWorker(self)
        self.preview_worker = PreviewWorker(self)
        self.trial_worker = TrialWorker(self)

        # ---- 去抖動計時器 --------------------------------------------------
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._on_preview_timeout)

        # ---- 介面 ----------------------------------------------------------
        self._build_toolbar()
        self._build_body()
        self.setStatusBar(QStatusBar(self))

        self._wire_widgets()
        self._wire_workers()
        self.model.add_listener(self._on_model_changed)

        self.library.set_steps([s.describe() for s in list_steps()]
                               + [_SCORE_LIBRARY_ENTRY])
        self._refresh_all()
        self._status("準備好了 —— 先「開啟 KLARF…」載入資料，或「載入範本」看一條完整流程。")

    # ==================================================================== #
    # 介面組裝
    # ==================================================================== #
    def _build_toolbar(self) -> None:
        bar = QToolBar("主要動作", self)
        bar.setMovable(False)
        bar.setFloatable(False)
        self.toolbar = bar
        self.addToolBar(bar)

        self.btn_open_klarf = self._tool_button(
            "開啟 KLARF…", "載入一份 KLARF（可另外指定 patch TIFF）",
            self._on_open_klarf)
        self.btn_open_recipe = self._tool_button(
            "開啟 Recipe…", "載入一份 recipe JSON", self._on_open_recipe)
        self.btn_save_recipe = self._tool_button(
            "存 Recipe…", "把目前流程存成 recipe JSON", self._on_save_recipe)
        self.btn_template = self._tool_button(
            "載入範本（die-to-die）", "載入內建的 die-to-die 範例流程",
            self.load_template)
        for b in (self.btn_open_klarf, self.btn_open_recipe,
                  self.btn_save_recipe, self.btn_template):
            bar.addWidget(b)

        spacer = QWidget(bar)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        bar.addWidget(QLabel("試跑筆數 ", bar))
        self.spin_trial_n = QSpinBox(bar)
        self.spin_trial_n.setRange(10, 5000)
        self.spin_trial_n.setValue(200)
        self.spin_trial_n.setToolTip("試跑要跑前幾顆 defect（調參時先跑少一點）")
        bar.addWidget(self.spin_trial_n)

        self.btn_trial = self._tool_button(
            "▶ 試跑", "用目前流程跑前 N 顆，看分數分佈",
            self._on_trial_clicked, primary=True)
        self.btn_full = self._tool_button(
            "▶ 全跑", "跑完整個資料集", self._on_full_clicked)
        bar.addWidget(self.btn_trial)
        bar.addWidget(self.btn_full)

    def _tool_button(self, text: str, tip: str, slot: Any,
                     primary: bool = False) -> QToolButton:
        b = QToolButton(self)
        b.setText(text)
        b.setToolTip(tip)
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        b.setCursor(Qt.PointingHandCursor)
        if primary:
            b.setObjectName("primary")
        b.clicked.connect(slot)
        return b

    def _build_body(self) -> None:
        # 左：卡片庫
        self.library = LibraryPanel(self)
        self.library.setMinimumWidth(180)

        # 中：流程 + （參數表單 / 分數編輯）
        self.pipeline = PipelinePanel(self)
        self.param_form = ParamForm(self)
        self.score_pane = self._build_score_pane()
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.param_form)     # index 0
        self.stack.addWidget(self.score_pane)     # index 1

        middle = QSplitter(Qt.Vertical, self)
        middle.addWidget(self.pipeline)
        middle.addWidget(self.stack)
        middle.setStretchFactor(0, 3)
        middle.setStretchFactor(1, 2)
        self.middle_splitter = middle

        # 右：預覽
        right = self._build_preview_pane()

        top = QSplitter(Qt.Horizontal, self)
        top.addWidget(self.library)
        top.addWidget(middle)
        top.addWidget(right)
        top.setStretchFactor(0, 0)
        top.setStretchFactor(1, 2)
        top.setStretchFactor(2, 3)
        top.setSizes([230, 420, 620])
        self.top_splitter = top

        # 下：全寬直方圖
        self.histogram = HistogramWidget(self)

        root = QSplitter(Qt.Vertical, self)
        root.addWidget(top)
        root.addWidget(self.histogram)
        root.setStretchFactor(0, 4)
        root.setStretchFactor(1, 1)
        root.setSizes([620, 190])
        self.root_splitter = root
        self.setCentralWidget(root)

    def _build_score_pane(self) -> QWidget:
        pane = QWidget(self)
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(2, 2, 8, 2)
        lay.setSpacing(4)

        title = QLabel("Score / Bin 判定", pane)
        title.setObjectName("paramTitle")
        lay.addWidget(title)

        head = QLabel("流程的最後一步：把特徵算成一個分數，再用門檻切成 bin。", pane)
        head.setObjectName("paramStepHelp")
        head.setWordWrap(True)
        lay.addWidget(head)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        lbl_expr = QLabel("分數表達式", pane)
        lbl_expr.setObjectName("paramLabel")
        lbl_expr.setMinimumWidth(104)
        self.expr_edit = QLineEdit(pane)
        self.expr_edit.setPlaceholderText("例：glv_max + (glv_max - glv_q99)")
        self.expr_edit.setToolTip("用特徵名寫一條算式，算出來就是這顆 defect 的分數")
        row1.addWidget(lbl_expr)
        row1.addWidget(self.expr_edit, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        lbl_ins = QLabel("插入特徵", pane)
        lbl_ins.setObjectName("paramLabel")
        lbl_ins.setMinimumWidth(104)
        self.feature_combo = QComboBox(pane)
        self.feature_combo.setToolTip("選一個特徵名，會插到表達式游標的位置")
        row2.addWidget(lbl_ins)
        row2.addWidget(self.feature_combo, 1)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        lbl_thr = QLabel("判定門檻", pane)
        lbl_thr.setObjectName("paramLabel")
        lbl_thr.setMinimumWidth(104)
        self.threshold_spin = QDoubleSpinBox(pane)
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setRange(-1e9, 1e9)
        self.threshold_spin.setSingleStep(0.5)
        self.threshold_spin.setToolTip("分數 ≥ 門檻 → bin 1（要抓的），否則 bin 0")
        row3.addWidget(lbl_thr)
        row3.addWidget(self.threshold_spin, 1)
        lay.addLayout(row3)

        hint = QLabel(_SCORE_HELP, pane)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.score_hint = hint

        lay.addStretch(1)
        return pane

    def _build_preview_pane(self) -> QWidget:
        pane = QWidget(self)
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.btn_prev = QPushButton("◀", pane)
        self.btn_prev.setObjectName("cardButton")
        self.btn_prev.setFixedWidth(28)
        self.btn_prev.setToolTip("上一顆 defect")
        self.btn_next = QPushButton("▶", pane)
        self.btn_next.setObjectName("cardButton")
        self.btn_next.setFixedWidth(28)
        self.btn_next.setToolTip("下一顆 defect")
        self.defect_combo = QComboBox(pane)
        self.defect_combo.setToolTip("直接跳到某一顆 defect")
        self.defect_label = QLabel("（尚未載入資料集）", pane)
        self.defect_label.setObjectName("paramHint")
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        nav.addWidget(self.defect_combo, 1)
        nav.addWidget(self.defect_label)
        lay.addLayout(nav)

        srow = QHBoxLayout()
        srow.setSpacing(6)
        lbl_stream = QLabel("影像流", pane)
        lbl_stream.setObjectName("paramLabel")
        self.stream_combo = QComboBox(pane)
        self.stream_combo.setToolTip("要看哪一條影像流（test / ref / diff / snr_map …）")
        srow.addWidget(lbl_stream)
        srow.addWidget(self.stream_combo, 1)
        lay.addLayout(srow)

        self.image_view = ImageView(pane)
        lay.addWidget(self.image_view, 3)

        self.feature_table = FeatureTable(pane)
        self.feature_table.setMinimumHeight(120)
        lay.addWidget(self.feature_table, 2)

        vrow = QHBoxLayout()
        vrow.setSpacing(6)
        self.verdict = VerdictChip(pane)
        vrow.addWidget(QLabel("判定", pane))
        vrow.addWidget(self.verdict)
        vrow.addStretch(1)
        lay.addLayout(vrow)

        return pane

    # ==================================================================== #
    # 訊號接線
    # ==================================================================== #
    def _wire_widgets(self) -> None:
        self.library.add_requested.connect(self._on_add_requested)

        self.pipeline.node_selected.connect(self.select_node)
        self.pipeline.node_toggled.connect(self._on_node_toggled)
        self.pipeline.move_requested.connect(self._on_move_requested)
        self.pipeline.remove_requested.connect(self._on_remove_requested)
        self.pipeline.score_clicked.connect(self.show_score_page)

        self.param_form.param_edited.connect(self._on_param_edited)

        self.expr_edit.textEdited.connect(self._on_expr_edited)
        self.feature_combo.activated.connect(self._on_feature_chosen)
        self.threshold_spin.valueChanged.connect(self._on_threshold_spin)

        self.btn_prev.clicked.connect(lambda: self.step_defect(-1))
        self.btn_next.clicked.connect(lambda: self.step_defect(+1))
        self.defect_combo.currentIndexChanged.connect(self._on_defect_combo)
        self.stream_combo.currentTextChanged.connect(self._on_stream_changed)

        self.image_view.cursor_info.connect(self._on_cursor_info)

        self.histogram.threshold_changed.connect(self._on_threshold_changed)
        self.histogram.threshold_committed.connect(self._on_threshold_committed)

    def _wire_workers(self) -> None:
        self.dataset_worker.loaded.connect(self._on_dataset_loaded)
        self.dataset_worker.failed.connect(
            lambda msg: self._status("載入資料集失敗：%s" % msg))

        self.preview_worker.ready.connect(self._on_preview_ready)
        self.preview_worker.busy.connect(self._on_preview_busy)
        self.preview_worker.failed.connect(
            lambda msg: self._status("預覽失敗：%s" % msg))

        self.trial_worker.progress.connect(self._on_trial_progress)
        self.trial_worker.done.connect(self._on_trial_done_async)
        self.trial_worker.failed.connect(
            lambda msg: self._status("試跑失敗：%s" % msg))

    # ==================================================================== #
    # 狀態列
    # ==================================================================== #
    def _status(self, msg: str) -> None:
        self.statusBar().showMessage(str(msg))

    def status_text(self) -> str:
        """目前狀態列文字（測試用）。"""
        return self.statusBar().currentMessage()

    def _on_cursor_info(self, text: str) -> None:
        if text:
            self._status(text)

    # ==================================================================== #
    # model → UI
    # ==================================================================== #
    def _on_model_changed(self) -> None:
        """model 任何變動的統一入口（listener）。"""
        self._refresh_pipeline()
        self._sync_score_widgets()
        self.histogram.set_threshold(self.model.threshold)
        self._refresh_bin_summary(self.model.threshold)
        self._schedule_preview()

    def _refresh_all(self) -> None:
        self._refresh_pipeline()
        self._sync_score_widgets()
        self._refresh_feature_combo()
        self.histogram.set_threshold(self.model.threshold)
        self._refresh_bin_summary(self.model.threshold)

    def _node_summary(self, node: Any) -> str:
        """最多 3 個「非預設」參數，渲染成 ``k=v`` 串起來。"""
        try:
            step_cls = get_step(node.step)
        except KeyError:
            return "（未知的卡片 %s）" % node.step
        defaults = {p.name: p.default for p in step_cls.params}
        parts: List[str] = []
        for name, value in node.params.items():
            if name in defaults and defaults[name] == value:
                continue
            parts.append("%s=%s" % (name, _fmt(value)))
            if len(parts) >= 3:
                break
        return " · ".join(parts)

    def _refresh_pipeline(self) -> None:
        nodes: List[Dict[str, Any]] = []
        for nid in self.model.node_order:
            node = self.model.nodes.get(nid)
            if node is None:
                continue
            try:
                step_cls = get_step(node.step)
                label, category = step_cls.label, step_cls.category
            except KeyError:
                label, category = node.step, ""
            nodes.append({
                "node_id": nid,
                "step_key": node.step,
                "label": label,
                "category": category,
                "enabled": bool(node.enabled),
                "summary": self._node_summary(node),
            })
        self.pipeline.set_nodes(nodes)
        if self.selected_node not in self.model.nodes:
            self.selected_node = None
        self.pipeline.set_selected(self.selected_node)
        self.pipeline.set_score_summary(self.model.expr, self.model.threshold)

    def _sync_score_widgets(self) -> None:
        self._syncing = True
        try:
            if self.expr_edit.text() != self.model.expr:
                self.expr_edit.setText(self.model.expr)
            if float(self.threshold_spin.value()) != float(self.model.threshold):
                self.threshold_spin.setValue(float(self.model.threshold))
        finally:
            self._syncing = False
        self.pipeline.set_score_summary(self.model.expr, self.model.threshold)

    def _refresh_feature_combo(self) -> None:
        self._syncing = True
        try:
            self.feature_combo.clear()
            self.feature_combo.addItem(_FEATURE_PLACEHOLDER)
            for name in self.model.available_features():
                self.feature_combo.addItem(name)
            self.feature_combo.setCurrentIndex(0)
        finally:
            self._syncing = False

    def _refresh_bin_summary(self, threshold: float) -> None:
        if not self.trial_scores:
            self.histogram.set_bin_summary(None)
            return
        self.histogram.set_bin_summary(
            rebin(self.trial_scores, float(threshold), self.model.bins))

    # ==================================================================== #
    # 卡片庫 / 流程
    # ==================================================================== #
    def _on_add_requested(self, step_key: str) -> None:
        if str(step_key) == _SCORE_LIBRARY_KEY:
            # 「Score / Bin」不是可增刪的卡片 —— 每條 pipeline 固定有一張，
            # 點它就是去編輯分數表達式與門檻（三段式的最後一段）。
            self.show_score_page()
            self._status("編輯分數 / 門檻")
            return
        try:
            node_id = self.model.add_step(str(step_key))
        except (KeyError, ParamError) as e:
            self._status("加入卡片失敗：%s" % e)
            return
        self._status("已加入「%s」" % node_id)
        self.select_node(node_id)

    def _on_node_toggled(self, node_id: str, enabled: bool) -> None:
        self.model.set_enabled(str(node_id), bool(enabled))

    def _on_move_requested(self, node_id: str, delta: int) -> None:
        self.model.move(str(node_id), int(delta))

    def _on_remove_requested(self, node_id: str) -> None:
        node_id = str(node_id)
        self.model.remove(node_id)
        if self.selected_node == node_id:
            self.selected_node = None
            self.param_form.set_step(None, {}, [])
        self._status("已移除「%s」" % node_id)

    def select_node(self, node_id: str) -> bool:
        """選取一個節點：右邊換成它的參數表單，預覽跑到它為止。"""
        node_id = str(node_id)
        node = self.model.nodes.get(node_id)
        if node is None:
            self._status("找不到節點「%s」。" % node_id)
            return False
        self.selected_node = node_id
        self._user_stream = None       # 換節點 → 影像流回到「這個節點的輸出」
        self.pipeline.set_selected(node_id)
        try:
            describe = get_step(node.step).describe()
        except KeyError:
            describe = None
        streams = self.model.available_streams(before_node=node_id)
        self.param_form.set_step(describe, node.params, streams)
        self.stack.setCurrentWidget(self.param_form)
        self._schedule_preview()
        return True

    def show_score_page(self) -> None:
        """切到分數編輯頁（順便刷新特徵下拉）。"""
        self._refresh_feature_combo()
        self._sync_score_widgets()
        self.stack.setCurrentWidget(self.score_pane)

    def show_param_page(self) -> None:
        self.stack.setCurrentWidget(self.param_form)

    # ==================================================================== #
    # 參數編輯
    # ==================================================================== #
    def _on_param_edited(self, name: str, value: Any) -> None:
        """ParamForm 的唯一出口：驗證通過才寫回 model，失敗就把那列變紅字。"""
        node_id = self.selected_node
        if node_id is None or node_id not in self.model.nodes:
            self._status("先在流程中選一個節點，再調整參數。")
            return
        try:
            self.model.set_param(node_id, str(name), value)
        except ParamError as e:
            self.param_form.show_error(str(name), str(e))
            self._status(str(e))
        else:
            self.param_form.clear_errors()

    # ==================================================================== #
    # 分數編輯
    # ==================================================================== #
    def _on_expr_edited(self, text: str) -> None:
        if self._syncing:
            return
        self.model.set_expr(str(text))

    def _on_feature_chosen(self, index: int) -> None:
        """「插入特徵 ▾」：把特徵名插到表達式的游標位置。"""
        if self._syncing or int(index) <= 0:
            return
        token = self.feature_combo.itemText(int(index))
        self._syncing = True
        try:
            self.feature_combo.setCurrentIndex(0)
        finally:
            self._syncing = False
        if not token:
            return
        text = self.expr_edit.text()
        pos = self.expr_edit.cursorPosition()
        pos = max(0, min(pos, len(text)))
        new_text = text[:pos] + token + text[pos:]
        self._syncing = True
        try:
            self.expr_edit.setText(new_text)
            self.expr_edit.setCursorPosition(pos + len(token))
        finally:
            self._syncing = False
        self.model.set_expr(new_text)

    def _on_threshold_spin(self, value: float) -> None:
        if self._syncing:
            return
        self.model.set_threshold(float(value))

    # ---- 直方圖門檻線 -----------------------------------------------------
    def _on_threshold_changed(self, value: float) -> None:
        """拖曳中：**只**重算 bin 數（秒回），絕不寫 model、不重跑。"""
        self._refresh_bin_summary(float(value))
        self._status("門檻 %.3g（放開滑鼠才套用）" % float(value))

    def _on_threshold_committed(self, value: float) -> None:
        """放開滑鼠：這時才寫回 model（會觸發刷新與預覽）。"""
        self.model.set_threshold(float(value))
        self._status("門檻已設為 %.3g" % float(value))

    # ==================================================================== #
    # 資料集
    # ==================================================================== #
    def load_dataset_path(self, path: Any, tiff: Optional[Any] = None,
                          sync: bool = False) -> bool:
        """載入 KLARF（``sync=True`` 走同步路徑，給測試 / CLI 用）。"""
        path = str(path)
        tiff = None if tiff is None else str(tiff)
        if not os.path.isfile(path):
            self._status("找不到檔案：%s" % path)
            return False
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync(path, tiff)
            except Exception as e:      # noqa: BLE001 — UI 邊界，一律回報
                self._status("載入資料集失敗：%s: %s" % (type(e).__name__, e))
                return False
            self._on_dataset_loaded(ds)
            return True
        if not self.dataset_worker.start(path, tiff):
            self._status("已經在載入資料集了，請稍候。")
            return False
        self._status("載入中：%s" % os.path.basename(path))
        return True

    def _on_dataset_loaded(self, dataset: Any) -> None:
        self.dataset = dataset
        items = list(getattr(dataset, "items", []) or [])
        self.defect_index = 0

        self._syncing = True
        try:
            self.defect_combo.clear()
            for it in items:
                self.defect_combo.addItem(str(getattr(it, "defect_id", "?")))
            if items:
                self.defect_combo.setCurrentIndex(0)
        finally:
            self._syncing = False

        # 空流程時讓 route 型別跟著資料走（載了 recipe 之後就以 recipe 為準）
        if not self.model.node_order:
            self.model.kind = str(getattr(dataset, "kind", self.model.kind))

        self._update_defect_label()
        warn = list(getattr(dataset, "warnings", []) or [])
        msg = "已載入 %d 顆 defect（型別 %s）" % (
            len(items), getattr(dataset, "kind", "?"))
        if warn:
            msg += "　⚠ %s" % warn[0]
        self._status(msg)
        if items:
            self.refresh_preview(force=False)

    def _current_item(self) -> Optional[Any]:
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            return None
        i = max(0, min(int(self.defect_index), len(items) - 1))
        self.defect_index = i
        return items[i]

    def _update_defect_label(self) -> None:
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self.defect_label.setText("（尚未載入資料集）")
            return
        i = max(0, min(int(self.defect_index), len(items) - 1))
        self.defect_label.setText(
            "%s · 第 %d / %d 顆" % (getattr(self.dataset, "kind", "?"),
                                    i + 1, len(items)))

    def set_defect_index(self, index: int) -> bool:
        """跳到第 ``index`` 顆 defect（超出範圍會夾住）。"""
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self._status("還沒有載入資料集 —— 請先「開啟 KLARF…」。")
            return False
        i = max(0, min(int(index), len(items) - 1))
        self.defect_index = i
        self._syncing = True
        try:
            if self.defect_combo.currentIndex() != i:
                self.defect_combo.setCurrentIndex(i)
        finally:
            self._syncing = False
        self._update_defect_label()
        self._schedule_preview()
        return True

    def step_defect(self, delta: int) -> bool:
        return self.set_defect_index(int(self.defect_index) + int(delta))

    def _on_defect_combo(self, index: int) -> None:
        if self._syncing or int(index) < 0:
            return
        self.set_defect_index(int(index))

    # ==================================================================== #
    # Recipe
    # ==================================================================== #
    def load_recipe_path(self, path: Any, sync: bool = False) -> bool:
        """載入 recipe JSON：重建 model、重接 listener、刷新所有面板。"""
        path = str(path)
        try:
            recipe = Recipe.load(path)
        except Exception as e:          # noqa: BLE001 — UI 邊界
            self._status("載入 recipe 失敗：%s: %s" % (type(e).__name__, e))
            return False
        kind = None
        ds_kind = str(getattr(self.dataset, "kind", "")) if self.dataset else ""
        if ds_kind and ds_kind in recipe.routes:
            kind = ds_kind
        self._apply_model(RecipeModel.from_recipe(recipe, kind=kind))
        self.recipe_path = path
        self.setWindowTitle("ADEPT Studio — %s" % self.model.recipe_id)
        n = len(self.model.node_order)
        self._status("已載入 recipe「%s」（%d 個步驟，route %s）"
                     % (self.model.recipe_id, n, self.model.kind))
        if ds_kind and ds_kind not in recipe.routes:
            self._status("已載入 recipe「%s」，但它沒有 '%s' 這條 route —— "
                         "預覽/試跑會失敗。" % (self.model.recipe_id, ds_kind))
        self.refresh_preview(sync=sync, force=False)
        return True

    def _apply_model(self, model: RecipeModel) -> None:
        """換掉 model 並重接所有顯示（listener 一定要重掛）。"""
        self.model = model
        self.model.add_listener(self._on_model_changed)
        self.selected_node = None
        self._user_stream = None
        self.pipeline.set_selected(None)
        self.param_form.set_step(None, {}, [])
        self.stack.setCurrentWidget(self.param_form)
        self._refresh_all()

    def load_template(self) -> bool:
        """載入內建的 die-to-die 範本；檔案不在就只在狀態列抱怨，不炸。"""
        path = TEMPLATE_RECIPE
        if not path.is_file():
            self._status("找不到內建範本：%s" % path)
            return False
        return self.load_recipe_path(str(path))

    def save_recipe_path(self, path: Any) -> bool:
        """把目前 model 存成 recipe JSON。"""
        path = str(path)
        if not self.model.node_order:
            self._status("流程還是空的，沒有東西可以存。")
            return False
        try:
            self.model.to_recipe().save(path)
        except Exception as e:          # noqa: BLE001 — UI 邊界
            self._status("存檔失敗：%s: %s" % (type(e).__name__, e))
            return False
        self.recipe_path = path
        self.model.dirty = False
        self._status("已存檔：%s" % path)
        return True

    # ==================================================================== #
    # 預覽
    # ==================================================================== #
    def _schedule_preview(self) -> None:
        """排一次去抖動的預覽（300ms 內的連續變動只算最後一次）。"""
        self._preview_timer.start()

    def _on_preview_timeout(self) -> None:
        self.refresh_preview(force=False)

    def refresh_preview(self, sync: bool = False, force: bool = True) -> bool:
        """重算單顆預覽。

        ``force=False`` 時前置條件不滿足只是安靜跳過（去抖動計時器用的路徑，
        不要一直在狀態列鬼叫）；``force=True`` 會把原因寫到狀態列。
        """
        self._preview_timer.stop()
        if not self.model.node_order:
            if force:
                self._status("流程還是空的 —— 先從左邊卡片庫加入第一張卡。")
            return False
        item = self._current_item()
        if item is None:
            if force:
                self._status("還沒有載入資料集 —— 請先「開啟 KLARF…」。")
            return False

        recipe = self.model.to_recipe()
        upto = self.selected_node if self.selected_node in self.model.nodes else None
        if sync:
            try:
                result = PreviewWorker.run_sync(recipe, item, self.model.kind,
                                                upto_node=upto)
            except Exception as e:      # noqa: BLE001 — UI 邊界
                self._status("預覽失敗：%s: %s" % (type(e).__name__, e))
                return False
            self._on_preview_ready(result)
            return True
        self.preview_worker.request(recipe, item, self.model.kind, upto_node=upto)
        return True

    def _on_preview_busy(self, busy: bool) -> None:
        if busy:
            self._status("預覽計算中…")

    def _on_preview_ready(self, result: Any) -> None:
        self._last_result = result
        ctx = getattr(result, "context", None)
        images = dict(getattr(ctx, "images", {}) or {}) if ctx is not None else {}
        self._preview_images = images

        self._populate_streams(images)
        self._show_current_stream()

        highlight = self._highlight_features(result)
        self.feature_table.set_features(getattr(result, "features", {}) or {},
                                        highlight=highlight)
        score = getattr(result, "score", None)
        self.verdict.set_verdict(getattr(result, "bin", None)
                                 if score is not None else None)

        if not getattr(result, "ok", False):
            # 失敗照樣把已經算出來的影像留在畫面上（診斷比清空有用）
            self._status("預覽有問題：%s" % (getattr(result, "error", None) or "未知錯誤"))
        elif self.selected_node:
            self._status("預覽：跑到「%s」為止（%d 條影像流）"
                         % (self.selected_node, len(images)))
        else:
            self._status("預覽完成（%d 條影像流）%s"
                         % (len(images),
                            "　分數 %.4g" % score if score is not None else ""))

    def _highlight_features(self, result: Any) -> Sequence[str]:
        """選取節點這一步新增/改值的特徵 → 在特徵表裡標色。"""
        nid = self.selected_node
        if not nid:
            return ()
        for tr in getattr(result, "traces", []) or []:
            if getattr(tr, "node_id", None) == nid:
                return list(getattr(tr, "features_added", {}) or {})
        return ()

    def _default_stream(self, images: Dict[str, Any]) -> str:
        nid = self.selected_node
        node = self.model.nodes.get(nid) if nid else None
        if node is not None:
            try:
                writes = get_step(node.step).resolve_writes(node.params)
            except KeyError:
                writes = []
            for w in reversed(list(writes)):
                if w in images:
                    return str(w)
        if "test" in images:
            return "test"
        for k in images:
            return str(k)
        return ""

    def _populate_streams(self, images: Dict[str, Any]) -> None:
        """重建影像流下拉；使用者**親手挑過**的那條還在就留著。

        「親手挑過」只認 :meth:`_on_stream_changed`（真的動了下拉）；換節點時
        會清掉，讓畫面自動跳到新節點的輸出 —— 點卡片就看得到那張圖。
        """
        names = sorted(images)
        want = (self._user_stream if self._user_stream in images
                else self._default_stream(images))
        self._syncing = True
        try:
            self.stream_combo.clear()
            self.stream_combo.addItems(names)
            if want in names:
                self.stream_combo.setCurrentIndex(names.index(want))
        finally:
            self._syncing = False

    def _show_current_stream(self) -> None:
        name = self.stream_combo.currentText()
        self.image_view.set_image(self._preview_images.get(name))

    def _on_stream_changed(self, text: str) -> None:
        if self._syncing:
            return
        self._user_stream = str(text) or None
        self._show_current_stream()

    # ==================================================================== #
    # 試跑
    # ==================================================================== #
    def run_trial(self, n: int, workers: Optional[int] = 1,
                  sync: bool = False, cache_dir: Optional[Any] = None) -> bool:
        """跑前 ``n`` 顆並更新直方圖。``sync=True`` 走同步路徑（測試用）。"""
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self._status("還沒有載入資料集 —— 請先「開啟 KLARF…」。")
            return False
        if not self.model.node_order:
            self._status("流程還是空的 —— 先加入卡片再試跑。")
            return False
        limit = max(1, min(int(n), len(items)))
        recipe = self.model.to_recipe()
        cdir = None if cache_dir is None else str(cache_dir)

        if sync:
            t0 = time.time()
            try:
                results = TrialWorker.run_sync(
                    recipe, self.dataset, limit,
                    workers=int(workers) if workers else 1, cache_dir=cdir)
            except Exception as e:      # noqa: BLE001 — UI 邊界
                self._status("試跑失敗：%s: %s" % (type(e).__name__, e))
                return False
            self._apply_trial_results(results, time.time() - t0)
            return True

        self._trial_t0 = time.time()
        if not self.trial_worker.start(recipe, self.dataset, limit,
                                       workers=workers, cache_dir=cdir):
            self._status("已經在試跑了，請稍候。")
            return False
        self._status("試跑中：0 / %d" % limit)
        return True

    def _on_trial_clicked(self) -> None:
        self.run_trial(int(self.spin_trial_n.value()), workers=TRIAL_WORKERS,
                       cache_dir=DEFAULT_CACHE_DIR)

    def _on_full_clicked(self) -> None:
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self._status("還沒有載入資料集 —— 請先「開啟 KLARF…」。")
            return
        self.run_trial(len(items), workers=TRIAL_WORKERS,
                       cache_dir=DEFAULT_CACHE_DIR)

    def _on_trial_progress(self, done: int, total: int) -> None:
        self._status("試跑中：%d / %d" % (int(done), int(total)))

    def _on_trial_done_async(self, results: Any) -> None:
        self._apply_trial_results(list(results or []),
                                  time.time() - (self._trial_t0 or time.time()))

    def _apply_trial_results(self, results: Sequence[Dict[str, Any]],
                             elapsed: float) -> None:
        results = list(results or [])
        self.trial_scores = [r["score"] for r in results
                             if r.get("ok") and r.get("score") is not None]
        edges, counts = histogram(self.trial_scores)
        self.histogram.set_data(edges, counts)
        self.histogram.set_threshold(self.model.threshold)
        self._refresh_bin_summary(self.model.threshold)
        ok = sum(1 for r in results if r.get("ok"))
        fail = len(results) - ok
        self._status("試跑完成：%d 顆（成功 %d、失敗 %d），耗時 %.1f 秒"
                     % (len(results), ok, fail, float(elapsed)))

    # ==================================================================== #
    # 對話框（測試不走這條路）
    # ==================================================================== #
    def _on_open_klarf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "開啟 KLARF", "", "KLARF (*.001 *.klarf *.txt);;所有檔案 (*)")
        if not path:
            return
        self.load_dataset_path(path)

    def _on_open_recipe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "開啟 Recipe", "", "Recipe JSON (*.json);;所有檔案 (*)")
        if not path:
            return
        self.load_recipe_path(path)

    def _on_save_recipe(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "存 Recipe", self.recipe_path or "recipe.json",
            "Recipe JSON (*.json);;所有檔案 (*)")
        if not path:
            return
        self.save_recipe_path(path)

    # ==================================================================== #
    # 關窗
    # ==================================================================== #
    def closeEvent(self, event) -> None:      # noqa: D102 - Qt hook
        self._preview_timer.stop()
        for worker in (self.preview_worker, self.trial_worker,
                       self.dataset_worker):
            try:
                worker.stop()
            except Exception:              # noqa: BLE001 — 關窗不准擋路
                pass
        super().closeEvent(event)
