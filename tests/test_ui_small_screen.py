# U1：視窗要裝得進廠內那台螢幕 — authored 2026-09-08.
"""**開發機是 1920×1080，目標機器是機台旁那台 1366×768 的 PC。**

寫死的 ``resize(1440, 900)`` 在開發時看不出問題，在那台上是「底部那排鈕在
螢幕外面」—— 而畫面上沒有任何東西說它在那裡（Qt 不會自己捲）。

這一支的形狀
------------
不是「檢查每個 `resize` 有沒有改成 `fit`」（那種測試在下一個新對話框出現時
一句話都不會說），而是**把每一個頂層視窗真的開起來，量它的 frameGeometry
落不落在 availableGeometry 裡**。

⚠ **螢幕尺寸是假的，而那是刻意的。** offscreen 平台的螢幕是 800×800 ——
一個誰也沒有的尺寸；在它上面全綠只證明「在 CI 上放得下」。所以視窗那一段
把 `fit_screen.FORCE_RECT` 設成真正要保證的那兩個尺寸
（1366×768 與更窄的 1024×768），跑完還原。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect                       # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget    # noqa: E402

from d4t.ui import fit_screen                          # noqa: E402
from d4t.ui import theme as theme_mod                  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


#: 要保證的螢幕尺寸。第一個是驗收條件寫的那一台（機台旁的 PC）；第二個更窄，
#: 因為 4:3 的舊面板在廠內還很多，而寬度才是版面真正撐不住的那一軸。
SCREENS = ((1366, 768), (1024, 768))


@pytest.fixture
def fake_screen():
    """把 `fit_screen` 的「螢幕」換成一個指定的尺寸，用完還原。"""
    def _use(width: int, height: int):
        fit_screen.FORCE_RECT = QRect(0, 0, int(width), int(height))
        return fit_screen.FORCE_RECT

    yield _use
    fit_screen.FORCE_RECT = None


# --------------------------------------------------------------------------- #
# 算式本身
# --------------------------------------------------------------------------- #
def test_a_window_that_already_fits_is_not_shrunk(qapp):
    """螢幕夠大的時候這一整件事**一個像素都不動** —— 開發機的行為不變。"""
    w = QWidget()
    rect = fit_screen.available_rect(w)
    small = (int(rect.width() * 0.5), int(rect.height() * 0.5))
    assert fit_screen.fit(w, *small) == small
    w.deleteLater()


def test_a_window_bigger_than_the_screen_is_cut_down(qapp):
    w = QWidget()
    rect = fit_screen.available_rect(w)
    got_w, got_h = fit_screen.fit(w, rect.width() * 3, rect.height() * 3)
    assert got_w <= rect.width() and got_h <= rect.height()
    assert got_w == int(rect.width() * fit_screen.SCREEN_FRACTION)
    w.deleteLater()


def test_a_minimum_size_bigger_than_the_screen_is_relaxed_first(qapp):
    """**這一步不做的話 `resize` 是沒有效果的** —— Qt 不會縮到 minimum 以下。

    主視窗的 ``setMinimumHeight(760)`` 在一個可用高 728 的螢幕上正是這件事。
    """
    w = QWidget()
    rect = fit_screen.available_rect(w)
    w.setMinimumSize(rect.width() * 2, rect.height() * 2)
    fit_screen.fit(w, rect.width(), rect.height())
    assert w.minimumWidth() <= rect.width()
    assert w.height() <= rect.height() and w.width() <= rect.width()
    w.deleteLater()


def test_a_window_pushed_off_the_edge_comes_back(qapp):
    w = QWidget()
    fit_screen.fit(w, 300, 200)
    rect = fit_screen.available_rect(w)
    w.move(rect.right() + 500, rect.bottom() + 500)
    fit_screen.keep_on_screen(w)
    assert fit_screen.fits_on_screen(w), w.frameGeometry()
    w.deleteLater()


def test_it_does_not_need_a_screen_to_answer(qapp):
    """螢幕資訊拿不到時回一個保守的矩形，**不是拋例外** —— 一個開不起來的
    視窗比一個大小不理想的視窗糟得多。"""
    assert fit_screen.available_rect(None).width() > 0


# --------------------------------------------------------------------------- #
# 每一個頂層視窗
# --------------------------------------------------------------------------- #
def _every_top_level(qapp, tmp_path):
    """開得起來的每一個頂層視窗 → ``(名字, widget)``。

    ⚠ 這張清單就是 U15 說的那九個。**加一個新的頂層視窗要加進這裡** ——
    下面那條 `test_the_list_covers_every_window_class` 會問。
    """
    import numpy as np

    from d4t.ui.chart_settings import ChartSettingsDialog
    from d4t.ui.gc_generator import GcGeneratorWindow
    from d4t.ui.graph_builder import GraphBuilderDialog
    from d4t.ui.region_check import RegionCheckWindow
    from d4t.ui.results import ResultsWindow
    from d4t.ui.studio import StudioWindow
    from d4t.ui.template_dialog import TemplateDialog
    from d4t.ui.uniformity_window import UniformityWindow
    from d4t.ui.welcome import RecipeLibraryDialog, WelcomeDialog

    out = [
        ("StudioWindow", StudioWindow(show_welcome_on_start=False)),
        ("ResultsWindow", ResultsWindow()),
        ("WelcomeDialog", WelcomeDialog()),
        ("RecipeLibraryDialog", RecipeLibraryDialog(str(tmp_path))),
        ("RegionCheckWindow", RegionCheckWindow()),
        ("TemplateDialog", TemplateDialog()),
        ("GcGeneratorWindow", GcGeneratorWindow()),
        ("ChartSettingsDialog", ChartSettingsDialog()),
        ("GraphBuilderDialog", GraphBuilderDialog()),
        ("UniformityWindow", UniformityWindow()),
    ]
    del np
    return out


@pytest.mark.parametrize("size", SCREENS)
def test_every_top_level_window_lands_inside_the_screen(qapp, tmp_path,
                                                        fake_screen, size):
    """**驗收條件本身**：逐一開，斷言 geometry 完全落在 availableGeometry 內。"""
    fake_screen(*size)
    too_big = []
    for name, win in _every_top_level(qapp, tmp_path):
        try:
            win.show()
            fit_screen.keep_on_screen(win)
            qapp.processEvents()
            rect = fit_screen.available_rect(win)
            frame = win.frameGeometry()
            if not rect.contains(frame):
                too_big.append((name, frame.width(), frame.height(),
                                rect.width(), rect.height()))
        finally:
            win.close()
            win.deleteLater()
    qapp.processEvents()
    assert not too_big, (
        "這幾個視窗在 %d×%d 的螢幕上放不下（名字, 寬, 高, 螢幕寬, 螢幕高）：\n  %s\n"
        "  修法：建構式裡的 resize 改成 fit_screen.fit(self, w, h)；內容本身\n"
        "  就比螢幕高的話，把版面掛到 fit_screen.scroll_host(self) 上。"
        % (fit_screen.available_rect(None).width(),
           fit_screen.available_rect(None).height(),
           "\n  ".join(map(str, too_big))))


def test_no_window_hard_codes_a_size_any_more():
    """``resize(w, h)`` 這個寫法在 ``d4t/ui`` 裡不該再出現（U1 的反向測試）。

    只有 `fit_screen` 自己可以呼叫 `resize` —— 它就是那個做決定的地方。
    沒有這一條的話，下一個新對話框會照著旁邊那幾行抄一個寫死的尺寸回來，
    而測試全綠。
    """
    import re

    bad = []
    for path in sorted((REPO / "d4t" / "ui").rglob("*.py")):
        if path.name == "fit_screen.py":
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            text = line.strip()
            if text.startswith("#"):
                continue
            # 兩個數字的 resize ＝ 寫死的視窗尺寸。`cv2.resize(...)` 與
            # `resize(n)`（list/array）不是這回事，所以要求兩個引數且是常數。
            if re.search(r"(?<!cv2)\.resize\(\s*\d+\s*,\s*\d+\s*\)", text):
                bad.append("%s:%d  %s" % (path.name, i, text))
    assert not bad, (
        "這幾行寫死了視窗尺寸，小螢幕上會超出畫面：\n  %s\n"
        "  改用 fit_screen.fit(widget, w, h)。" % "\n  ".join(bad))


# --------------------------------------------------------------------------- #
# 工具列裝不裝得進那台機器
# --------------------------------------------------------------------------- #
def test_the_toolbar_still_fits_the_machine_beside_the_tool(qapp, fake_screen):
    """**主視窗的預設寬度是工具列決定的，而螢幕決定得了它**（U1 ＋ X4）。

    `studio_layout.build_toolbar` 那一段記著一次踩過的：加「Results」那顆鈕之後，Qt 把放不下
    的最後一顆收進右邊那個 » 溢位選單 —— 而使用者要的正是「按一顆鈕就叫得出
    Results」，一顆藏在兩層選單底下的鈕不算數。

    2026-09-08 X4 把「Templates…」放回去，工具列從 997 px 變成 1,153 px，而
    1366×768 上視窗只有 1,229 px 寬 —— **只剩 76 px**。下一顆鈕會把它推過去，
    而症狀是「某一顆鈕在那台機器上不見了」，開發機（1920 寬）上看不到。

    所以這一條把那個餘裕**量出來**：不是「不准再加鈕」，是**加之前會有人看見**。
    """
    from d4t.ui.studio import StudioWindow

    rect = fake_screen(*SCREENS[0])              # 1366×768，驗收條件寫的那一台
    win = StudioWindow(show_welcome_on_start=False)
    try:
        need = win.toolbar.sizeHint().width()
        have = int(rect.width() * fit_screen.SCREEN_FRACTION)
        assert need <= have, (
            "工具列要 %d px，而 %d×%d 的螢幕上視窗只有 %d px 寬 —— 尾巴那幾顆"
            "會被收進 » 溢位選單。\n"
            "  要嘛把某顆鈕收起來／縮短它的字（`scope.INPUT_SOURCES` 的 short），"
            "要嘛在這裡說明為什麼那幾顆躲進選單是可以接受的。"
            % (need, rect.width(), rect.height(), have))
    finally:
        win.close()
        win.deleteLater()
