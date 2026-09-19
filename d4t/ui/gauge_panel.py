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

**2026-09-19（F116 第 1 步之 1b）**：`bottom_stack` 的**另一頁**（特徵表）也
搬進來了 —— `_feature_sections` 那一族把「這張卡產出哪些數字」排成畫得出來的
段落，而 `show_bottom_page` 本來就在這裡管兩頁誰在前面。同一塊畫面、同一個
狀態機，分成兩個 controller 的話 `show_bottom_page` 會變成跨物件呼叫
（F116 §3-2 不准 controller 互叫）。

`profile_panel` 也在這裡，理由一樣：它回的是**現在掛著的儀表**身上那塊面板
（`_inspector.panel`），而那個狀態的家在這一支。

接線仍然留在 `studio.py`（`_wire_widgets` / `_wire_workers`）—— 這一支只提供
slot（F116 §3-4）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QObject

from d4t.core.log import swallowed
from d4t.core.pipeline import get_step
from d4t.core.pipeline.engine import FEATURE_OWNER_KEY, feature_prefixes
from d4t.core.pipeline.step import REGISTRY
from . import theme
from .inspectors import inspector_for
from .widgets import ProfilePanel

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
        #: 沒有投影曲線面板時回的那個**空的替身**（原 StudioWindow._no_profile）。
        self._no_profile: Optional[Any] = None
        #: 圖的視窗現在畫的是**哪一張卡**的數字（F117 G8）。選取跑到別張卡
        #: 上的時候，視窗那一行字要說得出這幾張圖是誰的。
        self._charts_owner = ""
        self._charts_window: Optional[Any] = None

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
        self._charts_owner = str(getattr(self._inspector, "title", "")
                                 or "Charts folder")
        self._refresh_charts_window(self._inspector, force=True)
        win.show()
        win.raise_()
        win.activateWindow()

    def _refresh_charts_window(self, insp: Any, force: bool = False) -> None:
        """把儀表現在那一顆餵給圖的視窗（開著才餵）。

        ⚠ **餵不了的時候要講一句，不能安靜地 return**（F117 G8）。這個視窗
        只有「Charts folder」那張卡餵得動，而使用者選了別張卡之後它還亮著、
        還畫著上一張卡的數字 —— 而畫面上一個字都沒說。那正是這個 repo 記過
        七次的「跑得完、有數字、而且是錯的」。
        """
        win = getattr(self, "_charts_window", None)
        if win is None or not (force or win.isVisible()):
            return
        if not hasattr(insp, "series") or not hasattr(insp, "charts"):
            win.set_stale(self._charts_owner)
            return
        self._charts_owner = str(getattr(insp, "title", "") or "this card")
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
        if self.w.compare_enabled():
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
            self._no_profile = ProfilePanel(self.w)
            self._no_profile.setVisible(False)
        return self._no_profile

    def profile_panel_visible(self) -> bool:
        """面板現在開著嗎（用明確狀態，不要問 ``isVisible()``）。"""
        node = self.w.model.nodes.get(self.w.selected_node or "")
        return self.w._is_method(node, self.w.PROFILE_STEP,
                               self.w.PROFILE_METHOD)

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
            recipe = self.w.model.to_recipe()
            bounds = bound_specs(recipe, self.w.model.kind)
            diags = diagnostic_columns(recipe, self.w.model.kind)
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
        for nid in self.w.model.node_order:
            node = self.w.model.nodes.get(nid)
            if node is None or not node.enabled:
                continue
            try:
                got = get_step(node.step).resolve_feature_specs(node.params)
            except Exception:  # 顯示用，壞了就不拆
                swallowed("gauge_panel._feature_specs")
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
            recipe = self.w.model.to_recipe()
            prefixes = feature_prefixes(list(self.w.model.node_order), recipe,
                                        REGISTRY)
        except Exception:  # 顯示用，壞了就退回節點 id
            prefixes = {}
        for nid in self.w.model.node_order:
            node = self.w.model.nodes.get(nid)
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
        nid = self.w.selected_node
        if not nid:
            return ()
        for tr in getattr(result, "traces", []) or []:
            if getattr(tr, "node_id", None) == nid:
                return list(getattr(tr, "features_added", {}) or {})
        return ()
