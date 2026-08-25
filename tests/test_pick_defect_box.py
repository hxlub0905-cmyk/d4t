# F20 驗收：「這一組框裡，哪一塊是缺陷那一塊」；F32 瘦身成 centre / none。
"""``pick`` 只剩兩個值：``centre``（離 patch 正中心最近）與 ``none``（不挑）。

**``strongest``（訊號挑框）於 F32 刪掉了**（使用者定調）。它當初是量出來的
（F20 在 ``0822test/mgepi_real3`` 上：「離中心最近」11/24、AUC 0.688，
「訊號最強」24/24、AUC 0.977 —— 見
`docs/history/plans/F20-pick-defect-box.md`），代價記在
`_util.PICK_RULES` 的註解上。大圖上「找最異常」現在歸 GLV 的逐框比較。

這一份鎖住：centre 挑對、``none`` 不產生 ``_center``/``_others``、
舊 recipe 填過 ``strongest`` 的**明確報錯**（不安靜換成 centre ——
換規則等於安靜換一組數字）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.steps._util import pick_defect_box  # noqa: E402
from d4t.core.steps.roi_cross import RoiCrossStep  # noqa: E402
from d4t.core.steps.roi_template import RoiTemplateStep  # noqa: E402

SHAPE = (81, 81)
#: 三個框：左、正中間、右。故意讓「離中心最近」與「訊號最強」是不同的兩塊。
BOXES = [(6, 34, 12, 12), (35, 34, 12, 12), (63, 34, 12, 12)]


def test_centre_rule_picks_the_middle_one():
    assert pick_defect_box(BOXES, SHAPE) == 1


def test_empty_box_list_does_not_raise():
    assert pick_defect_box([], SHAPE) == 0


def test_the_choices_are_exactly_centre_and_none():
    """``strongest`` 刪掉之後不准安靜長回來 —— 要回來得先過這一條。"""
    from d4t.core.steps._util import PICK_RULES

    assert tuple(PICK_RULES) == ("centre", "none")
    a = {q.name: q for q in RoiCrossStep.params}
    assert "pick_source" not in a                 # Judge on 那條線一起走了
    assert list(a["pick"].choices) == ["centre", "none"]


def test_an_old_recipe_with_strongest_fails_loudly():
    """舊 recipe 填過 ``strongest`` 的要**報得出讀得懂的錯**，
    不是安靜換成 centre 跑出另一組數字。"""
    from d4t.core.pipeline.step import ParamError

    with pytest.raises(ParamError) as e:
        RoiCrossStep.validate_params({"pick": "strongest"})
    text = str(e.value)
    assert "strongest" in text and "centre" in text


def test_both_cards_say_it_the_same_way():
    """同一件事在兩張卡上要一字不差 —— 使用者只學一次。"""
    a = {q.name: q for q in RoiCrossStep.params}
    b = {q.name: q for q in RoiTemplateStep.params}
    key = "pick"
    assert a[key].help == b[key].help
    assert a[key].label == b[key].label
    assert list(a[key].choices or []) == list(b[key].choices or [])


# --------------------------------------------------------------------------- #
# pick = "none"（F31 T4）—— 不挑：只有主名字，沒有 _center / _others
# --------------------------------------------------------------------------- #
def test_none_declares_only_the_plain_name_on_every_card():
    """三張卡的宣告都經過 `_util.region_family` —— 開關只在那一支。"""
    from d4t.core.pipeline.step import REGISTRY

    ref = REGISTRY["roi_reference"]
    gds = {"method": "layout layers", "layers": "17:epi", "pick": "none"}
    assert ref.resolve_regions_out(gds) == ["epi"]
    assert ref.resolve_regions_out(dict(gds, pick="centre")) == [
        "epi", "epi_center", "epi_others"]

    assert RoiCrossStep.resolve_regions_out(
        {"roi_out": "cross", "pick": "none"}) == ["cross"]
    assert RoiTemplateStep.resolve_regions_out(
        {"regions": "epi: 0,0,1,1", "pick": "none"}) == ["epi"]


def test_none_writes_only_the_plain_name_at_run_time():
    """執行也一樣：`ctx.roi_names()` 只有主名字，`regions_absent` 也不記
    `_others`（那個名字**沒有被宣告**，不是「該在而不在」）。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    label = np.zeros((60, 60), np.uint16)
    label[10:30, 10:50] = 17
    ctx = Context(images={"layout_label": label})
    get_step("roi_reference")().run(ctx, {
        "method": "layout layers", "layers": "17:epi", "pick": "none"})
    assert ctx.roi_names() == ["epi"]
    assert "epi_others" not in (ctx.meta.get("regions_absent") or {})


def test_none_declares_and_writes_the_same_feature_set():
    """`pick_by_signal` 跟著挑選一起走 —— 宣告 == 寫出（逐字相等）。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    label = np.zeros((60, 60), np.uint16)
    label[10:30, 10:50] = 17
    p = {"method": "layout layers", "layers": "17:epi", "pick": "none"}
    ctx = Context(images={"layout_label": label})
    card = get_step("roi_reference")
    card().run(ctx, p)
    assert set(ctx.features) == set(card.resolve_features(p))
    assert not any("pick_by_signal" in k for k in ctx.features)


def test_none_never_falls_back_to_the_nearest_box():
    """`pick_defect_box` 對不認得的 rule 會安靜退回「離中心最近」——
    所以 ``none`` 必須在呼叫端短路。這一條驗的是那個短路真的發生：
    交會格數不變、而沒有任何一格被當成中心。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    rng = np.random.default_rng(3)
    img = np.full((81, 81), 40.0)
    for c in (10, 37, 64):                     # 3×3 條紋交會
        img[:, c:c + 8] += 60.0
        img[c:c + 8, :] += 60.0
    img += rng.normal(0, 2.0, img.shape)
    ctx = Context(images={"ref": img.astype(np.float32)})
    get_step("roi_reference")().run(ctx, {
        "method": "stripes in the image", "source": "ref",
        "roi_out": "cross", "pick": "none"})
    assert "cross" in ctx.roi_names()
    assert "cross_center" not in ctx.roi_names()
    assert "cross_pick_by_signal" not in ctx.features
    assert "cross_dist_px" not in ctx.features   # 「挑中那塊離中心多遠」不存在


def test_a_downstream_card_still_pointing_at_center_is_caught_by_lint():
    """pick=none 之後下游還指著 `_center` → `unknown-region`（現有機制），
    不是安靜地改量整張圖。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline.recipe import (Recipe, RecipeNode, ScoreSpec,
                                          validate)
    from d4t.core.pipeline.step import REGISTRY

    def rec(pick):
        return Recipe(
            recipe_id="t", routes={"rsem": ["load", "r", "g"]},
            nodes={"load": RecipeNode("load", "load_single", {}),
                   "r": RecipeNode("r", "roi_reference", {
                       "method": "layout layers", "layers": "17:epi",
                       "pick": pick}),
                   "g": RecipeNode("g", "glv_stats", {
                       "source": "single", "roi": "epi_center"})},
            score=ScoreSpec(expr="1", threshold=0.0,
                            bins={"below": 0, "above": 1}))

    codes = {i.code for i in validate(rec("none"), registry=REGISTRY)}
    assert "unknown-region" in codes
    codes = {i.code for i in validate(rec("centre"), registry=REGISTRY)}
    assert "unknown-region" not in codes


def test_the_error_message_no_longer_swears_the_defect_is_in_the_middle():
    """「which is where the defect is」在 RSEM 大圖上是錯的 —— 改成分兩種
    情況講。全 repo 的 help／錯誤訊息都不准再無條件斷言缺陷在中央。"""
    import inspect

    import d4t.core.steps._util as util
    import d4t.core.steps.roi_cross as cross
    import d4t.core.steps.roi_reference as ref

    for mod in (util, cross, ref):
        assert "which is where the defect is" not in inspect.getsource(mod)

    # 新訊息本身：兩條路都在
    from d4t.core.pipeline.context import Context
    from d4t.core.steps._util import roi_rect_or_none
    from d4t.core.pipeline.step import StepError

    ctx = Context(images={})
    ctx.set_roi_boxes("epi", [(0.0, 0.0, 0.4, 0.4), (0.5, 0.5, 0.4, 0.4)])
    with pytest.raises(StepError) as e:
        roi_rect_or_none(ctx, "cd_measure", np.zeros((10, 10)), "epi")
    text = str(e.value)
    assert "epi_center" in text
    assert "On a full-size image" in text
    assert "compares all the boxes" in text
