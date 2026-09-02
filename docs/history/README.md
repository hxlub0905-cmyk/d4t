# docs/history —— 封存

做完的東西搬到這裡：按月封存的開發紀錄、已完成 milestone 的計畫書。
**搬的時候內容一個字都不改**，只是換個地方住 —— 要改的是**搬之前**那一步：
把頂上的狀態標成 ✅ 並寫出它實際收在哪裡（一份寫著「未動工」而其實已經上線的
計畫書，封存起來就是一句會誤導下一個人的話）。

> 2026-09-02 這條規矩真的用到了：`2026-08b.md` 裡 F58 的頂上寫著
> 「⏸ 等使用者定調放哪裡」，而隔一輪的 F59 早就把那個問題整個換掉了。
> 搬之前補了一段後記，不是搬完才發現。

## 開發紀錄（`SESSION_LOG` 的封存）

| 檔案 | 涵蓋 |
|---|---|
| [`2026-08b.md`](2026-08b.md) | 08-19 ～ 08-28（**F42 ～ F66**）：區域線走 edges、結果表分層／FeatureSpec、檔案架構與授權、六個決定、畫布上只剩卡片和線、特徵名與數字只有一種寫法、合成資料長成真的那種 layout |
| [`2026-08.md`](2026-08.md) | 08-07 ～ 08-18（第十五輪以前）：F8 純規則 ROI、畫布 n8n 化、Phase 1 收斂、F10、Phase 2 的 Input／Enhance／Region 三段 |
| [`2026-07.md`](2026-07.md) | M0–M7、F7-9…F7-18、兩台機器與搬運通道的成形 |

⚠ **切點換過一次。** 前兩份用的是「上一次合併進 `main` 的那一輪」；這條分支從
08-19 起沒有再併回 main，那條線因此切不動任何東西，所以第三份改用**月份**。

## 計畫書（做完的）

**`docs/plans/` 現在只剩一份活的**（`F11` —— Phase 2 的議程）。其餘全部在
[`plans/`](plans/) 底下，照編號排：

| 計畫書 | 是什麼 |
|---|---|
| [`F0-master-plan.md`](plans/F0-master-plan.md) | **原始總計畫 v1.0（2026-07-27）**，依六專案盤點 + 三輪需求訪談定案。⚠ 它描述的形狀**大半已經被推翻**（19 張卡、Image/Algo 兩大類、M0–M7）—— 進度看 [`../ROADMAP.md`](../ROADMAP.md)，訪談結論看 [`../HANDOVER.md`](../HANDOVER.md)。留著是為了「當初是怎麼想的」 |
| [`F7-canvas-and-taxonomy.md`](plans/F7-canvas-and-taxonomy.md) | F7 全系列（F7-1…F7-24）✅。`CLAUDE.md` 的坑表大量引用它的 §，那些引用仍然有效 |
| [`F8-rule-based-roi.md`](plans/F8-rule-based-roi.md) | 純規則的 ROI 定位（兩組條紋的交會處）✅ |
| [`F9-dag-streams.md`](plans/F9-dag-streams.md) | 影像流變成 DAG 上的線 ✅ —— `CLAUDE.md` 鐵則 10 引用它 |
| [`F10-canvas-tells-the-truth.md`](plans/F10-canvas-tells-the-truth.md) | 畫布要符合現實（剛加的卡前後都是空的、埠點得到、多連一）✅ |
| [`F12-region-edges.md`](plans/F12-region-edges.md) | 具名區域也有線了（虛線＋菱形埠）✅。⚠ **§3 於 F42 被推翻**（線改成住在 `recipe.edges`），其他部分仍然成立 |
| [`F15-pair-sources.md`](plans/F15-pair-sources.md) | 配對分析：兩筆資料逐顆對起來。2026-08-20 使用者叫停（「太快了」），08-25 由 F33 續完 ✅ |
| [`F18-glv.md`](plans/F18-glv.md) | Measure 第一張：Gray level ✅（三個互相獨立的問題、名字分家族、量得準不準是明講的）|
| [`F19-cd.md`](plans/F19-cd.md) | Measure 第二張：CD ✅（原子單位從「一個區域」換成「一條量測線」，σ 就是 LWR）|
| [`F20-pick-defect-box.md`](plans/F20-pick-defect-box.md) | 哪一塊是缺陷那一塊（`_util.pick_defect_box`）✅ |
| [`F21-algo-and-roi.md`](plans/F21-algo-and-roi.md) | Algo 段要不要存在、ROI 值多少 —— **用量的不是用想的** ✅。§6 那條「黃金值是壞的」已於 08-23 重凍解除（見該節後記）|
| [`F22-adc-multiclass.md`](plans/F22-adc-multiclass.md) | 多類別 ADC ✅ —— 這個 app 第一次分得出兩類以上 |
| [`F23-route-by.md`](plans/F23-route-by.md) | 分流：不同 CLASSNUMBER 走不同的卡片 ✅（`routes-drift` lint 定調為先不做）|
| [`F24-decision-tree.md`](plans/F24-decision-tree.md) | 判定樹上畫布 ✅ —— Algo 段在這一份 §5 解散進判定（八段變七段）|
| [`F25-adc-usable.md`](plans/F25-adc-usable.md) | 判定段要**有人會用** ✅（二元門檻的 UI 整支拿掉，舊 recipe 一打開就是樹）|
| [`F26-decide-panel-ux.md`](plans/F26-decide-panel-ux.md) | 判定面板的 UI/UX ✅（最後一條「草案 7 版面」於 08-28 由 F48 收掉）|
| [`F27-results-panel.md`](plans/F27-results-panel.md) | 跑完之後那一頁 ✅（三件待定調兩件由 F48 定案；剩下的「純度那一欄沒有 ground truth 就沒值」記在 [`../ROADMAP.md`](../ROADMAP.md) Phase 3）|
| [`F28-canvas-and-measure.md`](plans/F28-canvas-and-measure.md) | ADC 判定區拖得動拿得掉、Measure 段改名重排、Z-map 走人 ✅ |
| [`F29-detect-and-report.md`](plans/F29-detect-and-report.md) | 把已經量到的位置說出來 ＋ 報表資料夾 ✅ |
| [`F33-ebi-characterization.md`](plans/F33-ebi-characterization.md) | EBI ↔ API characterization ✅。使用者的操作手冊在 [`../USING-CHARACTERIZATION.md`](../USING-CHARACTERIZATION.md) |
| [`F34-save-recipe.md`](plans/F34-save-recipe.md) | 存檔 recipe 做回來 ＋ 第一份出貨的 recipe ✅。**F35 住在同一份**（§5）|
| [`F36-boxplot-and-patch-recipe.md`](plans/F36-boxplot-and-patch-recipe.md) | 整批的分布畫得出來（手寫 SVG）＋ patch 的 dSNR recipe ✅ |
| [`F37-glv-roi-names-and-output.md`](plans/F37-glv-roi-names-and-output.md) | GLV↔ROI 命名對齊 ＋ 出圖那張卡折進報表 ✅ |
| [`F38-output-three-cards.md`](plans/F38-output-three-cards.md) | Output 七張收成三張 ✅ |
| [`F39-f-test-audit.md`](plans/F39-f-test-audit.md) | F 編號測試審一輪 ✅。⚠ **五批之中四批的數字是錯的**（估「刪 282 條」實刪 25 條），事後檢討在它的 §12 |
| [`F40-stack-agreement.md`](plans/F40-stack-agreement.md) | 把「疊得準不準」量對 ✅ —— 一支恆綠零斷言的測試底下是一個演算法問題 |
| [`F41-phase3-delete-algo-cards.md`](plans/F41-phase3-delete-algo-cards.md) | 刪掉 `feature_math` / `feature_fill` ✅（§4 的兩個問題 08-28 由 F48 定調）|
| [`F42-region-edges-plan-b.md`](plans/F42-region-edges-plan-b.md) | 區域線改存進 `recipe.edges` ✅（B0–B4）—— `CLAUDE.md` 鐵則 10 的第二半引用它 |
| [`F43-results-layers.md`](plans/F43-results-layers.md) | 結果表分層 + 診斷徽章 ✅（總工作單 PR-1）|
| [`F44-region-wiring-and-panels.md`](plans/F44-region-wiring-and-panels.md) | 區域接線可讀性 + 儀表補洞 ✅（PR-2）|
| [`F45-feature-specs-and-verdict-trace.md`](plans/F45-feature-specs-and-verdict-trace.md) | `FeatureSpec` 結構化身分 ＋ 分數回溯 ✅（PR-3）|
| [`F48-six-decisions.md`](plans/F48-six-decisions.md) | 六個待定調的決定一次收 ✅ —— 含**其中一件為什麼退回去重問** |
| [`F49-features-on-wires.md`](plans/F49-features-on-wires.md) | 特徵也走線的**範圍評估**（一行程式都沒動）。結論：留下現有設計，改用淡的推導線；⚠ 這一份有一個核心論點被實測推翻，見 [`../ROADMAP.md`](../ROADMAP.md) |
| [`F50-canvas-is-cards.md`](plans/F50-canvas-is-cards.md) | 畫布上只剩卡片和線 ✅（六件事一次點頭）|
| [`F51-feature-names-one-truth.md`](plans/F51-feature-names-one-truth.md) | 特徵名只有一個真相 ✅。⚠ §6 對 C 的描述有一句是錯的，那一節有訂正 |
| [`F52-one-way-to-print-a-number.md`](plans/F52-one-way-to-print-a-number.md) | 一個特徵值，一種寫法 ✅（六種格式化函式收成一支）|
| [`F67-glv-compare-by-wire.md`](plans/F67-glv-compare-by-wire.md) | GLV 的「跟誰比」由線決定 ✅ |
| [`F68-glv-defect-hunting.md`](plans/F68-glv-defect-hunting.md) | GLV 是抓 defect 的主力卡 ✅（驗收由 F73 補跑完，見 [`../../SESSION_LOG.md`](../../SESSION_LOG.md)）|

## 為什麼要有這個目錄

`SESSION_LOG` 與做完的計畫書有一個共同點：**只增不減，而且公司機一行都用不到**
（那台機器的工作是拿到程式碼並執行）。所以這個目錄**不進搬運包**
（`tools/make_filelist.py` 的 `EXCLUDE_DIRS`，`make_text_bundle.py` 共用同一份
定義），把搬運量留給真的要搬的東西。

那個大小之所以值得管：GitHub 的**檔案瀏覽頁**不顯示超過 1 MB 的檔案，而「按
複製鈕」是搬進公司機最順的一條路。**超過也不是死路** —— raw 連結打得開、
全選複製一樣搬得走（見 [`AGENTS.md`](../../AGENTS.md) §2），只是操作變麻煩。

要讀封存的內容？GitHub 上讀得到，`git clone` 也拿得到 —— 少掉的只有「跟著整包
被複製進公司機」這件事。

## 什麼時候該往這裡搬

- `SESSION_LOG.md` 又長到讓人不想捲：把上一段整段搬過來，**保持新→舊的順序**
  （原檔曾經是三批不同排序拼起來的，找一件事得先猜自己在哪一批裡）。
- 一個 milestone 的計畫書標成 ✅ 而且不再有人往裡面寫東西：連同它搬過來，
  並把引用它的路徑一起改掉（`grep -rn "docs/plans/<名字>"`）。
  ⚠ **搬完檔案本身的相對連結也要重算**（深了一層）——
  `tests/test_docs_links.py` 會擋，但它擋不到「指得到、卻指錯地方」的那種。

搬完記得 `git add -A && python tools/release.py && git add -A` —— 那一支會報
目前的水位，超過 85% 就會叫。
