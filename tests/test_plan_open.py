# F121 期 4：一顆 Open —— 「這條路徑是什麼資料」只有一個家。
"""**使用者挑一個檔案或一個資料夾，d4t 自己看出是哪一種**（`ingest.dataset.plan_open`）。

使用者（2026-09-24）：「我想把入口簡單化」。以前是兩顆鈕（`Open KLARF…` /
`Open images…`），使用者要先知道自己的資料屬於哪一種 —— 而那件事**看那條路徑
就知道**：一個檔案是不是 KLARF 讀檔頭就知道（KLARF 沒有可靠的副檔名：
``.001`` / ``.klarf`` / ``.txt``），是 patch 還是一顆一張由 KLARF 自己講。

這一份鎖那一份判斷的每一格，特別是**資料夾**那幾格 —— 使用者最常挑的是一整個
lot 資料夾，而那裡面常常同時躺著 KLARF 與它的影像。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from d4t.core.ingest import imageio  # noqa: E402
from d4t.core.ingest.dataset import (  # noqa: E402
    load_folder, looks_like_klarf, plan_open,
)


@pytest.fixture(scope="module")
def lots(tmp_path_factory):
    from make_sample import generate as patch_lot
    from make_sample_rsem import generate as rsem_lot

    root = tmp_path_factory.mktemp("lots")
    return {"patch": patch_lot(str(root / "patch"), n=2, seed=3),
            "rsem": rsem_lot(str(root / "rsem"), n=2, seed=3)}


def _png(path: Path) -> Path:
    imageio.save_gray(str(path), np.full((8, 8), 20, np.uint8))
    return path


# --------------------------------------------------------------------------- #
# 認 KLARF：看檔頭，不看副檔名
# --------------------------------------------------------------------------- #
def test_a_klarf_is_recognised_by_what_is_inside(lots, tmp_path):
    assert looks_like_klarf(lots["patch"]["klarf"])
    renamed = tmp_path / "lot.txt"                    # 副檔名換掉也認得
    renamed.write_bytes(Path(lots["patch"]["klarf"]).read_bytes())
    assert looks_like_klarf(renamed)
    notes = tmp_path / "notes.txt"
    notes.write_text("just some notes", encoding="utf-8")
    assert not looks_like_klarf(notes)
    assert not looks_like_klarf(_png(tmp_path / "a.png"))
    assert not looks_like_klarf(tmp_path / "missing.001")
    assert not looks_like_klarf(tmp_path)             # 資料夾不是


# --------------------------------------------------------------------------- #
# 檔案
# --------------------------------------------------------------------------- #
def test_a_file_is_a_klarf_an_image_or_raw(lots, tmp_path):
    assert plan_open(lots["patch"]["klarf"]) == ("klarf", lots["patch"]["klarf"])
    png = _png(tmp_path / "a.png")
    assert plan_open(png) == ("image", str(png))
    raw_dir = tmp_path / "raws"
    raw_dir.mkdir()
    raw = raw_dir / "a.raw"
    raw.write_bytes(np.zeros((8, 8), "<u2").tobytes())
    # 一個 `.raw` 檔 → 它的資料夾（版面整批共用）
    assert plan_open(raw) == ("raw", str(raw_dir))


# --------------------------------------------------------------------------- #
# 資料夾
# --------------------------------------------------------------------------- #
def test_a_lot_folder_opens_its_klarf_even_with_images_beside_it(lots):
    """EBI 的 lot 資料夾裡躺著它的 patch TIFF（`.tif` 算影像檔）；挑這個資料夾
    的人要的是那一批（有座標、寫得回），不是「那一個 TIFF 當成一顆」。"""
    folder = Path(lots["patch"]["klarf"]).parent
    assert sorted(p.suffix for p in folder.iterdir()
                  if p.suffix in (".tif", ".001")) == [".001", ".tif"]
    assert plan_open(folder) == ("klarf", lots["patch"]["klarf"])
    # RSEM：KLARF 在外面、影像在 images/ 底下
    assert plan_open(lots["rsem"]["out_dir"]).what == "klarf"


def test_a_folder_of_images_without_a_klarf_is_a_folder(lots):
    images = lots["rsem"]["images_dir"]
    assert plan_open(images) == ("folder", str(images))


def test_a_raw_folder_is_raw(tmp_path):
    (tmp_path / "a.raw").write_bytes(b"\0" * 128)
    assert plan_open(tmp_path) == ("raw", str(tmp_path))


def test_several_klarfs_and_no_images_says_to_pick_one(lots, tmp_path):
    """**反向**：兩份 KLARF 不替使用者挑 —— 當成資料夾，而 `load_folder` 講出
    「挑一份」（不是含糊的「沒有影像」）。"""
    for name in ("a.001", "b.001"):
        (tmp_path / name).write_bytes(
            Path(lots["patch"]["klarf"]).read_bytes())
    assert plan_open(tmp_path) == ("folder", str(tmp_path))
    said = " ".join(load_folder(tmp_path).warnings)
    assert "2 KLARF files" in said and "a.001" in said, said


def test_a_folder_with_only_sub_folders_says_where_the_images_are(tmp_path):
    (tmp_path / "day1").mkdir()
    _png(tmp_path / "day1" / "a.png")
    assert plan_open(tmp_path) == ("folder", str(tmp_path))
    said = " ".join(load_folder(tmp_path).warnings)
    assert "sub-folders (day1)" in said, said
