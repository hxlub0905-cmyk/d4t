# F9 Phase 4a：剪線＝真的斷開（2026-08-15）。
"""畫布上那顆「×」以前是**假的**。

主幹是從 ``node_order`` 的相鄰對**推導**出來的，而那顆 × 只從
``model.edges`` 裡刪東西 —— 一條推導出來的線根本不在那份清單裡。按下去：
狀態列說「Disconnected」、圖一點都沒變、線還畫在原地。

這是這個工具最糟的一種行為：**說做了卻沒做**。（同類的還有 `cd_x_nm` 恆為 0、
快取只存了一半的 Context —— 都是「跑得完、有數字、而且是錯的」。）

規矩定成一句話：**一份 recipe 只要有一條顯式的線，引擎就不再推導主幹。**
所以第一次動線的時候要把整條主幹寫下來，剪掉的那一條才有地方「不在」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, studio_mod=studio_mod,
             theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1200, 700)
    win.load_recipe_path(str(studio_mod.TEMPLATE_RECIPE))
    yield win
    win.close()


def _backbone(win):
    from adept.core.pipeline.graph import KIND_STREAM
    return [(a, b) for a, _sp, b, _dp, k in win._compiled_wiring()[0]
            if k != KIND_STREAM]


# --------------------------------------------------------------------------- #
# 1. 剪掉就是真的不見了
# --------------------------------------------------------------------------- #
def test_cutting_a_derived_wire_really_disconnects(window):
    assert window.model.edges == [], "前提：這份 recipe 一條顯式線都沒有"
    assert ("align", "cross") in _backbone(window)

    window._on_edge_removed("align", "cross")

    assert ("align", "cross") not in _backbone(window), (
        "剪掉的線還在圖上 —— 狀態列說 Disconnected 而什麼都沒發生")
    assert "Disconnected" in window.status_text()
    # 其餘的線一條都不能跟著消失
    assert ("norm", "align") in _backbone(window)
    assert ("cross", "sub") in _backbone(window)


def test_a_cut_leaves_the_card_visibly_orphaned(window):
    """斷開之後那張卡收不到東西 —— 這件事要在**跑之前**講出來。"""
    window._on_edge_removed("align", "cross")
    errs = [(i.code, i.node_id) for i in window.model.validate()
            if i.level == "error"]
    assert ("no-upstream", "cross") in errs, errs


def test_cutting_the_same_wire_twice_says_it_cannot(window):
    """第二次剪不該回報成功 —— 那條線已經不在了。"""
    window._on_edge_removed("align", "cross")
    window._on_edge_removed("align", "cross")
    assert "Could not disconnect" in window.status_text()


def test_a_cut_survives_save_and_load(window, tmp_path):
    """剪掉的線不可以在存檔往返之後長回來。"""
    from adept.core.pipeline import Recipe

    window._on_edge_removed("align", "cross")
    out = tmp_path / "cut.json"
    assert window.save_recipe_path(str(out)) is True

    loaded = Recipe.load(str(out))
    pairs = {(str(e[0]), str(e[1])) for e in loaded.edges if len(e) == 2}
    assert pairs, "主幹要跟著存進檔案，不然載回來又變成推導的"
    assert ("align", "cross") not in pairs


# --------------------------------------------------------------------------- #
# 2. 拉第一條線不可以順手弄斷其他八條
# --------------------------------------------------------------------------- #
def test_drawing_one_wire_does_not_orphan_everything_else(window):
    """引擎一看到顯式的線就關掉推導 —— 只寫新拉的那一條，其餘的卡會在那一瞬間
    全部變成孤兒，而使用者只是拉了一條線。"""
    before = set(_backbone(window))
    window._on_edge_added("load", "sub", "test")
    after = set(_backbone(window))

    # 只有「sub 原本從誰來」那一條該變（見下一支測試）；其餘一條都不能掉
    gone = {e for e in before - after if e[1] != "sub"}
    assert not gone, sorted(gone)
    assert ("load", "sub") in after
    errs = [i for i in window.model.validate()
            if i.level == "error" and i.code == "no-upstream"]
    assert not errs, [(i.node_id, i.detail) for i in errs]


def test_a_second_wire_into_one_input_replaces_the_first(window):
    """狀態入口只能有一條線 —— 第二條是「我改變主意了」，不是合流。

    兩條都留著的話引擎只用其中一條，另一條那半邊量出來的東西整批不見：
    跑得完、有數字、而且是錯的。所以拉的當下就換掉，而且**要講出換掉了誰** ——
    不然畫面上會有一條線無聲無息地消失。
    """
    assert ("cross", "sub") in _backbone(window)
    window._on_edge_added("load", "sub", "test")

    fed = [a for a, b in _backbone(window) if b == "sub"]
    assert fed == ["load"], fed
    assert "no longer comes from" in window.status_text()
    # 而且不會留下「兩條線接到同一個入口」那個 lint
    assert not [i for i in window.model.validate()
                if i.code == "merge-into-one-port"]


# --------------------------------------------------------------------------- #
# 3. 接進 Input 卡是接不起來的
# --------------------------------------------------------------------------- #
def test_nothing_can_be_wired_into_an_input_card(window):
    """Input 卡是一條 pipeline 的**起點**。以前這條線拉得起來、存得下去，
    然後什麼都不會發生 —— 畫面上多一條指向起點的線，而那是一句假話。"""
    before = list(window.model.edges)
    window._on_edge_added("sub", "load", "diff")
    assert window.model.edges == before
    assert "input card" in window.status_text()
