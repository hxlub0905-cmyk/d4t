# d4t Studio Results 視窗 — authored 2026-07-28 (F7-5).
"""``ResultsWindow`` —— 跑完一批之後才有意義的東西，全部搬到這裡。

為什麼要拆出去
--------------
主視窗一直是四區塊 + 底部全寬直方圖，於是「編流程」與「看整批結果」兩種
模式擠在同一個畫面上。使用者的話是：**直方圖不是不重要，而是它不是必要 ——
主介面的分析區應該乾淨。**

拆的界線就在「這個東西要不要先跑過一批才有意義」：

===================  ==========================================
主視窗 Workspace     編流程 · 看單顆 · 調參數
Results 視窗         分數分佈 · Gallery · 輸出
===================  ==========================================

直方圖與 Gallery 都屬於後者，所以一起搬。Export 本來就是對話框，
按鈕也一併放進來 —— 「跑完 → 看分佈 → 掃縮圖 → 輸出」是同一段動線。

**秒回不能弄丟**
----------------
拖門檻線目前走的是 ``viewmodel.rebin()`` 的純計算路徑（不重跑影像）。
搬家之後訊號改成由本視窗轉發給 Studio，但走的仍是同一條路 ——
``threshold_changed`` 只重算 bin 數、放開才 ``threshold_committed`` 寫回 model。
這條性質有測試鎖（``tests/test_ui_results.py``）。

視窗而不是對話框
----------------
用 ``QMainWindow`` 是為了能有自己的工具列與狀態列，而且**非 modal** ——
使用者要能一邊看結果一邊回主視窗改參數。關掉它不會丟掉結果，
再跑一次或按主視窗的 Gallery 入口就會回來。
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .gallery import GalleryPanel
from .widgets import HistogramWidget, apply_button_cursors

__all__ = ["ResultsWindow"]


class ResultsWindow(QMainWindow):
    """一批結果的檢視：Gallery（上）+ 分數分佈（下）+ 整批入口。

    本視窗**不自己驅動任何東西** —— 所有互動都轉成訊號交給
    :class:`~d4t.ui.studio.StudioWindow`，跟 ``WelcomeDialog`` 同一個慣例。
    這樣它可以單獨測，Studio 也可以在沒有它的情況下跑完整流程。
    """

    run_all_requested = Signal()
    #: 下面那張圖現在要看哪一個東西（``SCORE`` 或一個 feature 名）。
    #: 這是 Spread 的新家（F18 第 2 步）—— 見 :meth:`_build_spread`。
    shown_feature_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("d4t — Results")
        self.setWindowFlag(Qt.Window, True)
        self.resize(980, 700)

        bar = QToolBar("Results", self)
        bar.setMovable(False)
        bar.setFloatable(False)
        self.toolbar = bar
        self.addToolBar(bar)

        self.summary_label = QLabel("No results yet.", bar)
        self.summary_label.setObjectName("paramHint")
        bar.addWidget(self.summary_label)

        spacer = QWidget(bar)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        # 試跑看起來對了之後，**下一步就是整批跑並寫出去** —— 所以那顆鈕在
        # 這裡（使用者正在看的是試跑的結果）。以前這一格是「Export…」，開一個
        # 輸出精靈；精靈拿掉之後（F16 Stage 5c）寫什麼、寫去哪住在畫布上的
        # Output 卡上，這顆鈕只負責「跑完整批然後照卡片寫」。
        self.btn_run_all = QToolButton(self)
        self.btn_run_all.setText("Run all & write")
        self.btn_run_all.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_run_all.setCursor(Qt.PointingHandCursor)
        self.btn_run_all.setObjectName("primary")
        self.btn_run_all.setToolTip(
            "Run every defect, then write whatever the Output cards say")
        self.btn_run_all.clicked.connect(self.run_all_requested)
        bar.addWidget(self.btn_run_all)
        self.set_run_all_enabled(False)     # 還沒有結果（同 A1 的可用性規則）

        self.gallery = GalleryPanel(self)
        self.histogram = HistogramWidget(self)
        self.histogram.setMinimumHeight(150)
        spread = self._build_spread()

        split = QSplitter(Qt.Vertical, self)
        split.addWidget(self.gallery)
        split.addWidget(spread)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        split.setSizes([500, 190])
        self.splitter = split
        self.setCentralWidget(split)
        self.setStatusBar(QStatusBar(self))
        apply_button_cursors(self)

    #: 下拉裡代表「分數」的那一項（不是 feature 名，所以用一個不可能撞名的字）。
    SCORE = "(score)"

    def _build_spread(self) -> QWidget:
        """分數/特徵的分佈圖，上面一條「要看哪一個」的選擇列（F18 第 2 步）。

        **Spread 的新家。** 它以前住在量測卡的儀表上，而那個位置在跑之前
        永遠是空的（使用者：「他在 run 之前都是空的」）。它真正回答的問題是
        「這個特徵分不分得開、門檻該設哪」—— 那是跑完之後才問得出來的問題，
        也是這個視窗存在的理由。

        分數與特徵的差別要說得出來：**門檻是分數的門檻**，所以看別的特徵時
        整張圖是唯讀的（`HistogramWidget.set_interactive`）。一條看起來能拖、
        拖了卻什麼都不會發生的線，比沒有線更糟。
        """
        host = QWidget(self)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QWidget(host)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 4, 8, 0)
        rl.setSpacing(8)
        title = QLabel("Spread of", row)
        title.setObjectName("paramHint")
        rl.addWidget(title)

        self.feature_combo = QComboBox(row)
        self.feature_combo.setMinimumWidth(190)
        self.feature_combo.addItem("Score", self.SCORE)
        self.feature_combo.setToolTip(
            "Which number to spread out across the batch. Squeezed into one "
            "bar means it separates nothing; two humps means there is "
            "something to cut between.")
        self.feature_combo.currentIndexChanged.connect(self._on_feature_pick)
        rl.addWidget(self.feature_combo)

        self.spread_hint = QLabel("", row)
        self.spread_hint.setObjectName("paramHint")
        self.spread_hint.setWordWrap(True)
        rl.addWidget(self.spread_hint, 1)
        lay.addWidget(row)
        lay.addWidget(self.histogram, 1)
        return host

    def set_features(self, names: Sequence[str]) -> None:
        """下拉裡可以選哪些特徵（跑完之後由 Studio 餵）。

        目前選著的那一個**留著** —— 使用者調了一輪參數再跑一次，最想看的
        通常就是同一個特徵，而下拉自己跳回「Score」等於每次都要重選。
        """
        keep = self.shown_feature()
        self.feature_combo.blockSignals(True)
        try:
            self.feature_combo.clear()
            self.feature_combo.addItem("Score", self.SCORE)
            for n in names:
                self.feature_combo.addItem(str(n), str(n))
            idx = self.feature_combo.findData(keep)
            self.feature_combo.setCurrentIndex(max(0, idx))
        finally:
            self.feature_combo.blockSignals(False)

    def shown_feature(self) -> str:
        data = self.feature_combo.currentData()
        return str(data if data is not None else self.SCORE)

    def show_feature(self, name: str) -> None:
        """程式化選一個（測試 / 外部呼叫用）。"""
        idx = self.feature_combo.findData(str(name))
        if idx >= 0:
            self.feature_combo.setCurrentIndex(idx)

    def set_spread_hint(self, text: str) -> None:
        self.spread_hint.setText(str(text or ""))

    def spread_hint_text(self) -> str:
        return self.spread_hint.text()

    def _on_feature_pick(self, _index: int) -> None:
        self.shown_feature_changed.emit(self.shown_feature())

    # ---- 對外 -------------------------------------------------------------
    def set_summary(self, text: str) -> None:
        """工具列左側的一句話（「跑了幾顆、成功幾顆、花多久」）。"""
        self.summary_label.setText(str(text or ""))

    def summary_text(self) -> str:
        return self.summary_label.text()

    def set_run_all_enabled(self, enabled: bool) -> None:
        self.btn_run_all.setEnabled(bool(enabled))
        self.btn_run_all.setToolTip(
            "Run every defect, then write whatever the Output cards say"
            if enabled else "No results yet — run a trial first.")

    def status(self, msg: str) -> None:
        self.statusBar().showMessage(str(msg))

    def status_text(self) -> str:
        return self.statusBar().currentMessage()

    def present(self) -> None:
        """顯示並拉到前面（已經開著就只是 raise，不會閃一下）。"""
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:      # noqa: D102 - Qt hook
        # 關掉不丟結果：下次再跑（或按主視窗的 Gallery 入口）就會回來。
        super().closeEvent(event)


def summarize_run(n_total: int, n_ok: int, elapsed: float,
                  scores: Sequence[Any] = ()) -> str:
    """Results 工具列那一行文字（Studio 與測試共用，避免兩邊寫法漂移）。"""
    n_fail = int(n_total) - int(n_ok)
    text = "%d defects · %d ok · %d failed · %.1f s" % (
        int(n_total), int(n_ok), n_fail, float(elapsed))
    vals = [float(s) for s in (scores or ()) if s is not None]
    if vals:
        text += "   score %.4g – %.4g" % (min(vals), max(vals))
    return text
