"""缺陷疊圖渲染（M5-1）：形狀 / dtype / 紅框 / [test | diff] 並排 / 標籤。

疊圖是「使用者看得懂機器在想什麼」的唯一介面，所以這裡連
「標籤塞中文會不會炸」都要測 —— cv2 的內建字型沒有 CJK 字元，
:mod:`d4t.core.export.overlay` 會把非 ASCII 換成 ``?`` 而不是丟例外。
"""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.export import overlay
from d4t.core.export.klarf_out import ExportError

H = W = 64


def flat(value=100, h=H, w=W):
    return np.full((h, w), value, np.uint8)


# ---------------------------------------------------------------------------
# 基本形狀 / dtype
# ---------------------------------------------------------------------------
def test_single_panel_shape_and_dtype():
    out = overlay.render_overlay({"test": flat()}, {})
    assert out.shape == (H, W, 3)
    assert out.dtype == np.uint8


def test_rsem_single_channel_is_accepted():
    out = overlay.render_overlay({"single": flat()}, {})
    assert out.shape == (H, W, 3)


def test_base_priority_test_beats_single():
    images = {"single": flat(0), "test": flat(255)}
    out = overlay.render_overlay(images, {})
    assert int(out[0, 0, 0]) == 255


def test_explicit_base_key():
    out = overlay.render_overlay({"test": flat(0), "ref": flat(200)}, {},
                                 base_key="ref")
    assert int(out[0, 0, 0]) == 200


def test_missing_base_key_raises_with_available_list():
    with pytest.raises(ExportError) as ei:
        overlay.render_overlay({"test": flat()}, {}, base_key="nope")
    assert "nope" in str(ei.value) and "test" in str(ei.value)


def test_empty_images_raises():
    with pytest.raises(ExportError):
        overlay.render_overlay({}, {})


def test_float_image_is_stretched_to_uint8():
    arr = np.linspace(-2.0, 5.0, H * W).reshape(H, W).astype(np.float32)
    out = overlay.render_overlay({"test": arr}, {})
    assert out.dtype == np.uint8
    assert int(out.min()) == 0 and int(out.max()) == 255


def test_constant_float_image_does_not_divide_by_zero():
    out = overlay.render_overlay({"test": np.full((H, W), 3.5, np.float32)}, {})
    assert out.shape == (H, W, 3)
    assert int(out.max()) == 0


def test_rgb_input_passes_through():
    rgb = np.zeros((H, W, 3), np.uint8)
    rgb[..., 0] = 200
    out = overlay.render_overlay({"test": rgb}, {})
    assert tuple(int(v) for v in out[0, 0]) == (200, 0, 0)


# ---------------------------------------------------------------------------
# 紅框
# ---------------------------------------------------------------------------
def test_blob_box_changes_pixels_at_the_bbox_edge():
    """框畫在 blob 的邊界上：邊界像素變紅、框內遠離邊界的像素不動。"""
    base = {"test": flat(100)}
    plain = overlay.render_overlay(base, {})
    blobs = [{"x": 16, "y": 16, "w": 20, "h": 20, "snr_value": 9.0, "area": 40}]
    boxed = overlay.render_overlay(base, {}, blobs=blobs)

    assert boxed.shape == plain.shape
    assert not np.array_equal(plain, boxed)

    # 邊框四個邊都被畫到
    for y, x in [(16, 20), (35, 20), (20, 16), (20, 35)]:
        assert tuple(int(v) for v in boxed[y, x]) == overlay.BOX_COLOR, (y, x)
    # 框的正中央沒被塗掉
    assert tuple(int(v) for v in boxed[25, 25]) == (100, 100, 100)
    # 框外也沒被塗掉
    assert tuple(int(v) for v in boxed[50, 50]) == (100, 100, 100)


def test_explicit_box_overrides_blobs():
    blobs = [{"x": 0, "y": 0, "w": 4, "h": 4, "snr_value": 9.0}]
    out = overlay.render_overlay({"test": flat()}, {}, blobs=blobs,
                                 box=(30, 30, 10, 10))
    assert tuple(int(v) for v in out[30, 35]) == overlay.BOX_COLOR
    assert tuple(int(v) for v in out[0, 2]) != overlay.BOX_COLOR


def test_primary_blob_is_the_strongest_snr():
    blobs = [
        {"x": 4, "y": 4, "w": 6, "h": 6, "snr_value": 1.0},
        {"x": 30, "y": 30, "w": 8, "h": 8, "snr_value": 9.0},
        {"x": 50, "y": 50, "w": 6, "h": 6, "snr_value": 3.0},
    ]
    assert overlay.primary_blob_box(blobs) == (30, 30, 8, 8)
    out = overlay.render_overlay({"test": flat()}, {}, blobs=blobs)
    assert tuple(int(v) for v in out[30, 34]) == overlay.BOX_COLOR
    assert tuple(int(v) for v in out[4, 6]) != overlay.BOX_COLOR


def test_box_from_features_when_no_blobs():
    feats = {"blob_x": 20, "blob_y": 20, "blob_w": 10, "blob_h": 10}
    assert overlay.primary_blob_box(None, feats) == (20, 20, 10, 10)
    out = overlay.render_overlay({"test": flat()}, feats)
    assert tuple(int(v) for v in out[20, 25]) == overlay.BOX_COLOR


def test_box_outside_image_is_clipped_not_crashing():
    out = overlay.render_overlay({"test": flat()}, {}, box=(60, 60, 999, 999))
    assert out.shape == (H, W, 3)
    assert tuple(int(v) for v in out[63, 63]) == overlay.BOX_COLOR


def test_no_blobs_means_no_box():
    plain = overlay.render_overlay({"test": flat()}, {})
    assert np.array_equal(plain, np.dstack([flat()] * 3))


def test_an_object_with_xywh_attributes_is_accepted():
    """overlay 吃 dict **也**吃有 x/y/w/h 屬性的物件（`_blob_box` 兩條路）。

    這條以前是 import `algo.blob.DefectROI` 來驗的。那個模組已於 2026-08-17
    移除（Phase 2 要重寫 blob 分割，見 `docs/plans/F11-phase2-features.md`
    §7.1），所以這裡改用一個最小的替身 —— **要驗的本來就是 overlay 的
    duck typing，不是那個 dataclass 長什麼樣**。之後重寫的 Blob 卡如果吐
    dataclass 而不是 dict，這條就是它接得上 overlay 的保證。
    """
    class _Blob:
        x, y, w, h = 10, 12, 8, 6
        snr_value = 5.0
        area = 48

    assert overlay.primary_blob_box([_Blob()]) == (10, 12, 8, 6)


# ---------------------------------------------------------------------------
# 並排（montage）
# ---------------------------------------------------------------------------
def test_montage_width_is_double_when_diff_present():
    images = {"test": flat(100), "diff": flat(30)}
    out = overlay.render_overlay(images, {})
    assert out.shape == (H, 2 * W, 3)
    assert int(out[0, 0, 0]) == 100                # 左：test
    assert int(out[0, W + 5, 0]) == 30             # 右：diff


def test_montage_can_be_disabled():
    images = {"test": flat(100), "diff": flat(30)}
    out = overlay.render_overlay(images, {}, montage=False)
    assert out.shape == (H, W, 3)


def test_montage_resizes_mismatched_diff():
    images = {"test": flat(100), "diff": flat(30, h=32, w=32)}
    out = overlay.render_overlay(images, {})
    assert out.shape == (H, 2 * W, 3)


def test_montage_draws_box_on_both_panels():
    images = {"test": flat(100), "diff": flat(30)}
    out = overlay.render_overlay(images, {}, box=(20, 20, 10, 10))
    assert tuple(int(v) for v in out[20, 25]) == overlay.BOX_COLOR
    assert tuple(int(v) for v in out[20, W + 25]) == overlay.BOX_COLOR


def test_diff_only_context_does_not_montage_itself():
    """只有 diff 時它就是底圖，不該和自己並排。"""
    out = overlay.render_overlay({"diff": flat(50)}, {})
    assert out.shape == (H, W, 3)


# ---------------------------------------------------------------------------
# 標籤
# ---------------------------------------------------------------------------
def test_label_is_drawn_top_left():
    plain = overlay.render_overlay({"test": flat(200)}, {})
    labelled = overlay.render_overlay({"test": flat(200)}, {}, label="score=3.21")
    assert labelled.shape == plain.shape
    assert not np.array_equal(plain[:16], labelled[:16])   # 左上角有變化
    assert np.array_equal(plain[40:], labelled[40:])       # 下半部沒被動到


def test_unicode_label_does_not_crash():
    """cv2 的字型沒有中日韓字元 —— 換成 '?' 畫出來，不准丟例外。"""
    for text in ("分數 3.21 / bin 1 真缺陷", "スコア", "점수", "α β γ", "🙂"):
        out = overlay.render_overlay({"test": flat()}, {}, label=text)
        assert out.shape == (H, W, 3)
        assert out.dtype == np.uint8


def test_empty_label_is_a_no_op():
    plain = overlay.render_overlay({"test": flat(200)}, {})
    assert np.array_equal(plain, overlay.render_overlay(
        {"test": flat(200)}, {}, label="   "))


def test_label_defaults_to_score_from_features():
    plain = overlay.render_overlay({"test": flat(200)}, {})
    auto = overlay.render_overlay({"test": flat(200)}, {"score": 3.21})
    assert not np.array_equal(plain, auto)


def test_label_on_tiny_image_does_not_crash():
    out = overlay.render_overlay({"test": flat(100, h=8, w=8)}, {},
                                 label="score=1.0")
    assert out.shape == (8, 8, 3)


# ---------------------------------------------------------------------------
# write_png
# ---------------------------------------------------------------------------
def test_write_png_roundtrip_and_atomic(tmp_path):
    import cv2

    arr = overlay.render_overlay({"test": flat(120), "diff": flat(30)}, {},
                                 box=(10, 10, 8, 8), label="score=1.00")
    path = tmp_path / "sub" / "o.png"
    out = overlay.write_png(arr, str(path))
    assert out == str(path)
    assert path.exists()
    assert not (tmp_path / "sub" / "o.png.tmp").exists()      # atomic

    back = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    back = cv2.cvtColor(back, cv2.COLOR_BGR2RGB)
    assert back.shape == arr.shape
    assert np.array_equal(back, arr)                          # PNG 無失真


def test_write_png_accepts_gray_array(tmp_path):
    path = tmp_path / "g.png"
    overlay.write_png(flat(77), str(path))
    assert path.exists()


# ---------------------------------------------------------------------------
# 與 pipeline 的實際串接
# ---------------------------------------------------------------------------
def test_renders_from_a_real_context_images_dict():
    """直接吃 Context.images + meta["blobs"] 的形狀（UI 就是這樣叫的）。"""
    from d4t.core.pipeline.context import Context

    rng = np.random.RandomState(0)
    ctx = Context()
    ctx.set_image("test", rng.randint(0, 255, (H, W)).astype(np.uint8))
    ctx.set_image("ref", rng.randint(0, 255, (H, W)).astype(np.uint8))
    ctx.set_image("diff", (ctx.images["test"].astype(np.float32)
                           - ctx.images["ref"].astype(np.float32)))
    ctx.add_feature("blob_snr", 4.2)
    ctx.meta["blobs"] = [{"x": 8, "y": 8, "w": 12, "h": 12, "area": 100,
                          "snr_value": 7.5}]

    out = overlay.render_overlay(ctx.images, ctx.features,
                                 blobs=ctx.meta["blobs"], label="bin=1")
    assert out.shape == (H, 2 * W, 3)
    assert out.dtype == np.uint8
