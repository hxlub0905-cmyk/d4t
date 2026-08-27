# d4t Roadmap

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
  ⚠ **這一條有一半回來了**：2026-08-26 起 `recipes/` 底下有出貨的 recipe
  （目前一份：characterization），走 `Open recipe…` 那條路。它跟舊的
  `examples/` 差在**有測試守著**（`tests/test_shipped_recipes.py`）——
  舊的那批就是因為沒人測而爛掉的。範本庫那個入口仍然關著。
- ~~**存檔 recipe 的功能拿掉了**（2026-08-16）~~ →
  **2026-08-26 做回來了**（F34）。`Recipe.save()`、工具列的「Save recipe…」、
  `Ctrl+S`（存回原檔）與 `Ctrl+Shift+S`（另存）都在，標題列的星號是「還沒存」
  的常駐訊號。拿掉的理由是「先把整個 engine 用好」，而 Phase 1 同一天就收斂了
  —— 那個前提到期。計畫書：[`docs/history/plans/F34-save-recipe.md`](history/plans/F34-save-recipe.md)。

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
驗收 `tests/test_ui_canvas_invariants.py`（20 條，全部對 registry 裡每一張卡
自動套用）＋ 兩支稽核腳本（11 項不變量）。詳見
[`history/plans/F10-canvas-tells-the-truth.md`](history/plans/F10-canvas-tells-the-truth.md)。

**Phase 1 到此收斂。接下來是 Phase 2（功能補完 —— 與原 Phase 3 對調）。**

## Phase 2 —— 功能補完（**2026-08-17 與原 Phase 3 對調**）

使用者定調：「**我想優先做好內部的每個功能。**」原本排在這裡的產品化
（手冊、範例庫、標注介面）往後挪一格 —— 理由跟 Phase 1 先做的理由是同一個：
對著還會長的東西寫說明書、做範例，寫完就得重寫。而範例 recipe 現在**刻意
一份都沒有**（使用者：「現在還沒有打算給人用，就我自己測試」）。

計畫書：[`plans/F11-phase2-features.md`](plans/F11-phase2-features.md)。

**做法是「逐段逐卡」**（使用者 2026-08-17）：從左側卡片庫的順序一步一步往下
（F16 起是 Input → Enhance → ROI → Measure → Compare → ADC → Output；F24 §5 之後
是七段，Algo 解散進判定），**每張卡的預期功能、
UI 介面、設定放哪都要先討論過**才動手。所以計畫書是**議程**不是待辦清單，
而這個 phase 的**週期會拉很長**（新功能 + 完善舊功能）。

兩條貫穿整個 phase 的定調：

- **演算法一律重寫、不照抄 vendored 的**（「我基本會想要優化改良」）。
  範圍見計畫書 §7.1 —— **確認之前不動任何演算法檔案**。
- **d4t 不解析 layout**：GDS/OASIS 留在上游
  [GLAS](https://github.com/hxlub0905-cmyk/GLAS)，d4t 只吃它匯出的 label map
  （＋合成 gray、alignment offset），join key 是 KLARF `DEFECTID`。
  契約與「上游要小改什麼」全部在 [`GLAS-INTERFACE.md`](GLAS-INTERFACE.md)。

| 段 | 缺什麼 |
|---|---|
| **Input** | ✅ **收斂 2026-08-17**（Input-0…4）：多入口（`Step.is_source`）、`channel_map`（這一顆的第幾張叫什麼）、`tiff_stack`（大 TIFF 沒有 KLARF）、四種輸入的入口做齊、**Input 卡按 source 拆成兩張**（`load_patch` / `load_single` —— 兩張都不看資料型別，畫布因此不說謊）。**範圍：patch + RSEM**（多通道擱置）|
| **Enhance** | ✅ **收斂 2026-08-17**（Enhance-1…3）：**值域變成明講的契約**（實測 `stripes_h` 吐 261.5，會活到後面某個 `to_uint8` 才被壓掉）＋ `clip_frac`；三個新方法（`flatten` 的 median 背景估計、`denoise` 的 `hot_pixels`、`normalize` 的耐離群 `zscore`），**一張新卡都沒開**；五個面板輔助（核心大小畫在影像上、削平的整批走勢、曲線墊直方圖、磨掉幾個 σ、兩條流還有多像）；兩支 lint（`uneven-treatment` / `card-order`）。**融合卡（PCA Ref、BSE·SE quadrant）擱置** —— 使用者 2026-08-17：「我決定我暫時不做 multi channel，暫時 focus 在 patch 跟 RSEM Image」|
| **Region** | **分三個階段，對應三種 mode（使用者定調 2026-08-17，照難度爬）**：**Region-1 Template ✅ 2026-08-18**（`roi_template` 改成「一張卡好幾個區域、一個區域好幾個矩形」，框在 Golden Cell 上**畫**出來 —— 含 multi add 一次長一整排等距的框；框映到 patch 時整片鋪過去，不再只取離缺陷最近的那一份。尾巴：模板過期健檢還沒做）→ **Region-2 Profile ✅ 2026-08-18**（`roi_cross`：三個下拉改圖示、點曲線就是挑材質，以及**單方向** —— 原本寫死「兩組正交條紋」是需求的形狀不是演算法的形狀，新的 `directions` 讓一張只有 line/space 的 patch 也定得出位置，做法是給沒在用的那一軸一根滿版的條紋，交會的幾何一行都不用改。**「三個框尺寸改成在影像上拖」使用者否決了** —— 那些框是逐顆的結果，拖它等於改輸出；可以用拖的只有所有 defect 共用的那一個物件）→ **兩張卡共用的兩件小事 ✅ 2026-08-18**（`drop_edge`／`edge_margin`：靠邊 n px 內的框自動拿掉 —— 壓在 patch 邊上的框量到的是半截的那一塊，而它照樣吐得出看起來正常的數字；**滿版的那一軸不算靠邊**、**缺陷那一塊永遠留著**。以及**疊框一個區域一個顏色**，跟模板編輯器同一組 —— 一張卡好幾個區域之後，全部畫成藍色就分不出哪塊是 ROI1）→ **Region-3 GDS**（**只做 RSEM**：單張 + KLARF，使用者定調 2026-08-18 —— GLAS 是瞄著 RSEM 大圖對的，patch 太小且 GLAS 那邊沒打通；那一刀讓「給 GLAS 的兩件必要需求」都不需要了。**匯出健檢 ✅**：`tools/check_glas_export.py` 印出可以貼出來的遮蔽報告，四條核心檢查是讀 GLAS 程式碼讀出來的。**第 1／2 步 ✅ 2026-08-18**：`tools/make_glas_export.py`（家用機的合成匯出）＋ `ingest/glas_export.py` 配對 ＋ `load_sidecar` 卡（附加檔住 `DefectItem.sidecars`，不進 `images` —— 混進去 `load_single` 會因為「一顆兩張」而全部載不進來）。順手修掉兩個安靜的錯：換匯出快取不失效、`load_raw` 會把三通道 label 合成灰階把 id 混掉。**第 3／4 步 ✅ 2026-08-18**：`roi_from_mask`（精確拆矩形 —— L 形的 bbox 會框到別的材質；`max_boxes` 預設 8192 是量出來的，真實一層是幾十到約五千個矩形，既有的 64 會安靜砍掉 95%）＋ Studio（`Open GDS export…`、`layers` 的表格、儀表）。新卡 `roi_from_mask` 吃 GLAS 的 label map；每個 layer 切成一堆小矩形 —— 站點的區域本來就都是矩形，所以那是等價不是近似）。出口契約已經留好（見 [`ARCHITECTURE.md`](ARCHITECTURE.md)），下游零改動）→ **Region-4 輸出統一 ✅ 2026-08-18**（三張找 ROI 的卡對**每一個區域**寫同一組五個數字 `present`／`boxes`／`area_px`／`clipped`／`edge_dropped`，使用者：「現在有點像大家資料結構不一樣」。前三個從 ctx 讀回來、不是卡片自己記一份；`clipped`／`edge_dropped` 整個家族共用；`present` 與 `boxes` 刻意會不一致 —— 退回整張圖那個保險是「有東西可以量，但它不是你要的那個」）→ **Region-5 單張大圖 ✅ 2026-08-18**（使用者要第四種「用重複結構鋪 ROI」的卡，**量過之後不必新卡**：Template 餵一張 1000×1000 就得到 625 個框、相位正確、61 ms，差別只在接哪一條流。修掉三個擋路的：`max_boxes` 64 → 8192（同 `roi_from_mask`）、`<name>_clipped` 在 Template 上原本恆為 0、對話框多一顆 `Use the image on screen`。`pattern_ref` 因此沒事做了，先收進 `HIDDEN_STEPS`、2026-08-20 刪掉）。**Region 段到此收斂 —— 四種找 ROI 的方法都在，輸出契約一致。** → **Region-6 兩支收成一張卡 ✅ 2026-08-25（F29）**（使用者：「golden cell 跟 GDS 同樣重要而且他們要能在同張 card 裡（都是接區域 ROI 卡）」。`roi_from_mask` → **`roi_reference`**「Reference regions」，method = `repeating cells`（`algo/period` 量週期 → `algo/golden.tile_coords` 每一格一個框）／`layout layers`（原本的 GDS 那一支）。GDS 那一支**也吐 `_center` / `_others`** 了 —— 當初不吐的理由（大圖上缺陷不保證在正中央）沒有被推翻，當時的答案是 `pick="strongest"`（它去找）；F32 刪掉它之後，大圖上「找最異常」歸 GLV 的逐框比較，這張卡選 `pick="none"` 只放框。舊 recipe 走 `_migrate_roi_from_mask_into_roi_reference`。順手修掉一個安靜的：畫布的區域埠上限數的是**埠**不是區域，一層變三個名字之後 6 就等於「兩層」）。|
| **Compare** | **它不缺卡，缺的是既有那幾張長 method**（2026-08-20 讀 code 讀出來的）：`Image Combination`（原 `Compare two streams`）加 `abs` / normalized `(a−b)/(a+b)`；`align`（在 `HIDDEN_STEPS`）加一個吃 GLAS 算好 offset 的 method。小圖對大圖那張已經有了（`H2H`，原 `Align to other stream`，F15）。**ROADMAP 以前寫的「GLAS 合成 gray 當 ref」不需要新卡** —— gray 由 `load_sidecar` 在 Input 載進來，Compare 只負責對位＋相減。⚠ **`pattern_ref` 已於 F16 刪除**（使用者：「完全沒用」），所以單張影像那條路現在**造不出 ref**。✅ **F15 的配對那一段已於 F33（2026-08-25）續完** —— 見下面「F15 停在哪裡」|
| **Measure** | **Gray level ✅ 收斂 2026-08-21（F18）** ＋ **CD ✅ 收斂 2026-08-21（F19）** —— 見下面兩段。→ **逐框比較 ✅ 2026-08-25（F31/F32）**：GLV 的 each box 長出 `worst_*` 家族（贏家框的座標＋leave-one-out 分數；judge 統計量可選可自訂、畫布上即時預覽贏家 X 標記），報表疊圖畫全部 ROI 框、贏家框內把推分數過線的像素染色（**只畫不吐特徵** —— 吐了 find_defect 就從後門長回來；染色只在 `worst_score >= k` 的顆上出現，正常顆整張安靜）。`find_defect` **刪除**（位置歸 `worst_x/y/w/h`），`pick` 瘦身成 centre/none（`strongest` 刪除 —— 大圖上「找最異常」歸逐框比較）。剩下：離群旗標（跨顆 —— 要 `lot baseline` 那一層）、Region Stats / FFT、`snr_map` 多來源。~~Blob 分割~~ **不做**（使用者 2026-08-20：「不需要 也不要再出現」；F31 T5 連 `find_defect` 帶著它的 `blob_*` 特徵一起刪了）|
| **ADC** | **一張卡都沒有，而且只分得出兩類。** score 是 recipe 上的一個欄位（`bins` 被強制只有 `below`/`above`），`__score__` 是 UI 造的假節點。多類別要先設計資料結構，不是加一張卡 —— 這是整個 app 最大的功能缺口 |
| ML Classify | **Phase 2 後半**。吃已經匯得出來的 feature vector CSV；相依策略到時候再定 |

### Measure 段第一張：Gray level ✅ 收斂（F18，2026-08-21）

一天之內從「只量得出絕對值的陽春卡」走到收斂，六步加五次補課，全部在
[`history/plans/F18-glv.md`](history/plans/F18-glv.md)。留下來的形狀：

* **三個互相獨立的問題**：在哪量（畫布上的線）× 量什麼（Statistics 膠囊）
  × 跟誰比（`reference` 五選一 ＋ 可複選的 Compare their）。以前那是一個
  二選一的 `method`，所以「這塊的平均是 120」與「它比隔壁亮 12」拿不到同一張
  卡上。
* **名字分家族**：`glv_…` 是這一塊自己的灰階，`cmp_…` 是跟參照比出來的，
  統計量落在尾巴（`epi_cmp_delta_q90`）。舊 recipe 的分數表達式自動改寫。
* **面板預覽就有東西**（讀 `ctx.meta`，不是跑完一批的 `trial_results`），
  而參照那條分布疊在同一把尺上 —— 相對量因此是**圖**不只是數字。
* **量得準不準是明講的**：`glv_pixels` 永遠吐、樣本太薄／貼在 0 與 255
  的比例會講出來、算不出來的那一格**不寫**（不是 NaN，也不是 0）。
* **SNR 的分母是框與框之間、不帶正負號**，而且整個 repo 只有一份公式
  （`algo/glv.compare_pixels`）—— 原來那張 `ROI SNR` 卡刪掉了。

**還缺的四件都不在這張卡上**（`lot baseline` 那一層、Measure 段共用的影像
overlay、CSV 欄位排序）—— 見計畫書 §9.0。

### Measure 段第二張：CD ✅ 收斂（F19，2026-08-21）

整張砍掉重做（使用者：「基本上要全部砍掉」）。全部在
[`history/plans/F19-cd.md`](history/plans/F19-cd.md)。留下來的形狀：

* **原子單位從「一個區域」換成「一條量測線」。** 舊的 bbox 是極值統計量 ——
  一顆離群像素 100% 傳進答案，圖再大也不會變準。換成 N 條線之後平均是 CD、
  **σ 就是 LWR**、min 是頸縮、max 是橋接：粗糙度不是另外加的功能，是同一趟的
  副產品。兩條邊各自的 σ 是 LER，而 LER 有、LWR 沒有 = 載台在漂。
* **四個彼此正交的問題**（在哪量 × 沿哪個方向 × 邊界怎麼定義 × 怎麼收），
  **不是四個 method** —— 那種選項每一個都同時綁死三件事。判準是一句話：
  這個參數問的是使用者的樣品，還是問軟體。
* **預設的判準被實測推翻了。** 設計時主張 `fit`（√N），量出來 `threshold` 的
  σ 最小、`gradient` 的偏差最小。兩份說法都留在 `algo/edge` 的檔頭 ——
  下一個人很可能會再推論一次同樣的 √N。
* **三條寫死的規矩**：沒有「要不要次像素」的開關；絕不把畫面或框的邊界當成
  一條邊；量不到就不寫那一格。
* **卡片自動做的每一個決定都變成一個數字**（`cd_axis_deg` / `cd_bright`）——
  這一條是實跑合成 lot 才補上的：`target="auto"` 逐顆挑了不同的極性，於是同
  一欄裡裝著「線寬 6.5」與「溝寬 9.4」兩群。
* **影像上看得到掃描線與邊點**（`ImageView.set_marks` ＋ `Step.overlay_marks`），
  而那是**整個 Measure 段共用**的機制，不是 CD 專用（F18 §9.0 指名的那一件）。

**第二批（無方向那一支）✅ 2026-08-21**：卡片最上面多一個岔路（`shape` =
一條線／一團東西），團那一支走 `algo/shape.py` —— 真實覆蓋面積、等效圓直徑、
旋轉卡尺的最大／最小 Feret，全部**旋轉不變**（一個 L 形的 bbox 是它真實面積的
1.9 倍，而那個數字看起來完全正常）。`threshold_pct` **兩支共用同一格、同一支
函式**，那正是「邊界判準是一個軸，不是一個 method」兌現的地方。UI **一個新原語
都沒加** —— 輪廓就是一串線段，第一批那個「Measure 段共用」的 `set_marks` 原封
不動就夠了。三個坑（百分位藏著「前景佔幾成」的假設、一階差分看不見低頻起伏、
兩道門檻只抄了一道）全部在 `PITFALLS.md`，而**第二個只有實跑一批資料才炸得
出來**：修之前假點 12/12 都量得出面積，修之後 0/12、真缺陷 11/12。

**第三批（顏色與面板）✅ 2026-08-21**：一個具名區域擁有一個顏色，而影像上的
框、模板編輯器、GLV 面板早就共用同一組（`theme.REGION_COLORS`）—— CD 沒跟，整張
畫 accent 藍。修法的重點不是換一個色票，是**索引由卡片給**（`region_index` 進
meta，`MultiSourceStep` 注入 `CURRENT_REGION_INDEX`）而**標記上色重用畫框那一份
順序** —— 兩邊各數各的話，`top,bot` 在一邊是 0/1、在另一邊（照名字排序）是 1/0，
而顏色指錯區域比沒有顏色糟得多。顏色做對之後才看得出下一件事：面板一次只畫
`notes()[0]`，於是接兩個區域時**輪廓畫在 B 區、面板在講 A 區的「什麼都沒有」**。
現在接幾個區域畫幾列（上限 3），順序照接線的順序。

**給使用者的操作手冊**：[`USING-CD.md`](USING-CD.md) —— 每一格什麼時候該動、
動了之後數字會往哪邊走、量不到時每一句話對應的動作、三個完整的設定範例。
要動 CD 卡的參數、help 文字或輸出名字之前要一起改。

⚠ ~~**黃金值要在家用機重凍**~~ —— **2026-08-23 實測推翻了這一條**（F21/F22 收尾）：
在容器裡（numpy 2.4.6 / opencv 5.0，比 pin 的 1.24 / 4.8 新兩個 major）重跑
`freeze_golden.py --check`，**每一個共有特徵都跟家用機凍的值逐位元組相同**
（`FLOAT_FORMAT` 是 `%.17g`，完整雙精度），bin 與 score 也零差異 —— 22 條差異
全部是 F19/F17 的改名與增刪。所以**哪台機器都凍得**。
這一條當初擋了黃金值兩天（F19 改名之後沒人敢凍），而它擋掉的風險並不存在。

**真正還成立的那一半**：重凍是「把現在的值當成新基準」，所以**看差異的那一步
不能跳過** —— `--check` 會逐項列出「哪一顆的哪個特徵從多少變成多少」，那份清單
要一條一條對得上你這一輪真的改了什麼。2026-08-23 那次重凍的清單是
「消失 area_px / cd_x_px / cd_y_px / test_clip_frac、新增 cd_* 那一批 ＋
norm_clip_frac」，逐項對得上 F19 與 F17-②。

### 畫布的七段（F16 定八段，F24 §5 解散 Algo）

```
Input → Enhance → ROI → Measure → Compare → ADC → Output
```

⚠ **這裡以前寫著八段。** `Algo` 在 F24 §5（使用者 2026-08-24 點頭）解散進判定，
`GROUP_ORDER` 現在是七段 —— 唯一出處在 `d4t/core/pipeline/step.py`。

**段落本身 ✅ 2026-08-20**：`GROUP_ORDER` 重排並加了 `algo` / `output` 兩段，
`LibraryPanel.GROUPS` 對齊（`tests/test_ui_f16_stages.py` 把兩份綁在一起），
階段色從 6 個擴到 8 個。

**這個順序不決定執行順序** —— 執行是 DAG 拓撲排序，線怎麼拉就怎麼跑；
`GROUP_ORDER` 排的是卡片庫的分區順序。所以「Compare 排在 Measure 後面」不代表
`diff` 會晚一步產生。

兩段的界線各有一條自動套用到 registry 的測試：

* **Algo** —— 使用者：「measure 是量出數值來，但 **Algo 是拿這些 feature 內去做
  更 custom 的處理**」。寫成不變量：**Algo 段的卡 `resolve_reads()` 恆為空**
  （不吃影像流）。⚠ **這一段 2026-08-24 解散、唯二兩張卡 2026-08-27 刪掉了**
  （`feature_math` / `feature_fill` → 判定的 working numbers）。`GROUP_ALGO`
  這個常數留著給外掛卡相容，但 repo 裡零張卡 —— 而那條不變量因此**沒有東西
  可以套用**，守它的測試同一天拿掉了（一條永遠不會執行的斷言比沒有斷言更糟）。
* **Output** —— 使用者：「**他就是個 end point**」，而且「可以產出多種 style
  （分 card）：Report / CSV / KLARF / HTML，要單純 output image 也可」。
  寫成不變量：**`resolve_writes()` 與 `resolve_features()` 都是空的**。
  ✅ **Output 為真相，Export 精靈已於 2026-08-20 拿掉**（使用者定調）。
  順序是綁死的，而且真的照著走：先讓 Output 卡做到能取代精靈、**逐位元組驗過**
  （`tests/test_export_parity.py`），再刪 —— 否則中間 app 輸不出任何東西。
* **Custom 這一層** —— **先不做**（使用者 2026-08-20：「先把大部分功能完成
  需要我們再來研究」）。

### 引擎缺口：跨顆那一層（batch-level step）

`run_defect` 一顆一顆跑、從不 raise（鐵則 7），所以任何「要看過整批才算得出來」
的東西現在都沒有地方放。**四個需求卡在同一件事上**：

| 需求 | 為什麼是跨顆 |
|---|---|
| Output 的 CSV / KLARF / Report / HTML | 一批一個檔案（出圖那幾張是例外，逐顆）|
| 離群旗標（Tukey IQR、z-score）| 門檻由整批的分布決定 |
| ~~F15 欠的那份點對點 report~~ ✅ F33（2026-08-25）| 一顆一列的表 ＋ 整批的分布 —— `output_char`（畫面上 F38 起叫 “Write comparison”）|
| `H2H` 的 `expect_dx_px` 建議值 | 整批取中位數（現在只能靠 `tools/pair_probe.py` 在外面算）|

先做機制，四個都便宜；不做機制，四個各自發明一套。

**機制 ✅ 2026-08-20**（`Step.is_batch` ＋ `pipeline.run_batch_steps` ＋
`BatchContext`），第一張消費者是 `output_csv`（F38 折進 `output_report` 了；產的 CSV 與 Export 精靈**逐位元組
相同**，那是之後拿掉精靈的前提）。三條規矩：

* **跨顆卡不在 `run_defect` 裡跑**，而且**跳過不是報錯** —— 一份含 Output 卡的
  recipe 在單顆預覽上仍然要跑得完（那是調參數的畫面）。
* **一張跨顆卡出錯不影響其他卡**（鐵則 7 的跨顆版），訊息進 `bctx.errors`。
* **試跑不寫**（使用者定調）—— 而那不是一個旗標，是**兩支函式**：試跑那條路
  根本不叫 `run_batch_steps`。旗標遲早有人忘記關，而症狀是不可逆的覆寫。

**五張卡 ✅ 2026-08-20**（⚠ **F38 於 2026-08-26 收成三張**，見這一段結尾）：
`output_csv` / `output_report`（Excel）/
`output_klarf`（三種寫回模式）/ `output_html`（自帶樣式，可以直接寄出去）/
`output_image`（每顆一張疊圖）。**五張都是 `is_batch`，包含會出圖的那一張** ——
它看起來是逐顆的，但做成普通 Step 的話它會在 `run_defect` 裡跑，而那條路每切換
一顆 defect 就走一次（瀏覽 defect 時會一直寫 PNG）。所以它也是整批之後跑一次，
一顆一顆重跑 pipeline 取影像 —— 那正是 Export 精靈今天做的事。

⚠ **F38（2026-08-26）把七張收成三張**（使用者：「七張裡有五張在回答同一個
問題，收成三張」）：`output_csv` / `output_html` / `output_boxplot` / `output_bundle`
與原本的 Excel 卡全部折進 **`output_report`「Write report」**——一個資料夾，
要哪幾樣是一格勾選。留下的另外兩張是 `output_klarf` 與 `output_char`
（後者只改了 label：“Write comparison”）。舊 recipe 走
`recipe._migrate_folded_output_cards`：**內容逐位元組相同，路徑依那道遷移的
docstring 那張表位移**（`/x/my.csv` → `/x/defects.csv`）。

⚠ **`output_image` 於 F37（2026-08-26）折進 `output_bundle` 了**（而後者又在
F38 折進 `output_report`，遷移鏈一段一段接）：它的七格參數
一格不差全部是後者的子集，寫出來的東西正好是後者少了報表／表格／recipe。現在
是那張卡上的「只勾 pictures」，舊 recipe 走遷移。上面那段「為什麼它也是整批
一次」的道理**一字不變**，只是主詞換成了報表資料夾那張卡。

### Stage 5c ✅ 2026-08-20：Studio 的整批入口，然後刪掉精靈

1. **Studio 的「跑整批並寫出」入口** ✅ —— `StudioWindow.run_all()`。
   在此之前「Run all defects」跟「Run trial」是**同一支函式、同一條路**，
   差別只有 `limit`；現在它們真的不一樣：
   * **Run all 寫、Run trial 不寫**，而且旗標**跟著那一次執行走**
     （`_write_outputs_this_run`），不是讀當下的 UI —— 按了之後可以馬上去改
     別的東西。
   * **中途按停止 → 不寫，而且講出來**（部分結果寫進 KLARF 是不可逆的錯；
     安靜地不寫跟安靜地寫一樣糟）。
   * 寫檔走背景執行緒（`workers.OutputWorker`）—— 出圖那張卡會一顆一顆
     重跑 pipeline，在 GUI 執行緒做會僵住幾十秒。
   * 工具列那一格從「Export…」變成「**Run all & write**」（同一個位子、同一件
     事），前提改成跟 Run trial 一樣（有資料、流程跑得動）——它自己就是那一次跑。
2. **`output_klarf` 的寫回前預覽** ✅ —— `WriteBackInspector`（F7-17 的機制）。
   精靈的做法是把「寫出」鈕鎖住直到按過預覽；乾跑（`plan_writeback`）一個
   位元組都不寫，所以它不需要那顆鈕：選到那張卡就看得到會改幾列、寫去哪、
   原檔動不動 —— 比精靈**更早**。
   ＋ **只在 `inplace` 時跳確認**（使用者定調）。判準是「**會不會動到原檔**」
   不是「是不是 KLARF」：`annotate` / `topn` 寫的都是新檔，每次都問的話那個
   確認很快就變成閉著眼睛按掉的東西 —— 而它要擋的正是 `inplace` 那一種。
   停用的卡不跳（不會跑的東西跳確認就是騙人）。
3. **逐位元組的許可證** ✅ —— `tests/test_export_parity.py`：同一批結果，兩條路
   各產一次，CSV / KLARF（annotate、topn 兩種、inplace）/ 疊圖 PNG **逐位元組
   相同**，Excel 逐格相同（`.xlsx` 是 zip，檔頭有時間戳，比位元組會變成一條
   每次都紅的測試）。**不綠就不刪** —— 而它抓到了兩件精靈有、卡片沒有的事：
   疊圖左上角的 `score=` / `bin=`（`overlay_label`）與檔名的消毒
   （`overlay_filename`）。兩支都搬進了 `core/export/overlay.py`。
4. **刪掉** ✅ —— `d4t/ui/export_dialog.py`（1213 行）、工具列的 `Export…`、
   `results.export_requested` 接線、`open_export_dialog`、
   `tests/test_ui_export_dialog.py`。**`core/export/` 一行都沒刪**：
   `klarf_out` / `report` / `overlay` 是 Output 卡的引擎。
   CLI 的 `d4t export` 子命令**保留**（使用者定調「下一輪再看」）—— 它不是精靈：
   它跑的是「已經跑完的結果重新匯出」（從 SQLite 歷史），跟 Output 卡不完全重疊。
## F17：讓 DAG 引擎名實相符（2026-08-20）

從「特徵要不要開第三種埠」一路查到引擎，翻出一個更根本的診斷：
**d4t 不是純 DAG 引擎，是「有序清單 ＋ 補充的線」**（見
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) 的「執行順序只有一個家」）。
使用者定調把四件事做掉，而且**不開新埠**。

| | 做了什麼 | 黃金值 |
|---|---|---|
| ① | **順序只有一個家**：`execution_order` 拿掉 route 相鄰對，邊只來自 `edges`；route 位置退成 Kahn 的平手依據 | 不動（可證明）|
| ③ | **快取邊界從宣告推導**：checkpoint ＝ 最後一張吐影像流的卡，不看 `category`；新增 `CATEGORY_BATCH` | 不動 |
| ② | **特徵的擁有者是結構**：寫入當下記；撞名前綴從節點 id 換成流名 | **動了兩個名字**（值全同，見下）|
| ④ | **一顆與整批是兩個尺度**：`Step.scale`（`is_batch` 推導）；新增 `batch-card-has-downstream` lint | 不動 |

**② 是唯一動到黃金值的一項，而它動的只有名字。** `norm_clip_frac` →
`test_clip_frac`、`norm_ref_clip_frac` → `ref_clip_frac`；逐項比對過**值、
score、bin 全部相同**才重凍。舊 recipe 的表達式有一道遷移
（`_migrate_rescued_feature_names`），判準是「舊東西在不在」（鐵則 9）。

**兩種做法的名字仍然不會完全一樣，那是刻意的**：兩張卡各接一條流時，最後寫的
那個保留短名 `glv_mean`（D2，2026-08-16）。要讓它也變成 `ref_glv_mean` 就得把
贏的那個改名，而那會讓 `glv_mean` 突然不存在。

### 還沒做的（⑤，暫不動）

**kind / route 的分組模型**：現在每個 kind 一條 route、節點跨 route 共用 id。
可以考慮「一份 recipe ＝ 一個圖，kind 只影響入口卡」，但代價大、收益不明顯。

### 特徵要不要有自己的埠（2026-08-20 結論）

**不開新埠**（使用者：「多一種阜 可能就會有多的學習成本」）。三種通道的現況：

| 通道 | 畫布上 | 為什麼 |
|---|---|---|
| 影像流 | 圓埠、實線 | 身分是 `(節點, 埠)` |
| 具名區域 | 菱形埠、虛線（推導） | 全域唯一的名字（`unknown-region` 是 error）|
| **特徵** | **沒有埠、沒有線** | 見下 |

* **不能跟影像走**：Algo 段的卡按定義**不在影像的 DAG 上**（`feature_math` 的
  影像輸入埠、影像輸出、區域埠都是 0）。要讓它在上面就得給它兩顆假埠 ——
  一顆它不吃的輸入、一顆它不產的輸出。而且分岔時會**指錯**：實測一份分岔
  recipe，接在 test 那支的 Algo 卡拿到的是 ref 那支的值（107.2712 vs 107.2673，
  差 0.0039，看不出來）。
* **不能跟區域走**：區域埠是參數宣告出來的，加一個 ROI 參數等於強迫每份用到
  Algo 的 recipe 都要有一張 Region 卡。
* **所以是「名字就是線」**：F17-② 之後每個數字的名字自己帶來源
  （`test_glv_mean`），「這個數字從哪來」看名字就知道 —— 不用埠、不用線。

Output 卡同理**不需要埠**：它吃的是「這一次跑的全部」，沒有「哪一個」可以選。
它需要的是 end point 的**畫法**（使用者：「再看看」），而 `scale = SCALE_LOT`
＋ `batch-card-has-downstream` 已經把那件事變成引擎裡的規則。

### Output 段還欠什麼（下一輪）

**畫布那一半**（使用者 2026-08-20：「先做引擎，畫布那一半下一輪」）：跨顆卡吃的
是「整批的 feature 表」，而 d4t 沒有那種埠 —— 跟 Algo 段的 `feature_math` 是同一
個題目（第三種埠）。目前兩者都靠 route 順序，所以**畫布上看不出它們吃什麼**，
而那正是鐵則 9 說的那件事的形狀（資料從哪來由線決定）。

### F15 停在哪裡（2026-08-20）—— **✅ 2026-08-25 由 F33 續完**

> 停下來的兩件事都補上了：**證據**那一份是
> [`history/plans/F33-ebi-characterization.md`](history/plans/F33-ebi-characterization.md) 的
> C3（`output_char`，一顆一列、兩張圖跟數字在同一列上），而它需要的兩個資料
> 缺口是 C2（配不到的那一顆留下來，`pair_found = 0` 走得到判定樹）與 C1
> （die 內排名，母體是第二份的完整清單）。下面留的是當時停下來的理由。

使用者叫停：「**我看不出來有沒有對好、對到，有沒有把 data 整理好（一一對應）**
…現有的功能只是告訴我有對到（**但是不是不知道**）…我覺得現在做這邊**太快了**」。

**引擎那一半是對的而且有測試**（配對、對圖、尺度自動、搜尋框、stage offset、
`peak_ratio`、`tools/pair_probe.py`）。**缺的是產品化那一半**：

1. **證據**：現在吐的每一個數字都在說「有對到」，沒有一個在說「對得對不對」。
2. **那份 report**：使用者要的是「**點對點、包含圖的 report**」—— 一顆一列、
   左右兩張圖、加上那幾個數字，一眼掃過去就看得出哪幾顆可疑。
   （`pair_probe` 的分布是給**調參數**的人看的，不是給**檢查這批對不對**的人
   看的 —— 兩件事。）

**不刪、不收起來、停在原地**，等 Compare 段做完再回來接 —— 那時候「一一對應
看不看得出來」會跟 Compare 段其他卡的答案長成同一個形狀。

## Phase 3 —— 讓人用得起來（原 Phase 2）

engine 與功能收斂之後才有意義。

| 項目 | 說明 |
|---|---|
| ground truth **標注介面** | 讀答案卷與即時準確率已經在（Phase 1），缺的是**在 Studio 裡標**：現在還是要人另外準備一份 JSON／CSV |
| ~~整批的分布畫得出來~~ | ✅ **2026-08-26（F36）**：一片葉子一個盒子，手寫 SVG（零新相依 —— 公司機是用複製檔案更新的）。`Numbers to plot` 留空 = 判定問過的那幾個（`decide_tree.features_used`）。⚠ **F38 起它不是自己一張卡**，是 `Write report` 上的一個勾（寫出 `spread.html`）|
| ~~存檔 recipe 做回來~~ | ✅ **2026-08-26（F34）**。`app_version` 那條相容策略本來就在（`version_skew`），這一輪只是把寫檔那一半接回來 |
| 範例 recipe 庫 | 使用者的原話是「等 APP 完成再給範例」。`recipes/` 已經有出貨的 recipe（2026-08-26），缺的是**庫的入口**（`SHOW_SAMPLE_ENTRIES`）|
| 使用者手冊 | 目前所有文件都是寫給開發者的。目標使用者是不寫 code 的製程／設備工程師 |
| 快速參考卡 PDF | M6 欠著的 |

## Phase 4 —— 規模

多 lot 趨勢｜recipe A/B 比較｜共用 recipe library｜自由 DAG 畫布（雙 reference AND）｜
自然語言 → recipe 草稿。

---

## 已完成

| Milestone | 狀態 | 內容 |
|---|---|---|
| F8 | 🔨 | **純規則 ROI 定位 + mask 通道 + UI 第二波**（詳見 `SESSION_LOG.md` 逐輪紀錄與 `docs/history/plans/F8-rule-based-roi.md`）。已完成：`roi_cross`（條紋交會處放框、一鍵整批量 pitch）、`roi_mask` + Normalize `use_within`（見 §2.5）、參數說明搬 tooltip、D 案版面（畫布佔中上、設定拿大頭、**畫布彈出視窗**兩窗互通）、右鍵平移、手動佈局保留（tidy 才重排）、route 虛線退役（排版仍吃隱含順序）、量測卡預覽疊區域框、`multi_choice` 參數型別（glv_stats 統計量用勾的）、subtract 預設 `b=ref`（patch 天生對齊；舊檔載入遷移補 `ref_aligned` —— **改預設值必附遷移**） |
| M0 抽庫 | ✅ | 從 KLIP/GLAS/MMH/PEAR/CPE/Fusi³ vendoring 演算法資產 |
| M1 引擎 | ✅ | Context/Step/Recipe DAG/表達式/14 張卡/合成資料/CLI |
| M2 批次 | ✅ | ProcessPool + 影像段快取 + SQLite 歷史 + rescore |
| M3 Studio | ✅ | PySide6 四區塊視覺化編輯器 |
| M4 雙輸入 | ✅ | RSEM 單張 ingest、輸入型別分流、Golden Cell + Cell 週期估測卡（`period.choose_origin` 相位搜尋已補完）。驗收達成：一份 recipe 同時吃 EBI patch 與 RSEM，跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1%（那份 `dual_route_basic.json` 現在留在 `tests/fixtures/recipes/`）|
| M5 Gallery+Export | ✅ | Gallery（虛擬捲動、排序、直方圖點 bar 篩選）；KLARF 三種寫回模式（就地無損／另存含 ADCSCORE+ADCCLASS／Top-N）+ 寫回前預覽變更；CSV/Excel 報表（含抓漏率/誤殺率）；overlay；`fab_probe/` 三支探測腳本；CLI `d4t export` |
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
