# F110 驗收：Focus index 吃區域（三張 Measure 卡裡最後一張補上的）。
"""「整張圖夠不夠清楚」跟「我在意的那一塊夠不夠清楚」不是同一個問題。

一張 RSEM 大圖上空白的角落會把整張的銳利度**拉低** —— 而那不是失焦，那是
那裡本來就沒有東西。`focus_quality` 是三張 Measure 卡裡唯一沒有 `region_keys`
的，所以它是唯一問不出第二個問題的那一張。

⚠ 這一份守的核心是**裁出二維的一塊**：Laplacian／Tenengrad／FFT／IQI 量的都是
「相鄰像素之間」的變化，拿一串攤平的像素（`roi_pixels`）餵進去，四個數字照樣
算得出來、看起來也正常，而「相鄰」是假的。那是這個 repo 最貴的那種失敗。
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import quality as algo_quality  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.step import StepError  # noqa: E402

SHARP = np.s_[0:64, 0:64]      # 左上：細棋盤（銳利）
FLAT = np.s_[64:128, 64:128]   # 右下：全平（沒有東西可以對焦）


def _half_sharp(size: int = 128) -> np.ndarray:
    """左上角銳利、右下角平坦 —— 兩塊的答案必須明顯不同。"""
    rng = np.random.default_rng(5)
    img = np.full((size, size), 120.0)
    for y in range(0, size // 2, 4):
        for x in range(0, size // 2, 4):
            img[y:y + 4, x:x + 4] = 220 if ((y // 4) + (x // 4)) % 2 == 0 else 30
    img += rng.normal(0, 3, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _run(images, rois=None, **params):
    step = get_step("focus_quality")()
    ctx = Context(images=dict(images))
    for name, rects in (rois or {}).items():
        ctx.set_roi_boxes(name, rects)
    return ctx, step.run(ctx, dict(params))


# --------------------------------------------------------------------------- #
# 1. 核心承諾：裁的是二維的一塊
# --------------------------------------------------------------------------- #
def test_measuring_in_a_region_measures_only_that_region():
    """接了區域之後，數字要等於**自己裁那一塊**算出來的 —— 逐項相同。

    這一條同時擋掉兩種壞法：整張圖照量（區域根本沒生效），以及拿攤平的像素
    去算（`roi_pixels` 那條路，數字會不一樣但看起來正常）。
    """
    img = _half_sharp()
    _step, ctx = _run({"test": img},
                      rois={"hot": [(0.0, 0.0, 0.5, 0.5)]},
                      source="test", roi="hot")
    want = algo_quality.compute_quality(np.ascontiguousarray(img[SHARP]))
    assert ctx.features["focus_lapvar"] == pytest.approx(want["laplacian_var"])
    assert ctx.features["focus_tenengrad"] == pytest.approx(want["tenengrad"])
    assert ctx.features["focus_fft"] == pytest.approx(want["fft_hf_ratio"])


def test_a_flat_corner_no_longer_drags_the_whole_image_down():
    """這張卡長出這一格的**理由**，寫成一條測試。

    整張圖有一半是空白的時候，「這張圖清楚嗎」的答案被那一半拉低了 ——
    而使用者在意的是有 pattern 的那一塊。
    """
    img = _half_sharp()
    _w, whole = _run({"test": img}, source="test")
    _s, sharp = _run({"test": img}, rois={"hot": [(0.0, 0.0, 0.5, 0.5)]},
                     source="test", roi="hot")
    _f, flat = _run({"test": img}, rois={"dead": [(0.5, 0.5, 0.5, 0.5)]},
                    source="test", roi="dead")
    assert sharp.features["focus_lapvar"] > whole.features["focus_lapvar"]
    assert whole.features["focus_lapvar"] > flat.features["focus_lapvar"]


def test_the_flat_pixels_are_not_secretly_still_in_there():
    """反向：把區域接到平坦那一塊，數字要**真的**掉下來。

    「區域參數被讀了但裁錯了」（例如裁成整張、裁成外接矩形）在上面那一條上
    分不出來，在這裡分得出來。
    """
    img = _half_sharp()
    _f, flat = _run({"test": img}, rois={"dead": [(0.5, 0.5, 0.5, 0.5)]},
                    source="test", roi="dead")
    want = algo_quality.compute_quality(np.ascontiguousarray(img[FLAT]))
    assert flat.features["focus_lapvar"] == pytest.approx(want["laplacian_var"])


# --------------------------------------------------------------------------- #
# 2. 名字：接一個區域時逐字不變，接兩個才帶前綴
# --------------------------------------------------------------------------- #
def test_one_region_keeps_the_names_it_had_before():
    """**黃金值不動的前提。** 舊 recipe 的分數表達式寫的是 `focus_lapvar`。"""
    img = _half_sharp()
    _step, ctx = _run({"test": img}, rois={"hot": [(0.0, 0.0, 0.5, 0.5)]},
                      source="test", roi="hot")
    assert set(ctx.features) == {"focus_lapvar", "focus_tenengrad", "focus_fft"}


def test_two_regions_put_each_ones_name_in_front():
    img = _half_sharp()
    _step, ctx = _run({"test": img},
                      rois={"hot": [(0.0, 0.0, 0.5, 0.5)],
                            "dead": [(0.5, 0.5, 0.5, 0.5)]},
                      source="test", roi="hot,dead")
    assert "hot_focus_lapvar" in ctx.features
    assert "dead_focus_lapvar" in ctx.features
    assert "focus_lapvar" not in ctx.features
    assert ctx.features["hot_focus_lapvar"] > ctx.features["dead_focus_lapvar"]


def test_what_it_declares_is_what_it_writes():
    """宣告與真的寫出來的要對得起來 —— 畫布是照宣告畫的。"""
    step = get_step("focus_quality")
    params = {"source": "test", "roi": "hot,dead"}
    img = _half_sharp()
    _s, ctx = _run({"test": img},
                   rois={"hot": [(0.0, 0.0, 0.5, 0.5)],
                         "dead": [(0.5, 0.5, 0.5, 0.5)]}, **params)
    assert set(step.resolve_features(params)) == set(ctx.features)
    assert step.resolve_regions_in(params) == ["hot", "dead"]


# --------------------------------------------------------------------------- #
# 3. 多框區域：走既有的那條路，不自己發明規矩
# --------------------------------------------------------------------------- #
def test_a_region_of_several_boxes_says_which_one_to_name():
    """銳利度是**幾何**的量，而幾何拿不到「散落幾塊的那一個矩形」。

    這個 repo 對「要幾何的卡」早就有答案（CD 卡走同一條）：報錯並指名
    `<name>_center`。這張卡不另外發明規矩 —— 那句錯誤訊息使用者已經在別處
    讀過一次了。
    """
    img = _half_sharp()
    with pytest.raises(StepError) as e:
        _run({"test": img},
             rois={"cross": [(0.0, 0.0, 0.2, 0.2), (0.6, 0.6, 0.2, 0.2)]},
             source="test", roi="cross")
    assert "cross_center" in str(e.value), str(e.value)


def test_no_line_still_means_the_whole_image():
    """**沒接區域的意思從來不是「不要量」。** 舊 recipe 一個字都沒改。"""
    img = _half_sharp()
    _step, ctx = _run({"test": img}, source="test")
    want = algo_quality.compute_quality(img)
    assert ctx.features["focus_lapvar"] == pytest.approx(want["laplacian_var"])
