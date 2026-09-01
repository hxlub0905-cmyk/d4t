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
#: （`reference`）；**F67 連那一格都拿掉了** —— 有沒有在比、跟誰比，
#: 一律由 ``reference_region`` / ``reference_source`` 那兩顆埠有沒有接線決定
#: （見 `steps.glv_stats._reference_of`）。舊 recipe 由
#: `recipe._migrate_reference_into_ports` 接住（見
#: `test_an_old_roi_compare_recipe_still_opens`）。
#:
#: 這一份的每一條測的東西**都沒有變**，只有參數名跟著卡片走：
#: ``target_source/target_region`` 就是這張卡本來就在量的 ``source``/``roi``。
BASE = {"source": "test", "roi": "hot",
        "metrics": "glv_mean",
        "reference_region": "cold", "reference_source": "",
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
    _run(ctx, roi="hot", reference_region="", reference_source="ref")
    assert ctx.features["cmp_delta_mean"] == pytest.approx(25.0, abs=1.0)


def test_it_declares_both_streams_and_both_regions():
    """畫布上要有**兩個**輸入埠，lint 要看得到兩個區域。"""
    card = get_step("glv_stats")
    across = dict(BASE, reference_region="", reference_source="ref")
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
        dict(BASE, reference_region="", reference_source="ref")) == []


def test_not_wiring_anything_is_not_an_error_it_is_no_comparison():
    """F67：「挑了跟誰比卻沒挑到東西」這個狀態**構造上不存在**了。

    以前那是一格下拉配兩顆埠，所以「選了另一塊、但沒接線」是個講得出來的
    半成品狀態（一條 lint ＋ 一條跑起來的錯）。現在沒接線**就是**不比 ——
    卡片照樣吐絕對值，一句話都不必說。
    """
    card = get_step("glv_stats")
    idle = dict(BASE, reference_region="", reference_source="")
    assert card.configuration_issues(idle) == []
    ctx = _run(_ctx(), reference_region="", reference_source="")
    assert ctx.features["glv_mean"] > 0                  # 絕對值照樣有
    assert not [n for n in ctx.features if n.startswith("cmp_")]


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
        _run(_ctx(), reference_region="", reference_source="diff")
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
    plain = _run(_ctx(), reference_region="", reference_source="")
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
    """舊 recipe 裡的 `roi_compare` 節點要**走完三道遷移**（F16 → F18 → F67），
    **而且相對值的特徵名逐字不變** —— 那些名字會被打進分數表達式。

    三道：`roi_compare` → ``method="compare"`` → ``reference`` → 兩顆埠。
    順序要緊，每一道產生的東西正是下一道的輸入。
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
    assert "reference" not in node.params, "第三道（F67）做完也要把那一格拿掉"
    assert node.params["reference_source"] == "ref", \
        "兩邊的流不同 → 參照那顆流埠接著 ref"
    assert node.params["reference_region"] == "", \
        "同一塊在兩張圖上 —— 參照區域那顆埠**不接**，不然就變成第四種了"
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


def test_comparing_against_the_other_boxes_is_one_more_line():
    """「跟其餘那些比」F67 起就是把 ``<name>_others`` 接進參照那顆埠。

    以前它是下拉的第五個答案（``the other regions``），靠 Region 卡的家族慣例
    自己推出那個名字 —— 兩種寫法同時存在，而使用者被教的是接線那一種
    （F44 的 preset①）。現在只剩一種。
    """
    card = get_step("glv_stats")
    p = dict(BASE, reference_region="hot_others")
    assert card.resolve_regions_in(p) == ["hot", "hot_others"]

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


def test_the_other_regions_is_declared_so_the_lint_can_see_it():
    """F37：``the other regions`` 以前**不宣告**，於是健檢看不到它。

    代價是實測出來的：接 ``hot_center`` 再選「跟其餘那些比」時，
    `configuration_issues()` 回空的、`unknown-region` 也沉默，而**跑起來每一顆
    defect 各失敗一次**（找 ``hot_center_others``，那個名字沒有人產出）。
    錯誤訊息本身是好的，只是它出現在跑完一批之後。

    宣告出來之後，同一件事由既有的 `unknown-region` 在按下去之前講完。

    ⚠ **把 `resolve_regions_in` 裡那一段「參照那一個也要宣告」拿掉，
    這支測試會紅** —— 那就是它守著的東西。
    """
    card = get_step("glv_stats")

    # 上游那張 Region 卡吐的是 hot / hot_center / hot_others（`region_family`）。
    assert set(card.resolve_regions_in(dict(BASE, reference_region="hot_others"))
               ) <= {"hot", "hot_center", "hot_others"}

    # 接到一個沒有人產出的名字（例如 `_center` 的「其餘那些」）——
    # 宣告出來，`unknown-region` 才問得到。
    got = card.resolve_regions_in(
        dict(BASE, roi="hot_center", reference_region="hot_center_others"))
    assert "hot_center_others" in got

    # 什麼都沒接 = 不比，別憑空宣告一個參照區域。
    assert card.resolve_regions_in(
        dict(BASE, roi="", reference_region="")) == []


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

    assert ctx.features["glv_boxes"] == 25.0
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
        # F68：贏家那一格的每一個量（`_outlier` 是「這個量自己最極端的那格」，
        # `_worst` 是「judge 挑的那格」—— 兩者不一定是同一格）。
        "glv_median_worst", "glv_mad_worst",
        "glv_boxes", "glv_pixels",
        # F31：總冠軍那一組（照 `judge` 挑）＋ score 的分布。
        "glv_worst_i", "glv_worst_x", "glv_worst_y", "glv_worst_w",
        "glv_worst_h", "glv_worst_score", "glv_worst_value",
        "glv_worst_score_median", "glv_worst_score_spread"}

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
        "across_boxes": "each box",
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
    assert ctx.features["glv_boxes"] == 0.0, "每一格都只有 256 px，全部低於下限"
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
    _run(ctx, roi="hot", reference_source="ref", reference_region="cold",
         compare_metrics="delta")
    # 140 (hot @ test) − 75 (cold @ ref) = 65，**不是** 25（那是同一塊的答案）
    assert ctx.features["cmp_delta_mean"] == pytest.approx(65.0, abs=1.5)

    card = get_step("glv_stats")
    p = dict(BASE, reference_source="ref", reference_region="cold")
    assert card.resolve_reads(p) == ["test", "ref"], "兩個影像埠"
    assert card.resolve_regions_in(p) == ["hot", "cold"], "兩個區域埠"
    assert card.configuration_issues(p) == []

    # F67：**這一種不必再被誰記得**。兩顆埠都接了線就是它，所以「第一版漏了
    # 一格」那種錯在構造上不可能再發生 —— 少接一條線就是真值表上的另一格，
    # 而那一格照樣算得出東西（下面兩條）。
    assert card.resolve_regions_in(dict(p, reference_region="")) == ["hot"]
    assert card.resolve_reads(dict(p, reference_source="")) == ["test"]


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

    # F67 起真值表的四格**就是那兩顆埠的四種接法**，所以每一格斷言的是
    # 「哪一顆接著、哪一顆是空的」——「接著」與「空的」兩邊都要斷言：
    # 舊那一格選回去的時候另一顆埠的線不會自己剪掉，而照抄過來的線在 F67
    # 之後**就是答案**（見 `_migrate_reference_into_ports`）。
    same_stream = migrated()
    assert same_stream["reference_region"] == "mg"
    assert same_stream["reference_source"] == ""
    assert "reference" not in same_stream

    same_region = migrated(reference_source="ref", reference_region="epi")
    assert same_region["reference_source"] == "ref"
    assert same_region["reference_region"] == ""

    both = migrated(reference_source="ref", reference_region="epi_others")
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
    assert ctx.features["glv_worst_i"] == 12.0
    assert ctx.features["glv_worst_value"] == pytest.approx(160.0)
    # 其他 24 格完全一樣（spread 踩地板 1 灰階）→ score = |160-100| / 1 = 60
    assert ctx.features["glv_worst_score"] == pytest.approx(60.0)
    assert ctx.features["glv_worst_score_median"] == pytest.approx(0.0)


def test_the_worst_box_is_the_roi_box_itself():
    """座標不另外量：逐位元組就是 `ctx.roi_rects()[glv_worst_i]` 那一格。

    「只有一種框」—— ROI 的框既是輸入也是報表上畫的那個框。把 bug 放回去的
    形狀是任何一種自己換算座標的寫法（正規化來回、中心點重算）。
    """
    ctx = _run_each_box(_grid_ctx(hot_cell=7))
    wi = int(ctx.features["glv_worst_i"])
    x, y, w, h = ctx.roi_rects("cells", ctx.images["test"].shape[:2])[wi]
    assert ctx.features["glv_worst_x"] == float(x)
    assert ctx.features["glv_worst_y"] == float(y)
    assert ctx.features["glv_worst_w"] == float(w)
    assert ctx.features["glv_worst_h"] == float(h)


def test_identical_boxes_do_not_divide_by_zero():
    """其他格完全相同 → spread 是 0 → 地板（1 灰階）接住，score 全體是 0。"""
    ctx = _run_each_box(_grid_ctx(hot=100.0))     # 亮格跟別人一樣亮
    assert ctx.features["glv_worst_score"] == pytest.approx(0.0)
    assert ctx.features["glv_worst_score_median"] == pytest.approx(0.0)
    assert ctx.features["glv_worst_score_spread"] == pytest.approx(0.0)
    assert np.isfinite(ctx.features["glv_worst_value"])


def test_a_single_box_has_no_other_boxes_to_compare():
    """單框不吐 worst 那一組（沒得比），但**不偷退 pooled**（boxes = 1）。

    退回 pooled 的話同一格參數有兩種意思，而且宣告（帶後綴的名字）跟寫出的
    （裸名）對不上 —— 那正是以前 `_each_box` 寫 `> 1` 時的樣子。
    """
    img = np.full((60, 60), 100.0, np.float32)
    ctx = Context(images={"test": img})
    ctx.set_roi_boxes("cells", [(0.1, 0.1, 0.4, 0.4)])
    _run_each_box(ctx)
    assert ctx.features["glv_boxes"] == 1.0
    assert "glv_median_typical" in ctx.features       # 不是 pooled 的裸名
    assert "glv_median" not in ctx.features
    for name in ("glv_worst_i", "glv_worst_x", "glv_worst_score",
                 "glv_worst_value", "glv_worst_score_median",
                 "glv_worst_score_spread"):
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
    assert by_median.features["glv_worst_score"] == pytest.approx(0.0)

    ctx2 = _grid_ctx(hot=100.0)
    img2 = ctx2.images["test"]
    img2[y + h // 2, x + w // 2] = 250.0
    by_max = _run_each_box(ctx2, judge="glv_max")
    assert by_max.features["glv_worst_i"] == 6.0
    assert by_max.features["glv_worst_value"] == pytest.approx(250.0)
    assert by_max.features["glv_worst_score"] > 10.0


def test_the_overlay_note_is_the_same_computation():
    """meta 的 `worst` 跟特徵是**同一次計算** —— 疊圖讀它畫框、標像素。

    `spread` 已含地板，所以 score == |value − baseline| / spread 逐位元組
    成立 —— 像素標記用同一條除法，不必自己知道地板的存在。
    """
    ctx = _run_each_box(_grid_ctx(hot_cell=12))
    notes = [n for n in ctx.meta["glv_hist"] if n.get("worst")]
    assert len(notes) == 1
    worst = notes[0]["worst"]
    assert worst["i"] == int(ctx.features["glv_worst_i"])
    assert worst["score"] == ctx.features["glv_worst_score"]
    assert worst["value"] == ctx.features["glv_worst_value"]
    assert worst["rect"] == [int(ctx.features["glv_worst_x"]),
                             int(ctx.features["glv_worst_y"]),
                             int(ctx.features["glv_worst_w"]),
                             int(ctx.features["glv_worst_h"])]
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


# --------------------------------------------------------------------------- #
# 11. judge 自訂（F32）—— 清單只是常用的那幾個，手寫的 glv_q97 一樣合法
# --------------------------------------------------------------------------- #
def test_a_custom_percentile_can_judge_the_odd_box():
    ctx = _grid_ctx(hot_cell=12)
    _run_each_box(ctx, judge="glv_q90")
    assert ctx.features["glv_worst_i"] == 12.0
    meta = [n for n in ctx.meta["glv_hist"] if n.get("worst")][0]["worst"]
    assert meta["judge"] == "glv_q90"


def test_a_bad_judge_id_fails_loudly_not_quietly():
    """打錯的 id 不准安靜換成預設 —— 使用者以為照 glv_q97 挑、整批其實照
    median 挑，每一顆都吐得出正常的數字。"""
    with pytest.raises(StepError) as e:
        _run_each_box(_grid_ctx(), judge="glv_qq7")
    text = str(e.value)
    assert "glv_qq7" in text and "Pick the odd one by" in text


def test_judge_takes_one_id_not_a_list():
    with pytest.raises(ParamError):
        get_step("glv_stats").validate_params(
            {"judge": "glv_median,glv_max"})


def test_the_preview_outlines_the_worst_box_before_any_batch():
    """試跑（甚至只是預覽）當下就看得到贏家 —— `overlay_marks` 讀 worst note。

    形狀：典型那一格 1 條淡線＋4 角點，贏家**一個 X（兩條對角線）**——
    描邊會跟區域框完全重疊、同一個顏色，等於沒畫（實測截圖抓到的，
    典型格用角點的理由一字不差）。`focus` 指著 X 的第一條（滿 alpha）。
    """
    ctx = _run_each_box(_grid_ctx(hot_cell=12))
    card = get_step("glv_stats")
    lines, points, focus, labels = card.overlay_marks(ctx, {}, "test")
    assert len(lines) == len(points) == len(labels) == 3    # 1 典型 + 2 對角
    assert focus == 1                                        # X 的第一條
    wi = int(ctx.features["glv_worst_i"])
    wx, wy, ww, wh = ctx.roi_norm_rects("cells")[wi]
    xs = {round(pt[0], 6) for seg in lines[1:] for pt in seg}
    ys = {round(pt[1], 6) for seg in lines[1:] for pt in seg}
    assert xs == {round(wx, 6), round(wx + ww, 6)}
    assert ys == {round(wy, 6), round(wy + wh, 6)}
    # 對角線：每一條的兩端 x 不同、y 也不同（描邊的水平/垂直線做不到）
    for seg in lines[1:]:
        assert seg[0][0] != seg[1][0] and seg[0][1] != seg[1][1]
    assert set(labels) == {"cells"}


def test_no_worst_keeps_the_typical_focus():
    """單框比不出贏家 → 照舊聚焦典型那一格（畫面不長出一個假的主角）。"""
    ctx = _grid_ctx()
    ctx.meta["glv_hist"] = [{"region": "cells", "stream": "test",
                             "box": 2, "boxes": 3}]
    lines, _points, focus, _labels = get_step("glv_stats").overlay_marks(
        ctx, {}, "test")
    assert len(lines) == 1 and focus == 0


# --------------------------------------------------------------------------- #
# F37：名字的家族（2026-08-26）
# --------------------------------------------------------------------------- #
def test_glv_never_collides_with_the_region_cards_own_numbers():
    """GLV 寫的名字**不能**撞到 Region 卡對同一個區域寫的那五個。

    這是實測出來的：接兩個區域時 GLV 的前綴就是區域名，於是它的 ``boxes``
    變成 ``epi_boxes`` —— 而 Region 卡對 ``epi`` 也寫一個 ``epi_boxes``
    （`_util.REGION_FACTS`）。兩個數字，同一個名字：

    ==================  ==========================================
    Region 卡的         這個區域**有**幾個框
    GLV 的              其中幾格**量得出來**（像素太少的跳過）
    ==================  ==========================================

    lint 報得出來（`feature-collision`）、engine 也把先寫的救成
    ``<節點名>_epi_boxes`` —— 所以它從來不是安靜的。問題是這個撞名**由構造
    決定**：只要接兩個區域就一定發生，使用者再小心都躲不掉，而每一份正常
    recipe 上都會出現的警告最後就會被學會忽略（`_feature_collisions` 自己
    寫下的話，F11 Enhance-3 為 `clip_frac` 開的例外就是同一個形狀）。

    ⚠ **把 `BOX_COUNT` 改回 ``"boxes"`` 這支會紅** —— 那就是它守著的東西。
    """
    from d4t.core.steps._util import region_fact_names

    card = get_step("glv_stats")
    regions = ["epi", "mg"]
    mine = set(card.resolve_features(dict(
        source="test", roi=",".join(regions), metrics="glv_median",
        across_boxes="each box", judge="glv_median", reference="none",
        output_prefix="")))
    theirs = set(region_fact_names(regions))
    assert not (mine & theirs), (
        "GLV 與 Region 卡撞名：%s" % sorted(mine & theirs))


def test_every_number_this_card_writes_says_who_wrote_it():
    """這張卡吐的每一個名字都以 ``glv_`` 或 ``cmp_`` 開頭（去掉前綴之後）。

    F18 立了兩個家族（``glv_`` 是這一塊自己的灰階、``cmp_`` 是跟參照比出來
    的），而 F31 加進來的逐框那一族**一個記號都沒有** —— ``worst_score`` /
    ``score_median`` / ``boxes`` 排在一份同時有 ``cd_*`` 與 ``<n>_present``
    的 CSV 上，是唯一說不出自己是誰算的一族。F37 補上。

    ``score_median`` 那個名字特別值得記：在一份有分數表達式的 recipe 上它
    讀起來像「分數的中位數」，而它其實是逐框異常度的中位數。
    """
    card = get_step("glv_stats")
    names = card.resolve_features(dict(
        source="test", roi="", metrics="glv_median,glv_mad",
        across_boxes="each box", judge="glv_median",
        reference="another region", reference_region="bg",
        stat="glv_mean", compare_metrics="delta,snr", output_prefix=""))
    assert names
    stray = [n for n in names
             if not (n.startswith("glv_") or n.startswith("cmp_"))]
    assert not stray, "沒有家族記號的名字：%s" % stray


# --------------------------------------------------------------------------- #
# PR-2（2c）：worst 直方圖與 judge 值帶 —— 跟特徵**同一次計算**
# --------------------------------------------------------------------------- #
def test_worst_histogram_is_the_same_computation_as_the_worst_features():
    """`glv_hist` 的 worst 欄畫的框與分布 == `glv_worst_*` 特徵那一格。

    面板疊圖讀的是這一份 —— 各算一份的那天，「圖上標紅、數字說正常」遲早來。
    """
    ctx = _grid_ctx()
    img = ctx.images["test"]
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box"})
    note = ctx.meta["glv_hist"][0]
    worst = note["worst"]
    assert worst is not None
    wi = int(ctx.features["glv_worst_i"])
    rects = ctx.roi_rects("cells", img.shape[:2])
    assert worst["rect"] == [int(v) for v in rects[wi]], \
        "worst 的框要逐位元組是 ctx.roi_rects()[worst_i] 那一格"
    assert worst["rect"] == [int(ctx.features["glv_worst_x"]),
                             int(ctx.features["glv_worst_y"]),
                             int(ctx.features["glv_worst_w"]),
                             int(ctx.features["glv_worst_h"])]
    # bins 用同一格像素、同一支 pixel_hist 重算要逐項相同（預設旋鈕全關）。
    x, y, w, h = rects[wi]
    px = np.asarray(img[y:y + h, x:x + w], np.float64).ravel()
    counts, _ = algo_glv.pixel_hist(px, bins=get_step("glv_stats").HIST_BINS)
    assert worst["bins"] == [int(c) for c in counts]
    assert worst["n"] == int(px.size) and worst["n_raw"] == int(px.size)


def test_judge_band_holds_the_values_the_worst_was_judged_by():
    ctx = _grid_ctx(n=5)
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box"})
    judge = ctx.meta["glv_hist"][0]["judge"]
    assert judge is not None
    assert judge["stat"] == "glv_median"
    assert len(judge["values"]) == len(judge["boxes"]) == 25
    assert judge["sampled"] is False
    assert judge["worst_box"] == int(ctx.features["glv_worst_i"])
    assert judge["median"] == pytest.approx(float(np.median(judge["values"])))
    # 反空洞：worst 那一格的值真的坐在帶上（照 boxes 找得到）。
    at = judge["boxes"].index(judge["worst_box"])
    assert judge["values"][at] == pytest.approx(
        float(ctx.features["glv_worst_value"]))


def test_judge_band_samples_beyond_512_boxes_and_keeps_the_worst():
    """幾百格塞不進一條帶：>512 等距取樣、記 `sampled`、worst **必留**。"""
    n_cols, n_rows = 25, 24                      # 600 格
    img = np.full((240, 250), 100.0, np.float32)
    img[5:10, 5:10] = 200.0                      # 第 0 格是異常的那格
    ctx = Context(images={"test": img})
    ctx.set_roi_boxes("cells", [
        (c / n_cols, r / n_rows, 1.0 / n_cols, 1.0 / n_rows)
        for r in range(n_rows) for c in range(n_cols)])
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box"})
    judge = ctx.meta["glv_hist"][0]["judge"]
    assert judge["sampled"] is True
    assert len(judge["values"]) <= 512
    assert judge["worst_box"] in judge["boxes"], "取樣不准把 worst 丟掉"
    assert judge["worst_box"] == int(ctx.features["glv_worst_i"])


def test_single_box_emits_no_worst_and_no_judge_band():
    """一格沒有「其他格」可比 —— worst 與 judge 整組不出現，不是 0。"""
    ctx = _grid_ctx()
    ctx.set_roi_boxes("one", [(0.1, 0.1, 0.3, 0.3)])
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "one", "metrics": "glv_median",
        "across_boxes": "each box"})
    note = ctx.meta["glv_hist"][0]
    assert note["worst"] is None and note["judge"] is None
    assert "glv_worst_i" not in ctx.features


def test_glv_hist_meta_is_json_serializable():
    """快取 payload 走 `_meta_snapshot`（JSON-safe 才留得住）—— numpy 標量
    混進來的話，快取熱跑會**安靜地**少這一份。"""
    import json

    ctx = _grid_ctx()
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box"})
    json.dumps(ctx.meta["glv_hist"])   # 丟得進 JSON 就是過了


# --------------------------------------------------------------------------- #
# 12. F67：「跟誰比」就是那兩顆埠（那一格下拉沒有了）
# --------------------------------------------------------------------------- #
def test_the_truth_table_is_the_two_ports():
    """真值表的四格 = **兩顆埠的四種接法**（`_reference_of` 的唯一出處）。

    以前它另外寫成一格 `reference`，於是同一件事在卡上有兩個說法，而它們可以
    不一致（引擎讀那一格，使用者看的是線）。
    """
    from d4t.core.steps.glv_stats import (REF_BOTH, REF_NONE, REF_REGION,
                                          REF_STREAM, _reference_of)
    assert _reference_of({}) == REF_NONE
    assert _reference_of({"reference_region": "mg"}) == REF_REGION
    assert _reference_of({"reference_source": "ref"}) == REF_STREAM
    assert _reference_of({"reference_region": "mg",
                          "reference_source": "ref"}) == REF_BOTH
    # 空字串不是「有接」—— 那一格沒填跟沒有那一格是同一件事
    assert _reference_of({"reference_region": "  ", "reference_source": ""}) \
        == REF_NONE


def test_that_one_field_is_gone_for_good():
    """`reference` **不是被藏起來，是不存在了** —— 手寫 recipe 打進去會被擋。

    留一格「還認得、但不顯示」的話，一份舊 recipe 沒走遷移也照樣打得開，
    而它會安靜地贏過線（`CLAUDE.md` §5 那張表：收起來／刪掉是兩件事，
    而這一格的意思整個被線取代了，沒有「之後可能還要」的那一面）。
    """
    card = get_step("glv_stats")
    assert "reference" not in {p.name for p in card.params}
    with pytest.raises(ParamError):
        card.validate_params(dict(BASE, reference="another region"))


def test_a_leftover_reference_line_does_not_quietly_start_comparing(tmp_path):
    """遷移的**剪線那一半**（`_migrate_reference_into_ports`）。

    舊的 `reference` 選回 ``none`` 的時候，`reference_region` 上的線不會跟著
    剪掉 —— 以前無害（引擎讀的是那一格），F67 之後那條線**就是答案**。
    照抄過來的話，一份只報絕對值的 recipe 會安靜地開始吐 ``cmp_*``。
    """
    import json
    from d4t.core.pipeline import Recipe

    def loaded(reference):
        doc = {"recipe_id": "old", "version": 2,
               "routes": {"ebi_patch": ["roi", "glv"]},
               "nodes": {
                   "roi": {"step": "roi_reference", "enabled": True,
                           "params": {"method": "layout layers",
                                      "layers": "1:epi, 2:mg"}},
                   "glv": {"step": "glv_stats", "enabled": True, "params": {
                       "source": "test", "roi": "epi",
                       "reference": reference,
                       "reference_region": "mg", "reference_source": "ref",
                       "metrics": "glv_median", "stat": "glv_median",
                       "compare_metrics": "delta"}}},
               "edges": [["roi", "epi", "glv", "roi"],
                         ["roi", "mg", "glv", "reference_region"]],
               "score": {"expr": "glv_median", "threshold": 1.0,
                         "bins": {"below": 0, "above": 1}}}
        path = tmp_path / ("%s.json" % abs(hash(reference)))
        path.write_text(json.dumps(doc), encoding="utf-8")
        return Recipe.load(str(path))

    idle = loaded("none")
    assert idle.nodes["glv"].params["reference_region"] == ""
    assert idle.nodes["glv"].params["reference_source"] == ""
    assert not [e for e in idle.edges if e.dst_in == "reference_region"], \
        "線留著的話，那份 recipe 會安靜地開始比"
    assert not [n for n in get_step("glv_stats").resolve_features(
        idle.nodes["glv"].params) if n.startswith("cmp_")]

    # 反面：真的在比的那一份，線與值都要留著（連同**另一顆**埠該不該留）
    region = loaded("another region")
    assert region.nodes["glv"].params["reference_region"] == "mg"
    assert region.nodes["glv"].params["reference_source"] == ""
    assert [e.src_out for e in region.edges if e.dst_in == "reference_region"] \
        == ["mg"]


def test_the_other_regions_migrates_into_a_line_of_its_own(tmp_path):
    """``the other regions`` 以前不接線（靠 ``<roi>_others`` 的家族慣例）——
    遷移要**補出那條線**，而且來源是產出 ``<roi>`` 的同一張卡。"""
    import json
    from d4t.core.pipeline import Recipe

    doc = {"recipe_id": "old", "version": 2,
           "routes": {"ebi_patch": ["roi", "glv"]},
           "nodes": {
               "roi": {"step": "roi_reference", "enabled": True,
                       "params": {"method": "layout layers",
                                  "layers": "1:epi, 2:mg"}},
               "glv": {"step": "glv_stats", "enabled": True, "params": {
                   "source": "test", "roi": "epi",
                   "reference": "the other regions",
                   "metrics": "glv_median", "stat": "glv_median",
                   "compare_metrics": "delta"}}},
           "edges": [["roi", "epi", "glv", "roi"]],
           "score": {"expr": "glv_median", "threshold": 1.0,
                     "bins": {"below": 0, "above": 1}}}
    path = tmp_path / "others.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    r = Recipe.load(str(path))

    assert r.nodes["glv"].params["reference_region"] == "epi_others"
    assert [(e.src, e.src_out) for e in r.edges
            if e.dst_in == "reference_region"] == [("roi", "epi_others")]
    # 特徵名逐字不變 —— 那是舊分數表達式不必改寫的前提
    assert "cmp_delta_median" in get_step("glv_stats").resolve_features(
        r.nodes["glv"].params)
    # 走第二次不能再動它（`run_batch` 送 recipe 進 worker 走的正是那條路）
    again = Recipe.from_json_dict(r.to_json_dict())
    assert again.to_json_dict() == r.to_json_dict()


def test_every_region_against_one_others_line_says_so():
    """一條線只指得到一塊 —— 量好幾塊的時候那**不是**逐塊配對（F67 的 lint）。

    舊的 ``the other regions`` 是逐塊的（epi 跟 epi_others 比、mg 跟 mg_others
    比），而遷移只補得出第一條線。同名不同義的東西不准安靜。
    """
    card = get_step("glv_stats")
    p = dict(BASE, roi="hot,cold", reference_region="hot_others")
    says = card.configuration_hints(p)
    assert says and "one GLV card per region" in says[0]
    # **提醒，不是路障**：那個設定完全合法（有時候正是要的），所以它不可以
    # 出現在擋跑的那一支裡（F67 當天訂正 —— 它一開始寫錯了地方）。
    assert card.configuration_issues(p) == []
    # 一塊的時候什麼都不必說（那是 F44 的 preset①，最常見的那一種）
    assert card.configuration_hints(
        dict(BASE, roi="hot", reference_region="hot_others")) == []


# --------------------------------------------------------------------------- #
# 13. F68：方向、判準可以是「跟參照差多少」、贏家那格的全套統計量、幾格越線
# --------------------------------------------------------------------------- #
def _dir_ctx(vals=(100, 100, 100, 130, 70, 100)):
    """一列 n 個框，值由 `vals` 指定 —— 第 3 格亮、第 4 格暗。"""
    n = len(vals)
    img = np.zeros((20, 20 * n), np.float32)
    for i, v in enumerate(vals):
        img[:, i * 20:(i + 1) * 20] = float(v)
    ctx = Context(images={"test": img, "ref": np.full_like(img, 100.0)})
    ctx.set_roi_boxes("cells", [(i / n, 0.0, 1.0 / n, 1.0) for i in range(n)])
    return ctx


def _each_box(ctx, **over):
    p = {"source": "test", "roi": "cells", "metrics": "glv_median",
         "across_boxes": "each box"}
    p.update(over)
    get_step("glv_stats")().run(ctx, p)
    return ctx


def test_direction_decides_which_box_wins():
    """`both` 底下最亮的格跟最黑的格**平起平坐** —— 而使用者要的是其中一種。

    這一條刻意用「一亮一暗、離基準一樣遠」的資料：三個方向各挑到不同的格，
    所以它證明的是方向真的在作用，不是碰巧。
    """
    assert _each_box(_dir_ctx()).features["glv_worst_i"] == 3.0        # 亮的
    assert _each_box(_dir_ctx(), direction="brighter"
                     ).features["glv_worst_i"] == 3.0
    assert _each_box(_dir_ctx(), direction="darker"
                     ).features["glv_worst_i"] == 4.0                  # 暗的


def test_the_default_direction_is_exactly_what_it_did_before():
    """`both` ＝ F68 之前的**唯一**行為 —— 既有 recipe 的數字一個都不准動。"""
    a = _each_box(_dir_ctx(), direction="both").features
    b = _each_box(_dir_ctx()).features                 # 沒填 = 預設
    assert a == b
    # 而且 `both` 真的是絕對值：離基準一樣遠的一亮一暗分數相同
    assert a["glv_worst_score"] == pytest.approx(
        _each_box(_dir_ctx(), direction="darker").features["glv_worst_score"])


def test_the_outlier_family_follows_the_direction_too():
    """同一張卡上兩族名字不可以用兩種「極端」的定義。"""
    dark = _each_box(_dir_ctx(), direction="darker").features
    assert dark["glv_median_outlier"] == pytest.approx(70.0)
    assert dark["glv_median_outlier_box"] == 4.0
    bright = _each_box(_dir_ctx(), direction="brighter").features
    assert bright["glv_median_outlier"] == pytest.approx(130.0)


def _rough_ctx():
    """六個框：第 5 格比較亮，第 1 格一樣亮**但很粗糙**。"""
    rng = np.random.default_rng(0)
    n = 6
    img = np.zeros((30, 30 * n), np.float32)
    for i, v in enumerate((100, 100, 100, 100, 100, 160)):
        img[:, i * 30:(i + 1) * 30] = v + rng.normal(0, 3, (30, 30))
    img[:, 30:60] += rng.normal(0, 18, (30, 30))
    ctx = Context(images={"test": img, "ref": np.full_like(img, 100.0)})
    ctx.set_roi_boxes("cells", [(i / n, 0.0, 1.0 / n, 1.0) for i in range(n)])
    ctx.set_roi_boxes("bg", [(0.0, 0.0, 1.0 / n, 1.0)])
    return ctx


def _judged_by(judge):
    ctx = _rough_ctx()
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box", "judge": judge,
        "reference_region": "bg", "stat": "glv_median",
        "compare_metrics": "delta,abs_delta,ratio,contrast,overlap,"
                           "spread_ratio"})
    return int(ctx.features["glv_worst_i"])


def test_judging_by_a_comparison_really_uses_that_number():
    """F68：判準可以是「跟參照比出來的量」（使用者：「這才是正確的挑法」）。

    證明它真的在用另一個量，而不是名字換了而已：``spread_ratio`` 問的是
    「這一格比參照粗糙多少」，於是它挑中**一樣亮但很粗糙**的那一格，
    而不是最亮的那一格。
    """
    assert _judged_by("glv_median") == 5, "照絕對灰階挑 → 最亮的那格"
    assert _judged_by("spread_ratio") == 1, "照粗糙度挑 → 另一格"


def test_a_shared_reference_makes_most_comparisons_pick_the_same_box():
    """⚠ **這一條記的是一個限制，不是一個功能**（F68 實測發現）。

    參照是**一整塊、每一格共用**的（`_reference_block` 回一份 ``ref_px``），
    所以 ``delta`` = 這一格的統計量 − 一個常數、``ratio`` = 除以一個常數……
    而 `odd_box_scores` 是 leave-one-out 的偏離量除以偏離量的散布 ——
    **對這種單調變換免疫**。於是照它們挑，挑到的跟照絕對統計量挑**一模一樣**：

        照 glv_median 挑 → 第 5 格
        照 delta / abs_delta / ratio / contrast / overlap 挑 → 也是第 5 格

    差別要出現，參照必須**逐格不同**（第 i 格對上參照影像的第 i 格）——
    那是另一件事，見 `docs/plans/F68-*.md`。這支測試守著「不要以為已經做到了」。
    """
    same = [j for j in ("delta", "abs_delta", "ratio", "contrast", "overlap")
            if _judged_by(j) != _judged_by("glv_median")]
    assert same == [], (
        "有比較量開始挑到不同的格了 —— 如果那是因為做了逐格配對，"
        "請把這支測試改寫成它的正面版本：%s" % same)


def test_judging_by_a_comparison_without_a_reference_is_caught_before_the_run():
    """每一顆都會失敗的設定要擋在跑之前（`configuration_issues` 的判準）。"""
    card = get_step("glv_stats")
    says = card.configuration_issues(
        {"source": "test", "roi": "cells", "across_boxes": "each box",
         "judge": "snr"})
    assert says and "Pick the odd one by" in says[0]
    # 而手寫 recipe 硬跑的話，錯誤訊息要講得出原因
    with pytest.raises(StepError) as e:
        _each_box(_dir_ctx(), judge="snr")
    assert "no reference is wired" in str(e.value)


def test_the_winner_box_reports_every_statistic_that_was_ticked():
    """「最黑那格的 Q25」—— F68 之前只能把 judge 改成 q25 才拿得到。"""
    ctx = _each_box(_dir_ctx(), metrics="glv_median,glv_q25,glv_max",
                    direction="darker")
    f = ctx.features
    assert f["glv_worst_i"] == 4.0
    # 贏家那一格的每一個量都在，而且真的是**那一格**的值（第 4 格整片 70）
    for name in ("glv_median_worst", "glv_q25_worst", "glv_max_worst"):
        assert f[name] == pytest.approx(70.0), name
    # ⚠ 而 `_outlier` 那一族答的是另一個問題 —— 同一份資料上它們相等只是
    # 因為 judge 就是 median；把 judge 換掉就分家（下一條）。
    assert f["glv_median_outlier"] == pytest.approx(70.0)


def test_worst_and_outlier_are_not_the_same_box():
    """兩族名字的差別要**看得出來**，不然 `_worst` 只是 `_outlier` 的別名。"""
    # 值：max 最極端的是第 1 格（有一個亮點），median 最極端的是第 4 格
    n = 5
    img = np.full((20, 20 * n), 100.0, np.float32)
    img[:, 80:100] = 60.0                 # 第 4 格整片暗 → median 最極端
    img[0, 20:22] = 255.0                 # 第 1 格一個亮點 → max 最極端
    ctx = Context(images={"test": img})
    ctx.set_roi_boxes("cells", [(i / n, 0.0, 1.0 / n, 1.0) for i in range(n)])
    f = _each_box(ctx, metrics="glv_median,glv_max", judge="glv_median").features
    assert f["glv_worst_i"] == 4.0, "judge 是 median → 贏家是整片暗的那格"
    assert f["glv_max_outlier_box"] == 1.0, "max 自己最極端的是有亮點那格"
    assert f["glv_max_worst"] == pytest.approx(60.0), "贏家那格的 max"
    assert f["glv_max_outlier"] == pytest.approx(255.0), "另一格的 max"


def test_counting_the_boxes_over_the_line():
    """「一顆髒點」與「整片都不對」—— 現在特徵表上分得出來了。"""
    one_bad = _each_box(_dir_ctx((100, 100, 100, 100, 100, 40)),
                        over_k=3.0).features
    assert one_bad["glv_boxes_over_k"] == 1.0
    assert one_bad["glv_boxes_over_k_frac"] == pytest.approx(1 / 6)
    # 不填就整組不吐（不是 0）—— 0 讀起來像「數過了，沒有」
    assert "glv_boxes_over_k" not in _each_box(_dir_ctx()).features
    assert "glv_boxes_over_k" not in get_step("glv_stats").resolve_features(
        {"source": "test", "roi": "cells", "across_boxes": "each box"})


# --------------------------------------------------------------------------- #
# 14. F68：第 i 格對第 i 格（patch 的參照）
# --------------------------------------------------------------------------- #
def _patterned_pair():
    """test 與 ref 上是**同一個圖案**（一亮一暗交替），而 test 的第 3 格有缺陷。

    重點在第 2 格：它很亮，**但 ref 的第 2 格也很亮** —— 那是圖案不是缺陷。
    混成一堆的參照分不出第 2 格與第 3 格，逐格配對分得出來。
    """
    n = 6
    pattern = [60, 60, 150, 60, 150, 60]
    test = np.zeros((30, 30 * n), np.float32)
    ref = np.zeros((30, 30 * n), np.float32)
    for i, v in enumerate(pattern):
        test[:, i * 30:(i + 1) * 30] = float(v)
        ref[:, i * 30:(i + 1) * 30] = float(v)
    test[:, 90:120] = 150.0            # 第 3 格：ref 說該暗，它卻是亮的 ← 缺陷
    ctx = Context(images={"test": test, "ref": ref})
    ctx.set_roi_boxes("cells", [(i / n, 0.0, 1.0 / n, 1.0) for i in range(n)])
    return ctx


def _pair_run(pairing, judge="delta"):
    ctx = _patterned_pair()
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box", "judge": judge,
        "reference_source": "ref", "stat": "glv_median",
        "compare_metrics": "delta,abs_delta", "ref_pairing": pairing})
    return ctx.features


def test_pairing_box_to_box_finds_the_defect_that_pooling_hides():
    """F68 的主線（使用者：「patch 預設就用逐格配對」）。

    圖案上有亮有暗。混成一堆的參照 → 每一格都跟同一個數字比 → 挑到的是
    「本來就該亮」的那一格；逐格配對 → 圖案抵消 → 挑到真的不一樣的那一格。
    """
    per_box = _pair_run("per box")
    assert per_box["glv_worst_i"] == 3.0, "ref 說該暗、它卻是亮的那一格"
    # 那一格的 delta 是 +90（150 對上 ref 的 60）；其餘格都是 0
    assert per_box["cmp_delta_median_worst"] == pytest.approx(90.0)

    pooled = _pair_run("pooled")
    assert pooled["glv_worst_i"] != 3.0, \
        "混成一堆的參照挑不出它（這一條是上面那條的對照組）"


def test_the_pairing_default_is_per_box_but_old_recipes_keep_pooled(tmp_path):
    """**一個會動的預設等於安靜地改掉每一份舊 recipe 的數字**（CLAUDE.md §3）。

    新卡預設逐格配對（那才是對的），舊檔案由 `_migrate_glv_ref_pairing`
    釘回 ``pooled`` —— 數字逐位元組不變，而且畫面上看得到自己在用哪一種。
    """
    import json
    from d4t.core.pipeline import Recipe

    card = get_step("glv_stats")
    fresh = card.validate_params({"source": "test", "roi": "cells",
                                  "across_boxes": "each box",
                                  "reference_source": "ref"})
    assert fresh["ref_pairing"] == "per box", "新卡用對的那一種"

    doc = {"recipe_id": "old", "version": 2,
           "routes": {"ebi_patch": ["glv"]},
           "nodes": {"glv": {"step": "glv_stats", "enabled": True, "params": {
               "source": "test", "roi": "cells", "across_boxes": "each box",
               "reference_source": "ref", "metrics": "glv_median",
               "stat": "glv_median", "compare_metrics": "delta"}}},
           "edges": [], "score": {"expr": "glv_median_typical",
                                  "threshold": 1.0,
                                  "bins": {"below": 0, "above": 1}}}
    path = tmp_path / "old.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    got = Recipe.load(str(path)).nodes["glv"].params
    assert got["ref_pairing"] == "pooled", "舊檔案的數字不准因為打開它而改變"

    # 走第二次不能再動它（`run_batch` 送 recipe 進 worker 走的正是那條路）
    r = Recipe.load(str(path))
    again = Recipe.from_json_dict(r.to_json_dict())
    assert again.to_json_dict() == r.to_json_dict()


def test_pairing_is_only_offered_where_it_is_defined():
    """接了**另一塊區域**的話兩邊框數不同，第 i 格對不到第 i 格。"""
    spec = {p.name: p for p in get_step("glv_stats").params}["ref_pairing"]
    same_block = {"reference_source": "ref", "reference_region": "",
                  "across_boxes": "each box"}
    assert spec.visible_for(same_block)
    assert not spec.visible_for(dict(same_block, reference_region="mg"))
    assert not spec.visible_for(dict(same_block, across_boxes="pooled"))
    assert not spec.visible_for(dict(same_block, reference_source=""))
