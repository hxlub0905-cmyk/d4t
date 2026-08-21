"""Tests for d4t.core.algo.shape — CD 無方向那一半的數學（F19 第二批第 1 步）。

合成圖形的面積與軸長是**已知的**，所以「量得準不準」是可以斷言的數字。
兩支印表的測試是這一份的重點：面積的量化誤差、以及 **bbox 對一個 L 形錯得
多離譜** —— 後者就是這一支存在的理由。
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from d4t.core.algo import shape as algo_shape


# --------------------------------------------------------------------------- #
# 合成圖形
# --------------------------------------------------------------------------- #
def canvas(size=64, bg=60.0):
    return np.full((size, size), float(bg), dtype=np.float64)


def add_ellipse(img, cx, cy, rx, ry, angle=0.0, amp=120.0, blur=0.0):
    """在 ``img`` 上蓋一個實心橢圓（角度是**逆時針**度）。

    ``blur`` 是邊有多糊。**要試門檻高度就一定要給它**：一個完全銳利的階梯，
    任何落在兩個準位之間的門檻都切出一模一樣的形狀（那是對的，不是 bug）。
    """
    import cv2

    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    t = math.radians(angle)
    dx, dy = xx - cx, yy - cy
    u = dx * math.cos(t) + dy * -math.sin(t)
    v = dx * math.sin(t) + dy * math.cos(t)
    bump = ((u / rx) ** 2 + (v / ry) ** 2 <= 1.0).astype(np.float64)
    if blur > 0:
        bump = cv2.GaussianBlur(bump, (0, 0), float(blur))
    img += amp * bump
    return img


def disc(size=64, d=20.0, **kw):
    img = canvas(size)
    return add_ellipse(img, size / 2.0, size / 2.0, d / 2.0, d / 2.0, **kw)


def square(size=96, side=30.0, amp=120.0):
    img = canvas(size)
    a = int(side)
    y0 = x0 = (size - a) // 2
    img[y0:y0 + a, x0:x0 + a] += amp
    return img


def l_shape(size=64, arm=26, thick=8, amp=120.0):
    """一個 L —— 它的 bounding box 會框到一大片背景。"""
    img = canvas(size)
    y0 = (size - arm) // 2
    x0 = (size - arm) // 2
    img[y0:y0 + arm, x0:x0 + thick] += amp          # 直的那一劃
    img[y0 + arm - thick:y0 + arm, x0:x0 + arm] += amp   # 橫的那一劃
    return img


def noisy(img, sigma, seed=0):
    return img + np.random.default_rng(seed).normal(0.0, sigma, img.shape)


# --------------------------------------------------------------------------- #
# 準位與極性
# --------------------------------------------------------------------------- #
def test_levels_come_from_the_border_and_a_percentile():
    img = disc(d=20.0)
    bg, fg, used = algo_shape.pick_levels(img)
    assert bg == pytest.approx(60.0, abs=1.0)
    assert fg == pytest.approx(180.0, abs=1.0)
    assert used == "bright"


def test_auto_polarity_picks_whichever_side_stands_out():
    bright = disc(d=20.0)
    assert algo_shape.pick_levels(bright)[2] == "bright"
    dark = canvas() * 0 + 200.0
    dark = add_ellipse(dark, 32, 32, 10, 10, amp=-140.0)
    assert algo_shape.pick_levels(dark)[2] == "dark"


def test_a_hot_pixel_does_not_move_the_foreground_level():
    """``fg`` 走百分位不走 max —— max 是極值統計量，一顆熱像素就搬得動它。"""
    img = disc(d=20.0)
    plain = algo_shape.pick_levels(img)[1]
    img[2, 2] = 4000.0
    assert algo_shape.pick_levels(img)[1] == pytest.approx(plain, abs=1.0)


# --------------------------------------------------------------------------- #
# 面積
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("d", [10.0, 16.0, 24.0, 32.0])
def test_area_matches_a_disc_of_known_size(d):
    res = algo_shape.measure_blob(disc(d=d))
    assert res.ok and res.reason == ""
    truth = math.pi * (d / 2.0) ** 2
    assert res.area == pytest.approx(truth, rel=0.06)
    assert algo_shape.equivalent_diameter(res.area) == pytest.approx(d, abs=0.6)


def test_area_quantisation_table(capsys):
    """面積的量化誤差表 —— **「不做次像素」那個決定的代價，量出來放著**。

    理論值約 ``2/√(πd)``：d=10 約 3.6%、d=30 約 2%。
    """
    rows = []
    for d in (8.0, 12.0, 20.0, 32.0):
        res = algo_shape.measure_blob(disc(size=96, d=d))
        truth = math.pi * (d / 2.0) ** 2
        rows.append((d, res.area, truth, (res.area - truth) / truth))
    print("\n  直徑   量到   真值     相對誤差")
    for d, got, truth, rel in rows:
        print("  %4.0f  %5d  %7.1f   %+6.2f%%" % (d, got, truth, rel * 100.0))
    for _d, _got, _truth, rel in rows:
        assert abs(rel) < 0.08


def test_the_l_shape_is_why_a_bounding_box_is_not_a_size(capsys):
    """**這一支就是無方向那一支存在的理由。**

    一個 L 的 bounding box 幾乎是它真實面積的三倍 —— 而那個數字看起來完全正常。
    """
    img = l_shape(arm=26, thick=8)
    res = algo_shape.measure_blob(img)
    assert res.ok
    truth = 26 * 8 + (26 - 8) * 8          # 兩劃扣掉重疊的角
    bbox = 26 * 26
    print("\n  真實面積 %d、bbox %d（%.1f 倍）、量到 %d"
          % (truth, bbox, bbox / truth, res.area))
    assert res.area == pytest.approx(truth, rel=0.06)
    assert bbox > res.area * 1.5           # bbox 錯得離譜，而它不會報錯


def test_area_survives_noise():
    for sigma in (2.0, 6.0):
        res = algo_shape.measure_blob(noisy(disc(d=24.0), sigma, seed=3))
        truth = math.pi * 12.0 ** 2
        assert res.ok, sigma
        assert res.area == pytest.approx(truth, rel=0.10), sigma


# --------------------------------------------------------------------------- #
# Feret
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("angle", [0.0, 30.0, 45.0, 90.0, 135.0])
def test_feret_is_rotation_invariant(angle):
    """一條 30×8 的細棒轉到哪裡，長短都是 30 與 8 —— bbox 不會。"""
    img = canvas(96)
    add_ellipse(img, 48, 48, 15.0, 4.0, angle=angle)
    res = algo_shape.measure_blob(img)
    assert res.ok
    assert res.feret_max == pytest.approx(30.0, abs=2.0)
    assert res.feret_min == pytest.approx(8.0, abs=2.0)


def test_feret_angle_says_which_way_it_is_stretched():
    for angle in (0.0, 45.0, 90.0, 120.0):
        img = canvas(96)
        add_ellipse(img, 48, 48, 18.0, 4.0, angle=angle)
        res = algo_shape.measure_blob(img)
        assert res.ok
        got = res.feret_angle % 180.0
        near = min(abs(got - angle), 180.0 - abs(got - angle))
        assert near < 8.0, (angle, got)


def test_a_disc_has_equal_ferets():
    res = algo_shape.measure_blob(disc(size=96, d=30.0))
    assert res.feret_max == pytest.approx(res.feret_min, rel=0.12)
    assert res.feret_max == pytest.approx(30.0, abs=1.5)


def test_feret_is_not_the_min_area_rectangle():
    """便利貼：``minAreaRect`` 的長邊**不是** max Feret。

    一個邊長 30 的正方形把差距講得最清楚 —— 最遠的兩點是**對角線**（42.4），
    而最小面積矩形的長邊是 30。拿後者當「這一團有多長」會小 30%，而它照樣是一個
    看起來完全正常的數字。（橢圓上兩者幾乎相同，所以它驗不出這件事。）
    """
    import cv2

    res = algo_shape.measure_blob(square(side=30.0))
    assert res.ok
    mask = np.zeros((96, 96), np.uint8)
    cv2.drawContours(mask, [res.contour.astype(np.int32)], -1, 1, -1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_NONE)
    rect_long = max(cv2.minAreaRect(contours[0])[1])
    assert res.feret_max == pytest.approx(30.0 * math.sqrt(2.0), abs=2.0)
    assert rect_long == pytest.approx(30.0, abs=1.5)
    assert res.feret_max > rect_long * 1.3
    # min Feret 則**等於**最小面積矩形的短邊（那是旋轉卡尺的標準結論）
    assert res.feret_min == pytest.approx(min(cv2.minAreaRect(contours[0])[1]),
                                          abs=1.5)


def test_feret_of_degenerate_input_does_not_raise():
    assert algo_shape.feret(np.empty((0, 2)))[0] == 0.0
    assert algo_shape.feret([[3.0, 4.0]])[0] == 0.0


# --------------------------------------------------------------------------- #
# 形狀
# --------------------------------------------------------------------------- #
def test_roundness_separates_a_blob_from_a_whisker():
    """``aspect`` 與 ``roundness`` 問的不是同一件事，所以兩個都留著。"""
    round_res = algo_shape.measure_blob(disc(size=96, d=30.0))
    bar = canvas(96)
    add_ellipse(bar, 48, 48, 20.0, 3.0)
    bar_res = algo_shape.measure_blob(bar)
    r_round = algo_shape.roundness(round_res.area, round_res.perimeter)
    r_bar = algo_shape.roundness(bar_res.area, bar_res.perimeter)
    assert r_round > 0.8
    assert r_bar < 0.6
    assert r_round > r_bar


def test_equivalent_diameter_and_roundness_survive_zero():
    assert algo_shape.equivalent_diameter(0) == 0.0
    assert algo_shape.roundness(0, 0) == 0.0


# --------------------------------------------------------------------------- #
# 拒絕的那幾種
# --------------------------------------------------------------------------- #
def test_a_flat_region_is_refused_rather_than_cut_in_half():
    """**Otsu 會照樣切一半，這裡不會。** 沒有前景的時候「最亮的 1%」永遠存在。"""
    res = algo_shape.measure_blob(noisy(canvas(64), 4.0, seed=1))
    assert not res.ok and res.reason == "flat"
    assert res.area == 0 and res.contour.size == 0


def test_noise_alone_never_produces_a_size():
    """跟線寬那一支 §6 是同一個坑的二維版 —— 逐 seed 掃過都不准過。"""
    for seed in range(6):
        res = algo_shape.measure_blob(noisy(canvas(64), 6.0, seed=seed))
        assert not res.ok, seed


def test_specks_below_min_area_are_not_blobs():
    """兩顆孤立的亮點不是一團 —— 而 3×3 中位數讓它們連 ``fg`` 都抬不動。"""
    img = canvas(64)
    img[10, 10] += 150.0
    img[40, 40] += 150.0
    res = algo_shape.measure_blob(img, min_quality=0.0)
    assert not res.ok and res.reason == "flat"

    # 有前景、但那一團小於 min_area。**要 3×3 才過得了那道中位數** —— 那也是
    # 這一支能認得的最小的一團（模組說明裡的「約 3×3」就是這個數字）。
    img2 = canvas(64)
    img2[31:34, 31:34] += 150.0            # 3×3 = 9 px
    assert algo_shape.measure_blob(img2, min_area=16).reason == "no_blob"
    assert algo_shape.measure_blob(img2, min_area=4).ok


def test_a_region_with_no_foreground_is_refused_even_with_the_floor_at_zero():
    """**兩道門檻缺一不可。** 使用者把相對那道關掉時，絕對那道還在。

    沒有這一道的話 ``fg == bg``、門檻落在背景那一格，於是**整塊區域**被切成
    一團 —— 面積 4096、形狀完美、每一顆都有。
    """
    flat = canvas(64)
    res = algo_shape.measure_blob(flat, min_quality=0.0)
    assert not res.ok and res.reason == "flat"


def test_a_region_too_small_says_so():
    assert algo_shape.measure_blob(np.zeros((2, 2))).reason == "too_small"
    assert algo_shape.measure_blob(np.zeros((5,))).reason == "too_small"


# --------------------------------------------------------------------------- #
# 幾團、挑哪一團、貼不貼邊
# --------------------------------------------------------------------------- #
def test_it_picks_the_blob_at_the_centre_and_says_how_many_there_were():
    """patch 以缺陷為中心裁切，所以中心那一團就是「這一顆」。

    ``pieces`` 是揭露這個自動決定的唯一線索。
    """
    img = canvas(96)
    add_ellipse(img, 48, 48, 8.0, 8.0)         # 中心那一團（小）
    add_ellipse(img, 80, 80, 13.0, 13.0)       # 角落那一團（大）
    res = algo_shape.measure_blob(img)
    assert res.ok and res.pieces == 2
    assert res.area == pytest.approx(math.pi * 64.0, rel=0.1)   # 挑了小的那個


def test_with_nothing_at_the_centre_it_falls_back_to_the_largest():
    img = canvas(96)
    add_ellipse(img, 20, 20, 6.0, 6.0)
    add_ellipse(img, 76, 76, 12.0, 12.0)
    res = algo_shape.measure_blob(img)
    assert res.ok and res.pieces == 2
    assert res.area == pytest.approx(math.pi * 144.0, rel=0.1)


def test_a_blob_running_off_the_frame_is_measured_but_flagged():
    """**跟線寬那一支的「拒絕」不一致是刻意的**（使用者 2026-08-21）。

    線寬拿畫面當邊是**發明**一個數字；這裡是一個誠實的下界，而旗子就在 CSV 上
    （同區域卡的 ``<name>_clipped``）。
    """
    img = canvas(64)
    add_ellipse(img, 58, 32, 14.0, 10.0)       # 右邊被切掉
    res = algo_shape.measure_blob(img)
    assert res.ok and res.touches_edge
    assert res.area > 0

    inside = algo_shape.measure_blob(disc(d=20.0))
    assert inside.ok and not inside.touches_edge


# --------------------------------------------------------------------------- #
# 門檻高度：跟線寬那一支同一支函式
# --------------------------------------------------------------------------- #
def test_the_height_knob_means_the_same_thing_as_on_the_line_branch():
    """高度一律**從暗算到亮**，所以亮的團拉高就變小、暗的孔拉高就變大。

    邊要是糊的才試得出來：完全銳利的階梯上，任何落在兩個準位之間的門檻都切出
    一模一樣的形狀（那是對的，不是 bug）。
    """
    bright = disc(size=96, d=30.0, amp=120.0, blur=2.0)
    lo = algo_shape.measure_blob(bright, frac=0.25).area
    mid = algo_shape.measure_blob(bright, frac=0.5).area
    hi = algo_shape.measure_blob(bright, frac=0.75).area
    assert lo > mid > hi

    hole = np.full((96, 96), 200.0)
    add_ellipse(hole, 48, 48, 15.0, 15.0, amp=-140.0, blur=2.0)
    d_lo = algo_shape.measure_blob(hole, target="dark", frac=0.25).area
    d_hi = algo_shape.measure_blob(hole, target="dark", frac=0.75).area
    assert d_hi > d_lo


def test_the_level_and_histogram_are_carried_for_the_panel():
    res = algo_shape.measure_blob(disc(d=20.0))
    counts, lo, hi = res.hist
    assert len(counts) == 40 and sum(counts) == 64 * 64
    assert lo <= res.level <= hi
    assert res.bg < res.level < res.fg


def test_quality_uses_the_same_formula_as_the_line_branch():
    from d4t.core.algo import edge as algo_edge

    clean = algo_shape.measure_blob(disc(d=24.0))
    assert clean.quality > 0.95
    assert clean.quality == pytest.approx(
        algo_edge.edge_quality(clean.fg - clean.bg, 0.0), abs=1e-9)
    noisy_res = algo_shape.measure_blob(noisy(disc(d=24.0), 8.0, seed=2))
    assert noisy_res.quality < clean.quality


def test_a_wandering_background_is_not_a_blob():
    """**低頻起伏是一階差分看不見的那一類雜訊。**

    只用逐點估計的話，一塊「背景在慢慢漂」的區域會拿到「對比 12、雜訊 0.1」
    ＝ 品質 0.72，過關，然後吐得出一個面積。實跑合成 lot 的 diff 上，12 顆假點
    **12 顆都量得出來**；加上空間那一項之後是 0 顆，而真缺陷仍然是 11/12。
    """
    def wander(seed, scale=3.0):
        import cv2

        r = np.random.default_rng(seed)
        return canvas(64) + cv2.GaussianBlur(
            r.normal(0.0, 5.0, (64, 64)), (0, 0), scale) * scale

    for seed in (7, 8, 9):
        res = algo_shape.measure_blob(wander(seed))
        assert not res.ok and res.reason == "flat", seed

    # 而**同樣起伏的背景上真的有一團**時照樣量得到
    with_blob = add_ellipse(wander(7), 32, 32, 8.0, 8.0, amp=90.0)
    got = algo_shape.measure_blob(with_blob)
    assert got.ok and got.area == pytest.approx(math.pi * 64.0, rel=0.25)


def test_the_two_noise_estimates_agree_on_white_noise():
    """取大的那一個不會讓乾淨／白雜訊的資料變嚴 —— 兩種估計在那裡本來就一致
    （實測 4.80 vs 4.59）。"""
    rng = np.random.default_rng(0)
    white = canvas(64) + rng.normal(0.0, 5.0, (64, 64))
    assert algo_shape._region_noise(white) == pytest.approx(5.0, rel=0.25)
    assert algo_shape._region_noise(canvas(64)) == 0.0
