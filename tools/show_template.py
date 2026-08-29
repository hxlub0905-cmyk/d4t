#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# d4t offline tool — authored 2026-08-28 (F54).
"""把 recipe 裡的模板影像存成 PNG —— **看得到它長什麼樣**。

用法::

    python tools/show_template.py my_recipe.json
    python tools/show_template.py my_recipe.json --out /tmp/tpl
    python tools/show_template.py my_recipe.json --scale 4   # 放大 4 倍再存

模板（Golden Cell 的那一張 cell）在 recipe 裡是一串
``gc2:<寬>x<高>:<自週期>:<zlib+base64>`` —— 一張影像塞進 JSON 的一格。
它**打不出來也讀不出來**：`roi_template` 的錯誤訊息就寫著「a template is an
image, it cannot be typed in」。

為什麼需要這支
--------------
Studio 裡本來就看得到（選起那張卡 →「Edit template & regions…」），
但有三種時候你手上只有 JSON：

* 在**沒有 GUI 的機器**上檢查一份 recipe（公司機、CI、遠端）；
* 把模板寄給別人看、貼進報告、附在問題單上；
* 兩份 recipe 對照「它們的模板是不是同一張」。

⚠ **只用標準函式庫。** 不 import numpy、不 import PIL、也不 import d4t ——
理由跟 `doctor.py` 一樣：這支要能在「相依套件還沒裝好」的機器上跑，而它做的
事（zlib 解壓 ＋ 寫一個灰階 PNG）標準函式庫本來就夠。PNG 的編碼在
:func:`_png_bytes`，二十行。

⚠ **模板可能是廠內圖案。** 存出來的 PNG 跟原始影像一樣敏感 ——
別把它 commit 進 repo（`CLAUDE.md` 鐵則 8）。這支預設存到**recipe 旁邊**，
不是專案資料夾裡。
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import struct
import sys
import zlib
from typing import Dict, List, Optional, Tuple

__all__ = ["decode_template", "write_png", "templates_in"]


# --------------------------------------------------------------------------- #
# 解模板字串
# --------------------------------------------------------------------------- #
def decode_template(text: str) -> Optional[Tuple[bytes, int, int, Tuple[int, int]]]:
    """``"gc2:WxH:SxS:<blob>"`` → ``(畫素, 寬, 高, 自週期)``；壞了回 ``None``。

    **絕不 raise** —— 同 `d4t.core.algo.template.decode_template` 的契約：
    一份壞掉的 recipe 不該讓這支工具炸在使用者臉上，它該講一句話。

    ``gc1``（舊的、沒有自週期）也讀得動，那時候自週期視同整張。
    """
    s = str(text or "").strip()
    if not s:
        return None
    parts = s.split(":")
    tag = parts[0] if parts else ""
    if tag == "gc1" and len(parts) == 3:
        size, self_size, blob = parts[1], None, parts[2]
    elif tag == "gc2" and len(parts) == 4:
        size, self_size, blob = parts[1], parts[2], parts[3]
    else:
        return None
    try:
        w, h = (int(v) for v in size.split("x"))
        raw = zlib.decompress(base64.b64decode(blob.encode("ascii")))
    except (ValueError, binascii.Error, zlib.error):
        return None
    if w < 1 or h < 1 or len(raw) != w * h:
        return None
    if self_size is None:
        return raw, w, h, (w, h)
    try:
        sx, sy = (int(v) for v in self_size.split("x"))
    except ValueError:
        return raw, w, h, (w, h)
    if not (1 <= sx <= w and 1 <= sy <= h):
        return raw, w, h, (w, h)
    return raw, w, h, (sx, sy)


def templates_in(recipe: Dict) -> List[Tuple[str, str]]:
    """一份 recipe 裡每一個模板 → ``[(節點 id, 模板字串), …]``。

    掃的是**每一張卡的每一個參數**，不是一份寫死的「哪張卡有模板」清單 ——
    下一張帶模板的卡不必回來改這裡（同引擎那邊問卡片宣告的做法）。
    """
    out: List[Tuple[str, str]] = []
    nodes = (recipe or {}).get("nodes") or {}
    for nid in sorted(nodes):
        params = (nodes[nid] or {}).get("params") or {}
        for key in sorted(params):
            val = params[key]
            if isinstance(val, str) and val[:4] in ("gc1:", "gc2:"):
                out.append((str(nid), val))
    return out


# --------------------------------------------------------------------------- #
# 寫 PNG（標準函式庫）
# --------------------------------------------------------------------------- #
def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _png_bytes(pixels: bytes, w: int, h: int, scale: int = 1) -> bytes:
    """8-bit 灰階 → PNG。

    PNG 的每一列前面要一個 filter byte（0 = 不濾波）—— 漏掉它是自己寫 PNG
    最常見的錯，而症狀是「圖看起來斜掉了一格」。
    """
    scale = max(1, int(scale))
    rows = []
    for y in range(h):
        line = pixels[y * w:(y + 1) * w]
        if scale > 1:
            line = bytes(b for px in line for _ in range(scale) for b in (px,))
        for _ in range(scale):
            rows.append(b"\x00" + line)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale,
                                          8, 0, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
            + _chunk(b"IEND", b""))


def write_png(path: str, pixels: bytes, w: int, h: int, scale: int = 1) -> str:
    """寫檔（atomic —— `CLAUDE.md` 鐵則 5）。回傳寫到哪。"""
    blob = _png_bytes(pixels, w, h, scale)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)
    return path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _describe(pixels: bytes, w: int, h: int, self_period: Tuple[int, int]) -> str:
    lo, hi = min(pixels), max(pixels)
    mean = sum(pixels) / float(len(pixels))
    sx, sy = self_period
    note = ("整張就是一個單元（沒找到更小的重複）"
            if (sx, sy) == (w, h) else "自己重複的單元 %d×%d" % (sx, sy))
    return ("%d×%d 灰階 · 灰階範圍 %d–%d · 平均 %.1f · %s"
            % (w, h, lo, hi, mean, note))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="把 recipe 裡的模板影像存成 PNG（只用標準函式庫）")
    ap.add_argument("recipe", help="recipe JSON 的路徑")
    ap.add_argument("--out", default="",
                    help="存到哪個資料夾（預設：recipe 檔旁邊）")
    ap.add_argument("--scale", type=int, default=1,
                    help="放大幾倍再存（模板通常很小，4 比較看得清楚）")
    args = ap.parse_args(argv)

    try:
        with open(args.recipe, encoding="utf-8") as f:
            recipe = json.load(f)
    except (OSError, ValueError) as e:
        print("讀不到 recipe：%s" % e)
        return 1

    found = templates_in(recipe)
    if not found:
        print("這份 recipe 裡沒有模板（沒有任何 gc1:/gc2: 開頭的參數）。")
        return 0

    out_dir = args.out or os.path.dirname(os.path.abspath(args.recipe))
    written = 0
    for nid, text in found:
        got = decode_template(text)
        if got is None:
            print("✗ %-18s 模板字串解不開（格式不對，或內容被截斷）" % nid)
            continue
        pixels, w, h, self_period = got
        path = os.path.join(out_dir, "%s_template.png" % nid)
        write_png(path, pixels, w, h, args.scale)
        print("✓ %-18s %s" % (nid, _describe(pixels, w, h, self_period)))
        print("  → %s%s" % (path, "（放大 %d×）" % args.scale
                            if args.scale > 1 else ""))
        written += 1

    if written:
        print("\n⚠ 模板可能是廠內圖案 —— 這幾個 PNG 跟原始影像一樣敏感，"
              "不要 commit 進 repo。")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
