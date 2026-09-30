# F124 期 4：線丟在卡上就好（2026-09-30）。
"""拉線只有一個動作：從卡右邊的名字拖出來，丟到要用它的卡上（`ui/link_drop.py`）。

* 丟在埠上 → 接那一顆；
* 丟在卡上、只有一格接得上 → 直接接；
* 兩格以上 → 問（`link_drop.CHOOSE` 在這裡代替使用者挑），取消＝不接；
* 單一格已經有線 → 選單上寫明會取代哪一條。

⚠ 以前丟在卡上沒丟準埠會**安靜地挑高度最近的那一格** —— 丟在 Compare 偏上面
就接 a、偏下面就接 b。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.ui import canvas as canvas_mod, link_drop  # noqa: E402
from d4t.ui import studio as studio_mod, theme as theme_mod  # noqa: E402

RECIPE = REPO / "recipes" / "ebi-die-to-die.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    assert win.load_recipe_path(str(RECIPE), sync=True)
    try:
        yield win
    finally:
        win.close()


@pytest.fixture()
def asked(monkeypatch):
    """代替使用者挑：記下每一次被問了什麼，回 ``answer`` 那一格。"""
    calls = []
    box = {"answer": None}

    def choose(title, options):
        calls.append((title, options))
        return box["answer"]

    monkeypatch.setattr(link_drop, "ASK", True)
    monkeypatch.setattr(link_drop, "CHOOSE", choose)
    return calls, box


def _drop(window, src, port_name, dst, at=None):
    view = window.pipeline
    item = view.node_item(src)
    view.begin_link(item, item.port_names().index(port_name))
    target = view.node_item(dst)
    pos = at or (target.scenePos()
                 + QPointF(canvas_mod.NODE_W / 2.0, target.height() / 2.0))
    view._drop_link(pos)


def _into(window, dst):
    return [(e.src, e.src_out, e.dst_in) for e in window.model.edges
            if e.dst == dst]


def test_one_slot_connects_without_asking(window, asked):
    calls, _box = asked
    tone = window.model.add_step("tone")
    window._refresh_pipeline()
    _drop(window, "dn", "diff", tone)
    assert ("dn", "diff", "streams") in _into(window, tone)
    assert calls == [], "只有一格接得上 —— 不該問"


def test_two_slots_ask_which_one(window, asked):
    calls, box = asked
    sub = window.model.add_step("subtract")
    window._refresh_pipeline()
    box["answer"] = "b"
    _drop(window, "dn", "diff", sub)
    title, options = calls[0]
    assert "diff" in title
    assert [n for n, _t in options] == ["a", "b"]
    assert [t for _n, t in options] == ["First stream", "Second stream"]
    assert ("dn", "diff", "b") in _into(window, sub), "接的是使用者挑的那一格"


def test_cancelling_the_menu_draws_nothing(window, asked):
    _calls, box = asked
    sub = window.model.add_step("subtract")
    window._refresh_pipeline()
    box["answer"] = None
    _drop(window, "dn", "diff", sub)
    assert _into(window, sub) == []


def test_the_menu_says_which_line_it_would_replace(window, asked):
    calls, box = asked
    box["answer"] = None                       # 看一眼就好，不接（會成環）
    _drop(window, "dn", "diff", "sub")
    texts = [t for _n, t in calls[0][1]]
    assert any("replaces the line from “Normalize”" in t for t in texts), texts


def test_a_line_dropped_on_a_port_goes_to_that_port(window, asked):
    calls, _box = asked
    view = window.pipeline
    sub = view.node_item("sub")
    at = sub.in_anchors()[1]                   # b 那一顆
    assert link_drop.drop_param(view, sub, "image", "diff", at) == "b"
    assert calls == []


def test_without_the_menu_it_falls_back_to_the_nearest_slot(window, monkeypatch):
    """headless 測試的退路（`tests/conftest.py` 把 ASK 關掉）：F124 之前的行為。"""
    monkeypatch.setattr(link_drop, "ASK", False)
    monkeypatch.setattr(link_drop, "CHOOSE", None)
    view = window.pipeline
    sub = view.node_item("sub")
    at = sub.scenePos() + QPointF(canvas_mod.NODE_W / 2.0, sub.height() / 2.0)
    assert link_drop.drop_param(view, sub, "image", "diff", at) == \
        sub.in_param_at(sub.mapFromScene(at), "image")
