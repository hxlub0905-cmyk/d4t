#!/usr/bin/env python3
# d4t 黃金值凍結 — authored 2026-08-16 (F9-0).
"""把現在算出來的 feature 表凍成一份 JSON，給重構當安全網。

    python tools/freeze_golden.py            # 寫出 tests/fixtures/golden/*.json
    python tools/freeze_golden.py --check    # 只比對，不寫檔（不一樣就回非零）

為什麼需要這支
--------------
F9（影像流綁在線上）要動的是引擎的地基。這種重構最危險的失敗**不是跑不動**
—— 跑不動當場就看得到。危險的是**跑得動、而答案悄悄變了**：測試全綠、
畫面正常，只有分數跟上禮拜不一樣，而沒有人會發現。

所以動地基之前先把「現在算出來的每一個數字」寫下來，之後每改一段就對一次。
驗收條件是**逐項相同**，不是「差不多」。

為什麼不放進預設的測試套件
--------------------------
這些是**浮點數**，會隨 numpy / OpenCV 的版本漂移。CI 跑 3.9/3.11/3.12 三種
環境，家用機又是另一種 —— committed 的值不可能在每一台都逐位元組相同。

而這份東西的用途本來就不是跨機器重現，是**同一台機器上、重構前後的比較**。
所以：

* 預設**不跑**（`tests/test_golden_features.py` 沒有 `D4T_GOLDEN=1` 就 skip）；
* 開始重構之前在**你自己的機器上**跑一次這支凍結；
* 每改完一段跑 `--check`；
* 數字真的該變的時候（例如刻意改了演算法），重新凍一次並在 commit 訊息裡說明。

本檔與 `tools/` 其他工具一樣是 stdlib-only 的入口，第三方套件都在函式內 lazy
import（`tests/test_offline_tools.py` 會掃）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO_ROOT, "tests", "fixtures", "golden")
RECIPE_DIR = os.path.join(REPO_ROOT, "tests", "fixtures", "recipes")

#: 凍哪幾份 recipe、用哪一種合成資料、幾顆、什麼 seed。
#:
#: seed 寫死是重點：黃金值必須對著**同一批圖**才有意義。
CASES = (
    # (recipe 檔名,            產生器,          n,  seed)
    ("die_to_die_basic.json", "make_sample", 8, 7),
    ("dual_route_basic.json", "make_sample", 8, 7),
    ("dual_route_basic.json", "make_sample_rsem", 6, 11),
)

#: 浮點數存成幾位有效數字。
#:
#: 存 repr 會把「這台機器的最後一個 bit」也寫進去，於是換一台機器必定不同而且
#: 看不出差在哪。17 位仍然遠比任何真實的行為改變精細 —— 重構如果動到數字，
#: 差的是第 3 位不是第 17 位。
FLOAT_FORMAT = "%.17g"


def _tag(recipe_file: str, gen: str) -> str:
    return "%s__%s" % (os.path.splitext(recipe_file)[0], gen)


def golden_path(recipe_file: str, gen: str) -> str:
    return os.path.join(GOLDEN_DIR, _tag(recipe_file, gen) + ".json")


def compute(recipe_file: str, gen: str, n: int, seed: int) -> dict:
    """跑一份 recipe，回傳可以逐項比對的結果（純資料，沒有時間/路徑）。"""
    import tempfile

    sys.path.insert(0, REPO_ROOT)
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import d4t.core.steps                                # noqa: F401
    from d4t.core.ingest.dataset import load_dataset
    from d4t.core.pipeline import Recipe, run_defect
    from d4t.core.pipeline.batch import pin_cv2_deterministic

    generator = __import__(gen)
    pin_cv2_deterministic()          # 沒有這行，IPP 會讓同一張圖每次差 1e-8

    work = tempfile.mkdtemp(prefix="d4t_golden_")
    info = generator.generate(os.path.join(work, "lot"), n=n, seed=seed)
    ds = load_dataset(info["klarf"])
    recipe = Recipe.load(os.path.join(RECIPE_DIR, recipe_file))
    if ds.kind not in recipe.routes:
        return {"skipped": "recipe 沒有 '%s' 這條 route" % ds.kind}

    defects = {}
    for item in ds.items:
        r = run_defect(recipe, item, ds.kind)
        defects[str(item.defect_id)] = {
            "ok": bool(r.ok),
            "error": r.error,
            "bin": r.bin,
            "score": None if r.score is None else FLOAT_FORMAT % float(r.score),
            "features": {k: FLOAT_FORMAT % float(v)
                         for k, v in sorted((r.features or {}).items())},
        }
    return {
        "recipe": recipe_file,
        "generator": gen,
        "n": n,
        "seed": seed,
        "kind": ds.kind,
        "defects": defects,
    }


def _dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _diff(old: dict, new: dict) -> list:
    """把兩份結果的差異列成人看得懂的行（空 list = 一模一樣）。"""
    out = []
    a, b = old.get("defects") or {}, new.get("defects") or {}
    if set(a) != set(b):
        out.append("defect 集合不同：只在舊的 %s；只在新的 %s"
                   % (sorted(set(a) - set(b)), sorted(set(b) - set(a))))
    for did in sorted(set(a) & set(b)):
        da, db = a[did], b[did]
        for field in ("ok", "error", "bin", "score"):
            if da.get(field) != db.get(field):
                out.append("defect %s 的 %s：%r → %r"
                           % (did, field, da.get(field), db.get(field)))
        fa, fb = da.get("features") or {}, db.get("features") or {}
        if set(fa) != set(fb):
            out.append("defect %s 的特徵名不同：少了 %s、多了 %s"
                       % (did, sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))))
        for name in sorted(set(fa) & set(fb)):
            if fa[name] != fb[name]:
                out.append("defect %s 的 %s：%s → %s"
                           % (did, name, fa[name], fb[name]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Freeze (or check) the golden feature tables for F9.")
    ap.add_argument("--check", action="store_true",
                    help="只比對不寫檔；有任何一個數字不同就回非零")
    a = ap.parse_args(argv)

    if not os.path.isdir(GOLDEN_DIR):
        os.makedirs(GOLDEN_DIR, exist_ok=True)

    bad = 0
    for recipe_file, gen, n, seed in CASES:
        path = golden_path(recipe_file, gen)
        rel = os.path.relpath(path, REPO_ROOT)
        new = compute(recipe_file, gen, n, seed)
        if new.get("skipped"):
            print("－ %-46s 略過（%s）" % (rel, new["skipped"]))
            continue

        if a.check:
            if not os.path.isfile(path):
                print("✗ %-46s 還沒凍過 —— 先跑 python tools/freeze_golden.py" % rel)
                bad += 1
                continue
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
            lines = _diff(old, new)
            if lines:
                bad += 1
                print("✗ %s：%d 處不同" % (rel, len(lines)))
                for line in lines[:12]:
                    print("      %s" % line)
                if len(lines) > 12:
                    print("      …還有 %d 處" % (len(lines) - 12))
            else:
                print("✓ %-46s %d 顆全部逐項相同" % (rel, len(new["defects"])))
            continue

        text = _dump(new)
        tmp = path + ".tmp"                              # atomic（鐵則 5）
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
        print("✓ %-46s %d 顆" % (rel, len(new["defects"])))

    if a.check and bad:
        print("")
        print("  數字變了。如果**不是刻意的**，那就是重構動到了行為 —— 先查清楚。")
        print("  如果是刻意的（例如改了演算法），重新凍一次並在 commit 訊息裡說明：")
        print("      python tools/freeze_golden.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
