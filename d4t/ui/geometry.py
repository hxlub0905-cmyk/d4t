# d4t Studio：視窗記得自己上次多大、在哪 — authored 2026-09-20 (F117 I16).
"""**每一個子視窗每次開都回到預設大小。**

走查（F117 I16）記的是三個：Results、Chart settings、範本庫。`d4t/ui` 裡
一個 `saveGeometry` 都沒有 —— 而這三個都是「調整半天、關掉、再開」的東西：
Results 拉寬是為了看得到欄，Chart settings 拉高是為了看得到預覽。每次回到
預設，等於每次重做一遍那個動作。

⚠ **記回來之前要先確定它還在螢幕上**（`fit_screen.keep_on_screen`）。
一個在雙螢幕上拉到第二個螢幕的視窗，拔掉螢幕之後還原出來是**看不見的**
—— 那時候使用者按了「Results」而什麼都沒發生，沒有任何線索。

⚠ **測試不准寫進使用者真正的設定檔**（CLAUDE.md §4 的第三條）。這一支是
「第四個會寫磁碟的東西」，所以它跟前三個（`crashlog.LOG_DIR`、
`autosave.DIR`、`BaselineStore(settings)`）一樣**先做出覆寫點**：
:data:`SETTINGS`。沒有覆寫、而且正在跑測試的時候，讀寫兩邊都是 no-op。
"""
from __future__ import annotations

from typing import Any, Optional

from d4t.core.log import swallowed

from . import fit_screen
from .welcome import app_settings

__all__ = ["remember", "restore", "SETTINGS", "key_for"]

#: ⚠ **覆寫點**：測試把它指到自己的 `QSettings`（一個 tmp_path 底下的 INI），
#: 就可以真的驗「存了、讀得回來」而不碰使用者的檔案。
SETTINGS: Optional[Any] = None

#: QSettings 裡的前綴（跟 `ui/columns`、釘住的基準線同一組設定）。
PREFIX = "ui/geometry/"


def _running_under_pytest() -> bool:
    import sys
    return "pytest" in sys.modules


def _store() -> Optional[Any]:
    """要寫去哪。覆寫優先；沒有覆寫又在跑測試就**什麼都不做**。"""
    if SETTINGS is not None:
        return SETTINGS
    if _running_under_pytest():
        return None
    return app_settings()


def key_for(name: str) -> str:
    """一個視窗的鍵。**名字自己取**，不要用 class 名字。

    class 改名是重構，而重構不該讓使用者的視窗大小消失。
    """
    return "%s%s" % (PREFIX, str(name or "window"))


def remember(widget: Any, name: str) -> bool:
    """把這個視窗現在的大小與位置存起來（關窗時叫）。回傳有沒有真的存。

    ⚠ **最小化／全螢幕的時候不存**：存下來的是一個 0×0 或整個螢幕的幾何，
    而下一次開起來使用者會以為視窗壞了。那兩種狀態下保留上一次的值。
    """
    store = _store()
    if store is None or widget is None:
        return False
    try:
        if widget.isMinimized() or widget.isFullScreen():
            return False
        store.setValue(key_for(name), widget.saveGeometry())
    except Exception:          # 設定寫不動不准擋住關窗
        swallowed("geometry.remember")
        return False
    return True


def restore(widget: Any, name: str) -> bool:
    """還原大小與位置；**還原完一定推回螢幕裡**。回傳有沒有真的還原。

    沒存過、讀不動、或還原出來整個在螢幕外 —— 三種都回 False，而呼叫端那時
    候就照它自己的預設（`fit_screen.fit`）。
    """
    store = _store()
    if store is None or widget is None:
        return False
    try:
        blob = store.value(key_for(name))
        if not blob or not widget.restoreGeometry(blob):
            return False
    except Exception:
        swallowed("geometry.restore")
        return False
    # ⚠ 拔掉第二個螢幕之後，存下來的位置會落在沒有螢幕的地方 —— 還原出來
    # 是一個看不見的視窗，而使用者按了按鈕什麼都沒發生。
    fit_screen.keep_on_screen(widget)
    return True
