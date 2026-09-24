# 介面語言的開關 — authored 2026-09-24（評價清單 #6）.
"""**工具列右邊一顆鈕切換介面語言**（English ⇄ 中文），偏好存在 QSettings。

翻譯機制（`strings.tr()` ＋ `locales/<code>.json`）F117 就在了，但**從來沒有
人呼叫 `strings.install()`** —— 畫面上永遠是英文。這一支補的是那個開關；
**譯文的內容**照 F117 H5 的定調，等目標使用者試用過再補（`tools/i18n_todo.py`
列得出還缺哪些句子），所以切到中文之後目前只有一部分字會變。

為什麼切換要重開
----------------
`tr()` 是**建構時**讀的：每一顆鈕、每一句說明在建出來的那一刻就定了字。
要當場換，得把每一個已經建好的 widget 的字重設一遍 —— 那是一份會永遠漏掉
幾個的名單。重開一次（先照常問要不要存 recipe）便宜得多，而且保證整個畫面
是同一種語言。

⚠ 會跳 modal 的東西要有關得掉的旗標（`CLAUDE.md` §4）：:data:`ASK`。
關著的時候只存偏好、不問也不重開（`tests/conftest.py` 關掉它）。
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

from . import strings

__all__ = ["ASK", "SETTINGS_KEY", "LABELS", "saved", "save", "apply_saved",
           "next_locale", "button_text", "toggle"]

#: 關掉＝切換時不問、不重開（headless 測試用）。
ASK = True

SETTINGS_KEY = "ui/language"

#: 認得的語言。鈕上顯示的字是**「按下去會切到的那一種」的自稱**（跟主題鈕
#: 同一個慣例）—— 使用者要找的是「中文」這兩個字，不是「現在是 EN」。
#:
#: ⚠ **自稱與對話框的譯文住在那份翻譯檔裡，不住在這裡**：UI 字串一律英文
#: （`tests/test_ui_english_only.py`，M7 使用者：「中英夾雜很混亂」），中文只
#: 准出現在 `locales/zh_TW.json`。鍵是 :data:`NAME_KEY`。
LABELS: Dict[str, str] = {"en": "EN", "zh_TW": "zh_TW"}

#: 翻譯檔裡「這種語言叫什麼」的那一列（值＝鈕上的字）。
NAME_KEY = "Language name (shown on the language button)"


def _settings():
    from .welcome import app_settings
    return app_settings()


def saved() -> str:
    """存著的語言；沒存過、或那份翻譯檔不在了 → ``en``。"""
    try:
        code = str(_settings().value(SETTINGS_KEY, strings.DEFAULT_LOCALE) or "")
    except Exception:
        return strings.DEFAULT_LOCALE
    return code if code in strings.available() else strings.DEFAULT_LOCALE


def save(code: str) -> None:
    s = _settings()
    s.setValue(SETTINGS_KEY, str(code))
    s.sync()


def apply_saved() -> str:
    """啟動時呼叫（**在建任何視窗之前** —— `tr()` 是建構時讀的）。"""
    return strings.install(saved())


def _choices() -> List[str]:
    return [c for c in LABELS if c in strings.available()]


def next_locale(current: str) -> str:
    order = _choices() or [strings.DEFAULT_LOCALE]
    try:
        return order[(order.index(current) + 1) % len(order)]
    except ValueError:
        return order[0]


def said_in(code: str, text: str) -> str:
    """一句英文在**另一種語言**裡怎麼說（還沒切過去，所以不能用 `tr()`）。"""
    if code == strings.DEFAULT_LOCALE:
        return text
    import json

    try:
        raw = json.loads((strings.LOCALE_DIR / ("%s.json" % code))
                         .read_text(encoding="utf-8"))
    except Exception:
        return text
    got = raw.get(text) if isinstance(raw, dict) else None
    return str(got) if got and str(got).strip() else text


def button_text() -> str:
    """鈕上的字 = 按下去會切到的那一種語言的自稱。"""
    nxt = next_locale(strings.current())
    if nxt == strings.DEFAULT_LOCALE:
        return LABELS["en"]
    name = said_in(nxt, NAME_KEY)
    return name if name != NAME_KEY else LABELS.get(nxt, nxt)


def _relaunch_command():
    """重開用的指令：``(程式, 參數, 工作目錄)``。

    ⚠ ``python -m d4t gui`` 啟動時 ``sys.argv[0]`` 是 ``…/d4t/__main__.py``，
    直接拿它重跑會變成「跑一個檔案」而不是「跑一個套件」，import 會失敗。
    那種情況改回 ``-m d4t``，並站在套件的上一層。
    """
    import os

    argv = list(sys.argv) or ["d4t"]
    here = os.path.abspath(argv[0])
    if os.path.basename(here) == "__main__.py":
        pkg_parent = os.path.dirname(os.path.dirname(here))
        return sys.executable, ["-m", "d4t"] + argv[1:], pkg_parent
    return sys.executable, argv, os.getcwd()


def toggle(window: Any) -> str:
    """切到下一種語言：存偏好，問要不要現在重開。回傳新的語言代碼。"""
    nxt = next_locale(strings.current())
    save(nxt)
    if not ASK:
        return nxt
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QMessageBox

    # 對話框用**要切過去的那一種語言**講（使用者切到中文就是想讀中文）。
    def say(text: str) -> str:
        return said_in(nxt, text)

    box = QMessageBox(window)
    box.setWindowTitle(say("Switch language"))
    box.setText(say("The interface will switch language (only part of it is "
                    "translated so far). Restart d4t now?\n(You will be asked "
                    "to save an unsaved recipe first.)"))
    btn_now = box.addButton(say("Restart now"), QMessageBox.AcceptRole)
    box.addButton(say("Next time I open d4t"), QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is btn_now and window.close():
        # 先關（使用者可能在「要不要存」那一步反悔），關成了才開新的。
        prog, args, cwd = _relaunch_command()
        QProcess.startDetached(prog, args, cwd)
    else:
        window._status(say("Language saved - it changes the next time d4t "
                           "opens."))
    return nxt
