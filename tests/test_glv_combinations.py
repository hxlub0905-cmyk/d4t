# F67 續（2026-09-01）：GLV 卡「量哪裡 × 怎麼量 × 跟誰比」的**整張表**。
"""使用者要的那張排列組合表，寫成一支跑得動的測試。

為什麼是測試而不是一份文件：這張表的每一格都是**算出來的**（preset 對得上
哪一顆、有沒有在比、健檢講不講話、那排 note 說什麼），而文件裡的表只要有人
改了偵測條件就會安靜地過期 —— 這個 repo 為「兩份說法漂掉」付過好幾次錢
（`CLAUDE.md` §0）。這裡列的是**四個軸的完整乘積**，不是挑幾個例子。

四個軸（`source` 那一軸不在裡面：多接一條流是**乘上去**的，它只改前綴，
不改這張表的任何一格）：

===========================  ===============================================
``roi``（量哪裡）            －／``epi``／``epi_center``／``epi_others``／
                             ``epi,mg``
``across_boxes``（怎麼量）   ``pooled``／``each box``
``reference_region``         －／``epi_others``／``mg``／``epi``
``reference_source``         －／``ref``
===========================  ===============================================
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication          # noqa: E402

from d4t.core.pipeline import get_step              # noqa: E402
from d4t.ui.viewmodel import (                      # noqa: E402
    GLV_INTENT_CUSTOM, GLV_INTENTS, RecipeModel,
)

ROI = ("", "epi", "epi_center", "epi_others", "epi,mg")
BOXES = ("pooled", "each box")
REF_REGION = ("", "epi_others", "mg", "epi")
REF_SOURCE = ("", "ref")

#: 四個軸的完整乘積。
GRID = list(itertools.product(ROI, BOXES, REF_REGION, REF_SOURCE))

#: **對得上 preset 的那幾格**（其餘一律 custom）。
#: ``reference_source`` 不在鍵裡 —— 跟另一張圖比是**疊在**那三種形狀上的第二
#: 個問題，不是第四種形狀（見 `RecipeModel.glv_compares_across_images`）。
PRESET_ROWS = {
    ("epi_center", "pooled", "epi_others"): "defect_box",
    ("epi", "each box", ""): "oddest_box",
    ("epi", "pooled", ""): "region_stats",
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _card(m, roi, boxes, ref_region, ref_source):
    """load → Region（layout layers，吐 epi/mg 兩個家族）→ GLV。"""
    load = m.add_step("load_patch")
    region = m.add_step("roi_reference")
    m.set_param(region, "method", "layout layers")
    m.set_param(region, "layers", "1:epi, 2:mg")
    glv = m.add_step("glv_stats")
    m.add_edge(load, region, "test", "source")
    m.add_edge(load, glv, "test", "source")
    for name in [x for x in roi.split(",") if x]:
        m.add_edge(region, glv, name, "roi")
    if ref_region:
        m.add_edge(region, glv, ref_region, "reference_region")
    if ref_source:
        m.set_param(glv, "reference_source", ref_source)
    m.set_param(glv, "across_boxes", boxes)
    return glv


@pytest.fixture(params=GRID, ids=["%s|%s|%s|%s" % tuple(g or "-" for g in row)
                                  for row in GRID])
def combo(request, qapp):
    roi, boxes, ref_region, ref_source = request.param
    m = RecipeModel()
    glv = _card(m, roi, boxes, ref_region, ref_source)
    return m, glv, request.param


# --------------------------------------------------------------------------- #
# 1. 每一格對得上哪一顆鈕
# --------------------------------------------------------------------------- #
def test_the_preset_of_every_combination_is_the_table(combo):
    m, glv, (roi, boxes, ref_region, ref_source) = combo
    want = PRESET_ROWS.get((roi, boxes, ref_region), GLV_INTENT_CUSTOM)
    assert m.glv_intent(glv) == want


def test_the_table_really_covers_all_three_presets():
    """反向：表上少了一顆鈕的話，上面那支會全綠而它什麼都沒證明。"""
    assert set(PRESET_ROWS.values()) == {row[0] for row in GLV_INTENTS}


# --------------------------------------------------------------------------- #
# 2. 有沒有在比 —— 只由那兩顆埠決定，而且宣告要跟著
# --------------------------------------------------------------------------- #
def test_comparing_happens_exactly_when_a_reference_port_is_wired(combo):
    """真值表的可執行版：**接了線才有 `cmp_*`，沒接就一個都沒有**。

    這一條同時擋住兩種安靜的錯：宣告說會吐而實際不吐（下游指到一個永遠不存在
    的特徵），以及反過來（一份「只要絕對值」的 recipe 悄悄多出一族數字）。
    """
    m, glv, (_roi, _boxes, ref_region, ref_source) = combo
    params = m.nodes[glv].params
    names = get_step("glv_stats").resolve_features(params)
    got = [n for n in names if n.startswith("cmp_") or "_cmp_" in n]
    assert bool(got) == bool(ref_region or ref_source)


def test_the_reference_label_names_both_halves(combo):
    """參照那一塊叫什麼 —— 區域、流、或者兩個都講（不比的時候是空字串）。"""
    m, glv, (roi, _boxes, ref_region, ref_source) = combo
    label = get_step("glv_stats").reference_label(m.nodes[glv].params)
    if not (ref_region or ref_source):
        assert label == ""
    elif ref_region and ref_source:
        assert label == "%s @ %s" % (ref_region, ref_source)
    elif ref_region:
        assert label == ref_region
    elif "," in roi:
        # 每一塊各自跟自己在另一張圖上的那一塊 —— 逐一列出來會讀成一個怪名字
        assert label == "the same areas @ %s" % ref_source
    else:
        assert label == "%s @ %s" % (roi or "the image", ref_source)


# --------------------------------------------------------------------------- #
# 3. 鈕 ＋ 那句話 = 這張卡真的在做的事
# --------------------------------------------------------------------------- #
def test_the_sentence_says_what_is_wired(combo):
    m, glv, (roi, boxes, ref_region, ref_source) = combo
    words = m.glv_wiring_words(glv)
    assert words.startswith("measuring %s" % (roi.replace(",", " and ")
                                              if roi else "the image"))
    assert ("box by box" in words) == (boxes == "each box")
    label = get_step("glv_stats").reference_label(m.nodes[glv].params)
    assert ("compared against %s" % label in words) == bool(label)


def test_the_note_appears_exactly_when_the_buttons_are_not_the_whole_truth(combo):
    """note 什麼時候該出現：**對不上**（custom），或者**對得上但漏講一件事**
    （接了參照流 —— 三顆鈕不覆蓋那一軸）。其餘時候畫面上不該多一行字 ——
    一行永遠都在的字沒有人會讀。"""
    m, glv, (roi, _boxes, _ref_region, ref_source) = combo
    custom = m.glv_intent(glv) == GLV_INTENT_CUSTOM
    across = m.glv_compares_across_images(glv)
    assert across == bool(ref_source)

    note = m.glv_intent_note(glv)
    if not roi:
        assert note == "Wire a Region card into “Region” first."
    elif custom:
        assert note == "custom - %s." % m.glv_wiring_words(glv)
    elif across:
        assert note == "%s." % m.glv_wiring_words(glv)
    else:
        assert note == "", "三顆鈕已經說完了，不必再多一行"


# --------------------------------------------------------------------------- #
# 4. 健檢：哪幾格會講話（**每一句都要有人講得出理由**）
# --------------------------------------------------------------------------- #
def test_the_lints_of_every_combination_are_the_table(combo):
    """**擋跑的那一支**（error）只有兩條，而且只有這兩條：

    * each box 卻沒接區域 —— 整張圖只有一格，那個設定沒有作用
    * 量的那一塊跟參照那一塊是同一塊、同一條流 —— 每個數字恆為 0

    兩條都是「跑起來每一顆都會出事或什麼都沒說」。**提醒**那一條在下面
    那支測試（warning，不擋跑）—— 兩支分開才擋得住「用一條 lint 否決
    使用者的意思」。
    """
    m, glv, (roi, boxes, ref_region, ref_source) = combo
    says = get_step("glv_stats").configuration_issues(m.nodes[glv].params)
    mine = [r for r in roi.split(",") if r]

    want = []
    if boxes == "each box" and not mine:
        want.append("does nothing")
    if not ref_source and ref_region and ref_region in mine:
        want.append("zero no matter what")

    assert len(says) == len(want), says
    for said, fragment in zip(says, want):
        assert fragment in said


def test_measuring_several_regions_against_one_others_is_a_hint_not_a_block(combo):
    """**提醒，不是路障**（F67 當天訂正）。

    「這兩塊都跟 epi_others 比」是合法的、有時候正是要的設定 —— 它一開始被
    寫進 `configuration_issues`（error），而那一支會擋住整批跑。同名不同義
    的東西不准安靜，但也不該變成一道路障。
    """
    m, glv, (roi, _boxes, ref_region, _ref_source) = combo
    mine = [r for r in roi.split(",") if r]
    card = get_step("glv_stats")
    hints = card.configuration_hints(m.nodes[glv].params)
    want = len(mine) > 1 and ref_region in ["%s_others" % r for r in mine]
    assert bool(hints) == want
    if want:
        assert "one GLV card per region" in hints[0]
        # 而且**不在**擋跑的那一支裡
        assert not [s for s in card.configuration_issues(m.nodes[glv].params)
                    if "one GLV card per region" in s]
        assert [i.level for i in m.validate()
                if i.code == "half-configured"] == ["warning"]


def test_the_same_block_on_another_image_is_not_flagged(combo):
    """反面：`epi @ test` vs `epi @ ref` 是**正當的**（真值表第三格）——
    「同一塊比自己」那條 lint 不可以連它一起擋掉。"""
    m, glv, (roi, _boxes, ref_region, ref_source) = combo
    if not (ref_source and ref_region and ref_region == roi):
        pytest.skip("這一格不是那一種")
    says = get_step("glv_stats").configuration_issues(m.nodes[glv].params)
    assert not [s for s in says if "zero no matter what" in s]
