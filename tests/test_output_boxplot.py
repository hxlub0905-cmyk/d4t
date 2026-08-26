# -*- coding: utf-8 -*-
"""F36：整批的分布 → 一張 box plot（**一個盒子 = 一片葉子**）。

使用者要的是「report 然後**還有一張** box plot」—— 兩個交付物，回答兩個問題：
報表是「這一顆長什麼樣」，這張圖是「**這一批**散得多開，四類分不分得開」。

鎖在這裡的四件事：

1. **盒子是葉子不是 bin**（兩片葉子共用一個 bin 是合法的），順序與顏色跟畫布
   上的樹一樣；
2. **算不出來的不畫**，而且要**說出來** —— 一張每一格都寫著 no data 的圖比
   沒有那張圖更糟（推廣鐵則）；
3. `Numbers to plot` 留空 = **判定問過的那幾個**（不是全部的特徵，也不是一份
   寫死的清單 —— 寫死的那一份總有一天跟樹漂掉）；
4. NaN 不會把整組統計毒掉（`F19`：算不出來的那一格本來就不寫，而混進來的
   NaN 會讓中位數變成 NaN）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.export import boxplot                               # noqa: E402
from d4t.core.pipeline import decide_tree                         # noqa: E402
from d4t.core.pipeline.context import BatchContext                # noqa: E402
from d4t.core.pipeline.recipe import (                            # noqa: E402
    DecideSpec, Let, Recipe, RecipeNode, ScoreSpec, TreeLeaf, TreeStep,
)
from d4t.core.pipeline.step import REGISTRY                       # noqa: E402

#: F38：box plot 不再是自己一張卡，是 `output_report` 上的一個勾。
CARD = "output_report"
TICK = "boxplot"


# --------------------------------------------------------------------------- #
# 1. 盒鬚圖的那幾個數字
# --------------------------------------------------------------------------- #
def test_the_whiskers_stop_at_real_data_not_at_the_computed_fence():
    """鬚的端點是**落在 1.5×IQR 之內的真實資料點**。

    畫到 ``q1 − 1.5·IQR`` 的話，鬚會伸進一段根本沒有資料的地方 —— 而讀圖的人
    會以為那裡有東西。
    """
    st = boxplot.box_stats([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 100])
    assert st["hi"] == 19.0, "100 是離群點，鬚不該跟著它跑"
    assert st["lo"] == 10.0
    assert 100.0 in st["outliers"]
    assert st["vmax"] == 100.0, "但它仍然要在圖上（vmax 決定尺度）"


def test_nan_does_not_poison_the_whole_box():
    """一顆量不到就是一顆量不到 —— 不該讓整組統計變成 NaN。"""
    st = boxplot.box_stats([1.0, 2.0, float("nan"), 3.0, float("inf")])
    assert st["n"] == 3
    assert st["med"] == 2.0


def test_nothing_measurable_is_none_not_an_empty_box():
    """**「這一類沒有這個數字」跟「這一類是空的」是兩件事。**

    回 0 或一個高度為零的盒子的話，圖上讀起來是「量了，而且全部都是 0」。
    """
    assert boxplot.box_stats([]) is None
    assert boxplot.box_stats([float("nan"), float("nan")]) is None


def test_every_value_the_same_still_draws():
    """整組一模一樣（IQR = 0）不能把 SVG 弄壞 —— 那是很常見的一批。"""
    svg = boxplot.build_boxplot_svg(
        [{"name": "flat", "values": [7.0] * 20, "colour": "#123456"}])
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "n=20" in svg


def test_a_class_with_no_data_says_so_on_the_chart():
    """有盒子的那幾類照畫，沒有的那一類寫 ``no data``。"""
    svg = boxplot.build_boxplot_svg([
        {"name": "has", "values": [1, 2, 3], "colour": "#111111"},
        {"name": "none", "values": [], "colour": "#222222"},
    ])
    assert "no data" in svg
    assert "has" in svg and "none" in svg


def test_the_svg_escapes_the_names_people_type():
    """葉子的名字是使用者打的字 —— 它會進 SVG。"""
    svg = boxplot.build_boxplot_svg(
        [{"name": "a<b & c", "values": [1, 2, 3]}])
    assert "a&lt;b &amp; c" in svg
    assert "<b &" not in svg


# --------------------------------------------------------------------------- #
# 2. 判定問過哪幾個數字
# --------------------------------------------------------------------------- #
def _decide():
    return DecideSpec(
        let=[Let(name="snr_min", expr="4"),
             Let(name="borrowed", expr="raw_thing", fill="0")],
        rules=[],
        tree=TreeStep(
            when="focus_lapvar >= 150",
            yes=TreeStep(when="cmp_snr_mean_outlier > snr_min",
                         yes=TreeLeaf(bin=1, label="strong"),
                         no=TreeLeaf(bin=3, label="no signal")),
            no=TreeLeaf(bin=99, label="garbage"),
        ),
        score="",
    )


def test_features_used_skips_the_numbers_the_decision_made_up():
    """``let`` 的名字不算 —— 把一個常數畫成盒子只會得到一條平線。

    但它們**算式裡用到的**要算：一份全部靠 working number 判定的 recipe 不該
    答「什麼都沒問」。
    """
    got = decide_tree.features_used(_decide())
    assert "snr_min" not in got and "borrowed" not in got
    assert "focus_lapvar" in got and "cmp_snr_mean_outlier" in got
    assert "raw_thing" in got, "working number 借來的那個數字才是量出來的"


def test_features_used_follows_the_tree_from_the_top():
    """順序＝畫布上由上往下 —— 三個地方講同一件事，順序也該一樣。"""
    got = decide_tree.features_used(_decide())
    assert got.index("focus_lapvar") < got.index("cmp_snr_mean_outlier")


# --------------------------------------------------------------------------- #
# 3. 卡片
# --------------------------------------------------------------------------- #
def _rows():
    """三類各五顆，數字刻意分得開（分不開的話這支測試證不了東西）。"""
    out = []
    for i in range(15):
        cls = i % 3
        out.append({
            "defect_id": "D%02d" % i, "ok": True,
            "features": {
                "focus_lapvar": 60.0 + i if cls == 2 else 300.0 + i,
                "cmp_snr_mean_outlier": (9.0 + i * 0.1) if cls == 0
                else (1.0 + i * 0.1),
            },
        })
    return out


def _recipe(folder, **over):
    params = {"folder": str(folder), "contents": TICK,
              "plot_features": "", "title": ""}
    params.update(over)
    return Recipe(
        recipe_id="plot_demo",
        routes={"ebi_patch": ["plot"]},
        nodes={"plot": RecipeNode("plot", CARD, params)},
        score=ScoreSpec(expr="", threshold=0.5, bins={}),
        decide=_decide(),
    )


def _run(tmp_path, rows=None, **over):
    path = tmp_path / "out" / "spread.html"
    recipe = _recipe(tmp_path / "out", **over)
    rows = list(rows if rows is not None else _rows())
    # 判定真的跑一遍 —— bin 是 `verdict_rows` 分盒子的依據。
    # ⚠ **working number 要先算進 features**，跟引擎一樣：少了它們，
    # `cmp_snr_mean_outlier > snr_min` 這一題會因為「問不到 snr_min」答「否」，
    # 於是每一顆都掉進同一片葉子 —— 而測試看起來只是「分類不如預期」。
    for r in rows:
        for lt in recipe.decide.let:
            try:
                r["features"][lt.name] = float(lt.expr)
            except (TypeError, ValueError):
                pass
        leaf, _p, _m = decide_tree.walk(recipe.decide.tree, r["features"])
        r["bin"] = leaf.bin
    bctx = BatchContext(rows=rows, dataset=None, recipe=recipe,
                        kind="ebi_patch")
    REGISTRY[CARD]().run_batch(bctx, recipe.nodes["plot"].params)
    return path, bctx


def test_one_box_per_leaf_named_the_way_the_user_named_it(tmp_path):
    """盒子上的字就是他在樹上打的那一句。"""
    path, bctx = _run(tmp_path)
    page = path.read_text(encoding="utf-8")
    assert not bctx.errors
    for name in ("strong", "no signal", "garbage"):
        assert name in page
    # F38：這張卡回報的是**資料夾**（它寫得出好幾樣），圖在那個資料夾裡。
    assert str(path.parent) in bctx.outputs
    assert path.is_file()


def test_an_empty_features_box_plots_what_the_decision_asked_about(tmp_path):
    """留空 ≠ 什麼都不畫，也 ≠ 畫全部 —— 畫**判定問過的**那幾個。"""
    path, _ = _run(tmp_path)
    page = path.read_text(encoding="utf-8")
    assert "focus_lapvar" in page
    assert "cmp_snr_mean_outlier" in page
    assert "snr_min" not in page, "常數不該有一張圖"


def test_a_misspelt_feature_is_said_out_loud_not_drawn_empty(tmp_path):
    """打錯名字 → **不畫那張圖**，而且警告要講得出下一步。

    畫一張每一格都是 no data 的圖的話，使用者會以為是資料的問題。
    """
    path, bctx = _run(tmp_path, plot_features="cmp_snr_mean_outlier,nosuchthing")
    page = path.read_text(encoding="utf-8")
    said = " ".join(bctx.warnings or [])
    assert "nosuchthing" in said and "Numbers to plot" in said
    assert page.count("<figure>") == 1, "只剩看得懂的那一張"


def test_it_refuses_politely_when_there_is_nothing_to_plot(tmp_path):
    """沒有 decide、又沒填名字 —— 那不是「畫一張空圖」，是設定還沒完成。"""
    from d4t.core.pipeline.step import StepError

    recipe = Recipe(
        recipe_id="bare", routes={"ebi_patch": ["plot"]},
        nodes={"plot": RecipeNode("plot", CARD,
                                  {"folder": str(tmp_path / "x"),
                                   "contents": TICK})},
        score=ScoreSpec(expr="", threshold=0.5, bins={}))
    bctx = BatchContext(rows=_rows(), dataset=None, recipe=recipe,
                        kind="ebi_patch")
    with pytest.raises(StepError) as e:
        REGISTRY[CARD]().run_batch(bctx, recipe.nodes["plot"].params)
    assert "Numbers to plot" in str(e.value)


def test_without_a_decision_it_still_draws_the_whole_lot(tmp_path):
    """沒有判定但有指定數字 → 一個盒子（這一批）。分不出類是實話，不是錯誤。"""
    path = tmp_path / "one" / "spread.html"
    recipe = Recipe(
        recipe_id="bare", routes={"ebi_patch": ["plot"]},
        nodes={"plot": RecipeNode("plot", CARD,
                                  {"folder": str(path.parent),
                                   "contents": TICK,
                                   "plot_features":
                                       "cmp_snr_mean_outlier"})},
        score=ScoreSpec(expr="", threshold=0.5, bins={}))
    bctx = BatchContext(rows=_rows(), dataset=None, recipe=recipe,
                        kind="ebi_patch")
    REGISTRY[CARD]().run_batch(bctx, recipe.nodes["plot"].params)
    page = path.read_text(encoding="utf-8")
    assert REGISTRY[CARD].ALL_LABEL in page
    assert page.count("<figure>") == 1


def test_a_failed_defect_is_not_a_class(tmp_path):
    """跑掛的那幾顆**不畫成一個盒子** —— 它們不是一種判定結果。

    （`verdict_rows` 會把它們列成 ``failed`` / ``unbinned`` 兩列，那是報表上
    要講的事；圖上多一個叫 failed 的盒子只會讓人以為那是第五類。）
    """
    rows = _rows()
    rows.append({"defect_id": "boom", "ok": False, "error": "nope",
                 "features": {}})
    path, _ = _run(tmp_path, rows=rows)
    page = path.read_text(encoding="utf-8")
    assert "could not be measured" not in page
    # 三類，每張圖三個 n= 標籤
    first = page.split("</figure>")[0]
    assert len(re.findall(r">n=\d+<", first)) == 3
    assert sum(int(n) for n in re.findall(r">n=(\d+)<", first)) == 15, \
        "跑掛的那一顆不進任何一個盒子"


def test_the_page_is_a_single_file_with_the_svg_inline(tmp_path):
    """一個檔案就是全部 —— 可以直接寄出去（同 `output_html` 的理由）。"""
    path, _ = _run(tmp_path)
    page = path.read_text(encoding="utf-8")
    assert "<svg" in page and "<img" not in page
    assert not list(tmp_path.glob("*.tmp")), "atomic 寫入（鐵則 5）"
    assert not list(tmp_path.glob("*.svg")), "不該散出第二個檔案"


def test_the_card_is_an_end_point_like_every_other_output_card(tmp_path):
    """Output 段的不變量：不吐流、不吐特徵、**沒有輸入埠**（不接線）。"""
    card = REGISTRY[CARD]
    p = card.validate_params({"folder": "x"})
    assert card.resolve_reads(p) == []
    assert card.resolve_writes(p) == []
    assert card.resolve_features(p) == []
    assert card.configuration_issues({"folder": ""}), "沒填路徑要講"
