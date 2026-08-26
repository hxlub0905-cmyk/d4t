# F16 Stage 5c：Studio 的整批入口（Run all 真的會寫）。
"""在此之前 **「Run all defects」跟「Run trial」是同一支函式、同一條路**，
差別只有 `limit`。而使用者定調了「**試跑不寫，只有整批才寫**」——
那件事要成立，兩條路就得真的不一樣。

這一份鎖住的是那個差別，以及它的三個邊角：

1. **Run all 寫、Run trial 不寫**（而且旗標跟著那一次執行走，不是讀當下的 UI）；
2. **中途按停止不寫**（部分結果寫進 KLARF 是不可逆的錯），**而且要講出來**；
3. **`inplace` 才跳確認**（annotate / topn 寫的是新檔；每次都問的話那個確認
   很快就變成閉著眼睛按掉的東西），而且**停用的卡不跳**。

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
# 1. Run all 寫、Run trial 不寫
# --------------------------------------------------------------------------- #
def test_a_trial_run_writes_nothing(window, tmp_path):
    """試跑是**調參數的迴圈** —— 每拖一下門檻就覆寫一次檔案是不可逆的。"""
    out = tmp_path / "trial"
    _wire(window, out, contents="table")
    assert window.run_trial(N, workers=1, sync=True) is True
    assert not out.exists(), "試跑不該寫出任何東西"


def test_run_all_writes(window, tmp_path):
    out = tmp_path / "all"
    _wire(window, out, contents="table")
    assert window.run_all(sync=True) is True
    assert out.exists()
    lines = (out / "defects.csv").read_text(
        encoding="utf-8-sig").splitlines()
    assert len(lines) == N + 1          # 表頭 + 一顆一列
    assert "Wrote" in window.status_text() and str(out) in window.status_text()


def test_the_flag_follows_the_run_not_the_ui(window, tmp_path):
    """旗標**跟著那一次執行走**：Run all 之後馬上再按 Run trial，
    第二批不該因為第一批而寫出東西（反之亦然）。"""
    first, second = tmp_path / "a", tmp_path / "b"
    _wire(window, first, contents="table")
    assert window.run_all(sync=True) is True
    assert first.exists()

    # 換一個路徑，改按試跑 —— 不該寫
    out_node = [n for n in window.model.node_order
                if window.model.nodes[n].step == "output_report"][0]
    window.model.set_param(out_node, "folder", str(second))
    assert window.run_trial(N, workers=1, sync=True) is True
    assert not second.exists(), "試跑用到了上一次 Run all 留下來的旗標"


def test_a_recipe_with_no_output_card_says_so(window, tmp_path):
    """一張 Output 卡都沒有不是錯 —— 但**要講**，不然「按了沒事發生」。"""
    load = window.model.add_step("load_patch")
    glv = window.model.add_step("glv_stats")
    window.model.set_param(glv, "source", "test")
    window.model.set_expr("glv_max")
    window.model.set_threshold(1.0)
    assert window.run_all(sync=True) is True
    assert "no Output card" in window.status_text(), window.status_text()


# --------------------------------------------------------------------------- #
# 2. 中途按停止 → 不寫，而且講出來
# --------------------------------------------------------------------------- #
def test_a_stopped_run_writes_nothing_and_says_so(window, tmp_path,
                                                  monkeypatch):
    """被停掉的是**部分結果**。安靜地不寫跟安靜地寫一樣糟。"""
    out = tmp_path / "stopped.csv"
    _wire(window, out)
    # 讓 `_apply_trial_results` 以為這一批是被停掉的
    monkeypatch.setattr(window.trial_worker, "is_aborted", lambda: True)
    assert window.run_all(sync=True) is True
    assert not out.exists()
    assert "nothing was written" in window.status_text(), window.status_text()


# --------------------------------------------------------------------------- #
# 3. inplace 才跳確認
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
    assert seen == []


def test_inplace_asks_first(window, tmp_path, monkeypatch):
    seen = _count_confirms(window, monkeypatch)
    _wire(window, tmp_path / "b.001", step="output_klarf", mode="inplace")
    assert window.run_all(sync=True) is True
    assert len(seen) == 1
    assert "cannot be undone" in seen[0]
    # M5 的「寫回前先預覽」承接：對話框上要有「會改幾列」
    # （這一份 recipe 還沒跑過，所以那一句可能不在 —— 有的話要是真的數字）
    assert "In place" in seen[0]


def test_cancelling_the_confirmation_runs_nothing(window, tmp_path,
                                                  monkeypatch):
    out = tmp_path / "c.001"
    monkeypatch.setattr(
        studio_mod.QMessageBox, "warning",
        staticmethod(lambda *a, **k: studio_mod.QMessageBox.Cancel))
    _wire(window, out, step="output_klarf", mode="inplace")
    assert window.run_all(sync=True) is False
    assert not out.exists()


def test_a_disabled_inplace_card_does_not_ask(window, tmp_path, monkeypatch):
    """停用的那張卡**不會跑** —— 跳確認就是騙人。"""
    seen = _count_confirms(window, monkeypatch)
    _, _, out_node = _wire(window, tmp_path / "d.001",
                           step="output_klarf", mode="inplace")
    window.model.set_enabled(out_node, False)
    assert window.run_all(sync=True) is True
    assert seen == []


# --------------------------------------------------------------------------- #
# 4. 寫檔走背景執行緒（非同步那條路）
# --------------------------------------------------------------------------- #
def test_the_async_path_uses_a_background_thread(window, tmp_path, qapp):
    """出圖那張卡會一顆一顆重跑 pipeline —— 在 GUI 執行緒做會僵住。"""
    out = tmp_path / "async"
    _wire(window, out, contents="table")
    assert window.run_all() is True          # 非同步
    # 兩段背景工作：先跑批次（TrialWorker），再寫輸出（OutputWorker）。
    # 兩個都要轉到 event loop 才會回來 —— 那正是這一條在驗的事。
    assert _spin(qapp, lambda: out.exists(), 30.0), \
        "背景那條路沒有把檔案寫出來"
    assert not window.output_worker.is_running()


# --------------------------------------------------------------------------- #
# 5. 寫回前先預覽：那道關卡搬進了 output_klarf 的儀表
# --------------------------------------------------------------------------- #
def test_the_writeback_inspector_says_what_would_change(window, tmp_path):
    """M5 那條規則是硬性的：**寫回前一定先預覽變更**。

    Export 精靈的做法是把「寫出」鈕鎖住直到按過預覽。精靈拿掉之後那條規則不能
    跟著消失 —— 而它其實不需要一顆鈕：乾跑（`plan_writeback`）一個位元組都不
    寫，所以它可以是**這張卡的儀表**，而且比精靈**更早**出現。
    """
    from d4t.ui.inspectors import inspector_for

    assert inspector_for("output_klarf") is not None
    _, _, out_node = _wire(window, tmp_path / "e.001",
                           step="output_klarf", mode="inplace")
    assert window.run_trial(N, workers=1, sync=True) is True   # 先有一批結果
    window.select_node(out_node)
    text = window.inspector_summary.text()
    assert "inplace" in text and "edits the original file" in text
    assert "row(s) would change" in text, text


def test_the_inspector_does_not_call_annotate_dangerous(window, tmp_path):
    """`annotate` 寫的是新檔 —— 面板上那句話要跟 inplace **不一樣**。

    三種都講成「危險」的話，使用者很快就不讀它了。
    """
    _, _, out_node = _wire(window, tmp_path / "f.001",
                           step="output_klarf", mode="annotate")
    assert window.run_trial(N, workers=1, sync=True) is True
    window.select_node(out_node)
    text = window.inspector_summary.text()
    assert "writes a new file" in text and "edits the original" not in text
