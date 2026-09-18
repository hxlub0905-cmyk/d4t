"""``.I01`` —— 副檔名不同的 patch TIFF（2026-09-17，使用者點名）。

使用者：「我要能支援新的圖檔叫做 I01，一樣是跟 klarf 一一配對的」。它**不是**
新的 kind、也不是新的 Load 卡：一份 KLARF 配一個檔、裡面是多頁 TIFF，資料形狀
跟 ``.tif`` 逐項相同，所以副檔名只住在「去哪找檔」那一層（`klarf_core.tiff_path`
／`dataset._TIFF_EXTS`／Studio 的檔案對話框），ingest 之後每一層都看不到它。

「內容是 TIFF」是還沒在廠內驗過的假設（`docs/FAB-VALIDATION.md` #8）—— 所以
這裡也測「假設錯的那一天使用者看到什麼」：一句講出下一步的話，不是 traceback。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import numpy as np
import pytest

from d4t.core.ingest import dataset, klarf_core

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(REPO, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import make_sample  # noqa: E402

N = 6
SEED = 7


@pytest.fixture(scope="module")
def tif_lot(tmp_path_factory):
    out = tmp_path_factory.mktemp("i01_tif")
    return make_sample.generate(str(out / "lot"), n=N, seed=SEED)


@pytest.fixture(scope="module")
def i01_lot(tmp_path_factory):
    """`--image-ext .I01` 產的：KLARF 的 TiffFileName 指到 ``LOT_SYN.I01``。"""
    out = tmp_path_factory.mktemp("i01_named")
    return make_sample.generate(str(out / "lot"), n=N, seed=SEED, image_ext=".I01")


def _copy_lot_with_renamed_image(paths, tmp_path, new_ext):
    """把 lot 複製一份，只把影像檔改名 —— KLARF **原樣**（還說 ``.tif``）。"""
    dst = tmp_path / "lot"
    shutil.copytree(paths["out_dir"], dst)
    old = dst / os.path.basename(paths["tiff"])
    new = old.with_suffix(new_ext)
    old.rename(new)
    return str(dst / os.path.basename(paths["klarf"])), str(new)


def _pixels(ds, i=0, ch="test"):
    return ds.items[i].load(ch)


# ---------------------------------------------------------------------------
# 1. 找得到：KLARF 同名 .I01（就算 KLARF 裡還寫著 .tif）
# ---------------------------------------------------------------------------
def test_a_same_stem_i01_next_to_the_klarf_is_found(tif_lot, tmp_path):
    klarf, i01 = _copy_lot_with_renamed_image(tif_lot, tmp_path, ".I01")
    doc = klarf_core.load(klarf)
    assert doc.tiff_file_name.endswith(".tif")          # KLARF 還指著舊名字
    assert doc.tiff_path() == i01                        # 同名 .I01 補上了
    ds = dataset.load_dataset(klarf)
    assert ds.kind == "ebi_patch", ds.warnings
    assert len(ds.items) == N
    assert all(sorted(it.images) == ["ref", "test"] for it in ds.items)
    ref = dataset.load_dataset(tif_lot["klarf"])
    assert np.array_equal(_pixels(ds), _pixels(ref))
    assert np.array_equal(_pixels(ds, N - 1, "ref"), _pixels(ref, N - 1, "ref"))


def test_lower_case_i01_is_found_too(tif_lot, tmp_path):
    """Linux 的檔名分大小寫；廠內的檔案怎麼命名不歸我們管。"""
    klarf, i01 = _copy_lot_with_renamed_image(tif_lot, tmp_path, ".i01")
    assert klarf_core.load(klarf).tiff_path() == i01
    assert dataset.load_dataset(klarf).kind == "ebi_patch"


# ---------------------------------------------------------------------------
# 2. KLARF 自己就指到 .I01（TiffFileName）
# ---------------------------------------------------------------------------
def test_a_klarf_that_names_the_i01_loads_and_gives_the_same_pixels(tif_lot, i01_lot):
    assert i01_lot["tiff"].endswith("LOT_SYN.I01")
    text = open(i01_lot["klarf"], encoding="utf-8").read()
    assert "TiffFileName LOT_SYN.I01;" in text
    ds = dataset.load_dataset(i01_lot["klarf"])
    assert ds.kind == "ebi_patch", ds.warnings
    ref = dataset.load_dataset(tif_lot["klarf"])
    assert ds.warnings == ref.warnings       # 副檔名沒有多講一句話
    for i in range(N):
        for ch in ("test", "ref"):
            assert np.array_equal(_pixels(ds, i, ch), _pixels(ref, i, ch))


def test_the_i01_lot_differs_from_the_tif_lot_only_by_name(tif_lot, i01_lot):
    """副檔名不進像素、不進 ground truth：兩份除了那一行逐位元組相同。"""
    with open(tif_lot["tiff"], "rb") as a, open(i01_lot["tiff"], "rb") as b:
        assert a.read() == b.read()
    with open(tif_lot["ground_truth"], "rb") as a, open(i01_lot["ground_truth"], "rb") as b:
        assert a.read() == b.read()
    ka = open(tif_lot["klarf"], encoding="utf-8").read().splitlines()
    kb = open(i01_lot["klarf"], encoding="utf-8").read().splitlines()
    diff = [(x, y) for x, y in zip(ka, kb) if x != y]
    assert len(ka) == len(kb) and diff == [
        ("TiffFileName LOT_SYN.tif;", "TiffFileName LOT_SYN.I01;")]


def test_make_sample_refuses_an_extension_ingest_would_not_find(tmp_path):
    """`.png` 產得出來、但 KLARF 旁邊沒人會去找它 —— 那是一份安靜壞掉的資料。"""
    with pytest.raises(ValueError, match="image_ext"):
        make_sample.generate(str(tmp_path / "lot"), n=2, image_ext=".png")


# ---------------------------------------------------------------------------
# 3. 假設錯的那一天：內容不是 TIFF
# ---------------------------------------------------------------------------
def test_an_i01_that_is_not_a_tiff_inside_says_so_and_points_at_the_probe(tif_lot, tmp_path):
    klarf, i01 = _copy_lot_with_renamed_image(tif_lot, tmp_path, ".I01")
    with open(i01, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)     # 隨便一種不是 TIFF 的東西
    ds = dataset.load_dataset(klarf)
    # 不炸、不假裝：defect 進來了、沒有影像、warnings 講出檔名與下一步
    assert len(ds.items) == N
    assert all(it.images == {} for it in ds.items)
    said = "\n".join(ds.warnings)
    assert "LOT_SYN.I01" in said
    assert "probe_tiff.py" in said
    assert "Traceback" not in said


# ---------------------------------------------------------------------------
# 4. 三處要對得上：ingest 的表、Studio 的對話框、廠內探測腳本
# ---------------------------------------------------------------------------
def test_i01_is_in_the_tiff_family_everywhere():
    assert ".I01" in klarf_core.PATCH_IMAGE_EXTS
    assert {".i01", ".I01"} <= set(klarf_core.patch_image_ext_variants())
    assert ".i01" in dataset._TIFF_EXTS
    assert dataset._TIFF_EXTS <= dataset._IMAGE_EXTS
    # ⚠ 對話框 2026-09-18（F110）搬去 `ui/open_dialogs.py` 了 —— 那一輪要加
    # 第五顆 Open 鈕，而 `studio.py` 那格天花板只准往下，所以整族搬家。
    # 這裡跟著搬：問的是「那些過濾字串認不認得 .I01」，不是它們住在哪個檔案。
    src = open(os.path.join(REPO, "d4t", "ui", "open_dialogs.py"),
               encoding="utf-8").read()
    filters = re.findall(r'"(?:Multi-page TIFF|Images) \(([^)]*)\)', src)
    # ⚠ 2026-09-18（F114）從兩條變一條：`Open stack…` 拿掉了，
    # `STACK_FILTER` 跟著走。數量不是重點（寫死數字的話下一次加／減一顆
    # Open 鈕就要來改它）—— 重點是**還在的每一條都認得 `.I01`**。
    assert filters, "一條過濾字串都沒抓到 —— 這支測試問不出任何事"
    for f in filters:
        assert ".I01" in f or ".i01" in f, f
    for f in filters:
        assert "*.I01" in f, f


def test_load_image_file_treats_an_i01_like_a_multipage_tiff(i01_lot):
    """`Open image…` 挑到一個 I01：跟 `.tif` 一樣只讀第 0 頁、並講去哪開。"""
    ds = dataset.load_image_file(i01_lot["tiff"])
    assert ds.kind == "folder" and len(ds.items) == 1
    assert any("more than one page" in w for w in ds.warnings)


def _run(script, *args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, script] + [str(a) for a in args],
                          cwd=REPO, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    return (proc.returncode, proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def test_probe_tiff_reads_an_i01_and_pairs_it_with_the_klarf(i01_lot):
    """廠內回答 #8 用的那支：不看副檔名、只看檔頭，配對得起來。"""
    code, out, err = _run(os.path.join(REPO, "fab_probe", "probe_tiff.py"),
                          i01_lot["tiff"], "--with-klarf", i01_lot["klarf"])
    assert code == 0, err
    assert "Traceback" not in err
    assert "n_pages" in out or "頁" in out


def test_probe_klarf_finds_the_sibling_i01(tif_lot, tmp_path):
    klarf, _i01 = _copy_lot_with_renamed_image(tif_lot, tmp_path, ".I01")
    code, out, err = _run(os.path.join(REPO, "fab_probe", "probe_klarf.py"), klarf)
    assert code == 0, err
    assert ".I01" in out                 # 候選清單裡有它、而且找到了


# ---------------------------------------------------------------------------
# 5. 真檔長的樣子（2026-09-17 使用者的 agent 看過）：record 語法、巢狀 ImageFileName、
#    列尾 Images {id "type"} —— 識別碼全部遮蔽，斷言的是結構
# ---------------------------------------------------------------------------
def _record_klarf(ids_per_row):
    rows = []
    for k, (a, b) in enumerate(ids_per_row):
        rows.append('          %d 100 200 1 2 10 10 5 25.0 0 12 0 0 3 0 0 0 2  '
                    'Images 2 {%d "30",%d "31"} ;' % (k + 1, a, b))
    return (
        'Record FileRecord  "1.8"\n{\n  Record LotRecord "LOT_SYN"\n  {\n'
        '    Field DeviceID 1 {"SYNDEV"}\n'
        '    Record WaferRecord "07"\n    {\n'
        '      Field SlotNumber 1 {1}\n'
        '      Field ImageFileName 2 {"LOT_SYN_1.I01", "TIF"}\n'
        '      List DefectList\n      {\n'
        '        Columns 19 { int32 DEFECTID, int32 XREL, int32 YREL, int32 XINDEX, '
        'int32 YINDEX, int32 XSIZE, int32 YSIZE, int32 DSIZE, float DEFECTAREA, '
        'int32 CLASSNUMBER, int32 OTYPE, int32 VOLUME, int32 GRADE, int32 TEST, '
        'int32 ROUGHBINNUMBER, int32 REVIEWSAMPLE, int32 CLUSTERNUMBER, '
        'int32 IMAGECOUNT, ImageList Images }\n'
        '        Data %d\n        {\n%s\n        }\n      }\n    }\n  }\n}\n'
        % (len(rows), "\n".join(rows)))


def test_a_record_syntax_klarf_names_its_i01_in_the_wafer_record(tif_lot, tmp_path):
    """`Field ImageFileName {"<lot>_1.I01", "TIF"}` 住在 WaferRecord 裡，一樣讀得到；
    檔在旁邊就配得起來，id 連號 → page = id − 1；"30" 在前 = test。"""
    lot = tmp_path / "lot"
    lot.mkdir()
    klarf = lot / "LOT_SYN_1.001"
    klarf.write_text(_record_klarf([(2 * k + 1, 2 * k + 2) for k in range(N)]),
                     encoding="utf-8")
    shutil.copy(tif_lot["tiff"], lot / "LOT_SYN_1.I01")
    doc = klarf_core.load(str(klarf))
    assert doc.version == "1.8"
    assert doc.tiff_file_name == "LOT_SYN_1.I01"
    assert doc.tiff_path() == str(lot / "LOT_SYN_1.I01")
    # `"30"` 是影像類型名不是檔名 —— 不准被當成每顆一個檔
    assert doc.defect_image_filename(doc.defects[0]) is None
    ds = dataset.load_dataset(str(klarf))
    assert ds.kind == "ebi_patch", ds.warnings
    assert [(it.images["test"].page, it.images["ref"].page) for it in ds.items] \
        == [(2 * i, 2 * i + 1) for i in range(N)]


def test_the_i01_missing_next_to_a_record_klarf_says_so_not_a_bogus_filename(tmp_path):
    klarf = tmp_path / "LOT_SYN_1.001"
    klarf.write_text(_record_klarf([(1, 2), (3, 4), (5, 6)]), encoding="utf-8")
    ds = dataset.load_dataset(str(klarf))
    assert all(it.images == {} for it in ds.items)          # 不會去開一個叫 "30" 的檔
    assert any("LOT_SYN_1.I01" in w for w in ds.warnings)   # 講的是那個不在的 .I01


def test_globally_numbered_image_ids_map_to_page_id_minus_one(tmp_path):
    """真檔確認（2026-09-17，使用者的 agent 走完整條 IFD 鏈）：id 全檔連號、
    缺陷 N 的兩張是 2N−1（"30"）與 2N（"31"）、**page = id − 1**，
    132,230 頁 = 66,115 顆 × 2。那正是 `defect_image_map` 的 imagelist（1-based）
    模式 —— 這裡鎖住它：DID 1 → page 0/1、DID 51 → page 100/101。"""
    klarf = tmp_path / "LOT_SYN_1.001"
    klarf.write_text(_record_klarf([(2 * k + 1, 2 * k + 2) for k in range(51)]),
                     encoding="utf-8")
    m = klarf_core.load(str(klarf)).defect_image_map(None)
    assert m["mode"] == "imagelist" and m["base"] == 1
    assert m["pages"][0] == [0, 1]
    assert m["pages"][50] == [100, 101]
