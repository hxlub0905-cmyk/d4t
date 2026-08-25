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
from tests.region_cards import (  # noqa: E402
    add_region_step, region_card,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    from d4t.ui import widgets as widgets_mod
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
# 1. 參數說明：住在 tooltip，列面上不佔一行
#    （2026-08-14 起取代 F7-15 的「一行、hover 攤開」—— 攤開/收合跟著滑鼠
#      此起彼落地閃，使用者的形容是「移過去會顯示、移走又消失，很亂」。）
# --------------------------------------------------------------------------- #
def test_help_lives_in_the_tooltip_not_on_the_row(window, qapp):
    window.show()
    nid = add_region_step(window.model, "roi_template")
    window.select_node(nid)
    qapp.processEvents()

    form = window.param_form
    row = form._rows["min_structure"]
    assert row.hint_visible() is False, "說明不再常駐在列面上"
    full = form.hint_text("min_structure")
    assert row.toolTip() == full, "整列都要能停出全文"
    assert row.name_label.toolTip() == full


def test_the_full_text_is_still_the_full_text(window):
    """畫面上不畫只是**畫面上**的事。問「這個參數的說明寫了什麼」的人要的，
    從來不是「現在放得下多少」。"""
    nid = add_region_step(window.model, "roi_template")
    window.select_node(nid)
    full = window.param_form.hint_text("min_structure")
    assert "featureless patch scores about 1" in full
    editor = window.param_form.editor("min_structure")
    assert editor.toolTip() == full, "滑鼠停上去也要看得到全文"


def test_an_error_is_painted_on_the_row_and_stays(window):
    """錯誤是他現在最需要讀完的一句話 —— 它是唯一准許回到列面上的說明，
    而且出現就是整段（不裁切、不跟著滑鼠收合）。"""
    nid = add_region_step(window.model, "roi_template")
    window.select_node(nid)
    form = window.param_form
    row = form._rows["min_score"]
    form.show_error("min_score", "must be between -1 and 1")
    assert row.hint_visible() is True
    assert row.hint.is_expanded() is True, "錯誤要整段攤開，不裁切"
    assert "must be between" in row.hint.text()
    form.clear_errors()
    assert row.hint_visible() is False, "錯誤清掉之後列面要收乾淨"
    assert form.hint_text("min_score") == row.spec["help"]


def test_rows_are_one_line_tall_without_hints(window, qapp):
    """這一項的重點就是**看得到幾個參數**。拿掉常駐說明之後，每一列只剩
    標題列一行高；掛上錯誤那一列才長高。"""
    window.show()
    nid = add_region_step(window.model, "roi_template")
    window.select_node(nid)
    qapp.processEvents()
    form = window.param_form
    assert all(r.hint_visible() is False for r in form._rows.values())
    plain = form._rows["min_score"].sizeHint().height()
    form.show_error("min_score", "must be between -1 and 1")
    qapp.processEvents()
    with_error = form._rows["min_score"].sizeHint().height()
    assert with_error > plain, (plain, with_error)


# --------------------------------------------------------------------------- #
# 2. 沒有資料時，最大的那一塊要說得出下一步
# --------------------------------------------------------------------------- #
def test_the_empty_panel_offers_what_you_can_actually_do(window):
    """沒有資料時，最大的那一塊要說得出下一步 —— **而且只說得出真的做得到的**。

    這條以前叫「the two things you can do」，第二件是「用範例資料試一次」。
    範例 recipe 2026-08-16 全部拿掉之後那顆鈕收起來了
    （``scope.SHOW_SAMPLE_ENTRIES``），所以現在只剩一條路 —— 而畫面上那句話
    也不能再提它。鈕本身還在（只是隱形），光看 ``.text()`` 看不出差別。

    問的是 ``isHidden()`` 不是 ``isVisible()``：視窗還沒 ``show()`` 的時候
    **每一個 widget 的 ``isVisible()`` 都是 False**（docs/PITFALLS.md 那一列），
    拿它問「這顆藏起來了嗎」在建構期永遠答「是」。``isHidden()`` 問的是
    「有沒有被明確藏起來」，那正是這裡要知道的事。
    """
    from d4t.ui import scope

    assert window.image_stack.currentIndex() == 0
    assert window.btn_empty_open.text() == "Open KLARF…"
    assert window.btn_empty_open.isHidden() is False

    if scope.SHOW_SAMPLE_ENTRIES:
        assert "sample data" in window.btn_empty_sample.text()
        assert window.btn_empty_sample.isHidden() is False
    else:
        assert window.btn_empty_sample.isHidden() is True
        assert "sample data" not in window.empty_state_hint.text()


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

    nid = add_region_step(window.model, "roi_template")
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
