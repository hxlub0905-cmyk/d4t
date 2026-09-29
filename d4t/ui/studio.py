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
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QWidget,
)

import d4t.core.steps  # noqa: F401 — 觸發卡片註冊（Qt-free、便宜）
from d4t.core.pipeline import ParamError, Recipe, get_step, list_steps
from d4t.core.pipeline.cellrois import region_names
from d4t.core.pipeline import sampling
from d4t.core.pipeline.step import SCALE_DEFECT, SCALE_LOT
from d4t.core.pipeline.recipe import (
    describe_migration, route_for, version_skew,
)
from d4t.core.pipeline.verdict_trace import verdict_trace

from . import autosave
from . import cross_links
from . import card_menu
from functools import partial

from . import clipboard
from . import open_dialogs
from . import baseline
from . import fit_screen
from .canvas import NODE_H, NODE_W, SUMMARY_SEP, PipelineCanvas, run_status_from
from .gauge_panel import GaugePanel
from .preview_overlays import PreviewOverlays
from . import studio_layout
from .gallery_controller import GalleryController
from .attach_sources import AttachSources
from .run_controller import RunController
from . import canvas_edges, wording
# ⚠ 這個常數的家在 `ui/run_controller.py`（F116 第 5 步跟著用它的程式碼
# 搬過去了）。這裡拿回來是因為它在下面的 `__all__` 裡（ruff 認得 ——
# 所以不必 noqa）：它是對外的名字，不是實作細節。
from .run_controller import DEFAULT_CACHE_DIR
# ⚠ 縮圖那一條鏈的家在 `ui/gallery_controller.py`（F116 第 3 步）。這裡拿
# 回來是因為前兩個在下面的 `__all__` 裡、而三個都有測試用 `studio_mod.`
# 拿 —— 它們是對外的名字，不是實作細節。
from .gallery_controller import (  # noqa: F401
    THUMB_CHANNEL_PRIORITY, ThumbWorker, thumb_channel,
)
# ⚠ 這兩個常數的家在 `ui/studio_layout.py`（F116 第 2 步跟著用它們的
# 程式碼搬過去了）。這裡拿回來是因為 **`studio.DEFAULT_TRIAL_N` 與
# `studio.COLUMN_SIZES` 是對外的名字**：載入資料集時要夾那個預設值
# （下面用得到），而測試兩個都從這個模組拿。
from .studio_layout import COLUMN_SIZES, DEFAULT_TRIAL_N  # noqa: F401
from . import strings
from .status_action import StatusAction
from .status_log import StatusHistory
from .region_check import regions_of_node
from . import region_check
from .template_dialog import TemplateDialog
from .results import extra_only, summarize_run
from . import scope
from . import truth_marks
from .scope import (
    is_supported_kind, no_klarf_message, unsupported_kind_message, visible_steps,
)
from .numbers import format_feature_value
from .viewmodel import (GLV_INTENTS, RecipeModel,
                        is_a_constant_expression, accuracy_at, histogram,
                        rebin)
from .theme import DEFAULT_THEME, THEMES, apply_theme, current_theme
from .workbench import MODES as LAYOUT_MODE_NAMES
from .welcome import (
    RecipeLibraryDialog, WelcomeDialog, app_settings, save_theme,
    welcome_disabled,
)
from .widgets import (
    apply_button_cursors, verdict_words,
)

from .workers import (
    CalibrateWorker, DatasetLoadWorker, OutputWorker, PreviewWorker,
    RegionCheckWorker, TrialWorker, shutdown_window,
)


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

#: 「用範例資料試一次」把合成 lot 產在哪（使用者自己的檔案一律不碰）。
DEMO_DIR = os.path.join(os.path.expanduser("~"), ".d4t", "demo_lot")

#: 範例資料的 defect 數與 seed（少到一分鐘內跑得完，多到直方圖看得出形狀）。
DEMO_DEFECTS = 24
DEMO_SEED = 7
#: model 變動 → 重算預覽 的去抖動間隔（毫秒）。拖 spinbox 不會每格都重算。
PREVIEW_DEBOUNCE_MS = 300

#: 右欄分頁的索引 —— F7-5 之後右欄只剩單顆預覽，Gallery 搬進 Results 視窗。
#: 常數保留是為了不打壞外部呼叫端；``TAB_GALLERY`` 現在等同「開 Results 視窗」。
TAB_PREVIEW = 0
TAB_GALLERY = 1

_FEATURE_PLACEHOLDER = "Insert feature ▾"
_SCORE_HELP = ("The score is an expression whose variables are the feature names "
               "produced by the pipeline above (e.g. snr_max, area_px, "
               "glv_max). score >= threshold → bin 1, otherwise bin 0. "
               "You can use + - * / ( ) and sqrt / abs / min / max.")


def _fmt(value: Any) -> str:
    """參數摘要用的短字串（float 去掉多餘的 0）。"""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return ("%g" % value)
    return str(value)



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

    ``tools/make_sample.py`` 不是安裝進來的套件，所以**延遲 import**（補
    ``sys.path``）；它也會拉進 tifffile —— 只按別的鈕的人不需要付這個成本。

    同一組 ``(n, seed)`` 產出的位元組完全相同，所以已經產過就直接沿用
    （第二次按這顆鈕是秒回的）。
    """
    out = str(out_dir) if out_dir is not None else DEMO_DIR
    klarf = os.path.join(out, "LOT_SYN.001")
    tiff = os.path.join(out, "LOT_SYN.tif")
    if os.path.isfile(klarf) and os.path.isfile(tiff):
        return {"out_dir": out, "klarf": klarf, "tiff": tiff}

    tools_dir = str(Path(__file__).resolve().parents[2] / "tools")
    if not os.path.isfile(os.path.join(tools_dir, "make_sample.py")):
        raise RuntimeError("the sample-data maker (tools/make_sample.py) is not "
                           "here - copy the whole d4t folder, not only d4t/")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from make_sample import generate

    return generate(out, n=int(n), seed=int(seed))


def verdict_note(selected_node: Optional[str], verdict_bin: Any,
                 ok: bool) -> str:
    """Verdict 膠囊旁邊那句「為什麼是破折號」（F99 P1-2）。

    只在一種情況講話：預覽跑得好好的、有選一張卡、而判定還沒跑到
    （``bin`` 是空的）。其他情況（沒選卡、跑出錯、真的有判定）都是空字串 ——
    膠囊或狀態列已經在講那件事，這裡再講一次只是把位子佔掉。
    """
    if selected_node and ok and verdict_bin is None:
        # ⚠ **不再只寫「press Esc」**（F117 D1）：那句話沒有人想得到，而且
        # 查下去它根本不成立（見 `studio_layout.clear_selection`）。最後那幾
        # 個字是點得下去的，Esc 修好之後照樣有效、寫在 tooltip 上。
        return ('preview stops at “%s” — <a href="#end">run to the end</a>'
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
        self.preview_worker = PreviewWorker(self)
        self.trial_worker = TrialWorker(self)
        # Output 段的卡（F16 Stage 5c）。**只有 `run_all()` 叫得到它** ——
        # 使用者定調「試跑不寫」，而那件事是結構上的：試跑那條路沒有這一支。
        self.output_worker = OutputWorker(self)
        #: 這一次執行要不要寫出輸出。**跟著那一次執行走**，不是讀當下的 UI
        #: 狀態 —— 使用者按了 Run all 之後可以馬上去改別的東西。
        self._write_outputs_this_run = False
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
        studio_layout.build_toolbar(self)
        studio_layout.build_body(self)
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
        studio_layout.build_progress(self)

        # ---- controller（F116）---------------------------------------------
        # ⚠ 順序：**介面組裝之後**（它讀 `bottom_stack`、`inspector_host` 那些
        # 東西）、**接線之前**（`_wire_widgets` / `_wire_workers` 要接得到它的
        # slot）。
        self.gauges = GaugePanel(self)
        self.overlays = PreviewOverlays(self)
        self.gallery_ctl = GalleryController(self)
        self.attach_ctl = AttachSources(self)
        self.run_ctl = RunController(self)

        self._wire_widgets()
        self._wire_workers()
        studio_layout.build_shortcuts(self)
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
        self._status("Ready — press “Help” for a guided start, or “Open data…” "
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
    # 介面的表與動作（**組裝本身在 `ui/studio_layout.py`**，F116 第 2 步）
    # ==================================================================== #
    # 這一段留下的是兩種東西：`StudioWindow` 身上的**表**（快捷鍵那一張，
    # `studio_layout.build_shortcuts` 讀 `win.SHORTCUTS`），以及那些鈕**按下去
    # 會發生什麼**（undo／redo／停止／進度列）。擺東西的那一千行搬走了 ——
    # 段名跟著改，不然它會是這個檔案裡第一個說謊的標題。
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
        view.link_dropped.connect(
            lambda *a: canvas_edges.on_link_dropped(self, *a))
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
        # ``btn_empty_open`` 在 ``studio_layout.build_body`` 建它的時候就接好了（那一列是
        # 從 ``scope.INPUT_SOURCES`` 長出來的，接線跟著一起長）——
        # 在這裡再接一次會變成按一下開兩個檔案對話框。
        self.btn_empty_sample.clicked.connect(self._on_demo_requested)
        self.param_form.action_requested.connect(self._on_param_action)
        self.param_form.source_requested.connect(self._on_source_requested)
        self.param_form.intent_chosen.connect(self._on_intent_chosen)
        # 設定區的插槽（F68）—— 走的是跟畫布拉線**完全同一條路**。
        self.param_form.wire_requested.connect(self._on_slot_wire)
        self.param_form.wire_show_requested.connect(self._on_slot_show)
        self.stream_combo.currentTextChanged.connect(
            self.overlays._on_stream_changed)
        self.stream_combo_b.currentTextChanged.connect(
            self.overlays._on_stream_b_changed)
        self.compare_check.toggled.connect(self.set_compare)

        self.image_view.cursor_info.connect(self._on_cursor_info)
        self.image_view_b.cursor_info.connect(self._on_cursor_info)
        self.image_view.view_changed.connect(
            lambda s, o: self.overlays._link_views(
                self.image_view, self.image_view_b, s, o))
        self.image_view_b.view_changed.connect(
            lambda s, o: self.overlays._link_views(
                self.image_view_b, self.image_view, s, o))

        self.results.shown_feature_changed.connect(self._on_spread_feature_changed)
        self.histogram.threshold_changed.connect(self._on_threshold_changed)
        self.histogram.threshold_committed.connect(self._on_threshold_committed)
        self.histogram.bar_clicked.connect(self.gallery_ctl._on_bar_clicked)

        self.gallery.thumbs_requested.connect(
            self.gallery_ctl._on_thumbs_requested)
        self.gallery.defect_activated.connect(
            self.gallery_ctl._on_defect_activated)
        # 表格上雙擊一列跟縮圖上雙擊一張是同一件事（R7）—— 同一支處理常式。
        self.results.table.defect_activated.connect(
            self.gallery_ctl._on_defect_activated)
        # 單擊（或方向鍵）一顆 → 主畫面帶過去，但**不搶焦點**（2026-09-09）。
        self.results.defect_selected.connect(
            self.gallery_ctl._on_defect_selected)
        self.gallery.selection_changed.connect(
            self.gallery_ctl._on_gallery_selection)
        # 回溯（PR-3）：點 score/bin/class → 算 trace 開面板；點面板上一項 →
        # 跳到產出它的卡（有區域就把那一塊亮起來）。
        self.results.trace_requested.connect(
            self.gallery_ctl._on_trace_requested)
        # **欄名 → 算它的那張卡**（F117 I6）。接 `partial` 不接一個新的方法：
        # 那一格的方法數是 `HARD_CAPS`，而內容本來就住在 `cross_links`。
        self.results.card_requested.connect(
            partial(cross_links.go_to_feature, self))
        self.results.truth_marked.connect(self._on_truth_marked)
        self.results.why_item_activated.connect(self.gallery_ctl._on_why_item)

    def _wire_workers(self) -> None:
        self.dataset_worker.loaded.connect(self._on_dataset_loaded)
        self.dataset_worker.failed.connect(
            lambda msg: (self._progress_done(),
                         self._status("Could not load dataset: %s" % msg, "error")))

        self.preview_worker.ready.connect(self._on_async_preview_ready)
        self.preview_worker.busy.connect(self._on_preview_busy)
        self.region_check_worker.ready.connect(
            lambda results: region_check.on_region_ready(self, results))
        self.region_check_worker.failed.connect(
            lambda msg: self._status("Region check failed: %s" % msg, "error"))
        self.preview_worker.failed.connect(
            lambda msg: self._status("Preview failed: %s" % msg, "error"))

        self.trial_worker.progress.connect(self.run_ctl._on_trial_progress)
        self.trial_worker.done.connect(self.run_ctl._on_trial_done_async)
        self.output_worker.done.connect(self.run_ctl._on_outputs_done)
        self.output_worker.failed.connect(self.run_ctl._on_outputs_failed)
        self.trial_worker.failed.connect(self.run_ctl._on_trial_failed)


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
        """Esc：放掉手上的東西（內容在 `studio_layout.clear_selection`）。"""
        studio_layout.clear_selection(self)

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
        """游標讀數 → 預覽區自己的標籤（**不碰狀態列**，見 ``studio_layout.build_preview_pane``）。"""
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
        region_check.refresh_region_button(self)
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
            run_why = "No dataset loaded yet — use “Open data…” first."
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
            self._status(row["text"] or row["title"],
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
                issues = self.model.validate(self.dataset)
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
            out[nid] = (wording.issue_line(issue, self.model), str(issue.level))
        return out

    def _refresh_pipeline(self) -> None:
        # ⚠ **lint 只跑一次**，畫布的警示點與 Problems 列吃同一份（U2）。
        # 各算一次的那天，畫面上會有一張卡是紅的而清單說沒有問題。
        try:
            issues: Sequence[Any] = self.model.validate(self.dataset)
        except Exception:  # 顯示用
            issues = []
        self.problems.set_issues(issues, self.model)
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
            issues = self.model.validate(self.dataset)
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
                best = (wording.issue_line(issue, self.model), lvl)
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
        # ⚠ **收起來的樹上沒有菱形**（F117 A5）：面板那句「去點一顆菱形」
        # 要跟著畫布的狀態換一句話。`set_tree_collapsed` 自己會 refresh。
        # ⚠ `getattr`：這一支在**畫布還沒組出來之前**就會被叫到一次。
        # ⚠ 那個屬性叫 `pipeline` —— 第一版寫成 `canvas`，而 `getattr` 的
        # 預設把它吞掉了：那一版永遠回 False，A5 等於沒修而測試也不會紅。
        self.decide_panel.set_tree_collapsed(
            getattr(getattr(self, "pipeline", None), "tree_collapsed",
                    bool)())
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
        self._status("Added “%s”%s"
             % (node_id, canvas_edges.unmet_needs(self, node_id)))
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
                     % (new_id, nid,
                        canvas_edges.unmet_needs(self, new_id)))
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

    def _on_node_toggled(self, node_id: str, enabled: bool) -> None:
        self.model.set_enabled(str(node_id), bool(enabled))

    def _on_move_requested(self, node_id: str, delta: int) -> None:
        self.model.move(str(node_id), int(delta))

    # ---- 畫布連線（F7-6；F7-18 起帶著影像流）-------------------------------
    def _on_remove_requested(self, node_id: str) -> None:
        """刪掉一張卡（內容在 `ui/canvas_edges.py` —— 它整件事都是線的事）。"""
        canvas_edges.remove_card(self, node_id)

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
            view.select_card(node_id)
        self._fill_param_form(node_id)
        self.stack.setCurrentWidget(self.param_form)
        self.gauge_note.setText("")              # 儀表又是這張卡的了（P1-7）
        self.bottom_stack.setEnabled(True)
        self._sync_params_pane()
        region_check.refresh_region_button(self)
        # 右下角換成這張卡的儀表（F7-17）。**參數要一起給**：`roi_reference`
        # 一個 key 有四種面板，由 ``method`` 決定（F30）。
        self.gauges._install_inspector(node.step, node.params)
        self.gauges._refresh_inspector(self._last_result)
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

    #: 資料那張卡（Input，`load_patch`）的鈕上寫什麼 —— 跟空白畫面上那一顆
    #: 同一個字（F121 期 4 起入口只有一顆，`scope.INPUT_SOURCES[0].title`；
    #: `tests/test_ui_one_open.py` 守著兩邊一樣）。
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
                canvas_edges.connect(self, src, nid, name, str(param))
            return
        src = self.model.stream_producer(name, before_node=nid)
        if src:
            canvas_edges.connect(self, src, nid, name, str(param))

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
        """入口卡上那顆鈕：附加檔、第二份 lot、主資料各自開自己的對話框。

        主資料那一顆以前開一張選單（`scope.INPUT_SOURCES` 一列一項）；F121 期 4
        起入口只有一顆，**按下去就是那一顆**，不先問「你要開哪一種」。
        """
        nid = self.selected_node
        node = self.model.nodes.get(nid) if nid else None
        if node is None:
            return
        att_key = self._ATTACHMENT_CARDS.get(node.step)
        if att_key:
            # ⚠ 名字是**組出來的**（`_on_open_` ＋ 表裡那個 key），所以沒有任何
            # 靜態掃描找得到它 —— F116 第 4 步搬走 `_on_open_gds` 的時候，
            # `ruff`、`studio_surface --check`、`import` 全部是綠的，只有
            # 「選到 layout(GDS) 卡再按那顆鈕」那一條路會 AttributeError。
            getattr(self.attach_ctl, "_on_open_%s" % att_key)()
            return
        if node.step in self._PAIR_CARDS:
            self.attach_ctl._on_open_pair_source(nid)
            return
        open_dialogs.open_source(self, scope.INPUT_SOURCES[0].key)

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
                n = spec.extent_px(node.params.get(spec.name, spec.default))
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
            self._status("Select a card on the canvas before editing its settings.", "error")
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
            canvas_edges.say_fallout(self, says)
            self.attach_ctl._after_carry_param(node_id, str(name))
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
        self.attach_ctl._sync_pair_fields(
            str(node.params.get("source", "") or ""))
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
                self._status("Could not load dataset: %s" % wording.failure("studio.load_dataset", e), "error")
                return False
            return self._on_dataset_loaded(ds)
        if not self.dataset_worker.start(path, tiff):
            self._status("A dataset is already loading — please wait.")
            return False
        self._progress_busy("Loading %s…" % os.path.basename(path))
        self._status("Loading: %s" % os.path.basename(path))
        return True

    def load_folder_path(self, folder: Any, sync: bool = False) -> bool:
        """載入一個**資料夾的單張影像**（F11 Input-3）。

        沒有 KLARF、沒有座標。每個影像檔一顆 defect，多頁 TIFF 在這條路上只讀得到
        第一頁（ingest 會為此發一句警告）。
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
                self._status("Could not load folder: %s"
                             % wording.failure("studio.load_folder", e), "error")
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
                self._status("Could not load image: %s"
                             % wording.failure("studio.load_image", e), "error")
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
        self.attach_ctl._carry_main_columns()
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

        # route 鍵跟著資料走 —— **只在畫布是空的時候**（F121 期 1）。
        #
        # 以前的條件是「使用者還沒動過」（`not dirty`），而一份**剛開的 recipe**
        # 也是沒動過 —— 於是先開 recipe 再開資料，它那條 route 會被**默默改名**
        # 成資料的型別，`Ctrl+S` 就改寫了原檔。現在 route 鍵只是標籤
        # （`route_for`：只有一條就跑那一條），所以畫布上有卡的時候一個字都
        # 不動；空白畫布才順手把鍵名改成資料的型別（存出去的 JSON 讀起來對）。
        ds_kind = str(getattr(dataset, "kind", self.model.kind))
        if ds_kind != self.model.kind:
            if not self.model.node_order:
                self.model.kind = ds_kind
                self.model.dirty = False      # 換 route 不算「使用者改過」
                # ⚠ **換 kind 必須重畫**：`model.kind` 是直接設的屬性，不會
                # 通知 listener（「畫布跟實際對不起來」的第一層就是少了這一行）。
                self._refresh_all()
            elif (getattr(self.model, "route_by", None) is None
                  and route_for(self.model.to_recipe(), ds_kind) is None):
                # 只剩手寫的多型別 recipe 走得到這裡：它的每一條都綁著一種資料，
                # 而這一種沒有。
                warn.insert(0, (
                    "this recipe has a separate pipeline for each kind of data "
                    "(%s) and none for %s data; open a recipe for it, or start "
                    "a new pipeline."
                    % (", ".join(self.model.route_keys()), ds_kind)))
        added = self._adopt_source_for()

        # `channel_map` 的表格要照「這批資料一顆有幾張圖」排列數（F11），並露出
        # 「照這份資料填」（F121 期 3）—— 資料的事實，在這裡講一次。
        self.param_form.set_data_item(items[0] if items else None)

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

    def _adopt_source_for(self) -> str:
        """畫布是空的 → 補上 Input 卡，名字表照資料填（回它的顯示名）。

        開窗時不放（F11 Enhance-4，使用者：「Load image 卡片改成預設沒有……add
        才會出現」），**載入資料的那一刻才放** —— 那時候一顆有幾張、叫什麼已經
        不是猜的，是資料說的（`RecipeModel.add_starter_input`，F121 期 2）。
        規則：**空白畫布才補，而且把補了什麼講出來**（狀態列）；使用者已經蓋了
        一條 pipeline 的話，那是他的東西，這一段一個字都不准動它。
        """
        if self.model.node_order or self.model.dirty:
            return ""
        items = self._items()
        try:
            nid = self.model.add_starter_input(items[0] if items else None)
        except KeyError:                 # pragma: no cover — 卡片庫壞了才會發生
            return ""
        # 補上來的那張卡不算「使用者做過的一步」：Ctrl+Z 不該把它退掉，關窗也
        # 不該因此問「要存檔嗎」（同 `RecipeModel.starter` 的理由）。
        self.model.dirty = False
        self.model.clear_history()
        self.select_node(nid)
        return str(get_step(RecipeModel.STARTER_STEP).label)

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
            self._status("No dataset loaded yet — use “Open data…” first.", "error")
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
            self._status("Could not load recipe: %s" % wording.failure("studio.load_recipe", e), "error")
            return False
        # 舊格式**升級了就要說**（U17）：畫布上多出來的線與拆開的卡是遷移補的，
        # 而使用者只會看到「這跟我上次存的不一樣」。讀原始 JSON 再比一次是為了
        # 拿到 `Recipe.load` 已經丟掉的那一半（版本號與原本的線）。
        upgraded = self._describe_upgrade(path, recipe)
        ds_kind = str(getattr(self.dataset, "kind", "")) if self.dataset else ""
        # 編哪一條：資料會跑的那一條（`route_for`，F121 期 1）；挑不到退回第一條。
        kind = route_for(recipe, ds_kind) if ds_kind else None
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
        if ds_kind and route_for(recipe, ds_kind) is None \
                and getattr(recipe, "route_by", None) is None:
            self._status("Loaded recipe “%s”, but it has no '%s' route — "
                         "preview and trial runs will fail."
                         % (self.model.recipe_id, ds_kind))
        # **換 recipe 也要重填 `carry`**（F117 F3 查到的洞）。以前只有「換一份
        # 資料」與「改那一格」會填 —— 於是「先開 lot、再開一份有勾 `carry` 的
        # recipe」那條路上，那幾欄從來沒有被填過，而症狀是**每一顆都失敗**，
        # 訊息說「這份 lot 沒有那個欄位，它有的是：(nothing)」。
        #
        # ⚠ 那句話看起來像 KLARF 的問題，而它其實是「沒有人去填」。出貨的
        # recipe 打開座標的那一刻，`test_ui_template_library` 當場抓到。
        self.attach_ctl._carry_main_columns()
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
            self._status("Could not save: %s" % wording.failure("studio.save", e),
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
                self._status("No dataset loaded yet — use “Open data…” first.", "error")
            return False

        recipe = self.model.to_recipe()
        upto = self.selected_node if self.selected_node in self.model.nodes else None
        if self._preview_whole_route():
            upto = None                  # Output 卡／判定樹：跑到底，連判定
        # `kind` 是**資料的身分**（load 卡讀 `meta["_dataset_kind"]`），route 由
        # `run_defect` 自己解（有 `route_by` 逐顆看欄位，沒有就 `route_for`）——
        # 所以一律傳資料的型別，不傳正在編的 route 鍵（F23 期2；F121 期 1 起
        # 沒有 `route_by` 的也一樣：鍵名只剩標籤，跟整批跑的是同一條）。
        kind = str(getattr(self.dataset, "kind", "") or self.model.kind)
        if sync:
            try:
                result = PreviewWorker.run_sync(recipe, item, kind,
                                                upto_node=upto,
                                                sources=self.sources_for_run())
            except Exception as e:  # UI 邊界
                self._status("Preview failed: %s" % wording.failure("studio.preview", e), "error")
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

        self.overlays._populate_streams(images)
        self.overlays._show_current_stream()

        self.gauges._refresh_inspector(result)
        highlight = self.gauges._highlight_features(result)
        self.feature_panel.set_model(
            self.gauges._feature_model(result, highlight))
        score = getattr(result, "score", None)
        # 名字（X7）與好壞（F119）**一起查** —— 兩張表分開查的那天，畫面上
        # 那一行字與它的顏色會來自不同的葉子（`verdict_words` 的說明）。
        verdict_bin = getattr(result, "bin", None) if score is not None else None
        name, outcome = verdict_words(getattr(self.model, "decide", None),
                                      verdict_bin)
        self.verdict.set_verdict(verdict_bin, label=name, outcome=outcome)
        self.verdict_score.setText("" if score is None
                                   else "score %s" % format_feature_value(score))
        self.verdict_note.setText(verdict_note(
            self.selected_node, verdict_bin, getattr(result, "ok", False)))
        self._show_decide_path(result)

        who = wording.card(self.model, self.selected_node)
        if not ran:
            # 兩種「沒有東西可看」要講不同的話，因為下一步不一樣：
            #   跑起來了但失敗   → 講**那個錯誤**（它自己就帶著怎麼修）；
            #   根本沒跑到       → 講**怎麼接線**（lint 對這件事早就有一句可以照做
            #                      的話，用它而不是再寫一份）。
            tr = self._selected_trace(result)
            err = wording.trace_error_text(tr, self.model) if tr else ""
            if err:
                self._status("Preview problem: %s" % err, "error")
            else:
                why = self._node_problems().get(self.selected_node or "",
                                                ("", ""))[0]
                self._status(why or "“%s” did not run this time, so there "
                             "is nothing to show for it yet." % who, "error")
        elif not getattr(result, "ok", False):
            # 這張卡跑過了，是**後面**某張卡失敗 —— 那時候畫面上的影像有意義
            # （診斷比清空有用），所以留著。
            self._status("Preview problem: %s"
                         % (getattr(result, "error", None) or "unknown error"))
        elif self.selected_node:
            self._status("Preview: stopped after “%s” (%d image streams)"
                         % (who, len(images)))
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
        可能叫 `single`、`test` 或使用者自己取的任何名字（Input 卡的名字表是
        他填的），而寫死 `ref`/`test` 的話那條路永遠拿不到圖。
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

    # ==================================================================== #
    # 跑完了，畫面怎麼變（**怎麼發動、怎麼寫在 `ui/run_controller.py`**）
    # ==================================================================== #
    # 這一段只剩 `_apply_trial_results` —— 而它留在這裡是刻意的（F116 第 5 步）：
    # 它叫的那一串 `_refresh_*` 跟「這批數字怎麼變成一句話」是**交織**的，而且
    # 每一段前面都釘著一句「順序反過來就會畫出上一批的顏色」。把它搬去
    # controller 再發 signal 回來，等於把那個順序拆成好幾段再拼回去。
    def _apply_trial_results(self, results: Sequence[Dict[str, Any]],
                             elapsed: float) -> None:
        results = list(results or [])
        self._progress_done()
        self.trial_results = results
        # **這一批的底稿**：Re-run 從這裡重判、Write outputs 拿它對「結果還是不是
        # 畫面上這份 recipe 的」（`RunController.snapshot`，F122 搬過去）。
        self._last_run = self.run_ctl.snapshot(results)
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
        self.gallery_ctl._populate_gallery(results)
        self.gauges._refresh_inspector(self._last_result)   # 儀表吃的是整批（F7-17）
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
            n_out = self.run_ctl._enabled_output_cards()
            if n_out:
                msg = ("%s  ·  Run only - nothing written yet. When the "
                       "numbers look right, press “Write outputs” in Results "
                       "to let the %d Output card%s write."
                       % (msg, n_out, "" if n_out == 1 else "s"))
        self._status(msg)
        if write and results:
            self.run_ctl._write_outputs(results)
        # F7-5：結果一到就把 Results 視窗帶出來 —— 使用者按 Run 想看的就是這個
        self.results.set_summary(
            summarize_run(len(results), ok, elapsed, self.trial_scores, results))
        # X1：baseline 那一行吃的是**引擎判出來的 bin**（不是某個門檻重算的），
        # 因為使用者剛剛看到的就是它。拖門檻線時 `_refresh_bin_summary` 會用
        # 那個門檻再餵一次。
        self._publish_run_snapshot(None)
        self.results.set_run_all_enabled(bool(results),
                                         self.run_ctl._enabled_output_cards())
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
    # ==================================================================== #
    # 首次開啟導覽 + 範例 recipe 庫（M6）
    # ==================================================================== #
    def _open_windows(self):
        """Studio 的頂層子視窗（U15 那張表上准開的）—— 關窗時一起關。"""
        return [("Results", getattr(self, "results", None)),
                ("Region check", getattr(self, "region_window", None)),
                ("Uniformity charts",
                 getattr(self.gauges, "_charts_window", None))]

    def show_welcome(self, force: bool = False) -> Optional[Any]:
        """開（或重開）首次導覽。

        ``force=False`` 時尊重「不再顯示」（勾過就回 ``None``）；``force=True``
        不管那個勾（工具列的 Help 鈕 2026-09-24 拿掉了，現在只有測試這樣叫）。對話框是**非 modal** 的，所以這個方法
        永遠會馬上回來 —— 測試可以直接拿回傳值來按鈕。
        """
        if not force and welcome_disabled():
            return None
        dlg = self.welcome_dialog
        if dlg is None:
            dlg = WelcomeDialog(self)
            dlg.demo_requested.connect(self._on_demo_requested)
            dlg.open_klarf_requested.connect(
                partial(open_dialogs.open_source, self,
                        scope.INPUT_SOURCES[0].key))
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
            self._status("Could not make the sample data: %s" % e, "error")
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
            "is on the right. Next, use “Open data…” to switch to your own data.")
        return True

    # ==================================================================== #
    # 對話框（測試不走這條路）
    # ==================================================================== #
    # ---- 三格「用選的」要的答案（F15-2）------------------------------------
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
        return bool(open_dialogs.save_recipe(self))

    def showEvent(self, event) -> None:  # Qt hook
        super().showEvent(event)
        # 中欄的畫布/設定比例第一次 show 才套 —— setSizes 要有實際高度才
        # 算得出來（見 `studio_layout.build_body` 的說明）。只做一次：之後的比例是使用者
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

    # ==================================================================== #
    # 門面（F116）
    # ==================================================================== #
    # 搬進 controller 的方法裡，**測試與其他模組用得多**的那幾個在這裡留一行
    # 轉呼叫（F116 §3-3）。用得少的沒有門面 —— 門面也算方法數，而那一格天花板
    # 只准往下。

    def inspector(self) -> Optional[Any]:
        """目前掛著的卡片儀表（沒有就 None）。"""
        return self.gauges.inspector()

    def bottom_page(self) -> int:
        return self.gauges.bottom_page()

    def open_region_check(self, n: Optional[int] = None,
                          sync: bool = False) -> bool:
        """把選取節點定義的區域畫到前 N 顆上（內容在 `ui/region_check.py`）。"""
        return region_check.open_region_check(self, n, sync)

    @property
    def profile_panel(self) -> Any:
        """投影曲線面板（沒有的話是一個空的替身 —— 見 `GaugePanel`）。"""
        return self.gauges.profile_panel

    def profile_panel_visible(self) -> bool:
        return self.gauges.profile_panel_visible()

    def set_compare(self, on: bool) -> bool:
        """開／關並排的第二張圖（內容在 `ui/preview_overlays.py`）。"""
        return self.overlays.set_compare(on)

    def _on_edge_added(self, src: str, dst: str, stream: str = "",
                       dst_in: str = "") -> None:
        """拉一條線（規則在 `ui/canvas_edges.py` —— 鐵則 10 的主場）。"""
        canvas_edges.on_edge_added(self, src, dst, stream, dst_in)

    def _connect(self, src: str, dst: str, stream: str,
                 dst_in: str = "") -> None:
        canvas_edges.connect(self, src, dst, stream, dst_in)

    def _on_edge_removed(self, src: str, dst: str, stream: str = "",
                         dst_in: str = "") -> None:
        canvas_edges.on_edge_removed(self, src, dst, stream, dst_in)

    def run_trial(self, n: int, workers: Optional[int] = 1,
                  sync: bool = False, cache_dir: Optional[Any] = None,
                  write_outputs: bool = False) -> bool:
        """跑前 N 顆（內容在 `ui/run_controller.py`）。**不寫任何檔案。**"""
        return self.run_ctl.run_trial(n, workers, sync, cache_dir, write_outputs)

    def run_all(self, sync: bool = False) -> bool:
        """跑整批。**一樣不寫** —— 寫是 `write_outputs()`（鐵則 11）。"""
        return self.run_ctl.run_all(sync)

    def write_outputs(self, sync: bool = False) -> bool:
        """把現在這批結果照 Output 卡寫出去（鐵則 11 的「另一個動作」）。"""
        return self.run_ctl.write_outputs(sync)

    def rerun(self, sync: bool = False) -> bool:
        """Results 上的「Re-run」—— 只重判或整批重跑（`batch.rerun_decision`）。"""
        return self.run_ctl.rerun(sync)

    def show_gallery(self) -> None:
        """開 Results 視窗（工具列那顆鈕與 Ctrl+Shift+R 接的就是這一行）。"""
        self.gallery_ctl.show_gallery()

    def results_visible(self) -> bool:
        return self.gallery_ctl.results_visible()

    def compare_enabled(self) -> bool:
        """並排比對開著嗎。

        ⚠ 這一支**不只是給測試用的門面**：`GaugePanel` 要知道畫面上現在看的是
        一條流還是兩條（底下的直方圖跟著畫幾張），而 controller 之間不直接互叫
        （F116 §3-2）—— 它走的就是這一行。
        """
        return self.overlays.compare_enabled()

    def region_overlay_names(self) -> List[str]:
        return self.overlays.region_overlay_names()

    def heat_tiles(self, stream: Optional[str] = None):
        return self.overlays.heat_tiles(stream)

    def _focus_box_index(self, boxes: Sequence[Sequence[float]]) -> int:
        return self.overlays._focus_box_index(boxes)

    def _on_calibrated(self, result: Any) -> None:
        """一鍵校正量完了（`calibrate_worker.ready` 接的就是這一行）。"""
        self.gauges._on_calibrated(result)

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
        # ⚠ **名單不寫在這裡**（F117 G9）：這裡以前列六個 worker，而視窗身上
        # 有八個 —— 漏掉的那兩條在關程式時是
        # `QThread: Destroyed while thread is still running`。現在
        # `shutdown_window` 自己去找，加第七個的人什麼都不必記得。
        shutdown_window(self)
        super().closeEvent(event)
