# F102 — 疊模板之前先框一塊（Crop）

狀態：**已收斂（2026-09-17）** —— 使用者點名當天做完：`ui/crop_dialog.py`（新模組）＋
`TemplateDialog` 的「Crop first」勾選與「Crop…」鈕；`tests/test_ui_crop_dialog.py` 十一條。

## 1. 使用者說了什麼

> 幫我加入 crop 功能，載入 template 的大圖，可以選擇要不要 crop 想要的部分之後再進行計算

## 2. 為什麼需要

`build_golden_cell` 疊的是整張大圖，而整張圖裡不只有要的那種 cell：RSEM 大圖正中央
是缺陷本體、邊上可能是 scribe line 或另一種 layout、角落有量測條。週期估測看的是
整張圖的投影，這些東西一多，估出來的就不是要的那個週期 —— 而錯的週期疊出來的模板
會讓後面每一顆都對錯，畫面上不會有錯誤訊息。

## 3. 做法

| 事 | 在哪 | 決定 |
|---|---|---|
| 拉框 | `ui/crop_dialog.py`：`CropView`（畫大圖、拉框、座標一律影像像素）＋ `CropDialog`（三選一：這一塊／整張／取消）| 框是在圖上拉的，不是四個打進去的數字（同 `cell_canvas` 的理由）；不到 `MIN_SIDE`=8 px 的框當成沒拉 |
| 什麼時候問 | `TemplateDialog.take_image`：兩個入口（挑檔案、畫面上那一張）都走它；勾了「Crop first」先問再疊 | 第一次載一張 7680² 不該先花 17 秒疊整張才能裁；沒勾就跟以前一樣 |
| 事後換一塊 | 「Crop…」→ `_on_crop`：帶著上一個框去問，重新量週期 | 要有整張原圖（從 recipe 讀回的模板沒有原料，講出來） |
| 裁的是什麼 | `load_image(..., crop=)`：`_full` 是整張、`_source` 是疊進去的那一塊、`_crop` 是框；`restack` 走 `_full`＋`_crop` | 裁的是原料不是結果：**框不進 recipe**（大圖路徑也不進），摘要那一行講「cropped to W × H px at (x, y)」 |
| 裁的地方 | `crop_dialog.crop_array` 一處 | 預覽與疊進去的必須是同一塊 |

## 4. 沒做的

* 框不存進 recipe。存了會變成「recipe 綁一張圖」，而模板本身已經在 recipe 裡。
* 不自動偵測缺陷位置去避開。那是猜；使用者拉框是一秒的事。
