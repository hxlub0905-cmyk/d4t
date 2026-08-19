# d4t — authored 2026-08-17 (F11 Input-1).
"""通道對照表：**這一顆的第幾張圖 → 叫什麼流名**。

為什麼需要它
------------
資料是「一顆 defect 好幾張圖」（實例：1 張 BSE + 4 張 SE，同時由不同 detector
收，**BSE 固定在第 2 張**）。而 ingest 層的命名是位置決定的
（第 1 張 = ``test``、第 2 張 = ``ref``、之後接 ``img3``…），**recipe 摸不到**
—— 於是 BSE 會被叫成 ``ref``，而 ``subtract`` 一句話都不會說，比的是 BSE 減 SE。
那是「跑得完、有數字、而且是錯的」。

所以 ``load_patch`` 多一個 ``channel_map`` 參數，值長這樣：

    1:se1, 2:bse, 3:se2, 4:se3, 5:se4

**頁碼是 1-based，而且是「這一顆的第幾張」**，不是 TIFF 的絕對頁號 ——
使用者看到的是「這顆有五張圖」，而同一批的第二顆在 TIFF 裡是第 6–10 頁。

**空字串 = 照 ingest 給的名字**（也就是現在的行為）。所以這個參數的預設值就是
舊行為，**舊 recipe 不需要遷移**，黃金值也逐項相同（鐵則 9 的反面用法：
不必判斷「新東西在不在」，因為新東西的預設值不改變任何結果）。

名字的限制
----------
流名會變成**特徵的前綴**（`bse_glv_max`），而特徵名是分數表達式的變數名，
所以名字只能用「可以當變數名的字」—— 這裡與 ``step.STREAM_NAME_PATTERN``
共用同一條規則（**不另外抄一份**，見 :func:`parse_channel_map` 裡的 import 註解）。
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

#: 一列 = (第幾張（1-based）, 流名)
Pair = Tuple[int, str]


class ChannelMapError(ValueError):
    """通道對照表不合法。訊息是白話的 —— 會直接顯示在參數列下面。"""


def parse_channel_map(text: object, noun: str = "image") -> List[Pair]:
    """``"1:test, 2:bse"`` → ``[(1, "test"), (2, "bse")]``（依頁碼排序）。

    每一條規則都回一句白話錯誤（鐵則 4：壞值不准跑到演算法裡）：

    * 每一列的形狀是 ``<第幾張>:<名字>``；
    * 第幾張是 ≥ 1 的整數（1-based —— 使用者數圖是從 1 開始數的）；
    * 同一張不能出現兩次、同一個名字不能用在兩張圖上
      （兩張圖同名 = 後面那張把前面那張蓋掉，而畫布上只看得到一條流）；
    * 名字要能當變數名用（流名會變成特徵的前綴）。

    空字串（或 ``None``）→ ``[]`` ＝**照 ingest 給的名字**（現行行為）。

    ``noun`` 是**這一列在講什麼東西**（``"image"`` / ``"layer"``）。同一支解析器
    服務兩張卡：`load_patch` 的一列是一張圖，`roi_from_mask` 的一列是一層 ——
    而錯誤訊息是使用者唯一看得到的東西。2026-08-18 使用者在 GDS 那張卡上打錯
    一列，看到的是「image 2 has no name」，而那張卡上一張圖都沒有。
    UI 那一頭早就分開講了（`ChannelMapField._WORDS`），只有這裡還沒有。
    """
    noun = str(noun or "image")
    a_noun = "%s %s" % ("an" if noun[:1].lower() in "aeiou" else "a", noun)
    # 這個 import 刻意放在函式裡：``step`` 在 module level import 這個模組
    # （``ParamSpec.validate`` 要用），module level 互相 import 會成環。
    # 規則只有一份 —— 抄第二份出來的那份會漂移（這個 repo 記過三次）。
    from .step import STREAM_NAME_PATTERN
    import re

    if text is None:
        return []
    raw = str(text).strip()
    if not raw:
        return []

    pairs: List[Pair] = []
    seen_pages = {}
    seen_names = {}
    for chunk in raw.replace(";", ",").split(","):
        item = chunk.strip()
        if not item:
            continue
        if ":" not in item:
            raise ChannelMapError(
                "each row looks like '<%s number>:<name>' (for example "
                "'2:bse'); '%s' has no ':'" % (noun, item))
        left, right = item.split(":", 1)
        page_text, name = left.strip(), right.strip()
        try:
            page = int(page_text)
        except (TypeError, ValueError):
            raise ChannelMapError(
                "'%s' is not %s number - use 1 for the first %s, "
                "2 for the second, and so on"
                % (page_text, a_noun, noun)) from None
        if page < 1:
            raise ChannelMapError(
                "%s numbers start at 1 (got %d) - 1 is the first %s"
                % (noun, page, noun))
        if not name:
            raise ChannelMapError(
                "%s %d has no name - every %s you list needs one"
                % (noun, page, noun))
        if not re.match(STREAM_NAME_PATTERN, name):
            raise ChannelMapError(
                "'%s' cannot be used as a stream name - use letters, digits "
                "and underscores only, and do not start with a digit "
                "(the name becomes a prefix on the features this image "
                "produces)" % name)
        if page in seen_pages:
            raise ChannelMapError(
                "%s %d is listed twice (as '%s' and '%s') - each %s gets "
                "exactly one name"
                % (noun, page, seen_pages[page], name, noun))
        if name in seen_names:
            raise ChannelMapError(
                "'%s' is used for %s %d and %s %d - two %ss with the "
                "same name means the second one silently replaces the first"
                % (name, noun, seen_names[name], noun, page, noun))
        seen_pages[page] = name
        seen_names[name] = page
        pairs.append((page, name))

    pairs.sort(key=lambda p: p[0])
    return pairs


def format_channel_map(pairs: Sequence[Pair]) -> str:
    """對照表 → 標準字串（依頁碼排序、``", "`` 分隔）。

    正規化的理由跟 ``curve`` 一樣：手打的 ``"2:bse ,1:se1"`` 與 UI 排出來的
    ``"1:se1, 2:bse"`` 要在 recipe 裡長得一樣，不然 round-trip 不是 identity
    （而 ``to_json_dict → from_json_dict`` 是 ``run_batch`` 送 recipe 進 worker
    的路 —— 它一旦不是 identity，``workers=1`` 與 ``workers=2`` 會算出不同的
    分數。真的發生過，見 docs/PITFALLS.md）。
    """
    return ", ".join("%d:%s" % (int(p), str(n)) for p, n in
                     sorted(pairs, key=lambda x: int(x[0])))


def mapped_names(pairs: Sequence[Pair]) -> List[str]:
    """對照表裡的流名，依頁碼順序。"""
    return [str(n) for _p, n in sorted(pairs, key=lambda x: int(x[0]))]


def highest_image_number(pairs: Sequence[Pair]) -> int:
    """對照表宣告到第幾張（空的回 0）。

    ``load_patch`` 用它擋「宣告了第 5 張、這顆卻只有 2 張」——
    **不准安靜地照順序硬套**（那會把 BSE 的數字寫在 SE 的名字上）。
    """
    return max((int(p) for p, _n in pairs), default=0)
