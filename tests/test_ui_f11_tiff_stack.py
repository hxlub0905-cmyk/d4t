# F11 Input-2（UI 那一半）：多頁 TIFF 有自己的入口，而且沒有 KLARF 要當場講。
"""三件事：

1. **一種 source 一個入口**（使用者定調「source 不一樣本來就要分」）——
   工具列多一顆 `Open stack…`，不是把兩件事併進 `Open KLARF…`。
   併起來的話，使用者按下去之前分不出自己要的是哪一種。
2. **`tiff_stack` 進得了 Studio**（`scope.SUPPORTED_KINDS`）。
3. **沒有 KLARF 就寫不回 KLARF，而那句話要在載入的當下講。** Export 精靈本來就
   會把選項變灰（它看 `dataset.klarf`），但那是使用者跑完一整批之後才看到的事。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adept.ui import scope  # noqa: E402


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    from adept.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, studio_mod=studio_mod,
             theme_mod=theme_mod, widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def win(qapp):
    w = studio_mod.StudioWindow()
    yield w
    w.close()
    w.deleteLater()


@pytest.fixture
def stack(tmp_path):
    path = tmp_path / "LOT_STACK.tif"
    with tifffile.TiffWriter(str(path)) as tw:
        for i in range(10):
            tw.write(np.full((16, 16), 10 * (i + 1), np.uint8),
                     photometric="minisblack")
    return path


# ---------------------------------------------------------------------------
def test_the_stack_kind_is_supported_now():
    assert scope.is_supported_kind("tiff_stack")
    assert scope.is_supported_kind("ebi_patch")


def test_there_is_a_separate_entry_for_it(win):
    """`Open stack…` 是自己的一顆鈕，而且圖示跟 `Open KLARF…` 不同。"""
    assert win.btn_open_stack.text() == "Open stack…"
    tip = win.btn_open_stack.toolTip()
    assert "no KLARF" in tip and "per defect" in tip
    assert "stack" in widgets_mod.GLYPH_ICONS


def test_loading_a_stack_gives_one_defect_per_page_group(win, stack):
    assert win.load_stack_path(str(stack), 5, sync=True) is True
    assert win.dataset.kind == "tiff_stack"
    assert len(win.dataset.items) == 2
    ids = [win.defect_combo.itemText(i) for i in range(win.defect_combo.count())]
    assert ids == ["LOT_STACK_1", "LOT_STACK_2"]


def test_no_klarf_is_said_where_it_stays_on_screen(win, stack):
    """**不能只在狀態列講一次。**

    載完就接著算預覽，狀態列那句話幾毫秒後就被 "Computing preview…" 蓋掉 ——
    這一條就是那樣紅出來的（同一個教訓 ground truth 那一輪學過）。所以掛在
    資料集標籤上：常駐、在眼前，而且它講的正是「你現在手上是什麼資料」。
    """
    win.load_stack_path(str(stack), 5, sync=True)
    assert "no KLARF" in win.defect_label.text()
    tip = win.defect_label.toolTip()
    assert "written back" in tip and "CSV" in tip     # 講得出還有什麼路可以走


def test_an_ebi_patch_dataset_does_not_get_that_label(win, tmp_path):
    """有 KLARF 的資料集不該看到那句話（不然它就變成雜訊）。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from make_sample import generate
    paths = generate(str(tmp_path / "lot"), n=4, seed=5)
    win.load_dataset_path(paths["klarf"], sync=True)
    assert win.dataset.kind == "ebi_patch"
    assert "no KLARF" not in win.defect_label.text()
    assert win.defect_label.toolTip() == ""


def test_a_missing_file_is_refused_without_touching_the_current_dataset(win, stack):
    win.load_stack_path(str(stack), 5, sync=True)
    before = win.dataset
    assert win.load_stack_path(str(stack.parent / "nope.tif"), 5,
                               sync=True) is False
    assert win.dataset is before


def test_the_channel_map_table_gets_its_rows_from_the_data(win, stack):
    """載一份「一顆五張」的資料 → 命名表格一開就有五列（F11 Input-1 的尾巴）。"""
    win.load_stack_path(str(stack), 5, sync=True)
    win.select_node(win.model.node_order[0])
    ed = win.param_form.editor("channel_map")
    assert ed is not None and ed.row_count() == 5
