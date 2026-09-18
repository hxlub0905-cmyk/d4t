# F110 驗收：Image Combination 拆成「比較卡」與「融合卡」。
"""一張卡的五個 ``op`` 其實是**兩個問題**，而判準是訊號形狀（F109 定的那條）：

* ``subtract`` / ``ratio`` 問的是「**這兩張哪裡不一樣**」—— 2 條進、1 條出；
* ``max`` / ``min`` / ``mean`` 問的是「**把這幾張併成一張**」—— N 條進、1 條出。

擠在一起的代價實際看得見：那張卡只有 ``a`` 與 ``b`` **兩顆埠**，所以想把三張
condition 併成一張 reference 的人得放兩張卡串起來，而畫布上那兩張卡看起來是在
比較兩次。名字也跟著說謊 —— F16 把它改叫 ``Image Combination`` 是因為「五個 op
只有一個是相減」，而拆完之後那個理由不成立了。

⚠ **這一輪的驗收是「數字沒有變」**（跟 F109 相反）：出貨的三份與 fixture 都只用
``op: "subtract"``，所以換卡那一道對它們是 no-op，`absolute=True → sign="abs"`
也必須跑出逐位元組相同的結果。變了就是遷移寫錯，不是預期。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 註冊卡片
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.recipe import Recipe  # noqa: E402
from d4t.core.pipeline.step import (  # noqa: E402
    GROUP_COMPARE, REGISTRY, StepError,
)


def _run(key, images, **params):
    step = get_step(key)()
    ctx = Context(images=dict(images))
    return step, step.run(ctx, dict(params))


def _old(params, version=3):
    return {"recipe_id": "t", "version": version,
            "routes": {"ebi_patch": ["l", "s"]},
            "nodes": {"l": {"step": "load_patch", "params": {}},
                      "s": {"step": "subtract", "params": dict(params)}},
            "edges": [["l", "test", "s", "a"], ["l", "ref", "s", "b"]],
            "score": {"expr": "1", "threshold": 0.0,
                      "bins": {"below": 0, "above": 1}}}


# --------------------------------------------------------------------------- #
# 1. 兩張卡各自回答自己的問題
# --------------------------------------------------------------------------- #
def test_the_two_cards_are_both_in_the_compare_stage():
    """融合也是 2 條以上進、一條出 —— 判準是訊號形狀，所以它也屬於 Compare。"""
    compare = [k for k, c in REGISTRY.items()
               if c.resolve_group() == GROUP_COMPARE]
    assert compare == ["align", "subtract", "combine", "align_to"], compare


def test_the_name_image_combination_went_to_the_card_that_earns_it():
    assert get_step("combine").label == "Image Combination"
    # ⚠ 跟 `roi_reference`／`ROI` 同一個先例：一段裡最正統的那一張卡
    # 就叫那一段的名字。`Compare two images` 是 18 字元，而卡片名的
    # 天花板是**現況的最大值**（17）—— 名字要短到不必先去調那把尺。
    assert get_step("subtract").label == "Compare"
    # key 不准動 —— 那是 recipe 的鍵
    assert get_step("subtract").key == "subtract"


def test_the_compare_card_no_longer_offers_the_merging_ops():
    ops = [s for s in get_step("subtract").params if s.name == "op"][0].choices
    assert set(ops) == {"subtract", "ratio", "normalized", "over_sigma"}
    assert not ({"max", "min", "mean"} & set(ops))


def test_merging_takes_as_many_streams_as_you_wire():
    """**這是拆卡真正買到的東西。** 以前三張要串兩張卡，而畫布上那看起來是
    比較了兩次。"""
    rng = np.random.default_rng(1)
    base = rng.integers(20, 200, (16, 16)).astype(np.uint8)
    imgs = {"c%d" % i: np.clip(base.astype(np.int16) + i, 0, 255).astype(np.uint8)
            for i in range(1, 6)}
    _s, ctx = _run("combine", imgs, streams=",".join(imgs), method="mean",
                   out="avg")
    assert ctx.images["avg"].shape == base.shape
    assert ctx.images["avg"] == pytest.approx(
        np.mean([i.astype(np.float32) for i in imgs.values()], axis=0))


def test_the_median_drops_what_only_one_image_has():
    """**median 是預設的理由**，寫成一條測試：N 張裡有一張帶著缺陷的時候，
    `mean` 把它抹進結果裡（每張貢獻 1/N），`median` 直接不看它。

    「用好幾張造一張乾淨的 reference」正是這張卡最常見的用途。
    """
    clean = np.full((16, 16), 100, np.uint8)
    dirty = clean.copy()
    dirty[4:8, 4:8] = 250                     # 只有其中一張有的東西
    imgs = {"a": clean, "b": clean.copy(), "c": dirty}
    _s, med = _run("combine", imgs, streams="a,b,c", method="median", out="m")
    _s2, avg = _run("combine", imgs, streams="a,b,c", method="mean", out="m")
    assert med.images["m"] == pytest.approx(np.full((16, 16), 100.0))
    assert avg.images["m"][6, 6] > 140.0, "mean 應該被那一張帶走"


def test_merging_one_stream_is_a_lint_error_and_a_run_error():
    """設定期看得出來的事就在設定期講 —— 不要等到跑完才報。"""
    assert get_step("combine").configuration_issues({"streams": "a"})
    assert not get_step("combine").configuration_issues({"streams": "a,b"})
    with pytest.raises(StepError):
        _run("combine", {"a": np.zeros((8, 8), np.uint8)}, streams="a",
             method="median", out="m")


def test_merging_different_sizes_says_to_align_first():
    with pytest.raises(StepError) as e:
        _run("combine", {"a": np.zeros((8, 8), np.uint8),
                         "b": np.zeros((9, 9), np.uint8)},
             streams="a,b", method="median", out="m")
    assert "Align" in str(e.value)


def test_trimming_falls_back_instead_of_emptying_the_stack():
    """三張流兩端各砍 25% 就是各砍 0.75 張 —— 取整之後有可能把全部砍光。

    那時候「算不出來」是錯的答案（中位數明明算得出來），而 NaN 會一路流進
    分數表達式。
    """
    imgs = {"a": np.full((8, 8), 10, np.uint8),
            "b": np.full((8, 8), 20, np.uint8),
            "c": np.full((8, 8), 30, np.uint8)}
    _s, ctx = _run("combine", imgs, streams="a,b,c", method="trimmed", out="m")
    assert np.all(np.isfinite(ctx.images["m"]))
    assert ctx.images["m"] == pytest.approx(np.full((8, 8), 20.0))


# --------------------------------------------------------------------------- #
# 2. 比較卡的新東西
# --------------------------------------------------------------------------- #
def _pair():
    a = np.full((8, 8), 120, np.uint8)
    b = np.full((8, 8), 100, np.uint8)
    a[2, 2] = 60                              # 一顆暗的
    return {"a": a, "b": b}


def test_split_writes_two_streams_each_holding_only_its_own_half():
    """分開的整個意思就是**讓下游各給一個門檻** —— 所以兩條流各自只留自己那半，
    不是把負的變 0 再丟同一條。"""
    step = get_step("subtract")
    p = {"a": "a", "b": "b", "op": "subtract", "sign": "split", "out": "d"}
    assert step.resolve_writes(p) == ["d_bright", "d_dark"]
    _s, ctx = _run("subtract", _pair(), **p)
    bright, dark = ctx.images["d_bright"], ctx.images["d_dark"]
    assert bright[0, 0] == pytest.approx(20.0) and dark[0, 0] == 0.0
    assert dark[2, 2] == pytest.approx(40.0) and bright[2, 2] == 0.0
    assert np.all(bright >= 0) and np.all(dark >= 0)


def test_abs_and_signed_still_write_exactly_one_stream():
    step = get_step("subtract")
    for sign in ("abs", "signed"):
        p = {"a": "a", "b": "b", "op": "subtract", "sign": sign, "out": "d"}
        assert step.resolve_writes(p) == ["d"]
        _s, ctx = _run("subtract", _pair(), **p)
        assert set(ctx.images) == {"a", "b", "d"}
    _s, signed = _run("subtract", _pair(), a="a", b="b", op="subtract",
                      sign="signed", out="d")
    assert signed.images["d"][2, 2] == pytest.approx(-40.0), "負號要留著"


def test_normalized_survives_a_nearly_black_reference():
    """`ratio` 在參照接近黑的時候會噴出幾千，而那個數字會被打進分數表達式。"""
    imgs = {"a": np.full((4, 4), 40, np.uint8), "b": np.zeros((4, 4), np.uint8)}
    _s, ctx = _run("subtract", imgs, a="a", b="b", op="normalized",
                   sign="signed", out="d")
    assert np.all(np.abs(ctx.images["d"]) <= 1.0 + 1e-6)


def test_over_sigma_means_the_same_thing_on_a_grainy_image():
    """「差了幾個 σ」的重點是**門檻在兩張圖上意思一樣** —— 雜訊大一倍，
    同樣的灰階差就該只值一半的 σ。"""
    rng = np.random.default_rng(4)
    quiet = np.clip(rng.normal(100, 4, (64, 64)), 0, 255).astype(np.uint8)
    noisy = np.clip(rng.normal(100, 16, (64, 64)), 0, 255).astype(np.uint8)
    out = []
    for ref in (quiet, noisy):
        tgt = np.clip(ref.astype(np.int16) + 20, 0, 255).astype(np.uint8)
        _s, ctx = _run("subtract", {"a": tgt, "b": ref}, a="a", b="b",
                       op="over_sigma", sign="signed", out="d")
        out.append(float(np.mean(ctx.images["d"])))
    assert out[0] > 2.5 * out[1], "σ 大四倍，同樣的 20 階差要小很多：%s" % out


# --------------------------------------------------------------------------- #
# 3. 遷移：舊檔案照開，而且數字不變
# --------------------------------------------------------------------------- #
def test_an_old_merging_subtract_becomes_the_combine_card():
    r = Recipe.from_json_dict(_old({"a": "test", "b": "ref", "op": "mean",
                                    "out": "avg"}))
    node = r.nodes["s"]
    assert node.step == "combine"
    assert node.params == {"streams": "test,ref", "method": "mean",
                           "out": "avg"}
    # ⚠ 線上的埠名也要換 —— 少了這一件，畫布上那兩條線指向不存在的埠
    assert [e.dst_in for e in r.edges] == ["streams", "streams"]


def test_an_old_comparing_subtract_is_left_where_it_is():
    r = Recipe.from_json_dict(_old({"a": "test", "b": "ref", "op": "ratio"}))
    assert r.nodes["s"].step == "subtract"
    assert [e.dst_in for e in r.edges] == ["a", "b"]


@pytest.mark.parametrize("old,want", [({"absolute": True}, "abs"),
                                      ({"absolute": False}, "signed")])
def test_the_old_bool_becomes_the_new_choice(old, want):
    r = Recipe.from_json_dict(_old(dict(old, a="test", b="ref")))
    assert r.nodes["s"].params["sign"] == want
    assert "absolute" not in r.nodes["s"].params


def test_a_file_that_never_wrote_absolute_gets_nothing_invented():
    """**鐵則 9 的正牌用法**，而這一道第一版真的踩到了它。

    舊的 ``absolute=True`` 跟新的 ``sign="abs"`` 是同一件事，所以檔案裡沒寫
    就什麼都不要做 —— 寫下去就是「讀檔幫使用者填了一個他沒寫的值」。
    """
    r = Recipe.from_json_dict(_old({"op": "subtract"}))
    assert r.nodes["s"].params == {"op": "subtract"}


def test_both_migrations_are_a_no_op_the_second_time():
    """``to_json_dict → from_json_dict`` 必須是 identity（鐵則 9）——
    那一對是 `run_batch` 送 recipe 進 worker 的路。"""
    for params in ({"a": "t", "b": "r", "op": "mean"},
                   {"a": "t", "b": "r", "absolute": False},
                   {"op": "subtract"}):
        once = Recipe.from_json_dict(_old(params))
        twice = Recipe.from_json_dict(once.to_json_dict())
        assert twice.to_json_dict() == once.to_json_dict(), params
