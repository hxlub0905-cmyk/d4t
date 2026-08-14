# F7-10 驗收（2026-08-14 改版）：route 的隱含順序**不再畫成線**。
"""F7-10 畫了金色虛線表達 route 順序；使用者實測半個月後退掉它：「會混淆」。

退掉的只有**畫**這件事：引擎的依賴仍是「route 相鄰對 ∪ 顯式 edges」、
排版仍照隱含順序分欄（卡片的排列本身就表達順序，左→右、上→下）。
F7-10 當年擔心的「沒有線以為互不相干」由現在的預設行為緩解：從卡片庫加卡
與拖放都會建**顯式**連線，新做的 recipe 天生有線。這一檔改鎖新行為。
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


def _edges(canvas):
    return list(canvas._edges)


def test_route_order_is_not_painted_as_lines(window):
    """範例 recipe 一條線都沒拉 → 畫布上**零條線**（虛線退役），
    但排版仍照順序分欄 —— 卡片的排列本身就是順序。"""
    assert window.model.edges == [], "前提：這份 recipe 沒有顯式 edges"
    assert window.pipeline._edges == [], "route 順序不該畫成任何線"
    # 排版仍照隱含順序：不是全部疊在第 0 欄
    xs = {round(window.pipeline.card(nid).pos().x())
          for nid in window.pipeline.node_ids()}
    assert len(xs) > 1, "排版沒有吃隱含順序 —— 卡片全疊在同一欄"


def test_drawing_the_link_yourself_makes_a_solid_line(window):
    """使用者自己拉的線照樣是實線，而且只有一條。"""
    a, b = window.model.node_order[0], window.model.node_order[1]
    window.pipeline.link_to(a, b)

    assert (a, b) in window.model.edges
    pairs = [e.pair() for e in window.pipeline._edges]
    assert pairs.count((a, b)) >= 1


def test_edge_pairs_still_reports_only_the_users_own_links(window):
    """存檔寫的是使用者拉的線。route 順序不進 edges（也不再畫）。"""
    assert window.pipeline.edge_pairs() == window.model.edges == []
    window.pipeline.link_to(window.model.node_order[0],
                            window.model.node_order[2])
    assert window.pipeline.edge_pairs() == window.model.edges


def test_a_long_chain_wraps_instead_of_running_off_the_screen(window):
    """隱含順序讓每一份 recipe 都有依賴（就算不畫），換行必須對深度排版成立
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
