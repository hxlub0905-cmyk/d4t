# F8 驗收（UI 那一半）：交會定位在畫面上看得懂、而且不說謊。
"""兩件事：

1. **儀表要兩條曲線。** 交會處是兩組條紋共同定義的，所以失敗也有兩種，
   而且處置完全不同（調哪一組 sensitivity／pitch，還是這種 patch 本來就沒有
   橫的條紋）。只給一條曲線或一個信心值，使用者只知道「失敗了」。
2. **區域檢視要畫出每一個框。** 一個名字底下有八個框、畫面上只出現一個的話，
   使用者會以為量的是那一塊 —— 而畫面上沒有任何東西透露這件事。

⚠ **2026-08-27（F39-B4）從 `test_ui_f8_cross.py` 改名。** 同時把十一條
「疊在影像上的框不能說謊」切出去成 `tests/test_ui_region_overlay_truth.py`
—— 那十一條問的是**每一張 Region 卡**都要成立的事，跟交會定位這張卡無關。
留在這裡的是交會定位自己的儀表：兩條曲線、量給我填、點條紋挑材質、方向。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import wire_up  # noqa: E402  —— F10：加完卡要接線

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from tests.region_cards import (  # noqa: E402
    add_region_step, region_card,
)

SIZE, MG_PITCH, EPI_PITCH = 128, 24, 34


_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import inspectors as insp_mod
    from d4t.ui import region_check as rc_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QApplication=QApplication, insp_mod=insp_mod, rc_mod=rc_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lines_lot(tmp_path_factory):
    """兩軸不同週期的線陣列 —— F8 要練的就是這種 layout。"""
    from make_sample import generate

    return generate(str(tmp_path_factory.mktemp("f8_lines")), n=6, seed=4,
                    size=128, pitch=18, noise=4.0, pattern="lines")


@pytest.fixture
def cross_window(qapp, lines_lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lines_lot["klarf"], sync=True)
    nid = wire_up(win.model, add_region_step(win.model, "roi_cross"))
    win.model.set_param(nid, "roi_out", "xing")
    win.model.set_param(nid, "place", "beside_vertical")
    win.select_node(nid)
    yield win
    win.close()


def _img(ox: int = 0, epi_width: int = 14) -> np.ndarray:
    rng = np.random.default_rng(0)
    img = np.full((SIZE, SIZE), 90.0, np.float32)
    if epi_width:
        img[np.arange(SIZE) % EPI_PITCH < epi_width, :] = 170.0
    img[:, (np.arange(SIZE) + ox) % MG_PITCH < 8] = 45.0
    return img + rng.normal(0, 2.0, (SIZE, SIZE)).astype(np.float32)


def _run(epi_width: int = 14) -> Context:
    img = _img(epi_width=epi_width)
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    region_card("roi_cross")().run(ctx, {
        "source": "ref", "place": "beside_vertical", "box_size": 5.0,
        "inset": 3.0, "roi_out": "xing",
        "vertical_pitch": MG_PITCH, "horizontal_pitch": EPI_PITCH})
    return ctx


# --------------------------------------------------------------------------- #
# 1. 儀表
# --------------------------------------------------------------------------- #
def test_the_inspector_is_registered_for_the_card(qapp):
    """依 ``Step.key`` 註冊 —— 加一張卡不必動 UI，但**這張**卡需要它自己的儀表。"""
    assert insp_mod.inspector_for("roi_cross") is insp_mod.CrossInspector


def test_both_directions_get_their_own_curve(qapp):
    """一條曲線答不出「該調哪一半」。"""
    ctx = _run()
    panel = insp_mod.CrossInspector()
    panel.set_context("cross", {"roi_out": "xing"}, meta=ctx.meta)

    assert panel.has_data() is True
    assert panel.across.has_data() is True, "直的那組沒有曲線"
    assert panel.down.has_data() is True, "橫的那組沒有曲線"
    # 兩條曲線是**不同**的資料，不是同一條畫兩次
    assert panel.across.summary() != panel.down.summary()


def test_the_summary_says_how_many_boxes_and_what_pitch(qapp):
    ctx = _run()
    panel = insp_mod.CrossInspector()
    panel.set_context("cross", {"roi_out": "xing"}, meta=ctx.meta)
    text = panel.summary()
    assert "boxes" in text and "pitch" in text
    assert "%d boxes" % ctx.roi_count("xing") in text


def test_a_failure_says_which_direction_had_nothing(qapp):
    """使用者下一步要做什麼完全取決於是哪一邊。"""
    ctx = _run(epi_width=0)          # 只有直的條紋
    panel = insp_mod.CrossInspector()
    panel.set_context("cross", {"roi_out": "xing"}, meta=ctx.meta)
    text = panel.summary()
    assert "not located" in text and "flat stripes" in text


def test_the_curve_panel_shades_every_selected_stripe(qapp):
    """``ProfilePanel`` 原本只塗**一段**（投影定位挑一段）。交會定位一整排都要
    —— 只塗一段的話，面板會少講「這張卡其實用到了這一整排」。"""
    ctx = _run()
    panel = insp_mod.CrossInspector()
    panel.set_context("cross", {"roi_out": "xing"}, meta=ctx.meta)
    rec = ctx.meta["crossings"]["xing"]
    assert len(rec["x"]["selected"]) > 2
    # 摘要走的是 selected 那條路（講條紋數與 pitch，不是「挑了哪一段」）
    assert "stripes" in panel.across.summary()

    # 量畫素，而且跟**只塗一段**的同一個面板比 —— 比對照組不比絕對顏色，
    # 這樣換主題、換 token 都不會讓這條測試變成假警報。
    from d4t.ui.widgets import ProfilePanel

    data = dict(rec["x"])
    # 三個對照：完全不塗（只有曲線）／塗一段／塗整排。減掉「只有曲線」那一份
    # 才量得到**塗的面積本身** —— 曲線的畫素三種情況都有。
    none = _shaded_columns(ProfilePanel(), dict(data, selected=[]))
    one = _shaded_columns(ProfilePanel(), dict(data, selected=data["selected"][:1]))
    many = _shaded_columns(ProfilePanel(), data)
    assert one > none, "連一段都沒塗到"
    assert (many - none) > (one - none) * 2, (
        "整排只塗出 %d 欄，一段是 %d 欄（曲線本身佔 %d 欄）—— 沒有全部塗出來"
        % (many - none, one - none, none))


def test_the_panel_says_when_the_line_width_was_given_not_measured(qapp):
    """給定的線寬是使用者填進去的**假設**，而假設要看得到才驗得了 ——
    量到的線寬畫面上本來就看得到（塗起來的那幾段有多寬），給定的那個看不到。"""
    from d4t.ui.widgets import ProfilePanel

    ctx = _run()
    data = dict(ctx.meta["crossings"]["xing"]["x"])
    given, measured = ProfilePanel(), ProfilePanel()
    given.set_data("upright stripes", dict(data, width_fixed=True,
                                           width_used=8.0))
    measured.set_data("upright stripes", dict(data, width_fixed=False))
    assert "width 8.0 px (given)" in given.summary()
    assert "given" not in measured.summary()


def _shaded_columns(panel, data) -> int:
    """面板中間那一列上，有幾欄不是純底色（= 被塗到的寬度）。"""
    from PySide6.QtGui import QColor, QImage

    panel.set_data("x", data)
    panel.resize(240, 120)
    img = QImage(240, 120, QImage.Format_ARGB32)
    img.fill(0)
    panel.render(img)
    bg = QColor(insp_mod.TOKENS["bg_surface"]).rgb()
    return sum(1 for x in range(12, 228)
               if QImage.pixelColor(img, x, 100).rgb() != bg)


# --------------------------------------------------------------------------- #
# 4. 「這一格我故意不放」要看得出來（F8 第六輪）
# --------------------------------------------------------------------------- #
def _cpode_ctx() -> Context:
    """MG 的晶格上有兩格是別的材質（很暗）—— 站點的 CPODE。"""
    rng = np.random.default_rng(0)
    img = np.full((SIZE, SIZE), 90.0, np.float32)
    img[np.arange(SIZE) % EPI_PITCH < 14, :] = 180.0
    img[:, np.arange(SIZE) % MG_PITCH < 8] = 220.0
    for site in (2, 4):
        img[:, site * MG_PITCH:site * MG_PITCH + 8] = 30.0
    img += rng.normal(0, 2.0, (SIZE, SIZE)).astype(np.float32)
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    region_card("roi_cross")().run(ctx, {
        "source": "ref", "place": "beside_vertical", "box_size": 5.0,
        "inset": 3.0, "roi_out": "xing", "vertical_kinds": 3,
        "vertical_pitch": MG_PITCH, "horizontal_pitch": EPI_PITCH})
    return ctx


def test_the_summary_says_how_many_spots_were_left_out(qapp):
    """「這一格我故意不放」跟「這一格我沒找到」在畫面上長得一模一樣。
    少了這句話，使用者會以為那裡定位失敗，然後去調敏感度 —— 而敏感度對它
    一點作用都沒有。"""
    rec = _cpode_ctx().meta["crossings"]["xing"]
    assert len(rec["x"]["blocked"]) == 2, rec["x"]["blocked"]

    panel = insp_mod.CrossInspector()
    panel.set_context("cross", {"roi_out": "xing"},
                      meta={"crossings": {"xing": rec}})
    assert "2 left out" in panel.across.summary()


def test_the_spots_left_out_are_drawn_on_the_curve(qapp):
    """數字說「有兩格沒用」，但**哪兩格**只有畫出來才答得出來 ——
    而那正是使用者要判斷「它跳過的是不是我想跳過的那兩格」的依據。"""
    from d4t.ui.widgets import ProfilePanel

    data = _cpode_ctx().meta["crossings"]["xing"]["x"]
    with_marks = _shaded_columns(ProfilePanel(), dict(data))
    without = _shaded_columns(ProfilePanel(), dict(data, blocked=[]))
    assert with_marks > without + 4, (
        "被擋掉的那兩格沒有畫出來（%d vs %d 欄）" % (with_marks, without))


# --------------------------------------------------------------------------- #
# 5. 「量給我填」與「藍框跟線為什麼對不齊」（F8 第六輪）
# --------------------------------------------------------------------------- #
def test_the_panel_offers_the_pitch_it_measured(qapp):
    """使用者原話：「有辦法自動 measure 填入左側數值嗎」。曲線本來就知道答案，
    要他看著面板上的數字再手動打一次，是在製造一個可以打錯的機會。"""
    rec = _run().meta["crossings"]["xing"]["x"]
    insp = insp_mod.CrossInspector()      # 留著參考：子元件跟著父物件一起活
    panel = insp.across
    panel.set_data("upright stripes", dict(rec, pitches_used=[]))

    assert panel.measured_pitches()[0] == pytest.approx(MG_PITCH, abs=1.5)
    text = panel.fill_button_text()
    assert text.startswith("Use ") and "px" in text, text


def test_the_offer_disappears_once_it_is_already_that_value(qapp):
    """按了不會改變任何東西的按鈕比沒有那顆按鈕糟 —— 使用者會以為自己按錯了。"""
    rec = _run().meta["crossings"]["xing"]["x"]
    insp = insp_mod.CrossInspector()
    panel = insp.across
    panel.set_data("upright stripes",
                   dict(rec, pitch_measured=24.0, pitch_measured_2=0.0,
                        pitches_used=[24.0]))
    assert panel.fill_button_text() == ""


def test_pressing_it_asks_for_both_pitch_boxes(qapp):
    """只送第一格的話，上一次留下來的交錯值會跟新量到的單一 pitch 湊成一組
    沒有人量過的組合。"""
    rec = _run().meta["crossings"]["xing"]["x"]
    insp = insp_mod.CrossInspector()
    seen = []
    insp.param_requested.connect(lambda n, v: seen.append((n, v)))
    insp.across.set_data("upright stripes", dict(rec, pitches_used=[]))
    insp.across._request_pitch()

    assert [n for n, _v in seen] == ["vertical_pitch", "vertical_pitch_2"]
    assert seen[0][1] == pytest.approx(MG_PITCH, abs=1.5)
    assert seen[1][1] == 0.0

    seen.clear()
    insp.down.set_data("flat stripes",
                       dict(rec, axis="y", pitch_measured=40.0,
                            pitch_measured_2=33.0, pitches_used=[]))
    insp.down._request_pitch()
    assert [n for n, _v in seen] == ["horizontal_pitch", "horizontal_pitch_2"]
    assert (seen[0][1], seen[1][1]) == (40.0, 33.0)


def test_the_button_writes_it_into_the_card_and_can_be_undone(qapp, cross_window):
    """走的是跟使用者自己動參數表同一條路 —— 一個會改 recipe 而撤不掉的
    按鈕，比沒有那顆按鈕糟。"""
    win = cross_window
    nid = win.selected_node
    win.refresh_preview(sync=True)
    before = win.model.nodes[nid].params.get("vertical_pitch")

    insp = win.inspector()
    assert isinstance(insp, insp_mod.CrossInspector)
    assert insp.across.fill_button_text(), "沒有量到可以填的東西"
    insp.across._request_pitch()

    after = win.model.nodes[nid].params.get("vertical_pitch")
    assert after != before and float(after) > 2.0
    # 參數表也要跟著顯示新值 —— 不然畫面上那一格還是舊的，而使用者按了鈕
    assert float(win.param_form.values()["vertical_pitch"]) == float(after)

    win.undo()
    assert win.model.nodes[nid].params.get("vertical_pitch") == before


def test_the_summary_explains_the_gap_between_the_lines_and_the_blocks(qapp):
    """使用者原話：「藍框跟線的實際意義是什麼（我發現有時候兩者會 shift）」。
    shift 是刻意的，但沒講出來就只是「怪」—— 而「怪」的下一步通常是去亂調
    敏感度。"""
    from d4t.ui.widgets import ProfilePanel

    rec = _run().meta["crossings"]["xing"]["x"]
    moved, still = ProfilePanel(), ProfilePanel()
    moved.set_data("upright stripes", dict(rec, snap_shift=2.1))
    still.set_data("upright stripes", dict(rec, snap_shift=0.0))
    assert "snapped 2.1 px" in moved.summary()
    assert "snapped" not in still.summary()


def test_a_pitch_that_was_given_but_not_used_is_called_out(qapp):
    """使用者會以為那格生效了，然後拿一份其實是「照影像自己量」的結果去跑整批。"""
    from d4t.ui.widgets import ProfilePanel

    rec = _run().meta["crossings"]["xing"]["x"]
    panel = ProfilePanel()
    panel.set_data("flat stripes",
                   dict(rec, pitch_note="cannot tell which of the two "
                                        "spacings comes first"))
    assert "pitch not used" in panel.summary()


def test_the_panel_shouts_when_the_pitch_does_not_agree(qapp):
    """這是「這一顆能不能信」的答案，而在這種失敗上 confidence 反而更高
    （實測 285.9 vs 正確時的 215.8）—— 所以它要排在信心值前面。"""
    from d4t.ui.widgets import ProfilePanel

    rec = _run().meta["crossings"]["xing"]["x"]
    panel = ProfilePanel()
    panel.set_data("upright stripes",
                   dict(rec, pitch_disagrees=True, pitch_ratio=0.5))
    text = panel.summary()
    assert "50% of the pitch you gave" in text
    assert text.index("50%") < text.index("confidence")


# --------------------------------------------------------------------------- #
# F11 Region-2b：點曲線上的一根條紋 = 選那一種材質
# --------------------------------------------------------------------------- #
def test_the_engine_says_which_group_each_stripe_is_in(qapp):
    """UI **不自己分群** —— 分幾群取決於現在挑第幾亮，那個規則只該有一份。"""
    data = _cpode_ctx().meta["crossings"]["xing"]["x"]
    assert len(data["groups"]) == len(data["bands"])
    assert data["group_rules"], "每一群都要講得出「要填什麼」"
    assert str(data["group_picked"]) in {str(g) for g in data["groups"]}


def test_clicking_a_stripe_asks_for_that_material(qapp):
    """使用者：「能用圖就用圖。」`second_brightest` 這個詞本身不告訴他任何事 ——
    「哪一組是第二亮的」是一個只有看圖才答得出來的問題，而圖就在這裡。"""
    from d4t.ui.widgets import ProfilePanel

    data = _cpode_ctx().meta["crossings"]["xing"]["x"]
    panel = ProfilePanel()
    panel.resize(400, 120)
    panel.set_data("upright stripes", data)

    got = []
    panel.select_requested.connect(lambda a, r: got.append((a, r)))

    # 挑一根**不是**現在選中那一群的條紋來點
    other = next(i for i, g in enumerate(data["groups"])
                 if g != data["group_picked"])
    a, b = data["bands"][other]
    _click_curve(panel, (a + b) / 2.0)

    assert got, "點了沒反應"
    axis, rule = got[0]
    assert axis == "x"
    assert rule == data["group_rules"][str(data["groups"][other])]


def test_dragging_still_measures_instead_of_picking(qapp):
    """同一個手勢兩種意思會很糟 —— **點一下 = 選材質，拖一段 = 量尺**。"""
    from d4t.ui.widgets import ProfilePanel

    data = _cpode_ctx().meta["crossings"]["xing"]["x"]
    panel = ProfilePanel()
    panel.resize(400, 120)
    panel.set_data("upright stripes", data)

    picked, measured = [], []
    panel.select_requested.connect(lambda a, r: picked.append(r))
    panel.measure_changed.connect(lambda *a: measured.append(a))

    _click_curve(panel, 6.0, to_index=30.0)
    assert measured, "拖曳要量尺"
    assert picked == [], "拖曳不該順手改參數"


def test_clicking_between_the_stripes_does_nothing(qapp):
    """點在沒有任何段的地方 —— **不要猜一個最近的**。"""
    from d4t.ui.widgets import ProfilePanel

    panel = ProfilePanel()
    panel.resize(400, 120)
    panel.set_data("upright stripes", {"profile": [10.0] * 40, "raw": [10.0] * 40,
                                       "bands": [], "groups": []})
    got = []
    panel.select_requested.connect(lambda a, r: got.append(r))
    _click_curve(panel, 20.0)
    assert got == []


def test_the_studio_sends_it_to_the_right_axis(cross_window):
    """``x`` 那條曲線講的是**直的**條紋。接反的症狀是點左邊改到右邊的參數 ——
    而畫面上兩邊都會動，看起來像是「有反應」。"""
    win = cross_window
    nid = wire_up(win.model, add_region_step(win.model, "roi_cross"))
    win.select_node(nid)

    win._on_select_requested("x", "darkest")
    assert win.model.nodes[nid].params["vertical_select"] == "darkest"
    win._on_select_requested("y", "second_brightest")
    assert win.model.nodes[nid].params["horizontal_select"] == "second_brightest"
    assert win.model.nodes[nid].params["vertical_select"] == "darkest"


def _click_curve(panel, at_index: float, to_index: float = None) -> None:
    """在曲線的第 ``at_index`` 個取樣點按下（可選拖到 ``to_index``）再放開。"""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import Qt as _Qt

    n = max(2, len(panel._data.get("profile") or [2]))
    plot = panel._plot_rect()

    def x_of(i):
        return plot.left() + plot.width() * (float(i) / (n - 1))

    def send(kind, x, button, buttons):
        pt = QPointF(x, plot.center().y())
        ev = QMouseEvent(kind, pt, pt, button, buttons, _Qt.NoModifier)
        {QEvent.MouseButtonPress: panel.mousePressEvent,
         QEvent.MouseMove: panel.mouseMoveEvent,
         QEvent.MouseButtonRelease: panel.mouseReleaseEvent}[kind](ev)

    send(QEvent.MouseButtonPress, x_of(at_index), _Qt.LeftButton, _Qt.LeftButton)
    if to_index is not None:
        send(QEvent.MouseMove, x_of(to_index), _Qt.NoButton, _Qt.LeftButton)
        at_index = to_index
    send(QEvent.MouseButtonRelease, x_of(at_index), _Qt.LeftButton, _Qt.NoButton)


# --------------------------------------------------------------------------- #
# 一個方向（F11 Region-2c）—— 畫面上不能留下一條「空的曲線」
# --------------------------------------------------------------------------- #
def _run_one_way() -> Context:
    """只有直條紋的圖 ＋ 只看直的方向。"""
    img = _img(epi_width=0)
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    region_card("roi_cross")().run(ctx, {
        "source": "ref", "directions": "upright", "place": "crossing",
        "inset": 0.0, "roi_out": "xing", "vertical_pitch": MG_PITCH})
    return ctx


def test_the_direction_that_is_not_used_has_no_curve_on_screen(qapp):
    """沒在看的方向畫出來是一條**平的**曲線。

    平的線在這張面板上的意思一直都是「這裡沒東西、去調敏感度」—— 完全相反的
    意思。留著它等於給一個錯的提示，而且佔掉在看的那條曲線一半的高度。
    """
    ctx = _run_one_way()
    panel = insp_mod.CrossInspector()
    panel.set_context("cross", {"roi_out": "xing", "directions": "upright"},
                      meta=ctx.meta)
    assert panel.across.isVisibleTo(panel) is True
    assert panel.down.isVisibleTo(panel) is False


def test_both_curves_come_back_when_both_directions_are_used(qapp):
    ctx = _run()
    panel = insp_mod.CrossInspector()
    panel.set_context("cross", {"roi_out": "xing"}, meta=ctx.meta)
    assert panel.across.isVisibleTo(panel) is True
    assert panel.down.isVisibleTo(panel) is True


def test_the_summary_does_not_report_a_pitch_it_never_looked_for(qapp):
    """「flat pitch 0.0 px」是一個看起來像量測失敗的**假**數字。"""
    ctx = _run_one_way()
    panel = insp_mod.CrossInspector()
    panel.set_context("cross", {"roi_out": "xing", "directions": "upright"},
                      meta=ctx.meta)
    text = panel.summary()
    assert "upright pitch" in text
    assert "flat pitch" not in text


def test_the_three_direction_icons_are_drawable_and_different(qapp):
    """三顆並排，唯一的差別是亮的是哪一組條紋 —— 那也是選項唯一的差別。"""
    from PySide6.QtGui import QImage, QPainter

    from d4t.ui.widgets import GLYPH_ICONS, draw_glyph_icon

    seen = {}
    for name in ("dir_both", "dir_upright", "dir_flat"):
        assert name in GLYPH_ICONS
        img = QImage(21, 21, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        draw_glyph_icon(p, name, 21.0, "#ffffff")
        p.end()
        seen[name] = bytes(img.constBits())
    assert len(set(seen.values())) == 3, "三顆圖示不能長得一樣"


