# M3 迴歸測試：run_batch 從非主執行緒呼叫不得死鎖（Studio「試跑」按鈕的路徑）。
"""背景：Linux 預設的 fork 若從非主執行緒呼叫，子行程會繼承其他執行緒持有的鎖，
Studio 用 QThread 跑 run_batch(workers=2) 實測 100% 死鎖（第二次執行必卡）。
修法見 batch.py `_pool_context()`：主執行緒 fork、非主執行緒 spawn。
"""
from __future__ import annotations

import multiprocessing
import sys
import threading
from pathlib import Path



REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate  # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import Recipe, run_batch  # noqa: E402
from d4t.core.pipeline.batch import _pool_context  # noqa: E402

RECIPE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"


def test_pool_context_main_thread_prefers_fork_when_available():
    ctx = _pool_context()
    if "fork" in multiprocessing.get_all_start_methods():
        assert ctx.get_start_method() == "fork"   # 主執行緒：保留免 __main__ 保護的便利
    else:
        assert ctx.get_start_method() == "spawn"  # Windows


def test_pool_context_off_thread_uses_spawn():
    seen = {}

    def probe():
        seen["method"] = _pool_context().get_start_method()

    t = threading.Thread(target=probe)
    t.start()
    t.join(timeout=10)
    assert seen.get("method") == "spawn"


def test_run_batch_twice_from_worker_thread_does_not_deadlock(tmp_path):
    """連續兩次從背景執行緒平行跑批次 —— 修正前第二次必死鎖。"""
    paths = generate(str(tmp_path / "lot"), n=6, seed=7)
    ds = load_dataset(paths["klarf"])
    recipe = Recipe.load(str(RECIPE))

    results = {}

    def job(tag):
        results[tag] = run_batch(recipe, ds, workers=2, limit=6)

    for tag in ("first", "second"):
        t = threading.Thread(target=job, args=(tag,))
        t.start()
        t.join(timeout=180)
        assert not t.is_alive(), f"run_batch 在背景執行緒卡住（{tag} 次）"

    for tag in ("first", "second"):
        assert len(results[tag]) == 6
        assert all(r.get("ok") for r in results[tag])
