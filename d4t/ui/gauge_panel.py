# d4t UI — authored 2026-09-18 (F116 第 1 步).
"""右下角那一塊：**選哪張卡就換成那張卡的儀表**（F7-17）。

為什麼自己一個模組（`CLAUDE.md` §4：新的面板一律開新模組，`studio.py` 留給
接線）：這一族裡面是**內容**不是接線 —— 換卡片時怎麼換儀表、一鍵校正量完之後
哪些填得回去哪些要講原因、圖的視窗怎麼跟著當下那一顆走、曲線後面墊的是哪一條
流的分布。`studio.py` 那一格天花板**只准往下**，而 F116 第 1 步要走完
「`StudioWindow` 只留組裝與接線」那條路，於是這一族整個搬過來。

**行為零改動**（F116 §1 的非目標）：方法本體逐字搬，只把屬於視窗的
``self.x`` 換成 ``self.w.x``；屬於這一塊自己的狀態（``_inspector``、
``_charts_window``）跟著行為一起搬進來。

接線仍然留在 `studio.py`（`_wire_widgets` / `_wire_workers`）—— 這一支只提供
slot（F116 §3-4）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from PySide6.QtCore import QObject

from d4t.core.pipeline import get_step
from .inspectors import inspector_for

if TYPE_CHECKING:                      # 只給型別看：這一支不 import studio
    from .studio import StudioWindow


class GaugePanel(QObject):
    """右下角的卡片儀表。從 `StudioWindow` 搬來（F116 第 1 步）。"""

    def __init__(self, win: "StudioWindow") -> None:
        # ⚠ **一定要掛 parent**：controller 若不是視窗的 QObject 子物件、又沒有
        # 人握著它，Python 端會被回收，而接在它 bound method 上的 signal 會
        # **安靜地不再觸發**（不是例外 —— 畫面只是不動了）。
        super().__init__(win)
        self.w = win
        self._inspector: Optional[Any] = None      # 原 StudioWindow._inspector

    def show_bottom_page(self, index: int) -> None:
        """0 = 這張卡的儀表，1 = 特徵表。"""
        index = 1 if int(index) else 0
        if index == 0 and self._inspector is None:
            index = 1          # 這張卡沒有儀表 —— 不要給一片空白
        self.w.bottom_stack.setCurrentIndex(index)
        self.w.btn_tab_card.setChecked(index == 0)
        self.w.btn_tab_features.setChecked(index == 1)
        self.w.btn_tab_card.setEnabled(self._inspector is not None)

    def bottom_page(self) -> int:
        return int(self.w.bottom_stack.currentIndex())

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
                self.w.inspector_slot.removeWidget(self._inspector)
                self._inspector.setParent(None)
                self._inspector.deleteLater()
                self._inspector = None
            if cls is not None:
                self._inspector = cls(self.w.inspector_host)
                self.w.inspector_slot.addWidget(self._inspector)
                self._connect_inspector(self._inspector)
            # 字在 `_refresh_inspector` 餵完資料之後才定案（儀表要看得到
            # 現在畫的是什麼才說得出「誰跟誰比」）—— 這裡先給一個保底。
            self.w.btn_tab_card.setText(str(getattr(cls, "title", "Card"))
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
        nid = self.w.selected_node
        node = self.w.model.nodes.get(nid or "")
        if not self.w._is_method(node, self.w.PROFILE_STEP,
                               self.w.PROFILE_METHOD):
            return
        items = self.w._items()
        if not items:
            self.w._status("Load a KLARF first - measuring across the lot "
                         "needs the lot.", "error")
            return
        if not self.w.calibrate_worker.start(
                self.w.model.to_recipe(), items[:self.CALIBRATE_LIMIT],
                self.w.model.kind, nid, dict(node.params),
                sources=self.w.sources_for_run()):
            self.w._status("Still measuring - please wait.")
            return
        self.w._status("Measuring stripe pitch and width on %d defects…"
                     % min(len(items), self.CALIBRATE_LIMIT))

    def _on_calibrated(self, result: Any) -> None:
        """量完了：能填的填進卡片（走 set_param，可復原），不能填的講原因。"""
        nid = self.w.selected_node
        node = self.w.model.nodes.get(nid or "")
        if not self.w._is_method(node, self.w.PROFILE_STEP,
                               self.w.PROFILE_METHOD):
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
            self.w.model.set_param(nid, "%s_pitch" % side, round(cal.pitch, 3))
            self.w.model.set_param(nid, "%s_pitch_2" % side,
                                 round(cal.pitch_2, 3))
            bits = ("pitch %.1f / %.1f px" % (cal.pitch, cal.pitch_2)
                    if cal.pitch_2 >= 2.0 else "pitch %.1f px" % cal.pitch)
            if cal.width >= 1.0:
                self.w.model.set_param(nid, "%s_width" % side,
                                     round(cal.width, 3))
                bits += ", width %.1f px" % cal.width
            filled.append("%s %s (%d defects, %.0f%% agree)"
                          % (word, bits, cal.n_used, cal.agree * 100.0))
        node = self.w.model.nodes.get(nid)
        self.w.param_form.set_step(
            get_step(node.step).describe(), node.params,
            self.w.model.available_streams(before_node=nid),
            self.w.model.available_regions(before_node=nid))
        if refused:
            # 拒絕的那一半是**主角**：它講的是「這批 patch 自己不同意」，
            # 而那正是 kinds 沒設對的樣子。填了的也要一起講 —— 只報壞消息
            # 的話，使用者會以為整件事失敗了，然後把填好的那一半也改掉。
            msg = "Not filled in - %s" % " · ".join(refused)
            if filled:
                msg = "Filled %s. %s" % (" · ".join(filled), msg)
            self.w._status(msg, "error")
        elif filled:
            self.w._status("Measured across the lot: %s." % " · ".join(filled))
        else:
            self.w._status("Nothing to measure - no defects had stripes.",
                         "error")

    def _on_param_requested(self, name: str, value: Any) -> None:
        """儀表說「這一格該是這個值」（目前只有「量給我填」用到）。

        走的是跟使用者自己動參數表**同一條路**（``set_param`` → 復原堆疊 →
        重跑預覽），所以它可以被 Ctrl+Z 撤銷 —— 一個會改 recipe 而撤不掉的
        按鈕，比沒有那顆按鈕糟。
        """
        nid = self.w.selected_node
        if not nid or nid not in self.w.model.nodes:
            return
        self.w._on_param_edited(str(name), value)
        # 參數表要跟著顯示新值 —— 不然畫面上那一格還是舊的，而使用者按了鈕。
        node = self.w.model.nodes.get(nid)
        if node is not None:
            self.w.param_form.set_step(
                get_step(node.step).describe(), node.params,
                self.w.model.available_streams(before_node=nid),
                self.w.model.available_regions(before_node=nid))

    def _on_charts_requested(self) -> None:
        """`Write charts` 儀表上的 `Preview charts…`（F87）。

        視窗**只有一個**（開第二次是把同一個抬到最前面）—— 每按一次多開一個
        的話，改設定會只改到其中一個，而其他幾個還畫著舊的樣子。
        """
        from .uniformity_window import UniformityWindow

        win = getattr(self, "_charts_window", None)
        if win is None:
            # ⚠ parent 是**視窗**，不是這個 controller：`UniformityWindow`
            # 是 QWidget，而 controller 是 QObject（F116 搬家時踩到的）。
            win = UniformityWindow(self.w)
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
        node = self.w.model.nodes.get(self.w.selected_node or "")
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
        for view in (self.w.image_view, self.w.image_view_b):
            view.set_measure(axis, start, end)

    def _on_measure_ended(self) -> None:
        for view in (self.w.image_view, self.w.image_view_b):
            view.clear_measure()

    def _refresh_inspector(self, result: Any = None) -> None:
        """把三種來源餵給儀表：這張卡的參數、這一顆的結果、整批的結果。"""
        insp = self._inspector
        # meta 在 **context** 上，不在 result 上（result 只帶 features/score/bin）。
        ctx = getattr(result, "context", None) if result is not None else None
        meta = dict(getattr(ctx, "meta", {}) or {})
        if insp is None:
            self.w.inspector_summary.setText("")
            # 沒有儀表的卡也可能有曲線欄位 —— 那個背景跟儀表是兩件事，
            # 不要因為前者不在就跳過後者。
            self._refresh_curve_backdrop(meta)
            return
        node = self.w.model.nodes.get(self.w.selected_node or "")
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
        shown = [self.w.stream_combo.currentText()]
        if self.w._compare_on:
            shown.append(self.w.stream_combo_b.currentText())
        # 寫回的儀表要**真的乾跑一次**才講得出「會改幾列」，而那需要 KlarfDoc。
        # 儀表不自己去讀檔（它連檔名都不該知道）—— 由這裡遞過去。
        # 沒有 KLARF 的兩種輸入這一格就是 None，面板會退回估算並標明。
        meta = dict(meta or {})
        meta["_klarf_doc"] = getattr(self.w.dataset, "klarf", None)
        # 跨顆那張圖的座標（`die_x` / `x_um`）在**結果那幾列裡沒有** ——
        # 它們住在 `Dataset.items`。同 `_klarf_doc` 的理由由這裡遞過去，
        # 不然選單裡少掉 die 那兩欄，而 die 圖正是那張圖最有用的一種。
        meta["_items"] = list(getattr(self.w.dataset, "items", None) or [])
        insp.set_context(self.w.selected_node or "",
                         params=dict(node.params) if node else {},
                         result=one, batch=self.w.trial_results, meta=meta,
                         feature_names=feats,
                         shown_streams=[s for s in shown if s])
        self.w.inspector_summary.setText(insp.summary())
        # 圖的視窗開著就跟著這一顆走 —— 換一顆 defect 而視窗停在上一顆的
        # 數字，是最難發現的那一種說謊（兩張圖都畫得出來）。
        self._refresh_charts_window(insp)
        # `Chart look` 那一列的編輯器，預覽要畫**這一顆**（不是樣本）。
        # 同 `set_histogram` 的先例：數字只有引擎那一份，UI 不再算一次。
        self.w.param_form.set_chart_series(
            insp.series() if hasattr(insp, "series") else None)
        # 散佈圖那一格的選單是從**這一顆的長表**長出來的（欄名跟著量測卡走，
        # 寫死一份的話使用者的欄位在選單上找不到）。
        self.w.param_form.set_chart_frame(
            insp.frame() if hasattr(insp, "frame") else None)
        # 分頁鈕的字由**儀表現在畫的東西**決定（使用者 2026-08-21：「title 要
        # 更詳細一點」）。放不下的那半句進 tooltip。
        if hasattr(insp, "tab_title"):
            self.w.btn_tab_card.setText(str(insp.tab_title() or "Card"))
            self.w.btn_tab_card.setToolTip(str(insp.tab_tooltip() or ""))
        self._refresh_curve_backdrop(meta)

    def _refresh_curve_backdrop(self, meta: Dict[str, Any]) -> None:
        """曲線欄位後面墊上「這張卡吃進來的那條流」的灰階分布（F11 UI-C）。

        用的是引擎那份 ``stream_change[流]['before']`` —— 跟 Enhance 儀表左邊那條
        細線同一組數字。UI 不自己再壓一次直方圖：畫面上的分布跟真的跑出來的
        不一樣，比沒有那個背景更糟。

        ``before`` 是「這張卡動它之前」的樣子，而曲線的橫軸就是輸入灰階 ——
        兩者講的是同一件事，所以不必另外算一份。
        """
        node = self.w.model.nodes.get(self.w.selected_node or "")
        if node is None:
            self.w.param_form.set_histogram([])
            return
        changes = dict((meta or {}).get("stream_change") or {})
        # 這張卡處理的第一條流（曲線是逐像素的，兩條流吃的是同一條曲線）。
        keys = [k.strip() for k in
                str(node.params.get("streams") or "").split(",") if k.strip()]
        for key in keys:
            rec = changes.get(key)
            if rec and rec.get("before"):
                self.w.param_form.set_histogram(list(rec["before"]))
                return
        self.w.param_form.set_histogram([])
