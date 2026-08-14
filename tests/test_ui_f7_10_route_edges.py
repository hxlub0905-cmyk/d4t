# F7-10 驗收：畫布要畫出 route 的隱含順序。
"""**畫布上沒有線，不代表沒有連接。**

引擎的依賴是「route 相鄰對 ∪ 顯式 edges」（``recipe.execution_order``），
但畫布以前只畫顯式 edges。於是載入一份沒拉過線的 recipe，使用者看到的是
九張互不相干的卡 —— 而它其實是照順序跑的。他只會得到兩種結論，兩種都是錯的：
以為要自己連起來才會跑，或以為沒連線的卡不會執行。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "recipes" \
    / "die_to_die_basic.json"


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import canvas as canvas_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f7_10")), n=6, seed=13)


@pytest.fixture
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lot["klarf"], sync=True)
    win.load_recipe_path(str(EXAMPLE), sync=True)
    yield win
    win.close()


def _edges(canvas, implicit):
    return [e for e in canvas._edges if e.implicit is implicit]


def test_a_recipe_with_no_explicit_links_still_shows_how_data_flows(window):
    """範例 recipe 一條線都沒拉，但它是一條鏈 —— 畫布要看得出來。"""
    assert window.model.edges == [], "前提：這份 recipe 沒有顯式 edges"
    n = len(window.model.node_order)

    implicit = _edges(window.pipeline, True)
    assert implicit, "沒有畫出任何隱含連線 —— 使用者會以為卡片互不相干"
    pairs = {e.pair() for e in implicit}
    expected = set(zip(window.model.node_order, window.model.node_order[1:]))
    assert pairs == expected


def test_the_implicit_order_matches_what_the_engine_actually_does(window):
    """畫的東西必須是引擎真的依據的東西，不是另一套說法。"""
    from adept.core.pipeline import execution_order

    order = execution_order(window.model.to_recipe(), window.model.kind)
    drawn = {e.pair() for e in _edges(window.pipeline, True)}
    drawn |= {e.pair() for e in _edges(window.pipeline, False)}
    for a, b in zip(order, order[1:]):
        assert (a, b) in drawn, "引擎認為 %s → %s，畫布上卻沒有這條線" % (a, b)


def test_implicit_links_look_different_and_cannot_be_deleted(window):
    """隱含順序來自卡片的排列。刪掉它在語意上等於「把卡片從流程裡拿掉」——
    那是另一個動作，不該用同一個 Delete 鍵完成。"""
    from PySide6.QtWidgets import QGraphicsItem

    for e in _edges(window.pipeline, True):
        assert not e.flags() & QGraphicsItem.ItemIsSelectable
        assert "order of the cards" in e.toolTip()
    for e in _edges(window.pipeline, False):
        assert e.flags() & QGraphicsItem.ItemIsSelectable


def test_drawing_the_link_yourself_turns_it_into_a_real_one(window):
    """使用者把隱含的那條連起來 → 變成實線，而且不會畫成兩條。"""
    a, b = window.model.node_order[0], window.model.node_order[1]
    window.pipeline.link_to(a, b)

    assert (a, b) in window.model.edges
    assert (a, b) in {e.pair() for e in _edges(window.pipeline, False)}
    assert (a, b) not in {e.pair() for e in _edges(window.pipeline, True)}, \
        "同一對節點不可以同時有實線與虛線"


def test_edge_pairs_still_reports_only_the_users_own_links(window):
    """存檔寫的是使用者拉的線。隱含順序來自 route，存進 edges 會重複記錄。"""
    assert window.pipeline.edge_pairs() == window.model.edges == []
    window.pipeline.link_to(window.model.node_order[0],
                            window.model.node_order[2])
    assert window.pipeline.edge_pairs() == window.model.edges


def test_a_long_chain_wraps_instead_of_running_off_the_screen(window):
    """隱含連線讓每一份 recipe 都有依賴，所以換行必須對深度排版也成立
    （不然九張卡又會排成一條 2500px 的橫列）。"""
    cols = set()
    for nid in window.pipeline.node_ids():
        item = window.pipeline.card(nid)
        cols.add(round(item.pos().x() / (canvas_mod.NODE_W + canvas_mod.COL_GAP)))
    assert max(cols) < canvas_mod.WRAP
    assert len(window.pipeline.node_ids()) > canvas_mod.WRAP, "前提：卡片數超過一行"


def test_a_single_card_has_no_dangling_link(window):
    """只有一張起手卡的時候不可以畫出「連到自己」之類的東西。"""
    canvas = canvas_mod.PipelineCanvas()
    canvas.set_nodes([{"node_id": "load", "label": "Load images",
                       "group": "input", "enabled": True, "summary": "",
                       "reads": [], "writes": ["test", "ref"]}], [])
    assert canvas._edges == []
