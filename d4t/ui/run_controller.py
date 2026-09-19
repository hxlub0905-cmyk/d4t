# d4t UI — authored 2026-09-19 (F116 第 5 步).
"""**發動一次執行、把結果寫出去**：試跑／整批、Re-run、Write outputs。

為什麼自己一個模組（`CLAUDE.md` §4：`studio.py` 留給接線，不留給內容）：
這一族是**內容** —— 跑幾顆、幾個 worker、快取在哪、被停掉的那一批算不算數、
KLARF `inplace` 之前要問哪一句、寫完之後三種東西要講成三句不同的話。

**鐵則 11（跑不寫，寫是另一個動作）整條住在這裡**：`run_trial` / `run_all`
都不寫，`write_outputs` 才寫，而它前面那三道關（沒有結果／部分結果／
`inplace` 要先問）就是那條鐵則本身。搬家不准讓它鬆掉 ——
`tests/test_ui_write_only_on_run_all.py` 與 `tests/test_rerun_decision.py`
是這一步的驗收。

⚠ **`_apply_trial_results` 沒有搬**，而那是這一步最重要的決定。

計畫書 §4 原本寫「改成 controller 發 signal（`trial_started` /
`trial_finished(results)` / `outputs_written(paths)`），`studio.py` 把它們接到
那一串 refresh」。真的讀了那 115 行之後，前提不成立：**那不是一串可以搬出來的
refresh**。`_refresh_verdict` / `_refresh_spread` / `_refresh_decide_counts` 跟
「這批數字怎麼變成一句話」「要不要寫出去」是**交織**的，而且每一段前面都釘著
一句 ⚠（「判定段要先算，順序反過來圖上染的是上一批的類別 —— 跑得完、有顏色、
而且是錯的」）。要保住那個順序，signal 就得在精確的點發好幾次 —— 那只是把直接
呼叫包了一層。

所以刀切在**另一個地方**，而它反而更乾淨：
`_apply_trial_results`（＝「結果到了，畫面怎麼變」）**留在視窗**，跟它叫的那
一串 `_refresh_*` 住在一起；這一支只留「怎麼發動、怎麼寫」。於是這一族往外
就剩**一個**呼叫（`self.w._apply_trial_results(...)`），而那正是計畫書想用
signal 換到的東西。

**為什麼那一個也不做成 signal**：它有三個發射點，而 Qt 的 direct connection
雖然是同步的，例外卻會被 Qt 的 hook 吃掉印出來、不往上傳。測試大量用
`run_trial(sync=True)`，`_apply_trial_results` 裡爆掉的東西現在會讓那條測試
**當場紅**；包成 signal 之後它只會印在 stderr 上。這個 repo 最怕的就是
「跑得完、有數字、而且是錯的」，所以留直接呼叫。

**行為零改動**（F116 §1）：本體逐字搬，只把屬於視窗的 ``self.x`` 換成
``self.w.x``。

留在視窗的狀態（§3-1，被別段也寫）：`trial_worker` / `output_worker`
（`stop_run` 也在用）、`trial_results` / `trial_scores`（Results 與儀表在讀）、
`_last_run` / `_pending_warnings` / `_filtered_note` / `_write_outputs_this_run`
（`_apply_trial_results` 在寫或在讀）。這一支自己的只有 `_trial_t0` 與
`_write_outputs_sync`。
"""
from __future__ import annotations

import copy
import os
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Sequence

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox

from d4t.core.log import swallowed
from d4t.core.pipeline import sampling

from .status_action import open_folder
from .workers import OutputWorker, TrialWorker

if TYPE_CHECKING:                      # 只給型別看：這一支不 import studio
    from .studio import StudioWindow


#: 試跑用的影像段快取位置（跨次試跑重用，第二次調參會明顯變快）。
DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".d4t", "cache")


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


class RunController(QObject):
    """試跑／整批／寫出去。從 `StudioWindow` 搬來（F116 第 5 步）。"""

    def __init__(self, win: "StudioWindow") -> None:
        # ⚠ 一定要掛 parent（F116 §7-1）—— 理由見 `gauge_panel.py` 同一行。
        super().__init__(win)
        self.w = win
        self._trial_t0 = 0.0
        #: `write_outputs(sync=True)` 要一路同步跑完（測試那條路）。
        self._write_outputs_sync = False

    def run_trial(self, n: int, workers: Optional[int] = 1,
                  sync: bool = False, cache_dir: Optional[Any] = None,
                  write_outputs: bool = False) -> bool:
        """跑前 ``n`` 顆並更新直方圖。``sync=True`` 走同步路徑（測試用）。

        ``write_outputs``（F16 Stage 5c）：跑完之後要不要讓 Output 段的卡
        **真的寫出檔案**。**預設 False 是刻意的** —— 使用者定調「試跑不寫，
        只有整批才寫」，而新加一條跑 pipeline 的路時它預設不寫。
        只有 :meth:`run_all` 傳 True。
        """
        items = list(getattr(self.w.dataset, "items", []) or []) if self.w.dataset else []
        if not items:
            self.w._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
            return False
        if not self.w.model.node_order:
            self.w._status("The pipeline is empty — add a card before running.")
            return False

        # 跑之前先 lint（F7-9）。引擎的契約是「單顆出錯不殺整批」，所以一組接
        # 錯的卡片以前的下場是**跑完 200 顆、每一顆都失敗**：進度條走完、結果
        # 是空的、原因埋在每顆的錯誤訊息裡。同一份檢查 CLI 從 M1 就在用了，
        # 只是 Studio 一直沒接上來。只擋 error，warning 照跑。
        issues = self.w.model.validate()
        problems = [i for i in issues if i.level == "error"]
        if problems:
            first = problems[0]
            more = ("  (and %d more problem%s)"
                    % (len(problems) - 1, "" if len(problems) == 2 else "s")
                    if len(problems) > 1 else "")
            self.w._status("Cannot run — %s: %s%s"
                         % (first.title, first.detail, more), "error")
            return False
        self.w._pending_warnings = [i for i in issues if i.level == "warning"]

        recipe = self.w.model.to_recipe()
        # 「只跑這幾個 code」（F50）：**篩掉零顆的時候不可以安靜地跑完**。
        #
        # 引擎那一頭篩得很乾淨（`batch.select_items`），而乾淨的下場正是危險
        # 的：一個打錯的欄名或一個不存在的 code，跑出來是「0 defects」與一張
        # 空的結果表 —— 使用者要去猜是資料沒載到、pipeline 壞了，還是篩選太緊。
        # 那三件事的下一步完全不同，所以這裡要講出**是哪一個**。
        from d4t.core.pipeline.batch import item_filters, select_items

        picks = item_filters(recipe)
        if picks:
            kept = select_items(recipe, self.w.dataset, items)
            if not kept:
                where = ", ".join("%s = %s" % (col, ", ".join(vals))
                                  for _nid, col, vals in picks)
                self.w._status(
                    "Nothing to run — the input filter (%s) matches none of "
                    "the %d defects in this dataset. Check the column and the "
                    "values, or clear the filter to run everything."
                    % (where, len(items)), "error")
                return False
            self.w._filtered_note = ("%d of %d defects match the input filter"
                                   % (len(kept), len(items)))
            items = kept
        else:
            self.w._filtered_note = ""

        limit = max(1, min(int(n), len(items)))
        cdir = None if cache_dir is None else str(cache_dir)
        # **跟著這一次執行走**，不是讀當下的 UI 狀態：使用者按了 Run all 之後
        # 可以馬上去改別的東西，而這一批的結果仍然是「他叫我整批跑」的那一批。
        self.w._write_outputs_this_run = bool(write_outputs)
        # 同步那條路（headless 測試 / CLI 式呼叫）沒有 event loop 在轉，
        # 背景 worker 的訊號投遞不到 —— 寫檔那一段要跟著走同步版。
        self._write_outputs_sync = bool(sync)

        # 這一次抽哪幾顆（X3）。**紀錄先寫下來再跑** —— 跑到一半當掉的時候，
        # 「剛才那一批是哪幾顆」仍然答得出來。
        spec = self.w.sample_spec()
        # 這裡**再算一次**同一個抽樣，只為了拿那份紀錄。它不浪費（幾千顆的
        # `random.sample`），而且**保證跟 `run_batch` 挑到同一批** —— 同一個
        # 種子、同一串 items。紀錄裡的 `mode` 可能跟 `spec` 不一樣（分層那一欄
        # 整批是空的時候會退成 random），而使用者要看到的是**真的發生的那個**。
        _picked, note = sampling.pick(
            items, limit, mode=str(spec.get("mode", "first")),
            seed=spec.get("seed"),
            column=str(spec.get("column", "CLASSNUMBER") or "CLASSNUMBER"))
        self.w.sample_note = dict(note)

        if sync:
            t0 = time.time()
            try:
                results = TrialWorker.run_sync(
                    recipe, self.w.dataset, limit,
                    workers=int(workers) if workers else 1, cache_dir=cdir,
                    sample=spec)
            except Exception as e:  # UI 邊界
                self.w._status("Trial run failed: %s: %s" % (type(e).__name__, e), "error")
                return False
            self.w._apply_trial_results(results, time.time() - t0)
            return True

        self._trial_t0 = time.time()
        if not self.w.trial_worker.start(recipe, self.w.dataset, limit,
                                       workers=workers, cache_dir=cdir,
                                       sample=spec):
            self.w._status("A run is already in progress — please wait.")
            return False
        self.w._progress_set(0, limit, "%v / %m defects")
        self.w._show_stop(True)
        self.w._status("Running: 0 / %d" % limit)
        return True

    def _on_trial_clicked(self) -> None:
        self.run_trial(int(self.w.spin_trial_n.value()), workers=TRIAL_WORKERS,
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
        items = list(getattr(self.w.dataset, "items", []) or []) if self.w.dataset else []
        if not items:
            self.w._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
            return False
        return self.run_trial(len(items), workers=TRIAL_WORKERS,
                              cache_dir=DEFAULT_CACHE_DIR, sync=sync)

    def write_outputs(self, sync: bool = False) -> bool:
        """把**現在這批結果**照 Output 卡寫出去（2026-09-09）。

        三道關，每一道都要講話（推廣鐵則）：沒有結果不寫；被停掉的那一批是
        **部分結果**，不寫（寫進 KLARF 是不可逆的錯）；KLARF ``inplace`` 先問
        一次（`_confirm_irreversible_writes`，那是這個 app 唯一不可逆的動作）。
        """
        results = list(self.w.trial_results or [])
        if not results:
            self.w._status("Nothing to write yet — run a trial or “Run all” "
                         "first.", "error")
            return False
        last = dict(getattr(self.w, "_last_run", None) or {})
        if last.get("partial"):
            self.w._status("That run was stopped part-way, so these are partial "
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

        last = dict(getattr(self.w, "_last_run", None) or {})
        rows = copy.deepcopy(last.get("rows") or [])
        if not rows:
            self.w._status("Nothing to re-run yet — run a trial first.", "error")
            return False
        issues = self.w.model.validate()
        problems = [i for i in issues if i.level == "error"]
        if problems:
            first = problems[0]
            self.w._status("Cannot re-run — %s: %s" % (first.title, first.detail),
                         "error")
            return False
        self.w._pending_warnings = [i for i in issues if i.level == "warning"]
        recipe = self.w.model.to_recipe()
        if measurement_signature(recipe) != str(last.get("sig") or ""):
            self.w._status("A measuring card changed since the last run, so the "
                         "numbers have to be measured again — running every "
                         "defect of the last run.")
            return self.run_trial(int(last.get("limit") or len(rows)),
                                  workers=TRIAL_WORKERS,
                                  cache_dir=DEFAULT_CACHE_DIR, sync=sync)
        t0 = time.time()
        try:
            n = rerun_decision(recipe, rows)
        except Exception as e:  # UI 邊界
            self.w._status("Re-run failed: %s: %s" % (type(e).__name__, e), "error")
            return False
        elapsed = time.time() - t0
        self.w._apply_trial_results(rows, elapsed)
        self.w._status("Re-run: decided %d of %d defects again from the stored "
                     "numbers in %.1f s — no image was recomputed."
                     % (n, len(rows), elapsed))
        return True


    # ---- Output 段：把結果寫出去（F16 Stage 5c）---------------------------
    def _write_outputs(self, results: Sequence[Dict[str, Any]]) -> bool:
        """跑 Output 段的卡（背景執行緒）。回 False = 沒開起來。

        **只有 `run_all()` 走得到這裡**（使用者定調：試跑不寫）。
        """
        recipe = self.w.model.to_recipe()
        self.w._status("Writing outputs…")
        if getattr(self, "_write_outputs_sync", False):
            # 同步那條路沒有 event loop，訊號投遞不到 —— 直接跑並自己收尾，
            # 走的是**同一支** `run_batch_steps`（不是第二套邏輯）。
            try:
                bctx = OutputWorker.run_sync(recipe, self.w.dataset, list(results))
            except Exception as e:  # UI 邊界
                self._on_outputs_failed("%s: %s" % (type(e).__name__, e))
                return False
            self._on_outputs_done(bctx)
            return True
        if not self.w.output_worker.start(recipe, self.w.dataset, list(results)):
            self.w._status("Still writing the last run's outputs — please wait.")
            return False
        return True

    def _on_outputs_done(self, bctx: Any) -> None:
        """寫完了：**三種東西是三句不同的話**（見 `BatchContext`）。"""
        outputs = list(getattr(bctx, "outputs", None) or [])
        warnings = list(getattr(bctx, "warnings", None) or [])
        errors = dict(getattr(bctx, "errors", None) or {})

        if not outputs and not errors and not warnings:
            # 一張 Output 卡都沒有 —— 那不是錯，只是這份 recipe 沒有出口。
            self.w._status("Run finished. This recipe has no Output card, so "
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
            self.w._status_next_step(
                msg, "Open the folder",
                lambda: self._open_output_folder(where), level or "info",
                "Show %s in the file browser" % where)
        else:
            self.w._status(msg, level)

    def _open_output_folder(self, where: str) -> None:
        """帶使用者去那個資料夾。開不起來就**說出來**，不要安靜地沒反應。

        按了一顆鈕、什麼都沒發生，使用者第一個念頭是「這個工具有沒有壞」——
        `undo()` 那句「Nothing to undo.」是同一條規矩。
        """
        if not open_folder(where):
            self.w._status("Could not open %s — the path is in the message "
                         "above, copy it into the file browser." % where,
                         "error")

    def _on_outputs_failed(self, msg: str) -> None:
        self.w._status("Writing outputs failed: %s" % msg, "error")

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
        for nid in self.w.model.node_order:
            node = self.w.model.nodes.get(nid)
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
            self.w, "Write into the original KLARF?", body,
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        return answer == QMessageBox.Yes

    def _writeback_plan_text(self) -> str:
        """乾跑一次寫回，回一句「會改幾列」。跑不出來就回空字串。

        **乾跑不寫任何東西**（`plan_writeback`），所以在確認之前跑它是安全的。
        """
        try:
            from d4t.core.export.klarf_out import plan_writeback

            doc = getattr(self.w.dataset, "klarf", None)
            rows = list(self.w.trial_results or [])
            if doc is None or not rows:
                return ""
            plan = plan_writeback(doc, rows, "inplace")
            return ("Based on the last run: %d of %d row(s) would change."
                    % (int(getattr(plan, "n_rows_changed", 0)),
                       int(getattr(plan, "n_rows_out", 0))))
        except Exception:  # 這只是一句提示，不准擋路
            return ""

    def _on_trial_progress(self, done: int, total: int) -> None:
        self.w._progress_set(int(done), int(total), "%v / %m defects")
        self.w._status("Running: %d / %d" % (int(done), int(total)))

    def _on_trial_done_async(self, results: Any) -> None:
        self.w._apply_trial_results(list(results or []),
                                  time.time() - (self._trial_t0 or time.time()))

    def _enabled_output_cards(self) -> int:
        """畫布上**啟用中**的 Output 卡有幾張（F86）。

        只數啟用的：停用的那張不會跑，把它算進去等於承諾一件不會發生的事。
        """
        from ..core.pipeline import get_step
        from ..core.pipeline.step import CATEGORY_BATCH

        n = 0
        for nid in self.w.model.node_order:
            node = self.w.model.nodes.get(nid)
            if node is None or not getattr(node, "enabled", True):
                continue
            try:
                if get_step(node.step).category == CATEGORY_BATCH:
                    n += 1
            except Exception:  # 一句提示不准擋畫面
                swallowed("studio._enabled_output_cards")
                continue
        return n
