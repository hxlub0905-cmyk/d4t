# F7-13 驗收：控制項要看得出自己是什麼。
"""這一支測的不是「功能對不對」，是**看不看得出來**。

三個症狀來自同一種毛病：控制項長得不像它自己。下拉選單長得像文字框，於是
沒有人知道它可以點開；一個沒辦法用打的值配一個文字框，於是使用者對著它猜；
一張還不能跑的卡片長得跟設定完整的一樣，於是要跑過一次才知道。

這種 bug 用「功能測試」抓不到 —— 每一項功能都是好的。所以這裡直接量畫素、
量控制項的型別、量卡片上有沒有那個標記。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _import_qt(g):
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QLineEdit, QPushButton,
    )

    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    from adept.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, QComboBox=QComboBox, QLineEdit=QLineEdit,
             QPushButton=QPushButton, QPixmap=QPixmap, studio_mod=studio_mod,
             theme_mod=theme_mod, widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app
    theme_mod.apply_theme(app, "light")


def _ink(widget, x0: int, x1: int) -> int:
    """widget 畫出來之後，[x0, x1) 這條直帶裡有多少畫素不是它的底色。"""
    from PySide6.QtGui import QColor

    widget.resize(200, 26)
    pm = QPixmap(widget.size())
    pm.fill(QColor("#808080"))          # 中性灰：淺色與深色主題都不會剛好同色
    widget.render(pm)
    img = pm.toImage()
    bg = img.pixelColor(widget.width() // 2, widget.height() // 2)
    n = 0
    for x in range(x0, x1):
        for y in range(4, widget.height() - 4):
            p = img.pixelColor(x, y)
            if (abs(p.red() - bg.red()) + abs(p.green() - bg.green())
                    + abs(p.blue() - bg.blue())) > 30:
                n += 1
    return n


# --------------------------------------------------------------------------- #
# 1. 下拉選單看得出是下拉選單
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_a_dropdown_does_not_look_like_a_text_box(qapp, theme_name):
    """`QComboBox::drop-down { border: 0 }` 會讓箭頭**完全不畫**（styled 的
    subcontrol 需要自帶 down-arrow 圖檔，而這個 repo 是純文字的）。

    症狀不是「醜」——是「Match on」（三選一）跟「Name this region」（自由文字）
    在畫面上一模一樣，使用者無從得知哪個點得開。
    """
    theme_mod.apply_theme(qapp, theme_name)
    combo = QComboBox()
    combo.addItems(["ref", "test"])
    arrow_area = (176, 197)
    assert _ink(combo, *arrow_area) > 0, "the dropdown arrow is not drawn"
    assert _ink(QLineEdit("ref"), *arrow_area) == 0, "a line edit grew an arrow"


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_a_toolbar_button_looks_pressable(qapp, theme_name):
    """工具列以前是一排沒有邊框的字 —— 那讀起來是「File Edit View…」，
    而選單列是拉下來的東西，不是按的東西。"""
    theme_mod.apply_theme(qapp, theme_name)
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        btn = win.btn_open_klarf
        btn.resize(150, 30)
        from PySide6.QtGui import QColor

        pm = QPixmap(btn.size())
        pm.fill(QColor("#808080"))
        btn.render(pm)
        img = pm.toImage()
        # 上緣那一條就是邊框（1 px）；中間是按鈕的底色。兩者一樣 = 沒有邊框，
        # 也就是「一排字」。
        edge = img.pixelColor(btn.width() // 2, 0)
        middle = img.pixelColor(btn.width() // 2, btn.height() // 2)
        assert edge != middle, "the button has no visible edge — it reads as a menu bar"
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 2. 模板參數
# --------------------------------------------------------------------------- #
def _a_template() -> str:
    from adept.core.algo import template as at

    img = np.zeros((240, 320), np.float32)
    for k in range(8):
        x = k * 40
        img[:, x:x + 40] = 120.0
        img[:, x + 14:x + 34] = 60.0
        img[:, x + 12:x + 16] = 210.0
        img[:, x + 32:x + 36] = 210.0
    img += np.random.default_rng(0).normal(0, 4, img.shape).astype(np.float32)
    return at.encode_cell(at.build_golden_cell(img).cell)


def test_the_template_parameter_is_not_a_text_box(qapp):
    """值有六千多個字元而且沒有人能用打的。文字框在這裡有三個後果：空的時候
    看起來只是「還沒填」、填了之後變成一片 base64、而且它可以被改。"""
    from adept.core.pipeline.step import get_step

    form = widgets_mod.ParamForm()
    step = get_step("roi_template")
    form.set_step(step.describe(), {}, ["test", "ref"])
    editor = form.editor("template")
    assert isinstance(editor, widgets_mod.TemplateField)
    assert not isinstance(editor, QLineEdit)
    assert editor.has_template() is False
    assert "cannot run" in editor.describe()

    editor.set_text(_a_template())
    assert editor.has_template() is True
    # 摘要講的是**解出來的東西**，不是旁邊記著的字串長度
    assert "40 × 240 px" in editor.describe()


def test_the_button_asks_studio_to_open_the_dialog(qapp):
    """按鈕在參數列裡，但對話框是 Studio 開的 —— 元件不知道那是什麼對話框。"""
    from adept.core.pipeline.step import get_step

    form = widgets_mod.ParamForm()
    form.set_step(get_step("roi_template").describe(), {}, ["ref"])
    seen = []
    form.action_requested.connect(seen.append)
    form.editor("template").button.click()
    assert seen == ["template"]


# --------------------------------------------------------------------------- #
# 3. 「這張卡還不能跑」看得見
# --------------------------------------------------------------------------- #
@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


def test_a_card_that_cannot_run_is_marked_on_the_canvas(window):
    """lint 早就知道模板是空的 —— 但那個知識以前只在按下 Run trial 的那一刻
    出現一次，卡片在畫布上看起來永遠是好的。"""
    nid = window.model.add_step("roi_template")
    window.select_node(nid)

    codes = [i.code for i in window.model.validate() if i.node_id == nid]
    assert "not-configured" in codes

    item = window.pipeline.node_item(nid)
    assert item is not None
    assert "Build template" in item.problem()
    assert "Build template" in item.toolTip()

    window._apply_template(nid, _a_template(), "x")
    assert window.pipeline.node_item(nid).problem() == ""
    assert [i.code for i in window.model.validate() if i.node_id == nid] == []


def test_the_badge_paints_in_both_themes(window):
    """標記畫在卡片的右上角，而那裡本來是卡片名字的尾巴。"""
    from PySide6.QtGui import QColor, QPainter

    nid = window.model.add_step("roi_template")
    item = window.pipeline.node_item(nid)
    for name in ("light", "dark"):
        theme_mod.set_theme(name)
        pm = QPixmap(240, 80)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        item.paint(p, None, None)          # 例外會在這裡冒出來
        p.end()
        assert not pm.isNull()
    theme_mod.apply_theme(QApplication.instance(), "light")


def test_the_card_summary_never_shows_the_raw_template(window):
    """節點的第三行是「哪些參數被改過」。模板直接串進去的話，那一行就變成
    一段 base64 —— 既沒有資訊，也把真正有用的參數擠掉了。"""
    nid = window.model.add_step("roi_template")
    window._apply_template(nid, _a_template(), "x")
    summary = window.pipeline.node_item(nid).info.get("summary", "")
    assert "gc1:" not in summary
    assert "template: set" in summary
    assert len(summary) < 120
