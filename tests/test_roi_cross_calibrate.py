# F8 第七輪：一鍵校正 —— pitch 是設計常數，整批一起量。
"""使用者原話：「我不會只有一張 patch（可能有 50 張 100 張），直接用這些
patch calculate 就可以找出一個最好的設定？因為你現在的 Use 彼此算之間
還是有 variation。」

他說的 variation 是真的：單張量測有 ±0.5 px 的雜訊（邊界糊、crop 相位）。
而 pitch 是**設計常數** —— 這一批每一張量的都是同一個數字，聚合就把雜訊
除掉了。

第一版聚合「每張的結論」，在交錯的 layout 上安靜地錯掉：128px 配 40/33 的
patch 大多只看得到三根線，單張的結論是 36.5 —— 一個**沒有任何一對線真的距離
36.5** 的平均值，而且 50 張彼此完全同意這個錯的數字。所以聚合的是**原始間距**
（50 張 × 2~3 個 = 一百多個樣本，40 與 33 兩群一目了然）。

唯一的鐵則：**這批 patch 自己不同意的時候，不要硬給一個數字。**
不同意是資訊（一半量到 24、一半量到 12 = CPODE 而 kinds 沒設），
講出兩群比取一個落在其中一群上的中位數誠實得多。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.algo import grid as algo_grid  # noqa: E402

SIZE = 128


def _mg(ox=0, oy=0, pitch=24, w=8, cpode=(), noise=2.0, seed=0,
        size=SIZE) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((size, size), 90.0, np.float32)
    img[(np.arange(size) + oy) % 34 < 14, :] = 180.0
    img[:, (np.arange(size) + ox) % pitch < w] = 220.0
    for site in cpode:
        lo = site * pitch - ox
        if 0 <= lo < size:
            img[:, lo:lo + w] = 30.0
    return img + rng.normal(0, noise, (size, size)).astype(np.float32)


def _epi_alt(order, oy, size=SIZE, w=16, seed=0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((size, size), 90.0, np.float32)
    img[:, np.arange(size) % 24 < 8] = 220.0
    cs, c, i = [], -float(oy), 0
    while c < size + 80:
        cs.append(c)
        c += order[i % 2]
        i += 1
    for c in cs:
        lo, hi = max(0, int(round(c - w / 2))), min(size, int(round(c + w / 2)))
        if hi > lo:
            img[lo:hi, :] = 180.0
    return img + rng.normal(0, 3.0, (size, size)).astype(np.float32)


# --------------------------------------------------------------------------- #
# 1. 批次贏單張 —— 這個功能存在的理由
# --------------------------------------------------------------------------- #
def test_the_lot_agrees_on_one_number():
    rng = np.random.default_rng(1)
    imgs = [_mg(ox=int(rng.integers(0, 24)), oy=int(rng.integers(0, 34)),
                noise=float(rng.uniform(1.5, 5.0)), seed=i)
            for i in range(50)]
    cal = algo_grid.calibrate_axis(imgs, "x")
    assert cal.note == ""
    assert cal.pitch == pytest.approx(24.0, abs=0.2)
    assert cal.pitch_2 == 0.0
    assert cal.width == pytest.approx(8.0, abs=1.0)
    assert cal.n_used >= 45
    assert cal.agree > 0.9


def test_a_pitch_that_does_not_divide_evenly_survives():
    """29.333（1.5 nm/px 配 44 nm）—— 校正不能把它捨成整數。"""
    rng = np.random.default_rng(2)
    imgs = [_mg(ox=int(rng.integers(0, 29)), pitch=29, seed=i)
            for i in range(30)]
    cal = algo_grid.calibrate_axis(imgs, "x")
    assert cal.pitch == pytest.approx(29.0, abs=0.3)


# --------------------------------------------------------------------------- #
# 2. 交錯：單張看不出來的，一批看得出來
# --------------------------------------------------------------------------- #
def test_alternation_a_single_patch_cannot_see_is_found_by_the_lot():
    """這正是使用者的 y 方向。128px 配 40/33，大多數 patch 只看得到三根線 ——
    單張的「Use」給的是 36.5（兩個間距的中位數，一個不存在的值）。"""
    rng = np.random.default_rng(3)
    imgs = [_epi_alt([(40, 33), (33, 40)][int(rng.integers(0, 2))],
                     int(rng.integers(0, 40)), seed=i) for i in range(50)]

    # 前提先鎖住：單張確實大多看不出交錯（不然這條測試在測空氣）
    singles = sum(1 for im in imgs
                  if algo_grid.find_stripes(im, axis="y", select="brightest"
                                            ).pitch_measured_2 < 2.0)
    assert singles > 25, "單張大多看得出交錯？那批次的價值要重新量"

    cal = algo_grid.calibrate_axis(imgs, "y")
    assert cal.note == ""
    assert cal.pitch == pytest.approx(40.0, abs=0.5)
    assert cal.pitch_2 == pytest.approx(33.0, abs=0.5)


def test_missing_stripes_do_not_fake_an_alternation():
    """每張隨機淡掉一根 → 跨過去的間距是 48（2×24）。整數倍是「缺線」，
    不是「交錯」—— 設計出來的兩個尺寸不會剛好差整數倍。"""
    rng = np.random.default_rng(4)
    imgs = []
    for i in range(40):
        im = _mg(ox=int(rng.integers(0, 24)), seed=100 + i)
        k = int(rng.integers(0, 5))
        im[:, k * 24:k * 24 + 8] = 120.0
        imgs.append(im)
    cal = algo_grid.calibrate_axis(imgs, "x")
    assert cal.note == ""
    assert cal.pitch == pytest.approx(24.0, abs=0.3)
    assert cal.pitch_2 == 0.0, "缺線被當成第二種 pitch 了"


def test_gaps_across_skipped_cpode_sites_fold_back_into_one_pitch():
    """kinds 設對之後 CPODE 那格被正確跳過 —— 跨過它的間距是 48 或 72。
    那也是整數倍：同一排、同一個 pitch。"""
    rng = np.random.default_rng(5)
    imgs = [_mg(ox=int(rng.integers(0, 24)),
                cpode=(tuple(int(v) for v in rng.integers(0, 6, 2))
                       if i % 2 else ()), seed=i) for i in range(50)]
    cal = algo_grid.calibrate_axis(imgs, "x", kinds=3)
    assert cal.note == ""
    assert cal.pitch == pytest.approx(24.0, abs=0.3)
    assert cal.pitch_2 == 0.0


# --------------------------------------------------------------------------- #
# 3. 批次不同意 → 拒絕，而且講出兩群
# --------------------------------------------------------------------------- #
def test_a_lot_that_disagrees_is_refused_with_both_camps_named():
    """一半的 patch 有 CPODE 而 kinds 沒設 → 那一半量到半個 pitch。
    每張 patch **自己**是一致的（間距全 12 或全 24），所以這不是空間結構，
    是批次在不同意 —— 中位數會落在其中一群上，看起來像個答案，但它不是。"""
    rng = np.random.default_rng(6)
    imgs = [_mg(ox=int(rng.integers(0, 24)),
                cpode=(tuple(int(v) for v in rng.integers(0, 6, 2))
                       if i % 2 else ()), seed=i) for i in range(50)]
    cal = algo_grid.calibrate_axis(imgs, "x", kinds=0)
    assert cal.pitch == 0.0, "不同意還是給了數字"
    assert "do not agree" in cal.note
    assert "12" in cal.note and "24" in cal.note, cal.note
    assert "how many kinds" in cal.note, "沒講下一步"


def test_a_featureless_lot_measures_nothing_instead_of_noise():
    """純雜訊的批「量得到」一個 8.4 px 的假 pitch（雜訊邊緣被 min_gap 排成
    等距）—— 信心閘門要把它擋在聚合之外。"""
    flat = [np.random.default_rng(i).normal(120, 4, (SIZE, SIZE))
            .astype(np.float32) for i in range(20)]
    cal = algo_grid.calibrate_axis(flat, "x")
    assert cal.pitch == 0.0
    assert "had stripes to measure" in cal.note


def test_a_few_bad_patches_do_not_spoil_the_lot():
    """校正是統計 —— 混進幾張沒有結構的，答案不變、只是樣本少幾張。"""
    rng = np.random.default_rng(7)
    good = [_mg(ox=int(rng.integers(0, 24)), seed=i) for i in range(30)]
    flat = [np.random.default_rng(90 + i).normal(120, 4, (SIZE, SIZE))
            .astype(np.float32) for i in range(8)]
    cal = algo_grid.calibrate_axis(good + flat, "x")
    assert cal.note == ""
    assert cal.pitch == pytest.approx(24.0, abs=0.3)
    assert cal.n_used == 30 and cal.n_total == 38


def test_too_few_usable_patches_is_said_not_papered_over():
    imgs = [_mg(seed=i) for i in range(2)]
    cal = algo_grid.calibrate_axis(imgs, "x")
    assert cal.pitch == 0.0
    assert "2 of 2" in cal.note
