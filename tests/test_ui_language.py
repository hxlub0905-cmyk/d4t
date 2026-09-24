# 評價清單 #6：工具列上一顆鈕切換介面語言（English ⇄ 中文），偏好存 QSettings。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme
    # QSettings 不准弄髒開發機（同 test_ui_welcome）。
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(tmp_path_factory.mktemp("qsettings")))
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "light")
    yield app


@pytest.fixture(autouse=True)
def english_after(qapp):
    from d4t.ui import language, strings
    yield
    language.save("en")
    strings.install("en")


def test_the_chinese_catalog_ships(qapp):
    from d4t.ui import strings
    assert "zh_TW" in strings.available()


def test_the_button_names_the_language_it_switches_to(qapp):
    from d4t.ui import language, strings
    strings.install("en")
    assert language.button_text() == "中文"
    strings.install("zh_TW")
    assert language.button_text() == "EN"


def test_toggle_saves_and_the_next_start_applies_it(qapp):
    from d4t.ui import language, strings
    strings.install("en")
    assert language.toggle(None) == "zh_TW"      # ASK 在 conftest 關掉 → 只存
    assert language.saved() == "zh_TW"
    assert language.apply_saved() == "zh_TW"
    assert strings.tr("Nothing to undo.") != "Nothing to undo.", "真的換成譯文"


def test_a_missing_catalog_falls_back_to_english(qapp):
    from d4t.ui import language
    language.save("xx_NOPE")
    assert language.saved() == "en"


def test_the_button_is_on_the_toolbar(qapp):
    from d4t.ui import strings, studio
    strings.install("en")
    win = studio.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.btn_lang.text() == "中文"
        assert win.btn_lang.toolTip()
        assert win.toolbar.widgetForAction(
            next(a for a in win.toolbar.actions()
                 if win.toolbar.widgetForAction(a) is win.btn_lang)) is win.btn_lang
    finally:
        win.close()


def test_relaunch_uses_the_package_not_the_file(monkeypatch):
    from d4t.ui import language
    monkeypatch.setattr(sys, "argv", ["/x/repo/d4t/__main__.py", "gui"])
    prog, args, cwd = language._relaunch_command()
    assert args == ["-m", "d4t", "gui"] and cwd == "/x/repo"
