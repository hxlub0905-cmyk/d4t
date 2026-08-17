# F9-7：線由使用者拉，一個輸入埠只有一條 — authored 2026-08-16.
"""**加一張卡不會自己接線**，而且**一個輸入埠只能有一條線**。

為什麼（2026-08-16 使用者回報）
------------------------------
以前從卡片庫加卡會順手接一條 ``選取那張 → 新卡`` 的線。立意是少按一次，但
它讓畫布上出現了**使用者沒畫過的線**：他接著自己從 Denoise 拉一條進 Adjust
tone，於是同一個輸入埠有兩條線 —— 一條自動的（Load → Adjust tone）、一條他畫
的。引擎查資料來源的 key 是 ``(下游節點, 流名)``，兩條線落在同一個 key 上時只有
一條算數，而贏的是 ``edges`` 裡排在後面的那條 —— 那個順序在畫布上看不出來。
症狀就是「我明明接了 Denoise，跑出來卻像沒接」。

這一支鎖兩件事：
1. ``add_card_after`` **不產生任何線**（順序照排）；
2. 往同一個輸入埠再拉一條線 → 舊的那條**讓位**，不是兩條並存。
   ``image_keys`` 的卡（可以同時做好幾條流）上，不同流名的線照樣並存。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication          # noqa: E402

from adept.core.pipeline.recipe import validate     # noqa: E402
from adept.ui import studio as studio_mod           # noqa: E402
from adept.ui import theme as theme_mod             # noqa: E402


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


def _load_denoise_tone(win):
    """Load images → Denoise → Adjust tone（三張卡，**一條線都沒有**）。"""
    win._on_add_requested("load_patch")
    load = win.selected_node
    win._on_add_requested("denoise")
    dn = win.selected_node
    win.select_node(load)
    win._on_add_requested("tone")
    tone = win.selected_node
    return load, dn, tone


# --------------------------------------------------------------------------- #
# 1. 加卡不接線
# --------------------------------------------------------------------------- #
def test_adding_a_card_draws_no_line_at_all(window):
    window._on_add_requested("load_patch")
    load = window.selected_node
    window._on_add_requested("denoise")
    dn = window.selected_node

    assert dn and dn != load
    assert window.model.edge_pairs() == [], \
        "加一張卡就自己接了一條線 —— 線要留給使用者拉"


def test_the_new_card_still_lands_after_the_selected_one(window):
    """不接線不代表不排序 —— 「在這之後做」跟「資料從這來」是兩件事。"""
    window._on_add_requested("load_patch")
    load = window.selected_node
    window._on_add_requested("denoise")
    dn = window.selected_node
    window.select_node(load)
    window._on_add_requested("tone")
    tone = window.selected_node

    order = window.model.node_order
    assert order.index(tone) == order.index(load) + 1, \
        "新卡沒有排在選取那張的後面"
    assert order.index(dn) > order.index(load)


def test_adding_a_card_says_what_to_do_next(window):
    """不接線就要講出接下來要做什麼（推廣鐵則：使用者不會自己猜）。"""
    window._on_add_requested("load_patch")
    window._on_add_requested("denoise")
    assert "drag a line" in window.status_text().lower()


# --------------------------------------------------------------------------- #
# 2. 一個輸入埠一條線
# --------------------------------------------------------------------------- #
def test_a_second_line_into_the_same_input_replaces_the_first(window):
    """截圖上那個接法：Load 與 Denoise 都接進 Adjust tone 的同一個輸入。

    使用者要的是「tone 做在 denoise 的輸出上」，所以後拉的那條贏、
    Load → tone 那條讓位 —— 不是兩條並存然後由 ``edges`` 的順序偷偷決定。
    """
    load, dn, tone = _load_denoise_tone(window)
    window._on_edge_added(load, dn, "test")
    window._on_edge_added(load, tone, "test")
    assert (load, tone) in window.model.edge_pairs()

    window._on_edge_added(dn, tone, "test")
    pairs = window.model.edge_pairs()
    assert (dn, tone) in pairs, "使用者剛拉的那條線不見了"
    assert (load, tone) not in pairs, \
        "同一個輸入埠留著兩條線 —— 只有一條算數，另一條是裝飾"
    assert "replacing" in window.status_text().lower(), \
        "安靜地拿掉一條使用者畫過的線 —— 至少要講一聲"


def test_two_different_streams_into_the_same_card_still_coexist(window):
    """``image_keys`` 的卡可以同時做 test 與 ref —— 那是兩個輸入，不是搶。"""
    load, dn, _tone = _load_denoise_tone(window)
    window._on_edge_added(load, dn, "test")
    window._on_edge_added(load, dn, "ref")

    node = window.model.nodes[dn]
    assert set(str(node.params["streams"]).split(",")) == {"test", "ref"}


def test_replacing_a_line_leaves_a_recipe_the_engine_accepts(window):
    """換完線之後 lint 要是乾淨的 —— 這條在驗「換」是真的換掉了。"""
    load, dn, tone = _load_denoise_tone(window)
    window._on_edge_added(load, dn, "test")
    window._on_edge_added(load, tone, "test")
    window._on_edge_added(dn, tone, "test")

    bad = [i for i in validate(window.model.to_recipe(), "ebi_patch")
           if i.code == "ambiguous-input"]
    assert bad == [], "換過線之後還是有兩條線搶同一個輸入"


# --------------------------------------------------------------------------- #
# 3. 手寫的 recipe 也要擋（UI 不是唯一的入口）
# --------------------------------------------------------------------------- #
def test_the_engine_reports_two_lines_into_one_input(window):
    """UI 擋得住是因為它會換線；直接編 JSON 的人沒有那道關卡，lint 要講出來。"""
    load, dn, tone = _load_denoise_tone(window)
    window._on_edge_added(load, dn, "test")
    window._on_edge_added(dn, tone, "test")
    # 繞過 UI 的換線邏輯，直接把第二條線塞回 model（＝手寫 recipe 的形狀）
    window.model.add_edge(load, tone, src_out="test", dst_in="streams")

    issues = [i for i in validate(window.model.to_recipe(), "ebi_patch")
              if i.code == "ambiguous-input"]
    assert len(issues) == 1
    assert issues[0].level == "error"
    assert load in issues[0].detail and dn in issues[0].detail, \
        "沒有講出是哪兩條線在搶（使用者要照著這句話去刪線）"
