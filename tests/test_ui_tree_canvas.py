# F24 ②：判定樹上畫布（唯讀渲染）。
"""鎖住判定區的五條性質（`docs/plans/F24-decision-tree.md` §4、§10）：

1. **樹的形狀直接來自 DecideSpec**：`rules` 模式畫成等價鏈狀樹（樓梯 ——
   yes 往右、no 往下），`(anything else)` 那片葉子標得出來。
2. **分支流量守恆**：每個菱形 in = yes + no；根 = 跑成功的顆數。
3. **未試跑：一個數字都不畫**（不是 0 —— F18 的老規矩）。
4. **入口小卡永遠恰好一個**，點它發 `decision_clicked`（跳到判定編輯）。
5. 走二元 score 的 recipe **沒有判定區**（那條路的判定住在門檻滑桿）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

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
def _canvas():
    view = canvas_mod.PipelineCanvas(popout_button=False)
    view.set_nodes([{"node_id": "load", "step_key": "load_patch",
                     "label": "Load images", "enabled": True,
                     "writes": ["test"], "reads": [], "group": "input"}], [])
    return view


def _entries(view):
    return [it for it in view.decision_items()
            if isinstance(it, tree_mod._EntryItem)]


def _trays(view):
    return [it for it in view.decision_items()
            if isinstance(it, tree_mod._TrayItem)]


def test_the_zone_appears_with_exactly_one_entry_card(qapp):
    view = _canvas()
    assert view.decision_items() == []       # 還沒 set_decision
    view.set_decision(tree_mod.decision_info(_decide_rules(), [], None))
    assert len(_entries(view)) == 1
    assert len(_trays(view)) == 3            # big / mid / (anything else)
    diamonds = [it for it in view.decision_items()
                if isinstance(it, tree_mod._DiamondItem)]
    assert len(diamonds) == 2


def test_before_a_run_no_number_is_drawn(qapp):
    view = _canvas()
    view.set_decision(tree_mod.decision_info(_decide_rules(), [], None))
    assert _entries(view)[0]._n_in is None
    assert all(t.count is None for t in _trays(view))


def test_after_a_run_the_counts_arrive_and_conserve(qapp):
    view = _canvas()
    rows = _rows([10, 20, 40, 60, 80])
    view.set_decision(tree_mod.decision_info(_decide_rules(), rows, None))
    assert _entries(view)[0]._n_in == 5
    assert sorted(t.count for t in _trays(view)) == [1, 2, 2]


def test_binary_score_recipes_have_no_zone(qapp):
    view = _canvas()
    view.set_decision(tree_mod.decision_info(_decide_rules(), [], None))
    view.set_decision(None)
    assert view.decision_items() == []


def test_the_zone_survives_a_set_nodes_rebuild(qapp):
    """`set_nodes` 每次都 clear 整個 scene —— 判定區要用存著的 info 重生。"""
    view = _canvas()
    view.set_decision(tree_mod.decision_info(_decide_rules(), [], None))
    view.set_nodes([{"node_id": "load", "step_key": "load_patch",
                     "label": "Load images", "enabled": True,
                     "writes": ["test"], "reads": [], "group": "input"}], [])
    assert len(_entries(view)) == 1


def test_clicking_the_entry_card_jumps_to_the_decision(qapp):
    view = _canvas()
    view.set_decision(tree_mod.decision_info(_decide_rules(), [], None))
    hits = []
    view.decision_clicked.connect(lambda: hits.append(1))

    from PySide6.QtCore import Qt

    class _Ev:
        def button(self):
            return Qt.LeftButton

        def accept(self):
            pass

    _entries(view)[0].mousePressEvent(_Ev())
    assert hits == [1]


def test_double_click_collapses_the_tree_to_the_entry_card(qapp):
    """F24 §4：雙擊入口卡收合整棵樹（嫌佔位的出口）—— 再雙擊回來。"""
    view = _canvas()
    view.set_decision(tree_mod.decision_info(_decide_rules(), [], None))
    assert len(_trays(view)) == 3
    view.toggle_tree_collapsed()
    assert len(_entries(view)) == 1 and len(_trays(view)) == 0
    view.toggle_tree_collapsed()
    assert len(_trays(view)) == 3


def test_hovering_a_diamond_draws_ghost_wires_and_leaving_clears(qapp):
    """F24 ④：幽靈線是**臨時**的 —— 出現在 hover、消失在移開。"""
    view = _canvas()
    info = tree_mod.decision_info(_decide_rules(), [], None)
    info["feat_owner"] = {"contrast": "load"}     # contrast 由 load 卡「產出」
    view.set_decision(info)
    diamond = next(it for it in view.decision_items()
                   if isinstance(it, tree_mod._DiamondItem))
    view.show_tree_ghosts(diamond)
    assert len(view.ghost_items()) == 1
    assert view.node_item("load")._hover           # 來源卡亮起來
    view.clear_tree_ghosts()
    assert view.ghost_items() == []
    assert not view.node_item("load")._hover


def test_ghost_wires_point_at_the_entry_for_working_numbers(qapp):
    """`let` 的中間值沒有卡 —— 幽靈線指回入口小卡（Decision）。"""
    view = _canvas()
    info = tree_mod.decision_info(_decide_rules(), [], None)
    info["feat_owner"] = {"contrast": ""}          # 空字串 = let 中間值
    view.set_decision(info)
    diamond = next(it for it in view.decision_items()
                   if isinstance(it, tree_mod._DiamondItem))
    view.show_tree_ghosts(diamond)
    assert len(view.ghost_items()) == 1


def test_the_previewed_defects_path_lights_up_on_the_tree(qapp):
    """F24 §8：看某一顆時，它走過的分支在樹上亮起來。"""
    view = _canvas()
    view.set_decision(tree_mod.decision_info(_decide_rules(), [], None))
    view.set_tree_highlight("ny")
    hot = [it for it in view.decision_items()
           if isinstance(it, tree_mod._BranchItem) and it._hot]
    # 入口→根、根→n、n→ny —— 整條路三段。
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


def test_the_zone_sits_to_the_right_of_the_cards(qapp):
    """mockup 定稿：判定區在畫布右側 —— 不能壓在卡片上。"""
    view = _canvas()
    view.set_decision(tree_mod.decision_info(_decide_rules(), [], None))
    node = view.node_item("load")
    node_right = node.pos().x() + canvas_mod.NODE_W
    entry = _entries(view)[0]
    assert entry.pos().x() > node_right
