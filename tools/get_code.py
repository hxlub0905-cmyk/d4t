#!/usr/bin/env python3
# ADEPT 取得程式碼（不用 git、不用 zip）— authored 2026-07-30.
"""在「zip 下載被擋」的機器上把整包程式碼抓下來。stdlib-only、單一檔案。

為什麼需要這支
--------------
GitHub 的 Download ZIP 是從 ``codeload.github.com`` 出來的 —— **跟 github.com
是不同的主機**，而公司 proxy 的 allowlist 常常只放了後者。網頁看得到、zip 下不來，
而 ``.tar.gz`` 也在同一台主機上，所以換副檔名沒有用。

這支只用 **一台主機**：``raw.githubusercontent.com``（送 ``text/plain``，
DLP 對它的規則跟 ``application/zip`` 完全不同）。

怎麼拿到這支
------------
你連這個檔案也下載不了 —— 所以到 GitHub 上打開 ``tools/get_code.py``，
按右上角的**複製鈕**，貼進一個新檔案存成 ``get_code.py``。整份是純文字。

    python get_code.py                 # 抓到 .\\ADEPT\\
    python get_code.py --dest D:\\tools  # 抓到別的地方
    python get_code.py --ref main      # 指定分支（預設 main）
    python get_code.py --ref a30a040…  # 指定 commit（要完全可重現時用這個）

``--ref`` 給分支名的時候，抓到的是 **CDN 上的那一版** —— 剛推上去的東西可能要
等幾分鐘才看得到（實測會拿到前一個 commit；清單與檔案來自同一份快照，
所以 SHA 仍然全部對得上，不會誤報，但你拿到的是稍舊的一份）。
要百分之百確定抓到哪一版，``--ref`` 直接給 commit SHA（commit 是不變的，沒有快取問題）。

為什麼要驗 SHA
--------------
被擋的 proxy **不一定回錯誤碼** —— 它常常回一頁登入頁或一段警告 HTML，
HTTP 200。那種東西寫進 ``.py`` 檔之後，症狀會變成「程式碼看起來都在，
但 import 就爆語法錯誤」，而使用者完全不知道是下載壞了。
所以每個檔案都對 ``FILELIST.txt`` 裡的 **git blob SHA-1** 驗過才落地。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.error
import urllib.request

REPO = "hxlub0905-cmyk/ADEPT"
RAW = "https://raw.githubusercontent.com/%s/%s/%s"
MANIFEST = "tools/FILELIST.txt"
TIMEOUT = 30


def fetch(ref: str, path: str, cafile: str = "") -> bytes:
    url = RAW % (REPO, ref, path)
    kw = {"timeout": TIMEOUT}
    if cafile:
        import ssl
        kw["context"] = ssl.create_default_context(cafile=cafile)
    with urllib.request.urlopen(url, **kw) as r:      # noqa: S310 — 固定 https
        return r.read()


def blob_sha(data: bytes) -> str:
    """git 算 blob SHA 的方式：``"blob <len>\\0" + 內容``。"""
    h = hashlib.sha1()                                # noqa: S324 — git 的格式
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def write_atomic(dest: str, rel: str, data: bytes) -> None:
    full = os.path.join(dest, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    tmp = full + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, full)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download ADEPT without git or zip.")
    ap.add_argument("--dest", default="ADEPT", help="要放在哪個資料夾（預設 .\\ADEPT）")
    ap.add_argument("--ref", default="main", help="分支或 tag（預設 main）")
    ap.add_argument("--cafile", default="",
                    help="公司的根憑證 .pem（TLS 被中間攔截時才需要）")
    a = ap.parse_args(argv)

    print("來源  : https://raw.githubusercontent.com/%s (%s)" % (REPO, a.ref))
    print("目的地: %s" % os.path.abspath(a.dest))
    try:
        raw = fetch(a.ref, MANIFEST, a.cafile).decode("utf-8")
    except urllib.error.HTTPError as e:
        # **伺服器有回答** —— 所以連線是通的。這裡最容易給錯的診斷是把 404
        # 講成「被擋住了」，然後使用者去找 IT，而真正的原因是 --ref 打錯。
        print("\n✗ 抓 %s 失敗：HTTP %s" % (MANIFEST, e.code))
        if e.code == 404:
            print("  連得上，但這個分支上沒有這個檔案。檢查 --ref（現在是 '%s'）；"
                  % a.ref)
            print("  預設分支通常是 main。")
        elif e.code in (401, 403, 407, 451, 511):
            print("  連得上，但被拒絕了 —— 403 / 407 這種通常就是公司 proxy")
            print("  （不是 GitHub）。看下面「三台主機都被擋」的那條路。")
        else:
            print("  %s" % e.reason)
        return 2
    except urllib.error.URLError as e:
        # 連不上（DNS / TCP / TLS）—— 這才是「被擋掉了」。
        print("\n✗ 連不上 raw.githubusercontent.com：%s" % e.reason)
        if "CERTIFICATE" in str(e.reason).upper():
            print("  看起來是 TLS 被公司中間攔截。用 --cafile 指到公司的根憑證，")
            print("  **不要**去關掉憑證驗證。")
            return 2
        print("  這台主機也被擋掉了。剩下的路只有：")
        print("  1. 請 IT 放行 codeload.github.com（zip 就會回來，這是根治）")
        print("  2. 在有網路的機器上取得，用你搬 wheels\\ 的同一條路搬過來")
        print("     （見 docs/OFFLINE-INSTALL.md）")
        return 2

    want = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            sha, _, path = line.partition(" ")
            if path:
                want.append((sha, path))
    if not want:
        print("\n✗ %s 是空的 —— proxy 可能回了一頁別的東西。" % MANIFEST)
        return 2
    print("清單  : %d 個檔案\n" % len(want))

    # 清單自己不在自己的清單裡（SHA 沒辦法自我包含），但受限機器上還是需要它 ——
    # 少了它，抓下來那份 repo 就不完整，而且**看不出來少了什麼**。
    # 位元組已經在手上，直接落地。
    write_atomic(a.dest, MANIFEST, raw.encode("utf-8"))

    bad, done = [], 0
    for sha, path in want:
        try:
            data = fetch(a.ref, path, a.cafile)
        except Exception as e:                        # noqa: BLE001
            bad.append((path, "抓不到：%s" % e))
            continue
        got = blob_sha(data)
        if got != sha:
            # 最常見的原因不是「檔案壞了」，是 proxy 回了一頁 HTML（HTTP 200）
            hint = "內容不是預期的（可能是 proxy 的攔截頁）"
            if data.lstrip()[:1] == b"<":
                hint += "；開頭是 '<'，看起來真的是 HTML"
            bad.append((path, hint))
            continue
        write_atomic(a.dest, path, data)
        done += 1
        if done % 25 == 0 or done == len(want):
            print("  %d / %d" % (done, len(want)))

    if bad:
        print("\n✗ %d 個檔案沒抓成功：" % len(bad))
        for path, why in bad[:12]:
            print("    %-44s %s" % (path, why))
        if len(bad) > 12:
            print("    …還有 %d 個" % (len(bad) - 12))
        print("\n  這份程式碼**不完整，不要用**。先解決上面的原因再重跑。")
        return 1

    print("\n✓ %d 個檔案都抓下來了，SHA 全部對得上。\n" % done)
    print("下一步：")
    print("  cd %s" % a.dest)
    print("  python tools\\doctor.py        # 環境自檢（會告訴你還缺什麼）")
    print("  相依套件裝不了的話走離線 wheels：docs\\OFFLINE-INSTALL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
