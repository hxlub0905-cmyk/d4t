# F121 期 3：Studio 端 —— Input 卡看資料，而且下一步就在那張卡上。
"""**使用者回報的原始情境，從頭走一次。**

2026-09-24：開一份 EBI 的 recipe（Patch：``1:test, 2:ref``，帶 KLARF 座標），
再開一個沒有 KLARF 的 RSEM 影像資料夾，按跑 —— 每一顆都報錯。

F121 之後的樣子，這一份一條一條鎖：

1. 開資料的那一刻，**Input 卡上**就有那兩句話（名字表要 2 張、這份資料一顆 1 張；
   沒有 KLARF 卻要帶座標）—— Problems 列與畫布的警示點吃的是同一份；
2. 按跑 → **開跑之前擋下**，講一次，一顆都沒跑；
3. 名字表那一格有一顆「照這份資料填」—— 按一下名字表變成 ``1:test``、只剩一列
   （**線能留的就留**：資料有第 1 張，所以 ``test`` 那個名字與它的線都不動）；
   吃消失的 ``ref`` 的下游卡**在畫布上變紅**（使用者一眼看得出 die-to-die 在這種
   資料上缺的是參照影像），`test` 那一條照舊，而 Input 卡自己那一句消失；
4. **反向**：值跟資料對得上的時候那顆鈕不出現（空白畫布開資料補上的那一張、
   patch 資料上的 patch recipe）。
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

from d4t.ui import studio as studio_mod                 # noqa: E402
from d4t.ui import theme as theme_mod                   # noqa: E402

EBI = REPO / "recipes" / "ebi-die-to-die.json"


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
    from make_sample_rsem import generate

    return generate(str(tmp_path_factory.mktemp("rsem")), n=4, seed=11)


@pytest.fixture(scope="module")
def patch(tmp_path_factory):
    from make_sample import generate

    return generate(str(tmp_path_factory.mktemp("patch")), n=4, seed=11)


def _ebi_on_rsem_images(window, rsem):
    assert window.load_recipe_path(str(EBI), sync=True)
    assert window.load_folder_path(rsem["images_dir"], sync=True)
    assert window.dataset.kind == "folder"


def _rows(window):
    window._refresh_pipeline()
    return window.problems.rows()


# --------------------------------------------------------------------------- #
# 1. 開資料的那一刻就講，而且講在 Input 卡上
# --------------------------------------------------------------------------- #
def test_the_input_card_says_what_does_not_fit_as_soon_as_the_data_opens(
        window, rsem):
    _ebi_on_rsem_images(window, rsem)
    on_input = [r for r in _rows(window) if r["node_id"] == "load"]
    titles = " | ".join(r["title"] for r in on_input)
    assert "asks for more images than this data has" in titles, titles
    assert "needs a KLARF" in titles, titles


# --------------------------------------------------------------------------- #
# 2. 開跑之前擋下，講一次
# --------------------------------------------------------------------------- #
def test_running_stops_before_the_first_defect(window, rsem):
    _ebi_on_rsem_images(window, rsem)
    assert window.run_trial(4, workers=1, sync=True) is False
    assert not window.trial_results, "一顆都不該跑"
    said = window.status_text()
    assert "Cannot run" in said and "Name the images" in said, said


# --------------------------------------------------------------------------- #
# 3. 下一步就在那一格：照這份資料填
# --------------------------------------------------------------------------- #
def test_one_click_fills_the_names_in_from_the_data(window, rsem):
    _ebi_on_rsem_images(window, rsem)
    window.select_node("load")
    ed = window.param_form.editor("channel_map")
    btn = ed.suggestion_button()
    assert not btn.isHidden(), "值跟資料對不上 —— 那顆鈕要在"
    btn.click()

    assert window.model.nodes["load"].params["channel_map"] == "1:test"
    ed = window.param_form.editor("channel_map")
    assert ed.row_count() == 1, "一顆一張就是一列"
    assert ed.suggestion_button().isHidden()

    rows = _rows(window)
    assert not [r for r in rows if r["node_id"] == "load"
                and "more images" in r["title"]], "Input 卡那一句要消失"
    # 做不到的卡在畫布上變紅：`ref` 那一條沒了，吃它的那一張要講話……
    red = {r["node_id"] for r in rows if r["level"] == "error"}
    assert "norm_ref" in red, rows
    # ……而 `test` 那一條的名字與線都留著，那一張不該被牽連。
    assert "norm" not in red, rows


# --------------------------------------------------------------------------- #
# 4. 反向：對得上的時候不出現
# --------------------------------------------------------------------------- #
def test_the_card_added_for_the_data_needs_no_fixing(window, rsem):
    assert window.load_folder_path(rsem["images_dir"], sync=True)
    nid = window.model.node_order[0]
    assert window.model.nodes[nid].params["channel_map"] == "1:single"
    window.select_node(nid)
    ed = window.param_form.editor("channel_map")
    assert ed.suggestion_button().isHidden()
    assert ed.row_count() == 1, "一顆一張的資料下面不該多一列寫著 ref"
    assert not [r for r in _rows(window) if r["node_id"] == nid]


def test_a_patch_recipe_on_patch_data_needs_no_fixing(window, patch):
    assert window.load_recipe_path(str(EBI), sync=True)
    assert window.load_dataset_path(patch["klarf"], sync=True)
    window.select_node("load")
    assert window.param_form.editor("channel_map") \
        .suggestion_button().isHidden()
    assert not [r for r in _rows(window) if r["node_id"] == "load"
                and r["title"].startswith("“")]
