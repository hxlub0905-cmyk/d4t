# F7-8 驗收：自訂色調曲線（控制點編碼 + 保單調插值 + gamma 卡整合）。
"""曲線有三個獨立的正確性問題，這裡分開驗：

1. **編碼**（``pipeline/curve.py``）—— 字串進、控制點出；壞掉的字串要在
   ``validate_params`` 就被擋下並講出白話原因（鐵則 4）。
2. **插值**（``algo/curve.py``）—— 必須保單調。自然三次樣條會 overshoot，
   在影像上會直接看到一圈假的暗環，那是**演算法造出來的缺陷**，
   對一個要拿去判 defect 的工具來說是最糟的一種 bug。
3. **接手規則**（``steps/tone.py``）—— 曲線一旦不是 y=x 就完全接手 gamma。
"""
from __future__ import annotations

import numpy as np
import pytest

from adept.core.algo.curve import curve_lut, eval_curve
from adept.core.pipeline.curve import (
    IDENTITY, CurveError, format_curve, is_identity, parse_curve,
)
from adept.core.pipeline.step import ParamError, ParamSpec
from adept.core.steps.tone import GammaStep, apply_curve, apply_gamma


# --------------------------------------------------------------------------- #
# 1. 編碼
# --------------------------------------------------------------------------- #
def test_parsing_sorts_and_round_trips():
    pts = parse_curve("1,1 ; 0.35,0.55 ; 0,0")
    assert pts == [(0.0, 0.0), (0.35, 0.55), (1.0, 1.0)]
    assert format_curve(pts) == "0,0; 0.35,0.55; 1,1"
    assert parse_curve(format_curve(pts)) == pts


def test_an_empty_curve_means_identity():
    """舊 recipe 沒有這個參數也要讀得動。"""
    assert parse_curve("") == parse_curve(None) == parse_curve(IDENTITY)
    assert is_identity(parse_curve("")) is True
    assert is_identity(parse_curve("0,0; 0.4,0.7; 1,1")) is False


@pytest.mark.parametrize("bad,expect", [
    ("0,0; 0.5,2; 1,1", "outside"),
    ("0.2,0; 1,1", "must start at x=0"),
    ("0,0; 1,1; 1,0.5", "same input level"),
    ("0,0", "at least two points"),
    ("nope", "should look like"),
    ("0,0; 1; 1,1", "should look like"),
])
def test_a_broken_curve_is_refused_with_a_plain_reason(bad, expect):
    with pytest.raises(CurveError) as exc:
        parse_curve(bad)
    assert expect in str(exc.value)


def test_the_param_form_blocks_it_not_the_algorithm():
    """鐵則 4：填爆的值擋在 ``validate_params``，不准跑到演算法裡才炸。"""
    spec = ParamSpec(name="curve", type="curve", default=IDENTITY,
                     help="the curve")
    assert spec.validate("1,1;0.2,0.7;0,0") == "0,0; 0.2,0.7; 1,1"
    with pytest.raises(ParamError) as exc:
        spec.validate("0,0; 0.5,9; 1,1")
    assert "curve" in str(exc.value) and "outside" in str(exc.value)

    with pytest.raises(ParamError):
        GammaStep.validate_params({"curve": "garbage"})


# --------------------------------------------------------------------------- #
# 2. 插值
# --------------------------------------------------------------------------- #
def test_identity_control_points_give_back_a_straight_line():
    lut = curve_lut(IDENTITY, 256)
    assert np.allclose(lut, np.linspace(0.0, 1.0, 256), atol=1e-12)


@pytest.mark.parametrize("curve", [
    "0,0; 0.35,0.6; 1,1",
    "0,0; 0.45,0.05; 0.55,0.95; 1,1",      # 陡到接近階梯 —— 最容易 overshoot
    "0,0.2; 0.5,0.5; 1,0.8",               # 端點不在角落
    "0,0; 0.2,0.2; 0.8,0.2; 1,1",          # 中間一段完全平
])
def test_the_curve_never_overshoots_or_goes_backwards(curve):
    """保單調 —— 自然三次樣條在這幾條上都會凹出去。"""
    lut = curve_lut(curve, 512)
    assert lut.min() >= 0.0 and lut.max() <= 1.0
    assert np.all(np.diff(lut) >= -1e-12)


def test_the_curve_passes_through_its_control_points():
    pts = parse_curve("0,0; 0.35,0.6; 1,1")
    ys = eval_curve(pts, np.asarray([p[0] for p in pts]))
    assert np.allclose(ys, [p[1] for p in pts], atol=1e-9)


def test_a_curve_can_do_what_gamma_cannot():
    """gamma 是全域的單參數重分佈；曲線可以只動暗部、亮部原封不動。

    這正是「為什麼需要曲線」的那個理由，所以把它鎖成測試。
    """
    lut = curve_lut("0,0; 0.25,0.5; 0.6,0.6; 1,1", 256)
    x = np.linspace(0.0, 1.0, 256)
    assert lut[64] > x[64] + 0.2, "暗部要被拉起來"
    assert abs(lut[-16] - x[-16]) < 0.05, "亮部幾乎不動"


# --------------------------------------------------------------------------- #
# 3. 接手規則與影像行為
# --------------------------------------------------------------------------- #
def _ctx(dtype=np.uint8):
    from adept.core.pipeline.context import Context
    img = np.linspace(0, 255, 64 * 64).reshape(64, 64).astype(dtype)
    ctx = Context()
    ctx.set_image("test", img)
    ctx.set_image("ref", img.copy())
    return ctx


def test_an_identity_curve_leaves_the_image_exactly_alone():
    img = np.arange(256, dtype=np.uint8).reshape(16, 16)
    assert np.array_equal(apply_curve(img, IDENTITY), img)


def test_the_curve_keeps_the_dtype_and_the_value_range():
    """插在流程哪裡都不可以偷偷改型別 —— 下游的 diff 是 float32。"""
    for dtype in (np.uint8, np.float32):
        img = np.linspace(0, 255, 256).reshape(16, 16).astype(dtype)
        out = apply_curve(img, "0,0; 0.3,0.65; 1,1")
        assert out.dtype == img.dtype
        assert out.min() >= img.min() - 1e-3 and out.max() <= img.max() + 1e-3


def test_the_curve_takes_over_from_gamma_once_it_is_bent():
    """兩個旋鈕一個結果：曲線不是 y=x 時 gamma 完全不生效。"""
    step = GammaStep()
    bent = "0,0; 0.4,0.75; 1,1"

    # gamma 給一個很極端的值，但曲線接手 -> 結果與 gamma 無關
    a = step.run(_ctx(), {"gamma": 0.2, "curve": bent}).images["test"]
    b = step.run(_ctx(), {"gamma": 4.0, "curve": bent}).images["test"]
    assert np.array_equal(a, b)
    assert np.array_equal(a, apply_curve(_ctx().images["test"], bent))

    # 曲線放回 y=x -> gamma 又生效了
    c = step.run(_ctx(), {"gamma": 0.4, "curve": IDENTITY}).images["test"]
    assert np.array_equal(c, apply_gamma(_ctx().images["test"], 0.4))
    assert not np.array_equal(c, a)


def test_two_cards_keep_the_pair_comparable_and_one_card_does_not():
    """test 調了 ref 沒調，diff 會整片亮起來 —— 那是假缺陷。

    F7-18 之後那件事由**兩張卡**表達（畫布上一條線接 test、一條接 ref），
    而不是一張卡的 also_apply。這條測試因此鎖兩件事：一張卡真的只動自己那條，
    而放上第二張卡之後兩邊又對得起來了。
    """
    bent = "0,0; 0.4,0.75; 1,1"
    ctx = GammaStep().run(_ctx(), {"curve": bent})
    assert not np.array_equal(ctx.images["test"], ctx.images["ref"])

    ctx = GammaStep().run(ctx, {"target": "ref", "curve": bent})
    assert np.array_equal(ctx.images["test"], ctx.images["ref"])
