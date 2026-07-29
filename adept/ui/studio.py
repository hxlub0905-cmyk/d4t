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
    QCheckBox,
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
    QProgressBar,
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
from .canvas import PipelineCanvas
from .gallery import make_thumb
from .region_check import MAX_CHECK, RegionCheckWindow, regions_of_node
from .template_dialog import TemplateDialog
from .results import ResultsWindow, summarize_run
from .scope import (
    is_supported_kind, recipe_is_supported, unsupported_kind_message,
    visible_steps,
)
from .viewmodel import RecipeModel, histogram, rebin
from .theme import DEFAULT_THEME, THEMES, apply_theme, current_theme
from .welcome import (
    RecipeLibraryDialog, WelcomeDialog, save_theme, welcome_disabled,
)
from .widgets import (
    FeatureTable,
    ImageView,
    LibraryPanel,
    ParamForm,
    PipelinePanel,
    ProfilePanel,
    VerdictChip,
)
from .workers import (
    DatasetLoadWorker, PreviewWorker, RegionCheckWorker, TrialWorker,
    _ThreadedWorker,
)

__all__ = ["StudioWindow", "ThumbWorker", "TEMPLATE_RECIPE", "DEFAULT_CACHE_DIR",
           "THUMB_CHANNEL_PRIORITY", "TAB_PREVIEW", "TAB_GALLERY",
           "DEMO_DIR", "DEMO_DEFECTS", "DEMO_SEED", "generate_demo_lot"]

#: 區域跨顆檢視的縮圖邊長（px）。
REGION_THUMB = 120

#: 卡片庫「ADC 判定」段固定顯示的 Score / Bin 項目。它不是 registry 裡的
#: step（每條 pipeline 天生就有一張 ScoreSpec），但三段式的心智模型要完整 ——
#: 使用者要能在庫裡看到「影像 → 算法 → ADC 判定」三段都有東西。點它 = 去編輯分數。
_SCORE_LIBRARY_KEY = "__score__"
_SCORE_LIBRARY_ENTRY = {
    "key": _SCORE_LIBRARY_KEY,
    "label": "Score / Bin",
    "category": "adc",
    "group": "adc",
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

#: 主視窗三欄的出廠寬度：卡片庫 | 流程+參數 | 單顆預覽。
#: F7-5 之後預覽拿到最寬的一欄（使用者要求「影像大一點、置中」），
#: 因為直方圖與 Gallery 都搬去 Results 視窗了。
COLUMN_SIZES = (256, 470, 674)

#: 「試跑筆數」的出廠值。載入資料集時會再夾成 ``min(這個值, 資料集顆數)`` ——
#: 對一份只有 24 顆的 lot 顯示 200 沒有任何意義，只會讓人以為自己看錯了。
DEFAULT_TRIAL_N = 200

#: 右欄分頁的索引 —— F7-5 之後右欄只剩單顆預覽，Gallery 搬進 Results 視窗。
#: 常數保留是為了不打壞外部呼叫端；``TAB_GALLERY`` 現在等同「開 Results 視窗」。
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
        # 開窗就先放好 Input 卡（F7-9）：空白畫布對不會寫 code 的人是一道
        # 「現在要幹嘛」的關卡，而答案永遠是同一個 —— 先載入影像。
        self.model = RecipeModel.starter()
        self.dataset: Optional[Any] = None
        self.trial_scores: List[float] = []
        self.trial_results: List[Dict[str, Any]] = []   # M5：Gallery / 輸出的來源
        self.defect_index: int = 0
        self.selected_node: Optional[str] = None
        self.recipe_path: Optional[str] = None

        self._preview_images: Dict[str, Any] = {}
        self._last_result: Optional[Any] = None
        self._user_stream: Optional[str] = None   # 使用者親手挑的影像流（會被保留）
        self._user_stream_b: Optional[str] = None  # 同上，並排的右邊那張
        self._compare_on = False         # 並排比對開著嗎（F7-8）
        self._view_syncing = False       # 正在把檢視狀態推給另一張圖
        self._syncing = False            # 程式在寫 widget（別回頭觸發 model）
        self._trial_t0 = 0.0
        self._items_by_id: Dict[str, Any] = {}    # defect_id -> DefectItem（縮圖用）
        self._score_filter: Optional[Any] = None  # 直方圖點出來的 (lo, hi)
        self._pending_warnings: List[Any] = []    # 跑前 lint 的警告（跑完才講）
        self._preview_epoch = 0                   # 預覽的世代（丟掉過期結果用）
        self._async_epoch = 0                     # 背景那筆出發時的世代
        self.welcome_dialog: Optional[Any] = None
        self.library_dialog: Optional[Any] = None
        self.region_window: Optional[Any] = None   # 區域跨顆檢視（F7-11）
        self.template_dialog: Optional[Any] = None  # 建模板對話框（F7-12）
        self._region_regions: List[str] = []

        # ---- 背景工作 ------------------------------------------------------
        self.dataset_worker = DatasetLoadWorker(self)
        self.preview_worker = PreviewWorker(self)
        self.trial_worker = TrialWorker(self)
        self.thumb_worker = ThumbWorker(self)
        self.region_check_worker = RegionCheckWorker(self)

        # ---- 去抖動計時器 --------------------------------------------------
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._on_preview_timeout)

        # ---- 介面 ----------------------------------------------------------
        self._build_toolbar()
        self._build_body()
        self.setStatusBar(QStatusBar(self))
        self._build_progress()

        self._wire_widgets()
        self._wire_workers()
        self.model.add_listener(self._on_model_changed)

        # F7-1：卡片庫只列目前輸入型別用得到的卡（見 adept/ui/scope.py）
        self.library.set_steps(
            visible_steps([s.describe() for s in list_steps()])
            + [_SCORE_LIBRARY_ENTRY])
        self._refresh_all()
        if self.model.node_order:
            # 起手卡直接選起來：右欄一開窗就是「可以動的東西」，
            # 而不是一句「請先從卡片庫挑一張卡」。
            self.select_node(self.model.node_order[0])
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
        # 主題切換：一顆字元鈕，不佔位子也找得到（偏好存 QSettings）
        self.btn_theme = self._tool_button(
            "◐", "Switch between the light and dark theme",
            self.toggle_theme)
        for b in (self.btn_open_klarf, self.btn_open_recipe,
                  self.btn_save_recipe, self.btn_examples,
                  self.btn_export, self.btn_help, self.btn_theme):
            bar.addWidget(b)

        spacer = QWidget(bar)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        self.lbl_trial_n = QLabel("First ", bar)
        bar.addWidget(self.lbl_trial_n)
        self.spin_trial_n = QSpinBox(bar)
        self.spin_trial_n.setRange(10, 5000)
        # 「First 200」旁邊沒有單位時，200 可以是任何東西（秒？百分比？）。
        self.spin_trial_n.setSuffix(" defects")
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

    def _build_progress(self) -> None:
        """狀態列右側的進度條（F7-7）。

        以前載入資料集與試跑都只有狀態列的一行字，那對「跑一批一萬顆」這種
        會等好幾分鐘的動作是不夠的 —— 使用者看不出還要多久、也看不出它到底
        在不在動。這條進度條在**閒著時完全隱藏**，不佔位子也不製造噪音。

        載入 KLARF 沒有可回報的百分比（``load_dataset`` 是一次呼叫），所以那個
        情況用**不定型**（range 0–0）的跑馬燈：它回答的是「還在動嗎」，
        而不是「還剩多久」——謊報一個假的百分比比不報還糟。
        """
        self.progress = QProgressBar(self)
        self.progress.setFixedWidth(220)
        self.progress.setTextVisible(True)
        self.progress.setVisible(False)
        # 明確狀態：``isVisible()`` 在視窗 show() 之前一律 False，
        # headless 測試會全部誤判（同 LibraryPanel 的 badge，見 widgets.py）。
        self._progress_on = False
        self.statusBar().addPermanentWidget(self.progress)

    def _progress_busy(self, label: str) -> None:
        """不定型跑馬燈（不知道總量時用）。"""
        self.progress.setRange(0, 0)
        self.progress.setFormat(str(label))
        self.progress.setVisible(True)
        self._progress_on = True

    def _progress_set(self, done: int, total: int, label: str = "%v / %m") -> None:
        self.progress.setRange(0, max(1, int(total)))
        self.progress.setValue(int(done))
        self.progress.setFormat(str(label))
        self.progress.setVisible(True)
        self._progress_on = True

    def _progress_done(self) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.progress.reset()
        self._progress_on = False

    def progress_visible(self) -> bool:
        """進度條現在看得到嗎（測試用）。"""
        return bool(self._progress_on)

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
        self.library.panel_toggled.connect(self._on_library_panel_toggled)

        # 中：流程畫布 + （參數表單 / 分數編輯）
        self.pipeline = PipelineCanvas(self)
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

        # 右：單顆預覽（F7-5：Gallery 與直方圖搬到 Results 視窗，
        #     主視窗只留「編流程 + 看單顆」，影像因此拿得到整欄高度）
        self.preview_pane = self._build_preview_pane()

        # Results 視窗（跑完才 show；先建好讓 histogram / gallery 一直有實體，
        # 這樣所有既有接線與測試都不用管它現在開著沒有）
        self.results = ResultsWindow(self)
        self.histogram = self.results.histogram
        self.gallery = self.results.gallery
        self.results.export_requested.connect(self.open_export_dialog)

        root = QSplitter(Qt.Horizontal, self)
        root.addWidget(self.library)
        root.addWidget(middle)
        root.addWidget(self.preview_pane)
        root.setStretchFactor(0, 0)
        root.setStretchFactor(1, 2)
        root.setStretchFactor(2, 4)
        root.setSizes(list(COLUMN_SIZES))
        self.top_splitter = root
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

        # 並排比對（F7-8）—— 預設關著，見 _set_compare 的說明
        self.compare_check = QCheckBox("Compare", pane)
        self.compare_check.setToolTip(
            "Show a second image stream side by side, with linked zoom and pan "
            "— useful when tuning Enhance cards, to check test and ref still "
            "match")
        self.stream_combo_b = QComboBox(pane)
        self.stream_combo_b.setToolTip("The stream shown on the right")
        self.stream_combo_b.setVisible(False)
        srow.addWidget(self.compare_check)
        srow.addWidget(self.stream_combo_b, 1)
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
        self.image_view_b = ImageView(pane)
        self.image_view_b.setVisible(False)
        images = QWidget(pane)
        irow = QHBoxLayout(images)
        irow.setContentsMargins(0, 0, 0, 0)
        irow.setSpacing(4)
        irow.addWidget(self.image_view, 1)
        irow.addWidget(self.image_view_b, 1)
        lay.addWidget(images, 3)

        # 模板定位卡的入口在**參數列裡**（F7-13），不在這裡。它是那個參數的值
        # 從哪來，不是一個預覽動作 —— 放在影像下方等於把「這個欄位怎麼填」的
        # 答案擺到半個螢幕外，而欄位本身看起來只是「還沒填」。

        # 「這個區域在整批上都對嗎」（F7-11）。跟曲線面板一樣平常收起來，
        # 只有選到會定義區域的卡片時才出現。
        self.btn_region_check = QPushButton("Check this region across defects…",
                                            pane)
        self.btn_region_check.setProperty("variant", "secondary")
        self.btn_region_check.setToolTip(
            "Draw this region on many defects at once. A setting that looks "
            "right on defect 1 can be completely off on defect 50 — the "
            "structure sits in a different place on every patch.")
        self.btn_region_check.setVisible(False)
        lay.addWidget(self.btn_region_check)

        # 投影曲線面板（F7-11）。**平常收起來** —— 它只有在編輯投影定位卡的
        # 時候才有意義，常駐會把好不容易爭取到的影像高度又吃掉一塊。
        self.profile_panel = ProfilePanel(pane)
        self.profile_panel.setVisible(False)
        lay.addWidget(self.profile_panel)

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
        self.pipeline.edge_added.connect(self._on_edge_added)
        self.pipeline.edge_removed.connect(self._on_edge_removed)

        self.param_form.param_edited.connect(self._on_param_edited)

        self.expr_edit.textEdited.connect(self._on_expr_edited)
        self.feature_combo.activated.connect(self._on_feature_chosen)
        self.threshold_spin.valueChanged.connect(self._on_threshold_spin)

        self.btn_prev.clicked.connect(lambda: self.step_defect(-1))
        self.btn_next.clicked.connect(lambda: self.step_defect(+1))
        self.defect_combo.currentIndexChanged.connect(self._on_defect_combo)
        self.btn_region_check.clicked.connect(lambda: self.open_region_check())
        self.param_form.action_requested.connect(self._on_param_action)
        self.stream_combo.currentTextChanged.connect(self._on_stream_changed)
        self.stream_combo_b.currentTextChanged.connect(self._on_stream_b_changed)
        self.compare_check.toggled.connect(self.set_compare)

        self.image_view.cursor_info.connect(self._on_cursor_info)
        self.image_view_b.cursor_info.connect(self._on_cursor_info)
        self.image_view.view_changed.connect(
            lambda s, o: self._link_views(self.image_view, self.image_view_b, s, o))
        self.image_view_b.view_changed.connect(
            lambda s, o: self._link_views(self.image_view_b, self.image_view, s, o))

        self.histogram.threshold_changed.connect(self._on_threshold_changed)
        self.histogram.threshold_committed.connect(self._on_threshold_committed)
        self.histogram.bar_clicked.connect(self._on_bar_clicked)

        self.gallery.thumbs_requested.connect(self._on_thumbs_requested)
        self.gallery.defect_activated.connect(self._on_defect_activated)
        self.gallery.selection_changed.connect(self._on_gallery_selection)

    def _wire_workers(self) -> None:
        self.dataset_worker.loaded.connect(self._on_dataset_loaded)
        self.dataset_worker.failed.connect(
            lambda msg: (self._progress_done(),
                         self._status("Could not load dataset: %s" % msg)))

        self.preview_worker.ready.connect(self._on_async_preview_ready)
        self.preview_worker.busy.connect(self._on_preview_busy)
        self.region_check_worker.ready.connect(self._on_region_ready)
        self.region_check_worker.failed.connect(
            lambda msg: self._status("Region check failed: %s" % msg))
        self.preview_worker.failed.connect(
            lambda msg: self._status("Preview failed: %s" % msg))

        self.trial_worker.progress.connect(self._on_trial_progress)
        self.trial_worker.done.connect(self._on_trial_done_async)
        self.trial_worker.failed.connect(
            lambda msg: (self._progress_done(),
                         self._status("Trial run failed: %s" % msg)))

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
        self._refresh_library_badges()
        self._refresh_region_button()
        self._schedule_preview()

    def _refresh_all(self) -> None:
        self._refresh_pipeline()
        self._sync_score_widgets()
        self._refresh_feature_combo()
        self.histogram.set_threshold(self.model.threshold)
        self._refresh_bin_summary(self.model.threshold)
        self._update_action_states()
        self._refresh_library_badges()

    def _refresh_library_badges(self) -> None:
        """把「pipeline 目前產出了哪些影像流」餵給卡片庫（F7-3）。

        卡片庫據此把前置條件未滿足的卡標成 ``needs diff`` 並調淡 ——
        **但仍然可以加**。卡片庫的順序不是執行順序，使用者可能先放卡再補上游。
        """
        try:
            streams = list(self.model.available_streams())
        except Exception:                # noqa: BLE001 — 顯示用，壞了就不標
            streams = []
        self.library.set_available_streams(streams)

    def _on_library_panel_toggled(self, open_: bool) -> None:
        """卡片區收起來時，把左欄的寬度真的還給工作區。

        只搬左欄與中欄之間的那條分隔線 —— 右欄（單顆預覽）的寬度不動，
        使用者自己調過的預覽大小不該因為收合卡片庫而被重設。
        """
        root = getattr(self, "root_splitter", None)
        if root is None:
            return
        sizes = list(root.sizes())
        if len(sizes) != 3 or sum(sizes) <= 0:
            return
        want = self.library.minimumWidth()
        delta = want - sizes[0]
        sizes[0], sizes[1] = want, max(240, sizes[1] - delta)
        root.setSizes(sizes)

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
        # 有些參數的值不是給人看的（模板是一整張影像的內容，六千多個字元）。
        # 直接串進摘要，那張卡的第三行就變成一段 base64 —— 元件會把它切掉，
        # 於是看到的是「template=gc1:iVBORw0KGg…」，既沒有資訊也擠掉了真正
        # 有用的參數。這種參數只講「有沒有設」。
        opaque = {p.name: p.type for p in step_cls.params if p.type == "template"}
        parts: List[str] = []
        for name, value in node.params.items():
            if name in defaults and defaults[name] == value:
                continue
            if name in opaque:
                parts.append("%s: set" % name)
            else:
                parts.append("%s=%s" % (name, _fmt(value)))
            if len(parts) >= 3:
                break
        return " · ".join(parts)

    def _node_problems(self) -> Dict[str, Any]:
        """每個節點最嚴重的一則 lint 發現（畫布上的警示標記用）。

        lint 本來就知道「這張卡缺模板」「這張卡指到不存在的區域」—— 但那個知識
        以前只在按下 Run trial 的那一刻出現一次。卡片在畫布上看起來永遠是好的，
        於是使用者要跑過才知道，而跑一次是好幾分鐘。
        """
        out: Dict[str, Any] = {}
        try:
            issues = self.model.validate()
        except Exception:                        # noqa: BLE001 — 顯示用，壞了就沒標記
            return out
        for issue in issues:
            nid = getattr(issue, "node_id", None)
            if not nid:
                continue
            prev = out.get(nid)
            # error 蓋過 warning；同級的取先出現的那則
            if prev is not None and not (prev[1] == "warning"
                                         and issue.level == "error"):
                continue
            out[nid] = (str(issue.detail or issue.title), str(issue.level))
        return out

    def _refresh_pipeline(self) -> None:
        problems = self._node_problems()
        nodes: List[Dict[str, Any]] = []
        for nid in self.model.node_order:
            node = self.model.nodes.get(nid)
            if node is None:
                continue
            step_cls = None
            try:
                step_cls = get_step(node.step)
                label, category = step_cls.label, step_cls.category
            except KeyError:
                label, category = node.step, ""
            # writes 用 kind-aware 版本解析：patch 的 Input 節點因此吐
            # ["test", "ref"]，畫布上就畫成兩個具名輸出埠（F7-7）。
            try:
                writes = list(step_cls.resolve_writes_for_kind(
                    node.params, self.model.kind))
            except Exception:              # noqa: BLE001 — 顯示用，壞了就空著
                writes = []
            try:
                reads = list(step_cls.resolve_reads(node.params))
            except Exception:              # noqa: BLE001
                reads = []
            nodes.append({
                "node_id": nid,
                "step_key": node.step,
                "label": label,
                "category": category,
                "enabled": bool(node.enabled),
                "summary": self._node_summary(node),
                "writes": writes,
                "reads": reads,
                "group": step_cls.resolve_group() if step_cls else "",
                "problem": problems.get(nid, ("", ""))[0],
                "problem_level": problems.get(nid, ("", "error"))[1],
            })
        self.pipeline.set_nodes(nodes, self.model.edges)
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
        self._status("Added “%s”%s" % (node_id, self._unmet_needs(node_id)))
        self.select_node(node_id)

    def _producers_of(self, stream: str) -> List[str]:
        """哪些卡片（用預設參數）會產出 ``stream``。"""
        out: List[str] = []
        for cls in visible_steps([s.describe() for s in list_steps()]) or []:
            key = str(cls.get("key", ""))
            try:
                step_cls = get_step(key)
                params = step_cls.validate_params({})
                writes = step_cls.resolve_writes_for_kind(params, self.model.kind)
            except Exception:              # noqa: BLE001 — 顯示用
                continue
            if stream in writes and step_cls.label:
                out.append(str(step_cls.label))
        return out

    def _unmet_needs(self, node_id: str) -> str:
        """剛加的卡少了什麼上游 —— 講成一句可以照做的話（回傳含前導空白）。

        以前只有卡片庫上一個 ``needs ref_aligned`` 的灰字 badge。對不會寫 code
        的人那句話沒有動作可做：他不知道 ``ref_aligned`` 是誰產的，也不知道
        「不然還可以怎麼辦」。最常踩到的就是 Subtract —— 它預設吃對位過的
        ``ref_aligned``，所以 Load 之後直接放 Subtract 一定缺一張上游。
        """
        node = self.model.nodes.get(str(node_id))
        if node is None:
            return ""
        try:
            step_cls = get_step(node.step)
            needs = list(step_cls.resolve_reads(node.params))
        except KeyError:
            return ""
        have = set(self.model.available_streams(before_node=str(node_id)))
        missing = [s for s in needs if s and s not in have]
        if not missing:
            return ""
        bits = []
        for s in missing:
            makers = self._producers_of(s)
            bits.append("“%s” (add %s first)" % (s, " or ".join(makers))
                        if makers else "“%s”" % s)
        return (" — but it still needs the image stream %s, or point it at one "
                "of: %s." % (", ".join(bits), ", ".join(sorted(have)) or "(none)"))

    def _on_node_toggled(self, node_id: str, enabled: bool) -> None:
        self.model.set_enabled(str(node_id), bool(enabled))

    def _on_move_requested(self, node_id: str, delta: int) -> None:
        self.model.move(str(node_id), int(delta))

    # ---- 畫布連線（F7-6）--------------------------------------------------
    def _on_edge_added(self, src: str, dst: str) -> None:
        """拉一條線。會造成循環時 model 回 False —— 那條線就不會出現。

        擋在這裡（而不是等執行時報錯）是刻意的：使用者看到的是「這條線拉不
        起來」，不是「拉起來之後整條 pipeline 壞掉」。

        「已經連著了」與「會成環」必須講成兩句話。把第二個埠（ref）拖到已經
        接了第一個埠（test）的節點上，是**很正常的操作** —— 而且畫面上兩條線
        本來就都在了。這種時候回一句「Cannot connect」，會讓一個成功的動作
        看起來像失敗。
        """
        src, dst = str(src), str(dst)
        if self.model.has_edge(src, dst):
            self._status("%s → %s is already connected — every image stream "
                         "they share is already drawn." % (src, dst))
        elif self.model.add_edge(src, dst):
            self._status("Connected %s → %s" % (src, dst))
        else:
            self._status("Cannot connect %s → %s — that would make the "
                         "pipeline loop back on itself." % (src, dst))

    def _on_edge_removed(self, src: str, dst: str) -> None:
        if self.model.remove_edge(str(src), str(dst)):
            self._status("Disconnected %s → %s" % (src, dst))

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
        self._refresh_region_button()
        self._schedule_preview()
        return True

    # ==================================================================== #
    # 主題（F7-2）
    # ==================================================================== #
    def toggle_theme(self) -> str:
        """light ⇄ dark；換完立刻重畫，偏好寫進 QSettings。

        所有顏色都走 ``theme.TOKENS``，但**自繪 widget 是在建構式裡取色的**
        （直方圖長條、節點卡色條、Gallery chip…），所以換膚之後要叫它們重畫。
        """
        order = list(THEMES)
        try:
            nxt = order[(order.index(current_theme()) + 1) % len(order)]
        except ValueError:                  # pragma: no cover — 主題名壞掉
            nxt = DEFAULT_THEME
        return self.set_theme(nxt)

    def set_theme(self, name: str) -> str:
        app = QApplication.instance()
        applied = apply_theme(app, name) if app is not None else str(name)
        save_theme(applied)
        self._repaint_for_theme()
        self._status("Theme: %s" % applied)
        return applied

    def _repaint_for_theme(self) -> None:
        """把在建構式裡吃過 token 的元件重建/重畫一次。"""
        self.library.set_steps(
            visible_steps([s.describe() for s in list_steps()])
            + [_SCORE_LIBRARY_ENTRY])
        self.library.refresh_colors()
        self._refresh_pipeline()
        self.gallery.refresh_styles()
        for w in (self.histogram, self.image_view, self.verdict,
                  self.feature_table, self.library, self.pipeline, self.gallery):
            w.update()

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
            self._autofill_output_prefix(node_id, str(name), value)

    #: 挑了區域就順手把輸出名填成區域的名字（F7-11）。
    _PREFIX_SOURCE = "roi"

    def _autofill_output_prefix(self, node_id: str, name: str, value: Any) -> None:
        """使用者挑了一個區域 → 輸出名還空著的話，就填成那個區域的名字。

        為什麼要自動填
        --------------
        「兩張量測卡的特徵會互相蓋掉」是一個**命名空間**的問題，而製程工程師沒有
        理由要懂那是什麼。但他做的動作已經表達了意圖 —— 他把這張卡指到 `epi`，
        那結果本來就該叫 `epi_...`。所以由工具把話補完。

        只在**空著**的時候填：使用者自己改過的名字不可以被蓋掉，
        不然「我明明改了它又跳回去」比沒有這個功能更糟。
        """
        if name != self._PREFIX_SOURCE:
            return
        node = self.model.nodes.get(node_id)
        if node is None or "output_prefix" not in node.params:
            return
        if str(node.params.get("output_prefix", "") or "").strip():
            return                       # 使用者已經自己命名過了
        wanted = str(value or "").strip()
        if not wanted:
            return
        try:
            self.model.set_param(node_id, "output_prefix", wanted)
        except ParamError:
            return                       # 區域名不能當變數名 -> 安靜跳過
        self.param_form.set_step(
            get_step(node.step).describe(), node.params,
            self.model.available_streams(before_node=node_id))
        self._status("Results from this card will be named “%s_…” so they do "
                     "not collide with another card measuring a different "
                     "region." % wanted)

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
        self._progress_busy("Loading %s…" % os.path.basename(path))
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
        self._progress_done()
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
        # 每要求一次預覽就換一個世代編號。背景那筆算完時如果編號已經不是它
        # 出發時那個，就代表畫面上的東西比它新 —— 那筆結果直接丟掉。
        self._preview_epoch += 1
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
        self._async_epoch = self._preview_epoch
        self.preview_worker.request(recipe, item, self.model.kind, upto_node=upto)
        return True

    def _on_async_preview_ready(self, result: Any) -> None:
        """背景預覽算完。**過期的結果直接丟掉。**

        `PreviewWorker` 只合併「還沒開跑」的請求；已經在跑的那一筆照樣會跑完並
        發出 ready。所以「先送出一筆背景預覽，接著又跑了一筆同步預覽」的時候，
        舊的那筆會**後到**，把新的畫面蓋掉 —— 使用者看到的是他剛剛那個動作
        之前的狀態，而且不會再更新，因為沒有人會再算一次。

        這個順序在實際操作裡並不罕見（點卡片 → 立刻改參數），
        只是以前的症狀是「影像閃一下」，不容易歸因；投影曲線面板讓它變成
        「面板空白」，才浮出來。
        """
        if getattr(self, "_async_epoch", 0) != self._preview_epoch:
            return
        self._on_preview_ready(result)

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
        self._refresh_profile_panel(ctx)

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

    #: 會產生投影曲線的卡片 key（面板只在編輯它的時候出現）。
    PROFILE_STEP = "roi_profile"

    # ==================================================================== #
    # 區域跨顆檢視（F7-11）
    # ==================================================================== #
    def selected_regions(self) -> List[str]:
        """選取的節點會定義哪些具名區域（不是 Region 卡就是空的）。"""
        node = self.model.nodes.get(self.selected_node or "")
        return regions_of_node(node) if node is not None else []

    #: 需要模板的卡片 key（那張卡的模板只能用這個對話框做出來）。
    TEMPLATE_STEP = "roi_template"

    def template_build_available(self) -> bool:
        """選取的卡片需要模板嗎（用明確狀態，不要問 widget 的可見性）。"""
        node = self.model.nodes.get(self.selected_node or "")
        return bool(node is not None and node.step == self.TEMPLATE_STEP)

    def _on_param_action(self, param_name: str) -> None:
        """某個參數說「我的值要用別的方式產生」（目前只有模板）。"""
        if str(param_name) == "template":
            self.open_template_dialog()

    def open_template_dialog(self) -> Optional[Any]:
        """開「從大圖建模板」對話框；接受之後把模板寫回這張卡。"""
        if not self.template_build_available():
            self._status("Select a Locate region by template card first.")
            return None
        node_id = self.selected_node
        dlg = TemplateDialog(self)
        dlg.accepted_template.connect(
            lambda text, axis, nid=node_id: self._apply_template(nid, text, axis))
        self.template_dialog = dlg
        dlg.show()
        return dlg

    def _apply_template(self, node_id: str, text: str, axis: str) -> None:
        """把疊好的模板寫進卡片參數（連同它適用的方向）。"""
        if node_id not in self.model.nodes:
            return
        try:
            self.model.set_param(node_id, "template", str(text))
            self.model.set_param(node_id, "locate_axis", str(axis))
        except ParamError as e:
            self._status("Could not store the template: %s" % e)
            return
        node = self.model.nodes[node_id]
        self.param_form.set_step(
            get_step(node.step).describe(), node.params,
            self.model.available_streams(before_node=node_id))
        self._status("Template stored in this recipe — it repeats along %s. "
                     "Now mark the region on the cell with the Region "
                     "left/top/width/height sliders." % axis)
        self._schedule_preview()

    def region_check_available(self) -> bool:
        """現在按得下「跨顆檢視」嗎。

        用明確狀態而不是 ``btn.isVisible()`` —— 視窗還沒 show 之前後者恆為
        False（CLAUDE.md §7 的老坑）。
        """
        return bool(self.selected_regions()) and bool(self._items())

    def _refresh_region_button(self) -> None:
        regions = self.selected_regions()
        has_data = bool(self._items())
        self.btn_region_check.setVisible(bool(regions))
        self.btn_region_check.setEnabled(bool(regions) and has_data)
        if regions and not has_data:
            self.btn_region_check.setToolTip(
                "No dataset loaded yet — use “Open KLARF…” first.")

    def open_region_check(self, n: Optional[int] = None,
                          sync: bool = False) -> bool:
        """把選取節點定義的區域畫到前 N 顆上。

        為什麼要有這個視窗
        ------------------
        區域設定對不對是一個**關於整批**的問題：patch 是以缺陷為中心裁的，
        所以結構在每張 patch 裡的位置本來就不一樣 —— 在第 1 顆剛好的框，
        第 50 顆可能整個偏掉。看單顆永遠看不出這件事。
        """
        regions = self.selected_regions()
        if not regions:
            self._status("Select a card that defines a region first.")
            return False
        items = self._items()
        if not items:
            self._status("No dataset loaded yet — use “Open KLARF…” first.")
            return False

        limit = int(n if n is not None else self.spin_trial_n.value())
        limit = max(1, min(limit, MAX_CHECK, len(items)))
        node = self.model.nodes[self.selected_node]
        source = str(node.params.get("source", "") or "") or None
        args = (self.model.to_recipe(), items[:limit], self.model.kind,
                self.selected_node, regions, REGION_THUMB, source)

        if self.region_window is None:
            self.region_window = RegionCheckWindow(self)
            self.region_window.defect_activated.connect(self._on_defect_activated)

        if sync:
            self._apply_region_results(regions,
                                       RegionCheckWorker.run_sync(*args))
            return True
        self._region_regions = regions
        if not self.region_check_worker.start(*args):
            self._status("Still checking the previous region — please wait.")
            return False
        self._status("Checking “%s” on %d defects…"
                     % (", ".join(regions), limit))
        return True

    def _on_region_ready(self, results: Any) -> None:
        self._apply_region_results(list(getattr(self, "_region_regions", []) or []),
                                   list(results or []))

    def _apply_region_results(self, regions: Sequence[str],
                              results: Sequence[Dict[str, Any]]) -> None:
        if self.region_window is None:
            self.region_window = RegionCheckWindow(self)
            self.region_window.defect_activated.connect(self._on_defect_activated)
        self.region_window.set_results(list(regions), list(results))
        self.region_window.show()
        self.region_window.raise_()
        self._status(self.region_window.summary_text())

    def _refresh_profile_panel(self, ctx: Any) -> None:
        """選到投影定位卡時，把**引擎這一次算出來的**曲線畫出來。

        面板不自己重算 —— 它讀 ``ctx.meta["profiles"]``。UI 自己再算一次是很容易
        發生的事，但那會讓「畫面上的框」跟「真的量下去的框」有機會不一樣，
        而那種 bug 幾乎不可能靠肉眼發現。
        """
        node = self.model.nodes.get(self.selected_node or "")
        if node is None or node.step != self.PROFILE_STEP:
            self.profile_panel.setVisible(False)
            self.profile_panel.set_data("", None)
            return
        name = str(node.params.get("roi_out", "") or "")
        profiles = dict(getattr(ctx, "meta", {}) or {}).get("profiles") or {}
        self.profile_panel.set_data(name, profiles.get(name))
        self.profile_panel.setVisible(True)

    def profile_panel_visible(self) -> bool:
        """面板現在開著嗎（用明確狀態，不要問 ``isVisible()``）。"""
        node = self.model.nodes.get(self.selected_node or "")
        return bool(node is not None and node.step == self.PROFILE_STEP)

    def _highlight_features(self, result: Any) -> Sequence[str]:
        """選取節點這一步新增/改值的特徵 → 在特徵表裡標色。"""
        nid = self.selected_node
        if not nid:
            return ()
        for tr in getattr(result, "traces", []) or []:
            if getattr(tr, "node_id", None) == nid:
                return list(getattr(tr, "features_added", {}) or {})
        return ()

    #: 「這張卡主要做在哪一條流上」的參數名（依優先順序）。
    #: Enhance 卡的慣例是 ``target``／``source`` 是主角，``also_apply`` 是附帶。
    _PRIMARY_PARAMS = ("target", "source")

    def _default_stream(self, images: Dict[str, Any]) -> str:
        """點一張卡時，左邊那張圖預設顯示哪一條流。

        規則是**這張卡的主要輸出**，不是「它寫過的最後一條流」。這兩者以前被
        當成同一件事（取 ``writes`` 的最後一個），但 Enhance 卡的
        ``resolve_writes`` 是 ``[target] + also_apply``，於是預設值一路是
        ``also_apply`` 的最後一項 —— 點 Normalize 就跳到 ``ref``。
        並排比對開著、右邊又停在 ``ref`` 的時候，畫面就變成左右兩張一模一樣的
        ref，每點一張卡都要手動切回來（F7-9 試用回饋 §4）。
        """
        nid = self.selected_node
        node = self.model.nodes.get(nid) if nid else None
        if node is not None:
            for name in self._PRIMARY_PARAMS:
                val = str(node.params.get(name, "") or "")
                if val in images:
                    return val
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
        want_b = (self._user_stream_b if self._user_stream_b in images
                  else self._default_compare_stream(images, want))
        if want_b == want:
            # 左右同一條流 = 兩張一模一樣的圖，那是並排唯一沒有意義的狀態。
            # 使用者親手挑的右邊也讓步 —— 他挑 ref 是為了「跟左邊比」，
            # 不是為了「看兩次 ref」。
            want_b = self._default_compare_stream(images, want)
        self._syncing = True
        try:
            self.stream_combo.clear()
            self.stream_combo.addItems(names)
            if want in names:
                self.stream_combo.setCurrentIndex(names.index(want))
            self.stream_combo_b.clear()
            self.stream_combo_b.addItems(names)
            if want_b in names:
                self.stream_combo_b.setCurrentIndex(names.index(want_b))
        finally:
            self._syncing = False

    def _default_compare_stream(self, images: Dict[str, Any], left: str) -> str:
        """並排的右邊預設放什麼：左邊是 test 就配 ref（反之亦然）。

        並排最常見的用途就是「這張 Enhance 卡有沒有把 test 和 ref 調成不一樣」，
        所以預設直接給那一對，不要讓使用者每次都自己挑。
        """
        pair = {"test": "ref", "ref": "test"}
        mate = pair.get(str(left))
        if mate and mate in images:
            return mate
        for k in ("ref", "diff", "test"):
            if k in images and k != left:
                return k
        for k in sorted(images):
            if k != left:
                return str(k)
        return str(left)

    def _show_current_stream(self) -> None:
        self.image_view.set_image(
            self._preview_images.get(self.stream_combo.currentText()))
        if self.compare_check.isChecked():
            self.image_view_b.set_image(
                self._preview_images.get(self.stream_combo_b.currentText()))

    def _on_stream_changed(self, text: str) -> None:
        if self._syncing:
            return
        self._user_stream = str(text) or None
        self._show_current_stream()

    def _on_stream_b_changed(self, text: str) -> None:
        if self._syncing:
            return
        self._user_stream_b = str(text) or None
        self._show_current_stream()

    # ---- 並排比對（F7-8）--------------------------------------------------
    def set_compare(self, on: bool) -> bool:
        """開／關並排的第二張圖。回傳最後的狀態。

        **預設是關的**，這是刻意的：F7-5 把 Gallery 與直方圖搬走，就是為了讓
        右欄的影像變大（使用者原話「影像最好大一點、置中」）。預設並排等於
        把剛爭取到的寬度再砍一半。真正需要並排的是**調 Enhance 卡的時候**
        （確認 test 與 ref 被調成一樣），那是一個明確的時機，一次點擊就到。

        兩張圖的縮放與平移連動 —— 沒有連動的並排要使用者自己把兩邊拖到同一個
        位置才比得起來，那還不如切換一張。
        """
        on = bool(on)
        if self.compare_check.isChecked() != on:
            self.compare_check.setChecked(on)     # 會再繞回這裡一次
            return self.compare_check.isChecked()
        self.image_view_b.setVisible(on)
        self.stream_combo_b.setVisible(on)
        self._compare_on = on
        if on:
            self._show_current_stream()
            scale, offset = self.image_view.view_state()
            self.image_view_b.set_view(scale, offset)
        else:
            self.image_view_b.set_image(None)
        return on

    def compare_enabled(self) -> bool:
        """並排現在開著嗎。用明確狀態而非 ``isVisible()``（視窗還沒 show 時後者恆假）。"""
        return bool(self._compare_on)

    def _link_views(self, source: Any, target: Any, scale: float, offset) -> None:
        """把 ``source`` 的檢視狀態推給 ``target``（單向，避免無限來回）。"""
        if not self._compare_on or self._view_syncing:
            return
        self._view_syncing = True
        try:
            target.set_view(scale, offset)
        finally:
            self._view_syncing = False

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

        # 跑之前先 lint（F7-9）。引擎的契約是「單顆出錯不殺整批」，所以一組接
        # 錯的卡片以前的下場是**跑完 200 顆、每一顆都失敗**：進度條走完、結果
        # 是空的、原因埋在每顆的錯誤訊息裡。同一份檢查 CLI 從 M1 就在用了，
        # 只是 Studio 一直沒接上來。只擋 error，warning 照跑。
        issues = self.model.validate()
        problems = [i for i in issues if i.level == "error"]
        if problems:
            first = problems[0]
            more = ("  (and %d more problem%s)"
                    % (len(problems) - 1, "" if len(problems) == 2 else "s")
                    if len(problems) > 1 else "")
            self._status("Cannot run — %s: %s%s"
                         % (first.title, first.detail, more))
            return False
        self._pending_warnings = [i for i in issues if i.level == "warning"]

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
        self._progress_set(0, limit, "%v / %m defects")
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
        self._progress_set(int(done), int(total), "%v / %m defects")
        self._status("Running: %d / %d" % (int(done), int(total)))

    def _on_trial_done_async(self, results: Any) -> None:
        self._apply_trial_results(list(results or []),
                                  time.time() - (self._trial_t0 or time.time()))

    def _apply_trial_results(self, results: Sequence[Dict[str, Any]],
                             elapsed: float) -> None:
        results = list(results or [])
        self._progress_done()
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
        msg = ("Run finished: %d defects (%d ok, %d failed) in %.1f s"
               % (len(results), ok, fail, float(elapsed)))
        # 跑之前的 lint 警告在這裡才講：跑之前講會被「Running: 3 / 200」洗掉。
        # 警告不擋執行，但它描述的是「跑得完、數字卻不是你以為的那個」——
        # 例如兩張量測卡撞名，後面那張把前面那張蓋掉了。
        warns = list(getattr(self, "_pending_warnings", []) or [])
        if warns:
            more = ("  (and %d more warning%s)"
                    % (len(warns) - 1, "" if len(warns) == 2 else "s")
                    if len(warns) > 1 else "")
            msg = "%s  ⚠ %s: %s%s" % (msg, warns[0].title, warns[0].detail, more)
        self._status(msg)
        # F7-5：結果一到就把 Results 視窗帶出來 —— 使用者按 Run 想看的就是這個
        self.results.set_summary(
            summarize_run(len(results), ok, elapsed, self.trial_scores))
        self.results.set_export_enabled(bool(results))
        self.results.status(msg)
        if results:
            self.results.present()

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
        """把 Results 視窗叫出來（Gallery 與分數分佈都在那裡）。"""
        self.results.present()

    def show_preview(self) -> None:
        """回到主視窗的單顆預覽。"""
        self.raise_()
        self.activateWindow()

    def results_visible(self) -> bool:
        """Results 視窗現在開著嗎（測試用）。"""
        return bool(self.results.isVisible())

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
        for dlg in (self.welcome_dialog, self.library_dialog, self.results):
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
