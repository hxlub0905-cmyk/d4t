# ADEPT Studio 產品範圍開關 — authored 2026-07-28 (F7-1).
"""Studio 支援哪些輸入型別、哪些卡片會出現在卡片庫。

**2026-08-17（F11 Input-3）：四種輸入全部打開了。** 使用者的話是「目前 ADEPT
可以支援 patch + 對應 KLARF，我需要他也能支援 **RSEM image + KLARF，或單純
圖片**」，而 Input 段的定位是「**整個輸入 image source 的核心**」。

| kind | 什麼樣的資料 | Studio 的入口 |
|---|---|---|
| ``ebi_patch`` | KLARF + patch TIFF（每顆連續幾頁）| ``Open KLARF…`` |
| ``rsem`` | KLARF + 每顆一個影像檔 | ``Open KLARF…``（自動判別）|
| ``tiff_stack`` | 一個多頁 TIFF、**沒有 KLARF** | ``Open stack…`` |
| ``folder`` | 一個資料夾的單張影像、沒有 KLARF | ``Open folder…`` |

後兩者沒有 KLARF → 沒有座標、**寫不回 KLARF**，而那件事在載入的當下就講
（資料集標籤上常駐 ``· no KLARF``，見 :func:`no_klarf_message`）。

這個檔案還是「產品範圍開關」的家
--------------------------------
F7-1 用它把 Studio 收斂成 patch-only（使用者當時的話是「**暫時**只支援 patch」），
而那一輪的做法是**收起來、不刪掉** —— 於是這一輪要打開時，改的是這裡的兩個常數，
`ingest` / `golden_cell` / `algo/period.py` 一行都不用動。收起來的成本是零、
回復的成本是加一個字串，那個判斷在一年後被驗證了。

⚠ ``algo/period.py`` 仍然不要刪：它的 ``estimate_period`` / ``choose_origin``
（相位搜尋）**是之後做 pattern-frame ROI 的唯一工具**
（見 ``docs/history/plans/F7-canvas-and-taxonomy.md`` §4），不只 Golden Cell 在用。

CLI 不受影響
------------
``python -m adept run`` 一直吃得下每一種 kind —— 這裡只管 GUI。
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

__all__ = [
    "SUPPORTED_KINDS", "HIDDEN_STEPS", "DEFAULT_KIND", "SHOW_SAMPLE_ENTRIES",
    "is_supported_kind", "visible_steps", "recipe_is_supported",
    "unsupported_kind_message",
]

#: Studio 接受的資料集型別（``dataset.kind``）—— 四種，見模組說明的表。
#:
#: **2026-08-17（F11 Input-3）：RSEM 與單張圖片打開了。** 使用者的話是
#: 「目前 ADEPT 可以支援 patch + 對應 KLARF，我需要他也能支援 **RSEM image +
#: KLARF，或單純圖片**」。四條路對應四種 source，而「一種 source 一個入口」
#: 是使用者定的分類原則 —— 見 `StudioWindow` 工具列的三顆 Open。
SUPPORTED_KINDS: Sequence[str] = ("ebi_patch", "tiff_stack", "rsem", "folder")

#: 只有在不支援的型別下才有意義、因此不列進卡片庫的 step key。
#:
#: **2026-08-17（F11 Input-3）：空了。** 這裡原本收著 ``golden_cell`` 與
#: ``cell_period``，理由是「它們存在的唯一目的是幫**單張影像**疊一張 ref 出來，
#: 而 Studio 那時只吃兩兩成對的 patch」。現在單張那條路打開了
#: （``rsem`` / ``folder`` / ``tiff_stack`` 都可能只有一張圖），那兩張卡就是
#: 那條路**唯一**的 ref 來源 —— 繼續收著等於把功能打開一半。
#:
#: 機制留著（一個 tuple、一個 `visible_steps()`）：下一次要暫時收起某張卡時，
#: 加一個字串就好。
HIDDEN_STEPS: Sequence[str] = ()

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
    return ("ADEPT Studio does not know this kind of input: “%s”. It reads "
            "KLARF datasets (patch pairs or one image per defect), multi-page "
            "image stacks, and folders of single images. The command line can "
            "still run it: python -m adept run <recipe> <data>."
            % (kind or "unknown"))


def no_klarf_message(kind: Any) -> str:
    """資料集沒有 KLARF 時，載入當下就要講的那一句（F11 Input-2）。

    為什麼要在**載入**時講：沒有 KLARF 就沒有 defect 清單、沒有座標，
    **寫不回 KLARF**。Export 精靈本來就會把那個選項變灰（它看 ``dataset.klarf``），
    但那是使用者跑完一整批、打開輸出精靈才會看到的事 —— 太晚了。
    """
    return ("no KLARF with this data (%s), so the ADC verdict cannot be "
            "written back to a KLARF - CSV and Excel reports still work."
            % (kind or "image stack"))
