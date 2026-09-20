# F117 J4：刪掉中間那張卡之後，補線是一個按鈕（2026-09-20）。
"""走查記的是「刪掉中間的卡，上下游斷開」。

⚠ **斷開本身是對的。** `RecipeModel.remove` 連同碰到它的每一條線一起拿掉，
因為殘留的線會接到一張使用者從來沒接過的新卡（F10-5 那個使用者回報過的
bug）。真正的問題是**接回來要重拉一次**，而他剛剛做的只是「把中間這張換掉」。

所以這一輪加的是**提議**，不是自動補線 —— 鐵則 10：畫布上每一條線都是使用者
拉的。這一支最重要的兩條：

* `bridge_plan` **問不出來就不提議**（`sub` 那種兩條單數輸入的卡）；
* 按下去走的是**跟手拉線同一條路**（`canvas_edges.connect`），不是
  `model.add_edge` 的捷徑 —— 不然補出來的線跟手拉的線不一樣，而畫布上看
  起來會一模一樣。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

from d4t.core.pipeline.recipe import Recipe           # noqa: E402
from d4t.ui import theme as theme_mod                 # noqa: E402
from d4t.ui.viewmodel import RecipeModel              # noqa: E402

RECIPE = REPO / "recipes" / "ebi-die-to-die.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def model():
    raw = json.loads(RECIPE.read_text(encoding="utf-8"))
    return RecipeModel.from_recipe(Recipe.from_json_dict(raw))


def _lines(m):
    return {(e.src, e.src_out, e.dst, e.dst_in) for e in m.edges}


# --------------------------------------------------------------------------- #
# 1. 算得出來的那幾條
# --------------------------------------------------------------------------- #
def test_a_card_in_a_chain_proposes_the_line_through_it(model):
    """`load → norm → sub` 裡拿掉 `norm`，提議 `load → sub`。"""
    assert model.bridge_plan("norm") == [("load", "test", "sub", "a")]


def test_it_keeps_the_upstream_output_port(model):
    """⚠ **埠要帶過去。** 下游那張卡接的是 `load` 的 `test` 那一顆輸出，不是
    「load」這個節點 —— 掉了埠就等於回到 F9-1 之前「影像流是全域名字」的世界，
    而那正是分支分不開的原因。"""
    src, src_out, dst, dst_in = model.bridge_plan("norm")[0]
    assert (src_out, dst_in) == ("test", "a")


def test_a_second_input_does_not_confuse_it(model):
    """⚠ `norm_ref` 有**兩條**進來的線：`load.ref → streams` 與
    `load.test → range_from`。

    穿過這張卡的是前者 —— 判準是 CLAUDE.md 的單複數規矩（`*_keys` 是「這張卡
    處理的東西」，`*_key` 是「順便參考的另一條流」），不是哪一條先接的。
    """
    assert model.bridge_plan("norm_ref") == [("load", "ref", "sub", "b")]


def test_two_equal_inputs_are_left_alone(model):
    """⚠ **`sub` 的 `a` 與 `b` 一樣重要，所以不提議。**

    替使用者猜錯一條線，會安靜地算出一批看起來很正常的數字 —— 那比沒有補線
    糟得多。寧可讓他自己拉。
    """
    assert model.bridge_plan("sub") == []


def test_the_ends_have_nothing_to_bridge(model):
    assert model.bridge_plan("load") == []
    assert model.bridge_plan("report") == []


def test_an_unknown_card_is_not_a_crash(model):
    assert model.bridge_plan("nope") == []
    assert model.bridge_plan("") == []


def test_it_does_not_propose_a_line_that_is_already_there(model):
    """本來就有那條線的話，「補線」什麼都不該做。"""
    assert model.add_edge("load", "sub", "test", "a") is True
    assert model.bridge_plan("norm") == []


def test_it_never_proposes_a_self_loop(model):
    """`X → mid → X` 補起來會是 `X → X`。

    ⚠ **`add_edge` 造不出這個形狀**（它擋成環），所以這一條的前提要自己塞進
    `model.edges` 裡。那不是為了測一個不會發生的事：`RecipeModel.from_recipe`
    吃的是**手寫的 recipe JSON**，而那份檔案裡的線沒有經過 `add_edge`。
    """
    from d4t.core.pipeline.recipe import Edge

    model.edges.append(Edge(src="glv", dst="norm", src_out="",
                            dst_in="streams"))
    assert any(e.src == "glv" and e.dst == "norm" for e in model.edges), "前提"
    for src, _out, dst, _in in model.bridge_plan("norm"):
        assert src != dst, (src, dst)


def test_the_plan_is_only_a_plan(model):
    """⚠ **算完之後 model 一條線都沒有變。** 它是提議，不是動作。"""
    before = _lines(model)
    for nid in list(model.node_order):
        model.bridge_plan(nid)
    assert _lines(model) == before


# --------------------------------------------------------------------------- #
# 2. 按下去才成真
# --------------------------------------------------------------------------- #
def test_deleting_offers_the_button_and_clicking_it_reconnects(qapp):
    from d4t.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.load_recipe_path(str(RECIPE)) is True
        plan = win.model.bridge_plan("norm")
        assert plan, "前提：這張卡補得回來"

        win._on_remove_requested("norm")
        assert "norm" not in win.model.nodes
        assert set(plan) & _lines(win.model) == set(), \
            "⚠ 刪完**還沒有**補線 —— 補線是使用者按下去的那一步"
        assert win.status_action.text(), "沒有那顆鈕 —— 提議根本沒送到畫面上"

        win.status_action.click()
        qapp.processEvents()
        assert set(plan) <= _lines(win.model), "按了鈕，線沒有接上"
    finally:
        win.close()


def test_the_reconnect_is_one_undo(qapp):
    """⚠ 使用者按的是**一顆鈕**，Ctrl+Z 就該退回按之前。

    接一條線在 model 上是好幾個動作（加線、把下游那一格指到這條流、擠掉搶
    同一個輸入的舊線）—— 各記一步的話，一次復原會停在一個使用者從來沒有做
    出來過的中間狀態（F9-7 記過同一件事）。
    """
    from d4t.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.load_recipe_path(str(RECIPE)) is True
        win._on_remove_requested("norm")
        after_delete = _lines(win.model)
        win.status_action.click()
        qapp.processEvents()
        assert _lines(win.model) != after_delete
        win.model.undo()
        assert _lines(win.model) == after_delete, "一次復原沒有回到按之前"
    finally:
        win.close()


def test_a_card_with_nothing_to_bridge_just_says_removed(qapp):
    """⚠ 沒東西補的時候**不准掛一顆按了沒事的鈕**。

    一顆按下去什麼都不會發生的鈕，比沒有鈕更傷 —— 它教使用者不要相信那個
    位置。
    """
    from d4t.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.load_recipe_path(str(RECIPE)) is True
        win._on_remove_requested("report")
        assert "Removed" in win.status_text()
        assert not win.status_action.text()
    finally:
        win.close()


def test_the_offer_goes_through_the_same_door_as_a_hand_drawn_line():
    """⚠ **這一條守的是一條捷徑不存在。**

    接一條線的規矩住在 `edit_plan`／`canvas_edges.connect`（下游那一格要指到
    這條流、搶同一個輸入的舊線要擠掉、成環要擋）。`bridge` 直接叫
    `model.add_edge` 的話，補出來的線跟手拉的線**不一樣** —— 而畫布上看起來
    會一模一樣，所以沒有人會發現。
    """
    import ast

    src = (REPO / "d4t" / "ui" / "canvas_edges.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "bridge")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "connect" in called
    attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert "add_edge" not in attrs
