# d4t CLI — authored 2026-07-27 (M1).
"""d4t 指令列介面。

用法：
    python -m d4t steps                          # 列出所有卡片
    python -m d4t validate RECIPE [--kind K]     # recipe 健檢（lint）
    python -m d4t run RECIPE KLARF [--tiff T] [--out r.json] [--csv r.csv] [--limit N]

合成測試資料：``python tools/make_sample.py OUT_DIR``（見 tools/）。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Any, List, Optional


def _cmd_steps(_args: argparse.Namespace) -> int:
    import d4t.core.steps  # noqa: F401 — 觸發註冊
    from d4t.core.pipeline import list_steps

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
    from d4t.core.pipeline import Recipe

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
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import validate

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
    import time

    import d4t.core.steps  # noqa: F401
    from d4t.core.ingest.dataset import load_dataset
    from d4t.core.pipeline import run_batch, validate

    recipe = _load_recipe(args.recipe)
    if recipe is None:
        return 2

    ds = load_dataset(args.klarf, tiff_path=args.tiff)
    print(f"資料集：kind={ds.kind}，{len(ds.items)} 顆 defect")
    for w in ds.warnings:
        print(f"  △ {w}")
    # Load 卡上 `carry` 點名的 KLARF 欄位（F16）。**只帶點名的那幾欄** ——
    # 一份 raw data 幾十萬顆 ×24 欄字串是幾百 MB，而且要 pickle 進每個 worker。
    # 一格都沒勾就一欄都不帶，所以既有的 recipe 一個位元組都沒多帶。
    _carry_main_columns(ds, recipe)
    if getattr(args, "gds", ""):
        from d4t.core.ingest import glas_export

        try:
            rep = glas_export.attach(ds, args.gds)
        except glas_export.GlasExportError as e:
            print(f"[錯誤] --gds：{e}", file=sys.stderr)
            return 2
        print(f"GDS 匯出：{rep.summary()}")
        for w in rep.warnings:
            print(f"  △ {w}")
    for spec in (getattr(args, "source", None) or []):
        sid, _, path = str(spec).partition("=")
        sid, path = sid.strip(), path.strip()
        if not sid or not path:
            print("[錯誤] --source 要寫成 `代號=路徑`（收到：%s）" % spec,
                  file=sys.stderr)
            return 2
        from d4t.core.ingest import pair_source as pair_ingest

        from d4t.core.steps.pair_source import columns_for_source

        want = columns_for_source(recipe.nodes.values(), sid)
        try:
            second = load_dataset(path)
            # 只複製 recipe 真的要 carry 的那幾欄（幾十萬顆 ×24 欄是幾百 MB，
            # 而那幾欄還要 pickle 進每個 worker）。
            rep = pair_ingest.attach(ds, second, sid, columns=want)
        except Exception as e:              # noqa: BLE001 — CLI 邊界，一律回報
            print("[錯誤] --source %s：%s" % (spec, e), file=sys.stderr)
            return 2
        # **打錯一個欄名要在這裡就停**，不是讓每一顆都失敗一次：整批跑完才發現
        # 「那一欄根本不存在」是最貴的一種發現方式，而這裡手上還有 KlarfDoc。
        missing = pair_ingest.missing_columns(second, want)
        if missing:
            print("[錯誤] --source %s：這一份沒有 %s 這幾欄（它有：%s）"
                  % (sid, ", ".join(missing),
                     ", ".join(pair_ingest.columns_of(second))), file=sys.stderr)
            return 2
        print("第二份 source：%s" % rep.summary())
        for w in second.warnings:
            print("  △ %s" % w)

    # ---- 分流（F23）：route_by 存在時它覆蓋 kind 選路 ----
    # 欄位在不在**這裡**查（手上有 KlarfDoc，答得出「那它有哪些欄」）——
    # 整批跑完才發現「那一欄根本不存在」是最貴的一種發現方式。
    rb = getattr(recipe, "route_by", None)
    if rb is not None:
        from d4t.core.ingest.dataset import columns_of, missing_columns_of

        absent = missing_columns_of(ds, [rb.column])
        if absent:
            have = ", ".join(columns_of(ds)) or "（這種資料沒有 KLARF，沒有欄位）"
            print("[錯誤] route_by 指到這份資料沒有的欄：%s。它有的是：%s"
                  % (", ".join(absent), have), file=sys.stderr)
            return 2
        mapping = "、".join("%s→%s" % (v, r)
                            for v, r in sorted(rb.map.items()))
        tail = ("；其他走 %s" % rb.default.strip()) if rb.default.strip() \
            else "；對不上＝那一顆失敗"
        print(f"分流：{rb.column}（{mapping}{tail}）")
    elif ds.kind not in recipe.routes:
        print(f"[錯誤] recipe 沒有 '{ds.kind}' 的 route（有：{sorted(recipe.routes)}）", file=sys.stderr)
        return 2

    print(f"\nRecipe 健檢（{ds.kind}）：")
    if _print_issues(validate(recipe, kind=ds.kind)):
        print("[錯誤] recipe 有 error 等級問題，請先修正。", file=sys.stderr)
        return 1

    n_total = min(len(ds.items), args.limit) if args.limit else len(ds.items)

    def _progress(i: int, n: int, res) -> None:
        if (i + 1) % 50 == 0 or (i + 1) == n:
            print(f"  … {i + 1}/{n}", flush=True)

    print(f"\n執行 {n_total} 顆（workers={args.workers or 'auto'}"
          f"{'，cache=' + args.cache if args.cache else ''}）：")
    t0 = time.perf_counter()
    payload = run_batch(recipe, ds, workers=args.workers, cache_dir=args.cache,
                        progress=_progress, limit=args.limit)
    elapsed = time.perf_counter() - t0

    ok = [r for r in payload if r.get("ok")]
    fail = [r for r in payload if not r.get("ok")]
    scores = [r.get("score") for r in ok if r.get("score") is not None]
    per = (elapsed / max(len(payload), 1)) * 1000
    print(f"\n完成：{len(ok)} 成功 / {len(fail)} 失敗 · {elapsed:.1f}s（{per:.1f} ms/顆）")
    if scores:
        import statistics

        print(
            f"score：min {min(scores):.3f} · median {statistics.median(scores):.3f} · max {max(scores):.3f}"
        )
        bins: dict = {}
        for r in ok:
            bins[r.get("bin")] = bins.get(r.get("bin"), 0) + 1
        print("bin 分佈：" + " · ".join(f"bin {b}={c}" for b, c in sorted(bins.items())))
    # ---- 分流摘要（F23 §4.1）----
    # 「掉進 default 的顆數」一定要看得見：站點換了編碼、整批掉進 default，
    # 是「跑得完、有數字、而且是錯的」的形狀。route 的決定是純函式
    # （fields → route），所以這裡重算一次就是批次裡用的那個答案。
    if rb is not None:
        from d4t.core.pipeline.recipe import resolve_route

        route_counts: dict = {}
        n_defaulted = 0
        for item in list(ds.items)[:n_total]:
            r_key, _val, how = resolve_route(recipe, item, ds.kind)
            key = r_key if r_key is not None else "（沒有 route，該顆失敗）"
            route_counts[key] = route_counts.get(key, 0) + 1
            if how == "default":
                n_defaulted += 1
        print("分流結果：" + " · ".join(f"{rk}={c}"
                                      for rk, c in sorted(route_counts.items())))
        if n_defaulted:
            print(f"  △ {n_defaulted} 顆的 {rb.column} 值不在對照表裡，"
                  f"走了 default route「{rb.default.strip()}」")
        declared = set(rb.map.values()) | ({rb.default.strip()}
                                           if rb.default.strip() else set())
        untaken = sorted(declared - set(route_counts))
        if untaken:
            print("  △ 這幾條 route 一顆都沒走到：%s（寫了但用不到的路最容易爛）"
                  % ", ".join(untaken))
    gt_path, gt = _find_ground_truth(getattr(args, "ground_truth", None),
                                     str(args.klarf))
    if gt:
        from d4t.core.export import summarize
        from d4t.core.export.report import UNBINNED_KEY

        summary = summarize(payload, ground_truth=gt)
        g = (summary.get("ground_truth") or {})
        print(f"\n對照 ground truth（{gt_path}）：")
        if g.get("n_evaluated"):
            print(f"  正確率 {_pct(g.get('accuracy'))}　"
                  f"抓漏率 {_pct(g.get('miss_rate'))}"
                  f"（漏抓 {g.get('fn', 0)} 顆真缺陷）　"
                  f"誤殺率 {_pct(g.get('false_alarm_rate'))}"
                  f"（誤判 {g.get('fp', 0)} 顆假點）")
        else:
            print("  這一批沒有一顆對得上 ground truth 裡的 defect id —— "
                  "是不是對到別的 lot 了？")

        # 每一個 bin 的純度（F22-UI）—— 多類別唯一量得出來的東西。
        # **只在真的分出兩類以上時才印**：二元判定的純度上面那三個數字已經
        # 講完了，多印一張表只是同一件事講兩次。
        purity = summary.get("bin_purity") or []
        if len([r for r in purity if r.get("bin") != UNBINNED_KEY]) > 2:
            print("  每一個 bin 裡有幾顆是真的：")
            for row in purity:
                pct = ("—" if row.get("purity") is None
                       else "%.0f%%" % (row["purity"] * 100))
                print("    bin %-4s %3d 顆　真缺陷 %3d　假點 %3d　純度 %s"
                      % (row["bin"], row["n"], row["n_real"],
                         row["n_nuisance"], pct))

    for r in fail[:5]:
        print(f"  ✗ {r.get('defect_id')}: {r.get('error')}")

    if args.db:
        from d4t.core.store import RunStore

        with RunStore(args.db) as store:
            run_id = store.save_run(recipe, payload, klarf_path=str(args.klarf),
                                    dataset_kind=ds.kind, notes=args.notes or "")
        print(f"→ 已存入批次歷史：run_id={run_id}（{args.db}）")
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

    # ---- Output 段：跨顆那一層（F16）------------------------------------
    # **這裡才叫，試跑那條路不叫**（使用者定調：「試跑不寫，只有整批才寫」）。
    # 做成另一支要自己叫的函式而不是 run_batch 的一個旗標，就是為了讓那件事
    # 是結構上的 —— 旗標遲早有人忘記關，而症狀是不可逆的覆寫。
    from d4t.core.pipeline import run_batch_steps

    bctx = run_batch_steps(recipe, ds, payload)
    for w in bctx.warnings:
        print(f"  △ {w}")
    for path in bctx.outputs:
        print(f"→ {path}")
    if bctx.errors:
        # **一張跨顆卡出錯不影響其他卡**（鐵則 7 的跨顆版），但要講出來 ——
        # 而且回非 0：批次跑完了，可是使用者要的東西沒有全部寫出來。
        for nid, msg in bctx.errors.items():
            print(f"[錯誤] 輸出卡 '{nid}'：{msg}", file=sys.stderr)
        return 1
    return 0


def _cmd_runs(args: argparse.Namespace) -> int:
    from d4t.core.store import RunStore

    with RunStore(args.db) as store:
        rows = store.list_runs()
    if not rows:
        print("（尚無批次歷史）")
        return 0
    for r in rows:
        print(f"{r['run_id']}  {r['created_utc']}  recipe={r['recipe_id']}  "
              f"kind={r['dataset_kind']}  n={r['n_total']}（ok {r['n_ok']} / fail {r['n_fail']}）"
              f"{'  ' + r['notes'] if r.get('notes') else ''}")
    return 0


def _cmd_rescore(args: argparse.Namespace) -> int:
    from d4t.core.store import RunStore, rescore

    bins = None
    if args.bins:
        try:
            lo, hi = (int(x) for x in args.bins.split(","))
            bins = {"below": lo, "above": hi}
        except ValueError:
            print("[錯誤] --bins 格式：below,above（例：0,1）", file=sys.stderr)
            return 2
    with RunStore(args.db) as store:
        try:
            summary = rescore(store, args.run_id, expr=args.expr,
                              threshold=args.threshold, bins=bins,
                              save_as=(True if args.save else None), notes=args.notes or "")
        except KeyError as e:
            print(f"[錯誤] {e}", file=sys.stderr)
            return 2
    print(f"rescore {summary['run_id']}：n={summary['n']}，錯誤 {summary['n_errors']}，"
          f"耗時 {summary['elapsed_s']:.2f}s")
    if summary.get("bin_counts"):
        print("bin 分佈：" + " · ".join(f"bin {b}={c}" for b, c in sorted(summary["bin_counts"].items())))
    if summary.get("score_min") is not None:
        print(f"score：min {summary['score_min']:.3f} · median {summary['score_median']:.3f} · "
              f"max {summary['score_max']:.3f}")
    if summary.get("saved_run_id"):
        print(f"→ 已另存為新 run：{summary['saved_run_id']}")
    return 0



def _carry_main_columns(ds: Any, recipe: Any) -> None:
    """把 Load 卡點名的 KLARF 欄位填進每一顆（`DefectItem.fields`）。

    **答案只有一份**：`steps.load.columns_for_main`（`carry` 的意思住在卡片）。
    Studio 走的是同一支（`StudioWindow._carry_main_columns`）—— 這裡與那裡
    只是兩個入口，不是兩份規則。
    """
    from d4t.core.ingest.dataset import fill_fields, missing_columns_of
    from d4t.core.steps.load import columns_for_main

    want = columns_for_main(getattr(recipe, "nodes", None) or {})
    if not want:
        return
    absent = missing_columns_of(ds, want)
    if absent:
        # **在跑之前講**：整批跑完才發現「那一欄根本不存在」是最貴的一種發現
        # 方式（F15-2 的同一條教訓）。這裡答得出「那它有哪些欄」——卡片手上
        # 只有複製過去的那幾欄，答不出來。
        from d4t.core.ingest.dataset import columns_of
        print("[錯誤] Load 卡的 “Carry these columns” 指到這份 KLARF 沒有的欄："
              "%s。它有的是：%s" % (", ".join(absent), ", ".join(columns_of(ds))),
              file=sys.stderr)
        raise SystemExit(2)
    n = fill_fields(ds, want)
    print("KLARF 欄位：帶了 %d 欄（%s）" % (n, ", ".join(want)))


def _cmd_export(args: argparse.Namespace) -> int:
    """把批次歷史裡的一次執行結果輸出：寫回 KLARF / 報表。"""
    import json

    import d4t.core.steps  # noqa: F401
    from d4t.core.export import (
        ExportError, apply_writeback, plan_writeback, summarize,
        write_csv, write_excel,
    )
    from d4t.core.ingest import klarf_core
    from d4t.core.store import RunStore

    with RunStore(args.db) as store:
        try:
            run = store.get_run(args.run_id)
            results = list(store.iter_results(args.run_id))
        except Exception as exc:  # noqa: BLE001 — CLI 邊界
            print(f"[錯誤] 讀不到 run '{args.run_id}'：{exc}", file=sys.stderr)
            return 2
    print(f"run {args.run_id}：{len(results)} 筆結果"
          f"（recipe={run.get('recipe_id')}，kind={run.get('dataset_kind')}）")

    gt = None
    if args.ground_truth:
        with open(args.ground_truth, encoding="utf-8") as f:
            gt = json.load(f)
    s = summarize(results, ground_truth=gt)
    print(f"成功 {s.get('n_ok')} / 失敗 {s.get('n_fail')}；"
          f"bin 分佈 " + " · ".join(f"bin {b}={c}"
                                   for b, c in sorted((s.get('bin_counts') or {}).items(),
                                                      key=lambda kv: str(kv[0]))))
    g = s.get("ground_truth") or {}
    if g.get("n_evaluated"):
        print(f"對照 ground truth（{g['n_evaluated']} 顆）："
              f"正確率 {g.get('accuracy', 0):.1%}　"
              f"抓漏率 {g.get('miss_rate', 0):.1%}（漏抓 {g.get('fn', 0)} 顆真缺陷）　"
              f"誤殺率 {g.get('false_alarm_rate', 0):.1%}（誤判 {g.get('fp', 0)} 顆假點）")

    if args.csv:
        print(f"→ CSV：{write_csv(results, args.csv)}")
    if args.excel:
        try:
            print(f"→ Excel：{write_excel(results, args.excel, ground_truth=gt)}")
        except ExportError as exc:
            print(f"[錯誤] {exc}", file=sys.stderr)
            return 2

    if args.klarf_out or args.dry_run:
        src = args.klarf or run.get("klarf_path")
        if not src:
            print("[錯誤] 沒有來源 KLARF；請用 --klarf 指定。", file=sys.stderr)
            return 2
        doc = klarf_core.load(src)
        opts = {}
        if args.mode == "inplace":
            opts = {"class_col": args.class_col, "bin_col": args.bin_col,
                    "size_col": args.size_col,
                    "size_feature": args.size_feature,
                    "size_scale": args.size_scale}
            opts = {k: v for k, v in opts.items() if v}
        elif args.mode == "topn":
            opts = {"n": args.top_n, "min_score": args.min_score}
        try:
            if args.dry_run:
                plan = plan_writeback(doc, results, args.mode, **opts)
            else:
                plan = apply_writeback(doc, results, args.mode, args.klarf_out, **opts)
        except ExportError as exc:
            print(f"[錯誤] {exc}", file=sys.stderr)
            return 2
        print(f"\n寫回模式：{plan.mode}{'（預覽，未寫檔）' if args.dry_run else ''}")
        print(f"  會改動 {plan.n_rows_changed} 列；輸出 {plan.n_rows_out} 列")
        if plan.columns_touched:
            print(f"  動到欄位：{', '.join(plan.columns_touched)}")
        if plan.columns_added:
            print(f"  新增欄位：{', '.join(plan.columns_added)}")
        for note in plan.notes:
            print(f"  · {note}")
        for it in plan.issues:
            mark = {"error": "✗", "warning": "△"}.get(getattr(it, "level", ""), "·")
            print(f"  {mark} [{getattr(it, 'code', '?')}] {getattr(it, 'title', it)}")
        if not args.dry_run:
            print(f"→ KLARF：{args.klarf_out}")
    return 0


def _cmd_gui(_args: argparse.Namespace) -> int:
    """開 Studio。PySide6 在此 lazy import —— core/CLI 本身不依賴 Qt。"""
    try:
        from d4t.ui.app import main as gui_main
    except ImportError as exc:
        print(f"[錯誤] 無法載入圖形介面（需要 PySide6）：{exc}\n"
              f"       安裝：pip install PySide6", file=sys.stderr)
        return 2
    return gui_main([])


def _pct(value: Any) -> str:
    """比率 → ``"25.0%"``，**沒有定義的時候是 `—` 不是 0%**。

    `report._ground_truth` 的三個比率在分母是 0 的時候回 None（一批裡一顆假點
    都沒有 → 誤殺率沒有定義）。以前這裡寫 ``g.get(k, 0):.1%``，而那個鍵
    **存在**、值是 None —— 預設值救不了，於是整個 `d4t run` 在印摘要的最後一行
    炸掉。而「一批全是真缺陷」一點都不罕見。

    印 `—` 也比印 `0.0%` 誠實：**沒有分母不等於一個都沒誤殺。**
    """
    return "—" if value is None else format(float(value), ".1%")


def _find_ground_truth(arg, klarf_path: str):
    """``(用了哪個檔, 內容)``；沒有就 ``("", None)``。

    ``--ground-truth`` 沒給時**自動找 KLARF 旁邊的 ``ground_truth.json``** ——
    ``tools/make_sample.py`` 就是寫在那裡，而開發迴圈裡「跑一次看準不準」是最
    常做的事，每次都要多打一個路徑是白費力氣。

    自動找到的一定會**把路徑印出來**：猜對了要讓人看得見猜的是什麼，
    猜錯了（例如 lot 資料夾裡剛好有一個別的 ground_truth.json）才有機會發現。
    ``--ground-truth none`` 關掉自動尋找。
    """
    import os

    text = str(arg or "").strip()
    if text.lower() in ("none", "off", "no"):
        return "", None
    if text:
        with open(text, encoding="utf-8") as f:
            return text, json.load(f)
    for folder in (os.path.dirname(os.path.abspath(str(klarf_path))),):
        guess = os.path.join(folder, "ground_truth.json")
        if os.path.isfile(guess):
            try:
                with open(guess, encoding="utf-8") as f:
                    return guess, json.load(f)
            except Exception:              # noqa: BLE001 — 找不到就算了
                return "", None
    return "", None


def main(argv: Optional[List[str]] = None) -> int:
    # 廠內機器的 console 是 cp950，而這支 CLI 印 ✓ / ✗ / △ / →（cp950 沒有
    # 這幾個字）。不設這個的話，跑完 48 顆、CSV 也寫好了，使用者看到的卻是
    # 一條 UnicodeEncodeError 的 traceback —— 在**成功**的那一刻。
    # ``errors="replace"`` 把印不出的字換成 ?（中文 cp950 本來就有，不受影響）；
    # 檔案輸出全部自帶 encoding="utf-8"，不走這裡。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass    # 不是真的 console（被 redirect 成別的東西）就算了

    ap = argparse.ArgumentParser(
        prog="d4t",
        description="d4t — 把想法變算法的 ADC 工具",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("gui", help="開啟 Studio 視覺化介面").set_defaults(func=_cmd_gui)
    sub.add_parser("steps", help="列出所有已註冊卡片").set_defaults(func=_cmd_steps)

    p_val = sub.add_parser("validate", help="Recipe 健檢（lint）")
    p_val.add_argument("recipe")
    p_val.add_argument("--kind", default=None, help="只檢查特定資料型別（ebi_patch/rsem）")
    p_val.set_defaults(func=_cmd_validate)

    p_run = sub.add_parser("run", help="對一份 KLARF(+TIFF) 跑 recipe")
    p_run.add_argument("recipe")
    p_run.add_argument("klarf")
    p_run.add_argument("--tiff", default=None, help="patch TIFF 路徑（預設自動尋找）")
    p_run.add_argument("--gds", default="",
                       help="GLAS 匯出資料夾（`<id>_label.png` + "
                            "overlay_manifest.json）—— 掛上去之後 "
                            "`load_sidecar` 卡才有東西可以載")
    p_run.add_argument("--source", action="append", default=[],
                       metavar="代號=KLARF路徑",
                       help="第二份 lot（F15）：`pair_source` 卡靠代號指它。"
                            "可以重複給。路徑不進 recipe —— 換一批資料重跑時"
                            "在這裡換")
    p_run.add_argument("--out", default=None, help="輸出 JSON 路徑")
    p_run.add_argument("--csv", default=None, help="輸出 CSV 路徑（feature vector）")
    p_run.add_argument("--limit", type=int, default=None, help="只跑前 N 顆（試跑）")
    p_run.add_argument("--workers", type=int, default=None, help="平行 worker 數（預設=CPU 核心數；1=單進程）")
    p_run.add_argument("--cache", default=None, help="影像段快取資料夾（改算法段參數重跑會大幅加速）")
    p_run.add_argument("--db", default=None, help="存入批次歷史 SQLite（例：~/.d4t/runs.db）")
    p_run.add_argument("--notes", default=None, help="批次備註")
    p_run.add_argument(
        "--ground-truth", default=None, metavar="JSON",
        help=("ground_truth.json（有的話跑完直接印正確率/抓漏率/誤殺率）。"
              "不給的話會自動找 KLARF 旁邊的 ground_truth.json；"
              "用 --ground-truth none 可以關掉。"))
    p_run.set_defaults(func=_cmd_run)

    p_runs = sub.add_parser("runs", help="列出批次歷史")
    p_runs.add_argument("--db", required=True, help="批次歷史 SQLite 路徑")
    p_runs.set_defaults(func=_cmd_runs)

    p_ex = sub.add_parser("export", help="輸出：寫回 KLARF / CSV / Excel 報表")
    p_ex.add_argument("run_id")
    p_ex.add_argument("--db", required=True, help="批次歷史 SQLite 路徑")
    p_ex.add_argument("--mode", choices=["inplace", "annotate", "topn"], default="annotate",
                      help="寫回模式：inplace=就地改欄（無損）／annotate=另存含分數欄／topn=只留前 N 名")
    p_ex.add_argument("--klarf", default=None, help="來源 KLARF（預設用 run 紀錄裡的路徑）")
    p_ex.add_argument("--klarf-out", default=None, help="輸出 KLARF 路徑")
    p_ex.add_argument("--dry-run", action="store_true", help="只預覽會改什麼，不寫檔")
    p_ex.add_argument("--class-col", default=None, help="inplace：bin 寫進哪個分類欄（例 CLASSNUMBER）")
    p_ex.add_argument("--bin-col", default=None, help="inplace：bin 寫進哪個 bin 欄（例 ROUGHBINNUMBER）")
    p_ex.add_argument("--size-col", default=None, help="inplace：CD 寫進哪個尺寸欄（例 DSIZE）")
    p_ex.add_argument("--size-feature", default=None,
                      help="inplace：尺寸欄寫哪個特徵（預設 cd_median）")
    p_ex.add_argument("--size-scale", type=float, default=None,
                      help="inplace：尺寸值寫進去之前乘上的係數。量測全是 pixel，"
                           "要寫 nm 就填 nm/px（預設 1 = 原樣寫 pixel）")
    p_ex.add_argument("--top-n", type=int, default=0, help="topn：取前幾名（0=改用 --min-score）")
    p_ex.add_argument("--min-score", type=float, default=0.0, help="topn：分數門檻")
    p_ex.add_argument("--csv", default=None, help="輸出 feature vector CSV")
    p_ex.add_argument("--excel", default=None, help="輸出 Excel 報表（需要 openpyxl）")
    p_ex.add_argument("--ground-truth", default=None, help="ground_truth.json（有的話會算正確率/抓漏率）")
    p_ex.set_defaults(func=_cmd_export)

    p_rs = sub.add_parser("rescore", help="改分數表達式/門檻重算（不重跑影像，秒級）")
    p_rs.add_argument("run_id")
    p_rs.add_argument("--db", required=True, help="批次歷史 SQLite 路徑")
    p_rs.add_argument("--expr", default=None, help="新的分數表達式（不給=沿用）")
    p_rs.add_argument("--threshold", type=float, default=None, help="新門檻")
    p_rs.add_argument("--bins", default=None, help="below,above（例：0,1）")
    p_rs.add_argument("--save", action="store_true", help="另存為新 run")
    p_rs.add_argument("--notes", default=None, help="備註")
    p_rs.set_defaults(func=_cmd_rescore)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
