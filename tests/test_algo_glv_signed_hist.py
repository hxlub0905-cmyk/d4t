# PR-2：`signed_hist`（差影像的 0 置中直方圖）與 `pixel_hist` 的分工。
"""`pixel_hist` 是 0–255 寫死的灰階直方圖（跨顆可比是它的契約，**不准動**）；
`signed_hist` 給有號的差影像流。這一份鎖住兩支各自的契約 —— 包括
`pixel_hist` 的絆線：哪天有人「順手」讓它跟著資料調範圍，這裡會先紅。
"""
from __future__ import annotations

import numpy as np

from d4t.core.algo.glv import pixel_hist, signed_hist


def test_edges_are_symmetric_and_zero_centred():
    rng = np.random.default_rng(7)
    d = rng.normal(0.0, 3.0, size=(64, 64)).astype(np.float32)
    counts, edges, clipped = signed_hist(d, bins=64)
    assert len(counts) == 64 and len(edges) == 65
    assert edges[0] == -edges[-1], "範圍要對稱於 0"
    assert edges[32] == 0.0, "bins 是偶數，0 正好落在正中央的 bin 邊"
    assert counts.sum() == d.size, "clip 進最外側 bin：一顆像素都不能丟"
    assert 0.0 <= clipped <= 1.0


def test_clipped_fraction_is_exact_on_a_constructed_tail():
    """99.5 百分位之外的那 0.5% 要被收編進最外側 bin，而且比例要講出來。"""
    d = np.zeros(1000, dtype=np.float64)
    d[:10] = 1000.0                       # 1% 的巨大尾巴
    counts, edges, clipped = signed_hist(d, bins=64, clip_q=99.0)
    beyond = float((np.abs(d) > edges[-1]).mean())
    assert abs(clipped - beyond) < 1e-12
    assert clipped > 0.0, "反空洞：這組資料真的有尾巴"
    assert counts[-1] >= 10, "尾巴收編在最外側 bin，不是消失"


def test_empty_and_all_zero_inputs_are_well_formed():
    for data in (np.zeros(0), np.zeros((8, 8), dtype=np.float32)):
        counts, edges, clipped = signed_hist(data)
        assert len(counts) == 64 and len(edges) == 65
        assert clipped == 0.0
        assert edges[0] < 0.0 < edges[-1], "全零也要有一個合法的對稱範圍"


def test_pixel_hist_range_is_still_hardcoded_0_255():
    """絆線：`pixel_hist` 的 0–255 是契約（bin 寬跨顆可比），不隨資料變。

    值域/dtype 的問題歸 bug 修正單 —— 修的方式是**另開 helper**（上面那支
    `signed_hist` 就是第一個），不是把這一支改成看資料。
    """
    for data in (np.array([50.0, 60.0]), np.array([-5.0, 300.0]),
                 np.zeros(0)):
        _counts, edges = pixel_hist(data, bins=32)
        assert edges[0] == 0.0 and edges[-1] == 255.0, \
            "pixel_hist 的範圍被改掉了 —— 那是跨顆可比的契約"
