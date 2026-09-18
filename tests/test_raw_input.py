# F113 驗收：headerless `.raw` 影像。
"""**`.raw` 裡沒有任何一個 byte 在講寬、高或位元深度。**

所以這條路要的東西比別的格式多，而那不是設計上的疏忽 —— 那些數字只有使用者
知道（或者從檔案大小推得出來）。

⚠ **猜錯的代價是每一個像素都錯，而且不會報錯**：寬度差一格，整張圖變成一條
斜線；位元深度猜錯，亮度差 16 倍或 256 倍。所以這一份守的兩件事都是「不准安靜
地硬套」：對不上就當場報錯，降位的位移整批共用而且講出來。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.ingest.dataset import load_folder, load_raw_folder  # noqa: E402
from d4t.core.ingest.rawfile import (  # noqa: E402
    RAW_EXTS, RawSpec, guess_layouts, read_raw, suggest_shift,
)

W = H = 64
HEADER = 1024


def _write(path, arr, header=HEADER):
    with open(path, "wb") as f:
        f.write(b"\x00" * header)
        f.write(np.asarray(arr).tobytes())
    return str(path)


def _lot(tmp_path, n=3, top=4095, header=HEADER, seed=0):
    rng = np.random.default_rng(seed)
    for i in range(n):
        a = rng.integers(0, top + 1, (H, W)).astype("<u2")
        a[0, 0] = top                      # 讓最大值可預測
        _write(tmp_path / ("shot%d.raw" % i), a, header)
    return str(tmp_path)


# --------------------------------------------------------------------------- #
# 1. 從檔案大小推版面
# --------------------------------------------------------------------------- #
def test_the_users_file_size_has_exactly_one_square_answer():
    """使用者機台的實際數字（2026-09-18）：25,755,648 bytes。

    只有一組正方形解 —— 64 KiB 檔頭 ＋ 16-bit ＋ 3584×3584。**唯一**這件事就是
    那個建議值得相信的理由；有兩組的時候這支測試會告訴下一個人要去問。
    """
    got = guess_layouts(25_755_648)
    assert len(got) == 1, [s.describe() for s in got]
    s = got[0]
    assert (s.width, s.height, s.bits, s.header) == (3584, 3584, 16, 65536)
    assert s.nbytes() == 25_755_648


def test_a_size_that_fits_nothing_says_nothing_instead_of_guessing():
    """**推不出來就回空的**，不要挑一個「最像的」。"""
    assert guess_layouts(3) == []
    assert guess_layouts(0) == []


def test_only_square_answers_are_offered():
    """非正方形有無限多組解（任何一組因數都行），列出來只會讓人在數字裡挑。"""
    for s in guess_layouts(1024 + W * H * 2):
        assert s.width == s.height


# --------------------------------------------------------------------------- #
# 2. 讀：對不上就報錯，不讀成一張斜掉的圖
# --------------------------------------------------------------------------- #
def test_a_wrong_layout_is_an_error_not_a_skewed_picture(tmp_path):
    """**這是這一份最重要的一條。** 寬度差一格，`np.fromfile` 照樣讀得出東西
    —— 而那張圖是斜的，不是一個錯誤訊息。"""
    p = _write(tmp_path / "a.raw", np.zeros((H, W), "<u2"))
    good = RawSpec(width=W, height=H, header=HEADER, bits=16)
    read_raw(p, good)                                  # 前提：對的那組讀得動
    for bad in (RawSpec(width=W + 1, height=H, header=HEADER, bits=16),
                RawSpec(width=W, height=H, header=0, bits=16),
                RawSpec(width=W, height=H, header=HEADER, bits=8)):
        with pytest.raises(IOError) as e:
            read_raw(p, bad)
        assert "bytes" in str(e.value) and "skewed" in str(e.value)


def test_the_pixels_come_back_exactly(tmp_path):
    """16-bit 原樣（``shift=None``）時**一個位元都不准動**。"""
    src = np.arange(W * H, dtype="<u2").reshape(H, W) % 4096
    p = _write(tmp_path / "a.raw", src)
    got = read_raw(p, RawSpec(width=W, height=H, header=HEADER, bits=16))
    assert got.dtype == np.dtype("<u2")
    assert np.array_equal(got, src)


def test_the_header_is_really_skipped(tmp_path):
    """檔頭沒跳過的話，整張圖會**平移** —— 而那是看得出來但說不清楚的錯。"""
    src = np.full((H, W), 1000, "<u2")
    with open(tmp_path / "a.raw", "wb") as f:
        f.write(b"\xff" * HEADER)          # 檔頭刻意是最大值
        f.write(src.tobytes())
    got = read_raw(str(tmp_path / "a.raw"),
                   RawSpec(width=W, height=H, header=HEADER, bits=16))
    assert np.array_equal(got, src), "檔頭的 0xFF 漏進畫面了"


# --------------------------------------------------------------------------- #
# 3. 16-bit → 8-bit：整批同一個位移
# --------------------------------------------------------------------------- #
def test_the_shift_comes_from_what_the_data_actually_uses():
    """12-in-16 與滿量程 16-bit **在檔案裡長得一模一樣** —— 唯一分得出來的
    線索是像素值真的到了哪裡（`require_8bit` 的說明就是在講這件事）。"""
    assert suggest_shift(np.array([4095], "<u2")) == 4      # 12 bit → >>4
    assert suggest_shift(np.array([65535], "<u2")) == 8     # 16 bit → >>8
    assert suggest_shift(np.array([255], "<u2")) == 0       # 本來就進得去
    assert suggest_shift(np.array([0], "<u2")) == 0
    assert suggest_shift(np.array([200], "u1"), bits=8) == 0


def test_every_image_in_the_folder_gets_the_same_shift(tmp_path):
    """**逐張量會讓兩張圖不再可比**，而「比」是這個工具的全部。

    這正是 `imageio.load_gray` 對非 8-bit 做錯的那件事（每張各自 MINMAX 拉伸
    → 亮度砍半的圖載進來平均值一模一樣）。所以位移在載入的當下決定**一次**。
    """
    rng = np.random.default_rng(4)
    bright = rng.integers(3000, 4096, (H, W)).astype("<u2")
    dim = (bright // 8).astype("<u2")      # 暗很多的第二張
    _write(tmp_path / "a_bright.raw", bright)
    _write(tmp_path / "b_dim.raw", dim)

    ds = load_raw_folder(str(tmp_path),
                         RawSpec(width=W, height=H, header=HEADER, bits=16))
    specs = [i.images["single"].raw for i in ds.items]
    assert len({s.shift for s in specs}) == 1, "整批要共用同一個位移"
    a = ds.items[0].load("single").astype(float)
    b = ds.items[1].load("single").astype(float)
    assert a.mean() > 3 * b.mean(), (
        "亮的那張載進來要還是比較亮（%.1f vs %.1f）—— 一樣亮就是各自拉伸了"
        % (a.mean(), b.mean()))


def test_what_it_decided_is_said_out_loud(tmp_path):
    """**決定了什麼要講出來**（同 `require_8bit` 的原則：不准安靜地硬套）。"""
    ds = load_raw_folder(_lot(tmp_path),
                         RawSpec(width=W, height=H, header=HEADER, bits=16))
    said = " ".join(ds.warnings)
    assert "shifted down by" in said and "comparable" in said
    assert "%d x %d" % (W, H) in said


def test_it_comes_out_as_an_ordinary_folder_lot(tmp_path):
    """⚠ **kind 是 `folder`，不是第六種。** `.raw` 跟 PNG 的差別只在「怎麼把
    byte 變成像素」，而那件事 ingest 就做完了 —— 一顆一張、沒有 KLARF、寫不回
    KLARF，形狀跟 `folder` 一模一樣。多一種 kind 等於把同樣的答案抄第二份。"""
    ds = load_raw_folder(_lot(tmp_path, n=3),
                         RawSpec(width=W, height=H, header=HEADER, bits=16))
    assert ds.kind == "folder" and ds.klarf is None
    assert [i.defect_id for i in ds.items] == ["shot0", "shot1", "shot2"]
    assert ds.items[0].load("single").dtype == np.uint8


# --------------------------------------------------------------------------- #
# 4. 走錯入口要講得出正確的那一個
# --------------------------------------------------------------------------- #
def test_a_folder_with_no_raw_says_which_entry_to_use(tmp_path):
    (tmp_path / "x.txt").write_text("not an image", encoding="utf-8")
    ds = load_raw_folder(str(tmp_path), RawSpec(width=W, height=H))
    assert ds.items == []
    assert any("Open folder" in w for w in ds.warnings), ds.warnings


def test_the_plain_folder_entry_still_ignores_raw(tmp_path):
    """`.raw` **不進 `_IMAGE_EXTS`** —— 進去的話 `Open folder…` 會撿到它，
    然後 `cv2.imdecode` 解不開，而使用者看到的是一句「你的圖壞了」。"""
    _write(tmp_path / "a.raw", np.zeros((H, W), "<u2"))
    ds = load_folder(str(tmp_path))
    assert ds.items == []
    assert RAW_EXTS == (".raw",)


def test_a_missing_directory_does_not_raise(tmp_path):
    ds = load_raw_folder(str(tmp_path / "nope"), RawSpec(width=W, height=H))
    assert ds.kind == "folder" and ds.items == [] and ds.warnings


# --------------------------------------------------------------------------- #
# 5. CLI
# --------------------------------------------------------------------------- #
def test_the_cli_takes_the_layout_on_the_command_line(tmp_path):
    from d4t.__main__ import _open_input, _parse_raw_layout

    s = _parse_raw_layout("3584x3584+65536@16")
    assert (s.width, s.height, s.header, s.bits) == (3584, 3584, 65536, 16)
    assert _parse_raw_layout("64x32").header == 0
    assert _parse_raw_layout("64x32").bits == 16, "省略時是 16-bit"

    ds = _open_input(_lot(tmp_path), None, "%dx%d+%d@16" % (W, H, HEADER))
    assert ds.kind == "folder" and len(ds.items) == 3


def test_the_cli_refuses_to_guess_when_the_size_is_ambiguous(tmp_path):
    """**CLI 問不了問題，所以它要嘛推得出唯一解、要嘛停下來把候選列出來。**
    挑一個「最像的」跑下去，使用者會拿到一批安靜算錯的數字。"""
    from d4t.__main__ import _open_input

    _lot(tmp_path, n=1, header=0)          # 0 檔頭 → 好幾種版面都說得通
    with pytest.raises(SystemExit) as e:
        _open_input(str(tmp_path), None, None)
    assert "--raw" in str(e.value)
