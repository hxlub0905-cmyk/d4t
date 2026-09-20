# F117 F5／F3／F8／F7：離開這個工具的那些檔案（2026-09-20）。
"""這四條的共通點：**使用者會把它寄給別人。**

畫面上的毛病他自己能繞過 —— 寄出去的 CSV 與報表不能，而收到的人沒有這個工具
可以回頭問。

* **F5** 均勻度 CSV 的欄名長成 `cells_cells_area_px`。那個名字會被貼進別人的
  分析腳本裡。
* **F3** CSV 不帶 KLARF 座標（機制早就有，是 recipe 沒開）；順帶查出
  `d4t run --csv` 有一份**手抄的 writer**，所以 F117 F1 修的「表頭 `score`
  出現兩次」在那條路上還活著。
* **F8** 熱圖刻度 `24.50`、標題一個靠左三個置中、profile 三種線沒有圖例、
  摘要表有兩欄整欄是 `-`。
* **F7** 四張圖單欄，寬頁右半空白。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from d4t.core import steps as _steps                        # noqa: E402,F401
from d4t.core.export import report, uniformity_charts as uc  # noqa: E402
from d4t.core.export.boxplot import (                       # noqa: E402
    TITLE_WEIGHT, TITLE_X, build_boxplot_page,
)
from d4t.core.pipeline.recipe import Recipe, validate       # noqa: E402

RECIPES = REPO / "recipes"


def _recipe(name):
    return Recipe.load(str(RECIPES / name))


def _raw(name):
    return json.loads((RECIPES / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# F5：同一個字不要連著出現兩次
# --------------------------------------------------------------------------- #
def test_no_shipped_recipe_writes_a_doubled_column_name():
    """`cells_cells_area_px` —— 一次是 `output_prefix`，一次是區域名。"""
    for path in sorted(RECIPES.glob("*.json")):
        codes = [i for i in validate(Recipe.load(str(path)))
                 if i.code == "doubled-prefix"]
        assert not codes, (path.name, [i.detail for i in codes])


def test_the_lint_catches_it_when_somebody_does_it_again():
    """**反向測試** —— 拿掉出貨 recipe 上那一格之後，這條 lint 沒有東西可以
    咬了。它擋的是**下一個人**，所以這裡把那一格放回去問一次。
    """
    raw = _raw("one-image-uniformity.json")
    raw["nodes"]["roi"]["params"]["output_prefix"] = "cells"
    found = [i for i in validate(Recipe.from_json_dict(raw))
             if i.code == "doubled-prefix"]
    assert found, "lint 沒有咬到 —— 它現在什麼都不擋"
    assert found[0].level == "warning", "這不是錯，跑得起來（只是名字難看）"
    assert found[0].param == "output_prefix", "要指得出是哪一格"
    assert any("cells_cells" in n for n in found[0].names)


def test_a_name_that_merely_repeats_later_is_left_alone():
    """⚠ **只看相鄰的重複。**

    `epi_center_epi` 那種（同一個字隔開出現兩次）是另一回事：區域 `epi` 的
    center 那半，跟一個剛好也叫 `epi` 的 output_prefix。讀起來繞口，但它講的
    是兩件不同的事 —— 而這條 lint 問的是「有沒有一個字白寫了」。
    """
    from d4t.core.pipeline.recipe import _doubled_names

    class _Fake:
        @staticmethod
        def resolve_features(params):
            return ["epi_center_epi_area", "a_a_b", "plain_name"]

    assert _doubled_names(_Fake, {"output_prefix": "epi"}) == ["a_a_b"]


def test_nothing_is_flagged_when_the_user_never_typed_a_prefix():
    """⚠ 沒填那一格的時候**不出聲**。

    那是他唯一改得動的東西 —— 給不出動作的提醒會把真的那一條一起教成雜訊。
    """
    from d4t.core.pipeline.recipe import _doubled_names

    class _Fake:
        @staticmethod
        def resolve_features(params):
            return ["a_a_b"]

    assert _doubled_names(_Fake, {}) == []
    assert _doubled_names(_Fake, {"output_prefix": ""}) == []


# --------------------------------------------------------------------------- #
# F3：座標帶得出來，而且只帶一次
# --------------------------------------------------------------------------- #
def test_the_klarf_recipes_carry_the_coordinates():
    """走查：「CSV／報表預設不帶 KLARF 座標」—— 機制早就有，是沒開。"""
    for name in ("ebi-die-to-die.json", "rsem-worst-box.json"):
        raw = _raw(name)
        carried = {c.strip().upper()
                   for n in raw["nodes"].values()
                   if n["step"] in ("load_patch", "load_single")
                   for c in str(n["params"].get("carry", "")).split(",")}
        assert {"XREL", "YREL"} <= carried, (name, carried)


def test_the_recipe_without_a_klarf_carries_nothing():
    """⚠ `one-image-uniformity` 走的是 `folder` —— **根本沒有 KLARF**。

    在那一份上填欄名，每一顆都會失敗在一句「這份 lot 沒有那個欄位」。
    """
    raw = _raw("one-image-uniformity.json")
    assert list(raw["routes"]) == ["folder"]
    for n in raw["nodes"].values():
        assert not str(n["params"].get("carry", "") or "")


def test_only_the_safest_columns_are_turned_on():
    """⚠ **少一欄就整批失敗**（`load._carry_features` 故意拋）。

    所以出貨的那份只點名座標：`XREL`／`YREL` 是「一顆 defect 在哪裡」，沒有
    它們的 KLARF 不成立。`CLASSNUMBER` 這種**刻意不填** —— 一份沒有分類的
    檢測結果可以完全合法地沒有那一欄，而那會讓一份出貨的 recipe 在對方的機器
    上一顆都跑不出來。
    """
    for name in ("ebi-die-to-die.json", "rsem-worst-box.json"):
        raw = _raw(name)
        for n in raw["nodes"].values():
            carried = str(n["params"].get("carry", "") or "")
            if carried:
                assert {c.strip().upper() for c in carried.split(",")} \
                    == {"XREL", "YREL"}, (name, carried)


def test_the_cli_csv_goes_through_the_one_writer():
    """⚠ **這一條守的是一份手抄的 writer 不存在。**

    F117 F1 修「表頭裡 `score` 出現兩次」的時候數到三個寫檔的地方 —— 而
    `d4t run --csv` 是**第四份**，它沒有被數到。CLAUDE.md §0 那句話：
    抄第二份出來的那份一定會漂。
    """
    import ast

    src = (REPO / "d4t" / "__main__.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    writers = {n.func.attr for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "writerow" not in writers, "又有人自己寫 CSV 了"
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "write_csv" in names


def test_the_shared_writer_never_repeats_a_base_column():
    rows = [{"defect_id": "1", "ok": True, "score": 1.0, "bin": 0,
             "features": {"score": 1.0, "glv_mean": 3.0}}]
    assert report.detail_feature_keys(rows) == ["glv_mean"]
    header = list(report.BASE_COLUMNS) + report.detail_feature_keys(rows)
    assert len(header) == len(set(header)), header


def test_a_carried_column_lands_in_the_csv(tmp_path):
    """整條路：帶進來的欄 → feature → CSV 的一欄。"""
    rows = [{"defect_id": "1", "ok": True, "score": 1.0, "bin": 0,
             "features": {"XREL": 2818.375, "YREL": 4120.785}}]
    path = report.write_csv(rows, str(tmp_path / "out.csv"))
    with open(path, encoding="utf-8-sig", newline="") as f:
        head, first = list(csv.reader(f))[:2]
    assert "XREL" in head and "YREL" in head
    assert first[head.index("XREL")] == "2818.375"


# --------------------------------------------------------------------------- #
# F8：摘要表不印使用者答過的問題
# --------------------------------------------------------------------------- #
def _rows(**cells):
    return [{"name": "cells", "metric": "glv_mean", "boxes": 100,
             "cells": dict(cells)}]


def test_a_column_nobody_measured_is_not_printed():
    """⚠ 那兩欄之所以空著，是因為使用者**已經回答過了**（GLV 卡上沒勾）。"""
    keys = [c[0] for c in uc.summary_columns(_rows(cv_pct=0.25, slope_x=0.13))]
    assert keys == ["cv_pct", "slope_x"]
    html = uc.build_summary_html(_rows(cv_pct=0.25, slope_x=0.13))
    assert "range" not in html


def test_a_column_that_one_region_is_missing_stays():
    """⚠ **有一格有值就整欄留著。**

    那時候的 `-` 是真的資訊：別的區域量得到，這一個量不到。兩種 `-` 長得
    一樣而意思差很遠，分得開它們的唯一辦法就是「整欄都沒有」才拿掉。
    """
    rows = [{"name": "a", "metric": "m", "boxes": 4, "cells": {"range": 1.0}},
            {"name": "b", "metric": "m", "boxes": 4, "cells": {}}]
    assert [c[0] for c in uc.summary_columns(rows)] == ["range"]
    assert uc.build_summary_html(rows).count("<td>-</td>") == 1


def test_the_shipped_uniformity_page_has_no_empty_column():
    """出貨那份 recipe 的 GLV 卡只報 `cv_pct` / `slope_x` / `slope_y`。"""
    recipe = _recipe("one-image-uniformity.json")
    glv = next(n for n in recipe.nodes.values() if n.step == "glv_stats")
    report_keys = str(glv.params.get("report") or "")
    assert "range" not in report_keys, "前提變了 —— 這條測試要重寫"


# --------------------------------------------------------------------------- #
# F8：刻度、標題、圖例
# --------------------------------------------------------------------------- #
def test_pixel_ticks_are_whole_numbers():
    """⚠ 框中心落在半個像素上是真的，但**它不是資訊**。"""
    assert uc._pos_labels([24.5, 72.5, 120.5]) == ["24", "72", "120"]


def test_ticks_keep_their_decimals_when_rounding_would_collide():
    """⚠ 框只有幾個像素寬的時候，整數分不開相鄰兩欄。

    那時候印兩個一樣的數字比印 `24.50` 糟得多 —— 它看起來像畫錯了。
    """
    got = uc._pos_labels([1.0, 1.5, 2.0])
    assert len(set(got)) == 3, got


def test_every_chart_title_is_aligned_the_same_way():
    """⚠ 兩種對齊在同一頁上就是不對：眼睛會以為那是兩類東西。"""
    series = [{"name": "cells", "values": [1.0, 2.0, 3.0],
               "cx": [1.0, 2.0, 3.0], "cy": [1.0, 2.0, 3.0],
               "colour": "#2f9e8f"}]
    box = uc.build_chart_svg({"groups": series, "metric": "m"},
                             uc.CHART_BOX, {"title": "Box plot"})
    hist = uc.build_chart_svg({"groups": series, "metric": "m"},
                              uc.CHART_HIST, {"title": "Histogram"})
    for svg, name in ((box, "Box plot"), (hist, "Histogram")):
        assert "text-anchor='middle'>%s<" % name not in svg, name
        assert 'x="%d"' % TITLE_X in svg or "x='%d'" % TITLE_X in svg, name
        assert TITLE_WEIGHT in svg, name


def test_the_profile_says_which_line_is_which():
    """走查：「Position profile 虛線／點線無圖例」。"""
    series = {"groups": [{"name": "cells", "values": [1.0, 2.0, 3.0, 4.0],
                          "cx": [10.0, 20.0, 30.0, 40.0],
                          "cy": [10.0, 20.0, 30.0, 40.0],
                          "colour": "#2f9e8f"}],
              "metric": "glv_mean"}
    svg = uc.build_chart_svg(series, uc.CHART_PROFILE, {"axis": "x"})
    for word in ("profile", "trend", "group average"):
        assert ">%s<" % word in svg, word
    assert "slope" in svg, "斜率那個數字不准被圖例換掉 —— 兩件不同的事"


def test_the_legend_does_not_claim_a_colour_when_there_are_several_groups():
    """⚠ 一群的時候拿那一群的顏色是對的；好幾群的時候那個色塊會變成一句假話。

    它看起來像在說「這個顏色＝profile」，而每一群各有各的顏色。圖例講的是
    **線的樣子**，誰是誰由斜率那一行上的名字講。
    """
    def _svg(n):
        groups = [{"name": "g%d" % i, "values": [1.0, 2.0, 3.0, 4.0],
                   "cx": [10.0, 20.0, 30.0, 40.0],
                   "cy": [10.0, 20.0, 30.0, 40.0],
                   "colour": ["#2f9e8f", "#c2410c"][i]} for i in range(n)]
        return uc.build_chart_svg({"groups": groups, "metric": "m"},
                                  uc.CHART_PROFILE, {"axis": "x"})

    one, two = _svg(1), _svg(2)
    assert "#2f9e8f" in one.split(">profile<")[0].rsplit("<line", 1)[-1]
    legend_two = two.split(">profile<")[0].rsplit("<line", 1)[-1]
    assert "#2f9e8f" not in legend_two and "#c2410c" not in legend_two,         legend_two
    for name in ("g0", "g1"):
        assert name in two, "誰是誰還是要講得出來（斜率那一行）"


def test_the_legend_draws_lines_not_squares():
    """⚠ 方塊分不出虛實，而這裡要分的正好就是虛實。"""
    out = []
    uc._line_legend(out, [("#111", "", "solid"), ("#222", "6 4", "dashed")],
                    10.0, 20.0)
    svg = "".join(out)
    assert svg.count("<line") == 2
    assert "stroke-dasharray='6 4'" in svg
    assert "<rect" not in svg


# --------------------------------------------------------------------------- #
# F7：寬頁排兩欄
# --------------------------------------------------------------------------- #
def test_the_charts_page_lays_out_in_a_grid():
    page = build_boxplot_page([{"svg": "<svg/>"}, {"svg": "<svg/>"}],
                              title="t")
    assert "class='sheet'" in page
    assert "display:grid" in page
    assert "auto-fit" in page, "寫死欄數的話，窄的頁面會被切掉"


def test_a_narrow_page_falls_back_to_one_column():
    """`auto-fit` + `minmax` 的意思：放不下兩欄就自己收回一欄。

    ⚠ 這條測的是**那個規則寫對了**，不是瀏覽器怎麼算 —— 後者不是這裡能量的。
    """
    page = build_boxplot_page([{"svg": "<svg/>"}], title="t")
    assert "minmax(560px,1fr)" in page.replace(" ", "")


def test_one_chart_still_gets_the_container():
    """一張圖的那一頁也走同一條路 —— 兩種版型就是兩種要維護的東西。"""
    assert "class='sheet'" in build_boxplot_page([{"svg": "<svg/>"}], title="t")
