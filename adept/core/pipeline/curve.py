# ADEPT pipeline contract — authored 2026-07-29 (F7-8).
"""Tone-curve 控制點的字串編碼（parse / format）。

為什麼是字串
------------
recipe 是給人看、也給 git diff 看的 JSON。控制點如果存成巢狀陣列，
diff 會變成一整片括號；存成 ``"0,0; 0.35,0.55; 1,1"`` 一眼就看得出使用者
把暗部拉起來了。而且 ``ParamSpec`` 的值一律是純量 —— 一個參數一個值，
UI 表單、rescore、CLI ``--set`` 都靠這條規則，不想為了曲線破例。

為什麼放在 ``pipeline/`` 而不是 ``algo/``
-----------------------------------------
``ParamSpec.validate`` 要用它（推廣鐵則：填爆的值要擋在表單，不能跑到演算法
裡才炸），而 ``pipeline`` 不該把整個 ``algo`` 套件（連帶 cv2）拉進 import 圖。
所以**編碼**在這裡、純 stdlib；**求值**（LUT、套用到影像）在
``algo/curve.py``，那邊才用 numpy。
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

__all__ = ["IDENTITY", "parse_curve", "format_curve", "is_identity",
           "CurveError"]

Point = Tuple[float, float]

#: 預設曲線 = ``y = x``（什麼都不做）。UI 的曲線編輯器一開也是這條線。
IDENTITY = "0,0; 1,1"

#: 兩個 x 太靠近就視為同一點（避免除以 0，也避免使用者拖出肉眼看不出的重疊點）。
_MIN_DX = 1e-4


class CurveError(ValueError):
    """曲線字串不合法。訊息是白話的 —— 會直接顯示在參數列下面。"""


def parse_curve(text: object) -> List[Point]:
    """``"0,0; 0.4,0.6; 1,1"`` → ``[(0.0, 0.0), (0.4, 0.6), (1.0, 1.0)]``。

    規則（每一條都會回一句白話錯誤）：

    * 至少兩點；
    * x 與 y 都在 0–1；
    * 依 x 排序後 x 必須嚴格遞增（曲線不能往回折）；
    * 頭尾的 x 必須是 0 與 1 —— 曲線要覆蓋整個灰階範圍，
      少了就會有一段灰階沒有定義。

    空字串（或 ``None``）視為 :data:`IDENTITY`，這樣舊 recipe 沒有這個參數
    也讀得動。
    """
    s = "" if text is None else str(text).strip()
    if not s:
        return parse_curve(IDENTITY)

    pts: List[Point] = []
    for chunk in s.replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        bits = [b.strip() for b in chunk.split(",")]
        if len(bits) != 2:
            raise CurveError(
                "curve point '%s' should look like 'x,y' (two numbers between "
                "0 and 1, separated by a comma)" % chunk)
        try:
            x, y = float(bits[0]), float(bits[1])
        except ValueError:
            raise CurveError(
                "curve point '%s' is not a pair of numbers" % chunk) from None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise CurveError(
                "curve point '%s' is outside 0–1 (x is the input gray level, "
                "y is the output, both normalised)" % chunk)
        pts.append((x, y))

    if len(pts) < 2:
        raise CurveError("a curve needs at least two points (start and end)")

    pts.sort(key=lambda p: p[0])
    for a, b in zip(pts, pts[1:]):
        if b[0] - a[0] < _MIN_DX:
            raise CurveError(
                "two curve points share the same input level (x=%.4f); "
                "a curve can only go left to right" % a[0])
    if pts[0][0] > 0.0 or pts[-1][0] < 1.0:
        raise CurveError(
            "a curve must start at x=0 and end at x=1, otherwise part of the "
            "gray range has no output defined")
    return pts


def format_curve(points: Sequence[Point]) -> str:
    """控制點 → 標準字串。四位小數 —— 再細也不是使用者拉得出來的精度。"""
    out = []
    for x, y in points:
        out.append("%s,%s" % (_num(x), _num(y)))
    return "; ".join(out)


def is_identity(points: Sequence[Point], tol: float = 1e-6) -> bool:
    """這條曲線等於 ``y = x`` 嗎（也就是「使用者其實沒畫」）。

    卡片用這個判斷要不要理會曲線 —— 沒畫就走 gamma 滑桿。
    """
    pts = list(points)
    if len(pts) != 2:
        return all(abs(y - x) <= tol for x, y in pts)
    return all(abs(y - x) <= tol for x, y in pts)


def _num(v: float) -> str:
    """去掉沒有意義的尾數零：``0.5000`` → ``0.5``、``1.0000`` → ``1``。"""
    s = "%.4f" % float(v)
    s = s.rstrip("0").rstrip(".")
    return s or "0"
