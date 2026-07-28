# F7-4 驗收：Region 段 —— ROI 從「藏在量測卡裡的參數」升成一級概念。
"""具名 ROI 的契約，以及它修掉的那個坑。

背景：F7-4 之前，「要看哪裡」是被複製在每張量測卡裡的幾何參數
（``glv_stats`` 的 ``region``/``box_size``、``roi_snr`` 的 ``mode``/``box_size``）。
``CLAUDE.md`` §7 記著它的後果：同一組中心框參數在 128² patch 上準、
換成 256² 就漏抓。現在幾何只在 Region 卡裡定義一次，量測卡只引用名字。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adept.core.pipeline import REGISTRY, StepError          # noqa: E402
from adept.core.pipeline.context import Context, ContextError  # noqa: E402
from adept.core.steps.region import center_norm_rect          # noqa: E402
import adept.core.steps  # noqa: F401,E402 — 觸發註冊


def run_step(key, ctx, **params):
    cls = REGISTRY[key]
    return cls().run(ctx, cls.validate_params(params))


def _ctx(size=128, key="test"):
    return Context(images={key: np.zeros((size, size), np.uint8)})


# --------------------------------------------------------------------------- #
# 1. Context 的具名 ROI 契約
# --------------------------------------------------------------------------- #
def test_named_roi_round_trip_and_overwrite():
    ctx = _ctx()
    assert ctx.roi_names() == []

    ctx.set_roi("a", (0.25, 0.25, 0.5, 0.5))
    assert ctx.roi_names() == ["a"]
    assert ctx.roi_rect("a", (128, 128)) == (32, 32, 64, 64)

    # 同名要覆寫，不是變成兩個
    ctx.set_roi("a", (0.0, 0.0, 1.0, 1.0))
    assert ctx.roi_names() == ["a"]
    assert ctx.roi_rect("a", (128, 128)) == (0, 0, 128, 128)


def test_require_roi_names_what_is_available():
    """打錯字要講得出「有哪些可用」，不能只說找不到。"""
    ctx = _ctx()
    ctx.set_roi("centre", (0.4, 0.4, 0.2, 0.2))
    with pytest.raises(ContextError) as ei:
        ctx.require_roi("centr")
    msg = str(ei.value)
    assert "centre" in msg and "Region card" in msg


# --------------------------------------------------------------------------- #
# 2. Region 卡
# --------------------------------------------------------------------------- #
def test_roi_define_center_is_actually_centred():
    ctx = _ctx(128)
    run_step("roi_define", ctx, name="mid", shape="center", size=32)
    x, y, w, h = ctx.roi_rect("mid", (128, 128))
    assert (w, h) == (32, 32)
    assert (x + w / 2, y + h / 2) == (64, 64), "缺陷永遠在 patch 正中心"


def test_roi_define_whole_covers_everything():
    ctx = _ctx(64)
    run_step("roi_define", ctx, name="all", shape="whole")
    assert ctx.roi_rect("all", (64, 64)) == (0, 0, 64, 64)


def test_percent_sizing_survives_a_patch_size_change():
    """**CLAUDE.md §7 那個坑的正解。**

    以像素定義的框換 patch 尺寸就失效；以百分比定義的框會跟著縮放，
    所以同一份 recipe 在 128² 與 256² 上看的是「同一塊相對區域」。
    """
    assert center_norm_rect((128, 128), 32, "px") != \
        center_norm_rect((256, 256), 32, "px"), \
        "px 模式的正規化矩形本來就會隨影像尺寸改變 —— 這正是問題所在"

    pct = center_norm_rect((128, 128), 25, "percent")
    assert pct == center_norm_rect((256, 256), 25, "percent")

    ctx = _ctx()
    ctx.set_roi("q", pct)
    assert ctx.roi_rect("q", (128, 128)) == (48, 48, 32, 32)
    assert ctx.roi_rect("q", (256, 256)) == (96, 96, 64, 64)   # 比例相同


def test_roi_define_clamps_silly_sizes():
    """填爆的值要被夾住，不能產生無效的框（鐵則 4）。"""
    ctx = _ctx(64)
    run_step("roi_define", ctx, name="huge", shape="center", size=99999)
    assert ctx.roi_rect("huge", (64, 64)) == (0, 0, 64, 64)

    run_step("roi_define", ctx, name="tiny", shape="center", size=1)
    _x, _y, w, h = ctx.roi_rect("tiny", (64, 64))
    assert w >= 1 and h >= 1


def test_empty_region_name_is_refused():
    ctx = _ctx()
    with pytest.raises(StepError):
        run_step("roi_define", ctx, name="   ")


# --------------------------------------------------------------------------- #
# 3. 量測卡引用具名 ROI
# --------------------------------------------------------------------------- #
def test_glv_stats_measures_inside_the_named_region():
    img = np.zeros((64, 64), np.float32)
    img[24:40, 24:40] = 100.0            # 只有中央 16×16 有訊號
    ctx = Context(images={"test": img})

    run_step("roi_define", ctx, name="mid", shape="center", size=16)
    run_step("glv_stats", ctx, roi="mid", metrics="glv_mean")
    assert ctx.features["glv_mean"] == pytest.approx(100.0)

    ctx2 = Context(images={"test": img})
    run_step("glv_stats", ctx2, roi="", metrics="glv_mean")   # 整張圖
    assert ctx2.features["glv_mean"] == pytest.approx(img.mean())


def test_blob_segment_publishes_its_main_blob_as_a_named_region():
    """偵測出來的框與手畫的框走同一條路 —— 這是 F7-4 最關鍵的一刀。"""
    rng = np.random.default_rng(3)
    diff = rng.normal(0, 1, (96, 96)).astype(np.float32)
    diff[40:56, 40:56] += 80.0
    ctx = Context(images={"diff": diff})
    run_step("snr_map", ctx, window=15, exclude_border=8)
    # 門檻用範例 recipe 的值：預設 0 = Otsu，在正規化 SNR map 上會切掉半張圖
    # （CLAUDE.md §7 的老坑，這裡不重蹈）
    run_step("blob_segment", ctx, min_area=6, snr_threshold=200)

    assert "blob" in ctx.roi_names(), "主 blob 要以具名 ROI 發布出來"
    x, y, w, h = ctx.roi_rect("blob", diff.shape)
    assert w > 0 and h > 0
    assert x <= 48 <= x + w and y <= 48 <= y + h, "主 blob 要蓋到訊號所在位置"
    # 量測卡指名 blob 與指名手畫框，走的是同一段程式
    run_step("glv_stats", ctx, source="diff", roi="blob", metrics="glv_max")
    assert ctx.features["glv_max"] > 50.0, "ROI 要蓋到 +80 的訊號"


def test_measure_cards_refuse_a_typo_instead_of_silently_using_everything():
    """ROI 名字打錯要報錯 —— 安靜地退回整張圖會讓人以為量對了。"""
    ctx = Context(images={"test": np.zeros((32, 32), np.float32)})
    for key, kw in (("glv_stats", {"metrics": "glv_mean"}),
                    ("roi_snr", {}),
                    ("cd_measure", {})):
        with pytest.raises(StepError):
            run_step(key, Context(images=dict(ctx.images)), roi="nope", **kw)


def test_blob_roi_works_even_without_the_image_stream():
    """``roi='blob'`` 存的是像素座標，所以下游把影像流蓋掉也還量得到。"""
    ctx = Context(images={"diff": np.zeros((32, 32), np.float32)})
    ctx.meta["blobs"] = [{"x": 4, "y": 6, "w": 10, "h": 20, "area": 150}]
    del ctx.images["diff"]
    run_step("cd_measure", ctx, roi="blob")
    assert ctx.features["cd_x_px"] == 10.0
    assert ctx.features["cd_y_px"] == 20.0
