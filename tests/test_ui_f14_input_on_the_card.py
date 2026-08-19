# F14-1：資料的入口長在讀它的那張卡上 — authored 2026-08-19.
"""使用者：「關於 Input 我想改成統一從卡片內 Input⋯⋯如果按照目前從 UI 上方，
使用者會錯亂而且沒辦法多開」，接著定調：**「工具列拿掉吧（會混淆）」**。

那跟這幾輪一直在講的是同一條規矩：以前檔案在**工具列**上選，而畫布上那張
Load 卡完全不會說它讀的是哪個檔案 —— 同一件事兩個地方，而畫布是說謊的那一個。

這一份鎖住三件事：

1. 工具列上**沒有**資料的入口了（而入口沒有變少：空白狀態仍然一種 source 一列）；
2. 入口在**讀那份資料的那張卡**上，判準是 `Step.is_source()`（沒有影像輸入的卡）
   —— 不是一張寫死的名單，所以下一張入口卡不必記得回來註冊；
3. **畫布也要跟著說得出來**：那張卡上印著現在載的是哪一份，否則搬家只搬了一半。

⚠ 這一輪**沒有**動「一份 recipe 一個 dataset」那個前提（多 source 是第二步，
要先定配對規則）。這裡只是把入口搬到對的地方 —— 而那天到了，入口已經在了。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QToolButton   # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.core.pipeline import get_step, list_steps        # noqa: E402
from d4t.ui import scope                                  # noqa: E402
from d4t.ui import studio as studio_mod                   # noqa: E402
from d4t.ui import theme as theme_mod                     # noqa: E402
from d4t.ui.scope import HIDDEN_STEPS                     # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f14")), n=5, seed=3)


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1500, 950)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 工具列上沒有了，但入口沒有變少
# --------------------------------------------------------------------------- #
def test_the_toolbar_carries_no_data_entry(window):
    texts = set()
    for a in window.toolbar.actions():
        w = window.toolbar.widgetForAction(a)
        if isinstance(w, QToolButton):
            texts.add(w.text())
    for src in scope.INPUT_SOURCES:
        assert src.title not in texts and (src.short or "!") not in texts
    for att in scope.ATTACHMENTS:
        assert att.title not in texts
    # recipe 留著 —— 它不是資料，是這份 pipeline 本身。
    assert "Open recipe…" in texts


def test_the_empty_state_still_offers_every_source(window):
    """畫面最大的那一塊（沒有資料時）是第一次進來的人真的會看的地方。"""
    for src in scope.INPUT_SOURCES:
        btn = window.empty_source_buttons[src.key]
        assert btn.text() == src.title
        assert btn.isEnabled()


# --------------------------------------------------------------------------- #
# 2. 入口在卡片上
# --------------------------------------------------------------------------- #
def test_every_source_card_has_the_entry_and_no_other_card_does(window):
    """判準是 `Step.is_source()`，不是一張寫死的名單。"""
    first = None
    for cls in list_steps():
        if cls.key in HIDDEN_STEPS:
            continue
        nid = window.model.add_step(cls.key)
        first = first or nid
        window.select_node(nid)
        label = window.param_form.source_button().text()
        assert bool(label) is window.param_form.has_source_action()
        assert bool(label) is cls.is_source(), (
            "%s：is_source=%s 但入口 %s" % (cls.key, cls.is_source(),
                                          "在" if label else "不在"))


def test_the_data_card_says_which_lot_it_is_reading(window, lot):
    window.load_dataset_path(lot["klarf"], sync=True)
    nid = window.model.node_order[0]
    window.select_node(nid)
    assert window.param_form.source_button().text() == \
        studio_mod.StudioWindow.DATA_SOURCE_LABEL
    note = window.param_form._source_note.text()
    assert Path(lot["klarf"]).name in note
    assert "5 defects" in note


def test_before_anything_is_loaded_it_says_so(window):
    nid = window.model.add_step("load_patch")
    window.select_node(nid)
    assert window.param_form._source_note.text() == "No data loaded yet"


def test_the_attachment_card_opens_the_attachment(window, lot, monkeypatch):
    """`load_sidecar` 的鈕直接開 GLAS 匯出，不是一張選單 —— 它只有一條路。"""
    called = []
    monkeypatch.setattr(window, "_on_open_gds", lambda: called.append(1))
    nid = window.model.add_step("load_sidecar")
    window.select_node(nid)
    assert window.param_form.source_button().text() == "Open GDS export…"
    window._on_source_requested()
    assert called == [1]


# --------------------------------------------------------------------------- #
# 3. 畫布跟著說得出來
# --------------------------------------------------------------------------- #
def test_the_card_on_the_canvas_shows_the_file(window, lot):
    window.load_dataset_path(lot["klarf"], sync=True)
    nid = window.model.node_order[0]
    parts = window.pipeline.node_item(nid).summary_parts()
    assert Path(lot["klarf"]).name in parts, parts
    assert parts[0] == Path(lot["klarf"]).name, "資料是這張卡的第一件事"


def test_only_the_source_card_shows_it(window, lot):
    """`Denoise` 上印一個檔名沒有意義 —— 它讀的是上游那條流。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    dn = window.add_card_after(src, "denoise")
    parts = window.pipeline.node_item(dn).summary_parts()
    assert Path(lot["klarf"]).name not in parts, parts
