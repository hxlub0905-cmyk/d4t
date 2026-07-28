# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

---

## 2026-07-28 · M0–M3 + 專案命名（Claude Cowork session）

從零建立整個專案。原工作代號 FlexADC，完成 M3 後定名 **ADEPT**。

### M0 抽庫（117 tests）
盤點六個既有專案（KLIP / GLAS / MMH / PEAR / cell-period-estimator /
Perspective-Combination），把可重用演算法 vendoring 進 `adept/core`。
決策：**vendoring 而非共用 library** —— 新工具完全獨立、不動現有專案。

統一了三個歷史摩擦：
1. ROI 座標 → 正規化座標（`NamedROI`）為正典，像素矩形一律 `(x,y,w,h)`。
2. SNR 正負號 → `snr_signed = (μ_target − μ_ref)/σ_ref` 為唯一正典 primitive。
3. `compute_snr_map` → 改回傳 `SnrMapResult(map_float, snr_max)`（原版回傳 tuple 與型別註記不符）。

順手抓到 **Fusi³ `ecc` 對位 backend 位移正負號與其他四個相反**的 bug（原專案可回頭修）。

### M1 引擎（223 tests）
- `Context` / `Step` / `ParamSpec` / registry 契約（MMH recipe 架構的一般化：
  寫死 6 stage → 任意 DAG 節點，並補上 MMH 缺的參數驗證）。
- `Recipe`(DAG) + lint 式 `validate`（10 種 issue code，一次列出所有問題）。
- score 表達式引擎：自寫 tokenizer → recursive-descent parser → AST → evaluator，
  **不用 Python eval**；安全語意（除以零/log 負數/nan → 0.0，不爆給使用者看）。
- 14 張步驟卡片、合成資料產生器、CLI。
- **端到端驗收**：合成 lot（24 顆、真假各半）分類正確率 ~94%（跨 seed）。
  調出這份範例 recipe 的過程本身就是工具價值的實證 —— 第一版完全分不開
  （Otsu 在正規化 SNR map 上把半張圖切成 blob），靠 feature 表診斷 →
  主 blob 選取從「面積最大」改「SNR 最強」→ 加 Denoise 卡 →
  score 改用 diff 中心區 GLV 峰值，三輪迭代從 50% 拉到 94%。

### M2 批次（245 tests）
- ProcessPool 平行批次（單顆爆不殺整批、progress/abort）。
- **影像段 checkpoint 快取**：快取邊界切在三段式的「影像段結尾」，
  與 UI 心智模型對齊 —— 改算法段/判定段的任何東西都是秒級回饋。
- SQLite 批次歷史 + **rescore**（改表達式/門檻不重跑影像）。
- 實測（2 核容器、2000 顆合成 patch）：cold 17.5 ms/顆 → warm cache 2.2 ms/顆 →
  rescore 0.17 s。換算 8 核廠內機 10k patch 約 1 分鐘。
- 過程中發現 **OpenCV IPP 非決定性**（同圖算兩次差 ~1e-8，SIMD 路徑依緩衝區位址而變），
  導致快取無法 bit-identical → `pin_cv2_deterministic()` 關閉 IPP。

### M3 Studio UI（291 tests）
- PySide6 四區塊：卡片庫｜Pipeline｜單顆預覽｜分數直方圖，三段式分色。
- `RecipeModel` 是 Qt-free 的編輯模型（可 headless 測試），UI 元件只做顯示與轉發。
- ParamForm 由 ParamSpec 自動生成，每格都有白話說明、範圍防呆、錯誤即時紅字。
- PreviewWorker 請求合併（改參數狂發請求只跑最新那個）。
- 拖門檻線即時看 bin 數變化（走 rescore 的純計算路徑，不碰影像）。
- **修掉一個會讓工具在廠內「看起來當掉」的 bug**：`run_batch` 從 QThread fork
  ProcessPool 在 Linux 上第二次必定死鎖（進度條不動也不報錯）。
  修法：`batch._pool_context()` 主執行緒 fork（CLI/腳本免寫 `if __name__ == "__main__"`）、
  非主執行緒 spawn。補迴歸測試 `tests/test_batch_thread_safety.py`。
- 補上卡片庫「ADC 判定」段的固定 Score/Bin 項目，讓三段式故事在 UI 上完整。

### 命名
候選過水果系（PEACH/FIG/PLUM，與 PEAR 成家族）與非水果系，最後選
**ADEPT = Auto Defect Evaluation Pipeline Tool** —— 縮寫精準對應功能，
而 adept（熟練、得心應手）正是要給不寫 code 同事的承諾。
套件 `flexadc` → `adept`、CLI `python -m adept`、設定目錄 `~/.adept/`。

### 下一步
M4 雙輸入 + Golden Cell（見 CLAUDE.md §9）。
