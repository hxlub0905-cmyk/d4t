# ADEPT Studio 產品範圍開關 — authored 2026-07-28 (F7-1).
"""Studio 目前支援哪些輸入型別、哪些卡片會出現在卡片庫。

**要把 RSEM 打開，就是改這個檔。** 整包 RSEM 的能力（ingest、Golden Cell、
週期估測、範例 recipe、測試）全部原封不動留在 core 裡 —— 這裡只是把它們
從 Studio 的畫面上收起來。

為什麼是「收起來」而不是「刪掉」
--------------------------------
使用者的決定是「**暫時**只支援 patch」（F7 D1）。刪掉的話：

* 整個 M4（雙輸入 + Golden Cell）要重做；
* ``algo/period.py`` 會跟著陪葬 —— 而它的 ``estimate_period`` /
  ``choose_origin``（相位搜尋）**是之後做 pattern-frame ROI 的唯一工具**
  （見 ``docs/plans/F7-canvas-and-taxonomy.md`` §4）。那個檔案看起來像是
  「只有 Golden Cell 在用」，其實不是。

收起來的成本是零；回復的成本是把 ``SUPPORTED_KINDS`` 加一個字串。

CLI 不受影響
------------
``python -m adept run`` 照樣吃得下 rsem recipe —— 這裡只管 GUI。
臨時真的要跑 RSEM 的人不會沒有路走。
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

__all__ = [
    "SUPPORTED_KINDS", "HIDDEN_STEPS", "DEFAULT_KIND",
    "is_supported_kind", "visible_steps", "recipe_is_supported",
    "unsupported_kind_message",
]

#: Studio 目前接受的資料集型別（``dataset.kind``）。
#: 加回 ``"rsem"`` 就會讓 RSEM 整條路線重新出現在 GUI 上。
SUPPORTED_KINDS: Sequence[str] = ("ebi_patch",)

#: 只有在不支援的型別下才有意義、因此暫時不列進卡片庫的 step key。
#:
#: * ``golden_cell`` —— 存在的唯一理由是「RSEM 單張沒有 ref，疊一張出來」。
#:   patch 兩兩對應本來就有 ref，這張卡沒有用武之地。
#: * ``cell_period`` —— 唯一用途是餵 ``golden_cell``。
#:
#: （``adc`` 判定卡於 F9 Phase 3a 加進這份名單、Phase 3d 拿掉 —— 它當時收
#: 起來的唯一理由是 ``Recipe.score`` 那個固定欄位還在，兩個地方都能設門檻。
#: 那個欄位退場的同一輪就把它放出來，不然會變成「做好了但沒有人打開」。）
#:
#: 這幾張卡仍然註冊在 registry 裡：舊 recipe 載得進來、CLI 跑得動、測試照跑。
HIDDEN_STEPS: Sequence[str] = ("golden_cell", "cell_period")

#: 沒有資料集時 ``RecipeModel`` 用的 route 名稱。
DEFAULT_KIND: str = SUPPORTED_KINDS[0]


def is_supported_kind(kind: Any) -> bool:
    """這個 ``dataset.kind`` 目前的 Studio 吃不吃得下。"""
    return str(kind or "") in SUPPORTED_KINDS


def visible_steps(steps: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """過掉卡片庫不該顯示的卡（吃 ``Step.describe()`` 的 dict 清單）。"""
    return [d for d in (steps or [])
            if str(d.get("key", "")) not in HIDDEN_STEPS]


def recipe_is_supported(info: Dict[str, Any]) -> bool:
    """範本庫要不要列出這份 recipe。

    判準是「**它至少有一條看得懂的 route**」，不是「它只有看得懂的 route」——
    ``dual_route_basic.json`` 同時定義 ebi_patch 與 rsem，載進來之後
    ``RecipeModel.from_recipe`` 會挑 ``sorted(routes)[0]``（= ebi_patch），
    完全跑得動，沒有理由把它藏起來。只有純 rsem 的才會被濾掉。
    """
    routes = [str(r) for r in (info or {}).get("routes") or ()]
    if not routes:
        return True          # 讀壞的檔案交給對話框顯示紅字，不在這裡吃掉
    return any(is_supported_kind(r) for r in routes)


def unsupported_kind_message(kind: Any) -> str:
    """載到不支援的資料集時，狀態列要說的話（白話 + 講得出替代路徑）。"""
    return ("This build of ADEPT Studio only supports EBI patch input "
            "(test + reference pairs); the dataset you opened is “%s”. "
            "The command line can still run it: python -m adept run "
            "<recipe> <klarf>." % (kind or "unknown"))
