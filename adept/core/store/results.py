# ADEPT result store — authored 2026-07-28 (M2).
"""批次結果儲存（SQLite）＋ rescore：MMH ``batch_run_store`` 模式的一般化。

角色（見 docs/plans/F0-master-plan.md §6）：

- **RunStore**：每次批次執行存成一個 run —— ``runs`` 一列（recipe 快照、
  KLARF 路徑、ok/fail 統計）＋ ``results`` 每顆一列（score/bin/features）。
  直方圖、gallery、報表、feature vector 匯出全吃這張表。
- **rescore**：改表達式/門檻**不重跑影像** —— 從既有 run 的 features 直接
  重算 score/bin（「拖門檻線 → bin 數即時變」的 headless 基礎）。
  10k 顆 rescore 遠低於 5 秒（純 python dict 迴圈 + executemany）。

設計慣例：

- WAL journal、foreign_keys ON、``ON DELETE CASCADE``（刪 run 連 results 一起掉）。
- schema_version 記在 ``meta`` 表（v1）；未來升版走 migration。
- 資料庫路徑由呼叫端決定（CLI 層預設 ``~/.adept/runs.db``），這裡不寫死。
- results 列 = :func:`adept.core.pipeline.result_to_json_dict` 的 dict
  （traces 不入庫；features 中 nan/inf 一律存成 None，JSON 安全）。
"""
from __future__ import annotations

import csv
import json
import math
import os
import statistics
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

import sqlite3

from adept.core.pipeline.expression import parse_expression

__all__ = ["RunStore", "rescore", "SCHEMA_VERSION"]

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs(
    run_id       TEXT PRIMARY KEY,
    created_utc  TEXT NOT NULL,
    recipe_id    TEXT NOT NULL DEFAULT '',
    recipe_json  TEXT NOT NULL DEFAULT '',
    klarf_path   TEXT NOT NULL DEFAULT '',
    dataset_kind TEXT NOT NULL DEFAULT '',
    n_total      INTEGER NOT NULL DEFAULT 0,
    n_ok         INTEGER NOT NULL DEFAULT 0,
    n_fail       INTEGER NOT NULL DEFAULT 0,
    notes        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS results(
    run_id        TEXT NOT NULL,
    defect_id     TEXT NOT NULL,
    ok            INTEGER NOT NULL,
    error         TEXT,
    score         REAL,
    bin           INTEGER,
    features_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, defect_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
"""

_RUN_COLS = ("run_id", "created_utc", "recipe_id", "klarf_path",
             "dataset_kind", "n_total", "n_ok", "n_fail", "notes")


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _safe_num(v: Any) -> Optional[float]:
    """float 化；None/nan/inf/不可轉 → None（與 engine._safe_num 同語意）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _auto_run_id() -> str:
    """自動 run_id：UTC 時間戳（到分）＋短 uuid，例 ``20260728T0102-ab12cd``。"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
    return "{}-{}".format(stamp, uuid.uuid4().hex[:6])


def _recipe_to_dict(recipe: Any) -> Dict[str, Any]:
    """Recipe dataclass 或 recipe JSON dict → dict（duck typing，不硬綁類別）。"""
    if hasattr(recipe, "to_json_dict"):
        return recipe.to_json_dict()
    if isinstance(recipe, dict):
        return dict(recipe)
    raise TypeError(
        "recipe must be a Recipe object (with to_json_dict) or a recipe JSON "
        "dict, got {}".format(type(recipe).__name__))


# ---------------------------------------------------------------------------
# RunStore
# ---------------------------------------------------------------------------
class RunStore:
    """批次歷史 SQLite 儲存；一個實例 = 一條連線。支援 context manager。

    .. code-block:: python

        with RunStore(str(db_path)) as store:
            run_id = store.save_run(recipe, [result_to_json_dict(r) for r in rs])
            summary = rescore(store, run_id, threshold=2.5)
    """

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        parent = os.path.dirname(self.db_path)
        if parent and self.db_path != ":memory:":
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._conn:
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),))

    # ---- 生命週期 ---------------------------------------------------------
    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    # ---- 寫入 -------------------------------------------------------------
    def save_run(self, recipe: Any, results: List[Dict[str, Any]], *,
                 klarf_path: str = "", dataset_kind: str = "",
                 notes: str = "", run_id: Optional[str] = None) -> str:
        """存一個 run（單一交易、``executemany``），回傳 run_id。

        ``results`` 為 :func:`result_to_json_dict` 形狀的 dict list
        （traces 不入庫）；features 中 nan/inf → None。
        ``run_id=None`` 自動產生（時間戳＋短 uuid，撞號自動重抽）。
        """
        rdict = _recipe_to_dict(recipe)
        recipe_id = str(rdict.get("recipe_id", ""))
        recipe_json = json.dumps(rdict, ensure_ascii=False)

        if run_id is None:
            run_id = _auto_run_id()
            while self._run_exists(run_id):  # pragma: no cover — uuid 撞號極罕見
                run_id = _auto_run_id()
        else:
            run_id = str(run_id)

        rows = []
        n_ok = 0
        for r in results:
            ok = bool(r.get("ok"))
            n_ok += 1 if ok else 0
            feats = {k: _safe_num(v) for k, v in (r.get("features") or {}).items()}
            b = r.get("bin")
            rows.append((
                run_id,
                str(r.get("defect_id", "")),
                1 if ok else 0,
                r.get("error"),
                _safe_num(r.get("score")),
                None if b is None else int(b),
                json.dumps(feats, ensure_ascii=False),
            ))

        with self._conn:  # 單一交易：runs + results 同進同出
            self._conn.execute(
                "INSERT INTO runs(run_id, created_utc, recipe_id, recipe_json, "
                "klarf_path, dataset_kind, n_total, n_ok, n_fail, notes) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (run_id, _now_utc_iso(), recipe_id, recipe_json,
                 str(klarf_path), str(dataset_kind),
                 len(rows), n_ok, len(rows) - n_ok, str(notes)))
            self._conn.executemany(
                "INSERT INTO results(run_id, defect_id, ok, error, score, bin, "
                "features_json) VALUES(?,?,?,?,?,?,?)", rows)
        return run_id

    def delete_run(self, run_id: str) -> None:
        """刪 run；results 由 ``ON DELETE CASCADE`` 一併清掉。不存在則靜默。"""
        with self._conn:
            self._conn.execute("DELETE FROM runs WHERE run_id=?", (str(run_id),))

    # ---- 讀取 -------------------------------------------------------------
    def _run_exists(self, run_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM runs WHERE run_id=?", (str(run_id),))
        return cur.fetchone() is not None

    def list_runs(self) -> List[Dict[str, Any]]:
        """全部 run 摘要（**不含** recipe_json），新的在前。"""
        cur = self._conn.execute(
            "SELECT {} FROM runs ORDER BY created_utc DESC, rowid DESC".format(
                ", ".join(_RUN_COLS)))
        return [dict(row) for row in cur.fetchall()]

    def get_run(self, run_id: str) -> Dict[str, Any]:
        """單一 run 完整列（**含** recipe_json）；不存在 → :class:`KeyError`。"""
        cur = self._conn.execute(
            "SELECT * FROM runs WHERE run_id=?", (str(run_id),))
        row = cur.fetchone()
        if row is None:
            raise KeyError("run '{}' not found (database: {})".format(run_id, self.db_path))
        return dict(row)

    def iter_results(self, run_id: str) -> Iterator[Dict[str, Any]]:
        """逐顆 yield 結果 dict（features 已從 JSON 解析回 dict），依存入順序。"""
        if not self._run_exists(run_id):
            raise KeyError("run '{}' not found (database: {})".format(run_id, self.db_path))
        cur = self._conn.execute(
            "SELECT defect_id, ok, error, score, bin, features_json "
            "FROM results WHERE run_id=? ORDER BY rowid", (str(run_id),))
        for row in cur:
            yield {
                "defect_id": row["defect_id"],
                "ok": bool(row["ok"]),
                "error": row["error"],
                "score": row["score"],
                "bin": row["bin"],
                "features": json.loads(row["features_json"]),
            }

    def get_features_table(self, run_id: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """``(defect_ids, feature_dicts)`` 兩平行 list —— feature vector / ML 備料。"""
        ids: List[str] = []
        feats: List[Dict[str, Any]] = []
        for r in self.iter_results(run_id):
            ids.append(r["defect_id"])
            feats.append(r["features"])
        return ids, feats

    # ---- 匯出 -------------------------------------------------------------
    def export_csv(self, run_id: str, path: str) -> str:
        """匯出一個 run 為 CSV（utf-8-sig，Excel 直開不亂碼）。

        欄位：defect_id, ok, error, score, bin，之後接**排序後的
        feature key 聯集**（缺的留空）—— feature vector 匯出 = ML 備料。
        atomic 寫入（``.tmp`` + ``os.replace``）。回傳寫入路徑。
        """
        path = str(path)
        rows = list(self.iter_results(run_id))
        keys: List[str] = sorted(set().union(*(r["features"].keys() for r in rows))) \
            if rows else []
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["defect_id", "ok", "error", "score", "bin"] + keys)
            for r in rows:
                feats = r["features"]
                w.writerow(
                    [r["defect_id"],
                     1 if r["ok"] else 0,
                     "" if r["error"] is None else r["error"],
                     "" if r["score"] is None else r["score"],
                     "" if r["bin"] is None else r["bin"]]
                    + [("" if feats.get(k) is None else feats.get(k)) for k in keys])
        os.replace(tmp, path)
        return path


# ---------------------------------------------------------------------------
# rescore：改表達式/門檻不重跑影像
# ---------------------------------------------------------------------------
def _decision_spec(rdict: Dict[str, Any], run_id: str
                   ) -> Tuple[Dict[str, Any], Any]:
    """從存下來的 recipe JSON 找出「判定是怎麼下的」，並回一個寫回去的函式。

    兩種形狀都要吃得下，因為 **資料庫裡的 recipe_json 是歷史快照，沒辦法遷移**：

    * **判定卡**（F9 Phase 3d 起）—— ``nodes`` 裡 ``step == "adc"`` 的那一張。
    * **``score`` 區塊**（舊 run）—— 那時候判定是 recipe 上的一個固定欄位。

    多於一張判定卡就講清楚不要猜：rescore 只換一組數字，而「換哪一張的」
    在有兩條分支的圖上沒有預設答案。
    """
    nodes = dict(rdict.get("nodes") or {})
    adc_ids = sorted(nid for nid, nd in nodes.items()
                     if str((nd or {}).get("step", "")) == "adc")
    if len(adc_ids) > 1:
        raise ValueError(
            "the recipe of run '{}' has {} Decide cards ({}); rescore changes "
            "one set of numbers and cannot tell which branch you mean"
            .format(run_id, len(adc_ids), ", ".join(adc_ids)))

    if adc_ids:
        p = dict(nodes[adc_ids[0]].get("params") or {})
        spec = {
            "expr": str(p.get("expr", "") or ""),
            "threshold": float(p.get("threshold", 0.0) or 0.0),
            "bins": {"below": int(p.get("bin_below", 0)),
                     "above": int(p.get("bin_above", 1))},
        }

        def write_back(updated: Dict[str, Any]) -> None:
            b = dict(updated.get("bins") or {})
            p.update({
                "expr": str(updated.get("expr", "")),
                "threshold": float(updated.get("threshold", 0.0)),
                "bin_below": int(b.get("below", 0)),
                "bin_above": int(b.get("above", 1)),
            })
            nodes[adc_ids[0]]["params"] = p
            rdict["nodes"] = nodes

        return spec, write_back

    spec = dict(rdict.get("score") or {})

    def write_back_legacy(updated: Dict[str, Any]) -> None:
        rdict["score"] = updated

    return spec, write_back_legacy


def rescore(store: RunStore, run_id: str, *,
            expr: Optional[str] = None,
            threshold: Optional[float] = None,
            bins: Optional[Dict[str, int]] = None,
            save_as: Optional[Union[str, bool]] = None,
            notes: str = "") -> Dict[str, Any]:
    """用既有 run 的 features 重算 score/bin（**不重跑影像**）。

    - ``expr`` / ``threshold`` / ``bins``：None → 沿用該 run recipe 的設定。
    - 每顆的變數 = 存下來的 features **排除 "score"**（避免舊分數污染新式）。
    - 判定與 engine 相同：``score < threshold → bins["below"]``，否則
      ``bins["above"]``。
    - 某顆 features 缺變數（或值是 None，例如原本是 nan）→ 該顆
      score=None、bin=None、記入 ``n_errors``，**絕不炸整批**。
    - ``save_as``：字串 → 以該 id 存成**新 run**；True → 自動 id；
      新 run 帶更新後的 recipe_json、原 run 的 klarf_path/dataset_kind、
      ``notes``；新 id 放在回傳的 ``saved_run_id``。

    回傳 summary::

        {run_id, n, n_errors, bin_counts, score_min, score_median,
         score_max, elapsed_s, saved_run_id}
    """
    t0 = time.perf_counter()
    run = store.get_run(run_id)

    # ---- 組出「更新後的 score spec」（None → 沿用）----
    try:
        rdict: Dict[str, Any] = json.loads(run["recipe_json"]) or {}
    except (ValueError, TypeError):
        rdict = {}
    spec, write_back = _decision_spec(rdict, run_id)
    if expr is not None:
        spec["expr"] = str(expr)
    if threshold is not None:
        spec["threshold"] = float(threshold)
    if bins is not None:
        spec["bins"] = {str(k): int(v) for k, v in bins.items()}
    if not str(spec.get("expr", "") or ""):
        raise ValueError(
            "the recipe of run '{}' has no Decide card with a score expression;"
            " rescore needs an expression via expr=".format(run_id))
    write_back(spec)

    expression = parse_expression(str(spec["expr"]))  # 語法錯誤 → 直接 raise（recipe 寫錯要讓人看到）
    thr = float(spec.get("threshold", 0.0))
    bins_used = dict(spec.get("bins") or {})
    b_below = int(bins_used.get("below", 0))
    b_above = int(bins_used.get("above", 1))

    # ---- 純 python dict 迴圈重算（10k 顆遠低於 5 s）----
    n = 0
    n_errors = 0
    scores: List[float] = []
    bin_counts: Dict[int, int] = {}
    new_rows: List[Dict[str, Any]] = []
    for r in store.iter_results(run_id):
        n += 1
        feats = r["features"]
        variables = {k: v for k, v in feats.items() if k != "score"}
        try:
            s = expression.eval(variables)
            b = b_below if s < thr else b_above
        except Exception as e:  # 缺變數 / 值不是數字 → 該顆記錯，不殺整批
            n_errors += 1
            feats["score"] = None
            new_rows.append({
                "defect_id": r["defect_id"], "ok": False, "error": str(e),
                "features": feats, "score": None, "bin": None})
            continue
        scores.append(s)
        bin_counts[b] = bin_counts.get(b, 0) + 1
        feats["score"] = s
        new_rows.append({
            "defect_id": r["defect_id"], "ok": True, "error": None,
            "features": feats, "score": s, "bin": b})

    # ---- 存成新 run（選配）----
    saved_run_id: Optional[str] = None
    if save_as:
        saved_run_id = store.save_run(
            rdict, new_rows,
            klarf_path=run.get("klarf_path", ""),
            dataset_kind=run.get("dataset_kind", ""),
            notes=notes,
            run_id=(None if save_as is True else str(save_as)))

    return {
        "run_id": run_id,
        "n": n,
        "n_errors": n_errors,
        "bin_counts": bin_counts,
        "score_min": min(scores) if scores else None,
        "score_median": statistics.median(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "elapsed_s": time.perf_counter() - t0,
        "saved_run_id": saved_run_id,
    }
