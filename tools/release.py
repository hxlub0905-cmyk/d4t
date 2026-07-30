#!/usr/bin/env python3
# ADEPT 更新搬運檔 — authored 2026-07-30.
"""改完程式碼之後跑這一支：重產**公司機拿得到的那兩樣東西**。

    git add -A && python tools/release.py && git add -A

它做兩件事，順序不能顛倒：

1. ``tools/FILELIST.txt`` —— 全部檔案的 git blob SHA。公司機用它判斷
   「哪幾個檔案要重新複製」（`tools/check_files.py`）。
2. ``bundle/ADEPT_bundle.py`` —— 整個 repo 壓成一個 711 KB 的純文字 `.py`，
   在 GitHub 上按複製鈕就能整包搬進公司機（見 `AGENTS.md` §2）。

**先清單再打包**：包裡面含著那份清單，順序反了就會把舊清單封進新包裡，
而那個包解出來之後 `check_files.py` 會報一堆不存在的差異。

為什麼要有這支而不是叫人記得跑兩行
----------------------------------
兩行本身不難，難的是**忘了跑不會有任何症狀** —— 直到公司機上少一個檔案，
或者 `check_files.py` 說「你的檔案跟清單一致」而那份清單是三天前的。
所以 `tests/test_offline_tools.py` 有一支測試會在這些東西過期時變紅，
而它的錯誤訊息就是上面那一行指令。

``--check`` 只檢查不寫檔（測試用；有東西過期就回非零）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_filelist                      # noqa: E402  （tools/ 裡的同伴）
import make_text_bundle                   # noqa: E402

BUNDLE = os.path.join("bundle", "ADEPT_bundle.py")


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def untracked(root: str) -> List[str]:
    """還沒 ``git add`` 的檔案。

    這是這一整套裡最容易踩的坑，而且**踩到不會有任何症狀**：清單與包都是從
    ``git ls-files`` 產的，所以還沒 add 的新檔案會安靜地不在裡面 ——
    公司機上就少一個檔案，而它是唯一拿得到程式碼的地方。
    """
    out = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root, check=True, stdout=subprocess.PIPE).stdout.decode("utf-8")
    return [p for p in out.split("\n") if p.strip()]


def _bundle_entries(text: str) -> List[Tuple[str, str]]:
    """從一份 bundle 裡取出 ``(sha, 路徑)`` —— 只解壓，不寫任何檔案。

    解壓是 0.04 秒，重新壓縮是 1.3 秒；檢查用解壓就夠，所以 ``--check`` 很便宜。
    """
    import base64
    import lzma

    lines = text.split("\n")
    try:
        start = lines.index(make_text_bundle.SENTINEL) + 1
    except ValueError:
        return []
    data = lines[start:]
    enc = data[0].strip() if data else ""
    data = data[1:]
    if enc == "#ENC lzma+base64":
        blob = "".join(ln[2:] for ln in data if ln.startswith("#B"))
        data = lzma.decompress(base64.b64decode(blob)).decode("utf-8").split("\n")
    out = []
    i = 0
    while i < len(data):
        if data[i].startswith("#F "):
            _, sha, count, path = data[i].split(" ", 3)
            out.append((sha, path))
            i += 1 + int(count)
        else:
            i += 1
    return out


def stale(root: str = "") -> List[str]:
    """哪些搬運檔過期了（空 list = 都是最新的）。"""
    root = root or repo_root()
    problems = []

    want_listing = make_filelist.build_lines(root)
    listing_path = os.path.join(root, make_filelist.MANIFEST.replace("/", os.sep))
    got = []
    if os.path.isfile(listing_path):
        with open(listing_path, "r", encoding="utf-8") as f:
            got = f.read().splitlines()
    if got != want_listing:
        problems.append("tools/FILELIST.txt 跟目前的檔案對不上")

    bundle_path = os.path.join(root, BUNDLE.replace("/", os.sep))
    if not os.path.isfile(bundle_path):
        problems.append("%s 不存在" % BUNDLE)
        return problems
    with open(bundle_path, "r", encoding="utf-8") as f:
        inside = _bundle_entries(f.read())
    want = [(sha, rel) for sha, rel in
            (ln.split(" ", 1) for ln in want_listing if not ln.startswith("#"))]
    # 包裡**也含著那份清單**（`check_files.py` 靠它），所以要一起比
    listing_sha = make_filelist.blob_sha(
        ("\n".join(want_listing) + "\n").encode("utf-8"))
    want.append((listing_sha, make_filelist.MANIFEST))
    if sorted(inside) != sorted(want):
        problems.append("%s 裡的內容跟目前的檔案對不上" % BUNDLE)
    return problems


def write(root: str = "") -> None:
    root = root or repo_root()
    # 1. 先清單（包裡面含著它）
    lines = make_filelist.build_lines(root)
    listing = os.path.join(root, make_filelist.MANIFEST.replace("/", os.sep))
    tmp = listing + ".tmp"                            # atomic（鐵則 5）
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, listing)
    print("tools/FILELIST.txt：%d 個檔案" % (len(lines) - len(make_filelist.HEADER)))

    # 2. 再打包
    bundle = os.path.join(root, BUNDLE.replace("/", os.sep))
    os.makedirs(os.path.dirname(bundle), exist_ok=True)
    text = make_text_bundle.build(os.path.basename(bundle), root, compress=True)
    tmp = bundle + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, bundle)
    n = len(make_text_bundle.collect(root))
    print("%s：%d 個檔案、%.0f KB"
          % (BUNDLE, n, len(text.encode("utf-8")) / 1024))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Regenerate the files the company machine can reach.")
    ap.add_argument("--check", action="store_true",
                    help="只檢查有沒有過期，不寫檔（過期回非零）")
    a = ap.parse_args(argv)
    root = repo_root()

    loose = untracked(root)
    if loose:
        print("⚠ 有 %d 個檔案還沒 git add —— 它們**不會**進清單也不會進包：" % len(loose))
        for p in loose[:8]:
            print("    %s" % p)
        if len(loose) > 8:
            print("    …還有 %d 個" % (len(loose) - 8))
        print("  先 `git add -A` 再跑這支。")
        return 2

    if a.check:
        problems = stale(root)
        if problems:
            print("✗ 搬運檔過期了：")
            for p in problems:
                print("    %s" % p)
            print("")
            print("  跑：git add -A && python tools/release.py && git add -A")
            return 1
        print("✓ tools/FILELIST.txt 與 %s 都是最新的。" % BUNDLE)
        return 0

    write(root)
    print("")
    print("記得 `git add -A` 再 commit —— 這兩個檔案是公司機唯一拿得到程式碼的地方。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
