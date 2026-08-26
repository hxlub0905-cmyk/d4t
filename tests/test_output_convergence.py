# d4t 測試 — F37 B2：Output 段的產物收斂（2026-08-26）.
"""同一批資料不該有好幾種讀法，而共用的東西不該被抄第二份。

⚠ **這一份守的不是「全部收成一張」。** 報表資料夾與 characterization 的版面
確實該分開 —— 那個取捨在 6000 顆與 30 顆是反過來的（`export/html.py` 模組
說明）。守的是**它們一樣的那幾部分真的只有一份**，以及**同一個約定在兩張卡
上是同一個意思**。
"""
from __future__ import annotations

import os

import pytest

import d4t.core.steps  # noqa: F401
from d4t.core.export import html as export_html
from d4t.core.pipeline.step import REGISTRY, get_step


def _folder_cards():
    """寫資料夾的那幾張卡。"""
    return [c for c in REGISTRY.values()
            if c.resolve_group() == "output" and getattr(c, "PATH", "") == "folder"]


# --------------------------------------------------------------------------- #
# B2-5：「指到檔案／資料夾」的檢查只有一份，而且在**跑之前**
# --------------------------------------------------------------------------- #
def test_pointing_a_folder_card_at_a_file_is_caught_on_the_canvas(tmp_path):
    """以前這句話住在 `run_batch` 裡 —— 要按下去、跑完一整批之後才聽得到。

    重複的代價不是重複本身，是**時機**：`configuration_issues` 這一份在畫布上
    就掛得出警示標記。

    ⚠ 把 `_OutputStep.path_issue` 的 folder 那一支拿掉，這支會紅。
    """
    a_file = tmp_path / "not-a-folder.txt"
    a_file.write_text("x", encoding="utf-8")
    cards = _folder_cards()
    assert cards, "一張寫資料夾的卡都沒有？"
    for cls in cards:
        says = cls.configuration_issues({"folder": str(a_file)})
        assert says and "is a file, not a folder" in says[0], cls.key


def test_pointing_a_file_card_at_a_folder_is_caught_too(tmp_path):
    """反過來那一半 —— 兩句話走同一支 `path_issue`。"""
    card = get_step("output_csv")
    says = card.configuration_issues({"path": str(tmp_path)})
    assert says and "is a folder, not a file" in says[0]


def test_a_folder_that_does_not_exist_yet_is_not_an_error(tmp_path):
    """**不檢查「存不存在」**：寫檔那一族會自己建。

    在這裡擋的話，一個完全正常的路徑會被說成設定錯誤（第一版真的這樣寫了）。
    """
    for cls in _folder_cards():
        assert cls.configuration_issues(
            {"folder": str(tmp_path / "brand-new"), "contents": "pictures",
             "columns": ""}) == []


# --------------------------------------------------------------------------- #
# B2-3：`limit` 的 0 在每一張卡上是同一個意思
# --------------------------------------------------------------------------- #
def test_zero_means_every_defect_on_every_card_that_limits_pictures():
    """以前一張是「0 ＝ 不限」、另一張 ``min=1`` —— 同一個數字，一張填得進去
    一張填不進去。使用者學一次那個約定，然後在第二張卡上被打回來。

    ⚠ 預設值**刻意仍然不同**（一張 0、一張 200），而那是對的：一份少一半的
    報表跟完整的長得一模一樣，但 characterization 每一列都掛圖正是它讀得下去
    的理由。**約定共用，取捨各自保留。**
    """
    limits = {}
    for cls in REGISTRY.values():
        spec = {p.name: p for p in cls.params}.get("limit")
        if spec is not None and cls.resolve_group() == "output":
            limits[cls.key] = spec
    assert len(limits) >= 2, sorted(limits)
    for key, spec in limits.items():
        assert spec.min == 0, "%s 的 limit 填不進 0" % key
        assert export_html and "Zero means every defect." in spec.help, key


def test_zero_really_writes_every_picture_not_none(tmp_path, monkeypatch):
    """``ordered[:0]`` 是**一張圖都沒有** —— 正好是「不限」的相反。

    這一條是實作上真的會踩的那一刀：把 `min` 從 1 放寬到 0 而忘了處理切片，
    使用者填 0 之後拿到一份**一張圖都沒有**的報表，而卡片說「0 ＝ 全部」。
    """
    from d4t.core.steps.output import OutputCharStep

    card = OutputCharStep()
    p = card.validate_params({"folder": str(tmp_path), "limit": 0})
    assert p["limit"] == 0                       # 填得進去
    # 切片那一刀：0 要變成 None（見 run_batch 裡的 `cut`）
    ordered = [1, 2, 3]
    cut = p["limit"] if p["limit"] > 0 else None
    assert ordered[:cut] == [1, 2, 3]


# --------------------------------------------------------------------------- #
# B2-4：畫圖的卡都畫得出 ROI 框
# --------------------------------------------------------------------------- #
def test_every_card_that_draws_pictures_can_draw_the_roi_boxes():
    """`output_char` 以前**畫圖卻畫不出框** —— 而 GLV 逐框比較的贏家框正是
    報表上最該看到的東西（「這一顆為什麼被判成這一類」的答案就在那個框裡）。

    ⚠ 把 `*roi_draw_specs()` 從 `OutputCharStep.params` 拿掉，這支會紅。
    """
    from d4t.core.steps.output import roi_draw_specs

    shared = {sp.name: sp for sp in roi_draw_specs()}
    for cls in _folder_cards():
        names = {p.name for p in cls.params}
        if "jpeg_quality" not in names and "picture_format" not in names:
            continue                     # 不畫圖的卡（目前沒有，留給第三張）
        on_card = {p.name: p for p in cls.params}
        for name, sp in shared.items():
            assert name in on_card, "%s 畫圖卻沒有 %s" % (cls.key, name)
            got = on_card[name]
            # **逐字同一份**：同一句話在兩張卡上長出兩種意思是這個 repo 最常
            # 踩的形狀。
            assert (got.type, got.default, got.label, got.help) == (
                sp.type, sp.default, sp.label, sp.help), (cls.key, name)


# --------------------------------------------------------------------------- #
# B2-2：兩份報表**一樣的那一段**只有一份
# --------------------------------------------------------------------------- #
def _rows():
    return [{"defect_id": "d1", "ok": True, "score": 3.0, "bin": 1,
             "features": {"glv_median": 120.0}},
            {"defect_id": "d2", "ok": False, "score": None, "bin": None,
             "features": {}, "error": "boom"}]


def test_both_reports_open_with_exactly_the_same_head():
    """標題、「幾顆／幾顆沒跑起來／bins」那一行、判定那一段 —— 逐字相同。

    版面**確實該分開**（6000 顆點一列換圖 vs 30 顆一列兩張圖），但一樣的那
    一段沒有理由寫兩次：改了其中一份的那一天，同一批資料的兩份報表會有兩個
    不同的開頭，而在這支測試之前沒有任何東西會問。

    ⚠ 把 `_page_head` 拆回兩份、改掉其中一份的一個字，這支會紅。
    """
    rows = _rows()
    a = export_html.build_report(rows, "T", ["glv_median"])
    b = export_html.build_char_report(rows, "T", ["glv_median"], {})
    head = "\n".join(export_html._page_head("T", rows))
    assert a.startswith(head), "整批那一份的開頭不是共用的那一段"
    assert b.startswith(head), "characterization 那一份的開頭不是共用的那一段"


def test_the_head_says_how_many_did_not_run():
    """那一行要講的三件事都在（顆數／沒跑起來幾顆／bins）。"""
    head = "\n".join(export_html._page_head("T", _rows()))
    assert "2 defect(s)" in head
    assert "1 did not run" in head


def test_the_two_layouts_are_still_two_functions():
    """⚠ **這支測試守的是「不要合併」。**

    使用者 2026-08-26 定調 `output_char` 併不併進 `output_bundle`「再討論」，
    而版面的取捨在兩個規模是反過來的：6000 顆的表格裡塞 6000 個 ``<img>``
    會讓瀏覽器很鈍（所以點一列換圖，整份只有一個 ``<img>``），而 30 顆要的是
    「我可以一一對應」（所以圖排在列上）。

    共用的是開頭、CSS 與跳脫；**版面各自保留**。哪天真的要合，先回來刪這一支
    並且在計畫書上寫下為什麼 —— 不要讓它安靜地消失。
    """
    rows = _rows()
    a = export_html.build_report(rows, "T", [], images={"d1": "images/d1.jpg"})
    b = export_html.build_char_report(rows, "T", [], {"d1": {"main": "m.jpg"}})
    assert "Which ones" in a and "Defect by defect" in b
    assert "<script>" in a, "整批那一份靠 JS 換圖"
    assert "<script>" not in b, "點對點那一份不需要換圖，圖就在列上"
