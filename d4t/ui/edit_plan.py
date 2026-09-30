# 畫布上拉一條線是什麼意思 — 從 studio.py 抽出來 2026-09-08 (U6).
"""**接線／換線／剪線的語意住在這裡，而這裡一行 Qt 都沒有。**

為什麼要抽出來
--------------
`_connect` / `_connect_region` / `_drop_conflicting_edges` / `_unpoint_stream`
/ `_unmet_needs` / `_producers_of` 是**引擎正確性的一半** —— F9／F10／F42 那
三輪踩過的七個「跑得完、有數字、而且是錯的」，全部發生在這幾支裡：

* 同一個輸入埠上留了兩條線，引擎只認其中一條，而畫面上看不出是哪一條；
* 剪一條線連旁邊那條一起剪掉，卡片還指著一條沒有線的流；
* 區域線被當成影像流算進「這張卡已經有什麼」。

而它們住在一個 7,000 行的 `QMainWindow` 裡 —— 要驗其中任何一條，都得先開一個
視窗。**這一份把「決定」搬出來，讓它們可以在沒有 QApplication 的情況下問。**

分界線在哪
----------
這裡只回答「**應該發生什麼**」：這條線落在哪一格、是影像還是區域、哪幾條舊線
要讓位、那一格的值會變成什麼、要對使用者說哪一句話。

**真的動 model 的仍然是 `StudioWindow`** —— 因為那一段的順序有意義
（`add_edge` 會因為成環而失敗，而失敗的那條線不該留下任何痕跡），而順序不是
一個純函式講得清楚的東西。硬要把 mutation 也包進來，就得在這裡把 model 模擬
一遍，那是把一個難的東西換成兩份會漂的東西。

⚠ **這一份吃的是 `RecipeModel`，而它本來就不碰 Qt**（`ui/viewmodel.py`）。
所以這裡的每一支都是純函式：吃 model、回答案，不改任何東西。
"""
from __future__ import annotations
from d4t.core.log import swallowed

from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional

from ..core.pipeline import get_step, list_steps
from ..core.pipeline.recipe import is_data_edge, is_region_edge
from ..core.pipeline.step import DATA_PORTS, NUMBERS, REGION_TYPES, RESULTS
from . import wording
from .scope import visible_steps

__all__ = [
    "IMAGE", "REGION", "DATA", "REJECT", "ConnectPlan", "UnpointPlan",
    "line_kind", "is_region_param", "param_for_stream", "conflicting_edges",
    "region_conflicts", "plan_connect", "plan_unpoint", "producers_of",
    "unmet_needs", "copyable_params",
]

#: 「這條線接不上」時 `plan_connect` 用的 kind。
REJECT = "reject"
#: 影像流的線。
IMAGE = "image"
#: 具名區域的線（畫布上是虛線 + 菱形埠）。
REGION = "region"
#: 數字線與結果線（F123 期 2）：量測卡 → Decision → Output。
DATA = "data"


@dataclass
class ConnectPlan:
    """拉一條線之後**應該發生什麼**（不含真的去做）。

    ``kind`` 是三種之一：

    * :data:`IMAGE` —— 一條影像流的線；
    * :data:`REGION` —— 一條區域線；
    * :data:`REJECT` —— 接不上，:attr:`reject` 是要對使用者說的那一句。

    :attr:`already` 非空 = 這條線已經在了，什麼都不用做（那一句仍然要說 ——
    使用者剛做了一個動作，畫面上沒有回音比較糟）。
    """

    kind: str
    param: str = ""
    reject: str = ""
    already: str = ""
    #: 影像流那一側：這一格上已經有線了嗎（有 = 累加，沒有 = 設定它）。
    accumulate: bool = False
    #: 要一起拿掉的舊線（「一個輸入埠只能有一條線」，F9-7）。
    conflicts: List[Any] = field(default_factory=list)

    def ok(self) -> bool:
        return self.kind in (IMAGE, REGION, DATA) and not self.reject


@dataclass
class UnpointPlan:
    """剪掉一條線之後，下游那一格的值該變成什麼。

    :attr:`change` 是 False 時什麼都不要動 —— 而那**不是**「沒事發生」的同義
    詞：區域那一格的值是從線水合出來的（F42 B2），在這裡動它等於讓參數跟線
    說不同的話。
    """

    change: bool = False
    param: str = ""
    value: str = ""
    #: 那一格的顯示名（訊息裡用）。
    label: str = ""


# --------------------------------------------------------------------------- #
# 這條線是什麼、落在哪一格
# --------------------------------------------------------------------------- #
def line_kind(model: Any, node_id: str, name: str) -> str:
    """從 ``node_id`` 的哪一顆埠拉出來的 —— 影像還是區域。

    判準是**那顆埠是哪一種**，而且讀的就是畫布畫埠用的那一份
    （`RecipeModel.region_outputs`，含原樣送出的）—— 畫的跟判的分家的話，
    使用者會拉得到一條「看起來接上了、其實沒有」的線。
    """
    if not name:
        return IMAGE
    return (REGION if str(name) in model.region_outputs(str(node_id))
            else IMAGE)


def is_region_param(model: Any, node_id: str, param: str) -> bool:
    """``node_id`` 的 ``param`` 那一格吃的是具名區域嗎。"""
    node = model.nodes.get(str(node_id))
    if node is None or not param:
        return False
    try:
        specs = get_step(node.step).region_input_specs()
    except KeyError:                       # pragma: no cover
        return False
    return any(sp.name == str(param) for sp in specs)


def param_for_stream(model: Any, node_id: str) -> str:
    """線沒有指定落點時，這條線該接哪一格輸入（沒有輸入回空字串）。

    F10 起**正常路徑不會走到這裡** —— 使用者放開滑鼠的位置就是落點。
    這是給程式化拉線（測試、之後可能的自動排版）用的退路，判準是
    「第一個**還空著**的輸入」：接第二條線時它自然落到還沒接的那一格，
    而不是又去蓋掉第一格。

    以前這裡是一張寫死的名單（``streams`` → ``target`` → ``source``），
    於是 ``subtract`` 的 ``a`` / ``b`` 永遠只挑得到一個 —— 兩顆輸入的卡在畫布
    上根本分不開。名單也不會自己認得之後加的卡。
    """
    node = model.nodes.get(str(node_id))
    if node is None:
        return ""
    try:
        specs = [sp for sp in get_step(node.step).input_specs()
                 if sp.visible_for(node.params)]
    except KeyError:                       # pragma: no cover
        return ""
    if not specs:
        return ""
    for spec in specs:
        if not str(node.params.get(spec.name, "") or "").strip():
            return spec.name
    return specs[0].name


# --------------------------------------------------------------------------- #
# 一個輸入埠只能有一條線（F9-7）
# --------------------------------------------------------------------------- #
def conflicting_edges(model: Any, src: str, dst: str, stream: str,
                      param: str) -> List[Any]:
    """哪幾條舊線跟這條新線**搶同一個輸入**。

    什麼叫搶同一個輸入
    ------------------
    引擎是用 ``(下游節點, 流名)`` 去查資料從哪來的（``_explicit_bindings``），
    所以同一個 key 只能有一個來源。兩條線落在同一個 key 上時，**dict 後寫的
    贏** —— 也就是「``recipe.edges`` 裡排在後面的那條」，而那個順序在畫布上
    完全看不出來。

    - ``image_key``（``subtract`` 的 ``a``／量測卡的 ``source``）：一個參數就是
      一個角色，同一個參數上的舊線一律讓位。
    - ``image_keys``（Enhance 卡的 ``streams``，可以同時做好幾條）：只有
      **同一條流名**才算搶 —— 一條給 test、一條給 ref 是兩個 key，本來就該並存。

    ⚠ 判準是「**不是剛拉的這一條**」而不是「來源不同的那些」（F10 修）：
    從**同一張卡**先拉 test 再拉 ref 到同一顆角色埠時，來源相同 —— 舊的判準把
    它放過去，於是參數換成了 ref、而畫布上兩條線都還在。
    """
    node = model.nodes.get(str(dst))
    if node is None or not param:
        return []
    try:
        spec = {p.name: p for p in get_step(node.step).params}.get(param)
    except KeyError:                       # pragma: no cover
        return []
    if spec is None:
        return []
    return [e for e in list(model.edges)
            if e.dst == str(dst) and e.dst_in == param
            and not (e.src == str(src) and e.src_out == str(stream))
            and (spec.type == "image_key" or e.src_out == str(stream))]


def region_conflicts(model: Any, src: str, dst: str, name: str,
                     param: str) -> List[Any]:
    """區域那一側的同一條規矩（F12 §7-②）。

    ``region_key`` 那一格只放得下一個名字，所以第二條線是「改接別的」不是
    「這個也算」—— 同一格上的舊線全部讓位。``region_keys`` 是清單，第二條是
    累加，所以一條都不讓位。
    """
    node = model.nodes.get(str(dst))
    if node is None or not param:
        return []
    try:
        spec = next((sp for sp in get_step(node.step).region_input_specs()
                     if sp.name == param), None)
    except KeyError:                       # pragma: no cover
        return []
    if spec is not None and spec.type == "region_keys":
        return []
    return [e for e in list(model.edges)
            if e.dst == str(dst) and e.dst_in == param
            and not (e.src == str(src) and e.src_out == str(name))]


# --------------------------------------------------------------------------- #
# 拉一條線
# --------------------------------------------------------------------------- #
def plan_connect(model: Any, src: str, dst: str, stream: str,
                 dst_in: str = "") -> ConnectPlan:
    """使用者從 ``src`` 拉一條 ``stream`` 到 ``dst`` —— **應該發生什麼**。

    落點由呼叫端給（使用者放開滑鼠的那一格，F10）；沒給才自己挑
    （:func:`param_for_stream`）。
    """
    data = _plan_data(model, src, dst, stream, str(dst_in or ""))
    if data is not None:
        return data
    param = str(dst_in or "") or param_for_stream(model, dst)
    kind = line_kind(model, src, stream)
    region_param = is_region_param(model, dst, param)

    # **區域線走的是同一條路，只是守門的話不一樣**（F42 B2）。
    if region_param or kind == REGION:
        return _plan_region(model, src, dst, stream, param, kind, region_param)
    return _plan_image(model, src, dst, stream, param)


def _plan_data(model: Any, src: str, dst: str, port: str,
               dst_in: str) -> Optional[ConnectPlan]:
    """數字線與結果線（F123 期 2）；不是資料線回 ``None``（走影像／區域那兩條）。

    判準兩頭都看：從資料出埠拉出來的（``numbers`` / ``results``），或落在資料
    入埠上的。擋的四件事每一件都講得出下一句話：資料線只進 Decision 與 Output；
    Decision 只收數字；影像與區域進不了資料埠；線本來就在。**一顆資料埠接很多條**
    —— 沒有「擠掉舊線」這一步。
    """
    s, d = model.nodes.get(src), model.nodes.get(dst)
    if s is None or d is None:
        return None
    try:
        s_cls, d_cls = get_step(s.step), get_step(d.step)
    except KeyError:                       # pragma: no cover
        return None
    sends = s_cls.data_output(s.params)
    from_data = bool(port) and port == sends and port in DATA_PORTS
    into = dst_in if dst_in in d_cls.data_inputs else ""
    if not from_data and not into:
        return None
    if not from_data:
        return ConnectPlan(
            kind=REJECT, param=into,
            reject="“%s” takes %s here - that line carries an image or a "
                   "region. Drag from the %s port of a measuring card."
                   % (dst, wording.port_word(into), wording.port_word(NUMBERS)))
    takes = (RESULTS if RESULTS in d_cls.data_inputs
             else NUMBERS if (port == NUMBERS and NUMBERS in d_cls.data_inputs)
             else "")
    if not takes:
        why = ("a Decision takes numbers, not the results of a decision"
               if d_cls.data_inputs else
               "numbers go into a Decision or an Output card")
        return ConnectPlan(kind=REJECT, param=into,
                           reject="“%s” cannot take %s - %s."
                                  % (dst, wording.port_word(port), why))
    if model.has_line(src, dst, port, takes):
        return ConnectPlan(kind=DATA, param=takes,
                           already="%s → %s is already connected." % (src, dst))
    return ConnectPlan(kind=DATA, param=takes)


def _plan_image(model: Any, src: str, dst: str, stream: str,
                param: str) -> ConnectPlan:
    # **這一格上已經有線了嗎** —— 有就是累加（多連一），沒有就是設定它。
    #
    # 以前的判準是「這一對節點之間已經有線了嗎」，那在 F10 之前是對的：卡片的
    # 輸入帶著規格預設值（``streams="test"``），第一條線的意思是「改成這個」
    # 而不是「再加一個」。現在新卡的輸入本來就是空的，那個理由不成立了 ——
    # 而舊判準還會漏掉「兩條線來自**不同**上游卡」這種多連一，那正是量測卡
    # 最常見的接法（一條 diff、一條 test）。
    accumulate = any(e.dst == dst and e.dst_in == param for e in model.edges)
    if model.has_line(src, dst, stream, param):
        return ConnectPlan(kind=IMAGE, param=param,
                           already="%s → %s is already connected on %s."
                                   % (src, dst, stream or "that stream"))
    return ConnectPlan(
        kind=IMAGE, param=param, accumulate=accumulate,
        # ⚠ 先算 conflicts、後 `add_edge` 是**安全的**：上面那個篩子把「剛拉
        # 的這一條」明確排除掉了，所以新線在不在 `model.edges` 裡都算得出同一
        # 組答案。（順序反過來寫也對，但那樣就得先動 model 才問得出來 ——
        # 而這一份的整個重點是「問得出來而不必動任何東西」。）
        conflicts=conflicting_edges(model, src, dst, stream, param))


def _plan_region(model: Any, src: str, dst: str, name: str, param: str,
                 kind: str, region_param: bool) -> ConnectPlan:
    """區域線擋得住的三件事，而每一件都講得出可以照做的下一句話。

    ⚠ F12 還擋第四件：「來源排在下游」。**F42 B2 拿掉了** —— 區域線進了
    `recipe.edges` 之後那條線自己就是順序（`execution_order` 只看線），
    擋下來等於不讓使用者做那個唯一能修好順序的動作。真正會壞的那一種
    （成環）由 `add_edge` 擋，而且它擋的是事實不是排版。
    """
    if not param or not region_param:
        return ConnectPlan(
            kind=REJECT, param=param,
            reject="“%s” has no region input — that line carries a region, "
                   "and this card takes an image there." % dst)
    if kind != REGION:
        return ConnectPlan(
            kind=REJECT, param=param,
            reject="“%s” is an image stream, not a region. Drag from a "
                   "Region card's diamond port instead."
                   % (name or "that port"))
    node = model.nodes.get(dst)
    current = str(node.params.get(param, "") or "")
    keys = [k.strip() for k in current.split(",") if k.strip()]
    if name in keys:
        return ConnectPlan(kind=REGION, param=param,
                           already="“%s” already measures %s." % (dst, name))
    return ConnectPlan(kind=REGION, param=param,
                       conflicts=region_conflicts(model, src, dst, name, param))


# --------------------------------------------------------------------------- #
# 剪一條線
# --------------------------------------------------------------------------- #
def plan_unpoint(model: Any, node_id: str, stream: str,
                 param: str = "") -> UnpointPlan:
    """線剪掉了 → 那條流也要從下游卡的參數裡拿掉，而那一格會變成什麼。

    不拿掉的話畫布會**反過來說謊**：畫面上那條線沒了，卡片卻還在處理它
    （``streams=test,ref`` 一個字都沒變）。這是 F9-7「接線時參數跟著改」的
    另一半。

    F10 之前這裡有兩個保留條款，現在**兩個都拿掉了**：

    * 「單一角色的輸入（``image_key``）值就留著」—— 那時候那一格的值是唯一的
      紀錄。現在線才是唯一的來源，值留著等於畫布上沒有線、卡片卻還指著一條流。
    * 「最後一條不拿掉」—— 理由是 ``MultiStreamStep`` 對空字串會退回 ``test``；
      那個 ``or`` 在 F10 拿掉了，保留條款也就沒有存在的理由。
    """
    node = model.nodes.get(str(node_id))
    param = str(param or "")
    if node is None:
        return UnpointPlan()
    try:
        specs = {p.name: p for p in get_step(node.step).params}
    except KeyError:                       # pragma: no cover
        return UnpointPlan()
    spec = specs.get(param)
    if spec is None or not spec.is_input():
        return UnpointPlan()
    # **區域那一格不歸這裡管**（F42 B2）。它的值是從線水合出來的，所以在這裡
    # 動它 = 在線還在的時候讓參數跟線說不同的話。
    if spec.type in REGION_TYPES:
        return UnpointPlan()
    if spec.type == "image_keys":
        keys = [k.strip() for k
                in str(node.params.get(param, "") or "").split(",")
                if k.strip()]
        if stream and stream in keys:
            keys.remove(stream)
        elif len(keys) > 1:
            return UnpointPlan()   # 指不出剪的是哪一條，寧可不動
        else:
            keys = []
        value = ",".join(keys)
    else:
        value = ""                         # 角色埠：那條線就是它的全部來源
    if value == str(node.params.get(param, "") or ""):
        return UnpointPlan()
    return UnpointPlan(change=True, param=param, value=value,
                       label=str(spec.label or param))


# --------------------------------------------------------------------------- #
# 「這張卡還缺什麼」
# --------------------------------------------------------------------------- #
def producers_of(model: Any, stream: str) -> List[str]:
    """哪些卡片（用預設參數）會產出 ``stream``。"""
    out: List[str] = []
    for cls in visible_steps([s.describe() for s in list_steps()]) or []:
        key = str(cls.get("key", ""))
        try:
            step_cls = get_step(key)
            params = step_cls.validate_params({})
            writes = step_cls.resolve_writes_for_kind(params, model.kind)
        except Exception:  # 顯示用
            swallowed("edit_plan.producers_of")
            continue
        if stream in writes and step_cls.label:
            out.append(str(step_cls.label))
    return out


def unmet_needs(model: Any, node_id: str) -> str:
    """剛加的卡少了什麼上游 —— 講成一句可以照做的話（回傳含前導空白）。

    以前只有卡片庫上一個 ``needs diff`` 之類的灰字 badge。對不會寫 code 的人
    那句話沒有動作可做：他不知道那條流是誰產的，也不知道「不然還可以怎麼辦」。
    """
    node = model.nodes.get(str(node_id))
    if node is None:
        return ""
    try:
        step_cls = get_step(node.step)
        needs = list(step_cls.resolve_reads(node.params))
        # F10：剛加進來的卡**沒有來源**，所以 ``resolve_reads`` 是空的 ——
        # 照字面走的話這裡會說「什麼都不缺」，而它其實什麼都還沒接。
        #
        # 那一句話不能只講「這一格是空的」：對不寫 code 的使用者，「還缺 diff」
        # 跟「先加一張 Compare two streams」才是**做得下去**的話。卡片的
        # ``default`` 正好就是「這張卡本來預期吃哪一條流」—— 值被清掉了，
        # 但宣告還在。
        for name in step_cls.missing_inputs(node.params):
            spec = next((sp for sp in step_cls.params if sp.name == name), None)
            want = str(getattr(spec, "default", "") or "")
            if want and want not in needs:
                needs.append(want)
    except KeyError:
        return ""
    # 「上游有哪些流」有兩個來源，兩個都要算（F9-11）：
    #
    # 1. ``available_streams`` —— 照 route 的**線性順序**累加。這是沒有埠的線
    #    （既有 recipe）唯一的依據。
    # 2. **接進這張卡的線自己帶的流名。** F9 之後資料是照線走的，而線可以從執行
    #    順序上「後面」的節點接過來（分支的兩支各自往前接）。只看第 1 點的話，
    #    明明畫布上有線，這裡卻說「還缺 ref」—— 使用者照著那句話再加一張卡，
    #    就多了一張沒有用的卡。
    have = set(model.available_streams(before_node=str(node_id)))
    have |= {e.src_out for e in model.edges
             if e.dst == str(node_id) and e.src_out
             # 區域線帶的是**區域名**，不是影像流（F42 B2）。算進來的話一張
             # 接了 `epi` 的卡會被當成「它已經有一條叫 epi 的流」。資料線同理。
             and not is_region_edge(e, model.nodes)
             and not is_data_edge(e, model.nodes)}
    missing = [s for s in needs if s and s not in have]
    if not missing:
        return ""
    bits = []
    for s in missing:
        makers = producers_of(model, s)
        bits.append("“%s” (add %s first)" % (s, " or ".join(makers))
                    if makers else "“%s”" % s)
    return (" — but it still needs the image stream %s, or point it at one "
            "of: %s." % (", ".join(bits), ", ".join(sorted(have)) or "(none)"))


def copyable_params(step_key: str, params: Any) -> Dict[str, Any]:
    """複製一張卡時帶走哪些格（F99 P1-8）：**設定帶走，接線不帶**。

    吃影像流／區域的那幾格（``image_key(s)`` / ``region_key(s)``）的值是
    **線**水合出來的（鐵則 10）——貼上的那張卡還沒有線，帶著 ``source="single"``
    過去等於一張沒接線卻看起來接好了的卡，而那正是 F10 擋掉的東西。
    其他每一格照抄：滑桿、膠囊、門檻，那才是使用者按 Ctrl+C 想留住的。
    """
    from ..core.pipeline import get_step
    try:
        cls = get_step(str(step_key))
    except KeyError:
        return {}
    wired = {p.name for p in cls.params
             if p.type in ("image_key", "image_keys",
                           "region_key", "region_keys")}
    return {str(k): v for k, v in dict(params or {}).items()
            if str(k) not in wired}
