"""Tests for fab_probe/ — 廠內格式探測腳本（以 subprocess 跑，檢查文字輸出）。

這三支腳本是「單檔、純標準函式庫」的，所以測試也把它們當外部程式跑：
用 tools/make_sample*.py 產生資料 → `sys.executable probe_*.py` → 檢查輸出文字。
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_DIR = os.path.join(REPO, "fab_probe")
KLARF_PROBE = os.path.join(PROBE_DIR, "probe_klarf.py")
TIFF_PROBE = os.path.join(PROBE_DIR, "probe_tiff.py")
STATS_PROBE = os.path.join(PROBE_DIR, "probe_stats.py")
ALL_PROBES = (KLARF_PROBE, TIFF_PROBE, STATS_PROBE)

_TOOLS = os.path.join(REPO, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

N_EBI = 6
N_RSEM = 4

# 真實感的識別碼（遮蔽測試用）：這些字串預設絕不可以出現在報告裡
REAL_LOT = "AA0000.0X"
REAL_WAFER = "AA0000.01"
REAL_DEVICE = "DEVICE0001"


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def ebi(tmp_path_factory):
    import make_sample                                  # noqa: WPS433 (lazy)
    out = tmp_path_factory.mktemp("probe_ebi")
    return make_sample.generate(str(out / "lot"), n=N_EBI, seed=7)


@pytest.fixture(scope="module")
def rsem(tmp_path_factory):
    import make_sample_rsem                             # noqa: WPS433
    out = tmp_path_factory.mktemp("probe_rsem")
    return make_sample_rsem.generate(str(out / "lot"), n=N_RSEM, seed=11)


@pytest.fixture(scope="module")
def ebi_with_ids(ebi, tmp_path_factory):
    """把合成 KLARF 的 LotID/WaferID/DeviceID 換成真實感的字串。"""
    out = tmp_path_factory.mktemp("probe_ids")
    src = ebi["klarf"]
    text = open(src, encoding="utf-8").read()
    text = (text.replace('LotID "LOT_SYN"', 'LotID "%s"' % REAL_LOT)
                .replace('WaferID "W01"', 'WaferID "%s"' % REAL_WAFER)
                .replace('DeviceID "SYNDEV"', 'DeviceID "%s"' % REAL_DEVICE))
    assert REAL_LOT in text and REAL_WAFER in text and REAL_DEVICE in text
    dst = str(out / "LOT_SYN.001")
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return dst


# ---------------------------------------------------------------- helpers

def run_probe(script, *args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run([sys.executable, script] + [str(a) for a in args],
                          cwd=REPO, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    return proc.returncode, out, err


def parse_summary(out):
    """取出 >>>JSON_BEGIN … >>>JSON_END 之間的摘要並解析。"""
    assert ">>>JSON_BEGIN" in out and ">>>JSON_END" in out, "報告缺少可回報的 JSON 區塊"
    body = out.split(">>>JSON_BEGIN", 1)[1].split(">>>JSON_END", 1)[0]
    return json.loads(body)


# ---------------------------------------------------------------- probe_klarf

def test_klarf_12_structure(ebi):
    code, out, err = run_probe(KLARF_PROBE, ebi["klarf"])
    assert code == 0, err
    s = parse_summary(out)
    assert s["klarf_version"] == "1.2"
    assert s["version_heuristic"] == "FileVersion N M"
    assert s["defect_columns"] == ["DEFECTID", "XREL", "YREL", "XINDEX", "YINDEX",
                                   "CLASSNUMBER", "IMAGECOUNT", "IMAGELIST"]
    assert s["n_defect_rows"] == N_EBI
    assert s["n_defect_lists"] == 1
    # 影像佈局：IMAGELIST 欄 + TiffSpec 宣告每張圖 1 個 token
    assert s["image_layout_variant"] == "declared"
    assert s["image_layout_nfields"] == 1
    assert s["imagecount_distribution"] == {"2": N_EBI}
    assert s["total_images"] == 2 * N_EBI
    assert s["tiff_referenced"] is True and s["tiff_exists"] is True
    assert s["row_length_anomalies_aligned"] == 0
    assert "1.2" in out and "假設 #3" in out


def test_klarf_18_structure(rsem):
    code, out, err = run_probe(KLARF_PROBE, rsem["klarf"])
    assert code == 0, err
    s = parse_summary(out)
    assert s["klarf_version"] == "1.8"
    assert s["version_heuristic"] == "Record FileRecord"
    assert s["defect_columns"][-1] == "IMAGEINFO"
    assert s["defect_column_types"][-1] == "ImageList"
    assert s["n_defect_rows"] == N_RSEM
    assert s["image_layout_variant"] == "images18"
    assert s["imagecount_distribution"] == {"1": N_RSEM}
    # 每顆 defect 一個 PNG，且都找得到
    assert s["n_rows_with_image_filename"] == N_RSEM
    assert s["n_image_files_found"] == N_RSEM
    assert s["image_file_extensions"] == {".png": N_RSEM}


def test_klarf_variant_d_real_fixture():
    """廠內實檔樣式：沒有 IMAGECOUNT 欄，但列尾帶 Images 子區塊（變體 D）。"""
    fixture = os.path.join(REPO, "tests", "fixtures", "sample_real.klarf")
    code, out, err = run_probe(KLARF_PROBE, fixture)
    assert code == 0, err
    s = parse_summary(out)
    assert s["klarf_version"] == "1.8"
    assert s["imagecount_col"] == -1
    assert s["image_layout_variant"] == "imagefile"
    assert s["n_defect_columns"] == 42
    # 影像子區塊壓成一個 token 後，每列都對得上 42 欄
    assert s["row_length_anomalies_aligned"] == 0


def test_klarf_redacts_identifiers_by_default(ebi_with_ids):
    code, out, err = run_probe(KLARF_PROBE, ebi_with_ids)
    assert code == 0, err
    for ident in (REAL_LOT, REAL_WAFER, REAL_DEVICE):
        assert ident not in out, "預設輸出洩漏了識別碼 %s" % ident
    assert "<redacted," in out
    # 欄位名本身要看得到（那是格式資訊，不是資料）
    assert "LotID" in out and "WaferID" in out and "DeviceID" in out
    # 座標欄的值一個都不能出現
    rows = open(ebi_with_ids, encoding="utf-8").read().splitlines()
    xrels = [ln.split()[1] for ln in rows if ln.strip()[:1].isdigit() and len(ln.split()) == 9]
    assert xrels, "測資裡應該有 defect 列"
    for v in xrels:
        assert v not in out, "報告洩漏了座標值 %s" % v


def test_klarf_include_ids_opt_in(ebi_with_ids):
    code, out, err = run_probe(KLARF_PROBE, ebi_with_ids, "--include-ids")
    assert code == 0, err
    for ident in (REAL_LOT, REAL_WAFER, REAL_DEVICE):
        assert ident in out, "--include-ids 應該要輸出 %s" % ident
    assert parse_summary(out)["ids_included"] is True


def test_klarf_rows_option(ebi):
    code, out, _ = run_probe(KLARF_PROBE, ebi["klarf"], "--rows", "3")
    assert code == 0
    assert parse_summary(out)["n_defect_rows"] == N_EBI


# ---------------------------------------------------------------- probe_tiff

def test_tiff_pages_and_uniformity(ebi):
    code, out, err = run_probe(TIFF_PROBE, ebi["tiff"])
    assert code == 0, err
    s = parse_summary(out)
    assert s["n_pages"] == 2 * N_EBI
    assert s["uniform_pages"] is True
    assert s["n_page_signatures"] == 1
    assert s["page0"]["width"] == 128 and s["page0"]["height"] == 128
    assert s["page0"]["bits"] == 8 and s["page0"]["layout"] == "strip"
    assert s["bigtiff"] is False


def test_tiff_with_klarf_reports_pairing(ebi):
    code, out, err = run_probe(TIFF_PROBE, ebi["tiff"],
                               "--with-klarf", ebi["klarf"])
    assert code == 0, err
    s = parse_summary(out)
    cross = s["klarf_crosscheck"]
    assert cross is not None
    assert cross["n_defect_rows"] == N_EBI
    assert cross["pattern"] == "pairs"
    assert cross["pages_eq_2x_defects"] is True
    assert cross["pages_eq_imagecount"] is True
    assert cross["map_mode"] == "imagelist"
    assert cross["map_base"] == 1
    assert cross["map_out_of_range"] == 0
    assert "假設 #1" in out
    assert "defect #0 -> [0, 1]" in out


def test_tiff_with_rsem_klarf_reports_single(ebi, rsem):
    """給錯配的 KLARF 也不能爆：要如實報出 single 與連續配頁。"""
    code, out, err = run_probe(TIFF_PROBE, ebi["tiff"], "--with-klarf", rsem["klarf"])
    assert code == 0, err
    cross = parse_summary(out)["klarf_crosscheck"]
    assert cross["pattern"] == "single"
    assert cross["pages_eq_imagecount"] is False
    assert cross["map_mode"] == "sequential"


def test_tiff_text_tag_redaction_rule():
    """ImageDescription 的遮蔽規則：數字留、識別碼遮 —— 這是 nm_per_px 的關鍵。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("probe_tiff_mod", TIFF_PROBE)
    mod = importlib.util.module_from_spec(spec)
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True             # 不要在 fab_probe/ 留下 __pycache__
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = saved
    text = 'LotID AA0000.0X PixelSize=3.25nm Mag=50000 Cam1 SN=AB12345678'
    red = mod.redact_text(text)
    assert "AA0000.0X" not in red and "AB12345678" not in red
    assert "3.25nm" in red and "50000" in red          # 數值一定要保留
    assert "PixelSize" in red and "LotID" in red       # 欄位名保留
    assert mod.redact_text(text, include_ids=True) == text


def test_tiff_redacts_filename(ebi):
    code, out, _ = run_probe(TIFF_PROBE, ebi["tiff"])
    assert code == 0
    assert "LOT_SYN.tif" not in out
    assert "<redacted," in out
    code, out, _ = run_probe(TIFF_PROBE, ebi["tiff"], "--include-ids")
    assert code == 0
    assert "LOT_SYN.tif" in out


# ---------------------------------------------------------------- probe_stats

def _ascii_grid_lines(out):
    """取出第 5 段的 4x4 ASCII 方格。"""
    lines = out.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if "ASCII" in ln and "字元梯度" in ln:
            start = i + 1
            break
    assert start is not None, "報告裡找不到 4x4 ASCII 方格"
    return [ln.strip() for ln in lines[start:start + 4]]


def test_stats_histogram_and_grid(ebi):
    code, out, err = run_probe(STATS_PROBE, ebi["tiff"], "--pages", "4", "--bins", "16")
    assert code == 0, err
    s = parse_summary(out)
    assert s["decoded_pages"] == 4
    assert len(s["sampled_pages"]) == 4
    assert s["bits"] == 8 and s["bins"] == 16
    assert len(s["histogram"]) == 16
    # 直方圖各格加總 == 取樣像素數 == 4 頁 x 128 x 128
    assert sum(s["histogram"]) == s["sampled_pixels"] == 4 * 128 * 128
    assert 0 <= s["min"] <= s["max"] <= 255
    assert len(s["page_means"]) == 4 and len(s["page_stds"]) == 4
    assert len(s["grid4x4"]) == 16
    grid = _ascii_grid_lines(out)
    assert len(grid) == 4, grid
    for row in grid:
        assert len(row) == 4, row
        assert all(ch in ".:-=+*#@" for ch in row), row
    assert "只有這一支會實際讀取影像的像素值" in out


def test_stats_bins_option(ebi):
    code, out, err = run_probe(STATS_PROBE, ebi["tiff"], "--pages", "2", "--bins", "8")
    assert code == 0, err
    s = parse_summary(out)
    assert len(s["histogram"]) == 8
    assert sum(s["histogram"]) == s["sampled_pixels"] == 2 * 128 * 128


def test_stats_on_png_reports_not_tiff(rsem):
    """RSEM 是每顆 defect 一個 PNG —— 要說清楚不是 TIFF，而不是爆掉。"""
    png = rsem["images"][0]
    code, out, err = run_probe(STATS_PROBE, png)
    assert code != 0
    assert "Traceback" not in err and "Traceback" not in out
    assert "不是 TIFF" in err
    assert "PNG" in err


# ------------------------------------------------- 通用：好輸入 0、壞輸入非 0

def test_all_probes_exit_zero_on_good_input(ebi):
    for script, args in ((KLARF_PROBE, [ebi["klarf"]]),
                         (TIFF_PROBE, [ebi["tiff"]]),
                         (STATS_PROBE, [ebi["tiff"]])):
        code, out, err = run_probe(script, *args)
        assert code == 0, "%s 失敗：%s" % (os.path.basename(script), err)
        parse_summary(out)                    # 三支都要有可回報的 JSON 區塊


@pytest.mark.parametrize("script", ALL_PROBES)
def test_probe_missing_file(script, tmp_path):
    missing = tmp_path / "nope.dat"
    code, out, err = run_probe(script, missing)
    assert code != 0
    assert "Traceback" not in err
    assert "找不到檔案" in err


@pytest.mark.parametrize("script", ALL_PROBES)
def test_probe_garbage_file(script, tmp_path):
    junk = tmp_path / "junk.dat"
    junk.write_bytes(b"this is not a klarf nor a tiff\n" * 4)
    code, out, err = run_probe(script, junk)
    assert code != 0
    assert "Traceback" not in err
    assert err.startswith("錯誤：")
    assert len(err.strip()) > 10          # 有一句看得懂的說明


@pytest.mark.parametrize("script", ALL_PROBES)
def test_probe_empty_file(script, tmp_path):
    empty = tmp_path / "empty.dat"
    empty.write_bytes(b"")
    code, out, err = run_probe(script, empty)
    assert code != 0
    assert "Traceback" not in err


# ------------------------------------------------- 單檔、純標準函式庫

FORBIDDEN = {"numpy", "cv2", "tifffile", "d4t", "PySide6", "scipy", "PIL"}


@pytest.mark.parametrize("script", ALL_PROBES)
def test_probe_is_stdlib_only(script):
    tree = ast.parse(open(script, encoding="utf-8").read(), filename=script)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:                     # 相對 import = 依賴同專案檔案
                pytest.fail("%s 用了相對 import，違反『單檔』原則"
                            % os.path.basename(script))
            if node.module:
                imported.add(node.module.split(".")[0])
    leaked = imported & FORBIDDEN
    assert not leaked, "%s 匯入了非標準函式庫：%s" % (os.path.basename(script), leaked)
    assert imported <= {"argparse", "array", "json", "math", "os", "re",
                        "struct", "sys"}, imported


@pytest.mark.parametrize("script", ALL_PROBES)
def test_probe_is_python36_parsable(script):
    """廠內機器可能是舊 Python：語法要在 3.6 就能 parse。"""
    src = open(script, encoding="utf-8").read()
    ast.parse(src, filename=script, feature_version=(3, 6))


def test_readme_lists_all_three_probes():
    readme = open(os.path.join(PROBE_DIR, "README.md"), encoding="utf-8").read()
    for name in ("probe_klarf.py", "probe_tiff.py", "probe_stats.py"):
        assert name in readme
    for phrase in ("假設 #1", "假設 #2", "假設 #3", "--include-ids"):
        assert phrase in readme
