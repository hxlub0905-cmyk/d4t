#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ADEPT offline packaging tool #2 — authored 2026-07-28 (M6-1).
"""在**沒有網路的公司機**上，用離線 wheels 資料夾把 ADEPT 的相依套件裝起來。

用法（在解壓後的 ADEPT 資料夾裡執行）：
    python tools\\install_offline.py                       # 用 wheels\\，裝進 .venv\\
    python tools\\install_offline.py --wheels D:\\adept_wheels
    python tools\\install_offline.py --no-venv             # 不建虛擬環境，直接裝進現在這個 Python
    python tools\\install_offline.py --no-venv --user      # 沒有系統管理權限時
    python tools\\install_offline.py --dry-run             # 只做事前檢查、印出指令，不真的安裝

它做的事：
    1. 事前檢查（這一段最重要，八成的失敗都擋在這裡，而且會用白話告訴你怎麼修）
    2. 建立虛擬環境 .venv（可用 --no-venv 跳過）
    3. pip install --no-index --find-links=wheels -r requirements.txt
    4. 自動跑 tools/doctor.py 驗收，並印出下一步要打的指令

本檔**只用標準函式庫**：它要在「什麼套件都還沒裝」的機器上跑。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

MANIFEST_NAME = "MANIFEST.txt"
MIN_PYTHON = (3, 9)
# 安裝過程需要的餘裕：wheel 解開後大約是原檔的 2~3 倍（PySide6 尤其肥）
SPACE_FACTOR = 3.0
SPACE_MARGIN_BYTES = 150 * 1024 * 1024

PLATFORM_TAG_HINT = {
    "win32": "win_amd64 / win32",
    "linux": "manylinux*",
    "darwin": "macosx_*",
}


# ---------------------------------------------------------------- 小工具

def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0 or unit == "GB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%.1f GB" % n


def running_python_tag() -> str:
    """目前這個 Python 的版本 tag：3.9 → ``39``、3.11 → ``311``。"""
    return "%d%d" % (sys.version_info[0], sys.version_info[1])


def parse_python_tag(value: str) -> Optional[Tuple[int, int]]:
    """``39`` / ``3.9`` / ``cp39`` / ``py311`` → (3, 9) / (3, 11)；認不出來回 None。"""
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    if len(digits) < 2:
        return None
    return (int(digits[0]), int(digits[1:]))


def parse_manifest(path: str) -> Dict[str, str]:
    """讀 fetch_wheels.py 產生的 MANIFEST.txt 表頭（``key: value``）。讀不到回空 dict。"""
    info: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().endswith(".whl") or " " in line.split(":")[0]:
                    continue          # 檔案表格那一段，不是表頭
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip().lower()
                    if re.match(r"^[a-z_]+$", key):
                        info[key] = val.strip()
    except OSError:
        return {}
    return info


def find_wheels(wheels_dir: str) -> List[str]:
    try:
        return sorted(fn for fn in os.listdir(wheels_dir) if fn.lower().endswith(".whl"))
    except OSError:
        return []


def wheel_python_tags(filename: str) -> List[str]:
    """從 wheel 檔名取出 python tag（``numpy-2.0-cp39-cp39-win_amd64.whl`` → ['cp39']）。"""
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        return []
    return [t for t in parts[-3].split(".") if t]


def wheels_are_pure_python(wheels: Sequence[str]) -> bool:
    """整包都是 ``py3-none-any`` 這種與版本無關的 wheel？（那版本不合也裝得起來）"""
    if not wheels:
        return False
    for fn in wheels:
        for tag in wheel_python_tags(fn):
            if tag.startswith("cp") or re.match(r"^py3\d+$", tag):
                return False
    return True


def build_pip_install_command(python_exe: str, wheels_dir: str, requirements: str,
                              *, user: bool = False,
                              extra_packages: Sequence[str] = ()) -> List[str]:
    """組出離線安裝指令（純函式，方便測試）。"""
    cmd = [python_exe, "-m", "pip", "install",
           "--no-index", "--find-links", wheels_dir,
           "-r", requirements]
    if user:
        cmd.append("--user")
    cmd += list(extra_packages)
    return cmd


def venv_python(venv_dir: str) -> str:
    """虛擬環境裡 python.exe / bin/python 的路徑。"""
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def _existing_ancestor(path: str) -> str:
    path = os.path.abspath(path)
    while path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path or os.path.abspath(os.sep)


# ---------------------------------------------------------------- 事前檢查

class PreflightError(Exception):
    """事前檢查沒過。訊息是給使用者看的白話說明（多行）。"""


def _fail(title: str, *lines: str) -> "PreflightError":
    return PreflightError("\n".join(["[錯誤] " + title] + ["       " + ln for ln in lines]))


def preflight(*, wheels_dir: str, requirements: str, venv_dir: Optional[str],
              force: bool = False, user: bool = False) -> List[str]:
    """全部事前檢查。過不了就 raise PreflightError；回傳「提醒」字串清單。"""
    notes: List[str] = []

    # --- 0. Python 本身 ---
    if sys.version_info[:2] < MIN_PYTHON:
        raise _fail(
            "這台機器的 Python 是 %d.%d，ADEPT 需要 %d.%d 以上。"
            % (sys.version_info[0], sys.version_info[1], MIN_PYTHON[0], MIN_PYTHON[1]),
            "請改用比較新的 Python（在「開始」功能表搜尋 Python 看看有沒有裝多個版本），",
            "再用那個版本執行：C:\\Python311\\python.exe tools\\install_offline.py")

    # --- 1. requirements.txt ---
    if not os.path.isfile(requirements):
        raise _fail(
            "找不到 requirements.txt：%s" % requirements,
            "你可能不在 ADEPT 的資料夾裡。請先切換到解壓出來的資料夾（裡面看得到 adept\\ 與 tools\\）：",
            "    cd C:\\...\\ADEPT-main",
            "    python tools\\install_offline.py")

    # --- 2. wheels 資料夾存在 ---
    if not os.path.isdir(wheels_dir):
        raise _fail(
            "找不到離線套件資料夾：%s" % wheels_dir,
            "這個資料夾要在**有網路的機器**上先產生，做法：",
            "    python tools\\fetch_wheels.py --python-version %s" % running_python_tag(),
            "然後把整個 wheels 資料夾拷貝到這台機器、放在 ADEPT 資料夾底下，再跑一次本指令。",
            "若資料夾放在別的地方，請用 --wheels 指定，例如：--wheels D:\\adept_wheels")

    # --- 3. wheels 資料夾非空 ---
    wheels = find_wheels(wheels_dir)
    if not wheels:
        others = []
        try:
            others = sorted(os.listdir(wheels_dir))[:5]
        except OSError:
            pass
        raise _fail(
            "資料夾 %s 裡面沒有任何 .whl 檔。" % wheels_dir,
            "看到的內容：%s" % (("、".join(others) or "（空的）")),
            "常見原因：拷貝時只複製了資料夾外殼、或防毒/DLP 把 .whl 檔擋掉了（.whl 其實是 zip）。",
            "請回到有網路的機器重新執行 python tools\\fetch_wheels.py，並確認 wheels 資料夾裡有一堆 .whl。")

    # --- 4. Python 版本 vs wheels 版本（最常見的失敗，一定要擋在 pip 之前） ---
    manifest_path = os.path.join(wheels_dir, MANIFEST_NAME)
    manifest = parse_manifest(manifest_path) if os.path.isfile(manifest_path) else {}
    target = parse_python_tag(manifest.get("target_python", ""))
    if target is None:
        tags = [t for fn in wheels for t in wheel_python_tags(fn)]
        cps = sorted({t for t in tags if t.startswith("cp")})
        if cps:
            target = parse_python_tag(cps[0])
    running = sys.version_info[:2]
    if target and tuple(target) != tuple(running):
        if wheels_are_pure_python(wheels):
            notes.append("MANIFEST 說這批 wheel 是給 Python %d.%d 的，但它們與版本無關（py3-none-any），"
                         "所以照樣可以裝。" % target)
        elif force:
            notes.append("Python 版本與 wheels 不合（wheels 給 %d.%d，這台是 %d.%d），"
                         "但你加了 --force，繼續。" % (target[0], target[1], running[0], running[1]))
        else:
            raise _fail(
                "Python 版本對不上：這批 wheel 是給 Python %d.%d 用的，"
                "但你現在跑的是 Python %d.%d。" % (target[0], target[1], running[0], running[1]),
                "cp%d%d 的 wheel 在 Python %d.%d 上一定裝不起來（pip 會說 "
                "\"is not a supported wheel on this platform\"）。"
                % (target[0], target[1], running[0], running[1]),
                "二選一：",
                "  (A) 用對的 Python 跑本指令 —— 如果這台機器裝了 Python %d.%d，改成："
                % (target[0], target[1]),
                "      C:\\Python%d%d\\python.exe tools\\install_offline.py --wheels %s"
                % (target[0], target[1], wheels_dir),
                "  (B) 回到有網路的機器，重抓符合這台機器的 wheels：",
                "      python tools\\fetch_wheels.py --python-version %s" % running_python_tag(),
                "（清單檔：%s）" % manifest_path)

    # --- 5. 平台 tag（只提醒，不擋） ---
    target_plat = manifest.get("target_platform", "")
    if target_plat:
        expect = PLATFORM_TAG_HINT.get(sys.platform, sys.platform)
        first = target_plat.split(",")[0].strip()
        if first and not any(k in first for k in expect.replace("*", "").split(" / ")):
            notes.append("這批 wheel 標的平台是 %s，但這台機器看起來是 %s（%s）；"
                         "若 pip 說 not a supported wheel，請重抓對應平台的 wheels。"
                         % (target_plat, sys.platform, expect))

    # --- 6. 磁碟空間 ---
    total = 0
    for fn in wheels:
        try:
            total += os.path.getsize(os.path.join(wheels_dir, fn))
        except OSError:
            pass
    need = int(total * SPACE_FACTOR) + SPACE_MARGIN_BYTES
    where = _existing_ancestor(venv_dir or os.getcwd())
    try:
        free = shutil.disk_usage(where).free
    except OSError:
        free = None
    if free is not None and free < need:
        raise _fail(
            "磁碟空間不夠：%s 只剩 %s，安裝大約需要 %s。" % (where, human_size(free), human_size(need)),
            "PySide6 解開後就要幾百 MB。請清出空間，或把 ADEPT 放到空間夠的磁碟",
            "（例如 D:\\），再用 --venv D:\\adept_venv 指定虛擬環境位置。")

    # --- 7. 寫入權限 ---
    target_dir = _existing_ancestor(venv_dir) if venv_dir else os.getcwd()
    if not os.access(target_dir, os.W_OK):
        raise _fail(
            "沒有寫入權限：%s" % target_dir,
            "請把 ADEPT 解壓到你自己的資料夾（例如 C:\\Users\\你的帳號\\ADEPT-main），",
            "不要放在 C:\\Program Files、系統磁碟根目錄或唯讀的網路磁碟。")

    if user and venv_dir:
        notes.append("--user 只有搭配 --no-venv 才有意義（虛擬環境裡不需要）；這次會忽略它。")
    return notes


# ---------------------------------------------------------------- 建 venv

def create_venv(venv_dir: str) -> Tuple[bool, str]:
    """建立虛擬環境。回傳 (是否成功, 訊息)。已存在就直接沿用。"""
    py = venv_python(venv_dir)
    if os.path.isfile(py):
        return True, "沿用已存在的虛擬環境：%s" % venv_dir
    cmd = [sys.executable, "-m", "venv", venv_dir]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        return False, "叫不動 python -m venv：%s" % exc
    out = (proc.stdout or b"").decode("utf-8", "replace")
    if proc.returncode == 0 and os.path.isfile(py):
        return True, "已建立虛擬環境：%s" % venv_dir
    return False, out.strip() or "python -m venv 回傳碼 %d（沒有任何訊息）" % proc.returncode


def explain_venv_failure(message: str, venv_dir: str) -> List[str]:
    """把建 venv 的失敗翻成白話與可行的替代方案。"""
    low = (message or "").lower()
    tips: List[str] = []
    if "ensurepip" in low or "pip" in low:
        tips.append("這台機器的 Python 把 ensurepip 拿掉了（公司統一安裝的映像常見）。")
    elif "no module named venv" in low:
        tips.append("這個 Python 沒有內建 venv 模組。")
    elif "permission" in low or "denied" in low or "errno 13" in low:
        tips.append("沒有權限在 %s 建立資料夾。" % os.path.dirname(os.path.abspath(venv_dir)))
    tips.append("改用不建虛擬環境的方式安裝：")
    tips.append("    python tools\\install_offline.py --no-venv")
    tips.append("如果連系統目錄都不能寫，再加 --user（裝到你自己的帳號底下）：")
    tips.append("    python tools\\install_offline.py --no-venv --user")
    return tips


# ---------------------------------------------------------------- pip 失敗翻譯

def explain_pip_failure(output: str, wheels_dir: str) -> List[str]:
    low = (output or "").lower()
    tips: List[str] = []
    if "not a supported wheel on this platform" in low:
        tips.append("wheel 的 Python 版本或平台跟這台機器不合。"
                    "請在有網路的機器重抓：python tools\\fetch_wheels.py --python-version %s"
                    % running_python_tag())
    if "no matching distribution" in low or "could not find a version" in low:
        tips.append("%s 裡缺了某個相依套件（pip 會把缺的名字印在上面）。" % wheels_dir)
        tips.append("請回到有網路的機器重跑 fetch_wheels.py，把整個 wheels 資料夾重新帶過來"
                    "（不要只挑幾個檔案複製）。")
    if "no module named pip" in low:
        tips.append("這個 Python 沒有 pip。請試 python -m ensurepip --default-pip，"
                    "或請 IT 幫忙裝一個完整的 Python。")
    if "permission" in low or "access is denied" in low:
        tips.append("權限不足。請加 --no-venv --user，或把 ADEPT 移到你自己的資料夾再試。")
    if "proxy" in low or "connection" in low or "timed out" in low or "ssl" in low:
        tips.append("看起來 pip 還是想連網。--no-index 已經關掉連網了，"
                    "若仍出現這種訊息，請檢查有沒有 pip.ini 設了 index-url，"
                    "或加環境變數 PIP_NO_INDEX=1 後重試。")
    if not tips:
        tips.append("請把上面 pip 的訊息整段回報（最後 10 行最重要）。")
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
        prog="install_offline.py",
        description="在沒有網路的機器上，用離線 wheels 資料夾安裝 ADEPT 的相依套件。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="範例：\n"
               "  python tools\\install_offline.py\n"
               "  python tools\\install_offline.py --wheels D:\\adept_wheels --venv D:\\adept_venv\n"
               "  python tools\\install_offline.py --no-venv --user\n")
    ap.add_argument("--wheels", default="wheels", help="離線 wheel 資料夾（預設 wheels）")
    ap.add_argument("--venv", default=".venv", help="虛擬環境資料夾（預設 .venv）")
    ap.add_argument("--no-venv", action="store_true",
                    help="不建虛擬環境，直接裝進目前這個 Python")
    ap.add_argument("--user", action="store_true",
                    help="搭配 --no-venv：裝到使用者目錄（沒有系統管理權限時用）")
    ap.add_argument("--requirements", default=os.path.join(repo, "requirements.txt"),
                    help="requirements.txt 路徑")
    ap.add_argument("--force", action="store_true",
                    help="即使 Python 版本與 wheels 不合也硬裝（不建議）")
    ap.add_argument("--include-pytest", action="store_true",
                    help="連 pytest 一起裝（wheels 資料夾裡要有；抓的時候也要加 --include-pytest）")
    ap.add_argument("--skip-doctor", action="store_true", help="安裝完不要自動跑環境自檢")
    ap.add_argument("--dry-run", action="store_true",
                    help="只做事前檢查並印出指令，不真的安裝")
    args = ap.parse_args(list(argv) if argv is not None else None)

    wheels_dir = os.path.abspath(args.wheels)
    venv_dir = None if args.no_venv else os.path.abspath(args.venv)
    requirements = os.path.abspath(args.requirements)

    print("ADEPT 離線安裝")
    print("  Python      ：%s（%s）" % (".".join(str(x) for x in sys.version_info[:3]),
                                      sys.executable))
    print("  wheels 資料夾：%s" % wheels_dir)
    print("  安裝到      ：%s" % (venv_dir or "目前這個 Python（--no-venv）"))
    print("")
    print("[1/4] 事前檢查…")
    try:
        notes = preflight(wheels_dir=wheels_dir, requirements=requirements,
                          venv_dir=venv_dir, force=args.force, user=args.user)
    except PreflightError as exc:
        print("")
        print(str(exc), file=sys.stderr)
        print("")
        print("（安裝沒有開始，什麼都沒有被改動。）", file=sys.stderr)
        return 2
    wheels = find_wheels(wheels_dir)
    total = sum(os.path.getsize(os.path.join(wheels_dir, fn)) for fn in wheels
                if os.path.isfile(os.path.join(wheels_dir, fn)))
    print("      ✓ 通過（%d 個 wheel，共 %s）" % (len(wheels), human_size(total)))
    for n in notes:
        print("      △ %s" % n)

    # --- 2. venv ---
    if venv_dir:
        print("\n[2/4] 建立虛擬環境 %s …" % venv_dir)
        if args.dry_run:
            print("      （--dry-run：跳過）")
            py_exe = venv_python(venv_dir)
        else:
            ok, msg = create_venv(venv_dir)
            if not ok:
                print("\n[錯誤] 建立虛擬環境失敗。", file=sys.stderr)
                print("       原始訊息：%s" % msg.replace("\n", "\n                 "),
                      file=sys.stderr)
                for tip in explain_venv_failure(msg, venv_dir):
                    print("       " + tip, file=sys.stderr)
                return 2
            print("      ✓ %s" % msg)
            py_exe = venv_python(venv_dir)
    else:
        print("\n[2/4] 不建虛擬環境（--no-venv），直接用目前的 Python。")
        py_exe = sys.executable

    # --- 3. pip install ---
    extra: List[str] = []
    if args.include_pytest:
        if any(fn.lower().startswith("pytest-") for fn in wheels):
            extra.append("pytest")
        else:
            print("      △ --include-pytest：%s 裡沒有 pytest 的 wheel，這次不裝它。"
                  % wheels_dir)
    cmd = build_pip_install_command(py_exe, wheels_dir, requirements,
                                    user=bool(args.user and not venv_dir),
                                    extra_packages=extra)
    print("\n[3/4] 安裝套件…")
    print("      " + " ".join(cmd))
    if args.dry_run:
        print("\n（--dry-run：事前檢查已通過，沒有真的安裝。）")
        return 0
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        print("\n[錯誤] 叫不動 pip：%s" % exc, file=sys.stderr)
        print("       這個 Python 可能沒有 pip，請試 python -m ensurepip --default-pip。",
              file=sys.stderr)
        return 1
    out = (proc.stdout or b"").decode("utf-8", "replace")
    print(out.rstrip())
    if proc.returncode != 0:
        print("\n[錯誤] pip 安裝失敗（回傳碼 %d）。" % proc.returncode, file=sys.stderr)
        for tip in explain_pip_failure(out, wheels_dir):
            print("  · " + tip, file=sys.stderr)
        return 1
    print("      ✓ 套件安裝完成")

    # --- 4. doctor ---
    doctor = os.path.join(repo, "tools", "doctor.py")
    skipped_doctor = args.skip_doctor or not os.path.isfile(doctor)
    if skipped_doctor:
        rc = 0
        print("\n[4/4] 略過環境自檢。")
    else:
        print("\n[4/4] 環境自檢（tools/doctor.py）…\n")
        try:
            rc = subprocess.call([py_exe, doctor], cwd=repo)
        except OSError as exc:
            print("[警告] 跑不起來環境自檢：%s" % exc, file=sys.stderr)
            rc = 1

    print("\n" + "=" * 60)
    if skipped_doctor:
        print("套件安裝完成（這次沒有跑環境自檢）。建議跑一次：python tools\\doctor.py")
        print("接下來：")
    elif rc == 0:
        print("安裝完成，環境自檢通過。接下來：")
    else:
        print("套件裝好了，但環境自檢有項目沒過（見上面的 ✗ 與修正建議）。修好後再跑：")
        print("    python tools\\doctor.py --verbose")
        print("接下來（自檢過了才會正常）：")
    if venv_dir:
        rel = os.path.relpath(venv_dir, repo) if venv_dir.startswith(repo) else venv_dir
        if os.name == "nt":
            print("    %s\\Scripts\\activate          ← 每次開新的命令列都要先做這一步" % rel)
            print("      （PowerShell 版：%s\\Scripts\\Activate.ps1）" % rel)
        else:
            print("    source %s/bin/activate      ← 每次開新的終端機都要先做這一步" % rel)
            print("      （Windows 版：%s\\Scripts\\activate）" % rel)
    print("    python -m adept gui                 ← 開圖形介面 Studio")
    print("    python tools\\make_sample.py C:\\temp\\lot --n 100   ← 產一份合成資料試玩")
    print("=" * 60)
    return 0 if rc == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
