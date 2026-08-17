# F11 Input-1（UI 那一半）：「第幾張圖 → 叫什麼」是一張小表，不是一行逗號字串。
"""值長這樣：``1:se1, 2:bse, 3:se2, 4:se3, 5:se4``。

五列以上的時候，一行逗號字串**數不清位置** —— 而「哪一張是 BSE」正是這個參數
唯一要回答的問題。數錯一格不會有語法錯誤，只會讓 BSE 的數字被寫在 SE 的名字上。

所以排成一列一張圖：位置是程式寫的（打不錯），名字才是使用者打的；空著的那一列
就是「不命名」，而 placeholder 寫出它不命名時會叫什麼（那是現行行為）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.pipeline import get_step  # noqa: E402


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import theme as theme_mod
    from adept.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, theme_mod=theme_mod,
             widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def field(qapp):
    f = widgets_mod.ChannelMapField("")
    yield f
    f.deleteLater()


def test_the_editor_is_a_table_not_a_text_box(qapp):
    """`channel_map` 型別拿到的是 ChannelMapField，不是 QLineEdit。"""
    form = widgets_mod.ParamForm()
    form.set_step(get_step("load_patch")().describe(), {}, ["test", "ref"])
    w = form.editor("channel_map")
    assert isinstance(w, widgets_mod.ChannelMapField), type(w).__name__
    form.deleteLater()


def test_it_starts_with_two_rows_so_it_does_not_look_broken(field):
    assert field.row_count() == 2
    assert field.text() == ""          # 空的 = 照預設命名（現行行為）


def test_rows_grow_to_fit_the_value(qapp):
    f = widgets_mod.ChannelMapField("1:se1, 2:bse, 5:se4")
    assert f.row_count() == 5, "第 5 張有名字，就要有第 5 列"
    assert f.text() == "1:se1, 2:bse, 5:se4"
    f.deleteLater()


def test_add_another_image_appends_a_row(field):
    before = field.row_count()
    field._add_btn.click()
    assert field.row_count() == before + 1


def test_an_empty_row_means_that_image_is_not_named(qapp):
    """空著不是「壞掉的欄位」，是「這一張不命名」—— 值裡就不該出現它。"""
    f = widgets_mod.ChannelMapField("1:se1, 2:bse")
    f._edits[0].setText("")
    assert f.text() == "2:bse"
    f.deleteLater()


def test_the_placeholder_says_what_it_would_be_called_without_a_name(field):
    """使用者看得到自己在改什麼：不命名的話第 1 張叫 test、第 2 張叫 ref。"""
    assert field._edits[0].placeholderText() == "test"
    assert field._edits[1].placeholderText() == "ref"
    field._add_btn.click()
    assert field._edits[2].placeholderText() == "img3"


def test_typing_a_name_emits_the_whole_value(field):
    seen = []
    field.changed.connect(seen.append)
    field._edits[1].setText("bse")
    assert seen and seen[-1] == "2:bse"
