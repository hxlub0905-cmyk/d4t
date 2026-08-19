#!/usr/bin/env python3
# d4t 檔案比對 — authored 2026-07-30.
"""比對這台機器上的程式碼跟 ``tools/FILELIST.txt``，列出**要重新複製哪幾個檔案**。

為什麼需要這支
--------------
公司機的情況（見 `docs/NO-GIT-SETUP.md` §「兩台機器」）：不能用 git、不能下載
任何東西，但**看得到 GitHub 上的檔案並且可以複製**。所以更新程式碼的動作是
「在瀏覽器上開檔案 → 按複製鈕 → 貼進本機的檔案」——
而問題是 176 個檔案裡**哪幾個變了**。

答案在 `tools/FILELIST.txt`：它是全部檔案的 git blob SHA。那一個檔案只有 12 KB，
複製它幾秒鐘。複製完跑這支，它會告訴你剩下要複製哪幾個。

    python tools/check_files.py

所以更新一次的成本是「一次小複製 + 幾次針對性的複製」，而不是重跑整個
六批的搬運流程。

它**不連網路**（公司機連不出去），只比對磁碟上的東西。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from typing import Dict, List, Tuple

MANIFEST = os.path.join("tools", "FILELIST.txt")
RAW = "https://github.com/hxlub0905-cmyk/ADEPT/blob/main/%s"


def blob_sha(data: bytes) -> str:
    """git 算 blob SHA 的方式：``"blob <長度>\\0" + 內容``。"""
    h = hashlib.sha1()                                # noqa: S324 — git 的格式
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def read_manifest(path: str) -> Dict[str, str]:
    want: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                sha, _, rel = line.partition(" ")
                if rel:
                    want[rel] = sha
    return want


def compare(root: str, want: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """回傳 (缺的, 內容不一樣的)。"""
    missing, stale = [], []
    for rel, sha in sorted(want.items()):
        full = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(full):
            missing.append(rel)
            continue
        with open(full, "rb") as f:
            if blob_sha(f.read()) != sha:
                stale.append(rel)
    return missing, stale


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Which files differ from tools/FILELIST.txt")
    ap.add_argument("--root", default=".", help="程式碼在哪個資料夾（預設目前目錄）")
    ap.add_argument("--urls", action="store_true",
                    help="連 GitHub 上的網址一起印出來（貼到瀏覽器就能複製）")
    a = ap.parse_args(argv)

    root = os.path.abspath(a.root)
    path = os.path.join(root, MANIFEST)
    if not os.path.isfile(path):
        print("✗ 找不到 %s" % path)
        print("  先從 GitHub 複製那一個檔案過來（只有 12 KB）——")
        print("  它是「哪些檔案變了」的唯一依據：")
        print("    %s" % (RAW % "tools/FILELIST.txt"))
        return 2

    want = read_manifest(path)
    if not want:
        print("✗ %s 是空的（複製的時候被截斷了？）" % MANIFEST)
        return 2

    missing, stale = compare(root, want)
    print("清單裡有 %d 個檔案。" % len(want))
    print("缺少      : %d" % len(missing))
    print("內容不一樣: %d" % len(stale))

    if not missing and not stale:
        print("")
        print("✓ 這一份跟清單完全一致。")
        print("")
        print("注意：清單自己也可能是舊的 —— 它只證明「你的檔案跟你手上這份清單"
              "一致」。要確認是最新的，重新複製一次 tools/FILELIST.txt 再跑一遍。")
        return 0

    todo = [("缺少", missing), ("內容不一樣", stale)]
    for label, group in todo:
        if not group:
            continue
        print("")
        print("%s（%d 個）—— 從 GitHub 複製這幾個：" % (label, len(group)))
        for rel in group:
            print("    %s" % rel)
            if a.urls:
                print("        %s" % (RAW % rel))
    print("")
    print("複製的方式：在瀏覽器打開那個檔案 → 按右上角的複製鈕 → 貼進本機的同名"
          "檔案。複製完再跑一次這支確認。")
    # 有東西要處理就回非零 —— 這樣包在批次檔裡也看得出結果。
    return 1


if __name__ == "__main__":
    sys.exit(main())
