#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ADEPT offline packaging tool #1 — authored 2026-07-28 (M6-1).
"""在**有網路的機器**上，把 ADEPT 需要的套件下載成離線 wheels 資料夾。

情境：公司機的 pip 連不到外網（或整台機器沒有對外網路），
所以要先在家用/開發機把「Windows 版的 .whl 檔」抓好，整個資料夾帶進廠。

用法：
    python tools/fetch_wheels.py                        # 預設抓 win_amd64 + Python 3.9
    python tools/fetch_wheels.py --python-version 311   # 公司機是 Python 3.11 就改這個
    python tools/fetch_wheels.py --dest wheels --include-pytest
    python tools/fetch_wheels.py --dry-run              # 只印出它會執行的 pip 指令

重點：**本機是 Linux/macOS 也照樣能抓 Windows 的 wheel** ——
靠的是 ``pip download --only-binary=:all: --platform win_amd64
--python-version 39 --implementation cp --abi cp39``。
（pip 規定：一旦指定 --platform/--python-version，就必須加 --only-binary=:all:。）

產出：
    wheels/*.whl
    wheels/MANIFEST.txt   ← 檔名 + sha256 + 目標平台/Python，給使用者與 IT 稽核用

本檔**只用標準函式庫**（它要能在還沒裝任何套件的機器上跑）。
下載動作一律外包給 `python -m pip download` 子行程，不 import pip 內部 API。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

MANIFEST_NAME = "MANIFEST.txt"
MANIFEST_SCHEMA = "adept.wheels.manifest/1"

DEFAULT_PLATFORM = "win_amd64"
DEFAULT_PYTHON_VERSION = "39"
DEFAULT_IMPLEMENTATION = "cp"

# 依賴名 → 在公司機上「import 得到的名字」（只用來把訊息寫得白話一點）
IMPORT_NAME = {
    "opencv-python": "cv2",
    "pyside6": "PySide6",
    "numpy": "numpy",
    "tifffile": "tifffile",
    "openpyxl": "openpyxl",
    "pytest": "pytest",
}


# ---------------------------------------------------------------- 小工具

def _norm(name: str) -> str:
    """PEP 503 風格的正規化：``opencv-python`` 與 ``opencv_python`` 視為同一個。"""
    return re.sub(r"[-_.]+", "_", name).strip().lower()


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0 or unit == "GB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%.1f GB" % n


def parse_requirements(path: str) -> List[str]:
    """讀 requirements.txt，回傳「套件名」清單（去掉版本條件與註解）。

    只做最低限度的解析：本專案的 requirements.txt 是最單純的一行一個套件。
    以 ``-`` 開頭的 pip 選項行（例如 ``--index-url``）直接略過。
    """
    names: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
            if m:
                names.append(m.group(1))
    return names


def parse_wheel_filename(fname: str) -> Optional[Tuple[str, str, str, str, str]]:
    """``name-version-pytag-abitag-plattag.whl`` → 5 元組；認不出來回 None。"""
    if not fname.lower().endswith(".whl"):
        return None
    parts = fname[:-4].split("-")
    if len(parts) < 5:
        return None
    # build tag（選用）夾在 version 之後；把它併掉，只保留最後三個 tag
    name, version = parts[0], parts[1]
    pytag, abitag, plattag = parts[-3], parts[-2], parts[-1]
    return (name, version, pytag, abitag, plattag)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- pip 指令組裝

def default_abi(python_version: str, implementation: str = DEFAULT_IMPLEMENTATION) -> str:
    """由 --python-version / --implementation 推出預設 abi tag（cp39 → ``cp39``）。"""
    digits = re.sub(r"[^0-9]", "", python_version)
    if implementation != "cp" or not digits:
        return "none"
    if digits in ("36", "37"):
        return "cp%sm" % digits          # 3.7 以前 Windows ABI tag 帶 m
    return "cp%s" % digits


def build_pip_command(*, dest: str, requirements: Optional[str] = None,
                      platforms: Sequence[str] = (DEFAULT_PLATFORM,),
                      python_version: str = DEFAULT_PYTHON_VERSION,
                      implementation: str = DEFAULT_IMPLEMENTATION,
                      abi: Optional[str] = None,
                      extra_packages: Sequence[str] = (),
                      python_exe: Optional[str] = None) -> List[str]:
    """組出 ``pip download`` 的 argv（純函式，測試直接驗這個，不真的連網）。"""
    exe = python_exe or sys.executable
    cmd: List[str] = [exe, "-m", "pip", "download",
                      "--only-binary=:all:",
                      "--dest", dest,
                      "--python-version", str(python_version),
                      "--implementation", implementation,
                      "--abi", abi or default_abi(python_version, implementation)]
    for plat in platforms:
        cmd += ["--platform", plat]
    if requirements:
        cmd += ["-r", requirements]
    cmd += list(extra_packages)
    return cmd


# ---------------------------------------------------------------- 驗證與報表

def scan_dest(dest: str) -> Tuple[List[str], List[str]]:
    """掃 dest：回傳 (wheel 檔名清單, 非 wheel 的套件檔清單=sdist)。"""
    wheels: List[str] = []
    sdists: List[str] = []
    for fn in sorted(os.listdir(dest)):
        low = fn.lower()
        if low.endswith(".whl"):
            wheels.append(fn)
        elif low.endswith((".tar.gz", ".zip", ".tar.bz2")):
            sdists.append(fn)
    return wheels, sdists


def match_requirements(requirements: Sequence[str],
                       wheels: Sequence[str]) -> Dict[str, List[str]]:
    """每個 requirement → 對應到的 wheel 檔名（可能 0 個）。"""
    by_name: Dict[str, List[str]] = {}
    for fn in wheels:
        info = parse_wheel_filename(fn)
        if info is None:
            continue
        by_name.setdefault(_norm(info[0]), []).append(fn)
    return {req: by_name.get(_norm(req), []) for req in requirements}


def _atomic_write(path: str, text: str) -> None:
    """先寫 .tmp 再 os.replace（CLAUDE.md 鐵則 5：檔案寫入一律 atomic）。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def build_manifest_text(*, wheels: Sequence[str], dest: str, platforms: Sequence[str],
                        python_version: str, implementation: str, abi: str,
                        requirements_path: str,
                        requirement_names: Sequence[str]) -> str:
    """產生 MANIFEST.txt 內容（人看得懂，也好用 grep/程式解析）。"""
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: List[Tuple[str, str, int]] = []
    total = 0
    for fn in wheels:
        full = os.path.join(dest, fn)
        size = os.path.getsize(full)
        total += size
        rows.append((fn, sha256_of(full), size))

    lines: List[str] = []
    lines.append("# ADEPT 離線安裝套件清單（MANIFEST）")
    lines.append("# 由 tools/fetch_wheels.py 產生；tools/install_offline.py 會讀這個檔做版本檢查。")
    lines.append("# 這個資料夾只包含公開 PyPI 上的官方套件，沒有任何 ADEPT 自製二進位檔。")
    lines.append("")
    lines.append("schema: %s" % MANIFEST_SCHEMA)
    lines.append("generated_utc: %s" % now)
    lines.append("target_platform: %s" % ",".join(platforms))
    lines.append("target_python: %s" % python_version)
    lines.append("target_implementation: %s" % implementation)
    lines.append("target_abi: %s" % abi)
    lines.append("requirements_file: %s" % os.path.basename(requirements_path))
    lines.append("requirements: %s" % ", ".join(requirement_names))
    lines.append("wheel_count: %d" % len(rows))
    lines.append("total_bytes: %d" % total)
    lines.append("fetched_on_host: Python %s / %s" %
                 (".".join(str(x) for x in sys.version_info[:3]), sys.platform))
    lines.append("")
    lines.append("# 以下每行：檔名 <空白> sha256 <空白> 位元組數")
    lines.append("# 驗證方式（Windows PowerShell）：Get-FileHash -Algorithm SHA256 wheels\\檔名")
    for fn, digest, size in rows:
        lines.append("%s  %s  %d" % (fn, digest, size))
    lines.append("")
    return "\n".join(lines)


def _width(text: str) -> int:
    """顯示寬度：CJK 全形字算 2 格（不然表格會歪掉）。"""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int, right: bool = False) -> str:
    fill = " " * max(0, width - _width(text))
    return (fill + text) if right else (text + fill)


def print_table(dest: str, wheels: Sequence[str]) -> int:
    """印出（套件、版本、大小）表格，回傳總位元組數。"""
    rows: List[Tuple[str, str, str, int]] = []
    total = 0
    for fn in wheels:
        info = parse_wheel_filename(fn)
        size = os.path.getsize(os.path.join(dest, fn))
        total += size
        if info is None:
            rows.append((fn, "?", "?", size))
        else:
            rows.append((info[0], info[1], "%s-%s" % (info[2], info[4]), size))
    if not rows:
        return 0
    w0 = max([_width("套件")] + [_width(r[0]) for r in rows])
    w1 = max([_width("版本")] + [_width(r[1]) for r in rows])
    w2 = max([_width("標籤")] + [_width(r[2]) for r in rows])
    rule = "  " + "-" * (w0 + w1 + w2 + 16)
    print("")
    print("  %s  %s  %s  %s" % (_pad("套件", w0), _pad("版本", w1),
                                _pad("標籤", w2), _pad("大小", 10, right=True)))
    print(rule)
    for name, ver, tag, size in sorted(rows, key=lambda r: r[0].lower()):
        print("  %s  %s  %s  %s" % (_pad(name, w0), _pad(ver, w1), _pad(tag, w2),
                                    _pad(_human_size(size), 10, right=True)))
    print(rule)
    print("  合計 %d 個檔案，%s" % (len(rows), _human_size(total)))
    return total


# ---------------------------------------------------------------- pip 失敗的白話翻譯

def explain_pip_failure(stderr: str, *, platform: str, python_version: str) -> List[str]:
    """把 pip 的英文錯誤翻成「該怎麼辦」。回傳數行建議。"""
    low = (stderr or "").lower()
    tips: List[str] = []
    if "no matching distribution" in low or "could not find a version" in low:
        tips.append("最可能的原因：某個套件在 %s + Python %s 這個組合下沒有官方 wheel。"
                    % (platform, python_version))
        tips.append("做法 A：把 --python-version 改成公司機真正的 Python 版本"
                    "（在公司機執行 `python -V` 查）。")
        tips.append("做法 B：放寬 requirements.txt 的版本下限（舊 Python 只有舊版套件）。")
    if "none of the wheels" in low or "only-binary" in low:
        tips.append("這個套件只有原始碼（sdist），沒有 wheel；"
                    "公司機沒有編譯器裝不起來，請改用有 wheel 的版本。")
    if "proxy" in low or "connection" in low or "network" in low or "timed out" in low:
        tips.append("看起來是這台機器連不到 PyPI（代理/防火牆）。"
                    "fetch_wheels.py 必須在**有網路**的機器上跑。")
    if "no module named pip" in low:
        tips.append("這台機器的 Python 沒有 pip。請用另一個有 pip 的 Python，"
                    "或先執行 `python -m ensurepip`。")
    if not tips:
        tips.append("請把上面 pip 的原始訊息連同這行指令一起回報。")
    return tips


# ---------------------------------------------------------------- 主流程

def _soften_stdout() -> None:
    """主控台字碼頁吐不出某些字時，改成 replace 而不是整支程式炸掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")      # Python 3.7+
        except Exception:                             # noqa: BLE001 — 沒有就算了
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _soften_stdout()
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(
        prog="fetch_wheels.py",
        description="在有網路的機器上，把 ADEPT 的相依套件下載成離線 wheels 資料夾。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="範例：\n"
               "  python tools/fetch_wheels.py --python-version 311 --include-pytest\n"
               "  python tools/fetch_wheels.py --platform win_amd64 --dest D:\\adept_wheels\n")
    ap.add_argument("--dest", default="wheels", help="wheel 存放資料夾（預設 wheels）")
    ap.add_argument("--python-version", default=DEFAULT_PYTHON_VERSION,
                    help="公司機的 Python 版本，寫成 39 / 310 / 311（預設 39）")
    ap.add_argument("--platform", action="append", default=None,
                    help="目標平台 tag（預設 win_amd64；可重複指定）")
    ap.add_argument("--implementation", default=DEFAULT_IMPLEMENTATION,
                    help="Python 實作（預設 cp = CPython）")
    ap.add_argument("--abi", default=None, help="ABI tag（預設由 --python-version 推出，例 cp39）")
    ap.add_argument("--requirements", default=os.path.join(repo, "requirements.txt"),
                    help="requirements.txt 路徑")
    ap.add_argument("--include-pytest", action="store_true",
                    help="連 pytest 一起抓（想在公司機跑測試才需要）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只印出將要執行的 pip 指令，不真的下載")
    args = ap.parse_args(list(argv) if argv is not None else None)

    platforms = args.platform or [DEFAULT_PLATFORM]
    abi = args.abi or default_abi(args.python_version, args.implementation)
    dest = os.path.abspath(args.dest)

    if not os.path.isfile(args.requirements):
        print("[錯誤] 找不到 requirements 檔：%s" % args.requirements, file=sys.stderr)
        print("       請在 ADEPT 專案資料夾裡執行，或用 --requirements 指定路徑。", file=sys.stderr)
        return 2
    try:
        req_names = parse_requirements(args.requirements)
    except OSError as exc:
        print("[錯誤] 讀不到 requirements 檔：%s" % exc, file=sys.stderr)
        return 2
    if not req_names:
        print("[錯誤] %s 裡沒有任何套件。" % args.requirements, file=sys.stderr)
        return 2

    extra: List[str] = ["pytest"] if args.include_pytest else []
    all_reqs = req_names + extra

    cmd = build_pip_command(dest=dest, requirements=args.requirements,
                            platforms=platforms, python_version=args.python_version,
                            implementation=args.implementation, abi=abi,
                            extra_packages=extra)

    print("ADEPT 離線 wheels 下載")
    print("  目標平台      ：%s" % ", ".join(platforms))
    print("  目標 Python   ：%s（abi %s、implementation %s）"
          % (args.python_version, abi, args.implementation))
    print("  要抓的套件    ：%s" % ", ".join(all_reqs))
    print("  存放資料夾    ：%s" % dest)
    print("")
    print("將執行：")
    print("  " + " ".join(cmd))

    if args.dry_run:
        print("\n（--dry-run：沒有真的下載。）")
        return 0

    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as exc:
        print("\n[錯誤] 建不了資料夾 %s：%s" % (dest, exc), file=sys.stderr)
        return 2

    print("\n下載中（第一次要幾分鐘，PySide6 就有 100 MB 以上）…\n")
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        print("[錯誤] 叫不動 pip：%s" % exc, file=sys.stderr)
        return 2
    output = (proc.stdout or b"").decode("utf-8", "replace")
    print(output.rstrip())

    if proc.returncode != 0:
        print("\n[錯誤] pip download 失敗（回傳碼 %d）。" % proc.returncode, file=sys.stderr)
        for tip in explain_pip_failure(output, platform=platforms[0],
                                       python_version=args.python_version):
            print("  · " + tip, file=sys.stderr)
        return 1

    # ---- 下載後驗證 ----
    wheels, sdists = scan_dest(dest)
    total = print_table(dest, wheels)

    problems = 0
    matched = match_requirements(all_reqs, wheels)
    missing = [r for r, files in matched.items() if not files]
    if missing:
        problems += 1
        print("\n[錯誤] 這些套件沒有抓到任何 .whl：%s" % ", ".join(missing), file=sys.stderr)
        print("       公司機會裝不起來。請確認 --python-version / --platform 是否正確。",
              file=sys.stderr)
    if sdists:
        problems += 1
        print("\n[警告] 資料夾裡有 %d 個原始碼包（不是 wheel）：%s"
              % (len(sdists), ", ".join(sdists)), file=sys.stderr)
        print("       原始碼包在公司機需要 C 編譯器才裝得起來，幾乎一定會失敗。",
              file=sys.stderr)
        print("       請改用有提供 wheel 的版本，或請 IT 從內部鏡像站取得。", file=sys.stderr)

    manifest_path = os.path.join(dest, MANIFEST_NAME)
    try:
        _atomic_write(manifest_path, build_manifest_text(
            wheels=wheels, dest=dest, platforms=platforms,
            python_version=args.python_version, implementation=args.implementation,
            abi=abi, requirements_path=args.requirements, requirement_names=all_reqs))
    except OSError as exc:
        print("\n[錯誤] 寫不出 MANIFEST.txt：%s" % exc, file=sys.stderr)
        return 1
    print("\n→ 已寫出清單：%s" % manifest_path)
    print("  （裡面有每個檔案的 sha256 與目標平台／Python，可以直接給 IT 看。）")

    if problems:
        print("\n結論：下載完成但**有問題**，請先處理上面的錯誤或警告。")
        return 1

    print("\n結論：%d 個 wheel、共 %s，全部齊全。" % (len(wheels), _human_size(total)))
    print("下一步：把整個 %s 資料夾連同 ADEPT 原始碼帶到公司機，然後執行" % os.path.basename(dest))
    print("        python tools\\install_offline.py --wheels %s" % os.path.basename(dest))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
