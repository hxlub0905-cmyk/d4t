# F99 P1-1／P1-5／P1-8：畫布上三件 n8n 使用者反射動作會做的事 — authored 2026-09-08.
"""2026-09-08 的外部評審：兩個死掉的手勢（空白處右鍵、把線拖到空白處）、
跑完一批畫布跟跑之前一模一樣、有 undo 卻沒有 copy。

三件事的**內容**各住在自己的地方（`ui/card_menu.py`、`canvas.run_status_from`、
`edit_plan.copyable_params`），Studio 只接線 —— 所以這裡先問純函式，再開一次
視窗問接線。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from conftest import first_source  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    from d4t.ui.studio import StudioWindow
    win = StudioWindow(show_welcome_on_start=False)
    # ⚠ conftest 那支 autouse 只在 `d4t.ui.studio` **已經** import 的時候關掉
    # 關窗時的「要不要存」對話框；這裡是在 fixture 裡才 import，來不及 ——
    # 於是一條失敗的測試在 teardown 停在一個 modal 上，faulthandler 都叫不醒
    # （C++ 的 exec 裡 Python 沒有機會跑）。自己關。
    win.PROMPT_ON_CLOSE = False
    win.resize(1200, 800)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# P1-1：加卡的選單
# --------------------------------------------------------------------------- #
def test_the_add_menu_is_grouped_like_the_library():
    from d4t.core.pipeline import list_steps
    from d4t.core.pipeline.step import GROUPS
    from d4t.ui import card_menu
    keys = [s.key for s in list_steps()]
    groups = card_menu.grouped(keys)
    titles = [t for t, _items in groups]
    order = [t for _g, t, _s in GROUPS]
    assert titles == [t for t in order if t in titles], "順序要跟卡片庫一樣"
    assert sum(len(items) for _t, items in groups) == len(keys)
    for _t, items in groups:
        for key, label in items:
            assert key and label


def test_only_cards_that_take_the_wire_are_offered():
    from d4t.core.pipeline import list_steps
    from d4t.ui import card_menu
    keys = [s.key for s in list_steps()]
    images = card_menu.compatible(keys, "image")
    regions = card_menu.compatible(keys, "region")
    assert "denoise" in images and "glv_stats" in images
    assert "load_single" not in images, "入口卡不吃線"
    assert "glv_stats" in regions and "denoise" not in regions
    assert card_menu.input_param_for("denoise", "image")
    assert card_menu.input_param_for("glv_stats", "region") == "roi"
    assert card_menu.input_param_for("denoise", "region") == ""


def test_the_canvas_announces_a_wire_dropped_on_nothing(qapp):
    from PySide6.QtCore import QPointF

    from d4t.ui import canvas as canvas_mod
    c = canvas_mod.PipelineCanvas()
    c.set_nodes([
        {"node_id": "load", "label": "Load images", "group": "input",
         "enabled": True, "summary": "", "reads": [], "writes": ["test", "ref"],
         "produces": ["test", "ref"]},
    ], [])
    got = []
    c.link_dropped.connect(lambda *a: got.append(a))
    c.begin_link(c.node_item("load"), 1)          # 從 ref 那顆埠拉
    c._drop_link(QPointF(900.0, 900.0))           # 放在空白處
    assert got and got[0][:3] == ("load", "image", "ref"), got
    assert c._link_line is None, "拖到一半的那條虛線要收掉"


def test_right_click_on_empty_canvas_asks_for_a_card(qapp):
    from PySide6.QtCore import QPointF

    from d4t.ui import canvas as canvas_mod
    c = canvas_mod.PipelineCanvas()
    c.resize(600, 400)
    c.show()
    qapp.processEvents()
    got = []
    c.add_menu_requested.connect(lambda x, y: got.append((x, y)))
    # 走 mouseReleaseEvent 那條路：右鍵按下（記起點）→ 原地放開。
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent
    pos = QPointF(300.0, 200.0)
    press = QMouseEvent(QEvent.MouseButtonPress, pos, Qt.RightButton,
                        Qt.RightButton, Qt.NoModifier)
    release = QMouseEvent(QEvent.MouseButtonRelease, pos, Qt.RightButton,
                          Qt.NoButton, Qt.NoModifier)
    c.mousePressEvent(press)
    c.mouseReleaseEvent(release)
    assert len(got) == 1, "空白處右鍵要開加卡的選單"


def test_a_wire_dropped_on_nothing_grows_a_connected_card(window, qapp):
    """挑一張之後：卡加在放開的地方、線接上（線是使用者拉的，不是加卡順手接）。"""
    src = first_source(window)
    qapp.processEvents()
    before = set(window.model.node_order)
    from d4t.ui import canvas_edges

    nid = canvas_edges.on_link_dropped(window, src, "image", "test",
                                       640.0, 300.0, pick="denoise")
    qapp.processEvents()
    assert nid and nid not in before
    assert window.model.nodes[nid].step == "denoise"
    assert any(e.src == src and e.dst == nid for e in window.model.edges), \
        "線沒接上：%s" % list(window.model.edges)
    # `place_dropped` 把卡**置中**在放開的那一點（拖放的語意）。
    from d4t.ui.canvas import NODE_H, NODE_W
    item = window.pipeline.node_item(nid)
    cx, cy = item.pos().x() + NODE_W / 2.0, item.pos().y() + NODE_H / 2.0
    assert abs(cx - 640.0) < 30 and abs(cy - 300.0) < 30, (cx, cy)


def test_right_click_add_puts_the_card_where_you_clicked(window, qapp):
    nid = window._on_add_menu(500.0, 260.0, pick="denoise")
    qapp.processEvents()
    assert nid in window.model.nodes
    assert not [e for e in window.model.edges if e.dst == nid], "加卡不接線"


# --------------------------------------------------------------------------- #
# P1-5：跑完一批，卡片上要看得出來
# --------------------------------------------------------------------------- #
def test_run_status_folds_traces_per_card():
    from d4t.ui.canvas import run_status_from, run_text
    results = [
        {"ok": True, "traces": [{"node_id": "load", "ok": True, "ms": 10.0},
                                {"node_id": "glv", "ok": True, "ms": 120.5}]},
        {"ok": False, "traces": [{"node_id": "load", "ok": True, "ms": 12.0},
                                 {"node_id": "glv", "ok": False, "ms": 3.0}]},
    ]
    st = run_status_from(results)
    assert st["load"] == (2, 0, 22.0)
    assert st["glv"] == (1, 1, 123.5)
    # 2026-09-09：總耗時 → 每秒幾顆（使用者：「X img/s 而不是 total time」）
    assert run_text(st["load"]) == "2 ok · 91 img/s"       # 2 顆 / 22 ms
    assert run_text(st["glv"]) == "1 failed", "失敗優先"
    assert run_text(None) == "" and run_text((0, 0, 0.0)) == ""
    assert run_text((24, 0, 340.0)) == "24 ok · 71 img/s"
    assert run_text((3, 0, 1200.0)) == "3 ok · 2.5 img/s", "慢的卡留一位小數"
    assert run_text((5, 0, 0.0)) == "5 ok", "沒量到時間不寫無限大"


def test_the_canvas_keeps_run_status_and_paints_it(qapp):
    from d4t.ui import canvas as canvas_mod
    c = canvas_mod.PipelineCanvas()
    c.set_nodes([
        {"node_id": "load", "label": "Load images", "group": "input",
         "enabled": True, "summary": "", "reads": [], "writes": ["test"],
         "produces": ["test"]},
    ], [])
    c.set_run_status({"load": (24, 0, 340.0)})
    assert c.run_status_of("load") == (24, 0, 340.0)
    c.resize(500, 300)
    c.show()
    qapp.processEvents()
    c.grab()                                # 畫一次不准炸
    c.set_run_status({})
    assert c.run_status_of("load") is None


# --------------------------------------------------------------------------- #
# P1-8：Ctrl+C / Ctrl+V / Ctrl+D
# --------------------------------------------------------------------------- #
def test_a_copy_carries_settings_but_not_wiring():
    from d4t.ui import edit_plan
    got = edit_plan.copyable_params(
        "denoise", {"streams": "test", "method": "median", "k": 5})
    assert "streams" not in got, "接線不帶"
    assert got.get("method") == "median" and got.get("k") == 5
    assert edit_plan.copyable_params("no_such_card", {"a": 1}) == {}


def test_copy_paste_and_duplicate_on_the_window(window, qapp):
    from d4t.ui.studio import StudioWindow
    keys = dict(StudioWindow.SHORTCUTS)
    assert keys["Ctrl+C"] == "copy_cards" and keys["Ctrl+V"] == "paste_cards"
    assert keys["Ctrl+D"] == "duplicate_cards"
    assert {"copy_cards", "paste_cards", "duplicate_cards"} <= \
        set(StudioWindow._WIDGET_SHORTCUTS), "跟 Delete 一樣掛在畫布上"

    src = first_source(window)
    nid = window._on_add_menu(400.0, 200.0, pick="denoise")
    window.model.set_param(nid, "method", "median")
    window.select_node(nid)
    qapp.processEvents()

    assert window.paste_cards() == [], "剪貼簿是空的要講出來，不准炸"
    assert window.copy_cards() == 1
    made = window.paste_cards()
    assert len(made) == 1
    new = window.model.nodes[made[0]]
    assert new.step == "denoise" and new.params.get("method") == "median"
    assert not [e for e in window.model.edges if e.dst == made[0]], "貼上沒有線"
    item, orig = window.pipeline.node_item(made[0]), window.pipeline.node_item(nid)
    assert item.pos().x() > orig.pos().x() and item.pos().y() > orig.pos().y()

    n_before = len(window.model.node_order)
    window.select_node(src)
    dup = window.duplicate_cards()
    assert len(dup) == 1 and len(window.model.node_order) == n_before + 1
    assert window.model.nodes[dup[0]].step == window.model.nodes[src].step
    # 一步復原：貼上的那張整張消失
    assert window.undo() is True
    assert dup[0] not in window.model.nodes


# --------------------------------------------------------------------------- #
# P1-7：選到判定樹的一步，儀表板要說它是誰的
# --------------------------------------------------------------------------- #
def test_the_gauge_pane_says_whose_it_is_when_a_tree_step_is_picked(window, qapp):
    src = first_source(window)
    window.select_node(src)
    assert window.gauge_note.text() == ""
    assert window.bottom_stack.isEnabled()
    assert window.add_decision() is True
    qapp.processEvents()
    window._on_tree_step_clicked("")
    qapp.processEvents()
    assert src in window.gauge_note.text(), window.gauge_note.text()
    assert not window.bottom_stack.isEnabled(), "上一張卡的儀表要淡掉"
    window.select_node(src)
    assert window.gauge_note.text() == "" and window.bottom_stack.isEnabled()
