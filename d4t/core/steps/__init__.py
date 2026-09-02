# d4t step-card library — authored 2026-07-28 (M1).
"""步驟卡片庫：import 本套件即完成所有卡片的 registry 註冊。

每個子模組是一到多張卡（@register_step 的 Step 子類別）；
引擎與 UI 只需 ``import d4t.core.steps`` 再從
``d4t.core.pipeline.step.REGISTRY`` / ``list_steps()`` 取卡。

已註冊的 key（影像段 → 算法段）：
  load_patch, load_single, load_sidecar, normalize, tone, denoise, flatten,
  align, subtract, align_to, pair_source,
  roi_reference,
  glv_stats, cd_measure, focus_quality,
  output_report, output_klarf, output_char

**2026-09-02：``roi_mask``（Mask from regions）刪掉了。** 使用者：「請幫我拿掉
（看不到此功能 card 用處）」。連同它唯一的消費者 —— ``normalize`` 的
``use_within``（畫面上的「Use only」）—— 一起拿掉：那一格只吃得下這張卡吐的
mask 流，卡走了就沒有任何一張卡產得出它，而那一格是 ``image_key``（設定區
唯讀、只能靠拉線填），於是它會變成**一個接不到東西的埠**。

代價量過而且很小：**沒有任何一份 recipe 用它** —— `recipes/` 三份、
`tests/fixtures/recipes/` 兩份、三份黃金值全部沒有 ``roi_mask`` 節點，也沒有
一格 ``use_within``（黃金值三份逐項相同）。`algo/histmatch.py` 的 ``_masked``
**不刪**（同 ``algo/snr.py`` 那條規矩）：它是「量與套用分開」那個慣例的規範
出處，而 ``range_from`` 走的是同一套。

舊 recipe：帶 ``roi_mask`` 節點的開起來是一條 ``unknown-step``（同
``pattern_ref`` / ``feature_math`` 的先例）；``normalize`` 上那一格由
``recipe._migrate_drop_use_within`` 拿掉 —— 不拿的話它是
「unknown parameters」，而那句話的意思是「這份檔案壞了」。

**Region 段因此只剩一張卡，而它的 label 從「Reference regions」改成「ROI」**
（使用者同一句話）。``key`` 仍然是 ``roi_reference``（recipe 的鍵）、
feature 名一個都沒動 —— 改的只有畫面上那幾個字（CLAUDE.md §5 那張價目表的
最後一列：「名字剪短一點」＝零代價）。

**2026-08-25（F31 T5）：``find_defect`` 刪掉了。** 使用者：「我覺得 find
defect 不需要。」它 2026-08-25 早上才進來（F29），零 recipe、零 fixture、
零黃金值在用 —— 「先收後刪」那條規矩服務的是「舊 recipe 還在用」，這裡沒有
那個問題，所以直接刪。三類輸出全部有了替代：位置＝GLV 逐框比較的
``glv_worst_x/y/w/h``（框就是 ROI 自己）、突出度＝``glv_worst_score``、框內細節＝
疊圖的像素標記（只畫，不吐數字）。``algo/shape.py`` 的 ``find_blobs`` /
``BlobScan`` / ``BlobHit`` 一起刪（唯一呼叫者就是這張卡）；``measure_blob``
與共用的準位不動 —— CD 在用。

**2026-08-25：``snr_map``（畫面上叫 Z-map）刪掉了。** 使用者：「Z-map 功能請
先幫我完整刪掉」。代價量過：兩份 fixture recipe 有三個 `snr_map` 節點，而
**沒有任何一張下游的卡讀它那條流**（`cd` / `glv` 讀的是 `test` 與 `diff`），
兩份 recipe 的 score 也都不含 `snr_max` —— 所以拿掉它只是三份黃金值各少一個
特徵欄，分數與 bin 一個都沒有動。這跟 `pattern_ref` 那次不一樣（那次
rsem route 的準確率從 24/24 掉到 12/24）。

⚠ ``d4t/core/algo/snr.py`` **不刪**。它的呼叫者確實只剩測試，但 `snr_signed`
是**帶正負號那個慣例的規範出處** —— GLV 卡的 `snr` 統計量照它做，而
`tests/test_steps.py` 就在斷言它還在。同一條規矩 `algo/period.py` 與
`algo/golden.py` 已經寫過一次（見 `d4t/ui/scope.py`）。

**2026-08-20（F16）：``pattern_ref`` 刪掉了。** 使用者：「Compare 中
pattern_ref 這項功能完全沒用，請直接拿掉」。

它的代價量過而且**真的付了**：rsem 那條 route 靠它從單張影像的重複 pattern
疊一張 ref 出來，才有 ``diff`` 可以量 —— 分類正確率 24/24。沒有它，同一條
route 只剩「直接量單張影像」，而那條路量過是 12/24（＝猜銅板）。所以
``tests/fixtures/recipes/dual_route_basic.json`` 的 rsem route 重做了，
而 ``tests/test_e2e_dual_route.py`` 的 rsem 斷言從**準確率**改成**跑得完、
算得出分數** —— 那個準確率證據跟著這張卡一起消失了，假裝它還在比沒有更糟。

**2026-08-18：``golden`` 那一支拆成兩件事**（前情）：``cell_period``
（Cell period）刪掉 —— 使用者：「不需要這功能」；``golden_cell`` 先刪、同一天
要回來並改名成 ``pattern_ref`` —— 也就是這一輪拿掉的那一張。

刪掉與 `scope.HIDDEN_STEPS` 收起來是兩件事，差別在使用者說的是哪一句話：
`align` 是「之後真需要我再回來」→ 收起來；`cell_period` / `pattern_ref` 是
「不需要」「完全沒用」→ 刪掉。

⚠ ``d4t/core/algo/golden.py`` 與 ``d4t/core/algo/period.py`` **仍然不要刪** ——
`pattern_ref` 走了之後它們的呼叫者只剩一個（``algo/template.py`` 疊 Golden Cell
模板時要 ``stack_cells`` 與 ``estimate_period`` / ``choose_origin``）。
只剩一個呼叫者的模組正是最容易被當成死碼順手清掉的那一種。
"""
from __future__ import annotations

from . import _util          # 共用小工具（非卡片）
from . import load           # load_patch / load_single
from . import load_sidecar  # load_sidecar（GLAS 的 label map）
from . import normalize      # normalize（percentile / glv_band / match / local）
from . import denoise        # denoise
from . import tone           # tone（亮度/對比/gamma/曲線/反相）
from . import flatten        # flatten
from . import align          # align
from . import arith          # subtract / invert
from . import align_to       # 小圖在大圖裡的位置（F15-C）
from . import pair_source    # 另一份資料的對應那一顆（F15）
# Region 段只剩**一張**（F30 收成兩張，2026-09-02 再收成一張）。
# `roi_cross`（Profile）與 `roi_template`（Template）折進 `roi_reference` 變成
# 它的兩個 method，所以那兩個模組**不在這裡 import** —— 它們不再自己註冊，
# 是被 `roi_reference` 取用的實作。
from . import roi_reference  # roi_reference（四種找法 → 具名區域）
# ⚠ **Measure 段的順序就是這幾行的順序**（使用者 2026-08-25：「Measure 的 card
# 順序幫我改命名&重排：GLV → CD → Focus index」）。`list_steps` 照 REGISTRY 的
# 插入序回，而 REGISTRY 的插入序就是這裡的 import 序 —— 卡片庫裡看到的先後
# 住在這幾行，不住在任何一張卡上。
#
from . import glv_stats      # glv_stats（GLV：stats / compare）
from . import cd             # cd_measure（CD）
from . import quality        # focus_quality（Focus index）
from . import output         # Output 段（csv / report / klarf / image）

__all__ = [
    "load", "load_sidecar", "normalize", "denoise", "tone", "flatten", "align", "arith",
    "quality", "glv_stats",
    "output",
]
