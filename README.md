# ADEPT — Auto Defect Evaluation Pipeline Tool

> 彈性、多步驟、**任何 Inspection 站點都適用**的 ADC（Auto Defect Classification）工具。
>
> 讀半導體 E-beam Inspection 的 patch 影像（test + ref）或 Review SEM 單張影像 +
> 對應的 KLARF，用「步驟卡片組 pipeline」把腦中的想法變成算法，對每顆 defect 算分、
> 調參看整批分佈、再把結果寫回 KLARF。
>
> **核心理念：站點差異封裝進 recipe，不封裝進程式碼。**
> 傳統 PADC / RADC 每個站點都要工程師重寫一份 code；ADEPT 讓不會寫 code 的人
> 也能用滑鼠把想法組成算法，產出可量化的證據。

| | |
|---|---|
| **輸入** | KLARF + multi-page patch TIFF（EBI）｜KLARF + per-defect 影像（Review SEM）｜純資料夾 |
| **組裝** | 17 張步驟卡片、n8n 式節點畫布（拉線、拖卡、雙視窗）；使用者視角六階段：Input → Enhance → ROI → Compare → Measure → ADC |
| **輸出** | 無損寫回 KLARF（class / bin / DSIZE）｜Top-N 新 KLARF｜CSV / Excel 報表｜feature vector（ML 備料） |
| **介面** | PySide6 Studio 視覺化編輯器 ＋ CLI（可排程、可腳本化） |

## 文件在哪（每個主題只有一個家）

| 你要知道的 | 去哪 |
|---|---|
| **環境限制**（兩台機器、剪貼簿是唯一通道）—— **動手前先讀** | [`AGENTS.md`](AGENTS.md) |
| 怎麼動手：鐵則、加卡片、開發流程 | [`CLAUDE.md`](CLAUDE.md) |
| 架構：心智模型、資料模型、目錄結構 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 進度與 phase 計畫 | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| 已知的坑（30+ 條） | [`docs/PITFALLS.md`](docs/PITFALLS.md) |
| 為什麼長成這樣（訪談結論、六個來源專案） | [`docs/HANDOVER.md`](docs/HANDOVER.md) |
| 廠內待驗證的假設、受限機器部署 | [`docs/FAB-VALIDATION.md`](docs/FAB-VALIDATION.md) |
| 沒有 git 的機器怎麼取得程式碼 | [`docs/NO-GIT-SETUP.md`](docs/NO-GIT-SETUP.md) |
| 離線安裝相依套件 | [`docs/OFFLINE-INSTALL.md`](docs/OFFLINE-INSTALL.md) |
| 逐輪的決策與理由 | [`SESSION_LOG.md`](SESSION_LOG.md)、[`docs/history/`](docs/history/) |

## 現在的狀態

**M0–M7 完成 ✅（v1 功能齊備 + UI/UX 大改版）；engine 精修中。**
逐項見 [`docs/ROADMAP.md`](docs/ROADMAP.md)。

兩件**目前刻意不支援**的事（不是漏掉的，engine 做完會回來）：

- **沒有範例 recipe**，Studio 的「用範例資料試一次」與「Templates…」入口收起來了。
- **不能存檔 recipe** —— 沒有 Save Recipe…、沒有 Ctrl+S。**讀取仍然在**，CLI 照跑。

## 跑起來

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt                    # 含 PySide6

python -m adept gui                                # 開 Studio

# CLI（不需真實資料）
python tools/make_sample.py /tmp/lot --n 100       # 產合成 KLARF + patch TIFF
python -m adept steps                              # 看所有卡片
python -m adept validate <recipe>.json
python -m adept run <recipe>.json /tmp/lot/LOT_SYN.001 \
    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
python -m adept runs --db /tmp/runs.db             # 批次歷史
python -m adept rescore <run_id> --db /tmp/runs.db --threshold 60 --save
python -m adept export <run_id> --db /tmp/runs.db --mode annotate \
    --klarf-out out.001 --csv feat.csv --excel report.xlsx
```

> repo 裡沒有現成的 recipe（見上）。只是想確認引擎跑得動的話，
> `python tools/doctor.py` 會用內建的最小 pipeline 端到端跑一顆。

## 開發

```bash
pip install pytest
QT_QPA_PLATFORM=offscreen pytest -q tests --ignore-glob="*test_ui_*"   # 核心，~25s
```

UI 測試**一個檔案一個檔案跑**（整套塞進同一個行程會因 Qt 記憶體累積而慢到跑不完）：

```bash
for f in tests/test_ui_*.py; do QT_QPA_PLATFORM=offscreen pytest -q "$f"; done
```

改完之後（**家用機**）：`git add -A && python tools/release.py && git add -A`。

## 慣例

- **Vendoring**：每個模組檔頭註明來源專案／檔案與改動清單；六個來源專案各給了
  什麼見 [`CLAUDE.md`](CLAUDE.md) §6。
- **`adept/core` 禁止 Qt import**、**Python ≥ 3.9 相容** —— 兩條都有測試守門。
- **ROI 座標**：正規化座標（`NamedROI`）為正典；像素矩形一律 `(x, y, w, h)`。
- **SNR 正負號**：`snr_signed = (μ_target − μ_ref) / σ_ref`（e-beam 定義）為唯一正典
  primitive（`algo/snr.py`）；`roi_snr` 同時回報 signed 與 abs。
