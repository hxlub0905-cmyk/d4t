# ADEPT Studio Results 視窗 — authored 2026-07-28 (F7-5).
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
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QWidget,
)

from .gallery import GalleryPanel
from .widgets import HistogramWidget, apply_button_cursors

__all__ = ["ResultsWindow"]


class ResultsWindow(QMainWindow):
    """一批結果的檢視：Gallery（上）+ 分數分佈（下）+ 輸出入口。

    本視窗**不自己驅動任何東西** —— 所有互動都轉成訊號交給
    :class:`~adept.ui.studio.StudioWindow`，跟 ``WelcomeDialog`` 同一個慣例。
    這樣它可以單獨測，Studio 也可以在沒有它的情況下跑完整流程。
    """

    export_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ADEPT — Results")
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

        self.btn_export = QToolButton(self)
        self.btn_export.setText("Export…")
        self.btn_export.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setObjectName("primary")
        self.btn_export.setToolTip(
            "Write these results back to KLARF, or produce reports and overlays")
        self.btn_export.clicked.connect(self.export_requested)
        bar.addWidget(self.btn_export)
        self.set_export_enabled(False)      # 還沒有結果（同 A1 的可用性規則）

        self.gallery = GalleryPanel(self)
        self.histogram = HistogramWidget(self)
        self.histogram.setMinimumHeight(150)

        split = QSplitter(Qt.Vertical, self)
        split.addWidget(self.gallery)
        split.addWidget(self.histogram)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        split.setSizes([500, 190])
        self.splitter = split
        self.setCentralWidget(split)
        self.setStatusBar(QStatusBar(self))
        apply_button_cursors(self)

    # ---- 對外 -------------------------------------------------------------
    def set_summary(self, text: str) -> None:
        """工具列左側的一句話（「跑了幾顆、成功幾顆、花多久」）。"""
        self.summary_label.setText(str(text or ""))

    def summary_text(self) -> str:
        return self.summary_label.text()

    def set_export_enabled(self, enabled: bool) -> None:
        self.btn_export.setEnabled(bool(enabled))
        self.btn_export.setToolTip(
            "Write these results back to KLARF, or produce reports and overlays"
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
                  scores: Sequence[Any] = (), n_no_verdict: int = 0) -> str:
    """Results 工具列那一行文字（Studio 與測試共用，避免兩邊寫法漂移）。

    ``n_no_verdict`` = **跑得好好的、但沒有任何一張判定卡給結論**的顆數
    （F9 Phase 3d）。它們算在 ``n_ok`` 裡 —— 那沒有錯，它們確實沒有失敗 ——
    但如果只說 ok，這一整批就是「看起來全部跑完了」，而下面那個分數範圍
    其實只涵蓋其中一部分。**沒有結論不是失敗，但它也不是有結論。**
    """
    n_fail = int(n_total) - int(n_ok)
    text = "%d defects · %d ok · %d failed · %.1f s" % (
        int(n_total), int(n_ok), n_fail, float(elapsed))
    if int(n_no_verdict) > 0:
        text += " · %d with no verdict" % int(n_no_verdict)
    vals = [float(s) for s in (scores or ()) if s is not None]
    if vals:
        text += "   score %.4g – %.4g" % (min(vals), max(vals))
    return text
