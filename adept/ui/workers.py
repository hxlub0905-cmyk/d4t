# ADEPT Studio 背景工作層 — authored 2026-07-28 (M3).
"""Studio 的三個背景工作：載資料集、單顆預覽、試跑批次。

設計原則
--------
- **GUI 不卡**：每個工作把 core 的重運算（``load_dataset`` / ``run_defect`` /
  ``run_batch``）丟到自己的 :class:`QThread` 上跑；worker 物件本身留在 GUI
  執行緒，只在背景執行緒 ``emit`` 訊號（Qt 的 AutoConnection 會依「接收端」
  所在執行緒自動排隊，UI slot 仍在 GUI 執行緒被呼叫）。背景程式碼**不碰**
  任何 GUI 物件。
- **執行緒樣式（統一）**：每次 ``start()`` / ``request()`` 都開一條全新的
  ``QThread``，把一個 :class:`_Task`（純 QObject，帶要跑的 callable）
  ``moveToThread`` 過去，``thread.started -> task.run``；``run`` 跑完
  ``emit finished`` 後呼叫 ``QThread.currentThread().quit()`` 結束該執行緒的
  event loop。GUI 端收到 ``finished``（queued）後 ``quit() + wait()`` 回收，
  不留殘骸、不 poll、不 busy-loop。
- **同步模式**：三個 worker 都提供 ``run_sync(...)``，完全不碰 Qt 執行緒，
  給 headless 測試與 CLI 用（``QApplication`` 不存在也能跑）。
- **關窗安全**：``stop()``（``shutdown()`` 為別名）會先設中止旗標 / 清掉
  待跑請求，再 join 背景執行緒；之後 ``is_running()`` 為 False、內部
  thread 參考歸 None。無法在時限內結束的執行緒（不可中斷的 core 呼叫）
  會被移到 ``_zombies`` 保住參考，**絕不** ``terminate()``（會毀掉 numpy /
  cv2 的狀態），也絕不在還在跑時銷毀 QThread 物件。

注意：非同步模式（``start`` / ``request``）需要有 ``QApplication`` 且
GUI 執行緒的 event loop 有在轉，訊號才會被投遞——這是 Qt 的常態；
``run_sync`` 沒有這個限制。
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

import adept.core.steps  # noqa: F401 — 觸發卡片註冊（Qt-free、便宜）
from adept.core.ingest.dataset import Dataset, load_dataset
from adept.core.pipeline import Recipe, run_batch, run_defect
from adept.core.pipeline.engine import DefectResult

__all__ = ["DatasetLoadWorker", "PreviewWorker", "TrialWorker"]

#: ``stop()`` 等背景執行緒收工的預設上限（毫秒）。
DEFAULT_JOIN_MS = 15000


# ---------------------------------------------------------------------------
# 內部：一次性的執行緒任務
# ---------------------------------------------------------------------------
class _Task(QObject):
    """跑一個 callable 的一次性任務物件（會被 moveToThread 到背景執行緒）。

    ``fn`` 自己負責 emit 業務訊號（loaded / ready / done / failed）；
    ``_Task`` 只保證「跑完一定會 emit ``finished(job_id)`` 並讓執行緒 quit」。
    ``job_id`` 讓 GUI 端能認出並忽略**過期**的完成通知（queued 訊號可能在
    該份工作已被回收之後才送達）。
    """

    finished = Signal(int)

    def __init__(self, job_id: int, fn: Callable[[], None]) -> None:
        super().__init__()
        self._job_id = int(job_id)
        self._fn = fn

    def run(self) -> None:  # 在背景執行緒被呼叫
        try:
            self._fn()
        finally:
            try:
                self.finished.emit(self._job_id)
            finally:
                thread = QThread.currentThread()
                if thread is not None:
                    thread.quit()   # 結束這條 thread 的 event loop


class _ThreadedWorker(QObject):
    """三個 worker 的共用底座：一次一條 QThread，收工即回收。"""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._task: Optional[_Task] = None
        self._job_id = 0                    # 目前這份工作的編號（過期通知用）
        self._zombies: List[QThread] = []   # join 逾時、還在跑的執行緒（保住參考）

    # ---- 狀態查詢 ---------------------------------------------------------
    def is_running(self) -> bool:
        """目前是否有背景工作在跑。"""
        t = self._thread
        return t is not None and t.isRunning()

    @property
    def thread_obj(self) -> Optional[QThread]:
        """目前的背景執行緒物件（沒有工作時為 None）——測試用。"""
        return self._thread

    # ---- 啟動 / 回收 ------------------------------------------------------
    def _start_job(self, fn: Callable[[], None]) -> None:
        """開一條新 QThread 跑 ``fn``（必須在 GUI 執行緒呼叫）。"""
        self._reap(DEFAULT_JOIN_MS)          # 前一條若已收工，先清乾淨
        self._job_id += 1
        thread = QThread()
        task = _Task(self._job_id, fn)
        task.moveToThread(thread)
        thread.started.connect(task.run)
        task.finished.connect(self._on_task_finished)   # queued 回 GUI 執行緒
        self._thread = thread
        self._task = task
        thread.start()

    def _on_task_finished(self, job_id: int) -> None:
        """背景任務跑完（GUI 執行緒、queued）：回收執行緒後給子類接手。"""
        if int(job_id) != self._job_id:
            return                           # 過期通知（該份工作已被回收）
        self._reap(DEFAULT_JOIN_MS)
        self._job_finished()

    def _job_finished(self) -> None:
        """子類覆寫：一份工作結束後的後續動作（例如跑下一個待跑請求）。"""

    def _reap(self, timeout_ms: int) -> bool:
        """quit + wait 目前的執行緒並丟掉參考；回傳是否成功收乾淨。

        同時把 ``_job_id`` 往前推一格，讓這份工作之後才送達的 queued
        ``finished`` 通知被視為過期而忽略。
        """
        thread = self._thread
        if thread is None:
            return True
        self._job_id += 1
        thread.quit()
        ok = bool(thread.wait(int(timeout_ms)))
        self._thread = None
        self._task = None
        if not ok:
            # 還在跑（core 呼叫不可中斷）：保住參考，QThread 物件不能被銷毀
            self._zombies.append(thread)
        return ok

    # ---- 關閉 -------------------------------------------------------------
    def stop(self, timeout_ms: int = DEFAULT_JOIN_MS) -> bool:
        """中止並 join 背景執行緒；回傳是否已完全收乾淨（關窗時呼叫）。"""
        self._before_stop()
        return self._reap(timeout_ms)

    def shutdown(self, timeout_ms: int = DEFAULT_JOIN_MS) -> bool:
        """:meth:`stop` 的別名（關窗語意讀起來比較順）。"""
        return self.stop(timeout_ms)

    def _before_stop(self) -> None:
        """子類覆寫：join 之前要設的中止旗標 / 要清的待跑佇列。"""


# ---------------------------------------------------------------------------
# 1) 載入資料集
# ---------------------------------------------------------------------------
class DatasetLoadWorker(_ThreadedWorker):
    """背景載入 KLARF（可帶 patch TIFF）→ :class:`Dataset`。

    訊號：``loaded(Dataset)`` 成功、``failed(str)`` 失敗（``load_dataset``
    會 raise，例如檔案不存在 / KLARF 壞掉）。
    """

    loaded = Signal(object)
    failed = Signal(str)

    def start(self, path: str, tiff: Optional[str] = None) -> bool:
        """開背景執行緒載入；已有工作在跑時回傳 False（不排隊）。"""
        if self.is_running():
            return False
        path_s = str(path)
        tiff_s = None if tiff is None else str(tiff)

        def job() -> None:
            try:
                ds = load_dataset(path_s, tiff_s)
            except Exception as e:                      # noqa: BLE001 — 一律回報
                self.failed.emit(f"{type(e).__name__}: {e}")
            else:
                self.loaded.emit(ds)

        self._start_job(job)
        return True

    @staticmethod
    def run_sync(path: str, tiff: Optional[str] = None) -> Dataset:
        """同步載入（不開執行緒）；失敗直接 raise，給測試 / headless 用。"""
        return load_dataset(str(path), None if tiff is None else str(tiff))


# ---------------------------------------------------------------------------
# 2) 單顆預覽（請求合併）
# ---------------------------------------------------------------------------
class PreviewWorker(_ThreadedWorker):
    """單顆 defect 預覽：**只保留最新一筆**待跑請求的合併式 worker。

    Studio 每動一次參數就會呼叫 :meth:`request`，過期的請求算完也沒人看，
    所以：有工作在跑時只記住**最後一筆**，前面的待跑請求靜靜丟掉；
    目前這筆跑完再跑它。

    訊號
    ----
    ``ready(DefectResult)``
        一筆預覽算完（``run_defect`` 永不 raise，失敗會是 ``ok=False`` 的
        DefectResult，一樣走 ``ready``）。
    ``busy(bool)``
        ``True``：有工作開跑（每筆都發，statusbar 直接接）；
        ``False``：佇列排空（沒有待跑請求了）。
        為了讓 UI 立即有反應，``busy`` 在**呼叫端（GUI）執行緒**同步發出。
    ``failed(str)``
        **錯誤策略**：``run_defect`` 依合約永不 raise，所以這個訊號只會在
        「意外」時出現（例如 registry 被抽掉、記憶體不足）。此時**不會**
        再發 ``ready``（不硬湊一顆假的 DefectResult，避免 UI 把它當成
        真的預覽結果畫出來）；UI 該做的是保留上一張畫面 + statusbar 顯示
        錯誤。``busy`` 的 True/False 配對仍然成立。
        同步模式（:meth:`run_sync`）則相反：例外照常往外 raise。
    """

    ready = Signal(object)
    busy = Signal(bool)
    failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._pending: Optional[tuple] = None   # 只留最新一筆 (recipe,item,kind,upto)

    # ---- 對外 -------------------------------------------------------------
    def request(self, recipe: Recipe, item: Any, kind: str,
                upto_node: Optional[str] = None) -> None:
        """要求算一筆預覽；忙碌中則覆蓋掉先前的待跑請求（舊的直接丟）。"""
        job = (recipe, item, str(kind), upto_node)
        if self.is_running():
            self._pending = job            # 覆蓋 = 丟掉更舊的請求
            return
        self._launch(job)

    @staticmethod
    def run_sync(recipe: Recipe, item: Any, kind: str,
                 upto_node: Optional[str] = None) -> DefectResult:
        """同步跑一筆預覽（不開執行緒）；``keep_context=True`` 以便看中間影像。"""
        return run_defect(recipe, item, str(kind), keep_context=True,
                          upto_node=upto_node)

    def has_pending(self) -> bool:
        """是否還有待跑的請求（測試 / statusbar 用）。"""
        return self._pending is not None

    # ---- 內部 -------------------------------------------------------------
    def _launch(self, job: tuple) -> None:
        recipe, item, kind, upto = job

        def work() -> None:
            try:
                r = run_defect(recipe, item, kind, keep_context=True,
                               upto_node=upto)
            except Exception as e:          # noqa: BLE001 — 合約外的意外
                self.failed.emit(f"{type(e).__name__}: {e}")
            else:
                self.ready.emit(r)

        self.busy.emit(True)                # 呼叫端執行緒：UI 立刻變忙
        self._start_job(work)

    def _job_finished(self) -> None:
        """一筆算完（GUI 執行緒）：有待跑就接著跑，沒有就宣告閒置。"""
        job, self._pending = self._pending, None
        if job is not None:
            self._launch(job)
        else:
            self.busy.emit(False)

    def _before_stop(self) -> None:
        self._pending = None                # 關窗：待跑請求全部作廢


# ---------------------------------------------------------------------------
# 3) 試跑批次
# ---------------------------------------------------------------------------
class TrialWorker(_ThreadedWorker):
    """在背景跑 :func:`adept.core.pipeline.run_batch`（前 N 顆試跑）。

    訊號：``progress(done, total)``、``done(list)``（result dict 清單，
    即使被 :meth:`abort` 也會帶著部分結果發出）、``failed(str)``。

    ``run_batch`` 內部可能開 ProcessPool——從背景執行緒開子進程沒問題
    （子進程不繼承 Qt event loop 的使用）。
    """

    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._abort = threading.Event()

    # ---- 對外 -------------------------------------------------------------
    def start(self, recipe: Recipe, dataset: Any, n: int,
              workers: Optional[int] = None,
              cache_dir: Optional[str] = None) -> bool:
        """開背景執行緒試跑前 ``n`` 顆；已有工作在跑時回傳 False。"""
        if self.is_running():
            return False
        self._abort.clear()
        limit = int(n)
        w = None if workers is None else int(workers)
        cdir = None if cache_dir is None else str(cache_dir)

        def progress_cb(done_count: int, total: int,
                        _result: Dict[str, Any]) -> None:
            self.progress.emit(int(done_count), int(total))

        def job() -> None:
            try:
                out = run_batch(recipe, dataset, workers=w, cache_dir=cdir,
                                limit=limit, progress=progress_cb,
                                abort_check=self._abort.is_set)
            except Exception as e:          # noqa: BLE001 — 整批爆掉才會走到這
                self.failed.emit(f"{type(e).__name__}: {e}")
            else:
                self.done.emit(out)

        self._start_job(job)
        return True

    def abort(self) -> None:
        """設中止旗標：``run_batch`` 的 ``abort_check`` 會看到，
        已完成的部分結果仍會由 ``done`` 送出（不 join，不阻塞 UI）。"""
        self._abort.set()

    def is_aborted(self) -> bool:
        """中止旗標目前狀態。"""
        return self._abort.is_set()

    @staticmethod
    def run_sync(recipe: Recipe, dataset: Any, n: int, workers: int = 1,
                 cache_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """同步試跑（不開執行緒），回傳 result dict 清單。"""
        return run_batch(recipe, dataset, workers=int(workers),
                         cache_dir=None if cache_dir is None else str(cache_dir),
                         limit=int(n))

    # ---- 內部 -------------------------------------------------------------
    def _before_stop(self) -> None:
        self._abort.set()                   # 關窗：讓 run_batch 早點收手
