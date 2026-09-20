# F117 I7：那一行只在有話要說的時候說（2026-09-20）。
"""走查記的是「每張卡都印 `20 ok · 2051 img/s`」。

一行字在七張卡上重複七次的時候，它不再是資訊 —— 使用者真正要從它得到的只有
兩件事：**這裡出事了**，以及**拖慢整批的是這一張**。

⚠ **不是把數字丟掉。** 每一張卡的速率照樣量得到，它搬進 tooltip（滑過去就
有）。丟掉一個量得到的數字，跟把它印七遍一樣糟 —— 只是錯的方向不同。

這一支裡最該讀的是「平均分配的那一批沒有瓶頸」那一條：硬挑一個最慢的標出來，
會讓使用者去調一張其實不重要的卡。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from d4t.ui.canvas import SLOW_SHARE, loud_nodes, run_text   # noqa: E402


def _stats(**kw):
    """``name=(ok, failed, total_ms)``。"""
    return {k: tuple(v) for k, v in kw.items()}


# --------------------------------------------------------------------------- #
# 1. 失敗永遠講
# --------------------------------------------------------------------------- #
def test_a_card_that_failed_always_speaks():
    """⚠ **這一條沒有例外。** 一顆都沒跑起來的卡不會是瓶頸（它很快），
    而那正是使用者最需要在畫布上看到的那一張。"""
    stats = _stats(a=(20, 0, 100.0), b=(18, 2, 5.0), c=(20, 0, 100.0))
    assert "b" in loud_nodes(stats)
    assert run_text(stats["b"]) == "2 failed"


def test_several_failures_all_speak():
    stats = _stats(a=(0, 20, 3.0), b=(0, 20, 3.0))
    assert loud_nodes(stats) == {"a", "b"}


# --------------------------------------------------------------------------- #
# 2. 瓶頸才講，而且要真的是瓶頸
# --------------------------------------------------------------------------- #
def test_the_bottleneck_speaks():
    """一張卡吃掉八成的時間 —— 那就是使用者要調的那一張。"""
    stats = _stats(slow=(20, 0, 800.0), a=(20, 0, 100.0), b=(20, 0, 100.0))
    assert loud_nodes(stats) == {"slow"}


def test_an_even_batch_says_nothing():
    """⚠ **平均分配的那一批沒有瓶頸。**

    七張卡各佔七分之一的時候，硬挑一個最慢的標出來會讓使用者去調一張其實
    不重要的卡 —— 那比不講更糟。
    """
    stats = _stats(**{n: (20, 0, 100.0) for n in "abcdefg"})
    assert loud_nodes(stats) == set()


def test_the_threshold_reads_as_one_sentence():
    """門檻的意思是：**它一張比其他所有卡加起來還久。**

    ⚠ 第一版寫三分之一，而它在**兩張卡**的批次上破功：兩張一樣快的卡各佔
    50%，於是其中一張被指成瓶頸 —— 而那兩張一模一樣。一個跟卡片張數有關的
    門檻要嘛跟著張數算，要嘛就用一句跟張數無關的話。
    """
    assert SLOW_SHARE == pytest.approx(0.5)
    assert loud_nodes(_stats(a=(9, 0, 60.0), b=(9, 0, 40.0))) == {"a"}
    assert loud_nodes(_stats(a=(9, 0, 50.0), b=(9, 0, 50.0))) == set()
    # 剛好在門檻上：`> 0.5`，不是 `>=`（一半一半的時候沒有「比較久」的那個）。
    assert loud_nodes(_stats(a=(9, 0, 51.0), b=(9, 0, 49.0))) == {"a"}
    assert loud_nodes(_stats(a=(9, 0, 40.0), b=(9, 0, 35.0),
                             c=(9, 0, 25.0))) == set()


def test_one_card_on_its_own_says_nothing():
    """⚠ **一張卡當然佔 100%。** 「唯一的那張卡最慢」不是資訊。"""
    assert loud_nodes(_stats(only=(20, 0, 500.0))) == set()


def test_cards_with_no_timing_do_not_count():
    """快取命中的卡沒有 trace（`run_defect_cached`），耗時是 0。

    它們不該被算進分母 —— 不然一張真的卡會因為旁邊都是快取而看起來像瓶頸，
    或反過來被稀釋掉。
    """
    stats = _stats(cached=(20, 0, 0.0), real=(20, 0, 50.0))
    assert loud_nodes(stats) == set(), "只有一張卡有時間 = 沒有可比的對象"


def test_nothing_ran_nothing_speaks():
    assert loud_nodes({}) == set()
    assert loud_nodes(None) == set()


# --------------------------------------------------------------------------- #
# 3. 數字沒有不見，它在 tooltip 裡
# --------------------------------------------------------------------------- #
def test_the_speed_is_still_measured_for_every_card():
    """⚠ **反向測試：這一輪不准把數字弄丟。**

    `run_text` 對每一張卡照樣講得出速率 —— 變的只是誰把它畫在畫布上。
    """
    for st in ((20, 0, 10.0), (3, 0, 1000.0), (1, 0, 1.0)):
        assert "img/s" in run_text(st), st


def test_the_card_tooltip_carries_it(qapp_canvas):
    canvas, nid = qapp_canvas
    canvas.set_run_status({nid: (20, 0, 9.75)})
    tip = canvas.card(nid).toolTip()
    assert "Last run:" in tip, tip
    assert run_text((20, 0, 9.75)) in tip, tip


def test_the_tooltip_still_says_who_it_is(qapp_canvas):
    """⚠ 身分那一行不准被跑完的數字擠掉 —— tooltip 是**加上去**，不是換掉。"""
    canvas, nid = qapp_canvas
    canvas.set_run_status({nid: (20, 0, 9.75)})
    assert nid in canvas.card(nid).toolTip()


def test_a_quiet_card_draws_nothing(qapp_canvas):
    canvas, nid = qapp_canvas
    canvas.set_run_status({nid: (20, 0, 9.75), "other": (20, 0, 9.75)})
    assert canvas.is_loud(nid) is False


def test_clearing_the_status_clears_the_tooltip_too(qapp_canvas):
    """跑完一批、改了 recipe、再清掉 —— tooltip 不准還掛著上一批的數字。"""
    canvas, nid = qapp_canvas
    canvas.set_run_status({nid: (20, 0, 9.75)})
    assert "Last run:" in canvas.card(nid).toolTip()
    canvas.set_run_status({})
    assert "Last run:" not in canvas.card(nid).toolTip()


@pytest.fixture
def qapp_canvas():
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme as theme_mod
    from d4t.ui.canvas import PipelineCanvas

    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    canvas = PipelineCanvas()
    canvas.set_nodes([{"node_id": "dn", "label": "Denoise",
                       "category": "image", "group": "enhance"}])
    yield canvas, "dn"
    canvas.deleteLater()
