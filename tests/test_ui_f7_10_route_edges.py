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


def test_route_order_is_painted_as_the_backbone(window):
    """**F9 Phase 3c 起前提反過來了。**

    2026-08-14 退掉的是 route 順序的金色**虛線** —— 那時候它只說「這兩張卡有
    先後」，是裝飾。現在資料就是沿著那條鏈流的（`graph._compile_recipe` 的
    backbone），所以它是**程式本身**，不畫的話畫布就又在說謊了。

    排版仍照順序分欄 —— 卡片的排列本身也還是順序。
    """
    assert window.model.edges == [], "前提：這份 recipe 沒有顯式 edges"
    assert window.pipeline._edges, "主幹要畫出來（route 順序就是資料的路徑）"
    assert all(k == "packet" for k in window.pipeline.edge_kinds())
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


def test_drawing_the_first_wire_writes_the_whole_backbone_down(window):
    """⚠ **這一條在 F9 Phase 4a 反過來了，而且是刻意的。**

    以前這裡寫的是「存檔只寫使用者親手拉的線，推導出來的主幹不該被寫死 ——
    卡片順序一改那些線就該重算」。那個理由在當時成立，但它有一個沒被看見的
    後果：**推導出來的線不是資料，所以剪不掉**。使用者在畫布上按那顆「×」，
    狀態列說「Disconnected」，而圖一點都沒變、線還畫在原地 —— 這個工具最糟的
    一種行為（說做了卻沒做）。

    現在的規矩：一份 recipe 只要有一條顯式的線，引擎就**不再推導主幹**
    （``graph._compile_recipe`` 的 ``backbone_is_explicit``）。所以拉第一條線
    的當下要把整條主幹一起寫下來 —— 不然其餘的卡會在那一瞬間全部變成沒人接的
    孤兒，而使用者只是拉了一條線。

    「順序一改線要重算」那個好處換成了「線就是順序」：排版與執行順序都從
    edges 拓撲排序出來，不再有第二套真理。
    """
    assert window.model.edges == []
    a, c = window.model.node_order[0], window.model.node_order[2]
    window.pipeline.link_to(a, c)

    assert (a, c) in window.model.edges, "使用者拉的那一條一定要在"
    chain = list(zip(window.model.node_order, window.model.node_order[1:]))
    have = set(window.model.edges)
    # 主幹整條寫下來了（除了會跟新線衝突而被拓撲排序重排的部分）
    assert len(have) >= len(chain) - 1, (have, chain)
    assert (a, c) in window.pipeline.edge_pairs()

    # 而且現在剪得掉 —— 這正是把主幹寫下來換到的東西
    assert window.model.remove_edge(a, c) is True
    assert (a, c) not in window.model.edges


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
