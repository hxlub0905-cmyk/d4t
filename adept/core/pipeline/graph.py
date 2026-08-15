# ADEPT pipeline engine — authored 2026-08-15 (F9 Phase 2).
"""圖執行器：**線就是資料通道**。

在這個模組之前，資料走的是一個**全域** ``Context``：每張卡伸手進
``ctx.images`` 用名字（``"test"``、``"diff"``）拿東西，而畫布上的線只影響
執行順序。後果是那份範例 recipe 的 ``edges`` 是 ``[]`` —— 九張卡、零條線，
而它跑得完全正常。把線刪掉也什麼都不會發生。

現在改成：**一條線上流的是「一顆 defect 的整包狀態」**（:class:`Packet`）。
一張卡從進來的線上收，處理完往出去的線上送。沒接到線的卡就真的收不到東西。

設計與取捨見 ``docs/plans/F9-graph-as-program.md``。這裡只記實作上的三件事。

一、卡片不用改（Phase 2 的關鍵）
--------------------------------
``Packet`` 裝的東西跟 ``Context`` 一樣，所以執行器可以**幫每個節點把進來的
Packet 攤成一個 Context**、呼叫既有的 ``Step.run(ctx, params)``、再把回來的
Context 收成 Packet。既有 17 張卡一行都不用動，而執行模型已經是圖了。

卡片要用新能力時，``run()`` 可以改回傳 ``{輸出埠名: Context}``——
執行器兩種都收（見 :func:`_emit`）。條件分流就是這樣做的：回傳的 dict 裡
只放它這次要吐的那個埠。

二、分岔才複製（copy-on-fork）
------------------------------
線性的 pipeline（目前每一份 recipe 都是）每個輸出只有一個下游，那就**直接把
物件交出去**，不複製 —— 所以換成圖之後效能沒有變。只有一個輸出接到兩張以上
的卡時才複製，而那正是「兩條分支不該互相影響」開始有意義的時候。

複製要連 ``meta`` 裡的 list/dict 一起（``warnings`` 是 list，一邊 append
另一邊會看到）與 ``rois``（那是一個可變物件）。像素陣列**不複製** ——
卡片一律產生新陣列，不就地改寫，這是 F9 §4.1 對卡片作者的規矩。

三、沒收到就不跑，不是報錯
--------------------------
一個輸入埠**接了線但上游沒吐**（條件分流沒選到這一邊）→ 這個節點連同它的
下游整段安靜跳過。一個輸入埠**根本沒接線** → 節點照跑，然後卡片自己會說
「image stream 'test' does not exist」。兩件事不一樣，處理方式也不該一樣。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type

from .context import Context
from .recipe import Recipe, execution_order
from .step import Step

__all__ = ["Packet", "Wire", "Graph", "compile_recipe", "run_graph",
           "stream_ports", "optional_ports", "parse_stream_names",
           "KIND_PACKET", "KIND_STREAM", "DEFAULT_IN", "DEFAULT_OUT"]

#: 卡片沒有宣告埠時用的預設埠名。
DEFAULT_IN = "in"
DEFAULT_OUT = "out"


# --------------------------------------------------------------------------- #
# 線上流的東西
# --------------------------------------------------------------------------- #
@dataclass
class Packet:
    """一顆 defect 目前的全部狀態，沿著線流動。

    內部就是一個 :class:`Context` —— 這樣既有卡片不用改。``Packet`` 的價值
    在於**它有主人**：某一條線上的那一包，而不是所有人共用的那一包。
    """
    ctx: Context

    def fork(self) -> "Packet":
        """複製一份給另一條分支（像素陣列共用，其餘該複製的都複製）。"""
        src = self.ctx
        dup = Context(
            images=dict(src.images),          # 陣列共用：卡片不就地改寫
            rois=_copy_rois(src.rois),
            labels=src.labels,
            features=dict(src.features),
            meta=_copy_meta(src.meta),
        )
        dup.track_changes = src.track_changes
        return Packet(dup)


def _copy_rois(rois: Any) -> Any:
    """``MultiROISet`` 的淺複製 —— 清單要是新的，裡面的 ROI 可以共用。

    共用得起是因為卡片只會**加**或**刪**整個 ROI，不會就地改某一個的座標。
    """
    if rois is None:
        return None
    dup = copy.copy(rois)
    inner = getattr(dup, "_rois", None)
    if isinstance(inner, list):
        dup._rois = list(inner)
    return dup


def _copy_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """meta 的一層深複製：裡面的 list / dict 要各自一份。

    ``warnings`` 是 list、``stream_change`` 是 dict —— 只做 ``dict(meta)``
    的話，一條分支 append 一句警告，另一條分支也會看到。那種汙染不會報錯，
    只會讓兩邊的診斷訊息莫名其妙地混在一起。
    """
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, list):
            out[k] = list(v)
        elif isinstance(v, dict):
            out[k] = dict(v)
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------------- #
# 圖
# --------------------------------------------------------------------------- #
#: 線有兩種，因為「狀態往哪走」跟「這張卡動哪一條流」是兩件不同的事。
KIND_PACKET = "packet"
KIND_STREAM = "stream"


@dataclass(frozen=True)
class Wire:
    """一條線：``src`` 的 ``src_port`` → ``dst`` 的 ``dst_port``。

    ``kind`` 兩種（F9 Phase 3b）：

    * ``packet`` —— **狀態的去向**。這一顆 defect 目前的整包（影像們、區域們、
      特徵們）沿著它走。分岔時要複製；剪掉它，下游就真的收不到東西。
    * ``stream`` —— **「這張卡動哪一條流」**。它把來源埠的名字（``test`` /
      ``ref`` / ``diff``…）綁進下游卡的那個參數，**不搬狀態**。

    為什麼要分：``ref`` 這條流可能同時被 Normalize、一張 Region 卡、一張量測
    卡讀到。那是三條 ``stream`` 線（畫布上看得見「這三張都在動 ref」），
    但**不是三條分岔** —— 它們的特徵仍然要累積到同一包裡，最後才判定得出來。
    把它們當成分岔的話，每張卡各拿一份複本，量出來的數字散在三個地方，
    而分數式子只看得到其中一份。
    """
    src: str
    src_port: str
    dst: str
    dst_port: str
    kind: str = KIND_PACKET


@dataclass
class Graph:
    """要跑的圖：節點（照執行順序）+ 線。

    ``wires`` 改過之後要呼叫 :meth:`reindex`（測試會直接指派 ``wires``
    來模擬「把線剪掉」）。索引存在的理由只有一個：``incoming`` 與 ``fanout``
    在每個節點上各掃一次全部的線，是 O(節點 × 線)，而這段程式碼一顆 defect
    要跑一次、一個 lot 有一萬顆。
    """
    order: List[str]                                  # 執行順序（拓撲）
    nodes: Dict[str, Any]                             # id -> RecipeNode
    wires: List[Wire] = field(default_factory=list)
    #: ``節點 id -> (輸入埠, 輸出埠)``，**編譯時算一次**。
    #:
    #: 為什麼不讓執行期自己再算一次：``load_patch`` 的輸出流跟資料型別有關
    #: （``rsem`` 是 single+test、``ebi_patch`` 是 test+ref），而執行期看不到
    #: ``kind``。兩邊各算一次的下場是編譯期接的是 ``load.single``、執行期吐的
    #: 是 ``load.test`` —— 對不上，於是下游**整條鏈安靜地不執行**，跑得完、
    #: 沒有錯誤訊息、只有 load 一張卡跑過。踩過一次，別再讓它有機會不一致。
    ports: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = field(
        default_factory=dict)

    def __post_init__(self) -> None:
        self.reindex()

    def reindex(self) -> None:
        inc: Dict[str, List[Wire]] = {}
        fan: Dict[Tuple[str, str], int] = {}
        for w in self.wires:
            inc.setdefault(w.dst, []).append(w)
            if w.kind == KIND_PACKET:          # 只有搬狀態的線才算扇出
                key = (w.src, w.src_port)
                fan[key] = fan.get(key, 0) + 1
        self._incoming = inc
        self._fanout = fan

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if name == "wires" and hasattr(self, "_incoming"):
            self.reindex()                    # 直接改 wires 也不會拿到舊索引

    def incoming(self, node_id: str) -> List[Wire]:
        return self._incoming.get(node_id, [])

    def fanout(self, node_id: str, port: str) -> int:
        return self._fanout.get((node_id, port), 0)


def _ports(step_cls: Optional[Type[Step]], attr: str, default: str) -> Tuple[str, ...]:
    got = getattr(step_cls, attr, None) if step_cls is not None else None
    return tuple(got) if got else (default,)


# --------------------------------------------------------------------------- #
# 埠名就是影像流名（F9 Phase 3b）
# --------------------------------------------------------------------------- #
#: 「輸出流叫什麼」的參數名。有這個參數的卡片，它的輸出埠就叫那個名字。
OUT_PARAM = "out"


def stream_ports(step_cls: Optional[Type[Step]], params: Dict[str, Any],
                 kind: str = "", first: bool = False
                 ) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """一張卡的（輸入埠, 輸出埠）—— **從卡片自己的宣告推出來，不用逐張改**。

    規則兩條：

    * **輸入埠 = 每一個「選影像流」的參數**（型別 ``image_key`` /
      ``image_keys``，``out`` 除外）。所以埠名就是那個參數的角色名：
      ``source`` / ``a`` / ``b`` / ``moving`` / ``fixed`` / ``reference`` /
      ``range_from`` / ``use_within`` / ``streams``。使用者看到的是
      「這張卡要接兩條線：a 和 b」，而不是「這張卡有兩個下拉選單」。
    * **輸出埠 = 這張卡寫出來的影像流名**（``out`` 參數指定，或
      ``resolve_writes()``）。所以 Load 的輸出埠就是 ``test`` 與 ``ref``，
      從 ``ref`` 那顆埠拉出去的每一條線都代表「這條線帶的是 ref」。

    為什麼這件事重要（使用者 2026-08-15 的兩條原則）
    ------------------------------------------------
    1. 「卡片內可以選 image source」要拿掉 —— **改成只能從節點拉**，免得
       畫布上接的是一條線、卡片裡選的是另一條流，兩者不一致而且沒人看得出來。
    2. 同一顆輸出埠要**拉得出好幾條線**：Load 的 ``ref`` 可以同時餵
       Normalize 與一張 Region 卡。埠名帶著流名，這件事才說得清楚。

    沒有宣告任何流參數的卡（例如判定卡）就退回 ``Step.inputs`` /
    ``Step.outputs`` 的預設。
    """
    if step_cls is None:
        return (DEFAULT_IN,), (DEFAULT_OUT,)

    specs = list(getattr(step_cls, "params", ()) or ())
    # **用不到的參數不該有埠。**（2026-08-15 修）
    #
    # ``show_when`` 已經在參數表上把「這個方法用不到」的那幾列藏起來了，但埠的
    # 推導一開始沒看它 —— 於是 Normalize 選 percentile 的時候，畫布上還是長出
    # 一顆 ``reference`` 埠，而且真的接了一條線。那條線**完全不影響結果**。
    # 那是 §7「help 裡寫『這個方法用不到』是一句道歉不是設計」的同一個病，
    # 只是搬到了畫布上。
    ins = tuple(p.name for p in specs
                if p.type in ("image_key", "image_keys")
                and p.name != OUT_PARAM
                and p.visible_for(params))
    if not ins:
        ins = _ports(step_cls, "inputs", DEFAULT_IN)

    outs: Tuple[str, ...] = ()
    if any(p.name == OUT_PARAM for p in specs):
        name = str(params.get(OUT_PARAM, "") or "").strip()
        if name:
            outs = (name,)
    if not outs:
        try:
            written = (step_cls.resolve_writes_for_kind(params, kind) if first
                       else step_cls.resolve_writes(params))
        except Exception:                      # noqa: BLE001 — 壞參數不該擋住編譯
            written = list(getattr(step_cls, "writes", ()) or ())
        outs = tuple(dict.fromkeys(str(w) for w in written if str(w).strip()))
    if not outs:
        outs = _ports(step_cls, "outputs", DEFAULT_OUT)
    return ins, outs



def optional_ports(step_cls: Optional[Type[Step]],
                   params: Dict[str, Any]) -> Tuple[str, ...]:
    """哪幾個輸入埠是**選用**的（畫布可以在沒接線時收起來）。

    判準沿用卡片自己已經有的兩個旗標，不發明新的：``advanced``（「這一格填
    預設值就跑得出正確答案」），或者預設值是空字串（``range_from`` /
    ``use_within`` 那種「不填就是不做」的）。

    為什麼要分級：``normalize`` 有 4 個輸入埠、``subtract`` 2 個、``align``
    2 個 —— 全部常駐在節點旁邊的話，會跟資料流搶畫面（F7-8 那條「常駐在節點
    旁邊的裝飾」的教訓）。非接不可的永遠顯示，其餘接了才長出來。
    """
    out = []
    for spec in (getattr(step_cls, "params", ()) or ()):
        if spec.type not in ("image_key", "image_keys") or spec.name == OUT_PARAM:
            continue
        if not spec.visible_for(params):
            continue
        if spec.advanced or not str(spec.default or "").strip():
            out.append(spec.name)
    return tuple(out)


def _has_stream_inputs(step_cls: Optional[Type[Step]]) -> bool:
    """這張卡有沒有「選影像流」的參數（= 它的輸入埠是不是流）。"""
    return any(p.type in ("image_key", "image_keys") and p.name != OUT_PARAM
               for p in (getattr(step_cls, "params", ()) or ()))



def _fingerprint(recipe: Recipe, kind: str) -> tuple:
    """「這份 recipe 編出來的圖會不會不一樣」的便宜判準。

    只看**結構**（有哪些節點、是哪張卡、開著沒、有哪些顯式邊），不看參數 ——
    參數改變不會改變接線。比重新拓撲排序 + 造一堆 Wire 物件便宜得多，而這件事
    一顆 defect 要做一次。
    """
    return (kind,
            tuple(sorted((nid, n.step, bool(n.enabled))
                         for nid, n in recipe.nodes.items())),
            tuple(tuple(e) for e in recipe.edges),
            tuple(recipe.routes.get(kind, ())))


def compile_recipe(recipe: Recipe, kind: str,
                   registry: Optional[Dict[str, Type[Step]]] = None) -> Graph:
    """編譯（帶快取）。快取掛在 ``recipe`` 物件上，用結構指紋驗證。

    為什麼要快取：批次是「同一份 recipe 跑一萬顆」，而編譯的結果每一顆都一樣。
    為什麼還要驗指紋：``Recipe`` 是可變的（Studio 會改），只認物件不認內容的
    快取會在改完 recipe 之後**安靜地跑舊的圖** —— 跑得完、有數字、而且是錯的。
    """
    fp = _fingerprint(recipe, kind)
    hit = getattr(recipe, "_graph_cache", None)
    if hit is not None and hit[0] == fp:
        return hit[1]
    graph = _compile_recipe(recipe, kind, registry=registry)
    try:
        recipe._graph_cache = (fp, graph)
    except Exception:                          # noqa: BLE001 — 快取不了就算了
        pass
    return graph


def _compile_recipe(recipe: Recipe, kind: str,
                    registry: Optional[Dict[str, Type[Step]]] = None) -> Graph:
    """把一份 ``Recipe`` 編成圖 —— **線由影像流的名字解析出來**。

    每個節點的每一個輸入埠（= 一個「選影像流」的參數）都問同一個問題：
    **這條流是上游哪一張卡吐的？** 往回找最後一個輸出埠叫這個名字的節點，
    接一條線過去。

    這同時是**遷移**與**新語意**，而且兩者剛好一致：舊模型的執行方式就是
    「拿名字去全域字典撈」，所以「照名字接線」產生的圖跟以前的行為逐位元組
    相同 —— 差別只在於那個查找現在**看得見**（是畫布上一條線），而且之後
    使用者改的是線，不是下拉選單。

    顯式的四段式 ``edges``（``[src, src_port, dst, dst_port]``）**贏過**推導 ——
    使用者在畫布上拉的線就是他說了算，條件分流的 match / else 靠它。
    """
    if registry is None:
        from .step import REGISTRY
        registry = REGISTRY

    order = [nid for nid in execution_order(recipe, kind)
             if recipe.nodes.get(nid) is not None and recipe.nodes[nid].enabled]
    pos = {nid: i for i, nid in enumerate(order)}

    # ---- 每個節點的埠與乾淨參數 ----
    ports: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {}
    clean: Dict[str, Dict[str, Any]] = {}
    for i, nid in enumerate(order):
        node = recipe.nodes[nid]
        step_cls = registry.get(node.step)
        try:
            p = step_cls.validate_params(node.params) if step_cls else dict(node.params)
        except Exception:                      # noqa: BLE001 — 壞參數不擋編譯
            p = dict(node.params)
        clean[nid] = p
        ports[nid] = stream_ports(step_cls, p, kind=kind, first=(i == 0))

    #: 影像流名 -> 最後吐出它的節點（邊走邊更新 = 自然的「往回找最近的」）
    producer: Dict[str, str] = {}
    #: (dst, dst_port) -> (src, src_port)
    packet_in: Dict[Tuple[str, str], Tuple[str, str]] = {}
    stream_in: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}

    for i, nid in enumerate(order):
        ins, outs = ports[nid]
        p = clean[nid]

        # ---- stream 線：這張卡動哪一條流（不搬狀態）----
        for port in ins:
            if port == DEFAULT_IN:
                continue                       # 那是 packet 埠，不是流參數
            for stream in parse_stream_names(p.get(port)):
                src = producer.get(stream)
                if src is not None and pos[src] < pos[nid]:
                    stream_in.setdefault((nid, port), []).append((src, stream))

        # ---- packet 線：狀態沿著執行順序走（就是舊模型的那條鏈）----
        if i > 0:
            prev = order[i - 1]
            prev_outs = ports[prev][1]
            if prev_outs:
                packet_in[(nid, DEFAULT_IN)] = (prev, prev_outs[0])

        for out in outs:
            producer[out] = nid

    # 顯式的線贏過推導出來的 —— **使用者在畫布上拉的就是他說了算**。
    #
    # 兩段式 ``[src, dst]``（畫布上拉一條線存出來的那種）也要算數。漏掉它的
    # 話，使用者拉的線會被推導出來的主幹蓋掉：畫面上他接了 load → norm，
    # 實際跑的卻是 load → norm_ref → norm，而且看不出來 —— 正好是 F9 要修的
    # 那件事，而不是可以順手忽略的細節。
    explicit: List[Wire] = []
    for e in recipe.edges:
        e = list(e)
        if len(e) == 4:
            src, sp, dst, dp = (str(x) for x in e)
        elif len(e) == 2:
            src, dst = str(e[0]), str(e[1])
            if src not in pos or dst not in pos:
                continue
            sp = (ports[src][1] or (DEFAULT_OUT,))[0]
            dp = (DEFAULT_IN if _has_stream_inputs(registry.get(
                recipe.nodes[dst].step)) else (ports[dst][0] or (DEFAULT_IN,))[0])
        else:
            continue
        if src in pos and dst in pos and pos[src] < pos[dst]:
            explicit.append(Wire(src, sp, dst, dp, KIND_PACKET))
            packet_in.pop((dst, dp), None)
            stream_in.pop((dst, dp), None)

    wires = [Wire(src, sp, dst, dp, KIND_PACKET)
             for (dst, dp), (src, sp) in packet_in.items()]
    wires += [Wire(src, sp, dst, dp, KIND_STREAM)
              for (dst, dp), srcs in stream_in.items() for src, sp in srcs]
    wires.extend(explicit)
    wires.sort(key=lambda w: (pos[w.dst], w.kind, pos[w.src], w.dst_port))
    return Graph(order=order, nodes=dict(recipe.nodes), wires=wires,
                 ports=ports)


def parse_stream_names(value: Any) -> List[str]:
    """一個流參數的值 → 流名清單（``image_keys`` 是逗號分隔的一串）。"""
    out: List[str] = []
    for tok in str(value or "").split(","):
        tok = tok.strip()
        if tok and tok not in out:
            out.append(tok)
    return out


# --------------------------------------------------------------------------- #
# 執行
# --------------------------------------------------------------------------- #
def _emit(ret: Any, fallback: Context,
          out_ports: Sequence[str]) -> Dict[str, Context]:
    """卡片的回傳值正規化成 ``{輸出埠名: Context}``。

    既有卡片回一個 ``Context``（或什麼都不回，就地改 ctx）→ **每一個輸出埠
    都吐同一包**。這不是浪費：一張卡可能吐好幾條影像流（Load 吐 test 與
    ref），而埠只是**標籤** —— 下游從 ``ref`` 那顆埠拉線，拿到的是同一包，
    埠名告訴它「你要動的是 ref」。

    新式卡片回 ``{埠名: Context}`` → 原樣用，**沒放進去的埠就是這次不吐**，
    那正是條件分流的表達方式。
    """
    if isinstance(ret, dict):
        return {str(k): v for k, v in ret.items() if isinstance(v, Context)}
    ctx = ret if isinstance(ret, Context) else fallback
    ports = tuple(out_ports) or (DEFAULT_OUT,)
    return {port: ctx for port in ports}


@dataclass
class NodeRun:
    """一個節點跑完的紀錄（engine 用它組 StepTrace）。"""
    node_id: str
    step_key: str
    ok: bool
    ms: float
    error: Optional[str]
    features_added: Dict[str, float]
    images_after: List[str]


def run_graph(graph: Graph, seed: Packet, *,
              registry: Optional[Dict[str, Type[Step]]] = None,
              start: int = 0,
              stop: Optional[int] = None,
              upto_node: Optional[str] = None,
              inbox: Optional[Dict[Tuple[str, str], Packet]] = None,
              track_changes: bool = False,
              ) -> Tuple[Dict[Tuple[str, str], Packet], List[NodeRun], Optional[str],
                         Optional[Packet]]:
    """跑 ``graph.order[start:stop]``。

    回傳 ``(outbox, runs, error, last_packet)``：

    * ``outbox``   —— ``(節點, 輸出埠) -> Packet``（給續跑／快取用）
    * ``runs``     —— 每個真的跑過的節點一筆
    * ``error``    —— 出錯的話是 ``"[node] 訊息"``，否則 None
    * ``last_packet`` —— 最後一個吐出東西的節點吐的那一包（沒有就是 seed）

    **永不 raise** 由呼叫端（engine）保證；這裡遇到卡片丟例外會收成 error 回傳。
    """
    import time

    if registry is None:
        from .step import REGISTRY
        registry = REGISTRY

    outbox: Dict[Tuple[str, str], Packet] = dict(inbox or {})
    taken: Dict[Tuple[str, str], int] = {}
    runs: List[NodeRun] = []
    last: Optional[Packet] = None
    order = graph.order[start:len(graph.order) if stop is None else stop]

    #: 這一段的第一個節點沒東西可收時，用 ``seed``。兩種情況都靠它：
    #: 圖的頭（load 卡，本來就沒有上游），以及快取命中之後從中間續跑。
    first_in_segment = True

    for nid in order:
        node = graph.nodes.get(nid)
        if node is None:                       # 理論上編譯期就濾掉了
            continue
        step_cls = registry.get(node.step)
        in_ports, out_ports = graph.ports.get(
            nid, ((DEFAULT_IN,), (DEFAULT_OUT,)))

        wires_in = graph.incoming(nid)

        # ---- stream 線：把「這張卡動哪一條流」綁進參數 ----
        #
        # **參數不再是使用者選的，是線決定的**（使用者 2026-08-15 的原則 1）。
        # 同一個埠接了好幾條線 = 這張卡同時做那幾條流（``image_keys``）。
        bound: Dict[str, str] = {}
        for w in wires_in:
            if w.kind != KIND_STREAM:
                continue
            prev = bound.get(w.dst_port)
            bound[w.dst_port] = (prev + "," + w.src_port) if prev else w.src_port

        # ---- packet 線：狀態從哪裡來 ----
        ins: Dict[str, Packet] = {}
        starved = False
        # **狀態一律從 ``in`` 埠進來。** 卡片宣告的那些流參數（source / a / b …）
        # 是「動哪一條流」的埠，不搬狀態。只有完全不吃影像流的卡（判定卡、
        # 之後的合流卡）才用它自己宣告的輸入埠當狀態入口。
        packet_ports = ([DEFAULT_IN] if _has_stream_inputs(step_cls)
                        else list(in_ports))
        for port in packet_ports:
            feeding = [w for w in wires_in
                       if w.kind == KIND_PACKET and w.dst_port == port
                       and (w.src, w.src_port) in outbox]
            if not feeding:
                if any(w.kind == KIND_PACKET and w.dst_port == port
                       for w in wires_in):
                    starved = True             # 接了線但上游沒吐 -> 整段跳過
                    break
                continue
            w = feeding[-1]
            ins[port] = take(outbox, (w.src, w.src_port), graph, taken)

        head = packet_ports[0]
        if head not in ins and first_in_segment:
            ins[head] = seed                   # 圖的頭 / 快取續跑的接點
            starved = False
        elif starved:
            continue
        first_in_segment = False

        primary = ins.get(head)
        if primary is None:                    # 沒接線又不是頭 —— 讓卡片說話
            primary = Packet(Context())

        ctx = primary.ctx
        ctx.track_changes = bool(track_changes)
        feats_before = dict(ctx.features)

        t0 = time.perf_counter()
        try:
            if step_cls is None:
                from .step import StepError
                raise StepError(
                    node.step,
                    "unknown step '%s'; registered: %s"
                    % (node.step, sorted(registry)))
            raw = dict(node.params)
            raw.update(bound)                  # 線說了算，參數只是它的落腳處
            params = step_cls.validate_params(raw)
            ret = step_cls().run(ctx, params)
        except Exception as e:                  # noqa: BLE001 — 收成結果，不外洩
            ms = (time.perf_counter() - t0) * 1000.0
            runs.append(NodeRun(nid, node.step, False, ms, str(e), {},
                                sorted(ctx.images)))
            return outbox, runs, "[%s] %s" % (nid, e), last
        ms = (time.perf_counter() - t0) * 1000.0

        produced = _emit(ret, ctx, out_ports)
        added = {k: v for k, v in ctx.features.items()
                 if k not in feats_before or feats_before[k] != v}
        runs.append(NodeRun(nid, node.step, True, ms, None, added,
                            sorted(ctx.images)))

        for port, out_ctx in produced.items():
            pk = Packet(out_ctx)
            outbox[(nid, port)] = pk           # 分岔的複製在 take() 那一刻做
            last = pk
        if nid == upto_node:
            break

    return outbox, runs, None, last


def take(outbox: Dict[Tuple[str, str], Packet], key: Tuple[str, str],
         graph: Graph, taken: Dict[Tuple[str, str], int]) -> Packet:
    """從 outbox 取一包給下游用。

    * 只有一個下游（線性 pipeline，目前每一份 recipe 都是）→ **直接交出原件**，
      不複製，所以換成圖之後效能沒有變。
    * 兩個以上 → **每一個都拿複本**，outbox 裡那份保持原樣。

    第一個取用者不能拿原件：既有卡片是就地改 ``ctx`` 的，它一改，
    留在 outbox 裡的那份就髒了，第二個分支複製到的會是**已經被上一條分支
    改過**的狀態 —— 而那正是分岔要防的那件事。
    """
    taken[key] = taken.get(key, 0) + 1
    pk = outbox[key]
    return pk if graph.fanout(key[0], key[1]) <= 1 else pk.fork()
