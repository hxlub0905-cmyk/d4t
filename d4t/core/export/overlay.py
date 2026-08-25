# d4t overlay rendering — authored 2026-07-28 (M5-1).
"""缺陷疊圖：把「機器看到什麼」畫成一張人看得懂的圖。

純 numpy/cv2，**不碰檔案**（除了 :func:`write_png`）—— 這樣 Studio 的
Gallery、CLI 的批次出圖、報表的插圖都能共用同一支渲染函式。

:func:`render_overlay` 產出 RGB uint8 面板：

- 底圖取 ``images["test"]``（EBI patch）或 ``images["single"]``（rSEM）；
- 主 blob 的 bounding box 畫**紅框**；
- 左上角可疊一行標籤（score / bin …），底下鋪半透明深色條方便閱讀；
- ``images`` 裡有 ``"diff"`` 時輸出 **[test | diff] 並排**（寬度剛好兩倍）。

★ 字型限制 ★
  cv2 內建的 Hershey 字型**沒有中日韓字元**。標籤裡的非 ASCII 字元會被
  換成 ``?`` 再畫（不會炸、不會亂碼）。要中文標籤請在 UI 層用 Qt 畫。

批次執行時 Context 不會保留（記憶體會爆），所以這裡**不提供**
``save_overlays(results_with_ctx, ...)``；改由呼叫端逐顆
``render_overlay`` → :func:`write_png`，要畫哪幾顆由 UI/CLI 決定。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Sequence, Tuple

import cv2
import numpy as np

from .klarf_out import ExportError

__all__ = ["render_overlay", "write_png", "to_display_rgb",
           "primary_blob_box", "pick_overlay_results", "overlay_label",
           "overlay_filename", "OVERLAY_PREFIX", "BOX_COLOR"]

#: 疊圖 PNG 的檔名前綴。**留著**是因為使用者常常把疊圖寫進一個已經有東西的
#: 資料夾裡 —— 前綴讓「這批是這一次跑出來的」一眼看得出來，也讓刪掉它們是
#: 一個 glob 而不是逐個檔案挑。
OVERLAY_PREFIX = "overlay_"

#: 主 blob 外框的顏色（RGB）。
BOX_COLOR = (255, 32, 32)
#: 標籤文字顏色（RGB）與底條顏色。
TEXT_COLOR = (255, 255, 255)
BANNER_COLOR = (0, 0, 0)

#: 底圖的挑選順序（第一個找得到的就用）。
BASE_PRIORITY = ("test", "single", "aligned", "ref", "diff")

_FONT = cv2.FONT_HERSHEY_SIMPLEX


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _ascii_only(text: str) -> str:
    """非 ASCII → '?'（cv2 的內建字型畫不出 CJK，但也不該讓它炸）。"""
    return "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(text))


def to_display_rgb(arr: np.ndarray) -> np.ndarray:
    """任意 2-D/3-D 陣列 → 可顯示的 RGB uint8（float 圖自動拉伸到 0–255）。"""
    a = np.asarray(arr)
    if a.ndim == 3 and a.shape[2] == 1:
        a = a[:, :, 0]
    if a.ndim not in (2, 3):
        raise ExportError(
            "Overlays accept a 2-D grayscale or 3-channel colour image only; got shape {}.".format(a.shape))
    if a.ndim == 3 and a.shape[2] not in (3, 4):
        raise ExportError(
            "Overlays accept 3- or 4-channel colour images only; got {} channels.".format(a.shape[2]))

    if a.dtype != np.uint8:
        f = a.astype(np.float32)
        lo = float(np.nanmin(f)) if f.size else 0.0
        hi = float(np.nanmax(f)) if f.size else 1.0
        f = np.nan_to_num(f, nan=lo, posinf=hi, neginf=lo)
        if hi - lo < 1e-12:
            a = np.zeros(f.shape, np.uint8)
        else:
            # 四捨五入（不是無條件捨去）：最大值才會剛好落在 255
            a = np.clip(np.rint((f - lo) * (255.0 / (hi - lo))),
                        0, 255).astype(np.uint8)

    if a.ndim == 2:
        return cv2.cvtColor(a, cv2.COLOR_GRAY2RGB)
    if a.shape[2] == 4:
        return cv2.cvtColor(a, cv2.COLOR_RGBA2RGB)
    return np.ascontiguousarray(a)


def _blob_box(b: Any) -> Optional[Tuple[int, int, int, int]]:
    """blob（dict 或 DefectROI）→ (x, y, w, h)。"""
    if b is None:
        return None
    if isinstance(b, dict):
        if not all(k in b for k in ("x", "y", "w", "h")):
            return None
        vals = (b["x"], b["y"], b["w"], b["h"])
    elif hasattr(b, "bbox"):
        vals = tuple(b.bbox)
    elif all(hasattr(b, k) for k in ("x", "y", "w", "h")):
        vals = (b.x, b.y, b.w, b.h)
    elif isinstance(b, (tuple, list)) and len(b) >= 4:
        vals = tuple(b[:4])
    else:
        return None
    try:
        return (int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3]))
    except (TypeError, ValueError):
        return None


def _blob_rank(b: Any) -> float:
    """主 blob 的挑選依據：SNR 最強者；沒有 SNR 就用面積。"""
    if isinstance(b, dict):
        v = b.get("snr_value", b.get("area", 0.0))
    else:
        v = getattr(b, "snr_value", getattr(b, "area", 0.0))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


#: 特徵裡「一個框」長什麼名字 —— **順序就是優先順序**（F29）。
#:
#: * ``blob_*`` —— `find_defect` **去圖上找**出來的那一團；
#: * ``cd_box_*`` —— CD 卡量那一塊的時候**順手知道**的位置。
#:
#: 先找的贏，理由是它回答的問題比較接近疊圖要問的那一句：「這張圖上最可疑的
#: 東西在哪」。CD 的框是「使用者用線指給我的那一塊裡面，那一團在哪」——
#: 一樣有用，但它已經預設了範圍。兩個都在的時候畫兩個框才是誠實的做法，
#: 而那要等疊圖畫得下第二個框（今天 `render_overlay` 只吃一個 ``box``）。
_BOX_FEATURE_SETS = (
    ("blob_x", "blob_y", "blob_w", "blob_h"),
    ("cd_box_x", "cd_box_y", "cd_box_w", "cd_box_h"),
)


def primary_blob_box(blobs: Optional[Sequence[Any]] = None,
                     features: Optional[Dict[str, Any]] = None
                     ) -> Optional[Tuple[int, int, int, int]]:
    """挑出「主 blob」的框：blobs 裡 SNR 最強的那塊；

    blobs 是空的時候，退而求其次看 features 裡有沒有一組框 ——
    順序見 :data:`_BOX_FEATURE_SETS`。都沒有回 None。

    ⚠ **只認沒有前綴的那一份。** 量測卡接了兩個以上的區域時，名字會變成
    ``epi_cd_box_x`` / ``mg_cd_box_x`` —— 那時候「主 blob」有兩個答案，
    而在兩個裡面挑一個畫出來、畫面上又不說是哪一個，正是這個 repo 最怕的
    「跑得完、有圖、而且是錯的」。所以那種情況下不畫框（回 None），
    等疊圖畫得下好幾個框再說。
    """
    best = None
    best_rank = None
    for b in (blobs or ()):
        box = _blob_box(b)
        if box is None:
            continue
        rank = _blob_rank(b)
        if best_rank is None or rank > best_rank:
            best, best_rank = box, rank
    if best is not None:
        return best
    f = features or {}
    for keys in _BOX_FEATURE_SETS:
        if all(k in f for k in keys):
            return _blob_box(dict(zip(("x", "y", "w", "h"),
                                      (f[k] for k in keys))))
    return None



def overlay_filename(defect_id: Any) -> str:
    """defect id → 疊圖的檔名（``overlay_<id>.png``）。

    **會把不能當檔名的字換成底線**：RSEM 那條路的 id 是從檔名來的，而
    `output_image` 第一版直接把它拼進路徑 —— 一顆 id 裡有 ``/`` 或 ``:``
    的 defect 會讓那張卡整個失敗，而症狀是「少了幾張 PNG」（鐵則 7 把例外
    吃掉了）。跟 :func:`overlay_label` 一樣是從 Export 精靈搬過來的。
    """
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_"
                   for ch in str(defect_id)) or "unknown"
    return "%s%s.png" % (OVERLAY_PREFIX, safe)


def overlay_label(result: Dict[str, Any]) -> str:
    """疊圖左上角那一行：``#3  score=4.210  bin=1``。

    **住在這裡而不是 UI**（F16 Stage 5c 搬過來的，同 :func:`pick_overlay_results`）：
    它問的是「這張圖上要寫哪一行字」——跟畫面無關，而 `output_image` 跟 Export
    精靈要的是同一行。以前它在 `ui/export_dialog.py` 裡，於是那張卡只寫得出
    defect id：**一疊 PNG 上少了分數與 bin，看起來跟完整的一模一樣**，
    而那正是使用者拿它們來挑門檻的理由。

    cv2 的內建字型沒有 CJK，所以這裡刻意只用 ASCII。
    """
    parts = ["#%s" % result.get("defect_id", "?")]
    s = result.get("score")
    if s is not None:
        try:
            parts.append("score=%.3f" % float(s))
        except (TypeError, ValueError):
            pass
    b = result.get("bin")
    if b is not None:
        parts.append("bin=%d" % int(b))
    return "  ".join(parts)


def pick_overlay_results(results: Sequence[Dict[str, Any]], limit: int
                         ) -> List[Dict[str, Any]]:
    """依分數由高到低取前 ``limit`` 顆（沒有分數的排最後）。

    **住在這裡而不是 UI**（F16 Stage 5c 搬過來的）：它問的是「這一批裡最值得
    看的是哪幾顆」——跟畫面無關，而 `output_image` 跟 Export 精靈要的是同一個
    答案。以前它在 `ui/export_dialog.py` 裡，於是那張卡照 `rows` 的順序取前 N
    —— **檔案順序上的前 N 顆幾乎一定不是使用者想看的那幾顆**，而畫面上看不出
    差別（都是 N 張 PNG）。

    ``limit`` 是 0（或負的）＝ 全部，不截斷。
    """
    rows = [r for r in (results or []) if r.get("ok", True)] or list(results or [])

    def key(r: Dict[str, Any]) -> Tuple[int, float]:
        s = r.get("score")
        try:
            return (0, -float(s))
        except (TypeError, ValueError):
            return (1, 0.0)

    rows = sorted(rows, key=key)
    n = max(0, int(limit))
    return rows[:n] if n else rows


def _pick_base(images: Dict[str, Any]) -> Tuple[str, np.ndarray]:
    for k in BASE_PRIORITY:
        if k in images and images[k] is not None:
            return k, images[k]
    for k in sorted(images):
        if images[k] is not None:
            return k, images[k]
    raise ExportError(
        "This defect has no image to draw (images is empty). Check that the "
        "load card in the pipeline ran successfully.")


def _draw_box(panel: np.ndarray, box: Tuple[int, int, int, int],
              color: Tuple[int, int, int] = BOX_COLOR) -> None:
    """在 panel 上畫框（超出邊界會被裁到圖內，至少留 1 px 寬高）。"""
    h, w = panel.shape[:2]
    x, y, bw, bh = box
    x0 = max(0, min(int(x), w - 1))
    y0 = max(0, min(int(y), h - 1))
    x1 = max(x0, min(int(x) + max(1, int(bw)) - 1, w - 1))
    y1 = max(y0, min(int(y) + max(1, int(bh)) - 1, h - 1))
    thick = 1 if min(h, w) < 192 else 2
    cv2.rectangle(panel, (x0, y0), (x1, y1), tuple(int(c) for c in color), thick)


def _draw_label(panel: np.ndarray, label: str) -> None:
    """左上角一行標籤（深色底條 + 白字）。非 ASCII 會變成 '?'。"""
    text = _ascii_only(label).strip()
    if not text:
        return
    h, w = panel.shape[:2]
    scale = max(0.35, min(0.6, w / 320.0))
    thick = 1
    (tw, th), base = cv2.getTextSize(text, _FONT, scale, thick)
    pad = 3
    bh = min(h, th + base + 2 * pad)
    band = panel[0:bh, 0:min(w, tw + 2 * pad)]
    if band.size:
        band[:] = (band.astype(np.uint16) * 1 // 4).astype(np.uint8)  # 壓暗當底
    cv2.putText(panel, text, (pad, pad + th), _FONT, scale,
                tuple(int(c) for c in TEXT_COLOR), thick, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# 主函式
# ---------------------------------------------------------------------------
def render_overlay(images: Dict[str, Any],
                   features: Optional[Dict[str, Any]] = None, *,
                   blobs: Optional[Sequence[Any]] = None,
                   box: Optional[Sequence[int]] = None,
                   label: Optional[str] = None,
                   base_key: Optional[str] = None,
                   diff_key: str = "diff",
                   montage: bool = True) -> np.ndarray:
    """把一顆 defect 畫成 RGB uint8 面板。

    參數
    ----
    images
        Context 的影像 dict（或其子集）。底圖依 ``test`` → ``single`` →
        ``aligned`` → ``ref`` → ``diff`` 的順序挑第一個找得到的；
        ``base_key`` 可以指定。
    features
        該顆的特徵 dict。兩個用途：(1) ``box`` 與 ``blobs`` 都沒給時，
        若含 ``blob_x/blob_y/blob_w/blob_h`` 就用它畫框；(2) ``label``
        沒給但含 ``score`` 時自動組出 ``score=…`` 標籤。
    blobs
        ``ctx.meta["blobs"]``（dict 清單）或 ``DefectROI`` 清單；
        取 SNR 最強的那塊畫紅框。
    box
        直接指定 ``(x, y, w, h)``，優先於 ``blobs`` / ``features``。
    label
        左上角文字（非 ASCII 會顯示成 ``?``，見模組 docstring）。
    montage
        ``images`` 有 ``diff`` 時是否輸出 **[底圖 | diff] 並排**
        （預設 True，寬度剛好是底圖的兩倍）。

    回傳 ``(H, W, 3)`` 或 ``(H, 2W, 3)`` 的 uint8 RGB 陣列。
    """
    if not isinstance(images, dict) or not images:
        raise ExportError(
            "render_overlay needs a dict of images (e.g. ctx.images); it got an empty one.")
    features = dict(features or {})

    if base_key is not None:
        if base_key not in images or images[base_key] is None:
            raise ExportError(
                "The requested base image stream \"{}\" does not exist; this defect has: {}.".format(
                    base_key, ", ".join(sorted(images))))
        base = images[base_key]
    else:
        base_key, base = _pick_base(images)

    left = to_display_rgb(base)
    h, w = left.shape[:2]

    the_box = _blob_box(box) if box is not None else primary_blob_box(blobs, features)
    if the_box is not None:
        _draw_box(left, the_box)

    panel = left
    right_src = images.get(diff_key)
    if montage and diff_key != base_key and right_src is not None:
        right = to_display_rgb(right_src)
        if right.shape[:2] != (h, w):
            right = cv2.resize(right, (w, h), interpolation=cv2.INTER_NEAREST)
        if the_box is not None:
            _draw_box(right, the_box)
        panel = np.concatenate([left, right], axis=1)
        panel[:, w:w + 1] = 96          # 中間一條細分隔線（不改變總寬度）

    if label is None:
        s = features.get("score")
        if s is not None:
            try:
                label = "score={:.3f}".format(float(s))
            except (TypeError, ValueError):
                label = None
    if label:
        _draw_label(panel, str(label))

    return np.ascontiguousarray(panel.astype(np.uint8))


def write_png(arr: np.ndarray, path: str) -> str:
    """把疊圖存成 PNG —— atomic（``.tmp`` + :func:`os.replace`）、CJK 路徑安全。

    走 ``cv2.imencode`` + ``ndarray.tofile``（``cv2.imwrite`` 在 Windows
    吃不到含中日韓字元的路徑）。輸入是 RGB，寫檔前轉成 cv2 要的 BGR。
    """
    path = str(path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    a = np.asarray(arr)
    if a.dtype != np.uint8 or a.ndim not in (2, 3):
        a = to_display_rgb(a)
    if a.ndim == 3 and a.shape[2] == 3:
        a = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".png", a)
    if not ok:      # pragma: no cover — PNG 編碼失敗實務上只在記憶體不足時發生
        raise ExportError("PNG encoding failed; cannot write {}.".format(path))
    tmp = path + ".tmp"
    buf.tofile(tmp)
    os.replace(tmp, path)
    return path
