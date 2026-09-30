# d4t — Re-run、Write outputs、Results 單擊帶主畫面、Output／判定樹的預覽跑到底
# （2026-09-09，使用者點名的四件事裡的三件）。
"""Qt 一律 lazy import（見 `tests/test_ui_studio_m5.py`）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from make_sample import generate  # noqa: E402

N = 6


def _load_qt() -> None:
    from PySide6.QtWidgets import QApplication  # noqa: F401

    from d4t.ui import studio as studio_mod  # noqa: F401
    from d4t.ui import theme as theme_mod  # noqa: F401
    globals().update(locals())


@pytest.fixture(scope="module")
def qapp():
    _load_qt()
    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
    theme_mod.apply_theme(app)
    yield app
    app.processEvents()


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    return generate(str(tmp_path_factory.mktemp("rerun")), n=N, seed=7)


@pytest.fixture
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    assert win.load_dataset_path(lot["klarf"], sync=True) is True
    yield win
    win.close()


def _wire(win, when="glv_max > 1", out_dir=None):
    """Load → Gray level → 判定樹（一步）→（選配）一張 Output 卡。"""
    load = win.model.add_step("load_patch")
    glv = win.model.add_step("glv_stats")
    win.model.set_param(glv, "source", "test")
    win.model.set_param(glv, "metrics", "glv_max")
    win.model.set_expr("glv_max")
    win.model.set_threshold(1.0)
    win.model.use_decide(True)
    win.model.ensure_tree()
    win.model.set_tree_when("", when)
    # 線都畫出來（F123 期 2：判定問的數字要接進 Decision、Output 寫它上游的）。
    dec = win.model.decision_node()
    win.model.add_edge(load, glv, src_out="test", dst_in="source")
    win.model.add_edge(glv, dec, src_out="numbers", dst_in="numbers")
    out = None
    if out_dir is not None:
        out = win.model.add_step("output_report")
        win.model.set_param(out, "folder", str(out_dir))
        win.model.set_param(out, "contents", "table")
        win.model.add_edge(dec, out, src_out="results", dst_in="results")
    return glv, out


def _bins(win):
    return [r.get("bin") for r in win.trial_results]


# --------------------------------------------------------------------------- #
# 1. Re-run：量測沒改 → 只重判；改了 → 整批重跑
# --------------------------------------------------------------------------- #
def test_rerun_redecides_without_touching_the_images(window):
    glv, _ = _wire(window, "glv_max > 1")
    assert window.run_trial(N, workers=1, sync=True) is True
    before = _bins(window)
    assert before and all(b == 1 for b in before), before   # 灰階 max 都 > 1
    traces_before = [r.get("traces") for r in window.trial_results]

    window.model.set_tree_when("", "glv_max > 100000")
    assert window.rerun(sync=True) is True
    assert all(b == 0 for b in _bins(window)), _bins(window)
    assert "no image was recomputed" in window.status_text(), window.status_text()
    assert [r.get("traces") for r in window.trial_results] == traces_before, \
        "只重判：每張卡的執行紀錄一個位元都不該變"
    assert window.results.btn_rerun.isEnabled()


def test_rerun_revives_defects_the_last_decision_failed_on(window):
    _wire(window, "glv_max > 1")
    window.model.set_let(0, name="a", expr="nosuch * 2") if window.model.decide.let \
        else window.model.add_let()
    window.model.set_let(0, name="a", expr="nosuch * 2")
    window.model.set_tree_when("", "a > 1")
    assert window.run_trial(N, workers=1, sync=True) is True
    assert all(not r.get("ok") for r in window.trial_results), "前提：判定炸了"
    window.model.set_let(0, expr="glv_max * 2")
    assert window.rerun(sync=True) is True
    assert all(r.get("ok") and r.get("bin") is not None
               for r in window.trial_results)


def test_rerun_runs_everything_again_when_a_measuring_card_changed(window):
    glv, _ = _wire(window, "glv_max > 1")
    assert window.run_trial(N, workers=1, sync=True) is True
    assert "glv_median" not in (window.trial_results[0].get("features") or {})
    window.model.set_param(glv, "metrics", "glv_max,glv_median")
    assert window.rerun(sync=True) is True
    assert "measured again" in window.status_text() or \
        "Run finished" in window.status_text(), window.status_text()
    assert "glv_median" in (window.trial_results[0].get("features") or {}), \
        "量測卡改了卻拿舊數字重判 —— 跑得完、有數字、而且是錯的"


def test_rerun_before_any_run_says_so(window):
    _wire(window)
    assert window.rerun(sync=True) is False
    assert "run a trial" in window.status_text().lower()


# --------------------------------------------------------------------------- #
# 2. Results 單擊一顆 → 主畫面帶過去（不搶焦點）
# --------------------------------------------------------------------------- #
def test_selecting_a_row_moves_the_main_window_to_that_defect(window):
    _wire(window)
    assert window.run_trial(N, workers=1, sync=True) is True
    ids = [r["defect_id"] for r in window.trial_results]
    assert window.defect_index == 0
    assert window.results.table.select_defect(ids[3]) is True
    assert window.defect_index == 3
    window.results.gallery.defect_selected.emit(ids[1])
    assert window.defect_index == 1


# --------------------------------------------------------------------------- #
# 3. Output 卡／判定樹選著的時候，預覽跑到底（有影像、有判定）
# --------------------------------------------------------------------------- #
def test_an_output_card_still_shows_the_route_image_and_the_verdict(window, tmp_path):
    _, out = _wire(window, "glv_max > 1", out_dir=tmp_path / "o")
    assert window.select_node(out) is True
    assert window.refresh_preview(sync=True) is True
    res = window._last_result
    assert res is not None and res.bin is not None, "Output 卡：判定要跑到"
    assert window._preview_images, "Output 卡：影像不該是空白"


def test_editing_the_tree_previews_the_whole_route(window):
    glv, _ = _wire(window, "glv_max > 1")
    assert window.select_node(glv) is True
    window._on_tree_step_clicked("")
    assert window._tree_focus is True
    assert window.refresh_preview(sync=True) is True
    assert window._last_result.bin is not None, "編樹時判定要跑，路徑才亮得起來"
    assert window.select_node(glv) is True
    assert window._tree_focus is False
