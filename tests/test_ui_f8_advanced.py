# F8 第六輪：參數表要先給「非答不可的那幾格」。
"""使用者原話：「我覺得這張卡的 UI 有點亂，有些我不知道是什麼功能，也不知道
怎麼調」——第三輪用小標題把 24 格分成五組解了一半（每一格在回答哪個問題），
這一輪解另一半：**要不要現在回答**。

判準只有一句話：**這一格填了預設值就跑得出正確答案的話，它就是進階的。**

所以 ``sensitivity`` / ``smooth`` 是進階的（預設就找得到條紋，而且找不到的時候
面板上看得出來），``pitch`` 不是（站點知道、程式猜不到），``kinds`` 也不是
（``0`` 碰到第三種材質時答案是**錯的**，而且是安靜的錯 —— 見
``test_roi_cross_lattice.py``）。

**收起來不是貶低它們。** ``smooth`` / ``sensitivity`` 在調不出來的那一天是唯一
的出路，而那一天使用者最需要它們就在手邊 —— 所以是摺疊，不是刪掉，而且按鈕上
要講清楚**還有幾格**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step, list_steps  # noqa: E402


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme as theme_mod
    from d4t.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, theme_mod=theme_mod,
             widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def form(qapp):
    f = widgets_mod.ParamForm()
    f.set_step(get_step("roi_cross")().describe(), {}, ["test", "ref"])
    yield f
    f.deleteLater()


# --------------------------------------------------------------------------- #
# 1. 收起來了，而且看得出還有幾格
# --------------------------------------------------------------------------- #
def test_the_advanced_rows_start_hidden(form):
    assert form.advanced_open() is False
    names = form.advanced_names()
    assert names, "roi_cross 一格進階都沒有？那這張卡沒有被整理過"
    for name in names:
        assert form.row_visible(name) is False, "%s 一開始就攤開了" % name


def test_the_rows_that_matter_are_still_there(form):
    """把「非答不可的」也收起來的話，這個功能就變成把卡片藏起來。"""
    for name in ("source", "vertical_pitch", "vertical_width", "place",
                 "vertical_kinds", "roi_out", "gap", "fill_rule"):
        assert form.row_visible(name) is True, "%s 被收起來了" % name


def test_the_button_says_how_many_are_hidden(form):
    """「進階」兩個字答不出使用者真正的問題：**我漏看了什麼**。"""
    text = form.advanced_button_text()
    assert str(len(form.advanced_names())) in text, text
    assert "more settings" in text


def test_opening_it_shows_them_all_and_closing_puts_them_back(form):
    form.toggle_advanced()
    assert form.advanced_open() is True
    for name in form.advanced_names():
        assert form.row_visible(name) is True, "%s 展開了還是看不到" % name
    assert "Hide" in form.advanced_button_text()

    form.toggle_advanced()
    assert form.advanced_open() is False
    assert all(not form.row_visible(n) for n in form.advanced_names())


def test_a_card_with_nothing_advanced_has_no_button(qapp):
    """按鈕本身也是一列 —— 沒有東西可展開的卡片不該多一行噪音。"""
    f = widgets_mod.ParamForm()
    f.set_step(get_step("align")().describe(), {}, ["test", "ref"])
    assert f.advanced_names() == []
    assert f.advanced_button_visible() is False


def test_switching_card_folds_it_back(form):
    """上一張卡展開過，不代表這一張也要 —— 那是**這一張**卡的問題。"""
    form.toggle_advanced()
    assert form.advanced_open() is True
    form.set_step(get_step("roi_cross")().describe(), {}, ["test", "ref"])
    assert form.advanced_open() is False


# --------------------------------------------------------------------------- #
# 2. 跟 show_when 是兩個軸，不能互相蓋掉
# --------------------------------------------------------------------------- #
def test_show_when_still_wins_over_being_expanded(qapp):
    """一列同時是進階的、又被方法排除掉時，展開進階不該把它變出來 ——
    那一列在這個方法下**根本不算數**（``show_when`` 的語意）。"""
    f = widgets_mod.ParamForm()
    f.set_step(get_step("normalize")().describe(), {"method": "clahe"},
               ["test", "ref"])
    hidden = [n for n in f.param_names() if not f.row_visible(n)]
    f.set_advanced_open(True)
    still = [n for n in f.param_names() if not f.row_visible(n)]
    assert still, "展開之後每一列都出現了 —— show_when 被蓋掉了"
    assert set(still) <= set(hidden)


def test_the_count_only_counts_rows_that_apply_right_now(qapp):
    """數字要是**按下去會出現幾格**，不是「這張卡標了幾格」。"""
    f = widgets_mod.ParamForm()
    f.set_step(get_step("roi_cross")().describe(), {}, ["test", "ref"])
    n = len([x for x in f.advanced_names() if f._shown_by_rules(x)])
    assert str(n) in f.advanced_button_text()
    f.set_advanced_open(True)
    shown = sum(1 for x in f.advanced_names() if f.row_visible(x))
    assert shown == n


# --------------------------------------------------------------------------- #
# 3. 這是每張卡都用得到的機制，不是 roi_cross 的私有補丁
# --------------------------------------------------------------------------- #
def test_every_card_can_declare_advanced_rows(qapp):
    """``describe()`` 一定要帶這個鍵 —— UI 讀不到就整批當成非進階，
    而那是「安靜地失效」而不是「壞掉」。"""
    for step in list_steps():
        for spec in step().describe()["params"]:
            assert "advanced" in spec, "%s.%s" % (step.key, spec["name"])
            assert isinstance(spec["advanced"], bool)


def test_advanced_rows_still_have_their_value(form):
    """收起來的參數照樣有值、照樣送得出去 —— 這是**顯示**規則。"""
    assert form.values()["smooth"] == 3
    assert "smooth" in form.values()
