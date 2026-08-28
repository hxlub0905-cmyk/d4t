# 畫布上的「整批跑一次」（F50，2026-08-28；原 F30 Phase D 的 Output 框）。
"""**這幾張卡跟其他卡不一樣，它們整批只跑一次。**

畫布上其他每一張卡都是「一顆 defect 跑一次」。Output 段那幾張是在**整批跑完
之後**才跑，而且只跑一次（`Step.scale == SCALE_LOT`）。

⚠ **這一支 2026-08-28 換了守的東西，不是換了名字。** F30 用的是畫在卡片
**外面**的一個虛線框（`ui/output_band.py`），使用者定調拿掉它，理由是編碼錯
了：**框的意思是「這幾個是一組」，而真相是「跑的時間不一樣」** —— 那是一張卡
自己的屬性，不是一群卡的關係。順帶治好一個 bug（框從卡片位置算出來，所以每一
個拖曳 frame 重建一次，在 `MinimalViewportUpdate` 底下累積成殘影）。

所以守的四條也跟著翻面：

1. **判準是 `Step.scale`，不是 group、也不是一份寫死的 key 清單**；
2. **腳帶用字，不只用顏色**（推廣鐵則：一條色帶不是一句話）；
3. **埠均分的是卡片本體，不是本體加腳帶**（不然有腳帶的卡埠會整體下偏）；
4. **`output_band` 那個模組真的走了** —— 留著一個沒有呼叫者的畫圖模組，
   下一個人會照著它再畫一個框。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from d4t.core.pipeline.step import REGISTRY, SCALE_LOT  # noqa: E402
from d4t.ui import canvas as canvas_mod  # noqa: E402
from d4t.ui import studio as studio_mod, theme as theme_mod  # noqa: E402

from tests.conftest import first_source  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        yield win
    finally:
        win.close()


def canvas(window):
    return window.pipeline


def add_output(window, key="output_report"):
    return window.add_card_after(first_source(window), key)


def item(window, node_id):
    return canvas(window)._items[node_id]


# --------------------------------------------------------------------------- #
# 1. 判準是卡片自己宣告的 scale
# --------------------------------------------------------------------------- #
def test_the_strip_marks_exactly_the_cards_that_run_once_per_lot(window):
    nid = add_output(window)
    lot = {i.node_id for i in canvas(window).lot_nodes()}
    assert nid in lot

    # 逐張對 registry —— **不是一份寫死的清單**。加一張新的整批卡不必動這裡。
    for other_id, it in canvas(window)._items.items():
        cls = REGISTRY.get(str(it.info.get("step_key") or ""))
        want = cls is not None and cls.scale == SCALE_LOT
        assert it.is_lot() is want, other_id


def test_a_per_defect_card_has_no_strip(window):
    add_output(window)
    src = item(window, first_source(window))
    assert src.is_lot() is False
    assert src.height() == src.body_height(), "逐顆的卡不該長出腳帶"


def test_the_strip_is_real_height_not_something_drawn_outside(window):
    """腳帶佔的是**真的高度**。

    畫在卡片外面的東西正是上一版那個框 —— 而它會跟下一列的卡片打架
    （`output_band` 的 PAD 那段記過一次：上下各留 26 的話相鄰兩列疊了 42px）。
    """
    nid = add_output(window)
    it = item(window, nid)
    assert it.height() == it.body_height() + canvas_mod._LOT_STRIP
    assert it.boundingRect().height() >= it.height()


# --------------------------------------------------------------------------- #
# 2. 用字，不只用顏色
# --------------------------------------------------------------------------- #
def test_the_strip_says_when_these_cards_run_in_words(window):
    """一條色帶對不會寫 code 的使用者不是一句話（推廣鐵則）。"""
    text = canvas_mod.LOT_STRIP_TEXT
    assert text.strip(), "腳帶沒有字，只剩顏色"
    assert "lot" in text.lower(), text


def test_the_words_live_in_one_place(window):
    """那句話只有一個家 —— studio 不准抄第二份。"""
    src = (REPO / "d4t" / "ui" / "studio.py").read_text(encoding="utf-8")
    assert canvas_mod.LOT_STRIP_TEXT not in src


# --------------------------------------------------------------------------- #
# 3. 埠均分的是本體
# --------------------------------------------------------------------------- #
def test_ports_are_spread_over_the_body_not_the_strip(window):
    """有腳帶的卡，埠不該整體往下偏。

    ⚠ 目前 Output 段沒有埠，所以這件事**看不出來** —— 這一條就是為了那個
    看不出來才寫的：下一張宣告 `SCALE_LOT` 又有埠的卡不該去發現它。
    所以這裡拿一張真的有埠的卡，把它假裝成整批卡來量。
    """
    src = item(window, first_source(window))
    src.info["scale"] = "lot"
    try:
        assert src.is_lot() is True
        anchors = src.out_anchors_local()
        if anchors:
            assert max(a.y() for a in anchors) <= src.body_height() + 0.01
    finally:
        src.info["scale"] = "defect"


# --------------------------------------------------------------------------- #
# 4. 那個框真的走了
# --------------------------------------------------------------------------- #
def test_the_band_module_is_gone_for_good():
    """**翻面來的一條。** 以前它守的是「那個框住在自己的模組裡」。

    留著一個沒有呼叫者的畫圖模組，下一個人會照著它再畫一個框 ——
    而框那個編碼正是這一輪拿掉的東西。
    """
    assert not (REPO / "d4t" / "ui" / "output_band.py").exists()
    canvas_src = (REPO / "d4t" / "ui" / "canvas.py").read_text(encoding="utf-8")
    assert "import output_band" not in canvas_src
    assert "build_band" not in canvas_src


def test_nothing_is_rebuilt_on_every_drag_frame(window):
    """殘影的**機制**：那個框從卡片位置算出來，所以拖曳時每 frame 重建一次。

    腳帶跟著卡片走（它就畫在卡片上），所以 `refresh_edges` 不必為它做任何事。
    這一條守的是那個結論：拖曳的路徑上不可以再出現「重建某個獨立圖元」。
    """
    src = (REPO / "d4t" / "ui" / "canvas.py").read_text(encoding="utf-8")
    body = src.split("def refresh_edges", 1)[1].split("\n    def ", 1)[0]
    # ⚠ **只看會執行的那幾行。** 那個墓碑註解（「這裡以前還有一句…」）是刻意
    # 留的 —— 它記著殘影的機制，而下一個想在拖曳路徑上加東西的人要先讀到它。
    # 第一版沒有濾註解，於是這一條抓到的是自己的墓碑。
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "_rebuild_output_band" not in code
    assert "addItem" not in code, "拖曳的路徑上又有人在生圖元了"


def test_dragging_an_output_card_keeps_its_strip(window):
    """卡片拖走，腳帶跟著走 —— 因為它就是卡片的一部分。"""
    nid = add_output(window)
    it = item(window, nid)
    before = it.height()
    it.setPos(it.pos() + QPointF(140.0, 90.0))
    canvas(window).refresh_edges()
    assert it.is_lot() is True
    assert it.height() == before
