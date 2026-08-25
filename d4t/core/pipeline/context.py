# d4t pipeline contract — authored 2026-07-27 (M1).
"""Context — pipeline 步驟間傳遞的執行狀態。

設計原則（見 docs/plans/F0-master-plan.md §3.2）：
- ``images``   命名影像流（"test"、"ref"、"ref_aligned"、"diff"、"snr_map"…）。
- ``rois``     MultiROISet（正規化座標；M3 起由 ROI 卡填入）。
- ``labels``   整數 ROI label map（0=背景, 1..N；GLAS 契約 gray[labels==k]）。
- ``features`` 扁平特徵區 —— **score 表達式的唯一變數空間**。
  任何卡塞進來的數字（CD、SNR、GLV、focus…）一視同仁。
- ``meta``     診斷與雜項（nm_per_px、對位 dx/dy、fallback_reason…）。

慣例：
- Step 對同名影像流做 in-place 覆寫（linear 鏈的預設行為）；要保留舊圖就寫新 key。
- feature 覆寫允許，但會記錄在 ``meta["feature_overwrites"]`` 供 lint/UI 提示。
- 引擎在執行前會把當前 DefectItem 放進 ``meta["_defect_item"]``、Dataset kind 放進
  ``meta["_dataset_kind"]``（Load 卡讀這兩個 key）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


#: ``meta`` 裡放「每個特徵是哪張卡產出的」的鍵。
#:
#: 放在 meta 而不是 :class:`~d4t.core.pipeline.engine.DefectResult` 的新欄位，
#: 是為了**不動序列化** —— `store/results.py` 的資料表、CSV 的欄位、KLARF 寫回
#: 全部吃的是扁平的 ``features`` dict。
FEATURE_OWNER_KEY = "feature_owner"


class ContextError(RuntimeError):
    """步驟向 Context 要不存在的資源時拋出（訊息需列出現有 keys）。"""


@dataclass
class Context:
    images: Dict[str, np.ndarray] = field(default_factory=dict)
    rois: Optional[Any] = None            # d4t.core.algo.roi.MultiROISet
    labels: Optional[np.ndarray] = None
    features: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    #: 現在正在跑的是哪一張卡（引擎每跑一張之前設好；F17-②）。
    #:
    #: **特徵的擁有者是在寫進來的當下記下的，不是事後推的。** 以前引擎是比對
    #: 每張卡跑前跑後的 ``features`` dict 差異，再回推「這張卡產出了什麼」——
    #: 而那份差異在「後面那張卡剛好算出一樣的值」時是空的（F9-3 踩過，見
    #: `docs/PITFALLS.md` 的「把『要不要記錄』跟『值有沒有變』綁在一起」）。
    #: 寫入當下就記，那個巧合就不存在了。
    current_node: str = ""

    #: 記錄「這一步把某條影像流改成什麼樣」（F7-17，**預設關閉**）。
    #:
    #: Enhance 卡是就地改寫同一條流的（``test → test``），所以跑完之後「之前
    #: 長什麼樣」就沒了 —— 而那正是使用者最需要看的：對比拉大之後背景被壓成
    #: 全黑、缺陷的邊界也一起被吃掉，畫面上只會覺得「變乾淨了」。
    #:
    #: 只在**預覽**（單顆）打開。批次跑一萬顆時每一次 set_image 都算兩個直方圖
    #: 是白花的力氣 —— 那份資料沒有人看。
    track_changes: bool = False

    # ---- images -----------------------------------------------------------
    def require_image(self, key: str) -> np.ndarray:
        try:
            return self.images[key]
        except KeyError:
            raise ContextError(
                f"image stream '{key}' does not exist; available: "
                f"{sorted(self.images)}"
            ) from None

    def set_image(self, key: str, arr: np.ndarray) -> None:
        if not isinstance(arr, np.ndarray):
            raise ContextError(f"set_image('{key}') needs a numpy array, got "
                               f"{type(arr).__name__}")
        if self.track_changes and key in self.images:
            # 覆寫既有的流 = 有人在改它。記下改之前與改之後的樣子。
            self._record_change(key, self.images[key], arr)
        self.images[key] = arr

    #: 記錄用的直方圖分幾格。夠看出「壓平了」「削掉了」，又不會讓 meta 變肥。
    HIST_BINS = 48

    def _record_change(self, key: str, before: np.ndarray,
                       after: np.ndarray) -> None:
        """把一次覆寫壓成兩個直方圖 + 削平計數，放進 ``meta['stream_change']``。

        存的是**摘要不是影像** —— 存兩張圖會讓每顆 defect 的 meta 變成幾百 KB，
        而使用者要回答的問題（「我把資訊弄掉了嗎」）用直方圖就答得出來。
        """
        try:
            rec = {
                "before": _hist(before, self.HIST_BINS),
                "after": _hist(after, self.HIST_BINS),
                "clipped_low": _clipped(after, low=True),
                "clipped_high": _clipped(after, low=False),
                "was_clipped_low": _clipped(before, low=True),
                "was_clipped_high": _clipped(before, low=False),
            }
        except Exception:               # noqa: BLE001 — 記錄失敗不准影響執行
            return
        self.meta.setdefault("stream_change", {})[str(key)] = rec

    # ---- ROI（F7-4）--------------------------------------------------------
    #
    # ``rois`` 是 ``algo.roi.MultiROISet``（vendoring 自 Fusi³，正規化座標）。
    # 那個類別是為「ROI 編輯器」設計的（有 id / target / reference / 顏色），
    # d4t 要的其實只是「用**名字**取一個框」，所以在這裡包一層以名字為鍵的
    # API，底層仍然用 MultiROISet 的 ``label`` 當名字 —— 不另外發明資料結構。
    #
    # 座標一律是正規化的 (nx, ny, nw, nh)，理由見 docs/plans/F7 §4：
    # patch 是以 defect 為中心裁切的，同一份 recipe 換一個 patch 尺寸時，
    # 用比例定義的框才會落在同一個地方（像素值會失效）。

    def set_roi(self, name: str, norm_rect: Any) -> None:
        """以名字寫入一個 ROI（同名覆寫）。``norm_rect`` = (nx, ny, nw, nh)。"""
        from ..algo.roi import MultiROISet

        name = str(name)
        rect = tuple(float(v) for v in norm_rect)
        if len(rect) != 4:
            raise ContextError(
                f"set_roi('{name}') needs (nx, ny, nw, nh), got {norm_rect!r}")
        if self.rois is None:
            self.rois = MultiROISet()
        for roi in list(self.rois.rois):
            if roi.label == name:
                self.rois.remove_roi(roi.id)
        self.rois.add_roi(rect, label=name)

    def set_roi_boxes(self, name: str, norm_rects: Any) -> None:
        """一個名字對應**好幾個**框（同名覆寫；F8）。

        為什麼一個名字可以有多個框
        --------------------------
        「MG 與 EPI 的交界」在一張 patch 上不只一處 —— 好幾根直線乘上好幾根
        橫線，交會處自然是分散的好幾塊，而且**數量隨影像而異**（換一顆
        defect、換一個 patch 尺寸就不一樣）。若讓卡片吐 ``cross_0`` …
        ``cross_n``，recipe 就得寫死一個數量，而那個數量根本不存在。

        所以「區域」升級成「一個名字 + 一組框」。單框只是 N=1 的情形，
        既有的 ``set_roi`` 與所有量測卡完全不受影響。
        """
        from ..algo.roi import MultiROISet

        name = str(name)
        rects = [tuple(float(v) for v in r) for r in (norm_rects or ())]
        for rect in rects:
            if len(rect) != 4:
                raise ContextError(
                    f"set_roi_boxes('{name}') needs (nx, ny, nw, nh) per box, "
                    f"got {rect!r}")
        if self.rois is None:
            self.rois = MultiROISet()
        for roi in list(self.rois.rois):
            if roi.label == name:
                self.rois.remove_roi(roi.id)
        for rect in rects:
            self.rois.add_roi(rect, label=name)

    def roi_names(self) -> List[str]:
        """目前定義了哪些 ROI 名字（依加入順序，**不重複**）。

        多框區域底下是好幾個同 label 的 ROI，但對使用者與 lint 來說那是
        **一個**名字 —— 列成 ``['cross', 'cross', 'cross']`` 的訊息只會讓人
        以為自己接錯了什麼。
        """
        if self.rois is None:
            return []
        out: List[str] = []
        for roi in self.rois.rois:
            if roi.label not in out:
                out.append(roi.label)
        return out

    def roi_count(self, name: str) -> int:
        """這個名字底下有幾個框（0 = 沒定義）。"""
        name = str(name)
        if self.rois is None:
            return 0
        return sum(1 for roi in self.rois.rois if roi.label == name)

    def roi_norm_rects(self, name: str) -> List[Any]:
        """以名字取**所有**正規化矩形 ``[(nx, ny, nw, nh), …]``（不需要影像尺寸）。

        畫框的地方要用這個而不是 ``require_roi(...).norm_rect`` —— 後者只回
        第一個，於是多框區域在畫面上會少掉其餘每一塊。那不只是漏畫：
        使用者看到一個框、實際上量的是八個，**而畫面上沒有任何東西透露這件事**。
        """
        name = str(name)
        if self.rois is None:
            return []
        return [roi.norm_rect for roi in self.rois.rois if roi.label == name]

    def roi_rects(self, name: str, shape: Any) -> List[Any]:
        """以名字取**所有**像素矩形 ``[(x, y, w, h), …]``。"""
        name = str(name)
        self.require_roi(name)          # 不存在時給的是帶說明的錯誤
        hw = tuple(shape)[:2]
        return [roi.to_pixel_rect(hw)
                for roi in self.rois.rois if roi.label == name]

    def require_roi(self, name: str) -> Any:
        """以名字取一個 ``NamedROI``；不存在時拋帶說明的 ContextError。"""
        name = str(name)
        for roi in (self.rois.rois if self.rois is not None else ()):
            if roi.label == name:
                return roi
        raise ContextError(
            f"ROI '{name}' is not defined; available: {self.roi_names()}. "
            f"Add an ROI card upstream, or leave the roi parameter empty "
            f"to use the whole image.")

    def roi_rect(self, name: str, shape: Any) -> Any:
        """以名字取像素矩形 ``(x, y, w, h)``，套用到 ``shape``=(H, W) 的影像。"""
        return self.require_roi(name).to_pixel_rect(tuple(shape)[:2])

    # ---- features ---------------------------------------------------------
    def add_feature(self, name: str, value: Any) -> None:
        """寫入一個特徵值（強制轉 float；NaN/inf 允許，由表達式層做安全處理）。

        **順便記下擁有者**（F17-②）：``current_node`` 是引擎在跑這張卡之前設好
        的，所以「這個數字是誰算的」是**寫入當下的事實**，不是事後從 dict 的
        差異回推出來的。
        """
        v = float(value)
        if name in self.features:
            self.meta.setdefault("feature_overwrites", []).append(name)
        self.features[name] = v
        if self.current_node:
            self.meta.setdefault(FEATURE_OWNER_KEY, {})[name] = self.current_node

    def add_features(self, mapping: Dict[str, Any]) -> None:
        for k, v in mapping.items():
            self.add_feature(k, v)

    # ---- misc -------------------------------------------------------------
    @property
    def nm_per_px(self) -> Optional[float]:
        return self.meta.get("nm_per_px")

    def stream_nm_per_px(self, key: str) -> Optional[float]:
        """**這一條流**的 nm/px（2026-08-20）。不知道就回 None。

        為什麼不是一個全域數字：一份 pipeline 可以同時吃兩份資料（F15 的第二
        份 lot），而兩台機台的像素大小不一樣 —— 那正是 `align_to` 要縮放才對得
        起來的原因。所以數字掛在**流**上，由把那條流吐出來的那張卡填。

        沒有登記過就退回全域那個（`meta["nm_per_px"]`，主 lot 的 Load 卡填的）
        —— 只有一份資料的時候兩者本來就一樣。
        """
        table = self.meta.get("stream_nm_per_px") or {}
        value = table.get(str(key))
        return self.nm_per_px if value is None else float(value)

    def set_stream_nm_per_px(self, key: str, value: Optional[float]) -> None:
        """登記某一條流的 nm/px（0／None = 不知道，不登記）。"""
        try:
            v = float(value or 0.0)
        except (TypeError, ValueError):
            return
        if v > 0:
            self.meta.setdefault("stream_nm_per_px", {})[str(key)] = v

    def warn(self, msg: str) -> None:
        self.meta.setdefault("warnings", []).append(str(msg))

    def summary(self) -> Dict[str, Any]:
        """輕量摘要（不含像素資料），供 trace / debug 輸出。"""
        return {
            "images": {k: tuple(v.shape) for k, v in self.images.items()},
            "features": dict(self.features),
            "warnings": list(self.meta.get("warnings", [])),
        }


# --------------------------------------------------------------------------- #
# 影像流變動的摘要（F7-17）—— 純函式，UI 與測試都可以直接用
# --------------------------------------------------------------------------- #
def _finite(arr: "np.ndarray") -> "np.ndarray":
    a = np.asarray(arr)
    if a.dtype.kind == "f":
        a = a[np.isfinite(a)]
    return a.reshape(-1)


def _hist(arr: "np.ndarray", bins: int) -> List[int]:
    """灰階分布。**固定用 0–255 的刻度**，不用每張圖自己的 min–max ——
    比較 before / after 的前提是兩者在同一把尺上，各自拉伸就沒得比了。

    float 影像（diff / snr_map 這類）本來就不在 0–255，那時候退回兩者的
    共同範圍；退回的判斷放在呼叫端之外，這裡只負責照給定範圍分格。
    """
    a = _finite(arr)
    if a.size == 0:
        return [0] * int(bins)
    lo, hi = 0.0, 255.0
    if a.dtype.kind == "f" and (float(a.min()) < -1.0 or float(a.max()) > 256.0):
        lo, hi = float(a.min()), float(a.max())
        if hi <= lo:
            hi = lo + 1.0
    idx = np.clip(((a.astype(np.float64) - lo) / (hi - lo) * bins).astype(int),
                  0, int(bins) - 1)
    return np.bincount(idx, minlength=int(bins)).astype(int).tolist()


def _clipped(arr: "np.ndarray", low: bool) -> float:
    """貼在 0（或 255）的畫素佔多少比例。

    削平是 Enhance **唯一**會安靜毀掉資訊的方式：那些畫素的差異永遠回不來了，
    而畫面上只會覺得「對比變好了」。
    """
    a = _finite(arr)
    if a.size == 0:
        return 0.0
    hit = (a <= 0.5) if low else (a >= 254.5)
    return float(np.count_nonzero(hit)) / float(a.size)


# --------------------------------------------------------------------------- #
# 跨顆那一層（F16）
# --------------------------------------------------------------------------- #
@dataclass
class BatchContext:
    """一張**跨顆卡**看得到的東西：整批跑完之後的結果表。

    為什麼需要一個新的 Context
    --------------------------
    :class:`Context` 是**一顆** defect 的（images / rois / features），而
    ``run_defect`` 一顆一顆跑、從不 raise（鐵則 7）。所以任何「要看過整批才算
    得出來」的東西現在都沒有地方放，而那不是一個需求，是四個：

    * Output 的 CSV / KLARF / Report / HTML（一批一個檔案）
    * 離群旗標（Tukey IQR、z-score —— 門檻由整批的分布決定）
    * F15 欠的那份點對點 report（一顆一列的表 ＋ 整批的分布）
    * ``H2H`` 的 ``expect_dx_px`` 建議值（整批取中位數）

    先做機制，四個都便宜；不做機制，四個各自發明一套。

    欄位
    ----
    ``rows``
        每一顆的結果 dict（``result_to_json_dict`` 的產物：``defect_id`` /
        ``ok`` / ``error`` / ``score`` / ``bin`` / ``features``）。**這就是
        報表與寫回吃的東西**，所以跨顆卡拿到的跟 `core/export/` 要的一模一樣。
    ``dataset``
        原始資料集。``output_klarf`` 要它的 ``.klarf``（KlarfDoc）——
        那份東西刻意不進 worker，而跨顆那一層跑在主行程，所以拿得到。
    ``outputs``
        寫出去的檔案路徑（給 UI 與 CLI 報告「這一次產出了什麼」）。
    ``errors``
        ``{節點 id: 訊息}`` —— **鐵則 7 的跨顆版**：一張跨顆卡出錯只記在這裡，
        其他卡照跑，而整批的結果仍然拿得到。
    """

    rows: List[Dict[str, Any]] = field(default_factory=list)
    dataset: Any = None
    recipe: Any = None
    kind: str = ""
    outputs: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)
    #: 影像段的快取與「這是哪一份資料」（F29 C4）—— 出圖那幾張卡要重跑一次
    #: pipeline 才拿得到像素，而那一趟的影像段跟剛才那一批逐位元組相同。
    #: ``None`` = 沒有快取可用（照 `run_defect` 全程重算，結果一模一樣）。
    #: 走 :meth:`rerun` 而不是自己叫 —— 那一格 `None` 檢查漏在任何一張卡上，
    #: 症狀都是「報表慢了十倍」而不是一個錯誤。
    cache: Any = None
    dataset_token: str = ""

    def rerun(self, item: Any, sources: Optional[Dict[str, Any]] = None):
        """重跑**一顆**，拿回它的 Context（出圖那幾張卡走這一支）。

        有快取就走 `engine.run_defect_cached`（影像段命中，只跑算法段），
        沒有就 `engine.run_defect` —— **兩條路的 features / score / bin
        位元級一致**（那是 `run_defect_cached` 的合約）。
        """
        from .engine import run_defect, run_defect_cached

        if self.cache is not None:
            return run_defect_cached(self.recipe, item, self.kind, self.cache,
                                     self.dataset_token, keep_context=True,
                                     sources=sources)
        return run_defect(self.recipe, item, self.kind, keep_context=True,
                          sources=sources)

    def add_output(self, path: Any) -> None:
        """記下一個寫出去的檔案（同一個路徑只記一次）。"""
        s = str(path)
        if s and s not in self.outputs:
            self.outputs.append(s)

    def warn(self, msg: str) -> None:
        self.warnings.append(str(msg))

    @property
    def ok_rows(self) -> List[Dict[str, Any]]:
        """只有跑成功的那幾顆。

        失敗的那幾顆**留在 ``rows`` 裡**（報表要看得到它們失敗了，那是
        `write_csv` 的 ``error`` 欄），所以這是一個**選配**的視角，不是預設。
        """
        return [r for r in self.rows if r.get("ok")]
