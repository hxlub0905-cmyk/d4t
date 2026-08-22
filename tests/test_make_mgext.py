"""Tests for tools/make_mgext.py — MG extrusion 合成 lot 產生器（F20 那一批）。

這一支產的資料**不進版控**（`0822test/` 在 .gitignore 裡）—— 2 MB 的 TIFF，
而且隨時重產得出來。所以這份測試鎖住的正是那句話：**同一個種子產出來的東西
逐位元組相同**。它一旦不成立，`docs/plans/F20-pick-defect-box.md` 上那些數字
就沒有人能重跑了。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

from d4t.core.ingest import dataset, klarf_core, tiff_index

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import make_mgext  # noqa: E402


N = 9


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    out = tmp_path_factory.mktemp("mgext")
    return make_mgext.generate(str(out / "lot"), n=N, seed=23, n_clean=3)


def test_klarf_and_tiff_line_up(lot):
    doc = klarf_core.load(lot["klarf"])
    assert doc.version == "1.2"
    assert len(doc.defects) == N
    assert tiff_index.n_pages(lot["tiff"]) == 2 * N        # 每顆 test ＋ ref
    ds = dataset.load_dataset(lot["klarf"])
    assert ds.kind == "ebi_patch" and len(ds.items) == N


def test_the_extrusion_is_a_designed_value_not_a_measured_one(lot):
    """這一組存在的理由：**每一顆都帶著真值**，量測結果才回歸得了。

    `mgepi_real3` 那一組答不出「量得準不準」—— 那顆 Hf 沒有一個叫做凸出量的
    真值可以對。
    """
    truth = json.load(open(lot["ground_truth"], encoding="utf-8"))
    assert len(truth) == N
    real = [v for v in truth.values() if v["is_real"]]
    clean = [v for v in truth.values() if not v["is_real"]]
    assert len(clean) == 3 and len(real) == N - 3

    for v in real:
        assert v["type"] == "mg_extrusion"
        assert v["extrusion_px"] > 0.0
        # nm 是 px × pixel size，而**兩個都寫出來**：名字帶著單位就永遠不必
        # 回頭查「那份資料當初填了沒」（同 `_util.nm_twins` 的理由）。
        assert v["extrusion_nm"] == pytest.approx(
            v["extrusion_px"] * make_mgext.NM_PER_PX, abs=1e-6)
        # 幾何位置：任何量法都要對得回去
        assert v["side"] in ("left", "right")
        span = abs(v["tip_px"] - v["mg_edge_px"])
        assert span == pytest.approx(v["extrusion_px"], abs=1e-6)
    for v in clean:
        assert v["type"] == "none" and v["extrusion_px"] == 0.0


def test_the_lengths_are_spread_evenly(lot):
    """等距取樣而不是亂數：同樣的顆數之下回歸線鋪得比較勻，斜率的信賴區間窄得多。"""
    truth = json.load(open(lot["ground_truth"], encoding="utf-8"))
    got = sorted(v["extrusion_px"] for v in truth.values() if v["is_real"])
    gaps = np.diff(got)
    assert np.allclose(gaps, gaps[0], atol=1e-6)
    assert got[0] == pytest.approx(make_mgext.EXT_RANGE_PX[0])
    assert got[-1] == pytest.approx(make_mgext.EXT_RANGE_PX[1])


def test_same_seed_identical_bytes(tmp_path):
    """**這一條是重點。** 資料不進版控，所以「重產得出來」必須是真的。"""
    a = make_mgext.generate(str(tmp_path / "a"), n=4, seed=5, n_clean=1)
    b = make_mgext.generate(str(tmp_path / "b"), n=4, seed=5, n_clean=1)
    for key in ("tiff", "klarf", "ground_truth"):
        assert open(a[key], "rb").read() == open(b[key], "rb").read(), key


def test_a_different_seed_gives_different_images(tmp_path):
    a = make_mgext.generate(str(tmp_path / "a"), n=4, seed=5, n_clean=1)
    b = make_mgext.generate(str(tmp_path / "b"), n=4, seed=6, n_clean=1)
    assert open(a["tiff"], "rb").read() != open(b["tiff"], "rb").read()


def test_the_defect_sits_where_the_ground_truth_says(lot):
    """test 與 ref 只差凸出物 —— 差影像的熱點就該落在記下來的那個位置上。

    這一條同時擋住兩種錯：凸出物畫在別的地方，以及 ground truth 記錯。
    """
    import tifffile

    pages = np.stack([p.asarray() for p in
                      tifffile.TiffFile(lot["tiff"]).pages]).astype(float)
    truth = json.load(open(lot["ground_truth"], encoding="utf-8"))
    checked = 0
    for key, v in truth.items():
        if not v["is_real"] or v["extrusion_px"] < 4.0:
            continue                       # 太小的凸出物本來就淹在雜訊裡
        i = int(key) - 1
        diff = pages[2 * i] - pages[2 * i + 1]
        y, x = np.unravel_index(int(np.argmax(diff)), diff.shape)
        assert abs(y - v["row_px"]) <= 4.0, key
        lo, hi = sorted((v["mg_edge_px"], v["tip_px"]))
        assert lo - 2.0 <= x <= hi + 2.0, key
        checked += 1
    assert checked >= 2


def test_cli_main(tmp_path, capsys):
    make_mgext.main([str(tmp_path / "lot"), "--n", "4", "--clean", "1",
                     "--seed", "23"])
    out = capsys.readouterr().out
    assert "ok:" in out and "extrusion" in out
    assert os.path.exists(str(tmp_path / "lot" / "LOT_SYN.001"))
