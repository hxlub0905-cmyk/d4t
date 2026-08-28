# d4t core — 這一顆為什麼判成這樣（PR-3，2026-08-27）。
"""**把一顆 defect 的判定重放一遍**：帶實值的算式、走過的路徑、缺了什麼。

「這顆為什麼判 NG」以前要人腦重放：打開 recipe、找到樹、逐格查 CSV。這一份
是那個過程的純函式版 —— UI 的回溯面板（`ui/why_panel.py`）只畫它的輸出。

三條立身規矩：

* **不重算任何值。** 面板上每個數字要嘛是 features 裡的葉值替換
  （`valued_text`）、要嘛是引擎自己寫進 features 的（let 值、score）。
  表達式的 SAFE 語意（/0→0、log/sqrt 界外→0、**只在頂層** nan→0，見
  `expression.py`）因此不可能跟引擎不一致 —— 自己逐節點重算的那份會。
* **有 `scale` 的 let 不重放。** 整批換算是兩趟的（`batch.apply_lot_scaling`
  → `redecide`，而 redecide 重評前把有 scale 的 let **拿掉**，
  batch.py:414-418 —— 這裡鏡射那條規則，不 import batch：它會拖進
  multiprocessing 與 ingest）。features 裡的值就是樹真的比過的那一份
  （換算後），原始值在 ``<name>_raw``。
* **缺值明白標「沒人產出」**，不是留白 —— `answer` 缺值答「否」照走
  （F30 的規矩），但走過哪裡、缺了什麼要講得出來。

住新模組而不是 `verdict_features.py`：那一份的契約是「顯示層 metadata、
不碰數字」，這一份逐顆碰數字 —— 混在一起那句話就不成立了。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import decide_tree
from .expression import ExpressionError, parse_expression
from .recipe import Recipe

__all__ = ["LetTrace", "StepTraceRow", "Trace", "valued_text",
           "verdict_trace"]


def _collect_var_spans(node: Any, out: List[Tuple[str, int]]) -> None:
    """AST 裡每個 ``("var", name, pos)``（照 `expression._collect_vars` 的形）。"""
    tag = node[0]
    if tag == "var":
        out.append((str(node[1]), int(node[2])))
    elif tag in ("neg", "not"):
        _collect_var_spans(node[1], out)
    elif tag in ("bool", "cmp", "bin"):
        _collect_var_spans(node[2], out)
        _collect_var_spans(node[3], out)
    elif tag == "call":
        for a in node[2]:
            _collect_var_spans(a, out)


def valued_text(expr_text: str, feats: Mapping[str, Any],
                missing_mark: str = "?") -> str:
    """算式原文，每個變數以**實值**替換：``glv_mean + 2*cd_n`` →
    ``42.3 + 2*5``。缺的變數換成 ``missing_mark``。

    用 var 節點的**字元位置**由後往前 splice —— 位置定位對「一個變數名是另一
    個的子字串」免疫（`a` 與 `abs_a` 各換各的）。算式壞掉就原樣回去
    （validate 已經報過，這裡沒有第二句話好講）。
    """
    text = str(expr_text or "")
    try:
        expr = parse_expression(text)
    except ExpressionError:
        return text
    spans: List[Tuple[str, int]] = []
    _collect_var_spans(expr._ast, spans)
    for name, pos in sorted(spans, key=lambda x: x[1], reverse=True):
        v = feats.get(name)
        shown = ("%.4g" % float(v)) if isinstance(v, (int, float)) \
            else str(missing_mark)
        text = text[:pos] + shown + text[pos + len(name):]
    return text


@dataclass(frozen=True)
class LetTrace:
    """一行 working number 的重放。"""
    name: str
    expr: str
    valued: str                      #: expr 帶實值（換算 let 顯示的是換算前公式）
    value: Optional[float]           #: features 裡的值（**不重算**）
    filled: bool = False             #: 這一顆真的用了 fill（`_missing == 1`）
    fill: str = ""                   #: recipe 上那格的字（"" = 沒有）
    scaled: bool = False             #: 有 scale：值是整批換算後的
    raw: Optional[float] = None      #: ``<name>_raw``（scaled 才有）
    missing_vars: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StepTraceRow:
    """樹上的一步（或 rules 的一條）的重放。"""
    when: str
    valued: str
    answer: str                      #: "yes" | "no"
    missing: Tuple[str, ...] = ()    #: 這一題問不出來的名字（答案因此是 no）


@dataclass(frozen=True)
class Trace:
    mode: str                        #: "tree" | "rules" | "score" | "none"
    lets: Tuple[LetTrace, ...] = ()
    steps: Tuple[StepTraceRow, ...] = ()
    path: str = ""                   #: "yn…"（rules 也走等價的鏈狀樹）
    leaf_bin: Optional[int] = None
    leaf_label: str = ""
    rule_index: int = -1             #: rules 模式：第幾條對上（-1 = otherwise）
    score_expr: str = ""
    score_valued: str = ""
    score: Optional[float] = None    #: features["score"]（不重算）
    threshold: Optional[float] = None
    bins: Optional[Dict[str, int]] = None
    missing: Tuple[str, ...] = ()    #: 所有「沒人產出」的名字（sorted、去重）
    features: Dict[str, float] = field(default_factory=dict)


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) \
        and not isinstance(v, bool) else None


def verdict_trace(recipe: Recipe, route: str,
                  features: Mapping[str, Any]) -> Trace:
    """重放一顆 defect 的判定。純函式：吃批次列的 ``features`` dict 即可
    （引擎在判定**之後**快照，let 值都在；``meta["decide"]`` 不需要）。

    不變量（測試守）：``leaf_bin == row["bin"]``、``path`` 與
    `decide_tree._path_of` 相同、逐步缺值的**總數**
    （``sum(len(s.missing) for s in steps)``）與 ``decide_unanswered`` 相同
    （引擎數的是每一題各記一次，`Trace.missing` 才去重）。
    ``route`` 目前只做介面對稱（decide 是 recipe 層級的），留著是
    因為呼叫端本來就知道自己在哪條 route 上，而這個簽名以後才不用改。
    """
    del route  # 見 docstring —— decide 是 recipe 層級的
    # 跟 `batch.redecide` 同一個過濾（那邊 :424-425）：重放要看見它看見的。
    feats: Dict[str, float] = {
        str(k): float(v) for k, v in dict(features or {}).items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)}

    decide = recipe.decide
    if decide is None:
        expr = str(recipe.score.expr or "").strip()
        if not expr:
            return Trace(mode="none", features=feats)
        try:
            missing = tuple(sorted(
                v for v in parse_expression(expr).variables
                if v not in feats))
        except ExpressionError:
            missing = ()
        return Trace(
            mode="score", score_expr=expr,
            score_valued=valued_text(expr, feats),
            score=feats.get("score"),
            threshold=float(recipe.score.threshold),
            bins=dict(recipe.score.bins or {}),
            leaf_bin=(int(feats["bin"]) if "bin" in feats else None),
            missing=missing, features=feats)

    # ---- working numbers（順序 = 宣告序，同引擎）---------------------------
    lets: List[LetTrace] = []
    for item in decide.let:
        name = str(item.name).strip()
        if not name:
            continue
        fill = str(getattr(item, "fill", "") or "")
        scaled = bool(str(getattr(item, "scale", "") or ""))
        try:
            expr_vars = parse_expression(item.expr).variables
        except ExpressionError:
            expr_vars = frozenset()
        lets.append(LetTrace(
            name=name, expr=str(item.expr),
            valued=valued_text(item.expr, feats),
            value=feats.get(name),
            filled=(feats.get(name + "_missing") == 1.0),
            fill=fill, scaled=scaled,
            raw=feats.get(name + "_raw") if scaled else None,
            missing_vars=tuple(sorted(
                v for v in expr_vars if v not in feats))))

    # ---- 樹（rules 走等價的鏈狀樹 —— 跟引擎、畫布同一份）-------------------
    tree = decide_tree.display_tree(decide)
    steps: List[StepTraceRow] = []
    path = ""
    leaf_bin: Optional[int] = None
    leaf_label = ""
    step_missing: List[str] = []
    if tree is not None:
        leaf, walked = decide_tree.walk_steps(tree, feats)
        for node, yes, gaps in walked:
            steps.append(StepTraceRow(
                when=str(node.when),
                valued=valued_text(node.when, feats),
                answer="yes" if yes else "no",
                missing=tuple(gaps)))
            path += "y" if yes else "n"
            step_missing.extend(gaps)
        leaf_bin, leaf_label = int(leaf.bin), str(leaf.label)

    mode = "tree" if decide.tree is not None else "rules"
    # rules 的鏈狀樹裡「走到第 k 步答 yes」= 第 k 條規則對上；全 no = otherwise。
    rule_index = -1
    if mode == "rules" and path.endswith("y"):
        rule_index = len(path) - 1

    score_expr = str(decide.score or "").strip()
    return Trace(
        mode=mode, lets=tuple(lets), steps=tuple(steps), path=path,
        leaf_bin=leaf_bin, leaf_label=leaf_label, rule_index=rule_index,
        score_expr=score_expr,
        score_valued=valued_text(score_expr, feats) if score_expr else "",
        score=feats.get("score"),
        missing=tuple(sorted(set(step_missing))),
        features=feats)
