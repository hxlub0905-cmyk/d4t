# `.raw` 版面表單（2026-09-24）：四格一次填、對不上大小就不准按 OK、看得到圖。
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
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


@pytest.fixture
def raw_file(tmp_path):
    """120 × 50 的 16-bit、32-byte 檔頭 —— 不是正方形，所以大小推不出它。"""
    img = (np.arange(50 * 120, dtype="<u2").reshape(50, 120) * 7) % 4096
    p = tmp_path / "a.raw"
    p.write_bytes(b"\0" * 32 + img.astype("<u2").tobytes())
    return str(p)


def test_ok_is_off_until_the_layout_matches_the_file(qapp, raw_file):
    from d4t.ui.raw_dialog import RawLayoutDialog

    dlg = RawLayoutDialog(raw_file)
    assert not dlg.btn_ok.isEnabled(), "預設的 1024×1024 對不上，不准按"
    assert "+" in dlg.lbl_check.text() or "-" in dlg.lbl_check.text(), "要講差多少"
    assert dlg.preview.pixmap().isNull()
    dlg.sp_width.setValue(120)
    dlg.sp_header.setValue(32)
    dlg.sp_height.setValue(50)
    assert dlg.matches() and dlg.btn_ok.isEnabled()
    assert not dlg.preview.pixmap().isNull(), "對上了就畫得出圖"
    s = dlg.spec()
    assert (s.width, s.height, s.header, s.bits) == (120, 50, 32, 16)


def test_height_from_file_size(qapp, raw_file):
    from d4t.ui.raw_dialog import RawLayoutDialog

    dlg = RawLayoutDialog(raw_file)
    dlg.sp_width.setValue(120)
    dlg.sp_header.setValue(32)
    dlg.fit_height()
    assert dlg.sp_height.value() == 50 and dlg.btn_ok.isEnabled()
    # 除不盡：不亂填，講為什麼
    dlg.sp_width.setValue(77)
    before = dlg.sp_height.value()
    dlg.fit_height()
    assert dlg.sp_height.value() == before
    assert "multiple" in dlg.lbl_check.text()


def test_the_read_spec_actually_reads_the_file(qapp, raw_file):
    """表單交出去的那一組要讀得出原圖（不是只有大小對）。"""
    from d4t.core.ingest.rawfile import read_raw
    from d4t.ui.raw_dialog import RawLayoutDialog

    dlg = RawLayoutDialog(raw_file)
    dlg.sp_width.setValue(120)
    dlg.sp_header.setValue(32)
    dlg.fit_height()
    img = read_raw(raw_file, dlg.spec())
    assert img.shape == (50, 120) and int(img[1, 0]) == (120 * 7) % 4096


def test_starts_from_the_guess_when_there_is_one(qapp, tmp_path):
    from d4t.core.ingest.rawfile import RawSpec
    from d4t.ui.raw_dialog import RawLayoutDialog

    p = tmp_path / "sq.raw"
    p.write_bytes(np.zeros((64, 64), "<u2").tobytes())
    dlg = RawLayoutDialog(str(p), initial=RawSpec(width=64, height=64))
    assert dlg.btn_ok.isEnabled()
