# d4t UI — authored 2026-09-19 (F116 第 4 步).
"""**把第二份東西掛到已經載入的這一份資料上**：配對卡的第二份 lot（F15）
與 GLAS 匯出的 layer 標註（F11 Region-3）。

為什麼這兩件事是同一塊（`CLAUDE.md` §4：先問那一塊該不該是一塊）：
它們的形狀一字不差 —— **問一個路徑 → 交給 ingest 層做事 → 把結果講成一句話
→ 把量到的名字填回卡片**。`attach_pair_source` 與 `attach_gds_export` 連
「不要讓使用者自己抄一次」那個理由都一樣。計畫書 §4 只點名了配對那一半
（`ui/pair_source_ui.py`），但另一半留在 `studio.py` 的話，`對話框` 那一段會
剩下兩支名字對不上段名的東西。

**不在這裡的三支**（它們在那一段裡只是鄰居）：`_number_info`（設定區「插入
數字 ▾」的 provider）、`_dynamic_choices_for`（卡片三格選單的選項）、
`sources_for_run`（每一條跑 pipeline 的路都問它的那個答案）—— 它們不是
「掛第二份東西」，留在 `studio.py`。

**行為零改動**（F116 §1）：本體逐字搬，只把屬於視窗的 ``self.x`` 換成
``self.w.x``。

⚠ `_carry_filled` **留在視窗**：換資料集時 `_on_dataset_loaded` 會把它清成
`None`，而那一段不在這一族裡（F116 §3-1）。

接線：`pair_worker` **只有這一族在用**，所以由這一支自己建、自己接
（同 `gallery_controller` 的 `thumb_worker`）。
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog

from .workers import DatasetLoadWorker
from . import wording

if TYPE_CHECKING:                      # 只給型別看：這一支不 import studio
    from .studio import StudioWindow


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


class AttachSources(QObject):
    """第二份 lot 與 GLAS 匯出。從 `StudioWindow` 搬來（F116 第 4 步）。"""

    def __init__(self, win: "StudioWindow") -> None:
        # ⚠ 一定要掛 parent（F116 §7-1）—— 理由見 `gauge_panel.py` 同一行。
        super().__init__(win)
        self.w = win
        #: 第二份 lot 用**另一個** worker（F15-2）：跟 main 那一份是兩件可以
        #: 同時發生的事，共用一個的話「已經有工作在跑」會把其中一個默默擋掉。
        self.pair_worker = DatasetLoadWorker(win)
        self.pair_worker.loaded.connect(self._on_pair_source_loaded)
        self.pair_worker.failed.connect(self._on_pair_source_failed)
        #: 正在載的第二份是**哪一張卡**要的（載完才知道要掛到哪）。
        self._pending_pair: Optional[Tuple[str, str]] = None
        #: 每一份第二 source 上次填了哪幾欄（`carry` 沒變就不用重填）。
        self._pair_filled: Dict[str, Tuple[str, ...]] = {}

    def _on_open_pair_source(self, node_id: str) -> None:
        """`pair_source` 卡上的 `Open data…`：載一份**第二個** lot 掛上去。

        **不取代目前的資料集**：main 決定批次跑幾顆、route 用哪一條、KLARF 寫回
        誰。這一份只提供「另一張圖與它的座標」。
        """
        if self.w.dataset is None:
            self.w._status("Load the main lot first — this card pairs every "
                         "defect of the open lot with one from a second lot.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self.w, "Open the second lot's KLARF", "",
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
        node = self.w.model.nodes.get(str(node_id))
        if node is None or self.w.dataset is None:
            return ""
        if sync:
            try:
                ds = DatasetLoadWorker.run_sync(str(klarf_path), None)
            except Exception as e:  # UI 邊界，一律回報
                return self._on_pair_source_failed(wording.failure("attach.pair_source", e))
            self._pending_pair = (str(node_id), str(klarf_path))
            return self._on_pair_source_loaded(ds)

        if self.pair_worker.is_running():
            msg = "A second lot is already loading — please wait."
            self.w._status(msg)
            return msg
        self._pending_pair = (str(node_id), str(klarf_path))
        self.pair_worker.start(str(klarf_path), None)
        name = os.path.basename(str(klarf_path))
        self.w._progress_busy("Loading %s…" % name)
        msg = "Loading second lot: %s" % name
        self.w._status(msg)
        return msg

    def _on_pair_source_failed(self, msg: str) -> str:
        self._pending_pair = None
        self.w._progress_done()
        text = "Could not load that lot: %s" % msg
        self.w._status(text, "error")
        return text

    def _on_pair_source_loaded(self, ds: Any) -> str:
        """第二份載完了 → 掛到 main 上（背景與同步兩條路都走這裡）。"""
        from d4t.core.ingest import pair_source as pair_ingest

        pending, self._pending_pair = self._pending_pair, None
        self.w._progress_done()
        if pending is None:
            return ""                       # 關窗／換卡之後才送達的通知
        node_id, klarf_path = pending
        node = self.w.model.nodes.get(str(node_id))
        if node is None or self.w.dataset is None:
            return ""

        sid = str(node.params.get("source", "") or "").strip()
        if not sid:
            sid = _source_id_from(klarf_path)
            self.w.model.set_param(str(node_id), "source", sid)
        # **只複製要用的那幾欄**：raw data 是幾十萬顆，×24 欄字串是幾百 MB，
        # 而那幾欄還要 pickle 進 worker。`carry` 之後改了會重填（見
        # `_sync_pair_fields`），所以少複製不會變成「這一欄不見了」。
        cols = self._pair_columns_wanted(sid)
        try:
            rep = pair_ingest.attach(self.w.dataset, ds, sid, columns=cols)
        except pair_ingest.PairSourceError as e:
            self.w._status(str(e), "error")
            return str(e)
        self._pair_filled[sid] = tuple(cols)
        self._say_missing_columns(sid, cols)
        # 卡片旁邊那句話要講得出檔名 —— 它是使用者認得的東西。
        ds._d4t_name = os.path.basename(str(klarf_path))
        self.w._sync_source_action(node)
        # 三格的選單（代號／哪張圖／哪些欄）現在才有答案（F15-2）。
        if self.w.selected_node == str(node_id):
            self.w.param_form.set_dynamic_choices(self.w._dynamic_choices_for(node))
        self.w._refresh_all()
        # **掛上第二份 = 這條 pipeline 的產出變了**，所以預覽要重跑一次
        # （2026-08-20）。以前不重跑，於是使用者按完 `Open data…` 什麼事都沒
        # 發生：影像流的下拉裡沒有 `paired`，要再去點一張卡才會出現 ——
        # 而「按了鈕、畫面沒反應」讀起來就是「載不進來」。
        self.w._schedule_preview()
        msg = "Paired source · %s" % rep.summary()
        self.w._status(msg)
        return msg

    def _pair_columns_wanted(self, source_id: str) -> List[str]:
        """指著這個代號的每一張配對卡，`carry` 的聯集（`carry` 的意思住在卡片）。"""
        from d4t.core.steps.pair_source import columns_for_source

        return columns_for_source(self.w.model.nodes.values(), source_id)

    def _after_carry_param(self, node_id: str, name: str) -> None:
        """Load 卡改了 `carry` 之後要重填（F16）。

        跟 `_after_pair_param` 是同一件事的另一半：那一支管掛上來的第二份，
        這一支管主資料集。分開兩支是因為它們問的是**兩份不同的 KLARF**。
        """
        node = self.w.model.nodes.get(str(node_id))
        if node is None or node.step != "load_patch":
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

        if self.w.dataset is None:
            return
        want = columns_for_main(self.w.model.nodes.values())
        if getattr(self.w, "_carry_filled", None) == tuple(want):
            return                          # 沒變 —— 不用走一遍幾十萬顆
        absent = missing_columns_of(self.w.dataset, want)
        fill_fields(self.w.dataset, want)
        self.w._carry_filled = tuple(want)
        if absent:
            self.w._status(
                "This lot has no KLARF column called %s. It has: %s."
                % (", ".join(absent), ", ".join(columns_of(self.w.dataset))),
                "error")

    def _sync_pair_fields(self, source_id: str) -> None:
        """`carry` 改了 → 把那幾欄補進掛著的那一份（F15-2）。

        掛的時候只複製「當時要的那幾欄」，所以之後才勾起來的那一欄不在
        `fields` 裡 —— 而卡片會照它的規矩說「這一份沒有這個欄位」，
        那句話是錯的（欄位在，只是沒複製）。KlarfDoc 還在手上，重填很便宜。
        """
        from d4t.core.ingest import pair_source as pair_ingest

        sid = str(source_id or "").strip()
        if not sid or self.w.dataset is None:
            return
        if sid not in (getattr(self.w.dataset, "sources", None) or {}):
            return
        cols = self._pair_columns_wanted(sid)
        if self._pair_filled.get(sid) == tuple(cols):
            return                          # 要的欄位沒變 —— 不用走一遍幾十萬顆
        pair_ingest.refill_fields(self.w.dataset, sid, cols)
        self._pair_filled[sid] = tuple(cols)
        self._say_missing_columns(sid, cols)

    def _say_missing_columns(self, source_id: str, columns: Sequence[str]) -> None:
        """要 carry 一個那一份沒有的欄位 → **在勾的當下**就講（F15-2）。

        以前這句話要等跑起來才出現，一顆一顆講，而且列出來的是「帶過來的那幾
        欄」不是「那一份有的那幾欄」—— 打錯字的人最需要的正是後者。
        這裡手上還有 KlarfDoc，所以答得出來。
        """
        from d4t.core.ingest import pair_source as pair_ingest

        src = (getattr(self.w.dataset, "sources", None) or {}).get(str(source_id))
        if src is None:
            return
        missing = pair_ingest.missing_columns(src, columns)
        if not missing:
            return
        self.w._status(
            "'%s' has no KLARF column %s — its columns are: %s"
            % (source_id, ", ".join(missing),
               ", ".join(pair_ingest.columns_of(src))), "error")

    def _on_open_gds(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self.w,
            "Attach GLAS export (the folder with the *_label.png files)")
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

        if not self.w.dataset:
            msg = ("Load the lot first — “Open GDS export…” attaches labels to "
                   "the defects that are already open.")
            self.w._status(msg)
            return msg
        try:
            rep = glas_export.attach(self.w.dataset, export_dir)
            doc = glas_export.read_manifest(export_dir)
        except glas_export.GlasExportError as e:
            self.w._status(str(e))
            return str(e)

        # 名字填進**每一張** roi_reference 卡（還沒設定過的才填 —— 使用者改過的
        # 名字不能被一次「重新掛載」洗掉）。
        default = glas_export.default_layer_map(doc)
        filled = 0
        if default:
            for nid, node in self.w.model.nodes.items():
                if node.step == "roi_reference" and not str(
                        node.params.get("layers", "") or "").strip():
                    self.w.model.set_param(nid, "layers", default)
                    filled += 1
        # 表單的列數要照**這份匯出有幾層**排（`ChannelMapField` 的 labels 版）。
        self.w._gds_layers = list(rep.layers)
        self.w.param_form.set_label_count(len(rep.layers))
        msg = rep.summary()
        if filled:
            msg += " · filled the layer names into %d card(s)" % filled
        for w in rep.warnings:
            msg += " · △ %s" % w
        self.w._status(msg)
        self.w.refresh_preview()
        return msg
