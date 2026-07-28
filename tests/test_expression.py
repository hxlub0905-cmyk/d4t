"""M1 驗收：score 表達式引擎（優先度、比較折疊、函數 arity、SAFE 語意、caret）。"""
from __future__ import annotations

import math

import pytest

from adept.core.pipeline import ExpressionError, parse_expression


def ev(text, variables=None):
    return parse_expression(text).eval(variables or {})


# ---------------------------------------------------------------------------
# 優先度與結合性
# ---------------------------------------------------------------------------
def test_precedence_mul_over_add():
    assert ev("2 + 3 * 4") == 14.0
    assert ev("(2 + 3) * 4") == 20.0


def test_power_right_assoc():
    assert ev("2 ** 3 ** 2") == 512.0  # 2**(3**2)，非 (2**3)**2=64


def test_unary_minus_binds_below_power():
    assert ev("-2**2") == -4.0          # Python 語意：-(2**2)
    assert ev("(-2)**2") == 4.0
    assert ev("2**-1") == 0.5           # 指數可帶一元負號


def test_left_assoc_sub_div():
    assert ev("10 - 4 - 3") == 3.0
    assert ev("12 / 4 / 3") == 1.0


def test_number_formats():
    assert ev("2.5e2") == 250.0
    assert ev(".5 + 1") == 1.5
    assert ev("1.5") == 1.5


# ---------------------------------------------------------------------------
# 比較與布林 → 1.0 / 0.0
# ---------------------------------------------------------------------------
def test_comparisons_return_float():
    assert ev("3 > 2") == 1.0
    assert ev("2 > 3") == 0.0
    assert ev("2 >= 2") == 1.0
    assert ev("2 <= 1") == 0.0
    assert ev("1 == 1") == 1.0
    assert ev("1 != 1") == 0.0


def test_comparison_folds_left_assoc_not_python_chaining():
    # (3 < 2) → 0.0；0.0 < 1 → 1.0。Python 鏈式比較會給 False（0.0）。
    assert ev("3 < 2 < 1") == 1.0
    # (1 < 2) → 1.0；1.0 < 3 → 1.0
    assert ev("1 < 2 < 3") == 1.0


def test_booleans():
    assert ev("1 and 0") == 0.0
    assert ev("1 and 2") == 1.0
    assert ev("1 or 0") == 1.0
    assert ev("0 or 0") == 0.0
    assert ev("not 0") == 1.0
    assert ev("not 3") == 0.0
    assert ev("not 1 > 2") == 1.0          # not 綁比較之後：not (1>2)
    assert ev("not 1 or 1") == 1.0         # (not 1) or 1
    assert ev("1 == 1 and 2 > 3") == 0.0
    assert ev("(1 < 2) and (3 > 4)") == 0.0


def test_arith_precedence_over_comparison():
    assert ev("1 + 1 == 2") == 1.0


# ---------------------------------------------------------------------------
# 函數（含 parse 期 arity 檢查）
# ---------------------------------------------------------------------------
def test_functions_arity_one():
    assert ev("sqrt(9)") == 3.0
    assert ev("abs(0 - 2)") == 2.0
    assert ev("abs(-2)") == 2.0
    assert ev("exp(0)") == 1.0
    assert ev("log(1)") == 0.0


def test_min_max_multiarg():
    assert ev("min(3, 1, 2)") == 1.0
    assert ev("max(3, 1, 2)") == 3.0
    assert ev("min(5)") == 5.0
    assert ev("max(1, 2) + min(0, 4)") == 2.0


def test_arity_error_at_parse_time():
    with pytest.raises(ExpressionError):
        parse_expression("sqrt(1, 2)")
    with pytest.raises(ExpressionError):
        parse_expression("log()")
    with pytest.raises(ExpressionError):
        parse_expression("min()")
    with pytest.raises(ExpressionError):
        parse_expression("max()")


def test_unknown_function_rejected():
    with pytest.raises(ExpressionError):
        parse_expression("sin(1)")


# ---------------------------------------------------------------------------
# variables
# ---------------------------------------------------------------------------
def test_variables_set():
    e = parse_expression("snr_max * sqrt(blob_area) + min(a, b) - a")
    assert e.variables == frozenset({"snr_max", "blob_area", "a", "b"})
    assert isinstance(e.variables, frozenset)
    assert parse_expression("1 + 2").variables == frozenset()


def test_variable_eval():
    assert ev("snr_max * 2", {"snr_max": 3.5}) == 7.0
    assert ev("a > b", {"a": 1, "b": 2}) == 0.0


# ---------------------------------------------------------------------------
# SAFE 語意
# ---------------------------------------------------------------------------
def test_safe_division_by_zero():
    assert ev("1 / 0") == 0.0
    assert ev("0 / 0") == 0.0
    assert ev("x / y", {"x": 5.0, "y": 0.0}) == 0.0


def test_safe_log():
    assert ev("log(0)") == 0.0
    assert ev("log(-5)") == 0.0
    assert ev("log(x)", {"x": -1.0}) == 0.0


def test_safe_sqrt():
    assert ev("sqrt(-9)") == 0.0
    assert ev("sqrt(0 - 9)") == 0.0


def test_safe_pow():
    assert ev("0 ** -1") == 0.0            # 0 的負次方
    assert ev("(-2) ** 0.5") == 0.0        # 負底非整數次方
    assert ev("(-2) ** 3") == -8.0         # 負底整數次方照算


def test_final_nan_inf_to_zero():
    assert ev("exp(10000)") == 0.0         # overflow → inf → 0.0
    assert ev("1e308 * 10") == 0.0         # inf → 0.0
    assert ev("(1/0) ** 0") == 1.0         # 中間 SAFE 後正常值保留


def test_nan_variable_final_zero():
    assert ev("x + 1", {"x": float("nan")}) == 0.0
    assert ev("x", {"x": float("inf")}) == 0.0


# ---------------------------------------------------------------------------
# 錯誤訊息：caret 位置、missing var、非數字變數
# ---------------------------------------------------------------------------
def test_caret_position_unknown_symbol():
    with pytest.raises(ExpressionError) as ei:
        parse_expression("1 + $")
    e = ei.value
    assert e.pos == 4
    lines = str(e).splitlines()
    assert len(lines) == 3
    assert lines[1] == "    1 + $"
    assert lines[2] == "    " + " " * 4 + "^"   # caret 對準第 5 個字元


def test_caret_position_trailing_garbage():
    with pytest.raises(ExpressionError) as ei:
        parse_expression("1 + 2 3")
    assert ei.value.pos == 6
    lines = str(ei.value).splitlines()
    assert lines[2].index("^") - 4 == 6         # 4 = 訊息縮排寬度


def test_caret_position_missing_operand():
    with pytest.raises(ExpressionError) as ei:
        parse_expression("1 + ")
    assert ei.value.pos == 4                    # 指到結尾


def test_empty_expression():
    with pytest.raises(ExpressionError):
        parse_expression("")
    with pytest.raises(ExpressionError):
        parse_expression("   ")


def test_single_equals_hint():
    with pytest.raises(ExpressionError) as ei:
        parse_expression("a = 1")
    assert "==" in str(ei.value)


def test_missing_paren():
    with pytest.raises(ExpressionError):
        parse_expression("(1 + 2")
    with pytest.raises(ExpressionError):
        parse_expression("sqrt(1")


def test_missing_variable_raises_and_lists_available():
    e = parse_expression("a + b")
    with pytest.raises(ExpressionError) as ei:
        e.eval({"a": 1.0, "zz": 2.0})
    msg = str(ei.value)
    assert "'b'" in msg
    assert "a" in msg and "zz" in msg           # 列出目前可用變數
    assert ei.value.pos == 4                    # 指到 b 的位置


def test_non_numeric_variable_friendly_error():
    e = parse_expression("a * 2")
    with pytest.raises(ExpressionError):
        e.eval({"a": "hello"})
    with pytest.raises(ExpressionError):
        e.eval({"a": None})
    with pytest.raises(ExpressionError):
        e.eval({"a": [1, 2]})


def test_bool_variable_ok():
    assert ev("a + 1", {"a": True}) == 2.0
