# d4t Studio — 「插入數字 ▾」：一個下拉、三個家（2026-09-09）。
"""可以拿來用的數字，填進一個下拉 —— **一張卡一組、組名點不到、每一項帶
一句它是什麼**。

三個地方用同一支：判定面板（let 行、score）、判定樹那一步（導引式的
「pick a number」與算式框旁的那支）、以及**每張卡的設定區**（`ParamForm`
的 `feature_key` / `feature_keys` 那幾格 —— Output 卡的 `rank_by` /
`plot_features` / `columns`）。以前它們是三份各自寫的平清單，長相不一樣、
而且只有前兩個列 working numbers（使用者 2026-09-09：「Output card 中也要
能夠連動 working numbers」）。

為什麼是一支新模組而不是塞進 `decide_panel`：`param_form` 也要用它，而
`decide_panel` import `widgets`、`widgets` 轉出口 `param_form` —— 從
`param_form` 反過來 import `decide_panel` 是一個圈。CLAUDE.md §4：一塊新
元件一個新模組。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox

from .fields import region_dot_icon
from .param_form import split_labelled
from .viewmodel import RecipeModel

__all__ = ["DECISION_GROUP", "fill_number_picker", "number_tips"]

#: working numbers 那一組的標題 —— 跟 `RecipeModel.DECISION_LABEL` 同一個字。
DECISION_GROUP = RecipeModel.DECISION_LABEL


def number_tips(model: Any) -> Dict[str, str]:
    """名字 → 滑鼠停上去那一句（2026-09-09，使用者：「user 會不會混淆 or
    看不懂」—— 會，而且 `glv_stats.py` 記著 2026-09-02 有人問過一模一樣的
    「typical 跟 outliner、worst、score 是指什麼」）。

    卡片算的那些走 `feature_gloss`（**跟 Feature 表那一欄同一支**，說明只有
    一個家）＋ `feature_unit`；判定段自己算的（let）講它的算式、fill 與
    scale —— 那三件事 spec 上沒有，只有 model 的 `decide.let` 知道。
    查不到的留白：少一句話，不會是錯的一句話。
    """
    from .feature_text import feature_gloss, feature_unit

    out: Dict[str, str] = {}
    if model is None:
        return out
    lets: Dict[str, Any] = {}
    d = getattr(model, "decide", None)
    for item in (d.let if d is not None else []):
        if not item.is_blank and str(item.name).strip():
            lets[str(item.name).strip()] = item
    getter = getattr(model, "bound_feature_specs", None)
    for b in (getter() if callable(getter) else []):
        spec = b.spec
        name = str(spec.name)
        if spec.family == "engine" and spec.base in lets:
            let = lets[spec.base]
            var = str(spec.variant or "")
            if var == "missing":
                tip = ("1 when '%s' could not be worked out on this defect "
                       "and used its fallback (%s); 0 otherwise"
                       % (spec.base, let.fill))
            elif var == "raw":
                tip = ("'%s' as measured on this defect, before it was "
                       "scaled against the batch" % spec.base)
            else:
                tip = "= %s" % let.expr
                if str(let.fill or ""):
                    tip += "\nif missing \u2192 %s" % let.fill
                if str(let.scale or ""):
                    tip += "\nscaled against the batch (%s)" % let.scale
            out[name] = tip
            continue
        _kind, text = feature_gloss(name, spec=spec)
        unit = feature_unit(spec)
        if text:
            out[name] = ("%s  [%s]" % (text, unit)) if unit else text
    return out


def fill_number_picker(combo: QComboBox, items: Sequence[str],
                       regions: Optional[Dict[str, int]] = None,
                       placeholder: str = "",
                       tips: Optional[Dict[str, str]] = None) -> None:
    """把「可以拿來用的數字」填進一個下拉 —— **一張卡一組，組名不能點**。

    2026-09-09 使用者：「ADC 下拉選單分類可以再做更好一點嗎」。在這之前它是
    一條平的清單，每一項寫「名字 — 誰算的」：`glv_stats` 開 each box 之後
    一張卡就吐 55 個名字，於是「誰算的」那半邊在 55 列上重複 55 次，而真正
    要掃的那半邊（名字）被推到不同的起點。現在「誰算的」只出現一次，當那一
    組的標題；名字齊頭排在它底下。

    * 組的順序＝清單上第一次出現的順序（卡片的執行順序）；**working numbers
      永遠第一組** —— 那是使用者自己剛取的名字，找它的人最多。
    * 標題列 **disabled**：滑鼠點不到、鍵盤跳過它，`activated` 永遠只帶回
      一個真的名字。
    * 沒有「誰算的」的項目（recipe 裡指到、但清單上沒有的舊名字）不掛標題，
      排在最前面 —— 它是使用者的東西，不是我們知道來歷的東西。
    * 每一項的 ``UserRole`` 就是要插進算式的裸名，所以 ``combo.itemData`` /
      ``findData`` 跟以前一字不差；區域的顏色點也還在。
    """
    from PySide6.QtGui import QStandardItem, QStandardItemModel

    regions = dict(regions or {})
    model = QStandardItemModel(combo)
    head = QStandardItem(str(placeholder))
    head.setData("", Qt.UserRole)
    model.appendRow(head)

    groups: Dict[str, List[str]] = {}
    order: List[str] = []
    for it in items:
        name, owner = split_labelled(it)
        if not name:
            continue
        if owner not in groups:
            groups[owner] = []
            order.append(owner)
        if name not in groups[owner]:
            groups[owner].append(name)
    # 沒有來歷的排最前，working numbers 次之，其餘照出現順序。
    front = [o for o in ("", DECISION_GROUP) if o in groups]
    order = front + [o for o in order if o not in front]

    for owner in order:
        if owner:
            title = QStandardItem(str(owner))
            title.setFlags(Qt.NoItemFlags)
            title.setData("", Qt.UserRole)
            model.appendRow(title)
        for name in groups[owner]:
            idx = regions.get(name, -1)
            item = (QStandardItem(region_dot_icon(idx), name) if idx >= 0
                    else QStandardItem(name))
            item.setData(name, Qt.UserRole)
            # 滑鼠停上去講它是什麼（`number_tips`）—— 名字本身講不出
            # 「_worst 是 z 分數最高那一格身上的量」那種事。
            tip = str((tips or {}).get(name, "") or "")
            if tip:
                item.setData(tip, Qt.ToolTipRole)
            model.appendRow(item)
    combo.setModel(model)
    combo.setCurrentIndex(0)
