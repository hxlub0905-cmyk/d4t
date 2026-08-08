# ADEPT Studio Gallery 測試 — authored 2026-07-28 (M5-2).
"""``adept/ui/gallery.py``（縮圖網格／同屏比多顆）的離屏（offscreen）測試。

執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_gallery.py -q``

**為什麼所有 Qt import 都是 lazy 的（別改回去）**

``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
PySide6 模組。pytest 是「先蒐集全部測試檔、再開始跑」，所以只要這個檔案在
**模組層** ``import PySide6``（或 ``import adept.ui.gallery``），蒐集階段就會把 Qt
塞進 ``sys.modules``，那個守門測試就會紅 —— 即使它先跑。

因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
每個測試都必須要求 ``qapp`` fixture，否則那些名字不存在。

pytest-qt 沒有安裝：訊號一律用手動 slot（append 到 list）捕捉，滑鼠事件自己建構
``QMouseEvent`` 後送給 ``grid.viewport()``（QAbstractScrollArea 會把 viewport 的
事件轉給 ``mousePressEvent`` / ``mouseDoubleClickEvent``）。

離屏環境的兩個小陷阱：
1. 巢狀 layout 要 ``show()`` + ``processEvents()`` 之後 viewport 才有真實尺寸，
   可視範圍的計算才有意義（只 ``resize()`` 不夠）。
2. 要讓 ``paintEvent`` 真的跑（例如驗證 QPixmap LRU 快取）就呼叫 ``widget.grab()``。
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pytest


def _load_qt() -> None:
    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: F401
    from PySide6.QtGui import QMouseEvent  # noqa: F401
    from PySide6.QtWidgets import QApplication, QWidget  # noqa: F401

    from adept.ui import gallery as gal_mod  # noqa: F401
    from adept.ui import theme as theme_mod  # noqa: F401

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
def _items(n=20, with_thumb=False, thumb_px=32):
    """n 顆合成結果（形狀 = ``engine.result_to_json_dict`` 再加一個 thumb）。"""
    out = []
    for i in range(n):
        out.append({
            "defect_id": "D%03d" % i,
            "ok": True,
            "error": None,
            "score": float(i),
            "bin": 1 if i % 2 else 0,
            "features": {"snr": float((i * 7) % 13), "area": float(i * 2)},
            "thumb": (np.full((thumb_px, thumb_px), (i * 11) % 256, np.uint8)
                      if with_thumb else None),
        })
    return out


def _panel(qapp, items=None, w=820, h=560):
    """建一個已經 show 過、viewport 有真實尺寸的 GalleryPanel。"""
    p = gal_mod.GalleryPanel()
    p.resize(w, h)
    p.show()
    qapp.processEvents()
    if items is not None:
        p.set_items(items)
        qapp.processEvents()
    return p


def _mouse(widget, etype, pos, button=None, buttons=None, mods=None):
    """建構並派送一顆滑鼠事件（離屏環境下比 QTest 可靠）。"""
    button = Qt.LeftButton if button is None else button
    buttons = button if buttons is None else buttons
    mods = Qt.NoModifier if mods is None else mods
    ev = QMouseEvent(etype, QPointF(pos), QPointF(pos), button, buttons, mods)
    QApplication.sendEvent(widget, ev)


def _click(panel, index, mods=None, dbl=False):
    """點第 ``index`` 格（顯示順序）的正中央。"""
    center = panel.grid.tile_rect(index).center()
    etype = QEvent.MouseButtonDblClick if dbl else QEvent.MouseButtonPress
    _mouse(panel.grid.viewport(), etype, center, mods=mods)


def _has_cjk(text):
    return any("　" <= ch <= "鿿" for ch in str(text))


# --------------------------------------------------------------------------- #
# 1. make_thumb（Qt-free 的純運算；背景執行緒會直接呼叫它）
# --------------------------------------------------------------------------- #
def test_make_thumb_square_uint8_and_float_normalised(qapp):
    make_thumb = gal_mod.make_thumb

    # uint8 進來原樣（不拉伸），輸出一定是方形 uint8
    src = np.arange(256, dtype=np.uint8).reshape(16, 16)
    out = make_thumb(src, 64)
    assert out.shape == (64, 64)
    assert out.dtype == np.uint8
    assert int(out.min()) == 0 and int(out.max()) == 255

    # float 走 min–max 正規化（跟 ImageView 同一套規則）
    f = np.array([[0.0, 0.5], [1.0, 2.0]], dtype=np.float32)
    fo = make_thumb(f, 64)
    assert fo.dtype == np.uint8 and fo.shape == (64, 64)
    assert int(fo.min()) == 0 and int(fo.max()) == 255

    # 全 NaN 不該炸（ImageView 也是這個行為）
    nan_out = make_thumb(np.full((8, 8), np.nan, dtype=np.float32), 32)
    assert nan_out.shape == (32, 32) and int(nan_out.max()) == 0


def test_make_thumb_non_square_tiny_and_colour(qapp):
    make_thumb = gal_mod.make_thumb

    # 非方形 -> letterbox（等比縮 + 置中補黑），不裁掉邊緣的缺陷
    wide = np.full((10, 40), 200, dtype=np.uint8)
    out = make_thumb(wide, 64)
    assert out.shape == (64, 64)
    assert int(out[32, 32]) == 200        # 中間是影像
    assert int(out[0, 0]) == 0            # 上緣是補的黑邊

    # 極小輸入放大不能炸
    tiny = make_thumb(np.array([[7]], dtype=np.uint8), 96)
    assert tiny.shape == (96, 96) and int(tiny.max()) == 7
    assert make_thumb(np.zeros((1, 5), np.uint8), 64).shape == (64, 64)

    # 彩色（H,W,3）保留三通道；尺寸會被夾在合理範圍
    rgb = make_thumb(np.zeros((20, 30, 3), np.uint8), 48)
    assert rgb.shape == (48, 48, 3)
    assert make_thumb(np.zeros((9, 9), np.uint8), 1).shape == (8, 8)


# --------------------------------------------------------------------------- #
# 2. set_items / 標頭 / 空狀態
# --------------------------------------------------------------------------- #
def test_set_items_header_count_and_empty_state(qapp):
    p = _panel(qapp, _items(20))
    assert p.total_count() == 20 and p.displayed_count() == 20
    assert p.header_text() == "Showing 20 / 20 defects"
    assert p.empty_text() == ""                       # 有 tile 就沒有空狀態文字
    assert len(p.displayed_ids()) == 20

    p.set_items([])
    qapp.processEvents()
    assert p.header_text() == "Showing 0 / 0 defects"
    assert p.empty_text() == ("(Thumbnails for every defect appear here after "
                              "a trial run)")

    # 篩到一顆都不剩 -> 換另一句（並且告訴使用者怎麼救）
    p.set_items(_items(5))
    p.filter_by_score_range(100.0, 200.0)
    assert p.displayed_count() == 0
    assert "No defect matches" in p.empty_text()
    assert p.header_text() == "Showing 0 / 5 defects"


# --------------------------------------------------------------------------- #
# 3. 虛擬捲動（10,000 顆）
# --------------------------------------------------------------------------- #
def test_virtual_scrolling_with_10k_items(qapp):
    p = _panel(qapp)
    widgets_before = len(p.findChildren(QWidget))

    big = _items(10000)
    t0 = time.time()
    p.set_items(big)
    elapsed = time.time() - t0
    assert elapsed < 1.0, "10k 顆 set_items 花了 %.3fs（太慢）" % elapsed
    assert p.total_count() == 10000 and p.displayed_count() == 10000

    # 1) tile 不是 widget：10k 顆之後子 widget 數量完全沒變
    #    （基準值 = 標頭那幾個控制項 + 下拉/捲軸自己的內部 widget，數十個而已）
    assert len(p.findChildren(QWidget)) == widgets_before
    assert widgets_before < 60

    # 2) 只有可視範圍（+1 列 overscan）會被畫
    vis = p.visible_indices()
    assert 0 < len(vis) < 200, "可視範圍應該只跟 viewport 大小有關"
    cols = p.grid.columns()
    assert len(vis) <= (p.grid.viewport().height() // p.grid._cell_h() + 3) * cols
    assert vis[0] == 0                                  # 一開始在最上面

    # 3) 捲到底 -> 可視範圍換到尾端，長度依舊小
    bar = p.grid.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    qapp.processEvents()
    vis_end = p.visible_indices()
    assert vis_end != vis
    assert vis_end[0] > vis[-1]
    assert vis_end[-1] == 9999
    assert len(vis_end) < 200

    # 4) 畫一次不會爆（paintEvent 只跑可視格）
    t0 = time.time()
    p.grid.grab()
    assert time.time() - t0 < 1.0


def test_thumbs_requested_for_visible_items_only(qapp):
    """缺縮圖時會告訴主視窗「先補這幾顆」——才有辦法漸進式載入。"""
    p = _panel(qapp)
    asked = []
    p.thumbs_requested.connect(asked.append)
    p.set_items(_items(500))
    qapp.processEvents()
    assert asked, "缺縮圖的可視範圍應該要發 thumbs_requested"
    first = asked[-1]
    assert set(first) <= set(p.displayed_ids())
    assert len(first) == len(p.visible_indices())

    # 補上其中一張之後，它就不再出現在下一次請求裡
    did = first[0]
    assert p.set_thumb(did, np.full((24, 24), 128, np.uint8)) is True
    assert p.set_thumb("不存在的顆", np.zeros((4, 4), np.uint8)) is False
    bar = p.grid.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert did not in asked[-1]


# --------------------------------------------------------------------------- #
# 4. 排序
# --------------------------------------------------------------------------- #
def test_sort_by_score_feature_and_unknown_key(qapp):
    items = _items(6)
    items[3]["score"] = None                      # 沒分數的一律排最後
    p = _panel(qapp, items)

    p.set_sort("score", descending=True)
    ids = p.displayed_ids()
    assert ids == ["D005", "D004", "D002", "D001", "D000", "D003"]
    assert p.sort_key() == "score" and p.sort_descending() is True

    p.set_sort("score", descending=False)
    assert p.displayed_ids() == ["D000", "D001", "D002", "D004", "D005", "D003"]
    assert p.sort_descending() is False

    # 任一 feature 也能排（snr = (i*7)%13）
    p.set_sort("snr", descending=True)
    expect = sorted(items, key=lambda d: d["features"]["snr"], reverse=True)
    assert p.displayed_ids() == [d["defect_id"] for d in expect]

    # defect_id 排序
    p.set_sort("defect_id", descending=False)
    assert p.displayed_ids() == ["D00%d" % i for i in range(6)]

    # 不認得的 key -> 不炸、不掉資料，維持原始順序
    p.set_sort("沒有這個欄位", descending=True)
    assert p.displayed_ids() == [d["defect_id"] for d in items]
    assert p.displayed_count() == 6

    # 取消排序（標頭 chip 的「✕」走的也是這條）
    p.set_sort(None)
    assert p.sort_key() is None
    assert p.displayed_ids() == [d["defect_id"] for d in items]


def test_sort_controls_and_chip(qapp):
    p = _panel(qapp, _items(8))
    p.set_sort_keys(["score", "snr", "area"])
    assert p.sort_keys() == ["score", "snr", "area", "defect_id"]
    assert p.sort_combo.itemText(0) == gal_mod.GalleryPanel.NO_SORT
    assert p.sort_key() == "score"
    assert p.chip_texts() == ["Sort: score ↓"]

    # 換方向鈕
    p.order_button.click()
    assert p.sort_descending() is False
    assert p.displayed_ids()[0] == "D000"
    assert p.chip_texts() == ["Sort: score ↑"]

    # 下拉換欄位
    p.sort_combo.setCurrentIndex(p.sort_keys().index("area") + 1)
    assert p.sort_key() == "area"

    # 點 chip -> 移除排序條件
    p.chips()[0].click()
    qapp.processEvents()
    assert p.sort_key() is None
    assert p.chip_texts() == []
    assert p.sort_combo.currentIndex() == 0


# --------------------------------------------------------------------------- #
# 5. 篩選
# --------------------------------------------------------------------------- #
def test_filter_by_score_range_and_clear(qapp):
    p = _panel(qapp, _items(10))
    p.set_sort("defect_id", descending=False)
    assert p.displayed_count() == 10

    p.filter_by_score_range(3.0, 5.0)             # 直方圖點一根 bar 走這條
    assert p.displayed_ids() == ["D003", "D004", "D005"]
    assert p.header_text() == "Showing 3 / 10 defects"
    assert "score" in p.filter_text()
    assert any(c.startswith("Filter:") for c in p.chip_texts())

    p.clear_filter()
    assert p.displayed_count() == 10
    assert p.header_text() == "Showing 10 / 10 defects"
    assert p.filter_text() == ""
    assert not any(c.startswith("Filter:") for c in p.chip_texts())

    # 點篩選 chip 也能移除
    p.filter_by_score_range(0.0, 1.0)
    assert p.displayed_count() == 2
    chip = [c for c in p.chips() if c.label_text.startswith("Filter:")][0]
    chip.click()
    qapp.processEvents()
    assert p.displayed_count() == 10


def test_filter_bin_failed_and_custom(qapp):
    items = _items(10)
    items[2]["ok"] = False
    items[2]["bin"] = None
    items[2]["score"] = None
    p = _panel(qapp, items)

    p.filter_by_bin(1)
    assert p.displayed_count() == 5
    assert all(i.endswith(("1", "3", "5", "7", "9")) for i in p.displayed_ids())

    p.show_failed_only()
    assert p.displayed_ids() == ["D002"]
    assert p.header_text() == "Showing 1 / 10 defects"

    p.set_filter(lambda it: (it.get("features") or {}).get("area", 0) >= 10)
    assert p.displayed_count() == 5
    assert p.filter_text() == "custom filter"

    p.set_filter(None)
    assert p.displayed_count() == 10

    with pytest.raises(ValueError):
        p.set_filter({"mode": "什麼鬼"})


# --------------------------------------------------------------------------- #
# 6. 選取 / 啟動
# --------------------------------------------------------------------------- #
def test_selection_click_ctrl_click_and_double_click(qapp):
    p = _panel(qapp, _items(12))
    p.set_sort("defect_id", descending=False)
    qapp.processEvents()

    picked, activated = [], []
    p.selection_changed.connect(picked.append)
    p.defect_activated.connect(activated.append)

    _click(p, 0)
    assert picked[-1] == ["D000"]
    assert p.selected_ids() == ["D000"]

    _click(p, 2, mods=Qt.ControlModifier)         # ctrl 加選
    assert picked[-1] == ["D000", "D002"]
    assert p.selected_ids() == ["D000", "D002"]

    _click(p, 4, mods=Qt.ShiftModifier)           # shift 連選（錨點 = 上一次點的）
    assert p.selected_ids() == ["D002", "D003", "D004"]

    _click(p, 2, mods=Qt.ControlModifier)         # ctrl 再點一次 = 取消該顆
    assert "D002" not in p.selected_ids()

    _click(p, 1)                                   # 一般點擊 = 只選這顆
    assert p.selected_ids() == ["D001"]

    activated.clear()
    _click(p, 3, dbl=True)
    assert activated == ["D003"]                   # 雙擊 -> 主視窗跳去單顆預覽
    assert p.selected_ids() == ["D003"]

    # 程式設定選取不該回頭發訊號
    n = len(picked)
    p.set_selected(["D005", "D006"])
    assert p.selected_ids() == ["D005", "D006"]
    assert len(picked) == n

    # 點空白處 -> 清空選取
    _click(p, 0)
    empty_pos = p.grid.tile_rect(0).topLeft()
    _mouse(p.grid.viewport(), QEvent.MouseButtonPress,
           empty_pos - QPointF(5, 5).toPoint())
    assert p.selected_ids() == []


# --------------------------------------------------------------------------- #
# 7. bin 色條 + 說明文字（顏色不是唯一通道）
# --------------------------------------------------------------------------- #
def test_bin_colour_bar_and_caption_carry_the_bin_number(qapp):
    items = _items(4)
    items[3]["ok"] = False
    items[3]["bin"] = None
    p = _panel(qapp, items)
    p.set_sort("defect_id", descending=False)

    cap1 = p.caption_of("D001")                    # bin 1
    assert "bin 1" in cap1 and "#D001" in cap1     # 顏色以外一定要有文字
    assert "bin 0" in p.caption_of("D000")
    assert p.caption_at(0) == p.caption_of("D000")

    # 顏色一律取自 theme token
    T = theme_mod.TOKENS
    assert p.bin_color("D001") == T["success"]     # bin 1 = 過門檻（綠）
    assert p.bin_color("D000") == T["seg_disabled"]  # bin 0 = 低調灰
    assert p.bin_color("D003") == T["danger"]      # 跑失敗 = 紅
    assert "FAILED" in p.caption_of("D003")


# --------------------------------------------------------------------------- #
# 8. QPixmap LRU 快取有上限
# --------------------------------------------------------------------------- #
def test_pixmap_cache_is_bounded(qapp):
    p = _panel(qapp, _items(1500, with_thumb=True))
    assert gal_mod.CACHE_CAP == 512

    p.grid.grab()
    first = p.cache_size()
    assert 0 < first <= gal_mod.CACHE_CAP

    bar = p.grid.verticalScrollBar()
    step = max(1, bar.maximum() // 12)
    for v in range(0, bar.maximum() + 1, step):
        bar.setValue(v)
        p.grid.grab()
        assert p.cache_size() <= gal_mod.CACHE_CAP
    assert p.cache_size() > first, "翻頁之後快取應該有被填進新的縮圖"

    # 換縮圖尺寸 -> key 不同，但上限不變
    p.set_thumb_size(144)
    assert p.thumb_size() == 144
    p.grid.grab()
    assert p.cache_size() <= gal_mod.CACHE_CAP

    # 重新餵資料要把快取清乾淨（不然會顯示上一批的圖）
    p.set_items(_items(3, with_thumb=True))
    assert p.cache_size() == 0


# --------------------------------------------------------------------------- #
# 9. 推廣鐵則：每個看得到的控制項都要有說明，而且 UI 一律英文
# --------------------------------------------------------------------------- #
def test_every_control_has_an_english_tooltip(qapp):
    p = _panel(qapp, _items(6))
    p.filter_by_score_range(1.0, 4.0)

    for name, widget in (("count", p.count_label), ("sort combo", p.sort_combo),
                         ("sort order", p.order_button), ("zoom", p.zoom_combo)):
        tip = widget.toolTip()
        assert tip, "%s has no tooltip" % name
        # UI 一律英文（中英夾雜對使用者是噪音）—— 這裡順便當成不變量鎖住
        assert not _has_cjk(tip), "%s tooltip is not English: %r" % (name, tip)

    assert p.zoom_combo.itemText(0) == "S"
    assert [p.zoom_combo.itemText(i) for i in range(p.zoom_combo.count())] == \
        ["S", "M", "L"]
    assert [s[1] for s in gal_mod.THUMB_SIZES] == [64, 96, 144]

    chips = p.chips()
    assert chips, "sort / filter conditions must be shown as chips"
    for chip in chips:
        assert chip.toolTip() and not _has_cjk(chip.toolTip())
        assert chip.text().endswith("×")           # 看得出來可以移除
        assert chip.label_text and not _has_cjk(chip.label_text)

    # 空狀態與載入中佔位也是白話英文
    p.set_items([])
    assert p.empty_text() and not _has_cjk(p.empty_text())
