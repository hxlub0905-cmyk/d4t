# FlexADC CLI — authored 2026-07-27 (M1).
"""FlexADC 指令列介面。

用法：
    python -m flexadc steps                          # 列出所有卡片
    python -m flexadc validate RECIPE [--kind K]     # recipe 健檢（lint）
    python -m flexadc run RECIPE KLARF [--tiff T] [--out r.json] [--csv r.csv] [--limit N]

合成測試資料：``python tools/make_sample.py OUT_DIR``（見 tools/）。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import List, Optional


def _cmd_steps(_args: argparse.Namespace) -> int:
    import flexadc.core.steps  # noqa: F401 — 觸發註冊
    from flexadc.core.pipeline import list_steps

    names = {"image": "影像段 IMAGE", "algo": "算法段 ALGO", "adc": "判定段 ADC"}
    for cat in ("image", "algo", "adc"):
        cards = list_steps(cat)
        if not cards:
            continue
        print(f"\n== {names[cat]} ==")
        for s in cards:
            flag = "（需要 ref）" if s.requires_ref else ""
            print(f"  {s.key:<16} {s.label}{flag} — {s.help}")
            for p in s.params:
                print(f"      · {p.name} ({p.type}, 預設 {p.default!r}) — {p.help}")
    return 0


def _load_recipe(path: str):
    from flexadc.core.pipeline import Recipe

    try:
        return Recipe.load(path)
    except Exception as exc:  # noqa: BLE001 — CLI 邊界
        print(f"[錯誤] 無法載入 recipe：{exc}", file=sys.stderr)
        return None


def _print_issues(issues) -> bool:
    """列印 lint 結果；回傳是否有 error 等級。"""
    has_error = False
    for it in issues:
        mark = "✗" if it.level == "error" else "△"
        has_error = has_error or it.level == "error"
        node = f" @{it.node_id}" if it.node_id else ""
        print(f"  {mark} [{it.code}]{node} {it.title} — {it.detail}")
    if not issues:
        print("  ✓ 無問題")
    return has_error


def _cmd_validate(args: argparse.Namespace) -> int:
    import flexadc.core.steps  # noqa: F401
    from flexadc.core.pipeline import validate

    recipe = _load_recipe(args.recipe)
    if recipe is None:
        return 2
    kinds = [args.kind] if args.kind else sorted(recipe.routes)
    bad = False
    for kind in kinds:
        print(f"\n-- route: {kind} --")
        bad = _print_issues(validate(recipe, kind=kind)) or bad
    return 1 if bad else 0


def _cmd_run(args: argparse.Namespace) -> int:
    import flexadc.core.steps  # noqa: F401
    from flexadc.core.ingest.dataset import load_dataset
    from flexadc.core.pipeline import run_dataset, result_to_json_dict, validate

    recipe = _load_recipe(args.recipe)
    if recipe is None:
        return 2

    ds = load_dataset(args.klarf, tiff_path=args.tiff)
    print(f"資料集：kind={ds.kind}，{len(ds.items)} 顆 defect")
    for w in ds.warnings:
        print(f"  △ {w}")
    if ds.kind not in recipe.routes:
        print(f"[錯誤] recipe 沒有 '{ds.kind}' 的 route（有：{sorted(recipe.routes)}）", file=sys.stderr)
        return 2

    print(f"\nRecipe 健檢（{ds.kind}）：")
    if _print_issues(validate(recipe, kind=ds.kind)):
        print("[錯誤] recipe 有 error 等級問題，請先修正。", file=sys.stderr)
        return 1

    n_total = min(len(ds.items), args.limit) if args.limit else len(ds.items)

    def _progress(i: int, n: int, res) -> None:
        if (i + 1) % 10 == 0 or (i + 1) == n:
            print(f"  … {i + 1}/{n}", flush=True)

    print(f"\n執行 {n_total} 顆：")
    results = run_dataset(recipe, ds, progress=_progress, limit=args.limit)

    ok = [r for r in results if r.ok]
    fail = [r for r in results if not r.ok]
    scores = [r.score for r in ok if r.score is not None]
    print(f"\n完成：{len(ok)} 成功 / {len(fail)} 失敗")
    if scores:
        import statistics

        print(
            f"score：min {min(scores):.3f} · median {statistics.median(scores):.3f} · max {max(scores):.3f}"
        )
        bins: dict = {}
        for r in ok:
            bins[r.bin] = bins.get(r.bin, 0) + 1
        print("bin 分佈：" + " · ".join(f"bin {b}={c}" for b, c in sorted(bins.items())))
    for r in fail[:5]:
        print(f"  ✗ {r.defect_id}: {r.error}")

    payload = [result_to_json_dict(r) for r in results]
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"→ JSON：{args.out}")
    if args.csv:
        feat_keys: List[str] = sorted({k for r in payload for k in r.get("features", {})})
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["defect_id", "ok", "error", "score", "bin"] + feat_keys)
            for r in payload:
                feats = r.get("features", {})
                w.writerow(
                    [r["defect_id"], r["ok"], r.get("error") or "", r.get("score"), r.get("bin")]
                    + [feats.get(k) for k in feat_keys]
                )
        print(f"→ CSV：{args.csv}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="flexadc",
        description="Flex-ADC — 把想法變算法的 ADC 工具（M1 CLI）",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("steps", help="列出所有已註冊卡片").set_defaults(func=_cmd_steps)

    p_val = sub.add_parser("validate", help="Recipe 健檢（lint）")
    p_val.add_argument("recipe")
    p_val.add_argument("--kind", default=None, help="只檢查特定資料型別（ebi_patch/rsem）")
    p_val.set_defaults(func=_cmd_validate)

    p_run = sub.add_parser("run", help="對一份 KLARF(+TIFF) 跑 recipe")
    p_run.add_argument("recipe")
    p_run.add_argument("klarf")
    p_run.add_argument("--tiff", default=None, help="patch TIFF 路徑（預設自動尋找）")
    p_run.add_argument("--out", default=None, help="輸出 JSON 路徑")
    p_run.add_argument("--csv", default=None, help="輸出 CSV 路徑（feature vector）")
    p_run.add_argument("--limit", type=int, default=None, help="只跑前 N 顆（試跑）")
    p_run.set_defaults(func=_cmd_run)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
