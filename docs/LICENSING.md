# d4t 授權與來源

這一份是**授權的唯一出處**：d4t 自己現在是什麼授權狀態、vendoring 進來的東西
從哪來、跑起來會用到誰的程式碼。其他文件要講到這些，一律連過來。

- 六個來源專案的**技術脈絡**（拿了什麼、刻意沒拿什麼）在
  [`HANDOVER.md`](HANDOVER.md) §3 —— 這一份只管**授權**那一面。
- 每一支 vendored 模組的**改動清單**在那支模組自己的檔頭，不在這裡。

> 下面每一條 GitHub 事實都是 **2026-08-28** 查的（GitHub API）。
> 可見性與 LICENSE 檔會變，改了就回來改這一份。

---

## 1. d4t 自己：**專有／內部使用**

2026-08-28 使用者定案：**專有（proprietary）、僅限組織內部使用**，
措辭跟 KLIP 那份對齊（§2）。

| | |
|---|---|
| repo | `hxlub0905-cmyk/d4t` |
| 可見性 | **public** ⚠ 見下 |
| `LICENSE` 檔 | [有](../LICENSE) —— `PROPRIETARY — INTERNAL USE ONLY` |
| `pyproject.toml` 的 `license` 欄位 | 有（`license = {file = "LICENSE"}`）|

打包出來的 wheel 因此帶著
`License: PROPRIETARY — INTERNAL USE ONLY`，而 `LICENSE` 全文會裝進
`dist-info/licenses/` —— 拿到套件的人不必回 GitHub 才看得到條款。

`LICENSE` 裡有一句話值得單獨指出來：**它不涵蓋執行時的相依套件**。
專有的聲明蓋不住 numpy／OpenCV／PySide6 —— 那些仍然各自照自己的授權走（§4）。
少了那一句，一份「全部保留」的聲明會把 LGPL 的 PySide6 一起蓋進去，
而那正是不能做的事。

> ⚠ **`pyproject.toml` 用的是 `license = {file = ...}` 這個舊寫法**，
> 不是 PEP 639 的 `license = "LicenseRef-…"`。後者要 `setuptools>=77`，
> 而 `build-system` 的底線是 `>=61`（廠內機器可能是舊版 —— 這個 repo 到處在
> 防的就是這件事）。新版 setuptools 會對舊寫法發 deprecation warning：
> 那是**警告不是錯誤**，等底線抬到 77 再換。

### ⚠ 還沒關掉的那一件：repo 是 public

授權寫的是「未經書面同意不得在組織外使用」，而 repo 現在**任何人都看得到**。
這兩件事不矛盾（公開原始碼 ＋ 保留所有權利是成立的組合），但它讓 §2 那個
**營業秘密**的問題原封不動地留著 —— 見下一節。

**轉不轉 private 是所有權人的決定**，這一份不代下。

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

**加上 `LICENSE` 沒有解掉這一條。** 2026-08-28 那一份寫的是「專有／內部使用」
—— 它把**授權**講清楚了（誰可以用），但營業秘密缺的是**未公開**這個事實狀態，
而那個狀態由 repo 的可見性決定，不由 LICENSE 的文字決定。
一份寫著「內部使用」的公開 repo，在授權上沒有問題，在營業秘密上仍然是公開的。

這一份文件只負責把事實寫下來：**要不要把 d4t 轉 private，是所有權人的決定**，
不是這份文件（或任何一個 session）能替他下的。真的要處理的話，記得 git 歷史
也留著同一份檔案 —— 轉 private 之前先讀
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

> **2026-08-28 使用者定調：先別動**（F48）。所以這一條不是待辦，是一個
> **明知而暫緩**的狀態 —— 目前 d4t 只在組織內部使用（§1），那個問題還沒到
> 檯面上。**觸發條件寫在這裡，因為到時候不會有人回來翻這一段**：要出貨給
> 客戶、給別的法人、或 repo 轉成任何形式的對外散布時，這一條要先關掉。

> 這一條跟 [`FAB-VALIDATION.md`](FAB-VALIDATION.md) 裡那些「待驗證的假設」
> 同一個性質：**寫下來、標成未確認，比裝作沒這件事好。**

---

## 5. 這個決定是怎麼下的，還剩什麼沒關

2026-08-28，使用者：「專有 內部license加進去」。三條路當時列著，選了第一條：

| 選擇 | | 為什麼 |
|---|---|---|
| **專有／內部使用** | ✅ **選了這個** | 跟 KLIP 那份宣告一致 —— d4t 裡放著它的 `klarf_core.py` 整檔（§2），兩份文件不該互相打臉 |
| MIT | ✗ | 要先處理 §2：把一份宣告為營業秘密的檔案用 MIT 放出去，那兩句話沒辦法同時成立 |
| Apache-2.0 | ✗ | 同上 |

**六個來源專案都是自己的（§2），所以沒有任何一條路被第三方擋住。**
擋路的只有 KLIP 那份自我宣告，而選了第一條之後那個張力消失了 —— 兩邊現在說
同一句話。

做掉的：

- [x] repo 根加 `LICENSE`（`PROPRIETARY — INTERNAL USE ONLY`，措辭對齊 KLIP）
- [x] `pyproject.toml` 補 `license = {file = "LICENSE"}` —— 打包出來的 wheel
      帶著授權欄位、`LICENSE` 進 `dist-info/licenses/`（驗過）
- [x] `LICENSE` 裡明講**不涵蓋第三方相依**（否則會把 LGPL 的 PySide6 一起蓋進去）

**還沒關的一件（所有權人決定，不是工程決定）：**

- [ ] **repo 還是 public。** 授權寫「內部使用」不會讓一份公開的檔案變成未公開
      —— §2 那個營業秘密的前提還是不在。要關就是轉 private，而 git 歷史裡
      也留著同一份檔案（見 [`../AGENTS.md`](../AGENTS.md) §3.5）。

      **2026-08-28 使用者：「我之後會轉 private」**（F48）。所以這一格
      **不是等決定，是等執行** —— 決定下了，動作在所有權人手上（那個開關
      工程這邊按不到）。轉完之後把這一格打勾，並回頭讀 §2：營業秘密那個
      前提要到那時候才真的成立。

**還沒問過的一件：** §4 的 PySide6 那條離線搬 wheel 的路算不算 LGPL 意義下的
散布 —— 那是法務問題。加上 `LICENSE` 沒有回答它，因為那份 `LICENSE` 管的是
**d4t 自己的程式碼**，管不到 Qt。

---

## 6. 這一份有測試守著

`tests/test_licensing_doc.py`：

* §3 那張表要跟磁碟一致 —— 檔頭寫著 vendored 的模組少一支或多一支都會紅
  （加一支 vendored 模組而忘了寫進來，正是這種表爛掉的方式）；
* §4 那張表要蓋到 `pyproject.toml` ＋ `requirements.txt` 宣告的每一個套件；
* **`LICENSE` 真的在**，而且 `pyproject.toml` 指著它 —— 一份說「已經加了授權」
  的文件配上一個不存在的檔案，比沒有那份文件更糟；
* **`LICENSE` 的第三方 carve-out 要蓋到每一個相依套件。** 這一條看起來多餘，
  它不是：一份「保留所有權利」的聲明只點名五個套件、漏掉第六個 LGPL 的，
  就是把那一個蓋進了自己的專有聲明裡。加相依套件的時候，`LICENSE` 與 §4
  **兩邊都要加**，而這一條會告訴你漏了哪一邊；
* 還有一支反向的：**parser 真的抓得到表格** —— 不然上面幾條會安靜地永遠綠。

它抓不到的：授權**內容**對不對、GitHub 上的可見性有沒有變。那兩件事只有人
回來看才知道，所以這一份頂上寫著查證日期。
