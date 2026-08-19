# ADEPT pipeline engine — authored 2026-07-28 (M1; M2 加入 checkpoint 快取).
"""單顆執行引擎：對一顆 defect 依 recipe 跑完整 pipeline。

M1：單進程、循序。M2：內部重構成可重用片段（種 Context → 跑節點區間 →
算分），讓 :func:`run_defect_cached` 能從「影像段結束」的 checkpoint 續跑
（影像段快取見 :mod:`.cache`，平行批次見 :mod:`.batch`）。

鐵則：**單顆爆 = 該顆 FAIL，不殺整批** —— :func:`run_defect` 與
:func:`run_defect_cached` 永不 raise，所有錯誤（StepError / ContextError /
RecipeError / 快取讀寫失敗 / 其他）都收進 :class:`DefectResult` 或
自動退回全程重算。
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from .context import Context
from .expression import parse_expression
from .recipe import Recipe, RecipeError, execution_order
from .step import CATEGORY_IMAGE, REGISTRY, Step, StepError

__all__ = ["StepTrace", "DefectResult", "run_defect", "run_defect_cached",
           "run_dataset", "image_segment_signature", "result_to_json_dict"]


@dataclass
class StepTrace:
    """一個節點的執行紀錄（供 Studio 單顆預覽與 debug）。"""
    node_id: str
    step_key: str
    ok: bool
    ms: float
    error: Optional[str]
    features_added: Dict[str, float]   # 該步驟新增或改值的特徵
    images_after: List[str]            # 該步驟結束後的影像流 key（排序）


@dataclass
class DefectResult:
    """一顆 defect 的完整執行結果。"""
    defect_id: str
    ok: bool
    error: Optional[str]
    features: Dict[str, float]
    score: Optional[float]
    bin: Optional[int]
    traces: List[StepTrace]
    context: Optional[Context]         # keep_context=True 才附上（不進 JSON）


# ---------------------------------------------------------------------------
# 可重用片段（M2 重構；run_defect 的行為與 M1 完全相同）
# ---------------------------------------------------------------------------
def _seed_context(item: Any, kind: str, defect_id: str) -> Context:
    """建立新 Context 並種入引擎慣例的 meta key（Load 卡讀這些）。"""
    ctx = Context()
    ctx.meta["_defect_item"] = item
    ctx.meta["_dataset_kind"] = kind
    ctx.meta["_defect_id"] = defect_id
    ctx.meta["nm_per_px"] = getattr(item, "nm_per_px", None)
    return ctx


def _finish(defect_id: str, ctx: Context, traces: List[StepTrace],
            keep_context: bool, ok: bool, error: Optional[str],
            score: Optional[float] = None,
            bin_: Optional[int] = None) -> DefectResult:
    return DefectResult(
        defect_id=defect_id, ok=ok, error=error,
        features=dict(ctx.features), score=score, bin=bin_,
        traces=traces, context=(ctx if keep_context else None))


#: ``ctx.meta`` 裡放「每個特徵是哪張卡產出的」的鍵。
#:
#: 放在 meta 而不是 :class:`DefectResult` 的新欄位，是為了**不動序列化** ——
#: `store/results.py` 的資料表、CSV 的欄位、KLARF 寫回全部吃的是扁平的
#: ``features`` dict，加一個欄位就得動 schema，而 F9-3 的驗收條件是
#: 「沒有撞名時輸出逐位元組相同」。
FEATURE_OWNER_KEY = "feature_owner"


def qualified_feature_name(node_id: str, name: str) -> str:
    """被蓋掉的特徵改用這個名字保存：``<產出它的節點>_<原名>``。

    D1（使用者 2026-08-16 同意）：**特徵掛在產出它的節點上**。節點只有一個，
    所以「這個數字從哪來」永遠答得出來 —— 包括那些不屬於任何一條影像流的
    （``n_channels`` 是這顆 defect 的、``align_dx`` 是兩條流之間的關係、
    ``cross_*`` 是具名區域的）。

    D2：**沒撞名就用原名**，撞名才加前綴。所以使用者平常看到的名字跟以前
    一模一樣，不必學新語法（寫 score 的是不會寫 code 的工程師）。

    F9-5 之後線會有自己的身分，那時前綴可以換成線名（``ref_soft_glv_max``
    比 ``glv_stats2_glv_max`` 好讀）。現在線還沒有身分，節點有。
    """
    return "%s_%s" % (node_id, name)


def _produced_feature_names(step_cls: Type[Step], params: Dict[str, Any],
                            ctx: Context, added: Dict[str, Any]) -> List[str]:
    """這張卡這一輪「產出了哪些特徵」——**看宣告，不看值有沒有變**。

    用 ``added``（值的差異）判斷是不夠的：後面那張卡如果剛好算出**一樣的值**，
    差異是空的，於是「誰擁有這個特徵」不會更新、被蓋掉的也不會被救。那會讓
    行為**跟數值巧合有關** —— 同一份 recipe 在某些 defect 上多一個特徵欄位、
    某些上沒有，而那是最難解釋的一種不一致。
    """
    names = [f for f in step_cls.resolve_features(params) if f in ctx.features]
    for k in added:                      # 沒宣告卻寫了的（防禦性；I3 擋著）
        if k not in names:
            names.append(k)
    return names


def _rescue_overwritten_features(ctx: Context, nid: str,
                                 before: Dict[str, Any],
                                 added: Dict[str, Any],
                                 owner: Dict[str, str]) -> None:
    """這張卡蓋掉了誰的特徵，就把被蓋掉的那份用**帶節點名的名字**留下來。

    **既有語意一個字都沒改**：``glv_max`` 仍然是「最後一張卡寫的那個值」，
    score 表達式、CSV、KLARF 寫回全部照舊。改的只有一件事 —— 以前被蓋掉的
    那個值**完全消失、指都指不到**（`validate` 的 feature-collision 警告就是
    在講這件事），現在它還在，叫 ``<前一張卡的節點名>_<原名>``。

    為什麼是「救回舊的」而不是「把新的改名」：後者會讓 ``glv_max`` 突然不存在，
    一份跑得好好的 recipe 的 score 表達式當場失效。救回舊的是**純粹加東西**，
    沒有任何既有的東西被拿走。
    """
    for name in added:
        prev_owner = owner.get(name)
        if name in before and prev_owner is not None and prev_owner != nid:
            rescued = qualified_feature_name(prev_owner, name)
            if rescued not in ctx.features:
                ctx.features[rescued] = before[name]
            ctx.meta.setdefault(FEATURE_OWNER_KEY, {})[rescued] = prev_owner
        owner[name] = nid
        ctx.meta.setdefault(FEATURE_OWNER_KEY, {})[name] = nid


def _local_view(master: Context, visible: Dict[str, Any]) -> Context:
    """給一張卡看的 ``Context``：**只有它宣告要讀的那幾條影像流**。

    F9-2（2026-08-16）。以前是一個 ``ctx`` 從頭傳到尾，所以每張卡都看得到
    「到目前為止的所有流」—— 那正是分支做不到的原因，也是「卡片偷讀一條沒宣告
    的流」不會被發現的原因（畫布上不會有那條線，使用者於是看不出兩張卡有關係）。

    **只有 ``images`` 是這張卡自己的**；``rois`` / ``labels`` / ``features`` /
    ``meta`` 仍然共用同一份（F9-3 才處理 feature 的歸屬）。dict 是直接共用參考，
    所以卡片往 features/meta 寫的東西會直接落到 master 上；``rois`` / ``labels``
    是**可能被整個換掉**的欄位（``set_roi`` 會 rebind），所以跑完要抄回去。
    """
    return Context(images=dict(visible), rois=master.rois, labels=master.labels,
                   features=master.features, meta=master.meta,
                   track_changes=master.track_changes)


def _visible_streams(master: Context, step_cls: Type[Step],
                     params: Dict[str, Any]) -> Dict[str, Any]:
    """這張卡宣告要讀的流裡，**目前真的存在**的那些。

    宣告了但不存在的不補 —— 卡片自己去 ``require_image`` 會拿到帶說明的
    ``ContextError``，而那句話正好是使用者需要的（「這條流不存在，現有的是…」）。
    """
    out: Dict[str, Any] = {}
    for name in step_cls.resolve_reads(params):
        if name in master.images:
            out[name] = master.images[name]
    return out


# ---------------------------------------------------------------------------
# F9-5a：影像流的身分 = (哪個節點, 哪個輸出埠)
# ---------------------------------------------------------------------------
def _param_types(step_cls: Type[Step]) -> Dict[str, str]:
    return {str(p["name"]): str(p["type"]) for p in step_cls.describe()["params"]}


def _explicit_bindings(recipe: Recipe, registry: Dict[str, Type[Step]]
                       ) -> Dict[Tuple[str, str], Tuple[str, str]]:
    """``recipe.edges`` 裡**兩個埠都填了**的那些線 → ``(節點, 流名) → (來源節點, 來源埠)``。

    邊記的是「落在下游的哪個**參數**」（``dst_in``），但卡片是用**流名**去
    ``require_image`` 的，所以要把參數換算成流名：

    * ``image_key``（``subtract`` 的 ``b``）→ 流名就是 ``params["b"]`` 的值；
    * ``image_keys``（Enhance 卡的 ``streams``，一串）→ 一個參數會有好幾條線，
      每條線自己帶著它給的是哪一條（``src_out``）。

    埠沒填的線不進來（目前 UI 拉出來的線就是這種）—— 它們仍然只表達先後順序，
    資料從哪來由 :func:`_implicit_bindings` 照「最後一個寫它的人」推。
    """
    out: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for e in recipe.edges:
        if not (e.src_out and e.dst_in):
            continue
        node = recipe.nodes.get(e.dst)
        step_cls = registry.get(node.step) if node is not None else None
        if step_cls is None:
            continue
        try:
            params = step_cls.validate_params(node.params)
        except Exception:              # noqa: BLE001 — 壞參數交給 validate 報
            continue
        ptype = _param_types(step_cls).get(e.dst_in, "")
        if ptype == "image_keys":
            local_name = e.src_out
        elif ptype == "image_key":
            local_name = str(params.get(e.dst_in, "") or "")
        else:
            continue                   # 那個參數不是影像流，這條線不是資料流
        if local_name:
            out[(e.dst, local_name)] = (e.src, e.src_out)
    return out


def _implicit_bindings(recipe: Recipe, order: List[str],
                       registry: Dict[str, Type[Step]], kind: str
                       ) -> Dict[Tuple[str, str], Tuple[str, str]]:
    """沒有明講的線 → 照「**執行順序上最後一個寫這條流的人**」推。

    那正是 F9 之前的語意（一個全域名字表，後寫的蓋掉先寫的），所以**推出來的
    結果跟舊行為逐位元組相同** —— 這是 F9-5a 敢動資料流的唯一理由。

    UI 還沒開始產帶埠的線（F9-5b），所以現在每一條資料流都走這裡。
    """
    out: Dict[Tuple[str, str], Tuple[str, str]] = {}
    last_writer: Dict[str, str] = {}
    for nid in order:
        node = recipe.nodes.get(nid)
        if node is None or not node.enabled:
            continue
        step_cls = registry.get(node.step)
        if step_cls is None:
            continue
        try:
            params = step_cls.validate_params(node.params)
        except Exception:              # noqa: BLE001
            continue
        for name in step_cls.resolve_reads(params):
            if name in last_writer:
                out[(nid, name)] = (last_writer[name], name)
        # kind-aware 的 writes 宣告是**卡片自己的事**，不是「排第幾個」的事
        # （F11 Input-0）。預設實作就是 ``resolve_writes``，只有 load 卡覆寫
        # 它 —— 所以無條件呼叫，一張卡的宣告不會因為它前面多一張卡而改變。
        writes = step_cls.resolve_writes_for_kind(params, kind)
        for w in writes:
            last_writer[w] = nid
    return out


def _follow_disabled(recipe: Recipe,
                     bind: Dict[Tuple[str, str], Optional[Tuple[str, str]]],
                     src: Tuple[str, str]) -> Optional[Tuple[str, str]]:
    """線指到一張**被停用**的卡時，沿著它自己的入線再往上找（F9-8）。

    為什麼要走這一段
    ----------------
    停用只是「這次不跑」，不是「這條線不存在」。但被停用的節點沒有產出，
    於是 ``produced[(它, 埠)]`` 是空的 —— 而以前空的就退回 ``ctx.images``
    ＝「最後一個寫這個名字的人」，在分支上那是**隔壁那一支**。
    實測：停用 ×3 那一支的卡，它下游的量測卡量到的是 ×5 那一支的值。

    往上找到的是「這條線上第一個還開著的產出者」，那正是使用者的意思：
    把中間一張卡關掉 = 資料直接從它的上游流過來。

    找不到（整條線的上游都關著，或那個名字本來就不是傳遞下去的）→ 回 ``None``
    ＝ **這條流在這條線上沒有東西**。呼叫端據此讓卡片看不到它，於是它會拿到
    一句「缺這條影像流」的錯誤 —— 而不是安靜地吃到別支的圖。
    """
    seen = set()
    cur: Optional[Tuple[str, str]] = src
    while cur is not None:
        node = recipe.nodes.get(cur[0])
        if node is None:
            return None
        if node.enabled:
            return cur
        if cur in seen:                       # 理論上不會（DAG），但別無限迴圈
            return None
        seen.add(cur)
        cur = bind.get(cur)
    return None


def _bindings(recipe: Recipe, order: List[str],
              registry: Dict[str, Type[Step]], kind: str
              ) -> Dict[Tuple[str, str], Optional[Tuple[str, str]]]:
    """這條 route 上每個「節點要的流」各自從哪個 ``(節點, 埠)`` 來。

    明講的線**蓋過**推出來的 —— 使用者在畫布上拉的那條，永遠贏過「剛好排在
    前面的那張卡」。

    值可能是 ``None``：線指到的那張卡被停用了，而沿著它往上也找不到還開著的
    產出者（見 :func:`_follow_disabled`）。那代表**這條線上沒有這條流**。
    """
    merged: Dict[Tuple[str, str], Optional[Tuple[str, str]]] = dict(
        _implicit_bindings(recipe, order, registry, kind))
    explicit = _explicit_bindings(recipe, registry)
    merged.update(explicit)
    # 停用的節點只在**明講的線**上要處理：``_implicit_bindings`` 本來就跳過
    # 停用節點（它算的是「最後一個**跑過**的寫者」），推出來的結果不會指到
    # 關著的卡。
    for key in explicit:
        merged[key] = _follow_disabled(recipe, merged, merged[key])
    return merged


def _run_nodes(recipe: Recipe, order: List[str], start: int, stop: int,
               ctx: Context, traces: List[StepTrace],
               registry: Dict[str, Type[Step]],
               upto_node: Optional[str],
               kind: str = "") -> Tuple[Context, Optional[str]]:
    """執行 ``order[start:stop]`` 的節點；trace 逐一 append。

    回傳 ``(ctx, error)``：error 為 None 表成功（或在 upto_node 停下）；
    否則為 "[node_id] 訊息" 字串（呼叫端包成失敗結果）。
    """
    # F9-3：誰產出了哪個特徵（D1）。從 meta 撿既有的，這樣**快取續跑**接得上
    # —— 冷跑前半段的歸屬不會因為後半段是從快照續跑而消失。
    owner: Dict[str, str] = dict(ctx.meta.get(FEATURE_OWNER_KEY) or {})

    # F9-5a：每個「節點要的流」從哪個 (節點, 埠) 來。明講的線蓋過推出來的。
    bind = _bindings(recipe, order, registry, kind or str(
        ctx.meta.get("_dataset_kind") or ""))
    # (節點, 輸出埠) → 陣列。**這才是資料真正的身分**；``ctx.images`` 仍然維持
    # 「名字 → 最後一個寫它的人」那份視圖，給快取／預覽／trace 用（不變）。
    produced: Dict[Tuple[str, str], Any] = dict(
        getattr(ctx, "_produced", None) or {})
    for name, arr in ctx.images.items():
        produced.setdefault(("", name), arr)   # 快取續跑：快照來的流沒有產地

    for nid in order[start:stop]:
        node = recipe.nodes.get(nid)
        if node is None:
            traces.append(StepTrace(
                node_id=nid, step_key="?", ok=False, ms=0.0,
                error=f"step '{nid}' is not in recipe.nodes", features_added={},
                images_after=sorted(ctx.images)))
            return ctx, f"[{nid}] step '{nid}' is not in recipe.nodes"
        if not node.enabled:
            if nid == upto_node:
                break  # 目標節點被停用：停在它這裡、不執行它
            continue

        t0 = time.perf_counter()
        feats_before = dict(ctx.features)
        try:
            step_cls = registry.get(node.step)
            if step_cls is None:
                raise StepError(
                    node.step,
                    f"unknown step '{node.step}'; registered: {sorted(registry)}")
            params = step_cls.validate_params(node.params)
            # **沒有來源就不准跑**（F10）。這一格是空的，代表畫布上沒有任何
            # 一條線接進來 —— 以前這種卡照樣跑得完：`MultiStreamStep` 空的
            # ``streams`` 會退回 ``test``，量測卡的空 ``source`` 則在
            # ``ctx.images`` 那份全域名字表裡撿「最後一個寫它的人」。
            # 跑得完、有數字、而且跟畫布上畫的東西沒有關係。
            not_connected = step_cls.missing_inputs(params)
            if not_connected:
                raise StepError(
                    node.step,
                    "no input connected: %s. Drag a line from the card that "
                    "produces the image into this one."
                    % ", ".join("'%s' is empty" % n for n in not_connected))
            # F9-2/F9-5a：卡片看到的是**照它的入線組出來的** Context。
            visible: Dict[str, Any] = {}
            for name in step_cls.resolve_reads(params):
                if bind.get((nid, name), False) is None:
                    # 明講的線指到一張停用的卡，而沿線往上也沒有還開著的產出者
                    # （F9-8）。**這條線上沒有這條流** —— 讓卡片看不到它，
                    # 於是它會說「缺這條影像流」。以前這裡會退回「最後一個寫
                    # 這個名字的人」，在分支上那是隔壁那一支的圖。
                    continue
                src = bind.get((nid, name))
                if src is not None and src in produced:
                    visible[name] = produced[src]
                elif ("", name) in produced:
                    visible[name] = produced[("", name)]   # 快照來的
                elif name in ctx.images:
                    visible[name] = ctx.images[name]
            local = _local_view(ctx, visible)
            ret = step_cls().run(local, params)
            if isinstance(ret, Context):
                local = ret
            # 產出**綁節點身分**（F9-5a）：同一條 ref 分岔成兩支時，兩支各自
            # 是 (denoise_a, "ref") 與 (denoise_b, "ref")，不會互相蓋掉。
            for name, arr in local.images.items():
                produced[(nid, name)] = arr
            # 同時維持「名字 → 最後一個寫它的人」那份視圖：快取快照、單顆預覽的
            # 影像流下拉、trace 的 images_after 都吃它，全部不變。
            for name, arr in local.images.items():
                ctx.images[name] = arr
            # rois / labels 是可能被整個換掉的欄位，抄回去（features/meta 共用
            # 同一個 dict，卡片寫進去的已經在 master 上了）。
            ctx.rois = local.rois
            ctx.labels = local.labels
        except Exception as e:  # StepError / ContextError / ParamError / 其他
            ms = (time.perf_counter() - t0) * 1000.0
            traces.append(StepTrace(
                node_id=nid, step_key=node.step, ok=False, ms=ms,
                error=str(e), features_added={},
                images_after=sorted(ctx.images)))
            return ctx, _prefixed(nid, e)

        ms = (time.perf_counter() - t0) * 1000.0
        added = {
            k: v for k, v in ctx.features.items()
            if k not in feats_before or feats_before[k] != v
        }
        _rescue_overwritten_features(
            ctx, nid, feats_before,
            {k: ctx.features[k] for k in
             _produced_feature_names(step_cls, params, ctx, added)},
            owner)
        setattr(ctx, "_produced", produced)
        traces.append(StepTrace(
            node_id=nid, step_key=node.step, ok=True, ms=ms,
            error=None, features_added=added,
            images_after=sorted(ctx.images)))
        if nid == upto_node:
            break
    return ctx, None


def _eval_score(recipe: Recipe, ctx: Context) -> Tuple[float, int]:
    """ADC 判定：score = expr(features) → bin。失敗會 raise（呼叫端攔截）。"""
    expr = parse_expression(recipe.score.expr)
    score = expr.eval(ctx.features)
    ctx.features["score"] = score
    if score < float(recipe.score.threshold):
        b = int(recipe.score.bins["below"])
    else:
        b = int(recipe.score.bins["above"])
    return score, b


def run_defect(recipe: Recipe, item: Any, kind: str, *,
               keep_context: bool = False,
               upto_node: Optional[str] = None,
               track_changes: bool = False,
               registry: Optional[Dict[str, Type[Step]]] = None) -> DefectResult:
    """對單顆 defect 執行 ``kind`` 這條 route；**永不 raise**。

    - Context.meta 先種入 ``_defect_item`` / ``_dataset_kind`` / ``_defect_id`` /
      ``nm_per_px``（Load 卡讀這些 key）。
    - 停用（enabled=False）節點跳過。
    - ``track_changes``：把「每一次覆寫既有影像流的前後樣貌」記進
      ``ctx.meta['stream_change']``（F7-17 的 Enhance 儀表要的）。**預設關**——
      批次跑一萬顆時那份資料沒有人看，不值得每次 set_image 都算兩個直方圖。
    - ``upto_node``：跑到該節點**之後**就停（Studio 點卡看中間輸出用）；
      強制 keep_context=True，score/bin 不算（None）；若該節點被停用則
      停在它前面、不執行它；不在 route 上 → ok=False（不 raise）。
    - 步驟全過後：score = expr(features)、features["score"] = score、
      bin = bins["below"]（score < threshold）否則 bins["above"]。
    """
    if registry is None:
        registry = REGISTRY
    if upto_node is not None:
        keep_context = True  # 中間輸出就是要看 context

    defect_id = str(getattr(item, "defect_id", ""))
    ctx = _seed_context(item, kind, defect_id)
    ctx.track_changes = bool(track_changes)
    traces: List[StepTrace] = []

    try:
        order = execution_order(recipe, kind)
    except RecipeError as e:
        return _finish(defect_id, ctx, traces, keep_context, False, str(e))

    if upto_node is not None and upto_node not in order:
        return _finish(
            defect_id, ctx, traces, keep_context, False,
            f"upto_node '{upto_node}' is not in the execution order {order} "
            f"of route '{kind}'")

    ctx, err = _run_nodes(recipe, order, 0, len(order), ctx, traces,
                          registry, upto_node, kind)
    if err is not None:
        return _finish(defect_id, ctx, traces, keep_context, False, err)

    if upto_node is not None:
        return _finish(defect_id, ctx, traces, keep_context, True, None)

    # ---- ADC 判定：score → bin ----
    try:
        score, b = _eval_score(recipe, ctx)
    except Exception as e:
        return _finish(defect_id, ctx, traces, keep_context, False, f"[score] {e}")
    return _finish(defect_id, ctx, traces, keep_context, True, None,
                   score=score, bin_=b)


# ---------------------------------------------------------------------------
# M2：影像段 checkpoint（signature）與快取續跑
# ---------------------------------------------------------------------------
def image_segment_signature(recipe: Recipe, kind: str,
                            registry: Optional[Dict[str, Type[Step]]] = None
                            ) -> Tuple[str, int]:
    """算出 ``kind`` route 的影像段簽章與 checkpoint 索引。

    checkpoint 索引 = 執行順序中「最後一個 enabled 且 category==image 的節點」
    的下一個位置；沒有影像段節點 → 0（快取沒意義）。
    簽章 = checkpoint 前所有 enabled 節點的
    ``[(node_id, step_key, sorted-param-items), ...]`` + **落在這一段裡的線**
    + kind 的穩定 JSON 字串（params 先過 ``validate_params`` 正規化：帶預設值、
    coerce 型別，讓「寫不寫預設值」不影響簽章）。deterministic。

    ⚠ **線一定要在裡面（F9-8）。** F9 之後「資料從哪來」是線決定的，而在畫布上
    把一條線從 A 改接到 B **可以完全不動任何參數**（兩邊都叫 ``ref``）。線不進
    簽章的話那次改動算出來的簽章跟改之前一模一樣 —— 快取直接回舊影像，使用者
    看到的是「我改了接線，重跑，數字沒動」，而他會以為是自己改錯了。
    實測過：把 ``x5`` 的輸入從 ``load`` 改接到 ``x3``，正確答案 15.0，
    帶著舊快取跑出來是 5.0。

    注意：未知 route / 循環會 raise :class:`RecipeError`
    （:func:`run_defect_cached` 會攔截並退回 :func:`run_defect`）。
    """
    if registry is None:
        registry = REGISTRY
    order = execution_order(recipe, kind)

    ckpt = 0
    for i, nid in enumerate(order):
        node = recipe.nodes.get(nid)
        if node is None or not node.enabled:
            continue
        step_cls = registry.get(node.step)
        if step_cls is not None and step_cls.category == CATEGORY_IMAGE:
            ckpt = i + 1

    sig_nodes: List[List[Any]] = []
    for nid in order[:ckpt]:
        node = recipe.nodes.get(nid)
        if node is None or not node.enabled:
            continue  # 停用節點不影響執行，也不進簽章
        params: Dict[str, Any] = dict(node.params)
        step_cls = registry.get(node.step)
        if step_cls is not None:
            try:
                params = step_cls.validate_params(node.params)
            except Exception:
                params = dict(node.params)  # 壞參數：用原樣（執行時會爆，簽章仍穩定）
        items = sorted((str(k), v) for k, v in params.items())
        sig_nodes.append([nid, node.step, [list(kv) for kv in items]])

    # 影像段裡的線（F9-8）。只收 ``dst`` 落在這一段的 —— checkpoint 之後的線
    # 不影響快取住的那份影像，收進來只會讓「改了算法段」也整段重算。
    in_segment = {nid for nid in order[:ckpt]
                  if (recipe.nodes.get(nid) is not None
                      and recipe.nodes[nid].enabled)}
    sig_edges = sorted([e.src, e.src_out, e.dst, e.dst_in]
                       for e in recipe.edges if e.dst in in_segment)

    sig = json.dumps({"kind": kind, "nodes": sig_nodes, "edges": sig_edges},
                     ensure_ascii=False, sort_keys=True, default=str,
                     separators=(",", ":"))
    return sig, ckpt


def _json_safe(v: Any) -> bool:
    try:
        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False


def _meta_snapshot(meta: Dict[str, Any]) -> Dict[str, Any]:
    """meta 的可快取子集：去掉私有 key（``_`` 開頭，引擎每次重新種入）、
    去掉 JSON 序列化不了的值（例如 ndarray、物件）。
    涵蓋 warnings / notes / nm_per_px / align_dx / align_dy /
    feature_overwrites … 等後段卡片可能讀到的一般值。

    ⚠ **``feature_owner``（F9-3）一定要在裡面。** checkpoint 之前的節點在熱跑時
    根本沒有執行，所以「誰產出了哪個特徵」這份帳只能從快照回來 —— 掉了的話熱跑
    不知道 ``glv_max`` 本來是誰的，於是不會救被蓋掉的那份：**冷跑多一個特徵、
    熱跑少一個，兩邊都跑得完**。它現在是靠上面那條「非私有且 JSON-safe 就留」
    通過的（不是特例），改這個函式成白名單之前先看
    ``tests/test_batch_cache.py::test_feature_ownership_survives_a_cache_hit``。"""
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if str(k).startswith("_"):
            continue
        if _json_safe(v):
            out[k] = v
    return out


def _roi_snapshot(ctx: Context) -> List[Any]:
    """具名 ROI → ``[(name, (nx, ny, nw, nh)), ...]``（可 JSON 化）。"""
    out: List[Any] = []
    for roi in (ctx.rois.rois if ctx.rois is not None else ()):
        try:
            rect = tuple(float(v) for v in roi.norm_rect)
        except Exception:              # noqa: BLE001 — 快取是盡力而為
            continue
        out.append((str(roi.label), rect))
    return out


def _streams_needed_across_checkpoint(
        recipe: Recipe, order: List[str], ckpt: int,
        registry: Dict[str, Type[Step]], kind: str) -> Set[Tuple[str, str]]:
    """checkpoint **之後**的卡片，明講要吃 checkpoint **之前**哪幾個
    ``(節點, 埠)`` 的輸出（F9-10）。

    這就是「快照要多存哪幾張圖」的清單。為什麼不是全存：一條五張卡的影像段，
    每張卡都會留下自己的輸出，全存等於快取檔按張數倍增 —— 而絕大多數中間結果
    在 checkpoint 之後根本沒有人要。

    ⚠ **這份清單會隨 checkpoint 之後的線改變，而那些線刻意不在簽章裡**
    （不然改一下量測卡的接線就要整段重算影像）。所以「照這份清單存」一定要配
    :func:`run_defect_cached` 裡那條防線：熱跑時要的不在快照裡就**當 miss
    重算**，不可以退回 ``ctx.images``（那是「最後一個寫這個名字的人」，在分支
    上就是隔壁那一支）。少了那條防線，這個做法會製造一個新的安靜錯誤。
    """
    before = set(order[:ckpt])
    bind = _bindings(recipe, order, registry, kind)
    # **只算明講的線。** 推出來的（``_implicit_bindings``）本來就是「執行順序上
    # 最後一個寫這個名字的人」，那正好等於快照裡的 ``images`` —— 退回去拿到的
    # 是同一張圖。所以既有的（沒有埠的）recipe 一張都不必多存，快取大小完全
    # 沒變；只有真的在畫布上拉了線的地方才付這個代價。
    explicit = set(_explicit_bindings(recipe, registry))
    need: Set[Tuple[str, str]] = set()
    for nid in order[ckpt:]:
        node = recipe.nodes.get(nid)
        if node is None or not node.enabled:
            continue
        step_cls = registry.get(node.step)
        if step_cls is None:
            continue
        try:
            params = step_cls.validate_params(node.params)
        except Exception:              # noqa: BLE001 — 壞參數交給 validate 報
            continue
        for name in step_cls.resolve_reads(params):
            if (nid, name) not in explicit:
                continue
            src = bind.get((nid, name))
            if src is not None and src[0] in before:
                need.add(src)
    return need


def _restore_context(item: Any, kind: str, defect_id: str,
                     snap: Dict[str, Any]) -> Context:
    """由快取快照重建 Context。

    **Context 的每一個欄位都要回來**，不只 images/features/meta。checkpoint 是
    執行順序上的位置，不是「所有影像段的卡」，所以夾在中間的 Region 卡
    （algo）會落在快取段裡 —— 漏掉 ``rois`` 的話會變成「第一次跑對、第二次跑
    錯」。見 :mod:`.cache` 的模組說明。
    """
    ctx = _seed_context(item, kind, defect_id)
    for name, arr in dict(snap.get("images") or {}).items():
        ctx.images[str(name)] = arr
    for name, val in dict(snap.get("features") or {}).items():
        ctx.features[str(name)] = float(val)
    for k, v in dict(snap.get("meta") or {}).items():
        ctx.meta[str(k)] = v  # 快照不含 ``_`` 開頭 key，不會蓋掉剛種的
    # **一個名字可能有好幾個框**（F8 的交會定位）。逐一 ``set_roi`` 是錯的 ——
    # 它會先刪掉同名的，所以 17 個框還原完只剩最後一個：冷跑量 17 塊、熱跑量
    # 1 塊，而兩邊都跑得完、都有數字。這正是 F7-9 那條「第一次跑對、第二次跑
    # 錯」，只是這次不是整組不見而是**只剩一個**，更難發現。
    grouped: Dict[str, List[Any]] = {}
    for name, rect in (snap.get("rois") or []):
        grouped.setdefault(str(name), []).append(rect)
    for name, rects in grouped.items():
        ctx.set_roi_boxes(name, rects)
    labels = snap.get("labels")
    if labels is not None:
        ctx.labels = labels
    # F9-10：把「哪個節點的哪顆埠產出了這張圖」也接回去。少了它，指向快取段內
    # 某個節點的線在熱跑時查不到，會退回「最後一個寫這個名字的人」＝隔壁那支。
    prod = dict(snap.get("produced") or {})
    if prod:
        setattr(ctx, "_produced", {(str(k[0]), str(k[1])): v
                                   for k, v in prod.items()})
    return ctx


def run_defect_cached(recipe: Recipe, item: Any, kind: str,
                      cache: Any, dataset_token: str, *,
                      keep_context: bool = False,
                      registry: Optional[Dict[str, Type[Step]]] = None
                      ) -> DefectResult:
    """帶影像段快取的單顆執行；**永不 raise**，結果與 :func:`run_defect`
    位元級一致（features / score / bin）。

    - 影像段（到 checkpoint 為止）命中快取 → 直接重建 Context 續跑算法段；
      未命中 → 跑影像段、寫入快取（:class:`.cache.StageCache`）、續跑。
    - checkpoint == 0（沒有影像段節點）或快取讀/寫失敗 → 退回全程重算，
      不會 crash。
    - 快取命中時 ``traces`` 只含 checkpoint 之後的節點（影像段沒真的跑）。
    """
    if registry is None:
        registry = REGISTRY

    try:
        sig, ckpt = image_segment_signature(recipe, kind, registry=registry)
    except Exception:
        return run_defect(recipe, item, kind,
                          keep_context=keep_context, registry=registry)
    if cache is None or ckpt <= 0:
        return run_defect(recipe, item, kind,
                          keep_context=keep_context, registry=registry)

    defect_id = str(getattr(item, "defect_id", ""))
    key: Optional[str] = None
    snap: Optional[Dict[str, Any]] = None
    try:
        key = cache.make_key(str(dataset_token), defect_id, sig)
        snap = cache.get(key)
    except Exception:
        snap = None  # 快取層出包 → 當作 miss

    order = execution_order(recipe, kind)  # signature 已驗證過，不會再 raise
    traces: List[StepTrace] = []
    ctx: Optional[Context] = None

    # 這次要用到快取段裡哪幾個 (節點, 埠)（F9-10）。
    try:
        need = _streams_needed_across_checkpoint(recipe, order, ckpt,
                                                 registry, kind)
    except Exception:                  # noqa: BLE001 — 算不出來就別用快取
        need = None

    if snap is not None and need is not None:
        # **缺了就重算**：快照只存了「當時有人要的那幾張」，而「誰要」是由
        # checkpoint 之後的線決定的 —— 那些線改了簽章不會變（刻意的，見
        # image_segment_signature），於是會出現「快取有效、但這次要的那張沒存」。
        # 退回 ctx.images 的話就是安靜地拿到隔壁那一支的圖，所以這裡當 miss。
        have = set(dict(snap.get("produced") or {}))
        if not need.issubset(have):
            snap = None

    if snap is not None:
        try:
            ctx = _restore_context(item, kind, defect_id, snap)
        except Exception:
            ctx = None  # 快照壞掉 → 退回重算影像段

    if ctx is None:
        # miss：跑影像段（order[:ckpt]），成功才寫快取
        ctx = _seed_context(item, kind, defect_id)
        ctx, err = _run_nodes(recipe, order, 0, ckpt, ctx, traces,
                              registry, None, kind)
        if err is not None:
            return _finish(defect_id, ctx, traces, keep_context, False, err)
        if key is not None:
            try:
                produced = dict(getattr(ctx, "_produced", None) or {})
                cache.put(key, dict(ctx.images), dict(ctx.features),
                          _meta_snapshot(ctx.meta),
                          rois=_roi_snapshot(ctx), labels=ctx.labels,
                          produced={k: produced[k] for k in (need or ())
                                    if k in produced})
            except Exception:
                pass  # 快取寫入失敗 → 不影響本次結果

    # 續跑算法段 + ADC 判定
    ctx, err = _run_nodes(recipe, order, ckpt, len(order), ctx, traces,
                          registry, None, kind)
    if err is not None:
        return _finish(defect_id, ctx, traces, keep_context, False, err)
    try:
        score, b = _eval_score(recipe, ctx)
    except Exception as e:
        return _finish(defect_id, ctx, traces, keep_context, False, f"[score] {e}")
    return _finish(defect_id, ctx, traces, keep_context, True, None,
                   score=score, bin_=b)


def run_dataset(recipe: Recipe, dataset: Any, *,
                progress: Optional[Callable[[int, int, DefectResult], Any]] = None,
                limit: Optional[int] = None) -> List[DefectResult]:
    """循序跑整個 dataset（M1 單進程；平行批次見 :func:`.batch.run_batch`）。

    - ``limit``：只跑前 N 顆（調參試跑用）。
    - ``progress(i, n, result)``：每顆跑完呼叫一次（i 為 0 起算的索引）。
    - 單顆失敗不影響其他顆（run_defect 永不 raise）。
    """
    items = list(dataset.items) if limit is None else list(dataset.items)[:limit]
    n = len(items)
    results: List[DefectResult] = []
    for i, item in enumerate(items):
        r = run_defect(recipe, item, dataset.kind)
        results.append(r)
        if progress is not None:
            progress(i, n, r)
    return results


# ---------------------------------------------------------------------------
# JSON 匯出（CLI `adept run` 輸出 features JSON 用）
# ---------------------------------------------------------------------------
def _safe_num(v: Any) -> Optional[float]:
    """float 化；nan/inf/ndarray/不可轉 → None（JSON 安全）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def result_to_json_dict(r: DefectResult) -> Dict[str, Any]:
    """DefectResult → 可直接 ``json.dumps`` 的 dict。

    不含 ndarray、不含 context；nan/inf → None；ms 取 3 位小數。
    """
    return {
        "defect_id": r.defect_id,
        "ok": bool(r.ok),
        "error": r.error,
        "features": {k: _safe_num(v) for k, v in r.features.items()},
        "score": _safe_num(r.score),
        "bin": None if r.bin is None else int(r.bin),
        "traces": [
            {
                "node_id": t.node_id,
                "step_key": t.step_key,
                "ok": bool(t.ok),
                "ms": round(float(t.ms), 3),
                "error": t.error,
                "features_added": {k: _safe_num(v)
                                   for k, v in t.features_added.items()},
                "images_after": [str(x) for x in t.images_after],
            }
            for t in r.traces
        ],
    }


def _prefixed(nid: str, e: Exception) -> str:
    """``[節點 id] 訊息`` —— 但**同一個名字不印兩次**。

    節點 id 與 step key 是兩回事（畫布上可以有三張 Denoise），所以錯誤訊息兩個
    都要有：`StepError` 帶 step key，這裡補節點 id。但一張卡剛加進來時節點 id
    **就是** step key，於是使用者看到的是
    ``[load_sidecar] [load_sidecar] defect 3 has no layout label…`` ——
    重複的那半個字讀起來像程式壞了，而它出現在使用者最需要看懂訊息的時候。
    """
    text = str(e)
    head = "[%s] " % nid
    return text if text.startswith(head) else head + text
