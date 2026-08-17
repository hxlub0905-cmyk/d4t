# ADEPT Roadmap

**進度與計畫的唯一出處。** 以前這張表同時存在 README、CLAUDE.md、
`docs/plans/F0-master-plan.md` 與 `SESSION_LOG.md` 四個地方，於是四份各自漂移。
要引用進度，連過來，不要再抄一份。

（逐輪的決策與理由仍然在 [`../SESSION_LOG.md`](../SESSION_LOG.md) 與
[`history/`](history/)；這裡只講「做到哪、接下來做什麼」。）

---

## 現在的定位

**engine 還在做。** 使用者 2026-08-16 定調的優先順序是
**先把運算引擎與功能做對做完，再回頭支援「產品化」的那些東西**。
兩個直接後果，看到它們不要以為是漏掉的：

- **範例 recipe 全部拿掉**（`examples/` 已移除），Studio 上的「用範例資料試一次」
  與「Templates…」兩個入口跟著收起來（`ui/scope.py` 的 `SHOW_SAMPLE_ENTRIES`）。
- **存檔 recipe 的功能拿掉了**（2026-08-16）。Studio 沒有「Save Recipe…」、
  沒有 Ctrl+S，`Recipe.save()` 也移除了。**讀取仍然在** —— CLI
  `python -m adept run <recipe> <klarf>` 照跑，`tests/fixtures/recipes/` 照用。
  等 engine 收斂了再把存檔做回來（那時要一併決定 recipe 的版本與相容策略）。

---

## Phase 1 —— 讓數字可信（**收斂**，2026-08-16）

後面每一個 phase 都踩在「跑出來的數字是對的」這個前提上，所以它先做。
除了「遇到再說」的 KLARF 變體，項目全部結案。

| 項目 | 狀態 | 說明 |
|---|---|---|
| recipe JSON round-trip 必須是 identity | ✅ 2026-08-16 | 一道遷移靠「參數缺席」判斷，害 `workers=1` 與 `workers=2` 算出不同分數（glv_max 50 vs 43）。已移除並鎖上迴歸測試 `test_a_json_round_trip_changes_nothing` |
| 遷移的鐵則寫進程式碼 | ✅ 2026-08-16 | 只能靠「舊東西在不在」判斷，不能靠「新東西不在」。見 `recipe.py::from_json_dict` 的註解 |
| 準確率接進調參迴圈 | ✅ 2026-08-16 | CLI `run --ground-truth` 印正確率／抓漏／誤殺；Studio 載資料時自動撿 KLARF 旁邊的 `ground_truth.json`，拖門檻即時重算（只重分 bin，不重跑影像）|
| 畫布上的線只有一個作者 | ✅ 2026-08-16 | 加卡不再自動接線；同一個輸入埠上兩條線由 UI 換線 + lint `ambiguous-input` 擋住（F9-7）|
| 分支路徑稽核（F9-8…F9-10） | ✅ 2026-08-16 | 四個「跑得完、有數字、而且是錯的」全部修完並鎖上迴歸測試：快取簽章含線、停用的卡沿線讓路、一對節點可以有好幾條線、快照存得下流的身分。見 [`history/plans/F9-dag-streams.md`](history/plans/F9-dag-streams.md) §12–14 |
| KLARF 變體（廠內假設 #3） | ⏸ | 使用者定調**遇到再說**（2026-08-16）。假設本身仍記在 [`FAB-VALIDATION.md`](FAB-VALIDATION.md) |
| 卡片的數值行為逐張過一次 | ✅ 2026-08-16 | `tests/test_card_invariants.py` 的六條性質**自動套用到 registry 裡每一張卡**：I1 同輸入跑兩次相同、I2 換行程相同、I3 只碰宣告過的東西、I4 快取重放＝全程重算、I5 參數推到上下界不炸也不吐 NaN、I6 換 patch 尺寸照跑。每條都用「把對應的 bug 放回去」驗過會紅 |

### Phase 1 收在哪裡（2026-08-16）

「數字可信」現在有三層守著，加第 18 張卡的人不必記得來補任何一層：

1. **黃金值**（`tools/freeze_golden.py --check`）—— 三組 22 顆 defect 的完整
   feature 表凍住。任何重構的驗收都是「跟改動前逐項相同」。
2. **六條卡片不變量**（`tests/test_card_invariants.py`）—— 自動套用到 registry
   裡每一張卡。
3. **可量化的 KPI**（`run --ground-truth` + Studio 的即時準確率）—— 「判得更準
   還是更差」不再是不可驗證的命題。

這一輪一共修掉 **6 個會安靜算錯數字的 bug**（recipe round-trip、快取簽章看不見
線、分支冷熱不一致、停用外洩隔壁支線、一對節點只存得下一條線、同一個輸入兩條
線），全部有迴歸測試，全部驗過「把 bug 放回去會紅」。

### F10 —— 畫布要符合現實（2026-08-17，Phase 1 的最後一段）

使用者在畫布上實際操作之後，**七項**依序修完（前五項回報、後兩項稽核抓到）：
埠點到的是自己那一顆、剛加的卡前後都是空的、量測卡多連一、剪線＝拿掉來源、
刪卡＝連同線一起刪、改輸出名下游跟著走、`write result to` 打得進去。

真正換來的是一句可驗證的話：**畫布上看得到的，就是引擎真的會做的。**
驗收 `tests/test_ui_f10_canvas_reality.py`（20 條，全部對 registry 裡每一張卡
自動套用）＋ 兩支稽核腳本（11 項不變量）。詳見
[`plans/F10-canvas-tells-the-truth.md`](plans/F10-canvas-tells-the-truth.md)。

**Phase 1 到此收斂。接下來是 Phase 2（功能補完 —— 與原 Phase 3 對調）。**

## Phase 2 —— 功能補完（**2026-08-17 與原 Phase 3 對調**）

使用者定調：「**我想優先做好內部的每個功能。**」原本排在這裡的產品化
（手冊、範例庫、標注介面）往後挪一格 —— 理由跟 Phase 1 先做的理由是同一個：
對著還會長的東西寫說明書、做範例，寫完就得重寫。而範例 recipe 現在**刻意
一份都沒有**（使用者：「現在還沒有打算給人用，就我自己測試」）。

計畫書：[`plans/F11-phase2-features.md`](plans/F11-phase2-features.md)（含現況稽核、
排序理由、每一項的規格草案與待定調的三題）。

**演算法一律重寫、不照抄 vendored 的**（使用者 2026-08-17：「我基本會想要優化改良」）。
範圍見計畫書 §2.1 —— 確認之前不動任何演算法檔案。

| 項目 | 說明 |
|---|---|
| mask 進來（原 GDS ROI 定位） | **ADEPT 不解析 layout**（2026-08-17 定調）：GDS/OASIS 留在上游 [GLAS](https://github.com/hxlub0905-cmyk/GLAS)，ADEPT 只吃它產出的 mask image、與 defect 一一對應（樣本之後提供）。出口契約已經留好（見 [`ARCHITECTURE.md`](ARCHITECTURE.md)），下游零改動 |
| `snr_map` 多來源 + 產流卡的命名契約 | F10-3 只做了「只吐數字」的量測卡；會產生新流的卡要先決定「一條流一張輸出圖」怎麼命名（見 [`plans/F10-canvas-tells-the-truth.md`](plans/F10-canvas-tells-the-truth.md) §6）。**PCA Ref、BSE/SE 融合、會吐圖的 Region Stats 都踩在這條規則上** |
| Blob 分割 + 離群旗標（**新發現的缺口**）| 演算法在（`algo/blob.py`、`algo/stats.py`）卻**沒有卡片**，而 `cd_measure` 的警告叫使用者「run Blob segment first」、`overlay` 的主 blob 紅框兩條路都沒有生產者。詳見計畫書 §1.1 |
| Region Stats / FFT 卡 | v1 移出的。FFT 那一半可以接 `algo/period.py` 既有的 rFFT |
| 多通道（BSE + 4×SE 同 TIFF）→ PCA Ref / 融合 | 頁數機制已支援任意頁，但**頁的名字只能在 ingest 層決定，recipe 摸不到**（現在叫 `test, ref, img3…`）。前提是廠內事實，見計畫書 §6.1 |
| ML Classify 卡 | **Phase 2 後半**（2026-08-17 定調）。吃已經匯得出來的 feature vector CSV；相依策略到時候再定 |

## Phase 3 —— 讓人用得起來（原 Phase 2）

engine 與功能收斂之後才有意義。

| 項目 | 說明 |
|---|---|
| ground truth **標注介面** | 讀答案卷與即時準確率已經在（Phase 1），缺的是**在 Studio 裡標**：現在還是要人另外準備一份 JSON／CSV |
| 存檔 recipe 做回來 | 連同版本與相容策略一起想 |
| 範例 recipe 庫 | 使用者的原話是「等 APP 完成再給範例」。回來時把 `SHOW_SAMPLE_ENTRIES` 打開 |
| 使用者手冊 | 目前所有文件都是寫給開發者的。目標使用者是不寫 code 的製程／設備工程師 |
| 快速參考卡 PDF | M6 欠著的 |

## Phase 4 —— 規模

多 lot 趨勢｜recipe A/B 比較｜共用 recipe library｜自由 DAG 畫布（雙 reference AND）｜
自然語言 → recipe 草稿。

---

## 已完成

| Milestone | 狀態 | 內容 |
|---|---|---|
| F8 | 🔨 | **純規則 ROI 定位 + mask 通道 + UI 第二波**（詳見 `SESSION_LOG.md` 逐輪紀錄與 `docs/plans/F8-rule-based-roi.md`）。已完成：`roi_cross`（條紋交會處放框、一鍵整批量 pitch）、`roi_mask` + Normalize `use_within`（見 §2.5）、參數說明搬 tooltip、D 案版面（畫布佔中上、設定拿大頭、**畫布彈出視窗**兩窗互通）、右鍵平移、手動佈局保留（tidy 才重排）、route 虛線退役（排版仍吃隱含順序）、量測卡預覽疊區域框、`multi_choice` 參數型別（glv_stats 統計量用勾的）、subtract 預設 `b=ref`（patch 天生對齊；舊檔載入遷移補 `ref_aligned` —— **改預設值必附遷移**） |
| M0 抽庫 | ✅ | 從 KLIP/GLAS/MMH/PEAR/CPE/Fusi³ vendoring 演算法資產 |
| M1 引擎 | ✅ | Context/Step/Recipe DAG/表達式/14 張卡/合成資料/CLI |
| M2 批次 | ✅ | ProcessPool + 影像段快取 + SQLite 歷史 + rescore |
| M3 Studio | ✅ | PySide6 四區塊視覺化編輯器 |
| M4 雙輸入 | ✅ | RSEM 單張 ingest、輸入型別分流、Golden Cell + Cell 週期估測卡（`period.choose_origin` 相位搜尋已補完）。驗收達成：一份 recipe 同時吃 EBI patch 與 RSEM，跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1%（那份 `dual_route_basic.json` 現在留在 `tests/fixtures/recipes/`）|
| M5 Gallery+Export | ✅ | Gallery（虛擬捲動、排序、直方圖點 bar 篩選）；KLARF 三種寫回模式（就地無損／另存含 ADCSCORE+ADCCLASS／Top-N）+ 寫回前預覽變更；CSV/Excel 報表（含抓漏率/誤殺率）；overlay；`fab_probe/` 三支探測腳本；CLI `adept export` |
| M6 推廣包 | ✅ | 離線安裝三件套（`tools/fetch_wheels.py` / `install_offline.py` / `doctor.py`，全 stdlib-only）、首啟導覽 + 範本庫對話框。**5 份範例 recipe 已於 2026-08-16 全部移除**，連帶收起「用範例資料試一次」與「Templates…」兩個入口（`ui/scope.py`）。快速參考卡 PDF 暫緩（移到 backlog） |
| M7 UI/UX | ✅ | A 組防呆 + **UI 全英文**（`tests/test_ui_english_only.py` 鎖住）。F7 全數完成：patch-only 收斂（`ui/scope.py`）、中性色/平面主題 + 暗色、卡片依流程階段分組 + 搜尋 + 前置條件 badge、**Region 段（具名 ROI）**、Results 視窗、**節點畫布**。計畫書 `docs/history/plans/F7-canvas-and-taxonomy.md` |
| F7-24 | ✅ | **版面把空間給對的東西**（來自一張跑起來的截圖）：**開 recipe 自動 fit**（`fit_later()` 等畫布真的有尺寸才算；`fit` 加上限 1.0 —— `fitInView` 會把兩張卡的 pipeline 放大成三倍）、**兩個下拉框不再吃掉整列**（以前各佔八百多 px 去裝「1」與「diff」，而 `ebi_patch · defect 1 / 24` 被擠掉）、**刪掉死掉的 `PipelinePanel`**（F7-6 的畫布取代了它，但每一輪主題工作都還要繞過它）、**工具列不再是七顆一樣的白鈕**（亮色 `toolbar` 以前與 `bg_surface` **同為 `#ffffff`**；五顆文字鈕各配一個自繪圖示；`Export…` 拿 accent 外框 —— 整條工具列只有兩顆有顏色，而它們正好是要按的那兩顆）。**`Spread` 面板補上軸與圖例**（刻度畫在每一排自己身上 —— 每排單位不同，不能共用一句「0 → 255」；圖例畫一次，並明講右邊那欄是**這一顆**的值）、**往回走的線不再橫掃畫布**（換行那條線以前控制點水平推 `|Δx|*0.5`，一條線甩七百多 px；改成水平只推固定的 46px、量交給垂直方向）。**第二輪（對著自己截的圖再看一次）**：**fit 的下限從 0.45 改成量出來的 0.7**（十張卡落在 52%，卡片副標是一團灰；52/60/70/80/100% 逐級看過，副標要到 70% 才回來）、**塞不下時靠開頭對齊不置中**（`fitInView` 置中會把第一張跟最後一張同時切掉，而 pipeline 是從左往右讀的 —— 這條是前一項造出來的問題，**一輪改動要再截一次圖**）、**`Run trial` 與 `▾` 包成分段控制項**（1px 縫 + 內側直角）。驗收 `tests/test_ui_f7_24_layout.py`（13 條）。計畫書 §28、§29 |
| F7-23 | ✅ | **按鈕要說得出自己現在是什麼狀態**（試用回饋第九輪）。第一輪**只動 `theme.py`**、呼叫端零改動：**八種按鈕全部補上焦點框**（以前只有「沒有 objectName 也沒有 variant」的那一種有 —— 見 §7 新增的兩列；新 token `focus_ring_inverse`，因為框要跟按鈕自己的底對比）、**disabled 的 primary 留住 accent 淡底**（以前跟一般鈕同一片灰，於是沒載資料時「該按哪一顆」沒有答案）、**圓角收成 `radius_sm/md/pill` 三個 token**（原本六個值散在 QSS 各處）、刪掉**寫了兩次的 `QToolBar::separator`**（贏的是沒有註解的那一份）。`Run trial ▾` 的下拉區量下來 QSS 做不到（見 §7），移到第二輪。**第二輪**：小按鈕的**六種尺寸收成一種**（`widgets.small_button()` 只說形狀 `square`/`wide`，邊長由 `control_sm` 決定；`kind="icon"` 給浮在畫布／影像上的那幾顆一個自己的底）、**垂直節奏統一**（重要性只用水平 padding 表達 —— 以前 primary 高 2px，空白狀態下兩顆並排的鈕對不齊）、**游標從「每個人自己記得」變成規則**（`apply_button_cursors()` 掃一次；以前一半的按鈕滑過去沒有變手指）、**`Run trial ▾` 拆成兩顆真的按鈕**。驗收 `tests/test_ui_f7_23_buttons.py`（13 條；對第一輪前 7 紅、對第二輪前 5 紅），含一條靜態掃描擋 `setFixedSize` 長回按鈕上。**第三輪**：**三個元件不再自己組色盤**（`_Chip` / `StageButton` / `LibraryItem`+`libBadge` 搬進 QSS —— 以前換膚要靠有人記得逐顆重套，而帶 badge 的卡片庫列那條路沒被走到，會留在上一個主題的灰色；真正每個實例不同的階段色仍留在 widget）、**`pressed` 真的跳一階**（新 token `pressed_bg`；以前與 hover 只差 ΔL*≈3.5）、**最小的按鈕不再有最大的反應**（`#cardButton:hover` 從動三件事收成兩件）、**`QPushButton` 補上 `:checked`**。順帶抓到 `radius_pill` 的 `999px` 在 Qt 是**方角**（見 §7）。**第四輪**：**按鈕上的字元圖示改自繪**（`widgets.draw_glyph_icon()` 14 個 + `IconButton`；`⤢`(U+2922)、`⌗`(U+2317)、`↶↷`(U+21B6/B7) 在廠內的 Windows 上 Segoe UI 根本沒有，退字型會讓同一排按鈕每顆字大小與 baseline 都不同，最壞是豆腐框 —— 而開發機看不到）。圖示顏色取 `palette()` 的 `ButtonText`（Qt 從 QSS 的 `color` 解析），換膚與變灰自動跟著；**主題鈕的實心半邊會隨目前主題翻面**，以前兩個主題長得一樣。刻意**不**碰 `−↑↓×` —— 那幾個 Segoe UI 有，一起畫掉只是多改動。計畫書 §27。|
| F7-22 | ✅ | **畫布再往 n8n 靠一步**：**參數表預設收起、雙擊卡片才攤開**（畫布因此拿到整欄；`params_open()` 追明確狀態）、**線上 hover 出現斷開 ×**（虛線不給 —— 它刪不掉）、**「排整齊」按鈕**（放縮放鈕旁邊：兩者都只動「怎麼看」）、**卡片庫可以拖到畫布**（自訂 MIME，不是純文字）。計畫書 §26 |
| F7-21 | ✅ | **畫布上接得出「兩條都做」＋ 直方圖看得懂**（試用回饋第八輪）：同一對節點的**第二條線改成累加**（`image_keys` 才累加；`subtract` 的 a/b 這種角色埠仍然取代。而且**第一條線是取代** —— 卡片預設的 `streams="test"` 是規格預設值不是使用者拉的線，第一條就累加的話他拉一條會得到兩條）、**並排預設左 test 右 ref**、**並排時一條流一張直方圖**（`set_context` 多 `shown_streams`）、**直方圖標出軸與圖例**（`gray level` / `pixels`，圖例改成畫一段線＋一塊方塊，不再用 `outline = before` 那種要先翻譯的字）。順手修掉 F7-20 的回歸：`_default_stream` 拿 `"test,ref"` 整串去比流名比不到，會掉回 writes 最後一項 → 點 Normalize 跳到 ref。計畫書 §25 |
| F7-20 | ✅ | **正規化那一家收成一張卡**（試用回饋第七輪）：Enhance **9 張 → 4 張** —— Normalize（percentile / glv_band / match / local 四選一）、Adjust tone（亮度・對比・gamma・曲線・反相，**不是**四選一，是可以同時做的幾個旋鈕）、Denoise、Remove background。新增 `ParamSpec.show_when`（參數跟著方法出現／消失，取代 help 裡那句「這個方法用不到」的道歉）與 `Step.resolve_requires_ref`。順帶做掉 F7-19 的引擎那一半：`MultiStreamStep` 讓一張卡吃 N 條流（`streams`），`range_from` 的順序陷阱因此消失。**畫布那一半還沒做**（輸入側仍是單一埠）。舊 recipe 由 `recipe._migrate_merged_cards` 換名，分數逐項相同。計畫書 §24 |
| F7-19 | ✅ | 引擎於 F7-20、畫布於 F7-21 完成。原始計畫與復盤見下一列與 §23 |
| F7-19（計畫） | ✅ | **一張卡是「一次處理」，不是一條流**（試用回饋第六輪）：卡片頭尾都變成每條流一個埠，接幾條就處理幾條（N 進 N 出）。**這不是 `also_apply` 回來** —— F7-18 保護的不變量是「畫布不能說謊」，而這一輪的第二條流有真的線、真的埠。順手解掉 §22.7 全部三條未解。**不做卡片分類、不新增參數**：既有的 `range_from` 原樣保留（它已經是畫布上一條線），要讓兩條流吃不同處理就放兩張卡 —— 計畫第一版為此發明了 `measure_on` + 三類卡，被使用者當場擋下來，理由與復盤寫在 §23.3。計畫書 §23；引擎已完成於 F7-20，剩畫布的輸入埠 |
| 單位 | ✅ | **量測一律 pixel，換算搬到輸出**（2026-07-30 使用者決定）：`cd_measure` 拿掉 `cd_x_nm` / `cd_y_nm` / `area_nm2`（它們在沒有 `nm_per_px` 時**每一顆都是 0**，而那個欄位從來沒有來源），改吐 `cd_x_px` / `cd_y_px` / **`area_px`**（新的）。nm 換算由 Export 精靈的 `× scale` 一格輸入承接（`klarf_out` 的 `size_scale`、CLI `--size-scale`，預設 1 = 原樣寫 pixel），並寫進 plan.notes。同日確認 **page→channel 就是 test/ref**，兩條待驗證假設結案。見 §8 |
| F7-18 | ✅ | **影像流是節點的事，不是控制列的事**（試用回饋第五輪）：拿掉輸出埠上常駐的「+」（入口收回卡片庫，接線與影像流由 `add_card_after` 承接）、**虛線給自己的色相**（`canvas_edge_implicit`；同色淡一點只說得出「比較不重要」）、**一張卡一條流**（七張 Enhance 卡的 `also_apply` / `anchor` 拿掉；`percentile_norm` / `glv_mask_norm` 補 `range_from` 保住「兩張圖還比得起來」）、**連線指定影像流**（`edge_added` 帶出發埠；同一對節點再拉一條是「我改變主意了」）。舊 recipe 由 `recipe._migrate_also_apply` 展開成多張卡，分數逐項相同。計畫書 §22 |
| F7-17 | ✅ | **右下角變成「這張卡自己的儀表」**（依 `Step.key` 註冊，沒註冊的用原本的特徵表 → 加新卡不必動 UI）。四個：`load_patch` 的 **page→stream 對應**（廠內假設 #1 第一次看得見）、Enhance 九張卡的 **before/after 直方圖 + 削平計數**（新增 `Context.track_changes`，**只有預覽打開**）、`align` 的**整批位移散佈圖 + 搜尋半徑框**、五張量測卡的**整批分布 + 這一顆站在哪**。第二批：`roi_profile` 的曲線面板**收進同一個機制**（原本是平行的另一條路）、`roi_template` 的**三道閘門各自的門檻線**（match / certainty / **structure** 三種失敗的處置完全不同）。計畫書 §21 |
| F7-16 | ✅ | **四張安全網**：**復原/重做**（存整份快照，不是反向操作；滑桿一次拖曳算一步）、**快捷鍵**（Ctrl+O/S/R/Z/0/±/F/←→，全照 OS 慣例，並寫進 tooltip）、**關窗前問「還沒存」**（存檔失敗不算可以關）、**跑到一半可以停**（引擎本來就支援，只是按不到；已跑完的留著，而且訊息講「stopped」不是「finished」）。計畫書 §20 |
| F7-15 | ✅ | **畫面上的字要能被讀完**（C 組）：參數說明**收成一行、用到才攤開**（錯誤永遠攤開；`hint_text()` 回全文）、沒資料時最大的那一塊給「Open KLARF… / Try it with sample data」、**狀態列的拒絕變紅字**（`_status(msg, "error")` + QSS，逐條列舉哪些算 error）。計畫書 §19 |
| F7-14 | ✅ | **從畫布上就做得完一條 pipeline**（B 組）：輸出埠上的 **「+」**（清單只列**現在就接得上**的卡，依階段排序；按哪個埠決定新卡做在哪條流上；接出來的是實線）、**畫布縮放控制**（左下四顆 + 百分比，夾在 25–300%）、**節點副標印 `吃什麼 → 吐什麼`**（Region 卡取 `resolve_regions_out`；重複的卡才帶 id）。計畫書 §18 |
| F7-13 | ✅ | **控制項要看得出自己是什麼**（試用回饋第四輪 A 組）：下拉選單的箭頭（0 個畫素的 QSS 坑）、`template` 參數型別（按鈕 + 摘要，不是文字框，入口從預覽面板搬回參數列）、`Step.configuration_issues()` → lint `not-configured` → **畫布上的警示標記**、工具列按鈕看起來像按鈕。計畫書 §17。**未做**：n8n 的輸出埠 `+`、畫布縮放控制、節點副標印關鍵參數 |
| F7-12 | ✅ | **ROI 定位第二批：Golden Cell 模板**。匯入一張原大圖 → 量週期 → 疊出一個完整 cell 當模板 → 在 cell 上標一次框，每顆 patch 用 NCC 對回相位再把框搬過來。patch **小於**一個週期沒關係（是把小 patch 滑進大模板，不是兩張小圖互相對位）。模板凍進 recipe（base64 純文字，不是路徑）。新卡 `roi_template` + `ui/template_dialog.py`。三道閘門見 §7 表。計畫書 §16。**未做**：用當次的大圖對凍住的 GC 做健檢 |
| F7-11 | ✅ | **ROI 定位第一批**：量測卡 `output_prefix`（多區域的前置；Studio 挑了區域自動填名）、**投影定位卡** `roi_profile`（壓成曲線→找轉折→挑一段，可一次吐出鄰段）、**曲線面板**、**區域跨顆檢視**（把框畫到前 N 顆縮圖上，可只看定位失敗的）。定不出來就退回整張圖並標 `locate_ok=0`。順手修掉「過期的背景預覽會蓋掉新畫面」。計畫書 §15 |
| F7-10 | ✅ | **route 的隱含順序畫成虛線**（畫布上「沒有線」以前不代表「沒有連接」，而使用者看到的是九張互不相干的卡）；**Enhance 補齊空間性 artifact**：新卡 `flatten`（背景梯度／掃描線條紋／top-hat／black-hat 五個方法一張卡）與 `local_contrast`（CLAHE），邊緣保留去噪塞進既有 `denoise`、雙流運算塞進既有 `subtract`。計畫書 §14 |
| F7-9 | ✅ | 試用回饋第三輪：**六個階段六個顏色**（`theme.group_hex`，ΔE ≥ 25 且明度差 ≤ 15，兩條都有測試鎖）、**埠座標系 bug**（殘影＋「後面沒有圓框」同一個因）、**開窗就有 Input 起手卡**、**`image_keys` 參數型別**（`also_apply` 從自由文字變成勾選框）+ `ParamSpec.label`、**點卡片不再跳到 ref**、**具名 ROI 納入 lint** + Studio 試跑前先 lint。計畫書 §13 |
| F7-7 / F7-8 | ✅ | 試用回饋兩輪：階段大按鈕 → **直式 icon rail**（卡片區收起來時整欄只剩 rail）、載入/試跑進度條、Brightness/Contrast + **Gamma / Curve** 卡、**每個有上下界的參數配滑桿**、**自訂色調曲線**（保單調插值）、**並排比對兩條影像流**（連動縮放平移）、畫布 n8n 化（圖示磚／點陣底／方向箭頭／每條影像流一條線）。詳見計畫書 §12 |

v2 backlog：快速參考卡 PDF、自由 DAG 畫布、ground-truth 標注 + 混淆矩陣、ML Classify 卡
（吃現成的 feature vector CSV）、PCA Ref、Region Stats/FFT、BSE/SE 多通道融合。
