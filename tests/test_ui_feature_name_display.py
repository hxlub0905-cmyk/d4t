# d4t 測試 — F37 A4：特徵名的上下標與顏色（2026-08-26）.
"""使用者 2026-08-26：「值可否用上下標　更清楚　配合顏色」。

一個特徵名在畫面上拆成三個角色，而**每一個都對應名字裡真的存在的一段**：

    glv_median  ᵉᵖⁱ  ₜₑₛₜ  hot
    ─────────   ───  ────  ───
    主體        上標  下標  使用者自己取的名字

⚠ **顏色不是在這裡發明的**：`theme.region_hex(index)` 同時是影像上那個 ROI
框的顏色與畫布上區域埠的顏色 —— 三個地方同一個顏色，來源只有一份。
各自挑一份的話，"top,bot" 在一邊是 0/1、在另一邊是 1/0，而顏色指錯區域比
沒有顏色糟得多。
"""
from __future__ import annotations

import pytest

import d4t.core.steps  # noqa: F401
from d4t.core.pipeline.step import get_step

pytest.importorskip("PySide6")

from d4t.ui import theme                                    # noqa: E402
from d4t.ui.widgets import feature_html                     # noqa: E402


# --------------------------------------------------------------------------- #
# 1. 拆解由卡片給，而且跟宣告完全對得上
# --------------------------------------------------------------------------- #
def test_the_card_can_take_every_name_it_declares_back_apart():
    """`feature_parts` 是 `resolve_features` 的**反向**，兩者不准對不上。

    兩支走同一個雙層迴圈、同一組 `*_prefix` 呼叫。各寫一份的話，「這個名字
    有沒有區域那一段」會有兩個答案，而畫面用的是錯的那一個。

    ⚠ 把 `MultiSourceStep.feature_parts` 的 `regions` 換成 `["x"]` 之類的
    寫死值，這支會紅。
    """
    card = get_step("glv_stats")
    p = dict(source="test,diff", roi="epi,mg", metrics="glv_median,glv_mad",
             reference="none", across_boxes="pooled", output_prefix="hot")
    assert set(card.feature_parts(p)) == set(card.resolve_features(p))


def test_a_single_region_leaves_the_name_alone():
    """只接一條流、一個區域時名字裡**沒有**前綴，所以也不該畫上下標。

    畫面要照著名字說實話：顯示的東西跟打進分數表達式的東西是同一串。
    """
    card = get_step("glv_stats")
    p = dict(source="test", roi="epi", metrics="glv_median",
             reference="none", across_boxes="pooled", output_prefix="")
    parts = card.feature_parts(p)
    assert parts["glv_median"] == {"base": "glv_median"}
    assert feature_html("glv_median", parts["glv_median"]) == "glv_median"


def test_the_region_index_follows_the_order_the_user_wired_them():
    """顏色照**接線的順序**挑，不是照名字排序。

    `MultiSourceStep.CURRENT_REGION_INDEX` 用同一個序去挑 ROI 框的顏色 ——
    兩邊各自從自己那邊數的話，"top,bot" 在一邊是 0/1、在另一邊是 1/0。
    """
    card = get_step("glv_stats")
    p = dict(source="test", roi="top,bot", metrics="glv_median",
             reference="none", across_boxes="pooled", output_prefix="")
    parts = card.feature_parts(p)
    assert parts["top_glv_median"]["region_index"] == 0
    assert parts["bot_glv_median"]["region_index"] == 1


# --------------------------------------------------------------------------- #
# 2. 畫出來的樣子
# --------------------------------------------------------------------------- #
def test_the_region_is_a_coloured_superscript_and_the_stream_a_subscript():
    html = feature_html("test_epi_glv_median",
                        {"base": "glv_median", "stream": "test",
                         "region": "epi", "region_index": 0})
    assert "<sup" in html and ">epi<" in html
    assert "<sub" in html and ">test<" in html
    assert html.startswith("glv_median")


def test_the_colour_comes_from_the_one_place_it_lives():
    """上標的顏色**逐字**是 `theme.region_hex(index)`。

    這支測試存在的理由不是「顏色對不對」，是「有沒有第二份」—— 抄一份出來
    的那一份會漂，而漂掉的症狀是特徵表跟影像上的框對不起來。
    """
    for i in (0, 1, 5, 9):
        html = feature_html("x", {"base": "b", "region": "r",
                                  "region_index": i})
        assert theme.region_hex(i) in html


def test_a_name_it_cannot_take_apart_is_shown_as_it_is():
    """拆不出來就照原樣顯示整串 —— 少一點資訊，不會是錯的資訊。"""
    assert feature_html("epi_boxes", None) == "epi_boxes"
    assert feature_html("epi_boxes", {}) == "epi_boxes"


def test_the_name_is_escaped_not_injected():
    """特徵名是使用者取的字（`output_prefix`）—— 它會走進 HTML。"""
    html = feature_html("x", {"base": "a<i>c", "region": "r&d",
                              "region_index": 0})
    # 使用者打的 `<i>` 要變成字，不是變成標籤。（不要用 `<b>` 當樣本 ——
    # 上標本身就用 `<b>` 加粗，那會讓斷言誤判成「沒轉義」。）
    assert "<i>" not in html and "&lt;i&gt;" in html
    assert "r&amp;d" in html and "r&d" not in html.replace("r&amp;d", "")


# --------------------------------------------------------------------------- #
# 3. 表格：長相變了，而「打得進表達式的那一串」沒變
# --------------------------------------------------------------------------- #
def test_the_plain_name_is_still_what_the_panel_reports(qapp=None):
    """HTML 只是長相 —— **取用口回的仍然是那一串字**。

    複製、搜尋、以及使用者照著打進分數表達式讀到的都是它。
    （2026-09-02 從 `FeatureTable` 搬到 `FeaturePanel`：那張表刪掉了，而它
    守的這件事沒有變 —— 換的只是誰在畫。）
    """
    from PySide6.QtWidgets import QApplication

    from d4t.core.pipeline.step import FeatureSpec
    from d4t.ui.feature_panel import FeaturePanel, panel_model

    app = QApplication.instance() or QApplication([])
    spec = FeatureSpec(name="test_epi_glv_median", card="glv_stats",
                       base="glv_median", stream="test", region="epi",
                       region_index=0, family="glv")
    bound = type("B", (), {"node_id": "glv", "label": "GLV", "spec": spec})()
    model = panel_model({"test_epi_glv_median": 12.5}, [bound])
    row = model[0]["flat"][0]
    assert row["name"] == "test_epi_glv_median"       # 打得進表達式的那一串
    assert "<sup" in row["html"]                       # 而長相是拆開的

    panel = FeaturePanel()
    try:
        panel.set_model(model)
        assert panel.feature_names() == ["test_epi_glv_median"]
        assert panel.value_text("test_epi_glv_median") == "12.5"
    finally:
        panel.deleteLater()
    del app
