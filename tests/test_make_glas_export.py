# F11 Region-3 第 1 步：合成 GLAS 匯出的驗收。
"""這一份鎖住的是**這份測試資料值得拿來開發**，不是它產得出檔案。

`AGENTS.md` §1：新功能只能用真實資料驗證的話，它在家用機上就等於不能驗證。
所以 Region-3 的第一步是這份合成品 —— 而一份「全部都對、而且長得很規律」的
假資料比沒有更糟：它會讓每一條錯誤路徑都綠燈，然後在廠內第一次跑真資料時爆。

所以斷言的是四件**刻意做進去的難處**：

1. 圖案**非週期**（GDS 的使用時機就在非週期區域）；
2. 有 **L 形**（它的 bounding box 會框到別的材質）；
3. **後面的層蓋掉前面的層**，而且真的有一顆被蓋光；
4. **壞樣本在最後面**（前面幾顆要乾淨，不然每次抽樣看到的都是特例）。

外加一條整合測試：產出來的東西要通得過 `check_glas_export.py`，
**除了那幾條刻意壞掉的**。兩支工具一起鎖，格式才不會各走各的。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_glas_export as chk        # noqa: E402
import make_glas_export as gen         # noqa: E402
import make_sample_rsem as rsem        # noqa: E402


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    """一個小的合成 RSEM lot（整個模組共用 —— 產圖不便宜）。"""
    out = tmp_path_factory.mktemp("lot")
    rsem.generate(str(out), n=6, size=64, pitch=8, seed=3)
    return str(out)


@pytest.fixture(scope="module")
def export(lot, tmp_path_factory):
    out = tmp_path_factory.mktemp("gds")
    gen.generate(lot, str(out), layers=3, seed=5)
    return str(out)


def _manifest(export_dir):
    with open(os.path.join(export_dir, "overlay_manifest.json"),
              encoding="utf-8") as f:
        return json.load(f)


def _label(export_dir, name):
    flat = chk.png_pixels(os.path.join(export_dir, name))
    head = chk.png_header(os.path.join(export_dir, name))
    return np.frombuffer(bytes(flat), np.uint8).reshape(head["height"],
                                                        head["width"])


# --------------------------------------------------------------------------- #
# 1. 難處要真的在裡面
# --------------------------------------------------------------------------- #
def test_the_layout_is_not_periodic():
    """等距的測試資料會讓「偷偷假設有週期」的程式碼一路綠燈跑到廠內才爆。"""
    rng = np.random.default_rng(5)
    shapes = gen.layer_shapes(rng, 256, 256, 0)
    xs = sorted(x for x, _y, _w, _h in shapes)
    gaps = {b - a for a, b in zip(xs, xs[1:])}
    assert len(gaps) >= 3, "形狀是等距排的 —— 那就是週期性 pattern"
    widths = {w for _x, _y, w, _h in shapes}
    assert len(widths) >= 3, "每一塊都一樣大 —— 那也是一種週期"


def test_every_layer_has_an_L_shape():
    """L 形的 bounding box 會框到別的材質 —— 「取 bbox」與「精確拆成矩形」
    的差別**只有這種形狀看得出來**。"""
    rng = np.random.default_rng(5)
    shapes = gen.layer_shapes(rng, 128, 128, 0)
    x, y, w, h = shapes[0]
    assert (x, y + h, w // 2, h) in shapes, "第一塊沒有配一個半寬的鄰居"

    # 畫出來之後，那一塊真的不是一個矩形：連通元件 1 個、矩形 2 個。
    canvas = np.zeros((128, 128), np.uint8)
    gen.paint(shapes[:2], 128, 128, 1, canvas)
    runs = chk._runs(bytearray(canvas.reshape(-1)), 128, 128, 1)
    assert chk.blob_count(runs) == 1
    assert chk.rect_count(runs) == 2


def test_a_later_layer_eats_exactly_one_layer_not_the_whole_image():
    """**這是我自己踩的坑的回歸測試。**

    第一版的 ``eaten`` 是「最後一層蓋滿整張圖」，結果那張圖 100% 都是同一個
    id —— 其他層**跟背景**一起沒了。它同時不再是一張像樣的 label 圖，也量不出
    「一層拆成幾個矩形」。要吃掉的是**一層**，不是整張圖。
    """
    rng = np.random.default_rng(5)
    label, _gray = gen.render(rng, 128, 128, layers=3, eaten=True)
    present = set(np.unique(label))
    assert 2 not in present, "倒數第二層應該被吃光"
    assert {0, 1, 3} <= present, "背景與其他層要活著（不然這張圖沒有代表性）"
    assert (label == 0).mean() > 0.2, "背景幾乎沒了 —— 又蓋太大了"


def test_without_the_eaten_flag_every_layer_survives():
    rng = np.random.default_rng(5)
    label, _gray = gen.render(rng, 128, 128, layers=3, eaten=False)
    assert {0, 1, 2, 3} <= set(np.unique(label))


def test_the_layer_names_are_the_awkward_shape_on_purpose():
    """用乾淨的名字產測試資料，等於把「layer 名怎麼變成區域名」那一題藏起來。"""
    from d4t.core.steps._util import FEATURE_PREFIX_PATTERN
    import re

    for name in gen.LAYER_NAMES:
        assert not re.match(FEATURE_PREFIX_PATTERN + "$", name), \
            "%r 已經是合法的區域名了 —— 那就驗不到改寫" % name


def test_the_bad_samples_are_at_the_end(export):
    """前面幾顆要乾淨 —— 開發與健檢都是抽前幾顆看（``--samples 2``）。"""
    rows = _manifest(export)["images"]
    assert len(rows) == 6
    assert all(r["label_png"] for r in rows[:3]), "前三顆就已經有壞的了"
    # 順序固定：… 好的 …, eaten, miss, wrong_size
    assert rows[-2]["label_png"] == "", "倒數第二顆應該是「沒有 label 檔」那顆"
    head = chk.png_header(os.path.join(export, rows[-1]["label_png"]))
    assert (head["width"], head["height"]) != (int(rows[-1]["width_px"]),
                                               int(rows[-1]["height_px"]))


# --------------------------------------------------------------------------- #
# 2. 格式照真實匯出（v4）
# --------------------------------------------------------------------------- #
def test_the_manifest_is_v4_with_the_columns_the_real_one_has(export):
    doc = _manifest(export)
    assert doc["schema"] == "mmh-gds-overlay-v4"
    assert doc["columns"] == gen.COLUMNS
    for col in ("id_source", "page", "width_px", "height_px", "nm_per_px"):
        assert col in doc["columns"]
    assert all(r["id_source"] == "klarf-defectid" for r in doc["images"])
    assert all(r["page"] == "" for r in doc["images"]), \
        "RSEM 一顆一個檔，page 要是空的"


def test_the_ids_come_from_the_klarf_not_from_a_counter(lot, export):
    """GLAS 也是讀同一份 KLARF —— 自己編 id 的話，配對那條路就沒被走過。"""
    _klarf, ids, _files = gen.read_lot(lot)
    assert [r["image_id"] for r in _manifest(export)["images"]] == ids


def test_label_is_one_channel_and_label_view_is_three(export):
    rows = [r for r in _manifest(export)["images"] if r["label_png"]]
    lab = chk.png_header(os.path.join(export, rows[0]["label_png"]))
    view = chk.png_header(os.path.join(export, rows[0]["label_view_png"]))
    assert lab["color_type"] == 0 and lab["bit_depth"] == 8
    assert view["color_type"] == 2, \
        "label_view 要是 3 通道 —— 它有一半的意義是當**指錯檔案**的陷阱"


def test_the_gray_image_lines_up_with_the_label():
    """兩張是同一組幾何畫的。對不齊的話，用 gray 當影像看到的框會是錯的。"""
    rng = np.random.default_rng(11)
    label, gray = gen.render(rng, 96, 96, layers=3, eaten=False)
    assert label.shape == gray.shape
    for i in range(3):
        inside = gray[label == i + 1]
        assert np.median(inside) == pytest.approx(gen.LAYER_GLV[i], abs=1), \
            "第 %d 層的 gray 灰階對不上它的 fg_glv" % (i + 1)


def test_the_label_is_not_blurred_but_the_gray_is():
    """``label`` 不模糊正是它存在的理由（``label == id`` 是精確的區域）。"""
    rng = np.random.default_rng(11)
    label, gray = gen.render(rng, 96, 96, layers=2, eaten=False)
    assert set(np.unique(label)) <= {0, 1, 2}, "label 出現了不是 id 的值"
    assert len(set(np.unique(gray))) > 3, "gray 沒有被模糊過"


def test_the_two_tools_agree_on_the_filename_transform():
    """檔名的來源在兩支工具裡各有一份（產的那支、驗的那支）。
    改一邊沒改另一邊 = 產出來的檔案驗不過，而症狀會很難懂。"""
    for value in ("1", "A/1", "A:1", "", "層1", "A-1_2.tif"):
        assert gen.safe_name(value) == chk.safe_name(value)


# --------------------------------------------------------------------------- #
# 3. 可重現（同 seed 同位元組）
# --------------------------------------------------------------------------- #
def test_the_same_seed_gives_the_same_bytes(lot, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    gen.generate(lot, str(a), layers=3, seed=5)
    gen.generate(lot, str(b), layers=3, seed=5)
    names = sorted(os.listdir(str(a)))
    assert names == sorted(os.listdir(str(b))) and names
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_a_different_seed_gives_a_different_layout(lot, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    gen.generate(lot, str(a), layers=3, seed=5)
    gen.generate(lot, str(b), layers=3, seed=6)
    rows = [r["label_png"] for r in _manifest(str(a))["images"] if r["label_png"]]
    assert (a / rows[0]).read_bytes() != (b / rows[0]).read_bytes()


# --------------------------------------------------------------------------- #
# 4. 整合：健檢對它的判定必須**正好**是那幾條刻意壞掉的
# --------------------------------------------------------------------------- #
def _verdicts(export_dir, samples=8):
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        chk.main([export_dir, "--samples", str(samples)])
    out = {}
    for line in buf.getvalue().splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            out[line.split("]", 1)[1].strip()] = line[1:5].strip()
    return out


def test_the_checker_passes_everything_except_the_deliberate_faults(export):
    v = _verdicts(export)
    # 刻意壞掉的兩條
    assert v["label PNG is the same size as the SEM image"] == "FAIL"
    assert v["every layer in label_map has pixels on every image"] == "WARN"
    # layer 名那條也是刻意的（見上面那條測試）
    assert v["layer names can be used as d4t region names"] == "WARN"
    # 其餘一條都不准紅
    rest = {k: got for k, got in v.items()
            if k not in ("label PNG is the same size as the SEM image",
                         "every layer in label_map has pixels on every image",
                         "layer names can be used as d4t region names")}
    assert not [k for k, got in rest.items() if got == "FAIL"], \
        "不該壞的地方壞了：%s" % [k for k, got in rest.items() if got == "FAIL"]
    assert v["manifest schema is a GLAS overlay manifest"] == "PASS"
    assert v["the manifest says image_id is the KLARF DEFECTID"] == "PASS"
    assert v["per-row image size (width_px / height_px)"] == "PASS"


def test_a_clean_export_has_no_red_at_all(lot, tmp_path):
    """把壞樣本關掉就該全綠 —— 不然「紅字」這個訊號本身就不可信。"""
    out = tmp_path / "clean"
    gen.generate(lot, str(out), layers=3, seed=5, miss=0, wrong_size=0,
                 eaten=0)
    v = _verdicts(str(out))
    bad = [k for k, got in v.items()
           if got == "FAIL" or (got == "WARN" and "layer names" not in k)]
    assert not bad, bad


def test_it_refuses_a_folder_with_no_klarf(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(SystemExit) as e:
        gen.generate(str(empty), str(tmp_path / "out"))
    assert "make_sample_rsem" in str(e.value), "要講得出下一步怎麼做"
