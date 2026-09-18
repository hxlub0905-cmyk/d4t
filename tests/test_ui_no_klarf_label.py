# 沒有 KLARF 的那句話要常駐在畫面上 — 原 F11 Input-2 的 UI 那一半，F114 改寫。
"""**這一份原本叫 `test_ui_f11_tiff_stack.py`，綁在 `Open stack…` 上。**

2026-09-18（F114）使用者把 stack 拿掉了（「我們用不到」），而它守的三件事裡
只有第一件是 stack 自己的：

* ~~一種 source 一個入口 → 多一顆 `Open stack…`~~ —— 隨那個入口一起走了。
* **沒有 KLARF 就寫不回 KLARF，而那句話要在載入的當下講**，而且**不能只在狀態列
  講一次**：載完就接著算預覽，狀態列那句話幾毫秒後就被 "Computing preview…"
  蓋掉。所以它掛在**資料集標籤**上 —— 常駐、在眼前。
* **命名表格的列數來自資料**，不是寫死的。

後兩件跟 stack 一點關係都沒有：`folder`、`doe_folder`、`raw` 三條路**全部**
沒有 KLARF，而那句話對它們一字不差。所以這一份改接在 `doe_folder` 上 ——
**測的是機制，不是那一個入口**（同 `test_ui_scope_profiles.py` 那一輪的教訓：
把某一個具體對象抄進測試裡，那個對象一被拿掉，紅的理由就跟壞掉的東西無關）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QApplication=QApplication, studio_mod=studio_mod,
             theme_mod=theme_mod)


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
def doe(tmp_path):
    """一顆三張、沒有 KLARF —— `doe_folder` 那條路。"""
    from make_doe_sample import generate

    return generate(str(tmp_path / "doe"), n=3, seed=5)["out_dir"]


def test_no_klarf_is_said_where_it_stays_on_screen(win, doe):
    """**不能只在狀態列講一次。**

    載完就接著算預覽，狀態列那句話幾毫秒後就被 "Computing preview…" 蓋掉 ——
    這一條就是那樣紅出來的（同一個教訓 ground truth 那一輪學過）。所以掛在
    資料集標籤上：常駐、在眼前，而且它講的正是「你現在手上是什麼資料」。
    """
    win.load_folder_path(str(doe), doe=True, sync=True)
    assert "no KLARF" in win.defect_label.text()
    tip = win.defect_label.toolTip()
    assert "written back" in tip and "CSV" in tip     # 講得出還有什麼路可以走


def test_an_ebi_patch_dataset_does_not_get_that_label(win, tmp_path):
    """有 KLARF 的資料集不該看到那句話（不然它就變成雜訊）。"""
    from make_sample import generate

    paths = generate(str(tmp_path / "lot"), n=4, seed=5)
    win.load_dataset_path(paths["klarf"], sync=True)
    assert win.dataset.kind == "ebi_patch"
    assert "no KLARF" not in win.defect_label.text()
    assert win.defect_label.toolTip() == ""


def test_a_missing_folder_is_refused_without_touching_the_current_dataset(
        win, doe):
    win.load_folder_path(str(doe), doe=True, sync=True)
    before = win.dataset
    assert win.load_folder_path(str(Path(doe).parent / "nope"), doe=True,
                                sync=True) is False
    assert win.dataset is before


def test_the_channel_map_table_gets_its_rows_from_the_data(win, doe):
    """載一份「一顆三張」的資料 → 命名表格一開就有三列（F11 Input-1 的尾巴）。

    **列數是資料說了算**，不是卡片預設的兩列 —— 寫死兩列的話，第三個
    condition 會安靜地載不進來。
    """
    win.load_folder_path(str(doe), doe=True, sync=True)
    win.select_node(first_source(win))
    ed = win.param_form.editor("channel_map")
    assert ed is not None and ed.row_count() == 3
