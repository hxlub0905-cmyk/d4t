# -*- coding: utf-8 -*-
"""F60：「貼一張 GC 進來就產一批資料」那個視窗。

使用者 2026-08-28：「你可以製作一個產生器嗎（包含 UI）？如果我以後有其他
類似的 GC 也可以直接貼進去，模擬產生。」

這一支守的是**介面**這一層：貼得進來、量得出週期、預覽畫得出來、按鈕的狀態
誠實、跑起來不卡住 GUI。**產生邏輯本身不在這裡測** —— 它住在
`tools/make_lot_from_gc.py`，有 `tests/test_make_lot_from_gc.py` 的 12 條。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

pytest.importorskip("PySide6")


def _import_qt(g):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage
    from d4t.ui import gc_generator as mod
    from d4t.ui import theme
    g.update(QApplication=QApplication, QImage=QImage, mod=mod, theme=theme)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def gc_arr():
    import _synth_mgepi as mgepi
    G = mgepi.GEOMETRY
    return np.clip(mgepi.frame(int(G.epi_pitch * 2.2),
                               int(G.mg_pitch * G.period * 2.4), G),
                   0, 255).astype(np.uint8)


@pytest.fixture
def win(qapp):
    w = mod.GcGeneratorWindow()
    yield w
    w.close()


# --------------------------------------------------------------------------- #
# 1. 貼一張 GC 進來
# --------------------------------------------------------------------------- #
def test_a_pasted_colour_screenshot_becomes_a_sane_grayscale(qapp):
    """⚠ **截圖幾乎都是 32-bit ARGB，不是灰階。**

    直接把它的 `bits()` reshape 成 (h, w) 會拿到「寬度四倍、內容是交錯通道」
    的東西 —— 而那**看起來仍然像一張圖**（條紋狀），只是每個數字都不對。
    所以 `qimage_to_gray` 一定要先 `convertToFormat`。
    """
    img = QImage(37, 11, QImage.Format_ARGB32)
    img.fill(0xFF804020)
    arr = mod.qimage_to_gray(img)
    assert arr is not None
    assert arr.shape == (11, 37), "寬度不對 —— 大概是直接 reshape 了 BGRA"
    assert arr.dtype == np.uint8
    assert 1 <= int(arr.min()) == int(arr.max()) <= 254   # 單一顏色 → 單一灰階


def test_an_empty_clipboard_image_is_refused(qapp):
    assert mod.qimage_to_gray(QImage()) is None
    assert mod.qimage_to_gray(QImage(2, 2, QImage.Format_Grayscale8)) is None


def test_setting_a_gc_measures_the_period_and_draws_a_preview(win, gc_arr):
    assert win.set_gc(gc_arr, "unit") is True
    import _synth_mgepi as mgepi
    G = mgepi.GEOMETRY
    assert abs(win.sp_px.value() - G.mg_pitch * G.period) < 2.0
    assert abs(win.sp_py.value() - G.epi_pitch) < 2.0
    assert win.lbl_prev.pixmap() is not None
    assert not win.lbl_prev.pixmap().isNull()


def test_a_gc_that_is_too_small_is_refused(win):
    assert win.set_gc(np.zeros((4, 4), np.uint8)) is False


# --------------------------------------------------------------------------- #
# 2. 週期那一格
# --------------------------------------------------------------------------- #
def test_a_narrow_gc_says_so(win):
    """不到兩個週期寬的 GC 量不準是原理上的事 —— 畫面上要講出來。"""
    import _synth_mgepi as mgepi
    G = mgepi.GEOMETRY
    narrow = np.clip(mgepi.frame(int(G.epi_pitch * 2.2),
                                 int(G.mg_pitch * G.period * 1.16), G),
                     0, 255).astype(np.uint8)
    win.set_gc(narrow)
    assert "⚠" in win.lbl_warn.text()
    assert "across" in win.lbl_warn.text()


def test_a_wide_gc_does_not_cry_wolf(win, gc_arr):
    win.set_gc(gc_arr)
    assert "⚠" not in win.lbl_warn.text()


def test_the_label_is_plain_text_not_markdown(win, gc_arr):
    """QLabel 不是 Markdown —— 星號會原樣印出來（第一版就是那樣）。"""
    win.set_gc(gc_arr)
    for lbl in (win.lbl_warn, win.lbl_sites, win.lbl_gc_info):
        assert "**" not in lbl.text()


def test_editing_the_period_by_hand_redraws_the_preview(win, gc_arr):
    win.set_gc(gc_arr)
    before = win.lbl_prev.pixmap().toImage()
    win.sp_px.setValue(win.sp_px.value() * 0.5)
    after = win.lbl_prev.pixmap().toImage()
    assert before != after, "改了週期而預覽沒有跟著變"


# --------------------------------------------------------------------------- #
# 3. 按鈕的狀態
# --------------------------------------------------------------------------- #
def test_generate_stays_off_until_there_is_a_gc_and_a_folder(win, gc_arr, tmp_path):
    assert win.btn_go.isEnabled() is False        # 什麼都還沒有
    win.set_gc(gc_arr)
    assert win.btn_go.isEnabled() is False        # 有 GC，沒有輸出資料夾
    win.ed_out.setText(str(tmp_path))
    win._sync()
    assert win.btn_go.isEnabled() is True
    assert win.btn_stop.isEnabled() is False      # 還沒開始跑


# --------------------------------------------------------------------------- #
# 4. 真的跑一次（小份）
# --------------------------------------------------------------------------- #
def test_it_writes_both_lots_without_blocking_the_gui(win, gc_arr, tmp_path):
    """按下去之後 GUI 執行緒要還活著 —— 50 張 1000² 要好幾秒。"""
    from d4t.core.ingest.dataset import load_dataset

    win.set_gc(gc_arr)
    win.ed_out.setText(str(tmp_path / "lot"))
    win.sp_images.setValue(2)
    win.sp_size.setValue(900)
    win.sp_defects.setValue(8)
    win._sync()
    win._go()
    assert win._worker is not None
    assert win.btn_go.isEnabled() is False        # 跑的時候不准再按
    assert win.btn_stop.isEnabled() is True
    win._worker.wait(120000)
    QApplication.instance().processEvents()

    assert win._worker is None
    assert "✓" in win.lbl_result.text(), win.lbl_result.text()
    assert load_dataset(str(tmp_path / "lot" / "rsem" / "LOT_RSEM.001")).kind == "rsem"
    ds = load_dataset(str(tmp_path / "lot" / "patch" / "LOT_SYN.001"))
    assert ds.kind == "ebi_patch" and len(ds.items) == 8


def test_the_result_line_warns_that_the_data_is_as_sensitive_as_the_gc(
        win, gc_arr, tmp_path):
    """鐵則 8 —— 產出來的東西跟原始影像一樣敏感，那句話要出現在畫面上。

    ⚠ 訊息是**英文**的（M7：UI 全英文，`test_ui_english_only.py` 鎖著）——
    這一支第一版整個視窗都是中文，那條測試當場紅。
    """
    win.set_gc(gc_arr)
    win.ed_out.setText(str(tmp_path / "lot2"))
    win.sp_images.setValue(1)
    win.sp_size.setValue(900)
    win.sp_defects.setValue(2)
    win._go()
    win._worker.wait(120000)
    QApplication.instance().processEvents()
    assert "do not commit" in win.lbl_result.text()


# --------------------------------------------------------------------------- #
# 5. 缺陷長什麼樣（F62）
# --------------------------------------------------------------------------- #
def test_the_defect_boxes_translate_into_a_spec(win, gc_arr):
    win.set_gc(gc_arr)
    win.sp_dmin.setValue(9.0)
    win.sp_dmax.setValue(3.0)          # 故意填反
    win.sp_cmin.setValue(90)
    win.sp_cmax.setValue(30)
    win.cmb_pol.setCurrentIndex(win.cmb_pol.findData("dark"))
    win.chk_bridge.setChecked(False)
    spec = win.defect_spec()
    # 填反了要**自己排好**，不是拿去產一批空的
    assert spec.diameter == (3.0, 9.0)
    assert spec.contrast == (30.0, 90.0)
    assert spec.polarity == "dark" and spec.bridge is False
    assert spec.kinds() == ("dark_blob",)


def test_the_sample_strip_redraws_when_a_knob_moves(win, gc_arr):
    """調的是一格數字，看到的是**等一下會拿到的那張圖** —— 那是這個視窗
    最像模擬器的地方，所以它必須真的跟著動。"""
    win.set_gc(gc_arr)
    before = win.lbl_samples.pixmap().toImage()
    win.sp_dmax.setValue(20.0)
    after = win.lbl_samples.pixmap().toImage()
    assert before != after


def test_the_sample_strip_is_stable_between_edits(win, gc_arr):
    """⚠ 樣本用**固定的 seed**：使用者一格一格微調，每動一次就換一批隨機的
    話，他分不出「數字變了」與「剛好抽到不一樣的」。"""
    win.set_gc(gc_arr)
    a = win.lbl_samples.pixmap().toImage()
    win._refresh_samples()
    b = win.lbl_samples.pixmap().toImage()
    assert a == b


def test_dark_only_really_reaches_the_written_lot(win, gc_arr, tmp_path):
    import json
    win.set_gc(gc_arr)
    win.cmb_pol.setCurrentIndex(win.cmb_pol.findData("dark"))
    win.chk_bridge.setChecked(False)
    win.sp_real.setValue(100)
    win.ed_out.setText(str(tmp_path / "dark"))
    win.sp_images.setValue(1); win.sp_size.setValue(900); win.sp_defects.setValue(8)
    win._go()
    win._worker.wait(120000)
    QApplication.instance().processEvents()
    truth = json.load(open(str(tmp_path / "dark" / "patch" / "ground_truth.json"),
                           encoding="utf-8"))
    assert {v["type"] for v in truth.values()} == {"dark_blob"}
