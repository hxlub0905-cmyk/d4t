# F8 驗收（量測尺）：不知道 pitch 的時候，從曲線上量出來。
"""使用者原話：「我希望 crossing 部分可以增加按住圖形可以量測的功能（放開就
結束），這樣 user 至少在如果不知道 pitch 的時候，也能從 profile 量測判斷
（用綠線然後按住時上方 image stream 也能同步顯示）」。

為什麼這件事不是「錦上添花」
----------------------------
``roi_cross`` 的 pitch 欄位是**可以留白**的（留白就靠影像自己量）。但一旦影像
上的條紋不夠乾淨，那張卡就會要求使用者填一個他不知道的數字 —— 而畫面上唯一
握有這個資訊的東西正是那條曲線。沒有尺，那條曲線只能用眼睛估。

三件事各自都會壞，所以各自鎖住：

1. **按住才有、放開就沒有。** 它是「現在正在量」的回饋，不是留在畫面上的註記。
2. **讀數要答得出 pitch。** 只講「幾個像素」的話，使用者還要自己數條紋再除。
3. **上面那張影像要同步。** 曲線上的一段只是「第 40 到第 74 個取樣點」；
   「我量到的是不是兩根 MG 的距離」這個問題只有看影像答得出來。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import wire_up  # noqa: E402  —— F10：加完卡要接線

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.pipeline import get_step  # noqa: E402
from adept.core.pipeline.context import Context  # noqa: E402

SIZE, MG_PITCH, EPI_PITCH = 128, 24, 34

_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)


def _import_qt(g):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from adept.ui import inspectors as insp_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    from adept.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, QMouseEvent=QMouseEvent, QPoint=QPoint,
             QPointF=QPointF, Qt=Qt, insp_mod=insp_mod, studio_mod=studio_mod,
             theme_mod=theme_mod, widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _img() -> np.ndarray:
    rng = np.random.default_rng(0)
    img = np.full((SIZE, SIZE), 90.0, np.float32)
    img[np.arange(SIZE) % EPI_PITCH < 14, :] = 170.0
    img[:, np.arange(SIZE) % MG_PITCH < 8] = 45.0
    return img + rng.normal(0, 2.0, (SIZE, SIZE)).astype(np.float32)


@pytest.fixture(scope="module")
def record():
    """一次真的計算 —— 面板畫的資料一律來自引擎，UI 不自己再算一次。"""
    ctx = Context(images={"test": _img(), "ref": _img()})
    get_step("roi_cross")().run(ctx, {
        "source": "ref", "place": "beside_vertical", "box_size": 5.0,
        "roi_out": "xing", "vertical_pitch": MG_PITCH,
        "horizontal_pitch": EPI_PITCH})
    return ctx.meta["crossings"]["xing"]


@pytest.fixture
def panel(qapp, record):
    p = widgets_mod.ProfilePanel()
    p.set_data("upright stripes", record["x"])
    p.resize(400, 120)
    yield p
    p.deleteLater()


def _press(w, x: float, button=None):
    button = button or Qt.LeftButton
    _send(w, QMouseEvent.Type.MouseButtonPress, x, button, button)


def _move(w, x: float):
    _send(w, QMouseEvent.Type.MouseMove, x, Qt.NoButton, Qt.LeftButton)


def _release(w, x: float):
    _send(w, QMouseEvent.Type.MouseButtonRelease, x, Qt.LeftButton, Qt.NoButton)


def _send(w, kind, x: float, button, buttons) -> None:
    pos = QPointF(float(x), float(w.height()) / 2.0)
    ev = QMouseEvent(kind, pos, w.mapToGlobal(pos.toPoint()),
                     button, buttons, Qt.NoModifier)
    QApplication.sendEvent(w, ev)


def _x_of(panel, index: float) -> float:
    """曲線上第 ``index`` 個取樣點畫在 widget 的哪個 x（測試自己不重算映射，
    走的是面板公開的反函數 —— 這樣兩邊只要有一邊改了就會被抓到）。"""
    lo, hi = 0.0, float(panel.width())
    for _ in range(40):                      # 二分反解 _index_at
        mid = (lo + hi) / 2.0
        if panel._index_at(mid) < index:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# --------------------------------------------------------------------------- #
# 1. 按住才有，放開就沒有
# --------------------------------------------------------------------------- #
def test_nothing_is_measured_until_you_press(panel):
    assert panel.ruler_span() is None
    assert panel.ruler_text() == ""


def test_press_and_drag_measures_the_stretch(panel):
    _press(panel, _x_of(panel, 20))
    _move(panel, _x_of(panel, 68))

    span = panel.ruler_span()
    assert span is not None
    assert span[0] == pytest.approx(20.0, abs=0.6)
    assert span[1] == pytest.approx(68.0, abs=0.6)


def test_letting_go_ends_it(panel):
    """「放開就結束」—— 它是現在正在量的回饋，不是留在畫面上的註記。"""
    _press(panel, _x_of(panel, 20))
    _move(panel, _x_of(panel, 68))
    assert panel.ruler_span() is not None

    _release(panel, _x_of(panel, 68))
    assert panel.ruler_span() is None
    assert panel.ruler_text() == ""


def test_dragging_backwards_measures_the_same_stretch(panel):
    """從右往左拉是一樣一件事。負的長度會讓讀數變成 ``-48.0 px``。"""
    _press(panel, _x_of(panel, 68))
    _move(panel, _x_of(panel, 20))
    a, b = panel.ruler_span()
    assert a < b
    assert (b - a) == pytest.approx(48.0, abs=1.2)


def test_the_ruler_stays_inside_the_curve(panel):
    """拉出面板外面不該量到「第 -30 個取樣點」—— 那個位置在影像上不存在。"""
    _press(panel, _x_of(panel, 4))
    _move(panel, -500.0)
    a, _b = panel.ruler_span()
    assert a >= 0.0

    _move(panel, 5000.0)
    _a, b = panel.ruler_span()
    assert b <= len(panel._data["profile"]) - 1


def test_a_card_with_no_curve_cannot_be_measured(qapp):
    """空面板按下去不能留下一把量不出東西的尺。"""
    empty = widgets_mod.ProfilePanel()
    empty.resize(400, 120)
    _press(empty, 100.0)
    assert empty.ruler_span() is None


def test_switching_card_drops_the_ruler(panel, record):
    """換一張卡（面板改餵別的資料）之後，上一把尺不能留著 —— 它量的是上一條
    曲線的座標，畫在新曲線上是錯的。"""
    _press(panel, _x_of(panel, 20))
    _move(panel, _x_of(panel, 68))
    panel.set_data("flat stripes", record["y"])
    assert panel.ruler_span() is None


# --------------------------------------------------------------------------- #
# 2. 讀數要答得出 pitch
# --------------------------------------------------------------------------- #
def test_the_readout_gives_the_pitch_not_just_the_distance(panel):
    """量一個週期是所有量法裡最不準的一種（兩端各差一個像素 → pitch 差兩個）。
    橫跨好幾根再除以根數，誤差被根數除掉 —— 所以讀數要順便講 pitch。"""
    _press(panel, _x_of(panel, 2))
    _move(panel, _x_of(panel, 110))
    text = panel.ruler_text()

    assert "px" in text and "stripes" in text and "pitch" in text
    pitch = float(text.split("pitch")[1].split("px")[0])
    assert pitch == pytest.approx(MG_PITCH, abs=1.0), text


def test_a_short_drag_still_gives_the_distance(panel):
    """一根條紋都沒跨過去也要有讀數 —— 尺本來就要能當尺用。"""
    _press(panel, _x_of(panel, 30))
    _move(panel, _x_of(panel, 36))
    text = panel.ruler_text()
    assert "px" in text
    assert "pitch" not in text, "只跨到一根條紋，算不出 pitch 卻報了一個"


def test_the_measured_pitch_can_be_compared_with_the_cards_pitch(panel, record):
    """量出來的東西要跟卡片正在用的 pitch 是**同一個單位**，不然對照不了。"""
    _press(panel, _x_of(panel, 2))
    _move(panel, _x_of(panel, 110))
    pitch = float(panel.ruler_text().split("pitch")[1].split("px")[0])
    assert pitch == pytest.approx(float(record["x"]["pitch_used"]), abs=1.0)


# --------------------------------------------------------------------------- #
# 3. 綠色，而且畫得出來
# --------------------------------------------------------------------------- #
def test_the_ruler_is_drawn_in_green(panel):
    """跟畫面上其他東西**換一個色相**：曲線是墨色、轉折線是 accent。
    再從那一家挑一個色階的話，「哪一條是我剛剛拉的」就只剩深淺可分。"""
    from PySide6.QtGui import QColor, QImage

    def greens() -> int:
        img = QImage(400, 120, QImage.Format_ARGB32)
        img.fill(0)
        panel.render(img)
        want = QColor(widgets_mod.TOKENS["success"])
        n = 0
        for x in range(0, 400):
            for y in range(20, 100, 4):
                c = QColor(QImage.pixelColor(img, x, y))
                if (abs(c.hue() - want.hue()) < 20 and c.saturation() > 40
                        and abs(c.value() - want.value()) < 90):
                    n += 1
        return n

    before = greens()
    _press(panel, _x_of(panel, 30))
    _move(panel, _x_of(panel, 90))
    after = greens()
    assert after > before + 10, "尺畫出來的綠只有 %d 個畫素（原本 %d）" % (
        after, before)


# --------------------------------------------------------------------------- #
# 4. 上面那張影像要同步
# --------------------------------------------------------------------------- #
def test_the_image_view_marks_the_same_stretch(qapp):
    view = widgets_mod.ImageView()
    view.set_image(_img())
    assert view.measure_span() is None

    view.set_measure("x", 68.0, 20.0)          # 反過來給也要正規化
    assert view.measure_span() == ("x", 20.0, 68.0)

    view.clear_measure()
    assert view.measure_span() is None


def test_the_image_view_ignores_a_direction_it_cannot_draw(qapp):
    """軸名錯了要當成「沒有東西可標」，不能拿一個猜的方向去畫。"""
    view = widgets_mod.ImageView()
    view.set_image(_img())
    view.set_measure("", 10.0, 20.0)
    assert view.measure_span() is None


def test_the_band_shows_up_on_the_image(qapp):
    from PySide6.QtGui import QColor, QImage

    view = widgets_mod.ImageView()
    view.set_image(np.full((64, 64), 128.0, np.float32))
    view.resize(200, 200)
    view.fit()

    def greens() -> int:
        img = QImage(200, 200, QImage.Format_ARGB32)
        img.fill(0)
        view.render(img)
        want = QColor(widgets_mod.TOKENS["success"])
        return sum(1 for x in range(0, 200, 2) for y in range(0, 200, 2)
                   if abs(QColor(QImage.pixelColor(img, x, y)).hue()
                          - want.hue()) < 25
                   and QColor(QImage.pixelColor(img, x, y)).saturation() > 25)

    before = greens()
    view.set_measure("x", 20.0, 44.0)
    assert greens() > before + 20


# --------------------------------------------------------------------------- #
# 5. 接起來了（面板 → 儀表 → 主視窗 → 影像）
# --------------------------------------------------------------------------- #
def test_the_inspector_forwards_both_curves(qapp, record):
    """兩條曲線各有一把尺，兩把都要通到影像上。"""
    insp = insp_mod.CrossInspector()
    insp.set_context("cross", {"roi_out": "xing"},
                     meta={"crossings": {"xing": record}})
    seen = []
    insp.measure_changed.connect(lambda *a: seen.append(a))
    insp.measure_ended.connect(lambda: seen.append(("ended",)))

    for p in (insp.across, insp.down):
        p.resize(400, 120)
        _press(p, _x_of(p, 20))
        _move(p, _x_of(p, 60))
        _release(p, _x_of(p, 60))

    assert [a[0] for a in seen if a[0] in ("x", "y")] == ["x", "x", "y", "y"]
    assert seen.count(("ended",)) == 2


@pytest.fixture(scope="module")
def lines_lot(tmp_path_factory):
    from make_sample import generate

    return generate(str(tmp_path_factory.mktemp("f8_ruler")), n=4, seed=4,
                    size=128, pitch=18, noise=4.0, pattern="lines")


def test_holding_the_ruler_marks_the_preview_image(qapp, lines_lot):
    """使用者原話的後半段：「按住時上方 image stream 也能同步顯示」。"""
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        win.load_dataset_path(lines_lot["klarf"], sync=True)
        nid = wire_up(win.model, win.model.add_step("roi_cross"))
        win.model.set_param(nid, "roi_out", "xing")
        win.select_node(nid)
        win.refresh_preview(sync=True)

        insp = win.inspector()
        assert isinstance(insp, insp_mod.CrossInspector)
        assert insp.across.has_data() is True
        insp.across.resize(400, 120)

        assert win.image_view.measure_span() is None
        _press(insp.across, _x_of(insp.across, 12))
        _move(insp.across, _x_of(insp.across, 90))

        span = win.image_view.measure_span()
        assert span is not None, "按著尺，影像上什麼都沒標"
        assert span[0] == "x"
        assert span[2] - span[1] == pytest.approx(78.0, abs=2.0)

        _release(insp.across, _x_of(insp.across, 90))
        assert win.image_view.measure_span() is None, "放開了還留在影像上"
    finally:
        win.close()


def test_leaving_the_card_clears_the_band(qapp, lines_lot):
    """面板被拆掉就不會再有「放開」—— 綠帶會永遠留在影像上。"""
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        win.load_dataset_path(lines_lot["klarf"], sync=True)
        nid = wire_up(win.model, win.model.add_step("roi_cross"))
        win.select_node(nid)
        win.refresh_preview(sync=True)
        insp = win.inspector()
        insp.across.resize(400, 120)
        _press(insp.across, _x_of(insp.across, 12))
        _move(insp.across, _x_of(insp.across, 90))
        assert win.image_view.measure_span() is not None

        other = wire_up(win.model, win.model.add_step("align"))
        win.select_node(other)
        assert win.image_view.measure_span() is None
    finally:
        win.close()
