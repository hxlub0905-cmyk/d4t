"""Tests for d4t.core.algo.edge — CD 的全部數學（F19 第 1 步）。

合成資料的好處是**寬度是已知的**，所以「量得準不準」是一個可以斷言的數字，
不是一句感覺。這一份的核心是 :func:`test_criterion_noise_table` —— 它印出三個
判準在幾種雜訊下的偏差與標準差，而那張表**推翻了設計時挑的預設**（原本主張
``fit``，量出來 ``threshold`` 的 σ 最小、``gradient`` 的偏差最小）。理由記在
``d4t/core/algo/edge.py`` 的模組說明裡。
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from d4t.core.algo import edge as algo_edge


# --------------------------------------------------------------------------- #
# 合成資料：已知寬度、erf 模糊的一條亮線
# --------------------------------------------------------------------------- #
def _erf(x):
    return np.array([math.erf(float(v)) for v in np.asarray(x).ravel()]
                    ).reshape(np.asarray(x).shape)


def line_profile(n=64, center=32.0, width=12.0, blur=1.5,
                 low=40.0, high=180.0):
    """一條亮線的剖面（兩條 erf 的差）。``width`` 是 50% 高度處的寬度。"""
    x = np.arange(n, dtype=np.float64)
    s = math.sqrt(2.0) * blur
    a, b = center - width / 2.0, center + width / 2.0
    shape = 0.5 * (_erf((x - a) / s) - _erf((x - b) / s))
    return low + (high - low) * shape


def line_block(rows=24, jitter=0.0, seed=0, noise=0.0, **kw):
    """把剖面疊成一塊影像。``jitter`` = 每一列的中心抖動 σ（拿來做粗糙度）。"""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(rows):
        c = kw.get("center", 32.0) + (rng.normal(0.0, jitter) if jitter else 0.0)
        prof = line_profile(**dict(kw, center=c))
        if noise:
            prof = prof + rng.normal(0.0, noise, size=prof.shape)
        out.append(prof)
    return np.asarray(out, dtype=np.float64)


# --------------------------------------------------------------------------- #
# 乾淨的邊：三個判準都要量得準
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("criterion", list(algo_edge.CRITERIA))
def test_clean_line_width_is_recovered(criterion):
    prof = line_profile(width=12.0, blur=1.2)
    a, b, reason, used = algo_edge.measure_line(prof, criterion=criterion)
    assert reason == ""
    assert used == "bright"
    assert b.pos - a.pos == pytest.approx(12.0, abs=0.35)


@pytest.mark.parametrize("width", [9.0, 12.0, 15.0, 21.0])
def test_width_tracks_the_truth(width):
    """夠寬的線（≥ 9× 糊度）三個判準都準。更窄的極限另有一支測試釘住。"""
    prof = line_profile(width=width, blur=1.0)
    a, b, reason, _ = algo_edge.measure_line(prof)
    assert reason == ""
    assert b.pos - a.pos == pytest.approx(width, abs=0.25)


def test_polarity_and_contrast():
    prof = line_profile(width=10.0, low=40.0, high=180.0)
    edges = algo_edge.find_edges(prof)
    good = [e for e in edges if not e.reason]
    assert len(good) == 2
    assert good[0].polarity == 1 and good[1].polarity == -1
    for e in good:
        assert e.contrast == pytest.approx(140.0, rel=0.15)
        assert e.quality > 0.9          # 沒有雜訊 → 品質接近 1


@pytest.mark.parametrize("criterion", list(algo_edge.CRITERIA))
def test_every_criterion_reports_the_edge_blur(criterion):
    """糊度是**這張影像的性質**，不是某個判準的副產品 —— 三個都要吐得出來。

    量到的值含平滑器那一份（``smooth=0`` 才量得到原本的 2.0）。
    """
    prof = line_profile(width=16.0, blur=2.0)
    edges = [e for e in algo_edge.find_edges(prof, criterion=criterion,
                                             smooth=0.0) if not e.reason]
    assert len(edges) == 2
    for e in edges:
        assert e.blur == pytest.approx(2.0, rel=0.2)


def test_a_very_sharp_edge_falls_back_to_threshold_and_says_so():
    """銳到只有一兩個過渡像素時，擬合沒有樣本可用 —— 退回但不隱形。

    要關掉平滑才看得到：預設的 ``smooth=1.0`` 本身就會把邊糊開到擬合有樣本可
    用（量到的 ``blur`` 因此一律含平滑那一份，見 :class:`EdgePoint`）。
    """
    prof = line_profile(width=12.0, blur=0.2)
    edges = [e for e in algo_edge.find_edges(prof, criterion="fit", smooth=0.0)
             if not e.reason]
    assert edges
    assert all(e.method == "threshold" for e in edges)
    assert edges[1].pos - edges[0].pos == pytest.approx(12.0, abs=0.4)


# --------------------------------------------------------------------------- #
# ★ 預設值的證據：三個判準在雜訊下的偏差與標準差
# --------------------------------------------------------------------------- #
def _sweep(criterion, noise, truth=12.0, blur=1.5, trials=200, **kw):
    rng = np.random.default_rng(20260821)
    got = []
    for _ in range(trials):
        prof = line_profile(width=truth, blur=blur)
        prof = prof + rng.normal(0.0, noise, size=prof.shape)
        a, b, reason, _u = algo_edge.measure_line(prof, criterion=criterion,
                                                  **kw)
        if not reason:
            got.append(b.pos - a.pos)
    arr = np.asarray(got)
    return float(arr.mean() - truth), float(arr.std()), len(got)


def test_criterion_noise_table():
    """判準的實測表 —— **預設值的證據，也是它被改掉的證據**。

    設計時主張預設用 ``fit``（整段爬升 → √N）。這張表推翻了它：``threshold``
    的 σ 最小、``gradient`` 的偏差最小，``fit`` 兩項都不是最好。理由寫在
    ``algo/edge`` 的模組說明裡（平滑器先賺走了 √N；單邊模型被隔壁那條邊污染）。
    """
    rows = [(noise, {c: _sweep(c, noise) for c in algo_edge.CRITERIA})
            for noise in (2.0, 5.0, 10.0)]

    out = ["", "  真值 12.00 px、blur 1.5、200 次",
           "  %-6s %-24s %-24s %-24s" % ("雜訊", *algo_edge.CRITERIA)]
    for noise, line in rows:
        cells = ["bias %+5.3f σ %5.3f (%d)" % (line[c][0], line[c][1],
                                               line[c][2])
                 for c in algo_edge.CRITERIA]
        out.append("  %-6.1f %-24s %-24s %-24s" % (noise, *cells))
    print("\n".join(out))

    for noise, line in rows:
        # ① 預設（threshold）的 σ 要是最小的 —— 它當預設的唯一理由。
        assert line["threshold"][1] <= min(line["gradient"][1],
                                           line["fit"][1]) + 1e-9, (
            "threshold 的 σ 不再是最小的 —— 預設值要重選（noise=%.1f）" % noise)
        # ② gradient 的偏差要是最小的 —— 它存在的唯一理由。
        assert abs(line["gradient"][0]) <= min(abs(line["threshold"][0]),
                                               abs(line["fit"][0])) + 1e-9
        # ③ 三個判準都不該系統性地量錯。
        for criterion in algo_edge.CRITERIA:
            assert abs(line[criterion][0]) < 0.5


def test_over_smoothing_biases_the_crossing_but_not_the_inflection():
    """``smooth`` 開大會把 threshold／fit 往外推，``gradient`` 不動。

    對稱的平滑不會移動反曲點，但它會把兩條邊的尾巴糊到一起，於是 50% 的高度處
    往外跑。這就是「要跨批次比絕對 CD 就選 gradient」那句話的來源。
    """
    heavy = {c: _sweep(c, 5.0, smooth=2.0)[0] for c in algo_edge.CRITERIA}
    assert heavy["threshold"] > 0.15
    assert heavy["fit"] > 0.15
    assert abs(heavy["gradient"]) < 0.05


def test_a_line_narrower_than_a_few_blurs_reads_slightly_wide():
    """**已知的極限**：線寬接近糊度時，平台還沒到，所有判準都會量寬一點。

    這不是可以修掉的 bug（資訊就是不夠），但它是使用者該知道的一件事 ——
    所以它有一支測試，數字動了會被看見。
    """
    bias = {}
    for width in (6.0, 9.0, 12.0, 21.0):
        prof = line_profile(width=width, blur=1.0)
        a, b, reason, _ = algo_edge.measure_line(prof)
        assert reason == ""
        bias[width] = b.pos - a.pos - width
    assert bias[6.0] > bias[9.0] > bias[12.0]      # 越窄偏得越多
    assert bias[6.0] < 0.5                         # 但也就是半個像素
    assert abs(bias[21.0]) < 0.05                  # 夠寬就準


# --------------------------------------------------------------------------- #
# 失敗要講得出是哪一種
# --------------------------------------------------------------------------- #
def test_flat_profile_has_no_edges():
    a, b, reason, _ = algo_edge.measure_line(np.full(64, 100.0))
    assert (a, b) == (None, None)
    assert reason == "flat_profile"


def test_structure_running_off_the_frame_is_open_edge_not_a_number():
    """**畫面邊界不是一條邊。** 半條線只能拒絕，不能吐出「到畫面為止」那個寬度。"""
    prof = line_profile(n=64, center=58.0, width=24.0, blur=1.2)
    a, b, reason, _ = algo_edge.measure_line(prof, anchor=58.0)
    assert (a, b) == (None, None)
    assert reason == "open_edge"


def test_no_pair_when_the_anchor_is_outside_every_structure():
    prof = line_profile(n=80, center=20.0, width=8.0, blur=1.0)
    a, b, reason, _ = algo_edge.measure_line(prof, anchor=60.0,
                                             target="bright")
    assert reason in ("no_pair", "open_edge")
    assert a is None and b is None


# --------------------------------------------------------------------------- #
# 亮的／暗的／auto
# --------------------------------------------------------------------------- #
def test_dark_target_measures_the_gap():
    """暗的溝：把亮線的剖面反過來，量到的還是同一個寬度。"""
    prof = 220.0 - line_profile(width=10.0, blur=1.2)
    a, b, reason, used = algo_edge.measure_line(prof, target="dark")
    assert reason == ""
    assert used == "dark"
    assert b.pos - a.pos == pytest.approx(10.0, abs=0.35)


def test_auto_picks_the_polarity_that_pairs():
    prof = line_profile(width=10.0)
    _a, _b, reason, used = algo_edge.measure_line(prof, target="auto")
    assert reason == "" and used == "bright"
    _a, _b, reason, used = algo_edge.measure_line(220.0 - prof, target="auto")
    assert reason == "" and used == "dark"


def test_auto_prefers_the_inner_structure():
    """兩種極性都配得出來時，取**內側**那一個（錨點所在的那個結構）。"""
    x = np.arange(120, dtype=np.float64)
    prof = np.full_like(x, 60.0)
    prof[20:100] = 200.0                   # 一片亮
    prof[52:68] = 60.0                     # 中間挖一條暗溝
    prof = algo_edge.gaussian_filter1d(prof, 1.2)
    a, b, reason, used = algo_edge.measure_line(prof, anchor=60.0,
                                                target="auto")
    assert reason == ""
    assert used == "dark"                  # 內側是那條暗溝，不是外面那片亮
    assert b.pos - a.pos == pytest.approx(16.0, abs=1.0)


# --------------------------------------------------------------------------- #
# 掃一個區域
# --------------------------------------------------------------------------- #
def test_scan_gives_one_width_per_row():
    block = line_block(rows=20, width=12.0, blur=1.2)
    res = algo_edge.scan(block, axis="x")
    assert len(res.lines) == 20
    assert res.widths.size == 20
    assert res.widths.mean() == pytest.approx(12.0, abs=0.35)
    assert res.reasons == {}
    assert res.median_line >= 0
    assert res.profile is not None and res.profile.size == block.shape[1]


def test_scan_y_axis_is_the_transpose():
    block = line_block(rows=20, width=12.0, blur=1.2)
    a = algo_edge.scan(block, axis="x")
    b = algo_edge.scan(block.T, axis="y")
    assert a.widths.mean() == pytest.approx(b.widths.mean(), abs=1e-9)


def test_sigma_of_the_widths_is_the_roughness():
    """粗糙度不是另外算的 —— 它就是那組寬度的 σ。"""
    smooth = algo_edge.scan(line_block(rows=40, jitter=0.0, seed=1))
    rough = algo_edge.scan(line_block(rows=40, jitter=1.5, seed=1))
    # 中心抖動 = 兩條邊一起動 → LER 有、LWR 幾乎沒有。
    assert rough.a_positions.std() > smooth.a_positions.std() + 0.5
    assert rough.widths.std() == pytest.approx(smooth.widths.std(), abs=0.5)


def test_line_bin_averages_rows_and_costs_roughness():
    block = line_block(rows=40, jitter=1.5, seed=2, noise=3.0)
    plain = algo_edge.scan(block, line_bin=1)
    binned = algo_edge.scan(block, line_bin=8)
    assert binned.a_positions.std() < plain.a_positions.std()
    assert len(binned.lines) < len(plain.lines)


def test_line_step_skips_lines():
    block = line_block(rows=40)
    assert len(algo_edge.scan(block, line_step=4).lines) == 10


def test_truncation_is_not_silent():
    block = line_block(rows=40)
    res = algo_edge.scan(block, max_lines=10)
    assert len(res.lines) == 10
    assert res.reasons["too_many"] == 30


def test_scan_records_why_lines_failed():
    block = line_block(rows=12, center=58.0, width=24.0, blur=1.2)
    res = algo_edge.scan(block)
    assert res.widths.size == 0
    assert res.reasons.get("open_edge") == 12


def test_scan_counts_fit_fallbacks():
    res = algo_edge.scan(line_block(rows=10, blur=0.2), criterion="fit",
                         smooth=0.0)
    assert res.fallbacks == 20             # 每條線兩條邊都退回


# --------------------------------------------------------------------------- #
# 自動選方向
# --------------------------------------------------------------------------- #
def test_choose_axis_finds_the_direction_with_the_edges():
    block = line_block(rows=40, width=12.0)      # 垂直的邊 → 沿 X 量
    axis, sx, sy = algo_edge.choose_axis(block)
    assert axis == "x" and sx > sy
    axis, sx, sy = algo_edge.choose_axis(block.T)
    assert axis == "y" and sy > sx


def test_choose_axis_survives_a_flat_block():
    axis, _sx, _sy = algo_edge.choose_axis(np.full((16, 16), 100.0))
    assert axis in ("x", "y")


def test_scan_of_an_empty_block_does_not_raise():
    res = algo_edge.scan(np.empty((0, 0)))
    assert res.widths.size == 0 and res.reasons == {"empty": 1}


# --------------------------------------------------------------------------- #
# 剖面兩端的平滑（2026-08-22）
# --------------------------------------------------------------------------- #
def test_smoothing_does_not_invent_a_gradient_at_the_ends():
    """平的剖面平滑完還是平的 —— 補零的話兩端會被拉向 0。

    這不是「頭尾兩格不準」而已：``find_edges`` 的偵測門檻是**相對的**
    （0.35 × 該剖面最大梯度），所以端點的假梯度會把門檻整個墊高。
    """
    flat = np.full(40, 180.0)
    out = algo_edge.gaussian_filter1d(flat, 1.5)
    assert np.allclose(out, 180.0, atol=1e-9)


def test_a_bright_end_of_the_profile_does_not_hide_a_real_edge():
    """框切在亮的地方，中間那條比較弱的邊仍然要找得到。

    真實案例（F19 之後、mgext 合成資料）：一根 MG 從側壁竄出去一段，
    框的兩端各切在別的材質上。補零時端點的假梯度是全剖面最強的，
    門檻被墊高到 14.2，而凸出物末端那條真的邊只有 8.4 —— 於是那一列回
    ``open_edge``，看起來完全像「結構被框切掉了」。
    """
    prof = np.full(40, 205.0)              # 兩端都是亮的（框切在材質裡）
    prof[26:] = 165.0                      # 中間偏右一條比較弱的邊（對比 40）
    prof = algo_edge.gaussian_filter1d(prof, 0.8)
    edges = algo_edge.find_edges(prof, window=6, smooth=0.8, min_quality=0.2)
    assert [e.polarity for e in edges] == [-1]
    assert edges[0].pos == pytest.approx(25.5, abs=1.0)
