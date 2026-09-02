# d4t Studio — 特徵怎麼分組（F76 刀 3，2026-09-02 從 `results_table.py` 搬來）。
"""**卡 → 區域 → 統計量的那棵樹，只有一份。**

為什麼搬出來
------------
這棵樹（`column_tree`）是 2026-08-27 為結果表寫的（PR-1／PR-3），而 Preview
欄那張特徵表走的是**另一條、弱得多的路**：`studio._feature_sections()` 讀
``meta["feature_owner"]``，只分到「哪張卡」為止。

同一件事兩份說法，而它們**已經漂開了**：`region_index` 是由每張卡各自算的，
於是同一個區域在同一張表上有兩種顏色（F76 刀 1 修的那個病）。所以這一份不是
新東西 —— 它是把已經在跑的那一份搬到一個兩邊都指得到的位置。

住在 `ui/` 而不是 `core/`
-------------------------
它排的是**畫面上的順序與標籤**（`widgets.metric_face` 的短標籤、`_fixed_columns`
的徽章欄），不是引擎的事。真正屬於 core 的那一半 —— 每個特徵名的結構化身分
—— 早就在 `core/pipeline/verdict_features.bound_specs` 了，這一份吃它的輸出。
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ..core.export.report import BASE_COLUMNS, feature_keys
from .widgets import metric_face

__all__ = ["BADGE_COLUMN", "CLASS_COLUMN", "column_tree", "fixed_columns",
           "stat_label"]

#: 類別名那一欄插在哪（``defect_id`` 之後）——**它是這一顆判成了什麼**，
#: 跟 id 一起看才有意義，排在最後面等於要橫向捲過整排特徵才看得到。
CLASS_COLUMN = "class"

#: CSV 有、但畫面上沒有用的欄。``ok`` 的資訊已經在 ``error`` 與整列的顏色上，
#: 而一欄 0/1 在一張要用眼睛掃的表上只是雜訊。
_HIDDEN = ("ok",)

#: 警示徽章那一欄（永遠在最左）。名字帶 ``!`` 所以撞不到任何特徵名 ——
#: 特徵名都是 Python 識別字。它跟 ``class`` 一樣只存在於畫面上，CSV 沒有。
BADGE_COLUMN = "!warn"


def fixed_columns() -> List[str]:
    """每一份表都有的前段：徽章 ＋ base（去 ``ok``）＋ ``class`` 緊鄰 id。"""
    base = [c for c in BASE_COLUMNS if c not in _HIDDEN]
    i = base.index("defect_id") + 1 if "defect_id" in base else 0
    return [BADGE_COLUMN] + base[:i] + [CLASS_COLUMN] + base[i:]


def stat_label(bound: Any) -> str:
    """下層表頭的短標籤。metric id 查 `widgets.metric_face`（那張表**認不得
    的也答得出來**），沒有 metric 的（引擎名、load 的座標那些）用 base ——
    **不猜**，原始欄名永遠在懸停上。"""
    spec = bound.spec
    if spec.metric:
        return metric_face(spec.metric)[1]
    return spec.base or spec.name


def column_tree(results: Sequence[Dict[str, Any]],
                verdict_features: Sequence[str] = (),
                specs: Sequence[Any] = (),
                diagnostics: Sequence[str] = ()) -> Dict[str, Any]:
    """`ResultsTableModel.set_results` 吃的分層描述 —— **卡 → 區域 → 統計量
    的樹只算一次**，摺疊順序、雙層表頭、維度過濾共用這一份。

    ``specs`` 是 `verdict_features.bound_specs` 的回傳（BoundSpec 序列）。
    「判定引用 > 診斷隱藏」那條規矩住在這裡：被判定引用的診斷特徵**不**藏
    （使用者 2026-08-27 定調 —— 「這顆為什麼判 NG」要看得到比的那個值），
    其餘的診斷欄兩層都不出現。

    舊鍵（``columns`` / ``verdict_columns`` / ``n_more`` / ``diagnostics``）
    一個不少；PR-3 加 ``spec_of``（欄名 → BoundSpec）與 ``groups``
    （``[{node_id, label, regions: [{region, role, columns:
    [{name, stat_label}]}]}]``）。
    """
    verdict = [str(f) for f in verdict_features]
    drop = {d for d in map(str, diagnostics) if d not in set(verdict)}
    spec_of: Dict[str, Any] = {}
    for b in specs:
        spec_of.setdefault(str(b.spec.name), b)

    vcols = list(fixed_columns())
    placed = set(vcols)
    for f in verdict:
        # 判定引用了沒人產出的名字 → **照樣是一欄**（整欄留白）。
        if f and f not in placed and f not in drop:
            placed.add(f)
            vcols.append(f)

    # 卡 → 區域 → 統計量。specs 已是執行序，而量測卡的宣告迴圈是
    # 流 → 區域 → 統計量（`MultiSourceStep.resolve_feature_specs`），
    # 所以照原序分段就保證**同區域的欄相鄰** —— 表頭的跨欄靠它。
    groups: List[Dict[str, Any]] = []
    for name, b in spec_of.items():
        if name in drop:
            continue
        col = {"name": name, "stat_label": _stat_label(b)}
        if not (groups and groups[-1]["node_id"] == b.node_id
                and groups[-1]["label"] == b.label):
            groups.append({"node_id": b.node_id, "label": b.label,
                           "regions": []})
        regs = groups[-1]["regions"]
        if not (regs and regs[-1]["region"] == b.spec.region):
            regs.append({"region": b.spec.region,
                         "role": b.spec.region_role, "columns": []})
        regs[-1]["columns"].append(col)

    rest: List[str] = []
    for g in groups:
        for reg in g["regions"]:
            for col in reg["columns"]:
                n = col["name"]
                if n and n not in placed:
                    placed.add(n)
                    rest.append(n)
    # 歸不到任何一張卡的放最後（fixture 造的名字、宣告漏掉的那些）。
    for n in feature_keys(results):
        if n not in placed and n not in drop:
            placed.add(n)
            rest.append(n)
    return {"columns": vcols + rest, "verdict_columns": vcols,
            "n_more": len(rest), "diagnostics": [str(d) for d in diagnostics],
            "spec_of": spec_of, "groups": groups}

