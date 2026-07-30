# F7-15 驗收：畫面上的字要能被讀完。
"""三件事都不是「功能不對」，是**讀不完 / 看不到 / 分不出來**。

* 一張卡 11 個參數、每個帶 2–3 行灰字 = 一面牆。一定要捲，而且真正要緊的事
  （這張卡還沒有模板）淹在裡面。
* 沒載資料時最大的一塊是一片黑，角落有一行極小的「(no dataset loaded)」——
  首啟導覽關掉之後就沒有任何東西說得出下一步。
* 狀態列是**唯一**會講「這件事沒成功」的地方，而它跟「Added denoise」用一模
  一樣的灰字，在畫面最左下角。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    from adept.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, studio_mod=studio_mod,
             theme_mod=theme_mod, widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1400, 900)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 參數說明：一行，用到才攤開
# --------------------------------------------------------------------------- #
def test_help_is_one_line_until_you_use_that_row(window, qapp):
    window.show()
    nid = window.model.add_step("roi_template")
    window.select_node(nid)
    qapp.processEvents()

    form = window.param_form
    row = form._rows["min_structure"]
    assert row.hint.is_expanded() is False
    assert row.hint.wordWrap() is False, "收起來的說明不能換行 —— 那就沒有收"
    # 切字自己算，不讓 Qt 硬切在字的中間
    assert row.hint.text().endswith("…")
    assert len(row.hint.text()) < len(form.hint_text("min_structure"))

    row.set_active(True)
    assert row.hint.is_expanded() is True
    assert row.hint.wordWrap() is True
    assert row.hint.text() == form.hint_text("min_structure")


def test_the_full_text_is_still_the_full_text(window):
    """收起來只是**畫面上**的事。問「這個參數的說明寫了什麼」的人要的，
    從來不是「現在放得下多少」。"""
    nid = window.model.add_step("roi_template")
    window.select_node(nid)
    full = window.param_form.hint_text("min_structure")
    assert "featureless patch scores about 1" in full
    editor = window.param_form.editor("min_structure")
    assert editor.toolTip() == full, "滑鼠停上去也要看得到全文"


def test_an_error_stays_open(window):
    """錯誤是他現在最需要讀完的一句話 —— 不能因為滑鼠移開就切掉。"""
    nid = window.model.add_step("roi_template")
    window.select_node(nid)
    form = window.param_form
    row = form._rows["min_score"]
    form.show_error("min_score", "must be between -1 and 1")
    assert row.hint.is_expanded() is True
    row.set_active(False)
    assert row.hint.is_expanded() is True, "錯誤被收起來了"
    form.clear_errors()
    assert row.hint.is_expanded() is False


def test_more_parameters_fit_on_screen_than_before(window, qapp):
    """這一項的重點就是**看得到幾個參數**。11 個參數 × 3 行 vs × 1 行。"""
    window.show()
    nid = window.model.add_step("roi_template")
    window.select_node(nid)
    qapp.processEvents()
    form = window.param_form
    collapsed = sum(r.sizeHint().height() for r in form._rows.values())
    for r in form._rows.values():
        r.set_active(True)
    qapp.processEvents()
    expanded = sum(r.sizeHint().height() for r in form._rows.values())
    assert collapsed < expanded * 0.75, (collapsed, expanded)


# --------------------------------------------------------------------------- #
# 2. 沒有資料時，最大的那一塊要說得出下一步
# --------------------------------------------------------------------------- #
def test_the_empty_panel_offers_the_two_things_you_can_do(window):
    assert window.image_stack.currentIndex() == 0
    assert window.btn_empty_open.text() == "Open KLARF…"
    assert "sample data" in window.btn_empty_sample.text()


def test_the_images_come_back_once_data_is_loaded(window, tmp_path):
    from make_sample import generate

    out = generate(str(tmp_path / "lot"), n=4, seed=3)
    assert window.load_dataset_path(out["klarf"], sync=True) is True
    assert window.image_stack.currentIndex() == 1


# --------------------------------------------------------------------------- #
# 3. 「沒成功」不能跟「做好了」長得一樣
# --------------------------------------------------------------------------- #
def test_a_refusal_is_marked_as_one(window, tmp_path):
    """加一張缺模板的卡 → 試跑被 lint 擋下來。那是使用者按了鈕之後**唯一**的
    解釋，它不能跟上一句「Added roi_template」長得一模一樣。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lot2"), n=4, seed=4)
    window.load_dataset_path(out["klarf"], sync=True)
    window._status("Added denoise")
    assert window.status_level() == "info"

    nid = window.model.add_step("roi_template")
    window.select_node(nid)
    assert window.run_trial(n=4) is False
    assert "Cannot run" in window.status_text()
    assert window.status_level() == "error"

    window._status("Added denoise")
    assert window.status_level() == "info"


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_error_colour_is_actually_different(window, qapp, theme_name):
    """屬性設了不代表畫出來不一樣（QSS 沒寫規則的話什麼都不會變）。"""
    from PySide6.QtGui import QColor, QPixmap

    theme_mod.apply_theme(qapp, theme_name)
    window.show()
    bar = window.statusBar()
    bar.resize(400, 22)

    def shot(level):
        # **同一句話**，只有 level 不同 —— 這樣兩張圖的差別只可能來自樣式。
        window._status("Cannot run — this card is not set up", level)
        qapp.processEvents()
        pm = QPixmap(bar.size())
        pm.fill(QColor("#808080"))
        bar.render(pm)
        return pm.toImage()

    normal, bad = shot("info"), shot("error")
    diff = sum(1 for x in range(bar.width()) for y in range(bar.height())
               if normal.pixelColor(x, y) != bad.pixelColor(x, y))
    assert diff > 20, "紅字的屬性設了，但畫出來一模一樣（QSS 沒有對應規則）"
    theme_mod.apply_theme(qapp, "light")
