# d4t export package — created 2026-07-28 (M5-1).
"""d4t.core.export — 結果輸出層：KLARF 寫回、報表、疊圖。

單一匯入點::

    from d4t.core.export import (
        plan_writeback, apply_writeback,      # KLARF 三種寫回模式
        summarize, write_csv, write_excel,    # 報表
        render_overlay, write_png,            # 疊圖
    )

三塊各自的規矩（細節見各模組 docstring）：

- :mod:`.klarf_out` —— ``inplace`` 只改既有欄位且**無損**（沒改到的 byte
  與原檔逐位元組相同）；``annotate`` 追加 ADCSCORE/ADCCLASS 並保證影像
  區塊留在列尾；``topn`` 只留高分的並講清楚影像參照怎麼處理。
- :mod:`.report` —— CSV 是 utf-8-sig，Excel 三張表都由 :func:`summarize`
  這支純資料函式餵。
- :mod:`.overlay` —— 純 numpy/cv2 渲染，檔案 IO 只有 :func:`write_png`。

檔案寫入一律 atomic（``.tmp`` + ``os.replace``），且**零 Qt**。
"""
from __future__ import annotations

from .klarf_out import (
    MODES,
    ExportError,
    WriteBackPlan,
    apply_writeback,
    plan_writeback,
)
from .overlay import (
    pick_overlay_results, primary_blob_box, render_overlay, to_display_rgb,
    write_png,
)
from .report import feature_keys, summarize, write_csv, write_excel

__all__ = [
    "ExportError", "WriteBackPlan", "MODES", "plan_writeback", "apply_writeback",
    "summarize", "write_csv", "write_excel", "feature_keys",
    "render_overlay", "write_png", "to_display_rgb", "primary_blob_box",
    "pick_overlay_results",
]
