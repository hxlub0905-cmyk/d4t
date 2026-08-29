# -*- coding: utf-8 -*-
"""F56：**一張卡有線的時候，它排在哪裡由那條線決定，不由 route 的排列。**

自動排版除了使用者拉的線，還會補一條「route 裡前後相鄰」的隱含順序
（`PipelineCanvas.set_nodes` 的 `_implicit`）。那件事本身是對的，而寫在
`canvas.py` 上的理由只有一句：

    **沒有線的卡片**，執行順序就是 route 的排列。

問題是那一行以前沒有把那五個字當真 —— 它只問「這一對在不在 `_pairs` 裡」，
而該問的是「**下游那張卡**有沒有真正的入線」。

2026-08-28 使用者帶了一份 recipe 進來，route 排成
``… → glv_stats → focus_quality → output_report``，而 `focus_quality` 真正的
來源是前面的 `denoise`。多出來的那條 ``glv_stats → focus_quality`` 把它推到
深度 4；`WRAP` 是 4，於是它換行落回**第 0 欄** —— 也就是它來源的**左邊**。
畫面上那條線因此由右往左畫。

**在一張由左往右讀的畫布上，那讀起來是「它先跑」。** `docs/PITFALLS.md` 上
「Region 卡排在量測卡右邊，量測卡先跑」那一條記的是同一種誤讀造成的真 bug ——
差別只在那一次錯的是引擎，這一次錯的是畫面。

⚠ 這一支**不是**在測 `layout_columns`（那支拿到什麼算什麼，一直是對的）。
它測的是 `set_nodes` **餵給它什麼**。第一次查這個現象的時候直接呼叫
`layout_columns` 得到了正確答案，於是差點下結論說沒事 —— 錯在測錯了那一層。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")


def _import_qt(g):
    from PySide6.QtWidgets import QApplication
    from d4t.ui import canvas as canvas_mod
    g.update(QApplication=QApplication, canvas_mod=canvas_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    yield app


def _node(nid, reads=(), writes=()):
    return {"node_id": nid, "label": nid, "group": "algo", "enabled": True,
            "summary": "", "reads": list(reads), "writes": list(writes)}


def _columns(canvas):
    """每張卡在第幾欄（x / 欄距），四捨五入到整數。"""
    col_w = canvas_mod.NODE_W + canvas_mod.COL_GAP
    return {nid: round(item.pos().x() / col_w)
            for nid, item in canvas._items.items()}


def _canvas(order, pairs, wrap: int = 4):
    """一張**換行點固定**的畫布。

    ⚠ 換行點跟著 viewport 的實際寬度走（`wrap_for_width`，F13-1），而一個
    還沒被 layout 過的 widget 很窄 —— 實測 `wrap()` 回 2，而 `resize()` 在
    沒 show 過的 widget 上不會傳到 viewport。所以這裡把它釘成 4，也就是
    **使用者那台機器上量到的值**。

    釘的只有這一個「畫面有多寬」的常數，`set_nodes` 其餘每一行都照跑 ——
    這一支要問的是它**餵給 `layout_columns` 什麼**，不是視窗多寬。
    """
    c = canvas_mod.PipelineCanvas()
    c.wrap = lambda: int(wrap)                 # noqa: E731 - 釘住畫面寬度
    c.set_nodes([_node(n, reads=["x"], writes=["x"]) for n in order], pairs)
    assert c._laid_wrap == wrap
    return c


# --------------------------------------------------------------------------- #
# 1. 使用者那份 recipe 的形狀
# --------------------------------------------------------------------------- #
def test_a_wired_card_is_never_placed_left_of_its_own_source(qapp):
    """深度 4 換行落回第 0 欄 —— 而它的來源在第 1 欄。"""
    c = _canvas(["load", "den", "roi", "glv", "focus", "report"],
                [("load", "den"), ("den", "roi"), ("den", "glv"),
                 ("roi", "glv"), ("den", "focus")])
    col = _columns(c)
    assert col["focus"] > col["den"], (
        "focus 被排在它來源的左邊了：%r" % col)
    # 它的深度只由那條線決定：den 是第 1 欄 → focus 是第 2 欄
    assert col["focus"] == col["den"] + 1 == 2
    assert col["load"] == 0 and col["glv"] == 3


def test_the_route_order_still_places_a_card_with_no_wire(qapp):
    """**反向**：沒有線的卡片，route 的排列仍然是唯一的線索。

    這一條是那個修法的邊界 —— 修過頭的話（例如乾脆不補隱含順序）所有沒接線
    的卡片會全部疊在第 0 欄，而那正是 `layout_columns` 的退化情況本來就要
    避免的事。
    """
    c = _canvas(["load", "den", "report"],
                [("load", "den")])            # report 一條線都沒有
    col = _columns(c)
    assert col["report"] == col["den"] + 1, col


def test_a_chain_with_no_wires_at_all_still_reads_left_to_right(qapp):
    c = _canvas(["a", "b", "c"], [])
    assert _columns(c) == {"a": 0, "b": 1, "c": 2}


# --------------------------------------------------------------------------- #
# 2. 隱含順序這張表本身
# --------------------------------------------------------------------------- #
def test_the_implicit_chain_skips_a_card_that_already_has_a_line(qapp):
    """直接鎖 `_implicit` 的內容 —— 上面那條測的是後果，這條測的是原因。"""
    c = _canvas(["load", "den", "glv", "focus", "report"],
                [("load", "den"), ("den", "glv"), ("den", "focus")])
    assert ("glv", "focus") not in c._implicit      # focus 有線
    assert ("focus", "report") in c._implicit       # report 沒有


def test_a_region_line_counts_as_a_line(qapp):
    """區域線也住在 `recipe.edges` 裡（F42），所以它也算「有線」。"""
    c = _canvas(["load", "roi", "mid", "glv"],
                [("load", "roi"), ("load", "mid"), ("roi", "glv")])
    assert ("mid", "glv") not in c._implicit
