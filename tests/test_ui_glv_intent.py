# PR-2（2a）：GLV「我要量什麼」三選 —— preset 不是參數。
"""鎖四件事：套 preset 只動那三樣（roi/reference_region 的線 + reference /
across_boxes 兩格）；defect_box 的兩條虛線同一個 producer；**preset 存出的
JSON 跟手拉線手填格的逐位元組相同**（證明沒有新欄位、schema 沒動）；一次
Ctrl+Z 全還原；比不上顯示 custom 且偵測永不改 recipe。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from d4t.ui import theme as theme_mod  # noqa: E402
from d4t.ui.viewmodel import (  # noqa: E402
    GLV_INTENT_CUSTOM, GLV_INTENTS, RecipeModel,
)

sys.path.insert(0, str(REPO / "tests"))
from region_cards import add_region_step  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _model(qapp):
    """load → Region(Profile, roi_out=cells) → GLV，roi 接 `cells`。"""
    m = RecipeModel()
    load = m.add_step("load_patch")
    roi = add_region_step(m, "roi_cross")
    m.set_param(roi, "roi_out", "cells")
    glv = m.add_step("glv_stats")
    m.add_edge(load, roi, "test", "source")
    m.add_edge(load, glv, "test", "source")
    m.add_edge(roi, glv, "cells", "roi")
    return m, roi, glv


def _snapshot(m):
    return (json.dumps({nid: dict(n.params) for nid, n in m.nodes.items()},
                       sort_keys=True, default=str),
            [(e.src, e.dst, e.src_out, e.dst_in) for e in m.edges])


def test_each_preset_touches_only_the_three_things(qapp):
    for intent in ("defect_box", "oddest_box", "region_stats"):
        m, roi, glv = _model(qapp)
        params_before, edges_before = _snapshot(m)
        assert m.apply_glv_intent(glv, intent) is True
        params_after, edges_after = _snapshot(m)
        # 參數 diff：只有 glv 的 roi/reference/across_boxes/reference_region。
        before = json.loads(params_before)
        after = json.loads(params_after)
        for nid in before:
            diff = {k for k in set(before[nid]) | set(after[nid])
                    if before[nid].get(k) != after[nid].get(k)}
            if nid != glv:
                assert not diff, "preset 動到別張卡：%s %s" % (nid, diff)
            else:
                # F67：`reference` 那一格沒有了 —— preset 動的是**線**加
                # 一格 `across_boxes`（`reference_region` 是線水合出來的值）。
                allowed = {"roi", "across_boxes", "reference_region"}
                assert diff <= allowed, "preset 動了那幾格之外的：%s" % diff
        # 線 diff：只有進 glv 的 roi / reference_region 兩格。
        changed = set(edges_before) ^ set(edges_after)
        assert all(dst == glv and dst_in in ("roi", "reference_region")
                   for _s, dst, _o, dst_in in changed), changed


def test_defect_box_wires_both_dashed_lines_to_the_same_producer(qapp):
    m, roi, glv = _model(qapp)
    assert m.apply_glv_intent(glv, "defect_box") is True
    got = {e.dst_in: (e.src, e.src_out) for e in m.edges
           if e.dst == glv and e.dst_in in ("roi", "reference_region")}
    assert got["roi"] == (roi, "cells_center")
    assert got["reference_region"] == (roi, "cells_others")
    # F67：**那條線就是「在比」**（以前還要 `reference` 那一格一起說一次）。
    assert "reference" not in m.nodes[glv].params
    assert m.nodes[glv].params["across_boxes"] == "pooled"
    assert m.glv_intent(glv) == "defect_box", "套完要偵測得回自己"


def test_preset_json_is_byte_identical_to_a_hand_built_recipe(qapp):
    """**沒有新欄位**的可執行證明：preset 存出的 JSON 跟手拉線、手填格的
    那一份逐位元組相同（recipe schema 不動、不用遷移）。"""
    m, roi, glv = _model(qapp)
    m.apply_glv_intent(glv, "defect_box")
    by_preset = json.dumps(m.to_recipe().to_json_dict(), sort_keys=True,
                           ensure_ascii=False, indent=1)

    h, hroi, hglv = _model(qapp)
    # 手工：retarget roi 線、加參照線、填兩格 —— preset 做的那幾步逐一手做。
    h.remove_edge(hroi, hglv, "cells", "roi")
    h.add_edge(hroi, hglv, "cells_center", "roi")
    h.add_edge(hroi, hglv, "cells_others", "reference_region")
    h.set_param(hglv, "across_boxes", "pooled")
    by_hand = json.dumps(h.to_recipe().to_json_dict(), sort_keys=True,
                         ensure_ascii=False, indent=1)
    assert by_preset == by_hand


def test_all_presets_round_trip_through_detection(qapp):
    for intent in ("defect_box", "oddest_box", "region_stats"):
        m, _roi, glv = _model(qapp)
        assert m.apply_glv_intent(glv, intent) is True
        assert m.glv_intent(glv) == intent


def test_no_match_shows_custom_and_detection_never_mutates(qapp):
    m, roi, glv = _model(qapp)
    # 三選都對不上：接了 `_center` 卻**沒有**那條參照線（F67 之後「跟誰比」
    # 只有線這一種說法，所以對不上 preset 的方式也只剩動線）。
    m.remove_edge(roi, glv, "cells", "roi")
    m.add_edge(roi, glv, "cells_center", "roi")
    before = _snapshot(m)
    assert m.glv_intent(glv) == GLV_INTENT_CUSTOM
    assert _snapshot(m) == before, "偵測永不改 recipe"


def test_one_undo_reverts_a_whole_preset(qapp):
    m, _roi, glv = _model(qapp)
    before = _snapshot(m)
    m.apply_glv_intent(glv, "defect_box")
    assert _snapshot(m) != before
    m.undo()
    assert _snapshot(m) == before, \
        "preset 是好幾個動作 —— 一次 Ctrl+Z 要全回去（compound）"


def test_without_a_roi_wire_the_preset_refuses(qapp):
    m = RecipeModel()
    load = m.add_step("load_patch")
    glv = m.add_step("glv_stats")
    m.add_edge(load, glv, "test", "source")
    before = _snapshot(m)
    assert m.apply_glv_intent(glv, "oddest_box") is False
    assert _snapshot(m) == before
    assert m.glv_intent(glv) == GLV_INTENT_CUSTOM


# --------------------------------------------------------------------------- #
# F68 第三輪：這一排也是膠囊（使用者：「最上方的 What do I want to measure
# 也是，而且我覺得他有一點太口語」）
# --------------------------------------------------------------------------- #
def test_the_preset_row_is_the_same_pill_as_everything_else(qapp):
    """一排選項在這張卡上只有一種長相 —— 兩種的話使用者要學兩次。"""
    from d4t.ui import widgets as widgets_mod

    form = widgets_mod.ParamForm()
    form.set_intent_row("What to measure", GLV_INTENTS, "oddest_box")
    chips = list(form.intent_buttons().values())
    assert chips and all(isinstance(c, widgets_mod._ChipBase) for c in chips)
    assert all(c.icon in widgets_mod.GLYPH_ICONS for c in chips)


def test_a_preset_wears_the_picture_of_the_row_it_sets(qapp):
    """三顆的圖**就是底下那幾格的圖**，不是另外畫的三張。

    這一排是那幾格的捷徑，圖一樣才看得出「按這一顆＝把那幾格設成這樣」。
    兩張表因此要對得起來 —— 各畫各的那天，同一件事在同一張卡上有兩張圖。
    """
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step
    from d4t.core.steps.glv_stats import EACH_BOX, POOLED

    icons = {row[0]: row[3] for row in GLV_INTENTS}
    spec = {p.name: p for p in get_step("glv_stats").params}["across_boxes"]
    by_value = dict(zip(spec.choices, spec.icons))
    assert icons["oddest_box"] == by_value[EACH_BOX]
    assert icons["region_stats"] == by_value[POOLED]


def test_the_words_are_not_chatty(qapp):
    """使用者：「我覺得他有一點太口語。」

    帶冠詞的口語短句（「The most unusual box」）跟底下每一格的膠囊
    （`Pooled` / `Each box` / `Brightest`）不是同一種語氣，而它們就排在
    上下兩公分內。
    """
    labels = {row[0]: row[1] for row in GLV_INTENTS}
    assert labels == {"defect_box": "Defect box",
                      "oddest_box": "Odd box out",
                      "region_stats": "Whole region"}
    for text in labels.values():
        assert not text.lower().startswith(("the ", "a ", "my ")), text


def test_pressing_the_one_already_picked_does_not_unpick_it(qapp):
    """preset 不是開關：再按一次要**回到哪個狀態**沒有答案。"""
    from d4t.ui.widgets import ParamForm

    form = ParamForm()
    seen = []
    form.intent_chosen.connect(seen.append)
    form.set_intent_row("What to measure", GLV_INTENTS, "oddest_box")
    form.intent_buttons()["oddest_box"].click()
    assert seen == ["oddest_box"], "照樣要發訊號（套一次是冪等的）"
    assert form.intent_buttons()["oddest_box"].is_checked(), \
        "畫面要停在真實狀態上，不是停在使用者按下去的那一顆"


def test_a_greyed_out_preset_does_nothing(qapp):
    """roi 那條線還沒接的時候整排灰掉 —— 而灰掉的東西按了不可以生效。

    Qt 只擋得住滑鼠事件；直接呼叫的路（鍵盤、測試）擋不到。
    """
    from d4t.ui.widgets import ParamForm

    form = ParamForm()
    seen = []
    form.intent_chosen.connect(seen.append)
    form.set_intent_row("What to measure", GLV_INTENTS, "defect_box",
                        note="wire a region in first", enabled=False)
    form.intent_buttons()["oddest_box"].click()
    assert seen == []


def test_rebuilding_the_row_leaves_no_ghosts(qapp):
    """**這一條是那個 bug 本身。**

    `deleteLater()` 要等事件圈的 DeferredDelete 那一趟，而在那之前舊的那幾顆
    還在畫面上、停在上一次版面給它們的位置。這一排有彈簧，面板一換寬度位置
    就變 —— 於是舊的疊在標題與新膠囊上（render 出來才看到）。
    """
    from d4t.ui import widgets as widgets_mod

    form = widgets_mod.ParamForm()
    form.resize(520, 300)
    form.set_intent_row("What to measure", GLV_INTENTS, "oddest_box")
    qapp.processEvents()
    form.resize(760, 300)
    form.set_intent_row("What to measure", GLV_INTENTS, "defect_box")
    qapp.processEvents()
    alive = form._intent_row.findChildren(widgets_mod._ChipBase)
    assert len(alive) == len(GLV_INTENTS), \
        "上一批膠囊還掛在那一排上（%d 顆）" % len(alive)


def test_the_form_row_shows_the_three_choices(qapp):
    """表單那一排：三顆膠囊、當前的那顆勾著、custom 一顆都不勾。"""
    from d4t.ui.widgets import ParamForm

    form = ParamForm()
    form.set_intent_row("What to measure", GLV_INTENTS, "oddest_box")
    btns = form.intent_buttons()
    assert set(btns) == {row[0] for row in GLV_INTENTS}
    assert btns["oddest_box"].is_checked()
    assert not btns["defect_box"].is_checked()
    form.set_intent_row("What to measure", GLV_INTENTS,
                        GLV_INTENT_CUSTOM, note="custom")
    assert not any(b.is_checked() for b in form.intent_buttons().values())
    form.set_step(None, {}, [])
    assert form.has_intent_row() is False, "換卡要清掉 —— 別張卡不出現這排"
