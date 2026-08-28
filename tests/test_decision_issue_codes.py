# F50：沒有節點的 lint 都要被分類到（2026-08-28）。
"""`Issue.node_id` 是「哪一張卡」，而判定不是一張卡 —— 它是 recipe 的頂層鍵，
所以它的 issue 一律 ``node_id=None``。而 `studio._node_problems()` 第一件事
就是把沒有節點的 issue 丟掉，於是**判定的警告畫不出徽章**。

F50 給它一個家（`DECISION_ISSUE_CODES`）。這一支是那張表的**反向測試**：

> 每一條沒有節點的 lint 都要被分類到 —— 判定的、或明講不是判定的。

沒有這一條的話，下一個人加一條 `node_id=None` 的 lint 而忘了分類，它會安靜地
掉回地上（就是這一輪在修的那個洞），而全套測試照樣綠。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from d4t.core.pipeline.recipe import (  # noqa: E402
    DECISION_ISSUE_CODES, NON_DECISION_NODELESS_CODES,
)

_SRC = (REPO / "d4t" / "core" / "pipeline" / "recipe.py").read_text(
    encoding="utf-8")


def _nodeless_codes() -> set:
    """原始碼裡每一個 ``Issue(code=…, …, node_id=None…)`` 的 code。

    掃原始碼而不是跑一遍 validate：**要抓的是「有人加了一條卻沒分類」**，
    而那條新 lint 不一定在任何一份 fixture recipe 上觸發得到。
    """
    out = set()
    for block in re.findall(r"Issue\(([^)]*?node_id=None[^)]*?)\)", _SRC,
                            re.S):
        m = re.search(r'code="([^"]+)"', block)
        if m:
            out.add(m.group(1))
    return out


def test_every_nodeless_lint_is_classified():
    found = _nodeless_codes()
    assert found, "一條都沒掃到 —— 這支測試的正規表示式壞了（反空洞）"
    known = set(DECISION_ISSUE_CODES) | set(NON_DECISION_NODELESS_CODES)
    unclassified = sorted(found - known)
    assert not unclassified, (
        "這幾條 lint 沒有節點、也沒有被分類，所以它們畫不出任何徽章：%s\n"
        "把它們加進 recipe.DECISION_ISSUE_CODES（判定的）或 "
        "NON_DECISION_NODELESS_CODES（不是判定的）。" % unclassified)


def test_the_two_tables_do_not_overlap():
    both = DECISION_ISSUE_CODES & NON_DECISION_NODELESS_CODES
    assert not both, both


def test_the_tables_do_not_list_codes_that_are_gone():
    """表上點名的 code 要真的還有人發 —— 不然它是一張只會變長的紙。"""
    found = _nodeless_codes()
    stale = sorted((set(DECISION_ISSUE_CODES)
                    | set(NON_DECISION_NODELESS_CODES)) - found)
    assert not stale, "表上這幾條已經沒有人發了：%s" % stale
