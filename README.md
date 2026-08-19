# d4t — defect

> 半導體 E-beam Inspection（EBI）與 Review SEM 的**可組態 ADC**
> （Auto Defect Classification）工具。以節點畫布把影像處理與量測步驟組成 recipe，
> 對每一顆 defect 計算特徵、算分、分 bin，並將結果**無損**寫回 KLARF。

**`d4t` 是 *defect* 的 numeronym** —— 頭字母 ＋ 中間字數 ＋ 尾字母，
與 `i18n`、`k8s`、`n8n` 同一套慣例。名稱底下一律並列全稱：**d4t — defect**。

---

## 設計立場

半導體廠的每一個 Inspection 站點，缺陷型態、影像條件與判定標準都不一樣。
傳統 PADC / RADC 的做法是**為每個站點各寫一份程式**，於是站點差異散落在程式碼裡，
每一次調整都得回到工程師手上。

d4t 的第一原則是：

> **站點差異封裝進 recipe，不封裝進程式碼。**

第二原則決定了介面的每一個取捨：

> **目標使用者是不會寫 code 的製程／設備工程師。**
> 任何讓他們看不懂、或會噴出錯誤訊息的設計，都視為 bug。

兩者合起來的結果，是一個讓人**用滑鼠把想法組成算法**、並產出可量化證據的工具。

---

## 能力概覽

| | |
|---|---|
| **輸入** | 四種 source，各有各的入口：`ebi_patch`（KLARF ＋ 多頁 patch TIFF）、`rsem`（KLARF ＋ 每顆一個影像檔）、`tiff_stack`（多頁 TIFF，無 KLARF）、`folder`（單張影像資料夾，無 KLARF） |
| **組裝** | 20 張步驟卡片（卡片庫現行可見 18 張）；節點畫布拉線接卡，recipe 即 DAG |
| **量測** | SNR／GLV 統計、CD 次像素邊緣定位、影像品質指標、區域對比、SNR map、blob 分割 |
| **輸出** | 無損寫回 KLARF（class／bin／DSIZE）、Top-N 新 KLARF、CSV／Excel 報表、feature vector（供日後 ML 訓練備料） |
| **介面** | PySide6 桌面編輯器（Studio）＋ CLI（可排程、可腳本化） |
| **執行** | 多行程批次、影像段快取；設計目標為單批 10,000 顆 defect 仍流暢 |

無 KLARF 的兩種 source（`tiff_stack`、`folder`）沒有座標，因此**無法寫回 KLARF**。
這句話常駐在資料集標籤上，不是等使用者按下 Export 才告知。

---

## 心智模型

引擎依「這張卡吐什麼型別」分三段，這同時是快取切點與驗證順序：

```
【影像段】把圖變乾淨、可比  →  【算法段】從圖量出數字  →  【ADC 判定】score → bin → 寫回 KLARF
```

使用者看到的則是另一個軸 —— 依「想解決什麼問題」分六階段：

```
Input → Enhance → Region → Compare → Measure → ADC
```

兩個軸各有用途，不合併；詳見 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。
ADC 判定不是卡片，而是 recipe 上的 score 運算式與 bin 規則。

**畫布上的每一條線都是使用者拉的。** 影像流的身分是 `(節點, 埠)` 而非全域名稱；
一個輸入埠只能接一條線，接錯會在 `validate` report `ambiguous-input`。
這條不變量的代價與由來記在 [`docs/PITFALLS.md`](docs/PITFALLS.md)。

---

## 目前的範圍界線

Phase 1（讓數字可信）已於 2026-08-16 收斂，現階段依
[`docs/ROADMAP.md`](docs/ROADMAP.md) 推進 Phase 2。使用者定調的順序是
**先把引擎做對，再回頭做產品化**，因此以下兩件事**目前刻意不支援**，
不是遺漏：

- **未附範例 recipe**，Studio 的「用範例資料試一次」與「Templates…」入口一併收起。
- **不提供 recipe 存檔** —— 無 Save Recipe…、無 Ctrl+S。**讀取仍在**，CLI 不受影響。

開關集中在 `d4t/ui/scope.py`，這也是「暫時不給看」的唯一去處。

---

## 安裝與執行

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt                    # 含 PySide6

python -m d4t gui                                  # 開啟 Studio
```

CLI（下列流程不需真實廠內資料）：

```bash
python tools/make_sample.py /tmp/lot --n 100       # 產生合成 KLARF ＋ patch TIFF
python -m d4t steps                                # 列出所有步驟卡片
python -m d4t validate <recipe>.json
python -m d4t run <recipe>.json /tmp/lot/LOT_SYN.001 \
    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
python -m d4t runs   --db /tmp/runs.db             # 批次歷史
python -m d4t rescore <run_id> --db /tmp/runs.db --threshold 60 --save
python -m d4t export  <run_id> --db /tmp/runs.db --mode annotate \
    --klarf-out out.001 --csv feat.csv --excel report.xlsx
```

> repo 內未附現成 recipe（見上）。若僅需確認引擎可運作，
> `python tools/doctor.py` 會以內建的最小 pipeline 端到端跑完一顆並自檢環境。

**受限環境**：目標機器可能無網路、無 git。取得程式碼見
[`docs/NO-GIT-SETUP.md`](docs/NO-GIT-SETUP.md)，離線安裝相依套件見
[`docs/OFFLINE-INSTALL.md`](docs/OFFLINE-INSTALL.md)。
`tools/` 底下的 bootstrap 工具因此一律維持 **stdlib-only**。

---

## 開發

```bash
pip install pytest
QT_QPA_PLATFORM=offscreen pytest -q tests --ignore-glob="*test_ui_*"   # 核心，約 25 秒
```

UI 測試**逐檔各起一個行程**（整套塞進同一個行程會因 Qt 記憶體累積而慢到跑不完）：

```bash
for f in tests/test_ui_*.py; do QT_QPA_PLATFORM=offscreen pytest -q "$f"; done
```

每次改動之後（於具備 git 的機器）：

```bash
git add -A && python tools/release.py && git add -A
```

`git add` 必須在前 —— 兩份產出都由 `git ls-files` 產生，尚未 add 的新檔案會
**安靜地不在裡面**；`tests/test_offline_tools.py` 會擋住過期的產出。

新增步驟卡片的做法見 [`CLAUDE.md`](CLAUDE.md) §3：新增一個 `Step` 子類別並
`@register_step`，**UI 與引擎皆無需修改**，卡片庫會自動出現。

---

## 設計不變量

以下每一條都有測試守門：

- **`d4t/core` 不得 import Qt**；UI 僅透過 callback 與 core 互動。
- **Python 3.9 相容語法**（廠內機器可能為舊版）。
- 每個 `ParamSpec` 的 `help` 必填且須為白話；`register_step` 會拒絕未填者。
- 檔案寫入一律 atomic（`.tmp` ＋ `os.replace`）。
- **KLARF 寫回無損**：未被修改的位元組與原檔逐位元組相同。
- **單顆 defect 出錯不得中斷整批**（`run_defect` 不 raise，回傳 `ok=False`）。
- **repo 內不得出現未遮蔽的廠內識別碼**，測試 fixture 亦同。

其餘慣例：

- **ROI 座標**：正規化座標（`NamedROI`）為正典；像素矩形一律 `(x, y, w, h)`。
- **SNR 正負號**：`snr_signed = (μ_target − μ_ref) / σ_ref`（e-beam 定義）為唯一正典
  primitive（`algo/snr.py`）；`roi_snr` 同時回報 signed 與 abs。
- **Vendoring**：每個 vendored 模組於檔頭註明來源專案、原始檔案與改動清單。

---

## 文件索引

每個主題只有一個出處；要引用請連結，不要複製一份。

| 主題 | 文件 |
|---|---|
| **環境限制**（兩台機器、剪貼簿是唯一通道）—— **動手前先讀** | [`AGENTS.md`](AGENTS.md) |
| 開發手冊：鐵則、加卡片、開發流程 | [`CLAUDE.md`](CLAUDE.md) |
| 架構：心智模型、資料模型、目錄結構 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 進度與 phase 計畫 | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| 已知的坑（30 條以上，只增不減） | [`docs/PITFALLS.md`](docs/PITFALLS.md) |
| 設計緣由：需求訪談結論、名稱由來、六個來源專案 | [`docs/HANDOVER.md`](docs/HANDOVER.md) |
| 廠內待驗證假設、受限機器部署 | [`docs/FAB-VALIDATION.md`](docs/FAB-VALIDATION.md) |
| 上游 GLAS 的介面契約 | [`docs/GLAS-INTERFACE.md`](docs/GLAS-INTERFACE.md) |
| 逐輪決策與理由 | [`SESSION_LOG.md`](SESSION_LOG.md)、[`docs/history/`](docs/history/) |

---

## 來源

d4t 的演算法多數自六個既有專案 vendoring 而來，各自提供的內容如下
（完整脈絡見 [`CLAUDE.md`](CLAUDE.md) §6 與 [`docs/HANDOVER.md`](docs/HANDOVER.md) §3）：

| 來源 | 提供了什麼 |
|---|---|
| **KLIP** | KLARF 1.2／1.8 無損引擎、TIFF page 對應、健檢 lint |
| **GLAS** | fine align、SEM loader、DAG 拓撲排序、ROI label map 契約 |
| **MMH** | recipe 架構原型、批次引擎模式、次像素邊緣定位、品質指標、KLARF 寫回 |
| **PEAR** | GLV 統計 metric bank、Tukey 離群、η²／Cohen's d、CJK-safe 影像載入 |
| **cell-period-estimator** | 週期估測、Golden Cell 堆疊、ghosting 分數 |
| **Perspective-Combination (Fusi³)** | 正規化、直方圖匹配、多後端對位、SNR map、blob 分割 |
