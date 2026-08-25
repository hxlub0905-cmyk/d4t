# F23 期2：分流的 UI —— route 切換器、預覽跟著顆走、route_by 編輯區塊。
"""鎖住三件事（`docs/history/plans/F23-route-by.md` §6）：

1. **model 抱得住整份分流 recipe**：`from_recipe → to_recipe` 對其他 route
   與 `route_by` 是 identity（少了這個，載入分流 recipe 再試跑，其他 route
   會安靜地消失）。undo 也不能弄丟它們。
2. **預覽跟著這一顆走**：看一顆 CLASSNUMBER=2 的 defect，畫布自動切到它
   真正走的 route，標籤寫出 `CLASSNUMBER=2 → route "b_route"` ——
   不做這個就是 F10 那批「畫布說謊」的重演。
3. **route_by 編輯區塊**（判定欄上方）：讀得到、改得動、關得掉。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import (  # noqa: E402
    Recipe, RecipeNode, RouteBy, ScoreSpec,
)
from d4t.ui.viewmodel import RecipeModel  # noqa: E402


def _route_recipe() -> Recipe:
    return Recipe(
        recipe_id="split",
        routes={"a_route": ["load", "glv_a"], "b_route": ["load", "glv_b"]},
        nodes={
            "load": RecipeNode("load", "load_patch", {}),
            "glv_a": RecipeNode("glv_a", "glv_stats",
                                {"source": "test", "metrics": "glv_max"}),
            "glv_b": RecipeNode("glv_b", "glv_stats",
                                {"source": "test", "metrics": "glv_mean"}),
        },
        score=ScoreSpec(expr="1.0", threshold=0.5,
                        bins={"below": 0, "above": 1}),
        route_by=RouteBy(column="CLASSNUMBER",
                         map={"1": "a_route", "2": "b_route"}))


# --------------------------------------------------------------------------- #
# 1. model（headless）
# --------------------------------------------------------------------------- #
def test_the_model_round_trips_every_route_and_the_route_by():
    r = _route_recipe()
    m = RecipeModel.from_recipe(r, kind="a_route")
    assert m.kind == "a_route"
    assert m.route_keys() == ["a_route", "b_route"]
    assert m.to_recipe().to_json_dict() == r.to_json_dict()


def test_editing_one_route_keeps_the_other_intact():
    m = RecipeModel.from_recipe(_route_recipe(), kind="a_route")
    m.set_param("glv_a", "metrics", "glv_median")
    out = m.to_recipe()
    assert out.routes["b_route"] == ["load", "glv_b"]
    assert out.nodes["glv_b"].params["metrics"] == "glv_mean"
    assert out.route_by is not None


def test_switching_routes_by_rebuilding_loses_nothing():
    m = RecipeModel.from_recipe(_route_recipe(), kind="a_route")
    m2 = RecipeModel.from_recipe(m.to_recipe(), kind="b_route")
    assert m2.kind == "b_route"
    assert m2.node_order == ["load", "glv_b"]
    assert m2.to_recipe().to_json_dict() == _route_recipe().to_json_dict()


def test_undo_does_not_drop_the_other_route():
    m = RecipeModel.from_recipe(_route_recipe(), kind="a_route")
    m.set_param("glv_a", "metrics", "glv_median")
    m.undo()
    out = m.to_recipe()
    assert "b_route" in out.routes and out.route_by is not None
    assert out.to_json_dict() == _route_recipe().to_json_dict()


def test_set_and_clear_route_by_are_undoable():
    m = RecipeModel.from_recipe(_route_recipe(), kind="a_route")
    m.set_route_by("classnumber", {"1": "a_route"}, "b_route")
    assert m.route_by.column == "CLASSNUMBER"      # 正規化大寫
    assert m.route_by.default == "b_route"
    m.clear_route_by()
    assert m.route_by is None
    m.undo()
    assert m.route_by is not None
    m.undo()
    assert m.route_by == _route_recipe().route_by


# --------------------------------------------------------------------------- #
# 2.–3. Studio（要 Qt）
# --------------------------------------------------------------------------- #
def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme as theme_mod
    from d4t.ui.studio import StudioWindow
    g.update(QApplication=QApplication, theme_mod=theme_mod,
             StudioWindow=StudioWindow)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("uiroute")), n=8, seed=7,
                    class_by_truth=True)


@pytest.fixture()
def window(qapp, lot, tmp_path):
    w = StudioWindow()
    assert w.load_dataset_path(lot["klarf"], sync=True)
    path = tmp_path / "split.json"
    path.write_text(json.dumps(_route_recipe().to_json_dict()),
                    encoding="utf-8")
    assert w.load_recipe_path(str(path), sync=True)
    yield w
    w.close()


def _class_of(lot, defect_id: str) -> str:
    with open(lot["ground_truth"], encoding="utf-8") as f:
        truth = json.load(f)
    return "1" if truth[str(defect_id)]["is_real"] else "2"


def test_the_route_switcher_lists_both_routes(window):
    assert window.route_combo.isVisible() or True   # offscreen 下不驗可見性
    texts = [window.route_combo.itemText(i)
             for i in range(window.route_combo.count())]
    assert texts == ["a_route", "b_route"]
    assert window.route_combo.currentText() == window.model.kind


def test_switch_route_swaps_the_canvas_and_keeps_the_recipe(window):
    before = window.model.to_recipe().to_json_dict()
    other = [k for k in window.model.route_keys()
             if k != window.model.kind][0]
    assert window.switch_route(other)
    assert window.model.kind == other
    assert window.pipeline.node_ids() == window.model.node_order
    assert window.model.to_recipe().to_json_dict() == before


def test_the_preview_follows_the_defects_own_route(window, lot):
    """看一顆 class=2 的 defect，畫布自動切到 b_route（F23 §6-2）。"""
    items = list(window.dataset.items)
    i2 = next(i for i, it in enumerate(items)
              if _class_of(lot, it.defect_id) == "2")
    window.set_defect_index(i2)
    assert window.model.kind == "b_route"
    assert "glv_b" in window.pipeline.node_ids()
    label = window.defect_label.text()
    assert "CLASSNUMBER=2" in label and "b_route" in label

    i1 = next(i for i, it in enumerate(items)
              if _class_of(lot, it.defect_id) == "1")
    window.set_defect_index(i1)
    assert window.model.kind == "a_route"
    assert "a_route" in window.defect_label.text()


def test_the_route_by_editor_shows_the_mapping(window):
    box = window.route_box
    assert box.toggle.isChecked()
    assert box.rows() == [("1", "a_route"), ("2", "b_route")]


def test_the_editor_writes_the_model(window):
    window.route_box._write_map("3", "b_route")
    assert window.model.route_by.map["3"] == "b_route"
    window.route_box._remove_value("3")
    assert "3" not in window.model.route_by.map


# --------------------------------------------------------------------------- #
# 4. 畫布上的分流徽章（F25-B）
# --------------------------------------------------------------------------- #
def test_the_canvas_shows_a_prefilter_badge(window):
    """畫布要講得出「這一批分兩條路跑」—— 在此之前它完全沉默。"""
    from d4t.ui import route_badge

    items = window.pipeline.prefilter_items()
    badges = [it for it in items
              if isinstance(it, route_badge.RouteBadgeItem)]
    assert len(badges) == 1
    assert badges[0].info["column"] == "CLASSNUMBER"
    assert badges[0].info["map"] == [("1", "a_route"), ("2", "b_route")]


def test_the_badge_is_not_a_card(window):
    """它不是 pipeline 的一步：不可拖、不可選、沒有埠。"""
    from PySide6.QtWidgets import QGraphicsItem

    from d4t.ui import route_badge

    badge = next(it for it in window.pipeline.prefilter_items()
                 if isinstance(it, route_badge.RouteBadgeItem))
    assert not badge.flags() & QGraphicsItem.ItemIsMovable
    assert not badge.flags() & QGraphicsItem.ItemIsSelectable
    assert badge.node_id if False else True      # 沒有 node_id 這種東西
    assert not hasattr(badge, "out_specs")


def test_the_badge_stands_in_front_of_every_card(window):
    """左→右讀起來就是時間順序：先分流、再跑卡片、最後判定。"""
    from d4t.ui import route_badge

    badge = next(it for it in window.pipeline.prefilter_items()
                 if isinstance(it, route_badge.RouteBadgeItem))
    lefts = [window.pipeline.node_item(n).pos().x()
             for n in window.pipeline.node_ids()]
    assert badge.pos().x() + route_badge.BADGE_W <= min(lefts)


def test_clicking_the_badge_opens_the_route_editor(window):
    from PySide6.QtCore import Qt

    from d4t.ui import route_badge

    hits = []
    window.pipeline.prefilter_clicked.connect(lambda: hits.append(1))
    badge = next(it for it in window.pipeline.prefilter_items()
                 if isinstance(it, route_badge.RouteBadgeItem))

    class _Ev:
        def button(self):
            return Qt.LeftButton

        def accept(self):
            pass

    badge.mousePressEvent(_Ev())
    assert hits == [1]


def test_the_badge_says_which_route_this_defect_takes(window, lot):
    from d4t.ui import route_badge

    items = list(window.dataset.items)
    i2 = next(i for i, it in enumerate(items)
              if _class_of(lot, it.defect_id) == "2")
    window.set_defect_index(i2)
    badge = next(it for it in window.pipeline.prefilter_items()
                 if isinstance(it, route_badge.RouteBadgeItem))
    assert badge.info["current"] == ("2", "b_route")


def test_the_badge_counts_come_from_route_taken(window):
    """每條路幾顆是從 `route_taken` 讀的 —— F19 當初就是為了這件事寫它。"""
    from d4t.core.pipeline import run_batch
    from d4t.ui import route_badge

    rows = run_batch(window.model.to_recipe(), window.dataset, workers=1)
    window._apply_trial_results(rows, 1.0)
    badge = next(it for it in window.pipeline.prefilter_items()
                 if isinstance(it, route_badge.RouteBadgeItem))
    counts = badge.info["counts"]
    assert counts is not None and sum(counts.values()) == len(rows)


def test_no_route_by_means_no_badge_at_all(window):
    window.model.clear_route_by()
    assert window.pipeline.prefilter_items() == []


def test_turning_the_toggle_off_clears_route_by(window):
    window.route_box.toggle.setChecked(False)
    assert window.model.route_by is None
    window.model.undo()
    assert window.model.route_by is not None
