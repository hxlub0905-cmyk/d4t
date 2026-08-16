#!/usr/bin/env python3
# ADEPT 更新搬運檔 — authored 2026-07-30.
"""**在家用機上**改完程式碼之後跑這一支：重產公司機拿得到的那兩樣東西。

    git add -A && python tools/release.py && git add -A

⚠ **這支是給有 git 的那台機器（家用機）用的。** 公司機不能執行 git 操作，
也不需要跑這支 —— 它只負責「拿到程式碼並執行」，見 `AGENTS.md` §2。

它做兩件事，順序不能顛倒：

1. ``tools/FILELIST.txt`` —— 全部檔案的 git blob SHA。公司機用它判斷
   「哪幾個檔案要重新複製」（`tools/check_files.py`）。
2. ``bundle/ADEPT_bundle.py`` —— 整個 repo 壓成一個純文字 `.py`，
   在 GitHub 上按複製鈕就能整包搬進公司機（見 `AGENTS.md` §2）。
   **它必須小於 1 MB**，否則公司機在網頁上點不開；每次產完都會報目前的水位
   （見 :func:`bundle_size_report`）。

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

#: GitHub 網頁**不顯示**超過 1 MB 的檔案。
#:
#: 這不是一個效能數字，是一堵牆：公司機下載不了東西，唯一的傳輸通道是「在
#: GitHub 上打開檔案、按右上角的複製鈕」（`AGENTS.md` §2）。包一旦超過這條線，
#: 那台機器上就**點不開來複製** —— 而這個包存在的唯一理由就是繞過這件事。
BUNDLE_LIMIT_BYTES = 1024 * 1024

#: 開始出聲的水位（85%）。
#:
#: 為什麼要提早喊：破線**沒有任何症狀**。測試不會紅、release.py 不會錯、
#: 家用機上一切正常 —— 症狀只會出現在公司機的瀏覽器裡，而那時候人已經站在
#: 機台旁邊了。2026-08-16 實測 962 KB（94%），只剩 ~60 KB 餘裕；壓縮比約
#: 3.2:1，換算成純文字大約再加 200 KB 就會撞牆。
BUNDLE_WARN_RATIO = 0.85


def bundle_size_report(nbytes: int) -> Tuple[str, str]:
    """包的大小 → ``(等級, 要印的話)``；等級是 ``ok`` / ``warn`` / ``over``。

    切開成純函式是為了測得到 —— 產一個 1 MB 的包只為了驗這段訊息太貴。
    """
    pct = 100.0 * nbytes / BUNDLE_LIMIT_BYTES
    size = "%.0f KB（GitHub 1 MB 上限的 %.0f%%）" % (nbytes / 1024.0, pct)
    if nbytes > BUNDLE_LIMIT_BYTES:
        return "over", (
            "✗ %s —— **超過上限了**。公司機在 GitHub 網頁上點不開這個檔案，\n"
            "    也就複製不走，整條搬運通道斷掉（AGENTS.md §2）。\n"
            "    先把不需要進包的大檔搬進 docs/history/（那個目錄不打包），\n"
            "    或用 make_text_bundle.py --split 分批。" % size)
    if nbytes > BUNDLE_LIMIT_BYTES * BUNDLE_WARN_RATIO:
        return "warn", (
            "⚠ %s —— 快撞牆了。破線之後**在家用機上沒有任何症狀**，\n"
            "    只有公司機的瀏覽器會打不開。現在就該把長期只增不減的文件\n"
            "    （SESSION_LOG、做完的計畫書）搬進 docs/history/。" % size)
    return "ok", "  %s" % size


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def has_git(root: str) -> bool:
    """這台機器跑得動 git 嗎。

    公司機不能執行 git 操作，而這支的每一件事都建立在 ``git ls-files`` 上 ——
    在那台機器上跑會丟一個看不懂的 subprocess 例外。與其那樣，不如直接講出
    「你跑錯機器了」以及那台機器該做什麼。
    """
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root,
                       check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


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
    nbytes = len(text.encode("utf-8"))
    print("%s：%d 個檔案、%.0f KB" % (BUNDLE, n, nbytes / 1024))
    print(bundle_size_report(nbytes)[1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Regenerate the files the company machine can reach.")
    ap.add_argument("--check", action="store_true",
                    help="只檢查有沒有過期，不寫檔（過期回非零）")
    a = ap.parse_args(argv)
    root = repo_root()

    if not has_git(root):
        print("✗ 這台機器上沒有 git（或這不是一個 git work tree）。")
        print("")
        print("  這支是**給家用機用的** —— 它重產「公司機拿得到程式碼」所需的兩個檔案，")
        print("  而那件事需要 git。公司機不需要跑它。")
        print("")
        print("  在公司機上你要的大概是這兩支之一：")
        print("    python tools/check_files.py    # 哪幾個檔案跟 GitHub 上不一樣")
        print("    python tools/doctor.py         # 環境自檢")
        return 2

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
        # 大小是**跟過期無關**的另一條線：包可以既是最新的、又大到送不進去。
        bundle_path = os.path.join(root, BUNDLE.replace("/", os.sep))
        level, msg = bundle_size_report(os.path.getsize(bundle_path))
        print(msg)
        return 1 if level == "over" else 0

    write(root)
    print("")
    print("記得 `git add -A` 再 commit —— 這兩個檔案是公司機唯一拿得到程式碼的地方。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
