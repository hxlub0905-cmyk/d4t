"""F103：從使用者標的一格量週期（`algo/seed.py`）＋ 格線原點（`GoldenCell.origin`）。

使用者 2026-09-17 問「目前計算 cell 方式還可以添加什麼方法，假設算不對我該怎麼
知道」。第二種量法的承諾：答案直接來自「這一格在圖上重複了幾次、隔多遠」，而且
疊出來的 cell 長得跟他框的那一塊一樣。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.algo import golden, seed, template  # noqa: E402

PERIOD = 40


def stripes(seed_n: int = 0, noise: float = 4.0) -> np.ndarray:
    """跟 `test_ui_template_dialog.big_image` 同一張：一維、週期 40。"""
    rng = np.random.default_rng(seed_n)
    img = np.zeros((240, PERIOD * 8), np.float32)
    for k in range(8):
        x = k * PERIOD
        img[:, x:x + PERIOD] = 120.0
        img[:, x + 14:x + 34] = 60.0
        img[:, x + 12:x + 16] = 210.0
        img[:, x + 32:x + 36] = 210.0
    return img + rng.normal(0, noise, img.shape).astype(np.float32)


def squares(px: int = 32, py: int = 24, nx: int = 10, ny: int = 8,
            noise: float = 5.0) -> np.ndarray:
    """二維：圓角方塊晶格，兩軸週期不同。"""
    tile = np.zeros((py, px), np.float32) + 80
    tile[py // 4: 3 * py // 4, px // 4: 3 * px // 4] = 180
    big = np.tile(tile, (ny, nx))
    return big + np.random.default_rng(2).normal(0, noise, big.shape)


# ---------------------------------------------------------------------------
# 1. 量得對
# ---------------------------------------------------------------------------
def test_the_marked_cell_gives_the_period_and_its_corner_is_the_origin():
    r = seed.period_from_seed(stripes(), (47, 100, PERIOD, 60))
    assert r.px == PERIOD and r.py is None
    assert r.confidence_x == 100.0
    assert r.origin == (47, 100)
    assert r.n_row >= 5 and r.n_copies >= r.n_row
    assert any("no period that way (a stripe layout)" in w for w in r.warnings)


def test_a_two_dimensional_lattice_gives_both_periods():
    r = seed.period_from_seed(squares(), (37, 69, 32, 24))
    assert (r.px, r.py) == (32, 24)
    assert r.confidence_x == 100.0 and r.confidence_y == 100.0
    assert r.periodic == (True, True)
    assert r.warnings == []


def test_the_box_does_not_have_to_start_on_a_cell_boundary():
    """使用者框的是「一格」，不是「從格線起算的一格」—— 相位是他決定的。"""
    for x in (0, 5, 13, 21):
        r = seed.period_from_seed(squares(), (x, 7, 32, 24))
        assert (r.px, r.py) == (32, 24), x


def test_noise_has_no_copies_and_says_so():
    noise = np.random.default_rng(1).normal(120.0, 6.0, (128, 128))
    r = seed.period_from_seed(noise, (10, 10, 20, 20))
    assert r.px is None and r.py is None
    assert any("does not repeat" in w for w in r.warnings)


def test_a_flat_box_and_a_box_that_is_the_whole_image_are_refused():
    flat = np.full((100, 100), 90.0)
    assert any("no structure" in w for w in
               seed.period_from_seed(flat, (10, 10, 20, 20)).warnings)
    assert any("covers the whole image" in w for w in
               seed.period_from_seed(squares(), (0, 0, 10000, 10000)).warnings)


def test_a_box_half_a_cell_wide_reports_the_period_of_what_was_marked():
    """框只有半格的話，量到的是半格的重複 —— 那是誠實的答案，對話框會把
    找到幾個複本印出來，使用者看得出「太多了」。"""
    r = seed.period_from_seed(squares(), (37, 69, 16, 24))
    assert r.px in (16, 32)          # 半格圖案可能自己就重複
    assert r.py == 24


# ---------------------------------------------------------------------------
# 2. 疊出來的 cell 就是他框的那一塊（origin 進 build_golden_cell）
# ---------------------------------------------------------------------------
def test_stacking_from_the_marked_origin_gives_a_cell_that_looks_like_the_box():
    img = squares()
    r = seed.period_from_seed(img, (37, 69, 32, 24))
    gc = template.build_golden_cell(img, px=r.px, py=r.py, origin=r.origin)
    assert gc.cell.shape == (24, 32)
    assert gc.anchor == (0, 0)                      # 不做上升邊錨定
    assert gc.origin == (37 % 32, 69 % 24)
    box = img[69:93, 37:69]
    assert float(np.abs(box - gc.cell.astype(np.float32)).mean()) < 8.0
    assert gc.agreement > 0.8


def test_the_origin_of_a_default_stack_puts_the_lattice_in_phase():
    """沒有 seed 的那條路：`origin` 已經把錨定的捲動算進去 —— 從它起每 px
    一格，格子裡的東西就是 cell（格線檢視畫的就是這個）。"""
    img = stripes()
    gc = template.build_golden_cell(img)
    ox, oy = gc.origin
    assert 0 <= ox < gc.px and oy == 0
    coords = golden.tile_coords(img.shape, gc.px, gc.py, (ox, oy))
    assert coords
    x, y = coords[0]
    in_phase = float(np.abs(img[y:y + gc.py, x:x + gc.px] - gc.cell).mean())
    off = float(np.abs(img[y:y + gc.py, x + 13:x + 13 + gc.px] - gc.cell).mean())
    assert in_phase < 10.0 < off


def test_an_axis_without_a_period_keeps_its_origin_at_zero():
    """垂直條紋的 Y 軸：一格就是整張影像，原點只能是 0 —— 不然一格都放不下，
    疊出來是一張全黑的 cell 而且不會報錯（第一版踩到）。"""
    img = stripes()
    gc = template.build_golden_cell(img, px=PERIOD, py=None, origin=(47, 100))
    assert gc.periodic == (True, False)
    assert gc.origin == (47 % PERIOD, 0)
    assert gc.n_cells > 0 and gc.cell.max() > 100


@pytest.mark.parametrize("x", [0, 3, 31, 45])
def test_the_origin_is_the_corner_modulo_the_period(x):
    img = squares()
    gc = template.build_golden_cell(img, px=32, py=24, origin=(x, 0))
    assert gc.origin == (x % 32, 0)
