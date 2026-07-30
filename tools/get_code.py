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
    python get_code.py --proxy http://proxy.corp.com:8080   # 要走公司 proxy

**瀏覽器連得到但這支逾時（WinError 10060）＝ 沒走 proxy，不是被擋。**
``urllib`` 會讀 ``HTTPS_PROXY`` 與 Windows 登錄檔裡**手動設定**的 proxy，
但**讀不到 PAC（自動設定指令碼）**，而公司幾乎都用 PAC —— 瀏覽器懂 PAC、
Python 不懂，所以同一台機器上一個通一個不通。

所以在 Windows 上，沒有其他 proxy 設定時這支會**自己請 .NET 把 PAC 解開**
（``GetSystemWebProxy().GetProxy(url)``，跟瀏覽器同一套設定），解得出來就直接
用，開頭那行 ``Proxy :`` 會講它是怎麼來的。解不出來才要你自己填 ``--proxy``。

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
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "hxlub0905-cmyk/ADEPT"
RAW = "https://raw.githubusercontent.com/%s/%s/%s"
MANIFEST = "tools/FILELIST.txt"
TIMEOUT = 30


def build_opener(cafile: str = "", proxy: str = ""):
    """做一個 opener（proxy 與公司憑證都掛在這裡）。

    不給 ``proxy`` 的話走 urllib 的預設 —— 它會讀 ``HTTPS_PROXY`` 環境變數，
    在 Windows 上也會讀登錄檔裡**手動設定**的 proxy。
    **但它讀不到 PAC（自動設定指令碼）**，而公司幾乎都用 PAC ——
    那種情況下 urllib 會直接連出去，然後逾時（WinError 10060）。
    """
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    if cafile:
        import ssl
        handlers.append(urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=cafile)))
    return urllib.request.build_opener(*handlers)


#: ``main()`` 建好之後放在這裡，``fetch()`` 用它（``fetch`` 的簽名保持簡單，
#: 測試才好 monkeypatch 掉整個網路層）。
_OPENER = None


def fetch(ref: str, path: str, cafile: str = "") -> bytes:
    url = RAW % (REPO, ref, path)
    opener = _OPENER or build_opener(cafile)
    with opener.open(url, timeout=TIMEOUT) as r:      # noqa: S310 — 固定 https
        return r.read()


def proxy_in_effect(proxy: str = "") -> str:
    """現在實際會用哪個 proxy（沒有就回空字串）。"""
    if proxy:
        return proxy
    return urllib.request.getproxies().get("https", "")


def system_proxy_for(url: str) -> str:
    """問 Windows「連這個網址要走哪個 proxy」—— **PAC 會被解開**。

    ``urllib`` 讀不到 PAC，但 .NET 讀得到（瀏覽器用的是同一套設定），
    所以在 Windows 上借 PowerShell 問一次。這比叫使用者自己打開 PAC 檔去找
    ``PROXY 主機:埠`` 好太多了 —— 那種檔案通常有上百行條件判斷，而且「哪一行
    適用於這個網址」正是 PAC 要算的東西。

    ``GetProxy()`` 在「不需要 proxy」時會回傳原網址，所以那種情況回空字串。
    任何一步失敗都回空字串（診斷用的東西不可以自己變成失敗原因）。
    """
    if not sys.platform.startswith("win"):
        return ""
    ps = ("[System.Net.WebRequest]::GetSystemWebProxy()"
          ".GetProxy('%s').AbsoluteUri" % url)
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25)
    except Exception:                                 # noqa: BLE001 — 診斷用
        return ""
    got = out.stdout.decode("utf-8", "replace").strip().splitlines()
    got = got[-1].strip() if got else ""
    if not got or got.rstrip("/") == url.rstrip("/"):
        return ""                                     # .NET 說不用 proxy
    if not got.startswith(("http://", "https://")):
        return ""
    return got


def pac_url() -> str:
    """Windows 登錄檔裡的 PAC（自動設定指令碼）網址；沒有或不是 Windows 回空字串。

    這是「瀏覽器連得到、Python 連不到」最常見的原因，而且從錯誤訊息完全看不出來
    —— 所以直接去把它讀出來講給使用者聽。
    """
    if not sys.platform.startswith("win"):
        return ""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        try:
            return str(winreg.QueryValueEx(key, "AutoConfigURL")[0] or "")
        finally:
            winreg.CloseKey(key)
    except Exception:                                 # noqa: BLE001 — 診斷用
        return ""


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
    ap.add_argument("--proxy", default="",
                    help="公司 proxy，例如 http://proxy.corp.com:8080")
    a = ap.parse_args(argv)

    # 沒人給 proxy、環境也沒有的時候，去問 Windows（PAC 就是在這裡被解開的）。
    # 使用者不該為了下載一份程式碼去讀一個上百行的 PAC 檔。
    proxy, how = a.proxy, ""
    if not proxy and not proxy_in_effect():
        proxy = system_proxy_for(RAW % (REPO, a.ref, MANIFEST))
        if proxy:
            how = "（從 Windows 的自動設定（PAC）解出來的）"

    global _OPENER
    _OPENER = build_opener(a.cafile, proxy)

    print("來源  : https://raw.githubusercontent.com/%s (%s)" % (REPO, a.ref))
    print("目的地: %s" % os.path.abspath(a.dest))
    print("Proxy : %s%s" % (proxy_in_effect(proxy) or "（不用 proxy，直接連）", how))
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
        # 連不上（DNS / TCP / TLS）。**這裡不能一律講「被擋掉了」** ——
        # 逾時（WinError 10060 / timed out）的意思是「直接連出去、封包沒人回」，
        # 而那通常代表 **Python 沒有走公司 proxy**，不是這台主機被封。
        # 瀏覽器連得到、Python 連不到，幾乎都是這件事。
        reason = str(e.reason)
        print("\n✗ 連不上 raw.githubusercontent.com：%s" % reason)
        if "CERTIFICATE" in reason.upper():
            print("  這是 TLS 被公司中間攔截。用 --cafile 指到公司的根憑證，")
            print("  **不要**去關掉憑證驗證。")
            return 2

        timed_out = ("10060" in reason or "timed out" in reason.lower()
                     or "timeout" in reason.lower())
        using = proxy_in_effect(proxy)
        if timed_out and not using:
            pac = pac_url()
            print("\n  這是**逾時**，不是被拒絕 —— 封包直接送出去而沒有人回應。")
            print("  如果你的瀏覽器連得到 GitHub，那答案幾乎一定是：")
            print("  **這台機器要透過公司 proxy 才連得出去，而 Python 沒有走 proxy。**")
            if pac:
                print("\n  你的 proxy 是用 PAC 自動設定檔設的 ——")
                print("    %s" % pac)
                print("  我試著請 Windows 幫我解開它（.NET 讀得懂 PAC），但沒有解出")
                print("  可以用的 proxy。請用瀏覽器打開上面那個網址，找 `PROXY 主機:埠`，")
                print("  然後：")
            else:
                print("\n  先找出 proxy（PowerShell，任一個有值就用它）：")
                print("    netsh winhttp show proxy")
                print("    Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows"
                      "\\CurrentVersion\\Internet Settings' |"
                      " Select ProxyServer, AutoConfigURL")
                print("    pip config list          # pip 能連的話，proxy 就在這裡")
                print("  AutoConfigURL 有值 = PAC 檔：用瀏覽器打開它，找 `PROXY 主機:埠`。")
                print("  然後：")
            print("    python get_code.py --proxy http://主機:埠")
            print("  （或先 `$env:HTTPS_PROXY='http://主機:埠'` 再跑，pip 也吃這個）")
            return 2

        if using:
            print("\n  用的 proxy 是 %s —— 它沒有回應。確認位址與埠是對的，" % using)
            print("  有些公司 proxy 只放行特定網域，那就要請 IT 加"
                  " raw.githubusercontent.com。")
        else:
            print("\n  這台主機連不上。剩下的路：")
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
