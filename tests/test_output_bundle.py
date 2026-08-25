# 報表 bundle：一個資料夾裝完一整批（F29 C，2026-08-25）。
"""使用者：「我是想 output 報表（包含很多顆 >6000 的把每一張圖分數都算出來
有 overlay 等等）但你說 html 這樣會很大 → 有替代方案嗎」。

有：**圖擺在報表旁邊，不是嵌在裡面**。實測一張整版的 overlay panel
PNG 70 KB、JPEG q75 12.6 KB；6000 顆嵌進 HTML 是 566 MB（PNG）／
約 76 MB（JPEG base64），而純文字的報表約 3 MB。

所以這一份鎖住四件事：

1. **四個東西都在**，而且報表裡的 `<img src>` 真的指得到那些檔案；
2. **報表列出每一顆，圖才有上限** —— 一份少了一半的報表跟完整的長得一樣；
3. **報表本身不含圖片資料**（有大小回歸盯著）；
4. **`recipe.json` 在** —— 沒有它，半年後沒人重現得出這份報表。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import (  # noqa: E402
    run_batch, run_batch_steps,
)
from d4t.core.pipeline.recipe import (  # noqa: E402
    Recipe, RecipeNode, ScoreSpec,
)

KIND = "ebi_patch"


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("bundle")), n=6, seed=5)


@pytest.fixture(scope="module")
def dataset(lot):
    return load_dataset(lot["klarf"])


def recipe_for(folder, **over):
    params = {"folder": str(folder)}
    params.update(over)
    return Recipe(
        recipe_id="bundle_demo", routes={KIND: ["load", "glv", "out"]},
        nodes={
            "load": RecipeNode("load", "load_patch", {}),
            "glv": RecipeNode("glv", "glv_stats",
                              {"source": "test", "metrics": "glv_max"}),
            "out": RecipeNode("out", "output_bundle", params),
        },
        score=ScoreSpec(expr="glv_max", threshold=1.0,
                        bins={"below": 0, "above": 1}))


def run(dataset, folder, **over):
    r = recipe_for(folder, **over)
    rows = run_batch(r, dataset, workers=1)
    bctx = run_batch_steps(r, dataset, rows)
    assert not bctx.errors, bctx.errors
    return bctx, rows


# --------------------------------------------------------------------------- #
# 1. 四個東西都在，而且連得起來
# --------------------------------------------------------------------------- #
def test_the_folder_has_the_four_things(dataset, tmp_path):
    out = tmp_path / "bundle"
    bctx, rows = run(dataset, out)
    assert (out / "report.html").is_file()
    assert (out / "defects.csv").is_file()
    assert (out / "recipe.json").is_file()
    assert (out / "images").is_dir()
    assert len(list((out / "images").glob("*.jpg"))) == len(rows)
    assert str(out) in bctx.outputs


def _tree_recipe_for(folder, **over):
    """同一份 pipeline，但**用判定樹分類、沒有分數表達式**（F30）。

    那是判定樹最常見的樣子，而它以前會讓每一顆拿到一個假的 ``score = 0``。
    """
    params = {"folder": str(folder)}
    params.update(over)
    r = recipe_for(folder, **over)
    raw = r.to_json_dict()
    raw["nodes"]["out"]["params"] = params
    raw["score"] = {"expr": "", "threshold": 1.0,
                    "bins": {"below": 0, "above": 1}}
    raw["decide"] = {"let": [],
                     "tree": {"when": "glv_max > 200",
                              "yes": {"bin": 2, "label": "bright"},
                              "no": {"bin": 1, "label": "plain"}}}
    return Recipe.from_json_dict(raw)


def test_a_tree_without_a_score_says_the_order_is_not_a_ranking(dataset,
                                                                tmp_path):
    """**這一條是那個 bug 的形狀。**

    判定樹是一個分類器 —— 沒有分數表達式的時候，「照分數取最差的 N 顆」
    無事可排，於是拿到的是**檔案順序**的前 N 顆。圖的張數、報表的樣子、
    資料夾的結構全部一模一樣，所以那件事在產出的當下完全看不出來。
    """
    r = _tree_recipe_for(tmp_path / "bundle", limit=2)
    rows = run_batch(r, dataset, workers=1)
    assert all(row.get("score") is None for row in rows)     # 沒有假的 0
    assert all("score" not in (row.get("features") or {}) for row in rows)
    bctx = run_batch_steps(r, dataset, rows)
    said = " ".join(bctx.warnings)
    assert "no defect has a score" in said
    assert "not the worst" in said


def test_ranking_by_a_measured_number_makes_the_warning_go_away(dataset,
                                                                tmp_path):
    """講出來的前提是它**只在真的排不出來時**講 —— 否則它是一句雜訊。"""
    r = _tree_recipe_for(tmp_path / "bundle2", limit=2, rank_by="glv_max")
    rows = run_batch(r, dataset, workers=1)
    bctx = run_batch_steps(r, dataset, rows)
    assert "nothing to sort on" not in " ".join(bctx.warnings)
    assert "no defect has a score" not in " ".join(bctx.warnings)


def test_the_pictures_are_the_top_ones_by_the_chosen_number(dataset, tmp_path):
    """排序真的照那個數字走 —— 否則上面那條只證明了「沒有警告」。"""
    out = tmp_path / "bundle3"
    r = _tree_recipe_for(out, limit=2, rank_by="glv_max")
    rows = run_batch(r, dataset, workers=1)
    run_batch_steps(r, dataset, rows)
    want = sorted(rows, key=lambda x: -float(x["features"]["glv_max"]))[:2]
    got = {p.stem.replace("overlay_", "")
           for p in (out / "images").glob("*.jpg")}
    assert got == {str(x["defect_id"]) for x in want}


def test_every_img_src_points_at_a_real_file(dataset, tmp_path):
    """**這一條是「圖擺在旁邊」那個決定的驗收。**

    相對路徑寫錯的話報表照樣開得起來 —— 只是每一格都是破圖，而那件事在
    產出的當下完全看不出來。
    """
    out = tmp_path / "bundle"
    run(dataset, out)
    text = (out / "report.html").read_text(encoding="utf-8")
    rels = set(re.findall(r'data-img="([^"]+)"', text))
    assert rels, "報表裡一個可以點的列都沒有"
    for rel in rels:
        # ⚠ **先確認它是相對的。** `Path(out) / "/abs/x.jpg"` 在 pathlib 裡
        # 會直接變成那個絕對路徑，所以只檢查 `is_file()` 的話，一個絕對路徑
        # 也會過 —— 而那正是「把資料夾寄給別人」的那一刻會破的東西。
        assert not os.path.isabs(rel) and ":" not in rel, rel
        assert not rel.startswith(("/", "\\")), rel
        assert (out / rel).is_file(), rel


def test_the_report_names_the_recipe_that_made_it(dataset, tmp_path):
    """一疊數字沒有配方，等於一句「我們那時候量到這樣」。"""
    out = tmp_path / "bundle"
    run(dataset, out)
    doc = json.loads((out / "recipe.json").read_text(encoding="utf-8"))
    assert doc["recipe_id"] == "bundle_demo"
    assert doc["nodes"]["glv"]["step"] == "glv_stats"


# --------------------------------------------------------------------------- #
# 2. 每一顆都在報表上；有上限的是圖
# --------------------------------------------------------------------------- #
def test_the_limit_caps_the_pictures_not_the_rows(dataset, tmp_path):
    out = tmp_path / "bundle"
    _bctx, rows = run(dataset, out, limit=2)
    assert len(list((out / "images").glob("*.jpg"))) == 2
    text = (out / "report.html").read_text(encoding="utf-8")
    assert text.count("<tr") == len(rows) + 1        # 每一顆一列 + 表頭


def test_zero_means_every_defect(dataset, tmp_path):
    """使用者定調 2026-08-25：「參數化，**預設全部**」。"""
    from d4t.core.pipeline.step import REGISTRY
    spec = {p.name: p for p in REGISTRY["output_bundle"].params}["limit"]
    assert spec.default == 0

    out = tmp_path / "bundle"
    _bctx, rows = run(dataset, out, limit=0)
    assert len(list((out / "images").glob("*.jpg"))) == len(rows)


def test_the_pictures_are_the_worst_ones_first(dataset, tmp_path):
    """截斷的時候留下的是**分數最高的那幾顆**，不是檔案順序上的前幾顆。

    照 `rows` 的順序取的話，畫面上看不出差別（都是 N 張圖）。
    """
    out = tmp_path / "bundle"
    _bctx, rows = run(dataset, out, limit=2)
    best = sorted((r for r in rows if r.get("score") is not None),
                  key=lambda r: -float(r["score"]))[:2]
    kept = {p.stem.replace("overlay_", "")
            for p in (out / "images").glob("*.jpg")}
    assert kept == {str(r["defect_id"]) for r in best}


# --------------------------------------------------------------------------- #
# 3. 報表本身不含圖片資料（大小回歸）
# --------------------------------------------------------------------------- #
def test_the_report_stays_text_sized(dataset, tmp_path):
    """**6000 顆的那份是這一條在守的。**

    嵌進去的話 24 顆就已經是幾 MB，而「報表打不開」是一個沒有人會回報的 bug
    （使用者只會不用它）。
    """
    out = tmp_path / "bundle"
    _bctx, rows = run(dataset, out)
    size = (out / "report.html").stat().st_size
    assert size < 200_000, size
    text = (out / "report.html").read_text(encoding="utf-8")
    assert "base64" not in text
    # 圖真的有寫出來（否則上面那條會因為「根本沒有圖」而永遠是綠的）
    assert sum(p.stat().st_size for p in (out / "images").glob("*.jpg")) > size


def test_jpeg_is_much_smaller_than_png(dataset, tmp_path):
    """換成 JPEG 是這個功能可行的前提，所以那個差要有人盯著。"""
    import numpy as np
    from d4t.core.export import overlay

    rng = np.random.default_rng(0)
    base = np.clip(rng.normal(120, 12, (256, 256)), 0, 255).astype(np.uint8)
    base[80:120, 60:110] = 220
    panel = overlay.render_overlay({"test": base, "diff": base // 2}, {},
                                   montage=True)
    png = Path(overlay.write_png(panel, str(tmp_path / "a.png")))
    jpg = Path(overlay.write_jpeg(panel, str(tmp_path / "a.jpg")))
    assert jpg.stat().st_size * 3 < png.stat().st_size


# --------------------------------------------------------------------------- #
# 4. 第二趟吃快取（`limit=0` 的前提）
# --------------------------------------------------------------------------- #
def test_the_second_pass_hits_the_image_cache(dataset, tmp_path):
    """**6000 顆的那份要跑得完，靠的就是這個。**

    出圖那幾張卡要**重跑一次 pipeline** 才拿得到像素（結果表裡只有數字），
    而那一趟的影像段跟剛才那一批是逐位元組相同的。快取本來就在
    （`run_batch` 用的那一份），只是 `run_batch_steps` 沒有這個參數、
    `output_*` 叫的是 `run_defect`、CLI 手上有 `--cache` 也沒有傳。

    三個地方接起來之後，第二趟**每一顆都命中**，只跑算法段。
    """
    cache_dir = tmp_path / "cache"
    out = tmp_path / "bundle"
    r = recipe_for(out)
    rows = run_batch(r, dataset, workers=1, cache_dir=str(cache_dir))
    bctx = run_batch_steps(r, dataset, rows, cache_dir=str(cache_dir))
    assert not bctx.errors, bctx.errors
    assert bctx.cache is not None
    assert bctx.cache.hits == len(rows), (bctx.cache.hits, bctx.cache.misses)
    assert bctx.cache.misses == 0


def test_without_a_cache_it_still_writes_everything(dataset, tmp_path):
    """沒有快取就全程重算 —— **結果一模一樣**，只是慢。

    少了這一條，`cache_dir=None` 那條路壞掉的症狀是「報表少了圖」。
    """
    out = tmp_path / "bundle"
    _bctx, rows = run(dataset, out)          # 這個 helper 不給 cache_dir
    assert len(list((out / "images").glob("*.jpg"))) == len(rows)


def test_the_cached_pass_produces_the_same_pictures(dataset, tmp_path):
    """快取那條路與全程重算那條路**寫出來的位元組要一樣**。

    `run_defect_cached` 的合約是「結果與 `run_defect` 位元級一致」，而疊圖是
    從影像畫出來的 —— 這一條把那個合約延伸到圖上。差別會很安靜：
    一份用快取跑的報表跟一份沒用的長得一模一樣。
    """
    cache_dir = tmp_path / "cache"
    cold, warm = tmp_path / "cold", tmp_path / "warm"
    r_cold, r_warm = recipe_for(cold), recipe_for(warm)
    rows = run_batch(r_cold, dataset, workers=1, cache_dir=str(cache_dir))
    run_batch_steps(r_cold, dataset, rows)                       # 無快取
    run_batch_steps(r_warm, dataset, rows, cache_dir=str(cache_dir))
    a = sorted((cold / "images").glob("*.jpg"))
    b = sorted((warm / "images").glob("*.jpg"))
    assert [p.name for p in a] == [p.name for p in b] and a
    for x, y in zip(a, b):
        assert x.read_bytes() == y.read_bytes(), x.name


# --------------------------------------------------------------------------- #
# 5. 版面：判定 → 哪幾顆 → 憑什麼（同 Results 三段）
# --------------------------------------------------------------------------- #
def test_the_report_opens_with_what_it_decided(dataset, tmp_path):
    """使用者跑完一整批之後問的是三個依序的問題，而報表要照那個順序排。

    以前這張卡（`output_html`）第一眼就是一張 6000 列的表 —— 那是從細節開始。
    """
    out = tmp_path / "bundle"
    _bctx, rows = run(dataset, out)
    text = (out / "report.html").read_text(encoding="utf-8")
    assert text.index("What it decided") < text.index("Which ones")
    # 每一類一條橫條，而**顆數加起來就是這一批**（判定那一段不能少講一類）。
    counts = [int(n) for n in re.findall(r"<div class='vn'>(\d+)</div>", text)]
    assert counts and sum(counts) == len(rows)


def test_the_report_and_the_panel_count_the_same_thing(dataset, tmp_path):
    """報表的「每一類幾顆」跟畫面上那一條是**同一支函式**算的（F29 C0）。

    抄第二份出來的話，兩邊的數字會在某一次改動之後悄悄分開 —— 而那時候
    沒有人知道該相信哪一個。
    """
    from d4t.core.pipeline import decide_tree

    out = tmp_path / "bundle"
    _bctx, rows = run(dataset, out)
    text = (out / "report.html").read_text(encoding="utf-8")
    counts = [int(n) for n in re.findall(r"<div class='vn'>(\d+)</div>", text)]
    assert counts == [int(e["count"])
                      for e in decide_tree.verdict_rows(None, rows)]


def test_a_defect_that_did_not_run_is_its_own_row(dataset, tmp_path):
    """「有卡片出錯」跟「跑完了但判不出 bin」是兩種事故，不是同一列。"""
    from d4t.core.export import html

    rows = [{"defect_id": "1", "ok": True, "error": "", "score": 1.0,
             "bin": 1, "features": {}},
            {"defect_id": "2", "ok": False, "error": "boom", "score": None,
             "bin": None, "features": {}}]
    text = html.build_report(rows, "t", [])
    assert "a card errored" in text and "boom" in text


# --------------------------------------------------------------------------- #
# 6. 壞輸入
# --------------------------------------------------------------------------- #
def test_pointing_at_a_file_says_so(dataset, tmp_path):
    """貼了路徑忘了改成資料夾 —— 症狀不該是 `NotADirectoryError`。"""
    f = tmp_path / "not_a_folder.txt"
    f.write_text("x", encoding="utf-8")
    r = recipe_for(f)
    rows = run_batch(r, dataset, workers=1)
    bctx = run_batch_steps(r, dataset, rows)
    assert bctx.errors
    assert "is a file, not a folder" in " ".join(bctx.errors.values())


def test_an_empty_path_is_a_configuration_issue_not_a_crash():
    from d4t.core.pipeline.step import REGISTRY
    says = REGISTRY["output_bundle"].configuration_issues({"folder": ""})
    assert says and "Write to" in says[0]
    assert REGISTRY["output_bundle"].configuration_issues(
        {"folder": "/tmp/x"}) == []


# ---------------------------------------------------------------------------
# 逐框比較的框上報表（F31 T2）—— 兩張出圖卡逐字同一組設定
# ---------------------------------------------------------------------------
def test_both_image_cards_offer_the_same_box_settings_word_for_word():
    from d4t.core.pipeline.step import REGISTRY

    specs = {}
    for key in ("output_image", "output_bundle"):
        by_name = {p.name: p for p in REGISTRY[key].params}
        specs[key] = tuple(
            (by_name[n].type, by_name[n].default, by_name[n].label,
             tuple(by_name[n].choices or ()), by_name[n].help,
             by_name[n].advanced)
            for n in ("draw_boxes", "draw_boxes_cap"))
    assert specs["output_image"] == specs["output_bundle"]
    # 預設 all（框少的時候最有用），上限是使用者的一格不是魔術數字
    assert specs["output_image"][0][1] == "all"


def test_the_roi_kwargs_helper_reads_the_glv_note():
    """`_roi_overlay_kwargs`（兩張卡共用的那六行）吃 each box 跑完的 ctx。"""
    import numpy as np

    from d4t.core.export import overlay
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context
    from d4t.core.steps.output import _roi_overlay_kwargs

    img = np.full((100, 100), 100, np.float32)
    img[42:58, 42:58] = 170.0
    ctx = Context(images={"test": img})
    n = 5
    ctx.set_roi_boxes("cells", [
        (c / n + 0.02, r / n + 0.02, 1.0 / n - 0.04, 1.0 / n - 0.04)
        for r in range(n) for c in range(n)])
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box"})

    kw, degraded = _roi_overlay_kwargs(
        ctx, {"draw_boxes": "all", "draw_boxes_cap": 300})
    assert len(kw["roi_boxes"]) == 25 and kw["roi_winner"] == 12
    assert not degraded

    kw, degraded = _roi_overlay_kwargs(
        ctx, {"draw_boxes": "all", "draw_boxes_cap": 5})
    assert len(kw["roi_boxes"]) == 5 and degraded
    assert kw["roi_boxes"][kw["roi_winner"]] == ctx.roi_norm_rects("cells")[12]

    # 沒有 ctx（rerun 失敗）→ 不畫、不炸
    kw, degraded = _roi_overlay_kwargs(
        None, {"draw_boxes": "all", "draw_boxes_cap": 300})
    assert kw == {"roi_boxes": [], "roi_winner": -1} and not degraded

    # 像素標記（T3）：k > 0 才帶，數字逐字是 meta 的 worst 那兩個
    kw, _ = _roi_overlay_kwargs(
        ctx, {"draw_boxes": "all", "draw_boxes_cap": 300,
              "mark_pixels_k": 3.0})
    worst = [n for n in ctx.meta["glv_hist"] if n.get("worst")][0]["worst"]
    odd = kw["odd_pixels"]
    assert odd["baseline"] == worst["baseline"]
    assert odd["spread"] == worst["spread"]
    assert odd["box"] == ctx.roi_norm_rects("cells")[12]
    assert odd["src"] is ctx.images["test"]
    kw, _ = _roi_overlay_kwargs(
        ctx, {"draw_boxes": "all", "draw_boxes_cap": 300,
              "mark_pixels_k": 0.0})
    assert "odd_pixels" not in kw

    # 染色門檻是同一個 k、比的是贏家自己的分數：把 k 調到比 score 高，
    # 同一顆、同一份 meta → 不帶（證明門檻不是寫死的 3）。
    assert worst["score"] >= 3.0
    kw, _ = _roi_overlay_kwargs(
        ctx, {"draw_boxes": "all", "draw_boxes_cap": 300,
              "mark_pixels_k": worst["score"] + 1.0})
    assert "odd_pixels" not in kw


def test_a_quiet_image_gets_no_tint():
    """正常顆（worst_score < k）整張安靜 —— 實測 overlay_10 的那個坑：
    像素判準的分母是框間統計量的散布（常踩 1 灰階地板），遠小於像素雜訊，
    沒有這道門的話**每一顆**的贏家框都整格染色。"""
    import numpy as np

    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context
    from d4t.core.steps.output import _roi_overlay_kwargs

    rng = np.random.default_rng(7)
    img = (100.0 + rng.normal(0, 5.0, (100, 100))).astype(np.float32)
    ctx = Context(images={"test": img})
    n = 5
    ctx.set_roi_boxes("cells", [
        (c / n + 0.02, r / n + 0.02, 1.0 / n - 0.04, 1.0 / n - 0.04)
        for r in range(n) for c in range(n)])
    get_step("glv_stats")().run(ctx, {
        "source": "test", "roi": "cells", "metrics": "glv_median",
        "across_boxes": "each box"})

    worst = [m for m in ctx.meta["glv_hist"] if m.get("worst")][0]["worst"]
    assert worst["score"] < 3.0          # 純雜訊：沒有一格真的異常
    kw, _ = _roi_overlay_kwargs(
        ctx, {"draw_boxes": "all", "draw_boxes_cap": 300,
              "mark_pixels_k": 3.0})
    assert "odd_pixels" not in kw        # 安靜的圖保持安靜
    assert kw["roi_winner"] >= 0         # 框照畫 —— 只有染色被門住
