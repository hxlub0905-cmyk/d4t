# F24 ②：判定樹上畫布（唯讀渲染）。
"""鎖住判定區的五條性質（`docs/history/plans/F24-decision-tree.md` §4、§10）：

1. **樹的形狀直接來自 DecideSpec**：`rules` 模式畫成等價鏈狀樹（樓梯 ——
   yes 往右、no 往下），`(anything else)` 那片葉子標得出來。
2. **分支流量守恆**：每個菱形 in = yes + no；根 = 跑成功的顆數。
3. **未試跑：一個數字都不畫**（不是 0 —— F18 的老規矩）。
4. **樹掛在 Decision 卡底下**（F123 期 1）：一條線從卡的下緣接到根、樹排在
   所有卡片的下面、拖那張卡樹跟著走。以前的淡紫虛線框與入口小卡拿掉了。
5. 沒有判定的 recipe **畫布上沒有樹**。
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Let, Rule, TreeLeaf, TreeStep,
)


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import canvas as canvas_mod
    from d4t.ui import theme as theme_mod
    from d4t.ui import tree_scene as tree_mod
    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
             theme_mod=theme_mod, tree_mod=tree_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


def _decide_rules():
    return DecideSpec(
        let=[Let(name="contrast", expr="a * 2")],
        rules=[Rule(when="contrast > 100", bin=3, label="big"),
               Rule(when="contrast > 30", bin=2, label="mid")],
        otherwise_bin=0, otherwise_label="", score="contrast")


def _decide_tree():
    return DecideSpec(
        let=[],
        tree=TreeStep(when="a > 5",
                      yes=TreeLeaf(bin=1, label="real"),
                      no=TreeLeaf(bin=0, label="nuisance")),
        score="")


def _rows(values, ok=True):
    return [{"defect_id": str(i + 1), "ok": ok,
             "bin": (0 if ok else None), "score": 0.0,
             "features": {"a": float(v), "contrast": float(v) * 2}}
            for i, v in enumerate(values)]


# --------------------------------------------------------------------------- #
# 純資料（不用開視窗）
# --------------------------------------------------------------------------- #
def test_rules_render_as_a_staircase(qapp):
    cells = tree_mod.layout_cells(tree_mod.display_tree(_decide_rules()),
                                  _decide_rules())
    at = {c["path"]: c for c in cells}
    # 樓梯：每一步右邊一個托盤、往下一步。
    assert (at[""]["col"], at[""]["row"]) == (0, 0)
    assert at[""]["kind"] == "step"
    assert (at["y"]["col"], at["y"]["row"]) == (1, 0)
    assert (at["n"]["col"], at["n"]["row"]) == (0, 1)
    assert (at["ny"]["col"], at["ny"]["row"]) == (1, 1)
    assert (at["nn"]["col"], at["nn"]["row"]) == (0, 2)
    # 「其他都掉進這裡」那一片標得出來，而且只有它。
    assert at["nn"]["otherwise"] and at["nn"]["kind"] == "leaf"
    assert not at["y"]["otherwise"] and not at["ny"]["otherwise"]


def test_a_hand_written_tree_has_no_otherwise_leaf(qapp):
    cells = tree_mod.layout_cells(tree_mod.display_tree(_decide_tree()),
                                  _decide_tree())
    assert not any(c.get("otherwise") for c in cells)


def test_flow_counts_conserve_at_every_step(qapp):
    tree = tree_mod.display_tree(_decide_rules())
    rows = _rows([10, 20, 40, 60, 80])       # contrast: 20 40 80 120 160
    counts = tree_mod.flow_counts(tree, rows)
    assert counts[""] == 5
    assert counts[""] == counts["y"] + counts["n"]
    assert counts["n"] == counts["ny"] + counts["nn"]
    assert counts["y"] == 2                  # contrast > 100：120 與 160
    assert counts["ny"] == 2                 # 40 與 80
    assert counts["nn"] == 1                 # 20


def test_failed_defects_are_not_counted(qapp):
    tree = tree_mod.display_tree(_decide_tree())
    rows = _rows([1, 10]) + _rows([99], ok=False)
    assert tree_mod.flow_counts(tree, rows)[""] == 2


def test_leaf_stats_need_ground_truth(qapp):
    tree = tree_mod.display_tree(_decide_tree())
    rows = _rows([1, 10, 20])
    assert tree_mod.leaf_stats(tree, rows, None) == {}
    gt = {"1": {"is_real": False}, "2": {"is_real": True},
          "3": {"is_real": True}}
    stats = tree_mod.leaf_stats(tree, rows, gt)
    assert stats["y"] == (2, 2)              # a=10 與 20 走 yes，兩顆都是真的
    assert stats["n"] == (0, 1)


def test_decision_info_is_none_without_a_decide_block(qapp):
    assert tree_mod.decision_info(None, [], None) is None


def test_decision_info_has_no_counts_before_a_run(qapp):
    info = tree_mod.decision_info(_decide_rules(), [], None)
    assert info is not None and info["counts"] is None
    info2 = tree_mod.decision_info(_decide_rules(), _rows([10]), None)
    assert info2["counts"] is not None


# --------------------------------------------------------------------------- #
# 畫布
# --------------------------------------------------------------------------- #
_LOAD = {"node_id": "load", "step_key": "load_patch", "label": "Load images",
         "enabled": True, "writes": ["test"], "reads": [], "group": "input"}
_CARD = {"node_id": "decision", "step_key": "decision", "label": "Decision",
         "enabled": True, "writes": [], "reads": [], "group": "adc"}


def _canvas(collapsed: bool = False, with_card: bool = True):
    """一份畫布：Input 卡＋Decision 卡。**預設把樹展開**（`collapsed=False`）——

    ⚠ 2026-08-28（F50）起判定樹**開窗是收起來的**
    （`canvas.TREE_COLLAPSED_DEFAULT`，使用者：「ADC 他一樣是張卡片，
    可以，但把它點開可以看到 decision tree」）。下面那幾條問的是**樹裡面**
    有什麼（菱形、托盤、顆數、幽靈線、走過的路），所以它們要先點開 ——
    收起來的時候那些東西本來就不該存在。

    「預設是收起來的」本身由 `test_the_tree_starts_collapsed` 守著。
    """
    view = canvas_mod.PipelineCanvas(popout_button=False)
    view._tree_collapsed = bool(collapsed)
    view.set_nodes([_LOAD] + ([_CARD] if with_card else []), [])
    return view


def _info(decide=None, rows=(), owners=None):
    info = tree_mod.decision_info(decide or _decide_rules(), list(rows), None)
    info["node"] = "decision"
    if owners is not None:
        info["feat_owner"] = owners
    return info


def _trays(view):
    return [it for it in view.decision_items()
            if isinstance(it, tree_mod._TrayItem)]


def _root_wire(view):
    """從 Decision 卡接到根的那一條（沒有就 None）。"""
    card = view.node_item("decision")
    if card is None:
        return None
    a = card.pos() + QPointF(canvas_mod.NODE_W / 2.0, card.height())
    return next((it for it in view.decision_items()
                 if isinstance(it, tree_mod._BranchItem) and it._a == a), None)


def _import_qpointf(g):
    from PySide6.QtCore import QPointF
    g["QPointF"] = QPointF


def test_the_tree_hangs_under_the_decision_card(qapp):
    _import_qpointf(globals())
    view = _canvas()
    assert view.decision_items() == []       # 還沒 set_decision
    view.set_decision(_info())
    assert len(_trays(view)) == 3            # big / mid / (anything else)
    diamonds = [it for it in view.decision_items()
                if isinstance(it, tree_mod._DiamondItem)]
    assert len(diamonds) == 2
    assert _root_wire(view) is not None, "Decision 卡到根沒有那一條線"
    # 虛線框與入口小卡拿掉了（F123 期 1）：判定在畫布上就是那一張卡。
    assert not hasattr(tree_mod, "_ZoneItem")
    assert not hasattr(tree_mod, "_EntryItem")


def test_before_a_run_no_number_is_drawn(qapp):
    _import_qpointf(globals())
    view = _canvas()
    view.set_decision(_info())
    assert _root_wire(view)._count is None
    assert all(t.count is None for t in _trays(view))


def test_after_a_run_the_counts_arrive_and_conserve(qapp):
    _import_qpointf(globals())
    view = _canvas()
    view.set_decision(_info(rows=_rows([10, 20, 40, 60, 80])))
    assert _root_wire(view)._count == 5
    assert sorted(t.count for t in _trays(view)) == [1, 2, 2]


def test_no_decision_no_tree(qapp):
    view = _canvas()
    view.set_decision(_info())
    view.set_decision(None)
    assert view.decision_items() == []


def test_the_tree_survives_a_set_nodes_rebuild(qapp):
    """`set_nodes` 每次都 clear 整個 scene —— 樹要用存著的 info 重生。"""
    _import_qpointf(globals())
    view = _canvas()
    view.set_decision(_info())
    view.set_nodes([_LOAD, _CARD], [])
    assert len(_trays(view)) == 3 and _root_wire(view) is not None


def test_the_tree_sits_below_every_card(qapp):
    """往右是 yes、往下是 no —— 排在所有卡片下面，就不會壓到任何一張卡。"""
    view = _canvas()
    view.set_decision(_info())
    bottom = max(view.node_item(n).pos().y() + view.node_item(n).height()
                 for n in ("load", "decision"))
    tops = [it.pos().y() for it in view.decision_items()
            if not isinstance(it, tree_mod._BranchItem)]
    assert tops and min(tops) > bottom


def test_dragging_the_card_takes_the_tree_along(qapp):
    """要動整棵樹就拖那張卡（以前的把手是虛線框）；相對位置一格都不變。"""
    _import_qpointf(globals())
    view = _canvas()
    view.set_decision(_info())
    before = [QPointF(it.pos()) for it in view.decision_items()]
    card = view.node_item("decision")
    card.setPos(card.pos() + QPointF(120.0, -40.0))
    after = [it.pos() for it in view.decision_items()]
    assert before and len(before) == len(after)
    for a, b in zip(before, after):
        assert b.x() - a.x() == pytest.approx(120.0)
        assert b.y() - a.y() == pytest.approx(-40.0)
    # 其他卡動了樹不動（它掛的是 Decision 那一張）。
    load = view.node_item("load")
    load.setPos(load.pos() + QPointF(0.0, 30.0))
    assert [it.pos() for it in view.decision_items()] == after


def test_without_a_decision_card_the_tree_still_stands(qapp):
    """手寫的 recipe 可以有 ``decide`` 而沒有那張卡：樹照畫，站在卡片右邊。"""
    view = _canvas(with_card=False)
    view.set_decision(_info())
    assert len(_trays(view)) == 3
    right = view.node_item("load").pos().x() + canvas_mod.NODE_W
    assert min(it.pos().x() for it in view.decision_items()
               if not isinstance(it, tree_mod._BranchItem)) > right
    assert _root_wire(view) is None      # 沒有卡，就沒有從卡接下來的線


def test_double_click_collapses_the_tree(qapp):
    """F24 §4：收合整棵樹（嫌佔位的出口）—— 再來一次回來。收著就一個圖元
    都沒有：Decision 卡本身就是它收起來的樣子。"""
    view = _canvas()
    view.set_decision(_info())
    assert len(_trays(view)) == 3
    view.toggle_tree_collapsed()
    assert view.decision_items() == []
    view.toggle_tree_collapsed()
    assert len(_trays(view)) == 3


def test_hovering_a_diamond_draws_ghost_wires_and_leaving_clears(qapp):
    """F24 ④：幽靈線是**臨時**的 —— 出現在 hover、消失在移開。"""
    view = _canvas()
    view.set_decision(_info(owners={"contrast": "load"}))  # contrast 由 load 卡「產出」
    diamond = next(it for it in view.decision_items()
                   if isinstance(it, tree_mod._DiamondItem))
    view.show_tree_ghosts(diamond)
    assert len(view.ghost_items()) == 1
    assert view.node_item("load")._hover           # 來源卡亮起來
    view.clear_tree_ghosts()
    assert view.ghost_items() == []
    assert not view.node_item("load")._hover


def test_ghost_wires_point_at_the_decision_card_for_working_numbers(qapp):
    """`let` 的中間值屬於 Decision 卡（`RecipeModel.feature_owners`）。"""
    view = _canvas()
    view.set_decision(_info(owners={"contrast": "decision"}))
    diamond = next(it for it in view.decision_items()
                   if isinstance(it, tree_mod._DiamondItem))
    view.show_tree_ghosts(diamond)
    assert len(view.ghost_items()) == 1
    assert view.node_item("decision")._hover


def test_the_previewed_defects_path_lights_up_on_the_tree(qapp):
    """F24 §8：看某一顆時，它走過的分支在樹上亮起來。"""
    view = _canvas()
    view.set_decision(_info())
    view.set_tree_highlight("ny")
    hot = [it for it in view.decision_items()
           if isinstance(it, tree_mod._BranchItem) and it._hot]
    # 卡→根、根→n、n→ny —— 整條路三段。
    assert len(hot) == 3
    view.set_tree_highlight(None)
    hot = [it for it in view.decision_items()
           if isinstance(it, tree_mod._BranchItem) and it._hot]
    assert hot == []


def test_path_text_reads_the_walk_back(qapp):
    tree = tree_mod.display_tree(_decide_rules())
    assert tree_mod.path_text(tree, "ny") == \
        "contrast > 100 ? no → contrast > 30 ? yes"
    assert tree_mod.path_text(tree, "yyy") == ""   # 走不完就不硬湊


def test_opening_a_threshold_recipe_puts_a_tree_on_the_canvas(qapp, tmp_path):
    """F25（使用者：「二元門檻的 UI 完全拿掉」）：舊 recipe 一打開，
    畫布上就是一棵樹 —— 而且**不算改過**（關窗不該問要不要存）。"""
    import json

    from d4t.core.pipeline import Recipe, RecipeNode, ScoreSpec
    from d4t.ui.studio import StudioWindow

    recipe = Recipe(
        recipe_id="old", routes={"ebi_patch": ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", {})},
        score=ScoreSpec(expr="glv_max", threshold=3.0,
                        bins={"below": 0, "above": 1}))
    path = tmp_path / "old.json"
    path.write_text(json.dumps(recipe.to_json_dict()), encoding="utf-8")

    w = StudioWindow()
    try:
        assert w.load_recipe_path(str(path), sync=True)
        assert w.model.decide is not None
        # F122 期 3：轉出來的就是引擎跑的那一棵（`legacy_decision`）——
        # 問的是分數，分數表達式是原本那一條。
        from d4t.core.pipeline.recipe_schema import legacy_decision
        assert w.model.decide == legacy_decision(recipe.score)
        assert w.model.tree_node("").when == "score >= 3"
        assert w.model.decide.score == "glv_max"
        nid = w.model.decision_node()
        assert nid and w.pipeline.node_item(nid) is not None, \
            "畫布上沒有 Decision 卡"
        assert not w.model.dirty, "只是打開一個檔案，不該算成使用者改過"
    finally:
        w.close()


# --------------------------------------------------------------------------- #
# 開窗是收起來的（F50，2026-08-28）
# --------------------------------------------------------------------------- #
def test_the_tree_starts_collapsed(qapp):
    """**畫布上一律是卡片，判定就是其中一張，要看細節才點開。**

    收合這個能力 F24 §4 就做好了，只是預設是展開 —— 於是畫布右邊常駐一整片
    菱形，而它跟左邊那一排卡片是兩種長得不一樣的東西。使用者 2026-08-28
    定調把預設翻過來。
    """
    view = canvas_mod.PipelineCanvas(popout_button=False)
    view.set_nodes([_LOAD, _CARD], [])
    assert view.tree_collapsed() is True
    view.set_decision(_info())
    assert view.node_item("decision") is not None, "收起來也要有那一張卡"
    assert view.decision_items() == [], "收起來卻畫了樹"


def test_it_opens_and_closes_again(qapp):
    """點開看得到樹，再點一次收回去 —— 一個手勢兩個方向。"""
    view = canvas_mod.PipelineCanvas(popout_button=False)
    view.set_nodes([_LOAD, _CARD], [])
    view.set_decision(_info())

    def diamonds():
        return [it for it in view.decision_items()
                if isinstance(it, tree_mod._DiamondItem)]

    assert not diamonds()
    view.toggle_tree_collapsed()
    assert view.tree_collapsed() is False and len(diamonds()) == 2
    view.toggle_tree_collapsed()
    assert view.tree_collapsed() is True and not diamonds()


def test_collapsing_is_a_view_state_not_recipe_content(qapp):
    """存檔存不到它，開檔也不會帶著它回來（同縮放平移）。

    這一條擋的是「順手把它存進 recipe」—— 那會讓兩台機器打開同一份檔案看到
    不一樣的畫面，而畫面狀態不是 recipe 的內容。
    """
    import ast
    import inspect

    from d4t.ui import canvas as cm

    # ⚠ **只看會執行的那幾行。** 第一版直接掃函式的原始碼，而它的 docstring
    # 裡就寫著「不進 recipe」—— 那一條抓到的是自己的說明。
    for method in (cm.PipelineCanvas.toggle_tree_collapsed,
                   cm.PipelineCanvas.set_tree_collapsed):
        tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
        fn = tree.body[0]
        if (fn.body and isinstance(fn.body[0], ast.Expr)
                and isinstance(fn.body[0].value, ast.Constant)):
            fn.body = fn.body[1:]                       # 丟掉 docstring
        code = ast.dump(ast.Module(body=fn.body, type_ignores=[]))
        for leak in ("recipe", "set_param", "to_json", "model"):
            assert leak not in code, leak


# --------------------------------------------------------------------------- #
# F122 期 3：問不出來的那一題在畫布上看得出來
# --------------------------------------------------------------------------- #
def test_a_question_nobody_can_answer_is_marked_on_the_canvas(qapp):
    """那一題用到一個沒有人產出的數字 → 每一顆都答「否」，而它以前在畫布上
    長得跟一題正常的問題一模一樣。「誰產出什麼」只問 `feature_owners` 那一份。"""
    view = _canvas()
    decide = DecideSpec(tree=TreeStep(
        when="a > 5",
        yes=TreeStep(when="CLASSNUMBER == 3",
                     yes=TreeLeaf(bin=2), no=TreeLeaf(bin=1)),
        no=TreeLeaf(bin=0)))
    view.set_decision(_info(decide, owners={"a": "load"}))
    diamonds = {it.when: it for it in view.decision_items()
                if isinstance(it, tree_mod._DiamondItem)}
    assert diamonds["a > 5"].missing == []
    assert diamonds["CLASSNUMBER == 3"].missing == ["CLASSNUMBER"]
    assert "answered 'no'" in diamonds["CLASSNUMBER == 3"].toolTip()
    assert "Carry these columns" in diamonds["CLASSNUMBER == 3"].toolTip()


def test_without_knowing_who_makes_what_nothing_is_marked(qapp):
    """**反向**：不知道（沒有 `feat_owner`）就不講 —— 講錯比不講糟。"""
    view = _canvas()
    view.set_decision(_info(_decide_tree()))
    assert all(it.missing == [] for it in view.decision_items()
               if isinstance(it, tree_mod._DiamondItem))
