# F11 Enhance-4：三件「畫布/畫面在說謊」的回報。
"""三個都是使用者實際操作時看到的，而三個都是同一條規矩的破口：

> **資料從哪來由線決定，而畫布上每一條線都是使用者拉的**（F9，CLAUDE.md 鐵則 10）

1. **開窗預先放一張 Load 卡** = 替使用者決定了他還沒決定的事（Input-4 之後有兩張
   載入卡，而猜錯的那一半在畫布上看起來完全正常）。
2. **入口卡左邊畫著一顆輸入埠** = 一顆接不上任何東西的埠。
3. **沒接線的卡選起來卻有畫面** = 那張圖是入口卡的輸出，看起來像這張卡的結果。

第四件是同一輪修的**可讀性**：節點第三行被切在字中間（`refer…`），而被切掉的那
一項使用者根本不知道它存在。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source, wire_up  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import canvas as canvas_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1400, 900)
    yield win
    win.close()


@pytest.fixture
def lot(tmp_path):
    from make_sample import generate
    return generate(str(tmp_path / "lotT"), n=4, seed=91)


# --------------------------------------------------------------------------- #
# 1. 開窗是空白畫布，載入資料才補上「這種資料該用的那一張」
# --------------------------------------------------------------------------- #
def test_the_canvas_starts_empty_and_offers_both_load_cards(window):
    assert window.model.node_order == []
    assert window.selected_node is None
    for key in ("load_patch", "load_single"):
        assert window.library.entry(key) is not None, key


def test_loading_patch_data_brings_in_load_images(window, lot):
    window.load_dataset_path(lot["klarf"], sync=True)
    assert [window.model.nodes[n].step for n in window.model.node_order] \
        == ["load_patch"]
    assert window.selected_node == window.model.node_order[0]
    # 補進來的那張卡不算「使用者做過的一步」
    assert window.model.dirty is False and window.model.can_undo() is False


def test_loading_single_image_data_brings_in_load_one_image(window, tmp_path):
    """一顆一張的資料要補的是**另一張**卡 —— 而那正是預先放一張會猜錯的一半。"""
    from make_sample_rsem import generate

    out = generate(str(tmp_path / "lotR"), n=4, seed=92)
    window.load_dataset_path(out["klarf"], sync=True)
    steps = [window.model.nodes[n].step for n in window.model.node_order]
    assert steps == ["load_single"], steps


def test_a_pipeline_the_user_built_is_never_touched(window, lot):
    """使用者已經放了東西 → 這一段一個字都不准動它。"""
    window._on_add_requested("load_single")     # 他自己挑的（就算跟資料不合）
    before = list(window.model.node_order)
    window.load_dataset_path(lot["klarf"], sync=True)
    assert window.model.node_order == before


# --------------------------------------------------------------------------- #
# 2. 入口卡沒有輸入埠
# --------------------------------------------------------------------------- #
def test_a_source_card_has_no_input_port(window, lot):
    """使用者原話：「因為她是最初始的 source，card 最前方不能有連接的白色原點。」"""
    window.load_dataset_path(lot["klarf"], sync=True)
    card = window.pipeline.card(window.model.node_order[0])
    assert card.in_specs() == []
    assert card.in_anchors_local() == [], "入口卡畫了一顆接不上任何東西的埠"
    # 連拖過去的動作都不該成立
    assert card.in_port_at(card.in_port_local()) is None
    assert card.in_param_at(card.in_port_local()) == ""


def test_every_other_card_still_has_its_ports(window, lot):
    """只有「沒有輸入」的卡不畫 —— 其餘每一張照舊（一個輸入參數一顆埠，F10）。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    sub = window.add_card_after(src, "subtract")
    card = window.pipeline.card(sub)
    assert len(card.in_anchors_local()) == 2
    for anchor in card.in_anchors_local():
        assert card.in_port_at(anchor) is not None


def test_the_geometry_still_answers_for_edge_drawing(window, lot):
    """`in_port()` 是給連線畫圖用的座標，**不是**畫面上的埠 —— 它不准 IndexError
    （拖線經過入口卡時每一格都會問它）。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    card = window.pipeline.card(window.model.node_order[0])
    p = card.in_port(0)
    assert p == card.in_port(5)          # 越界的索引也要答得出同一個點
    assert card.shape().contains(card.boundingRect().center())


# --------------------------------------------------------------------------- #
# 3. 沒接線的卡不准有畫面
# --------------------------------------------------------------------------- #
def test_selecting_an_unconnected_card_shows_nothing(window, lot):
    """**這一支就是回報本身。**

    以前：預覽是跑整條 route（`upto_node` 只是提早停），而入口卡不需要線就跑得
    起來 —— 它把 test / ref 寫進了 master context。Denoise 沒有輸入所以失敗，
    但失敗的策略是「把已經算出來的影像留在畫面上」，於是畫面上出現入口卡的輸出，
    看起來像 Denoise 的結果。
    """
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    d = window.add_card_after(src, "denoise")       # 故意不接線
    window.select_node(d)
    assert window.refresh_preview(sync=True) is True

    assert window._preview_images == {}
    assert window.image_view.has_image() is False
    # 而且要講得出**下一步怎麼做**。引擎攔這件事的時候已經講了一句可以照做的話
    # （`no input connected … Drag a line …`），所以這裡用它就好 ——
    # lint 那一句是「連 trace 都沒有」（上游斷掉）時的退路。
    said = window.status_text()
    assert "Drag a line" in said and "'streams' is empty" in said


def test_connecting_it_makes_the_image_appear(window, lot):
    """接上線就有 —— 這一半也要測，不然「永遠不顯示」也會過。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    d = window.add_card_after(src, "denoise")
    window._on_edge_added(src, d, "test")
    window.select_node(d)
    assert window.refresh_preview(sync=True) is True
    assert "test" in window._preview_images
    assert window.image_view.has_image() is True


def test_a_card_whose_upstream_is_unconnected_shows_nothing_either(window, lot):
    """鏈中間斷掉也一樣：這張卡自己接好了，但它的上游沒有 —— 那它同樣沒跑，
    而畫面上一樣會出現入口卡的圖。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    a = window.add_card_after(src, "denoise")       # 上游沒接
    b = window.add_card_after(a, "tone")
    window._on_edge_added(a, b, "test")
    window.select_node(b)
    assert window.refresh_preview(sync=True) is True
    assert window._preview_images == {}


def test_a_card_that_ran_and_failed_says_the_error_itself(window, lot):
    """**兩種「沒有東西可看」要講不同的話**，因為下一步不一樣。

    這裡的 Denoise 接好了線、跑起來了，但 ksize 是偶數 → 卡片自己 raise
    StepError。畫面上照樣不留東西（它沒有輸出），但狀態列要講**那個錯誤**
    （它自己就帶著怎麼修），不是那句「還沒接線」。
    """
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    d = wire_up(window.model, window.add_card_after(src, "denoise"))
    window._on_edge_added(src, d, "test")
    window.model.set_param(d, "ksize", 4)           # 偶數核 = 卡片自己擋下來
    window.select_node(d)
    assert window.refresh_preview(sync=True) is True
    assert window.image_view.has_image() is False
    assert "ksize must be odd" in window.status_text()
    assert "drag a line" not in window.status_text()


def test_a_failure_further_down_keeps_this_card_s_image(window, lot):
    """界線的另一半：**這張卡跑過了**，是後面某張卡失敗 —— 那時候畫面上的影像
    有意義（診斷比清空有用），所以留著。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    d = wire_up(window.model, window.add_card_after(src, "denoise"))
    window._on_edge_added(src, d, "test")
    window.select_node(d)
    assert window.refresh_preview(sync=True) is True
    assert window.image_view.has_image() is True, "這張卡自己是好的"


# --------------------------------------------------------------------------- #
# 4. 節點第三行不准被切在字中間
# --------------------------------------------------------------------------- #
def test_an_empty_value_is_not_printed_at_all(window, lot):
    """剛加進來的卡每一格輸入都是空的（F10），而空字串跟卡片預設值不相等 ——
    於是節點上長出 `streams=`，一個沒有任何資訊的欄位，還把有用的那項擠掉。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    n = window.add_card_after(src, "normalize")
    window.model.set_param(n, "p_low", 1.2)
    window._refresh_pipeline()
    parts = window.pipeline.card(n).summary_parts()
    assert "p_low=1.2" in parts
    assert not [p for p in parts if p.endswith("=")], parts


def test_what_does_not_fit_becomes_a_count(window, lot):
    """使用者回報：「normalize 的節點文字會被吃掉」。

    `+1` 是一個看得懂的訊息（點開卡片就看得到那一項），`refer…` 不是。
    """
    from PySide6.QtGui import QFont, QFontMetricsF

    parts = ["method=match", "p_low=1.2", "target_spread=64", "tiles=12"]
    text = canvas_mod._fit_parts(QFontMetricsF(QFont()), 90.0, parts)
    assert text.endswith("+2") or text.endswith("+3"), text
    assert "…" not in text, "放不下的那一項要收成數字，不是切在字中間"
    # 寬到全部塞得下的時候就不該有 +N
    wide = canvas_mod._fit_parts(QFontMetricsF(QFont()), 4000.0, parts)
    assert "+" not in wide and wide.count("·") == 3


def test_a_card_with_nothing_connected_says_so_in_words(window, lot):
    """副標以前印的是 step_key（`normalize`）—— 使用者剛在上面一行讀過同一個字。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    src = window.model.node_order[0]
    n = window.add_card_after(src, "normalize")
    window._refresh_pipeline()
    assert window.pipeline.card(n).subtitle() == "(not connected)"
    window._on_edge_added(src, n, "test")
    window._refresh_pipeline()
    assert window.pipeline.card(n).subtitle() == "test → test"
