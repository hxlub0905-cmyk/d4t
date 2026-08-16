# docs/history —— 封存

做完的東西搬到這裡：按月封存的開發紀錄、已完成 milestone 的計畫書。
**內容一個字都不改**，只是換個地方住。

| 檔案 | 是什麼 |
|---|---|
| [`2026-07.md`](2026-07.md) | 2026 年 7 月的 `SESSION_LOG`（M0–M7、F7-9…F7-18、兩台機器與搬運通道的成形） |
| [`plans/F7-canvas-and-taxonomy.md`](plans/F7-canvas-and-taxonomy.md) | F7 全系列的計畫書（F7-1…F7-24，✅ 全數完成）。CLAUDE.md 的坑表大量引用它的 §，那些引用仍然有效 |

## 為什麼要有這個目錄

不是整理癖，是**搬運餘裕**。

公司機下載不了東西，唯一的通道是在 GitHub 網頁上按複製鈕，而**GitHub 不顯示
超過 1 MB 的檔案**（見 [`AGENTS.md`](../../AGENTS.md) §2）。整包壓成一個
`bundle/ADEPT_bundle.py` 就是為了繞過這件事 —— 而它 2026-08-16 已經到 962 KB，
只剩 6% 餘裕。

`SESSION_LOG` 與做完的計畫書有一個共同點：**只增不減，而且公司機一行都用不到**。
那台機器的工作是拿到程式碼並執行。所以這個目錄**不進搬運包**
（`tools/make_filelist.py` 的 `EXCLUDE_DIRS`，`make_text_bundle.py` 共用同一份
定義），把餘裕留給真的要搬的東西。搬完之後量到 888 KB。

要讀？GitHub 上讀得到，`git clone` 也拿得到 —— 被擋掉的只有「複製進公司機」
那一條路。

## 什麼時候該往這裡搬

- `SESSION_LOG.md` 又長到讓人不想捲：把上個月整段搬過來，**保持新→舊的順序**
  （原檔曾經是三批不同排序拼起來的，找一件事得先猜自己在哪一批裡）。
- 一個 milestone 的計畫書標成 ✅ 而且不再有人往裡面寫東西：連同它搬過來，
  並把引用它的路徑一起改掉（`grep -rn "docs/plans/<名字>"`）。

搬完記得 `git add -A && python tools/release.py && git add -A` —— 那一支會報
目前的水位，超過 85% 就會叫。
