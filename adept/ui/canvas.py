# ADEPT Studio 節點畫布 — authored 2026-07-28 (F7-6).
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

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
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
    QWidget,
)

from . import theme
from .theme import TOKENS
from .widgets import CARD_MIME, IconButton, draw_group_icon, small_button

__all__ = ["PipelineCanvas", "NODE_W", "NODE_H", "COL_GAP", "ROW_GAP"]

#: 一個節點最多畫幾個輸出埠（再多就擠不下，退回單一埠）。
_MAX_PORTS = 4

#: 埠標籤佔的寬度（畫在節點右緣之外，boundingRect 必須算進去）。
_PORT_LABEL_W = 52.0

#: 節點左側 icon 的邊長，以及裝著它的圓角色塊。
#: 用**色塊**而不是細色條（F7-8）：n8n 的節點一眼認得出來，靠的就是左邊那顆
#: 有顏色的圖示磚。細條太安靜，遠看整張畫布還是一排一模一樣的方框。
_ICON = 18.0
_TILE = 32.0

#: 節點卡尺寸與排版間距（畫布座標）。
NODE_W, NODE_H = 190.0, 56.0
COL_GAP, ROW_GAP = 96.0, 26.0
_PORT_R = 5.0
#: 埠的**命中**半徑（比畫出來的圓點大 —— 5px 的點用滑鼠瞄很痛苦）。
#: ``out_port_at`` 與 ``_NodeItem.shape`` 都讀它：命中範圍只能有一個定義，
#: 分成兩份遲早會對不起來，而「對不起來」的症狀是「點了沒反應」。
_PORT_GRAB = _PORT_R * 3.0

#: 連線中點的方向箭頭大小。畫布可以縮放平移，光看曲線不一定分得出資料往哪流。
_ARROW = 5.0
#: 線上那顆「斷開」× 的半徑（F7-22）。
_CUT_R = 8.0

#: 連線的 z 值。節點是 0，所以線平常畫在卡片**底下**（n8n 也是這樣，
#: 卡片才是主角）；滑鼠移上來的那一條抬到卡片之上 —— 見 ``hoverEnterEvent``。
_Z_EDGE, _Z_EDGE_HOVER = -1.0, 1.0

#: 還沒拉線時，一列最多排幾張卡（見 :func:`layout_columns`）。
WRAP = 4


def layout_columns(node_ids: Sequence[str],
                   edges: Sequence[Tuple[str, str]]) -> Dict[str, Tuple[int, int]]:
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
    ids = [str(n) for n in node_ids]
    idx = {n: i for i, n in enumerate(ids)}
    preds: Dict[str, List[str]] = {n: [] for n in ids}
    for a, b in edges:
        if a in idx and b in idx:
            preds[b].append(a)

    if not any(preds[n] for n in ids):
        return {n: (i % WRAP, i // WRAP) for i, n in enumerate(ids)}

    depth: Dict[str, int] = {}
    for n in ids:                       # ids 已是拓撲順序，一遍就夠
        depth[n] = max((depth.get(p, 0) + 1 for p in preds[n]), default=0)

    # 一「帶」= 換行之前的 WRAP 個深度。帶高取「最擠的那個深度有幾個節點」，
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
        band, col = divmod(d, WRAP)
        for r, n in enumerate(members):
            rows_of[n] = r
            out[n] = (col, band * band_h + r)
    return out


def _draw_elided(p: QPainter, rect: QRectF, text: str) -> None:
    """畫一行文字，太長就切成 ``像這樣…``。

    直接 ``drawText`` 到一個放不下的矩形，Qt 會**硬切在字的中間**，看起來像
    畫面壞掉；``參數摘要=diff · metri`` 這種殘句還會讓人以為值真的是那樣。
    """
    s = str(text)
    fm = p.fontMetrics()
    if fm.horizontalAdvance(s) > rect.width():
        s = fm.elidedText(s, Qt.ElideRight, int(rect.width()))
    p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, s)


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
        tip = "%s — %s" % (self.node_id, info.get("label", ""))
        if info.get("problem"):
            # 標記說「有問題」，滑鼠停上去說「是什麼問題」。標記本身放不下一句話，
            # 而「有一個紅點但不知道為什麼」比沒有標記更讓人焦慮。
            tip += "\n\n⚠ %s" % info["problem"]
        self.setToolTip(tip)

    # -- 幾何 ---------------------------------------------------------------
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
                      right - left, NODE_H + 2.0 * (_PORT_GRAB + 1.0))

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
        p.addRoundedRect(QRectF(0.0, -1.0, NODE_W, NODE_H + 2.0), 7, 7)
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
        """這張卡的輸入格：``[{"name","label","stream"}, …]``（由 Studio 給）。"""
        return [dict(d) for d in (self.info.get("inputs") or [])]

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
        if n == 1:
            return [QPointF(0.0, NODE_H / 2.0)]
        step = NODE_H / (n + 1)
        return [QPointF(0.0, step * (i + 1)) for i in range(n)]

    def in_anchors(self) -> List[QPointF]:
        base = self.scenePos()
        return [base + p for p in self.in_anchors_local()]

    #: 沒有輸入的卡（Input）**不畫**埠，但幾何上仍然要答得出一個點：
    #: 連線的貝茲曲線、`shape()`、測試都會問。左緣正中央。
    _NO_INPUT_ANCHOR = QPointF(0.0, NODE_H / 2.0)

    def in_port(self, index: int = 0) -> QPointF:
        anchors = self.in_anchors()
        if not anchors:
            return self.scenePos() + self._NO_INPUT_ANCHOR
        return anchors[max(0, min(int(index), len(anchors) - 1))]

    def in_port_local(self) -> QPointF:
        anchors = self.in_anchors_local()
        return anchors[0] if anchors else QPointF(self._NO_INPUT_ANCHOR)

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
        names = [str(w) for w in (self.info.get("writes") or [])]
        return names[:_MAX_PORTS]

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
        if n == 1:
            return [QPointF(NODE_W, NODE_H / 2.0)]
        step = NODE_H / (n + 1)
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
            return self.scenePos() + QPointF(NODE_W, NODE_H / 2.0)
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
    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        enabled = bool(self.info.get("enabled", True))
        selected = self.isSelected()
        body = QRectF(0, 0, NODE_W, NODE_H)

        p.setRenderHint(QPainter.Antialiasing, True)

        # 投影：讓節點浮在網格之上。用畫的而不是 QGraphicsDropShadowEffect ——
        # effect 會強迫 Qt 額外開一層離屏 buffer，為了 2px 的陰影不值得。
        # hover / 選中時深一階：跟按鈕的 hover 同一個語言 ——「這個東西回應你」。
        lifted = (self._hover or selected) and enabled
        shadow = QColor(0, 0, 0, (64 if lifted else 46) if enabled else 22)
        p.setPen(Qt.NoPen)
        p.setBrush(shadow)
        p.drawRoundedRect(body.translated(1.5, 2.5 if not lifted else 3.0), 7, 7)

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
            p.drawRoundedRect(body, 7, 7)

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
        p.drawRoundedRect(body, 7, 7)

        # 左邊的圖示磚：淡色底 + 與左側 rail 完全相同的圖形（F7-8）。
        tile = QRectF(8, (NODE_H - _TILE) / 2.0, _TILE, _TILE)
        wash = QColor(tile_col)
        wash.setAlpha(46 if enabled else 24)
        p.setPen(QPen(tile_col if enabled else QColor(TOKENS["border_default"]), 1.0))
        p.setBrush(wash)
        p.drawRoundedRect(tile, 6, 6)

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
        _draw_elided(p, QRectF(text_x, 9, text_w, 15),
                     str(self.info.get("label", self.node_id)))
        f.setBold(False)
        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        p.setPen(QColor(TOKENS["text_secondary"] if enabled else TOKENS["text_disabled"]))
        _draw_elided(p, QRectF(text_x, 24, text_w, 13), self.subtitle())
        parts = self.summary_parts()
        if parts:
            _draw_parts(p, QRectF(text_x, 36, text_w, 13), parts)

        # 連接埠（**本地座標** —— 見 out_anchors_local 的說明）。
        # 輸入是空心圈、輸出是實心點：一眼看得出線該從哪邊拉到哪邊。
        p.setPen(QPen(QColor(TOKENS["canvas_edge"]), 1.2))
        p.setBrush(QBrush(QColor(TOKENS["bg_surface"])))
        ins = self.in_specs()
        in_anchors = self.in_anchors_local()
        for i, anchor in enumerate(in_anchors):
            p.drawEllipse(anchor, _PORT_R, _PORT_R)
            if len(ins) < 2 or i >= len(ins):
                continue
            # 兩個以上的輸入才標名字：一顆埠的時候「這條線接到哪」沒有歧義，
            # 標了只是多一個字；兩顆以上不標的話，使用者要去猜上面那顆是
            # `First stream` 還是 `Second stream` —— 而猜錯了畫面上完全看不
            # 出來（兩張圖相減，a 與 b 反過來就是整張圖的正負號反過來）。
            spec = ins[i]
            text = str(spec.get("stream") or spec.get("label") or "")
            if not text:
                continue
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(
                QRectF(anchor.x() - _PORT_LABEL_W - 4, anchor.y() - 7,
                       _PORT_LABEL_W, 14),
                Qt.AlignVCenter | Qt.AlignRight, text)
            p.setPen(QPen(QColor(TOKENS["canvas_edge"]), 1.2))
            p.setBrush(QBrush(QColor(TOKENS["bg_surface"])))

        outs = self.out_names()
        p.setBrush(QBrush(QColor(TOKENS["canvas_edge"])))
        for name, anchor in zip(outs, self.out_anchors_local()):
            p.drawEllipse(anchor, _PORT_R, _PORT_R)
            if not name:
                continue
            # 每個輸出埠都標上它吐的影像流名（F7-9）。以前只有多埠才標，
            # 於是「這張卡到底做在哪一條流上」在畫布上是看不到的 ——
            # 而 Enhance 卡的 target / also apply 講的正是這些名字。
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(anchor.x() + 4, anchor.y() - 7, _PORT_LABEL_W - 10, 14),
                       Qt.AlignVCenter | Qt.AlignLeft, name)
            p.setPen(QPen(QColor(TOKENS["canvas_edge"]), 1.2))

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
        regions = [r for r in (self.info.get("regions_out") or []) if r]
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
        """右上角一個小圓標。錯誤紅、警告琥珀。

        文字用 ``!`` 而不是圖形：這個標記只有 14 px，任何再細一點的形狀在
        100% 縮放下都會糊成一個點。
        """
        why = self.problem()
        if not why:
            return
        level = str(self.info.get("problem_level", "error"))
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
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: D102 - Qt hook
        """雙擊 = 打開這張卡的設定（F7-22，n8n 的動作）。

        參數面板平常是收起來的，畫布因此吃得到整欄。單擊仍然只是選取
        （右邊的預覽會跟著跑到這張卡為止），雙擊才把設定攤開。
        """
        self.canvas.node_selected.emit(self.node_id)
        self.canvas.node_activated.emit(self.node_id)
        e.accept()

    def itemChange(self, change, value):        # noqa: D102 - Qt hook
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.canvas.refresh_edges()
        return super().itemChange(change, value)

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
    引擎的依賴仍然是「route 相鄰對 ∪ 顯式 edges」（那沒有變，變的只有
    畫不畫），排版也仍然吃隱含順序（``set_nodes`` 的 ``self._implicit``）。
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
        self.setToolTip("%s → %s  (click the × to disconnect)"
                        % (src.node_id, dst.node_id))

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

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(TOKENS["canvas_edge_active"] if self.isSelected()
                     else TOKENS["canvas_edge"])
        path = self.path()
        p.setPen(QPen(col, 2.2 if self.isSelected() else 1.6))
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

    def __init__(self, parent=None, popout_button: bool = True):
        super().__init__(parent)
        #: 彈出視窗裡的那份畫布把這顆鈕關掉 —— 從彈出視窗再彈一個視窗，
        #: 沒有那種需求，只有無限套娃。
        self._popout_button = bool(popout_button)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
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

        # route 的相鄰對是**真的依賴**（engine 的 execution_order 是
        # 「route 相鄰對 ∪ edges」），**排版**照樣把它算進去 —— 但 2026-08-14
        # 起不再畫成金色虛線（使用者：「會混淆」）。畫布上只畫使用者拉的線；
        # 順序上的依賴由卡片的排列（左→右、上→下）表達。
        self._implicit = [pair for pair in zip(self._order, self._order[1:])
                          if pair not in set(self._pairs)]

        pos = layout_columns(self._order, self._pairs + self._implicit)
        for info in nodes:
            item = _NodeItem(info, self)
            if item.node_id in prev:
                item.setPos(prev[item.node_id])
            else:
                col, row = pos.get(item.node_id, (0, 0))
                item.setPos(col * (NODE_W + COL_GAP), row * (NODE_H + ROW_GAP))
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

        self.set_selected(self._selected)
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(rect)

    def copy_positions_from(self, other: "PipelineCanvas") -> None:
        """把另一份畫布的節點位置搬過來（彈出視窗開啟時跟主視窗一致）。"""
        for nid, item in other._items.items():
            mine = self._items.get(nid)
            if mine is not None:
                mine.setPos(item.pos())
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

    def node_ids(self) -> List[str]:
        return list(self._order)

    def edge_pairs(self) -> List[Tuple[str, str]]:
        return list(self._pairs)

    def set_selected(self, node_id: Optional[str]) -> None:
        self._selected = None if node_id is None else str(node_id)
        for nid, item in self._items.items():
            item.setSelected(nid == self._selected)
            item.update()

    def selected_node(self) -> Optional[str]:
        return self._selected

    def selected(self) -> Optional[str]:
        """與舊 ``PipelinePanel.selected()`` 同名同義。"""
        return self._selected

    def card(self, node_id: str) -> Optional["_NodeItem"]:
        """取某個節點的圖元（highlight / 測試用；對應舊的 ``card()``）。"""
        return self._items.get(str(node_id))

    def set_score_summary(self, expr: str, threshold: Any) -> None:
        self._score_summary = "score = %s   threshold %s" % (expr, threshold)

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

    def fit(self) -> None:
        """整張圖縮放到看得完（但不縮到看不懂、也不放大）。"""
        rect = self._scene.itemsBoundingRect()
        if not rect.isValid():
            return
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
        item.setPos(float(x) - NODE_W / 2.0, float(y) - NODE_H / 2.0)
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
        pos = layout_columns(self._order, self._pairs + self._implicit)
        for nid, item in self._items.items():
            col, row = pos.get(nid, (0, 0))
            item.setPos(col * (NODE_W + COL_GAP), row * (NODE_H + ROW_GAP))
        self.refresh_edges()
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(rect)

    def refresh_edges(self) -> None:
        for e in self._edges:
            e.prepareGeometryChange()
            e.update()
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

    def _drop_link(self, scene_pos: QPointF) -> None:
        src, self._link_from = self._link_from, None
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
            if top is not None:
                top.set_hovered(True)

    def leaveEvent(self, e) -> None:           # noqa: D102
        if self._hover_node is not None:
            self._hover_node.set_hovered(False)
            self._hover_node = None
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
        self.resetTransform()
        self._sync_zoom_label()

    def wheelEvent(self, e) -> None:           # noqa: D102
        self.zoom_by(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
        e.accept()

    #: 背景點陣間距（畫布座標）。
    GRID = 22.0

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:  # noqa: D102
        """點陣底，不是格線底（F7-8）。

        格線會在整張畫布上鋪滿橫豎線，跟連線同一種筆觸，於是「哪條是資料流、
        哪條是背景」要看第二眼才分得出來。點只提供對齊的參考，不會跟線搶。
        """
        p.fillRect(rect, QColor(TOKENS["canvas_bg"]))
        step = self.GRID
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
