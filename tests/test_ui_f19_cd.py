"""CD 的 UI（F19 第 4 步）：影像上的量測標記 ＋ 卡片面板。

**一律讀 API，不讀畫素**（`summary()` / `mark_count()` / `metric_face()`）——
畫素比對在這個 repo 只用在「兩顆圖示長得一不一樣」那種地方。
"""
from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

import d4t.core.steps  # noqa: F401 — registration side-effect
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import REGISTRY, get_step
from d4t.core.steps.cd import (
    MAX_CONTOUR_POINTS, MAX_DRAWN_LINES, REPORT_CHOICES, SHAPE_BLOB,
    SHAPE_LINE, SIZE_CHOICES,
)

from tests.test_algo_edge import line_block
from tests.test_algo_shape import add_ellipse, canvas, disc


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
    lines, points, focus, labels = get_step("cd_measure").overlay_marks(
        ctx, p)
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
    lines, _points, focus, _labels = get_step(
        "cd_measure").overlay_marks(ctx, p)
    assert len(lines) == MAX_DRAWN_LINES
    assert focus >= 0


def test_every_card_answers_the_marks_question():
    """預設什麼都不畫，所以既有的卡一張都不用動。"""
    ctx = Context(images={"test": np.zeros((8, 8), np.float32)})
    for key, cls in REGISTRY.items():
        lines, points, focus, labels = cls.overlay_marks(ctx, {})
        assert list(lines) == [] and list(points) == [] and focus == -1, key
        assert list(labels) == [], key


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



def paint_calls(insp):
    """把面板畫進一張離屏圖，回它畫了幾列（`_paint_one` 被呼叫幾次）。

    數呼叫次數而不是數畫素：畫素會隨字型與抗鋸齒漂，而這裡要問的是**結構**
    （幾個區域就幾列）。
    """
    from PySide6.QtGui import QPainter, QPixmap

    seen = []
    real = insp._paint_one

    def spy(p, rect, note, **kw):
        seen.append(str(note.get("region") or ""))
        return real(p, rect, note, **kw)

    insp._paint_one = spy
    pm = QPixmap(800, 260)
    painter = QPainter(pm)
    try:
        insp.paint_body(painter, QRectF(0, 0, 800, 260))
    finally:
        painter.end()
        insp._paint_one = real
    return {"rows": len(seen), "regions": seen}


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


# --------------------------------------------------------------------------- #
# 無方向那一支的 UI（F19 第二批）
# --------------------------------------------------------------------------- #
def measured_blob(img=None, **params):
    cls = REGISTRY["cd_measure"]
    p = cls.validate_params(dict({"shape": SHAPE_BLOB}, **params))
    block = disc(d=20.0) if img is None else img
    ctx = Context(images={"test": np.asarray(block, dtype=np.float32)})
    return cls().run(ctx, p), p


def test_the_outline_and_the_chord_become_marks():
    """**沒有新的 UI 原語** —— 一圈輪廓是一串線段，最長的弦是第 N+1 條。"""
    ctx, p = measured_blob()
    lines, points, focus, labels = get_step("cd_measure").overlay_marks(
        ctx, p)
    assert len(lines) == len(points) > 3
    assert focus == len(lines) - 1                 # 弦畫成醒目的那一條
    assert len(points[focus]) == 2
    assert len(lines) <= MAX_CONTOUR_POINTS + 1    # 輪廓抽稀過
    for seg in lines:
        for x, y in seg:
            assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def test_nothing_measured_means_no_marks_at_all():
    """「框還在但標記沒了」= 這一顆量不出來，而那是最有用的一個狀態。"""
    ctx, p = measured_blob(canvas(64))
    lines, points, focus, labels = get_step("cd_measure").overlay_marks(
        ctx, p)
    assert lines == [] and points == [] and focus == -1


def test_the_panel_switches_to_the_blob_view(qapp):
    ctx, p = measured_blob()
    insp = make_panel(qapp, ctx, p)
    assert insp.is_blob()
    said = insp.summary()
    assert "area 3" in said and "px" in said
    assert "at " in said and "°" in said
    assert "blob" in insp.tab_tooltip()


def test_the_blob_panel_says_why_when_there_is_no_size(qapp):
    ctx, p = measured_blob(canvas(64))
    insp = make_panel(qapp, ctx, p)
    assert insp.has_data()                          # 有 meta = 講得出為什麼
    assert "no size here" in insp.summary()
    assert "stands out from the noise" in insp.summary()


def test_the_blob_panel_flags_the_two_things_worth_knowing(qapp):
    """挑了哪一團、以及貼不貼邊 —— 兩個都要在那一行字上。"""
    two = canvas(96)
    add_ellipse(two, 48, 48, 8.0, 8.0)
    add_ellipse(two, 80, 80, 13.0, 13.0)
    ctx, p = measured_blob(two)
    assert "2 blobs" in make_panel(qapp, ctx, p).summary()

    edge = canvas(64)
    add_ellipse(edge, 58, 32, 14.0, 10.0)
    ctx, p = measured_blob(edge)
    assert "lower bound" in make_panel(qapp, ctx, p).summary()


def test_the_blob_panel_draws_without_blowing_up(qapp):
    from PySide6.QtGui import QPixmap

    for img in (disc(d=20.0), canvas(64)):
        ctx, p = measured_blob(img)
        insp = make_panel(qapp, ctx, p,
                          batch=[{"features": {"cd_area_px": 300.0 + i}}
                                 for i in range(30)])
        insp.resize(560, 190)
        insp.render(QPixmap(560, 190))


def test_every_size_metric_the_card_offers_has_a_face(qapp):
    from d4t.ui import widgets as widgets_mod

    groups = set()
    for mid in SIZE_CHOICES:
        group, label, glyph = widgets_mod.metric_face(mid)
        assert group in widgets_mod.METRIC_GROUP_ORDER, mid
        assert group != "Other", "%s 沒有登記在 METRIC_GROUPS" % mid
        assert label and not label.startswith("cd_"), mid
        assert glyph in widgets_mod.METRIC_GLYPHS, mid
        groups.add(group)
    # **不要用 ``Shape``** —— 那個字在 GLV 那邊已經是偏度那一群了。
    assert groups == {"Size", "Outline"}
    assert "Shape" not in groups


def test_the_shape_fork_is_two_buttons_not_a_dropdown(qapp):
    from d4t.ui import widgets as widgets_mod

    spec = {s.name: s for s in REGISTRY["cd_measure"].params}["shape"]
    assert spec.type == "icon_choice"
    assert list(spec.choices) == [SHAPE_LINE, SHAPE_BLOB]
    for icon in spec.icons:
        assert icon in widgets_mod.GLYPH_ICONS, icon
    for choice in spec.choices:
        assert spec.choice_help.get(choice), choice


def test_the_two_shape_icons_do_not_look_the_same(qapp):
    """兩顆並排的鈕長得一樣 = 那一列等於沒有（同 F11 那四支 ROI 工具）。"""
    from PySide6.QtGui import QImage, QPainter
    from d4t.ui import widgets as widgets_mod

    shots = []
    for name in ("shape_line", "shape_blob"):
        img = QImage(19, 19, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        try:
            widgets_mod.draw_glyph_icon(p, name, 19.0, "#000000")
        finally:
            p.end()
        shots.append(img.constBits().tobytes())
    assert shots[0] != shots[1]


def test_the_blob_panel_never_prints_a_zero_area(qapp):
    """**0 是一個看起來很像答案的答案** —— 而面板一度自己犯了卡片的規矩 3。

    第一版把 ``area %d px`` **無條件**畫在直方圖右上角，所以量不出來的那一顆上面
    寫著「area 0 px」。（那一行後來整個拿掉了：它右對齊之後緊貼著隔壁那一格的
    標題，而摘要那一行本來就寫了同一句話。）兩件都是**截圖出來才看到的**，所以
    這裡留一支釘住：畫出來的東西要跟「有沒有量到」有關，而數字只在摘要那一行。
    """
    from PySide6.QtGui import QImage

    shots = {}
    for tag, img in (("ok", disc(d=20.0)), ("none", canvas(64))):
        ctx, p = measured_blob(img)
        insp = make_panel(qapp, ctx, p)
        insp.resize(560, 190)
        pic = QImage(560, 190, QImage.Format_ARGB32)
        pic.fill(0)
        insp.render(pic)
        shots[tag] = pic.constBits().tobytes()
    assert shots["ok"] != shots["none"]
    # 而**摘要那一行**才是講「為什麼沒有」的地方
    ctx, p = measured_blob(canvas(64))
    said = make_panel(qapp, ctx, p).summary()
    assert "0 px" not in said and "no size here" in said


# --------------------------------------------------------------------------- #
# 版面（截圖出來才看得到的那幾件）
# --------------------------------------------------------------------------- #
def test_a_row_label_that_echoes_its_section_is_dropped(qapp):
    """**同一個字不要在畫面上出現兩次。**

    CD 的膠囊那一格 ``label`` 與 ``section`` 都是 "Report"，而一整塊的編輯器
    那一列的名字是垂直置中的 —— 於是那個字落在群組區塊的**中間那一列**旁邊，
    讀起來像是一個叫「Report」的群（Size 的第二排看起來屬於它）。
    """
    from d4t.ui.widgets import ParamForm

    form = ParamForm()
    form.set_step(REGISTRY["cd_measure"].describe(),
                  REGISTRY["cd_measure"].validate_params({}))
    row = form._rows["report"]
    assert row.spec["label"] == row.spec["section"] == "Report"
    assert row.name_label.isHidden(), "重複自己小標題的名字要收起來"

    # 而**不**重複的那些照常顯示
    assert not form._rows["criterion"].name_label.isHidden()


def _label_alignment(row):
    """那一列的名稱在它自己那一列裡對齊到哪（`_ParamRow` 的第一個 HBox）。"""
    top = row.layout().itemAt(0).layout()
    for i in range(top.count()):
        if top.itemAt(i).widget() is row.name_label:
            return top.itemAt(i).alignment()
    return None


def test_block_editors_get_their_label_at_the_top(qapp):
    """一整塊的編輯器（膠囊、曲線、表格…）名字要對齊到最上面。

    垂直置中的話，那個名字會落在區塊**中間某一列**旁邊，而那一列有它自己的
    意思（群名、第幾條曲線…）—— 讀起來就變成那一列的標題。
    """
    from PySide6.QtCore import Qt
    from d4t.ui.widgets import ParamForm, _BLOCK_EDITORS

    form = ParamForm()
    form.set_step(REGISTRY["glv_stats"].describe(),
                  REGISTRY["glv_stats"].validate_params({}))
    row = form._rows["metrics"]
    assert row.spec["type"] in _BLOCK_EDITORS
    assert not row.name_label.isHidden()          # 這一格沒有重複小標題
    assert _label_alignment(row) & Qt.AlignTop

    # 一行高的那些**不要**跟著改 —— 它們垂直置中才對得上輸入框
    plain = form._rows["source"]
    assert plain.spec["type"] not in _BLOCK_EDITORS
    assert not (_label_alignment(plain) or 0) & Qt.AlignTop


def test_the_profile_zooms_to_the_pair_it_measured(qapp):
    """**一張 128 px 的 patch 上有八個一模一樣的週期。** 整條畫出來的話，
    那兩個交點淹在裡面 —— 而這一格的唯一工作就是「邊被判在哪」。"""
    ctx, p = measured()
    insp = make_panel(qapp, ctx, p)
    prof = insp.note()["profile"]
    x0, x1 = insp._profile_window(prof, len(prof["values"]))
    assert x0 < prof["a"] < prof["b"] < x1          # 兩個交點都在視窗裡
    assert (x1 - x0) < len(prof["values"]) * 0.8    # 而且真的有放大
    # 兩側都要留白 —— 「邊的外面長什麼樣」是判斷配對對不對的依據
    assert prof["a"] - x0 > 1.0 and x1 - prof["b"] > 1.0


def test_a_profile_with_no_pair_falls_back_to_the_whole_line(qapp):
    insp = make_panel(qapp, *measured())
    assert insp._profile_window({}, 64) == (0, 63)


# --------------------------------------------------------------------------- #
# 顏色：一個具名區域一個顏色，而且到處都是同一個
# --------------------------------------------------------------------------- #
def test_the_panel_uses_the_region_palette_not_a_flat_accent(qapp):
    """**同一塊區域在哪裡都是同一個顏色。**

    這條規矩是 `GlvInspector._colour` 立下的（疊框、模板編輯器、GLV 面板共用
    `theme.REGION_COLORS`）。CD 一開始整張畫 accent 藍 —— 於是同一塊區域在
    GLV 面板上是綠的、在 CD 面板上是藍的、影像上的框又是綠的。
    """
    from d4t.ui.theme import region_hex

    cls = REGISTRY["cd_measure"]
    p = cls.validate_params({"roi": "band"})
    ctx = Context(images={"test": line_block(rows=40, width=12.0,
                                             blur=1.2).astype(np.float32)})
    ctx.set_roi("band", (0.0, 0.0, 1.0, 1.0))
    insp = make_panel(qapp, cls().run(ctx, p), p)
    assert insp.colour() == region_hex(0)

    # 第二個區域拿第二個顏色 —— 而索引是**卡片**給的，不是面板自己數的
    insp.meta = {"cd": {"b": dict(insp.note(), region_index=1)}}
    assert insp.colour() == region_hex(1)


def test_the_card_says_which_region_each_note_is(qapp):
    """索引由卡片寫進 meta：兩邊各數各的話，"top,bot" 在一邊是 0/1、在另一邊
    （照名字排序）是 1/0，而顏色指錯區域比沒有顏色糟得多。"""
    cls = REGISTRY["cd_measure"]
    p = cls.validate_params({"roi": "top,bot"})
    ctx = Context(images={"test": line_block(rows=64, width=12.0,
                                             blur=1.2).astype(np.float32)})
    ctx.set_roi("top", (0.0, 4 / 64.0, 1.0, 12 / 64.0))
    ctx.set_roi("bot", (0.0, 40 / 64.0, 1.0, 12 / 64.0))
    notes = cls().run(ctx, p).meta["cd"]
    # 參數寫的順序是 top,bot —— 而區域框也是照那個順序上色的
    assert notes["top"]["region_index"] == 0
    assert notes["bot"]["region_index"] == 1


def test_marks_on_the_image_carry_their_region_colour(qapp):
    """兩塊區域的掃描線要分得出來，而且**跟它們自己的框同一個顏色**。"""
    from d4t.ui.theme import region_hex
    from d4t.ui.widgets import ImageView

    cls = REGISTRY["cd_measure"]
    p = cls.validate_params({"roi": "top,bot"})
    ctx = Context(images={"test": line_block(rows=64, width=12.0,
                                             blur=1.2).astype(np.float32)})
    ctx.set_roi("top", (0.0, 4 / 64.0, 1.0, 12 / 64.0))
    ctx.set_roi("bot", (0.0, 40 / 64.0, 1.0, 12 / 64.0))
    out = cls().run(ctx, p)
    lines, points, focus, labels = cls.overlay_marks(out, p)
    assert len(labels) == len(lines)
    assert set(labels) == {"top", "bot"}

    view = ImageView()
    view.set_image(np.zeros((64, 64), np.uint8))
    # 框先上色（studio 就是這個順序），標記沿用它排好的順序
    view.set_overlay([(0.0, 0.06, 1.0, 0.19), (0.0, 0.62, 1.0, 0.19)],
                     -1, ["top", "bot"])
    view.set_marks(lines, points, focus, labels)
    assert dict(view.mark_legend()) == {"top": region_hex(0),
                                        "bot": region_hex(1)}
    assert dict(view.overlay_legend()) == dict(view.mark_legend())


def test_marks_without_labels_still_draw(qapp):
    """沒有具名區域（量整張圖）就整組畫 accent —— 不是不畫。"""
    from d4t.ui.widgets import ImageView

    view = ImageView()
    view.set_image(np.zeros((64, 64), np.uint8))
    view.set_marks([[(0.0, 0.2), (1.0, 0.2)]], [[(0.3, 0.2), (0.7, 0.2)]], 0)
    assert view.mark_count() == 1
    assert view.mark_legend() == []


# --------------------------------------------------------------------------- #
# 接了幾個區域，面板就畫幾列
# --------------------------------------------------------------------------- #
def two_regions(qapp, shape=None, batch=None):
    """兩個區域跑一次，回面板。上面那一塊量得到、下面那一塊量不到。"""
    cls = REGISTRY["cd_measure"]
    p = cls.validate_params(dict({"roi": "top,bot"},
                                 **({"shape": shape} if shape else {})))
    img = line_block(rows=64, width=12.0, blur=1.2).astype(np.float32)
    img[40:, :] = 0.0                       # 下面那一塊什麼都沒有
    ctx = Context(images={"test": img})
    ctx.set_roi("top", (0.0, 4 / 64.0, 1.0, 12 / 64.0))
    ctx.set_roi("bot", (0.0, 40 / 64.0, 1.0, 20 / 64.0))
    return make_panel(qapp, cls().run(ctx, p), p, batch=batch)


def test_the_panel_draws_every_region_not_just_the_first(qapp):
    """以前只畫 ``notes()[0]``，而那是**照名字排序**的第一個 —— 於是影像上
    兩塊都有標記、面板卻只講其中一塊，另一塊去了哪畫面上沒有任何線索。

    最糟的形狀是被留下的那一塊剛好量不到：圖上的輪廓在 B 區、面板在講 A 區的
    「什麼都沒有」。這裡就是那個形狀（``bot`` 是空的）。
    """
    insp = two_regions(qapp)
    assert len(insp.notes()) == 2
    drawn = paint_calls(insp)
    # 一個區域一列，而且每一列都畫過東西
    assert drawn["rows"] == 2
    assert insp.tab_title() == "CD · 2 regions"


def test_each_row_is_its_own_region_colour(qapp):
    """兩列的顏色就是那兩塊區域在影像上的框的顏色（`region_hex` 同一組）。"""
    from d4t.ui.theme import region_hex

    insp = two_regions(qapp)
    got = [insp.colour(n) for n in insp.notes()]
    assert got == [region_hex(0), region_hex(1)]
    # 一列一個顏色 —— 兩列同色的話，畫面上分不出哪一條曲線是哪一塊
    assert len(set(got)) == 2


def test_the_summary_line_names_every_region(qapp):
    """「+1 more」說不出那一個是量到了還是量不到 —— 面板每一列都畫了，
    這一行也要每一個都講。"""
    insp = two_regions(qapp)
    said = insp.summary()
    assert "top:" in said and "bot:" in said
    assert "more" not in said
    # 而且講得出「那一塊沒有」
    assert "no width here" in said


def test_one_region_still_reads_exactly_as_before(qapp):
    """一個區域的時候標題還是區域名、小標題還是那三句話 —— 疊列的機制
    不能讓最常見的那個情況變複雜。"""
    ctx, p = measured()
    insp = make_panel(qapp, ctx, p)
    assert insp.tab_title().startswith("CD · ")
    assert "regions" not in insp.tab_title()
    assert ":" not in insp.summary().split("·")[0]     # 沒有冠上區域名


def test_too_many_regions_stop_at_max_rows(qapp):
    """面板不高。四列以上每一列的曲線就只剩幾個畫素（`GlvInspector.MAX_ROWS`
    同一個理由）—— 多的不畫，而不是每一列都畫不清楚。"""
    insp = two_regions(qapp)
    one = insp.notes()[0]
    insp.meta = {"cd": {k: dict(one, region_index=i)
                        for i, k in enumerate("abcde")}}
    assert len(insp.notes()) == 5
    assert paint_calls(insp)["rows"] == insp.MAX_ROWS


def test_the_row_label_keeps_its_underscores(qapp):
    """區域名畫在一個**照字型高度**留的行裡。寫死 13 px 的話底線被切掉，
    ``band_a_center`` 在畫面上變成「band a center」—— 那不是同一個名字
    （CSV 上的欄名是有底線的那個）。"""
    from PySide6.QtGui import QFontMetricsF, QPainter, QPixmap

    insp = two_regions(qapp)
    pm = QPixmap(600, 200)
    p = QPainter(pm)
    try:
        rect = QRectF(0, 0, 600, 200)
        body = insp._caption(p, rect, "", ("band_a_center", QColor("#5fd0a0")))
        used = rect.height() - body.height()
        assert used >= QFontMetricsF(p.font()).height()
    finally:
        p.end()


def test_rows_follow_the_wiring_order_not_the_alphabet(qapp):
    """"top,bot" 接進來的順序是 top 先，而顏色是照那個順序給的。照名字排的話
    面板會是「橘的在上、綠的在下」，跟影像上的框正好相反 —— 而使用者是拿
    顏色在兩邊之間認位置的。"""
    insp = two_regions(qapp)
    assert [n["region"] for n in insp.notes()] == ["top", "bot"]
    assert paint_calls(insp)["regions"] == ["top", "bot"]


def test_no_region_means_accent_in_the_panel_too(qapp):
    """量整張圖的時候沒有區域，也就沒有那個區域的顏色。影像上的標記在這個情況
    畫 accent（`ImageView._paint_marks`：沒有 labels 就整組 accent）—— 面板照樣
    畫 `region_hex(0)` 的綠的話，同一件事在兩邊又是兩個顏色。"""
    from d4t.ui.theme import TOKENS, region_hex
    from d4t.ui.widgets import ImageView

    ctx, p = measured()                       # 沒有 roi
    insp = make_panel(qapp, ctx, p)
    assert str(insp.note().get("region") or "") == ""
    assert insp.colour() == str(TOKENS["accent"])
    assert insp.colour() != region_hex(0)

    # 而影像那一邊本來就是 accent —— 兩邊現在講同一句話
    lines, points, focus, labels = REGISTRY["cd_measure"].overlay_marks(ctx, p)
    view = ImageView()
    view.set_image(np.zeros((64, 64), np.uint8))
    view.set_marks(lines, points, focus, labels)
    assert view.mark_legend() == []
