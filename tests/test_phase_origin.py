"""Tests for the M4-1 phase search in ``adept.core.algo.period.choose_origin``.

``choose_origin`` picks the lattice origin ``(ox, oy)`` — the offset at
which cutting the image into ``px x py`` cells puts every cell in phase.
It maximises the **raw Laplacian variance** of the stacked cell
(``golden.ghosting_score(...)[1]``, higher = sharper = less ghosting).

The criterion is translation-equivariant rather than absolute: which
phase inside the cell it prefers depends on the pattern, but cropping
the *same* image by ``c`` pixels must shift the answer by ``-c``
(mod pitch).  That is what "recovers a known phase offset" means here,
and it is what the Golden Cell card relies on.
"""
from __future__ import annotations

import time

import cv2
import numpy as np
import pytest

from adept.core.algo.golden import ghosting_score, stack_cells
from adept.core.algo.period import choose_origin

PITCH = 16


def _cell_tile(pitch: int = PITCH) -> np.ndarray:
    """一格 cell：圓角亮方塊 + 一個小記號（打破左右對稱）。"""
    c = np.zeros((pitch, pitch), np.float64)
    cv2.rectangle(c, (3, 3), (pitch - 6, pitch - 6), 210, -1)
    c[pitch - 4:pitch - 2, 2:5] = 120
    return cv2.GaussianBlur(c, (3, 3), 0.9) + 35.0


def _lattice(h=256, w=256, pitch=PITCH, crop=0, seed=0, noise=3.0) -> np.ndarray:
    """Periodic lattice cropped at a KNOWN phase offset ``crop`` (both axes)."""
    tile = _cell_tile(pitch)
    reps = (h // pitch + 3, w // pitch + 3)
    big = np.tile(tile, reps)
    img = big[crop:crop + h, crop:crop + w]
    img = img + np.random.default_rng(seed).normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _circ(a: int, b: int, period: int) -> int:
    """Circular distance between two offsets of the same period."""
    d = abs(int(a) - int(b)) % period
    return min(d, period - d)


@pytest.fixture(scope="module")
def base_origin():
    """The origin the criterion picks for the un-cropped lattice."""
    img = _lattice()
    return choose_origin(img.shape, PITCH, PITCH, image=img)


# ---------------------------------------------------------------- 相位回復

@pytest.mark.parametrize("crop", [0, 3, 5, 9, 13])
def test_recovers_known_phase_offset(crop, base_origin):
    """裁掉 crop 個像素後，找到的原點必須跟著位移 -crop（mod pitch）。"""
    img = _lattice(crop=crop)
    ox, oy = choose_origin(img.shape, PITCH, PITCH, image=img)
    assert 0 <= ox < PITCH and 0 <= oy < PITCH
    assert _circ(ox + crop, base_origin[0], PITCH) <= 1
    assert _circ(oy + crop, base_origin[1], PITCH) <= 1


def test_chosen_origin_stacks_sharper_than_wrong_phase():
    """挑到的相位疊出來要比刻意錯開半格的相位清晰（higher lap_var = better）。"""
    img = _lattice(crop=5)
    ox, oy = choose_origin(img.shape, PITCH, PITCH, image=img)
    best = ghosting_score(stack_cells(img, PITCH, PITCH, origin=(ox, oy)))[1]
    worst = ghosting_score(stack_cells(
        img, PITCH, PITCH,
        origin=((ox + PITCH // 2) % PITCH, (oy + PITCH // 2) % PITCH)))[1]
    assert best > worst


def test_deterministic_same_input_same_answer():
    img = _lattice(crop=7)
    a = choose_origin(img.shape, PITCH, PITCH, image=img)
    b = choose_origin(img.shape, PITCH, PITCH, image=img)
    assert a == b


# ---------------------------------------------------------------- 相容性 / 防呆

def test_without_image_is_the_legacy_zero_origin():
    """舊的三參數呼叫（沒有 image）維持 (0, 0) 行為。"""
    assert choose_origin((320, 288), 24, 32) == (0, 0)
    assert choose_origin((320, 288), 24, 32, image=None) == (0, 0)


def test_flat_image_returns_zero_origin():
    flat = np.full((128, 128), 128, np.uint8)
    assert choose_origin(flat.shape, 16, 16, image=flat) == (0, 0)


@pytest.mark.parametrize("px,py", [(None, 16), (16, None), (None, None),
                                   (0, 16), (1, 16), (16, 1), (-4, 16)])
def test_bad_period_returns_zero_origin(px, py):
    img = _lattice()
    assert choose_origin(img.shape, px, py, image=img) == (0, 0)


def test_image_smaller_than_one_cell_returns_zero_origin():
    tiny = _lattice(h=10, w=10)
    assert choose_origin(tiny.shape, 16, 16, image=tiny) == (0, 0)


def test_single_cell_row_pins_that_axis_to_zero():
    """只放得下一列 cell 時，該軸沒有相位資訊 → 釘在 0，另一軸照常搜尋。"""
    img = _lattice(h=20, w=256, crop=5)
    ox, oy = choose_origin(img.shape, PITCH, PITCH, image=img)
    assert oy == 0
    assert 0 <= ox < PITCH


def test_colour_image_is_accepted():
    gray = _lattice(crop=3)
    colour = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    assert choose_origin(colour.shape, PITCH, PITCH, image=colour) == \
        choose_origin(gray.shape, PITCH, PITCH, image=gray)


# ---------------------------------------------------------------- 成本上限

def test_large_period_is_capped_and_fast():
    """px=py=64（4096 個相位）必須靠取樣 + 微調壓在 2 秒內，且答對。"""
    base = _lattice(h=512, w=512, pitch=64, crop=0, seed=1)
    shifted = _lattice(h=512, w=512, pitch=64, crop=7, seed=1)

    t0 = time.time()
    b = choose_origin(base.shape, 64, 64, image=base)
    s = choose_origin(shifted.shape, 64, 64, image=shifted)
    elapsed = time.time() - t0
    assert elapsed < 2.0, f"phase search too slow: {elapsed:.2f}s for 2 runs"

    # 取樣（stride）+ 微調後仍要抓到相位：位移 7 → 原點跟著位移 -7
    assert _circ(s[0] + 7, b[0], 64) <= 1
    assert _circ(s[1] + 7, b[1], 64) <= 1
