"""F11 Enhance-1：Enhance 段的**值域契約**、削平計數、雜訊 σ、mask 版 match。

這一批補的是四個「跑得完、有數字、而且沒人講出來」的洞：

1. Enhance 卡的輸出**沒有值域契約** —— 實測 ``stripes_h`` 會吐 261.5，
   而那個超界的值活到後面某個 ``to_uint8`` 才被壓掉，也就是資訊在使用者看不見
   的地方飽和。現在：壓回 0–255 是明講的契約，而「壓了多少」變成一個特徵。
2. 削平從「直方圖上看得到」升級成「數字 + 超過 1% 就講一句話」。
3. Denoise 的 ``strength`` 單位（這張圖自己的雜訊 σ）以前只活在演算法內部。
4. ``normalize`` 的 ``match`` 吃不到 ``use_within`` —— 另外三個方法都吃得到。
"""
from __future__ import annotations

import numpy as np
import pytest

from adept.core.algo import histmatch as algo_histmatch
from adept.core.pipeline.context import Context
from adept.core.pipeline.step import StepError, get_step
import adept.core.steps  # noqa: F401 - 註冊卡片
from adept.core.steps._util import CLIP_FRAC, clip_to_range


def _ctx(**images) -> Context:
    ctx = Context()
    for k, v in images.items():
        ctx.set_image(k, v)
    return ctx


def _ramp(h: int = 32, w: int = 32) -> np.ndarray:
    """一張有梯度、有雜訊也有一顆亮點的合成 patch。"""
    rng = np.random.default_rng(11)
    y, x = np.mgrid[0:h, 0:w]
    img = 90.0 + 0.8 * x + 0.5 * y + rng.normal(0.0, 3.0, (h, w))
    img[h // 2 - 2:h // 2 + 2, w // 2 - 2:w // 2 + 2] += 60.0
    return np.clip(img, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# 1. clip_to_range 本身
# --------------------------------------------------------------------------- #
def test_in_range_images_are_returned_untouched():
    """契約是 clip，**不是** rescale —— 界內的畫素一個都不准動。

    這是刻意的：``keep_level`` 承諾「影像留在原本的灰階區間，下游的門檻才還是
    同一個意思」。rescale 會動到每一個畫素，那句承諾就假了。
    """
    img = _ramp()
    out, frac = clip_to_range(img)
    assert frac == 0.0
    assert out is img or np.array_equal(out, img)


def test_it_reports_what_fraction_had_to_be_pushed_back():
    img = np.array([[-5.0, 10.0], [260.0, 300.0]], dtype=np.float32)
    out, frac = clip_to_range(img)
    assert frac == pytest.approx(3.0 / 4.0)      # -5, 260 是界內？不 —— 260 > 255
    assert out.tolist() == [[0.0, 10.0], [255.0, 255.0]]
    assert out.dtype == np.float32, "dtype 不強制統一（見 clip_to_range docstring）"


def test_an_empty_image_is_not_a_crash():
    out, frac = clip_to_range(np.zeros((0, 0), np.float32))
    assert frac == 0.0 and out.size == 0


# --------------------------------------------------------------------------- #
# 2. 卡片：超界的值不再溜到下游
# --------------------------------------------------------------------------- #
def _bright(h: int = 32, w: int = 32) -> np.ndarray:
    """一張**亮**的 patch（背景 240）加一條暗掃描線與一顆暗缺陷。

    亮的圖才會踩到超界：``keep_level`` 把原本的平均亮度加回殘差上，
    240 + 殘差就可能大於 255 —— 那正是實測出來的 250.09 / 261.5 的來源。
    """
    rng = np.random.default_rng(11)
    img = np.full((h, w), 240.0) + rng.normal(0.0, 2.0, (h, w))
    img[h // 4, :] = 180.0
    img[h // 2 - 2:h // 2 + 2, w // 2 - 2:w // 2 + 2] = 100.0
    return np.clip(img, 0, 255).astype(np.uint8)


def test_flattening_no_longer_leaves_values_outside_0_255():
    """實測出來的那個 250.09（``background`` + ``keep_level``）。

    以前這個超界的值會活到**後面某個** ``to_uint8`` 才被壓掉 —— 也就是資訊在
    使用者看不見的地方飽和，而 ``keep_level`` 的說明還寫著「讓影像留在原本的
    灰階區間，下游的門檻才還是同一個意思」。那句話在這個修正之前是假的。
    """
    step = get_step("flatten")()
    ctx = _ctx(test=_bright())
    out = step.run(ctx, {"streams": "test", "method": "background",
                         "size": 9, "keep_level": True})
    arr = np.asarray(out.images["test"])
    assert float(arr.max()) <= 255.0 and float(arr.min()) >= 0.0
    assert out.features[CLIP_FRAC] > 0.0, "壓過就要講出來"


def test_a_card_that_stays_in_range_reports_zero():
    step = get_step("denoise")()
    ctx = _ctx(test=_ramp())
    out = step.run(ctx, {"streams": "test", "method": "median", "ksize": 3})
    assert out.features[CLIP_FRAC] == 0.0


def test_the_clip_fraction_is_declared_and_prefixed_per_stream():
    """宣告要跟真的吐出來的名字一致 —— 一條流時逐字 ``clip_frac``（F10-3 規則）。"""
    cls = get_step("denoise")
    assert cls.resolve_features({"streams": "test"}) == [CLIP_FRAC]
    assert cls.resolve_features({"streams": "test,ref"}) == [
        "test_" + CLIP_FRAC, "ref_" + CLIP_FRAC]

    ctx = _ctx(test=_ramp(), ref=_ramp())
    out = cls().run(ctx, {"streams": "test,ref", "method": "median", "ksize": 3})
    assert set(out.features) == {"test_" + CLIP_FRAC, "ref_" + CLIP_FRAC}


def test_pushing_a_lot_of_pixels_out_of_range_says_so():
    """1% 以上就講話，而那句話要講得出**下一步怎麼做**。"""
    step = get_step("flatten")()
    out = step.run(_ctx(test=_bright()),
                   {"streams": "test", "method": "dark_spots", "size": 9,
                    "keep_level": True})
    assert out.features[CLIP_FRAC] > 0.01
    said = " ".join(out.meta.get("warnings") or [])
    assert "clipped back" in said and "gentler setting" in said


def test_a_tiny_amount_of_clipping_does_not_cry_wolf():
    """原圖本來就可能有幾顆貼著頂的畫素；每次都喊跟不喊一樣沒有用。"""
    img = np.full((32, 32), 250, np.uint8)
    img[0, 0] = 120                     # 1024 顆裡動一顆 = 0.1%
    out = get_step("flatten")().run(
        _ctx(test=img), {"streams": "test", "method": "dark_spots", "size": 9,
                         "keep_level": True})
    assert 0.0 < out.features[CLIP_FRAC] <= 0.01
    assert not [w for w in (out.meta.get("warnings") or [])
                if "clipped back" in w]


def test_clip_frac_is_about_values_computed_out_of_range_not_flattening():
    """**界線畫在哪裡**（不要把這個數字讀成「這張卡削平了多少」）。

    ``tone`` 的亮度是在卡片內部就夾回值域的（``apply_brightness_contrast``），
    所以 +120 把六成的畫素壓到 255 之後，走到基底這一層時**已經沒有界外的值**
    —— ``clip_frac`` 是 0，而那是對的：它回答的是「有多少資訊在你看不見的地方
    被丟掉」，而 tone 這種削平在**直方圖上看得見**（兩端那根染色的柱子，加上
    儀表的 ⚠）。

    兩個數字合成一個試過，不行：``bright_spots`` / ``dark_spots``（top-hat）
    的輸出本來就有一大片剛好等於 0 的畫素 —— 那是這張卡的用途，不是失敗。
    合成之後它每跑一次就喊一次狼來了。
    """
    out = get_step("tone")().run(_ctx(test=_bright()),
                                 {"streams": "test", "brightness": 60})
    arr = np.asarray(out.images["test"])
    assert float((arr == 255).mean()) > 0.5, "確實削平了大半張圖"
    assert out.features[CLIP_FRAC] == 0.0
    assert not (out.meta.get("warnings") or [])


# --------------------------------------------------------------------------- #
# 3. Denoise 的 strength 有單位了
# --------------------------------------------------------------------------- #
def test_denoise_records_the_noise_sigma_it_measured():
    """``strength`` 的單位是這張圖自己的 σ —— 那個數字要看得到。"""
    rng = np.random.default_rng(3)
    img = np.clip(128.0 + rng.normal(0.0, 6.0, (64, 64)), 0, 255).astype(np.uint8)
    ctx = _ctx(test=img)
    out = get_step("denoise")().run(
        ctx, {"streams": "test", "method": "bilateral", "ksize": 5,
              "strength": 1.0})
    sigma = out.meta["noise_sigma"]["test"]
    assert 4.0 < sigma < 8.5, sigma


def test_the_sigma_is_measured_per_stream_and_before_filtering():
    """兩條流各一個 σ，而且量的是**進來的**那張圖（不是濾過的）。"""
    rng = np.random.default_rng(5)
    quiet = np.full((48, 48), 120, np.uint8)
    noisy = np.clip(120.0 + rng.normal(0.0, 9.0, (48, 48)), 0, 255).astype(np.uint8)
    ctx = _ctx(test=noisy, ref=quiet)
    out = get_step("denoise")().run(
        ctx, {"streams": "test,ref", "method": "median", "ksize": 3})
    table = out.meta["noise_sigma"]
    assert set(table) == {"test", "ref"}
    assert table["ref"] < 1.0 < table["test"]


def test_sigma_is_meta_not_a_feature():
    """σ 是**這張圖的性質**，不是這張卡算出來的結果（接不接 Denoise 都一樣）。

    當成特徵的話，「有沒有這個數字」會取決於使用者有沒有放這張卡 —— 那不是一個
    可以拿來當 gate 的東西。要 gate 請用 Measure 段的 focus_quality。
    """
    cls = get_step("denoise")
    assert CLIP_FRAC in cls.resolve_features({"streams": "test"})
    assert "noise_sigma" not in cls.resolve_features({"streams": "test"})


# --------------------------------------------------------------------------- #
# 4. match 也吃 use_within
# --------------------------------------------------------------------------- #
def _two_patterns():
    """左半亮、右半暗的兩張圖 —— 但右半的**面積**在 test 與 ref 上不一樣。

    那正是 mask 存在的理由：整張圖的統計會被「這一顆剛好切到多少背景」帶著跑。
    """
    a = np.full((32, 32), 60, np.uint8)
    a[:, :16] = 200
    b = np.full((32, 32), 90, np.uint8)
    b[:, :8] = 210                      # 亮的那塊只有一半寬
    mask = np.zeros((32, 32), np.uint8)
    mask[:, :8] = 255                   # 只用兩張圖上都是亮的那一塊
    return a, b, mask


def test_match_measures_inside_the_mask_when_asked():
    a, b, mask = _two_patterns()
    step = get_step("normalize")()
    plain = step.run(_ctx(test=a, ref=b),
                     {"streams": "test", "method": "match",
                      "match_method": "linear"}).images["test"]
    masked = step.run(_ctx(test=a, ref=b, m=mask),
                      {"streams": "test", "method": "match",
                       "match_method": "linear",
                       "use_within": "m"}).images["test"]
    assert not np.array_equal(plain, masked), "mask 沒有生效"


def test_match_applies_the_mapping_to_the_whole_image():
    """量在 mask 內，**套用是整張圖** —— 不然 mask 邊界會出現一道人工階梯，
    而那道階梯會被下游當成邊緣訊號。"""
    a, b, mask = _two_patterns()
    out = get_step("normalize")().run(
        _ctx(test=a, ref=b, m=mask),
        {"streams": "test", "method": "match", "match_method": "linear",
         "use_within": "m"}).images["test"]
    # 原圖只有兩個灰階值 → 線性映射之後也只有兩個（mask 內外各自被搬走了，
    # 但搬的是同一個映射）。
    assert len(np.unique(out)) == 2


def test_the_mask_is_declared_as_a_line_on_the_canvas():
    """宣告漏了 mask，畫布上就沒有那條線 —— 使用者看不出兩張卡有關係（F9）。"""
    cls = get_step("normalize")
    reads = cls.resolve_reads({"streams": "test", "method": "match",
                               "reference": "ref", "use_within": "m"})
    assert reads == ["test", "ref", "m"]


def test_a_mask_of_the_wrong_size_is_a_plain_sentence_not_a_crash():
    a, b, _ = _two_patterns()
    with pytest.raises(StepError) as e:
        get_step("normalize")().run(
            _ctx(test=a, ref=b, m=np.ones((8, 8), np.uint8)),
            {"streams": "test", "method": "match", "match_method": "linear",
             "use_within": "m"})
    assert "Same size as" in str(e.value)


@pytest.mark.parametrize("method", ["exact", "linear", "percentile"])
def test_mask_none_reproduces_the_vendored_behaviour(method):
    """``mask=None`` 一定要跟 vendor 進來的那份逐位元組相同（改動的紀律）。"""
    rng = np.random.default_rng(7)
    src = rng.integers(0, 256, (24, 24), dtype=np.uint8)
    ref = rng.integers(0, 256, (24, 24), dtype=np.uint8)
    fn = algo_histmatch.MATCH_FN[method]
    full = np.ones((24, 24), np.uint8)
    assert np.array_equal(fn(src, ref), fn(src, ref, mask=full))


def test_an_all_zero_mask_falls_back_to_the_whole_image():
    """區域落在影像外的時候不要炸，也不要吐一張空圖。"""
    rng = np.random.default_rng(9)
    src = rng.integers(0, 256, (16, 16), dtype=np.uint8)
    ref = rng.integers(0, 256, (16, 16), dtype=np.uint8)
    zeros = np.zeros((16, 16), np.uint8)
    out = algo_histmatch.match_histogram_linear(src, ref, mask=zeros)
    assert np.array_equal(out, algo_histmatch.match_histogram_linear(src, ref))


def test_use_within_shows_up_for_match_in_the_form():
    """``show_when`` 是使用者看得到的那一半：三個方法用得到就要三個都列。"""
    spec = [s for s in get_step("normalize").params if s.name == "use_within"][0]
    assert spec.show_when == ("method", ("percentile", "glv_band", "match"))
