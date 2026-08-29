# F52：一個特徵值，一種寫法（2026-08-28）。
"""在 `ui/numbers.py` 出生之前，**同一個數字在畫面上有六種寫法** ——
六個各自寫的格式化函式，沒有一個共用。實測：

=========  ==========  ==========  ==========  =========
值          結果表       特徵表       Gallery     影像標記
=========  ==========  ==========  ==========  =========
66.1163    66.12       66.116      66.1        66
1234.5     **1234**    1234.500    1.23e+03    1234
99.995     **100**     99.995      100         100
0.000312   0.000312    0.000312    0.000312    **0.00**
=========  ==========  ==========  ==========  =========

三個真的會出事的：``99.995`` 在結果表是 100、在單顆特徵表是 99.995（使用者
會以為自己點錯顆）；``1234.5`` 一邊丟掉 ``.5``、一邊補三位假精度；
``0.000312`` 畫在影像上是 ``0.00``（讀起來是零）。

這一支守兩件事：**每個顯示點印出來一樣**，以及**那幾支別名真的是別名**
（值一樣可能只是巧合 —— 兩份實作在某些值上剛好同意）。
"""
from __future__ import annotations

import inspect as _inspect
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


#: 挑過的值：每一個都對應上面那張表裡的一個症狀。
VALUES = [66.1163, 1234.5, 99.995, 0.000312, 3.14159, 12.0, 0.0421,
          -7.25, 0.0, 1234567.0]


def _sites():
    """每一個把**特徵值**印給人看的地方 → ``(名字, 函式)``。"""
    from d4t.ui.gallery import _fmt_score
    from d4t.ui.inspectors import _fmt
    from d4t.ui.numbers import format_feature_value
    from d4t.ui.results_table import ResultsTableModel  # noqa: F401 — 見下
    from d4t.ui.why_panel import _fmt as why_fmt
    from d4t.ui.widgets import _fmt_number

    return [("numbers", format_feature_value),
            ("特徵表 widgets._fmt_number", _fmt_number),
            ("Gallery gallery._fmt_score", _fmt_score),
            ("儀表 inspectors._fmt", _fmt),
            ("Why why_panel._fmt", why_fmt)]


# --------------------------------------------------------------------------- #
# 1. 印出來一樣
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", VALUES)
def test_every_place_prints_the_same_string(qapp, value):
    got = {name: fn(value) for name, fn in _sites()}
    assert len(set(got.values())) == 1, got


def test_the_results_table_agrees_too(qapp):
    """結果表走 model 的 DisplayRole，所以另外量一次（它不是一支函式）。"""
    from PySide6.QtCore import Qt

    from d4t.ui.numbers import format_feature_value
    from d4t.ui.results_table import ResultsTableModel

    rows = [{"defect_id": "1", "ok": True, "error": None, "score": v,
             "bin": 0, "features": {"x": v}} for v in VALUES]
    m = ResultsTableModel()
    m.set_results(rows)
    col = m.columns().index("x")
    for i, v in enumerate(VALUES):
        shown = m.data(m.index(i, col), Qt.DisplayRole)
        assert shown == format_feature_value(v), (v, shown)


# --------------------------------------------------------------------------- #
# 2. 那幾支真的是別名（值一樣可能只是巧合）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["特徵表 widgets._fmt_number",
                                  "Gallery gallery._fmt_score",
                                  "儀表 inspectors._fmt",
                                  "Why why_panel._fmt"])
def test_they_delegate_rather_than_agree_by_luck(qapp, name):
    """**兩份實作在某些值上剛好同意，不代表它們是同一份。**

    上面那條比的是值 —— 而這個 repo 記過三次「同一份抄兩次然後漂開」，
    每一次都是從「現在看起來一樣」開始的。所以這一條看的是**原始碼**：
    那幾支要真的呼叫 `format_feature_value`。
    """
    import ast
    import textwrap

    fn = dict(_sites())[name]
    # ⚠ **只看函式體，不看 docstring。** 第一版直接掃 `getsource`，而每一支
    # 別名的說明裡都寫著「F52 起它是 format_feature_value 的別名」——
    # 於是把它換回一份自己寫的實作，這一條照樣綠（實測過）。
    # 同一個形狀這一輪已經是第三次了：**掃原始碼的測試要先把字掃掉。**
    tree = ast.parse(textwrap.dedent(_inspect.getsource(fn)))
    body = tree.body[0].body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)):
        body = body[1:]
    called = {n.func.id for n in ast.walk(ast.Module(body=body, type_ignores=[]))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert called & {"format_feature_value", "format_feature_value_short"}, (
        "%s 沒有呼叫共用那一支 —— 它自己又寫了一份" % name)


#: **不是特徵值**、所以可以自己挑位數的那幾行（模組 → 出現幾次）。
#:
#: ⚠ 每一列都要講得出「它印的不是某一顆的特徵值」。目前只有一種：**座標軸的
#: 刻度**。軸標要的是短的整數（``0`` … ``250``），拿 5 位有效數字去印會讓
#: 一條 260 px 寬的軸兩端各占掉一半。
#:
#: 配一支反向測試（`test_the_allowlist_does_not_rot`）—— 這個 repo 的
#: `ALLOWED_ERRORS` 學到的那一課：**任何例外清單都要有那支反向的測試**，
#: 不然它就是一張只會變長的紙。
_AXIS_LABEL_ALLOWLIST = {"widgets": 2}      # 直方圖 x 軸的 lo / hi


def _precision_picks(mod: str) -> int:
    text = (REPO / "d4t" / "ui" / ("%s.py" % mod)).read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith("#"))
    return sum(code.count(bad) for bad in ('"%.4g"', '"%.3g"', '"%.3f"'))


@pytest.mark.parametrize("mod", ["gallery", "widgets", "inspectors",
                                 "why_panel", "results_table"])
def test_the_shared_one_is_the_only_place_that_picks_a_precision(qapp, mod):
    """挑有效位數這件事只有一個家（座標軸刻度除外，見上）。"""
    allowed = _AXIS_LABEL_ALLOWLIST.get(mod, 0)
    got = _precision_picks(mod)
    assert got <= allowed, (
        "%s 多了 %d 個自己挑位數的地方 —— 特徵值請走 format_feature_value；"
        "真的是座標軸刻度的話，把 _AXIS_LABEL_ALLOWLIST 加上去並寫下理由"
        % (mod, got - allowed))


def test_the_allowlist_does_not_rot(qapp):
    """**例外修好了卻沒從表上拿掉，那個模組從此少一條防線而測試照樣綠。**

    所以反過來也要問一次：表上寫著幾個，就要真的還有幾個。
    """
    for mod, n in _AXIS_LABEL_ALLOWLIST.items():
        assert _precision_picks(mod) == n, (
            "%s 的例外從 %d 變成 %d 了 —— 把 _AXIS_LABEL_ALLOWLIST 改對"
            % (mod, n, _precision_picks(mod)))


# --------------------------------------------------------------------------- #
# 3. 非數字的那幾種各有各的字
# --------------------------------------------------------------------------- #
def test_the_awkward_values_each_say_something_useful(qapp):
    from d4t.ui.numbers import format_feature_value as f

    assert f(None) == "", "沒有值要留白 —— 不是 `None` 那四個字（F30）"
    assert f(True) == "Yes" and f(False) == "No"
    assert f(float("nan")) == "NaN"
    assert f(float("inf")) == "∞" and f(float("-inf")) == "-∞"
    assert f("not a number") == "not a number"
    assert f(12.0) == "12", "整數不拖小數"


# --------------------------------------------------------------------------- #
# 4. 影像上的短版：刻意的例外，但不准把小數印成零
# --------------------------------------------------------------------------- #
def test_the_short_one_never_prints_a_small_number_as_zero(qapp):
    """``0.000312 → 0.00`` 讀起來是**零**，而這個標記畫在影像上。"""
    from d4t.ui.numbers import format_feature_value_short as s

    for v in (0.000312, 0.0009, -0.00044):
        got = s(v)
        assert float(got.replace("−", "-")) != 0.0, (v, got)


def test_the_short_one_is_only_used_on_the_image(qapp):
    """短版是**刻意的例外**，而例外要有邊界：只有疊圖用它。"""
    from d4t.ui import numbers

    users = []
    for path in sorted((REPO / "d4t" / "ui").glob("*.py")):
        if path.name == "numbers.py":
            continue
        text = path.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in text.splitlines()
                         if not ln.lstrip().startswith("#"))
        if "format_feature_value_short" in code:
            users.append(path.name)
    assert users == ["inspectors.py"], users
    assert numbers.format_feature_value_short(5.0, signed=True) == "+5"
