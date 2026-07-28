# ADEPT parallel batch engine — authored 2026-07-28 (M2).
"""ProcessPool 平行批次（MMH 模式）：整個 lot 多進程跑完。

設計要點：
- worker 初始化（:func:`_init_worker`，TOP-LEVEL、picklable）只做一次：
  import 卡片庫（registry 註冊）、由 JSON dict 重建 Recipe、建 StageCache，
  存進模組全域 ``_WORKER`` —— 之後每顆 defect 只傳 DefectItem（純 dataclass，
  pickle 乾淨；不帶 KlarfDoc）。
- 單顆爆 = 該顆 FAIL dict，不殺整批（run_defect / run_defect_cached 永不
  raise；worker 層再包一層 try/except 保險）。
- 結果一律回「原始 item 順序」（as_completed 亂序 → index map 排回）。
- ``workers <= 1`` → 同進程循序跑（無 pool；語意與平行路徑相同，
  cache_dir 有給就照用）。
"""
from __future__ import annotations

import hashlib
import multiprocessing as _mp
import os
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from .cache import StageCache, dataset_token
from .engine import result_to_json_dict, run_defect, run_defect_cached
from .recipe import Recipe

__all__ = ["run_batch", "pin_cv2_deterministic"]

# adept/core/pipeline/batch.py → 上四層 = repo root（spawn 模式 sys.path 保險）
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

# worker 進程的全域狀態（initializer 填入；每個 worker 各自一份）
_WORKER: Dict[str, Any] = {}


def pin_cv2_deterministic() -> None:
    """把 cv2 調成 bit-reproducible 模式（worker 一律套用；parent 想跟
    worker 位元級一致時也可呼叫）。

    - ``setNumThreads(1)``：N workers × cv2 threads 會超額訂閱，pool 內
      本來就該單執行緒。
    - ``ipp.setUseIPP(False)``：Intel IPP 的 Sobel / filter kernel 會依
      buffer 位址（對齊）選不同 SIMD 路徑，同一張圖兩次重算可能差在
      1e-8 級 —— 關掉 IPP 後同輸入必同輸出（「快取重放 = 全程重算」
      的位元級驗收靠這個）。
    """
    try:
        import cv2
    except Exception:  # pragma: no cover — repo 必裝 cv2；防禦性而已
        return
    try:
        cv2.setNumThreads(1)
    except Exception:
        pass
    try:
        cv2.ipp.setUseIPP(False)
    except Exception:
        pass


def _init_worker(recipe_json: Dict[str, Any], kind: str,
                 cache_dir: Optional[str], token: str,
                 repo_root: Optional[str] = None) -> None:
    """ProcessPool worker 初始化（TOP-LEVEL：spawn/fork 皆可 pickle）。"""
    if repo_root and repo_root not in sys.path:
        sys.path.insert(0, repo_root)  # spawn 模式下確保 adept 找得到
    pin_cv2_deterministic()
    import adept.core.steps  # noqa: F401 — 觸發卡片註冊（fork 模式重複 import 無害）
    _WORKER["recipe"] = Recipe.from_json_dict(recipe_json)
    _WORKER["kind"] = str(kind)
    _WORKER["cache"] = StageCache(str(cache_dir)) if cache_dir else None
    _WORKER["token"] = str(token)


def _run_one(item: Any) -> Dict[str, Any]:
    """worker 執行一顆 defect（TOP-LEVEL picklable）→ JSON-safe dict。"""
    recipe: Recipe = _WORKER["recipe"]
    kind: str = _WORKER["kind"]
    cache: Optional[StageCache] = _WORKER["cache"]
    if cache is not None:
        r = run_defect_cached(recipe, item, kind, cache, _WORKER["token"])
    else:
        r = run_defect(recipe, item, kind)
    return result_to_json_dict(r)


def _fail_dict(item: Any, err: BaseException) -> Dict[str, Any]:
    """worker 層意外（pickle 失敗、worker 被殺…）→ 單顆 FAIL dict。"""
    return {
        "defect_id": str(getattr(item, "defect_id", "")),
        "ok": False,
        "error": f"{type(err).__name__}: {err}",
        "features": {},
        "score": None,
        "bin": None,
        "traces": [],
    }


def _dataset_token_for(dataset: Any) -> str:
    """由 Dataset 推 lot token：有 KLARF 就用檔案 stat（重產 lot 自動失效）；
    folder / 無 KLARF 模式退化為各 item 影像來源（路徑+mtime+size）的 sha1。"""
    doc = getattr(dataset, "klarf", None)
    src = getattr(doc, "source_path", None) if doc is not None else None
    if src and os.path.exists(str(src)):
        return dataset_token(src)
    h = hashlib.sha1()
    h.update(str(getattr(dataset, "kind", "")).encode("utf-8"))
    for item in getattr(dataset, "items", []) or []:
        images = getattr(item, "images", {}) or {}
        for ch in sorted(images):
            ref = images[ch]
            h.update(f"|{getattr(item, 'defect_id', '')}|{ch}"
                     f"|{ref.path}|{ref.page}".encode("utf-8"))
            try:
                st = os.stat(ref.path)
                h.update(f"|{st.st_mtime_ns}|{st.st_size}".encode("utf-8"))
            except OSError:
                pass
    return "items:" + h.hexdigest()


def _pool_context():
    """挑選 multiprocessing 啟動方式：主執行緒用 fork、非主執行緒用 spawn。

    為什麼要分：
    - **fork**（Linux 預設）快、且呼叫端腳本不需要 ``if __name__ == "__main__"``
      保護 —— CLI 與一般 script 都在主執行緒，維持這個便利性。
    - 但 fork 若從**非主執行緒**（例如 Studio 的 QThread）呼叫，子行程會繼承
      其他執行緒持有的鎖，實測 100% 死鎖（M3 Studio「試跑」按鈕）。這種情況
      改用 **spawn**：每個 worker 多約 0.3 s 啟動成本，但不會卡死。
      GUI/CLI 進入點都有 ``if __name__ == "__main__"`` 保護，spawn 安全。
    - Windows 沒有 fork，一律 spawn（本函式自動退回）。
    """
    on_main = threading.current_thread() is threading.main_thread()
    methods = _mp.get_all_start_methods()
    if on_main and "fork" in methods:
        return _mp.get_context("fork")
    return _mp.get_context("spawn")


def run_batch(recipe: Recipe, dataset: Any, *,
              workers: Optional[int] = None,
              cache_dir: Optional[str] = None,
              progress: Optional[Callable[[int, int, Dict[str, Any]], Any]] = None,
              abort_check: Optional[Callable[[], Any]] = None,
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """平行（或循序）跑整個 dataset，回傳 JSON-safe result dict 清單。

    - ``workers``：None → ``os.cpu_count()``；``<= 1`` → 同進程循序（無 pool）。
    - ``cache_dir``：有給 → 走 :func:`run_defect_cached`（影像段快取）。
    - ``progress(done_count, total, result_dict)``：每顆完成呼叫一次
      （done_count 從 1 起算；平行模式為完成順序，非 item 順序）。
    - ``abort_check()`` 回 truthy → 取消尚未開跑的顆、回傳已完成的部分結果。
    - ``limit``：只跑前 N 顆。
    - 回傳順序 = 原始 item 順序（被 abort 略過的顆不在清單裡）。
    - 單顆失敗（含 worker 層意外）→ 該顆 ``ok=False`` dict，不殺整批。
    """
    items = list(dataset.items) if limit is None else list(dataset.items)[:limit]
    n = len(items)
    kind = str(getattr(dataset, "kind", ""))
    token = _dataset_token_for(dataset) if cache_dir else ""

    if workers is None:
        workers = os.cpu_count() or 1
    workers = int(workers)

    # ---- 循序路徑（無 pool；語意同平行路徑）----
    if workers <= 1 or n <= 1:
        cache = StageCache(str(cache_dir)) if cache_dir else None
        out: List[Dict[str, Any]] = []
        done = 0
        for item in items:
            if abort_check is not None and abort_check():
                break
            try:
                if cache is not None:
                    r = run_defect_cached(recipe, item, kind, cache, token)
                else:
                    r = run_defect(recipe, item, kind)
                d = result_to_json_dict(r)
            except Exception as e:  # pragma: no cover — run_defect 永不 raise 的保險
                d = _fail_dict(item, e)
            out.append(d)
            done += 1
            if progress is not None:
                progress(done, n, d)
        return out

    # ---- 平行路徑：ProcessPoolExecutor ----
    results: Dict[int, Dict[str, Any]] = {}
    recipe_json = recipe.to_json_dict()
    with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=_pool_context(),
            initializer=_init_worker,
            initargs=(recipe_json, kind, cache_dir, token, _REPO_ROOT)) as ex:
        fut_to_idx = {ex.submit(_run_one, item): i
                      for i, item in enumerate(items)}
        done = 0
        for fut in as_completed(fut_to_idx):
            i = fut_to_idx[fut]
            try:
                d = fut.result()
            except Exception as e:  # 單顆 worker 意外 → FAIL dict，不殺整批
                d = _fail_dict(items[i], e)
            results[i] = d
            done += 1
            if progress is not None:
                progress(done, n, d)
            if abort_check is not None and abort_check():
                for f in fut_to_idx:
                    f.cancel()  # 尚未開跑的顆取消；跑一半的顆等它結束但不收
                break

    return [results[i] for i in sorted(results)]
