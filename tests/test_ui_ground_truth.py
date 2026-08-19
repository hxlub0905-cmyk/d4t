# Phase 1：把準確率接進調參迴圈 — authored 2026-08-16.
"""調門檻的時候，**準確率要跟著動**。

以前 ground truth 只有 CLI 看得到（`python -m d4t run --ground-truth`），
可是調門檻這件事是在 Studio 裡一邊拖一邊看的 —— 使用者拖完滑桿得跳出去跑一次
CLI 才知道剛才那一下是變好還是變壞，於是實際上沒有人在看正確率。

這一支鎖三件事：
1. 載資料集時**自動**撿 KLARF 旁邊的 ``ground_truth.json``（那正是
   ``tools/make_sample.py`` 寫它的地方），而且要在狀態列講出撿到哪一個；
2. 換一份沒有答案卷的資料集時，舊的答案卷要**跟著消失**（否則會拿 A 的答案
   去對 B 的結果，而那個數字看起來完全正常）；
3. 換門檻只重算分 bin，不重跑影像 —— ``accuracy_at`` 吃的是既有的
   ``trial_results``。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication          # noqa: E402

from d4t.ui import studio as studio_mod           # noqa: E402
from d4t.ui import theme as theme_mod             # noqa: E402
from d4t.ui.viewmodel import accuracy_at          # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("gt")), n=6, seed=11)


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


def test_loading_a_lot_picks_up_the_ground_truth_next_to_the_klarf(window, lot):
    assert window.ground_truth is None, "還沒載資料就有答案卷"
    assert window.load_dataset_path(lot["klarf"], sync=True) is True
    assert window.ground_truth, "KLARF 旁邊就有 ground_truth.json 卻沒撿到"
    # 猜對了要讓人看得見猜的是什麼 —— 不然使用者無從發現它猜錯了。
    # 掛在直方圖上而不是狀態列：載完馬上接著算預覽，狀態列那句話活不過幾毫秒。
    assert "ground_truth.json" in window.histogram.toolTip()


def test_a_lot_without_an_answer_key_clears_the_previous_one(window, lot, tmp_path):
    """換一份沒有答案卷的資料集 → 舊的要消失，不是留著繼續算。"""
    window.load_dataset_path(lot["klarf"], sync=True)
    assert window.ground_truth

    bare = tmp_path / "bare"
    bare.mkdir()
    for name in os.listdir(os.path.dirname(str(lot["klarf"]))):
        if name == "ground_truth.json":
            continue
        shutil.copy(os.path.join(os.path.dirname(str(lot["klarf"])), name),
                    str(bare / name))
    window.load_dataset_path(str(bare / os.path.basename(str(lot["klarf"]))),
                             sync=True)
    assert window.ground_truth is None, "上一份資料集的答案卷還在"
    assert window.histogram.toolTip() == "", "tooltip 還在講上一份的答案卷"


def test_a_broken_answer_key_is_treated_as_no_answer_key(window, lot, tmp_path):
    """讀不動就當沒有 —— 一份壞掉的 JSON 不可以讓資料集載不進來。"""
    folder = tmp_path / "broken"
    folder.mkdir()
    src = os.path.dirname(str(lot["klarf"]))
    for name in os.listdir(src):
        shutil.copy(os.path.join(src, name), str(folder / name))
    (folder / "ground_truth.json").write_text("{ not json", encoding="utf-8")

    ok = window.load_dataset_path(
        str(folder / os.path.basename(str(lot["klarf"]))), sync=True)
    assert ok is True, "壞掉的答案卷把整份資料集擋掉了"
    assert window.ground_truth is None


def test_the_accuracy_line_is_empty_without_a_ground_truth(window):
    assert window._accuracy_text(0.5) == ""


def test_accuracy_follows_the_threshold_without_rerunning_the_images():
    """同一批結果、兩個門檻 → 兩個不同的正確率。

    ``accuracy_at`` 只重算分 bin（``rebin``），所以拖門檻的迴圈裡不會有一次
    影像重算 —— 那正是「準確率接得進調參迴圈」的前提。
    """
    results = [{"defect_id": "1", "ok": True, "score": 0.9, "bin": 1},
               {"defect_id": "2", "ok": True, "score": 0.1, "bin": 0}]
    gt = {"1": {"is_real": True}, "2": {"is_real": False}}
    bins = {"below": 0, "above": 1}

    good = accuracy_at(results, 0.5, bins, gt)
    bad = accuracy_at(results, 0.05, bins, gt)     # 門檻壓低 → 兩顆都判 real
    assert good and bad
    assert good["accuracy"] == 1.0
    assert bad["accuracy"] < good["accuracy"], "門檻變了正確率卻沒變"


def test_no_ground_truth_means_no_number_at_all():
    """沒有答案卷就回 ``None``，不是回一個 0% —— 0% 讀起來像「全錯」。"""
    assert accuracy_at([], 0.5, None, None) is None
