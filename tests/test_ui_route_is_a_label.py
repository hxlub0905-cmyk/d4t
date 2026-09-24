# F121 期 1：Studio 端 —— route 鍵只是標籤。
"""**使用者回報的三條路，一條一條走。**

2026-09-24：跑沒有 KLARF 的 RSEM 影像（一個影像資料夾，``folder``），每一顆都報
``unknown input-type route 'folder'; this recipe only defines: ['ebi_patch']``。
那一輪在 headless Studio 上重現出三條走得到的路：

1. **先有 pipeline 再開影像**（先加了卡／救回草稿）—— Studio 不動 pipeline，
   只在狀態列講一句（馬上被蓋掉），跑下去每一顆都錯；
2. **先開影像再開 recipe** —— 同上；
3. **先開 recipe 再開影像** —— Studio **默默把 route 改名**成 ``folder``，
   `Ctrl+S` 就改寫了原檔。

而開跑前的健檢拿的是 pipeline 自己的鍵去比，所以一條都沒擋下。

F121 期 1 之後 route 鍵只是標籤（`route_for`：只有一條就跑那一條），這一份鎖：
能跑的就跑、畫布上有卡的 recipe 一個字都不被改、健檢跟引擎講同一件事、
而**反向**：手寫的多型別 recipe 沒有這種資料的那一條時，開跑**之前**就擋下
（不是跑完每一顆都錯）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication              # noqa: E402

from d4t.core.pipeline import Recipe                    # noqa: E402
from d4t.ui import studio as studio_mod                 # noqa: E402
from d4t.ui import theme as theme_mod                   # noqa: E402

RECIPES = REPO / "recipes"
DUAL = REPO / "tests" / "fixtures" / "recipes" / "dual_route_basic.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


@pytest.fixture(scope="module")
def rsem(tmp_path_factory):
    """一份 RSEM lot：``klarf`` 是有 KLARF 的那一種，``images_dir`` 單獨拿出來
    就是使用者手上那種「一個資料夾的影像、沒有 KLARF」。"""
    from make_sample_rsem import generate

    return generate(str(tmp_path_factory.mktemp("rsem")), n=4, seed=11)


def _errors(win):
    return [r.get("error") for r in (win.trial_results or []) if not r.get("ok")]


# --------------------------------------------------------------------------- #
# 1. 先有 pipeline，再開影像
# --------------------------------------------------------------------------- #
def test_a_pipeline_built_before_the_data_runs_on_it(window, rsem):
    """開窗就先放卡（畫布的鍵是預設的 ``ebi_patch``），再開一個影像資料夾。"""
    window.model.add_step("load_single")
    assert window.model.kind == "ebi_patch" and window.model.dirty

    assert window.load_folder_path(rsem["images_dir"], sync=True)
    assert window.dataset.kind == "folder"
    # 使用者蓋的東西一個字都不動（鍵名也不改）……
    assert window.model.kind == "ebi_patch"
    # ……而它照樣跑得動。
    assert window.run_trial(4, workers=1, sync=True) is True
    assert window.trial_results and not _errors(window), _errors(window)


# --------------------------------------------------------------------------- #
# 2. 先開影像，再開 recipe
# --------------------------------------------------------------------------- #
def test_a_recipe_opened_on_other_data_edits_the_route_that_will_run(window,
                                                                     rsem):
    """一份 `folder` 的出貨 recipe 開在一份有 KLARF 的 RSEM lot 上（一顆一張，
    卡片這一層一模一樣）。以前狀態列會說 "preview and trial runs will fail"。"""
    assert window.load_dataset_path(rsem["klarf"], sync=True)
    assert window.dataset.kind == "rsem"
    path = RECIPES / "one-image-uniformity.json"
    assert list(Recipe.load(str(path)).routes) == ["folder"]

    assert window.load_recipe_path(str(path), sync=True)
    assert window.model.kind == "folder"          # 它唯一的那一條
    assert "will fail" not in window.status_text()
    assert window.run_trial(4, workers=1, sync=True) is True
    assert not _errors(window), _errors(window)


# --------------------------------------------------------------------------- #
# 3. 先開 recipe，再開影像
# --------------------------------------------------------------------------- #
def test_opening_data_does_not_rename_the_recipe_you_just_opened(window,
                                                                 rsem):
    """以前這一條會**默默把 route 改名**成資料的型別，存檔就改寫原檔。"""
    path = RECIPES / "ebi-die-to-die.json"
    assert window.load_recipe_path(str(path), sync=True)
    before = window.model.to_recipe().to_json_dict()
    assert window.model.dirty is False

    assert window.load_folder_path(rsem["images_dir"], sync=True)
    assert window.model.kind == "ebi_patch"
    assert window.model.dirty is False, "開一份資料不是改了 recipe"
    assert window.model.to_recipe().to_json_dict() == before


def test_a_blank_canvas_still_takes_the_data_kind_as_its_name(window, rsem):
    """空白畫布沒有東西可以被改壞：鍵名順手跟著資料（存出去的 JSON 讀起來對），
    起手卡照資料補。"""
    assert not window.model.node_order
    assert window.load_folder_path(rsem["images_dir"], sync=True)
    assert window.model.kind == "folder"
    steps = [window.model.nodes[n].step for n in window.model.node_order]
    assert steps == ["load_single"]


# --------------------------------------------------------------------------- #
# 健檢與引擎講同一件事
# --------------------------------------------------------------------------- #
def test_the_problems_list_asks_about_the_data_that_is_open(window, rsem):
    """Problems 列（畫布上那一份健檢）問的是**開著的資料**會跑哪一條。

    手寫的多型別 recipe（`ebi_patch` 與 `rsem` 各一條）開在一個影像資料夾上：
    畫布編的是 `ebi_patch` 那一條，拿它的鍵去健檢會說「沒問題」—— 以前就是
    這樣，然後每一顆都錯。拿資料的型別去問，才講得出「沒有一條是給它的」。"""
    assert window.load_folder_path(rsem["images_dir"], sync=True)
    assert window.load_recipe_path(str(DUAL), sync=True)
    assert window.model.kind == "ebi_patch"
    assert not [i for i in window.model.validate() if i.code == "unknown-route"]

    window._refresh_pipeline()
    titles = [r["title"] for r in window.problems.rows()]
    assert any("'folder'" in t for t in titles), titles
    assert window.problems.counts()["error"] >= 1


def test_a_recipe_with_no_pipeline_for_this_data_stops_before_running(window,
                                                                      rsem):
    """**反向**：手寫的多型別 recipe（`ebi_patch` 與 `rsem` 各一條）開在一個
    影像資料夾上 —— 那是真的沒有一條能跑。以前開跑前的健檢拿畫布的鍵去比，
    說「沒問題」，然後每一顆都錯；現在開跑之前就擋下，而且只講一次。"""
    assert window.load_folder_path(rsem["images_dir"], sync=True)
    assert window.load_recipe_path(str(DUAL), sync=True)
    assert sorted(window.model.route_keys()) == ["ebi_patch", "rsem"]

    assert window.run_trial(4, workers=1, sync=True) is False
    assert not window.trial_results
    said = window.status_text()
    assert "Cannot run" in said, said
