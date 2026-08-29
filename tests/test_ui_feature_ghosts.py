# F50：淡線 —— 用名字吃的數字，來源看得見（2026-08-28）。
"""**「如果不一致，會有兩套準則，真正的使用者反而不知道怎麼用。」**

畫布上影像與具名區域走線，**特徵走名字** —— 那是系統刻意的分法（`route_by`
以外，Output 那三張卡的 `rank_by` / `size_feature` / `columns` 與判定樹的每
一個問題都是名字）。使用者不要那個不一致。

F49 量過「讓特徵真的變成邊」的代價（撞名與救援機制、recipe 格式遷移、70 處
引用），結論是先不付。這一輪付的是**便宜的那一半**：把來源**畫出來**，但它
是**視圖不是邊**。

四條規矩，每一條都是一個具體的謊言不准出現：

1. **它不是一條邊** —— 不進 `recipe.edges`、不影響執行順序、不進快取簽章；
2. **判定與卡片走同一支** —— 兩份會漂，而漂掉的那一份會讓畫布說謊；
3. **來源從宣告推**，不是猜名字（卡片宣告會寫出那個數字，線才畫得出來）；
4. **滑鼠移開就清乾淨**（含被點亮的來源卡 —— 它們不是 `_hover_node`）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from d4t.ui import studio as studio_mod, theme as theme_mod  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def wired(qapp):
    """一份「量灰階 → 出報表照 glv_median 排序」的 recipe。"""
    w = studio_mod.StudioWindow(show_welcome_on_start=False)
    w.model.add_step("load_patch")
    glv = w.model.add_step("glv_stats")
    rep = w.model.add_step("output_report")
    w.model.set_param(rep, "rank_by", "glv_median")
    w._refresh_pipeline()
    try:
        yield w, glv, rep
    finally:
        w.close()


def _item(w, nid):
    return w.pipeline._items[nid]


# --------------------------------------------------------------------------- #
# 1. 畫得出來，而且指對地方
# --------------------------------------------------------------------------- #
def test_an_output_card_shows_where_its_number_comes_from(wired):
    w, glv, rep = wired
    view = w.pipeline
    assert _item(w, rep).info.get("feature_reads") == ["glv_median"]

    view.show_card_ghosts(_item(w, rep))
    assert len(view.ghost_items()) == 1
    # **來源卡要真的亮起來** —— 一條線指著一張沒有反應的卡，使用者得自己
    # 沿著線看到底是哪一張。
    assert _item(w, glv)._hover is True


def test_a_card_that_reads_no_numbers_draws_nothing(wired):
    w, glv, _rep = wired
    view = w.pipeline
    view.show_card_ghosts(_item(w, glv))
    assert view.ghost_items() == []


def test_the_source_comes_from_the_declaration_not_a_guess(wired):
    """指到一個沒人算得出來的名字 → **一條線都不畫**。

    畫一條指向「不知道哪裡」的線，比不畫更糟：使用者會以為那個數字有來源。
    """
    w, _glv, rep = wired
    view = w.pipeline
    w.model.set_param(rep, "rank_by", "nosuch_number")
    w._refresh_pipeline()
    view.show_card_ghosts(_item(w, rep))
    assert view.ghost_items() == []


# --------------------------------------------------------------------------- #
# 2. 它不是一條邊
# --------------------------------------------------------------------------- #
def test_the_ghost_is_a_view_not_an_edge(wired):
    """**唯一的真相是那張卡的參數，這條線是它的投影。**

    ⚠ F42 B4 拆掉過一條推導出來的線（`region_lines()`），理由是「兩份相加、
    每條線被畫了兩次」—— 那裡有兩個出處，這裡只有一個。這一條把那個差別
    釘住，不然下一個人會照 F42 的結論把它清掉。
    """
    w, _glv, rep = wired
    view = w.pipeline
    before = list(w.model.edges)
    n_edges_drawn = len(view._edges)
    view.show_card_ghosts(_item(w, rep))
    assert view.ghost_items(), "前提：這時候真的有畫線"
    assert list(w.model.edges) == before, "淡線跑進 recipe.edges 了"
    # 畫布上**真的線**的條數也不准變 —— 淡線不是 `_EdgeItem`。
    assert len(view._edges) == n_edges_drawn


def test_it_does_not_change_the_recipe_on_disk(wired, tmp_path):
    """畫過淡線之後存檔，跟畫之前**逐位元組相同**。"""
    w, _glv, rep = wired
    before = json.dumps(w.model.to_recipe().to_json_dict(), sort_keys=True)
    w.pipeline.show_card_ghosts(_item(w, rep))
    after = json.dumps(w.model.to_recipe().to_json_dict(), sort_keys=True)
    assert after == before


# --------------------------------------------------------------------------- #
# 3. 判定與卡片走同一支
# --------------------------------------------------------------------------- #
def test_both_kinds_of_ghost_come_from_one_function():
    """兩份會漂，而漂掉的那一份會讓畫布說謊（這個 repo 記過三次）。"""
    src = (REPO / "d4t" / "ui" / "tree_scene.py").read_text(encoding="utf-8")
    assert "def ghost_wires(" in src
    body = src.split("def build_ghosts", 1)[1].split("\ndef ", 1)[0]
    assert "return ghost_wires(" in body, "菱形那一支自己又寫了一次"

    canvas_src = (REPO / "d4t" / "ui" / "canvas.py").read_text(encoding="utf-8")
    assert "tree_scene.ghost_wires(" in canvas_src


# --------------------------------------------------------------------------- #
# 4. 清得乾淨
# --------------------------------------------------------------------------- #
def test_leaving_clears_the_wires_and_the_lit_up_cards(wired):
    """被點亮的來源卡**不是** `_hover_node` —— 上面那條清不到它們。"""
    w, glv, rep = wired
    view = w.pipeline
    view.show_card_ghosts(_item(w, rep))
    assert view.ghost_items()
    view.clear_tree_ghosts()
    assert view.ghost_items() == []
    assert _item(w, glv)._hover is False, "來源卡還亮著"


# --------------------------------------------------------------------------- #
# 5. 最常見的那一條線（F51，2026-08-28）
# --------------------------------------------------------------------------- #
def test_ranking_a_report_by_the_score_draws_a_line_from_the_decision(qapp):
    """**「報表照分數排序」是整個工具最常見的一條連結，而它以前畫不出來。**

    兩個原因疊在一起，各修一個：

    * `ranked_feature` 刻意把 ``score`` 排除在 `optional_features_in` 外面
      —— 對 lint 是**對的**（`score` 不是任何一張卡算的，永遠不會缺），
      但畫線問的是「設定上寫著哪些名字」。→ 改走 `Step.feature_names_in`。
    * `feature_owners` 是第三份「誰產出這個特徵」的實作，而它不知道 ``score``。
      → 改成 `bound_specs` 的投影。
    """
    w = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert w.load_recipe_path(
            str(REPO / "tests" / "fixtures" / "recipes"
                / "die_to_die_basic.json"), sync=True)
        w.add_decision()
        rep = w.model.add_step("output_report")
        w.model.set_param(rep, "rank_by", "score")
        w._refresh_pipeline()

        assert _item(w, rep).info.get("feature_reads") == ["score"]
        assert "score" in w.model.feature_owners()
        w.pipeline.show_card_ghosts(_item(w, rep))
        assert len(w.pipeline.ghost_items()) == 1
    finally:
        w.close()


def test_a_rescued_name_still_finds_its_card(qapp):
    """撞名被救起來的那份（``glv_glv_max``）也要畫得出線。

    它是引擎真的寫進 CSV 的一個數字，而使用者拿它去 `rank_by` 是完全合理的
    ——「我要看**前面那張** GLV 卡量到的最大值」。
    """
    import json

    raw = json.loads((REPO / "tests" / "fixtures" / "recipes"
                      / "die_to_die_basic.json").read_text(encoding="utf-8"))
    raw["nodes"]["glv_2"] = dict(raw["nodes"]["glv"])
    raw["routes"]["ebi_patch"] = list(raw["routes"]["ebi_patch"]) + ["glv_2"]
    for e in list(raw.get("edges", [])):
        if e[2] == "glv":
            raw["edges"].append([e[0], e[1], "glv_2", e[3]])

    w = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        from d4t.core.pipeline.recipe import Recipe
        from d4t.ui.viewmodel import RecipeModel

        w.model = RecipeModel.from_recipe(Recipe.from_json_dict(raw),
                                          kind="ebi_patch")
        rescued = [n for n in w.model.feature_owners() if n.startswith("glv_glv")]
        assert rescued, "前提：這份 recipe 真的救起了一個名字"
        assert w.model.feature_owners()[rescued[0]] == "glv", \
            "救起來的那份要掛在**被蓋掉**的那張卡上"
    finally:
        w.close()
