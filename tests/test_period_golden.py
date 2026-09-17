"""Tests for d4t.core.algo.period and .golden (vendored from
cell-period-estimator)."""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.algo.golden import (
    ghosting_score,
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


def test_choose_origin_without_pixels_is_zero():
    """沒有給影像就沒有相位可搜 —— 回 ``(0, 0)``，不是猜一個。

    `choose_origin` 的相位搜尋要看畫素（M4 補完的）；`image=None` 是呼叫端
    只知道形狀時的那條路。真正的搜尋由 `tests/test_phase_origin.py` 守。
    """
    assert choose_origin((320, 288), PX, PY) == (0, 0)


# --------------------------------------------------------------------------- #
# stack_agreement —— 「疊得準不準」（F40，2026-08-27）
#
# 為什麼要有第二個指標：`ghosting_score` 量的是「疊完那張圖有多少邊緣能量」，
# 而那**不是**「那幾格有沒有對齊」。兩者在**線／間距圖**上分得最開，而這個
# 形狀在 F40 之前完全沒有測試碰過（這個檔案用 2D 方格、`test_phase_origin`
# 用圓角方格、`test_roi_template` 的條紋圖只斷言 `ghosting > 50` 從不比較）。
#
# 真正發現它的路徑：`test_ui_template_dialog.py` 有一支測試的斷言全在
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


# --------------------------------------------------------------------------- #
# F86：疊得快，但**一個位元都不准變**
# --------------------------------------------------------------------------- #
def _periodic(h: int, w: int) -> np.ndarray:
    """一張有真週期的圖（`grid_image` 那個 fixture 的函式版）。"""
    img = np.zeros((h, w), np.uint8)
    img[::PY, :] = 255
    img[:, ::PX] = 255
    return img


def _stack_the_old_way(gray, px, py, origin=(0, 0)):
    """F86 之前的寫法：每一格切一份出來、堆起來、對 axis 0 取平均。

    留在測試裡當**參照實作** —— 「快了」是廉價的，「還是同一個答案」才是
    這一刀成立的條件。
    """
    from d4t.core.algo.golden import _to_gray, tile_coords
    g = _to_gray(gray)
    coords = tile_coords(g.shape, px, py, origin)
    if not coords:
        return np.zeros((max(py, 1), max(px, 1)), np.uint8)
    cells = np.stack([g[y:y + py, x:x + px].astype(np.float64)
                      for (x, y) in coords])
    return np.clip(cells.mean(axis=0), 0, 255).astype(np.uint8)


@pytest.mark.parametrize("side", [300, 577, 1024])
@pytest.mark.parametrize("pitch", [(48, 48), (31, 17), (7, 7)])
def test_the_fast_stack_is_byte_for_byte_the_old_one(side, pitch):
    """reshape 版跟逐格版**逐位元組相同**（F86）。

    這一條是那一刀的全部：它省下的是一塊 469 MB 的暫時陣列，不是任何一個
    數字。差一個灰階，`choose_origin` 就可能挑到別的相位 —— 而使用者在
    Golden Cell 上標的每一個區域都掛在那個相位上。
    """
    from d4t.core.algo.golden import stack_cells
    px, py = pitch
    img = np.random.default_rng(side + px).integers(0, 256, (side, side),
                                                    dtype=np.uint8)
    for origin in ((0, 0), (3, 5), (px - 1, py - 1)):
        got = stack_cells(img, px, py, origin=origin)
        want = _stack_the_old_way(img, px, py, origin)
        assert np.array_equal(got, want), (side, pitch, origin)
        # F105：週期與原點從此可以是 float 型別（`build_golden_cell` 回小數週期）。
        # **值是整數的 float 要走同一條路、同一組 byte** —— 那是「整數 pitch 的
        # 影像一個 byte 都不變」這條原則的實際檢查點。
        got_f = stack_cells(img, float(px), float(py),
                            origin=(float(origin[0]), float(origin[1])))
        assert np.array_equal(got_f, want), (side, pitch, origin, "float args")


def test_cell_origins_is_tile_coords_on_integer_periods():
    """F105 的 `cell_origins`（小數週期的格子位置）在整數參數上要逐元素等於
    `tile_coords` —— 格線檢視換了它之後，整數的圖畫出來的格子不准動。"""
    from d4t.core.algo.golden import cell_origins, tile_coords
    for shape, px, py, origin in (((288, 320), 24, 32, (0, 0)),
                                  ((288, 320), 24, 32, (5, 7)),
                                  ((100, 100), 7, 7, (6, 6)),
                                  ((50, 50), 60, 10, (0, 0)),       # 一格都放不下
                                  ((240, 320), 40, 240, (7, 0))):   # 一維 layout
        want = tile_coords(shape, px, py, origin)
        got = cell_origins(shape, float(px), float(py),
                           (float(origin[0]), float(origin[1])))
        assert [(int(x), int(y)) for x, y in got] == want, (shape, px, py, origin)
        assert all(float(x).is_integer() and float(y).is_integer() for x, y in got)


def test_cell_origins_steps_by_the_fractional_period():
    """79.5 不是 79：第 k 格在 k·79.5，不是 k·79 —— 那 25 px 就是格線靠邊會滑的量。"""
    from d4t.core.algo.golden import cell_origins
    got = cell_origins((4000, 41), 41.0, 79.5, (0.0, 0.0))
    ys = [y for _x, y in got]
    assert ys[:3] == [0.0, 79.5, 159.0]
    assert ys[-1] + 79.5 <= 4000 < ys[-1] + 2 * 79.5     # 最後一格是完整的、再一格就出界
    assert len(got) == 50


def test_the_median_path_is_untouched():
    """中位數**看得到每一格**，那正是它對稀疏缺陷免疫的原因 —— 不准 reshape。"""
    from d4t.core.algo.golden import stack_cells
    img = np.random.default_rng(4).integers(0, 256, (240, 240), dtype=np.uint8)
    img[0:48, 0:48] = 255                    # 一格全白：平均會被拉走，中位數不會
    med = stack_cells(img, 48, 48, method="median")
    mean = stack_cells(img, 48, 48, method="mean")
    assert not np.array_equal(med, mean)


def test_the_phase_search_reports_progress_and_can_be_cancelled():
    """F86：`choose_origin` 要說得出它跑到哪，而且停得下來。

    為什麼是 core 的事：它跑在 UI 執行緒上（`ui/template_dialog`），而
    **core 不得 import Qt**（鐵則 1）—— 所以這裡給的是 callback，
    畫面長什麼樣由 UI 決定。
    """
    img = _periodic(288, 288)
    seen = []
    choose_origin(img.shape, PX, PY, image=img,
                  progress=lambda d, t: seen.append((d, t)))
    assert seen, "一次都沒回報"
    assert seen[-1][0] == seen[-1][1], "最後一筆要是 done == total"
    assert all(t == seen[0][1] for _d, t in seen), "total 不准中途改"

    # 取消：回一個**真的評過分的**相位，不是 (0, 0)
    stopped = []

    def cancel(done, total):
        stopped.append(done)
        return done < 5
    got = choose_origin(img.shape, PX, PY, image=img, progress=cancel)
    assert len(stopped) <= 6, "取消之後還在算"
    assert 0 <= got[0] < PX and 0 <= got[1] < PY
