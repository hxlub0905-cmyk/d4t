# -*- coding: utf-8 -*-
"""`recipes/` 裡出貨的 recipe —— **每一份都要跑得動**。

為什麼這支測試比那幾份檔案還重要
--------------------------------
這個 repo 上一次有「範例 recipe」是 `examples/`，而它 2026-08-16 被整個刪掉，
理由不是「不需要範例」——是**它們爛了**：卡片改名、參數換了、其中五份根本
載不進來，而沒有任何一條測試問過它們。留下來的是兩個按了會撞牆的入口
（`scope.SHOW_SAMPLE_ENTRIES`），而**按了撞牆的鈕比沒有那顆鈕更糟**（推廣鐵則）。

所以這一次 recipe 跟測試一起進來。這裡問三種問題：

1. **載得進來**（`Recipe.load`）而且 **`validate` 沒有 error** ——
   一份出貨的 recipe 打開來就有紅字，等於送出去的東西是壞的。
2. **接線是對的**：線在該在的埠上（F9／鐵則 9 —— 資料從哪來由線決定）。
3. **真的跑得出那三類**：端對端跑一次，① ② ③ 都要數得出來。

⚠ 第 3 條刻意跑**整條路**（`run_batch` + `run_batch_steps`），不是 mock ——
這份 recipe 的價值就在「照著跑會得到什麼」，而那件事只有真的跑才問得到。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest import pair_source as pair_ingest       # noqa: E402
from d4t.core.ingest.dataset import load_dataset             # noqa: E402
from d4t.core.pipeline import Recipe, run_batch, validate    # noqa: E402
from d4t.core.pipeline.batch import run_batch_steps          # noqa: E402

RECIPES = REPO / "recipes"
CHAR = RECIPES / "ebi-to-api-characterization.json"


def _shipped():
    return sorted(RECIPES.glob("*.json"))


# --------------------------------------------------------------------------- #
# 1. 每一份都載得進來、健檢沒有 error
# --------------------------------------------------------------------------- #
def test_there_is_at_least_one_shipped_recipe():
    """空的 `recipes/` 會讓底下每一支測試變成「什麼都沒測、而且是綠的」。"""
    assert _shipped(), "recipes/ 是空的 —— 底下的測試就全部空轉了"


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: p.name)
def test_a_shipped_recipe_loads_and_passes_its_own_lint(path):
    """**沒有 error**（warning 可以）。

    warning 放行是刻意的：這份 characterization recipe 有一條
    `unknown-feature`（排名欄位還沒選，所以沒有人產 `pair_die_rank`），
    而那正是它要講的話 —— 它連帶著一片叫「no ranking column picked yet」的
    葉子。擋掉 warning 等於逼一份誠實的 recipe 說謊。
    """
    recipe = Recipe.load(path)
    for kind in recipe.routes:
        errors = [i for i in validate(recipe, kind=kind) if i.level == "error"]
        assert not errors, "\n".join(
            "%s @%s: %s" % (i.code, i.node_id, i.detail) for i in errors)


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: p.name)
def test_a_shipped_recipe_survives_a_round_trip(path):
    """存檔那一對是 `run_batch` 送 recipe 進 worker 的路（鐵則 9）。"""
    recipe = Recipe.load(path)
    assert Recipe.from_json_dict(recipe.to_json_dict()).to_json_dict() \
        == recipe.to_json_dict()


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: p.name)
def test_a_shipped_recipe_says_which_version_wrote_it(path):
    """`app_version` 在的話，使用者在舊版打開它會被告知「你的程式舊了」，
    而不是「這份檔案壞了」（`docs/PITFALLS.md`）。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert str(raw.get("app_version", "")).strip()


# --------------------------------------------------------------------------- #
# 2. characterization：接線與那三片葉子
# --------------------------------------------------------------------------- #
def test_the_characterization_recipe_is_wired_the_way_the_manual_says():
    """**小圖接 Small image、大圖接 Search inside** —— 反過來接就是拿大圖去
    小圖裡找，而 `docs/USING-CHARACTERIZATION.md` §3 就是這張表。"""
    recipe = Recipe.load(CHAR)
    wires = {(e.src, e.src_out, e.dst, e.dst_in) for e in recipe.edges}
    assert ("load", "single", "h2h", "search") in wires
    assert ("pair", "paired", "h2h", "template") in wires


def test_the_output_card_is_wired_to_nothing_on_purpose():
    """**Output 段沒有輸入埠** —— 它不接線，在 route 上就會跑。

    使用者這一輪問的正是這件事（「output 段要怎麼接」）。答案是「不接」，
    而那不是漏掉的：`_OutputStep.resolve_reads` 回空清單，`run_batch_steps`
    是整批跑完之後照 route 的順序各跑一次。拉一條線進去的話那條線落在一個
    不存在的埠上 —— 畫布會說謊。
    """
    from d4t.core.pipeline import get_step

    recipe = Recipe.load(CHAR)
    assert "report" in recipe.routes["rsem"], "沒在 route 上就永遠不會跑"
    assert not [e for e in recipe.edges if e.dst == "report"]
    step = get_step(recipe.nodes["report"].step)
    assert step.resolve_reads(recipe.nodes["report"].params) == []


def test_the_first_question_is_pair_found():
    """判定樹**第一步一定要問 `pair_found`**。

    樹只會評走得到的那條路，所以先問它，③ 那一支就永遠問不到 ncc /
    排名那幾題，`decide_unanswered` 維持 0。反過來排的話那幾顆會累積一堆
    「問不出來」，而那是 recipe 的錯不是資料的錯。
    """
    tree = Recipe.load(CHAR).decide.tree
    assert "pair_found" in tree.when
    assert tree.yes.bin == 3, "yes 那一邊就是「EBI 沒偵測到」"


def test_the_grouping_ships_filled_in_and_the_score_column_does_not():
    """**分組預先填好，排序欄留空** —— 兩格的性質不一樣。

    `XINDEX` + `YINDEX`（每顆 die 各自排）是絕大多數站點的 sample 規則，
    而**填錯它不會有任何人講話**：只勾一欄就是把整整一行 die 併成一組，
    跑得完、數字看起來正常，只有 `pair_die_total` 看得出來。實測 4×3 顆 die、
    每 die 取前 2 名：只勾 `XINDEX` 讓「① 抓到了」從 24 顆掉到 8 顆，全部灌進
    「② 排名太低」—— 整份報告的結論反過來。所以它不留給使用者猜。

    `rank_by` 相反：每一台機台的分數欄叫的名字不一樣，猜不到。而「還沒選」
    不是安靜的 —— `die_rank` 這一行帶 `fill`，所以每一顆都拿得到
    `die_rank_missing`，樹上第二問就是它。
    """
    recipe = Recipe.load(CHAR)
    pair = recipe.nodes["pair"].params
    assert pair["rank_within"] == "XINDEX,YINDEX"
    assert pair["rank_by"] == ""

    lets = {x.name: x for x in recipe.decide.let}
    assert lets["die_rank"].expr == "pair_die_rank"
    assert lets["die_rank"].fill, "沒有 fill 的話那一顆會整個失敗，不是分一類"
    assert "die_rank_missing" in recipe.decide.tree.no.when


def test_the_half_filled_ranking_is_a_warning_not_a_blocker():
    """填了分組、還沒填排序欄 —— 那張卡**跑得起來**，所以它是 warning。

    F33 把這一條放在 `configuration_issues`（error），於是這份 recipe 只要把
    “Rank within” 預先填對，就會被自己的 lint 擋在 CLI 門外。分成兩支之後
    判準是一句話：error ＝ 這張卡會拋或什麼都不產出；warning ＝ 它會跑，
    但你八成不是這個意思。
    """
    recipe = Recipe.load(CHAR)
    issues = [i for i in validate(recipe, kind="rsem") if i.node_id == "pair"]
    assert not [i for i in issues if i.level == "error"]
    hint = [i for i in issues if i.code == "half-configured"]
    assert len(hint) == 1
    assert "Rank by" in hint[0].detail


def test_it_runs_as_it_ships_without_any_editing(tmp_path):
    """**下載下來、載進去、按跑，不改一個字** —— 這是使用者這一輪要的東西。

    唯一的條件是「有第二份資料」，而那本來就不可能寫進 recipe（路徑不進
    recipe，F15）。沒有排名欄位的時候每一顆落在第 9 類 —— 那是報表在告訴他
    還有哪一格沒填。
    """
    main, second = _two_lots(tmp_path)
    recipe = _with_folder(Recipe.load(CHAR), tmp_path / "out")
    rows = run_batch(recipe, main, workers=1)

    assert all(r.get("ok") for r in rows), \
        [r.get("error") for r in rows if not r.get("ok")]
    bins = {int(r.get("bin", -1)) for r in rows}
    assert bins <= {1, 2, 3, 9}
    assert 9 in bins, "沒選排名欄位就該落在那一片說得出原因的葉子上"
    assert all(int(r["features"].get("decide_unanswered", 0)) == 0
               for r in rows), "每一題都答得出來 —— 那正是 fill 與樹的順序在做的事"


def test_all_three_classes_come_out_once_the_ranking_column_is_picked(tmp_path):
    """填上那一格之後，① ② ③ 三類都要真的數得出來。

    這是整份 recipe 唯一的驗收條件 —— 它存在的理由就是把 ② 跟 ③ 分開。
    """
    main, second = _two_lots(tmp_path)
    recipe = _configured(Recipe.load(CHAR), tmp_path / "out")

    rows = run_batch(recipe, main, workers=1)
    assert all(r.get("ok") for r in rows), \
        [r.get("error") for r in rows if not r.get("ok")]
    bins = sorted({int(r.get("bin", -1)) for r in rows})
    assert bins == [1, 2, 3], "① 抓到了 / ② 排名太低 / ③ 沒偵測到，一類都不能少"

    # ③ 那幾顆是**第二份裡沒有的那幾顆**，而且它們沒有失敗。
    missed = [r for r in rows if int(r["bin"]) == 3]
    assert missed and all(r["features"]["pair_found"] == 0.0 for r in missed)
    assert all("match_dist_nm" not in r["features"] for r in missed), \
        "配不到就不寫那幾格（算不出來的不寫）"


def test_the_report_it_writes_has_a_row_for_every_defect(tmp_path):
    """整條路走到底：報表、CSV、圖、還有那份 recipe 的複本。"""
    main, second = _two_lots(tmp_path)
    folder = tmp_path / "out"
    recipe = _configured(Recipe.load(CHAR), folder)

    rows = run_batch(recipe, main, workers=1)
    bctx = run_batch_steps(recipe, main, rows, kind="rsem")
    assert not bctx.errors, bctx.errors

    html = (folder / "report.html").read_text(encoding="utf-8")
    assert (folder / "defects.csv").is_file()
    assert (folder / "recipe.json").is_file()
    for name in ("caught", "ranked too low", "never detected"):
        assert name in html, "三類的名字都要出現在報表上"
    # 配不到的那一顆**沒有第二張圖**，而那一格是空的不是破圖。
    assert "<td class='none'>" in html


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _two_lots(tmp_path):
    """main = API 那一份（8 顆）；第二份 = 少了兩顆的「EBI」，帶一個分數欄。

    第二份用**同一個 seed** 產，所以兩邊座標對得起來（真實情況是兩台機台量
    同一片 wafer）。少掉的那兩顆就是 ③。
    """
    from make_sample_rsem import generate

    main = load_dataset(generate(str(tmp_path / "api"), n=8, seed=11)["klarf"])
    other = load_dataset(
        generate(str(tmp_path / "ebi"), n=8, seed=11)["klarf"])
    # **少兩顆** —— 那兩顆在 API 上有、EBI 上沒有，就是「根本沒偵測到」。
    other.items = [it for it in other.items if it.index not in (2, 5)]
    pair_ingest.attach(main, other, "ebi")
    # 機台自己的分數欄。真的 KLARF 上它叫什麼由站點決定（所以 recipe 裡是
    # 空的）—— 這裡塞一個，讓排名那一半也跑得到。
    for i, it in enumerate(main.sources["ebi"].items):
        it.fields["EBISCORE"] = float(100 - i * 7)
    return main, other


def _with_folder(recipe, folder):
    recipe.nodes["report"].params["folder"] = str(folder)
    return recipe


def _configured(recipe, folder):
    """把使用者本來就要填的那幾格填好（站點資料，不進出貨的檔案）。"""
    recipe = _with_folder(recipe, folder)
    recipe.nodes["pair"].params["rank_by"] = "EBISCORE"
    recipe.nodes["pair"].params["carry"] = "DEFECTID"
    # ⚠ **這裡把出貨的 `XINDEX,YINDEX` 清掉**，而理由值得寫下來：合成 lot
    # 一顆 die 只有一兩顆 defect，所以照 die 分組之後每一組都只有一個成員 ——
    # 每一顆都是 rank 1，② 那一類就永遠是空的。那不是 bug（那份資料上的
    # 答案本來就是這樣），是**這份合成資料撐不起分組**。分組本身的語意
    # 在 `test_pair_source.py`（手造的 die 佈局，看得見組的大小）。
    recipe.nodes["pair"].params["rank_within"] = ""
    lets = list(recipe.decide.let)
    for i, x in enumerate(lets):
        if x.name == "sample_top":
            lets[i] = type(x)(name=x.name, expr="3", scale=x.scale,
                              fill=x.fill)
    from dataclasses import replace
    recipe.decide = replace(recipe.decide, let=lets)
    return recipe
