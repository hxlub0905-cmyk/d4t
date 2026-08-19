#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# d4t offline packaging tool #3 — authored 2026-07-28 (M6-1).
"""d4t 環境自檢（doctor）：一次告訴你「這台機器能不能跑 d4t」。

用法：
    python tools/doctor.py            # 在 d4t 專案資料夾裡執行
    python tools/doctor.py --verbose  # 連錯誤細節一起印
    python tools/doctor.py --skip-smoke   # 不跑最後的端到端試跑（省 10 秒）

檢查項目（每項都會給一行「怎麼修」）：
    1. Python 版本 >= 3.9、是不是 64 位元
    2. numpy / opencv-python(cv2) / tifffile / PySide6 / openpyxl 能不能 import、版本多少
       （pytest 是選用的，缺了只給提醒）
    3. 從**目前這個資料夾**能不能 import 到 d4t —— 最常見的錯是「跑錯資料夾」
    4. PySide6 能不能真的開一個 QApplication（用子行程做，避免整支 doctor 被拖死）
    5. 目前資料夾與快取資料夾 ~/.d4t 有沒有寫入權限
    6. 端到端試跑：產一份迷你合成 lot，用**內建的**最小 pipeline 跑一顆 defect
       （約 10 秒；不讀 repo 裡任何 recipe 檔，見 ``_SMOKE_RECIPE``）

離開碼：必要項目全過 = 0，否則 = 1。最後一行永遠是一句白話結論。

本檔在「相依套件還沒裝好」時也必須能跑，所以**模組層只 import 標準函式庫**；
第三方套件一律在函式內部 lazy import 或丟到子行程裡驗。
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
from typing import List, Optional, Sequence, Tuple

MIN_PYTHON = (3, 9)
CACHE_DIR_NAME = ".d4t"

# 相依套件： (pip 上的名字, import 用的名字, 是否必要)
DEPENDENCIES: Tuple[Tuple[str, str, bool], ...] = (
    ("numpy", "numpy", True),
    ("opencv-python", "cv2", True),
    ("tifffile", "tifffile", True),
    ("openpyxl", "openpyxl", True),
    ("PySide6", "PySide6", True),
    ("pytest", "pytest", False),
)

OK, WARN, BAD = "ok", "warn", "bad"

_MARKS = {OK: "✓", WARN: "△", BAD: "✗"}
_MARKS_ASCII = {OK: "[OK]", WARN: "[!!]", BAD: "[XX]"}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SMOKE_TIMEOUT_S = 180.0
QT_TIMEOUT_S = 90.0
_JSON_TAG = "D4T_DOCTOR_JSON:"


# ---------------------------------------------------------------- 輸出小工具

def _width(text: str) -> int:
    """顯示寬度：CJK 全形字算 2 格（不然表格會歪掉）。"""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _marks():
    """Big5/cp950 主控台可能吐不出 ✓✗△，吐不出來就退回純 ASCII。"""
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "".join(_MARKS.values()).encode(enc)
    except (UnicodeEncodeError, LookupError):
        return _MARKS_ASCII
    return _MARKS


class Report(object):
    """收集每一項檢查結果，最後印成表格。"""

    def __init__(self) -> None:
        self.rows: List[dict] = []

    def add(self, status: str, name: str, detail: str = "",
            hint: str = "", essential: bool = True, extra: str = "") -> str:
        self.rows.append({"status": status, "name": name, "detail": detail,
                          "hint": hint, "essential": essential, "extra": extra})
        return status

    def failures(self) -> List[dict]:
        return [r for r in self.rows if r["status"] == BAD and r["essential"]]

    def warnings(self) -> List[dict]:
        return [r for r in self.rows if r["status"] == WARN
                or (r["status"] == BAD and not r["essential"])]

    def render(self, verbose: bool = False) -> None:
        marks = _marks()
        w_mark = max(_width(m) for m in marks.values())
        w_name = max([4] + [_width(r["name"]) for r in self.rows])
        print("")
        for r in self.rows:
            print("  %s %s  %s" % (_pad(marks[r["status"]], w_mark),
                                   _pad(r["name"], w_name), r["detail"]))
            if r["status"] != OK and r["hint"]:
                print("  %s   → 修正建議：%s" % (" " * w_mark, r["hint"]))
            if verbose and r["extra"]:
                for line in str(r["extra"]).rstrip().splitlines():
                    print("      | %s" % line)


# ---------------------------------------------------------------- 子行程腳本

_QT_CHILD = r"""
import json, os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
out = {"import_ok": False, "version": None, "app_ok": False, "error": None}
try:
    import PySide6
    out["import_ok"] = True
    out["version"] = getattr(PySide6, "__version__", None)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    out["app_ok"] = True
except BaseException as exc:
    out["error"] = "%s: %s" % (type(exc).__name__, exc)
sys.stdout.write("D4T_DOCTOR_JSON:" + json.dumps(out) + "\n")
"""

#: 端到端試跑用的 pipeline —— **doctor 自己帶著，不讀 repo 裡任何 recipe 檔**。
#:
#: 以前這裡讀 ``examples/recipes/die_to_die_basic.json``。那份檔案 2026-08-14
#: 被刪掉之後，doctor 對每一台機器都說「找不到範例 recipe → 原始碼解壓不完整，
#: 請重新解壓一次」—— 一個**錯的診斷**，而 doctor 存在的唯一理由就是在裝不起來
#: 的機器上給出對的診斷。第一次裝的人會照著重解壓一次，然後看到同一句話。
#:
#: 所以它不再依賴任何外部檔案：這四張卡（載入 → 相減 → 量 → 給分）就是
#: 「引擎從頭到尾跑得完」的最小證據，而那正是這一項要回答的問題。
_SMOKE_RECIPE = {
    "recipe_id": "doctor_smoke",
    "version": 2,
    "description": "doctor 內建的最小 pipeline（不是給使用者看的範例）。",
    "routes": {"ebi_patch": ["load", "sub", "glv"]},
    "nodes": {
        "load": {"step": "load_patch", "params": {}, "enabled": True},
        "sub": {"step": "subtract", "params": {"b": "ref"}, "enabled": True},
        "glv": {"step": "glv_stats",
                "params": {"source": "diff", "metrics": "glv_max,glv_mean",
                           "roi": ""},
                "enabled": True},
    },
    "edges": [],
    "score": {"expr": "glv_max", "threshold": 50.0,
              "bins": {"below": 0, "above": 1}},
}

_SMOKE_CHILD = r"""
import json, os, shutil, sys, tempfile
root = sys.argv[1]
recipe_json = sys.argv[2]
sys.path.insert(0, root)
sys.path.insert(1, os.path.join(root, "tools"))
out = {"ok": False, "error": None, "score": None, "kind": None, "n_features": 0}
work = None
try:
    import make_sample
    import d4t.core.steps  # noqa: F401  觸發卡片註冊
    from d4t.core.ingest.dataset import load_dataset
    from d4t.core.pipeline import Recipe, run_defect

    work = tempfile.mkdtemp(prefix="d4t_doctor_")
    info = make_sample.generate(os.path.join(work, "lot"), n=2, seed=7)
    ds = load_dataset(info["klarf"])
    out["kind"] = ds.kind
    recipe = Recipe.from_json_dict(json.loads(recipe_json))
    res = run_defect(recipe, ds.items[0], ds.kind)
    out["ok"] = bool(res.ok) and res.score is not None
    out["error"] = res.error
    out["score"] = res.score
    out["n_features"] = len(res.features or {})
except BaseException as exc:
    out["error"] = "%s: %s" % (type(exc).__name__, exc)
finally:
    if work:
        shutil.rmtree(work, ignore_errors=True)
sys.stdout.write("D4T_DOCTOR_JSON:" + json.dumps(out) + "\n")
"""


def _run_child(code: str, args: Sequence[str], timeout: float,
               cwd: Optional[str] = None) -> Tuple[Optional[dict], str]:
    """跑一段子行程並抓回它印的 JSON。回傳 (資料 or None, 原始輸出)。"""
    cmd = [sys.executable, "-c", code] + list(args)
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout, cwd=cwd, env=env)
    except subprocess.TimeoutExpired:
        return None, "子行程超過 %.0f 秒沒有結束（timeout）。" % timeout
    except OSError as exc:
        return None, "叫不動子行程：%s" % exc
    text = (proc.stdout or b"").decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith(_JSON_TAG):
            try:
                return json.loads(line[len(_JSON_TAG):]), text
            except ValueError:
                break
    tail = text.strip() or "（子行程沒有任何輸出）"
    return None, "子行程異常結束（回傳碼 %d）：\n%s" % (proc.returncode, tail)


# ---------------------------------------------------------------- 各項檢查

def check_python(rep: Report) -> None:
    vi = sys.version_info
    ver = "%d.%d.%d" % (vi[0], vi[1], vi[2])
    if vi[:2] >= MIN_PYTHON:
        rep.add(OK, "Python 版本", "%s（需要 >= %d.%d）" % (ver, MIN_PYTHON[0], MIN_PYTHON[1]),
                extra=sys.executable)
    else:
        rep.add(BAD, "Python 版本", "%s 太舊（需要 >= %d.%d）" % (ver, MIN_PYTHON[0], MIN_PYTHON[1]),
                hint="請改用 Python %d.%d 以上；公司機通常在「開始→Python」裡可以選版本。"
                     % (MIN_PYTHON[0], MIN_PYTHON[1]),
                extra=sys.executable)

    bits = struct.calcsize("P") * 8
    if bits >= 64:
        rep.add(OK, "Python 位元數", "64 位元")
    else:
        rep.add(WARN, "Python 位元數", "32 位元", essential=False,
                hint="PySide6/opencv 幾乎只出 64 位元 wheel；請改裝 64 位元的 Python。")


def check_dependencies(rep: Report, verbose: bool = False) -> bool:
    """回傳「必要套件是否全部 import 成功」。PySide6 只在這裡看版本，實際能否開視窗由 Qt 檢查負責。"""
    all_ok = True
    for pip_name, import_name, essential in DEPENDENCIES:
        try:
            mod = __import__(import_name)
            ver = getattr(mod, "__version__", None) or _dist_version(pip_name) or "（版本不明）"
            rep.add(OK, "套件 %s" % pip_name, "%s → import %s 成功" % (ver, import_name))
        except BaseException as exc:  # noqa: BLE001 — 什麼爛事都可能發生
            detail = "import %s 失敗：%s" % (import_name, type(exc).__name__)
            if essential:
                all_ok = False
                rep.add(BAD, "套件 %s" % pip_name, detail,
                        hint="離線安裝：python tools\\install_offline.py --wheels wheels"
                             "（或有網路時 pip install %s）" % pip_name,
                        extra="%s: %s" % (type(exc).__name__, exc))
            else:
                rep.add(WARN, "套件 %s" % pip_name, detail + "（選用）", essential=False,
                        hint="只有要跑測試才需要：pip install pytest（離線時加 --include-pytest 抓）",
                        extra="%s: %s" % (type(exc).__name__, exc))
    return all_ok


def _dist_version(pip_name: str) -> Optional[str]:
    try:
        from importlib import metadata  # Python 3.8+
        return metadata.version(pip_name)
    except Exception:  # noqa: BLE001
        return None


def check_d4t_importable(rep: Report) -> bool:
    """從**目前工作資料夾**能不能 import d4t —— 專治「跑錯資料夾」。"""
    cwd = os.getcwd()
    has_dir = os.path.isdir(os.path.join(cwd, "d4t"))
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    try:
        import d4t  # noqa: F401
        where = os.path.dirname(os.path.abspath(d4t.__file__ or ""))
        rep.add(OK, "d4t 套件", "可以載入（%s）" % where)
        return True
    except BaseException as exc:  # noqa: BLE001
        if has_dir:
            hint = ("目前資料夾裡有 d4t\\，但載入失敗 —— 通常是相依套件沒裝好"
                    "（看上面的套件檢查），或 d4t\\ 裡的檔案不完整（請重新解壓一次原始碼 zip）。")
        else:
            hint = ("你跑錯資料夾了。請先 cd 到「裡面看得到 d4t\\ 這個資料夾」的地方"
                    "（解壓後通常是 d4t-main\\），再執行一次："
                    "cd C:\\...\\d4t-main 然後 python tools\\doctor.py")
        rep.add(BAD, "d4t 套件", "在目前資料夾 %s 載入不到（%s）" % (cwd, type(exc).__name__),
                hint=hint, extra="%s: %s" % (type(exc).__name__, exc))
        return False


def check_qt(rep: Report) -> None:
    data, raw = _run_child(_QT_CHILD, [], QT_TIMEOUT_S)
    if data is None:
        rep.add(BAD, "Qt 圖形介面", "PySide6 檢查子行程沒有正常結束（可能是直接當掉）",
                hint="PySide6 裝壞了或缺系統元件：請重裝 PySide6，"
                     "Windows 上多半還要裝「Microsoft Visual C++ Redistributable 2015-2022 (x64)」。",
                extra=raw)
        return
    if not data.get("import_ok"):
        rep.add(BAD, "Qt 圖形介面", "PySide6 import 不起來",
                hint="離線安裝：python tools\\install_offline.py --wheels wheels；"
                     "若已安裝仍失敗，多半缺 VC++ Redistributable (x64)。",
                extra=data.get("error") or raw)
        return
    ver = data.get("version") or "（版本不明）"
    if data.get("app_ok"):
        rep.add(OK, "Qt 圖形介面", "PySide6 %s，QApplication 建得起來" % ver)
    else:
        rep.add(BAD, "Qt 圖形介面", "PySide6 %s 裝了，但開不了視窗" % ver,
                hint="請確認有裝 VC++ Redistributable (x64)；遠端桌面/無桌面環境可先設定"
                     " QT_QPA_PLATFORM=offscreen 只跑命令列模式（python -m d4t run ...）。",
                extra=data.get("error") or raw)


def _probe_write(path: str) -> Optional[str]:
    """試著在 path 底下寫一個暫存檔；成功回 None，失敗回錯誤字串。"""
    try:
        os.makedirs(path, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".d4t_write_test_", dir=path)
        os.close(fd)
        os.remove(tmp)
        return None
    except OSError as exc:
        return "%s: %s" % (type(exc).__name__, exc)


def check_write_permissions(rep: Report) -> None:
    cwd = os.getcwd()
    err = _probe_write(cwd)
    if err is None:
        rep.add(OK, "寫入權限（目前資料夾）", cwd)
    else:
        rep.add(BAD, "寫入權限（目前資料夾）", "不能寫入 %s" % cwd,
                hint="請把 d4t 解壓到你自己的資料夾（例如 C:\\Users\\你的帳號\\d4t-main），"
                     "不要放在 C:\\Program Files 或唯讀的網路磁碟。",
                extra=err)

    cache = os.path.join(os.path.expanduser("~"), CACHE_DIR_NAME)
    err = _probe_write(cache)
    if err is None:
        rep.add(OK, "寫入權限（快取 ~/.d4t）", cache)
    else:
        rep.add(BAD, "寫入權限（快取 ~/.d4t）", "不能寫入 %s" % cache,
                hint="家目錄被鎖住時，請改用 --cache 指定一個你寫得進去的資料夾"
                     "（例如 python -m d4t run ... --cache D:\\temp\\d4t_cache）。",
                extra=err)


def check_smoke(rep: Report, skip: bool = False, reason: str = "") -> None:
    if skip:
        rep.add(WARN, "端到端試跑", "略過（%s）" % (reason or "使用者指定"), essential=False,
                hint="上面的問題修好後，再跑一次 python tools\\doctor.py 就會做這項。")
        return
    t0 = time.time()
    data, raw = _run_child(_SMOKE_CHILD,
                           [REPO_ROOT, json.dumps(_SMOKE_RECIPE)],
                           SMOKE_TIMEOUT_S)
    dt = time.time() - t0
    if data is None:
        rep.add(BAD, "端到端試跑", "試跑子行程沒有正常結束（%.1f 秒）" % dt,
                hint="請把上面的錯誤訊息（加 --verbose 可看到完整內容）連同這台機器的 "
                     "Python 版本一起回報。",
                extra=raw)
        return
    if data.get("ok"):
        rep.add(OK, "端到端試跑", "合成 lot → 內建 pipeline → score=%.3f，%d 個特徵（%.1f 秒）"
                % (float(data.get("score") or 0.0), int(data.get("n_features") or 0), dt))
    else:
        rep.add(BAD, "端到端試跑", "跑得動但結果不對：%s" % (data.get("error") or "沒有算出 score"),
                hint="通常是相依套件版本太舊。請確認 numpy/opencv 版本符合 requirements.txt，"
                     "或重新離線安裝一次。",
                extra=raw)


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
    ap = argparse.ArgumentParser(
        prog="doctor.py",
        description="d4t 環境自檢：一次檢查 Python、相依套件、Qt、權限與端到端試跑。")
    ap.add_argument("--verbose", action="store_true", help="連錯誤細節（完整訊息）一起印出來")
    ap.add_argument("--skip-smoke", action="store_true", help="不跑最後的端到端試跑（省約 10 秒）")
    args = ap.parse_args(list(argv) if argv is not None else None)

    print("d4t 環境自檢（doctor）")
    print("  目前資料夾：%s" % os.getcwd())
    print("  Python    ：%s" % sys.executable)

    rep = Report()
    check_python(rep)
    deps_ok = check_dependencies(rep, verbose=args.verbose)
    d4t_ok = check_d4t_importable(rep)
    check_qt(rep)
    check_write_permissions(rep)

    skip_reason = ""
    if args.skip_smoke:
        skip_reason = "--skip-smoke"
    elif not deps_ok:
        skip_reason = "相依套件還沒裝齊"
    elif not d4t_ok:
        skip_reason = "d4t 套件載入不到"
    check_smoke(rep, skip=bool(skip_reason), reason=skip_reason)

    rep.render(verbose=args.verbose)

    fails = rep.failures()
    warns = rep.warnings()
    print("")
    if fails:
        print("結論：有 %d 項必要檢查沒過（%s），d4t 目前還不能跑；"
              "請照上面每一行的『修正建議』處理後，再執行一次 python tools\\doctor.py。"
              % (len(fails), "、".join(r["name"] for r in fails)))
        if not args.verbose:
            print("（想看完整錯誤訊息：python tools\\doctor.py --verbose）")
        return 1
    if warns:
        print("結論：必要項目全部通過，d4t 可以跑（有 %d 項非必要提醒，見上面的 △）。"
              "下一步：python -m d4t gui" % len(warns))
    else:
        print("結論：全部檢查通過，這台機器可以跑 d4t。下一步：python -m d4t gui")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
