# d4t Studio — 區域名怎麼講給人聽（PR-2，2026-08-27）。
"""`<n>` / `<n>_center` / `<n>_others` 三個埠對使用者是三個謎 —— 這一份是
它們的**一句話**，而且是唯一的一份：畫布的埠 hover、GLV 面板的標題、
Profile 檢視器的斜線圖例都從這裡拿字。三個地方各寫一份的話，同一顆埠會在
兩個畫面上有兩種說法（CLAUDE.md §0 的那條規矩）。

後綴的**語意**不住這裡：`_util.region_family` 是那三個名字的唯一產地，
`role_of` 只是把它的後綴翻成角色 —— 這不是「拆特徵字串猜語意」（那條禁令
管的是特徵名），區域名的後綴本來就是宣告出來的契約。
"""
from __future__ import annotations

from ..core.steps._util import CENTRE_SUFFIX, OTHERS_SUFFIX

__all__ = ["ROLE_ALL", "ROLE_CENTER", "ROLE_OTHERS", "role_of",
           "PORT_HOVER", "INTENT_PHRASE", "LEFT_OUT_LEGEND"]

ROLE_ALL = "all"
ROLE_CENTER = "center"
ROLE_OTHERS = "others"


def role_of(name: str) -> str:
    """區域（埠）名 → 角色。認不得的後綴一律當 `<n>`（全部的框）。"""
    n = str(name or "")
    if n.endswith(CENTRE_SUFFIX):
        return ROLE_CENTER
    if n.endswith(OTHERS_SUFFIX):
        return ROLE_OTHERS
    return ROLE_ALL


#: 菱形埠 hover 的一句話（畫布用；GLV tab_tooltip 也引用同一句）。
PORT_HOVER = {
    ROLE_ALL: "all the boxes",
    ROLE_CENTER: "the defect's box (a patch is guaranteed centred on it)",
    ROLE_OTHERS: "the other boxes = the reference",
}

#: 面板標題的意圖語言（接了 `_center` 時 GLV 標題講「缺陷那格」而不是裸名）。
INTENT_PHRASE = {ROLE_CENTER: "the defect's box"}

#: Profile 檢視器角落的圖例字（斜線色塊旁邊那一句）。
LEFT_OUT_LEGEND = "boxes left out (different material)"
