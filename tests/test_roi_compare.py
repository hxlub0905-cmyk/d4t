# F11 Measure：比較兩個區域（T/R 住在這張卡上）。
"""這一份鎖住的是**「拿哪兩塊比」變成一件看得見、擋得住的事**。

今天沒有這張卡也比得出來 —— 只是比較發生在**分數表達式**裡
（`test_epi_glv_mean - ref_epi_glv_mean`）。而表達式裡的減法：畫布上看不到、
recipe 的 diff 讀不懂、兩邊挑錯區域也沒有人擋得住。所以這張卡的價值不在算術，
在**那三件事變成可見的**，而測試要測的正是那三件：

1. **兩對（流 + 區域）**，因為使用者列的三種情況裡有一種是「同一個區域、
   兩條不同的流」——一條流配兩個區域表達不出它；
2. **同一塊比自己**要在跑之前就擋（它的每個數字恆為 0，而那些 0 不會因為任何
   缺陷而改變）；
3. **區域不在**的時候講出真正的原因（`<name>_others` 在只有一份的 patch 上是
   **不存在**的，那不是設定錯）。

算術本身只鎖一件事：`snr` 用的是這個 repo 已經有的那個帶正負號的慣例，
**不是第三種寫法**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.algo import glv as algo_glv  # noqa: E402
from adept.core.pipeline import get_step  # noqa: E402
from adept.core.pipeline.context import Context  # noqa: E402
from adept.core.pipeline.step import ParamError, ParamSpec, StepError  # noqa: E402

BASE = {"target_source": "test", "target_region": "hot",
        "reference_source": "test", "reference_region": "cold",
        "stat": "glv_mean", "metrics": "delta,snr,tstat,ratio,percent",
        "output_prefix": ""}


def _ctx(hot_glv=140.0, cold_glv=100.0, spread=4.0, seed=0, shape=(40, 40)):
    """一張圖，兩塊區域：左半是 `hot`、右半是 `cold`。"""
    rng = np.random.default_rng(seed)
    img = np.zeros(shape, np.float32)
    img[:, :shape[1] // 2] = hot_glv
    img[:, shape[1] // 2:] = cold_glv
    img = img + rng.normal(0, spread, shape).astype(np.float32)
    ctx = Context(images={"test": img, "ref": img.copy()})
    ctx.set_roi_boxes("hot", [(0.0, 0.0, 0.5, 1.0)])
    ctx.set_roi_boxes("cold", [(0.5, 0.0, 0.5, 1.0)])
    return ctx


def _run(ctx, **over):
    p = dict(BASE)
    p.update(over)
    get_step("roi_compare")().run(ctx, p)
    return ctx


# --------------------------------------------------------------------------- #
# 1. 兩對（流 + 區域）—— 三種情況用同一張卡說得完
# --------------------------------------------------------------------------- #
def test_two_regions_on_one_stream():
    """情況 1／3：跟同一張圖上的另一塊比。"""
    ctx = _run(_ctx(hot_glv=140.0, cold_glv=100.0))
    assert ctx.features["delta"] == pytest.approx(40.0, abs=1.0)
    assert ctx.features["snr"] == pytest.approx(10.0, rel=0.15)


def test_the_same_region_on_two_streams():
    """情況 2：**同一個區域、兩條不同的流**。

    一條流配兩個區域表達不出這一種 —— 而它正是使用者列的三種裡的中間那一種
    （patch 跟 ref 那張的同一塊比）。
    """
    ctx = _ctx()
    ctx.set_image("ref", np.asarray(ctx.images["test"]) - 25.0)
    _run(ctx, target_region="hot", reference_region="hot",
         reference_source="ref")
    assert ctx.features["delta"] == pytest.approx(25.0, abs=1.0)


def test_it_declares_both_streams_and_both_regions():
    """畫布上要有**兩個**輸入埠，lint 要看得到兩個區域。"""
    card = get_step("roi_compare")
    p = dict(BASE, reference_source="ref")
    assert card.resolve_reads(p) == ["test", "ref"]
    assert card.resolve_regions_in(p) == ["hot", "cold"]
    # 兩邊同一條流時不重複宣告（一個埠一條線，F9）
    assert card.resolve_reads(BASE) == ["test"]


def test_the_declared_features_are_what_it_writes():
    ctx = _run(_ctx())
    declared = set(get_step("roi_compare").resolve_features(BASE))
    assert set(ctx.features) == declared


def test_the_prefix_applies():
    ctx = _run(_ctx(), output_prefix="epi_vs_mg", metrics="delta")
    assert list(ctx.features) == ["epi_vs_mg_delta"]


# --------------------------------------------------------------------------- #
# 2. 同一塊比自己 —— 在跑之前就擋
# --------------------------------------------------------------------------- #
def test_comparing_a_region_with_itself_is_caught_before_the_run():
    """每個數字恆為 0，而那些 0 **不會因為任何缺陷而改變** ——
    跑得完、有數字、而且那些數字什麼都沒說。"""
    says = get_step("roi_compare").configuration_issues(
        dict(BASE, reference_region="hot"))
    assert says and "zero no matter what" in says[0]


def test_the_same_region_on_two_different_streams_is_fine():
    """那正是情況 2 —— 不可以連它一起擋掉。"""
    assert get_step("roi_compare").configuration_issues(
        dict(BASE, reference_region="hot", reference_source="ref")) == []


def test_nothing_picked_yet_points_at_the_two_fields():
    """訊息要指向**填得到的東西**（`test_ui_f7_9_feedback` 的不變量）。"""
    says = get_step("roi_compare").configuration_issues(
        dict(BASE, target_region="", reference_region=""))
    assert says
    labels = {p.label for p in get_step("roi_compare").params}
    assert "“Target region”" in says[0] and "“Reference region”" in says[0]
    assert {"Target region", "Reference region"} <= labels


def test_running_with_nothing_picked_says_so():
    with pytest.raises(StepError) as e:
        _run(_ctx(), target_region="", reference_region="")
    assert "compares two" in str(e.value)


# --------------------------------------------------------------------------- #
# 3. 區域不在的時候，講出真正的原因
# --------------------------------------------------------------------------- #
def test_an_absent_region_says_why_not_just_that_it_is_missing():
    """`<name>_others` 在只有一份的 patch 上是**不存在**的（不是空的）——
    那不是設定錯，是這一顆沒有基準，而使用者要分得出那兩件事。"""
    ctx = _ctx()
    ctx.meta.setdefault("regions_absent", {})["cold_others"] = (
        "this patch only has one copy of 'cold', so there is no other copy "
        "to use as a baseline")
    with pytest.raises(StepError) as e:
        _run(ctx, reference_region="cold_others")
    text = str(e.value)
    assert "only has one copy" in text
    assert "rest of the batch is unaffected" in text


def test_a_region_nobody_produced_says_that_instead():
    with pytest.raises(StepError) as e:
        _run(_ctx(), reference_region="nope")
    assert "no card upstream produced it" in str(e.value)


def test_a_missing_stream_names_what_is_there():
    with pytest.raises(StepError) as e:
        _run(_ctx(), reference_source="diff")
    assert "does not exist here" in str(e.value) and "test" in str(e.value)


# --------------------------------------------------------------------------- #
# 4. 算術：**不發明第三種 SNR**
# --------------------------------------------------------------------------- #
def test_snr_is_the_same_signed_convention_the_repo_already_uses():
    """`(μ_T − μ_R) / σ_R` —— 跟 `algo.glv.group_snr` 與 `algo/snr` 同一個。

    同一個名字在不同卡片上算出不同的東西，是最難發現的那種錯。
    """
    rng = np.random.default_rng(3)
    t = rng.normal(130, 3, 500)
    r = rng.normal(100, 6, 500)
    got = algo_glv.compare_pixels(t, r)
    assert got["snr"] == pytest.approx((t.mean() - r.mean()) / r.std())


def test_a_denominator_of_zero_is_nan_not_zero():
    """0 的意思是「沒有差異」，而這裡的事實是「這個問題答不出來」。"""
    got = algo_glv.compare_pixels(np.full(50, 120.0), np.full(50, 100.0))
    assert got["delta"] == pytest.approx(20.0)
    assert np.isnan(got["snr"]), "常數參考的 σ 是 0 —— snr 沒有答案"
    assert got["ratio"] == pytest.approx(1.2)
    got0 = algo_glv.compare_pixels(np.full(50, 20.0), np.zeros(50))
    assert np.isnan(got0["ratio"]) and np.isnan(got0["percent"])


def test_tstat_takes_the_region_sizes_into_account_and_snr_does_not():
    """GDS 的一層可能是另一層的十倍大 —— 兩個問題，兩個數字。"""
    rng = np.random.default_rng(5)
    r = rng.normal(100, 5, 4000)
    small = algo_glv.compare_pixels(rng.normal(110, 5, 20), r)
    big = algo_glv.compare_pixels(rng.normal(110, 5, 2000), r)
    assert small["snr"] == pytest.approx(big["snr"], rel=0.25)
    assert big["tstat"] > small["tstat"] * 3, "樣本數沒有進 tstat"


def test_the_statistic_being_compared_is_the_users_choice():
    """中位數會忽略幾顆很亮的點 —— 那正是「區域裡有一顆不是要量的東西」。"""
    ctx = _ctx(hot_glv=100.0, cold_glv=100.0, spread=0.0)
    img = np.asarray(ctx.images["test"]).copy()
    img[0, :3] = 255.0                      # 三顆亮點在 hot 那半邊
    ctx.set_image("test", img)
    mean = _run(ctx, stat="glv_mean", metrics="delta").features["delta"]
    ctx2 = _ctx(hot_glv=100.0, cold_glv=100.0, spread=0.0)
    ctx2.set_image("test", img)
    median = _run(ctx2, stat="glv_median", metrics="delta").features["delta"]
    assert mean > 0.1 and median == pytest.approx(0.0)


def test_an_unknown_comparison_is_refused_with_the_list():
    with pytest.raises(StepError) as e:
        _run(_ctx(), metrics="delta,bogus")
    assert "bogus" in str(e.value) and "snr" in str(e.value)


# --------------------------------------------------------------------------- #
# 5. `region_key` 是**一個**區域
# --------------------------------------------------------------------------- #
def test_a_region_key_takes_one_name_not_a_list():
    """`region_keys`（複數）是逗號清單，這個不是 —— 而錯的那句話要是白話的。"""
    spec = ParamSpec(name="target_region", type="region_key", default="",
                     help="x")
    assert spec.validate("epi") == "epi"
    with pytest.raises(ParamError) as e:
        spec.validate("epi,mg")
    assert "one region name, not a list" in str(e.value)
    assert "one Compare regions card per pair" in str(e.value)


def test_the_card_uses_the_singular_type_for_both_regions():
    kinds = {p.name: p.type for p in get_step("roi_compare").params}
    assert kinds["target_region"] == "region_key"
    assert kinds["reference_region"] == "region_key"


# --------------------------------------------------------------------------- #
# 6. 儀表看到的就是引擎算的
# --------------------------------------------------------------------------- #
def test_the_panel_sees_the_same_numbers():
    ctx = _run(_ctx())
    rec = ctx.meta["compares"]["hot_vs_cold"]
    assert rec["values"]["delta"] == ctx.features["delta"]
    assert rec["target_px"] == 40 * 20 and rec["reference_px"] == 40 * 20
    assert rec["stat"] == "glv_mean"
