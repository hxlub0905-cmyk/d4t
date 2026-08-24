# d4t parallel batch engine — authored 2026-07-28 (M2).
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
from typing import Any, Callable, Dict, List, Optional, Sequence

from dataclasses import replace as _replace

from ..ingest import pair_source
from .cache import StageCache, dataset_token
from .context import BatchContext, Context
from .expression import parse_expression
from .step import REGISTRY, SCALE_LOT
from .engine import (
    _eval_score, _safe_num, result_to_json_dict, run_defect,
    run_defect_cached,
)
from .recipe import Recipe, execution_order

__all__ = ["run_batch", "apply_lot_scaling", "redecide",
           "pin_cv2_deterministic"]

# d4t/core/pipeline/batch.py → 上四層 = repo root（spawn 模式 sys.path 保險）
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
                 repo_root: Optional[str] = None,
                 sources: Optional[Dict[str, Any]] = None) -> None:
    """ProcessPool worker 初始化（TOP-LEVEL：spawn/fork 皆可 pickle）。

    ``sources`` 是掛在 main 上的第二（第三…）份資料，``{代號: [DefectItem, …]}``
    （F15）。**在 init 傳一次**，不是每顆都傳：它是一整批共用的東西，而
    ``DefectItem`` 裝的是路徑不是像素，pickle 一次很便宜。
    """
    if repo_root and repo_root not in sys.path:
        sys.path.insert(0, repo_root)  # spawn 模式下確保 d4t 找得到
    pin_cv2_deterministic()
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊（fork 模式重複 import 無害）
    _WORKER["recipe"] = Recipe.from_json_dict(recipe_json)
    _WORKER["kind"] = str(kind)
    _WORKER["cache"] = StageCache(str(cache_dir)) if cache_dir else None
    _WORKER["token"] = str(token)
    _WORKER["sources"] = dict(sources or {})


def _run_one(item: Any) -> Dict[str, Any]:
    """worker 執行一顆 defect（TOP-LEVEL picklable）→ JSON-safe dict。"""
    recipe: Recipe = _WORKER["recipe"]
    kind: str = _WORKER["kind"]
    cache: Optional[StageCache] = _WORKER["cache"]
    sources = _WORKER.get("sources") or {}
    if cache is not None:
        r = run_defect_cached(recipe, item, kind, cache, _WORKER["token"],
                              sources=sources)
    else:
        r = run_defect(recipe, item, kind, sources=sources)
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


def _sidecar_token(dataset: Any) -> str:
    """掛上去的**附加檔**（GLAS 的 label map）也要進 token。

    為什麼這一段非有不可（F11 Region-3 第 2 步）
    --------------------------------------------
    有 KLARF 的時候，下面那條路只看 **KLARF 的 stat** —— 而換一份 GDS 匯出
    完全不會動到 KLARF。於是「同一個 lot、換一個 mask 目錄」的 token 一模一樣，
    影像段快取就會把**上一份匯出算出來的框**餵回來：跑得完、有數字、而且是錯的
    （鐵則 9 講的正是這個形狀）。

    一顆都沒有 sidecar 時回空字串，**token 因此逐字元不變** —— 既有的快取目錄
    與黃金值不受影響。
    """
    h = hashlib.sha1()
    seen = False
    for item in getattr(dataset, "items", []) or []:
        cars = getattr(item, "sidecars", None) or {}
        for name in sorted(cars):
            seen = True
            ref = cars[name]
            h.update(f"|{getattr(item, 'defect_id', '')}|{name}"
                     f"|{ref.path}|{ref.page}".encode("utf-8"))
            try:
                st = os.stat(ref.path)
                h.update(f"|{st.st_mtime_ns}|{st.st_size}".encode("utf-8"))
            except OSError:
                pass
    return "|sidecars:" + h.hexdigest() if seen else ""


def _sources_token(dataset: Any) -> str:
    """掛在 main 上的**第二份資料**也要進 token（F15）。

    理由跟 :func:`_sidecar_token` 逐字相同：有 KLARF 的時候上面那條路只看
    **main 的 KLARF stat**，而換一份第二 source 完全不會動到它。於是
    「同一個 lot、換一份 RSEM」的 token 一模一樣，影像段快取會把上一份配到的
    那張圖餵回來 —— 跑得完、有數字、而且是錯的（鐵則 9）。

    **代號也要進去**：同一份資料換一個代號，`pair_source` 卡指的就是另一個東西。

    一份都沒掛時回空字串，**token 因此逐字元不變** —— 既有的快取目錄與黃金值
    不受影響。
    """
    srcs = getattr(dataset, "sources", None) or {}
    if not srcs:
        return ""
    h = hashlib.sha1()
    for sid in sorted(srcs):
        h.update(("|src|%s|" % sid).encode("utf-8"))
        sub = srcs[sid]
        doc = getattr(sub, "klarf", None)
        path = getattr(doc, "source_path", None) if doc is not None else None
        if path and os.path.exists(str(path)):
            h.update(dataset_token(str(path)).encode("utf-8"))
            continue
        for item in getattr(sub, "items", []) or []:
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
    return "+src:" + h.hexdigest()


def _dataset_token_for(dataset: Any) -> str:
    """由 Dataset 推 lot token：有 KLARF 就用檔案 stat（重產 lot 自動失效）；
    folder / 無 KLARF 模式退化為各 item 影像來源（路徑+mtime+size）的 sha1。

    兩條路後面都接 :func:`_sidecar_token` —— 見那一支的說明。
    """
    doc = getattr(dataset, "klarf", None)
    src = getattr(doc, "source_path", None) if doc is not None else None
    if src and os.path.exists(str(src)):
        return (dataset_token(src) + _sidecar_token(dataset)
                + _sources_token(dataset))
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
    return ("items:" + h.hexdigest() + _sidecar_token(dataset)
            + _sources_token(dataset))


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
    # ---- 分流（F23）：route_by 的那一欄要在每一顆的 `fields` 裡 ----
    # 使用者不必記得先 carry —— 開跑前自動補。**只在有顆缺這一欄時才動手**，
    # 而且補的是「現有欄位 ∪ 這一欄」：`fill_fields` 是整份換掉（刻意的，見
    # 它的說明），只補一欄的話會把 Load 卡 carry 進來的其他欄安靜地洗掉。
    # 每一顆都已經有這一欄（測試手填、或上游已 carry）→ 一個位元都不動。
    rb = getattr(recipe, "route_by", None)
    if rb is not None:
        col = str(rb.column or "").strip().upper()
        if col and any(col not in (getattr(it, "fields", None) or {})
                       for it in items):
            from ..ingest.dataset import fill_fields
            have: set = set()
            for it in getattr(dataset, "items", []) or []:
                have.update((getattr(it, "fields", None) or {}).keys())
            fill_fields(dataset, sorted(have | {col}))
    token = _dataset_token_for(dataset) if cache_dir else ""
    # 掛在 main 上的第二份資料（F15）。只送 items —— `Dataset` 掛著 `KlarfDoc`，
    # 而那個東西刻意不進 worker（見模組說明）。
    sources = pair_source.sources_for_run(dataset)

    if workers is None:
        workers = os.cpu_count() or 1
    workers = int(workers)

    # ---- 循序路徑（無 pool；語意同平行路徑）----
    if workers <= 1 or n <= 1:
        # **這裡也要 pin**（F15）。以前只有 worker 套，於是「語意相同」少了最後
        # 一段：cv2 的 IPP 路徑會依 buffer 對齊選不同 SIMD，NCC 那種卡的分數在
        # `workers=1` 與 `workers=2` 差在 1e-7 —— 鐵則 9 講的正是這件事。而
        # Studio 的試跑走的就是這條路（一顆 → n<=1），所以那個差還會變成
        # 「畫面上的數字」與「批次的數字」不一樣。
        pin_cv2_deterministic()
        cache = StageCache(str(cache_dir)) if cache_dir else None
        out: List[Dict[str, Any]] = []
        done = 0
        for item in items:
            if abort_check is not None and abort_check():
                break
            try:
                if cache is not None:
                    r = run_defect_cached(recipe, item, kind, cache, token,
                                          sources=sources)
                else:
                    r = run_defect(recipe, item, kind, sources=sources)
                d = result_to_json_dict(r)
            except Exception as e:  # pragma: no cover — run_defect 永不 raise 的保險
                d = _fail_dict(item, e)
            out.append(d)
            done += 1
            if progress is not None:
                progress(done, n, d)
        # 「跟整批比」的兩趟判定（F23 期3）。沒有 scale 行＝一個位元不動。
        apply_lot_scaling(recipe, out)
        return out

    # ---- 平行路徑：ProcessPoolExecutor ----
    results: Dict[int, Dict[str, Any]] = {}
    recipe_json = recipe.to_json_dict()
    with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=_pool_context(),
            initializer=_init_worker,
            initargs=(recipe_json, kind, cache_dir, token, _REPO_ROOT,
                      sources)) as ex:
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

    out = [results[i] for i in sorted(results)]
    # 同循序路徑：兩條路收攏在同一份數字上（workers=1 與 2 逐項相同）。
    apply_lot_scaling(recipe, out)
    return out


# --------------------------------------------------------------------------- #
# 「跟整批比」的兩趟判定（F23 期3）
# --------------------------------------------------------------------------- #
def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return float(s[mid]) if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _stat_rows(rows, name: str, expr: str):
    """這一行的整批統計要看哪幾顆的值。

    排除：跑失敗的、沒判定的、值不是數字的，以及**補過值的** ——
    expr 用到的任何變數帶著 ``<變數>_missing == 1``（`feature_fill` 補的），
    或這一行自己的 ``<name>_missing == 1``（`Let.fill` 補的，F24 ⑤）。
    A1 的規矩：補進去的值不進中位數，不然「整批的中位數」有一半是同一個
    補進去的常數。
    """
    try:
        variables = sorted(parse_expression(str(expr)).variables)
    except Exception:              # noqa: BLE001 — 壞算式第一趟就逐顆失敗了
        variables = []
    out = []
    for r in rows:
        if not r.get("ok") or r.get("bin") is None:
            continue
        feats = r.get("features") or {}
        # ⚠ **有 ``_raw`` 就用它**（F4，2026-08-24）。這一支跑第二次的時候，
        # ``feats[name]`` 裝的已經是換算過的值 —— 拿它再算一次整批統計，
        # 得到的是「z 分數的 z 分數」。原始量測值一直在 ``<name>_raw``。
        v = feats.get("%s_raw" % name, feats.get(name))
        if not isinstance(v, (int, float)):
            continue
        if any(feats.get("%s_missing" % var) == 1
               for var in variables + [name]):
            continue
        out.append(float(v))
    return out


def redecide(recipe: Recipe, rows) -> int:
    """用**已經算好的 features** 重跑一次判定（不重跑影像），就地改寫 ``rows``。

    回傳重算成功的顆數。

    **判定邏輯只有一個家**（F3，2026-08-24）
    ----------------------------------------
    在這之前有兩份：這一支（`apply_lot_scaling` 裡的那一段）走
    :func:`engine._eval_score`，而 `store.rescore` 自己實作了一次 ——
    讀 ``recipe.score``、算 ``expr``、跟 ``threshold`` 比、分 below/above，
    **從來沒有看過 ``decide``**。F21–F25 把整個判定段搬進 `DecideSpec` 之後
    那一份就漂了：一份判定樹 recipe 走 rescore 會拿那個廢棄的 ``score`` 區塊
    算完，回報 ``n_errors: 0``，而每一顆都是 bin 0 —— 跑得完、有數字、
    而且是錯的。

    所以現在兩邊都叫這一支，而它叫的是引擎那一支
    （:func:`engine._eval_score` 自己會分流到 `_eval_decision`）。

    ``scale`` 的行為什麼不重算
    --------------------------
    標了「跟整批比」的 ``let`` 行，值是**整批收齊之後**才算得出來的
    （`apply_lot_scaling`），逐顆重算只會拿回換算前的那個數字。它們的值在
    ``features`` 裡已經是最終的，所以這裡把它們從 ``let`` 拿掉 ——
    沒換算的行照原順序重算，用到換算值時拿到的是新值（跟規則看到的一致）。
    """
    decide = getattr(recipe, "decide", None)
    if decide is not None:
        recipe = _replace(recipe, decide=_replace(
            decide, let=[x for x in decide.let
                         if not str(getattr(x, "scale", "") or "")]))
    redone = 0
    for r in rows:
        if not r.get("ok") or r.get("bin") is None:
            continue
        ctx = Context()
        ctx.features.update({k: v for k, v in (r.get("features") or {}).items()
                             if isinstance(v, (int, float))})
        try:
            score, b = _eval_score(recipe, ctx)
        except Exception as e:             # noqa: BLE001 — 鐵則 7：單顆失敗
            r["ok"] = False
            r["error"] = "[score] %s" % e
            r["score"], r["bin"] = None, None
            continue
        feats = dict(r.get("features") or {})
        feats.update({k: _safe_num(v) for k, v in ctx.features.items()})
        r["features"] = feats
        r["score"] = _safe_num(score)
        r["bin"] = int(b)
        redone += 1
    return redone


def apply_lot_scaling(recipe: Recipe, rows) -> int:
    """把 ``decide.let`` 裡標了「跟整批比」的行換算成整批尺度，並重算判定。

    F23 §8 的兩趟引擎：`run_batch`（逐顆，判定先算一版）→ 這裡回填 → 重算
    判定（**不重跑影像**，秒級）。`run_batch` 的兩條路徑都在回傳前呼叫它，
    所以 CLI、Studio 試跑、測試拿到的是同一份數字。

    * 沒有任何 ``scale`` 行 → **一個位元都不動**（嚴格附加；黃金值三份靠它）。
    * 原始值改名 ``<name>_raw`` 留著（F19：換算前後都要畫得出分布）。
    * 重算判定時**不重算換算過的行**（它們的值已經是最終的），其他行照原順序
      重算 —— 一行沒換算的 let 用到換算過的值時，拿到的是新值（跟規則看到的
      一致）。
    * 回傳重算判定的顆數。
    """
    decide = getattr(recipe, "decide", None)
    if decide is None:
        return 0
    scaled = [x for x in decide.let if str(getattr(x, "scale", "") or "")]
    rows = list(rows or [])
    if not scaled or not rows:
        return 0

    for item in scaled:
        name = str(item.name).strip()
        if not name:
            continue
        stat_vals = _stat_rows(rows, name, item.expr)
        if not stat_vals:
            # 整批一顆可用的值都沒有 —— 沒有統計就沒有換算，這一行原樣留著
            # （每一顆的原始值還在，CSV 看得出這件事）。
            continue
        med = _median(stat_vals)
        if item.scale == "z":
            mad = _median([abs(v - med) for v in stat_vals])
            spread = 1.4826 * mad          # 同 algo/enhance.py 的一致性因子
        n = len(stat_vals)
        raw_key = "%s_raw" % name
        for r in rows:
            feats = r.get("features") or {}
            # ⚠ **``_raw`` 是冪等的錨**（F4，2026-08-24）。這一支以前無條件
            # 覆寫它，所以跑第二次時寫進去的是「已經 z 化過的值」——
            # 真正的量測值就此消失，而 ``name`` 被換算了兩次。今天 `run_batch`
            # 的兩條路徑各只叫一次，但這是公開 API（`pipeline.__all__`），
            # 而 F3 把 rescore 接上判定引擎之後它會有第二個呼叫點。
            # 規矩：**已經有 ``_raw`` 就從它算起，而且不覆寫它。**
            v = feats.get(raw_key, feats.get(name))
            if not isinstance(v, (int, float)):
                continue
            v = float(v)
            feats.setdefault(raw_key, v)
            if item.scale == "z":
                feats[name] = ((v - med) / spread) if spread > 0 else 0.0
            else:                          # "percentile"（值域 0–100，midrank）
                less = sum(1 for s in stat_vals if s < v)
                equal = sum(1 for s in stat_vals if s == v)
                feats[name] = 100.0 * (less + 0.5 * equal) / n

    # ---- 重算判定（只有數字，沒有影像）—— 跟 rescore 同一支（F3）----
    return redecide(recipe, rows)


# --------------------------------------------------------------------------- #
# 跨顆那一層（F16）
# --------------------------------------------------------------------------- #
def run_batch_steps(recipe: Recipe, dataset: Any,
                    rows: Sequence[Dict[str, Any]],
                    kind: Optional[str] = None,
                    registry: Optional[Dict[str, Any]] = None) -> BatchContext:
    """整批跑完之後，把**整批一次**（``scale == SCALE_LOT``）的卡各跑一次。

    **這一支跟 :func:`run_batch` 是分開的兩件事，而那是刻意的。**
    使用者定調（2026-08-20）：「**試跑不寫，只有整批才寫**」—— Studio 的
    Run trial 是調參數的迴圈（拖門檻、改參數跟著跑），每拖一下就覆寫一次 KLARF
    是不可逆的災難。把「寫出去」做成 ``run_batch`` 的一個旗標的話，那個旗標
    遲早會有人忘記關；做成**另一支要自己叫的函式**，試跑那條路就是根本沒叫它。

    所以規則是一句話：**要寫出東西的那條路自己叫這一支，試跑不叫。**
    目前叫它的只有 CLI（`python -m d4t run`）—— Studio 只有試跑那條路，
    它的輸出目前仍然走 Export 精靈（見 docs/ROADMAP.md）。

    一張卡出錯**不影響其他卡**（鐵則 7 的跨顆版）：訊息記進 ``bctx.errors``，
    其餘照跑，而整批的結果本來就已經在 ``rows`` 裡了。
    """
    from .context import BatchContext

    reg = REGISTRY if registry is None else registry
    k = str(kind if kind is not None else getattr(dataset, "kind", "") or "")
    bctx = BatchContext(rows=list(rows), dataset=dataset, recipe=recipe, kind=k)
    # 分流（F23）：route_by 存在時 route 鍵不是 kind，而是 map/default 指到的
    # 那幾條 —— 每一條上的跨顆卡都要跑到（同一個節點出現在兩條 route 上時
    # 只跑一次：Output 卡寫檔是不可逆的，寫兩次不是「再保險一次」是覆寫）。
    rb = getattr(recipe, "route_by", None)
    if rb is None:
        route_keys = [k]
    else:
        route_keys = sorted({str(v) for v in rb.map.values()}
                            | ({str(rb.default).strip()}
                               if str(rb.default or "").strip() else set()))
    try:
        orders = [execution_order(recipe, rk) for rk in route_keys]
    except Exception as e:
        # route 有問題的話 `run_defect` 已經一顆一顆講過了，所以這裡不再報
        # 一次 error（同一件事兩個訊息，使用者會以為是兩個問題）。但也**不能
        # 完全不出聲**：`rows` 是空的時候（整批一顆都沒跑）就沒有人講過，
        # 而症狀會是「按了跑，什麼檔案都沒出現」。
        bctx.warn("No output was written: this recipe has no route for '%s' "
                  "(%s)." % (k, e))
        return bctx
    seen: set = set()
    for order in orders:
        for nid in order:
            if nid in seen:
                continue
            seen.add(nid)
            node = recipe.nodes.get(nid)
            if node is None or not node.enabled:
                continue
            step_cls = reg.get(node.step)
            if step_cls is None or step_cls.scale != SCALE_LOT:
                continue
            try:
                params = step_cls.validate_params(node.params)
                step_cls().run_batch(bctx, params)
            except Exception as e:          # noqa: BLE001 — 鐵則 7 的跨顆版
                bctx.errors[nid] = str(e)
    return bctx
