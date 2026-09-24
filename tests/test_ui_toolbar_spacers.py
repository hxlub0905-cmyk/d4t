# F117 E6：工具列上的撐開空白要叫 `toolbarSpacer`，不然主題把它畫成一條灰框。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "light")
    yield app


def _bad_spacers(bar):
    from PySide6.QtWidgets import QSizePolicy, QWidget
    out = []
    for w in bar.findChildren(QWidget):
        if (type(w) is QWidget
                and w.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding
                and w.objectName() != "toolbarSpacer"):
            out.append(w)
    return out


def test_every_toolbar_spacer_is_the_transparent_one(qapp):
    from d4t.ui import studio
    win = studio.StudioWindow(show_welcome_on_start=False)
    try:
        assert not _bad_spacers(win.toolbar)
        assert not _bad_spacers(win.results.toolbar), \
            "Results 的撐開空白沒名字 → 一條灰框（E6）"
    finally:
        win.close()


def test_the_theme_really_makes_that_name_transparent():
    src = (REPO / "d4t" / "ui" / "theme.py").read_text(encoding="utf-8")
    assert "QWidget#toolbarSpacer { background: transparent" in src
