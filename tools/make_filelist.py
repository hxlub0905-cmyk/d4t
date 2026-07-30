#!/usr/bin/env python3
# ADEPT 檔案清單產生器 — authored 2026-07-30.
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

HEADER = (
    "# ADEPT 檔案清單 —— tools/get_code.py 用（每行：git blob SHA-1 + 路徑）。",
    "# 由 tools/make_filelist.py 產生；tests/test_offline_tools.py 會擋住它腐爛。",
)


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tracked_files(root: str = "") -> List[str]:
    """``git ls-files``（排除清單自己），排序後回傳。"""
    root = root or repo_root()
    out = subprocess.run(["git", "ls-files"], cwd=root, check=True,
                         stdout=subprocess.PIPE).stdout.decode("utf-8")
    return sorted(p for p in out.split("\n") if p.strip() and p.strip() != MANIFEST)


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
