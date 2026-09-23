# 使用者面的字只有一個進出口 — authored 2026-09-08 (U14).
"""**註解全中文、UI 字串 100% 英文硬編碼，沒有 tr() 也沒有 catalog。**

之後要出中文版＝改 38 個檔案，而那時候正是最不想動 UI 的時候（外部檢視清單
U14）。這一份是那件事的前置。

設計：**鍵就是英文原句**
------------------------
`tr("Run trial")`，不是 `tr("toolbar.run_trial")`。三個理由，而第三個是真正的
理由：

1. 沒有翻譯檔的時候它**回原句** —— 也就是漏包一句話的代價是「那句話沒有被
   翻譯」，不是「畫面上出現一個 `toolbar.run_trial`」。
2. 讀原始碼的人看得到那句話長什麼樣，不必去查一張表。
3. **它讓「之後不必改 38 個檔案」這句話成立。** 鍵是原句的話，翻譯層可以擺在
   **共用的那幾支**（工具列的鈕、ParamForm 的說明句、狀態列）——
   那些地方本來就有人流過，包一次就涵蓋幾百句，而呼叫端一個字都不用改。

⚠ **不翻譯的兩類**（使用者定調，`CLAUDE.md` §5 那條的同一個道理）：

* **卡片名**（`Step.label`）—— 它是 recipe JSON 的鄰居與廠內的共同語彙。
  「Denoise」翻成「去雜訊」之後，一份 recipe 在兩台機器上講的是兩個名字。
* **階段名**（`step.GROUPS` 的標題）—— 同上，而且它印在 rail 上、CLI 上、
  文件上。

所以這裡**沒有**掛在 `Step.label` 或 `GROUPS` 上的鉤子，而且有一條測試守著。

怎麼加一種語言
--------------
`locales/<code>.json`：一個 `{英文原句: 譯文}` 的平表。
`install("zh_TW")` 之後 `tr()` 就會回譯文。缺的句子回原句 —— 一份翻到一半的
catalog 是可以出貨的，那正是要的。

⚠ 這一支**不 import Qt**（它只是一張字典）。它住在 `d4t/ui` 是因為它服務的是
UI，不是因為它需要 Qt。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

__all__ = ["DEFAULT_LOCALE", "available", "current", "install", "missing",
           "seen", "tr"]

DEFAULT_LOCALE = "en"

#: 翻譯檔住哪。
LOCALE_DIR = Path(__file__).resolve().parent / "locales"

_locale = DEFAULT_LOCALE
_catalog: Dict[str, str] = {}

#: **每一句流過 :func:`tr` 的原句。**
#:
#: 它不是除錯用的殘留 —— 它是「翻譯檔要翻哪些句子」的唯一答案。手寫一份清單
#: 的話，下一個人加一句話而忘了加進清單，那句話會安靜地永遠不被翻譯。
_seen: Dict[str, int] = {}


def current() -> str:
    """現在是哪一種語言。"""
    return _locale


def available() -> List[str]:
    """有哪幾份翻譯檔（含 ``en`` —— 它不需要檔案）。"""
    out = [DEFAULT_LOCALE]
    if LOCALE_DIR.is_dir():
        out += sorted(p.stem for p in LOCALE_DIR.glob("*.json"))
    return out


def install(locale: str) -> str:
    """換一種語言，回真的套上去的那一個。

    **讀不到檔案就退回英文，不拋例外**：一個少了翻譯檔的安裝應該是「英文版的
    d4t」，不是一個開不起來的 d4t（推廣鐵則）。
    """
    global _locale, _catalog
    use = str(locale or "") or DEFAULT_LOCALE
    if use == DEFAULT_LOCALE:
        _locale, _catalog = DEFAULT_LOCALE, {}
        return _locale
    path = LOCALE_DIR / ("%s.json" % use)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # 見上
        _locale, _catalog = DEFAULT_LOCALE, {}
        return _locale
    if not isinstance(raw, dict):
        _locale, _catalog = DEFAULT_LOCALE, {}
        return _locale
    _catalog = {str(k): str(v) for k, v in raw.items() if str(v).strip()}
    _locale = use
    return _locale


def tr(text: str) -> str:
    """把一句使用者面的話翻過去。**沒有翻譯就回原句。**

    它也把原句記進 :func:`seen` —— 那是產翻譯檔範本的依據。
    """
    src = str(text)
    if not src:
        return src
    _seen[src] = _seen.get(src, 0) + 1
    return _catalog.get(src, src)


def seen() -> Dict[str, int]:
    """這一輪流過 :func:`tr` 的每一句原句 → 出現幾次。"""
    return dict(_seen)


def missing() -> List[str]:
    """流過 :func:`tr` 但這份 catalog 沒有的句子（照出現次數由多到少）。

    「先翻哪一句」有一個依據 —— 出現最多次的那一句，使用者看到它的機會最大。
    """
    if _locale == DEFAULT_LOCALE:
        return []
    return [t for t, _n in sorted(_seen.items(), key=lambda kv: -kv[1])
            if t not in _catalog]


def forget() -> None:
    """清掉 :func:`seen`（測試用 —— 它是行程層的狀態）。"""
    _seen.clear()
