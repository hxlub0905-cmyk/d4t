# d4t Studio 節點畫布 — authored 2026-07-28 (F7-6).
"""``PipelineCanvas`` —— n8n 風格的節點畫布，取代原本的直線清單。

為什麼這件事不用動引擎
----------------------
``core`` 從 F0 起就是 DAG：``Recipe`` 早就有 ``edges`` 欄位、
``execution_order()`` 早就是 Kahn 拓撲排序 + 循環偵測、``validate()`` 早就會
報「這條 route 有循環」。當初刻意寫成「UI v1 只呈現直線，之後上自由畫布時
引擎零改動」。所以這一整個檔案純粹是 UI。

畫布長什麼樣
------------
* 節點卡：左側是所屬階段的色條，卡上是名稱 + 非預設參數摘要。
  停用的節點整張調淡（不是消失 —— 使用者要看得到它還在）。
* 連接埠：左邊是輸入、右邊是輸出。從輸出拖到輸入就連起來。
* 連線：三次貝茲曲線，方向永遠左→右，所以「資料往右流」是看得出來的。
* 選取的節點與連線用 accent 色描邊；``Delete`` 刪掉選取的東西。

位置怎麼決定
------------
**自動排版**：依拓撲深度分欄、同欄內依 ``node_order`` 排列。
使用者可以拖動節點（當下看起來會照他擺的位置），但**位置不寫進 recipe**——
recipe JSON 的結構沒有 ``pos`` 欄位，為了在畫布上存座標而改檔案格式，
會讓每一份既有 recipe 都要遷移，代價和收益不成比例。重新載入就回到自動排版。

循環擋在哪
----------
擋在 ``RecipeModel.add_edge``：拉出來的線若會造成循環，model 直接回 ``False``
不落地，畫布也就不會畫出那條線。使用者看到的是「這條線拉不起來」，
而不是「拉起來之後整條 pipeline 壞掉、跑的時候才報錯」。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolTip,
    QWidget,
)

from . import region_words
from . import theme
from .theme import TOKENS
from .widgets import CARD_MIME, IconButton, draw_group_icon, small_button

__all__ = ["PipelineCanvas", "NODE_W", "NODE_H", "COL_GAP", "ROW_GAP"]

#: 一個節點最多畫幾個**影像**輸出埠（再多就擠不下，退回單一埠）。
_MAX_PORTS = 4

#: 判定區**一開始是收起來的**（F50，2026-08-28，使用者定調：「ADC 他一樣是
#: 張卡片，可以，但把它點開可以看到 decision tree」）。
#:
#: 收合這個能力 F24 §4 就做好了，只是預設是展開 —— 於是畫布右邊常駐一整片
#: 菱形，而它跟左邊那一排卡片是**兩種長得不一樣的東西**。使用者要的是：
#: 畫布上一律是卡片，判定就是其中一張，**要看細節才點開**。
#:
#: ⚠ **這是檢視狀態，不是 recipe 的內容** —— 存檔存不到它，開檔也不會帶著
#: 它回來（同縮放平移）。所以「預設」的意思是「每次開窗」，那正是使用者
#: 講的那句話。
TREE_COLLAPSED_DEFAULT = True

#: 「整批跑一次」那條腳帶有多高（`Step.scale == SCALE_LOT` 的卡才有）。
_LOT_STRIP = 15.0

#: 腳帶上那句話。**講的是「什麼時候跑」**，而那正是這個標記存在的理由 ——
#: 段名畫布上已經有了（卡片的顏色與圖示），「整批跑完之後跑一次」沒有。
#:
#: ⚠ 這句話 2026-08-25 到 2026-08-28 之間住在 `ui/output_band.py`（F30），
#: 畫在卡片**外面**一個虛線框的左緣。使用者定調拿掉那個框，理由是編碼錯了：
#: **框的意思是「這幾個是一組」，而真相是「跑的時間不一樣」** —— 而那是一張
#: 卡自己的屬性，不是一群卡的關係。順帶治好一個 bug：那個框從卡片位置算出來，
#: 所以每一個拖曳 frame 都被銷毀重建一次，而畫布用 Qt 預設的
#: `MinimalViewportUpdate` —— 抗鋸齒的虛線每 frame 溢出 boundingRect 一點點，
#: 累積起來就是使用者回報的「拖曳留下殘影」。
#:
#: **用字不用顏色**：一條色帶對不會寫 code 的使用者不是一句話（推廣鐵則）。
LOT_STRIP_TEXT = "once per lot"

#: 最多畫幾個**區域**輸出埠（F12）。跟影像的上限分開數，因為它們是兩排不同
#: 的東西：一張 GDS 卡吐三層區域的同時，還原樣送出它吃進來的那條流。
#: 卡片會為了容納埠**長高**（見 ``_NodeItem.height``），所以這個數字管的是
#: 「多到某個程度就算了」，不是版面。
#:
#: ⚠ **數的是埠，而一個區域是三個埠**（``<name>`` / ``_center`` / ``_others``）。
#: 這個數字原本是 6，那時候它剛好等於「六個區域」—— 因為當時的 GDS 卡一層只吐
#: 一個名字。F29（2026-08-25）讓它也吐家族之後，6 就變成「**兩層**」：第三層
#: 開始的每一個區域在畫布上都沒有出口，而它們確實是這張卡產出的東西。
#: 所以改成 18 = 六個家族，把「看得到幾層」擺回原來的地方。
#: （F31 T4 起 ``pick="none"`` 的家族只有一個名字＝一顆埠 —— 那時 18 顆
#: 埠就是十八層。數的仍然是埠，這個數字不用動。）
_MAX_REGION_PORTS = 18

#: 區域埠的半徑（畫成菱形 —— 影像埠是圓）。
#:
#: 為什麼要長得不一樣：這兩種埠**接不到彼此**。把一條影像線拉進區域埠，那一格
#: 會變成一個沒有人定義的區域名 —— 跑起來是 `unknown-region`，而畫面上那條線
#: 看起來完全正常。形狀在滑鼠靠近之前就講出這件事。
_REGION_PORT_R = 5.5

#: 埠標籤佔的寬度（畫在節點右緣之外，boundingRect 必須算進去）。
_PORT_LABEL_W = 52.0

#: 節點左側 icon 的邊長，以及裝著它的圓角色塊。
#: 用**色塊**而不是細色條（F7-8）：n8n 的節點一眼認得出來，靠的就是左邊那顆
#: 有顏色的圖示磚。細條太安靜，遠看整張畫布還是一排一模一樣的方框。
_ICON = 18.0
_TILE = 32.0

#: 節點卡尺寸與排版間距（畫布座標）。
#:
#: F13-⑤（2026-08-19）把卡片放大了一號，兩個都是量出來的：
#:
#: * **寬 190 → 204**：標題可用的寬度是 ``NODE_W`` 減掉左邊那塊圖示磚（40）
#:   與右邊的邊界（8）—— 190 只剩 142px，而 ``Compare two streams`` 這種
#:   10pt 粗體剛好卡在邊上，一縮放就被切成 ``Compare two strea…``。
#:   **只加 14 不是 20**：卡片變寬會讓整排的 `fit` 縮得更小，而那正是
#:   F13-1 剛買回來的東西。14 讓標題有餘裕，又留得住 70% 那條線。
#: * **高 56 → 64**：卡上有三行字（標題／副標／設定摘要），56 的時候第三行
#:   離底只有 7px，讀起來像被壓在框裡。
#: * **欄距 96 → 116**：埠的標籤畫在卡片**外面**，左右各 ``_PORT_LABEL_W``
#:   （52）。96 的欄距塞不下兩個 52 —— 上游的輸出名與下游的輸入名會疊在
#:   同一塊空白上（實測 `layout_label` 與 `single` 疊在一起）。
NODE_W, NODE_H = 204.0, 64.0
COL_GAP, ROW_GAP = 116.0, 26.0
_PORT_R = 5.0
#: 埠的**命中**半徑（比畫出來的圓點大 —— 5px 的點用滑鼠瞄很痛苦）。
#: ``out_port_at`` 與 ``_NodeItem.shape`` 都讀它：命中範圍只能有一個定義，
#: 分成兩份遲早會對不起來，而「對不起來」的症狀是「點了沒反應」。
_PORT_GRAB = _PORT_R * 3.0
#: 相鄰兩顆埠至少要離多遠（F68）。埠畫出來 11px 寬，所以這是「兩顆埠之間看得
#: 出空隙、而且瞄得準」的下限。`_NodeItem._PORT_PITCH` 由它決定。
_PORT_MIN_GAP = 15.0

#: 連線中點的方向箭頭大小。畫布可以縮放平移，光看曲線不一定分得出資料往哪流。
_ARROW = 5.0
#: 線上那顆「斷開」× 的半徑（F7-22）。
_CUT_R = 8.0

#: 連線的 z 值。節點是 0，所以線平常畫在卡片**底下**（n8n 也是這樣，
#: 卡片才是主角）；滑鼠移上來的那一條抬到卡片之上 —— 見 ``hoverEnterEvent``。
_Z_EDGE, _Z_EDGE_HOVER = -1.0, 1.0

#: 縮到這個比例以下，卡片只畫「認得出是哪一張」需要的東西（F78）。
#:
#: 背景的點陣底早就有這條線了（`drawBackground` 在 0.45 以下不畫點，理由是
#: 「會糊成一片灰」），但**卡片沒有** —— 於是 `fit()` 到 40% 的時候，每張卡
#: 上那兩行 6–7pt 的副標與設定摘要、加上左右各一排埠標籤，全部變成糊在卡片
#: 上的灰噪點，而且每張卡還照跑一次 `_draw_elided` 的 elide 計算。
#:
#: 值取 0.55 而不是跟著背景的 0.45：字比點更早糊。`MIN_FIT_SCALE` 那裡量過
#: 「副標要到 70% 才讀得回來」—— 0.55 是「已經讀不到了，別再畫」的位置，
#: 中間那段留給還看得出輪廓的模糊字。
_LOD_TERSE = 0.55

#: 「換一個視角」的動畫要不要跑（F80）。
#:
#: 這**不是裝飾**。`fit()` / `reset_zoom()` / `tidy()` 以前是瞬間跳的，而瞬間跳
#: 會讓使用者**失去「我剛剛在看的是哪一塊」** —— 畫面前後兩張圖之間沒有任何線索
#: 說「這兩張是同一份 pipeline」，他得重新找一次自己的位置。這叫空間連續性，
#: 是節點畫布上少數幾個動畫真的有用的地方。
#:
#: ⚠ **測試裡要關掉**（`tests/conftest.py` 有一支 autouse fixture）。開著的話
#: 「按了 fit 之後縮放是多少」會變成一個**跟時間有關**的問題，而那種測試會間歇性
#: 變紅、然後被關掉。滾輪縮放刻意**不**走這條路：它本來就是一格一格的，加上動畫
#: 只會變得黏手。
ANIMATE = True
#: 動畫長度（毫秒）。短到不擋路、長到看得出東西往哪裡去。
ANIM_MS = 170


def card_radius() -> float:
    """節點卡的圓角 —— **讀 QSS 的同一個 token**（F80）。

    以前這裡寫死 7，而 QSS 的 ``radius_md`` 是 6：畫布上的卡與面板上的卡
    是同一種東西，圓角卻差 1px，而且沒有任何東西擋得住它繼續漂。
    每次呼叫都重讀，因為換主題時 ``TOKENS`` 是**就地更新**的。
    """
    return theme.radius("radius_md")


#: 背景點陣的間距 —— **同時是版面的格線**（F79）。
#:
#: 以前它是 22，而且**只**是背景的裝飾。版面用的是另外一組數字：欄距
#: ``NODE_W + COL_GAP`` = 320（320 / 22 = 14.55）、列距「卡片高 + ``ROW_GAP``」
#: = 90（90 / 22 = 4.09）。兩組都不整除，所以按了「排整齊」之後**卡片的角落落
#: 在點與點之間，而且每一列偏移的量還不一樣** —— 那張點陣底看起來像對齊參考，
#: 實際上對不齊任何東西。
#:
#: 20 是唯一不必動卡片尺寸就成立的值：``NODE_W + COL_GAP`` = 204 + 116 = 320
#: 正好是 16 × 20。列距則由 :func:`on_grid` 進位（卡片高度是變動的 —— 有
#: 「整批跑一次」腳帶的卡比較高）。
#:
#: ⚠ **卡片的右緣仍然不在點上**（204 不是 20 的倍數）。量過了：要讓它也落在點
#: 上得把 ``NODE_W`` 收成 200，而那 4px 是 F13-⑤ 花錢買回來的標題寬度
#: （190 → 204 的理由是 ``Compare two streams`` 被切）。左上角對齊才是「這一排
#: 卡有沒有排好」的判準，右緣多出來的 4px 是同一個常數，不會讓卡片之間歪掉。
GRID = 20.0


def on_grid(value: float) -> float:
    """把一段長度**往上**進位到 :data:`GRID` 的倍數。

    往上不往下：列距是「這一列最高的卡 + 間距」，往下取整會讓最高的那張卡
    貼到下一列去。
    """
    step = GRID
    return float(int((float(value) + step - 1e-9) // step) * step)


#: 還沒拉線時，一列最多排幾張卡（見 :func:`layout_columns`）。
WRAP = 4


def wrap_for_width(width: float) -> int:
    """這麼寬的畫布，一列排得下幾張卡（F13-1）。

    ``WRAP`` 以前是寫死的 4，而那等於**要求畫布有 1050px 寬**
    （4 × (NODE_W + COL_GAP)）。主視窗的中欄實測只有 551px，於是 ``fit()``
    把整排縮到 50% —— 而卡片的副標（「這張卡吃什麼吐什麼」）要到 70% 才讀得
    回來（見 :data:`PipelineCanvas.MIN_FIT_SCALE` 的說明）。

    一份讀不出字的全景不算全景。所以換行點跟著**實際有多寬**走：窄就早一點
    換行、排得高一點，換來每一張卡都讀得到字。上限仍然是 ``WRAP`` ——
    再寬也不要排成一條要橫著掃的長列。
    """
    # 兩件事要算對：
    #
    # 1. **最後一欄不需要 COL_GAP**（欄距是欄與欄「之間」的），所以 n 張卡佔
    #    ``n * NODE_W + (n - 1) * COL_GAP``。少算這一格的話 551px 會被算成
    #    「只排得下 1 張」，而它實際上排得下 2 張（190 + 96 + 190 = 476）。
    # 2. **不必排到 100% 才算數。** `fit()` 會縮，而副標要到 70% 才糊 ——
    #    所以這裡容許縮到 ~87%（× 1.15），把那一格餘裕拿去多排一欄。
    #    埠的標籤畫在卡片外面，那點溢出也吃在這個餘裕裡。
    usable = max(1.0, float(width)) * 1.15
    fits = int((usable + COL_GAP) // (NODE_W + COL_GAP))
    return max(1, min(WRAP, fits))


def layout_columns(node_ids: Sequence[str],
                   edges: Sequence[Tuple[str, str]],
                   wrap: Optional[int] = None) -> Dict[str, Tuple[int, int]]:
    """自動排版：``node_id -> (欄, 列)``。

    欄 = 拓撲深度（最長前置路徑長度），列 = 同欄內依 ``node_ids`` 的原順序。
    沒有任何連線時每個節點各自深度 0 —— 那會全部疊在第一欄，所以退化情況下
    改成「一個接一個往右排」，讓空 recipe 加卡片時看起來仍然是一條鏈。

    但那條鏈**會換行**（``WRAP``，F7-9）。一份九張卡、還沒拉線的 recipe 排成
    一列會超過 2500px；``fit()`` 為了塞進畫面得縮到看不出字，而它又有下限
    （縮成小方塊比留捲軸更糟），結果是「一排讀不出來的小方塊 + 一條捲軸」。
    換行之後同樣九張卡是 3×3，每一張都讀得到字。閱讀順序仍然是左到右、
    上到下 —— 跟文字一樣，不需要額外學。
    """
    wrap = WRAP if wrap is None else max(1, int(wrap))
    ids = [str(n) for n in node_ids]
    idx = {n: i for i, n in enumerate(ids)}
    preds: Dict[str, List[str]] = {n: [] for n in ids}
    for a, b in edges:
        if a in idx and b in idx:
            preds[b].append(a)

    if not any(preds[n] for n in ids):
        return {n: (i % wrap, i // wrap) for i, n in enumerate(ids)}

    depth: Dict[str, int] = {}
    for n in ids:                       # ids 已是拓撲順序，一遍就夠
        depth[n] = max((depth.get(p, 0) + 1 for p in preds[n]), default=0)

    # 一「帶」= 換行之前的 ``wrap`` 個深度。帶高取「最擠的那個深度有幾個節點」，
    # 這樣換行之後上下兩帶不會疊在一起。
    per_depth: Dict[int, int] = {}
    for n in ids:
        per_depth[depth[n]] = per_depth.get(depth[n], 0) + 1
    band_h = max(per_depth.values(), default=1)

    # 同欄內的列序用 **barycenter**（上游都排在第幾列，我就往那個平均靠）。
    # 以前照 node_order 排：上游在第 0 列、下游被排到第 2 列，線就斜跨整欄，
    # 而三條斜線交叉起來「亂」的觀感比任何配色問題都大。跟上游對齊之後，
    # 大部分的線接近水平 —— 交叉不是被畫得更好看，是**根本不發生**。
    # 平手（沒有上游、或平均相同）退回原順序，既有測試鎖的就是這個順序。
    rows_of: Dict[str, int] = {}
    out: Dict[str, Tuple[int, int]] = {}
    for d in sorted(set(depth.values())):
        members = [n for n in ids if depth[n] == d]

        def _bary(n: str) -> float:
            prs = [rows_of[p] for p in preds[n] if p in rows_of]
            return (sum(prs) / float(len(prs))) if prs else float(idx[n])

        members.sort(key=lambda n: (_bary(n), idx[n]))
        band, col = divmod(d, wrap)
        for r, n in enumerate(members):
            rows_of[n] = r
            out[n] = (col, band * band_h + r)
    return out


def _draw_elided(p: QPainter, rect: QRectF, text: str,
                 align=Qt.AlignLeft) -> None:
    """畫一行文字，太長就切成 ``像這樣…``。

    直接 ``drawText`` 到一個放不下的矩形，Qt 會**硬切在字的中間**，看起來像
    畫面壞掉；``參數摘要=diff · metri`` 這種殘句還會讓人以為值真的是那樣。
    靠右對齊的更糟 —— 它從**左邊**切，於是 ``Borrow range from`` 變成
    ``nge from``，讀起來像另一個欄位的名字（F13-⑤ 量到的）。
    """
    s = str(text)
    fm = p.fontMetrics()
    if fm.horizontalAdvance(s) > rect.width():
        s = fm.elidedText(s, Qt.ElideRight, int(rect.width()))
    p.drawText(rect, Qt.AlignVCenter | align, s)


#: 參數摘要各項之間的分隔（Studio 組字串時用的是同一個）。
SUMMARY_SEP = " · "


def _fit_parts(fm, width: float, parts: List[str]) -> str:
    """把「這張卡被設定成什麼」逐項塞進 ``width``，**放不下的收成 `+N`**。

    為什麼不是直接 elide 整串（使用者回報：「normalize 的節點文字會被吃掉」）
    -----------------------------------------------------------------------
    以前這一行是「三個非預設參數 join 起來」再交給 :func:`_draw_elided`，於是節點
    上長出 ``streams= · p_low=1.2 · refer…`` —— 最後一項被切在字中間，而**被切掉
    的那一項使用者根本不知道它存在**。

    改成逐項塞：塞得下的完整顯示，塞不下的用一個數字承認「還有 N 項」。
    ``+1`` 是一個看得懂的訊息（點開卡片就看得到那一項），``refer…`` 不是。

    純函式（只吃 ``QFontMetricsF``）—— 所以「幾項塞得下」測得到，不必去讀畫素。
    """
    items = [str(x) for x in parts if str(x)]
    kept: List[str] = []
    for part in items:
        trial = SUMMARY_SEP.join(kept + [part])
        hidden_after = len(items) - len(kept) - 1
        need = trial + ("  +%d" % hidden_after if hidden_after else "")
        if kept and fm.horizontalAdvance(need) > width:
            break
        kept.append(part)
    text = SUMMARY_SEP.join(kept)
    hidden = len(items) - len(kept)
    if hidden:
        text = "%s  +%d" % (text, hidden) if text else "+%d" % hidden
    return text


def _draw_parts(p: QPainter, rect: QRectF, parts: List[str]) -> str:
    """:func:`_fit_parts` 的結果畫上去（回畫出的字，狀態列與測試讀得到）。"""
    text = _fit_parts(p.fontMetrics(), rect.width(), parts)
    _draw_elided(p, rect, text)
    return text


def region_color() -> QColor:
    """區域線與區域埠的顏色 —— Region 段的階段色（F12）。

    用階段色而不是另外挑一個：使用者已經在卡片庫、左側 rail、卡片左邊那顆
    圖示磚上看過這個顏色三次了，它就是「這是區域的事」的意思。
    """
    return QColor(theme.group_hex("region"))


def badge_paints(level: str) -> bool:
    """這一級 lint 發現在卡片右上角畫不畫圓標（PR-2）。

    ``info`` 不畫：那一級是「值得知道、但連 warning 都算不上」——
    畫了琥珀點，它跟 warning 就分不開，而一顆常駐的點會被學會忽略
    （推廣鐵則）。info 只住在卡片的 tooltip 與 CLI 的清單裡。
    """
    return str(level) in ("error", "warning")


def _diamond(centre: QPointF, r: float) -> QPainterPath:
    """以 ``centre`` 為心、半徑 ``r`` 的菱形（區域埠的形狀）。"""
    path = QPainterPath(centre + QPointF(0.0, -r))
    path.lineTo(centre + QPointF(r, 0.0))
    path.lineTo(centre + QPointF(0.0, r))
    path.lineTo(centre + QPointF(-r, 0.0))
    path.closeSubpath()
    return path


def _port_label_text(spec: Dict[str, Any]) -> str:
    """一顆輸入埠旁邊寫什麼字（F68）。

    **接上線之後也要說得出角色**。以前這裡是 ``stream or label``，於是一接上
    線，``Region`` / ``Ref region`` 就變成區域名字 —— 分辨兩顆菱形的唯一線索，
    在最需要它的時候消失。現在參照那一顆前面掛著 ``ref``，而放不下的時候
    `_draw_elided` 從後面切，所以**先被切掉的是名字，不是角色**。
    """
    text = str(spec.get("stream") or spec.get("label") or "")
    if text and str(spec.get("role", "")) == "reference" and spec.get("stream"):
        text = "ref " + text
    return text


def _draw_port(p: QPainter, anchor: QPointF, kind: str, filled: bool,
               role: str = "", lit: bool = False) -> None:
    """畫一顆埠。影像是圓、區域是菱形；輸入空心、輸出實心。

    ``role``（F68）：``"reference"`` 的埠畫**虛線邊**。理由是量出來的 ——
    ``roi`` 與 ``reference_region`` 在這之前是**逐位元組相同的兩顆菱形**，
    而唯一的線索（左邊那 52px 的標籤）**接上線之後就變成區域名字**，角色的字
    消失。於是使用者要拖線的時候，正好沒有東西告訴他該拖哪一顆 —— 而拖歪了
    兩個都是合法的區域參數，`_connect_region` 攔不到。
    虛線是**跟區域線同一個語彙**（那條線也是虛的），不是新發明的記號。

    ``lit``（F68）：拖線拖到一半時，接得上的埠會亮起來、放大一點。
    """
    col = region_color() if kind == "region" else QColor(TOKENS["canvas_edge"])
    if lit:
        col = QColor(TOKENS["canvas_edge_active"])
    pen = QPen(col, 2.0 if lit else 1.2)
    if role == "reference":
        pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    grow = 1.6 if lit else 0.0
    if kind == "region":
        p.setBrush(QBrush(col if filled else QColor(TOKENS["bg_surface"])))
        p.drawPath(_diamond(anchor, _REGION_PORT_R + grow))
        return
    p.setBrush(QBrush(col if filled else QColor(TOKENS["bg_surface"])))
    p.drawEllipse(anchor, _PORT_R + grow, _PORT_R + grow)


class _NodeItem(QGraphicsItem):
    """一張節點卡（自繪；顏色全部取自 ``theme.TOKENS``）。"""

    def __init__(self, info: Dict[str, Any], canvas: "PipelineCanvas"):
        super().__init__()
        self.canvas = canvas
        self.info = dict(info)
        self.node_id = str(info.get("node_id", ""))
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # hover 回饋的狀態（誰在 hover 由 **view** 判斷，不是這裡收事件 ——
        # 卡片一收 hover，事件就不再穿過它，壓在線中點上的卡會把 × 悶死；
        # 見 shape() 的說明與 test_ui_canvas_cut_button）。
        self._hover = False
        #: 現在這張卡是不是正被使用者的手拖著（F79）。只有這種時候位置才吸到
        #: 格線上 —— 理由見 :meth:`_snapped`。
        self._dragging = False
        tip = "%s — %s" % (self.node_id, info.get("label", ""))
        if info.get("problem"):
            # 標記說「有問題」，滑鼠停上去說「是什麼問題」。標記本身放不下一句話，
            # 而「有一個紅點但不知道為什麼」比沒有標記更讓人焦慮。
            tip += "\n\n⚠ %s" % info["problem"]
        self.setToolTip(tip)

    # -- 幾何 ---------------------------------------------------------------
    #: 一顆埠至少要佔幾 px 才點得到（埠的直徑是 10–11）。
    #: 兩顆埠之間留多高（F68 從 13 提到 17）。
    #:
    #: 13 的時候，四顆埠的卡片上相鄰兩顆相距 **12.8px** —— 而埠本身畫出來就
    #: 有 11px 寬。瞄準的餘裕只剩一個像素多，而 `in_param_at` 是就近吸附：
    #: 拖歪一點就落在隔壁那一顆上，**兩顆都是合法的區域參數**，
    #: `_connect_region` 攔不到，於是那條線安靜地接錯。
    #:
    #: ⚠ 這不是說「抓取圈不可以重疊」—— 就近吸附之下重疊是無害的（每顆埠
    #: 拿走離自己比較近的那一半）。要守的是**瞄得準**，所以下限是
    #: :data:`_PORT_MIN_GAP`，`tests/test_ui_canvas_ports.py` 釘著。
    _PORT_PITCH = 17.0

    def height(self) -> float:
        """這張卡多高 —— **埠多就長高**（F12）。

        ``NODE_H``（56）容得下四顆埠；區域也變成埠之後，一張吐三層的 GDS 卡
        右邊是「一條原樣送出的流 + 三個區域」。埠均分卡高，所以在固定高度下
        它們會擠到互相重疊 —— 而重疊的埠是**點不到**的（``out_port_at`` 取最近
        的那一顆，兩顆疊在一起就等於其中一顆消失）。

        長高而不是截斷：截掉的那幾個區域仍然是這張卡真的產出的東西，畫布上
        看不到它們就是說謊。
        """
        n = max(len(self.in_specs()), len(self.out_specs()), 1)
        base = max(NODE_H, self._PORT_PITCH * n + 10.0)
        # 腳帶佔的是**真的高度**，不是畫在卡片外面 —— 畫在外面的東西正是
        # 上一版那個框，而它會跟下一列的卡片打架（`output_band` 的 PAD 那段
        # 記過一次：上下各留 26 的話相鄰兩列疊了 42px）。
        return base + (_LOT_STRIP if self.is_lot() else 0.0)

    def body_height(self) -> float:
        """卡片**本體**多高（不含腳帶）。

        埠要均分的是本體，不是本體加腳帶 —— 用整個高度算的話，一張有腳帶的卡
        埠會整體往下偏，而它對面那張沒有腳帶的卡不會，兩條線於是一高一低。
        （目前 Output 段沒有埠，所以這件事看不出來 —— 這一支是**為了那個
        看不出來**才存在的：下一張宣告 `SCALE_LOT` 又有埠的卡不該去發現它。）
        """
        return self.height() - (_LOT_STRIP if self.is_lot() else 0.0)

    def is_lot(self) -> bool:
        """這張卡是**整批跑一次**嗎（`Step.scale == SCALE_LOT`）。

        讀的是 studio 放進 info 的 ``scale`` —— **卡片自己宣告的**，不是一份
        寫死在 UI 的 Output 卡清單。以前那件事由 `output_band` 問
        ``step_cls.scale``，同一個出處，只是換了一個地方問。
        """
        return str(self.info.get("scale", "")) == "lot"

    def boundingRect(self) -> QRectF:
        """**要涵蓋所有畫得出去的東西**，否則拖動節點會留下殘影。

        埠標籤（"test" / "ref"）畫在節點右緣之外 —— 之前 boundingRect 只算到
        ``NODE_W + _PORT_R``，Qt 就只重繪那個範圍，標籤的舊位置沒被清掉。
        選中的光暈（3px 寬、畫在卡片邊緣之外）也算 —— 上下各要多留 4px。

        **它同時是 ``shape()`` 的上限**：Qt 找滑鼠下的圖元時先用 boundingRect
        粗篩，再問 shape。所以 shape 伸出去而 boundingRect 沒跟上的那一圈，
        使用者點下去是**完全沒有反應**的 —— 以前埠的抓取圈（±15px）就有一段
        落在這個矩形外面（上下各只留了 4px），那正是「最上面／最下面那顆埠
        有時候點不到」的另一半。所以這裡直接以抓取半徑放寬。

        左緣與上下以抓取半徑放寬；右緣本來就被埠標籤撐得比抓取圈遠，
        所以**不再往右加**（多出來的空白會讓相鄰的節點互相吃到點擊，
        那是 F7-14 拿掉常駐「+」時就量過的事）。
        """
        # 兩個以上的輸入才會在左邊標名字（見 paint）—— 標了就要涵蓋那塊字，
        # 不然拖動節點會在原處留下擦不掉的殘影（這個坑踩過三次）。
        left = -_PORT_GRAB - 1.0
        if len(self.in_specs()) >= 2:
            left -= _PORT_LABEL_W
        right = NODE_W + max(_PORT_GRAB, _PORT_R + _PORT_LABEL_W) + 1.0
        return QRectF(left, -_PORT_GRAB - 1.0,
                      right - left, self.height() + 2.0 * (_PORT_GRAB + 1.0))

    def shape(self) -> QPainterPath:
        """**點得到的範圍不是畫得到的範圍。**

        ``QGraphicsItem`` 預設的 ``shape()`` 就是 ``boundingRect()``，
        而上面那個 rect 是為了「畫得出去的東西要重繪得到」（埠標籤在節點右緣
        之外）**刻意加寬**的 —— 加寬的代價是這張卡順便把右邊 56px 的空白
        也一起**收成自己的滑鼠命中區**，而且那塊空白看起來完全是畫布。

        那塊空白正是連線的家：兩欄相距 ``COL_GAP``（96px），而一條相鄰欄的
        貝茲曲線中點落在 ``(a.x + b.x) / 2`` —— 也就是上游卡右緣往右 48px，
        還在那 56px 裡面。線上那顆「斷開」的 ×（F7-22）就畫在中點上，
        於是**每一條同列相鄰的線，它的 × 都被上游那張卡的隱形命中區蓋住**：

        * hover 事件會**穿過**不收 hover 的圖元（卡片不收），所以 × 照樣畫得
          出來 —— 使用者看得到它。
        * 滑鼠**按下**不會穿過。z 值大的節點（0）贏過連線（-1），
          於是那一下被卡片收走，變成「選取上游那張卡」。

        看得到、按得到、然後什麼都沒發生。這是最難查的一種 —— 沒有錯誤訊息，
        而且畫面上真的有東西動（另一張卡被選起來了）。

        所以命中區自己講清楚：**卡片本體 + 每一顆埠自己的抓取圈**，不含標籤。
        標籤是印出來給人讀的字，本來就不該是可以按的東西。

        埠的圈要**逐顆畫進來**，不能只把本體上下各撐開 1px：
        ``out_port_at`` 用的是以埠心為中心、半徑 ``_PORT_GRAB`` 的圓，而最上面
        那顆埠的圓有一段在卡片上緣之外（四個埠時埠心在 y=11.2，圓一路到
        −3.8）。命中區小於判定區的那一圈，游標明明在圈裡卻進不了
        ``out_port_at`` —— 使用者的體感就是「這顆埠有時候點不到」。
        **命中範圍只能有一個定義**，所以這裡照著判定區畫。

        ⚠ 一定要 ``WindingFill``：``QPainterPath`` 預設是 ``OddEvenFill``，
        而埠的圈跟卡片本體是**重疊**的兩個子路徑 —— 交集在奇偶規則下會被
        「抵消」成洞，於是輸入埠的圓心（正好落在本體裡）反而不算命中。
        測試抓到過：加了圈之後 ``shape().contains(in_port_local())`` 是 False。
        """
        p = QPainterPath()
        p.setFillRule(Qt.WindingFill)
        r = card_radius()
        p.addRoundedRect(QRectF(0.0, -1.0, NODE_W, self.height() + 2.0), r, r)
        for anchor in self.in_anchors_local() + self.out_anchors_local():
            p.addEllipse(anchor, _PORT_GRAB, _PORT_GRAB)
        return p

    # -- 輸入埠（F10：**一個輸入參數一顆埠**）--------------------------------
    #
    # 以前左邊只有一顆埠，因為在 F10 之前「線落在哪個參數上」是**猜**的
    # （Studio 的 ``_PRIMARY_PARAMS`` 依 streams → target → source 的順序挑第一
    # 個）。猜得中是因為當時每張卡只有一個輸入在用；``subtract`` 的
    # ``a`` / ``b`` 兩個輸入從來就沒有分別接過 —— 它們靠參數預設值（test / ref）
    # 自己填好，畫布上那條線其實什麼都沒說。
    #
    # 「兩條線接進同一張卡的**不同**輸入」是使用者要的多連一，而那件事要成立，
    # 左邊就得有兩顆分得開的埠。
    def in_specs(self) -> List[Dict[str, Any]]:
        """這張卡的輸入格：``[{"name","label","stream","kind"}, …]``。

        **影像的在前，區域的在後**（F12）。兩種埠住在同一個清單，因為畫布上
        「這條線落在哪一格」只有一套算法（``in_param_at`` → ``dst_name``）——
        分成兩份的話，兩種線的落點判斷遲早會長歪，而症狀是「線接到隔壁那一格」，
        跑得完、有數字、而且是錯的。
        """
        out = [dict(d, kind=str(d.get("kind") or "image"))
               for d in (self.info.get("inputs") or [])]
        out += [dict(d, kind="region")
                for d in (self.info.get("region_inputs") or [])]
        return out

    def in_kinds(self) -> List[str]:
        return [str(d.get("kind") or "image") for d in self.in_specs()]

    def _ports_to_light(self) -> set:
        """拖線拖到一半時，**這張卡上哪幾顆埠接得上**（F68）。

        存在的理由是量出來的：兩顆同型別的埠現在**畫得一樣、抓取圈重疊、
        而 `in_param_at` 就近吸附** —— 拖歪了會安靜地接到隔壁那一顆，而兩顆都是
        合法的區域參數，`_connect_region` 攔不到。拖的當下把接得上的埠亮起來，
        使用者在放手**之前**就看得到自己要接到哪一顆。

        只看**型別**（影像線只接得上圓埠、區域線只接得上菱形埠）—— 那正是
        `studio._connect` / `_connect_region` 真的會擋的那一條，兩邊要一致。
        """
        view = getattr(self, "canvas", None)
        src = getattr(view, "_link_from", None) if view is not None else None
        if src is None or src is self:
            return set()
        try:
            kind = src.out_kind(int(getattr(view, "_link_port", 0)))
        except Exception:                  # noqa: BLE001 — 畫圖用，壞了就不亮
            return set()
        return {str(sp.get("name") or "") for sp in self.in_specs()
                if str(sp.get("kind") or "image") == str(kind)}

    def in_anchors_local(self) -> List[QPointF]:
        """每個輸入埠在本地座標的位置（由上而下均分節點左緣）。

        **沒有輸入的卡就沒有埠**（F11 Enhance-4，使用者定調：「因為她是最初始的
        source，card 最前方不能有連接的白色原點」）。以前這裡回一顆「反正畫一個」
        的埠，而那顆埠是**畫布在說謊**的一個實例：它看起來可以接線，但入口卡的
        資料不是從別張卡來的，任何線都接不上去（`in_port_at` 現在也回 None，
        所以連拖過去的動作都不成立）。

        幾何用途（`in_port`）仍然答得出一個點 —— 那是給連線畫圖用的內部座標，
        不是畫在畫面上的東西。
        """
        n = len(self.in_specs())
        if n == 0:
            return []
        h = self.body_height()
        if n == 1:
            return [QPointF(0.0, h / 2.0)]
        step = h / (n + 1)
        return [QPointF(0.0, step * (i + 1)) for i in range(n)]

    def in_anchors(self) -> List[QPointF]:
        base = self.scenePos()
        return [base + p for p in self.in_anchors_local()]

    def _no_input_anchor(self) -> QPointF:
        """沒有輸入的卡（Input）**不畫**埠，但幾何上仍然要答得出一個點：
        連線的貝茲曲線、`shape()`、測試都會問。左緣正中央。"""
        return QPointF(0.0, self.height() / 2.0)

    def in_port(self, index: int = 0) -> QPointF:
        anchors = self.in_anchors()
        if not anchors:
            return self.scenePos() + self._no_input_anchor()
        return anchors[max(0, min(int(index), len(anchors) - 1))]

    def in_port_local(self) -> QPointF:
        anchors = self.in_anchors_local()
        return anchors[0] if anchors else self._no_input_anchor()

    def in_port_at(self, pos: QPointF):
        """本地座標 ``pos`` 最靠近哪一個輸入埠（沒有夠近的回 ``None``）。

        跟 :meth:`out_port_at` 同一個判準（取最近的、要落在抓取圈裡）——
        這兩件事只能有一套算法，分成兩份遲早會對不起來。
        """
        best, best_d2 = None, None
        for i, local in enumerate(self.in_anchors_local()):
            d = pos - local
            d2 = d.x() * d.x() + d.y() * d.y()
            if d2 <= _PORT_GRAB ** 2 and (best_d2 is None or d2 < best_d2):
                best, best_d2 = i, d2
        return best

    def in_param_at(self, pos: QPointF) -> str:
        """``pos`` 落在哪一個輸入**參數**上（``a`` / ``b`` / ``streams``…）。

        放開滑鼠的地方不一定準準地在埠上 —— 使用者多半是往卡片上一丟。
        所以命中不到埠時退回**最近的那一個**，而不是讓這一下什麼都不做
        （「線拉過去了卻沒接上」是最讓人以為工具壞掉的一種回應）。
        """
        specs = self.in_specs()
        if not specs:
            return ""
        idx = self.in_port_at(pos)
        if idx is None:
            anchors = self.in_anchors_local()
            idx = min(range(len(anchors)),
                      key=lambda i: (pos - anchors[i]).y() ** 2)
        return str(specs[min(idx, len(specs) - 1)].get("name", ""))

    def in_names(self) -> List[str]:
        """這個節點讀哪些影像流（用來決定上游的線該接哪個埠）。"""
        return [str(r) for r in (self.info.get("reads") or []) if r]

    def out_names(self) -> List[str]:
        """這個節點吐出的影像流名稱（決定畫幾個輸出埠）。

        來自 ``Step.describe()`` 的 ``writes``。對 patch 的 Input 節點來說
        那是 ``["test", "ref"]`` —— 畫布上就看得到「一張 defect、一張 reference」，
        而不是一個什麼都不說的單一輸出。

        還沒接上來源的卡回**空的**（F10）—— 一顆什麼都還沒算出來的輸出埠是
        接得出去的，而接出去的那條線會讓下游指著一條沒有人產出的流。
        以前這裡的 ``or [""]`` 保證每張卡至少有一顆埠，所以「前後都是空的」
        這件事在畫布上表達不出來。
        """
        return [str(d["name"]) for d in self.out_specs()]

    def out_specs(self) -> List[Dict[str, str]]:
        """每一顆輸出埠：``[{"name","kind"}, …]``。影像在前，區域在後（F12）。

        區域也是這張卡**產出**的東西（``resolve_regions_out``），只是它流的不是
        像素。以前畫布上它完全沒有出口，於是「這張卡定義的區域被誰用了」在畫面
        上是看不見的 —— 那條依賴真的存在（拿掉這張卡，下游會安靜地改量整張圖）。
        """
        outs = [{"name": str(w), "kind": "image"}
                for w in (self.info.get("writes") or []) if str(w)][:_MAX_PORTS]
        outs += [{"name": str(r), "kind": "region"}
                 for r in (self.info.get("regions_out") or [])
                 if str(r)][:_MAX_REGION_PORTS]
        return outs

    def out_kinds(self) -> List[str]:
        return [d["kind"] for d in self.out_specs()]

    def out_kind(self, index: int) -> str:
        kinds = self.out_kinds()
        return kinds[index] if 0 <= index < len(kinds) else "image"

    def out_anchors_local(self) -> List[QPointF]:
        """每個輸出埠在**本地座標**的位置（由上而下均分節點右緣）。

        ``paint()`` 畫的是本地座標，連線算的是場景座標 —— 兩者差一個
        ``scenePos()``。之前只有場景座標版，``paint()`` 直接拿去畫，於是節點一
        離開原點，輸出埠就被畫到 ``2 × 位移`` 的地方：第一欄的 Input 看起來正常
        （它剛好在原點），後面每一張卡的右側圓點都畫到卡外面去，看起來就是
        **「新增的節點只有前面有圓框、後面沒有」**；拖動 Input 時埠標籤
        （test/ref）也會離開 ``boundingRect``，留下擦不掉的殘影。

        沒有輸出流就**一顆埠都沒有**（F10）—— 拉不出線，因為真的沒有東西
        可以拉。
        """
        n = len(self.out_names())
        if n == 0:
            return []
        h = self.body_height()
        if n == 1:
            return [QPointF(NODE_W, h / 2.0)]
        step = h / (n + 1)
        return [QPointF(NODE_W, step * (i + 1)) for i in range(n)]

    def out_anchors(self) -> List[QPointF]:
        """每個輸出埠在**場景座標**的位置（連線用）。"""
        base = self.scenePos()
        return [base + p for p in self.out_anchors_local()]

    def out_port(self, index: int = 0) -> QPointF:
        anchors = self.out_anchors()
        if not anchors:
            # 這張卡現在沒有輸出埠（還沒接上來源）。已經存在的線仍然要畫得
            # 出來 —— 畫在右緣中點，看起來就是「線從這張卡出來、但這張卡上
            # 沒有埠」。那正是實情，不要為了好看假裝有一顆埠。
            return self.scenePos() + QPointF(NODE_W, self.height() / 2.0)
        return anchors[max(0, min(int(index), len(anchors) - 1))]

    def out_port_at(self, pos: QPointF):
        """本地座標 ``pos`` 命中哪一個輸出埠（沒命中回 ``None``）。

        **取最近的那一顆，不是第一顆碰到的。** 以前這裡是「由上往下找，第一個
        落在半徑內的就算」—— 而抓取半徑（15px）比埠的間距（三個埠時 14px）還
        大，於是**上面那顆把下面的吃掉**：`subtract` 的三個埠（diff / test /
        ref）點在 `test` 的圓心上拉出來的是 `diff`，點在 `ref` 的圓心上拉出來
        的是 `test`。

        症狀是使用者說的「一連多的時候點不到、線拉不出來」—— 但它其實比點不到
        更糟：**線拉得出來，只是拉到隔壁那條流**，而畫面上那條線看起來完全正常。
        跑得完、有數字、而且是錯的。

        取最近的之後，每顆埠自然拿到「到鄰居的一半」那段，最上與最下那顆對外
        仍然有完整的 15px 可以瞄。半徑不必跟著埠數縮小（縮了只會讓每顆都更難
        點）—— 要分的是「這一下比較靠近誰」，不是「有沒有碰到」。
        """
        best, best_d2 = None, None
        for i, local in enumerate(self.out_anchors_local()):
            d = pos - local
            d2 = d.x() * d.x() + d.y() * d.y()
            if d2 <= _PORT_GRAB ** 2 and (best_d2 is None or d2 < best_d2):
                best, best_d2 = i, d2
        return best

    # -- 繪製 ---------------------------------------------------------------
    @staticmethod
    def terse_at(scale: float) -> bool:
        """縮到這個比例時，這張卡要不要收掉小字（F78）。

        跟 :meth:`_EdgeItem.line_pen` 同一個理由拉出來：判斷寫在 paint 裡就
        只有數像素才驗得到。
        """
        return float(scale) < _LOD_TERSE

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        enabled = bool(self.info.get("enabled", True))
        selected = self.isSelected()
        # 卡片本體不含腳帶 —— 邊框、光暈、投影都照本體畫，腳帶是接在它下面
        # 的一條，不是把卡片變高。
        body = QRectF(0, 0, NODE_W, self.body_height())

        p.setRenderHint(QPainter.Antialiasing, True)

        # 這張卡現在被縮到多小（F78）。讀 painter 的 world transform 而不是
        # `_opt.levelOfDetailFromTransform`：節點沒有自己的 transform，兩者
        # 同值，而這一支不必去信一個平常被丟掉的參數。
        terse = self.terse_at(p.worldTransform().m11())
        radius = card_radius()

        # 投影：讓節點浮在網格之上。用畫的而不是 QGraphicsDropShadowEffect ——
        # effect 會強迫 Qt 額外開一層離屏 buffer，為了 2px 的陰影不值得。
        # hover / 選中時深一階：跟按鈕的 hover 同一個語言 ——「這個東西回應你」。
        lifted = (self._hover or selected) and enabled
        shadow = QColor(0, 0, 0, (64 if lifted else 46) if enabled else 22)
        p.setPen(Qt.NoPen)
        p.setBrush(shadow)
        p.drawRoundedRect(body.translated(1.5, 2.5 if not lifted else 3.0),
                          radius, radius)

        gid = str(self.info.get("group", "") or "enhance")
        tile_col = QColor(theme.group_hex(gid) if enabled else TOKENS["seg_disabled"])

        if selected:
            # 選中的光暈：一圈 3px 的半透明 accent，畫在邊框**外面**。
            # 只加粗邊框的話，在一整排 1px 灰框的卡片裡要找「哪張是 2px 藍框」
            # 得一張一張看 —— 光暈讓選中的那張在餘光裡就跳出來。
            halo = QColor(TOKENS["accent"])
            halo.setAlpha(56)
            p.setPen(QPen(halo, 6.0))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(body, radius, radius)

        if selected:
            border = QColor(TOKENS["accent"])
        elif self._hover and enabled:
            border = QColor(TOKENS["accent"])
            border.setAlpha(150)
        else:
            border = QColor(TOKENS["border_default"])
        # 停用的節點畫虛線框（n8n 的慣例）—— 不是消失，是「還在，但這次不跑」。
        pen = QPen(border, 2.0 if selected else (1.4 if self._hover and enabled
                                                 else 1.0))
        if not enabled:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(TOKENS["bg_surface"] if enabled else TOKENS["disabled_bg"]))
        p.drawRoundedRect(body, radius, radius)

        # 「整批跑一次」的腳帶（F50）。畫在本體**下面**，同一個圓角收邊。
        if self.is_lot():
            self._paint_lot_strip(p, body, tile_col, enabled)

        # 左邊的圖示磚：淡色底 + 與左側 rail 完全相同的圖形（F7-8）。
        tile = QRectF(8, (min(NODE_H, self.body_height()) - _TILE) / 2.0,
                      _TILE, _TILE)
        wash = QColor(tile_col)
        wash.setAlpha(46 if enabled else 24)
        p.setPen(QPen(tile_col if enabled else QColor(TOKENS["border_default"]), 1.0))
        p.setBrush(wash)
        p.drawRoundedRect(tile, radius, radius)

        icon_rect = QRectF(tile.center().x() - _ICON / 2.0,
                           tile.center().y() - _ICON / 2.0, _ICON, _ICON)
        p.save()
        p.translate(icon_rect.topLeft())
        draw_group_icon(p, gid, tile_col.name(), _ICON)
        p.restore()

        # 「這張卡還不能跑」的標記（F7-13）。lint 早就知道這件事，只是那個知識
        # 以前留在跑之前的檢查裡 —— 於是一張缺模板的卡在畫布上看起來跟設定完整
        # 的一模一樣，使用者要按下 Run trial 才會知道。
        self._paint_badge(p, body)

        text_x = tile.right() + 9
        # 有警示標記時把標題讓開 —— 不讓的話標記正好蓋在卡片名字的尾巴上，
        # 兩個東西都變得難讀。
        text_w = NODE_W - text_x - (8 if not self.problem() else 22)

        fg = TOKENS["text_primary"] if enabled else TOKENS["text_disabled"]
        p.setPen(QColor(fg))
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(max(7.0, f.pointSizeF()))
        p.setFont(f)
        # 縮很小的時候**標題留著**（那是這張卡的身分，也是唯一還讀得出輪廓的
        # 一行），副標與設定摘要收掉 —— 見 `_LOD_TERSE`。
        if terse:
            # 只剩一行的時候把它擺到卡片中線上，不然標題會孤零零貼在上緣、
            # 底下空一大塊，看起來像沒畫完。
            _draw_elided(p, QRectF(text_x, (min(NODE_H, self.body_height()) - 16) / 2.0,
                                   text_w, 16),
                         str(self.info.get("label", self.node_id)))
        else:
            _draw_elided(p, QRectF(text_x, 11, text_w, 16),
                         str(self.info.get("label", self.node_id)))
            f.setBold(False)
            f.setPointSizeF(max(6.0, f.pointSizeF() - 1.0))
            p.setFont(f)
            p.setPen(QColor(TOKENS["text_secondary"] if enabled
                            else TOKENS["text_disabled"]))
            _draw_elided(p, QRectF(text_x, 28, text_w, 14), self.subtitle())
            parts = self.summary_parts()
            if parts:
                _draw_parts(p, QRectF(text_x, 43, text_w, 14), parts)

        # 連接埠（**本地座標** —— 見 out_anchors_local 的說明）。
        # 輸入是空心圈、輸出是實心點：一眼看得出線該從哪邊拉到哪邊。
        ins = self.in_specs()
        in_anchors = self.in_anchors_local()
        lit_names = self._ports_to_light()
        for i, anchor in enumerate(in_anchors):
            kind = str(ins[i].get("kind") or "image") if i < len(ins) else "image"
            role = str(ins[i].get("role") or "") if i < len(ins) else ""
            name = str(ins[i].get("name") or "") if i < len(ins) else ""
            _draw_port(p, anchor, kind, filled=False, role=role,
                       lit=name in lit_names)
            if terse or len(ins) < 2 or i >= len(ins):
                continue
            # 兩個以上的輸入才標名字：一顆埠的時候「這條線接到哪」沒有歧義，
            # 標了只是多一個字；兩顆以上不標的話，使用者要去猜上面那顆是
            # `First stream` 還是 `Second stream` —— 而猜錯了畫面上完全看不
            # 出來（兩張圖相減，a 與 b 反過來就是整張圖的正負號反過來）。
            text = _port_label_text(ins[i])
            if not text:
                continue
            p.setPen(QColor(TOKENS["text_secondary"] if kind != "region"
                            else region_color().name()))
            # **放不下就切在後面加省略號**（F13-⑤）。以前是直接 drawText 進一個
            # 52px 的框，Qt 對靠右對齊的字是**從左邊硬切**的 —— `Borrow range
            # from` 於是畫成 `nge from`，讀起來像另一個欄位的名字。
            _draw_elided(p, QRectF(anchor.x() - _PORT_LABEL_W - 4,
                                   anchor.y() - 7, _PORT_LABEL_W, 14),
                         text, align=Qt.AlignRight)

        for spec, anchor in zip(self.out_specs(), self.out_anchors_local()):
            name, kind = spec["name"], spec["kind"]
            _draw_port(p, anchor, kind, filled=True)
            if terse or not name:
                continue
            # 每個輸出埠都標上它吐的名字（F7-9；F12 起也含具名區域）。以前
            # 只有多埠才標，於是「這張卡到底做在哪一條流上」在畫布上是看不到
            # 的 —— 而 Enhance 卡的 target / also apply 講的正是這些名字。
            p.setPen(QColor(region_color().name() if kind == "region"
                            else TOKENS["text_secondary"]))
            # 同左邊那一側：放不下要看得出來被切了（`layout_label` 以前畫成
            # `layout_`，讀起來像一條真的叫那個名字的流）。
            _draw_elided(p, QRectF(anchor.x() + 4, anchor.y() - 7,
                                   _PORT_LABEL_W - 10, 14), name)

    def _paint_lot_strip(self, p: QPainter, body: QRectF,
                         col: QColor, enabled: bool) -> None:
        """卡片底下那條「once per lot」。

        **只用字，不只用顏色**（推廣鐵則）：一條色帶對不會寫 code 的使用者
        不是一句話，而這個標記存在的全部理由就是要講出那句話。顏色跟著段色，
        所以它讀起來是這張卡的一部分，不是貼上去的東西。
        """
        radius = card_radius()
        strip = QRectF(0, body.bottom() - radius, NODE_W, _LOT_STRIP + radius)
        p.save()
        p.setClipRect(QRectF(0, body.bottom(), NODE_W, _LOT_STRIP + 1.0))
        wash = QColor(col if enabled else QColor(TOKENS["seg_disabled"]))
        wash.setAlpha(38 if enabled else 20)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.setBrush(wash)
        p.drawRoundedRect(strip, radius, radius)
        p.restore()

        f = p.font()
        f.setBold(False)
        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.0))
        f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 0.6)
        p.setFont(f)
        p.setPen(QColor(col if enabled else TOKENS["text_disabled"]))
        p.drawText(QRectF(8, body.bottom(), NODE_W - 16, _LOT_STRIP),
                   int(Qt.AlignLeft | Qt.AlignVCenter), LOT_STRIP_TEXT)

    def subtitle(self) -> str:
        """副標：**這張卡吃什麼、吐什麼**（F7-14）。

        以前這一行印的是 node_id（``roi_template``）—— 那是 recipe JSON 的鍵，
        使用者看了得不到任何新資訊：卡片名字就在它上面一行。n8n 的節點副標印的
        是那張卡這次**被設定成做什麼**，所以整張畫布不點開就讀得懂。

        重複的卡片（``glv_stats2``）才把 id 帶出來 —— 那時候「是哪一張」才真的
        是使用者需要知道的事。
        """
        reads = [r for r in (self.info.get("reads") or []) if r]
        # 副標印的是**這張卡真的產出什麼**（``produces``），不是所有輸出埠
        # —— F9-6 起 ``writes`` 還含著「原樣送出的輸入」，全印出來的話
        # 每張卡的副標都會變成「test ref → test ref diff」那種一長串。
        # 用「有沒有這個 key」判斷，**不能用 or** —— 區域卡的 ``produces`` 是
        # 空的（它產出的是具名區域不是影像流），``x or y`` 會因此掉回 ``writes``，
        # 而 F9-6 之後那裡面裝的是「原樣送出的輸入」，副標就變成「diff → diff」。
        _p = (self.info["produces"] if "produces" in self.info
              else self.info.get("writes") or [])
        outs = [w for w in (_p or []) if w]
        # 同理，區域也要分「真的產出的」與「原樣送出的」（F12 第二輪）：
        # 量測卡把接進來的 `epi` 送出去給下一張卡接，但它**沒有定義**它 ——
        # 副標印成「single → epi」的話，那張卡看起來變成一張 Region 卡。
        _r = (self.info["regions_produced"] if "regions_produced" in self.info
              else self.info.get("regions_out") or [])
        regions = [r for r in (_r or []) if r]
        right = " ".join(str(x) for x in (outs or regions))
        left = " ".join(str(r) for r in reads)
        if left and right:
            body = "%s → %s" % (left, right)
        elif left or right:
            body = left or right
        else:
            # 兩邊都空 = **還沒接線**（F10：剛加的卡前後都是空的）。以前這裡印
            # 的是 step_key（`normalize`），而那個字使用者剛剛才在卡片名字那一行
            # 讀過一次英文版 —— 一行沒有新資訊的字。現在直接講狀態，
            # 而下一步（拉一條線過來）由警示標記的 tooltip 講完整。
            body = "(not connected)"
        step_key = str(self.info.get("step_key", ""))
        if step_key and self.node_id != step_key:
            # 同一張卡加了第二次：這時候 id 是有意義的（分數表達式指的是特徵名，
            # 但 lint 訊息與前綴講的是這個 id）。
            body = "%s · %s" % (self.node_id, body)
        return body

    def summary_parts(self) -> List[str]:
        """第三行的各項（``["p_low=1.2", "method=match"]``）。

        Studio 給的是一個 list（`summary_parts`）；舊的 `summary` 字串留著給
        測試與狀態列讀，這裡在缺 list 的時候從它切回來 —— 分隔字串只有一個定義
        （:data:`SUMMARY_SEP`）。
        """
        parts = self.info.get("summary_parts")
        if parts is not None:
            return [str(x) for x in parts if str(x)]
        text = str(self.info.get("summary", "") or "")
        return [s for s in text.split(SUMMARY_SEP) if s]

    def problem(self) -> str:
        """這張卡現在有什麼問題（空字串 = 沒問題）。"""
        return str(self.info.get("problem", "") or "")

    def _paint_badge(self, p: QPainter, body: QRectF) -> None:
        """右上角一個小圓標。錯誤紅、警告琥珀、**info 不畫**。

        文字用 ``!`` 而不是圖形：這個標記只有 14 px，任何再細一點的形狀在
        100% 縮放下都會糊成一個點。
        """
        why = self.problem()
        if not why:
            return
        level = str(self.info.get("problem_level", "error"))
        if not badge_paints(level):
            return
        col = QColor(TOKENS["danger_text"] if level == "error"
                     else TOKENS["warning"])
        r = 7.0
        centre = QPointF(body.right() - r - 3.0, body.top() + r + 3.0)
        p.setPen(QPen(QColor(TOKENS["bg_surface"]), 1.5))
        p.setBrush(QBrush(col))
        p.drawEllipse(centre, r, r)
        p.setPen(QPen(QColor("#ffffff"), 1.0))
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(8.0)
        p.setFont(f)
        p.drawText(QRectF(centre.x() - r, centre.y() - r, 2 * r, 2 * r),
                   Qt.AlignCenter, "!")

    # -- 互動 ---------------------------------------------------------------
    def set_hovered(self, hovered: bool) -> None:
        """view 判斷出來的 hover 狀態（見 __init__ 的說明）。"""
        if bool(hovered) != self._hover:
            self._hover = bool(hovered)
            self.update()

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        hit = (self.out_port_at(e.pos())
               if e.button() == Qt.LeftButton else None)
        if hit is not None:
            self.canvas.begin_link(self, hit)  # 從某一個輸出埠拉線
            e.accept()
            return
        self.canvas.node_selected.emit(self.node_id)
        # 從這裡到放開為止，位置的改變都是**使用者的手**（見 itemChange）。
        self._dragging = e.button() == Qt.LeftButton
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:    # noqa: D102 - Qt hook
        self._dragging = False
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: D102 - Qt hook
        """雙擊 = 打開這張卡的設定（F7-22，n8n 的動作）。

        參數面板平常是收起來的，畫布因此吃得到整欄。單擊仍然只是選取
        （右邊的預覽會跟著跑到這張卡為止），雙擊才把設定攤開。
        """
        self.canvas.node_selected.emit(self.node_id)
        self.canvas.node_activated.emit(self.node_id)
        e.accept()

    def itemChange(self, change, value):        # noqa: D102 - Qt hook
        if change == QGraphicsItem.ItemPositionChange and self._dragging:
            return self._snapped(value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.canvas.refresh_edges()
        return super().itemChange(change, value)

    @staticmethod
    def _snapped(pos: QPointF) -> QPointF:
        """把拖到的位置吸到格線上（F79）。

        ⚠ **只吸使用者拖的那一下，不吸 ``setPos``。** 兩個理由，第二個才是硬的：

        1. 吸附是**手勢的一部分**（拖到附近就對齊），不是座標系的性質。
        2. ``setPos`` 是別的程式碼**重現**一個位置的路：彈出視窗要跟主畫布擺
           在一樣的地方、重建畫布要把使用者拖好的佈局放回去。那條路一旦量化
           就不再是 identity —— 存 333 讀回 340、再存 340…… 每重建一次就漂一
           格。這跟鐵則 9（``to_json_dict → from_json_dict`` 必須是 identity）
           是同一種 bug，只是這裡漂的是像素不是分數。

        所以判準是「這一下是不是從 ``mousePressEvent`` 來的」，見 ``_dragging``。
        """
        step = GRID
        return QPointF(round(pos.x() / step) * step,
                       round(pos.y() / step) * step)

    def show_context_menu(self, screen_pos) -> None:
        """這張卡的右鍵選單。

        入口有兩個：Qt 原生的 contextMenuEvent（鍵盤選單鍵等），以及
        view 的「右鍵原地放開」（右鍵拖曳被平移接管之後，選單改由那裡開）。
        """
        menu = QMenu()
        act_toggle = menu.addAction(
            "Skip this step" if self.info.get("enabled", True) else "Enable this step")
        act_remove = menu.addAction("Remove")
        chosen = menu.exec(screen_pos)
        if chosen is act_toggle:
            self.canvas.node_toggled.emit(
                self.node_id, not bool(self.info.get("enabled", True)))
        elif chosen is act_remove:
            self.canvas.remove_requested.emit(self.node_id)

    def contextMenuEvent(self, e) -> None:      # noqa: D102 - Qt hook
        self.show_context_menu(e.screenPos())
        e.accept()


class _EdgeItem(QGraphicsItem):
    """一條連線（三次貝茲，左→右）。點它可選取，``Delete`` 移除。

    歷史：F7-10 起這裡還有第二種線 —— route 隱含順序的金色虛線
    （``implicit=True``）。**2026-08-14 使用者退掉了它**：「會混淆」。
    ⚠ **引擎那一句在 F17-① 之後不成立了**：執行順序的邊**只**來自
    ``recipe.edges``，route 的排列退成 Kahn 的平手依據（見
    `core/pipeline/recipe.py` 的 `execution_order`）。排版仍然吃排列順序
    （``set_nodes`` 的 ``self._implicit``），但理由換了 —— 見那裡的說明。
    F7-10 擔心的「沒有線以為互不相干」由現在的預設行為緩解：從卡片庫加卡
    （``add_card_after``）與拖放都會建**顯式**連線，新做的 recipe 天生有線。
    """

    def __init__(self, src: _NodeItem, dst: _NodeItem, canvas: "PipelineCanvas",
                 port: int = 0, dst_port: int = 0):
        super().__init__()
        self.src, self.dst, self.canvas, self.port = src, dst, canvas, int(port)
        #: 進的是下游的第幾顆輸入埠（F10）。兩條線接進同一張卡的不同輸入時，
        #: 它們在畫布上必須落在**不同**的點 —— 疊在一起的話，「這張卡的 a 跟
        #: b 各自接了什麼」在畫面上就消失了。
        self.dst_port = int(dst_port)
        self._hover = False
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(_Z_EDGE)
        # 滑鼠移上來要出現「斷開」的 ×（F7-22）。
        self.setAcceptHoverEvents(True)
        what = ("region “%s”" % self.out_name() if self.kind() == "region"
                else "image")
        self.setToolTip("%s → %s  (%s; click the × to disconnect)"
                        % (src.node_id, dst.node_id, what))

    def kind(self) -> str:
        """這條線搬的是影像還是區域（F12）—— **由它出發的那顆埠決定**。

        不另外存一個旗標：埠已經知道自己是哪一種，而兩份會漂。
        """
        return self.src.out_kind(self.port)

    def line_color(self, strength: float = 0.5) -> QColor:
        """這條線的顏色 —— **來源那張卡的階段色，但調淡一半**（F13-⑤）。

        全部畫成灰的時候，一張擠了十條線的畫布上「這條是從哪裡出來的」只能
        用眼睛沿著線走。給它來源的階段色就答得出來了，而顏色跟卡片左邊那塊
        圖示磚是同一個 —— 不必再學一組意思。

        **調淡一半**是重點：原色會讓畫布變成一團彩虹，而線是背景不是主角
        （它們平常畫在卡片**底下**，見 `_Z_EDGE`）。混一半灰之後，同一條線
        仍然分得出色系，但整張圖的重量還在卡片上。

        ``strength`` 是那個「一半」（F78）。選中一張卡的時候，接著它的線要
        **把同一個顏色調回來**而不是換成另一個顏色 —— 換色的話使用者得學
        「藍色 = 被選中的線」這第二層意思，而調濃只是把原本就在那裡的線索
        講大聲一點。
        """
        base = QColor(TOKENS["canvas_edge"])
        gid = str(self.src.info.get("group", "") or "")
        if not gid:
            return base
        return QColor(theme.mix_hex(theme.group_hex(gid),
                                    TOKENS["canvas_edge"], float(strength)))

    # ---- 選中一張卡時，它的線要跟著講話（F78）-----------------------------
    def focus_state(self) -> str:
        """這條線相對於**目前選中的那張卡**是什麼身分。

        ``"flat"``（沒有選任何卡）／``"near"``（接著選中的卡）／
        ``"far"``（有選，但跟它無關）。

        為什麼要有這件事：選一張卡以前只有那張卡自己有反應，而使用者點它
        的理由通常正是「它接了誰」—— 那個問題在畫面上要用眼睛沿著線走才答
        得出來，一張擠了十條線的畫布上根本走不完。
        """
        if not self.canvas.has_node_selection():
            return "flat"
        return "near" if (self.src.isSelected() or self.dst.isSelected()) else "far"

    # ---- 斷開鈕（F7-22）---------------------------------------------------
    #: 斷開鈕的命中半徑。畫出來的圓是 ``_CUT_R``，多給 2px 是因為使用者瞄的是
    #: 圓心不是圓周 —— 但 :meth:`shape` 必須用**同一個值**，見那裡的說明。
    CUT_GRAB = _CUT_R + 2.0

    def cut_center(self) -> QPointF:
        """×（斷開鈕）的圓心 —— 線的中點。"""
        return self.path().pointAtPercent(0.5)

    def cut_hit(self, pos: QPointF) -> bool:
        d = pos - self.cut_center()
        return (d.x() * d.x() + d.y() * d.y()) <= self.CUT_GRAB ** 2

    def hoverEnterEvent(self, e) -> None:       # noqa: D102 - Qt hook
        self._hover = True
        # 提到節點之上（節點是 0）。滑鼠已經在這條線上了，這時候它就是使用者
        # 正在瞄的東西 —— 而它平常畫在卡片底下，中點只要被任何一張卡蓋到，
        # 那顆 × 就既看不見也按不到。抬起來之後「看得到的」與「按得到的」
        # 恆等，不必再去推敲這條線的中點會落在誰身上。離開時放回去。
        self.setZValue(_Z_EDGE_HOVER)
        self.update()
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e) -> None:       # noqa: D102 - Qt hook
        self._hover = False
        self.setZValue(_Z_EDGE)
        self.update()
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e) -> None:       # noqa: D102 - Qt hook
        if (self._hover
                and e.button() == Qt.LeftButton and self.cut_hit(e.pos())):
            self.canvas.edge_removed.emit(self.src.node_id, self.dst.node_id,
                                          self.out_name(), self.dst_name())
            e.accept()
            return
        super().mousePressEvent(e)

    def pair(self) -> Tuple[str, str]:
        return (self.src.node_id, self.dst.node_id)

    def dst_name(self) -> str:
        """這條線進的是下游的哪一個輸入參數（``a`` / ``b`` / ``streams``…）。"""
        specs = self.dst.in_specs()
        if 0 <= self.dst_port < len(specs):
            return str(specs[self.dst_port].get("name", ""))
        return ""

    def out_name(self) -> str:
        """這條線從來源的哪一顆輸出埠出發（埠索引換算成流名）。"""
        outs = self.src.out_names()
        return str(outs[self.port]) if 0 <= self.port < len(outs) else ""

    #: 往回走的線，控制點往外推多遠（固定值，**不隨距離長大**）。
    BACK_REACH = 46.0

    def path(self) -> QPainterPath:
        """左→右的三次貝茲；**往回走的線走另一個形狀**。

        埠是固定的：出在右邊、進在左邊。所以當下游那張卡排在上游**左邊**時
        （換行 —— 上一列的最後一張接下一列的第一張），這條線本來就得往回走。

        以前不管往哪走都用同一條式子（控制點水平推 ``|Δx| * 0.5``）。往前走時
        那是對的，往回走時 Δx 是一整列的寬度，於是控制點被推到 a 的右邊 350px
        與 b 的左邊 350px —— 一條連兩張卡的線橫掃了七百多 px，還甩到比第一張卡
        更左邊。三列就是三條這種折線橫過整張畫布，**比它要表達的「順序」還
        搶眼**，而它表達的只是「這兩張卡有先後」。

        往回走改成：水平只推一個固定的小距離，剩下的量交給**垂直**方向。
        線因此收在兩列之間的帶子裡，兩端各只超出 ``BACK_REACH``。
        """
        a, b = self.src.out_port(self.port), self.dst.in_port(self.dst_port)
        dx = b.x() - a.x()
        p = QPainterPath(a)
        if dx >= 2 * self.BACK_REACH:
            # 水平推力的下限是 COL_GAP 的 2/3：推力太小（以前是 40，縮放 70%
            # 之後只剩 28px）曲線就退化成斜的直線，n8n 那種「從埠水平流出、
            # 水平流入」的秩序感整個不見 —— 看起來像線亂穿，其實是切線不夠平。
            h = max(COL_GAP * 0.67, dx * 0.5)
            p.cubicTo(a + QPointF(h, 0), b - QPointF(h, 0), b)
            return p
        h = self.BACK_REACH
        v = max(30.0, abs(b.y() - a.y()) * 0.5)
        sign = 1.0 if b.y() >= a.y() else -1.0
        p.cubicTo(a + QPointF(h, sign * v), b - QPointF(h, sign * v), b)
        return p

    def boundingRect(self) -> QRectF:
        # ``_CUT_R + 2`` 是那顆 × 的半徑。**boundingRect 必須涵蓋所有畫得出去的
        # 東西** —— 一條水平的線本身高度接近 0，而 × 畫在中點上下各 8 px；
        # 不加寬的話 Qt 只會重繪那條細長條，滑鼠移開之後 × 的舊位置擦不掉。
        # （這個坑在節點那邊踩過三次了：埠標籤、埠圓點、輸出埠的 +。）
        pad = max(6.0, _CUT_R + 3.0)
        return self.path().boundingRect().adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        """線本身（加粗到 10px 好瞄）**加上斷開鈕那顆圓**。

        少了那顆圓的話，畫出來的 × 有一圈是點不到的：stroke 只給線的兩側各
        5px，而 × 的半徑是 ``_CUT_R``（8）、``cut_hit`` 更收到 ``CUT_GRAB``
        （10）。差的那幾 px 不是邊角料 —— 它是那顆圓**四分之一以上的面積**，
        而且滑鼠一走進去就離開了 shape，於是 hover 結束、× 當場消失，
        按下去的是空的畫布。使用者的描述會是「有時候按得動，有時候按不動」。

        所以這裡跟 ``cut_hit`` 讀同一個 ``CUT_GRAB``：**點得到的範圍與
        判定命中的範圍是同一個定義**，不會再各自演化。
        """
        st = QPainterPathStroker(QPen(Qt.black, 10.0))
        path = st.createStroke(self.path())
        disc = QPainterPath()
        disc.addEllipse(self.cut_center(), self.CUT_GRAB, self.CUT_GRAB)
        path = path.united(disc)
        return path

    #: 三種身分各自的（濃度, 線寬）。``near`` 把 :meth:`line_color` 的「一半」
    #: 調回九成（同一個色相、講大聲一點）；``far`` 則是把線往畫布底色混掉
    #: 過半 —— **壓下去的那些不能消失**，它們仍然是這張圖的骨架，只是這一刻
    #: 不是使用者在問的東西。
    _FOCUS = {"flat": (0.50, 1.6), "near": (0.90, 2.2), "far": (0.50, 1.6)}
    #: ``far`` 的線往 ``canvas_bg`` 混多少（0 = 不動，1 = 完全消失）。
    _FADE = 0.55

    def line_pen(self) -> QPen:
        """這條線現在要用哪一支筆 —— **顏色、粗細、虛實的唯一定義**。

        獨立成一支而不是寫在 :meth:`paint` 裡，理由跟 :meth:`shape` 與
        ``cut_hit`` 讀同一個 ``CUT_GRAB`` 一模一樣：**看得到的與測得到的必須是
        同一個定義**。寫在 paint 裡的話，要驗「選中一張卡，它的線有沒有真的
        亮起來」只能去數像素 —— 而那種測試會在任何一次改字體、改抗鋸齒的時候
        變紅，於是很快就沒有人相信它。
        """
        region = self.kind() == "region"
        state = self.focus_state()
        strength, width = self._FOCUS[state]
        if self.isSelected():
            col = QColor(TOKENS["canvas_edge_active"])
            width = 2.2
        elif self._hover:
            # 滑鼠移上來時**線本身**也要動（F78）。以前只有中點長出那顆紅 ×，
            # 而線可以很長 —— × 離兩端各一百多 px，餘光裡「我現在瞄到的是哪
            # 一條」沒有答案。抬 z 值（見 hoverEnterEvent）解的是「看不看得
            # 到」，這一行解的是「認不認得出」。
            col = QColor(TOKENS["canvas_edge_active"])
            width = 2.4
        elif region:
            # 區域線本來就畫原色（它是虛線，已經跟影像流分得開），所以 ``near``
            # 在這一支只剩加粗 —— 濃度沒有可以再調的空間。
            col = region_color()
        else:
            col = self.line_color(strength)
        if state == "far" and not (self.isSelected() or self._hover):
            col = QColor(theme.mix_hex(col.name(), TOKENS["canvas_bg"],
                                       1.0 - self._FADE))
        # 區域線畫**虛線**：它搬的不是像素，而使用者要在餘光裡就分得出這兩種
        # 線（它們接不到彼此）。顏色是 Region 段的階段色，跟卡片上那顆圖示磚
        # 同一個 —— 不必再學一組新的意思。
        pen = QPen(col, width)
        if region:
            pen.setStyle(Qt.DashLine)
            pen.setDashPattern([4.0, 3.0])
        return pen

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        path = self.path()
        pen = self.line_pen()
        col = pen.color()
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # 滑鼠在線上 → 中點換成一顆「斷開」的 ×（F7-22）。
        #
        # 選起來按 Delete 本來就做得到，但**畫面上沒有任何東西講出這件事** ——
        # 接錯一條線的人會卡在那裡。刪除的入口要長在被刪的東西上面。
        # 箭頭跟 × 二選一：兩個都畫在中點會疊成一團。
        if self._hover:
            c = self.cut_center()
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(TOKENS["danger_text"])))
            p.drawEllipse(c, _CUT_R, _CUT_R)
            p.setPen(QPen(QColor(TOKENS["bg_surface"]), 1.6))
            d = _CUT_R * 0.45
            p.drawLine(c + QPointF(-d, -d), c + QPointF(d, d))
            p.drawLine(c + QPointF(-d, d), c + QPointF(d, -d))
            return

        # 中點的方向箭頭。畫布可以縮放、平移、節點也可以拖，光看一條曲線不一定
        # 分得出資料往哪一邊流 —— 這是「這是一張流程圖」的最基本線索。
        mid = path.pointAtPercent(0.5)
        ang = path.angleAtPercent(0.5)
        p.save()
        p.translate(mid)
        p.rotate(-ang)
        head = QPainterPath(QPointF(_ARROW, 0.0))
        head.lineTo(QPointF(-_ARROW * 0.8, _ARROW * 0.72))
        head.lineTo(QPointF(-_ARROW * 0.8, -_ARROW * 0.72))
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(head)
        p.restore()


class PipelineCanvas(QGraphicsView):
    """節點畫布。對外的 API 與訊號刻意與舊的 ``PipelinePanel`` 對齊。

    Studio 只要換掉建構的類別，其餘接線幾乎不動 —— 這是為了讓「換 UI」
    不要順便變成「重寫主視窗」。
    """

    node_selected = Signal(str)
    #: 雙擊一張卡 = 「我要編它」（F7-22）。單擊只是選取。
    node_activated = Signal(str)
    node_toggled = Signal(str, bool)
    move_requested = Signal(str, int)          # 相容用，畫布不發
    remove_requested = Signal(str)
    score_clicked = Signal()
    #: ``(來源節點, 目標節點, 這條線帶的影像流名)``。第三個參數是 F7-18 加的：
    #: 使用者從 ``ref`` 那個埠拉一條線到某張卡，講的就是「這張卡做在 ref 上」。
    #: 沒有它的話，畫布只能表達「先後順序」，而「對哪一張圖做」還是得回到
    #: 控制列上的下拉去設 —— 那正是使用者說「變很複雜」的東西。
    #: 來源節點只有一個沒有名字的輸出埠時是空字串。
    #: ``(來源, 目的, 來源的輸出埠, 目的的輸入參數)``。第四個是 F10 加的：
    #: 以前「線落在哪個參數上」是 Studio 用固定順序**猜**的（streams → target
    #: → source），於是 ``subtract`` 的 ``a`` / ``b`` 根本分不開 —— 兩顆輸入，
    #: 一條線，猜中的那個永遠是同一個。現在由**使用者放開滑鼠的位置**決定。
    edge_added = Signal(str, str, str, str)
    #: ``(來源, 目的, 來源埠)`` —— 埠是剪刀剪的**那一條**（F9-9：兩張卡之間
    #: 可以有兩條並排的線，剪一條跟剪兩條是完全不同的事）。
    #: 第四欄是 F10 加的：兩條線可能從**同一顆輸出埠**進到同一張卡的兩個不同
    #: 輸入（load 的 test 同時餵 a 與 b 是合法的），只靠來源埠指不出剪的是哪條。
    edge_removed = Signal(str, str, str, str)
    #: 從卡片庫拖一張卡丟到畫布上：``(step_key, 場景 x, 場景 y)``（F7-22）。
    card_dropped = Signal(str, float, float)
    #: 「在自己的視窗打開畫布」（F8-UI D 案）。畫布在主視窗只佔中上一塊
    #: （它會 zoom，不需要常駐大面積），要看全貌就彈出去。
    popout_requested = Signal()
    #: 點了判定區的入口小卡（F24 ②）——「跳到判定的編輯」。
    #: 入口卡永遠恰好一個、不能刪，所以這裡沒有 id 要帶。
    decision_clicked = Signal()
    #: 使用者按了判定區右上角那顆 ✕（2026-08-25）。畫布只**請**，
    #: 要不要真的拿掉由 Studio 決定（底下掛著一整棵樹，要問過）。
    decision_remove_requested = Signal()
    #: 點了畫布上的分流徽章（F25-B）—— 去編 route_by。
    prefilter_clicked = Signal()
    #: 點了判定樹的一個菱形／托盤（F24 ③）—— 帶的是**路徑**（"" = 根、
    #: "yn…" 一路往下）。節點是 frozen dataclass，路徑才是唯一的身分。
    tree_step_clicked = Signal(str)
    tree_leaf_clicked = Signal(str)

    def __init__(self, parent=None, popout_button: bool = True):
        super().__init__(parent)
        #: 彈出視窗裡的那份畫布把這顆鈕關掉 —— 從彈出視窗再彈一個視窗，
        #: 沒有那種需求，只有無限套娃。
        self._popout_button = bool(popout_button)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        #: 現在有沒有選中任何一張卡（F78）。線在 paint 裡要問這件事，而每一條
        #: 線問一次「掃過所有節點」是 O(線 × 卡)；存一個旗標就是 O(1)。
        self._sel_nodes = False
        # 節點 hover（_sync_hover_node）與線上的 × 都吃「沒按鍵也送 move」。
        # QGraphicsView 建構時本來就會把 viewport 的 mouseTracking 打開
        # （item hover 靠它），這行是把**依賴講明**：哪天換了 viewport 或
        # base style 把它關掉，hover 會安靜地只剩拖曳時有效。
        self.viewport().setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)                 # 卡片庫拖進來（F7-22）
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setMinimumHeight(180)

        self._items: Dict[str, _NodeItem] = {}
        self._edges: List[_EdgeItem] = []
        # **接 scene 的訊號，不是接 set_selected**：選取有三條路（點卡片、
        # 框選、程式呼叫 set_selected），只補其中一條的話，另外兩條選出來的
        # 卡片線不會亮 —— 而那正是「有時候會亮有時候不會」這種找不到的 bug。
        # 接在 `_items` / `_edges` **之後**：handler 讀這兩個，而場景這時是空的
        # （訊號不會提早響），但那件事不值得靠它撐著。
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._order: List[str] = []
        self._pairs: List[Tuple[str, str]] = []      # 使用者拉的線
        self._implicit: List[Tuple[str, str]] = []   # route 順序帶來的依賴
        self._selected: Optional[str] = None
        self._score_summary = ""
        self._link_from: Optional[_NodeItem] = None
        self._link_port = 0
        self._link_line = None
        #: 現在游標壓著哪張卡（hover 回饋）。由這裡追而不是讓卡片自己收
        #: hover 事件 —— 卡片一收，事件就穿不過去，線上的 × 會被悶死。
        self._hover_node: Optional[_NodeItem] = None
        #: 右鍵平移的狀態（None = 沒在平移）。
        self._pan_last = None
        self._pan_moved = False
        self._build_zoom_bar()
        self._build_header()

    # ---- 這一欄叫什麼（F13-4）---------------------------------------------
    def _build_header(self) -> None:
        """畫布左上角的地標。

        它跟 zoom bar 同一種做法（**浮在畫布上的子 widget**，不佔版面）——
        畫布在主視窗裡是 splitter 的直接子項，包一層容器會讓
        「``canvas_column.widget(0)`` 就是畫布」這件事不再成立，而好幾條測試與
        彈出視窗的邏輯都靠它。一個地標不值得換掉那個形狀。
        """
        from .widgets import column_header

        self._header = column_header("Pipeline", self)
        self._header.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._place_header()

    def _place_header(self) -> None:
        lbl = getattr(self, "_header", None)
        if lbl is not None:
            lbl.adjustSize()
            lbl.move(9, 6)
            lbl.raise_()

    # ---- 縮放控制（F7-14）--------------------------------------------------
    def _build_zoom_bar(self) -> None:
        """左下角幾顆小鈕：縮小 / 放大 / 全部看得完 / 回到 100% / 排整齊。

        滾輪縮放本來就有，但**畫面上沒有任何東西說得出這件事** —— 而且滾過頭
        之後沒有路回來：點陣底縮小之後每一格都一樣，使用者不知道自己在哪裡。
        n8n 把這四顆固定放在左下角，這裡照做（順便顯示目前的百分比，
        「我到底縮到多小了」也是看不出來的事）。
        """
        bar = QWidget(self)
        bar.setObjectName("canvasZoom")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(2)
        self._zoom_label = QLabel("100%", bar)
        self._zoom_label.setObjectName("paramHint")
        self._zoom_label.setMinimumWidth(38)
        self._zoom_label.setAlignment(Qt.AlignCenter)

        # ``1:1`` 留成文字（數字與冒號是 ASCII，哪台機器都畫得出來）；其餘四顆
        # 改成自繪圖示 —— ``⤢`` 與 ``⌗`` 在 Windows 的 Segoe UI 根本沒有
        # （F7-23 第四輪，見 widgets.draw_glyph_icon）。
        specs = [("zoom_out", "Zoom out", lambda: self.zoom_by(1 / 1.25)),
                 ("zoom_in", "Zoom in", lambda: self.zoom_by(1.25)),
                 ("fit", "Fit the whole pipeline in view", self.fit),
                 (None, "Back to 100%", self.reset_zoom),
                 # 排整齊跟縮放是同一類東西（都只動「怎麼看」，不動 recipe），
                 # 所以放同一排，而不是放到會改檔案的工具列上。
                 ("tidy", "Tidy up — put the cards back on the grid", self.tidy)]
        if self._popout_button:
            # 「彈出視窗」也是「怎麼看」的一種 —— 主視窗的畫布只佔中上一塊
            # （D 案），要看全貌就到自己的視窗看。
            specs.append(("popout", "Open the pipeline in its own window",
                          self.popout_requested.emit))
        self._zoom_buttons = []
        for icon, tip, slot in specs:
            # 這一排浮在畫布上，所以要 ``kind="icon"``（自己的底）。
            if icon is None:
                b = small_button("1:1", tip, bar, kind="icon", shape="wide")
            else:
                b = IconButton(icon, tip, bar, kind="icon")
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(slot)
            lay.addWidget(b)
            self._zoom_buttons.append(b)
        lay.addWidget(self._zoom_label)
        bar.adjustSize()
        self._zoom_bar = bar
        self._place_zoom_bar()

    def _place_zoom_bar(self) -> None:
        bar = getattr(self, "_zoom_bar", None)
        if bar is None:
            return
        bar.adjustSize()
        bar.move(8, max(0, self.viewport().height() - bar.height() - 8))
        bar.raise_()

    def _sync_zoom_label(self) -> None:
        label = getattr(self, "_zoom_label", None)
        if label is not None:
            label.setText("%d%%" % self.zoom_percent())

    def resizeEvent(self, e) -> None:          # noqa: D102 - Qt hook
        super().resizeEvent(e)
        self._place_zoom_bar()
        self._place_header()
        self._consume_pending_fit()

    # ---- 對外（與 PipelinePanel 對齊）--------------------------------------
    def forget_positions(self) -> None:
        """下一次 ``set_nodes`` 不要沿用現在的節點位置（換了一份 recipe 時用）。

        位置平常是**保留**的（見 set_nodes）—— 但那是「同一份 recipe 一直在
        編」的前提。換檔案之後，上一份剛好同名的節點（load_patch 幾乎每份都
        有）不該繼承拖過的位置。
        """
        self._keep_positions = False

    def set_nodes(self, nodes: Sequence[Dict[str, Any]],
                  edges: Sequence[Tuple[str, str]] = ()) -> None:
        """重建整張畫布。``nodes`` 依執行順序，``edges`` 是顯式連線。

        **既有節點的位置保留**（2026-08-14 使用者要求）：重建發生在每一次
        model 變動（改參數、開彈出視窗…），以前每次都重跑自動排版 ——
        使用者剛拖好的佈局在改一個參數之後就被「自動整理」掉。現在只有
        **新**節點拿排版位置；要整批排回去，按「排整齊」（tidy）。
        """
        prev = ({nid: item.pos() for nid, item in self._items.items()}
                if getattr(self, "_keep_positions", True) else {})
        self._keep_positions = True
        self._scene.clear()
        self._hover_node = None            # 舊的圖元剛被 clear() 銷毀
        self._items, self._edges = {}, []
        self._order = [str(n.get("node_id", "")) for n in nodes]
        # ``edges`` 收兩種形狀：``(來源, 目的)`` 與 ``(來源, 目的, 來源埠)``。
        # 帶埠的那種是 F9-9 —— 一對節點之間可以有好幾條線，每條各自從哪顆埠
        # 出發要由 model 講，不能再從「兩端共用哪幾條流」推（推出來的猜不出
        # 使用者只接了其中一條）。
        # 一條線是 ``(來源, 目的, 來源埠, 目的的輸入參數)``。第四欄是 F10 加的
        # —— 沒有它，兩條接進同一張卡不同輸入的線會疊在同一個點上，而「a 接了
        # 什麼、b 接了什麼」正是使用者要在畫布上讀到的東西。
        self._lines: List[Tuple[str, str, str, str]] = []
        for row in (edges or ()):
            row = tuple(str(x) for x in row)
            self._lines.append((row[0], row[1],
                                row[2] if len(row) > 2 else "",
                                row[3] if len(row) > 3 else ""))
        self._pairs = []
        for a, b, _o, _i in self._lines:
            if (a, b) not in self._pairs:
                self._pairs.append((a, b))

        # **排版**把相鄰的卡片排成一串。以前這裡寫的理由是「route 相鄰對是真的
        # 依賴（engine 的 execution_order 是『route 相鄰對 ∪ edges』）」——
        # **F17-① 之後那句話是假的**：執行順序的邊只來自 `edges`。
        #
        # 但這件事照做仍然是對的，理由換成一句更準的：**沒有線的卡片，執行順序
        # 就是 route 的排列**（那是 `execution_order` 裡 Kahn 的平手依據）。
        # 所以照排列由左往右擺，畫面上的先後跟真正跑的先後仍然一致。
        # 2026-08-14 起不畫成金色虛線（使用者：「會混淆」）—— 畫布上只畫使用者
        # 拉的線，排列本身就是那句話。
        #
        # ⚠ **「沒有線的卡片」那五個字要當真**（F56，2026-08-28）。這一行以前
        # 只問「這一對在不在 `_pairs` 裡」，而該問的是「**下游那張卡**有沒有
        # 真正的入線」—— 有線的話，它排在哪裡該由那條線決定，route 的排列在
        # 它身上沒有發言權。
        #
        # 代價是實際發生過的：一份 route 排成
        # `… → glv_stats → focus_quality → output_report`、而 `focus_quality`
        # 真正的來源是前面的 `denoise` 的 recipe，多出來的那條
        # `glv_stats → focus_quality` 把它推到深度 4；WRAP 是 4，於是它換行
        # 落回**第 0 欄** —— 也就是它來源的**左邊**。畫面上那條線因此由右往左
        # 畫，而在一張由左往右讀的畫布上，那讀起來是「它先跑」。
        # `docs/PITFALLS.md` 上「Region 卡排在量測卡右邊」那一條記的是同一種
        # 誤讀造成的真 bug。
        wired = {b for _a, b in self._pairs}
        self._implicit = [pair for pair in zip(self._order, self._order[1:])
                          if pair not in set(self._pairs) and pair[1] not in wired]

        self._laid_wrap = self.wrap()
        pos = layout_columns(self._order, self._pairs + self._implicit,
                             self._laid_wrap)
        fresh = [_NodeItem(info, self) for info in nodes]
        # **列距要容得下最高的那張卡**（F12）：埠多的卡片會長高，用固定的
        # ``NODE_H + ROW_GAP`` 排的話它會壓到下一列。
        # 列距**進位到格線上**（F79）：卡片的左上角因此落在點上，而欄距
        # （320 = 16 × 20）本來就是。卡片高度是變動的，所以這裡不能寫死。
        self._pitch = on_grid(max([it.height() for it in fresh] or [NODE_H])
                              + ROW_GAP)
        for item in fresh:
            if item.node_id in prev:
                item.setPos(prev[item.node_id])
            else:
                col, row = pos.get(item.node_id, (0, 0))
                item.setPos(col * (NODE_W + COL_GAP), row * self._pitch)
            self._scene.addItem(item)
            self._items[item.node_id] = item

        for a, b in self._pairs:
            if a not in self._items or b not in self._items:
                continue
            src, dst = self._items[a], self._items[b]
            outs = src.out_names()
            in_names = [str(d.get("name", "")) for d in dst.in_specs()]
            named = [(o, i) for (x, y, o, i) in self._lines
                     if (x, y) == (a, b) and o]
            if named:
                # 明講的線：一條就是一條，兩端各畫在**它自己那顆埠**上。
                ports = []
                for name, dst_in in named:
                    port = outs.index(name) if name in outs else 0
                    dp = in_names.index(dst_in) if dst_in in in_names else 0
                    if (port, dp) not in ports:
                        ports.append((port, dp))
            else:
                ports = [(port, 0) for port in self._ports_between(src, dst)]
            for port, dst_port in ports:
                edge = _EdgeItem(src, dst, self, port, dst_port)
                self._scene.addItem(edge)
                self._edges.append(edge)

        # 判定區（F24 ②）：scene 剛被 clear()，舊圖元已銷毀 —— 用存著的 info
        # 重建。它跟節點一起住在 scene 裡，所以平移縮放是同一件事。
        self._tree_items = []
        self._rebuild_decision()
        # 分流徽章（F25-B）同理：它站在所有卡片的**前面**。
        self._prefilter_items = []
        self._rebuild_prefilter()
        # Output 段那一塊（F30 Phase D）：它站在所有卡片的**後面**。

        self.set_selected(self._selected)
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(rect)

    # ---- 整批跑一次的那幾張卡（F50，原 F30 Phase D 的框）-------------------
    def lot_nodes(self) -> List[Any]:
        """哪幾張卡是**整批跑一次**的。

        判準是**卡片自己宣告的 `Step.scale`**，不是一份寫死的 key 清單，也
        不是 group ——「Output 段」與「整批跑一次」今天剛好是同一組卡，而那是
        巧合不是定義（`step.py` 的 `SCALE_LOT` 說明就寫著 Output 卡以前借用
        `CATEGORY_ADC` 只是因為那個值剛好讓它們落在快取 checkpoint 之後）。
        腳帶講的是時間，所以判準也要是時間。
        """
        return [it for it in self._items.values() if it.is_lot()]

    # ---- 判定區（F24 ②）---------------------------------------------------
    def set_decision(self, info: Optional[Dict[str, Any]]) -> None:
        """換掉判定區的內容（``None`` = 這份 recipe 走二元 score，沒有判定區）。

        info 的形狀見 `tree_scene.decision_info`。畫布只負責畫 ——
        counts 是不是 None（試跑過沒）由呼叫端決定，這裡不猜。
        """
        self._decision_info = None if info is None else dict(info)
        self._rebuild_decision()

    def _rebuild_decision(self) -> None:
        from . import tree_scene

        # 幽靈線指著即將被換掉的圖元 —— 先清（滑鼠移開的事件不一定會來）。
        self.clear_tree_ghosts()
        for it in getattr(self, "_tree_items", []) or []:
            try:
                self._scene.removeItem(it)
            except Exception:              # noqa: BLE001 — clear() 先銷毀過就算了
                pass
        self._tree_items = []
        info = getattr(self, "_decision_info", None)
        if not info:
            return
        # 判定區放在所有卡片的右邊（mockup 定稿：畫布右側一塊淡紫區），
        # 再加上使用者自己拖出來的位移（2026-08-25）。
        #
        # **位移是 session 狀態，不進 recipe** —— 跟卡片的位置一模一樣的待遇
        # （見模組 docstring）。所以拖它不會讓檔案變髒，也不必進復原堆疊，
        # 而 `tidy()` 會把它跟卡片一起排回去。
        right = 0.0
        top = 0.0
        for item in self._items.values():
            right = max(right, item.pos().x() + NODE_W)
            top = min(top, item.pos().y())
        off = getattr(self, "_tree_offset", None) or QPointF(0.0, 0.0)
        origin = QPointF(right + COL_GAP * 1.8 + off.x(), top + off.y())
        self._tree_items = tree_scene.build_zone(
            self._scene, self, info, origin,
            collapsed=bool(getattr(self, "_tree_collapsed", TREE_COLLAPSED_DEFAULT)),
            selected_path=getattr(self, "_tree_selected", None),
            highlight_path=getattr(self, "_tree_highlight", None))
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(self._scene.sceneRect().united(rect))

    def decision_items(self) -> List[Any]:
        """判定區現在的圖元（測試與外部檢查用）。"""
        return list(getattr(self, "_tree_items", []) or [])

    # ---- 拖整個判定區（2026-08-25）----------------------------------------
    def move_decision_by(self, dx: float, dy: float) -> None:
        """把整個判定區平移 ``(dx, dy)``。

        **就地搬每一個圖元，不重建**：重建會把滑鼠從把手上搶走（拖到一半突然
        失去控制比慢一點更難用 —— F26 在拖門檻時學到同一條）。累積的位移記在
        `_tree_offset`，下一次真的重建時 `_rebuild_decision` 會把它加回去。
        """
        off = getattr(self, "_tree_offset", None) or QPointF(0.0, 0.0)
        self._tree_offset = QPointF(off.x() + float(dx), off.y() + float(dy))
        for it in getattr(self, "_tree_items", []) or []:
            it.moveBy(float(dx), float(dy))
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(self._scene.sceneRect().united(rect))

    def decision_offset(self) -> QPointF:
        """使用者把判定區拖了多遠（測試用）。"""
        return QPointF(getattr(self, "_tree_offset", None) or QPointF(0.0, 0.0))

    def reset_decision_offset(self) -> None:
        """把判定區排回自動的位置（`tidy()` 會叫它）。"""
        self._tree_offset = QPointF(0.0, 0.0)
        self._rebuild_decision()

    # ---- 分流徽章（F25-B）-------------------------------------------------
    def set_prefilter(self, info: Optional[Dict[str, Any]]) -> None:
        """換掉分流徽章（``None`` = 這份 recipe 沒有分流，畫布上就沒有它）。

        形狀見 `route_badge.route_badge_info`。它**不是一張卡**（不可拖、
        沒有埠）—— 理由見那個模組的說明。
        """
        self._prefilter_info = None if info is None else dict(info)
        self._rebuild_prefilter()

    def _rebuild_prefilter(self) -> None:
        from . import route_badge

        for it in getattr(self, "_prefilter_items", []) or []:
            try:
                self._scene.removeItem(it)
            except Exception:          # noqa: BLE001 — clear() 先銷毀過就算了
                pass
        self._prefilter_items = []
        info = getattr(self, "_prefilter_info", None)
        if not info:
            return
        # 站在最左邊那張卡的**前面**（左→右讀起來就是時間順序：
        # 先分流、再跑卡片、最後判定）。
        left, top, feed = None, 0.0, None
        for item in self._items.values():
            x = item.pos().x()
            if left is None or x < left:
                left, top = x, item.pos().y()
                feed = QPointF(x, item.pos().y() + item.height() / 2.0)
        if left is None:
            left, top = 0.0, 0.0
        origin = QPointF(left - route_badge.BADGE_W - COL_GAP, top)
        self._prefilter_items = route_badge.build_badge(
            self._scene, self, info, origin, feed_to=feed)
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(self._scene.sceneRect().united(rect))

    def prefilter_items(self) -> List[Any]:
        """分流徽章現在的圖元（測試與外部檢查用）。"""
        return list(getattr(self, "_prefilter_items", []) or [])

    def set_tree_selected(self, path: Optional[str]) -> None:
        """畫布上亮起判定樹的某一步（右欄正在編它）。``None`` = 沒有。"""
        self._tree_selected = None if path is None else str(path)
        self._rebuild_decision()

    def tree_selected(self) -> Optional[str]:
        return getattr(self, "_tree_selected", None)

    def toggle_tree_collapsed(self) -> None:
        """雙擊入口卡＝收合／展開整棵樹（F24 §4）。

        收合是**這一份畫布的檢視狀態**，不進 recipe —— 跟縮放平移同一類。
        """
        self._tree_collapsed = not self.tree_collapsed()
        self._rebuild_decision()

    def tree_collapsed(self) -> bool:
        return bool(getattr(self, "_tree_collapsed", TREE_COLLAPSED_DEFAULT))

    def set_tree_highlight(self, path: Optional[str]) -> None:
        """亮起「現在預覽那一顆走過的路」（F24 §8）。``None`` = 清掉。"""
        new = None if path is None else str(path)
        if new == getattr(self, "_tree_highlight", None):
            return
        self._tree_highlight = new
        self._rebuild_decision()

    # ---- 幽靈線（F24 ④；F50 起卡片也有）------------------------------------
    def set_feature_owners(self, owners: Optional[Dict[str, str]]) -> None:
        """特徵名 → 產出它的節點 id（`RecipeModel.feature_owners`）。

        ⚠ **跟判定分開送。** 以前這張表只搭 `_decision_info` 的便車，而
        Output 卡沒有判定也照樣用名字吃數字 —— 搭便車的話「這份 recipe 沒有
        判定」就等於「淡線畫不出來」，而那兩件事不相干。
        """
        self._feature_owners = dict(owners or {})

    def show_card_ghosts(self, item: Any) -> None:
        """滑鼠停在一張卡上：**它用名字吃的那幾個數字**各亮一條線回來源卡。

        跟菱形的幽靈線是**同一支**（`tree_scene.ghost_wires`）與同一個手勢
        —— 使用者定調「不一致會有兩套準則」，而「判定看得到來源、Output
        看不到」正是兩套。

        ⚠ **它不是一條邊。** 不進 `recipe.edges`、不影響 `execution_order`、
        不進快取簽章、拉不動也剪不掉 —— 它是**視圖**：唯一的真相是那張卡的
        參數，這條線是它的投影。（F42 B4 拆掉的那條推導路是「兩份相加、每條
        線畫兩次」，不是這個形狀 —— 那裡有兩個出處，這裡只有一個。）
        """
        from . import tree_scene

        self.clear_tree_ghosts()
        names = [str(x) for x in (item.info.get("feature_reads") or [])]
        if not names:
            return
        target = item.pos() + QPointF(0.0, item.body_height() / 2.0)
        owners = dict(getattr(self, "_feature_owners", None) or {})
        self._ghost_items, self._ghost_cards = tree_scene.ghost_wires(
            self._scene, self, target, names, owners)

    def show_tree_ghosts(self, diamond: Any) -> None:
        """滑鼠停在一個菱形上：它用到的數字各自亮出來源卡＋一條臨時點線。"""
        from . import tree_scene

        self.clear_tree_ghosts()
        info = getattr(self, "_decision_info", None)
        if not info:
            return
        self._ghost_items, self._ghost_cards = tree_scene.build_ghosts(
            self._scene, self, diamond, dict(info.get("feat_owner") or {}))

    def clear_tree_ghosts(self) -> None:
        for it in getattr(self, "_ghost_items", []) or []:
            try:
                self._scene.removeItem(it)
            except Exception:              # noqa: BLE001 — clear() 先銷毀就算了
                pass
        for card in getattr(self, "_ghost_cards", []) or []:
            try:
                card.set_hovered(False)
            except Exception:              # noqa: BLE001
                pass
        self._ghost_items, self._ghost_cards = [], []

    def ghost_items(self) -> List[Any]:
        """現在畫著的幽靈線（測試用）。"""
        return list(getattr(self, "_ghost_items", []) or [])

    def copy_positions_from(self, other: "PipelineCanvas") -> None:
        """把另一份畫布的節點位置搬過來（彈出視窗開啟時跟主視窗一致）。"""
        for nid, item in other._items.items():
            mine = self._items.get(nid)
            if mine is not None:
                mine.setPos(item.pos())
        # **抄過來的位置不准被重排掉**（F13-1）：彈出視窗比主視窗寬，換行點
        # 因此不同，而第一次拿到真寬度時的那一次 `tidy()` 會把剛抄好的位置
        # 洗掉。``None`` = 「這份畫布的位置不是排出來的」。
        self._laid_wrap = None
        self.refresh_edges()

    def node_item(self, node_id: str):
        """畫布上那個節點（測試與外部檢查用；沒有回 ``None``）。"""
        return self._items.get(str(node_id))

    @staticmethod
    def _ports_between(src: "_NodeItem", dst: "_NodeItem") -> List[int]:
        """一條依賴要畫成幾條線 —— 依**兩端共用的影像流**決定。

        Input 節點吐 ``test`` 與 ``ref``；``subtract`` 兩張都讀，所以
        Input → Subtract 會畫**兩條**線，各自從對應的埠出發。
        這是推導出來的，不是存起來的 —— recipe JSON 的 edge 仍然是
        ``[from, to]`` 兩個 id，格式不用改，重新載入也不會掉資訊。

        兩端沒有共用的流（或下游沒宣告 reads）→ 退回單一條線。
        """
        outs = src.out_names()
        wanted = set(dst.in_names())
        ports = [i for i, name in enumerate(outs) if name in wanted]
        return ports or [0]

    def wrap(self) -> int:
        """這一份畫布一列排得下幾張卡（F13-1）。

        **問的是 viewport 不是 window**：捲軸與邊框都吃寬度，而少算的那幾 px
        正好是「多排一張卡」與「不多排」的分界。

        **還沒 show 過的畫布回 :data:`WRAP`**（既有行為），真正的排版在
        `fit_later` 那一輪重來。判準是「連一張卡都放不下」——一張卡連同它左右
        的埠標籤要 ``NODE_W + 2 * _PORT_LABEL_W``，比這還窄的不是一塊排版用的
        版面，是一個還沒被 layout 過的 widget（實測未 show 過是 89px）。
        把它當真的話，整份 recipe 會被排成一直條。
        """
        w = float(self.viewport().width())
        return WRAP if w < NODE_W + 2.0 * _PORT_LABEL_W else wrap_for_width(w)

    def node_ids(self) -> List[str]:
        return list(self._order)

    def edge_pairs(self) -> List[Tuple[str, str]]:
        return list(self._pairs)

    def set_selected(self, node_id: Optional[str]) -> None:
        self._selected = None if node_id is None else str(node_id)
        for nid, item in self._items.items():
            item.setSelected(nid == self._selected)
            item.update()

    # ---- 選中一張卡 → 它的線跟著講話（F78）--------------------------------
    def has_node_selection(self) -> bool:
        """現在有沒有選中任何一張卡（`_EdgeItem.focus_state` 問的就是這個）。

        問的是**卡片**不是 `scene().selectedItems()` —— 線自己也是可選的，
        而「選了一條線」不該讓其他所有線都黯下去。
        """
        return self._sel_nodes

    def _on_selection_changed(self) -> None:
        """選取一變就把所有線重畫一次。

        無條件重畫（而不是只在旗標翻轉時）：從卡 A 點到卡 B 的時候旗標兩次
        都是 True，但該亮的線整組換了一批。
        """
        self._sel_nodes = any(it.isSelected() for it in self._items.values())
        for edge in self._edges:
            edge.update()

    def selected_node(self) -> Optional[str]:
        return self._selected

    def selected(self) -> Optional[str]:
        """與舊 ``PipelinePanel.selected()`` 同名同義。"""
        return self._selected

    def card(self, node_id: str) -> Optional["_NodeItem"]:
        """取某個節點的圖元（highlight / 測試用；對應舊的 ``card()``）。"""
        return self._items.get(str(node_id))

    def set_score_summary(self, text: str) -> None:
        """判定段的一句話摘要（狀態列與測試讀得到）。

        ⚠ 以前這裡自己組 ``"score = … threshold …"`` —— 而 F25 之後**每一份
        開起來的 recipe 都是判定樹**，那句話會永遠是空的門檻。組字的責任因此
        搬去 Studio（它才知道現在是哪一種判定），這裡只收結果。
        """
        self._score_summary = str(text)

    def score_summary(self) -> str:
        return self._score_summary

    def score_summary_text(self) -> str:
        """與舊 ``PipelinePanel.score_summary_text()`` 同名同義。"""
        return self._score_summary

    #: ``fit()`` 最多縮到多小。還沒拉線的 recipe 會排成一條很長的橫列，
    #: 硬要全部塞進畫面會把節點縮成看不出字的小方塊 —— 那時候寧可留捲軸。
    #: ``fit`` 縮到這裡就停 —— **再小下去就不是「看得完」了**。
    #:
    #: 0.45 是憑感覺挑的，實際跑起來一份十張卡的 pipeline 落在 52%，那時候卡片
    #: 的**副標**（``norm_ref · ref test → ref``，也就是「這張卡吃什麼吐什麼」）
    #: 已經是一團灰。把同一張圖畫在 52 / 60 / 70 / 80 / 100% 逐級看過：標題到
    #: 60% 還讀得出來，副標要到 **70%** 才回來。
    #:
    #: 所以下限是 0.7。代價是很長的 pipeline 會超出畫面、要捲 —— 那是划算的：
    #: **讀不出來的全景不算全景**，而想看整體形狀的人本來就會再按一次縮小。
    #:
    #: D 案（2026-08-14）之後這是**類別預設**，不再是唯一的答案：主視窗的
    #: 畫布變成中上的一條**概覽**（副標的細節住在下方設定區與彈出視窗），
    #: 「全部看得完」比「副標讀得出」重要 —— Studio 把主畫布的這個值調成
    #: 0.5（見 _build_body），彈出視窗維持 0.7（它就是拿來讀的）。
    MIN_FIT_SCALE = 0.7

    # ---- 換視角要看得出「這兩張是同一份 pipeline」（F80）------------------
    def _view_state(self):
        """現在看的是哪裡 —— ``(縮放, 水平捲軸, 垂直捲軸)``。"""
        return (self.transform().m11(),
                self.horizontalScrollBar().value(),
                self.verticalScrollBar().value())

    def _set_view_state(self, state) -> None:
        from PySide6.QtGui import QTransform

        scale, hval, vval = state
        # 順序不能反：捲軸的**範圍**是從 transform 算出來的，先設值會被舊的範圍
        # 夾掉，而夾掉的那一下看起來就是「動畫結束時彈了一下」。
        self.setTransform(QTransform().scale(scale, scale))
        self.horizontalScrollBar().setValue(int(round(hval)))
        self.verticalScrollBar().setValue(int(round(vval)))
        self._sync_zoom_label()

    def _tween_view(self, apply_end) -> None:
        """把 ``apply_end()`` 造成的視角改變演成一小段動畫。

        **終點由 ``apply_end()`` 自己決定，這裡一個字都不算。** 做法是先讓它
        跳到終點、把終點量下來，再回到起點動畫過去 —— 所以不管 ``fit`` 的規則
        以後怎麼改（``MIN_FIT_SCALE``、只縮不放、靠開頭對齊…），動畫都不會跟
        它分家。自己算一份終點的話，那份會漂。
        """
        start = self._view_state()
        apply_end()
        end = self._view_state()
        anim = getattr(self, "_view_anim", None)
        if anim is not None:
            anim.stop()
            self._view_anim = None
        if not ANIMATE or not self.isVisible():
            return
        if (abs(end[0] - start[0]) < 1e-6
                and end[1] == start[1] and end[2] == start[2]):
            return                      # 沒動就不要演
        s0, s1 = start[0], end[0]
        if s0 <= 0 or s1 <= 0:
            return

        def step(t: float) -> None:
            # 縮放用**幾何**內插：50% → 200% 的中點是 100%，不是 125%。
            # 線性內插在放大時會前段太慢、後段暴衝。
            scale = s0 * (s1 / s0) ** float(t)
            self._set_view_state((scale,
                                  start[1] + (end[1] - start[1]) * t,
                                  start[2] + (end[2] - start[2]) * t))

        anim = QVariantAnimation(self)
        anim.setDuration(ANIM_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v: step(float(v)))
        # 終點**照抄量到的那一組**，不靠動畫的最後一格算出來 —— 內插誤差與
        # 捲軸夾值都會讓最後一格差個一兩 px，而那一兩 px 是會累積的。
        anim.finished.connect(lambda: self._set_view_state(end))
        self._view_anim = anim
        step(0.0)                       # 先回到起點
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    def fit(self) -> None:
        """整張圖縮放到看得完（但不縮到看不懂、也不放大）。"""
        rect = self._scene.itemsBoundingRect()
        if not rect.isValid():
            return
        self._tween_view(lambda: self._fit_now(rect))

    def _fit_now(self, rect: QRectF) -> None:
        self.fitInView(rect.adjusted(-30, -30, 30, 30), Qt.KeepAspectRatio)
        s = self.transform().m11()
        if 0 < s < self.MIN_FIT_SCALE:
            self.scale(self.MIN_FIT_SCALE / s, self.MIN_FIT_SCALE / s)
        elif s > 1.0:
            # **fit 只會縮，不會放。** 一條只有兩張卡的 pipeline 塞得進畫布，
            # 這時候 ``fitInView`` 會把它放大到三倍去填滿版面 —— 卡片變成巨無霸，
            # 而使用者按的是「全部看得完」不是「放到最大」。
            self.scale(1.0 / s, 1.0 / s)
        self._anchor_start(rect)
        self._sync_zoom_label()

    def _anchor_start(self, rect: QRectF) -> None:
        """塞不下的時候，靠**開頭**對齊，不要置中。

        撞到 ``MIN_FIT_SCALE`` 之後內容一定比畫面寬，而 ``fitInView`` 是置中的
        —— 於是兩端各被切掉一半，第一張卡（``Load images``）跟最後一張同時看
        不見。**pipeline 是從左往右讀的**，看不完的時候該看到的是開頭：
        使用者要嘛從那裡接下去，要嘛往右捲。上下同理。
        """
        view = self.mapToScene(self.viewport().rect()).boundingRect()
        if view.width() < rect.width():
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().minimum())
        if view.height() < rect.height():
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().minimum())

    def fit_later(self) -> None:
        """等畫布真的有尺寸了再 fit 一次。

        ``fitInView`` 算的是「要縮多少才塞得進 viewport」，而 viewport 在
        ``show()`` 之前是一個預設值 —— 在那個時間點 fit，算出來的倍率會直接
        留在畫面上，使用者看到的是一個對不上自己視窗的縮放。
        """
        self._fit_pending = True
        self._consume_pending_fit()

    def _consume_pending_fit(self) -> None:
        if getattr(self, "_fit_pending", False) and self.viewport().width() > 80:
            self._fit_pending = False
            # **第一次拿到真的寬度**：排版當時用的換行點是猜的（畫布還沒 show，
            # viewport 是一個預設值），現在才知道一列真的排得下幾張。不重排的話
            # 一份剛開的 recipe 會照著「假設有 1050px」排好，然後被 `fit` 縮到
            # 讀不出字 —— 那正是 F13-1 要修的那個畫面。
            #
            # **只在這一刻**：`fit_later` 是「整份換掉／剛開窗」才呼叫的，
            # 所以使用者自己拖好的佈局不會被重排（那條規矩是 2026-08-14 定的）。
            if getattr(self, "_laid_wrap", None) not in (None, self.wrap()):
                self.tidy()
            self.fit()

    def showEvent(self, e) -> None:            # noqa: D102 - Qt hook
        super().showEvent(e)
        self._consume_pending_fit()

    # ---- 從卡片庫拖進來（F7-22）-------------------------------------------
    def dragEnterEvent(self, e) -> None:            # noqa: D102 - Qt hook
        if e.mimeData().hasFormat(CARD_MIME):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e) -> None:             # noqa: D102 - Qt hook
        if e.mimeData().hasFormat(CARD_MIME):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e) -> None:                 # noqa: D102 - Qt hook
        if not e.mimeData().hasFormat(CARD_MIME):
            return super().dropEvent(e)
        key = bytes(e.mimeData().data(CARD_MIME)).decode("utf-8")
        # 落點：**滑鼠放開的地方**（場景座標），這正是拖曳相對於「Add」的差別。
        # 位置不寫進 recipe（見模組 docstring），所以它只影響現在看到的畫面 ——
        # 重新載入會回到自動排版，那是既有的行為，這裡不改。
        pos = self.mapToScene(e.position().toPoint()
                              if hasattr(e, "position") else e.pos())
        self.card_dropped.emit(str(key), float(pos.x()), float(pos.y()))
        e.acceptProposedAction()

    def place_dropped(self, node_id: str, x: float, y: float) -> bool:
        """把剛加進來的節點移到落點（Studio 加完卡之後回頭呼叫）。"""
        item = self._items.get(str(node_id))
        if item is None:
            return False
        item.setPos(float(x) - NODE_W / 2.0, float(y) - item.height() / 2.0)
        self.refresh_edges()
        return True

    def tidy(self) -> None:
        """把節點重新排回自動排版的位置（F7-22）。

        節點是拖得動的，而拖過之後就只能自己一個個搬回去 —— 這在 n8n 是一顆
        「Tidy up」。排版本來就有（:func:`layout_columns`，每次重建畫布都在用），
        所以這裡只是**把它再套一次**，不是新的排版邏輯。

        位置不寫進 recipe（見模組 docstring），所以這個動作不會讓檔案變髒，
        也就不需要進復原堆疊。
        """
        self._laid_wrap = self.wrap()
        pos = layout_columns(self._order, self._pairs + self._implicit,
                             self._laid_wrap)
        pitch = getattr(self, "_pitch", on_grid(NODE_H + ROW_GAP))
        moves = {}
        for nid, item in self._items.items():
            col, row = pos.get(nid, (0, 0))
            moves[nid] = (item.pos(),
                          QPointF(col * (NODE_W + COL_GAP), row * pitch))
            item.setPos(moves[nid][1])
        # 判定區也是「拖得動的東西」，所以 Tidy up 也要把它排回去 ——
        # 只排一半的整理，下一次還是得自己搬。
        self._tree_offset = QPointF(0.0, 0.0)
        self._rebuild_decision()
        self.refresh_edges()
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(rect)
        self._tween_nodes(moves)

    def _tween_nodes(self, moves) -> None:
        """讓卡片**滑**到新位置，而不是瞬間出現在那裡（F80）。

        排整齊會同時搬動每一張卡。瞬間跳的話，使用者要重新認一次哪張是哪張
        —— 而他按這顆鈕的理由通常是「我拖亂了」，也就是他心裡還有一份舊的
        位置圖。看得到每張卡從哪裡去到哪裡，那份圖才接得上。

        ``moves`` 是 ``{node_id: (起點, 終點)}``，而**終點已經設好了** ——
        跟 :meth:`_tween_view` 同一個做法：先到終點、再回頭演。動畫被打斷
        （再按一次、或畫布重建）時停在哪裡都無所謂，因為 model 那一邊早就是
        終點了。
        """
        anim = getattr(self, "_node_anim", None)
        if anim is not None:
            anim.stop()
            self._node_anim = None
        if not ANIMATE or not self.isVisible():
            return
        live = {nid: (a, b) for nid, (a, b) in moves.items()
                if (a - b).manhattanLength() > 0.5}
        if not live:
            return                      # 本來就整齊，不用演

        def step(t: float) -> None:
            for nid, (a, b) in live.items():
                item = self._items.get(nid)
                if item is not None:
                    item.setPos(a + (b - a) * float(t))

        anim = QVariantAnimation(self)
        anim.setDuration(ANIM_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v: step(float(v)))
        anim.finished.connect(lambda: step(1.0))
        self._node_anim = anim
        step(0.0)
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    def refresh_edges(self) -> None:
        for e in self._edges:
            e.prepareGeometryChange()
            e.update()
        # ⚠ **這裡以前還有一句 `self._rebuild_output_band()`**（F30）——
        # Output 段那個框從卡片位置算出來，所以卡片一動就得整個重算。它因此
        # 在**每一個拖曳 frame** 銷毀重建一次，而畫布用 Qt 預設的
        # `MinimalViewportUpdate`：抗鋸齒的虛線每 frame 溢出 boundingRect
        # 一點點，累積起來就是使用者回報的殘影。F50 把那件事改成卡片自己的
        # 一條腳帶（`_NodeItem._paint_lot_strip`），跟著卡片走，不用重算。
        # 卡片拖到 sceneRect 外面，那一塊是**捲不到的** —— 埠與標籤就這樣
        # 「不見」（使用者回報的）。所以 sceneRect 跟著拖曳長大（只長不縮：
        # 拖曳中一直重算縮小的話畫面會跳；縮回來由 set_nodes / tidy 做）。
        grown = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(self._scene.sceneRect().united(grown))

    # ---- 拉線 -------------------------------------------------------------
    def begin_link(self, src: _NodeItem, port: int = 0) -> None:
        self._link_from = src
        self._link_port = int(port)
        self._link_line = self._scene.addPath(
            QPainterPath(src.out_port(port)),
            QPen(QColor(TOKENS["canvas_edge_active"]), 1.6, Qt.DashLine))
        self._repaint_ports()   # 接得上的埠要亮起來（F68）

    def _repaint_ports(self) -> None:
        """每一張卡重畫一次埠 —— 拖線**開始與結束**時各一次。

        只在這兩個時刻重畫（不是每次滑鼠移動），因為亮不亮只跟「現在拖的是
        哪一種線」有關，跟游標在哪裡無關。
        """
        for item in self._scene.items():
            if isinstance(item, _NodeItem):
                item.update()

    def _drop_link(self, scene_pos: QPointF) -> None:
        src, self._link_from = self._link_from, None
        self._repaint_ports()                       # 亮起來的埠要熄掉（F68）
        port = int(getattr(self, "_link_port", 0))
        if self._link_line is not None:
            self._scene.removeItem(self._link_line)
            self._link_line = None
        if src is None:
            return
        for item in self._scene.items(scene_pos):
            if isinstance(item, _NodeItem) and item is not src:
                self.edge_added.emit(
                    src.node_id, item.node_id, self.stream_of(src, port),
                    item.in_param_at(item.mapFromScene(scene_pos)))
                return

    @staticmethod
    def stream_of(src: "_NodeItem", port: int) -> str:
        """``src`` 的第 ``port`` 個輸出埠吐的影像流名（沒有名字回空字串）。"""
        names = src.out_names()
        if 0 <= port < len(names):
            return str(names[port] or "")
        return ""

    def link_to(self, src_id: str, dst_id: str, port: int = 0,
                dst_port: int = 0) -> None:
        """程式化拉一條線（測試用；等同使用者從第 ``port`` 個輸出埠拖過去）。

        ``dst_port`` 是落在下游的第幾顆**輸入**埠（F10）——
        ``subtract`` 的 a 與 b 是兩顆不同的埠，接哪一顆是使用者的決定。
        """
        src = self._items.get(str(src_id))
        dst = self._items.get(str(dst_id))
        if src is not None and dst is not None:
            specs = dst.in_specs()
            i = max(0, min(int(dst_port), len(specs) - 1)) if specs else 0
            self.edge_added.emit(
                str(src_id), str(dst_id), self.stream_of(src, int(port)),
                str(specs[i].get("name", "")) if specs else "")

    def _port_tip_at(self, view_pos) -> str:
        """游標下那顆**區域埠**（菱形）的一句話（不在埠上／影像埠回 ``""``）。

        字典住在 `region_words`（跟 GLV 面板標題、Profile 圖例同一份）。
        掛在 view 而不是節點上：`_NodeItem` 故意不收 hover 事件（收了會把
        邊的 × 鈕吃掉，`test_ui_canvas_cut_button` 守著），而 view 的
        mouse-move 本來就在追 hover（`_sync_hover_node`）。純函式好測 ——
        測試打這一支，不必真的擠出一顆 QToolTip。
        """
        top = None
        for item in self.items(view_pos):
            if isinstance(item, _NodeItem):
                top = item
                break
        if top is None:
            return ""
        local = top.mapFromScene(self.mapToScene(view_pos))

        def tip(name: str) -> str:
            name = str(name or "")
            if not name:
                return ""
            return "%s — %s" % (
                name, region_words.PORT_HOVER[region_words.role_of(name)])

        i = top.out_port_at(local)
        if i is not None:
            specs = top.out_specs()
            if 0 <= i < len(specs) and specs[i].get("kind") == "region":
                return tip(specs[i].get("name"))
            return ""
        i = top.in_port_at(local)
        if i is not None:
            specs = top.in_specs()
            if 0 <= i < len(specs) and specs[i].get("kind") == "region":
                # 輸入埠講**接進來的那個名字**（有線才有名字；沒接就沒話講）。
                return tip(specs[i].get("stream"))
        return ""

    # ---- Qt hooks ---------------------------------------------------------
    def _sync_hover_node(self, view_pos) -> None:
        """讓游標下最上面那張卡亮起 hover 邊框。"""
        top = None
        for item in self.items(view_pos):
            if isinstance(item, _NodeItem):
                top = item
                break
        if top is not self._hover_node:
            if self._hover_node is not None:
                self._hover_node.set_hovered(False)
            self._hover_node = top
            # 幽靈線跟著 hover 走（F50）—— 跟菱形同一個手勢。
            # ⚠ 清在設定之前：`show_card_ghosts` 會把來源卡設成 hovered，
            # 而那幾張卡不是 `_hover_node`，所以上面那一行清不到它們。
            self.clear_tree_ghosts()
            if top is not None:
                top.set_hovered(True)
                self.show_card_ghosts(top)

    def leaveEvent(self, e) -> None:           # noqa: D102
        if self._hover_node is not None:
            self._hover_node.set_hovered(False)
            self._hover_node = None
        self.clear_tree_ghosts()
        super().leaveEvent(e)

    @staticmethod
    def _view_pos(e):
        # ``QMouseEvent.pos()`` 在 Qt6 是 deprecated（CI 的警告）。
        return e.position().toPoint() if hasattr(e, "position") else e.pos()

    def mousePressEvent(self, e) -> None:      # noqa: D102
        # 右鍵按住拖曳 = 平移畫布（使用者要求）。原地放開仍然要出得來
        # 節點的右鍵選單 —— 那條路移到 mouseReleaseEvent。
        if e.button() == Qt.RightButton:
            self._pan_last = self._view_pos(e)
            self._pan_moved = False
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:       # noqa: D102
        if self._pan_last is not None and (e.buttons() & Qt.RightButton):
            pos = self._view_pos(e)
            d = pos - self._pan_last
            if d.manhattanLength() > 2:
                self._pan_moved = True
            self._pan_last = pos
            h, v = self.horizontalScrollBar(), self.verticalScrollBar()
            h.setValue(h.value() - d.x())
            v.setValue(v.value() - d.y())
            e.accept()
            return
        self._sync_hover_node(self._view_pos(e))
        # 區域埠的一句話（PR-2）：只在真的落在菱形上時出現，離開就收 ——
        # 一顆黏著不走的 tooltip 比沒有 tooltip 更煩。
        port_tip = self._port_tip_at(self._view_pos(e))
        if port_tip:
            at = (e.globalPosition().toPoint()
                  if hasattr(e, "globalPosition") else e.globalPos())
            QToolTip.showText(at, port_tip, self)
            self._port_tip_shown = True
        elif getattr(self, "_port_tip_shown", False):
            QToolTip.hideText()
            self._port_tip_shown = False
        if self._link_from is not None and self._link_line is not None:
            a = self._link_from.out_port(getattr(self, "_link_port", 0))
            b = self.mapToScene(self._view_pos(e))
            dx = max(40.0, abs(b.x() - a.x()) * 0.5)
            path = QPainterPath(a)
            path.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
            self._link_line.setPath(path)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:    # noqa: D102
        if e.button() == Qt.RightButton and self._pan_last is not None:
            moved, self._pan_moved = self._pan_moved, False
            self._pan_last = None
            if not moved:
                # 原地放開 = 右鍵選單（拖了就是平移，不出選單）。
                for item in self.items(self._view_pos(e)):
                    if isinstance(item, _NodeItem):
                        gp = (e.globalPosition().toPoint()
                              if hasattr(e, "globalPosition") else e.globalPos())
                        item.show_context_menu(gp)
                        break
            e.accept()
            return
        if self._link_from is not None:
            self._drop_link(self.mapToScene(self._view_pos(e)))
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e) -> None:     # noqa: D102
        # 右鍵被平移接管。不吞掉的話，Linux 在**按下的瞬間**就彈選單，
        # 平移永遠拖不起來；選單改在「原地放開」時開（見 mouseReleaseEvent）。
        e.accept()

    def keyPressEvent(self, e) -> None:        # noqa: D102
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in list(self._scene.selectedItems()):
                if isinstance(item, _EdgeItem):
                    a, b = item.pair()
                    self.edge_removed.emit(a, b, item.out_name(),
                                           item.dst_name())
                elif isinstance(item, _NodeItem):
                    self.remove_requested.emit(item.node_id)
            e.accept()
            return
        super().keyPressEvent(e)

    #: 縮放範圍。沒有下限的話滾兩下就把整張圖縮成一個點，而且**看不出自己在
    #: 哪裡**（背景是點陣，縮小之後每一格都長得一樣）；沒有上限則會滾進一片
    #: 純色裡。兩種都只能靠「fit」把自己救回來，而在這之前使用者不知道有這顆鈕。
    MIN_SCALE, MAX_SCALE = 0.25, 3.0

    def zoom_percent(self) -> int:
        return int(round(self.transform().m11() * 100))

    def zoom_by(self, factor: float) -> None:
        """縮放，並夾在 MIN_SCALE / MAX_SCALE 之間。"""
        s = self.transform().m11()
        target = max(self.MIN_SCALE, min(self.MAX_SCALE, s * float(factor)))
        if abs(target - s) > 1e-9:
            self.scale(target / s, target / s)
        self._sync_zoom_label()

    def reset_zoom(self) -> None:
        """回到 100%（`fit` 之後想看清楚字的時候要的就是這個）。"""
        def _now():
            self.resetTransform()
            self._sync_zoom_label()

        self._tween_view(_now)

    def wheelEvent(self, e) -> None:           # noqa: D102
        self.zoom_by(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
        e.accept()

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:  # noqa: D102
        """點陣底，不是格線底（F7-8）。

        格線會在整張畫布上鋪滿橫豎線，跟連線同一種筆觸，於是「哪條是資料流、
        哪條是背景」要看第二眼才分得出來。點只提供對齊的參考，不會跟線搶。

        ⚠ **間距住在模組層的 :data:`GRID`，不是這裡的一個私有常數**（F79）——
        排版與拖曳的吸附都讀同一個值。它以前是這個類別自己的 22，於是「背景
        說的對齊」與「版面做的對齊」是兩套，而點陣底因此對不齊任何東西。
        """
        p.fillRect(rect, QColor(TOKENS["canvas_bg"]))
        step = GRID
        # 縮太小的時候點會糊成一片灰 —— 那時候乾脆不畫
        if self.transform().m11() < 0.45:
            return
        p.setPen(QPen(QColor(TOKENS["canvas_grid"]), 1.6, Qt.SolidLine,
                      Qt.RoundCap))
        x0 = rect.left() - (rect.left() % step)
        y0 = rect.top() - (rect.top() % step)
        y = y0
        while y < rect.bottom():
            x = x0
            while x < rect.right():
                p.drawPoint(QPointF(x, y))
                x += step
            y += step
