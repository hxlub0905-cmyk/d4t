# d4t 授權與來源

這一份是**授權的唯一出處**：d4t 自己現在是什麼授權狀態、vendoring 進來的東西
從哪來、跑起來會用到誰的程式碼。其他文件要講到這些，一律連過來。

- 六個來源專案的**技術脈絡**（拿了什麼、刻意沒拿什麼）在
  [`HANDOVER.md`](HANDOVER.md) §3 —— 這一份只管**授權**那一面。
- 每一支 vendored 模組的**改動清單**在那支模組自己的檔頭，不在這裡。

> 下面每一條 GitHub 事實都是 **2026-08-28** 查的（GitHub API）。
> 可見性與 LICENSE 檔會變，改了就回來改這一份。

---

## 1. d4t 自己：**還沒有授權**

| | |
|---|---|
| repo | `hxlub0905-cmyk/d4t` |
| 可見性 | **public** |
| `LICENSE` 檔 | **沒有** |
| `pyproject.toml` 的 `license` 欄位 | **沒有** |

**沒有授權聲明不等於「隨便用」。** 著作權的預設是**保留所有權利** ——
沒有人被授予重製、修改、散布的權利。看得到不等於用得到，一個公開但無授權的
repo 對讀到它的人來說是「不能合法使用」，不是「公有領域」。

**這是還沒決定，不是決定了不寫。** 要下決定的那一天看 §5，那裡列了三條路
各自的後果。

---

## 2. vendoring：六個來源專案**都是同一個作者自己的**

d4t 的演算法幾乎都從使用者既有的六個專案搬過來
（[`HANDOVER.md`](HANDOVER.md) §3）。授權上最要緊的一句話是：
**那六個專案全部是同一個人寫的、同一個 GitHub 帳號底下的**（使用者
2026-08-28 確認：「裡面的 vendoring 相關所有 APP 都是我自己寫的」）。

所以 **d4t 沒有任何第三方的 vendoring 授權義務** —— 自己的程式碼可以自己
重新授權。真正有外部義務的是**執行時的相依套件**，那在 §4。

| 來源專案 | GitHub | 可見性 | 那邊的 `LICENSE` |
|---|---|---|---|
| **KLIP** | `hxlub0905-cmyk/KLIP` | **private** | **有** —— 「PROPRIETARY — INTERNAL USE ONLY」（見下） |
| **GLAS** | `hxlub0905-cmyk/GLAS` | public | 沒有 |
| **MMH** | `hxlub0905-cmyk/MMH` | public | 沒有 |
| **PEAR** | `hxlub0905-cmyk/PEAR` | public | 沒有 |
| **cell-period-estimator (CPE)** | `hxlub0905-cmyk/cell-period-estimator` | public | 沒有 |
| **Perspective-Combination (Fusi³)** | `hxlub0905-cmyk/Perspective-Combination` | public | 沒有 |

六個裡有五個跟 d4t 現在一樣：public、無授權聲明 ＝ 保留所有權利。

### ⚠ KLIP 那一個要單獨講

KLIP 是六個裡**唯一有 LICENSE 檔**的，而它寫的是：

> PROPRIETARY — INTERNAL USE ONLY
> …proprietary and constitute trade secret material registered for internal
> Trade Secret Registration purposes.
> No part of this repository may be copied, distributed, published,
> sublicensed, or used outside the owner's organization without prior
> written permission from the owner.

而 d4t 的 [`d4t/core/ingest/klarf_core.py`](../d4t/core/ingest/klarf_core.py)
是那份 KLIP `klarf_core.py` 的**整檔搬**（90 KB，檔頭列著四項改動），
d4t 是 **public**。

**這不是授權衝突**（同一個所有權人，要授權給誰是他自己的事）。但有一件事值得
所有權人自己確認一次：**營業秘密的保護要件包含「未經公開」** ——
一份宣告為營業秘密登記素材的檔案，放在一個公開 repo 裡，那個「未公開」的
前提就不在了。

這一份文件只負責把事實寫下來：**要不要把 d4t 轉 private、或把那份宣告改掉，
是所有權人的決定**，不是這份文件（或任何一個 session）能替他下的。
真的要處理的話，記得 git 歷史也留著同一份檔案 —— 轉 private 之前先讀
[`../AGENTS.md`](../AGENTS.md) §3.5（識別碼已經進了 git 歷史怎麼辦），
那一節談的是同一類問題。

---

## 3. d4t 裡哪幾支是 vendored 的

規矩：**每一支 vendored 模組的檔頭要註明來源專案、原始檔案與改動清單。**
（`tests/test_licensing_doc.py` 守著下面這張表跟磁碟一致 —— 少一支或多一支都會紅。）

| 模組 | 來源 |
|---|---|
| [`d4t/core/algo/align.py`](../d4t/core/algo/align.py) | Fusi³ ＋ GLAS（5 backend；ecc 的正負號 d4t 修過） |
| [`d4t/core/algo/glv.py`](../d4t/core/algo/glv.py) | PEAR |
| [`d4t/core/algo/golden.py`](../d4t/core/algo/golden.py) | CPE |
| [`d4t/core/algo/histmatch.py`](../d4t/core/algo/histmatch.py) | Fusi³ |
| [`d4t/core/algo/normalize.py`](../d4t/core/algo/normalize.py) | Fusi³ |
| [`d4t/core/algo/period.py`](../d4t/core/algo/period.py) | CPE |
| [`d4t/core/algo/quality.py`](../d4t/core/algo/quality.py) | MMH |
| [`d4t/core/algo/roi.py`](../d4t/core/algo/roi.py) | Fusi³（`MultiROISet`） |
| [`d4t/core/algo/snr.py`](../d4t/core/algo/snr.py) | PEAR（SNR 正負號的規範出處） |
| [`d4t/core/algo/subpixel.py`](../d4t/core/algo/subpixel.py) | MMH（CMG recipe） |
| [`d4t/core/calibration.py`](../d4t/core/calibration.py) | MMH |
| [`d4t/core/ingest/dataset.py`](../d4t/core/ingest/dataset.py) | KLIP ＋ GLAS（改寫幅度最大的一支） |
| [`d4t/core/ingest/imageio.py`](../d4t/core/ingest/imageio.py) | PEAR（CJK-safe 讀寫） |
| [`d4t/core/ingest/klarf_core.py`](../d4t/core/ingest/klarf_core.py) | **KLIP（整檔搬）** —— 見 §2 |
| [`d4t/core/ingest/tiff_index.py`](../d4t/core/ingest/tiff_index.py) | KLIP（`klarf_tif_probe`） |
| [`d4t/ui/theme.py`](../d4t/ui/theme.py) | CPE（GLAS 暖色 token） |
| [`d4t/ui/widgets.py`](../d4t/ui/widgets.py) | PEAR（`ImageView` 的 zoom/pan 骨架） |

---

## 4. 執行時的相依套件：**外部義務只在這裡**

`pyproject.toml` 與 `requirements.txt` 宣告的那幾個。授權欄位取自 PyPI 中繼資料
（2026-08-28 查）：

| 套件 | d4t 要求的版本 | 授權 |
|---|---|---|
| `numpy` | `>=1.24` | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` |
| `opencv-python` | `>=4.8` | Apache-2.0（wheel 內另有數個 bundled 函式庫，各有各的條款） |
| `tifffile` | `>=2023.7` | BSD-3-Clause |
| `openpyxl` | `>=3.1` | MIT |
| `PySide6` ＋ `shiboken6` | `>=6.5` | **`LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`**（另有商業授權） |
| `pytest`（開發用） | `>=7` | MIT |

前四個都是寬鬆授權，照著附上授權條款就沒事。**要注意的是 PySide6。**

### PySide6 的 LGPL 值得看一眼

兩件跟這個 repo 的實際做法有關的事實：

1. **d4t 不把 PySide6 打包進去。** `pyproject.toml` 把它放在具名的 `gui` extra
   （`pip install .[gui]`），因為 CLI 那條路（`python -m d4t run`）不需要 Qt。
   所以「散布 d4t 的原始碼」不等於散布 Qt。
2. **但離線安裝那條路會搬 wheel 檔本身。**
   [`tools/fetch_wheels.py`](../tools/fetch_wheels.py)（有網路的機器抓）→
   [`tools/install_offline.py`](../tools/install_offline.py)（air-gapped 機器裝）
   之間，`PySide6` 的 wheel 是**被複製到另一台機器上**的
   （見 [`OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md)）。

搬的是**未修改的官方 wheel**，這是 LGPL 底下負擔最輕的一種情形；同一個組織
內部之間搬又跟對外散布不一樣。**但「這樣算不算散布」是法務問題，不是工程問題**
—— 真的要出貨給客戶或別的法人之前，請找公司的法務／IP 窗口確認一次。
這一份只負責讓那個對話有東西可以看。

> 這一條跟 [`FAB-VALIDATION.md`](FAB-VALIDATION.md) 裡那些「待驗證的假設」
> 同一個性質：**寫下來、標成未確認，比裝作沒這件事好。**

---

## 5. 要下 LICENSE 的那一天

三條路，代價不一樣。**這一份不替所有權人選**，只把後果寫清楚：

| 選擇 | 意思 | 要順手做的事 |
|---|---|---|
| **專有／內部使用**（跟 KLIP 同一套措辭） | 跟 §2 那份宣告一致，是目前現況最自然的延伸 | 加 `LICENSE`；`pyproject.toml` 補 `license`；**認真考慮把 repo 轉 private**（否則 §2 那個「未公開」的前提還是不在） |
| **MIT** | 最寬鬆的開放授權 | 加 `LICENSE`；補 `pyproject.toml`；**先處理 §2** —— 把一份宣告為營業秘密的檔案用 MIT 放出去，兩份文件會互相打臉 |
| **Apache-2.0** | 開放 ＋ 明示的專利授權條款 | 同上，另加 `NOTICE` |

三條路共通的兩件事：

* `pyproject.toml` 現在**沒有** `license` 欄位 —— 選完要補上，不然
  `pip install` 出來的套件中繼資料仍然是空的。
* 六個來源專案是自己的（§2），**所以沒有任何一條路被第三方擋住**。擋路的只有
  KLIP 那份自我宣告，而那也是所有權人自己能改的。

---

## 6. 這一份有測試守著

`tests/test_licensing_doc.py`：

* §3 那張表要跟磁碟一致 —— 檔頭寫著 vendored 的模組少一支或多一支都會紅
  （加一支 vendored 模組而忘了寫進來，正是這種表爛掉的方式）；
* §4 那張表要蓋到 `pyproject.toml` ＋ `requirements.txt` 宣告的每一個套件；
* 還有一支反向的：**parser 真的抓得到表格** —— 不然上面兩條會安靜地永遠綠。

它抓不到的：授權**內容**對不對、GitHub 上的可見性有沒有變。那兩件事只有人
回來看才知道，所以這一份頂上寫著查證日期。
