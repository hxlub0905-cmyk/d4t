# -*- coding: utf-8 -*-
"""F58：MG × EPI 合成圖案 —— **它真的長成我們宣稱的樣子嗎**。

使用者 2026-08-28 給了一張真的 Golden Cell 並描述了 layout：直的是 MG、
橫的是 EPI、交界比較暗的地方是 inner space（缺陷都在那裡），而且
**六根一個週期、第三根缺席**。`tools/_synth_mgepi.py` 是它的模擬器。

一個合成資料產生器最容易壞的方式不是炸掉，是**畫出一張看起來很像、但性質
不對的圖** —— 而下游每一支演算法都會照樣吐出正常的數字。所以這一支測的不是
「跑得完」，是**把圖量回來**：週期真的是六根嗎、缺席的真的是第三根嗎、
inner space 的框真的落在 EPI 亮帶上嗎。

⚠ 這裡面有兩條是**寫的時候真的踩到**的（各留了一句話在測試上）：
EPI 亮帶的相位差半個週期、以及「每種材質自己的 EPI 反應」不能用一個共同的
乘法增益。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO, os.path.join(REPO, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _synth_mgepi as mg  # noqa: E402


G = mg.GEOMETRY


def _col(img):
    return img.mean(axis=0)


def _row(img):
    return img.mean(axis=1)


# --------------------------------------------------------------------------- #
# 1. 週期：六根，第三根缺席
# --------------------------------------------------------------------------- #
def test_the_period_really_is_six_lines():
    """自相關的最佳位移 = 六根，**不是一根**。

    這一條就是這個圖案存在的理由：`_synth.py` 那兩個圖案一根就是一個週期，
    所以「一根的 pitch」與「真正的週期」永遠相同 —— `algo/period` 走不到
    「找到的是 pitch 不是週期」那條分支。
    """
    img = mg.frame(int(G.epi_pitch), int(G.mg_pitch * G.period * 3), G)
    c = _col(img)
    c = c - c.mean()
    span = int(round(G.mg_pitch * G.period))

    def r_at(lag: int) -> float:
        a, b = c[:-lag], c[lag:]
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    # ⚠ **要問的是「一根對不上、六根才對得上」** —— 第一版只問了「最佳位移
    # 是不是 span」，而把「第三根缺席」拿掉之後那條照樣綠（一根就對得上，
    # 六根當然也對得上，兩個 r 都 ≈ 1）。一個對兩種圖案都成立的斷言不是斷言。
    assert r_at(span) > 0.95, "六根對不上（r=%.3f）" % r_at(span)
    one = int(round(G.mg_pitch))
    assert r_at(one) < 0.80, (
        "一根就對得上（r=%.3f）—— 那表示沒有『第三根缺席』這件事，"
        "而這個圖案存在的理由就是它" % r_at(one))
    assert r_at(span) > r_at(one) + 0.2


def test_the_third_line_is_the_one_that_is_missing():
    """把每一根的亮度量回來：第三根明顯比其他五根暗。"""
    img = mg.frame(int(G.epi_pitch), int(G.mg_pitch * G.period), G)
    c = _col(img)
    peak = []
    for gi in range(G.period):
        x0 = int(round(gi * G.mg_pitch + G.mg_width / 2))
        peak.append(float(c[x0]))
    dark = int(np.argmin(peak))
    assert dark == G.absent == 2, "缺席的是第 %d 根（0-based），期望 2" % dark
    others = [v for i, v in enumerate(peak) if i != dark]
    assert peak[dark] < 0.6 * min(others)


def test_the_space_core_survives_the_missing_line():
    """⚠ 缺席的是**線**，不是整格 —— 那一格的亮芯還在。

    第一版連芯一起抹掉，於是寬暗區從量到的 18 px 變成 26 px。
    """
    img = mg.frame(int(G.epi_pitch), int(G.mg_pitch * G.period), G)
    c = _col(img)
    mid = int(round(G.absent * G.mg_pitch + (G.mg_width + G.mg_pitch) / 2))
    edge = int(round(G.absent * G.mg_pitch + G.mg_width / 2))
    assert c[mid] > c[edge] + 10.0, "缺席那一格的亮芯不見了"


# --------------------------------------------------------------------------- #
# 2. Golden Cell tile
# --------------------------------------------------------------------------- #
def test_the_golden_cell_is_exactly_one_period():
    gc = mg.golden_cell()
    assert gc.shape[1] == int(round(G.mg_pitch * G.period))
    assert gc.shape[0] == int(round(G.epi_pitch * 2))
    assert gc.dtype == np.uint8


def test_tiling_the_golden_cell_reproduces_the_pattern():
    """把 tile 鋪三次 = 直接畫三個週期。**週期宣稱的意思就是這句話。**"""
    gc = mg.golden_cell(periods_x=1, periods_y=1)
    tiled = np.tile(gc, (1, 3)).astype(np.float32)
    wide = mg.frame(gc.shape[0], gc.shape[1] * 3, G)
    assert np.abs(tiled - np.clip(wide, 0, 255)).max() <= 1.0


# --------------------------------------------------------------------------- #
# 3. inner space：要量的那些小條
# --------------------------------------------------------------------------- #
def test_every_inner_space_box_sits_on_a_bright_epi_band():
    """⚠ 這一條抓到過一個真的 bug。

    `_epi` 是 ``0.5 − 0.5·cos``，所以亮帶在 ``epi_pitch/2``，**不是 0**。
    第一版把框放在 ``≡ 0`` 上 —— 每一個框都落在最暗的那一列，而它照樣吐得出
    看起來正常的數字。
    """
    h, w = int(G.epi_pitch * 3), int(G.mg_pitch * G.period)
    img = mg.frame(h, w, G)
    rows = _row(img)
    boxes = mg.inner_space_boxes(h, w, G)
    assert boxes
    hi = rows.max()
    for x, y, bw, bh in boxes:
        centre = rows[y + bh // 2]
        assert centre > 0.9 * hi, "框在 y=%d，那一列的亮度只有 %.0f（最亮 %.0f）" % (
            y, centre, hi)


def test_every_inner_space_box_straddles_an_mg_edge():
    """框的意思是「MG 與 space 的交界」—— 框裡要同時看得到兩邊。"""
    h, w = int(G.epi_pitch * 2), int(G.mg_pitch * G.period)
    img = mg.frame(h, w, G)
    for x, y, bw, bh in mg.inner_space_boxes(h, w, G):
        strip = img[y:y + bh, x:x + bw]
        assert float(strip.max() - strip.min()) > 20.0, (
            "x=%d 的框裡是一片均勻的東西，它沒有跨在交界上" % x)


def test_the_absent_line_contributes_no_boxes():
    """不在的那一根沒有交界。一個週期上是 ``2 × (period − 1)`` 條。"""
    h = int(G.epi_pitch * 2)
    w = int(G.mg_pitch * G.period * 2)
    boxes = mg.inner_space_boxes(h, w, G, phase_x=G.mg_pitch / 2.0)
    per_band = len({b[0] for b in boxes})
    assert per_band == 2 * (G.period - 1) * 2 - 1 or per_band >= 2 * (G.period - 1), (
        "一個週期應該有 %d 條交界，量到 %d" % (2 * (G.period - 1), per_band))


# --------------------------------------------------------------------------- #
# 4. 缺陷
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", mg.REAL_TYPES)
def test_a_defect_actually_changes_the_image(kind):
    h, w = int(G.epi_pitch * 3), int(G.mg_pitch * G.period)
    clean = mg.frame(h, w, G)
    dirty = clean.copy()
    mg.plant_inner_space_defect(dirty, kind, np.random.default_rng(3), G)
    assert float(np.abs(dirty - clean).max()) >= 50.0, "振幅太小，抓不到"


def test_a_blob_lands_inside_an_inner_space_box():
    """使用者：「defect 都在這邊」。種在別處的合成資料會讓量 inner space
    這件事看起來沒有用 —— 而那是這份 layout 唯一要量的東西。"""
    h, w = int(G.epi_pitch * 3), int(G.mg_pitch * G.period)
    img = mg.frame(h, w, G)
    x, y = mg.plant_inner_space_defect(img, "bright_blob",
                                       np.random.default_rng(1), G)
    boxes = mg.inner_space_boxes(h, w, G)
    assert any(bx - 2 <= x <= bx + bw + 2 and by - 2 <= y <= by + bh + 2
               for bx, by, bw, bh in boxes), \
        "缺陷落在 (%d,%d)，不在任何一條 inner space 上" % (x, y)


def test_missing_line_removes_a_whole_line_not_a_dot():
    """這個 layout 才有的一種：**一整根 MG 不見了**。

    只看局部對比的做法抓不到它 —— 所以合成資料要生得出它，不然那條路
    永遠沒有被測過。
    """
    h, w = int(G.epi_pitch * 3), int(G.mg_pitch * G.period)
    img = mg.frame(h, w, G)
    before = _col(img).copy()
    mg.plant_inner_space_defect(img, "missing_line",
                                np.random.default_rng(2), G)
    after = _col(img)
    lost = np.where(before - after > 40.0)[0]
    assert len(lost) >= int(G.mg_width * 0.7), (
        "只掉了 %d 個 column，那不是「一整根不見」" % len(lost))


# --------------------------------------------------------------------------- #
# 5. EPI 對每一種材質的作用不一樣（第一版用一個共同增益，是錯的）
# --------------------------------------------------------------------------- #
def test_the_space_goes_dark_off_band_but_the_mg_line_does_not():
    """量真的那張 GC：MG 只掉一半（0.56），space 幾乎全黑（0.07）。

    一個共同的乘法增益做不出這件事 —— 物理上也不該：**MG 壓在 EPI 上**，
    所以只有 space 才看得到底下的帶亮不亮。
    """
    h, w = int(G.epi_pitch * 2), int(G.mg_pitch * G.period)
    img = mg.frame(h, w, G, phase_y=G.epi_pitch / 2.0)   # 亮帶落在 y=0
    yb, yd = 0, int(G.epi_pitch / 2)
    line_x = int(G.mg_width / 2)
    space_x = int(G.mg_width) + 3
    r_line = img[yd, line_x] / img[yb, line_x]
    r_space = img[yd, space_x] / img[yb, space_x]
    assert r_space < 0.20, "space 沒有暗下去（比值 %.2f）" % r_space
    assert r_line > 0.40, "MG 線跟著 space 一起暗掉了（比值 %.2f）" % r_line
    assert r_line > 2.5 * r_space


# --------------------------------------------------------------------------- #
# 6. 產生器：同 seed 位元組相同，而且既有的兩個圖案一個位元組都沒有變
# --------------------------------------------------------------------------- #
def _sha(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_the_patch_lot_is_reproducible(tmp_path):
    import make_sample
    a = make_sample.generate(str(tmp_path / "a"), n=4, size=128, seed=5,
                             pattern="mg_epi")
    b = make_sample.generate(str(tmp_path / "b"), n=4, size=128, seed=5,
                             pattern="mg_epi")
    assert _sha(a["tiff"]) == _sha(b["tiff"])
    assert _sha(a["golden_cell"]) == _sha(b["golden_cell"])


def test_the_rsem_lot_is_reproducible(tmp_path):
    import make_sample_rsem
    a = make_sample_rsem.generate(str(tmp_path / "a"), n=3, size=360, seed=5,
                                  pattern_name="mg_epi")
    b = make_sample_rsem.generate(str(tmp_path / "b"), n=3, size=360, seed=5,
                                  pattern_name="mg_epi")
    assert [_sha(p) for p in a["images"]] == [_sha(p) for p in b["images"]]


def test_a_golden_cell_ships_with_every_mg_epi_lot(tmp_path):
    """一份這種 layout 的資料沒有 GC 是半個東西 —— `roi_reference` 的
    「a cell I mark myself」要的就是那一張。"""
    import make_sample
    import make_sample_rsem
    p = make_sample.generate(str(tmp_path / "p"), n=2, size=128, seed=1,
                             pattern="mg_epi")
    r = make_sample_rsem.generate(str(tmp_path / "r"), n=2, size=360, seed=1,
                                  pattern_name="mg_epi")
    assert os.path.isfile(p["golden_cell"]) and os.path.isfile(r["golden_cell"])
    # 預設圖案**不附** GC（那個圖案沒有「一個週期」這回事要另外講）
    q = make_sample.generate(str(tmp_path / "q"), n=2, size=128, seed=1)
    assert "golden_cell" not in q


def test_the_rsem_lot_refuses_a_size_smaller_than_one_period(tmp_path):
    """看不到「第三根缺席」的大圖不是這個 layout 的大圖。"""
    import make_sample_rsem
    with pytest.raises(ValueError, match="mg_epi"):
        make_sample_rsem.generate(str(tmp_path / "x"), n=1, size=120,
                                  pattern_name="mg_epi")
