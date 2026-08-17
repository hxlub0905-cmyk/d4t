# ADEPT Studio 主視窗 — authored 2026-07-28 (M3 收尾).
"""``StudioWindow`` —— 把 M3 的元件、view-model 與背景工作接成一台可用的機器。

版面（全部用 QSplitter，使用者拉得動）::

    ┌ 工具列：開啟 KLARF／Recipe／存檔／範本／範例 recipe ｜ 輸出… ｜ 說明
    │         ｜ 試跑筆數 ▶試跑 ▶全跑                                      ┐
    ├──────────┬──────────────────────┬──────────────────────────────┤
    │ 卡片庫    │ 流程（PipelineCanvas）│ ［單顆預覽］［Gallery］        │
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
:meth:`~StudioWindow.run_trial` /
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

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
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
from adept.core.pipeline.recipe import version_skew

from .export_dialog import ExportDialog
from .canvas import PipelineCanvas
from .inspectors import inspector_for
from .gallery import make_thumb
from .region_check import MAX_CHECK, RegionCheckWindow, regions_of_node
from .template_dialog import TemplateDialog
from .results import ResultsWindow, summarize_run
from . import scope
from .scope import (
    is_supported_kind, no_klarf_message, recipe_is_supported,
    unsupported_kind_message, visible_steps,
)
from .viewmodel import RecipeModel, accuracy_at, histogram, rebin
from .theme import DEFAULT_THEME, THEMES, apply_theme, current_theme
from .welcome import (
    RecipeLibraryDialog, WelcomeDialog, save_theme, welcome_disabled,
)
from .widgets import (
    FeatureTable,
    IconButton,
    ImageView,
    LibraryPanel,
    ParamForm,
    ProfilePanel,
    VerdictChip,
    _GlyphMixin,
    apply_button_cursors,
    small_button,
)


class _GlyphToolButton(_GlyphMixin, QToolButton):
    """工具列上會自己畫圖示的 QToolButton（``_tool_button(icon=…)`` 用）。"""

from .workers import (
    CalibrateWorker, DatasetLoadWorker, PreviewWorker, RegionCheckWorker,
    TrialWorker,
    _ThreadedWorker,
)

__all__ = ["StudioWindow", "ThumbWorker", "TEMPLATE_RECIPE", "DEFAULT_CACHE_DIR",
           "THUMB_CHANNEL_PRIORITY", "TAB_PREVIEW", "TAB_GALLERY",
           "DEMO_DIR", "DEMO_DEFECTS", "DEMO_SEED", "generate_demo_lot"]

#: 區域跨顆檢視的縮圖邊長（px）。
REGION_THUMB = 120

#: 預覽區那兩個下拉框的寬度上限（px）。
#:
#: 它們裝的是 defect id 與影像流名字，都很短。以前兩個都吃 ``stretch 1``，
#: 於是在寬螢幕上各自變成一個八百多 px、裡面只寫著「1」或「diff」的框 ——
#: 版面把最多的空間給了資訊量最少的東西。
DEFECT_COMBO_MAX = 220
STREAM_COMBO_MAX = 180

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

#: 「載入範本」讀的檔案。
#:
#: ``examples/`` 2026-08-16 整個移除（使用者：「範例 recipe 都先全部拿掉」），
#: 所以這個檔案**現在不存在** —— :meth:`StudioWindow.load_template` 會在狀態列
#: 說「Built-in template not found」並回 ``False``，不會炸。路徑刻意留著：
#: 範例庫回來的那一天，把 JSON 放回這個位置、
#: 把 :data:`adept.ui.scope.SHOW_SAMPLE_ENTRIES` 改成 ``True`` 就整組回來。
TEMPLATE_RECIPE = Path(__file__).resolve().parents[2] / "examples" / "recipes" \
    / "cross_regions.json"

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
        #: 這批資料的 ground truth（``{defect_id: {"is_real": bool}}``）。
        #: 載資料集時自動找 KLARF 旁邊的 ``ground_truth.json``；沒有就 None。
        self.ground_truth: Optional[Dict[Any, Any]] = None
        #: ``_point_at_stream`` 剛剛把線綁到哪個參數（F9-5b 的 ``dst_in``）。
        #: 它是那個函式的第二個回傳值，用屬性傳是為了不動既有呼叫端的形狀。
        self._bound_param: str = ""

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
        self.calibrate_worker = CalibrateWorker(self)
        self.calibrate_worker.ready.connect(self._on_calibrated)
        self.calibrate_worker.failed.connect(
            lambda msg: self._status("Measuring across the lot failed: %s"
                                     % msg, "error"))

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
        self._build_shortcuts()
        # 「滑過去變手指」以前是每個呼叫端自己記得要做的事，於是只做到一半。
        # 現在改成視窗建好之後掃一次（見 widgets.apply_button_cursors）。
        apply_button_cursors(self)
        self.model.add_listener(self._on_model_changed)

        # F7-1：卡片庫只列目前輸入型別用得到的卡（見 adept/ui/scope.py）
        self.library.set_steps(
            visible_steps([s.describe() for s in list_steps()])
            + [_SCORE_LIBRARY_ENTRY])
        self._refresh_all()
        self.pipeline.fit_later()
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
        """工具列（M7 精簡；F7-22 分組）。

        兩處刻意的取捨：

        * **「載入範本」併進「Templates…」** —— 舊版兩顆鈕做的是同一件事
          （都在載 ``examples/recipes/`` 底下的 JSON），而 die-to-die 對第一次
          用的人是行話。現在只留一個入口，範本庫自己把 die-to-die 排第一。
        * **「全跑」收進「Run trial」的下拉** —— 兩顆長得一樣的 ▶ 鈕擺在一起，
          新手分不出差別也不知道該按哪顆。主要動作只留一顆，破壞性比較大的
          「跑整批」降級成選單項目。

        分組（F7-22）
        -------------
        以前是七顆長得一模一樣的鈕排成一列，沒有任何分隔 —— 讀起來是一串等權重
        的東西，使用者得逐顆讀完才知道哪顆是自己要的。現在照**做什麼事**分四段，
        中間用分隔線：

            檔案（開/存） │ 起手與輸出 │ 復原 │ ……… │ 說明・主題 │ 試跑

        `Help` 與主題移到右邊：它們是**隨時可用但不屬於流程**的東西，混在檔案
        操作裡只會讓左邊那段變長。試跑仍然在最右邊 —— 它是這個畫面的主要動作。

        **復原／重做這一輪才長出按鈕。** F7-16 給了 Ctrl+Z / Ctrl+Shift+Z，
        但工具列上沒有對應的鈕 —— 而目標使用者是不寫 code 的工程師，
        「這個軟體能不能反悔」這件事不該只寫在快捷鍵裡。
        """
        bar = QToolBar("Main actions", self)
        bar.setMovable(False)
        bar.setFloatable(False)
        self.toolbar = bar
        self.addToolBar(bar)

        self.btn_open_klarf = self._tool_button(
            "Open KLARF…", "Load a KLARF (the patch TIFF can be picked separately)",
            self._on_open_klarf, icon="folder")
        # 一種 source 一個入口（F11 Input-2）。刻意**不**塞進上面那顆：這條路
        # 吃的東西不同（一個多頁 TIFF + 「一顆幾張」），而且它產出的資料集沒有
        # KLARF —— 寫不回 KLARF。把兩件事併成一顆鈕，使用者按下去之前分不出
        # 自己要的是哪一種。
        self.btn_open_stack = self._tool_button(
            "Open stack…",
            "Load a multi-page TIFF that has no KLARF: every N pages become "
            "one defect (N = the images per defect you enter). No KLARF means "
            "no coordinates and no write-back — CSV and Excel reports still work.",
            self._on_open_stack, icon="stack")
        self.btn_open_folder = self._tool_button(
            "Open folder…",
            "Load a folder of single images (no KLARF): every image file "
            "becomes one defect. No KLARF means no coordinates and no "
            "write-back — CSV and Excel reports still work.",
            self._on_open_folder, icon="folder_open")
        self.btn_open_recipe = self._tool_button(
            "Open Recipe…", "Load a recipe JSON", self._on_open_recipe,
            icon="document")
        self.btn_examples = self._tool_button(
            "Templates…",
            "Open the template library — every entry is a complete, runnable "
            "pipeline. Start here rather than from an empty pipeline.",
            self.open_recipe_library, icon="templates")
        # 範本庫目前是空的（``examples/`` 已移除），所以這顆鈕按下去只會開一個
        # 空對話框 —— 對不會寫 code 的目標使用者，那比沒有這顆鈕更糟。
        # **建出來再藏**，不是不建：版面量測、``_update_action_states``、既有測試
        # 都還指得到它，回復只要改 ``scope.SHOW_SAMPLE_ENTRIES``。
        self.btn_examples.setVisible(bool(scope.SHOW_SAMPLE_ENTRIES))
        self.btn_export = self._tool_button(
            "Export…",
            "Write these results back to KLARF, or produce reports and overlays",
            self.open_export_dialog, icon="export")
        # Export 是這條流程的**終點**，也是「跑完之後要做的那件事」—— 它跟旁邊
        # 那幾顆檔案操作不同級。所以給它 accent 的外框（不是填滿，填滿的是
        # Run trial）。這不是裝飾：工具列上唯一有顏色的兩顆，正好是使用者
        # 真正要按的那兩顆。
        self.btn_export.setProperty("variant", "secondary")
        self.btn_undo = self._tool_button(
            "", "Undo the last change", self.undo, icon="undo")
        self.btn_redo = self._tool_button(
            "", "Redo the change you just undid", self.redo, icon="redo")
        self.btn_help = self._tool_button(
            "Help", "Reopen the getting-started tour (includes “Try it with "
                    "sample data”)",
            lambda: self.show_welcome(force=True))
        # 主題切換：一顆字元鈕，不佔位子也找得到（偏好存 QSettings）
        self.btn_theme = self._tool_button(
            "", "Switch between the light and dark theme",
            self.toggle_theme, icon="theme")

        # 一段 = 一種事情；段與段之間一條分隔線。
        for group in ((self.btn_open_klarf, self.btn_open_stack,
                       self.btn_open_folder, self.btn_open_recipe),
                      (self.btn_examples, self.btn_export),
                      (self.btn_undo, self.btn_redo)):
            for b in group:
                bar.addWidget(b)
            bar.addSeparator()

        spacer = QWidget(bar)
        spacer.setObjectName("toolbarSpacer")
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        # 右邊：不屬於流程、但要隨時找得到的兩顆。
        bar.addWidget(self.btn_help)
        bar.addWidget(self.btn_theme)
        bar.addSeparator()

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
            "Run trial", "Run the current pipeline over the first N defects "
                         "and show the score distribution",
            self._on_trial_clicked, primary=True, icon="play")
        # 「跑整批」是同一顆鈕的次要動作：點主體 = 試跑，點箭頭才看得到它。
        menu = QMenu(self.btn_trial)
        self.act_run_all = QAction("Run all defects", menu)
        self.act_run_all.setToolTip("Run the whole dataset, not just the first N")
        self.act_run_all.triggered.connect(self._on_full_clicked)
        menu.addAction(self.act_run_all)
        self.trial_menu = menu

        # 箭頭是**第二顆真的按鈕**，不是 ``MenuButtonPopup``（F7-23 第二輪）。
        #
        # 以前這兩個動作是同一顆 QToolButton 的兩半，而那半邊的外觀完全歸 Qt
        # 管：它用自己的淺色按鈕樣式畫在我們的藍底上，也不理會圓角 —— 全 UI
        # 最重要的一顆鈕，右邊掛著一塊跟主題無關的東西。
        #
        # 補樣式補不起來：只要給 ``::menu-button`` 一個盒子（背景、邊框、圓角
        # **任一**），Qt 就把繪製整個交給 stylesheet，而 stylesheet 沒有
        # ``image`` 就不畫箭頭 —— 這個 repo 是純文字的（docs/FAB-VALIDATION.md）塞不了
        # 圖檔。實測只有 ``width`` 是安全的。同一條坑 F7-13 在
        # ``QComboBox::drop-down`` 上踩過，這次量到 ``::menu-button`` 上。
        #
        # 所以拆成兩顆普通按鈕，兩顆都是我們控制得了的。這顆**不設 menu**：
        # 設了 Qt 又會自己加一個下拉指示器，等於畫兩個箭頭。
        self.btn_trial_more = self._tool_button(
            "", "More ways to run — including the whole dataset",
            self._popup_trial_menu, primary=True, icon="chevron_down")

        # 兩顆**放進同一個容器**，中間只留 1px（F7-24 第二輪）。
        #
        # 分開放在工具列上時它們吃全域的 6px 間距，讀起來像兩顆不相干的按鈕 ——
        # 而箭頭是 ``Run trial`` 的次要動作，不是另一個功能。1px 的縫加上內側
        # 拉直的圓角（QSS 的 ``[seg]``）就是一個分段控制項：**一件事，兩個半邊**。
        #
        # 注意這跟 F7-23 拆掉 ``MenuButtonPopup`` 不衝突：那一輪要的是「這半邊的
        # 外觀歸我們管」，而這裡正是在管它 —— 差別在現在兩個半邊都是真的按鈕。
        self.btn_trial.setProperty("seg", "left")
        self.btn_trial_more.setProperty("seg", "right")
        group = QWidget(bar)
        group.setObjectName("toolbarGroup")
        glay = QHBoxLayout(group)
        glay.setContentsMargins(0, 0, 0, 0)
        glay.setSpacing(1)
        glay.addWidget(self.btn_trial)
        glay.addWidget(self.btn_trial_more)
        self.trial_group = group
        bar.addWidget(group)

    #: 鍵盤快捷鍵（F7-16）。以前一個都沒有 —— 而這是一個「一直在試」的工具，
    #: 存檔、跑一次、退回上一步是每分鐘都在做的事，每一次都要把手移到滑鼠、
    #: 找到那顆鈕、按下去。
    #:
    #: 每一組都照作業系統的慣例（Ctrl+S 存檔、Ctrl+Z 復原、Ctrl+0 回原尺寸），
    #: 不自己發明 —— 使用者的肌肉記憶是從別的軟體帶過來的，這裡不該重學。
    SHORTCUTS = (
        ("Ctrl+O", "open_klarf"), ("Ctrl+Shift+O", "open_recipe"),
        ("Ctrl+R", "run"),
        ("Ctrl+Z", "undo"), ("Ctrl+Shift+Z", "redo"), ("Ctrl+Y", "redo"),
        ("Ctrl+0", "zoom_reset"), ("Ctrl++", "zoom_in"), ("Ctrl+=", "zoom_in"),
        ("Ctrl+-", "zoom_out"), ("Ctrl+Shift+F", "zoom_fit"),
        ("Ctrl+F", "find_card"),
        ("Ctrl+Left", "prev_defect"), ("Ctrl+Right", "next_defect"),
    )

    def _build_shortcuts(self) -> None:
        handlers = {
            "open_klarf": self._on_open_klarf,
            "open_recipe": self._on_open_recipe,
            "run": self._on_trial_clicked,
            "undo": self.undo,
            "redo": self.redo,
            "zoom_reset": self.pipeline.reset_zoom,
            "zoom_in": lambda: self.pipeline.zoom_by(1.25),
            "zoom_out": lambda: self.pipeline.zoom_by(1 / 1.25),
            "zoom_fit": self.pipeline.fit,
            "find_card": self.focus_card_search,
            "prev_defect": lambda: self.step_defect(-1),
            "next_defect": lambda: self.step_defect(+1),
        }
        self._shortcuts = []
        for keys, name in self.SHORTCUTS:
            sc = QShortcut(QKeySequence(keys), self)
            sc.activated.connect(handlers[name])
            self._shortcuts.append(sc)

        # 按鍵存在還不夠 —— 使用者要**發現得到**。工具列的 tooltip 是他唯一
        # 會停留的地方，所以把快捷鍵寫進去（作業系統慣例：括號附在後面）。
        #
        # 註冊而不是「設一次」：``_update_action_states`` 每次 refresh 都會重寫
        # 這幾顆的 tooltip（「還沒有東西可以存」之類的原因），設一次的話第一次
        # refresh 就被蓋掉了。所以改成**設 tooltip 的那個動作自己會補上快捷鍵**。
        self._tip_keys = {
            id(self.btn_open_klarf): "Ctrl+O",
            id(self.btn_open_recipe): "Ctrl+Shift+O",
            id(self.btn_trial): "Ctrl+R",
            id(self.btn_empty_open): "Ctrl+O",
            # F7-22：這兩顆這一輪才長出來，快捷鍵 F7-16 就有了。
            id(self.btn_undo): "Ctrl+Z",
            id(self.btn_redo): "Ctrl+Shift+Z",
        }
        for w in (self.btn_open_klarf, self.btn_open_recipe,
                  self.btn_trial, self.btn_empty_open,
                  self.btn_undo, self.btn_redo):
            self._set_tip(w, w.toolTip())

    def _set_tip(self, widget: Any, text: str) -> None:
        """設 tooltip，並自動補上這顆鈕的快捷鍵。"""
        keys = getattr(self, "_tip_keys", {}).get(id(widget))
        widget.setToolTip("%s  (%s)" % (text, keys) if keys else str(text))

    def focus_card_search(self) -> None:
        """跳到卡片庫的搜尋框（收起來的話先展開）—— 與 rail 上的放大鏡同一條路。"""
        self.library.focus_search()

    # ---- 復原 / 重做 -------------------------------------------------------
    def undo(self) -> bool:
        """退回上一步。做不到的時候要**說出來** —— 按了 Ctrl+Z 卻什麼都沒發生，
        使用者第一個念頭是「這個工具有沒有壞」，不是「已經沒得退了」。"""
        if not self.model.undo():
            self._status("Nothing to undo.")
            return False
        self._status("Undone.")
        return True

    def redo(self) -> bool:
        if not self.model.redo():
            self._status("Nothing to redo.")
            return False
        self._status("Redone.")
        return True

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

        # 「跑到一半發現參數設錯」是最常見的情況，而一萬顆要好幾分鐘（F7-16）。
        # 引擎本來就支援中止（``run_batch`` 的 ``abort_check``、
        # ``TrialWorker.abort``）—— 只是以前沒有任何地方按得到它，
        # 於是使用者唯一的中止方式是把整個視窗關掉。
        self.btn_stop = QPushButton("Stop", self)
        self.btn_stop.setProperty("variant", "danger")
        self.btn_stop.setToolTip(
            "Stop this run. Defects already finished are kept — you get the "
            "results for them, not nothing.")
        self.btn_stop.setVisible(False)
        self.btn_stop.clicked.connect(self.stop_run)
        self.statusBar().addPermanentWidget(self.btn_stop)
        self._stop_on = False

    def _progress_busy(self, label: str) -> None:
        """不定型跑馬燈（不知道總量時用）。"""
        self.progress.setRange(0, 0)
        self.progress.setFormat(str(label))
        self.progress.setVisible(True)
        self._progress_on = True

    def _show_stop(self, on: bool) -> None:
        """中止鈕只在真的有東西在跑的時候出現（明確狀態，不問 widget）。"""
        self._stop_on = bool(on)
        self.btn_stop.setVisible(bool(on))
        self.btn_stop.setEnabled(bool(on))

    def stop_available(self) -> bool:
        return bool(self._stop_on)

    def stop_run(self) -> bool:
        """中止進行中的批次。已經跑完的那些顆**留著** —— 使用者按停止是想
        「不要再等了」，不是「把剛才那五分鐘丟掉」。"""
        if not self.trial_worker.is_running():
            return False
        self.trial_worker.abort()
        self.btn_stop.setEnabled(False)
        self._status("Stopping — keeping the defects that already finished…")
        return True

    def _progress_set(self, done: int, total: int, label: str = "%v / %m") -> None:
        self.progress.setRange(0, max(1, int(total)))
        self.progress.setValue(int(done))
        self.progress.setFormat(str(label))
        self.progress.setVisible(True)
        self._progress_on = True

    def _progress_done(self) -> None:
        self._show_stop(False)
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.progress.reset()
        self._progress_on = False

    def progress_visible(self) -> bool:
        """進度條現在看得到嗎（測試用）。"""
        return bool(self._progress_on)

    def _popup_trial_menu(self) -> None:
        """把「跑整批」的選單開在箭頭鈕正下方（貼齊左緣，像一般的下拉）。"""
        b = self.btn_trial_more
        self.trial_menu.popup(b.mapToGlobal(QPoint(0, b.height())))

    def _tool_button(self, text: str, tip: str, slot: Any,
                     primary: bool = False,
                     icon: Optional[str] = None) -> QToolButton:
        """工具列上的一顆鈕。``icon`` 給的是**自繪**圖示的名字（不是字元）。

        有文字又有圖示時（只有 ``Run trial``），圖示畫在左邊那一格 ——
        QSS 的 ``[hasGlyph="true"]`` 把左邊 padding 撐開，文字才不會疊上去。
        """
        b = _GlyphToolButton(self) if icon else QToolButton(self)
        b.setText(text)
        b.setToolTip(tip)
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        b.setCursor(Qt.PointingHandCursor)
        if primary:
            b.setObjectName("primary")
        if icon:
            b._init_glyph(icon, "left" if text else "center")
        b.clicked.connect(slot)
        return b

    def _build_body(self) -> None:
        # 左：卡片庫
        self.library = LibraryPanel(self)
        self.library.panel_toggled.connect(self._on_library_panel_toggled)

        # 中：流程畫布（上）+ 參數表單／分數編輯（下）。
        #
        # 版面史，因為它繞了一圈（F7-22 → F8-UI 抽屜 → 現在）：F7-22 讓參數
        # 預設收起、雙擊才攤開（畫布是主體）；F8-UI 第一輪改成畫布右緣的
        # 抽屜 —— 使用者當天就退了它：「pipeline 往右長，抽屜也吃右邊，兩個
        # 在搶同一個方向」。他拍板的形狀（D 案）是：**畫布會 zoom、又有
        # 彈出視窗，所以平面上只需要中上一塊**；大空間還給設定與影像。
        # 所以：上下切回來、比例反過來（畫布 2 / 設定 3）、設定**預設攤開**，
        # 「看全貌」由 zoom bar 的彈出視窗鈕承接（open_canvas_window）。
        self.pipeline = PipelineCanvas(self)
        # 主畫布是概覽條（D 案）：fit 的「全部看得完」贏過「副標讀得出」。
        # 讀細節的地方是下方設定區與彈出視窗（那份維持類別預設 0.7）。
        self.pipeline.MIN_FIT_SCALE = 0.5
        self.param_form = ParamForm(self)
        self.score_pane = self._build_score_pane()
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.param_form)     # index 0
        self.stack.addWidget(self.score_pane)     # index 1

        middle = QSplitter(Qt.Vertical, self)
        middle.addWidget(self.pipeline)
        middle.addWidget(self.stack)
        middle.setStretchFactor(0, 2)
        middle.setStretchFactor(1, 3)
        self.canvas_column = middle
        self._params_open = True
        # 比例在 showEvent 才真的套 —— setSizes 要有實際高度才算得出來
        #（isVisible 之前那些數字沒有意義，docs/PITFALLS.md 的老坑）。
        self._layout_ratio_applied = False
        #: 畫布的彈出視窗（沒開著是 None）。
        self._canvas_popout: Optional[Any] = None
        self._popout_view: Optional[PipelineCanvas] = None

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
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

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
        # 間距走 8px 節奏（F8-UI）：這一欄以前是 2/4/6px 各處自己挑，
        # 排在一起就是「差一點對齊」—— 比完全沒對齊更讓人覺得亂。
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.btn_prev = IconButton("prev", "Previous defect", pane, kind="icon")
        self.btn_next = IconButton("next", "Next defect", pane, kind="icon")
        self.defect_combo = QComboBox(pane)
        self.defect_combo.setToolTip("Jump straight to a defect")
        self.defect_label = QLabel("(no dataset loaded)", pane)
        self.defect_label.setObjectName("paramHint")
        # 下拉框**不吃 stretch**。它裝的是一個 defect id，而以前它拿了
        # ``stretch 1``，於是在寬螢幕上是一個 800px 寬、裡面寫著「1」的框，
        # 而真正有資訊的那句（``ebi_patch · defect 1 / 24``）被擠到最右邊。
        # 空間給誰，就是在說什麼比較重要。
        self.defect_combo.setMaximumWidth(DEFECT_COMBO_MAX)
        self.defect_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        nav.addWidget(self.defect_combo)
        nav.addWidget(self.defect_label, 1)
        lay.addLayout(nav)

        srow = QHBoxLayout()
        srow.setSpacing(8)
        lbl_stream = QLabel("Image stream", pane)
        lbl_stream.setObjectName("paramLabel")
        self.stream_combo = QComboBox(pane)
        self.stream_combo.setToolTip(
            "Which image stream to look at (test / ref / diff / snr_map …)")
        # 同上：影像流的名字是 ``test`` / ``ref`` / ``diff`` / ``snr_map``，
        # 最長也就那樣，不需要整列。
        self.stream_combo.setMaximumWidth(STREAM_COMBO_MAX)
        srow.addWidget(lbl_stream)
        srow.addWidget(self.stream_combo)

        # 並排比對（F7-8）—— 預設關著，見 _set_compare 的說明
        self.compare_check = QCheckBox("Compare", pane)
        self.compare_check.setToolTip(
            "Show a second image stream side by side, with linked zoom and pan "
            "— useful when tuning Enhance cards, to check test and ref still "
            "match")
        self.stream_combo_b = QComboBox(pane)
        self.stream_combo_b.setToolTip("The stream shown on the right")
        self.stream_combo_b.setVisible(False)
        self.stream_combo_b.setMaximumWidth(STREAM_COMBO_MAX)
        srow.addWidget(self.compare_check)
        srow.addWidget(self.stream_combo_b)
        srow.addStretch(1)
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
        irow.setSpacing(8)
        irow.addWidget(self.image_view, 1)
        irow.addWidget(self.image_view_b, 1)

        # 還沒載資料時，畫面上最大的一塊是**一片黑**，角落有一行極小的
        # 「(no dataset loaded)」（F7-15）。首啟導覽關掉之後就沒有任何東西告訴
        # 使用者下一步要做什麼 —— 而「下一步」只有兩個，就把那兩個放在這裡。
        self.empty_state = QWidget(pane)
        estack = QVBoxLayout(self.empty_state)
        estack.addStretch(1)
        title = QLabel("No data loaded yet", self.empty_state)
        title.setObjectName("paramTitle")
        title.setAlignment(Qt.AlignCenter)
        estack.addWidget(title)
        # 這句話要跟旁邊實際看得到的鈕一致 —— 範例資料那顆收起來的時候還講
        # 「or try the tool with generated sample data」，使用者會去找一顆不在
        # 畫面上的鈕。
        why = QLabel("Open a KLARF to see your patches here, or try the tool "
                     "with generated sample data first."
                     if scope.SHOW_SAMPLE_ENTRIES else
                     "Open a KLARF to see your patches here.", self.empty_state)
        why.setObjectName("paramHint")
        why.setAlignment(Qt.AlignCenter)
        why.setWordWrap(True)
        # 留一個名字：這句話必須跟旁邊看得到的鈕一致，而那是測得出來的
        # （`test_nothing_on_screen_points_at_a_button_that_is_not_there`）。
        self.empty_state_hint = why
        estack.addWidget(why)
        brow = QHBoxLayout()
        brow.addStretch(1)
        self.btn_empty_open = QPushButton("Open KLARF…", self.empty_state)
        self.btn_empty_open.setObjectName("primary")
        brow.addWidget(self.btn_empty_open)
        self.btn_empty_sample = QPushButton("Try it with sample data",
                                            self.empty_state)
        self.btn_empty_sample.setProperty("variant", "secondary")
        # 見 btn_examples：demo 會產出資料卻載不到 pipeline（範本庫已移除），
        # 所以整個入口先收起來。同一個開關管兩顆。
        self.btn_empty_sample.setVisible(bool(scope.SHOW_SAMPLE_ENTRIES))
        brow.addWidget(self.btn_empty_sample)
        brow.addStretch(1)
        estack.addLayout(brow)
        estack.addStretch(1)

        self.image_stack = QStackedWidget(pane)
        self.image_stack.addWidget(self.empty_state)      # index 0
        self.image_stack.addWidget(images)                # index 1
        lay.addWidget(self.image_stack, 3)

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
        # 投影曲線面板搬進卡片儀表（F7-17）：它本來就是「這張卡自己的儀表」，
        # 只是 F7-11 當時直接掛在這裡，變成一條跟儀表機制平行的路。兩條並存的
        # 下場是加新面板的人不知道走哪一條，然後兩邊各長一半。

        # 右下角那一塊：**選哪張卡就換成那張卡的儀表**（F7-17）。
        # 原本固定是一張「特徵 / 數值」表 —— 問題不是它佔位子，是那些數字沒有
        # 辦法判讀（`blob_dist_center 11.170` 是大還是小？），而且使用者在問的
        # 問題**每張卡都不一樣**。特徵表仍然留著，用切換列回去。
        self.feature_table = FeatureTable(pane)
        self.feature_table.setMinimumHeight(120)

        self.inspector_host = QWidget(pane)
        ihost = QVBoxLayout(self.inspector_host)
        ihost.setContentsMargins(0, 0, 0, 0)
        ihost.setSpacing(2)
        self.inspector_summary = QLabel("", self.inspector_host)
        self.inspector_summary.setObjectName("paramHint")
        self.inspector_summary.setWordWrap(True)
        self.inspector_slot = QVBoxLayout()
        self.inspector_slot.setContentsMargins(0, 0, 0, 0)
        ihost.addLayout(self.inspector_slot, 1)
        ihost.addWidget(self.inspector_summary)
        self._inspector: Optional[Any] = None

        self.bottom_stack = QStackedWidget(pane)
        self.bottom_stack.addWidget(self.inspector_host)      # index 0
        self.bottom_stack.addWidget(self.feature_table)       # index 1

        tabs = QHBoxLayout()
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(4)
        self.btn_tab_card = small_button("Card", parent=pane, shape="wide")
        self.btn_tab_features = small_button("Features", parent=pane, shape="wide")
        for i, b in enumerate((self.btn_tab_card, self.btn_tab_features)):
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, k=i: self.show_bottom_page(k))
            tabs.addWidget(b)
        tabs.addStretch(1)
        lay.addLayout(tabs)
        lay.addWidget(self.bottom_stack, 2)

        vrow = QHBoxLayout()
        vrow.setSpacing(8)
        self.verdict = VerdictChip(pane)
        vrow.addWidget(QLabel("Verdict", pane))
        vrow.addWidget(self.verdict)
        vrow.addStretch(1)
        lay.addLayout(vrow)

        return pane

    # ==================================================================== #
    # 訊號接線
    # ==================================================================== #
    def _wire_canvas(self, view: PipelineCanvas) -> None:
        """把一份畫布接上同一批 handler。

        主視窗的畫布與彈出視窗的畫布走**完全相同**的接線 —— 差一條，
        兩個視窗的行為就分家（在這邊拉得動的線在那邊拉不動），而且沒有
        訊息會講出差在哪。"""
        view.node_selected.connect(self.select_node)
        view.node_activated.connect(self._on_node_activated)
        view.card_dropped.connect(self._on_card_dropped)
        view.node_toggled.connect(self._on_node_toggled)
        view.move_requested.connect(self._on_move_requested)
        view.remove_requested.connect(self._on_remove_requested)
        view.score_clicked.connect(self.show_score_page)
        view.edge_added.connect(self._on_edge_added)
        view.edge_removed.connect(self._on_edge_removed)
        view.popout_requested.connect(self.open_canvas_window)

    def _wire_widgets(self) -> None:
        self.library.add_requested.connect(self._on_add_requested)

        self._wire_canvas(self.pipeline)

        self.param_form.param_edited.connect(self._on_param_edited)

        self.expr_edit.textEdited.connect(self._on_expr_edited)
        self.feature_combo.activated.connect(self._on_feature_chosen)
        self.threshold_spin.valueChanged.connect(self._on_threshold_spin)

        self.btn_prev.clicked.connect(lambda: self.step_defect(-1))
        self.btn_next.clicked.connect(lambda: self.step_defect(+1))
        self.defect_combo.currentIndexChanged.connect(self._on_defect_combo)
        self.btn_region_check.clicked.connect(lambda: self.open_region_check())
        self.btn_empty_open.clicked.connect(self._on_open_klarf)
        self.btn_empty_sample.clicked.connect(self._on_demo_requested)
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
                         self._status("Could not load dataset: %s" % msg, "error")))

        self.preview_worker.ready.connect(self._on_async_preview_ready)
        self.preview_worker.busy.connect(self._on_preview_busy)
        self.region_check_worker.ready.connect(self._on_region_ready)
        self.region_check_worker.failed.connect(
            lambda msg: self._status("Region check failed: %s" % msg, "error"))
        self.preview_worker.failed.connect(
            lambda msg: self._status("Preview failed: %s" % msg, "error"))

        self.trial_worker.progress.connect(self._on_trial_progress)
        self.trial_worker.done.connect(self._on_trial_done_async)
        self.trial_worker.failed.connect(
            lambda msg: (self._progress_done(),
                         self._status("Trial run failed: %s" % msg, "error")))

        self.thumb_worker.ready.connect(self._on_thumbs_ready)
        self.thumb_worker.failed.connect(self._status)

    # ==================================================================== #
    # 狀態列
    # ==================================================================== #
    def _status(self, msg: str, level: str = "info") -> None:
        """狀態列。``level="error"`` 會把它變成紅字（F7-15）。

        狀態列是**唯一**會講出「這件事沒成功」的地方（lint 擋下試跑、卡片加不
        進去、模板存不起來），而它以前跟「Added denoise」用完全一樣的灰字，
        在畫面最左下角。使用者按了一顆鈕、什麼都沒發生、而唯一的解釋長得跟
        剛才那句成功訊息一模一樣 —— 那等於沒有講。
        """
        bar = self.statusBar()
        bar.setProperty("level", "error" if level == "error" else "info")
        bar.style().unpolish(bar)
        bar.style().polish(bar)
        bar.showMessage(str(msg))

    def status_text(self) -> str:
        """目前狀態列文字（測試用）。"""
        return self.statusBar().currentMessage()

    def status_level(self) -> str:
        """狀態列現在是不是在報錯（用明確狀態，不要去比對顏色）。"""
        return str(self.statusBar().property("level") or "info")

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

        # 沒有資料時，最大的那一塊要說得出下一步（F7-15）
        self.image_stack.setCurrentIndex(1 if n_items else 0)

        if can_run:
            run_why = ""
        elif not n_items and not has_steps:
            run_why = "Load a KLARF and add at least one card first."
        elif not n_items:
            run_why = "No dataset loaded yet — use “Open KLARF…” first."
        else:
            run_why = "The pipeline is empty — add a card from the library first."

        self.btn_trial.setEnabled(can_run)
        self._set_tip(self.btn_trial,
                      run_why or "Run the current pipeline over the first %d "
                                 "defects and show the score distribution"
                      % int(self.spin_trial_n.value()))
        # 箭頭鈕與主鈕同進退：選單裡唯一那一項擋住的時候，還打得開一個
        # 「每一項都是灰的」的選單，等於讓使用者多按一次才知道不能按。
        self.btn_trial_more.setEnabled(can_run)
        self._set_tip(self.btn_trial_more,
                      run_why or "More ways to run — including the whole dataset")
        self.act_run_all.setEnabled(can_run)
        self.act_run_all.setToolTip(
            run_why or "Run all %d defects, not just the first %d"
                       % (n_items, int(self.spin_trial_n.value())))
        self.spin_trial_n.setEnabled(can_run)
        self.lbl_trial_n.setEnabled(can_run)

        # 復原／重做：沒得退的時候要**看得出來**沒得退（F7-22）。
        # 這兩顆是新長出來的鈕，而 model 早就答得出這兩個問題了。
        self.btn_undo.setEnabled(self.model.can_undo())
        self._set_tip(self.btn_undo,
                      "Undo the last change" if self.model.can_undo()
                      else "Nothing to undo yet.")
        self.btn_redo.setEnabled(self.model.can_redo())
        self._set_tip(self.btn_redo,
                      "Redo the change you just undid" if self.model.can_redo()
                      else "Nothing to redo.")

        has_results = bool(self.trial_results)
        self.btn_export.setEnabled(has_results)
        self.btn_export.setToolTip(
            "Write these results back to KLARF, or produce reports and overlays"
            if has_results
            else "No results yet — run a trial first.")

    def _node_summary(self, node: Any, shown: Optional[Sequence[str]] = None) -> str:
        """最多 3 個「非預設」參數，渲染成 ``k=v`` 串起來。

        ``shown`` 是**副標那一行已經講過的影像流名**（``test ref → test ref``）。
        指定影像流的那些參數會被跳掉 —— 它們的值就是副標的來源，兩行講同一件事
        只是把第三行佔掉，而第三行本來是拿來放「這張卡被設定成什麼」的
        （F7-21：``streams=test,ref`` 跟上面那行完全重複）。
        """
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
        stream_params = {p.name for p in step_cls.params
                         if p.type in ("image_key", "image_keys")}
        seen = {str(s) for s in (shown or [])}
        parts: List[str] = []
        for name, value in node.params.items():
            if name in defaults and defaults[name] == value:
                continue
            if name in stream_params and seen:
                # 這個參數挑的流副標已經列出來了 → 不要再講一次。
                picked = {v.strip() for v in str(value).split(",") if v.strip()}
                if picked and picked <= seen:
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
            try:
                # Region 卡不寫影像流，它定義的是具名區域 —— 副標要講得出
                # 「ref → cell」，否則那張卡在畫布上看起來什麼都不產出。
                regions_out = list(step_cls.resolve_regions_out(node.params))
            except Exception:              # noqa: BLE001
                regions_out = []
            # F9-6：**同進同出** —— 接進來的每一條流，卡片後面也要接得出去，
            # 否則鏈到量測卡就斷了（那五張卡的 ``writes`` 是空的，畫布上根本
            # 沒有輸出埠）。順序是「自己產的新流」在前、「原樣送出的」在後。
            #
            # 引擎那邊本來就成立：跑一張卡的 local Context 是用它的輸入種出來
            # 的，跑完整份收成 ``produced[(節點, 名字)]``，所以輸入本來就在裡面
            # 送得出去（見 engine 的 ``_run_nodes``）。這裡只是把它畫出來。
            #
            # 「不需要就不要連它」—— 多出來的埠不接線就不會有任何作用。
            outs = list(writes) + [r for r in reads if r not in writes]
            # **還沒接上來源的卡，後面不長東西**（F10，使用者定調 2026-08-17：
            # 「一張卡片剛被 new add 時，前後應該都是空的乾淨的，連上 source，
            # 後面 source 才會出來」）。
            #
            # 這不只是畫面乾淨的問題：`Compare to stream` 一加進來就在後面掛一顆
            # ``diff``，那顆埠**接得出去**，於是下游那張卡指著一條根本還沒有人
            # 算出來的流。畫布因此變成一份「看起來成立、跑起來不是那回事」的圖。
            #
            # 沒有來源 → 沒有輸出、沒有輸入標籤、也沒有具名區域。三件事同一個
            # 理由：它們都是「這張卡跑完會有什麼」，而它現在跑不起來。
            reads = [r for r in reads if r]
            missing = list(step_cls.missing_inputs(node.params)) if step_cls else []
            if missing:
                writes, outs, regions_out = [], [], []
            # 每一格輸入在畫布上都是一顆埠（F10）。``show_when`` 藏起來的不算
            # —— 那一格現在不成立，畫一顆接不上任何意義的埠只會讓人問「這是
            # 什麼」。標籤用 ParamSpec 的 label（`First stream`），不是參數名。
            inputs = []
            if step_cls is not None:
                for spec in step_cls.input_specs():
                    if not spec.visible_for(node.params):
                        continue
                    inputs.append({
                        "name": spec.name,
                        "label": spec.label or spec.name,
                        "stream": str(node.params.get(spec.name, "") or ""),
                    })
            nodes.append({
                "node_id": nid,
                "inputs": inputs,
                "step_key": node.step,
                "label": label,
                "category": category,
                "enabled": bool(node.enabled),
                # 副標那行印的是 reads → writes/regions；摘要不要再講一次
                "summary": self._node_summary(
                    node, shown=list(reads) + list(writes) + list(regions_out)),
                # 畫布的輸出埠吃這個（含原樣送出的輸入）；副標仍然只印
                # 「這張卡真的產出什麼」，不然每張卡的副標都會變成一長串。
                "writes": outs,
                "produces": writes,
                "reads": reads,
                "regions_out": regions_out,
                "group": step_cls.resolve_group() if step_cls else "",
                "problem": problems.get(nid, ("", ""))[0],
                "problem_level": problems.get(nid, ("", "error"))[1],
            })
        if self.selected_node not in self.model.nodes:
            self.selected_node = None
        for view in self._canvases():
            view.set_nodes(nodes, self.model.edge_lines())
            view.set_selected(self.selected_node)
            view.set_score_summary(self.model.expr, self.model.threshold)

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
            rebin(self.trial_scores, float(threshold), self.model.bins),
            extra=self._accuracy_text(float(threshold)))

    def _accuracy_text(self, threshold: float) -> str:
        """有 ground truth 時，這個門檻下的正確率／抓漏／誤殺（一行字）。

        沒有 ground truth 就回空字串 —— **不要放一行「N/A」**：那會佔掉版面
        而且每次都在提醒使用者少了一個他可能根本沒有的東西。
        """
        g = accuracy_at(self.trial_results, threshold, self.model.bins,
                        self.ground_truth)
        if not g or not g.get("n_evaluated"):
            return ""
        return ("accuracy %.0f%%  missed %d  false alarms %d"
                % (100.0 * float(g.get("accuracy") or 0.0),
                   int(g.get("fn") or 0), int(g.get("fp") or 0)))

    def _load_ground_truth_beside(self, klarf_path: Any) -> str:
        """找 KLARF 旁邊的 ``ground_truth.json``；回傳用了哪個檔（沒有回 ""）。

        自動找是因為開發／驗證迴圈裡「跑一次看準不準」是最常做的事，而
        ``tools/make_sample.py`` 就是把它寫在那裡。找到一定在狀態列講出來 ——
        猜對了要讓人看得見猜的是什麼，猜錯了才有機會發現。
        """
        self.ground_truth = None
        try:
            folder = os.path.dirname(os.path.abspath(str(klarf_path)))
            guess = os.path.join(folder, "ground_truth.json")
            if not os.path.isfile(guess):
                return ""
            with open(guess, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                self.ground_truth = data
                return guess
        # 只吞「檔案的問題」（不存在、讀不動、不是 JSON）。以前這裡是 bare
        # ``except Exception``，於是 ``json`` 忘了 import 也只是安靜地當成
        # 「這份資料沒有答案卷」—— 找不到跟寫錯了長得一模一樣。
        except (OSError, ValueError, UnicodeDecodeError):
            self.ground_truth = None
        return ""

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
        # 選著一張卡的時候，新的卡排在它後面 —— 但**線不會自己出現**
        # （2026-08-16，使用者：「新增卡 不要自己接線（線都給 user 接）」）。
        # 加完就選取新卡 —— 所以連按三張卡片會長成一排，順序就是按下去的順序。
        after = self.selected_node if self.selected_node in self.model.nodes else None
        if after is not None:
            self.add_card_after(after, str(step_key))
            return
        try:
            node_id = self.model.add_step(str(step_key))
        except (KeyError, ParamError) as e:
            self._status("Could not add card: %s" % e, "error")
            return
        self._autofill_roi_mask(node_id)
        self._status("Added “%s”%s" % (node_id, self._unmet_needs(node_id)))
        self.select_node(node_id)

    def add_card_after(self, node_id: str, step_key: str) -> Optional[str]:
        """把 ``step_key`` 排在 ``node_id`` 後面。**不接線**。

        為什麼不接（2026-08-16 使用者定調：「新增卡 不要自己接線，線都給 user 接」）
        ------------------------------------------------------------------------
        以前這裡會順手做兩件事：接一條 ``node_id → 新卡`` 的實線，並且把新卡的
        來源改成前一張卡那條流。立意是「少按一次」，但它製造的是一種**看不見的
        第二個作者** —— 使用者接著自己拉一條線過來，畫面上就有兩條線進同一個
        輸入埠，而其中一條他從來沒畫過。兩條線落在同一個參數上時只有一條算數
        （見 ``_conflicting_edges``），於是「我明明接了 Denoise，怎麼跑出來像沒接」。

        線由使用者拉，這件事就沒有第二個作者。**順序**仍然照放（新卡排在選取
        那張後面）—— 那是「我要在這之後做這件事」，跟資料從哪來是兩回事。
        """
        nid = str(node_id)
        if nid not in self.model.nodes:
            return None
        at = self.model.node_order.index(nid) + 1
        # 使用者做的是**一個**動作（加一張卡），所以復原也該是一步（F7-22）。
        with self.model.compound("add-card"):
            try:
                new_id = self.model.add_step(str(step_key), at=at)
            except (KeyError, ParamError) as e:
                self._status("Could not add card: %s" % e, "error")
                return None
            self._autofill_roi_mask(new_id)
        self._status("Added “%s” after “%s” — drag a line into it to say which "
                     "image stream it works on.%s"
                     % (new_id, nid, self._unmet_needs(new_id)))
        self.select_node(new_id)
        return new_id

    def _autofill_roi_mask(self, node_id: Optional[str]) -> None:
        """剛加進來的 Mask from regions 卡，把上游定義過的區域名自動填進去。

        使用者的直覺是「Profile / Template 應該直接吐 mask」—— 名字要他自己
        打一次，是這張卡與上游之間**看得到卻要用手搬**的一段。量測卡的
        ``output_prefix`` 走過同一條路（挑了區域自動填名），這裡照做：
        上游有哪些具名區域就全部填上（多名字本來就是聯集），不合意再刪。
        只在**空的**時候填 —— 使用者打過的字不覆蓋。
        """
        node = self.model.nodes.get(str(node_id or ""))
        if node is None or node.step != "roi_mask":
            return
        if str(node.params.get("regions", "") or "").strip():
            return
        names: List[str] = []
        for nid in self.model.node_order:
            if nid == node.id:
                break
            n = self.model.nodes.get(nid)
            if n is None or not n.enabled:
                continue
            try:
                outs = get_step(n.step).resolve_regions_out(n.params)
            except Exception:              # noqa: BLE001 — 顯示用，壞了就跳過
                outs = []
            for r in outs:
                if r and r not in names:
                    names.append(str(r))
        if names:
            self.model.set_param(node.id, "regions", ", ".join(names))

    # ---- 「這張卡做在哪一條流上」（F7-18）----------------------------------
    #: 主要影像流的參數名（依優先順序）。Enhance 卡一律叫 ``target`` 或
    #: ``source``，而**一張卡只做一條流** —— 要對另一張圖做同一件事就再放一張
    #: 卡，那才是畫布看得懂的說法。
    _PRIMARY_PARAMS = ("streams", "target", "source")

    def _primary_stream_of(self, node_id: str) -> str:
        """``node_id`` 這張卡做在哪一條流上（接下去的卡預設跟著它走）。"""
        node = self.model.nodes.get(str(node_id))
        if node is None:
            return ""
        for name in self._PRIMARY_PARAMS:
            val = str(node.params.get(name, "") or "")
            if val:
                return val
        try:
            writes = get_step(node.step).resolve_writes(node.params)
        except KeyError:                           # pragma: no cover
            return ""
        return str(writes[0]) if writes else ""

    def _point_at_stream(self, node_id: str, stream: str,
                         accumulate: bool = False, param: str = "") -> str:
        """把 ``node_id`` 的輸入接上 ``stream``（回一句給狀態列的話）。

        這是「用節點表達要對哪一張圖做」的實作點：使用者從 ``ref`` 那顆輸出埠
        拉一條線過來，講的就是**這張卡也做 ref**。以前那句話只能在控制列的
        下拉裡講，畫布只表達得出先後順序 —— 於是 test 是主角、ref 是附帶。

        **累加還是取代，看參數型別**（F7-19）：

        - ``image_keys``（一串流，例如 Enhance 卡的 ``streams``）且
          ``accumulate=True`` → **累加**。先拉 test 再拉 ref 的意思是「兩張都
          做」，不是「改成只做 ref」。這正是使用者說的「希望是能夠互相連動
          的」—— 以前第二條線把第一條的設定蓋掉，於是畫布上做不出「兩條都
          接」，得回控制列去勾。
        - ``image_key``（單一具名角色，例如 ``subtract`` 的 ``a`` / ``b``）→
          **取代**。往 ``a`` 再拉一條是「改接別的」，不是「a 有兩條」。

        ``accumulate`` 由呼叫端決定，而它的判準是**這條線是不是新的依賴**：

        - **第一條線**（``add_edge`` 成功）→ 取代。卡片預設的 ``streams="test"``
          是規格的預設值，不是使用者拉的線；把 ref 累加上去的話，他拉了一條卻
          得到兩條，而畫布就說謊了。
        - **同一對節點的第二條線**（``has_edge``）→ 累加。那才是「這條也接上」。
        - 從卡片庫加一張新卡（``add_card_after``）→ 取代，理由同第一條。

        累加不必回頭處理畫線：畫布的線數是從「兩端共用的影像流」推出來的
        （``_ports_between``），``streams`` 一多一條，那條線就自己出現了。
        """
        node = self.model.nodes.get(str(node_id))
        if node is None or not stream:
            return ""
        try:
            specs = {p.name: p for p in get_step(node.step).params}
        except KeyError:                       # pragma: no cover
            return ""
        # F10：落點由呼叫端給（使用者放開滑鼠的那一格）。沒給才自己挑。
        names = [param] if param else [
            sp.name for sp in get_step(node.step).input_specs()]
        for name in names:
            spec = specs.get(name)
            if spec is None or spec.type not in ("image_key", "image_keys"):
                continue
            # 這就是這張卡吃影像流的那個參數 = 這條線的 ``dst_in``（F9-5b）。
            # **要在這裡記，不能等到真的改了值才記** —— 參數的預設值本來就等於
            # 那條流時，下面會提早 return（沒有東西要改），但線還是接在這個
            # 參數上。漏掉的話那條線在引擎眼裡就是「沒指定」，於是退回用
            # 「執行順序上最後一個寫它的人」推 —— 分支當場失效。
            self._bound_param = name
            current = str(node.params.get(name, "") or "")
            if spec.type == "image_keys" and accumulate:
                keys = [k.strip() for k in current.split(",") if k.strip()]
                if stream in keys:
                    return ""
                keys.append(stream)
                value, joined = ",".join(keys), True
            else:
                if current == stream:
                    return ""
                value, joined = stream, False
            try:
                self.model.set_param(str(node_id), name, value)
            except ParamError:                 # pragma: no cover — 值就是流名
                return ""
            # F9-5b：把「這條線落在哪個參數」寫回邊上。引擎靠它決定資料從哪來
            # （而不是靠「執行順序上最後一個寫這條流的人」），分支才成立。
            self._bound_param = name
            if joined and "," in value:
                return (" — “%s” now works on %s (same settings for both)"
                        % (node_id, " and ".join(value.split(","))))
            return " — “%s” now works on %s" % (node_id, stream)
        return ""

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

        以前只有卡片庫上一個 ``needs diff`` 之類的灰字 badge。對不會寫 code
        的人那句話沒有動作可做：他不知道那條流是誰產的，也不知道「不然還可以
        怎麼辦」。例：Load 之後直接放 SNR map，它預設吃 ``diff``，一定缺
        一張上游的 Compare。（Subtract 以前也是常客 —— 它曾預設吃
        ``ref_aligned``；2026-08-14 起改吃 ``ref``，patch 本來就對齊。）
        """
        node = self.model.nodes.get(str(node_id))
        if node is None:
            return ""
        try:
            step_cls = get_step(node.step)
            needs = list(step_cls.resolve_reads(node.params))
            # F10：剛加進來的卡**沒有來源**，所以 ``resolve_reads`` 是空的 ——
            # 照字面走的話這裡會說「什麼都不缺」，而它其實什麼都還沒接。
            #
            # 那一句話不能只講「這一格是空的」：對不寫 code 的使用者，「還缺
            # diff」跟「先加一張 Compare two streams」才是**做得下去**的話。
            # 卡片的 ``default`` 正好就是「這張卡本來預期吃哪一條流」，拿它來
            # 講那句話 —— 值被清掉了，但宣告還在。
            for name in step_cls.missing_inputs(node.params):
                spec = next((sp for sp in step_cls.params if sp.name == name),
                            None)
                want = str(getattr(spec, "default", "") or "")
                if want and want not in needs:
                    needs.append(want)
        except KeyError:
            return ""
        # 「上游有哪些流」有兩個來源，兩個都要算（F9-11）：
        #
        # 1. ``available_streams`` —— 照 route 的**線性順序**累加。這是沒有埠的
        #    線（既有 recipe）唯一的依據。
        # 2. **接進這張卡的線自己帶的流名。** F9 之後資料是照線走的，而線可以
        #    從執行順序上「後面」的節點接過來（分支的兩支各自往前接）。
        #    只看第 1 點的話，明明畫布上有線，這裡卻說「還缺 ref」——
        #    使用者照著那句話再加一張卡，就多了一張沒有用的卡。
        have = set(self.model.available_streams(before_node=str(node_id)))
        have |= {e.src_out for e in self.model.edges
                 if e.dst == str(node_id) and e.src_out}
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

    def _drop_conflicting_edges(self, src: str, dst: str, stream: str,
                                param: str) -> str:
        """拿掉「跟這條新線搶同一個輸入」的舊線；回一句給狀態列的話。

        什麼叫搶同一個輸入
        ------------------
        引擎是用 ``(下游節點, 流名)`` 去查資料從哪來的（``_explicit_bindings``），
        所以同一個 key 只能有一個來源。兩條線落在同一個 key 上時，**dict 後寫
        的贏** —— 也就是「``recipe.edges`` 裡排在後面的那條」，而那個順序在畫布
        上完全看不出來。

        - ``image_key``（``subtract`` 的 ``a``／量測卡的 ``source``）：一個參數
          就是一個角色，同一個參數上的舊線一律讓位。
        - ``image_keys``（Enhance 卡的 ``streams``，可以同時做好幾條）：只有
          **同一條流名**才算搶 —— 一條給 test、一條給 ref 是兩個 key，本來就
          該並存。
        """
        node = self.model.nodes.get(str(dst))
        if node is None or not param:
            return ""
        try:
            spec = {p.name: p for p in get_step(node.step).params}.get(param)
        except KeyError:                       # pragma: no cover
            return ""
        if spec is None:
            return ""
        # 「不是剛拉的這一條」而不是「來源不同的那些」（F10 修）：從**同一張卡**
        # 先拉 test 再拉 ref 到同一顆角色埠時，來源相同 —— 舊的判準把它放過去，
        # 於是參數換成了 ref、而畫布上兩條線都還在，同一個輸入埠上有兩條線。
        # 那正是 F9-7 擋下來的東西（引擎只認其中一條，而畫面上看不出是哪條）。
        # F10 之前這個洞碰不到，因為 a / b 這種角色埠上根本不會有線。
        losers = [e for e in list(self.model.edges)
                  if e.dst == str(dst) and e.dst_in == param
                  and not (e.src == str(src) and e.src_out == str(stream))
                  and (spec.type == "image_key" or e.src_out == str(stream))]
        for e in losers:
            # 帶著流名剪 —— 兩張卡之間可以有好幾條並排的線（F9-9），
            # 不指名的話會把隔壁那條一起剪掉。
            self.model.remove_edge(e.src, e.dst, src_out=e.src_out or None)
        if not losers:
            return ""
        return (" (replacing the line from %s)"
                % ", ".join(sorted({e.src for e in losers})))

    def _on_node_toggled(self, node_id: str, enabled: bool) -> None:
        self.model.set_enabled(str(node_id), bool(enabled))

    def _on_move_requested(self, node_id: str, delta: int) -> None:
        self.model.move(str(node_id), int(delta))

    # ---- 畫布連線（F7-6；F7-18 起帶著影像流）-------------------------------
    def _on_edge_added(self, src: str, dst: str, stream: str = "",
                       dst_in: str = "") -> None:
        """拉一條線。會造成循環時 model 回 False —— 那條線就不會出現。

        擋在這裡（而不是等執行時報錯）是刻意的：使用者看到的是「這條線拉不
        起來」，不是「拉起來之後整條 pipeline 壞掉」。

        ``stream`` 是**線從哪個輸出埠出發**（F7-18）。從 ref 那顆埠拉過去，
        意思就是「這張卡做在 ref 上」，所以下游那張卡的主要輸入跟著改。
        以前這件事只能在控制列的下拉裡講，於是同一個動作在畫布上做不完。

        兩個節點之間**已經有線**也照樣要處理那句話：先從 test 拉、再從 ref 拉
        是很正常的操作（「我改變主意了，這張卡要做在 ref 上」），而以前它只會
        得到一句「already connected」然後什麼都沒發生 —— 看起來就像畫布不准
        你碰 ref。

        **拉一條線 = 一步復原**（F9-7）。在 model 上它其實是三、四個動作
        （add_edge → set_param → set_edge_ports →（有時）拿掉搶同一個輸入的
        舊線），各記一步的話按一次 Ctrl+Z 會停在「線還在但埠沒了」這種中間
        狀態 —— 使用者從來沒有做出過那個畫面。
        """
        src, dst, stream = str(src), str(dst), str(stream or "")
        with self.model.compound("connect"):
            self._connect(src, dst, stream, str(dst_in or ""))

    def _connect(self, src: str, dst: str, stream: str,
                 dst_in: str = "") -> None:
        # 這條線會落在下游卡的哪個參數上（F9-9：**先算出來**，才有辦法把埠跟
        # 線一起加進去）。以前是「先加一條沒有埠的線，再回頭補埠」，而補埠只
        # 找得到一對節點之間的第一條 —— 兩條並排的線就補錯了。
        # 這條線落在哪個輸入參數上：**使用者放開滑鼠的地方說了算**（F10）。
        # 以前是 Studio 依 streams → target → source 的固定順序挑第一個 ——
        # 那在「一張卡只有一個輸入在用」的年代猜得中，但 ``subtract`` 的
        # a / b 兩顆輸入永遠只挑得到同一個，於是畫布上接哪一顆都一樣。
        param = dst_in or self._param_for_stream(dst)
        # **這一格上已經有線了嗎** —— 有就是累加（多連一），沒有就是設定它。
        #
        # 以前的判準是「這一對節點之間已經有線了嗎」，那在 F10 之前是對的：
        # 卡片的輸入帶著規格預設值（``streams="test"``），第一條線的意思是
        # 「改成這個」而不是「再加一個」。現在新卡的輸入本來就是空的，那個理由
        # 不成立了 —— 而舊判準還會漏掉「兩條線來自**不同**上游卡」這種多連一，
        # 那正是量測卡最常見的接法（一條 diff、一條 test）。
        accumulate = any(e.dst == dst and e.dst_in == param
                         for e in self.model.edges)
        if self.model.has_line(src, dst, stream, param):
            self._status("%s → %s is already connected on %s."
                         % (src, dst, stream or "that stream"))
            return
        if not self.model.add_edge(src, dst, src_out=stream, dst_in=param):
            self._status("Cannot connect %s → %s — that would make the "
                         "pipeline loop back on itself." % (src, dst), "error")
            return
        # 影像流在**線真的接起來之後**才改。會成環的那條線沒有落地，
        # 它不該留下任何痕跡 —— 尤其不是「那張卡安靜地改成做 ref 了」。
        # 同一對節點的第二條線是「這條也接上」（累加），不是「改接別的」。
        note = self._point_at_stream(dst, stream, accumulate=accumulate,
                                     param=param)
        # **一個輸入埠只能有一條線**：新的這條贏，舊的那條拿掉（F9-7）。
        # 留著兩條的話引擎只會照其中一條送資料（``recipe.validate`` 會報
        # ambiguous-input），而畫面上看不出是哪一條 —— 使用者剛拉的那一條
        # 有可能根本不算數。**同一個輸入**指的是同一個參數上的同一條流名，
        # 所以一條給 test、一條給 ref 不算搶（F9-9 的「多連一」）。
        dropped = self._drop_conflicting_edges(src, dst, stream, param)
        self._status("Connected %s → %s%s%s" % (src, dst, note, dropped))

    def _param_for_stream(self, node_id: str) -> str:
        """線沒有指定落點時，這條線該接哪一格輸入（沒有輸入回空字串）。

        F10 起**正常路徑不會走到這裡** —— 使用者放開滑鼠的位置就是落點。
        這是給程式化拉線（測試、之後可能的自動排版）用的退路，判準是
        「第一個**還空著**的輸入」：接第二條線時它自然落到還沒接的那一格，
        而不是又去蓋掉第一格。

        以前這裡是一張寫死的名單（``streams`` → ``target`` → ``source``），
        於是 ``subtract`` 的 ``a`` / ``b`` 永遠只挑得到 —— 兩顆輸入的卡在畫布上
        根本分不開。名單也不會自己認得之後加的卡。
        """
        node = self.model.nodes.get(str(node_id))
        if node is None:
            return ""
        try:
            specs = [sp for sp in get_step(node.step).input_specs()
                     if sp.visible_for(node.params)]
        except KeyError:                       # pragma: no cover
            return ""
        if not specs:
            return ""
        for spec in specs:
            if not str(node.params.get(spec.name, "") or "").strip():
                return spec.name
        return specs[0].name

    def _on_edge_removed(self, src: str, dst: str, stream: str = "",
                         dst_in: str = "") -> None:
        """剪掉一條線。``stream`` 是剪刀瞄的那一條（F9-9），``dst_in`` 是它
        進到下游的哪一格（F10）。

        兩張卡之間可以有兩條並排的線，所以**剪一條**跟剪掉整個依賴是兩件事。
        瞄不到特定那條（舊格式的線沒有埠）就退回拿掉整對。

        **剪掉線就是拿掉來源**（F10）：線是唯一的來源，所以那一格要跟著空掉。
        不空的話畫布會反過來說謊 —— 畫面上線沒了，卡片卻還指著那條流，而且
        照樣跑得出數字。使用者回報的原話是「把線按 X 清掉，後方卡片的 Node
        不會跟著清掉」。
        """
        src, dst, stream = str(src), str(dst), str(stream or "")
        dst_in = str(dst_in or "")
        # 剪之前先問清楚這條線落在哪一格 —— 剪完就查不到了。
        if not dst_in:
            for e in self.model.edges:
                if (e.src == src and e.dst == dst
                        and (not stream or e.src_out == stream)):
                    dst_in = e.dst_in
                    break
        with self.model.compound("disconnect"):
            one = stream and self.model.remove_edge(
                src, dst, src_out=stream, dst_in=dst_in or None)
            if one:
                note = self._unpoint_stream(dst, stream, dst_in)
                self._status("Disconnected %s → %s on %s%s"
                             % (src, dst, stream, note))
            elif self.model.remove_edge(src, dst):
                note = self._unpoint_stream(dst, stream, dst_in)
                self._status("Disconnected %s → %s%s" % (src, dst, note))

    def _unpoint_stream(self, node_id: str, stream: str,
                        param: str = "") -> str:
        """線剪掉了 → 那條流也要從下游卡的參數裡拿掉（回一句給狀態列的話）。

        不拿掉的話畫布會**反過來說謊**：畫面上那條線沒了，卡片卻還在處理它
        （`streams=test,ref` 一個字都沒變）。這是 F9-7「接線時參數跟著改」的
        另一半。

        F10 之前這裡有兩個保留條款，現在**兩個都拿掉了**：

        * 「單一角色的輸入（``image_key``）值就留著」—— 那時候那一格的值是
          唯一的紀錄，清了就沒有東西講「這張卡本來要做什麼」。現在線才是唯一
          的來源，值留著等於畫布上沒有線、卡片卻還指著一條流。
        * 「最後一條不拿掉」—— 理由是 ``MultiStreamStep`` 對空字串會退回
          ``test``。那個 ``or`` 在 F10 拿掉了，所以這個保留條款也沒有存在的
          理由；留著反而讓「剪掉最後一條線」變成畫面與實際不一致的那一步。

        剪完之後那張卡回到「還沒接線」的狀態 —— 跟剛加進來的卡一模一樣：
        沒有輸出埠、lint 報 ``not-connected``、引擎不放行。
        """
        node = self.model.nodes.get(str(node_id))
        param = str(param or "")
        if node is None:
            return ""
        try:
            specs = {p.name: p for p in get_step(node.step).params}
        except KeyError:                       # pragma: no cover
            return ""
        spec = specs.get(param)
        if spec is None or not spec.is_input():
            return ""
        if spec.type == "image_keys":
            keys = [k.strip() for k
                    in str(node.params.get(param, "") or "").split(",")
                    if k.strip()]
            if stream and stream in keys:
                keys.remove(stream)
            elif len(keys) > 1:
                return ""          # 指不出剪的是哪一條，寧可不動
            else:
                keys = []
            value = ",".join(keys)
        else:
            value = ""                         # 角色埠：那條線就是它的全部來源
        if value == str(node.params.get(param, "") or ""):
            return ""
        try:
            self.model.set_param(str(node_id), param, value)
        except ParamError:                     # pragma: no cover — 值就是流名
            return ""
        if not value:
            return " — “%s” has no input on “%s” now" % (
                node_id, spec.label or param)
        return " — “%s” now works on %s" % (node_id, " and ".join(
            value.split(",")))

    def _on_remove_requested(self, node_id: str) -> None:
        node_id = str(node_id)
        # 刪掉一張卡 = 把它餵出去的每一條線都剪掉（F10-5）。下游那幾格要跟著
        # 空出來，否則它們指著一條再也沒有人產出的流 —— 跟按 × 剪掉是同一件事，
        # 所以走同一條路（`_unpoint_stream`），不要在這裡另寫一份。
        with self.model.compound("remove-card"):
            for e in [e for e in self.model.edges if e.src == node_id]:
                self._unpoint_stream(e.dst, e.src_out, e.dst_in)
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
            self._status("No such step: “%s”." % node_id, "error")
            return False
        self.selected_node = node_id
        self._user_stream = None       # 換節點 → 影像流回到「這個節點的輸出」
        # 換卡片＝上一段連續調整結束（見 viewmodel 的 coalescing）。不切的話，
        # 「調 A 卡的 gamma → 換到 B 卡 → 再調回 A 卡的 gamma」會被併成一步。
        self.model.end_coalescing()
        for view in self._canvases():
            view.set_selected(node_id)
        try:
            describe = get_step(node.step).describe()
        except KeyError:
            describe = None
        streams = self.model.available_streams(before_node=node_id)
        self.param_form.set_step(describe, node.params, streams)
        self.stack.setCurrentWidget(self.param_form)
        self._refresh_region_button()
        self._install_inspector(node.step)     # 右下角換成這張卡的儀表（F7-17）
        self._refresh_inspector(self._last_result)
        self._schedule_preview()
        return True

    # ---- 設定面板：預設收起，雙擊卡片才攤開（F7-22）------------------------
    def _on_node_activated(self, node_id: str) -> None:
        """雙擊一張卡：選它 + 把設定攤開。"""
        if self.select_node(str(node_id)):
            self.set_params_open(True)

    def _on_card_dropped(self, step_key: str, x: float, y: float) -> None:
        """從卡片庫拖一張卡丟到畫布上（F7-22）。

        接法跟按「Add」完全一樣（``_on_add_requested`` → ``add_card_after``），
        差別只在**落點**：丟在哪裡就擺在哪裡。位置不寫進 recipe，所以這只影響
        現在看到的畫面 —— 那是既有的行為（見 canvas 模組 docstring），
        重新載入會回到自動排版。
        """
        self._on_add_requested(str(step_key))
        nid = self.selected_node
        if nid:
            self.pipeline.place_dropped(nid, float(x), float(y))

    def params_open(self) -> bool:
        """設定面板現在攤開著嗎。

        追**明確狀態**而不是問 widget：`isVisible()` 在視窗 show 之前恆為
        False，那個坑這個 repo 踩過（見 docs/PITFALLS.md）。
        """
        return bool(self._params_open)

    def set_params_open(self, on: bool) -> bool:
        """攤開／收起設定區（中欄的下半）。預設是攤開的（D 案）——
        畫布會 zoom，平面上只需要中上一塊；收起來是給「現在只想看流程」的人。"""
        on = bool(on)
        self._params_open = on
        total = sum(self.canvas_column.sizes()) or self.canvas_column.height()
        if on:
            keep = max(240, int(total * 0.6))
            self.canvas_column.setSizes([max(0, total - keep), keep])
        else:
            self.canvas_column.setSizes([total, 0])
        return on

    # ---- 畫布的彈出視窗（F8-UI D 案）--------------------------------------
    def open_canvas_window(self) -> None:
        """把 pipeline 開在自己的視窗（全尺寸）。

        主視窗的畫布只佔中上一塊 —— 要看全貌不是把主視窗的版面搶回來，
        是到自己的視窗看。第二個視窗是**另一份 PipelineCanvas 接同一個
        model**：所有訊號走同一批 handler，所以在彈出視窗拉線、拖卡、
        選取，主視窗全部跟著動（反之亦然）。
        """
        from PySide6.QtWidgets import QDialog

        if self._canvas_popout is not None:
            self._canvas_popout.raise_()
            self._canvas_popout.activateWindow()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Pipeline — full view")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        view = PipelineCanvas(dlg, popout_button=False)
        lay.addWidget(view)
        self._wire_canvas(view)
        dlg.resize(1100, 700)
        dlg.finished.connect(self._on_canvas_popout_closed)
        self._canvas_popout, self._popout_view = dlg, view
        # 畫布已經在別的視窗全尺寸攤開了，主視窗那一份就把位子讓出來 ——
        # 設定往上補滿整欄（使用者要的 flexible）。關窗時還原原本的比例。
        self._pre_popout_sizes = list(self.canvas_column.sizes())
        total = sum(self._pre_popout_sizes) or self.canvas_column.height()
        self.canvas_column.setSizes([0, total])
        self._refresh_pipeline()          # 把現在的節點畫進新視窗
        # 開窗那一刻跟主視窗長得一樣（含使用者拖過的位置）——
        # 「彈出去被自動整理」正是使用者退掉的行為。
        view.copy_positions_from(self.pipeline)
        dlg.show()
        view.fit_later()

    def _on_canvas_popout_closed(self, *_a) -> None:
        self._canvas_popout = None
        self._popout_view = None
        # 還原彈出前的版面。當時的比例就是使用者自己調的 —— 還原成那個，
        # 不是還原成預設值。
        saved = getattr(self, "_pre_popout_sizes", None)
        if saved and sum(saved):
            self.canvas_column.setSizes(saved)
        else:
            self.set_params_open(self._params_open)

    def canvas_popout_open(self) -> bool:
        """彈出視窗現在開著嗎（**明確狀態**，不問 widget）。"""
        return self._canvas_popout is not None

    def _canvases(self) -> List[PipelineCanvas]:
        """現在活著的每一份畫布（主視窗的 + 彈出視窗的）。"""
        views = [self.pipeline]
        if self._popout_view is not None:
            views.append(self._popout_view)
        return views

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
        self.set_params_open(True)   # 分數面板本來就是「我要編」

    def show_param_page(self) -> None:
        self.stack.setCurrentWidget(self.param_form)

    # ==================================================================== #
    # 參數編輯
    # ==================================================================== #
    def _on_param_edited(self, name: str, value: Any) -> None:
        """ParamForm 的唯一出口：驗證通過才寫回 model，失敗就把那列變紅字。"""
        node_id = self.selected_node
        if node_id is None or node_id not in self.model.nodes:
            self._status("Select a step in the pipeline before editing parameters.", "error")
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
                self._status("Could not load dataset: %s: %s" % (type(e).__name__, e), "error")
                return False
            return self._on_dataset_loaded(ds)
        if not self.dataset_worker.start(path, tiff):
            self._status("A dataset is already loading — please wait.")
            return False
        self._progress_busy("Loading %s…" % os.path.basename(path))
        self._status("Loading: %s" % os.path.basename(path))
        return True

    def load_stack_path(self, path: Any, per_defect: int = 1,
                        sync: bool = False) -> bool:
        """載入一個**多頁 TIFF、沒有 KLARF**（F11 Input-2）。

        ``per_defect`` 是「一顆 defect 幾張圖」—— 那是**資料的屬性**（機台怎麼收
        的），所以在這裡問，不放進 recipe。recipe 只負責**命名**那幾張
        （`load_patch` 的 `channel_map`）。分組與命名分開，同一批資料的「一顆幾張」
        才不會因為換一份 recipe 而改變。
        """
        path = str(path)
        n = max(1, int(per_defect))
        if not os.path.isfile(path):
            self._status("File not found: %s" % path)
            return False
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync_stack(path, n)
            except Exception as e:      # noqa: BLE001 — UI 邊界，一律回報
                self._status("Could not load image stack: %s: %s"
                             % (type(e).__name__, e), "error")
                return False
            return self._on_dataset_loaded(ds)
        if not self.dataset_worker.start_stack(path, n):
            self._status("A dataset is already loading — please wait.")
            return False
        self._progress_busy("Loading %s…" % os.path.basename(path))
        self._status("Loading: %s (%d image(s) per defect)"
                     % (os.path.basename(path), n))
        return True

    def load_folder_path(self, folder: Any, sync: bool = False) -> bool:
        """載入一個**資料夾的單張影像**（F11 Input-3）。

        沒有 KLARF、沒有座標，每個影像檔一顆 defect。多頁 TIFF 在這條路上只讀
        得到第一頁 —— ingest 會為此發一句警告並指向 ``Open stack…``。
        """
        d = str(folder)
        if not os.path.isdir(d):
            self._status("Not a folder: %s" % d)
            return False
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync_folder(d)
            except Exception as e:      # noqa: BLE001 — UI 邊界，一律回報
                self._status("Could not load folder: %s: %s"
                             % (type(e).__name__, e), "error")
                return False
            return self._on_dataset_loaded(ds)
        if not self.dataset_worker.start_folder(d):
            self._status("A dataset is already loading — please wait.")
            return False
        self._progress_busy("Loading %s…" % os.path.basename(d.rstrip("/\\")))
        self._status("Loading folder: %s" % d)
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

        warn = list(getattr(dataset, "warnings", []) or [])

        # route 型別跟著資料走 —— **但只在使用者還沒動過 pipeline 的時候**
        # （F11 Input-3）。以前這裡的條件是「畫布是空的」，而 F7-9 之後開窗就有
        # 一張起手卡，所以那個條件**永遠是 False** —— 在只支援一種輸入的時候看
        # 不出來，四種輸入之後就會：載一份 rsem 資料，pipeline 還留在 ebi_patch
        # 那條 route 上，於是 lint 以為有 `ref`（kind-aware 宣告）而執行期才發現
        # 沒有。判準改成 `dirty`（`RecipeModel.starter()` 特意把它設 False）。
        ds_kind = str(getattr(dataset, "kind", self.model.kind))
        if ds_kind != self.model.kind:
            if not self.model.dirty or not self.model.node_order:
                self.model.kind = ds_kind
                self.model.dirty = False      # 換 route 不算「使用者改過」
                # ⚠ **換 kind 必須重畫**。`model.kind` 是直接設的屬性，不會通知
                # listener，而畫布的輸出埠是照 kind 算的（`resolve_writes_for_kind`）
                # —— 少了這一行，載一份 rsem 資料之後畫布上還是 patch 的
                # `test` / `ref` 兩顆埠，而資料只有一條 `single`。
                # 使用者回報的「畫布跟實際對不起來」第一層就是這個。
                self._refresh_all()
            else:
                # 使用者已經蓋了一條 pipeline，那是他的東西 —— 不要偷偷改掉它，
                # 但要講出這個組合跑不起來。
                warn.insert(0, (
                    "this pipeline is written for %s data and you just opened "
                    "%s data; open a recipe for %s, or start a new pipeline."
                    % (self.model.kind, ds_kind, ds_kind)))

        # `channel_map` 的表格要照「這批資料一顆有幾張圖」排列數（F11）。
        # 那是資料的事實，所以在這裡講一次，不是每次選卡片時重新猜。
        self.param_form.set_image_count(
            len(getattr(items[0], "images", {}) or {}) if items else 0)

        self._update_defect_label()
        self._update_action_states()
        self._progress_done()
        msg = "Loaded %d defects (input type %s)" % (
            len(items), getattr(dataset, "kind", "?"))
        # 換一份資料集就換一份答案卷 —— 上一份的 ground truth 留著的話，
        # 狀態列會拿 A 的答案去對 B 的結果，而那個數字看起來完全正常。
        gt = self._load_ground_truth_beside(
            getattr(getattr(dataset, "klarf", None), "source_path", "") or "")
        # 撿到哪一份答案卷要**留在畫面上**，不能只在狀態列講一次 —— 載完就接著
        # 算預覽，那句話幾毫秒後就被蓋掉了。直方圖旁邊的正確率是它唯一的用處，
        # 所以把「拿什麼對的」掛在同一個東西的 tooltip 上。
        self.histogram.setToolTip(
            "Accuracy is measured against %s" % gt if gt else "")
        # 沒有 KLARF 就寫不回 KLARF（F11 Input-2）。講在**載入的當下**，因為
        # Export 精靈把那個選項變灰是使用者跑完一整批之後才看得到的事。
        if getattr(dataset, "klarf", None) is None:
            warn.append(no_klarf_message(getattr(dataset, "kind", "")))
        if warn:
            msg += "   ! %s" % warn[0]
        if gt:
            msg += "   (ground truth: %s)" % os.path.basename(gt)
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
        # 「沒有 KLARF」要**常駐**，不能只在狀態列講一次（F11 Input-2）——
        # 載完就接著算預覽，狀態列那句話幾毫秒後就被 "Computing preview…" 蓋掉。
        # 同一個教訓在 ground truth 那一輪就學過了（見 `_on_dataset_loaded`）。
        # 掛在資料集標籤上：它就在使用者眼前，而且它講的正是「你現在手上是什麼資料」。
        no_klarf = getattr(self.dataset, "klarf", None) is None
        self.defect_label.setText(
            "%s · defect %d / %d%s" % (getattr(self.dataset, "kind", "?"),
                                       i + 1, len(items),
                                       " · no KLARF" if no_klarf else ""))
        self.defect_label.setToolTip(
            no_klarf_message(getattr(self.dataset, "kind", ""))
            if no_klarf else "")

    def set_defect_index(self, index: int) -> bool:
        """跳到第 ``index`` 顆 defect（超出範圍會夾住）。"""
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
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
            self._status("Could not load recipe: %s: %s" % (type(e).__name__, e), "error")
            return False
        kind = None
        ds_kind = str(getattr(self.dataset, "kind", "")) if self.dataset else ""
        if ds_kind and ds_kind in recipe.routes:
            kind = ds_kind
        self._apply_model(RecipeModel.from_recipe(recipe, kind=kind))
        self.recipe_path = path
        self.setWindowTitle("ADEPT Studio — %s" % self.model.recipe_id)
        n = len(self.model.node_order)
        # 版本落差要在**載入的那一刻**講，不是等他按了試跑才從 lint 冒出來 ——
        # 那時候他已經在調參數了，而該做的是先更新程式（見 recipe.version_skew）。
        skew = version_skew(getattr(recipe, "app_version", ""))
        if skew:
            self._status(skew, "error")
        else:
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
        for view in self._canvases():
            view.set_selected(None)
            view.forget_positions()   # 換了一份 recipe，別繼承上一份拖過的位置
        self.param_form.set_step(None, {}, [])
        self.stack.setCurrentWidget(self.param_form)
        self._refresh_all()
        # 換了一整份 pipeline 就把它擺好給人看。以前開一份 recipe 之後卡片是
        # 擠在角落的，畫面上一大片空白，而使用者的第一個動作永遠是自己去按
        # 「全部看得完」—— 那顆鈕該是「我又滾亂了」時用的，不是每次開檔的儀式。
        #
        # **只在這裡**（整份換掉）做，不在 ``_refresh_all`` 做：加一張卡就重新
        # 縮放一次，等於使用者每動一下畫面就跳一次。
        self.pipeline.fit_later()

    def load_template(self) -> bool:
        """載入內建的 die-to-die 範本；檔案不在就只在狀態列抱怨，不炸。"""
        path = TEMPLATE_RECIPE
        if not path.is_file():
            self._status("Built-in template not found: %s" % path)
            return False
        return self.load_recipe_path(str(path))

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
                self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
            return False

        recipe = self.model.to_recipe()
        upto = self.selected_node if self.selected_node in self.model.nodes else None
        if sync:
            try:
                result = PreviewWorker.run_sync(recipe, item, self.model.kind,
                                                upto_node=upto)
            except Exception as e:      # noqa: BLE001 — UI 邊界
                self._status("Preview failed: %s: %s" % (type(e).__name__, e), "error")
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

        self._refresh_inspector(result)
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
    PROFILE_STEP = "roi_cross"

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
            self._status("Select a Locate region by template card first.", "error")
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
            self._status("Could not store the template: %s" % e, "error")
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
        False（docs/PITFALLS.md 的老坑）。
        """
        return bool(self.selected_regions()) and bool(self._items())

    # ---- 右下角：卡片儀表（F7-17）------------------------------------------
    def show_bottom_page(self, index: int) -> None:
        """0 = 這張卡的儀表，1 = 特徵表。"""
        index = 1 if int(index) else 0
        if index == 0 and self._inspector is None:
            index = 1          # 這張卡沒有儀表 —— 不要給一片空白
        self.bottom_stack.setCurrentIndex(index)
        self.btn_tab_card.setChecked(index == 0)
        self.btn_tab_features.setChecked(index == 1)
        self.btn_tab_card.setEnabled(self._inspector is not None)

    def bottom_page(self) -> int:
        return int(self.bottom_stack.currentIndex())

    def inspector(self) -> Optional[Any]:
        """目前掛著的卡片儀表（沒有就 None）。"""
        return self._inspector

    def _install_inspector(self, step_key: str) -> None:
        """換卡片時換儀表。沒有註冊儀表的卡就只剩特徵表。"""
        cls = inspector_for(step_key)
        current = type(self._inspector) if self._inspector is not None else None
        if cls is not current:
            if self._inspector is not None:
                # 面板被拆掉就不會再有「放開」——影像上的綠帶會永遠留著。
                self._on_measure_ended()
                self.inspector_slot.removeWidget(self._inspector)
                self._inspector.setParent(None)
                self._inspector.deleteLater()
                self._inspector = None
            if cls is not None:
                self._inspector = cls(self.inspector_host)
                self.inspector_slot.addWidget(self._inspector)
                self._connect_inspector(self._inspector)
            self.btn_tab_card.setText(str(getattr(cls, "title", "Card"))
                                      if cls is not None else "Card")
        # **每次都要同步頁面**，不能因為「儀表類別沒變」就跳過：兩張都沒有儀表
        # 的卡片連續選下去時，類別確實沒變（都是 None），但畫面若停在儀表那一頁
        # 就是一片空白 —— 而那比原本的特徵表還糟。
        self.show_bottom_page(0 if cls is not None else 1)

    def _connect_inspector(self, insp: Any) -> None:
        """儀表能發的選配訊號在這裡接起來。

        用 ``getattr`` 探而不是 ``isinstance``：加一個會量測的儀表時，這裡不必
        跟著改（F7-17 那條「加新卡不必動 UI」的延伸）。
        """
        sig = getattr(insp, "measure_changed", None)
        if sig is not None:
            sig.connect(self._on_measure)
        sig = getattr(insp, "measure_ended", None)
        if sig is not None:
            sig.connect(self._on_measure_ended)
        sig = getattr(insp, "param_requested", None)
        if sig is not None:
            sig.connect(self._on_param_requested)
        sig = getattr(insp, "calibrate_requested", None)
        if sig is not None:
            sig.connect(self._on_calibrate_requested)

    #: 一鍵校正最多量幾顆。統計上 50 顆已經把單張雜訊除到 1/7，再多只是等待。
    CALIBRATE_LIMIT = 60

    def _on_calibrate_requested(self) -> None:
        """一鍵校正（F8 第七輪）：整批量 pitch/線寬，量完填回這張卡。

        跟「量測尺」「Use」是同一件事的三個尺度：拖一把尺（手動、單段）、
        按 Use（自動、單張）、按這顆（自動、整批）。批次的價值在統計 ——
        pitch 是設計常數，每張量的都是同一個數字，中位數把單張的雜訊除掉；
        小 patch 看不出「間距交錯」，一批看得出。
        """
        nid = self.selected_node
        node = self.model.nodes.get(nid or "")
        if node is None or node.step != self.PROFILE_STEP:
            return
        items = self._items()
        if not items:
            self._status("Load a KLARF first - measuring across the lot "
                         "needs the lot.", "error")
            return
        if not self.calibrate_worker.start(
                self.model.to_recipe(), items[:self.CALIBRATE_LIMIT],
                self.model.kind, nid, dict(node.params)):
            self._status("Still measuring - please wait.")
            return
        self._status("Measuring stripe pitch and width on %d defects…"
                     % min(len(items), self.CALIBRATE_LIMIT))

    def _on_calibrated(self, result: Any) -> None:
        """量完了：能填的填進卡片（走 set_param，可復原），不能填的講原因。"""
        nid = self.selected_node
        node = self.model.nodes.get(nid or "")
        if node is None or node.step != self.PROFILE_STEP:
            return                        # 量的過程中使用者換卡了 —— 別亂寫
        res = dict(result or {})
        filled, refused = [], []
        for axis, side, word in (("x", "vertical", "upright"),
                                 ("y", "horizontal", "flat")):
            cal = res.get(axis)
            if cal is None:
                continue
            if cal.note:
                refused.append("%s: %s" % (word, cal.note))
                continue
            self.model.set_param(nid, "%s_pitch" % side, round(cal.pitch, 3))
            self.model.set_param(nid, "%s_pitch_2" % side,
                                 round(cal.pitch_2, 3))
            bits = ("pitch %.1f / %.1f px" % (cal.pitch, cal.pitch_2)
                    if cal.pitch_2 >= 2.0 else "pitch %.1f px" % cal.pitch)
            if cal.width >= 1.0:
                self.model.set_param(nid, "%s_width" % side,
                                     round(cal.width, 3))
                bits += ", width %.1f px" % cal.width
            filled.append("%s %s (%d defects, %.0f%% agree)"
                          % (word, bits, cal.n_used, cal.agree * 100.0))
        node = self.model.nodes.get(nid)
        self.param_form.set_step(
            get_step(node.step).describe(), node.params,
            self.model.available_streams(before_node=nid))
        if refused:
            # 拒絕的那一半是**主角**：它講的是「這批 patch 自己不同意」，
            # 而那正是 kinds 沒設對的樣子。填了的也要一起講 —— 只報壞消息
            # 的話，使用者會以為整件事失敗了，然後把填好的那一半也改掉。
            msg = "Not filled in - %s" % " · ".join(refused)
            if filled:
                msg = "Filled %s. %s" % (" · ".join(filled), msg)
            self._status(msg, "error")
        elif filled:
            self._status("Measured across the lot: %s." % " · ".join(filled))
        else:
            self._status("Nothing to measure - no defects had stripes.",
                         "error")

    def _on_param_requested(self, name: str, value: Any) -> None:
        """儀表說「這一格該是這個值」（目前只有「量給我填」用到）。

        走的是跟使用者自己動參數表**同一條路**（``set_param`` → 復原堆疊 →
        重跑預覽），所以它可以被 Ctrl+Z 撤銷 —— 一個會改 recipe 而撤不掉的
        按鈕，比沒有那顆按鈕糟。
        """
        nid = self.selected_node
        if not nid or nid not in self.model.nodes:
            return
        self._on_param_edited(str(name), value)
        # 參數表要跟著顯示新值 —— 不然畫面上那一格還是舊的，而使用者按了鈕。
        node = self.model.nodes.get(nid)
        if node is not None:
            self.param_form.set_step(
                get_step(node.step).describe(), node.params,
                self.model.available_streams(before_node=nid))

    def _on_measure(self, axis: str, start: float, end: float) -> None:
        """曲線面板上按著量測尺 → 影像上標出同一段（F8）。

        兩張圖都標：並排比對開著的時候，使用者量的是「這個位置」而不是
        「左邊那張的這個位置」。
        """
        for view in (self.image_view, self.image_view_b):
            view.set_measure(axis, start, end)

    def _on_measure_ended(self) -> None:
        for view in (self.image_view, self.image_view_b):
            view.clear_measure()

    def _refresh_inspector(self, result: Any = None) -> None:
        """把三種來源餵給儀表：這張卡的參數、這一顆的結果、整批的結果。"""
        insp = self._inspector
        if insp is None:
            self.inspector_summary.setText("")
            return
        node = self.model.nodes.get(self.selected_node or "")
        one: Dict[str, Any] = {}
        if result is not None:
            one = {"features": dict(getattr(result, "features", {}) or {})}
        # meta 在 **context** 上，不在 result 上（result 只帶 features/score/bin）。
        ctx = getattr(result, "context", None) if result is not None else None
        meta = dict(getattr(ctx, "meta", {}) or {})
        # 「這張卡產出哪些特徵」要問卡片庫（含 output_prefix）—— 儀表只負責畫。
        feats: List[str] = []
        if node is not None:
            try:
                feats = list(get_step(node.step).resolve_features(node.params))
            except Exception:              # noqa: BLE001 — 顯示用
                feats = []
        # 儀表要跟著**畫面上正在看的東西**走：並排比對打開時是左右那兩條流，
        # 所以底下的直方圖也是兩張、順序一樣（使用者是拿它們互相對照的）。
        shown = [self.stream_combo.currentText()]
        if self._compare_on:
            shown.append(self.stream_combo_b.currentText())
        insp.set_context(self.selected_node or "",
                         params=dict(node.params) if node else {},
                         result=one, batch=self.trial_results, meta=meta,
                         feature_names=feats,
                         shown_streams=[s for s in shown if s])
        self.inspector_summary.setText(insp.summary())

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
            self._status("Select a card that defines a region first.", "error")
            return False
        items = self._items()
        if not items:
            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
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

    @property
    def profile_panel(self) -> Any:
        """投影曲線面板 —— 現在住在 ``ProfileInspector`` 裡面（F7-17）。

        保留這個名字是因為它是「這張卡的面板」的對外身分（測試與狀態列都用
        它）。選的不是投影定位卡時回一個**空的替身**，這樣呼叫端不必到處
        寫 ``if is None``。
        """
        insp = self._inspector
        panel = getattr(insp, "panel", None)
        if panel is not None:
            return panel
        if getattr(self, "_no_profile", None) is None:
            self._no_profile = ProfilePanel(self)
            self._no_profile.setVisible(False)
        return self._no_profile

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

    def _default_stream(self, images: Dict[str, Any]) -> str:
        """點一張卡時，左邊那張圖預設顯示哪一條流。

        規則是**這張卡的主要輸出**，不是「它寫過的最後一條流」。這兩者以前被
        當成同一件事（取 ``writes`` 的最後一個），但當時 Enhance 卡的
        ``resolve_writes`` 是 ``[主流] + 附帶的那一串``，於是預設值一路是那一串
        的最後一項 —— 點 Normalize 就跳到 ``ref``。並排比對開著、右邊又停在
        ``ref`` 的時候，畫面就變成左右兩張一模一樣的 ref，每點一張卡都要手動
        切回來（F7-9 試用回饋 §4）。F7-18 之後一張卡只寫一條流，兩者又合一了，
        但這條規則仍然是對的（``roi_template`` 這類卡的 writes 不只一項）。
        """
        # 並排打開時左邊固定從 test 起跳（右邊就是 ref）——「兩張輸入影像」是
        # 並排唯一的用途，而每次點卡片都要重認一次哪邊是哪邊的話，比對就慢了。
        if self._compare_on and "test" in images:
            return "test"
        nid = self.selected_node
        node = self.model.nodes.get(nid) if nid else None
        if node is not None:
            for name in self._PRIMARY_PARAMS:
                # ``streams`` 是**一串**（"test,ref"）—— 整串當流名去比一定
                # 落空，然後就掉到下面的 writes 分支取最後一項，於是點一張
                # 兩條流的 Normalize 會跳到 ref。取第一條才是「這張卡的主流」。
                for val in str(node.params.get(name, "") or "").split(","):
                    val = val.strip()
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
        self._refresh_region_overlay()

    def region_overlay(self) -> List[Tuple[float, float, float, float]]:
        """**選著的那張卡**牽涉到的框（正規化座標，可能有好幾個）。

        兩種來源，同一個畫法：
        - 這張卡**定義**的區域（``resolve_regions_out``，F7-11 起）——
          調 Region 卡時看框跟著參數動；
        - 這張卡**引用**的區域（``resolve_regions_in``，2026-08-14 使用者
          要求）—— 選 Gray-level stats / Mask from regions 時，畫面直接回答
          「我到底在量哪裡」。以前量測卡選起來預覽上什麼都沒有，roi 填錯
          只能用數字猜。

        仍然只畫**選著那張卡**的，不是 context 裡所有的框：一份 recipe 常常
        有好幾張 Region 卡，全部畫出來分不清誰是誰。
        """
        node = self.model.nodes.get(self.selected_node or "")
        ctx = getattr(getattr(self, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return []
        try:
            step_cls = get_step(node.step)
            produced = list(step_cls.resolve_regions_out(node.params))
            consumed = list(step_cls.resolve_regions_in(node.params))
        except Exception:                  # noqa: BLE001 — 顯示用，不能擋畫面
            return []
        names: List[str] = []
        for name in produced:
            # ``_center`` 是同一組框裡的一個，畫兩次只會變成粗一點的線。
            # 它的角色由 focus 表達（見下面），不是多畫一個框。
            # （**引用**的不套這條 —— 量測卡明確指著 ``cross_center`` 時，
            #   那個框就是它在量的地方，當然要畫。）
            if name.endswith("_center") or name in names:
                continue
            names.append(name)
        for name in consumed:
            if name and name not in names:
                names.append(name)
        out: List[Tuple[float, float, float, float]] = []
        for name in names:
            out.extend(tuple(float(v) for v in r)
                       for r in ctx.roi_norm_rects(name))
        return out

    def _refresh_region_overlay(self) -> None:
        """把框疊到預覽影像上。**每次預覽算完都會走這裡**，所以拖參數的時候
        框是跟著動的 —— 那正是這種參數唯一調得動的方式（F7-8）。"""
        boxes = self.region_overlay()
        focus = self._focus_box_index(boxes)
        for view in (self.image_view, self.image_view_b):
            view.set_overlay(boxes, focus)

    def _focus_box_index(self, boxes: Sequence[Sequence[float]]) -> int:
        """哪一個框要畫成醒目的那一個 —— 離影像正中心最近的那個。

        缺陷永遠在 patch 正中心（裁切方式保證的），所以那一塊就是「**這一顆**
        發生了什麼」的所在。一堆一模一樣的框裡看不出哪個是它。
        """
        best, best_d = -1, None
        for i, (nx, ny, nw, nh) in enumerate(boxes):
            d = (nx + nw / 2.0 - 0.5) ** 2 + (ny + nh / 2.0 - 0.5) ** 2
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

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
            # 打開的當下重挑一次左右兩條流：預設是 test / ref。手動挑過的
            # (``_user_stream``) 仍然優先 —— 這裡只負責「還沒挑過」的情況。
            self._populate_streams(self._preview_images or {})
            self._show_current_stream()
            scale, offset = self.image_view.view_state()
            self.image_view_b.set_view(scale, offset)
        else:
            self.image_view_b.set_image(None)
        # 儀表跟著畫面走：兩張圖 → 兩張直方圖（見 _refresh_inspector）。
        self._refresh_inspector(getattr(self, "_last_result", None))
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
            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
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
                         % (first.title, first.detail, more), "error")
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
                self._status("Trial run failed: %s: %s" % (type(e).__name__, e), "error")
                return False
            self._apply_trial_results(results, time.time() - t0)
            return True

        self._trial_t0 = time.time()
        if not self.trial_worker.start(recipe, self.dataset, limit,
                                       workers=workers, cache_dir=cdir):
            self._status("A run is already in progress — please wait.")
            return False
        self._progress_set(0, limit, "%v / %m defects")
        self._show_stop(True)
        self._status("Running: 0 / %d" % limit)
        return True

    def _on_trial_clicked(self) -> None:
        self.run_trial(int(self.spin_trial_n.value()), workers=TRIAL_WORKERS,
                       cache_dir=DEFAULT_CACHE_DIR)

    def _on_full_clicked(self) -> None:
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
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
        self._refresh_inspector(self._last_result)   # 儀表吃的是整批（F7-17）
        self._update_action_states()
        ok = sum(1 for r in results if r.get("ok"))
        fail = len(results) - ok
        # 被按停止的那一批**不能講「finished」**：數字是真的，但它描述的是
        # 「你叫我停的時候跑到哪裡」，不是整批的結果。差一個字，後面所有
        # 根據這批數字做的判斷就都建立在錯的前提上。
        stopped = bool(self.trial_worker.is_aborted())
        msg = ("%s: %d defects (%d ok, %d failed) in %.1f s"
               % ("Run stopped" if stopped else "Run finished",
                  len(results), ok, fail, float(elapsed)))
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
            self._status("No results to export yet — run a trial first.", "error")
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

    def open_recipe_library(self, directory: Optional[Any] = None) -> Optional[Any]:
        """開範例 recipe 庫；選了哪份就直接載進流程面板。

        ``directory`` 只給測試用（正式路徑一律走 ``welcome.RECIPES_DIR``）——
        `examples/` 移除之後，「照資料夾內容列出來」這件事需要一個真的有東西的
        資料夾才測得到，而那個資料夾不該是 repo 的一部分。
        """
        dlg = self.library_dialog
        if dlg is not None and directory is not None:
            dlg.close()
            dlg = self.library_dialog = None
        if dlg is None:
            dlg = RecipeLibraryDialog(directory=directory, parent=self)
            dlg.recipe_chosen.connect(self._on_recipe_chosen)
            self.library_dialog = dlg
        else:
            dlg.reload()
        if dlg.count() == 0:
            self._status("No templates found — the sample recipe library is empty.")
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
            self._status("Could not generate sample data: %s: %s" % (type(e).__name__, e), "error")
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

    def _on_open_stack(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image stack", "",
            "Multi-page TIFF (*.tif *.tiff);;All files (*)")
        if not path:
            return
        # 「一顆幾張」問一次就好，而且**預設值要是這個檔案自己的頁數線索**：
        # 問這一格的時候使用者手上唯一的事實是「這個檔案有幾頁」，所以先講出來。
        pages = 0
        try:
            from adept.core.ingest import tiff_index
            pages = int(tiff_index.n_pages(path))
        except Exception:                       # noqa: BLE001 — 只是拿來寫提示
            pages = 0
        prompt = ("How many images make up one defect?\n\n"
                  "%s\nEvery N consecutive pages become one defect; enter 1 if "
                  "each page is its own defect. Name them afterwards on the "
                  "Load images card." % ("This file has %d page(s)." % pages
                                         if pages else ""))
        n, ok = QInputDialog.getInt(self, "Images per defect", prompt, 1, 1,
                                    max(1, pages) if pages else 999)
        if not ok:
            return
        self.load_stack_path(path, n)

    def _on_open_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Open folder of images", "")
        if not d:
            return
        self.load_folder_path(d)

    def _on_open_recipe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Recipe", "", "Recipe JSON (*.json);;All files (*)")
        if not path:
            return
        self.load_recipe_path(path)

    # ==================================================================== #
    # 關窗
    # ==================================================================== #
    #: 關窗前要不要問「還沒存」。測試整批把它關掉 —— 一個 modal 對話框會讓
    #: headless 測試永遠停在那裡（而不是失敗），那種卡住最難查。
    PROMPT_ON_CLOSE = True

    def unsaved_changes(self) -> bool:
        """有沒有還沒被保存的編輯（明確狀態，不要去猜）。

        名字沿用 F7-16。存檔功能拿掉之後它的意思更強了：**沒有任何辦法保住
        這份 pipeline**，關掉就是真的沒了。
        """
        return bool(self.model.dirty)

    def _ask_unsaved(self) -> str:
        """問使用者確定不確定。回 ``"discard"`` / ``"cancel"``。

        以前有三個答案（存 / 丟掉 / 取消）。存檔功能還沒支援（engine 先做完
        再回來），所以「存」那個選項會是一顆做不到自己承諾的鈕 —— 拿掉。
        剩下的兩個仍然要問：**現在關掉是不可逆的**。

        單獨一個方法是為了測試接得住 —— 要驗的是「答案各自會怎樣」，
        不是「QMessageBox 長什麼樣」。
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Close without keeping this pipeline?")
        box.setText("Closing now discards the pipeline you just built.")
        box.setInformativeText(
            "Saving a recipe to a file is not supported yet, so there is no "
            "way to get this back — write down the settings you care about "
            "before you close.")
        box.setStandardButtons(QMessageBox.Discard | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        answer = box.exec()
        return "discard" if answer == QMessageBox.Discard else "cancel"

    def confirm_close(self) -> bool:
        """可以關了嗎。預設答案是 **Cancel**（「先別關」）—— 關掉之後沒有任何
        辦法把這份 pipeline 找回來。"""
        if not (self.PROMPT_ON_CLOSE and self.unsaved_changes()):
            return True
        return self._ask_unsaved() == "discard"

    def showEvent(self, event) -> None:       # noqa: D102 - Qt hook
        super().showEvent(event)
        # 中欄的畫布/設定比例第一次 show 才套 —— setSizes 要有實際高度才
        # 算得出來（見 _build_body 的說明）。只做一次：之後的比例是使用者
        # 自己拖的，重新 show（從最小化回來）不可以把它蓋掉。
        if not self._layout_ratio_applied:
            self._layout_ratio_applied = True
            self.set_params_open(self._params_open)

    def closeEvent(self, event) -> None:      # noqa: D102 - Qt hook
        if not self.confirm_close():
            event.ignore()
            return
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
