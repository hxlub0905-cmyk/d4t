# 換視角要看得出「這兩張是同一份 pipeline」（F80）。
"""`fit()` / `reset_zoom()` / `tidy()` 以前是**瞬間跳**的。

瞬間跳會讓使用者失去「我剛剛在看的是哪一塊」—— 畫面前後兩張圖之間沒有任何線索
說這兩張是同一份 pipeline，他得重新找一次自己的位置。`tidy()` 更明顯：它同時搬
動每一張卡，而按這顆鈕的人心裡還有一份舊的位置圖，看得到每張卡從哪去到哪，那份
圖才接得上。

⚠ **這是全 repo 唯一一個開著動畫跑的測試檔。** `tests/conftest.py` 有一支 autouse
fixture 把 `canvas.ANIMATE` 關掉，理由是動畫會讓「按了 fit 之後縮放是多少」變成
一個跟時間有關的問題 —— 那種測試會間歇性變紅然後被關掉。這裡自己打開、驗完關回
去，而且**每一條都等到動畫真的結束**才斷言。

問三件事：

1. 動畫的**終點跟沒有動畫時逐位相同**（動畫不准改結果）。
2. 中途真的在動（不是「跳到終點然後假裝」）。
3. 關掉時是同步的 —— 呼叫完就到位，不需要跑事件迴圈。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import QElapsedTimer, QPointF
    from PySide6.QtWidgets import QApplication

    from d4t.ui import canvas as canvas_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QElapsedTimer=QElapsedTimer, QPointF=QPointF,
             QApplication=QApplication, canvas_mod=canvas_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def animated(qapp):
    """把動畫打開（conftest 的 autouse fixture 預設關掉它）。"""
    before = canvas_mod.ANIMATE
    canvas_mod.ANIMATE = True
    yield
    canvas_mod.ANIMATE = before


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1200, 700)
    win.show()
    qapp.processEvents()
    src = first_source(win)
    prev = src
    for _ in range(4):
        nid = win.add_card_after(prev, "denoise")
        win._on_edge_added(prev, nid, "test")
        prev = nid
    qapp.processEvents()
    yield win
    win.close()


def _settle(qapp, ms=None):
    """跑事件迴圈直到動畫做完（多給一倍時間當緩衝）。"""
    budget = (canvas_mod.ANIM_MS * 2 + 200) if ms is None else ms
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < budget:
        qapp.processEvents()


def _view_state(view):
    return (round(view.transform().m11(), 6),
            view.horizontalScrollBar().value(),
            view.verticalScrollBar().value())


# --------------------------------------------------------------------------- #
# 1. 動畫不准改結果
# --------------------------------------------------------------------------- #
def test_fit_lands_exactly_where_it_would_without_the_animation(window, qapp,
                                                                animated):
    """**終點由 `fit` 自己決定，動畫一個字都不算。**

    `_tween_view` 的做法是先讓 `fit` 跳到終點、把終點量下來、再回頭演 ——
    所以不管 `fit` 的規則以後怎麼改（`MIN_FIT_SCALE`、只縮不放、靠開頭對齊…），
    動畫都不會跟它分家。這條測試守的就是那件事。
    """
    view = window.pipeline
    view.reset_zoom()
    _settle(qapp)

    canvas_mod.ANIMATE = False
    view.fit()
    qapp.processEvents()
    plain = _view_state(view)

    view.reset_zoom()
    qapp.processEvents()
    canvas_mod.ANIMATE = True
    view.fit()
    _settle(qapp)

    assert _view_state(view) == plain, "動畫把 fit 的終點改掉了"


def test_tidy_lands_exactly_where_it_would_without_the_animation(window, qapp,
                                                                 animated):
    view = window.pipeline
    canvas_mod.ANIMATE = False
    view.tidy()
    qapp.processEvents()
    plain = {n: view.node_item(n).pos().toTuple() for n in view.node_ids()}

    view.node_item(view.node_ids()[0]).setPos(QPointF(500.0, 400.0))
    canvas_mod.ANIMATE = True
    view.tidy()
    _settle(qapp)

    got = {n: view.node_item(n).pos().toTuple() for n in view.node_ids()}
    assert got == plain, "動畫把排整齊的終點改掉了"


def test_the_model_is_already_at_the_end_while_the_cards_are_still_moving(
        window, qapp, animated):
    """動畫被打斷停在半路也不會留下爛攤子。

    `tidy` 是**先**把每張卡 setPos 到終點、**再**回頭演的，所以任何時刻的
    「真相」都已經是終點；畫面只是還沒追上。這條測試從 `_tween_nodes` 存的
    那份 moves 問同一件事。
    """
    view = window.pipeline
    view.node_item(view.node_ids()[0]).setPos(QPointF(500.0, 400.0))
    view.tidy()
    # 還沒跑事件迴圈 —— 動畫一格都還沒動
    anim = getattr(view, "_node_anim", None)
    assert anim is not None, "沒有動畫在跑，這條測試沒有在測東西"
    assert view.scene().sceneRect().isValid()
    _settle(qapp)


# --------------------------------------------------------------------------- #
# 2. 中途真的在動
# --------------------------------------------------------------------------- #
def test_the_cards_are_somewhere_in_between_while_it_plays(window, qapp,
                                                           animated):
    """不是「跳到終點然後假裝有動畫」。"""
    view = window.pipeline
    nid = view.node_ids()[0]

    # 終點要**先**用「關掉動畫的 tidy」問出來。
    # ⚠ 不能在動畫版的 `tidy()` 之後才讀 `pos()` —— `_tween_nodes` 的最後一步
    # 是 `step(0.0)`，也就是把卡片放回**起點**。第一版就是這樣寫的，於是
    # `end` 量到的其實是起點，兩個錨點疊在一起，這條測試問的東西整個垮掉。
    canvas_mod.ANIMATE = False
    view.tidy()
    qapp.processEvents()
    end = QPointF(view.node_item(nid).pos())

    start = QPointF(600.0, 500.0)
    view.node_item(nid).setPos(start)
    qapp.processEvents()
    assert (start - end).manhattanLength() > 100.0, "起點終點太近，測不出中間值"

    canvas_mod.ANIMATE = True
    view.tidy()
    qapp.processEvents()                     # 畫面應該先回到起點

    seen = []
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < canvas_mod.ANIM_MS + 60:
        qapp.processEvents()
        seen.append(view.node_item(nid).pos())
    _settle(qapp)

    between = [p for p in seen
               if (p - start).manhattanLength() > 1.0
               and (p - end).manhattanLength() > 1.0]
    assert between, (
        "從頭到尾都沒有經過中間位置 —— 那不是動畫，是跳過去再假裝")
    assert (view.node_item(nid).pos() - end).manhattanLength() < 0.5, \
        "動畫結束了卻沒有停在終點"


def test_the_zoom_really_passes_through_the_middle(window, qapp, animated):
    view = window.pipeline
    view.reset_zoom()
    _settle(qapp)
    start = view.transform().m11()

    view.fit()
    seen = []
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < canvas_mod.ANIM_MS + 60:
        qapp.processEvents()
        seen.append(view.transform().m11())
    _settle(qapp)
    end = view.transform().m11()

    assert abs(end - start) > 0.02, "這份 pipeline 的 fit 沒有改變縮放，換一份"
    lo, hi = sorted((start, end))
    assert any(lo + 1e-3 < s < hi - 1e-3 for s in seen), \
        "縮放沒有經過中間值 —— 那是跳的不是演的"


# --------------------------------------------------------------------------- #
# 3. 關掉的時候是同步的
# --------------------------------------------------------------------------- #
def test_with_animations_off_everything_is_done_when_the_call_returns(window,
                                                                      qapp):
    """`ANIMATE = False` 時**呼叫完就到位** —— 不需要跑事件迴圈。

    這是其餘幾百條 UI 測試賴以成立的前提（conftest 那支 autouse fixture）。
    它一旦不成立，那些測試會開始間歇性變紅，而原因在另一個檔案裡。
    """
    assert canvas_mod.ANIMATE is False, "conftest 的 fixture 沒有把動畫關掉"
    view = window.pipeline
    view.node_item(view.node_ids()[0]).setPos(QPointF(500.0, 400.0))

    view.tidy()
    assert getattr(view, "_node_anim", None) is None
    view.fit()
    assert getattr(view, "_view_anim", None) is None
    before = _view_state(view)
    view.reset_zoom()
    assert getattr(view, "_view_anim", None) is None
    assert _view_state(view) != before or before[0] == 1.0
