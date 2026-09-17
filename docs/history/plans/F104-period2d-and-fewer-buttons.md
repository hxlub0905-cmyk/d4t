# F104 — 二維自相關找峰；模板對話框收回一列；Mark one cell 刪掉

狀態：**已收斂（2026-09-17）** —— 使用者看過 F102/F103 之後定的三件事，當天做完。

## 1. 使用者說了什麼

> 1. 按鈕還是太多，crop 相關功能請直接接進 Rebuild from image（mark one cell 功能也拿掉，不實用）
> 2. 你上面說的交錯圖形還沒解 → 請幫忙做二維自相關找峰
> 3. Check on the image 改成類似格線的開關按鈕，可以開啟顯示或關閉顯示格線

## 2. 二維自相關（`core/algo/period2d.py`）

交錯 layout（每隔一列錯半格）上投影法的 X 軸互相抵消：實測合成的 32 × 24、隔列錯 16
的晶格，`estimate_period` X 軸回 **None**、Y 軸回 24（一列的高度，不是重複單元）。
二維自相關不投影：整張圖跟自己平移 (dx, dy) 之後有多像，矩形重複單元就是這張面上
沿 X 軸（dy = 0）與沿 Y 軸（dx = 0）離原點最近的峰 → **32 × 48**。規則晶格、條紋、
純雜訊三種跟投影法答案一模一樣（平的軸靠「軸線上 > 0.9 的比例過半」擋掉）。
中央 1536² 視窗、去背景（高斯低通）、FFT，幾毫秒。

**分工**（`template._measure_period`）：投影法是主，兩個同意就什麼都不改（黃金值不動）。
只在兩種情況採用二維：投影那一軸量不到而二維量得到；二維是投影的整數倍（±1 px）。
每一次接手都在 warnings 講一句。`tests/test_period2d.py` 十條。

## 3. 對話框（`ui/template_dialog.py`）

| 以前 | 現在 |
|---|---|
| 兩列十一個東西 | **一列**：Use the image on screen ／ Rebuild from image… ／ Cell W、Cell H、×2、Re-stack ／ **Grid**（開關）／ 檔名 |
| 「Crop first」勾選 ＋「Crop…」鈕 | 沒有。載入大圖（挑檔案或畫面上那一張）**一定**先出現「Where to measure the cell」：拉一塊、整張、或取消。Re-stack 沿用那一塊 |
| 「Mark one cell…」（F103 seed） | **刪掉**（使用者：不實用）。`core/algo/seed.py`、`build_golden_cell(origin=)`、對話框的 seed 模式與測試一起拿掉；`GoldenCell.origin` 留著（格線要用） |
| 「Check on the image…」開一個視窗 | **Grid** 可勾選的開關：開＝格線視窗出現並跟著 re-stack 更新，關＝收起來；使用者直接關視窗，開關跟著彈回 |

## 4. 沒做的

* 斜的 layout：二維自相關在 7° 上仍量得到週期（信心 61），疊出來會糊，`cells agree`
  會說。要真的解要先估角度再轉正，那是另一件事。
