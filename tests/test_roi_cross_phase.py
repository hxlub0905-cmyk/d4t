# F8 第六輪：交錯的 pitch 分不出相位時要說出來，而不是猜一個。
"""使用者回報：「藍框跟線有時候會 shift，如果有 shift ROI 就會出現在錯誤的
位置上，尤其我瀏覽常常出現在 y 方向上（看起來是有兩種 pitch 造成的）。」

實測（EPI 間距 40/33、一個週期 73 px）：

    64 px 的 patch，30 種 crop → **錯位 3 次**，離真值最遠 33.5 px，
    而 ``pitch_error`` 回報 **0.00**。

原因不是計算錯了，是**問題本身沒有答案**：「寬、窄、寬、窄」有兩個相，而分辨
它們唯一的證據是相鄰兩根線之間的距離 —— 64 px 裡只放得下一根完整的線，兩個相
一樣貼合。程式挑了一個，然後**把那根看得見的線搬到錯的位置**。

第二件事：挑相位的分數以前用中位數，而中位數對「其中一根對不上」是免疫的 ——
那正好是相位錯掉的唯一症狀。實測三根線的例子裡，錯的那個相有一根差 12 px、
另外兩根 0，中位數 0.000，跟正確的相**一模一樣**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.algo import grid as algo_grid  # noqa: E402

P1, P2, STRIPE_W = 40.0, 33.0, 16


def _epi(order, oy: int, size: int, noise: float = 3.0, seed: int = 0):
    """橫的 EPI 條紋，間距在 ``order`` 兩個值之間交錯。回 (影像, 真實中心)。"""
    rng = np.random.default_rng(seed)
    img = np.full((size, size), 90.0, np.float32)
    img[:, np.arange(size) % 24 < 8] = 220.0          # 直的 MG（不影響 y 投影）
    cs, c, i = [], -float(oy), 0
    while c < size + 80:
        cs.append(c)
        c += order[i % 2]
        i += 1
    for c in cs:
        lo, hi = max(0, int(round(c - STRIPE_W / 2))), int(round(c + STRIPE_W / 2))
        if min(size, hi) > lo:
            img[lo:min(size, hi), :] = 180.0
    return (img + rng.normal(0, noise, (size, size)).astype(np.float32),
            [c for c in cs if 0 <= c < size])


def _worst(s, truth, size) -> float:
    got = [(a + b) / 2.0 for a, b in s.selected if a > .5 and b < size - .5]
    if not got or not truth:
        return -1.0
    return max(min(abs(c - t) for t in truth) for c in got)


# --------------------------------------------------------------------------- #
# 1. 分不出來的時候不要猜
# --------------------------------------------------------------------------- #
def test_a_patch_too_small_to_tell_the_phase_says_so():
    """一根完整的線問不出「寬的在上還是窄的在上」。"""
    img, _truth = _epi((33, 40), 0, 64)
    s = algo_grid.find_stripes(img, axis="y", select="brightest",
                               pitch=P1, pitch_2=P2)
    assert s.pitch_note, "分不出相位卻沒有講"
    assert "two whole stripes" in s.pitch_note or "equally well" in s.pitch_note
    assert s.filled == 0, "分不出相位還照樣補線"


def test_the_visible_stripe_is_not_moved_when_the_phase_is_unknown():
    """這是使用者真正看到的東西：**看得見的那根線被搬走了**。

    相位不確定時晶格是猜的，而套用一個猜的晶格會把影像上明明看得到的那根線
    移到別的地方 —— 框跟著走，於是 ROI 落在錯的位置。
    """
    img, truth = _epi((33, 40), 0, 64)
    plain = algo_grid.find_stripes(img, axis="y", select="brightest")
    s = algo_grid.find_stripes(img, axis="y", select="brightest",
                               pitch=P1, pitch_2=P2)
    assert s.selected == plain.selected, (
        "相位不確定時應該原樣用影像量到的：%s vs %s" % (s.selected, plain.selected))
    assert _worst(s, truth, 64) < 2.0


def test_it_still_locks_on_when_there_is_enough_to_go_on():
    """不能因為「小心一點」就把整個功能關掉 —— 看得到兩根以上就要用。"""
    img, truth = _epi((40, 33), 9, 160)
    s = algo_grid.find_stripes(img, axis="y", select="brightest",
                               pitch=P1, pitch_2=P2)
    assert not s.pitch_note, s.pitch_note
    assert s.pitches_used == [P1, P2]
    assert _worst(s, truth, 160) < 2.0


def test_every_crop_lands_in_the_right_place():
    """使用者原話：「我瀏覽常常出現在 y 方向上」—— 那是逐顆 crop 不同造成的，
    所以驗收也要逐顆掃過去，不能只測一種相位。"""
    bad = []
    for size in (64, 128, 160):
        for order in [(40, 33), (33, 40)]:
            for oy in (0, 9, 18, 27, 36):
                img, truth = _epi(order, oy, size)
                s = algo_grid.find_stripes(img, axis="y", select="brightest",
                                           pitch=P1, pitch_2=P2)
                e = _worst(s, truth, size)
                if e > 2.0:
                    bad.append((size, order[0], oy, round(e, 2)))
    assert not bad, "錯位 %d 次：%s" % (len(bad), bad)


def test_the_phase_is_ranked_by_something_a_single_miss_shows_up_in():
    """中位數對「其中一根對不上」免疫，而那是相位錯掉的**唯一**症狀。

    三根線、間距 24/36：錯的相有一根差 12 px、另外兩根 0 —— 中位數 0.000，
    跟正確的相一模一樣。所以挑相位不能用中位數（判合不合仍然用，那是
    另一個問題：一根被缺陷撐大的線不該讓整份 recipe 失效）。
    """
    size = 128
    rng = np.random.default_rng(1)
    img = np.full((size, size), 90.0, np.float32)
    for c in (10.5, 34.5, 94.5):            # 中間那根（58.5）不見了
        img[int(c - 5):int(c + 5), :] = 190.0
    img += rng.normal(0, 2.0, (size, size)).astype(np.float32)

    s = algo_grid.find_stripes(img, axis="y", select="brightest",
                               pitch=24.0, pitch_2=36.0)
    got = sorted(round((a + b) / 2.0) for a, b in s.selected)
    for want in (10, 34, 94):
        assert min(abs(c - want) for c in got) <= 2, (
            "看得見的線被搬走了：%s" % got)


# --------------------------------------------------------------------------- #
# 2. 「藍框跟線 shift」要講出數字
# --------------------------------------------------------------------------- #
def test_how_far_the_lattice_moved_things_is_reported():
    """shift 是刻意的（次像素精修 + 對齊到你給的 pitch），但沒講出來就只是
    「怪」—— 而「怪」的下一步通常是去亂調敏感度。"""
    img, _ = _epi((40, 33), 9, 160)
    snapped = algo_grid.find_stripes(img, axis="y", select="brightest",
                                     pitch=P1, pitch_2=P2)
    plain = algo_grid.find_stripes(img, axis="y", select="brightest")
    assert snapped.snap_shift > 0.0
    assert plain.snap_shift == 0.0, "沒有給 pitch 就沒有晶格，不該報搬移"


# --------------------------------------------------------------------------- #
# 3. 「量給我填」
# --------------------------------------------------------------------------- #
def test_it_can_measure_a_plain_pitch():
    assert algo_grid.measure_pitches([0, 24, 48, 72, 96]) == (24.0, 0.0)


def test_it_can_measure_two_alternating_pitches():
    a, b = algo_grid.measure_pitches([0, 40, 73, 113, 146])
    assert (round(a), round(b)) == (40, 33)


def test_a_gap_in_the_row_does_not_become_a_second_pitch():
    """缺一根就多一個「兩倍」的間距。天真的中位數會被它拉走，而按奇偶分組
    更糟 —— 它會把那個兩倍當成「第二種 pitch」然後回一個假的交錯。"""
    assert algo_grid.measure_pitches([0, 24, 72, 96]) == (24.0, 0.0)
    a, b = algo_grid.measure_pitches([0, 24, 48, 96, 120])
    assert b == 0.0 and round(a) == 24


def test_two_gaps_are_not_enough_to_claim_alternating():
    """「一寬一窄」跟「其中一個是雜訊」分不開，而後者常見得多。
    要看到它**重複一次**（兩組各至少兩個）才敢說是交錯。"""
    a, b = algo_grid.measure_pitches([0, 40, 73])
    assert b == 0.0, "只看到兩個間距就宣稱交錯"


def test_measuring_ignores_a_stripe_cut_by_the_image_edge():
    """半根線量到的中心依定義是偏的，而這個數字是要拿去填回參數格的。"""
    size = 160
    img, _ = _epi((30, 30), 0, size)        # 第一根中心在 0 → 只露一半
    s = algo_grid.find_stripes(img, axis="y", select="brightest")
    assert s.pitch_measured == pytest.approx(30.0, abs=1.0), s.pitch_measured


def test_a_real_alternating_row_is_not_mistaken_for_a_wrong_pitch():
    """量到的是「相鄰兩根有多遠」，而交錯的排法裡那個值就是兩個 pitch 裡**小的
    那一個**。拿它去對平均的話，一排完全正常的 40/33 會算出 0.83，而
    「挑錯組」的門檻在 0.80 —— 差一點就把正常的 layout 判成錯的。
    兩邊都取 min 才是同一件事的兩個說法。"""
    img, _ = _epi((40, 33), 9, 160)
    s = algo_grid.find_stripes(img, axis="y", select="brightest",
                               pitch=P1, pitch_2=P2)
    assert s.pitch_disagrees is False, "比值 %.2f" % s.pitch_ratio
    assert s.pitch_ratio == pytest.approx(1.0, abs=0.15)


# --------------------------------------------------------------------------- #
# 4. 一個 pitch 描述不了交錯的排（使用者：「下一張又會歪一點」）
# --------------------------------------------------------------------------- #
def _crops(size: int = 128):
    return [(o, oy) for o in [(40, 33), (33, 40)] for oy in range(0, 40, 4)]


def test_one_pitch_for_an_alternating_row_is_refused():
    """最難自己發現的一種。單一 pitch 的晶格套在「寬、窄、寬、窄」上，一半的
    線對得上、另一半差半個差距 —— 而 ``pitch_error`` 取中位數，剛好落在中間，
    過得了容差。實測 40/33 的 EPI 只填 40：誤差中位 6.50 px、最大 7.51，
    20 種 crop **一次都沒被擋下來**。
    """
    caught = 0
    for order, oy in _crops():
        img, _ = _epi(order, oy, 128)
        s = algo_grid.find_stripes(img, axis="y", select="brightest", pitch=P1)
        caught += bool(s.trust_note)
    assert caught >= 19, "20 種 crop 只擋下 %d 種" % caught


def test_filling_in_the_average_is_refused_too():
    """「歪一點」講的多半是這一種：填兩者的平均，誤差 3–4 px。
    那比只填一個小，但它一樣是逐顆不同的系統性偏差。"""
    caught = 0
    for order, oy in _crops():
        img, _ = _epi(order, oy, 128)
        s = algo_grid.find_stripes(img, axis="y", select="brightest",
                                   pitch=(P1 + P2) / 2.0)
        caught += bool(s.trust_note)
    assert caught >= 18, "20 種 crop 只擋下 %d 種" % caught


def test_it_says_the_two_spacings_when_it_can_measure_them():
    """使用者原話：「我不知道怎麼設定」。答案本來就在這條曲線上 ——
    講出來比只說「這個 pitch 不對」有用得多。"""
    img, _ = _epi((40, 33), 9, 160)
    s = algo_grid.find_stripes(img, axis="y", select="brightest", pitch=P1)
    assert "alternating" in s.trust_note
    assert "40" in s.trust_note and "33" in s.trust_note
    assert "every other one" in s.trust_note, "沒有講出要填哪一格"


def test_both_pitches_filled_in_is_accepted():
    """擋掉錯的不能連對的一起擋。"""
    for order, oy in _crops():
        img, _ = _epi(order, oy, 128)
        s = algo_grid.find_stripes(img, axis="y", select="brightest",
                                   pitch=P1, pitch_2=P2)
        assert not s.trust_note, "%s %s → %s" % (order, oy, s.trust_note)


def test_a_normal_row_is_not_refused_for_one_odd_stripe():
    """一根被缺陷撐大的線不該讓整份 recipe 失效 —— 這條檢查問的是
    「是不是**一半**都歪了」，不是「有沒有一根歪」。"""
    img, _ = _epi((30, 30), 5, 160)
    img[60:78, :] = 180.0                      # 一根特別胖
    s = algo_grid.find_stripes(img, axis="y", select="brightest", pitch=30.0)
    assert not s.trust_note, s.trust_note
    assert s.misfit <= algo_grid.MISFIT_FRAC


def test_a_pitch_that_does_not_divide_evenly_is_not_refused():
    """29.333（1.5 nm/px 配 44 nm）是站點真實的數字 —— 它不能被當成「對不上」。"""
    img, _ = _epi((29, 29), 3, 160)
    s = algo_grid.find_stripes(img, axis="y", select="brightest", pitch=29.333)
    assert not s.trust_note, s.trust_note
