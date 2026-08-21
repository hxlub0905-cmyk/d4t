"""Tests for the rebuilt CD card (F19 第 2 步).

合成資料的寬度是**已知的**，所以這一份問的每一個問題都有一個對的答案。
演算法本身的準確度在 `tests/test_algo_edge.py`；這裡問的是卡片那一層：
接線、區域、前綴、失敗時說了什麼、以及 ``ctx.meta`` 裡畫得出來的那一份。
"""
from __future__ import annotations

import math

import numpy as np
import pytest

import d4t.core.steps  # noqa: F401 — registration side-effect
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import REGISTRY, StepError
from d4t.core.steps.cd import ALWAYS, DEFAULT_REPORT, REPORT_CHOICES

from tests.test_algo_edge import line_block, line_profile

CARD = "cd_measure"


def run_cd(ctx, **params):
    cls = REGISTRY[CARD]
    return cls().run(ctx, cls.validate_params(params))


def ctx_with(block, key="test", **images):
    imgs = {key: np.asarray(block, dtype=np.float32)}
    imgs.update({k: np.asarray(v, dtype=np.float32)
                 for k, v in images.items()})
    return Context(images=imgs)


def norm_rect(x, y, w, h, size=64):
    return (x / size, y / size, w / size, h / size)


# --------------------------------------------------------------------------- #
# 量得對
# --------------------------------------------------------------------------- #
def test_measures_a_known_width():
    ctx = ctx_with(line_block(rows=32, width=12.0, blur=1.2))
    out = run_cd(ctx)
    assert out.features["cd_median"] == pytest.approx(12.0, abs=0.3)
    assert out.features["cd_n"] == 32.0
    assert out.features["cd_lines"] == 32.0
    assert out.features["cd_edge_score"] > 0.95
    assert not out.meta.get("warnings")


def test_every_automatic_decision_becomes_a_number():
    """方向是卡片自己選的 —— 它一定要吐得出來，否則整批混著兩種量測。"""
    ctx = ctx_with(line_block(rows=32, width=12.0))
    assert run_cd(ctx, axis="auto").features["cd_axis_deg"] == 0.0
    ctx = ctx_with(line_block(rows=32, width=12.0).T)
    assert run_cd(ctx, axis="auto").features["cd_axis_deg"] == 90.0


def test_the_always_features_are_always_there():
    ctx = ctx_with(line_block(rows=20, width=12.0))
    got = run_cd(ctx, report="cd_median").features
    for name in ALWAYS:
        assert name in got, name


def test_roughness_is_the_spread_of_the_widths():
    """σ 不是另外算的功能，它就是那組寬度的散布 —— 而兩條邊各自的 σ 是 LER。"""
    smooth = run_cd(ctx_with(line_block(rows=40, jitter=0.0, seed=4)),
                    report="cd_std,ler_a_std,ler_b_std").features
    rough = run_cd(ctx_with(line_block(rows=40, jitter=1.5, seed=4)),
                   report="cd_std,ler_a_std,ler_b_std").features
    # 整條線在漂 = 兩條邊一起動 → LER 大很多，LWR 幾乎不動。
    assert rough["ler_a_std"] > smooth["ler_a_std"] + 0.5
    assert rough["ler_b_std"] > smooth["ler_b_std"] + 0.5
    assert rough["cd_std"] == pytest.approx(smooth["cd_std"], abs=0.5)


def test_min_and_max_find_the_neck():
    """一條被捏細的線：平均看不出來，``cd_min`` 看得出來。"""
    block = line_block(rows=30, width=12.0, blur=1.0)
    pinched = line_profile(width=7.0, blur=1.0)
    block[14:17] = pinched                       # 中間三列頸縮
    got = run_cd(ctx_with(block), report="cd_median,cd_min,cd_max").features
    assert got["cd_median"] == pytest.approx(12.0, abs=0.4)
    assert got["cd_min"] == pytest.approx(7.0, abs=0.5)
    assert got["cd_max"] == pytest.approx(12.0, abs=0.4)


@pytest.mark.parametrize("criterion", ["threshold", "gradient", "fit"])
def test_all_three_criteria_run_through_the_card(criterion):
    ctx = ctx_with(line_block(rows=20, width=12.0, blur=1.2))
    got = run_cd(ctx, criterion=criterion).features
    assert got["cd_median"] == pytest.approx(12.0, abs=0.4)


def test_threshold_height_is_a_real_knob():
    """門檻拉高，量到的亮線就變窄；暗溝相反。

    **這一支是踩過的坑的便利貼。** 第一版的門檻高度是「從左邊那個平台算起」，
    於是一條亮線的上升邊量在 25%、下降邊量在 75% —— 兩條邊同向移動，寬度
    完全不動（12.2348106481077 對 12.234810648107693）。一個看起來有在動、
    實際上沒有作用、而且每一顆都吐得出正常數字的旋鈕。
    """
    bright = line_block(rows=20, width=12.0, blur=2.0)
    lo = run_cd(ctx_with(bright), threshold_pct=25).features["cd_median"]
    mid = run_cd(ctx_with(bright), threshold_pct=50).features["cd_median"]
    hi = run_cd(ctx_with(bright), threshold_pct=75).features["cd_median"]
    assert lo > mid > hi
    assert lo - hi > 3.0

    dark = 220.0 - bright                        # 暗溝：同一組高度，反過來
    d_lo = run_cd(ctx_with(dark), threshold_pct=25,
                  target="dark").features["cd_median"]
    d_hi = run_cd(ctx_with(dark), threshold_pct=75,
                  target="dark").features["cd_median"]
    assert d_hi > d_lo + 3.0
    assert d_lo == pytest.approx(hi, abs=0.05)   # 鏡像，逐格對得上


def test_dark_target_measures_the_gap():
    block = 220.0 - line_block(rows=20, width=10.0, blur=1.2)
    got = run_cd(ctx_with(block), target="dark").features
    assert got["cd_median"] == pytest.approx(10.0, abs=0.35)


# --------------------------------------------------------------------------- #
# 區域
# --------------------------------------------------------------------------- #
def test_a_region_narrows_where_it_measures():
    block = line_block(rows=64, width=12.0, blur=1.2)
    ctx = ctx_with(block)
    ctx.set_roi("band", norm_rect(0, 8, 64, 16))
    got = run_cd(ctx, roi="band").features
    assert got["cd_lines"] == 16.0                # 只有那 16 列
    assert got["cd_median"] == pytest.approx(12.0, abs=0.3)


def test_two_regions_get_their_names_in_front():
    block = line_block(rows=64, width=12.0, blur=1.2)
    ctx = ctx_with(block)
    ctx.set_roi("top", norm_rect(0, 4, 64, 12))
    ctx.set_roi("bot", norm_rect(0, 40, 64, 12))
    got = run_cd(ctx, roi="top,bot").features
    assert "top_cd_median" in got and "bot_cd_median" in got
    assert "cd_median" not in got                 # 兩個以上一定帶前綴


def test_one_region_keeps_the_bare_name():
    """只接一個時名字跟沒接區域時逐字相同 —— 分數表達式不必改寫。"""
    block = line_block(rows=64, width=12.0)
    ctx = ctx_with(block)
    ctx.set_roi("band", norm_rect(0, 8, 64, 16))
    assert "cd_median" in run_cd(ctx, roi="band").features


def test_two_streams_get_their_names_in_front():
    a = line_block(rows=24, width=12.0, blur=1.2)
    b = line_block(rows=24, width=8.0, blur=1.2)
    ctx = ctx_with(a, test=a, ref=b)
    got = run_cd(ctx, source="test,ref").features
    assert got["test_cd_median"] == pytest.approx(12.0, abs=0.3)
    assert got["ref_cd_median"] == pytest.approx(8.0, abs=0.3)


def test_an_unknown_region_is_an_error_not_a_silent_whole_image():
    ctx = ctx_with(line_block(rows=20, width=12.0))
    with pytest.raises(StepError) as e:
        run_cd(ctx, roi="nope")
    assert "not defined" in str(e.value)


def test_a_region_too_small_to_cross_says_so():
    block = line_block(rows=32, width=12.0)
    ctx = ctx_with(block)
    ctx.set_roi("sliver", norm_rect(30, 30, 2, 2))
    out = run_cd(ctx, roi="sliver")
    assert not any(k.startswith("cd_") for k in out.features)
    assert "too small" in " ".join(out.meta["warnings"])


# --------------------------------------------------------------------------- #
# 失敗時說了什麼（三條寫死的規矩）
# --------------------------------------------------------------------------- #
def test_the_frame_is_never_an_edge():
    """結構跑出畫面時**拒絕**，不是吐出「到畫面為止」那個寬度。

    重做之前的那張卡在這裡會吐 patch 的寬度 —— 一個看起來完全正常的常數。
    """
    block = line_block(rows=24, center=58.0, width=24.0, blur=1.2)
    out = run_cd(ctx_with(block))
    assert "cd_median" not in out.features
    assert out.features["cd_n"] == 0.0
    assert out.features["cd_lines"] == 24.0
    said = " ".join(out.meta["warnings"])
    assert "a frame is not an edge" in said
    assert "ran past the edge" in said            # 講得出下一步


def test_too_few_lines_writes_nothing_rather_than_a_number():
    block = line_block(rows=24, width=12.0, blur=1.2)
    block[3:] = 100.0                             # 只剩三列有結構
    # ``axis="x"`` 是刻意的：那 21 列平的會讓 auto 改挑 y（上下之間才是最陡的
    # 地方），而那個判斷是對的 —— 這一支要測的是「線太少」，不是自動選方向。
    out = run_cd(ctx_with(block), min_lines=10, axis="x")
    assert "cd_median" not in out.features
    assert "cd_edge_score" not in out.features    # 不是 0，是**不寫**
    assert out.features["cd_n"] == 3.0
    assert "no width is written" in " ".join(out.meta["warnings"])


def test_a_flat_image_fails_quietly_per_defect():
    """鐵則 7：單顆量不出來不得殺掉整批。"""
    out = run_cd(ctx_with(np.full((32, 64), 120.0)))
    assert out.features["cd_n"] == 0.0
    assert "cd_median" not in out.features


def test_there_is_no_subpixel_switch():
    """次像素不是選項 —— 1 px 的量化打在 10 px 的線上是 10%。"""
    names = {s.name for s in REGISTRY[CARD].params}
    assert "refine" not in names
    assert not any("subpixel" in n for n in names)


# --------------------------------------------------------------------------- #
# 宣告 = 真的吐出來的（鐵則：畫布與 CSV 不能說謊）
# --------------------------------------------------------------------------- #
def test_declaration_matches_what_comes_out():
    cls = REGISTRY[CARD]
    params = cls.validate_params({"report": ",".join(REPORT_CHOICES),
                                  "target_cd": 12.0})
    ctx = ctx_with(line_block(rows=24, width=12.0, blur=1.2))
    out = cls().run(ctx, params)
    declared = set(cls.resolve_features(params))
    assert set(out.features) <= declared
    for name in REPORT_CHOICES:
        assert name in out.features, name


def test_target_features_are_not_declared_without_a_target():
    cls = REGISTRY[CARD]
    without = cls.resolve_features(cls.validate_params(
        {"report": "cd_median,cd_dev,cd_dev_frac"}))
    assert "cd_dev" not in without and "cd_dev_frac" not in without
    withit = cls.resolve_features(cls.validate_params(
        {"report": "cd_median,cd_dev,cd_dev_frac", "target_cd": 12.0}))
    assert "cd_dev" in withit and "cd_dev_frac" in withit


def test_off_target_is_the_number_worth_binning_on():
    ctx = ctx_with(line_block(rows=24, width=9.0, blur=1.0))
    got = run_cd(ctx, report="cd_median,cd_dev,cd_dev_frac",
                 target_cd=12.0).features
    assert got["cd_dev"] == pytest.approx(-3.0, abs=0.4)
    assert got["cd_dev_frac"] == pytest.approx(-0.25, abs=0.04)


def test_nanometres_come_along_when_the_pixel_size_is_known():
    ctx = ctx_with(line_block(rows=24, width=12.0, blur=1.2))
    ctx.meta["nm_per_px"] = 5.0
    got = run_cd(ctx, report="cd_median,cd_std,cd_dev_frac",
                 target_cd=12.0).features
    assert got["cd_median_nm"] == pytest.approx(got["cd_median"] * 5.0)
    assert got["cd_std_nm"] == pytest.approx(got["cd_std"] * 5.0)
    # 比例、條數、角度**不該**有 nm 版本
    for name in ("cd_dev_frac", "cd_n", "cd_lines", "cd_axis_deg"):
        assert name + "_nm" not in got


def test_the_old_bbox_features_are_gone():
    """F19：舊的三個完全刪掉，以新的為主（使用者 2026-08-21）。"""
    ctx = ctx_with(line_block(rows=24, width=12.0))
    got = run_cd(ctx, report=",".join(REPORT_CHOICES)).features
    for old in ("cd_x_px", "cd_y_px", "area_px"):
        assert old not in got
    assert old not in REGISTRY[CARD].features_out


# --------------------------------------------------------------------------- #
# 給面板與影像疊圖的那一份
# --------------------------------------------------------------------------- #
def test_meta_carries_everything_the_panel_needs():
    ctx = ctx_with(line_block(rows=24, width=12.0, blur=1.2))
    note = run_cd(ctx).meta["cd"][""]
    assert note["axis"] == "x" and note["criterion"] == "threshold"
    assert note["n"] == 24 and note["lines"] == 24
    assert len(note["scan_lines"]) == 24 and len(note["edges"]) == 24
    prof = note["profile"]
    assert len(prof["values"]) == 64
    assert prof["level"] is not None                # threshold 判準才有橫線
    assert prof["a"] < prof["b"]


def test_meta_coordinates_are_normalised_and_inside_the_region():
    block = line_block(rows=64, width=12.0, blur=1.2)
    ctx = ctx_with(block)
    ctx.set_roi("band", norm_rect(0, 16, 64, 20))
    note = run_cd(ctx, roi="band").meta["cd"][""]
    for (x0, y0), (x1, y1) in note["scan_lines"]:
        assert 0.0 <= x0 <= 1.0 and 0.0 <= x1 <= 1.0
        # 掃描線落在區域那 20 列裡（16/64 … 36/64）
        assert 0.25 <= y0 <= 0.5625 and y0 == y1
    for (xa, _ya), (xb, _yb) in note["edges"]:
        assert 0.0 < xa < xb < 1.0


def test_meta_is_keyed_by_prefix_so_two_regions_do_not_collide():
    block = line_block(rows=64, width=12.0)
    ctx = ctx_with(block)
    ctx.set_roi("top", norm_rect(0, 4, 64, 12))
    ctx.set_roi("bot", norm_rect(0, 40, 64, 12))
    note = run_cd(ctx, roi="top,bot").meta["cd"]
    assert set(note) == {"top", "bot"}
    assert note["top"]["region"] == "top"


def test_meta_records_why_lines_failed():
    block = line_block(rows=20, center=58.0, width=24.0, blur=1.2)
    note = run_cd(ctx_with(block)).meta["cd"][""]
    assert note["reasons"]["open_edge"] == 20
    assert note["n"] == 0 and "profile" not in note


def test_the_default_report_is_the_robust_one():
    assert DEFAULT_REPORT.split(",") == ["cd_median", "cd_std", "cd_min",
                                         "cd_max"]
    assert all(m in REPORT_CHOICES for m in DEFAULT_REPORT.split(","))
