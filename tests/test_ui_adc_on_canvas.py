# Decision 是畫布上的一張卡：拖得動、刪得掉（2026-08-25 → F123 期 1）。
"""使用者 2026-08-25：「ADC 也要能在原畫布上拖曳 移除」；2026-09-29：「我會覺得對
畫布來說很奇怪，不管是 ADC card 或者是 Output card 的定位（理論上 input =
output）」→ 做法 B：Decision 是一張真的卡。

以前的把手是判定區的淡紫虛線框，右上角一顆 ✕；現在把手就是那張卡：

* **拖那張卡，樹跟著走**（樹是一個結構，不是幾張散卡 —— 那句話仍然成立）；
* **刪那張卡＝拿掉整個判定**，而且**先問過**；復原一步回來。

兩條不變量沒有動：
* 拖它**不改 recipe**（位置是 session 狀態）；
* 拖它**不改樹的形狀**（動的只有畫布座標）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.ui import studio as studio_mod, theme as theme_mod  # noqa: E402
from d4t.ui import tree_scene  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.model.add_step("load_patch")
    win.add_decision()
    try:
        yield win
    finally:
        win.close()


def _card(win):
    nid = win.model.decision_node()
    assert nid, "add_decision 沒有放上一張 Decision 卡"
    return win.pipeline.node_item(nid)


# --------------------------------------------------------------------------- #
# 它是一張卡
# --------------------------------------------------------------------------- #
def test_adding_the_decision_puts_one_card_on_the_canvas_with_its_tree_open(window):
    assert _card(window) is not None
    assert window.pipeline.tree_collapsed() is False, "加進來就要看得到樹"
    assert any(isinstance(it, tree_scene._DiamondItem)
               for it in window.pipeline.decision_items())
    # 再加一次不會生第二張（一份 recipe 判一次，`duplicate-decision`）。
    window.add_decision()
    cards = [n for n in window.model.node_order
             if window.model.nodes[n].step == "decision"]
    assert len(cards) == 1


def test_the_library_lists_the_real_card_not_a_pseudo_entry(window):
    """`__score__` 那張偽卡拿掉了 —— 卡片庫裡的 Decision 就是 registry 裡那一張。"""
    keys = window.library.step_keys()
    assert "decision" in keys
    assert "__score__" not in keys


def test_clicking_the_card_opens_the_decision_panel(window):
    window.select_node(window.model.decision_node())
    assert window.stack.currentWidget() is window.score_pane
    # 換一張卡，又是參數表單。
    window.select_node(window.model.node_order[0])
    assert window.stack.currentWidget() is window.param_form


def test_double_clicking_the_card_folds_the_tree(window):
    nid = window.model.decision_node()
    before = window.pipeline.tree_collapsed()
    window._on_node_activated(nid)
    assert window.pipeline.tree_collapsed() is not before
    window._on_node_activated(nid)
    assert window.pipeline.tree_collapsed() is before


# --------------------------------------------------------------------------- #
# 拖
# --------------------------------------------------------------------------- #
def test_dragging_the_card_moves_the_tree_as_one_block(window):
    view = window.pipeline
    before = [QPointF(it.pos()) for it in view.decision_items()]
    card = _card(window)
    card.setPos(card.pos() + QPointF(120.0, -40.0))
    after = [it.pos() for it in view.decision_items()]
    assert before and len(before) == len(after)
    for a, b in zip(before, after):
        assert b.x() - a.x() == pytest.approx(120.0)
        assert b.y() - a.y() == pytest.approx(-40.0)


def test_dragging_the_card_does_not_touch_the_recipe_or_the_tree(window):
    """位置是 session 狀態，**不寫進 recipe** —— 動的是座標，不是樹。"""
    m = window.model
    before = m.to_recipe().to_json_dict()
    dirty_before = m.dirty
    card = _card(window)
    card.setPos(card.pos() + QPointF(75.0, 15.0))
    assert m.to_recipe().to_json_dict() == before
    assert m.dirty == dirty_before


def test_tidy_up_puts_the_tree_back_under_the_card(window):
    """`Tidy up` 把卡排回去，樹跟著它（根對齊 Decision 卡的中線）。"""
    view = window.pipeline
    card = _card(window)
    card.setPos(card.pos() + QPointF(200.0, 120.0))
    view.tidy()                 # 視窗沒顯示 → 不演動畫，直接到終點
    card = _card(window)
    root = min((it for it in view.decision_items()
                if isinstance(it, tree_scene._DiamondItem)),
               key=lambda it: (it.pos().y(), it.pos().x()))
    centre = root.pos().x() + tree_scene._DIA_W / 2.0
    assert centre == pytest.approx(card.pos().x() + studio_mod.NODE_W / 2.0)


# --------------------------------------------------------------------------- #
# 刪
# --------------------------------------------------------------------------- #
def test_removing_asks_first_and_says_how_much_goes(window, monkeypatch):
    """刪卡的重量看起來跟刪一張 Denoise 一樣，而底下掛著整棵樹 —— 要問過。"""
    asked = {}

    def fake(parent, title, text, *a, **kw):
        asked["title"], asked["text"] = title, text
        return QMessageBox.Cancel

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake))
    assert window.remove_decision() is False
    assert window.model.decide is not None, "按了取消卻還是拿掉了"
    assert window.model.decision_node(), "按了取消卡卻不見了"
    assert "class" in asked["text"], asked
    assert "Undo" in asked["text"], "要講得出反悔的路"


def test_deleting_the_card_on_the_canvas_asks_too(window, monkeypatch):
    """畫布上的刪除（Delete 鍵、卡片的 ✕）跟 `remove_decision` 走同一條路。"""
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **kw: asked.append(1) or QMessageBox.Cancel))
    window._on_remove_requested(window.model.decision_node())
    assert asked == [1]
    assert window.model.decide is not None and window.model.decision_node()


def test_removing_takes_the_whole_decision_off_the_canvas(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **kw: QMessageBox.Yes))
    assert window.model.decide is not None
    assert window.remove_decision() is True
    assert window.model.decide is None
    assert window.model.decision_node() == ""
    for view in window._canvases():
        assert view.decision_items() == [], "model 拿掉了，畫布上還有東西"


def test_removing_is_one_undo_step(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **kw: QMessageBox.Yes))
    tree = window.model.decide.tree
    window.remove_decision()
    assert window.model.decide is None
    window.model.undo()
    assert window.model.decide is not None
    assert window.model.decide.tree == tree
    assert window.model.decision_node(), "復原回來的判定沒有它的卡"


def test_removing_when_there_is_nothing_to_remove_is_a_no_op(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.model.decide is None
        assert win.remove_decision() is False
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 內容與卡同生同滅（model 那一層）
# --------------------------------------------------------------------------- #
def test_turning_the_decision_on_and_off_brings_the_card_along(qapp):
    from d4t.ui.viewmodel import RecipeModel

    m = RecipeModel()
    m.add_step("load_patch")
    m.use_decide(True)
    assert m.decide is not None and m.decision_node()
    m.use_decide(False)
    assert m.decide is None and m.decision_node() == ""
    m.undo()
    assert m.decide is not None and m.decision_node(), "一步復原兩件一起回來"


def test_every_route_shares_the_one_card(qapp):
    """一份 recipe 判一次：在第二條 route 上加 Decision，排進來的是**同一張**卡，
    不是第二張（那是 `duplicate-decision`）；刪掉它，每一條 route 上都不見。"""
    from d4t.core.pipeline import Recipe, RecipeNode, ScoreSpec
    from d4t.ui.viewmodel import RecipeModel

    recipe = Recipe(recipe_id="two", routes={"ebi_patch": ["a"], "rsem": ["b"]},
                    nodes={"a": RecipeNode("a", "load_patch", {}),
                           "b": RecipeNode("b", "load_patch", {})},
                    score=ScoreSpec(expr="", threshold=0.0, bins={}))
    m = RecipeModel.from_recipe(recipe, kind="ebi_patch")
    first = m.add_step("decision")
    other = RecipeModel.from_recipe(m.to_recipe(), kind="rsem")
    assert other.decide is not None
    assert other.add_step("decision") == first
    r = other.to_recipe()
    assert [n for n, x in r.nodes.items() if x.step == "decision"] == [first]
    assert all(first in order for order in r.routes.values())
    assert not [i for i in other.validate() if i.code == "duplicate-decision"]

    other.remove(first)
    r = other.to_recipe()
    assert r.decide is None
    assert not any(first in order for order in r.routes.values())
    assert first not in r.nodes


def test_removing_leaves_no_editor_for_a_decision_that_is_gone(window, monkeypatch):
    """刪卡之前右邊開著判定樹的某一步 —— 刪完不准還停在那個面板上。"""
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **kw: QMessageBox.Yes))
    assert window.stack.currentWidget() is window.tree_pane, "前提：正在編第一題"
    window.remove_decision()
    assert window.stack.currentWidget() is window.param_form
