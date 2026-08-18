# pattern_ref —— 從重複 pattern 疊出一張 ref（M4-1 的 golden_cell 改名重生）。
"""沒有 ref 影像的資料（Review SEM 單張）靠這一張卡自己造參考圖：
量週期 → 疊 cell → 鋪回原尺寸 → 下游 subtract 照跑。

**這一份是 `tests/test_golden_step.py` 的下半（`golden_cell` 那一半）。**
上半（`cell_period`）跟著那張卡一起刪掉了（2026-08-18，使用者：「不需要這功能」），
於是週期的來源只剩「參數填死」與「自己估」兩條，而那兩條這裡都測。

改名之後仍然逐位元組相同這件事**不在這一份**，在黃金值：
`tests/fixtures/golden/dual_route_basic__make_sample_rsem.json` 的 6 顆，
除了三個 feature 換了名字之外每一個數字都跟改名前一樣（2026-08-18 對過）。
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


# ---------------------------------------------------------------- 疊出 ref

def test_pattern_ref_shape_matches_source_and_defect_is_attenuated(clean, defective):
    ctx = Context(images={"test": defective})
    run_step("pattern_ref", ctx, method="median")

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

    assert ctx.features["ref_px"] == pytest.approx(PITCH, abs=1)
    assert ctx.features["ref_py"] == pytest.approx(PITCH, abs=1)
    assert 0.0 <= ctx.features["ref_sharpness"] <= 100.0


def test_the_repeat_size_can_be_typed_in(defective):
    """使用者知道版圖 pitch 的時候，參數贏過自動量測。

    以前這一條問的是「meta 裡的週期會不會被讀到」（`cell_period` 卡寫的）。
    那張卡刪掉之後 meta 那條路也一起拿掉了 —— 現在只剩兩個來源，而**參數要贏**
    是其中唯一有優先順序的一條。
    """
    ctx = Context(images={"test": defective})
    run_step("pattern_ref", ctx, px=32, py=32)
    assert (ctx.features["ref_px"], ctx.features["ref_py"]) == (32.0, 32.0)


def test_pattern_ref_standalone_estimates_period_itself(defective):
    ctx = Context(images={"test": defective})
    run_step("pattern_ref", ctx)
    assert ctx.features["ref_px"] == pytest.approx(PITCH, abs=1)
    assert ctx.meta["pattern_ref"]["n_cells"] > 4


def test_phase_search_beats_no_phase_search_on_misaligned_crop():
    """刻意錯開相位的裁切圖：開相位搜尋要疊得更清晰（lap_var 更高）。"""
    img = _clean_lattice(crop=5)
    got = {}
    for flag in (True, False):
        ctx = Context(images={"test": img})
        run_step("pattern_ref", ctx, method="mean", px=PITCH, py=PITCH,
                 phase_search=flag)
        got[flag] = (ctx.meta["pattern_ref"], ctx.features["ref_sharpness"])

    assert got[False][0]["ox"] == 0 and got[False][0]["oy"] == 0
    assert got[True][0]["ox"] != 0 or got[True][0]["oy"] != 0
    assert got[True][0]["lap_var"] > 1.2 * got[False][0]["lap_var"]
    assert got[True][1] >= got[False][1]


def test_pattern_ref_output_stream_is_subtractable(defective):
    """走完整條路：pattern_ref 寫 ref → subtract 直接吃得下，缺陷留在 diff 上。"""
    ctx = Context(images={"test": defective})
    run_step("pattern_ref", ctx)
    run_step("subtract", ctx, a="test", b="ref")
    diff = ctx.images["diff"]
    assert diff.shape == defective.shape
    assert float(diff[DEFECT].mean()) > 5.0 * float(diff.mean())


def test_pattern_ref_custom_out_key(defective):
    ctx = Context(images={"test": defective})
    run_step("pattern_ref", ctx, out="golden")
    assert "golden" in ctx.images and "ref" not in ctx.images


def test_pattern_ref_ghost_warn_fires(defective):
    ctx = Context(images={"test": defective})
    run_step("pattern_ref", ctx, sharp_warn=100.0)   # 不可能達到的門檻
    warns = ctx.meta.get("warnings") or []
    assert any("came out blurred" in w for w in warns), warns


def test_pattern_ref_float_source_keeps_scale(clean):
    """float32 0–1 的影像流進來，出去也要是 0–1 的 float32（否則 subtract 差 255 倍）。"""
    src = (clean.astype(np.float32) / 255.0)
    ctx = Context(images={"test": src})
    run_step("pattern_ref", ctx)
    out = ctx.images["ref"]
    assert out.shape == src.shape and out.dtype == np.float32
    assert 0.0 <= float(out.min()) and float(out.max()) <= 1.5


# ---------------------------------------------------------------- 防呆

def test_pattern_ref_on_non_periodic_raises_helpful_error():
    ctx = Context(images={"test": _noise_image()})
    with pytest.raises(StepError) as ei:
        run_step("pattern_ref", ctx)
    msg = str(ei.value)
    assert "no repeating pattern found" in msg
    # 要告訴使用者改走哪一條路，而且**兩條都給**（換比對方式、或自己填週期）
    assert "real ref image" in msg and "type the repeat size" in msg


def test_pattern_ref_period_larger_than_image_raises(defective):
    ctx = Context(images={"test": defective[:40, :40]})
    with pytest.raises(StepError) as ei:
        run_step("pattern_ref", ctx, px=64, py=64)
    assert "larger than the image" in str(ei.value)


def test_pattern_ref_too_few_cells_raises(defective):
    ctx = Context(images={"test": defective[:24, :24]})
    with pytest.raises(StepError) as ei:
        run_step("pattern_ref", ctx, px=20, py=20)
    assert "complete repeat(s)" in str(ei.value)


# ---------------------------------------------------------------- 推廣鐵則

@pytest.mark.parametrize("key", ["pattern_ref"])
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


def test_pattern_ref_does_not_require_ref():
    assert REGISTRY["pattern_ref"].requires_ref is False
    assert REGISTRY["pattern_ref"].resolve_writes({}) == ["ref"]


# ---------------------------------------------------------------- 改名
def test_the_name_does_not_say_golden_or_cell_anywhere_the_user_looks():
    """使用者：「那可能要拿回來 不過要改名字 不然會誤會」。

    會誤會的是 Template 卡 —— 它的設定對話框裡也在疊 golden cell（同一支
    `algo/golden.py`），於是畫面上兩個地方同名，看起來像同一個功能做了兩次。
    所以**使用者看得到的每一處**都不准再出現那兩個字：卡片名、說明、參數名、
    參數說明，以及它寫出來的 feature 名（那些會被打進分數表達式）。

    演算法那一層不在此限（`algo/golden.py` 是 vendored 的模組名）。
    """
    d = REGISTRY["pattern_ref"].describe()
    surfaces = [d["label"], d["help"]]
    for pr in d["params"]:
        surfaces += [pr["name"], str(pr.get("label") or ""), pr["help"]]
    surfaces += list(REGISTRY["pattern_ref"].features_out)
    for text in surfaces:
        low = str(text).lower()
        assert "golden" not in low, text
        assert "cell" not in low, text


def test_an_old_recipe_that_says_golden_cell_still_opens():
    """鐵則 9：判準是**舊東西在不在**，而且分數表達式也要跟著換。

    只換卡片的 key 不換 feature 名，等於只搬了一半 —— 舊 recipe 打開來會是
    一條 `unknown-feature` 警告加一個算不出來的分數，而那個分數正是這份
    recipe 存在的理由。
    """
    from adept.core.pipeline import Recipe

    r = Recipe.from_json_dict({
        "recipe_id": "old", "version": 1,
        "routes": {"rsem": ["g"]},
        "nodes": {"g": {"step": "golden_cell",
                        "params": {"source": "test", "out": "ref",
                                   "method": "median"},
                        "enabled": True}},
        "edges": [],
        "score": {"expr": "golden_ghost - golden_px + my_golden_px_ratio",
                  "threshold": 1.0, "bins": {"below": 0, "above": 1}},
    })
    assert r.nodes["g"].step == "pattern_ref"
    assert r.nodes["g"].params["method"] == "median"      # 參數原封不動
    # 只換整個識別字，不做子字串取代
    assert r.score.expr == "ref_sharpness - ref_px + my_golden_px_ratio"
    # 換完之後仍然是 identity（`run_batch` 靠這個把 recipe 送進 worker）
    assert Recipe.from_json_dict(r.to_json_dict()).to_json_dict() \
        == r.to_json_dict()
