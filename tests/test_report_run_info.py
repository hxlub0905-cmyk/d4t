# F117 F2：一份報表要講得出「這是哪一次跑的」（2026-09-20）。
"""走查記的原話：**「檔案一離開電腦就追不回是哪一次跑的」。**

`report.html` 以前只有 recipe id 與 bin 計數 —— 沒有日期、沒有來源 KLARF、
沒有 d4t 的版本／build id、也看不出這一批是不是只跑了一部分。而 `report.xlsx`
的摘要頁本來就有 recipe 那一段，兩份檔案對同一次跑講的話不一樣。

⚠ **兩份同源**：那幾列由 `export/report.run_info()` 產，HTML 與 xlsx 都吃它。
各算一份的那天，它們會對同一次跑講出兩個答案，而沒有人知道哪一個是對的。
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402  —— 觸發卡片註冊
from d4t import version_line  # noqa: E402
from d4t.core.export.html import build_report  # noqa: E402
from d4t.core.export.report import RUN_INFO_LABELS, run_info  # noqa: E402
from d4t.core.pipeline.recipe import Recipe  # noqa: E402

WHEN = datetime.datetime(2026, 9, 20, 14, 33)


def _recipe():
    path = REPO / "recipes" / "ebi-die-to-die.json"
    return Recipe.from_json_dict(json.loads(path.read_text(encoding="utf-8")))


def _as_dict(rows):
    return {str(k): str(v) for k, v in rows}


# --------------------------------------------------------------------------- #
# 1. 那幾列
# --------------------------------------------------------------------------- #
def test_it_answers_the_four_things_you_need_to_trace_a_report_back():
    got = _as_dict(run_info(_recipe(), source="D:/lots/LOT.001/defects.001",
                            n_rows=6000, n_source=6000, when=WHEN))
    assert got["Run at"] == "2026-09-20 14:33"
    assert got["Source"] == "D:/lots/LOT.001/defects.001"
    assert got["Defects"] == "6000"
    assert "ebi_die_to_die" in got["Recipe file"]
    # ⚠ **build id 是公司機唯一答得出「我這台跑的是哪一版」的東西**（那台沒
    # 有 git）。少了它，一份報表對不回任何一份程式碼。
    assert got["Made with"] == version_line()
    assert "build" in got["Made with"]


def test_a_partial_run_says_so():
    """**這是這個工具最容易誤導人的地方。**

    一份只跑了 60 顆的報表，看起來跟跑完 6 萬顆的一模一樣 —— 而使用者拿它
    去講「這個 lot 的情況」。所以顆數不是一個數字，是一句話。
    """
    got = _as_dict(run_info(n_rows=60, n_source=6000, when=WHEN))
    assert got["Defects"] == "60 of 6000 (not the whole lot)"
    # 跑完整批就只是一個數字 —— 每一份都掛一句「not the whole lot」的話，
    # 那句話就沒有人看了。
    assert _as_dict(run_info(n_rows=60, n_source=60, when=WHEN))["Defects"] \
        == "60"


def test_what_it_cannot_answer_it_leaves_out():
    """⚠ **算不出來的那一列不寫**（不是空字串、不是 ``unknown``）。

    一列寫著 ``Source: unknown`` 比沒有那一列更像「我知道，只是弄丟了」。
    同 CLAUDE.md §3 的「算不出來的那一格不寫」。
    """
    got = _as_dict(run_info(when=WHEN))
    assert "Source" not in got and "Defects" not in got
    assert "Recipe file" not in got
    # 剩下這兩件**永遠答得出來**，所以它們永遠在。
    assert "Run at" in got and "Made with" in got


def test_the_labels_are_declared_in_one_place():
    """名字有一份清單，因為 HTML 與 xlsx 兩邊都要指得到同一列。"""
    got = _as_dict(run_info(_recipe(), source="x", n_rows=1, n_source=1,
                            when=WHEN))
    assert set(got) == set(RUN_INFO_LABELS)


# --------------------------------------------------------------------------- #
# 2. HTML 那一份真的印出來
# --------------------------------------------------------------------------- #
def _html(info):
    rows = [{"defect_id": "1", "ok": True, "score": 1.0, "bin": 0,
             "features": {}}]
    return build_report(rows, "Bridge check", [], info=info)


def test_the_html_report_prints_it_at_the_top():
    html = _html(run_info(_recipe(), source="D:/lots/LOT.001/defects.001",
                          n_rows=1, n_source=6000, when=WHEN))
    block = html[html.index("<dl class='run'>"):html.index("</dl>")]
    for label in RUN_INFO_LABELS:
        assert "<dt>%s</dt>" % label in block, label
    assert "not the whole lot" in block
    # **在第 1 段判定之前** —— 追溯資訊是讀者的第一個問題，不是附註。
    assert html.index("<dl class='run'>") < html.index("<h2>")


def test_no_run_info_means_no_empty_block():
    """沒給就**完全不產生那些節點** —— 一個空的 ``<dl>`` 在畫面上是一道空白。

    同 `_thumb_cell` 那條規矩（F33）：沒有東西的時候不要留一個空殼。
    """
    assert "<dl class='run'>" not in _html(())


def test_the_values_are_escaped():
    """來源路徑是**外面來的字**（使用者挑的檔案），所以它要跳脫。

    一個叫 ``<script>`` 的資料夾不該變成報表裡的一段 JS。
    """
    html = _html([("Source", "D:/lots/<script>alert(1)</script>")])
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
