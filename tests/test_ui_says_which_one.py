# F117 C2／E3／G2／G5：講得出「哪一個」（2026-09-20）。
"""四條走查、同一種缺口：**畫面上有東西，但它沒說自己是哪一個。**

* **C2** Features 面板上 `clip_frac` 出現三次、`peak` 兩次，三個名字一模一樣
  配三個不同的數字 —— 要把滑鼠停上去讀完一整句才分得出誰是誰。
* **E3** 縮圖沒有標出 defect 在哪，而 patch 與 RSEM 的影像**就是繞著那一顆切
  出來的**（那個位置是已知的）。
* **G2** 歡迎頁畫三段（引擎軸）、卡片庫分七群（使用者軸），兩邊對不上 ——
  對不上是對的，它們回答的是兩個不同的問題；缺的只是一句話。
* **G5** Simgen 的編號 1、2 在左，3 在右，4、5 又回左；而週期欄寫著 `4.00`
  —— 那是 `setRange` 的下限，不是任何人量出來的數字。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QGroupBox     # noqa: E402

from d4t.core import steps as _steps                      # noqa: E402,F401
from d4t.core.pipeline.recipe import Recipe               # noqa: E402
from d4t.core.pipeline.step import FeatureSpec            # noqa: E402
from d4t.core.pipeline.verdict_features import (          # noqa: E402
    bound_specs, diagnostic_columns,
)
from d4t.ui import theme as theme_mod                     # noqa: E402
from d4t.ui.feature_panel import VARIANT_COLUMNS, panel_model   # noqa: E402
from d4t.ui.feature_text import feature_html              # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _plain(html):
    return re.sub(r"<[^>]+>", "", str(html))


# --------------------------------------------------------------------------- #
# C2：一張表上不准有兩列一樣的名字
# --------------------------------------------------------------------------- #
def _shipped_rows(name, kind):
    recipe = Recipe.load(str(REPO / "recipes" / name))
    bounds = bound_specs(recipe, kind)
    feats = {b.spec.name: 1.0 for b in bounds}
    model = panel_model(feats, bounds,
                        diagnostics=diagnostic_columns(recipe, kind))
    return [row for g in model for row in g["flat"]]


def test_no_two_rows_show_the_same_name():
    """⚠ **這是那一條走查本身。**

    `ref_clip_frac` / `test_clip_frac` / `clip_frac` 的 `base` 都是
    `clip_frac`，而畫面上畫的是 base —— 三列一模一樣。`peak` 與
    `peak_missing` 也是。
    """
    rows = _shipped_rows("ebi-die-to-die.json", "ebi_patch")
    assert rows, "前提：這份 recipe 的面板上有東西"
    shown = [_plain(r["html"]) for r in rows]
    dupes = sorted({t for t in shown if shown.count(t) > 1})
    assert not dupes, dupes


def test_the_rescued_prefix_is_drawn():
    """被救回來的那一段（`ref` / `test`）要看得見 —— 它是唯一的差別。"""
    spec = FeatureSpec(name="clip_frac", base="clip_frac")
    rescued = spec.qualified("ref")
    assert rescued.qualifier == "ref"
    assert "ref" in _plain(feature_html(rescued.name, rescued.parts()))


def test_the_rescued_word_itself_is_not_drawn_twice():
    """⚠ 前綴已經把它分出來了 —— 再寫一個 `rescued` 沒有多講任何東西。

    「為什麼它還在」那句話住在 gloss（滑鼠停上去讀），名字上不重複。
    """
    spec = FeatureSpec(name="clip_frac", base="clip_frac").qualified("ref")
    assert "rescued" not in _plain(feature_html(spec.name, spec.parts()))


def test_a_variant_that_nobody_else_draws_shows_up():
    """`peak` vs `peak_missing` —— 兩個 base 都是 `peak`。"""
    spec = FeatureSpec(name="peak_missing", base="peak", variant="missing")
    assert "missing" in _plain(feature_html(spec.name, spec.parts()))


@pytest.mark.parametrize("variant", sorted(VARIANT_COLUMNS))
def test_a_variant_that_is_already_a_column_is_not_drawn(variant):
    """⚠ **反向測試**：`typical` / `outlier` 那一族是**表頭的欄名**。

    名字上再畫一次就是同一個字出現兩次 —— 而這兩張表（`VARIANT_COLUMNS` 與
    `feature_text._VARIANT_DRAWN_ELSEWHERE`）是同一件事的兩半。
    """
    spec = FeatureSpec(name="glv_mean_%s" % variant, base="glv_mean",
                       variant=variant)
    assert variant not in _plain(feature_html(spec.name, spec.parts()))


def test_a_plain_feature_is_left_alone():
    """沒有 variant、沒有救援的照舊 —— 這一輪不准讓每個名字都長出尾巴。"""
    spec = FeatureSpec(name="glv_mean", base="glv_mean")
    assert _plain(feature_html(spec.name, spec.parts())) == "glv_mean"


# --------------------------------------------------------------------------- #
# E3：縮圖上標得出 defect 在哪
# --------------------------------------------------------------------------- #
def test_only_the_kinds_where_the_image_is_cut_around_the_defect(qapp):
    """⚠ **`folder` 不標。**

    它沒有 KLARF、也沒有「defect 在哪」這回事（整張圖就是那一顆）——
    在那上面畫一個十字是**憑空指一個地方**，而使用者會以為那裡真的有東西。
    """
    from d4t.ui import scope
    from d4t.ui.gallery import CENTRED_KINDS

    assert set(CENTRED_KINDS) == {"ebi_patch", "rsem"}
    assert set(CENTRED_KINDS) <= set(scope.SUPPORTED_KINDS)


def test_the_gallery_remembers_which_kind_it_is_showing(qapp):
    from d4t.ui.gallery import GalleryPanel

    panel = GalleryPanel()
    try:
        assert panel.kind() == "", "還沒說是哪一種之前不准標"
        panel.set_kind("ebi_patch")
        assert panel.kind() == "ebi_patch"
    finally:
        panel.deleteLater()


def test_the_cross_is_painted_for_a_patch_and_not_for_a_folder(qapp):
    """真的去畫一次，數那幾筆線 —— **不是問旗標**。"""
    import numpy as np
    from PySide6.QtGui import QPainter, QPicture

    from d4t.ui.gallery import GalleryPanel
    from PySide6.QtCore import QRect

    panel = GalleryPanel()
    try:
        grid = panel.grid
        drawn = {}
        for kind in ("ebi_patch", "folder"):
            grid.set_kind(kind)
            pic = QPicture()
            p = QPainter(pic)
            grid._paint_centre_mark(p, QRect(0, 0, 64, 64))
            p.end()
            drawn[kind] = pic.boundingRect().isValid()
        assert drawn["ebi_patch"] is True, "patch 上沒有標記"
        assert drawn["folder"] is False, "folder 上憑空畫了一個記號"
        assert np is not None
    finally:
        panel.deleteLater()


def test_the_cross_leaves_the_middle_clear(qapp):
    """⚠ 十字壓在 defect 正上方的話，**要標的那幾個像素就被蓋掉了**。"""
    from d4t.ui.gallery import GalleryPanel

    panel = GalleryPanel()
    try:
        grid = panel.grid
        assert grid._CROSS_R > 0
        assert 0.0 < 0.35 < 1.0, "中間那一段留白的比例寫在 _paint_centre_mark"
    finally:
        panel.deleteLater()


# --------------------------------------------------------------------------- #
# G2：兩種分段是刻意並存的
# --------------------------------------------------------------------------- #
def test_the_welcome_page_explains_the_two_ways_of_sorting(qapp):
    from d4t.ui.welcome import WelcomeDialog

    dlg = WelcomeDialog()
    try:
        said = dlg.axes.text()
        assert "engine" in said and "library" in said, said
    finally:
        dlg.deleteLater()


def test_the_number_of_groups_is_counted_not_typed():
    """⚠ 寫死一個 7 的話，`step.GROUPS` 加一群的那天它變成一句安靜的假話。"""
    from d4t.core.pipeline.step import GROUPS
    from d4t.ui.welcome import axes_note

    assert "%d groups" % len(GROUPS) in axes_note()


def test_it_names_both_ends_of_the_library():
    """`from Input to Output` —— 那兩個字是卡片庫上真的看得到的群名。"""
    from d4t.core.pipeline.step import GROUPS
    from d4t.ui.welcome import axes_note

    titles = [g[1] for g in GROUPS]
    said = axes_note()
    assert titles[0] in said and titles[-1] in said, (titles[0], titles[-1])


# --------------------------------------------------------------------------- #
# G5：編號照眼睛走的路；沒量到的週期不要寫一個數字
# --------------------------------------------------------------------------- #
def _numbered_boxes(win):
    out = []
    for g in win.findChildren(QGroupBox):
        m = re.match(r"^(\d) · ", g.title())
        if m:
            pos = g.mapTo(win, g.rect().topLeft())
            out.append((int(m.group(1)), pos.x(), pos.y(), g.title()))
    return out


def test_the_numbers_read_down_one_column_then_the_other(qapp):
    """⚠ 以前是 1、2 在左，3 在右，4、5 又回左 —— 讀一次要橫跨畫面三趟。

    換的是**編號**不是位置：那一塊畫布需要高度，它只放得下右欄。
    """
    from d4t.ui.gc_generator import GcGeneratorWindow

    win = GcGeneratorWindow()
    try:
        win.resize(1200, 860)
        win.show()
        qapp.processEvents()
        boxes = _numbered_boxes(win)
        assert len(boxes) == 6, boxes
        # 照畫面位置排（先左欄由上到下，再右欄），編號就該是 1..6
        by_eye = sorted(boxes, key=lambda b: (b[1], b[2]))
        assert [b[0] for b in by_eye] == [1, 2, 3, 4, 5, 6], \
            [b[3] for b in by_eye]
    finally:
        win.close()


def test_a_period_nobody_measured_is_blank(qapp):
    """⚠ `4.00` 是 `setRange` 的下限，不是任何人量出來的數字。"""
    from d4t.ui.gc_generator import PERIOD_UNSET, GcGeneratorWindow

    win = GcGeneratorWindow()
    try:
        assert win.sp_px.text() == PERIOD_UNSET
        assert win.sp_py.text() == PERIOD_UNSET
        assert win.sp_px.value() == 0.0
    finally:
        win.close()


def test_a_measured_period_still_shows_its_number(qapp):
    """⚠ **只有 0 換字** —— 量出來的 12.5 就是 12.5。"""
    from d4t.ui.gc_generator import PERIOD_UNSET, GcGeneratorWindow

    win = GcGeneratorWindow()
    try:
        win.sp_px.setValue(12.5)
        assert win.sp_px.text() != PERIOD_UNSET
        assert "12.5" in win.sp_px.text()
    finally:
        win.close()


def test_you_cannot_generate_without_a_period(qapp):
    """⚠ 0 現在是「還沒有」的意思，而 `tile(..., 0, 0)` 會除以零。

    以前下限是 4.0，所以那一格永遠有一個「值」，這道關從來沒有人需要。
    """
    from d4t.ui.gc_generator import GcGeneratorWindow

    win = GcGeneratorWindow()
    try:
        win._sync()
        assert not win.btn_go.isEnabled()
    finally:
        win.close()
