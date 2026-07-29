# ADEPT Studio UI 元件測試 — authored 2026-07-28 (M3).
"""``adept/ui/theme.py`` 與 ``adept/ui/widgets.py`` 的離屏（offscreen）測試。

執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_widgets.py -q``

**為什麼所有 Qt import 都是 lazy 的（別改回去）**

``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
PySide6 模組。pytest 是「先蒐集全部測試檔、再開始跑」，所以只要這個檔案在
**模組層** ``import PySide6``，蒐集階段就會把 Qt 塞進 ``sys.modules``，那個守門測試
就會紅 —— 即使它先跑。

因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
每個測試都必須要求 ``qapp`` fixture，否則那些名字不存在。

pytest-qt 沒有安裝：訊號一律用手動 slot（append 到 list）捕捉，滑鼠事件用
``QTest`` 或自己建構 ``QMouseEvent`` 後 ``QApplication.sendEvent`` 派送
（離屏平台上 ``QTest.mouseMove`` 不可靠，拖曳的中間段自己派送最穩）。
"""
from __future__ import annotations

import sys

import numpy as np
import pytest


def _load_qt() -> None:
    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: F401
    from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: F401
    from PySide6.QtTest import QTest  # noqa: F401
    from PySide6.QtWidgets import (  # noqa: F401
        QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QLineEdit,
        QSpinBox,
    )

    from adept.ui import theme as theme_mod  # noqa: F401
    from adept.ui import widgets as widgets_mod  # noqa: F401
    from adept.ui import viewmodel as vm_mod  # noqa: F401

    globals().update(locals())


@pytest.fixture(scope="module")
def qapp():
    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
    _load_qt()
    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
    theme_mod.apply_theme(app)
    yield app
    app.processEvents()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _steps():
    """真實 registry 的 describe() dict（不是手捏的假資料）。"""
    import adept.core.steps  # noqa: F401 — 觸發註冊
    from adept.core.pipeline import list_steps

    return [s.describe() for s in list_steps()]


def _describe(key):
    import adept.core.steps  # noqa: F401
    from adept.core.pipeline import get_step

    return get_step(key).describe()


def _mouse(widget, etype, pos, button=None, buttons=None):
    """建構並派送一顆滑鼠事件（離屏環境下比 QTest.mouseMove 可靠）。"""
    button = Qt.NoButton if button is None else button
    buttons = button if buttons is None else buttons
    ev = QMouseEvent(etype, QPointF(pos), QPointF(pos), button, buttons,
                     Qt.NoModifier)
    QApplication.sendEvent(widget, ev)



# --------------------------------------------------------------------------- #
# theme
# --------------------------------------------------------------------------- #
def _rgb(hexstr):
    h = str(hexstr).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def test_theme_applies_and_has_adept_tokens(qapp):
    assert qapp.styleSheet(), "apply_theme 應該有裝上 QSS"
    qss = theme_mod.build_stylesheet()
    # 主要動作按鈕靠 objectName "primary"
    assert "QPushButton#primary" in qss
    for selector in ("QComboBox", "QSpinBox", "QLineEdit", "QCheckBox::indicator",
                     "QScrollBar", "QSplitter::handle", "QHeaderView::section",
                     "QToolTip", "QAbstractItemView"):
        assert selector in qss, selector


def test_theme_is_neutral_and_flat(qapp):
    """F7-2 的兩條產品要求，用性質斷言而不是寫死色碼。

    舊配色是暖奶油底 + 琥珀 accent + 填滿色塊，使用者的評語是「太像玩具」。
    這裡鎖住的是**中性**（大面積不帶色相）與**平面**（無陰影漸層），
    色碼本身還可以繼續微調。
    """
    for key in ("bg_page", "bg_panel", "bg_surface", "toolbar", "statusbar"):
        r, g, b = _rgb(theme_mod.TOKENS[key])
        assert max(r, g, b) - min(r, g, b) <= 8, \
            "%s = %s 帶了明顯色相，大面積底色要中性" % (key, theme_mod.TOKENS[key])

    qss = theme_mod.build_stylesheet()
    for banned in ("box-shadow", "qlineargradient", "qradialgradient"):
        assert banned not in qss, "平面設計不用 %s" % banned


def test_light_and_dark_palettes_have_identical_keys(qapp):
    light, dark = theme_mod.PALETTES["light"], theme_mod.PALETTES["dark"]
    assert set(light) == set(dark), set(light) ^ set(dark)
    assert set(theme_mod.TOKENS) == set(light)
    # 暗色真的比較暗（拿最大的底色面積比）
    assert sum(_rgb(dark["bg_page"])) < sum(_rgb(light["bg_page"]))


def test_set_theme_is_in_place_and_reversible(qapp):
    """``TOKENS`` 必須是**同一個物件** —— 各模組都 import 過它了。"""
    before = theme_mod.TOKENS
    try:
        theme_mod.set_theme("dark")
        assert theme_mod.TOKENS is before, "set_theme 不可以換掉 TOKENS 物件"
        assert theme_mod.current_theme() == "dark"
        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["dark"]["bg_page"]
        assert theme_mod.seg_hex("algo") == theme_mod.PALETTES["dark"]["seg_algo"]

        # 不認得的名字要退回預設，不能炸
        assert theme_mod.set_theme("nope") == theme_mod.DEFAULT_THEME
    finally:
        theme_mod.apply_theme(qapp, "light")
    assert theme_mod.current_theme() == "light"


def test_theme_segment_tokens(qapp):
    t = theme_mod.TOKENS
    for cat in ("image", "algo", "adc"):
        assert t["seg_%s" % cat].startswith("#")
        assert t["seg_%s_bg" % cat].startswith("#")
    for tone in ("good", "bad", "neutral"):
        for part in ("bg", "text", "border"):
            assert t["chip_%s_%s" % (tone, part)].startswith("#")


def test_seg_color_mapping(qapp):
    for cat in ("image", "algo", "adc"):
        assert theme_mod.seg_color(cat).name() == theme_mod.TOKENS["seg_%s" % cat]
        assert theme_mod.seg_bg(cat).name() == theme_mod.TOKENS["seg_%s_bg" % cat]
    assert theme_mod.seg_color("algo", bg=True).name() == theme_mod.TOKENS["seg_algo_bg"]
    # 未知分類要有中性退路，不能炸
    assert theme_mod.seg_color("nope").isValid()


# --------------------------------------------------------------------------- #
# 1. ImageView
# --------------------------------------------------------------------------- #
def test_image_view_uint8_float_and_none(qapp):
    view = widgets_mod.ImageView()
    view.resize(320, 240)

    assert view.has_image() is False          # 初始 = 空狀態（畫「（無影像）」）

    u8 = np.arange(256, dtype=np.uint8).reshape(16, 16)
    view.set_image(u8)
    assert view.has_image()
    assert view.image().dtype == np.uint8
    np.testing.assert_array_equal(view.image(), u8)   # uint8 直接用，不做拉伸
    assert view.scale() > 1.0                          # 16x16 塞進 320x240 -> 放大

    # float + NaN：自動 min-max，NaN 不參與統計也不會炸
    f = np.full((8, 8), np.nan, dtype=np.float32)
    f[0, 0] = -2.0
    f[7, 7] = 6.0
    view.set_image(f)
    shown = view.image()
    assert shown.dtype == np.uint8
    assert shown[0, 0] == 0 and shown[7, 7] == 255
    assert shown[3, 3] == 0                            # NaN -> 0

    # 全 NaN 不應該爆
    view.set_image(np.full((4, 4), np.nan, dtype=np.float32))
    assert int(view.image().max()) == 0

    view.set_image(None)
    assert view.has_image() is False


def test_image_view_wheel_zoom_changes_scale(qapp):
    view = widgets_mod.ImageView()
    view.resize(300, 200)
    view.set_image(np.zeros((50, 50), dtype=np.uint8))
    before = view.scale()

    ev = QWheelEvent(QPointF(120, 90), QPointF(120, 90), QPoint(0, 0),
                     QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                     Qt.NoScrollPhase, False)
    QApplication.sendEvent(view, ev)
    assert view.scale() > before

    ev_out = QWheelEvent(QPointF(120, 90), QPointF(120, 90), QPoint(0, 0),
                         QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                         Qt.NoScrollPhase, False)
    QApplication.sendEvent(view, ev_out)
    assert view.scale() == pytest.approx(before, rel=1e-6)

    view.zoom_by(4.0)
    assert view.scale() > before
    view.fit()                                   # 雙擊走的是同一條路
    assert view.scale() == pytest.approx(before, rel=1e-6)


# --------------------------------------------------------------------------- #
# 2. ParamForm（用真實 registry 的卡片）
# --------------------------------------------------------------------------- #
def test_param_form_int_and_image_key_from_snr_map(qapp):
    form = widgets_mod.ParamForm()
    edits = []
    form.param_edited.connect(lambda n, v: edits.append((n, v)))

    desc = _describe("snr_map")
    streams = ["test", "ref", "diff", "ref_aligned"]
    form.set_step(desc, {"window": 31}, streams)

    # 每個 ParamSpec 都要有一列
    assert form.param_names() == [p["name"] for p in desc["params"]]
    # 建表本身不可以噴 param_edited
    assert edits == []

    window = form.editor("window")
    assert isinstance(window, QSpinBox)
    assert (window.minimum(), window.maximum()) == (5, 201)
    assert window.value() == 31
    window.setValue(41)
    assert edits[-1] == ("window", 41)
    assert isinstance(edits[-1][1], int)

    clip = form.editor("clip_sigma")
    assert isinstance(clip, QDoubleSpinBox)
    assert clip.value() == pytest.approx(3.0)
    clip.setValue(4.5)
    assert edits[-1] == ("clip_sigma", pytest.approx(4.5))
    assert isinstance(edits[-1][1], float)

    # image_key -> 可編輯下拉，內容 = 呼叫端給的影像流
    source = form.editor("source")
    assert isinstance(source, QComboBox) and source.isEditable()
    assert [source.itemText(i) for i in range(source.count())] == streams
    assert source.currentText() == "diff"
    source.setCurrentText("ref_aligned")
    assert edits[-1] == ("source", "ref_aligned")

    # 每一列都看得見白話 help（推廣鐵則）
    for spec in desc["params"]:
        assert form.hint_text(spec["name"]) == spec["help"]
        assert spec["help"]


def test_param_form_bool_choice_and_str(qapp):
    form = widgets_mod.ParamForm()
    edits = []
    form.param_edited.connect(lambda n, v: edits.append((n, v)))

    # bool -> QCheckBox（subtract.absolute 預設 True）
    form.set_step(_describe("subtract"), {}, ["test", "ref_aligned"])
    absolute = form.editor("absolute")
    assert isinstance(absolute, QCheckBox)
    assert absolute.isChecked() is True
    absolute.setChecked(False)
    assert edits[-1] == ("absolute", False)
    assert isinstance(edits[-1][1], bool)

    # choice -> 非可編輯 QComboBox，選項 = spec.choices
    edits.clear()
    desc = _describe("align")
    form.set_step(desc, {}, ["test", "ref"])
    method = form.editor("method")
    choices = [p for p in desc["params"] if p["name"] == "method"][0]["choices"]
    assert isinstance(method, QComboBox) and not method.isEditable()
    assert [method.itemText(i) for i in range(method.count())] == choices
    assert method.currentText() == "phase"
    method.setCurrentText("ncc")
    assert edits[-1] == ("method", "ncc")

    # int 有下限：search_radius 1..64
    radius = form.editor("search_radius")
    assert (radius.minimum(), radius.maximum()) == (1, 64)

    # str -> QLineEdit（load_patch.channels）
    edits.clear()
    form.set_step(_describe("load_patch"), {}, [])
    channels = form.editor("channels")
    assert isinstance(channels, QLineEdit)
    assert channels.text() == "auto"
    channels.setText("test,ref")
    assert edits[-1] == ("channels", "test,ref")
    assert isinstance(edits[-1][1], str)


def test_param_form_show_and_clear_errors(qapp):
    form = widgets_mod.ParamForm()
    desc = _describe("snr_map")
    form.set_step(desc, {}, ["diff"])
    help_text = [p for p in desc["params"] if p["name"] == "window"][0]["help"]

    assert form.has_error("window") is False
    form.show_error("window", "參數 'window'：4 低於下限 5")
    assert form.has_error("window") is True
    assert "低於下限 5" in form.hint_text("window")
    assert "color:%s" % theme_mod.TOKENS["danger_text"] in \
        form._rows["window"].hint.styleSheet()
    assert form.has_error("out") is False        # 其他列不受影響

    form.clear_errors()
    assert form.has_error("window") is False
    assert form.hint_text("window") == help_text


def test_param_form_empty_state(qapp):
    form = widgets_mod.ParamForm()
    form.set_step(None, {}, [])
    assert form.param_names() == []
    assert form.step_key() is None


# --------------------------------------------------------------------------- #
# 3. LibraryPanel
# --------------------------------------------------------------------------- #
def test_library_panel_groups_and_double_click(qapp):
    """F7-3：卡片庫改依**流程階段**分組（不是依 category 的影像／算法）。"""
    panel = widgets_mod.LibraryPanel()
    steps = _steps()
    panel.set_steps(steps)

    assert panel.section_titles() == [
        "Input", "Enhance", "Region", "Compare", "Measure", "ADC"]
    assert set(panel.step_keys()) == {s["key"] for s in steps}

    # 每張卡都被歸進宣告的那一段
    by_group = {}
    for s_ in steps:
        by_group.setdefault(s_["group"], set()).add(s_["key"])
    assert "load_patch" in by_group["input"]
    assert {"subtract", "align"} <= by_group["compare"]
    assert "blob_segment" in by_group["region"]
    assert {"glv_stats", "cd_measure", "roi_snr"} <= by_group["measure"]

    # 空的段落要留一行提示（registry 目前沒有 adc 卡片）
    empties = [lbl for lbl in panel.findChildren(QLabel)
               if lbl.objectName() == "libEmpty"]
    assert len(empties) == sum(
        1 for g, _t, _s in panel.GROUPS if not by_group.get(g))

    got = []
    panel.add_requested.connect(got.append)

    snr_desc = _describe("snr_map")
    item = panel.entry("snr_map")
    assert item is not None
    assert item.label.text() == snr_desc["label"]
    assert item.toolTip() == snr_desc["help"]             # help 掛成 tooltip
    QTest.mouseDClick(item, Qt.LeftButton)
    assert got == ["snr_map"]

    # 另一條路：hover 出現的「Add」按鈕
    other = panel.entry("align")
    assert other.add_button.text() == "Add"
    other.add_button.click()
    assert got == ["snr_map", "align"]

    # 重新 set_steps 不會留下舊項目
    panel.set_steps([s_ for s_ in steps if s_["group"] == "compare"])
    assert panel.entry("snr_map") is None
    assert panel.entry("align") is not None


def test_library_search_filters_cards_and_hides_empty_sections(qapp):
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    panel.toggle_group(None)                 # 全部收起來，只靠搜尋
    everything = set(panel.step_keys())

    panel.set_query("snr")
    hit = set(panel.visible_step_keys())
    assert {"snr_map", "roi_snr", "blob_segment"} <= hit
    assert "denoise" not in hit
    assert "Input" not in panel.visible_section_titles(), \
        "整組都沒命中的區塊標題要一起收起來"

    # 多個詞是 AND；說明文字也在搜尋範圍內
    panel.set_query("region blob")
    assert set(panel.visible_step_keys()) == {"blob_segment"}

    # F7-7：清空搜尋之後回到 rail 的狀態（這裡是全部收起來），不是全部攤開
    panel.set_query("")
    assert panel.open_group() is None
    assert panel.visible_step_keys() == []

    panel.toggle_group("enhance")
    assert set(panel.visible_step_keys()) < everything
    assert panel.visible_section_titles() == ["Enhance"]


def test_library_badges_unmet_prerequisites_but_still_allows_adding(qapp):
    """前置條件沒滿足 → 標 ``needs …`` 並調淡，**但不擋著不給加**。

    卡片庫的順序不是執行順序：使用者可能先放卡再補上游。擋住只會讓人以為壞了。
    """
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())

    # 還不知道上游有什麼 -> 一個 badge 都不該出現（別在空流程上嚇人）
    assert not [k for k in panel.step_keys() if panel.entry(k).badge_text()]

    panel.set_available_streams(["test", "ref"])
    assert panel.entry("snr_map").badge_text() == "needs diff"
    assert panel.entry("subtract").badge_text() == "needs ref_aligned"
    assert panel.entry("denoise").badge_text() == ""      # 只讀 test，滿足了

    got = []
    panel.add_requested.connect(got.append)
    panel.entry("snr_map").add_button.click()
    assert got == ["snr_map"], "有 badge 的卡仍然要加得進去"

    # 上游補齊之後 badge 要消失
    panel.set_available_streams(["test", "ref", "ref_aligned", "diff"])
    assert panel.entry("snr_map").badge_text() == ""
    assert panel.entry("subtract").badge_text() == ""


def test_group_icons_are_painted_not_files(qapp):
    """icon 一律 QPainter 畫 —— repo 有「只放純文字檔」的不變量。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    # 每個階段有兩個 icon：rail 上的大顆 + 展開區的小標題；
    # 再加 rail 底部的搜尋鈕（它不是流程階段，所以不在 stage_buttons 裡）
    icons = panel.findChildren(widgets_mod.GroupIcon)
    assert len(icons) == 2 * len(panel.GROUPS) + 1
    assert len(panel.stage_buttons) == len(panel.GROUPS)
    assert panel.search_button.group == "search"
    assert all(i.width() > 0 and i.height() > 0 for i in icons)

    # 換主題之後 icon 要跟著換色
    before = [i.color for i in icons]
    theme_mod.set_theme("dark")
    try:
        panel.refresh_colors()
        assert [i.color for i in icons] != before
    finally:
        theme_mod.set_theme("light")
        panel.refresh_colors()


# --------------------------------------------------------------------------- #
# 4. PipelinePanel
# --------------------------------------------------------------------------- #
def _nodes():
    return [
        {"node_id": "load_patch", "step_key": "load_patch", "label": "載入影像",
         "category": "image", "enabled": True, "summary": "channels=auto"},
        {"node_id": "align", "step_key": "align", "label": "對位",
         "category": "image", "enabled": False, "summary": "phase · r=8"},
        {"node_id": "snr_map", "step_key": "snr_map", "label": "SNR 地圖",
         "category": "algo", "enabled": True, "summary": "window=31"},
        {"node_id": "verdict", "step_key": "verdict", "label": "判定",
         "category": "adc", "enabled": True, "summary": ""},
    ]


def test_pipeline_panel_signals_and_styling(qapp):
    panel = widgets_mod.PipelinePanel()
    nodes = _nodes()
    panel.set_nodes(nodes)
    assert panel.node_ids() == ["load_patch", "align", "snr_map", "verdict"]

    selected, toggled, moved, removed, scored = [], [], [], [], []
    panel.node_selected.connect(selected.append)
    panel.node_toggled.connect(lambda n, v: toggled.append((n, v)))
    panel.move_requested.connect(lambda n, d: moved.append((n, d)))
    panel.remove_requested.connect(removed.append)
    panel.score_clicked.connect(lambda: scored.append(True))

    # 左側 4px 色條 = 該段顏色；停用的節點轉灰
    algo_card = panel.card("snr_map")
    assert algo_card.bar.width() == 4
    assert theme_mod.seg_hex("algo") in algo_card.bar.styleSheet()
    disabled_card = panel.card("align")
    assert theme_mod.TOKENS["seg_disabled"] in disabled_card.bar.styleSheet()
    assert disabled_card.chk.isChecked() is False

    # 點卡片 -> 選取 + accent ring
    _mouse(algo_card, QEvent.MouseButtonPress, QPointF(30, 10),
           Qt.LeftButton, Qt.LeftButton)
    assert selected == ["snr_map"]
    assert panel.selected() == "snr_map"
    assert theme_mod.TOKENS["accent"] in algo_card.styleSheet()
    assert theme_mod.TOKENS["accent"] not in panel.card("verdict").styleSheet()

    # 每張卡的 ↑ ↓ ✕ 與啟用勾
    panel.card("snr_map").btn_up.click()
    panel.card("snr_map").btn_down.click()
    panel.card("verdict").btn_remove.click()
    panel.card("align").chk.setChecked(True)
    assert moved == [("snr_map", -1), ("snr_map", 1)]
    assert removed == ["verdict"]
    assert toggled == [("align", True)]

    # 固定尾卡 Score / Bin
    panel.set_score_summary("snr_peak * 2", 3.5)
    text = panel.score_summary_text()
    assert "snr_peak * 2" in text and "3.5" in text
    _mouse(panel.score_card, QEvent.MouseButtonPress, QPointF(20, 10),
           Qt.LeftButton, Qt.LeftButton)
    assert scored == [True]


def test_pipeline_panel_selection_survives_set_nodes(qapp):
    panel = widgets_mod.PipelinePanel()
    panel.set_nodes(_nodes())
    panel.set_selected("align")
    assert panel.selected() == "align"

    # 重新餵資料（改了摘要）：選取要留著
    nodes = _nodes()
    nodes[1]["summary"] = "ncc · r=12"
    panel.set_nodes(nodes)
    assert panel.selected() == "align"
    assert theme_mod.TOKENS["accent"] in panel.card("align").styleSheet()
    assert panel.card("align").summary.text() == "ncc · r=12"

    # 被選的節點消失了 -> 選取清掉，不留幽靈
    panel.set_nodes([n for n in nodes if n["node_id"] != "align"])
    assert panel.selected() is None
    assert panel.card("align") is None

    panel.set_nodes([])
    assert panel.node_ids() == []


# --------------------------------------------------------------------------- #
# 5. HistogramWidget
# --------------------------------------------------------------------------- #
def test_histogram_data_threshold_and_drag(qapp):
    hist = widgets_mod.HistogramWidget()
    hist.resize(420, 220)

    scores = [0.5, 1.0, 1.2, 2.0, 2.4, 3.0, 3.1, 3.9, 4.5, 5.0]
    edges, counts = vm_mod.histogram(scores, n_bins=8)
    hist.set_data(edges, counts)
    assert hist.has_data()

    hist.set_threshold(3.0)
    assert hist.threshold() == pytest.approx(3.0)
    # set_threshold 是程式設定，不該回頭發訊號
    changed, committed = [], []
    hist.threshold_changed.connect(changed.append)
    hist.threshold_committed.connect(committed.append)
    hist.set_threshold(2.5)
    assert changed == [] and committed == []

    rect = hist._plot_rect()
    y = rect.center().y()
    start = QPointF(rect.left() + 20, y)
    mid = QPointF(rect.center().x(), y)
    end = QPointF(rect.right() - 20, y)

    _mouse(hist, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseMove, mid, Qt.NoButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)

    assert len(changed) >= 3, "拖曳過程要連續發 threshold_changed"
    assert len(committed) == 1, "放開才 commit 一次"
    lo, hi = edges[0], edges[-1]
    for v in changed:
        assert lo <= v <= hi
    assert changed[0] < changed[-1]                      # 由左拖到右
    assert committed[0] == pytest.approx(changed[-1])
    assert hist.threshold() == pytest.approx(committed[0])
    assert hist.threshold() == pytest.approx(hi, abs=(hi - lo) * 0.2)

    # 拖出範圍也要夾在 [lo, hi] 內
    changed.clear()
    _mouse(hist, QEvent.MouseButtonPress, QPointF(rect.right() - 1, y),
           Qt.LeftButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseMove, QPointF(rect.right() + 500, y),
           Qt.NoButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseButtonRelease, QPointF(rect.right() + 500, y),
           Qt.LeftButton, Qt.NoButton)
    assert hist.threshold() == pytest.approx(hi)
    assert all(lo <= v <= hi for v in changed)


def test_histogram_bin_summary_tooltip_and_empty(qapp):
    hist = widgets_mod.HistogramWidget()
    hist.resize(420, 220)

    # 空狀態
    assert hist.has_data() is False
    assert hist.bin_summary_text() == ""
    hist.set_data([0.0, 1.0], [0])                       # viewmodel 的空回傳
    assert hist.has_data() is False

    scores = [0.5, 1.0, 1.2, 2.0, 2.4, 3.0, 3.1, 3.9, 4.5, 5.0]
    edges, counts = vm_mod.histogram(scores, n_bins=8)
    hist.set_data(edges, counts)

    hist.set_bin_summary(vm_mod.rebin(scores, 3.0))
    text = hist.bin_summary_text()
    assert text.startswith("bin 0=") and "bin 1=" in text
    assert text == "bin 0=5   bin 1=5"

    # hover 某根長條 -> tooltip「score a–b：N 顆」
    rect = hist._plot_rect()
    bw = rect.width() / len(counts)
    idx = next(i for i, c in enumerate(counts) if c > 0)
    _mouse(hist, QEvent.MouseMove,
           QPointF(rect.left() + bw * (idx + 0.5), rect.bottom() - 4))
    tip = hist.toolTip()
    assert "score" in tip and "defects" in tip and "–" in tip
    assert tip.endswith("%d defects" % counts[idx])

    hist.set_bin_summary({})
    assert hist.bin_summary_text() == ""


# --------------------------------------------------------------------------- #
# 6. FeatureTable / VerdictChip
# --------------------------------------------------------------------------- #
def test_feature_table_formatting_and_score_pinned_last(qapp):
    table = widgets_mod.FeatureTable()
    table.set_features(
        {"score": 8.5, "snr_peak": 4.23456, "blob_area": 12.0,
         "glv_mean": 128.0, "tiny": 0.00002},
        highlight={"snr_peak"},
    )
    assert table.columnCount() == 2
    assert [table.horizontalHeaderItem(i).text() for i in range(2)] == ["Feature", "Value"]

    names = table.feature_names()
    assert names[-1] == "score"                          # score 釘最後
    assert set(names) == {"score", "snr_peak", "blob_area", "glv_mean", "tiny"}

    assert table.value_text("blob_area") == "12"         # 乾淨整數
    assert table.value_text("glv_mean") == "128"
    assert table.value_text("snr_peak") == "4.235"       # 3 位小數
    assert table.value_text("tiny") == "2e-05"           # 極小值不要變成 0.000
    assert table.value_text("score") == "8.500"

    score_row = names.index("score")
    assert table.item(score_row, 0).font().bold() is True
    assert table.item(score_row, 1).font().bold() is True

    hi_row = names.index("snr_peak")
    assert table.item(hi_row, 0).background().color().name() == \
        theme_mod.TOKENS["accent_bg"]

    table.set_features({})                               # 清空不該炸
    assert table.rowCount() == 0


def test_verdict_chip(qapp):
    chip = widgets_mod.VerdictChip()
    assert chip.text() == "—" and chip.tone() == "neutral"

    chip.set_verdict(1)
    assert chip.text() == "bin 1 · ≥ threshold"
    assert chip.tone() == "good"
    assert theme_mod.TOKENS["chip_good_bg"] in chip.styleSheet()
    assert chip.verdict() == 1

    chip.set_verdict(0)
    assert chip.text() == "bin 0 · < threshold"
    assert chip.tone() == "bad"
    assert theme_mod.TOKENS["chip_bad_bg"] in chip.styleSheet()

    # is_real_style：bin 1 = 抓到真缺陷 = 壞消息（紅），bin 0 = 乾淨（綠）
    chip.set_verdict(1, is_real_style=True)
    assert chip.text() == "bin 1 · ≥ threshold" and chip.tone() == "bad"
    chip.set_verdict(0, is_real_style=True)
    assert chip.text() == "bin 0 · < threshold" and chip.tone() == "good"

    chip.set_verdict(None)
    assert chip.text() == "—" and chip.verdict() is None


# --------------------------------------------------------------------------- #
# 7. F7-2 換膚：切主題之後畫面上的東西不能少，也不能殘留舊色
# --------------------------------------------------------------------------- #
def test_studio_theme_toggle_keeps_everything_and_repaints(qapp):
    from adept.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        cards_before = win.library.step_keys()
        assert theme_mod.current_theme() == "light"

        assert win.toggle_theme() == "dark"
        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["dark"]["bg_page"]
        assert win.library.step_keys() == cards_before, \
            "換膚會重建卡片庫 —— 內容不可以在過程中掉東西"
        assert qapp.styleSheet().find(theme_mod.PALETTES["dark"]["bg_page"]) >= 0

        assert win.toggle_theme() == "light"
        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["light"]["bg_page"]
    finally:
        win.close()
        theme_mod.apply_theme(qapp, "light")


# --------------------------------------------------------------------------- #
# 8. F7-7 左側 rail：先選階段，才展開裡面的卡片
# --------------------------------------------------------------------------- #
def test_stage_rail_drills_down_one_stage_at_a_time(qapp):
    """一開始就把 15 張卡攤開，正是「太瑣碎」的來源。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())

    assert len(panel.stage_buttons) == len(panel.GROUPS)
    # 每顆按鈕標出該段有幾張卡
    for gid, _t, _s in panel.GROUPS:
        n = sum(1 for d in _steps() if d["group"] == gid)
        assert panel.stage_buttons[gid].count.text() == ("" if n == 0 else str(n))

    panel.toggle_group("enhance")
    assert panel.open_group() == "enhance"
    assert panel.stage_buttons["enhance"].is_active() is True
    visible = set(panel.visible_step_keys())
    assert "gamma" in visible and "subtract" not in visible, \
        "沒展開的階段不該出現在清單裡"

    # 一次只開一段
    panel.toggle_group("measure")
    assert panel.open_group() == "measure"
    assert panel.stage_buttons["enhance"].is_active() is False
    assert "glv_stats" in panel.visible_step_keys()

    # 點同一顆再一次 = 收起來
    panel.toggle_group("measure")
    assert panel.open_group() is None
    assert panel.visible_step_keys() == []


def test_search_still_reaches_across_collapsed_stages(qapp):
    """收起來的階段不該把搜尋擋住 —— 搜尋是「我不知道它在哪一段」時用的。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    panel.toggle_group(None)
    assert panel.open_group() is None

    panel.set_query("gamma")
    assert panel.visible_step_keys() == ["gamma"]
    panel.set_query("")
    assert panel.visible_step_keys() == []


def test_rail_is_vertical_and_the_card_area_gives_its_width_back(qapp):
    """F7-8：rail 像工作列一樣由上而下，收起來時整欄只剩那條圖示條。

    寬度用 ``minimumWidth()`` 驗，不用 ``width()`` —— 沒 show 過的 widget
    幾何還沒生效，那會驗到一個假的數字。
    """
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())

    assert panel.rail.layout().__class__.__name__ == "QVBoxLayout"
    assert panel.rail.width() == panel.RAIL_W
    # 「圖示要大一點」：rail 上的 icon 明顯大於區塊標題的小 icon
    assert panel.stage_buttons["input"].icon._SIZE > widgets_mod.GroupIcon._SIZE

    seen = []
    panel.panel_toggled.connect(seen.append)

    panel.toggle_group(None)
    assert panel.panel_open() is False
    assert panel.minimumWidth() == panel.RAIL_W, "收起來就該把寬度還出去"

    panel.toggle_group("region")
    assert panel.panel_open() is True
    assert panel.minimumWidth() == panel.RAIL_W + panel.PANEL_W
    assert seen == [False, True]


def test_the_search_button_survives_collapsing_the_card_area(qapp):
    """搜尋框住在卡片區裡，卡片區收起來它也跟著不見 ——
    所以 rail 上必須留一顆放大鏡，不然搜尋就再也叫不出來了。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    panel.toggle_group(None)
    assert panel.panel_open() is False

    panel.search_button.clicked.emit("search")
    assert panel.panel_open() is True, "按了放大鏡就要把卡片區帶回來"
    # 而且搜尋框真的可以打字（不是被留在隱藏的容器裡）
    assert panel.search.isVisibleTo(panel) is True
    panel.set_query("gamma")
    assert panel.visible_step_keys() == ["gamma"]
