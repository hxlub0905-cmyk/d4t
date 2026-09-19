# F117 D1：「放掉選取 ⇒ 預覽跑到底」要真的成立、而且按得到（2026-09-20）。
"""走查記的是：膠囊旁邊那句 `preview stops at “norm” — press Esc to run the
decision too`，**「句子是對的，但很難被想到」**。

查下去 **句子也不是對的**：`Esc` 走的是 `pipeline.clear_selection()`，那一支
只放掉畫布自己那一份選取 —— 而預覽停在哪裡看的是 `win.selected_node`
（`_run_preview` 的 `upto`）。按了 Esc 畫布上的框不見了，預覽照樣停在同一張
卡上，判定也照樣沒有跑。

所以這一輪修的是兩件事：

1. **讓那句話成立** —— `studio_layout.clear_selection()` 把兩份選取一起放掉
   並重跑預覽；
2. **讓它按得到** —— 最後那幾個字是連結（同 `decide_path` 的先例 U11：
   底線本來就是「這個字可以點」的意思）。Esc 照樣有效，寫在 tooltip 上。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

from d4t.ui import studio as studio_mod               # noqa: E402
from d4t.ui import studio_layout                      # noqa: E402
from d4t.ui import theme as theme_mod                 # noqa: E402

RECIPE = REPO / "recipes" / "ebi-die-to-die.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    w = studio_mod.StudioWindow(show_welcome_on_start=False)
    assert w.load_recipe_path(str(RECIPE), sync=True)
    yield w
    w.close()


# --------------------------------------------------------------------------- #
# 1. 那句話現在成立
# --------------------------------------------------------------------------- #
def test_letting_go_really_lets_go(window):
    """⚠ **這就是那個 bug。**

    以前 `clear_selection` 只放掉畫布那一份，`selected_node` 原封不動 ——
    而預覽停在哪裡看的正是它。
    """
    nid = next(iter(window.model.nodes))
    window.select_node(nid)
    assert window.selected_node == nid

    studio_layout.clear_selection(window)
    assert window.selected_node is None, \
        "放掉了畫布那一份，而預覽還停在同一張卡上"


def test_the_escape_shortcut_goes_through_the_same_door(window):
    """Esc 與那個連結**是同一條路** —— 兩份實作的那天它們會分岔。"""
    nid = next(iter(window.model.nodes))
    window.select_node(nid)
    window._clear_canvas_selection()          # 快捷鍵接的就是這一支
    assert window.selected_node is None


def test_letting_go_when_nothing_is_held_changes_nothing(window):
    """沒選東西的時候按 Esc 不該排一次預覽（那是白跑一趟）。"""
    window.selected_node = None
    scheduled = []
    window._schedule_preview = lambda *a, **k: scheduled.append(1)
    studio_layout.clear_selection(window)
    assert scheduled == []


# --------------------------------------------------------------------------- #
# 2. 那句話按得到
# --------------------------------------------------------------------------- #
def test_the_note_offers_something_you_can_click():
    """⚠ **「按 Esc」沒有人想得到。**

    Esc 在這個畫面的意思是「放掉手上的東西」（U18），而「放掉選取 ⇒ 預覽跑
    到底」是一條要先知道前提才推得出來的因果 —— 一句正確而想不到的提示，
    等於沒有提示。
    """
    said = studio_mod.verdict_note("norm", None, True)
    assert "<a href=" in said and "run to the end" in said
    assert "norm" in said


def test_clicking_it_runs_to_the_end(window, qapp):
    """點那幾個字 = 放掉選取（而不是開一個說明）。"""
    nid = next(iter(window.model.nodes))
    window.select_node(nid)
    window.verdict_note.linkActivated.emit("#end")
    qapp.processEvents()
    assert window.selected_node is None


def test_escape_is_still_written_down_somewhere(window):
    """鍵盤那條路沒有消失 —— 它只是不再是**唯一**看得到的入口。"""
    assert "Esc" in window.verdict_note.toolTip()


def test_the_note_still_only_speaks_when_the_preview_stopped_early():
    """其他三種情況照舊沉默（F99 P1-2 那條不變量）。"""
    assert studio_mod.verdict_note(None, None, True) == ""
    assert studio_mod.verdict_note("norm", 2, True) == ""
    assert studio_mod.verdict_note("norm", None, False) == ""
