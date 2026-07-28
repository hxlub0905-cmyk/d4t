# FlexADC pipeline engine — authored 2026-07-28 (M1).
"""單顆執行引擎：對一顆 defect 依 recipe 跑完整 pipeline。

M1 範圍：單進程、循序（批次 ProcessPool 與快取是 M2）。
鐵則：**單顆爆 = 該顆 FAIL，不殺整批** —— :func:`run_defect` 永不 raise，
所有錯誤（StepError / ContextError / RecipeError / 其他）都收進
:class:`DefectResult`。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from .context import Context
from .expression import parse_expression
from .recipe import Recipe, RecipeError, execution_order
from .step import REGISTRY, Step, StepError

__all__ = ["StepTrace", "DefectResult", "run_defect", "run_dataset",
           "result_to_json_dict"]


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


def run_defect(recipe: Recipe, item: Any, kind: str, *,
               keep_context: bool = False,
               upto_node: Optional[str] = None,
               registry: Optional[Dict[str, Type[Step]]] = None) -> DefectResult:
    """對單顆 defect 執行 ``kind`` 這條 route；**永不 raise**。

    - Context.meta 先種入 ``_defect_item`` / ``_dataset_kind`` / ``_defect_id`` /
      ``nm_per_px``（Load 卡讀這些 key）。
    - 停用（enabled=False）節點跳過。
    - ``upto_node``：跑到該節點**之後**就停（Studio 點卡看中間輸出用）；
      強制 keep_context=True，score/bin 不算（None）；若該節點被停用則
      停在它前面、不執行它；不在 route 上 → ok=False（不 raise）。
    - 步驟全過後：score = expr(features)、features["score"] = score、
      bin = bins["below"]（score < threshold）否則 bins["above"]。
    """
    if registry is None:
        registry = REGISTRY
    if upto_node is not None:
        keep_context = True  # 中間輸出就是要看 context

    defect_id = str(getattr(item, "defect_id", ""))
    ctx = Context()
    ctx.meta["_defect_item"] = item
    ctx.meta["_dataset_kind"] = kind
    ctx.meta["_defect_id"] = defect_id
    ctx.meta["nm_per_px"] = getattr(item, "nm_per_px", None)
    traces: List[StepTrace] = []

    def _result(ok: bool, error: Optional[str],
                score: Optional[float] = None,
                bin_: Optional[int] = None) -> DefectResult:
        return DefectResult(
            defect_id=defect_id, ok=ok, error=error,
            features=dict(ctx.features), score=score, bin=bin_,
            traces=traces, context=(ctx if keep_context else None))

    try:
        order = execution_order(recipe, kind)
    except RecipeError as e:
        return _result(False, str(e))

    if upto_node is not None and upto_node not in order:
        return _result(
            False,
            f"upto_node '{upto_node}' 不在 route '{kind}' 的執行順序 {order} 中")

    for nid in order:
        node = recipe.nodes.get(nid)
        if node is None:
            traces.append(StepTrace(
                node_id=nid, step_key="?", ok=False, ms=0.0,
                error=f"節點 '{nid}' 不在 recipe.nodes 中", features_added={},
                images_after=sorted(ctx.images)))
            return _result(False, f"[{nid}] 節點 '{nid}' 不在 recipe.nodes 中")
        if not node.enabled:
            if nid == upto_node:
                break  # 目標節點被停用：停在它這裡、不執行它
            continue

        t0 = time.perf_counter()
        feats_before = dict(ctx.features)
        try:
            step_cls = registry.get(node.step)
            if step_cls is None:
                raise StepError(
                    node.step, f"未知的 step '{node.step}'；已註冊：{sorted(registry)}")
            params = step_cls.validate_params(node.params)
            ret = step_cls().run(ctx, params)
            if isinstance(ret, Context):
                ctx = ret
        except Exception as e:  # StepError / ContextError / ParamError / 其他
            ms = (time.perf_counter() - t0) * 1000.0
            traces.append(StepTrace(
                node_id=nid, step_key=node.step, ok=False, ms=ms,
                error=str(e), features_added={},
                images_after=sorted(ctx.images)))
            return _result(False, f"[{nid}] {e}")

        ms = (time.perf_counter() - t0) * 1000.0
        added = {
            k: v for k, v in ctx.features.items()
            if k not in feats_before or feats_before[k] != v
        }
        traces.append(StepTrace(
            node_id=nid, step_key=node.step, ok=True, ms=ms,
            error=None, features_added=added,
            images_after=sorted(ctx.images)))
        if nid == upto_node:
            break

    if upto_node is not None:
        return _result(True, None)  # 中間輸出模式：不算 score / bin

    # ---- ADC 判定：score → bin ----
    try:
        expr = parse_expression(recipe.score.expr)
        score = expr.eval(ctx.features)
        ctx.features["score"] = score
        if score < float(recipe.score.threshold):
            b = int(recipe.score.bins["below"])
        else:
            b = int(recipe.score.bins["above"])
    except Exception as e:
        return _result(False, f"[score] {e}")
    return _result(True, None, score=score, bin_=b)


def run_dataset(recipe: Recipe, dataset: Any, *,
                progress: Optional[Callable[[int, int, DefectResult], Any]] = None,
                limit: Optional[int] = None) -> List[DefectResult]:
    """循序跑整個 dataset（M1 單進程；M2 換 ProcessPool，介面不變）。

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
# JSON 匯出（CLI `flexadc run` 輸出 features JSON 用）
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
