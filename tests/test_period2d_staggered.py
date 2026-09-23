"""F105：交錯晶格＋粗亮線上的週期量測退化（小數週期、半週期陷阱、第一峰規則）。

外部沙盒的實測報告（2026-09-17）：一張 3200 × 4000 的真實 SEM 大圖，交錯
（body-centred）晶格、亮線約 10 px 寬，人工驗證的重複單元 41 × 79.5。三個量法錯在
同一邊：投影法回 (41, 40)（40 = 79.5/2，交錯的子列間距）、F104 的二維自相關回
(10, 30)（第一峰規則被線寬峰騙走）、仲裁照抄投影。`build_golden_cell` 再把 79.5
截成 79，格線在 4000 px 上漂 25 px ——「靠邊會滑」。

原圖不進版本庫（鐵則 8）。這裡的 fixture 是**解析式**畫出來的 body-centred 晶格，
保留大圖上讓三個量法都錯的那兩個性質：X 軸線上有 ≥ 0.5·top 的子結構峰（第一峰
規則會停在那裡），兩個子列的 Y 投影一樣（投影法看到的是半週期）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.algo import golden, period, period2d, template  # noqa: E402
from test_period2d import squares, staggered, stripes  # noqa: E402

PX, PY = 41.0, 79.5


def _line(x: np.ndarray, xc: float, half: float) -> np.ndarray:
    """一條抗鋸齒的線（寬 2·half）：小數位置畫得準，才有真的 79.5。"""
    return np.clip(half + 0.5 - np.abs(x - xc), 0.0, 1.0)


def bc_lattice(px: float = PX, py: float = PY, w: int = 41 * 20, h: int = 800,
               noise: float = 4.0, seed: int = 5,
               gains=(1.0, 1.0, 0.4)) -> np.ndarray:
    """body-centred 晶格：子列 A 在 (0, 0)、子列 B 在 (px/2, py/2)。

    每格三條 4 px 亮線相距 px/3、亮度不等（``gains``；B 是反過來的）：
    * 三條線給 X 軸線一個 ~0.65·top 的子結構峰（大圖上 0.67）—— 第一峰規則的餌；
    * 亮度不等所以真的週期是 px 而不是 px/3；
    * 兩個子列的**總亮度一樣**，所以 Y 投影看到的是 py/2 的重複 —— 投影法會回 40。
    高 ≥ 800 px：`autocorr2d` 的高通 σ = min(h, w)/16，太矮會吃掉 79.5 的基頻。
    """
    xs = np.arange(w, dtype=np.float64)
    ys = np.arange(h, dtype=np.float64)

    def xprof(x0: float, g) -> np.ndarray:
        out = np.zeros(w)
        for i in range(-1, int(w / px) + 2):
            for j, gj in enumerate(g):
                out += gj * _line(xs, i * px + x0 + j * px / 3.0, 2.0)
        return out

    def yprof(y0: float) -> np.ndarray:
        out = np.zeros(h)
        for k in range(-1, int(h / py) + 2):
            out += _line(ys, k * py + y0, 12.0)
        return out

    a = np.outer(yprof(12.0), xprof(6.0, gains))
    b = np.outer(yprof(12.0 + py / 2), xprof(6.0 + px / 2, tuple(gains)[::-1]))
    img = 70.0 + 150.0 * np.clip(a + b, 0, 1)
    return img + np.random.default_rng(seed).normal(0, noise, img.shape)


@pytest.fixture(scope="module")
def tile() -> np.ndarray:
    return bc_lattice()


@pytest.fixture(scope="module")
def tile_ac(tile) -> np.ndarray:
    return period2d.autocorr2d(tile.astype(np.float32))


# ---------------------------------------------------------------------------
# 0. fixture 要有牙齒：它存在的理由就是這兩個性質，掉了測試要叫
# ---------------------------------------------------------------------------
def test_the_fixture_has_the_sub_structure_peak_that_fooled_the_first_peak_rule(tile_ac):
    line = tile_ac[0, :tile_ac.shape[1] // 2]
    idx = period2d._local_maxima(line, 4)
    top = float(line[idx].max())
    first_old_rule = int(idx[line[idx] >= max(0.3, 0.5 * top)][0])
    assert first_old_rule < 25, "F104 的 0.5 門檻在這張圖上應該停在子結構峰"
    assert line[first_old_rule] < period2d.PEAK_REL * top, "而 0.85 要放得過它"


def test_the_fixture_makes_the_projection_see_the_half_period(tile):
    est = period.estimate_period(tile)
    assert est.py is not None and abs(est.py - PY / 2) <= 1      # 40：交錯的子列
    assert est.confidence_y >= template.MIN_PERIOD_CONFIDENCE   # 而且很有信心


# ---------------------------------------------------------------------------
# 1. 二維自相關：最小的夠高峰 + 諧波鏈 → 次像素
# ---------------------------------------------------------------------------
def test_the_2d_method_reads_the_true_cell_with_sub_pixel_period(tile):
    two = period2d.estimate_period_2d(tile)
    assert (two.px, two.py) == (41, 80)
    assert abs(two.px_sub - PX) < 0.3 and abs(two.py_sub - PY) < 0.3
    assert two.confidence_x > 80 and two.confidence_y > 80
    assert not any("harmonic chain" in w for w in two.warnings)


def test_the_existing_fixtures_fit_their_integer_periods_to_a_hundredth(tile):
    for img, want in ((squares(), (32, 24)), (staggered(), (32, 48))):
        two = period2d.estimate_period_2d(img)
        assert (two.px, two.py) == want
        assert abs(two.px_sub - want[0]) < 0.05 and abs(two.py_sub - want[1]) < 0.05
    two = period2d.estimate_period_2d(stripes())
    assert two.px == 40 and abs(two.px_sub - 40) < 0.05 and two.py_sub is None


def test_the_autocorrelation_is_linear_not_circular():
    """視窗不是週期的整數倍時環狀自相關會拉歪遠的諧波（800 px 上 318.47 對 318）。"""
    ln = period2d.autocorr2d(bc_lattice(noise=0.0).astype(np.float32))
    line = ln[:ln.shape[0] // 2, 0]
    idx = period2d._local_maxima(line, 4)
    top = float(line[idx].max())
    lags = [period._parabolic(line, int(i))[0] for i in idx if line[i] >= 0.85 * top]
    for k, lag in enumerate(lags[:4], start=1):
        assert abs(lag - k * PY) < 0.05, (k, lag)


# ---------------------------------------------------------------------------
# 2. 半週期第三票 —— 以及它的反向測試（每一條例外規則都要有）
# ---------------------------------------------------------------------------
def test_the_half_period_check_doubles_the_projection_answer(tile, tile_ac):
    hp = period2d.half_period_check(tile, 41, 40, ac=tile_ac)
    assert hp.doubled_y and not hp.doubled_x
    assert abs(hp.py - PY) < 0.3 and hp.px == 41
    assert hp.gain_y > period2d.HALF_PERIOD_GAIN
    assert any("doubled" in n and "down" in n for n in hp.notes)
    assert hp.stagger > 0.6                       # 交錯：半向量是晶格點


@pytest.mark.parametrize("img,pq", [
    (squares(), (32, 24)),
    (stripes(), (40, 240)),
    (staggered(), (32, 48)),
    (np.random.default_rng(1).normal(120.0, 6.0, (256, 256)), (20, 20)),
])
def test_the_half_period_check_leaves_regular_lattices_and_noise_alone(img, pq):
    hp = period2d.half_period_check(img, *pq)
    assert not hp.doubled_x and not hp.doubled_y
    assert (hp.px, hp.py) == pq
    assert hp.gain_x < period2d.HALF_PERIOD_GAIN and hp.gain_y < period2d.HALF_PERIOD_GAIN


def test_the_half_period_check_skips_axes_the_user_gave(tile, tile_ac):
    hp = period2d.half_period_check(tile, 41, 40, ac=tile_ac, skip=(False, True))
    assert not hp.doubled_y and hp.py == 40


def test_regular_and_staggered_lattices_score_stagger_as_expected():
    assert period2d.half_period_check(squares(), 32, 24).stagger < 0.3
    assert period2d.half_period_check(staggered(), 32, 48).stagger > 0.9


# ---------------------------------------------------------------------------
# 3. 仲裁：答案、小數、講出來
# ---------------------------------------------------------------------------
def test_the_arbitration_ends_on_the_true_cell_and_says_why(tile):
    m = template.measure_period(template._gray_u8(tile))
    assert abs(m.px - PX) < 0.3 and 79.2 <= m.py <= 79.8
    assert m.stagger > 0.6
    assert any("staggered" in n for n in m.notes)


def test_snapping_is_a_drift_bound_not_an_absolute():
    """0.1 px 在 5 格上是 0.5 px（snap）；同樣的 0.1 px 在 50 格上是 5 px（不 snap）。"""
    assert template._snap(80.1, 400) == 80.0
    assert template._snap(80.1, 4000) == 80.1
    assert template._snap(79.5, 800) == 79.5
    assert template._snap(24.006, 192) == 24.0


def test_integer_pitch_images_stay_on_the_integer_path():
    """F105 的原則：整數 pitch 的影像一個 byte 都不變 —— 週期就是陣列尺寸。"""
    for img in (squares(), stripes(), staggered()):
        gc = template.build_golden_cell(img)
        assert gc.period_x == gc.px and gc.period_y == gc.py
        assert float(gc.origin[0]).is_integer() and float(gc.origin[1]).is_integer()
        assert gc.doubled == (False, False)


# ---------------------------------------------------------------------------
# 4. 疊圖：小數週期重採樣成整數 pitch 再疊
# ---------------------------------------------------------------------------
def test_the_stack_uses_the_fractional_period(tile):
    gc = template.build_golden_cell(tile)
    assert gc.cell.shape == (80, 41)
    assert (gc.px, gc.py) == (41, 80)
    assert abs(gc.period_y - PY) < 0.3 and gc.period_x == 41.0
    assert gc.periodic == (True, True)
    assert gc.agreement > 0.9
    assert 0 <= gc.origin[0] < gc.period_x and 0 <= gc.origin[1] < gc.period_y
    assert gc.notes and all(n in gc.warnings for n in gc.notes)
    said = " ".join(gc.notes)
    assert "staggered" in said and "79.5" in said


def test_the_fractional_stack_beats_the_truncated_integer_one(tile):
    frac = template.build_golden_cell(tile, 41.0, 79.5)
    trunc = template.build_golden_cell(tile, 41, 79)
    assert frac.cell.shape == (80, 41) and trunc.cell.shape == (79, 41)
    assert frac.agreement > trunc.agreement + 0.03
    assert frac.period_y == 79.5 and trunc.period_y == 79.0
    assert frac.notes == []                       # 使用者明講的，沒有決定要講


def test_cell_origins_frame_the_same_structure_across_the_whole_image(tile):
    """格線不滑：第一格與最後一格框到的內容要一樣像（用真的週期鋪）。"""
    gc = template.build_golden_cell(tile)
    boxes = golden.cell_origins(tile.shape, gc.period_x, gc.period_y, gc.origin)
    assert len(boxes) >= 9 * 19
    x0, y0 = boxes[0]
    x1, y1 = boxes[-1]
    a = tile[int(round(y0)):int(round(y0)) + 80, int(round(x0)):int(round(x0)) + 41]
    b = tile[int(round(y1)):int(round(y1)) + 80, int(round(x1)):int(round(x1)) + 41]
    assert a.shape == b.shape == (80, 41)
    assert float(np.abs(a - b).mean()) < 12.0       # 兩格一樣（雜訊 σ=4 兩份 + 半像素）
    # 拿整數 79 鋪的話最後一列早就滑到別的東西上了
    ys = [y for _x, y in golden.cell_origins(tile.shape, 41.0, 79.0, gc.origin)]
    assert abs(ys[-1] - y1) > 4.0


def test_period_text_keeps_integers_as_integers():
    assert template.period_text(40, 240) == "40 x 240"
    assert template.period_text(41.0, 79.5) == "41 x 79.5"
    assert template.period_text(41.0, 79.502) == "41 x 79.5"
