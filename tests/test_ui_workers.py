# ADEPT M3 背景工作層測試 — authored 2026-07-28.
"""``adept.ui.workers`` 的 headless 測試（QT_QPA_PLATFORM=offscreen）。

★ 為什麼 Qt 是「延遲匯入」★
  ``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡
  沒有任何 Qt 模組。pytest 在跑第一個測試之前會先 **collect**（import）所有
  測試模組，所以本檔若在最上層 ``import PySide6`` 或 ``import
  adept.ui.workers``（它自己 import PySide6），那道守門測試就會被這裡的
  import 汙染而失敗。
  因此：Qt 與 workers 一律在 ``qt`` fixture 裡才 import，並注入 module
  globals（``QtCore`` / ``workers``）給各測試與輔助函式使用。最上層只留
  Qt-free 的 core import。

非同步測試一律用 ``_pump()``（QEventLoop + 輪詢 QTimer + 逾時）驅動：
逾時就讓測試 fail，**不會**卡住整個 test session。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

import adept.core.steps  # noqa: F401 — 觸發卡片註冊
from adept.core.pipeline import Recipe

REPO = Path(__file__).resolve().parent.parent
RECIPE_PATH = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"

sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate  # noqa: E402

TIMEOUT_MS = 30000          # 單次等待上限（實測整檔 < 5s）
PREVIEW_NODES = ["norm", "align", "sub", "dn", "snr"]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qt():
    """延遲匯入 Qt 與 workers（見模組 docstring），建立唯一的 QApplication。"""
    from PySide6 import QtCore, QtWidgets

    import adept.ui.workers as workers_mod

    g = globals()
    g["QtCore"] = QtCore
    g["workers"] = workers_mod

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(scope="module")
def synlot(tmp_path_factory):
    """6 顆 defect 的合成 lot（KLARF + 多頁 TIFF + ground truth）。"""
    out = tmp_path_factory.mktemp("ui_synlot")
    return generate(str(out), n=6, seed=7)


@pytest.fixture(scope="module")
def recipe():
    return Recipe.load(str(RECIPE_PATH))


@pytest.fixture(scope="module")
def dataset(qt, synlot):
    return workers.DatasetLoadWorker.run_sync(synlot["klarf"])


@pytest.fixture
def live():
    """建立 worker 的工廠；測試結束一律 shutdown（測試自己再驗一次沒漏）。"""
    created = []

    def make(cls):
        w = cls()
        created.append(w)
        return w

    yield make
    for w in created:
        w.shutdown(5000)


# ---------------------------------------------------------------------------
# 事件迴圈驅動
# ---------------------------------------------------------------------------
def _pump(predicate, timeout_ms=TIMEOUT_MS):
    """轉 GUI event loop 直到 ``predicate()`` 為真；逾時回 False（不 hang）。"""
    loop = QtCore.QEventLoop()
    deadline = time.monotonic() + timeout_ms / 1000.0
    state = {"ok": False}

    def check():
        if predicate():
            state["ok"] = True
            loop.quit()
        elif time.monotonic() > deadline:
            loop.quit()

    poll = QtCore.QTimer()
    poll.setInterval(5)
    poll.timeout.connect(check)
    poll.start()
    check()                       # predicate 可能已成立
    if not state["ok"]:
        loop.exec()
    poll.stop()
    return state["ok"]


def _drain(ms=100):
    """再多轉一下 event loop，讓可能遲到的訊號進來（例如多餘的 ready）。"""
    _pump(lambda: False, ms)


def _assert_reaped(w):
    """關閉後不該留下還在跑的 QThread。"""
    assert w.shutdown(5000) is True
    assert w.is_running() is False
    assert w.thread_obj is None
    assert not w._zombies, "有執行緒 join 逾時未回收"


# ---------------------------------------------------------------------------
# 1) 同步模式（headless，完全不碰 Qt 執行緒）
# ---------------------------------------------------------------------------
def test_dataset_run_sync(qt, synlot):
    ds = workers.DatasetLoadWorker.run_sync(synlot["klarf"])
    assert ds.kind == "ebi_patch"
    assert len(ds.items) == 6
    assert "test" in ds.items[0].images and "ref" in ds.items[0].images
    # 顯式帶 tiff 參數也要通
    ds2 = workers.DatasetLoadWorker.run_sync(synlot["klarf"], synlot["tiff"])
    assert ds2.kind == "ebi_patch" and len(ds2.items) == 6


def test_dataset_run_sync_raises_on_error(qt, tmp_path):
    # 路徑是資料夾 → load_dataset 開檔就爆（KLARF parser 對「不存在的檔」
    # 是回空 doc 不 raise，所以這裡用必定 raise 的情境）
    with pytest.raises(Exception):
        workers.DatasetLoadWorker.run_sync(str(tmp_path))


def test_preview_run_sync(qt, recipe, dataset):
    item = dataset.items[0]
    # 全程跑完：有 score / bin
    full = workers.PreviewWorker.run_sync(recipe, item, dataset.kind)
    assert full.ok, full.error
    assert full.score is not None and full.bin in (0, 1)

    # upto_node：停在該節點，context 帶著中間影像
    mid = workers.PreviewWorker.run_sync(recipe, item, dataset.kind,
                                         upto_node="sub")
    assert mid.ok, mid.error
    assert mid.context is not None
    assert "diff" in mid.context.images and "test" in mid.context.images
    assert mid.traces[-1].node_id == "sub"
    assert mid.score is None                 # 中途預覽不算分


def test_trial_run_sync(qt, recipe, dataset):
    out = workers.TrialWorker.run_sync(recipe, dataset, 6, workers=1)
    assert len(out) == 6
    assert all(d["ok"] for d in out), [(d["defect_id"], d["error"]) for d in out]
    assert all(isinstance(d["score"], float) for d in out)
    assert all(d["features"].get("score") is not None for d in out)


# ---------------------------------------------------------------------------
# 2) DatasetLoadWorker 非同步
# ---------------------------------------------------------------------------
def test_dataset_worker_async(qt, synlot, live):
    w = live(workers.DatasetLoadWorker)
    got, errs = [], []
    w.loaded.connect(got.append)
    w.failed.connect(errs.append)

    assert w.start(synlot["klarf"]) is True
    assert _pump(lambda: bool(got or errs)), "loaded/failed 30 秒內沒有發出"

    assert not errs, errs
    assert len(got) == 1
    assert got[0].kind == "ebi_patch" and len(got[0].items) == 6
    _assert_reaped(w)


def test_dataset_worker_async_failure(qt, tmp_path, live):
    w = live(workers.DatasetLoadWorker)
    got, errs = [], []
    w.loaded.connect(got.append)
    w.failed.connect(errs.append)

    w.start(str(tmp_path))                   # 資料夾 → load_dataset raise
    assert _pump(lambda: bool(got or errs)), "failed 30 秒內沒有發出"
    assert not got and len(errs) == 1 and errs[0]
    _assert_reaped(w)


# ---------------------------------------------------------------------------
# 3) PreviewWorker：請求合併
# ---------------------------------------------------------------------------
def test_preview_worker_coalesces_rapid_requests(qt, recipe, dataset, live):
    w = live(workers.PreviewWorker)
    results, busy, errs = [], [], []
    w.ready.connect(results.append)
    w.busy.connect(busy.append)
    w.failed.connect(errs.append)

    item = dataset.items[0]
    for node in PREVIEW_NODES:              # 5 個快速連發（模擬拖參數）
        w.request(recipe, item, dataset.kind, upto_node=node)

    assert _pump(lambda: busy and busy[-1] is False), "佇列 30 秒內沒有排空"
    _drain(150)                             # 等等看還有沒有遲到的 ready

    assert not errs, errs
    assert results, "至少要有一筆預覽結果"
    assert len(results) < len(PREVIEW_NODES), \
        f"沒有合併：{len(results)} 筆 ready（連發 {len(PREVIEW_NODES)} 次）"
    # 最後一筆結果必須對應最後一次請求的 upto_node
    last = results[-1]
    assert last.ok, last.error
    assert last.traces[-1].node_id == PREVIEW_NODES[-1]
    assert last.context is not None and last.context.images
    # busy 先 True、最後 False
    assert busy[0] is True and busy[-1] is False
    assert w.has_pending() is False
    _assert_reaped(w)


def test_preview_worker_sequential_requests(qt, recipe, dataset, live):
    """一次一筆（每筆等它跑完）→ 不該有任何合併，每筆都要回。"""
    w = live(workers.PreviewWorker)
    results, busy = [], []
    w.ready.connect(results.append)
    w.busy.connect(busy.append)

    item = dataset.items[1]
    for i, node in enumerate(["norm", "sub", "dn"]):
        w.request(recipe, item, dataset.kind, upto_node=node)
        assert _pump(lambda: len(results) > i), f"第 {i} 筆預覽逾時"
    assert _pump(lambda: busy and busy[-1] is False)

    assert [r.traces[-1].node_id for r in results] == ["norm", "sub", "dn"]
    assert busy.count(True) == 3
    _assert_reaped(w)


def test_preview_worker_unexpected_error_goes_to_failed(
        qt, recipe, dataset, live, monkeypatch):
    """錯誤策略：run_defect 意外爆掉 → 只發 failed(str)，不發假的 ready。"""
    def boom(*a, **k):
        raise RuntimeError("模擬意外")

    monkeypatch.setattr(workers, "run_defect", boom)
    w = live(workers.PreviewWorker)
    results, busy, errs = [], [], []
    w.ready.connect(results.append)
    w.busy.connect(busy.append)
    w.failed.connect(errs.append)

    w.request(recipe, dataset.items[0], dataset.kind)
    assert _pump(lambda: bool(errs) or bool(results)), "failed 30 秒內沒有發出"
    _drain(100)

    assert not results
    assert len(errs) == 1 and "模擬意外" in errs[0]
    assert busy[0] is True and busy[-1] is False
    _assert_reaped(w)


# ---------------------------------------------------------------------------
# 4) TrialWorker 非同步 + abort
# ---------------------------------------------------------------------------
def test_trial_worker_async(qt, recipe, dataset, live):
    w = live(workers.TrialWorker)
    prog, done, errs = [], [], []
    w.progress.connect(lambda d, t: prog.append((d, t)))
    w.done.connect(done.append)
    w.failed.connect(errs.append)

    assert w.start(recipe, dataset, 6, workers=1) is True
    assert w.start(recipe, dataset, 6, workers=1) is False   # 忙碌中不重入
    assert _pump(lambda: bool(done or errs)), "done/failed 30 秒內沒有發出"

    assert not errs, errs
    out = done[0]
    assert len(out) == 6
    assert all(d["ok"] for d in out), [(d["defect_id"], d["error"]) for d in out]
    assert all(d["score"] is not None for d in out)
    assert prog, "progress 一次都沒發"
    assert prog[-1] == (6, 6)
    assert [d for d, _ in prog] == sorted(d for d, _ in prog)
    _assert_reaped(w)


def test_trial_worker_abort_still_delivers(qt, recipe, dataset, live):
    w = live(workers.TrialWorker)
    done, errs = [], []
    w.done.connect(done.append)
    w.failed.connect(errs.append)

    w.start(recipe, dataset, 6, workers=1)
    w.abort()                                # 立刻喊停
    assert w.is_aborted() is True
    assert _pump(lambda: bool(done or errs)), "abort 後 done 30 秒內沒有發出"

    assert not errs, errs
    assert isinstance(done[0], list)
    assert len(done[0]) <= 6                 # 部分結果（可能為空）
    _assert_reaped(w)


# ---------------------------------------------------------------------------
# 5) 生命週期：不漏執行緒
# ---------------------------------------------------------------------------
def test_shutdown_is_safe_without_any_job(qt):
    for cls in (workers.DatasetLoadWorker, workers.PreviewWorker,
                workers.TrialWorker):
        w = cls()
        assert w.is_running() is False
        assert w.thread_obj is None
        assert w.shutdown() is True          # 沒跑過也能安全關
        assert w.stop() is True              # 重複關也安全
        assert w.thread_obj is None


def test_stop_during_running_job_joins(qt, recipe, dataset, synlot):
    """關窗情境：工作正在跑時 stop() → join 完成、無殘留執行緒。"""
    w = workers.TrialWorker()
    done = []
    w.done.connect(done.append)
    w.start(recipe, dataset, 6, workers=1)
    assert w.is_running() is True
    assert w.stop(10000) is True             # 設 abort 旗標 + join
    assert w.is_running() is False
    assert w.thread_obj is None
    assert not w._zombies

    p = workers.PreviewWorker()
    p.request(recipe, dataset.items[0], dataset.kind, upto_node="snr")
    p.request(recipe, dataset.items[0], dataset.kind, upto_node="glv")
    assert p.has_pending() is True
    assert p.shutdown(10000) is True
    assert p.has_pending() is False          # 待跑請求作廢
    assert p.is_running() is False and p.thread_obj is None
    _drain(50)                               # 過期的 finished 通知不該炸
    assert p.is_running() is False
