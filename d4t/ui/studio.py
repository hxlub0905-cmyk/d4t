# d4t Studio 主視窗 — authored 2026-07-28 (M3 收尾).
"""``StudioWindow`` —— 把 M3 的元件、view-model 與背景工作接成一台可用的機器。

版面（全部用 QSplitter，使用者拉得動；F100 v3，
`docs/history/plans/F100-workbench-layout.md` §8）::

    ┌ 工具列：開啟 Recipe／存檔／範本 ｜ 復原／重做 ｜ Results／說明▾／主題
    │         ｜ 試跑筆數 ▶試跑 ▶全跑                                      ┐
    ├──────────┬──────────────────────────────────┬──────────────────────┤
    │ 卡片庫    │ 流程（PipelineCanvas）—— 導覽，一排卡 │ 單顆預覽：◀ ▶ 影像流   │
    │ Library  │                                  │        ImageView     │
    │ rail+    │                                  │  Verdict · score     │
    │ panel    ├──────────────────────────────────┼──────────────────────┤
    │          │ 參數表單 / 分數編輯 / 判定樹一步     │ 這張卡的儀表          │
    │          │ （吃滿中欄的寬）                   │ （Card / Features）  │
    ├──────────┴──────────────────────────────────┴──────────────────────┤
    │ Problems 列（為什麼還不能跑）／ 狀態列：進度 / 訊息                     │
    └─────────────────────────────────────────────────────────────────────┘

    Build 模式把工作台（設定區）與右欄都收掉，畫布吃滿；Tune（預設）全開。
    右欄上下是一根 splitter。同一天走過三版（F100 §2／§7／§8），使用者定的
    是這一版：設定區與直方圖要的都是寬度，各給一整欄。Gallery 與分數分佈
    直方圖住在 Results 視窗（F7-5）。

五條資料流（別搞混）
--------------------
1. **編輯流**：UI 事件 → :class:`~d4t.ui.viewmodel.RecipeModel` 的方法 →
   model 通知 listener → 主視窗刷新 Pipeline/Score 顯示 + 排一次**去抖動
   （300ms）**的預覽。UI 元件自己**不改** model，也不直接呼叫引擎。
2. **預覽流**：:class:`~d4t.ui.workers.PreviewWorker` 算一顆 defect →
   ``ready`` → 填影像流下拉 / ImageView / 特徵表 / 判定 chip。
3. **試跑流**：:class:`~d4t.ui.workers.TrialWorker` 跑 N 顆 →
   ``done`` → 直方圖 + bin 摘要 + Gallery + 狀態列統計。
4. **縮圖流**（M5）：Gallery 捲到哪就要哪幾張縮圖 —— ``thumbs_requested(ids)``
   → :class:`ThumbWorker`（背景執行緒讀檔 + :func:`~d4t.ui.gallery.make_thumb`）
   → ``ready(dict)`` → ``set_thumbs``。**解碼絕不在 GUI 執行緒**，而且忙碌時
   新的請求會合併進待跑集合（``request`` 只累積、不排隊、不阻塞）。
5. **輸出流**（M5 → F16 Stage 5c 改寫）：`Run trial ▾` 選單裡的
   「Run all & write」（以及 Results 視窗上同名的那顆）→
   :meth:`StudioWindow.run_all` → 跑完整批之後把 **Output 段的卡**跑一次
   （:class:`~d4t.ui.workers.OutputWorker`）。**Output 卡是真相**（使用者
   2026-08-20 定調），輸出精靈已經拿掉 —— 寫去哪、寫什麼，全部在畫布上的
   那張卡上，而不是一個跑完才打開的對話框裡。
   ⚠ **試跑不寫**：那不是一個旗標，是兩支函式（見 `core/pipeline/batch.py`）。

調參迴圈的兩半（M5 的重點）
---------------------------
直方圖點一根長條 → ``bar_clicked(lo, hi)`` → Gallery 只留那個分數區間並自動
切到 Gallery 分頁；再點同一根（或按掉 Gallery 上的條件 chip）就取消篩選。
Gallery 雙擊某顆 → ``defect_activated`` → 切回「單顆預覽」並跳到那顆。
門檻的「秒回」路徑仍然成立：拖曳中只用 :func:`~d4t.ui.viewmodel.rebin`
重算 bin 數（**不寫 model、不重跑**），放開才 ``set_threshold``；
**點長條不會動到門檻**（見 ``HistogramWidget`` 的 click / drag 判定）。

測試友善 API（完全不開對話框，見 tests/test_ui_studio_smoke.py 與
tests/test_ui_studio_m5.py）：
:meth:`StudioWindow.load_dataset_path` / :meth:`~StudioWindow.load_recipe_path` /
:meth:`~StudioWindow.load_template` / :meth:`~StudioWindow.select_node` /
:meth:`~StudioWindow.set_defect_index` / :meth:`~StudioWindow.refresh_preview` /
:meth:`~StudioWindow.run_trial` / :meth:`~StudioWindow.save_recipe_path` /
:meth:`~StudioWindow.show_gallery` / :meth:`~StudioWindow.show_preview` /
:meth:`~StudioWindow.request_thumbs` / :meth:`~StudioWindow.run_all` /
:meth:`~StudioWindow.show_welcome` / :meth:`~StudioWindow.open_recipe_library` /
:meth:`~StudioWindow.run_demo`。
每個進入點都自我保護：沒有資料集 / 流程是空的 → 狀態列提示，不丟例外。

首次開啟導覽（M6）
------------------
:class:`~d4t.ui.welcome.WelcomeDialog` 是產品的「上車處」：第一次開窗時
（``show_welcome_on_start`` 預設 ``None`` = 依 QSettings 判斷，且**跑測試時
一律不跳**）排一次非 modal 的顯示。它的三顆鈕只發訊號，動作由本視窗做 ——
其中「用範例資料試一次」就是 :meth:`~StudioWindow.run_demo`：產合成資料 →
載入 → 套 die-to-die 範本 → 試跑 → 切到 Gallery。
"""
from __future__ import annotations
from d4t.core.log import swallowed

import json
import math
import os
import sys
import copy
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QProgressBar,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import d4t.core.steps  # noqa: F401 — 觸發卡片註冊（Qt-free、便宜）
from d4t.core.pipeline import ParamError, Recipe, get_step, list_steps
from d4t.core.pipeline.cellrois import region_names
from d4t.core.pipeline import sampling
from d4t.core.pipeline.engine import (
    FEATURE_OWNER_KEY, feature_prefixes,
)
from d4t.core.pipeline.step import REGISTRY, SCALE_DEFECT, SCALE_LOT
from d4t.core.pipeline.recipe import (
    describe_migration, is_region_edge, version_skew,
)
from d4t.core.pipeline import verdict_features
from d4t.core.pipeline.verdict_trace import verdict_trace

from . import autosave
from .splitters import HairlineSplitter
from . import card_menu
from . import clipboard
from . import windows_menu
from . import baseline
from . import fit_screen
from . import edit_plan
from .canvas import NODE_H, NODE_W, SUMMARY_SEP, PipelineCanvas, run_status_from
from .inspectors import inspector_for
from .problems_bar import ProblemsBar
from .why_panel import WhyPanel
from . import strings
from .status_action import StatusAction, open_folder
from .status_log import StatusHistory
from .gallery import make_thumb
from .region_check import MAX_CHECK, RegionCheckWindow, regions_of_node
from .template_dialog import TemplateDialog
from .results import ResultsWindow, extra_only, summarize_run
from . import results_table
from . import scope
from . import truth_marks
from .scope import (
    is_supported_kind, no_klarf_message, unsupported_kind_message, visible_steps,
)
from .decide_panel import DecidePanel
from .feature_panel import FeaturePanel
from .numbers import format_feature_value
from .viewmodel import (GLV_INTENTS, RecipeModel,
                        is_a_constant_expression, accuracy_at, histogram,
                        rebin)
from . import theme
from .theme import DEFAULT_THEME, THEMES, apply_theme, current_theme
from .workbench import MODES as LAYOUT_MODE_NAMES
from .workbench import WorkbenchLayout
from .welcome import (
    RecipeLibraryDialog, WelcomeDialog, app_settings, save_theme,
    welcome_disabled,
)
from .widgets import (
    IconButton,
    ImageView,
    LibraryPanel,
    ParamForm,
    ProfilePanel,
    VerdictChip,
    _GlyphMixin,
    apply_button_cursors,
    column_header,
    small_button,
)

from .workers import (
    CalibrateWorker, DatasetLoadWorker, OutputWorker, PreviewWorker,
    RegionCheckWorker, TrialWorker,
    _ThreadedWorker,
)


class _GlyphToolButton(_GlyphMixin, QToolButton):
    """工具列上會自己畫圖示的 QToolButton（``_tool_button(icon=…)`` 用）。"""


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
#: ⚠ **這一份跟範本庫是兩件事**（F91 X4）：範本庫 2026-09-08 回來了
#: （`recipes/`，`scope.SHOW_TEMPLATE_LIBRARY`），而**這一支還是死的** ——
#: 它是「用範例資料試一次」那條路的後半段：那條路產的是一批合成的
#: ``ebi_patch`` lot，而這一份就是出貨的 ebi_patch recipe（2026-09-09 之前
#: 指著一個 2026-08-16 刪掉的路徑，所以 `scope.SHOW_SAMPLE_DATA` 一直關著）。
#: `tests/test_shipped_recipes.py` 守著「這一份的 route 是 ebi_patch」。
TEMPLATE_RECIPE = Path(__file__).resolve().parents[2] / "recipes" \
    / "ebi-die-to-die.json"

#: 試跑用的影像段快取位置（跨次試跑重用，第二次調參會明顯變快）。
DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".d4t", "cache")

#: 「用範例資料試一次」把合成 lot 產在哪（使用者自己的檔案一律不碰）。
DEMO_DIR = os.path.join(os.path.expanduser("~"), ".d4t", "demo_lot")

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

#: 主視窗三欄的出廠寬度：卡片庫 | 主欄（畫布在上、設定區與儀表在下）| 單顆預覽。
#: F100 v2（`ui/workbench.py`）：影像回到右欄、全高——調參數的迴圈是
#: 「改一格 → 看影像」，那一刻影像是主角；畫布在 Tune 裡是導覽，要全貌有 Build。
COLUMN_SIZES = (256, 660, 450)

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
               "produced by the pipeline above (e.g. snr_max, area_px, "
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


def _source_id_from(path: Any) -> str:
    """檔名 → 一個能當變數名的代號（F15）。

    規則刻意很笨，因為它要**每次都一樣**：非變數字元換成 `_`、頭尾的 `_` 去掉、
    開頭是數字就補一個 `s`、空的就叫 `src`。（跟 `glas_export.region_name_for`
    同一條路 —— 那裡也是「一個給人取的名字必須先能當變數名」。）
    """
    import re as _re

    stem = os.path.splitext(os.path.basename(str(path)))[0]
    name = _re.sub(r"[^A-Za-z0-9_]", "_", stem).strip("_")
    if not name:
        return "src"
    return name if name[0].isalpha() or name[0] == "_" else "s" + name


def _running_under_pytest() -> bool:
    """現在是不是在跑測試（測試裡建 ``StudioWindow()`` 不准彈導覽）。"""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


#: 欄寬與中欄比例的 QSettings 鍵（F13-1）。跟主題、導覽旗標同一組設定。
COLUMNS_KEY = "ui/columns"
CANVAS_SPLIT_KEY = "ui/canvas_split"


def _save_sizes(key: str, sizes: Sequence[int]) -> None:
    """把一組分隔線位置寫進 QSettings（寫不進去就算了，不准擋關窗）。

    ⚠ **跑測試時不寫**（F100 v2 抓到的）：`_load_sizes` 在 pytest 裡不讀，
    但這一支照寫 —— 於是每一條會關窗的測試都把它那個 1,229 px 視窗的欄寬寫進
    開發者真正的 QSettings，下一次手動開 Studio 看到的是一個他從來沒調成那樣
    的版面（右欄 607、中欄 348）。跟 `autosave` 那條同一句話：測試不准寫進
    使用者真正的那幾個檔案。
    """
    if _running_under_pytest():
        return
    try:
        app_settings().setValue(key, ",".join(str(int(v)) for v in sizes))
    except Exception:
        swallowed("studio._save_sizes")


def _load_sizes(key: str, count: int) -> Optional[List[int]]:
    """讀回一組分隔線位置；**沒有、格式怪、或正在跑測試 → ``None``**。

    測試裡不還原是刻意的：還原了之後，某一次手動跑 GUI 拖過的分隔線會從
    QSettings 漏進下一次的測試，而版面斷言就開始看人品。
    """
    if _running_under_pytest():
        return None
    try:
        raw = str(app_settings().value(key, "") or "")
        out = [int(x) for x in raw.split(",") if x.strip()]
    except Exception:
        swallowed("studio._load_sizes")
        return None
    return out if len(out) == count and sum(out) > 0 else None


def _welcome_on_start_default() -> bool:
    """``show_welcome_on_start=None`` 時的預設：沒勾過「不再顯示」且不在測試中。"""
    if _running_under_pytest():
        return False
    try:
        return not welcome_disabled()
    except Exception:  # 設定讀不到不該擋開窗
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
    from make_sample import generate

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
            except Exception:  # 單顆壞掉不該殺整批
                swallowed("studio.run_sync")
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



def verdict_note(selected_node: Optional[str], verdict_bin: Any,
                 ok: bool) -> str:
    """Verdict 膠囊旁邊那句「為什麼是破折號」（F99 P1-2）。

    只在一種情況講話：預覽跑得好好的、有選一張卡、而判定還沒跑到
    （``bin`` 是空的）。其他情況（沒選卡、跑出錯、真的有判定）都是空字串 ——
    膠囊或狀態列已經在講那件事，這裡再講一次只是把位子佔掉。
    """
    if selected_node and ok and verdict_bin is None:
        return ("preview stops at “%s” — press Esc to run the decision too"
                % selected_node)
    return ""

class StudioWindow(QMainWindow):
    """d4t Studio 主視窗（M3 組裝 + M5 Gallery / 直方圖聯動 / 輸出）。"""

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
        self.setWindowTitle("d4t Studio")

        # ---- 狀態 ---------------------------------------------------------
        # 開窗就先放好 Input 卡（F7-9）：空白畫布對不會寫 code 的人是一道
        # 「現在要幹嘛」的關卡，而答案永遠是同一個 —— 先載入影像。
        self.model = RecipeModel.starter()
        self.dataset: Optional[Any] = None
        #: 掛上的 GLAS 匯出有哪幾層（``[(id, layer 名), …]``；沒掛就是空的）。
        self._gds_layers: List[Any] = []
        self.trial_scores: List[float] = []
        self.trial_results: List[Dict[str, Any]] = []
        #: 上一批的底稿：``rows``（原封不動）、``sig``（量測段簽章）、
        #: ``partial``（被停掉的）、``limit``（跑了幾顆）—— Re-run 與
        #: Write outputs 讀它（2026-09-09）。
        self._last_run: Dict[str, Any] = {}
        #: 使用者正在編判定樹 → 預覽跑到底（連判定），見 `_preview_whole_route`。
        self._tree_focus: bool = False   # M5：Gallery / 輸出的來源
        #: 試跑抽哪幾顆（X3）。預設 `first` —— 老行為，一個位元都不變。
        self.sample_mode: str = sampling.DEFAULT_MODE
        #: 上一次抽樣的紀錄（含種子）。**空的表示還沒跑過**，不是「用了預設」。
        self.sample_note: Dict[str, Any] = {}
        self.defect_index: int = 0
        self.selected_node: Optional[str] = None
        self.recipe_path: Optional[str] = None
        #: 這批資料的 ground truth（``{defect_id: {"is_real": bool}}``）。
        #: 載資料集時自動找 KLARF 旁邊的 ``ground_truth.json``；沒有就 None。
        self.ground_truth: Optional[Dict[Any, Any]] = None
        #: ``_point_at_stream`` 剛剛把線綁到哪個參數（F9-5b 的 ``dst_in``）。
        #: 它是那個函式的第二個回傳值，用屬性傳是為了不動既有呼叫端的形狀。

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
        self._filtered_note: str = ""             # 「只跑這幾個 code」篩掉多少（F50）
        self._preview_epoch = 0                   # 預覽的世代（丟掉過期結果用）
        self._async_epoch = 0                     # 背景那筆出發時的世代
        self.welcome_dialog: Optional[Any] = None
        self.library_dialog: Optional[Any] = None
        self.region_window: Optional[Any] = None   # 區域跨顆檢視（F7-11）
        self.template_dialog: Optional[Any] = None  # 建模板對話框（F7-12）
        self._region_regions: List[str] = []

        # ---- 背景工作 ------------------------------------------------------
        self.dataset_worker = DatasetLoadWorker(self)
        #: 第二份 lot 用**另一個** worker（F15-2）：跟 main 那一份是兩件可以同時
        #: 發生的事，共用一個的話「已經有工作在跑」會把其中一個默默擋掉。
        self.pair_worker = DatasetLoadWorker(self)
        #: 正在載的第二份是**哪一張卡**要的（載完才知道要掛到哪）。
        self._pending_pair: Optional[Tuple[str, str]] = None
        #: 每一份第二 source 上次填了哪幾欄（`carry` 沒變就不用重填）。
        self._pair_filled: Dict[str, Tuple[str, ...]] = {}
        self.preview_worker = PreviewWorker(self)
        self.trial_worker = TrialWorker(self)
        # Output 段的卡（F16 Stage 5c）。**只有 `run_all()` 叫得到它** ——
        # 使用者定調「試跑不寫」，而那件事是結構上的：試跑那條路沒有這一支。
        self.output_worker = OutputWorker(self)
        #: 這一次執行要不要寫出輸出。**跟著那一次執行走**，不是讀當下的 UI
        #: 狀態 —— 使用者按了 Run all 之後可以馬上去改別的東西。
        self._write_outputs_this_run = False
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
        # ⚠ **一定要在 `setStatusBar` 之後**（U2 後半）：`statusBar()` 會自己
        # 建一個，而下一行的 `setStatusBar` 把那一個整個換掉 —— 掛在舊的那個
        # 上面的東西就跟著不見了，而畫面上沒有任何錯誤（第一版就是這樣，
        # 那顆鈕的 parent 是一個已經沒有人看得到的 QStatusBar）。
        self.status_history = StatusHistory(self)
        # 那一句話的「下一步」（X5／X6）。它掛在歷史鈕**左邊** —— 它講的是
        # 剛才那一句，所以要挨著訊息，不是挨著工具。
        self.status_action = StatusAction(self)
        self.statusBar().addPermanentWidget(self.status_action)
        self.statusBar().addPermanentWidget(self.status_history)
        self._build_progress()

        self._wire_widgets()
        self._wire_workers()
        self._build_shortcuts()
        # 「滑過去變手指」以前是每個呼叫端自己記得要做的事，於是只做到一半。
        # 現在改成視窗建好之後掃一次（見 widgets.apply_button_cursors）。
        apply_button_cursors(self)
        self.model.add_listener(self._on_model_changed)
        #: 自動存草稿（U4）—— **一個屬性，沒有方法**：那件事跟主視窗其他的
        #: 責任沒有耦合，所以它住在 `ui/autosave.py`（`CLAUDE.md` §4）。
        #:
        #: 測試裡預設是關的：開一次 `StudioWindow` 就往開發者真正的
        #: ``~/.d4t`` 寫一份草稿的話，他下次開 Studio 會被問要不要救回一條
        #: 測試造出來的 pipeline。要驗它的測試自己 `start()`（同
        #: `_load_sizes` 對 QSettings 的做法）。
        self.autosave = autosave.AutosaveGuard(self)
        if _running_under_pytest():
            self.autosave.stop()

        # F7-1：卡片庫只列目前輸入型別用得到的卡（見 d4t/ui/scope.py）
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

        # **開窗要寬到工具列放得下**（F48，2026-08-28）。
        #
        # 以前這裡一行都沒有，視窗大小是 Qt 從版面的 size hint 湊出來的
        # ——實測 948 px，而工具列的內容那時正好要 916 px：**它是滿的**。
        # 加「Results」那顆鈕（100 px）的第一版因此在預設大小下**看不見**：
        # Qt 把放不下的最後一顆收進右邊那個 » 溢位選單，而使用者要的正是
        # 「按一顆鈕就叫得出 Results」——一顆藏在兩層選單底下的鈕不算數。
        # 抓到它的是既有的 `test_no_separator_fences_off_an_empty_stretch_of_toolbar`
        # （分隔線後面空無一物 = 那一段被收走了）。
        #
        # 所以預設大小改成**由工具列決定**，而不是反過來讓工具列去遷就一個
        # 沒有人選過的數字。`+ 24` 是視窗左右的邊框餘裕。
        #
        # ⚠ 這裡以前寫著「螢幕比這個小的時候由視窗管理員裁掉（Qt 本來就會
        # 做）」——**那句話是錯的**（U1，2026-09-08）：視窗管理員不會裁，
        # 一個比螢幕大的視窗就是一個底部那排鈕在畫面外的視窗，而 » 溢位選單
        # 只有在視窗**真的被縮小**的時候才會出現。所以這一行明說地裁，
        # 而 `fit` 會先把最小高度（760）降下來 —— 不做那一步 `resize` 是
        # 沒有效果的。
        want_w = max(self.toolbar.sizeHint().width() + 24, 1000)
        fit_screen.fit(self, max(want_w, self.width()),
                       max(760, self.height()))

        if show_welcome_on_start is None:
            show_welcome_on_start = _welcome_on_start_default()
        # ⚠ 跑測試時**這一扇**關窗對話框預設關掉（F99）。conftest 那支 autouse
        # 只在 `d4t.ui.studio` 已經 import 的時候改得到類別屬性——在 fixture 裡
        # 才 import 的測試檔改不到，於是一條失敗的測試在 teardown 停在
        # 「要不要存」的 modal 上，faulthandler 都叫不醒（C++ 的 exec 裡 Python
        # 沒有機會跑）。真的要測那扇門的測試自己把它設回 True。
        if _running_under_pytest():
            self.PROMPT_ON_CLOSE = False
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
          「跑整批」降級成選單項目。⚠ 這一條後來被 F16 Stage 5c 悄悄破壞了
          （「Export…」空出來的那一格改成整批入口，於是同一支 `run_all()`
          在工具列上有兩顆鈕）—— 2026-08-24 使用者指出來之後拿掉那一顆，
          這條規矩恢復成唯一的答案。

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

        # **資料的入口不在工具列上**（F14-1，2026-08-19 使用者定調：
        # 「工具列拿掉吧（會混淆）」）。
        #
        # 它現在長在**讀那份資料的那張卡上**（`ParamForm.set_source_action`）。
        # 理由跟這幾輪一直在講的是同一條：以前檔案在工具列上選，而畫布上那張
        # Load 卡完全不會說它讀的是哪個檔案 —— 同一件事兩個地方，而畫布是說謊
        # 的那一個。之後一份 recipe 要掛好幾個 source 的時候，入口也已經在對的
        # 地方了。
        #
        # **入口沒有變少，只是搬家**：畫面最大的那一塊（沒有資料時的空白狀態）
        # 仍然一種 source 一列（`empty_source_buttons`，從同一張 `INPUT_SOURCES`
        # 長出來），而那是第一次進來的人真的會看的地方。
        self.btn_open_recipe = self._tool_button(
            "Open recipe…", "Load a recipe JSON", self._on_open_recipe,
            icon="document")
        # **存檔回來了**（2026-08-26）。2026-08-16 拿掉的理由是「先把整個
        # engine 用好，再來支援」，而 Phase 1 同一天就收斂了 —— 那個前提到期。
        #
        # 一顆鈕、兩個快捷鍵：`Ctrl+S` 存回原檔（第一次沒有原檔就問），
        # `Ctrl+Shift+S` 一定問。鈕接的是 `Ctrl+S` 那一支 —— 使用者按工具列上
        # 那顆鈕的意思是「存起來」，不是「我要選一個路徑」。
        self.btn_save_recipe = self._tool_button(
            "Save recipe…", "Save this pipeline as a recipe JSON",
            self._on_save_recipe, icon="save")
        self.btn_examples = self._tool_button(
            "Templates…",
            "Open the template library — every entry is a complete, runnable "
            "pipeline. Start here rather than from an empty pipeline.",
            self.open_recipe_library, icon="templates")
        # **2026-09-08（F91 X4）：這顆鈕回來了。** 它收起來的理由是「範本庫是
        # 空的」（``examples/`` 已移除），而 `recipes/` 現在有出貨的 recipe、
        # 逐份有測試跑過 —— 那個理由到期了。開關在
        # ``scope.SHOW_TEMPLATE_LIBRARY``。
        self.btn_examples.setVisible(bool(scope.SHOW_TEMPLATE_LIBRARY))
        # ⚠ **這裡以前還有一顆「Run all & write」**，而它跟 `Run trial ▾` 選單
        # 裡的「跑整批」是**同一支函式**（兩邊都是 `run_all()`，一個位元的
        # 差別都沒有）。兩個決定各自都對，只是沒有互相看到：M7 把「全跑」收進
        # 下拉（見這支的說明），而 F16 Stage 5c 把「Export…」空出來的那一格
        # 改成整批入口。合起來就是同一個動作在工具列上有兩顆鈕。
        #
        # 使用者 2026-08-24：「若沒差或差不多 請留一個即可（傾向 trial）」。
        # 留下的是下拉裡那一項 —— 而**「跑完之後要做的那件事」搬到它真的會
        # 發生的地方**：Results 視窗（使用者正在看試跑結果，下一步才是整批）。
        # 工具列因此只剩一顆有顏色的鈕，而那正是這個畫面唯一的主要動作。
        self.btn_undo = self._tool_button(
            "", "Undo the last change", self.undo, icon="undo")
        self.btn_redo = self._tool_button(
            "", "Redo the change you just undid", self.redo, icon="redo")
        # **第三級：純圖示、沒有框**（F13-2）。工具列上「有框的字」是按鈕、
        # 「沒框的字」讀起來是選單列（那條規矩沒有變，見 theme.py）——
        # 但這幾顆**沒有字**，所以那個顧慮不成立，而它們也不該跟 `Open KLARF…`
        # 搶同一級的視覺重量：它們是隨時在旁邊的工具，不是流程上的一步。
        for b in (self.btn_undo, self.btn_redo):
            b.setProperty("variant", "ghost")
        # **Results 視窗的入口**（F48，2026-08-28，使用者：「可以改成加一個
        # 按鈕獨立呼叫一個視窗嗎（目前是跑完才會出來）」）。
        #
        # 以前只有兩條路會開它：跑完自動彈出、或在直方圖上點一根長條 ——
        # 兩條都要**先跑過一批**。關掉之後想再看一次，唯一的辦法是再跑一次
        # （而 `results.py` 的檔頭一直寫著「關掉它不會丟掉結果」：結果確實
        # 還在，只是沒有一顆鈕叫得出來，所以那句話描述著一個不存在的入口）。
        #
        # **跟 Help／主題同一段**，而不是接在 `Run trial` 右邊。動線上「跑 →
        # 看結果」確實是那個順序，但工具列的最後一格是留給那顆藍鈕的
        # （`test_the_toolbar_is_grouped_not_one_long_row` 守著：試跑在最後
        # 面）—— 而這一段的定義正好就是它：**不屬於流程、但要隨時找得到**。
        self.btn_results = self._tool_button(
            "Results", "Open the Results window - score distribution, "
                       "thumbnails and the per-defect table (Ctrl+Shift+R)",
            self.show_gallery, icon="popout")
        # **這顆鈕以前不會說裡面有沒有東西**（U21）。`ResultsWindow` 是先建好、
        # 跑完才 show，關掉不丟結果 —— 機制是對的，但使用者的心智模型裡「關掉
        # 視窗」通常等於「丟掉」，而鈕上沒有任何東西反駁那個猜測。
        self._refresh_results_button()
        self.btn_help = self._tool_button(
            "Help", "Reopen the getting-started tour (includes “Try it with "
                    "sample data”)",
            lambda: self.show_welcome(force=True))
        # 那顆鈕的小箭頭：現在開著哪些視窗（F99 P2-6；內容在 `windows_menu`）。
        windows_menu.attach(self.btn_help, self._open_windows)
        # 主題切換：一顆字元鈕，不佔位子也找得到（偏好存 QSettings）
        self.btn_theme = self._tool_button(
            "", "Switch between the light and dark theme",
            self.toggle_theme, icon="theme")
        self.btn_theme.setProperty("variant", "ghost")

        # 一段 = 一種事情；段與段之間一條分隔線。
        #
        # ⚠ **整段都看不見的時候不要放那條分隔線。** 「Templates…」曾經是藏著的
        # （`scope.SHOW_TEMPLATE_LIBRARY`，2026-09-08 打開），而它那一段以前
        # 還有「Run all & write」
        # 撐著；那顆鈕 2026-08-24 拿掉之後，那一段變成空的 —— 工具列上因此出現
        # 兩條連在一起的分隔線，中間夾著什麼都沒有。分隔線講的是「這裡換一種
        # 事情」，而一條隔開空氣的線只是雜訊。
        for group in ((self.btn_open_recipe, self.btn_save_recipe),
                      (self.btn_examples,),
                      (self.btn_undo, self.btn_redo)):
            # ⚠ **鈕還是要 addWidget**（藏著的也要）：建了卻沒加進工具列的
            # widget 會以工具列為 parent 疊在左上角
            # （`test_every_button_built_for_the_toolbar_is_actually_on_it`
            # 在第一版就抓到了）。跳過的只有那條**分隔線**。
            #
            # ⚠ 而「這一段看不看得見」**要在 addWidget 之前問**，用的也不是
            # `isHidden()`：`addWidget` 會把 widget 包進一個 QWidgetAction，
            # 而 Qt 在工具列真的顯示出來以前把它們**全部**藏著 —— 那時候
            # 每一顆都答 hidden，於是一條分隔線都不會加。要問的是「**我們**
            # 有沒有明講要藏它」（`setVisible(False)` 留下的那兩個屬性）。
            visible = [b for b in group
                       if not (b.testAttribute(Qt.WA_WState_ExplicitShowHide)
                               and b.testAttribute(Qt.WA_WState_Hidden))]
            for b in group:
                bar.addWidget(b)
            if visible:
                bar.addSeparator()

        # 分流的 route 切換器（F23 期2）：`RecipeModel` 一次編一條 route
        # （§6 第一期不動的那條），切換是「換一條來編」—— 畫布跟著換。
        # 只有一條 route 時整組收起來（多數 recipe 用不到它）。
        self.lbl_route = QLabel("Route ", bar)
        self.route_combo = QComboBox(bar)
        self.route_combo.setToolTip(
            "Which route (which set of cards) the canvas is editing. "
            "With route_by, each defect picks its own route at run time.")
        self.route_combo.activated.connect(self._on_route_combo)
        # ⚠ 工具列上的顯示/隱藏要走 **addWidget 回傳的 QAction**：直接
        # `widget.setVisible(False)` 會被 QToolBar 的排版蓋回去 —— 症狀是
        # 單 route 的 recipe 工具列上掛著一個空的下拉。
        self._route_actions = [bar.addWidget(self.lbl_route),
                               bar.addWidget(self.route_combo)]
        for act in self._route_actions:
            act.setVisible(False)

        spacer = QWidget(bar)
        spacer.setObjectName("toolbarSpacer")
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        # 右邊：不屬於流程、但要隨時找得到的那幾顆。
        bar.addWidget(self.btn_results)
        bar.addWidget(self.btn_help)
        bar.addWidget(self.btn_theme)
        bar.addSeparator()

        # **工具列的字要跟著抽樣方式換**（X3）。以前這裡寫死是「First」，
        # 而如果換了抽樣方式畫面卻沒有變，就是這個功能最危險的失敗方式：
        # 跑的東西變了、看的人不知道。字從 `sampling.describe()` 來。
        #
        # ⚠ **那個字自己就是那顆鈕。** 第一版是「一個 QLabel ＋ 旁邊一顆
        # 『…』」，而那多花 56 px —— 工具列在 1366×768 上量出來 1,285 px，
        # 超過那台機器的 1,229 px，尾巴幾顆會被收進 » 溢位選單
        # （`test_ui_small_screen` 當場抓到）。合成一顆之後既省了寬度，
        # 也比較誠實：會變的那個字就是可以點的那個東西。
        self.lbl_trial_n = QToolButton(bar)
        self.lbl_trial_n.setCursor(Qt.PointingHandCursor)
        self.lbl_trial_n.setPopupMode(QToolButton.InstantPopup)
        bar.addWidget(self.lbl_trial_n)
        self.spin_trial_n = QSpinBox(bar)
        self.spin_trial_n.setRange(10, 5000)
        # 「First 200」旁邊沒有單位時，200 可以是任何東西（秒？百分比？）。
        self.spin_trial_n.setSuffix(" defects")
        self.spin_trial_n.setValue(DEFAULT_TRIAL_N)
        self.spin_trial_n.setToolTip(
            "How many defects a trial run covers (keep it small while tuning)")
        bar.addWidget(self.spin_trial_n)

        # 抽樣方式（X3）：**一個下拉，掛在上面那個會變的字上**（見上）。
        menu_s = QMenu(self.lbl_trial_n)
        self._sample_actions = {}
        for mode in sampling.MODES:
            word, why = sampling.describe(mode)
            act = menu_s.addAction(word)
            act.setToolTip(why)
            act.setCheckable(True)
            act.setChecked(mode == self.sample_mode)
            act.triggered.connect(
                lambda _c=False, m=mode: self.set_sample_mode(m))
            self._sample_actions[mode] = act
        self.lbl_trial_n.setMenu(menu_s)
        self.set_sample_mode(self.sample_mode, say=False)

        self.btn_trial = self._tool_button(
            "Run trial", "Run the current pipeline over the first N defects "
                         "and show the score distribution",
            self._on_trial_clicked, primary=True, icon="play")
        # 「跑整批」是同一顆鈕的次要動作：點主體 = 試跑，點箭頭才看得到它。
        menu = QMenu(self.btn_trial)
        # ⚠ ``&&`` 不是筆誤：Qt 把單一個 ``&`` 當成助憶鍵的記號吃掉，畫出來
        # 是 **``Run all _write``**（使用者就是這樣叫它的）。要顯示一個真的
        # ``&`` 就得寫兩個。
        #
        # 名字跟 Results 視窗那顆**逐字相同** —— 同一個動作在兩個地方叫兩個
        # 名字，正是上面那兩顆鈕變成兩顆的第一步。
        # 2026-09-09 起它**只跑，不寫**：寫是 Results 視窗上另一顆鈕
        # （「Write outputs」）—— 使用者要先看過結果再決定要不要寫。
        self.act_run_all = QAction("Run all", menu)
        self.act_run_all.setToolTip(
            "Run every defect, not just the first N. Nothing is written - "
            "press “Write outputs” in Results when the numbers look right.")
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
        ("Ctrl+S", "save_recipe"), ("Ctrl+Shift+S", "save_recipe_as"),
        ("Ctrl+R", "run"), ("Ctrl+Shift+R", "results"),
        ("Ctrl+Z", "undo"), ("Ctrl+Shift+Z", "redo"), ("Ctrl+Y", "redo"),
        ("Ctrl+0", "zoom_reset"), ("Ctrl++", "zoom_in"), ("Ctrl+=", "zoom_in"),
        ("Ctrl+-", "zoom_out"), ("Ctrl+Shift+F", "zoom_fit"),
        ("Ctrl+F", "find_card"),
        ("Ctrl+Left", "prev_defect"), ("Ctrl+Right", "next_defect"),
        ("Ctrl+B", "layout_mode"),
        # U18：Delete / Esc 以前只住在畫布與 cell_canvas 各自的 keyPressEvent
        # 裡，主快捷鍵表上沒有 —— 於是「這個工具有哪些鍵」這個問題有兩個答案，
        # 而使用者讀得到的是不完整的那一個。
        #
        # ⚠ **它們綁在畫布上，不是綁在視窗上**（見 `_WIDGET_SHORTCUTS`）。
        # Delete 綁成 window-level 的話，使用者在參數區的輸入框裡按 Delete
        # 會刪掉一張卡 —— 那是這張表最貴的一種錯。
        ("Del", "delete_selected"), ("Esc", "clear_selection"),
        ("Ctrl+C", "copy_cards"), ("Ctrl+V", "paste_cards"),
        ("Ctrl+D", "duplicate_cards"),
    )

    #: 這幾個鍵**只在畫布上**管用（見上面那段 ⚠）。
    #:
    #: 它們仍然列在 `SHORTCUTS` 裡，因為那張表回答的是「這個工具有哪些鍵」——
    #: 一個使用者讀得到的答案，不是一份綁定清單。
    # ⚠ Ctrl+C / Ctrl+V 跟 Delete 同一條規矩（U18）：掛在**畫布**上。綁在視窗
    # 層的話，使用者在參數格裡按 Ctrl+C 複製一個數字，複製到的會是一張卡。
    _WIDGET_SHORTCUTS = frozenset(("delete_selected", "clear_selection",
                                   "copy_cards", "paste_cards",
                                   "duplicate_cards"))

    def _build_shortcuts(self) -> None:
        handlers = {
            "open_klarf": self._on_open_klarf,
            "open_recipe": self._on_open_recipe,
            "save_recipe": self._on_save_recipe,
            "save_recipe_as": self._on_save_recipe_as,
            "run": self._on_trial_clicked,
            "results": self.show_gallery,
            "undo": self.undo,
            "redo": self.redo,
            "zoom_reset": self.pipeline.reset_zoom,
            "zoom_in": lambda: self.pipeline.zoom_by(1.25),
            "zoom_out": lambda: self.pipeline.zoom_by(1 / 1.25),
            "zoom_fit": self.pipeline.fit,
            "find_card": self.focus_card_search,
            "prev_defect": lambda: self.step_defect(-1),
            "next_defect": lambda: self.step_defect(+1),
            "layout_mode": self.toggle_layout_mode,
            "delete_selected": self._delete_selected_on_canvas,
            "clear_selection": self._clear_canvas_selection,
            "copy_cards": self.copy_cards,
            "paste_cards": self.paste_cards,
            "duplicate_cards": self.duplicate_cards,
        }
        self._shortcuts = []
        for keys, name in self.SHORTCUTS:
            # 畫布專用的那幾個掛在畫布上、而且是 `WidgetWithChildrenShortcut`
            # —— 焦點不在畫布裡的時候它們根本不會被叫到（U18）。
            host = self.pipeline if name in self._WIDGET_SHORTCUTS else self
            sc = QShortcut(QKeySequence(keys), host)
            if name in self._WIDGET_SHORTCUTS:
                sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(handlers[name])
            self._shortcuts.append(sc)

        # 按鍵存在還不夠 —— 使用者要**發現得到**。工具列的 tooltip 是他唯一
        # 會停留的地方，所以把快捷鍵寫進去（作業系統慣例：括號附在後面）。
        #
        # 註冊而不是「設一次」：``_update_action_states`` 每次 refresh 都會重寫
        # 這幾顆的 tooltip（「還沒有東西可以存」之類的原因），設一次的話第一次
        # refresh 就被蓋掉了。所以改成**設 tooltip 的那個動作自己會補上快捷鍵**。
        self._tip_keys = {
            id(self.btn_open_recipe): "Ctrl+Shift+O",
            id(self.btn_save_recipe): "Ctrl+S",
            id(self.btn_trial): "Ctrl+R",
            # F14-1：`Ctrl+O` 的鈕搬到空白狀態與入口卡上了（工具列那幾顆
            # 拿掉了），而快捷鍵一個字都沒變 —— 它要在**還看得到的**那顆鈕上
            # 講出來，不然它就只活在原始碼裡。
            id(self.btn_empty_open): "Ctrl+O",
            # F7-22：這兩顆這一輪才長出來，快捷鍵 F7-16 就有了。
            id(self.btn_undo): "Ctrl+Z",
            id(self.btn_redo): "Ctrl+Shift+Z",
        }
        for w in (self.btn_open_recipe, self.btn_save_recipe,
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
        # **翻譯層擺在共用的那一支**（U14）：工具列的每一顆鈕都流過這裡，所以
        # 包這一次就涵蓋整條工具列 —— 而呼叫端一個字都不用改。那正是「之後
        # 不必改 38 個檔案」那句話成立的方式。
        b.setText(strings.tr(text))
        b.setToolTip(strings.tr(tip))
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
        # 「插入數字 ▾」每一項的說明與顏色點（`number_picker`，2026-09-09）。
        self.param_form.number_info_provider = self._number_info
        self.score_pane = self._build_score_pane()
        # 判定樹一步的編輯面板（F24 ③）—— 點畫布上的菱形時換到它。
        from .tree_panel import TreePanel

        self.tree_pane = TreePanel(self)
        self.tree_pane.set_model(self.model)
        self.tree_pane.step_requested.connect(self._on_tree_step_clicked)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.param_form)     # index 0
        self.stack.addWidget(self.score_pane)     # index 1
        self.stack.addWidget(self.tree_pane)      # index 2

        middle = HairlineSplitter(Qt.Vertical, self)
        middle.addWidget(self.pipeline)
        # 下半在 `_build_preview_pane` 跑完之後才接得起來（儀表是在那裡建的）
        # —— 見 `_build_params_row`。
        self.canvas_column = middle

        # 「為什麼還不能跑」的常駐清單（U2）—— **整個視窗最下面一條，橫跨三欄**
        # （見下面 `setCentralWidget` 那一段）。它不在任何一個 splitter 裡：
        # 它是使用者在畫布上找不到路時唯一的答案，而一個拖得掉的東西答不到
        # 那件事。
        self.problems = ProblemsBar(self)
        self.problems.problem_activated.connect(self._on_problem_activated)
        # **開窗時沒有選任何卡片，所以設定區是收起來的**（F13-1）。
        # 以前它一律攤開，於是畫面最大的一塊（中欄下半，1600×1000 上量到
        # 551px 高）裝的是一行灰字「(Pick a card from the library…)」——
        # 一塊叫人去別的地方點東西的空白，而它同時把畫布壓到 50% 縮放，
        # 卡片的副標（「這張卡吃什麼吐什麼」）當場讀不出來。
        # F100：那個狀態現在住在 `WorkbenchLayout.open`（工作台攤開著嗎）——
        # 而 Tune 模式開窗就是攤開的，因為影像住在工作台裡。
        # 比例在 showEvent 才真的套 —— setSizes 要有實際高度才算得出來
        #（isVisible 之前那些數字沒有意義，docs/PITFALLS.md 的老坑）。
        self._layout_ratio_applied = False
        # 右：單顆預覽（F7-5：Gallery 與直方圖搬到 Results 視窗，
        #     主視窗只留「編流程 + 看單顆」，影像因此拿得到整欄高度）
        self.preview_pane = self._build_preview_pane()
        # 參數 ＋ 儀表同欄同框（U8）。要在 preview pane 之後 —— 儀表那幾個
        # widget 是在那一支裡建的。
        middle.addWidget(self._build_params_row())
        middle.setStretchFactor(0, 2)
        middle.setStretchFactor(1, 3)
        # 版面模式的狀態與幾何（F100）—— 邏輯在 `ui/workbench.py`，這裡只接。
        # 主欄 = 畫布/工作台那根 splitter（F100 v2：Verdict 列搬進右欄影像下面）。
        self.main_column = middle

        # Results 視窗（跑完才 show；先建好讓 histogram / gallery 一直有實體，
        # 這樣所有既有接線與測試都不用管它現在開著沒有）
        self.results = ResultsWindow(self)
        self.histogram = self.results.histogram
        self.gallery = self.results.gallery
        self.results.rerun_requested.connect(self.rerun)
        self.results.write_requested.connect(self.write_outputs)
        self.results.class_selected.connect(self._on_verdict_class)

        # 右欄：影像在上、儀表在下（F100 v3），一根直向 splitter，比例記得住。
        self.right_column = HairlineSplitter(Qt.Vertical, self)
        self.right_column.addWidget(self.preview_pane)
        self.right_column.addWidget(self.gauge_pane)
        self.right_column.setStretchFactor(0, 3)
        self.right_column.setStretchFactor(1, 2)
        self.right_column.setCollapsible(0, False)
        root = HairlineSplitter(Qt.Horizontal, self)
        root.addWidget(self.library)
        root.addWidget(self.main_column)
        root.addWidget(self.right_column)
        root.setStretchFactor(0, 0)
        root.setStretchFactor(1, 3)
        root.setStretchFactor(2, 2)
        root.setCollapsible(1, False)
        # 出廠欄寬；上一次關窗的欄寬由 `WorkbenchLayout`（F100 v2）在 showEvent
        # 套（只記 Tune 的：Build 的右欄是 0，不是使用者調出來的）。
        root.setSizes(list(COLUMN_SIZES))
        # 版面模式的狀態與幾何（F100）—— 邏輯在 `ui/workbench.py`，這裡只接。
        self.layout_modes = WorkbenchLayout(
            middle, self.params_row, self.pipeline, self.library,
            root=root, preview_index=2, right=self.right_column,
            load=_load_sizes, save=_save_sizes)
        self.top_splitter = root
        self.root_splitter = root

        # Problems 列住在**三欄的下面、狀態列的上面**（U2）—— 橫跨整個視窗。
        #
        # ⚠ 位置換過兩次，而兩次都是**現有的不變量把它推到這裡**：
        #   1. 包在畫布外面 → `canvas_column.widget(0)` 不再是畫布
        #      （`canvas.py::_build_header` 的說明就寫著誰靠著它，
        #      `test_ui_f8_ui_polish` 當場紅）；
        #   2. 包住整個中欄 → `root_splitter` 的三個子項不再是
        #      `[library, canvas_column, preview_pane]`
        #      （`test_ui_results::test_main_window_keeps_only_the_editing_surface`）。
        # 包 central widget 誰都不礙著 —— 而且**這一塊本來就是視窗層級的答案**
        # （「這份 pipeline 現在能不能跑」不是中欄自己的事）。
        host = QWidget(self)
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(root, 1)
        hl.addWidget(self.problems)
        self.setCentralWidget(host)

    def _build_score_pane(self) -> QWidget:
        """判定段那一欄 —— 內容全部住在 `DecidePanel`（F22-UI）。

        為什麼搬出去：這一欄現在有兩種樣子（一個門檻／一串規則），而規則那一種
        是逐列生出來的。留在 `studio.py`（已經 5000 多行）的話，這一欄會是這個
        檔案裡最長的一段，而它跟視窗的其他部分沒有任何共用的東西。
        """
        self.decide_panel = DecidePanel(self)
        self.decide_panel.set_model(self.model)
        self.decide_panel.mode_changed.connect(self._on_decide_mode)
        self.decide_panel.decision_requested.connect(self.add_decision)
        # 分流的編輯區塊（F23 期2）—— 判定欄**上方**：它在跑之前就決定每一顆
        # 走哪條 route，判定是跑完之後的事，由上往下讀正好是時間順序。
        from .route_panel import RouteByBox

        self.route_box = RouteByBox(self)
        self.route_box.set_model(self.model)
        # ⚠ **建出來再藏，不是不建**（同 `btn_examples` 那一顆）：版面量測、
        # 既有測試、`_refresh_*` 都還指得到它，回復只要改一個字串。
        #
        # ⚠ 而且**它跟畫布上的徽章要同進同出**（`scope.SHOW_ROUTE_BY`）。
        # 只藏徽章的話，使用者仍然編得出一份會分流的 recipe，而畫布上一個字
        # 都不會說 —— 那正是這個 repo 一直在消滅的「畫布說謊」。
        self.route_box.setVisible(bool(scope.SHOW_ROUTE_BY))
        pane = QWidget(self)
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.route_box)
        lay.addWidget(self.decide_panel, 1)
        return pane

    def _build_params_row(self) -> QWidget:
        """中欄的下半：**參數在左、這張卡的儀表在右，同一個框裡**（U8）。

        為什麼它們必須挨著
        ------------------
        調參數的迴圈是「改一個數字 → 看那個數字怎麼變」。儀表以前住在右欄
        下半，中間隔著整張影像 —— 每改一格眼睛就要橫跨半個螢幕來回一趟，而那
        件事在一個 1366×768 的螢幕上尤其貴。

        **卡名與階段色只出現一次**：ParamForm 自己的標頭就是那一次，儀表這一
        邊只留 Card / Features 兩顆切換鈕。兩邊各畫一次的話，同一張卡的名字在
        同一個框裡出現兩遍，而使用者要花一秒鐘確認那是不是兩張卡。

        影像**不搬**：它是另一種迴圈（改參數 → 看圖），而且它要的是高度 ——
        把它擠進這一列只會讓兩件事都變小。
        """
        row = HairlineSplitter(Qt.Horizontal, self)
        row.addWidget(self.stack)
        # F100 v3：儀表搬到**右欄影像下面**（使用者：「最一開始的排版最好，儀表
        # 換到影像下方」）。設定區於是拿到整個中欄的寬度，儀表拿到右欄的寬度
        # ——兩個要寬的東西各一整欄，只有影像付出高度。「儀表挨著參數」（U8）
        # 沒有破：中欄下半與右欄下半左右相鄰，同一條視線。
        self.workbench = row
        # 參數那一邊寬一點：它裝的是一排排可以拖的滑桿（F7-8），而儀表是
        # 讀的東西。3:2 是量出來的 —— 再窄一點，`Borrow range from` 那種
        # 兩行的 label 會開始折行。
        row.setStretchFactor(0, 3)
        row.setStretchFactor(1, 2)
        row.setCollapsible(0, False)
        self.params_row = row
        return row

    def _build_preview_pane(self) -> QWidget:
        pane = QWidget(self)
        lay = QVBoxLayout(pane)
        # 間距走 8px 節奏（F8-UI）：這一欄以前是 2/4/6px 各處自己挑，
        # 排在一起就是「差一點對齊」—— 比完全沒對齊更讓人覺得亂。
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        # 這一欄叫什麼（F13-4）—— 四個直欄以前只靠 splitter 隔開，
        # 沒有任何東西說得出「這一欄是什麼」。它自己不帶左右內距，
        # 靠這一欄的 8px 邊界對齊（那個節奏是 F8-UI 定的，不要為了一個
        # 地標破壞它）。
        lay.addWidget(column_header("Preview", pane))

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
        # F100：這一列住在工作台的一格裡（1366 上約 420 px），150 的保留寬度
        # 是那一格硬最小寬度的最大來源之一。讀數最長是「x 1234, y 1234 · 255」，
        # 100 夠；不夠的那一瞬間它會被擠成省略號，而不是把整個視窗撐寬。
        self.cursor_label.setMinimumWidth(100)
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
        # F100：影像現在是工作台的一格（1366 上約 480 px 寬、380 px 高），而這
        # 一塊空白狀態是四列「鈕 ＋ 一句話」—— 塞不下的時候要**捲**，不是疊在
        # 一起（第一版就是疊的）。用 `fit_screen.scrolled` 在**建構時**包，
        # 事後搬是 segfault（`CLAUDE.md` §4）。捲軸還有第二個好處：
        # `QStackedWidget` 的最小寬度是它每一頁的最大值——**藏起來的那一頁也
        # 算**——而以前這一頁的 468 px 就是右欄硬最小寬度的來源。
        self.empty_state_host, self.empty_state = fit_screen.scrolled(pane)
        estack = QVBoxLayout(self.empty_state)
        estack.addStretch(1)
        title = QLabel("No data loaded yet", self.empty_state)
        title.setObjectName("paramTitle")
        title.setAlignment(Qt.AlignCenter)
        estack.addWidget(title)
        # 這句話要跟旁邊實際看得到的鈕一致 —— 範例資料那顆收起來的時候還講
        # 「or try the tool with generated sample data」，使用者會去找一顆不在
        # 畫面上的鈕。
        why = QLabel("d4t reads four kinds of data. Pick the one you have."
                     if not scope.SHOW_SAMPLE_DATA else
                     "d4t reads four kinds of data. Pick the one you have, "
                     "or try the tool with generated sample data first.",
                     self.empty_state)
        why.setObjectName("paramHint")
        why.setAlignment(Qt.AlignCenter)
        why.setWordWrap(True)
        # 留一個名字：這句話必須跟旁邊看得到的鈕一致，而那是測得出來的
        # （`test_nothing_on_screen_points_at_a_button_that_is_not_there`）。
        self.empty_state_hint = why
        estack.addWidget(why)

        # **每一種 source 一列，而那幾列是從 `scope.INPUT_SOURCES` 長出來的**
        # （F11 Input-5，使用者：「各種 image source 資料流是否改成個別入口比較
        # 好（但同時 UI 一開始進去的地方顯示也要改）」）。
        #
        # 以前這裡只有一顆 ``Open KLARF…``，而工具列上有三顆 —— 於是帶著一個
        # 資料夾的圖片、或一個多頁 TIFF 進來的人，在**整個畫面最大的那一塊**上
        # 看到的是「Open a KLARF to see your patches here」。他要嘛以為 d4t
        # 讀不了他的東西，要嘛得自己去工具列上一顆一顆讀過去。
        #
        # 一列一句話，說的是**這條路吃什麼樣的檔案**，不是它會做什麼 ——
        # 使用者站在這個畫面前面時，手上已經有檔案了，他要回答的問題是
        # 「我這一堆算哪一種」。
        self.empty_source_buttons: Dict[str, QPushButton] = {}
        rows = QVBoxLayout()
        rows.setSpacing(6)
        for i, src in enumerate(scope.INPUT_SOURCES):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addStretch(1)
            b = QPushButton(src.title, self.empty_state)
            if i == 0:
                b.setObjectName("primary")     # 最常見的那一條是主要動作
            b.setMinimumWidth(140)
            b.clicked.connect(
                getattr(self, "_on_open_%s" % src.key))
            self.empty_source_buttons[src.key] = b
            row.addWidget(b)
            what = QLabel(src.what if src.has_klarf else
                          "%s No KLARF, so no write-back." % src.what,
                          self.empty_state)
            what.setObjectName("paramHint")
            what.setWordWrap(True)
            what.setMinimumWidth(200)
            row.addWidget(what, 2)
            row.addStretch(1)
            rows.addLayout(row)
        estack.addLayout(rows)

        # 第一顆保留原本的名字：既有測試與 ``_build_shortcuts``（Ctrl+O）
        # 都指得到它，而它做的事一個字都沒變。
        self.btn_empty_open = self.empty_source_buttons[
            scope.INPUT_SOURCES[0].key]

        # 附加檔不是第五條路，所以它不是一顆鈕，是**一句說明它什麼時候才出現**
        # 的話。這正是使用者問的那一句「Load layout labels 要怎麼 load，好像
        # 沒有 load 的地方」—— 卡片在卡片庫裡看得到，而它的入口要等 lot 載進來
        # 才亮，於是這個畫面上必須說得出那個順序。
        att_bits = ["%s — %s %s" % (a.title, a.what, a.needs)
                    for a in scope.ATTACHMENTS]
        self.empty_state_attachments = QLabel(
            "  ·  ".join(att_bits), self.empty_state)
        self.empty_state_attachments.setObjectName("paramHint")
        self.empty_state_attachments.setAlignment(Qt.AlignCenter)
        self.empty_state_attachments.setWordWrap(True)
        self.empty_state_attachments.setVisible(bool(scope.ATTACHMENTS))
        estack.addSpacing(6)
        estack.addWidget(self.empty_state_attachments)

        brow = QHBoxLayout()
        brow.addStretch(1)
        self.btn_empty_sample = QPushButton("Try it with sample data",
                                            self.empty_state)
        self.btn_empty_sample.setProperty("variant", "secondary")
        # ⚠ **這顆跟 `btn_examples` 看的不是同一個旗標了**（F91 X4）：
        # demo 產得出資料，但**不載 pipeline** —— 按完看到的是一批資料配一張
        # 空白畫布。範本庫那個理由修好了，這個沒有。
        self.btn_empty_sample.setVisible(bool(scope.SHOW_SAMPLE_DATA))
        brow.addWidget(self.btn_empty_sample)
        brow.addStretch(1)
        estack.addSpacing(8)
        estack.addLayout(brow)
        estack.addStretch(1)

        self.image_stack = QStackedWidget(pane)
        self.image_stack.addWidget(self.empty_state_host)  # index 0
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
        # 辦法判讀（`glv_snr 11.170` 是大還是小？），而且使用者在問的
        # 問題**每張卡都不一樣**。特徵表仍然留著，用切換列回去。
        # F76 刀 4：這一塊從 `widgets.FeatureTable`（一條平的清單）換成
        # `feature_panel.FeaturePanel`（卡 › 區域 分段、四胞胎橫過來）。
        # 名字仍叫 `feature_panel`，取用口跟舊的那張表同名同義。
        self.feature_panel = FeaturePanel(self)
        self.feature_panel.setMinimumHeight(120)

        self.inspector_host = QWidget(self)
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

        self.bottom_stack = QStackedWidget(self)
        self.bottom_stack.addWidget(self.inspector_host)      # index 0
        self.bottom_stack.addWidget(self.feature_panel)       # index 1

        # ---- 儀表搬到參數旁邊（U8，2026-09-08）--------------------------
        #
        # 這一塊（Card 儀表 / Features）以前住在**右欄下半**，而參數住在
        # 中欄下半 —— 中間隔著整張影像。調參數的迴圈是「改一個數字 → 看那個
        # 數字怎麼變」，而那兩件事每一次都要橫跨半個螢幕，眼睛來回一趟。
        #
        # 現在它跟參數同欄同框（見 `_build_params_row`）。**影像維持獨立**：
        # 它是另一種迴圈（改參數 → 看圖），而且它需要的是高度。
        self.gauge_pane = QWidget(self)
        glay = QVBoxLayout(self.gauge_pane)
        glay.setContentsMargins(0, 0, 0, 0)
        glay.setSpacing(2)
        tabs = QHBoxLayout()
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(4)
        self.btn_tab_card = small_button("Card", parent=self.gauge_pane,
                                         shape="wide")
        self.btn_tab_features = small_button("Features", parent=self.gauge_pane,
                                             shape="wide")
        for i, b in enumerate((self.btn_tab_card, self.btn_tab_features)):
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, k=i: self.show_bottom_page(k))
            tabs.addWidget(b)
        # 選到判定樹的一步時，這一塊裝的還是**上一張卡**的儀表（F99 P1-7）——
        # 以前畫面上沒有任何東西講這件事，左邊寫著 Decision、右邊寫著 GLV。
        # 現在它淡掉，而且這一句說出它是誰的。
        self.gauge_note = QLabel("", self.gauge_pane)
        self.gauge_note.setObjectName("paramHint")
        tabs.addWidget(self.gauge_note, 1)
        glay.addLayout(tabs)
        glay.addWidget(self.bottom_stack, 1)

        # ---- 判定那一塊（F76 刀 5，2026-09-02）----------------------------
        #
        # **沒有判定就不畫它。** 使用者 2026-09-02：「大部分人應該建立
        # Pipeline 時 ADC 不會放到第一個」—— 而在那段時間裡，這一塊永遠是一個
        # 寫著 `—` 的 chip 加一片空白。它不是壞的，它是**什麼都沒說**，而那塊
        # 面積正好是量測卡最需要的地方（同 F7-15「空白狀態要說得出下一步」、
        # 以及 scope.SHOW_SAMPLE_DATA 那條「按了撞牆的鈕比沒有那顆鈕更糟」
        # 的鏡像 —— 這裡是「說不出話的那一格比沒有那一格更佔位」）。
        # Verdict 是一條**常駐的結論列**（F100）：橫跨在工作台下面，不在任何
        # splitter 裡，所以 Build 模式收掉工作台之後它還在。
        self.verdict_strip = QWidget(self)
        strip = QVBoxLayout(self.verdict_strip)
        strip.setContentsMargins(8, 4, 8, 4)
        strip.setSpacing(0)
        self.verdict_live = QWidget(self.verdict_strip)
        # **兩行，不是一行**（F100 v2）：這一塊住在右欄（1366 上約 460 px），
        # 一行排「Verdict ＋ 膠囊 ＋ score ＋ 那句為什麼 ＋ 路徑」的最小寬度是
        # 五百多 px，整欄被它撐開。膠囊（類別名）跟 Verdict 一行、數字與說明
        # 第二行、路徑第三行（會換行）。
        vcol = QVBoxLayout(self.verdict_live)
        vcol.setContentsMargins(0, 0, 0, 0)
        vcol.setSpacing(2)
        vrow = QHBoxLayout()
        vrow.setContentsMargins(0, 0, 0, 0)
        vrow.setSpacing(8)
        self.verdict = VerdictChip(self.verdict_live)
        vrow.addWidget(QLabel("Verdict", self.verdict_live))
        vrow.addWidget(self.verdict)
        vrow.addStretch(1)
        vcol.addLayout(vrow)
        vrow2 = QHBoxLayout()
        vrow2.setContentsMargins(0, 0, 0, 0)
        vrow2.setSpacing(8)
        # **score 那個數字跟 bin 一起常駐**（F76 刀 4 之後）。以前它是特徵表
        # 最後一列、粗體、永遠不被收合走的那一格 —— 理由是「它是這張表的
        # 結論」。新面板把它歸進 `Score / Bin` 那一段，而那一段收得起來，
        # 所以那條不變量搬到這裡：結論跟判定在同一塊，永遠看得到。
        self.verdict_score = QLabel("", self.verdict_live)
        self.verdict_score.setStyleSheet("font-weight:700;")
        vrow2.addWidget(self.verdict_score)
        # **膠囊寫著「—」的時候要說為什麼**（F99 P1-2）。預覽停在選到的那張卡
        # 是對的（F7 定調），但那一刻 Verdict 從「more than one box is off」
        # 變成一個破折號，而畫面上沒有任何東西講它為什麼不見 —— 看起來像剛剛
        # 還有判定、現在壞了。這一句住在膠囊旁邊，不住在狀態列。
        self.verdict_note = QLabel("", self.verdict_live)
        self.verdict_note.setObjectName("paramHint")
        self.verdict_note.setWordWrap(True)
        vrow2.addWidget(self.verdict_note, 1)
        vcol.addLayout(vrow2)
        # **那一行點得下去**（U11）：走過的路旁邊沒有別的入口，而回溯以前只有
        # 「跑一整批 → Results → 點 score/bin」那一條路 —— 使用者手上明明就有
        # 這一顆的每一個數字。做成連結而不是另加一顆鈕：底線本來就是
        # 「這個字可以點」的意思。
        self.decide_path = QLabel("", self.verdict_live)
        self.decide_path.setObjectName("paramHint")
        self.decide_path.setWordWrap(True)      # 右欄裝不下一整條路徑
        self.decide_path.setTextFormat(Qt.RichText)
        self.decide_path.setOpenExternalLinks(False)
        self.decide_path.linkActivated.connect(
            lambda _href: self.toggle_preview_why())
        vcol.addWidget(self.decide_path)
        strip.addWidget(self.verdict_live)

        # 這一顆為什麼判成這樣（U11）—— **跟 Results 那一份是同一個 widget**
        # （`why_panel.WhyPanel`），只是住在單顆預覽這一欄。跑整批之前它就答得
        # 出來，因為 `verdict_trace` 吃的是特徵、不是一批結果。
        #
        # ⚠ 高度有上限：它是回答一個問題的東西，不是這一欄的主角 ——
        # 把影像擠掉的話，使用者為了讀它得先關掉它。
        self.why_preview = WhyPanel(pane)
        self.why_preview.setMaximumHeight(220)
        self.why_preview.hide()
        self.why_preview.item_activated.connect(
            lambda name: self._on_why_item(self.why_preview.defect_id(),
                                           str(name)))
        lay.addWidget(self.why_preview)
        # Verdict 列住在影像下面（F100 v2）：這一顆判成什麼，跟這一顆的圖挨著。
        lay.addWidget(self.verdict_strip)

        # 還沒有判定的時候換成**一句可以照做的話 ＋ 那顆鈕**（推廣鐵則：
        # 講得出下一步，而那一步就在旁邊）。
        self.verdict_empty = QWidget(self.verdict_strip)
        erow = QHBoxLayout(self.verdict_empty)
        erow.setContentsMargins(0, 0, 0, 0)
        erow.setSpacing(8)
        hint = QLabel("No decision yet — these numbers are measured, but "
                      "nothing is drawing a conclusion from them.",
                      self.verdict_empty)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        erow.addWidget(hint, 1)
        self.btn_add_decision = QPushButton("Add a decision…",
                                            self.verdict_empty)
        self.btn_add_decision.setProperty("variant", "secondary")
        self.btn_add_decision.clicked.connect(self.show_score_page)
        erow.addWidget(self.btn_add_decision)
        strip.addWidget(self.verdict_empty)
        self._sync_verdict_block()

        return pane

    def _sync_verdict_block(self) -> None:
        """有判定才畫 Verdict 那一塊，沒有就畫「怎麼加一個」（F76 刀 5）。

        判準用 model（**recipe 有沒有判定**），不用「這一顆有沒有 bin」——
        後者在還沒預覽、或這一顆量不出來的時候也是空的，而那兩件事的下一步
        完全不同（一個是「去加一棵樹」，另一個是「先跑一次」）。
        """
        decide = getattr(self.model, "decide", None)
        has = bool(
            (decide is not None
             and (getattr(decide, "tree", None) is not None
                  or list(getattr(decide, "rules", ()) or [])))
            or str(getattr(getattr(self.model, "score", None), "expr", "")
                   or "").strip())
        if getattr(self, "verdict_live", None) is None:
            return
        self.verdict_live.setVisible(has)
        self.verdict_empty.setVisible(not has)

    def has_decision(self) -> bool:
        """畫面上那一塊現在是 Verdict 還是「加一個判定」（測試讀得到）。"""
        return bool(getattr(self, "verdict_live", None) is not None
                    and self.verdict_live.isVisibleTo(self))

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
        view.add_menu_requested.connect(self._on_add_menu)
        view.link_dropped.connect(self._on_link_dropped)
        view.node_toggled.connect(self._on_node_toggled)
        view.move_requested.connect(self._on_move_requested)
        view.remove_requested.connect(self._on_remove_requested)
        view.score_clicked.connect(self.show_score_page)
        # 判定區的入口小卡（F24 ②）：點了＝跳到判定的編輯（同 score 那條路）。
        view.decision_clicked.connect(self.show_score_page)
        # 分流徽章（F25-B）：點了去編 route_by（它就在判定欄的最上面）。
        view.prefilter_clicked.connect(self.show_score_page)
        view.decision_remove_requested.connect(self.remove_decision)
        # 判定樹的菱形／托盤（F24 ③）：右欄變成那一步／那一類的編輯面板。
        view.tree_step_clicked.connect(self._on_tree_step_clicked)
        view.tree_leaf_clicked.connect(self._on_tree_step_clicked)
        view.edge_added.connect(self._on_edge_added)
        view.edge_removed.connect(self._on_edge_removed)
        # zoom bar 上那顆鈕以前開第二個視窗，現在**切換版面**（U5）——
        # 它問的一直都是「讓我看全貌」，而那件事不需要第二個視窗。
        #
        # 切換而不是單向切到 Build：不然使用者按了之後沒有路回來，而那顆鈕
        # 就在他眼前（Ctrl+B 是給記得的人用的，不是唯一的路）。
        view.popout_requested.connect(self.toggle_layout_mode)

    def _wire_widgets(self) -> None:
        self.library.add_requested.connect(self._on_add_requested)

        self._wire_canvas(self.pipeline)

        self.param_form.param_edited.connect(self._on_param_edited)

        # 判定段的每一格直接寫 model（`DecidePanel` 的模組說明）——
        # 這裡不再轉手。

        self.btn_prev.clicked.connect(lambda: self.step_defect(-1))
        self.btn_next.clicked.connect(lambda: self.step_defect(+1))
        self.defect_combo.currentIndexChanged.connect(self._on_defect_combo)
        self.btn_region_check.clicked.connect(lambda: self.open_region_check())
        # ``btn_empty_open`` 在 ``_build_body`` 建它的時候就接好了（那一列是
        # 從 ``scope.INPUT_SOURCES`` 長出來的，接線跟著一起長）——
        # 在這裡再接一次會變成按一下開兩個檔案對話框。
        self.btn_empty_sample.clicked.connect(self._on_demo_requested)
        self.param_form.action_requested.connect(self._on_param_action)
        self.param_form.source_requested.connect(self._on_source_requested)
        self.param_form.intent_chosen.connect(self._on_intent_chosen)
        # 設定區的插槽（F68）—— 走的是跟畫布拉線**完全同一條路**。
        self.param_form.wire_requested.connect(self._on_slot_wire)
        self.param_form.wire_show_requested.connect(self._on_slot_show)
        self.stream_combo.currentTextChanged.connect(self._on_stream_changed)
        self.stream_combo_b.currentTextChanged.connect(self._on_stream_b_changed)
        self.compare_check.toggled.connect(self.set_compare)

        self.image_view.cursor_info.connect(self._on_cursor_info)
        self.image_view_b.cursor_info.connect(self._on_cursor_info)
        self.image_view.view_changed.connect(
            lambda s, o: self._link_views(self.image_view, self.image_view_b, s, o))
        self.image_view_b.view_changed.connect(
            lambda s, o: self._link_views(self.image_view_b, self.image_view, s, o))

        self.results.shown_feature_changed.connect(self._on_spread_feature_changed)
        self.histogram.threshold_changed.connect(self._on_threshold_changed)
        self.histogram.threshold_committed.connect(self._on_threshold_committed)
        self.histogram.bar_clicked.connect(self._on_bar_clicked)

        self.gallery.thumbs_requested.connect(self._on_thumbs_requested)
        self.gallery.defect_activated.connect(self._on_defect_activated)
        # 表格上雙擊一列跟縮圖上雙擊一張是同一件事（R7）—— 同一支處理常式。
        self.results.table.defect_activated.connect(self._on_defect_activated)
        # 單擊（或方向鍵）一顆 → 主畫面帶過去，但**不搶焦點**（2026-09-09）。
        self.results.defect_selected.connect(self._on_defect_selected)
        self.gallery.selection_changed.connect(self._on_gallery_selection)
        # 回溯（PR-3）：點 score/bin/class → 算 trace 開面板；點面板上一項 →
        # 跳到產出它的卡（有區域就把那一塊亮起來）。
        self.results.trace_requested.connect(self._on_trace_requested)
        self.results.truth_marked.connect(self._on_truth_marked)
        self.results.why_item_activated.connect(self._on_why_item)

    def _wire_workers(self) -> None:
        self.dataset_worker.loaded.connect(self._on_dataset_loaded)
        self.dataset_worker.failed.connect(
            lambda msg: (self._progress_done(),
                         self._status("Could not load dataset: %s" % msg, "error")))

        self.pair_worker.loaded.connect(self._on_pair_source_loaded)
        self.pair_worker.failed.connect(self._on_pair_source_failed)

        self.preview_worker.ready.connect(self._on_async_preview_ready)
        self.preview_worker.busy.connect(self._on_preview_busy)
        self.region_check_worker.ready.connect(self._on_region_ready)
        self.region_check_worker.failed.connect(
            lambda msg: self._status("Region check failed: %s" % msg, "error"))
        self.preview_worker.failed.connect(
            lambda msg: self._status("Preview failed: %s" % msg, "error"))

        self.trial_worker.progress.connect(self._on_trial_progress)
        self.trial_worker.done.connect(self._on_trial_done_async)
        self.output_worker.done.connect(self._on_outputs_done)
        self.output_worker.failed.connect(self._on_outputs_failed)
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
        bar.showMessage(strings.tr(str(msg)))
        # **下一句話一定把上一句的「下一步」收起來**（X5／X6 那顆鈕的第一條
        # 規矩）。一顆停在那裡的「復原」按鈕，在使用者做了三件別的事之後按
        # 下去，復原的不是他以為的那一件。收在這裡而不是在每個呼叫端，是因為
        # 「忘了收」這件事這樣就不會發生。
        self.status_action.disarm()
        # 說過的話留得住（U2 後半）—— 下一句就把這一句蓋掉了，而這一句可能
        # 正是唯一講出「那件事沒成功」的地方。
        self.status_history.add(str(msg), level)

    def set_sample_mode(self, mode: str, say: bool = True) -> None:
        """換抽樣方式，**並且把工具列上那個字換掉**（X3）。

        兩件事一定一起做：跑的東西變了而畫面沒變，是這個功能最危險的失敗方式
        —— 使用者會以為他還在看「前 200 顆」，而門檻是在另一批上調的。
        """
        use = str(mode or "")
        if use not in sampling.MODES:
            return
        self.sample_mode = use
        word, why = sampling.describe(use)
        self.lbl_trial_n.setText(word)
        self.lbl_trial_n.setToolTip(why)
        for name, act in (getattr(self, "_sample_actions", None) or {}).items():
            act.setChecked(name == use)
        # 建構的時候不要講話：狀態列那句話是**使用者換了模式**的回應，而開窗
        # 時沒有人換過任何東西（同 `_status` 的那條「不要對沒發生的事說話」）。
        if say:
            self._status("Trial runs now cover: %s — %s"
                         % (word.lower(), why))

    def sample_spec(self) -> Dict[str, Any]:
        """這一次要送給 `run_batch` 的抽樣設定。

        **每次跑都給一個新種子**（`first` 除外，它不用）：使用者按第二次
        「Run trial」的意思是「再抽一批看看」，不是「把剛才那批再跑一次」。
        要重現某一批的話，種子在跑完那句話裡（見 `_sample_line`），也留在
        `sample_note` 上。⚠ **Studio 不寫 runs.db**（只有 CLI 寫），所以那句話
        就是使用者唯一讀得到它的地方 —— 不要把它拿掉。
        """
        if self.sample_mode == "first":
            return {"mode": "first"}
        return {"mode": self.sample_mode, "seed": sampling.new_seed(),
                "column": "CLASSNUMBER"}

    def _sample_line(self) -> str:
        """跑完那句話後面的抽樣註記（`first` 是空的 —— 那是預設，不必說）。

        ⚠ 它回的是**真的發生的那一個 mode**，不是使用者選的那一個：分層的那
        一欄整批是空的時候 `sampling.pick` 會退成 random，而說謊比不說更糟。
        """
        note = dict(self.sample_note or {})
        mode = str(note.get("mode", "") or "")
        if not mode or mode == "first":
            return ""
        word = sampling.describe(mode)[0].lower()
        seed = note.get("seed")
        if seed is None:
            return "  ·  %s sample" % word
        return ("  ·  %s sample, seed %s (run again with this seed to get "
                "the same defects)" % (word, seed))

    def _refresh_results_button(self) -> None:
        """Results 那顆鈕要說出**裡面現在有幾顆**（U21）。

        兩件事一起做，因為它們是同一句話的兩半：

        * **有結果** → 鈕上帶計數（``Results · 200``）。使用者關掉那個視窗之後
          唯一的線索就是這個數字 —— 沒有它，「關掉」跟「丟掉」在畫面上長得
          一模一樣。
        * **沒跑過** → 鈕 disabled，而 tooltip 講**下一步**（推廣鐵則：
          「還沒有結果」對使用者沒有動作可做，「先按 Run trial」才有）。

        ⚠ 計數用的是 `trial_results` 的長度，不是「成功幾顆」—— 那個視窗裡本來
        就列著失敗的顆（鐵則 7：單顆出錯不殺整批，而那幾顆要看得到）。
        """
        n = len(self.trial_results or [])
        # ⚠ **不 disable 它。** 外部檢視清單 U21 寫的是「沒跑過就 disabled」，
        # 而那跟使用者 2026-08-28 自己講的話衝突：「可以改成加一個按鈕獨立
        # 呼叫一個視窗嗎（目前是跑完才會出來）」—— 那顆鈕存在的**唯一理由**
        # 就是「隨時叫得出那個視窗」。disable 掉等於把它變回原本的樣子。
        #
        # U21 真正的抱怨是「鈕上沒有東西說明裡面有沒有結果」，而那件事由
        # 計數與 tooltip 回答，不需要動到它能不能按。
        # （`tests/test_ui_results.py::test_results_has_a_button_of_its_own`
        # 當場抓到這個衝突。）
        # ⚠ **這一支繞過 `_tool_button`，所以它要自己翻**（U14）。翻譯層擺在
        # 共用的那幾支換到的是「大部分地方不用管」，不是「沒有地方要管」——
        # 任何**後來**又改寫 text/tooltip 的地方都要自己包一次。
        # 那不是理論：`tests/test_ui_strings.py` 就是這樣抓到這一格的。
        self.btn_results.setText(
            "%s · %d" % (strings.tr("Results"), n) if n
            else strings.tr("Results"))
        self.btn_results.setToolTip(strings.tr(
            "Open the Results window - score distribution, thumbnails and the "
            "per-defect table (Ctrl+Shift+R)" if n else
            "Open the Results window - it is empty until you run the pipeline "
            "(Run trial)"))

    def _delete_selected_on_canvas(self) -> None:
        """畫布上選著的卡片與線 —— 刪掉。

        真正的動作在 `PipelineCanvas.delete_selected()` 裡（它知道選著什麼），
        這一支只是把快捷鍵表上的那一格接過去 —— 好讓「這個工具有哪些鍵」只有
        一個答案，而**刪除只有一份實作**。
        """
        self.pipeline.delete_selected()

    def _clear_canvas_selection(self) -> None:
        """Esc：放掉手上的東西。"""
        self.pipeline.clear_selection()

    # ---- 複製 / 貼上 / 複製一份（F99 P1-8；內容在 `ui/clipboard.py`）--------
    def copy_cards(self) -> int:
        """把畫布上選著的卡（可以好幾張）記進剪貼簿；回幾張。"""
        ids = [n for n in self.pipeline.selected_ids() if n in self.model.nodes]
        if not ids and self.selected_node in self.model.nodes:
            ids = [self.selected_node]

        def pos_of(nid: str):
            item = self.pipeline.node_item(nid)
            return item.pos().toTuple() if item is not None else None

        self._card_clipboard = clipboard.snapshot(self.model, ids, pos_of)
        n = len(self._card_clipboard)
        if n:
            self._status("Copied %d card%s — Ctrl+V pastes %s next to the "
                         "original, without the lines."
                         % (n, "" if n == 1 else "s", "it" if n == 1 else "them"))
        return n

    def paste_cards(self) -> List[str]:
        """貼上：每一張加在原位右下角一點的地方，**沒有線**；一步復原。"""
        items = list(getattr(self, "_card_clipboard", None) or [])
        if not items:
            self._status("Nothing to paste — select a card and press Ctrl+C first.")
            return []
        made = clipboard.paste(self.model, items, self._status)
        for nid, (x, y) in made:
            # `place_dropped` 把卡**置中**在那個點上（拖放的語意）；剪貼簿記的
            # 是左上角，所以補半張卡。
            self.pipeline.place_dropped(nid, x + NODE_W / 2.0, y + NODE_H / 2.0)
        if made:
            self.select_node(made[-1][0])
            self._status("Pasted %d card%s — wire %s up on the canvas."
                         % (len(made), "" if len(made) == 1 else "s",
                            "it" if len(made) == 1 else "them"))
        return [nid for nid, _p in made]

    def duplicate_cards(self) -> List[str]:
        """Ctrl+D ＝ 複製再貼上，剪貼簿不留東西。"""
        before = list(getattr(self, "_card_clipboard", None) or [])
        if not self.copy_cards():
            return []
        made = self.paste_cards()
        self._card_clipboard = before
        return made

    def _status_next_step(self, msg: str, label: str, callback: Any,
                          level: str = "info", tip: str = "") -> None:
        """一句話 ＋ 它旁邊那顆「接下來能做什麼」的鈕。

        順序有意義：**先講話再掛鈕** —— `_status` 自己會把上一顆收掉，反過來
        寫的話新掛的那一顆會被它自己的訊息收走。
        """
        self._status(msg, level)
        self.status_action.arm(label, callback, tip)

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
        # 判定樹面板（F24 ③）：結構變了要跟上（打字不重建 —— 它自己的
        # typing guard 擋著）。
        self.tree_pane.refresh()
        # 分流（F23 期2）：route 清單與編輯區塊跟著 model 走。
        self._refresh_route_switcher()
        self.route_box.refresh()
        self._sync_threshold_line()
        self._update_action_states()
        self._refresh_library_badges()
        self._refresh_region_button()
        self._schedule_preview()

    def _refresh_all(self) -> None:
        self._refresh_pipeline()
        self._sync_score_widgets()
        self._sync_verdict_block()      # F76 刀 5：有判定才畫 Verdict 那一塊
        self._refresh_feature_combo()
        self._sync_threshold_line()
        self._update_action_states()
        self._refresh_library_badges()

    def _refresh_library_badges(self) -> None:
        """把「pipeline 目前產出了哪些影像流」餵給卡片庫（F7-3）。

        卡片庫據此把前置條件未滿足的卡標成 ``needs diff`` 並調淡 ——
        **但仍然可以加**。卡片庫的順序不是執行順序，使用者可能先放卡再補上游。
        """
        try:
            streams = list(self.model.available_streams())
        except Exception:  # 顯示用，壞了就不標
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
            run_why or "Run all %d defects, not just the first %d. Nothing "
                       "is written - press “Write outputs” in Results when "
                       "the numbers look right."
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
        # 存檔（2026-08-26）：空的 pipeline 沒東西可存，而那要**看得出來**
        # 是「還沒有東西」不是「壞掉了」。標題列的星號跟它同一件事的兩個講法。
        self.btn_save_recipe.setEnabled(has_steps)
        if not has_steps:
            save_tip = "The pipeline is empty — nothing to save yet."
        elif self.recipe_path:
            # **講出它會覆寫哪一個檔案。** `Ctrl+S` 不再問路徑（那是慣例），
            # 所以「存回哪裡」這件事要在按下去**之前**看得到；否則第一次按
            # 的人只能事後從狀態列知道自己蓋掉了什麼。
            save_tip = ("Save back to “%s”"
                        % os.path.basename(self.recipe_path))
        else:
            save_tip = "Save this pipeline as a recipe JSON"
        self._set_tip(self.btn_save_recipe, save_tip)
        self._refresh_title()


    def _refresh_title(self) -> None:
        """標題列 = ``d4t Studio — <recipe 名> *``。

        那顆星號是**「還沒存」的唯一一個常駐訊號**（每個編輯器都是這個
        慣例，使用者不必重學）。以前不需要它 —— 沒有存檔功能的時候「還沒存」
        是恆真的，講了等於沒講。存檔回來之後它才開始有兩種狀態。
        """
        name = str(getattr(self.model, "recipe_id", "") or "").strip()
        title = "d4t Studio" if not name else "d4t Studio — %s" % name
        if self.model.dirty and self.model.node_order:
            title += " *"
        if self.windowTitle() != title:
            self.setWindowTitle(title)

    def _card_summary_parts(self, node: Any, reads, writes, regions_out,
                            region_inputs) -> List[str]:
        """畫布上第三行的各項。**入口卡的第一項是它讀的那份資料**（F14-1）。

        以前那張卡上完全看不出讀的是哪個檔案 —— 檔案在工具列上選，而畫布上
        那張 Load 卡只說得出「load · test ref」。入口搬到卡片上之後，
        畫布也要跟著說得出來，否則搬家只搬了一半。
        """
        parts = self._node_summary_parts(
            node, shown=(list(reads) + list(writes) + list(regions_out)
                         + [d["stream"] for d in region_inputs]))
        try:
            is_source = get_step(node.step).is_source()
        except KeyError:                       # pragma: no cover
            is_source = False
        # 配對卡也是 `is_source`，但它讀的**不是**目前這份 lot —— 印 main 的
        # 檔名在它上面就是畫布說謊（F15）。它要印的是掛在它那個代號上的第二份。
        if node.step in self._PAIR_CARDS:
            name = self._pair_source_name(node)
            if name:
                parts.insert(0, name)
            return parts
        if is_source and node.step not in self._ATTACHMENT_CARDS:
            name = str(getattr(self, "dataset_name", "") or "")
            if name:
                parts.insert(0, name)
        return parts

    def _pair_source_name(self, node: Any) -> str:
        """配對卡掛的那第二份 lot 的檔名（還沒掛就回空字串）。"""
        sid = str(node.params.get("source", "") or "").strip()
        src = (getattr(self.dataset, "sources", None) or {}).get(sid) \
            if self.dataset is not None else None
        return str(getattr(src, "_d4t_name", "") or "") if src is not None else ""

    def _node_summary_parts(self, node: Any,
                            shown: Optional[Sequence[str]] = None) -> List[str]:
        """節點第三行的各項（`_node_summary` 的 list 版；畫布用這個）。

        分開一個 list 版是為了讓**畫的人決定塞得下幾項**：字串版在 Studio 這邊
        就把項數砍成 3，而節點只有 ~150px 寬，於是第三項被切在字中間
        （使用者回報的「normalize 的節點文字會被吃掉」）。見
        `canvas._draw_parts`。
        """
        # 畫在卡片上的那一份用 `ParamSpec.label`（F99 P1-4）：``roi_out=on_pattern``
        # 是 recipe 的鍵，對製程工程師不是一句話；``Call the regions=on_pattern``
        # 才是。字串版（`info["summary"]`）**維持鍵名**——狀態列與測試讀的是它，
        # 而測試要問的是「這張卡被設成什麼」，鍵名才是穩定的那一個。
        text = self._node_summary(node, shown=shown, use_labels=True)
        return [s for s in text.split(SUMMARY_SEP) if s]

    def _node_summary(self, node: Any, shown: Optional[Sequence[str]] = None,
                      use_labels: bool = False) -> str:
        """「非預設」參數渲染成 ``k=v`` 串起來。

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
        shown_as = {p.name: (str(getattr(p, "label", "") or "") or p.name)
                    for p in step_cls.params} if use_labels else {}
        # 有些參數的值不是給人看的（模板是一整張影像的內容，六千多個字元）。
        # 直接串進摘要，那張卡的第三行就變成一段 base64 —— 元件會把它切掉，
        # 於是看到的是「template=gc1:iVBORw0KGg…」，既沒有資訊也擠掉了真正
        # 有用的參數。這種參數只講「有沒有設」。
        opaque = {p.name: p.type for p in step_cls.params if p.type == "template"}
        # F12：區域也算 —— 它的值現在印在**輸入埠的標籤**上（`roi=epi` 那一項
        # 跟埠上的 `epi` 是同一件事），第三行再講一次只是把位子佔掉。
        stream_params = {p.name for p in step_cls.params
                         if p.type in ("image_key", "image_keys",
                                       "region_key", "region_keys")}
        seen = {str(s) for s in (shown or [])}
        parts: List[str] = []
        for name, value in node.params.items():
            if name in defaults and defaults[name] == value:
                continue
            # **空的值不要印**（F11 Enhance-4）。剛加進來的卡每一格輸入都是空的
            # （F10：`cleared_inputs`），而空字串跟卡片的預設值不相等 —— 於是
            # 節點上長出 ``streams=``，一個沒有任何資訊的欄位，還把真正有用的那
            # 一項擠掉。「還沒接線」這件事畫布上已經講了（沒有線＋警示標記）。
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if name in stream_params and seen:
                # 這個參數挑的流副標已經列出來了 → 不要再講一次。
                picked = {v.strip() for v in str(value).split(",") if v.strip()}
                if picked and picked <= seen:
                    continue
            word = shown_as.get(name, name)
            if name in opaque:
                parts.append("%s: set" % word)
            else:
                parts.append("%s=%s" % (word, _fmt(value)))
            # 上限放寬到 4：塞得下幾項由**畫的人**決定（`canvas._draw_parts`），
            # 而它會把放不下的收成 `+N`。這裡的上限只是別讓一張 19 個參數的卡
            # （`roi_cross`）產出一串沒有人讀得完的字。
            if len(parts) >= 4:
                break
        return SUMMARY_SEP.join(parts)

    def _on_problem_activated(self, node_id: str) -> None:
        """Problems 清單上點了一項 → 選中那張卡並捲到它（U2）。

        指不到任何一張卡的那幾條（「這份 recipe 沒有這個 route」那種）
        **不是沉默** —— 那一句話直接進狀態列，因為它就是使用者要看的答案。
        """
        nid = str(node_id or "")
        if nid and self.select_node(nid):
            return
        row = next((r for r in self.problems.rows() if not r["node_id"]), None)
        if row:
            self._status(row["detail"] or row["title"],
                         "error" if row["level"] == "error" else "info")

    def _node_problems(self, issues: Optional[Sequence[Any]] = None
                       ) -> Dict[str, Any]:
        """每個節點最嚴重的一則 lint 發現（畫布上的警示標記用）。

        lint 本來就知道「這張卡缺模板」「這張卡指到不存在的區域」—— 但那個知識
        以前只在按下 Run trial 的那一刻出現一次。卡片在畫布上看起來永遠是好的，
        於是使用者要跑過才知道，而跑一次是好幾分鐘。

        ``issues`` 給了就用那一份，不再跑一次 lint（U2）：Problems 列與畫布
        的警示點**必須是同一份東西**，而 `_refresh_pipeline` 那一支就是那個
        「只跑一次」的地方。不給＝自己跑（既有的呼叫者與測試照舊）。
        """
        out: Dict[str, Any] = {}
        if issues is None:
            try:
                issues = self.model.validate()
            except Exception:  # 顯示用，壞了就沒標記
                return out
        rank = {"error": 0, "warning": 1, "info": 2}
        for issue in issues:
            nid = getattr(issue, "node_id", None)
            if not nid:
                continue
            prev = out.get(nid)
            # error > warning > info；同級的取先出現的那則。info 也進表
            # （tooltip 要看得到），只是畫布不為它畫點（`canvas.badge_paints`）。
            if prev is not None and (rank.get(str(issue.level), 1)
                                     >= rank.get(prev[1], 1)):
                continue
            out[nid] = (str(issue.detail or issue.title), str(issue.level))
        return out

    def _refresh_pipeline(self) -> None:
        # ⚠ **lint 只跑一次**，畫布的警示點與 Problems 列吃同一份（U2）。
        # 各算一次的那天，畫面上會有一張卡是紅的而清單說沒有問題。
        try:
            issues: Sequence[Any] = self.model.validate()
        except Exception:  # 顯示用
            issues = []
        self.problems.set_issues(issues)
        problems = self._node_problems(issues)
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
            except Exception:  # 顯示用，壞了就空著
                writes = []
            try:
                reads = list(step_cls.resolve_reads(node.params))
            except Exception:
                reads = []
            try:
                # Region 卡不寫影像流，它定義的是具名區域 —— 副標要講得出
                # 「ref → cell」，否則那張卡在畫布上看起來什麼都不產出。
                regions_made = list(step_cls.resolve_regions_out(node.params))
            except Exception:
                regions_made = []
            # 右邊的**區域埠**還含「原樣送出的」（F12 第二輪，使用者：「區域線
            # 應該也要 follow 圖像線一樣，前進後出」）—— 跟影像的 `outs` 同一條
            # 規則。副標仍然只印 `regions_made`（真的產出的那些）。
            regions_out = list(self.model.region_outputs(nid))
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
                writes, outs, regions_out, regions_made = [], [], [], []
            # 每一格輸入在畫布上都是一顆埠（F10）。``show_when`` 藏起來的不算
            # —— 那一格現在不成立，畫一顆接不上任何意義的埠只會讓人問「這是
            # 什麼」。標籤用 ParamSpec 的 label（`First stream`），不是參數名。
            inputs = []
            region_inputs = []
            if step_cls is not None:
                for spec in step_cls.input_specs():
                    if not spec.visible_for(node.params):
                        continue
                    inputs.append({
                        "name": spec.name,
                        "label": spec.label or spec.name,
                        "stream": str(node.params.get(spec.name, "") or ""),
                        # 這顆埠是「要量的」還是「拿來比的」（F68）——
                        # 畫布靠它把兩顆同型別的埠分開，見 `canvas._draw_port`。
                        "role": spec.role,
                    })
                # 區域也是輸入埠（F12）—— 一張卡用到的每一個具名區域，畫布上
                # 都要有一條線指到定義它的那張卡。以前這件事只在參數裡，於是
                # 拿掉上游那張 Region 卡，量測卡不會報錯，它會**安靜地改量整張
                # 圖**，而畫面上兩張卡看起來本來就互不相干。
                for spec in step_cls.region_input_specs():
                    if not spec.visible_for(node.params):
                        continue
                    region_inputs.append({
                        "name": spec.name,
                        "label": spec.label or spec.name,
                        "stream": str(node.params.get(spec.name, "") or ""),
                        "role": spec.role,          # F68（同上）
                    })
            nodes.append({
                "node_id": nid,
                "inputs": inputs,
                "region_inputs": region_inputs,
                "step_key": node.step,
                "label": label,
                "category": category,
                "enabled": bool(node.enabled),
                # 副標那行印的是 reads → writes/regions；摘要不要再講一次
                "summary": self._node_summary(
                    node, shown=(list(reads) + list(writes) + list(regions_out)
                                 + [d["stream"] for d in region_inputs])),
                # 畫布照**寬度**決定塞得下幾項（放不下的收成 `+N`），所以給它
                # list；`summary` 那個字串留著給狀態列與測試讀。
                "summary_parts": self._card_summary_parts(node, reads, writes,
                                                          regions_out,
                                                          region_inputs),
                # 畫布的輸出埠吃這個（含原樣送出的輸入）；副標仍然只印
                # 「這張卡真的產出什麼」，不然每張卡的副標都會變成一長串。
                "writes": outs,
                "produces": writes,
                "reads": reads,
                "regions_out": regions_out,
                "regions_produced": regions_made,
                "group": step_cls.resolve_group() if step_cls else "",
                # **這張卡什麼時候跑**（F50）。以前這件事畫在卡片外面的一個
                # 虛線框上（`ui/output_band.py`）—— 而框的意思是「這幾個是
                # 一組」，真相卻是「跑的時間不一樣」。編碼錯了，於是 Output
                # 卡在畫布上是唯一一種被框起來的卡，而那個框每一個拖曳 frame
                # 重建一次、留下殘影。現在它是卡片自己的一個屬性。
                "scale": step_cls.scale if step_cls else SCALE_DEFECT,
                # **這張卡用名字吃哪些數字**（F50）。Output 那三張的
                # `rank_by` / `size_feature` / `columns` 都是名字，畫布上
                # 因此沒有任何一條線指向它們 —— 淡線就是畫這件事。
                # 兩支都問：會失敗的（`resolve_features_in`）與少了只會退化
                # 的（`optional_features_in`）在畫面上是同一件事「它讀這個」。
                # ⚠ 走 `feature_names_in`（F51），**不是** `optional_features_in`：
                # 後者問的是「少了會不會退化」，而 `score` 永遠不會缺，所以它
                # 被刻意排除 —— 於是「報表照分數排序」那條最常見的線畫不出來。
                # 畫線問的是「設定上寫著哪些名字」，那是另一個問題。
                "feature_reads": (step_cls.feature_names_in(node.params)
                                  if step_cls else []),
                "problem": problems.get(nid, ("", ""))[0],
                "problem_level": problems.get(nid, ("", "error"))[1],
            })
        if self.selected_node not in self.model.nodes:
            self.selected_node = None
        self._sync_params_pane()
        decision = self._decision_info()
        prefilter = self._prefilter_info()
        # 淡線要問「這個數字是誰算的」，而那張表跟判定在不在無關（Output 卡
        # 沒有判定也照樣吃數字）—— 所以它自己送一份，不搭 `decision` 的便車。
        owners = dict(self.model.feature_owners())
        for view in self._canvases():
            view.set_feature_owners(owners)
            # **每一條線都在 `recipe.edges` 裡**（F42 B4）。以前這裡是兩份相加
            # ——影像線來自 `edge_lines()`、區域線從參數推導（`region_lines()`）
            # ——而方案 B 之後區域線也是一條真的 Edge，所以第二份收的是同一批
            # 東西（B2 到 B3 之間它畫的每一條都跟第一份重複）。
            # 一條線就是一條線，它是哪一種由它出發的那顆埠決定。
            view.set_nodes(nodes, list(self.model.edge_lines()))
            # 判定區（F24 ②）：多類別的 recipe，判定樹住在畫布上。
            view.set_decision(decision)
            # 分流徽章（F25-B）：有 route_by 才有 —— 畫布因此講得出
            # 「這一批分兩條路跑」，而不是只有工具列一個下拉。
            view.set_prefilter(prefilter)
            view.set_selected(self.selected_node)
            view.set_score_summary(self._score_summary_text())

    def _score_summary_text(self) -> str:
        """判定段現在在做什麼，一句話。

        三種樣子各講各的：判定樹講「幾個問題」、規則清單講「幾條規則」、
        什麼都沒有就講沒有。（二元門檻那一句 F25 之後不會再出現 ——
        開起來的 recipe 一律是樹。）
        """
        from .tree_scene import display_tree, layout_cells

        d = getattr(self.model, "decide", None)
        if d is None:
            return "no decision yet"
        if getattr(d, "tree", None) is not None:
            steps = sum(1 for c in layout_cells(display_tree(d), d)
                        if c["kind"] == "step")
            return "decision tree · %d question%s" % (steps,
                                                      "" if steps == 1 else "s")
        return "decision · %d rule%s" % (len(d.rules),
                                         "" if len(d.rules) == 1 else "s")

    def _decision_problem(self) -> tuple:
        """判定段的 lint（最嚴重的那一條）→ ``(訊息, 級別)``；沒有就 ``("","")``。

        **這一支存在的理由是一個真的洞**（F50）：`Issue.node_id` 是「哪一張
        卡」，而判定不是一張卡 —— 它的 issue 一律 `node_id=None`，而
        `_node_problems()` 第一件事就是把沒有節點的丟掉。於是同樣是「指到一個
        沒人算得出來的數字」，卡片那邊一改就看得到徽章，判定那邊只在**跑完
        之後**的狀態列尾巴出現一次 —— 而跑一次是好幾分鐘。

        ⚠ **判準是那張表，不是「node_id 是 None」**（`DECISION_ISSUE_CODES`）：
        沒有節點的 lint 裡還有三條講分流、一條講整張圖，掛上來就是讓入口卡
        替別人的問題背鍋。
        """
        from d4t.core.pipeline.recipe import DECISION_ISSUE_CODES

        try:
            issues = self.model.validate()
        except Exception:  # 顯示用
            return ("", "")
        rank = {"error": 0, "warning": 1, "info": 2}
        best = None
        for issue in issues:
            if getattr(issue, "node_id", None):
                continue
            if str(getattr(issue, "code", "")) not in DECISION_ISSUE_CODES:
                continue
            lvl = str(issue.level)
            if best is None or rank.get(lvl, 1) < rank.get(best[1], 1):
                best = (str(issue.detail or issue.title), lvl)
        return best or ("", "")

    def _prefilter_info(self) -> Optional[Dict[str, Any]]:
        """畫布上的分流徽章要畫的東西（F25-B）；沒有 route_by 回 None。

        「現在這一顆走哪一條」跟資料集標籤是**同一支** `resolve_route`
        算的 —— 兩個地方各算一次的話，遲早會有一個說錯。

        ⚠ **`scope.SHOW_ROUTE_BY` 關著的時候一律回 None**（F50）——
        徽章因此不畫，而**引擎那一頭一個位元都沒動**：帶著 `route_by` 的
        recipe 照樣分流、照樣算出一樣的數字。收起來的是入口，不是能力。
        擋在這裡而不是擋在畫布，理由跟 `visible_steps` 一樣：一個地方決定
        「給不給看」，畫布只管畫它收到的東西。
        """
        from .route_badge import route_badge_info

        if not scope.SHOW_ROUTE_BY:
            return None

        current = None
        rb = getattr(self.model, "route_by", None)
        item = self._current_item() if rb is not None else None
        if item is not None and self.dataset is not None:
            from d4t.core.pipeline import resolve_route

            route, value, _how = resolve_route(self.model, item,
                                               str(self.dataset.kind))
            current = (value, route or "(fails)")
        return route_badge_info(self.model, self.trial_results or [], current)

    def _decision_info(self) -> Optional[Dict[str, Any]]:
        """畫布判定區要畫的東西（F24 ②）。

        走二元 score 的 recipe 回 None —— 那條路的判定住在右欄的門檻滑桿。
        流量吃**這一批試跑的結果**：沒跑過就是 None，判定區的形狀在、
        數字誠實地不在（F18 的老規矩）。
        """
        from .tree_scene import decision_info

        info = decision_info(getattr(self.model, "decide", None),
                             list(self.trial_results or []),
                             self.ground_truth)
        if info is not None:
            # 幽靈線（F24 ④）：菱形上的數字 → 產出它的卡。宣告層的答案。
            info["feat_owner"] = self.model.feature_owners()
            # 判定的 lint 掛到入口卡上（F50）—— 見 `_decision_problem`。
            why, level = self._decision_problem()
            info["problem"], info["problem_level"] = why, level
        return info

    def _sync_score_widgets(self) -> None:
        """model 換過（載入、undo、切 route）之後把判定面板重畫一次。

        **打字時不會走到這裡** —— 那一格是直接寫 model 的，而 `DecidePanel`
        自己會跳過「有人正在打字」的重建（見它的 `refresh`）。
        """
        self.decide_panel.refresh()
        self.pipeline.set_score_summary(self._score_summary_text())

    def _on_decide_mode(self, on: bool) -> None:
        """切了「分成好幾類」—— 門檻線只對二元那一種有意義。

        ⚠ 這裡以前自己判一次（``None if on else …``），而 `_refresh_spread`
        每跑一次就把它蓋回去。判斷現在只有一份（`_uses_a_threshold`）。
        """
        self._sync_threshold_line()
        self._sync_score_widgets()

    def _refresh_feature_combo(self) -> None:
        """判定面板的「插入數字 ▾」清單（F21-B）。"""
        self.decide_panel.set_features(self.model.labelled_features())

    # ---- Spread（F18 第 2 步：它從量測卡的儀表搬來這裡）--------------------
    def _features_in_results(self, results: Sequence[Dict[str, Any]]) -> List[str]:
        """整批結果裡真的有值的特徵名（順序照第一顆的順序）。

        **從結果讀而不是從 recipe 問**（`model.available_features()`）：
        那一份是「宣告會產出的」，而這張圖畫的是「真的算出來的」。一張卡出錯
        的那幾顆不會有它的特徵，而下拉裡多一個永遠畫不出東西的名字，正是
        「按了撞牆的鈕」那一類。
        """
        names: List[str] = []
        for r in results:
            for k in (r.get("features") or {}):
                if k not in names:
                    names.append(str(k))
        return names

    def _spread_segments(self, name: str) -> List[Any]:
        """``[(這個數字的值, 那一顆所屬類別的顏色), …]``（算不出來的不列）。"""
        colours: Dict[str, str] = {}
        for row in self.results.verdict.rows():
            if row.get("kind") != "class":
                continue
            for did in (row.get("ids") or ()):
                colours[str(did)] = str(row.get("colour"))
        out = []
        for r in self.trial_results or []:
            v = (r.get("features") or {}).get(str(name))
            colour = colours.get(str(r.get("defect_id")))
            if colour and isinstance(v, (int, float)) \
                    and not (math.isnan(float(v)) or math.isinf(float(v))):
                out.append((float(v), colour))
        return out

    @staticmethod
    def _bin_segments(edges: Sequence[float], points: Sequence[Any]):
        """把 ``(值, 顏色)`` 灑進直方圖的格子裡 → 每一格的 ``[(顏色, 顆數)]``。

        ⚠ **每一格裡的顏色順序要穩定**（照第一次出現的順序），否則同一批資料
        重畫兩次，堆疊的上下會換位子 —— 而那看起來像數字變了。
        """
        n = max(0, len(list(edges)) - 1)
        if n <= 0 or not points:
            return None
        lo, hi = float(edges[0]), float(edges[-1])
        width = (hi - lo) or 1.0
        order: List[List[Any]] = [[] for _ in range(n)]
        for value, colour in points:
            i = min(n - 1, max(0, int((float(value) - lo) / width * n)))
            cell = order[i]
            for pair in cell:
                if pair[0] == colour:
                    pair[1] += 1
                    break
            else:
                cell.append([colour, 1])
        return [[(c, k) for c, k in cell] for cell in order]

    def _default_spread_feature(self, results: Sequence[Dict[str, Any]]) -> str:
        """第一次打開那張圖要看哪個數字（R2，2026-08-24）。

        **你的第一個問題問的那個數字。** 那是這份 recipe 的判定真正建立在
        上面的量，所以「這一批在它上面長什麼樣」正是使用者接下來要問的事 ——
        而且它不必猜，樹上就寫著。

        沒有樹（二元那條老路）就退回 `suggest_condition` 挑分得最開的那個；
        兩個都答不出來就回空字串 = 維持「Score」。

        ⚠ 以前這裡沒有東西，一律開在「Score」—— 而樹的 recipe 沒有分數表達式，
        於是整批 24 顆全部落在 0，畫出來是**一根柱子**。這一頁最大的那張圖，
        在最常見的情況下什麼都沒說。
        """
        from .tree_scene import display_tree, parse_simple_condition, suggest_condition

        tree = display_tree(getattr(self.model, "decide", None))
        root = getattr(tree, "when", None)
        if root:
            simple = parse_simple_condition(str(root))
            if simple and simple[0]:
                return str(simple[0])
        guess = suggest_condition(list(results or []))
        return str(guess[0]) if guess else ""

    def _refresh_spread(self) -> None:
        """把下面那張圖換成「現在選的那個東西」的分佈。"""
        name = self.results.shown_feature()
        if name == self.results.SCORE:
            # ⚠ **門檻線只在真的有一條門檻在決定事情的時候才畫**（R1，2026-08-24）。
            #
            # 這裡以前無條件 `set_threshold(self.model.threshold)` ＋
            # `rebin(scores, threshold, bins)` —— 而 `_on_decide_mode(True)` 早就
            # 把那條線關掉了。它**只在模式切換時觸發一次**，這一支每跑一次都
            # 蓋回去，所以蓋掉的那一份才是使用者看到的。
            #
            # 後果是畫面上兩個互相矛盾的答案：每一張卡說 `bin 3`（樹真的判出來
            # 的），而 150px 底下的圖例說 `bin 1=24`，還附一行用那條門檻算的
            # `accuracy 50% missed 0 false alarms 12`。F25 之後**每一份 recipe
            # 一打開就是一棵樹**，所以那是所有人都會看到的畫面。
            self.histogram.set_marker(None)
            self.histogram.set_empty_text(
                "(Score distribution appears after a trial run)")
            edges, counts = histogram(self.trial_scores)
            self.histogram.set_data(edges, counts)
            self._sync_threshold_line()
            self.results.set_spread_hint("")
            return

        vals = [float(v) for r in self.trial_results
                for v in [(r.get("features") or {}).get(name)]
                if isinstance(v, (int, float))
                and not (math.isnan(float(v)) or math.isinf(float(v)))]
        # **這一段裡是哪一類**（R2 第二半）：一根單色的長條答不出這個，
        # 而「分得開誰」才是看這張圖的人真正在問的事。
        #
        # ⚠ **只有「看某個特徵」時才染。** 看「Score」是二元那條路，而那條路
        # 上的類別就是門檻切出來的兩邊 —— 門檻線本身已經畫在那裡了，再上一次
        # 色是同一件事講兩次。
        segments = self._spread_segments(name)
        # 門檻是**分數**的門檻 —— 在別的特徵上它沒有意義，所以整張圖唯讀
        # （見 `HistogramWidget.set_interactive`）。
        self.histogram.set_interactive(False)
        self.histogram.set_threshold(None)
        self.histogram.set_bin_summary(None)
        self.histogram.set_empty_text("(no values for %s in this run)" % name)
        edges, counts = histogram(vals)
        self.histogram.set_data(edges, counts)
        self.histogram.set_segments(self._bin_segments(edges, segments))
        # `_last_result` 是 `DefectResult`（dataclass），不是 dict —— 這一格
        # 曾經寫成 `.get("features")`，而它在**選了特徵之後**才會走到，
        # 所以那個錯不會在「按 Run」的路徑上出現。
        here = (getattr(self._last_result, "features", None) or {}).get(name)
        try:
            here = float(here)
        except (TypeError, ValueError):
            here = None
        self.histogram.set_marker(here, "this defect" if here is not None else "")
        self.results.set_spread_hint(self._spread_hint(name, vals))

    def _spread_hint(self, name: str, values: Sequence[float]) -> str:
        """一句話：這個特徵在這一批上分不分得開。

        這是 Spread 面板原本最有用的那一句 —— 擠成一根柱子的特徵，門檻設哪裡
        都一樣，而光看長條圖不一定看得出「它其實只差 0.3%」。
        """
        vals = [float(v) for v in values]
        if len(vals) < 4:
            return "%d values — too few to say anything about the spread." % len(vals)
        lo, hi = min(vals), max(vals)
        mid = (abs(lo) + abs(hi)) / 2.0 or 1.0
        if hi - lo <= 0 or (hi - lo) / mid < 0.01:
            return ("%s barely varies across the batch — no threshold on it "
                    "will separate anything." % name)
        return "%d defects · %.4g to %.4g" % (len(vals), lo, hi)

    def _on_spread_feature_changed(self, _name: str) -> None:
        self._refresh_spread()

    def _refresh_decide_counts(self) -> None:
        """判定面板每一條規則右邊的「bin N · 幾顆 · 純度」（F22-UI）。

        跟 F18 的灰階面板同一個立論：調規則的人是**一邊改一邊看**的。
        沒跑過就餵空的 —— 顯示 0 會讓人以為「這一格一顆都沒有」。
        """
        rows = list(self.trial_results or [])
        # 畫布上的判定區跟著這一批走（F24 ②：分支流量、托盤顆數）。
        decision = self._decision_info()
        for view in self._canvases():
            view.set_decision(decision)
        self.tree_pane.set_rows(rows)
        self.tree_pane.set_counts(None if not decision
                                  else decision.get("counts"))
        prefilter = self._prefilter_info()
        for view in self._canvases():
            view.set_prefilter(prefilter)
        if not rows:
            self.decide_panel.set_counts(None)
            return
        counts: Dict[int, int] = {}
        for r in rows:
            b = r.get("bin")
            if b is None:
                continue
            counts[int(b)] = counts.get(int(b), 0) + 1
        purity = None
        if self.ground_truth:
            from d4t.core.export import summarize
            purity = summarize(rows, ground_truth=self.ground_truth).get("bin_purity")
        self.decide_panel.set_counts(counts, purity=purity)

    def _refresh_verdict(self) -> None:
        """判定段（R3）：**這一批判成了什麼**。

        跟畫布的分支流量吃同一份 `tree_scene` —— 不自己數第二份。
        """
        self.results.set_verdict(getattr(self.model, "decide", None),
                                 list(self.trial_results or []),
                                 self.ground_truth)

    def _on_verdict_class(self, key: str) -> None:
        """點了判定段的某一類 → Gallery 只留那一類（``""`` = 看全部）。

        ⚠ 篩的是 **defect_id**，不是 bin：一個 bin 可能有好幾片葉子，照 bin
        篩會把另一片葉子的顆一起撈進來 —— 而那兩片葉子是使用者刻意分開命名的。
        """
        want = str(key or "")
        if not want:
            self.results.set_filter(None)
            return
        row = next((r for r in self.results.verdict.rows()
                    if str(r.get("key")) == want), None)
        if row is None:
            self.results.set_filter(None)
            return
        name = str(row.get("name") or "").strip() or "these"
        # 縮圖與表格一起篩（2026-09-09）—— 兩種看法看的是同一批。
        self.results.set_filter({"mode": "ids", "ids": list(row.get("ids") or ()),
                                 "label": "%s only" % name})

    def _uses_a_threshold(self) -> bool:
        """**這份 recipe 真的有一條門檻在決定事情嗎。**

        R1（2026-08-24）修的那個 bug 的形狀是：這個判斷散在四個地方，而其中
        三個沒有做 —— 於是「關掉門檻線」與「無條件把門檻線設回去」在同一次
        重新整理裡互相蓋，最後贏的是錯的那一個。畫面上的下場是每一張縮圖說
        `bin 3`、150px 底下的圖例說 `bin 1=24`，還附一行用那條門檻算出來的
        準確率。同一批 24 顆，兩個答案。

        所以判斷收成這一支，四個呼叫端都問它。F25 之後幾乎永遠是 False
        （每一份 recipe 一打開就是一棵樹），但二元那條老路仍然走得到。
        """
        return getattr(self.model, "decide", None) is None

    def _sync_threshold_line(self) -> None:
        """門檻線與它底下那行字 —— **有門檻才畫**（見 `_uses_a_threshold`）。"""
        if self._uses_a_threshold():
            self.histogram.set_interactive(True)
            self.histogram.set_threshold(self.model.threshold)
            self._refresh_bin_summary(self.model.threshold)
            return
        self.histogram.set_interactive(False)
        self.histogram.set_threshold(None)
        # 樹判出來的顆數是**真的那一份**，不是重算的，而它在判定段上已經有
        # 更好的位置了（每一類一列、寬度就是顆數）—— 不在這裡再講一次。
        self._refresh_decide_counts()
        self.histogram.set_bin_summary(None)

    def _refresh_bin_summary(self, threshold: float) -> None:
        self._refresh_decide_counts()
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

    def _publish_run_snapshot(self, threshold: Optional[float] = None) -> None:
        """把這一批壓成一塊交給 Results 的 baseline 條（X1）。

        **門檻拖到哪就用哪一個**：使用者拖著那條線看的正是「這樣調準不準」，
        而 baseline 那一行答的是「比上一次好還是壞」—— 兩者不同步的話，
        畫面上會有兩個算法不同、看起來都像現在這一批的正確率。
        """
        try:
            snap = baseline.snapshot(
                self.trial_results, self.ground_truth, self.model.bins,
                threshold=threshold)
        except Exception:  # 顯示用，壞了就不講
            swallowed("studio._publish_run_snapshot")
            return
        self.results.set_run_snapshot(snap if self.trial_results else None)

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

    def _on_truth_marked(self, marks: Any) -> None:
        """使用者在結果表上標了幾顆（X2）—— 併進答案卷、寫檔、重算正確率。

        **寫檔是這一支的事，不是那張表的事**：只有 Studio 知道資料在哪
        （`truth_marks.path_for`），而那張表連 `Dataset` 都沒看過。

        寫不出去的時候要**講**，不可以安靜地只改記憶體裡那一份：使用者標了
        50 顆、關掉 Studio、下次開起來一顆都沒有，而中間沒有任何一句話。
        """
        marks = dict(marks or {})
        if not marks:
            return
        merged = truth_marks.merge(self.ground_truth, marks)
        path = truth_marks.path_for(self.dataset)
        wrote = ""
        if path:
            try:
                wrote = truth_marks.write(path, merged)
            except OSError as e:
                self._status("Could not save the labels to %s: %s  (they are "
                             "on screen only until this is fixed.)"
                             % (path, e), level="error")
        else:
            self._status("Labelled on screen only - there is nowhere to put "
                         "%s for this data (no KLARF and no image folder)."
                         % truth_marks.FILENAME, level="error")
        self.ground_truth = merged or None
        self.results.set_truth(dict(merged))
        # 標了之後正確率就變了 —— 判定段、直方圖底下那一行、baseline 那一條
        # 全部吃同一份答案卷，所以三個都要跟上（少一個 = 畫面上兩個數字在
        # 講同一件事而不一樣）。
        self._refresh_verdict()
        self._refresh_spread()
        self._publish_run_snapshot(None)
        if wrote:
            self._status(truth_marks.summary_text(
                merged, len(self.trial_results or []), wrote))

    # ==================================================================== #
    # 卡片庫 / 流程
    # ==================================================================== #
    def _on_add_requested(self, step_key: str) -> None:
        if str(step_key) == _SCORE_LIBRARY_KEY:
            # 「Decision」不是可增刪的卡片 —— 每條 pipeline 固定有一棵判定樹，
            # 點它就是**把它放上畫布並開始編第一步**（F25，使用者定調：
            # 「加 ADC card 是要直接顯示在畫布上，而不是要勾選才顯示」）。
            self.add_decision()
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
        self._autofill_new_card(node_id)
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
            self._autofill_new_card(new_id)
        self._status("Added “%s” after “%s” — drag a line into it to say which "
                     "image stream it works on.%s"
                     % (new_id, nid, self._unmet_needs(new_id)))
        self.select_node(new_id)
        return new_id

    def _autofill_new_card(self, node_id: Optional[str]) -> None:
        """剛加進來的卡，把**這個畫面上已經知道的答案**先填好。

        現在只有一張卡走這條路：``roi_reference`` —— **已經掛上來的那份 GLAS
        匯出**的層對照表。那個答案已經在畫面上了，讓使用者用手抄一次是在製造
        一個可以抄錯的機會，而它是一張**對照表**（層號 → 名字），不是接線。

        ⚠ ``roi_mask`` 曾經也在這裡：加進來時把上游每一個區域名都填進
        ``regions``。**F12 拿掉了**，因為區域現在是畫布上的線 —— 自動填等於
        自動幫他畫了六條他沒有拉過的線，而那正是鐵則 10 擋的那件事
        （「加卡不准順手接線：自動接的線與使用者拉的線會落在同一個輸入，
        而只有一條算數」）。他不再需要用手抄名字：埠就在旁邊，拉過去就是了。

        第二個是 2026-08-18 補的，而它修掉一個順序造成的洞：填名字那段原本只在
        **掛匯出的當下**跑一次，掃的是當時已經存在的卡。但使用者的自然順序是
        「開 KLARF → 開 GDS 匯出 → 加卡」（那顆鈕在沒有 lot 的時候是灰的，
        空白狀態也叫他先載 lot）—— 於是後加的那張卡是空的，而它擋下來的那句話
        寫著「Use “Open GDS export…” — attaching the export fills in the layers」。
        使用者剛做完那件事。**一句叫人去做他已經做過的事的訊息，比沒有訊息更糟。**
        """
        node = self.model.nodes.get(str(node_id or ""))
        if node is None:
            return
        if node.step == "roi_reference":
            self._autofill_gds_layers(node)

    def _autofill_gds_layers(self, node: Any) -> None:
        """這張卡**永遠不該是空的** —— 空的看起來跟「線沒接上」一模一樣。

        使用者 2026-08-18：「一開始 layout labels 連過去 GDS layer card 時候
        image stream 完全不會顯示任何 overlay，要輸入 region name 才有，我希望
        有個防呆機制讓 Layer 一開始就填好⋯⋯避免 user 以為沒連到沒 work」。

        這張卡的規則是「**某一列空著 = 那一層不要**」，而那條規則是對的（要有
        辦法排除一層）。貴的是**整張卡都空著**的那個狀態：一個區域都不吐、影像
        上一個框都沒有，跟線沒接上長得一樣。所以只要看得到層，就先填。

        名字的優先順序（好的先用）：

        1. **掛上來那份匯出的 label_map** —— 真的層名（`L17/D0` → `L17_D0`）。
        2. **這一顆 label 圖上真的出現的 id** —— `LayerA` / `LayerB`…
           走到這裡的情況是 manifest 沒有 `label_map`（GLAS 匯出時沒勾）。
           名字很爛，但它讓接線這件事**當場看得到結果**，而名字使用者本來就會改。

        只在**空的**時候填 —— 使用者打過的字不覆蓋（重新掛一次匯出也不覆蓋）。

        ⚠ **``method`` 也一起填**（F29）。這張卡收成兩支之後預設是
        ``repeating cells``（不需要任何外部資料，所以它是對的預設）——
        但畫面上已經掛著一份 GLAS 匯出的人，加這張卡要的一定是另一支，
        而那一支的層對照表就在旁邊。同一句話：**把畫面上已經知道的答案先填好**。
        不是自動接線（鐵則 10 擋的是那件事）—— 這裡改的是一個下拉，
        而使用者一眼看得到它，改回去是一個動作。
        """
        if str(node.params.get("layers", "") or "").strip():
            return              # 使用者打過的字不覆蓋
        from d4t.core.ingest import glas_export
        from d4t.core.steps.roi_reference import METHOD_GDS

        default = glas_export.layer_map_default(self._gds_layers)
        count = len(self._gds_layers)
        if not default:
            ids = self._label_ids_for(node)
            default = glas_export.fallback_layer_names(ids)
            count = len(ids)
        if default:
            self.model.set_param(node.id, "method", METHOD_GDS)
            self.model.set_param(node.id, "layers", default)
            self.param_form.set_label_count(count)

    def _label_ids_for(self, node: Any) -> List[int]:
        """這張卡接的那條流上，上一次預覽真的看到哪幾個 label id。

        來源是 ``load_sidecar`` 寫的 ``ctx.meta["layout_label"][流名]["ids"]``
        —— **畫面上的數字就是引擎算的那一份**（同儀表的慣例），這裡不自己再拆
        一次 label 圖。
        """
        ctx = getattr(getattr(self, "_last_result", None), "context", None)
        if ctx is None:
            return []
        stream = str(node.params.get("label_source", "") or "")
        rec = (getattr(ctx, "meta", None) or {}).get("layout_label") or {}
        entry = rec.get(stream) or {}
        return [int(i) for i in (entry.get("ids") or ()) if int(i) > 0]

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
            #
            # ⚠ **那件事不在這一支做**：`_connect` 早就把它交給 `add_edge` 了
            # （`dst_in=plan.param`），而且是在呼叫這裡**之前**。順序有意義 ——
            # 參數的預設值本來就等於那條流時，下面會提早 return（沒有東西要
            # 改），但線還是接在這個參數上。落在這一支的話那條線在引擎眼裡就是
            # 「沒指定」，於是退回用「執行順序上最後一個寫它的人」推 ——
            # 分支當場失效。
            #
            # 這裡以前還有一個 `self._bound_param = name`（上下各一次）——
            # 那是那個舊機制的殘留：**寫了三次、一次都沒有被讀過**。真相搬到
            # 邊上之後它就只是一個會讓人以為「有人在用它」的欄位。2026-09-08 刪。
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
            if joined and "," in value:
                return (" — “%s” now works on %s (same settings for both)"
                        % (node_id, " and ".join(value.split(","))))
            return " — “%s” now works on %s" % (node_id, stream)
        return ""

    def _producers_of(self, stream: str) -> List[str]:
        """哪些卡片（用預設參數）會產出 ``stream``。

        ⚠ **實作住 `ui/edit_plan.py`**（U6）：它是圖編輯語意的一部分，而那一族
        必須在沒有 QApplication 的情況下問得出來。這裡只是轉呼叫。
        """
        return edit_plan.producers_of(self.model, stream)

    def _unmet_needs(self, node_id: str) -> str:
        """剛加的卡少了什麼上游 —— 講成一句可以照做的話（含前導空白）。

        ⚠ 實作住 `ui/edit_plan.py`（同上）。
        """
        return edit_plan.unmet_needs(self.model, node_id)

    def _drop_conflicting_edges(self, src: str, dst: str, stream: str,
                                param: str) -> str:
        """拿掉「跟這條新線搶同一個輸入」的舊線；回一句給狀態列的話。

        ⚠ **判準住 `edit_plan.conflicting_edges`**（U6）—— 那是引擎正確性的
        一半（F9-7「一個輸入埠只能有一條線」），而它現在問得起來而不必開視窗。
        這裡只剩「真的拿掉」與「說一句話」。
        """
        return self._drop_edges(
            edit_plan.conflicting_edges(self.model, src, dst, stream, param))

    def _drop_edges(self, losers: Sequence[Any]) -> str:
        """把讓位的那幾條線真的拿掉；回一句給狀態列的話（沒有就回空字串）。

        ⚠ **兩個埠都要指名**（B1，2026-08-24）。兩張卡之間可以有好幾條並排的
        線（F9-9），而它們可能落在**不同的輸入格**上 —— 只帶 `src_out` 的話
        `remove_edge` 的語意是「符合這個 src_out 的**全部**」，於是剪一條會剪掉
        一整排。

        實測：`load.test → subtract.a` 與 `load.test → subtract.b` 兩條並存時，
        把別的卡接到 `b` 會**連 `a` 那條一起剪掉** —— 沒有人碰過 `a`，而 `a` 的
        參數還留著 `test`：畫布上沒有線、卡片卻還指著那條流，於是引擎退回
        「執行順序上最後一個寫它的人」用猜的。線性時猜得中、分岔時猜錯，
        而且跑得完、有數字（F9／F10 整整兩輪在防的形狀）。

        ⚠ **不可以寫 `e.src_out or None`。** 空字串在 `remove_edge` 裡本來就是
        「精確比對空埠」，`or None` 會把它變成「全部」—— 那正是上面那個洞的
        第二階。
        """
        losers = list(losers or [])
        for e in losers:
            self.model.remove_edge(e.src, e.dst, src_out=e.src_out,
                                   dst_in=e.dst_in)
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

        **拉一條線 = 一步復原**（F9-7）。在 model 上它其實是三個動作
        （add_edge → set_param →（有時）拿掉搶同一個輸入的舊線），各記一步
        的話按一次 Ctrl+Z 會停在「線接上了但那張卡還沒改成處理它」這種中間
        狀態 —— 使用者從來沒有做出過那個畫面。

        ⚠ 這一段以前寫著 ``add_edge → set_param → set_edge_ports → …``，
        而 `set_edge_ports` 從 F9-9 起就沒有人叫了（那一輪改成「加線的時候
        就把埠一起帶進去」，因為補埠只找得到一對節點之間的第一條線，
        兩條並排的線會補錯）。留著一個描述不存在流程的說明比沒有說明更糟 ——
        它就寫在那段程式碼的正上方。
        """
        src, dst, stream = str(src), str(dst), str(stream or "")
        with self.model.compound("connect"):
            self._connect(src, dst, stream, str(dst_in or ""))

    def _connect(self, src: str, dst: str, stream: str,
                 dst_in: str = "") -> None:
        """使用者拉了一條線 —— **決定住 `edit_plan`，這裡只負責做與說**（U6）。

        ⚠ **順序有意義，所以它留在這裡**：`add_edge` 會因為成環而失敗，而
        失敗的那條線**不該留下任何痕跡** —— 尤其不是「那張卡安靜地改成做 ref
        了」。把 mutation 也包進計畫裡就得在那邊把 model 模擬一遍，那是把一個
        難的東西換成兩份會漂的東西。
        """
        plan = edit_plan.plan_connect(self.model, src, dst, stream, dst_in)
        if plan.kind == edit_plan.REJECT:
            self._status(plan.reject, "error")
            return
        # **「已經接過了」兩側共用一關**（U6）：以前影像那一側問的是
        # `has_line`、區域那一側問的是「這個名字在不在那一格裡」，兩句話寫在
        # 兩個地方。現在兩個都由 `plan.already` 回答 —— 而它們本來就是同一個
        # 問題（使用者剛做的這個動作有沒有改變任何東西）。
        if plan.already:
            self._status(plan.already)
            return
        if plan.kind == edit_plan.REGION:
            self._connect_region(src, dst, stream, plan)
            return
        if not self.model.add_edge(src, dst, src_out=stream,
                                   dst_in=plan.param):
            self._status("Cannot connect %s → %s — that would make the "
                         "pipeline loop back on itself." % (src, dst), "error")
            return
        # 影像流在**線真的接起來之後**才改（見上面那段 ⚠）。同一對節點的第二
        # 條線是「這條也接上」（累加），不是「改接別的」。
        note = self._point_at_stream(dst, stream, accumulate=plan.accumulate,
                                     param=plan.param)
        # **一個輸入埠只能有一條線**：新的這條贏，舊的那條拿掉（F9-7）。
        dropped = self._drop_edges(plan.conflicts)
        # **接完線就把這張卡填到「看得到結果」為止**（F11 Region-3 第五輪）。
        # 加卡的時候也跑過一次，但那時候還沒有線 —— 而「接上 layout labels」
        # 正是使用者期待畫面上出現東西的那一刻。
        self._autofill_new_card(dst)
        self._resync_params(dst)
        self._status("Connected %s → %s%s%s" % (src, dst, note, dropped))

    # ---- 區域線（F12）-----------------------------------------------------
    def _is_region_param(self, node_id: str, param: str) -> bool:
        """``node_id`` 的 ``param`` 那一格吃的是具名區域嗎。

        ⚠ 實作住 `ui/edit_plan.py`（U6）—— 這裡只是轉呼叫。
        """
        return edit_plan.is_region_param(self.model, node_id, param)

    def _line_kind(self, node_id: str, name: str) -> str:
        """從 ``node_id`` 的哪一顆埠拉出來的 —— 影像還是區域。

        ⚠ 實作住 `ui/edit_plan.py`（同上）。
        """
        return edit_plan.line_kind(self.model, node_id, name)

    def _connect_region(self, src: str, dst: str, name: str,
                        plan: Any) -> None:
        """把 ``dst`` 的區域那一格接上 ``src`` 定義的區域 ``name``。

        **擋得住什麼、哪幾條舊線讓位，全部由 `edit_plan.plan_connect` 決定**
        （U6）—— 這裡只剩「真的動 model」與「說一句話」，而那兩件事的順序
        有意義（見 `_connect` 那段 ⚠）。
        """
        param = plan.param
        node = self.model.nodes.get(dst)
        spec = next((sp for sp in get_step(node.step).region_input_specs()
                     if sp.name == param), None)
        current = str(node.params.get(param, "") or "")
        keys = [k.strip() for k in current.split(",") if k.strip()]
        # **從一個變成兩個時，把自動填的那個名字收回**（F13-⑥）。
        # 接第一條線時 `_autofill_output_prefix` 會把輸出名填成那個區域
        # （F7-11），而第二條線一來，每個數字本來就會帶自己的區域名 ——
        # 兩個加起來是 `epi_epi_glv_mean`。判準是「它正好等於原本那一個
        # 區域的名字」＝ 那正是自動填會寫的值；使用者自己打過的字不動。
        multi = spec is not None and spec.type == "region_keys"
        if multi and len(keys) == 1 and \
                str(node.params.get("output_prefix", "")) == keys[0]:
            try:
                self.model.set_param(dst, "output_prefix", "")
            except ParamError:                 # pragma: no cover
                pass
        # **改名的連帶影響要在值變之前先記下來**（F37 A2）。以前它是
        # `set_param` 的回傳值，而 F42 B2 之後值是**水合**出來的 —— 那一格不再
        # 由這裡寫，所以「動之前長什麼樣」也要由這裡自己抱著。
        before = dict(node.params)
        if not self.model.add_edge(src, dst, src_out=name, dst_in=param):
            self._status("Cannot connect %s → %s — that would make the "
                         "pipeline loop back on itself." % (src, dst), "error")
            return
        # **單一角色的區域埠一條線**（F12 §7-②）：`region_key` 那一格只放得下
        # 一個名字，所以第二條線是「改接別的」不是「這個也算」。判準住
        # `edit_plan.region_conflicts`。
        self._drop_edges(plan.conflicts)
        value = str(self.model.nodes[dst].params.get(param, "") or "")
        # 挑了區域就順手把輸出名填成區域的名字（F7-11）—— 拉線跟在設定區挑
        # 是同一個動作，所以走同一條路。
        self._autofill_output_prefix(dst, param, value)
        says = self.model.rename_fallout(dst, before,
                                         self.model.nodes[dst].params)
        self._resync_params(dst)
        self._say_fallout(says, "“%s” now measures %s (defined by “%s”)."
                          % (dst, value.replace(",", " and "), src))

    def _say_fallout(self, says: List[str], otherwise: str = "") -> None:
        """改名的連帶影響優先於「接好了」那句話（F37 A2）。

        量測卡的前綴是條件式的，所以在一張既有的卡上多接一條區域線，它寫的
        每一個名字都會改（``glv_median`` → ``epi_glv_median`` ＋
        ``mg_glv_median``），而分數表達式、判定樹、Output 卡的 ``rank_by``
        裡指著舊名字的字不會跟著改。

        使用者只做了一個動作，下游三個地方同時失效 —— 而在這之前，畫面上唯一
        的訊息是「接好了」。所以有連帶影響的時候，**那句話蓋過成功訊息**
        （紅字），沒有的時候才報成功。

        ⚠ 這一句是**當下**的提醒，不是唯一的防線：`stale-feature-ref` 這條
        lint 會讓那張卡在畫布上一直掛著警示標記，直到有人處理它。狀態列的字
        會被下一個動作蓋掉，而那正是它不能是唯一防線的理由。
        """
        if says:
            # **誤操作後的三秒鐘，是使用者最不想去找 Ctrl+Z 的三秒鐘**（X6）。
            # 他正在讀這句話，所以反悔的路要在這句話旁邊。Ctrl+Z 照樣在 ——
            # 這顆鈕只是把已經做得到的事縮短成一次點擊。
            self._status_next_step(
                " ".join(says), "Undo", self.undo, "error",
                "Undo that change (Ctrl+Z)")
        elif otherwise:
            self._status(otherwise)

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
        """剪掉一條線 —— **收尾一定要重讀設定欄**（見 :meth:`_resync_params`）。

        用一層外殼而不是在每個 ``return`` 前面加一行：這支底下有五條分支
        （區域線／瞄得到那一條／退回整對／舊格式…），而漏掉其中一條的症狀是
        「大部分時候會跟上」—— 那種 bug 查起來最貴。
        """
        try:
            self._apply_edge_removed(src, dst, stream, dst_in)
        finally:
            self._resync_params(dst)

    def _apply_edge_removed(self, src: str, dst: str, stream: str = "",
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
        # **這一段要排在區域那條岔路前面**（F42 B2）：區域線現在也是一條真的
        # Edge，所以「這是不是區域線」的答案就藏在剛問出來的那個 ``dst_in`` 裡。
        if not dst_in:
            for e in self.model.edges:
                if (e.src == src and e.dst == dst
                        and (not stream or e.src_out == stream)):
                    dst_in = e.dst_in
                    break
        # **區域線現在是一條真的 Edge**（F42 B2）：剪它跟剪影像線一樣，
        # 而「那一格跟著空掉」是水合的自然結果（`RecipeModel._hydrate_regions`）
        # —— 不必在這裡另外清一次。以前它沒有 Edge 可刪，所以清參數就是全部。
        if self._is_region_param(dst, dst_in):
            node = self.model.nodes.get(dst)
            before = dict(node.params) if node is not None else {}
            with self.model.compound("disconnect"):
                gone = self.model.remove_edge(
                    src, dst, src_out=stream or None, dst_in=dst_in)
            if not gone:
                self._status("%s → %s is not connected on %s."
                             % (src, dst, stream or "that region"))
                return
            says = self.model.rename_fallout(
                dst, before, self.model.nodes[dst].params)
            left = str(self.model.nodes[dst].params.get(dst_in, "") or "")
            note = ((" — “%s” has no region on “%s” now" % (dst, dst_in))
                    if not left else
                    " — “%s” now measures %s" % (dst, left.replace(",", " and ")))
            note += ("  " + " ".join(says)) if says else ""
            self._status("Disconnected %s → %s on %s%s"
                         % (src, dst, stream or "that region", note))
            return
        with self.model.compound("disconnect"):
            one = stream and self.model.remove_edge(
                src, dst, src_out=stream, dst_in=dst_in or None)
            # **知道是哪一格就用它**（B5，2026-08-24）。上面那一段已經從線本身
            # 問出了 ``dst_in``，但沒有流名時 ``stream and …`` 整條短路掉，於是
            # 直接跳到最後那個「拿掉整對」—— 兩張卡之間有兩條並排的線時
            # （F9-9 起是正常的接法），使用者按一把剪刀會斷兩條。
            if not one and dst_in:
                one = self.model.remove_edge(src, dst, dst_in=dst_in)
                if one:
                    note = self._unpoint_stream(dst, stream, dst_in)
                    self._status("Disconnected %s → %s%s" % (src, dst, note))
                    return
            if one:
                note = self._unpoint_stream(dst, stream, dst_in)
                self._status("Disconnected %s → %s on %s%s"
                             % (src, dst, stream, note))
            # 兩個埠都問不出來（舊格式的線沒有埠）→ 拿掉整對。那是刻意的：
            # 瞄不到特定那一條的時候，「全部拿掉」至少是可預期的。
            elif self.model.remove_edge(src, dst):
                note = self._unpoint_stream(dst, stream, dst_in)
                self._status("Disconnected %s → %s%s" % (src, dst, note))

    def _unpoint_stream(self, node_id: str, stream: str,
                        param: str = "") -> str:
        """線剪掉了 → 那條流也要從下游卡的參數裡拿掉（回一句給狀態列的話）。

        不拿掉的話畫布會**反過來說謊**：畫面上那條線沒了，卡片卻還在處理它
        （`streams=test,ref` 一個字都沒變）。這是 F9-7「接線時參數跟著改」的
        另一半。

        ⚠ **「那一格會變成什麼」住 `edit_plan.plan_unpoint`**（U6）—— 含那兩個
        F10 拿掉的保留條款、以及「區域那一格不歸這裡管」。這裡只剩寫值與說話。
        """
        plan = edit_plan.plan_unpoint(self.model, node_id, stream, param)
        if not plan.change:
            return ""
        try:
            says = self.model.set_param(str(node_id), plan.param, plan.value)
        except ParamError:                     # pragma: no cover — 值就是流名
            return ""
        # 影像流那一側同理（接第二條流也會把名字加上流名前綴）。這一支回的是
        # 一段**接在成功訊息後面**的字，所以連帶影響也接在同一句話上 ——
        # 而不是另外開一個要有人記得去消費的欄位。
        tail = ("  " + " ".join(says)) if says else ""
        if not plan.value:
            return " — “%s” has no input on “%s” now%s" % (
                node_id, plan.label, tail)
        return " — “%s” now works on %s%s" % (node_id, " and ".join(
            plan.value.split(",")), tail)

    def _on_remove_requested(self, node_id: str) -> None:
        node_id = str(node_id)
        # 刪掉一張卡 = 把它餵出去的每一條線都剪掉（F10-5）。下游那幾格要跟著
        # 空出來，否則它們指著一條再也沒有人產出的流 —— 跟按 × 剪掉是同一件事，
        # 所以走同一條路（`_unpoint_stream`），不要在這裡另寫一份。
        with self.model.compound("remove-card"):
            for e in [e for e in self.model.edges if e.src == node_id]:
                # **區域線跳過**（F42 B2）：它現在也住在 `model.edges` 裡，而
                # 它那一格是**水合**出來的 —— 在線還在的時候先把它清掉，
                # 「參數 ＝ 線說的」那條不變量就當場破了（而它是常開的斷言）。
                # `model.remove` 拿掉線之後水合會把它空出來，這裡不必動它。
                if is_region_edge(e, self.model.nodes):
                    continue
                self._unpoint_stream(e.dst, e.src_out, e.dst_in)
            # 區域線**不必**在這裡處理了（F42 B2）：它現在是一條真的 Edge，
            # 而 `RecipeModel.remove` 刪卡時本來就會把它兩端的線一起拿掉 ——
            # 拿掉之後水合就把下游那幾格空出來。以前它是從參數推導的，
            # 所以「把那一格空掉」非得在這裡自己做一次不可。
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
        self._tree_focus = False       # 回到卡片：預覽又停在這張卡
        self._user_stream = None       # 換節點 → 影像流回到「這個節點的輸出」
        # 換卡片＝上一段連續調整結束（見 viewmodel 的 coalescing）。不切的話，
        # 「調 A 卡的 gamma → 換到 B 卡 → 再調回 A 卡的 gamma」會被併成一步。
        self.model.end_coalescing()
        for view in self._canvases():
            view.set_selected(node_id)
            view.set_tree_selected(None)   # 一次只編一個東西（卡片或樹的一步）
        self._fill_param_form(node_id)
        self.stack.setCurrentWidget(self.param_form)
        self.gauge_note.setText("")              # 儀表又是這張卡的了（P1-7）
        self.bottom_stack.setEnabled(True)
        self._sync_params_pane()
        self._refresh_region_button()
        # 右下角換成這張卡的儀表（F7-17）。**參數要一起給**：`roi_reference`
        # 一個 key 有四種面板，由 ``method`` 決定（F30）。
        self._install_inspector(node.step, node.params)
        self._refresh_inspector(self._last_result)
        self._refresh_kernel_hint()            # 核心大小畫在影像上（F11 UI-A）
        self._schedule_preview()
        return True

    def _fill_param_form(self, node_id: str) -> None:
        """把某一張卡的參數畫進設定欄（`select_node` 與 :meth:`_resync_params`
        共用的那一段）。

        **抽出來是因為它有第二個呼叫端。** 線動了之後也要重畫一次，而在這之前
        那件事只能靠 `select_node`（會連帶把預覽的影像流選擇歸零）或者「剛好有
        一次預覽跑完順手重建了表單」—— 後者正是這個 bug 難查的原因：**同一個
        動作有時候會跟上、有時候不會。**
        """
        node = self.model.nodes.get(str(node_id))
        if node is None:
            return
        try:
            describe = get_step(node.step).describe()
        except KeyError:
            describe = None
        streams = self.model.available_streams(before_node=node_id)
        regions = self.model.available_regions(before_node=node_id)
        self.param_form.set_step(
            describe, node.params, streams, regions,
            self._dynamic_choices_for(node))
        # 接線插槽的選單（F68）：**到這張卡為止**上游真的產得出來的那些 ——
        # 列一個排在自己後面才算出來的東西，選下去就是一份跑不動的 recipe
        # （同 `_dynamic_choices_for` 裡「插入數字 ▾」那一句的理由）。
        self.param_form.set_wiring_choices(regions=regions, streams=streams)
        self._sync_source_action(node)
        self._sync_glv_intent(node_id, node)

    def _resync_params(self, *node_ids: str) -> None:
        """線動了 → **選著的那張卡的設定欄要跟著動**（2026-09-01）。

        使用者回報：「在 canvas 上把線切斷時，理論上設定頁也要同步取消
        （他們是同步的）；同理，在 canvas 上把線連接時，也要同步設定。」

        model 那一層本來就同步（剪線 → 那一格真的空掉，`_hydrate_regions`
        與 `_unpoint_stream` 各自負責）—— 壞的是**畫面沒有人叫它重讀**。四條
        路裡只有一條會跟上，而那一條是**碰巧**的：它剛好排在一次預覽前面，
        而預覽跑完會重建表單。於是同一個動作有時候跟得上、有時候不跟，
        看起來像是隨機的。

        這條規矩跟 F9／F10 的「畫布不能說謊」是同一句話的鏡像：**畫布與設定欄
        講的必須是同一件事**，因為線是唯一的儲存，那一格只是它的另一個長相。
        """
        if any(str(n) and str(n) == str(self.selected_node) for n in node_ids):
            self._fill_param_form(str(self.selected_node))

    # ---- 入口卡的「資料從哪來」（F14-1）------------------------------------
    #: 附加檔那張卡（`load_sidecar`）→ 它要開哪一個 `scope.ATTACHMENTS`。
    _ATTACHMENT_CARDS = {"load_sidecar": "gds"}

    #: **自己帶一份 lot 的卡**（F15）。它跟 main 那幾張入口卡走同一顆
    #: `Open data…`，但載進來的東西掛在 `Dataset.sources[代號]` 上，
    #: 不取代目前的資料集。
    _PAIR_CARDS = ("pair_source",)

    #: 資料那幾張卡（`load_patch` / `load_single`）的鈕上寫什麼。
    #: **它不是某一種 source 的名字** —— 一份 KLARF 是 patch 還是一顆一張由檔案
    #: 決定，所以這顆鈕開的是一張選單（`scope.INPUT_SOURCES` 那三條路）。
    DATA_SOURCE_LABEL = "Open data…"

    def _source_action_for(self, node: Any) -> Tuple[str, str, str]:
        """這張卡的「資料從哪來」那一排：``(鈕上的字, 現況, tooltip)``。

        不是入口卡就回三個空字串（`ParamForm` 看到空的就不顯示那一排）。
        判準是 `Step.is_source()`（**沒有影像輸入的卡**）—— 不是一張寫死的
        名單，所以下一張入口卡不必記得回來註冊。
        """
        try:
            step_cls = get_step(node.step)
        except KeyError:                       # pragma: no cover
            return "", "", ""
        att_key = self._ATTACHMENT_CARDS.get(node.step)
        if att_key:
            att = next((a for a in scope.ATTACHMENTS if a.key == att_key), None)
            if att is None:                    # pragma: no cover — 表被改過
                return "", "", ""
            if self.dataset is None:
                note = att.needs
            else:
                n = sum(1 for it in getattr(self.dataset, "items", [])
                        if getattr(it, "sidecars", None))
                note = ("%d of %d defects have a label map"
                        % (n, len(self.dataset.items)) if n
                        else "No export attached to this lot yet")
            return att.title, note, "%s  %s" % (att.what, att.needs)
        if node.step in self._PAIR_CARDS:
            sid = str(node.params.get("source", "") or "").strip()
            return (self.DATA_SOURCE_LABEL, self._pair_note(sid),
                    "Choose the second lot to pair every defect with")
        if not step_cls.is_source():
            return "", "", ""
        return (self.DATA_SOURCE_LABEL, self._dataset_note(),
                "Choose the images this pipeline runs on")

    def _pair_note(self, source_id: str) -> str:
        """`pair_source` 那張卡旁邊那句話：**第二份**現在是什麼（F15）。"""
        if self.dataset is None:
            return "Load the main lot first"
        src = (getattr(self.dataset, "sources", None) or {}).get(source_id)
        if src is None:
            return "No second lot yet" + (" for '%s'" % source_id if source_id else "")
        name = str(getattr(src, "_d4t_name", "") or "")
        return "%s%s · %s · %d defects" % (
            (name + " · ") if name else "", source_id or "?",
            getattr(src, "kind", "?"), len(getattr(src, "items", []) or []))

    def _dataset_note(self) -> str:
        """現在載的是哪一份（鈕只說得出「可以換一份」）。"""
        ds = self.dataset
        if ds is None:
            return "No data loaded yet"
        name = str(getattr(self, "dataset_name", "") or "")
        no_klarf = getattr(ds, "klarf", None) is None
        return "%s%s · %d defects%s" % (
            (name + " · ") if name else "", getattr(ds, "kind", "?"),
            len(getattr(ds, "items", []) or []),
            " · no KLARF" if no_klarf else "")

    def _sync_source_action(self, node: Any) -> None:
        self.param_form.set_source_action(*self._source_action_for(node))

    # ---- GLV「我要量什麼」三選（PR-2 2a）----------------------------------
    def _sync_glv_intent(self, node_id: str, node: Any) -> None:
        """GLV 卡才有這一排；其他卡 `set_step` 已經清掉了。"""
        if node is None or getattr(node, "step", "") != "glv_stats":
            return
        wired = bool(self.model._glv_region_edges(node_id, "roi"))
        current = self.model.glv_intent(node_id)
        # **鈕 ＋ 這句話 = 這張卡真的在做的事**（F67 續）。要說什麼住在 model
        # （`glv_intent_note`）—— 這裡只負責畫。
        note = self.model.glv_intent_note(node_id)
        self.param_form.set_intent_row(
            "What to measure", GLV_INTENTS,
            current, note=note, enabled=wired)

    def _on_intent_chosen(self, intent: str) -> None:
        nid = self.selected_node
        if not nid:
            return
        if self.model.apply_glv_intent(nid, str(intent)):
            # 重新走一次 select_node：表單（roi/reference 那幾格）、preset
            # 列的勾選、儀表、畫布的線一次到位 —— 不各自手動刷新。
            self.select_node(nid)
        else:
            node = self.model.nodes.get(nid)
            self._sync_glv_intent(nid, node)   # 套不上：勾選擺回真實狀態

    # ---- 設定區的接線插槽（F68）--------------------------------------------
    def _on_slot_wire(self, param: str, name: str) -> None:
        """使用者在插槽的選單裡挑了一個上游的區域／影像流。

        **一行都不自己動 model**：找出誰產出那個名字，然後呼叫畫布拉線走的
        那兩支（`_connect_region` / `_connect`）—— 於是型別檢查、單一角色埠的
        「舊線讓位」、`rename_fallout` 那句話、undo、健檢，全部原樣繼承。
        找不到產出者就什麼都不做（選單本來就只列得出上游有的東西）。
        """
        nid = self.selected_node
        node = self.model.nodes.get(nid) if nid else None
        if node is None or not name:
            return
        try:
            spec = next(sp for sp in get_step(node.step).params
                        if sp.name == str(param))
        except (KeyError, StopIteration):
            return
        if spec.is_region_input():
            src = self.model.region_producer(name, before_node=nid)
            if src:
                # **走 `_connect` 那條共用的路**（U6）：以前這裡直接呼叫
                # `_connect_region`，於是「已經接過了」與型別守門那幾關在這條
                # 路上是缺的 —— 同一個動作兩個入口，而只有一個有守門。
                self._connect(src, nid, name, str(param))
            return
        src = self.model.stream_producer(name, before_node=nid)
        if src:
            self._connect(src, nid, name, str(param))

    def _on_slot_show(self, param: str) -> None:
        """「在畫布上指給我看」—— 把**這一格接的那張卡**在畫布上亮起來。

        走的是 `_on_slot_wire` 找來源的**同一支**（`stream_producer` /
        `region_producer`），所以「選單裡挑的那個名字」與「畫布上指的那張卡」
        永遠是同一個答案。一個字都不改 model。

        ⚠ 這支以前寫的是 `self.canvas.show_card_ghosts(nid)`，而兩個名字都錯：
        主視窗的畫布叫 `self.pipeline`（`self.canvas` 從來沒有存在過，所以
        點下去只有一串 AttributeError），而 `show_card_ghosts` 吃的是一個
        **圖元**、畫的是「用名字吃的那幾個數字」的淡線 —— 影像流與區域的線
        是真的線，本來就畫在那裡，要指的是它的**另一端**。
        """
        nid = self.selected_node
        node = self.model.nodes.get(nid) if nid else None
        if node is None:
            return
        try:
            spec = next(sp for sp in get_step(node.step).params
                        if sp.name == str(param))
        except (KeyError, StopIteration):
            return
        names = [n.strip() for n in
                 str(node.params.get(str(param), "") or "").split(",")]
        find = (self.model.region_producer if spec.is_region_input()
                else self.model.stream_producer)
        srcs = []
        for name in names:
            src = find(name, before_node=nid) if name else ""
            if src and src not in srcs:
                srcs.append(src)
        if not srcs:
            return
        for view in self._canvases():
            view.reveal_cards(srcs)

    def _on_source_requested(self) -> None:
        """入口卡上那顆鈕：附加檔直接開，資料那幾張開一張選單。

        **選單的每一列都是 `scope.INPUT_SOURCES` 的一列** —— 那張表仍然是入口
        的唯一定義（F11 Input-5），這一輪只是換了它長在哪裡。
        """
        nid = self.selected_node
        node = self.model.nodes.get(nid) if nid else None
        if node is None:
            return
        att_key = self._ATTACHMENT_CARDS.get(node.step)
        if att_key:
            getattr(self, "_on_open_%s" % att_key)()
            return
        if node.step in self._PAIR_CARDS:
            self._on_open_pair_source(nid)
            return
        menu = QMenu(self)
        for src in scope.INPUT_SOURCES:
            act = QAction(src.title, menu)
            tip = src.what
            if not src.has_klarf:
                tip += ("  There is no KLARF here, and no KLARF means no "
                        "coordinates and no write-back - CSV and Excel "
                        "reports still work.")
            act.setToolTip(tip)
            act.triggered.connect(getattr(self, "_on_open_%s" % src.key))
            menu.addAction(act)
        btn = self.param_form.source_button()
        menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))

    # ---- 核心大小畫在影像上（F11 Enhance-UI-A）-----------------------------
    def _kernel_extent(self) -> Tuple[Optional[float], str]:
        """選取的卡片上那個「鄰域邊長」參數現在是多少（沒有就 ``(None, "")``）。

        只認 ``ParamSpec.extent``（明講的旗標），不認 ``unit == "px"`` ——
        後者有一半不是鄰域範圍（條紋間距、框線粗細、離邊界的留白），拿一個方框
        去表示那些會讓**影像**說謊，而那跟畫布說謊是同一件事。

        被 ``show_when`` 藏起來的不算：使用者看不到那一列的時候，畫面上不該有
        一個跟著它變的方框。
        """
        node = self.model.nodes.get(self.selected_node or "")
        if node is None:
            return None, ""
        try:
            specs = get_step(node.step).params
        except KeyError:
            return None, ""
        for spec in specs:
            if not getattr(spec, "extent", False):
                continue
            if not spec.visible_for(node.params):
                continue
            try:
                n = float(node.params.get(spec.name, spec.default))
            except (TypeError, ValueError):
                continue
            # 1 = 不濾波（`denoise` 的 ksize=1 就是原樣回傳），畫一個 1px 的框
            # 只會變成畫面正中央一個看不懂的點。
            if n <= 1.0:
                return None, ""
            return n, "%d px" % int(round(n))
        return None, ""

    def _refresh_kernel_hint(self) -> None:
        """兩張預覽圖都畫 —— 並排比對時使用者比的是「這個框 vs 畫面上的結構」，
        而那個判斷在左右兩邊都要做。"""
        px, label = self._kernel_extent()
        for view in (self.image_view, self.image_view_b):
            if px is None:
                view.clear_kernel_hint()
            else:
                view.set_kernel_hint(px, label)

    # ---- 設定面板：跟著「有沒有東西可以設定」走（F13-1）--------------------
    def _sync_params_pane(self) -> None:
        """選了卡片就把收起來的工作台打開；**取消選取不收**（F100）。

        影像住在工作台裡，收掉它等於把影像藏起來。F13-1 那條「沒選卡片時設定
        區收起來」的理由（那塊空白壓到畫布）在新版面上不成立：畫布現在吃滿寬
        度，高度有保底。

        兩個例外照舊：分數面板自己開（`show_score_page`）；使用者切到 Build 的
        時候不跟他搶（U5）。
        """
        if self.stack.currentWidget() is not self.param_form:
            return
        self.layout_modes.on_selection(self.selected_node is not None)

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

    def _on_add_menu(self, x: float, y: float,
                     pick: Optional[str] = None) -> Optional[str]:
        """空白處按右鍵 → 整個卡片庫的選單（F99 P1-1）；挑了就放在那裡。

        ``pick`` 是測試用的：直接指定挑哪一張，不開選單。內容在 `card_menu`。
        """
        keys = self.library.step_keys()
        if pick is not None:
            self._on_card_dropped(str(pick), float(x), float(y))
            return self.selected_node
        from PySide6.QtGui import QCursor
        menu = card_menu.build_menu(
            self, keys, lambda k: self._on_card_dropped(k, float(x), float(y)),
            title="Add a card here")
        card_menu.pick_at(menu, QCursor.pos())
        return None

    def _on_link_dropped(self, src: str, kind: str, stream: str,
                         x: float, y: float,
                         pick: Optional[str] = None) -> Optional[str]:
        """線拖到空白處放開 → 只列接得上的卡；挑了就加在那裡並把線接上
        （F99 P1-1）。線是使用者拉的，所以這不是「加卡順手接線」。
        """
        keys = card_menu.compatible(self.library.step_keys(), kind)

        def add(step_key: str) -> None:
            self._on_card_dropped(str(step_key), float(x), float(y))
            nid = self.selected_node
            if not nid:
                return
            dst_in = card_menu.input_param_for(str(step_key), kind)
            self._on_edge_added(str(src), nid, str(stream), dst_in)

        if pick is not None:
            add(str(pick))
            return self.selected_node
        from PySide6.QtGui import QCursor
        menu = card_menu.build_menu(
            self, keys, add, flat=True,
            title="Connect “%s” to a new card" % (stream or kind))
        card_menu.pick_at(menu, QCursor.pos())
        return None

    def params_open(self) -> bool:
        """工作台現在攤開著嗎（**明確狀態**，見 `WorkbenchLayout.open`）。

        F100 之前這一支問的是「設定區攤開著嗎」；現在設定區、儀表板、影像同住
        工作台，所以它問的是那整塊。Build 模式下恆為 False。
        """
        return bool(self.layout_modes.open)

    def set_params_open(self, on: bool) -> bool:
        """攤開／收起工作台。Build 模式下什麼都不做（U5）。"""
        return self.layout_modes.set_open(on)

    # ---- Build / Tune 兩種模式（U5 → F100）----------------------------------
    LAYOUT_MODES = LAYOUT_MODE_NAMES

    def layout_mode(self) -> str:
        """現在是哪一種版面（**明確狀態**，不去量 splitter）。"""
        return self.layout_modes.mode

    def set_layout_mode(self, mode: str, remember: bool = True) -> str:
        """換版面。回真的套上去的那一個。

        兩種模式共用同一份畫布（U5 的驗收條件：切模式不重建畫布，node id 與
        選取狀態原封不動）。幾何在 `ui/workbench.py`：

        * **Build** —— 工作台收到 0，畫布吃滿右邊整塊。
        * **Tune** —— 工作台開著（影像住在裡面），畫布保底、預設 40%。
        """
        use = self.layout_modes.apply(mode, remember=remember)
        self._sync_layout_button()
        # 換到 Build 的時候把畫布重新 fit 一次：位子變大了而使用者要的正是
        # 「看全貌」，停在原本的縮放等於那顆鈕只做了一半。
        if use == "build":
            self.pipeline.fit_later()
        return use

    def toggle_layout_mode(self) -> str:
        """Build ⇄ Tune（工具列那顆鈕與 Ctrl+B）。"""
        return self.set_layout_mode(
            "tune" if self.layout_mode() == "build" else "build")

    def _sync_layout_button(self) -> None:
        """鈕上寫的是**按下去會去哪裡**，不是現在在哪裡。

        寫現在在哪裡的話，使用者要先讀懂「這是狀態不是動作」才知道按了會怎樣
        —— 而一顆工具列的鈕沒有那麼多解釋的空間。
        """
        # 這顆鈕住在**畫布的縮放列上**，不在工具列（見 `_wire_canvas`）——
        # 工具列在 1366×768 上沒有位子了，而它控制的就是這塊畫布。
        btn = (self.pipeline.zoom_buttons() or [None])[-1] \
            if hasattr(self.pipeline, "zoom_buttons") else None
        if btn is None:
            return
        going = "Tune" if self.layout_mode() == "build" else "Build"
        # 同 `_refresh_results_button`：它繞過 `_tool_button`，要自己翻。
        # **模式的名字（Build / Tune）不翻** —— 它們是 `Ctrl+B` 的兩個檔位，
        # 跟卡片名同一類：使用者跟同事講的是那兩個字。
        # ⚠ 它是一顆**只有圖示**的鈕（縮放列上那一排），所以話只能講在
        # tooltip 上 —— 那也是它 accessible name 的來源。
        why = strings.tr(
            "canvas fills the column, for wiring and seeing the whole thing"
            if going == "Build" else
            "canvas on top, settings below, for tuning parameters")
        tip = strings.tr("Switch to %s layout (Ctrl+B) — %s") % (going, why)
        btn.setToolTip(tip)
        btn.setAccessibleName(tip)


    def _canvases(self) -> List[PipelineCanvas]:
        """現在活著的每一份畫布。

        **恆為一份**（U5 的驗收條件）。它以前會是兩份（主視窗 ＋ 彈出視窗），
        而那正是每一個訊號要接兩次、每一次重畫要記得兩邊都畫的原因。這一支
        留著是因為呼叫端寫的是「對每一份畫布做這件事」—— 那句話仍然是對的，
        而且哪天真的又需要第二份時，改的地方只有這裡。
        """
        return [self.pipeline]

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
                  self.feature_panel, self.library, self.pipeline, self.gallery):
            w.update()

    def remove_decision(self) -> bool:
        """把整個判定拿掉（畫布上判定區右上角那顆 ✕，2026-08-25）。

        使用者：「ADC 也要能在原畫布上拖曳 移除」。

        **先問過**：底下掛著使用者自己畫的整棵樹，而一顆 ✕ 的重量看起來跟
        刪一張卡一樣 —— `_remove_step` 對「yes 邊掛著一整個子樹」講過同一句話。
        復原回得來（`use_decide` 自己會 `_push_undo`），但「一個 ✕ 把三層樹
        默默吃掉」不是一顆按鈕該有的重量。
        """
        m = self.model
        if getattr(m, "decide", None) is None:
            return False
        from .tree_scene import display_tree, layout_cells

        n_class = sum(1 for c in layout_cells(display_tree(m.decide), m.decide)
                      if c.get("kind") == "leaf")
        answer = QMessageBox.question(
            self, "Remove the decision?",
            "This takes the whole decision off the canvas - %d class%s and "
            "every question that sorts into them.\n\nUndo brings it back."
            % (n_class, "" if n_class == 1 else "es"),
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return False
        m.use_decide(False)
        self.show_param_page()
        self._status("Decision removed. Undo brings it back.")
        return True

    def show_score_page(self) -> None:
        """切到分數編輯頁（順便刷新特徵下拉）。"""
        self._refresh_feature_combo()
        self._sync_score_widgets()
        self.stack.setCurrentWidget(self.score_pane)
        self.set_params_open(True)   # 分數面板本來就是「我要編」

    def show_param_page(self) -> None:
        self.stack.setCurrentWidget(self.param_form)

    # ---- 分流（F23 期2）----------------------------------------------------
    def _refresh_route_switcher(self) -> None:
        """工具列的 route 下拉：跟 model 的 route 清單同步；單 route 收起來。"""
        keys = list(self.model.route_keys())
        show = len(keys) > 1
        for act in getattr(self, "_route_actions", []):
            act.setVisible(show)
        if not show:
            return
        current = [self.route_combo.itemText(i)
                   for i in range(self.route_combo.count())]
        want = sorted(keys)
        if current != want:
            self.route_combo.blockSignals(True)
            self.route_combo.clear()
            for k in want:
                self.route_combo.addItem(k)
            self.route_combo.blockSignals(False)
        i = self.route_combo.findText(self.model.kind)
        if i >= 0 and self.route_combo.currentIndex() != i:
            self.route_combo.blockSignals(True)
            self.route_combo.setCurrentIndex(i)
            self.route_combo.blockSignals(False)

    def _on_route_combo(self, index: int) -> None:
        self.switch_route(str(self.route_combo.itemText(int(index))))

    def switch_route(self, key: str) -> bool:
        """切到另一條 route 編輯（畫布跟著換）。

        做法是「收回去再拿出來」（`to_recipe` → `from_recipe`）—— 正在編的
        改動全部保住（`to_recipe` 會把其他 route 原樣合併回去）。代價是
        **undo 堆疊重來**：復原是編輯這一條 route 的歷史，切走再切回來是
        兩段不同的編輯。
        """
        key = str(key)
        if key == self.model.kind or key not in self.model.route_keys():
            return False
        dirty = self.model.dirty
        m = RecipeModel.from_recipe(self.model.to_recipe(), kind=key)
        m.dirty = dirty
        self._apply_model(m)
        self._status("Route: %s" % key)
        return True

    def _fill_route_fields(self) -> None:
        """`route_by` 的那一欄要進每一顆的 `fields`（預覽逐顆解 route 要讀它）。

        跟 `run_batch` 同一套規矩：只在有顆缺這一欄時動手，補「現有欄位 ∪
        這一欄」（`fill_fields` 是整份換掉，只補一欄會洗掉 carry 進來的）。
        欄位不存在時**在這裡就講**（手上有 KlarfDoc，答得出它有哪些欄）。
        """
        rb = getattr(self.model, "route_by", None)
        if rb is None or self.dataset is None:
            return
        from d4t.core.ingest.dataset import (
            columns_of, fill_fields, missing_columns_of,
        )

        if getattr(self.dataset, "klarf", None) is None:
            self._status("route_by needs KLARF columns, and this data has "
                         "no KLARF - every defect will fail to route.",
                         "error")
            return
        absent = missing_columns_of(self.dataset, [rb.column])
        if absent:
            self._status("route_by points at a column this KLARF does not "
                         "have: %s. It has: %s"
                         % (", ".join(absent),
                            ", ".join(columns_of(self.dataset))), "error")
            return
        col = str(rb.column).strip().upper()
        items = list(getattr(self.dataset, "items", []) or [])
        if any(col not in (getattr(it, "fields", None) or {})
               for it in items):
            have: set = set()
            for it in items:
                have.update((getattr(it, "fields", None) or {}).keys())
            fill_fields(self.dataset, sorted(have | {col}))

    def _follow_defect_route(self) -> None:
        """預覽跟著這一顆走（F23 §6-2）：看 defect 12 時，畫布自動切到它真正
        走的 route —— 不做這個就是 F10 那批「畫布說謊」的重演。"""
        rb = getattr(self.model, "route_by", None)
        if rb is None or self.dataset is None:
            return
        item = self._current_item()
        if item is None:
            return
        from d4t.core.pipeline import resolve_route

        self._fill_route_fields()
        route, _value, _how = resolve_route(self.model, item,
                                            str(self.dataset.kind))
        if route and route != self.model.kind \
                and route in self.model.route_keys():
            self.switch_route(route)

    def _adopt_threshold_as_a_tree(self) -> bool:
        """開一份**用門檻分兩類**的舊 recipe → 當場變成判定樹（F25，使用者
        2026-08-24：「二元門檻的 UI 完全拿掉」）。

        只在**讀檔案**這條路上做，而且只在真的有 score 表達式時做 ——
        空白的新 recipe 不會被塞一棵樹（那是 ADC 卡的工作）。

        ⚠ 這是 **UI 層的遷移**，不是引擎的：`Recipe.load` 一個位元都沒動，
        CLI 照舊跑那份檔案的 `score`（黃金值因此不受影響）。

        ⚠⚠ **2026-08-26 起這一段多了一個後果**，而它以前不存在：存檔功能
        回來了，所以使用者按一下 `Ctrl+S`，磁碟上那份**門檻 recipe 就變成
        一份判定樹 recipe**。這裡以前寫的是「而 Studio 現在又存不了檔，
        所以磁碟上的東西不會被改寫」—— 那句話現在是假的，留著就是這個 repo
        最怕的那種漂移（`CLAUDE.md` §0）。

        會不會不小心？**不會安靜地發生**：載入時狀態列已經講過一次
        「Its threshold is now the first question of the decision tree」，
        而覆寫原檔是使用者自己按的 `Ctrl+S`。存出跟畫面上不一樣的東西才是
        說謊 —— 所以正確的行為就是照畫面存。想留住舊檔就 `Ctrl+Shift+S`
        另存一份（那也是每個編輯器的慣例）。

        ⚠ 一個誠實的落差：`use_decide` 產出的規則是 ``expr >= threshold``，
        而老路是 ``score < threshold`` 判 below —— 兩者在**分數是 NaN** 的
        時候會分到不同的 bin（老路進 above、新的進 otherwise）。留 ``>=``
        是因為它讀起來才是正著的（「大於就是這一類」）；NaN 的分數本來就是
        一份算壞了的 recipe。
        """
        m = self.model
        if getattr(m, "decide", None) is not None:
            return False
        # **常數的 score 不是門檻**（U1，2026-08-24）。這裡以前只問「是不是
        # 空的」，於是一份 `score.expr` 是 `"0"` 的檔案打開之後會被塞一棵
        # `0 >= 0` 的樹 —— 而那句「只在真的有 score 表達式時做」的本意
        # 正是不要發生這件事。見 `viewmodel.is_a_constant_expression`。
        if is_a_constant_expression(getattr(m, "expr", "")):
            return False
        m.use_decide(True)
        m.ensure_tree()
        m.dirty = False          # 使用者什麼都還沒做，關窗不要問他要不要存
        m.clear_history()        # 「復原」不該把他退回一個看不到編輯器的狀態
        return True

    def add_decision(self) -> bool:
        """把判定樹放上畫布，並開始編第一步（F25）。

        使用者 2026-08-24 定調的兩件事都在這裡：**加 ADC 卡＝畫布上直接
        有東西**（不是勾一個選項），而且**一進去就是多類別**（「原來的
        根本不會用到」）。二元門檻沒有被拿掉 —— 它變成舊 recipe 的樣子，
        而換過來的時候現有的門檻會變成樹的第一個問題（`use_decide`）。
        """
        from d4t.core.pipeline.recipe import TreeLeaf

        m = self.model
        with m.compound("add decision"):
            if getattr(m, "decide", None) is None:
                m.use_decide(True)      # 現有門檻 → 第一條規則（不丟東西）
            m.ensure_tree()             # 規則清單 → 等價的樹
            if isinstance(m.tree_node(""), TreeLeaf):
                # 整棵樹只有一片葉子（這份 recipe 還沒有任何判定）——
                # 給一個真的問得出東西的起手問題，不是一格空白。
                m.split_tree_leaf("")
            # **建議一律問一次**（U1，2026-08-24）。這裡以前縮在上面那個
            # `if` 裡面，所以一個**已經是 TreeStep** 的根就跳過建議 ——
            # 而全新 recipe 的根正好是那樣（佔位值 `"0"` 被翻成 `0 >= 0`）。
            # `suggest_question` 自己會判斷該不該動：真的問題它不碰，
            # 空的或常數的它才填。
            self.tree_pane.set_rows(self.trial_results or [])
            self.tree_pane.suggest_question("")
        self._on_tree_step_clicked("")
        # **看得到才算在畫布上**：判定區長在所有卡片的右邊，而畫布這時多半
        # 停在左半邊 —— 不 fit 的話使用者按了 ADC 卡，畫面上什麼都沒發生。
        for view in self._canvases():
            view.fit()
        self._status("Decision: the tree is on the canvas - edit this step "
                     "on the right, or click another diamond.")
        return True

    def _on_tree_step_clicked(self, path: str) -> None:
        """畫布上點了判定樹的一步／一類（F24 ③），或面板要求跳到另一步。

        `rules` 模式先無損翻成樹（`ensure_tree`）—— 編輯動作只有樹的形狀
        表達得了「yes 接另一步」。
        """
        if getattr(self.model, "decide", None) is None:
            return
        self.model.ensure_tree()
        info = self._decision_info()
        self.tree_pane.set_features(self.model.labelled_features())
        self.tree_pane.set_counts(None if not info else info.get("counts"))
        # 導引式問題的滑桿範圍與「幾顆說 yes」吃這一批的結果（F25）。
        self.tree_pane.set_rows(self.trial_results or [])
        self.tree_pane.show_path(str(path))
        self.stack.setCurrentWidget(self.tree_pane)
        self.set_params_open(True)
        # 儀表板不是這一步的（F99 P1-7）：淡掉、說出它是誰的。
        last = self.selected_node or ""
        self.gauge_note.setText(
            ("showing “%s” — the card picked last" % last) if last else "")
        self.bottom_stack.setEnabled(False)
        for view in self._canvases():
            view.set_tree_selected(str(path))
        # 編樹的時候預覽要跑到底（連判定），路徑才亮得起來（2026-09-09）。
        if not getattr(self, "_tree_focus", False):
            self._tree_focus = True
            self._schedule_preview()

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
            says = self.model.set_param(node_id, str(name), value)
        except ParamError as e:
            self.param_form.show_error(str(name), str(e))
            self._status(str(e))
        else:
            self.param_form.clear_errors()
            self._autofill_output_prefix(node_id, str(name), value)
            self._after_pair_param(node_id, str(name))
            # 在設定區少勾一個統計量也是改名（那個數字從此不存在）——
            # 跟拉線同一件事，所以講同一句話。
            self._say_fallout(says)
            self._after_carry_param(node_id, str(name))
            # 拖滑桿的時候框要跟著變 —— 那正是這個輔助的全部意義（F7-8：
            # 使用者是一邊看影像一邊決定值的）。
            self._refresh_kernel_hint()

    def _after_pair_param(self, node_id: str, name: str) -> None:
        """配對卡改了 `source` / `carry` / 排名欄位之後要跟上的兩件事（F15-2）。

        **不重建表單**：使用者可能正在 “Source name” 那一格打字，而重建會把
        游標搶走 —— `set_dynamic_choices` 只換內容，還會跳過有游標的那一格。

        排名那兩格（F33）跟 `carry` 是同一件事：它們指名的欄位要跟著複製過來
        （`columns_for_source` 的聯集），少了重灌那一步，剛挑好的排序欄在
        `fields` 裡是空的。``rank_desc`` 不在名單裡 —— 它不指名任何欄位。
        """
        node = self.model.nodes.get(str(node_id))
        if node is None or node.step not in self._PAIR_CARDS:
            return
        if name not in ("source", "carry", "rank_within", "rank_by"):
            return
        self._sync_pair_fields(str(node.params.get("source", "") or ""))
        if name == "source" and self.selected_node == str(node_id):
            self.param_form.set_dynamic_choices(self._dynamic_choices_for(node))

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
        if "," in wanted:
            # **接了兩個以上的區域就不要自動命名**（F13-⑥）：那時候每個數字
            # 本來就會帶自己的區域名（`epi_glv_mean` / `mg_glv_mean`），
            # 再加一個共同前綴只會變成 `epi_mg_epi_glv_mean`。
            return
        try:
            self.model.set_param(node_id, "output_prefix", wanted)
        except ParamError:
            return                       # 區域名不能當變數名 -> 安靜跳過
        self.param_form.set_step(
            get_step(node.step).describe(), node.params,
            self.model.available_streams(before_node=node_id),
            self.model.available_regions(before_node=node_id),
            self._dynamic_choices_for(node))
        self._status("Results from this card will be named “%s_…” so they do "
                     "not collide with another card measuring a different "
                     "region." % wanted)

    # ==================================================================== #
    # 分數編輯
    # ==================================================================== #

    # ---- 直方圖門檻線 -----------------------------------------------------
    def _on_threshold_changed(self, value: float) -> None:
        """拖曳中：**只**重算 bin 數（秒回），絕不寫 model、不重跑。"""
        self._refresh_bin_summary(float(value))
        self._status("Threshold %.3g (applied when you release the mouse)" % float(value))

    def _on_threshold_committed(self, value: float) -> None:
        """放開滑鼠：這時才寫回 model（會觸發刷新與預覽）。"""
        self.model.set_threshold(float(value))
        # baseline 那一行也跟著這個門檻（X1）。**在放開的時候，不是拖曳中**：
        # 拖曳中那條路是「秒回」的（只重算 bin 數），而算一次 baseline 是一趟
        # 完整的 `summarize` —— 直方圖底下那行正確率已經在跟著動了，
        # 這一行慢半拍不會少講任何事。
        self._publish_run_snapshot(float(value))
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
        self._pending_dataset_name = os.path.basename(path)
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync(path, tiff)
            except Exception as e:  # UI 邊界，一律回報
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
        self._pending_dataset_name = os.path.basename(path)
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync_stack(path, n)
            except Exception as e:  # UI 邊界，一律回報
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
        self._pending_dataset_name = os.path.basename(d.rstrip("/\\"))
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync_folder(d)
            except Exception as e:  # UI 邊界，一律回報
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

    def load_image_path(self, path: Any, sync: bool = False) -> bool:
        """載入**一個影像檔**（F85）—— `load_folder_path` 的單檔版。

        沒有 KLARF、沒有座標，那一張圖就是唯一的一顆 defect。資料集標籤上
        仍然寫 ``folder``（`ingest.load_image_file` 的 docstring 有理由）。
        """
        f = str(path)
        if not os.path.isfile(f):
            self._status("Not a file: %s" % f)
            return False
        self._pending_dataset_name = os.path.splitext(os.path.basename(f))[0]
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync_image_file(f)
            except Exception as e:  # UI 邊界，一律回報
                self._status("Could not load image: %s: %s"
                             % (type(e).__name__, e), "error")
                return False
            return self._on_dataset_loaded(ds)
        if not self.dataset_worker.start_image_file(f):
            self._status("A dataset is already loading — please wait.")
            return False
        self._progress_busy("Loading %s…" % os.path.basename(f))
        self._status("Loading image: %s" % f)
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
        # Load 卡的 `carry` 點名的 KLARF 欄位要跟著這一份重填（F16）——
        # 換一份資料 = 那幾欄的值全變了。忘了填的下場是**上一份的欄位值**
        # 留在這一份的每一顆上，跑得完、有數字、而且是別人的。
        self._carry_filled = None
        self._carry_main_columns()
        # 分流（F23 期2）：編輯區塊的欄位下拉要吃這一份的欄名；route_by 的
        # 那一欄也趁現在填進每一顆（換一份資料＝值全變了，同 carry 的理由）。
        from d4t.core.ingest.dataset import columns_of as _cols

        self.route_box.set_columns(_cols(dataset))
        self._fill_route_fields()
        # 入口卡上要印出**現在載的是哪一份**（F14-1）。名字在請求的那一刻就
        # 知道了，但要等載成功才採用 —— 開錯一個檔不會讓卡片上的名字先變。
        self.dataset_name = str(getattr(self, "_pending_dataset_name", "") or "")
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
        self.pipeline.set_run_status({})       # 換一批資料，舊的執行狀態不算數
        self._refresh_results_button()
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
        added = self._adopt_source_for(ds_kind)

        # `channel_map` 的表格要照「這批資料一顆有幾張圖」排列數（F11）。
        # 那是資料的事實，所以在這裡講一次，不是每次選卡片時重新猜。
        self.param_form.set_image_count(
            len(getattr(items[0], "images", {}) or {}) if items else 0)

        self._update_defect_label()
        self._update_action_states()
        self._progress_done()
        msg = "Loaded %d defects (input type %s)" % (
            len(items), getattr(dataset, "kind", "?"))
        if added:
            msg += "   · added “%s” for it" % added
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

    def _adopt_source_for(self, kind: str) -> str:
        """畫布是空的 → 補上**這種資料該用的那一張**載入卡（回它的顯示名）。

        為什麼開窗時不放、載資料時才放（F11 Enhance-4）
        ----------------------------------------------
        使用者：「一開始進去 GUI 畫面時，Load image 卡片改成預設沒有（user 可以
        選擇要 Load images or Load one image），add 才會出現。」他要的是**開窗時
        不要替他決定** —— 因為 Input-4 之後有兩張載入卡，而預先放一張就是替他決定
        了他還沒決定的事（而猜錯的那一半在畫布上看起來完全正常）。

        但**載入資料的那一刻，「哪一張」已經不是猜的**：`ingest` 判別出來的 kind
        就是答案（`ebi_patch`/`tiff_stack` → Load images；`rsem`/`folder` →
        Load one image）。那時候不放才是把一個已知的答案丟給使用者自己拼。
        所以規則是：**空白畫布才補，而且把補了什麼講出來**（狀態列）。

        只在**完全空白且沒動過**的時候補：使用者已經蓋了一條 pipeline 的話，
        那是他的東西 —— 這一段一個字都不准動它。
        """
        if self.model.node_order or self.model.dirty:
            return ""
        want = RecipeModel.starter_step_for(str(kind or ""))
        try:
            nid = self.model.add_step(want)
        except KeyError:                 # pragma: no cover — 卡片庫壞了才會發生
            return ""
        # 補上來的那張卡不算「使用者做過的一步」：Ctrl+Z 不該把它退掉，關窗也
        # 不該因此問「要存檔嗎」（同 `RecipeModel.starter` 的理由）。
        self.model.dirty = False
        self.model.clear_history()
        self.select_node(nid)
        try:
            return str(get_step(want).label)
        except KeyError:                 # pragma: no cover
            return want

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
        # 分流（F23 期2）：這一顆的欄位值與它真正走的 route **常駐在標籤上**
        # —— 畫布自動切了 route，這一行就是「為什麼畫布剛剛跳了」的答案。
        route_bit = ""
        rb = getattr(self.model, "route_by", None)
        if rb is not None and 0 <= i < len(items):
            from d4t.core.pipeline import resolve_route

            route, value, _how = resolve_route(self.model, items[i],
                                               str(self.dataset.kind))
            route_bit = " · %s=%s → %s" % (
                rb.column, value or "?",
                ("route “%s”" % route) if route else "no route (fails)")
        self.defect_label.setText(
            "%s · defect %d / %d%s%s" % (getattr(self.dataset, "kind", "?"),
                                         i + 1, len(items),
                                         " · no KLARF" if no_klarf else "",
                                         route_bit))
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
        # 分流：先跟著這一顆切 route（切了會整個 _refresh_all），標籤才會寫出
        # 它真正走的那一條。
        self._follow_defect_route()
        self._update_defect_label()
        # 徽章上「現在這一顆走哪一條」要跟著換（F25-B）。
        info = self._prefilter_info()
        for view in self._canvases():
            view.set_prefilter(info)
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
        except Exception as e:  # UI 邊界
            self._status("Could not load recipe: %s: %s" % (type(e).__name__, e), "error")
            return False
        # 舊格式**升級了就要說**（U17）：畫布上多出來的線與拆開的卡是遷移補的，
        # 而使用者只會看到「這跟我上次存的不一樣」。讀原始 JSON 再比一次是為了
        # 拿到 `Recipe.load` 已經丟掉的那一半（版本號與原本的線）。
        upgraded = self._describe_upgrade(path, recipe)
        kind = None
        ds_kind = str(getattr(self.dataset, "kind", "")) if self.dataset else ""
        if ds_kind and ds_kind in recipe.routes:
            kind = ds_kind
        self._apply_model(RecipeModel.from_recipe(recipe, kind=kind))
        converted = self._adopt_threshold_as_a_tree()
        self.recipe_path = path
        # ⚠ **要在這裡再刷一次**：`_apply_model` 已經 refresh 過了，但那時候
        # `recipe_path` 還是舊的 —— 存檔鈕的 tooltip 要講「存回哪一個檔案」，
        # 而它會停在載入前的答案。
        self._update_action_states()
        n = len(self.model.node_order)
        # 版本落差要在**載入的那一刻**講，不是等他按了試跑才從 lint 冒出來 ——
        # 那時候他已經在調參數了，而該做的是先更新程式（見 recipe.version_skew）。
        skew = version_skew(getattr(recipe, "app_version", ""))
        if skew:
            self._status(skew, "error")
        elif converted:
            # 轉過去了就**講出來** —— 使用者存的是一個門檻，打開看到的是一棵
            # 樹，不說的話那是「這個工具把我的東西改掉了」。
            self._status("Loaded recipe “%s” (%d steps). Its threshold is now "
                         "the first question of the decision tree on the "
                         "canvas." % (self.model.recipe_id, n))
        elif upgraded:
            # **一句常駐訊息 ＋ 一個看細節的入口**（U17）。存檔會把它寫成新
            # 格式，所以這句話要在存檔之前出現，不是之後。
            self._status_next_step(
                "Loaded recipe “%s” (%d steps) — this file is an older format "
                "and was upgraded: %s. Saving will write the new format."
                % (self.model.recipe_id, n, ", ".join(upgraded)),
                "What changed", lambda: self._show_upgrade_detail(upgraded),
                tip="List what the upgrade changed on the canvas")
        else:
            self._status("Loaded recipe “%s” (%d steps, route %s)"
                         % (self.model.recipe_id, n, self.model.kind))
        # route_by 存在時 route 鍵是任意字串、覆蓋 kind 選路（F23 §4.2）——
        # 「沒有這個 kind 的 route」對它不是問題，別嚇人。
        if ds_kind and ds_kind not in recipe.routes \
                and getattr(recipe, "route_by", None) is None:
            self._status("Loaded recipe “%s”, but it has no '%s' route — "
                         "preview and trial runs will fail."
                         % (self.model.recipe_id, ds_kind))
        self.refresh_preview(sync=sync, force=False)
        return True

    @staticmethod
    def _describe_upgrade(path: Any, recipe: Any) -> List[str]:
        """這份檔案被升級了什麼。讀不到原始 JSON 就回空 —— **不准擋載入**。

        recipe 已經載好了；這裡只是為了說一句話而多讀一次檔。所以任何失敗都
        安靜地退成「沒話說」，而不是把一個載得起來的 recipe 變成一個錯誤。
        """
        import json

        try:
            with open(str(path), "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:  # 只是一句提示
            return []
        try:
            return list(describe_migration(raw, recipe))
        except Exception:  # 同上
            return []

    def _show_upgrade_detail(self, upgraded: List[str]) -> None:
        """「改了什麼」點開來的細節。

        用 `QMessageBox` 而不是一塊新面板：這是**讀完就走**的東西，而
        `docs/ARCHITECTURE.md` 那條視窗規則說得很清楚 —— 不需要一邊看著它一邊
        動主視窗的，就是 modal。
        """
        QMessageBox.information(
            self, "Recipe upgraded",
            "This recipe was saved by an older version of d4t. Opening it "
            "upgraded the file's shape to the current one:\n\n  · %s\n\n"
            "Nothing about what it measures changed — the canvas now draws "
            "connections that used to be implied. Saving writes the new "
            "format; the file on disk is untouched until you do."
            % "\n  · ".join(upgraded))

    def save_recipe_path(self, path: Any) -> bool:
        """把目前的 model 寫成一份 recipe JSON。回「真的存下去了嗎」。

        測試接的是這一支（不是那個檔案對話框）—— 要驗的是「存出來的東西對
        不對」，不是 ``QFileDialog`` 長什麼樣。
        """
        path = str(path)
        if not self.model.node_order:
            self._status("The pipeline is empty — nothing to save.")
            return False
        try:
            self.model.to_recipe().save(path)
        except Exception as e:  # UI 邊界
            self._status("Could not save: %s: %s" % (type(e).__name__, e),
                         "error")
            return False
        self.recipe_path = path
        self.model.dirty = False
        self.model.end_coalescing()      # 存檔＝一段編輯結束（見 viewmodel）
        self._update_action_states()     # 星號、鈕的 tooltip 一起跟上
        self._status("Saved: %s" % path)
        return True

    def _apply_model(self, model: RecipeModel) -> None:
        """換掉 model 並重接所有顯示（listener 一定要重掛）。"""
        self.model = model
        self.model.add_listener(self._on_model_changed)
        # 草稿那一條也要重掛 —— 少了它，載完一份 recipe 之後的每一個改動都
        # 不再進草稿，而畫面上沒有任何差別（U4）。
        self.autosave.rebind()
        # 判定面板抓著 model 的參考（它直接寫進去），所以**換 model 一定要
        # 跟著換**。漏掉的話它會安靜地繼續編輯上一份 recipe 的判定段，而畫面
        # 上唯一的線索是「那一格的數字沒跟著載進來的 recipe 動」。
        self.decide_panel.set_model(model)
        self.tree_pane.set_model(model)   # 同一個理由：它也直接寫 model
        self.route_box.set_model(model)   # 同上（F23 期2）
        self._refresh_route_switcher()
        self._fill_route_fields()
        self.selected_node = None
        self._user_stream = None
        for view in self._canvases():
            view.set_selected(None)
            view.set_tree_selected(None)
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
        if self._preview_whole_route():
            upto = None                  # Output 卡／判定樹：跑到底，連判定
        # 分流（F23 期2）：`kind` 是**資料的身分**（load 卡讀
        # `meta["_dataset_kind"]`），route 由 `run_defect` 逐顆自己解。
        # route_by 存在時 model.kind 是一個 route 鍵（"particle_route"），
        # 把它當 kind 傳會讓 load 卡把資料認成不存在的型別。
        kind = self.model.kind
        if getattr(self.model, "route_by", None) is not None \
                and self.dataset is not None:
            kind = str(getattr(self.dataset, "kind", "") or kind)
        if sync:
            try:
                result = PreviewWorker.run_sync(recipe, item, kind,
                                                upto_node=upto,
                                                sources=self.sources_for_run())
            except Exception as e:  # UI 邊界
                self._status("Preview failed: %s: %s" % (type(e).__name__, e), "error")
                return False
            self._on_preview_ready(result)
            return True
        self._async_epoch = self._preview_epoch
        self.preview_worker.request(recipe, item, kind,
                                    upto_node=upto,
                                    sources=self.sources_for_run())
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

    def _selected_trace(self, result: Any) -> Any:
        """選取的那張卡這一次的執行紀錄（`None` = **它根本沒跑到**）。"""
        nid = self.selected_node
        if not nid or nid not in self.model.nodes:
            return None
        for tr in (getattr(result, "traces", None) or []):
            if str(getattr(tr, "node_id", "")) == nid:
                return tr
        return None

    def _selected_card_ran(self, result: Any) -> bool:
        """選取的那張卡**這一次真的執行了嗎**（F11 Enhance-4）。

        為什麼要問這一句
        ----------------
        使用者回報：「Load image 載入圖片後點選 Denoise，為何會有畫面？我前面的
        rule 應該有說要連接線（image source）右側才會出現 patch。」他是對的，
        而畫面上那張圖是這樣來的：預覽是**跑整條 route**（`upto_node` 只是提早
        停），而入口卡不需要任何線就跑得起來 —— 它把 `test` / `ref` 寫進了
        master context。Denoise 沒有輸入所以失敗，但**失敗的策略是「把已經算出
        來的影像留在畫面上」**，於是畫面上出現的是入口卡的輸出，看起來像是
        Denoise 的結果。

        那是 F9 那條規矩在影像區的破口：**資料從哪來由線決定**。沒有線就沒有
        資料，畫面上就不該有東西 —— 一張看起來對的圖比一片空白危險得多。

        判準用 traces（引擎的執行紀錄）而不是 lint：它同時涵蓋「這張卡沒接線」
        與「它的上游沒接線」——後者一樣不會執行，而畫面上一樣會出現入口卡的圖。
        """
        nid = self.selected_node
        if not nid or nid not in self.model.nodes:
            return True                  # 沒有選卡 = 看整條 route 的結果
        if self._preview_whole_route():
            # Output 卡／判定樹：它們不是逐顆的卡，沒有「自己的」影像可以講
            # —— 誠實的畫面是整條 route 跑完的樣子（2026-09-09，使用者：
            # 「目前在 ADC 跟 output 段影像預設是不顯示？」）。
            return True
        tr = self._selected_trace(result)
        return bool(tr is not None and getattr(tr, "ok", False))

    def _preview_whole_route(self) -> bool:
        """預覽要跑到底、連判定一起，而不是停在選取的那張卡嗎。

        兩種情況（2026-09-09）：選的是整批一次的卡（Output 段 —— 逐顆引擎
        跳過它，`upto` 停在那裡什麼都沒有），或使用者正在編判定樹（那時候他
        要看的正是「這一顆會走到哪片葉子」，而 `upto` 停在上一張卡的話判定
        根本不跑）。
        """
        if getattr(self, "_tree_focus", False):
            return True
        nid = self.selected_node
        node = self.model.nodes.get(nid) if nid else None
        if node is None:
            return False
        try:
            return get_step(node.step).scale == SCALE_LOT
        except KeyError:
            return False

    def _on_preview_ready(self, result: Any) -> None:
        self._last_result = result
        ctx = getattr(result, "context", None)
        images = dict(getattr(ctx, "images", {}) or {}) if ctx is not None else {}
        ran = self._selected_card_ran(result)
        if not ran:
            # **畫面上不留別人的圖**（見 :meth:`_selected_card_ran`）。
            images = {}
        self._preview_images = images

        self._populate_streams(images)
        self._show_current_stream()

        self._refresh_inspector(result)
        highlight = self._highlight_features(result)
        self.feature_panel.set_model(self._feature_model(result, highlight))
        score = getattr(result, "score", None)
        # 判定的**名字**（recipe 自己取的）比 `bin 1` 有意義得多 —— 廠內講的是
        # real / nuisance 或某個 class name（X7）。名字住在 `Rule.label` /
        # `TreeLeaf.label` / `otherwise_label`，`bin_labels()` 把它們收成一張表。
        verdict_bin = getattr(result, "bin", None) if score is not None else None
        decide = getattr(self.model, "decide", None)
        names = decide.bin_labels() if decide is not None else {}
        self.verdict.set_verdict(verdict_bin,
                                 label=names.get(verdict_bin, ""))
        self.verdict_score.setText("" if score is None
                                   else "score %s" % format_feature_value(score))
        self.verdict_note.setText(verdict_note(
            self.selected_node, verdict_bin, getattr(result, "ok", False)))
        self._show_decide_path(result)

        if not ran:
            # 兩種「沒有東西可看」要講不同的話，因為下一步不一樣：
            #   跑起來了但失敗   → 講**那個錯誤**（它自己就帶著怎麼修）；
            #   根本沒跑到       → 講**怎麼接線**（lint 對這件事早就有一句可以照做
            #                      的話，用它而不是再寫一份）。
            tr = self._selected_trace(result)
            err = str(getattr(tr, "error", "") or "") if tr is not None else ""
            if err:
                self._status("Preview problem: %s" % err, "error")
            else:
                why = self._node_problems().get(self.selected_node or "",
                                                ("", ""))[0]
                self._status(why or ("“%s” did not run this time, so there is "
                                     "nothing to show for it yet."
                                     % self.selected_node), "error")
        elif not getattr(result, "ok", False):
            # 這張卡跑過了，是**後面**某張卡失敗 —— 那時候畫面上的影像有意義
            # （診斷比清空有用），所以留著。
            self._status("Preview problem: %s"
                         % (getattr(result, "error", None) or "unknown error"))
        elif self.selected_node:
            self._status("Preview: stopped after “%s” (%d image streams)"
                         % (self.selected_node, len(images)))
        else:
            self._status("Preview done (%d image streams)%s"
                         % (len(images),
                            "   score %.4g" % score if score is not None else ""))

    def _show_decide_path(self, result: Any) -> None:
        """Preview 的 Path（F24 §8）：這一顆走過的路，一句話＋樹上亮起來。

        PR-3 起建在 `verdict_trace` 上 —— **跟引擎走同一支**
        （`decide_tree.walk_steps`），所以重放出的路跟引擎記在
        ``meta["decide"]["path"]`` 的必然相同，這裡不再讀 meta。
        判定樹模式亮路徑；`rules` 模式講「第幾條規則對上」；沒有判定
        （或這一顆沒跑到判定 —— ``bin`` 還是空的）就清空，**不寫 N/A**。
        """
        from .tree_scene import display_tree, path_text

        decide = getattr(self.model, "decide", None)
        text, hl = "", None
        # 這一顆的判定重放（U11）—— 那一行點下去就是把它交給回溯面板。
        self._preview_trace = None
        feats = dict(getattr(result, "features", {}) or {})
        ran = (decide is not None and getattr(result, "ok", False)
               and getattr(result, "bin", None) is not None)
        if ran:
            try:
                trace = verdict_trace(self.model.to_recipe(),
                                      self.model.kind, feats)
            except Exception:  # 顯示層
                trace = None
            self._preview_trace = trace
            if trace is not None and trace.mode == "tree" and trace.path:
                hl = trace.path
                tree = display_tree(decide)
                text = path_text(tree, hl) if tree is not None else ""
                if text:
                    text = "Path:  " + text
            elif trace is not None and trace.mode == "rules" \
                    and trace.rule_index >= 0:
                text = "Path:  rule %d matched" % (trace.rule_index + 1)
                if trace.leaf_label:
                    text += " (%s)" % trace.leaf_label
        self.decide_path.setText(self._decide_path_markup(text))
        self.decide_path.setToolTip(
            "Click to see why this defect got this verdict - every question "
            "the decision asked, and the number it compared."
            if text else "")
        for view in self._canvases():
            view.set_tree_highlight(hl)
        # 面板開著的時候換一顆 defect ＝ 換一份回溯（開著卻停在上一顆的話，
        # 畫面上那幾個數字跟旁邊的影像不是同一顆 —— 這個 repo 最怕的形狀）。
        # **講不出來就收起來**，不是留著上一顆的答案：拿掉判定、或這一顆算到
        # 一半就失敗了，那幾列數字會變成一份沒有主人的說明。
        # ⚠ 問 `isHidden()` 不是 `isVisible()`：視窗還沒 `show()` 的時候
        # 每一個子元件的 `isVisible()` 都是 False（docs/PITFALLS.md 那一列），
        # 於是「面板開著嗎」在那之前永遠答「沒有」。
        if not self.why_preview.isHidden() and not self._fill_preview_why():
            self.why_preview.dismiss()

    @staticmethod
    def _decide_path_markup(text: str) -> str:
        """把那一行變成一個連結（空的就留空 —— 不放一個點了沒事的連結）。

        ⚠ **要跳脫**：路徑裡有 ``>``（``contrast > 120``）與 ``&``，而這個
        QLabel 現在是 RichText —— 不跳脫的話那一段會被當成標籤吃掉，
        使用者看到的是一句少了半截的話。
        """
        raw = str(text or "")
        if not raw:
            return ""
        esc = (raw.replace("&", "&amp;").replace("<", "&lt;")
               .replace(">", "&gt;"))
        return '<a href="#why" style="text-decoration:underline;">%s</a>' % esc

    def _fill_preview_why(self) -> bool:
        """把目前這一顆的回溯餵給預覽欄的面板；沒有東西可講回 ``False``。"""
        trace = getattr(self, "_preview_trace", None)
        if trace is None or getattr(trace, "mode", "none") == "none":
            return False
        item = self._current_item()
        self.why_preview.set_trace(
            str(getattr(item, "defect_id", "") or ""), trace)
        return True

    def toggle_preview_why(self) -> bool:
        """單顆預覽的回溯面板：開／關（U11）。回傳現在開著沒有。

        **不必先跑整批** —— 那正是這件事的重點：`verdict_trace` 吃的是這一顆
        的特徵，而預覽已經把它們算出來了。以前唯一的入口是
        「跑一批 → Results → 點 score/bin」，而使用者手上明明就有這一顆的
        每一個數字。
        """
        if not self.why_preview.isHidden():     # 見 `_show_decide_path` 的 ⚠
            self.why_preview.dismiss()
            return False
        if not self._fill_preview_why():
            self._status("This recipe has no score and no decision — "
                         "there is nothing to replay.")
            return False
        self.why_preview.present()
        return True

    #: 會產生投影曲線的那一支（面板只在編輯它的時候出現）。
    #:
    #: ⚠ **一張卡、好幾個 method**（F30；幾個看 ``roi_reference.METHODS``，
    #: 這裡不抄）—— 判準因此是 ``(key, method)`` 不是 key。只看 key 的話 Region
    #: 卡全部亮起那塊面板，而別的 method 產不出投影曲線：那是一塊永遠空的面板。
    PROFILE_STEP = "roi_reference"
    PROFILE_METHOD = "stripes in the image"

    # ==================================================================== #
    # 區域跨顆檢視（F7-11）
    # ==================================================================== #
    def selected_regions(self) -> List[str]:
        """選取的節點會定義哪些具名區域（不是 Region 卡就是空的）。"""
        node = self.model.nodes.get(self.selected_node or "")
        return regions_of_node(node) if node is not None else []

    #: 需要模板的那一支（模板只能用那個對話框做出來）。見 `PROFILE_STEP`。
    TEMPLATE_STEP = "roi_reference"
    TEMPLATE_METHOD = "a cell I mark myself"

    def _is_method(self, node: Any, step: str, method: str) -> bool:
        """這個節點是不是「那張卡的那一支」（F30）。

        ``method`` 沒填時用卡片的預設值 —— 引擎那一邊看到的永遠是
        `validate_params` 補完的一份，兩邊的判斷要一致。
        """
        if node is None or node.step != step:
            return False
        got = str(node.params.get("method", "") or "")
        if not got:
            from ..core.pipeline.step import get_step
            spec = {p.name: p for p in get_step(step).params}.get("method")
            got = str(getattr(spec, "default", "") or "")
        return got == method

    def template_build_available(self) -> bool:
        """選取的卡片需要模板嗎（用明確狀態，不要問 widget 的可見性）。"""
        node = self.model.nodes.get(self.selected_node or "")
        return self._is_method(node, self.TEMPLATE_STEP, self.TEMPLATE_METHOD)

    def _on_param_action(self, param_name: str) -> None:
        """某個參數說「我的值要用別的方式產生」。

        模板與區域是**同一個對話框**：框的座標相對於那一格 cell，所以少了 cell
        那張圖，四個數字沒有意義（F11 Region-1）。兩個參數各有一顆按鈕，但按下去
        去的是同一個地方。
        """
        if str(param_name) in ("template", "regions"):
            self.open_template_dialog()

    def open_template_dialog(self) -> Optional[Any]:
        """開「模板與區域」對話框；接受之後把兩者一起寫回這張卡。"""
        if not self.template_build_available():
            self._status("Select a Locate region by template card first.", "error")
            return None
        node_id = self.selected_node
        node = self.model.nodes[node_id]
        dlg = TemplateDialog(self)
        # 已經有模板就**讀回來**，不要逼使用者重挑一張大圖 —— 重建會重算相位，
        # 而相位一變，他標好的框就全部平移了（見 TemplateDialog.load_encoded）。
        dlg.load_encoded(str(node.params.get("template", "") or ""),
                         str(node.params.get("locate_axis", "x") or "x"))
        dlg.set_regions_text(str(node.params.get("regions", "") or ""))
        # 「畫面上那一張」—— 單張 SEM 那條路要疊 cell 的圖就是它（F11 Region-5）。
        img, why = self._template_source_image(node)
        dlg.set_screen_image(img, why)
        dlg.set_patch_size(self._preview_patch_size(node))
        dlg.accepted_setup.connect(
            lambda text, axis, regions, nid=node_id:
            self._apply_template(nid, text, axis, regions))
        dlg.check_across_requested.connect(self.open_region_check)
        self.template_dialog = dlg
        dlg.show()
        return dlg

    def _template_source_image(self, node: Any) -> Tuple[Optional[Any], str]:
        """這張卡接的那一條流，在這一顆上長什麼樣（給對話框疊 cell 用）。

        **問的是卡片自己的 `source`**，不是一組寫死的名字：單張影像那條路的流
        可能叫 `single`、`test` 或使用者自己取的任何名字（`load_single` 的
        `out` 是他填的），而寫死 `ref`/`test` 的話那條路永遠拿不到圖。
        """
        res = getattr(self, "_last_result", None)
        images = dict(getattr(res, "images", None) or {}) if res is not None else {}
        if not images:
            # 這一顆跑失敗時 ``res.images`` 是空的 —— 而**「這張卡還沒接線」正是
            # 使用者會來開這個對話框的時候**。上游已經算出來的那幾條流還在
            # context 上，拿得到就拿。
            ctx = getattr(res, "context", None)
            images = dict(getattr(ctx, "images", None) or {})
        wanted = str(node.params.get("source", "") or "")
        for key in [k for k in (wanted, "ref", "test") if k]:
            img = images.get(key)
            if img is not None and getattr(img, "size", 0):
                item = self._current_item()
                return img, "%s · %s" % (
                    str(getattr(item, "defect_id", "") or "defect"), key)
        return None, ""

    def _preview_patch_size(self, node: Any = None) -> Optional[Any]:
        """目前這一顆影像有多大（``(h, w)``）—— 不知道就 ``None``。

        畫布拿它畫「一顆 defect 看得到多少」。**不知道就不畫**：畫一個猜出來的
        窗比不畫更糟，使用者會照著那個窗決定哪些區域標得到。

        跟 :meth:`_template_source_image` 問同一條流 —— 兩者不一致的話，畫面上
        那個窗畫的是一張圖、疊出來的 cell 來自另一張。
        """
        if node is not None:
            img, _why = self._template_source_image(node)
            if img is not None:
                return (int(img.shape[0]), int(img.shape[1]))
            return None
        res = getattr(self, "_last_result", None)
        images = dict(getattr(res, "images", None) or {}) if res is not None else {}
        for key in ("ref", "test"):
            img = images.get(key)
            if img is not None and getattr(img, "size", 0):
                shape = img.shape[:2]
                return (int(shape[0]), int(shape[1]))
        return None

    def _apply_template(self, node_id: str, text: str, axis: str,
                        regions: str = "") -> None:
        """把疊好的模板與畫好的區域一起寫進卡片參數。"""
        if node_id not in self.model.nodes:
            return
        try:
            self.model.set_param(node_id, "template", str(text))
            self.model.set_param(node_id, "locate_axis", str(axis))
            self.model.set_param(node_id, "regions", str(regions))
        except ParamError as e:
            self._status("Could not store the template: %s" % e, "error")
            return
        node = self.model.nodes[node_id]
        self.param_form.set_step(
            get_step(node.step).describe(), node.params,
            self.model.available_streams(before_node=node_id),
            self.model.available_regions(before_node=node_id))
        names = region_names(str(regions))
        self._status(
            "Template stored in this recipe — it repeats along %s. %s"
            % (axis,
               ("Regions: %s. Use “Check this region across defects…” to see "
                "whether they hold for the whole batch." % ", ".join(names))
               if names else "No regions drawn yet — this card cannot run."))
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

    def _install_inspector(self, step_key: str,
                           params: Optional[Dict[str, Any]] = None) -> None:
        """換卡片時換儀表。沒有註冊儀表的卡就只剩特徵表。"""
        cls = inspector_for(step_key, params)
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
            # 字在 `_refresh_inspector` 餵完資料之後才定案（儀表要看得到
            # 現在畫的是什麼才說得出「誰跟誰比」）—— 這裡先給一個保底。
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
        sig = getattr(insp, "select_requested", None)
        if sig is not None:
            sig.connect(self._on_select_requested)
        sig = getattr(insp, "calibrate_requested", None)
        if sig is not None:
            sig.connect(self._on_calibrate_requested)
        sig = getattr(insp, "charts_requested", None)
        if sig is not None:
            sig.connect(self._on_charts_requested)

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
        if not self._is_method(node, self.PROFILE_STEP,
                               self.PROFILE_METHOD):
            return
        items = self._items()
        if not items:
            self._status("Load a KLARF first - measuring across the lot "
                         "needs the lot.", "error")
            return
        if not self.calibrate_worker.start(
                self.model.to_recipe(), items[:self.CALIBRATE_LIMIT],
                self.model.kind, nid, dict(node.params),
                sources=self.sources_for_run()):
            self._status("Still measuring - please wait.")
            return
        self._status("Measuring stripe pitch and width on %d defects…"
                     % min(len(items), self.CALIBRATE_LIMIT))

    def _on_calibrated(self, result: Any) -> None:
        """量完了：能填的填進卡片（走 set_param，可復原），不能填的講原因。"""
        nid = self.selected_node
        node = self.model.nodes.get(nid or "")
        if not self._is_method(node, self.PROFILE_STEP,
                               self.PROFILE_METHOD):
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
            self.model.available_streams(before_node=nid),
            self.model.available_regions(before_node=nid))
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
                self.model.available_streams(before_node=nid),
                self.model.available_regions(before_node=nid))

    def _on_charts_requested(self) -> None:
        """`Write charts` 儀表上的 `Preview charts…`（F87）。

        視窗**只有一個**（開第二次是把同一個抬到最前面）—— 每按一次多開一個
        的話，改設定會只改到其中一個，而其他幾個還畫著舊的樣子。
        """
        from .uniformity_window import UniformityWindow

        win = getattr(self, "_charts_window", None)
        if win is None:
            win = UniformityWindow(self)
            win.style_changed.connect(self._on_chart_style_changed)
            self._charts_window = win
        self._refresh_charts_window(self._inspector, force=True)
        win.show()
        win.raise_()
        win.activateWindow()

    def _refresh_charts_window(self, insp: Any, force: bool = False) -> None:
        """把儀表現在那一顆餵給圖的視窗（開著才餵）。"""
        win = getattr(self, "_charts_window", None)
        if win is None or not (force or win.isVisible()):
            return
        if not hasattr(insp, "series") or not hasattr(insp, "charts"):
            return
        series = insp.series()
        win.set_context(series, look=str(insp.params.get("look", "") or ""),
                        axis=str(insp.params.get("axis", "") or "x"),
                        metric=str(series.get("metric") or ""),
                        kinds=insp.charts(),
                        # 散佈圖吃的那兩份（別的圖用不到）。
                        frame=insp.frame() if hasattr(insp, "frame") else None,
                        spec=str(insp.params.get("spec", "") or ""))

    def _on_chart_style_changed(self, look: str) -> None:
        """視窗裡改完設定 → 寫回那張卡的 ``look`` 那一格。

        走「量給我填」同一條路（`_on_param_requested` → `set_param`），所以它
        進得了復原堆疊、參數表也跟著顯示新值 —— 一個會改 recipe 而 Ctrl+Z
        撤不掉的視窗，比沒有那個視窗糟。
        """
        node = self.model.nodes.get(self.selected_node or "")
        if node is None or node.step != "output_uniformity":
            return
        self._on_param_requested("look", str(look))

    def _on_select_requested(self, axis: str, rule: str) -> None:
        """使用者在曲線上**點了一根條紋** → 那個方向改用那一種材質（F11 2b）。

        走跟「量給我填」同一條路（``_on_param_requested`` → ``set_param``），
        所以它可以 Ctrl+Z 撤銷、參數表也跟著顯示新值。

        ``axis`` 是曲線的方向：``x`` 那條曲線講的是**直的**條紋
        （``vertical_*``），別接反了 —— 接反的症狀是點左邊的圖改到右邊的參數，
        而畫面上兩邊都會動，看起來像是「有反應」。
        """
        name = "vertical_select" if str(axis) == "x" else "horizontal_select"
        self._on_param_requested(name, str(rule))

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
        # meta 在 **context** 上，不在 result 上（result 只帶 features/score/bin）。
        ctx = getattr(result, "context", None) if result is not None else None
        meta = dict(getattr(ctx, "meta", {}) or {})
        if insp is None:
            self.inspector_summary.setText("")
            # 沒有儀表的卡也可能有曲線欄位 —— 那個背景跟儀表是兩件事，
            # 不要因為前者不在就跳過後者。
            self._refresh_curve_backdrop(meta)
            return
        node = self.model.nodes.get(self.selected_node or "")
        one: Dict[str, Any] = {}
        if result is not None:
            one = {"features": dict(getattr(result, "features", {}) or {})}
        # 「這張卡產出哪些特徵」要問卡片庫（含 output_prefix）—— 儀表只負責畫。
        feats: List[str] = []
        if node is not None:
            try:
                feats = list(get_step(node.step).resolve_features(node.params))
            except Exception:  # 顯示用
                feats = []
        # 儀表要跟著**畫面上正在看的東西**走：並排比對打開時是左右那兩條流，
        # 所以底下的直方圖也是兩張、順序一樣（使用者是拿它們互相對照的）。
        shown = [self.stream_combo.currentText()]
        if self._compare_on:
            shown.append(self.stream_combo_b.currentText())
        # 寫回的儀表要**真的乾跑一次**才講得出「會改幾列」，而那需要 KlarfDoc。
        # 儀表不自己去讀檔（它連檔名都不該知道）—— 由這裡遞過去。
        # 沒有 KLARF 的兩種輸入這一格就是 None，面板會退回估算並標明。
        meta = dict(meta or {})
        meta["_klarf_doc"] = getattr(self.dataset, "klarf", None)
        # 跨顆那張圖的座標（`die_x` / `x_um`）在**結果那幾列裡沒有** ——
        # 它們住在 `Dataset.items`。同 `_klarf_doc` 的理由由這裡遞過去，
        # 不然選單裡少掉 die 那兩欄，而 die 圖正是那張圖最有用的一種。
        meta["_items"] = list(getattr(self.dataset, "items", None) or [])
        insp.set_context(self.selected_node or "",
                         params=dict(node.params) if node else {},
                         result=one, batch=self.trial_results, meta=meta,
                         feature_names=feats,
                         shown_streams=[s for s in shown if s])
        self.inspector_summary.setText(insp.summary())
        # 圖的視窗開著就跟著這一顆走 —— 換一顆 defect 而視窗停在上一顆的
        # 數字，是最難發現的那一種說謊（兩張圖都畫得出來）。
        self._refresh_charts_window(insp)
        # `Chart look` 那一列的編輯器，預覽要畫**這一顆**（不是樣本）。
        # 同 `set_histogram` 的先例：數字只有引擎那一份，UI 不再算一次。
        self.param_form.set_chart_series(
            insp.series() if hasattr(insp, "series") else None)
        # 散佈圖那一格的選單是從**這一顆的長表**長出來的（欄名跟著量測卡走，
        # 寫死一份的話使用者的欄位在選單上找不到）。
        self.param_form.set_chart_frame(
            insp.frame() if hasattr(insp, "frame") else None)
        # 分頁鈕的字由**儀表現在畫的東西**決定（使用者 2026-08-21：「title 要
        # 更詳細一點」）。放不下的那半句進 tooltip。
        if hasattr(insp, "tab_title"):
            self.btn_tab_card.setText(str(insp.tab_title() or "Card"))
            self.btn_tab_card.setToolTip(str(insp.tab_tooltip() or ""))
        self._refresh_curve_backdrop(meta)

    def _refresh_curve_backdrop(self, meta: Dict[str, Any]) -> None:
        """曲線欄位後面墊上「這張卡吃進來的那條流」的灰階分布（F11 UI-C）。

        用的是引擎那份 ``stream_change[流]['before']`` —— 跟 Enhance 儀表左邊那條
        細線同一組數字。UI 不自己再壓一次直方圖：畫面上的分布跟真的跑出來的
        不一樣，比沒有那個背景更糟。

        ``before`` 是「這張卡動它之前」的樣子，而曲線的橫軸就是輸入灰階 ——
        兩者講的是同一件事，所以不必另外算一份。
        """
        node = self.model.nodes.get(self.selected_node or "")
        if node is None:
            self.param_form.set_histogram([])
            return
        changes = dict((meta or {}).get("stream_change") or {})
        # 這張卡處理的第一條流（曲線是逐像素的，兩條流吃的是同一條曲線）。
        keys = [k.strip() for k in
                str(node.params.get("streams") or "").split(",") if k.strip()]
        for key in keys:
            rec = changes.get(key)
            if rec and rec.get("before"):
                self.param_form.set_histogram(list(rec["before"]))
                return
        self.param_form.set_histogram([])

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
                self.selected_node, regions, REGION_THUMB, source,
                self.sources_for_run())

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
        return self._is_method(node, self.PROFILE_STEP,
                               self.PROFILE_METHOD)

    def _feature_about(self, result: Any) -> Dict[str, str]:
        """哪一個相對量是**跟誰**比出來的（特徵表中間那一欄要用）。

        名字裡沒有這件事 —— ``epi_cmp_delta_median`` 不講 mg，而把它塞進名字
        會變成 ``epi_vs_mg_cmp_delta_median`` 那種長度。引擎在
        ``meta["compares"]`` 已經記著（那一份本來就是給儀表用的），
        這裡只是讀出來，**不重算**。
        """
        ctx = getattr(result, "context", None)
        rows = (getattr(ctx, "meta", {}) or {}).get("compares") or {}
        out: Dict[str, str] = {}
        for rec in rows.values():
            ref = str((rec or {}).get("reference") or "")
            for name in (rec or {}).get("names") or []:
                out[str(name)] = ref
        return out

    def _feature_model(self, result: Any,
                       highlight: Sequence[str] = ()) -> List[Dict[str, Any]]:
        """特徵面板要畫的那幾段（F76 刀 4）—— **跟結果表同一棵樹**。

        分組不是在這裡發明的：`verdict_features.bound_specs` 給每個名字的
        結構化身分（卡、區域、統計量、變體），`feature_panel.panel_model`
        把它排成「一張卡 × 一個區域」的段。Results 是 *N 顆 × M 特徵*，
        這裡是 *一顆* —— 同一棵樹的轉置。

        ⚠ 這一支取代了 `_feature_sections()` 與 `_feature_specs()`：那兩支
        各自從 `meta["feature_owner"]` 與逐張卡的 `resolve_feature_specs`
        重建了一次分組，而**那份說法跟結果表那份已經漂開了** —— 區域顏色
        在同一張表上出現兩種就是漂出來的第一個症狀（F76 刀 1）。
        """
        from .feature_panel import panel_model
        from ..core.pipeline.verdict_features import (
            bound_specs, diagnostic_columns,
        )

        try:
            recipe = self.model.to_recipe()
            bounds = bound_specs(recipe, self.model.kind)
            diags = diagnostic_columns(recipe, self.model.kind)
        except Exception:  # 顯示層，壞了就不分組
            bounds, diags = [], []
        return panel_model(getattr(result, "features", {}) or {}, bounds,
                           highlight=highlight,
                           about=self._feature_about(result),
                           diagnostics=diags)

    def _feature_specs(self) -> Dict[str, Any]:
        """特徵名 → 誕生處宣告的身分（`FeatureSpec`，PR-3；前身 F37 A4 的
        `_feature_parts`）。

        **問每一張卡，不自己拆字串**：``test_epi_hot_glv_median`` 這一串裡哪
        一段是流、哪一段是區域、哪一段是使用者自己取的名字，三者都是任意識別
        字，UI 只能猜 —— 而猜錯會把區域畫成流，顏色跟著錯，而顏色正是這件事的
        重點。組名字的規則住在卡片上，身分就宣告在同一個地方
        （`Step.resolve_feature_specs`；上下標的拆解 = ``spec.parts()``）。

        先出現的贏（同 `feature_owners`）：撞名的時候引擎留的是先寫那一份的
        救援名，而畫面上那一格顯示的是後寫的值 —— 兩邊都指同一個人比較不會錯。
        """
        out: Dict[str, Any] = {}
        for nid in self.model.node_order:
            node = self.model.nodes.get(nid)
            if node is None or not node.enabled:
                continue
            try:
                got = get_step(node.step).resolve_feature_specs(node.params)
            except Exception:  # 顯示用，壞了就不拆
                swallowed("studio._feature_specs")
                continue
            for s in got:
                out.setdefault(str(s.name), s)
        return out

    def _feature_sections(self, result: Any) -> List[Dict[str, Any]]:
        """特徵表要怎麼分組（F13-1 ①）—— **照引擎已經記下來的事分**。

        兩份資料都早就在了，只是 UI 沒用：

        * ``ctx.meta["feature_owner"]`` —— 每個特徵是**哪張卡**寫的（engine 在
          救援撞名的那一段順手記的）；
        * ``Step.diagnostic_features()`` —— 哪幾個是「這張卡自己做了什麼」
          （`clip_frac` 那類），不是在量缺陷。

        所以這裡不發明分類規則。發明一份的話它會跟引擎漂 —— 而漂掉的症狀是
        「這個數字被歸到錯的卡底下」，畫面上完全看不出來。

        順序 = **執行順序**（讀起來跟畫布一樣，由前到後），診斷那一組排最後
        而且**預設收起來**：它每張 Enhance 卡都會產出，攤開來會把真正在量的
        那幾個數字擠到看不見。
        """
        ctx = getattr(result, "context", None)
        owner = dict(getattr(ctx, "meta", {}).get(FEATURE_OWNER_KEY, {})
                     or {}) if ctx is not None else {}
        features = dict(getattr(result, "features", {}) or {})
        if not owner:
            return []

        diagnostics: List[str] = []
        sections: List[Dict[str, Any]] = []
        # 救回來的那份叫什麼，**跟引擎用同一支**（F17-②）。以前這裡自己用
        # `qualified_feature_name(nid, f)` 組（節點 id 前綴），而引擎改成流名
        # 前綴之後兩邊就對不上了 —— 症狀是那個值以「量測值」的身分排到最上面，
        # 而它量的是那張卡自己。兩份說法必然有一份會漂（CLAUDE.md §0）。
        try:
            recipe = self.model.to_recipe()
            prefixes = feature_prefixes(list(self.model.node_order), recipe,
                                        REGISTRY)
        except Exception:  # 顯示用，壞了就退回節點 id
            prefixes = {}
        for nid in self.model.node_order:
            node = self.model.nodes.get(nid)
            if node is None:
                continue
            mine = [f for f in features if owner.get(f) == nid]
            if not mine:
                continue
            try:
                step_cls = get_step(node.step)
                label = step_cls.label
                colour = theme.group_hex(step_cls.resolve_group())
                diag = set(step_cls.diagnostic_features(node.params))
                # **救回來的那一份也是診斷數字**：兩張 Enhance 卡都寫
                # `clip_frac`，engine 把先寫的留成 `<那條流>_clip_frac`。
                # 救援名用 `FeatureSpec.qualified`（跟引擎、binder 同一支）。
                pfx = prefixes.get(nid, nid)
                diag |= {s.qualified(pfx).name
                         for s in step_cls.resolve_feature_specs(node.params)
                         if s.name in diag}
            except Exception:  # 顯示用，壞了就當一般的
                label, colour, diag = node.step, "", set()
            measured = [f for f in mine if f not in diag]
            diagnostics.extend(f for f in mine if f in diag)
            if measured:
                sections.append({"title": label, "color": colour,
                                 "names": measured, "node": nid})
        # **同一張卡放兩次時才把 id 帶出來**（畫布的副標用的是同一條規則）：
        # 兩組都叫 `Normalize` 的話，使用者分不出哪一組是哪一張卡；而每一組都
        # 掛一個 node id 又是在每一份正常的 recipe 上加噪音。
        seen_titles = [sec["title"] for sec in sections]
        for sec in sections:
            if seen_titles.count(sec["title"]) > 1:
                sec["title"] = "%s · %s" % (sec["title"], sec["node"])
        if diagnostics:
            sections.append({"title": "Diagnostics", "color": "",
                             "names": diagnostics, "collapsed": True})
        return sections

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
          要求）—— 選 Gray-level stats 那種量測卡時，畫面直接回答
          「我到底在量哪裡」。以前量測卡選起來預覽上什麼都沒有，roi 填錯
          只能用數字猜。

        仍然只畫**選著那張卡**的，不是 context 裡所有的框：一份 recipe 常常
        有好幾張 Region 卡，全部畫出來分不清誰是誰。
        """
        node = self.model.nodes.get(self.selected_node or "")
        ctx = getattr(getattr(self, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return []
        out: List[Tuple[float, float, float, float]] = []
        for name in self._overlay_region_names(node):
            out.extend(tuple(float(v) for v in r)
                       for r in ctx.roi_norm_rects(name))
        return out

    @staticmethod
    def _overlay_region_names(node) -> List[str]:
        """要畫哪幾個區域，**依畫的順序**。

        只有一份：框與框的名字必須走同一個清單，不然顏色會指到錯的區域 ——
        而畫面上沒有任何東西透露那件事。
        """
        try:
            step_cls = get_step(node.step)
            produced = list(step_cls.resolve_regions_out(node.params))
            consumed = list(step_cls.resolve_regions_in(node.params))
        except Exception:  # 顯示用，不能擋畫面
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
        return names

    def region_overlay_names(self) -> List[str]:
        """每個框屬於哪一個具名區域（跟 :meth:`region_overlay` 等長）。

        分開一支而不是讓 ``region_overlay`` 回 tuple：那一支有測試在比清單，
        而且「框在哪」與「框叫什麼」是兩個問題 —— 疊框只需要前者也還是對的
        （長度對不上時 `ImageView` 就整組不分色，見 `set_overlay`）。
        """
        node = self.model.nodes.get(self.selected_node or "")
        ctx = getattr(getattr(self, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return []
        out: List[str] = []
        for name in self._overlay_region_names(node):
            out.extend([name] * len(ctx.roi_norm_rects(name)))
        return out

    def _refresh_region_overlay(self) -> None:
        """把框疊到預覽影像上。**每次預覽算完都會走這裡**，所以拖參數的時候
        框是跟著動的 —— 那正是這種參數唯一調得動的方式（F7-8）。"""
        boxes = self.region_overlay()
        focus = self._focus_box_index(boxes)
        labels = self.region_overlay_names()
        for view in (self.image_view, self.image_view_b):
            view.set_overlay(boxes, focus, labels)
        self._refresh_measure_marks()

    def measure_marks(self, stream: Optional[str] = None):
        """選著那張卡要畫的量測標記 ``(lines, points, focus, labels)``（F19）。

        ``stream`` 是**這個 view 現在顯示的那一條流** —— 卡片只交那一條量到的
        （見 `Step.overlay_marks`）。不給就是全部，`measure_marks()` 那樣呼叫的
        既有測試因此不用動。

        資料由**卡片自己**交出來（`Step.overlay_marks`）—— meta 的形狀是那張卡
        的事。這裡只問「現在選著的是誰」，所以整個 Measure 段共用同一條路。

        **跟框不同來源**：框從 model 推導（recipe 說要看哪裡），標記來自
        `_last_result` 的 context（這一顆真的量到了什麼）。混在一起的話，
        「框還在但標記沒了」這個最有用的狀態就講不出來。
        """
        node = self.model.nodes.get(self.selected_node or "")
        ctx = getattr(getattr(self, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return [], [], -1, []
        try:
            lines, points, focus, labels = get_step(node.step).overlay_marks(
                ctx, node.params, stream)
        except Exception:  # 顯示用，不能擋畫面
            return [], [], -1, []
        # ``focus`` 可以是一個 index 或**一串**（一個記號不只一條線 ——
        # GLV 的贏家格是一個 X）。這裡不收窄成 int：收窄過的那一版，X 的第二
        # 條會掉進「不是焦點」那一組，畫出來只剩一條斜線。
        return (list(lines or []), list(points or []), focus,
                [str(v) for v in (labels or [])])

    def heat_tiles(self, stream: Optional[str] = None):
        """選著那張卡要鋪的熱圖 ``(cells, colours, legend)``（F87）。

        跟 :meth:`measure_marks` 一模一樣的形狀 —— 卡片自己交
        （`Step.overlay_heat`），這裡只問「現在選著的是誰、正在看哪一條流」。
        """
        node = self.model.nodes.get(self.selected_node or "")
        ctx = getattr(getattr(self, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return [], [], None
        try:
            cells, colours, legend = get_step(node.step).overlay_heat(
                ctx, node.params, stream)
        except Exception:  # 顯示用，不能擋畫面
            return [], [], None
        return list(cells or []), [str(c) for c in (colours or [])], legend

    def _refresh_measure_marks(self) -> None:
        """**一個 view 一次** —— 兩張圖顯示的可能是不同的流（比對模式）。

        以前這裡取一次就推給兩個 view，於是一張卡在 test 與 ref 上各量一次時，
        兩組線會同時畫在**你正在看的那一張**上，同色、同標籤、分不出來。
        現在各問各的，比對模式因此也才是對的（2026-08-22）。
        """
        for view, combo in ((self.image_view, self.stream_combo),
                            (self.image_view_b, self.stream_combo_b)):
            lines, points, focus, labels = self.measure_marks(
                str(combo.currentText() or ""))
            view.set_marks(lines, points, focus, labels,
                           solid=self._marks_solid())
            cells, colours, legend = self.heat_tiles(
                str(combo.currentText() or ""))
            view.set_heat(cells, colours, legend)

    def _marks_solid(self) -> bool:
        """選著那張卡的標記要不要畫滿（`Step.marks_solid`）。

        **那張卡說的，不是這裡猜的** —— 「幾條線算少」是卡片自己才知道的事。
        """
        node = self.model.nodes.get(self.selected_node or "")
        if node is None:
            return False
        try:
            return bool(getattr(get_step(node.step), "marks_solid", False))
        except Exception:  # 顯示用，不能擋畫面
            return False

    def _focus_box_index(self, boxes: Sequence[Sequence[float]]) -> int:
        """哪一個框要畫成醒目的那一個 —— **卡片真的挑走的那一塊**。

        醒目的那一個的意思一直都是 ``<name>_center``（見
        :meth:`_overlay_region_names` 的註解：「它的角色由 focus 表達」）。
        以前這裡是用「離影像正中心最近」算出來的，而那在 F20 之前跟
        ``_center`` **必定一致** —— 那一版的 `_center` 就是這樣定義的。

        F20（2026-08-22）之後 Region 卡多了一格「哪一塊是缺陷那一塊」，
        選「訊號最強」時 ``_center`` 會落在別的地方。這裡不跟著改的話，
        影像上被畫成醒目的是 A、卡片實際量的是 B —— 而畫面上沒有任何東西
        透露那件事（那正是這個 repo 最怕的那種錯）。

        所以改成**去問 context 那一塊到底是哪一個**，對不上才退回舊規則
        （沒跑過、或那張卡不吐 ``_center``）。
        """
        rects = self._center_rects()
        for i, box in enumerate(boxes):
            if any(all(abs(float(a) - float(b)) < 1e-6 for a, b in zip(box, r))
                   for r in rects):
                return i
        if not self._defines_regions():
            # **量測卡選著的時候不要亂指一個。** 這裡的醒目一直都是
            # ``<name>_center`` 的意思，而那是 **Region 卡**的產物。
            # 量測卡（GLV / CD）只是**引用**別人定義的區域 —— 一個 24 格的
            # 區域被 pooled 成一堆像素時，沒有任何一格是特別的，把離畫面中心
            # 最近的那一格畫成醒目等於在說一件不成立的事。
            # 量測卡要指哪一格，走的是自己的 `overlay_marks`（那才是
            # 「這一顆真的量到了什麼」那條路）。
            return -1
        if not self._picks_a_center():
            # **``pick="none"`` 的 Region 卡也不畫醒目框**（F31 T4）：它明講
            # 「沒有哪一格是缺陷那一塊」，退回「離中心最近」畫一個醒目的，
            # 等於畫布替引擎說了一句它沒說的話。
            return -1
        best, best_d = -1, None
        for i, (nx, ny, nw, nh) in enumerate(boxes):
            d = (nx + nw / 2.0 - 0.5) ** 2 + (ny + nh / 2.0 - 0.5) ** 2
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _defines_regions(self) -> bool:
        """選著的這張卡是不是**定義**區域的那種（Region 卡）。

        引用別人區域的量測卡不算 —— 見 :meth:`_focus_box_index` 的說明。
        """
        node = self.model.nodes.get(self.selected_node or "")
        if node is None:
            return False
        try:
            return bool(get_step(node.step).resolve_regions_out(node.params))
        except Exception:  # 顯示用，不能擋畫面
            return False

    def _picks_a_center(self) -> bool:
        """這張卡有沒有挑一塊 —— 宣告裡有沒有 ``<name>_center``。

        `pick="none"` 的 Region 卡定義區域但**不挑**，宣告裡因此沒有那個
        名字（`_util.region_family` 的開關）—— 醒目框跟著挑選一起走。
        """
        node = self.model.nodes.get(self.selected_node or "")
        if node is None:
            return False
        try:
            names = get_step(node.step).resolve_regions_out(node.params)
        except Exception:  # 顯示用，不能擋畫面
            return False
        return any(str(n).endswith("_center") for n in names)

    def _center_rects(self) -> List[Sequence[float]]:
        """這一顆上 ``<name>_center`` 實際落在哪 —— 沒跑過就是空的。"""
        node = self.model.nodes.get(self.selected_node or "")
        ctx = getattr(getattr(self, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return []
        out: List[Sequence[float]] = []
        try:
            names = list(get_step(node.step).resolve_regions_out(node.params))
        except Exception:  # 顯示用，不能擋畫面
            return []
        for name in names:
            if not str(name).endswith("_center"):
                continue
            out.extend(tuple(float(v) for v in r)
                       for r in ctx.roi_norm_rects(name))
        return out

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
                  sync: bool = False, cache_dir: Optional[Any] = None,
                  write_outputs: bool = False) -> bool:
        """跑前 ``n`` 顆並更新直方圖。``sync=True`` 走同步路徑（測試用）。

        ``write_outputs``（F16 Stage 5c）：跑完之後要不要讓 Output 段的卡
        **真的寫出檔案**。**預設 False 是刻意的** —— 使用者定調「試跑不寫，
        只有整批才寫」，而新加一條跑 pipeline 的路時它預設不寫。
        只有 :meth:`run_all` 傳 True。
        """
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

        recipe = self.model.to_recipe()
        # 「只跑這幾個 code」（F50）：**篩掉零顆的時候不可以安靜地跑完**。
        #
        # 引擎那一頭篩得很乾淨（`batch.select_items`），而乾淨的下場正是危險
        # 的：一個打錯的欄名或一個不存在的 code，跑出來是「0 defects」與一張
        # 空的結果表 —— 使用者要去猜是資料沒載到、pipeline 壞了，還是篩選太緊。
        # 那三件事的下一步完全不同，所以這裡要講出**是哪一個**。
        from d4t.core.pipeline.batch import item_filters, select_items

        picks = item_filters(recipe)
        if picks:
            kept = select_items(recipe, self.dataset, items)
            if not kept:
                where = ", ".join("%s = %s" % (col, ", ".join(vals))
                                  for _nid, col, vals in picks)
                self._status(
                    "Nothing to run — the input filter (%s) matches none of "
                    "the %d defects in this dataset. Check the column and the "
                    "values, or clear the filter to run everything."
                    % (where, len(items)), "error")
                return False
            self._filtered_note = ("%d of %d defects match the input filter"
                                   % (len(kept), len(items)))
            items = kept
        else:
            self._filtered_note = ""

        limit = max(1, min(int(n), len(items)))
        cdir = None if cache_dir is None else str(cache_dir)
        # **跟著這一次執行走**，不是讀當下的 UI 狀態：使用者按了 Run all 之後
        # 可以馬上去改別的東西，而這一批的結果仍然是「他叫我整批跑」的那一批。
        self._write_outputs_this_run = bool(write_outputs)
        # 同步那條路（headless 測試 / CLI 式呼叫）沒有 event loop 在轉，
        # 背景 worker 的訊號投遞不到 —— 寫檔那一段要跟著走同步版。
        self._write_outputs_sync = bool(sync)

        # 這一次抽哪幾顆（X3）。**紀錄先寫下來再跑** —— 跑到一半當掉的時候，
        # 「剛才那一批是哪幾顆」仍然答得出來。
        spec = self.sample_spec()
        # 這裡**再算一次**同一個抽樣，只為了拿那份紀錄。它不浪費（幾千顆的
        # `random.sample`），而且**保證跟 `run_batch` 挑到同一批** —— 同一個
        # 種子、同一串 items。紀錄裡的 `mode` 可能跟 `spec` 不一樣（分層那一欄
        # 整批是空的時候會退成 random），而使用者要看到的是**真的發生的那個**。
        _picked, note = sampling.pick(
            items, limit, mode=str(spec.get("mode", "first")),
            seed=spec.get("seed"),
            column=str(spec.get("column", "CLASSNUMBER") or "CLASSNUMBER"))
        self.sample_note = dict(note)

        if sync:
            t0 = time.time()
            try:
                results = TrialWorker.run_sync(
                    recipe, self.dataset, limit,
                    workers=int(workers) if workers else 1, cache_dir=cdir,
                    sample=spec)
            except Exception as e:  # UI 邊界
                self._status("Trial run failed: %s: %s" % (type(e).__name__, e), "error")
                return False
            self._apply_trial_results(results, time.time() - t0)
            return True

        self._trial_t0 = time.time()
        if not self.trial_worker.start(recipe, self.dataset, limit,
                                       workers=workers, cache_dir=cdir,
                                       sample=spec):
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
        self.run_all()

    def run_all(self, sync: bool = False) -> bool:
        """跑**整批** —— 每一顆，不只前 N 顆。**不寫任何檔案。**

        ⚠ 2026-09-09 之前這一支跑完會順手讓 Output 卡寫出去（F16 Stage 5c
        的「試跑不寫，只有整批才寫」）。使用者：「跑完後可以檢查結果再按一個
        鍵 output」—— 所以「跑」跟「寫」現在是兩個動作：這裡只跑，寫是
        :meth:`write_outputs`（Results 視窗上那顆「Write outputs」）。理由是
        同一句：寫 KLARF 是不可逆的，而在這之前使用者連看一眼結果的機會都
        沒有。
        """
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        if not items:
            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
            return False
        return self.run_trial(len(items), workers=TRIAL_WORKERS,
                              cache_dir=DEFAULT_CACHE_DIR, sync=sync)

    def write_outputs(self, sync: bool = False) -> bool:
        """把**現在這批結果**照 Output 卡寫出去（2026-09-09）。

        三道關，每一道都要講話（推廣鐵則）：沒有結果不寫；被停掉的那一批是
        **部分結果**，不寫（寫進 KLARF 是不可逆的錯）；KLARF ``inplace`` 先問
        一次（`_confirm_irreversible_writes`，那是這個 app 唯一不可逆的動作）。
        """
        results = list(self.trial_results or [])
        if not results:
            self._status("Nothing to write yet — run a trial or “Run all” "
                         "first.", "error")
            return False
        last = dict(getattr(self, "_last_run", None) or {})
        if last.get("partial"):
            self._status("That run was stopped part-way, so these are partial "
                         "results — nothing was written. Run again to the end "
                         "before writing.", "error")
            return False
        if not self._confirm_irreversible_writes():
            return False
        self._write_outputs_sync = bool(sync)
        return self._write_outputs(results)

    def rerun(self, sync: bool = False) -> bool:
        """照**現在的 ADC 設定**把判定再跑一次（2026-09-09，使用者：「可以根據
        ADC 的設定快速 Re-run（因為 feature 應該都算了？）」）。

        兩條路，由 `batch.measurement_signature` 決定：量測那一段跟上一批一樣
        → 拿上一批的 features 重判（`batch.rerun_decision`，秒級，影像一顆都
        不碰）；不一樣 → 整批重跑（跟上一批同樣的顆數）。**不拿舊數字配新的
        量測卡**：那是這個 repo 最怕的「跑得完、有數字、而且是錯的」。

        重判的底稿是上一批**原封不動的那一份**（`_last_run["rows"]`），不是
        畫面上那一份 —— 連按兩次 Re-run 之間，上一次判定失敗的顆才救得回來。
        """
        from d4t.core.pipeline.batch import measurement_signature, rerun_decision

        last = dict(getattr(self, "_last_run", None) or {})
        rows = copy.deepcopy(last.get("rows") or [])
        if not rows:
            self._status("Nothing to re-run yet — run a trial first.", "error")
            return False
        issues = self.model.validate()
        problems = [i for i in issues if i.level == "error"]
        if problems:
            first = problems[0]
            self._status("Cannot re-run — %s: %s" % (first.title, first.detail),
                         "error")
            return False
        self._pending_warnings = [i for i in issues if i.level == "warning"]
        recipe = self.model.to_recipe()
        if measurement_signature(recipe) != str(last.get("sig") or ""):
            self._status("A measuring card changed since the last run, so the "
                         "numbers have to be measured again — running every "
                         "defect of the last run.")
            return self.run_trial(int(last.get("limit") or len(rows)),
                                  workers=TRIAL_WORKERS,
                                  cache_dir=DEFAULT_CACHE_DIR, sync=sync)
        t0 = time.time()
        try:
            n = rerun_decision(recipe, rows)
        except Exception as e:  # UI 邊界
            self._status("Re-run failed: %s: %s" % (type(e).__name__, e), "error")
            return False
        elapsed = time.time() - t0
        self._apply_trial_results(rows, elapsed)
        self._status("Re-run: decided %d of %d defects again from the stored "
                     "numbers in %.1f s — no image was recomputed."
                     % (n, len(rows), elapsed))
        return True


    # ---- Output 段：把結果寫出去（F16 Stage 5c）---------------------------
    def _write_outputs(self, results: Sequence[Dict[str, Any]]) -> bool:
        """跑 Output 段的卡（背景執行緒）。回 False = 沒開起來。

        **只有 `run_all()` 走得到這裡**（使用者定調：試跑不寫）。
        """
        recipe = self.model.to_recipe()
        self._status("Writing outputs…")
        if getattr(self, "_write_outputs_sync", False):
            # 同步那條路沒有 event loop，訊號投遞不到 —— 直接跑並自己收尾，
            # 走的是**同一支** `run_batch_steps`（不是第二套邏輯）。
            try:
                bctx = OutputWorker.run_sync(recipe, self.dataset, list(results))
            except Exception as e:  # UI 邊界
                self._on_outputs_failed("%s: %s" % (type(e).__name__, e))
                return False
            self._on_outputs_done(bctx)
            return True
        if not self.output_worker.start(recipe, self.dataset, list(results)):
            self._status("Still writing the last run's outputs — please wait.")
            return False
        return True

    def _on_outputs_done(self, bctx: Any) -> None:
        """寫完了：**三種東西是三句不同的話**（見 `BatchContext`）。"""
        outputs = list(getattr(bctx, "outputs", None) or [])
        warnings = list(getattr(bctx, "warnings", None) or [])
        errors = dict(getattr(bctx, "errors", None) or {})

        if not outputs and not errors and not warnings:
            # 一張 Output 卡都沒有 —— 那不是錯，只是這份 recipe 沒有出口。
            self._status("Run finished. This recipe has no Output card, so "
                         "nothing was written — add one to save the results.")
            return

        bits = []
        if outputs:
            # **列出路徑**：使用者要去那裡找檔案。
            bits.append("Wrote %s" % ", ".join(outputs))
        # 路徑寫出來還不夠 —— 使用者得自己開檔案總管、自己把它貼進去（X5：
        # 流程的終點沒有出口）。`QDesktopServices` 這個 repo 只用過一次，
        # 那條路一直在，只是沒有接上這裡。**留在 bits 裡的路徑不動**：
        # 這顆鈕是補充，開不起來的時候路徑照樣讀得到。
        where = str(outputs[0]) if outputs else ""
        for w in warnings:
            bits.append(str(w))
        if errors:
            # 其他卡照樣寫出去了（鐵則 7 的跨顆版），但失敗的要指名。
            first = sorted(errors.items())[0]
            more = ("  (and %d more)" % (len(errors) - 1)) if len(errors) > 1 else ""
            bits.append("Output card “%s” failed: %s%s" % (first[0], first[1], more))
        msg = "  ·  ".join(bits)
        level = "error" if errors else None
        if where:
            self._status_next_step(
                msg, "Open the folder",
                lambda: self._open_output_folder(where), level or "info",
                "Show %s in the file browser" % where)
        else:
            self._status(msg, level)

    def _open_output_folder(self, where: str) -> None:
        """帶使用者去那個資料夾。開不起來就**說出來**，不要安靜地沒反應。

        按了一顆鈕、什麼都沒發生，使用者第一個念頭是「這個工具有沒有壞」——
        `undo()` 那句「Nothing to undo.」是同一條規矩。
        """
        if not open_folder(where):
            self._status("Could not open %s — the path is in the message "
                         "above, copy it into the file browser." % where,
                         "error")

    def _on_outputs_failed(self, msg: str) -> None:
        self._status("Writing outputs failed: %s" % msg, "error")

    def _confirm_irreversible_writes(self) -> bool:
        """有**啟用**的 KLARF `inplace` 卡就先問一次（F16 Stage 5c）。

        M5 那條「寫回前一定先預覽變更」是硬性關卡，而它不能因為 Export 精靈
        消失就消失。承接方式是這裡加上 `output_klarf` 的儀表（選到那張卡就
        看得到乾跑的計畫書）。

        **判準是「會不會動到原檔」不是「是不是 KLARF」**：`annotate` 與 `topn`
        寫的都是新檔，每次都要多按一下的話，那個確認很快就會變成閉著眼睛按掉
        的東西 —— 而它要擋的正是 `inplace` 那一種。

        ⚠ **只看啟用的節點**：停用的那張卡不會跑，跳確認就是騙人。
        """
        targets = []
        for nid in self.model.node_order:
            node = self.model.nodes.get(nid)
            if node is None or not getattr(node, "enabled", True):
                continue
            if node.step != "output_klarf":
                continue
            if str(node.params.get("mode", "annotate")).strip() != "inplace":
                continue
            targets.append(str(node.params.get("path", "") or "(no path yet)"))
        if not targets:
            return True

        plan_text = self._writeback_plan_text()
        body = ("“In place” edits the KLARF file itself — this cannot be "
                "undone.\n\nFile(s): %s" % "\n".join(targets))
        if plan_text:
            body = "%s\n\n%s" % (body, plan_text)
        answer = QMessageBox.warning(
            self, "Write into the original KLARF?", body,
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        return answer == QMessageBox.Yes

    def _writeback_plan_text(self) -> str:
        """乾跑一次寫回，回一句「會改幾列」。跑不出來就回空字串。

        **乾跑不寫任何東西**（`plan_writeback`），所以在確認之前跑它是安全的。
        """
        try:
            from d4t.core.export.klarf_out import plan_writeback

            doc = getattr(self.dataset, "klarf", None)
            rows = list(self.trial_results or [])
            if doc is None or not rows:
                return ""
            plan = plan_writeback(doc, rows, "inplace")
            return ("Based on the last run: %d of %d row(s) would change."
                    % (int(getattr(plan, "n_rows_changed", 0)),
                       int(getattr(plan, "n_rows_out", 0))))
        except Exception:  # 這只是一句提示，不准擋路
            return ""

    def _on_trial_progress(self, done: int, total: int) -> None:
        self._progress_set(int(done), int(total), "%v / %m defects")
        self._status("Running: %d / %d" % (int(done), int(total)))

    def _on_trial_done_async(self, results: Any) -> None:
        self._apply_trial_results(list(results or []),
                                  time.time() - (self._trial_t0 or time.time()))

    def _enabled_output_cards(self) -> int:
        """畫布上**啟用中**的 Output 卡有幾張（F86）。

        只數啟用的：停用的那張不會跑，把它算進去等於承諾一件不會發生的事。
        """
        from ..core.pipeline import get_step
        from ..core.pipeline.step import CATEGORY_BATCH

        n = 0
        for nid in self.model.node_order:
            node = self.model.nodes.get(nid)
            if node is None or not getattr(node, "enabled", True):
                continue
            try:
                if get_step(node.step).category == CATEGORY_BATCH:
                    n += 1
            except Exception:  # 一句提示不准擋畫面
                swallowed("studio._enabled_output_cards")
                continue
        return n

    def _apply_trial_results(self, results: Sequence[Dict[str, Any]],
                             elapsed: float) -> None:
        results = list(results or [])
        self._progress_done()
        self.trial_results = results
        # **這一批的底稿**（2026-09-09）：Re-run 從這裡重判、Write outputs 看
        # 它是不是被停掉的部分結果。`sig` 是量測那一段的簽章 —— 量測卡改了
        # 就不能拿這批數字重判。`limit` 讓「整批重跑」跑一樣多顆。
        from d4t.core.pipeline.batch import measurement_signature

        self._last_run = {
            "rows": copy.deepcopy(results),
            "sig": measurement_signature(self.model.to_recipe()),
            "partial": bool(self.trial_worker.is_aborted()),
            "limit": len(results),
        }
        self._refresh_results_button()
        # 每張卡在這一批跑得怎樣，標在卡片上（F99 P1-5）。
        self.pipeline.set_run_status(run_status_from(results))
        self.trial_scores = [r["score"] for r in results
                             if r.get("ok") and r.get("score") is not None]
        # ⚠ **判定段要先算**：分布圖的分段染色讀的是它算好的「哪一類是哪幾顆」
        # （`_spread_segments`）。順序反過來的話，圖上染的是**上一批**的類別
        # —— 跑得完、有顏色、而且是錯的（這個 repo 最怕的形狀）。
        self._refresh_verdict()
        self.results.set_features(self._features_in_results(results),
                                  default=self._default_spread_feature(results))
        # ⚠ **畫布上的數字自己叫一次，不要靠別人的副作用。**
        # 這一行以前是不存在的：畫布的分支流量與分流徽章跟著
        # `_refresh_bin_summary` 一起被順手更新，而那一支是「直方圖底下那行字」
        # 的事。R2 讓那張圖預設不再開在 Score 上之後，那條路就走不到了 ——
        # 於是徽章上的顆數整個變成 None。**一件事要有自己的呼叫。**
        self._refresh_decide_counts()
        # ⚠ **不要在這裡再叫一次 `_refresh_bin_summary`**（R1，2026-08-24）：
        # `_refresh_spread()` 已經照「這份 recipe 到底有沒有門檻在決定事情」
        # 決定過了，而這一行無條件用二元那條老路算一次，正好把它蓋掉。
        # 這是同一個 bug 的第二個入口 —— 第一個在 `_refresh_spread` 裡面。
        self._refresh_spread()
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
        # **抽樣的種子要講出來**（X3）。一次「random 200」跑出漂亮的結果而重現
        # 不了，等於沒有跑過 —— 而在這之前它只存在 `sample_note` 這個欄位上，
        # 使用者看不到。這是他唯一會讀到它的地方。
        msg += self._sample_line()
        # 跑之前的 lint 警告在這裡才講：跑之前講會被「Running: 3 / 200」洗掉。
        # 警告不擋執行，但它描述的是「跑得完、數字卻不是你以為的那個」——
        # 例如兩張量測卡撞名，後面那張把前面那張蓋掉了。
        # 篩選講一次：**跑了幾顆是使用者第一眼要對的數字**，而「37」在一份
        # 200 顆的 lot 上看起來像出了什麼事。
        note = str(getattr(self, "_filtered_note", "") or "")
        if note:
            msg = "%s  ·  %s (the rest were not processed, and their KLARF " \
                  "rows are untouched)" % (msg, note)

        warns = list(getattr(self, "_pending_warnings", []) or [])
        if warns:
            more = ("  (and %d more warning%s)"
                    % (len(warns) - 1, "" if len(warns) == 2 else "s")
                    if len(warns) > 1 else "")
            msg = "%s  ⚠ %s: %s%s" % (msg, warns[0].title, warns[0].detail, more)

        # ---- Output 段（F16 Stage 5c）--------------------------------------
        # 這一批要不要寫，看的是**開跑時**設的旗標（`run_all` 才是 True）。
        write = bool(getattr(self, "_write_outputs_this_run", False))
        self._write_outputs_this_run = False        # 一次就是一次
        if write and stopped:
            # 被停掉的是**部分結果** —— 寫進 KLARF 是不可逆的錯。
            # **而且要講出來**：安靜地不寫跟安靜地寫一樣糟。
            msg = "%s  ·  Stopped, so nothing was written." % msg
            write = False
        elif not write:
            # **跑不寫，而那件事要說出來**（F86，2026-09-07，使用者：「output
            # 預覽有，但跑完沒 output（沒看到資料夾）」）。2026-09-09 起
            # **每一次跑都不寫** —— 寫是 Results 視窗上那顆「Write outputs」
            # （使用者：「跑完後可以檢查結果再按一個鍵 output」）。錯的從來
            # 不是「不寫」，是**沒有回音**：畫布上明明有一張 Output 卡，按下
            # 那顆最大的鈕之後什麼都沒有發生，而狀態列只說「Run finished」。
            #
            # 所以只在**真的有 Output 卡**的時候多講一句，並且指名那個動作。
            n_out = self._enabled_output_cards()
            if n_out:
                msg = ("%s  ·  Run only - nothing written yet. When the "
                       "numbers look right, press “Write outputs” in Results "
                       "to let the %d Output card%s write."
                       % (msg, n_out, "" if n_out == 1 else "s"))
        self._status(msg)
        if write and results:
            self._write_outputs(results)
        # F7-5：結果一到就把 Results 視窗帶出來 —— 使用者按 Run 想看的就是這個
        self.results.set_summary(
            summarize_run(len(results), ok, elapsed, self.trial_scores))
        # X1：baseline 那一行吃的是**引擎判出來的 bin**（不是某個門檻重算的），
        # 因為使用者剛剛看到的就是它。拖門檻線時 `_refresh_bin_summary` 會用
        # 那個門檻再餵一次。
        self._publish_run_snapshot(None)
        self.results.set_run_all_enabled(bool(results),
                                         self._enabled_output_cards())
        # ⚠ **狀態列只講工具列沒講的那一半**（R4，2026-08-24）。
        # 這裡以前把整句 `msg` 原封不動再貼一次，而它的前半段
        #（「24 defects (24 ok, 0 failed) in 0.1 s」）跟 30px 上面那一行
        # 是同一件事。同一個事實兩個位置，遲早會有一個先過期。
        # 剩下的那一半（lint 警告、「停掉所以沒有寫」）沒有別的地方講，留著。
        self.results.status(extra_only(msg))
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
        # **每一顆判成了哪一類**（R5，2026-08-24）。縮圖底下第一行寫的是這個字
        # —— 使用者在樹上親手取的名字，而不是 `bin 3`（那是 KLARF 的實作細節）。
        # 名字從判定段那一份算出來（`verdict_rows`），所以整個 Results 視窗
        # 講的是同一份東西，不是兩份各自數出來的。
        names = self._class_names(results)
        # 表格的分層與徽章（PR-1）：判定層、按卡分組、診斷欄、警示布林 ——
        # 全部由 recipe 推導（`core/pipeline/verdict_features.py` 是唯一出處）。
        # 顯示層：推不出來就退回平鋪，不准因此沒有表。
        layout = alarms = None
        try:
            recipe = self.model.to_recipe()
            kind = self.model.kind
            layout = results_table.column_tree(
                results,
                verdict_features.features_in_verdict(recipe, kind),
                verdict_features.bound_specs(recipe, kind),
                verdict_features.diagnostic_columns(recipe, kind))
            alarms = verdict_features.diagnostic_alarm_map(recipe, kind)
        except Exception:  # 顯示層，見上
            layout = alarms = None
        # ⚠ 答案卷**一律傳**（沒有就是空 dict，不是 ``None``）：``None`` 的意思是
        # 「這個宿主沒有標注這回事」，而 Studio 永遠有 —— 那一欄消失的話，
        # 使用者標完之後畫面上不會有任何變化（X2）。
        self.results.set_table(results, names, layout, alarms,
                               dict(self.ground_truth or {}))  # 表格那一半（R7）
        self.gallery.set_items([
            {
                "defect_id": str(r.get("defect_id", "")),
                "ok": bool(r.get("ok", True)),
                "score": r.get("score"),
                "bin": r.get("bin"),
                "cls": names.get(str(r.get("defect_id", "")), ""),
                "features": dict(r.get("features") or {}),
                "thumb": None,
            }
            for r in results
        ])
        # 新的一批 = 分數分佈變了：舊的分數篩選一定要清掉，不然使用者會看到
        # 一個對不上新直方圖的區間（而且 chip 還掛在那裡）。
        self.results.clear_filter()
        self._score_filter = None

    def _class_names(self, results: Sequence[Dict[str, Any]]) -> Dict[str, str]:
        """``defect_id → 這一顆判成了哪一類的名字``（沒取名字的那一類是空的）。

        ⚠ **不自己走一次樹**：判定段已經算好每一類是哪幾顆
        （`verdict_rows` 的 ``ids``），這裡只是把它翻過來。兩邊各走一次的話，
        縮圖上的名字跟判定段上的顆數會是兩份會漂的東西。
        """
        from .verdict_band import verdict_rows

        out: Dict[str, str] = {}
        for row in verdict_rows(getattr(self.model, "decide", None),
                                list(results or []), self.ground_truth):
            if row.get("kind") != "class":
                continue
            name = str(row.get("name") or "").strip()
            for did in (row.get("ids") or ()):
                out[str(did)] = name
        return out

    def show_gallery(self) -> None:
        """把 Results 視窗叫出來（Gallery 與分數分佈都在那裡）。

        **還沒跑過也叫得出來**（F48，2026-08-28）：工具列那顆「Results」與
        `Ctrl+Shift+R` 走的是這一支，而它們不要求先跑一批。空的時候視窗自己
        要講得出為什麼是空的 —— 那是 F44 的 empty_reason 巡檢同一條規矩：
        **一塊空白要嘛有東西，要嘛有一句話說它在等什麼。**

        工具列左邊的摘要本來就寫著 `No results yet.`，但那句話回答不了
        「所以我現在該做什麼」，而狀態列是這個視窗唯一會講整句話的地方。
        """
        if not self.trial_results:
            self.results.status(
                "Nothing to show yet — press “Run trial” in the main window "
                "and the score distribution, thumbnails and table fill in here.")
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
    def _on_defect_selected(self, defect_id: str) -> None:
        """Results 裡單擊（或方向鍵走到）某顆 → 主畫面跳過去，**不搶焦點**
        （2026-09-09）。使用者正在 Results 視窗裡一顆一顆看，主視窗每次都跳到
        前面的話，他每看一顆就要再點回去一次。已經在那一顆上就不動。"""
        did = str(defect_id)
        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
        for i, it in enumerate(items):
            if str(getattr(it, "defect_id", "")) == did:
                if i != int(self.defect_index):
                    self.set_defect_index(i)
                return

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

    # ---- 回溯面板（PR-3）：這一顆為什麼判成這樣 ---------------------------
    def _on_trace_requested(self, defect_id: str) -> None:
        """結果表點了 score / bin / class → 重放那一顆的判定並開面板。

        trace 吃**那一列的 features**（引擎判定後的快照，let 值都在）——
        不重跑影像、不重算任何值（`verdict_trace` 的立身規矩）。
        """
        did = str(defect_id)
        row = next((r for r in (self.trial_results or [])
                    if str(r.get("defect_id", "")) == did), None)
        if row is None:
            return
        if not row.get("ok"):
            self._status("Defect “%s” failed before the decision — the error "
                         "column says why." % did, "error")
            return
        feats = dict(row.get("features") or {})
        # score-only 的 recipe：bin 只在列上（引擎不寫進 features）——
        # 補給 trace 顯示；decide 模式的 leaf_bin 是重放樹算的，不看這一格。
        if row.get("bin") is not None:
            feats.setdefault("bin", float(row["bin"]))
        try:
            trace = verdict_trace(self.model.to_recipe(), self.model.kind,
                                  feats)
        except Exception as e:  # 顯示層
            self._status("Could not replay the decision: %s" % e, "error")
            return
        if trace.mode == "none":
            self._status("This recipe has no score and no decision — "
                         "there is nothing to replay.")
            return
        self.results.show_why(did, trace)

    def _on_why_item(self, defect_id: str, name: str) -> None:
        """面板上點了一項 → 跳到產出那個數字的卡。

        身分查 `bound_specs`（跟結果表的分組同一份）：有區域的項把那一塊
        **亮**在影像上（`highlight_region`），引擎的項（let / score）對映
        Score / Bin 偽卡＝打開判定區。
        """
        try:
            bound = {b.spec.name: b for b in verdict_features.bound_specs(
                self.model.to_recipe(), self.model.kind)}
        except Exception:  # 顯示層
            swallowed("studio._on_why_item")
            return
        b = bound.get(str(name))
        if b is None:
            return
        if not b.node_id:
            # 引擎的名字（let、score、decide_unanswered）：去編判定區 ——
            # 跟畫布上點 ADC 那一格走同一條。
            self._on_tree_step_clicked("")
            return
        if b.spec.region:
            self.highlight_region(defect_id, b.node_id, b.spec.region)
        else:
            self.select_node(b.node_id)

    def highlight_region(self, defect_id: str, node_id: str,
                         region: str) -> bool:
        """跳到那一顆、選產出的卡，並把**那一塊區域**亮在影像上。

        亮法住在 `ImageView.set_overlay_emphasis`：命中的框全強度、其餘降
        alpha —— 顏色仍然說「哪一塊」、粗細仍然說「缺陷格」，**不 overload
        focus**。`set_overlay` 會清掉強調，所以先刷新預覽再點亮。
        """
        did = str(defect_id)
        items = list(getattr(self.dataset, "items", []) or []) \
            if self.dataset else []
        index = next((i for i, it in enumerate(items)
                      if str(getattr(it, "defect_id", "")) == did), None)
        if index is not None:
            self.set_defect_index(index)
        if not self.select_node(str(node_id)):
            return False
        self.refresh_preview(sync=True)
        for view in (self.image_view, self.image_view_b):
            view.set_overlay_emphasis([str(region)])
        return True

    # ---- 直方圖點長條 → Gallery 篩選 --------------------------------------
    def _on_bar_clicked(self, lo: float, hi: float) -> None:
        """點一根長條：只看那個分數區間；再點同一根就取消。

        「同一根」的判斷要連 Gallery 目前**真的還在篩**一起看 —— 使用者可能
        已經按掉 Gallery 上的條件 chip 了，那時候再點同一根當然是重新篩選。
        """
        rng = (float(lo), float(hi))
        if self._score_filter == rng and self.gallery.filter_text():
            self.results.clear_filter()
            self._score_filter = None
            self._status("Score filter cleared (showing all %d)"
                         % self.gallery.displayed_count())
            return
        self.results.set_filter({"mode": "score_range",
                                 "lo": rng[0], "hi": rng[1]})
        self._score_filter = rng
        self.show_gallery()
        self._status("Filtered to score %.3g–%.3g (%d defects)"
                     % (rng[0], rng[1], self.gallery.displayed_count()))

    # ==================================================================== #
    # 首次開啟導覽 + 範例 recipe 庫（M6）
    # ==================================================================== #
    def _open_windows(self):
        """「Windows」下拉列的那幾個頂層視窗（U15 那張表上准開的）。"""
        return [("Results", getattr(self, "results", None)),
                ("Region check", getattr(self, "region_window", None)),
                ("Uniformity charts", getattr(self, "_charts_window", None))]

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
        """開範本庫；選了哪份就直接載進流程面板。

        ``directory`` 給測試用（正式路徑一律走 ``welcome.RECIPES_DIR``，
        F91 X4 起就是 repo 的 `recipes/`）—— 要驗「壞掉的檔案不會讓整個庫開
        不起來」那種情境時，得餵一個自己造的資料夾。
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
            # **講出找過哪裡**（同對話框裡那一句）：使用者的下一個問題是
            # 「那我要把檔案放哪」，而「是空的」答不出來。
            self._status("No templates found in %s." % dlg.directory)
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
        except Exception as e:  # UI 邊界，一律回報
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

    # ---- 第二份 lot（F15）--------------------------------------------------
    def _on_open_pair_source(self, node_id: str) -> None:
        """`pair_source` 卡上的 `Open data…`：載一份**第二個** lot 掛上去。

        **不取代目前的資料集**：main 決定批次跑幾顆、route 用哪一條、KLARF 寫回
        誰。這一份只提供「另一張圖與它的座標」。
        """
        if self.dataset is None:
            self._status("Load the main lot first — this card pairs every "
                         "defect of the open lot with one from a second lot.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open the second lot's KLARF", "",
            "KLARF (*.001 *.klarf *.txt);;All files (*)")
        if path:
            self.attach_pair_source(node_id, path)

    def attach_pair_source(self, node_id: str, klarf_path: str,
                           sync: bool = False) -> str:
        """載入第二份 lot 並掛到 main 上（回狀態列那句話）。

        **預設走背景執行緒**（F15-2）。第一版是同步的，於是開一份 raw data
        （幾十萬顆）的時候整個 Studio 沒有反應好一陣子 —— main 那一份早就在
        背景載了（`dataset_worker`），第二份沒有跟上。``sync=True`` 留給測試
        與 headless。

        代號從卡片的 `source` 參數來；還沒取名就用檔名推一個 —— 使用者要打的字
        程式已經知道了（同 F11 的「量到的 pitch 自動填回參數」）。
        """
        node = self.model.nodes.get(str(node_id))
        if node is None or self.dataset is None:
            return ""
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync(str(klarf_path), None)
            except Exception as e:  # UI 邊界，一律回報
                return self._on_pair_source_failed("%s: %s" % (type(e).__name__, e))
            self._pending_pair = (str(node_id), str(klarf_path))
            return self._on_pair_source_loaded(ds)

        if self.pair_worker.is_running():
            msg = "A second lot is already loading — please wait."
            self._status(msg)
            return msg
        self._pending_pair = (str(node_id), str(klarf_path))
        self.pair_worker.start(str(klarf_path), None)
        name = os.path.basename(str(klarf_path))
        self._progress_busy("Loading %s…" % name)
        msg = "Loading second lot: %s" % name
        self._status(msg)
        return msg

    def _on_pair_source_failed(self, msg: str) -> str:
        self._pending_pair = None
        self._progress_done()
        text = "Could not load that lot: %s" % msg
        self._status(text, "error")
        return text

    def _on_pair_source_loaded(self, ds: Any) -> str:
        """第二份載完了 → 掛到 main 上（背景與同步兩條路都走這裡）。"""
        from d4t.core.ingest import pair_source as pair_ingest

        pending, self._pending_pair = self._pending_pair, None
        self._progress_done()
        if pending is None:
            return ""                       # 關窗／換卡之後才送達的通知
        node_id, klarf_path = pending
        node = self.model.nodes.get(str(node_id))
        if node is None or self.dataset is None:
            return ""

        sid = str(node.params.get("source", "") or "").strip()
        if not sid:
            sid = _source_id_from(klarf_path)
            self.model.set_param(str(node_id), "source", sid)
        # **只複製要用的那幾欄**：raw data 是幾十萬顆，×24 欄字串是幾百 MB，
        # 而那幾欄還要 pickle 進 worker。`carry` 之後改了會重填（見
        # `_sync_pair_fields`），所以少複製不會變成「這一欄不見了」。
        cols = self._pair_columns_wanted(sid)
        try:
            rep = pair_ingest.attach(self.dataset, ds, sid, columns=cols)
        except pair_ingest.PairSourceError as e:
            self._status(str(e), "error")
            return str(e)
        self._pair_filled[sid] = tuple(cols)
        self._say_missing_columns(sid, cols)
        # 卡片旁邊那句話要講得出檔名 —— 它是使用者認得的東西。
        ds._d4t_name = os.path.basename(str(klarf_path))
        self._sync_source_action(node)
        # 三格的選單（代號／哪張圖／哪些欄）現在才有答案（F15-2）。
        if self.selected_node == str(node_id):
            self.param_form.set_dynamic_choices(self._dynamic_choices_for(node))
        self._refresh_all()
        # **掛上第二份 = 這條 pipeline 的產出變了**，所以預覽要重跑一次
        # （2026-08-20）。以前不重跑，於是使用者按完 `Open data…` 什麼事都沒
        # 發生：影像流的下拉裡沒有 `paired`，要再去點一張卡才會出現 ——
        # 而「按了鈕、畫面沒反應」讀起來就是「載不進來」。
        self._schedule_preview()
        msg = "Paired source · %s" % rep.summary()
        self._status(msg)
        return msg

    # ---- 三格「用選的」要的答案（F15-2）------------------------------------
    def _pair_columns_wanted(self, source_id: str) -> List[str]:
        """指著這個代號的每一張配對卡，`carry` 的聯集（`carry` 的意思住在卡片）。"""
        from d4t.core.steps.pair_source import columns_for_source

        return columns_for_source(self.model.nodes.values(), source_id)

    def _number_info(self):
        """設定區「插入數字 ▾」的 tooltip 與區域顏色（`ParamForm.number_info_provider`）。"""
        from .number_picker import number_tips

        return number_tips(self.model), self.model.feature_regions()

    def _dynamic_choices_for(self, node: Any) -> Dict[str, List[str]]:
        """這張卡的三格選單現在有哪些選項（`ParamSpec.choices_from` 的答案）。

        `source_images` / `source_columns` 問的是**這張卡指著的那一份**。
        指著一個還沒掛上來的代號 → 兩個都是空的，而空的那一格會講出為什麼。
        （拿「唯一掛著的那一份」去頂替是不行的：那一格印的欄位就會是另一份的，
        而畫面說謊比空白糟。）
        """
        from d4t.core.ingest import pair_source as pair_ingest

        sources = dict(getattr(self.dataset, "sources", None) or {})
        out: Dict[str, List[str]] = {"sources": sorted(sources)}
        # Load 卡的 `carry`（F16）問的是**主資料集**有哪些欄 —— 跟指著誰無關，
        # 所以它在下面那個 early return 之前。
        out["main_columns"] = (pair_ingest.columns_of(self.dataset)
                               if self.dataset is not None else [])
        # 算式那一格的「插入數字 ▾」（F21-B）。**到這張卡為止**，不是整條 route
        # —— 列出一個排在自己後面才算出來的數字，點下去就是一份跑起來每一顆
        # 都失敗的 recipe。
        out["features"] = self.model.labelled_features(
            upto_node=str(getattr(node, "id", "") or "") or None,
            include_upto=False)
        # **整批一次的卡（Output 段）看得到 working numbers**（2026-09-09，
        # 使用者：「Output card 中也要能夠連動 working numbers」）。它們在每一顆
        # 都判定完之後才跑（`batch-card-has-downstream` 那條 error 守著），
        # 所以 `let` 的名字那時候真的在每一列的 features 裡。逐顆的卡**不行**
        # —— 判定在它們之後才算，列出來就是一份跑起來每一顆都失敗的 recipe。
        try:
            if get_step(node.step).scale == SCALE_LOT:
                out["features"] = list(out["features"]) + \
                    list(self.model.decision_features())
        except KeyError:
            pass                      # 不認得的卡：清單照舊
        src = sources.get(str(node.params.get("source", "") or "").strip())
        if src is None:
            return out
        items = list(getattr(src, "items", None) or [])
        out["source_images"] = sorted(getattr(items[0], "images", None) or {}) \
            if items else []
        out["source_columns"] = pair_ingest.columns_of(src)
        return out

    def sources_for_run(self) -> Dict[str, Any]:
        """掛在目前這份資料上的第二（第三…）份 —— **每一條跑 pipeline 的路都要**。

        2026-08-20 踩過：`run_batch` 那條路傳了，**單顆預覽那條沒有**。
        於是同一份 pipeline「試跑」有圖、切換 defect 沒圖，而使用者看到的是
        「載入 RSEM 之後不會有圖」——那句話怎麼查都查不到 PNG 上面去。

        所以這個答案只有一份，而且每一條路都問它：預覽、區域檢查、一鍵校正、
        疊圖輸出、批次。
        """
        from d4t.core.ingest import pair_source as pair_ingest

        if self.dataset is None:
            return {}
        return pair_ingest.sources_for_run(self.dataset)


    def _after_carry_param(self, node_id: str, name: str) -> None:
        """Load 卡改了 `carry` 之後要重填（F16）。

        跟 `_after_pair_param` 是同一件事的另一半：那一支管掛上來的第二份，
        這一支管主資料集。分開兩支是因為它們問的是**兩份不同的 KLARF**。
        """
        node = self.model.nodes.get(str(node_id))
        if node is None or node.step not in ("load_patch", "load_single"):
            return
        if name != "carry":
            return
        self._carry_main_columns()

    def _carry_main_columns(self) -> None:
        """把 Load 卡點名的 KLARF 欄位填進主資料集的每一顆。

        **答案只有一份**：`steps.load.columns_for_main`（`carry` 的意思住在
        卡片）。CLI 走的是同一支 —— 兩個入口，不是兩份規則。

        沒有人勾 → 一欄都不填，所以既有的 recipe 一個位元組都沒多帶。
        要一個這份 KLARF 沒有的欄 → **在勾的當下就講**（同 F15-2：等跑起來
        才講的話，那句話會一顆一顆出現，而且列的是「你要的」不是「它有的」）。
        """
        from d4t.core.ingest.dataset import (
            columns_of, fill_fields, missing_columns_of,
        )
        from d4t.core.steps.load import columns_for_main

        if self.dataset is None:
            return
        want = columns_for_main(self.model.nodes.values())
        if getattr(self, "_carry_filled", None) == tuple(want):
            return                          # 沒變 —— 不用走一遍幾十萬顆
        absent = missing_columns_of(self.dataset, want)
        fill_fields(self.dataset, want)
        self._carry_filled = tuple(want)
        if absent:
            self._status(
                "This lot has no KLARF column called %s. It has: %s."
                % (", ".join(absent), ", ".join(columns_of(self.dataset))),
                "error")

    def _sync_pair_fields(self, source_id: str) -> None:
        """`carry` 改了 → 把那幾欄補進掛著的那一份（F15-2）。

        掛的時候只複製「當時要的那幾欄」，所以之後才勾起來的那一欄不在
        `fields` 裡 —— 而卡片會照它的規矩說「這一份沒有這個欄位」，
        那句話是錯的（欄位在，只是沒複製）。KlarfDoc 還在手上，重填很便宜。
        """
        from d4t.core.ingest import pair_source as pair_ingest

        sid = str(source_id or "").strip()
        if not sid or self.dataset is None:
            return
        if sid not in (getattr(self.dataset, "sources", None) or {}):
            return
        cols = self._pair_columns_wanted(sid)
        if self._pair_filled.get(sid) == tuple(cols):
            return                          # 要的欄位沒變 —— 不用走一遍幾十萬顆
        pair_ingest.refill_fields(self.dataset, sid, cols)
        self._pair_filled[sid] = tuple(cols)
        self._say_missing_columns(sid, cols)

    def _say_missing_columns(self, source_id: str, columns: Sequence[str]) -> None:
        """要 carry 一個那一份沒有的欄位 → **在勾的當下**就講（F15-2）。

        以前這句話要等跑起來才出現，一顆一顆講，而且列出來的是「帶過來的那幾
        欄」不是「那一份有的那幾欄」—— 打錯字的人最需要的正是後者。
        這裡手上還有 KlarfDoc，所以答得出來。
        """
        from d4t.core.ingest import pair_source as pair_ingest

        src = (getattr(self.dataset, "sources", None) or {}).get(str(source_id))
        if src is None:
            return
        missing = pair_ingest.missing_columns(src, columns)
        if not missing:
            return
        self._status(
            "'%s' has no KLARF column %s — its columns are: %s"
            % (source_id, ", ".join(missing),
               ", ".join(pair_ingest.columns_of(src))), "error")

    def _on_open_gds(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Attach GLAS export (the folder with the *_label.png files)")
        if path:
            self.attach_gds_export(path)

    def attach_gds_export(self, export_dir: str) -> str:
        """把一份 GLAS 匯出掛到目前的資料集上（F11 Region-3）。回傳狀態列那句話。

        **配對在 ingest 層**（`core/ingest/glas_export.attach`），這裡只負責問
        路徑、把結果講出來、以及把 layer 的名字**填進卡片** —— 那個對照表在
        匯出的 manifest 裡，讓使用者自己去抄一次是在製造一個可以抄錯的機會
        （同 F11 Input 的「量到的 pitch 自動填回參數」）。
        """
        from d4t.core.ingest import glas_export

        if not self.dataset:
            msg = ("Load the lot first — “Open GDS export…” attaches labels to "
                   "the defects that are already open.")
            self._status(msg)
            return msg
        try:
            rep = glas_export.attach(self.dataset, export_dir)
            doc = glas_export.read_manifest(export_dir)
        except glas_export.GlasExportError as e:
            self._status(str(e))
            return str(e)

        # 名字填進**每一張** roi_reference 卡（還沒設定過的才填 —— 使用者改過的
        # 名字不能被一次「重新掛載」洗掉）。
        default = glas_export.default_layer_map(doc)
        filled = 0
        if default:
            for nid, node in self.model.nodes.items():
                if node.step == "roi_reference" and not str(
                        node.params.get("layers", "") or "").strip():
                    self.model.set_param(nid, "layers", default)
                    filled += 1
        # 表單的列數要照**這份匯出有幾層**排（`ChannelMapField` 的 labels 版）。
        self._gds_layers = list(rep.layers)
        self.param_form.set_label_count(len(rep.layers))
        msg = rep.summary()
        if filled:
            msg += " · filled the layer names into %d card(s)" % filled
        for w in rep.warnings:
            msg += " · △ %s" % w
        self._status(msg)
        self.refresh_preview()
        return msg

    def _on_open_stack(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image stack", "",
            "Multi-page TIFF (*.tif *.tiff *.I01);;All files (*)")
        if not path:
            return
        # 「一顆幾張」問一次就好，而且**預設值要是這個檔案自己的頁數線索**：
        # 問這一格的時候使用者手上唯一的事實是「這個檔案有幾頁」，所以先講出來。
        pages = 0
        try:
            from d4t.core.ingest import tiff_index
            pages = int(tiff_index.n_pages(path))
        except Exception:  # 只是拿來寫提示
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

    def _on_open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image", "",
            "Images (*.png *.tif *.tiff *.I01 *.jpg *.jpeg *.bmp);;All files (*)")
        if not path:
            return
        self.load_image_path(path)

    def _on_open_recipe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Recipe", "", "Recipe JSON (*.json);;All files (*)")
        if not path:
            return
        self.load_recipe_path(path)

    #: 「另存」對話框的副檔名 —— 這一個常數是為了**下面那句 endswith**
    #: 而存在的，不是為了整齊：Windows 的另存對話框在使用者自己打了一個
    #: 沒有副檔名的名字時**不會**幫他補（`docs/NO-GIT-SETUP.md` 記過記事本
    #: 那個反例），而一份叫 `char` 的檔案下次打開時在「Recipe JSON」這個
    #: 篩選底下**看不見**。
    RECIPE_SUFFIX = ".json"

    def _on_save_recipe(self) -> bool:
        """`Ctrl+S` 與工具列那顆鈕：**存回原檔**，沒有原檔才問路徑。

        回傳「真的存下去了嗎」—— 關窗前的確認要靠這個答案（F7-16）：
        使用者在另存對話框按取消，意思是「先別關」，不是「丟掉」。
        """
        if self.recipe_path:
            return bool(self.save_recipe_path(self.recipe_path))
        return self._on_save_recipe_as()

    def _on_save_recipe_as(self) -> bool:
        """`Ctrl+Shift+S`：**一定問路徑**。"""
        start = self.recipe_path or ("%s%s" % (
            str(getattr(self.model, "recipe_id", "") or "recipe").strip()
            or "recipe", self.RECIPE_SUFFIX))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Recipe", start,
            "Recipe JSON (*%s);;All files (*)" % self.RECIPE_SUFFIX)
        if not path:
            return False
        if not str(path).lower().endswith(self.RECIPE_SUFFIX):
            path = "%s%s" % (path, self.RECIPE_SUFFIX)
        return bool(self.save_recipe_path(path))

    # ==================================================================== #
    # 關窗
    # ==================================================================== #
    #: 關窗前要不要問「還沒存」。測試整批把它關掉 —— 一個 modal 對話框會讓
    #: headless 測試永遠停在那裡（而不是失敗），那種卡住最難查。
    PROMPT_ON_CLOSE = True

    def unsaved_changes(self) -> bool:
        """有沒有還沒存的編輯（明確狀態，不要去猜）。

        2026-08-16 到 2026-08-26 之間這句話的意思比現在強 —— 那段時間沒有
        存檔功能，所以「還沒存」是恆真的，而關窗提示講的是「關掉就沒了」。
        存檔回來之後它回到原本的意思：**有一個辦法，而他還沒用**。
        """
        return bool(self.model.dirty)

    def _ask_unsaved(self) -> str:
        """問使用者要不要存。回 ``"save"`` / ``"discard"`` / ``"cancel"``。

        第三個答案 2026-08-26 回來了（2026-08-16 拿掉，因為那時候它是一顆
        做不到自己承諾的鈕）。**預設答案仍然不是「丟掉」** —— 那一顆按下去
        沒有第二次機會。

        單獨一個方法是為了測試接得住 —— 要驗的是「三個答案各自會怎樣」，
        不是「QMessageBox 長什麼樣」。
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Save this pipeline before closing?")
        box.setText("This recipe has changes you have not saved.")
        box.setInformativeText(
            "The pipeline you just built is the whole point of the tuning you "
            "did — closing without saving throws it away.")
        box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard
                               | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Save)
        answer = box.exec()
        return {QMessageBox.Save: "save",
                QMessageBox.Discard: "discard"}.get(answer, "cancel")

    def confirm_close(self) -> bool:
        """可以關了嗎。

        **存檔失敗、或使用者在另存對話框按了取消，都不算可以關** —— 那是
        「我改變主意了」，不是「丟掉吧」。這一條 F7-16 就寫過，2026-08-26
        存檔回來時一起回來。
        """
        if not (self.PROMPT_ON_CLOSE and self.unsaved_changes()):
            return True
        answer = self._ask_unsaved()
        if answer == "cancel":
            return False
        if answer == "discard":
            return True
        return bool(self._on_save_recipe())

    def showEvent(self, event) -> None:  # Qt hook
        super().showEvent(event)
        # 中欄的畫布/設定比例第一次 show 才套 —— setSizes 要有實際高度才
        # 算得出來（見 _build_body 的說明）。只做一次：之後的比例是使用者
        # 自己拖的，重新 show（從最小化回來）不可以把它蓋掉。
        if not self._layout_ratio_applied:
            self._layout_ratio_applied = True
            # 上一次沒存到的東西（U4）—— **在版面套好之前問**，那時候畫面
            # 上還沒有任何東西，使用者不會以為那句話跟他剛才做的事有關。
            try:
                autosave.offer_restore(self)
            except Exception:  # 一張網不准擋開窗
                swallowed("studio.showEvent")
            # 版面模式自己會去讀那一格 QSettings（U5）—— 這裡以前有一段
            # 「只在設定區攤開時才還原」的判斷，而那個判斷現在住在
            # `set_layout_mode` 裡（Build 模式不吃存下來的比例，它就是滿版）。
            self.set_layout_mode(self.layout_mode(), remember=False)

    def closeEvent(self, event) -> None:  # Qt hook
        if not self.confirm_close():
            event.ignore()
            return
        self._preview_timer.stop()
        # **正常關窗＝把草稿收掉**（U4）。`confirm_close` 已經問過「要不要存」
        # 而使用者回答了 —— 留著一份草稿等於下次開窗再問他一次同一件事。
        # ⚠ 只在**走完關窗流程**的時候做：上面 `confirm_close` 回 False 的
        # 那條路已經 return 了，所以按了取消的人草稿還在。
        self.autosave.stop()
        autosave.clear()
        # 只存 Tune 的比例與欄寬（F100，理由在 `WorkbenchLayout.remember`）。
        self.layout_modes.remember()
        for dlg in (self.welcome_dialog, self.library_dialog, self.results):
            try:
                if dlg is not None:
                    dlg.close()
            except Exception:  # 關窗不准擋路
                swallowed("studio.closeEvent")
        for worker in (self.preview_worker, self.trial_worker,
                       self.dataset_worker, self.pair_worker,
                       self.thumb_worker, self.output_worker):
            try:
                worker.stop()
            except Exception:  # 關窗不准擋路
                swallowed("studio.closeEvent")
        super().closeEvent(event)
