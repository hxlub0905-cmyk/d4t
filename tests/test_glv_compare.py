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
    _run(ctx, roi="hot", reference="another stream", reference_source="ref")
    assert ctx.features["delta"] == pytest.approx(25.0, abs=1.0)


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
    ctx = _run(_ctx())
    declared = set(get_step("glv_stats").resolve_features(BASE))
    assert set(ctx.features) == declared


def test_the_prefix_applies():
    """相對值的名字**逐字不變** —— 那是舊 recipe 的分數表達式不必改寫的前提。

    絕對值與樣本數是 F18 疊上去的（`compare` 以前從不吐絕對值，而那正是這一刀
    要解的坑），它們吃同一個前綴，所以看得出來講的是同一塊。
    """
    ctx = _run(_ctx(), output_prefix="epi_vs_mg", compare_metrics="delta")
    assert set(ctx.features) == {"epi_vs_mg_delta", "epi_vs_mg_glv_mean",
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
    mean = _run(ctx, stat="glv_mean", compare_metrics="delta").features["delta"]
    ctx2 = _ctx(hot_glv=100.0, cold_glv=100.0, spread=0.0)
    ctx2.set_image("test", img)
    median = _run(ctx2, stat="glv_median", compare_metrics="delta").features["delta"]
    assert mean > 0.1 and median == pytest.approx(0.0)


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
    assert rec["values"]["delta"] == ctx.features["delta"]
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
    # **相對值的名字逐字相同** —— 分數表達式不用改寫。絕對值與樣本數是疊上去的。
    got = set(get_step("glv_stats").resolve_features(node.params))
    assert {"epi_vs_mg_delta", "epi_vs_mg_ratio"} <= got
    assert got == {"epi_vs_mg_delta", "epi_vs_mg_ratio",
                   "epi_vs_mg_glv_median", "epi_vs_mg_glv_pixels"}

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
    assert "delta" not in ctx.features


def test_the_absolute_numbers_come_out_even_when_it_compares():
    """F18 這一刀要解的坑：舊的 `compare` **從不輸出絕對值**。

    於是「這塊 EPI 的平均灰階是 120」跟「它比隔壁亮 12」不能在同一張卡上同時
    得到 —— 使用者得放兩張卡、接兩次線，而那兩張卡各自有機會設得不一樣。
    """
    ctx = _run(_ctx(hot_glv=140.0, cold_glv=100.0), compare_metrics="delta")
    assert ctx.features["glv_mean"] == pytest.approx(140.0, abs=1.0)
    assert ctx.features["delta"] == pytest.approx(40.0, abs=1.0)


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
    assert ctx.features["delta"] == pytest.approx(40.0, abs=1.0)

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
        "boxes", "glv_pixels"}

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
    assert ctx.features["delta_typical"] == pytest.approx(0.0, abs=1.0)
    assert ctx.features["delta_outlier"] == pytest.approx(60.0, abs=1.0)
    assert ctx.features["delta_outlier_box"] == 12.0


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
    assert ctx.features["delta"] == pytest.approx(65.0, abs=1.5)

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
