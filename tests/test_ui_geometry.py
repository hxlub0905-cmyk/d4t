# F117 I16：子視窗記得自己上次多大、在哪（2026-09-20）。
"""走查記的三個：Results、Chart settings、範本庫 —— `d4t/ui` 裡一個
`saveGeometry` 都沒有。這三個都是「調整半天、關掉、再開」的東西：Results
拉寬是為了看得到欄，Chart settings 拉高是為了看得到預覽。每次回到預設，
等於每次重做一遍那個動作。

⚠ **測試不准寫進使用者真正的設定檔**（CLAUDE.md §4 的第三條）。`geometry`
是「第四個會寫磁碟的東西」，所以它跟前三個一樣先做出覆寫點
（`geometry.SETTINGS`）—— 這一支就是那個覆寫點的第一個使用者。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings                 # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from d4t.ui import geometry                          # noqa: E402
from d4t.ui import theme as theme_mod                # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """一份**自己的** QSettings —— 不碰使用者那一份。"""
    s = QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)
    monkeypatch.setattr(geometry, "SETTINGS", s)
    yield s


# --------------------------------------------------------------------------- #
# 1. 存得下、讀得回
# --------------------------------------------------------------------------- #
def test_a_window_comes_back_the_size_it_was_left(qapp, store):
    w = QWidget()
    w.resize(753, 431)
    assert geometry.remember(w, "probe") is True

    again = QWidget()
    assert geometry.restore(again, "probe") is True
    assert again.size().width() == 753 and again.size().height() == 431
    w.deleteLater()
    again.deleteLater()


def test_a_window_nobody_saved_is_left_alone(qapp, store):
    """沒存過就回 False —— 呼叫端那時候照它自己的 `fit_screen.fit`。"""
    w = QWidget()
    w.resize(300, 200)
    assert geometry.restore(w, "never-saved") is False
    assert w.size().width() == 300, "沒存過卻動了視窗"
    w.deleteLater()


# --------------------------------------------------------------------------- #
# 2. 兩個會安靜做錯的狀態
# --------------------------------------------------------------------------- #
def test_a_minimised_window_does_not_overwrite_a_good_size(qapp, store):
    """⚠ 最小化的時候存下來的是一個沒有用的幾何。

    下一次開起來使用者會以為視窗壞了 —— 而他上一次真的調過的那個大小已經
    被蓋掉了。
    """
    w = QWidget()
    w.resize(900, 600)
    geometry.remember(w, "probe")
    # ⚠ 比的是「還原出來的那個大小」而不是 900 —— `keep_on_screen` 會把比
    # 螢幕大的視窗縮進來（offscreen 平台的螢幕是 800 寬），而那是它的工作。
    before = QWidget()
    geometry.restore(before, "probe")
    good = before.size()

    w.showMinimized()
    if w.isMinimized():                 # offscreen 平台不一定真的最小化得了
        assert geometry.remember(w, "probe") is False
    again = QWidget()
    geometry.restore(again, "probe")
    assert again.size() == good, "最小化那一下把好好的大小蓋掉了"
    for x in (w, before, again):
        x.deleteLater()


def test_restoring_pushes_the_window_back_onto_a_screen(qapp, store,
                                                        monkeypatch):
    """⚠ **拔掉第二個螢幕之後，存下來的位置會落在沒有螢幕的地方。**

    還原出來是一個看不見的視窗，而使用者按了按鈕什麼都沒發生 —— 沒有任何
    線索。所以還原完一定過一次 `fit_screen.keep_on_screen`。
    """
    called = []
    monkeypatch.setattr(geometry.fit_screen, "keep_on_screen",
                        lambda w: called.append(w))
    w = QWidget()
    w.resize(500, 400)
    geometry.remember(w, "probe")
    again = QWidget()
    geometry.restore(again, "probe")
    assert called == [again], "還原之後沒有推回螢幕裡"
    w.deleteLater()
    again.deleteLater()


# --------------------------------------------------------------------------- #
# 3. 覆寫點真的是覆寫點
# --------------------------------------------------------------------------- #
def test_without_an_override_a_test_run_writes_nothing(qapp, monkeypatch):
    """**沒有覆寫、而且在跑測試 → 讀寫都是 no-op。**

    這一條就是 CLAUDE.md 那條「測試不准寫進使用者真正的檔案」的證據。
    """
    monkeypatch.setattr(geometry, "SETTINGS", None)
    w = QWidget()
    w.resize(640, 480)
    assert geometry.remember(w, "probe") is False
    assert geometry.restore(w, "probe") is False
    w.deleteLater()


def test_the_key_is_a_name_we_chose_not_a_class_name():
    """class 改名是重構，而重構不該讓使用者的視窗大小消失。"""
    assert geometry.key_for("results").endswith("results")
    assert geometry.key_for("results") != geometry.key_for("chart_settings")
