# F25：導引式問題的純邏輯 ＋ 閃退的結構性防線。
"""兩件事在這裡鎖住：

**一、問題不必用打的**（使用者 2026-08-24：「我目前不太知道怎麼用，如果我都
不會用其他人更不會」）。一個問題大部分時候就是「哪個數字·比什麼·多少」，
所以要有一支**認得回來**的解析（`parse_simple_condition`）與一支組回去的
（`format_condition`），而且它們要 round-trip。認不得的（複合條件）誠實地
回 None —— 猜錯的那次會安靜地改掉使用者的判定。

**二、拆版面不准銷毀 widget**（`clear_layout_parked`）。面板是「改一格就整段
重建」的，而改那一格的訊號還在被拆掉的那個 widget 的堆疊上 —— 直接
`setParent(None)` 就是 use-after-free（回報：「輸入 bin 有機會閃退」）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme as theme_mod
    from d4t.ui import tree_scene as ts
    from d4t.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, theme_mod=theme_mod, ts=ts,
             widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


# --------------------------------------------------------------------------- #
# 解析與組字
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text, want", [
    ("contrast > 120", ("contrast", ">", 120.0)),
    ("  cd_deq   <=  4.5 ", ("cd_deq", "<=", 4.5)),
    ("glv_mad>=-2", ("glv_mad", ">=", -2.0)),
    ("n == 0", ("n", "==", 0.0)),
    ("x != 1e3", ("x", "!=", 1000.0)),
    ("a < .5", ("a", "<", 0.5)),
])
def test_a_simple_comparison_parses(qapp, text, want):
    assert ts.parse_simple_condition(text) == want


@pytest.mark.parametrize("text", [
    "", "   ", "(a > 5) * (b < 2)", "a > b", "a + 1 > 5", "a >", "> 5",
    "a >> 5", "sqrt(a) > 5",
])
def test_anything_else_is_honestly_unparseable(qapp, text):
    assert ts.parse_simple_condition(text) is None


def test_format_and_parse_round_trip(qapp):
    for name, op, val in (("contrast", ">", 120.0), ("a", "<=", -3.25)):
        text = ts.format_condition(name, op, val)
        assert ts.parse_simple_condition(text) == (name, op, val)


def test_whole_numbers_are_written_the_way_a_person_types_them(qapp):
    assert ts.format_condition("contrast", ">", 120.0) == "contrast > 120"


# --------------------------------------------------------------------------- #
# 「幾顆說 yes」與建議
# --------------------------------------------------------------------------- #
def _rows(values, key="a"):
    return [{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
             "features": {key: float(v)}}
            for i, v in enumerate(values)]


def test_count_yes_ignores_defects_that_do_not_have_the_number(qapp):
    rows = _rows([1.0, 5.0, 9.0])
    rows.append({"defect_id": "x", "ok": True, "bin": 0, "score": 0.0,
                 "features": {}})          # 這一顆沒量到 a
    assert ts.count_yes(rows, "a", ">", 4.0) == (2, 3)


def test_count_yes_covers_every_comparison(qapp):
    rows = _rows([1.0, 5.0, 9.0])
    assert ts.count_yes(rows, "a", "<", 5.0) == (1, 3)
    assert ts.count_yes(rows, "a", ">=", 5.0) == (2, 3)
    assert ts.count_yes(rows, "a", "<=", 5.0) == (2, 3)
    assert ts.count_yes(rows, "a", "==", 5.0) == (1, 3)
    assert ts.count_yes(rows, "a", "!=", 5.0) == (2, 3)


def test_suggest_picks_the_number_that_actually_separates(qapp):
    rows = []
    for i, v in enumerate((1.0, 8.0, 40.0, 600.0)):
        rows.append({"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
                     "features": {"spread": v, "flat": 3.0}})
    got = ts.suggest_condition(rows)
    assert got is not None
    assert got[0] == "spread" and got[1] == ">"


def test_suggest_prefers_the_users_own_working_numbers(qapp):
    rows = []
    for i, v in enumerate((1.0, 8.0, 40.0, 600.0)):
        rows.append({"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
                     "features": {"raw_thing": v, "contrast": v * 2}})
    assert ts.suggest_condition(rows, prefer=["contrast"])[0] == "contrast"


def test_suggest_never_offers_score_or_a_flag(qapp):
    rows = []
    for i, v in enumerate((1.0, 8.0, 40.0, 600.0)):
        rows.append({"defect_id": str(i), "ok": True, "bin": 0,
                     "score": v,
                     "features": {"score": v, "a_missing": float(i % 2),
                                  "a_raw": v}})
    assert ts.suggest_condition(rows) is None


def test_suggest_says_nothing_when_there_is_no_run(qapp):
    assert ts.suggest_condition([]) is None


def test_rows_reaching_follows_the_tree(qapp):
    from d4t.core.pipeline.recipe import TreeLeaf, TreeStep

    tree = TreeStep(when="a > 5",
                    yes=TreeLeaf(bin=1), no=TreeLeaf(bin=0))
    rows = _rows([1.0, 9.0, 20.0])
    assert len(ts.rows_reaching(tree, rows, "")) == 3
    assert len(ts.rows_reaching(tree, rows, "y")) == 2
    assert len(ts.rows_reaching(tree, rows, "n")) == 1


# --------------------------------------------------------------------------- #
# 閃退：拆版面不准銷毀正在發訊號的那一個
# --------------------------------------------------------------------------- #
def test_clearing_a_layout_keeps_the_widgets_alive(qapp):
    """`clear_layout_parked` 拆下來的 widget **要還活著**。

    這一條是「輸入 bin 有機會閃退」的迴歸測試：那個 widget 正在發訊號，
    而它的 C++ 物件被當場解構 —— 這裡驗的是「拆完之後還碰得到它」，
    因為碰得到就代表沒有被釋放。
    """
    from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

    host = QWidget()
    lay = QVBoxLayout(host)
    kids = [QPushButton("b%d" % i) for i in range(3)]
    for k in kids:
        lay.addWidget(k)
    graveyard: list = []
    widgets_mod.clear_layout_parked(lay, graveyard)

    assert lay.count() == 0
    assert len(graveyard) == 3
    for k in kids:
        assert k.text().startswith("b")    # 還活著（碰得到 C++ 物件）
        assert k.parent() is None and not k.isVisible()


def test_a_widget_can_clear_the_layout_it_lives_in_from_its_own_signal(qapp):
    """面板的形狀：按鈕在自己的 `clicked` 裡把整個版面拆掉 —— 不能爆。"""
    from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

    host = QWidget()
    lay = QVBoxLayout(host)
    graveyard: list = []
    hits = []

    def on_click() -> None:
        widgets_mod.clear_layout_parked(lay, graveyard)
        hits.append(1)

    btn = QPushButton("go")
    btn.clicked.connect(on_click)
    lay.addWidget(btn)
    btn.click()
    assert hits == [1]
    assert btn.text() == "go"              # 訊號返回之後它還在
