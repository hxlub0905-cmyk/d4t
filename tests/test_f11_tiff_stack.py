# F11 Input-2 驗收 — authored 2026-08-17.
"""**一個多頁 TIFF、沒有 KLARF** 也要進得來。

使用者的多通道資料就是這個形式：「在大 TIFF 內，但這種大 tiff 不會伴隨 klarf」。
而在這之前它**進不來，而且是安靜地進不來** —— 丟進 `load_folder` 的話，一個 15
頁的 TIFF 會變成**一顆** defect（`imageio.load_gray` 走 `cv2.imdecode`，多頁
TIFF 只解得到第 0 頁）。跑得完、有數字、而且錯得離譜。

兩個刻意分開的責任（這一支同時鎖住）：

* **分組是資料層的事**（一顆幾張 = 機台怎麼收的）→ `load_tiff_stack(per_defect=)`
* **命名是 recipe 的事**（哪一張叫 bse）→ `load_patch` 的 `channel_map`（Input-1）

分不開的話，同一批資料的「一顆幾張」會因為換一份 recipe 而改變。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adept.core.steps                                        # noqa: F401,E402
from adept.core.ingest import dataset                           # noqa: E402
from adept.core.pipeline import Context                         # noqa: E402
from adept.core.pipeline.step import REGISTRY                   # noqa: E402


@pytest.fixture()
def stack(tmp_path):
    """15 頁的 TIFF；每一頁的灰階 = 頁號 ×10（哪一頁去了哪裡一眼看得出來）。"""
    path = tmp_path / "LOT_STACK.tif"
    with tifffile.TiffWriter(str(path)) as tw:
        for i in range(15):
            tw.write(np.full((16, 16), 10 * (i + 1), np.uint8),
                     photometric="minisblack")
    return path


# ---------------------------------------------------------------------------
# 分組
# ---------------------------------------------------------------------------
def test_five_pages_per_defect_gives_three_defects(stack):
    ds = dataset.load_tiff_stack(str(stack), per_defect=5)
    assert ds.kind == "tiff_stack"
    assert ds.klarf is None              # 沒有 KLARF —— 寫不回 KLARF
    assert len(ds.items) == 3
    assert [it.defect_id for it in ds.items] == [
        "LOT_STACK_1", "LOT_STACK_2", "LOT_STACK_3"]
    assert not ds.warnings


def test_each_defect_gets_its_own_consecutive_pages(stack):
    """第三顆拿的是第 11–15 頁 —— 不是每顆都從第 0 頁重來。"""
    ds = dataset.load_tiff_stack(str(stack), per_defect=5)
    third = ds.items[2]
    means = {ch: float(third.load(ch).mean()) for ch in third.images}
    assert means == {"test": 110.0, "ref": 120.0, "img3": 130.0,
                     "img4": 140.0, "img5": 150.0}


def test_one_page_per_defect_is_every_page_its_own_defect(stack):
    ds = dataset.load_tiff_stack(str(stack), per_defect=1)
    assert len(ds.items) == 15
    assert sorted(ds.items[0].images) == ["test"]
    assert ds.items[7].load("test").mean() == 80.0


def test_no_coordinates_because_there_is_no_klarf(stack):
    it = dataset.load_tiff_stack(str(stack), per_defect=5).items[0]
    assert it.die is None and it.xrel_nm is None and it.yrel_nm is None


# ---------------------------------------------------------------------------
# 對不齊的尾巴：**不吞掉**
# ---------------------------------------------------------------------------
def test_a_leftover_tail_is_reported_not_absorbed(stack):
    """15 頁 ÷ 4 → 3 顆 + 剩 3 頁。剩下的**不進任何一顆**，而且要講出來。

    安靜地塞進最後一顆的話，那三頁的數字會出現在錯的 defect 上。
    """
    ds = dataset.load_tiff_stack(str(stack), per_defect=4)
    assert len(ds.items) == 3
    assert ds.warnings and "not a multiple of 4" in ds.warnings[0]
    assert "last 3 page(s) are not loaded" in ds.warnings[0]
    # 最後一顆是第 9–12 頁，不是第 12–15 頁
    last = ds.items[-1]
    assert last.load("test").mean() == 90.0


def test_not_even_one_complete_defect_says_so(stack):
    ds = dataset.load_tiff_stack(str(stack), per_defect=20)
    assert ds.items == []
    assert "not even one complete defect" in ds.warnings[0]


@pytest.mark.parametrize("kw, says", [
    ({"per_defect": 0}, "at least 1"),
    ({"per_defect": -3}, "at least 1"),
])
def test_a_bad_group_size_says_something_actionable(stack, kw, says):
    ds = dataset.load_tiff_stack(str(stack), **kw)
    assert ds.items == [] and says in ds.warnings[0]


def test_a_missing_file_is_reported_not_raised(tmp_path):
    ds = dataset.load_tiff_stack(str(tmp_path / "nope.tif"), per_defect=1)
    assert ds.items == [] and "Not a file" in ds.warnings[0]


# ---------------------------------------------------------------------------
# 舊的那條路不再說謊
# ---------------------------------------------------------------------------
def test_the_folder_route_now_says_it_only_reads_the_first_page(stack):
    """`load_folder` 對多頁 TIFF **只讀第 0 頁** —— 以前那件事一句話都沒有。

    行為刻意不變（那條路的定義就是「一個檔案一顆」），改的是**它會講出來**，
    並指向這種資料真正的入口。
    """
    ds = dataset.load_folder(str(stack.parent))
    assert len(ds.items) == 1                     # 15 頁還是變成一顆
    assert ds.warnings and "only the first page is used" in ds.warnings[0]
    assert "image stack" in ds.warnings[0]        # 講得出去哪裡
    assert stack.name in ds.warnings[0]


# ---------------------------------------------------------------------------
# 跟 Input-1 接起來：分組（資料層）＋ 命名（recipe）
# ---------------------------------------------------------------------------
def test_the_recipe_names_the_pages_that_the_data_layer_grouped(stack):
    """**這一輪與上一輪合起來的驗收**：五張一顆 + BSE 在第 2 張。"""
    ds = dataset.load_tiff_stack(str(stack), per_defect=5)
    params = {"channel_map": "1:se1, 2:bse, 3:se2, 4:se3, 5:se4"}
    for k, item in enumerate(ds.items):
        ctx = Context()
        ctx.meta["_defect_item"] = item
        ctx.meta["_dataset_kind"] = ds.kind
        out = REGISTRY["load_patch"]().run(ctx, params)
        assert sorted(out.images) == ["bse", "se1", "se2", "se3", "se4"]
        # 每一顆的 bse 都是**自己的第 2 張**（第 k 組的第 2 頁）
        assert out.images["bse"].mean() == float((k * 5 + 2) * 10)


# ---------------------------------------------------------------------------
# 位元深度的防呆（F11 Input 的尾巴）
# ---------------------------------------------------------------------------
def test_a_16_bit_stack_says_so_at_load_time(tmp_path):
    """位元深度在 IFD 的 tag 裡 → **不解碼像素**就答得出來，所以載入時就講。"""
    path = tmp_path / "deep.tif"
    with tifffile.TiffWriter(str(path)) as tw:
        for _ in range(4):
            tw.write((np.linspace(0, 4095, 256).reshape(16, 16)).astype(np.uint16),
                     photometric="minisblack")
    assert dataset.tiff_index.bit_depths(str(path)) == [16]
    ds = dataset.load_tiff_stack(str(path), per_defect=2)
    assert len(ds.items) == 2            # 分組照做（那件事跟位元深度無關）
    assert any("16-bit" in w for w in ds.warnings), ds.warnings
    assert any("8-bit" in w for w in ds.warnings)


def test_16_bit_pixels_are_refused_not_silently_saturated(tmp_path):
    """以前這裡是 **93.8% 的像素飽和成 255**，而且一句話都沒有。

    自動降位也不安全：12-in-16 與滿量程 16-bit 在檔案裡長得一樣，除以 16 還是
    256 猜不出來。所以擋下來並講出看到了什麼 —— 跟 channel_map 對不上時同一個
    原則：不准安靜地硬套。
    """
    path = tmp_path / "deep.tif"
    with tifffile.TiffWriter(str(path)) as tw:
        tw.write((np.linspace(0, 4095, 256).reshape(16, 16)).astype(np.uint16),
                 photometric="minisblack")
    item = dataset.load_tiff_stack(str(path), per_defect=1).items[0]
    with pytest.raises(dataset.DataError) as e:
        item.load("test")
    msg = str(e.value)
    assert "uint16" in msg and "4095" in msg          # 講出看到了什麼
    assert "8-bit" in msg and "guess" in msg          # 講出為什麼不自動轉


def test_a_single_defect_failing_does_not_kill_the_batch(tmp_path):
    """鐵則 7：引擎把它包成這一顆的失敗，不是整批爆掉。"""
    path = tmp_path / "deep.tif"
    with tifffile.TiffWriter(str(path)) as tw:
        tw.write((np.linspace(0, 4095, 256).reshape(16, 16)).astype(np.uint16),
                 photometric="minisblack")
    from adept.core.pipeline import Recipe, RecipeNode, ScoreSpec, run_defect
    ds = dataset.load_tiff_stack(str(path), per_defect=1)
    rec = Recipe(
        recipe_id="deep", routes={"tiff_stack": ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", {})},
        score=ScoreSpec(expr="n_channels", threshold=1.0,
                        bins={"below": 0, "above": 1}))
    res = run_defect(rec, ds.items[0], "tiff_stack")
    assert res.ok is False                      # 這一顆失敗
    assert "8-bit" in (res.error or "")         # 而且訊息傳得出來


def test_an_image_file_route_keeps_its_dtype_so_the_guard_can_see_it(tmp_path):
    """`folder` / `rsem` 那條路以前**先被 MINMAX 拉伸**才交出來 —— 於是

    (a) 兩張圖之間不再可比（`test − ref` 的前提沒了）、
    (b) 防呆看不到原本的 dtype。改走 `imageio.load_raw` 之後兩件事都解了。
    """
    from adept.core.ingest import imageio
    deep = (np.linspace(0, 4095, 256).reshape(16, 16)).astype(np.uint16)
    tifffile.imwrite(str(tmp_path / "d1.tif"), deep)
    assert imageio.load_raw(str(tmp_path / "d1.tif")).dtype == np.uint16
    # load_gray 仍然給「看得到的東西」（模板對話框那種用途）
    assert imageio.load_gray(str(tmp_path / "d1.tif")).dtype == np.uint8

    item = dataset.load_folder(str(tmp_path)).items[0]
    with pytest.raises(dataset.DataError):
        item.load("single")
