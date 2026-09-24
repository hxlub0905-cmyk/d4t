# 長的動作失敗了要當面講 — authored 2026-09-24（評價清單 #5）.
"""**Run all 與寫出檔案失敗時，跳一個說得清楚的對話框。**

其他失敗照舊只在狀態列（那裡有歷史，`status_log.py`）；只有這兩種升級成對話框，
因為它們的共同點是**使用者按下去之後通常走開了**：一整批跑幾分鐘、寫報表寫幾千
張圖。回來的時候狀態列上那一行紅字可能已經被下一句蓋掉、或被截斷，而「那一批
到底有沒有成功」是他最需要知道的一件事。

對話框講四件事：發生什麼、可能的原因、可以怎麼做、詳細的紀錄在哪（一顆鈕打開
那個資料夾）。

⚠ **會跳 modal 的東西要有關得掉的旗標**（`CLAUDE.md` §4）：:data:`SHOW`。
`tests/conftest.py` 把它關掉，要驗對話框本身的測試自己打開。關著的時候
:func:`tell` 仍然回傳它**會**說的那些字，所以測試驗得到內容。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from . import strings

__all__ = ["SHOW", "tell", "compose"]

#: 關掉＝不跳對話框（headless 測試用）。同 `crashlog.SHOW_DIALOG`。
SHOW = True


def compose(what: str, detail: str, tips: Sequence[str],
            log_folder: str = "") -> Dict[str, str]:
    """組出對話框上的字（純函式，測試用）。"""
    body = str(detail or "").strip()
    lines = ["• %s" % strings.tr(t) for t in tips if str(t).strip()]
    info = ""
    if lines:
        info = strings.tr("What you can try:") + "\n" + "\n".join(lines)
    if log_folder:
        info += ("\n\n" if info else "") + strings.tr(
            "The full details are in the log (d4t.log) in:") + "\n" + log_folder
    return {"title": strings.tr(what), "text": body, "info": info}


def tell(parent: Any, what: str, detail: str, tips: Sequence[str],
         log_folder: Optional[str] = None) -> Dict[str, str]:
    """跳對話框（:data:`SHOW` 開著時），回傳上面的字。"""
    if log_folder is None:
        from . import crashlog
        log_folder = crashlog.log_dir()
    said = compose(what, detail, tips, log_folder or "")
    if not SHOW:
        return said
    from PySide6.QtWidgets import QMessageBox

    from .status_action import open_folder

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(said["title"])
    box.setText(said["title"] + "\n\n" + said["text"])
    box.setInformativeText(said["info"])
    btn_log = None
    if log_folder:
        btn_log = box.addButton(strings.tr("Open the log folder"),
                                QMessageBox.ActionRole)
    box.addButton(QMessageBox.Close)
    box.exec()
    if btn_log is not None and box.clickedButton() is btn_log:
        open_folder(log_folder)
    return said
