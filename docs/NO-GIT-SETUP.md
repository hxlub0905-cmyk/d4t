# 在沒有 git 的機器上使用 ADEPT

適用情境：**公司機沒有 git（或 git 被擋），你習慣從 GitHub 按「Download ZIP」
把整包下載下來，直接用 Python 跑。**

ADEPT 完全支援這種用法 —— 整個 repo 只有純文字檔（`.py` / `.md` / `.json` /
`.toml` / `.txt` / `.yml`），沒有任何執行檔或二進位檔，不需要 git 也能跑。

---

## 1. 取得程式碼

到 `https://github.com/hxlub0905-cmyk/ADEPT` → 綠色 **Code** 按鈕 →
**Download ZIP** → 解壓到任意資料夾。

解壓後會得到 `ADEPT-main\`，裡面就是完整程式碼。
（GitHub 產生的 zip **不含 `.git` 資料夾**，所以是純文字包，
企業 DLP 掃描不會有問題。）

## 2. 安裝相依套件

```
cd ADEPT-main
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

需要 4 個套件：`numpy`、`opencv-python`、`tifffile`、`PySide6`。

**如果公司擋 pip 對外連線**，請在有網路的機器上先下載離線 wheels：

```
pip download -r requirements.txt -d wheels --platform win_amd64 ^
    --python-version 39 --only-binary=:all:
```

把 `wheels\` 資料夾一起帶進公司機，然後：

```
pip install --no-index --find-links=wheels -r requirements.txt
```

## 3. 確認能跑

```
python -m adept steps
```

會列出全部步驟卡片。看得到「影像段 IMAGE / 算法段 ALGO」就代表裝好了。

跑測試（可選，需要 `pip install pytest`）：

```
set QT_QPA_PLATFORM=offscreen
pytest -q
```

## 4. 產一份合成資料試玩（不需要真實 KLARF）

```
python tools\make_sample.py C:\temp\lot --n 100
```

會產生 `LOT_SYN.001`（KLARF）、`LOT_SYN.tif`（patch 影像）、
`ground_truth.json`（哪些是真缺陷，供你驗證算分效果）。

## 5. 開圖形介面

```
python -m adept gui
```

在 Studio 裡：**開啟 KLARF** 選剛才的 `LOT_SYN.001` → **載入範本（die-to-die）**
→ **試跑** → 拖下方的門檻線看 bin 數變化。

## 6. 命令列批次

```
python -m adept run examples\recipes\die_to_die_basic.json C:\temp\lot\LOT_SYN.001 ^
    --workers 4 --cache C:\temp\cache --csv features.csv
```

---

## 沒有 git 的情況下，怎麼保存你的修改

你的 recipe 存成單一 JSON 檔（Studio 裡「存 Recipe」），那才是你的心血結晶 ——
程式碼可以隨時重新下載，recipe 不行。建議把 `examples\recipes\` 底下的檔案
另外備份一份到你自己的資料夾。

如果改了程式碼（例如加了新的步驟卡片），把改動的 `.py` 檔另外複製一份留底；
之後在有 git 的機器上再合併回 repo。
