# 版面模式：畫布在上、工作台在下 — authored 2026-09-08 (F100).
"""``WorkbenchLayout`` —— Build / Tune 兩種版面的**狀態與幾何**，不建 widget。

主視窗的版面（F100 v3，`docs/history/plans/F100-workbench-layout.md` §8）::

    ┌─庫─┬──────── 畫布（導覽，一排卡的高度）────────┬── 預覽影像 ─────────┐
    │rail│                                           │  Verdict · score    │
    │    ├───────────────────────────────────────────┼─────────────────────┤
    │    │ 設定區（吃滿中欄）                          │  儀表板             │
    └────┴───────────────────────────────────────────┴─────────────────────┘

* **Build** —— 工作台與右欄都收到 0，畫布吃滿。看全貌、接線、排版。
* **Tune** —— 工作台開著（**開窗就開著**）、右欄開著，畫布保底
  :data:`CANVAS_MIN_PX`、預設 :data:`CANVAS_SHARE_TUNE`；右欄上下的比例
  預設 :data:`IMAGE_SHARE_TUNE`，拖過記得住。調參數、看影像、看圖。

⚠ **第一版（同一天早上）畫布是吃滿全寬的**，影像跟設定區、儀表板擠在下面
同一列。1366×768 上那一列三格都小（影像 330×250）—— 調參數是最高頻的迴圈，
而它要的三樣東西全變小了。畫布要的是**寬度**不是面積，而且 Tune 裡它是導覽
（要看全貌有 Build）。所以 v2 把影像還給右欄、全高。

為什麼是一個獨立的類別而不是 `StudioWindow` 的幾支方法：`studio.py` 是這個 repo
唯一會自己長大的檔案（`CLAUDE.md` §4、`tests/test_size_ceilings.py`），而版面
模式的邏輯——哪一根 splitter 設成多少、記在哪一格 QSettings、什麼時候收卡片庫
——跟「接訊號、轉呼叫」不是同一件事。這裡純幾何，只碰 splitter 與卡片庫的
公開 API，所以測試可以不開整個 Studio 就問它。

⚠ ``QSplitter.setSizes`` 要 widget **真的排過版**才算得出來（`docs/PITFALLS.md`
的老坑）——所以 :meth:`apply` 不在建構期呼叫，主視窗的 ``showEvent`` 第一次
show 才套（跟 U5 之前一樣）。
"""
from __future__ import annotations
from d4t.core.log import swallowed

from typing import Callable, List, Optional, Sequence

__all__ = [
    "WorkbenchLayout", "MODES", "CANVAS_MIN_PX", "CANVAS_SHARE_TUNE",
    "COLUMN_STRETCH", "SPLIT_KEYS", "WORKBENCH_COLUMNS_KEY",
    "PREVIEW_SHARE_TUNE", "ROOT_COLUMNS_KEY", "IMAGE_SHARE_TUNE", "RIGHT_SPLIT_KEY",
]

#: 兩種版面。`tune` 是預設——開窗看到的就是它。
MODES = ("build", "tune")
#: Tune 模式畫布的保底高度（px）。768 高的螢幕扣掉工具列、Verdict 列、Problems
#: 列與狀態列之後主欄約 600 px，200 就是評審說的「35%」。用 px 不用比例，因為
#: 保底要跟著螢幕走：1080 的螢幕上 35% 是 300 px，而畫布在那裡不需要更高。
CANVAS_MIN_PX = 200
#: Tune 模式畫布預設佔主欄的比例（使用者拖過之後記他的）。
#:
#: ⚠ **0.40 → 0.50**（F117 A4，2026-09-20）。走查量的：Tune 的畫布只剩約
#: 300 px 高，七張卡就縮到 50%，副標與埠名讀不到 —— 而**同一份 recipe 在
#: Build 模式的 61% 是讀得到的**。那個數字是評審給的，所以這一格照它回推：
#: 縮放大致跟受限的那一邊成正比，50% → 61% 是 ×1.22，0.40 × 1.22 ≈ 0.49。
#:
#: ⚠ **只動預設，不動 `CANVAS_MIN_PX`**：保底那一格是小螢幕的最後一道防線
#: （它自己的說明寫著 768 高的螢幕上 200 就是上一輪評審說的 35%），而這一輪
#: 問的是「預設分得夠不夠」，不是「最壞能多壞」。拖過的人照樣拿他自己的值。
CANVAS_SHARE_TUNE = 0.50
#: 工作台兩格（設定區｜儀表板）的伸縮比。設定區裝的是可以拖的滑桿，儀表是讀
#: 的東西。
COLUMN_STRETCH = (3, 2)
#: Tune 模式右欄（預覽影像）預設佔 root 的比例；Build 收到 0。
PREVIEW_SHARE_TUNE = 0.34
#: root 三欄的寬度存在哪一格（只在 Tune 存：Build 的右欄是 0，不是使用者調的）。
ROOT_COLUMNS_KEY = "ui/columns_f100v2"
#: 右欄「影像／儀表」預設影像佔幾成（v3）；拖過之後記在 :data:`RIGHT_SPLIT_KEY`。
#: 影像要的是高度、直方圖要的是寬度——右欄的寬度兩個都拿得到，高度給影像多一點。
#:
#: ⚠ **它要比 :data:`CANVAS_SHARE_TUNE` 小**，而那不是美觀問題：儀表住在右欄
#: 的下格、設定區住在中欄的下格，而 U8 的驗收條件是**那兩塊左右相鄰、同一條
#: 視線**（`test_ui_layout_modes::test_they_are_actually_side_by_side_on_screen`
#: 真的去量座標）。儀表的上緣＝影像的高度，設定區的上緣＝畫布的高度 ——
#: 影像佔得比畫布多的那一刻，儀表就整塊掉到設定區下面去了。
#: 2026-09-20（F117 A4）：畫布從 0.40 升到 0.50，這一格跟著從 0.50 降到 0.45。
IMAGE_SHARE_TUNE = 0.45
RIGHT_SPLIT_KEY = "ui/right_split_f100v3"
#: 兩種模式各自的「畫布 / 工作台」比例存在哪一格 QSettings。
#:
#: **兩格而不是一格**（U5 的理由沒變）：使用者在 Build 裡把畫布拉高、在 Tune 裡把
#: 工作台拉高，那是兩個不同的偏好。
#: ⚠ Tune 那一格是**新名字**：舊那一格（``ui/canvas_split``）存的是「畫布 2 /
#: 設定 3」，套到新版面上畫布會低於保底。換名字等於升級那一天重設一次——
#: 代價寫在計畫書 §6。
SPLIT_KEYS = {"build": "ui/canvas_split_build",
              "tune": "ui/canvas_split_tune_f100"}
#: 工作台三格的寬度存在哪一格。
WORKBENCH_COLUMNS_KEY = "ui/workbench_columns"


class WorkbenchLayout:
    """Build / Tune 的狀態機。

    ``column`` 是直向的 QSplitter（``widget(0)`` 畫布、``widget(1)`` 工作台），
    ``workbench`` 是工作台那根橫向的 QSplitter（設定區｜儀表板｜預覽影像）。
    ``load`` / ``save`` 是主視窗那兩支讀寫 QSettings 的函式（測試時 ``load``
    永遠回 ``None``，那是它自己的規矩）。
    """

    def __init__(self, column, workbench, pipeline, library=None, *,
                 root=None, preview_index: int = 2, right=None,
                 load: Optional[Callable[[str, int], Optional[List[int]]]] = None,
                 save: Optional[Callable[[str, Sequence[int]], None]] = None):
        self.column = column
        self.workbench = workbench
        self.pipeline = pipeline
        self.library = library
        #: root 那根橫向 splitter（``[卡片庫, 畫布/工作台, 預覽影像]``）；
        #: 沒給就不管右欄（純幾何測試）。
        self.root = root
        self.preview_index = int(preview_index)
        #: 右欄那根直向 splitter（``[影像, 儀表]``）；沒給就不管（v2 以前、純幾何測試）。
        self.right = right
        self._right_applied = False
        self._load = load or (lambda _key, _n: None)
        self._save = save or (lambda _key, _sizes: None)
        self.mode: str = "tune"
        #: 工作台現在攤開著嗎（**明確狀態**，不去問 ``isVisible``）。
        #: Tune 模式開窗就是 True——影像住在裡面。
        self.open: bool = True
        self._columns_applied = False
        self._root_applied = False
        #: 右欄收起來之前多寬（Build → Tune 要還回同一個寬度）。
        self._preview_w = 0
        pipeline.setMinimumHeight(CANVAS_MIN_PX)
        for i, s in enumerate(COLUMN_STRETCH):
            if i < workbench.count():
                workbench.setStretchFactor(i, s)
        # 設定區不准被拖到 0：那是使用者現在在改的東西。儀表板可以（它是讀的
        # 東西，有人會想把設定區拉寬）。
        if workbench.count():
            workbench.setCollapsible(0, False)

    # ---- 查詢 ------------------------------------------------------------
    def total(self) -> int:
        return int(sum(self.column.sizes()) or self.column.height())

    def canvas_share(self) -> float:
        """畫布現在佔主欄的比例（0–1）。"""
        sizes = list(self.column.sizes())
        tot = sum(sizes)
        return (sizes[0] / float(tot)) if tot else 0.0

    # ---- 換模式 ----------------------------------------------------------
    def apply(self, mode: str, remember: bool = True) -> str:
        """換版面。回真的套上去的那一個（不認得的名字什麼都不做）。

        ``remember=True`` 時先把**現在**這個模式的比例記下來——只記 Tune：
        Build 的「畫布 100% / 工作台 0」不是使用者調出來的比例，存下來下次
        照著還原他會看到一個從來沒有調成那樣的版面。
        """
        use = str(mode or "")
        if use not in MODES:
            return self.mode
        was = self.mode
        if remember and was == "tune" and self.open:
            sizes = list(self.column.sizes())
            if sum(sizes):
                self._save(SPLIT_KEYS["tune"], sizes)
        self.mode = use
        self._restore_columns()
        if use == "build":
            self.open = False
            self.column.setSizes([self.total(), 0])
            self._set_preview(0.0)
        else:
            self.open = True
            self._open_workbench()
            self._open_preview()
            self._open_right()
            # 從 Build 切過來：卡片區收成 rail，那 200 px 給工作台。**只在切換
            # 的時候**——開窗時卡片清單是空白狀態下第一眼要看的東西。
            if was == "build" and self.library is not None:
                try:
                    self.library.toggle_group(None)
                except Exception:  # 版面不准擋在卡片庫上
                    swallowed("workbench.apply")
        return use

    def set_open(self, on: bool) -> bool:
        """攤開／收起工作台（Tune 模式）。Build 模式下什麼都不做。"""
        if self.mode == "build":
            return False
        self.open = bool(on)
        if self.open:
            self._open_workbench()
        else:
            self.column.setSizes([self.total(), 0])
        return self.open

    def on_selection(self, has_selection: bool) -> None:
        """選到卡片：收起來的工作台要打開。取消選取**不**收——影像住在裡面。"""
        if self.mode == "tune" and has_selection and not self.open:
            self.set_open(True)

    # ---- 關窗 ------------------------------------------------------------
    def remember(self) -> None:
        """關窗時把使用者拖過的分隔線存起來。"""
        if self.mode == "tune" and self.open:
            sizes = list(self.column.sizes())
            if sum(sizes):
                self._save(SPLIT_KEYS["tune"], sizes)
            if self.root is not None:
                rs = list(self.root.sizes())
                if sum(rs):
                    self._save(ROOT_COLUMNS_KEY, rs)
            if self.right is not None:
                rr = list(self.right.sizes())
                if sum(rr):
                    self._save(RIGHT_SPLIT_KEY, rr)
        cols = list(self.workbench.sizes())
        if sum(cols):
            self._save(WORKBENCH_COLUMNS_KEY, cols)

    def preview_width(self) -> int:
        """右欄現在多寬（沒有 root、或收起來了就 0）。"""
        w = self._preview_widget()
        if w is None or not w.isVisibleTo(self.root):
            return 0
        sizes = list(self.root.sizes())
        return int(sizes[self.preview_index]) if len(sizes) > self.preview_index else 0

    def _preview_widget(self):
        if self.root is None or self.root.count() <= self.preview_index:
            return None
        return self.root.widget(self.preview_index)

    # ---- 右欄 --------------------------------------------------------------
    def _set_preview(self, width: float) -> None:
        """把右欄設成 ``width``（0 ＝ 收掉），多出來或少掉的寬度給中欄。

        收掉是**真的藏起來**（``hide``），不是 setSizes 到 0：一個有最小寬度的
        widget 被 setSizes 到 0 時 QSplitter 會把它撐回最小寬度，總和超過視窗，
        視窗跟著長（量到 1,993）。藏起來的 widget QSplitter 不算它。
        """
        w = self._preview_widget()
        if w is None:
            return
        if width <= 0:
            if w.isVisibleTo(self.root):
                self._preview_w = self.preview_width()
            w.setVisible(False)
            return
        w.setVisible(True)
        sizes = list(self.root.sizes())
        if len(sizes) <= self.preview_index:
            return
        mid = 1 if self.preview_index != 1 else 0
        if sum(sizes) <= 0:
            # showEvent 那一刻 splitter 還沒排過版（sizes 全 0）——用 root 的
            # 寬度自己算一份：卡片庫拿它的最小寬度，其餘給中欄與右欄。
            total = int(self.root.width())
            if total <= 0:
                return
            first = self.root.widget(0)
            lib_w = int(first.minimumWidth() or first.sizeHint().width()) \
                if first is not None and first is not w and self.preview_index != 0 else 0
            sizes = [0] * len(sizes)
            sizes[0] = lib_w
        total = sum(sizes) or int(self.root.width())
        sizes[mid] = max(0, sizes[mid] + sizes[self.preview_index] - int(width))
        sizes[self.preview_index] = int(width)
        # 四捨五入的餘數丟給中欄，總寬不變。
        sizes[mid] = max(0, sizes[mid] + total - sum(sizes))
        self.root.setSizes(sizes)

    def _open_preview(self) -> None:
        """右欄開著、而且是**對的寬度**。

        第一次（開窗）：存過就用存的，沒有就 :data:`PREVIEW_SHARE_TUNE`。
        ⚠ 建構期的 ``setSizes`` 在 show 之前算不出來（PITFALLS 的老坑），所以
        出廠比例要在這裡、show 之後套一次 —— 不套的話 QSplitter 用最小寬度
        猜出來的比例是「中欄 348、右欄 607」，影像比設定區與儀表加起來還寬。
        之後（Build → Tune）：還回收起來之前的寬度。
        """
        if self.root is None:
            return
        w = self._preview_widget()
        if w is None:
            return
        was_hidden = not w.isVisibleTo(self.root)
        if not self._root_applied:
            self._root_applied = True
            saved = self._load(ROOT_COLUMNS_KEY, self.root.count())
            w.setVisible(True)
            # 存下來的每一欄都要像一欄（≥ 100 px）：一份在 show 之前就關掉的
            # 視窗會存出 ``31,31,30`` 那種東西，套上去 Qt 按比例放大之後是
            # 「中欄 348、右欄 607」——影像比設定區與儀表加起來還寬。
            if saved and sum(saved) and min(saved) >= 100:
                self.root.setSizes(saved)
            else:
                total = sum(self.root.sizes()) or int(self.root.width())
                if total > 0:
                    self._set_preview(total * PREVIEW_SHARE_TUNE)
            return
        if was_hidden:
            total = sum(self.root.sizes())
            self._set_preview(self._preview_w or total * PREVIEW_SHARE_TUNE)

    def _open_right(self) -> None:
        """右欄上下（影像／儀表）的出廠比例，show 之後套一次；存過就用存的。"""
        if self.right is None or self._right_applied:
            return
        sizes = list(self.right.sizes())
        total = sum(sizes) or int(self.right.height())
        if total <= 0:
            return
        self._right_applied = True
        saved = self._load(RIGHT_SPLIT_KEY, self.right.count())
        if saved and sum(saved) and min(saved) >= 60:
            self.right.setSizes(saved)
            return
        top = int(total * IMAGE_SHARE_TUNE)
        self.right.setSizes([top, max(0, total - top)])

    # ---- internals ---------------------------------------------------------
    def _open_workbench(self) -> None:
        total = self.total()
        saved = self._load(SPLIT_KEYS["tune"], 2)
        if saved and sum(saved) and saved[0] >= CANVAS_MIN_PX:
            self.column.setSizes(saved)
            return
        canvas = max(CANVAS_MIN_PX, int(total * CANVAS_SHARE_TUNE))
        self.column.setSizes([canvas, max(0, total - canvas)])

    def _restore_columns(self) -> None:
        """工作台三格的寬度：存過就用存的，沒有就照 :data:`COLUMN_STRETCH`。
        只套一次——之後是使用者自己拖的。"""
        if self._columns_applied:
            return
        self._columns_applied = True
        n = self.workbench.count()
        saved = self._load(WORKBENCH_COLUMNS_KEY, n)
        if saved and sum(saved):
            self.workbench.setSizes(saved)
            return
        total = int(sum(self.workbench.sizes()) or self.workbench.width())
        if total <= 0:
            return
        weights = list(COLUMN_STRETCH[:n]) or [1] * n
        wsum = float(sum(weights)) or 1.0
        self.workbench.setSizes([int(total * w / wsum) for w in weights])
