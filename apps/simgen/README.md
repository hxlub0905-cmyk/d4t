# Golden Cell generator

從一張 Golden Cell 產一整批模擬資料。

```bash
pip install -r requirements.txt
python main.py
```

## 這個資料夾是什麼

它是一個**完整、可以單獨帶走的程式** —— 整個資料夾複製到任何地方都跑得起來，
不需要 d4t。

它由 `tools/extract_app.py` 從 d4t 抽出來（2026-09-23），而那是一次性的搬家：
d4t 那邊之後會把這個工具移除，所以**這裡是唯一的家**，不會有兩份要對。

## 裡面有什麼

`simgenapp/` 底下的目錄形狀跟 d4t 一樣，所以從 d4t 帶過來的程式碼一個字都沒改
（只有 `import d4t.…` 換成 `import simgenapp.…`）：

* `simgenapp/core/` — 純運算，**不 import Qt**
* `simgenapp/ui/` — 視窗與元件

共 11 支模組、4,355 行。

## 相依

* Python 3.9+
* 見 `requirements.txt`

## 授權

跟 d4t 同一份（專有／內部）—— 見原 repo 的 `LICENSE`。
