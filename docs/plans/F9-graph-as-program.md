# F9 — 圖就是程式（線變成真的資料通道）

**狀態：Phase 1–3a 完成（2026-08-15）。判定已經是畫布上的卡片。**
**剩下：輸入變卡片、`routes`/`score` 退場、卡片搬家、畫布（Phase 3b–4）。**

---

## 1. 需求從哪裡來

使用者對這個工具的定位講清楚了：

> 「我想要的是我把 Function 寫好 → 工程師只需用節點（n8n like）方式，將所想要
> 做的事自己**創造出來**。你說的什麼 ADC、ML、寫回 KLARF、output 什麼什麼東東
> 都是後面的**增加卡片**、增加節點的功能。但我現在是想要確立**大方向**。」

也就是說：**產品是那台編輯器，卡片是外掛。** 六個方向題的回答：

| | 決定 |
|---|---|
| 線要不要變成真的資料通道 | **要** |
| 誰寫卡片 | 使用者自己寫 → **不需要外掛機制**，卡片進 repo 就好 |
| 邊界 | 主要是影像 + KLARF；之後要能依 KLARF 欄位分流（例 `CLASSNUMBER=1` 走 A、`=2` 走 B）|
| 判定（ADC）要不要變卡片 | 要（卡片後做，**位置現在就空出來**）|
| 跨顆的卡 | 同上 |
| 輸入要不要變卡片 | **要**，依資料型別分 |

---

## 2. 為什麼現在做不到

**畫布上的線不搬資料。** 證據是 repo 裡唯一那份範例 recipe：

```
$ python -c "import json; print(json.load(open('examples/recipes/cross_regions.json'))['edges'])"
[]
```

九張卡、**零條線**，而它跑得完全正常。

因為真正的接線不在線上，在每張卡的參數字串裡：`normalize` 讀 `streams="test"`、
`glv_stats` 讀 `source="diff"`。資料走的是一個**全域的 `ctx.images` 字典**，
用名字取。`edges` 只影響執行順序。

三個具體後果：

1. 載入一份 recipe，畫布可能一條線都沒有，但它是對的
2. **把線刪掉，那張卡照樣讀同一條流** —— 刪線什麼都沒發生
3. 兩張卡都寫 `test`，後面那張蓋掉前面那張，畫布上看不出來

另外三件事是寫死的，而它們正好擋住上面表格裡的每一個「要」：

- **判定不是卡片**：`CATEGORY_ADC` 的卡片數是 **0**。`score`/`threshold`/`bins`
  是 `Recipe` 的固定欄位，不在圖上。
- **輸入不是卡片**：引擎先把 defect 塞進 `ctx.meta`，Load 卡去撿；而 route 是
  以 dataset kind（`ebi_patch`/`rsem`）當 key 的。
- **分流沒有地方表達**：`routes` 分的是「資料型別」，不是「資料的值」。

---

## 3. 決定：線上流的是「一顆 defect 的整包狀態」

兩個候選：

**A. 線上流一條影像流**（`test` 一條線、`ref` 一條線）
這是 F7-18～F7-21 已經投資的方向。看得出哪張圖去哪裡，但：量測卡吐十個數字，
判定卡就要接十條線；而且「`CLASSNUMBER=1` 走 A」分的是**整顆 defect**，
不是某一條影像流 —— 在 A 底下沒有自然的表達方式。

**B. 線上流一顆 defect 的整包狀態**（= 現在的 `Context` 從全域變成在線上流動）

選 **B**。理由：分流天生成立、特徵不必接線、分岔天生是各自一份。

### 3.1 這條不變量要改寫

F7-18 立的是「**一張卡動到的每一條流，畫面上都要有一條線**」。那條在 B 底下
不成立，也不需要成立 —— 一條線帶的是整包，卡片動裡面哪一條是它自己的參數。
新的說法是：

> **畫布上看得到的是「這顆 defect 的狀態往哪裡流、在哪裡分岔、依什麼條件」。
> 一張卡動到裡面哪一條影像流，是那張卡自己的事（節點副標已經印 `吃什麼 → 吐什麼`）。**
>
> 可測的那一半：**刪掉一條線，下游就真的收不到東西。** 這正是今天壞掉的部分。

不要因為「F7-18 說過一張卡一條流」就把 A 拉回來 —— F7-18 保護的是「畫布不能
說謊」，B 用另一個粒度達成同一件事，而且它做得到 A 做不到的分流。

---

## 4. 契約

### 4.1 Packet —— 線上流的東西

```python
@dataclass(frozen=True)
class Packet:
    images:   Dict[str, np.ndarray]
    regions:  Dict[str, List[tuple]]     # 名字 -> 一組框（0–1 比例座標，不變）
    features: Dict[str, float]
    meta:     Dict[str, Any]             # defect_id、KLARF 欄位、診斷…
```

**不可變。** 卡片回傳新的 Packet，不改舊的（`with_image()` 只換 dict，
像素陣列本身共用）。這一條同時買到兩件事：

- **分岔安全**：兩條分支各拿一個 Packet，一邊改不到另一邊
- **分岔不吃記憶體**：沒有人就地改陣列，所以不必深拷貝像素

> ⚠ 對卡片作者的規矩：**永遠產生新陣列，不要就地寫**（`arr += 1` 不行，
> `arr = arr + 1` 可以）。現在的卡片本來就是這樣寫的（`ctx.set_image(k, op(img))`），
> 所以這不是新負擔，但它從慣例升級成規則。

### 4.2 Node —— 卡片

```python
class Node:
    inputs:   Tuple[str, ...] = ("in",)
    outputs:  Tuple[str, ...] = ("out",)
    required: Tuple[str, ...] = ("in",)   # 少了就不執行（也不報錯）

    def run(self, ins: Dict[str, Packet], params) -> Dict[str, Packet]:
        """回 {輸出埠名: Packet} —— 只放它這次要吐的埠。"""
```

「回一個 dict，只放要吐的埠」這一個設計同時涵蓋四種卡：

| 卡的種類 | 回什麼 |
|---|---|
| 一般處理 | `{"out": pk}` |
| **條件分流** | `{"match": pk}` **或** `{"else": pk}`（只吐一個） |
| 分裂 | 兩個都吐 |
| 判定（尾節點） | `outputs = ()`，吐判定結果 |

### 4.3 執行語意

- **拓撲排序**求值；每個節點從進來的線上收 Packet
- **`required` 少一個就整段安靜跳過** —— 分支沒被選到時，下游不是報錯，是不執行
- **一張圖可以有好幾個判定尾節點**（每條分支自己的判定標準）
  - 0 個判定觸發 → 這顆 defect **沒有結論**，要如實記錄（不是給 0 分）
  - 2 個以上觸發 → 編輯期就該 lint 出來

### 4.4 這會取代掉什麼

| 現在 | 之後 |
|---|---|
| `routes: {ebi_patch: [...]}` | Input 節點（依資料型別分）+ 分流卡 |
| `score: {expr, threshold, bins}` | ADC 節點（可以有好幾個） |
| `params.source` / `streams` 決定接線 | `edges` 決定接線；參數只決定「動裡面哪一條流」 |
| `edges` 只影響順序 | `edges` 就是資料流 |

---

## 5. 原型驗證了什麼

寫了一份約 250 行的 spike（附錄），跑起來證明六件事：

```
== 分流：只有被選到的那一邊會跑 ==
  CLASSNUMBER=1 -> 跑過 ['input', 'route', 'enh_a', 'sub_a', 'meas_a', 'adc_a']
     判定：{'adc_a': {'score': 60.0, 'bin': 1, 'by': 'A'}}
  CLASSNUMBER=2 -> 跑過 ['input', 'route', 'enh_b', 'sub_b', 'meas_b', 'adc_b']
     判定：{'adc_b': {'score': 233.0, 'bin': 1, 'by': 'B'}}

== 分岔：兩條分支互不影響，而且不複製像素 ==
  跑過 ['input', 'left', 'right', 'join', 'adc']
  right 量到的是**原圖**的峰值：179.0
```

1. 一條線把整包狀態帶到下一張卡 ✓
2. 分岔各自一份、原始輸入沒被就地改掉（斷言鎖住）✓
3. 一張卡多個輸出埠、依條件只吐一個 ✓
4. 沒被選到的分支，下游整段安靜不執行 ✓
5. 合流是一張明講「怎麼合」的卡 ✓
6. 一張圖有多個判定尾節點 ✓

**Q3 的 `CLASSNUMBER` 分流在這個模型下不需要任何特殊機制** —— 它就是一張
「多輸出埠 + 依條件擇一」的普通卡。

---

## 5b. Phase 2 實際做了什麼（2026-08-15）

新檔案 `adept/core/pipeline/graph.py`：`Packet` / `Wire` / `Graph` /
`compile_recipe()` / `run_graph()`。`engine._run_nodes()` 變成一層薄殼，
真正的執行在圖執行器上。**17 張卡一行都沒改。**

### 5b.1 契約跟 §4.1 有一處不一樣（重要）

§4.1 寫的是「`Packet` 是 frozen dataclass，卡片回傳新的」。**實作沒有這樣做。**

`Packet` 現在就是包著一個 `Context`，不可變性靠兩件事保證：

1. 卡片本來就**產生新陣列、不就地改寫像素**（現有 17 張卡都是這樣寫的）
2. 執行器在**分岔的時候**複製（copy-on-fork），線性鏈上直接把物件交出去

換來的是「卡片不用改」—— 而那正是讓 Phase 2 的風險降到可以一次做完的原因。
代價是**不可變性從型別保證降級成慣例**：卡片作者若寫 `arr += 1`（就地改寫），
分岔的兩條分支會互相汙染，而且不會報錯。這一條要在 Phase 3 卡片搬家時
用型別重新鎖上（或加一條測試掃描就地改寫）。

### 5b.2 踩到的坑：第一個取用者不能拿原件

`take()` 一開始寫成「第一個下游拿原件、第二個以後拿複本」（想省一次複製）。
錯的：**既有卡片是就地改 `ctx` 的**，第一個下游一改，留在 outbox 裡的那份
就髒了，第二個分支複製到的是「已經被上一條分支改過」的狀態 —— 正好是分岔
要防的那件事。現在是「扇出 > 1 就每一個都複製」。
`tests/test_graph.py::test_a_fork_gives_each_branch_its_own_copy` 鎖住它。

### 5b.3 驗收

**逐顆對答案**（計畫書要求的那條）：同一份 `cross_regions.json`、同一批 60 顆
合成 defect，舊引擎（commit `d0650d8`，全域 Context）與新引擎（圖執行器）
比對 `score` / `bin` / **每一個特徵值**：

```
顆數: 舊 60 / 新 60
逐項完全相同的顆數: 60 / 60
```

**效能沒有退化**（各跑 5 次取中位數）：

```
old: median 8.40 ms/顆
new: median 7.89 ms/顆
```

新的略快，因為編譯結果現在有快取（以前每顆都重算一次 `execution_order`）。
快取掛在 `Recipe` 物件上並用**結構指紋**驗證 —— 只認物件不認內容的快取會在
Studio 改完 recipe 之後安靜地跑舊的圖。

**全套測試**：77 個檔案全綠（既有的 `test_engine` / `test_batch_cache` /
`test_e2e_*` 一個字都沒改，它們全綠就是「線性 pipeline 行為沒變」的證明）。

新性質由 `tests/test_graph.py` 釘住：編出來的線、**剪掉線下游就收不到**、
分岔隔離（像素共用但 warnings 不互相汙染）、條件分流只跑選到的那一邊、
停用節點要把線接過去。

---

## 5c. Phase 3a：判定變成卡片（2026-08-15）

新卡 `adept/core/steps/adc.py`（key `adc`，label **Decide**）—— 這是專案裡
**第一張 `CATEGORY_ADC` 的卡**（在此之前那一段的卡片數是 0）。

### 5c.1 為什麼這件事值得先做

判定以前是 `Recipe.score` 這個固定欄位：一份 recipe 只有一條式子、一個門檻，
而且不在畫布上。那擋住的正是使用者要的東西 —— `CLASSNUMBER=1` 走 A、`=2` 走 B
的時候，**兩條分支的門檻本來就該不一樣**（A 是已知的真缺陷要抓乾淨、B 是雜訊
要濾掉），綁成同一個數字等於兩邊都調不好。

現在一張圖可以放好幾張判定卡，每條分支自己一張。

### 5c.2 三種情況，三種下場（`engine._judge`）

| 情況 | 下場 |
|---|---|
| 圖上**沒有**判定卡 | 走舊的 `recipe.score`（既有的每一份 recipe 都走這條） |
| 剛好**一張**跑到 | 就用它 |
| **一張都沒跑到** | **沒有結論**：score/bin 留 `None`，並在 warnings 講出來 |
| **兩張以上**跑到 | recipe 接錯了 → 失敗並指名是哪幾張，不偷偷挑一個 |

第三條是 §6.4 那一題的答案。給 0 分是最糟的處理 —— 0 會排序、會進報表、
看起來像「很乾淨」，跟 `cd_x_nm` 恆為 0 是同一類的坑。

### 5c.3 順手補上：線存得下「從哪個埠出去」

寫測試的時候發現得 monkeypatch 才能塞一張分支的圖 —— 那是個訊號：**檔案格式
存不下埠**，所以分支 recipe 根本存不起來。`edges` 因此多一種寫法：

```json
["r", "match", "m", "in"]      // 四段式：從 r 的 match 埠 → m 的 in 埠
["subtract", "snr"]            // 兩段式：兩端的預設埠（既有檔案都是這種）
```

四段式**贏過**route 順序推出來的那條線（使用者指名了就是他說了算）。
三個元素的線會在載入時被擋下來並講清楚 —— 不猜使用者的意思。

### 5c.4 `adc` 暫時不出現在卡片庫

`ui/scope.py` 的 `HIDDEN_STEPS` 加了 `"adc"`。理由：Studio 的分數頁
（`Recipe.score`）還在，兩個地方都能設門檻而使用者不知道哪個算數。
**Phase 3b 拿掉 `score` 欄位的同一輪要把這個字串刪掉** —— 不然會變成
「做好了但沒有人打開」。CLI 與既有 recipe 不受影響。

---

## 6. 還沒解決的（Phase 3b 要面對）

### 6.1 快取切點在 DAG 上不成立

現在的定義是「執行順序上**最後一張** `category==image` 的卡的下一格」。
在有分支的圖上這句話沒有意義。

提議改成**逐節點記憶化**：key = (defect, 這個節點的上游簽章)。好處是它比現在
更通用（分支各自命中）、而且「改算法段參數不重算影像段」自動成立。代價是要決定
存哪些節點的 Packet（全部存會爆記憶體）—— 這一題留到 Phase 2 量過再定。

### 6.2 舊 recipe 遷移

`routes` → Input 節點 + 一條線一條線接起來；`score` → ADC 節點。機械式，但
**驗收必須是「同一份 recipe、同一批資料，遷移前後逐顆分數相同」**（沿用 F7-18
的作法，不要靠讀程式碼驗證）。

### 6.3 `ui/scope.py` 綁 dataset kind

「Studio 只吃 ebi_patch」是靠 `SUPPORTED_KINDS` 過濾 route 做的。輸入變成卡片
之後那個機制要重新想 —— 大概會變成「卡片庫裡只列這幾張 Input 卡」。

### 6.4 判定為 0 個時要說什麼 —— ✅ 已解（見 §5c.2）

score/bin 留 `None` 並在 warnings 講出來。**剩下 UI 那一半**：Gallery 與
輸出精靈要看得出「這顆沒有結論」跟「這顆分數很低」是兩件事。

---

## 7. Phase 切法

| Phase | 做什麼 | 風險 |
|---|---|---|
| **1** ✅ | 定契約 + 原型證明 | 無 |
| **2** ✅ | 引擎換心：依 wires 求值、copy-on-fork、編譯快取。**卡片沒動。** | 已通過逐顆驗收 |
| **3a** ✅ | ADC 變卡片（引擎支援多判定 / 沒有判定）；線存得下埠 | 低（舊路徑保留） |
| **3b** | Input 變卡片；`routes` / `score` 兩個固定欄位退場；卡片搬到新契約並用型別鎖住「不就地改寫」；`scope.py` 解除隱藏 `adc` | 中（量大但機械，使用者自己寫） |
| **4** | 畫布變成真的編輯器：埠型別擋不合法連線、**刪線=真的斷開**、分岔/合流畫得出來 | 中 |
| **5+** | 開始長功能卡：`CLASSNUMBER` 分流、跨顆統計、ML、更多量測 | 低（純加法） |

Phase 2 的驗收是整件事的安全網：**遷移前後逐顆分數相同** —— 已通過（見 §5b.3）。

---

## 8. 附錄：原型原始碼

> 這份 spike 刻意**不放進套件**（它是一條平行的路，留在 `adept/` 底下會腐爛）。
> 保留在這裡是為了 Phase 2 動工時可以拿它對答案。存成 `.py` 直接跑即可。

```python
"""Phase 1 原型：驗證「線上流的是一顆 defect 的整包狀態」這個模型成立。"""
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Tuple
import numpy as np


@dataclass(frozen=True)
class Packet:
    images: Dict[str, np.ndarray] = field(default_factory=dict)
    regions: Dict[str, List[tuple]] = field(default_factory=dict)
    features: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def with_image(self, name, arr):
        d = dict(self.images); d[name] = arr
        return replace(self, images=d)

    def with_features(self, **kw):
        d = dict(self.features); d.update({k: float(v) for k, v in kw.items()})
        return replace(self, features=d)


class Node:
    inputs: Tuple[str, ...] = ("in",)
    outputs: Tuple[str, ...] = ("out",)
    required: Tuple[str, ...] = ("in",)

    def run(self, ins, p):
        raise NotImplementedError


class Input(Node):
    inputs, required = (), ()

    def run(self, ins, p):
        item = p["item"]
        return {"out": Packet(images=dict(item["images"]),
                              meta={"defect_id": item["id"],
                                    "klarf": item["klarf"]})}


class Route(Node):
    """依 KLARF 欄位分流：兩個輸出埠，只吐其中一個。"""
    outputs = ("match", "else")

    def run(self, ins, p):
        pk = ins["in"]
        hit = pk.meta["klarf"].get(p["field"]) == p["equals"]
        return {("match" if hit else "else"): pk}


class Enhance(Node):
    def run(self, ins, p):
        pk = ins["in"]
        for name in p["streams"]:
            pk = pk.with_image(name, pk.images[name] * float(p["gain"]))
        return {"out": pk}


class Subtract(Node):
    def run(self, ins, p):
        pk = ins["in"]
        out = pk.images[p["a"]].astype(np.float32) - pk.images[p["b"]]
        return {"out": pk.with_image(p["out"], out)}


class Measure(Node):
    def run(self, ins, p):
        pk = ins["in"]
        return {"out": pk.with_features(
            **{p["name"]: float(np.max(np.abs(pk.images[p["source"]])))})}


class Merge(Node):
    """合流：明講怎麼合。"""
    inputs = required = ("a", "b")

    def run(self, ins, p):
        a, b = ins["a"], ins["b"]
        return {"out": replace(a, features={**a.features, **b.features},
                               images={**a.images, **b.images})}


class Adc(Node):
    outputs = ()

    def run(self, ins, p):
        pk = ins["in"]
        score = float(eval(p["expr"], {"__builtins__": {}}, dict(pk.features)))
        return {"__verdict__": replace(pk, meta={**pk.meta, "verdict": {
            "score": score, "bin": 1 if score >= p["threshold"] else 0,
            "by": p["label"]}})}


@dataclass
class Wire:
    src: str
    src_port: str
    dst: str
    dst_port: str


def run_graph(nodes, wires, item):
    indeg = {n: 0 for n in nodes}
    succ = {n: [] for n in nodes}
    for w in wires:
        succ[w.src].append(w.dst); indeg[w.dst] += 1
    order, ready = [], sorted([n for n, d in indeg.items() if d == 0])
    while ready:
        n = ready.pop(0); order.append(n)
        for m in succ[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort()
    assert len(order) == len(nodes), "圖上有循環"

    outbox, verdicts, ran = {}, {}, []
    for nid in order:
        node, params = nodes[nid]
        ins = {w.dst_port: outbox[(w.src, w.src_port)] for w in wires
               if w.dst == nid and (w.src, w.src_port) in outbox}
        if any(r not in ins for r in node.required):
            continue                     # 上游沒吐 -> 這一段整個不跑
        ran.append(nid)
        for port, pk in node.run(ins, dict(params, item=item)).items():
            if port == "__verdict__":
                verdicts[nid] = pk.meta["verdict"]
            else:
                outbox[(nid, port)] = pk
    return {"verdicts": verdicts, "ran": ran}
```
