# 沒有分數的時候，「最值得看的前 N 顆」是什麼（F30，2026-08-25）。
"""**判定樹是一個分類器，多數樹沒有分數表達式。**

而 F30 之前 `engine._eval_decision` 在那種情況下寫 ``score = 0.0``。
每一顆同分的後果，一個比一個嚴重：

1. CSV 多一欄全是 0 的 ``score``；
2. 每一張疊圖左上角寫著 ``score=0.000``（讀起來像「這顆得 0 分」）；
3. **「照分數排序取前 N 顆」變成「檔案順序的前 N 顆」** —— 全部同分時
   `sorted` 是穩定的，所以它原封不動地回傳輸入順序。而
   `pick_overlay_results` 自己的說明寫著「檔案順序上的前 N 顆幾乎一定不是
   使用者想看的那幾顆」。

第 3 點是實跑 6000 顆的報表時看到的，而排序正是使用者要那份報表的理由。
修法有兩半：**沒有分數就是沒有**（不是 0），以及**排不出來要講出來**
（安靜地退回檔案順序才是那個 bug）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.export import overlay  # noqa: E402
from d4t.core.pipeline.step import REGISTRY  # noqa: E402


def rows(scores=None, strengths=None, n=4):
    out = []
    for i in range(n):
        r = {"defect_id": str(i), "ok": True, "features": {}}
        if scores is not None:
            r["score"] = scores[i]
        if strengths is not None:
            r["features"]["blob_strength"] = strengths[i]
        out.append(r)
    return out


def ids(picked):
    return [r["defect_id"] for r in picked]


# --------------------------------------------------------------------------- #
# 排序
# --------------------------------------------------------------------------- #
def test_a_real_score_still_ranks_the_same_way():
    """有分數的那條路**一個位元都不能變**。"""
    got = overlay.pick_overlay_results(rows(scores=[1.0, 9.0, 5.0, 3.0]), 3)
    assert ids(got) == ["1", "2", "3"]


def test_ranking_by_a_measured_number_instead():
    got = overlay.pick_overlay_results(
        rows(scores=[None] * 4, strengths=[1.0, 9.0, 5.0, 3.0]),
        3, "blob_strength")
    assert ids(got) == ["1", "2", "3"]


def test_nothing_to_rank_on_is_reported_not_hidden():
    """**這一條是那個 bug 的形狀。**

    回傳檔案順序本身不是錯的（總得回一個順序），錯的是**沒有人被告知**。
    """
    r = rows(scores=[None] * 4)
    assert ids(overlay.pick_overlay_results(r, 3)) == ["0", "1", "2"]
    assert overlay.rank_is_meaningless(r) is True
    assert overlay.rank_is_meaningless(rows(scores=[1.0, 2.0, 3.0, 4.0])) is False


def test_all_equal_scores_are_just_as_unrankable_as_none():
    """全部 0 分跟全部沒有分數，排出來的順序一模一樣 —— 那正是舊行為。

    ⚠ 這一條**不**要求 `rank_is_meaningless` 對「全部同分」回 True：
    使用者刻意讓每一顆同分是一件合法的事。它記的是「舊行為為什麼看不出來」。
    """
    zeros = rows(scores=[0.0] * 4)
    nones = rows(scores=[None] * 4)
    assert ids(overlay.pick_overlay_results(zeros, 3)) == \
        ids(overlay.pick_overlay_results(nones, 3))


def test_a_missing_feature_sinks_that_defect_to_the_bottom():
    r = rows(scores=[None] * 3, strengths=[1.0, 9.0, 5.0], n=3)
    del r[1]["features"]["blob_strength"]
    assert ids(overlay.pick_overlay_results(r, 3, "blob_strength")) == \
        ["2", "0", "1"]


def test_nan_is_not_a_number_you_can_rank_on():
    r = rows(scores=[float("nan")] * 3, n=3)
    assert overlay.rank_is_meaningless(r) is True
    assert overlay.rank_value(r[0]) is None


def test_rank_value_reads_the_top_level_score_but_a_feature_by_name():
    """``score`` 住在結果最上層，其他名字住在 ``features`` —— 兩個不同的地方。"""
    r = {"score": 7.0, "features": {"score": 99.0, "blob_strength": 2.0}}
    assert overlay.rank_value(r, "score") == 7.0
    assert overlay.rank_value(r, "blob_strength") == 2.0


# --------------------------------------------------------------------------- #
# 兩張出圖的卡
# --------------------------------------------------------------------------- #
def test_every_card_that_ranks_says_it_the_same_way_word_for_word():
    """同一句話在兩個地方長出兩種意思，是這個 repo 最常踩的形狀。

    ⚠ 配對換了（F37）：`output_image` 折進 `output_bundle` 之後，還在排序的
    是 `output_bundle` 與 `output_char`。**改成問 registry「誰有 rank_by」**
    而不是寫死兩個 key —— 第三張會排序的卡加進來時，這支測試自己就跟上了。
    """
    from d4t.core.steps.output import rank_by_spec

    shared = rank_by_spec()
    want = (shared.type, shared.default, shared.label, shared.help)
    found = []
    for key, cls in REGISTRY.items():
        spec = {p.name: p for p in cls.params}.get(shared.name)
        # ⚠ **只問 Output 段那幾張。** `pair_source` 上也有一格叫 `rank_by`，
        # 而它問的是完全不同的事（「第二份那個 lot 自己照哪一欄排名次」）——
        # 同一個參數名在兩個段落上是兩個概念，所以不能照名字掃整個 registry。
        if spec is None or not str(getattr(cls, "key", "")).startswith("output_"):
            continue
        found.append(key)
        assert (spec.type, spec.default, spec.label, spec.help) == want, (
            "%s 的 rank_by 跟共用的那一份不一樣" % key)
    assert len(found) >= 2, "至少該有兩張出圖卡在排序：%s" % found
    assert shared.default == overlay.RANK_BY_SCORE


def test_the_help_says_what_to_do_when_there_is_no_score():
    """推廣鐵則：使用者不會寫 code，那一格的說明要自己講得完。"""
    spec = {p.name: p for p in REGISTRY["output_report"].params}["rank_by"]
    assert "decision tree" in spec.help
    assert "file order" in spec.help


# --------------------------------------------------------------------------- #
# 畫面上「沒有分數」要長成空白，不是四個字母
# --------------------------------------------------------------------------- #
def test_the_gallery_caption_leaves_a_missing_score_blank():
    """`str(None)` 會在每一張縮圖的說明列上畫出 **``None``** 那四個字。

    判定樹是一個分類器 —— 沒有分數表達式的時候**每一格**都會是它。
    """
    pytest.importorskip("PySide6")
    from d4t.ui.gallery import _fmt_score, caption_lines_of
    assert _fmt_score(None) == ""
    top, sub = caption_lines_of({"defect_id": "7", "score": None, "bin": 2},
                                "score")
    assert "None" not in top and "None" not in sub
    # 有值的時候照常畫 —— 否則上面那句只證明了「這一格永遠是空的」
    assert _fmt_score(3.5) == "3.5"


def test_the_results_table_leaves_a_missing_score_blank():
    """表格那一邊本來就對（F19 的「留白，不是 0」）—— 鎖住它別退化。"""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from d4t.ui.results_table import ResultsTableModel

    QApplication.instance() or QApplication([])
    m = ResultsTableModel()
    m.set_results([{"defect_id": "1", "ok": True, "score": None, "bin": 2,
                    "features": {}}])
    col = m._columns.index("score")
    assert m.data(m.index(0, col), Qt.DisplayRole) == ""
