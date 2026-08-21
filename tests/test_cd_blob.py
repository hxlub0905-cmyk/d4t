"""CD 的無方向那一支，在卡片那一層（F19 第二批第 2 步）。

演算法本身在 `tests/test_algo_shape.py`；這裡問的是卡片：岔路有沒有把另一支
關乾淨、宣告對不對、失敗說了什麼、以及 ``ctx.meta`` 裡畫得出來的那一份。
"""
from __future__ import annotations

import math

import numpy as np
import pytest

import d4t.core.steps  # noqa: F401 — registration side-effect
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import REGISTRY
from d4t.core.steps.cd import (
    ALWAYS, ALWAYS_BLOB, DEFAULT_SIZE_REPORT, REPORT_CHOICES, SHAPE_BLOB,
    SHAPE_LINE, SIZE_CHOICES,
)

from tests.test_algo_edge import line_block
from tests.test_algo_shape import add_ellipse, canvas, disc, l_shape

CARD = "cd_measure"
ALL_SIZE = ",".join(SIZE_CHOICES)


def run_blob(img, **params):
    cls = REGISTRY[CARD]
    p = cls.validate_params(dict({"shape": SHAPE_BLOB,
                                  "size_report": ALL_SIZE}, **params))
    ctx = Context(images={"test": np.asarray(img, dtype=np.float32)})
    return cls().run(ctx, p), p


def norm_rect(x, y, w, h, size=64):
    return (x / size, y / size, w / size, h / size)


# --------------------------------------------------------------------------- #
# 量得對
# --------------------------------------------------------------------------- #
def test_measures_a_disc_of_known_size():
    out, _p = run_blob(disc(d=20.0))
    got = out.features
    assert got["cd_area_px"] == pytest.approx(math.pi * 100.0, rel=0.06)
    assert got["cd_deq"] == pytest.approx(20.0, abs=0.6)
    assert got["cd_feret_max"] == pytest.approx(20.0, abs=1.5)
    assert got["cd_feret_min"] == pytest.approx(20.0, abs=1.5)
    assert got["cd_aspect"] == pytest.approx(1.0, abs=0.15)
    assert got["cd_roundness"] > 0.85
    assert got["cd_pieces"] == 1.0
    assert got["cd_touches_edge"] == 0.0
    assert not out.meta.get("warnings")


def test_the_area_is_the_real_coverage_not_the_box():
    """**這一支存在的理由。** 一個 L 的 bbox 幾乎是它真實面積的兩倍。"""
    out, _p = run_blob(l_shape(arm=26, thick=8))
    truth = 26 * 8 + (26 - 8) * 8
    assert out.features["cd_area_px"] == pytest.approx(truth, rel=0.06)
    assert out.features["cd_area_px"] < 26 * 26 * 0.7


@pytest.mark.parametrize("angle", [0.0, 45.0, 90.0, 135.0])
def test_the_answer_does_not_depend_on_which_way_it_is_turned(angle):
    img = canvas(96)
    add_ellipse(img, 48, 48, 15.0, 4.0, angle=angle)
    got = run_blob(img)[0].features
    assert got["cd_feret_max"] == pytest.approx(30.0, abs=2.0)
    assert got["cd_feret_min"] == pytest.approx(8.0, abs=2.0)
    assert got["cd_area_px"] == pytest.approx(math.pi * 15.0 * 4.0, rel=0.12)


def test_the_angle_separates_a_scratch_from_a_particle():
    """``cd_feret_angle`` 是自動算出來的，而且它本身有用。"""
    img = canvas(96)
    add_ellipse(img, 48, 48, 18.0, 4.0, angle=30.0)
    got = run_blob(img)[0].features
    assert got["cd_feret_angle"] == pytest.approx(30.0, abs=8.0)
    assert got["cd_aspect"] > 3.0
    round_got = run_blob(disc(size=96, d=30.0))[0].features
    assert round_got["cd_aspect"] < 1.2


def test_a_dark_void_is_measured_too():
    hole = np.full((96, 96), 200.0)
    add_ellipse(hole, 48, 48, 12.0, 12.0, amp=-140.0)
    got = run_blob(hole)[0].features
    assert got["cd_bright"] == 0.0
    assert got["cd_deq"] == pytest.approx(24.0, abs=1.2)


def test_the_height_knob_is_shared_with_the_line_branch():
    """同一格、同一句話：拉高，亮的團變小。"""
    bright = disc(size=96, d=30.0, blur=2.0)
    lo = run_blob(bright, threshold_pct=25)[0].features["cd_area_px"]
    hi = run_blob(bright, threshold_pct=75)[0].features["cd_area_px"]
    assert lo > hi


# --------------------------------------------------------------------------- #
# 岔路：另一支要關乾淨
# --------------------------------------------------------------------------- #
def test_the_blob_branch_writes_none_of_the_line_features():
    got = run_blob(disc(d=20.0))[0].features
    for name in ("cd_median", "cd_std", "cd_n", "cd_lines", "cd_axis_deg"):
        assert name not in got, name


def test_the_line_branch_is_untouched_by_the_new_fork():
    """既有 recipe 沒有 ``shape`` 這個鍵 —— 走的就是線那一支，一字不變。"""
    cls = REGISTRY[CARD]
    block = line_block(rows=32, width=12.0, blur=1.2).astype(np.float32)
    without = cls().run(Context(images={"test": block}),
                        cls.validate_params({})).features
    explicit = cls().run(Context(images={"test": block}),
                         cls.validate_params({"shape": SHAPE_LINE})).features
    assert without == explicit
    assert without["cd_median"] == pytest.approx(12.0, abs=0.3)
    for name in ("cd_area_px", "cd_pieces", "cd_touches_edge"):
        assert name not in without


def test_an_unknown_shape_is_rejected_rather_than_guessed():
    """``icon_choice`` 的驗證擋在前面（鐵則 4）—— 壞值進不到演算法裡。"""
    from d4t.core.pipeline.step import ParamError

    cls = REGISTRY[CARD]
    with pytest.raises(ParamError) as e:
        cls().run(Context(images={"test": disc(d=20.0).astype(np.float32)}),
                  {"shape": "nonsense"})
    assert "shape" in str(e.value)


def test_the_rows_that_do_not_apply_are_hidden():
    """方向對一團東西沒有意義 —— 那一列該收起來，不是攤在那裡讓人猜。"""
    specs = {s.name: s for s in REGISTRY[CARD].params}
    blob = {"shape": SHAPE_BLOB}
    line = {"shape": SHAPE_LINE}
    for name in ("axis", "criterion", "window", "report", "target_cd",
                 "line_step", "line_bin", "min_lines", "smooth"):
        assert not specs[name].visible_for(blob), name
        assert specs[name].visible_for(line), name
    for name in ("size_report", "min_area"):
        assert specs[name].visible_for(blob), name
        assert not specs[name].visible_for(line), name
    # **兩支共用的那幾格一直都在**
    for name in ("source", "roi", "target", "threshold_pct", "min_edge",
                 "output_prefix", "shape"):
        assert specs[name].visible_for(blob) and specs[name].visible_for(line)


# --------------------------------------------------------------------------- #
# 宣告 = 真的吐出來的
# --------------------------------------------------------------------------- #
def test_declaration_matches_what_comes_out():
    out, p = run_blob(disc(d=20.0))
    declared = set(REGISTRY[CARD].resolve_features(p))
    assert set(out.features) <= declared
    for name in SIZE_CHOICES:
        assert name in out.features, name
    for name in ALWAYS_BLOB:
        assert name in out.features, name


def test_each_branch_declares_only_its_own_names():
    cls = REGISTRY[CARD]
    blob = set(cls.resolve_features(cls.validate_params(
        {"shape": SHAPE_BLOB, "size_report": ALL_SIZE})))
    line = set(cls.resolve_features(cls.validate_params({})))
    assert not (blob & {m for m in REPORT_CHOICES})
    assert not (line & {m for m in SIZE_CHOICES})
    assert set(ALWAYS_BLOB) <= blob and set(ALWAYS) <= line


def test_area_converts_with_the_square_and_lengths_do_not():
    """``cd_area_px`` 結尾是 ``_px`` 但意思是面積 —— 少乘一次會很安靜。"""
    cls = REGISTRY[CARD]
    p = cls.validate_params({"shape": SHAPE_BLOB, "size_report": ALL_SIZE})
    ctx = Context(images={"test": disc(d=20.0).astype(np.float32)},
                  meta={"nm_per_px": 3.0})
    got = cls().run(ctx, p).features
    assert got["cd_area_nm2"] == pytest.approx(got["cd_area_px"] * 9.0)
    assert got["cd_deq_nm"] == pytest.approx(got["cd_deq"] * 3.0)
    assert "cd_area_nm" not in got                 # 那是少乘一次的那個名字
    for name in ("cd_aspect", "cd_roundness", "cd_feret_angle", "cd_pieces"):
        assert name + "_nm" not in got


def test_the_default_report_is_the_four_sizes():
    assert DEFAULT_SIZE_REPORT.split(",") == [
        "cd_area_px", "cd_deq", "cd_feret_max", "cd_feret_min"]
    assert all(m in SIZE_CHOICES for m in DEFAULT_SIZE_REPORT.split(","))


# --------------------------------------------------------------------------- #
# 失敗時說了什麼
# --------------------------------------------------------------------------- #
def test_noise_alone_produces_no_size_at_all():
    """線那一支 §6 的二維版：沒有訊號的時候，「最亮的一點」永遠存在。"""
    rng = np.random.default_rng(5)
    out, _p = run_blob(canvas(64) + rng.normal(0.0, 6.0, (64, 64)))
    assert not any(k.startswith("cd_area") for k in out.features)
    # 尺寸不寫，但**「量得準不準」照吐** —— 同線那一支失敗時仍然吐 cd_n。
    assert out.features["cd_pieces"] == 0.0
    assert out.features["cd_edge_score"] < 0.5     # 「為什麼沒有」的那個數字
    assert "cd_touches_edge" not in out.features   # 沒有團的時候它沒有意義
    said = " ".join(out.meta["warnings"])
    assert "stands out from the noise" in said


def test_a_flat_region_says_why_and_does_not_write_zero():
    out, _p = run_blob(canvas(64))
    assert "cd_area_px" not in out.features       # 不是 0，是**不寫**
    assert "nothing to measure" in " ".join(out.meta["warnings"])


def test_a_blob_at_the_edge_is_measured_and_flagged():
    """**照量，但插一支旗子**（使用者 2026-08-21）。"""
    img = canvas(64)
    add_ellipse(img, 58, 32, 14.0, 10.0)
    out, _p = run_blob(img)
    assert out.features["cd_touches_edge"] == 1.0
    assert out.features["cd_area_px"] > 0          # 下界，不是不寫
    said = " ".join(out.meta["warnings"])
    assert "lower bound" in said and "Widen the region" in said


def test_pieces_reveals_which_blob_it_picked():
    img = canvas(96)
    add_ellipse(img, 48, 48, 8.0, 8.0)             # 中心那一團（小）
    add_ellipse(img, 80, 80, 13.0, 13.0)           # 角落那一團（大）
    got = run_blob(img)[0].features
    assert got["cd_pieces"] == 2.0
    assert got["cd_deq"] == pytest.approx(16.0, abs=1.5)   # 挑了中心那個


def test_a_region_too_small_says_so():
    cls = REGISTRY[CARD]
    ctx = Context(images={"test": disc(d=20.0).astype(np.float32)})
    ctx.set_roi("sliver", norm_rect(30, 30, 2, 2))
    out = cls().run(ctx, cls.validate_params(
        {"shape": SHAPE_BLOB, "roi": "sliver"}))
    assert not any(k.startswith("cd_") for k in out.features)
    assert "too small" in " ".join(out.meta["warnings"])


def test_min_area_keeps_specks_out():
    img = canvas(64)
    img[31:34, 31:34] += 150.0                     # 3×3
    assert run_blob(img, min_area=4)[0].features["cd_area_px"] == 9.0
    out, _p = run_blob(img, min_area=25)
    assert "cd_area_px" not in out.features
    assert "smallest blob this card counts" in " ".join(out.meta["warnings"])


# --------------------------------------------------------------------------- #
# 區域與前綴（跟線那一支同一套基底，所以只確認它真的跟著走）
# --------------------------------------------------------------------------- #
def test_regions_and_prefixes_work_the_same_as_on_the_line_branch():
    cls = REGISTRY[CARD]
    img = canvas(96)
    add_ellipse(img, 24, 24, 6.0, 6.0)
    add_ellipse(img, 72, 72, 10.0, 10.0)
    ctx = Context(images={"test": img.astype(np.float32)})
    ctx.set_roi("a", (0.0, 0.0, 0.5, 0.5))
    ctx.set_roi("b", (0.5, 0.5, 0.5, 0.5))
    got = cls().run(ctx, cls.validate_params(
        {"shape": SHAPE_BLOB, "roi": "a,b"})).features
    assert got["a_cd_deq"] == pytest.approx(12.0, abs=1.5)
    assert got["b_cd_deq"] == pytest.approx(20.0, abs=1.5)
    assert "cd_deq" not in got                     # 兩個以上一定帶前綴


# --------------------------------------------------------------------------- #
# 給面板與影像疊圖的那一份
# --------------------------------------------------------------------------- #
def test_meta_carries_the_outline_and_the_levels():
    out, _p = run_blob(disc(d=20.0))
    note = out.meta["cd"][""]
    assert note["shape"] == SHAPE_BLOB and note["ok"]
    assert note["bg"] < note["level"] < note["fg"]
    assert 8 <= len(note["outline"]) <= 96         # 抽稀過，但還是一圈
    assert len(note["chord"]) == 2
    hist = note["hist"]
    assert sum(hist["counts"]) == 64 * 64
    assert hist["lo"] <= note["level"] <= hist["hi"]
    for x, y in note["outline"]:                   # 正規化座標
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def test_meta_is_written_even_when_nothing_was_measured():
    """面板要說得出「為什麼沒有」—— 沒有 meta 的話它跟「還沒跑」長得一樣。"""
    out, _p = run_blob(canvas(64))
    note = out.meta["cd"][""]
    assert note["shape"] == SHAPE_BLOB
    assert not note["ok"] and note["reason"] == "flat"
    assert note["outline"] == [] and note["chord"] == []


def test_the_outline_becomes_marks_with_the_chord_focused():
    """**不需要任何新的 UI 原語** —— 一圈輪廓是一串線段，弦是第 N+1 條。"""
    out, p = run_blob(disc(d=20.0))
    lines, points, focus = REGISTRY[CARD].overlay_marks(out, p)
    assert len(lines) == len(points) > 3
    assert focus == len(lines) - 1                 # 弦畫成醒目的那一條
    assert len(points[focus]) == 2                 # 兩端各一個點
    assert all(points[i] == [] for i in range(focus))
    for seg in lines:
        for x, y in seg:
            assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
