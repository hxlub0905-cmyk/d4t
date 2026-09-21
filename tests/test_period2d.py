"""F104：二維自相關找峰（`algo/period2d.py`）＋ 它跟投影法怎麼分工
（`template.measure_period`）＋ `GoldenCell.origin`（格線檢視靠它）。

使用者 2026-09-17：「你上面說的交錯圖形還沒解 —— 請幫忙做二維自相關找峰」。
交錯 layout 上投影法的 X 軸互相抵消（實測回 None），Y 軸回一列的高度而不是兩列；
二維自相關沿軸找離原點最近的峰，答案是真正的矩形重複單元。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.algo import golden, period, period2d, template  # noqa: E402

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
    """二維：方塊晶格，兩軸週期不同。"""
    tile = np.zeros((py, px), np.float32) + 80
    tile[py // 4: 3 * py // 4, px // 4: 3 * px // 4] = 180
    big = np.tile(tile, (ny, nx))
    return big + np.random.default_rng(2).normal(0, noise, big.shape)


def staggered(px: int = 32, py: int = 24, nx: int = 12, ny: int = 10,
              noise: float = 5.0, shift: float = 0.5) -> np.ndarray:
    """交錯：每隔一列往右錯 ``shift`` 格。矩形重複單元是 ``px × 2py``。"""
    H, W = ny * py, nx * px
    img = np.full((H, W), 80.0, np.float32)
    for j in range(ny):
        off = int(round(shift * px)) if j % 2 else 0
        for i in range(-1, nx + 1):
            x0, y0 = i * px + off + px // 4, j * py + py // 4
            xs, xe = max(0, x0), min(W, x0 + px // 2)
            if xe > xs:
                img[y0:y0 + py // 2, xs:xe] = 180
    return img + np.random.default_rng(3).normal(0, noise, img.shape)


# ---------------------------------------------------------------------------
# 1. 二維自相關本身
# ---------------------------------------------------------------------------
def test_a_staggered_layout_is_where_the_projection_fails_and_2d_does_not():
    img = staggered()
    proj = period.estimate_period(img)
    assert proj.px is None or proj.confidence_x < template.MIN_PERIOD_CONFIDENCE
    assert proj.py == 24                       # 一列的高度，不是重複單元
    two = period2d.estimate_period_2d(img)
    assert (two.px, two.py) == (32, 48)        # 真正的矩形重複單元
    assert two.confidence_x > 90 and two.confidence_y > 90


@pytest.mark.parametrize("img,want", [
    (squares(), (32, 24)),
    (staggered(shift=0), (32, 24)),
    (stripes(), (PERIOD, None)),
])
def test_regular_lattices_and_stripes_agree_with_the_projection(img, want):
    two = period2d.estimate_period_2d(img)
    assert (two.px, two.py) == want
    if want[1] is None:
        assert two.flat_y is True


def test_noise_and_a_flat_image_have_no_repeat():
    noise = np.random.default_rng(1).normal(120.0, 6.0, (256, 256))
    two = period2d.estimate_period_2d(noise)
    assert two.px is None and two.py is None
    assert any("no repeat" in w for w in two.warnings)
    flat = period2d.estimate_period_2d(np.full((128, 128), 90.0))
    assert flat.px is None and any("flat" in w for w in flat.warnings)


def test_a_tiny_image_says_so_instead_of_raising():
    two = period2d.estimate_period_2d(np.zeros((6, 6)))
    assert two.px is None and two.warnings


# ---------------------------------------------------------------------------
# 2. 分工：同意就不改，交錯才接手
# ---------------------------------------------------------------------------
def test_the_stack_uses_the_2d_period_on_a_staggered_layout_and_says_so():
    gc = template.build_golden_cell(staggered())
    assert (gc.px, gc.py) == (32, 48)
    assert gc.periodic == (True, True)
    assert gc.agreement > 0.8                  # 兩列一組疊得齊
    said = " ".join(gc.warnings)
    assert "2-D autocorrelation" in said or "staggered" in said


def test_the_stack_is_unchanged_where_the_two_methods_agree():
    for img, want in ((squares(), (32, 24)), (stripes(), (PERIOD, 240))):
        gc = template.build_golden_cell(img)
        assert (gc.px, gc.py) == want
        assert not any("autocorrelation" in w or "staggered" in w for w in gc.warnings)


def test_the_measure_step_only_takes_over_for_integer_multiples():
    """投影 30、二維 45（不是整數倍）→ 照投影；投影 30、二維 60 → 接手。"""
    m = template.measure_period(np.asarray(squares(), np.uint8))
    assert (m.px, m.py) == (32, 24) and m.notes == []
    assert m.doubled == (False, False)


# ---------------------------------------------------------------------------
# 3. 格線原點（格線檢視畫的就是它）
# ---------------------------------------------------------------------------
def test_the_origin_of_a_stack_puts_the_lattice_in_phase():
    img = stripes()
    gc = template.build_golden_cell(img)
    ox, oy = gc.origin
    assert 0 <= ox < gc.px and oy == 0
    x, y = golden.tile_coords(img.shape, gc.px, gc.py, (ox, oy))[0]
    in_phase = float(np.abs(img[y:y + gc.py, x:x + gc.px] - gc.cell).mean())
    off = float(np.abs(img[y:y + gc.py, x + 13:x + 13 + gc.px] - gc.cell).mean())
    assert in_phase < 10.0 < off


def test_the_origin_is_within_one_cell_for_a_two_dimensional_stack():
    gc = template.build_golden_cell(squares())
    assert 0 <= gc.origin[0] < gc.px and 0 <= gc.origin[1] < gc.py
