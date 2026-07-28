# ADEPT Studio 主視窗 — authored 2026-07-28 (M3 收尾).
"""``StudioWindow`` —— 把 M3 的元件、view-model 與背景工作接成一台可用的機器。

版面（全部用 QSplitter，使用者拉得動）::

    ┌ 工具列：開啟 KLARF／Recipe／存檔／範本／範例 recipe ｜ 輸出… ｜ 說明
    │         ｜ 試跑筆數 ▶試跑 ▶全跑                                      ┐
    ├──────────┬──────────────────────┬──────────────────────────────┤
    │ 卡片庫    │ 流程（PipelinePanel） │ ［單顆預覽］［Gallery］        │
    │ Library  │ ──────────────────── │  單顆：◀ ▶ 缺陷選單 / 影像流   │
    │ ~230px   │ 參數表單 / 分數編輯   │        ImageView              │
    │          │ （QStackedWidget）    │        特徵表 + 判定 chip     │
    │          │                      │  Gallery：縮圖牆（同屏比多顆）  │
    ├──────────┴──────────────────────┴──────────────────────────────┤
    │ 分數分佈直方圖（可拖門檻線、可點長條）                             │
    ├─────────────────────────────────────────────────────────────────┤
    │ 狀態列：進度 / 訊息                                              │
    └─────────────────────────────────────────────────────────────────┘

五條資料流（別搞混）
--------------------
1. **編輯流**：UI 事件 → :class:`~adept.ui.viewmodel.RecipeModel` 的方法 →
   model 通知 listener → 主視窗刷新 Pipeline/Score 顯示 + 排一次**去抖動
   （300ms）**的預覽。UI 元件自己**不改** model，也不直接呼叫引擎。
2. **預覽流**：:class:`~adept.ui.workers.PreviewWorker` 算一顆 defect →
   ``ready`` → 填影像流下拉 / ImageView / 特徵表 / 判定 chip。
3. **試跑流**：:class:`~adept.ui.workers.TrialWorker` 跑 N 顆 →
   ``done`` → 直方圖 + bin 摘要 + Gallery + 狀態列統計。
4. **縮圖流**（M5）：Gallery 捲到哪就要哪幾張縮圖 —— ``thumbs_requested(ids)``
   → :class:`ThumbWorker`（背景執行緒讀檔 + :func:`~adept.ui.gallery.make_thumb`）
   → ``ready(dict)`` → ``set_thumbs``。**解碼絕不在 GUI 執行緒**，而且忙碌時
   新的請求會合併進待跑集合（``request`` 只累積、不排隊、不阻塞）。
5. **輸出流**（M5）：工具列「輸出…」→ :class:`~adept.ui.export_dialog.ExportDialog`
   （試跑/全跑有結果才會亮）。

調參迴圈的兩半（M5 的重點）
---------------------------
直方圖點一根長條 → ``bar_clicked(lo, hi)`` → Gallery 只留那個分數區間並自動
切到 Gallery 分頁；再點同一根（或按掉 Gallery 上的條件 chip）就取消篩選。
Gallery 雙擊某顆 → ``defect_activated`` → 切回「單顆預覽」並跳到那顆。
門檻的「秒回」路徑仍然成立：拖曳中只用 :func:`~adept.ui.viewmodel.rebin`
重算 bin 數（**不寫 model、不重跑**），放開才 ``set_threshold``；
**點長條不會動到門檻**（見 ``HistogramWidget`` 的 click / drag 判定）。

測試友善 API（完全不開對話框，見 tests/test_ui_studio_smoke.py 與
tests/test_ui_studio_m5.py）：
:meth:`StudioWindow.load_dataset_path` / :meth:`~StudioWindow.load_recipe_path` /
:meth:`~StudioWindow.load_template` / :meth:`~StudioWindow.select_node` /
:meth:`~StudioWindow.set_defect_index` / :meth:`~StudioWindow.refresh_preview` /
:meth:`~StudioWindow.run_trial` / :meth:`~StudioWindow.save_recipe_path` /
:meth:`~StudioWindow.show_gallery` / :meth:`~StudioWindow.show_preview` /
:meth:`~StudioWindow.request_thumbs` / :meth:`~StudioWindow.open_export_dialog` /
:meth:`~StudioWindow.show_welcome` / :meth:`~StudioWindow.open_recipe_library` /
:meth:`~StudioWindow.run_demo`。
每個進入點都自我保護：沒有資料集 / 流程是空的 → 狀態列提示，不丟例外。

首次開啟導覽（M6）
------------------
:class:`~adept.ui.welcome.WelcomeDialog` 是產品的「上車處」：第一次開窗時
（``show_welcome_on_start`` 預設 ``None`` = 依 QSettings 判斷，且**跑測試時
一律不跳**）排一次非 modal 的顯示。它的三顆鈕只發訊號，動作由本視窗做 ——
其中「用範例資料試一次」就是 :meth:`~StudioWindow.run_demo`：產合成資料 →
載入 → 套 die-to-die 範本 → 試跑 → 切到 Gallery。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import adept.core.steps  # noqa: F401 — 觸發卡片註冊（Qt-free、便宜）
from adept.core.pipeline import ParamError, Recipe, get_step, list_steps

from .export_dialog import ExportDialog
from .gallery import GalleryPanel, make_thumb
from .scope import (
    is_supported_kind, recipe_is_supported, unsupported_kind_message,
    visible_steps,
)
from .viewmodel import RecipeModel, histogram, rebin
from .welcome import RecipeLibraryDialog, WelcomeDialog, welcome_disabled
from .widgets import (
    FeatureTable,
    HistogramWidget,
    ImageView,
    LibraryPanel,
    ParamForm,
    PipelinePanel,
    VerdictChip,
)
from .workers import DatasetLoadWorker, PreviewWorker, TrialWorker, _ThreadedWorker

__all__ = ["StudioWindow", "ThumbWorker", "TEMPLATE_RECIPE", "DEFAULT_CACHE_DIR",
           "THUMB_CHANNEL_PRIORITY", "TAB_PREVIEW", "TAB_GALLERY",
           "DEMO_DIR", "DEMO_DEFECTS", "DEMO_SEED", "generate_demo_lot"]

#: 卡片庫「ADC 判定」段固定顯示的 Score / Bin 項目。它不是 registry 裡的
#: step（每條 pipeline 天生就有一張 ScoreSpec），但三段式的心智模型要完整 ——
#: 使用者要能在庫裡看到「影像 → 算法 → ADC 判定」三段都有東西。點它 = 去編輯分數。
_SCORE_LIBRARY_KEY = "__score__"
_SCORE_LIBRARY_ENTRY = {
    "key": _SCORE_LIBRARY_KEY,
    "label": "Score / Bin",
    "category": "adc",
    "help": "Combine the measured features into a score and split into bins by a threshold — every pipeline has exactly one; click to edit it.",
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

#: 「用範例資料試一次」把合成 lot 產在哪（使用者自己的檔案一律不碰）。
DEMO_DIR = os.path.join(os.path.expanduser("~"), ".adept", "demo_lot")

#: 範例資料的 defect 數與 seed（少到一分鐘內跑得完，多到直方圖看得出形狀）。
DEMO_DEFECTS = 24
DEMO_SEED = 7

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

#: 「試跑筆數」的出廠值。載入資料集時會再夾成 ``min(這個值, 資料集顆數)`` ——
#: 對一份只有 24 顆的 lot 顯示 200 沒有任何意義，只會讓人以為自己看錯了。
DEFAULT_TRIAL_N = 200

#: 右欄分頁的索引（``right_tabs``）。
TAB_PREVIEW = 0
TAB_GALLERY = 1

#: Gallery 縮圖要用哪個 channel（依序找第一個有的；都沒有就用第一個 channel）。
THUMB_CHANNEL_PRIORITY = ("test", "single")

_FEATURE_PLACEHOLDER = "Insert feature ▾"
_SCORE_HELP = ("The score is an expression whose variables are the feature names "
               "produced by the pipeline above (e.g. snr_max, blob_area, "
               "glv_max). score >= threshold -> bin 1, otherwise bin 0. "
               "You can use + - * / ( ) and sqrt / abs / min / max.")


def _fmt(value: Any) -> str:
    """參數摘要用的短字串（float 去掉多餘的 0）。"""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return ("%g" % value)
    return str(value)


def thumb_channel(item: Any) -> Optional[str]:
    """這顆 defect 的縮圖要讀哪個 channel：``test`` → ``single`` → 第一個有的。"""
    images = dict(getattr(item, "images", {}) or {})
    for name in THUMB_CHANNEL_PRIORITY:
        if name in images:
            return name
    for name in images:
        return str(name)
    return None


def load_thumb(item: Any, size: int) -> Optional[Any]:
    """一顆 defect → ``size`` × ``size`` 的縮圖 ndarray（**Qt-free**，可跑在背景）。

    讀不到圖（沒有 channel / 檔案不見了 / TIFF 壞頁）一律回 ``None`` ——
    Gallery 會繼續畫「載入中…」的佔位磚，不會有人看到 traceback（鐵則 7 的精神）。
    """
    channel = thumb_channel(item)
    if channel is None:
        return None
    arr = item.load(channel)
    return make_thumb(arr, int(size))


def _running_under_pytest() -> bool:
    """現在是不是在跑測試（測試裡建 ``StudioWindow()`` 不准彈導覽）。"""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def _welcome_on_start_default() -> bool:
    """``show_welcome_on_start=None`` 時的預設：沒勾過「不再顯示」且不在測試中。"""
    if _running_under_pytest():
        return False
    try:
        return not welcome_disabled()
    except Exception:                   # noqa: BLE001 — 設定讀不到不該擋開窗
        return False


def generate_demo_lot(out_dir: Any = None, n: int = DEMO_DEFECTS,
                      seed: int = DEMO_SEED) -> Dict[str, str]:
    """產一批合成 EBI patch 資料（「用範例資料試一次」的第一步）。

    ``tools/make_sample.py`` 不是安裝進來的套件，所以這裡**延遲 import**：
    把 repo 的 ``tools/`` 補進 ``sys.path`` 再 import ``make_sample.generate``。
    延遲的另一個理由是它會拉進 tifffile —— 只按別的鈕的人不需要付這個成本。

    同一組 ``(n, seed)`` 產出的位元組完全相同，所以已經產過就直接沿用
    （第二次按這顆鈕是秒回的）。
    """
    out = str(out_dir) if out_dir is not None else DEMO_DIR
    klarf = os.path.join(out, "LOT_SYN.001")
    tiff = os.path.join(out, "LOT_SYN.tif")
    if os.path.isfile(klarf) and os.path.isfile(tiff):
        return {"out_dir": out, "klarf": klarf, "tiff": tiff}

    tools_dir = str(Path(__file__).resolve().parents[2] / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from make_sample import generate      # noqa: E402 — 刻意延遲（見 docstring）

    return generate(out, n=int(n), seed=int(seed))


class ThumbWorker(_ThreadedWorker):
    """Gallery 縮圖的背景解碼工（沿用 ``workers.py`` 的一次性 QThread 樣式）。

    為什麼要有它：``make_thumb`` 前面那一步是**讀檔 + 解 TIFF 頁**，在 GUI
    執行緒上做會讓捲動一格一格卡。所以 Gallery 只發「我要這些 id 的縮圖」，
    真正的解碼在這裡。

    **請求合併**：忙碌時 :meth:`request` 只是把 id 併進待跑集合（不排隊、
    不阻塞、也不會為每次捲動各開一條執行緒），目前這批做完再一次做掉。
    正在做的那批用 ``_inflight`` 記著，重複請求不會做第二次。

    訊號：``ready(dict)``（``{defect_id: ndarray}``，回到 GUI 執行緒）、
    ``failed(str)``（整批都讀不出來時才發，單顆失敗只是靜靜略過）。
    """

    ready = Signal(object)
    failed = Signal(str)

    #: 一批最多做幾張（做完立刻回 UI，剩下的下一批繼續 —— 縮圖要「陸續」出現）。
    BATCH = 48

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._pending: Dict[str, Any] = {}      # defect_id -> DefectItem
        self._inflight: List[str] = []
        self._size = 96

    # ---- 對外 -------------------------------------------------------------
    def request(self, jobs: Sequence[Any], size: int) -> None:
        """要求做這些縮圖；``jobs`` 是 ``(defect_id, DefectItem)`` 的序列。"""
        self._size = int(size)
        for did, item in jobs or ():
            did = str(did)
            if did in self._inflight:
                continue
            self._pending[did] = item
        if not self.is_running():
            self._launch()

    def pending_count(self) -> int:
        """還沒開始做的縮圖張數（測試 / statusbar 用）。"""
        return len(self._pending)

    @staticmethod
    def run_sync(jobs: Sequence[Any], size: int) -> Dict[str, Any]:
        """同步做一批縮圖（不開執行緒），回傳 ``{defect_id: ndarray}``。"""
        out: Dict[str, Any] = {}
        for did, item in jobs or ():
            try:
                arr = load_thumb(item, int(size))
            except Exception:               # noqa: BLE001 — 單顆壞掉不該殺整批
                continue
            if arr is not None:
                out[str(did)] = arr
        return out

    # ---- 內部 -------------------------------------------------------------
    def _launch(self) -> None:
        if not self._pending:
            return
        ids = list(self._pending)[:self.BATCH]
        batch = [(i, self._pending.pop(i)) for i in ids]
        self._inflight = [i for i, _ in batch]
        size = int(self._size)

        def work() -> None:
            out = ThumbWorker.run_sync(batch, size)
            if out:
                self.ready.emit(out)
            elif batch:
                self.failed.emit("Could not read thumbnails for %d defects "
                                 "(the image files may be missing)." % len(batch))

        self._start_job(work)

    def _job_finished(self) -> None:
        """一批做完（GUI 執行緒）：還有待做的就接著做。"""
        self._inflight = []
        if self._pending:
            self._launch()

    def _before_stop(self) -> None:
        self._pending = {}                  # 關窗：待做的縮圖全部作廢
        self._inflight = []


class StudioWindow(QMainWindow):
    """ADEPT Studio 主視窗（M3 組裝 + M5 Gallery / 直方圖聯動 / 輸出）。"""

    def __init__(self, parent: Optional[QWidget] = None,
                 show_welcome_on_start: Optional[bool] = None) -> None:
        """``show_welcome_on_start``：

        - ``True`` / ``False`` —— 明講要不要在開窗後跳導覽（測試用 ``False``）。
        - ``None``（預設）—— 自己判斷：使用者沒勾過「不再顯示」**且**現在不是
          在跑測試，才跳。**建構 StudioWindow() 在測試裡絕不可以彈出對話框**，
          所以這裡把 ``pytest``／``PYTEST_CURRENT_TEST`` 也當成「不要跳」。
          就算真的跳了，它也是非 modal 而且排在 event loop 的下一輪
          （``QTimer.singleShot(0, …)``），建構式永遠不會被卡住。
        """
        super().__init__(parent)
        self.setWindowTitle("ADEPT Studio")

        # ---- 狀態 ---------------------------------------------------------
        self.model = RecipeModel()
        self.dataset: Optional[Any] = None
        self.trial_scores: List[float] = []
        self.trial_results: List[Dict[str, Any]] = []   # M5：Gallery / 輸出的來源
        self.defect_index: int = 0
        self.selected_node: Optional[str] = None
        self.recipe_path: Optional[str] = None

        self._preview_images: Dict[str, Any] = {}
        self._last_result: Optional[Any] = None
        self._user_stream: Optional[str] = None   # 使用者親手挑的影像流（會被保留）
        self._syncing = False            # 程式在寫 widget（別回頭觸發 model）
        self._trial_t0 = 0.0
        self._items_by_id: Dict[str, Any] = {}    # defect_id -> DefectItem（縮圖用）
        self._score_filter: Optional[Any] = None  # 直方圖點出來的 (lo, hi)
        self.welcome_dialog: Optional[Any] = None
        self.library_dialog: Optional[Any] = None

        # ---- 背景工作 ------------------------------------------------------
        self.dataset_worker = DatasetLoadWorker(self)
        self.preview_worker = PreviewWorker(self)
        self.trial_worker = TrialWorker(self)
        self.thumb_worker = ThumbWorker(self)

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

        # F7-1：卡片庫只列目前輸入型別用得到的卡（見 adept/ui/scope.py）
        self.library.set_steps(
            visible_steps([s.describe() for s in list_steps()])
            + [_SCORE_LIBRARY_ENTRY])
        self._refresh_all()
        self._status("Ready — press “Help” for a guided start, or “Open KLARF…” "
                     "to load your data.")

        if show_welcome_on_start is None:
            show_welcome_on_start = _welcome_on_start_default()
        if show_welcome_on_start:
            # 非 modal + 排到下一輪 event loop：建構式永遠不會被對話框卡住
            QTimer.singleShot(0, lambda: self.show_welcome(force=False))

    # ==================================================================== #
    # 介面組裝
    # ==================================================================== #
    def _build_toolbar(self) -> None:
        """工具列（M7 精簡）。

        兩處刻意的取捨：

        * **「載入範本」併進「Templates…」** —— 舊版兩顆鈕做的是同一件事
          （都在載 ``examples/recipes/`` 底下的 JSON），而 die-to-die 對第一次
          用的人是行話。現在只留一個入口，範本庫自己把 die-to-die 排第一。
        * **「全跑」收進「Run trial」的下拉** —— 兩顆長得一樣的 ▶ 鈕擺在一起，
          新手分不出差別也不知道該按哪顆。主要動作只留一顆，破壞性比較大的
          「跑整批」降級成選單項目。
        """
        bar = QToolBar("Main actions", self)
        bar.setMovable(False)
        bar.setFloatable(False)
        self.toolbar = bar
        self.addToolBar(bar)

        self.btn_open_klarf = self._tool_button(
            "Open KLARF…", "Load a KLARF (the patch TIFF can be picked separately)",
            self._on_open_klarf)
        self.btn_open_recipe = self._tool_button(
            "Open Recipe…", "Load a recipe JSON", self._on_open_recipe)
        self.btn_save_recipe = self._tool_button(
            "Save Recipe…", "Save the current pipeline as a recipe JSON",
            self._on_save_recipe)
        self.btn_examples = self._tool_button(
            "Templates…",
            "Open the template library — every entry is a complete, runnable "
            "pipeline. Start here rather than from an empty pipeline.",
            self.open_recipe_library)
        self.btn_export = self._tool_button(
            "Export…",
            "Write these results back to KLARF, or produce reports and overlays",
            self.open_export_dialog)
        self.btn_help = self._tool_button(
            "Help", "Reopen the getting-started tour (includes “Try it with "
                    "sample data”)",
            lambda: self.show_welcome(force=True))
        for b in (self.btn_open_klarf, self.btn_open_recipe,
                  self.btn_save_recipe, self.btn_examples,
                  self.btn_export, self.btn_help):
            bar.addWidget(b)

        spacer = QWidget(bar)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        self.lbl_trial_n = QLabel("First ", bar)
        bar.addWidget(self.lbl_trial_n)
        self.spin_trial_n = QSpinBox(bar)
        self.spin_trial_n.setRange(10, 5000)
        self.spin_trial_n.setValue(DEFAULT_TRIAL_N)
        self.spin_trial_n.setToolTip(
            "How many defects a trial run covers (keep it small while tuning)")
        bar.addWidget(self.spin_trial_n)

        self.btn_trial = self._tool_button(
            "▶ Run trial", "Run the current pipeline over the first N defects "
                           "and show the score distribution",
            self._on_trial_clicked, primary=True)
        # 「跑整批」是同一顆鈕的次要動作：點主體 = 試跑，點箭頭才看得到它。
        menu = QMenu(self.btn_trial)
        self.act_run_all = QAction("Run all defects", menu)
        self.act_run_all.setToolTip("Run the whole dataset, not just the first N")
        self.act_run_all.triggered.connect(self._on_full_clicked)
        menu.addAction(self.act_run_all)
        self.btn_trial.setMenu(menu)
        self.btn_trial.setPopupMode(QToolButton.MenuButtonPopup)
        self.trial_menu = menu
        bar.addWidget(self.btn_trial)

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

        # 右：［單顆預覽］［Gallery］兩個分頁
        right = self._build_right_tabs()

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

        title = QLabel("Score / Bin decision", pane)
        title.setObjectName("paramTitle")
        lay.addWidget(title)

        head = QLabel("The last step of the pipeline: turn features into one score, then split into bins by a threshold.", pane)
        head.setObjectName("paramStepHelp")
        head.setWordWrap(True)
        lay.addWidget(head)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        lbl_expr = QLabel("Score expression", pane)
        lbl_expr.setObjectName("paramLabel")
        lbl_expr.setMinimumWidth(104)
        self.expr_edit = QLineEdit(pane)
        self.expr_edit.setPlaceholderText("e.g. glv_max + (glv_max - glv_q99)")
        self.expr_edit.setToolTip("Write an expression over feature names — the result is this defect's score")
        row1.addWidget(lbl_expr)
        row1.addWidget(self.expr_edit, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        lbl_ins = QLabel("Insert feature", pane)
        lbl_ins.setObjectName("paramLabel")
        lbl_ins.setMinimumWidth(104)
        self.feature_combo = QComboBox(pane)
        self.feature_combo.setToolTip("Pick a feature name to insert at the cursor in the expression")
        row2.addWidget(lbl_ins)
        row2.addWidget(self.feature_combo, 1)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        lbl_thr = QLabel("Decision threshold", pane)
        lbl_thr.setObjectName("paramLabel")
        lbl_thr.setMinimumWidth(104)
        self.threshold_spin = QDoubleSpinBox(pane)
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setRange(-1e9, 1e9)
        self.threshold_spin.setSingleStep(0.5)
        self.threshold_spin.setToolTip("score >= threshold -> bin 1 (the ones you want), otherwise bin 0")
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

    def _build_right_tabs(self) -> QWidget:
        """右欄：兩個分頁 —— 單顆看細節、Gallery 一次看一整批。

        分頁一定要「看得出來有兩個」：兩個分頁都寫明用途（不用圖示、不用
        只有一個字的標籤），並各自掛 tooltip 說明什麼時候該用哪一頁。
        """
        self.preview_pane = self._build_preview_pane()
        self.gallery = GalleryPanel(self)

        tabs = QTabWidget(self)
        tabs.setDocumentMode(False)
        tabs.setTabPosition(QTabWidget.North)
        tabs.addTab(self.preview_pane, "Single defect")
        tabs.addTab(self.gallery, "Gallery (compare many)")
        tabs.setTabToolTip(TAB_PREVIEW, "One defect at a time: image streams, feature values, verdict")
        tabs.setTabToolTip(TAB_GALLERY, "Thumbnails for the whole batch — scan "
                                        "with your eyes for mis-tuned cases "
                                        "(populated after a trial run)")
        tabs.setCurrentIndex(TAB_PREVIEW)
        self.right_tabs = tabs
        return tabs

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
        self.btn_prev.setToolTip("Previous defect")
        self.btn_next = QPushButton("▶", pane)
        self.btn_next.setObjectName("cardButton")
        self.btn_next.setFixedWidth(28)
        self.btn_next.setToolTip("Next defect")
        self.defect_combo = QComboBox(pane)
        self.defect_combo.setToolTip("Jump straight to a defect")
        self.defect_label = QLabel("(no dataset loaded)", pane)
        self.defect_label.setObjectName("paramHint")
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        nav.addWidget(self.defect_combo, 1)
        nav.addWidget(self.defect_label)
        lay.addLayout(nav)

        srow = QHBoxLayout()
        srow.setSpacing(6)
        lbl_stream = QLabel("Image stream", pane)
        lbl_stream.setObjectName("paramLabel")
        self.stream_combo = QComboBox(pane)
        self.stream_combo.setToolTip(
            "Which image stream to look at (test / ref / diff / snr_map …)")
        srow.addWidget(lbl_stream)
        srow.addWidget(self.stream_combo, 1)
        # 游標讀數有自己的位置（M7）。以前它是寫進狀態列的，於是滑鼠只要飄過
        # 影像，剛才那句「Trial run finished: …」就被 x/y/gray 洗掉了 ——
        # 狀態列該留給「使用者要讀的事件」，一直在刷的東西不該跟它搶同一格。
        self.cursor_label = QLabel("", pane)
        self.cursor_label.setObjectName("paramHint")
        self.cursor_label.setMinimumWidth(150)
        self.cursor_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cursor_label.setToolTip("Cursor position and gray level")
        srow.addWidget(self.cursor_label)
        lay.addLayout(srow)

        self.image_view = ImageView(pane)
        lay.addWidget(self.image_view, 3)

        self.feature_table = FeatureTable(pane)
        self.feature_table.setMinimumHeight(120)
        lay.addWidget(self.feature_table, 2)

        vrow = QHBoxLayout()
        vrow.setSpacing(6)
        self.verdict = VerdictChip(pane)
        vrow.addWidget(QLabel("Verdict", pane))
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
        self.histogram.bar_clicked.connect(self._on_bar_clicked)

        self.gallery.thumbs_requested.connect(self._on_thumbs_requested)
        self.gallery.defect_activated.connect(self._on_defect_activated)
        self.gallery.selection_changed.connect(self._on_gallery_selection)

    def _wire_workers(self) -> None:
        self.dataset_worker.loaded.connect(self._on_dataset_loaded)
        self.dataset_worker.failed.connect(
            lambda msg: self._status("Could not load dataset: %s" % msg))

        self.preview_worker.ready.connect(self._on_preview_ready)
        self.preview_worker.busy.connect(self._on_preview_busy)
        self.preview_worker.failed.connect(
            lambda msg: self._status("Preview failed: %s" % msg))

        self.trial_worker.progress.connect(self._on_trial_progress)
        self.trial_worker.done.connect(self._on_trial_done_async)
        self.trial_worker.failed.connect(
            lambda msg: self._status("Trial run failed: %s" % msg))

        self.thumb_worker.ready.connect(self._on_thumbs_ready)
        self.thumb_worker.failed.connect(self._status)

    # ==================================================================== #
    # 狀態列
    # ==================================================================== #
    def _status(self, msg: str) -> None:
        self.statusBar().showMessage(str(msg))

    def status_text(self) -> str:
        """目前狀態列文字（測試用）。"""
        return self.statusBar().currentMessage()

    def cursor_text(self) -> str:
        """目前的游標讀數（測試用）。"""
        return self.cursor_label.text()

    def _on_cursor_info(self, text: str) -> None:
        """游標讀數 → 預覽區自己的標籤（**不碰狀態列**，見 ``_build_preview_pane``）。"""
        self.cursor_label.setText(str(text or ""))

    # ==================================================================== #
    # model → UI
    # ==================================================================== #
    def _on_model_changed(self) -> None:
        """model 任何變動的統一入口（listener）。"""
        self._refresh_pipeline()
        self._sync_score_widgets()
        self.histogram.set_threshold(self.model.threshold)
        self._refresh_bin_summary(self.model.threshold)
        self._update_action_states()
        self._schedule_preview()

    def _refresh_all(self) -> None:
        self._refresh_pipeline()
        self._sync_score_widgets()
        self._refresh_feature_combo()
        self.histogram.set_threshold(self.model.threshold)
        self._refresh_bin_summary(self.model.threshold)
        self._update_action_states()

    # ---- 動作可用性（M7）--------------------------------------------------
    def _update_action_states(self) -> None:
        """按鈕的前置條件不滿足 → **變灰並在 tooltip 說明原因**。

        舊行為是「按下去才在狀態列說『還沒有載入資料集』」。狀態列在螢幕最下
        角，第一次用的人根本不會往那裡看 —— 對他而言就是「我按了，沒反應」。
        推廣鐵則要求：擋在前面，而且要講得出為什麼。

        這裡只碰 ``setEnabled`` / ``setToolTip``，不改 model、不觸發預覽，
        所以任何 refresh 路徑都可以放心呼叫。
        """
        n_items = len(self._items())
        has_steps = bool(self.model.node_order)
        can_run = bool(n_items) and has_steps

        if can_run:
            run_why = ""
        elif not n_items and not has_steps:
            run_why = "Load a KLARF and add at least one card first."
        elif not n_items:
            run_why = "No dataset loaded yet — use “Open KLARF…” first."
        else:
            run_why = "The pipeline is empty — add a card from the library first."

        self.btn_trial.setEnabled(can_run)
        self.btn_trial.setToolTip(
            run_why or "Run the current pipeline over the first %d defects and "
                       "show the score distribution" % int(self.spin_trial_n.value()))
        self.act_run_all.setEnabled(can_run)
        self.act_run_all.setToolTip(
            run_why or "Run all %d defects, not just the first %d"
                       % (n_items, int(self.spin_trial_n.value())))
        self.spin_trial_n.setEnabled(can_run)
        self.lbl_trial_n.setEnabled(can_run)

        self.btn_save_recipe.setEnabled(has_steps)
        self.btn_save_recipe.setToolTip(
            "Save the current pipeline as a recipe JSON" if has_steps
            else "Nothing to save yet — the pipeline is empty.")

        has_results = bool(self.trial_results)
        self.btn_export.setEnabled(has_results)
        self.btn_export.setToolTip(
            "Write these results back to KLARF, or produce reports and overlays"
            if has_results
            else "No results yet — run a trial first.")

    def _node_summary(self, node: Any) -> str:
        """最多 3 個「非預設」參數，渲染成 ``k=v`` 串起來。"""
        try:
            step_cls = get_step(node.step)
        except KeyError:
            return "(unknown card %s)" % node.step
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
            self._status("Editing the score / threshold")
            return
        try:
            node_id = self.model.add_step(str(step_key))
        except (KeyError, ParamError) as e:
            self._status("Could not add card: %s" % e)
            return
        self._status("Added “%s”" % node_id)
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
        self._status("Removed “%s”" % node_id)

    def select_node(self, node_id: str) -> bool:
        """選取一個節點：右邊換成它的參數表單，預覽跑到它為止。"""
        node_id = str(node_id)
        node = self.model.nodes.get(node_id)
        if node is None:
            self._status("No such step: “%s”." % node_id)
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
            self._status("Select a step in the pipeline before editing parameters.")
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
        self._status("Threshold %.3g (applied when you release the mouse)" % float(value))

    def _on_threshold_committed(self, value: float) -> None:
        """放開滑鼠：這時才寫回 model（會觸發刷新與預覽）。"""
        self.model.set_threshold(float(value))
        self._status("Threshold set to %.3g" % float(value))

    # ==================================================================== #
    # 資料集
    # ==================================================================== #
    def load_dataset_path(self, path: Any, tiff: Optional[Any] = None,
                          sync: bool = False) -> bool:
        """載入 KLARF（``sync=True`` 走同步路徑，給測試 / CLI 用）。"""
        path = str(path)
        tiff = None if tiff is None else str(tiff)
        if not os.path.isfile(path):
            self._status("File not found: %s" % path)
            return False
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync(path, tiff)
            except Exception as e:      # noqa: BLE001 — UI 邊界，一律回報
                self._status("Could not load dataset: %s: %s" % (type(e).__name__, e))
                return False
            return self._on_dataset_loaded(ds)
        if not self.dataset_worker.start(path, tiff):
            self._status("A dataset is already loading — please wait.")
            return False
        self._status("Loading: %s" % os.path.basename(path))
        return True

    def _on_dataset_loaded(self, dataset: Any) -> bool:
        # F7-1：型別要到載完才知道，所以擋在這裡而不是 load_dataset_path。
        # 擋下來時**不動既有狀態** —— 使用者手上原本那份資料集還在，
        # 開錯一個檔不會把他正在調的東西弄丟。
        kind = getattr(dataset, "kind", None)
        if not is_supported_kind(kind):
            self._status(unsupported_kind_message(kind))
            return False

        self.dataset = dataset
        items = list(getattr(dataset, "items", []) or [])
        self.defect_index = 0
        # 試跑筆數跟著資料集走：對一份 24 顆的 lot 顯示「First 200」只會讓人困惑
        if items:
            self.spin_trial_n.setValue(
                max(self.spin_trial_n.minimum(),
                    min(DEFAULT_TRIAL_N, len(items))))
        # 縮圖工只拿得到 defect_id，這張表是它回頭找 DefectItem 的唯一途徑
        self._items_by_id = {str(getattr(it, "defect_id", "")): it for it in items}
        # 換資料集 = 舊的結果與縮圖全部作廢
        self.trial_results = []
        self.trial_scores = []
        self._score_filter = None
        self.gallery.set_items([])

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
        self._update_action_states()
        warn = list(getattr(dataset, "warnings", []) or [])
        msg = "Loaded %d defects (input type %s)" % (
            len(items), getattr(dataset, "kind", "?"))
        if warn:
            msg += "   ! %s" % warn[0]
        self._status(msg)
        if items:
            self.refresh_preview(force=False)
        return True

    def _items(self) -> List[Any]:
        """目前資料集的 defect 清單（沒有資料集就是空的）。"""
        if not self.dataset:
            return []
        return list(getattr(self.dataset, "items", []) or [])

    def _current_item(self) -> Optional[Any]:
        items = self._items()
        if not items:
            return None
        i = max(0, min(int(self.defect_index), len(items) - 1))
        self.defect_index = i
        return items[i]

    def _update_defect_label(self) -> None:
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self.defect_label.setText("(no dataset loaded)")
            return
        i = max(0, min(int(self.defect_index), len(items) - 1))
        self.defect_label.setText(
            "%s · defect %d / %d" % (getattr(self.dataset, "kind", "?"),
                                     i + 1, len(items)))

    def set_defect_index(self, index: int) -> bool:
        """跳到第 ``index`` 顆 defect（超出範圍會夾住）。"""
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self._status("No dataset loaded yet — use “Open KLARF…” first.")
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
            self._status("Could not load recipe: %s: %s" % (type(e).__name__, e))
            return False
        kind = None
        ds_kind = str(getattr(self.dataset, "kind", "")) if self.dataset else ""
        if ds_kind and ds_kind in recipe.routes:
            kind = ds_kind
        self._apply_model(RecipeModel.from_recipe(recipe, kind=kind))
        self.recipe_path = path
        self.setWindowTitle("ADEPT Studio — %s" % self.model.recipe_id)
        n = len(self.model.node_order)
        self._status("Loaded recipe “%s” (%d steps, route %s)"
                     % (self.model.recipe_id, n, self.model.kind))
        if ds_kind and ds_kind not in recipe.routes:
            self._status("Loaded recipe “%s”, but it has no '%s' route — "
                         "preview and trial runs will fail."
                         % (self.model.recipe_id, ds_kind))
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
            self._status("Built-in template not found: %s" % path)
            return False
        return self.load_recipe_path(str(path))

    def save_recipe_path(self, path: Any) -> bool:
        """把目前 model 存成 recipe JSON。"""
        path = str(path)
        if not self.model.node_order:
            self._status("The pipeline is empty — nothing to save.")
            return False
        try:
            self.model.to_recipe().save(path)
        except Exception as e:          # noqa: BLE001 — UI 邊界
            self._status("Could not save: %s: %s" % (type(e).__name__, e))
            return False
        self.recipe_path = path
        self.model.dirty = False
        self._status("Saved: %s" % path)
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
                self._status("The pipeline is empty — add the first card from the library.")
            return False
        item = self._current_item()
        if item is None:
            if force:
                self._status("No dataset loaded yet — use “Open KLARF…” first.")
            return False

        recipe = self.model.to_recipe()
        upto = self.selected_node if self.selected_node in self.model.nodes else None
        if sync:
            try:
                result = PreviewWorker.run_sync(recipe, item, self.model.kind,
                                                upto_node=upto)
            except Exception as e:      # noqa: BLE001 — UI 邊界
                self._status("Preview failed: %s: %s" % (type(e).__name__, e))
                return False
            self._on_preview_ready(result)
            return True
        self.preview_worker.request(recipe, item, self.model.kind, upto_node=upto)
        return True

    def _on_preview_busy(self, busy: bool) -> None:
        if busy:
            self._status("Computing preview…")

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
            self._status("Preview problem: %s"
                         % (getattr(result, "error", None) or "unknown error"))
        elif self.selected_node:
            self._status("Preview: stopped after “%s” (%d image streams)"
                         % (self.selected_node, len(images)))
        else:
            self._status("Preview done (%d image streams)%s"
                         % (len(images),
                            "   score %.4g" % score if score is not None else ""))

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
            self._status("No dataset loaded yet — use “Open KLARF…” first.")
            return False
        if not self.model.node_order:
            self._status("The pipeline is empty — add a card before running.")
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
                self._status("Trial run failed: %s: %s" % (type(e).__name__, e))
                return False
            self._apply_trial_results(results, time.time() - t0)
            return True

        self._trial_t0 = time.time()
        if not self.trial_worker.start(recipe, self.dataset, limit,
                                       workers=workers, cache_dir=cdir):
            self._status("A run is already in progress — please wait.")
            return False
        self._status("Running: 0 / %d" % limit)
        return True

    def _on_trial_clicked(self) -> None:
        self.run_trial(int(self.spin_trial_n.value()), workers=TRIAL_WORKERS,
                       cache_dir=DEFAULT_CACHE_DIR)

    def _on_full_clicked(self) -> None:
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self._status("No dataset loaded yet — use “Open KLARF…” first.")
            return
        self.run_trial(len(items), workers=TRIAL_WORKERS,
                       cache_dir=DEFAULT_CACHE_DIR)

    def _on_trial_progress(self, done: int, total: int) -> None:
        self._status("Running: %d / %d" % (int(done), int(total)))

    def _on_trial_done_async(self, results: Any) -> None:
        self._apply_trial_results(list(results or []),
                                  time.time() - (self._trial_t0 or time.time()))

    def _apply_trial_results(self, results: Sequence[Dict[str, Any]],
                             elapsed: float) -> None:
        results = list(results or [])
        self.trial_results = results
        self.trial_scores = [r["score"] for r in results
                             if r.get("ok") and r.get("score") is not None]
        edges, counts = histogram(self.trial_scores)
        self.histogram.set_data(edges, counts)
        self.histogram.set_threshold(self.model.threshold)
        self._refresh_bin_summary(self.model.threshold)
        self._populate_gallery(results)
        self._update_action_states()
        ok = sum(1 for r in results if r.get("ok"))
        fail = len(results) - ok
        self._status("Run finished: %d defects (%d ok, %d failed) in %.1f s"
                     % (len(results), ok, fail, float(elapsed)))

    # ==================================================================== #
    # Gallery（M5）
    # ==================================================================== #
    def _populate_gallery(self, results: Sequence[Dict[str, Any]]) -> None:
        """試跑/全跑結果 → Gallery。縮圖一律先給 ``None``，之後背景補上。

        排序欄位 = ``score`` + 這批結果實際出現過的特徵名（沒跑到的特徵不會
        出現在下拉裡 —— 使用者只看得到「這一批真的有的東西」）。
        """
        results = list(results or [])
        feats: List[str] = []
        for r in results:
            for k in (r.get("features") or {}):
                if k not in feats:
                    feats.append(str(k))
        self.gallery.set_sort_keys(["score"] + sorted(feats))
        self.gallery.set_items([
            {
                "defect_id": str(r.get("defect_id", "")),
                "ok": bool(r.get("ok", True)),
                "score": r.get("score"),
                "bin": r.get("bin"),
                "features": dict(r.get("features") or {}),
                "thumb": None,
            }
            for r in results
        ])
        # 新的一批 = 分數分佈變了：舊的分數篩選一定要清掉，不然使用者會看到
        # 一個對不上新直方圖的區間（而且 chip 還掛在那裡）。
        self.gallery.clear_filter()
        self._score_filter = None

    def show_gallery(self) -> None:
        """切到 Gallery 分頁。"""
        self.right_tabs.setCurrentIndex(TAB_GALLERY)

    def show_preview(self) -> None:
        """切回「單顆預覽」分頁。"""
        self.right_tabs.setCurrentIndex(TAB_PREVIEW)

    def current_tab(self) -> int:
        """目前在哪個分頁（:data:`TAB_PREVIEW` / :data:`TAB_GALLERY`）——測試用。"""
        return int(self.right_tabs.currentIndex())

    # ---- 縮圖（永遠不在 GUI 執行緒解碼）------------------------------------
    def _on_thumbs_requested(self, ids: Any) -> None:
        self.request_thumbs(list(ids or []))

    def request_thumbs(self, ids: Sequence[str], sync: bool = False) -> int:
        """做這些 defect 的縮圖。``sync=True`` 直接算完（測試 / headless 用）。

        回傳實際排進去（或同步做好）的張數；認不得的 id 靜靜略過。
        """
        jobs = [(str(i), self._items_by_id[str(i)])
                for i in (ids or []) if str(i) in self._items_by_id]
        if not jobs:
            return 0
        size = int(self.gallery.thumb_size())
        if sync:
            mapping = ThumbWorker.run_sync(jobs, size)
            self._on_thumbs_ready(mapping)
            return len(mapping)
        self.thumb_worker.request(jobs, size)
        return len(jobs)

    def _on_thumbs_ready(self, mapping: Any) -> None:
        """背景做好的縮圖回到 GUI 執行緒 —— 只有這裡碰 Gallery。"""
        self.gallery.set_thumbs(dict(mapping or {}))

    # ---- Gallery 的互動 ---------------------------------------------------
    def _on_defect_activated(self, defect_id: str) -> None:
        """Gallery 雙擊某顆 → 切回單顆預覽並跳過去。"""
        did = str(defect_id)
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        index = None
        for i, it in enumerate(items):
            if str(getattr(it, "defect_id", "")) == did:
                index = i
                break
        self.show_preview()
        if index is None:
            self._status("Defect “%s” is not in the current dataset." % did)
            return
        self.set_defect_index(index)
        self._status("Jumped to defect “%s” (%d / %d)"
                     % (did, index + 1, len(items)))

    def _on_gallery_selection(self, ids: Any) -> None:
        self._status("%d selected" % len(list(ids or [])))

    # ---- 直方圖點長條 → Gallery 篩選 --------------------------------------
    def _on_bar_clicked(self, lo: float, hi: float) -> None:
        """點一根長條：只看那個分數區間；再點同一根就取消。

        「同一根」的判斷要連 Gallery 目前**真的還在篩**一起看 —— 使用者可能
        已經按掉 Gallery 上的條件 chip 了，那時候再點同一根當然是重新篩選。
        """
        rng = (float(lo), float(hi))
        if self._score_filter == rng and self.gallery.filter_text():
            self.gallery.clear_filter()
            self._score_filter = None
            self._status("Score filter cleared (showing all %d)"
                         % self.gallery.displayed_count())
            return
        self.gallery.filter_by_score_range(rng[0], rng[1])
        self._score_filter = rng
        self.show_gallery()
        self._status("Filtered to score %.3g–%.3g (%d defects)"
                     % (rng[0], rng[1], self.gallery.displayed_count()))

    # ==================================================================== #
    # 輸出（M5）
    # ==================================================================== #
    def open_export_dialog(self) -> Optional[Any]:
        """開輸出精靈；沒有結果就只在狀態列提示（不開空對話框）。"""
        if not self.trial_results:
            self._status("No results to export yet — run a trial first.")
            return None
        dlg = ExportDialog(
            self.trial_results,
            doc=getattr(self.dataset, "klarf", None),
            dataset=self.dataset,
            recipe=self.model.to_recipe() if self.model.node_order else None,
            parent=self)
        dlg.exported.connect(self._on_exported)
        self.export_dialog = dlg
        dlg.show()
        return dlg

    def _on_exported(self, summary: Any) -> None:
        outputs = list((summary or {}).get("outputs") or [])
        self._status("Export finished: %s"
                     % (", ".join(outputs) if outputs else "(no files)"))

    # ==================================================================== #
    # 首次開啟導覽 + 範例 recipe 庫（M6）
    # ==================================================================== #
    def show_welcome(self, force: bool = False) -> Optional[Any]:
        """開（或重開）首次導覽。

        ``force=False`` 時尊重「不再顯示」（勾過就回 ``None``）；工具列的
        「說明」一律 ``force=True``。對話框是**非 modal** 的，所以這個方法
        永遠會馬上回來 —— 測試可以直接拿回傳值來按鈕。
        """
        if not force and welcome_disabled():
            return None
        dlg = self.welcome_dialog
        if dlg is None:
            dlg = WelcomeDialog(self)
            dlg.demo_requested.connect(self._on_demo_requested)
            dlg.open_klarf_requested.connect(self._on_open_klarf)
            dlg.library_requested.connect(self.open_recipe_library)
            self.welcome_dialog = dlg
        dlg.show()
        dlg.raise_()
        return dlg

    def open_recipe_library(self) -> Optional[Any]:
        """開範例 recipe 庫；選了哪份就直接載進流程面板。"""
        dlg = self.library_dialog
        if dlg is None:
            dlg = RecipeLibraryDialog(parent=self)
            dlg.recipe_chosen.connect(self._on_recipe_chosen)
            self.library_dialog = dlg
        else:
            dlg.reload()
        if dlg.count() == 0:
            self._status("No templates found (examples/recipes/ is empty).")
        dlg.show()
        dlg.raise_()
        return dlg

    def _on_recipe_chosen(self, path: str) -> None:
        self.load_recipe_path(str(path))

    def _on_demo_requested(self) -> None:
        self.run_demo()

    def run_demo(self, out_dir: Optional[Any] = None, n: int = DEMO_DEFECTS,
                 sync: bool = True) -> bool:
        """「用範例資料試一次」的完整動作 —— 這顆鈕是整個產品的入口。

        產合成資料 → 載入資料集 → 載入 die-to-die 範本 → 試跑 → 切到
        Gallery。做完畫面上就是「有分數分佈的直方圖 + 一整牆縮圖」，
        使用者不必先懂任何東西。

        產資料那一段會拉進 numpy/tifffile 並寫幾百 KB 的檔，在慢一點的機器上
        會有一兩秒的停頓 —— 所以整段包在**等待游標**裡，畫面不會像當掉。
        每一步都自我保護：任何一步失敗只在狀態列說明原因並回 ``False``。
        """
        self._status("Preparing sample data…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            paths = generate_demo_lot(out_dir, n=int(n))
        except Exception as e:          # noqa: BLE001 — UI 邊界，一律回報
            self._status("Could not generate sample data: %s: %s" % (type(e).__name__, e))
            return False
        finally:
            QApplication.restoreOverrideCursor()

        if not self.load_dataset_path(paths["klarf"], sync=True):
            return False
        if not self.load_template():
            return False

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok = self.run_trial(int(n), workers=1, sync=bool(sync))
        finally:
            QApplication.restoreOverrideCursor()
        if not ok:
            return False

        self.show_gallery()
        self._status(
            "Sample run finished — the histogram below is the score "
            "distribution (drag the threshold line), and the wall of thumbnails "
            "is on the right. Next, use “Open KLARF…” to switch to your own data.")
        return True

    # ==================================================================== #
    # 對話框（測試不走這條路）
    # ==================================================================== #
    def _on_open_klarf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open KLARF", "", "KLARF (*.001 *.klarf *.txt);;All files (*)")
        if not path:
            return
        self.load_dataset_path(path)

    def _on_open_recipe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Recipe", "", "Recipe JSON (*.json);;All files (*)")
        if not path:
            return
        self.load_recipe_path(path)

    def _on_save_recipe(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Recipe", self.recipe_path or "recipe.json",
            "Recipe JSON (*.json);;All files (*)")
        if not path:
            return
        self.save_recipe_path(path)

    # ==================================================================== #
    # 關窗
    # ==================================================================== #
    def closeEvent(self, event) -> None:      # noqa: D102 - Qt hook
        self._preview_timer.stop()
        for dlg in (self.welcome_dialog, self.library_dialog):
            try:
                if dlg is not None:
                    dlg.close()
            except Exception:              # noqa: BLE001 — 關窗不准擋路
                pass
        for worker in (self.preview_worker, self.trial_worker,
                       self.dataset_worker, self.thumb_worker):
            try:
                worker.stop()
            except Exception:              # noqa: BLE001 — 關窗不准擋路
                pass
        super().closeEvent(event)
