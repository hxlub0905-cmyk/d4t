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
GitHub 產生的 zip **不含 `.git` 資料夾**，所以裡面 170 個檔案全部是純文字
（`.py` / `.md` / `.json` / `.toml` / `.txt` / `.yml` / 一份 `.klarf`），約 830 KB。

### 如果 Download ZIP 被公司擋掉

**這件事跟 repo 的內容不一定有關係**，先分辨是哪一種 —— 三種原因的處置完全不同：

| 先做這個測試 | 結果 | 那就是 |
|---|---|---|
| 直接開 `https://codeload.github.com/hxlub0905-cmyk/ADEPT/zip/refs/heads/main` | 這個網址被擋，但 `github.com` 的網頁看得到 | **主機層的封鎖**。Download ZIP 其實是從 `codeload.github.com` 出來的（不同主機），公司的 allowlist 常常只放了 `github.com`。請 IT 加 `codeload.github.com` |
| 隨便下載另一個無關的公開 repo 的 zip | 也被擋 | **政策層面禁止 .zip 這個類別**，跟哪個 repo 無關。走下面的替代路徑 |
| 上面兩個都正常，只有這個 repo 的 zip 被擋 | — | **DLP 掃到了內容**。看 §「DLP 掃內容」那一段 |

替代路徑（依省事程度排）：

1. **改抓 `.tar.gz`**：把網址的 `/zip/` 換成 `/tar.gz/`（同一台主機，但有些
   規則只列了 `.zip`）。Windows 的 `tar -xf` 從 Win10 1803 起內建。
2. **請 IT 放行 `codeload.github.com`**（如果測試指向主機層封鎖，這是根治）。
3. **逐檔抓純文字**：`raw.githubusercontent.com` 送的是 `text/plain`，DLP 對它的
   規則跟 `application/zip` 完全不同，常常是通的。170 個檔案手抓不現實，但
   只要先手抓一支 stdlib-only 的小腳本，剩下的就交給它。需要的話開 issue，
   我們把那支腳本加進 `tools/`。

### DLP 掃內容

如果只有這個 repo 的 zip 被擋，那要看的是**裡面有沒有公司的識別碼**。
`tests/fixtures/sample_real.klarf` 是唯一一份真實來源的檔案（它就是這樣抓到
KLARF variant D 的），它裡面的 Lot／Wafer／機台／device／**recipe 名稱**
（recipe 名稱通常編碼了層別與製程步驟）與缺陷分類名稱**都已經遮蔽成合成值**，
而且有一支測試守著（`tests/test_no_real_fab_data.py`）：

```
pytest -q tests/test_no_real_fab_data.py
```

加新 fixture 時那支測試會擋下沒遮蔽的值。**遮蔽是等長替換，測試只看結構不看值，
所以遮蔽不會弄壞任何斷言。**

⚠ 遮蔽只影響「現在的檔案」。**已經推上去的 git 歷史裡還留著原本的值** ——
DLP 掃的是下載下來的 zip（GitHub 的 zip 不含 `.git`，所以看不到歷史），
但如果要求是「repo 裡完全不能有」，那需要重寫歷史或把 repo 改成 private。

## 2. 安裝相依套件

```
cd ADEPT-main
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

需要 4 個套件：`numpy`、`opencv-python`、`tifffile`、`PySide6`。

**如果公司擋 pip 對外連線**（很常見）：改走離線 wheels ——
在有網路的機器上 `python tools/fetch_wheels.py`，把產生的 `wheels\` 資料夾帶進公司機，
再跑 `python tools/install_offline.py`。完整步驟與疑難排解見
**[`docs/OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md)**。

裝完（或安裝失敗想知道卡在哪）都可以跑環境自檢：

```
python tools/doctor.py
```

它會逐項檢查 Python 版本、每個套件、Qt 能不能開視窗、資料夾權限，
每個沒過的項目都附一行「怎麼修」。

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
