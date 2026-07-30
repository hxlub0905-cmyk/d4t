# ADEPT pipeline engine — authored 2026-07-28 (M1).
"""Score 表達式引擎：手寫 tokenizer → 遞迴下降 parser → AST → evaluator。

設計（見 docs/plans/F0-master-plan.md §4）：
- 變數 = Context.features 的 key（snr_max、cd_x_nm、glv_mean_roi1…）。
- 運算元：``+ - * / **``、比較 ``> < >= <= == !=``、布林 ``and or not``、
  函數 ``sqrt log abs exp``（1 個參數）與 ``min max``（至少 1 個參數）。
- 比較採**左結合折疊**：``a < b < c`` 解讀為 ``(a < b) < c``，
  **不是** Python 的鏈式比較（v1 刻意如此，語意單純）。
- ``**`` 右結合、優先度高於一元負號（``-2**2 == -4``、``2**-1`` 合法）。

SAFE 語意（inline 調參不炸批次的鐵則）：
- 除以 0 → 0.0；log(≤0) → 0.0；sqrt(<0) → 0.0；
  0 的負次方 → 0.0；負數的非整數次方 → 0.0。
- 最終結果為 nan/inf → 0.0。
- 例外：**變數不存在**與**變數值不是數字**會 raise ExpressionError
  （這是 recipe 寫錯，不是資料髒 —— 要讓使用者看到）。

錯誤訊息以繁體中文白話呈現，附 caret（^）指出出錯位置，
非工程師同事也能看懂哪裡打錯了。
"""
from __future__ import annotations

import math
from typing import Any, FrozenSet, List, Mapping, Set, Tuple

__all__ = ["ExpressionError", "Expression", "parse_expression"]

# 訊息中表達式行的縮排（測試依賴此常數對 caret 位置做驗證）
_INDENT = "    "

# 固定參數個數的函數；min/max 為至少 1 個參數
_FIXED_ARITY = {"sqrt": 1, "log": 1, "abs": 1, "exp": 1}
_VARIADIC = ("min", "max")
_KEYWORDS = ("and", "or", "not")
_CMP_OPS = (">", "<", ">=", "<=", "==", "!=")
_TWO_CHAR_OPS = ("**", ">=", "<=", "==", "!=")


class ExpressionError(ValueError):
    """表達式錯誤：``.pos`` 為出錯的字元位置（0 起算），
    訊息共三行 —— 白話說明、原始表達式、caret（^）指位。"""

    def __init__(self, desc: str, text: str = "", pos: int = 0):
        self.desc = desc
        self.text = text
        self.pos = max(0, int(pos))
        msg = (
            f"Problem in the score expression (near character "
            f"{self.pos + 1}): {desc}\n"
            f"{_INDENT}{text}\n"
            f"{_INDENT}{' ' * self.pos}^"
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------
# token = (kind, value, pos)；kind ∈ {"num","name","op","lparen","rparen","comma","end"}
_Token = Tuple[str, Any, int]


def _tokenize(text: str) -> List[_Token]:
    toks: List[_Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        # ---- 數字（int/float，支援 1.5、.5、2.、1e3、1.2e-3）----
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            start = i
            while i < n and text[i].isdigit():
                i += 1
            if i < n and text[i] == ".":
                i += 1
                while i < n and text[i].isdigit():
                    i += 1
            if i < n and text[i] in "eE":
                j = i + 1
                if j < n and text[j] in "+-":
                    j += 1
                if j < n and text[j].isdigit():
                    i = j
                    while i < n and text[i].isdigit():
                        i += 1
                else:
                    raise ExpressionError(
                        "scientific notation (e) must be followed by digits, "
                        "e.g. 1e3", text, i)
            toks.append(("num", float(text[start:i]), start))
            continue
        # ---- 識別字 / 關鍵字 ----
        if c.isalpha() or c == "_":
            start = i
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1
            toks.append(("name", text[start:i], start))
            continue
        # ---- 雙字元運算子優先 ----
        two = text[i:i + 2]
        if two in _TWO_CHAR_OPS:
            toks.append(("op", two, i))
            i += 2
            continue
        if c in "+-*/><":
            toks.append(("op", c, i))
            i += 1
            continue
        if c == "(":
            toks.append(("lparen", c, i))
            i += 1
            continue
        if c == ")":
            toks.append(("rparen", c, i))
            i += 1
            continue
        if c == ",":
            toks.append(("comma", c, i))
            i += 1
            continue
        if c == "=":
            raise ExpressionError(
                "a single '=' cannot be used to compare; write 'equals' as "
                "'=='", text, i)
        if c == "!":
            raise ExpressionError(
                "'!' cannot be used on its own; write 'not equal' as '!='",
                text, i)
        raise ExpressionError(f"unrecognised character '{c}'", text, i)
    toks.append(("end", "", n))
    return toks


# ---------------------------------------------------------------------------
# Parser（遞迴下降；AST 用 tuple 表示，可 pickle）
#
# 文法（低優先度 → 高優先度）：
#   expr    := or
#   or      := and ("or" and)*
#   and     := not ("and" not)*
#   not     := "not" not | cmp
#   cmp     := arith (CMPOP arith)*          ← 左結合折疊，非鏈式
#   arith   := term (("+"|"-") term)*
#   term    := unary (("*"|"/") unary)*
#   unary   := "-" unary | power
#   power   := atom ("**" unary)?            ← 右結合；-2**2 == -(2**2)
#   atom    := NUM | NAME | NAME "(" args ")" | "(" expr ")"
# ---------------------------------------------------------------------------
class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = _tokenize(text)
        self.i = 0

    def _peek(self) -> _Token:
        return self.toks[self.i]

    def _next(self) -> _Token:
        t = self.toks[self.i]
        self.i += 1
        return t

    def _is_name(self, word: str) -> bool:
        kind, val, _ = self._peek()
        return kind == "name" and val == word

    # ---- 進入點 -----------------------------------------------------------
    def parse(self) -> tuple:
        kind, _, pos = self._peek()
        if kind == "end":
            raise ExpressionError(
                "the expression is empty — enter a formula such as "
                "snr_max * 2", self.text, pos)
        node = self.parse_or()
        kind, _, pos = self._peek()
        if kind != "end":
            raise ExpressionError(
                "the expression should have ended here; there is extra content "
                "after it", self.text, pos)
        return node

    # ---- 各優先度層 -------------------------------------------------------
    def parse_or(self) -> tuple:
        node = self.parse_and()
        while self._is_name("or"):
            self._next()
            node = ("bool", "or", node, self.parse_and())
        return node

    def parse_and(self) -> tuple:
        node = self.parse_not()
        while self._is_name("and"):
            self._next()
            node = ("bool", "and", node, self.parse_not())
        return node

    def parse_not(self) -> tuple:
        if self._is_name("not"):
            self._next()
            return ("not", self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self) -> tuple:
        node = self.parse_arith()
        while True:
            kind, val, _ = self._peek()
            if kind == "op" and val in _CMP_OPS:
                self._next()
                node = ("cmp", val, node, self.parse_arith())  # 左結合折疊
            else:
                return node

    def parse_arith(self) -> tuple:
        node = self.parse_term()
        while True:
            kind, val, _ = self._peek()
            if kind == "op" and val in ("+", "-"):
                self._next()
                node = ("bin", val, node, self.parse_term())
            else:
                return node

    def parse_term(self) -> tuple:
        node = self.parse_unary()
        while True:
            kind, val, _ = self._peek()
            if kind == "op" and val in ("*", "/"):
                self._next()
                node = ("bin", val, node, self.parse_unary())
            else:
                return node

    def parse_unary(self) -> tuple:
        kind, val, _ = self._peek()
        if kind == "op" and val == "-":
            self._next()
            return ("neg", self.parse_unary())
        return self.parse_power()

    def parse_power(self) -> tuple:
        base = self.parse_atom()
        kind, val, _ = self._peek()
        if kind == "op" and val == "**":
            self._next()
            # 指數走 unary → 右結合，且 2**-1 合法
            return ("bin", "**", base, self.parse_unary())
        return base

    def parse_atom(self) -> tuple:
        kind, val, pos = self._next()
        if kind == "num":
            return ("num", float(val))
        if kind == "name" and val not in _KEYWORDS:
            k2, _, _ = self._peek()
            if k2 == "lparen":
                return self.parse_call(str(val), pos)
            return ("var", str(val), pos)
        if kind == "lparen":
            node = self.parse_or()
            k2, _, p2 = self._peek()
            if k2 != "rparen":
                raise ExpressionError("missing a closing bracket ')'", self.text, p2)
            self._next()
            return node
        raise ExpressionError(
            "a number, a variable or an opening bracket is expected here",
            self.text, pos)

    def parse_call(self, name: str, name_pos: int) -> tuple:
        if name not in _FIXED_ARITY and name not in _VARIADIC:
            raise ExpressionError(
                f"'{name}' is not a supported function "
                f"(supported: abs, exp, log, max, min, sqrt)",
                self.text, name_pos)
        self._next()  # 吃掉 '('
        args: List[tuple] = []
        kind, _, _ = self._peek()
        if kind == "rparen":
            self._next()
        else:
            while True:
                args.append(self.parse_or())
                kind, _, pos = self._peek()
                if kind == "comma":
                    self._next()
                    continue
                if kind == "rparen":
                    self._next()
                    break
                raise ExpressionError(
                    "function arguments must be separated by commas and end "
                    "with a closing bracket ')'", self.text, pos)
        # ---- 參數個數在「解析期」就檢查，不等執行才爆 ----
        if name in _FIXED_ARITY and len(args) != _FIXED_ARITY[name]:
            raise ExpressionError(
                f"function {name}() takes 1 argument, but {len(args)} were "
                f"given",
                self.text, name_pos)
        if name in _VARIADIC and len(args) < 1:
            raise ExpressionError(
                f"function {name}() needs at least 1 argument", self.text,
                name_pos)
        return ("call", name, tuple(args))


# ---------------------------------------------------------------------------
# Evaluator（SAFE 語意）
# ---------------------------------------------------------------------------
def _truthy(v: float) -> bool:
    return v != 0.0


def _safe_pow(a: float, b: float) -> float:
    """SAFE 次方：0 的負次方 → 0.0；負底非整數次方 → 0.0；溢位 → inf。"""
    if a == 0.0 and b < 0.0:
        return 0.0
    if a < 0.0 and math.isfinite(b) and b != math.floor(b):
        return 0.0
    try:
        return float(a ** b)
    except OverflowError:
        # 結果太大：以 inf 代表，最終結果層會安全歸零
        neg = a < 0.0 and math.isfinite(b) and (math.floor(b) % 2 == 1)
        return -math.inf if neg else math.inf


def _safe_call(name: str, args: List[float]) -> float:
    if name == "sqrt":
        x = args[0]
        return math.sqrt(x) if x >= 0.0 else 0.0
    if name == "log":
        x = args[0]
        return math.log(x) if x > 0.0 else 0.0
    if name == "abs":
        return abs(args[0])
    if name == "exp":
        try:
            return math.exp(args[0])
        except OverflowError:
            return math.inf
    if name == "min":
        return float(min(args))
    if name == "max":
        return float(max(args))
    raise ExpressionError(f"'{name}' is not a supported function")  # pragma: no cover — parser 已擋


def _lookup_var(name: str, pos: int, variables: Mapping[str, Any], text: str) -> float:
    try:
        v = variables[name]
    except (KeyError, TypeError):
        avail = (", ".join(sorted(variables)) if variables
             else "(no variables are available yet)")
        raise ExpressionError(
            f"variable '{name}' not found; available variables: {avail}",
            text, pos) from None
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if v is None or isinstance(v, (str, bytes)):
        raise ExpressionError(
            f"variable '{name}' is not a number (got {type(v).__name__}: "
            f"{v!r}) — check that the upstream card really produces this "
            f"feature", text, pos)
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ExpressionError(
            f"variable '{name}' is not a number (got {type(v).__name__}) — "
            f"check that the upstream card really produces this feature",
            text, pos) from None


def _eval(node: tuple, variables: Mapping[str, Any], text: str) -> float:
    tag = node[0]
    if tag == "num":
        return float(node[1])
    if tag == "var":
        return _lookup_var(node[1], node[2], variables, text)
    if tag == "neg":
        return -_eval(node[1], variables, text)
    if tag == "not":
        return 0.0 if _truthy(_eval(node[1], variables, text)) else 1.0
    if tag == "bool":
        op, lhs, rhs = node[1], node[2], node[3]
        lv = _truthy(_eval(lhs, variables, text))
        rv = _truthy(_eval(rhs, variables, text))
        if op == "and":
            return 1.0 if (lv and rv) else 0.0
        return 1.0 if (lv or rv) else 0.0
    if tag == "cmp":
        op, lhs, rhs = node[1], node[2], node[3]
        lv = _eval(lhs, variables, text)
        rv = _eval(rhs, variables, text)
        if op == ">":
            ok = lv > rv
        elif op == "<":
            ok = lv < rv
        elif op == ">=":
            ok = lv >= rv
        elif op == "<=":
            ok = lv <= rv
        elif op == "==":
            ok = lv == rv
        else:  # "!="
            ok = lv != rv
        return 1.0 if ok else 0.0
    if tag == "bin":
        op, lhs, rhs = node[1], node[2], node[3]
        lv = _eval(lhs, variables, text)
        rv = _eval(rhs, variables, text)
        if op == "+":
            return lv + rv
        if op == "-":
            return lv - rv
        if op == "*":
            return lv * rv
        if op == "/":
            return lv / rv if rv != 0.0 else 0.0  # SAFE：除以 0 → 0.0
        if op == "**":
            return _safe_pow(lv, rv)
    if tag == "call":
        args = [_eval(a, variables, text) for a in node[2]]
        return _safe_call(node[1], args)
    raise ExpressionError(f"internal error: unknown AST node {tag!r}")  # pragma: no cover


def _collect_vars(node: tuple, out: Set[str]) -> None:
    tag = node[0]
    if tag == "var":
        out.add(node[1])
    elif tag in ("neg", "not"):
        _collect_vars(node[1], out)
    elif tag in ("bool", "cmp", "bin"):
        _collect_vars(node[2], out)
        _collect_vars(node[3], out)
    elif tag == "call":
        for a in node[2]:
            _collect_vars(a, out)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------
class Expression:
    """已解析的表達式：``variables`` 列出用到的變數、``eval`` 求值。"""

    __slots__ = ("text", "_ast", "_vars")

    def __init__(self, text: str, ast: tuple, variables: Set[str]):
        self.text = text
        self._ast = ast
        self._vars: FrozenSet[str] = frozenset(variables)

    @property
    def variables(self) -> FrozenSet[str]:
        """表達式中用到的所有變數名（不含函數名）。"""
        return self._vars

    def eval(self, vars: Mapping[str, Any]) -> float:
        """以 ``vars``（通常是 Context.features）求值。

        比較與布林運算回傳 1.0/0.0；最終結果為 nan/inf 一律歸 0.0。
        變數不存在或值不是數字會 raise :class:`ExpressionError`。
        """
        result = float(_eval(self._ast, vars if vars is not None else {}, self.text))
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result

    def __repr__(self) -> str:  # pragma: no cover
        return f"Expression({self.text!r})"


def parse_expression(text: str) -> Expression:
    """解析表達式文字；語法錯誤 raise :class:`ExpressionError`（含 caret 指位）。"""
    if not isinstance(text, str):
        raise ExpressionError(
            f"the expression must be text, got {type(text).__name__}",
            str(text), 0)
    parser = _Parser(text)
    ast = parser.parse()
    names: Set[str] = set()
    _collect_vars(ast, names)
    return Expression(text, ast, names)
