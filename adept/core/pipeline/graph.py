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
           "DEFAULT_IN", "DEFAULT_OUT"]

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
@dataclass(frozen=True)
class Wire:
    """一條線：``src`` 的 ``src_port`` → ``dst`` 的 ``dst_port``。"""
    src: str
    src_port: str
    dst: str
    dst_port: str


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

    def __post_init__(self) -> None:
        self.reindex()

    def reindex(self) -> None:
        inc: Dict[str, List[Wire]] = {}
        fan: Dict[Tuple[str, str], int] = {}
        for w in self.wires:
            inc.setdefault(w.dst, []).append(w)
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
    """把一份 ``Recipe`` 編成圖。

    **舊檔案不能改變行為**，所以線是這樣長出來的：

    * 先拿 ``execution_order()``（route 相鄰對 ∪ 顯式 edges 的拓撲排序）——
      跟以前完全一樣的順序；
    * 停用的節點拿掉，**前後接起來**（以前是跑到它就 ``continue``，效果一樣）；
    * 剩下的相鄰節點串成一條線；
    * 顯式 ``edges`` 也加進去。

    ⚠ 一個輸入埠被好幾條線餵到時，取**執行順序上最晚**的那一條。舊模型裡
    下游看到的是「累積到目前為止」的全域狀態，取最晚的那個來源才對得起來。
    """
    if registry is None:
        from .step import REGISTRY
        registry = REGISTRY

    order = [nid for nid in execution_order(recipe, kind)
             if recipe.nodes.get(nid) is not None and recipe.nodes[nid].enabled]
    pos = {nid: i for i, nid in enumerate(order)}

    # 每個節點的主要輸入埠 / 輸出埠（Phase 2 的卡片都是單進單出）
    def in_port(nid: str) -> str:
        node = recipe.nodes[nid]
        return _ports(registry.get(node.step), "inputs", DEFAULT_IN)[0]

    def out_port(nid: str) -> str:
        node = recipe.nodes[nid]
        return _ports(registry.get(node.step), "outputs", DEFAULT_OUT)[0]

    #: (dst, dst_port) -> src  —— 同一個埠留最晚的來源
    chosen: Dict[Tuple[str, str], Tuple[str, str]] = {}

    def offer(src: str, dst: str) -> None:
        if src not in pos or dst not in pos or pos[src] >= pos[dst]:
            return
        key = (dst, in_port(dst))
        prev = chosen.get(key)
        if prev is None or pos[prev[0]] < pos[src]:
            chosen[key] = (src, out_port(src))

    for a, b in zip(order, order[1:]):
        offer(a, b)

    #: 顯式的線。四段式 ``[src, src_port, dst, dst_port]`` **講明了埠**，
    #: 所以它不走 ``offer()`` 的「同一個埠取最晚來源」規則 —— 使用者指名要接
    #: 哪個埠，就是那個埠（條件分流的 match / else 靠這個才存得起來）。
    explicit: List[Wire] = []
    for e in recipe.edges:
        e = list(e)
        if len(e) == 4:
            src, sp, dst, dp = (str(x) for x in e)
            if src in pos and dst in pos and pos[src] < pos[dst]:
                explicit.append(Wire(src, sp, dst, dp))
                chosen.pop((dst, dp), None)     # 明講的贏過推出來的
        elif len(e) == 2:
            offer(str(e[0]), str(e[1]))

    wires = [Wire(src, src_port, dst, dst_port)
             for (dst, dst_port), (src, src_port) in chosen.items()]
    wires.extend(explicit)
    wires.sort(key=lambda w: (pos[w.dst], pos[w.src]))
    return Graph(order=order, nodes=dict(recipe.nodes), wires=wires)


# --------------------------------------------------------------------------- #
# 執行
# --------------------------------------------------------------------------- #
def _emit(ret: Any, fallback: Context, out_default: str) -> Dict[str, Context]:
    """卡片的回傳值正規化成 ``{輸出埠名: Context}``。

    既有卡片回一個 ``Context``（或什麼都不回，就地改 ctx）→ 全部當成主要
    輸出埠。新式卡片回 ``{埠名: Context}`` → 原樣用，**沒放進去的埠就是
    這次不吐**，那正是條件分流的表達方式。
    """
    if isinstance(ret, dict):
        return {str(k): v for k, v in ret.items() if isinstance(v, Context)}
    if isinstance(ret, Context):
        return {out_default: ret}
    return {out_default: fallback}


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
        in_ports = _ports(step_cls, "inputs", DEFAULT_IN)
        out_default = _ports(step_cls, "outputs", DEFAULT_OUT)[0]

        wires_in = graph.incoming(nid)
        ins: Dict[str, Packet] = {}
        starved = False
        for port in in_ports:
            feeding = [w for w in wires_in if w.dst_port == port
                       and (w.src, w.src_port) in outbox]
            if not feeding:
                # 沒接線 → 卡片自己會抱怨缺哪條流；
                # 接了線但上游沒吐 → 整段安靜跳過。兩者的差別在這裡分開。
                if any(w.dst_port == port for w in wires_in):
                    starved = True
                    break
                continue
            w = feeding[-1]                    # 同一個埠多個來源：取最晚的
            ins[port] = take(outbox, (w.src, w.src_port), graph, taken)

        if in_ports[0] not in ins and first_in_segment:
            ins[in_ports[0]] = seed            # 圖的頭 / 快取續跑的接點
            starved = False
        elif starved:
            continue
        first_in_segment = False

        primary = ins.get(in_ports[0])
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
            params = step_cls.validate_params(node.params)
            ret = step_cls().run(ctx, params)
        except Exception as e:                  # noqa: BLE001 — 收成結果，不外洩
            ms = (time.perf_counter() - t0) * 1000.0
            runs.append(NodeRun(nid, node.step, False, ms, str(e), {},
                                sorted(ctx.images)))
            return outbox, runs, "[%s] %s" % (nid, e), last
        ms = (time.perf_counter() - t0) * 1000.0

        produced = _emit(ret, ctx, out_default)
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
