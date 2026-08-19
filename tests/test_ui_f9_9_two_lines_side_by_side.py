# F9-9：一對節點之間可以有好幾條線 — authored 2026-08-16.
"""**餵圖是節點跟節點之間在處理的事**（使用者定調 2026-08-16）。

> 卡片只負責「餵進來的這些 source 要怎麼處理，再把 result 丟出去」。
> 所以理想上可以多連一，也可以一連多。

以前 ``Edge`` 只有一個 ``src_out`` 欄位，而 ``add_edge`` 看到同一對節點就回
False。於是從 Load 先拉 ``test`` 再拉 ``ref`` 到同一張卡時，第二條只能去
**覆寫**第一條的埠 —— 參數上兩條流都在（``streams=test,ref``），但只有一條線
帶得出它從哪來，另一條退回「執行順序上最後一個寫它的人」猜。

線性時猜的跟真的一樣，所以看不出來；**分支時猜錯**，而且跑得完、有數字。

這一支鎖四件事：多連一、一連多、剪掉其中一條、以及「兩條線在引擎眼裡都是
明講的」（後者才是這一段真正要換來的東西）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication          # noqa: E402

from d4t.core.pipeline import REGISTRY            # noqa: E402
from d4t.core.pipeline.engine import _explicit_bindings   # noqa: E402
from d4t.ui import studio as studio_mod           # noqa: E402
from d4t.ui import theme as theme_mod             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


def _load_and(win, step_key="denoise"):
    src = first_source(win)
    return src, win.add_card_after(src, step_key)


# --------------------------------------------------------------------------- #
# 1. 多連一：兩條流餵進同一張卡
# --------------------------------------------------------------------------- #
def test_two_streams_into_one_card_are_two_lines(window):
    src, nid = _load_and(window)
    window._on_edge_added(src, nid, "test")
    window._on_edge_added(src, nid, "ref")

    assert len(window.model.edges) == 2, "第二條線把第一條蓋掉了"
    assert {e.src_out for e in window.model.edges} == {"test", "ref"}
    assert window.model.nodes[nid].params["streams"] == "test,ref"


def test_both_lines_are_explicit_to_the_engine(window):
    """**這才是這一段要換來的東西。**

    兩條線都要在 ``_explicit_bindings`` 裡 —— 少一條的話那條流退回「執行順序上
    最後一個寫它的人」，線性時剛好猜對、分支時猜錯。
    """
    src, nid = _load_and(window)
    window._on_edge_added(src, nid, "test")
    window._on_edge_added(src, nid, "ref")

    bind = _explicit_bindings(window.model.to_recipe(), REGISTRY)
    assert bind.get((nid, "test")) == (src, "test")
    assert bind.get((nid, "ref")) == (src, "ref"), \
        "第二條流沒有明講的來源 —— 引擎會退回用執行順序猜"


def test_the_canvas_draws_one_line_per_edge(window):
    src, nid = _load_and(window)
    window._on_edge_added(src, nid, "test")
    window._on_edge_added(src, nid, "ref")

    drawn = [e for e in window.pipeline._edges if e.pair() == (src, nid)]
    assert len(drawn) == 2
    assert {e.out_name() for e in drawn} == {"test", "ref"}


# --------------------------------------------------------------------------- #
# 2. 一連多：同一顆埠餵好幾張卡
# --------------------------------------------------------------------------- #
def test_one_port_can_feed_several_cards(window):
    src, a = _load_and(window, "denoise")
    b = window.add_card_after(a, "tone")
    window._on_edge_added(src, a, "test")
    window._on_edge_added(src, b, "test")

    assert len(window.model.edges) == 2
    assert {(e.src, e.dst) for e in window.model.edges} == {(src, a), (src, b)}


# --------------------------------------------------------------------------- #
# 3. 剪刀剪的是「使用者瞄的那一條」
# --------------------------------------------------------------------------- #
def test_cutting_one_line_leaves_the_other(window):
    src, nid = _load_and(window)
    window._on_edge_added(src, nid, "test")
    window._on_edge_added(src, nid, "ref")

    window._on_edge_removed(src, nid, "ref")
    assert [e.src_out for e in window.model.edges] == ["test"], \
        "剪一條把兩條都剪掉了"


def test_cutting_a_line_also_stops_the_card_working_on_that_stream(window):
    """畫布不能**反過來**說謊：線沒了，卡片就不該還在處理那條流。"""
    src, nid = _load_and(window)
    window._on_edge_added(src, nid, "test")
    window._on_edge_added(src, nid, "ref")

    window._on_edge_removed(src, nid, "ref")
    assert window.model.nodes[nid].params["streams"] == "test"
    assert "test" in window.status_text()


def test_cutting_the_last_line_leaves_the_card_with_no_source(window):
    """剪掉最後一條線 → 那張卡回到「還沒接線」的狀態（F10 改）。

    這條測試本來鎖的是相反的事（最後一條不清空），理由是
    ``MultiStreamStep.stream_list`` 對空字串會退回 ``test`` —— 清成空的卡會
    安靜地跑回 test，比留著更難解釋。**F10 把那個 ``or`` 拿掉了**，所以保留
    條款也跟著沒有理由：留著的話畫布上線沒了、卡片卻還指著一條流，而且照樣
    跑得出數字。

    使用者回報的原話：「連接卡片節點後，再把線按 X 清掉 → 後方卡片的 Node
    不會跟著清掉。」
    """
    src, nid = _load_and(window)
    window._on_edge_added(src, nid, "test")
    window._on_edge_removed(src, nid, "test")

    assert window.model.edges == []
    assert window.model.nodes[nid].params["streams"] == ""
    # 回到跟「剛加進來」一模一樣：沒有輸出埠、lint 擋著
    assert window.pipeline.node_item(nid).out_names() == []
    assert [i.code for i in window.model.validate() if i.node_id == nid] \
        == ["not-connected"]


# --------------------------------------------------------------------------- #
# 4. 舊規則還在
# --------------------------------------------------------------------------- #
def test_the_same_line_twice_is_still_a_no_op(window):
    """整條一模一樣（兩個節點 + 兩個埠都一樣）仍然只算一條。"""
    src, nid = _load_and(window)
    window._on_edge_added(src, nid, "test")
    window._on_edge_added(src, nid, "test")

    assert len(window.model.edges) == 1
    assert "already connected" in window.status_text()


def test_a_second_source_on_the_same_stream_still_replaces(window):
    """F9-7 的規則不變：同一個輸入（同參數同流名）上的舊線讓位。

    「多連一」指的是**不同**的流各走各的線，不是同一條流有兩個來源。
    """
    src, a = _load_and(window, "denoise")
    b = window.add_card_after(a, "tone")
    window._on_edge_added(src, a, "test")
    window._on_edge_added(src, b, "test")
    window._on_edge_added(a, b, "test")

    pairs = window.model.edge_pairs()
    assert (a, b) in pairs
    assert (src, b) not in pairs, "同一條流留了兩個來源 —— 只有一條算數"


# --------------------------------------------------------------------------- #
# 5. 「還缺什麼上游」也要照線看（F9-11，F9 的最後一條尾巴）
# --------------------------------------------------------------------------- #
def test_a_wired_card_is_not_told_it_is_missing_that_stream(window):
    """畫布上明明有線，提示卻說「還缺這條流」—— 那句話會害人多加一張沒用的卡。

    ``available_streams`` 是照 route 的**線性順序**累加的，而 F9 之後資料是照
    線走的：線可以從執行順序上「後面」的節點接過來（分支的兩支各自往前接）。
    所以「上游有哪些流」要把**接進這張卡的線自己帶的流名**也算進去。
    """
    src, nid = _load_and(window, "snr_map")      # 預設吃 diff，一定缺上游
    assert "still needs" in window._unmet_needs(nid), \
        "這條測試的前提是「沒接線時真的會報缺」"

    window._on_edge_added(src, nid, "diff")
    assert window._unmet_needs(nid) == "", \
        "線就在畫布上，提示卻還在說缺這條流"
