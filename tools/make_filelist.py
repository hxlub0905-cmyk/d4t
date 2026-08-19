#!/usr/bin/env python3
# d4t 檔案清單產生器 — authored 2026-07-30.
"""產生 ``tools/FILELIST.txt``：``tools/get_code.py`` 靠它知道要抓哪些檔案。

在**開發機**上跑（需要 git）：

    python tools/make_filelist.py

為什麼要有這份清單
------------------
``get_code.py`` 刻意只用**一台主機**（``raw.githubusercontent.com``）——
`codeload.github.com`（zip）與 `api.github.com`（列檔案）都是另外的主機，
而公司 proxy 的 allowlist 每多一台就多一個會被擋的地方。
raw 送得出單一檔案但列不出目錄，所以清單得先放在 repo 裡。

清單裡存的是 **git blob SHA-1**，不是大小或 md5 —— 這樣 ``git hash-object``
可以直接對照，`tests/test_offline_tools.py` 也就擋得住這份清單腐爛
（新增檔案卻忘了重跑這支的話，那個檔案在受限機器上會**安靜地少掉**）。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from typing import List

#: 清單自己不列在自己裡面（它的 SHA 沒辦法包含自己的 SHA）。
#: ``get_code.py`` 是先抓這份清單才開始抓別的，所以它不需要被驗。
MANIFEST = "tools/FILELIST.txt"

#: 不搬進公司機的目錄。**這份清單同時是打包的依據**（`make_text_bundle.py`
#: import 它），所以兩邊永遠一致 —— 兩份各自維護的排除清單一定會分家。
#:
#: * `bundle/` —— `make_text_bundle.py` 產的搬運用檔案，是 repo 的**複本**不是
#:   內容。列進去有兩個後果：`get_code.py` 會白抓一份，而分批解包的「還缺幾個」
#:   永遠到不了 0（那幾個檔案本來就不在包裡）。
#: * `docs/history/` —— 封存的開發紀錄。它**只增不減**，而搬運包離 GitHub 的
#:   1 MB 顯示上限只剩不到一成（見 `release.py` 的 `BUNDLE_LIMIT_BYTES`）。
#:   公司機的工作是「拿到程式碼並執行」，開發史在那台機器上一行都用不到，
#:   卻會佔掉真正要搬的東西的餘裕。要讀的話 GitHub 上讀得到。
EXCLUDE_DIRS = ("bundle", "docs/history")

HEADER = (
    "# d4t 檔案清單 —— tools/get_code.py 用（每行：git blob SHA-1 + 路徑）。",
    "# 由 tools/make_filelist.py 產生；tests/test_offline_tools.py 會擋住它腐爛。",
)


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tracked_files(root: str = "") -> List[str]:
    """``git ls-files``（排除清單自己），排序後回傳。"""
    root = root or repo_root()
    out = subprocess.run(["git", "ls-files"], cwd=root, check=True,
                         stdout=subprocess.PIPE).stdout.decode("utf-8")
    keep = []
    for raw in out.split("\n"):
        rel = raw.strip()
        if not rel or rel == MANIFEST:
            continue
        if any(rel.startswith(d + "/") for d in EXCLUDE_DIRS):
            continue
        keep.append(rel)
    return sorted(keep)


def blob_sha(data: bytes) -> str:
    """git 算 blob SHA 的方式：``"blob <len>\\0" + 內容``（與 get_code.py 相同）。"""
    h = hashlib.sha1()                                # noqa: S324 — git 的格式
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def build_lines(root: str = "") -> List[str]:
    """整份清單的內容（測試拿這個跟磁碟上的檔案對照）。"""
    root = root or repo_root()
    lines = list(HEADER)
    for rel in tracked_files(root):
        with open(os.path.join(root, rel.replace("/", os.sep)), "rb") as f:
            lines.append("%s %s" % (blob_sha(f.read()), rel))
    return lines


def main(argv=None) -> int:
    root = repo_root()
    lines = build_lines(root)
    path = os.path.join(root, MANIFEST.replace("/", os.sep))
    tmp = path + ".tmp"                               # atomic（鐵則 5）
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
    print("%s：%d 個檔案" % (MANIFEST, len(lines) - len(HEADER)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
