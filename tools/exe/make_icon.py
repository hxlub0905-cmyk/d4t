#!/usr/bin/env python3
# SVG → ICO — authored 2026-10-02 (F125).
"""把 ``d4t/ui/assets/d4t.svg`` 畫成 Windows 的 ``.ico``（給 PyInstaller 的 ``icon=``）。

    python tools/exe/make_icon.py d4t/ui/assets/d4t.svg build/exe/d4t.ico

repo 裡只有 SVG（鐵則：純文字檔），而 Windows 的 exe 圖示要 ``.ico``，所以在打包時
現做。畫圖用 Qt（這台既然要打包就一定有 PySide6），寫檔用 stdlib：

* 16／32／48 px 寫成傳統的 32-bit BMP（DIB）項目 —— 每一版 Windows 與 PyInstaller
  的 icon 解析器都認得；
* 256 px 寫成 PNG 項目（Vista 起的規矩，大圖用 PNG 才不會讓檔案變成 1 MB）。

``build_exe.py`` 用子行程叫這支（``QT_QPA_PLATFORM=offscreen``），失敗只會印一句
「圖示沒做出來」然後用預設圖示 —— 它不該擋打包。
"""
from __future__ import annotations

import struct
import sys
from typing import List, Tuple

SIZES = (16, 32, 48, 256)
PNG_FROM = 256       # 這個尺寸（含）以上用 PNG 項目

#: QGuiApplication 要**抓著不放**：建完沒人參照它就會被回收，下一行畫圖直接 segfault。
_APP = None


def render(svg_path: str, size: int) -> Tuple[bytes, bytes]:
    """回 ``(BGRA 像素，由上而下, PNG 位元組)``。"""
    from PySide6.QtCore import QBuffer, QIODevice, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    global _APP
    if QGuiApplication.instance() is None:
        _APP = QGuiApplication(["make_icon"])
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        raise RuntimeError("cannot read SVG: %s" % svg_path)
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    # ARGB32 在 little-endian 的記憶體裡就是 B,G,R,A —— ICO 的 DIB 要的順序
    raw = bytes(img.constBits())[: size * size * 4]
    # ⚠ 不要寫 ``QBuffer(QByteArray())``：那個暫時的 QByteArray 當場被回收，save 會 segfault。
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return raw, bytes(buf.data())


def dib_entry(bgra_top_down: bytes, size: int) -> bytes:
    """32-bit BGRA 的 ICO 圖像項目：BITMAPINFOHEADER + 由下而上的像素 + AND 遮罩。"""
    row = size * 4
    rows = [bgra_top_down[i * row:(i + 1) * row] for i in range(size)]
    pixels = b"".join(reversed(rows))                 # DIB 是由下而上
    mask_row = ((size + 31) // 32) * 4                # 1 bpp，每列補到 4 bytes
    mask = b"\x00" * (mask_row * size)                # 全 0 = 透明度交給 alpha
    header = struct.pack(
        "<IiiHHIIiiII",
        40, size, size * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def pack_ico(images: List[Tuple[int, bytes]]) -> bytes:
    """``[(size, 圖像位元組)]`` → ICO 檔。圖像位元組是 DIB 項目或整個 PNG。"""
    count = len(images)
    offset = 6 + 16 * count
    directory = [struct.pack("<HHH", 0, 1, count)]
    body = []
    for size, data in images:
        wh = 0 if size >= 256 else size
        directory.append(struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(data), offset))
        body.append(data)
        offset += len(data)
    return b"".join(directory + body)


def build(svg_path: str, out_path: str) -> int:
    images: List[Tuple[int, bytes]] = []
    for size in SIZES:
        raw, png = render(svg_path, size)
        images.append((size, png if size >= PNG_FROM else dib_entry(raw, size)))
    data = pack_ico(images)
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    import os
    os.replace(tmp, out_path)
    return len(data)


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print("usage: make_icon.py IN.svg OUT.ico", file=sys.stderr)
        return 2
    n = build(argv[1], argv[2])
    print("wrote %s (%d bytes, sizes %s)" % (argv[2], n, "/".join(str(s) for s in SIZES)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
