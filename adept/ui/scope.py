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
  （見 ``docs/history/plans/F7-canvas-and-taxonomy.md`` §4）。那個檔案看起來像是
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
    "SUPPORTED_KINDS", "HIDDEN_STEPS", "DEFAULT_KIND", "SHOW_SAMPLE_ENTRIES",
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
#: 兩張卡仍然註冊在 registry 裡：舊 recipe 載得進來、CLI 跑得動、測試照跑。
HIDDEN_STEPS: Sequence[str] = ("golden_cell", "cell_period")

#: 沒有資料集時 ``RecipeModel`` 用的 route 名稱。
DEFAULT_KIND: str = SUPPORTED_KINDS[0]

#: 「範例 recipe」的兩個入口要不要出現在畫面上：工具列的 ``Templates…``、
#: 導覽與空白狀態上的「用範例資料試一次」。
#:
#: 2026-08-16：使用者定調「範例 recipe 都先全部拿掉」，``examples/`` 整個移除
#: （原本五份在 39b9fea 就因為依賴被拿掉的卡片而刪了，剩下的一份也不留）。
#: 沒有 recipe 可以載，這兩個入口就是**按了會撞牆的東西**：範本庫開起來是空的，
#: 「用範例資料試一次」產得出資料卻載不到 pipeline。對不會寫 code 的目標使用者，
#: 那比沒有這顆鈕更糟（推廣鐵則）—— 所以連入口一起收起來。
#:
#: 收起來的是**入口，不是能力**：``StudioWindow.run_demo()`` /
#: ``generate_demo_lot()`` / :class:`~adept.ui.welcome.RecipeLibraryDialog`
#: 一行都沒動，測試照樣直接呼叫得到。範例 recipe 庫回來的那一天，
#: 把這個常數改成 ``True`` 就整組回來 —— 跟 ``SUPPORTED_KINDS`` 同一套辦法。
SHOW_SAMPLE_ENTRIES: bool = False


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
    一份同時定義 ebi_patch 與 rsem 的 recipe，載進來之後
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
