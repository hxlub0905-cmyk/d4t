# ADC 判定區：在原畫布上拖得動、也拿得掉（2026-08-25）。
"""使用者：「ADC 也要能在原畫布上拖曳 移除」。

以前判定區的圖元**全部唯讀**（`tree_scene` 的檔頭寫著「不可拖、不可刪」）：
理由是「樹是一個結構，不是幾張散卡」—— 那句話**仍然成立**，所以這一輪加的
不是「每個菱形各自拖」，而是：

* **整區當一個東西拖**，把手是外框（不是裡面任何一張卡）；
* 右上角一顆 ✕ ＝ 拿掉整個判定，而且**先問過**。

兩條不變量沒有動：
* 拖它**不改 recipe**（位置跟卡片的位置一樣是 session 狀態）；
* 拖它**不改樹的形狀**（動的只有畫布座標）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
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


def _zone(win):
    """判定區的外框（那個把手）。"""
    for view in win._canvases():
        for it in view.decision_items():
            if isinstance(it, tree_scene._ZoneItem):
                return view, it
    raise AssertionError("畫布上沒有判定區的外框")


# --------------------------------------------------------------------------- #
# 拖
# --------------------------------------------------------------------------- #
def test_the_zone_moves_as_one_block(window):
    """拖外框 → **整區**跟著走，相對位置一格都不變。

    一個一個拖的話畫面會長出樹上沒有的形狀（兩個菱形疊在一起、葉子跑到根的
    上面）—— 而畫布的職責正是「這棵樹長什麼樣」。
    """
    view, zone = _zone(window)
    before = [it.pos() for it in view.decision_items()]
    view.move_decision_by(120.0, -40.0)
    after = [it.pos() for it in view.decision_items()]

    assert len(before) == len(after) and before
    for a, b in zip(before, after):
        # 浮點數：`moveBy` 是加法，位置本身是任意的小數。
        assert b.x() - a.x() == pytest.approx(120.0)
        assert b.y() - a.y() == pytest.approx(-40.0)


def test_dragging_survives_a_rebuild(window):
    """重建之後還在原地 —— 否則試跑一次（每次都重建）就跳回去。"""
    view, _ = _zone(window)
    view.move_decision_by(90.0, 30.0)
    assert view.decision_offset() == QPointF(90.0, 30.0)

    view._rebuild_decision()
    assert view.decision_offset() == QPointF(90.0, 30.0)
    _, zone2 = _zone(window)
    assert zone2 is not None


def test_dragging_the_zone_does_not_touch_the_recipe(window):
    """位置是 session 狀態，**不寫進 recipe** —— 跟卡片的位置同一個待遇。

    寫進去的話：拖一下畫面就變成「檔案髒了」，而且它會佔一格復原。
    """
    m = window.model
    before = m.to_recipe().to_json_dict()
    dirty_before = m.dirty
    view, _ = _zone(window)
    view.move_decision_by(75.0, 15.0)
    assert m.to_recipe().to_json_dict() == before
    assert m.dirty == dirty_before


def test_dragging_the_zone_does_not_reshape_the_tree(window):
    """動的是座標，不是樹。"""
    m = window.model
    before = m.decide.tree
    view, _ = _zone(window)
    view.move_decision_by(-60.0, 200.0)
    assert m.decide.tree == before


def test_tidy_up_puts_the_zone_back_too(window):
    """`Tidy up` 把卡片排回去 —— 判定區也是拖得動的東西，一起排。

    只排一半的整理，下一次還是得自己搬。
    """
    view, _ = _zone(window)
    view.move_decision_by(200.0, 120.0)
    assert view.decision_offset() != QPointF(0.0, 0.0)
    view.tidy()
    assert view.decision_offset() == QPointF(0.0, 0.0)


# --------------------------------------------------------------------------- #
# 移除
# --------------------------------------------------------------------------- #
def test_the_zone_has_a_close_button_only_when_someone_can_catch_it(qapp):
    """畫一顆按不動的鈕比沒有那顆鈕更糟 —— 沒有 canvas 就不畫 ✕。"""
    from PySide6.QtCore import QRectF

    lonely = tree_scene._ZoneItem(QRectF(0, 0, 300, 200))
    assert lonely._canvas is None
    assert lonely.acceptHoverEvents() is False


def test_removing_asks_first_and_says_how_much_goes(window, monkeypatch):
    """一顆 ✕ 的重量看起來跟刪一張卡一樣，而底下掛著整棵樹 —— 要問過。"""
    asked = {}

    def fake(parent, title, text, *a, **kw):
        asked["title"], asked["text"] = title, text
        return QMessageBox.Cancel

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake))
    assert window.remove_decision() is False
    assert window.model.decide is not None, "按了取消卻還是拿掉了"
    assert "class" in asked["text"], asked
    assert "Undo" in asked["text"], "要講得出反悔的路"


def test_removing_takes_the_whole_decision_off_the_canvas(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **kw: QMessageBox.Yes))
    assert window.model.decide is not None
    assert window.remove_decision() is True
    assert window.model.decide is None
    for view in window._canvases():
        assert view.decision_items() == [], "model 拿掉了，畫布上還有東西"


def test_removing_is_undoable(window, monkeypatch):
    """`use_decide` 自己會 `_push_undo` —— 這一條確認那條路沒有被繞過。"""
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **kw: QMessageBox.Yes))
    tree = window.model.decide.tree
    window.remove_decision()
    assert window.model.decide is None
    window.model.undo()
    assert window.model.decide is not None
    assert window.model.decide.tree == tree


def test_removing_when_there_is_nothing_to_remove_is_a_no_op(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.model.decide is None
        assert win.remove_decision() is False
    finally:
        win.close()
