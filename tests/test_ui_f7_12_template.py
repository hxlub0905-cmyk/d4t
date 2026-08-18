# F7-12 驗收（UI）：從大圖建 Golden Cell 模板；F11 Region-1 起同一個對話框標區域。
"""模板與區域都不可能用打字的，所以這個對話框是那張卡唯一的入口 —— 它壞掉，
整張卡就不能用。

而整條路唯一會**安靜壞掉**的地方是「週期估錯」：估錯了疊出來的 cell 會糊掉，
糊掉的模板會讓後面每一顆都對錯，但畫面上不會有錯誤訊息，只會有一批看起來很正常、
其實量錯位置的數字。所以測試盯的是**判斷材料有沒有被攤開給人看**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import wire_up  # noqa: E402  —— F10：加完卡要接線

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

PERIOD = 40


def big_image(seed: int = 0, noise: float = 4.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((240, PERIOD * 8), np.float32)
    for k in range(8):
        x = k * PERIOD
        img[:, x:x + PERIOD] = 120.0
        img[:, x + 14:x + 34] = 60.0
        img[:, x + 12:x + 16] = 210.0
        img[:, x + 32:x + 36] = 210.0
    return img + rng.normal(0, noise, img.shape).astype(np.float32)


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import cell_canvas as canvas_mod
    from adept.ui import studio as studio_mod
    from adept.ui import template_dialog as tpl_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, studio_mod=studio_mod,
             tpl_mod=tpl_mod, theme_mod=theme_mod, canvas_mod=canvas_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    """一批從那張大圖上不同相位裁下來的 patch。"""
    import tifffile
    from make_sample import generate

    out = generate(str(tmp_path_factory.mktemp("f7_12")), n=6, seed=5)
    img = big_image(3)
    rng = np.random.default_rng(1)
    pages = []
    for _ in range(6):
        phase = int(rng.integers(0, PERIOD))
        ref = img[100:132, 3 * PERIOD + phase:3 * PERIOD + phase + 32]
        test = ref.copy()
        test[12:20, 12:20] += 55.0
        pages += [np.clip(test, 0, 255).astype(np.uint8),
                  np.clip(ref, 0, 255).astype(np.uint8)]
    tifffile.imwrite(out["tiff"], np.stack(pages))
    return out


@pytest.fixture
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lot["klarf"], sync=True)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 對話框
# --------------------------------------------------------------------------- #
def test_nothing_can_be_accepted_before_an_image_is_loaded(qapp):
    dlg = tpl_mod.TemplateDialog()
    assert dlg.is_ready() is False
    assert dlg.encoded() == ""
    assert dlg.summary() == ""


def test_the_dialog_lays_out_the_evidence_for_judging_the_template(qapp):
    """使用者不需要懂銳利度分數怎麼算 —— 他要看得到「疊出來是清楚還是糊的」，
    以及量到的週期、疊了幾格。"""
    dlg = tpl_mod.TemplateDialog()
    assert dlg.load_image(big_image(), "LOT_full.tif") is True
    assert dlg.is_ready() is True

    summary = dlg.summary()
    assert "cell %d" % PERIOD in summary
    assert "repeats across" in summary        # 一維 layout
    assert "stacked from" in summary
    assert "sharpness" in summary
    assert dlg.locate_axis() == "x"
    assert dlg.canvas.has_cell() is True


def test_an_image_without_a_repeat_is_refused_with_a_reason(qapp):
    dlg = tpl_mod.TemplateDialog()
    noise = np.random.default_rng(1).normal(120.0, 6.0, (128, 128))
    assert dlg.load_image(noise, "noise.tif") is False
    assert dlg.is_ready() is False
    assert "Could not build" in dlg.report.text()
    assert dlg.canvas.has_cell() is False


def test_an_empty_image_is_refused_instead_of_crashing(qapp):
    dlg = tpl_mod.TemplateDialog()
    assert dlg.load_image(np.zeros((0, 0), np.float32), "empty.tif") is False
    assert dlg.is_ready() is False


def test_a_blurred_stack_is_called_out_not_just_scored(qapp):
    """週期估錯 -> 疊出來糊掉 -> 每一顆都對錯，而且畫面上不會有錯誤訊息。
    所以糊掉這件事要用**白話**講，不能只丟一個分數。"""
    from adept.core.algo import template as algo_template

    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "ok.tif")
    # 故意用一個錯的週期疊（+7 px），模擬「週期估錯」
    dlg.cell = algo_template.build_golden_cell(big_image(), px=PERIOD + 7,
                                               py=240)
    if dlg.cell.ghosting < 40.0:
        assert "blurred" in dlg.summary()
        assert "mis-place" in dlg.summary()


def test_the_canvas_paints_with_and_without_a_template(qapp):
    from PySide6.QtGui import QPixmap

    view = canvas_mod.CellCanvas()
    view.resize(320, 260)
    for cell in (None, big_image()[:40, :40].astype(np.uint8)):
        view.set_cell(cell)
        view.set_regions([("epi", [(0.2, 0.0, 0.5, 1.0)]),
                          ("mg", [(0.0, 0.0, 0.15, 1.0)])])
        view.set_patch_size((32, 32))
        for name in ("light", "dark"):
            theme_mod.set_theme(name)
            pm = QPixmap(view.size())
            pm.fill()
            view.render(pm)          # 例外會在這裡冒出來
            assert not pm.isNull()
    theme_mod.apply_theme(qapp, "light")


def test_a_box_drawn_on_the_cell_is_what_gets_stored(qapp):
    """畫布上的框與 recipe 裡的字串是**同一份資料**，不是兩份。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.35, 0.0, 0.2, 1.0))
    assert dlg.regions_text() == "ROI1: 0.35,0,0.2,1"

    dlg.set_regions_text("epi: 0.1,0,0.3,1 | mg: 0.5,0,0.2,1")
    assert [n for n, _b in dlg.canvas.regions()] == ["epi", "mg"]
    assert dlg.regions_text() == "epi: 0.1,0,0.3,1 | mg: 0.5,0,0.2,1"


def test_a_region_name_that_cannot_be_a_variable_is_refused(qapp):
    """區域名會變成特徵名的一部分 —— 擋在改名的當下（鐵則 4）。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.1, 0.0, 0.2, 1.0))
    assert dlg.rename_region("my region") is False
    assert dlg.rename_region("epi") is True
    assert dlg.regions_text().startswith("epi:")

    dlg.add_region()
    dlg.canvas.add_box((0.5, 0.0, 0.2, 1.0))
    assert dlg.rename_region("epi") is False        # 撞名


def test_the_multi_add_tool_grows_an_evenly_spaced_row(qapp):
    """一根一根拉會歪，而歪掉的框在畫面上看不出來、在數字上看得出來。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.spin_w.setValue(4)
    dlg.spin_h.setValue(200)
    dlg.spin_nx.setValue(4)
    dlg.spin_ny.setValue(1)

    dlg.toggle_array()
    assert dlg.canvas.array_active() is True
    assert dlg.btn_array_ok.isEnabled() is False       # 錨點還不夠

    dlg.canvas.place_array_anchor(0.1, 0.5)
    assert len(dlg.canvas.array_preview()) == 1        # 只有一個錨點 = 一個框
    dlg.canvas.place_array_anchor(0.7, 0.5)
    assert len(dlg.canvas.array_preview()) == 4
    assert dlg.btn_array_ok.isEnabled() is True

    assert dlg.commit_array() == 4
    boxes = dlg.canvas.regions()[0][1]
    centres = sorted(b[0] + b[2] / 2.0 for b in boxes)
    gaps = [b - a for a, b in zip(centres, centres[1:])]
    assert all(abs(g - gaps[0]) < 1e-9 for g in gaps)
    assert dlg.canvas.array_active() is False


def test_the_multi_add_anchor_is_the_box_centre(qapp):
    """使用者按下去的那一點是**框的中心**（他定的規格），不是左上角。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    h, w = dlg.canvas.cell_shape()
    dlg.spin_w.setValue(int(w * 0.2))
    dlg.spin_h.setValue(int(h * 0.4))
    dlg.spin_nx.setValue(1)
    dlg.spin_ny.setValue(1)
    dlg.toggle_array()
    dlg.canvas.place_array_anchor(0.5, 0.5)
    x, y, bw, bh = dlg.canvas.array_preview()[0]
    assert abs((x + bw / 2.0) - 0.5) < 1e-6
    assert abs((y + bh / 2.0) - 0.5) < 1e-6


def test_a_stored_template_is_read_back_instead_of_rebuilt(qapp):
    """回來調框不可以重算模板 —— 相位一變，標好的框就全部平移了。"""
    from adept.core.algo import template as algo_template

    src = tpl_mod.TemplateDialog()
    src.load_image(big_image(), "LOT_full.tif")
    encoded = src.encoded()

    dlg = tpl_mod.TemplateDialog()
    assert dlg.load_encoded(encoded, "x") is True
    assert dlg.is_ready() is True
    assert dlg.encoded() == encoded
    assert dlg.locate_axis() == "x"
    assert "read back from this recipe" in dlg.summary()
    assert dlg.load_encoded("not a template") is False


def test_deleting_a_rectangle_and_a_region(qapp):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.1, 0.0, 0.2, 1.0))
    dlg.canvas.add_box((0.5, 0.0, 0.2, 1.0))
    assert len(dlg.canvas.regions()[0][1]) == 2
    assert dlg.canvas.delete_selected() is True
    assert len(dlg.canvas.regions()[0][1]) == 1

    dlg.add_region()
    assert len(dlg.canvas.regions()) == 2
    dlg.delete_region()
    assert len(dlg.canvas.regions()) == 1


# --------------------------------------------------------------------------- #
# 2. 接回 Studio
# --------------------------------------------------------------------------- #
def test_the_button_only_shows_for_the_card_that_needs_a_template(window):
    nid = wire_up(window.model, window.model.add_step("roi_template"))
    window.select_node(nid)
    assert window.template_build_available() is True

    other = wire_up(window.model, window.model.add_step("roi_cross"))
    window.select_node(other)
    assert window.template_build_available() is False
    assert window.open_template_dialog() is None
    assert "Locate region by template" in window.status_text()


def test_accepting_the_dialog_stores_the_template_in_the_recipe(window):
    """存進 recipe 的是**模板本身**，不是大圖的路徑 ——
    recipe 要能寄給別人，存路徑的話圖被換掉之後結果會安靜地變。"""
    nid = wire_up(window.model, window.model.add_step("roi_template"))
    window.select_node(nid)
    dlg = window.open_template_dialog()
    assert dlg is not None
    assert dlg.load_image(big_image(), "LOT_full.tif") is True
    dlg.canvas.add_box((0.35, 0.0, 0.2, 1.0))
    dlg.rename_region("epi")
    dlg._on_accept()

    params = window.model.nodes[nid].params
    assert params["template"].startswith("gc1:")
    assert params["locate_axis"] == "x"
    assert params["regions"] == "epi: 0.35,0,0.2,1"
    assert "Template stored" in window.status_text()
    assert "epi" in window.status_text()


def test_reopening_the_dialog_shows_what_is_already_stored(window):
    """第二次打開要看得到現在的模板與框 —— 不然使用者只能從頭再畫一次。"""
    nid = wire_up(window.model, window.model.add_step("roi_template"))
    window.select_node(nid)
    dlg = window.open_template_dialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.35, 0.0, 0.2, 1.0))
    dlg.rename_region("epi")
    dlg._on_accept()

    again = window.open_template_dialog()
    assert again.canvas.has_cell() is True
    assert again.regions_text() == "epi: 0.35,0,0.2,1"
    assert again.encoded() == window.model.nodes[nid].params["template"]


def test_the_stored_template_actually_locates_the_regions(window):
    """存完之後真的跑一顆，區域要落在有結構的地方而不是退回整張圖。"""
    nid = wire_up(window.model, window.model.add_step("roi_template"))
    window.select_node(nid)
    dlg = window.open_template_dialog()
    dlg.load_image(big_image(3), "LOT_full.tif")

    # EPI 在 cell 上的位置（使用者會在畫布上拖出來的那一塊）
    cell = dlg.cell.cell
    prof = cell.mean(axis=0)
    dark = np.where(prof < 90)[0]
    lo = float(dark.min()) / cell.shape[1]
    wd = float(dark.max() - dark.min() + 1) / cell.shape[1]
    dlg.canvas.add_box((lo, 0.0, wd, 1.0))
    dlg.rename_region("epi")
    dlg._on_accept()

    assert window.refresh_preview(sync=True) is True
    feats = dict(window._last_result.features or {})
    assert feats.get("locate_ok") == 1.0, feats
    assert feats.get("match_score", 0.0) > 0.8


def test_a_card_with_no_template_refuses_to_run_and_says_where_to_go(window):
    """跑之前的 lint 會擋下來，訊息要指向那顆按鈕，不是丟一個空參數給人猜。"""
    nid = wire_up(window.model, window.model.add_step("roi_template"))
    window.select_node(nid)
    assert window.refresh_preview(sync=True) is True
    assert "Edit template & regions" in window.status_text()


def test_the_region_check_view_works_for_the_template_card_too(window):
    """跨顆檢視對**任何**會定義區域的卡片都成立 —— 模板卡也不例外。"""
    nid = wire_up(window.model, window.model.add_step("roi_template"))
    window.select_node(nid)
    dlg = window.open_template_dialog()
    dlg.load_image(big_image(3), "LOT_full.tif")
    dlg.canvas.add_box((0.3, 0.0, 0.25, 1.0))
    dlg.rename_region("epi")
    dlg._on_accept()

    assert window.selected_regions() == ["epi", "epi_center"]
    assert window.region_check_available() is True
    assert window.open_region_check(n=6, sync=True) is True
    assert "6 defects" in window.region_window.summary_text()
