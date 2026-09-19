# F99 P0-4：截字截在最重要的字上 — authored 2026-09-08.
"""2026-09-08 的外部評審在預設版面上看到四處截字，而每一處截掉的都是**身分
資訊**：Verdict 膠囊的類別名（「:han one box is off」）、Results 縮圖底下的類別
名（「more than on…」）、設定區 Region 那一格的區域名（「…between_columns, be」）。

省略號是「畫布不能說謊」的正確做法（`canvas.py` F7 §12.5），但被省略的是名字
的時候，該做的是換行、給寬度、或至少停在上面讀得到整句 —— 不是省略。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "light")
    yield app


def test_the_verdict_chip_grows_with_its_name(qapp):
    """`setMinimumWidth(112)` 的意思是「版面可以把我縮到 112」——
    於是長一點的類別名被從左邊切掉。最小寬度要跟著字走。"""
    from d4t.ui.feature_text import VerdictChip
    chip = VerdictChip()
    chip.set_verdict(2, label="more than one box is off")
    need = chip.fontMetrics().horizontalAdvance(chip.text())
    assert chip.minimumWidth() >= need, (chip.minimumWidth(), need)
    chip.set_verdict(None)
    assert chip.minimumWidth() >= 112


def test_the_region_slot_wraps_instead_of_clipping(qapp):
    from d4t.ui.wiring_slot import REGION, WiringSlot
    slot = WiringSlot(REGION, "on_pattern, between_columns, between_rows")
    assert slot.text.wordWrap() is True
    assert "between_rows" in slot.text.text()


def test_a_gallery_tile_tells_its_whole_caption_on_hover(qapp):
    """一格 96 px 的縮圖底下省略是對的（寬度不是免費的），但停在上面要讀得到
    整句 —— tile 是畫的不是 widget，所以 tooltip 走 viewport 的事件。"""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QToolTip

    from d4t.ui import gallery as gal_mod
    p = gal_mod.GalleryPanel()
    p.resize(700, 400)
    p.show()
    qapp.processEvents()
    p.set_items([{"defect_id": "4", "bin": 2, "score": 35.506, "ok": True,
                  "cls": "more than one box is off", "thumb": None}])
    qapp.processEvents()
    grid = p.grid
    rect = grid.tile_rect(0) if hasattr(grid, "tile_rect") else None
    if rect is None:
        pytest.skip("這一版的縮圖牆沒有暴露 tile 幾何")
    pos = rect.center()
    ev = QHelpEvent(QHelpEvent.ToolTip, pos, grid.viewport().mapToGlobal(pos))
    assert grid.viewportEvent(ev) is True
    qapp.processEvents()
    assert "more than one box is off" in QToolTip.text()
    p.close()


def test_region_cards_carry_their_region_name_in_the_title(qapp):
    """三張「ROI」在畫布上以前分不出來（P1-3）：唯一的區別是第三行 9 px 灰字
    裡的 node id。區域名是那張卡的身分，上標題。量測卡與影像卡不帶。"""
    from d4t.ui import canvas as canvas_mod
    c = canvas_mod.PipelineCanvas()
    c.set_nodes([
        {"node_id": "load", "label": "Load one image", "group": "input",
         "enabled": True, "summary": "", "reads": [], "writes": ["single"],
         "produces": ["single"]},
        {"node_id": "roi_a", "label": "ROI", "group": "region", "enabled": True,
         "summary": "", "reads": ["single"], "writes": ["single"],
         "produces": [], "regions_out": ["on_pattern"],
         "regions_produced": ["on_pattern"]},
        {"node_id": "roi_b", "label": "ROI", "group": "region", "enabled": True,
         "summary": "", "reads": ["single"], "writes": ["single"],
         "produces": [], "regions_out": ["between_rows"],
         "regions_produced": ["between_rows"]},
        {"node_id": "glv", "label": "GLV", "group": "measure", "enabled": True,
         "summary": "", "reads": ["single"], "writes": ["single"],
         "produces": [], "regions_out": ["on_pattern"],
         "regions_produced": []},
    ], [("load", "roi_a"), ("load", "roi_b"), ("load", "glv")])
    titles = {nid: c.node_item(nid).title() for nid in c.node_ids()}
    assert titles["roi_a"] == "ROI · on_pattern"
    assert titles["roi_b"] == "ROI · between_rows"
    assert titles["roi_a"] != titles["roi_b"], "同名的卡要分得出來"
    assert titles["glv"] == "GLV", "量測卡把區域原樣送出去，那不是它的身分"
    assert titles["load"] == "Load one image"


def test_the_verdict_note_only_speaks_when_the_preview_stopped_early(qapp):
    """膠囊寫著「—」的時候要說為什麼（P1-2）——而且只在那一種情況講話。"""
    from d4t.ui.studio import verdict_note
    said = verdict_note("glv", None, True)
    assert "glv" in said
    # ⚠ **那幾個字要點得下去**（F117 D1）：以前這裡寫的是「press Esc」，
    # 而 Esc 在這個畫面的意思是「放掉手上的東西」—— 一句正確而想不到的
    # 提示等於沒有提示。Esc 照樣有效，寫在 tooltip 上。
    assert "<a href=" in said and "run to the end" in said
    assert verdict_note(None, None, True) == "", "沒選卡：預覽本來就跑完"
    assert verdict_note("glv", 2, True) == "", "真的有判定：膠囊自己在講"
    assert verdict_note("glv", None, False) == "", "跑出錯：狀態列在講"


def test_the_help_button_lists_open_windows(qapp):
    """P2-6：十一個頂層視窗、零個視窗管理。工具列裝不下第十三顆鈕（1366 上只剩
    76 px），所以掛在 Help 的小箭頭上。"""
    from PySide6.QtWidgets import QToolButton, QWidget

    from d4t.ui import windows_menu
    a, b = QWidget(), QWidget()
    a.show()
    rows = windows_menu.rows(lambda: [("A", a), ("B", b), ("C", None)])
    assert [(t, alive) for t, _w, alive in rows] == [("A", True), ("B", False),
                                                     ("C", False)]
    btn = QToolButton()
    btn.setToolTip("Help")
    windows_menu.attach(btn, lambda: [("A", a)])
    assert btn.menu() is not None
    assert btn.popupMode() == QToolButton.MenuButtonPopup, "鈕本身照舊，只多一個箭頭"
    btn.menu().aboutToShow.emit()
    texts = [act.text() for act in btn.menu().actions()]
    assert "A" in texts
    a.close()
