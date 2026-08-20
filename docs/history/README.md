# docs/history —— 封存

做完的東西搬到這裡：按月封存的開發紀錄、已完成 milestone 的計畫書。
**內容一個字都不改**，只是換個地方住。

| 檔案 | 是什麼 |
|---|---|
| [`2026-08.md`](2026-08.md) | 2026 年 8 月**前半**的 `SESSION_LOG`（08-07 ～ 08-18，第十五輪以前）。切點是**上一次合併進 main 的那一輪**，不是月份 |
| [`2026-07.md`](2026-07.md) | 2026 年 7 月的 `SESSION_LOG`（M0–M7、F7-9…F7-18、兩台機器與搬運通道的成形） |
| [`plans/F7-canvas-and-taxonomy.md`](plans/F7-canvas-and-taxonomy.md) | F7 全系列的計畫書（F7-1…F7-24，✅ 全數完成）。CLAUDE.md 的坑表大量引用它的 §，那些引用仍然有效 |
| [`plans/F8-rule-based-roi.md`](plans/F8-rule-based-roi.md) | 純規則的 ROI 定位（兩組條紋的交會處）✅ |
| [`plans/F9-dag-streams.md`](plans/F9-dag-streams.md) | 影像流變成 DAG 上的線 ✅ —— CLAUDE.md 鐵則 10 引用它 |
| [`plans/F10-canvas-tells-the-truth.md`](plans/F10-canvas-tells-the-truth.md) | 畫布要符合現實（剛加的卡前後都是空的、埠點得到、多連一）✅ |
| [`plans/F12-region-edges.md`](plans/F12-region-edges.md) | 具名區域也有線了（虛線＋菱形埠，**線從參數推導、不存第二份**）✅ |

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
