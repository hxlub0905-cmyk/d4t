# d4t overlay rendering — authored 2026-07-28 (M5-1).
"""缺陷疊圖：把「機器看到什麼」畫成一張人看得懂的圖。

純 numpy/cv2，**不碰檔案**（除了 :func:`write_png`）—— 這樣 Studio 的
Gallery、CLI 的批次出圖、報表的插圖都能共用同一支渲染函式。

:func:`render_overlay` 產出 RGB uint8 面板：

- 底圖取 ``images["test"]``（EBI patch）或 ``images["single"]``（rSEM）；
- 量測框（``cd_box_*``）畫**紅框**；GLV 逐框比較的 ROI 框畫琥珀／鋼青
  （:func:`_draw_roi_boxes`），贏家框內可再標異常像素；
- 左上角可疊一行標籤（score / bin …），底下鋪半透明深色條方便閱讀；
- ``images`` 裡有 ``"diff"`` 時輸出 **[test | diff] 並排**（寬度剛好兩倍）；
  要別的組合就給 ``panes``（指名哪幾條流）與 ``stack``（橫排／直疊）。

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

__all__ = ["render_overlay", "write_png", "write_jpeg",
           "STACK_H", "STACK_V", "STACK_MODES",
           "DEFAULT_JPEG_QUALITY", "to_display_rgb",
           "primary_blob_box", "pick_base", "pick_overlay_results",
           "overlay_label",
           "rank_value", "rank_is_meaningless", "RANK_BY_SCORE",
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

#: 逐框比較（GLV 的 each box，F31）畫在報表上的兩種框（RGB）。
#: 贏家（最異常的那一格）用琥珀色粗框 —— 跟量測框（`BOX_COLOR` 的紅）分開，
#: 一張圖上兩種框各自講的是「哪一格異常」與「量到的東西在哪」。
#: 其餘的框畫細的鋼青色：它們是**參照**，要看得到（使用者才知道比較的分母是
#: 什麼）但不能跟主角搶畫面。core 不得 import Qt，所以這裡是自己的常數，
#: 不是 `theme.REGION_COLORS`。
ROI_WINNER_COLOR = (255, 176, 0)
ROI_BOX_COLOR = (110, 165, 220)

#: 「其餘的框」怎麼畫（出圖卡的 `draw_boxes` 那一格；`pick_roi_boxes`）。
DRAW_ALL = "all"
DRAW_NONE = "none"
DRAW_NEAR = "near the winner"
DRAW_MODES = (DRAW_ALL, DRAW_NONE, DRAW_NEAR)

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


#: 特徵裡「一個框」長什麼名字。
#:
#: 只剩 ``cd_box_*``（CD 卡量那一塊時**順手知道**的位置）——
#: ``blob_x/y/w/h`` 那一組連同 `find_defect` 於 F31 T5 刪掉（產者沒了，
#: 名單上多一組沒有人會寫的名字，等於邀請下一張卡撞進同一個名字空間）。
#: 「這張圖最異常的地方」現在走另一條路：GLV 逐框比較的贏家框由
#: :func:`worst_note_for_overlay` 從 meta 讀、當 ROI 框畫（粗琥珀），
#: 不進這張「量測框」名單 —— ROI 的框跟量測框是兩種東西。
_BOX_FEATURE_SETS = (
    ("cd_box_x", "cd_box_y", "cd_box_w", "cd_box_h"),
)


def primary_blob_box(features: Optional[Dict[str, Any]] = None
                     ) -> Optional[Tuple[int, int, int, int]]:
    """features 裡的量測框（:data:`_BOX_FEATURE_SETS`）；沒有回 None。

    （``blobs`` 那個參數 —— ``ctx.meta["blobs"]`` 的 richer path —— 連同
    `find_defect` 於 F31 T5 拿掉：全 repo 沒有任何東西在寫那個 meta 鍵。）

    ⚠ **只認沒有前綴的那一份。** 量測卡接了兩個以上的區域時，名字會變成
    ``epi_cd_box_x`` / ``mg_cd_box_x`` —— 那時候「主 blob」有兩個答案，
    而在兩個裡面挑一個畫出來、畫面上又不說是哪一個，正是這個 repo 最怕的
    「跑得完、有圖、而且是錯的」。所以那種情況下不畫框（回 None），
    等疊圖畫得下好幾個框再說。
    """
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


#: 排序用的預設欄位。``"score"`` 讀的是每一顆結果最上層的那一格，其他名字
#: 一律當成**特徵名**去 ``features`` 裡拿。
RANK_BY_SCORE = "score"


def rank_value(r: Dict[str, Any], rank_by: str = RANK_BY_SCORE) -> Optional[float]:
    """這一顆拿來排序的那個數字（拿不到回 ``None``）。"""
    raw = (r.get("score") if str(rank_by) == RANK_BY_SCORE
           else (r.get("features") or {}).get(str(rank_by)))
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    return None if f != f else f          # nan 不是一個排得了序的數字


def pick_overlay_results(results: Sequence[Dict[str, Any]], limit: int,
                         rank_by: str = RANK_BY_SCORE
                         ) -> List[Dict[str, Any]]:
    """依 ``rank_by`` 由高到低取前 ``limit`` 顆（拿不到那個數字的排最後）。

    **住在這裡而不是 UI**（F16 Stage 5c 搬過來的）：它問的是「這一批裡最值得
    看的是哪幾顆」——跟畫面無關，而 `output_image` 跟 Export 精靈要的是同一個
    答案。以前它在 `ui/export_dialog.py` 裡，於是那張卡照 `rows` 的順序取前 N
    —— **檔案順序上的前 N 顆幾乎一定不是使用者想看的那幾顆**，而畫面上看不出
    差別（都是 N 張 PNG）。

    ``rank_by`` 是 F30 加的，而它不是「多一個選項」那種加法：**判定樹是一個
    分類器，多數樹沒有分數表達式**，於是這一批一顆分數都沒有 —— 而上面那句
    警告講的正是那時候會發生的事。排序要有意義，就得由使用者指名一個他量得到
    的數字（``blob_strength``、``cmp_snr_mean``、``cd_area_px``…）。
    ``"score"`` 以外的名字一律當成**特徵名**。

    ⚠ **一顆都排不出來的時候，這裡回的就是輸入順序** —— 呼叫端有責任把那件事
    講出來（見 :func:`rank_is_meaningless`）。安靜地回檔案順序正是 F30 要修的
    那個 bug。

    ``limit`` 是 0（或負的）＝ 全部，不截斷。
    """
    rows = [r for r in (results or []) if r.get("ok", True)] or list(results or [])

    def key(r: Dict[str, Any]) -> Tuple[int, float]:
        v = rank_value(r, rank_by)
        return (1, 0.0) if v is None else (0, -v)

    rows = sorted(rows, key=key)
    n = max(0, int(limit))
    return rows[:n] if n else rows


def rank_is_meaningless(results: Sequence[Dict[str, Any]],
                        rank_by: str = RANK_BY_SCORE) -> bool:
    """這一批**一顆都排不出來**嗎（⇒ 取前 N 顆等於取檔案順序的前 N 顆）。

    分開成一支而不是讓 `pick_overlay_results` 自己 warn：它是純函式，而
    「要對誰講這句話」（`ctx.warn`、報表上一行字、對話框）是呼叫端的事。
    """
    return not any(rank_value(r, rank_by) is not None
                   for r in (results or []))


def pick_base(images: Dict[str, Any]) -> Tuple[str, np.ndarray]:
    """「沒有指名的時候，這一顆的圖是哪一張」——``BASE_PRIORITY`` 由前往後。

    出圖的卡也要問同一個問題（`output_char` 的左邊那一格），而**答案只能有
    一個**：兩個地方各自挑的話，同一顆 defect 在兩份輸出上會是兩張不同的圖。
    """
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
              color: Tuple[int, int, int] = BOX_COLOR,
              thick: Optional[int] = None) -> None:
    """在 panel 上畫框（超出邊界會被裁到圖內，至少留 1 px 寬高）。

    ``thick=None``＝照影像大小自動（量測框一直以來的規則）；
    逐框比較的 ROI 框自帶粗細（贏家粗、其餘細 —— 粗細就是那句話本身）。
    """
    h, w = panel.shape[:2]
    x, y, bw, bh = box
    x0 = max(0, min(int(x), w - 1))
    y0 = max(0, min(int(y), h - 1))
    x1 = max(x0, min(int(x) + max(1, int(bw)) - 1, w - 1))
    y1 = max(y0, min(int(y) + max(1, int(bh)) - 1, h - 1))
    if thick is None:
        thick = 1 if min(h, w) < 192 else 2
    cv2.rectangle(panel, (x0, y0), (x1, y1), tuple(int(c) for c in color),
                  int(thick))


def _draw_roi_boxes(panel: np.ndarray, roi_boxes, roi_winner: int) -> None:
    """畫逐框比較的 ROI 框（**正規化座標** 0..1）：其餘細、贏家粗。

    先畫其餘再畫贏家 —— 疊到的地方贏家在上面。贏家索引指不到（-1 或越界）
    就全部細線：**不猜**哪一格是主角（猜錯的框比沒有框糟得多）。
    """
    h, w = panel.shape[:2]
    boxes = list(roi_boxes or [])

    def _px(nb):
        nx, ny, nw, nh = (float(v) for v in nb)
        return (int(round(nx * w)), int(round(ny * h)),
                max(1, int(round(nw * w))), max(1, int(round(nh * h))))

    for i, nb in enumerate(boxes):
        if i != roi_winner:
            _draw_box(panel, _px(nb), color=ROI_BOX_COLOR, thick=1)
    if 0 <= roi_winner < len(boxes):
        px = _px(boxes[roi_winner])
        thick = 2 if min(h, w) < 192 else 3
        # 粗線不准吃掉框的內部：cv2 的線是騎在邊上畫的（往內外各長一半），
        # 一格只有幾 px 寬時 3 px 的四條邊會把整格塗滿 —— 於是 T3 的像素
        # 染色（畫在框**底下**）整片被蓋住，贏家框變成一顆實心色塊。
        # 實測（384²、~500 框、贏家 5×9 px）：染了 32 px、畫完框一個都看不見。
        thick = max(1, min(thick, (min(px[2], px[3]) - 1) // 3))
        _draw_box(panel, px, color=ROI_WINNER_COLOR, thick=thick)


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
# 逐框比較的框（F31）：從重跑回來的 Context 撿出來、決定畫哪幾個
# ---------------------------------------------------------------------------
def worst_note_for_overlay(ctx: Any) -> Tuple[list, int, Optional[Dict[str, Any]]]:
    """從 rerun 的 Context 撿逐框比較 → ``(正規化框列表, 贏家索引, note)``。

    來源是 GLV 卡留在 ``ctx.meta["glv_hist"]`` 的 note（``boxes >= 1`` 的那些
    是 each box 模式跑出來的）—— **跟 `worst_*` 特徵同一次計算**，不在這裡
    重新挑一次贏家。回傳的第三個值是那條 note 本身（贏家的 ``worst`` 帶著
    baseline / spread —— 像素標記的分母，見 :func:`_mark_odd_pixels`）；
    沒有逐框比較（pooled、沒接區域、根本沒跑 GLV）就回 ``([], -1, None)``，
    疊圖照舊 —— 沒接 ROI 的 recipe 一個位元不變。

    好幾條 note 都有框時取**第一條**（＝接線順序的第一個區域）：兩個區域各
    畫一組框、各有各的贏家，要等疊圖說得清「哪組框是誰的」再說 —— 挑一組畫
    而畫面上不說是哪一組，正是這個 repo 最怕的形狀，所以先只畫第一組，而
    「第一」是穩定的。
    """
    meta = getattr(ctx, "meta", None) or {}
    for note in meta.get("glv_hist") or []:
        region = str(note.get("region") or "")
        if not region or int(note.get("boxes") or 0) < 1:
            continue
        try:
            rects = list(ctx.roi_norm_rects(region))
        except Exception:       # noqa: BLE001 — note 指著一個已經不在的區域
            continue
        if not rects:
            continue
        worst = note.get("worst") or {}
        i = int(worst.get("i", -1)) if isinstance(worst, dict) else -1
        return rects, (i if 0 <= i < len(rects) else -1), dict(note)
    return [], -1, None


def roi_boxes_for_overlay(ctx: Any) -> Tuple[list, int]:
    """:func:`worst_note_for_overlay` 的前兩項（只要框的呼叫端用這個）。"""
    rects, winner, _note = worst_note_for_overlay(ctx)
    return rects, winner


def _mark_odd_pixels(panel: np.ndarray, src: Any, odd: Dict[str, Any]) -> None:
    """贏家框內偏離基準的像素上一層半透明的贏家色（F31 T3）。

    判準是 ``|pixel − baseline| / spread > k`` —— **baseline / spread 逐字是
    T1 算 `worst_score` 用的那兩個數字**（GLV 留在 meta 的 `worst` note；
    `spread` 已含地板）。這裡**不另外算一次**：畫面跟數字各自算的話，遲早出現
    「圖上標紅但數字說正常」—— Results R1 那個 bug 的形狀（同一個判斷散在
    兩個地方）。所以改 GLV 卡的判準統計量，標出來的東西**跟著變**。

    ``src`` 是**量測那條流的原始像素**（不是顯示用、被 `to_display_rgb` 拉過
    值域的那份）—— 判準跟數字同一份輸入。拿不到就一個都不標（不猜）。

    界線（任務書寫死的）：**只進 overlay**。不吐特徵、不生具名區域、不寫
    ``ctx.meta["blobs"]`` —— 一旦它開始吐 `blob_x` 那一族，find_defect 就從
    後門長回來了，而整個 F31 的設計是為了只有一種框。
    """
    if src is None:
        return
    arr = np.asarray(src, dtype=np.float64)
    if arr.ndim == 3:
        arr = arr.mean(axis=2)
    h, w = panel.shape[:2]
    if arr.shape[:2] != (h, w):
        return                       # 幾何對不上就不標 —— 標錯位置比不標糟
    nx, ny, nw, nh = (float(v) for v in odd["box"])
    x0 = max(0, min(int(round(nx * w)), w - 1))
    y0 = max(0, min(int(round(ny * h)), h - 1))
    x1 = max(x0 + 1, min(int(round((nx + nw) * w)), w))
    y1 = max(y0 + 1, min(int(round((ny + nh) * h)), h))
    spread = max(float(odd["spread"]), 1e-12)
    mask = (np.abs(arr[y0:y1, x0:x1] - float(odd["baseline"])) / spread
            > float(odd["k"]))
    if not mask.any():
        return
    seg = panel[y0:y1, x0:x1]
    tint = np.asarray(ROI_WINNER_COLOR, dtype=np.uint16)
    seg[mask] = ((seg[mask].astype(np.uint16) + tint) // 2).astype(np.uint8)


def pick_roi_boxes(rects, winner: int, mode: str, cap: int):
    """哪幾個框真的畫 → ``(要畫的框, 贏家在其中的索引, 有沒有自動退化)``。

    ``mode`` 是使用者那一格（:data:`DRAW_MODES`）；``cap`` 是「最多畫幾個」
    —— 它同時是 ``all`` 的自動退化門檻與 ``near the winner`` 的數量，**一個
    數字管兩件事**，所以不必再發明第二個。500 個框全畫會把整張圖蓋滿。

    * ``all``：全畫；超過 ``cap`` 自動退成 ``near the winner``（回傳的第三個
      值講出退化發生了，呼叫端要警告一次 —— 安靜退化的圖跟全畫的圖看起來
      都「有框」）。
    * ``near the winner``：贏家 ＋ 離它最近的 ``cap − 1`` 個（中心距離，平手
      照索引 —— 決定性）。
    * ``none``：只畫贏家。
    * 沒有贏家（-1）：``near`` 沒有「近」的參考點 —— ``all`` 且 ≤ ``cap``
      就全部細線，否則一個都不畫（畫不下又挑不出來，誠實的答案是不畫）。
    """
    boxes = list(rects or [])
    n = len(boxes)
    cap = max(1, int(cap))
    if not boxes:
        return [], -1, False
    mode = str(mode or DRAW_ALL)
    degraded = mode == DRAW_ALL and n > cap
    if degraded:
        mode = DRAW_NEAR
    if winner < 0 or winner >= n:
        if mode == DRAW_ALL:
            return boxes, -1, False
        return [], -1, degraded
    if mode == DRAW_ALL:
        return boxes, winner, False
    if mode == DRAW_NONE:
        return [boxes[winner]], 0, False
    # near the winner
    wx, wy, ww, wh = (float(v) for v in boxes[winner])
    wcx, wcy = wx + ww / 2.0, wy + wh / 2.0

    def _dist(k):
        x, y, w, h = (float(v) for v in boxes[k])
        return (x + w / 2.0 - wcx) ** 2 + (y + h / 2.0 - wcy) ** 2

    others = [k for k in range(n) if k != winner]
    others.sort(key=lambda k: (_dist(k), k))  # 平手照索引 —— 決定性
    keep = sorted([winner] + others[:cap - 1])  # 贏家一定在；照原框序畫
    return [boxes[k] for k in keep], keep.index(winner), degraded


# ---------------------------------------------------------------------------
# 並排／堆疊
# ---------------------------------------------------------------------------
#: 面板之間那一條分隔線的灰階值。
SEAM_GRAY = 96
#: `render_overlay` 的 ``stack``：橫著排／直著疊。
STACK_H = "h"
STACK_V = "v"
STACK_MODES = (STACK_H, STACK_V)


def _pane(src: Any, size: Tuple[int, int],
          roi_boxes: Optional[Sequence[Any]], roi_winner: int,
          the_box: Optional[Tuple[int, int, int, int]]) -> np.ndarray:
    """一格面板：拉成可顯示的 RGB、對齊到底圖的大小、把框畫上去。

    **兩條路共用這一支**（預設的 [底圖 | diff] 與指名 ``panes`` 的那條）——
    各寫一份的話，「框有沒有畫在第二格上」這種事會在其中一條路上安靜地漂掉。
    """
    h, w = int(size[0]), int(size[1])
    arr = to_display_rgb(src)
    if arr.shape[:2] != (h, w):
        arr = cv2.resize(arr, (w, h), interpolation=cv2.INTER_NEAREST)
    if roi_boxes:
        _draw_roi_boxes(arr, roi_boxes, int(roi_winner))
    if the_box is not None:
        _draw_box(arr, the_box)
    return arr


def _stack_panes(parts: Sequence[np.ndarray], stack: str) -> np.ndarray:
    """把幾格面板接成一張，接縫處畫一條細線。

    ``"h"`` 橫著排、``"v"`` 直著疊。分隔線是**覆寫**接縫後的第一列／行，
    不是插進去一條 —— 所以兩格橫排的總寬度剛好是兩倍（那是這個函式出現之前
    就成立的事，不可以因為抽出來而改變）。
    """
    parts = [p for p in parts if p is not None]
    if len(parts) <= 1:
        return parts[0]
    axis = 0 if str(stack) == STACK_V else 1
    panel = np.concatenate(parts, axis=axis)
    off = 0
    for part in parts[:-1]:
        off += int(part.shape[axis])
        if axis == 1:
            panel[:, off:off + 1] = SEAM_GRAY
        else:
            panel[off:off + 1, :] = SEAM_GRAY
    return panel


# ---------------------------------------------------------------------------
# 主函式
# ---------------------------------------------------------------------------
def render_overlay(images: Dict[str, Any],
                   features: Optional[Dict[str, Any]] = None, *,
                   box: Optional[Sequence[int]] = None,
                   label: Optional[str] = None,
                   base_key: Optional[str] = None,
                   diff_key: str = "diff",
                   montage: bool = True,
                   panes: Optional[Sequence[str]] = None,
                   stack: str = STACK_H,
                   roi_boxes: Optional[Sequence[Any]] = None,
                   roi_winner: int = -1,
                   odd_pixels: Optional[Dict[str, Any]] = None) -> np.ndarray:
    """把一顆 defect 畫成 RGB uint8 面板。

    參數
    ----
    images
        Context 的影像 dict（或其子集）。底圖依 ``test`` → ``single`` →
        ``aligned`` → ``ref`` → ``diff`` 的順序挑第一個找得到的；
        ``base_key`` 可以指定。
    features
        該顆的特徵 dict。兩個用途：(1) ``box`` 沒給時，若含
        ``cd_box_x/y/w/h``（:data:`_BOX_FEATURE_SETS`）就用它畫紅框；
        (2) ``label`` 沒給但含 ``score`` 時自動組出 ``score=…`` 標籤。
    box
        直接指定 ``(x, y, w, h)``，優先於 ``features``。
    label
        左上角文字（非 ASCII 會顯示成 ``?``，見模組 docstring）。
    montage
        ``images`` 有 ``diff`` 時是否輸出 **[底圖 | diff] 並排**
        （預設 True，寬度剛好是底圖的兩倍）。``panes`` 給了就不看這一個。
    panes / stack
        **指名哪幾條流、橫著排還是直著疊**（F33）。``panes`` 是一串流名，
        第一個就是底圖（``base_key`` 沒給的話）；接不到的那一條跳過。
        ``stack`` 是 ``"h"``（預設，橫排）或 ``"v"``（直疊）。

        直疊是 characterization 要的方向：上面 ground truth、下面第二份 ——
        它要對得上報表由上往下讀的順序。``panes=None``（預設）時整條路徑
        跟這兩個參數出現之前**逐位元組相同**。
    roi_boxes / roi_winner
        逐框比較的 ROI 框（F31）：**正規化** 0..1 的 ``(x, y, w, h)`` 清單與
        贏家的索引。其餘畫細的鋼青色、贏家畫粗的琥珀色；索引是 -1 就全部
        細線（**不猜**）。誰畫、畫幾個由呼叫端的 :func:`pick_roi_boxes`
        決定，來源用 :func:`roi_boxes_for_overlay` 從 Context 撿。
        預設 ``None``：不畫，跟這個參數出現之前逐位元組相同。
    odd_pixels
        贏家框內的像素標記（F31 T3；:func:`_mark_odd_pixels`）：
        ``{"box": 正規化rect, "baseline": …, "spread": …, "k": …,
        "src": 量測那條流的原始陣列}``。判準的 baseline / spread 逐字是
        GLV 算 `worst_score` 用的那兩個數字 —— 不另外算一次。
        預設 ``None``：不標。

    回傳 ``(H, W, 3)`` 或 ``(H, 2W, 3)`` 的 uint8 RGB 陣列；
    ``panes`` 給了 N 格就是 ``(H, N·W, 3)``（橫排）或 ``(N·H, W, 3)``（直疊）。
    """
    if not isinstance(images, dict) or not images:
        raise ExportError(
            "render_overlay needs a dict of images (e.g. ctx.images); it got an empty one.")
    features = dict(features or {})

    names = None
    if panes is not None:
        names = [str(n) for n in panes if str(n).strip()]
        if not names:
            raise ExportError(
                "render_overlay was asked for named panes but the list is "
                "empty; leave panes out to get the usual [base | diff].")
        if str(stack) not in STACK_MODES:
            raise ExportError(
                "render_overlay stack must be one of {}; got {!r}.".format(
                    ", ".join(STACK_MODES), stack))
        # 第一格**就是**底圖 —— 呼叫端指名了順序，這裡不再自己挑一張。
        if base_key is None:
            base_key = names[0]

    if base_key is not None:
        if base_key not in images or images[base_key] is None:
            raise ExportError(
                "The requested base image stream \"{}\" does not exist; this defect has: {}.".format(
                    base_key, ", ".join(sorted(images))))
        base = images[base_key]
    else:
        base_key, base = pick_base(images)

    left = to_display_rgb(base)
    h, w = left.shape[:2]

    # 像素標記最底、ROI 框中間、量測框最上 —— 疊到的地方
    # 「量到的東西在哪」在最上面。
    if odd_pixels:
        _mark_odd_pixels(left, odd_pixels.get("src"), odd_pixels)
    if roi_boxes:
        _draw_roi_boxes(left, roi_boxes, int(roi_winner))
    the_box = _blob_box(box) if box is not None else primary_blob_box(features)
    if the_box is not None:
        _draw_box(left, the_box)

    if names is not None:
        # 指名了哪幾條流：第一格就是底圖（上面已經畫好），其餘照順序接上去。
        # **接不到的那一條就跳過** —— 同「``diff`` 不在就不並排」的老規矩：
        # 缺一格不值得讓整張圖畫不出來，而缺的那一格本身常常就是答案
        # （配不到的那一顆沒有第二張圖）。
        parts = [left]
        for name in names[1:]:
            src = images.get(name)
            if src is not None:
                parts.append(_pane(src, (h, w), roi_boxes, roi_winner, the_box))
        panel = _stack_panes(parts, stack)
    else:
        panel = left
        right_src = images.get(diff_key)
        if montage and diff_key != base_key and right_src is not None:
            panel = _stack_panes(
                [left, _pane(right_src, (h, w), roi_boxes, roi_winner,
                             the_box)], STACK_H)

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


def _write_encoded(arr: np.ndarray, path: str, ext: str, params=None) -> str:
    """編碼 → atomic 落地（``.tmp`` + :func:`os.replace`）、CJK 路徑安全。

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
    ok, buf = cv2.imencode(ext, a, list(params or ()))
    if not ok:      # pragma: no cover — 編碼失敗實務上只在記憶體不足時發生
        raise ExportError("%s encoding failed; cannot write %s."
                          % (ext.lstrip(".").upper(), path))
    tmp = path + ".tmp"
    buf.tofile(tmp)
    os.replace(tmp, path)
    return path


def write_png(arr: np.ndarray, path: str) -> str:
    """把疊圖存成 PNG —— atomic、CJK 路徑安全（見 :func:`_write_encoded`）。"""
    return _write_encoded(arr, path, ".png")


#: JPEG 的預設品質。**80 不是隨手挑的**：實測一張整版的 overlay panel
#: （test | diff 並排、紅框、一行標籤）PNG 是 70 KB，JPEG q75 是 12.6 KB。
#: 一份 6000 顆的報表因此是 566 MB 對上約 76 MB —— 那是「打不開」與「寄得出去」
#: 的差別。80 比 75 再多一點餘裕，代價是幾 KB。
DEFAULT_JPEG_QUALITY = 80


def write_jpeg(arr: np.ndarray, path: str,
               quality: int = DEFAULT_JPEG_QUALITY) -> str:
    """把疊圖存成 JPEG —— 跟 :func:`write_png` 同一個 atomic 寫法。

    ⚠ **JPEG 是有損的，所以它只給「拿來看的」那一份**（報表裡的縮圖）。
    要拿去量、要逐位元組比對的那一份請用 PNG —— 壓縮痕跡會在平坦的區域上
    造成幾個灰階的起伏，而這個 repo 有一整族「幾個灰階」等級的判斷
    （`algo/shape._MIN_CONTRAST` 就是 1）。
    """
    q = max(1, min(100, int(quality)))
    return _write_encoded(arr, path, ".jpg", (cv2.IMWRITE_JPEG_QUALITY, q))
