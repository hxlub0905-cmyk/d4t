"""Tests for the M4-1 Golden Cell cards: ``cell_period`` + ``golden_cell``.

沒有 ref 影像的資料（Review SEM 單張）靠這兩張卡自己造參考圖：
量週期 → 疊 cell → 鋪回原尺寸 → 下游 subtract 照跑。
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

import adept.core.steps  # noqa: F401 — registration side-effect
from adept.core.pipeline.context import Context
from adept.core.pipeline.step import REGISTRY, StepError

PITCH = 16
DEFECT = (slice(70, 80), slice(100, 112))   # 種進去的缺陷位置（y, x）


def run_step(key, ctx, **params):
    cls = REGISTRY[key]
    return cls().run(ctx, cls.validate_params(params))


def _cell_tile(pitch: int = PITCH) -> np.ndarray:
    c = np.zeros((pitch, pitch), np.float64)
    cv2.rectangle(c, (3, 3), (pitch - 6, pitch - 6), 210, -1)
    c[pitch - 4:pitch - 2, 2:5] = 120
    return cv2.GaussianBlur(c, (3, 3), 0.9) + 35.0


def _clean_lattice(h=256, w=256, pitch=PITCH, crop=0, seed=0, noise=3.0):
    tile = _cell_tile(pitch)
    big = np.tile(tile, (h // pitch + 3, w // pitch + 3))
    img = big[crop:crop + h, crop:crop + w]
    img = img + np.random.default_rng(seed).normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def clean():
    return _clean_lattice()


@pytest.fixture(scope="module")
def defective(clean):
    """同一張週期影像，但其中一格被種了一個亮缺陷。"""
    img = clean.copy()
    img[DEFECT] = 255
    return img


def _noise_image():
    return np.random.default_rng(1).integers(0, 256, (128, 128)).astype(np.uint8)


# ---------------------------------------------------------------- cell_period

def test_cell_period_recovers_pitch_and_fills_meta(defective):
    ctx = Context(images={"test": defective})
    run_step("cell_period", ctx)
    assert abs(ctx.features["cell_px"] - PITCH) <= 1
    assert abs(ctx.features["cell_py"] - PITCH) <= 1
    assert ctx.features["cell_conf_x"] > 50 and ctx.features["cell_conf_y"] > 50
    assert ctx.meta["cell_period"] == {"px": int(ctx.features["cell_px"]),
                                       "py": int(ctx.features["cell_py"])}
    assert not ctx.meta.get("warnings")


def test_cell_period_without_refine_also_works(defective):
    ctx = Context(images={"test": defective})
    run_step("cell_period", ctx, refine=False)
    assert abs(ctx.features["cell_px"] - PITCH) <= 1
    assert abs(ctx.features["cell_py"] - PITCH) <= 1


def test_cell_period_on_non_periodic_warns_but_does_not_raise():
    """沒有週期性不是錯誤：回零 + 白話警告。"""
    ctx = Context(images={"test": _noise_image()})
    run_step("cell_period", ctx)
    assert ctx.features["cell_px"] == 0.0 and ctx.features["cell_py"] == 0.0
    assert ctx.meta["cell_period"] == {"px": 0, "py": 0}
    warns = ctx.meta.get("warnings") or []
    assert any("no periodic structure" in w for w in warns), warns


def test_cell_period_rejects_inverted_bounds(defective):
    ctx = Context(images={"test": defective})
    with pytest.raises(StepError):
        run_step("cell_period", ctx, min_period=32, max_period=8)


# ---------------------------------------------------------------- golden_cell

def test_golden_cell_shape_matches_source_and_defect_is_attenuated(clean, defective):
    ctx = Context(images={"test": defective})
    run_step("cell_period", ctx)
    run_step("golden_cell", ctx, method="median")

    golden = ctx.images["ref"]
    assert golden.shape == defective.shape        # 下游 subtract 要求 shape 完全相同
    assert golden.dtype == defective.dtype

    ref = clean.astype(np.float64)
    resid_golden = float(np.abs(golden[DEFECT].astype(np.float64) - ref[DEFECT]).mean())
    resid_source = float(np.abs(defective[DEFECT].astype(np.float64) - ref[DEFECT]).mean())
    # 缺陷被其他 cell 的中位數洗掉：殘差要小一個量級以上
    assert resid_golden < 0.1 * resid_source
    # 而且整張圖都要像乾淨版圖，不是只有缺陷處剛好對上
    assert float(np.abs(golden.astype(np.float64) - ref).mean()) < 10.0

    assert ctx.features["golden_px"] == pytest.approx(PITCH, abs=1)
    assert ctx.features["golden_py"] == pytest.approx(PITCH, abs=1)
    assert 0.0 <= ctx.features["golden_ghost"] <= 100.0


def test_golden_cell_uses_cell_period_meta_without_reestimating(defective):
    """meta 有週期就直接用（這裡塞一個明顯不同的值來證明它真的被讀了）。"""
    ctx = Context(images={"test": defective}, meta={"cell_period": {"px": 32, "py": 32}})
    run_step("golden_cell", ctx)
    assert (ctx.features["golden_px"], ctx.features["golden_py"]) == (32.0, 32.0)


def test_golden_cell_explicit_params_win_over_meta(defective):
    ctx = Context(images={"test": defective}, meta={"cell_period": {"px": 32, "py": 32}})
    run_step("golden_cell", ctx, px=PITCH, py=PITCH)
    assert (ctx.features["golden_px"], ctx.features["golden_py"]) == (16.0, 16.0)


def test_golden_cell_standalone_estimates_period_itself(defective):
    ctx = Context(images={"test": defective})
    run_step("golden_cell", ctx)
    assert ctx.features["golden_px"] == pytest.approx(PITCH, abs=1)
    assert ctx.meta["golden_cell"]["n_cells"] > 4


def test_phase_search_beats_no_phase_search_on_misaligned_crop():
    """刻意錯開相位的裁切圖：開相位搜尋要疊得更清晰（lap_var 更高）。"""
    img = _clean_lattice(crop=5)
    got = {}
    for flag in (True, False):
        ctx = Context(images={"test": img})
        run_step("golden_cell", ctx, method="mean", px=PITCH, py=PITCH,
                 phase_search=flag)
        got[flag] = (ctx.meta["golden_cell"], ctx.features["golden_ghost"])

    assert got[False][0]["ox"] == 0 and got[False][0]["oy"] == 0
    assert got[True][0]["ox"] != 0 or got[True][0]["oy"] != 0
    assert got[True][0]["lap_var"] > 1.2 * got[False][0]["lap_var"]
    assert got[True][1] >= got[False][1]


def test_golden_cell_output_stream_is_subtractable(defective):
    """走完整條路：golden_cell 寫 ref → subtract 直接吃得下，缺陷留在 diff 上。"""
    ctx = Context(images={"test": defective})
    run_step("golden_cell", ctx)
    run_step("subtract", ctx, a="test", b="ref")
    diff = ctx.images["diff"]
    assert diff.shape == defective.shape
    assert float(diff[DEFECT].mean()) > 5.0 * float(diff.mean())


def test_golden_cell_custom_out_key(defective):
    ctx = Context(images={"test": defective})
    run_step("golden_cell", ctx, out="golden")
    assert "golden" in ctx.images and "ref" not in ctx.images


def test_golden_cell_ghost_warn_fires(defective):
    ctx = Context(images={"test": defective})
    run_step("golden_cell", ctx, ghost_warn=100.0)   # 不可能達到的門檻
    warns = ctx.meta.get("warnings") or []
    assert any("looks blurred" in w for w in warns), warns


def test_golden_cell_float_source_keeps_scale(clean):
    """float32 0–1 的影像流進來，出去也要是 0–1 的 float32（否則 subtract 差 255 倍）。"""
    src = (clean.astype(np.float32) / 255.0)
    ctx = Context(images={"test": src})
    run_step("golden_cell", ctx)
    out = ctx.images["ref"]
    assert out.shape == src.shape and out.dtype == np.float32
    assert 0.0 <= float(out.min()) and float(out.max()) <= 1.5


# ---------------------------------------------------------------- 防呆

def test_golden_cell_on_non_periodic_raises_helpful_error():
    ctx = Context(images={"test": _noise_image()})
    with pytest.raises(StepError) as ei:
        run_step("golden_cell", ctx)
    msg = str(ei.value)
    assert "cell" in msg and "period" in msg
    assert "ref" in msg or "比對路線" in msg      # 要告訴使用者改走哪條路


def test_golden_cell_period_larger_than_image_raises(defective):
    ctx = Context(images={"test": defective[:40, :40]})
    with pytest.raises(StepError) as ei:
        run_step("golden_cell", ctx, px=64, py=64)
    assert "larger than the image" in str(ei.value)


def test_golden_cell_too_few_cells_raises(defective):
    ctx = Context(images={"test": defective[:24, :24]})
    with pytest.raises(StepError) as ei:
        run_step("golden_cell", ctx, px=20, py=20)
    assert "complete cell(s)" in str(ei.value)


# ---------------------------------------------------------------- 推廣鐵則

@pytest.mark.parametrize("key", ["cell_period", "golden_cell"])
def test_promotion_rules_help_everywhere(key):
    d = REGISTRY[key].describe()
    assert str(d["help"]).strip(), f"{key}: card help empty"
    assert str(d["label"]).strip()
    for pr in d["params"]:
        assert str(pr["help"]).strip(), f"{key}.{pr['name']}: param help empty"
        assert pr["default"] is not None, f"{key}.{pr['name']}: no default"
        if pr["type"] in ("int", "float"):
            assert pr["min"] is not None and pr["max"] is not None, \
                f"{key}.{pr['name']}: 數值參數要有 min/max 護欄"


def test_golden_cell_does_not_require_ref():
    assert REGISTRY["golden_cell"].requires_ref is False
    assert REGISTRY["golden_cell"].resolve_writes({}) == ["ref"]
