# Output 卡七張收成三張（F38，2026-08-26）。
"""四張報表卡折進 ``output_report``：**遷移**，加上兩件合併帶進來的新責任。

使用者：「七張裡有五張在回答同一個問題，收成三張。」

這一份守三件事：

1. **每一張舊卡開得起來，而且寫出來的東西沒變**（內容；路徑依那張對照表位移
   —— 產物的形狀從「一個檔案」變成「一個資料夾」是使用者定調的取捨）。
2. **遷移是冪等的**（鐵則 9）。``to_json_dict → from_json_dict`` 一旦不是
   identity，``workers=1`` 與 ``workers=2`` 就會算出不同的分數 —— 那真的發生
   過（`docs/PITFALLS.md`）。
3. **合併帶進來的兩個新壞法**：勾了六樣而其中一樣寫不出來時不准連坐其他樣；
   以及參數推到宣告的上下界不准炸。

⚠ **第 3 點的後半在 `tests/test_card_invariants.py` 裡是做不到的。** 那六條
不變量的 ``CARDS`` 過濾的是 ``not c.is_batch``，而每一張 Output 卡都是
``is_batch`` —— I5（參數推到上下界不炸也不吐 NaN）走的是 ``run_defect``，
而這張卡根本不在那條路上。所以那件事要在這裡自己問一次，走
``run_batch_steps``。
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
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import run_batch, run_batch_steps  # noqa: E402
from d4t.core.pipeline.recipe import Recipe  # noqa: E402
from d4t.core.pipeline.step import REGISTRY  # noqa: E402
from d4t.core.steps.output import (  # noqa: E402
    CONTENTS, DEFAULT_CONTENTS,
)

KIND = "ebi_patch"
CARD = "output_report"

#: 舊 key → (舊參數, 遷移後的 ``contents``)。
#:
#: ``output_report`` 自己也在表上：它以前是「寫一個 Excel 檔」，key 沒換而
#: **意思換了**，所以它的判準是「舊的參數名（``path``）還在不在」。
FOLDED = {
    "output_csv": ({"path": "/x/my.csv", "include_features": False}, "table"),
    "output_html": ({"path": "/x/page.html", "title": "T"}, "report"),
    "output_boxplot": ({"path": "/x/spread.html",
                        "features": "glv_max"}, "boxplot"),
    "output_report": ({"path": "/x/book.xlsx"}, "excel"),
}


def _recipe_dict(step, params):
    return {
        "recipe_id": "fold", "version": 1,
        "routes": {KIND: ["load", "out"]},
        "nodes": {
            "load": {"step": "load_patch", "params": {}},
            "out": {"step": step, "params": dict(params)},
        },
        "score": {"expr": "glv_max", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }


# --------------------------------------------------------------------------- #
# 1. 遷移：每一張舊卡各一條
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("step", sorted(FOLDED), ids=sorted(FOLDED))
def test_an_old_report_card_becomes_the_merged_card(step):
    """舊 key → ``output_report`` ＋ 只勾它自己那一樣。"""
    params, tick = FOLDED[step]
    rc = Recipe.from_json_dict(_recipe_dict(step, params))
    node = rc.nodes["out"]
    assert node.step == CARD
    assert node.params["contents"] == tick
    assert node.id == "out", "節點 id 不准動（畫布上的線指著它）"


@pytest.mark.parametrize("step", sorted(FOLDED), ids=sorted(FOLDED))
def test_the_single_file_path_becomes_the_folder_that_held_it(step):
    """``/x/my.csv`` → ``folder=/x``，而舊的那一格**不留下來**。

    留著的話 ``validate_params`` 會說「unknown parameter」—— 一份跑得動的
    recipe 開起來變成一條紅字。
    """
    params, _ = FOLDED[step]
    rc = Recipe.from_json_dict(_recipe_dict(step, params))
    node = rc.nodes["out"]
    assert "path" not in node.params
    assert node.params["folder"] == "/x"


def test_a_bare_file_name_does_not_become_nowhere_to_write():
    """``path="report.html"`` 的 dirname 是**空字串**，而空字串的意思是
    「還沒填」—— 一份跑得動的 recipe 會變成一條設定錯誤。"""
    rc = Recipe.from_json_dict(
        _recipe_dict("output_html", {"path": "report.html"}))
    assert rc.nodes["out"].params["folder"] == "."
    assert not REGISTRY[CARD].configuration_issues(rc.nodes["out"].params)


def test_the_box_plot_numbers_move_to_their_new_box():
    """``features`` → ``plot_features``（它跟 ``include_features`` 撞了）。

    ⚠ 漏掉這一半的下場**跑得完**：那張圖照畫，只是畫的是判定問過的那幾個
    而不是使用者指定的 —— 而畫面上沒有任何線索。
    """
    rc = Recipe.from_json_dict(
        _recipe_dict("output_boxplot",
                     {"path": "/x/s.html", "features": "a,b"}))
    p = rc.nodes["out"].params
    assert "features" not in p
    assert p["plot_features"] == "a,b"


def test_the_folder_card_keeps_every_setting_it_had():
    """``output_bundle`` 只是換 key —— 使用者填過的每一格原封不動。"""
    rc = Recipe.from_json_dict(_recipe_dict("output_bundle", {
        "folder": "/x", "limit": 7, "montage": False,
        "rank_by": "glv_max", "jpeg_quality": 91}))
    p = rc.nodes["out"].params
    assert rc.nodes["out"].step == CARD
    assert (p["limit"], p["montage"], p["rank_by"], p["jpeg_quality"]) \
        == (7, False, "glv_max", 91)


def test_a_folder_card_without_ticks_gets_the_old_four_written_in():
    """**沒寫 ``contents`` 的舊檔案要把當時的行為明寫進去。**

    F38 給那一格加了 Excel 與 box plot 兩個新選項。「鍵不在＝用預設」的舊
    recipe（出貨那份就是）如果跟著新預設走，會安靜地多寫兩個檔案 —— 而它們
    一個字都沒改過。
    """
    rc = Recipe.from_json_dict(_recipe_dict("output_bundle", {"folder": "/x"}))
    got = rc.nodes["out"].params["contents"].split(",")
    assert sorted(got) == sorted(DEFAULT_CONTENTS)
    assert "excel" not in got and "boxplot" not in got


def test_the_new_ticks_are_not_on_by_default():
    """上面那條的另一半：**新卡片的預設**也不含那兩個。

    兩件事是分開的（`DEFAULT_CONTENTS` 與遷移那張表各一份），所以兩邊都要問
    —— 綁成一份的話，動了預設就會回頭改掉舊 recipe 的行為。
    """
    spec = {p.name: p for p in REGISTRY[CARD].params}["contents"]
    assert sorted(spec.default.split(",")) == sorted(DEFAULT_CONTENTS)
    assert set(spec.choices) == set(CONTENTS), "勾得到的是六個"
    assert "excel" in spec.choices and "excel" not in spec.default


# --------------------------------------------------------------------------- #
# 2. 鐵則 9：第二次跑什麼都不會發生
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("step", sorted(FOLDED) + ["output_bundle"],
                         ids=sorted(FOLDED) + ["output_bundle"])
def test_the_migration_is_an_identity_the_second_time(step):
    """``to_json_dict → from_json_dict`` 是 identity（鐵則 9）。

    那條路正是 `run_batch` 送 recipe 進 worker 走的 —— 它一旦不是 identity，
    ``workers=1`` 與 ``workers=2`` 會算出不同的分數。真的發生過。
    """
    params = FOLDED.get(step, ({"folder": "/x"}, None))[0]
    once = Recipe.from_json_dict(_recipe_dict(step, params)).to_json_dict()
    twice = Recipe.from_json_dict(json.loads(json.dumps(once))).to_json_dict()
    assert once == twice


def test_a_recipe_already_on_the_new_card_is_left_alone():
    """判準是「**舊東西在不在**」，不是「新東西不在」（鐵則 9）。

    這一支問的是「已經填好的新 recipe 不被碰」。**分不出新舊的那個寫法要靠
    下一支才抓得到** —— 量過的：把判準改成「``folder`` 不在就補」，這一支
    照樣綠（它填了 ``folder``），紅的是下一支。
    """
    d = _recipe_dict(CARD, {"folder": "/x", "contents": "report,pictures",
                            "limit": 3})
    rc = Recipe.from_json_dict(d)
    assert rc.nodes["out"].params == d["nodes"]["out"]["params"]


def test_an_unconfigured_new_card_does_not_get_a_folder_invented():
    """路徑那一格空著的新卡片**不准**被遷移碰到。

    碰到的話它會拿到 ``contents="excel"`` —— 一張使用者還沒填完的報表卡，
    安靜地變成一張只寫 Excel 的卡。

    ⚠ **這一支就是鐵則 9 那條線。** 把判準寫成「``folder`` 不在就補」（＝問
    「新東西不在」而不是「舊東西在」）的話，只有這一支會紅 —— 驗過了。
    """
    rc = Recipe.from_json_dict(_recipe_dict(CARD, {}))
    assert rc.nodes["out"].params == {}


def test_the_write_images_chain_still_lands_on_the_merged_card():
    """``output_image`` → （F37）``output_bundle`` → （F38）``output_report``。

    **遷移鏈要一段一段接**：寫一條 `output_image` 直達的捷徑只有舊檔案會走到，
    永遠不會有人在上面測試（`_migrate_merged_cards` 的 docstring 那句話）。
    """
    rc = Recipe.from_json_dict(
        _recipe_dict("output_image", {"folder": "/x", "limit": 4}))
    p = rc.nodes["out"].params
    assert rc.nodes["out"].step == CARD
    assert p["contents"] == "pictures"
    assert p["picture_format"] == "png", "PNG 那個差別是 F37 那一道在補的"
    assert p["limit"] == 4


# --------------------------------------------------------------------------- #
# 3. 合併帶進來的新責任
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("fold")), n=4, seed=5)


@pytest.fixture(scope="module")
def dataset(lot):
    return load_dataset(lot["klarf"])


def _run(dataset, folder, **over):
    params = {"folder": str(folder)}
    params.update(over)
    r = Recipe.from_json_dict({
        "recipe_id": "fold_run", "version": 1,
        "routes": {KIND: ["load", "glv", "out"]},
        "nodes": {
            "load": {"step": "load_patch", "params": {}},
            "glv": {"step": "glv_stats",
                    "params": {"source": "test", "metrics": "glv_max"}},
            "out": {"step": CARD, "params": params},
        },
        "score": {"expr": "glv_max", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    })
    rows = run_batch(r, dataset, workers=1)
    return run_batch_steps(r, dataset, rows), rows


def test_one_thing_failing_does_not_take_the_rest_of_the_folder_with_it(
        dataset, tmp_path, monkeypatch):
    """**合併帶進來的、以前不存在的壞法。**

    分成五張卡的時候「Excel 寫不出來」只毀掉 Excel 那張卡。併成一張之後，
    一個 raise 會把報表、CSV、圖、recipe 一起丟掉 —— 使用者少的不是一個檔案，
    是整份報表。
    """
    from d4t.core.export import report as export_report

    def boom(*a, **k):
        raise ImportError("no openpyxl here")

    monkeypatch.setattr(export_report, "write_excel", boom)
    out = tmp_path / "folder"
    bctx, rows = _run(dataset, out, contents="report,table,excel,recipe")

    assert not bctx.errors, "一樣寫不出來不是整張卡失敗"
    assert (out / "report.html").is_file()
    assert (out / "defects.csv").is_file()
    assert (out / "recipe.json").is_file()
    assert not (out / "report.xlsx").exists()
    said = " ".join(bctx.warnings)
    assert "openpyxl" in said, "而且要講得出下一步"


def test_an_ordinary_write_failure_does_not_connect_either(
        dataset, tmp_path, monkeypatch):
    """上一支走的是 ``ImportError`` 那一支（openpyxl 沒裝）。

    ⚠ **只有那一支的話，一般的寫檔失敗仍然會連坐** —— 量過的：把泛用的
    ``except Exception`` 改回 ``raise``，上一支照樣綠。所以這一支走另一條：
    一個普通的 ``OSError``（磁碟滿了、沒有權限）。
    """
    from d4t.core.export import report as export_report

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(export_report, "write_csv", boom)
    out = tmp_path / "csv_boom"
    bctx, rows = _run(dataset, out, contents="report,table,recipe")

    assert not bctx.errors, bctx.errors
    assert (out / "report.html").is_file()
    assert (out / "recipe.json").is_file()
    assert not (out / "defects.csv").exists()
    assert "disk full" in " ".join(bctx.warnings)


def test_when_everything_asked_for_fails_the_card_says_why(dataset, tmp_path):
    """**勾了的全部失敗 ⇒ 這張卡真的什麼都沒做**，那不是一句警告。

    而訊息要帶著那一樣**自己的理由** —— 只勾了一樣的時候（＝每一份從舊的單檔
    卡遷移過來的 recipe），那句話跟合併之前逐字相同。包一層
    「something went wrong」上去的話，使用者拿到的是一句沒有下一步的話。
    """
    from d4t.core.pipeline.step import StepError

    out = tmp_path / "only_plot"
    bctx, _rows = _run(dataset, out, contents="boxplot")
    assert "out" in bctx.errors
    said = bctx.errors["out"]
    assert "Numbers to plot" in said, said
    assert said.count("[output_report]") == 1, "前綴不准疊第二次：%s" % said
    assert isinstance(StepError("k", "m").detail, str)


def test_nothing_ticked_is_caught_before_it_makes_an_empty_folder():
    """一個都沒勾的資料夾**會被建出來、而且是空的** —— 跑得完、沒有錯誤、
    什麼都沒有。那是這張卡最容易犯的新錯。"""
    card = REGISTRY[CARD]
    assert card.configuration_issues({"folder": "/x", "contents": ""})
    assert not card.configuration_issues({"folder": "/x"}), \
        "「這個鍵不在」＝還沒設過，不是「一個都沒勾」"


#: 每一格有上下界的數值參數 × 它宣告的兩個端點（同 `test_card_invariants` 的
#: `_extreme_param_cases`，只是那一支碰不到 batch 卡）。
EXTREME = sorted(
    (spec.name, int(b) if spec.type == "int" else float(b))
    for spec in REGISTRY[CARD].params
    if spec.type in ("int", "float")
    for b in (spec.min, spec.max) if b is not None)


def test_the_extreme_parameter_check_is_not_vacuous():
    """空轉的話上面那條測試會是綠的而且什麼都沒問。"""
    assert len(EXTREME) >= 6, EXTREME
    assert len({n for n, _ in EXTREME}) >= 3, EXTREME


@pytest.mark.parametrize("name,value", EXTREME,
                         ids=["%s=%s" % (n, v) for n, v in EXTREME])
def test_a_parameter_at_its_limit_does_not_blow_up_the_folder(
        dataset, tmp_path, name, value):
    """``min``/``max`` 是這張卡自己宣告的「使用者拖得到的範圍」（鐵則 4），
    所以這一條問的正是：**那個範圍宣告得對嗎**。

    一次只推一個參數（其餘留預設）—— 全部一起推的話，紅了也不知道是誰造成的，
    而使用者實際上也是一次拖一支滑桿。

    六樣全部勾起來，因為合併之後「勾了什麼」決定跑到哪幾段程式碼。
    """
    out = tmp_path / ("lim_%s_%s" % (name, value))
    bctx, rows = _run(dataset, out, contents=",".join(CONTENTS),
                      plot_features="glv_max", **{name: value})
    assert not bctx.errors, bctx.errors
    # 勾了的六樣至少要有一樣真的落地 —— 「跑完了而資料夾是空的」不算過。
    assert os.listdir(str(out)), "推到 %s=%s 就什麼都沒寫出來" % (name, value)


@pytest.mark.parametrize("ticks", [
    "report", "table", "pictures", "recipe", "excel", "boxplot",
    ",".join(CONTENTS),
], ids=lambda t: t.replace(",", "+"))
def test_every_single_tick_writes_what_it_says_and_nothing_else(
        dataset, tmp_path, ticks):
    """一個勾一個檔案，**而且沒有別的**。

    多寫一個的話，一份從 `output_csv` 遷移過來的 recipe 會在使用者的交付資料夾
    裡多出一份報表 —— 跑得完、沒有錯誤、而那不是他要的東西。
    """
    want = set(ticks.split(","))
    out = tmp_path / ticks.replace(",", "_")
    bctx, rows = _run(dataset, out, contents=ticks, plot_features="glv_max")
    assert not bctx.errors, bctx.errors
    card = REGISTRY[CARD]
    expect = {
        "report": card.REPORT_NAME, "table": card.CSV_NAME,
        "recipe": card.RECIPE_NAME, "excel": card.EXCEL_NAME,
        "boxplot": card.PLOT_NAME,
    }
    for tick, name in expect.items():
        assert (out / name).is_file() is (tick in want), (tick, name)
    if "pictures" in want:
        # 有報表才有 `images/` 那一層（那一層的理由是報表要相對路徑連過去）。
        where = out / card.IMAGE_DIR if "report" in want else out
        assert len(list(where.glob("*.jpg"))) == len(rows)
    else:
        assert not list(out.rglob("*.jpg"))
