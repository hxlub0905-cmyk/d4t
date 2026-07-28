"""Tests for adept.core.steps — the 14-card step library (M1).

Each test builds a synthetic Context, runs one card through
validate_params + run, and checks features / image streams / warnings.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
import tifffile

import adept.core.steps  # noqa: F401 — registration side-effect
from adept.core.ingest.dataset import DefectItem, ImageRef
from adept.core.pipeline.context import Context
from adept.core.pipeline.step import REGISTRY, StepError

# 本卡片庫全部的 key（影像段 8 張 + 算法段 6 張）
ALL_KEYS = [
    "load_patch", "percentile_norm", "glv_mask_norm", "hist_match",
    "denoise", "align", "subtract", "invert",
    "snr_map", "blob_segment", "cd_measure", "roi_snr",
    "focus_quality", "glv_stats",
]


def run_step(key, ctx, **params):
    cls = REGISTRY[key]
    return cls().run(ctx, cls.validate_params(params))


def _rng(seed=0):
    return np.random.default_rng(seed)


def _smooth_pattern(size=128, seed=3):
    """有結構的隨機影像（對位測試用：平滑過的雜訊）。"""
    base = _rng(seed).integers(0, 256, size=(size, size)).astype(np.uint8)
    return cv2.GaussianBlur(base, (7, 7), 2)


def _blob(size, cy, cx, sigma=3.0):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    return np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))


# ---------------------------------------------------------------- registry / 推廣鐵則

def test_registry_has_all_cards():
    assert set(ALL_KEYS) <= set(REGISTRY)


def test_promotion_rules_help_everywhere():
    """推廣鐵則：每張卡與每個參數都要有非空白話 help。"""
    for key in ALL_KEYS:
        d = REGISTRY[key].describe()
        assert str(d["help"]).strip(), f"{key}: card help empty"
        for pr in d["params"]:
            assert str(pr["help"]).strip(), f"{key}.{pr['name']}: param help empty"
            assert pr["default"] is not None, f"{key}.{pr['name']}: no default"


# ---------------------------------------------------------------- load_patch

@pytest.fixture()
def patch_tiff(tmp_path):
    pages = [np.full((16, 20), v, dtype=np.uint8) for v in (10, 120, 230)]
    path = tmp_path / "patches.tif"
    with tifffile.TiffWriter(str(path)) as tw:
        for arr in pages:
            tw.write(arr, photometric="minisblack")
    return str(path), pages


def test_load_patch_ebi(patch_tiff):
    path, pages = patch_tiff
    item = DefectItem(defect_id="1", die=(0, 0), xrel_nm=0.0, yrel_nm=0.0,
                      images={"test": ImageRef(path, 0, "test"),
                              "ref": ImageRef(path, 1, "ref")})
    ctx = Context(meta={"_defect_item": item, "_dataset_kind": "ebi_patch"})
    run_step("load_patch", ctx)
    assert set(ctx.images) == {"test", "ref"}
    assert ctx.images["test"].dtype == np.uint8
    assert np.array_equal(ctx.images["test"], pages[0])
    assert np.array_equal(ctx.images["ref"], pages[1])
    assert ctx.features["n_channels"] == 2.0


def test_load_patch_rsem_alias(patch_tiff):
    path, pages = patch_tiff
    item = DefectItem(defect_id="9", die=None, xrel_nm=None, yrel_nm=None,
                      images={"single": ImageRef(path, 2, "single")})
    ctx = Context(meta={"_defect_item": item, "_dataset_kind": "rsem"})
    run_step("load_patch", ctx)
    assert "single" in ctx.images and "test" in ctx.images
    assert np.array_equal(ctx.images["test"], pages[2])
    assert ctx.features["n_channels"] == 1.0
    assert any("single" in n for n in ctx.meta.get("notes", []))


def test_load_patch_explicit_and_errors(patch_tiff):
    path, pages = patch_tiff
    item = DefectItem(defect_id="1", die=None, xrel_nm=None, yrel_nm=None,
                      images={"test": ImageRef(path, 0, "test"),
                              "ref": ImageRef(path, 1, "ref")})
    ctx = Context(meta={"_defect_item": item, "_dataset_kind": "ebi_patch"})
    run_step("load_patch", ctx, channels="test")
    assert set(ctx.images) == {"test"}
    # 指定不存在的 channel → StepError
    with pytest.raises(StepError):
        run_step("load_patch", Context(meta={"_defect_item": item,
                                             "_dataset_kind": "ebi_patch"}),
                 channels="test,nope")
    # 沒有 defect item → StepError
    with pytest.raises(StepError):
        run_step("load_patch", Context())


# ---------------------------------------------------------------- percentile_norm

def _ramp(size=128):
    row = np.linspace(0, 255, size).astype(np.uint8)
    return np.tile(row, (size, 1))


def test_percentile_norm_range_and_anchor():
    src = _ramp()
    half = (src.astype(np.float32) / 2).astype(np.uint8)

    # anchor=source：other 影像用 source 的範圍 → 亮度只有一半（跨圖可比）
    ctx = Context(images={"test": src.copy(), "ref": half.copy()})
    run_step("percentile_norm", ctx, anchor="source")
    out_t, out_r = ctx.images["test"], ctx.images["ref"]
    assert out_t.dtype == np.uint8 and out_r.dtype == np.uint8
    assert out_t.min() == 0 and out_t.max() == 255       # 範圍拉滿
    assert abs(out_r.mean() - out_t.mean() / 2) < 8      # ref 保持相對亮度

    # anchor=self：各自拉自己的範圍 → 兩張平均亮度趨於一致
    ctx2 = Context(images={"test": src.copy(), "ref": half.copy()})
    run_step("percentile_norm", ctx2, anchor="self")
    assert abs(ctx2.images["ref"].mean() - ctx2.images["test"].mean()) < 8

    # also_apply 缺流：只警告不報錯
    ctx3 = Context(images={"test": src.copy()})
    run_step("percentile_norm", ctx3, also_apply="ref,ghost")
    assert len(ctx3.meta.get("warnings", [])) == 2

    # p_low >= p_high → StepError
    with pytest.raises(StepError):
        run_step("percentile_norm", Context(images={"test": src.copy()}),
                 p_low=50.0, p_high=50.0)


def test_glv_mask_norm_band_anchoring():
    img = np.full((64, 64), 100, dtype=np.uint8)
    img[10:40, 10:40] = np.linspace(150, 200, 900).reshape(30, 30).astype(np.uint8)
    ctx = Context(images={"test": img.copy()})
    run_step("glv_mask_norm", ctx, glv_low=150, glv_high=200, also_apply="")
    out = ctx.images["test"]
    assert out.dtype == np.uint8
    assert out[0, 0] == 0            # 帶外的背景被壓到 0
    assert out[10:40, 10:40].max() == 255   # 帶內像素被拉滿
    with pytest.raises(StepError):
        run_step("glv_mask_norm", Context(images={"test": img.copy()}),
                 glv_low=200, glv_high=100)


def test_hist_match_linear_means_close():
    rng = _rng(11)
    mov = np.clip(rng.normal(60, 10, (128, 128)), 0, 255).astype(np.uint8)
    ref = np.clip(rng.normal(180, 20, (128, 128)), 0, 255).astype(np.uint8)
    ctx = Context(images={"test": mov, "ref": ref})
    run_step("hist_match", ctx, method="linear")
    out = ctx.images["test"]
    assert out.dtype == np.uint8
    assert abs(float(out.mean()) - float(ref.mean())) < 2.0
    assert abs(float(out.std()) - float(ref.std())) < 2.0


# ---------------------------------------------------------------- denoise

def test_denoise_even_ksize_is_steperror():
    ctx = Context(images={"test": np.zeros((32, 32), dtype=np.uint8)})
    with pytest.raises(StepError):
        run_step("denoise", ctx, ksize=4)


def test_denoise_median_removes_salt_and_warn_missing_also():
    img = np.full((64, 64), 100, dtype=np.uint8)
    idx = _rng(2).integers(0, 64, size=(60, 2))
    img[idx[:, 0], idx[:, 1]] = 255                     # 鹽噪點
    ctx = Context(images={"test": img.copy()})
    run_step("denoise", ctx, method="median", ksize=3, also_apply="ghost")
    assert int(ctx.images["test"].max()) < 255          # 噪點被壓掉
    assert ctx.meta.get("warnings")                     # 缺流警告


# ---------------------------------------------------------------- align

def test_align_recovers_planted_shift():
    base = _smooth_pattern(128)
    dx, dy = 3, -2
    ref = np.roll(np.roll(base, dy, axis=0), dx, axis=1)  # ref(x,y)=base(x-dx,y-dy)
    ctx = Context(images={"test": base, "ref": ref})
    run_step("align", ctx)
    assert ctx.features["align_dx"] == pytest.approx(dx, abs=0.6)
    assert ctx.features["align_dy"] == pytest.approx(dy, abs=0.6)
    assert ctx.features["align_score"] > 50
    assert "ref_aligned" in ctx.images
    inner = np.s_[16:-16, 16:-16]
    err = np.abs(ctx.images["ref_aligned"][inner].astype(np.float32)
                 - base[inner].astype(np.float32))
    assert float(err.mean()) < 3.0


def test_align_flat_image_zero_shift_no_crash():
    flat = np.full((64, 64), 77, dtype=np.uint8)
    ctx = Context(images={"test": flat, "ref": flat.copy()})
    run_step("align", ctx)
    assert ctx.features["align_dx"] == 0.0
    assert ctx.features["align_dy"] == 0.0
    assert "ref_aligned" in ctx.images
    assert ctx.meta.get("warnings")


# ---------------------------------------------------------------- subtract / invert

def test_subtract_float32_with_visible_blob():
    size = 128
    pattern = _smooth_pattern(size, seed=8).astype(np.float32)
    test = np.clip(pattern + 90 * _blob(size, 64, 64, 3.0), 0, 255).astype(np.uint8)
    ref = np.clip(pattern, 0, 255).astype(np.uint8)
    ctx = Context(images={"test": test, "ref_aligned": ref})
    run_step("subtract", ctx)
    diff = ctx.images["diff"]
    assert diff.dtype == np.float32                     # diff 流是 float32
    assert float(diff[60:69, 60:69].max()) > 50         # 缺陷清楚可見
    assert float(np.median(diff)) < 5                   # 背景乾淨
    # 尺寸不合 → StepError
    with pytest.raises(StepError):
        run_step("subtract", Context(images={
            "test": np.zeros((8, 8), np.uint8),
            "ref_aligned": np.zeros((9, 9), np.uint8)}))


def test_invert_uint8():
    img = _ramp(32)
    ctx = Context(images={"test": img.copy()})
    run_step("invert", ctx)
    assert np.array_equal(ctx.images["test"], 255 - img)


# ---------------------------------------------------------------- snr_map

def _diff_pair(size=128, amp=100.0, seed=5):
    noise = np.abs(_rng(seed).normal(0, 2, (size, size))).astype(np.float32)
    clean = noise
    planted = noise + amp * _blob(size, size // 2, size // 2, 3.0).astype(np.float32)
    return planted, clean


def test_snr_map_planted_much_higher_than_clean():
    planted, clean = _diff_pair()
    ctx_p = Context(images={"diff": planted})
    ctx_c = Context(images={"diff": clean})
    run_step("snr_map", ctx_p)
    run_step("snr_map", ctx_c)
    assert ctx_p.images["snr_map"].dtype == np.float32
    assert ctx_p.features["snr_max"] > 3.0 * ctx_c.features["snr_max"]
    with pytest.raises(StepError):                      # 偶數視窗防呆
        run_step("snr_map", Context(images={"diff": planted}), window=30)


# ---------------------------------------------------------------- blob_segment

def test_blob_segment_planted_blob_features():
    planted, _ = _diff_pair()
    ctx = Context(images={"diff": planted})
    run_step("snr_map", ctx)
    run_step("blob_segment", ctx)
    assert ctx.features["blob_count"] >= 1
    assert ctx.features["blob_area"] > 0
    assert ctx.features["blob_snr"] > 0
    assert ctx.features["blob_dist_center"] < 15        # 種在中心
    blobs = ctx.meta["blobs"]
    assert isinstance(blobs, list) and isinstance(blobs[0], dict)
    for k in ("x", "y", "w", "h", "cx", "cy", "area",
              "mean_signal", "snr_value", "aspect_ratio", "dist_to_center"):
        assert k in blobs[0]


def test_blob_segment_zero_blobs_is_not_an_error():
    zeros = np.zeros((96, 96), dtype=np.float32)
    ctx = Context(images={"snr_map": zeros, "diff": zeros.copy()})
    run_step("blob_segment", ctx)
    assert ctx.meta["blobs"] == []
    for f in ("blob_count", "blob_area", "blob_aspect",
              "blob_dist_center", "blob_snr"):
        assert ctx.features[f] == 0.0


# ---------------------------------------------------------------- cd_measure

def _cd_ctx(nm_per_px=None):
    diff = np.zeros((128, 128), dtype=np.float32)
    diff[50:70, 50:60] = 80.0                           # 10 寬 × 20 高矩形
    blob = {"x": 50, "y": 50, "w": 10, "h": 20, "cx": 55.0, "cy": 60.0,
            "area": 200, "mean_signal": 0.3, "snr_value": 255.0,
            "aspect_ratio": 0.5, "dist_to_center": 10.0}
    meta = {"blobs": [blob]}
    if nm_per_px is not None:
        meta["nm_per_px"] = nm_per_px
    return Context(images={"diff": diff}, meta=meta)


def test_cd_measure_px_and_nm_paths():
    ctx = _cd_ctx()                                     # 無 nm_per_px
    run_step("cd_measure", ctx)
    assert ctx.features["cd_x_px"] == 10.0
    assert ctx.features["cd_y_px"] == 20.0
    assert ctx.features["cd_x_nm"] == 0.0
    assert ctx.features["area_nm2"] == 0.0
    assert any("nm_per_px" in w for w in ctx.meta["warnings"])

    ctx2 = _cd_ctx(nm_per_px=2.5)
    run_step("cd_measure", ctx2)
    assert ctx2.features["cd_x_nm"] == pytest.approx(25.0)
    assert ctx2.features["cd_y_nm"] == pytest.approx(50.0)
    assert ctx2.features["area_nm2"] == pytest.approx(200 * 2.5 * 2.5)


def test_cd_measure_subpixel_refine_and_fallbacks():
    ctx = _cd_ctx(nm_per_px=1.0)
    run_step("cd_measure", ctx, refine="subpixel")
    assert ctx.features["cd_y_px"] == pytest.approx(20.0, abs=2.0)
    assert ctx.features["cd_x_px"] == 10.0              # X 仍是 bbox（M1 簡化）

    # 精修影像流不存在 → 警告 + bbox
    ctx2 = _cd_ctx()
    del ctx2.images["diff"]
    run_step("cd_measure", ctx2, refine="subpixel")
    assert ctx2.features["cd_y_px"] == 20.0
    assert ctx2.meta.get("warnings")

    # 完全沒有 blob → 全 0 + 警告（不是錯誤）
    ctx3 = Context(images={"diff": np.zeros((32, 32), np.float32)})
    run_step("cd_measure", ctx3)
    assert all(ctx3.features[f] == 0.0 for f in
               ("cd_x_px", "cd_y_px", "cd_x_nm", "cd_y_nm", "area_nm2"))
    assert ctx3.meta.get("warnings")


# ---------------------------------------------------------------- roi_snr

def test_roi_snr_signed_sign_bright_vs_dark():
    size = 128
    for sign in (+1.0, -1.0):
        img = _rng(9).normal(0, 3, (size, size)).astype(np.float32)
        c0 = size // 2 - 12
        img[c0:c0 + 24, c0:c0 + 24] += sign * 60.0
        ctx = Context(images={"diff": img})
        run_step("roi_snr", ctx, mode="center", box_size=24)
        if sign > 0:
            assert ctx.features["roi_snr_signed"] > 3.0
        else:
            assert ctx.features["roi_snr_signed"] < -3.0
        assert ctx.features["roi_snr_abs"] > 3.0
        assert ctx.features["roi_contrast"] > 30.0


def test_roi_snr_blob_mode_without_blobs_warns_zero():
    ctx = Context(images={"diff": np.zeros((64, 64), np.float32)})
    run_step("roi_snr", ctx, mode="blob")
    assert ctx.features["roi_snr_signed"] == 0.0
    assert ctx.meta.get("warnings")


# ---------------------------------------------------------------- focus_quality

def test_focus_quality_sharp_vs_blurred():
    yy, xx = np.mgrid[0:128, 0:128]
    sharp = (((xx // 4 + yy // 4) % 2) * 255).astype(np.uint8)
    blurred = cv2.GaussianBlur(sharp, (9, 9), 3)
    ctx_s = Context(images={"test": sharp})
    ctx_b = Context(images={"test": blurred})
    run_step("focus_quality", ctx_s)
    run_step("focus_quality", ctx_b)
    for f in ("focus_lapvar", "focus_tenengrad", "focus_fft"):
        assert ctx_s.features[f] > ctx_b.features[f], f


# ---------------------------------------------------------------- glv_stats

def test_glv_stats_matches_numpy_including_aliases():
    img = _rng(21).integers(0, 256, size=(64, 64)).astype(np.uint8)
    ctx = Context(images={"test": img})
    run_step("glv_stats", ctx,
             metrics="glv_mean,glv_std,glv_p50,glv_q75,glv_p90,glv_min")
    f64 = img.astype(np.float64)
    assert ctx.features["glv_mean"] == pytest.approx(f64.mean())
    assert ctx.features["glv_std"] == pytest.approx(f64.std())
    assert ctx.features["glv_p50"] == pytest.approx(np.median(f64))   # 別名照列名輸出
    assert ctx.features["glv_q75"] == pytest.approx(np.percentile(f64, 75))
    assert ctx.features["glv_p90"] == pytest.approx(np.percentile(f64, 90))
    assert ctx.features["glv_min"] == pytest.approx(f64.min())

    # region=center 只取中央方框
    ctx2 = Context(images={"test": img})
    run_step("glv_stats", ctx2, region="center", box_size=16, metrics="glv_mean")
    crop = img[24:40, 24:40].astype(np.float64)
    assert ctx2.features["glv_mean"] == pytest.approx(crop.mean())

    # 未知統計項 → StepError
    with pytest.raises(StepError):
        run_step("glv_stats", Context(images={"test": img}), metrics="glv_bogus")
