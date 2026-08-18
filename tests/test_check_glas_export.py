# F11 Region-3 準備：GLAS 匯出健檢腳本的驗收。
"""這一份鎖住的是**那支腳本說對了話**，不是它跑得完。

它服務的情況很特別（`AGENTS.md` §2）：真實資料在一台**只能複製文字出來**的機器
上。所以這支腳本的產出是「使用者會貼給我看的那段文字」——

* **它不能洩漏廠內識別碼**（鐵則 8）。遮蔽漏一次，那段文字就進了對話紀錄。
* **它不能把「我沒查」印成 PASS。** 那份報告是之後所有設計決定的依據，
  一個假的綠燈會讓整個 Region-3 蓋在錯的假設上 —— 而那正是這個 repo
  一直在殺的那類錯（「跑得完、有數字、而且是錯的」）。

每一條檢查對應 GLAS 程式碼裡的一個**真實**行為（commit bef5492），
出處寫在 `tools/check_glas_export.py` 的檔頭。
"""
from __future__ import annotations

import json
import os
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_glas_export as chk  # noqa: E402


# --------------------------------------------------------------------------- #
# 一份最小的 PNG 寫出器 —— 測試不靠 OpenCV（腳本自己也不靠）
# --------------------------------------------------------------------------- #
def _png(path, rows, color_type=0, bit_depth=8):
    """把一組 row（每個 row 是一串 0..255）寫成 PNG。"""
    h = len(rows)
    w = len(rows[0])
    per = {0: 1, 2: 3}[color_type]
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(kind, data):
        c = kind + data
        return (struct.pack(">I", len(data)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w // per, h, bit_depth, color_type, 0, 0, 0)
    Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _label_rows(w=16, h=12):
    """兩個區域：id 1 在左上、id 2 在右下。"""
    rows = [[0] * w for _ in range(h)]
    for y in range(2, 6):
        for x in range(2, 8):
            rows[y][x] = 1
    for y in range(7, 11):
        for x in range(9, 15):
            rows[y][x] = 2
    return rows


def _export(tmp_path, ids=("1", "2"), layers=("EPI", "MG"), with_raw=True,
            label_color_type=0, label_map=True, sizes=None):
    d = tmp_path / "export"
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, did in enumerate(ids):
        base = chk.safe_name(did)
        lab = _label_rows(*(sizes[i] if sizes else (16, 12)))
        if label_color_type == 2:
            lab = [[v for value in r for v in (value, value, value)]
                   for r in lab]
        _png(d / ("%s_label.png" % base), lab, color_type=label_color_type)
        if with_raw:
            _png(d / ("%s_raw.png" % base),
                 [[100] * 16 for _ in range(12)])
        rows.append({"image_id": did, "raw_png":
                     ("%s_raw.png" % base) if with_raw else "",
                     "overlay_png": "", "fine_dx_nm": 0.5, "fine_dy_nm": 0.5,
                     "score": 0.9, "status": "ok", "gray_png": "",
                     "label_png": "%s_label.png" % base, "label_view_png": ""})
    doc = {"schema": "mmh-gds-overlay-v3",
           "columns": list(rows[0].keys()), "images": rows}
    if label_map:
        doc["label_map"] = [{"id": n + 1, "layer": name, "fg_glv": 200 - n * 40}
                            for n, name in enumerate(layers)]
    (d / "overlay_manifest.json").write_text(json.dumps(doc), encoding="utf-8")
    return d


def _run(export_dir, **kw):
    """跑一次，回傳 ``(輸出文字, {檢查項: 判定})``。"""
    import io
    import contextlib

    argv = [str(export_dir)]
    for key, value in kw.items():
        argv += ["--%s" % key.replace("_", "-"), str(value)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        chk.main(argv)
    text = buf.getvalue()
    verdicts = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            verdicts[line.split("]", 1)[1].strip()] = line[1:5].strip()
    return text, verdicts


# --------------------------------------------------------------------------- #
# 1. 遮蔽 —— 這一段最重要（鐵則 8）
# --------------------------------------------------------------------------- #
def test_no_fab_identifier_reaches_the_report(tmp_path):
    """報告是要**貼出來**的。廠內識別碼一個都不准在裡面。"""
    d = _export(tmp_path, ids=("LOTX_W03_D0001", "LOTX_W03_D0002"),
                layers=("SECRETLAYER (L17/D0)", "OTHERLAYER (L21/D0)"))
    text, _v = _run(d)
    for secret in ("SECRETLAYER", "OTHERLAYER", "LOTX", "W03", "D0001",
                   "L17", "L21", str(d)):
        assert secret not in text, "報告洩漏了 %r" % secret


def test_the_shape_of_an_id_survives_the_masking(tmp_path):
    """遮值不遮**格式** —— 有沒有補零、是不是純數字，決定 ADEPT 怎麼配對。"""
    assert "zero-padded" in chk.Masker.shape_of("0007")
    assert "all-digits" in chk.Masker.shape_of("42")
    assert "NON-ASCII" in chk.Masker.shape_of("層1")
    assert "has-punctuation" in chk.Masker.shape_of("A/1")


def test_reveal_is_opt_in(tmp_path):
    d = _export(tmp_path, layers=("EPI", "MG"))
    assert "EPI" not in _run(d)[0]
    assert "EPI" in _run_reveal(d), "--reveal 要看得到真值（那一份不能貼）"
    assert "do not paste" in _run_reveal(d)


def _run_reveal(export_dir):
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        chk.main([str(export_dir), "--reveal"])
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# 2. 「我沒查」不准印成 PASS
# --------------------------------------------------------------------------- #
def test_a_check_that_could_not_run_says_skip_not_pass(tmp_path):
    """沒有 ``_raw.png`` 又沒給 ``--images`` 時，尺寸根本沒得比。

    這一條以前是綠燈的 —— 而這份報告是之後所有設計決定的依據，
    一個假的綠燈會讓整個 Region-3 蓋在錯的假設上。
    """
    d = _export(tmp_path, with_raw=False)
    _text, v = _run(d)
    assert v["label PNG is the same size as the SEM image"] == "SKIP"


def test_the_size_check_really_compares_when_it_can(tmp_path):
    d = _export(tmp_path, with_raw=True)
    assert _run(d)[1]["label PNG is the same size as the SEM image"] == "PASS"
    d2 = _export(tmp_path / "b", with_raw=True, sizes=[(16, 12), (20, 12)])
    assert _run(d2)[1]["label PNG is the same size as the SEM image"] == "FAIL"


# --------------------------------------------------------------------------- #
# 3. 每一條檢查對應 GLAS 的一個真實行為
# --------------------------------------------------------------------------- #
def test_a_three_channel_label_is_a_failure(tmp_path):
    """``_label_view.png`` 是 3 通道的上色預覽。指錯檔案的話，ADEPT 會把通道
    平均掉，label id 1、2、3 被混成一堆不存在的值 —— **而它不會報錯**。"""
    d = _export(tmp_path, label_color_type=2)
    text, v = _run(d)
    assert v["label PNG is single-channel 8-bit greyscale"] == "FAIL"
    assert "label_view" in text


def test_a_missing_label_map_is_a_failure(tmp_path):
    """GLAS 只有在匯出時勾了 label 才寫 ``label_map``。沒有它就沒有名字。"""
    d = _export(tmp_path, label_map=False)
    assert _run(d)[1]["manifest carries label_map"] == "FAIL"


def test_ids_that_collapse_onto_one_filename_are_caught(tmp_path):
    """``a/b`` 與 ``a:b`` 都被 ``_safe_name`` 折成 ``a_b`` —— 後匯出的那顆
    **覆蓋**前一顆的 PNG，而 manifest 兩列的 image_id 仍然不同。"""
    d = _export(tmp_path, ids=("a/b", "a:b"))
    _text, v = _run(d)
    assert v["no two image_ids collapse onto the same filename"] == "FAIL"
    assert v["DEFECTID can be used verbatim to build the filename"] == "WARN"


def test_a_clean_id_does_not_raise_the_safe_name_warning(tmp_path):
    d = _export(tmp_path, ids=("1", "2"))
    v = _run(d)[1]
    assert v["DEFECTID can be used verbatim to build the filename"] == "PASS"
    assert v["no two image_ids collapse onto the same filename"] == "PASS"


def test_safe_name_matches_glas(tmp_path):
    """這六行是從 GLAS 抄過來的。抄錯 = ADEPT 配對出來的檔名跟 GLAS 寫的不同。"""
    assert chk.safe_name("a/b") == "a_b"
    assert chk.safe_name("A-1_2.tif") == "A-1_2.tif"
    assert chk.safe_name("") == "image"
    assert chk.safe_name("層1") == "層1"          # isalnum() 是 Unicode-aware


def test_a_layer_that_lost_every_pixel_is_reported(tmp_path):
    """GLAS 依序畫層，**後面的蓋掉前面的**。一層可能在某些 defect 上被吃光，
    而它的名字還留在 ``label_map`` —— 那一顆的區域就是空的。"""
    d = _export(tmp_path, ids=("1",), layers=("A", "B", "C"))
    _text, v = _run(d)
    assert v["every layer in label_map has pixels on every image"] == "WARN"


def test_a_pixel_value_with_no_entry_is_a_failure(tmp_path):
    d = _export(tmp_path, ids=("1",), layers=("A",))     # 圖裡有 id 2
    assert _run(d)[1]["every pixel value appears in label_map"] == "FAIL"


def test_a_declared_file_that_is_not_there_is_a_failure(tmp_path):
    d = _export(tmp_path)
    os.remove(str(d / "1_label.png"))
    assert _run(d)[1]["every label_png named in the manifest is on disk"] \
        == "FAIL"


def test_a_folder_with_no_label_pngs_says_so(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert _run(d)[1]["label PNGs are present"] == "FAIL"


def test_the_missing_width_height_column_is_always_flagged(tmp_path):
    """GLAS 的 manifest 沒有 ``width_px`` / ``height_px``
    （`GLAS-INTERFACE.md` §4「建議 3」）。這條 WARN 是給 GLAS 那邊的待辦。"""
    assert _run(_export(tmp_path))[1][
        "per-row image size (width_px / height_px)"] == "WARN"


# --------------------------------------------------------------------------- #
# 4. 純標準函式庫的 PNG 讀取（腳本靠它回答「是不是單通道」）
# --------------------------------------------------------------------------- #
def test_the_png_reader_counts_the_label_ids(tmp_path):
    path = tmp_path / "a.png"
    _png(path, _label_rows())
    counts, why = chk.png_value_counts(str(path))
    assert why == ""
    assert counts[1] == 4 * 6 and counts[2] == 4 * 6
    assert counts[0] == 16 * 12 - 48


def test_the_png_reader_refuses_rather_than_guesses(tmp_path):
    """讀不到本身就是答案。硬猜只會給一個錯的直方圖。"""
    path = tmp_path / "rgb.png"
    _png(path, [[v for _ in range(3) for v in (7,)] * 4 for _ in range(3)],
         color_type=2)
    counts, why = chk.png_value_counts(str(path))
    assert counts is None and "channel" in why
    assert chk.png_value_counts(str(tmp_path / "nope.png"))[0] is None


@pytest.mark.parametrize("filter_type", [0, 1, 2, 3, 4])
def test_every_row_filter_decodes(tmp_path, filter_type):
    """PNG 的五種列濾波都要吃得下 —— 寫檔的人選哪一種不是我們能控制的。"""
    w, h = 8, 4
    want = [[(x * 3 + y) % 7 for x in range(w)] for y in range(h)]
    raw = bytearray()
    prev = [0] * w
    for row in want:
        raw.append(filter_type)
        for i, value in enumerate(row):
            left = row[i - 1] if i else 0
            up = prev[i]
            ul = prev[i - 1] if i else 0
            if filter_type == 0:
                out = value
            elif filter_type == 1:
                out = value - left
            elif filter_type == 2:
                out = value - up
            elif filter_type == 3:
                out = value - ((left + up) >> 1)
            else:
                p = left + up - ul
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - ul)
                pr = left if (pa <= pb and pa <= pc) else (up if pb <= pc else ul)
                out = value - pr
            raw.append(out & 0xFF)
        prev = row

    def chunk(kind, data):
        c = kind + data
        return (struct.pack(">I", len(data)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))

    path = tmp_path / "f.png"
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))
    counts, why = chk.png_value_counts(str(path))
    assert why == ""
    expect = {}
    for row in want:
        for value in row:
            expect[value] = expect.get(value, 0) + 1
    assert counts == expect


def test_the_png_reader_survives_idat_split_across_chunks(tmp_path):
    """PNG 允許把壓縮資料切成好幾個 IDAT，而 OpenCV 寫大圖時就會切。"""
    w, h = 6, 3
    payload = zlib.compress(b"".join(b"\x00" + bytes([1] * w) for _ in range(h)))
    half = len(payload) // 2

    def chunk(kind, data):
        c = kind + data
        return (struct.pack(">I", len(data)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))

    path = tmp_path / "split.png"
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", payload[:half]) + chunk(b"IDAT", payload[half:])
        + chunk(b"IEND", b""))
    counts, why = chk.png_value_counts(str(path))
    assert why == "" and counts == {1: w * h}


# --------------------------------------------------------------------------- #
# 5. 它不寫檔、不連網
# --------------------------------------------------------------------------- #
def test_it_never_writes_anything(tmp_path):
    """在受限機器上跑別人的匯出資料夾 —— 它只准讀。"""
    d = _export(tmp_path)
    before = {p: p.stat().st_mtime_ns for p in sorted(d.iterdir())}
    _run(d)
    after = {p: p.stat().st_mtime_ns for p in sorted(d.iterdir())}
    assert before == after


def test_a_folder_that_is_not_there_exits_cleanly(tmp_path):
    assert chk.main([str(tmp_path / "nope")]) == 2


def test_the_klarf_argument_takes_a_folder_too(tmp_path):
    """使用者手上是一個資料夾（KLARF 跟影像放在一起）。要他先去看清楚 KLARF
    叫什麼名字才跑得動,是一個沒必要的步驟 —— 而每個沒必要的步驟都是一次
    「算了不跑」的機會（推廣鐵則）。"""
    lot = tmp_path / "lot"
    lot.mkdir()
    (lot / "LOT_SYN.001").write_text("x", encoding="utf-8")
    (lot / "notes.md").write_text("x", encoding="utf-8")
    assert chk.find_klarf(str(lot)).endswith("LOT_SYN.001")
    assert chk.find_klarf(str(lot / "LOT_SYN.001")).endswith("LOT_SYN.001")
    # 找不到就原樣回傳（呼叫端看得出來它還是一個資料夾，並說出可以照做的話）
    empty = tmp_path / "empty"
    empty.mkdir()
    assert chk.find_klarf(str(empty)) == str(empty)


def test_a_folder_with_no_klarf_says_what_to_do(tmp_path):
    d = _export(tmp_path)
    empty = tmp_path / "nothing"
    empty.mkdir()
    _text, v = _run(d, klarf=str(empty))
    assert v["manifest image_id == KLARF DEFECTID"] == "SKIP"


# --------------------------------------------------------------------------- #
# 6. 一層拆成幾塊、幾個矩形 —— Region-3 的設計就靠這兩個數字
# --------------------------------------------------------------------------- #
def _runs_of(grid, value=1):
    flat = bytearray(v for row in grid for v in row)
    return chk._runs(flat, len(grid[0]), len(grid), value)


def test_a_rectangle_is_one_rectangle():
    grid = [[0, 0, 0, 0],
            [0, 1, 1, 0],
            [0, 1, 1, 0],
            [0, 0, 0, 0]]
    assert chk.rect_count(_runs_of(grid)) == 1
    assert chk.blob_count(_runs_of(grid)) == 1


def test_an_L_is_two_rectangles_but_one_piece():
    """這正是「取 bounding box」會出錯的形狀 —— 而 ``pieces`` 才是「一份」。"""
    grid = [[1, 1, 1, 1],
            [1, 1, 1, 1],
            [1, 1, 0, 0],
            [1, 1, 0, 0]]
    assert chk.rect_count(_runs_of(grid)) == 2
    assert chk.blob_count(_runs_of(grid)) == 1


def test_two_separate_shapes_are_two_pieces():
    grid = [[1, 1, 0, 1, 1],
            [1, 1, 0, 1, 1]]
    assert chk.blob_count(_runs_of(grid)) == 2
    assert chk.rect_count(_runs_of(grid)) == 2


def test_a_diagonal_staircase_is_one_piece_and_many_rectangles():
    """非 Manhattan 的邊界會炸成一堆 1px 的矩形 —— 這個數字要看得到，
    不然 ``max_boxes`` 會安靜地砍掉大半。"""
    n = 6
    grid = [[1 if x <= y else 0 for x in range(n)] for y in range(n)]
    assert chk.blob_count(_runs_of(grid)) == 1
    assert chk.rect_count(_runs_of(grid)) == n


def test_a_shape_that_skips_a_row_does_not_merge_across_the_gap():
    """中間空一列的兩塊不准被合併成一個矩形（往下長只認**相鄰**的那一列）。"""
    grid = [[1, 1],
            [0, 0],
            [1, 1]]
    assert chk.rect_count(_runs_of(grid)) == 2
    assert chk.blob_count(_runs_of(grid)) == 2


def test_the_decomposition_is_reported_for_a_real_sized_layer(tmp_path):
    """報告要講得出「這一層有幾個矩形」—— 那是 Region-3 唯一的設計輸入。"""
    d = _export(tmp_path, ids=("1",), layers=("A", "B"))
    text, v = _run(d)
    assert "rectangles" in text
    assert "a layer fits under the Region cards' default box cap (64)" in v
