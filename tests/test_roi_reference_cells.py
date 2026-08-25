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
from d4t.core.steps.roi_reference import METHOD_CELLS, METHOD_GDS  # noqa: E402

CARD = "roi_reference"


def lattice(size=192, period=24, pad=6, bg=40.0, fg=200.0):
    """``size/period`` 見方的晶格 —— 每一格中間一個亮方塊。"""
    img = np.full((size, size), bg, np.float32)
    for y in range(0, size, period):
        for x in range(0, size, period):
            img[y + pad:y + period - pad, x + pad:x + period - pad] = fg
    return img


def stripes(size=192, period=16, width=8, bg=40.0, fg=200.0):
    img = np.full((size, size), bg, np.float32)
    for x in range(0, size, period):
        img[:, x:x + width] = fg
    return img


def run(img, **over):
    card = get_step(CARD)
    p = card.validate_params(dict({"method": METHOD_CELLS, "source": "test",
                                   "roi_out": "epi"}, **over))
    ctx = Context(images={"test": np.asarray(img, np.float32)})
    card().run(ctx, p)
    return ctx


# --------------------------------------------------------------------------- #
# 1. 切得對
# --------------------------------------------------------------------------- #
def test_a_lattice_becomes_one_region_per_cell():
    ctx = run(lattice(size=192, period=24))
    assert ctx.features["cells_px"] == 24.0
    assert ctx.features["cells_py"] == 24.0
    assert ctx.features["cells_n"] == 64.0          # (192/24)² = 8×8
    assert ctx.features["cells_axes"] == 2.0
    assert ctx.roi_count("epi") == 64


def test_every_cell_is_the_size_of_the_period():
    ctx = run(lattice(size=192, period=24))
    for _x, _y, w, h in ctx.roi_rects("epi", (192, 192)):
        assert (w, h) == (24, 24)


def test_the_family_is_the_whole_set_the_one_and_the_rest():
    """``_others`` 就是參照 —— 這一支存在的理由。"""
    ctx = run(lattice())
    assert sorted(ctx.roi_names()) == ["epi", "epi_center", "epi_others"]
    assert ctx.roi_count("epi_center") == 1
    assert ctx.roi_count("epi_others") == ctx.roi_count("epi") - 1


def test_the_confidence_is_on_the_same_scale_as_the_knob():
    """使用者那一格擋的就是這個數字 —— 報另一個刻度的話，「我設 0.18，
    它說 85」這句話沒有人解得開。（`estimate_period` 的 ``confidence``
    是 0..100，``peak_strength`` 才是 0..1。）"""
    got = run(lattice()).features["cells_confidence"]
    assert 0.0 <= got <= 1.0
    assert got > 0.5                                 # 這張圖非常規則


# --------------------------------------------------------------------------- #
# 2. 量不到就停下來
# --------------------------------------------------------------------------- #
def test_pure_noise_is_refused_not_guessed():
    """**這一條是這張卡最重要的一條。**

    一格猜出來的晶格照樣讓每一顆 defect 吐得出很正常的灰階值。
    """
    noise = np.random.default_rng(0).normal(120, 3, (192, 192)).astype(np.float32)
    with pytest.raises(StepError) as e:
        run(noise)
    text = str(e.value)
    assert "no repeating pattern" in text
    assert METHOD_GDS in text                        # 講得出下一步


def test_a_flat_image_is_refused_too():
    with pytest.raises(StepError):
        run(np.full((192, 192), 100.0, np.float32))


def test_raising_the_bar_refuses_a_weak_repeat():
    """``Ignore repeats weaker than`` 真的擋得住東西（否則它是個裝飾）。"""
    weak = lattice(bg=100.0, fg=104.0)               # 只差 4 灰階
    weak = weak + np.random.default_rng(1).normal(0, 6.0, weak.shape)
    with pytest.raises(StepError):
        run(weak.astype(np.float32), min_confidence=0.9)


def test_a_period_bigger_than_the_image_says_so():
    ctx_err = None
    try:
        run(lattice(size=64, period=24), min_period=200, max_period=400)
    except StepError as e:
        ctx_err = str(e)
    assert ctx_err and ("does not fit" in ctx_err
                        or "no repeating pattern" in ctx_err)


# --------------------------------------------------------------------------- #
# 3. 條紋不是晶格
# --------------------------------------------------------------------------- #
def test_stripes_span_the_image_on_the_axis_with_no_period():
    """沒有週期的那一軸**沒有相位可言** —— 硬給一個位置等於憑空捏造資訊。"""
    ctx = run(stripes(size=192, period=16, width=8))
    assert ctx.features["cells_px"] == 16.0
    assert ctx.features["cells_py"] == 192.0         # 整張圖高
    assert ctx.features["cells_axes"] == 1.0
    for _x, y, _w, h in ctx.roi_rects("epi", (192, 192)):
        assert (y, h) == (0, 192)


# --------------------------------------------------------------------------- #
# 4. 跟 GDS 那一支是同一張卡
# --------------------------------------------------------------------------- #
def test_both_methods_share_the_same_wiring_params():
    card = get_step(CARD)
    names = {s.name: s for s in card.params}
    for shared in ("pick", "pick_source", "drop_edge", "edge_margin",
                   "output_prefix", "max_boxes", "method"):
        assert names[shared].show_when in (None, ("pick", ("strongest",)),
                                           ("drop_edge", (True,))), shared
    # 兩支各自的那幾格要**藏起來**，不是攤在那裡讓使用者猜。
    assert names["layers"].show_when == ("method", (METHOD_GDS,))
    assert names["source"].show_when == ("method", (METHOD_CELLS,))
    assert names["label_source"].show_when == ("method", (METHOD_GDS,))


def test_each_method_declares_only_the_stream_it_really_reads():
    """兩支吃的是兩種完全不同的東西 —— 一張照片，跟一張「像素值就是層號」的圖。"""
    card = get_step(CARD)
    cells = card.resolve_reads(card.validate_params(
        {"method": METHOD_CELLS, "source": "test"}))
    gds = card.resolve_reads(card.validate_params(
        {"method": METHOD_GDS, "label_source": "layout_label"}))
    assert cells == ["test"]
    assert gds == ["layout_label"]


def test_judging_on_another_stream_is_declared_as_a_read():
    """`pick="strongest"` 要判斷的那條流，畫布上也是一條線。"""
    card = get_step(CARD)
    got = card.resolve_reads(card.validate_params(
        {"method": METHOD_CELLS, "source": "test", "pick": "strongest",
         "pick_source": "diff"}))
    assert got == ["test", "diff"]


def test_strongest_picks_the_odd_cell_out():
    img = lattice(size=192, period=24)
    sig = np.zeros((192, 192), np.float32)
    sig[52:68, 100:116] = 200.0                      # 落在第 (4, 2) 格附近
    card = get_step(CARD)
    ctx = Context(images={"test": img, "diff": sig})
    card().run(ctx, card.validate_params(
        {"method": METHOD_CELLS, "source": "test", "roi_out": "epi",
         "pick": "strongest", "pick_source": "diff"}))
    x, y, w, h = ctx.roi_rects("epi_center", (192, 192))[0]
    assert x <= 108 < x + w and y <= 60 < y + h
    assert ctx.features["pick_by_signal"] == 1.0


def test_falling_back_to_the_middle_is_said_out_loud():
    ctx = run(lattice(), pick="strongest")
    assert ctx.features["pick_by_signal"] == 0.0
    assert "Judge on" in " ".join(ctx.meta["warnings"])


def test_the_declared_features_match_what_it_writes():
    card = get_step(CARD)
    p = card.validate_params({"method": METHOD_CELLS, "source": "test",
                              "roi_out": "epi"})
    assert set(run(lattice()).features) == set(card.resolve_features(p))


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
                        "params": {"method": METHOD_CELLS, "source": "test",
                                   "roi_out": "epi"}}
    n = Recipe.from_json_dict(d).nodes["n2"]
    assert n.step == CARD and n.params["method"] == METHOD_CELLS
    assert n.params["source"] == "test"
