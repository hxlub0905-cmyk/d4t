# F8 第七輪（UI 那一半）：一鍵校正接到畫面上，而且按鈕放得下自己的字。
"""三件事：

1. **按下去 → 量整批 → 填回卡片。** 走 ``set_param`` 那條路（跟手動填同一條），
   所以可以復原、參數表跟著更新。
2. **批次不同意 → 拒填 + 紅字講出兩群。** 安靜地不填，使用者會以為按了沒反應。
3. **「Use …」按鈕要放得下自己的字。** 使用者回報「只看得到一半的數字」——
   square 形狀的 QSS 是 ``max-width: 22px``，文字按鈕塞進去只剩「Use 4…」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import wire_up  # noqa: E402  —— F10：加完卡要接線

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402

_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import inspectors as insp_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    from d4t.ui.workers import CalibrateWorker
    g.update(QApplication=QApplication, insp_mod=insp_mod,
             studio_mod=studio_mod, theme_mod=theme_mod,
             CalibrateWorker=CalibrateWorker)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lines_lot(tmp_path_factory):
    from make_sample import generate

    return generate(str(tmp_path_factory.mktemp("f8_cal")), n=8, seed=4,
                    size=128, pitch=18, noise=4.0, pattern="lines")


@pytest.fixture
def win(qapp, lines_lot):
    w = studio_mod.StudioWindow(show_welcome_on_start=False)
    w.load_dataset_path(lines_lot["klarf"], sync=True)
    nid = wire_up(w.model, w.model.add_step("roi_cross"))
    w.model.set_param(nid, "roi_out", "xing")
    w.select_node(nid)
    yield w
    w.close()


# --------------------------------------------------------------------------- #
# 1. 按下去 → 量整批 → 填回卡片
# --------------------------------------------------------------------------- #
def test_the_inspector_offers_the_button(qapp):
    insp = insp_mod.CrossInspector()
    assert insp.calibrate_btn.text().startswith("Measure")
    seen = []
    insp.calibrate_requested.connect(lambda: seen.append(1))
    insp.calibrate_btn.click()
    assert seen == [1]


def test_measuring_the_lot_fills_in_the_pitch(qapp, win):
    nid = win.selected_node
    assert float(win.model.nodes[nid].params.get("vertical_pitch", 0)) == 0.0

    result = CalibrateWorker.run_sync(
        win.model.to_recipe(), win._items(), win.model.kind, nid,
        dict(win.model.nodes[nid].params))
    win._on_calibrated(result)

    got = float(win.model.nodes[nid].params["vertical_pitch"])
    assert got > 2.0, "量完沒有填"
    # 合成資料的直條紋 pitch 是 18（make_sample 的 lines pattern）
    assert got == pytest.approx(18.0, abs=1.5)
    # 參數表也要顯示新值 —— 不然畫面上那一格還是舊的
    assert float(win.param_form.values()["vertical_pitch"]) == got


def test_the_fill_is_undoable(qapp, win):
    """會改 recipe 而撤不掉的按鈕，比沒有那顆按鈕糟。"""
    nid = win.selected_node
    result = CalibrateWorker.run_sync(
        win.model.to_recipe(), win._items(), win.model.kind, nid,
        dict(win.model.nodes[nid].params))
    win._on_calibrated(result)
    assert float(win.model.nodes[nid].params["vertical_pitch"]) > 2.0

    for _ in range(10):                      # 兩軸 × (pitch, pitch_2, width)
        if float(win.model.nodes[nid].params.get("vertical_pitch", 0)) == 0.0:
            break
        win.undo()
    assert float(win.model.nodes[nid].params.get("vertical_pitch", 0)) == 0.0


def test_a_lot_that_disagrees_reaches_the_user_not_the_recipe(qapp, win):
    """拒絕要看得到。安靜地不填的話，使用者會以為按了沒反應然後再按一次。"""
    from d4t.core.algo.grid import AxisCalibration

    nid = win.selected_node
    win._on_calibrated({
        "x": AxisCalibration(0.0, 0.0, 0.0, 50, 50, 0.5,
                             "the defects do not agree: 24 of them measure "
                             "about 12.0 px, 26 about 24.0 px."),
        "y": AxisCalibration(34.0, 0.0, 14.0, 50, 50, 0.98, ""),
    })
    # x 拒了 → 不填；y 好 → 照填。只報壞消息的話使用者會把好的那半也改掉。
    assert float(win.model.nodes[nid].params.get("vertical_pitch", 0)) == 0.0
    assert float(win.model.nodes[nid].params["horizontal_pitch"]) == 34.0
    text = win.status_text()
    assert "do not agree" in text
    assert "flat" in text, "填成功的那一半沒講"


def test_switching_card_mid_measure_does_not_write_into_the_wrong_card(
        qapp, win):
    """量整批要幾秒，量完的時候使用者可能已經選了別張卡。"""
    from d4t.core.algo.grid import AxisCalibration

    other = wire_up(win.model, win.model.add_step("align"))
    win.select_node(other)
    win._on_calibrated({
        "x": AxisCalibration(18.0, 0.0, 6.0, 8, 8, 1.0, ""),
        "y": AxisCalibration(18.0, 0.0, 6.0, 8, 8, 1.0, ""),
    })
    assert "vertical_pitch" not in win.model.nodes[other].params


# --------------------------------------------------------------------------- #
# 2. 量測用的是卡片實際看的那條流
# --------------------------------------------------------------------------- #
def test_it_measures_the_stream_the_card_reads(qapp, win):
    """上游有 Enhance 卡時，量原始檔就量錯了對象 —— 收集器要跑 pipeline。"""
    from d4t.ui.region_check import collect_source_images

    nid = win.selected_node
    imgs = collect_source_images(win.model.to_recipe(), win._items(),
                                 win.model.kind, nid, "ref")
    assert len(imgs) == len(win._items())
    assert all(isinstance(a, np.ndarray) for a in imgs)


# --------------------------------------------------------------------------- #
# 3. 面板上的按鈕要放得下自己的字（使用者回報的切邊）
# --------------------------------------------------------------------------- #
def test_the_use_button_is_wide_enough_for_its_own_text(qapp):
    """square 形狀的 QSS 是 max-width 22px —— 「Use 40.0 / 33.0 px」塞進去
    只剩「Use 4…」。量的是**按鈕自己**放不放得下，不是面板剪不剪它。"""
    from PySide6.QtGui import QFontMetrics

    from d4t.ui.widgets import ProfilePanel

    SIZE, MG, EPI = 128, 24, 34
    rng = np.random.default_rng(0)
    img = np.full((SIZE, SIZE), 90.0, np.float32)
    img[np.arange(SIZE) % EPI < 14, :] = 180.0
    img[:, np.arange(SIZE) % MG < 8] = 220.0
    img += rng.normal(0, 2.0, (SIZE, SIZE)).astype(np.float32)
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    get_step("roi_cross")().run(ctx, {
        "source": "ref", "place": "beside_vertical", "roi_out": "xing"})

    insp = insp_mod.CrossInspector()
    panel = insp.across
    panel.resize(400, 120)
    panel.set_data("upright stripes",
                   dict(ctx.meta["crossings"]["xing"]["x"], pitches_used=[]))

    btn = panel._fill_btn
    text = panel.fill_button_text()
    assert text, "沒有可以填的值，這條測試在測空氣"
    need = QFontMetrics(btn.font()).horizontalAdvance(btn.text())
    assert btn.width() >= need, (
        "按鈕 %d px 寬，字要 %d px —— 又被 QSS 的 max-width 鎖住了"
        % (btn.width(), need))
    # 而且要整顆都在面板裡（貼右邊放的，放出去一樣看不到）
    assert btn.x() >= 0 and btn.x() + btn.width() <= panel.width()
