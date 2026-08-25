# 畫布上的 Output 段（F30 Phase D，2026-08-25）。
"""**這幾張卡跟其他卡不一樣，它們整批只跑一次。**

畫布上其他每一張卡都是「一顆 defect 跑一次」。Output 段那幾張是在**整批跑完
之後**才跑，而且只跑一次（`Step.scale == SCALE_LOT`）。在這之前畫面上沒有任何
東西說得出那件事 —— 它們就是右邊飄著的幾張卡，長得跟 Denoise 一模一樣。

四條規矩，每一條都是一個具體的謊言不准出現：

1. **框裡剛好是那幾張卡**（多框一張別的段的卡，那句「整批跑一次」就變成假的）；
2. **不加埠、不加線** —— 進到這幾張卡的是「整批的結果表」，那不是一條影像流；
3. **沒有 Output 卡就沒有框**（一個框著空氣的虛線框讀起來像「這裡本來有東西」）；
4. **卡片拖走，框跟著走**（留在原地的框框的是一個已經不在那裡的東西）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from d4t.ui import output_band as band_mod  # noqa: E402
from d4t.ui import studio as studio_mod, theme as theme_mod  # noqa: E402

from tests.conftest import first_source  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        yield win
    finally:
        win.close()


def canvas(window):
    return window.pipeline


def add_output(window, key="output_csv"):
    return window.add_card_after(first_source(window), key)


# --------------------------------------------------------------------------- #
# 1. 框裡剛好是那幾張卡
# --------------------------------------------------------------------------- #
def test_the_band_appears_once_there_is_an_output_card(window):
    assert canvas(window).output_items() == []
    add_output(window)
    assert len(canvas(window).output_items()) == 1


def test_the_band_covers_every_output_card(window):
    a = add_output(window, "output_csv")
    b = add_output(window, "output_klarf")
    cv = canvas(window)
    rect = cv.output_items()[0].sceneBoundingRect()
    for nid in (a, b):
        assert rect.contains(band_mod.card_rect(cv.card(nid))), nid


def test_a_stranger_inside_the_frame_means_no_frame_at_all(window):
    """**畫布不能說謊。**

    這個框說的是「裡面這幾張整批只跑一次」。使用者可以把卡片拖到任何地方 ——
    兩張 Output 卡分開擺、中間夾一張 Denoise 的話，外接矩形會把 Denoise 一起
    框進去，而那句話就變成假的。一個消失的框只是少了一個提示，一個說謊的框
    是錯的。
    """
    a = add_output(window, "output_csv")
    b = add_output(window, "output_klarf")
    cv = canvas(window)
    assert cv.output_items(), "前提：兩張擺在一起時本來有框"
    other = window.add_card_after(first_source(window), "denoise")
    # 把 Denoise 搬到那兩張中間
    mid = (cv.card(a).scenePos() + cv.card(b).scenePos()) / 2.0
    cv.card(other).setPos(mid)
    assert cv.output_items() == []
    # 搬走就回來 —— 否則上面那句只證明了「加一張卡框就不見了」
    cv.card(other).setPos(mid + QPointF(0.0, 900.0))
    assert cv.output_items()


def test_which_cards_count_comes_from_the_card_not_a_hardcoded_list(window):
    """加一張新的 Output 卡不必動畫布 —— 判準是卡片自己宣告的 group。"""
    from d4t.core.pipeline.step import list_steps
    keys = [s.key for s in list_steps()
            if str(getattr(s, "group", "")) == "output"]
    assert len(keys) >= 4, keys
    for key in keys:
        add_output(window, key)
    cv = canvas(window)
    inside = cv.output_items()[0].sceneBoundingRect()
    for nid, node in window.model.nodes.items():
        if node.step in keys:
            assert inside.contains(band_mod.card_rect(cv.card(nid))), node.step


# --------------------------------------------------------------------------- #
# 2. 不加埠、不加線
# --------------------------------------------------------------------------- #
def test_the_band_adds_no_edge_and_no_port(window):
    """數字不是一條流 —— 畫一條存起來的線就是說謊（同判定區左緣那一句）。"""
    before_edges = len(window.model.edges)
    before_lines = len(canvas(window)._edges)
    add_output(window)
    assert len(window.model.edges) == before_edges
    assert len(canvas(window)._edges) == before_lines


def test_the_band_is_not_clickable_and_sits_behind_everything(window):
    """框是背景，不是一個可以選到的東西 —— 點它應該點到畫布。"""
    add_output(window)
    item = canvas(window).output_items()[0]
    assert item.zValue() < 0
    assert not item.acceptedMouseButtons()


def test_the_band_says_when_these_cards_run(window):
    """段名畫布上已經有了（顏色與圖示）；**「整批跑完之後跑一次」沒有**。"""
    assert "once per lot" in band_mod.OUTPUT_WHEN.lower()
    assert band_mod.OUTPUT_HINT.strip().endswith("→")


# --------------------------------------------------------------------------- #
# 3. 沒有卡就沒有框
# --------------------------------------------------------------------------- #
def test_no_output_card_means_no_band_at_all(window):
    """空框讀起來像「這裡本來有東西」—— 而正確的答案是「還沒有要寫出任何東西」。"""
    assert band_mod.band_rect([]) is None
    assert canvas(window).output_items() == []


def test_removing_the_last_output_card_takes_the_band_with_it(window):
    nid = add_output(window)
    assert canvas(window).output_items()
    window.model.remove(nid)
    window._refresh_pipeline()
    assert canvas(window).output_items() == []


# --------------------------------------------------------------------------- #
# 4. 卡片拖走，框跟著走
# --------------------------------------------------------------------------- #
def test_dragging_an_output_card_moves_the_band(window):
    nid = add_output(window)
    cv = canvas(window)
    before = cv.output_items()[0].sceneBoundingRect()
    item = cv.card(nid)
    item.setPos(item.pos() + QPointF(320.0, 180.0))
    after = cv.output_items()[0].sceneBoundingRect()
    assert after != before
    assert after.contains(band_mod.card_rect(item))


# --------------------------------------------------------------------------- #
# 5. 內容住在自己的模組（CLAUDE.md §4）
# --------------------------------------------------------------------------- #
def test_the_drawing_lives_in_its_own_module_not_in_studio():
    """一塊新的畫布元件＝一個新模組。`studio.py` 留給接線，不留給內容。

    這一條擋的是最容易發生的那件事：「先塞進 studio.py，之後再拆」——
    而 `studio.py` 已經 5000 多行，那個「之後」從來沒有到過。
    """
    src = (REPO / "d4t" / "ui" / "studio.py").read_text(encoding="utf-8")
    assert "output_band" not in src
    assert band_mod.OUTPUT_WHEN not in src

    canvas_src = (REPO / "d4t" / "ui" / "canvas.py").read_text(encoding="utf-8")
    # 畫布只負責**接線**：算出是哪幾張卡、清舊的、把新的擺進去。
    assert "output_band.build_band" in canvas_src
    assert band_mod.OUTPUT_WHEN not in canvas_src, "那句話住 output_band"
