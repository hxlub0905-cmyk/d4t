"""Tests for d4t.core.algo.period and .golden (vendored from
cell-period-estimator)."""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.algo.golden import (
    candidate_periods,
    ghosting_score,
    refine_period,
    stack_agreement,
    stack_cells,
    tile_coords,
)
from d4t.core.algo.period import choose_origin, estimate_period

PX, PY = 24, 32


@pytest.fixture(scope="module")
def grid_image():
    """Synthetic 2-D cell grid: bright rectangle per (PX x PY) cell + noise."""
    rng = np.random.default_rng(42)
    h, w = 320, 288
    img = np.full((h, w), 40, np.float64)
    for y0 in range(0, h - PY + 1, PY):
        for x0 in range(0, w - PX + 1, PX):
            img[y0 + 8:y0 + 24, x0 + 6:x0 + 18] = 200
    img += rng.normal(0, 3, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def line_space_image():
    """Vertical line/space pattern: period 20 along X, flat along Y."""
    rng = np.random.default_rng(43)
    img = np.full((256, 256), 30, np.float64)
    for x0 in range(0, 256, 20):
        img[:, x0:x0 + 10] = 220
    img += rng.normal(0, 2, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_estimate_period_grid_xy(grid_image):
    r = estimate_period(grid_image)
    assert r.axis_mode == "XY"
    assert r.px is not None and abs(r.px - PX) <= 1
    assert r.py is not None and abs(r.py - PY) <= 1
    assert r.confidence_x > 50 and r.confidence_y > 50
    assert (r.px, r.py) == r.candidates[0]


def test_estimate_period_line_space_x_only(line_space_image):
    r = estimate_period(line_space_image)
    assert r.axis_mode == "X"
    assert r.px is not None and abs(r.px - 20) <= 1
    assert r.py is None


def test_estimate_period_flat_none():
    flat = np.full((64, 64), 128, dtype=np.uint8)
    r = estimate_period(flat)
    assert r.axis_mode == "NONE"
    assert r.px is None and r.py is None
    assert "no periodic structure detected" in r.warnings


def test_correct_period_stacks_sharper(grid_image):
    good = stack_cells(grid_image, PX, PY)
    bad = stack_cells(grid_image, PX + 3, PY + 3)
    assert good.shape == (PY, PX)
    _, lap_good, edge_good = ghosting_score(good)
    score_bad, lap_bad, edge_bad = ghosting_score(bad)
    assert lap_good > 2.0 * lap_bad     # ghosting blurs the wrong-period stack
    assert edge_good > edge_bad
    score_good = ghosting_score(good)[0]
    assert score_good > score_bad


def test_refine_period_recovers_truth(grid_image):
    bpx, bpy, blv = refine_period(grid_image, PX - 2, PY - 2, search=4)
    assert (bpx, bpy) == (PX, PY)
    assert blv > 0


def test_tile_coords_complete_cells_only(grid_image):
    coords = tile_coords(grid_image.shape, PX, PY)
    h, w = grid_image.shape
    assert len(coords) == (w // PX) * (h // PY)
    assert all(x + PX <= w and y + PY <= h for x, y in coords)
    assert tile_coords(grid_image.shape, 0, 5) == []


def test_stack_cells_deterministic_sampling(grid_image):
    a = stack_cells(grid_image, PX, PY, sample_n=10, seed=5)
    b = stack_cells(grid_image, PX, PY, sample_n=10, seed=5)
    assert np.array_equal(a, b)


def test_candidate_periods_and_origin():
    cands = candidate_periods(PX, PY, lo=4, hi=128)
    assert cands[0] == (PX, PY)
    assert len(cands) == len(set(cands))
    assert all(4 <= a <= 128 and 4 <= b <= 128 for a, b in cands)
    assert (PX // 2, PY // 2) in cands and (2 * PX, 2 * PY) in cands
    # choose_origin is the documented (0, 0) stub until the M4 phase search
    assert choose_origin((320, 288), PX, PY) == (0, 0)


# --------------------------------------------------------------------------- #
# stack_agreement —— 「疊得準不準」（F40，2026-08-27）
#
# 為什麼要有第二個指標：`ghosting_score` 量的是「疊完那張圖有多少邊緣能量」，
# 而那**不是**「那幾格有沒有對齊」。兩者在**線／間距圖**上分得最開，而這個
# 形狀在 F40 之前完全沒有測試碰過（這個檔案用 2D 方格、`test_phase_origin`
# 用圓角方格、`test_roi_template` 的條紋圖只斷言 `ghosting > 50` 從不比較）。
#
# 真正發現它的路徑：`test_ui_f7_12_template.py` 有一支測試的斷言全在
# `if gc.ghosting < 40` 裡，而那個條件恆為 False —— 整支恆綠、零斷言。
# --------------------------------------------------------------------------- #
def test_a_perfect_stack_agrees_completely():
    """健全性控制：零雜訊 ＋ 正確週期 = 每一格一模一樣 = 1.0。

    ⚠ **這一條是先寫的，而它抓到了第一版。** 第一版把 `tile_coords` 回的
    ``(x, y)`` 拆成 ``(y, x)``，於是這個案例只拿到 0.049 而錯的週期拿 0.119。
    沒有一個「已知答案必須是多少」的控制，那個指標就會被交出去。
    """
    clean = np.full((256, 256), 30, np.uint8)
    for x0 in range(0, 256, 20):
        clean[:, x0:x0 + 10] = 220
    assert stack_agreement(clean, 20, 256) == pytest.approx(1.0, abs=1e-6)


def test_a_wrong_period_does_not_agree(line_space_image):
    """不成比例的週期 → 格子彼此對不上 → 趨近 0。"""
    assert stack_agreement(line_space_image, 20, 256) > 0.9
    for wrong in (23, 27, 30):
        assert stack_agreement(line_space_image, wrong, 256) < 0.1, wrong


def test_a_whole_multiple_of_the_period_still_agrees(line_space_image):
    """2× 的 cell **不是錯的** —— 使用者的原話就是他有時候要一個大的。

    所以這一條不是漏抓，是這個指標刻意不管的事：「cell 是 k 倍」由
    `template.cell_self_period` 講（那張卡上的 k× 提示）。
    """
    assert stack_agreement(line_space_image, 40, 256) > 0.9


def test_the_sharpness_score_is_inverted_on_a_line_space_pattern(
        line_space_image):
    """**這是那個 bug 本身。** 現行的銳利度分數在這張圖上分不出對錯。

    把它跟一個固定門檻比（對話框以前做的事）因此沒有意義 —— 而
    `stack_agreement` 在同一組數字上分得乾乾淨淨。
    """
    right = ghosting_score(stack_cells(line_space_image, 20, 256))[0]
    wrong = ghosting_score(stack_cells(line_space_image, 23, 256))[0]
    assert wrong > 90.0 and right > 90.0, (right, wrong)
    assert abs(right - wrong) < 5.0, \
        "銳利度分數本來就分不出這兩個 —— 分得出來的話這條測試該重寫"
    assert stack_agreement(line_space_image, 20, 256) > 0.9
    assert stack_agreement(line_space_image, 23, 256) < 0.1


def test_pure_noise_never_looks_well_stacked():
    """**最能說明問題的一個數字。**

    完全沒有東西可疊的時候，現行分數會隨雜訊變大而**變好**（σ=60 拿 100 /
    100，也就是「疊得非常準」）。一致性不會 —— 它一直是 0。
    """
    sharp, agree = [], []
    for sigma in (2.0, 20.0, 60.0):
        flat = np.clip(np.random.default_rng(7).normal(128, sigma, (256, 256)),
                       0, 255).astype(np.uint8)
        sharp.append(ghosting_score(stack_cells(flat, 20, 256))[0])
        agree.append(stack_agreement(flat, 20, 256))
    assert sharp[0] < 10.0 and sharp[-1] > 95.0, sharp
    assert max(agree) < 0.05, agree


def test_nothing_stacked_is_not_agreement():
    """放不下兩格、或整張是平的 —— 那是「沒有證據」，不是「完全一致」。

    回 1.0 的話，一張空白影像會拿到滿分而畫面上說它疊得完美。
    """
    clean = np.full((256, 256), 30, np.uint8)
    for x0 in range(0, 256, 20):
        clean[:, x0:x0 + 10] = 220
    assert stack_agreement(clean, 200, 256) == 0.0     # 只放得下一格
    assert stack_agreement(np.full((256, 256), 77, np.uint8), 20, 256) == 0.0


def test_the_floor_correction_is_what_makes_it_comparable():
    """``1/n`` 的地板不扣掉的話，門檻在每一種影像尺寸上意思都不一樣。

    ``n`` 格互不相關時 ``var(mean) ≈ var(cell)/n`` —— 所以只放得下兩格的小圖
    天生就有 0.5。這一條用**兩格**的雜訊圖鎖住它：扣完必須是 0，而扣之前是
    0.5 上下。
    """
    flat = np.clip(np.random.default_rng(11).normal(128, 18, (40, 81)),
                   0, 255).astype(np.uint8)
    assert len(tile_coords(flat.shape, 28, 40)) == 2, "前提：正好兩格"
    assert stack_agreement(flat, 28, 40) < 0.05

    cells = [flat[0:40, x:x + 28].astype(np.float64)
             for (x, _y) in tile_coords(flat.shape, 28, 40)]
    raw = (np.stack(cells).mean(axis=0).var()
           / np.mean([c.var() for c in cells]))
    assert 0.35 < raw < 0.65, \
        "沒扣地板的話兩格的雜訊圖大約是 0.5（raw=%.3f）" % raw
