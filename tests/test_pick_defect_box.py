# F20 驗收：「這一組框裡，哪一塊是缺陷那一塊」（2026-08-22）。
"""在這之前這件事是寫死的：**離 patch 正中心最近的那一塊**。

那句話假設 patch 是以缺陷為中心裁的。假設成立時它完全夠用而且不必接線；
但座標會偏 —— 在 ``0822test/mgepi_real3`` 上（缺陷離正中心中位數 7.1 px）
「離中心最近」只有 11/24 顆真的框到缺陷，換成「訊號最強」是 24/24，
而下游的凸出量 AUC 從 0.680 變成 0.985。

這一份鎖住三件事：兩種規則各自挑對、**沒接線要退回而且講出來**、
以及判斷用的那條流有進 ``resolve_reads``（不進去的話它就不在拓撲排序與
快取簽章裡，改一條線而簽章看不見 —— 鐵則 10）。
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


def _signal_on(box, value=200.0):
    img = np.full(SHAPE, 10.0)
    x, y, w, h = box
    img[y + 4:y + 8, x + 4:x + 8] = value
    return img


def test_centre_rule_picks_the_middle_one():
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "centre")
    assert idx == 1
    assert by_signal is False


def test_strongest_rule_follows_the_signal_not_the_centre():
    """訊號在最右邊那塊 —— 挑它，不是挑正中間那塊。"""
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "strongest",
                                     _signal_on(BOXES[2]))
    assert idx == 2
    assert by_signal is True


def test_strongest_rule_agrees_when_the_defect_really_is_in_the_middle():
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "strongest",
                                     _signal_on(BOXES[1]))
    assert (idx, by_signal) == (1, True)


def test_nothing_wired_falls_back_and_says_so():
    """**這一條是重點。** 安靜地照做才是最糟的：使用者以為挑的是訊號最強的那塊，
    整批其實是用正中心挑的，而每一顆都吐得出正常的數字。"""
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "strongest", None)
    assert idx == 1                     # 退回「離中心最近」
    assert by_signal is False           # 而且看得出來退了


def test_a_single_hot_pixel_does_not_steal_the_box():
    """挑之前先做 3×3 均值 —— 一顆熱點不該把整塊框挑走。"""
    img = np.full(SHAPE, 10.0)
    img[38, 40] = 255.0                                  # 正中間那塊：一顆熱點
    x, y, _w, _h = BOXES[2]
    img[y + 4:y + 8, x + 4:x + 8] = 90.0                 # 最右那塊：一小片
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "strongest", img)
    assert (idx, by_signal) == (2, True)


def test_empty_box_list_does_not_raise():
    assert pick_defect_box([], SHAPE, "strongest", np.zeros(SHAPE)) == (0, False)


@pytest.mark.parametrize("step", [RoiCrossStep, RoiTemplateStep])
def test_the_judging_stream_is_declared_as_an_input(step):
    """它會改變框挑到哪一塊 ＝ 會改變下游的結果，所以它必須是一條真的線。"""
    base = {"source": "ref", "pick": "centre", "pick_source": "diff"}
    assert step.resolve_reads(base) == ["ref"]
    assert step.resolve_reads(dict(base, pick="strongest")) == ["ref", "diff"]
    # 選了規則但沒接線 —— 不能宣告一條不存在的流
    assert step.resolve_reads(dict(base, pick="strongest",
                                   pick_source="")) == ["ref"]


@pytest.mark.parametrize("step,name", [(RoiCrossStep, "cross_pick_by_signal"),
                                       (RoiTemplateStep, "pick_by_signal")])
def test_both_cards_report_whether_the_signal_was_really_used(step, name):
    params = {"output_prefix": "", "regions": "", "roi_out": "cross"}
    assert name in step.resolve_features(params)


def test_both_cards_say_it_the_same_way():
    """同一件事在兩張卡上要一字不差 —— 使用者只學一次。"""
    a = {q.name: q for q in RoiCrossStep.params}
    b = {q.name: q for q in RoiTemplateStep.params}
    for key in ("pick", "pick_source"):
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
