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
from PySide6.QtCore import Qt

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


def _press(w, pt, button=None):
    _send(w, "mousePressEvent", pt, button or _qt().LeftButton, button or _qt().LeftButton)


def _move(w, pt, buttons=None):
    _send(w, "mouseMoveEvent", pt, _qt().NoButton, buttons or _qt().LeftButton)


def _release(w, pt, button=None):
    _send(w, "mouseReleaseEvent", pt, button or _qt().LeftButton, _qt().NoButton)


def _qt():
    from PySide6.QtCore import Qt as _Qt
    return _Qt


def _send(w, method, pt, button, buttons):
    """直接餵一個滑鼠事件給 widget（比 QTest 好讀，也不必真的顯示視窗）。"""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    kinds = {"mousePressEvent": QEvent.MouseButtonPress,
             "mouseMoveEvent": QEvent.MouseMove,
             "mouseReleaseEvent": QEvent.MouseButtonRelease}
    ev = QMouseEvent(kinds[method], QPointF(pt), QPointF(pt),
                     button, buttons, _qt().NoModifier)
    getattr(w, method)(ev)


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

    dlg.set_tool(canvas_mod.TOOL_ARRAY)
    assert dlg.canvas.array_active() is True
    assert dlg.btn_array_ok.isEnabled() is False       # 錨點還不夠

    dlg.canvas.place_array_anchor(0.1, 0.5)
    assert len(dlg.canvas.array_preview()) == 1        # 只有一個錨點 = 一個框
    dlg.canvas.place_array_anchor(0.7, 0.5)
    assert len(dlg.canvas.array_preview()) == 4
    assert dlg.btn_array_ok.isEnabled() is True

    assert dlg.commit_array() == 4
    boxes = dlg.canvas.regions()[0][1]
    centres = sorted(dlg.canvas.to_px(b)[0] + dlg.canvas.to_px(b)[2] / 2.0
                     for b in boxes)
    gaps = [b - a for a, b in zip(centres, centres[1:])]
    assert all(abs(g - gaps[0]) <= 1.0 for g in gaps), centres
    # 加完**留在陣列工具上**（通常要標好幾排），只是錨點清掉了
    assert dlg.canvas.array_active() is True
    assert dlg.canvas.array_anchor_count() == 0


def test_the_multi_add_anchor_is_the_box_centre(qapp):
    """使用者按下去的那一點是**框的中心**（他定的規格），不是左上角。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    h, w = dlg.canvas.cell_shape()
    dlg.spin_w.setValue(int(w * 0.2))
    dlg.spin_h.setValue(int(h * 0.4))
    dlg.spin_nx.setValue(1)
    dlg.spin_ny.setValue(1)
    dlg.set_tool(canvas_mod.TOOL_ARRAY)
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
    assert params["template"].startswith("gc2:")
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

    assert window.selected_regions() == ["epi", "epi_center", "epi_others"]
    assert window.region_check_available() is True
    assert window.open_region_check(n=6, sync=True) is True
    assert "6 defects" in window.region_window.summary_text()


# --------------------------------------------------------------------------- #
# 3. 試用回報七項（F11 Region-1 第二輪）
# --------------------------------------------------------------------------- #
def test_a_box_goes_somewhere_even_when_no_region_exists_yet(qapp):
    """**使用者回報的第 1 個 bug。** 「按下 Add them 加不進去 region」。

    從 Studio 打開一張**已經有模板、還沒有區域**的卡時，區域清單是空的 ——
    而那時候 `add_box` / `add_boxes` 直接回 −1／0：畫出來的框跟按下 Add them
    都**安靜地什麼都沒發生**，因為程式覺得自己沒事。

    「使用者做了一個明確的動作」與「沒有容器可以裝」之間，該讓步的是後者。
    """
    src = tpl_mod.TemplateDialog()
    src.load_image(big_image(), "LOT_full.tif")

    dlg = tpl_mod.TemplateDialog()
    assert dlg.load_encoded(src.encoded(), "x") is True
    dlg.set_regions_text("")
    assert dlg.canvas.regions() == []          # 這就是那個處境

    dlg.spin_w.setValue(4)
    dlg.spin_h.setValue(200)
    dlg.spin_nx.setValue(4)
    dlg.set_tool(canvas_mod.TOOL_ARRAY)
    dlg.canvas.place_array_anchor(0.1, 0.5)
    dlg.canvas.place_array_anchor(0.7, 0.5)
    assert dlg.commit_array() == 4
    assert dlg.regions_text().startswith("ROI1:")

    # 拖曳新增走的是同一條路，所以它以前也一樣安靜地失敗
    dlg2 = tpl_mod.TemplateDialog()
    dlg2.load_encoded(src.encoded(), "x")
    dlg2.set_regions_text("")
    assert dlg2.canvas.add_box((0.1, 0.0, 0.2, 1.0)) >= 0
    assert dlg2.regions_text() != ""


def test_every_box_lands_on_whole_cell_pixels(qapp):
    """「pixel 是整數才合理吧」—— 對，半個像素沒有東西可以量。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.1234, 0.0, 0.2345, 1.0))

    box = dlg.canvas.regions()[0][1][0]
    h, w = dlg.canvas.cell_shape()
    for v, size in zip(box, (w, h, w, h)):
        assert abs(v * size - round(v * size)) < 1e-9, box
    # 表格也是整數
    dlg.open_box_table()
    assert dlg.box_table.item(0, 0).text() == "5"


def test_a_zero_width_box_can_never_be_made(qapp):
    """吸附之後還是不能有 0 寬的框 —— 那種框存不進 recipe。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.5, 0.5, 0.0001, 0.0001))
    assert dlg.canvas.to_px(dlg.canvas.regions()[0][1][0])[2:] == (1, 1)


def test_the_cell_size_can_be_overridden_and_doubled(qapp):
    """「有時候會需要 2X 大 cell」—— 量出來的週期是預設值，不是結論。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    assert dlg.canvas.cell_shape()[1] == PERIOD

    dlg._on_double()
    assert dlg.canvas.cell_shape()[1] == PERIOD * 2
    # ⚠ 沒有週期的那一軸**不可以**跟著加倍：那會疊出一個比原圖還高的 cell，
    # 而 build_golden_cell「使用者明講的一律相信」會把它當成有週期 ——
    # locate_axis 就從 x 變成 both，開始在一個沒有相位的方向上搜尋。
    assert dlg.canvas.cell_shape()[0] == 240
    assert dlg.locate_axis() == "x"
    assert dlg.spin_cell_h.isEnabled() is False


def test_restacking_needs_the_original_image_and_says_so(qapp):
    """從 recipe 讀回來的模板只有結果、沒有原料 —— 那顆鈕不能按下去沒反應。"""
    src = tpl_mod.TemplateDialog()
    src.load_image(big_image(), "LOT_full.tif")

    dlg = tpl_mod.TemplateDialog()
    dlg.load_encoded(src.encoded(), "x")
    assert dlg.restack() is False
    assert "Pick a full-size image first" in dlg.tool_hint.text()


def test_the_four_tools_are_icons_and_only_one_is_active(qapp):
    """「請改成用 icon 方式顯示（目前介面文字太多）」。"""
    from adept.ui.widgets import IconButton

    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    assert set(dlg.tool_buttons) == set(canvas_mod.TOOLS)
    for key, btn in dlg.tool_buttons.items():
        assert isinstance(btn, IconButton)
        assert btn.text() == ""                 # 圖示鈕不放字
        assert btn.toolTip()                    # 說明退到 tooltip

    for key in canvas_mod.TOOLS:
        dlg.set_tool(key)
        assert dlg.canvas.tool() == key
        on = [k for k, b in dlg.tool_buttons.items() if b.isChecked()]
        assert on == [key]


def test_the_click_tool_drops_one_box_centred_on_the_pointer(qapp):
    """跟陣列工具的錨點講同一句話：按下去的那一點是**框的中心**。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.set_tool(canvas_mod.TOOL_CLICK)
    dlg.spin_w.setValue(6)
    dlg.spin_h.setValue(120)

    dlg.canvas.resize(400, 400)
    dlg.canvas._tool_click_at = None
    h, w = dlg.canvas.cell_shape()
    pt = dlg.canvas.norm_to_view(0.5, 0.5)
    _press(dlg.canvas, pt)

    x, y, bw, bh = dlg.canvas.to_px(dlg.canvas.regions()[0][1][-1])
    assert (bw, bh) == (6, 120)
    assert abs((x + bw / 2.0) - w / 2.0) <= 0.5
    assert abs((y + bh / 2.0) - h / 2.0) <= 0.5


def test_painting_pixels_merges_them_into_the_fewest_rectangles(qapp):
    """一顆一顆點出來的像素，放手時併成**逐列的矩形**（區域的模型是矩形）。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.set_tool(canvas_mod.TOOL_PAINT)
    dlg.canvas._paint = {(3, 5), (4, 5), (5, 5), (9, 5), (3, 6)}
    dlg.canvas._commit_paint()

    got = sorted(dlg.canvas.to_px(b) for b in dlg.canvas.regions()[0][1])
    assert got == [(3, 5, 3, 1), (3, 6, 1, 1), (9, 5, 1, 1)]


def test_right_dragging_pans_the_canvas(qapp):
    """「template 畫布按住右鍵要能拖拉移動」。"""
    from PySide6.QtCore import QPointF

    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.resize(400, 400)
    before = dlg.canvas.norm_to_view(0.0, 0.0)

    _press(dlg.canvas, QPointF(100.0, 100.0), button=Qt.RightButton)
    _move(dlg.canvas, QPointF(150.0, 130.0), buttons=Qt.RightButton)
    _release(dlg.canvas, QPointF(150.0, 130.0), button=Qt.RightButton)

    after = dlg.canvas.norm_to_view(0.0, 0.0)
    assert round(after.x() - before.x()) == 50
    assert round(after.y() - before.y()) == 30


def test_right_dragging_never_creates_a_box(qapp):
    """平移不可以順手留下一個框 —— 那是「畫布說謊」的最短路徑。"""
    from PySide6.QtCore import QPointF

    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.resize(400, 400)
    before = len(dlg.canvas.regions()[0][1])
    _press(dlg.canvas, QPointF(100.0, 100.0), button=Qt.RightButton)
    _move(dlg.canvas, QPointF(180.0, 160.0), buttons=Qt.RightButton)
    _release(dlg.canvas, QPointF(180.0, 160.0), button=Qt.RightButton)
    assert len(dlg.canvas.regions()[0][1]) == before


def test_the_numbers_table_lives_behind_a_button(qapp):
    """「表格部分建議不顯示，放在一個按鈕裡打開來可編輯」。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.1, 0.0, 0.2, 1.0))

    assert dlg.box_table.isVisible() is False
    assert "1 rectangle" in dlg.box_count.text()

    table = dlg.open_box_table()
    assert table.isVisible() is True
    assert dlg.box_table.rowCount() == 1

    # 表格是**可編輯的**，而且改完畫布上就是那個值（同一份資料）
    dlg.box_table.item(0, 2).setText("9")
    assert dlg.canvas.to_px(dlg.canvas.regions()[0][1][0])[2] == 9


# --------------------------------------------------------------------------- #
# 4. 第四輪：游標／復原／刪除／對齊，以及那個畫在左上角的標籤
# --------------------------------------------------------------------------- #
def test_no_widget_is_left_without_a_layout(qapp):
    """**使用者回報的 bug**：視窗左上角出現「Whole pixels of on…」字樣。

    widget 一旦以對話框為 parent 又不在任何 layout 裡，Qt 就把它畫在 (0, 0)
    —— **沒有家的 widget 不是隱形的，它是畫在左上角的**。
    """
    dlg = tpl_mod.TemplateDialog()
    lay = dlg.layout()
    stray = [c for c in dlg.children()
             if c.isWidgetType() and c.parent() is dlg
             and not c.isWindow() and lay.indexOf(c) < 0]
    assert stray == [], [type(c).__name__ for c in stray]
    assert dlg.box_units.parent() is dlg._table_dialog
    assert dlg.box_table.parent() is dlg._table_dialog


def test_the_toolbar_is_icons_only_and_big_enough(qapp):
    """「icon 功能列給我大一點漂亮一點」—— 而且一顆字都不放。"""
    from adept.ui.widgets import IconButton

    dlg = tpl_mod.TemplateDialog()
    buttons = (list(dlg.tool_buttons.values()) + list(dlg.align_buttons.values())
               + [dlg.btn_undo, dlg.btn_del_sel])
    for b in buttons:
        assert isinstance(b, IconButton)
        assert b.text() == ""
        assert b.toolTip()
        assert b.width() >= 32 and b.height() >= 32


def test_the_cursor_tool_selects_instead_of_drawing(qapp):
    """游標工具在空白處拖是**框選**，不是畫一個新框。"""
    from PySide6.QtCore import QPointF

    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.resize(420, 380)
    dlg.canvas.add_boxes([(0.1, 0.1, 0.1, 0.2), (0.4, 0.1, 0.1, 0.2),
                          (0.7, 0.6, 0.1, 0.2)])
    before = len(dlg.canvas.regions()[0][1])

    dlg.set_tool(canvas_mod.TOOL_CURSOR)
    a = dlg.canvas.norm_to_view(0.02, 0.02)
    b = dlg.canvas.norm_to_view(0.55, 0.45)
    _press(dlg.canvas, a)
    _move(dlg.canvas, b)
    _release(dlg.canvas, b)

    assert len(dlg.canvas.regions()[0][1]) == before      # 沒有多出一個框
    assert dlg.canvas.selection() == [0, 1]               # 完整落在套索裡的兩個


def test_ctrl_click_adds_to_the_selection(qapp):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_boxes([(0.1, 0.1, 0.2, 0.2), (0.5, 0.1, 0.2, 0.2)])
    dlg.canvas.select_box(0)
    assert dlg.canvas.selection() == [0]
    dlg.canvas.select_box(1, add=True)
    assert dlg.canvas.selection() == [0, 1]
    dlg.canvas.select_box(1, add=True)                    # 再點一次 = 取消選
    assert dlg.canvas.selection() == [0]


def test_delete_removes_every_selected_rectangle(qapp):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_boxes([(0.1, 0.1, 0.1, 0.2), (0.4, 0.1, 0.1, 0.2),
                          (0.7, 0.1, 0.1, 0.2)])
    dlg.canvas.set_selection([0, 2])
    assert dlg.delete_selected() is True
    assert len(dlg.canvas.regions()[0][1]) == 1


@pytest.mark.parametrize("how, index, expected", [
    ("left", 0, 0.1), ("right", 0, 0.7), ("center", 0, 0.4),
])
def test_aligning_moves_them_to_the_edge_of_the_selection(qapp, how, index,
                                                          expected):
    """基準是**選取範圍**的外框，不是「第一個選的那個」—— 使用者是先框一整排
    再按對齊，那時候「第一個」是哪一個他自己也不知道。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    # 三個同寬的框，左緣 0.1 / 0.4 / 0.7（cell 寬 40 px -> 4 / 16 / 28 px）
    dlg.canvas.add_boxes([(0.1, 0.1, 0.2, 0.2), (0.4, 0.3, 0.2, 0.2),
                          (0.7, 0.5, 0.2, 0.2)])
    dlg.canvas.select_all()
    assert dlg.align_selection(how) == 3

    xs = [b[0] for b in dlg.canvas.regions()[0][1]]
    assert len(set(round(x, 6) for x in xs)) == 1, xs      # 三個都對齊了
    h, w = dlg.canvas.cell_shape()
    assert abs(xs[index] - expected) < 1.5 / w


def test_aligning_needs_two_and_says_so(qapp):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.1, 0.1, 0.2, 0.2))
    assert dlg.align_selection("left") == 0
    assert "two or more" in dlg.tool_hint.text()


def test_undo_puts_the_rectangles_back(qapp):
    """畫錯一個框要能一鍵回去 —— 不然使用者不敢用工具。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.add_box((0.1, 0.1, 0.2, 0.2))
    one = dlg.regions_text()

    dlg.canvas.add_box((0.5, 0.1, 0.2, 0.2))
    assert dlg.regions_text() != one
    assert dlg.undo() is True
    assert dlg.regions_text() == one

    # 對齊、刪除、方向鍵微調也都退得回去
    dlg.canvas.add_box((0.5, 0.3, 0.2, 0.2))
    dlg.canvas.select_all()
    two = dlg.regions_text()
    dlg.align_selection("left")
    assert dlg.regions_text() != two
    assert dlg.undo() is True
    assert dlg.regions_text() == two


def test_undo_is_disabled_when_there_is_nothing_to_undo(qapp):
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas._undo.clear()
    dlg._refresh_tool_ui()
    assert dlg.btn_undo.isEnabled() is False
    assert all(not b.isEnabled() for b in dlg.align_buttons.values())


# --------------------------------------------------------------------------- #
# 5. 第五輪：k× cell 的確定度、等距的 pitch、還沒按下去的預覽
# --------------------------------------------------------------------------- #
def _alt_image(seed: int = 0) -> np.ndarray:
    """跟 big_image 一樣，但**每隔一格**的 MG 比較暗 —— 2× 才是真正的週期。"""
    img = big_image(seed)
    for k in range(0, 8, 2):
        img[:, k * PERIOD:k * PERIOD + 12] -= 35.0
    return img


def test_a_double_cell_no_longer_kills_the_certainty(qapp):
    """使用者：「假設我是 2x cell 大，certainty 可能會被壓很低，有解嗎？」

    實測不是壓很低，是**歸零**：margin 摺在「一個 cell」上，而 2× cell 的一個
    週期裡有兩個一模一樣的峰 → 最高 ＝ 次高 → 0.000，score 仍然 1.00。
    現在確定度摺在**自週期**上，位置仍然摺在整個 cell 上。
    """
    from adept.core.algo import template as at

    img = big_image()
    got = {}
    for label, px in (("1x", None), ("2x", 2 * PERIOD), ("3x", 3 * PERIOD)):
        gc = at.build_golden_cell(img, px=px)
        sp = at.cell_self_period(gc.cell)
        assert sp[0] == PERIOD, (label, sp)      # 自週期一直都是真正的那一個
        margins = []
        for phase in range(0, PERIOD, 5):
            patch = img[100:132, 3 * PERIOD + phase:3 * PERIOD + phase + 32]
            m = at.match_patch(gc.cell, patch, periodic=gc.periodic,
                               self_period=sp)
            margins.append(m.margin)
        got[label] = (min(margins), max(margins))

    assert got["1x"][0] > 0.3
    for label in ("2x", "3x"):
        assert got[label][0] > 0.3, (label, got)
        assert abs(got[label][0] - got["1x"][0]) < 0.05, got


def test_a_flat_axis_is_not_a_self_period(qapp):
    """平的那一軸對**任何**位移都相似 —— 那不是週期，是沒有結構。"""
    from adept.core.algo import template as at

    gc = at.build_golden_cell(big_image())
    sx, sy = at.cell_self_period(gc.cell)
    assert (sx, sy) == (PERIOD, gc.cell.shape[0])


def test_the_template_string_carries_the_self_period(qapp):
    """自週期是**模板的性質**（一份模板一個答案），所以存進字串、不是每顆重算。"""
    from adept.core.algo import template as at

    gc = at.build_golden_cell(big_image(), px=2 * PERIOD)
    text = at.encode_cell(gc.cell)
    assert text.startswith("gc2:")
    cell, sp = at.decode_template(text)
    assert sp == (PERIOD, gc.cell.shape[0])
    assert np.array_equal(cell, gc.cell)

    # 舊的 gc1 照讀，而且**行為與以前逐位元組相同**（自週期視同 cell 尺寸）
    parts = text.split(":")
    old = "gc1:%s:%s" % (parts[1], parts[3])
    cell1, sp1 = at.decode_template(old)
    assert np.array_equal(cell1, gc.cell)
    assert sp1 == (gc.cell.shape[1], gc.cell.shape[0])


def test_the_dialog_says_the_cell_holds_two_copies(qapp):
    """**不要等跑完 200 顆才發現** —— 選了 2× cell 的當下就講。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    assert "copies of" not in dlg.summary()

    dlg._on_double()
    assert dlg.self_period()[0] == PERIOD
    assert "2 copies of a %d x" % PERIOD in dlg.summary()
    assert "cannot tell which copy" in dlg.summary()


def test_multi_add_uses_one_pitch_for_every_gap(qapp):
    """使用者：「PERIOD 會不穩定，有時是 29 有時是 30，畫布顯示也對不齊。」

    先算小數中心、再逐個四捨五入，間距必然在 29／30 之間跳。現在**間距先取整
    數，再從第一個錨點排下去** —— 每一段都一樣長。
    """
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.spin_w.setValue(6)
    dlg.spin_h.setValue(200)
    dlg.spin_nx.setValue(9)
    dlg.spin_ny.setValue(1)
    dlg.set_tool(canvas_mod.TOOL_ARRAY)
    # 端點刻意選一個除不盡的距離（9 個框 = 8 段）
    dlg.canvas.place_array_anchor(0.05, 0.5)
    dlg.canvas.place_array_anchor(0.79, 0.5)

    xs = [dlg.canvas.to_px(b)[0] for b in dlg.canvas.array_preview()]
    gaps = [b - a for a, b in zip(xs, xs[1:])]
    assert len(gaps) == 8
    assert len(set(gaps)) == 1, gaps
    assert dlg.canvas.array_pitch()[0] == gaps[0]
    assert "every gap is the same" in dlg.tool_hint.text()
    assert "pitch %d px" % gaps[0] in dlg.tool_hint.text()

    # 真的放下去之後，表格裡的間距也一樣
    dlg.commit_array()
    xs2 = [dlg.canvas.to_px(b)[0] for b in dlg.canvas.regions()[0][1]]
    assert len(set(b - a for a, b in zip(xs2, xs2[1:]))) == 1


def test_the_next_box_is_previewed_before_you_click(qapp):
    """「MULTI-ADD 在還沒點下去前也幫我有個 box 預覽（方便對齊擺放）」。"""
    from PySide6.QtCore import QPointF

    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.resize(420, 380)
    dlg.spin_w.setValue(6)
    dlg.spin_h.setValue(120)

    for tool in (canvas_mod.TOOL_ARRAY, canvas_mod.TOOL_CLICK):
        dlg.set_tool(tool)
        assert dlg.canvas.hover_box() is None          # 游標還沒進來
        _move(dlg.canvas, dlg.canvas.norm_to_view(0.5, 0.5), buttons=Qt.NoButton)
        box = dlg.canvas.hover_box()
        assert box is not None, tool
        x, y, w, h = dlg.canvas.to_px(box)
        assert (w, h) == (6, 120)
        ch, cw = dlg.canvas.cell_shape()
        assert abs((x + w / 2.0) - cw / 2.0) <= 0.5    # 游標就是框的中心
        assert abs((y + h / 2.0) - ch / 2.0) <= 0.5

    # 游標離開畫布，預覽就要消失（畫布不能說謊）
    dlg.canvas.leaveEvent(None)
    assert dlg.canvas.hover_box() is None

    # 拖曳／游標工具不預覽（它們按下去不會長出一個固定大小的框）
    for tool in (canvas_mod.TOOL_DRAG, canvas_mod.TOOL_CURSOR):
        dlg.set_tool(tool)
        _move(dlg.canvas, dlg.canvas.norm_to_view(0.5, 0.5), buttons=Qt.NoButton)
        assert dlg.canvas.hover_box() is None, tool


def test_the_array_preview_replaces_the_single_hover(qapp):
    """已經放了錨點就預覽**整片**，不要再多一個游標下的孤兒框。"""
    dlg = tpl_mod.TemplateDialog()
    dlg.load_image(big_image(), "LOT_full.tif")
    dlg.canvas.resize(420, 380)
    dlg.set_tool(canvas_mod.TOOL_ARRAY)
    _move(dlg.canvas, dlg.canvas.norm_to_view(0.3, 0.5), buttons=Qt.NoButton)
    assert dlg.canvas.hover_box() is not None
    dlg.canvas.place_array_anchor(0.3, 0.5)
    assert dlg.canvas.hover_box() is None
