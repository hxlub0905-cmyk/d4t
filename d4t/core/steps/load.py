# d4t step-card library — authored 2026-07-28 (M1).
"""載入影像的卡 —— **一張 Input 卡**（F121 期 2，2026-09-24）。

從 ``ctx.meta["_defect_item"]``（ingest 層的 DefectItem，由引擎放入）讀出
這顆 defect 的像素並寫進 ``ctx.images``。

| 卡 | 一顆給什麼 | 吐什麼 |
|---|---|---|
| ``load_patch``「Input」| 一張或好幾張（RSEM、影像資料夾、EBI patch、多通道）| ``channel_map`` 表格裡的名字 |

**key 留 `load_patch`**：它是 recipe 的鍵，不是給人看的字（`CLAUDE.md` §5：只改
``label`` 零代價）—— 出貨 recipe 與黃金值裡的那個字一個都不動。

為什麼又合回一張（使用者 2026-09-24）
-------------------------------------
F11 Input-4（2026-08-17）照使用者的話拆成兩張 —— `load_patch`「Patch」與
`load_single`「SEM image」：

> 我現在 load 一張 RSEM image 他就是單張的，但其後的 NODE 節點會有 TEST 跟 REF？
> 但實際上是 Single。**這樣畫布跟實際對不起來。**

那一刀解掉的是「**宣告跟著隱形的資料型別變**」（拆之前 ``resolve_writes`` 說
``["test"]``、``resolve_writes_for_kind("rsem")`` 說 ``["single", "test"]``、畫布
畫 ``["test", "ref"]``，而資料只有 ``["single"]``）。拆完之後兩張卡的宣告都只看
使用者看得到的值 —— 而**那個條件合回一張也成立**：埠＝名字表，名字表在開資料時
照資料填（一顆一張就是一列 ``1:single``，見 :func:`channel_map_for`）。

合的理由是使用者要的「入口簡單化」（`docs/plans/F121-simple-input.md`）：兩張卡
要使用者先選對，而選錯的下場是每一顆都報錯。實測 `load_single(out="x")` 與
`load_patch(channel_map="1:x")` 在一顆一張的資料上**像素與特徵逐一相同** —— 兩張卡
差的只是預設值。舊 recipe 的 `load_single` 由 `recipe_migrations` 換成這一張。

⚠ **合完之後差的那一格是使用者同意過的**：一顆好幾張、名字表只寫一列時讀第一張，
並警告其餘沒載入（以前 `load_single` 會拒絕）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..pipeline.channels import (
    highest_image_number, mapped_names, parse_channel_map,
)
from ..ingest.dataset import images_in_order
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_INPUT,
)
from ._util import (
    carry_spec, ensure_gray, nm_per_px_spec, only_code_hints, only_code_specs,
    parse_key_list, parse_only_codes, to_uint8,
)

# "auto" 模式下 channel 的優先順序（其餘 channel 依名稱排序附加在後）
_PREFERRED_ORDER = ("test", "ref", "single")


#: ``load_patch`` 的 ``channel_map`` 預設值 —— 也就是 EBI patch 的老規矩
#: （第 1 張 test、第 2 張 ref）。
#:
#: **它為什麼不能是空字串**（F11 Input-4）：空的話「這張卡吐哪幾條流」就只能問
#: 資料型別（``resolve_writes_for_kind``），而那正是「畫布跟實際對不起來」的來源。
#: 給它一個看得見的預設值之後，宣告永遠等於**使用者看得到的那張表**。
DEFAULT_CHANNEL_MAP = "1:test, 2:ref"


@register_step
class LoadPatchStep(Step):
    """把 DefectItem 的影像（一張或好幾張）載入成 Context 影像流（一律 uint8 灰階）。"""

    key = "load_patch"
    label = "Input"
    category = CATEGORY_IMAGE
    group = GROUP_INPUT
    help = ("Load this defect's images into the pipeline, always converted to "
            "8-bit grayscale - one image (Review SEM, a folder of images) or "
            "several (a test/reference pair, detector channels). The table "
            "names each image; the names are the streams on the canvas, and "
            "opening data fills it in for you.")
    params = [
        ParamSpec(
            name="channel_map", type="channel_map", default=DEFAULT_CHANNEL_MAP,
            label="Name the images",
            help=("Name this defect's images by position: 1 is the first "
                  "image, 2 the second, and so on (for example "
                  "'1:se1, 2:bse, 3:se2'). These names are the streams on the "
                  "canvas and the prefix on each image's features. An image "
                  "you leave unnamed is not loaded."),
        ),
        ParamSpec(
            name="channels", type="str", default="auto",
            help=("Which of the named images to load: auto = all of them; or a "
                  "comma separated list such as test,ref when you only want "
                  "some."),
        ),
        nm_per_px_spec(),
        carry_spec(),
    ] + only_code_specs()
    reads: List[str] = []
    writes = ["test", "ref"]     # ＝ DEFAULT_CHANNEL_MAP 的名字（靜態備援）
    features_out = ["n_channels"]
    FEATURE_HELP = {"n_channels": "how many images this defect had"}

    @classmethod
    def item_filter(cls, params):
        """只跑 KLARF 某一欄符合的那幾顆（F50）—— 見 `Step.item_filter`。"""
        return parse_only_codes(params)

    @classmethod
    def configuration_hints(cls, params: Dict[str, Any]) -> List[str]:
        return only_code_hints(params)

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        """**只看使用者看得到的值**：對照表的名字（或 ``channels`` 挑的子集）。

        不再有 kind-aware 的版本（F11 Input-4）—— 一張卡對不同資料型別宣告不同的
        東西，就是「畫布跟實際對不起來」的來源。
        """
        # ⚠ **參數沒寫 ≠ 空的對照表。** 這幾個 `resolve_*` 拿到的是**原始**
        # `node.params`（recipe JSON 省略預設值是合法的，見
        # `test_a_subtract_without_an_explicit_b_keeps_the_card_default`），
        # 所以「沒有這個鍵」要回到卡片的預設值，而「有這個鍵但是空字串」是使用者
        # 真的把每一列都清掉了 —— 那就是「什麼都沒命名」，宣告因此是空的。
        # 第一版把兩者混成一件事，畫布上的 Input 卡當場一顆埠都不剩（測試抓到）。
        raw_map = params.get("channel_map", DEFAULT_CHANNEL_MAP)
        mapped = mapped_names(parse_channel_map(raw_map))
        raw = str(params.get("channels", "auto")).strip()
        if raw.lower() == "auto":
            return mapped
        wanted = [tok.strip() for tok in raw.split(",") if tok.strip()]
        return [w for w in wanted if not mapped or w in mapped] or mapped

    @classmethod
    def data_issues(cls, params: Dict[str, Any],
                    data: Any) -> List[Tuple[str, str, str, str]]:
        """這張卡跟**開著的那份資料**對不對得上（F121 期 3，見 `Step.data_issues`）。

        三件事，每一件在開資料那一刻就知道，而跑下去的話是**每一顆報一次**：

        * 名字表要的張數比資料多（EBI 的 ``1:test, 2:ref`` 開在一張一張的 RSEM
          上 —— 使用者回報的那一個）→ error；
        * 名字表比資料少 → info（使用者同意的行為：讀有名字的那幾張，其餘不載入）；
        * ``carry`` / ``only_*`` 要 KLARF 的欄位，而這份資料沒有 KLARF 或沒有那一欄
          → error（沒有 KLARF 時 ``only_*`` 以前講的是「篩選條件沒對上」，真正的
          原因沒講）。
        """
        out: List[Tuple[str, str, str, str]] = []
        n_min = int(getattr(data, "images_min", 0) or 0)
        n_max = int(getattr(data, "images_max", 0) or 0)
        have = [str(n) for n in (getattr(data, "image_names", ()) or ())]
        try:
            pairs = parse_channel_map(params.get("channel_map",
                                                 DEFAULT_CHANNEL_MAP))
        except Exception:                 # 壞值由 bad-param 講，這裡不重複
            pairs = []
        need = highest_image_number(pairs)
        if n_min == n_max:
            count = "%d image%s" % (n_min, "" if n_min == 1 else "s")
        else:                             # 有幾顆少拍了：講範圍，不挑一個數
            count = "%d to %d images" % (n_min, n_max)
        if n_max and need > n_min:
            out.append((
                "input-too-few-images", "error",
                "“Name the images” asks for more images than this data has",
                "This data has %s per defect (%s), and “Name the images” asks "
                "for %d (%s). Fill the names in from this data, or open the "
                "data this recipe was written for."
                % (count, ", ".join(have) or "none", need,
                   ", ".join(mapped_names(pairs)))))
        elif n_max and pairs and need < n_max:
            named = {int(pos) for pos, _n in pairs}
            unnamed = [have[i] if i < len(have) else "image %d" % (i + 1)
                       for i in range(n_max) if (i + 1) not in named]
            out.append((
                "input-unnamed-images", "info",
                "Some of this data's images are not loaded",
                "This data has %s per defect, and “Name the images” names %d "
                "of them - the rest (%s) are not loaded. Name them too if you "
                "want them on the canvas."
                % (count, len(named), ", ".join(unnamed))))

        has_klarf = bool(getattr(data, "has_klarf", False))
        klarf_cols = [str(c) for c in (getattr(data, "columns", ()) or ())]
        wants = [("“Carry these columns”", _carry_names(params))]
        only = parse_only_codes(params)
        if only is not None:
            wants.append(("“Only run this column”", [only[0].strip().upper()]))
        for field_label, cols in wants:
            if not cols:
                continue
            if not has_klarf:
                out.append((
                    "input-needs-klarf", "error",
                    "%s needs a KLARF, and this data has none" % field_label,
                    "%s is set to %s, but this data has no KLARF to read it "
                    "from - every defect would fail. Clear it, or open the "
                    "KLARF this recipe was written for."
                    % (field_label, ", ".join(cols))))
                continue
            missing = [c for c in cols if klarf_cols and c not in klarf_cols]
            if missing:
                out.append((
                    "input-no-such-column", "error",
                    "This KLARF has no column called %s" % ", ".join(missing),
                    "%s asks for %s, and this KLARF has no such column. It "
                    "has: %s." % (field_label, ", ".join(missing),
                                  ", ".join(klarf_cols))))
        return out

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        """``n_channels`` ＋ ``carry`` 點名的那幾欄（F16）。

        **宣告要跟著參數走**，不然那幾欄在 `available_features` 的下拉裡不存在
        —— 使用者就得用打的，而打錯只會得到一條 `unknown-feature` 警告。
        非數字的欄位仍然宣告：卡片手上沒有 KLARF，分不出哪一欄是數字，而
        「宣告」的意思是「可能會碰到的」（同 `MultiSourceStep` 的 nm 那一份）。
        """
        return ["n_channels"] + _carry_names(params)

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        item = ctx.meta.get("_defect_item")
        kind = ctx.meta.get("_dataset_kind")
        if item is None:
            raise StepError(self.key, "no defect data in the Context (meta['_defect_item']); this "
                            "card must be run by the engine after a dataset is loaded.")
        images = getattr(item, "images", None)
        if not images:
            raise StepError(self.key, f"defect {getattr(item, 'defect_id', '?')} has no images to load.")

        # ---- 通道對照表（F11 Input-1）：第幾張 → 叫什麼 ----------------------
        #
        # 對照表在 **recipe** 裡（使用者定調），所以同一份 recipe 拿到頁序不同的
        # 資料時**必須擋下來**：宣告了第 5 張的名字而這顆只有 2 張，照順序硬套的
        # 後果是「BSE 的數字寫在 SE 的名字上」—— 跑得完、有數字、而且是錯的。
        pairs = parse_channel_map(p.get("channel_map", ""))
        order = images_in_order(images)
        #: 流名 → **ingest 給的 channel 名**。改名只改「流叫什麼」，讀圖仍然要
        #: 用資料自己的 key（`item.load()` 只認得它自己那一份）。
        src_of = {k: k for k in order}
        if pairs:
            need = highest_image_number(pairs)
            if need > len(order):
                raise StepError(
                    self.key,
                    "the image names say there are at least %d images per "
                    "defect, but defect %s has %d (%s). Fix “Name the "
                    "images” to match this data, or open the data this "
                    "recipe was written for."
                    % (need, getattr(item, "defect_id", "?"), len(order),
                       ", ".join(order)))
            src_of = {name: order[page - 1] for page, name in pairs}
            unnamed = [k for k in order if k not in set(src_of.values())]
            if unnamed:
                # 沒被命名的那幾張**不載入**，但要講一句 —— 資料比 recipe 命名的
                # 多是使用者該知道的事（少講的話他會以為每一張都算進去了）。
                # 講的是「哪幾張」而不只是「幾張」：中間跳號也要看得見。
                ctx.warn("[%s] defect %s has %d images but only %d are named; "
                         "the rest (%s) are not loaded."
                         % (self.key, getattr(item, "defect_id", "?"),
                            len(order), len(src_of), ", ".join(unnamed)))
            images = {name: images[src] for name, src in src_of.items()}

        raw = str(p["channels"]).strip()
        if raw.lower() == "auto":
            avail = list(images.keys())
            wanted = [c for c in _PREFERRED_ORDER if c in avail]
            wanted += sorted(c for c in avail if c not in wanted)
        else:
            wanted = [tok.strip() for tok in raw.split(",") if tok.strip()]
            if not wanted:
                raise StepError(self.key, "the channels parameter is empty; use auto or a comma "
                                "separated list (e.g. test,ref).")

        loaded: List[str] = []
        for ch in wanted:
            if ch not in images:
                raise StepError(
                    self.key,
                    f"defect {getattr(item, 'defect_id', '?')} has no channel "
                    f"'{ch}' (available: {sorted(images)}).")
            try:
                arr = item.load(src_of.get(ch, ch))
            except Exception as e:  # 檔案毀損 / 頁碼超界等
                raise StepError(self.key, f"could not read channel '{ch}': {e}") from e
            arr_u8 = to_uint8(ensure_gray(arr))
            ctx.set_image(ch, arr_u8)
            loaded.append(ch)

        # ⚠ 這裡以前有一段「``single`` 順手鏡射成 ``test``」（讓單張資料的下游用
        # 預設參數就吃得到圖）。**F11 Input-4 拿掉了** —— 那是「宣告比現實多」的
        # 一個實例：資料只有一張圖，畫布上卻有兩顆埠。單張資料的名字表就是一列
        # （開資料時 :func:`channel_map_for` 填的），吐**一條**流。

        _apply_nm_per_px(ctx, p, loaded)
        _write_input_panel(ctx, item, kind, loaded, images)
        ctx.add_feature("n_channels", float(len(loaded)))
        _carry_features(ctx, item, p, self.key)
        return ctx


def channel_map_for(item: Any) -> str:
    """**這一顆的影像**照順序排成一張名字表（開資料時填 Input 卡用，F121 期 2）。

    名字就是 ingest 給的 channel 名（patch 是 ``test`` / ``ref`` / ``img3``…，
    一顆一張是 ``single``），所以 EBI patch 填出來正好是
    :data:`DEFAULT_CHANNEL_MAP`，而 RSEM／影像資料夾是 ``1:single`` —— 畫布上的埠
    因此一開始就等於資料真的有的那幾張（畫布不說謊）。沒有影像回空字串。
    """
    return fit_channel_map("", item)


def fit_channel_map(current: Any, item: Any) -> str:
    """把一張名字表**對齊到這一顆的影像**（「照這份資料填」那顆鈕，F121 期 3）。

    規則是「**線能留的就留**」：資料有的那幾個位置保留原本的名字（下游接的是
    名字，名字不動線就不動）；資料沒有的位置拿掉（那幾顆埠消失，接著它們的
    下游卡在畫布上變紅 —— 使用者一眼看得出哪幾張卡在這種資料上做不到）；
    資料多出來的位置補上 ingest 給的名字。

    使用者回報的那一個：EBI 的 ``1:test, 2:ref`` 對上一顆一張的 RSEM →
    ``1:test`` —— test 那一條照跑，吃 ref 的那幾張變紅。空的名字表就是
    :func:`channel_map_for`。解不開的舊值當成空的（壞值由 bad-param 講話）。
    """
    have = images_in_order(dict(getattr(item, "images", None) or {}))
    try:
        named = {int(pos): str(n) for pos, n in parse_channel_map(current or "")}
    except Exception:                     # 壞值：當成沒填，照資料給
        named = {}
    return ", ".join("%d:%s" % (i + 1, named.get(i + 1, name))
                     for i, name in enumerate(have))


def _carry_names(params: Dict[str, Any]) -> List[str]:
    """這張卡要把哪幾個 KLARF 欄位帶成 feature（大寫）。"""
    return [c.upper() for c in parse_key_list(params.get("carry", ""))]


def columns_for_main(nodes: Any) -> List[str]:
    """**每一張** Load 卡的 ``carry`` 聯集（大寫，保留出現順序）。

    掛主資料集的時候只複製這幾欄（`ingest.dataset.fill_fields` 的 ``columns``）
    —— 一份 raw data 是幾十萬顆，×24 欄字串是幾百 MB，而那幾欄還要 pickle 進
    每一個 worker。跟 F15 的 `pair_source.columns_for_source` 是同一件事的
    另一半，所以刻意長得一模一樣。

    **這件事只寫在這裡**：`carry` 的意思是這張卡的事，抄第二份出去的那一份
    會漂（`ROADMAP` / UI / CLI 各一份的話，「哪幾欄要帶」就有三個答案）。
    """
    # **dict 也吃得下**：`recipe.nodes` 是 ``{id: RecipeNode}``，而直接迭代它
    # 拿到的是 **id 字串** —— `getattr(str, "step")` 是空的，於是這支安靜地回
    # 空清單、一欄都不帶，而症狀出現在很後面（每一顆都說「這份 KLARF 沒有那個
    # 欄位」，因為根本沒填）。實測踩到，所以在這裡收掉而不是要求每個呼叫端記得
    # 加 `.values()`。
    if hasattr(nodes, "values"):
        nodes = list(nodes.values())
    out: List[str] = []
    for node in (nodes or ()):
        step = str(getattr(node, "step", "") or "")
        if step != "load_patch":
            continue
        params = dict(getattr(node, "params", None) or {})
        for col in _carry_names(params):
            if col not in out:
                out.append(col)
    return out


def _carry_features(ctx: Context, item: Any, params: Dict[str, Any],
                    step_key: str) -> None:
    """把 ``carry`` 點名的欄位寫成 feature（數字），非數字的留給報表。

    命名**就是欄名本身**（``ROUGHBINNUMBER``），不加前綴：那是使用者在 KLARF
    裡看到的字，而 KLARF 的欄名本來就是合法的變數名，打進分數表達式不用翻譯。
    （`pair_source` 加 ``pair_`` 是因為它帶的是**另一份**的同名欄 —— 不加的話
    兩份的同一欄會撞在一起。）
    """
    want = _carry_names(params)
    if not want:
        return
    fields = dict(getattr(item, "fields", None) or {})
    missing = [c for c in want if c not in fields]
    if missing:
        # **打錯一個欄名不可以安靜地沒事**：少一欄的 CSV 跟成功的 CSV 長得
        # 一模一樣，而使用者要到寫分數表達式時才發現那個變數指不到。
        raise StepError(
            step_key,
            "this lot has no KLARF column called %s. What it does have: %s. "
            "Fix “Carry these columns”."
            % (", ".join(missing), ", ".join(sorted(fields)) or "(nothing)"))
    for col in want:
        raw = str(fields.get(col, ""))
        try:
            ctx.add_feature(col, float(raw))
        except (TypeError, ValueError):
            # 帶不動的欄位（DEFECTID 那種字串）留在 meta 給報表 —— feature 是
            # **數字**的地盤，塞一個字串進去會讓分數表達式炸在一個跟它無關的
            # 地方。同 `pair_source` 的處置，不發明第二種。
            ctx.meta.setdefault("klarf_fields", {})[col] = raw


def _apply_nm_per_px(ctx: Context, p: Dict[str, Any],
                     streams: Optional[List[str]] = None) -> None:
    """卡片上填的 nm/px **覆蓋**資料自己帶的那個（2026-08-20）。

    引擎會先把 ``item.nm_per_px`` 種進 ``meta``（目前 KLARF 裡沒有來源，所以
    永遠是 ``None``）。使用者在這張卡上填的是他從機台設定抄來的數字 ——
    有人負責的那一個 —— 所以它說了算。填 0（預設）＝ 不知道，
    那就維持 ``None``，下游一律留在 pixel。
    """
    try:
        value = float(p.get("nm_per_px", 0.0) or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0:
        ctx.meta["nm_per_px"] = value
        # 這張卡吐的每一條流也各自登記一份 —— 一份 pipeline 可以同時吃兩份
        # 資料（F15），而兩台機台的像素大小不一樣（見 `Context.stream_nm_per_px`）。
        for name in (streams or []):
            ctx.set_stream_nm_per_px(name, value)


def _write_input_panel(ctx: Context, item: Any, kind: Any,
                       loaded: List[str], refs: Dict[str, Any]) -> None:
    """面板用（F7-17）：**每條影像流是從哪一頁來的、載進來長什麼樣**。

    「第一張是 test、第二張是 ref」已於 2026-07-30 由使用者確認，所以這裡不再是
    「驗證假設」的工具。留著是因為配對關係在別的地方都看不到：一顆出三頁以上、
    或 ``channel_map`` 改過名字的資料集，只有這份 meta 講得出實際載進來的是什麼。
    平均灰階則是拿來判「這兩張比得起來嗎」。

    F11 那兩張 Input 卡共用過它（抄兩份的話總有一份會長歪）；F121 合回一張。
    """
    pages = []
    for ch in loaded:
        ref = refs.get(ch)
        arr = ctx.images.get(ch)
        pages.append({
            "channel": ch,
            "page": None if ref is None else getattr(ref, "page", None),
            "file": "" if ref is None else str(getattr(ref, "path", "")),
            "shape": None if arr is None else [int(v) for v in arr.shape[:2]],
            "mean": None if arr is None else float(arr.mean()),
        })
    ctx.meta["input"] = {
        "kind": str(kind or ""),
        "defect_id": str(getattr(item, "defect_id", "")),
        "die": list(getattr(item, "die", None) or []),
        "xrel_nm": getattr(item, "xrel_nm", None),
        "yrel_nm": getattr(item, "yrel_nm", None),
        "klarf_row": int(getattr(item, "klarf_row", -1)),
        "nm_per_px": getattr(item, "nm_per_px", None),
        "pages": pages,
    }
