# d4t step-card library — authored 2026-07-29 (F7-12); regions reworked 2026-08-18 (F11 Region-1).
"""roi_template —— 用 Golden Cell 模板把每張 patch 對回版圖的相位，再放框。

跟投影定位（``roi_profile``）的分工
-----------------------------------
兩張卡解的是同一個問題（結構在每張 patch 裡的位置不一樣），差別在**資訊從哪來**：

* **投影定位**只看 patch 自己。便宜、不需要任何額外檔案，但只有在 patch 裡看得到
  地標時才定得出來。
* **模板定位**（這張）用大圖疊出來的一個完整週期當模板。patch 比週期小也沒關係
  —— 是把小 patch 滑進大模板，不是把小片互相對位。

模板長什麼樣、為什麼原點要錨在地標上、信心值為什麼看的是「峰有多突出」而不是
分數本身 —— 全部寫在 ``algo/template.py`` 的模組說明裡。

**同一張卡也是「單張大圖」那條路**（F11 Region-5，2026-08-18）
---------------------------------------------------------------
使用者原本以為那要另一張卡：「他是用在 repeating pattern 的 SEM（單張影像圖），
他鋪 ROI 的方式就是跟 template 很像，只不過他是反向把單 cell 鋪回去。」

**量過了：這張卡已經在做那件事。** 1000×1000 的合成 SEM、cell 40×40、兩軸都
重複，餵進去得到 **625 個框、相位正確、match 1.00、61 ms**。理由在
``algo/template.roi_boxes_in_patch``：它明講自己同時涵蓋兩種大小關係 ——
cell 比圖大（模板法的常態，最多落一份）與 **cell 比圖小（每一份都畫）**。

所以兩種用法**不是兩張卡，也不是一個下拉**，差別完全在「你把哪一條流接進去」
（F9：資料從哪來由線決定）：

============  ==========================  ====================================
接什麼        cell 與圖的大小關係          框出什麼
============  ==========================  ====================================
一張 patch    cell 通常比 patch 大         這一顆看得到的那一份（可能沒有）
一張大 SEM    cell 比圖小很多              每一份都畫（幾百到幾千個）
============  ==========================  ====================================

唯一真的擋路的是 ``max_boxes``：預設 64 會把 625 份**安靜地**留 64 份。所以它
改成 8192（跟 `roi_reference` 同一組數字 —— 兩張會吐幾千個框的 ROI 卡用同一個
上限，少一個要解釋的數字），而被砍到的時候 ``<name>_clipped`` 會講。實測不封頂
的成本：4 px pitch 的 1000×1000（62500 個框）也只要 83 ms。

配套的是**對話框**：疊 cell 的那張大圖，在這條路上就是使用者正在看的那一顆
（`TemplateDialog.set_screen_image`）。逼他去磁碟上找回同一個檔案，是把他已經
做完的事再做一次，而且很容易挑到別顆。

一張卡標**好幾個區域**，一個區域**好幾個矩形**（F11 Region-1）
--------------------------------------------------------------
以前是四個手打的數字（``roi_x/y/w/h``）加一個名字，也就是一張卡只框得出一個
矩形、一個區域。但站點要的東西不長那樣 —— 使用者的原話：

    「一個 layout 是橫向 EPI 跟直向 MG 交錯，我要的 ROI1 是 EPI 部分扣掉 MG
     交集。」

那個形狀用一個矩形表達不出來，用好幾個就可以（半導體 layout 幾乎都是曼哈頓的
—— F11 §3.3.2 的答案 B）。所以現在是一個 ``regions`` 參數，值是
``ROI1: 0.1,0,0.25,1; 0.62,0,0.25,1 | ROI2: …``（編碼與規則見
``pipeline/cellrois.py``），而框是在 Studio 的模板編輯器上**畫**出來的
—— 四個 0–1 的數字沒有一個地方講得清楚它們相對於什麼，一張圖講得清楚。

確定度（``margin``）預設**不當門檻**
------------------------------------
使用者回報「certainty 還是會太小，還是拿掉？」——「拿掉」的是門檻，不是數字。

* **數字要留著**：它是唯一講得出「這一顆可能落在另一份上」的東西。
* **門檻預設 0**：週期性強的 layout 上這個數字對每一顆都小，拿它擋顆數，
  擋掉的多半是好的。

而「落在另一份上要不要緊」這個問題**已經有一個確定的答案了**：把區域整組平移
1/k 看落不落回自己（``configuration_issues``）。落得回去就無害，落不回去卡片
會在跑之前就講。**有了那個檢查，margin 就不必再當一道盲目的閘門。**

cell 可以取成週期的 k 倍（使用者：「有時候會需要 2X 大 cell」）
----------------------------------------------------------------
那時候影像其實仍然以 1× 重複，於是相關面摺回「一個 cell」之後有 k 個一模一樣的
峰 —— 最高 ＝ 次高，``margin``（確定度）歸零，而預設門檻會把**每一顆**都判成
定不出來。實測：1× 的 cell margin 0.37–0.61，2× 與 3× 都是 0.000。

解法在 ``algo/template``：模板字串（``gc2:``）帶著**這個 cell 自己重複的單元**，
確定度摺在那個單元上、位置仍然摺在整個 cell 上。兩者摺在不同週期是刻意的 ——
框是標在整個 cell 上的，但那 k 個峰是同一個答案的複本。

框是**整片鋪過去**的，不是只放一份
----------------------------------
使用者標的是重複結構上的一塊，所以那塊在 patch 裡有幾份就量幾份
（``algo/template.roi_boxes_in_patch``）。只取「離缺陷最近的那一份」在
cell 比 patch 小的時候會只量到一根 EPI，其餘的靜靜漏掉。

模板存在 recipe 裡（不是存路徑）
--------------------------------
``template`` 參數存的是**模板本身**（base64 純文字）。存路徑的話，圖被搬走、
被換掉、下個月有人用了另一張大圖，結果會安靜地變 —— 而 recipe 是要交接給別人的
東西，它必須自己就是完整的。

跨 lot 共用是刻意的：同一支 inspection recipe 掃同一塊 scan area，圖案是一樣的。
**換一批資料要不要重算模板**，是 Studio 在設定時提供的健檢，不是每一顆的執行期
行為 —— 它住在這張卡的儀表上（`ui/inspectors.TemplateInspector.health`），
判讀的規則在 `algo/template.judge_template`。它吃的是每一顆都已經吐出來的三個
數字，不再跑一次比對：模板對不上的時候畫面看到的是「每一顆都定不出來」，而那跟
「這批 patch 本來就沒有結構」長得一模一樣 —— 兩者的處置**完全相反**，所以要
分開講。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from ..algo import template as algo_template
from ..pipeline.cellrois import (
    CellRoiError, parse_cell_rois, region_names, regions_repeat_at,
)
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
)
from ._util import (
    PICK_NONE, drop_edge_boxes, drop_edge_specs, output_prefix_spec,
    pick_defect_box, pick_rule_of, pick_rule_specs, prefix_features,
    prefix_names, region_fact_names, region_facts, region_family,
    require_image, set_region_family,
)

#: ``locate_axis`` -> 哪幾軸要做定位。一維的 layout（垂直條紋）只有 X 有相位，
#: 硬要在另一軸上搜尋只會把峰的突出程度稀釋掉，把「定得出來」誤判成「定不出來」。
_AXES = {"x": (True, False), "y": (False, True), "both": (True, True)}

def _prefix_in_section() -> ParamSpec:
    """``output_prefix`` 是共用的那一顆，只差要掛在哪一個小標題底下。"""
    spec = output_prefix_spec("cell")
    spec.section = "4 · Name and limits"
    spec.advanced = True          # 只有同型別的量測卡撞名時才要動它
    return spec


#: 每個區域各自吐的兩個 0/1（前面會加區域名）。
#:
#: ``present``        —— 這一顆有沒有這個區域（模板比 patch 大，某些顆的窗
#:                       就是沒蓋到）。
#: ``others_present`` —— 有沒有**基準**（同一張圖上同材質的另外幾塊）。
#:   只有一份的時候框還在、但沒有東西可以拿來比 —— 那是兩個不同的問題，
#:   一個數字答不了（見 ``_util.set_region_family``）。
#: ``edge_dropped`` —— 因為靠邊被丟掉幾塊（``drop_edge`` 關著就恆為 0）。
#:   這個數字要在，是因為那個開關**會安靜地改變基準的樣本數**：同一份 recipe
#:   在 wafer 中心與邊緣的 defect 上留下的框數不一樣，而 `_others` 的統計本來
#:   就跟樣本數有關。看得到才知道某一顆的基準是不是只剩一塊。
#: **2026-08-18（F11 Region-4）：這一份併進 `_util.REGION_FACTS` 了。**
#: 三張 ROI 卡各寫各的（這裡三個、GDS 四個、Profile 一個都沒有），於是下游得先
#: 知道區域是誰找的才問得出「它在不在這一顆上」。現在每一張都寫同一組五個 ——
#: 而這裡原本那三個名字**一個都沒有消失**：`<n>_present` 與 `<n>_edge_dropped`
#: 照舊，`<n>_others_present` 則是「對 `<n>_others` 這個區域寫 present」自然的
#: 結果（家族的每一個名字都拿得到五件事）。

#: 每個區域固定會有的幾個數字（區域自己的那兩個另外加）。
_MATCH_FEATURES = ["match_score", "match_margin", "match_structure",
                   "phase_x", "phase_y", "pick_by_signal", "locate_ok"]


# ⚠ **這個類別不再自己註冊**（F30，2026-08-25）。使用者：「把 Profile /
# Template 也折進 roi_reference」—— 四張 Region 卡回答的是同一句話（「哪些地方
# 應該長得一樣」），所以它們是一張卡的四個 method，不是四張卡。
#
# 留在這個檔案裡而不是搬進 `roi_reference.py`：把 1100 行演算法搬過去只會讓那
# 個檔案變成 1700 行，而「哪一支怎麼算」本來就各自看得懂 —— 要合的是**使用者
# 看到的那張卡**，不是檔案。`roi_reference` 從這裡取 ``params``（加上一條
# 「method 要是它」的條件）並轉呼叫 ``run`` / ``resolve_*``。
#
# ``key`` 改成 ``roi_reference``：它只剩下「錯誤訊息前面那個名字」這一個用途，
# 而使用者放進畫布的那張卡就叫這個名字。
class RoiTemplateStep(Step):
    """模板定位：把 patch 對回 Golden Cell 的相位，再把標好的框搬過來。"""

    key = "roi_reference"
    label = "Template"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Mark the regions once on one repeating cell of the layout, and "
            "this card puts them in the right place on every image. It works "
            "both ways round: on a small patch, where one cell is bigger than "
            "the patch and you get the one copy this defect can see; and on a "
            "full-size SEM image, where the cell is much smaller and every "
            "copy across the image gets marked.")
    params = [
        ParamSpec(
            name="source", type="image_key", direction="in", default="ref",
            section="1 · Which image",
            label="Match on",
            help=("Which image stream the cell is matched against. With a "
                  "test/ref pair, use ref: it has no defect on it, so nothing "
                  "interferes with the match, and the pair is already aligned "
                  "so the answer applies to test as well. With a single "
                  "full-size image there is only one stream, and the regions "
                  "are repeated across the whole of it."),
        ),
        ParamSpec(
            name="template", type="template", default="",
            section="2 · The repeating cell",
            label="Template",
            help=("The repeating cell this card matches against, stored inside "
                  "the recipe as text so the recipe stays a single file you can "
                  "hand to someone else. Build it from a full-size image in "
                  "Studio - there is nothing useful to type here by hand."),
        ),
        ParamSpec(
            name="locate_axis", type="choice", default="x",
            choices=["x", "y", "both"],
            section="2 · The repeating cell",
            label="Locate across",
            help=("Which direction the layout repeats in. x = vertical stripes "
                  "(the usual case); y = horizontal stripes; both = a cell that "
                  "repeats in two directions. Searching a direction that does "
                  "not repeat only makes the match less certain, and a region's "
                  "position along that direction is not used at all - the boxes "
                  "span the whole patch that way."),
        ),
        ParamSpec(
            name="regions", type="cell_rois", default="",
            section="3 · The regions marked on it",
            label="Regions",
            help=("The regions you marked on the cell, and where each one sits "
                  "on it. A region can be several rectangles - that is how a "
                  "shape like 'the EPI minus where the MG crosses it' is "
                  "expressed. Draw them on the cell in Studio; the positions "
                  "are fractions of one cell, not of the patch."),
        ),
        _prefix_in_section(),
        ParamSpec(
            name="max_boxes", type="int", default=8192, min=1, max=65536,
            section="4 · Name and limits",
            label="At most this many boxes per region",
            help=("A guard for patterns that repeat very finely: one region "
                  "can land thousands of times on a full-size image. The "
                  "boxes nearest the middle are kept, because that is where "
                  "the defect is, and <name>_clipped tells you it happened."),
            advanced=True,
        ),
        *drop_edge_specs("4 · Name and limits"),
        ParamSpec(
            name="min_score", type="float", default=0.3, min=-1.0, max=1.0,
            section="5 · When a defect cannot be located",
            label="Minimum match",
            help=("How well the patch must match the template at all. This is "
                  "brightness-independent, so it does not need retuning when "
                  "the gain changes."),
            advanced=True,
        ),
        ParamSpec(
            name="min_margin", type="float", default=0.0, min=0.0, max=2.0,
            section="5 · When a defect cannot be located",
            label="Minimum certainty",
            help=("How much better the best position must be than the next "
                  "best one. Zero (the default) means it is reported but never "
                  "rejects a defect - on a strongly repeating layout this "
                  "number is small for everyone, so using it as a gate throws "
                  "away good defects. Raise it only when landing on the wrong "
                  "copy would actually change what you measure: that is when "
                  "the regions are NOT the same on every copy, and this card "
                  "already tells you when that is the case."),
            advanced=True,
        ),
        *pick_rule_specs("3 · Where the boxes go"),
        ParamSpec(
            name="min_structure", type="float", default=5.0, min=0.0, max=200.0,
            section="5 · When a defect cannot be located",
            label="Give up below",
            help=("How much structure the patch itself must have. A patch that "
                  "sits entirely inside one material has nothing to match, and "
                  "no threshold on the match score can tell that apart from "
                  "luck - pure noise scores surprisingly well against any "
                  "template. Measured: a featureless patch scores about 1, "
                  "anything with structure scores 20 or more."),
            advanced=True,
        ),
    ]
    reads = ["ref"]
    writes: List[str] = []
    features_out = list(_MATCH_FEATURES)

    # ---- 宣告 ---------------------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        # 判斷訊號的那條流也是一條真的線，而且它會改變框挑到哪一塊 ——
        # 必須進拓撲排序與快取簽章（鐵則 10）。跟 `roi_cross` 一字不差。
        out = [str(params.get("source", "ref"))]
        if str(params.get("pick", "centre")) == "strongest":
            judge = str(params.get("pick_source", "") or "").strip()
            if judge and judge not in out:
                out.append(judge)
        return out

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        """每個區域三個名字：全部、缺陷那一塊、其餘那些。

        跟 ``roi_cross`` 是同一個約定（``_util.region_family`` 是唯一的那一份）
        —— 兩張卡對這件事的說法要一致，使用者只學一次。
        """
        out: List[str] = []
        for name in region_names(params.get("regions", "")):
            out.extend(region_family(name, pick_rule_of(params) != PICK_NONE))
        return out

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        names = list(_MATCH_FEATURES)
        if pick_rule_of(params) == PICK_NONE:
            # ``none`` 沒有「有沒有真的用訊號挑」可言。
            names.remove("pick_by_signal")
        return prefix_names(
            params.get("output_prefix", ""),
            names + region_fact_names(cls.resolve_regions_out(params)))

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """還沒設定完 ≠ 參數填錯。

        空字串是完全合法的值，所以參數檢查沒話說 —— 但這張卡跑起來**每一顆**
        都會失敗。使用者以前要跑過一次才知道，而且那時已經等完 200 顆了。
        """
        out: List[str] = []
        if not str(params.get("template", "") or "").strip():
            out.append("This card has no template yet. Select it and use "
                       "“Edit template & regions…” — a template is an image, "
                       "it cannot be typed in.")
        elif not region_names(params.get("regions", "")):
            out.append("This card has a template but no regions marked on it. "
                       "Select it, open “Edit template & regions…” and draw at "
                       "least one region on the cell.")
        else:
            out.extend(cls._ambiguous_copy_issue(params))
        return out

    @classmethod
    def _ambiguous_copy_issue(cls, params: Dict[str, Any]) -> List[str]:
        """cell 是自己的 k 倍，而兩份上標的東西**不一樣** → 會安靜量錯。

        這是 k× cell 這條路上最後一個安靜出錯的地方（F11 §3.3.7 第 2 項）：
        一顆 patch 分不出自己落在哪一份上，而確定度已經（正確地）不再因此扣分
        —— 所以如果兩份標得不一樣，這一顆有一半機率量到另一份的東西，
        **而畫面上不會有任何錯誤訊息**。

        它是**設定**的性質（模板 × 區域），不是每一顆的執行期行為，所以講在
        這裡，跑之前就看得到。
        """
        decoded = algo_template.decode_template(str(params.get("template", "")))
        if decoded is None:
            return []
        cell, (sx, sy) = decoded
        h, w = cell.shape[:2]
        if (sx, sy) == (w, h) or sx < 1 or sy < 1:
            return []
        try:
            regions = parse_cell_rois(params.get("regions", ""))
        except CellRoiError:
            return []
        if regions_repeat_at(regions, sx / float(w), sy / float(h)):
            return []
        return ["This cell holds %d copies of a %d x %d px repeat, and the "
                "regions are not the same on each copy. A patch cannot tell "
                "which copy it is on, so some defects will be measured on the "
                "wrong one. Either mark the same thing on every copy, or "
                "rebuild the template at the smaller cell size."
                % ((w // sx) * (h // sy), sx, sy)]

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        try:
            regions = parse_cell_rois(p["regions"])
        except CellRoiError as e:                       # pragma: no cover
            raise StepError(self.key, str(e)) from None
        if not regions:
            raise StepError(
                self.key,
                "no regions are marked on the cell yet. Select this card in "
                "Studio and use “Edit template & regions…” — the regions are "
                "drawn on the cell, they cannot be typed in by hand.")

        decoded = algo_template.decode_template(str(p["template"]))
        cell, self_period = decoded if decoded else (None, (0, 0))
        if cell is None or cell.size == 0:
            # 沒有模板不是「跑不出好結果」，是**還沒設定完**。講清楚要去哪裡設，
            # 不要讓使用者對著一個空白參數猜。
            raise StepError(
                self.key,
                "no template yet. Select this card in Studio and use “Edit "
                "template & regions…” — the template cannot be typed in by "
                "hand.")

        img = require_image(ctx, self.key, p["source"])
        axes = _AXES[str(p["locate_axis"])]
        match = algo_template.match_patch(
            cell, img, min_score=float(p["min_score"]),
            min_margin=float(p["min_margin"]),
            min_structure=float(p["min_structure"]), periodic=axes,
            self_period=self_period)

        shape = np.asarray(img).shape[:2]
        ph, pw = int(shape[0]), int(shape[1])
        judge = None
        if str(p["pick"]) == "strongest":
            key = str(p.get("pick_source", "") or "").strip()
            judge = ctx.images.get(key) if key else None
            if judge is None:
                ctx.warn("[%s] nothing is wired into “Judge on”, so the box "
                         "nearest the middle was used instead." % self.key)
        feats: Dict[str, float] = {
            "match_score": float(match.score),
            "match_margin": float(match.margin),
            "match_structure": float(match.structure),
            "phase_x": float(match.phase_x), "phase_y": float(match.phase_y),
            "locate_ok": 1.0 if match.ok else 0.0,
        }
        if pick_rule_of(p) != PICK_NONE:
            # 1 = 「缺陷那一塊」真的是用訊號挑的；0 = 用離正中心最近挑的。
            # 跟 `roi_cross` 的 `cross_pick_by_signal` 是同一件事、同一支函式。
            # ``none`` 之下這一格問的東西不存在，不寫。
            feats["pick_by_signal"] = 1.0 if (str(p["pick"]) == "strongest"
                                              and judge is not None) else 0.0

        edge = float(p["edge_margin"]) if bool(p["drop_edge"]) else 0.0
        for name, norm_boxes in regions:
            boxes, others, dropped, clipped = self._place(
                ctx, name, norm_boxes, match, cell.shape, (ph, pw), axes,
                int(p["max_boxes"]), edge, pick_rule_of(p), judge)
            # 五個數字，跟另外兩張 ROI 卡同一組（`_util.REGION_FACTS`）。
            # 丟掉幾個是**每個區域各自**的數字（區域的形狀不一樣，靠邊的份數
            # 也不一樣），所以要在迴圈裡一個區域一次。
            feats.update(region_facts(
                ctx, region_family(name, pick_rule_of(p) != PICK_NONE),
                (ph, pw), clipped=clipped,
                edge_dropped=dropped,
                # 定不出相位時 `_place` 會退回整張圖當保險 —— 框在，但那不是
                # 這個區域。`present = 0` 而 `boxes = 1`，見 `REGION_FACTS` 的 ⚠。
                located=bool(boxes)))
            # panel 用（跟 roi_cross 同一個慣例）：**UI 畫的就是引擎算的這一份**。
            # UI 自己再算一次很容易變成「畫面上的框」與「真的量下去的框」不一樣，
            # 那種 bug 極難發現。
            ctx.meta.setdefault("templates", {})[name] = {
                "cell_w": int(cell.shape[1]), "cell_h": int(cell.shape[0]),
                "phase_x": int(match.phase_x), "phase_y": int(match.phase_y),
                "score": float(match.score), "margin": float(match.margin),
                "structure": float(match.structure),
                "ok": bool(match.ok), "axis": str(p["locate_axis"]),
                "self_w": int(self_period[0]), "self_h": int(self_period[1]),
                "norm": [[float(v) for v in b] for b in norm_boxes],
                "boxes": [[int(v) for v in b] for b in boxes],
                "others": int(others),
            }

        ctx.add_features(prefix_features(p["output_prefix"], feats))
        return ctx

    # ---- 一個區域 -----------------------------------------------------------
    def _place(self, ctx: Context, name: str,
               norm_boxes: List[Tuple[float, float, float, float]],
               match: Any, cell_shape: Tuple[int, int],
               patch_shape: Tuple[int, int], axes: Tuple[bool, bool],
               max_boxes: int, edge_margin: float = 0.0,
               pick_rule: str = "centre", signal: Any = None
               ) -> Tuple[List[Tuple[int, int, int, int]], int, int, bool]:
        """一個區域的框搬到這張 patch 上，並寫進 ``ctx``。

        回傳 ``(實際放下的框, 其中「其餘」有幾塊, 因為靠邊被丟掉幾塊,
        有沒有被 max_boxes 砍到)``。
        """
        ph, pw = patch_shape
        if not match.ok:
            # 相位定不出來就沒有「哪一格」可言 —— 退回整張圖，並把這一顆標記
            # 起來（``locate_ok`` = 0）。這不是猜一個位置，是明講「這一顆的
            # 區域沒有意義」，下游才有機會把它挑掉。
            ctx.warn(
                "[%s] could not place '%s' on this defect (match %.2f, "
                "certainty %.2f); the region falls back to the whole image and "
                "this defect is marked locate_ok = 0."
                % (self.key, name, match.score, match.margin))
            set_region_family(ctx, self.key, name, [(0.0, 0.0, 1.0, 1.0)],
                              pick=pick_rule != PICK_NONE)
            return [], 0, 0, False

        # **多要一個**（`max_boxes + 1`）。`roi_boxes_in_patch` 自己就會把清單
        # 截到你給的長度，所以照 `max_boxes` 去要的話，回來的永遠正好是
        # `max_boxes` 個 —— 下面那個 `len(boxes) > max_boxes` 於是**永遠是 False**，
        # 而 `<name>_clipped` 就成了一個恆為 0 的旗標。
        # （2026-08-18 寫「大圖也走這張卡」的測試時抓到的：100 份被留成 25 份，
        #  而卡片說沒有被砍。那正是這個旗標存在要擋的那件事本身。）
        # 多要一個就分得出「剛好等於上限」與「其實還有更多」，而清單是照離中心
        # 遠近排序的，所以截掉的仍然是最外圍那些。
        boxes: List[Tuple[int, int, int, int]] = []
        for norm in norm_boxes:
            boxes.extend(algo_template.roi_boxes_in_patch(
                norm, match, cell_shape, patch_shape, periodic=axes,
                max_boxes=max_boxes + 1))
        # 一個區域的每一塊各自鋪出去之後總數才封頂 —— 留中間的那些（缺陷在
        # 正中央，同 ``roi_cross`` 的 max_boxes）。
        clipped = len(boxes) > max_boxes
        if clipped:
            cx, cy = pw / 2.0, ph / 2.0
            boxes.sort(key=lambda b: ((b[0] + b[2] / 2.0 - cx) ** 2
                                      + (b[1] + b[3] / 2.0 - cy) ** 2))
            boxes = boxes[:max_boxes]

        if not boxes:
            # 模板比 patch 大的時候這是**正常**的：這一顆的窗剛好沒蓋到這個
            # 區域。不要退回整張圖 —— 那會安靜地量到全部的像素，而那是錯的。
            # 講出來、記進 ``regions_absent``，量測卡才報得出真正的原因。
            ctx.warn("[%s] region '%s' does not land on this defect (the "
                     "template is larger than the patch, so this patch only "
                     "sees part of the cell); nothing is measured in it here."
                     % (self.key, name))
            absent_names = ([name, "%s_others" % name]
                            if pick_rule != PICK_NONE
                            else [name])
            for absent in absent_names:
                ctx.meta.setdefault("regions_absent", {})[absent] = (
                    "it is marked on a part of the cell that this patch does "
                    "not cover")
            return [], 0, 0, clipped

        if pick_rule == PICK_NONE:
            # **這裡短路**：`pick_defect_box` 對不認得的 rule 會安靜退回
            # 「離中心最近」。-1 = `drop_edge_boxes` 的「沒有受保護的框」。
            idx, by_signal = -1, False
        else:
            idx, by_signal = pick_defect_box(boxes, (ph, pw), pick_rule,
                                             signal)
            ctx.meta.setdefault("pick_by_signal", {})[name] = bool(by_signal)
        # 靠邊的丟掉 —— **在挑出中心那一塊之後**。順序反過來的話，中心會從
        # 「離缺陷最近的那一塊」變成「留下來的裡面離缺陷最近的那一塊」，
        # 而那兩者在缺陷靠近 patch 邊緣時不是同一塊。
        dropped = 0
        if edge_margin > 0.0:
            boxes, dropped, idx = drop_edge_boxes(boxes, (ph, pw),
                                                  edge_margin, idx)
        others = set_region_family(
            ctx, self.key, name,
            [(x / pw, y / ph, w / pw, h / ph) for x, y, w, h in boxes], idx,
            dropped, pick=pick_rule != PICK_NONE)
        return boxes, others, dropped, clipped

