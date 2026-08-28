# F54：把 recipe 裡的模板存成 PNG（2026-08-28）。
"""模板在 recipe 裡是一串 ``gc2:<寬>x<高>:<自週期>:<zlib+base64>`` —— 一張影像
塞進 JSON 的一格。它**打不出來也讀不出來**。

Studio 裡看得到（選起那張卡 →「Edit template & regions…」），但有三種時候
手上只有 JSON：沒有 GUI 的機器、要把模板寄給別人看、兩份 recipe 對照。

⚠ **這支工具只准用標準函式庫** —— 同 `doctor.py`：它要能在「相依套件還沒
裝好」的機器上跑，而 zlib 解壓 ＋ 寫一張灰階 PNG 標準函式庫本來就夠。
下面有一條測試守著這件事。
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import show_template as st  # noqa: E402

np = pytest.importorskip("numpy")


def _cell(w: int = 40, h: int = 12) -> "np.ndarray":
    x = np.arange(w)
    img = (110 + 70 * np.sin(2 * np.pi * x / 7))[None, :] * np.ones((h, 1))
    return img.clip(0, 255).astype(np.uint8)


def _encoded(cell) -> str:
    from d4t.core.algo.template import encode_cell
    return encode_cell(cell)


# --------------------------------------------------------------------------- #
# 1. 解得回原本那張圖
# --------------------------------------------------------------------------- #
def test_it_decodes_what_the_engine_encoded():
    """**用引擎自己的編碼器編，用這支解** —— 兩邊對不上就是這支在說謊。"""
    cell = _cell()
    got = st.decode_template(_encoded(cell))
    assert got is not None
    pixels, w, h, _self = got
    assert (h, w) == cell.shape
    assert pixels == cell.tobytes()


def test_a_broken_string_says_so_instead_of_raising():
    """壞掉的 recipe 不該讓工具炸在使用者臉上（同 core 那一支的契約）。"""
    for bad in ("", "not a template", "gc2:oops", "gc2:5x5:5x5:@@@",
                "gc2:5x5:5x5:" + "eJwB", None):
        assert st.decode_template(bad) is None


def test_a_truncated_blob_is_rejected_not_half_drawn():
    """截斷的 blob → None，**不是半張圖**。半張圖比沒有圖更糟：它看起來是
    一個答案。"""
    full = _encoded(_cell())
    head, blob = full.rsplit(":", 1)
    assert st.decode_template("%s:%s" % (head, blob[:len(blob) // 2])) is None


def test_a_size_that_does_not_match_the_data_is_rejected():
    """**這一條抓的是另一條路，而第一版漏掉了它。**

    上面那條切 base64 —— 那會先炸在 `zlib.decompress`，根本走不到長度檢查。
    於是把「長度不符就補零湊滿」這個突變放進去，那條測試照樣綠（實測過）。

    真正要擋的是：**zlib 解得開，但畫素數量跟宣告的尺寸對不上**（手改過
    的 recipe、或兩份 recipe 貼錯了一半）。那時候補零會畫出一張下半部全黑
    的圖 —— 而使用者會以為那是他的模板。
    """
    cell = _cell(40, 12)                       # 真的資料是 40×12 = 480 px
    blob = _encoded(cell).rsplit(":", 1)[1]
    lying = "gc2:40x20:40x20:%s" % blob        # 但宣告成 40×20 = 800 px
    assert st.decode_template(lying) is None


# --------------------------------------------------------------------------- #
# 2. 掃 recipe 的每一張卡、每一個參數
# --------------------------------------------------------------------------- #
def test_it_finds_templates_without_a_hardcoded_card_list():
    """下一張帶模板的卡不必回來改這支。"""
    tpl = _encoded(_cell())
    rcp = {"nodes": {
        "a": {"step": "roi_reference", "params": {"template": tpl}},
        "b": {"step": "denoise", "params": {"method": "gaussian"}},
        "c": {"step": "whatever_new_card", "params": {"some_other_key": tpl}}}}
    assert [nid for nid, _ in st.templates_in(rcp)] == ["a", "c"]


def test_no_template_is_not_an_error(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"nodes": {}}), encoding="utf-8")
    assert st.main([str(p)]) == 0


# --------------------------------------------------------------------------- #
# 3. 寫出來的真的是一張 PNG
# --------------------------------------------------------------------------- #
def _png_header(path: Path):
    d = path.read_bytes()
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    w, h, depth, colour = struct.unpack(">IIBB", d[16:26])
    return w, h, depth, colour


def test_it_writes_a_valid_grayscale_png(tmp_path):
    cell = _cell()
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"nodes": {"roi": {
        "step": "roi_reference", "params": {"template": _encoded(cell)}}}}),
        encoding="utf-8")
    assert st.main([str(p)]) == 0

    out = tmp_path / "roi_template.png"
    w, h, depth, colour = _png_header(out)
    assert (w, h) == (cell.shape[1], cell.shape[0])
    assert (depth, colour) == (8, 0), "要是 8-bit 灰階"


def test_scale_multiplies_both_sides(tmp_path):
    cell = _cell()
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"nodes": {"roi": {
        "step": "roi_reference", "params": {"template": _encoded(cell)}}}}),
        encoding="utf-8")
    st.main([str(p), "--scale", "3"])
    w, h, _d, _c = _png_header(tmp_path / "roi_template.png")
    assert (w, h) == (cell.shape[1] * 3, cell.shape[0] * 3)


def test_the_pixels_survive_the_round_trip(tmp_path):
    """**每一列前面那個 filter byte 是自己寫 PNG 最常漏的東西**，
    而漏掉的症狀是「圖看起來斜掉了一格」—— 所以逐位元組比一次。"""
    cell = _cell()
    blob = st._png_bytes(cell.tobytes(), cell.shape[1], cell.shape[0])
    idat = b""
    i = 8
    while i < len(blob):
        n = struct.unpack(">I", blob[i:i + 4])[0]
        tag = blob[i + 4:i + 8]
        if tag == b"IDAT":
            idat += blob[i + 8:i + 8 + n]
        i += 12 + n
    raw = zlib.decompress(idat)
    w = cell.shape[1]
    for y in range(cell.shape[0]):
        row = raw[y * (w + 1):(y + 1) * (w + 1)]
        assert row[0] == 0, "第 %d 列少了 filter byte" % y
        assert row[1:] == cell[y].tobytes(), "第 %d 列的畫素不對" % y


# --------------------------------------------------------------------------- #
# 4. 只准用標準函式庫
# --------------------------------------------------------------------------- #
def test_it_runs_without_numpy_or_pillow(tmp_path):
    """**在相依套件還沒裝好的機器上也要能跑**（同 `doctor.py`）。

    做法是真的開一個子行程，把 numpy / PIL / cv2 / d4t 全部擋掉再跑一次。
    """
    cell = _cell()
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"nodes": {"roi": {
        "step": "roi_reference", "params": {"template": _encoded(cell)}}}}),
        encoding="utf-8")

    blocker = (
        "import sys\n"
        "class Block:\n"
        "    def find_module(self, name, path=None):\n"
        "        return self if name.split('.')[0] in "
        "('numpy', 'PIL', 'cv2', 'd4t', 'tifffile') else None\n"
        "    def load_module(self, name):\n"
        "        raise ImportError('blocked: ' + name)\n"
        "sys.meta_path.insert(0, Block())\n"
        "sys.argv = ['show_template', %r]\n"
        "import runpy\n"
        "runpy.run_path(%r, run_name='__main__')\n"
        % (str(p), str(REPO / "tools" / "show_template.py")))
    r = subprocess.run([sys.executable, "-c", blocker],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert (tmp_path / "roi_template.png").exists()
