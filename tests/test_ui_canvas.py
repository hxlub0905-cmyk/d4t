# F7-6 驗收：節點畫布（n8n 式）取代直線清單。
"""畫布是純 UI —— 引擎那邊一行都沒動。

``core`` 從 F0 起就是 DAG：``Recipe.edges`` 早就存在、``execution_order()``
早就是 Kahn 拓撲排序 + 循環偵測。所以這裡驗的是 UI 有沒有把那個能力接出來，
以及**循環有沒有被擋在使用者拉線的當下**（而不是等執行時才爆）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "recipes" \
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
    return generate(str(tmp_path_factory.mktemp("f7_canvas")), n=6, seed=7)


@pytest.fixture
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lot["klarf"], sync=True)
    win.load_recipe_path(str(EXAMPLE), sync=True)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 自動排版
# --------------------------------------------------------------------------- #
def test_layout_is_a_straight_line_when_nothing_is_connected(qapp):
    """還沒拉線時每個節點深度都是 0 —— 不可以全部疊在同一欄。"""
    pos = canvas_mod.layout_columns(["a", "b", "c"], [])
    assert [pos[n] for n in ("a", "b", "c")] == [(0, 0), (1, 0), (2, 0)]


def test_layout_puts_each_node_at_its_topological_depth(qapp):
    pos = canvas_mod.layout_columns(
        ["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert pos["a"][0] == 0
    assert pos["b"][0] == pos["c"][0] == 1      # 兩條平行分支同欄
    assert pos["b"][1] != pos["c"][1]           # 但不同列，不會疊在一起
    assert pos["d"][0] == 2                     # 走最長路徑，不是最短


# --------------------------------------------------------------------------- #
# 2. 畫布反映 model
# --------------------------------------------------------------------------- #
def test_canvas_shows_every_node_of_the_recipe(window):
    assert window.pipeline.node_ids() == window.model.node_order
    assert len(window.pipeline.node_ids()) > 3
    assert window.pipeline.card("snr") is not None


def test_selecting_a_node_on_the_canvas_drives_the_param_form(window):
    assert window.select_node("snr") is True
    assert window.pipeline.selected() == "snr"
    assert window.param_form.step_key() == "snr_map"


# --------------------------------------------------------------------------- #
# 3. 連線
# --------------------------------------------------------------------------- #
def test_linking_two_nodes_records_an_edge(window):
    window.pipeline.link_to("load", "norm")
    assert ("load", "norm") in window.model.edges
    assert ("load", "norm") in window.pipeline.edge_pairs()
    assert "Connected" in window.status_text()


def test_a_link_that_would_loop_is_refused_at_draw_time(window):
    """**循環擋在拉線的當下**，不是等到執行時才爆。"""
    window.pipeline.link_to("load", "norm")
    window.pipeline.link_to("norm", "sub")
    before = list(window.model.edges)

    window.pipeline.link_to("sub", "load")        # 會成環
    assert window.model.edges == before, "成環的線不可以落進 model"
    assert "loop" in window.status_text()

    # 而且流程仍然跑得動 —— 沒有被那次嘗試弄壞
    assert window.run_trial(6, workers=1, sync=True) is True


def test_duplicate_and_self_links_are_ignored(window):
    window.pipeline.link_to("load", "norm")
    n = len(window.model.edges)
    window.pipeline.link_to("load", "norm")         # 重複
    window.pipeline.link_to("load", "load")         # 自迴圈
    assert len(window.model.edges) == n


def test_removing_an_edge_puts_it_back(window):
    window.pipeline.link_to("load", "norm")
    assert ("load", "norm") in window.model.edges
    window.pipeline.edge_removed.emit("load", "norm")
    assert ("load", "norm") not in window.model.edges
    assert "Disconnected" in window.status_text()


def test_edges_reorder_execution_and_survive_a_save_load_round_trip(window, tmp_path):
    """連線要真的影響執行順序，而且存檔再載回來還在。"""
    from adept.core.pipeline import Recipe

    window.pipeline.link_to("load", "norm")
    window.pipeline.link_to("norm", "sub")
    edges = list(window.model.edges)
    order = list(window.model.node_order)
    assert order.index("load") < order.index("norm") < order.index("sub")

    out = tmp_path / "wired.json"
    assert window.save_recipe_path(str(out)) is True
    loaded = Recipe.load(str(out))
    assert [tuple(e) for e in loaded.edges] == edges

    assert window.load_recipe_path(str(out), sync=True) is True
    assert window.model.edges == edges
    assert window.pipeline.edge_pairs() == edges


# --------------------------------------------------------------------------- #
# 4. 畫布不擋住既有的動線
# --------------------------------------------------------------------------- #
def test_adding_a_card_from_the_library_lands_on_the_canvas(window):
    before = len(window.pipeline.node_ids())
    window.library.entry("invert").add_button.click()
    assert len(window.pipeline.node_ids()) == before + 1
    assert window.pipeline.node_ids()[-1] in window.model.nodes


# --------------------------------------------------------------------------- #
# 5. 節點卡的外觀（F7-8）
# --------------------------------------------------------------------------- #
def test_long_text_is_elided_not_chopped_in_half(qapp):
    """硬切在字的中間看起來像畫面壞掉，而且 ``source=diff · metri`` 這種殘句
    會讓人以為參數值真的是那樣。"""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    img = QImage(200, 40, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    drawn = []
    p.drawText = lambda rect, flags, text: drawn.append(text)   # 攔下真正畫的字
    canvas_mod._draw_elided(p, QRectF(0, 0, 40, 14),
                            "a very long parameter summary indeed")
    canvas_mod._draw_elided(p, QRectF(0, 0, 180, 14), "short")
    p.end()

    assert drawn[0] != "a very long parameter summary indeed"
    assert drawn[0].endswith("…")
    assert drawn[1] == "short", "放得下的字不可以被動到"


def test_every_node_paints_without_raising(window):
    """``paint()`` 裡的例外被 Qt 吞掉只印到 stderr —— 測試不跑一次就看不到。

    順便涵蓋停用節點（虛線框）與被選取節點（粗框）兩條分支。
    """
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter

    window.pipeline.link_to("load", "sub")
    window._on_node_toggled("cd", False)
    assert window.select_node("sub") is True

    scene = window.pipeline._scene
    rect = scene.itemsBoundingRect()
    assert rect.width() > 0 and rect.height() > 0
    img = QImage(int(rect.width()) + 8, int(rect.height()) + 8,
                 QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    scene.render(p, QRectF(img.rect()), rect, Qt.KeepAspectRatio)
    p.end()

    # 真的畫出了東西（不是一張空的透明圖）
    assert any(img.pixelColor(x, y).alpha() > 0
               for x in range(0, img.width(), 7)
               for y in range(0, img.height(), 7))


def test_canvas_repaints_on_a_theme_switch(window):
    """節點卡是自繪的，顏色在 paint() 時才取 —— 換膚不需要重建畫布。"""
    try:
        assert window.toggle_theme() == "dark"
        assert window.pipeline.node_ids() == window.model.node_order
    finally:
        window.set_theme("light")
