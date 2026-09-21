"""`period.confidence_at` —— **打進去的那個週期，在這張圖上拿幾分**（F120）。

使用者 2026-09-21：「自定義 period 右上可否也能算 confidence？」

⚠ 這一支守的是**同尺度**，不是「有數字」。整個功能的價值在於那兩個數字
可以直接比（「你打的 45 得 0，量到的 60 得 92」）；一旦它變成另一套算法算
出來的另一種分數，畫面上就會有兩個長得一樣、意思不一樣的數字 —— 而那比
沒有分數更糟。
"""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.algo import period as algo_period
from d4t.core.algo import template as algo_template


def tiles(px: int = 60, py: int = 44, w: int = 900, h: int = 700,
          seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    img = (110 + 55 * (((x % px) < px * 0.42) + 0.8 * ((y % py) < py * 0.5))
           + rng.normal(0, 5, (h, w)))
    return np.clip(img, 0, 255).astype(np.uint8)


def test_at_the_measured_lag_it_reproduces_the_engines_own_number():
    """**這一條是整支測試的理由。**

    差一分都不行：這不是「差不多的第二意見」，它就是 `_analyze_axis` 的尾巴
    在另一個 lag 上取值。對不上就表示中間有人複製了一份算法。
    """
    img = tiles()
    m = algo_template.measure_period(img)
    assert algo_period.confidence_at(img, m.px, "x") == pytest.approx(m.conf_x)
    assert algo_period.confidence_at(img, m.py, "y") == pytest.approx(m.conf_y)


def test_the_right_period_scores_higher_than_a_nearby_wrong_one():
    """±1 px 就要看得出來 —— 使用者打錯一點點的時候正是這種。"""
    img = tiles(px=60)
    right = algo_period.confidence_at(img, 60, "x")
    assert right > algo_period.confidence_at(img, 59, "x")
    assert right > algo_period.confidence_at(img, 61, "x")


def test_an_anti_phase_lag_scores_zero():
    """60 的圖打 45（不是諧波、剛好錯開）拿 0 —— **那一刻長條就該變紅**。"""
    assert algo_period.confidence_at(tiles(px=60), 45, "x") == 0.0


def test_a_harmonic_still_scores_well_because_it_really_does_repeat():
    """⚠ 120 在一張 60 的圖上**真的**每 120 px 重複一次。

    分數不該把它打成錯的 —— 它只是不是**基頻**。「使用者要兩根 MG 當一個
    cell」是 `template_dialog` 認可的用法，畫面上給它一個誠實的高分才對。
    """
    assert algo_period.confidence_at(tiles(px=60), 120, "x") > 50.0


def test_the_two_axes_are_asked_separately():
    img = tiles(px=60, py=44)
    assert algo_period.confidence_at(img, 44, "y") > 80.0
    assert algo_period.confidence_at(img, 44, "x") < 50.0


def test_sub_pixel_lags_land_between_the_two_whole_ones():
    """F105 之後週期可以是 79.5，所以 `61.5` 不能被無聲地當成 61。"""
    img = tiles(px=60)
    lo, hi = algo_period.confidence_at(img, 61, "x"), algo_period.confidence_at(img, 62, "x")
    mid = algo_period.confidence_at(img, 61.5, "x")
    assert min(lo, hi) <= mid <= max(lo, hi)


@pytest.mark.parametrize("img, lag", [
    (tiles(), 0.0),                                   # 沒打
    (tiles(), 1.5),                                   # 比 MIN_PERIOD_PX 還小
    (tiles(), 5000.0),                                # 比半張圖還長
    (np.zeros((60, 60), np.uint8), 10.0),             # 全平：沒有調變
    (np.zeros((0, 0), np.uint8), 10.0),               # 空的
    (np.zeros((4,), np.uint8), 10.0),                 # 不是 2D
])
def test_it_returns_zero_instead_of_raising(img, lag):
    """⚠ 這支東西掛在**每一次 refresh** 上，而使用者打字的中途什麼都可能是。

    拋例外的話壞掉的是整個視窗，而不是一格分數。
    """
    assert algo_period.confidence_at(img, lag, "x") == 0.0


def test_it_never_leaves_the_zero_to_one_hundred_scale():
    img = tiles()
    for lag in range(2, 200, 7):
        v = algo_period.confidence_at(img, lag, "x")
        assert 0.0 <= v <= 100.0, (lag, v)
