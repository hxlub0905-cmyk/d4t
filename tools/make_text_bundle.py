#!/usr/bin/env python3
# d4t 單檔純文字打包 — authored 2026-07-30.
"""把整個 repo 打成**一個純文字 .py 檔**，那個檔案自己解得開。

什麼時候需要這個
----------------
實測遇到的情況：公司政策**擋掉 `.zip` 這個類別**（不只是 GitHub 的
`codeload.github.com`，連從別的來源下載同一包 zip 也擋），而且 proxy 也不讓
Python 逐檔抓。這時候 `tools/get_code.py` / `.ps1` 都用不上，能過的只剩
「一個純文字檔」。

所以這支產出的東西**沒有任何壓縮格式**：檔案內容原封不動地一行一行躺在裡面，
可以用記事本打開讀。也**刻意不用 base64** —— base64 對 DLP 來說是「看不懂的
東西」，而看不懂通常就等於擋掉；而且這個 repo 全部是純文字，本來就不需要編碼。

怎麼用
------
    python tools/make_text_bundle.py            # 產 d4t_bundle.py
    python tools/make_text_bundle.py --out X.py

拿到 `d4t_bundle.py` 的人：

    python d4t_bundle.py                      # 解到 .\\d4t\\
    python d4t_bundle.py --dest D:\\tools
    python d4t_bundle.py --list               # 只列出裡面有什麼，不寫檔

格式為什麼是「行數」而不是「位元組數」
--------------------------------------
這個檔案會經過瀏覽器下載、記事本另存、郵件附件…… 任何一步都可能把 LF 換成
CRLF。用位元組數的話那一換整包就對不起來了，而且錯誤會發生在**第一個檔案之後
的全部檔案**上，看起來像整包壞掉。用行數則對換行符號免疫 —— 解開的時候用
Python 的文字模式讀（它會把 CRLF 讀成 LF），所以來回一趟仍然逐位元組相同。
前提是 repo 裡全部是 LF + UTF-8，這支會在打包前檢查，不合就拒絕產出。

每個檔案仍然帶 **git blob SHA-1**，解開時逐檔驗 —— 傳輸途中被動到的話要當場
講出來，而不是讓使用者拿到一份安靜壞掉的程式碼。

⚠ 這個「bundle」跟 ``output_bundle`` 那張卡**沒有關係**（那是報表資料夾，
畫面上叫 “Write report folder”）。兩個都不改名，理由見 `CLAUDE.md` §0。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import lzma
import os
import subprocess
import sys
from typing import List, Optional, Tuple

#: 資料區的分隔行。解包時找的是**整行剛好等於它**的那一行 —— 而資料區的每一行
#: 都被加了 '#'，所以就算某個檔案的內容裡出現這個字串（``make_text_bundle.py``
#: 自己就在 repo 裡，它的源碼裡當然有），也永遠不會剛好相等。加 '#' 那件事因此
#: 同時解決了兩個問題：整個檔案仍然是合法的 Python，而分隔行不會被誤認。
BUNDLE_DIR = "bundle"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_filelist                       # noqa: E402  （tools/ 裡的同伴）

#: 不進包的目錄 —— **跟 FILELIST 用同一份定義**（`make_filelist.EXCLUDE_DIRS`）。
#: 兩邊分家的下場是：清單說有這個檔案、包裡沒有，於是公司機解完包之後
#: `check_files.py` 永遠報「還缺幾個」而那幾個永遠補不進來。
EXCLUDE_DIRS = make_filelist.EXCLUDE_DIRS

#: 資料區的分隔行。**純 ASCII**（2026-09-03）—— 整個包裡不准有非 ASCII
#: 字元，理由見 :func:`_data_lines_per_file`。舊的包帶著它自己那一行
#: （解包程式讀的是 `%(sentinel)s` 填進去的那份），所以改這個字串
#: **不會**讓已經搬進公司機的舊包失效。
SENTINEL = "# ==== d4t-BUNDLE-DATA ==== data below, do not edit ===="

#: 解包程式（放在產出檔案的最前面）。它自己也是這份 bundle 的一部分，
#: 所以刻意寫短、只用標準函式庫、而且看得完 —— 使用者要能在跑之前先讀一遍。
EXTRACTOR = '''#!/usr/bin/env python3
# d4t single-file text bundle (produced by tools/make_text_bundle.py).
#
# THIS FILE IS DELIBERATELY PURE ASCII - every byte is < 128. Do not put any
# non-ASCII character in here, not in a comment and not in a message.
# Reason (learned the hard way on 2026-09-03): the company machine gets this
# file by copying it out of a browser and saving it with Notepad, and Notepad
# on a Chinese Windows can write ANSI (cp950) instead of UTF-8. Any CJK byte
# then comes back mangled and Python refuses the whole file with
#   SyntaxError: Non-UTF-8 code starting with '\\\\xe5' ... no encoding declared
# An all-ASCII file cannot be damaged that way, whatever encoding is chosen.
# The payload below is base64 for the same reason.
"""The whole d4t repo lives inside this one file, as plain ASCII text.

Why this shape: company policy blocks the .zip category outright, and the
proxy will not let Python fetch files one by one -- the only thing that gets
through is a single text file you can see in a browser and copy.

    python %(name)s              # unpack into .\\\\d4t\\\\
    python %(name)s --dest D:\\\\tools
    python %(name)s --list       # just show what is inside, write nothing

Every file carries its git blob SHA-1 and is verified before it lands, so a
copy that got truncated or rewritten in transit says so instead of leaving
you with quietly broken code.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

SENTINEL = "%(sentinel)s"
PART, N_PARTS = %(part)d, %(n_parts)d   # which batch / how many (1/1 = single)
TOTAL = %(total)d                       # files in the whole repo, not this batch


def blob_sha(data: bytes) -> str:
    """How git computes a blob SHA: "blob <length>\\\\0" + content."""
    h = hashlib.sha1()
    h.update(b"blob %%d\\0" %% len(data))
    h.update(data)
    return h.hexdigest()


def entries(lines, per_file):
    """Walk the data area, yielding (sha, path, content bytes).

    ``per_file`` selects how each record's body is stored:
      True  -- base64 of lzma-compressed bytes, on "#B" lines (current format)
      False -- the file's own text, one line per line, each prefixed with "#"
    """
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#F "):
            i += 1
            continue
        _, sha, count, path = line.split(" ", 3)
        n = int(count)
        chunk = lines[i + 1:i + 1 + n]
        if per_file:
            import base64
            import lzma
            b64 = "".join(ln[2:] for ln in chunk if ln.startswith("#B"))
            yield sha, path, lzma.decompress(base64.b64decode(b64))
        else:
            # Every data line carries a leading '#' so the whole file stays
            # valid Python. Strip it back off here.
            body = [ln[1:] if ln[:1] == "#" else ln for ln in chunk]
            yield sha, path, "\\n".join(body).encode("utf-8")
        i += 1 + n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unpack the d4t text bundle.")
    ap.add_argument("--dest", default="d4t",
                    help="folder to unpack into (default .\\\\d4t)")
    ap.add_argument("--list", action="store_true",
                    help="only list the contents, write nothing")
    a = ap.parse_args(argv)

    # Read ourselves in text mode: Python turns CRLF into LF, so the file still
    # unpacks after its line endings were changed in transit (the format counts
    # lines, not bytes, for exactly that reason).
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
        lines = f.read().split("\\n")
    try:
        start = lines.index(SENTINEL) + 1
    except ValueError:
        print("FAILED: no data section found -- this file was truncated, or")
        print("        it is not a complete bundle. Copy it again.")
        return 2

    data = lines[start:]
    # The line right AFTER the separator declares the encoding. A fixed
    # position, not a pattern scan: "a line starting with #B is base64" would
    # be bitten by the content itself, because every data line gets a '#'
    # prefix, so any source line starting with B (BUNDLE_DIR = ...) becomes
    # "#B...".
    enc = data[0].strip() if data else ""
    data = data[1:]
    per_file = False
    if enc == "#ENC lzma+base64/file":
        per_file = True
    elif enc == "#ENC lzma+base64":
        # Legacy whole-archive form: one lzma stream for everything. Still
        # read here so bundles already carried into the fab keep working.
        b64 = [ln[2:] for ln in data if ln.startswith("#B")]
        import base64
        import lzma
        try:
            raw = lzma.decompress(base64.b64decode("".join(b64)))
        except Exception as exc:                     # noqa: BLE001
            print("FAILED: cannot decode the data section: %%s" %% exc)
            print("        This file was truncated or altered while being")
            print("        copied. Copy it again, and do NOT open it in an")
            print("        editor and re-save it.")
            return 2
        data = raw.decode("utf-8").split("\\n")

    try:
        items = list(entries(data, per_file))
    except Exception as exc:                         # noqa: BLE001
        print("FAILED: cannot decode the data section: %%s" %% exc)
        print("        This file was truncated or altered while being copied.")
        print("        Copy it again, and do NOT open it in an editor and")
        print("        re-save it.")
        return 2
    if not items:
        print("FAILED: the data section is empty -- this file was truncated.")
        return 2
    print("This bundle holds %%d files." %% len(items))
    if a.list:
        for _sha, path, data in items:
            print("  %%8d  %%s" %% (len(data), path))
        return 0

    dest = os.path.abspath(a.dest)
    print("Unpacking into: %%s" %% dest)
    bad, done = [], 0
    for sha, path, data in items:
        if blob_sha(data) != sha:
            bad.append(path)
            continue
        full = os.path.join(dest, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        tmp = full + ".tmp"                    # atomic: never leave half a file
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)
        done += 1

    if bad:
        print("")
        print("FAILED: %%d files do not match their own SHA:" %% len(bad))
        for path in bad[:12]:
            print("    %%s" %% path)
        print("")
        print("  This file was altered in transit (an editor re-saving it or a")
        print("  mail filter rewriting it both do this). Get a fresh copy and")
        print("  do not re-save it from an editor. This code is incomplete --")
        print("  do not use it.")
        return 1

    print("OK: %%d files unpacked, every SHA matches." %% done)

    # When the bundle is split we must say how many are still missing --
    # otherwise the user cannot tell whether they are done pasting. The count
    # comes from tools/FILELIST.txt (always in batch 1), not from this batch.
    listing = os.path.join(dest, "tools", "FILELIST.txt")
    have_listing = os.path.isfile(listing)
    missing = []
    if have_listing:
        with open(listing, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    rel = line.split(" ", 1)[1]
                    if not os.path.isfile(os.path.join(dest,
                                                       rel.replace("/", os.sep))):
                        missing.append(rel)

    if N_PARTS > 1 and not have_listing:
        # No file list yet, so "how many are missing" cannot be computed.
        # NEVER print "next step: run doctor" here -- that reads as if the
        # whole repo had arrived.
        print("")
        print("This is batch %%d of %%d; the repo has %%d files -- NOT all here yet."
              %% (PART, N_PARTS, TOTAL))
        print("Paste and run the other batches too (any order, re-running is safe).")
        print("Batch 1 carries the file list; after it, each batch says what is left.")
        return 0

    if missing:
        print("")
        print("This is batch %%d of %%d. The repo is still missing %%d files --"
              %% (PART, N_PARTS, len(missing)))
        print("they are in the other batches. Paste and run those too (any")
        print("order, re-running is safe). Missing for example:")
        for rel in missing[:6]:
            print("    %%s" %% rel)
        return 0

    print("")
    print("Next:")
    print("  cd %%s" %% dest)
    print("  python tools\\\\doctor.py        # environment self-check")
    print("  If the dependencies will not install: docs\\\\OFFLINE-INSTALL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def blob_sha(data: bytes) -> str:
    h = hashlib.sha1()                                # noqa: S324 — git 的格式
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def collect(root: str = "") -> List[Tuple[str, bytes]]:
    """``git ls-files`` 的每個檔案（路徑, 位元組）。

    順便擋掉兩種會讓「用行數打包」失效的東西：CRLF 與非 UTF-8。
    拒絕產出比產出一個解不開的包好 —— 後者要等收到的人才會發現。
    """
    root = root or repo_root()
    out = subprocess.run(["git", "ls-files"], cwd=root, check=True,
                         stdout=subprocess.PIPE).stdout.decode("utf-8")
    items = []
    for rel in sorted(p for p in out.split("\n") if p.strip()):
        if any(rel.startswith(d + "/") for d in EXCLUDE_DIRS):
            # `bundle/`：產出物自己不進包裡 —— 不然每打一次包，repo 就多一份
            # 上一次的包，而且是指數成長。
            # `docs/history/`：封存的開發史，公司機用不到而且只增不減。
            continue
        with open(os.path.join(root, rel.replace("/", os.sep)), "rb") as f:
            data = f.read()
        if b"\r" in data:
            raise SystemExit(
                "%s 含 CR（CRLF 或裸 CR）—— 以行數為單位的打包會弄壞它。"
                "先把它轉成 LF。" % rel)
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise SystemExit(
                "%s 不是 UTF-8 —— 這個格式只裝純文字。" % rel) from None
        items.append((rel, data))
    return items


def _slice(items: List[Tuple[str, bytes]], limit: int
           ) -> List[List[Tuple[str, bytes]]]:
    """依大小切成幾批。``limit`` 是每批的內容上限（位元組）。

    為什麼一定要切：**GitHub 不顯示超過 1 MB 的檔案**，而公司機唯一的取得方式是
    「在 GitHub 上看到、按複製鈕、貼進記事本」。一個 2.3 MB 的包在那台機器上
    根本點不開來複製 —— 打包成功但送不進去，是最糟的一種「做完了」。

    ``tools/FILELIST.txt`` 固定放在第一批：後面每一批解完都用它回報「還缺幾個」，
    所以它必須先到。
    """
    first = [it for it in items if it[0] == "tools/FILELIST.txt"]
    rest = [it for it in items if it[0] != "tools/FILELIST.txt"]
    out: List[List[Tuple[str, bytes]]] = [list(first)]
    size = sum(len(d) for _r, d in first)
    for rel, data in rest:
        if size + len(data) > limit and out[-1]:
            out.append([])
            size = 0
        out[-1].append((rel, data))
        size += len(data)
    return out


#: base64 一行多長。太長的行在 GitHub 上要橫向捲，看起來像壞掉的檔案。
_B64_WIDTH = 120


def _data_lines(items: List[Tuple[str, bytes]]) -> List[str]:
    """資料區（純文字形式）。壓縮版壓的也是這一段，所以兩種編碼的內容一模一樣。"""
    out: List[str] = []
    for rel, data in items:
        body = data.decode("utf-8").split("\n")
        out.append("#F %s %d %s" % (blob_sha(data), len(body), rel))
        # **每一行都要變成註解。** Python 在跑任何東西之前會先編譯整個檔案，
        # 所以資料區不能是裸的文字 —— 不然它會去解析別的檔案的內容然後語法錯誤
        # （第一版就是這樣掛的：某個 .md 裡的全形括號變成 SyntaxError）。
        # 加一個 '#' 比塞進三引號字串安全：檔案內容裡本來就可能有三個引號。
        out.extend("#" + line for line in body)
    return out


def _data_lines_per_file(items: List[Tuple[str, bytes]]) -> List[str]:
    """資料區（**逐檔 lzma + base64**）——2026-09-03 起出貨走這一種。

    一個檔案一段：``#F <sha> <幾行> <路徑>`` 之後接 ``#B<base64>`` 幾行。

    三個性質，缺一不可，而這個 repo 每一個都是踩出來的：

    1. **純 ASCII。** 公司機拿程式碼的方式是「在瀏覽器複製 → 記事本存檔」，
       而中文 Windows 的記事本會存成 ANSI（cp950）。包裡只要有一個中文字，
       存出來就是 Big5 位元組，Python 用 UTF-8 讀就死在
       ``SyntaxError: Non-UTF-8 code starting with '\xe5'`` ——
       **2026-09-03 使用者真的撞到這個**（那一輪把包改成不壓縮的純文字，
       31% 的位元組是中文）。base64 沒有這個問題，而**解包程式的檔頭也一起
       改成英文**了：那一段是最不能壞的，它就是解包本身。
    2. **git delta 壓得動。** 整包壓成一個 lzma 流的話，改一支模組會讓整份
       base64 從頭到尾變樣，git 只能每個 commit 完整存一份（實測每次 1,711 KB，
       217 個版本累積 378 MB＝pack 的 98%）。逐檔壓的話只有那一個檔案的那一段
       會變 —— 實測每次 **94 KB**。
    3. **夠小。** 純文字版 7,664 KB 在瀏覽器上全選複製會卡到不能用
       （使用者原話：「非常 lag 很卡」）。這一種 3,447 KB。

    | 格式 | 大小 | 非 ASCII | 每改一次 pack |
    |---|---|---|---|
    | 整包 lzma+base64（更早） | 2,264 KB | 934 | 1,711 KB |
    | 純文字（2026-09-03 早上） | 7,664 KB | 812,303 | 1 KB |
    | **逐檔 lzma+base64（現在）** | **3,447 KB** | **0** | **94 KB** |
    """
    out: List[str] = []
    for rel, data in items:
        # preset=6 而不是 9：9 大概只小 1%，而逐檔壓 380 次的時間差很有感。
        b64 = base64.b64encode(lzma.compress(data, preset=6)).decode("ascii")
        chunks = [b64[i:i + _B64_WIDTH] for i in range(0, len(b64), _B64_WIDTH)]
        out.append("#F %s %d %s" % (blob_sha(data), len(chunks), rel))
        out.extend("#B" + c for c in chunks)
    return out


def build(out_name: str = "d4t_bundle.py", root: str = "",
          items: Optional[List[Tuple[str, bytes]]] = None,
          part: int = 1, n_parts: int = 1, total_files: int = 0,
          compress: bool = False) -> str:
    items = collect(root) if items is None else items
    parts = [EXTRACTOR % {"name": out_name, "sentinel": SENTINEL,
                          "part": part, "n_parts": n_parts,
                          "total": total_files or len(items)}, SENTINEL]
    if not compress:
        # **預設**：逐檔 lzma+base64（純 ASCII、git 壓得動、夠小）。
        parts.append("#ENC lzma+base64/file")
        parts.extend(_data_lines_per_file(items))
        return "\n".join(parts) + "\n"
    body = _data_lines(items)
    if compress:
        parts.append("#ENC lzma+base64")
        # **lzma 而不是 gzip。** 整包 base64 之後 gzip 是 991 KB、lzma 是 701 KB，
        # 而 GitHub 不顯示超過 1 MB 的檔案 —— 那 290 KB 的差距正好就是
        # 「一個檔案」與「還是要分成六批」的差別。
        import base64
        import lzma
        blob = base64.b64encode(lzma.compress(
            "\n".join(body).encode("utf-8"), preset=9)).decode("ascii")
        parts.extend("#B" + blob[i:i + _B64_WIDTH]
                     for i in range(0, len(blob), _B64_WIDTH))
        return "\n".join(parts) + "\n"
    parts.append("#ENC text")
    parts.extend(body)
    return "\n".join(parts) + "\n"


#: 一個檔案最多幾 KB。**GitHub 不顯示超過 1 MB 的檔案**，而公司機唯一的
#: 取得方式是「在 GitHub 上看到、按複製鈕」。留一成餘裕給下一次成長。
LIMIT_KB = 900


def _content_bytes(items: List[Tuple[str, bytes]]) -> int:
    return sum(len(d) for _r, d in items)


def _fit(items: List[Tuple[str, bytes]], compress: bool, limit: int
         ) -> List[List[Tuple[str, bytes]]]:
    """切到**每一批真的塞得下**為止。

    為什麼是量出來不是算出來：壓縮率跟內容有關（這個 repo 大量重複的
    docstring 壓得特別好），任何事先估的比例都會在某一次改動之後失準 ——
    而失準的症狀是「打包成功，但那個檔案在公司機上點不開」。

    2026-08-14 記：壓縮版一度被當成「一定塞得進一個檔案」，那個假設在
    repo 長到 908 KB 的那天過期了。
    """
    limit = max(1, int(limit))
    total = _content_bytes(items)
    groups = [list(items)]
    for _ in range(32):
        sizes = [len(build("x.py", items=g, part=i, n_parts=len(groups),
                           total_files=len(items), compress=compress)
                     .encode("utf-8")) for i, g in enumerate(groups, 1)]
        if max(sizes) <= limit:
            return groups
        nxt = _slice(items, max(1, total // (len(groups) + 1) + 1))
        if len(nxt) <= len(groups):
            return groups                 # 切不下去了（單一檔案就超過上限）
        groups = _merge_tail(nxt, compress, limit, len(items))
    return groups


def _merge_tail(groups: List[List[Tuple[str, bytes]]], compress: bool,
                limit: int, total_files: int) -> List[List[Tuple[str, bytes]]]:
    """把尾巴上塞得下的批併回去。

    貪心切割會留下一個很小的尾批（實測 492 / 480 / **29** KB）——「還要再複製
    一次」對那台只能用剪貼簿的機器是實打實的成本，而那 29 KB 明明併得進去。
    """
    out = [list(g) for g in groups]
    while len(out) > 1:
        merged = out[:-2] + [out[-2] + out[-1]]
        sizes = [len(build("x.py", items=g, part=i, n_parts=len(merged),
                           total_files=total_files, compress=compress)
                     .encode("utf-8")) for i, g in enumerate(merged, 1)]
        if max(sizes) > limit:
            break
        out = merged
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Pack the repo into one plain-text self-extracting .py")
    ap.add_argument("--out", default="d4t_bundle.py",
                    help="輸出檔名（分批時會變成 ..._part1of6.py）")
    ap.add_argument("--compress", action="store_true",
                    help=("壓縮成**一個**檔案（lzma + base64，約 700 KB）。"
                          "一次複製就搬完，代價是內容不再是可以直接讀的文字 ——"
                          "解包程式本身仍然是可讀的 Python，而且 --list 可以先看"
                          "它會寫哪些檔案。"))
    ap.add_argument("--split", type=int, default=0, metavar="KB",
                    help=("每批最多幾 KB（0 = 不分批）。**GitHub 不顯示超過 1 MB "
                          "的檔案**，而剪貼簿是唯一的通道時就必須分批，"
                          "400 是安全值。"))
    a = ap.parse_args(argv)

    items = collect()
    if a.compress and not a.split:
        # **壓縮版也會長大。** 它一度是 701 KB，2026-08-14 到了 908 KB。
        # 所以不再假設「壓縮就一定塞得進一個檔案」：量出來，塞不下就分批。
        groups = _fit(items, True, LIMIT_KB * 1024)
    else:
        groups = _slice(items, a.split * 1024) if a.split else [items]
    out_dir = os.path.dirname(os.path.abspath(a.out))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    stem, ext = os.path.splitext(a.out)
    n_parts = len(groups)

    for i, group in enumerate(groups, 1):
        name = a.out if n_parts == 1 else "%s_part%dof%d%s" % (stem, i, n_parts, ext)
        text = build(os.path.basename(name), items=group, part=i,
                     n_parts=n_parts, total_files=len(items),
                     compress=a.compress)
        tmp = name + ".tmp"                           # atomic（鐵則 5）
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, name)
        print("%s：%d 個檔案、%.0f KB"
              % (name, len(group), len(text.encode("utf-8")) / 1024))
    if n_parts > 1:
        print("\n共 %d 批、%d 個檔案。每一批都可以單獨執行，順序不重要，"
              "重複執行也沒關係。" % (n_parts, len(items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
