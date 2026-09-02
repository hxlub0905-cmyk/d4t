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
# 紅框（量測框）
# ---------------------------------------------------------------------------
def test_the_cd_card_can_supply_the_box_when_nothing_searched():
    """CD 卡量一團的時候順手就知道位置 —— F29 之前那件事沒有出口。

    使用者 2026-08-25：「GLV CD 在 Measurements 就已經量出這顆 defect 或位置的
    一些資訊了（這些資訊不能拿來用嗎）」。這一條就是「能」的那一半。
    """
    feats = {"cd_box_x": 20, "cd_box_y": 20, "cd_box_w": 10, "cd_box_h": 10}
    assert overlay.primary_blob_box(feats) == (20, 20, 10, 10)
    out = overlay.render_overlay({"test": flat()}, feats)
    assert tuple(int(v) for v in out[20, 25]) == overlay.BOX_COLOR


def test_the_box_lands_on_the_bbox_edge_only():
    """框畫在邊界上：邊界像素變紅、框內外都不動。"""
    feats = {"cd_box_x": 16, "cd_box_y": 16, "cd_box_w": 20, "cd_box_h": 20}
    boxed = overlay.render_overlay({"test": flat(100)}, feats)
    for y, x in [(16, 20), (35, 20), (20, 16), (20, 35)]:
        assert tuple(int(v) for v in boxed[y, x]) == overlay.BOX_COLOR, (y, x)
    assert tuple(int(v) for v in boxed[25, 25]) == (100, 100, 100)
    assert tuple(int(v) for v in boxed[50, 50]) == (100, 100, 100)


def test_explicit_box_overrides_features():
    feats = {"cd_box_x": 0, "cd_box_y": 0, "cd_box_w": 4, "cd_box_h": 4}
    out = overlay.render_overlay({"test": flat()}, feats, box=(30, 30, 10, 10))
    assert tuple(int(v) for v in out[30, 35]) == overlay.BOX_COLOR
    assert tuple(int(v) for v in out[0, 2]) != overlay.BOX_COLOR


def test_blob_features_are_gone_and_stay_gone():
    """``blob_x`` 那一組連同 `find_defect` 於 F31 T5 刪掉（F28 的寫法：斷言
    **現在沒有** —— 哪天有一張卡又吐這組名字，這一條會紅，而那正是它要講
    的話：先去把 `_BOX_FEATURE_SETS` 跟這裡一起想清楚）。"""
    from d4t.core.pipeline.step import REGISTRY

    feats = {"blob_x": 20, "blob_y": 20, "blob_w": 10, "blob_h": 10}
    assert overlay.primary_blob_box(feats) is None
    for cls in REGISTRY.values():
        declared = cls.resolve_features(
            cls.validate_params(cls.cleared_inputs())
            if hasattr(cls, "cleared_inputs") else {})
        assert "blob_x" not in declared, cls.key


def test_a_half_written_box_is_not_a_box():
    """量不到的時候那幾格**不寫**（CD 的規矩 3），所以少一格就是「沒有框」。

    少了這一條，``cd_box_w`` 漏掉會拿到一個部分填好的 dict ——
    畫出一個看起來很正常的錯框。
    """
    assert overlay.primary_blob_box({"cd_box_x": 1, "cd_box_y": 2}) is None
    assert overlay.primary_blob_box({}) is None


def test_a_prefixed_box_is_not_picked_up():
    """接了兩個區域時「主 blob」有兩個答案 —— 挑一個畫等於畫布說謊。"""
    feats = {"epi_cd_box_x": 20, "epi_cd_box_y": 20,
             "epi_cd_box_w": 10, "epi_cd_box_h": 10,
             "mg_cd_box_x": 40, "mg_cd_box_y": 40,
             "mg_cd_box_w": 10, "mg_cd_box_h": 10}
    assert overlay.primary_blob_box(feats) is None


def test_box_outside_image_is_clipped_not_crashing():
    out = overlay.render_overlay({"test": flat()}, {}, box=(60, 60, 999, 999))
    assert out.shape == (H, W, 3)
    assert tuple(int(v) for v in out[63, 63]) == overlay.BOX_COLOR


def test_no_box_features_means_no_box():
    plain = overlay.render_overlay({"test": flat()}, {})
    assert np.array_equal(plain, np.dstack([flat()] * 3))


def test_an_object_with_xywh_attributes_is_accepted():
    """``box=`` 吃 tuple **也**吃 dict 與有 x/y/w/h 屬性的物件（`_blob_box`）。

    以前這條驗的是 blobs 清單的 duck typing；blobs 路徑連同 `find_defect`
    刪掉之後（F31 T5），留下來的是 ``box=`` 這個直接指定的入口 ——
    它還是要吃得下三種形狀。
    """
    class _Box:
        x, y, w, h = 10, 12, 8, 6

    out = overlay.render_overlay({"test": flat()}, {}, box=_Box())
    assert tuple(int(v) for v in out[12, 14]) == overlay.BOX_COLOR


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
def test_the_label_never_changes_the_picture_size():
    """**輸出尺寸跟輸入一樣**（2026-09-01 使用者定調：「不要改變原尺寸好了」）。

    那一天先做過另一版：標籤畫在影像下面新加的一條字幕條上，樣品一個像素都
    不會被蓋到。使用者看過之後選了原尺寸 —— 所以標籤蓋回左上角，而「字塞不
    塞得下」由 :func:`overlay._fit_label` 保證（見下一條）。
    """
    plain = overlay.render_overlay({"test": flat(200)}, {})
    labelled = overlay.render_overlay({"test": flat(200)}, {},
                                      label="score=3.21")
    assert labelled.shape == plain.shape
    assert not np.array_equal(plain[:16], labelled[:16])   # 左上角有變化
    assert np.array_equal(plain[40:], labelled[40:])       # 下半部沒被動到


def test_the_label_band_covers_the_whole_width():
    """底條**滿版**：以前它只有字那麼寬，而字沒有被裁 —— 超出去那一段是白字
    直接壓在樣品上。字現在一定塞得下，而滿版的底條讓它在任何底圖上都讀得出。
    """
    labelled = overlay.render_overlay({"test": flat(200)}, {}, label="bin=1")
    top = labelled[0]                     # 最上面那一列
    assert int(top.max()) < 200, "整條都要壓暗，不是只有字底下那一段"


def test_the_caption_always_fits_the_picture_it_sits_under():
    """**這一條是那個 bug 本身**（使用者：「patch 上標註的 bin 黑邊會因為
    patch 不同 size 導致上方的字彙超出去」）。

    以前字級只看影像寬度（``w / 320``），完全不看字有多長 —— 於是字長得比圖
    還快：64 px 超出 53 px、128 px 超出 27 px、160 px 超出 34 px，**每一種
    尺寸都超**。現在先問字有多長再挑字級，塞不下就換更短的寫法、最後截字。
    """
    import cv2

    label = "#12345  score=4.210  bin=3"
    for w in (32, 40, 48, 64, 96, 128, 160, 200, 256, 512):
        text, scale = overlay._fit_label(label, w)
        tw = cv2.getTextSize(text, overlay._FONT, scale, 1)[0][0]
        assert tw <= w - 2 * overlay._LABEL_PAD, (w, text, tw)
        assert text, w
        # **識別的那一段永遠留著**：丟得掉的是 score，不是 #id
        assert text.startswith("#12345") or text.startswith("#1"), (w, text)


def test_the_caption_drops_the_score_before_the_id():
    """塞不下的時候有優先序：`score` 最先被丟（它在圖上最不識別）。"""
    label = "#12345  score=4.210  bin=3"
    wide, _ = overlay._fit_label(label, 400)
    mid, _ = overlay._fit_label(label, 64)
    tiny, _ = overlay._fit_label(label, 40)
    assert "score" in wide and "bin" in wide
    assert "score" not in mid and "bin" in mid
    assert tiny == "#12345"


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
    assert out.shape == (8, 8, 3)                   # 8px 寬照樣不改尺寸
    assert out.dtype == np.uint8


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
    """直接吃 Context.images + features 的形狀（出圖卡就是這樣叫的）。"""
    from d4t.core.pipeline.context import Context

    rng = np.random.RandomState(0)
    ctx = Context()
    ctx.set_image("test", rng.randint(0, 255, (H, W)).astype(np.uint8))
    ctx.set_image("ref", rng.randint(0, 255, (H, W)).astype(np.uint8))
    ctx.set_image("diff", (ctx.images["test"].astype(np.float32)
                           - ctx.images["ref"].astype(np.float32)))
    ctx.add_feature("cd_box_x", 8.0)
    ctx.add_feature("cd_box_y", 8.0)
    ctx.add_feature("cd_box_w", 12.0)
    ctx.add_feature("cd_box_h", 12.0)

    out = overlay.render_overlay(ctx.images, ctx.features, label="bin=1")
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
    assert win == int(ctx.features["glv_worst_i"]) == 12
    assert rects == ctx.roi_norm_rects("cells")


def _two_region_ctx():
    """兩個區域接進同一張 GLV：**第二個**裡面才有真的缺陷。

    第一個區域（``quiet``）鋪在一片平坦的背景上 —— 它照樣挑得出一個「最不
    一樣」的框，只是那一格的分數很小。第二個（``hot``）有一格是亮的。
    """
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    rng = np.random.default_rng(3)
    img = np.full((100, 100), 100, np.float32)
    img += rng.normal(0, 0.5, img.shape).astype(np.float32)
    img[8:16, 60:68] = 190.0                       # hot 的第 2 格
    ctx = Context(images={"test": img})
    ctx.set_roi_boxes("quiet", [(0.05 + 0.2 * i, 0.55, 0.08, 0.08)
                                for i in range(4)])
    ctx.set_roi_boxes("hot", [(0.2 + 0.2 * i, 0.08, 0.08, 0.08)
                              for i in range(4)])
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "quiet,hot", "metrics": "glv_mean",
        "judge": "glv_mean", "across_boxes": "each box"})
    return ctx


def test_the_thick_box_is_the_one_the_score_came_from():
    """**分數說哪一格，粗框就畫哪一格** —— 跨區域也一樣。

    這一條是把 bug 放回去的形狀。以前這支函式取的是**接線順序第一條 note**
    （＝第一個區域）的框與**它自己的**贏家，所以兩個區域的時候，報表標題印
    的分數來自 B、粗框卻畫在 A 上面一個一點都不異常的框。F68 的驗收上實測到
    （`recipes/rsem-worst-box.json`，三個區域鋪滿整張圖）：標題 27.753、
    琥珀框畫在另一個區域一個 1.3σ 的框上。跑得完、有圖、而且是錯的。
    """
    ctx = _two_region_ctx()
    quiet = list(ctx.roi_norm_rects("quiet"))
    hot = list(ctx.roi_norm_rects("hot"))
    rects, win, note = overlay.worst_note_for_overlay(ctx)

    # **每一組的框都畫**：細框的意思是「我量過的框」，兩組是同一件事。
    assert rects == quiet + hot
    # 贏家是分數高的那一組裡的那一格 —— 索引是接起來之後的全域索引。
    assert str(note["region"]) == "hot"
    assert win == len(quiet) + int(ctx.features["hot_glv_worst_i"])
    assert rects[win] == hot[int(ctx.features["hot_glv_worst_i"])]
    # 這一條才是重點：贏家不在第一組裡。
    assert win >= len(quiet)
    assert float(ctx.features["hot_glv_worst_score"]) \
        > float(ctx.features["quiet_glv_worst_score"])


def test_one_region_draws_exactly_what_it_used_to():
    """一個區域的時候逐位元組跟以前相同 —— 那是上面那個改動的邊界。"""
    ctx = _each_box_ctx()
    rects, win, note = overlay.worst_note_for_overlay(ctx)
    assert rects == ctx.roi_norm_rects("cells")
    assert win == int(ctx.features["glv_worst_i"])
    assert str(note["region"]) == "cells"


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


# ---------------------------------------------------------------------------
# 贏家框內的像素標記（F31 T3）—— 只進 overlay，判準來自 T1 的數字
# ---------------------------------------------------------------------------
def _odd(src, box=(0.25, 0.25, 0.5, 0.5), baseline=100.0, spread=1.0, k=3.0):
    return {"box": box, "baseline": baseline, "spread": spread, "k": k,
            "src": src}


def test_pixels_beyond_k_get_tinted_inside_the_winner_box():
    img = np.full((64, 64), 100, np.uint8)
    img[30:34, 30:34] = 180                      # 框內一小塊偏亮
    img[4:8, 4:8] = 180                          # 框外也有 —— 不准標
    plain = overlay.render_overlay({"test": img}, {}, montage=False)
    out = overlay.render_overlay({"test": img}, {}, montage=False,
                                 odd_pixels=_odd(img))
    tinted = (out != plain).any(axis=-1)        # 跟不標的那張比 —— 亮度不算
    ys, xs = np.nonzero(tinted)
    assert tinted.any()
    assert xs.min() >= 16 and xs.max() < 48 and ys.min() >= 16 and ys.max() < 48


def test_a_huge_k_marks_nothing_and_does_not_crash():
    img = np.full((64, 64), 100, np.uint8)
    img[30:34, 30:34] = 180
    plain = overlay.render_overlay({"test": img}, {}, montage=False)
    out = overlay.render_overlay({"test": img}, {}, montage=False,
                                 odd_pixels=_odd(img, k=1e9))
    assert out.tobytes() == plain.tobytes()


def test_the_criterion_is_the_same_numbers_the_score_used():
    """改 GLV 的判準統計量 → baseline/spread 變 → 標出來的東西跟著變。

    這裡直接用兩組不同的 baseline/spread（同一張圖）驗「判準只吃那兩個數字」
    —— 端到端那半（meta 的 worst 就是這兩個數字）由
    `test_the_overlay_note_is_the_same_computation` 鎖著。
    """
    img = np.full((64, 64), 100, np.uint8)
    img[30:34, 30:34] = 130
    a = overlay.render_overlay({"test": img}, {}, montage=False,
                               odd_pixels=_odd(img, baseline=100.0, spread=1.0))
    b = overlay.render_overlay({"test": img}, {}, montage=False,
                               odd_pixels=_odd(img, baseline=100.0,
                                               spread=50.0))
    assert a.tobytes() != b.tobytes()            # spread 大 → 130 不算異常
    plain = overlay.render_overlay({"test": img}, {}, montage=False)
    assert b.tobytes() == plain.tobytes()


def test_marking_writes_no_feature_and_no_region():
    """界線寫死：只進 overlay。它一旦開始吐特徵，find_defect 就從後門長回來。"""
    ctx = _each_box_ctx()
    feats_before = dict(ctx.features)
    rois_before = list(ctx.roi_names())
    rects, win, note = overlay.worst_note_for_overlay(ctx)
    worst = note["worst"]
    overlay.render_overlay(
        {"test": ctx.images["test"]}, dict(ctx.features), montage=False,
        roi_boxes=rects, roi_winner=win,
        odd_pixels={"box": rects[win], "baseline": worst["baseline"],
                    "spread": worst["spread"], "k": 3.0,
                    "src": ctx.images["test"]})
    assert ctx.features == feats_before
    assert ctx.roi_names() == rois_before
    assert "blobs" not in ctx.meta


def test_the_winner_outline_does_not_swallow_the_tint_on_a_tiny_box():
    """實測踩到的：384²、~500 框時贏家框只有 5×9 px，3 px 的粗描邊
    （cv2 的線騎在邊上、往內外各長一半）把整格塗滿 —— T3 染的 32 個像素
    一個都看不見，贏家框變成一顆實心色塊。粗細要讓路給框的內部。"""
    img = np.full((384, 384), 100, np.uint8)
    box = (0.30, 0.30, 5 / 384.0, 9 / 384.0)      # 實測那顆的尺寸
    x0, y0 = int(0.30 * 384), int(0.30 * 384)
    img[y0:y0 + 9, x0:x0 + 5] = 180               # 整格偏亮 → 全部該染
    plain = overlay.render_overlay({"test": img}, {}, montage=False)
    boxed = overlay.render_overlay({"test": img}, {}, montage=False,
                                   roi_boxes=[box], roi_winner=0)
    both = overlay.render_overlay({"test": img}, {}, montage=False,
                                  roi_boxes=[box], roi_winner=0,
                                  odd_pixels=_odd(img, box=box))
    assert boxed.tobytes() != plain.tobytes()      # 框有畫
    assert both.tobytes() != boxed.tobytes()       # 染色沒有被描邊整片蓋掉
    # 大框不受影響：描邊照舊是粗的（跟細的其餘框分得出來）
    big = (0.1, 0.1, 0.5, 0.5)
    a = overlay.render_overlay({"test": img}, {}, montage=False,
                               roi_boxes=[big], roi_winner=0)
    b = overlay.render_overlay({"test": img}, {}, montage=False,
                               roi_boxes=[big], roi_winner=-1)
    assert a.tobytes() != b.tobytes()


def test_a_missing_source_stream_marks_nothing():
    img = np.full((64, 64), 100, np.uint8)
    img[30:34, 30:34] = 250
    plain = overlay.render_overlay({"test": img}, {}, montage=False)
    out = overlay.render_overlay({"test": img}, {}, montage=False,
                                 odd_pixels=_odd(None))
    assert out.tobytes() == plain.tobytes()


# ---------------------------------------------------------------------------
# 指名哪幾條流、橫排還是直疊（F33）
# ---------------------------------------------------------------------------
def test_the_default_path_is_untouched_by_the_new_parameters():
    """**預設的每一顆圖不准動一個位元。** 這兩個參數是加上去的，不是改掉的。"""
    images = {"test": flat(100), "diff": flat(30)}
    plain = overlay.render_overlay(images, {})
    spelled_out = overlay.render_overlay(images, {}, panes=None,
                                         stack=overlay.STACK_H)
    assert np.array_equal(plain, spelled_out)
    # 而指名同一組流也要得到同一張圖（兩條路共用 `_pane`／`_stack_panes`）
    named = overlay.render_overlay(images, {}, panes=["test", "diff"])
    assert np.array_equal(plain, named)


def test_panes_choose_which_streams_and_in_what_order():
    images = {"test": flat(10), "ref": flat(120), "diff": flat(240)}
    out = overlay.render_overlay(images, {}, panes=["ref", "diff"])
    assert out.shape == (H, 2 * W, 3)
    assert int(out[H // 2, 2, 0]) == 120            # 第一格是 ref
    assert int(out[H // 2, W + 5, 0]) == 240        # 第二格是 diff


def test_three_panes_fit_side_by_side():
    images = {"test": flat(10), "ref": flat(120), "diff": flat(240)}
    out = overlay.render_overlay(images, {}, panes=["test", "ref", "diff"])
    assert out.shape == (H, 3 * W, 3)
    assert int(out[H // 2, 2, 0]) == 10
    assert int(out[H // 2, W + 5, 0]) == 120
    assert int(out[H // 2, 2 * W + 5, 0]) == 240


def test_stacking_puts_the_first_pane_on_top():
    """直疊是 characterization 要的方向：上面 ground truth、下面第二份 ——
    它要對得上報表由上往下讀的順序。"""
    images = {"single": flat(60), "paired": flat(200)}
    out = overlay.render_overlay(images, {}, panes=["single", "paired"],
                                 stack=overlay.STACK_V)
    assert out.shape == (2 * H, W, 3)
    assert int(out[2, W // 2, 0]) == 60             # 上面那一格
    assert int(out[H + 5, W // 2, 0]) == 200        # 下面那一格
    assert int(out[H, W // 2, 0]) == overlay.SEAM_GRAY      # 接縫那一列


def test_the_seam_does_not_change_the_total_size():
    """分隔線是**覆寫**接縫後的第一列／行，不是插進去一條。"""
    images = {"test": flat(100), "diff": flat(30)}
    across = overlay.render_overlay(images, {}, panes=["test", "diff"])
    down = overlay.render_overlay(images, {}, panes=["test", "diff"],
                                  stack=overlay.STACK_V)
    assert across.shape == (H, 2 * W, 3) and down.shape == (2 * H, W, 3)


def test_a_pane_that_is_not_there_is_skipped_not_fatal():
    """缺一格不值得讓整張圖畫不出來 —— 而缺的那一格本身常常就是答案
    （配不到的那一顆沒有第二張圖）。"""
    images = {"single": flat(60)}
    out = overlay.render_overlay(images, {}, panes=["single", "paired"])
    assert out.shape == (H, W, 3)


def test_an_empty_pane_list_or_a_bad_stack_says_so():
    images = {"test": flat(100)}
    with pytest.raises(ExportError) as e1:
        overlay.render_overlay(images, {}, panes=[])
    assert "panes" in str(e1.value)
    with pytest.raises(ExportError) as e2:
        overlay.render_overlay(images, {}, panes=["test"], stack="sideways")
    assert "stack" in str(e2.value)


def test_the_boxes_are_drawn_on_every_pane():
    """框畫在哪幾格是**兩條路共用的那一支**決定的（`_pane`）—— 各寫一份的話
    會在其中一條路上安靜地漂掉。"""
    images = {"test": flat(100), "ref": flat(100), "diff": flat(100)}
    boxes = [(0.25, 0.25, 0.5, 0.5)]
    out = overlay.render_overlay(images, {}, panes=["test", "ref", "diff"],
                                 roi_boxes=boxes, roi_winner=0)
    for pane in range(3):
        cut = out[:, pane * W:(pane + 1) * W]
        assert not np.array_equal(cut, overlay.to_display_rgb(flat(100))), pane
