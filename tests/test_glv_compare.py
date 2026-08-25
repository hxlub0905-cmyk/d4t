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

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import glv as algo_glv  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.step import ParamError, ParamSpec, StepError  # noqa: E402

#: F16 把這張卡併進 `glv_stats`（label `Gray level`）當它的
#: ``method="compare"``；**F18 第 5 步再把那個二選一拆成「跟誰比」的一格**
#: （`reference`）—— 絕對值永遠吐，相對值疊在上面。舊 recipe 由
#: `recipe._migrate_compare_method_into_reference` 接住（見
#: `test_an_old_roi_compare_recipe_still_opens`）。
#:
#: 這一份的每一條測的東西**都沒有變**，只有參數名跟著卡片走：
#: ``target_source/target_region`` 就是這張卡本來就在量的 ``source``/``roi``。
BASE = {"source": "test", "roi": "hot",
        "metrics": "glv_mean",
        "reference": "another region", "reference_region": "cold",
        "stat": "glv_mean",
        "compare_metrics": "delta,snr,tstat,ratio,percent",
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


def _boxed_ctx(hot_glv=140.0, cold_glv=100.0, spread=4.0, seed=0, n=6):
    """右半邊切成 n 格的版本 —— ``snr`` / ``tstat`` 的分母是**框與框之間**，
    所以參照那一塊必須有好幾格才算得出來（2026-08-21 起）。"""
    ctx = _ctx(hot_glv=hot_glv, cold_glv=cold_glv, spread=spread, seed=seed)
    ctx.set_roi_boxes("cold", [(0.5, i / float(n), 0.5, 1.0 / n)
                               for i in range(n)])
    return ctx


def _run(ctx, **over):
    p = dict(BASE)
    p.update(over)
    get_step("glv_stats")().run(ctx, p)
    return ctx


# --------------------------------------------------------------------------- #
# 1. 兩對（流 + 區域）—— 三種情況用同一張卡說得完
# --------------------------------------------------------------------------- #
def test_two_regions_on_one_stream():
    """情況 1／3：跟同一張圖上的另一塊比。"""
    ctx = _run(_boxed_ctx(hot_glv=140.0, cold_glv=100.0))
    assert ctx.features["cmp_delta_mean"] == pytest.approx(40.0, abs=1.0)
    # snr 的分母是參照那六格**彼此**的散布（同材質，所以很小）—— 一個真的
    # 差 40 階的缺陷因此是很大的 snr。by pixel 的話分母裡有 shot noise，
    # 同一件事會被壓成個位數（使用者：「by pixel 會太小」）。
    assert ctx.features["cmp_snr_mean"] > 20.0


def test_the_same_region_on_two_streams():
    """情況 2：**同一個區域、兩條不同的流**。

    一條流配兩個區域表達不出這一種 —— 而它正是使用者列的三種裡的中間那一種
    （patch 跟 ref 那張的同一塊比）。
    """
    ctx = _ctx()
    ctx.set_image("ref", np.asarray(ctx.images["test"]) - 25.0)
    _run(ctx, roi="hot", reference="another stream", reference_source="ref")
    assert ctx.features["cmp_delta_mean"] == pytest.approx(25.0, abs=1.0)


def test_it_declares_both_streams_and_both_regions():
    """畫布上要有**兩個**輸入埠，lint 要看得到兩個區域。"""
    card = get_step("glv_stats")
    across = dict(BASE, reference="another stream", reference_source="ref")
    assert card.resolve_reads(across) == ["test", "ref"]
    # 跟另一條流比 = **同一塊**在兩張圖上，所以區域只有一個
    assert card.resolve_regions_in(across) == ["hot"]
    # 跟另一塊比 = 一條流、兩個區域
    assert card.resolve_reads(BASE) == ["test"]
    assert card.resolve_regions_in(BASE) == ["hot", "cold"]


def test_the_declared_features_are_what_it_writes():
    ctx = _run(_boxed_ctx())
    declared = set(get_step("glv_stats").resolve_features(BASE))
    assert set(ctx.features) == declared


def test_what_it_cannot_compute_is_absent_not_nan():
    """參照只有一格 → 沒有「框與框之間」的散布 → ``snr`` / ``tstat`` 不寫。

    **不是寫 NaN**：`NaN < threshold` 是 False，那顆 defect 會被安靜地判成真
    缺陷（`tests/test_card_invariants.py` 的 I5）。也不是退回 per-pixel ——
    同一個名字在不同情況下算出不同的東西，是最難發現的那種錯。

    宣告不變（宣告是「**可能**會產出的」，同 nm 孿生的理由）。
    """
    ctx = _run(_ctx())                       # cold 只有一格
    assert "cmp_delta_mean" in ctx.features   # 這些照樣算得出來
    assert "cmp_snr_mean" not in ctx.features
    assert "cmp_tstat_mean" not in ctx.features
    assert all(not np.isnan(v) for v in ctx.features.values())


def test_the_prefix_applies():
    """絕對量與相對量吃**同一個前綴** —— 所以看得出來講的是同一塊。

    名字本身分得出兩者（F18 補課第三輪，使用者：「絕對量的跟相對量的還是要
    分類好」）：``glv_`` 是這一塊自己的灰階，``cmp_`` 是跟參照比出來的，而
    統計量在名字尾巴上（勾了好幾個也不會撞）。
    """
    ctx = _run(_ctx(), output_prefix="epi_vs_mg", compare_metrics="delta")
    assert set(ctx.features) == {"epi_vs_mg_cmp_delta_mean",
                                 "epi_vs_mg_glv_mean",
                                 "epi_vs_mg_glv_pixels"}


# --------------------------------------------------------------------------- #
# 2. 同一塊比自己 —— 在跑之前就擋
# --------------------------------------------------------------------------- #
def test_comparing_a_region_with_itself_is_caught_before_the_run():
    """每個數字恆為 0，而那些 0 **不會因為任何缺陷而改變** ——
    跑得完、有數字、而且那些數字什麼都沒說。"""
    says = get_step("glv_stats").configuration_issues(
        dict(BASE, reference_region="hot"))
    assert says and "zero no matter what" in says[0]


def test_the_same_region_on_two_different_streams_is_fine():
    """那正是情況 2 —— 不可以連它一起擋掉。"""
    assert get_step("glv_stats").configuration_issues(
        dict(BASE, reference="another stream", reference_source="ref")) == []


def test_nothing_picked_yet_points_at_the_field():
    """訊息要指向**填得到的東西**（`test_ui_f7_9_feedback` 的不變量）。"""
    says = get_step("glv_stats").configuration_issues(
        dict(BASE, reference_region=""))
    assert says
    labels = {p.label for p in get_step("glv_stats").params}
    assert "“That region”" in says[0]
    assert "That region" in labels


def test_running_with_nothing_picked_says_so():
    with pytest.raises(StepError) as e:
        _run(_ctx(), reference_region="")
    assert "none is picked" in str(e.value)


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
        _run(_ctx(), reference="another stream", reference_source="diff")
    assert "does not exist here" in str(e.value) and "test" in str(e.value)


# --------------------------------------------------------------------------- #
# 4. 算術：**不發明第三種 SNR**
# --------------------------------------------------------------------------- #
def test_snr_is_by_box_and_never_negative():
    """使用者定調 2026-08-21：**by box、而且不帶正負號**。

    * 分母是「參照那一塊**每一格**的 stat」之間的標準差 —— per-pixel 的 σ 裡有
      shot noise，它比同材質格子之間的差大得多，於是 SNR 被壓得很小，而那個小
      不是訊號弱，是分母裝錯東西（使用者：「by pixel 會太小」）。
    * 亮的缺陷與暗的缺陷給**同一個** snr —— 方向是 `delta` 的事
      （使用者：「有負代表亮暗差異而已」）。
    """
    ref_boxes = [98.0, 100.0, 102.0, 99.0, 101.0, 100.0]
    t = np.full(400, 140.0)
    r = np.full(400, 100.0)
    got = algo_glv.compare_pixels(t, r, reference_boxes=ref_boxes)
    assert got["snr"] == pytest.approx(40.0 / np.std(ref_boxes, ddof=1))

    dark = algo_glv.compare_pixels(np.full(400, 60.0), r,
                                   reference_boxes=ref_boxes)
    assert dark["snr"] == pytest.approx(got["snr"]), "亮暗一樣大"
    assert dark["delta"] < 0 < got["delta"], "方向由 delta 講"

    # 少於兩格 → 沒有 by-box 的散布 → nan（**不退回 per-pixel**）
    assert np.isnan(algo_glv.compare_pixels(t, r)["snr"])
    assert np.isnan(algo_glv.compare_pixels(t, r, reference_boxes=[100.0])["snr"])


def test_a_denominator_of_zero_is_nan_not_zero():
    """0 的意思是「沒有差異」，而這裡的事實是「這個問題答不出來」。"""
    got = algo_glv.compare_pixels(np.full(50, 120.0), np.full(50, 100.0))
    assert got["delta"] == pytest.approx(20.0)
    assert np.isnan(got["snr"]), "常數參考的 σ 是 0 —— snr 沒有答案"
    assert got["ratio"] == pytest.approx(1.2)
    got0 = algo_glv.compare_pixels(np.full(50, 20.0), np.zeros(50))
    assert np.isnan(got0["ratio"]) and np.isnan(got0["percent"])


def test_tstat_counts_the_boxes_and_snr_does_not():
    """同樣的差距，格子多的那一邊更值得相信 —— 而 `snr` 看不到這件事。

    （2026-08-21 起兩者的分母都 by box，所以「樣本數」指的是**幾格**，
    不再是幾個像素。）
    """
    rng = np.random.default_rng(5)
    t, r = np.full(400, 140.0), np.full(400, 100.0)
    few = [float(v) for v in rng.normal(100, 3, 4)]
    many = [float(v) for v in rng.normal(100, 3, 64)]

    a = algo_glv.compare_pixels(t, r, reference_boxes=few)
    b = algo_glv.compare_pixels(t, r, reference_boxes=many)
    assert a["snr"] == pytest.approx(b["snr"], rel=0.5), "snr 只看散布"
    assert b["tstat"] > a["tstat"] * 2.5, "格子數沒有進 tstat"


def test_the_statistic_being_compared_is_the_users_choice():
    """中位數會忽略幾顆很亮的點 —— 那正是「區域裡有一顆不是要量的東西」。"""
    ctx = _ctx(hot_glv=100.0, cold_glv=100.0, spread=0.0)
    img = np.asarray(ctx.images["test"]).copy()
    img[0, :3] = 255.0                      # 三顆亮點在 hot 那半邊
    ctx.set_image("test", img)
    mean = _run(ctx, stat="glv_mean",
                compare_metrics="delta").features["cmp_delta_mean"]
    ctx2 = _ctx(hot_glv=100.0, cold_glv=100.0, spread=0.0)
    ctx2.set_image("test", img)
    median = _run(ctx2, stat="glv_median",
                  compare_metrics="delta").features["cmp_delta_median"]
    assert mean > 0.1 and median == pytest.approx(0.0)


def test_contrast_survives_a_nearly_black_reference():
    """`ratio` / `percent` 在參照接近 0 的時候會噴出幾千 —— `contrast` 不會。

    這不是理論上的角落：`diff` 那一條流的背景本來就在 0 附近，而使用者是拿
    一個固定門檻去比這個數字的。
    """
    dim = algo_glv.compare_pixels(np.full(50, 12.0), np.full(50, 0.4))
    assert dim["ratio"] > 25.0, "比值在這裡沒有可用的刻度"
    assert -1.0 <= dim["contrast"] <= 1.0
    assert dim["contrast"] == pytest.approx((12.0 - 0.4) / 12.4)

    # 一樣亮 → 0；而它跟 delta 一樣**帶方向**
    same = algo_glv.compare_pixels(np.full(50, 90.0), np.full(50, 90.0))
    assert same["contrast"] == pytest.approx(0.0)
    dark = algo_glv.compare_pixels(np.full(50, 40.0), np.full(50, 90.0))
    assert dark["contrast"] < 0 < dim["contrast"]


def test_abs_delta_is_delta_without_the_direction():
    up = algo_glv.compare_pixels(np.full(50, 130.0), np.full(50, 100.0))
    down = algo_glv.compare_pixels(np.full(50, 70.0), np.full(50, 100.0))
    assert up["delta"] == pytest.approx(-down["delta"])
    assert up["abs_delta"] == down["abs_delta"] == pytest.approx(30.0)


def test_pct_rank_says_where_it_ranks_without_assuming_a_bell():
    """名次不假設那些格子是常態分布的 —— σ 說「幾倍」，它說「排第幾」。"""
    boxes = [98.0, 99.0, 100.0, 101.0, 102.0]
    r = np.full(200, 100.0)

    top = algo_glv.compare_pixels(np.full(200, 140.0), r, reference_boxes=boxes)
    assert top["pct_rank"] == pytest.approx(100.0), "比每一格都亮"
    bottom = algo_glv.compare_pixels(np.full(200, 10.0), r, reference_boxes=boxes)
    assert bottom["pct_rank"] == pytest.approx(0.0)
    mid = algo_glv.compare_pixels(np.full(200, 100.0), r, reference_boxes=boxes)
    assert mid["pct_rank"] == pytest.approx(50.0), "正中間（兩格低、一格同）"

    # 跟 snr / tstat 同一條規矩：少於兩格 → 沒有答案（**不是 0**）
    assert np.isnan(algo_glv.compare_pixels(np.full(9, 5.0), r)["pct_rank"])


def test_overlap_and_spread_ratio_see_what_one_statistic_cannot():
    """兩塊的平均一模一樣，而它們根本不是同一件事。

    這是「Report 只有 delta 那一族」時整個看不見的一種缺陷：`delta` = 0、
    `ratio` = 1、`snr` = 0，而其中一塊是雙峰的、粗糙度差三倍。
    """
    rng = np.random.default_rng(3)
    ref = rng.normal(100.0, 3.0, 4000)
    # 同樣的平均，一半 70 一半 130 —— 兩座山，沒有一個像素落在 100 附近
    tgt = np.concatenate([np.full(2000, 70.0), np.full(2000, 130.0)])

    got = algo_glv.compare_pixels(tgt, ref, stat="glv_mean")
    assert abs(got["delta"]) < 1.0, "壓成一個統計量之後它們一樣"
    assert got["overlap"] == pytest.approx(0.0, abs=1e-6), "連一個灰階都不共用"
    assert got["spread_ratio"] > 5.0, "粗糙得多"

    # 同一堆像素跟自己比 → 完全重疊、一樣粗
    same = algo_glv.compare_pixels(ref, ref.copy(), stat="glv_mean")
    assert same["overlap"] == pytest.approx(1.0)
    assert same["spread_ratio"] == pytest.approx(1.0)


def test_overlap_does_not_care_which_side_is_bigger():
    """參照常常是 target 的幾十倍大 —— 兩邊各自正規化，所以那不影響答案。"""
    rng = np.random.default_rng(7)
    small = rng.normal(100.0, 4.0, 300)
    big = rng.normal(100.0, 4.0, 30000)
    a = algo_glv.compare_pixels(small, big)["overlap"]
    b = algo_glv.compare_pixels(small, big[:3000])["overlap"]
    assert a == pytest.approx(b, abs=0.06)
    assert a > 0.7, "同一個母體的兩份樣本應該疊得很好"


def test_the_hidden_metrics_are_hidden_not_gone():
    """收起來 ≠ 刪掉（使用者 2026-08-21：「請幫我將這些收起來」）。

    卡片庫上沒有它們，但**手寫進 recipe 照樣算得出來、舊 recipe 照跑** ——
    那正是「收起來」值得選的理由：回復的成本是把字串搬回清單。
    """
    from d4t.core.steps.glv_stats import (COMPARE_CHOICES,
                                          HIDDEN_COMPARE_METRICS,
                                          HIDDEN_METRICS, METRIC_CHOICES)

    for mid in HIDDEN_METRICS:
        assert mid not in METRIC_CHOICES
        assert np.isfinite(algo_glv.glv_value(np.arange(64.0), mid))
    for mid in HIDDEN_COMPARE_METRICS:
        assert mid not in COMPARE_CHOICES
        assert mid in algo_glv.COMPARE_METRICS      # 驗證看的是這一份

    ctx = _run(_ctx(), metrics="glv_median,glv_entropy",
               compare_metrics="delta,percent")
    assert "glv_entropy" in ctx.features
    assert "cmp_percent_mean" in ctx.features


def test_several_statistics_can_be_compared_at_once():
    """使用者 2026-08-21：「我不能一次選擇 report glv_median 或 glv_pn 嗎？」

    可以 —— 而**統計量進到名字裡**，所以兩輪不會撞在一起。
    """
    ctx = _run(_boxed_ctx(hot_glv=140.0, cold_glv=100.0),
               stat="glv_median,glv_q90", compare_metrics="delta,snr")
    assert set(ctx.features) >= {"cmp_delta_median", "cmp_delta_q90",
                                 "cmp_snr_median", "cmp_snr_q90"}
    # 宣告與實際寫出來的**一字不差**（那是畫布與分數下拉的來源）
    assert set(get_step("glv_stats").resolve_features(
        dict(BASE, stat="glv_median,glv_q90",
             compare_metrics="delta,snr"))) >= {"cmp_delta_q90"}

    # P90 比中位數更靠近亮的那一端 —— 兩個數字不該一樣
    assert ctx.features["cmp_delta_median"] != ctx.features["cmp_delta_q90"]


def test_the_two_stat_free_reports_are_written_once():
    """`overlap` / `spread_ratio` 不看 stat —— 勾三個統計量也只有一個它。

    帶後綴的話會冒出 `cmp_overlap_median`、`cmp_overlap_q90`… 三個一模一樣的
    數字，而看到三個不同名字的人會以為它們在講三件事。
    """
    ctx = _run(_boxed_ctx(), stat="glv_median,glv_mean,glv_q90",
               compare_metrics="delta,overlap,spread_ratio")
    names = [n for n in ctx.features if n.startswith("cmp_")]
    assert names.count("cmp_overlap") == 1
    assert names.count("cmp_spread_ratio") == 1
    assert not [n for n in names if n.startswith("cmp_overlap_")]
    assert len([n for n in names if n.startswith("cmp_delta_")]) == 3


def test_the_stat_free_pair_is_computed_once_not_once_per_statistic():
    """只寫一次不夠 —— **也只能算一次**。

    `overlap` 是一趟 256 bin 的直方圖，而一格一格量的 RSEM 大圖上有幾百格；
    勾三個統計量就重算三次的話，那是同一張圖白算幾百次。
    """
    calls = []
    real = algo_glv.compare_pixels

    def spy(*a, **kw):
        calls.append(sorted(kw.get("want") or algo_glv.COMPARE_METRICS))
        return real(*a, **kw)

    algo_glv.compare_pixels = spy
    try:
        _run(_boxed_ctx(), stat="glv_median,glv_mean,glv_q90",
             compare_metrics="delta,overlap")
    finally:
        algo_glv.compare_pixels = real

    assert len(calls) == 3, "一個統計量一輪"
    assert calls[0] == ["delta", "overlap"]
    assert calls[1] == calls[2] == ["delta"], "第二、三輪不該再算 overlap"


def test_one_statistic_still_reads_like_the_old_single_choice():
    """舊 recipe 的 ``stat: "glv_mean"`` 是一個合法的「一個元素的清單」。

    所以這一格從下拉變成膠囊**不需要遷移** —— 需要遷移的是改名，而這裡沒改名。
    """
    from d4t.core.steps.glv_stats import _stats_of

    assert _stats_of({"stat": "glv_mean"}) == ["glv_mean"]
    assert _stats_of({}) == ["glv_mean"]
    assert _stats_of({"stat": ""}) == ["glv_mean"]
    assert _stats_of({"stat": "glv_median,glv_q90"}) == ["glv_median", "glv_q90"]


def test_the_name_says_which_side_of_the_card_it_came_from():
    """`glv_` 是這一塊自己的、`cmp_` 是比出來的 —— 規則一句話講得完。

    使用者 2026-08-21：「絕對量的跟相對量的還是要分類好，不然不清楚命名規則
    會很痛苦。」
    """
    from d4t.core.steps.glv_stats import cmp_feature_name

    assert cmp_feature_name("delta", "glv_median") == "cmp_delta_median"
    assert cmp_feature_name("snr", "glv_q90") == "cmp_snr_q90"
    # 不看 stat 的那兩個不帶後綴
    assert cmp_feature_name("overlap", "glv_q90") == "cmp_overlap"

    ctx = _run(_boxed_ctx(), metrics="glv_median", compare_metrics="delta,snr")
    absolute = {n for n in ctx.features if n.startswith("glv_")}
    relative = {n for n in ctx.features if n.startswith("cmp_")}
    assert absolute and relative
    assert absolute | relative == set(ctx.features)


def test_the_expression_migration_only_fires_on_the_old_name():
    """鐵則 9：判準是「舊東西在不在」，而且第二次跑要是 no-op。

    `to_json_dict → from_json_dict` 是 `run_batch` 送 recipe 進 worker 的路 ——
    它一旦不是 identity，``workers=1`` 與 ``workers=2`` 會算出不同的分數。
    """
    import json

    from d4t.core.pipeline import Recipe

    doc = {"recipe_id": "old", "version": 1,
           "routes": {"ebi_patch": ["cmp"]},
           "nodes": {"cmp": {"step": "glv_stats", "enabled": True,
                             "params": {"source": "test", "roi": "epi",
                                        "reference": "another region",
                                        "reference_region": "mg",
                                        "stat": "glv_median",
                                        "metrics": "glv_median",
                                        "compare_metrics": "delta,snr"}}},
           "edges": [],
           "score": {"expr": "delta / (my_delta_ratio + 1)", "threshold": 1.0,
                     "bins": {"below": 0, "above": 1}}}
    r = Recipe.from_json_dict(doc)
    # 整個識別字才算 —— `my_delta_ratio` 是使用者自己取的名字，不准被打斷
    assert r.score.expr == "cmp_delta_median / (my_delta_ratio + 1)"
    again = Recipe.from_json_dict(r.to_json_dict())
    assert again.score.expr == r.score.expr
    assert again.to_json_dict() == r.to_json_dict()


def test_the_panel_gets_the_reference_distribution_too():
    """面板要把參照那條分布疊上去（使用者 2026-08-21），所以引擎要留給它。

    **畫面上的數字就是引擎算的這一份** —— UI 不自己再跑一次統計，不然面板上
    的曲線跟真的寫出去的數字有機會不一樣。
    """
    ctx = _run(_boxed_ctx(hot_glv=140.0, cold_glv=100.0),
               stat="glv_median", compare_metrics="delta,snr")
    row = ctx.meta["glv_hist"][0]
    ref = row["ref"]
    assert ref["label"] == "cold" and ref["boxes"] == 6
    assert sum(ref["bins"]) == ref["n"] > 0
    # 兩邊的同一個統計量 —— 面板拿它們畫那一段 Δ
    assert ref["here"]["glv_median"] - ref["marks"]["glv_median"] == \
        pytest.approx(ctx.features["cmp_delta_median"], abs=1.0)
    assert ref["values"] == {k: v for k, v in ctx.features.items()
                             if k.startswith("cmp_")}

    # 不比的時候那一格是 None（面板據此決定畫不畫）
    plain = _run(_ctx(), reference="none")
    assert plain.meta["glv_hist"][0]["ref"] is None


def test_the_compare_note_carries_the_full_feature_names():
    """特徵表要說得出「這個數字是跟誰比的」，而名字裡沒有那件事。"""
    ctx = _run(_boxed_ctx(), output_prefix="epi_vs_mg",
               compare_metrics="delta")
    rec = list(ctx.meta["compares"].values())[0]
    assert rec["reference"] == "cold"
    assert rec["names"] == ["epi_vs_mg_cmp_delta_mean"]
    assert set(rec["names"]) <= set(ctx.features)


def test_an_unknown_comparison_is_refused_with_the_list():
    with pytest.raises(StepError) as e:
        _run(_ctx(), compare_metrics="delta,bogus")
    assert "bogus" in str(e.value) and "snr" in str(e.value)


# --------------------------------------------------------------------------- #
# 5. `region_key` 是**一個**區域
# --------------------------------------------------------------------------- #
def test_a_region_key_takes_one_name_not_a_list():
    """`region_keys`（複數）是逗號清單，這個不是 —— 而錯的那句話要是白話的。"""
    spec = ParamSpec(name="reference_region", type="region_key", direction="in",
                     default="", help="x")
    assert spec.validate("epi") == "epi"
    with pytest.raises(ParamError) as e:
        spec.validate("epi,mg")
    assert "one region name, not a list" in str(e.value)
    # 卡片名從 registry 拿 —— 這條測的是「訊息講得出該用哪張卡」，
    # 不是那張卡現在叫什麼（F16 改成了 Gray level）。
    assert "one %s card per pair" % get_step("glv_stats").label in str(e.value)


def test_the_card_uses_the_right_plurality_for_each_region_field():
    """量的那一格是**一串**（同一件事做在好幾塊上），參照那一格是**一個**。

    單數／複數的意思跟影像流一字不差（F13-⑥）：複數的第二條線是累加，
    單數的第二條線是取代 —— 而「跟誰比」只有一個答案。
    """
    kinds = {p.name: p.type for p in get_step("glv_stats").params}
    assert kinds["roi"] == "region_keys"
    assert kinds["reference_region"] == "region_key"
    assert kinds["source"] == "image_keys"
    assert kinds["reference_source"] == "image_key"


# --------------------------------------------------------------------------- #
# 6. 儀表看到的就是引擎算的
# --------------------------------------------------------------------------- #
def test_the_panel_sees_the_same_numbers():
    ctx = _run(_ctx())
    rec = ctx.meta["compares"]["hot_vs_cold"]
    assert rec["values"]["cmp_delta_mean"] == ctx.features["cmp_delta_mean"]
    assert rec["target_px"] == 40 * 20 and rec["reference_px"] == 40 * 20
    assert rec["stat"] == "glv_mean"


# --------------------------------------------------------------------------- #
# 7. 多連一：一張量測卡可以量好幾個區域（F13-⑥）
# --------------------------------------------------------------------------- #
def test_one_card_measures_several_regions():
    """使用者：「我想將 ROI A 跟 ROI B 的區域線一起接到 GLV stats」。

    同一組統計量、同一張圖，量在兩個區域上 —— 而每個數字帶自己的區域名，
    不然兩組會互相蓋掉（`Context.add_feature` 允許覆寫），而畫面上看不出來。
    """
    ctx = _ctx()
    p = {"source": "test", "roi": "hot,cold", "metrics": "glv_mean",
         "output_prefix": ""}
    get_step("glv_stats")().run(ctx, p)
    assert ctx.features["hot_glv_mean"] > ctx.features["cold_glv_mean"]
    assert set(ctx.features) == set(get_step("glv_stats").resolve_features(p))


def test_one_region_keeps_the_old_names():
    """只接一個時特徵名跟以前**逐字相同** —— 那是「分數表達式不必改寫」與
    「黃金值不動」的前提，跟影像流那一半同一個理由（`stream_prefix`）。"""
    ctx = _ctx()
    p = {"source": "test", "roi": "hot", "metrics": "glv_mean",
         "output_prefix": ""}
    get_step("glv_stats")().run(ctx, p)
    # `glv_pixels` 跟著每一塊走（F18 第 4 步）——「只接一個時逐字相同」講的是
    # **前綴**，不是「這張卡只吐一個數字」。
    assert list(ctx.features) == ["glv_mean", "glv_pixels"]


def test_streams_and_regions_multiply():
    """兩條流 × 兩個區域 = 四組數字，而每一組的名字都指得出它是誰。"""
    ctx = _ctx()
    ctx.set_image("ref", np.asarray(ctx.images["test"]) * 0.5)
    p = {"source": "test,ref", "roi": "hot,cold", "metrics": "glv_mean",
         "output_prefix": ""}
    get_step("glv_stats")().run(ctx, p)
    assert set(ctx.features) == {
        "test_hot_glv_mean", "test_cold_glv_mean",
        "ref_hot_glv_mean", "ref_cold_glv_mean",
        "test_hot_glv_pixels", "test_cold_glv_pixels",
        "ref_hot_glv_pixels", "ref_cold_glv_pixels"}


# --------------------------------------------------------------------------- #
# 8. F16：兩張卡收成一張（`glv_stats` 的兩個 method）
# --------------------------------------------------------------------------- #
def test_an_old_roi_compare_recipe_still_opens(tmp_path):
    """舊 recipe 裡的 `roi_compare` 節點要**走完兩道遷移**（F16 → F18），
    **而且相對值的特徵名逐字不變** —— 那些名字會被打進分數表達式。

    兩道：`roi_compare` → ``method="compare"`` → ``reference``。順序要緊，
    第一道產生的東西正是第二道的輸入。
    """
    import json
    from d4t.core.pipeline import Recipe

    doc = {
        "recipe_id": "old", "version": 1,
        "routes": {"ebi_patch": ["load", "cmp"]},
        "nodes": {
            "load": {"step": "load_patch", "params": {}, "enabled": True},
            "cmp": {"step": "roi_compare", "enabled": True, "params": {
                "target_source": "test", "target_region": "epi",
                "reference_source": "ref", "reference_region": "epi",
                "stat": "glv_median", "metrics": "delta,ratio",
                "output_prefix": "epi_vs_mg"}},
        },
        "edges": [],
        "score": {"expr": "epi_vs_mg_delta", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }
    path = tmp_path / "old.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    r = Recipe.load(str(path))
    node = r.nodes["cmp"]
    assert node.step == "glv_stats"
    assert "method" not in node.params, "第二道遷移做完要把舊鍵拿掉（idempotent）"
    assert node.params["reference"] == "another stream", \
        "兩邊的流不同 → 跟另一條流比"
    assert node.params["reference_source"] == "ref"
    assert node.params["source"] == "test" and node.params["roi"] == "epi"
    # `compare_metrics` 是 F16 換的名字（兩格清單的值互斥，共用一格會留下對方
    # 不認得的值）；`metrics` 補成 `stat` —— 舊卡片用那個統計量代表每一塊，
    # 所以「它的絕對值」正是使用者心裡的那個數字。
    assert node.params["compare_metrics"] == "delta,ratio"
    assert node.params["stat"] == "glv_median"
    assert node.params["metrics"] == "glv_median"
    # **相對值改叫 `cmp_*`**（F18 補課第三輪）—— 而分數表達式跟著改寫，
    # 不然那份 recipe 打開來是一條 unknown-feature 加一個算不出來的分數。
    got = set(get_step("glv_stats").resolve_features(node.params))
    assert got == {"epi_vs_mg_cmp_delta_median", "epi_vs_mg_cmp_ratio_median",
                   "epi_vs_mg_glv_median", "epi_vs_mg_glv_pixels"}
    assert r.score.expr == "epi_vs_mg_cmp_delta_median"
    # 表達式裡指得到的東西真的在（遷移改寫成一個不存在的變數是最糟的結果 ——
    # 跑起來才炸，而且炸在別的地方）
    assert r.score.expr in got

    # 走第二次不能再動它（`run_batch` 送 recipe 進 worker 走的正是那條路）
    again = Recipe.from_json_dict(r.to_json_dict())
    assert again.nodes["cmp"].params == node.params


def test_the_migration_keys_on_the_old_thing_being_there_not_the_new_one():
    """鐵則 9：判準是「`step` 就是 roi_compare」，不是「`method` 沒填」。

    靠「新東西不在」的話，一份**新**的 recipe（method 用預設的 stats、所以
    JSON 裡根本沒有 `method` 這個鍵）會被誤判成舊檔而被改成 compare ——
    而 `to_json_dict → from_json_dict` 一旦不是 identity，`workers=1` 與
    `workers=2` 就會算出不同的分數。那真的發生過（見 docs/PITFALLS.md）。
    """
    from d4t.core.pipeline.recipe import (
        RecipeNode, _migrate_roi_compare_into_glv_stats,
    )

    nodes = {"a": RecipeNode(id="a", step="glv_stats", params={}),
             "b": RecipeNode(id="b", step="glv_stats",
                             params={"metrics": "glv_mean"})}
    _migrate_roi_compare_into_glv_stats(nodes)
    for nid in ("a", "b"):
        assert "method" not in nodes[nid].params, \
            "沒有 method 的 glv_stats 是新 recipe 用預設值，不是舊檔"
    assert nodes["b"].params["metrics"] == "glv_mean"


def test_not_comparing_anything_is_the_default_and_still_measures():
    """不挑「跟誰比」就只有絕對值 —— 那是這張卡最常見的用法。"""
    ctx = _ctx(hot_glv=140.0, cold_glv=100.0)
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "hot",
        "metrics": "glv_mean,glv_std", "output_prefix": ""})
    assert ctx.features["glv_mean"] == pytest.approx(140.0, abs=1.0)
    assert "cmp_delta_mean" not in ctx.features


def test_the_absolute_numbers_come_out_even_when_it_compares():
    """F18 這一刀要解的坑：舊的 `compare` **從不輸出絕對值**。

    於是「這塊 EPI 的平均灰階是 120」跟「它比隔壁亮 12」不能在同一張卡上同時
    得到 —— 使用者得放兩張卡、接兩次線，而那兩張卡各自有機會設得不一樣。
    """
    ctx = _run(_ctx(hot_glv=140.0, cold_glv=100.0), compare_metrics="delta")
    assert ctx.features["glv_mean"] == pytest.approx(140.0, abs=1.0)
    assert ctx.features["cmp_delta_mean"] == pytest.approx(40.0, abs=1.0)


def test_the_other_regions_needs_no_second_line():
    """``the other regions`` 用的是 Region 卡的家族慣例（`<name>_others`）。

    那個名字跟 `<name>` 出自同一張卡，畫布上那條線已經在了 —— 所以它**不宣告**
    第二個區域輸入（F12 的規矩是「用到的每一個區域都要有一條線指到定義它的那
    張卡」，而這裡指的是同一張）。
    """
    card = get_step("glv_stats")
    p = dict(BASE, reference="the other regions")
    assert card.resolve_regions_in(p) == ["hot"]

    ctx = _ctx()
    ctx.set_roi_boxes("hot_others", [(0.5, 0.0, 0.5, 1.0)])
    get_step("glv_stats")().run(ctx, dict(p, compare_metrics="delta"))
    assert ctx.features["cmp_delta_mean"] == pytest.approx(40.0, abs=1.0)

    # 沒有 `_others` 的那一顆要講出真正的原因，而不是「少了一個東西」
    lonely = _ctx()
    lonely.meta.setdefault("regions_absent", {})["hot_others"] = (
        "this patch only has one copy of 'hot'")
    with pytest.raises(StepError) as e:
        get_step("glv_stats")().run(lonely, dict(p, compare_metrics="delta"))
    assert "only has one copy" in str(e.value)


def test_putting_the_metrics_in_the_wrong_box_is_caught():
    """兩格清單互斥，所以「填錯格」認得出來 —— 而它本來是安靜的：
    `compare` 只讀 `compare_metrics`，把 `delta,snr` 打進 Statistics 的人
    會拿到一張跑得完、吐著預設值、完全不理他的卡。"""
    card = get_step("glv_stats")
    says = card.configuration_issues(dict(BASE, metrics="delta,snr"))
    assert says and "Report" in says[0] and "Statistics" in says[0]

    says = card.configuration_issues(
        {"method": "stats", "compare_metrics": "glv_mean"})
    assert says and "Statistics" in says[0]

    # 正常的兩種設定都沒話說
    assert not card.configuration_issues(BASE)
    assert not card.configuration_issues(
        {"method": "stats", "metrics": "glv_mean", "roi": ""})


# --------------------------------------------------------------------------- #
# 9. 一格一格量（F18 第 6 步）—— RSEM 大圖上「哪一格跟別人不一樣」
# --------------------------------------------------------------------------- #
def _grid_ctx(n=5, side=100, hot_cell=12, hot=160.0, base=100.0):
    """一張大圖鋪 n×n 個框，其中一格比別人亮（RSEM 的重複單元）。"""
    img = np.full((side, side), base, np.float32)
    step = side // n
    r, c = divmod(hot_cell, n)
    img[r * step + 2:(r + 1) * step - 2, c * step + 2:(c + 1) * step - 2] = hot
    ctx = Context(images={"test": img})
    ctx.set_roi_boxes("cells", [
        (col / n + 0.02, row / n + 0.02, 1.0 / n - 0.04, 1.0 / n - 0.04)
        for row in range(n) for col in range(n)])
    return ctx


def test_measuring_each_box_finds_the_odd_one_out():
    """把幾百個重複單元平均起來，正好把缺陷抹掉。

    `roi_template` 在一張 1000×1000 上鋪得出 625 個框，而 pooled 模式問的是
    「這一整組長什麼樣」—— 那是 F8 多框區域本來的用途，對交界統計是對的，
    對「哪一格壞了」是錯的。
    """
    ctx = _grid_ctx()
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box"})

    assert ctx.features["boxes"] == 25.0
    assert ctx.features["glv_median_typical"] == pytest.approx(100.0)
    assert ctx.features["glv_median_outlier"] == pytest.approx(160.0)
    assert ctx.features["glv_median_outlier_box"] == 12.0, "缺陷定位的答案"

    # pooled（預設）答的是另一個問題，而它**看不出**那一格
    pooled = _grid_ctx()
    get_step("glv_stats")().run(pooled, {
        "source": "test", "roi": "cells", "metrics": "glv_median"})
    assert pooled.features["glv_median"] == pytest.approx(100.0)
    assert "glv_median_outlier" not in pooled.features


def test_each_box_declares_exactly_what_it_writes():
    """框的數量**隨影像而異**，所以逐格吐特徵是寫不出宣告的。

    宣告的是分布的兩端加一個地址 —— 那三個名字的數量不隨資料變。
    """
    card = get_step("glv_stats")
    p = {"source": "test", "roi": "cells", "metrics": "glv_median,glv_mad",
         "across_boxes": "each box"}
    assert set(card.resolve_features(p)) == {
        "glv_median_typical", "glv_median_outlier", "glv_median_outlier_box",
        "glv_mad_typical", "glv_mad_outlier", "glv_mad_outlier_box",
        "boxes", "glv_pixels",
        # F31：總冠軍那一組（照 `judge` 挑）＋ score 的分布。
        "worst_i", "worst_x", "worst_y", "worst_w", "worst_h",
        "worst_score", "worst_value", "score_median", "score_spread"}

    ctx = _grid_ctx()
    get_step("glv_stats")().run(ctx, p)
    assert set(ctx.features) == set(card.resolve_features(p))


def test_each_box_compares_each_box_too():
    """「跟隔壁材質比，**哪一格**最不一樣」—— RSEM 大圖上真正的問題。

    比較也一格一格算（參照那一塊是共用的），所以 delta 吃同一套後綴。
    """
    ctx = _grid_ctx()
    ctx.set_roi_boxes("background", [(0.0, 0.9, 1.0, 0.1)])
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box", "reference": "another region",
        "reference_region": "background", "compare_metrics": "delta"})
    assert ctx.features["cmp_delta_mean_typical"] == pytest.approx(0.0, abs=1.0)
    assert ctx.features["cmp_delta_mean_outlier"] == pytest.approx(60.0, abs=1.0)
    assert ctx.features["cmp_delta_mean_outlier_box"] == 12.0


def test_each_box_without_a_region_is_caught_before_the_run():
    """整張圖只有一格 —— 那時候這個選項不是錯，是**沒有作用**。

    而一個沒有作用的設定看起來跟一個有作用的一模一樣。
    """
    says = get_step("glv_stats").configuration_issues(
        {"across_boxes": "each box", "roi": ""})
    assert says and "does nothing" in says[0]
    assert get_step("glv_stats").configuration_issues(
        {"across_boxes": "each box", "roi": "cells"}) == []


def test_a_box_too_small_to_measure_is_skipped_not_counted_as_zero():
    """框是鋪出來的，壓在影像邊上只剩幾個像素是正常的。

    那一格的統計量會把 typical 拉走，所以它**不算**（而 `boxes` 說得出來
    真正量了幾格）。
    """
    ctx = _grid_ctx()
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box", "min_pixels": 400})
    assert ctx.features["boxes"] == 0.0, "每一格都只有 256 px，全部低於下限"
    assert ctx.features["glv_ok"] == 0.0
    assert "glv_median_typical" not in ctx.features


# --------------------------------------------------------------------------- #
# 10. 兩邊都不一樣的那一種（2026-08-21 使用者問出來的洞）
# --------------------------------------------------------------------------- #
def test_another_region_on_another_stream():
    """`test` 的 `epi_center` 對上 `ref` 的 `epi_others`。

    使用者原話：「如果我想要比對的是兩個 source，test 取 EPI_center、ref 則是
    EPI_others，這種的我要怎麼拉線?」—— 答案是**當時拉不出來**。

    F18 第 5 步把 `method` 二選一拆成「跟誰比」的時候漏了這一格，而漏得很難看：
    `another stream` 那條路把 `reference_region` **安靜地忽略掉**，於是那份設定
    跑得完、有數字，而那個數字答的是「同一塊在另一條流上」。舊的
    `method="compare"` 有四個獨立的角色參數，所以它表達得出這一種。
    """
    ctx = _ctx()                                   # hot=140, cold=100
    ctx.set_image("ref", np.asarray(ctx.images["test"]) - 25.0)
    _run(ctx, roi="hot", reference="another region on another stream",
         reference_source="ref", reference_region="cold",
         compare_metrics="delta")
    # 140 (hot @ test) − 75 (cold @ ref) = 65，**不是** 25（那是同一塊的答案）
    assert ctx.features["cmp_delta_mean"] == pytest.approx(65.0, abs=1.5)

    card = get_step("glv_stats")
    p = dict(BASE, reference="another region on another stream",
             reference_source="ref", reference_region="cold")
    assert card.resolve_reads(p) == ["test", "ref"], "兩個影像埠"
    assert card.resolve_regions_in(p) == ["hot", "cold"], "兩個區域埠"

    # 兩格都要填 —— 少一格在跑之前就講
    assert card.configuration_issues(dict(p, reference_region=""))
    assert card.configuration_issues(dict(p, reference_source=""))
    assert card.configuration_issues(p) == []


def test_the_migration_covers_the_whole_truth_table(tmp_path):
    """流一不一樣 × 區域一不一樣 —— 四格，舊 recipe 每一格都要落對地方。

    第一版漏了「兩邊都不一樣」，於是那種舊 recipe 被安靜地轉成「同一塊、另一條
    流」。特徵名一樣、跑得完、數字不同 —— 這是最難發現的那一種。
    """
    import json
    from d4t.core.pipeline import Recipe

    def migrated(**over):
        doc = {"recipe_id": "old", "version": 1,
               "routes": {"ebi_patch": ["cmp"]},
               "nodes": {"cmp": {"step": "glv_stats", "enabled": True,
                                 "params": dict(
                                     {"method": "compare",
                                      "target_source": "test",
                                      "target_region": "epi",
                                      "reference_source": "test",
                                      "reference_region": "mg",
                                      "stat": "glv_mean",
                                      "compare_metrics": "delta"}, **over)}},
               "edges": [], "score": {"expr": "delta", "threshold": 1.0,
                                      "bins": {"below": 0, "above": 1}}}
        path = tmp_path / ("%s.json" % abs(hash(json.dumps(doc, sort_keys=True))))
        path.write_text(json.dumps(doc), encoding="utf-8")
        return Recipe.load(str(path)).nodes["cmp"].params

    same_stream = migrated()
    assert same_stream["reference"] == "another region"
    assert same_stream["reference_region"] == "mg"

    same_region = migrated(reference_source="ref", reference_region="epi")
    assert same_region["reference"] == "another stream"
    assert same_region["reference_source"] == "ref"

    both = migrated(reference_source="ref", reference_region="epi_others")
    assert both["reference"] == "another region on another stream"
    assert both["reference_source"] == "ref"
    assert both["reference_region"] == "epi_others"


# --------------------------------------------------------------------------- #
# 10. 逐框比較的總冠軍（F31）—— 「這張圖最異常的地方」有座標、有分數
# --------------------------------------------------------------------------- #
def _run_each_box(ctx, **over):
    p = {"source": "test", "roi": "cells", "metrics": "glv_median",
         "across_boxes": "each box"}
    p.update(over)
    get_step("glv_stats")().run(ctx, p)
    return ctx


def test_the_worst_box_is_the_hot_one():
    """25 格裡亮的那一格就是 worst —— 分數是「偏離其他格幾個穩健 σ」。"""
    ctx = _run_each_box(_grid_ctx(hot_cell=12))
    assert ctx.features["worst_i"] == 12.0
    assert ctx.features["worst_value"] == pytest.approx(160.0)
    # 其他 24 格完全一樣（spread 踩地板 1 灰階）→ score = |160-100| / 1 = 60
    assert ctx.features["worst_score"] == pytest.approx(60.0)
    assert ctx.features["score_median"] == pytest.approx(0.0)


def test_the_worst_box_is_the_roi_box_itself():
    """座標不另外量：逐位元組就是 `ctx.roi_rects()[worst_i]` 那一格。

    「只有一種框」—— ROI 的框既是輸入也是報表上畫的那個框。把 bug 放回去的
    形狀是任何一種自己換算座標的寫法（正規化來回、中心點重算）。
    """
    ctx = _run_each_box(_grid_ctx(hot_cell=7))
    wi = int(ctx.features["worst_i"])
    x, y, w, h = ctx.roi_rects("cells", ctx.images["test"].shape[:2])[wi]
    assert ctx.features["worst_x"] == float(x)
    assert ctx.features["worst_y"] == float(y)
    assert ctx.features["worst_w"] == float(w)
    assert ctx.features["worst_h"] == float(h)


def test_identical_boxes_do_not_divide_by_zero():
    """其他格完全相同 → spread 是 0 → 地板（1 灰階）接住，score 全體是 0。"""
    ctx = _run_each_box(_grid_ctx(hot=100.0))     # 亮格跟別人一樣亮
    assert ctx.features["worst_score"] == pytest.approx(0.0)
    assert ctx.features["score_median"] == pytest.approx(0.0)
    assert ctx.features["score_spread"] == pytest.approx(0.0)
    assert np.isfinite(ctx.features["worst_value"])


def test_a_single_box_has_no_other_boxes_to_compare():
    """單框不吐 worst 那一組（沒得比），但**不偷退 pooled**（boxes = 1）。

    退回 pooled 的話同一格參數有兩種意思，而且宣告（帶後綴的名字）跟寫出的
    （裸名）對不上 —— 那正是以前 `_each_box` 寫 `> 1` 時的樣子。
    """
    img = np.full((60, 60), 100.0, np.float32)
    ctx = Context(images={"test": img})
    ctx.set_roi_boxes("cells", [(0.1, 0.1, 0.4, 0.4)])
    _run_each_box(ctx)
    assert ctx.features["boxes"] == 1.0
    assert "glv_median_typical" in ctx.features       # 不是 pooled 的裸名
    assert "glv_median" not in ctx.features
    for name in ("worst_i", "worst_x", "worst_score", "worst_value",
                 "score_median", "score_spread"):
        assert name not in ctx.features


def test_the_judge_changes_who_wins():
    """判準是使用者的一格：中位數看不見的一顆亮點，max 看得見。

    一格裡塞一顆很亮的單點：它動不了那一格的 median，但 max 直接變成它。
    """
    ctx = _grid_ctx(hot=100.0)                        # 全部格子一樣
    img = ctx.images["test"]
    # cells[6] 的正中央放一顆亮點（格子 20px、邊距 2px → cell 6 = row1,col1）
    x, y, w, h = ctx.roi_rects("cells", img.shape[:2])[6]
    img[y + h // 2, x + w // 2] = 250.0
    by_median = _run_each_box(ctx)
    assert by_median.features["worst_score"] == pytest.approx(0.0)

    ctx2 = _grid_ctx(hot=100.0)
    img2 = ctx2.images["test"]
    img2[y + h // 2, x + w // 2] = 250.0
    by_max = _run_each_box(ctx2, judge="glv_max")
    assert by_max.features["worst_i"] == 6.0
    assert by_max.features["worst_value"] == pytest.approx(250.0)
    assert by_max.features["worst_score"] > 10.0


def test_the_overlay_note_is_the_same_computation():
    """meta 的 `worst` 跟特徵是**同一次計算** —— 疊圖讀它畫框、標像素。

    `spread` 已含地板，所以 score == |value − baseline| / spread 逐位元組
    成立 —— 像素標記用同一條除法，不必自己知道地板的存在。
    """
    ctx = _run_each_box(_grid_ctx(hot_cell=12))
    notes = [n for n in ctx.meta["glv_hist"] if n.get("worst")]
    assert len(notes) == 1
    worst = notes[0]["worst"]
    assert worst["i"] == int(ctx.features["worst_i"])
    assert worst["score"] == ctx.features["worst_score"]
    assert worst["value"] == ctx.features["worst_value"]
    assert worst["rect"] == [int(ctx.features["worst_x"]),
                             int(ctx.features["worst_y"]),
                             int(ctx.features["worst_w"]),
                             int(ctx.features["worst_h"])]
    assert worst["judge"] == "glv_median"
    assert worst["score"] == pytest.approx(
        abs(worst["value"] - worst["baseline"]) / worst["spread"])


def test_pooled_and_no_region_write_no_worst():
    """pooled 一個位元不動；沒接區域的 each box 也不會憑空長出 worst。"""
    pooled = _grid_ctx()
    get_step("glv_stats")().run(pooled, {
        "source": "test", "roi": "cells", "metrics": "glv_median"})
    assert not any(k.startswith("worst") for k in pooled.features)
    assert not any(n.get("worst") for n in pooled.meta["glv_hist"])
