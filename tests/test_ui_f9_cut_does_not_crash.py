# F9 Phase 4a 的回歸：按「×」會讓整個行程掛掉（2026-08-16，試用回饋）。
"""使用者的原話：「按 X 還會閃退」。

**機制**：``_EdgeItem.mousePressEvent`` 以前是**同步**發 ``edge_removed``。
接收端（``studio._on_edge_removed``）改 model → model 通知 listener →
listener 呼叫 ``PipelineCanvas.set_nodes()`` → 它第一件事是 ``scene.clear()``
—— 把**正在處理這個滑鼠事件的那條線自己**刪掉。事件處理函式回去的時候
Qt 去碰一個已經釋放的 C++ 物件，於是 segfault。

畫面上就是「按下去整個程式不見了」，**沒有任何錯誤訊息**（exit 139，
跟 CLAUDE.md §7 的 ``drawPolygon`` 那一列同一類）。

**為什麼是現在才炸**：Phase 4a 之前剪一條推導出來的線會被擋掉、什麼都不做，
所以沒有重建、沒有 clear、沒有崩。剪線變成真的之後才踩到。

segfault 沒辦法用 assert 抓（行程直接死掉，測試框架也一起死），所以這裡鎖的是
**不變量**：那個訊號不可以在滑鼠事件還在堆疊上的時候發出去。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication

    from adept.ui import canvas as canvas_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, QPointF=QPointF, Qt=Qt,
             canvas_mod=canvas_mod, studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1100, 640)
    win.load_recipe_path(str(studio_mod.TEMPLATE_RECIPE))
    yield win
    win.close()


def _edge(win, src, dst):
    for e in win.pipeline._edges:
        if e.pair() == (src, dst):
            return e
    raise AssertionError("找不到 %s → %s 這條線" % (src, dst))


def test_the_cut_button_does_not_fire_while_the_item_is_still_on_the_stack(window, qapp):
    """按下去的當下**不可以**已經把訊號發出去 —— 那一刻刪掉這條線就是 segfault。"""
    edge = _edge(window, "align", "cross")
    seen = []
    window.pipeline.edge_removed.connect(lambda a, b: seen.append((a, b)))

    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent

    edge._hover = True                         # 滑鼠在線上（× 才畫得出來）
    pos = edge.cut_center()
    ev = QMouseEvent(QEvent.GraphicsSceneMousePress, pos, Qt.LeftButton,
                     Qt.LeftButton, Qt.NoModifier)
    ev.pos = lambda: pos                      # QGraphicsItem 事件用 item 座標
    edge.mousePressEvent(ev)

    assert seen == [], (
        "訊號在 mousePressEvent 還在堆疊上的時候就發出去了 —— "
        "接收端會 scene.clear()，把這條線自己刪掉，回去就 segfault")

    qapp.processEvents()                       # 下一輪事件迴圈才發
    assert seen == [("align", "cross")], seen


def test_cutting_really_removes_the_wire_afterwards(window, qapp):
    """延後發訊號不可以把功能延後掉 —— 跑完一輪事件迴圈，線要真的不見。"""
    from adept.core.pipeline.graph import KIND_STREAM

    def backbone():
        return [(a, b) for a, _sp, b, _dp, k in window._compiled_wiring()[0]
                if k != KIND_STREAM]

    assert ("align", "cross") in backbone()
    edge = _edge(window, "align", "cross")
    edge._hover = True
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    pos = edge.cut_center()
    ev = QMouseEvent(QEvent.GraphicsSceneMousePress, pos, Qt.LeftButton,
                     Qt.LeftButton, Qt.NoModifier)
    ev.pos = lambda: pos
    edge.mousePressEvent(ev)
    qapp.processEvents()

    assert ("align", "cross") not in backbone()
    assert "Disconnected" in window.status_text()


# --------------------------------------------------------------------------- #
# 「黑線跟綠線差別是什麼？」—— 差異要有名字才有意義
# --------------------------------------------------------------------------- #
def test_the_canvas_says_what_the_two_kinds_of_wire_mean(window):
    """色相、粗細、有沒有箭頭 —— 那些差異說得出「這兩條不一樣」，
    說不出**哪一條才是資料走的路**。"""
    labels = window.pipeline.legend_labels()
    assert len(labels) == 2, labels
    assert any("flows" in t for t in labels)
    assert any("stream" in t for t in labels)


def test_a_stream_wire_is_dashed_and_the_backbone_is_not(window):
    """虛線是流程圖裡「這不是主要路徑」的通用寫法。"""
    window.select_node("cross")
    kinds = {}
    for e in window.pipeline._edges:
        kinds.setdefault(e.kind, []).append(e)
    assert "packet" in kinds and "stream" in kinds, sorted(kinds)
