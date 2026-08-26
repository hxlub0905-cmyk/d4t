# docs/history —— 封存

做完的東西搬到這裡：按月封存的開發紀錄、已完成 milestone 的計畫書。
**搬的時候內容一個字都不改**，只是換個地方住 —— 要改的是**搬之前**那一步：
把頂上的狀態標成 ✅ 並寫出它實際收在哪裡（一份寫著「未動工」而其實已經上線的
計畫書，封存起來就是一句會誤導下一個人的話）。

| 檔案 | 是什麼 |
|---|---|
| [`2026-08.md`](2026-08.md) | 2026 年 8 月**前半**的 `SESSION_LOG`（08-07 ～ 08-18，第十五輪以前）。切點是**上一次合併進 main 的那一輪**，不是月份 |
| [`2026-07.md`](2026-07.md) | 2026 年 7 月的 `SESSION_LOG`（M0–M7、F7-9…F7-18、兩台機器與搬運通道的成形） |
| [`plans/F7-canvas-and-taxonomy.md`](plans/F7-canvas-and-taxonomy.md) | F7 全系列的計畫書（F7-1…F7-24，✅ 全數完成）。CLAUDE.md 的坑表大量引用它的 §，那些引用仍然有效 |
| [`plans/F8-rule-based-roi.md`](plans/F8-rule-based-roi.md) | 純規則的 ROI 定位（兩組條紋的交會處）✅ |
| [`plans/F9-dag-streams.md`](plans/F9-dag-streams.md) | 影像流變成 DAG 上的線 ✅ —— CLAUDE.md 鐵則 10 引用它 |
| [`plans/F10-canvas-tells-the-truth.md`](plans/F10-canvas-tells-the-truth.md) | 畫布要符合現實（剛加的卡前後都是空的、埠點得到、多連一）✅ |
| [`plans/F12-region-edges.md`](plans/F12-region-edges.md) | 具名區域也有線了（虛線＋菱形埠，**線從參數推導、不存第二份**）✅ |
| [`plans/F18-glv.md`](plans/F18-glv.md) | Measure 段第一張：Gray level ✅（三個互相獨立的問題、名字分家族、量得準不準是明講的）|
| [`plans/F19-cd.md`](plans/F19-cd.md) | Measure 段第二張：CD ✅（原子單位從「一個區域」換成「一條量測線」，σ 就是 LWR）|
| [`plans/F20-pick-defect-box.md`](plans/F20-pick-defect-box.md) | 哪一塊是缺陷那一塊（`_util.pick_defect_box`）✅ |
| [`plans/F21-algo-and-roi.md`](plans/F21-algo-and-roi.md) | Algo 段要不要存在、ROI 值多少 —— **用量的不是用想的** ✅。§6 那條「黃金值是壞的」已於 2026-08-23 重凍解除（見該節後記）|
| [`plans/F22-adc-multiclass.md`](plans/F22-adc-multiclass.md) | 多類別 ADC ✅ —— 這個 app 第一次分得出兩類以上 |
| [`plans/F23-route-by.md`](plans/F23-route-by.md) | 分流：不同 CLASSNUMBER 走不同的卡片 ✅（三期全完成；`routes-drift` lint 定調為先不做）|
| [`plans/F24-decision-tree.md`](plans/F24-decision-tree.md) | 判定樹上畫布 ✅ —— Algo 段在這一份 §5 解散進判定（八段變七段）|
| [`plans/F25-adc-usable.md`](plans/F25-adc-usable.md) | 判定段要**有人會用** ✅（二元門檻的 UI 整支拿掉，舊 recipe 一打開就是樹）|
| [`plans/F28-canvas-and-measure.md`](plans/F28-canvas-and-measure.md) | ADC 判定區拖得動拿得掉、Measure 段改名重排、Z-map 走人 ✅ |
| [`plans/F29-detect-and-report.md`](plans/F29-detect-and-report.md) | 把已經量到的位置說出來 ＋ 報表 bundle ✅（A／B／C／D 全數完成）|
| [`plans/F15-pair-sources.md`](plans/F15-pair-sources.md) | 配對分析：兩筆資料逐顆對起來。2026-08-20 使用者叫停（「太快了」），**2026-08-25 由 F33 續完** ✅ —— 留著是為了「當時為什麼那樣設計」|
| [`plans/F33-ebi-characterization.md`](plans/F33-ebi-characterization.md) | EBI ↔ API characterization ✅ —— 把①抓到了／②排名太低／③沒偵測到三類分開。使用者的操作手冊在 [`../USING-CHARACTERIZATION.md`](../USING-CHARACTERIZATION.md) |
| [`plans/F34-save-recipe.md`](plans/F34-save-recipe.md) | 存檔 recipe 做回來 ＋ 第一份出貨的 recipe ✅。**F35 住在同一份**（§5：`configuration_issues` 與 `configuration_hints` 是兩件事）|
| [`plans/F36-boxplot-and-patch-recipe.md`](plans/F36-boxplot-and-patch-recipe.md) | 整批的分布畫得出來（`output_boxplot`，手寫 SVG）＋ patch 的 dSNR recipe ✅ |

**還在寫的計畫書留在 [`../plans/`](../plans/)**：`F0`（原始總計畫）、
`F11`（Phase 2 的議程）、`F26`／`F27`（各有一條等使用者定調的版面決定）。

## 為什麼要有這個目錄

`SESSION_LOG` 與做完的計畫書有一個共同點：**只增不減，而且公司機一行都用不到**
（那台機器的工作是拿到程式碼並執行）。所以這個目錄**不進搬運包**
（`tools/make_filelist.py` 的 `EXCLUDE_DIRS`，`make_text_bundle.py` 共用同一份
定義），把搬運量留給真的要搬的東西 —— 2026-08-16 這樣做之後包從 962 KB 回到
892 KB。

那個大小之所以值得管：GitHub 的**檔案瀏覽頁**不顯示超過 1 MB 的檔案，而「按
複製鈕」是搬進公司機最順的一條路。**超過也不是死路** —— raw 連結打得開、
全選複製一樣搬得走（見 [`AGENTS.md`](../../AGENTS.md) §2），只是操作變麻煩。

要讀封存的內容？GitHub 上讀得到，`git clone` 也拿得到 —— 少掉的只有「跟著整包
被複製進公司機」這件事。

## 什麼時候該往這裡搬

- `SESSION_LOG.md` 又長到讓人不想捲：把上個月整段搬過來，**保持新→舊的順序**
  （原檔曾經是三批不同排序拼起來的，找一件事得先猜自己在哪一批裡）。
- 一個 milestone 的計畫書標成 ✅ 而且不再有人往裡面寫東西：連同它搬過來，
  並把引用它的路徑一起改掉（`grep -rn "docs/plans/<名字>"`）。

搬完記得 `git add -A && python tools/release.py && git add -A` —— 那一支會報
目前的水位，超過 85% 就會叫。
