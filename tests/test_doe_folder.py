# F110 驗收：DOE 的輸入形狀 —— 一個資料夾一顆、裡面每個檔案一個 condition。
"""**這跟 `folder` 正好相反，所以它是第五種 kind 而不是那條路上的一個開關。**

DOE（使用者定調）：同一顆 defect、位置固定在 FOV 正中間、FOV 相同，用不同的
E-beam condition（Landing energy／電流）各拍一張，對齊之後在同一組 target／ref
box 上比 SNR。對標公司內的 imageY 流程。

為什麼不是在 `folder` 上加一個載入時的問題（像 `Open stack…` 那樣）：
同一個 ``kind`` 兩種形狀會讓**畫布說謊** —— `step.SINGLE_IMAGE_KINDS` 裡寫著
``folder``，而 DOE 的一顆有好幾張，於是畫布上那張預設的 `load_single` 對它
一定報錯。一種 source 一張載入卡（`CLAUDE.md` §5），而這一種走 `load_patch`
（它本來就吃 N 張 → N 條流）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 註冊卡片
from d4t.core.ingest import dataset as ds_mod  # noqa: E402
from d4t.core.ingest import imageio  # noqa: E402
from d4t.core.pipeline.step import (  # noqa: E402
    PATCH_KINDS, SINGLE_IMAGE_KINDS,
)

CONDITIONS = ("le300", "le500", "le800")


def _lot(root: Path, defects=("d1", "d2"), conditions=CONDITIONS) -> str:
    for i, name in enumerate(defects):
        (root / name).mkdir(parents=True, exist_ok=True)
        for j, cond in enumerate(conditions):
            imageio.save_gray(str(root / name / ("%s.png" % cond)),
                              np.full((16, 16), 30 + i * 10 + j * 20, np.uint8))
    return str(root)


# --------------------------------------------------------------------------- #
# 1. 分組
# --------------------------------------------------------------------------- #
def test_every_sub_folder_is_one_defect(tmp_path):
    ds = ds_mod.load_doe_folder(_lot(tmp_path))
    assert ds.kind == "doe_folder" and ds.klarf is None
    assert [i.defect_id for i in ds.items] == ["d1", "d2"]
    assert all(len(i.images) == 3 for i in ds.items)


def test_the_stream_order_is_the_file_name_order():
    """**這是一個契約，不是巧合。**

    這些 `ImageRef` 的 ``page`` 都是 ``None``，所以 `steps/load._in_defect_order`
    會退回 **dict 插入順序** —— 也就是這裡 `sorted()` 的順序。而 `load_patch`
    的 `channel_map`（1-based、每顆內編號）正是照它數的：使用者寫
    ``1:le300, 2:le500`` 的時候，他心裡數的就是檔名排序。
    """
    import tempfile

    root = Path(tempfile.mkdtemp())
    _lot(root, defects=("d1",), conditions=("b_second", "a_first", "c_third"))
    ds = ds_mod.load_doe_folder(str(root))
    assert list(ds.items[0].images) == ["test", "ref", "img3"]
    paths = [os.path.basename(r.path) for r in ds.items[0].images.values()]
    assert paths == ["a_first.png", "b_second.png", "c_third.png"]


def test_the_pixels_come_back_untouched(tmp_path):
    _lot(tmp_path, defects=("d1",), conditions=("only",))
    ds = ds_mod.load_doe_folder(str(tmp_path))
    assert np.array_equal(ds.items[0].load("test"), np.full((16, 16), 30,
                                                            np.uint8))


# --------------------------------------------------------------------------- #
# 2. 湊不成一顆的東西**不吞掉**
# --------------------------------------------------------------------------- #
def test_an_empty_sub_folder_is_reported_not_swallowed(tmp_path):
    """照 `load_tiff_stack` 對零頭的處置 —— 少一顆而沒有人講，是最難查的。"""
    _lot(tmp_path, defects=("d1",))
    (tmp_path / "nothing_here").mkdir()
    ds = ds_mod.load_doe_folder(str(tmp_path))
    assert [i.defect_id for i in ds.items] == ["d1"]
    assert any("nothing_here" in w for w in ds.warnings)


def test_loose_files_at_the_top_are_not_defects_here(tmp_path):
    """這條路上「檔案」不是一顆 defect，是放錯地方 —— 而那要看得出來。"""
    _lot(tmp_path, defects=("d1",))
    imageio.save_gray(str(tmp_path / "stray.png"),
                      np.zeros((8, 8), np.uint8))
    ds = ds_mod.load_doe_folder(str(tmp_path))
    assert [i.defect_id for i in ds.items] == ["d1"]


def test_a_folder_with_no_sub_folders_says_which_entry_to_use(tmp_path):
    """**按了撞牆的鈕比沒有那顆鈕更糟** —— 走錯入口要講得出正確的那一個。"""
    imageio.save_gray(str(tmp_path / "a.png"), np.zeros((8, 8), np.uint8))
    ds = ds_mod.load_doe_folder(str(tmp_path))
    assert ds.items == []
    assert any("Open folder" in w for w in ds.warnings), ds.warnings


def test_a_missing_directory_does_not_raise(tmp_path):
    ds = ds_mod.load_doe_folder(str(tmp_path / "nope"))
    assert ds.kind == "doe_folder" and ds.items == []
    assert ds.warnings


# --------------------------------------------------------------------------- #
# 3. 這一種 kind 在哪一群
# --------------------------------------------------------------------------- #
def test_doe_is_a_patch_kind():
    """DOE 的每一張都是「以 defect 為中心、FOV 固定」拍出來的 —— 那正是
    patch 形的定義（`_center` 在它身上有幾何意義），跟是不是機台裁的無關。"""
    assert "doe_folder" in PATCH_KINDS
    assert "doe_folder" not in SINGLE_IMAGE_KINDS


def test_the_two_groups_still_cover_every_supported_kind():
    """⚠ 加第五種 kind 的時候，**這一條就是那張安全網**：兩張表合起來要剛好
    蓋滿，漏掉的那一種會安靜地拿到另一群的判準。"""
    from d4t.ui import scope

    assert set(PATCH_KINDS) | set(SINGLE_IMAGE_KINDS) == set(
        scope.SUPPORTED_KINDS)
    assert not (set(PATCH_KINDS) & set(SINGLE_IMAGE_KINDS))


def test_the_starter_card_for_doe_is_the_one_that_takes_n_images():
    """一種 source 一張載入卡 —— DOE 一顆好幾張，所以起手卡是 `load_patch`。"""
    from d4t.ui.viewmodel import RecipeModel

    assert RecipeModel.starter_step_for("doe_folder") == "load_patch"
    assert RecipeModel.starter_step_for("folder") == "load_single"


def test_the_entry_is_on_the_one_table_that_grows_the_buttons():
    """加／改一個入口＝改 `INPUT_SOURCES`，不要動 UI（`CLAUDE.md` §5）。"""
    from d4t.ui import open_dialogs, scope

    row = [s for s in scope.INPUT_SOURCES if s.key == "doe_folder"]
    assert row and row[0].kinds == ("doe_folder",)
    assert row[0].has_klarf is False, "沒有 KLARF ⇒ 寫不回 KLARF"
    assert "doe_folder" in open_dialogs.OPENABLE
    icons = [s.icon for s in scope.INPUT_SOURCES]
    assert len(set(icons)) == len(icons), "每顆 Open 的輪廓要各不相同：%s" % icons


# --------------------------------------------------------------------------- #
# 4. CLI 走得通（那是 `folder` 那條路當初漏掉的東西）
# --------------------------------------------------------------------------- #
def test_the_cli_tells_the_two_folder_shapes_apart(tmp_path):
    """**由內容判斷，不是多一個旗標**：一個目錄裡裝的是影像檔還是資料夾，
    是看得出來的事實，而使用者在命令列上重打一次那個事實是沒有道理的。"""
    from d4t.__main__ import _open_input

    doe = tmp_path / "doe"
    _lot(doe)
    assert _open_input(str(doe)).kind == "doe_folder"

    flat = tmp_path / "flat"
    flat.mkdir()
    imageio.save_gray(str(flat / "a.png"), np.zeros((8, 8), np.uint8))
    assert _open_input(str(flat)).kind == "folder"


def test_the_cache_token_notices_a_condition_being_added(tmp_path):
    """快取要跟著「這一顆是由哪幾張圖組成的」走 —— 多一個 condition 是一批
    不一樣的資料，而拿舊快照續跑會是「跑得完、有數字、而且是錯的」。"""
    from d4t.core.pipeline.batch import _dataset_token_for

    _lot(tmp_path, defects=("d1",), conditions=("le300", "le500"))
    before = _dataset_token_for(ds_mod.load_doe_folder(str(tmp_path)))
    imageio.save_gray(str(tmp_path / "d1" / "le800.png"),
                      np.full((16, 16), 90, np.uint8))
    after = _dataset_token_for(ds_mod.load_doe_folder(str(tmp_path)))
    assert before != after
