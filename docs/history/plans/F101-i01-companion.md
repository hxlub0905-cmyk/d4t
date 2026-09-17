# F101 — `.I01`：副檔名不同的 patch TIFF

狀態：**已收斂（2026-09-17）** —— 程式出貨當天，假設 #8 由使用者的另一個 agent 在真檔上
整條確認（MM 多頁 TIFF、id 全檔連號、page = id − 1），對映邏輯零改動；見
[`../../FAB-VALIDATION.md`](../../FAB-VALIDATION.md) #8。

## 1. 使用者說了什麼

> 我要能支援新的圖檔叫做 I01，一樣是跟 klarf 一一配對的

「一樣」指的是現在的 patch TIFF：一份 KLARF 配一個檔（`LOT.001` ↔ `LOT.tif`）。
所以 `.I01` 的**資料形狀**跟 `ebi_patch` 逐項相同：一個檔、每顆連續幾頁。

## 2. 決定：不是新 kind、不是新 Load 卡

| 問題 | 答案 | 為什麼 |
|---|---|---|
| 第五種 kind？ | **不** | kind 講的是資料形狀不是檔名（2026-09-07 `Open image…` 走 `folder` 的同一個理由）。多一個 kind 要動 `scope.SUPPORTED_KINDS`、route、起手卡、快取簽章 —— 全部為了一個副檔名 |
| 第三張 Load 卡？ | **不** | 卡片看的是「一顆幾張」，不看檔案格式（F11 Input-4）。`load_patch` 對 `.I01` 的資料一個位元組都不用改 |
| 副檔名住哪 | **只住在「去哪找檔」** | `klarf_core.PATCH_IMAGE_EXTS`（`tiff_path()` 的同名候選）、`dataset._TIFF_EXTS`（`Open image…`／`Open folder…` 的多頁提醒）、Studio 兩個對話框的過濾字串 —— 三處，`tests/test_i01_companion.py` 守它們對得上 |
| 怎麼判斷內容 | **看檔頭不看副檔名** | `tiff_index.check_header`：8 個位元組。`.tif` 裡放 PNG 跟 `.I01` 裡放 PNG 是同一件事 |

## 3. 假設錯的那一天

`bit_depths` 對非 TIFF 是**安靜地回空 list**（刻意的：位元深度不該讓載入失敗）。
在這之前那代表一個內容不是 TIFF 的 companion 檔在按下 Open 時看起來完全正常，
然後每一顆 defect 各自倒在同一句 `Not a TIFF` 上。開放 `.I01` 之後這從「幾乎
不會發生」變成「假設 #8 錯了就一定發生」，所以 `load_dataset` 現在先讀 8 個
位元組，不是 TIFF 就在 warnings 講**一次**：檔名、為什麼、下一步（跑
`probe_tiff.py` 把報告貼回來）；defect 照樣進來、沒有影像。

## 4. 真檔長什麼樣（2026-09-17 確認）

見 `FAB-VALIDATION.md` #8。要點：record 語法 1.8、`ImageFileName` 住在 `WaferRecord`、
列尾 `Images 2 {id "30", id "31"}` 的 id 是**全檔連號的 1-based 頁碼**（缺陷 N →
2N−1／2N），正好是 `defect_image_map` 既有的 imagelist 模式。順手補的：
`defect_image_filename` 不再把 `"30"` 當成每顆一個檔的檔名（那會讓「.I01 不在」
的錯誤訊息講一個不存在的檔）；檔不在時 `load_dataset` 講出 KLARF 點名的那個檔名。

## 5. 家用機怎麼練

```
python tools/make_sample.py /tmp/lot_i01 --n 24 --image-ext .I01
python -m d4t run recipes/ebi-die-to-die.json /tmp/lot_i01/LOT_SYN.001 --csv f.csv
```

產出跟 `.tif` 那份**逐位元組相同**，只有檔名與 KLARF 的 `TiffFileName` 那一行不同
（測試鎖著）。
