# -*- coding: utf-8 -*-
"""**使用手冊在 app 裡打得開**（F117 K1）。

走查那一列寫的是「`docs/USING-*.md` 在 repo 裡，廠內使用者不會去翻」。那句話
底下有兩個不同的問題，而這一支兩個都要答：

1. **他不知道有這份東西。** 入口要長在**用得到它的那張卡上** —— 選了 CD 卡的
   人才需要 `USING-CD.md`，而工具列上一顆「Help」對他沒有意義。
2. **他打不開。** 那是一份 Markdown，而公司機上不保證有任何一個看得懂 `.md`
   的程式 —— 雙擊下去可能跳出記事本、可能跳出「要用什麼開啟」。所以這裡
   **自己畫**（`QTextBrowser.setMarkdown`）：離線、本機、不依賴外面任何東西。

⚠ **不准把檔案丟給系統去開**（`QDesktopServices.openUrl`）。那一步會把一個
本機檔案交給一個我們不知道是什麼的程式，而在一台受限的機器上那是一件會失敗
得很難看的事 —— 失敗的時候畫面上什麼都不會發生。

哪一張卡配哪一份手冊寫在**卡片自己身上**（:attr:`Step.manual`），不在這裡：
一張 UI 這邊的對照表會變成「按卡片名字分支」的第 N 處，而且卡片改名的那天
沒有人會想到去改它。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
    QWidget,
)

from . import strings

#: 手冊放哪（測試的覆寫點 —— 同 `crashlog.LOG_DIR` 的規矩）。``None`` = 用
#: 套件旁邊那一份：`bundle/d4t_bundle.py` 會把 `docs/` 一起帶過去，所以公司機
#: 上它就在 `d4t/` 的隔壁。
DOCS_DIR: Optional[Path] = None

#: 手冊的檔名長什麼樣 —— 「有沒有手冊」與「反向測試數得出幾份」共用這一條。
PREFIX = "USING-"

_TITLES: Dict[str, str] = {}


def docs_dir() -> Path:
    if DOCS_DIR is not None:
        return Path(DOCS_DIR)
    return Path(__file__).resolve().parents[2] / "docs"


def path_for(name: str) -> Optional[Path]:
    """``"USING-CD.md"`` → 那個檔案；不在就回 ``None``（**不炸**）。

    ⚠ 只認**檔名**，不認路徑：`name` 是卡片宣告的字串，而一個卡片宣告的字串
    不該有本事讀到 `docs/` 以外的任何東西。
    """
    base = Path(str(name or "")).name
    if not base:
        return None
    path = docs_dir() / base
    return path if path.is_file() else None


def title_of(name: str) -> str:
    """手冊的標題（檔案裡第一個 ``# `` 開頭那一行）。讀不到就退回檔名。"""
    key = Path(str(name or "")).name
    path = path_for(key)
    # ⚠ **快取的鍵是整條路徑**，不是檔名：`DOCS_DIR` 是可以被換掉的（測試的
    # 覆寫點），而一個只記檔名的快取會在換了目錄之後回答上一個目錄的答案。
    cache_key = str(path) if path is not None else key
    if cache_key in _TITLES:
        return _TITLES[cache_key]
    title = key
    if path is not None:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip() or key
                    break
        except OSError:
            title = key
    _TITLES[cache_key] = title
    return title


def manuals() -> List[Tuple[str, str]]:
    """``docs/`` 底下所有的手冊：``[(檔名, 標題), …]``。"""
    root = docs_dir()
    if not root.is_dir():
        return []
    return [(p.name, title_of(p.name))
            for p in sorted(root.glob("%s*.md" % PREFIX))]


class ManualDialog(QDialog):
    """一份手冊，**自己畫**。

    modal：進來讀一段、出去改參數 —— 它不是拿來跟主視窗並排的（U15 那張表
    上就是這樣表態的）。
    """

    def __init__(self, name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._name = Path(str(name or "")).name
        self.setModal(True)
        self.setWindowTitle(title_of(self._name))
        from . import fit_screen

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.view = QTextBrowser(self)
        self.view.setOpenExternalLinks(False)
        self.view.setOpenLinks(False)          # 連結由 `_on_link` 自己收
        self.view.anchorClicked.connect(self._on_link)
        lay.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.where = QLabel("", self)
        self.where.setObjectName("paramHint")
        self.where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.where, 1)
        close = QPushButton(strings.tr("Close"), self)
        close.clicked.connect(self.close)
        row.addWidget(close, 0)
        lay.addLayout(row)

        self.load(self._name)
        fit_screen.fit(self, 820, 640)

    # ---- 對外 -------------------------------------------------------------
    def name(self) -> str:
        return self._name

    def load(self, name: str) -> None:
        """換一份手冊（同一個視窗）—— 手冊之間互相連結的時候走這裡。"""
        self._name = Path(str(name or "")).name
        path = path_for(self._name)
        if path is None:
            # ⚠ **講得出它找過哪裡**：手冊沒跟著搬過來的時候，「打不開」與
            # 「我找錯地方」是兩件完全不同的事，而使用者要回報的正是那條路徑。
            self.view.setPlainText(strings.tr(
                "This manual is not installed next to the program."))
            self.where.setText("%s  %s" % (
                strings.tr("Looked in:"), docs_dir()))
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:   # UI 邊界：讀不到也只是一句話
            self.view.setPlainText("%s\n\n%s" % (
                strings.tr("This manual could not be read."), e))
            self.where.setText(str(path))
            return
        self.view.setMarkdown(text)
        self.view.moveCursor(QTextCursor.MoveOperation.Start)
        self.setWindowTitle(title_of(self._name))
        self.where.setText(str(path))

    # ---- 內部 -------------------------------------------------------------
    def _on_link(self, url: QUrl) -> None:
        """⚠ **只跟得動 `docs/` 裡的另一份手冊，其他一律不動。**

        手冊裡有指向原始碼與外部網址的連結。把它們交給作業系統去開，等於在
        一台受限的機器上按下一個我們不知道會發生什麼的按鈕 —— 而使用者按的
        時候以為自己只是在讀一份說明。
        """
        target = Path(str(url.toString() or "")).name
        if target.startswith(PREFIX) and path_for(target) is not None:
            self.load(target)


def show(name: str, parent: Optional[QWidget] = None) -> ManualDialog:
    dlg = ManualDialog(name, parent)
    dlg.exec()
    return dlg
