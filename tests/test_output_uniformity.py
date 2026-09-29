# -*- coding: utf-8 -*-
# F85：均勻度的四種圖 — authored 2026-09-07.
"""`output_uniformity` —— **一張影像之內，一格框一個點**。

跟 `output_report` 的盒鬚圖差別只有一個，而那個差別就是它存在的理由：
那一張是「一個盒子＝判定樹的一片葉子，一個點＝一顆 defect」（整批），
這一張是「一個盒子＝一個區域，一個點＝一格框」（一張圖之內）。
兩者在畫面上長得一模一樣。

鎖在這裡的五件事：

1. 一顆寫五個檔（一頁 ＋ 一張圖一個 SVG）——**一份文件要的是一張圖一個檔**；
2. 沒有逐框數字的時候**不寫空白頁**，而且講出來（原因通常是 Gray level
   還停在 pooled）；
3. 預覽（`planned_files`）跟真的寫出來的**檔名對得上**；
4. 鎖定範圍真的傳得到圖上；
5. 「一張圖都沒勾」在畫布上就擋得住，不是跑完一批才講。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.export import uniformity_charts as uc               # noqa: E402
from d4t.core.ingest.dataset import load_dataset                  # noqa: E402
from d4t.core.pipeline import (                                   # noqa: E402
    get_step, run_batch, run_batch_steps,
)
from d4t.core.pipeline.recipe import (                            # noqa: E402
    Edge, Recipe, RecipeNode, ScoreSpec, hydrate_regions,
)

KIND = "rsem"


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample_rsem import generate
    return generate(str(tmp_path_factory.mktemp("unif")), n=3, seed=11)


@pytest.fixture(scope="module")
def dataset(lot):
    return load_dataset(lot["klarf"])


def recipe_for(folder, glv=None, **over):
    """一張大圖 → 鋪一組 ROI → Gray level(each box) → Write charts。

    **這就是使用者的用法**（PEAR 的替代品），所以測試走的是同一條路。
    """
    params = {"folder": str(folder), "metric": "glv_mean", "limit": 0}
    params.update(over)
    gp = {"source": "single", "across_boxes": "each box",
          "metrics": "glv_mean,glv_median", "judge": "glv_mean"}
    gp.update(glv or {})
    r = Recipe(
        recipe_id="unif_demo",
        routes={KIND: ["load", "roi", "glv", "dec", "out"]},
        nodes={
            "load": RecipeNode("load", "load_patch",
                               {"channel_map": "1:single"}),
            "roi": RecipeNode("roi", "roi_reference", {
                "method": "stripes in the image", "source": "single",
                # ⚠ **不填 `output_prefix`**（F117 F5）。這份 fixture 本來
                # 跟出貨的 recipe 一樣填了 `"cells"`，而 ROI 卡的 base 名裡
                # 已經有區域名了 —— 疊起來是 `cells_cells_area_px`。
                # 新的 `doubled-prefix` lint 當場咬住這一份。
                "roi_out": "cells", "place": "crossing", "pick": "none"}),
            "glv": RecipeNode("glv", "glv_stats", gp),
            "dec": RecipeNode("dec", "decision", {}),
            "out": RecipeNode("out", "output_uniformity", params),
        },
        edges=[Edge("load", "roi", "single", "source"),
               Edge("roi", "glv", "cells", "roi"),
               Edge("load", "glv", "single", "source"),
               # F123 期 2：Output 寫的是線上游的東西。
               Edge("glv", "dec", "numbers", "numbers"),
               Edge("dec", "out", "results", "results")],
        score=ScoreSpec(expr="glv_worst_score", threshold=3.0,
                        bins={"below": 0, "above": 1}))
    # ⚠ **手搭的 Recipe 要自己水合區域線。** `roi="cells"` 那一格是從線上
    # 算出來的、不寫進 JSON（鐵則 10），而 `from_json_dict` 才會做這件事 ——
    # 少了這一行，GLV 那張卡的 `roi` 是空的，於是它安靜地退回「量整張圖」，
    # 吐的是 pooled 的裸名而不是逐框的後綴。跑得完、有數字、而且是錯的。
    hydrate_regions(r.nodes, r.edges)
    return r


def run(dataset, folder, glv=None, **over):
    r = recipe_for(folder, glv=glv, **over)
    rows = run_batch(r, dataset, workers=1)
    bctx = run_batch_steps(r, dataset, rows)
    assert not bctx.errors, bctx.errors
    return bctx, rows


# --------------------------------------------------------------------------- #
# 1. 寫出什麼
# --------------------------------------------------------------------------- #
def test_every_defect_gets_a_page_and_one_file_per_figure(dataset, tmp_path):
    """**一份文件要的是一張圖一個檔** —— 從一頁裡把 SVG 剪出來是使用者
    做不到的事，所以兩種都寫。"""
    out = tmp_path / "unif"
    bctx, rows = run(dataset, out)
    # ⚠ 好幾顆的時候多一份 `index.html`（F86）—— 它不是任何一顆的頁面
    pages = [p for p in sorted(out.glob("*.html")) if p.name != "index.html"]
    assert len(pages) == len(rows) > 0
    for page in pages:
        stem = page.stem
        # ⚠ **預設勾的那幾張**，不是全部 —— 散佈圖的兩條軸要使用者自己挑
        # （`DEFAULT_CHARTS` 的說明）。
        for kind in uc.DEFAULT_CHARTS:
            assert (out / ("%s-%s.svg" % (stem, kind))).is_file(), kind
        text = page.read_text(encoding="utf-8")
        assert text.count("<svg") == len(uc.DEFAULT_CHARTS)
    assert str(out) in bctx.outputs


def test_only_the_ticked_charts_are_drawn(dataset, tmp_path):
    out = tmp_path / "two"
    _bctx, rows = run(dataset, out, charts="histogram,map")
    assert sorted(p.name.split("-")[-1] for p in out.glob("*.svg")) == \
        sorted(["histogram.svg", "map.svg"] * len(rows))


def test_the_preview_names_match_what_is_really_written(dataset, tmp_path):
    """寫出前一定先預覽（M5 的硬規則），而預覽跟真跑要對得上 ——
    儀表列的檔名跟真的寫出來的不一樣，比沒有預覽糟。"""
    out = tmp_path / "plan"
    card = get_step("output_uniformity")
    planned = card.planned_files({"folder": str(out), "charts": "box,profile"})
    run(dataset, out, charts="box,profile")
    real = {p.name for p in out.iterdir()}
    for row in planned:
        pattern = row["name"].replace("<defect>", "")
        assert any(name.endswith(pattern) for name in real), row


# --------------------------------------------------------------------------- #
# 2. 沒有逐框數字的時候
# --------------------------------------------------------------------------- #
def test_pooled_writes_nothing_and_says_why(dataset, tmp_path):
    """走 pooled ⇒ 「這幾格之間」不存在。

    **不寫一張空白頁** —— 一張畫得出來但沒有意義的圖比沒有圖糟。而
    一個空資料夾跟「這張卡沒被跑到」在畫面上長得一模一樣，所以要講。
    """
    out = tmp_path / "pooled"
    bctx, _ = run(dataset, out, glv={"across_boxes": "pooled"})
    assert list(out.glob("*.html")) == []
    assert any("each box" in w for w in bctx.warnings), bctx.warnings


def test_nothing_ticked_is_caught_on_the_canvas_not_after_the_run(tmp_path):
    """跑一整批才講「你什麼都沒勾」是最貴的講法。"""
    card = get_step("output_uniformity")
    issues = card.configuration_issues({"folder": str(tmp_path), "charts": ""})
    assert issues and "Tick at least one" in issues[0]
    assert card.configuration_issues({"folder": str(tmp_path),
                                      "charts": "box"}) == []


def test_a_folder_that_is_a_file_is_caught_too(tmp_path):
    """跟另外兩張寫資料夾的卡走同一支 `path_issue`。"""
    f = tmp_path / "notafolder.txt"
    f.write_text("x", encoding="utf-8")
    issues = get_step("output_uniformity").configuration_issues(
        {"folder": str(f), "charts": "box"})
    assert issues and "not a folder" in issues[0]


# --------------------------------------------------------------------------- #
# 3. 設定真的傳得到圖上
# --------------------------------------------------------------------------- #
def test_locking_the_scale_reaches_every_chart(dataset, tmp_path):
    """鎖定是這一輪唯一非做不可的外觀設定，所以它要**真的鎖到圖上**。"""
    out = tmp_path / "lock"
    run(dataset, out, look='{"lock":true,"lo":0,"hi":255}')
    hist = next(out.glob("*-histogram.svg")).read_text(encoding="utf-8")
    heat = next(out.glob("*-map.svg")).read_text(encoding="utf-8")
    assert ">250<" in hist or ">200<" in hist      # 鎖到 0–255 才有的刻度
    assert "locked" in heat                        # 色階鎖住要在圖上說


def test_an_unset_lock_leaves_every_chart_scaling_itself(dataset, tmp_path):
    """`lock` 沒開 ⇒ auto。

    F87 之前這是「上界沒有高過下界」那條**要用背的**約定；現在是一顆明著的
    開關（舊 recipe 由 `_migrate_chart_params_into_look` 翻過來）。
    """
    out = tmp_path / "auto"
    run(dataset, out)
    assert "locked" not in next(out.glob("*-map.svg")).read_text(encoding="utf-8")


def test_the_value_name_replaces_the_statistic_id_on_the_axis(dataset,
                                                              tmp_path):
    """`glv_mean` 在報告裡不是一句話，`Gray level` 才是。"""
    out = tmp_path / "named"
    run(dataset, out, look='{"value_name":"Gray level"}')
    prof = next(out.glob("*-profile.svg")).read_text(encoding="utf-8")
    assert "Gray level" in prof


def test_the_profile_axis_switches_what_it_plots_against(dataset, tmp_path):
    a, b = tmp_path / "ax", tmp_path / "ay"
    run(dataset, a, axis="x")
    run(dataset, b, axis="y")
    sx = next(a.glob("*-profile.svg")).read_text(encoding="utf-8")
    sy = next(b.glob("*-profile.svg")).read_text(encoding="utf-8")
    assert "centre X" in sx and "centre Y" in sy


def test_a_metric_nobody_measured_draws_nothing_rather_than_the_wrong_one(
        dataset, tmp_path):
    """打錯統計量名字 ⇒ **不要安靜換一個**（同 `metrics` 那一格的立場）。"""
    out = tmp_path / "bogus"
    bctx, _ = run(dataset, out, metric="glv_nope")
    assert list(out.glob("*.html")) == []
    assert any("each box" in w for w in bctx.warnings)


# --------------------------------------------------------------------------- #
# 4. 這張卡在 Output 段的身分
# --------------------------------------------------------------------------- #
def test_it_is_a_batch_card_that_writes_nothing_into_the_pipeline():
    card = get_step("output_uniformity")
    p = {"folder": "/tmp/x", "charts": "box"}
    assert card.resolve_reads(p) == []
    assert card.resolve_writes(p) == []
    assert card.resolve_features(p) == []


def test_its_help_points_at_the_other_card_for_the_other_question():
    """兩張卡在畫面上長得一模一樣，所以**help 那一句話就是它們的分界**。"""
    card = get_step("output_uniformity")
    assert "Write report" in card.help
    assert "each box" in card.help


# --------------------------------------------------------------------------- #
# F86：檔名、數字、索引頁、打錯的統計量
# --------------------------------------------------------------------------- #
def test_the_files_are_not_called_overlay(dataset, tmp_path):
    """**這幾張不是疊圖。**

    第一版借了 `overlay.overlay_filename()`，於是檔名長成
    `overlay_field-box.svg` —— 而我要的只有它「把 / : 換成底線」那一半。
    前綴是搭便車來的，意思是錯的。
    """
    out = tmp_path / "names"
    run(dataset, out)
    names = [p.name for p in out.iterdir()]
    assert names, "什麼都沒寫"
    assert not any(n.startswith("overlay_") for n in names), names


def test_a_defect_id_that_is_not_a_legal_filename_still_writes():
    """消毒那一半**要留著**：RSEM 的 id 是從檔名來的，一顆 id 裡有 `/` 或
    `:` 的 defect 會讓寫檔整個失敗，而症狀是「少了幾張圖」（鐵則 7 把例外
    吃掉了）。"""
    from d4t.core.export.overlay import safe_stem
    assert safe_stem("LOT/1:2") == "LOT_1_2"
    assert safe_stem("") == "unknown"


def test_the_page_carries_the_numbers_not_just_the_pictures(dataset, tmp_path):
    """那一頁本來就該是「一顆的答案」。

    在這之前它只有四張 SVG —— 看圖的人得另外開 CSV 才知道 CV% 是多少。
    """
    out = tmp_path / "numbers"
    run(dataset, out)
    page = next(out.glob("*.html")).read_text(encoding="utf-8")
    assert "<table class='unif'" in page, "頁面上沒有數字表"
    assert "CV" in page and "left" in page       # 散多開 ＋ 往哪邊斜
    assert "boxes" in page


def test_the_numbers_on_the_page_are_the_ones_in_the_csv(dataset, tmp_path):
    """**同一顆的 CV% 不准有兩個。**

    摘要表的數字是從那一顆的 features 拿的，不在畫圖那一側重算 —— 重算的
    那一份會漂，而 CSV 與報告頁上出現兩個 CV% 的那天，沒有人看得出哪一個
    是對的。
    """
    from d4t.core.export import uniformity_charts as uc
    out = tmp_path / "same"
    _bctx, rows = run(dataset, out)
    feats = rows[0]["features"]
    notes = []          # 直接問那一支，避免再跑一次 pipeline
    got = uc.summary_rows({"metric": "glv_mean",
                           "groups": [{"name": "cells", "values": [1.0, 2.0]}]},
                          feats)
    assert got[0]["cells"].get("cv_pct") == feats.get("glv_mean_cv_pct")
    assert notes == []


def test_one_defect_gets_no_index_page(dataset, tmp_path):
    """**一顆的時候不寫索引**：那一顆的頁面本來就是答案，多一個檔只是多一層
    要點進去的東西。"""
    out = tmp_path / "single"
    run(dataset, out, limit=1)
    assert not (out / "index.html").exists()
    assert len(list(out.glob("*.html"))) == 1


def test_several_defects_get_an_entry_page(dataset, tmp_path):
    """20 顆會寫出 20 個 HTML ＋ 80 個 SVG 躺在同一個資料夾裡 —— 沒有入口的話
    要一個一個點。"""
    out = tmp_path / "many"
    _bctx, rows = run(dataset, out)
    if len(rows) < 2:
        pytest.skip("這份合成資料只有一顆")
    index = out / "index.html"
    assert index.is_file()
    text = index.read_text(encoding="utf-8")
    for r in rows:
        assert str(r["defect_id"]) in text, "索引頁少了一顆"
    assert text.count("<a href=") == len(rows)
    assert "CV" in text, "索引頁上要有數字，不然挑不出該點哪一顆"


def test_a_statistic_nobody_measured_is_caught_on_the_canvas():
    """打成 `glv_mena` 的下場是四張圖全空、**沒有任何訊息**。

    那一格是自由文字，而 d4t 對「指名上游東西」的欄位向來有型別。它不是
    特徵名（是統計量 id），所以落在既有的 `stale-feature-ref` 之外 ——
    要有自己的一條。
    """
    from d4t.core.pipeline import validate
    r = recipe_for("/tmp/x")
    assert [i for i in validate(r, kind=KIND)] == []
    r.nodes["out"].params["metric"] = "glv_mena"
    bad = [i for i in validate(r, kind=KIND)
           if i.code == "unknown-chart-metric"]
    assert bad, "打錯的統計量沒有被講出來"
    assert "glv_mean" in bad[0].detail, "要說得出上游到底量了什麼"


def test_pooled_upstream_is_caught_on_the_canvas():
    """走 pooled 的話這張卡跑得完、資料夾出得來、裡面什麼都沒有。"""
    from d4t.core.pipeline import validate
    r = recipe_for("/tmp/x", glv={"across_boxes": "pooled"})
    got = [i for i in validate(r, kind=KIND)
           if i.code == "charts-need-each-box"]
    assert got, "pooled 沒有被講出來"
    assert "Odd box out" in got[0].detail, "要指名那顆鈕"


# --------------------------------------------------------------------------- #
# F87：外觀是**一格參數**，而且四張圖吃同一份
# --------------------------------------------------------------------------- #
def test_the_look_is_one_parameter_not_twenty_five(dataset, tmp_path):
    """卡片上只剩「寫什麼」那幾格 —— 長相全部在 `look` 裡。"""
    card = get_step("output_uniformity")
    names = [p.name for p in card.params]
    assert "look" in names
    for gone in ("value_name", "value_lo", "value_hi", "points", "bins",
                 "percent"):
        assert gone not in names, "%s 應該折進 look 了" % gone
    # ⚠ 上限從 8 變 9（F88 第二刀的 `spec`）。**它預設是收起來的**
    # （沒勾散佈圖就看不到），所以「面板有多長」實際上沒有變 —— 但這個上限
    # 存在的理由是「不要一格一格加回去」，所以每加一格都要在這裡動一次手。
    assert len(names) <= 9, "面板又長回去了：%s" % names


@pytest.mark.parametrize("kind", ["box", "histogram", "profile", "map"])
def test_every_chart_obeys_the_same_look(dataset, tmp_path, kind):
    """**四張圖要吃同一份設定。**

    「字級只對四張裡的兩張有效」是最難發現的那種不一致：使用者調了、三張變
    了、一張沒有，而畫面上沒有任何線索說為什麼。實測踩過 —— 盒鬚圖走的是
    `boxplot` 那一支、熱圖的標籤寫死 10px。
    """
    out = tmp_path / ("look_%s" % kind)
    run(dataset, out, charts=kind,
        look='{"tick_size":14,"tick_bold":true}')
    svg = next(out.glob("*-%s.svg" % kind)).read_text(encoding="utf-8")
    assert "14" in svg and "700" in svg, "這張圖沒有吃到字級／粗體"


def test_a_per_chart_title_only_touches_that_chart(dataset, tmp_path):
    """每張圖的標題與軸名是**它自己的**（四張圖的 X 是四件不同的事）。"""
    out = tmp_path / "titles"
    run(dataset, out, look='{"box.title":"EPI uniformity"}')
    assert "EPI uniformity" in next(out.glob("*-box.svg")).read_text("utf-8")
    assert "EPI uniformity" not in next(out.glob("*-map.svg")).read_text("utf-8")


def test_an_impossible_setting_is_refused_when_you_type_it(dataset, tmp_path):
    """擋在打字的當下（鐵則 4），而且**留著白話那句話**。"""
    from d4t.core.pipeline.step import ParamError
    card = get_step("output_uniformity")
    with pytest.raises(ParamError) as e:
        card.validate_params({"folder": "/tmp/x", "look": '{"tick_size":99}'})
    assert "outside" in str(e.value), str(e.value)


def test_an_old_recipe_keeps_its_locked_scale():
    """⚠ **舊的約定要翻成新的開關。**

    F87 之前「鎖住了嗎」是「上界高過下界」；現在是一顆 `lock`。翻錯的話一份
    本來鎖著的 recipe 會安靜地變成 auto —— 兩張圖擺在一起，一樣高的柱子其實
    不一樣高，而圖上沒有線索。
    """
    from d4t.core.pipeline import Recipe, chart_style
    raw = {
        "recipe_id": "old", "version": 3, "app_version": "0.1",
        "routes": {KIND: ["c"]}, "edges": [],
        "score": {"expr": "", "threshold": 0.0, "bins": {}},
        "nodes": {"c": {"step": "output_uniformity", "params": {
            "folder": "/tmp/x", "charts": "box", "value_lo": 10.0,
            "value_hi": 200.0, "bins": 40, "points": False,
            "value_name": "Gray level"}}}}
    r = Recipe.from_json_dict(raw)
    p = r.nodes["c"].params
    assert "value_lo" not in p and "bins" not in p, "舊的格子沒有收掉"
    st = chart_style.style_for(p["look"], "box")
    assert st["vlock"] == (10.0, 200.0), "鎖定沒有翻過來"
    assert st["bins"] == 40 and st["points"] is False
    assert st["value_name"] == "Gray level"
    # 跑第二次是 no-op（鐵則 9：round-trip 要是 identity）
    assert Recipe.from_json_dict(r.to_json_dict()).to_json_dict() == \
        r.to_json_dict()


def test_profile_along_only_asks_when_that_chart_is_ticked():
    """**答了也沒用的問題不要問**（推廣鐵則）。

    `Profile along` 只影響 position profile 那一張。第一版把它攤在那裡，
    而對只勾了盒鬚圖的人那是一格永遠不生效的設定 —— 使用者填了值、畫面上
    什麼都沒說。

    ⚠ `show_when` 是**顯示**規則不是驗證規則：藏起來的 ``axis`` 照樣有預設
    值，而那沒問題 —— 沒勾那張圖就不會有人用到它。
    """
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.step import param_visible

    spec = [p for p in get_step("output_uniformity").describe()["params"]
            if p["name"] == "axis"][0]
    rule = spec.get("show_when")
    assert rule, "沒有這條規則的話那一格永遠都在"
    assert param_visible(rule, {"charts": "box,histogram,profile,map"})
    assert param_visible(rule, {"charts": "profile"})
    assert not param_visible(rule, {"charts": "box,map"})
    assert not param_visible(rule, {"charts": ""})


# --------------------------------------------------------------------------- #
# 熱圖疊回影像上（F87 第五刀）
# --------------------------------------------------------------------------- #
def _heat_ctx(bright=True):
    """一張有梯度的影像 ＋ 6×5 格框，跑一次 GLV（`each box` ＋ report）。"""
    import numpy as np

    from d4t.core.algo.roi import MultiROISet
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    h = w = 420
    yy, xx = np.mgrid[0:h, 0:w]
    img = (100.0 + 18.0 * xx / w + 9.0 * yy / h).astype(np.float32)
    if bright:
        img[180:220, 250:290] += 26.0
    rois = MultiROISet()
    for j in range(5):
        for i in range(6):
            rois.add_roi(((20 + 66 * i) / w, (20 + 66 * j) / h,
                          46 / w, 46 / h), label="cells")
    ctx = Context(images={"test": img}, rois=rois)
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "across_boxes": "each box",
        "metrics": "glv_mean", "report": "cv_pct,slope_x,slope_y"})
    return ctx


_HEAT_PARAMS = {"folder": "/tmp/x", "metric": "glv_mean",
                "charts": "box,histogram,profile,map"}


def test_the_heat_overlay_is_the_same_tiles_as_the_written_chart():
    """**畫面上那一格的顏色 = 報表裡那一格的顏色。**

    這是這一刀唯一真正重要的不變量：兩份各算一次的話，它們會在某一天分岔，
    而那一天兩張都畫得出來（這個 repo 最貴的那種 bug）。所以問的是
    `overlay_heat` 交出來的色，跟 `heat_tiles` 直接算的**逐項相同**。
    """
    from d4t.core.export import uniformity_charts as uc
    from d4t.core.pipeline import get_step

    ctx = _heat_ctx()
    card = get_step("output_uniformity")
    cells, colours, legend = card.overlay_heat(ctx, _HEAT_PARAMS, "test")
    assert len(cells) == 30 and len(colours) == 30

    series = uc.chart_series(ctx.meta["glv_hist"], "glv_mean")
    p = card.validate_params(_HEAT_PARAMS)
    st = card()._style_for(uc.CHART_MAP, p, "glv_mean")
    want_cells, want_cols, (lo, hi) = uc.heat_tiles(series, st,
                                                    bounds=(420, 420))
    assert colours == want_cols
    assert legend[0] == lo and legend[1] == hi
    # 座標是正規化的（同 `set_overlay` / `set_marks` 的契約）
    for nx, ny, nw, nh in cells:
        assert 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0
        assert 0.0 < nw <= 1.0 and 0.0 < nh <= 1.0
    got = [(c[0] * 420, c[1] * 420, (c[0] + c[2]) * 420, (c[1] + c[3]) * 420)
           for c in cells]
    for a, b in zip(got, want_cells):
        assert all(abs(x - y) < 1e-6 for x, y in zip(a, b))


def test_the_heat_overlay_covers_every_region_not_just_the_first():
    """一起鋪 —— 疊圖跟那張 SVG 走同一條路，所以這一條跟著成立。"""
    import numpy as np

    from d4t.core.algo.roi import MultiROISet
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    h = w = 300
    img = np.full((h, w), 120.0, dtype=np.float32)
    img[:, 150:] += 30.0
    rois = MultiROISet()
    for i in range(4):
        rois.add_roi(((10 + 30 * i) / w, 0.1, 20 / w, 20 / h), label="epi")
    for i in range(4):
        rois.add_roi(((160 + 30 * i) / w, 0.1, 20 / w, 20 / h), label="mg")
    ctx = Context(images={"test": img}, rois=rois)
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "epi,mg", "across_boxes": "each box",
        "metrics": "glv_mean", "report": "cv_pct"})
    cells, colours, _legend = get_step("output_uniformity").overlay_heat(
        ctx, {"folder": "/tmp/x", "metric": "glv_mean", "charts": "map"},
        "test")
    assert len(cells) == 8, "兩個區域的框都要鋪上去"
    assert len(set(colours)) > 1, "色階跨區域共用 —— 兩邊不該同色"


def test_nothing_is_painted_when_the_heat_map_is_not_ticked():
    """畫面上的東西要跟「會寫出去什麼」對得起來 —— 沒勾就不鋪。"""
    from d4t.core.pipeline import get_step

    ctx = _heat_ctx()
    got = get_step("output_uniformity").overlay_heat(
        ctx, {"folder": "/tmp/x", "metric": "glv_mean",
              "charts": "box,histogram"}, "test")
    assert got == ([], [], None)


def test_nothing_is_painted_for_a_stream_this_card_did_not_measure():
    """量在別張影像上的結果不准塗在你正在看的這一張上（同 `overlay_marks`）。"""
    from d4t.core.pipeline import get_step

    ctx = _heat_ctx()
    for note in ctx.meta["glv_hist"]:
        note["stream"] = "test"
    cells, _c, _l = get_step("output_uniformity").overlay_heat(
        ctx, _HEAT_PARAMS, "ref")
    assert cells == []


def test_a_context_with_no_image_paints_nothing():
    """正規化要影像尺寸 —— 拿不到就整組不畫（錯位的顏色指向錯的地方）。"""
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

    ctx = _heat_ctx()
    bare = Context(images={})
    bare.meta["glv_hist"] = ctx.meta["glv_hist"]
    assert get_step("output_uniformity").overlay_heat(
        bare, _HEAT_PARAMS, "") == ([], [], None)


def test_every_card_can_be_asked_for_heat_without_blowing_up():
    """`Step.overlay_heat` 的預設要對**每一張**卡成立 —— 加一張新卡不必動 UI。"""
    from d4t.core.pipeline import list_steps
    from d4t.core.pipeline.context import Context

    ctx = Context(images={})
    for card in list_steps():
        cells, colours, legend = card.overlay_heat(ctx, {}, "")
        assert list(cells) == [] or len(cells) == len(colours)
        assert legend is None or len(tuple(legend)) == 3


# --------------------------------------------------------------------------- #
# 一列一格框的表（F88 第一刀）
# --------------------------------------------------------------------------- #
def test_the_card_can_write_one_row_per_box(tmp_path):
    """`defects.csv` 是**一顆 defect 一列**，看不到一張影像裡的那些格。

    計畫書 `docs/history/plans/F88-graph-builder.md` §2：長表就算之後不做 graph
    builder 也值得，因為這張 CSV 現在完全沒有。
    """
    from d4t.core.pipeline import get_step

    card = get_step("output_uniformity")
    p = card.validate_params({"folder": str(tmp_path), "boxes_csv": True})
    names = [f["name"] for f in card.planned_files(p)]
    assert card.TABLE_NAME in names, "乾跑就要講得出它會寫這一份"
    off = card.validate_params({"folder": str(tmp_path), "boxes_csv": False})
    assert card.TABLE_NAME not in [f["name"] for f in card.planned_files(off)]


def test_the_box_table_says_which_defect_each_row_came_from():
    """20 顆的框混在一起，而沒有 `defect_id` 那一欄的話那張表回答不了任何
    問題。"""
    from d4t.core.export import chart_frame as cf
    from d4t.core.pipeline import get_step

    card = get_step("output_uniformity")
    rows = [{"region": "epi", "box": 0, "x": 1.0, "y": 2.0,
             card.TABLE_ID: "D-1"}]
    text = cf.Frame([card.TABLE_ID, "region", "box", "x", "y"], rows).to_csv()
    assert text.split("\n")[0].startswith(card.TABLE_ID)
    assert "D-1" in text
