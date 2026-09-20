# -*- coding: utf-8 -*-
"""**畫布、Features、Results 三塊互相指**（F117 I6）。

走查記的是「這三塊之間可以互相指」。它們講的是同一顆 defect 的三個面向 ——
畫布是**怎麼算的**、Features 是**算出什麼**、Results 是**一整批算出什麼** ——
而在這之前，從一個數字回頭找到算它的那張卡，靠的是使用者自己記得。

兩條路，而**它們刻意不一樣**：

* **滑過 Features 的一段** → `reveal_cards`（hover 那一套）。只是看一眼，
  所以不動右邊的設定；滑鼠一離開就熄掉。
* **Results 欄名的選單** → `select_node`（真的選取）。那是「帶我去」，
  他點下去就是要動手改。

**形狀**：模組層函式吃 `win`（同 `ui/studio_layout.py`、`ui/canvas_edges.py`）
—— 這一族**沒有自己的狀態**，全部讀寫 `win`。開一支新模組而不是塞進
`studio.py`，理由見 `CLAUDE.md` §4：那一格是 `HARD_CAPS`，只准往下。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from d4t.core.log import swallowed

if TYPE_CHECKING:                      # 只給型別看：這一支不 import studio
    from .studio import StudioWindow


def hover_card(win: "StudioWindow", node_id: str) -> None:
    """滑過 Features 的一段 → 在畫布上指出算它的那張卡。

    ⚠ **`reveal_cards` 不是 `select_card`**：選取會把右邊的設定換成那張卡，
    而使用者現在只是在讀數字 —— 他要的是眼睛找到來源，不是換一張卡編。

    ⚠ **空字串 = 熄掉。** 沒有這一半的話，滑鼠移出面板之後那張卡會一直亮著，
    而使用者早就不在看它了。
    """
    nid = str(node_id or "")
    for view in win._canvases():
        if nid:
            view.reveal_cards([nid])
        else:
            view.clear_tree_ghosts()


def go_to_feature(win: "StudioWindow", feature: str) -> None:
    """Results 的欄名選單 → **跳到**算那一欄的那張卡。

    ⚠ 找不到的時候**要講**：一個點下去什麼都沒發生的選單項，會讓使用者以為
    是自己點錯了。那句話講得出「畫布上沒有東西在算它」—— 而那通常表示那一欄
    是上一批跑出來的，recipe 已經改過了。
    """
    name = str(feature or "")
    nid = node_of_feature(win, name)
    if not nid:
        win._status("Nothing on the canvas measures “%s”." % name)
        return
    # Results 是另一個視窗 —— 選了卡片之後要把主視窗帶到前面，不然「跳過去」
    # 那件事發生在使用者看不到的地方。
    win.raise_()
    win.activateWindow()
    win.select_node(nid)


def node_of_feature(win: "StudioWindow", feature: str) -> str:
    """哪一張卡寫出這個數字（找不到回空字串）。

    **問 `bound_specs`，不自己拆字串** —— `test_epi_hot_glv_median` 裡哪一段
    是流、哪一段是區域、哪一段是使用者自己取的名字，三者都是任意識別碼，
    而「誰產出它」那份宣告本來就在（同 `studio._feature_specs` 的理由）。
    """
    from ..core.pipeline.verdict_features import bound_specs

    name = str(feature or "")
    if not name:
        return ""
    try:
        for b in bound_specs(win.model.to_recipe(), win.model.kind):
            if str(b.spec.name) == name:
                return str(b.node_id)
    except Exception:  # 顯示層：問不出來就當作沒有
        swallowed("cross_links.node_of_feature")
    return ""
