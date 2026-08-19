"""F11 Enhance-UI E 與 B：兩個「調的時候看不到、事後也沒人講」的診斷。

E. **磨掉的是雜訊還是訊號**（`denoise` 的 `removed_over_noise`）。
   `strength` / `ksize` 那兩個旋鈕唯一的問題就是這個，而在這之前它在畫面上完全
   沒有蹤跡 —— 使用者只能來回切 before/after 用眼睛看，而「邊緣被磨掉一點」正是
   眼睛最不擅長的那種差別。

B. **兩條流處理完之後還有多像**（`pair_level_delta` / `pair_spread_ratio`）。
   可比性是 `subtract` 的前提，而「不可比」在畫面上長得像「兩張圖本來就不一樣」
   —— 一張比較亮的 ref 減出來的 diff 整片偏移，看起來就像一個大面積的缺陷。
"""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import get_step
import d4t.core.steps  # noqa: F401 - 註冊卡片
from d4t.core.steps._util import (
    CLIP_FRAC, PAIR_FEATURES, PAIR_SAMPLE_MAX, pair_similarity,
)
from d4t.core.steps.denoise import REMOVED_OVER_NOISE


def _ctx(**images) -> Context:
    ctx = Context()
    for k, v in images.items():
        ctx.set_image(k, v)
    return ctx


def _run(key: str, ctx: Context, **params) -> Context:
    return get_step(key)().run(ctx, params)


def _noisy(sigma: float = 6.0, n: int = 64, level: float = 128.0,
           seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(level + rng.normal(0.0, sigma, (n, n)), 0, 255).astype(np.uint8)


def _striped(sigma: float = 1.5, n: int = 64, seed: int = 3) -> np.ndarray:
    """2px 寬、每 8px 一根的亮條紋 —— 「結構」的最小樣本。"""
    rng = np.random.default_rng(seed)
    img = np.zeros((n, n), np.float32)
    img[:, ::8] = 200.0
    img[:, 1::8] = 200.0
    return np.clip(img + 40.0 + rng.normal(0.0, sigma, (n, n)), 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# E. 磨掉的是雜訊還是訊號
# --------------------------------------------------------------------------- #
def test_filtering_pure_noise_removes_about_one_sigma():
    """把雜訊完全磨平的濾波器拿掉的正好是「一個 σ」那麼多 —— 這是刻度的定義。"""
    out = _run("denoise", _ctx(test=_noisy(sigma=6.0)), streams="test",
               method="median", ksize=3)
    assert 0.6 < out.features[REMOVED_OVER_NOISE] < 1.4, out.features


def test_wiping_out_the_structure_shows_up_as_a_huge_number():
    """**這一支就是這個數字存在的理由**（量出來的）。

    同一張有 2px 條紋的圖：`median ksize=7` 把條紋整個抹掉（拿走的東西是雜訊的
    幾十倍），`bilateral ksize=7` 留著它們（拿走的還是雜訊那個量級）。而**兩者在
    單顆畫面上都「看起來乾淨了」** —— 那正是問題。
    """
    img = _striped()
    wiped = _run("denoise", _ctx(test=img.copy()), streams="test",
                 method="median", ksize=7).features[REMOVED_OVER_NOISE]
    kept = _run("denoise", _ctx(test=img.copy()), streams="test",
                method="bilateral", ksize=7, strength=1.0
                ).features[REMOVED_OVER_NOISE]
    assert wiped > 10.0, wiped
    assert kept < 2.0, kept


def test_taking_out_more_than_two_sigma_says_so():
    out = _run("denoise", _ctx(test=_striped()), streams="test",
               method="gaussian", ksize=7)
    assert out.features[REMOVED_OVER_NOISE] > 2.0
    said = " ".join(out.meta.get("warnings") or [])
    assert "taking structure out as well as noise" in said
    assert "bilateral/nlm" in said, "那句話要講得出下一步怎麼做"


def test_a_quiet_filter_does_not_cry_wolf():
    out = _run("denoise", _ctx(test=_noisy(sigma=6.0)), streams="test",
               method="bilateral", ksize=5, strength=1.0)
    assert not (out.meta.get("warnings") or [])


def test_the_ratio_uses_the_sigma_measured_before_filtering():
    """濾過的圖已經沒有那個雜訊了，拿它當分母會讓比值無限膨脹。

    做法上這也是 `note_stream` 與 `after_stream` 兩個 hook 必須成對存在的理由：
    分子只有處理後才知道，分母只有處理前才對。
    """
    img = _noisy(sigma=6.0)
    out = _run("denoise", _ctx(test=img), streams="test", method="gaussian",
               ksize=5)
    sigma_before = out.meta["noise_sigma"]["test"]
    sigma_after = float(np.std(np.asarray(out.images["test"], np.float32)
                               - np.asarray(img, np.float32)))
    assert sigma_before > 4.0, "量到的是原圖的 σ"
    ratio = out.features[REMOVED_OVER_NOISE]
    assert ratio == pytest.approx(sigma_after / sigma_before, rel=0.2)


def test_ksize_1_removes_nothing_and_says_zero():
    out = _run("denoise", _ctx(test=_noisy()), streams="test",
               method="median", ksize=1)
    assert out.features[REMOVED_OVER_NOISE] == 0.0


def test_hot_pixels_reports_the_other_number_instead():
    """兩種方法問的是不同的問題，所以不硬湊成一個欄位。"""
    img = _noisy()
    img[10, 10] = 255
    out = _run("denoise", _ctx(test=img), streams="test", method="hot_pixels",
               ksize=3, threshold=4.0)
    assert "hot_px_frac" in out.features
    assert REMOVED_OVER_NOISE not in out.features


# --------------------------------------------------------------------------- #
# B. 兩條流還有多像
# --------------------------------------------------------------------------- #
def test_normalizing_both_streams_makes_the_pair_numbers_say_comparable():
    """**這一支是 B 的全部意義**：正規化前後那兩個數字要真的動。"""
    a = _noisy(sigma=4.0, level=90.0, seed=6)
    b = _noisy(sigma=12.0, level=180.0, seed=7)

    before = pair_similarity(a, b)
    assert before[PAIR_FEATURES[0]] > 50.0        # 背景差 90 個灰階
    assert before[PAIR_FEATURES[1]] > 2.0         # 起伏差三倍

    ctx = _ctx(test=a, ref=b)
    out = _run("normalize", ctx, streams="test,ref", method="zscore")
    assert out.features[PAIR_FEATURES[0]] < 3.0
    assert out.features[PAIR_FEATURES[1]] < 1.3


def test_a_card_that_leaves_them_incomparable_says_so_in_the_numbers():
    """只正規化 test、沒動 ref（那是 §3.2.5 要 lint 的那個錯）—— 一張卡處理兩條
    流的時候至少那兩個數字會講出結果。"""
    a = _noisy(sigma=4.0, level=90.0, seed=6)
    b = _noisy(sigma=12.0, level=180.0, seed=7)
    ctx = _ctx(test=a, ref=b)
    out = _run("tone", ctx, streams="test,ref", brightness=0.0)
    assert out.features[PAIR_FEATURES[0]] > 50.0, "沒有變可比，數字就不該說可比"


def test_the_pair_numbers_are_not_prefixed_with_a_stream_name():
    """它們講的是「這兩條之間」，掛在其中一條的名字下面會是錯的。"""
    cls = get_step("tone")
    feats = cls.resolve_features({"streams": "test,ref"})
    assert feats[-2:] == list(PAIR_FEATURES)
    assert not [f for f in feats if f.endswith("_pair_level_delta")]


def test_one_stream_alone_has_no_pair_to_report():
    cls = get_step("tone")
    assert PAIR_FEATURES[0] not in cls.resolve_features({"streams": "test"})
    out = _run("tone", _ctx(test=_noisy()), streams="test", brightness=1.0)
    assert set(out.features) == {CLIP_FRAC}


def test_identical_images_are_perfectly_comparable():
    img = _noisy()
    got = pair_similarity(img, img.copy())
    assert got[PAIR_FEATURES[0]] == 0.0
    assert got[PAIR_FEATURES[1]] == pytest.approx(1.0)


def test_two_flat_images_are_not_a_division_by_zero():
    """兩邊都平的話「差幾倍」沒有意義 —— 回 1（一樣）而不是 inf。

    inf 會一路活到某個分數表達式才變成 nan，而那時候的錯誤訊息指向表達式，
    不指向這裡。
    """
    got = pair_similarity(np.full((8, 8), 100, np.uint8),
                          np.full((8, 8), 100, np.uint8))
    assert got[PAIR_FEATURES[1]] == 1.0
    assert np.isfinite(list(got.values())).all()


def test_the_two_images_do_not_have_to_be_the_same_size():
    """patch 對 RSEM 就是不一樣大（§3.1.9）—— 量的是各自的整體統計。"""
    got = pair_similarity(_noisy(n=64), _noisy(n=200))
    assert set(got) == set(PAIR_FEATURES)


def test_big_images_are_sampled_so_this_stays_cheap():
    """這是一個**診斷**，而它要對 2000x2000 的 RSEM 影像也便宜到每顆都算。

    取樣是決定性的（等間隔），所以同一張圖永遠取到同一批畫素 —— 不然
    `to_json_dict → from_json_dict` 是 identity 這條規則就會在 workers=2 上破掉。
    """
    big = _noisy(n=400)                     # 160000 > PAIR_SAMPLE_MAX
    assert big.size > PAIR_SAMPLE_MAX
    first = pair_similarity(big, big.copy())
    again = pair_similarity(big, big.copy())
    assert first == again
    # 取樣過的統計要跟全圖的統計接近（不然這個便宜是白省的）
    full = pair_similarity(big[:200, :200], big[:200, :200])
    assert full[PAIR_FEATURES[1]] == pytest.approx(first[PAIR_FEATURES[1]], rel=0.1)


def test_an_empty_stream_reports_nothing_rather_than_a_fake_zero():
    assert pair_similarity(None, _noisy()) == {}
    assert pair_similarity(np.zeros((0, 0), np.uint8), _noisy()) == {}
