"""CD 的 UI（F19 第 4 步）：影像上的量測標記 ＋ 卡片面板。

**一律讀 API，不讀畫素**（`summary()` / `mark_count()` / `metric_face()`）——
畫素比對在這個 repo 只用在「兩顆圖示長得一不一樣」那種地方。
"""
from __future__ import annotations

import numpy as np
import pytest

import d4t.core.steps  # noqa: F401 — registration side-effect
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import REGISTRY, get_step
from d4t.core.steps.cd import MAX_DRAWN_LINES, REPORT_CHOICES

from tests.test_algo_edge import line_block


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def measured(rows=40, **params):
    """跑一次 CD，回 ``(ctx, params)``。"""
    cls = REGISTRY["cd_measure"]
    p = cls.validate_params(params)
    ctx = Context(images={"test": line_block(rows=rows, width=12.0,
                                             blur=1.2).astype(np.float32)})
    return cls().run(ctx, p), p


# --------------------------------------------------------------------------- #
# 影像上的量測標記
# --------------------------------------------------------------------------- #
def test_the_card_hands_over_its_own_marks():
    """meta 的形狀是**那張卡的事** —— UI 不去猜它長什麼樣。"""
    ctx, p = measured()
    lines, points, focus = get_step("cd_measure").overlay_marks(ctx, p)
    assert len(lines) == len(points) > 0
    assert 0 <= focus < len(lines)
    for (x0, y0), (x1, y1) in lines:                 # 正規化座標
        assert 0.0 <= x0 <= 1.0 and 0.0 <= x1 <= 1.0
        assert 0.0 <= y0 <= 1.0 and y0 == y1
    for pair in points:
        assert len(pair) == 2 and pair[0][0] < pair[1][0]


def test_marks_are_thinned_but_the_represented_line_survives():
    """128 條疊在一張 128 px 的 patch 上是一片實心的網 —— 但代表那一條非留不可
    （面板上那張剖面圖畫的就是它，兩邊對不起來使用者就找不到）。"""
    ctx, p = measured(rows=120)
    lines, _points, focus = get_step("cd_measure").overlay_marks(ctx, p)
    assert len(lines) == MAX_DRAWN_LINES
    assert focus >= 0


def test_every_card_answers_the_marks_question():
    """預設什麼都不畫，所以既有的卡一張都不用動。"""
    ctx = Context(images={"test": np.zeros((8, 8), np.float32)})
    for key, cls in REGISTRY.items():
        lines, points, focus = cls.overlay_marks(ctx, {})
        assert list(lines) == [] and list(points) == [] and focus == -1, key


def test_image_view_draws_marks_and_guards_against_mismatch(qapp):
    from d4t.ui.widgets import ImageView

    view = ImageView()
    view.set_image(np.zeros((64, 64), np.uint8))
    assert view.mark_count() == 0
    view.set_marks([[(0.0, 0.2), (1.0, 0.2)]], [[(0.3, 0.2), (0.7, 0.2)]], 0)
    assert view.mark_count() == 1
    # 長度對不上就**整組不畫**：錯位的標記會指向錯的地方，而畫面上沒有任何
    # 東西透露那件事（同 `set_overlay` 的老規矩）。
    view.set_marks([[(0.0, 0.2), (1.0, 0.2)]],
                   [[(0.3, 0.2)], [(0.4, 0.3)]], 0)
    assert view.mark_count() == 1
    assert view._mark_points == []
    view.clear_marks()
    assert view.mark_count() == 0


def test_marks_survive_a_repaint(qapp):
    from PySide6.QtGui import QPixmap, QPainter
    from d4t.ui.widgets import ImageView

    view = ImageView()
    view.set_image(np.zeros((64, 64), np.uint8))
    view.resize(200, 200)
    view.set_marks([[(0.0, 0.2), (1.0, 0.2)]], [[(0.3, 0.2), (0.7, 0.2)]], 0)
    view.render(QPixmap(200, 200))         # 畫得出來不丟例外就夠
    assert view.mark_count() == 1


# --------------------------------------------------------------------------- #
# 面板
# --------------------------------------------------------------------------- #
def make_panel(qapp, ctx, params, batch=None):
    from d4t.ui.inspectors import inspector_for

    insp = inspector_for("cd_measure")()
    cls = REGISTRY["cd_measure"]
    insp.set_context("cd", params=params,
                     result={"features": dict(ctx.features)},
                     batch=batch or [], meta=dict(ctx.meta),
                     feature_names=list(cls.resolve_features(params)))
    return insp


def test_the_panel_has_something_before_you_run_a_batch(qapp):
    """跟 `GlvInspector` 同一條路：資料從 ``ctx.meta`` 來，所以**選到卡片的
    那一刻就有東西**，不是跑完一批才有。"""
    ctx, p = measured()
    insp = make_panel(qapp, ctx, p, batch=[])
    assert insp.has_data()
    said = insp.summary()
    assert "CD 12." in said and "sigma" in said and "40/40 lines" in said
    assert "threshold" in said


def test_the_panel_title_says_what_it_is_looking_at(qapp):
    ctx, p = measured()
    insp = make_panel(qapp, ctx, p)
    assert insp.tab_title() == "CD · whole image @ test"
    assert "threshold" in insp.tab_tooltip()


def test_the_panel_names_the_region_it_measured(qapp):
    cls = REGISTRY["cd_measure"]
    p = cls.validate_params({"roi": "band"})
    ctx = Context(images={"test": line_block(rows=64, width=12.0,
                                             blur=1.2).astype(np.float32)})
    ctx.set_roi("band", (0.0, 8 / 64.0, 1.0, 16 / 64.0))
    ctx = cls().run(ctx, p)
    insp = make_panel(qapp, ctx, p)
    assert insp.tab_title() == "CD · band @ test"


def test_the_panel_says_why_when_nothing_was_measured(qapp):
    """**失敗時那一行比任何圖都有用** —— 而它跟警告訊息用同一張對照表。"""
    cls = REGISTRY["cd_measure"]
    p = cls.validate_params({})
    block = line_block(rows=24, center=58.0, width=24.0, blur=1.2)
    ctx = cls().run(Context(images={"test": block.astype(np.float32)}), p)
    insp = make_panel(qapp, ctx, p)
    assert insp.has_data()
    said = insp.summary()
    assert "no width here" in said
    assert "ran past the edge" in said
    assert "0 of 24 lines" in said


def test_the_panel_draws_without_blowing_up(qapp):
    from PySide6.QtGui import QPixmap

    ctx, p = measured()
    batch = [{"features": {"cd_median": 11.0 + i * 0.1}} for i in range(30)]
    insp = make_panel(qapp, ctx, p, batch=batch)
    insp.resize(560, 190)
    insp.render(QPixmap(560, 190))


def test_a_panel_with_no_data_says_what_to_do(qapp):
    from d4t.ui.inspectors import inspector_for

    insp = inspector_for("cd_measure")()
    assert not insp.has_data()
    assert "Run a trial" in insp.empty_reason()


# --------------------------------------------------------------------------- #
# 膠囊：引擎說有哪些，UI 說長什麼樣
# --------------------------------------------------------------------------- #
def test_every_report_metric_the_cd_card_offers_has_a_face(qapp):
    """卡片多宣告一顆而 UI 沒登記，畫出來是一顆沒有分群、標籤是原始 id 的膠囊
    —— 跑得完、看得到、而且醜，也就是不會有人回報（同 F18 的規矩）。"""
    from d4t.ui import widgets as widgets_mod

    groups = set()
    for mid in REPORT_CHOICES:
        group, label, glyph = widgets_mod.metric_face(mid)
        assert group in widgets_mod.METRIC_GROUP_ORDER, mid
        assert group != "Other", "%s 沒有登記在 METRIC_GROUPS" % mid
        assert label and not label.startswith("cd_"), mid
        assert glyph in widgets_mod.METRIC_GLYPHS, mid
        groups.add(group)
    # **粗糙度那一群要分得出來** —— 它只有在量測線夠多時才有意義，而那是
    # 「為什麼我的 LER 是 0」的答案。
    assert groups == {"Width", "Roughness", "Vs target"}


def test_the_direction_and_target_rows_are_buttons_not_english(qapp):
    """使用者定調「能用圖就用圖」（F11 Region-2）—— 這兩排各自是四個畫得出來
    的形狀，所以它們是圖示不是下拉。"""
    from d4t.ui import widgets as widgets_mod

    specs = {s.name: s for s in REGISTRY["cd_measure"].params}
    for name in ("axis", "target"):
        spec = specs[name]
        assert spec.type == "icon_choice", name
        assert len(spec.icons or []) == len(spec.choices or [])
        for icon in spec.icons:
            assert icon in widgets_mod.GLYPH_ICONS, icon
        for choice in spec.choices:
            assert spec.choice_help.get(choice), (name, choice)


def test_the_image_stream_and_region_rows_stay_read_only(qapp):
    """來源只在畫布上拉線決定（F9-6：「他會很亂連」）。"""
    specs = {s.name: s for s in REGISTRY["cd_measure"].params}
    assert specs["source"].type == "image_keys"
    assert specs["roi"].type == "region_keys"
    assert specs["source"].direction == "in"
    assert specs["roi"].direction == "in"
