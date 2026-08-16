# F9 —— 影像流的身分綁在「線」上（真正的 DAG）

> 狀態：**計畫中**（2026-08-16 使用者定調要做 B）
> 前置：F8 已完成；存檔 recipe 已移除；範例 recipe 已清空

## 1. 一句話

把影像流的身分從**全域的名字**改成**「哪個節點的哪個輸出埠」**，
於是同一條 `ref` 可以分岔成兩條互不干擾的支線，而每條線帶著自己的 feature。

## 2. 為什麼是現在

B 一向最貴的部分是**相容性** —— 改資料模型會讓使用者手上的 recipe 全部失效。
而這一刻：

- **存檔 recipe 已經移除**（2026-08-16），使用者手上不會有任何 recipe 檔；
- **範例 recipe 已經清空**（`examples/` 整個移除）；
- repo 裡的 recipe 只剩 `tests/fixtures/recipes/` 兩份，是我們自己的。

**所以遷移成本現在是零，之後只會變貴。** 這是做 B 最便宜的時間點。

## 3. 現在是什麼樣子

| | 現況 |
|---|---|
| **執行順序** | ✅ 已經是 DAG —— `execution_order()` 對 `route 相鄰對 ∪ edges` 做拓撲排序 |
| **資料** | ❌ 全域名字表 —— `Context.images` 是 `{"test": arr, "ref": arr, "diff": arr}` |

分支做不到的原因**在資料不在順序**：兩條分支各自處理 `ref`，寫回的是同一個
格子，後寫的蓋掉先寫的 —— 結果不是分支，是串聯。

```
        ┌── denoise A (ksize=3) ──▶ 寫回 ref
ref ────┤
        └── denoise B (ksize=9) ──▶ 寫回 ref     ← 蓋掉 A
```

## 4. 核心設計：卡片一行都不用改

**這是讓 B 從「重寫引擎」變成「改引擎的接線」的關鍵。**

卡片現在的樣子是：

```python
def run(self, ctx, params):
    img = ctx.require_image(params["source"])    # 用名字要一張圖
    ctx.set_image(params["out"], result)         # 用名字寫回去
```

新模型**不動這個介面**。改的是「跑一張卡之前，`ctx` 裡有什麼」：

```
現在   ── 一個 ctx 從頭傳到尾，每張卡都看得到所有流 ──
        load ─▶ ctx{test,ref} ─▶ denoise ─▶ ctx{test,ref} ─▶ subtract ─▶ …

之後   ── 每張卡拿到的是「照它的線組出來的」一個小 ctx ──
        produced[(load,"test")] ─┐
                                 ├─▶ denoise 看到 ctx{test}      → produced[(denoise,"test")]
        produced[(load,"ref")]  ─┴─▶ …
```

引擎多做兩件事，卡片全部無感：

1. **跑之前**：照這個節點的**入線**組一個只含它該看到的流的 `Context`；
2. **跑之後**：把它寫出來的流收成 `produced[(node_id, out_name)]`。

`Step.run()` 的簽章、17 張卡的程式碼、`ParamSpec`、`validate_params`
**一律不動**。I3 那條測試（宣告什麼就只碰什麼）正好是這件事的前提 ——
卡片如果會偷讀沒宣告的流，這個模型就組不出正確的小 `Context`。
**先有 I3，B 才安全**（已於 2026-08-16 完成）。

### 4.1 邊要帶什麼

```
現在：edges = [[src_node, dst_node], …]
之後：edges = [[src_node, src_out, dst_node, dst_in], …]
```

`src_out` = 來源節點的哪個輸出埠（`"ref"`）；
`dst_in` = 落在下游卡的哪個**輸入參數**（`"b"`、`"streams"`…）。

綁**參數名**而不是流名，是因為流名之後只是**顯示用的標籤** —— 使用者把
`ref_2` 改叫 `ref_soft`，接線不該因此斷掉。

### 4.2 feature 也跟著線走

```
現在：ctx.features = {"glv_max": 12.0, …}                 扁平、全域
之後：produced_features[(node_id, "glv_max")] = 12.0      綁在節點上
```

匯出（CSV／KLARF／score 表達式）時**攤平成一個名字**。攤平規則見 §6 決策 D2。

## 5. 波及範圍（誠實列出來）

| 模組 | 要改什麼 | 風險 |
|---|---|---|
| `pipeline/recipe.py` | edges 四元組、`execution_order` 改讀新 edges、舊格式遷移 | 中 |
| `pipeline/engine.py` | 每個節點組 local Context、收 outputs、trace 帶節點身分 | **高**（核心）|
| `pipeline/context.py` | `images` 仍是 dict（局部視圖），新增「這個視圖是哪些線組的」 | 低 |
| `pipeline/cache.py` | 快照從「一個全域表」變成「一組 (node, port) 產出」；`FORMAT_VERSION` +1 | 中 |
| `store/results.py`、`export/*` | 吃攤平後的 feature dict → **只要攤平規則穩定就不用動** | 低 |
| `pipeline/expression.py` | 表達式仍吃扁平名字 → **不動** | 低 |
| `ui/viewmodel.py`、`ui/canvas.py` | 邊帶埠、分支、輸出改名、`available_streams` 改成「沿線可見」 | 高 |
| 17 張卡 | **不動**（§4） | — |

## 6. 要先定的三個決策

### D1. defect 層級與跨線的 feature 掛哪

有三類 feature 天生不屬於單一條線（都在使用者的截圖裡出現過）：

| 例子 | 它描述什麼 |
|---|---|
| `n_channels` | 這顆 defect 有幾張圖 |
| `align_dx` / `align_dy` / `align_score` | **兩條線之間**的關係 |
| `cross_count` / `locate_ok` / `cross_pitch_*` | **具名區域**的屬性（`roi_cross` 吐的是框不是影像流）|

**提案**：feature 一律掛在**產出它的節點**上（不是線上）。節點本來就只有一個，
所以三類全部有明確的家；「沿著線累積」變成「沿著**線的上游節點集合**累積」，
語意一樣而且沒有例外。

### D2. 攤平成什麼名字

匯出與 score 表達式需要扁平的名字。**提案**：

1. 沒有撞名 → 就用原名（`glv_max`）。使用者看到的跟現在一樣。
2. 撞名 → 自動加前綴，前綴預設是**那條線的名字**（`ref_soft_glv_max`）。
3. 使用者仍可用 `output_prefix` 自己指定。

好處：不用發明 `ref_soft.glv_max` 這種語法 —— 寫 score 的是不會寫 code 的
工程師，多一種語法就是多一道牆。

### D3. 快取的切點

現在的 checkpoint 是「執行順序上最後一張影像段卡的下一格」。DAG 之後那不再是
一個點。**提案**：快照 = checkpoint **之前所有節點的產出集合**，
key 照舊是 recipe 簽章；`FORMAT_VERSION` +1 讓舊快取自動失效。

## 7. 分段交付（每一段結束時測試都要是綠的）

| 段 | 內容 | 驗收 |
|---|---|---|
| **F9-1** | edges 四元組 + 遷移 + `execution_order` | 既有 recipe 跑出來的分數**逐項相同** |
| **F9-2** | 引擎改成 per-node local Context（卡片不動） | 同上；I2/I3 全綠 |
| **F9-3** | feature 綁節點 + 攤平規則 | CSV／KLARF／rescore 的輸出**逐位元組相同**（沒有撞名時）|
| **F9-4** | 快取改成產出集合 | 冷跑＝熱跑逐位元組相同 |
| **F9-5** | UI：埠、分支、輸出改名、沿線可見 | 拉得出兩條互不干擾的支線 |
| **F9-6** | 量測卡 pass-through 輸出埠 + 設定區來源唯讀 | 線接得下去；設定區改不動來源 |

**每一段的驗收都是「跟改動前算出來的數字一樣」** —— 這是唯一擋得住
「重構完跑得動、但答案悄悄變了」的方法。F9-1 之前先把現有 fixture recipe 的
完整 feature 表凍成黃金值，之後每一段都對它。

## 8. 不做什麼

- **不改 `Step.run()` 的簽章**，也不改任何一張卡。
- **不改 score 表達式的語法**（見 D2）。
- **不做自由畫布的其他功能**（多 reference AND、子圖…），那是 v2 backlog。
