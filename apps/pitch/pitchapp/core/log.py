# d4t 唯一的 logger — authored 2026-09-09.
"""**被吞掉的例外要留痕。** 鐵則 7「單顆出錯不殺整批」是對的，但「不 raise」
不等於「不記」。

2026-09-09 量到的：``d4t/`` 有 203 個 ``except Exception``，其中 61 個後面直接
``pass`` / ``continue`` / ``return``，而整個套件**零**處用 ``logging``。UI 有
``ui/crashlog.py`` 接**沒被接住**的例外；被接住然後吃掉的那些，在廠內出事時
是唯一能事後查的東西 —— 而它們一個字都沒留下。

這一份買到什麼
--------------
* 一個 logger（``"d4t"``），預設掛 ``NullHandler`` —— 沒人接的時候一個位元組
  都不寫、一行都不印，跟以前一模一樣（``logging.lastResort`` 不會被觸發）。
* :func:`swallowed`：在 ``except`` 區塊裡呼叫一次，例外連 traceback 記成 DEBUG。
  沒有 handler 時 ``isEnabledFor`` 一行就回，成本可以忽略。
* :func:`attach_file`：把 logger 接到一個檔案。CLI 是 ``run --log FILE``，
  Studio 開起來時接到 ``crashlog.log_dir()`` 底下的 ``d4t.log``（跟當機紀錄
  同一個資料夾，使用者只要學一個地方）。

刻意不做的
----------
* **不動任何 except 的語意。** 吃掉的還是吃掉，只是多留一行。
* **不印到終端機。** 使用者看到的訊息由 ``ctx.warn`` 與狀態列決定，那是產品
  的一部分；這裡是給事後查的人看的。
* **不 log 使用者的資料。** 只記 traceback 與「在哪裡」，跟 ``crashlog`` 同一條
  規矩（鐵則 8 的精神）。

⚠ 平行批次的 worker 是另一個行程：``fork`` 會帶著 handler 過去，``spawn``
（Windows、非主執行緒）不會。要看 worker 裡的紀錄，用 ``--workers 1`` 重跑
那一顆 —— ``run_defect`` 本來就是為了「單顆可以重現」寫的。
"""
from __future__ import annotations

import logging
import os
from typing import List

__all__ = ["LOGGER", "get", "swallowed", "attach_file", "detach", "detach_all"]

LOGGER = logging.getLogger("d4t")
LOGGER.addHandler(logging.NullHandler())

_ATTACHED: List[logging.Handler] = []
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def get(name: str = "") -> logging.Logger:
    """``d4t`` 底下的子 logger（``get("pipeline")`` → ``d4t.pipeline``）。"""
    return LOGGER.getChild(name) if name else LOGGER


def swallowed(where: str) -> None:
    """在 ``except`` 區塊裡呼叫：把正在處理的例外連 traceback 記成 DEBUG。

    ``where`` 是「哪一支的哪個函式」（``engine._roi_snapshot``）—— 事後查的人
    是從這個字串找過來的，他還不知道是哪一行。
    """
    if LOGGER.isEnabledFor(logging.DEBUG):
        LOGGER.debug("swallowed in %s", where, exc_info=True)


def attach_file(path: str, level: int = logging.DEBUG) -> logging.Handler:
    """把 logger 接到 ``path``（UTF-8、append）。資料夾不存在就建。"""
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    LOGGER.addHandler(handler)
    if LOGGER.level == logging.NOTSET or LOGGER.level > level:
        LOGGER.setLevel(level)
    _ATTACHED.append(handler)
    return handler


def detach(handler: logging.Handler) -> None:
    """拿掉 :func:`attach_file` 接上的那一個（測試用；正常執行整個 process 都掛著）。"""
    if handler in _ATTACHED:
        _ATTACHED.remove(handler)
    LOGGER.removeHandler(handler)
    try:
        handler.close()
    except Exception:
        pass    # 關不掉的 handler 沒有第二個地方可以報
    if not _ATTACHED:
        LOGGER.setLevel(logging.NOTSET)


def detach_all() -> None:
    for h in list(_ATTACHED):
        detach(h)
