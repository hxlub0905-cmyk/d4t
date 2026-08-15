# ADEPT overlay rendering — authored 2026-07-28 (M5-1).
"""缺陷疊圖：把「機器看到什麼」畫成一張人看得懂的圖。

純 numpy/cv2，**不碰檔案**（除了 :func:`write_png`）—— 這樣 Studio 的
Gallery、CLI 的批次出圖、報表的插圖都能共用同一支渲染函式。

:func:`render_overlay` 產出 RGB uint8 面板：

- 底圖取 ``images["test"]``（EBI patch）或 ``images["single"]``（rSEM）；
- 呼叫端給了 ``box=(x, y, w, h)`` 就畫一個**紅框**；
- 左上角可疊一行標籤（score / bin …），底下鋪半透明深色條方便閱讀；
- ``images`` 裡有 ``"diff"`` 時輸出 **[test | diff] 並排**（寬度剛好兩倍）。

★ 框從哪裡來（2026-08-15 改）★
  這裡以前會自己去 ``ctx.meta["blobs"]`` 或 ``blob_x/blob_y/blob_w/blob_h``
  特徵裡挑「主 blob」。``blob_segment`` 卡在 F8 第五輪被拿掉之後，那兩個來源
  **再也沒有人產出**，於是那段程式碼永遠回 None —— 而 Export 精靈上仍然寫著
  「the main blob boxed in red」。跑得完、有輸出、而且承諾沒有兌現。
  現在框只有一個來源：**呼叫端明講**。要畫什麼由知道的人決定，這裡不猜。

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

__all__ = ["render_overlay", "write_png", "to_display_rgb", "BOX_COLOR"]

#: 外框的顏色（RGB）。
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


def _as_box(b: Any) -> Optional[Tuple[int, int, int, int]]:
    """``(x, y, w, h)``（四個數的序列，或有 ``x/y/w/h`` 的物件）→ 整數 tuple。

    看不懂就回 None，不要猜 —— 畫錯位置的框比沒有框糟得多。
    """
    if b is None:
        return None
    if isinstance(b, dict):
        if not all(k in b for k in ("x", "y", "w", "h")):
            return None
        vals = (b["x"], b["y"], b["w"], b["h"])
    elif isinstance(b, (tuple, list)) and len(b) >= 4:
        vals = tuple(b[:4])
    elif all(hasattr(b, k) for k in ("x", "y", "w", "h")):
        vals = (b.x, b.y, b.w, b.h)
    else:
        return None
    try:
        return (int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3]))
    except (TypeError, ValueError):
        return None


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
        該顆的特徵 dict。用途只有一個：``label`` 沒給但含 ``score`` 時
        自動組出 ``score=…`` 標籤。
    box
        要圈起來的 ``(x, y, w, h)``（像素座標）。**不給就不畫框** ——
        這裡不會自己去猜哪裡是缺陷（見模組 docstring）。
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

    the_box = _as_box(box)
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
