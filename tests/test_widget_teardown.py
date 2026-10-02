"""拆 widget 只有一種寫法：`ui/buttons.py` 的 `detach_widget` / `discard_widget` /
`clear_layout`（2026-10-02）。

為什麼要一支測試守一個順序：``setParent(None)`` 之前沒 ``hide()``，剛塞進 layout
的 widget 身上排著的「顯示」會落在一個沒有父視窗的 widget 上 —— 它變成一個空白
頂層視窗閃一下。使用者看到的是「雙擊一張卡跳出好幾個空白視窗」。當時 `d4t/ui`
裡有二十一處各自寫的 ``setParent(None)``，只有一處（`clear_layout_parked`）順序
是對的；寫對一次很容易，二十一處全對不可能，所以**全部收成一支**（使用者：
「全面改」），這裡用 ast 守「沒有人再自己寫」。

純 ast、不開 Qt，所以放在核心批。
"""
from __future__ import annotations

import ast
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(REPO, "d4t", "ui")
HELPERS = ("detach_widget", "discard_widget", "clear_layout", "clear_layout_parked")


def _ui_files():
    return sorted(os.path.join(UI, n) for n in os.listdir(UI) if n.endswith(".py"))


def _calls(tree):
    """``(行號, 被叫的名字)``：`x.setParent(None)` → ``setParent``，`f(x)` → ``f``。"""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute):
            out.append((node.lineno, f.attr, node))
        elif isinstance(f, ast.Name):
            out.append((node.lineno, f.id, node))
    return out


def _is_set_parent_none(call) -> bool:
    return (isinstance(call.func, ast.Attribute) and call.func.attr == "setParent"
            and len(call.args) == 1 and isinstance(call.args[0], ast.Constant)
            and call.args[0].value is None)


def test_nobody_outside_the_helper_detaches_a_widget_by_hand():
    offenders = []
    for path in _ui_files():
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and _is_set_parent_none(node):
                    if not (os.path.basename(path) == "buttons.py"
                            and fn.name == "detach_widget"):
                        offenders.append("%s:%d (%s)" % (os.path.basename(path),
                                                         node.lineno, fn.name))
    assert not offenders, (
        "自己寫了 setParent(None)，請改用 buttons.discard_widget / clear_layout / "
        "detach_widget：\n  " + "\n  ".join(offenders))


def test_the_helper_hides_before_it_detaches():
    """順序就是機制：`hide()` → `setParent(None)`。"""
    path = os.path.join(UI, "buttons.py")
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "detach_widget")
    names = [name for _ln, name, _c in sorted(_calls(fn), key=lambda t: t[0])]
    assert "setParent" in names and "hide" in names
    assert names.index("hide") < names.index("setParent"), names


def test_discard_detaches_and_then_deletes_later():
    path = os.path.join(UI, "buttons.py")
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "discard_widget")
    names = [name for _ln, name, _c in sorted(_calls(fn), key=lambda t: t[0])]
    assert names.index("detach_widget") < names.index("deleteLater"), names


def test_the_helpers_are_actually_used():
    """反空洞：守門的對象要真的存在 —— 上面那條在一個沒人拆 widget 的 repo 裡
    也會綠。"""
    users = set()
    for path in _ui_files():
        if os.path.basename(path) == "buttons.py":
            continue
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        if any(h + "(" in src for h in HELPERS):
            users.add(os.path.basename(path))
    assert len(users) >= 10, sorted(users)


@pytest.mark.parametrize("name", HELPERS)
def test_every_helper_still_exists(name):
    path = os.path.join(UI, "buttons.py")
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    assert any(isinstance(n, ast.FunctionDef) and n.name == name for n in tree.body), name
