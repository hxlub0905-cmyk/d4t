# F7-11 驗收（UI）：輸出名前綴、投影曲線面板、過期預覽結果。
"""三件事都是為了同一個目的：**讓「量兩個區域」這件事真的做得起來。**

- 前綴：沒有它，兩張量測卡的數字會互相蓋掉（跑得完、少一半）。
- 面板：沒有它，「敏感度」是一個要盲填的數字。
- 過期預覽：面板讓一個一直都在的 bug 現形（見下）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

W = H = 128


def _layout(shift: int = 0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((H, W), 120.0, np.float32)
    lo, hi = 40 + shift, 88 + shift
    img[:, max(0, lo):max(0, hi)] = 60.0
    for edge in (lo, hi):
        if 2 <= edge <= W - 2:
            img[:, edge - 2:edge + 2] = 210.0
    return img + rng.normal(0, 3.0, (H, W)).astype(np.float32)


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
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    """一批「MG | 亮交界 | EPI | 亮交界 | MG」的 patch，結構位置逐顆不同。"""
    import tifffile
    from make_sample import generate

    out = generate(str(tmp_path_factory.mktemp("f7_11")), n=6, seed=5)
    rng = np.random.default_rng(2)
    pages = []
    for _ in range(6):
        ref = _layout(int(rng.integers(-18, 19)), seed=int(rng.integers(0, 999)))
        test = ref.copy()
        test[60:68, 60:68] += 55.0                  # 缺陷永遠在中央
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
# 1. 輸出名前綴
# --------------------------------------------------------------------------- #
def test_picking_a_region_names_the_results_after_it(window):
    """「兩張卡的特徵會互相蓋掉」是一個命名空間的問題，而製程工程師沒有理由要
    懂那是什麼。但他把卡指到 `epi` 這個動作已經表達了意圖 —— 工具把話補完。"""
    nid = window.model.add_step("glv_stats")
    window.select_node(nid)
    window._on_param_edited("roi", "epi")

    assert window.model.nodes[nid].params["output_prefix"] == "epi"
    assert "named" in window.status_text()
    from adept.core.pipeline import get_step
    assert "epi_glv_mean" in get_step("glv_stats").resolve_features(
        window.model.nodes[nid].params)


def test_a_name_the_user_typed_is_never_overwritten(window):
    """「我明明改了它又跳回去」比沒有這個功能更糟。"""
    nid = window.model.add_step("glv_stats")
    window.select_node(nid)
    window._on_param_edited("output_prefix", "mine")
    window._on_param_edited("roi", "epi")
    assert window.model.nodes[nid].params["output_prefix"] == "mine"


def test_a_prefix_that_cannot_be_a_variable_name_is_refused(window):
    """特徵名是分數表達式的變數名。``my region`` 那種名字在表達式裡指不到，
    所以擋在參數驗證，而不是等使用者寫完表達式才發現。"""
    from adept.core.pipeline import ParamError, get_step

    with pytest.raises(ParamError):
        get_step("glv_stats").validate_params({"output_prefix": "my region"})
    with pytest.raises(ParamError):
        get_step("glv_stats").validate_params({"output_prefix": "2nd"})
    assert get_step("glv_stats").validate_params(
        {"output_prefix": "epi_2"})["output_prefix"] == "epi_2"


# --------------------------------------------------------------------------- #
# 2. 曲線面板
# --------------------------------------------------------------------------- #
def test_the_panel_shows_the_curve_for_the_selected_card(window):
    nid = window.model.add_step("roi_profile")
    window.model.set_param(nid, "roi_out", "epi")
    window.select_node(nid)
    window.refresh_preview(sync=True)

    assert window.profile_panel_visible() is True
    assert window.profile_panel.has_data() is True
    summary = window.profile_panel.summary()
    assert "epi" in summary and "confidence" in summary


def test_the_panel_hides_itself_for_any_other_card(window):
    nid = window.model.add_step("roi_profile")
    window.select_node(nid)
    window.refresh_preview(sync=True)
    assert window.profile_panel_visible() is True

    other = window.model.add_step("glv_stats")
    window.select_node(other)
    window.refresh_preview(sync=True)
    assert window.profile_panel_visible() is False
    assert window.profile_panel.has_data() is False


def test_the_panel_paints_with_and_without_data(qapp):
    """自繪元件的 bug 只在 ``paintEvent`` 真的跑過時才浮出來
    （這一輪就漏掉一個 import，開窗才炸）。"""
    from PySide6.QtGui import QPixmap

    panel = widgets_mod.ProfilePanel()
    panel.resize(320, 96)
    for data in (None,
                 {"axis": "x", "profile": [1.0, 5.0, 9.0, 4.0, 2.0],
                  "raw": [1.0, 6.0, 9.0, 3.0, 2.0], "transitions": [2],
                  "bands": [[0, 2], [2, 5]], "picked": [2, 5],
                  "confidence": 42.0}):
        panel.set_data("epi", data)
        for name in ("light", "dark"):
            theme_mod.set_theme(name)
            pm = QPixmap(panel.size())
            pm.fill()
            panel.render(pm)          # 例外會在這裡冒出來
            assert not pm.isNull()
    theme_mod.apply_theme(qapp, "light")


# --------------------------------------------------------------------------- #
# 3. 過期的預覽結果
# --------------------------------------------------------------------------- #
def test_a_stale_background_preview_never_overwrites_a_newer_one(window):
    """``PreviewWorker`` 只合併「還沒開跑」的請求；已經在跑的那筆照樣會跑完並
    發出 ready。所以「先送出背景預覽、接著又跑了同步預覽」的時候，舊的那筆會
    **後到**，把新的畫面蓋掉 —— 而且不會再更新，因為沒有人會再算一次。

    這個順序在實際操作裡並不罕見（點卡片 → 立刻改參數），只是以前的症狀是
    「影像閃一下」；投影曲線面板把它變成「面板整個空白」，才浮出來。
    """
    nid = window.model.add_step("roi_profile")
    window.model.set_param(nid, "roi_out", "epi")
    window.select_node(nid)

    stale = window.refresh_preview(sync=True) and window._last_result
    window.refresh_preview(sync=True)          # 這一筆才是畫面上的現況
    assert window.profile_panel.has_data() is True

    # 模擬那筆更早的背景預覽現在才回來（世代編號已經不是它出發時那個）
    window._on_async_preview_ready(_stripped(stale))
    assert window.profile_panel.has_data() is True, "過期的結果把畫面蓋掉了"


def _stripped(result):
    """把 profiles 拿掉，模擬「recipe 還沒加上這張卡」時算出來的那一筆。"""
    ctx = getattr(result, "context", None)
    if ctx is not None:
        ctx.meta.pop("profiles", None)
    return result


def test_a_current_background_result_is_still_applied(window):
    """擋掉過期的，不可以順手把正常的也擋掉。"""
    nid = window.model.add_step("roi_profile")
    window.model.set_param(nid, "roi_out", "epi")
    window.select_node(nid)
    window.refresh_preview(sync=True)
    result = window._last_result

    window._async_epoch = window._preview_epoch      # 「這筆是最新的」
    window.profile_panel.set_data("", None)
    window._on_async_preview_ready(result)
    assert window.profile_panel.has_data() is True
