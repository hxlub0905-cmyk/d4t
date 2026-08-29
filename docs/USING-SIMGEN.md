# 用 Golden Cell 產一批模擬資料（simgen）

**給使用者的操作手冊。** 貼一張 Golden Cell 進去，拿到一整批 d4t 讀得動的
資料 —— RSEM 大圖、patch，還有（選配）給訓練用的乾淨版與缺陷遮罩。

> **這個視窗不認識任何一種 layout。** 週期是量出來的，缺陷落點是量出來的
> 或你自己畫的。換一張 GC、換一個世代、換一層，這裡一格都不用改。
> （最高指導原則：站點差異封裝進資料，不封裝進程式碼。）

> ⚠ **產出來的資料跟原始影像一樣敏感。** GC 通常是廠內圖案，鋪出來的東西
> 就是廠內圖案。工具自己會印這句話 —— **不要 commit**，也不要放進 repo
> 底下（鐵則 8）。

怎麼開：

```bash
python -m d4t simgen
```

（刻意**不在** Studio 的工具列上。這是造資料的視窗，不是分析流程的一步。）

---

## 一分鐘的版本

1. `Ctrl+V` 貼一張 GC。
2. 看 **2 Period** 那兩個數字對不對；不對就自己填。
3. 按 **Fill the inner spaces**，再用筆刷補幾筆。
4. **4** 那條樣本帶看起來像你的缺陷了，就往下。
5. 選資料夾 → **Generate**。

其他每一格的意思在下面。

---

## 1 · The Golden Cell

四條路，隨便哪一條都可以，結果一模一樣：

| 怎麼給 | 什麼時候用 |
|---|---|
| **Paste image (Ctrl+V)** | 最快 —— 螢幕截圖直接貼，不必先存檔 |
| **Open image…** | 手上已經有 PNG／TIF |
| **Open recipe…** | 從 recipe 的模板那一格（`gc2:…`）取，跟你正在跑的 pipeline 用同一張 |
| 底下那個文字框 | 別人把 `gc2:205x73:205x73:eJx…` 這串貼給你 |

貼進來之後上面會顯示尺寸。**GC 至少要兩個週期寬**，理由見下一節。

## 2 · Period

**Across (px)** / **Down (px)** ＝ 這張 GC 圖案重複一次是幾個像素。
貼進來的時候會自己量一次，**Measure again** 重量。

- 這兩個數字**允許小數**，而且應該是小數。用整數週期鋪 1000 px，接縫每鋪
  一次累積一點偏移，鋪滿之後看得出來；取樣是雙線性的，非整數也接得準。
- **不到兩個週期寬的 GC 量不準，這是原理上的事，不是 bug。** 只有一個週期
  的話沒有東西可以比對。旁邊會出現提醒 —— **知道答案就直接填**。
- 量錯的樣子很好認：下面第 3 節的鋪圖預覽會出現**斷掉的接縫**或**鬼影**。
  預覽接得順，這兩個數字就是對的。

## 3 · Where defects can appear

**畫在一個週期上就等於畫在每一個重複上**（反正都是回推）。所以你塗的是
GC 那張小圖，下面的預覽即時顯示鋪開之後的樣子。

| | |
|---|---|
| **Brush** / **Rectangle** / **Erase** | 塗、拉框、擦掉 |
| **Size** | 筆刷半徑 |
| **Fill the inner spaces** | 從它自己量到的 MG／EPI 交界開始，再用筆刷改 |
| **Clear** | 從白紙開始 |

**Fill the inner spaces** 量的是：列平均的極大值 → EPI 亮帶；那幾列上的欄
平均 → MG 亮條；亮條的左右緣 → 交界。你的缺陷不在那裡（例如只在
line end、只在某一根特定的 MG 上），就自己畫。

下面那行字會說現在有幾個落點。**空的話缺陷會種在自動量到的位置**；一顆都
量不到又什麼都沒畫，就種在 GC 正中央。

## 4 · What a defect looks like

| 這一格 | 意思 | 調大會怎樣 |
|---|---|---|
| **Size (across)** | 缺陷的直徑範圍（px），每顆在區間內隨機 | 大顆、好抓 |
| **Contrast** | 跟背景差幾階灰（絕對值） | 亮的更亮／暗的更暗，`dSNR` 往上 |
| **Bright or dark** | 亮、暗、或隨機各半 | — |
| **Bridges** | 有幾成的缺陷是**橋接**（把相鄰兩條線連起來的一小段），不是點 | 只看局部對比的算法會漏掉的那一類變多。0 ＝ 不要 |

「直徑」是 **FWHM**（半高全寬），跟這個 repo 其他地方對「寬度」的定義同一個
—— 填 6 就是量起來 6，不是 σ。

底下那條**六顆樣本**是用你現在這幾格、在真的圖案上即時種出來的，而且抽的
比例就是 **Bridges** 那個比例（不是三選一等機率）。**它用固定的隨機種子**
—— 你一格一格微調的時候，變的只有設定，不會混進「剛好抽到不一樣的」。

## 5 · How many

| 這一格 | 意思 |
|---|---|
| **RSEM images** | 大圖幾張。一張大圖 = 一顆 KLARF defect |
| **Image size (px)** | 大圖邊長。實機 1000×1000 |
| **Patches (defects)** | patch 幾顆。**從大圖上切下來的**，不是另外畫的 |
| **Patch size (px)** | patch 邊長。EBI 常見 81 |
| **Real defects** | 有幾成的 patch 真的有缺陷。其餘是 nuisance（乾淨的），寫在 ground truth 裡是 `is_real: false` |
| **Noise σ** | 高斯雜訊的強度（灰階）。0 ＝ 不加 |
| **Seed** | 同一組設定 ＋ 同一個 seed ＝ 逐位元組同一批資料 |
| **Also write a clean copy and a mask** | 見下一節 |

**Real defects 不是 100 才對。** 你要驗的通常是「分得開嗎」，那就要有分不開
的那一半。50% 是常用的起點。

## 6 · Write it out

選一個資料夾（**不要選 repo 底下**）→ **Generate**。跑的時候可以 **Stop**。

跑完長這樣：

```
OUT/rsem/images/IMG_0001.png     1000×1000，一張一顆
OUT/rsem/LOT_RSEM.001            KLARF 1.8
OUT/patch/LOT_SYN.tif            一顆兩頁（test, ref）
OUT/patch/LOT_SYN.001            KLARF 1.2
OUT/{rsem,patch}/ground_truth.json
```

兩份都是 d4t 直接讀得動的 —— Studio 的 `Open KLARF…` 挑那個 `.001`。

`ground_truth.json` 的 key 是 defect id：

- patch：`{"is_real": false, "type": "none", "x": …, "y": …}`
- rsem：每張圖一串 `{"kind", "x", "y", "contrast", "size"}`

### 勾了 pairs 會多出來的東西

```
OUT/rsem/clean/IMG_0001.png      同一張，沒有缺陷，**同一份雜訊**
OUT/rsem/masks/IMG_0001.png      缺陷足跡（白 = 有）
OUT/patch/clean.tif  OUT/patch/masks.tif
```

**乾淨版與缺陷版共用同一個 speckle 陣列** —— 兩張圖的差別**只有**缺陷本身。
遮罩之外實測 99.9% 逐位元組相同（剩下的是 blob 尾巴溢出遮罩門檻一點點）。
這是 GAN／segmentation 要的那種配對資料；沒有這個性質的話，網路會學到
「雜訊不一樣」而不是「這裡有缺陷」。

輸出大小大約變成兩倍。

---

## 擬真：為什麼看起來不完美

完美鋪出來的圖每一格一模一樣，而真的機台不會。所以預設會加四件事：

| | 大概多少 |
|---|---|
| **MG 微微扭**（低頻位移場） | 亞像素到 1 px 級 |
| **線緣粗糙**（LER） | 同上，但空間頻率高很多 |
| **每一格的 GLV 不完全一樣**（gain／bias） | 相隔一個週期差 ~13 灰階（完美鋪圖是 0.4）|
| **大範圍的明暗不均** | 一張圖裡低頻擺幅 ~8 灰階 |

最後那一項刻意**壓得很輕**：真的機台不會忽亮忽暗（電流不會差那麼多），
有 GLV 差異但沒那麼明顯。

CLI 的 `--flat` 全部關掉，回到完美鋪圖 —— 要拿它當基準線的時候用。

---

## 命令列（同一支引擎）

UI 只是介面，算的東西住在 `tools/make_lot_from_gc.py`。要跑一整排參數掃描
就直接用它：

```bash
python3 tools/make_lot_from_gc.py OUT --recipe my_recipe.json \
    --images 10 --size 1000 --defects 60 --patch 81 \
    --period-x 175.96 --period-y 34.0 \
    --bridge-frac 0.05 --polarity both --seed 23 --pairs
```

| 旗標 | 對應到 UI 哪一格 |
|---|---|
| `--gc` / `--recipe` | 1 · The Golden Cell |
| `--period-x` / `--period-y` | 2 · Period（留空就自己量）|
| `--images` `--size` `--defects` `--patch` `--real-frac` `--noise` `--seed` | 5 · How many |
| `--bridge-frac` `--polarity` | 4 · What a defect looks like |
| `--pairs` | 5 的那個勾勾 |
| `--flat` | 關掉擬真（UI 上沒有）|
| `--format` | 大圖的副檔名 |

CLI **沒有**「畫落點」那一格 —— 那是 UI 才有的（它會用自動量到的
inner space）。要非預設的落點就走 UI。

---

## 出事了照這個順序查

1. **預覽的接縫斷掉／有鬼影** → 週期錯。GC 不到兩個週期寬就自己填
   （2 · Period）。這是最常見的一個，而且它會讓下面每一件事都怪怪的。
2. **缺陷跑到不該去的地方** → 第 3 節那塊什麼都沒畫，所以用的是自動量到的
   落點。按 **Fill the inner spaces** 看看它量到哪，再改。
3. **樣本帶是六格空白** → GC 還沒貼，或 **Bridges** 100% 但週期太小放不下
   一根橋。
4. **一顆 bridge 都沒有** → 比例乘上顆數不到 1。60 顆 × 5% ≈ 3 顆，實測
   會抽到 1–3 顆之間；要穩定看到就把顆數或比例調上去。
5. **Studio 開不起來那批** → 挑的是 `.001` 那個檔嗎（不是 `.tif`、不是資料夾）。
6. **兩次跑出來不一樣** → Seed 不同，或第 3 節的塗鴉動過了。

---

## 相關

- 資料怎麼進 d4t、四種 source 的差別：[`CLAUDE.md`](../CLAUDE.md) §5
- 這批資料要拿去跑什麼：[`docs/USING-CHARACTERIZATION.md`](USING-CHARACTERIZATION.md)
- 引擎與測試：`tools/make_lot_from_gc.py`、`tests/test_make_lot_from_gc.py`
- 介面：`d4t/ui/gc_generator.py`、`d4t/ui/gc_paint.py`
