# ADEPT Studio 進入點 — authored 2026-07-28 (M3).
"""``python -m adept.ui.app`` —— 開一個 ADEPT Studio 視窗。

薄薄一層：建 QApplication → 套主題 → 開主視窗 → 進 event loop。
所有邏輯都在 :mod:`adept.ui.studio`，這裡刻意什麼都不做，
方便未來換成別的殼（嵌進廠內既有 app）時只改這一個檔。
"""
from __future__ import annotations

import sys
from typing import List, Optional, Sequence

from PySide6.QtWidgets import QApplication

from . import theme
from .branding import app_icon
from .studio import StudioWindow
from .welcome import saved_theme

__all__ = ["main"]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """開視窗並跑到使用者關掉為止；回傳 process exit code。"""
    args: List[str] = list(sys.argv if argv is None else argv)
    if not args:
        args = ["adept-studio"]

    app = QApplication.instance()
    if app is None:
        app = QApplication(args)
    # 設在 app 上而不是每個視窗上 —— 所有 top-level 視窗（Studio、Results、
    # 各種對話框）都會跟著繼承，之後開新視窗不必記得補一行。
    app.setWindowIcon(app_icon())
    theme.apply_theme(app, saved_theme(theme.DEFAULT_THEME))

    win = StudioWindow()
    win.resize(1440, 900)
    win.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
