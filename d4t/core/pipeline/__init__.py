# d4t pipeline engine — authored 2026-07-28 (M1).
"""d4t.core.pipeline — Context / Step / Recipe / 表達式 / 執行引擎。

單一匯入點：steps、UI、CLI 一律 ``from d4t.core.pipeline import ...``。
"""
from __future__ import annotations

from .context import Context, ContextError, BatchContext
from .step import (
    CATEGORY_ADC,
    CATEGORY_BATCH,
    SCALE_DEFECT,
    SCALE_LOT,
    CATEGORY_ALGO,
    CATEGORY_IMAGE,
    ParamError,
    ParamSpec,
    REGISTRY,
    Step,
    StepError,
    get_step,
    list_steps,
    register_step,
)
from .expression import Expression, ExpressionError, parse_expression
from .recipe import (
    Issue,
    Edge,
    Recipe,
    RecipeError,
    RecipeNode,
    RouteBy,
    ScoreSpec,
    execution_order,
    resolve_route,
    route_miss_message,
    validate,
)
from .engine import (
    DefectResult,
    StepTrace,
    image_segment_signature,
    result_to_json_dict,
    run_dataset,
    run_defect,
    run_defect_cached,
)
from .cache import StageCache
from .batch import apply_lot_scaling, redecide, run_batch, run_batch_steps

__all__ = [
    # context
    "Context", "ContextError", "BatchContext",
    # step
    "Step", "ParamSpec", "ParamError", "StepError",
    "register_step", "get_step", "list_steps", "REGISTRY",
    "CATEGORY_IMAGE", "CATEGORY_ALGO", "CATEGORY_ADC", "CATEGORY_BATCH",
    "SCALE_DEFECT", "SCALE_LOT",
    # recipe
    "Edge", "Recipe", "RecipeNode", "ScoreSpec", "Issue",
    "validate", "execution_order", "RecipeError",
    # 分流（F23）
    "RouteBy", "resolve_route", "route_miss_message",
    # expression
    "parse_expression", "Expression", "ExpressionError",
    # engine
    "run_defect", "run_dataset", "DefectResult", "StepTrace",
    "result_to_json_dict",
    # M2：checkpoint 快取與平行批次
    "run_defect_cached", "image_segment_signature", "StageCache", "run_batch",
    "run_batch_steps",
    # 「跟整批比」的兩趟判定（F23 期3）
    "apply_lot_scaling",
    "redecide",
]
