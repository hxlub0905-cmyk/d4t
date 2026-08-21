"""Tests for d4t.core.steps — the 14-card step library (M1).

Each test builds a synthetic Context, runs one card through
validate_params + run, and checks features / image streams / warnings.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
import tifffile

import d4t.core.steps  # noqa: F401 — registration side-effect
from d4t.core.ingest.dataset import DefectItem, ImageRef
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import REGISTRY, StepError

# 本卡片庫全部的 key（影像段 8 張 + 算法段 6 張）
ALL_KEYS = [
    "load_patch", "normalize", "tone",
    "denoise", "align", "subtract",
    "snr_map", "cd_measure",
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


def test_load_single_gives_one_named_stream(patch_tiff):
    """單張資料走 `load_single`，而它吐**一條**流（F11 Input-4）。

    這一條以前叫 `test_load_patch_rsem_alias`，斷言的是 `load_patch` 會把
    `single` **順手鏡射一份到 `test`**。那個鏡射拿掉了：資料只有一張圖，畫布上
    卻有兩顆埠，正是使用者回報的「畫布跟實際對不起來」。
    """
    path, pages = patch_tiff
    item = DefectItem(defect_id="9", die=None, xrel_nm=None, yrel_nm=None,
                      images={"single": ImageRef(path, 2, "single")})
    ctx = Context(meta={"_defect_item": item, "_dataset_kind": "rsem"})
    run_step("load_single", ctx)
    assert set(ctx.images) == {"single"}          # 一條，不是兩條
    assert np.array_equal(ctx.images["single"], pages[2])

    # 名字是使用者的（畫布上的埠跟著改名）
    ctx2 = Context(meta={"_defect_item": item, "_dataset_kind": "rsem"})
    run_step("load_single", ctx2, out="rsem_img")
    assert set(ctx2.images) == {"rsem_img"}


def test_load_single_refuses_data_with_several_images(patch_tiff):
    """**不偷偷拿第一張**：這張卡承諾一顆一張，多張就是選錯卡。"""
    path, _pages = patch_tiff
    item = DefectItem(defect_id="1", die=None, xrel_nm=None, yrel_nm=None,
                      images={"test": ImageRef(path, 0, "test"),
                              "ref": ImageRef(path, 1, "ref")})
    ctx = Context(meta={"_defect_item": item, "_dataset_kind": "ebi_patch"})
    with pytest.raises(StepError) as e:
        run_step("load_single", ctx)
    assert "Load images" in str(e.value)          # 講得出該用哪一張卡


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


def test_percentile_norm_range_and_borrowed_range():
    """一張卡一條流（F7-18）；``range_from`` 是「兩張圖還比得起來」那條路。"""
    src = _ramp()
    half = (src.astype(np.float32) / 2).astype(np.uint8)

    # range_from=test：ref 用 test 的範圍 → 亮度只有一半（跨圖可比）
    ctx = Context(images={"test": src.copy(), "ref": half.copy()})
    run_step("normalize", ctx, streams="ref", range_from="test")
    run_step("normalize", ctx, streams="test")
    out_t, out_r = ctx.images["test"], ctx.images["ref"]
    assert out_t.dtype == np.uint8 and out_r.dtype == np.uint8
    assert out_t.min() == 0 and out_t.max() == 255       # 範圍拉滿
    assert abs(out_r.mean() - out_t.mean() / 2) < 8      # ref 保持相對亮度

    # range_from 空著：各自拉自己的範圍 → 兩張平均亮度趨於一致
    ctx2 = Context(images={"test": src.copy(), "ref": half.copy()})
    run_step("normalize", ctx2, streams="test")
    run_step("normalize", ctx2, streams="ref")
    assert abs(ctx2.images["ref"].mean() - ctx2.images["test"].mean()) < 8

    # 借不到範圍就報錯 —— 不靜靜改用自己的（輸出都是一張正常的圖，差別只在數字）
    ctx3 = Context(images={"test": src.copy()})
    with pytest.raises(StepError):
        run_step("normalize", ctx3, streams="test", range_from="ghost")

    # p_low >= p_high → StepError
    with pytest.raises(StepError):
        run_step("normalize", Context(images={"test": src.copy()}),
                 p_low=50.0, p_high=50.0)


def test_glv_mask_norm_band_anchoring():
    img = np.full((64, 64), 100, dtype=np.uint8)
    img[10:40, 10:40] = np.linspace(150, 200, 900).reshape(30, 30).astype(np.uint8)
    ctx = Context(images={"test": img.copy()})
    run_step("normalize", ctx, method="glv_band", glv_low=150, glv_high=200)
    out = ctx.images["test"]
    assert out.dtype == np.uint8
    assert out[0, 0] == 0            # 帶外的背景被壓到 0
    assert out[10:40, 10:40].max() == 255   # 帶內像素被拉滿
    with pytest.raises(StepError):
        run_step("normalize", Context(images={"test": img.copy()}), method="glv_band",
                 glv_low=200, glv_high=100)


def test_hist_match_linear_means_close():
    rng = _rng(11)
    mov = np.clip(rng.normal(60, 10, (128, 128)), 0, 255).astype(np.uint8)
    ref = np.clip(rng.normal(180, 20, (128, 128)), 0, 255).astype(np.uint8)
    ctx = Context(images={"test": mov, "ref": ref})
    run_step("normalize", ctx, method="match", match_method="linear")
    out = ctx.images["test"]
    assert out.dtype == np.uint8
    assert abs(float(out.mean()) - float(ref.mean())) < 2.0
    assert abs(float(out.std()) - float(ref.std())) < 2.0


# ---------------------------------------------------------------- denoise

def test_denoise_even_ksize_is_steperror():
    ctx = Context(images={"test": np.zeros((32, 32), dtype=np.uint8)})
    with pytest.raises(StepError):
        run_step("denoise", ctx, ksize=4)


def test_denoise_median_removes_salt_and_leaves_other_streams_alone():
    img = np.full((64, 64), 100, dtype=np.uint8)
    idx = _rng(2).integers(0, 64, size=(60, 2))
    img[idx[:, 0], idx[:, 1]] = 255                     # 鹽噪點
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    run_step("denoise", ctx, method="median", ksize=3)
    assert int(ctx.images["test"].max()) < 255          # 噪點被壓掉
    # 一張卡一條流（F7-18）：ref 沒被接進這張卡，就不該被動到。
    np.testing.assert_array_equal(ctx.images["ref"], img)


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
    ctx = Context(images={"test": test, "ref": ref})
    run_step("subtract", ctx)
    diff = ctx.images["diff"]
    assert diff.dtype == np.float32                     # diff 流是 float32
    assert float(diff[60:69, 60:69].max()) > 50         # 缺陷清楚可見
    assert float(np.median(diff)) < 5                   # 背景乾淨
    # 尺寸不合 → StepError
    with pytest.raises(StepError):
        run_step("subtract", Context(images={
            "test": np.zeros((8, 8), np.uint8),
            "ref": np.zeros((9, 9), np.uint8)}))


def test_invert_uint8():
    img = _ramp(32)
    ctx = Context(images={"test": img.copy()})
    run_step("tone", ctx, invert=True)
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


# ---------------------------------------------------------------- cd_measure

def _cd_ctx(nm_per_px=None):
    """一張含 10×20 矩形的 diff，外加一個框住它的具名 ROI。

    ROI 以前是 ``blob_segment`` 自動找出來的，那張卡在 F8 第五輪被拿掉了
    （ROI 只留 Profile / Template / GDS）。``cd_measure`` 現在量的是**你指給它
    的那個區域** —— 所以測試自己把區域放進去，量的東西一模一樣。
    """
    diff = np.zeros((128, 128), dtype=np.float32)
    diff[50:70, 50:60] = 80.0                           # 10 寬 × 20 高矩形
    meta = {} if nm_per_px is None else {"nm_per_px": nm_per_px}
    ctx = Context(images={"diff": diff}, meta=meta)
    ctx.set_roi("spot", (50 / 128.0, 50 / 128.0, 10 / 128.0, 20 / 128.0))
    return ctx


def test_cd_measure_reports_pixels_when_nobody_says_how_big_a_pixel_is():
    """**沒填 nm/px 就一個 `_nm` 都不要有**（2026-07-30 的決定，仍然成立）。

    以前這張卡在沒有 ``nm_per_px`` 時照樣吐三個 0（``cd_x_nm`` / ``cd_y_nm`` /
    ``area_nm2``），而 ``nm_per_px`` 那時候**沒有來源**，所以那三個 0 是每一顆
    的常態 —— 它們進得了分數表達式、也寫得進 DSIZE 欄。0 是個看起來很像答案
    的答案。
    """
    ctx = _cd_ctx()
    run_step("cd_measure", ctx, roi="spot")
    assert ctx.features["cd_x_px"] == 10.0
    assert ctx.features["cd_y_px"] == 20.0
    assert ctx.features["area_px"] == 200.0            # blob 的真實像素面積
    assert not [k for k in ctx.features if k.endswith(("_nm", "_nm2"))]
    assert not [w for w in ctx.meta.get("warnings", []) if "nm_per_px" in w]


def test_a_pixel_size_adds_the_nm_numbers_beside_the_pixel_ones():
    """2026-08-20：那個來源出現了 —— 使用者在 Load 卡上填的那一格。

    所以上一條測試的理由（「沒有來源，所以每一顆都是 0」）沒有被推翻，是被
    **補完**了。而補的方式是**多一組**不是換掉：同一個特徵名在不同資料上是
    不同單位的話，``score = cd_x > 50`` 這一行會在填了 nm/px 之後意思整個改變
    —— recipe 沒改、資料沒改、bin 卻不一樣，而 CSV 上看不出來。
    """
    ctx = _cd_ctx(nm_per_px=2.5)
    run_step("cd_measure", ctx, roi="spot")
    # pixel 那一份**一個字都沒變**
    assert ctx.features["cd_x_px"] == 10.0
    assert ctx.features["cd_y_px"] == 20.0
    assert ctx.features["area_px"] == 200.0
    # nm 那一份：長度乘一次，**面積乘平方**
    assert ctx.features["cd_x_nm"] == 25.0
    assert ctx.features["cd_y_nm"] == 50.0
    assert ctx.features["area_nm2"] == 200.0 * 2.5 * 2.5
    assert sorted(ctx.features) == ["area_nm2", "area_px", "cd_x_nm", "cd_x_px",
                                    "cd_y_nm", "cd_y_px"]


def test_cd_measure_can_target_a_named_region():
    """F7-4：CD 也可以量使用者畫的框，不再只能吃 meta['blobs']。"""
    img = np.zeros((64, 64), np.float32)
    ctx = Context(images={"diff": img})
    _centre_roi(ctx, "mid", 20, key="diff")
    run_step("cd_measure", ctx, roi="mid")
    assert ctx.features["cd_x_px"] == 20.0
    assert ctx.features["cd_y_px"] == 20.0


def test_cd_measure_subpixel_refine_and_fallbacks():
    ctx = _cd_ctx(nm_per_px=1.0)
    run_step("cd_measure", ctx, roi="spot", refine="subpixel")
    assert ctx.features["cd_y_px"] == pytest.approx(20.0, abs=2.0)
    assert ctx.features["cd_x_px"] == 10.0              # X 仍是 bbox（M1 簡化）




def _centre_roi(ctx, name: str, size: int, key: str = "test") -> None:
    """在 ``ctx`` 上直接放一個置中的具名 ROI。

    以前這是 ``roi_define`` 那張卡做的事，而那張卡在 F8 第五輪被拿掉了
    （ROI 只留 Profile / Template / GDS 三條路）。**這幾條測的是量測卡有沒有
    照著具名 ROI 量**，區域是誰放進去的不是重點 —— 所以直接寫進 Context，
    測試也就不再綁在某一張會被換掉的卡上。
    """
    h, w = ctx.require_image(key).shape[:2]
    ctx.set_roi(name, ((w - size) / 2.0 / w, (h - size) / 2.0 / h,
                       size / float(w), size / float(h)))


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

    # 具名 ROI 只取中央方框（F7-4：幾何從量測卡搬到 ROI 卡）
    ctx2 = Context(images={"test": img})
    _centre_roi(ctx2, "mid", 16)
    run_step("glv_stats", ctx2, roi="mid", metrics="glv_mean")
    crop = img[24:40, 24:40].astype(np.float64)
    assert ctx2.features["glv_mean"] == pytest.approx(crop.mean())

    # ROI 名字打錯 → StepError（不可以安靜地退回整張圖）
    ctx3 = Context(images={"test": img})
    with pytest.raises(StepError):
        run_step("glv_stats", ctx3, roi="typo")

    # 未知統計項 → StepError
    with pytest.raises(StepError):
        run_step("glv_stats", Context(images={"test": img}), metrics="glv_bogus")


def test_glv_stats_defaults_are_the_robust_set(tmp_path):
    """F18：新加的卡預設吐 median/MAD/min/max（以前是 mean/std/P50）。

    為什麼換得掉：`add_step` 走 ``validate_params(cleared_inputs())``，
    **每一格都會被寫進 recipe** —— 所以既有檔案帶著自己那一份 metrics，
    換掉的只有「之後新加的卡」。這一條同時鎖住那個前提：預設一旦沒有被寫進
    params，改預設就會安靜地改掉舊 recipe 的數字。
    """
    from d4t.core.pipeline.step import get_step
    from d4t.core.steps.glv_stats import DEFAULT_METRICS

    step = get_step("glv_stats")
    params = step.validate_params(step.cleared_inputs())
    assert params["metrics"] == DEFAULT_METRICS == \
        "glv_median,glv_mad,glv_min,glv_max"

    img = _rng(21).integers(0, 256, size=(48, 48)).astype(np.uint8)
    ctx = Context(images={"test": img})
    run_step("glv_stats", ctx)
    # `glv_pixels` 跟著每一塊走（F18 第 4 步）：patch 的 ROI 常常只有幾百個
    # 像素，而在那個數量下離散度本身沒有意義 —— 樣本數必須跟數字一起走。
    assert set(ctx.features) == {"glv_median", "glv_mad", "glv_min", "glv_max",
                                 "glv_pixels"}
    assert ctx.features["glv_pixels"] == 48 * 48
    f64 = img.astype(np.float64)
    assert ctx.features["glv_median"] == pytest.approx(np.median(f64))
    assert ctx.features["glv_mad"] == pytest.approx(
        np.median(np.abs(f64 - np.median(f64))))


def test_glv_stats_takes_the_shape_and_count_statistics():
    """形狀那一群要真的跑得完，而且 feature 名照使用者列的寫。"""
    img = _rng(5).integers(0, 256, size=(40, 40)).astype(np.uint8)
    ctx = Context(images={"test": img})
    run_step("glv_stats", ctx,
             metrics="glv_iqr,glv_skew,glv_kurt,glv_entropy,glv_bimodality,"
                     "glv_trim10,glv_above128,glv_sat_frac")
    assert set(ctx.features) == {
        "glv_iqr", "glv_skew", "glv_kurt", "glv_entropy", "glv_bimodality",
        "glv_trim10", "glv_above128", "glv_sat_frac", "glv_pixels"}
    assert all(np.isfinite(v) for v in ctx.features.values())

    # 數字打錯範圍的照樣是「未知統計項」，不是安靜地算出一個空集合的平均
    with pytest.raises(StepError):
        run_step("glv_stats", Context(images={"test": img}),
                 metrics="glv_trim60")


# ---------------------------------------------------------------- tone (F7-7)

def test_brightness_contrast_pivots_around_mid_gray():
    """對比以影像自己的中間值為支點 —— 以 0 為支點會順便把整張圖變亮。"""
    img = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)
    ctx = Context(images={"test": img.copy()})
    run_step("tone", ctx, contrast=2.0)
    out = ctx.images["test"]
    assert out[0, 2] == 128, "中灰是支點，不該移動"
    assert out[0, 0] == 0 and out[0, 4] == 255           # 兩端夾住
    assert int(out[0, 1]) < 64 and int(out[0, 3]) > 192  # 往兩邊拉開

    ctx2 = Context(images={"test": img.copy()})
    run_step("tone", ctx2, brightness=20.0)
    assert int(ctx2.images["test"][0, 2]) == 148
    assert ctx2.images["test"].dtype == np.uint8, "uint8 進 uint8 出"


def test_gamma_opens_up_dark_detail_and_is_reversible_at_one():
    img = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)

    ctx = Context(images={"test": img.copy()})
    run_step("tone", ctx, gamma=1.0)
    np.testing.assert_array_equal(ctx.images["test"], img)   # 1 = 不動

    ctx = Context(images={"test": img.copy()})
    run_step("tone", ctx, gamma=0.5)
    assert int(ctx.images["test"][0, 1]) < 64, "gamma<1 要壓暗部（拉開細節）"

    ctx = Context(images={"test": img.copy()})
    run_step("tone", ctx, gamma=2.0)
    assert int(ctx.images["test"][0, 1]) > 64
    # 端點永遠不動
    assert int(ctx.images["test"][0, 0]) == 0
    assert int(ctx.images["test"][0, 4]) == 255


def test_tone_cards_keep_float_streams_float_and_only_touch_their_own():
    """diff 是 float32 —— 這兩張卡插在哪裡都不該偷偷改變型別。

    順便鎖住 F7-18 的約定：**一張卡一條流**。要 test 與 ref 一起動，就放兩張卡
    （畫布上因此看得到兩條各自的鏈），而不是一張卡偷偷寫了兩條流。
    """
    f = np.linspace(-5.0, 5.0, 25, dtype=np.float32).reshape(5, 5)
    ctx = Context(images={"test": f.copy(), "ref": f.copy()})
    run_step("tone", ctx, gamma=0.7)
    assert ctx.images["test"].dtype == np.float32
    assert ctx.images["ref"].dtype == np.float32
    np.testing.assert_allclose(ctx.images["ref"], f)     # ref 沒被接進來

    run_step("tone", ctx, streams="ref", gamma=0.7)      # 第二張卡做 ref
    np.testing.assert_allclose(ctx.images["test"], ctx.images["ref"])

    # 指到不存在的流 -> 白話 StepError（不是靜靜跳過）
    ctx2 = Context(images={"test": f.copy()})
    with pytest.raises(StepError):
        run_step("tone", ctx2, streams="nope")


def test_glv_stats_can_say_which_pixels_count(tmp_path):
    """F18 第 4 步：三個旋鈕決定哪些像素算數，**而它們預設全部不作用**。

    預設是不是 no-op 不是風格問題：既有 recipe 的 JSON 裡沒有這幾個鍵，
    `validate_params` 會補上預設值 —— 一個會動的預設 = 安靜地改掉每一份舊
    recipe 的數字。這一條把那件事鎖起來。
    """
    img = _rng(2).integers(60, 180, size=(30, 30)).astype(np.uint8)
    img[0, 0] = 255
    img[0, 1] = 0
    mids = "glv_mean,glv_min,glv_max,glv_sat_frac"

    plain = Context(images={"test": img})
    run_step("glv_stats", plain, metrics=mids)
    assert plain.features["glv_min"] == 0.0 and plain.features["glv_max"] == 255.0
    assert plain.features["glv_pixels"] == 900.0
    assert "glv_ok" not in plain.features, \
        "沒設下限的時候 glv_ok 恆為 1，而一整欄的 1 是雜訊"

    # 丟掉貼在 0/255 的：min/max 收進來，但**飽和比例照樣量原始的那一份**
    # （丟掉之後再問「有多少貼在邊上」，答案恆為 0 —— 那是個沒有用的答案）
    clean = Context(images={"test": img})
    run_step("glv_stats", clean, metrics=mids, exclude_saturated=True)
    assert clean.features["glv_min"] > 0.0 and clean.features["glv_max"] < 255.0
    assert clean.features["glv_pixels"] == 898.0
    assert clean.features["glv_sat_frac"] == pytest.approx(2.0 / 900.0)

    # 兩端各修 5%：留下來的像素變少，全距一定不會變大
    trimmed = Context(images={"test": img})
    run_step("glv_stats", trimmed, metrics=mids, trim_percent=5.0)
    assert trimmed.features["glv_pixels"] < 900.0
    assert (trimmed.features["glv_max"] - trimmed.features["glv_min"]
            <= plain.features["glv_max"] - plain.features["glv_min"])


def test_glv_stats_writes_nothing_rather_than_a_wrong_number_when_too_thin():
    """量不出來的時候**那幾格不寫** —— 不是 0，也不是 NaN。

    三種都想過（`GlvStatsStep._too_thin` 的表）：0 會安靜地混進分數表達式；
    NaN 更糟，因為 ``NaN < threshold`` 是 False，那顆 defect 會被安靜地判成
    真缺陷（`tests/test_card_invariants.py` 的 I5 守著這件事）。不寫的話，
    沒有人引用就什麼都不會發生，有人引用就當場失敗並指名那個變數。

    而且不能用 raise：鐵則 7（單顆出錯不得殺掉整批）。
    """
    img = _rng(9).integers(0, 256, size=(20, 20)).astype(np.uint8)
    ctx = Context(images={"test": img})
    run_step("glv_stats", ctx, metrics="glv_mean,glv_std", min_pixels=5000)

    assert "glv_mean" not in ctx.features and "glv_std" not in ctx.features
    assert ctx.features["glv_ok"] == 0.0, "分數表達式要有一個乾淨的分支點"
    assert ctx.features["glv_pixels"] == 400.0, "樣本數本身還是要說得出來"
    assert all(not np.isnan(v) for v in ctx.features.values())

    ok = Context(images={"test": img})
    run_step("glv_stats", ok, metrics="glv_mean", min_pixels=100)
    assert ok.features["glv_ok"] == 1.0
    assert not np.isnan(ok.features["glv_mean"])


def test_gray_level_is_the_only_card_that_makes_an_snr_number():
    """`roi_snr` 那張卡刪掉之後，SNR 只剩一個出處（2026-08-21 使用者要求）。

    以前卡片庫裡有一張卡就叫 `SNR`（ROI 對周邊 margin 背景），而 Gray level
    也吐 `snr`（對使用者接的那一塊）—— 兩個名字一樣、分母不同。使用者：
    「原來的 SNR 那張卡請幫我拿掉整個程式碼刪掉避免混淆」。

    Z-map（`snr_map`）留著，但它吐的是一張**圖**，不是一個數字。
    """
    from d4t.core.pipeline.step import REGISTRY

    assert "roi_snr" not in REGISTRY
    from d4t.core.algo import snr as algo_snr
    assert not hasattr(algo_snr, "roi_snr"), "卡片走了，它的算法也不留著"
    assert hasattr(algo_snr, "compute_snr_map"), "Z-map 還要用"
    assert hasattr(algo_snr, "snr_signed"), "帶正負號慣例的規範出處"

    # 搜尋「snr」要找得到現在真的產出它的那張卡
    assert "SNR" in REGISTRY["glv_stats"].help
