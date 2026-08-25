# d4t Studio M5 接線測試 — authored 2026-07-28 (M5-3).
"""``d4t/ui/studio.py`` 的 M5 部分：Gallery 分頁、背景縮圖、直方圖聯動、輸出。

執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_studio_m5.py -q``

**為什麼所有 Qt import 都是 lazy 的（別改回去）**

``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
PySide6 模組。pytest 先蒐集全部測試檔、再開始跑，所以只要這個檔案在**模組層**
``import PySide6``（或 import ``d4t.ui.studio``），蒐集階段就會把 Qt 塞進
``sys.modules``，那個守門測試就會紅 —— 即使它先跑。

因此：所有 Qt / ``d4t.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
每個測試都必須（直接或間接）要求 ``qapp`` fixture，否則那些名字不存在。

測試一律走 ``StudioWindow`` 的公開 API（``run_trial(sync=True)`` /
``request_thumbs(sync=True)`` …）或直接 emit 元件的訊號，**不開任何對話框**、
不依賴 event loop。唯一的例外是直方圖那顆真滑鼠事件（自己建 ``QMouseEvent``
再 ``sendEvent``）—— 因為「點長條」與「拖門檻」的區分本來就是滑鼠行為。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_RECIPE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"

sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate  # noqa: E402

N = 8


def _load_qt() -> None:
    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: F401
    from PySide6.QtGui import QMouseEvent  # noqa: F401
    from PySide6.QtWidgets import QApplication  # noqa: F401

    from d4t.ui import studio as studio_mod  # noqa: F401
    from d4t.ui import theme as theme_mod  # noqa: F401

    globals().update(locals())


@pytest.fixture(scope="module")
def qapp():
    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
    _load_qt()
    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
    theme_mod.apply_theme(app)
    yield app
    app.processEvents()


@pytest.fixture(scope="module")
def synlot(tmp_path_factory):
    return generate(str(tmp_path_factory.mktemp("m5_lot")), n=N, seed=7)


@pytest.fixture(scope="module")
def window(qapp, synlot):
    """整個模組共用一個主視窗（已載入資料集 + 範例 recipe，尚未試跑）。"""
    win = studio_mod.StudioWindow()
    assert win.load_dataset_path(synlot["klarf"], sync=True) is True
    assert win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
    # 巢狀 layout 要 show + processEvents 之後 viewport 才有真實尺寸，
    # Gallery 的可視範圍計算（進而 thumbs_requested）才有意義。
    win.resize(1200, 800)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


@pytest.fixture(scope="module")
def ran(window, qapp):
    """跑一次全批（同步），之後的測試共用這批結果。"""
    assert window.run_trial(N, workers=1, sync=True) is True
    qapp.processEvents()
    return window


@pytest.fixture()
def scored(ran, qapp):
    """把畫面切回**分數的直方圖**，而且是門檻真的在決定事情的那條路。

    ⚠ 兩件事 2026-08-24 變了，而底下那幾條門檻互動的測試各踩到一個：

    * R2：那張圖預設不再開在「Score」上（樹的 recipe 沒有分數表達式，
      開在 Score 上是一根柱子）—— 不切回去的話，``set_threshold(50)`` 會被
      **夾進那個特徵的值域**（實測 50 變成 5.6）；
    * R1：有判定樹的時候門檻線整條不畫，也拖不動 —— 那正是它該有的樣子，
      所以要驗「拖得動」就得先回到二元那條路。
    """
    keep = ran.model.decide
    ran.model.decide = None
    ran.results.show_feature(ran.results.SCORE)
    ran._refresh_spread()
    qapp.processEvents()
    yield ran
    ran.model.decide = keep
    ran._refresh_spread()


def _mouse(widget, etype, pos, button=None, buttons=None):
    """建構並派送一顆滑鼠事件（離屏環境下比 QTest 可靠）。"""
    button = Qt.NoButton if button is None else button
    buttons = button if buttons is None else buttons
    ev = QMouseEvent(etype, QPointF(pos), QPointF(pos), button, buttons,
                     Qt.NoModifier)
    QApplication.sendEvent(widget, ev)


# --------------------------------------------------------------------------- #
# 1. Results 視窗（F7-5：Gallery 與直方圖從主視窗搬出去）
# --------------------------------------------------------------------------- #
def test_results_live_in_their_own_window(window):
    """主視窗只留「編流程 + 看單顆」；跑完才有意義的東西在 Results 視窗。"""
    assert window.gallery is window.results.gallery
    assert window.histogram is window.results.histogram
    assert window.results_visible() is False, "還沒跑就不該有結果視窗"

    # 主視窗的中央區只剩三欄：卡片庫 | 流程+參數 | 單顆預覽
    root = window.root_splitter
    assert root.count() == 3
    assert root.widget(0) is window.library
    assert root.widget(2) is window.preview_pane


def test_gallery_populates_after_trial(ran):
    window = ran
    assert window.gallery.total_count() == N
    assert window.gallery.displayed_count() == N
    assert len(window.trial_results) == N

    ids = window.gallery.displayed_ids()
    assert sorted(ids) == sorted(str(r["defect_id"]) for r in window.trial_results)
    # 縮圖一開始一律是 None（解碼是背景的事）。
    # **重新 populate 一次再看**：原本是跑完直接斷言，而那是在賭「背景那批
    # 還沒回來」—— 它賭的是 event loop 轉了幾圈，不是這裡要守的性質。
    # 要守的是「populate 自己不解碼」，所以就地 populate 再問。
    window._populate_gallery(window.trial_results)
    assert all(item["thumb"] is None for item in window.gallery.grid.items())
    # bin 一定寫在說明文字裡（不是只有顏色）
    assert "bin" in window.gallery.caption_at(0)

    # 排序欄位 = score + 這批真的量到的特徵
    keys = window.gallery.sort_keys()
    assert keys[0] == "score"
    assert "glv_max" in keys
    assert "defect_id" in keys
    feats = set()
    for r in window.trial_results:
        feats.update(r.get("features") or {})
    assert set(keys) == {"score", "defect_id"} | feats


# --------------------------------------------------------------------------- #
# 2. 縮圖：Gallery 要 → 背景做 → 回來貼上
# --------------------------------------------------------------------------- #
def test_thumbs_requested_leads_to_thumbs(ran, qapp):
    window = ran
    seen = []
    window.gallery.thumbs_requested.connect(lambda ids: seen.append(list(ids)))

    # F7-5：Gallery 在 Results 視窗裡，要先給它真實的 viewport 尺寸。
    window.results.resize(900, 640)
    window.show_gallery()
    qapp.processEvents()

    # ``_maybe_request_thumbs`` 對「和上次相同的可視範圍」會提早 return，
    # 而 ``ran`` 是 module-scoped —— 前面的測試已經觸發過第一次請求了。
    # 把那個備忘重置，才驗得到「量到可視範圍就會要縮圖」這件事本身。
    # （這一批全部塞得進畫面，所以範圍從頭到尾都是 (0, N)，
    #   單純再 resize 一次是不會重發的。）
    #
    # **也要把已經貼上的縮圖清掉**：背景那批可能已經回來了（那取決於 event
    # loop 轉了幾圈，不是這裡要守的性質），而已經有縮圖的顆本來就不必再要。
    window._populate_gallery(window.trial_results)
    window.gallery.grid._last_request = None
    window.gallery.grid.resize(860, 520)
    qapp.processEvents()

    assert seen, "可視範圍變動時 Gallery 應該要求縮圖"
    wanted = seen[-1]
    assert all(w in window.gallery.displayed_ids() for w in wanted)

    # 同步驅動（測試不靠 event loop）：真的去讀 TIFF 頁 + make_thumb
    n = window.request_thumbs(wanted, sync=True)
    assert n == len(wanted)

    by_id = {i["defect_id"]: i for i in window.gallery.grid.items()}
    for did in wanted:
        arr = by_id[did]["thumb"]
        assert isinstance(arr, np.ndarray)
        size = window.gallery.thumb_size()
        assert arr.shape[:2] == (size, size)
        assert arr.dtype == np.uint8

    # 認不得的 id 靜靜略過，不炸
    assert window.request_thumbs(["沒有這顆"], sync=True) == 0
    window.show_preview()


def test_thumb_worker_run_sync_and_channel_pick(ran):
    window = ran
    items = list(window.dataset.items)
    assert studio_mod.thumb_channel(items[0]) == "test"     # test → single → 其他

    jobs = [(str(it.defect_id), it) for it in items[:3]]
    out = studio_mod.ThumbWorker.run_sync(jobs, 64)
    assert set(out) == {j[0] for j in jobs}
    assert all(a.shape == (64, 64) for a in out.values())

    # 壞掉的一顆不該殺掉整批（load 會 raise，run_sync 要吞掉）
    class _Broken:
        images = {"test": object()}

        def load(self, channel):
            raise OSError("image gone")

    mixed = studio_mod.ThumbWorker.run_sync(jobs + [("bad", _Broken())], 64)
    assert set(mixed) == {j[0] for j in jobs}
    assert studio_mod.thumb_channel(_Broken()) == "test"


# --------------------------------------------------------------------------- #
# 3. Gallery → 單顆預覽
# --------------------------------------------------------------------------- #
def test_defect_activated_switches_tab_and_moves_preview(ran):
    window = ran
    window.show_gallery()
    assert window.results_visible() is True

    target = str(window.dataset.items[5].defect_id)
    window.gallery.defect_activated.emit(target)

    assert window.results_visible() is True   # 結果視窗不會因為跳單顆而關掉
    assert window.defect_index == 5
    assert str(window.dataset.items[window.defect_index].defect_id) == target
    assert target in window.status_text()

    # 不存在的 id：切回單顆預覽 + 狀態列講清楚，不炸
    window.gallery.defect_activated.emit("不存在")
    assert "is not in the current dataset" in window.status_text()


def test_gallery_selection_shows_count(ran):
    window = ran
    ids = window.gallery.displayed_ids()[:3]
    window.gallery.selection_changed.emit(list(ids))
    assert window.status_text() == "3 selected"


# --------------------------------------------------------------------------- #
# 4. 直方圖 → Gallery（調參迴圈的另一半）
# --------------------------------------------------------------------------- #
def test_bar_clicked_filters_gallery_and_switches_tab(ran):
    window = ran
    window.show_preview()
    window.gallery.clear_filter()
    lo, hi = window.histogram.bar_range(0)

    window.histogram.bar_clicked.emit(lo, hi)
    assert window.results_visible() is True
    assert "Filtered to score" in window.status_text()
    assert window.gallery.filter_text()
    shown = window.gallery.displayed_count()
    assert shown < N
    for item in window.gallery.grid.items():
        if item["defect_id"] in window.gallery.displayed_ids():
            assert lo <= item["score"] <= hi

    # 再點同一根 → 取消篩選
    window.histogram.bar_clicked.emit(lo, hi)
    assert window.gallery.displayed_count() == N
    assert window.gallery.filter_text() == ""
    assert "cleared" in window.status_text()


def test_chip_clears_filter_and_same_bar_refilters(ran):
    window = ran
    window.gallery.clear_filter()
    lo, hi = window.histogram.bar_range(0)
    window.histogram.bar_clicked.emit(lo, hi)
    filtered = window.gallery.displayed_count()

    chips = [c for c in window.gallery.chips() if c.label_text.startswith("Filter")]
    assert chips, window.gallery.chip_texts()
    chips[0].click()                                    # Gallery 上的 ✕
    assert window.gallery.displayed_count() == N

    # chip 按掉之後再點同一根 = 重新篩選（不是又切掉）
    window.histogram.bar_clicked.emit(lo, hi)
    assert window.gallery.displayed_count() == filtered
    window.gallery.clear_filter()


def test_real_click_on_bar_does_not_move_the_threshold(scored, qapp):
    """按下 + 原地放開 = 點長條（篩 Gallery）；門檻一動也不動。"""
    window = scored
    hist = window.histogram
    hist.resize(520, 200)
    qapp.processEvents()
    window.gallery.clear_filter()

    before = window.model.threshold
    hist.set_threshold(before)
    committed = []
    hist.threshold_committed.connect(committed.append)

    rect = hist._plot_rect()
    n = len(hist._counts)
    bw = rect.width() / n
    # 挑一根「離門檻線夠遠」的長條（不然那是抓門檻把手，不是點長條）
    idx = max(range(n), key=lambda i: abs(rect.left() + bw * (i + 0.5)
                                          - hist._x_at(hist.threshold())))
    pos = QPointF(rect.left() + bw * (idx + 0.5), rect.center().y())

    _mouse(hist, QEvent.MouseButtonPress, pos, Qt.LeftButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseButtonRelease, pos, Qt.LeftButton, Qt.NoButton)

    assert committed == [], "點長條不該 commit 門檻"
    assert hist.threshold() == pytest.approx(before)
    assert window.model.threshold == pytest.approx(before)
    assert window.results_visible() is True
    assert "Filtered to score" in window.status_text()

    window.gallery.clear_filter()
    window._score_filter = None


def test_real_drag_still_commits_the_threshold(scored, qapp):
    """按下 + 拖過去 + 放開 = 拖門檻（老行為不能壞）。"""
    window = scored
    hist = window.histogram
    hist.resize(520, 200)
    qapp.processEvents()
    before_visible = window.results_visible()

    bars = []
    hist.bar_clicked.connect(lambda a, b: bars.append((a, b)))
    committed = []
    hist.threshold_committed.connect(committed.append)

    rect = hist._plot_rect()
    y = rect.center().y()
    start = QPointF(rect.left() + 20, y)
    end = QPointF(rect.right() - 20, y)
    _mouse(hist, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseMove, QPointF(rect.center().x(), y),
           Qt.NoButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)

    assert bars == [], "拖曳不該被當成點長條"
    assert len(committed) == 1
    assert window.model.threshold == pytest.approx(committed[0])
    assert window.results_visible() == before_visible   # 拖門檻不改變視窗狀態


# --------------------------------------------------------------------------- #
# 5. 輸出動作
# --------------------------------------------------------------------------- #
def test_the_write_action_runs_the_whole_lot(qapp, synlot, tmp_path):
    """「跑整批然後照 Output 卡寫出去」這件事（M5 → F16 Stage 5c）。

    M5 的規則是「有結果才能輸出」，因為那時候那顆鈕開的是一個**吃結果**的
    對話框。現在它自己就是那一次跑 —— 所以前提跟 Run trial 一樣（有資料、
    流程跑得動），而**寫什麼、寫去哪**在畫布上的 Output 卡上。

    ⚠ 入口是 `Run trial ▾` 選單裡那一項（`act_run_all`）與 Results 視窗上
    同名的那顆。工具列上那顆重複的鈕 2026-08-24 拿掉了 —— 它跟選單那一項
    是同一支 `run_all()`。
    """
    win = studio_mod.StudioWindow()
    try:
        assert win.act_run_all.isEnabled() is False      # 沒資料、畫布是空的
        assert win.act_run_all.toolTip().strip()

        assert win.load_dataset_path(synlot["klarf"], sync=True) is True
        assert win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
        assert win.act_run_all.isEnabled() is True, "有資料、有流程就按得下去"

        # 加一張 Output 卡 → 按下去真的寫出東西
        out = tmp_path / "m5.csv"
        node = win.model.add_step("output_csv")
        win.model.set_param(node, "path", str(out))
        assert win.run_all(sync=True) is True
        assert out.exists()
        assert win.gallery.total_count() == N

        # 換一份資料集 → 舊結果作廢（那條規則沒變）
        assert win.load_dataset_path(synlot["klarf"], sync=True) is True
        assert win.gallery.total_count() == 0
    finally:
        win.close()


def test_close_stops_thumb_worker(qapp, synlot):
    win = studio_mod.StudioWindow()
    win.load_dataset_path(synlot["klarf"], sync=True)
    win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True)
    win.run_trial(N, workers=1, sync=True)
    win.request_thumbs(win.gallery.displayed_ids())        # 非同步：真的開執行緒
    win.close()
    assert win.thumb_worker.is_running() is False
    assert win.thumb_worker.thread_obj is None
    assert win.thumb_worker.pending_count() == 0
