# F13-2/3/4：層級、對比、地標 — authored 2026-08-19.
"""三件「看起來」的事，但每一件都量得出來。

* **F13-3 對比**：階段卡片數那個小數字吃的是 ``$text_disabled`` —— 用錯 token
  （那個 token 的意思是「停用」，不是「次要」）。量出來深色 2.90、**淺色
  1.89**，而 WCAG AA 對小字要 4.5。使用者回報的是深色看不清楚，
  更糟的其實是淺色。
* **F13-2 層級**：工具列上六顆等權重的框，只有 Run trial 是藍的。三級：
  主要（填滿）／次要（外框）／第三級（純圖示、沒有框）。
* **F13-4 地標**：四個直欄之間只有一條 splitter，沒有任何東西說得出
  「這一欄是什麼」。

顏色那一條**逐個階段、逐個主題**驗 —— 下一次調色盤的人不必記得回來算。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel     # noqa: E402

from d4t.ui import scope                               # noqa: E402
from d4t.ui import studio as studio_mod                # noqa: E402
from d4t.ui import theme as theme_mod                  # noqa: E402
from d4t.ui import widgets as widgets_mod              # noqa: E402
from d4t.ui.theme import THEMES                        # noqa: E402


def _stage_button_style() -> str:
    """rail 上任何一顆階段鈕的計數樣式（不必開整個主視窗）。"""
    panel = widgets_mod.LibraryPanel()
    try:
        return panel.stage_buttons["input"].count.styleSheet()
    finally:
        panel.deleteLater()


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    theme_mod.apply_theme(app, "light")


@pytest.fixture
def window(qapp):
    theme_mod.apply_theme(qapp, "light")
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1600, 1000)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# F13-3：對比是**算**出來的，不是用眼睛猜的
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", list(THEMES))
def test_every_stage_count_is_readable_in_every_theme(qapp, theme_name):
    """六個階段 × 兩種主題，全部要過 AA 的 4.5。

    逐個驗而不是驗一個代表：階段色是**各挑各的**，而淺色主題那六個原樣放在
    自己的淡底上只有 2.8–3.5 —— 「同一個規則兩種主題」只有算得出來，
    在其中一種主題下用眼睛調，另一種一定會歪。
    """
    theme_mod.apply_theme(qapp, theme_name)
    bg = theme_mod.TOKENS["bg_panel"]
    bad = []
    for gid, _title, _sub in widgets_mod.LibraryPanel.GROUPS:
        ratio = theme_mod.contrast_ratio(theme_mod.count_color(gid), bg)
        if ratio < theme_mod.AA_SMALL:
            bad.append("%s %.2f" % (gid, ratio))
    assert not bad, "%s 主題下讀不到：%s" % (theme_name, bad)


def test_the_old_token_would_not_have_passed(qapp):
    """把當初那個值也留在測試裡 —— 「以前有多糟」是這條測試存在的理由。"""
    theme_mod.apply_theme(qapp, "light")
    was = theme_mod.contrast_ratio(theme_mod.TOKENS["text_disabled"],
                                   theme_mod.TOKENS["bg_panel"])
    assert was < 2.5, "淺色主題的 $text_disabled 當初量到 1.89"


def test_readable_on_keeps_the_hue_and_stops_as_soon_as_it_passes():
    """推的方向由底色決定，所以色相留得住（綠推完還是綠）。"""
    green = "#5f8f3f"
    on_light = theme_mod.readable_on(green, "#d6e1d2")
    r, g, b = (int(on_light.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    assert g > r and g > b, "推完之後不是綠色了：%s" % on_light
    assert theme_mod.contrast_ratio(on_light, "#d6e1d2") >= theme_mod.AA_SMALL
    assert "background:transparent" in _stage_button_style(), \
        "使用者定調：數字不要網底"
    # 已經過得了的顏色原樣回傳（不要為了保險多推一格，那會讓深色主題變糊）
    assert theme_mod.readable_on("#000000", "#ffffff") == "#000000"


# --------------------------------------------------------------------------- #
# F13-2：三級，而且只有兩顆有顏色
# --------------------------------------------------------------------------- #
def test_the_toolbar_has_three_weights(window):
    # ⚠ 「secondary」那一級**現在工具列上沒有成員**：唯一那顆
    # （accent 外框的「Run all & write」）2026-08-24 拿掉了，因為它跟
    # `Run trial ▾` 選單裡那一項是同一支 `run_all()`。這一級**沒有刪**
    # —— QSS 還在，Results 視窗與其他地方用得到，而工具列上不該有第二個
    # 主要動作。
    tiers = {
        "primary": [window.btn_trial, window.btn_trial_more],
        "ghost": [window.btn_undo, window.btn_redo, window.btn_theme],
    }
    for b in tiers["primary"]:
        assert b.objectName() == "primary"
    for b in tiers["ghost"]:
        assert b.property("variant") == "ghost"
        assert b.text() == "", \
            "第三級是**純圖示**：一排沒有框的字讀起來是選單列（theme.py 的規矩）"


def test_the_data_entries_are_not_on_the_toolbar_any_more(window):
    """F14-1（使用者：「工具列拿掉吧（會混淆）」）—— 資料的入口搬到卡片上。

    **入口沒有變少，只是搬家**：這一條同時驗兩件事，因為只驗前半的話，
    「拿掉了」跟「弄丟了」在測試上長得一樣。
    """
    from PySide6.QtWidgets import QToolButton

    on_bar = {w.text() for a in window.toolbar.actions()
              if (w := window.toolbar.widgetForAction(a)) is not None
              and isinstance(w, QToolButton)}
    for src in scope.INPUT_SOURCES:
        assert src.title not in on_bar and src.short not in on_bar, src.title
        # 沒有資料時，畫面最大的那一塊仍然一種 source 一列
        assert window.empty_source_buttons[src.key].text() == src.title
    assert "Open GDS export…" not in on_bar


# --------------------------------------------------------------------------- #
# F13-4：每一欄都說得出自己是什麼
# --------------------------------------------------------------------------- #
def test_every_column_says_what_it_is(window):
    names = {lbl.text() for lbl in window.findChildren(QLabel)
             if lbl.objectName() == "columnHeader"}
    assert {"LIBRARY", "PIPELINE", "PREVIEW"} <= names, names


def test_the_pipeline_landmark_does_not_swallow_clicks(window):
    """它是浮在畫布上的一個地標，不是一塊擋在前面的東西。"""
    from PySide6.QtCore import Qt

    lbl = window.pipeline._header
    assert lbl.testAttribute(Qt.WA_TransparentForMouseEvents) is True
    assert lbl.parent() is window.pipeline, \
        "包一層容器會讓 canvas_column.widget(0) 不再是畫布"
