# F50：判定的警告掛得上徽章（2026-08-28）。
"""**同樣是「指到一個沒人算得出來的數字」，兩邊的下場以前完全不同。**

`Issue.node_id` 是「哪一張卡」，而判定不是一張卡 —— 它是 recipe 的頂層鍵，
所以它的 issue 一律 ``node_id=None``。而 `studio._node_problems()` 第一件事
就是把沒有節點的丟掉（``if not nid: continue``）：

===========  =====================  ==============================
             卡片的特徵警告          判定的特徵警告
===========  =====================  ==============================
畫布徽章      ✅ 一改就看得到          ❌ 沒有
什麼時候講    改的當下                 **跑完之後**，狀態列尾巴一次
===========  =====================  ==============================

而 `_node_problems` 自己的說明寫著徽章為什麼存在：「那個知識以前只在按下
Run trial 的那一刻出現一次……而跑一次是好幾分鐘。」判定就還停在那個狀態。

⚠ **判準是 `DECISION_ISSUE_CODES`，不是「node_id 是 None」** —— 沒有節點的
lint 裡還有三條講分流、一條講整張圖，掛上來就是讓入口卡替別人的問題背鍋。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from d4t.core.pipeline.recipe import (  # noqa: E402
    DECISION_ISSUE_CODES, NON_DECISION_NODELESS_CODES,
)
from d4t.ui import studio as studio_mod, theme as theme_mod  # noqa: E402
from d4t.ui import tree_scene as tree_mod  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    """一份**接好線**的 recipe，再加一棵判定樹。"""
    w = studio_mod.StudioWindow(show_welcome_on_start=False)
    assert w.load_recipe_path(str(FIXTURE), sync=True)
    w.add_decision()
    try:
        yield w
    finally:
        w.close()


def _entry(w):
    return next((it for it in w.pipeline.decision_items()
                 if isinstance(it, tree_mod._EntryItem)), None)


def _feature_that_exists(w) -> str:
    # `feature_owners()` 是「特徵名 → 誰算的」，鍵就是引擎看得到的那些名字
    # （淡線與 lint 用的是同一張表，所以這裡挑出來的一定接得上）。
    names = sorted(n for n in w.model.feature_owners() if n != "score")
    assert names, "前提：這份 recipe 真的量得出東西"
    return names[0]


# --------------------------------------------------------------------------- #
# 1. 有問題就看得到，而且跑之前就看得到
# --------------------------------------------------------------------------- #
def test_a_decision_pointing_at_nothing_gets_a_badge(window):
    w = window
    w.model.set_tree_when("", "nosuch_number > 1")
    w._refresh_pipeline()

    why, level = w._decision_problem()
    assert why and level == "warning"
    assert "nosuch_number" in why

    entry = _entry(w)
    assert entry is not None and entry.problem() == why
    assert "nosuch_number" in entry.toolTip()


def test_it_is_there_before_anything_has_been_run(window):
    """**這才是重點。** 以前那句話只在跑完之後的狀態列尾巴出現一次。"""
    w = window
    assert not w.trial_results, "前提：一顆都還沒跑"
    w.model.set_tree_when("", "nosuch_number > 1")
    w._refresh_pipeline()
    assert _entry(w).problem(), "還沒跑過就該看得到"


def test_a_decision_that_is_wired_up_has_no_badge(window):
    """接得上的時候一個標記都不該有 —— 每份 recipe 都亮的徽章會被學會忽略。"""
    w = window
    w.model.set_tree_when("", "%s > 1" % _feature_that_exists(w))
    w._refresh_pipeline()
    assert w._decision_problem() == ("", "")
    assert _entry(w).problem() == ""


# --------------------------------------------------------------------------- #
# 2. 不准替別人背鍋
# --------------------------------------------------------------------------- #
def test_it_only_claims_the_lints_that_are_really_the_decisions(window):
    """分流與整張圖的問題掛在別處，不掛在判定的入口卡上。

    ⚠ **這一條的第一版抓不到東西**，而那是自己驗出來的：它只問了「被挑中的
    那條在不在 `DECISION_ISSUE_CODES` 裡」—— 拿掉整個判準之後，那個場景剛好
    只有判定的 lint，於是照樣綠。

    現在的場景**故意讓一條不是判定的 lint 更嚴重**（分流指到一條不存在的
    route ＝ error，判定那條是 warning）。沒有判準的話「最嚴重的贏」就會把
    分流的錯掛到判定的入口卡上 —— 使用者去改判定，而問題在別的地方。
    """
    w = window
    w.model.set_tree_when("", "nosuch_number > 1")          # warning（判定的）
    w.model.set_route_by("CLASSNUMBER", {"1": "no_such_route"})  # error（不是）
    w._refresh_pipeline()

    codes = {i.code for i in w.model.validate()
             if not getattr(i, "node_id", None)}
    assert codes & NON_DECISION_NODELESS_CODES, \
        "前提壞了：這個場景要有一條不是判定的 nodeless lint"

    why, level = w._decision_problem()
    assert why and "nosuch_number" in why, why
    assert level == "warning", "把別人那條 error 挑走了"

    claimed = [i for i in w.model.validate()
               if not getattr(i, "node_id", None)
               and str(i.detail or i.title) == why]
    assert claimed and claimed[0].code in DECISION_ISSUE_CODES


def test_the_worst_one_wins(window):
    """error > warning —— 跟卡片那顆徽章同一條規則。"""
    w = window
    w.model.set_tree_when("", "nosuch_number > 1")        # warning
    w._refresh_pipeline()
    assert w._decision_problem()[1] == "warning"

    w.model.set_tree_when("", "this is not an expression")  # error（parse 不過）
    w._refresh_pipeline()
    assert w._decision_problem()[1] == "error"


# --------------------------------------------------------------------------- #
# 3. 兩顆徽章是同一個東西（便利貼）
# --------------------------------------------------------------------------- #
def test_the_two_badges_are_drawn_the_same_way():
    """`_NodeItem._paint_badge` 與 `_EntryItem._paint_badge` 是同一份的兩抄。

    抄過來而不是共用一支是刻意的（body 幾何與 import 方向不同），所以這裡
    留一張便利貼：**動一邊就要動另一邊。** 比的是那幾個決定外觀的數字。
    """
    import re

    def numbers(path, marker):
        src = (REPO / path).read_text(encoding="utf-8")
        body = src.split(marker, 1)[1].split("\n    def ", 1)[0]
        return re.findall(r"\b\d+\.\d+\b", body)

    a = numbers("d4t/ui/canvas.py", "def _paint_badge")
    b = numbers("d4t/ui/tree_scene.py", "def _paint_badge")
    assert a and a == b, (a, b)
