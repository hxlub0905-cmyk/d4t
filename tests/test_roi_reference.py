# 參照區域的 ``repeating cells`` 那一支（F29，2026-08-25）。
"""使用者：「golden cell 跟 GDS 同樣重要而且他們要能在同張 card 裡
（都是接區域 ROI 卡）」。

這一份問四件事：

1. **切得對** —— 週期量得準、格子數對得上手算的。
2. **量不到就停下來** —— 純雜訊要 `StepError`，不可以吐一格猜出來的晶格。
   一個編出來的網格照樣讓每一顆 defect 吐得出很正常的灰階值，而 CSV 上沒有
   任何線索（上一次 rsem route 悄悄變成 12/24 就是這個形狀）。
3. **條紋不是晶格** —— 只有一軸有週期的時候，另一軸取滿整張圖。硬給一個位置
   等於憑空捏造資訊。
4. **它跟 GDS 那一支是同一張卡** —— 共用 `pick` / `drop_edge` /
   `output_prefix` / `max_boxes`，而且舊 recipe 遷得過來。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.recipe import Recipe  # noqa: E402
from d4t.core.pipeline.step import StepError  # noqa: E402
from d4t.core.steps.roi_reference import (  # noqa: E402
    METHOD_GDS, METHOD_PROFILE, METHOD_TEMPLATE,
)

CARD = "roi_reference"
METHODS_ALL = (METHOD_PROFILE, METHOD_TEMPLATE, METHOD_GDS)





def stripes(size=192, period=16, width=8, bg=40.0, fg=200.0):
    img = np.full((size, size), bg, np.float32)
    for x in range(0, size, period):
        img[:, x:x + width] = fg
    return img





# --------------------------------------------------------------------------- #
# 4. 跟 GDS 那一支是同一張卡
# --------------------------------------------------------------------------- #
def test_both_methods_share_the_same_wiring_params():
    card = get_step(CARD)
    names = {s.name: s for s in card.params}
    for shared in ("pick", "drop_edge", "edge_margin",
                   "output_prefix", "max_boxes", "method"):
        assert names[shared].show_when in (None,
                                           ("drop_edge", (True,))), shared
    assert "pick_source" not in names        # strongest 連線一起走了（F32）
    # 兩支各自的那幾格要**藏起來**，不是攤在那裡讓使用者猜。
    assert names["layers"].show_when == ("method", (METHOD_GDS,))
    assert names["source"].show_when[1] == (METHOD_PROFILE, METHOD_TEMPLATE)
    assert names["label_source"].show_when == ("method", (METHOD_GDS,))


def test_each_method_declares_only_the_stream_it_really_reads():
    """兩支吃的是兩種完全不同的東西 —— 一張照片，跟一張「像素值就是層號」的圖。"""
    card = get_step(CARD)
    cells = card.resolve_reads(card.validate_params(
        {"method": METHOD_PROFILE, "source": "test"}))
    gds = card.resolve_reads(card.validate_params(
        {"method": METHOD_GDS, "label_source": "layout_label"}))
    assert cells == ["test"]
    assert gds == ["layout_label"]


def test_the_pick_choices_are_centre_and_none_only():
    """``strongest`` 於 F32 刪掉（見 `_util.PICK_RULES` 的史料註解）。"""
    card = get_step(CARD)
    names = {s.name: s for s in card.params}
    assert list(names["pick"].choices) == ["centre", "none"]











# --------------------------------------------------------------------------- #
# 5. 舊 recipe 遷得過來（鐵則 9）
# --------------------------------------------------------------------------- #
def _old_recipe():
    return {
        "recipe_id": "t", "version": 2, "score": {"expr": "0"},
        "routes": {"ebi_patch": ["n0", "n1", "n2"]},
        "nodes": {
            "n0": {"step": "load_patch", "params": {}, "enabled": True},
            "n1": {"step": "load_sidecar", "params": {}, "enabled": True},
            "n2": {"step": "roi_from_mask", "enabled": True,
                   "params": {"source": "layout_label", "layers": "17=epi",
                              "max_boxes": 500}},
        },
    }


def test_an_old_gds_card_becomes_this_card_on_the_gds_method():
    r = Recipe.from_json_dict(_old_recipe())
    n = r.nodes["n2"]
    assert n.step == CARD
    assert n.params["method"] == METHOD_GDS
    # ``source`` 換名字：新卡有**兩個**來源參數，因為那是兩種不同的東西。
    assert n.params["label_source"] == "layout_label"
    assert "source" not in n.params
    assert n.params["layers"] == "17=epi" and n.params["max_boxes"] == 500


def test_the_migration_is_an_identity_the_second_time():
    """``to_json_dict → from_json_dict`` 是 `run_batch` 送 recipe 進 worker 的
    路（鐵則 9）—— 它一旦不是 identity，``workers=1`` 與 ``workers=2`` 會算出
    不同的分數。真的發生過。"""
    once = Recipe.from_json_dict(_old_recipe())
    twice = Recipe.from_json_dict(json.loads(json.dumps(once.to_json_dict())))
    a, b = once.nodes["n2"], twice.nodes["n2"]
    assert (a.step, a.params) == (b.step, b.params)


def test_a_new_recipe_is_left_alone():
    """判準是「**舊 step 名在不在**」，不是「新參數不在」（鐵則 9）。"""
    d = _old_recipe()
    d["nodes"]["n2"] = {"step": CARD, "enabled": True,
                        "params": {"method": METHOD_PROFILE, "source": "test",
                                   "roi_out": "epi"}}
    n = Recipe.from_json_dict(d).nodes["n2"]
    assert n.step == CARD and n.params["method"] == METHOD_PROFILE
    assert n.params["source"] == "test"


# --------------------------------------------------------------------------- #
# 四張收成一張之後：合併卡與實作對同一格的說法要一致（F30）
# --------------------------------------------------------------------------- #
def test_the_merged_card_and_each_implementation_agree_on_every_shared_box():
    """**這一條是踩出來的。**

    折進來的兩支不再自己宣告 ``source`` / ``max_boxes`` 那幾格（合併卡上只有
    一份），可是它們的 `run` 仍然會 `validate_params` 一次 —— 拿的是**自己
    模組裡那一份舊 spec**。實測 ``roi_cross`` 的 ``max_boxes`` 上限是 4096、
    合併卡是 65536，於是合併卡的預設值 8192 讓 Profile 那一支**每一顆都失敗**，
    訊息是「parameter 'max_boxes': 8192 is above the maximum of 4096」——
    指著一個使用者從來沒有打過的數字。

    ``default`` **刻意不比**：三支的舊預設互相衝突，而遷移把舊值逐字寫進參數
    （見 `recipe._FOLDED_CARD_OLD_DEFAULTS`）。會咬人的是**範圍與型別**。
    """
    from d4t.core.steps.roi_cross import RoiCrossStep
    from d4t.core.steps.roi_template import RoiTemplateStep

    merged = {s.name: s for s in get_step(CARD).params}
    bad = []
    for impl in (RoiCrossStep, RoiTemplateStep):
        for spec in impl.params:
            mine = merged.get(spec.name)
            if mine is None:
                bad.append("%s.%s 不在合併卡上" % (impl.__name__, spec.name))
                continue
            for field in ("type", "min", "max", "choices", "pattern"):
                if getattr(spec, field, None) != getattr(mine, field, None):
                    bad.append("%s.%s 的 %s：%r vs 合併卡的 %r"
                               % (impl.__name__, spec.name, field,
                                  getattr(spec, field, None),
                                  getattr(mine, field, None)))
    assert not bad, "\n".join(bad)


def test_every_method_runs_with_nothing_but_its_defaults():
    """合併卡的預設值餵給每一支，四支都要**至少驗得過參數**。

    上面那條比的是 spec，這一條走的是真的那條路（`_params_for` → 實作的
    `validate_params`）—— 兩者都要，因為填值的那一步自己也可能填錯。
    """
    from d4t.core.steps.roi_reference import _params_for, _impl, METHODS
    card = get_step(CARD)
    for method in METHODS:
        impl = _impl(method)
        if impl is None:
            card.validate_params({"method": method})
            continue
        impl.validate_params(_params_for(method, {"method": method}))


# --------------------------------------------------------------------------- #
# 6. Profile / Template 也折進來（F30，2026-08-25）
# --------------------------------------------------------------------------- #
def _folded_recipe(step, params):
    return {
        "recipe_id": "t", "version": 2, "score": {"expr": "0"},
        "routes": {"ebi_patch": ["n0", "n1"]},
        "nodes": {
            "n0": {"step": "load_patch", "params": {}, "enabled": True},
            "n1": {"step": step, "params": dict(params), "enabled": True},
        },
    }


def test_an_old_profile_card_keeps_its_own_defaults():
    """**合併卡的共用預設故意跟舊卡不同** —— 三支的舊預設互相衝突。

    所以遷移要把舊值逐字寫進參數。少了這一步，一份舊檔案會安靜地換一組值跑：
    ``max_boxes`` 從 64 變 8192 不會報錯，它會多量一百個框然後吐出一組不一樣
    的統計量。
    """
    r = Recipe.from_json_dict(_folded_recipe("roi_cross", {"directions": "flat"}))
    n = r.nodes["n1"]
    assert n.step == CARD and n.params["method"] == METHOD_PROFILE
    assert n.params["source"] == "ref"          # 合併卡的預設是 test
    assert n.params["roi_out"] == "cross"       # 合併卡的預設是 region
    assert n.params["max_boxes"] == 64          # 合併卡的預設是 8192
    assert n.params["directions"] == "flat"     # 使用者填過的原樣


def test_an_old_template_card_becomes_the_template_method():
    r = Recipe.from_json_dict(
        _folded_recipe("roi_template", {"locate_axis": "y", "min_score": 0.7}))
    n = r.nodes["n1"]
    assert n.step == CARD and n.params["method"] == METHOD_TEMPLATE
    assert n.params["source"] == "ref"
    assert n.params["locate_axis"] == "y" and n.params["min_score"] == 0.7


def test_the_two_min_confidence_boxes_do_not_share_a_name():
    """撞名而**意思不同**的那一格要改名（同 `roi_compare` 的 ``metrics``）。

    ``min_confidence`` 在 Profile 上是「條紋的信心」（0..200，預設 5.0），在
    ``repeating cells`` 上是「週期的強度」（0..1，預設 0.18）。共用一格的話，
    切換 method 會留下一組對方**看得懂但意思完全不同**的值 —— 它不會報錯，
    它會照著跑。
    """
    old = Recipe.from_json_dict(
        _folded_recipe("roi_cross", {"min_confidence": 7.0})).nodes["n1"]
    assert old.params["min_stripe_confidence"] == 7.0
    assert "min_confidence" not in old.params

    names = {s.name for s in get_step(CARD).params}
    assert "min_stripe_confidence" in names
    # 撞名的那一格連同 ``repeating cells`` 一起走了（2026-08-25）
    assert "min_confidence" not in names
    assert "min_repeat_strength" not in names


@pytest.mark.parametrize("step,params", [
    ("roi_cross", {"directions": "flat", "min_confidence": 7.0}),
    ("roi_template", {"locate_axis": "y"}),
])
def test_the_folded_migration_is_an_identity_the_second_time(step, params):
    """鐵則 9：``to_json_dict → from_json_dict`` 是 `run_batch` 送 recipe 進
    worker 的路 —— 它一旦不是 identity，``workers=1`` 與 ``workers=2`` 會算出
    不同的分數。"""
    once = Recipe.from_json_dict(_folded_recipe(step, params)).to_json_dict()
    twice = Recipe.from_json_dict(once).to_json_dict()
    assert once == twice


def test_each_method_only_shows_its_own_settings():
    """四支的參數不可以互相洩漏 —— 攤在那裡讓使用者猜是這張卡最大的風險。"""
    card = get_step(CARD)
    specs = {s.name: s for s in card.params}
    seen = {}
    for method in (METHOD_PROFILE, METHOD_GDS, METHOD_PROFILE, METHOD_TEMPLATE):
        vals = card.validate_params({"method": method})
        seen[method] = {n for n, s in specs.items() if s.visible_for(vals)}
    # 各自的招牌參數只出現在自己那一支上
    for name, owner in (("layers", METHOD_GDS),
                        ("template", METHOD_TEMPLATE),
                        ("directions", METHOD_PROFILE)):
        for method, names in seen.items():
            assert (name in names) == (method == owner), (name, method)
    # `directions` 底下那一整組是 Profile 專屬的
    assert not (seen[METHOD_TEMPLATE] & {"vertical_width", "horizontal_width"})
    # 共用的那幾格每一支都在
    for method, names in seen.items():
        assert {"pick", "drop_edge", "output_prefix", "max_boxes"} <= names, method


# --------------------------------------------------------------------------- #
# 7. 打錯的層號表要**講出來**（2026-08-25）
# --------------------------------------------------------------------------- #
def test_a_layer_table_that_cannot_be_read_says_so():
    """**這一條是使用者回報的那個形狀。**

    原話：「如果選擇 layout layers 後方阜沒有出口可以輸出阜的區域線」。
    `_layers_of` 把 `ChannelMapError` 吞掉回空 list（打到一半不准拋，那是對的）
    —— 於是一個寫成 ``17=epi`` 的表格產不出任何區域埠，而畫面上**沒有任何東西
    說為什麼**。卡片要跑起來才報錯，可是使用者是在畫布上發現「這張卡好像沒有
    輸出」的。
    """
    card = get_step(CARD)
    broken = {"method": METHOD_GDS, "layers": "17=epi"}     # 分隔符是 ':'
    assert card.resolve_regions_out(broken) == []
    said = " ".join(card.configuration_issues(broken))
    assert "layer table cannot be read" in said
    assert "no outputs on the canvas" in said
    assert "':'" in said or ":" in said                      # 講得出正確寫法


def test_a_correct_layer_table_produces_the_ports_and_no_complaint():
    """否則上面那條只證明了「這張卡永遠在抱怨」。"""
    card = get_step(CARD)
    good = {"method": METHOD_GDS, "layers": "17:epi,22:mg"}
    assert card.resolve_regions_out(good) == [
        "epi", "epi_center", "epi_others", "mg", "mg_center", "mg_others"]
    assert card.configuration_issues(good) == []


def test_an_empty_layer_table_says_where_to_get_one():
    card = get_step(CARD)
    said = " ".join(card.configuration_issues({"method": METHOD_GDS}))
    assert "Open GDS export" in said


def test_the_repeating_cells_method_is_gone():
    """使用者 2026-08-25：「請把前者刪掉」。

    ⚠ **舊 recipe 要明確報錯，不可以安靜地換一支跑。** ``method`` 是一個
    `choice`，所以一個認不得的值進不了 `validate_params` —— 那正是要的：
    「這一份檔案用的那個方法不在了」比「它現在用另一個演算法算」好得多。
    """
    from d4t.core.steps import roi_reference as mod
    assert not hasattr(mod, "METHOD_CELLS")
    card = get_step(CARD)
    choices = {s.name: s for s in card.params}["method"].choices
    assert "repeating cells" not in choices
    assert len(choices) == 3
    with pytest.raises(Exception):
        card.validate_params({"method": "repeating cells"})


def test_nothing_declares_the_cells_features_any_more():
    card = get_step(CARD)
    declared = set(card.features_out)
    for m in METHODS_ALL:
        declared |= set(card.resolve_features({"method": m}))
    assert not (declared & {"cells_px", "cells_py", "cells_n",
                            "cells_confidence", "cells_axes"})
