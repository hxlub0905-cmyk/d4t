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
from tests.region_cards import (  # noqa: E402
    add_region_step, region_card,
)

from conftest import first_source, wire_up  # noqa: E402  —— F10：加完卡要接線

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
    # **橫向也要有結構。** F8 第五輪之後 ROI 只剩 Profile（``roi_cross``），
    # 而它是**兩個方向共同定義**的 —— 只有直的條紋定位不出來（而且它會照實
    # 說「沒有橫的條紋」）。舊的單軸卡在這裡只需要一個方向，那張卡已經拿掉了。
    img[(np.arange(H) % 26) < 10, :] += 26.0
    return img + rng.normal(0, 3.0, (H, W)).astype(np.float32)


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    from d4t.ui import widgets as widgets_mod
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
    nid = wire_up(window.model, window.model.add_step("glv_stats"))
    window.select_node(nid)
    window._on_param_edited("roi", "epi")

    assert window.model.nodes[nid].params["output_prefix"] == "epi"
    assert "named" in window.status_text()
    from d4t.core.pipeline import get_step
    # 這一條測的是**前綴**（區域名跑到 feature 名前面），所以拿預設勾的第一顆
    # 來問就好 —— 它是哪一顆由卡片的預設決定（F18 起是 median）。
    assert "epi_glv_median" in get_step("glv_stats").resolve_features(
        window.model.nodes[nid].params)


def test_a_name_the_user_typed_is_never_overwritten(window):
    """「我明明改了它又跳回去」比沒有這個功能更糟。"""
    nid = wire_up(window.model, window.model.add_step("glv_stats"))
    window.select_node(nid)
    window._on_param_edited("output_prefix", "mine")
    window._on_param_edited("roi", "epi")
    assert window.model.nodes[nid].params["output_prefix"] == "mine"


def test_a_prefix_that_cannot_be_a_variable_name_is_refused(window):
    """特徵名是分數表達式的變數名。``my region`` 那種名字在表達式裡指不到，
    所以擋在參數驗證，而不是等使用者寫完表達式才發現。"""
    from d4t.core.pipeline import ParamError, get_step

    with pytest.raises(ParamError):
        get_step("glv_stats").validate_params({"output_prefix": "my region"})
    with pytest.raises(ParamError):
        get_step("glv_stats").validate_params({"output_prefix": "2nd"})
    assert get_step("glv_stats").validate_params(
        {"output_prefix": "epi_2"})["output_prefix"] == "epi_2"


# --------------------------------------------------------------------------- #
# 2. 曲線面板
# --------------------------------------------------------------------------- #

def test_the_panel_hides_itself_for_any_other_card(window):
    nid = wire_up(window.model, add_region_step(window.model, "roi_cross"))
    window.select_node(nid)
    window.refresh_preview(sync=True)
    assert window.profile_panel_visible() is True

    other = wire_up(window.model, window.model.add_step("glv_stats"))
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

def _stripped(result):
    """把 profiles 拿掉，模擬「recipe 還沒加上這張卡」時算出來的那一筆。"""
    ctx = getattr(result, "context", None)
    if ctx is not None:
        ctx.meta.pop("profiles", None)
    return result



def _flat(seed: int = 0) -> np.ndarray:
    """整張都是同一種材質 —— 沒有任何東西可以定位。"""
    return np.random.default_rng(seed).normal(60.0, 4.0, (H, W)).astype(np.float32)


@pytest.fixture(scope="module")
def mixed_lot(tmp_path_factory):
    """一批混合的資料：大部分看得到結構，每四顆有一顆整張均勻。"""
    import tifffile
    from make_sample import generate

    out = generate(str(tmp_path_factory.mktemp("f7_11_mix")), n=12, seed=4)
    rng = np.random.default_rng(7)
    pages = []
    for i in range(12):
        ref = _flat(i) if i % 4 == 3 else _layout(int(rng.integers(-20, 21)), seed=i)
        test = ref.copy()
        test[60:68, 60:68] += 55.0
        pages += [np.clip(test, 0, 255).astype(np.uint8),
                  np.clip(ref, 0, 255).astype(np.uint8)]
    tifffile.imwrite(out["tiff"], np.stack(pages))
    return out


@pytest.fixture
def mixed_window(qapp, mixed_lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(mixed_lot["klarf"], sync=True)
    nid = wire_up(win.model, add_region_step(win.model, "roi_cross"))
    win.model.set_param(nid, "roi_out", "epi")
    win.select_node(nid)
    yield win
    win.close()


def test_the_thumbnail_placement_matches_the_thumbnail_itself(qapp):
    """框畫在縮圖上，所以縮圖的 letterbox 偏移必須算得跟 ``make_thumb`` 一樣。

    兩者分開放的話，哪天改了縮圖的縮放規則而忘了改另一邊，框就會整批偏掉 ——
    而畫面上看起來只是「框好像有點歪」，不會有人聯想到是縮圖改過。
    """
    from d4t.ui.gallery import make_thumb, thumb_placement

    for shape in ((64, 128), (128, 64), (100, 100), (7, 250)):
        img = np.full(shape, 255, np.uint8)         # 全白 -> 補的黑邊一目了然
        thumb = make_thumb(img, 96)
        x0, y0, tw, th = thumb_placement(shape, 96)
        ys, xs = np.nonzero(thumb)
        assert (int(xs.min()), int(ys.min())) == (x0, y0)
        assert (int(xs.max()) + 1, int(ys.max()) + 1) == (x0 + tw, y0 + th)


def test_the_boxes_follow_the_structure_across_defects(mixed_window):
    """**這個視窗存在的理由**：在第 1 顆剛好的框，第 50 顆可能整個偏掉。"""
    from d4t.ui.region_check import check_regions

    items = mixed_window._items()[:12]
    results = check_regions(mixed_window.model.to_recipe(), items,
                            mixed_window.model.kind, mixed_window.selected_node,
                            ["epi"], thumb_size=120, source="ref")
    located = [r for r in results if r["located"] and r["boxes"]]
    assert len(located) >= 6
    lefts = {round(r["boxes"][0][1][0]) for r in located}
    assert len(lefts) > 1, "每顆的框都落在同一個位置 —— 那就沒有跟著結構跑"


def test_a_patch_with_no_structure_is_marked_not_guessed(mixed_window):
    from d4t.ui.region_check import check_regions

    results = check_regions(mixed_window.model.to_recipe(),
                            mixed_window._items()[:12], mixed_window.model.kind,
                            mixed_window.selected_node, ["epi"], 120, "ref")
    fell_back = [r for r in results if not r["located"]]
    assert fell_back, "這批刻意放了整張均勻的 patch"
    for r in fell_back:
        assert r["error"] is None, "退回整張圖是正常結果，不是錯誤"
        assert r["boxes"], "退回之後區域仍然存在（就是整張圖）"


def test_check_regions_never_raises_on_a_broken_pipeline(mixed_window):
    """跟引擎「單顆爆不殺整批」同一個契約 —— 一顆壞掉只是一格壞掉。"""
    from d4t.ui.region_check import check_regions

    nid = mixed_window.selected_node
    mixed_window.model.set_param(nid, "source", "nope")      # 不存在的影像流
    results = check_regions(mixed_window.model.to_recipe(),
                            mixed_window._items()[:3], mixed_window.model.kind,
                            nid, ["epi"], 120, "ref")
    assert len(results) == 3
    assert all(r["error"] for r in results)


def test_the_window_summarises_and_can_show_only_the_failures(mixed_window):
    assert mixed_window.region_check_available() is True
    assert mixed_window.open_region_check(n=12, sync=True) is True

    win = mixed_window.region_window
    assert "12 defects" in win.summary_text()
    assert "fell back" in win.summary_text()
    assert len(win.visible_ids()) == 12

    failed = win.failed_ids()
    assert failed, "這批刻意放了定位不出來的 patch"
    win.only_failed.setChecked(True)
    assert win.visible_ids() == failed, "只看失敗的 —— 那些才是要看的"
    win.only_failed.setChecked(False)
    assert len(win.visible_ids()) == 12


def test_clicking_a_thumbnail_jumps_to_that_defect(mixed_window):
    assert mixed_window.open_region_check(n=6, sync=True) is True
    win = mixed_window.region_window
    seen = []
    win.defect_activated.connect(seen.append)
    win._cells[2].clicked.emit(win._cells[2].defect_id)
    assert seen == [win._cells[2].defect_id]


def test_the_button_only_appears_for_cards_that_define_a_region(mixed_window):
    assert mixed_window.selected_regions() == ["epi", "epi_center", "epi_others"]
    assert mixed_window.region_check_available() is True

    other = wire_up(mixed_window.model, mixed_window.model.add_step("glv_stats"))
    mixed_window.select_node(other)
    assert mixed_window.selected_regions() == []
    assert mixed_window.region_check_available() is False


def test_without_a_dataset_the_button_is_off_and_says_why(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        nid = wire_up(win.model, add_region_step(win.model, "roi_cross"))
        win.select_node(nid)
        assert win.selected_regions() == ["cross", "cross_center", "cross_others"]
        assert win.region_check_available() is False
        assert win.open_region_check(n=4, sync=True) is False
        assert "No dataset" in win.status_text()
    finally:
        win.close()


def test_every_cell_paints(qapp, mixed_window):
    """自繪元件的 bug 只在 paintEvent 真的跑過時才浮出來。"""
    from PySide6.QtGui import QPixmap

    assert mixed_window.open_region_check(n=12, sync=True) is True
    win = mixed_window.region_window
    for name in ("light", "dark"):
        theme_mod.set_theme(name)
        for cell in win._cells:
            pm = QPixmap(cell.size())
            pm.fill()
            cell.render(pm)
            assert not pm.isNull()
    theme_mod.apply_theme(qapp, "light")


# --------------------------------------------------------------------------- #
# F11 Region-1：區域名是**選**的，不是打的
# --------------------------------------------------------------------------- #
def test_the_mask_card_offers_the_regions_defined_upstream(window):
    """上游定義了哪些區域，程式本來就知道 —— 使用者不必（也不能）用打的。

    F11 Region-1 時這一格是勾選框；**F12 起它是畫布上的一條線**，這一格只顯示
    接的是什麼（同 F9-6 對影像來源做的事）。兩版要守的是同一件事：要打的字必須
    跟上游卡片的輸出一字不差，而打錯的時候 lint 要跑一次才講。
    """
    from PySide6.QtWidgets import QLineEdit

    tpl = wire_up(window.model, add_region_step(window.model, "roi_template"))
    window.model.set_param(tpl, "regions", "epi: 0.1,0,0.3,1 | mg: 0.5,0,0.2,1")

    mask = wire_up(window.model, window.model.add_step("roi_mask"))
    assert window.model.available_regions(before_node=mask) == [
        "epi", "epi_center", "epi_others",
        "mg", "mg_center", "mg_others"]

    window.select_node(mask)
    editor = window.param_form.editor("regions")
    assert isinstance(editor, QLineEdit) and editor.isReadOnly(), \
        "區域的來源只在畫布上決定（F12）"

    # 拉一條線過去 = 挑了那個區域，而那件事在參數上留下的字一模一樣。
    window._on_edge_added(tpl, mask, "epi", "regions")
    window._on_edge_added(tpl, mask, "mg", "regions")
    assert window.model.nodes[mask].params["regions"] == "epi,mg"
    assert (tpl, mask, "epi", "regions") in window.model.region_lines()


def test_a_region_name_from_the_recipe_survives_even_if_upstream_changed(window):
    """看不到就被靜靜刪掉，是最糟的一種「幫忙」。

    recipe 指著一個上游沒有人定義的區域時，那個字要**留在畫面上**（lint 會用
    ``unknown-region`` 講出它壞在哪）。畫布上沒有那條線 —— 因為真的沒有人
    定義它，而畫一條無中生有的線比沒有線更糟。
    """
    from PySide6.QtWidgets import QLineEdit

    mask = wire_up(window.model, window.model.add_step("roi_mask"))
    window.model.set_param(mask, "regions", "gone")
    window.select_node(mask)

    editor = window.param_form.editor("regions")
    assert isinstance(editor, QLineEdit) and editor.isReadOnly()
    assert editor.text() == "gone"
    assert [ln for ln in window.model.region_lines() if ln[1] == mask] == []
