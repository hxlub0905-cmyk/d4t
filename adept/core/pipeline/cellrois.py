# ADEPT pipeline contract — authored 2026-08-18 (F11 Region-1).
"""標在 Golden Cell 上的具名區域：**一個名字，好幾個矩形**。

這是什麼
--------
``roi_template`` 的框以前是四個手打的數字（``roi_x/y/w/h``）加一個名字
（``roi_out``）—— 一張卡只框得出**一個矩形、一個區域**。但站點要的東西不長
那樣：使用者的原話是「一個 layout 是橫向 EPI 跟直向 MG 交錯，我要的 ROI1 是
EPI 部分扣掉 MG 交集」。**那個形狀用一個矩形表達不出來，用好幾個就可以**
（半導體 layout 幾乎都是曼哈頓的，見 F11 §3.3.2 的答案 B）。

所以值變成：

    ROI1: 0.1,0,0.25,1; 0.62,0,0.25,1 | ROI2: 0.4,0.2,0.15,0.5

``區域 | 區域``、``名字: 框; 框; 框``、每個框 ``x,y,w,h``。

為什麼是一行字串而不是巢狀 JSON
--------------------------------
``curve`` 當初定下的規則，這裡照用（不為第二個參數破例）：**``ParamSpec`` 的
值一律是純量** —— UI 表單、rescore、CLI ``--set`` 都靠這條規則。而 recipe 是
給人看、也給 git diff 看的 JSON：存成巢狀陣列，diff 會變成一整片括號；存成
上面那一行，一眼就看得出使用者把 ROI1 切成了兩塊。

座標相對於**一個 cell**，不是相對於 patch
------------------------------------------
這是這張卡最容易誤解的一件事（F11 §3.3.1 第 2 項）。``0.62,0,0.25,1`` 講的是
「從這一格的 62% 開始、寬佔這一格的 25%」，而**那一格在每張 patch 上的位置
是比對出來的**（相位）。patch 是以缺陷為中心裁的，所以同一個框在每張 patch 上
的像素座標都不一樣 —— 那正是模板定位存在的理由。

一個框不能比一格還大
--------------------
``w``/``h`` 上限是 1。框映到 patch 上時是**整片鋪過去**的（一格出現幾次就畫
幾個框，見 ``algo/template.roi_boxes_in_patch``），比一格還大的框鋪出去會蓋到
自己 —— 那個東西沒有意義，而它算得出數字，所以要擋在這裡（鐵則 4）。

為什麼放在 ``pipeline/`` 而不是 ``algo/``
-----------------------------------------
同 ``curve`` / ``channels``：``ParamSpec.validate`` 要用它，而 ``pipeline``
不該把整個 ``algo`` 套件（連帶 cv2）拉進 import 圖。**編碼**在這裡、純 stdlib；
**幾何**（框怎麼落到 patch 上）在 ``algo/template.py``。
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .curve import format_number

__all__ = ["CellRoiError", "Region", "Box", "parse_cell_rois",
           "format_cell_rois", "region_names", "array_boxes",
           "array_pitch", "regions_repeat_at", "SHIFT_TOL",
           "MAX_REGIONS", "MAX_BOXES"]

#: 一個框：``(x, y, w, h)``，相對於一個 cell（0–1）。
Box = Tuple[float, float, float, float]
#: 一個具名區域：``(名字, [框, …])``。
Region = Tuple[str, List[Box]]

#: 一張卡最多幾個區域／一個區域最多幾個框。
#:
#: 不是效能考量 —— 是**畫面**：右欄的清單超過這個數就翻不完，而框畫在 patch 上
#: 超過這個數就看不出哪個是哪個。真的需要幾百個框的時候，那件事該由 GLAS 的
#: label map 來做（Region-3），不是用手標。
MAX_REGIONS = 32
MAX_BOXES = 64


class CellRoiError(ValueError):
    """區域字串不合法。訊息是白話的 —— 會直接顯示在參數列下面。"""


def parse_cell_rois(text: object) -> List[Region]:
    """``"a: 0,0,1,1 | b: 0.2,0,0.3,1"`` → ``[("a", [(0,0,1,1)]), …]``。

    每一條規則都回一句白話錯誤（鐵則 4：壞值不准跑到演算法裡）：

    * 每一段的形狀是 ``名字: 框; 框; …``；
    * 名字要能當變數名用（區域名會變成特徵名的一部分）；
    * 同一個名字不能出現兩次（後面那個會蓋掉前面那個，而畫面上只看得到一個）；
    * 每個框是四個數字 ``x,y,w,h``；
    * ``w``/``h`` 大於 0 且不超過 1（一個框不能比一格還大 —— 見模組說明）；
    * ``x``/``y`` 在 −1…2（框可以跨過一格的接縫；再遠就等於同一個框的複本）。

    空字串（或 ``None``）→ ``[]`` ＝**還沒標任何區域**。那是新卡片的預設值，
    而「還沒標」是設定沒做完、不是參數填錯 —— 所以它在這裡合法，由卡片的
    ``configuration_issues`` 講出來（跟 ``template`` 空著時同一條路）。
    """
    # 這個 import 刻意放在函式裡：``step`` 在 module level import 這個模組
    # （``ParamSpec.validate`` 要用），module level 互相 import 會成環。
    # 規則只有一份 —— 抄第二份出來的那份會漂移（同 channels.parse_channel_map）。
    from .step import STREAM_NAME_PATTERN
    import re

    s = "" if text is None else str(text).strip()
    if not s:
        return []

    out: List[Region] = []
    seen: List[str] = []
    for chunk in s.replace("\n", "|").split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise CellRoiError(
                "region '%s' should look like 'name: x,y,w,h' — the name, a "
                "colon, then one or more boxes separated by ';'" % chunk)
        name, _sep, body = chunk.partition(":")
        name = name.strip()
        if not re.match(STREAM_NAME_PATTERN, name):
            raise CellRoiError(
                "region name '%s' cannot be used: use letters, digits and "
                "underscores only, and do not start with a digit (the name "
                "becomes part of every feature this region produces)" % name)
        if name in seen:
            raise CellRoiError(
                "region '%s' is defined twice; the second one would silently "
                "replace the first" % name)
        seen.append(name)

        boxes: List[Box] = []
        for part in body.split(";"):
            part = part.strip()
            if not part:
                continue
            boxes.append(_parse_box(name, part))
        if not boxes:
            raise CellRoiError(
                "region '%s' has no boxes; a region with nothing in it "
                "measures nothing" % name)
        if len(boxes) > MAX_BOXES:
            raise CellRoiError(
                "region '%s' has %d boxes; the limit is %d (past that they "
                "cannot be told apart on screen)" % (name, len(boxes), MAX_BOXES))
        out.append((name, boxes))

    if len(out) > MAX_REGIONS:
        raise CellRoiError(
            "%d regions were given; the limit is %d" % (len(out), MAX_REGIONS))
    return out


def _parse_box(region: str, part: str) -> Box:
    bits = [b.strip() for b in part.split(",")]
    if len(bits) != 4:
        raise CellRoiError(
            "box '%s' of region '%s' should be four numbers 'x,y,w,h' as a "
            "fraction of one cell" % (part, region))
    try:
        x, y, w, h = (float(b) for b in bits)
    except ValueError:
        raise CellRoiError(
            "box '%s' of region '%s' is not four numbers" % (part, region)
        ) from None
    if not (w > 0.0 and h > 0.0):
        raise CellRoiError(
            "box '%s' of region '%s' has no width or no height" % (part, region))
    if w > 1.0 or h > 1.0:
        raise CellRoiError(
            "box '%s' of region '%s' is bigger than one cell; the box repeats "
            "with the pattern, so a box larger than one cell would overlap "
            "itself" % (part, region))
    if not (-1.0 <= x <= 2.0 and -1.0 <= y <= 2.0):
        raise CellRoiError(
            "box '%s' of region '%s' sits more than one cell away; a box that "
            "far out is the same box repeated" % (part, region))
    return (x, y, w, h)


def format_cell_rois(regions: Sequence[Region]) -> str:
    """區域 → 標準字串。

    正規化的理由跟 ``curve`` / ``channel_map`` 一樣：手打的
    ``"a:0.2000,0,0.3,1"`` 與編輯器拉出來的 ``"a: 0.2,0,0.3,1"`` 要在 recipe
    裡長得**一樣**，不然 round-trip 不是 identity —— 而 ``to_json_dict →
    from_json_dict`` 是 ``run_batch`` 送 recipe 進 worker 的路，它一旦不是
    identity，``workers=1`` 與 ``workers=2`` 就會算出不同的分數（鐵則 9，
    真的發生過，見 docs/PITFALLS.md）。

    **順序照留**（區域之間、框之間都是）。排序會讓編輯器裡的清單在每次拖曳
    之後跳動，而順序不影響結果 —— 這裡要的是穩定，不是字典序。
    """
    parts = []
    for name, boxes in regions:
        body = "; ".join(",".join(format_number(v) for v in box)
                         for box in boxes)
        parts.append("%s: %s" % (str(name), body))
    return " | ".join(parts)


def region_names(text: object) -> List[str]:
    """字串裡有哪些區域名（給 ``resolve_regions_out`` 與 UI 的下拉用）。

    壞字串回 ``[]`` 而不是拋 —— 呼叫端問的是「有哪些名字」，而 lint 與
    ``validate_params`` 已經會把壞值講出來。宣告在這裡多拋一次只會讓畫布在
    使用者打到一半的時候整個消失。
    """
    try:
        return [name for name, _boxes in parse_cell_rois(text)]
    except CellRoiError:
        return []


def array_boxes(first_centre: Tuple[float, float],
                last_centre: Tuple[float, float],
                box_w: float, box_h: float,
                nx: int, ny: int,
                cell_size: Optional[Tuple[int, int]] = None) -> List[Box]:
    """一次長出一整片**等距**的框（編輯器的 multi add）。

    為什麼要這個工具
    ----------------
    使用者要的區域是「整排 EPI」這種東西 —— 一根一根拉，第 20 根的時候間距
    已經歪掉了，而歪掉的框在畫面上看不太出來，在數字上看得出來。等距這件事
    是**設計常數**（pitch），所以它該由兩個端點算出來，不是拖出來。

    參數的形狀照使用者定的：兩個錨點（左上那格的中心、右下那格的中心）、
    框的大小、以及**兩個錨點之間有幾個框**（含頭尾）。所以間距 = 端點距離 ÷
    (n − 1)，而不是另外再輸入一個 pitch —— 端點看得見，pitch 看不見。

    ``cell_size``：給了就在**整數 cell 像素**上排（見下）。

    間距要不要取整（使用者 2026-08-18 回報，然後自己推翻了第一版）
    --------------------------------------------------------------
        「MULTI ADD 像素 PERIOD 會不穩定，舉例有 9 個 BOX，PERIOD 我去看表格
         有時是 29 有時是 30，這樣會造成在畫布顯示也對不齊。」

    第一版的處置是「間距先取整、再從第一個錨點排下去」——**那個修法是錯的**，
    使用者當場問回來：「改成非整數會比較好嗎（主要是畫面，因為 patch 對
    template 是對圖）」。對：

    * 整數 30 對上真實的 29.5 → 誤差**累積**：第 9 個框偏 4 px。6 px 寬的 EPI
      上那是量到隔壁去了。
    * 精確 29.5 → 每一個框都在真實位置的半個像素內，只是**表格上**看起來是
      29／30 交錯。

    而真正的重點是**該在哪裡取整**：``algo/template.roi_boxes_in_patch`` 本來
    就會在落到 patch 上的時候 ``round(x·cx − phase)``，而每一顆 patch 的相位
    不同 —— 同一個小數座標在不同 patch 上落到不同的整數像素，**那正是對的**，
    它追的是那一顆上結構真正的位置。編輯器先取整等於把誤差烤進去。

    所以：**框的大小**照使用者打的整數像素，**位置**保持精確的小數。
    手拉的框（drag／click／paint）仍然吸附到整數 —— 那時候使用者是對著一個
    像素邊在瞄，整數就是他的意圖。
    """
    nx, ny = max(1, int(nx)), max(1, int(ny))
    x1, y1 = float(first_centre[0]), float(first_centre[1])
    x2, y2 = float(last_centre[0]), float(last_centre[1])
    w, h = float(box_w), float(box_h)

    if cell_size:
        cw, ch = int(cell_size[0]), int(cell_size[1])
        # 大小取整（使用者打的就是整數 px），位置不取整（見上）
        w = max(1, int(round(w * cw))) / float(cw)
        h = max(1, int(round(h * ch))) / float(ch)

    def centres(a: float, b: float, n: int) -> List[float]:
        if n <= 1:
            return [a]
        step = (b - a) / float(n - 1)
        return [a + step * i for i in range(n)]

    out: List[Box] = []
    for cy in centres(y1, y2, ny):
        for cx in centres(x1, x2, nx):
            out.append((cx - w / 2.0, cy - h / 2.0, w, h))
    return out


def array_pitch(first_centre: Tuple[float, float],
                last_centre: Tuple[float, float],
                nx: int, ny: int,
                cell_size: Tuple[int, int]) -> Tuple[float, float]:
    """:func:`array_boxes` 實際用的間距（cell 像素，**可以是小數**）。

    給提示列顯示。使用者要看得到它 —— 表格上那個 29／30 交錯，其實是同一個
    29.5；把它講出來，「不穩定」這件事就消失了（它本來就沒有不穩定）。
    """
    cw, ch = int(cell_size[0]), int(cell_size[1])
    dx = (float(last_centre[0]) - float(first_centre[0])) * cw
    dy = (float(last_centre[1]) - float(first_centre[1])) * ch
    px = dx / float(nx - 1) if int(nx) > 1 else 0.0
    py = dy / float(ny - 1) if int(ny) > 1 else 0.0
    return (px, py)


#: 判斷「平移之後落回自己」時，兩個框差多少還算同一個（相對於一格）。
#: 1/2000 格 —— 一個 300 px 的 cell 上是 0.15 px，比任何有意義的差都小。
SHIFT_TOL = 5e-4


def regions_repeat_at(regions: Sequence[Region], shift_x: float,
                      shift_y: float, tol: float = SHIFT_TOL) -> bool:
    """把**每一個**區域的每一個框平移 ``(shift_x, shift_y)``，會落回自己嗎。

    為什麼要問這個（F11 §3.3.7 的第 2 項）
    --------------------------------------
    使用者可以把 cell 取成量到的週期的 k 倍（「有時候會需要 2X 大 cell」）。
    那時候一顆 patch **分不出自己落在哪一份上** —— 而那件事**只有在兩份上標的
    區域不一樣的時候才要緊**：

    * 每一份都標一樣 → 兩個答案都對，歧義無害。
    * 兩份標得不一樣 → 這一顆可能量到另一份的東西，而**畫面上不會有任何錯誤
      訊息**。那是這條路上最後一個會安靜出錯的地方。

    所以它是一個可以判定的問題，不是一句要使用者自己小心的叮嚀：把框整組平移
    1/k，看集合是不是映射回自己。

    平移是**環狀**的（超過一格就繞回來），因為 cell 本來就是重複的。
    區域的名字也要對上 —— ROI1 平移之後落到 ROI2 的位置上不算數，那是兩個
    不同的量測。
    """
    sx, sy = float(shift_x) % 1.0, float(shift_y) % 1.0
    if sx < tol and sy < tol:
        return True                      # 沒有平移可言（k = 1）

    def key(box: Box):
        x, y, w, h = box
        return (round((x % 1.0) / tol), round((y % 1.0) / tol),
                round(w / tol), round(h / tol))

    for name, boxes in regions:
        here = {key(b) for b in boxes}
        moved = {key((b[0] + sx, b[1] + sy, b[2], b[3])) for b in boxes}
        if here != moved:
            return False
    return True
