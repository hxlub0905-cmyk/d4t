# ADEPT pipeline engine — authored 2026-07-28 (M1; M2 加入 checkpoint 快取).
"""單顆執行引擎：對一顆 defect 依 recipe 跑完整 pipeline。

M1：單進程、循序。M2：內部重構成可重用片段（種 Context → 跑節點區間 →
算分），讓 :func:`run_defect_cached` 能從「影像段結束」的 checkpoint 續跑
（影像段快取見 :mod:`.cache`，平行批次見 :mod:`.batch`）。

鐵則：**單顆爆 = 該顆 FAIL，不殺整批** —— :func:`run_defect` 與
:func:`run_defect_cached` 永不 raise，所有錯誤（StepError / ContextError /
RecipeError / 快取讀寫失敗 / 其他）都收進 :class:`DefectResult` 或
自動退回全程重算。
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from .context import Context
from .recipe import Recipe, RecipeError, execution_order
from .step import CATEGORY_ADC, CATEGORY_IMAGE, REGISTRY, Step, StepError

__all__ = ["StepTrace", "DefectResult", "run_defect", "run_defect_cached",
           "run_dataset", "image_segment_signature", "result_to_json_dict"]


@dataclass
class StepTrace:
    """一個節點的執行紀錄（供 Studio 單顆預覽與 debug）。"""
    node_id: str
    step_key: str
    ok: bool
    ms: float
    error: Optional[str]
    features_added: Dict[str, float]   # 該步驟新增或改值的特徵
    images_after: List[str]            # 該步驟結束後的影像流 key（排序）


@dataclass
class DefectResult:
    """一顆 defect 的完整執行結果。"""
    defect_id: str
    ok: bool
    error: Optional[str]
    features: Dict[str, float]
    score: Optional[float]
    bin: Optional[int]
    traces: List[StepTrace]
    context: Optional[Context]         # keep_context=True 才附上（不進 JSON）


# ---------------------------------------------------------------------------
# 可重用片段（M2 重構；run_defect 的行為與 M1 完全相同）
# ---------------------------------------------------------------------------
def _seed_context(item: Any, kind: str, defect_id: str) -> Context:
    """建立新 Context 並種入引擎慣例的 meta key（Load 卡讀這些）。"""
    ctx = Context()
    ctx.meta["_defect_item"] = item
    ctx.meta["_dataset_kind"] = kind
    ctx.meta["_defect_id"] = defect_id
    ctx.meta["nm_per_px"] = getattr(item, "nm_per_px", None)
    return ctx


def _finish(defect_id: str, ctx: Context, traces: List[StepTrace],
            keep_context: bool, ok: bool, error: Optional[str],
            score: Optional[float] = None,
            bin_: Optional[int] = None) -> DefectResult:
    return DefectResult(
        defect_id=defect_id, ok=ok, error=error,
        features=dict(ctx.features), score=score, bin=bin_,
        traces=traces, context=(ctx if keep_context else None))


def _run_nodes(recipe: Recipe, order: List[str], start: int, stop: int,
               ctx: Context, traces: List[StepTrace],
               registry: Dict[str, Type[Step]],
               upto_node: Optional[str],
               kind: str = "",
               verdicts_out: Optional[List[Any]] = None,
               inbox: Optional[Dict[Any, Any]] = None) -> Tuple[Context, Optional[str]]:
    """執行 ``order[start:stop]`` 的節點；trace 逐一 append。

    **F9 Phase 2 起這裡只是一層薄殼。** 真正的執行在
    :func:`.graph.run_graph` —— 資料沿著線走，不再是所有卡共用一個全域
    ``Context``。這一層負責的是把圖執行器的輸出翻成既有的
    ``(ctx, error)`` 與 ``StepTrace``，讓 ``run_defect`` 的對外契約一個字
    都不用改（Studio、批次、快取、報表全都吃這個形狀）。

    ``order`` 仍然由呼叫端算好傳進來，因為快取要用「第幾格」切段。
    """
    from .graph import Packet, compile_recipe, run_graph

    try:
        graph = compile_recipe(recipe, kind, registry=registry)
    except Exception as e:                     # noqa: BLE001 — 收成結果不外洩
        return ctx, f"[recipe] {e}"

    # 呼叫端給的 order 含停用節點，compile 過的沒有 —— 用節點 id 對齊切點。
    lo = _segment_index(graph.order, order, start)
    hi = _segment_index(graph.order, order, stop)

    outbox, runs, err, last = run_graph(
        graph, Packet(ctx), registry=registry, start=lo, stop=hi,
        upto_node=upto_node, track_changes=ctx.track_changes,
        inbox=inbox)

    for r in runs:
        traces.append(StepTrace(
            node_id=r.node_id, step_key=r.step_key, ok=r.ok, ms=r.ms,
            error=r.error, features_added=r.features_added,
            images_after=r.images_after))
    out = last.ctx if last is not None else ctx
    if verdicts_out is not None:
        got = _collect_verdicts(graph, outbox, registry)
        verdicts_out.append(got)
    return out, err


def _segment_index(compiled: List[str], order: List[str], idx: int) -> int:
    """把「呼叫端那份 order 的第 idx 格」換算成編譯後那份 order 的位置。

    兩份清單的差別只有停用節點（編譯時就拿掉了），所以用**節點 id** 對齊：
    切點之前有幾個節點還活著，就是新的切點。
    """
    alive = set(compiled)
    return sum(1 for nid in order[:idx] if nid in alive)


#: 判定卡沒有任何一張跑到時，記在 warnings 裡的那句話。
NO_VERDICT_NOTE = (
    "no decision was made for this defect: the branch it took has no Decide "
    "card on it. The score is left empty on purpose - a 0 here would sort and "
    "report like a real answer.")

#: 整份 recipe 一張判定卡都沒有時，記在 warnings 裡的那句話。
#: 跟上面那句分開，因為要修的地方不一樣：這一句是「還沒加」，
#: 上面那句是「加了但這顆走的分支上沒有」。
NO_DECIDE_CARD_NOTE = (
    "this recipe has no Decide card, so it measures features but never turns "
    "them into a score. Every defect comes out without a score or a bin; add a "
    "Decide card at the end of the pipeline if you want a verdict.")


def _collect_verdicts(graph: Any, outbox: Dict[Any, Any],
                      registry: Dict[str, Type[Step]]
                      ) -> Optional[List[Dict[str, Any]]]:
    """圖上的判定卡各給了什麼結論。

    從 **outbox**（每個節點自己吐出來的那一包）收，不是從最後那一包收 ——
    有分岔的時候判定卡的那一包不一定是執行順序上的最後一個，讀最後那包會
    拿到別條分支的結論。

    回 ``None`` = 這份 recipe **一張判定卡都沒有** → 這顆沒有結論。
    回 ``[]``   = 有判定卡但**一張都沒跑到**（分流走到一條沒有判定的分支）
    —— 那是「沒有結論」，不是 0 分。
    """
    from ..steps.adc import VERDICT_KEY

    out: List[Dict[str, Any]] = []
    found_any = False
    for nid in graph.order:
        node = graph.nodes.get(nid)
        step_cls = registry.get(node.step) if node is not None else None
        if getattr(step_cls, "category", "") != CATEGORY_ADC:
            continue
        found_any = True
        for port in getattr(step_cls, "outputs", ()) or ():
            pk = outbox.get((nid, port))
            if pk is None:
                continue
            v = dict(pk.ctx.meta.get(VERDICT_KEY) or {})
            if v:
                v["node"] = nid
                out.append(v)
    return out if found_any else None


def run_defect(recipe: Recipe, item: Any, kind: str, *,
               keep_context: bool = False,
               upto_node: Optional[str] = None,
               track_changes: bool = False,
               registry: Optional[Dict[str, Type[Step]]] = None) -> DefectResult:
    """對單顆 defect 執行 ``kind`` 這條 route；**永不 raise**。

    - Context.meta 先種入 ``_defect_item`` / ``_dataset_kind`` / ``_defect_id`` /
      ``nm_per_px``（Load 卡讀這些 key）。
    - 停用（enabled=False）節點跳過。
    - ``track_changes``：把「每一次覆寫既有影像流的前後樣貌」記進
      ``ctx.meta['stream_change']``（F7-17 的 Enhance 儀表要的）。**預設關**——
      批次跑一萬顆時那份資料沒有人看，不值得每次 set_image 都算兩個直方圖。
    - ``upto_node``：跑到該節點**之後**就停（Studio 點卡看中間輸出用）；
      強制 keep_context=True，score/bin 不算（None）；若該節點被停用則
      停在它前面、不執行它；不在 route 上 → ok=False（不 raise）。
    - 步驟全過後：判定由圖上的 ``adc`` 卡給（見 :func:`_judge`）——
      沒有任何一張跑到就**沒有結論**（score/bin 是 None，不是 0）。
    """
    if registry is None:
        registry = REGISTRY
    if upto_node is not None:
        keep_context = True  # 中間輸出就是要看 context

    defect_id = str(getattr(item, "defect_id", ""))
    ctx = _seed_context(item, kind, defect_id)
    ctx.track_changes = bool(track_changes)
    traces: List[StepTrace] = []

    try:
        order = execution_order(recipe, kind, registry)
    except RecipeError as e:
        return _finish(defect_id, ctx, traces, keep_context, False, str(e))

    if upto_node is not None and upto_node not in order:
        return _finish(
            defect_id, ctx, traces, keep_context, False,
            f"upto_node '{upto_node}' is not in the execution order {order} "
            f"of route '{kind}'")

    # ``upto_node`` 要停在**那一格**，而不是「跑完再說」。用索引切段而不是只靠
    # ``run_graph`` 認節點 id：目標卡被**停用**的時候編譯過的圖裡根本沒有它，
    # 認不到就會一路跑到底 —— 以前看不出來，因為判定還不是卡片，route 的尾巴
    # 後面沒有東西；判定變成卡片之後，它會照跑然後回一個莫名其妙的錯。
    stop = len(order)
    if upto_node is not None:
        stop = order.index(upto_node) + 1

    verdicts_box: List[Any] = []
    ctx, err = _run_nodes(recipe, order, 0, stop, ctx, traces,
                          registry, upto_node, kind=kind,
                          verdicts_out=verdicts_box)
    if err is not None:
        return _finish(defect_id, ctx, traces, keep_context, False, err)

    if upto_node is not None:
        return _finish(defect_id, ctx, traces, keep_context, True, None)

    return _judge(recipe, ctx, traces, keep_context, defect_id,
                  verdicts_box[0] if verdicts_box else None)


def _judge(recipe: Recipe, ctx: Context, traces: List[StepTrace],
           keep_context: bool, defect_id: str,
           verdicts: Optional[List[Dict[str, Any]]]) -> DefectResult:
    """把判定收成結果。四種情況，四種不同的下場。

    * ``verdicts is None`` —— 整份 recipe **一張判定卡都沒有**。
    * ``verdicts == []`` —— 有判定卡，但這顆走的分支上一張都沒跑到。
    * 剛好一張判定卡跑到 → 就用它。
    * **兩張以上跑到** → 這是 recipe 接錯了（兩條判定同時生效），
      當成失敗講清楚，不要偷偷挑一個。

    前兩種都是「**沒有結論**」：score/bin 留 None 並在 warnings 裡講出來 ——
    給 0 分是最糟的處理（0 會排序、會進報表、看起來像「很乾淨」）。
    兩句話分開是因為要修的地方不一樣：一個是「還沒加判定卡」，
    另一個是「加了，但這條分支上沒有」。
    """
    if len(verdicts or ()) == 1:
        v = verdicts[0]
        return _finish(defect_id, ctx, traces, keep_context, True, None,
                       score=float(v["score"]), bin_=int(v["bin"]))

    if not verdicts:
        ctx.warn(NO_DECIDE_CARD_NOTE if verdicts is None else NO_VERDICT_NOTE)
        return _finish(defect_id, ctx, traces, keep_context, True, None)

    who = ", ".join(str(v.get("node", "?")) for v in verdicts)
    return _finish(defect_id, ctx, traces, keep_context, False,
                   "[adc] %d Decide cards both made a decision for this defect "
                   "(%s). Exactly one branch should end in a Decide card - "
                   "check the wiring." % (len(verdicts), who))


# ---------------------------------------------------------------------------
# M2：影像段 checkpoint（signature）與快取續跑
# ---------------------------------------------------------------------------
def image_segment_signature(recipe: Recipe, kind: str,
                            registry: Optional[Dict[str, Type[Step]]] = None
                            ) -> Tuple[str, int]:
    """算出 ``kind`` route 的影像段簽章與 checkpoint 索引。

    checkpoint 索引 = 執行順序中「最後一個 enabled 且 category==image 的節點」
    的下一個位置；沒有影像段節點 → 0（快取沒意義）。
    簽章 = checkpoint 前所有 enabled 節點的
    ``[(node_id, step_key, sorted-param-items), ...]`` + kind 的穩定 JSON 字串
    （params 先過 ``validate_params`` 正規化：帶預設值、coerce 型別，
    讓「寫不寫預設值」不影響簽章）。deterministic。

    注意：未知 route / 循環會 raise :class:`RecipeError`
    （:func:`run_defect_cached` 會攔截並退回 :func:`run_defect`）。
    """
    if registry is None:
        registry = REGISTRY
    order = execution_order(recipe, kind, registry)

    ckpt = 0
    for i, nid in enumerate(order):
        node = recipe.nodes.get(nid)
        if node is None or not node.enabled:
            continue
        step_cls = registry.get(node.step)
        if step_cls is not None and step_cls.category == CATEGORY_IMAGE:
            ckpt = i + 1

    sig_nodes: List[List[Any]] = []
    for nid in order[:ckpt]:
        node = recipe.nodes.get(nid)
        if node is None or not node.enabled:
            continue  # 停用節點不影響執行，也不進簽章
        params: Dict[str, Any] = dict(node.params)
        step_cls = registry.get(node.step)
        if step_cls is not None:
            try:
                params = step_cls.validate_params(node.params)
            except Exception:
                params = dict(node.params)  # 壞參數：用原樣（執行時會爆，簽章仍穩定）
        items = sorted((str(k), v) for k, v in params.items())
        sig_nodes.append([nid, node.step, [list(kv) for kv in items]])

    sig = json.dumps({"kind": kind, "nodes": sig_nodes},
                     ensure_ascii=False, sort_keys=True, default=str,
                     separators=(",", ":"))
    return sig, ckpt


def _json_safe(v: Any) -> bool:
    try:
        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False


def _meta_snapshot(meta: Dict[str, Any]) -> Dict[str, Any]:
    """meta 的可快取子集：去掉私有 key（``_`` 開頭，引擎每次重新種入）、
    去掉 JSON 序列化不了的值（例如 ndarray、物件）。
    涵蓋 warnings / notes / nm_per_px / align_dx / align_dy /
    feature_overwrites … 等後段卡片可能讀到的一般值。"""
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if str(k).startswith("_"):
            continue
        if _json_safe(v):
            out[k] = v
    return out


def _roi_snapshot(ctx: Context) -> List[Any]:
    """具名 ROI → ``[(name, (nx, ny, nw, nh)), ...]``（可 JSON 化）。"""
    out: List[Any] = []
    for roi in (ctx.rois.rois if ctx.rois is not None else ()):
        try:
            rect = tuple(float(v) for v in roi.norm_rect)
        except Exception:              # noqa: BLE001 — 快取是盡力而為
            continue
        out.append((str(roi.label), rect))
    return out


def _restore_context(item: Any, kind: str, defect_id: str,
                     snap: Dict[str, Any]) -> Context:
    """由快取快照重建 Context。

    **Context 的每一個欄位都要回來**，不只 images/features/meta。checkpoint 是
    執行順序上的位置，不是「所有影像段的卡」，所以夾在中間的 Region 卡
    （algo）會落在快取段裡 —— 漏掉 ``rois`` 的話會變成「第一次跑對、第二次跑
    錯」。見 :mod:`.cache` 的模組說明。
    """
    ctx = _seed_context(item, kind, defect_id)
    for name, arr in dict(snap.get("images") or {}).items():
        ctx.images[str(name)] = arr
    for name, val in dict(snap.get("features") or {}).items():
        ctx.features[str(name)] = float(val)
    for k, v in dict(snap.get("meta") or {}).items():
        ctx.meta[str(k)] = v  # 快照不含 ``_`` 開頭 key，不會蓋掉剛種的
    # **一個名字可能有好幾個框**（F8 的交會定位）。逐一 ``set_roi`` 是錯的 ——
    # 它會先刪掉同名的，所以 17 個框還原完只剩最後一個：冷跑量 17 塊、熱跑量
    # 1 塊，而兩邊都跑得完、都有數字。這正是 F7-9 那條「第一次跑對、第二次跑
    # 錯」，只是這次不是整組不見而是**只剩一個**，更難發現。
    grouped: Dict[str, List[Any]] = {}
    for name, rect in (snap.get("rois") or []):
        grouped.setdefault(str(name), []).append(rect)
    for name, rects in grouped.items():
        ctx.set_roi_boxes(name, rects)
    labels = snap.get("labels")
    if labels is not None:
        ctx.labels = labels
    return ctx


def run_defect_cached(recipe: Recipe, item: Any, kind: str,
                      cache: Any, dataset_token: str, *,
                      keep_context: bool = False,
                      registry: Optional[Dict[str, Type[Step]]] = None
                      ) -> DefectResult:
    """帶影像段快取的單顆執行；**永不 raise**，結果與 :func:`run_defect`
    位元級一致（features / score / bin）。

    - 影像段（到 checkpoint 為止）命中快取 → 直接重建 Context 續跑算法段；
      未命中 → 跑影像段、寫入快取（:class:`.cache.StageCache`）、續跑。
    - checkpoint == 0（沒有影像段節點）或快取讀/寫失敗 → 退回全程重算，
      不會 crash。
    - 快取命中時 ``traces`` 只含 checkpoint 之後的節點（影像段沒真的跑）。
    """
    if registry is None:
        registry = REGISTRY

    try:
        sig, ckpt = image_segment_signature(recipe, kind, registry=registry)
    except Exception:
        return run_defect(recipe, item, kind,
                          keep_context=keep_context, registry=registry)
    if cache is None or ckpt <= 0:
        return run_defect(recipe, item, kind,
                          keep_context=keep_context, registry=registry)

    defect_id = str(getattr(item, "defect_id", ""))
    key: Optional[str] = None
    snap: Optional[Dict[str, Any]] = None
    try:
        key = cache.make_key(str(dataset_token), defect_id, sig)
        snap = cache.get(key)
    except Exception:
        snap = None  # 快取層出包 → 當作 miss

    order = execution_order(recipe, kind, registry)  # signature 已驗證過，不會再 raise
    traces: List[StepTrace] = []
    ctx: Optional[Context] = None

    if snap is not None:
        try:
            ctx = _restore_context(item, kind, defect_id, snap)
        except Exception:
            ctx = None  # 快照壞掉 → 退回重算影像段

    if ctx is None:
        # miss：跑影像段（order[:ckpt]），成功才寫快取
        ctx = _seed_context(item, kind, defect_id)
        ctx, err = _run_nodes(recipe, order, 0, ckpt, ctx, traces,
                              registry, None, kind=kind)
        if err is not None:
            return _finish(defect_id, ctx, traces, keep_context, False, err)
        if key is not None:
            try:
                cache.put(key, dict(ctx.images), dict(ctx.features),
                          _meta_snapshot(ctx.meta),
                          rois=_roi_snapshot(ctx), labels=ctx.labels)
            except Exception:
                pass  # 快取寫入失敗 → 不影響本次結果

    # 續跑算法段 + ADC 判定
    verdicts_box: List[Any] = []
    ctx, err = _run_nodes(recipe, order, ckpt, len(order), ctx, traces,
                          registry, None, kind=kind, verdicts_out=verdicts_box)
    if err is not None:
        return _finish(defect_id, ctx, traces, keep_context, False, err)
    return _judge(recipe, ctx, traces, keep_context, defect_id,
                  verdicts_box[0] if verdicts_box else None)


def run_dataset(recipe: Recipe, dataset: Any, *,
                progress: Optional[Callable[[int, int, DefectResult], Any]] = None,
                limit: Optional[int] = None) -> List[DefectResult]:
    """循序跑整個 dataset（M1 單進程；平行批次見 :func:`.batch.run_batch`）。

    - ``limit``：只跑前 N 顆（調參試跑用）。
    - ``progress(i, n, result)``：每顆跑完呼叫一次（i 為 0 起算的索引）。
    - 單顆失敗不影響其他顆（run_defect 永不 raise）。
    """
    items = list(dataset.items) if limit is None else list(dataset.items)[:limit]
    n = len(items)
    results: List[DefectResult] = []
    for i, item in enumerate(items):
        r = run_defect(recipe, item, dataset.kind)
        results.append(r)
        if progress is not None:
            progress(i, n, r)
    return results


# ---------------------------------------------------------------------------
# JSON 匯出（CLI `adept run` 輸出 features JSON 用）
# ---------------------------------------------------------------------------
def _safe_num(v: Any) -> Optional[float]:
    """float 化；nan/inf/ndarray/不可轉 → None（JSON 安全）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def result_to_json_dict(r: DefectResult) -> Dict[str, Any]:
    """DefectResult → 可直接 ``json.dumps`` 的 dict。

    不含 ndarray、不含 context；nan/inf → None；ms 取 3 位小數。
    """
    return {
        "defect_id": r.defect_id,
        "ok": bool(r.ok),
        "error": r.error,
        "features": {k: _safe_num(v) for k, v in r.features.items()},
        "score": _safe_num(r.score),
        "bin": None if r.bin is None else int(r.bin),
        "traces": [
            {
                "node_id": t.node_id,
                "step_key": t.step_key,
                "ok": bool(t.ok),
                "ms": round(float(t.ms), 3),
                "error": t.error,
                "features_added": {k: _safe_num(v)
                                   for k, v in t.features_added.items()},
                "images_after": [str(x) for x in t.images_after],
            }
            for t in r.traces
        ],
    }
