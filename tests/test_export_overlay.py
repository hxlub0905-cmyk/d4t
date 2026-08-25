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


def test_the_cd_card_can_supply_the_box_when_nothing_searched():
    """CD 卡量一團的時候順手就知道位置 —— F29 之前那件事沒有出口。

    使用者 2026-08-25：「GLV CD 在 Measurements 就已經量出這顆 defect 或位置的
    一些資訊了（這些資訊不能拿來用嗎）」。這一條就是「能」的那一半。
    """
    feats = {"cd_box_x": 20, "cd_box_y": 20, "cd_box_w": 10, "cd_box_h": 10}
    assert overlay.primary_blob_box(None, feats) == (20, 20, 10, 10)
    out = overlay.render_overlay({"test": flat()}, feats)
    assert tuple(int(v) for v in out[20, 25]) == overlay.BOX_COLOR


def test_a_searched_box_wins_over_a_measured_one():
    """兩組都在的時候，**去圖上找出來的那一個**贏（見 `_BOX_FEATURE_SETS`）。

    順序有沒有寫對，在畫面上是看不出來的 —— 兩個都是一個紅框。
    """
    feats = {"blob_x": 4, "blob_y": 4, "blob_w": 6, "blob_h": 6,
             "cd_box_x": 40, "cd_box_y": 40, "cd_box_w": 10, "cd_box_h": 10}
    assert overlay.primary_blob_box(None, feats) == (4, 4, 6, 6)


def test_a_half_written_box_is_not_a_box():
    """量不到的時候那幾格**不寫**（CD 的規矩 3），所以少一格就是「沒有框」。

    少了這一條，``cd_box_w`` 漏掉會讓框退回上一組、或拿到一個部分填好的
    dict —— 兩種都會畫出一個看起來很正常的錯框。
    """
    assert overlay.primary_blob_box(None, {"cd_box_x": 1, "cd_box_y": 2}) is None
    assert overlay.primary_blob_box(None, {}) is None


def test_a_prefixed_box_is_not_picked_up():
    """接了兩個區域時「主 blob」有兩個答案 —— 挑一個畫等於畫布說謊。"""
    feats = {"epi_cd_box_x": 20, "epi_cd_box_y": 20,
             "epi_cd_box_w": 10, "epi_cd_box_h": 10,
             "mg_cd_box_x": 40, "mg_cd_box_y": 40,
             "mg_cd_box_w": 10, "mg_cd_box_h": 10}
    assert overlay.primary_blob_box(None, feats) is None


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


# ---------------------------------------------------------------------------
# 逐框比較的 ROI 框（F31）—— 贏家粗、其餘細，來源是 GLV 的 meta
# ---------------------------------------------------------------------------
def _nboxes(n=4):
    """一排並肩的正規化框。"""
    return [(i / n + 0.05 / n, 0.25, 0.9 / n, 0.5) for i in range(n)]


def test_the_winner_is_thick_and_amber_the_rest_thin_and_blue():
    img = flat(60, 200, 200)          # ≥192 → 贏家粗 3px、其餘 1px
    out = overlay.render_overlay({"test": img}, {}, roi_boxes=_nboxes(4),
                                 roi_winner=2)
    assert (out == overlay.ROI_WINNER_COLOR).all(axis=-1).any()
    assert (out == overlay.ROI_BOX_COLOR).all(axis=-1).any()
    # 粗細就是那句話本身：贏家的框邊要比其餘的厚
    win = (out == overlay.ROI_WINNER_COLOR).all(axis=-1).sum()
    one_other = (out == overlay.ROI_BOX_COLOR).all(axis=-1).sum() / 3.0
    assert win > one_other * 1.5


def test_no_winner_means_all_thin_and_no_guessing():
    out = overlay.render_overlay({"test": flat(60, 200, 200)}, {},
                                 roi_boxes=_nboxes(4), roi_winner=-1)
    assert not (out == overlay.ROI_WINNER_COLOR).all(axis=-1).any()
    assert (out == overlay.ROI_BOX_COLOR).all(axis=-1).any()


def test_no_roi_boxes_changes_nothing_byte_for_byte():
    """沒接 ROI 的 recipe 一個位元不變 —— 預設值就是「這個參數不存在」。"""
    a = overlay.render_overlay({"test": flat()}, {"blob_x": 10.0,
                               "blob_y": 10.0, "blob_w": 8.0, "blob_h": 8.0})
    b = overlay.render_overlay({"test": flat()}, {"blob_x": 10.0,
                               "blob_y": 10.0, "blob_w": 8.0, "blob_h": 8.0},
                               roi_boxes=None, roi_winner=-1)
    assert a.tobytes() == b.tobytes()


def test_roi_boxes_land_on_both_montage_panels():
    imgs = {"test": flat(60), "diff": flat(10)}
    out = overlay.render_overlay(imgs, {}, roi_boxes=_nboxes(2), roi_winner=0)
    left, right = out[:, :W], out[:, W:]
    for half in (left, right):
        assert (half == overlay.ROI_WINNER_COLOR).all(axis=-1).any()
        assert (half == overlay.ROI_BOX_COLOR).all(axis=-1).any()


def test_the_measured_box_stays_on_top_of_the_roi_boxes():
    """量測框（紅）後畫 —— 疊到的地方「量到的東西在哪」在最上面。"""
    boxes = [(0.1, 0.1, 0.5, 0.5)]
    out = overlay.render_overlay(
        {"test": flat(60)}, {}, box=(6, 6, 32, 32), roi_boxes=boxes,
        roi_winner=0)
    assert (out == overlay.BOX_COLOR).all(axis=-1).any()


# ---------------------------------------------------------------------------
# pick_roi_boxes —— 畫哪幾個（all / none / near the winner ＋ 自動退化）
# ---------------------------------------------------------------------------
def test_all_keeps_everything_below_the_cap():
    boxes, win, degraded = overlay.pick_roi_boxes(_nboxes(4), 2, "all", 300)
    assert len(boxes) == 4 and win == 2 and not degraded


def test_none_keeps_only_the_winner():
    boxes, win, degraded = overlay.pick_roi_boxes(_nboxes(4), 2, "none", 300)
    assert boxes == [_nboxes(4)[2]] and win == 0 and not degraded


def test_near_the_winner_keeps_the_cap_nearest():
    rects = _nboxes(10)
    boxes, win, degraded = overlay.pick_roi_boxes(rects, 5, "near the winner", 3)
    assert len(boxes) == 3 and not degraded
    assert rects[5] in boxes and boxes[win] == rects[5]
    assert rects[4] in boxes and rects[6] in boxes      # 貼著贏家的那兩個


def test_all_quietly_degrades_above_the_cap_and_says_so():
    rects = _nboxes(10)
    boxes, win, degraded = overlay.pick_roi_boxes(rects, 5, "all", 3)
    assert degraded and len(boxes) == 3 and boxes[win] == rects[5]


def test_no_winner_and_too_many_draws_nothing_rather_than_guessing():
    rects = _nboxes(10)
    boxes, win, degraded = overlay.pick_roi_boxes(rects, -1, "all", 3)
    assert boxes == [] and win == -1 and degraded


def test_the_winner_survives_even_a_cap_of_one():
    rects = _nboxes(6)
    boxes, win, _ = overlay.pick_roi_boxes(rects, 3, "near the winner", 1)
    assert boxes == [rects[3]] and win == 0


# ---------------------------------------------------------------------------
# roi_boxes_for_overlay —— 從 rerun 的 Context 撿，跟特徵同一次計算
# ---------------------------------------------------------------------------
def _each_box_ctx():
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    img = np.full((100, 100), 100, np.float32)
    img[42:58, 42:58] = 170.0                      # cell 12 (5×5 的正中)
    ctx = Context(images={"test": img})
    n = 5
    ctx.set_roi_boxes("cells", [
        (c / n + 0.02, r / n + 0.02, 1.0 / n - 0.04, 1.0 / n - 0.04)
        for r in range(n) for c in range(n)])
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box"})
    return ctx


def test_the_boxes_come_from_the_glv_note_not_a_second_pick():
    ctx = _each_box_ctx()
    rects, win = overlay.roi_boxes_for_overlay(ctx)
    assert len(rects) == 25
    assert win == int(ctx.features["worst_i"]) == 12
    assert rects == ctx.roi_norm_rects("cells")


def test_a_pooled_run_yields_no_roi_boxes():
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    ctx = Context(images={"test": np.full((60, 60), 90, np.float32)})
    ctx.set_roi_boxes("cells", [(0.1, 0.1, 0.5, 0.5), (0.6, 0.1, 0.3, 0.5)])
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median"})
    assert overlay.roi_boxes_for_overlay(ctx) == ([], -1)


def test_a_context_without_glv_yields_no_roi_boxes():
    class Bare:
        meta: dict = {}
    assert overlay.roi_boxes_for_overlay(Bare()) == ([], -1)
