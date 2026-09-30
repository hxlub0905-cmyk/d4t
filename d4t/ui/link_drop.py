# d4t Studio：一條線丟在卡上，接到哪一格 — authored 2026-09-30 (F124 期 4).
"""**拉線只有一個動作：從卡右邊的名字拖出來，丟到要用它的卡上。**

使用者（F124）：「user 不能有太多的學習成本」。以前要**瞄準**那一顆小埠；沒瞄
準（丟在卡上）的時候畫布會**安靜地挑高度最近的那一格**（`in_param_at` 的
退路）—— 丟在 Compare 偏上面就接 a、偏下面就接 b，而 a、b 反過來整張圖的正負號
就反了，畫面上看不出來。那是這個 repo 最怕的那種錯：跑得完、有數字、而且是錯的。

現在的規則
----------
* 丟在**埠上** → 接那一顆（跟以前一樣）。
* 丟在卡上、**只有一格**接得上這種線 → 直接接。
* **兩格以上** → 在放手的地方跳一個小選單，只列接得上的那幾格；單一格已經有線
  的寫明「會取代 ＿ 那條」。取消＝不接。
* **一格都接不上** → 照舊交給 `edit_plan` 講為什麼（它講得出來）。

選單是 modal 的，所以有一個關得掉的旗標（CLAUDE.md §4 F91）：:data:`ASK`。
測試關掉它（`tests/conftest.py`），要驗選單的測試用 :data:`CHOOSE` 換掉
「使用者挑了哪一個」。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from d4t.core.pipeline import get_step
from d4t.core.pipeline.step import DATA_PORTS

from . import strings, wording

__all__ = ["accepts", "drop_param", "options_for", "ASK", "CHOOSE"]

#: 兩格以上時要不要跳選單。關掉的話退回「最近的那一格」（F124 之前的行為）——
#: 只給 headless 測試用：一個 modal 選單在那裡會讓測試永遠停住。
ASK = True

#: 測試換掉「使用者從選單挑了哪一個」：``CHOOSE(title, options) -> 參數名或 None``，
#: ``options`` 是 ``[(參數名, 選單上的字), …]``。
CHOOSE: Optional[Callable[[str, List[Tuple[str, str]]], Optional[str]]] = None


def accepts(spec: Dict[str, Any], kind: str) -> bool:
    """這顆輸入埠收不收 ``kind`` 那種線（``accepts`` 沒寫就是它自己的那一種）。

    Output 的 ``results`` 埠兩種都收（F123 期 2：直接接量測卡也可以）。
    """
    return str(kind) in (spec.get("accepts")
                         or [str(spec.get("kind") or "image")])


def _takes_many(step_key: str, spec: Dict[str, Any]) -> bool:
    """這一格可以接好幾條（``*_keys`` 或資料埠）—— 丟進去是**加一條**，不是換掉。"""
    if str(spec.get("kind") or "") in DATA_PORTS:
        return True
    try:
        params = get_step(step_key).params
    except KeyError:
        return False
    name = str(spec.get("name", ""))
    return any(p.name == name and str(p.type).endswith("_keys") for p in params)


def options_for(view: Any, dst_item: Any, kind: str
                ) -> List[Tuple[str, str]]:
    """丟在 ``dst_item`` 上時接得上的那幾格：``[(參數名, 選單上的字), …]``。"""
    specs = dst_item.in_specs()
    step_key = str(dst_item.info.get("step_key", ""))
    out: List[Tuple[str, str]] = []
    for i, spec in enumerate(specs):
        if not accepts(spec, kind):
            continue
        text = wording.port_word(spec.get("label") or spec.get("name", ""))
        if not _takes_many(step_key, spec):
            there = [e.src for e in getattr(view, "_edges", ())
                     if e.dst is dst_item and e.dst_port == i]
            if there:
                text += " - " + strings.tr("replaces the line from") + \
                    " “%s”" % there[0].title()
        out.append((str(spec.get("name", "")), text))
    return out


def _menu(view: Any, title: str, options: Sequence[Tuple[str, str]],
          global_pos: Any) -> Optional[str]:
    """放手的地方跳一個小選單；回挑的那一格，取消回 ``None``。"""
    from PySide6.QtWidgets import QMenu

    menu = QMenu(view)
    head = menu.addAction(title)
    head.setEnabled(False)
    menu.addSeparator()
    picks = {}
    for name, text in options:
        picks[menu.addAction(text)] = name
    chosen = menu.exec(global_pos)
    return picks.get(chosen)


def drop_param(view: Any, dst_item: Any, kind: str, stream: str,
               scene_pos: Any) -> Optional[str]:
    """一條 ``kind`` 線（吐 ``stream``）丟在 ``dst_item`` 上 → 接到哪一格。

    ``None`` = 使用者從選單取消了（不接）。其餘見模組說明的四條規則。
    """
    local = dst_item.mapFromScene(scene_pos)
    specs = dst_item.in_specs()
    idx = dst_item.in_port_at(local)
    if idx is not None and idx < len(specs):
        return str(specs[idx].get("name", ""))
    options = options_for(view, dst_item, kind)
    if len(options) == 1:
        return options[0][0]
    if not options or (not ASK and CHOOSE is None):
        return dst_item.in_param_at(local, kind)
    title = strings.tr("Connect") + " “%s” " % wording.port_word(stream) + \
        strings.tr("to:")
    if CHOOSE is not None:
        return CHOOSE(title, list(options))
    global_pos = view.mapToGlobal(view.mapFromScene(scene_pos))
    return _menu(view, title, options, global_pos)
