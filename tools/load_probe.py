#!/usr/bin/env python3
# d4t 載入健檢 — authored 2026-08-20（使用者回報「幾萬顆會超級無敵久或直接不載入」）.
"""量一份真實 lot 的**載入時間花在哪一段**，印出可以安心貼出來的報告。

為什麼需要這支
--------------
家用機的合成資料上，2 萬顆 / 4 萬頁載入只要 0.5 秒 —— 所以「超級無敵久」的
原因**不在家用機看得到的地方**。可能是網路碟（每一次 seek 都是一次來回）、
可能是頁數、可能是 KLARF 的欄數、也可能是某一段的演算法。猜哪一段都是浪費一
趟往返，所以先量。

跟 `check_glas_export.py` 同一條路：**不連網路、不寫任何檔案**，預設**不印任何
廠內識別碼**（lot／wafer／device 名、路徑一律不印，只印結構、大小與秒數）。
要看真名自己加 ``--reveal``（那一份不要貼出來）。

    python tools/load_probe.py D:\\some\\LOT.001
    python tools/load_probe.py D:\\some\\LOT.001 --tiff D:\\other\\patch.tif
    python tools/load_probe.py D:\\some\\LOT.001 --copy   # 順便量「複製到本機
                                                          # 再開」會不會比較快

⚠ ``--copy`` 會把 TIFF 複製到系統暫存資料夾再量一次（結束時刪掉）。
   它回答的是**唯一真正重要的那個問題**：慢的是檔案在哪裡，還是我們的程式。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def _mask(path, reveal):
    """路徑一律不印 —— 只留副檔名（格式）與大小（量級），那才是要看的東西。"""
    if reveal:
        return str(path)
    ext = os.path.splitext(str(path))[1].lower() or "(no extension)"
    return "<%s file>" % ext


def _size(path):
    try:
        n = os.path.getsize(path)
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "?"


class _Timer:
    """每一段的秒數，印成一張表。"""

    def __init__(self):
        self.rows = []

    def run(self, label, fn):
        t0 = time.time()
        try:
            out, err = fn(), None
        except Exception as e:                    # noqa: BLE001 — 報告用
            out, err = None, "%s: %s" % (type(e).__name__, e)
        self.rows.append((label, time.time() - t0, err))
        return out

    @staticmethod
    def _cols(text):
        """終端機上這串字佔幾格 —— 中日韓的字是兩格寬。

        用 `len()` 對齊的話，中文的那幾列會整排歪掉，而這張表是要貼出來給人
        看的（同 `check_glas_export.py` 的報告）。
        """
        wide = sum(1 for ch in text
                   if unicodedata.east_asian_width(ch) in ("W", "F"))
        return len(text) + wide

    def report(self):
        total = sum(dt for _l, dt, _e in self.rows)
        width = max([self._cols(lb) for lb, _d, _e in self.rows] + [10])
        lines = ["", "秒數（總計 %.2f s）" % total, "-" * (width + 22)]
        for label, dt, err in self.rows:
            bar = "#" * min(30, int(round(30 * dt / total))) if total else ""
            pad = " " * max(0, width - self._cols(label))
            lines.append("%s%s %8.3f s  %s%s"
                         % (label, pad, dt, bar,
                            "" if err is None else "  ✗ " + err))
        return "\n".join(lines)


def probe(klarf_path, tiff_path=None, reveal=False, copy=False):
    from d4t.core.ingest import klarf_core, tiff_index

    out = []
    say = out.append
    t = _Timer()

    say("KLARF   : %s  (%s)" % (_mask(klarf_path, reveal), _size(klarf_path)))
    doc = t.run("klarf_core.load", lambda: klarf_core.load(str(klarf_path)))
    if doc is None:
        say("KLARF 讀不起來 —— 下面幾段跳過。")
        say(t.report())
        return "\n".join(out)

    say("          %d 顆 defect · %d 欄" % (len(doc.defects),
                                            len(doc.defect_columns)))
    say("          欄位：%s" % ", ".join(doc.defect_columns))

    tif = str(tiff_path) if tiff_path else doc.tiff_path()
    if not tif or not os.path.isfile(tif):
        say("")
        say("這份 KLARF 沒有對應的 patch TIFF（或找不到），所以沒有 TIFF 那幾段。")
        say(t.report())
        return "\n".join(out)

    say("TIFF    : %s  (%s)" % (_mask(tif, reveal), _size(tif)))
    # **載入已經不做這件事了**（2026-08-20）。留在報告裡是因為它是「這台機器
    # 走完整條 IFD 鏈要多久」的量尺 —— 跑整批仍然會逐頁走過去。
    npages = t.run("數頁數（載入不做，量尺用）",
                   lambda: tiff_index.n_pages(tif))
    say("          %s 頁" % npages)
    depths = t.run("bit_depths（前幾頁）", lambda: tiff_index.bit_depths(tif))
    say("          位元深度（前幾頁）：%s" % depths)
    head = t.run("read_tiff_pages(前 2 頁)",
                 lambda: tiff_index.read_tiff_pages(tif, max_pages=2)[0])
    for p in (head or []):
        say("          第 %d 頁：%sx%s，%s-bit，compression=%s"
            % (p.get("index"), p.get("width"), p.get("height"),
               p.get("bits"), p.get("compression")))
    imap = t.run("doc.defect_image_map",
                 lambda: doc.defect_image_map(npages))
    if imap:
        say("          對應模式：%s（base=%s）" % (imap["mode"], imap["base"]))
        for note in imap["notes"]:
            say("          △ %s" % note)

    def _load():
        from d4t.core.ingest.dataset import load_dataset
        return load_dataset(str(klarf_path), tif)

    ds = t.run("load_dataset（整段）", _load)
    if ds is not None:
        say("")
        say("結果    : kind=%s · %d 顆 · 第一顆 %d 張影像"
            % (ds.kind, len(ds.items), len(ds.items[0].images) if ds.items else 0))
        for w in ds.warnings:
            say("          △ %s" % w)
        if ds.items and ds.items[0].images:
            ch = sorted(ds.items[0].images)[0]
            t.run("讀一顆的影像（第 1 顆）", lambda: ds.items[0].load(ch))
            mid = ds.items[len(ds.items) // 2]
            if mid.images:
                t.run("讀一顆的影像（中間那顆）",
                      lambda: mid.load(sorted(mid.images)[0]))

    if copy:
        say("")
        say("--copy：把 TIFF 複製到本機暫存再量一次 —— 慢的是「檔案在哪裡」還是"
            "「我們的程式」，只有這一段答得出來。")
        tmp = tempfile.mkdtemp(prefix="d4t_probe_")
        try:
            local = os.path.join(tmp, "local" + os.path.splitext(tif)[1])
            t.run("複製到本機", lambda: shutil.copyfile(tif, local))
            t.run("數頁數（本機那份）", lambda: tiff_index.n_pages(local))
            t.run("bit_depths（本機那份）", lambda: tiff_index.bit_depths(local))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    say(t.report())
    say("")
    say("怎麼讀這張表")
    say("  · 某一段吃掉大部分時間 → 那一段就是要改的地方。")
    say("  · 每一段都慢、而 --copy 的本機那份快很多 → 慢的是網路碟，"
        "解法是把索引快取起來／先複製到本機。")
    say("  · 「讀一顆的影像」很慢 → 那不是載入的問題，是每一顆都會付一次的成本"
        "（批次會放大 N 倍）。")
    say("  · 「數頁數」很慢但「load_dataset」很快 → 那是正常的：載入已經不數頁數了"
        "（2026-08-20）。那個數字是「走完整條 IFD 鏈」的量尺 —— 跑整批仍然會"
        "逐頁走過去，只是跟讀像素混在一起攤掉。")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="量一份 lot 的載入時間花在哪一段（輸出預設已遮蔽，可以貼出來）")
    ap.add_argument("klarf", help="KLARF 檔（.001 / .klarf / .txt）")
    ap.add_argument("--tiff", default=None, help="patch TIFF（不填就照 KLARF 猜）")
    ap.add_argument("--copy", action="store_true",
                    help="順便量「複製到本機再開」（回答：慢的是網路碟嗎）")
    ap.add_argument("--reveal", action="store_true",
                    help="印出真實路徑（**這一份不要貼出來**）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.klarf):
        print("找不到這個檔：%s" % args.klarf, file=sys.stderr)
        return 2
    try:
        print(probe(args.klarf, args.tiff, args.reveal, args.copy))
    except ImportError as e:
        print("載入不到 d4t（%s）—— 這支要在裝好 d4t 的那台機器上、"
              "在 repo 根目錄底下跑。" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
