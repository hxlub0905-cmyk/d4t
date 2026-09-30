# d4t UI — authored 2026-09-19 (F116 第 3 步).
"""Gallery、Results 視窗與**回溯**（點一個數字 → 它從哪來）。

為什麼自己一個模組（`CLAUDE.md` §4：`studio.py` 留給接線，不留給內容）：
這一族是**內容** —— 哪一顆 defect 的縮圖要讀哪個 channel、背景怎麼解碼、
一批結果怎麼變成 Gallery 的磚、點一根長條怎麼篩、點 score/bin 怎麼算 trace
再把產出它的那張卡亮起來。

**縮圖那一條鏈整條在這裡**（`THUMB_CHANNEL_PRIORITY` → `thumb_channel` →
`load_thumb` → `ThumbWorker`）：它們以前散在 `studio.py` 的模組層，而唯一的
使用者是 Gallery。`studio.py` 仍然把 `ThumbWorker` / `THUMB_CHANNEL_PRIORITY`
/ `thumb_channel` 轉出去 —— 前兩個在它的 `__all__` 裡，而測試是用
`studio_mod.` 拿的（那是對外的名字，不是實作細節）。

**行為零改動**（F116 §1）：本體逐字搬，只把屬於視窗的 ``self.x`` 換成
``self.w.x``。

⚠ `_items_by_id`（縮圖工回頭找 `DefectItem` 的那張表）**留在視窗**：它是
`_on_dataset_loaded` 寫的，而那一段不在這一族裡（F116 §3-1：被別段也寫的留在
視窗）。計畫書 §4 原本寫它跟著搬 —— 搬了就會變成別的段落往 controller 裡寫
一個欄位，那比留著更難讀。

接線留在 `studio.py`（`_wire_widgets`）—— 這一支只提供 slot（F116 §3-4）。
唯一的例外是 `thumb_worker`：它**只有這一族在用**，所以由這一支自己建、
自己接（它兩端都在自己家裡）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QObject, Signal

from d4t.core.log import swallowed
from d4t.core.pipeline import verdict_features
from d4t.core.pipeline.verdict_trace import verdict_trace

from . import results_table
from .gallery import make_thumb
from .workers import _ThreadedWorker

if TYPE_CHECKING:                      # 只給型別看：這一支不 import studio
    from .studio import StudioWindow


#: Gallery 縮圖要用哪個 channel（依序找第一個有的；都沒有就用第一個 channel）。
THUMB_CHANNEL_PRIORITY = ("test", "single")

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


class GalleryController(QObject):
    """Gallery／Results／回溯。從 `StudioWindow` 搬來（F116 第 3 步）。"""

    def __init__(self, win: "StudioWindow") -> None:
        # ⚠ 一定要掛 parent（F116 §7-1）—— 理由見 `gauge_panel.py` 同一行。
        super().__init__(win)
        self.w = win
        #: 縮圖的背景解碼工。**只有這一族在用**，所以它建在這裡、也接在這裡
        #: （兩端都在自己家裡，不算 §3-4 說的那種接線）。
        self.thumb_worker = ThumbWorker(self)
        self.thumb_worker.ready.connect(self._on_thumbs_ready)
        self.thumb_worker.failed.connect(win._status)

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
        self.w.gallery.set_sort_keys(["score"] + sorted(feats))
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
            recipe = self.w.model.to_recipe()
            kind = self.w.model.kind
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
        self.w.results.set_table(results, names, layout, alarms,
                               dict(self.w.ground_truth or {}))  # 表格那一半（R7）
        # **這一批是哪一種資料**（F117 E3）：patch 與 RSEM 的影像是繞著那一顆
        # 切出來的，所以縮圖標得出「defect 在這裡」；另外兩種沒有那回事。
        self.w.gallery.set_kind(str(getattr(self.w.dataset, "kind", "") or ""))
        self.w.gallery.set_items([
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
        self.w.results.clear_filter()
        self.w._score_filter = None

    def _class_names(self, results: Sequence[Dict[str, Any]]) -> Dict[str, str]:
        """``defect_id → 這一顆判成了哪一類的名字``（沒取名字的那一類是空的）。

        ⚠ **不自己走一次樹**：判定段已經算好每一類是哪幾顆
        （`verdict_rows` 的 ``ids``），這裡只是把它翻過來。兩邊各走一次的話，
        縮圖上的名字跟判定段上的顆數會是兩份會漂的東西。
        """
        from .verdict_band import verdict_rows

        out: Dict[str, str] = {}
        for row in verdict_rows(getattr(self.w.model, "decide", None),
                                list(results or []), self.w.ground_truth):
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
        if not self.w.trial_results:
            self.w.results.status(
                "Nothing to show yet — press “Run trial” in the main window "
                "and the score distribution, thumbnails and table fill in here.")
        self.w.results.present()

    def show_preview(self) -> None:
        """回到主視窗的單顆預覽。"""
        self.w.raise_()
        self.w.activateWindow()

    def results_visible(self) -> bool:
        """Results 視窗現在開著嗎（測試用）。"""
        return bool(self.w.results.isVisible())

    # ---- 縮圖（永遠不在 GUI 執行緒解碼）------------------------------------
    def _on_thumbs_requested(self, ids: Any) -> None:
        self.request_thumbs(list(ids or []))

    def request_thumbs(self, ids: Sequence[str], sync: bool = False) -> int:
        """做這些 defect 的縮圖。``sync=True`` 直接算完（測試 / headless 用）。

        回傳實際排進去（或同步做好）的張數；認不得的 id 靜靜略過。
        """
        jobs = [(str(i), self.w._items_by_id[str(i)])
                for i in (ids or []) if str(i) in self.w._items_by_id]
        if not jobs:
            return 0
        size = int(self.w.gallery.thumb_size())
        if sync:
            mapping = ThumbWorker.run_sync(jobs, size)
            self._on_thumbs_ready(mapping)
            return len(mapping)
        self.thumb_worker.request(jobs, size)
        return len(jobs)

    def _on_thumbs_ready(self, mapping: Any) -> None:
        """背景做好的縮圖回到 GUI 執行緒 —— 只有這裡碰 Gallery。"""
        self.w.gallery.set_thumbs(dict(mapping or {}))

    # ---- Gallery 的互動 ---------------------------------------------------
    def _on_defect_selected(self, defect_id: str) -> None:
        """Results 裡單擊（或方向鍵走到）某顆 → 主畫面跳過去，**不搶焦點**
        （2026-09-09）。使用者正在 Results 視窗裡一顆一顆看，主視窗每次都跳到
        前面的話，他每看一顆就要再點回去一次。已經在那一顆上就不動。"""
        did = str(defect_id)
        items = list(getattr(self.w.dataset, "items", []) or []) if self.w.dataset else []
        for i, it in enumerate(items):
            if str(getattr(it, "defect_id", "")) == did:
                if i != int(self.w.defect_index):
                    self.w.set_defect_index(i)
                return

    def _on_defect_activated(self, defect_id: str) -> None:
        """Gallery 雙擊某顆 → 切回單顆預覽並跳過去。"""
        did = str(defect_id)
        items = list(getattr(self.w.dataset, "items", []) or []) if self.w.dataset else []
        index = None
        for i, it in enumerate(items):
            if str(getattr(it, "defect_id", "")) == did:
                index = i
                break
        self.show_preview()
        if index is None:
            self.w._status("Defect “%s” is not in the current dataset." % did)
            return
        self.w.set_defect_index(index)
        self.w._status("Jumped to defect “%s” (%d / %d)"
                     % (did, index + 1, len(items)))

    def _on_gallery_selection(self, ids: Any) -> None:
        self.w._status("%d selected" % len(list(ids or [])))

    # ---- 回溯面板（PR-3）：這一顆為什麼判成這樣 ---------------------------
    def _on_trace_requested(self, defect_id: str) -> None:
        """結果表點了 score / bin / class → 重放那一顆的判定並開面板。

        trace 吃**那一列的 features**（引擎判定後的快照，let 值都在）——
        不重跑影像、不重算任何值（`verdict_trace` 的立身規矩）。
        """
        did = str(defect_id)
        row = next((r for r in (self.w.trial_results or [])
                    if str(r.get("defect_id", "")) == did), None)
        if row is None:
            return
        if not row.get("ok"):
            self.w._status("Defect “%s” failed before the decision — the error "
                         "column says why." % did, "error")
            return
        feats = dict(row.get("features") or {})
        # score-only 的 recipe：bin 只在列上（引擎不寫進 features）——
        # 補給 trace 顯示；decide 模式的 leaf_bin 是重放樹算的，不看這一格。
        if row.get("bin") is not None:
            feats.setdefault("bin", float(row["bin"]))
        try:
            trace = verdict_trace(self.w.model.to_recipe(), self.w.model.kind,
                                  feats)
        except Exception as e:  # 顯示層
            self.w._status("Could not replay the decision: %s" % e, "error")
            return
        if trace.mode == "none":
            self.w._status("This recipe has no score and no decision — "
                         "there is nothing to replay.")
            return
        self.w.results.show_why(did, trace)

    def _on_why_item(self, defect_id: str, name: str) -> None:
        """面板上點了一項 → 跳到產出那個數字的卡。

        身分查 `bound_specs`（跟結果表的分組同一份）：有區域的項把那一塊
        **亮**在影像上（`highlight_region`），引擎的項（let / score）對映
        Decision 偽卡＝打開判定區。
        """
        try:
            bound = {b.spec.name: b for b in verdict_features.bound_specs(
                self.w.model.to_recipe(), self.w.model.kind)}
        except Exception:  # 顯示層
            swallowed("studio._on_why_item")
            return
        b = bound.get(str(name))
        if b is None:
            return
        if not b.node_id:
            # 引擎的名字（let、score、decide_unanswered）：去編判定區 ——
            # 跟畫布上點 ADC 那一格走同一條。
            self.w._on_tree_step_clicked("")
            return
        if b.spec.region:
            self.highlight_region(defect_id, b.node_id, b.spec.region)
        else:
            self.w.select_node(b.node_id)

    def highlight_region(self, defect_id: str, node_id: str,
                         region: str) -> bool:
        """跳到那一顆、選產出的卡，並把**那一塊區域**亮在影像上。

        亮法住在 `ImageView.set_overlay_emphasis`：命中的框全強度、其餘降
        alpha —— 顏色仍然說「哪一塊」、粗細仍然說「缺陷格」，**不 overload
        focus**。`set_overlay` 會清掉強調，所以先刷新預覽再點亮。
        """
        did = str(defect_id)
        items = list(getattr(self.w.dataset, "items", []) or []) \
            if self.w.dataset else []
        index = next((i for i, it in enumerate(items)
                      if str(getattr(it, "defect_id", "")) == did), None)
        if index is not None:
            self.w.set_defect_index(index)
        if not self.w.select_node(str(node_id)):
            return False
        self.w.refresh_preview(sync=True)
        for view in (self.w.image_view, self.w.image_view_b):
            view.set_overlay_emphasis([str(region)])
        return True

    # ---- 直方圖點長條 → Gallery 篩選 --------------------------------------
    def _on_bar_clicked(self, lo: float, hi: float) -> None:
        """點一根長條：只看那個分數區間；再點同一根就取消。

        「同一根」的判斷要連 Gallery 目前**真的還在篩**一起看 —— 使用者可能
        已經按掉 Gallery 上的條件 chip 了，那時候再點同一根當然是重新篩選。
        """
        rng = (float(lo), float(hi))
        if self.w._score_filter == rng and self.w.gallery.filter_text():
            self.w.results.clear_filter()
            self.w._score_filter = None
            self.w._status("Score filter cleared (showing all %d)"
                         % self.w.gallery.displayed_count())
            return
        self.w.results.set_filter({"mode": "score_range",
                                 "lo": rng[0], "hi": rng[1]})
        self.w._score_filter = rng
        self.show_gallery()
        self.w._status("Filtered to score %.3g–%.3g (%d defects)"
                     % (rng[0], rng[1], self.w.gallery.displayed_count()))
