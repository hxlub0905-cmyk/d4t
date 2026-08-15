"""tools/make_sample_rsem.py 與 rSEM ingest 路線的測試（M4-2）。

Review SEM 是 ingest 的另一條分支：**每顆 defect 一個獨立影像檔**，
KLARF 列尾用 `Images 1 { "檔名" … }` 指到那個檔。這裡驗證：
  1. KLARF 解得開、`load_dataset` 判成 rsem、每顆只有 single channel；
  2. 像素形狀／dtype、ground truth key 與 defect id 對得起來；
  3. 同 seed → 位元組完全相同（KLARF 與影像）；
  4. `load_patch` 卡會把 single 鏡射成 test（下游卡片才吃得到）；
  5. Golden Cell 路線（cell_period → golden_cell）在這份資料上跑得通
     —— 這是 M4「同一份 recipe 吃 EBI patch 與 RSEM」的驗收前提；
  6. `--real-frac 0` 的 lot 真的沒有種缺陷。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

import adept.core.steps  # noqa: F401 — 註冊卡片的 side-effect
from adept.core.ingest import dataset, klarf_core
from adept.core.pipeline.context import Context
from adept.core.pipeline.step import REGISTRY

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import make_sample_rsem  # noqa: E402


N = 8
SEED = 11
SIZE = 256
PITCH = 24

# 「有沒有種缺陷」的判準：nuisance 的 |single - golden_ref| 峰值 ~25（雜訊 sigma=5），
# 種了缺陷的 >= 64。取 45 當門檻，兩邊都有很大的餘裕。
RESIDUAL_THRESHOLD = 45.0


def run_step(key, ctx, **params):
    cls = REGISTRY[key]
    return cls().run(ctx, cls.validate_params(params))


def _read(path):
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    out = tmp_path_factory.mktemp("rsemlot")
    return make_sample_rsem.generate(str(out / "lot"), n=N, seed=SEED)


@pytest.fixture(scope="module")
def ds(lot):
    return dataset.load_dataset(lot["klarf"])


@pytest.fixture(scope="module")
def truth(lot):
    with open(lot["ground_truth"], "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------ 1. KLARF → rsem dataset

def test_klarf_parses_with_per_defect_filenames(lot):
    doc = klarf_core.load(lot["klarf"])
    assert doc.version == "1.8"
    assert len(doc.defects) == N
    # 沒有 patch TIFF：TiffFileName / TiffSpec 都不該出現，否則會被判成 ebi_patch
    assert doc.tiff_file_name is None
    assert doc.tiff_path() is None
    # 影像欄佈局：1.8 結構化 Images 區塊
    start, nfields, how = doc.image_layout()
    assert how == "images18"
    for k, row in enumerate(doc.defects):
        assert doc.defect_image_count(row) == 1
        assert doc.defect_image_filename(row) == "images/DEF_%04d.png" % (k + 1)


def test_load_dataset_is_rsem_single_channel(lot, ds):
    assert ds.kind == "rsem"
    assert len(ds.items) == N
    for i, it in enumerate(ds.items):
        assert set(it.images) == {"single"}          # 沒有 test / ref
        assert "test" not in it.images and "ref" not in it.images
        ref = it.images["single"]
        assert ref.page is None                      # 獨立影像檔，不是 TIFF 頁
        assert ref.channel == "single"
        assert os.path.isfile(ref.path)
        assert os.path.basename(ref.path) == "DEF_%04d.png" % (i + 1)
        # 座標落在假 die 內（KLARF 1.8 已是 nm）
        assert 0 < it.xrel_nm < 5_000_000
        assert 0 < it.yrel_nm < 5_000_000


# ------------------------------------------------------------ 2. 像素 + ground truth

def test_pixels_and_ground_truth(ds, truth):
    for it in ds.items:
        arr = it.load("single")
        assert arr.shape == (SIZE, SIZE)
        assert arr.dtype == np.uint8
    assert set(truth) == {it.defect_id for it in ds.items}
    n_real = sum(1 for v in truth.values() if v["is_real"])
    assert n_real == round(N * 0.5)                  # 預設 real_frac=0.5
    for v in truth.values():
        assert set(v) == {"is_real", "type"}
        if v["is_real"]:
            assert v["type"] in make_sample_rsem.REAL_TYPES
        else:
            assert v["type"] == make_sample_rsem.NUISANCE_TYPE
    assert all(v["is_real"] == (v["type"] != "none") for v in truth.values())


def test_images_are_not_all_identical(ds):
    """每張圖有自己的相位／亮度／雜訊 —— 不能是同一張複製。"""
    first = ds.items[0].load("single")
    assert any(not np.array_equal(first, it.load("single")) for it in ds.items[1:])


# ------------------------------------------------------------ 3. 決定性

def test_same_seed_identical_bytes(tmp_path):
    a = make_sample_rsem.generate(str(tmp_path / "a"), n=4, seed=42)
    b = make_sample_rsem.generate(str(tmp_path / "b"), n=4, seed=42)
    assert _read(a["klarf"]) == _read(b["klarf"])
    for pa, pb in zip(a["images"], b["images"]):
        assert _read(pa) == _read(pb), f"{os.path.basename(pa)} 位元組不同"
    assert _read(a["ground_truth"]) == _read(b["ground_truth"])

    c = make_sample_rsem.generate(str(tmp_path / "c"), n=4, seed=43)
    assert _read(c["images"][0]) != _read(a["images"][0])   # 不同 seed → 不同資料


# ------------------------------------------------------------ 4. load_patch 的 rsem 鏡射

def test_load_patch_mirrors_single_to_test(ds):
    it = ds.items[0]
    ctx = Context(meta={"_defect_item": it, "_dataset_kind": ds.kind})
    run_step("load_patch", ctx)
    # 卡片會把 single 同步一份到 test，下游卡片用預設 source="test" 就吃得到
    assert "single" in ctx.images and "test" in ctx.images
    assert np.array_equal(ctx.images["single"], ctx.images["test"])
    assert "ref" not in ctx.images
    assert ctx.features["n_channels"] == 1.0          # 只載入 single，鏡射不計數
    assert any("single" in note for note in ctx.meta.get("notes", []))


def test_load_patch_declared_writes_for_rsem():
    cls = REGISTRY["load_patch"]
    # F9 Phase 3d：一種資料型別一張 Input 卡，所以「吐什麼」不必再問 kind ——
    # 單張資料流由 ``load_single`` 這張卡負責，而它自己就答得出來。
    from adept.core.pipeline import get_step
    single = get_step("load_single")
    assert single.accepts_kinds == ("rsem", "folder")
    assert single.resolve_writes({"channels": "auto"}) == ["single", "test"]


# ------------------------------------------------------------ 5. Golden Cell 路線

def test_golden_cell_route_on_real_defect(ds, truth):
    real = [it for it in ds.items if truth[it.defect_id]["is_real"]]
    assert real, "這份 lot 應該要有 REAL 缺陷"
    it = real[0]

    ctx = Context(meta={"_defect_item": it, "_dataset_kind": ds.kind})
    run_step("load_patch", ctx)
    run_step("cell_period", ctx)
    assert abs(ctx.features["cell_px"] - PITCH) <= 2
    assert abs(ctx.features["cell_py"] - PITCH) <= 2

    run_step("golden_cell", ctx)
    single = ctx.images["single"]
    ref = ctx.images["ref"]
    assert ref.shape == single.shape
    assert ref.dtype == single.dtype
    # 疊出來的參考圖要乾淨（缺陷被洗掉），而且和原圖在缺陷處差得出來
    assert ctx.features["golden_ghost"] > 50.0
    residual = np.abs(single.astype(np.float64) - ref.astype(np.float64))
    assert residual.max() > RESIDUAL_THRESHOLD


# ------------------------------------------------------------ 6. real_frac=0

def test_real_frac_zero_has_no_planted_defect(tmp_path):
    paths = make_sample_rsem.generate(str(tmp_path / "clean"), n=6, seed=3,
                                      real_frac=0.0)
    with open(paths["ground_truth"], "r", encoding="utf-8") as f:
        gt = json.load(f)
    assert all(v == {"is_real": False, "type": "none"} for v in gt.values())

    ds0 = dataset.load_dataset(paths["klarf"])
    for it in ds0.items:
        ctx = Context(meta={"_defect_item": it, "_dataset_kind": ds0.kind})
        run_step("load_patch", ctx)
        run_step("cell_period", ctx)
        run_step("golden_cell", ctx)
        residual = np.abs(ctx.images["single"].astype(np.float64)
                          - ctx.images["ref"].astype(np.float64))
        assert residual.max() < RESIDUAL_THRESHOLD, \
            f"defect {it.defect_id} 不該有缺陷，殘差峰值卻是 {residual.max():.1f}"


# ------------------------------------------------------------ CLI / 參數防呆

def test_cli_main(tmp_path, capsys):
    rc = make_sample_rsem.main([str(tmp_path / "cli"), "--n", "2", "--seed", "1",
                                "--size", "96", "--pitch", "12", "--format", "tif"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "LOT_RSEM.001" in out
    assert os.path.isfile(str(tmp_path / "cli" / "images" / "DEF_0001.tif"))
    assert os.path.isfile(str(tmp_path / "cli" / "ground_truth.json"))
    ds1 = dataset.load_dataset(str(tmp_path / "cli" / "LOT_RSEM.001"))
    assert ds1.kind == "rsem" and len(ds1.items) == 2
    assert ds1.items[0].load("single").shape == (96, 96)


def test_bad_args_raise(tmp_path):
    with pytest.raises(ValueError):
        make_sample_rsem.generate(str(tmp_path / "x"), n=0)
    with pytest.raises(ValueError):
        make_sample_rsem.generate(str(tmp_path / "x"), real_frac=1.5)
    with pytest.raises(ValueError):
        make_sample_rsem.generate(str(tmp_path / "x"), size=48, pitch=24)
    with pytest.raises(ValueError):
        make_sample_rsem.generate(str(tmp_path / "x"), noise=-1.0)
    with pytest.raises(ValueError):
        make_sample_rsem.generate(str(tmp_path / "x"), fmt="jpg")
