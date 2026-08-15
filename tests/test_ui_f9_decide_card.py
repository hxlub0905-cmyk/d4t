# F9 Phase 3d 第一批的 UI 那一半（2026-08-15）。
"""判定卡在 Studio 上的樣子。

核心的那幾條在 ``tests/test_f9_decide_card.py``（不碰 Qt）。這一支管的是
**畫面上看得到的**：算式欄旁邊那顆下拉列的是什麼、以前那頁「Score / Bin」
真的不在了、門檻線讀的是判定卡的參數。

Qt 一律 **lazy import**（在 fixture 內 import 並注入 globals）——
在收集期 import 會弄壞 ``test_no_qt_after_import``（CLAUDE.md §7）。
"""
from __future__ import annotations

import sys

import pytest


def _load_qt() -> None:
    from PySide6.QtWidgets import QApplication  # noqa: F401

    # 卡片註冊是 import 的副作用（CLAUDE.md §7）—— 不明講的話 registry 是空的
    import adept.core.steps  # noqa: F401

    from adept.ui import theme as theme_mod  # noqa: F401
    from adept.ui import viewmodel as vm_mod  # noqa: F401
    from adept.ui import widgets as widgets_mod  # noqa: F401

    globals().update(locals())


@pytest.fixture(scope="module")
def qapp():
    _load_qt()
    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
    theme_mod.apply_theme(app)
    yield app
    app.processEvents()


# --------------------------------------------------------------------------- #
# 1. 算式欄要把特徵名列出來
# --------------------------------------------------------------------------- #
def test_the_score_box_lists_the_features_measured_upstream(qapp):
    """憑記憶打特徵名，最常見的下場是**打錯一個字**：lint 只出一句 warning、
    整批照樣跑得完，而每一顆都沒有分數。所以那些名字要列得出來。"""
    from adept.core.pipeline import get_step

    form = widgets_mod.ParamForm()
    form.set_step(get_step("adc").describe(), {"expr": "a"},
                  [], ["glv_max", "snr_max"])
    editor = form._rows["expr"].editor
    assert isinstance(editor, widgets_mod.ExprField)
    assert editor.feature_names() == ["glv_max", "snr_max"]


def test_picking_a_feature_inserts_it_at_the_cursor(qapp):
    f = widgets_mod.ExprField("a + ", ["glv_max"])
    got = []
    f.changed.connect(got.append)
    f._edit.setCursorPosition(len(f.text()))
    f._on_pick(1)                                  # 下拉的第 1 項 = glv_max
    assert f.text() == "a + glv_max"
    assert got and got[-1] == "a + glv_max"
    # 選完回到「Insert feature ▾」那一項，不然它看起來像個已選的值
    assert f._combo.currentIndex() == 0


def test_an_empty_feature_list_disables_the_dropdown(qapp):
    """一個空的下拉只是一顆按不出東西的鈕。"""
    f = widgets_mod.ExprField("", [])
    assert f._combo.isEnabled() is False
    f.set_features(["glv_max"])
    assert f._combo.isEnabled() is True


# --------------------------------------------------------------------------- #
# 2. 判定卡是普通的一張卡
# --------------------------------------------------------------------------- #
def test_a_decide_card_does_not_offer_its_own_score_as_a_variable(qapp):
    """``score = score * 2`` 不是合法的寫法 —— 別把它列出來讓人以為是。"""
    m = vm_mod.RecipeModel(kind="ebi_patch")
    m.add_step("load_patch")
    decide = m.add_step("adc")
    assert "score" not in m.available_features(before_node=decide)
    assert "score" in m.available_features(upto_node=decide)


def test_the_threshold_lives_on_the_card_not_on_the_model(qapp):
    """以前 model 上恆有一個 ``threshold`` 欄位，所以直方圖那條線一定畫得出來。

    現在「還沒有人做決定」是一個真的狀態 —— 沒有判定卡就**不畫**那條線。
    畫一條 0 的線比不畫更糟：它看起來像個真的門檻。
    """
    m = vm_mod.RecipeModel(kind="ebi_patch")
    m.add_step("load_patch")
    assert m.decide_nodes() == []
    assert m.decision_threshold() is None

    decide = m.add_step("adc")
    m.set_decision_threshold(12.5)
    assert m.decision_threshold() == pytest.approx(12.5)
    assert m.nodes[decide].params["threshold"] == pytest.approx(12.5)

    # 兩張判定卡 = 沒有唯一答案，一樣不畫（要改就到那張卡上改）
    m.add_step("adc")
    assert len(m.decide_nodes()) == 2
    assert m.decision_threshold() is None


def test_the_score_page_and_its_fake_library_card_are_gone(qapp):
    """判定變成卡片之後，那一頁與那個假卡片沒有存在的理由。

    留著的話畫面上有兩個地方能設門檻，而使用者不知道哪個算數 —— 那正是
    ``adc`` 被收在 ``HIDDEN_STEPS`` 裡那麼久的原因。
    """
    from adept.ui import canvas as canvas_mod
    from adept.ui import studio as studio_mod

    for gone in ("_SCORE_LIBRARY_KEY", "_SCORE_LIBRARY_ENTRY", "_SCORE_HELP"):
        assert not hasattr(studio_mod, gone), gone
    for gone in ("show_score_page", "_build_score_pane", "_sync_score_widgets"):
        assert not hasattr(studio_mod.StudioWindow, gone), gone
    # 畫布角落那行摘要是那個固定欄位在畫布上唯一的影子
    for gone in ("score_clicked", "set_score_summary", "score_summary_text"):
        assert not hasattr(canvas_mod.PipelineCanvas, gone), gone
