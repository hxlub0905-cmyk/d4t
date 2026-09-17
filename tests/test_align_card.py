# F109 驗收：align 拿回卡片庫，而且**對齊不動灰階**。
"""這一份守的是 F109 那句核心承諾：**位移只取整數，一個位元都不重採樣。**

為什麼這件事值得一支測試守著：align 2026-08-18 被收起來的第二個機制，就是
「只有被移動的那一條走了 `cv2.INTER_LINEAR`」—— 等於對它過一次低通、對基準那條
沒有。下游量的是灰階（`diff`、GLV、SNR），所以那一層材質差是憑空長出來的訊號。

而 DOE 把這件事從副作用變成致命傷：同一顆 defect、不同 E-beam condition 各拍一張，
量的**就是**它們的灰階差。對其中幾張各過一次不一樣的低通，再去比它們的 SNR，
那個比較是假的。

所以「像素值逐位元組相同」不是一條形狀測試，是這張卡存在的理由。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import align as algo_align  # noqa: E402
from d4t.core.steps import align as align_card  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.step import StepError  # noqa: E402

ALL_METHODS = ("phase", "hybrid", "ncc", "ecc", "template")


def _texture(size: int = 96, seed: int = 3) -> np.ndarray:
    """一張有東西可以對的圖（全平的圖每個 backend 都對不出來，那是另一條測試）。"""
    rng = np.random.default_rng(seed)
    img = (rng.random((size, size)) * 255).astype(np.float32)
    return cv2.GaussianBlur(img, (0, 0), 2)


def _rolled(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """``out(x, y) = img(x - dx, y - dy)``，週期性 —— 繞回來的那一圈會被裁掉。"""
    return np.roll(np.roll(img, dx, axis=1), dy, axis=0)


def _run(images, **params):
    step = get_step("align")()
    ctx = Context(images=dict(images))
    return step, step.run(ctx, dict(params))


# --------------------------------------------------------------------------- #
# 1. 核心承諾：對齊不動灰階
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", ALL_METHODS)
def test_alignment_does_not_touch_a_single_grey_level(method):
    """對齊之後，兩條流在重疊區內**逐位元組相同**。

    構造是刻意的：``ref`` 就是 ``test`` 整數平移過的同一張圖，所以「對得起來」
    的唯一正確答案，是兩張裁完之後**一模一樣**。任何重採樣 —— 次像素的
    ``INTER_LINEAR``、任何濾波、任何 dtype 轉換 —— 都會讓這一條紅。

    ⚠ 這不是「差很小」，是 `np.array_equal`。這張卡的承諾就是那個等號。
    """
    base = _texture()
    _step, ctx = _run({"test": base, "ref": _rolled(base, 4, -3)},
                      streams="test,ref", fixed="test", method=method,
                      search_radius=8)
    out_t, out_r = ctx.images["test"], ctx.images["ref"]
    assert out_t.shape == out_r.shape
    assert np.array_equal(out_t, out_r), (
        "對齊完的兩張在重疊區內不是逐位元組相同 —— 有人重採樣了。"
        "最大差 %.6g" % float(np.abs(out_t - out_r).max()))
    assert out_t.dtype == base.dtype


@pytest.mark.parametrize("method", ALL_METHODS)
def test_every_output_value_came_verbatim_from_its_own_input(method):
    """更直接的問法：出去的每一個灰階值，都是進來那張圖上真的有的值。

    上面那一條驗的是「兩張對得起來」，這一條驗的是「沒有插值出新的值」——
    ``INTER_LINEAR`` 會在兩個相鄰像素之間造出**原圖沒有的**中間值，而那正是
    2026-08-18 那個「拉 align 反而會飄」的第二個機制。
    """
    base = _texture()
    moved = _rolled(base, 4, -3)
    _step, ctx = _run({"test": base, "ref": moved},
                      streams="test,ref", fixed="test", method=method,
                      search_radius=8)
    for key, src in (("test", base), ("ref", moved)):
        out = ctx.images[key]
        extra = np.setdiff1d(np.unique(out), np.unique(src))
        assert extra.size == 0, (
            "'%s' 出去了 %d 個原圖沒有的灰階值（例如 %r）—— 插值出來的。"
            % (key, extra.size, extra[:3].tolist()))


# --------------------------------------------------------------------------- #
# 2. N 條流：裁完尺寸一致，而裁了多少有一個數字說得出來
# --------------------------------------------------------------------------- #
def test_n_streams_all_come_out_the_same_size():
    """DOE 一次餵 N 個 condition 進來，而下游那一組 box 是同一組。

    尺寸只要有一條對不上，`glv_stats` 那一輪就會在某一條流上量到框外 ——
    而症狀是「某個 condition 的 SNR 特別怪」，最不像是對齊出的問題。
    """
    base = _texture()
    images = {"c1": base,
              "c2": _rolled(base, 5, 0),
              "c3": _rolled(base, -2, 4),
              "c4": _rolled(base, 1, -6)}
    _step, ctx = _run(images, streams="c1,c2,c3,c4", fixed="c1",
                      method="phase", search_radius=8)
    shapes = {k: ctx.images[k].shape for k in images}
    assert len(set(shapes.values())) == 1, "N 條流裁完尺寸不一致：%s" % shapes
    # 都對得上同一張底圖，所以裁完應該張張相同。
    first = ctx.images["c1"]
    for k in images:
        assert np.array_equal(ctx.images[k], first), "'%s' 對完跟基準對不起來" % k


def test_valid_frac_matches_what_was_actually_cropped_away():
    """`align_valid_frac` 是「這張卡自己做的決定要變成一個畫得出分布的數字」。

    它說謊的話，使用者會拿一個看起來正常的數字去相信一張只剩半張的圖。
    """
    base = _texture()
    images = {"c1": base, "c2": _rolled(base, 5, 0), "c3": _rolled(base, -2, 4)}
    _step, ctx = _run(images, streams="c1,c2,c3", fixed="c1",
                      method="phase", search_radius=8)
    out = ctx.images["c1"]
    expected = float(out.shape[0] * out.shape[1]) / float(base.shape[0] * base.shape[1])
    assert ctx.features["align_valid_frac"] == pytest.approx(expected, abs=1e-9)
    assert 0.0 < ctx.features["align_valid_frac"] < 1.0, "有位移就一定裁掉了一點"


def test_two_streams_keep_the_feature_names_they_had_before_f109():
    """一條 ref 對一條 test（最常見的用法）**不加前綴** —— 舊 recipe 的分數
    表達式寫的是 `align_dx`，改名等於讓每一份舊 recipe 都算錯。"""
    base = _texture()
    _step, ctx = _run({"test": base, "ref": _rolled(base, 4, -3)},
                      streams="test,ref", fixed="test", method="phase",
                      search_radius=8)
    assert set(ctx.features) == {"align_dx", "align_dy", "align_score",
                                 "align_valid_frac"}
    assert ctx.features["align_dx"] == pytest.approx(4.0, abs=0.5)
    assert ctx.features["align_dy"] == pytest.approx(-3.0, abs=0.5)


def test_three_or_more_streams_prefix_the_numbers_by_stream():
    """三條以上就得分得出「哪一條移了多少」—— 同一個名字擠三個值等於只剩一個。"""
    base = _texture()
    _step, ctx = _run({"c1": base, "c2": _rolled(base, 5, 0),
                       "c3": _rolled(base, -2, 4)},
                      streams="c1,c2,c3", fixed="c1", method="phase",
                      search_radius=8)
    assert "c2_align_dx" in ctx.features and "c3_align_dx" in ctx.features
    assert "align_dx" not in ctx.features
    assert ctx.features["c2_align_dx"] == pytest.approx(5.0, abs=0.5)
    assert ctx.features["c3_align_dy"] == pytest.approx(4.0, abs=0.5)


def test_the_dashboard_names_and_the_declared_names_cannot_drift_apart():
    """`shift_feature_names`（儀表要畫哪幾組）與 `resolve_features`（卡片宣告
    會寫哪幾個）是**兩支各自算前綴的函式** —— 而那種對子會漂。

    漂掉的症狀是儀表板一片空白，而空白上寫著「跑一次試跑就看得到」：使用者
    照做之後還是空的，然後去懷疑資料。這一條讓那件事在 CI 上發生，不在畫面上。
    """
    step = get_step("align")
    for params in ({},
                   {"streams": "test,ref", "fixed": "test"},
                   {"streams": "c1,c2,c3,c4", "fixed": "c1"},
                   {"streams": "", "fixed": ""}):
        declared = set(step.resolve_features(dict(params)))
        for dx, dy in align_card.shift_feature_names(dict(params)):
            assert dx in declared and dy in declared, (
                "儀表要畫 %r/%r，而卡片宣告的是 %s" % (dx, dy, sorted(declared)))


# --------------------------------------------------------------------------- #
# 3. 做不到的事要說做不到
# --------------------------------------------------------------------------- #
def test_different_sizes_raise_instead_of_reporting_a_zero_shift():
    """**以前是「警告 ＋ 零位移」，而那三個數字照樣流進分數表達式。**

    一件做不到的事看起來像做完了，是這個 repo 最貴的一種失敗（「跑得完、
    有數字、而且是錯的」）。單顆報錯只讓那一顆 `ok=False`，整批照跑（鐵則 7）。
    """
    base = _texture(96)
    with pytest.raises(StepError) as e:
        _run({"test": base, "ref": _texture(64, seed=5)},
             streams="test,ref", fixed="test", method="phase", search_radius=8)
    msg = str(e.value)
    assert "H2H" in msg, "訊息要告訴使用者該用哪張卡：%s" % msg


def test_a_single_stream_raises_because_there_is_nothing_to_line_up_against():
    base = _texture()
    with pytest.raises(StepError):
        _run({"test": base}, streams="test", fixed="test", method="phase",
             search_radius=8)


def test_a_fixed_that_is_not_in_the_list_is_a_lint_error():
    """基準不在清單裡 = 它不會被裁 = 出去的幾條尺寸對不起來。

    這是**設定期**就看得出來的事，所以它該在畫布上出現一條紅字，而不是等到
    跑完之後在某張圖上發現框偏了。
    """
    step = get_step("align")
    issues = step.configuration_issues({"streams": "c1,c2", "fixed": "c9"})
    assert issues, "基準不在 streams 裡，lint 什麼都沒說"
    assert "c9" in issues[0], "訊息要指名是哪一個：%s" % issues[0]
    assert not step.configuration_issues({"streams": "c1,c2", "fixed": "c1"})


# --------------------------------------------------------------------------- #
# 4. 反向：help 宣稱的值域要跟 `algo/align` 真的回傳的一致
# --------------------------------------------------------------------------- #
def test_the_score_help_declares_the_range_the_backends_really_return():
    """`align_score` 的 help 以前寫 `0 to 1`，而每個 backend 都 `* 100`。

    那個數字**進得了分數表達式**，而 help 是使用者唯一讀得到的說明 ——
    寫錯就是把人帶到一個差 100 倍的門檻上（`score < 0.8` 會是「全部都過」）。

    這一條不抄任何數字進來：從 help 裡把宣告的上下界**讀出來**，再跟五個
    backend 實際跑出來的分數比。
    """
    step = get_step("align")
    text = step.FEATURE_HELP["align_score"]
    m = re.search(r"(\d+(?:\.\d+)?)\s*to\s*(\d+(?:\.\d+)?)", text)
    assert m, "help 沒有講值域，而這個數字會進分數表達式：%r" % text
    lo, hi = float(m.group(1)), float(m.group(2))

    base = _texture()
    moved = _rolled(base, 4, -3)
    scores = [algo_align.calculate_alignment(
        base, moved, method=meth, search_radius=8).final_score
        for meth in ALL_METHODS]
    assert min(scores) >= lo - 1e-6, "實際分數低於 help 宣告的下界：%s" % scores
    assert max(scores) <= hi + 1e-6, (
        "help 說 %g–%g，而實際跑出 %g —— `algo/align` 每個 backend 都 *100。"
        % (lo, hi, max(scores)))
    assert max(scores) > hi / 10.0, (
        "help 宣告的上界 %g 比實際跑得出來的最大值 %g 大一個數量級以上 —— "
        "那個上界沒有貼著真值，使用者訂的門檻會落在永遠不會發生的地方。"
        % (hi, max(scores)))


# --------------------------------------------------------------------------- #
# 5. `common_crop` 本身
# --------------------------------------------------------------------------- #
def test_common_crop_windows_all_have_the_same_size():
    windows = algo_align.common_crop((100, 120), {"a": (0, 0), "b": (5, -3),
                                                  "c": (-2, 4)})
    sizes = {k: (y1 - y0, x1 - x0) for k, (y0, y1, x0, x1) in windows.items()}
    assert len(set(sizes.values())) == 1, sizes
    assert sizes["a"] == (100 - (4 + 3), 120 - (5 + 2))


def test_common_crop_says_so_when_nothing_overlaps():
    with pytest.raises(ValueError):
        algo_align.common_crop((20, 20), {"a": (0, 0), "b": (25, 0)})
