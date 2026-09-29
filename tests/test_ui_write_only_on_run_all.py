# 「試跑不寫，只有整批才寫」（常駐）：Studio 的整批入口。
# 起於 F16 Stage 5c；2026-08-27 從 `test_ui_f16_run_all.py` 改名（F39 A 組）——
# 那條規則是使用者定調的，而這一支是它唯一的守門人。
"""**跑不寫，寫是另一個動作**（2026-09-09 改的契約）。

在此之前是「試跑不寫，只有整批才寫」（F16 Stage 5c）—— 整批跑完會順手讓
Output 卡寫出去。使用者 2026-09-09：「跑完後可以檢查結果再按一個鍵 output」
—— 寫 KLARF 是不可逆的，而使用者連看一眼的機會都沒有。所以：

1. **Run trial 與 Run all 都不寫**；寫是 `write_outputs()`（Results 視窗上
   那顆「Write outputs」），而且它寫的是**現在這批結果**；
2. **被停掉的那一批不能寫**（部分結果寫進 KLARF 是不可逆的錯），**而且要講**；
3. **`inplace` 才跳確認**，而且是在**寫的時候**問（annotate / topn 寫的是
   新檔；每次都問的話那個確認很快就變成閉著眼睛按掉的東西），**停用的卡不跳**。

Qt import 一律 lazy（見 `tests/test_ui_studio_m5.py` 的說明）。
"""
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
    return generate(str(tmp_path_factory.mktemp("runall")), n=N, seed=7)


@pytest.fixture
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    assert win.load_dataset_path(lot["klarf"], sync=True) is True
    yield win
    win.close()



def _spin(qapp, done, timeout_s=15.0):
    """轉 event loop 直到 ``done()`` 為真（或逾時）。

    非同步那條路要**真的**把訊號投遞回 GUI 執行緒才算數，所以不能用 sleep ——
    同 `tests/test_ui_f15_pair_source.py` 的做法。
    """
    import time

    t0 = time.time()
    while not done() and time.time() - t0 < timeout_s:
        qapp.processEvents()
    return done()


def _wire(win, out_path, step="output_report", **params):
    """最小的 pipeline：Load → Gray level → 一張 Output 卡。

    F38 之後報表那張卡吃的是**資料夾**，只有 KLARF 還是一格檔案路徑。
    """
    load = win.model.add_step("load_patch")
    glv = win.model.add_step("glv_stats")
    win.model.set_param(glv, "source", "test")
    win.model.set_param(glv, "metrics", "glv_max")
    out = win.model.add_step(step)
    key = "path" if step == "output_klarf" else "folder"
    win.model.set_param(out, key, str(out_path))
    for name, value in params.items():
        win.model.set_param(out, name, value)
    win.model.set_expr("glv_max")
    win.model.set_threshold(1.0)
    return load, glv, out


# --------------------------------------------------------------------------- #
# 1. 跑不寫，寫是另一顆鈕
# --------------------------------------------------------------------------- #
def test_neither_kind_of_run_writes(window, tmp_path):
    """跑是「我在看數字」，寫是「數字對了」—— 兩個動作。"""
    out = tmp_path / "trial"
    _wire(window, out, contents="table")
    assert window.run_trial(N, workers=1, sync=True) is True
    assert not out.exists(), "試跑不該寫出任何東西"
    assert window.run_all(sync=True) is True
    assert not out.exists(), "整批也不寫了（2026-09-09）—— 寫是另一顆鈕"
    assert "Write outputs" in window.status_text(), window.status_text()


def test_write_outputs_writes_the_current_results(window, tmp_path):
    out = tmp_path / "all"
    _wire(window, out, contents="table")
    assert window.run_all(sync=True) is True
    assert window.write_outputs(sync=True) is True
    assert out.exists()
    lines = (out / "defects.csv").read_text(
        encoding="utf-8-sig").splitlines()
    assert len(lines) == N + 1          # 表頭 + 一顆一列
    assert "Wrote" in window.status_text() and str(out) in window.status_text()


def test_nothing_to_write_before_a_run_says_so(window, tmp_path):
    _wire(window, tmp_path / "none", contents="table")
    assert window.write_outputs(sync=True) is False
    assert "run a trial" in window.status_text().lower(), window.status_text()


def test_a_recipe_with_no_output_card_says_so(window, tmp_path):
    """一張 Output 卡都沒有不是錯 —— 但**要講**，不然「按了沒事發生」。"""
    load = window.model.add_step("load_patch")
    glv = window.model.add_step("glv_stats")
    window.model.set_param(glv, "source", "test")
    window.model.set_expr("glv_max")
    window.model.set_threshold(1.0)
    assert window.run_all(sync=True) is True
    assert window.results.btn_write.isEnabled() is False, "沒有 Output 卡：那顆鈕灰掉"
    assert "Output card" in window.results.btn_write.toolTip()
    assert window.write_outputs(sync=True) is True
    assert "no Output card" in window.status_text(), window.status_text()


# --------------------------------------------------------------------------- #
# 2. 中途按停止 → 不寫，而且講出來
# --------------------------------------------------------------------------- #
def test_a_stopped_run_cannot_be_written_and_says_so(window, tmp_path,
                                                     monkeypatch):
    """被停掉的是**部分結果**。安靜地不寫跟安靜地寫一樣糟。"""
    out = tmp_path / "stopped"
    _wire(window, out, contents="table")
    # 讓 `_apply_trial_results` 以為這一批是被停掉的
    monkeypatch.setattr(window.trial_worker, "is_aborted", lambda: True)
    assert window.run_all(sync=True) is True
    assert window.write_outputs(sync=True) is False
    assert not out.exists()
    assert "partial" in window.status_text(), window.status_text()


# --------------------------------------------------------------------------- #
# 3. inplace 才跳確認 —— 在寫的時候
# --------------------------------------------------------------------------- #
def _count_confirms(window, monkeypatch):
    """把確認對話框換成計數器（測試不開真的對話框）。"""
    seen = []

    def fake(*args, **kwargs):
        seen.append(args[2] if len(args) > 2 else "")
        return studio_mod.QMessageBox.Yes

    monkeypatch.setattr(studio_mod.QMessageBox, "warning", staticmethod(fake))
    return seen


def test_annotate_does_not_ask(window, tmp_path, monkeypatch):
    """`annotate` 寫的是**新檔**，原檔不動 —— 每次都問的話，那個確認很快就會
    變成閉著眼睛按掉的東西，而它要擋的正是 inplace 那一種。"""
    seen = _count_confirms(window, monkeypatch)
    _wire(window, tmp_path / "a.001", step="output_klarf", mode="annotate")
    assert window.run_all(sync=True) is True
    assert window.write_outputs(sync=True) is True
    assert seen == []


def test_inplace_asks_first_and_only_when_writing(window, tmp_path, monkeypatch):
    seen = _count_confirms(window, monkeypatch)
    _wire(window, tmp_path / "b.001", step="output_klarf", mode="inplace")
    assert window.run_all(sync=True) is True
    assert seen == [], "跑的時候不問 —— 跑不寫"
    assert window.write_outputs(sync=True) is True
    assert len(seen) == 1
    assert "cannot be undone" in seen[0]
    # M5 的「寫回前先預覽」承接：對話框上要有「會改幾列」
    assert "In place" in seen[0]


def test_cancelling_the_confirmation_writes_nothing(window, tmp_path,
                                                    monkeypatch):
    out = tmp_path / "c.001"
    monkeypatch.setattr(
        studio_mod.QMessageBox, "warning",
        staticmethod(lambda *a, **k: studio_mod.QMessageBox.Cancel))
    _wire(window, out, step="output_klarf", mode="inplace")
    assert window.run_all(sync=True) is True
    assert window.write_outputs(sync=True) is False
    assert not out.exists()


def test_a_disabled_inplace_card_does_not_ask(window, tmp_path, monkeypatch):
    """停用的那張卡**不會跑** —— 跳確認就是騙人。"""
    seen = _count_confirms(window, monkeypatch)
    _, _, out_node = _wire(window, tmp_path / "d.001",
                           step="output_klarf", mode="inplace")
    window.model.set_enabled(out_node, False)
    assert window.run_all(sync=True) is True
    assert window.write_outputs(sync=True) is True
    assert seen == []


# --------------------------------------------------------------------------- #
# 4. 寫檔走背景執行緒（非同步那條路）
# --------------------------------------------------------------------------- #
def test_the_async_path_uses_a_background_thread(window, tmp_path, qapp):
    """出圖那張卡會一顆一顆重跑 pipeline —— 在 GUI 執行緒做會僵住。"""
    out = tmp_path / "async"
    _wire(window, out, contents="table")
    assert window.run_all(sync=True) is True
    assert window.write_outputs() is True          # 非同步
    assert _spin(qapp, lambda: out.exists(), 30.0), \
        "背景那條路沒有把檔案寫出來"
    assert not window.output_worker.is_running()


# --------------------------------------------------------------------------- #
# F122：寫的是「畫面上這份 recipe 的結果」，而且試跑的子集要講
# --------------------------------------------------------------------------- #
def test_a_changed_decision_must_be_rerun_before_writing(window, tmp_path):
    """改了判定沒按 Re-run 就寫：以前 CSV / KLARF 是**上一份**判定的 bin，
    畫面上是新的那一份。"""
    out = tmp_path / "stale"
    _wire(window, out, contents="table")
    assert window.run_all(sync=True) is True
    window.model.set_threshold(1e9)                 # 判定改了
    assert window.write_outputs(sync=True) is False
    assert not out.exists()
    assert "Re-run" in window.status_text(), window.status_text()
    assert window.run_ctl.rerun(sync=True) is True
    assert window.write_outputs(sync=True) is True
    assert out.exists()


def test_a_changed_measuring_card_must_be_run_again(window, tmp_path):
    out = tmp_path / "stale2"
    _, glv, _ = _wire(window, out, contents="table")
    assert window.run_all(sync=True) is True
    window.model.set_param(glv, "metrics", "glv_max,glv_median")
    assert window.write_outputs(sync=True) is False
    assert not out.exists()
    assert "Run again" in window.status_text(), window.status_text()


def test_changing_only_the_output_card_does_not_block_writing(window, tmp_path):
    """**反向**：Output 卡的資料夾換了不影響任何數字 —— 照樣寫。"""
    _, _, out_id = _wire(window, tmp_path / "a", contents="table")
    assert window.run_all(sync=True) is True
    window.model.set_param(out_id, "folder", str(tmp_path / "b"))
    assert window.write_outputs(sync=True) is True
    assert (tmp_path / "b" / "defects.csv").exists()


def test_writing_a_trial_says_it_is_not_the_whole_lot(window, tmp_path):
    out = tmp_path / "trial_write"
    _wire(window, out, contents="table")
    assert window.run_trial(2, workers=1, sync=True) is True
    assert window.write_outputs(sync=True) is True
    assert "2 of the %d defects" % N in window.status_text(), \
        window.status_text()
