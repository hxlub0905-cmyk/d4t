#!/usr/bin/env python3
# ADEPT 單檔純文字包（由 tools/make_text_bundle.py 產生）。
"""整個 ADEPT repo 就在這個檔案裡，一行一行的純文字，沒有壓縮、沒有編碼。

為什麼是這種形式：公司政策擋掉 .zip 這個類別，而 proxy 也不讓 Python 逐檔抓 ——
能過的只剩「一個純文字檔」。你可以用記事本打開它，往下捲就看得到每個檔案的內容。

    python ADEPT_part3of6.py              # 解到 .\\ADEPT\\
    python ADEPT_part3of6.py --dest D:\\tools
    python ADEPT_part3of6.py --list       # 只看裡面有什麼，不寫任何檔案

每個檔案都帶 git blob SHA-1，解開時逐檔驗過才落地 —— 傳輸途中被動到的話會當場
講出來，不會讓你拿到一份安靜壞掉的程式碼。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

SENTINEL = "# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ===="
PART, N_PARTS = 3, 6   # 這是第幾批 / 共幾批（1/1 = 沒有分批）
TOTAL = 178                       # 整個 repo 有幾個檔案，不是這一批有幾個


def blob_sha(data: bytes) -> str:
    """git 算 blob SHA 的方式："blob <長度>\\0" + 內容。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def entries(lines):
    """走過資料區，一個一個吐出 (sha, 路徑, 內容位元組)。"""
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#F "):
            i += 1
            continue
        _, sha, count, path = line.split(" ", 3)
        n = int(count)
        # 資料區每一行前面有一個 '#'（那樣整個檔案才仍然是合法的 Python）。
        body = [ln[1:] if ln[:1] == "#" else ln for ln in lines[i + 1:i + 1 + n]]
        yield sha, path, "\n".join(body).encode("utf-8")
        i += 1 + n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unpack the ADEPT text bundle.")
    ap.add_argument("--dest", default="ADEPT", help="解到哪個資料夾（預設 .\\ADEPT）")
    ap.add_argument("--list", action="store_true", help="只列出內容，不寫檔")
    a = ap.parse_args(argv)

    # 用文字模式讀自己：Python 會把 CRLF 讀成 LF，所以這個檔案就算在傳輸途中
    # 被換過行尾也解得開（格式用「行數」而不是「位元組數」正是為了這件事）。
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    try:
        start = lines.index(SENTINEL) + 1
    except ValueError:
        print("✗ 找不到資料區 —— 這個檔案被截斷了，或不是完整的 bundle。")
        return 2

    items = list(entries(lines[start:]))
    if not items:
        print("✗ 資料區是空的 —— 這個檔案被截斷了。")
        return 2
    print("這個包裡有 %d 個檔案。" % len(items))
    if a.list:
        for _sha, path, data in items:
            print("  %8d  %s" % (len(data), path))
        return 0

    dest = os.path.abspath(a.dest)
    print("解到  : %s" % dest)
    bad, done = [], 0
    for sha, path, data in items:
        if blob_sha(data) != sha:
            bad.append(path)
            continue
        full = os.path.join(dest, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        tmp = full + ".tmp"                      # atomic：半個檔案不要留在磁碟上
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)
        done += 1

    if bad:
        print("")
        print("✗ %d 個檔案的內容跟它自己的 SHA 對不上：" % len(bad))
        for path in bad[:12]:
            print("    %s" % path)
        print("")
        print("  這個檔案在傳輸途中被動過（編輯器另存、郵件過濾器改寫都會這樣）。")
        print("  請重新取得一份，不要用編輯器打開後另存。這份程式碼不完整，不要用。")
        return 1

    print("✓ %d 個檔案都解開了，SHA 全部對得上。" % done)

    # 分批的時候要講「還缺幾個」—— 不然使用者不知道自己貼完了沒有。
    # 判斷依據是 tools/FILELIST.txt（它固定在第一批），而不是這一批的數量。
    listing = os.path.join(dest, "tools", "FILELIST.txt")
    have_listing = os.path.isfile(listing)
    missing = []
    if have_listing:
        with open(listing, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    rel = line.split(" ", 1)[1]
                    if not os.path.isfile(os.path.join(dest,
                                                       rel.replace("/", os.sep))):
                        missing.append(rel)

    if N_PARTS > 1 and not have_listing:
        # 還沒拿到檔案清單，所以「缺幾個」算不出來。**這時候絕對不能印
        # 「下一步：跑 doctor」** —— 那看起來就像整包已經到位了。
        print("")
        print("這是第 %d 批 / 共 %d 批，整個 repo 有 %d 個檔案 —— **還沒到齊**。"
              % (PART, N_PARTS, TOTAL))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。")
        print("第 1 批裡有檔案清單，貼過它之後每一批都會告訴你還缺哪些。")
        return 0

    if missing:
        print("")
        print("這是第 %d 批 / 共 %d 批。整個 repo 還缺 %d 個檔案 —— 在其他批裡。"
              % (PART, N_PARTS, len(missing)))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。缺的例如：")
        for rel in missing[:6]:
            print("    %s" % rel)
        return 0

    print("")
    print("下一步：")
    print("  cd %s" % dest)
    print("  python tools\\doctor.py        # 環境自檢（會告訴你還缺什麼）")
    print("  相依套件裝不了的話走離線 wheels：docs\\OFFLINE-INSTALL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ====
#F b69629982f34dd647e5a7ffcee693859f24cadb7 804 adept/ui/canvas.py
## ADEPT Studio 節點畫布 — authored 2026-07-28 (F7-6).
#"""``PipelineCanvas`` —— n8n 風格的節點畫布，取代原本的直線清單。
#
#為什麼這件事不用動引擎
#----------------------
#``core`` 從 F0 起就是 DAG：``Recipe`` 早就有 ``edges`` 欄位、
#``execution_order()`` 早就是 Kahn 拓撲排序 + 循環偵測、``validate()`` 早就會
#報「這條 route 有循環」。當初刻意寫成「UI v1 只呈現直線，之後上自由畫布時
#引擎零改動」。所以這一整個檔案純粹是 UI。
#
#畫布長什麼樣
#------------
#* 節點卡：左側是所屬階段的色條，卡上是名稱 + 非預設參數摘要。
#  停用的節點整張調淡（不是消失 —— 使用者要看得到它還在）。
#* 連接埠：左邊是輸入、右邊是輸出。從輸出拖到輸入就連起來。
#* 連線：三次貝茲曲線，方向永遠左→右，所以「資料往右流」是看得出來的。
#* 選取的節點與連線用 accent 色描邊；``Delete`` 刪掉選取的東西。
#
#位置怎麼決定
#------------
#**自動排版**：依拓撲深度分欄、同欄內依 ``node_order`` 排列。
#使用者可以拖動節點（當下看起來會照他擺的位置），但**位置不寫進 recipe**——
#recipe JSON 的結構沒有 ``pos`` 欄位，為了在畫布上存座標而改檔案格式，
#會讓每一份既有 recipe 都要遷移，代價和收益不成比例。重新載入就回到自動排版。
#
#循環擋在哪
#----------
#擋在 ``RecipeModel.add_edge``：拉出來的線若會造成循環，model 直接回 ``False``
#不落地，畫布也就不會畫出那條線。使用者看到的是「這條線拉不起來」，
#而不是「拉起來之後整條 pipeline 壞掉、跑的時候才報錯」。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List, Optional, Sequence, Tuple
#
#from PySide6.QtCore import QPointF, QRectF, Qt, Signal
#from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
#from PySide6.QtWidgets import (
#    QGraphicsItem,
#    QGraphicsScene,
#    QGraphicsView,
#    QHBoxLayout,
#    QLabel,
#    QMenu,
#    QPushButton,
#    QWidget,
#)
#
#from . import theme
#from .theme import TOKENS
#from .widgets import draw_group_icon
#
#__all__ = ["PipelineCanvas", "NODE_W", "NODE_H", "COL_GAP", "ROW_GAP"]
#
##: 一個節點最多畫幾個輸出埠（再多就擠不下，退回單一埠）。
#_MAX_PORTS = 4
#
##: 埠標籤佔的寬度（畫在節點右緣之外，boundingRect 必須算進去）。
#_PORT_LABEL_W = 52.0
#
##: 節點左側 icon 的邊長，以及裝著它的圓角色塊。
##: 用**色塊**而不是細色條（F7-8）：n8n 的節點一眼認得出來，靠的就是左邊那顆
##: 有顏色的圖示磚。細條太安靜，遠看整張畫布還是一排一模一樣的方框。
#_ICON = 18.0
#_TILE = 32.0
#
##: 節點卡尺寸與排版間距（畫布座標）。
#NODE_W, NODE_H = 190.0, 56.0
#COL_GAP, ROW_GAP = 96.0, 26.0
#_PORT_R = 5.0
#
##: 連線中點的方向箭頭大小。畫布可以縮放平移，光看曲線不一定分得出資料往哪流。
#_ARROW = 5.0
#
##: 還沒拉線時，一列最多排幾張卡（見 :func:`layout_columns`）。
#WRAP = 4
#
#
#def layout_columns(node_ids: Sequence[str],
#                   edges: Sequence[Tuple[str, str]]) -> Dict[str, Tuple[int, int]]:
#    """自動排版：``node_id -> (欄, 列)``。
#
#    欄 = 拓撲深度（最長前置路徑長度），列 = 同欄內依 ``node_ids`` 的原順序。
#    沒有任何連線時每個節點各自深度 0 —— 那會全部疊在第一欄，所以退化情況下
#    改成「一個接一個往右排」，讓空 recipe 加卡片時看起來仍然是一條鏈。
#
#    但那條鏈**會換行**（``WRAP``，F7-9）。一份九張卡、還沒拉線的 recipe 排成
#    一列會超過 2500px；``fit()`` 為了塞進畫面得縮到看不出字，而它又有下限
#    （縮成小方塊比留捲軸更糟），結果是「一排讀不出來的小方塊 + 一條捲軸」。
#    換行之後同樣九張卡是 3×3，每一張都讀得到字。閱讀順序仍然是左到右、
#    上到下 —— 跟文字一樣，不需要額外學。
#    """
#    ids = [str(n) for n in node_ids]
#    idx = {n: i for i, n in enumerate(ids)}
#    preds: Dict[str, List[str]] = {n: [] for n in ids}
#    for a, b in edges:
#        if a in idx and b in idx:
#            preds[b].append(a)
#
#    if not any(preds[n] for n in ids):
#        return {n: (i % WRAP, i // WRAP) for i, n in enumerate(ids)}
#
#    depth: Dict[str, int] = {}
#    for n in ids:                       # ids 已是拓撲順序，一遍就夠
#        depth[n] = max((depth.get(p, 0) + 1 for p in preds[n]), default=0)
#
#    # 一「帶」= 換行之前的 WRAP 個深度。帶高取「最擠的那個深度有幾個節點」，
#    # 這樣換行之後上下兩帶不會疊在一起。
#    per_depth: Dict[int, int] = {}
#    for n in ids:
#        per_depth[depth[n]] = per_depth.get(depth[n], 0) + 1
#    band_h = max(per_depth.values(), default=1)
#
#    rows: Dict[int, int] = {}
#    out: Dict[str, Tuple[int, int]] = {}
#    for n in sorted(ids, key=lambda x: (depth[x], idx[x])):
#        d = depth[n]
#        band, col = divmod(d, WRAP)
#        r = rows.get(d, 0)
#        rows[d] = r + 1
#        out[n] = (col, band * band_h + r)
#    return out
#
#
#def _draw_elided(p: QPainter, rect: QRectF, text: str) -> None:
#    """畫一行文字，太長就切成 ``像這樣…``。
#
#    直接 ``drawText`` 到一個放不下的矩形，Qt 會**硬切在字的中間**，看起來像
#    畫面壞掉；``參數摘要=diff · metri`` 這種殘句還會讓人以為值真的是那樣。
#    """
#    s = str(text)
#    fm = p.fontMetrics()
#    if fm.horizontalAdvance(s) > rect.width():
#        s = fm.elidedText(s, Qt.ElideRight, int(rect.width()))
#    p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, s)
#
#
#class _NodeItem(QGraphicsItem):
#    """一張節點卡（自繪；顏色全部取自 ``theme.TOKENS``）。"""
#
#    def __init__(self, info: Dict[str, Any], canvas: "PipelineCanvas"):
#        super().__init__()
#        self.canvas = canvas
#        self.info = dict(info)
#        self.node_id = str(info.get("node_id", ""))
#        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
#        self.setFlag(QGraphicsItem.ItemIsMovable, True)
#        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
#        tip = "%s — %s" % (self.node_id, info.get("label", ""))
#        if info.get("problem"):
#            # 標記說「有問題」，滑鼠停上去說「是什麼問題」。標記本身放不下一句話，
#            # 而「有一個紅點但不知道為什麼」比沒有標記更讓人焦慮。
#            tip += "\n\n⚠ %s" % info["problem"]
#        self.setToolTip(tip)
#
#    # -- 幾何 ---------------------------------------------------------------
#    def boundingRect(self) -> QRectF:
#        """**要涵蓋所有畫得出去的東西**，否則拖動節點會留下殘影。
#
#        埠標籤（"test" / "ref"）畫在節點右緣之外 —— 之前 boundingRect 只算到
#        ``NODE_W + _PORT_R``，Qt 就只重繪那個範圍，標籤的舊位置沒被清掉。
#        """
#        return QRectF(-_PORT_R - 1, -1,
#                      NODE_W + 2 * _PORT_R + _PORT_LABEL_W,
#                      NODE_H + 5)
#
#    def in_port(self) -> QPointF:
#        return self.scenePos() + self.in_port_local()
#
#    @staticmethod
#    def in_port_local() -> QPointF:
#        return QPointF(0.0, NODE_H / 2.0)
#
#    def in_names(self) -> List[str]:
#        """這個節點讀哪些影像流（用來決定上游的線該接哪個埠）。"""
#        return [str(r) for r in (self.info.get("reads") or [])]
#
#    def out_names(self) -> List[str]:
#        """這個節點吐出的影像流名稱（決定畫幾個輸出埠）。
#
#        來自 ``Step.describe()`` 的 ``writes``。對 patch 的 Input 節點來說
#        那是 ``["test", "ref"]`` —— 畫布上就看得到「一張 defect、一張 reference」，
#        而不是一個什麼都不說的單一輸出。
#        """
#        names = [str(w) for w in (self.info.get("writes") or [])]
#        return names[:_MAX_PORTS] or [""]
#
#    def out_anchors_local(self) -> List[QPointF]:
#        """每個輸出埠在**本地座標**的位置（由上而下均分節點右緣）。
#
#        ``paint()`` 畫的是本地座標，連線算的是場景座標 —— 兩者差一個
#        ``scenePos()``。之前只有場景座標版，``paint()`` 直接拿去畫，於是節點一
#        離開原點，輸出埠就被畫到 ``2 × 位移`` 的地方：第一欄的 Input 看起來正常
#        （它剛好在原點），後面每一張卡的右側圓點都畫到卡外面去，看起來就是
#        **「新增的節點只有前面有圓框、後面沒有」**；拖動 Input 時埠標籤
#        （test/ref）也會離開 ``boundingRect``，留下擦不掉的殘影。
#        """
#        n = len(self.out_names())
#        if n <= 1:
#            return [QPointF(NODE_W, NODE_H / 2.0)]
#        step = NODE_H / (n + 1)
#        return [QPointF(NODE_W, step * (i + 1)) for i in range(n)]
#
#    def out_anchors(self) -> List[QPointF]:
#        """每個輸出埠在**場景座標**的位置（連線用）。"""
#        base = self.scenePos()
#        return [base + p for p in self.out_anchors_local()]
#
#    def out_port(self, index: int = 0) -> QPointF:
#        anchors = self.out_anchors()
#        return anchors[max(0, min(int(index), len(anchors) - 1))]
#
#    def out_port_at(self, pos: QPointF):
#        """本地座標 ``pos`` 命中哪一個輸出埠（沒命中回 ``None``）。"""
#        for i, local in enumerate(self.out_anchors_local()):
#            d = pos - local
#            if (d.x() * d.x() + d.y() * d.y()) <= (_PORT_R * 3.0) ** 2:
#                return i
#        return None
#
#    # -- 繪製 ---------------------------------------------------------------
#    def paint(self, p: QPainter, _opt, _widget=None) -> None:
#        enabled = bool(self.info.get("enabled", True))
#        selected = self.isSelected()
#        body = QRectF(0, 0, NODE_W, NODE_H)
#
#        p.setRenderHint(QPainter.Antialiasing, True)
#
#        # 投影：讓節點浮在網格之上。用畫的而不是 QGraphicsDropShadowEffect ——
#        # effect 會強迫 Qt 額外開一層離屏 buffer，為了 2px 的陰影不值得。
#        shadow = QColor(0, 0, 0, 46 if enabled else 22)
#        p.setPen(Qt.NoPen)
#        p.setBrush(shadow)
#        p.drawRoundedRect(body.translated(1.5, 2.5), 7, 7)
#
#        gid = str(self.info.get("group", "") or "enhance")
#        tile_col = QColor(theme.group_hex(gid) if enabled else TOKENS["seg_disabled"])
#
#        border = QColor(TOKENS["accent"] if selected else TOKENS["border_default"])
#        # 停用的節點畫虛線框（n8n 的慣例）—— 不是消失，是「還在，但這次不跑」。
#        pen = QPen(border, 2.0 if selected else 1.0)
#        if not enabled:
#            pen.setStyle(Qt.DashLine)
#        p.setPen(pen)
#        p.setBrush(QColor(TOKENS["bg_surface"] if enabled else TOKENS["disabled_bg"]))
#        p.drawRoundedRect(body, 7, 7)
#
#        # 左邊的圖示磚：淡色底 + 與左側 rail 完全相同的圖形（F7-8）。
#        tile = QRectF(8, (NODE_H - _TILE) / 2.0, _TILE, _TILE)
#        wash = QColor(tile_col)
#        wash.setAlpha(46 if enabled else 24)
#        p.setPen(QPen(tile_col if enabled else QColor(TOKENS["border_default"]), 1.0))
#        p.setBrush(wash)
#        p.drawRoundedRect(tile, 6, 6)
#
#        icon_rect = QRectF(tile.center().x() - _ICON / 2.0,
#                           tile.center().y() - _ICON / 2.0, _ICON, _ICON)
#        p.save()
#        p.translate(icon_rect.topLeft())
#        draw_group_icon(p, gid, tile_col.name(), _ICON)
#        p.restore()
#
#        # 「這張卡還不能跑」的標記（F7-13）。lint 早就知道這件事，只是那個知識
#        # 以前留在跑之前的檢查裡 —— 於是一張缺模板的卡在畫布上看起來跟設定完整
#        # 的一模一樣，使用者要按下 Run trial 才會知道。
#        self._paint_badge(p, body)
#
#        text_x = tile.right() + 9
#        # 有警示標記時把標題讓開 —— 不讓的話標記正好蓋在卡片名字的尾巴上，
#        # 兩個東西都變得難讀。
#        text_w = NODE_W - text_x - (8 if not self.problem() else 22)
#
#        fg = TOKENS["text_primary"] if enabled else TOKENS["text_disabled"]
#        p.setPen(QColor(fg))
#        f = p.font()
#        f.setBold(True)
#        f.setPointSizeF(max(7.0, f.pointSizeF()))
#        p.setFont(f)
#        _draw_elided(p, QRectF(text_x, 9, text_w, 15),
#                     str(self.info.get("label", self.node_id)))
#        f.setBold(False)
#        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.0))
#        p.setFont(f)
#        p.setPen(QColor(TOKENS["text_secondary"] if enabled else TOKENS["text_disabled"]))
#        _draw_elided(p, QRectF(text_x, 24, text_w, 13), self.subtitle())
#        summary = str(self.info.get("summary", ""))
#        if summary:
#            _draw_elided(p, QRectF(text_x, 36, text_w, 13), summary)
#
#        # 連接埠（**本地座標** —— 見 out_anchors_local 的說明）。
#        # 輸入是空心圈、輸出是實心點：一眼看得出線該從哪邊拉到哪邊。
#        p.setPen(QPen(QColor(TOKENS["canvas_edge"]), 1.2))
#        p.setBrush(QBrush(QColor(TOKENS["bg_surface"])))
#        p.drawEllipse(self.in_port_local(), _PORT_R, _PORT_R)
#
#        outs = self.out_names()
#        p.setBrush(QBrush(QColor(TOKENS["canvas_edge"])))
#        for name, anchor in zip(outs, self.out_anchors_local()):
#            p.drawEllipse(anchor, _PORT_R, _PORT_R)
#            if not name:
#                continue
#            # 每個輸出埠都標上它吐的影像流名（F7-9）。以前只有多埠才標，
#            # 於是「這張卡到底做在哪一條流上」在畫布上是看不到的 ——
#            # 而 Enhance 卡的 target / also apply 講的正是這些名字。
#            p.setPen(QColor(TOKENS["text_secondary"]))
#            p.drawText(QRectF(anchor.x() + 4, anchor.y() - 7, _PORT_LABEL_W - 10, 14),
#                       Qt.AlignVCenter | Qt.AlignLeft, name)
#            p.setPen(QPen(QColor(TOKENS["canvas_edge"]), 1.2))
#
#    def subtitle(self) -> str:
#        """副標：**這張卡吃什麼、吐什麼**（F7-14）。
#
#        以前這一行印的是 node_id（``roi_template``）—— 那是 recipe JSON 的鍵，
#        使用者看了得不到任何新資訊：卡片名字就在它上面一行。n8n 的節點副標印的
#        是那張卡這次**被設定成做什麼**，所以整張畫布不點開就讀得懂。
#
#        重複的卡片（``glv_stats2``）才把 id 帶出來 —— 那時候「是哪一張」才真的
#        是使用者需要知道的事。
#        """
#        reads = [r for r in (self.info.get("reads") or []) if r]
#        outs = [w for w in (self.info.get("writes") or []) if w]
#        regions = [r for r in (self.info.get("regions_out") or []) if r]
#        right = " ".join(str(x) for x in (outs or regions))
#        left = " ".join(str(r) for r in reads)
#        if left and right:
#            body = "%s → %s" % (left, right)
#        else:
#            body = left or right or str(self.info.get("step_key", self.node_id))
#        step_key = str(self.info.get("step_key", ""))
#        if step_key and self.node_id != step_key:
#            # 同一張卡加了第二次：這時候 id 是有意義的（分數表達式指的是特徵名，
#            # 但 lint 訊息與前綴講的是這個 id）。
#            body = "%s · %s" % (self.node_id, body)
#        return body
#
#    def problem(self) -> str:
#        """這張卡現在有什麼問題（空字串 = 沒問題）。"""
#        return str(self.info.get("problem", "") or "")
#
#    def _paint_badge(self, p: QPainter, body: QRectF) -> None:
#        """右上角一個小圓標。錯誤紅、警告琥珀。
#
#        文字用 ``!`` 而不是圖形：這個標記只有 14 px，任何再細一點的形狀在
#        100% 縮放下都會糊成一個點。
#        """
#        why = self.problem()
#        if not why:
#            return
#        level = str(self.info.get("problem_level", "error"))
#        col = QColor(TOKENS["danger_text"] if level == "error"
#                     else TOKENS["warning"])
#        r = 7.0
#        centre = QPointF(body.right() - r - 3.0, body.top() + r + 3.0)
#        p.setPen(QPen(QColor(TOKENS["bg_surface"]), 1.5))
#        p.setBrush(QBrush(col))
#        p.drawEllipse(centre, r, r)
#        p.setPen(QPen(QColor("#ffffff"), 1.0))
#        f = p.font()
#        f.setBold(True)
#        f.setPointSizeF(8.0)
#        p.setFont(f)
#        p.drawText(QRectF(centre.x() - r, centre.y() - r, 2 * r, 2 * r),
#                   Qt.AlignCenter, "!")
#
#    # -- 互動 ---------------------------------------------------------------
#    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
#        hit = (self.out_port_at(e.pos())
#               if e.button() == Qt.LeftButton else None)
#        if hit is not None:
#            self.canvas.begin_link(self, hit)  # 從某一個輸出埠拉線
#            e.accept()
#            return
#        self.canvas.node_selected.emit(self.node_id)
#        super().mousePressEvent(e)
#
#    def itemChange(self, change, value):        # noqa: D102 - Qt hook
#        if change == QGraphicsItem.ItemPositionHasChanged:
#            self.canvas.refresh_edges()
#        return super().itemChange(change, value)
#
#    def contextMenuEvent(self, e) -> None:      # noqa: D102 - Qt hook
#        menu = QMenu()
#        act_toggle = menu.addAction(
#            "Skip this step" if self.info.get("enabled", True) else "Enable this step")
#        act_remove = menu.addAction("Remove")
#        chosen = menu.exec(e.screenPos())
#        if chosen is act_toggle:
#            self.canvas.node_toggled.emit(
#                self.node_id, not bool(self.info.get("enabled", True)))
#        elif chosen is act_remove:
#            self.canvas.remove_requested.emit(self.node_id)
#        e.accept()
#
#
#class _EdgeItem(QGraphicsItem):
#    """一條連線（三次貝茲，左→右）。點它可選取，``Delete`` 移除。
#
#    ``implicit=True`` 是 **route 的隱含順序**（F7-10），畫成虛線、不可選取。
#    引擎的依賴是「route 相鄰對 ∪ 顯式 edges」——
#    也就是說**畫布上沒有線，不代表沒有連接**。以前只畫顯式 edges，於是載入
#    一份沒拉過線的 recipe 看到的是「九張互不相干的卡」，但它其實是照順序跑的。
#    使用者只會得到兩種結論，兩種都是錯的：以為要自己連起來才會跑，
#    或以為沒連線的卡不會執行。
#
#    不可選取（也就刪不掉）是刻意的：隱含順序來自卡片的排列，
#    刪掉它在語意上等於「把這張卡從流程裡拿掉」，那是另一個動作。
#    """
#
#    def __init__(self, src: _NodeItem, dst: _NodeItem, canvas: "PipelineCanvas",
#                 port: int = 0, implicit: bool = False):
#        super().__init__()
#        self.src, self.dst, self.canvas, self.port = src, dst, canvas, int(port)
#        self.implicit = bool(implicit)
#        self.setFlag(QGraphicsItem.ItemIsSelectable, not self.implicit)
#        self.setZValue(-2.0 if self.implicit else -1.0)
#        if self.implicit:
#            self.setToolTip(
#                "%s runs before %s because of the order of the cards.\n"
#                "Drag from a port to make the connection explicit."
#                % (src.node_id, dst.node_id))
#        else:
#            self.setToolTip("%s → %s  (select and press Delete to remove)"
#                            % (src.node_id, dst.node_id))
#
#    def pair(self) -> Tuple[str, str]:
#        return (self.src.node_id, self.dst.node_id)
#
#    def path(self) -> QPainterPath:
#        a, b = self.src.out_port(self.port), self.dst.in_port()
#        dx = max(40.0, abs(b.x() - a.x()) * 0.5)
#        p = QPainterPath(a)
#        p.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
#        return p
#
#    def boundingRect(self) -> QRectF:
#        return self.path().boundingRect().adjusted(-6, -6, 6, 6)
#
#    def shape(self) -> QPainterPath:
#        stroker_pen = QPen(Qt.black, 10.0)
#        from PySide6.QtGui import QPainterPathStroker
#        st = QPainterPathStroker(stroker_pen)
#        return st.createStroke(self.path())
#
#    def paint(self, p: QPainter, _opt, _widget=None) -> None:
#        p.setRenderHint(QPainter.Antialiasing, True)
#        col = QColor(TOKENS["canvas_edge_active"] if self.isSelected()
#                     else TOKENS["canvas_edge"])
#        path = self.path()
#        if self.implicit:
#            # **自己的顏色**，不是實線色調淡（F7-18）。同色淡一點只說得出
#            # 「比較不重要」；這兩種線在語意上是不同的東西 —— 一條是使用者拉的
#            # （刪得掉、表達意圖），一條是卡片排列帶來的順序（刪不掉，想讓它
#            # 變成真的連線就自己拉一條）。虛線講的是「這裡可以拉」，那需要
#            # 一眼認得出來，而深淺在縮放與換主題之後就不一定分得出來了。
#            col = QColor(TOKENS["canvas_edge_implicit"])
#            p.setPen(QPen(col, 1.4, Qt.DashLine))
#        else:
#            p.setPen(QPen(col, 2.2 if self.isSelected() else 1.6))
#        p.setBrush(Qt.NoBrush)
#        p.drawPath(path)
#
#        # 中點的方向箭頭。畫布可以縮放、平移、節點也可以拖，光看一條曲線不一定
#        # 分得出資料往哪一邊流 —— 這是「這是一張流程圖」的最基本線索。
#        mid = path.pointAtPercent(0.5)
#        ang = path.angleAtPercent(0.5)
#        p.save()
#        p.translate(mid)
#        p.rotate(-ang)
#        head = QPainterPath(QPointF(_ARROW, 0.0))
#        head.lineTo(QPointF(-_ARROW * 0.8, _ARROW * 0.72))
#        head.lineTo(QPointF(-_ARROW * 0.8, -_ARROW * 0.72))
#        head.closeSubpath()
#        p.setPen(Qt.NoPen)
#        p.setBrush(col)
#        p.drawPath(head)
#        p.restore()
#
#
#class PipelineCanvas(QGraphicsView):
#    """節點畫布。對外的 API 與訊號刻意與舊的 ``PipelinePanel`` 對齊。
#
#    Studio 只要換掉建構的類別，其餘接線幾乎不動 —— 這是為了讓「換 UI」
#    不要順便變成「重寫主視窗」。
#    """
#
#    node_selected = Signal(str)
#    node_toggled = Signal(str, bool)
#    move_requested = Signal(str, int)          # 相容用，畫布不發
#    remove_requested = Signal(str)
#    score_clicked = Signal()
#    #: ``(來源節點, 目標節點, 這條線帶的影像流名)``。第三個參數是 F7-18 加的：
#    #: 使用者從 ``ref`` 那個埠拉一條線到某張卡，講的就是「這張卡做在 ref 上」。
#    #: 沒有它的話，畫布只能表達「先後順序」，而「對哪一張圖做」還是得回到
#    #: 控制列上的下拉去設 —— 那正是使用者說「變很複雜」的東西。
#    #: 來源節點只有一個沒有名字的輸出埠時是空字串。
#    edge_added = Signal(str, str, str)
#    edge_removed = Signal(str, str)
#
#    def __init__(self, parent=None):
#        super().__init__(parent)
#        self._scene = QGraphicsScene(self)
#        self.setScene(self._scene)
#        self.setRenderHint(QPainter.Antialiasing, True)
#        self.setDragMode(QGraphicsView.RubberBandDrag)
#        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
#        self.setFrameShape(QGraphicsView.NoFrame)
#        self.setMinimumHeight(180)
#
#        self._items: Dict[str, _NodeItem] = {}
#        self._edges: List[_EdgeItem] = []
#        self._order: List[str] = []
#        self._pairs: List[Tuple[str, str]] = []      # 使用者拉的線
#        self._implicit: List[Tuple[str, str]] = []   # route 順序帶來的依賴
#        self._selected: Optional[str] = None
#        self._score_summary = ""
#        self._link_from: Optional[_NodeItem] = None
#        self._link_port = 0
#        self._link_line = None
#        self._build_zoom_bar()
#
#    # ---- 縮放控制（F7-14）--------------------------------------------------
#    def _build_zoom_bar(self) -> None:
#        """左下角四顆小鈕：縮小 / 放大 / 全部看得完 / 回到 100%。
#
#        滾輪縮放本來就有，但**畫面上沒有任何東西說得出這件事** —— 而且滾過頭
#        之後沒有路回來：點陣底縮小之後每一格都一樣，使用者不知道自己在哪裡。
#        n8n 把這四顆固定放在左下角，這裡照做（順便顯示目前的百分比，
#        「我到底縮到多小了」也是看不出來的事）。
#        """
#        bar = QWidget(self)
#        bar.setObjectName("canvasZoom")
#        lay = QHBoxLayout(bar)
#        lay.setContentsMargins(4, 3, 4, 3)
#        lay.setSpacing(2)
#        self._zoom_label = QLabel("100%", bar)
#        self._zoom_label.setObjectName("paramHint")
#        self._zoom_label.setMinimumWidth(38)
#        self._zoom_label.setAlignment(Qt.AlignCenter)
#
#        specs = (("−", "Zoom out", lambda: self.zoom_by(1 / 1.25)),
#                 ("+", "Zoom in", lambda: self.zoom_by(1.25)),
#                 ("⤢", "Fit the whole pipeline in view", self.fit),
#                 ("1:1", "Back to 100%", self.reset_zoom))
#        self._zoom_buttons = []
#        for text, tip, slot in specs:
#            b = QPushButton(text, bar)
#            b.setObjectName("cardButton")
#            b.setToolTip(tip)
#            b.setFixedSize(24 if text != "1:1" else 30, 22)
#            b.setFocusPolicy(Qt.NoFocus)
#            b.clicked.connect(slot)
#            lay.addWidget(b)
#            self._zoom_buttons.append(b)
#        lay.addWidget(self._zoom_label)
#        bar.adjustSize()
#        self._zoom_bar = bar
#        self._place_zoom_bar()
#
#    def _place_zoom_bar(self) -> None:
#        bar = getattr(self, "_zoom_bar", None)
#        if bar is None:
#            return
#        bar.adjustSize()
#        bar.move(8, max(0, self.viewport().height() - bar.height() - 8))
#        bar.raise_()
#
#    def _sync_zoom_label(self) -> None:
#        label = getattr(self, "_zoom_label", None)
#        if label is not None:
#            label.setText("%d%%" % self.zoom_percent())
#
#    def resizeEvent(self, e) -> None:          # noqa: D102 - Qt hook
#        super().resizeEvent(e)
#        self._place_zoom_bar()
#
#    # ---- 對外（與 PipelinePanel 對齊）--------------------------------------
#    def set_nodes(self, nodes: Sequence[Dict[str, Any]],
#                  edges: Sequence[Tuple[str, str]] = ()) -> None:
#        """重建整張畫布。``nodes`` 依執行順序，``edges`` 是顯式連線。"""
#        self._scene.clear()
#        self._items, self._edges = {}, []
#        self._order = [str(n.get("node_id", "")) for n in nodes]
#        self._pairs = [(str(a), str(b)) for a, b in (edges or ())]
#
#        # route 的相鄰對也是**真的依賴**（engine 的 execution_order 是
#        # 「route 相鄰對 ∪ edges」），所以排版與繪製都要把它算進去。
#        self._implicit = [pair for pair in zip(self._order, self._order[1:])
#                          if pair not in set(self._pairs)]
#
#        pos = layout_columns(self._order, self._pairs + self._implicit)
#        for info in nodes:
#            item = _NodeItem(info, self)
#            col, row = pos.get(item.node_id, (0, 0))
#            item.setPos(col * (NODE_W + COL_GAP), row * (NODE_H + ROW_GAP))
#            self._scene.addItem(item)
#            self._items[item.node_id] = item
#
#        for pairs, implicit in ((self._pairs, False), (self._implicit, True)):
#            for a, b in pairs:
#                if a not in self._items or b not in self._items:
#                    continue
#                src, dst = self._items[a], self._items[b]
#                for port in self._ports_between(src, dst):
#                    edge = _EdgeItem(src, dst, self, port, implicit=implicit)
#                    self._scene.addItem(edge)
#                    self._edges.append(edge)
#
#        self.set_selected(self._selected)
#        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
#        self._scene.setSceneRect(rect)
#
#    def node_item(self, node_id: str):
#        """畫布上那個節點（測試與外部檢查用；沒有回 ``None``）。"""
#        return self._items.get(str(node_id))
#
#    @staticmethod
#    def _ports_between(src: "_NodeItem", dst: "_NodeItem") -> List[int]:
#        """一條依賴要畫成幾條線 —— 依**兩端共用的影像流**決定。
#
#        Input 節點吐 ``test`` 與 ``ref``；``subtract`` 兩張都讀，所以
#        Input → Subtract 會畫**兩條**線，各自從對應的埠出發。
#        這是推導出來的，不是存起來的 —— recipe JSON 的 edge 仍然是
#        ``[from, to]`` 兩個 id，格式不用改，重新載入也不會掉資訊。
#
#        兩端沒有共用的流（或下游沒宣告 reads）→ 退回單一條線。
#        """
#        outs = src.out_names()
#        wanted = set(dst.in_names())
#        ports = [i for i, name in enumerate(outs) if name in wanted]
#        return ports or [0]
#
#    def node_ids(self) -> List[str]:
#        return list(self._order)
#
#    def edge_pairs(self) -> List[Tuple[str, str]]:
#        return list(self._pairs)
#
#    def set_selected(self, node_id: Optional[str]) -> None:
#        self._selected = None if node_id is None else str(node_id)
#        for nid, item in self._items.items():
#            item.setSelected(nid == self._selected)
#            item.update()
#
#    def selected_node(self) -> Optional[str]:
#        return self._selected
#
#    def selected(self) -> Optional[str]:
#        """與舊 ``PipelinePanel.selected()`` 同名同義。"""
#        return self._selected
#
#    def card(self, node_id: str) -> Optional["_NodeItem"]:
#        """取某個節點的圖元（highlight / 測試用；對應舊的 ``card()``）。"""
#        return self._items.get(str(node_id))
#
#    def set_score_summary(self, expr: str, threshold: Any) -> None:
#        self._score_summary = "score = %s   threshold %s" % (expr, threshold)
#
#    def score_summary(self) -> str:
#        return self._score_summary
#
#    def score_summary_text(self) -> str:
#        """與舊 ``PipelinePanel.score_summary_text()`` 同名同義。"""
#        return self._score_summary
#
#    #: ``fit()`` 最多縮到多小。還沒拉線的 recipe 會排成一條很長的橫列，
#    #: 硬要全部塞進畫面會把節點縮成看不出字的小方塊 —— 那時候寧可留捲軸。
#    MIN_FIT_SCALE = 0.45
#
#    def fit(self) -> None:
#        """整張圖縮放到看得完（但不縮到看不懂）。"""
#        rect = self._scene.itemsBoundingRect()
#        if not rect.isValid():
#            return
#        self.fitInView(rect.adjusted(-30, -30, 30, 30), Qt.KeepAspectRatio)
#        s = self.transform().m11()
#        if 0 < s < self.MIN_FIT_SCALE:
#            self.scale(self.MIN_FIT_SCALE / s, self.MIN_FIT_SCALE / s)
#        self._sync_zoom_label()
#
#    def refresh_edges(self) -> None:
#        for e in self._edges:
#            e.prepareGeometryChange()
#            e.update()
#
#    # ---- 拉線 -------------------------------------------------------------
#    def begin_link(self, src: _NodeItem, port: int = 0) -> None:
#        self._link_from = src
#        self._link_port = int(port)
#        self._link_line = self._scene.addPath(
#            QPainterPath(src.out_port(port)),
#            QPen(QColor(TOKENS["canvas_edge_active"]), 1.6, Qt.DashLine))
#
#    def _drop_link(self, scene_pos: QPointF) -> None:
#        src, self._link_from = self._link_from, None
#        port = int(getattr(self, "_link_port", 0))
#        if self._link_line is not None:
#            self._scene.removeItem(self._link_line)
#            self._link_line = None
#        if src is None:
#            return
#        for item in self._scene.items(scene_pos):
#            if isinstance(item, _NodeItem) and item is not src:
#                self.edge_added.emit(src.node_id, item.node_id,
#                                     self.stream_of(src, port))
#                return
#
#    @staticmethod
#    def stream_of(src: "_NodeItem", port: int) -> str:
#        """``src`` 的第 ``port`` 個輸出埠吐的影像流名（沒有名字回空字串）。"""
#        names = src.out_names()
#        if 0 <= port < len(names):
#            return str(names[port] or "")
#        return ""
#
#    def link_to(self, src_id: str, dst_id: str, port: int = 0) -> None:
#        """程式化拉一條線（測試用；等同使用者從第 ``port`` 個輸出埠拖過去）。"""
#        src = self._items.get(str(src_id))
#        if src is not None and str(dst_id) in self._items:
#            self.edge_added.emit(str(src_id), str(dst_id),
#                                 self.stream_of(src, int(port)))
#
#    # ---- Qt hooks ---------------------------------------------------------
#    def mouseMoveEvent(self, e) -> None:       # noqa: D102
#        if self._link_from is not None and self._link_line is not None:
#            a = self._link_from.out_port(getattr(self, "_link_port", 0))
#            b = self.mapToScene(e.pos())
#            dx = max(40.0, abs(b.x() - a.x()) * 0.5)
#            path = QPainterPath(a)
#            path.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
#            self._link_line.setPath(path)
#            e.accept()
#            return
#        super().mouseMoveEvent(e)
#
#    def mouseReleaseEvent(self, e) -> None:    # noqa: D102
#        if self._link_from is not None:
#            self._drop_link(self.mapToScene(e.pos()))
#            e.accept()
#            return
#        super().mouseReleaseEvent(e)
#
#    def keyPressEvent(self, e) -> None:        # noqa: D102
#        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
#            for item in list(self._scene.selectedItems()):
#                if isinstance(item, _EdgeItem):
#                    a, b = item.pair()
#                    self.edge_removed.emit(a, b)
#                elif isinstance(item, _NodeItem):
#                    self.remove_requested.emit(item.node_id)
#            e.accept()
#            return
#        super().keyPressEvent(e)
#
#    #: 縮放範圍。沒有下限的話滾兩下就把整張圖縮成一個點，而且**看不出自己在
#    #: 哪裡**（背景是點陣，縮小之後每一格都長得一樣）；沒有上限則會滾進一片
#    #: 純色裡。兩種都只能靠「fit」把自己救回來，而在這之前使用者不知道有這顆鈕。
#    MIN_SCALE, MAX_SCALE = 0.25, 3.0
#
#    def zoom_percent(self) -> int:
#        return int(round(self.transform().m11() * 100))
#
#    def zoom_by(self, factor: float) -> None:
#        """縮放，並夾在 MIN_SCALE / MAX_SCALE 之間。"""
#        s = self.transform().m11()
#        target = max(self.MIN_SCALE, min(self.MAX_SCALE, s * float(factor)))
#        if abs(target - s) > 1e-9:
#            self.scale(target / s, target / s)
#        self._sync_zoom_label()
#
#    def reset_zoom(self) -> None:
#        """回到 100%（`fit` 之後想看清楚字的時候要的就是這個）。"""
#        self.resetTransform()
#        self._sync_zoom_label()
#
#    def wheelEvent(self, e) -> None:           # noqa: D102
#        self.zoom_by(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
#        e.accept()
#
#    #: 背景點陣間距（畫布座標）。
#    GRID = 22.0
#
#    def drawBackground(self, p: QPainter, rect: QRectF) -> None:  # noqa: D102
#        """點陣底，不是格線底（F7-8）。
#
#        格線會在整張畫布上鋪滿橫豎線，跟連線同一種筆觸，於是「哪條是資料流、
#        哪條是背景」要看第二眼才分得出來。點只提供對齊的參考，不會跟線搶。
#        """
#        p.fillRect(rect, QColor(TOKENS["canvas_bg"]))
#        step = self.GRID
#        # 縮太小的時候點會糊成一片灰 —— 那時候乾脆不畫
#        if self.transform().m11() < 0.45:
#            return
#        p.setPen(QPen(QColor(TOKENS["canvas_grid"]), 1.6, Qt.SolidLine,
#                      Qt.RoundCap))
#        x0 = rect.left() - (rect.left() % step)
#        y0 = rect.top() - (rect.top() % step)
#        y = y0
#        while y < rect.bottom():
#            x = x0
#            while x < rect.right():
#                p.drawPoint(QPointF(x, y))
#                x += step
#            y += step
#
#F d90ef40306c61438f189b6a41c48d26e326ed96c 1164 adept/ui/export_dialog.py
## ADEPT Studio 輸出精靈 — authored 2026-07-28 (M5-3).
#"""``ExportDialog`` —— 把一批試跑/全跑結果寫成 KLARF / 報表 / 疊圖。
#
#這是 M5 的「出口」：Gallery 與直方圖讓工程師**看**懂這批結果，這支對話框讓
#他把結果**交出去**（回寫 KLARF 給 review 站、出報表給主管、出疊圖當證據）。
#
#三個區塊
#--------
#
#(a) **KLARF 寫回** —— 三選一，每個模式都附一行白話：
#
#    ==========================  ====================================================
#    ``就地改欄（無損）``          只改既有欄位（CLASSNUMBER / ROUGHBINNUMBER /
#    inplace                     FINEBINNUMBER / DSIZE），沒被改到的 byte 與原檔
#                                逐位元組相同。**這份 KLARF 沒有的欄位，控制項會
#                                變灰並寫明原因**（絕不默默略過）。
#    ``另存新檔（含分數欄）``      追加 ADCSCORE / ADCCLASS（可再選特徵欄），
#    annotate                    影像區塊仍留在列尾。
#    ``Top-N 另存``               依分數由高到低只留前 N 顆（或 >= 門檻），
#    topn                        可重新編號 DEFECTID。
#    ==========================  ====================================================
#
#    ★ **「預覽變更」是硬性關卡** ★ ——「寫出」在按過預覽之前是灰的。預覽走
#    :func:`~adept.core.export.plan_writeback`（乾跑，不寫任何檔案），把
#    :class:`~adept.core.export.WriteBackPlan` 翻成白話（會改幾列、動到哪些欄、
#    新增哪些欄、輸出幾列）再加上檔案健檢的 ✓ / △ / ✗ 三種行。任何一個設定被
#    改動 → 計畫作廢、「寫出」立刻變回灰的（使用者看到的一定是**這一版設定**
#    的後果）。
#
#(b) **報表** —— CSV（feature vector）／ Excel（三頁報告），各自的輸出路徑。
#
#(c) **Overlay 影像** —— 依分數由高到低取前 N 顆，逐顆
#    :func:`~adept.core.export.render_overlay` → :func:`~adept.core.export.write_png`。
#
#執行緒
#------
#所有實際寫檔都在 :class:`ExportWorker`（沿用 ``workers.py`` 的一次性 QThread
#樣式）裡跑，GUI 不卡；進度條吃 ``progress(done, total, 說明)``。
#真正的工作是 Qt-free 的模組層函式 :func:`run_export_job`，所以測試可以完全
#同步地跑它（``dialog.run_export(sync=True)``）。
#
#錯誤
#----
#:class:`~adept.core.export.ExportError` 一律翻成一個看得懂的訊息框
#（互動路徑）或 :meth:`ExportDialog.error_text`（同步路徑）——
#**永遠不讓使用者看到 traceback**（推廣鐵則）。
#"""
#from __future__ import annotations
#
#import os
#from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
#
#from PySide6.QtCore import Qt, Signal
#from PySide6.QtWidgets import (
#    QAbstractButton,
#    QButtonGroup,
#    QCheckBox,
#    QComboBox,
#    QDialog,
#    QDialogButtonBox,
#    QDoubleSpinBox,
#    QFileDialog,
#    QGroupBox,
#    QHBoxLayout,
#    QLabel,
#    QLineEdit,
#    QListWidget,
#    QListWidgetItem,
#    QMessageBox,
#    QProgressBar,
#    QPushButton,
#    QRadioButton,
#    QScrollArea,
#    QSpinBox,
#    QTextEdit,
#    QVBoxLayout,
#    QWidget,
#)
#
#from adept.core.export import (
#    ExportError,
#    apply_writeback,
#    feature_keys,
#    plan_writeback,
#    render_overlay,
#    write_csv,
#    write_excel,
#    write_png,
#)
#
#from .workers import _ThreadedWorker  # 同一套一次性 QThread 樣式（別另外發明一種）
#
#__all__ = [
#    "ExportDialog", "ExportWorker", "run_export_job",
#    "INPLACE_COLUMNS", "MODES", "MODE_LABELS", "MODE_HELP",
#    "OVERLAY_PREFIX", "DEFAULT_SIZE_FEATURE",
#]
#
##: 寫回模式（順序 = 畫面上的順序）。
#MODES = ("inplace", "annotate", "topn")
#
#MODE_LABELS = {
#    "inplace": "Edit in place (lossless)",
#    "annotate": "Save as new file (with score columns)",
#    "topn": "Top-N as new file",
#}
#
#MODE_HELP = {
#    "inplace": "Only touches columns this KLARF already has; every other byte is identical to the original.",
#    "annotate": "Writes a new KLARF with extra ADCSCORE / ADCCLASS columns; the original is untouched.",
#    "topn": "Writes a new KLARF keeping only the highest-scoring defects (or those above a threshold).",
#}
#
##: inplace 模式支援的四個目標欄位（實際有沒有這一欄，看載入的 KLARF）。
#INPLACE_COLUMNS = ("CLASSNUMBER", "ROUGHBINNUMBER", "FINEBINNUMBER", "DSIZE")
#
##: 這兩欄是「bin 寫去哪」的二選一（core 的 inplace 一次只吃一個 bin 欄）。
#_BIN_COLUMNS = ("ROUGHBINNUMBER", "FINEBINNUMBER")
#
##: DSIZE 預設寫哪個特徵。
#DEFAULT_SIZE_FEATURE = "cd_x_nm"
#
##: 疊圖檔名前綴。
#OVERLAY_PREFIX = "overlay_"
#
#_NO_BIN_COL = "(do not write a bin column)"
#_LEVEL_MARK = {"error": "✗", "warn": "△", "info": "✓"}
#
#
## --------------------------------------------------------------------------- #
## Qt-free：真正做事的部分（背景執行緒與測試都走這裡）
## --------------------------------------------------------------------------- #
#def _safe_name(text: Any) -> str:
#    """defect_id → 可以當檔名的字串。"""
#    out = []
#    for ch in str(text):
#        out.append(ch if (ch.isalnum() or ch in "-_") else "_")
#    return "".join(out) or "unknown"
#
#
#def _overlay_images(item: Any, recipe: Any, kind: str
#                    ) -> Tuple[Dict[str, Any], Dict[str, Any], Any]:
#    """一顆 defect 的疊圖素材 ``(images, features, blobs)``。
#
#    有 recipe 就跑一次 :func:`~adept.core.pipeline.run_defect`（``keep_context``），
#    這樣 diff / blobs 都在，疊圖才是「機器看到的東西」；跑不出影像（或沒有
#    recipe）就退回直接讀原始 channel（test → single → 第一個有的）。
#    """
#    from adept.core.pipeline import run_defect     # 延後匯入：對話框開啟才需要
#
#    if recipe is not None and item is not None:
#        r = run_defect(recipe, item, str(kind), keep_context=True)
#        ctx = getattr(r, "context", None)
#        images = dict(getattr(ctx, "images", {}) or {}) if ctx is not None else {}
#        if images:
#            blobs = (ctx.meta or {}).get("blobs") if ctx is not None else None
#            return images, dict(getattr(r, "features", {}) or {}), blobs
#
#    channels = list(getattr(item, "images", {}) or {})
#    images = {}
#    for ch in channels:
#        try:
#            images[ch] = item.load(ch)
#        except Exception:            # noqa: BLE001 — 單顆讀不出來不該殺掉整批
#            continue
#    return images, {}, None
#
#
#def _overlay_label(result: Dict[str, Any]) -> str:
#    """疊圖左上角那一行（cv2 的字型沒有中文，這裡刻意只用 ASCII）。"""
#    parts = ["#%s" % result.get("defect_id", "?")]
#    s = result.get("score")
#    if s is not None:
#        try:
#            parts.append("score=%.3f" % float(s))
#        except (TypeError, ValueError):
#            pass
#    b = result.get("bin")
#    if b is not None:
#        parts.append("bin=%d" % int(b))
#    return "  ".join(parts)
#
#
#def pick_overlay_results(results: Sequence[Dict[str, Any]], limit: int
#                         ) -> List[Dict[str, Any]]:
#    """依分數由高到低取前 ``limit`` 顆（沒有分數的排最後）。"""
#    rows = [r for r in (results or []) if r.get("ok", True)] or list(results or [])
#
#    def key(r: Dict[str, Any]) -> Tuple[int, float]:
#        s = r.get("score")
#        try:
#            return (0, -float(s))
#        except (TypeError, ValueError):
#            return (1, 0.0)
#
#    rows = sorted(rows, key=key)
#    n = max(0, int(limit))
#    return rows[:n] if n else rows
#
#
#def run_export_job(spec: Dict[str, Any],
#                   progress: Optional[Callable[[int, int, str], None]] = None
#                   ) -> Dict[str, Any]:
#    """真的寫檔（**Qt-free**）。回傳摘要 dict，:class:`ExportError` 直接往外丟。
#
#    ``spec``::
#
#        {
#          "klarf":   {"doc":…, "results":[…], "mode":"annotate",
#                      "out_path":"…", "opts":{…}}          # 或 None
#          "csv":     "path.csv" 或 None,
#          "excel":   {"path":…, "recipe":…, "ground_truth":…} 或 None,
#          "overlay": {"dir":…, "results":[…], "items":{id: DefectItem},
#                      "recipe":…, "kind":"ebi_patch"} 或 None,
#          "results": [...]        # csv / excel 用的結果
#        }
#
#    回傳 ``{"outputs": [路徑…], "notes": [白話…], "plan": WriteBackPlan|None,
#    "n_overlays": int, "n_overlay_failed": int}``。
#    """
#    spec = dict(spec or {})
#    results = list(spec.get("results") or [])
#    outputs: List[str] = []
#    notes: List[str] = []
#    plan = None
#
#    steps = [k for k in ("klarf", "csv", "excel", "overlay") if spec.get(k)]
#    total = max(1, len(steps))
#    done = 0
#
#    def tick(msg: str) -> None:
#        if progress is not None:
#            progress(done, total, msg)
#
#    tick("Preparing export…")
#
#    kl = spec.get("klarf")
#    if kl:
#        tick("Writing KLARF…")
#        plan = apply_writeback(kl["doc"], list(kl.get("results") or results),
#                               str(kl["mode"]), str(kl["out_path"]),
#                               **dict(kl.get("opts") or {}))
#        outputs.append(str(kl["out_path"]))
#        notes.append("KLARF (%s): %d rows changed, %d rows written."
#                     % (MODE_LABELS.get(plan.mode, plan.mode),
#                        plan.n_rows_changed, plan.n_rows_out))
#        done += 1
#
#    csv_path = spec.get("csv")
#    if csv_path:
#        tick("Writing CSV…")
#        outputs.append(write_csv(results, str(csv_path)))
#        notes.append("CSV: %d detail rows." % len(results))
#        done += 1
#
#    xl = spec.get("excel")
#    if xl:
#        tick("Writing Excel…")
#        path = write_excel(results, str(xl["path"]),
#                           recipe=xl.get("recipe"),
#                           ground_truth=xl.get("ground_truth"))
#        outputs.append(path)
#        notes.append("Excel: Summary / Details / Feature stats worksheets.")
#        done += 1
#
#    ov = spec.get("overlay")
#    n_ok = n_fail = 0
#    if ov:
#        rows = list(ov.get("results") or [])
#        items = dict(ov.get("items") or {})
#        out_dir = str(ov["dir"])
#        recipe = ov.get("recipe")
#        kind = str(ov.get("kind") or "")
#        total = max(1, len(steps) - 1 + len(rows))
#        for i, r in enumerate(rows, 1):
#            did = str(r.get("defect_id", ""))
#            tick("Overlay %d / %d (#%s)" % (i, len(rows), did))
#            item = items.get(did)
#            try:
#                images, feats, blobs = _overlay_images(item, recipe, kind)
#                if not images:
#                    n_fail += 1
#                    continue
#                merged = dict(feats)
#                merged.update(r.get("features") or {})
#                panel = render_overlay(images, merged, blobs=blobs,
#                                       label=_overlay_label(r))
#                write_png(panel, os.path.join(
#                    out_dir, "%s%s.png" % (OVERLAY_PREFIX, _safe_name(did))))
#            except ExportError:
#                raise
#            except Exception:        # noqa: BLE001 — 單顆畫不出來不該殺掉整批
#                n_fail += 1
#            else:
#                n_ok += 1
#                done += 1
#        outputs.append(out_dir)
#        notes.append("Overlays: %d written to %s." % (n_ok, out_dir))
#        if n_fail:
#            notes.append("Skipped %d defects whose overlay could not be drawn (usually unreadable images)."
#                         % n_fail)
#
#    if progress is not None:
#        progress(total, total, "Done")
#    return {"outputs": outputs, "notes": notes, "plan": plan,
#            "n_overlays": n_ok, "n_overlay_failed": n_fail}
#
#
## --------------------------------------------------------------------------- #
## 背景工作
## --------------------------------------------------------------------------- #
#class ExportWorker(_ThreadedWorker):
#    """在背景跑 :func:`run_export_job`。
#
#    訊號：``progress(done, total, 說明)``、``done(dict)``、``failed(str)``。
#    失敗訊息已經是白話（:class:`ExportError` 的訊息原樣帶出），UI 直接顯示即可。
#    """
#
#    progress = Signal(int, int, str)
#    done = Signal(object)
#    failed = Signal(str)
#
#    def start(self, spec: Dict[str, Any]) -> bool:
#        """開背景執行緒輸出；已有工作在跑時回傳 False（不排隊）。"""
#        if self.is_running():
#            return False
#        payload = dict(spec or {})
#
#        def emit_progress(d: int, t: int, msg: str) -> None:
#            self.progress.emit(int(d), int(t), str(msg))
#
#        def job() -> None:
#            try:
#                out = run_export_job(payload, emit_progress)
#            except ExportError as e:
#                self.failed.emit(str(e))
#            except Exception as e:      # noqa: BLE001 — UI 邊界，一律翻成訊息
#                self.failed.emit("%s: %s" % (type(e).__name__, e))
#            else:
#                self.done.emit(out)
#
#        self._start_job(job)
#        return True
#
#
## --------------------------------------------------------------------------- #
## 對話框
## --------------------------------------------------------------------------- #
#class ExportDialog(QDialog):
#    """輸出精靈（KLARF 寫回 / 報表 / 疊圖）。
#
#    測試友善 API（完全不開檔案對話框、不跳訊息框）::
#
#        dlg = ExportDialog(results, doc=doc, dataset=ds, recipe=recipe)
#        dlg.set_mode("inplace")
#        dlg.column_control("DSIZE").isEnabled()      # 這份 KLARF 沒這欄 → False
#        dlg.column_hint("DSIZE")                     # 為什麼不能選
#        dlg.preview_plan()                           # 乾跑 → 計畫書文字
#        dlg.plan_text()                              # 白話 + ✓/△/✗
#        dlg.btn_write.isEnabled()                    # 預覽成功後才是 True
#        dlg.run_export(sync=True)                    # 真的寫（同步）
#    """
#
#    #: 輸出完成（不論同步或背景）—— 主視窗接這個更新狀態列。
#    exported = Signal(object)
#
#    def __init__(self, results: Sequence[Dict[str, Any]],
#                 doc: Any = None, *,
#                 dataset: Any = None,
#                 recipe: Any = None,
#                 ground_truth: Optional[Dict[Any, Any]] = None,
#                 default_dir: Optional[str] = None,
#                 parent: Optional[QWidget] = None) -> None:
#        super().__init__(parent)
#        self.setWindowTitle("Export…")
#        self.setMinimumSize(720, 560)
#
#        self.results: List[Dict[str, Any]] = list(results or [])
#        self.doc = doc
#        self.dataset = dataset
#        self.recipe = recipe
#        self.ground_truth = ground_truth
#        self._plan: Any = None
#        self._plan_text = ""
#        self._error_text = ""
#        self._summary: Optional[Dict[str, Any]] = None
#        self._interactive = False        # True = 使用者按按鈕（可以跳訊息框）
#        # 組介面的過程中 setChecked() 會觸發 toggled，但那時候別的 widget 還沒
#        # 生出來 —— 這面旗子讓所有 slot 在組裝期間安靜地跳過。
#        self._building = True
#        self._col_controls: Dict[str, QAbstractButton] = {}
#        self._col_hints: Dict[str, QLabel] = {}
#
#        self._features = feature_keys(self.results)
#        self._columns = [str(c) for c in (getattr(doc, "defect_columns", None) or [])]
#        self._dir = str(default_dir or self._guess_dir())
#        self._stem = self._guess_stem()
#
#        self.worker = ExportWorker(self)
#        self.worker.progress.connect(self._on_progress)
#        self.worker.done.connect(self._on_done)
#        self.worker.failed.connect(self._on_failed)
#
#        self._build_ui()
#        self._building = False
#        self._sync_mode_pages()
#        self._update_write_enabled()
#
#    # ==================================================================== #
#    # 預設值
#    # ==================================================================== #
#    def _guess_dir(self) -> str:
#        src = getattr(self.doc, "source_path", None)
#        if src:
#            return os.path.dirname(os.path.abspath(str(src)))
#        return os.getcwd()
#
#    def _guess_stem(self) -> str:
#        src = getattr(self.doc, "source_path", None)
#        if src:
#            return os.path.splitext(os.path.basename(str(src)))[0]
#        return "adept"
#
#    def _default_path(self, suffix: str) -> str:
#        return os.path.join(self._dir, self._stem + suffix)
#
#    # ==================================================================== #
#    # 介面
#    # ==================================================================== #
#    def _build_ui(self) -> None:
#        outer = QVBoxLayout(self)
#        outer.setContentsMargins(10, 10, 10, 10)
#        outer.setSpacing(8)
#
#        head = QLabel("This batch has %d defect results — what would you like to export?" % len(self.results),
#                      self)
#        head.setObjectName("paramTitle")
#        outer.addWidget(head)
#
#        scroll = QScrollArea(self)
#        scroll.setWidgetResizable(True)
#        body = QWidget(scroll)
#        lay = QVBoxLayout(body)
#        lay.setContentsMargins(2, 2, 2, 2)
#        lay.setSpacing(10)
#        lay.addWidget(self._build_klarf_group())
#        lay.addWidget(self._build_report_group())
#        lay.addWidget(self._build_overlay_group())
#        lay.addStretch(1)
#        scroll.setWidget(body)
#        outer.addWidget(scroll, 1)
#
#        self.progress_bar = QProgressBar(self)
#        self.progress_bar.setRange(0, 100)
#        self.progress_bar.setValue(0)
#        self.progress_bar.setVisible(False)
#        outer.addWidget(self.progress_bar)
#
#        self.status_label = QLabel("", self)
#        self.status_label.setObjectName("paramHint")
#        self.status_label.setWordWrap(True)
#        outer.addWidget(self.status_label)
#
#        buttons = QDialogButtonBox(self)
#        self.btn_write = QPushButton("Write", self)
#        self.btn_write.setObjectName("primary")
#        self.btn_write.setToolTip("Unlocked once you have pressed “Preview changes”")
#        self.btn_write.clicked.connect(self._on_write_clicked)
#        self.btn_close = QPushButton("Close", self)
#        self.btn_close.clicked.connect(self.reject)
#        buttons.addButton(self.btn_write, QDialogButtonBox.AcceptRole)
#        buttons.addButton(self.btn_close, QDialogButtonBox.RejectRole)
#        outer.addWidget(buttons)
#
#    # ---- (a) KLARF ------------------------------------------------------
#    def _build_klarf_group(self) -> QWidget:
#        box = QGroupBox("(a) Write back to KLARF", self)
#        lay = QVBoxLayout(box)
#        lay.setSpacing(6)
#
#        self.chk_klarf = QCheckBox("Write the ADC verdict back to KLARF", box)
#        self.chk_klarf.setChecked(self.doc is not None)
#        self.chk_klarf.setEnabled(self.doc is not None)
#        if self.doc is None:
#            self.chk_klarf.setToolTip("No KLARF loaded — nothing to write back to.")
#            hint = QLabel("(No KLARF loaded — use “Open KLARF…” in the main window first)", box)
#            hint.setObjectName("paramHint")
#            lay.addWidget(self.chk_klarf)
#            lay.addWidget(hint)
#        else:
#            lay.addWidget(self.chk_klarf)
#        self.chk_klarf.toggled.connect(self._invalidate_plan)
#
#        self.mode_group = QButtonGroup(box)
#        self.mode_buttons: Dict[str, QRadioButton] = {}
#        for mode in MODES:
#            rb = QRadioButton(MODE_LABELS[mode], box)
#            rb.setToolTip(MODE_HELP[mode])
#            self.mode_group.addButton(rb)
#            self.mode_buttons[mode] = rb
#            lay.addWidget(rb)
#            help_label = QLabel("    " + MODE_HELP[mode], box)
#            help_label.setObjectName("paramHint")
#            help_label.setWordWrap(True)
#            lay.addWidget(help_label)
#            rb.toggled.connect(self._on_mode_toggled)
#        self.mode_buttons["inplace"].setChecked(True)
#
#        self.page_inplace = self._build_inplace_page(box)
#        self.page_annotate = self._build_annotate_page(box)
#        self.page_topn = self._build_topn_page(box)
#        for page in (self.page_inplace, self.page_annotate, self.page_topn):
#            lay.addWidget(page)
#
#        row = QHBoxLayout()
#        row.addWidget(QLabel("Output file", box))
#        self.edit_klarf_out = QLineEdit(self._default_path("_adc.001"), box)
#        self.edit_klarf_out.setToolTip("Where the new KLARF goes (the original is not overwritten by default)")
#        self.edit_klarf_out.textChanged.connect(self._invalidate_plan)
#        row.addWidget(self.edit_klarf_out, 1)
#        btn = QPushButton("Browse…", box)
#        btn.clicked.connect(self._pick_klarf_out)
#        row.addWidget(btn)
#        lay.addLayout(row)
#
#        prow = QHBoxLayout()
#        self.btn_preview = QPushButton("Preview changes", box)
#        self.btn_preview.setToolTip("Dry run: shows exactly how many rows and "
#                                    "which columns change. “Write” unlocks "
#                                    "afterwards.")
#        self.btn_preview.clicked.connect(self._on_preview_clicked)
#        prow.addWidget(self.btn_preview)
#        prow.addStretch(1)
#        lay.addLayout(prow)
#
#        self.plan_view = QTextEdit(box)
#        self.plan_view.setReadOnly(True)
#        self.plan_view.setMinimumHeight(150)
#        self.plan_view.setPlaceholderText(
#            "Press “Preview changes” to see what this would do (no file is written).")
#        lay.addWidget(self.plan_view)
#        return box
#
#    def _column_row(self, parent: QWidget, name: str,
#                    control: QAbstractButton, what: str) -> QWidget:
#        """一列欄位選擇器：控制項 + 白話說明；欄位不存在就變灰並寫明原因。"""
#        row = QWidget(parent)
#        h = QHBoxLayout(row)
#        h.setContentsMargins(0, 0, 0, 0)
#        h.setSpacing(8)
#        h.addWidget(control)
#        hint = QLabel("", row)
#        hint.setObjectName("paramHint")
#        hint.setWordWrap(True)
#        if name in self._columns:
#            hint.setText(what)
#        else:
#            control.setEnabled(False)
#            control.setChecked(False)
#            hint.setText("This KLARF has no “%s” column — use “Save as new file "
#                         "(with score columns)” to add one." % name)
#            control.setToolTip(hint.text())
#        h.addWidget(hint, 1)
#        self._col_controls[name] = control
#        self._col_hints[name] = hint
#        return row
#
#    def _build_inplace_page(self, parent: QWidget) -> QWidget:
#        page = QWidget(parent)
#        lay = QVBoxLayout(page)
#        lay.setContentsMargins(16, 2, 2, 2)
#        lay.setSpacing(4)
#
#        head = QLabel("Which existing columns should the verdict go into? (none selected = output identical to the original)",
#                      page)
#        head.setObjectName("paramHint")
#        head.setWordWrap(True)
#        lay.addWidget(head)
#
#        self.chk_class_col = QCheckBox("CLASSNUMBER", page)
#        self.chk_class_col.toggled.connect(self._invalidate_plan)
#        lay.addWidget(self._column_row(page, "CLASSNUMBER", self.chk_class_col,
#                                       "Write the bin into the class column (the one downstream review stations read most)."))
#
#        self.rb_no_bin_col = QRadioButton(_NO_BIN_COL, page)
#        self.rb_no_bin_col.setChecked(True)
#        self.rb_no_bin_col.setToolTip("Only one bin column can be written at a time (a limit of the KLARF writer)")
#        self.rb_no_bin_col.toggled.connect(self._invalidate_plan)
#        lay.addWidget(self.rb_no_bin_col)
#
#        self.bin_col_group = QButtonGroup(page)
#        self.bin_col_group.addButton(self.rb_no_bin_col)
#        for name, what in (
#                ("ROUGHBINNUMBER", "Write the bin into the coarse bin column."),
#                ("FINEBINNUMBER", "Write the bin into the fine bin column.")):
#            rb = QRadioButton(name, page)
#            rb.toggled.connect(self._invalidate_plan)
#            self.bin_col_group.addButton(rb)
#            lay.addWidget(self._column_row(page, name, rb, what))
#
#        self.chk_size_col = QCheckBox("DSIZE", page)
#        self.chk_size_col.toggled.connect(self._invalidate_plan)
#        lay.addWidget(self._column_row(
#            page, "DSIZE", self.chk_size_col, "Write the measured size feature into the size column."))
#
#        srow = QHBoxLayout()
#        srow.addWidget(QLabel("   Size feature", page))
#        self.size_feature_combo = QComboBox(page)
#        self.size_feature_combo.setToolTip("Which feature value goes into DSIZE")
#        for name in (self._features or [DEFAULT_SIZE_FEATURE]):
#            self.size_feature_combo.addItem(name)
#        if DEFAULT_SIZE_FEATURE in self._features:
#            self.size_feature_combo.setCurrentText(DEFAULT_SIZE_FEATURE)
#        self.size_feature_combo.currentIndexChanged.connect(self._invalidate_plan)
#        srow.addWidget(self.size_feature_combo, 1)
#        lay.addLayout(srow)
#        return page
#
#    def _build_annotate_page(self, parent: QWidget) -> QWidget:
#        page = QWidget(parent)
#        lay = QVBoxLayout(page)
#        lay.setContentsMargins(16, 2, 2, 2)
#        lay.setSpacing(4)
#
#        head = QLabel("Adds two columns: ADCSCORE (score) and ADCCLASS (bin). "
#                      "Pick any extra feature columns below.", page)
#        head.setObjectName("paramHint")
#        head.setWordWrap(True)
#        lay.addWidget(head)
#
#        self.feature_list = QListWidget(page)
#        self.feature_list.setToolTip("Each ticked feature becomes its own KLARF column")
#        self.feature_list.setMaximumHeight(140)
#        for name in self._features:
#            it = QListWidgetItem(str(name), self.feature_list)
#            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
#            it.setCheckState(Qt.Unchecked)
#        if not self._features:
#            self.feature_list.setEnabled(False)
#            empty = QLabel("(this batch has no features to pick from)", page)
#            empty.setObjectName("paramHint")
#            lay.addWidget(self.feature_list)
#            lay.addWidget(empty)
#        else:
#            lay.addWidget(self.feature_list)
#        self.feature_list.itemChanged.connect(lambda _i: self._invalidate_plan())
#        return page
#
#    def _build_topn_page(self, parent: QWidget) -> QWidget:
#        page = QWidget(parent)
#        lay = QVBoxLayout(page)
#        lay.setContentsMargins(16, 2, 2, 2)
#        lay.setSpacing(4)
#
#        row1 = QHBoxLayout()
#        row1.addWidget(QLabel("Keep top", page))
#        self.spin_topn = QSpinBox(page)
#        self.spin_topn.setRange(0, 1000000)
#        self.spin_topn.setValue(min(100, max(1, len(self.results))))
#        self.spin_topn.setToolTip("Keep this many defects by descending score; 0 = use the score threshold below instead")
#        self.spin_topn.valueChanged.connect(self._invalidate_plan)
#        row1.addWidget(self.spin_topn)
#        row1.addStretch(1)
#        lay.addLayout(row1)
#
#        row2 = QHBoxLayout()
#        self.chk_min_score = QCheckBox("Use a score threshold (>=) instead", page)
#        self.chk_min_score.setToolTip("Tick to keep every defect whose score is greater than or equal to this value")
#        self.chk_min_score.toggled.connect(self._invalidate_plan)
#        row2.addWidget(self.chk_min_score)
#        self.spin_min_score = QDoubleSpinBox(page)
#        self.spin_min_score.setDecimals(3)
#        self.spin_min_score.setRange(-1e9, 1e9)
#        self.spin_min_score.valueChanged.connect(self._invalidate_plan)
#        row2.addWidget(self.spin_min_score)
#        row2.addStretch(1)
#        lay.addLayout(row2)
#
#        self.chk_renumber = QCheckBox("Renumber DEFECTID as 1, 2, 3…", page)
#        self.chk_renumber.setChecked(True)
#        self.chk_renumber.setToolTip(
#            "Keeping a subset leaves gaps in the ids; tick to renumber. Note: "
#            "TIFF page numbers are not renumbered (this tool never touches the "
#            "original images).")
#        self.chk_renumber.toggled.connect(self._invalidate_plan)
#        lay.addWidget(self.chk_renumber)
#
#        self.chk_topn_annotate = QCheckBox("Also add ADCSCORE / ADCCLASS columns", page)
#        self.chk_topn_annotate.setChecked(True)
#        self.chk_topn_annotate.toggled.connect(self._invalidate_plan)
#        lay.addWidget(self.chk_topn_annotate)
#        return page
#
#    # ---- (b) 報表 --------------------------------------------------------
#    def _build_report_group(self) -> QWidget:
#        box = QGroupBox("(b) Reports", self)
#        lay = QVBoxLayout(box)
#        lay.setSpacing(6)
#
#        self.chk_csv = QCheckBox("CSV details (one row per defect, all features)", box)
#        self.chk_csv.toggled.connect(self._on_any_output_toggled)
#        lay.addWidget(self.chk_csv)
#        self.edit_csv_out, csv_row = self._path_row(
#            box, self._default_path("_features.csv"), "Choose where the CSV goes",
#            self._pick_csv_out)
#        lay.addLayout(csv_row)
#
#        self.chk_excel = QCheckBox("Excel report (Summary / Details / Feature stats)", box)
#        self.chk_excel.toggled.connect(self._on_any_output_toggled)
#        lay.addWidget(self.chk_excel)
#        self.edit_excel_out, xl_row = self._path_row(
#            box, self._default_path("_report.xlsx"), "Choose where the Excel file goes",
#            self._pick_excel_out)
#        lay.addLayout(xl_row)
#        return box
#
#    # ---- (c) 疊圖 --------------------------------------------------------
#    def _build_overlay_group(self) -> QWidget:
#        box = QGroupBox("(c) Overlay images", self)
#        lay = QVBoxLayout(box)
#        lay.setSpacing(6)
#
#        self.chk_overlay = QCheckBox("Write overlay PNGs (the main blob boxed in red)", box)
#        self.chk_overlay.toggled.connect(self._on_any_output_toggled)
#        lay.addWidget(self.chk_overlay)
#
#        row = QHBoxLayout()
#        row.addWidget(QLabel("Draw at most", box))
#        self.spin_overlay_limit = QSpinBox(box)
#        self.spin_overlay_limit.setRange(1, 100000)
#        self.spin_overlay_limit.setValue(min(50, max(1, len(self.results))))
#        self.spin_overlay_limit.setToolTip("Draw this many defects by descending score (drawing is slow)")
#        row.addWidget(self.spin_overlay_limit)
#        row.addStretch(1)
#        lay.addLayout(row)
#
#        self.edit_overlay_dir, orow = self._path_row(
#            box, os.path.join(self._dir, "overlay"), "Choose the overlay output folder",
#            self._pick_overlay_dir)
#        lay.addLayout(orow)
#
#        hint = QLabel("Overlays re-run the pipeline to obtain diff and blob; without a recipe only the raw image is drawn.",
#                      box)
#        hint.setObjectName("paramHint")
#        hint.setWordWrap(True)
#        lay.addWidget(hint)
#        return box
#
#    def _path_row(self, parent: QWidget, default: str, tip: str,
#                  slot: Callable[[], None]) -> Tuple[QLineEdit, QHBoxLayout]:
#        row = QHBoxLayout()
#        edit = QLineEdit(default, parent)
#        edit.setToolTip(tip)
#        row.addWidget(edit, 1)
#        btn = QPushButton("Browse…", parent)
#        btn.setToolTip(tip)
#        btn.clicked.connect(slot)
#        row.addWidget(btn)
#        return edit, row
#
#    # ==================================================================== #
#    # 模式切換 / 計畫作廢
#    # ==================================================================== #
#    def _on_mode_toggled(self, _checked: bool) -> None:
#        if self._building:
#            return
#        self._sync_mode_pages()
#        self._invalidate_plan()
#
#    def _sync_mode_pages(self) -> None:
#        mode = self.mode()
#        self.page_inplace.setVisible(mode == "inplace")
#        self.page_annotate.setVisible(mode == "annotate")
#        self.page_topn.setVisible(mode == "topn")
#
#    def _on_any_output_toggled(self, _checked: bool = False) -> None:
#        if self._building:
#            return
#        self._update_write_enabled()
#
#    def _invalidate_plan(self, *_args: Any) -> None:
#        """任何設定被動過 → 之前的預覽作廢，「寫出」立刻鎖回去。"""
#        if self._building:
#            return
#        if self._plan is not None or self._plan_text:
#            self.plan_view.setPlainText(
#                "Settings changed — press “Preview changes” again to confirm what this version would do.")
#        self._plan = None
#        self._plan_text = ""
#        self._update_write_enabled()
#
#    def _update_write_enabled(self) -> None:
#        has_report = bool(self.chk_csv.isChecked() or self.chk_excel.isChecked()
#                          or self.chk_overlay.isChecked())
#        if self._klarf_enabled():
#            self.btn_write.setEnabled(self._plan is not None)
#        else:
#            self.btn_write.setEnabled(has_report)
#
#    def _klarf_enabled(self) -> bool:
#        return bool(self.doc is not None and self.chk_klarf.isChecked())
#
#    # ==================================================================== #
#    # 對外（測試 / 主視窗都走這裡）
#    # ==================================================================== #
#    def mode(self) -> str:
#        """目前選的寫回模式。"""
#        for name, rb in self.mode_buttons.items():
#            if rb.isChecked():
#                return name
#        return MODES[0]
#
#    def set_mode(self, mode: str) -> bool:
#        """切換寫回模式（認不得的模式回 False，不炸）。"""
#        mode = str(mode)
#        rb = self.mode_buttons.get(mode)
#        if rb is None:
#            return False
#        rb.setChecked(True)
#        self._sync_mode_pages()
#        return True
#
#    def column_control(self, name: str) -> Optional[QAbstractButton]:
#        """inplace 模式中某個欄位的控制項（欄位不存在時它是 disabled 的）。"""
#        return self._col_controls.get(str(name))
#
#    def column_enabled(self, name: str) -> bool:
#        ctrl = self.column_control(name)
#        return bool(ctrl is not None and ctrl.isEnabled())
#
#    def column_hint(self, name: str) -> str:
#        """該欄位旁邊那一行白話說明（欄位不存在時說明為什麼不能選）。"""
#        lbl = self._col_hints.get(str(name))
#        return "" if lbl is None else lbl.text()
#
#    def klarf_columns(self) -> List[str]:
#        """載入的 KLARF 實際有的 defect 欄位。"""
#        return list(self._columns)
#
#    def feature_names(self) -> List[str]:
#        """annotate 可選的特徵欄名（= 這批結果出現過的特徵）。"""
#        return list(self._features)
#
#    def selected_features(self) -> List[str]:
#        out = []
#        for i in range(self.feature_list.count()):
#            it = self.feature_list.item(i)
#            if it.checkState() == Qt.Checked:
#                out.append(it.text())
#        return out
#
#    def set_selected_features(self, names: Sequence[str]) -> None:
#        want = {str(n) for n in (names or [])}
#        for i in range(self.feature_list.count()):
#            it = self.feature_list.item(i)
#            it.setCheckState(Qt.Checked if it.text() in want else Qt.Unchecked)
#
#    def set_output_path(self, kind: str, path: Any) -> bool:
#        """設定輸出路徑（``klarf`` / ``csv`` / ``excel`` / ``overlay``）。"""
#        edits = {"klarf": self.edit_klarf_out, "csv": self.edit_csv_out,
#                 "excel": self.edit_excel_out, "overlay": self.edit_overlay_dir}
#        edit = edits.get(str(kind))
#        if edit is None:
#            return False
#        edit.setText(str(path))
#        return True
#
#    def output_path(self, kind: str) -> str:
#        edits = {"klarf": self.edit_klarf_out, "csv": self.edit_csv_out,
#                 "excel": self.edit_excel_out, "overlay": self.edit_overlay_dir}
#        edit = edits.get(str(kind))
#        return "" if edit is None else edit.text().strip()
#
#    def plan(self) -> Any:
#        """最近一次成功預覽的 :class:`WriteBackPlan`（沒有就是 None）。"""
#        return self._plan
#
#    def plan_text(self) -> str:
#        """計畫書的白話文字（預覽失敗或還沒預覽時為空字串）。"""
#        return self._plan_text
#
#    def error_text(self) -> str:
#        """最近一次的錯誤訊息（白話；沒有錯誤就是空字串）。"""
#        return self._error_text
#
#    def summary(self) -> Optional[Dict[str, Any]]:
#        """最近一次輸出的摘要 dict。"""
#        return self._summary
#
#    def summary_text(self) -> str:
#        return self.status_label.text()
#
#    # ---- 預覽 ------------------------------------------------------------
#    def writeback_options(self) -> Dict[str, Any]:
#        """目前畫面設定 → :func:`plan_writeback` / :func:`apply_writeback` 的選項。"""
#        mode = self.mode()
#        if mode == "inplace":
#            opts: Dict[str, Any] = {}
#            if self.chk_class_col.isChecked():
#                opts["class_col"] = "CLASSNUMBER"
#            for name in _BIN_COLUMNS:
#                ctrl = self._col_controls.get(name)
#                if ctrl is not None and ctrl.isChecked():
#                    opts["bin_col"] = name
#                    break
#            if self.chk_size_col.isChecked():
#                opts["size_col"] = "DSIZE"
#                opts["size_feature"] = self.size_feature_combo.currentText()
#            return opts
#        if mode == "annotate":
#            return {"extra_features": self.selected_features()}
#        n = int(self.spin_topn.value())
#        opts = {"renumber": bool(self.chk_renumber.isChecked()),
#                "include_annotations": bool(self.chk_topn_annotate.isChecked())}
#        if self.chk_min_score.isChecked():
#            opts["n"] = 0
#            opts["min_score"] = float(self.spin_min_score.value())
#        else:
#            opts["n"] = n
#        if self.chk_topn_annotate.isChecked():
#            opts["extra_features"] = self.selected_features()
#        return opts
#
#    def preview_plan(self) -> Any:
#        """乾跑 :func:`plan_writeback`，把計畫書渲染成白話；失敗回 None。
#
#        成功之後「寫出」才會開放 —— 使用者一定先看過會發生什麼事。
#        """
#        self._error_text = ""
#        if not self._klarf_enabled():
#            self._fail("Nothing to write back — tick “Write the ADC verdict back to KLARF” first.")
#            return None
#        try:
#            plan = plan_writeback(self.doc, self.results, self.mode(),
#                                  **self.writeback_options())
#        except ExportError as e:
#            self._plan = None
#            self._plan_text = ""
#            self.plan_view.setPlainText("✗ These settings cannot be written:\n\n%s" % e)
#            self._fail(str(e))
#            self._update_write_enabled()
#            return None
#        except Exception as e:          # noqa: BLE001 — UI 邊界，絕不吐 traceback
#            self._plan = None
#            self._plan_text = ""
#            msg = "%s: %s" % (type(e).__name__, e)
#            self.plan_view.setPlainText("✗ Preview failed:\n\n%s" % msg)
#            self._fail(msg)
#            self._update_write_enabled()
#            return None
#
#        self._plan = plan
#        self._plan_text = describe_plan(plan, self.output_path("klarf"))
#        self.plan_view.setPlainText(self._plan_text)
#        self.status_label.setText("Preview done — check the plan above, then press “Write”.")
#        self._update_write_enabled()
#        return plan
#
#    def _on_preview_clicked(self) -> None:
#        self._interactive = True
#        try:
#            self.preview_plan()
#        finally:
#            self._interactive = False
#
#    # ---- 寫出 ------------------------------------------------------------
#    def export_spec(self) -> Dict[str, Any]:
#        """目前畫面設定 → :func:`run_export_job` 吃的 spec。"""
#        spec: Dict[str, Any] = {"results": self.results, "klarf": None,
#                                "csv": None, "excel": None, "overlay": None}
#        if self._klarf_enabled():
#            spec["klarf"] = {
#                "doc": self.doc,
#                "results": self.results,
#                "mode": self.mode(),
#                "out_path": self.output_path("klarf"),
#                "opts": self.writeback_options(),
#            }
#        if self.chk_csv.isChecked():
#            spec["csv"] = self.output_path("csv")
#        if self.chk_excel.isChecked():
#            spec["excel"] = {"path": self.output_path("excel"),
#                             "recipe": self.recipe,
#                             "ground_truth": self.ground_truth}
#        if self.chk_overlay.isChecked():
#            items = {}
#            for it in list(getattr(self.dataset, "items", []) or []):
#                items[str(getattr(it, "defect_id", ""))] = it
#            spec["overlay"] = {
#                "dir": self.output_path("overlay"),
#                "results": pick_overlay_results(
#                    self.results, int(self.spin_overlay_limit.value())),
#                "items": items,
#                "recipe": self.recipe,
#                "kind": str(getattr(self.dataset, "kind", "")),
#            }
#        return spec
#
#    def run_export(self, sync: bool = False) -> Optional[Dict[str, Any]]:
#        """開始輸出。``sync=True`` 直接在呼叫端跑完（測試 / CLI 用）。
#
#        回傳摘要 dict（同步）或 None（非同步已排入背景，或前置檢查沒過）。
#        """
#        self._error_text = ""
#        self._summary = None
#        if self._klarf_enabled() and self._plan is None:
#            self._fail("Press “Preview changes” first to see what would happen.")
#            return None
#        spec = self.export_spec()
#        if not any(spec.get(k) for k in ("klarf", "csv", "excel", "overlay")):
#            self._fail("Nothing is selected for export.")
#            return None
#        for key, label in (("csv", "CSV"), ("excel", "Excel")):
#            target = spec.get(key)
#            path = target if isinstance(target, str) else (target or {}).get("path")
#            if target and not str(path or "").strip():
#                self._fail("%s is selected but no output path was given." % label)
#                return None
#        if spec.get("klarf") and not str(spec["klarf"]["out_path"] or "").strip():
#            self._fail("KLARF write-back is selected but no output path was given.")
#            return None
#
#        if sync:
#            try:
#                out = run_export_job(spec)
#            except ExportError as e:
#                self._fail(str(e))
#                return None
#            except Exception as e:      # noqa: BLE001 — UI 邊界
#                self._fail("%s: %s" % (type(e).__name__, e))
#                return None
#            self._on_done(out)
#            return out
#
#        self.progress_bar.setVisible(True)
#        self.progress_bar.setRange(0, 0)         # 忙碌動畫，收到第一筆進度就換
#        self.btn_write.setEnabled(False)
#        if not self.worker.start(spec):
#            self.status_label.setText("An export is already running — please wait.")
#            return None
#        self.status_label.setText("Exporting…")
#        return None
#
#    def _on_write_clicked(self) -> None:
#        self._interactive = True
#        try:
#            self.run_export(sync=False)
#        finally:
#            self._interactive = False
#
#    # ---- worker 回呼 -----------------------------------------------------
#    def _on_progress(self, done: int, total: int, msg: str) -> None:
#        self.progress_bar.setVisible(True)
#        self.progress_bar.setRange(0, max(1, int(total)))
#        self.progress_bar.setValue(max(0, min(int(done), int(total))))
#        self.status_label.setText(str(msg))
#
#    def _on_done(self, summary: Any) -> None:
#        self._summary = dict(summary or {})
#        self.progress_bar.setVisible(False)
#        outputs = list(self._summary.get("outputs") or [])
#        notes = list(self._summary.get("notes") or [])
#        text = "Export finished:\n" + "\n".join("· " + n for n in notes)
#        if outputs:
#            text += "\nFiles:\n" + "\n".join("   " + p for p in outputs)
#        self.status_label.setText(text)
#        self._update_write_enabled()
#        self.exported.emit(self._summary)
#        if self._interactive:
#            QMessageBox.information(self, "Export finished", text)
#
#    def _on_failed(self, msg: str) -> None:
#        self.progress_bar.setVisible(False)
#        self._update_write_enabled()
#        self._fail(str(msg))
#
#    def _fail(self, msg: str) -> None:
#        """錯誤一律翻成白話：同步路徑存起來，互動路徑跳訊息框。"""
#        self._error_text = str(msg)
#        self.status_label.setText("⚠ %s" % msg)
#        if self._interactive:
#            QMessageBox.warning(self, "Cannot export", str(msg))
#
#    # ---- 檔案對話框（測試不走這條路）--------------------------------------
#    def _pick_klarf_out(self) -> None:
#        path, _ = QFileDialog.getSaveFileName(
#            self, "Export KLARF", self.output_path("klarf"),
#            "KLARF (*.001 *.klarf *.txt);;All files (*)")
#        if path:
#            self.set_output_path("klarf", path)
#
#    def _pick_csv_out(self) -> None:
#        path, _ = QFileDialog.getSaveFileName(
#            self, "Export CSV", self.output_path("csv"), "CSV (*.csv);;All files (*)")
#        if path:
#            self.set_output_path("csv", path)
#
#    def _pick_excel_out(self) -> None:
#        path, _ = QFileDialog.getSaveFileName(
#            self, "Export Excel", self.output_path("excel"),
#            "Excel (*.xlsx);;All files (*)")
#        if path:
#            self.set_output_path("excel", path)
#
#    def _pick_overlay_dir(self) -> None:
#        path = QFileDialog.getExistingDirectory(
#            self, "Choose the overlay output folder", self.output_path("overlay"))
#        if path:
#            self.set_output_path("overlay", path)
#
#    # ---- 關窗 ------------------------------------------------------------
#    def closeEvent(self, event) -> None:      # noqa: D102 - Qt hook
#        try:
#            self.worker.stop()
#        except Exception:                     # noqa: BLE001 — 關窗不准擋路
#            pass
#        super().closeEvent(event)
#
#
## --------------------------------------------------------------------------- #
## 計畫書 → 白話（Qt-free，方便單獨測）
## --------------------------------------------------------------------------- #
#def describe_plan(plan: Any, out_path: str = "") -> str:
#    """:class:`WriteBackPlan` → 使用者看得懂的一段字。
#
#    健檢結果用三種符號：``✓`` 沒問題 / ``△`` 提醒 / ``✗`` 會出事。
#    """
#    mode = getattr(plan, "mode", "?")
#    lines = ["Mode: %s" % MODE_LABELS.get(mode, mode)]
#    if out_path:
#        lines.append("Output file: %s" % out_path)
#    lines.append("")
#    lines.append("Rows changed: %d defects." % int(getattr(plan, "n_rows_changed", 0)))
#    touched = list(getattr(plan, "columns_touched", []) or [])
#    added = list(getattr(plan, "columns_added", []) or [])
#    lines.append("Existing columns touched: %s" % (", ".join(touched) if touched else "(none)"))
#    lines.append("Columns added: %s" % (", ".join(added) if added else "(none)"))
#    lines.append("The output file will have %d defect rows." % int(getattr(plan, "n_rows_out", 0)))
#
#    notes = list(getattr(plan, "notes", []) or [])
#    if notes:
#        lines.append("")
#        lines.append("Notes:")
#        lines.extend("· %s" % n for n in notes)
#
#    lines.append("")
#    lines.append("Output health check:")
#    issues = list(getattr(plan, "issues", []) or [])
#    if not issues:
#        lines.append("✓ No problems found.")
#    for it in issues:
#        level = str(getattr(it, "level", "info"))
#        mark = _LEVEL_MARK.get(level, "△")
#        title = str(getattr(it, "title", ""))
#        count = int(getattr(it, "count", 0) or 0)
#        head = "%s %s" % (mark, title)
#        if count:
#            head += "(%d entries)" % count
#        lines.append(head)
#        detail = str(getattr(it, "detail", "") or "").strip()
#        if detail:
#            lines.append("    %s" % detail)
#    return "\n".join(lines)
#
#F 7ef762dad06f4a00dc64c0a361c98b83ad86f7a8 1068 adept/ui/gallery.py
## ADEPT Studio Gallery — authored 2026-07-28 (M5-2).
## 虛擬捲動的骨架（單一自繪畫布 + 手算可視範圍）是本檔自寫；視覺語言、
## token 用法與 test-accessor 慣例沿用 adept/ui/widgets.py。
#"""同屏比多顆 —— 縮圖網格（Gallery）。
#
#為什麼要有這一頁：單顆預覽一次只能看一顆，但調參的真正問題是「**整群**看起來
#對不對」——排前面的是不是都是真缺陷？門檻附近坐著什麼？所以把整批 defect 攤成
#縮圖牆，用眼睛一次掃過一整批。它跟直方圖是同一個調參迴圈的兩半：
#直方圖點一根 bar → :meth:`GalleryPanel.filter_by_score_range` → 這裡只剩那一區間。
#
#設計約束（跟 ``widgets.py`` 同一套，別破壞）
#--------------------------------------------
#
#1. **純資料驅動**：只吃 dict / ndarray，只發 Signal。這個元件**不碰引擎、不開檔案**。
#   縮圖由呼叫端（背景執行緒用 :func:`make_thumb` 產生）餵進來；``thumb=None``
#   會畫「載入中…」的佔位磚，之後用 :meth:`GalleryPanel.set_thumb` 逐張補上。
#2. **顏色一律走 ``theme.TOKENS``**，不寫死 hex。
#3. **顏色不是唯一通道**：bin 除了色條，也一定寫在說明文字裡（「bin 1」），
#   色盲 / 投影機 / 列印都讀得到 —— 推廣鐵則。
#4. **虛擬捲動是硬需求**：目標 10k defect 順順跑。作法是「一塊自繪畫布」——
#   整個網格只有 **一個** widget（:class:`_GridView` 的 viewport），tile 是畫上去的
#   不是 widget，所以 10k 顆不會產生 10k 個 QWidget。每次重繪只走
#   :meth:`_GridView._visible_range` 算出來的可視索引區間（外加 1 列 overscan），
#   QPixmap 轉換結果放在上限 :data:`CACHE_CAP` 的 LRU 快取裡（key 含縮圖尺寸）。
#"""
#
#from __future__ import annotations
#
#import math
#from collections import OrderedDict
#from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
#
#import cv2
#import numpy as np
#from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
#from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
#from PySide6.QtWidgets import (
#    QAbstractScrollArea,
#    QComboBox,
#    QFrame,
#    QHBoxLayout,
#    QLabel,
#    QPushButton,
#    QSizePolicy,
#    QVBoxLayout,
#    QWidget,
#)
#
#from .theme import TOKENS
#from .widgets import to_uint8
#
#__all__ = ["GalleryPanel", "make_thumb", "THUMB_SIZES", "CACHE_CAP"]
#
##: 縮圖大小選項（顯示名稱, 邊長 px）—— 小 / 中 / 大。
#THUMB_SIZES: Tuple[Tuple[str, int], ...] = (("S", 64), ("M", 96), ("L", 144))
#
##: QPixmap LRU 快取上限（筆數）。key = (defect_id, 縮圖邊長)。
#CACHE_CAP = 512
#
##: 可視範圍上下各多算幾列（捲動時不會看到白邊）。
#OVERSCAN_ROWS = 1
#
#
## --------------------------------------------------------------------------- #
## 縮圖產生（Qt-free —— 呼叫端可以在背景執行緒跑）
## --------------------------------------------------------------------------- #
#def make_thumb(arr: np.ndarray, size: int = 96) -> np.ndarray:
#    """任意 ndarray → ``size`` × ``size`` 的方形 uint8 縮圖。
#
#    * 正規化規則與 :func:`widgets.to_uint8` **完全一致**：``uint8`` 原樣使用
#      （patch 的原始灰階就是原始灰階），float / int16 等走 min–max 自動拉伸，
#      NaN/Inf 不參與統計。同一顆 defect 在單顆預覽與 gallery 裡看起來一樣。
#    * 非方形輸入採 **letterbox**（等比縮到塞得下，四周補黑）而不是裁切 ——
#      缺陷可能就長在邊緣，裁掉會讓人看不到證據。
#    * 縮小用 ``cv2.INTER_AREA``（防摩爾紋），放大用 ``INTER_NEAREST``
#      （SEM 小圖要看得出方格，跟 ImageView 放大時關平滑取樣同一個理由）。
#
#    這個函式**不碰 Qt**，所以可以丟到背景執行緒批次產生縮圖。
#    """
#    s = int(max(8, min(512, int(size))))
#    a = np.asarray(arr)
#    if a.ndim == 3:
#        if a.shape[2] == 4:
#            a = a[:, :, :3]
#        elif a.shape[2] == 1:
#            a = a[:, :, 0]
#        elif a.shape[2] != 3:
#            a = a[:, :, 0]
#    if a.ndim not in (2, 3):
#        raise ValueError("make_thumb accepts (H,W) or (H,W,3/4) images only, got %r"
#                         % (a.shape,))
#
#    colour = a.ndim == 3
#    out_shape = (s, s, 3) if colour else (s, s)
#    h, w = a.shape[:2]
#    if h <= 0 or w <= 0:
#        return np.zeros(out_shape, dtype=np.uint8)
#
#    u8 = to_uint8(a)
#    scale = min(s / float(w), s / float(h))
#    tw = int(max(1, min(s, round(w * scale))))
#    th = int(max(1, min(s, round(h * scale))))
#    if (tw, th) != (w, h):
#        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_NEAREST
#        small = cv2.resize(u8, (tw, th), interpolation=interp)
#    else:
#        small = u8
#    if colour and small.ndim == 2:            # cv2 可能把單通道壓成 2-D
#        small = np.repeat(small[:, :, None], 3, axis=2)
#
#    out = np.zeros(out_shape, dtype=np.uint8)
#    y0, x0 = (s - th) // 2, (s - tw) // 2
#    out[y0:y0 + th, x0:x0 + tw] = small
#    return out
#
#
#def thumb_placement(shape: Any, size: int = 96) -> Tuple[int, int, int, int]:
#    """縮圖裡「影像實際落在哪」：``(x0, y0, w, h)``。
#
#    :func:`make_thumb` 用的是**置中的 letterbox**（等比縮放後四周補黑），
#    所以要把一個正規化座標的框畫到縮圖上，就得知道那個偏移與縮放。
#
#    **它與 make_thumb 是同一份算式，所以放在一起** —— 分開放的話，
#    哪天改了縮圖的縮放規則而忘了改這裡，框就會整批偏掉，
#    而且畫面上看起來只是「框好像有點歪」，不會有人聯想到是縮圖改過。
#    """
#    s = int(max(8, min(512, int(size))))
#    h, w = (int(shape[0]), int(shape[1])) if len(shape) >= 2 else (0, 0)
#    if h <= 0 or w <= 0:
#        return (0, 0, s, s)
#    scale = min(s / float(w), s / float(h))
#    tw = int(max(1, min(s, round(w * scale))))
#    th = int(max(1, min(s, round(h * scale))))
#    return ((s - tw) // 2, (s - th) // 2, tw, th)
#
#
#def _qimage_from_uint8(arr: np.ndarray) -> QImage:
#    """uint8 (H,W) / (H,W,3) → QImage（deep copy，不依賴原 buffer）。
#
#    規則與 ``widgets._qimage_from_uint8`` 相同；gallery 只會拿到縮圖，
#    所以只支援灰階與 RGB 兩種。
#    """
#    a = np.ascontiguousarray(arr)
#    if a.ndim == 2:
#        h, w = a.shape
#        img = QImage(a.data, w, h, w, QImage.Format_Grayscale8)
#    elif a.ndim == 3 and a.shape[2] == 3:
#        h, w, _ = a.shape
#        img = QImage(a.data, w, h, 3 * w, QImage.Format_RGB888)
#    elif a.ndim == 3 and a.shape[2] == 4:
#        h, w, _ = a.shape
#        img = QImage(a.data, w, h, 4 * w, QImage.Format_RGBA8888)
#    else:
#        raise ValueError("Unsupported thumbnail shape: %r" % (a.shape,))
#    return img.copy()
#
#
#def _fmt_score(value: Any) -> str:
#    """分數 → 說明文字用的短字串（3 位有效數字，整數不拖小數）。"""
#    try:
#        f = float(value)
#    except (TypeError, ValueError):
#        return str(value)
#    if math.isnan(f):
#        return "NaN"
#    if math.isinf(f):
#        return "∞" if f > 0 else "-∞"
#    if f == int(f) and abs(f) < 1e12:
#        return str(int(f))
#    return "%.3g" % f
#
#
## --------------------------------------------------------------------------- #
## 排序 / 篩選（Qt-free 的純邏輯，方便單獨測）
## --------------------------------------------------------------------------- #
#def _value_of(item: Dict[str, Any], key: str) -> Any:
#    """取排序值：``score`` / ``bin`` / ``defect_id`` 是固定欄位，其餘查 features。"""
#    if key == "score":
#        return item.get("score")
#    if key == "bin":
#        return item.get("bin")
#    if key == "defect_id":
#        return item.get("defect_id")
#    return (item.get("features") or {}).get(key)
#
#
#def _sort_key(value: Any, none_rank: int) -> Tuple[int, float, str]:
#    """把任意值壓成可比較的三元組；``None``/NaN 一律排到最後（不管升冪降冪）。"""
#    if value is None:
#        return (none_rank, 0.0, "")
#    if isinstance(value, bool):
#        return (0, float(value), "")
#    if isinstance(value, (int, float, np.integer, np.floating)):
#        f = float(value)
#        return (none_rank, 0.0, "") if math.isnan(f) else (0, f, "")
#    text = str(value)
#    try:                                   # KLARF 的 DEFECTID 常是純數字字串
#        return (0, float(text), "")
#    except ValueError:
#        return (1, 0.0, text)
#
#
#def make_filter(spec: Any) -> Tuple[Optional[Callable[[Dict[str, Any]], bool]], str]:
#    """篩選條件 → ``(predicate, 中文說明)``；``predicate=None`` 代表「全部」。
#
#    支援的 ``spec``：
#
#    ============================================  ================================
#    spec                                          意思
#    ============================================  ================================
#    ``None`` / ``"all"`` / ``{"mode": "all"}``    全部顯示
#    ``{"mode": "bin", "bin": 1}``                 只看某個 bin
#    ``{"mode": "score_range", "lo":a, "hi":b}``   分數落在 [a, b]（直方圖點 bar 用）
#    ``"failed"`` / ``{"mode": "failed"}``         只看跑失敗的（``ok=False``）
#    可呼叫物件 ``fn(item) -> bool``               自訂條件
#    ============================================  ================================
#    """
#    if spec is None:
#        return None, ""
#    if callable(spec):
#        return (lambda it: bool(spec(it))), "custom filter"
#    if isinstance(spec, str):
#        spec = {"mode": spec}
#    if not isinstance(spec, dict):
#        raise TypeError("Unrecognised filter spec: %r" % (spec,))
#
#    mode = str(spec.get("mode", "all"))
#    if mode == "all":
#        return None, ""
#    if mode == "failed":
#        return (lambda it: not bool(it.get("ok", True))), "failed only"
#    if mode == "bin":
#        want = spec.get("bin")
#        want = None if want is None else int(want)
#        return ((lambda it: it.get("bin") == want),
#                "bin %s only" % ("—" if want is None else want))
#    if mode == "score_range":
#        lo = spec.get("lo")
#        hi = spec.get("hi")
#        lo_f = -float("inf") if lo is None else float(lo)
#        hi_f = float("inf") if hi is None else float(hi)
#        if lo_f > hi_f:
#            lo_f, hi_f = hi_f, lo_f
#
#        def _in_range(it: Dict[str, Any]) -> bool:
#            s = it.get("score")
#            if s is None:
#                return False
#            f = float(s)
#            return not math.isnan(f) and lo_f <= f <= hi_f
#
#        return _in_range, "score %s ~ %s" % (_fmt_score(lo_f), _fmt_score(hi_f))
#    raise ValueError("Unknown filter mode: %r" % (mode,))
#
#
## --------------------------------------------------------------------------- #
## 條件 chip（可移除）
## --------------------------------------------------------------------------- #
#class _Chip(QPushButton):
#    """標頭上的一顆條件 chip：``排序：score ↓  ✕``。點一下就把該條件拿掉。"""
#
#    def __init__(self, text: str, tip: str, parent: Optional[QWidget] = None):
#        super().__init__("%s  ✕" % text, parent)
#        self.setObjectName("galleryChip")
#        self.label_text = text
#        self.setCursor(Qt.PointingHandCursor)
#        self.setToolTip(tip)
#        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
#        self.refresh_style()
#
#    def refresh_style(self) -> None:
#        """（重新）套用 token 顏色 —— 換主題時由 GalleryPanel 呼叫。"""
#        self.setStyleSheet(
#            "QPushButton#galleryChip { background:%s; color:%s;"
#            " border:1px solid %s; border-radius:9px; padding:2px 9px;"
#            " font-size:11px; font-weight:500; min-height:16px; }"
#            "QPushButton#galleryChip:hover { background:%s; }"
#            % (TOKENS["accent_bg"], TOKENS["accent_active"],
#               TOKENS["accent_border"], TOKENS["hover_warm_strong"])
#        )
#
#
## --------------------------------------------------------------------------- #
## 網格本體（虛擬捲動的自繪畫布）
## --------------------------------------------------------------------------- #
#class _GridView(QAbstractScrollArea):
#    """縮圖網格畫布 —— **整個網格只有一個 widget**（viewport），tile 是畫的。
#
#    捲動位置 + viewport 高度 → :meth:`_visible_range` 算出「這一瞬間該畫哪幾格」，
#    ``paintEvent`` 只跑那個區間。所以 10 顆與 10,000 顆的每幀成本一樣。
#    """
#
#    selection_changed = Signal(object)      # list[str]
#    defect_activated = Signal(str)
#    thumbs_requested = Signal(object)       # list[str]：可視範圍內還沒有縮圖的
#
#    _EMPTY_TEXT = "(Thumbnails for every defect appear here after a trial run)"
#    _NO_MATCH_TEXT = "(No defect matches the current filter — try removing a chip above)"
#
#    _MARGIN = 10
#    _GAP = 8
#    _PAD = 6
#    _BAR_H = 4                              # bin 色條
#    _CAPTION_H = 17
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setFrameShape(QFrame.NoFrame)
#        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
#        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
#        self.setFocusPolicy(Qt.StrongFocus)
#        self.viewport().setMouseTracking(True)
#        self.setMinimumSize(220, 140)
#
#        self._items: List[Dict[str, Any]] = []
#        self._pos_of: Dict[str, int] = {}
#        self._view: List[int] = []            # 顯示順序 -> _items 索引
#        self._selected: List[str] = []
#        self._anchor = -1
#
#        self._sort_key: Optional[str] = None
#        self._sort_desc = True
#        self._filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None
#        self._filter_text = ""
#
#        self._thumb = int(THUMB_SIZES[1][1])
#        self._cache: "OrderedDict[Tuple[str, int], QPixmap]" = OrderedDict()
#        self._last_request: Tuple[int, int] = (-1, -1)
#
#    # -- 資料 ---------------------------------------------------------------
#    def set_items(self, items: Sequence[Dict[str, Any]]) -> None:
#        norm: List[Dict[str, Any]] = []
#        pos: Dict[str, int] = {}
#        for raw in items or []:
#            d = {
#                "defect_id": str(raw.get("defect_id", "")),
#                "score": _opt_float(raw.get("score")),
#                "bin": _opt_int(raw.get("bin")),
#                "ok": bool(raw.get("ok", True)),
#                "features": dict(raw.get("features") or {}),
#                "thumb": raw.get("thumb"),
#            }
#            pos[d["defect_id"]] = len(norm)
#            norm.append(d)
#        # 先把顯示清單清空再換資料：setValue(0) 會同步觸發 scrollContentsBy，
#        # 那時若 _view 還指著舊清單的索引就會讀到已經不存在的項目。
#        self._view = []
#        self._last_request = (-1, -1)
#        self._items = norm
#        self._pos_of = pos
#        self._cache.clear()
#        self._selected = [i for i in self._selected if i in pos]
#        self._anchor = -1
#        self.verticalScrollBar().setValue(0)
#        self.refresh()
#
#    def set_thumb(self, defect_id: str, arr: Optional[np.ndarray]) -> bool:
#        """補上（或換掉）某顆的縮圖；``defect_id`` 不在清單裡回傳 False。"""
#        i = self._pos_of.get(str(defect_id))
#        if i is None:
#            return False
#        self._items[i]["thumb"] = arr
#        for key in [k for k in self._cache if k[0] == str(defect_id)]:
#            del self._cache[key]
#        self.viewport().update()
#        return True
#
#    def items(self) -> List[Dict[str, Any]]:
#        return list(self._items)
#
#    def total_count(self) -> int:
#        return len(self._items)
#
#    def displayed_count(self) -> int:
#        return len(self._view)
#
#    def displayed_ids(self) -> List[str]:
#        return [self._items[i]["defect_id"] for i in self._view]
#
#    def item_at(self, index: int) -> Optional[Dict[str, Any]]:
#        if 0 <= index < len(self._view):
#            return self._items[self._view[index]]
#        return None
#
#    # -- 排序 / 篩選 ---------------------------------------------------------
#    def set_sort(self, key: Optional[str], descending: bool = True) -> None:
#        self._sort_key = None if key in (None, "") else str(key)
#        self._sort_desc = bool(descending)
#        self.refresh()
#
#    def sort_key(self) -> Optional[str]:
#        return self._sort_key
#
#    def sort_descending(self) -> bool:
#        return self._sort_desc
#
#    def set_filter(self, spec: Any) -> None:
#        self._filter_fn, self._filter_text = make_filter(spec)
#        self.verticalScrollBar().setValue(0)
#        self.refresh()
#
#    def filter_text(self) -> str:
#        return self._filter_text
#
#    def refresh(self) -> None:
#        """重算顯示順序（篩選 → 排序）並重畫。"""
#        idx = list(range(len(self._items)))
#        if self._filter_fn is not None:
#            fn = self._filter_fn
#            keep = []
#            for i in idx:
#                try:
#                    if fn(self._items[i]):
#                        keep.append(i)
#                except Exception:            # noqa: BLE001 — 自訂條件炸掉不該殺 UI
#                    continue
#            idx = keep
#        if self._sort_key:
#            key = self._sort_key
#            none_rank = -1 if self._sort_desc else 2
#            idx.sort(key=lambda i: _sort_key(_value_of(self._items[i], key),
#                                             none_rank),
#                     reverse=self._sort_desc)
#        self._view = idx
#        self._update_scrollbar()
#        self.viewport().update()
#        self._maybe_request_thumbs()
#
#    # -- 選取 ---------------------------------------------------------------
#    def selected_ids(self) -> List[str]:
#        return list(self._selected)
#
#    def set_selected(self, ids: Sequence[str], emit: bool = False) -> None:
#        wanted = [str(i) for i in (ids or []) if str(i) in self._pos_of]
#        changed = wanted != self._selected
#        self._selected = wanted
#        self.viewport().update()
#        if changed and emit:
#            self.selection_changed.emit(list(self._selected))
#
#    # -- 縮圖大小 -----------------------------------------------------------
#    def set_thumb_size(self, px: int) -> None:
#        px = int(max(32, min(320, int(px))))
#        if px == self._thumb:
#            return
#        self._thumb = px
#        self._update_scrollbar()
#        self.viewport().update()
#        self._maybe_request_thumbs()
#
#    def thumb_size(self) -> int:
#        return self._thumb
#
#    # -- 幾何 ---------------------------------------------------------------
#    def _tile_w(self) -> int:
#        return self._thumb + 2 * self._PAD
#
#    def _tile_h(self) -> int:
#        return (self._BAR_H + self._PAD + self._thumb + 3
#                + self._CAPTION_H + self._PAD)
#
#    def _cell_w(self) -> int:
#        return self._tile_w() + self._GAP
#
#    def _cell_h(self) -> int:
#        return self._tile_h() + self._GAP
#
#    def _viewport_size(self) -> Tuple[int, int]:
#        vp = self.viewport()
#        w = vp.width() or self.width() or 1
#        h = vp.height() or self.height() or 1
#        return int(w), int(h)
#
#    def columns(self) -> int:
#        w, _ = self._viewport_size()
#        usable = max(1, w - 2 * self._MARGIN + self._GAP)
#        return max(1, usable // self._cell_w())
#
#    def _row_count(self) -> int:
#        n = len(self._view)
#        return 0 if n == 0 else int(math.ceil(n / float(self.columns())))
#
#    def content_height(self) -> int:
#        rows = self._row_count()
#        return 0 if rows == 0 else 2 * self._MARGIN + rows * self._cell_h() - self._GAP
#
#    def _update_scrollbar(self) -> None:
#        _, vh = self._viewport_size()
#        bar = self.verticalScrollBar()
#        bar.setSingleStep(max(8, self._cell_h() // 3))
#        bar.setPageStep(max(1, vh))
#        bar.setRange(0, max(0, self.content_height() - vh))
#
#    def _visible_range(self) -> Tuple[int, int]:
#        """目前該畫（含 overscan）的顯示索引區間 ``[lo, hi)``。"""
#        n = len(self._view)
#        if n == 0:
#            return (0, 0)
#        cols = self.columns()
#        cell_h = self._cell_h()
#        _, vh = self._viewport_size()
#        top = int(self.verticalScrollBar().value())
#        first = (top - self._MARGIN) // cell_h - OVERSCAN_ROWS
#        last = (top + vh - self._MARGIN) // cell_h + OVERSCAN_ROWS
#        lo = max(0, min(n, int(first) * cols))
#        hi = max(lo, min(n, (int(last) + 1) * cols))
#        return (lo, hi)
#
#    def visible_indices(self) -> List[int]:
#        lo, hi = self._visible_range()
#        return list(range(lo, hi))
#
#    def tile_rect(self, index: int) -> QRect:
#        """顯示索引 → viewport 座標的方框（給 hit-test / 測試點擊用）。"""
#        cols = self.columns()
#        row, col = divmod(int(index), cols)
#        x = self._MARGIN + col * self._cell_w()
#        y = self._MARGIN + row * self._cell_h() - int(self.verticalScrollBar().value())
#        return QRect(int(x), int(y), self._tile_w(), self._tile_h())
#
#    def index_at(self, pos: QPoint) -> Optional[int]:
#        if not self._view:
#            return None
#        x = int(pos.x()) - self._MARGIN
#        y = int(pos.y()) + int(self.verticalScrollBar().value()) - self._MARGIN
#        if x < 0 or y < 0:
#            return None
#        cols = self.columns()
#        col, in_x = divmod(x, self._cell_w())
#        row, in_y = divmod(y, self._cell_h())
#        if col >= cols or in_x >= self._tile_w() or in_y >= self._tile_h():
#            return None                       # 點在格與格之間的空隙
#        i = int(row) * cols + int(col)
#        return i if 0 <= i < len(self._view) else None
#
#    # -- 縮圖 LRU -----------------------------------------------------------
#    def cache_size(self) -> int:
#        return len(self._cache)
#
#    def _pixmap_for(self, item: Dict[str, Any]) -> Optional[QPixmap]:
#        arr = item.get("thumb")
#        if arr is None:
#            return None
#        key = (item["defect_id"], self._thumb)
#        hit = self._cache.get(key)
#        if hit is not None:
#            self._cache.move_to_end(key)
#            return hit
#        try:
#            u8 = to_uint8(np.asarray(arr))
#            if u8.ndim == 3 and u8.shape[2] not in (3, 4):
#                u8 = u8[:, :, 0]
#            pm = QPixmap.fromImage(_qimage_from_uint8(u8))
#        except Exception:                     # noqa: BLE001 — 壞縮圖不該殺掉整頁
#            return None
#        s = self._thumb
#        if pm.width() != s or pm.height() != s:
#            mode = (Qt.SmoothTransformation if max(pm.width(), pm.height()) > s
#                    else Qt.FastTransformation)
#            pm = pm.scaled(QSize(s, s), Qt.KeepAspectRatio, mode)
#        self._cache[key] = pm
#        self._cache.move_to_end(key)
#        while len(self._cache) > CACHE_CAP:
#            self._cache.popitem(last=False)   # 丟最久沒用到的
#        return pm
#
#    def _maybe_request_thumbs(self) -> None:
#        rng = self._visible_range()
#        if rng == self._last_request:
#            return
#        self._last_request = rng
#        missing = [self._items[self._view[i]]["defect_id"]
#                   for i in range(rng[0], rng[1])
#                   if self._items[self._view[i]].get("thumb") is None]
#        if missing:
#            self.thumbs_requested.emit(missing)
#
#    # -- 說明文字 -----------------------------------------------------------
#    def caption_at(self, index: int) -> str:
#        item = self.item_at(index)
#        return "" if item is None else caption_of(item)
#
#    def placeholder_text(self) -> str:
#        if not self._items:
#            return self._EMPTY_TEXT
#        if not self._view:
#            return self._NO_MATCH_TEXT
#        return ""
#
#    # -- 繪圖 ---------------------------------------------------------------
#    def paintEvent(self, _e) -> None:          # noqa: D102 - Qt hook
#        p = QPainter(self.viewport())
#        # 縮圖牆也用中性灰 —— 這裡是用眼睛掃整批的地方，背景偏差影響最大
#        p.fillRect(self.viewport().rect(), QColor(TOKENS["image_backdrop"]))
#        if not self._view:
#            p.setPen(QColor(TOKENS["text_disabled"]))
#            p.drawText(self.viewport().rect(), Qt.AlignCenter,
#                       self.placeholder_text())
#            p.end()
#            return
#        small = QFont(p.font())
#        small.setPointSize(8)
#        p.setFont(small)
#        lo, hi = self._visible_range()
#        for i in range(lo, hi):
#            self._paint_tile(p, i)
#        p.end()
#
#    def _paint_tile(self, p: QPainter, index: int) -> None:
#        item = self.item_at(index)
#        if item is None:
#            return
#        rect = self.tile_rect(index)
#        selected = item["defect_id"] in self._selected
#
#        p.setRenderHint(QPainter.Antialiasing, True)
#        if selected:
#            p.setPen(QPen(QColor(TOKENS["accent"]), 2))
#            p.setBrush(QColor(TOKENS["accent_bg"]))
#        else:
#            p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
#            p.setBrush(QColor(TOKENS["bg_surface"]))
#        p.drawRoundedRect(QRect(rect).adjusted(1, 1, -1, -1), 6, 6)
#
#        # bin 色條（顏色只是輔助，bin 數字一定也寫在說明文字裡）
#        p.setPen(Qt.NoPen)
#        p.setBrush(QColor(bin_hex(item)))
#        p.drawRect(QRect(rect.left() + 5, rect.top() + 4,
#                         rect.width() - 10, self._BAR_H))
#
#        img_top = rect.top() + self._BAR_H + self._PAD
#        img_rect = QRect(rect.left() + self._PAD, img_top, self._thumb, self._thumb)
#        pm = self._pixmap_for(item)
#        if pm is None:
#            p.setPen(QPen(QColor(TOKENS["border_default"]), 1, Qt.DashLine))
#            p.setBrush(QColor(TOKENS["bg_elevated"]))
#            p.drawRect(img_rect)
#            p.setPen(QColor(TOKENS["text_disabled"]))
#            p.drawText(img_rect, Qt.AlignCenter, "loading…")
#        else:
#            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
#            x = img_rect.left() + (img_rect.width() - pm.width()) // 2
#            y = img_rect.top() + (img_rect.height() - pm.height()) // 2
#            p.drawPixmap(QPoint(x, y), pm)
#
#        cap_rect = QRect(rect.left() + self._PAD, img_rect.bottom() + 3,
#                         self._thumb, self._CAPTION_H)
#        p.setPen(QColor(TOKENS["text_secondary"] if item["ok"]
#                        else TOKENS["danger_text"]))
#        text = p.fontMetrics().elidedText(caption_of(item), Qt.ElideMiddle,
#                                          cap_rect.width())
#        p.drawText(cap_rect, Qt.AlignLeft | Qt.AlignVCenter, text)
#
#    # -- 互動 ---------------------------------------------------------------
#    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
#        if e.button() != Qt.LeftButton:
#            return
#        idx = self.index_at(e.position().toPoint())
#        mods = e.modifiers()
#        before = list(self._selected)
#        if idx is None:
#            self._selected = []
#        elif mods & Qt.ShiftModifier and self._anchor >= 0:
#            lo, hi = sorted((self._anchor, idx))
#            self._selected = [self._items[self._view[i]]["defect_id"]
#                              for i in range(lo, min(hi + 1, len(self._view)))]
#        elif mods & (Qt.ControlModifier | Qt.MetaModifier):
#            did = self._items[self._view[idx]]["defect_id"]
#            if did in self._selected:
#                self._selected = [i for i in self._selected if i != did]
#            else:
#                self._selected = self._selected + [did]
#            self._anchor = idx
#        else:
#            self._selected = [self._items[self._view[idx]]["defect_id"]]
#            self._anchor = idx
#        self.viewport().update()
#        if self._selected != before:
#            self.selection_changed.emit(list(self._selected))
#        e.accept()
#
#    def mouseDoubleClickEvent(self, e) -> None:   # noqa: D102 - Qt hook
#        if e.button() != Qt.LeftButton:
#            return
#        idx = self.index_at(e.position().toPoint())
#        if idx is None:
#            return
#        item = self.item_at(idx)
#        if item is None:
#            return
#        if self._selected != [item["defect_id"]]:
#            self._selected = [item["defect_id"]]
#            self._anchor = idx
#            self.viewport().update()
#            self.selection_changed.emit(list(self._selected))
#        self.defect_activated.emit(item["defect_id"])
#        e.accept()
#
#    def scrollContentsBy(self, dx: int, dy: int) -> None:   # noqa: D102 - Qt hook
#        self.viewport().update()
#        self._maybe_request_thumbs()
#
#    def resizeEvent(self, e) -> None:          # noqa: D102 - Qt hook
#        super().resizeEvent(e)
#        self._update_scrollbar()
#        self._maybe_request_thumbs()
#
#
#def bin_hex(item: Dict[str, Any]) -> str:
#    """tile 色條顏色：失敗=紅、bin 1=綠、bin 0=灰、未判定=中性。"""
#    if not item.get("ok", True):
#        return TOKENS["danger"]
#    b = item.get("bin")
#    if b is None:
#        return TOKENS["chip_neutral_border"]
#    if int(b) == 0:
#        return TOKENS["seg_disabled"]
#    return TOKENS["success"]
#
#
#def caption_of(item: Dict[str, Any]) -> str:
#    """一行說明：``#id · bin 1 · 3.21``。
#
#    **bin 一定寫成文字**，色條只是輔助 —— 色盲、投影機、黑白列印都要讀得到。
#    """
#    parts = ["#%s" % item.get("defect_id", "")]
#    if not item.get("ok", True):
#        parts.append("FAILED")
#        return " · ".join(parts)
#    b = item.get("bin")
#    parts.append("bin %d" % int(b) if b is not None else "bin —")
#    s = item.get("score")
#    if s is not None:
#        parts.append(_fmt_score(s))
#    return " · ".join(parts)
#
#
#def _opt_float(v: Any) -> Optional[float]:
#    if v is None:
#        return None
#    try:
#        return float(v)
#    except (TypeError, ValueError):
#        return None
#
#
#def _opt_int(v: Any) -> Optional[int]:
#    if v is None:
#        return None
#    try:
#        return int(v)
#    except (TypeError, ValueError):
#        return None
#
#
## --------------------------------------------------------------------------- #
## 對外的面板（標頭 + 網格）
## --------------------------------------------------------------------------- #
#class GalleryPanel(QWidget):
#    """同屏比多顆：標頭（顯示筆數 + 排序 + 縮圖大小 + 條件 chip）+ 縮圖網格。
#
#    主視窗這樣用：
#
#    ``set_sort_keys([...])`` 一次（有哪些欄可排）→ 試跑完 ``set_items([...])``
#    （每筆 = ``result_to_json_dict`` 的 dict 再加一個 ``thumb`` 鍵）→ 縮圖用
#    :func:`make_thumb` 在背景產生後 ``set_thumb(defect_id, arr)`` 逐張補。
#    直方圖點一根 bar → :meth:`filter_by_score_range`。
#    使用者雙擊某顆 → ``defect_activated(defect_id)``，主視窗把單顆預覽跳過去。
#    """
#
#    selection_changed = Signal(object)      # list[str]
#    defect_activated = Signal(str)
#    thumbs_requested = Signal(object)       # list[str]
#
#    _ORDER_DESC = "↓ High to low"
#    _ORDER_ASC = "↑ Low to high"
#    #: 排序下拉的第一項 = 不排序（維持 set_items 給的原始順序）。
#    NO_SORT = "(original order)"
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        outer = QVBoxLayout(self)
#        outer.setContentsMargins(0, 0, 0, 0)
#        outer.setSpacing(4)
#
#        # ---- 標頭第一列：筆數 + 排序 + 縮圖大小 ----------------------------
#        head = QHBoxLayout()
#        head.setContentsMargins(2, 0, 2, 0)
#        head.setSpacing(6)
#
#        self.count_label = QLabel("")
#        self.count_label.setObjectName("galleryCount")
#        self.count_label.setToolTip("Defects shown after filtering / total in this batch")
#        self.count_label.setStyleSheet("color:%s; font-weight:700;"
#                                       % TOKENS["text_primary"])
#        head.addWidget(self.count_label)
#        head.addSpacing(6)
#
#        sort_label = QLabel("Sort by")
#        sort_label.setToolTip("Sort by a field: score, any feature, or defect id")
#        head.addWidget(sort_label)
#
#        self.sort_combo = QComboBox()
#        self.sort_combo.setToolTip("Sort by a field: score, any feature, or defect id")
#        self.sort_combo.setMinimumWidth(120)
#        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
#        head.addWidget(self.sort_combo)
#
#        self.order_button = QPushButton(self._ORDER_DESC)
#        self.order_button.setToolTip("Toggle descending / ascending")
#        self.order_button.setProperty("variant", "ghost")
#        self.order_button.clicked.connect(self._toggle_order)
#        head.addWidget(self.order_button)
#
#        head.addStretch(1)
#
#        zoom_label = QLabel("Thumbnail")
#        zoom_label.setToolTip("Thumbnail size: smaller shows more, larger shows more detail")
#        head.addWidget(zoom_label)
#
#        self.zoom_combo = QComboBox()
#        self.zoom_combo.setToolTip("Thumbnail size: smaller shows more, larger shows more detail")
#        for name, px in THUMB_SIZES:
#            self.zoom_combo.addItem(name, px)
#        self.zoom_combo.setCurrentIndex(1)
#        self.zoom_combo.currentIndexChanged.connect(self._on_zoom_changed)
#        head.addWidget(self.zoom_combo)
#        outer.addLayout(head)
#
#        # ---- 標頭第二列：條件 chip -----------------------------------------
#        self._chip_row = QHBoxLayout()
#        self._chip_row.setContentsMargins(2, 0, 2, 0)
#        self._chip_row.setSpacing(5)
#        self._chip_row.addStretch(1)
#        self._chips: List[_Chip] = []
#        outer.addLayout(self._chip_row)
#
#        # ---- 網格 ------------------------------------------------------------
#        self.grid = _GridView(self)
#        self.grid.selection_changed.connect(self.selection_changed)
#        self.grid.defect_activated.connect(self.defect_activated)
#        self.grid.thumbs_requested.connect(self.thumbs_requested)
#        outer.addWidget(self.grid, 1)
#
#        self._sort_keys: List[str] = []
#        self.set_sort_keys(["score"])
#        self.grid.set_thumb_size(int(THUMB_SIZES[1][1]))
#        self._refresh_header()
#
#    # -- 資料（主視窗呼叫）---------------------------------------------------
#    def set_items(self, items: Sequence[Dict[str, Any]]) -> None:
#        """餵資料。每筆：``{defect_id, score, bin, ok, features, thumb}``。
#
#        ``thumb`` 可以是 ``None``（先畫「載入中…」佔位磚，之後用
#        :meth:`set_thumb` 補）。這裡**不會**去讀檔或跑引擎。
#        """
#        self.grid.set_items(items)
#        self._refresh_header()
#
#    def set_thumb(self, defect_id: str, arr: Optional[np.ndarray]) -> bool:
#        """補上單顆的縮圖（背景執行緒算好後回主執行緒呼叫）。"""
#        return self.grid.set_thumb(defect_id, arr)
#
#    def set_thumbs(self, mapping: Dict[str, Optional[np.ndarray]]) -> int:
#        """一次補一批縮圖；回傳成功貼上的張數。"""
#        return sum(1 for k, v in (mapping or {}).items() if self.grid.set_thumb(k, v))
#
#    # -- 排序 ---------------------------------------------------------------
#    def set_sort_keys(self, keys: Sequence[str]) -> None:
#        """設定排序下拉的可選欄位（``defect_id`` 一定會補在最後）。
#
#        下拉的第一項固定是 :data:`NO_SORT`（原始順序）；目前的排序欄位若還在
#        新清單裡會保留，否則預設挑 ``score``（調參最常看的欄）。
#        """
#        keys = [str(k) for k in (keys or [])]
#        if "defect_id" not in keys:
#            keys = keys + ["defect_id"]
#        seen: List[str] = []
#        for k in keys:
#            if k and k not in seen:
#                seen.append(k)
#        self._sort_keys = seen
#
#        current = self.grid.sort_key()
#        if current not in seen:
#            current = "score" if "score" in seen else None
#        block = self.sort_combo.blockSignals(True)
#        self.sort_combo.clear()
#        self.sort_combo.addItem(self.NO_SORT)
#        self.sort_combo.addItems(seen)
#        self.sort_combo.setCurrentIndex(seen.index(current) + 1 if current else 0)
#        self.sort_combo.blockSignals(block)
#        self.grid.set_sort(current, self.grid.sort_descending())
#        self._refresh_header()
#
#    def sort_keys(self) -> List[str]:
#        return list(self._sort_keys)
#
#    def set_sort(self, key: Optional[str], descending: bool = True) -> None:
#        """排序。``key`` 可以是 ``"score"`` / 任一特徵名 / ``"defect_id"``；
#        認不得的 key（或該欄全都沒值）→ 維持原本順序，不會炸。"""
#        self.grid.set_sort(key, descending)
#        block = self.sort_combo.blockSignals(True)
#        if key and key in self._sort_keys:
#            self.sort_combo.setCurrentIndex(self._sort_keys.index(key) + 1)
#        elif not key:
#            self.sort_combo.setCurrentIndex(0)
#        self.sort_combo.blockSignals(block)
#        self.order_button.setText(self._ORDER_DESC if descending
#                                  else self._ORDER_ASC)
#        self._refresh_header()
#
#    def sort_key(self) -> Optional[str]:
#        return self.grid.sort_key()
#
#    def sort_descending(self) -> bool:
#        return self.grid.sort_descending()
#
#    # -- 篩選 ---------------------------------------------------------------
#    def set_filter(self, spec: Any) -> None:
#        """設定篩選條件（見 :func:`make_filter` 支援的寫法）。"""
#        self.grid.set_filter(spec)
#        self._refresh_header()
#
#    def filter_by_score_range(self, lo: Optional[float],
#                              hi: Optional[float]) -> None:
#        """只顯示分數落在 ``[lo, hi]`` 的 defect —— 直方圖點一根 bar 就呼叫這個。"""
#        self.set_filter({"mode": "score_range", "lo": lo, "hi": hi})
#
#    def filter_by_bin(self, bin_value: Optional[int]) -> None:
#        """只顯示某個 bin。"""
#        self.set_filter({"mode": "bin", "bin": bin_value})
#
#    def show_failed_only(self) -> None:
#        """只顯示跑失敗的 defect（``ok=False``）。"""
#        self.set_filter({"mode": "failed"})
#
#    def clear_filter(self) -> None:
#        """清掉篩選，回到全部。"""
#        self.set_filter(None)
#
#    def filter_text(self) -> str:
#        return self.grid.filter_text()
#
#    # -- 縮圖大小 -----------------------------------------------------------
#    def set_thumb_size(self, px: int) -> None:
#        """設定縮圖邊長（會對齊到最接近的 小/中/大 選項）。"""
#        px = int(px)
#        best = min(THUMB_SIZES, key=lambda kv: abs(kv[1] - px))
#        block = self.zoom_combo.blockSignals(True)
#        self.zoom_combo.setCurrentIndex([s[1] for s in THUMB_SIZES].index(best[1]))
#        self.zoom_combo.blockSignals(block)
#        self.grid.set_thumb_size(best[1])
#
#    def thumb_size(self) -> int:
#        return self.grid.thumb_size()
#
#    # -- 選取 ---------------------------------------------------------------
#    def selected_ids(self) -> List[str]:
#        return self.grid.selected_ids()
#
#    def set_selected(self, ids: Sequence[str]) -> None:
#        """程式設定選取（不發 ``selection_changed`` —— 那是使用者點擊才發的）。"""
#        self.grid.set_selected(ids, emit=False)
#
#    # -- 查詢（測試 / 主視窗都用得到）---------------------------------------
#    def displayed_ids(self) -> List[str]:
#        """目前依序顯示的 defect_id（已套用篩選與排序）。"""
#        return self.grid.displayed_ids()
#
#    def displayed_count(self) -> int:
#        return self.grid.displayed_count()
#
#    def total_count(self) -> int:
#        return self.grid.total_count()
#
#    def visible_indices(self) -> List[int]:
#        """**這一瞬間真的會被畫出來**的顯示索引（含 1 列 overscan）。
#
#        虛擬捲動的證據：不管清單有 20 顆還是 10,000 顆，這個清單長度只跟
#        viewport 大小有關。
#        """
#        return self.grid.visible_indices()
#
#    def caption_at(self, index: int) -> str:
#        return self.grid.caption_at(index)
#
#    def caption_of(self, defect_id: str) -> str:
#        for i, did in enumerate(self.displayed_ids()):
#            if did == str(defect_id):
#                return self.grid.caption_at(i)
#        return ""
#
#    def bin_color(self, defect_id: str) -> str:
#        for item in self.grid.items():
#            if item["defect_id"] == str(defect_id):
#                return bin_hex(item)
#        return ""
#
#    def cache_size(self) -> int:
#        return self.grid.cache_size()
#
#    def header_text(self) -> str:
#        return self.count_label.text()
#
#    def empty_text(self) -> str:
#        """目前顯示的空狀態文字（有 tile 時為空字串）。"""
#        return self.grid.placeholder_text()
#
#    def chips(self) -> List[_Chip]:
#        """標頭上的條件 chip（第一顆是排序、之後是篩選）。"""
#        return list(self._chips)
#
#    def chip_texts(self) -> List[str]:
#        return [c.label_text for c in self._chips]
#
#    def refresh_styles(self) -> None:
#        """換主題之後重新取色（chip 與網格都是自繪/內嵌樣式）。"""
#        for chip in self._chips:
#            chip.refresh_style()
#        self.grid.viewport().update()
#        self.update()
#
#    # -- 內部 ---------------------------------------------------------------
#    def _on_sort_changed(self, idx: int) -> None:
#        key = None if idx <= 0 else self.sort_combo.currentText()
#        self.grid.set_sort(key, self.grid.sort_descending())
#        self._refresh_header()
#
#    def _toggle_order(self) -> None:
#        self.set_sort(self.grid.sort_key(), not self.grid.sort_descending())
#
#    def _on_zoom_changed(self, _idx: int) -> None:
#        px = self.zoom_combo.currentData()
#        if px is not None:
#            self.grid.set_thumb_size(int(px))
#
#    def _clear_chips(self) -> None:
#        for chip in self._chips:
#            self._chip_row.removeWidget(chip)
#            chip.setParent(None)
#            chip.deleteLater()
#        self._chips = []
#
#    def _add_chip(self, text: str, tip: str, on_remove: Callable[[], None]) -> None:
#        chip = _Chip(text, tip, self)
#        chip.clicked.connect(lambda: on_remove())
#        self._chip_row.insertWidget(len(self._chips), chip)
#        self._chips.append(chip)
#
#    def _refresh_header(self) -> None:
#        self.count_label.setText("Showing %d / %d defects"
#                                 % (self.grid.displayed_count(),
#                                    self.grid.total_count()))
#        self.order_button.setText(self._ORDER_DESC if self.grid.sort_descending()
#                                  else self._ORDER_ASC)
#        self._clear_chips()
#        key = self.grid.sort_key()
#        if key:
#            arrow = "↓" if self.grid.sort_descending() else "↑"
#            self._add_chip("Sort: %s %s" % (key, arrow),
#                           "Click to clear sorting and return to the original order",
#                           lambda: self.set_sort(None, self.grid.sort_descending()))
#        ftext = self.grid.filter_text()
#        if ftext:
#            self._add_chip("Filter: %s" % ftext, "Click to remove this filter",
#                           self.clear_filter)
#
#F 9e2f4b65877a33fb430b18f0093453b650ee3df4 831 adept/ui/inspectors.py
## ADEPT Studio — 每張卡自己的儀表 (F7-17).
#"""選一張卡，右下角就換成**那張卡的儀表**。
#
#為什麼不是一塊通用面板
#----------------------
#右下角本來是一張「特徵 / 數值」表：`blob_dist_center 11.170`、`blob_snr 255`。
#問題不是它佔位子，是**那些數字沒有辦法判讀** —— 11.17 是大還是小？255 是不是
#飽和了？一個數字單獨存在，回答不了使用者真正在問的問題。
#
#而使用者在問的問題**每張卡都不一樣**：調 Align 的時候他要知道「搜尋半徑夠不夠
#大」，調 Denoise 的時候他要知道「我有沒有把訊號一起磨掉」。同一塊面板放同一種
#東西，對兩者都答非所問。
#
#挑選原則
#--------
#面板不高（約 200 px），所以每張卡**只放一件事**。挑的標準是：
#
#    這張卡最常見的失敗模式是什麼，而那個失敗**在單顆畫面上看不出來**。
#
#看得出來的（影像整個黑掉）不需要面板；看不出來的才需要。Align 就是典型：
#每一顆都「有對到啊」，只有把整批的位移畫在一起，才看得出來一半的點貼在搜尋框
#的邊上 —— 那些顆根本沒對準，只是被半徑截斷了。
#
#三條約定
#--------
#1. **依 ``Step.key`` 註冊**（``INSPECTORS``）。沒註冊的卡就用原本的特徵表，
#   所以加一張新卡不必動這個檔案 —— 維持「import 就出現」那條規則。
#2. **畫的是引擎算出來的那一份**。要嘛來自 ``ctx.meta``（step 卡自己放進去的，
#   同 ``roi_profile``），要嘛來自 ``trial_results``（跑完的整批結果）。
#   UI 不自己重算一次 —— 不然畫面上的東西跟真的跑出來的有機會不一樣。
#3. **沒有資料時說得出「為什麼沒有」**，而不是一片空白。最常見的原因是
#   「還沒跑過」，那句話要直接寫在面板上。
#"""
#from __future__ import annotations
#
#import math
#from typing import Any, Dict, List, Optional, Sequence, Tuple
#
#from PySide6.QtCore import QPointF, QRectF, Qt
#from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
#from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget
#
#from .theme import TOKENS
#
#__all__ = ["Inspector", "AlignInspector", "EnhanceInspector",
#           "MeasureInspector", "InputInspector",
#           "ProfileInspector", "TemplateInspector",
#           "INSPECTORS", "inspector_for"]
#
#
#class Inspector(QWidget):
#    """卡片儀表的共同介面。
#
#    ``set_context()`` 一次餵齊三種來源：這張卡的參數、**這一顆**的結果、
#    以及**整批**的結果。子類自己決定要用哪些 —— 但不准自己去跑 pipeline。
#    """
#
#    #: 面板標題（顯示在切換列上）。
#    title = "Card"
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.params: Dict[str, Any] = {}
#        self.result: Dict[str, Any] = {}
#        self.batch: List[Dict[str, Any]] = []
#        self.meta: Dict[str, Any] = {}
#        self.feature_names: List[str] = []
#        self.node_id = ""
#        self.setMinimumHeight(120)
#        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
#
#    def set_context(self, node_id: str, params: Optional[Dict[str, Any]] = None,
#                    result: Optional[Dict[str, Any]] = None,
#                    batch: Optional[Sequence[Dict[str, Any]]] = None,
#                    meta: Optional[Dict[str, Any]] = None,
#                    feature_names: Optional[Sequence[str]] = None) -> None:
#        self.node_id = str(node_id or "")
#        self.params = dict(params or {})
#        self.result = dict(result or {})
#        self.batch = [dict(r) for r in (batch or [])]
#        self.meta = dict(meta or {})
#        #: 這張卡**自己**產出哪些特徵（含 output_prefix）。解析要用卡片庫，
#        #: 那是 Studio 的事 —— 儀表只負責畫。
#        self.feature_names = [str(f) for f in (feature_names or [])]
#        self.update()
#
#    # -- 子類覆寫 -----------------------------------------------------------
#    def summary(self) -> str:
#        """一行文字摘要。**測試與狀態列讀這個**，不去讀畫素。"""
#        return ""
#
#    def has_data(self) -> bool:
#        return False
#
#    def empty_reason(self) -> str:
#        """沒有資料時要說的話 —— 空白面板本身不是訊息。"""
#        return "Run a trial to fill this in."
#
#    # -- 共用小工具 ---------------------------------------------------------
#    def feature_values(self, name: str) -> List[float]:
#        """整批裡某個特徵的值（跳過失敗與缺值的顆）。"""
#        out: List[float] = []
#        for r in self.batch:
#            v = (r.get("features") or {}).get(name)
#            if v is None:
#                continue
#            try:
#                f = float(v)
#            except (TypeError, ValueError):
#                continue
#            if not (math.isnan(f) or math.isinf(f)):
#                out.append(f)
#        return out
#
#    def this_value(self, name: str) -> Optional[float]:
#        v = (self.result.get("features") or {}).get(name)
#        try:
#            f = float(v)
#        except (TypeError, ValueError):
#            return None
#        return None if (math.isnan(f) or math.isinf(f)) else f
#
#    def _frame(self, p: QPainter) -> QRectF:
#        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
#        p.setRenderHint(QPainter.Antialiasing, True)
#        p.fillRect(QRectF(self.rect()), QColor(TOKENS["bg_surface"]))
#        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
#        p.drawRoundedRect(rect, 4, 4)
#        return rect.adjusted(8, 8, -8, -8)
#
#    def _say_empty(self, p: QPainter, rect: QRectF) -> None:
#        p.setPen(QColor(TOKENS["text_disabled"]))
#        p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, self.empty_reason())
#
#    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
#        p = QPainter(self)
#        rect = self._frame(p)
#        if not self.has_data():
#            self._say_empty(p, rect)
#        else:
#            self.paint_body(p, rect)
#        p.end()
#
#    def paint_body(self, p: QPainter, rect: QRectF) -> None:
#        """子類畫這裡（``rect`` 已經扣掉外框與留白）。"""
#
#
#class AlignInspector(Inspector):
#    """Align：**整批的位移散佈圖**，加上搜尋半徑的方框。
#
#    為什麼是這一張圖
#    ----------------
#    對位失敗在單顆上看不出來 —— 每一顆都「有對到啊」，因為演算法一定會回一個
#    位移。真正的失敗是**位移被搜尋半徑截斷**：真實偏移 12 px、半徑設 8，
#    那顆回報 8，而 8 是一個看起來完全正常的數字。
#
#    把整批畫在一起，這件事變成一眼可見：**點貼在方框的邊上**。而且它是可以照做
#    的 —— 把 Search radius 調大再跑一次就好。
#
#    資料來自 ``trial_results`` 的 ``align_dx`` / ``align_dy``（引擎算的），
#    方框來自這張卡的 ``search_radius`` 參數。UI 不自己算對位。
#    """
#
#    title = "Alignment"
#
#    #: 距離邊界多近算「貼在邊上」（像素）。次像素對位會落在 7.9 這種值上，
#    #: 用嚴格相等會什麼都抓不到。
#    _EDGE_TOL = 0.75
#
#    def radius(self) -> float:
#        try:
#            return float(self.params.get("search_radius", 0) or 0)
#        except (TypeError, ValueError):
#            return 0.0
#
#    def points(self) -> List[Tuple[float, float]]:
#        xs = self.feature_values("align_dx")
#        ys = self.feature_values("align_dy")
#        n = min(len(xs), len(ys))
#        return list(zip(xs[:n], ys[:n]))
#
#    def at_the_limit(self) -> int:
#        """有幾顆的位移貼在搜尋框的邊上（= 很可能根本沒對準）。"""
#        r = self.radius()
#        if r <= 0:
#            return 0
#        edge = r - self._EDGE_TOL
#        return sum(1 for x, y in self.points()
#                   if abs(x) >= edge or abs(y) >= edge)
#
#    def has_data(self) -> bool:
#        return bool(self.points())
#
#    def empty_reason(self) -> str:
#        return ("Run a trial to see how far every defect had to move to line "
#                "up. One defect cannot tell you whether the search radius is "
#                "big enough — the whole batch can.")
#
#    def summary(self) -> str:
#        pts = self.points()
#        if not pts:
#            return ""
#        r = self.radius()
#        far = max(max(abs(x), abs(y)) for x, y in pts)
#        text = ("%d defects · largest shift %.1f px · search radius %.0f px"
#                % (len(pts), far, r))
#        stuck = self.at_the_limit()
#        if stuck:
#            text += ("  ⚠ %d of them sit on the search limit — those did not "
#                     "really line up, they ran out of room. Raise “Search "
#                     "radius” and run again." % stuck)
#        return text
#
#    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
#        pts = self.points()
#        r = max(self.radius(), max((max(abs(x), abs(y)) for x, y in pts),
#                                   default=1.0), 1.0)
#        span = r * 1.15
#        # 正方形，而且**置中** —— dx 與 dy 必須同一個尺度（不然圓形的散佈看起來
#        # 像橢圓，使用者會以為某一軸偏得比較多），但靠左擺會讓十字跑到面板左邊。
#        side = min(rect.width(), rect.height())
#        plot = QRectF(rect.left() + (rect.width() - side) / 2.0,
#                      rect.top() + (rect.height() - side) / 2.0, side, side)
#        cx, cy = plot.center().x(), plot.center().y()
#        scale = (side / 2.0) / span
#
#        def to_px(dx: float, dy: float) -> QPointF:
#            # 螢幕的 y 往下為正，位移的 y 往上為正 —— 不翻的話整張圖上下顛倒，
#            # 而使用者是拿它跟影像對照的。
#            return QPointF(cx + dx * scale, cy - dy * scale)
#
#        # 十字與搜尋框
#        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0, Qt.DashLine))
#        p.drawLine(QPointF(plot.left(), cy), QPointF(plot.right(), cy))
#        p.drawLine(QPointF(cx, plot.top()), QPointF(cx, plot.bottom()))
#
#        rad = self.radius()
#        if rad > 0:
#            box = QRectF(to_px(-rad, rad), to_px(rad, -rad))
#            stuck = self.at_the_limit()
#            p.setPen(QPen(QColor(TOKENS["danger_text"] if stuck
#                                 else TOKENS["accent"]), 1.4))
#            p.setBrush(Qt.NoBrush)
#            p.drawRect(box)
#            # 說明放在方框**下面**：上面那條帶子已經有 dy 的軸標，
#            # 兩個東西擠在同一列會疊字（實測疊成一團看不懂）。
#            p.setPen(QColor(TOKENS["text_secondary"]))
#            p.drawText(QRectF(box.left(), box.bottom() + 1, box.width(), 14),
#                       Qt.AlignRight | Qt.AlignVCenter,
#                       "search radius %.0f px" % rad)
#
#        # 每一顆一個點；貼在邊上的用警示色（那些才是要看的）
#        edge = rad - self._EDGE_TOL if rad > 0 else float("inf")
#        normal = QColor(TOKENS["accent"])
#        normal.setAlpha(150)
#        bad = QColor(TOKENS["danger_text"])
#        p.setPen(Qt.NoPen)
#        for x, y in pts:
#            p.setBrush(QBrush(bad if (abs(x) >= edge or abs(y) >= edge)
#                              else normal))
#            p.drawEllipse(to_px(x, y), 2.6, 2.6)
#
#        # 目前這一顆：空心大圈，看得出「我在哪」
#        tx, ty = self.this_value("align_dx"), self.this_value("align_dy")
#        if tx is not None and ty is not None:
#            p.setBrush(Qt.NoBrush)
#            p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.6))
#            p.drawEllipse(to_px(tx, ty), 5.0, 5.0)
#
#        # 座標軸要標 —— 不標的話這是一張幾何圖形，不是量測結果。
#        # 兩個字都畫水平的：旋轉過的字連箭頭一起轉，「dy ↑」會變成「dy ←」。
#        p.setPen(QColor(TOKENS["text_secondary"]))
#        p.drawText(QRectF(plot.right() - 60, cy + 2, 58, 13),
#                   Qt.AlignRight | Qt.AlignVCenter, "dx (px)")
#        p.drawText(QRectF(cx + 4, plot.top(), 60, 13),
#                   Qt.AlignLeft | Qt.AlignVCenter, "dy (px)")
#
#
#class EnhanceInspector(Inspector):
#    """Enhance 九張卡共用：**同一條流的 before / after 直方圖 + 削平計數**。
#
#    為什麼是這一張圖
#    ----------------
#    Enhance 的失敗是安靜的。對比拉大之後「看起來變乾淨了」，但背景被壓成全黑、
#    缺陷的邊界也一起被吃掉 —— 而**後面每一張量測卡都吃這個結果**。
#
#    削平（畫素貼在 0 或 255）是唯一能量化「我毀掉了多少」的東西：那些畫素之間的
#    差異永遠回不來了。所以這裡除了兩條分布，還直接把「多少 % 被壓到底 / 頂」
#    講成一句話。
#
#    資料來自引擎（``ctx.meta['stream_change']``，預覽時才記）—— UI 不自己再套
#    一次那些演算法，不然畫面上的曲線跟真的算出來的有機會不一樣。
#    """
#
#    title = "Before / after"
#
#    #: 削平多少才值得警告。**不是 0** —— 原圖本來就可能有幾顆全黑的畫素，
#    #: 而每次都喊狼來了跟不喊一樣沒有用。實測 1% 以下肉眼看不出差別。
#    WARN_CLIP = 0.01
#
#    def stream(self) -> str:
#        """這張卡的主要輸出流（也就是要比 before/after 的那一條）。"""
#        return str(self.params.get("target") or self.params.get("source")
#                   or "test")
#
#    def record(self) -> Dict[str, Any]:
#        changes = dict(self.meta.get("stream_change") or {})
#        return dict(changes.get(self.stream()) or {})
#
#    def has_data(self) -> bool:
#        rec = self.record()
#        return bool(rec.get("before")) and bool(rec.get("after"))
#
#    def empty_reason(self) -> str:
#        return ("Select a defect to see what this card does to “%s” — the "
#                "grey levels before it ran and after." % self.stream())
#
#    def clipped(self) -> Tuple[float, float]:
#        rec = self.record()
#        return (float(rec.get("clipped_low", 0.0)),
#                float(rec.get("clipped_high", 0.0)))
#
#    def added_clipping(self) -> Tuple[float, float]:
#        """**這張卡自己**新增的削平（原圖本來就黑掉的部分不算它的帳）。"""
#        rec = self.record()
#        lo = float(rec.get("clipped_low", 0.0)) - float(rec.get("was_clipped_low", 0.0))
#        hi = float(rec.get("clipped_high", 0.0)) - float(rec.get("was_clipped_high", 0.0))
#        return (max(0.0, lo), max(0.0, hi))
#
#    def summary(self) -> str:
#        if not self.has_data():
#            return ""
#        lo, hi = self.clipped()
#        text = ("“%s” · %.1f%% of pixels at black, %.1f%% at white"
#                % (self.stream(), lo * 100.0, hi * 100.0))
#        alo, ahi = self.added_clipping()
#        if max(alo, ahi) >= self.WARN_CLIP:
#            text += ("  ⚠ this card flattened %.1f%% of the patch onto the "
#                     "ends of the scale — those pixels no longer differ from "
#                     "each other, and every measure card downstream reads "
#                     "them as identical." % (max(alo, ahi) * 100.0))
#        return text
#
#    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
#        rec = self.record()
#        before = [float(v) for v in rec.get("before") or []]
#        after = [float(v) for v in rec.get("after") or []]
#        n = max(len(before), len(after))
#        # **高度用平方根。** 削平會在兩端堆出兩根極高的柱子（六成的畫素都在那裡），
#        # 線性刻度下其餘的分布會被壓成一條貼著底的線 —— 而那正是要比較的形狀。
#        # 平方根保住高低順序，又讓中間看得見。
#        before = [math.sqrt(v) for v in before]
#        after = [math.sqrt(v) for v in after]
#        top = max(max(before or [1.0]), max(after or [1.0]), 1.0)
#
#        plot = QRectF(rect.left(), rect.top() + 14,
#                      rect.width(), max(20.0, rect.height() - 30))
#        bw = plot.width() / float(n)
#
#        def bars(vals: List[float], col: QColor, filled: bool) -> None:
#            p.setPen(Qt.NoPen if filled else QPen(col, 1.2))
#            p.setBrush(QBrush(col) if filled else Qt.NoBrush)
#            path_pts = []
#            for i, v in enumerate(vals):
#                h = (v / top) * plot.height()
#                x = plot.left() + i * bw
#                if filled:
#                    p.drawRect(QRectF(x, plot.bottom() - h, max(1.0, bw - 0.6), h))
#                else:
#                    path_pts.append(QPointF(x + bw / 2.0, plot.bottom() - h))
#            if not filled and len(path_pts) > 1:
#                for a, b in zip(path_pts, path_pts[1:]):
#                    p.drawLine(a, b)
#
#        # after 是實心的（那是現在的樣子），before 只畫輪廓 —— 兩個都實心會
#        # 疊成一團看不出誰是誰。
#        faint = QColor(TOKENS["text_disabled"])
#        bar = QColor(TOKENS["accent"])
#        bar.setAlpha(170)
#        bars(before, faint, False)
#        bars(after, bar, True)
#
#        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
#        p.drawLine(QPointF(plot.left(), plot.bottom()),
#                   QPointF(plot.right(), plot.bottom()))
#
#        # 兩端的削平：把貼在 0 / 255 的那一格標成警示色，不然它只是一根高柱子
#        lo, hi = self.clipped()
#        alo, ahi = self.added_clipping()
#        for frac, added, at_left in ((lo, alo, True), (hi, ahi, False)):
#            if frac <= 0.0005:
#                continue
#            col = QColor(TOKENS["danger_text"] if added >= self.WARN_CLIP
#                         else TOKENS["warning"])
#            x = plot.left() if at_left else plot.right() - bw
#            p.setPen(Qt.NoPen)
#            p.setBrush(QBrush(col))
#            p.drawRect(QRectF(x, plot.top() - 6, max(2.0, bw), 4))
#
#        # 圖例放**底部**：頂端那一列是削平標記的位置，兩個擠在一起會疊字。
#        legend = QRectF(rect.left(), plot.bottom() + 1, rect.width(), 13)
#        p.setPen(QColor(TOKENS["text_secondary"]))
#        p.drawText(legend, Qt.AlignLeft | Qt.AlignVCenter, "black")
#        p.drawText(legend, Qt.AlignRight | Qt.AlignVCenter, "white")
#        p.drawText(legend, Qt.AlignCenter, "outline = before · filled = after")
#
#
#class ProfileInspector(Inspector):
#    """`roi_profile`：投影曲線 + 找到的轉折 + 選中的那一段。
#
#    這一塊是 F7-11 就做好的（``widgets.ProfilePanel``），只是當時直接掛在預覽
#    面板上 —— 也就是一條**跟儀表機制平行的路**。兩條路並存的下場是：加新面板的
#    人不知道該走哪一條，然後兩邊各長一半。所以把它收進來，畫的還是同一個元件。
#
#    「敏感度要調多少」對不會寫 code 的人是沒有答案的問題，除非他看得到曲線、
#    看得到目前抓到幾條線、看得到線落在哪 —— 沒有這個面板，那張卡就只是另一個
#    要盲填的數字。
#    """
#
#    title = "Profile"
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        from .widgets import ProfilePanel
#
#        lay = QVBoxLayout(self)
#        lay.setContentsMargins(0, 0, 0, 0)
#        self.panel = ProfilePanel(self)
#        # 原本掛在預覽面板上時它是**固定高**（那裡的高度是搶來的）。搬進儀表
#        # 之後那一格本來就是給它的，不撐開的話曲線只佔下半截、上面一片空白。
#        self.panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
#        lay.addWidget(self.panel)
#
#    def region(self) -> str:
#        return str(self.params.get("roi_out") or "")
#
#    def set_context(self, *a, **kw) -> None:   # noqa: D102
#        super().set_context(*a, **kw)
#        profiles = dict(self.meta.get("profiles") or {})
#        name = self.region()
#        self.panel.set_data(name, profiles.get(name))
#
#    def has_data(self) -> bool:
#        return bool(self.panel.has_data())
#
#    def summary(self) -> str:
#        return self.panel.summary()
#
#    def paintEvent(self, _e) -> None:          # noqa: D102 - 內容由子元件畫
#        pass
#
#
#class TemplateInspector(Inspector):
#    """`roi_template`：三道閘門各自過了沒，以及這張 patch 對到哪個相位。
#
#    為什麼是這三根柱子
#    ------------------
#    定位失敗的時候，卡片只講「定不出來，退回整張圖」。但那有三個完全不同的
#    原因，而**處置完全不同**：
#
#    * **match 太低** —— 模板不對（或這批圖跟建模板那張差太多）；
#    * **certainty 太低** —— 對得上的位置不只一個（週期性太強或門檻太緊）；
#    * **structure 太低** —— **這張 patch 上根本沒有東西可比**。這個不是要調
#      參數，是本來就該退回整張圖。
#
#    分不出來的話，使用者會一直去調前兩個門檻，而問題其實在第三個。
#    """
#
#    title = "Match"
#
#    _GATES = (("match", "score", "min_score", 1.0),
#              ("certainty", "margin", "min_margin", 1.0),
#              ("structure", "structure", "min_structure", 40.0))
#
#    def record(self) -> Dict[str, Any]:
#        templates = dict(self.meta.get("templates") or {})
#        name = str(self.params.get("roi_out") or "")
#        return dict(templates.get(name) or (
#            list(templates.values())[0] if len(templates) == 1 else {}))
#
#    def has_data(self) -> bool:
#        return bool(self.record())
#
#    def empty_reason(self) -> str:
#        if not str(self.params.get("template") or "").strip():
#            return ("No template yet — build one from a full-size image, then "
#                    "this panel shows why each defect did or did not match.")
#        return "Select a defect to see how well it matched the template."
#
#    def gates(self) -> List[Tuple[str, float, float, bool]]:
#        """``(名稱, 量到的值, 門檻, 過了沒)``。"""
#        rec = self.record()
#        out = []
#        for label, key, param, _full in self._GATES:
#            got = float(rec.get(key, 0.0) or 0.0)
#            need = float(self.params.get(param, 0.0) or 0.0)
#            out.append((label, got, need, got >= need))
#        return out
#
#    def failing(self) -> List[str]:
#        return [g[0] for g in self.gates() if not g[3]]
#
#    def summary(self) -> str:
#        rec = self.record()
#        if not rec:
#            return ""
#        if rec.get("ok"):
#            return ("matched at phase %d,%d · %s"
#                    % (int(rec.get("phase_x", 0)), int(rec.get("phase_y", 0)),
#                       " · ".join("%s %.2f" % (g[0], g[1])
#                                  for g in self.gates())))
#        bad = self.failing()
#        why = {
#            "structure": ("this patch has nothing to match — it sits inside "
#                          "one material. That is not a setting to fix; the "
#                          "region falls back to the whole image, which is the "
#                          "right answer here."),
#            "certainty": ("more than one position fits equally well. Lower "
#                          "“Minimum certainty” only if you can live with a "
#                          "coin flip."),
#            "match": ("the patch does not look like the template. Check the "
#                      "template was built from this layer."),
#        }
#        first = bad[0] if bad else "match"
#        return "could not place the region — %s: %s" % (first, why[first])
#
#    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
#        gates = self.gates()
#        row_h = min(30.0, rect.height() / (len(gates) + 1))
#        for i, ((label, got, need, ok), (_l, _k, _p, full)) in enumerate(
#                zip(gates, self._GATES)):
#            band = QRectF(rect.left(), rect.top() + i * row_h,
#                          rect.width(), row_h - 4)
#            p.setPen(QColor(TOKENS["text_secondary"]))
#            p.drawText(QRectF(band.left(), band.top(), 76, band.height()),
#                       Qt.AlignLeft | Qt.AlignVCenter, label)
#
#            bar = QRectF(band.left() + 80, band.top() + band.height() / 2 - 5,
#                         max(20.0, band.width() - 150), 10)
#            p.setPen(Qt.NoPen)
#            p.setBrush(QBrush(QColor(TOKENS["hover_warm_strong"])))
#            p.drawRoundedRect(bar, 3, 3)
#            frac = max(0.0, min(1.0, got / full if full else 0.0))
#            p.setBrush(QBrush(QColor(TOKENS["success"] if ok
#                                     else TOKENS["danger_text"])))
#            p.drawRoundedRect(QRectF(bar.left(), bar.top(),
#                                     max(2.0, bar.width() * frac),
#                                     bar.height()), 3, 3)
#            # 門檻線：沒有它，柱子的長度沒有意義（多長才算夠？）
#            nx = bar.left() + bar.width() * max(0.0, min(1.0, need / full
#                                                         if full else 0.0))
#            p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.4))
#            p.drawLine(QPointF(nx, bar.top() - 3), QPointF(nx, bar.bottom() + 3))
#
#            p.setPen(QColor(TOKENS["text_primary"]))
#            p.drawText(QRectF(bar.right() + 8, band.top(), 62, band.height()),
#                       Qt.AlignRight | Qt.AlignVCenter, "%.2f" % got)
#
#        rec = self.record()
#        p.setPen(QColor(TOKENS["text_secondary"]))
#        p.drawText(QRectF(rect.left(), rect.bottom() - 14, rect.width(), 14),
#                   Qt.AlignLeft | Qt.AlignVCenter,
#                   "cell %d × %d px · phase %d,%d · line = the threshold"
#                   % (int(rec.get("cell_w", 0)), int(rec.get("cell_h", 0)),
#                      int(rec.get("phase_x", 0)), int(rec.get("phase_y", 0))))
#
#
#class MeasureInspector(Inspector):
#    """量測卡共用：**這張卡自己產出的每個數字，整批長什麼樣、這一顆站在哪。**
#
#    為什麼是這一張圖
#    ----------------
#    `blob_dist_center 11.170` 單獨存在回答不了任何問題。而調一張量測卡的時候，
#    要問的其實是：**我把參數設成這樣，量出來的東西分不分得開？**
#
#    分布回答得了：擠成一根柱子 = 這個特徵對這批資料沒有鑑別力（不管門檻設哪裡
#    都一樣）；分成兩坨 = 有東西可以分。而「這一顆在哪裡」讓使用者把畫面上看到
#    的缺陷跟數字連起來 —— 那是他唯一能校準自己直覺的方式。
#
#    只列**這張卡的**特徵（`Step.resolve_features`，含 output_prefix），
#    不是整份 feature 表 —— 那是 ADC 的事，不是這張卡的事。
#    """
#
#    title = "Spread"
#
#    #: 一次畫幾條。面板不高，六條以上每一條就只剩幾個畫素高。
#    MAX_ROWS = 5
#    BINS = 28
#
#    def rows(self) -> List[str]:
#        names = [n for n in self.feature_names if self.feature_values(n)]
#        return names[:self.MAX_ROWS]
#
#    def has_data(self) -> bool:
#        return bool(self.rows())
#
#    def empty_reason(self) -> str:
#        return ("Run a trial to see how this card's numbers are spread across "
#                "the batch. One value on its own cannot tell you whether it "
#                "separates anything.")
#
#    def percentile_of(self, name: str) -> Optional[float]:
#        """這一顆在整批裡的百分位（0–100）。"""
#        vals = self.feature_values(name)
#        here = self.this_value(name)
#        if not vals or here is None:
#            return None
#        below = sum(1 for v in vals if v < here)
#        return 100.0 * below / float(len(vals))
#
#    def summary(self) -> str:
#        names = self.rows()
#        if not names:
#            return ""
#        flat = [n for n in names if self._is_flat(n)]
#        text = "%d values over %d defects" % (len(names),
#                                              len(self.feature_values(names[0])))
#        here = [n for n in names if self.percentile_of(n) is not None
#                and self.percentile_of(n) >= 95.0]
#        if here:
#            text += ("  ·  this defect is in the top 5%% for %s"
#                     % ", ".join(here))
#        if flat:
#            text += ("  ⚠ %s barely varies across the batch — no threshold on "
#                     "it will separate anything." % ", ".join(flat))
#        return text
#
#    def _is_flat(self, name: str) -> bool:
#        """整批幾乎同一個值 = 這個特徵對這批資料沒有鑑別力。"""
#        vals = self.feature_values(name)
#        if len(vals) < 4:
#            return False
#        lo, hi = min(vals), max(vals)
#        if hi - lo <= 0:
#            return True
#        mid = (abs(lo) + abs(hi)) / 2.0 or 1.0
#        return (hi - lo) / mid < 0.01
#
#    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
#        names = self.rows()
#        row_h = rect.height() / float(len(names))
#        for i, name in enumerate(names):
#            band = QRectF(rect.left(), rect.top() + i * row_h,
#                          rect.width(), row_h - 2)
#            self._paint_row(p, band, name)
#
#    def _paint_row(self, p: QPainter, band: QRectF, name: str) -> None:
#        vals = self.feature_values(name)
#        lo, hi = min(vals), max(vals)
#        if hi <= lo:
#            hi = lo + 1.0
#
#        label = QRectF(band.left(), band.top(), 116, band.height())
#        p.setPen(QColor(TOKENS["text_secondary"]))
#        fm = p.fontMetrics()
#        p.drawText(label, Qt.AlignLeft | Qt.AlignVCenter,
#                   fm.elidedText(name, Qt.ElideRight, int(label.width()) - 4))
#
#        value = QRectF(band.right() - 74, band.top(), 74, band.height())
#        here = self.this_value(name)
#        p.setPen(QColor(TOKENS["text_primary"]))
#        p.drawText(value, Qt.AlignRight | Qt.AlignVCenter,
#                   "—" if here is None else _fmt(here))
#
#        plot = QRectF(label.right() + 4, band.top() + 2,
#                      value.left() - label.right() - 10,
#                      max(6.0, band.height() - 6))
#        if plot.width() < 20:
#            return
#
#        counts = [0] * self.BINS
#        for v in vals:
#            k = int((v - lo) / (hi - lo) * (self.BINS - 1))
#            counts[max(0, min(self.BINS - 1, k))] += 1
#        top = max(counts) or 1
#        bw = plot.width() / float(self.BINS)
#        col = QColor(TOKENS["accent"])
#        col.setAlpha(150)
#        p.setPen(Qt.NoPen)
#        p.setBrush(QBrush(col))
#        for k, c in enumerate(counts):
#            h = (c / float(top)) * plot.height()
#            p.drawRect(QRectF(plot.left() + k * bw, plot.bottom() - h,
#                              max(1.0, bw - 0.5), h))
#
#        # 這一顆在哪裡 —— 沒有這條線，分布只是一張統計圖，跟眼前這顆缺陷無關。
#        #
#        # 會落在範圍外是**正常的**：改了參數之後預覽會立刻重算，而整批還是上一次
#        # 跑的。那時候把線畫到圖外（會蓋到旁邊的文字）比不畫更糟，所以夾回邊界
#        # 並且畫成箭頭 —— 「在這個方向的外面」也是一個答案。
#        if here is not None:
#            frac = (here - lo) / (hi - lo)
#            outside = frac < 0.0 or frac > 1.0
#            x = plot.left() + min(1.0, max(0.0, frac)) * plot.width()
#            p.setPen(QPen(QColor(TOKENS["danger_text"]), 1.6))
#            p.drawLine(QPointF(x, plot.top() - 2), QPointF(x, plot.bottom() + 2))
#            if outside:
#                p.setBrush(QBrush(QColor(TOKENS["danger_text"])))
#                p.setPen(Qt.NoPen)
#                tip = -5.0 if frac < 0.0 else 5.0
#                mid = (plot.top() + plot.bottom()) / 2.0
#                # QPolygonF，不是三個散的 QPointF —— 後者在 PySide6 綁到別的
#                # overload，直接 segfault（不是例外，是整個行程掛掉）。
#                p.drawPolygon(QPolygonF([QPointF(x + tip, mid),
#                                         QPointF(x, mid - 4.0),
#                                         QPointF(x, mid + 4.0)]))
#
#
#def _fmt(v: float) -> str:
#    a = abs(v)
#    if a >= 1000 or (a and a < 0.01):
#        return "%.3g" % v
#    return "%.3f" % v if a < 100 else "%.1f" % v
#
#
#class InputInspector(Inspector):
#    """Load images：**哪一頁變成哪一條流**，以及每一頁載進來長什麼樣。
#
#    為什麼這一張最先要做
#    --------------------
#    「每顆 defect 的第一張是 test、第二張是 ref」是這個專案**第一條待廠內驗證
#    的假設**（CLAUDE.md §8）。它錯了的話，diff 會整個反號、所有分數都是錯的 ——
#    而畫面上完全看不出來，因為兩張圖本來就長得很像。
#
#    目前唯一的驗證方式是另外跑 ``fab_probe/probe_tiff.py``。把配對關係跟每一頁
#    的平均灰階直接攤在這裡，使用者載入第一份真資料的當下就會看到不對勁。
#
#    資料來自 Load 卡放進 ``ctx.meta['input']`` 的那一份 —— 也就是引擎**實際載
#    進來的東西**，不是 UI 從檔名猜的。
#    """
#
#    title = "Input"
#
#    def info(self) -> Dict[str, Any]:
#        return dict(self.meta.get("input") or {})
#
#    def pages(self) -> List[Dict[str, Any]]:
#        return [dict(d) for d in (self.info().get("pages") or [])]
#
#    def has_data(self) -> bool:
#        return bool(self.pages())
#
#    def empty_reason(self) -> str:
#        return ("Select a defect to see which page of the TIFF became which "
#                "image stream.")
#
#    def summary(self) -> str:
#        pages = self.pages()
#        if not pages:
#            return ""
#        info = self.info()
#        bits = ["defect %s" % (info.get("defect_id") or "?")]
#        die = info.get("die") or []
#        if len(die) == 2:
#            bits.append("die %d,%d" % (int(die[0]), int(die[1])))
#        if info.get("nm_per_px"):
#            bits.append("%.2f nm/px" % float(info["nm_per_px"]))
#        else:
#            # 這也是待驗證假設之一：找不到來源，CD 的 nm 值因此是 0。
#            bits.append("nm/px unknown — CD in nm will read 0")
#        return " · ".join(bits)
#
#    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
#        pages = self.pages()
#        head = QRectF(rect.left(), rect.top(), rect.width(), 15)
#        p.setPen(QColor(TOKENS["text_secondary"]))
#        p.drawText(head, Qt.AlignLeft | Qt.AlignVCenter,
#                   "page → stream        size        mean grey")
#
#        row_h = min(20.0, max(14.0, (rect.height() - 18) / max(1, len(pages))))
#        means = [d.get("mean") for d in pages if d.get("mean") is not None]
#        spread = (max(means) - min(means)) if len(means) > 1 else 0.0
#        for i, d in enumerate(pages):
#            y = rect.top() + 18 + i * row_h
#            band = QRectF(rect.left(), y, rect.width(), row_h)
#            page = d.get("page")
#            p.setPen(QColor(TOKENS["text_primary"]))
#            p.drawText(QRectF(band.left(), band.top(), 150, band.height()),
#                       Qt.AlignLeft | Qt.AlignVCenter,
#                       "%s → %s" % ("page %d" % page if page is not None
#                                    else "file", d.get("channel", "?")))
#            shape = d.get("shape") or []
#            p.setPen(QColor(TOKENS["text_secondary"]))
#            p.drawText(QRectF(band.left() + 150, band.top(), 90, band.height()),
#                       Qt.AlignLeft | Qt.AlignVCenter,
#                       "%d × %d" % (shape[1], shape[0]) if len(shape) == 2 else "—")
#            mean = d.get("mean")
#            p.drawText(QRectF(band.left() + 240, band.top(), 70, band.height()),
#                       Qt.AlignLeft | Qt.AlignVCenter,
#                       "—" if mean is None else "%.1f" % mean)
#
#        if spread >= 8.0:
#            # 兩張本來就該長得幾乎一樣（同一個位置、同一次掃描）。差很多的時候
#            # 最可能的解釋就是配對搞錯了 —— 那正是這個面板存在的理由。
#            p.setPen(QColor(TOKENS["warning"]))
#            p.drawText(QRectF(rect.left(), rect.bottom() - 14, rect.width(), 14),
#                       Qt.AlignLeft | Qt.AlignVCenter,
#                       "mean grey differs by %.0f between pages — check the "
#                       "page order" % spread)
#
#
##: step key -> 儀表。沒列在這裡的卡用原本的特徵表（見模組說明的約定 1）。
##:
##: Enhance 九張卡共用同一個儀表：它們做的事不同，但**要回答的問題是同一個**
##: （我把資訊弄掉了嗎）。
#INSPECTORS: Dict[str, type] = {
#    "load_patch": InputInspector,
#    "roi_profile": ProfileInspector,
#    "roi_template": TemplateInspector,
#    "align": AlignInspector,
#    "brightness_contrast": EnhanceInspector,
#    "gamma": EnhanceInspector,
#    "denoise": EnhanceInspector,
#    "flatten": EnhanceInspector,
#    "invert": EnhanceInspector,
#    "local_contrast": EnhanceInspector,
#    "glv_mask_norm": EnhanceInspector,
#    "hist_match": EnhanceInspector,
#    "percentile_norm": EnhanceInspector,
#    "glv_stats": MeasureInspector,
#    "cd_measure": MeasureInspector,
#    "focus_quality": MeasureInspector,
#    "roi_snr": MeasureInspector,
#    "cell_period": MeasureInspector,
#    "blob_segment": MeasureInspector,
#}
#
#
#def inspector_for(step_key: str) -> Optional[type]:
#    return INSPECTORS.get(str(step_key or ""))
#
#F 40b66dc163f75a9936692ca8bd257143bb9d8359 299 adept/ui/region_check.py
## ADEPT Studio — 區域跨顆檢視 (F7-11 第三批).
#"""把具名區域畫在**很多顆** defect 的縮圖上，一次看完。
#
#為什麼一張圖不夠
#----------------
#調一個區域的設定時，看單顆是不夠的：**在第 1 顆剛好的設定，第 50 顆可能整個
#偏掉。** 而這正是這一整段的前提 —— patch 是以缺陷為中心裁的，所以結構在每張
#patch 裡的位置本來就不一樣。設定對不對，是一個**關於整批**的問題，
#不是關於這一張圖的問題。
#
#所以這個視窗只回答一個問題：**這個區域設定，在整批上普遍成立嗎？**
#畫面上因此只有三件事：每顆的縮圖、框、以及「這顆定位成功了沒」。
#
#「只看失敗的」是預設就想得到的操作
#----------------------------------
#定位失敗的那些才是要看的。它們可能是「本來就沒有結構可認」（正常，整張量就對），
#也可能是「參數設得太緊」（要調）。兩者只有看圖分得出來，所以要能一鍵只看它們。
#
#本模組的 :func:`check_regions` 不碰 Qt，可以 headless 測試；
#Qt 的部分只負責把它算出來的東西畫出來。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List, Optional, Sequence, Tuple
#
#import numpy as np
#from PySide6.QtCore import QRectF, Qt, Signal
#from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
#from PySide6.QtWidgets import (
#    QCheckBox,
#    QDialog,
#    QFrame,
#    QGridLayout,
#    QHBoxLayout,
#    QLabel,
#    QScrollArea,
#    QVBoxLayout,
#    QWidget,
#)
#
#from adept.core.pipeline import get_step
#from adept.core.pipeline.engine import run_defect
#
#from .gallery import make_thumb, thumb_placement
#from .theme import TOKENS
#from .widgets import _qimage_from_uint8
#
#__all__ = ["check_regions", "regions_of_node", "RegionThumb", "RegionCheckWindow"]
#
##: 一次最多檢查幾顆（再多也看不完，而且每顆都要跑一次 pipeline）。
#MAX_CHECK = 200
#
#
#def regions_of_node(node: Any) -> List[str]:
#    """一個節點會定義哪些具名區域（不是 Region 卡就是空清單）。"""
#    try:
#        step_cls = get_step(node.step)
#        return [str(r) for r in step_cls.resolve_regions_out(node.params)]
#    except Exception:                       # noqa: BLE001 — 顯示用
#        return []
#
#
#def check_regions(recipe: Any, items: Sequence[Any], kind: str, node_id: str,
#                  regions: Sequence[str], thumb_size: int = 120,
#                  source: Optional[str] = None) -> List[Dict[str, Any]]:
#    """對每一顆跑到 ``node_id`` 為止，取出縮圖與該節點定義的區域框。
#
#    回傳每顆一個 dict：``defect_id`` / ``thumb``（uint8 方形縮圖）/
#    ``boxes``（``[(區域名, (x, y, w, h)), …]``，座標已經是**縮圖上的像素**）/
#    ``located``（這顆定位成功了沒）/ ``error``。
#
#    **永不 raise** —— 單顆出錯只會變成一顆 ``error`` 不為 None 的格子，
#    跟引擎「單顆爆不殺整批」的契約一致。
#    """
#    out: List[Dict[str, Any]] = []
#    wanted = [str(r) for r in regions]
#
#    for item in list(items)[:MAX_CHECK]:
#        defect_id = str(getattr(item, "defect_id", ""))
#        entry: Dict[str, Any] = {"defect_id": defect_id, "thumb": None,
#                                 "boxes": [], "located": True, "error": None}
#        try:
#            res = run_defect(recipe, item, kind, keep_context=True,
#                             upto_node=node_id)
#        except Exception as e:              # noqa: BLE001 — 合約外的意外
#            entry["error"] = "%s: %s" % (type(e).__name__, e)
#            out.append(entry)
#            continue
#
#        ctx = getattr(res, "context", None)
#        images = dict(getattr(ctx, "images", {}) or {}) if ctx is not None else {}
#        if not res.ok:
#            entry["error"] = res.error
#        img = images.get(str(source)) if source else None
#        if img is None:
#            for key in ("ref", "test"):      # 定位是在 ref 上做的，優先顯示它
#                if key in images:
#                    img = images[key]
#                    break
#        if img is None and images:
#            img = next(iter(images.values()))
#        if img is None:
#            entry["error"] = entry["error"] or "no image to show"
#            out.append(entry)
#            continue
#
#        arr = np.asarray(img)
#        entry["thumb"] = make_thumb(arr, thumb_size)
#        x0, y0, tw, th = thumb_placement(arr.shape, thumb_size)
#
#        names = set(ctx.roi_names() if ctx is not None else [])
#        for name in wanted:
#            if name not in names:
#                continue
#            nx, ny, nw, nh = ctx.require_roi(name).norm_rect
#            entry["boxes"].append((name, (
#                x0 + nx * tw, y0 + ny * th, max(1.0, nw * tw), max(1.0, nh * th))))
#
#        # ``locate_ok`` 是投影定位卡吐的旗標；沒有這個特徵的 Region 卡
#        # （例如手畫的框）一律當成定位成功 —— 它本來就不需要定位。
#        feats = dict(getattr(res, "features", {}) or {})
#        flags = [v for k, v in feats.items() if k.endswith("locate_ok")]
#        entry["located"] = all(float(v) > 0.5 for v in flags) if flags else True
#        out.append(entry)
#
#    return out
#
#
#def summarize(results: Sequence[Dict[str, Any]]) -> str:
#    """一行摘要（測試與標題列共用；不用去讀畫素）。"""
#    total = len(results)
#    failed = sum(1 for r in results if not r.get("located", True))
#    errors = sum(1 for r in results if r.get("error"))
#    parts = ["%d defects" % total,
#             "%d located" % (total - failed),
#             "%d fell back to the whole image" % failed]
#    if errors:
#        parts.append("%d could not be computed" % errors)
#    return " · ".join(parts)
#
#
#class RegionThumb(QFrame):
#    """一格：縮圖 + 區域框 + defect id；定位失敗的用邊框標出來。"""
#
#    clicked = Signal(str)
#
#    def __init__(self, entry: Dict[str, Any], parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.entry = dict(entry)
#        self.defect_id = str(entry.get("defect_id", ""))
#        self.setCursor(Qt.PointingHandCursor)
#        thumb = entry.get("thumb")
#        self._size = int(thumb.shape[0]) if thumb is not None else 120
#        self.setFixedSize(self._size + 8, self._size + 24)
#        tip = self.defect_id
#        if entry.get("error"):
#            tip += "\n%s" % entry["error"]
#        elif not entry.get("located", True):
#            tip += "\nno structure found - measured the whole image"
#        self.setToolTip(tip)
#
#    def located(self) -> bool:
#        return bool(self.entry.get("located", True))
#
#    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
#        if e.button() == Qt.LeftButton:
#            self.clicked.emit(self.defect_id)
#        super().mousePressEvent(e)
#
#    def paintEvent(self, _e) -> None:          # noqa: D102 - Qt hook
#        p = QPainter(self)
#        p.setRenderHint(QPainter.Antialiasing, True)
#        thumb = self.entry.get("thumb")
#        s = self._size
#
#        if thumb is not None:
#            p.drawPixmap(4, 4, QPixmap.fromImage(_qimage_from_uint8(thumb)))
#        else:
#            p.fillRect(QRectF(4, 4, s, s), QColor(TOKENS["disabled_bg"]))
#
#        # 第一個框是**使用者命名的那個區域**，其餘是它的鄰段。用實線 vs 虛線
#        # 分開 —— 三個一樣的藍框排在一起，看不出哪個是主角。
#        for i, (_name, (x, y, w, h)) in enumerate(self.entry.get("boxes") or []):
#            pen = QPen(QColor(TOKENS["accent"]), 1.8)
#            if i:
#                pen.setWidthF(1.2)
#                pen.setStyle(Qt.DashLine)
#            p.setPen(pen)
#            p.setBrush(Qt.NoBrush)
#            p.drawRect(QRectF(4 + x, 4 + y, w, h))
#
#        # 定位失敗 / 算不出來的用外框標出來 —— 這是這個視窗最重要的一個訊號
#        if self.entry.get("error"):
#            edge = QColor(TOKENS["danger"])
#        elif not self.located():
#            edge = QColor(TOKENS["warning"])
#        else:
#            edge = QColor(TOKENS["border_default"])
#        p.setPen(QPen(edge, 2.0))
#        p.setBrush(Qt.NoBrush)
#        p.drawRect(QRectF(3, 3, s + 2, s + 2))
#
#        p.setPen(QColor(TOKENS["text_secondary"]))
#        f = p.font()
#        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
#        p.setFont(f)
#        p.drawText(QRectF(4, s + 6, s, 14), Qt.AlignHCenter | Qt.AlignVCenter,
#                   self.defect_id)
#        p.end()
#
#
#class RegionCheckWindow(QDialog):
#    """區域跨顆檢視。非 modal —— 使用者要能一邊看它、一邊在主視窗調參數。"""
#
#    defect_activated = Signal(str)
#
#    _COLUMNS = 6
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setWindowTitle("Check region across defects")
#        self.setModal(False)
#        self.resize(880, 620)
#        self._results: List[Dict[str, Any]] = []
#        self._cells: List[RegionThumb] = []
#
#        outer = QVBoxLayout(self)
#        outer.setContentsMargins(10, 10, 10, 10)
#        outer.setSpacing(8)
#
#        head = QHBoxLayout()
#        self.title = QLabel("", self)
#        self.title.setObjectName("paramTitle")
#        head.addWidget(self.title, 1)
#        self.only_failed = QCheckBox("Only the ones that fell back", self)
#        self.only_failed.setToolTip(
#            "Show only the defects where no structure could be found. Those are "
#            "either patches with nothing to lock onto - which is fine, the whole "
#            "image is the right thing to measure there - or a sign the settings "
#            "are too tight. Looking at them is the only way to tell.")
#        self.only_failed.toggled.connect(lambda _v: self._relayout())
#        head.addWidget(self.only_failed)
#        outer.addLayout(head)
#
#        self.summary = QLabel("", self)
#        self.summary.setObjectName("paramHint")
#        self.summary.setWordWrap(True)
#        outer.addWidget(self.summary)
#
#        self._scroll = QScrollArea(self)
#        self._scroll.setWidgetResizable(True)
#        self._scroll.setFrameShape(QScrollArea.NoFrame)
#        self._host = QWidget()
#        self._grid = QGridLayout(self._host)
#        self._grid.setContentsMargins(2, 2, 2, 2)
#        self._grid.setSpacing(6)
#        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
#        self._scroll.setWidget(self._host)
#        outer.addWidget(self._scroll, 1)
#
#    # ---- 對外 -------------------------------------------------------------
#    def set_results(self, regions: Sequence[str],
#                    results: Sequence[Dict[str, Any]]) -> None:
#        self._results = list(results or [])
#        names = ", ".join(str(r) for r in regions) or "(no region)"
#        self.title.setText("Region: %s" % names)
#        self.summary.setText(summarize(self._results))
#        self._relayout()
#
#    def summary_text(self) -> str:
#        return self.summary.text()
#
#    def visible_ids(self) -> List[str]:
#        """目前排在畫面上的 defect id（測試用；不必去讀畫素）。"""
#        return [c.defect_id for c in self._cells]
#
#    def failed_ids(self) -> List[str]:
#        return [str(r.get("defect_id", "")) for r in self._results
#                if not r.get("located", True) or r.get("error")]
#
#    # ---- 內部 -------------------------------------------------------------
#    def _relayout(self) -> None:
#        for cell in self._cells:
#            self._grid.removeWidget(cell)
#            cell.setParent(None)
#            cell.deleteLater()
#        self._cells = []
#
#        shown = self._results
#        if self.only_failed.isChecked():
#            shown = [r for r in shown
#                     if not r.get("located", True) or r.get("error")]
#
#        for i, entry in enumerate(shown):
#            cell = RegionThumb(entry, self._host)
#            cell.clicked.connect(self.defect_activated)
#            self._grid.addWidget(cell, i // self._COLUMNS, i % self._COLUMNS)
#            self._cells.append(cell)
#
#F fa8845c4baad7e590da0f7190e56d979c8237db5 151 adept/ui/results.py
## ADEPT Studio Results 視窗 — authored 2026-07-28 (F7-5).
#"""``ResultsWindow`` —— 跑完一批之後才有意義的東西，全部搬到這裡。
#
#為什麼要拆出去
#--------------
#主視窗一直是四區塊 + 底部全寬直方圖，於是「編流程」與「看整批結果」兩種
#模式擠在同一個畫面上。使用者的話是：**直方圖不是不重要，而是它不是必要 ——
#主介面的分析區應該乾淨。**
#
#拆的界線就在「這個東西要不要先跑過一批才有意義」：
#
#===================  ==========================================
#主視窗 Workspace     編流程 · 看單顆 · 調參數
#Results 視窗         分數分佈 · Gallery · 輸出
#===================  ==========================================
#
#直方圖與 Gallery 都屬於後者，所以一起搬。Export 本來就是對話框，
#按鈕也一併放進來 —— 「跑完 → 看分佈 → 掃縮圖 → 輸出」是同一段動線。
#
#**秒回不能弄丟**
#----------------
#拖門檻線目前走的是 ``viewmodel.rebin()`` 的純計算路徑（不重跑影像）。
#搬家之後訊號改成由本視窗轉發給 Studio，但走的仍是同一條路 ——
#``threshold_changed`` 只重算 bin 數、放開才 ``threshold_committed`` 寫回 model。
#這條性質有測試鎖（``tests/test_ui_results.py``）。
#
#視窗而不是對話框
#----------------
#用 ``QMainWindow`` 是為了能有自己的工具列與狀態列，而且**非 modal** ——
#使用者要能一邊看結果一邊回主視窗改參數。關掉它不會丟掉結果，
#再跑一次或按主視窗的 Gallery 入口就會回來。
#"""
#from __future__ import annotations
#
#from typing import Any, Optional, Sequence
#
#from PySide6.QtCore import Qt, Signal
#from PySide6.QtWidgets import (
#    QLabel,
#    QMainWindow,
#    QSizePolicy,
#    QSplitter,
#    QStatusBar,
#    QToolBar,
#    QToolButton,
#    QWidget,
#)
#
#from .gallery import GalleryPanel
#from .widgets import HistogramWidget
#
#__all__ = ["ResultsWindow"]
#
#
#class ResultsWindow(QMainWindow):
#    """一批結果的檢視：Gallery（上）+ 分數分佈（下）+ 輸出入口。
#
#    本視窗**不自己驅動任何東西** —— 所有互動都轉成訊號交給
#    :class:`~adept.ui.studio.StudioWindow`，跟 ``WelcomeDialog`` 同一個慣例。
#    這樣它可以單獨測，Studio 也可以在沒有它的情況下跑完整流程。
#    """
#
#    export_requested = Signal()
#
#    def __init__(self, parent: Optional[QWidget] = None) -> None:
#        super().__init__(parent)
#        self.setWindowTitle("ADEPT — Results")
#        self.setWindowFlag(Qt.Window, True)
#        self.resize(980, 700)
#
#        bar = QToolBar("Results", self)
#        bar.setMovable(False)
#        bar.setFloatable(False)
#        self.toolbar = bar
#        self.addToolBar(bar)
#
#        self.summary_label = QLabel("No results yet.", bar)
#        self.summary_label.setObjectName("paramHint")
#        bar.addWidget(self.summary_label)
#
#        spacer = QWidget(bar)
#        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
#        bar.addWidget(spacer)
#
#        self.btn_export = QToolButton(self)
#        self.btn_export.setText("Export…")
#        self.btn_export.setToolButtonStyle(Qt.ToolButtonTextOnly)
#        self.btn_export.setCursor(Qt.PointingHandCursor)
#        self.btn_export.setObjectName("primary")
#        self.btn_export.setToolTip(
#            "Write these results back to KLARF, or produce reports and overlays")
#        self.btn_export.clicked.connect(self.export_requested)
#        bar.addWidget(self.btn_export)
#        self.set_export_enabled(False)      # 還沒有結果（同 A1 的可用性規則）
#
#        self.gallery = GalleryPanel(self)
#        self.histogram = HistogramWidget(self)
#        self.histogram.setMinimumHeight(150)
#
#        split = QSplitter(Qt.Vertical, self)
#        split.addWidget(self.gallery)
#        split.addWidget(self.histogram)
#        split.setStretchFactor(0, 4)
#        split.setStretchFactor(1, 1)
#        split.setSizes([500, 190])
#        self.splitter = split
#        self.setCentralWidget(split)
#        self.setStatusBar(QStatusBar(self))
#
#    # ---- 對外 -------------------------------------------------------------
#    def set_summary(self, text: str) -> None:
#        """工具列左側的一句話（「跑了幾顆、成功幾顆、花多久」）。"""
#        self.summary_label.setText(str(text or ""))
#
#    def summary_text(self) -> str:
#        return self.summary_label.text()
#
#    def set_export_enabled(self, enabled: bool) -> None:
#        self.btn_export.setEnabled(bool(enabled))
#        self.btn_export.setToolTip(
#            "Write these results back to KLARF, or produce reports and overlays"
#            if enabled else "No results yet — run a trial first.")
#
#    def status(self, msg: str) -> None:
#        self.statusBar().showMessage(str(msg))
#
#    def status_text(self) -> str:
#        return self.statusBar().currentMessage()
#
#    def present(self) -> None:
#        """顯示並拉到前面（已經開著就只是 raise，不會閃一下）。"""
#        self.show()
#        self.raise_()
#        self.activateWindow()
#
#    def closeEvent(self, event) -> None:      # noqa: D102 - Qt hook
#        # 關掉不丟結果：下次再跑（或按主視窗的 Gallery 入口）就會回來。
#        super().closeEvent(event)
#
#
#def summarize_run(n_total: int, n_ok: int, elapsed: float,
#                  scores: Sequence[Any] = ()) -> str:
#    """Results 工具列那一行文字（Studio 與測試共用，避免兩邊寫法漂移）。"""
#    n_fail = int(n_total) - int(n_ok)
#    text = "%d defects · %d ok · %d failed · %.1f s" % (
#        int(n_total), int(n_ok), n_fail, float(elapsed))
#    vals = [float(s) for s in (scores or ()) if s is not None]
#    if vals:
#        text += "   score %.4g – %.4g" % (min(vals), max(vals))
#    return text
#
#F 3291d88808ce6ac13388b852978fe9a28f54f016 83 adept/ui/scope.py
## ADEPT Studio 產品範圍開關 — authored 2026-07-28 (F7-1).
#"""Studio 目前支援哪些輸入型別、哪些卡片會出現在卡片庫。
#
#**要把 RSEM 打開，就是改這個檔。** 整包 RSEM 的能力（ingest、Golden Cell、
#週期估測、範例 recipe、測試）全部原封不動留在 core 裡 —— 這裡只是把它們
#從 Studio 的畫面上收起來。
#
#為什麼是「收起來」而不是「刪掉」
#--------------------------------
#使用者的決定是「**暫時**只支援 patch」（F7 D1）。刪掉的話：
#
#* 整個 M4（雙輸入 + Golden Cell）要重做；
#* ``algo/period.py`` 會跟著陪葬 —— 而它的 ``estimate_period`` /
#  ``choose_origin``（相位搜尋）**是之後做 pattern-frame ROI 的唯一工具**
#  （見 ``docs/plans/F7-canvas-and-taxonomy.md`` §4）。那個檔案看起來像是
#  「只有 Golden Cell 在用」，其實不是。
#
#收起來的成本是零；回復的成本是把 ``SUPPORTED_KINDS`` 加一個字串。
#
#CLI 不受影響
#------------
#``python -m adept run`` 照樣吃得下 rsem recipe —— 這裡只管 GUI。
#臨時真的要跑 RSEM 的人不會沒有路走。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List, Sequence
#
#__all__ = [
#    "SUPPORTED_KINDS", "HIDDEN_STEPS", "DEFAULT_KIND",
#    "is_supported_kind", "visible_steps", "recipe_is_supported",
#    "unsupported_kind_message",
#]
#
##: Studio 目前接受的資料集型別（``dataset.kind``）。
##: 加回 ``"rsem"`` 就會讓 RSEM 整條路線重新出現在 GUI 上。
#SUPPORTED_KINDS: Sequence[str] = ("ebi_patch",)
#
##: 只有在不支援的型別下才有意義、因此暫時不列進卡片庫的 step key。
##:
##: * ``golden_cell`` —— 存在的唯一理由是「RSEM 單張沒有 ref，疊一張出來」。
##:   patch 兩兩對應本來就有 ref，這張卡沒有用武之地。
##: * ``cell_period`` —— 唯一用途是餵 ``golden_cell``。
##:
##: 兩張卡仍然註冊在 registry 裡：舊 recipe 載得進來、CLI 跑得動、測試照跑。
#HIDDEN_STEPS: Sequence[str] = ("golden_cell", "cell_period")
#
##: 沒有資料集時 ``RecipeModel`` 用的 route 名稱。
#DEFAULT_KIND: str = SUPPORTED_KINDS[0]
#
#
#def is_supported_kind(kind: Any) -> bool:
#    """這個 ``dataset.kind`` 目前的 Studio 吃不吃得下。"""
#    return str(kind or "") in SUPPORTED_KINDS
#
#
#def visible_steps(steps: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
#    """過掉卡片庫不該顯示的卡（吃 ``Step.describe()`` 的 dict 清單）。"""
#    return [d for d in (steps or [])
#            if str(d.get("key", "")) not in HIDDEN_STEPS]
#
#
#def recipe_is_supported(info: Dict[str, Any]) -> bool:
#    """範本庫要不要列出這份 recipe。
#
#    判準是「**它至少有一條看得懂的 route**」，不是「它只有看得懂的 route」——
#    ``dual_route_basic.json`` 同時定義 ebi_patch 與 rsem，載進來之後
#    ``RecipeModel.from_recipe`` 會挑 ``sorted(routes)[0]``（= ebi_patch），
#    完全跑得動，沒有理由把它藏起來。只有純 rsem 的才會被濾掉。
#    """
#    routes = [str(r) for r in (info or {}).get("routes") or ()]
#    if not routes:
#        return True          # 讀壞的檔案交給對話框顯示紅字，不在這裡吃掉
#    return any(is_supported_kind(r) for r in routes)
#
#
#def unsupported_kind_message(kind: Any) -> str:
#    """載到不支援的資料集時，狀態列要說的話（白話 + 講得出替代路徑）。"""
#    return ("This build of ADEPT Studio only supports EBI patch input "
#            "(test + reference pairs); the dataset you opened is “%s”. "
#            "The command line can still run it: python -m adept run "
#            "<recipe> <klarf>." % (kind or "unknown"))
#
#F ad93d9039420c6cd2fac85e498851557ca3a1595 2759 adept/ui/studio.py
## ADEPT Studio 主視窗 — authored 2026-07-28 (M3 收尾).
#"""``StudioWindow`` —— 把 M3 的元件、view-model 與背景工作接成一台可用的機器。
#
#版面（全部用 QSplitter，使用者拉得動）::
#
#    ┌ 工具列：開啟 KLARF／Recipe／存檔／範本／範例 recipe ｜ 輸出… ｜ 說明
#    │         ｜ 試跑筆數 ▶試跑 ▶全跑                                      ┐
#    ├──────────┬──────────────────────┬──────────────────────────────┤
#    │ 卡片庫    │ 流程（PipelinePanel） │ ［單顆預覽］［Gallery］        │
#    │ Library  │ ──────────────────── │  單顆：◀ ▶ 缺陷選單 / 影像流   │
#    │ ~230px   │ 參數表單 / 分數編輯   │        ImageView              │
#    │          │ （QStackedWidget）    │        特徵表 + 判定 chip     │
#    │          │                      │  Gallery：縮圖牆（同屏比多顆）  │
#    ├──────────┴──────────────────────┴──────────────────────────────┤
#    │ 分數分佈直方圖（可拖門檻線、可點長條）                             │
#    ├─────────────────────────────────────────────────────────────────┤
#    │ 狀態列：進度 / 訊息                                              │
#    └─────────────────────────────────────────────────────────────────┘
#
#五條資料流（別搞混）
#--------------------
#1. **編輯流**：UI 事件 → :class:`~adept.ui.viewmodel.RecipeModel` 的方法 →
#   model 通知 listener → 主視窗刷新 Pipeline/Score 顯示 + 排一次**去抖動
#   （300ms）**的預覽。UI 元件自己**不改** model，也不直接呼叫引擎。
#2. **預覽流**：:class:`~adept.ui.workers.PreviewWorker` 算一顆 defect →
#   ``ready`` → 填影像流下拉 / ImageView / 特徵表 / 判定 chip。
#3. **試跑流**：:class:`~adept.ui.workers.TrialWorker` 跑 N 顆 →
#   ``done`` → 直方圖 + bin 摘要 + Gallery + 狀態列統計。
#4. **縮圖流**（M5）：Gallery 捲到哪就要哪幾張縮圖 —— ``thumbs_requested(ids)``
#   → :class:`ThumbWorker`（背景執行緒讀檔 + :func:`~adept.ui.gallery.make_thumb`）
#   → ``ready(dict)`` → ``set_thumbs``。**解碼絕不在 GUI 執行緒**，而且忙碌時
#   新的請求會合併進待跑集合（``request`` 只累積、不排隊、不阻塞）。
#5. **輸出流**（M5）：工具列「輸出…」→ :class:`~adept.ui.export_dialog.ExportDialog`
#   （試跑/全跑有結果才會亮）。
#
#調參迴圈的兩半（M5 的重點）
#---------------------------
#直方圖點一根長條 → ``bar_clicked(lo, hi)`` → Gallery 只留那個分數區間並自動
#切到 Gallery 分頁；再點同一根（或按掉 Gallery 上的條件 chip）就取消篩選。
#Gallery 雙擊某顆 → ``defect_activated`` → 切回「單顆預覽」並跳到那顆。
#門檻的「秒回」路徑仍然成立：拖曳中只用 :func:`~adept.ui.viewmodel.rebin`
#重算 bin 數（**不寫 model、不重跑**），放開才 ``set_threshold``；
#**點長條不會動到門檻**（見 ``HistogramWidget`` 的 click / drag 判定）。
#
#測試友善 API（完全不開對話框，見 tests/test_ui_studio_smoke.py 與
#tests/test_ui_studio_m5.py）：
#:meth:`StudioWindow.load_dataset_path` / :meth:`~StudioWindow.load_recipe_path` /
#:meth:`~StudioWindow.load_template` / :meth:`~StudioWindow.select_node` /
#:meth:`~StudioWindow.set_defect_index` / :meth:`~StudioWindow.refresh_preview` /
#:meth:`~StudioWindow.run_trial` / :meth:`~StudioWindow.save_recipe_path` /
#:meth:`~StudioWindow.show_gallery` / :meth:`~StudioWindow.show_preview` /
#:meth:`~StudioWindow.request_thumbs` / :meth:`~StudioWindow.open_export_dialog` /
#:meth:`~StudioWindow.show_welcome` / :meth:`~StudioWindow.open_recipe_library` /
#:meth:`~StudioWindow.run_demo`。
#每個進入點都自我保護：沒有資料集 / 流程是空的 → 狀態列提示，不丟例外。
#
#首次開啟導覽（M6）
#------------------
#:class:`~adept.ui.welcome.WelcomeDialog` 是產品的「上車處」：第一次開窗時
#（``show_welcome_on_start`` 預設 ``None`` = 依 QSettings 判斷，且**跑測試時
#一律不跳**）排一次非 modal 的顯示。它的三顆鈕只發訊號，動作由本視窗做 ——
#其中「用範例資料試一次」就是 :meth:`~StudioWindow.run_demo`：產合成資料 →
#載入 → 套 die-to-die 範本 → 試跑 → 切到 Gallery。
#"""
#from __future__ import annotations
#
#import os
#import sys
#import time
#from pathlib import Path
#from typing import Any, Dict, List, Optional, Sequence
#
#from PySide6.QtCore import Qt, QTimer, Signal
#from PySide6.QtGui import QAction, QKeySequence, QShortcut
#from PySide6.QtWidgets import (
#    QApplication,
#    QCheckBox,
#    QComboBox,
#    QDoubleSpinBox,
#    QFileDialog,
#    QHBoxLayout,
#    QLabel,
#    QLineEdit,
#    QMainWindow,
#    QMenu,
#    QMessageBox,
#    QPushButton,
#    QSizePolicy,
#    QProgressBar,
#    QSpinBox,
#    QSplitter,
#    QStackedWidget,
#    QStatusBar,
#    QTabWidget,
#    QToolBar,
#    QToolButton,
#    QVBoxLayout,
#    QWidget,
#)
#
#import adept.core.steps  # noqa: F401 — 觸發卡片註冊（Qt-free、便宜）
#from adept.core.pipeline import ParamError, Recipe, get_step, list_steps
#
#from .export_dialog import ExportDialog
#from .canvas import PipelineCanvas
#from .inspectors import inspector_for
#from .gallery import make_thumb
#from .region_check import MAX_CHECK, RegionCheckWindow, regions_of_node
#from .template_dialog import TemplateDialog
#from .results import ResultsWindow, summarize_run
#from .scope import (
#    is_supported_kind, recipe_is_supported, unsupported_kind_message,
#    visible_steps,
#)
#from .viewmodel import RecipeModel, histogram, rebin
#from .theme import DEFAULT_THEME, THEMES, apply_theme, current_theme
#from .welcome import (
#    RecipeLibraryDialog, WelcomeDialog, save_theme, welcome_disabled,
#)
#from .widgets import (
#    FeatureTable,
#    ImageView,
#    LibraryPanel,
#    ParamForm,
#    PipelinePanel,
#    ProfilePanel,
#    VerdictChip,
#)
#from .workers import (
#    DatasetLoadWorker, PreviewWorker, RegionCheckWorker, TrialWorker,
#    _ThreadedWorker,
#)
#
#__all__ = ["StudioWindow", "ThumbWorker", "TEMPLATE_RECIPE", "DEFAULT_CACHE_DIR",
#           "THUMB_CHANNEL_PRIORITY", "TAB_PREVIEW", "TAB_GALLERY",
#           "DEMO_DIR", "DEMO_DEFECTS", "DEMO_SEED", "generate_demo_lot"]
#
##: 區域跨顆檢視的縮圖邊長（px）。
#REGION_THUMB = 120
#
##: 卡片庫「ADC 判定」段固定顯示的 Score / Bin 項目。它不是 registry 裡的
##: step（每條 pipeline 天生就有一張 ScoreSpec），但三段式的心智模型要完整 ——
##: 使用者要能在庫裡看到「影像 → 算法 → ADC 判定」三段都有東西。點它 = 去編輯分數。
#_SCORE_LIBRARY_KEY = "__score__"
#_SCORE_LIBRARY_ENTRY = {
#    "key": _SCORE_LIBRARY_KEY,
#    "label": "Score / Bin",
#    "category": "adc",
#    "group": "adc",
#    "help": "Combine the measured features into a score and split into bins by a threshold — every pipeline has exactly one; click to edit it.",
#    "requires_ref": False,
#    "params": [],
#    "reads": [],
#    "writes": [],
#    "features_out": ["score"],
#}
#
##: 「載入範本」讀的檔案（repo 內的 die-to-die 範例）。
#TEMPLATE_RECIPE = Path(__file__).resolve().parents[2] / "examples" / "recipes" \
#    / "die_to_die_basic.json"
#
##: 試跑用的影像段快取位置（跨次試跑重用，第二次調參會明顯變快）。
#DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".adept", "cache")
#
##: 「用範例資料試一次」把合成 lot 產在哪（使用者自己的檔案一律不碰）。
#DEMO_DIR = os.path.join(os.path.expanduser("~"), ".adept", "demo_lot")
#
##: 範例資料的 defect 數與 seed（少到一分鐘內跑得完，多到直方圖看得出形狀）。
#DEMO_DEFECTS = 24
#DEMO_SEED = 7
#
##: GUI 試跑用幾個 worker。None = 依 CPU 核心數自動。
##:
##: 歷史：這裡一度必須寫死 1 —— ``run_batch(workers>1)`` 會開
##: ``ProcessPoolExecutor``，而在 fork 為預設啟動法的平台（Linux）上，從
##: :class:`~PySide6.QtCore.QThread`（``TrialWorker`` 就是）裡 fork 會**穩定死鎖**
##: （子行程繼承其他執行緒持有的鎖，卡在啟動階段，progress 一筆都不發）。
##: 已於 ``batch._pool_context()`` 修正：主執行緒仍用 fork（CLI/script 免寫
##: ``if __name__ == "__main__"`` 保護），非主執行緒自動改用 spawn。
##: 迴歸測試見 ``tests/test_batch_thread_safety.py``。
#TRIAL_WORKERS = None
#
##: model 變動 → 重算預覽 的去抖動間隔（毫秒）。拖 spinbox 不會每格都重算。
#PREVIEW_DEBOUNCE_MS = 300
#
##: 主視窗三欄的出廠寬度：卡片庫 | 流程+參數 | 單顆預覽。
##: F7-5 之後預覽拿到最寬的一欄（使用者要求「影像大一點、置中」），
##: 因為直方圖與 Gallery 都搬去 Results 視窗了。
#COLUMN_SIZES = (256, 470, 674)
#
##: 「試跑筆數」的出廠值。載入資料集時會再夾成 ``min(這個值, 資料集顆數)`` ——
##: 對一份只有 24 顆的 lot 顯示 200 沒有任何意義，只會讓人以為自己看錯了。
#DEFAULT_TRIAL_N = 200
#
##: 右欄分頁的索引 —— F7-5 之後右欄只剩單顆預覽，Gallery 搬進 Results 視窗。
##: 常數保留是為了不打壞外部呼叫端；``TAB_GALLERY`` 現在等同「開 Results 視窗」。
#TAB_PREVIEW = 0
#TAB_GALLERY = 1
#
##: Gallery 縮圖要用哪個 channel（依序找第一個有的；都沒有就用第一個 channel）。
#THUMB_CHANNEL_PRIORITY = ("test", "single")
#
#_FEATURE_PLACEHOLDER = "Insert feature ▾"
#_SCORE_HELP = ("The score is an expression whose variables are the feature names "
#               "produced by the pipeline above (e.g. snr_max, blob_area, "
#               "glv_max). score >= threshold -> bin 1, otherwise bin 0. "
#               "You can use + - * / ( ) and sqrt / abs / min / max.")
#
#
#def _fmt(value: Any) -> str:
#    """參數摘要用的短字串（float 去掉多餘的 0）。"""
#    if isinstance(value, bool):
#        return "Yes" if value else "No"
#    if isinstance(value, float):
#        return ("%g" % value)
#    return str(value)
#
#
#def thumb_channel(item: Any) -> Optional[str]:
#    """這顆 defect 的縮圖要讀哪個 channel：``test`` → ``single`` → 第一個有的。"""
#    images = dict(getattr(item, "images", {}) or {})
#    for name in THUMB_CHANNEL_PRIORITY:
#        if name in images:
#            return name
#    for name in images:
#        return str(name)
#    return None
#
#
#def load_thumb(item: Any, size: int) -> Optional[Any]:
#    """一顆 defect → ``size`` × ``size`` 的縮圖 ndarray（**Qt-free**，可跑在背景）。
#
#    讀不到圖（沒有 channel / 檔案不見了 / TIFF 壞頁）一律回 ``None`` ——
#    Gallery 會繼續畫「載入中…」的佔位磚，不會有人看到 traceback（鐵則 7 的精神）。
#    """
#    channel = thumb_channel(item)
#    if channel is None:
#        return None
#    arr = item.load(channel)
#    return make_thumb(arr, int(size))
#
#
#def _running_under_pytest() -> bool:
#    """現在是不是在跑測試（測試裡建 ``StudioWindow()`` 不准彈導覽）。"""
#    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules
#
#
#def _welcome_on_start_default() -> bool:
#    """``show_welcome_on_start=None`` 時的預設：沒勾過「不再顯示」且不在測試中。"""
#    if _running_under_pytest():
#        return False
#    try:
#        return not welcome_disabled()
#    except Exception:                   # noqa: BLE001 — 設定讀不到不該擋開窗
#        return False
#
#
#def generate_demo_lot(out_dir: Any = None, n: int = DEMO_DEFECTS,
#                      seed: int = DEMO_SEED) -> Dict[str, str]:
#    """產一批合成 EBI patch 資料（「用範例資料試一次」的第一步）。
#
#    ``tools/make_sample.py`` 不是安裝進來的套件，所以這裡**延遲 import**：
#    把 repo 的 ``tools/`` 補進 ``sys.path`` 再 import ``make_sample.generate``。
#    延遲的另一個理由是它會拉進 tifffile —— 只按別的鈕的人不需要付這個成本。
#
#    同一組 ``(n, seed)`` 產出的位元組完全相同，所以已經產過就直接沿用
#    （第二次按這顆鈕是秒回的）。
#    """
#    out = str(out_dir) if out_dir is not None else DEMO_DIR
#    klarf = os.path.join(out, "LOT_SYN.001")
#    tiff = os.path.join(out, "LOT_SYN.tif")
#    if os.path.isfile(klarf) and os.path.isfile(tiff):
#        return {"out_dir": out, "klarf": klarf, "tiff": tiff}
#
#    tools_dir = str(Path(__file__).resolve().parents[2] / "tools")
#    if tools_dir not in sys.path:
#        sys.path.insert(0, tools_dir)
#    from make_sample import generate      # noqa: E402 — 刻意延遲（見 docstring）
#
#    return generate(out, n=int(n), seed=int(seed))
#
#
#class ThumbWorker(_ThreadedWorker):
#    """Gallery 縮圖的背景解碼工（沿用 ``workers.py`` 的一次性 QThread 樣式）。
#
#    為什麼要有它：``make_thumb`` 前面那一步是**讀檔 + 解 TIFF 頁**，在 GUI
#    執行緒上做會讓捲動一格一格卡。所以 Gallery 只發「我要這些 id 的縮圖」，
#    真正的解碼在這裡。
#
#    **請求合併**：忙碌時 :meth:`request` 只是把 id 併進待跑集合（不排隊、
#    不阻塞、也不會為每次捲動各開一條執行緒），目前這批做完再一次做掉。
#    正在做的那批用 ``_inflight`` 記著，重複請求不會做第二次。
#
#    訊號：``ready(dict)``（``{defect_id: ndarray}``，回到 GUI 執行緒）、
#    ``failed(str)``（整批都讀不出來時才發，單顆失敗只是靜靜略過）。
#    """
#
#    ready = Signal(object)
#    failed = Signal(str)
#
#    #: 一批最多做幾張（做完立刻回 UI，剩下的下一批繼續 —— 縮圖要「陸續」出現）。
#    BATCH = 48
#
#    def __init__(self, parent: Optional[Any] = None) -> None:
#        super().__init__(parent)
#        self._pending: Dict[str, Any] = {}      # defect_id -> DefectItem
#        self._inflight: List[str] = []
#        self._size = 96
#
#    # ---- 對外 -------------------------------------------------------------
#    def request(self, jobs: Sequence[Any], size: int) -> None:
#        """要求做這些縮圖；``jobs`` 是 ``(defect_id, DefectItem)`` 的序列。"""
#        self._size = int(size)
#        for did, item in jobs or ():
#            did = str(did)
#            if did in self._inflight:
#                continue
#            self._pending[did] = item
#        if not self.is_running():
#            self._launch()
#
#    def pending_count(self) -> int:
#        """還沒開始做的縮圖張數（測試 / statusbar 用）。"""
#        return len(self._pending)
#
#    @staticmethod
#    def run_sync(jobs: Sequence[Any], size: int) -> Dict[str, Any]:
#        """同步做一批縮圖（不開執行緒），回傳 ``{defect_id: ndarray}``。"""
#        out: Dict[str, Any] = {}
#        for did, item in jobs or ():
#            try:
#                arr = load_thumb(item, int(size))
#            except Exception:               # noqa: BLE001 — 單顆壞掉不該殺整批
#                continue
#            if arr is not None:
#                out[str(did)] = arr
#        return out
#
#    # ---- 內部 -------------------------------------------------------------
#    def _launch(self) -> None:
#        if not self._pending:
#            return
#        ids = list(self._pending)[:self.BATCH]
#        batch = [(i, self._pending.pop(i)) for i in ids]
#        self._inflight = [i for i, _ in batch]
#        size = int(self._size)
#
#        def work() -> None:
#            out = ThumbWorker.run_sync(batch, size)
#            if out:
#                self.ready.emit(out)
#            elif batch:
#                self.failed.emit("Could not read thumbnails for %d defects "
#                                 "(the image files may be missing)." % len(batch))
#
#        self._start_job(work)
#
#    def _job_finished(self) -> None:
#        """一批做完（GUI 執行緒）：還有待做的就接著做。"""
#        self._inflight = []
#        if self._pending:
#            self._launch()
#
#    def _before_stop(self) -> None:
#        self._pending = {}                  # 關窗：待做的縮圖全部作廢
#        self._inflight = []
#
#
#class StudioWindow(QMainWindow):
#    """ADEPT Studio 主視窗（M3 組裝 + M5 Gallery / 直方圖聯動 / 輸出）。"""
#
#    def __init__(self, parent: Optional[QWidget] = None,
#                 show_welcome_on_start: Optional[bool] = None) -> None:
#        """``show_welcome_on_start``：
#
#        - ``True`` / ``False`` —— 明講要不要在開窗後跳導覽（測試用 ``False``）。
#        - ``None``（預設）—— 自己判斷：使用者沒勾過「不再顯示」**且**現在不是
#          在跑測試，才跳。**建構 StudioWindow() 在測試裡絕不可以彈出對話框**，
#          所以這裡把 ``pytest``／``PYTEST_CURRENT_TEST`` 也當成「不要跳」。
#          就算真的跳了，它也是非 modal 而且排在 event loop 的下一輪
#          （``QTimer.singleShot(0, …)``），建構式永遠不會被卡住。
#        """
#        super().__init__(parent)
#        self.setWindowTitle("ADEPT Studio")
#
#        # ---- 狀態 ---------------------------------------------------------
#        # 開窗就先放好 Input 卡（F7-9）：空白畫布對不會寫 code 的人是一道
#        # 「現在要幹嘛」的關卡，而答案永遠是同一個 —— 先載入影像。
#        self.model = RecipeModel.starter()
#        self.dataset: Optional[Any] = None
#        self.trial_scores: List[float] = []
#        self.trial_results: List[Dict[str, Any]] = []   # M5：Gallery / 輸出的來源
#        self.defect_index: int = 0
#        self.selected_node: Optional[str] = None
#        self.recipe_path: Optional[str] = None
#
#        self._preview_images: Dict[str, Any] = {}
#        self._last_result: Optional[Any] = None
#        self._user_stream: Optional[str] = None   # 使用者親手挑的影像流（會被保留）
#        self._user_stream_b: Optional[str] = None  # 同上，並排的右邊那張
#        self._compare_on = False         # 並排比對開著嗎（F7-8）
#        self._view_syncing = False       # 正在把檢視狀態推給另一張圖
#        self._syncing = False            # 程式在寫 widget（別回頭觸發 model）
#        self._trial_t0 = 0.0
#        self._items_by_id: Dict[str, Any] = {}    # defect_id -> DefectItem（縮圖用）
#        self._score_filter: Optional[Any] = None  # 直方圖點出來的 (lo, hi)
#        self._pending_warnings: List[Any] = []    # 跑前 lint 的警告（跑完才講）
#        self._preview_epoch = 0                   # 預覽的世代（丟掉過期結果用）
#        self._async_epoch = 0                     # 背景那筆出發時的世代
#        self.welcome_dialog: Optional[Any] = None
#        self.library_dialog: Optional[Any] = None
#        self.region_window: Optional[Any] = None   # 區域跨顆檢視（F7-11）
#        self.template_dialog: Optional[Any] = None  # 建模板對話框（F7-12）
#        self._region_regions: List[str] = []
#
#        # ---- 背景工作 ------------------------------------------------------
#        self.dataset_worker = DatasetLoadWorker(self)
#        self.preview_worker = PreviewWorker(self)
#        self.trial_worker = TrialWorker(self)
#        self.thumb_worker = ThumbWorker(self)
#        self.region_check_worker = RegionCheckWorker(self)
#
#        # ---- 去抖動計時器 --------------------------------------------------
#        self._preview_timer = QTimer(self)
#        self._preview_timer.setSingleShot(True)
#        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
#        self._preview_timer.timeout.connect(self._on_preview_timeout)
#
#        # ---- 介面 ----------------------------------------------------------
#        self._build_toolbar()
#        self._build_body()
#        self.setStatusBar(QStatusBar(self))
#        self._build_progress()
#
#        self._wire_widgets()
#        self._wire_workers()
#        self._build_shortcuts()
#        self.model.add_listener(self._on_model_changed)
#
#        # F7-1：卡片庫只列目前輸入型別用得到的卡（見 adept/ui/scope.py）
#        self.library.set_steps(
#            visible_steps([s.describe() for s in list_steps()])
#            + [_SCORE_LIBRARY_ENTRY])
#        self._refresh_all()
#        if self.model.node_order:
#            # 起手卡直接選起來：右欄一開窗就是「可以動的東西」，
#            # 而不是一句「請先從卡片庫挑一張卡」。
#            self.select_node(self.model.node_order[0])
#        self._status("Ready — press “Help” for a guided start, or “Open KLARF…” "
#                     "to load your data.")
#
#        if show_welcome_on_start is None:
#            show_welcome_on_start = _welcome_on_start_default()
#        if show_welcome_on_start:
#            # 非 modal + 排到下一輪 event loop：建構式永遠不會被對話框卡住
#            QTimer.singleShot(0, lambda: self.show_welcome(force=False))
#
#    # ==================================================================== #
#    # 介面組裝
#    # ==================================================================== #
#    def _build_toolbar(self) -> None:
#        """工具列（M7 精簡）。
#
#        兩處刻意的取捨：
#
#        * **「載入範本」併進「Templates…」** —— 舊版兩顆鈕做的是同一件事
#          （都在載 ``examples/recipes/`` 底下的 JSON），而 die-to-die 對第一次
#          用的人是行話。現在只留一個入口，範本庫自己把 die-to-die 排第一。
#        * **「全跑」收進「Run trial」的下拉** —— 兩顆長得一樣的 ▶ 鈕擺在一起，
#          新手分不出差別也不知道該按哪顆。主要動作只留一顆，破壞性比較大的
#          「跑整批」降級成選單項目。
#        """
#        bar = QToolBar("Main actions", self)
#        bar.setMovable(False)
#        bar.setFloatable(False)
#        self.toolbar = bar
#        self.addToolBar(bar)
#
#        self.btn_open_klarf = self._tool_button(
#            "Open KLARF…", "Load a KLARF (the patch TIFF can be picked separately)",
#            self._on_open_klarf)
#        self.btn_open_recipe = self._tool_button(
#            "Open Recipe…", "Load a recipe JSON", self._on_open_recipe)
#        self.btn_save_recipe = self._tool_button(
#            "Save Recipe…", "Save the current pipeline as a recipe JSON",
#            self._on_save_recipe)
#        self.btn_examples = self._tool_button(
#            "Templates…",
#            "Open the template library — every entry is a complete, runnable "
#            "pipeline. Start here rather than from an empty pipeline.",
#            self.open_recipe_library)
#        self.btn_export = self._tool_button(
#            "Export…",
#            "Write these results back to KLARF, or produce reports and overlays",
#            self.open_export_dialog)
#        self.btn_help = self._tool_button(
#            "Help", "Reopen the getting-started tour (includes “Try it with "
#                    "sample data”)",
#            lambda: self.show_welcome(force=True))
#        # 主題切換：一顆字元鈕，不佔位子也找得到（偏好存 QSettings）
#        self.btn_theme = self._tool_button(
#            "◐", "Switch between the light and dark theme",
#            self.toggle_theme)
#        for b in (self.btn_open_klarf, self.btn_open_recipe,
#                  self.btn_save_recipe, self.btn_examples,
#                  self.btn_export, self.btn_help, self.btn_theme):
#            bar.addWidget(b)
#
#        spacer = QWidget(bar)
#        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
#        bar.addWidget(spacer)
#
#        self.lbl_trial_n = QLabel("First ", bar)
#        bar.addWidget(self.lbl_trial_n)
#        self.spin_trial_n = QSpinBox(bar)
#        self.spin_trial_n.setRange(10, 5000)
#        # 「First 200」旁邊沒有單位時，200 可以是任何東西（秒？百分比？）。
#        self.spin_trial_n.setSuffix(" defects")
#        self.spin_trial_n.setValue(DEFAULT_TRIAL_N)
#        self.spin_trial_n.setToolTip(
#            "How many defects a trial run covers (keep it small while tuning)")
#        bar.addWidget(self.spin_trial_n)
#
#        self.btn_trial = self._tool_button(
#            "▶ Run trial", "Run the current pipeline over the first N defects "
#                           "and show the score distribution",
#            self._on_trial_clicked, primary=True)
#        # 「跑整批」是同一顆鈕的次要動作：點主體 = 試跑，點箭頭才看得到它。
#        menu = QMenu(self.btn_trial)
#        self.act_run_all = QAction("Run all defects", menu)
#        self.act_run_all.setToolTip("Run the whole dataset, not just the first N")
#        self.act_run_all.triggered.connect(self._on_full_clicked)
#        menu.addAction(self.act_run_all)
#        self.btn_trial.setMenu(menu)
#        self.btn_trial.setPopupMode(QToolButton.MenuButtonPopup)
#        self.trial_menu = menu
#        bar.addWidget(self.btn_trial)
#
#    #: 鍵盤快捷鍵（F7-16）。以前一個都沒有 —— 而這是一個「一直在試」的工具，
#    #: 存檔、跑一次、退回上一步是每分鐘都在做的事，每一次都要把手移到滑鼠、
#    #: 找到那顆鈕、按下去。
#    #:
#    #: 每一組都照作業系統的慣例（Ctrl+S 存檔、Ctrl+Z 復原、Ctrl+0 回原尺寸），
#    #: 不自己發明 —— 使用者的肌肉記憶是從別的軟體帶過來的，這裡不該重學。
#    SHORTCUTS = (
#        ("Ctrl+O", "open_klarf"), ("Ctrl+Shift+O", "open_recipe"),
#        ("Ctrl+S", "save_recipe"), ("Ctrl+R", "run"),
#        ("Ctrl+Z", "undo"), ("Ctrl+Shift+Z", "redo"), ("Ctrl+Y", "redo"),
#        ("Ctrl+0", "zoom_reset"), ("Ctrl++", "zoom_in"), ("Ctrl+=", "zoom_in"),
#        ("Ctrl+-", "zoom_out"), ("Ctrl+Shift+F", "zoom_fit"),
#        ("Ctrl+F", "find_card"),
#        ("Ctrl+Left", "prev_defect"), ("Ctrl+Right", "next_defect"),
#    )
#
#    def _build_shortcuts(self) -> None:
#        handlers = {
#            "open_klarf": self._on_open_klarf,
#            "open_recipe": self._on_open_recipe,
#            "save_recipe": self._on_save_recipe,
#            "run": self._on_trial_clicked,
#            "undo": self.undo,
#            "redo": self.redo,
#            "zoom_reset": self.pipeline.reset_zoom,
#            "zoom_in": lambda: self.pipeline.zoom_by(1.25),
#            "zoom_out": lambda: self.pipeline.zoom_by(1 / 1.25),
#            "zoom_fit": self.pipeline.fit,
#            "find_card": self.focus_card_search,
#            "prev_defect": lambda: self.step_defect(-1),
#            "next_defect": lambda: self.step_defect(+1),
#        }
#        self._shortcuts = []
#        for keys, name in self.SHORTCUTS:
#            sc = QShortcut(QKeySequence(keys), self)
#            sc.activated.connect(handlers[name])
#            self._shortcuts.append(sc)
#
#        # 按鍵存在還不夠 —— 使用者要**發現得到**。工具列的 tooltip 是他唯一
#        # 會停留的地方，所以把快捷鍵寫進去（作業系統慣例：括號附在後面）。
#        #
#        # 註冊而不是「設一次」：``_update_action_states`` 每次 refresh 都會重寫
#        # 這幾顆的 tooltip（「還沒有東西可以存」之類的原因），設一次的話第一次
#        # refresh 就被蓋掉了。所以改成**設 tooltip 的那個動作自己會補上快捷鍵**。
#        self._tip_keys = {
#            id(self.btn_open_klarf): "Ctrl+O",
#            id(self.btn_open_recipe): "Ctrl+Shift+O",
#            id(self.btn_save_recipe): "Ctrl+S",
#            id(self.btn_trial): "Ctrl+R",
#            id(self.btn_empty_open): "Ctrl+O",
#        }
#        for w in (self.btn_open_klarf, self.btn_open_recipe,
#                  self.btn_save_recipe, self.btn_trial, self.btn_empty_open):
#            self._set_tip(w, w.toolTip())
#
#    def _set_tip(self, widget: Any, text: str) -> None:
#        """設 tooltip，並自動補上這顆鈕的快捷鍵。"""
#        keys = getattr(self, "_tip_keys", {}).get(id(widget))
#        widget.setToolTip("%s  (%s)" % (text, keys) if keys else str(text))
#
#    def focus_card_search(self) -> None:
#        """跳到卡片庫的搜尋框（收起來的話先展開）—— 與 rail 上的放大鏡同一條路。"""
#        self.library.focus_search()
#
#    # ---- 復原 / 重做 -------------------------------------------------------
#    def undo(self) -> bool:
#        """退回上一步。做不到的時候要**說出來** —— 按了 Ctrl+Z 卻什麼都沒發生，
#        使用者第一個念頭是「這個工具有沒有壞」，不是「已經沒得退了」。"""
#        if not self.model.undo():
#            self._status("Nothing to undo.")
#            return False
#        self._status("Undone.")
#        return True
#
#    def redo(self) -> bool:
#        if not self.model.redo():
#            self._status("Nothing to redo.")
#            return False
#        self._status("Redone.")
#        return True
#
#    def _build_progress(self) -> None:
#        """狀態列右側的進度條（F7-7）。
#
#        以前載入資料集與試跑都只有狀態列的一行字，那對「跑一批一萬顆」這種
#        會等好幾分鐘的動作是不夠的 —— 使用者看不出還要多久、也看不出它到底
#        在不在動。這條進度條在**閒著時完全隱藏**，不佔位子也不製造噪音。
#
#        載入 KLARF 沒有可回報的百分比（``load_dataset`` 是一次呼叫），所以那個
#        情況用**不定型**（range 0–0）的跑馬燈：它回答的是「還在動嗎」，
#        而不是「還剩多久」——謊報一個假的百分比比不報還糟。
#        """
#        self.progress = QProgressBar(self)
#        self.progress.setFixedWidth(220)
#        self.progress.setTextVisible(True)
#        self.progress.setVisible(False)
#        # 明確狀態：``isVisible()`` 在視窗 show() 之前一律 False，
#        # headless 測試會全部誤判（同 LibraryPanel 的 badge，見 widgets.py）。
#        self._progress_on = False
#        self.statusBar().addPermanentWidget(self.progress)
#
#        # 「跑到一半發現參數設錯」是最常見的情況，而一萬顆要好幾分鐘（F7-16）。
#        # 引擎本來就支援中止（``run_batch`` 的 ``abort_check``、
#        # ``TrialWorker.abort``）—— 只是以前沒有任何地方按得到它，
#        # 於是使用者唯一的中止方式是把整個視窗關掉。
#        self.btn_stop = QPushButton("Stop", self)
#        self.btn_stop.setProperty("variant", "danger")
#        self.btn_stop.setToolTip(
#            "Stop this run. Defects already finished are kept — you get the "
#            "results for them, not nothing.")
#        self.btn_stop.setVisible(False)
#        self.btn_stop.clicked.connect(self.stop_run)
#        self.statusBar().addPermanentWidget(self.btn_stop)
#        self._stop_on = False
#
#    def _progress_busy(self, label: str) -> None:
#        """不定型跑馬燈（不知道總量時用）。"""
#        self.progress.setRange(0, 0)
#        self.progress.setFormat(str(label))
#        self.progress.setVisible(True)
#        self._progress_on = True
#
#    def _show_stop(self, on: bool) -> None:
#        """中止鈕只在真的有東西在跑的時候出現（明確狀態，不問 widget）。"""
#        self._stop_on = bool(on)
#        self.btn_stop.setVisible(bool(on))
#        self.btn_stop.setEnabled(bool(on))
#
#    def stop_available(self) -> bool:
#        return bool(self._stop_on)
#
#    def stop_run(self) -> bool:
#        """中止進行中的批次。已經跑完的那些顆**留著** —— 使用者按停止是想
#        「不要再等了」，不是「把剛才那五分鐘丟掉」。"""
#        if not self.trial_worker.is_running():
#            return False
#        self.trial_worker.abort()
#        self.btn_stop.setEnabled(False)
#        self._status("Stopping — keeping the defects that already finished…")
#        return True
#
#    def _progress_set(self, done: int, total: int, label: str = "%v / %m") -> None:
#        self.progress.setRange(0, max(1, int(total)))
#        self.progress.setValue(int(done))
#        self.progress.setFormat(str(label))
#        self.progress.setVisible(True)
#        self._progress_on = True
#
#    def _progress_done(self) -> None:
#        self._show_stop(False)
#        self.progress.setVisible(False)
#        self.progress.setRange(0, 1)
#        self.progress.reset()
#        self._progress_on = False
#
#    def progress_visible(self) -> bool:
#        """進度條現在看得到嗎（測試用）。"""
#        return bool(self._progress_on)
#
#    def _tool_button(self, text: str, tip: str, slot: Any,
#                     primary: bool = False) -> QToolButton:
#        b = QToolButton(self)
#        b.setText(text)
#        b.setToolTip(tip)
#        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
#        b.setCursor(Qt.PointingHandCursor)
#        if primary:
#            b.setObjectName("primary")
#        b.clicked.connect(slot)
#        return b
#
#    def _build_body(self) -> None:
#        # 左：卡片庫
#        self.library = LibraryPanel(self)
#        self.library.panel_toggled.connect(self._on_library_panel_toggled)
#
#        # 中：流程畫布 + （參數表單 / 分數編輯）
#        self.pipeline = PipelineCanvas(self)
#        self.param_form = ParamForm(self)
#        self.score_pane = self._build_score_pane()
#        self.stack = QStackedWidget(self)
#        self.stack.addWidget(self.param_form)     # index 0
#        self.stack.addWidget(self.score_pane)     # index 1
#
#        middle = QSplitter(Qt.Vertical, self)
#        middle.addWidget(self.pipeline)
#        middle.addWidget(self.stack)
#        middle.setStretchFactor(0, 3)
#        middle.setStretchFactor(1, 2)
#        self.middle_splitter = middle
#
#        # 右：單顆預覽（F7-5：Gallery 與直方圖搬到 Results 視窗，
#        #     主視窗只留「編流程 + 看單顆」，影像因此拿得到整欄高度）
#        self.preview_pane = self._build_preview_pane()
#
#        # Results 視窗（跑完才 show；先建好讓 histogram / gallery 一直有實體，
#        # 這樣所有既有接線與測試都不用管它現在開著沒有）
#        self.results = ResultsWindow(self)
#        self.histogram = self.results.histogram
#        self.gallery = self.results.gallery
#        self.results.export_requested.connect(self.open_export_dialog)
#
#        root = QSplitter(Qt.Horizontal, self)
#        root.addWidget(self.library)
#        root.addWidget(middle)
#        root.addWidget(self.preview_pane)
#        root.setStretchFactor(0, 0)
#        root.setStretchFactor(1, 2)
#        root.setStretchFactor(2, 4)
#        root.setSizes(list(COLUMN_SIZES))
#        self.top_splitter = root
#        self.root_splitter = root
#        self.setCentralWidget(root)
#
#    def _build_score_pane(self) -> QWidget:
#        pane = QWidget(self)
#        lay = QVBoxLayout(pane)
#        lay.setContentsMargins(2, 2, 8, 2)
#        lay.setSpacing(4)
#
#        title = QLabel("Score / Bin decision", pane)
#        title.setObjectName("paramTitle")
#        lay.addWidget(title)
#
#        head = QLabel("The last step of the pipeline: turn features into one score, then split into bins by a threshold.", pane)
#        head.setObjectName("paramStepHelp")
#        head.setWordWrap(True)
#        lay.addWidget(head)
#
#        row1 = QHBoxLayout()
#        row1.setSpacing(8)
#        lbl_expr = QLabel("Score expression", pane)
#        lbl_expr.setObjectName("paramLabel")
#        lbl_expr.setMinimumWidth(104)
#        self.expr_edit = QLineEdit(pane)
#        self.expr_edit.setPlaceholderText("e.g. glv_max + (glv_max - glv_q99)")
#        self.expr_edit.setToolTip("Write an expression over feature names — the result is this defect's score")
#        row1.addWidget(lbl_expr)
#        row1.addWidget(self.expr_edit, 1)
#        lay.addLayout(row1)
#
#        row2 = QHBoxLayout()
#        row2.setSpacing(8)
#        lbl_ins = QLabel("Insert feature", pane)
#        lbl_ins.setObjectName("paramLabel")
#        lbl_ins.setMinimumWidth(104)
#        self.feature_combo = QComboBox(pane)
#        self.feature_combo.setToolTip("Pick a feature name to insert at the cursor in the expression")
#        row2.addWidget(lbl_ins)
#        row2.addWidget(self.feature_combo, 1)
#        lay.addLayout(row2)
#
#        row3 = QHBoxLayout()
#        row3.setSpacing(8)
#        lbl_thr = QLabel("Decision threshold", pane)
#        lbl_thr.setObjectName("paramLabel")
#        lbl_thr.setMinimumWidth(104)
#        self.threshold_spin = QDoubleSpinBox(pane)
#        self.threshold_spin.setDecimals(3)
#        self.threshold_spin.setRange(-1e9, 1e9)
#        self.threshold_spin.setSingleStep(0.5)
#        self.threshold_spin.setToolTip("score >= threshold -> bin 1 (the ones you want), otherwise bin 0")
#        row3.addWidget(lbl_thr)
#        row3.addWidget(self.threshold_spin, 1)
#        lay.addLayout(row3)
#
#        hint = QLabel(_SCORE_HELP, pane)
#        hint.setObjectName("paramHint")
#        hint.setWordWrap(True)
#        lay.addWidget(hint)
#        self.score_hint = hint
#
#        lay.addStretch(1)
#        return pane
#
#    def _build_preview_pane(self) -> QWidget:
#        pane = QWidget(self)
#        lay = QVBoxLayout(pane)
#        lay.setContentsMargins(2, 2, 2, 2)
#        lay.setSpacing(4)
#
#        nav = QHBoxLayout()
#        nav.setSpacing(6)
#        self.btn_prev = QPushButton("◀", pane)
#        self.btn_prev.setObjectName("cardButton")
#        self.btn_prev.setFixedWidth(28)
#        self.btn_prev.setToolTip("Previous defect")
#        self.btn_next = QPushButton("▶", pane)
#        self.btn_next.setObjectName("cardButton")
#        self.btn_next.setFixedWidth(28)
#        self.btn_next.setToolTip("Next defect")
#        self.defect_combo = QComboBox(pane)
#        self.defect_combo.setToolTip("Jump straight to a defect")
#        self.defect_label = QLabel("(no dataset loaded)", pane)
#        self.defect_label.setObjectName("paramHint")
#        nav.addWidget(self.btn_prev)
#        nav.addWidget(self.btn_next)
#        nav.addWidget(self.defect_combo, 1)
#        nav.addWidget(self.defect_label)
#        lay.addLayout(nav)
#
#        srow = QHBoxLayout()
#        srow.setSpacing(6)
#        lbl_stream = QLabel("Image stream", pane)
#        lbl_stream.setObjectName("paramLabel")
#        self.stream_combo = QComboBox(pane)
#        self.stream_combo.setToolTip(
#            "Which image stream to look at (test / ref / diff / snr_map …)")
#        srow.addWidget(lbl_stream)
#        srow.addWidget(self.stream_combo, 1)
#
#        # 並排比對（F7-8）—— 預設關著，見 _set_compare 的說明
#        self.compare_check = QCheckBox("Compare", pane)
#        self.compare_check.setToolTip(
#            "Show a second image stream side by side, with linked zoom and pan "
#            "— useful when tuning Enhance cards, to check test and ref still "
#            "match")
#        self.stream_combo_b = QComboBox(pane)
#        self.stream_combo_b.setToolTip("The stream shown on the right")
#        self.stream_combo_b.setVisible(False)
#        srow.addWidget(self.compare_check)
#        srow.addWidget(self.stream_combo_b, 1)
#        # 游標讀數有自己的位置（M7）。以前它是寫進狀態列的，於是滑鼠只要飄過
#        # 影像，剛才那句「Trial run finished: …」就被 x/y/gray 洗掉了 ——
#        # 狀態列該留給「使用者要讀的事件」，一直在刷的東西不該跟它搶同一格。
#        self.cursor_label = QLabel("", pane)
#        self.cursor_label.setObjectName("paramHint")
#        self.cursor_label.setMinimumWidth(150)
#        self.cursor_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
#        self.cursor_label.setToolTip("Cursor position and gray level")
#        srow.addWidget(self.cursor_label)
#        lay.addLayout(srow)
#
#        self.image_view = ImageView(pane)
#        self.image_view_b = ImageView(pane)
#        self.image_view_b.setVisible(False)
#        images = QWidget(pane)
#        irow = QHBoxLayout(images)
#        irow.setContentsMargins(0, 0, 0, 0)
#        irow.setSpacing(4)
#        irow.addWidget(self.image_view, 1)
#        irow.addWidget(self.image_view_b, 1)
#
#        # 還沒載資料時，畫面上最大的一塊是**一片黑**，角落有一行極小的
#        # 「(no dataset loaded)」（F7-15）。首啟導覽關掉之後就沒有任何東西告訴
#        # 使用者下一步要做什麼 —— 而「下一步」只有兩個，就把那兩個放在這裡。
#        self.empty_state = QWidget(pane)
#        estack = QVBoxLayout(self.empty_state)
#        estack.addStretch(1)
#        title = QLabel("No data loaded yet", self.empty_state)
#        title.setObjectName("paramTitle")
#        title.setAlignment(Qt.AlignCenter)
#        estack.addWidget(title)
#        why = QLabel("Open a KLARF to see your patches here, or try the tool "
#                     "with generated sample data first.", self.empty_state)
#        why.setObjectName("paramHint")
#        why.setAlignment(Qt.AlignCenter)
#        why.setWordWrap(True)
#        estack.addWidget(why)
#        brow = QHBoxLayout()
#        brow.addStretch(1)
#        self.btn_empty_open = QPushButton("Open KLARF…", self.empty_state)
#        self.btn_empty_open.setObjectName("primary")
#        brow.addWidget(self.btn_empty_open)
#        self.btn_empty_sample = QPushButton("Try it with sample data",
#                                            self.empty_state)
#        self.btn_empty_sample.setProperty("variant", "secondary")
#        brow.addWidget(self.btn_empty_sample)
#        brow.addStretch(1)
#        estack.addLayout(brow)
#        estack.addStretch(1)
#
#        self.image_stack = QStackedWidget(pane)
#        self.image_stack.addWidget(self.empty_state)      # index 0
#        self.image_stack.addWidget(images)                # index 1
#        lay.addWidget(self.image_stack, 3)
#
#        # 模板定位卡的入口在**參數列裡**（F7-13），不在這裡。它是那個參數的值
#        # 從哪來，不是一個預覽動作 —— 放在影像下方等於把「這個欄位怎麼填」的
#        # 答案擺到半個螢幕外，而欄位本身看起來只是「還沒填」。
#
#        # 「這個區域在整批上都對嗎」（F7-11）。跟曲線面板一樣平常收起來，
#        # 只有選到會定義區域的卡片時才出現。
#        self.btn_region_check = QPushButton("Check this region across defects…",
#                                            pane)
#        self.btn_region_check.setProperty("variant", "secondary")
#        self.btn_region_check.setToolTip(
#            "Draw this region on many defects at once. A setting that looks "
#            "right on defect 1 can be completely off on defect 50 — the "
#            "structure sits in a different place on every patch.")
#        self.btn_region_check.setVisible(False)
#        lay.addWidget(self.btn_region_check)
#
#        # 投影曲線面板（F7-11）。**平常收起來** —— 它只有在編輯投影定位卡的
#        # 時候才有意義，常駐會把好不容易爭取到的影像高度又吃掉一塊。
#        # 投影曲線面板搬進卡片儀表（F7-17）：它本來就是「這張卡自己的儀表」，
#        # 只是 F7-11 當時直接掛在這裡，變成一條跟儀表機制平行的路。兩條並存的
#        # 下場是加新面板的人不知道走哪一條，然後兩邊各長一半。
#
#        # 右下角那一塊：**選哪張卡就換成那張卡的儀表**（F7-17）。
#        # 原本固定是一張「特徵 / 數值」表 —— 問題不是它佔位子，是那些數字沒有
#        # 辦法判讀（`blob_dist_center 11.170` 是大還是小？），而且使用者在問的
#        # 問題**每張卡都不一樣**。特徵表仍然留著，用切換列回去。
#        self.feature_table = FeatureTable(pane)
#        self.feature_table.setMinimumHeight(120)
#
#        self.inspector_host = QWidget(pane)
#        ihost = QVBoxLayout(self.inspector_host)
#        ihost.setContentsMargins(0, 0, 0, 0)
#        ihost.setSpacing(2)
#        self.inspector_summary = QLabel("", self.inspector_host)
#        self.inspector_summary.setObjectName("paramHint")
#        self.inspector_summary.setWordWrap(True)
#        self.inspector_slot = QVBoxLayout()
#        self.inspector_slot.setContentsMargins(0, 0, 0, 0)
#        ihost.addLayout(self.inspector_slot, 1)
#        ihost.addWidget(self.inspector_summary)
#        self._inspector: Optional[Any] = None
#
#        self.bottom_stack = QStackedWidget(pane)
#        self.bottom_stack.addWidget(self.inspector_host)      # index 0
#        self.bottom_stack.addWidget(self.feature_table)       # index 1
#
#        tabs = QHBoxLayout()
#        tabs.setContentsMargins(0, 0, 0, 0)
#        tabs.setSpacing(4)
#        self.btn_tab_card = QPushButton("Card", pane)
#        self.btn_tab_features = QPushButton("Features", pane)
#        for i, b in enumerate((self.btn_tab_card, self.btn_tab_features)):
#            b.setCheckable(True)
#            b.setObjectName("cardButton")
#            b.setFixedHeight(20)
#            b.clicked.connect(lambda _c=False, k=i: self.show_bottom_page(k))
#            tabs.addWidget(b)
#        tabs.addStretch(1)
#        lay.addLayout(tabs)
#        lay.addWidget(self.bottom_stack, 2)
#
#        vrow = QHBoxLayout()
#        vrow.setSpacing(6)
#        self.verdict = VerdictChip(pane)
#        vrow.addWidget(QLabel("Verdict", pane))
#        vrow.addWidget(self.verdict)
#        vrow.addStretch(1)
#        lay.addLayout(vrow)
#
#        return pane
#
#    # ==================================================================== #
#    # 訊號接線
#    # ==================================================================== #
#    def _wire_widgets(self) -> None:
#        self.library.add_requested.connect(self._on_add_requested)
#
#        self.pipeline.node_selected.connect(self.select_node)
#        self.pipeline.node_toggled.connect(self._on_node_toggled)
#        self.pipeline.move_requested.connect(self._on_move_requested)
#        self.pipeline.remove_requested.connect(self._on_remove_requested)
#        self.pipeline.score_clicked.connect(self.show_score_page)
#        self.pipeline.edge_added.connect(self._on_edge_added)
#        self.pipeline.edge_removed.connect(self._on_edge_removed)
#
#        self.param_form.param_edited.connect(self._on_param_edited)
#
#        self.expr_edit.textEdited.connect(self._on_expr_edited)
#        self.feature_combo.activated.connect(self._on_feature_chosen)
#        self.threshold_spin.valueChanged.connect(self._on_threshold_spin)
#
#        self.btn_prev.clicked.connect(lambda: self.step_defect(-1))
#        self.btn_next.clicked.connect(lambda: self.step_defect(+1))
#        self.defect_combo.currentIndexChanged.connect(self._on_defect_combo)
#        self.btn_region_check.clicked.connect(lambda: self.open_region_check())
#        self.btn_empty_open.clicked.connect(self._on_open_klarf)
#        self.btn_empty_sample.clicked.connect(self._on_demo_requested)
#        self.param_form.action_requested.connect(self._on_param_action)
#        self.stream_combo.currentTextChanged.connect(self._on_stream_changed)
#        self.stream_combo_b.currentTextChanged.connect(self._on_stream_b_changed)
#        self.compare_check.toggled.connect(self.set_compare)
#
#        self.image_view.cursor_info.connect(self._on_cursor_info)
#        self.image_view_b.cursor_info.connect(self._on_cursor_info)
#        self.image_view.view_changed.connect(
#            lambda s, o: self._link_views(self.image_view, self.image_view_b, s, o))
#        self.image_view_b.view_changed.connect(
#            lambda s, o: self._link_views(self.image_view_b, self.image_view, s, o))
#
#        self.histogram.threshold_changed.connect(self._on_threshold_changed)
#        self.histogram.threshold_committed.connect(self._on_threshold_committed)
#        self.histogram.bar_clicked.connect(self._on_bar_clicked)
#
#        self.gallery.thumbs_requested.connect(self._on_thumbs_requested)
#        self.gallery.defect_activated.connect(self._on_defect_activated)
#        self.gallery.selection_changed.connect(self._on_gallery_selection)
#
#    def _wire_workers(self) -> None:
#        self.dataset_worker.loaded.connect(self._on_dataset_loaded)
#        self.dataset_worker.failed.connect(
#            lambda msg: (self._progress_done(),
#                         self._status("Could not load dataset: %s" % msg, "error")))
#
#        self.preview_worker.ready.connect(self._on_async_preview_ready)
#        self.preview_worker.busy.connect(self._on_preview_busy)
#        self.region_check_worker.ready.connect(self._on_region_ready)
#        self.region_check_worker.failed.connect(
#            lambda msg: self._status("Region check failed: %s" % msg, "error"))
#        self.preview_worker.failed.connect(
#            lambda msg: self._status("Preview failed: %s" % msg, "error"))
#
#        self.trial_worker.progress.connect(self._on_trial_progress)
#        self.trial_worker.done.connect(self._on_trial_done_async)
#        self.trial_worker.failed.connect(
#            lambda msg: (self._progress_done(),
#                         self._status("Trial run failed: %s" % msg, "error")))
#
#        self.thumb_worker.ready.connect(self._on_thumbs_ready)
#        self.thumb_worker.failed.connect(self._status)
#
#    # ==================================================================== #
#    # 狀態列
#    # ==================================================================== #
#    def _status(self, msg: str, level: str = "info") -> None:
#        """狀態列。``level="error"`` 會把它變成紅字（F7-15）。
#
#        狀態列是**唯一**會講出「這件事沒成功」的地方（lint 擋下試跑、卡片加不
#        進去、模板存不起來），而它以前跟「Added denoise」用完全一樣的灰字，
#        在畫面最左下角。使用者按了一顆鈕、什麼都沒發生、而唯一的解釋長得跟
#        剛才那句成功訊息一模一樣 —— 那等於沒有講。
#        """
#        bar = self.statusBar()
#        bar.setProperty("level", "error" if level == "error" else "info")
#        bar.style().unpolish(bar)
#        bar.style().polish(bar)
#        bar.showMessage(str(msg))
#
#    def status_text(self) -> str:
#        """目前狀態列文字（測試用）。"""
#        return self.statusBar().currentMessage()
#
#    def status_level(self) -> str:
#        """狀態列現在是不是在報錯（用明確狀態，不要去比對顏色）。"""
#        return str(self.statusBar().property("level") or "info")
#
#    def cursor_text(self) -> str:
#        """目前的游標讀數（測試用）。"""
#        return self.cursor_label.text()
#
#    def _on_cursor_info(self, text: str) -> None:
#        """游標讀數 → 預覽區自己的標籤（**不碰狀態列**，見 ``_build_preview_pane``）。"""
#        self.cursor_label.setText(str(text or ""))
#
#    # ==================================================================== #
#    # model → UI
#    # ==================================================================== #
#    def _on_model_changed(self) -> None:
#        """model 任何變動的統一入口（listener）。"""
#        self._refresh_pipeline()
#        self._sync_score_widgets()
#        self.histogram.set_threshold(self.model.threshold)
#        self._refresh_bin_summary(self.model.threshold)
#        self._update_action_states()
#        self._refresh_library_badges()
#        self._refresh_region_button()
#        self._schedule_preview()
#
#    def _refresh_all(self) -> None:
#        self._refresh_pipeline()
#        self._sync_score_widgets()
#        self._refresh_feature_combo()
#        self.histogram.set_threshold(self.model.threshold)
#        self._refresh_bin_summary(self.model.threshold)
#        self._update_action_states()
#        self._refresh_library_badges()
#
#    def _refresh_library_badges(self) -> None:
#        """把「pipeline 目前產出了哪些影像流」餵給卡片庫（F7-3）。
#
#        卡片庫據此把前置條件未滿足的卡標成 ``needs diff`` 並調淡 ——
#        **但仍然可以加**。卡片庫的順序不是執行順序，使用者可能先放卡再補上游。
#        """
#        try:
#            streams = list(self.model.available_streams())
#        except Exception:                # noqa: BLE001 — 顯示用，壞了就不標
#            streams = []
#        self.library.set_available_streams(streams)
#
#    def _on_library_panel_toggled(self, open_: bool) -> None:
#        """卡片區收起來時，把左欄的寬度真的還給工作區。
#
#        只搬左欄與中欄之間的那條分隔線 —— 右欄（單顆預覽）的寬度不動，
#        使用者自己調過的預覽大小不該因為收合卡片庫而被重設。
#        """
#        root = getattr(self, "root_splitter", None)
#        if root is None:
#            return
#        sizes = list(root.sizes())
#        if len(sizes) != 3 or sum(sizes) <= 0:
#            return
#        want = self.library.minimumWidth()
#        delta = want - sizes[0]
#        sizes[0], sizes[1] = want, max(240, sizes[1] - delta)
#        root.setSizes(sizes)
#
#    # ---- 動作可用性（M7）--------------------------------------------------
#    def _update_action_states(self) -> None:
#        """按鈕的前置條件不滿足 → **變灰並在 tooltip 說明原因**。
#
#        舊行為是「按下去才在狀態列說『還沒有載入資料集』」。狀態列在螢幕最下
#        角，第一次用的人根本不會往那裡看 —— 對他而言就是「我按了，沒反應」。
#        推廣鐵則要求：擋在前面，而且要講得出為什麼。
#
#        這裡只碰 ``setEnabled`` / ``setToolTip``，不改 model、不觸發預覽，
#        所以任何 refresh 路徑都可以放心呼叫。
#        """
#        n_items = len(self._items())
#        has_steps = bool(self.model.node_order)
#        can_run = bool(n_items) and has_steps
#
#        # 沒有資料時，最大的那一塊要說得出下一步（F7-15）
#        self.image_stack.setCurrentIndex(1 if n_items else 0)
#
#        if can_run:
#            run_why = ""
#        elif not n_items and not has_steps:
#            run_why = "Load a KLARF and add at least one card first."
#        elif not n_items:
#            run_why = "No dataset loaded yet — use “Open KLARF…” first."
#        else:
#            run_why = "The pipeline is empty — add a card from the library first."
#
#        self.btn_trial.setEnabled(can_run)
#        self._set_tip(self.btn_trial,
#                      run_why or "Run the current pipeline over the first %d "
#                                 "defects and show the score distribution"
#                      % int(self.spin_trial_n.value()))
#        self.act_run_all.setEnabled(can_run)
#        self.act_run_all.setToolTip(
#            run_why or "Run all %d defects, not just the first %d"
#                       % (n_items, int(self.spin_trial_n.value())))
#        self.spin_trial_n.setEnabled(can_run)
#        self.lbl_trial_n.setEnabled(can_run)
#
#        self.btn_save_recipe.setEnabled(has_steps)
#        self._set_tip(self.btn_save_recipe,
#                      "Save the current pipeline as a recipe JSON" if has_steps
#                      else "Nothing to save yet — the pipeline is empty.")
#
#        has_results = bool(self.trial_results)
#        self.btn_export.setEnabled(has_results)
#        self.btn_export.setToolTip(
#            "Write these results back to KLARF, or produce reports and overlays"
#            if has_results
#            else "No results yet — run a trial first.")
#
#    def _node_summary(self, node: Any) -> str:
#        """最多 3 個「非預設」參數，渲染成 ``k=v`` 串起來。"""
#        try:
#            step_cls = get_step(node.step)
#        except KeyError:
#            return "(unknown card %s)" % node.step
#        defaults = {p.name: p.default for p in step_cls.params}
#        # 有些參數的值不是給人看的（模板是一整張影像的內容，六千多個字元）。
#        # 直接串進摘要，那張卡的第三行就變成一段 base64 —— 元件會把它切掉，
#        # 於是看到的是「template=gc1:iVBORw0KGg…」，既沒有資訊也擠掉了真正
#        # 有用的參數。這種參數只講「有沒有設」。
#        opaque = {p.name: p.type for p in step_cls.params if p.type == "template"}
#        parts: List[str] = []
#        for name, value in node.params.items():
#            if name in defaults and defaults[name] == value:
#                continue
#            if name in opaque:
#                parts.append("%s: set" % name)
#            else:
#                parts.append("%s=%s" % (name, _fmt(value)))
#            if len(parts) >= 3:
#                break
#        return " · ".join(parts)
#
#    def _node_problems(self) -> Dict[str, Any]:
#        """每個節點最嚴重的一則 lint 發現（畫布上的警示標記用）。
#
#        lint 本來就知道「這張卡缺模板」「這張卡指到不存在的區域」—— 但那個知識
#        以前只在按下 Run trial 的那一刻出現一次。卡片在畫布上看起來永遠是好的，
#        於是使用者要跑過才知道，而跑一次是好幾分鐘。
#        """
#        out: Dict[str, Any] = {}
#        try:
#            issues = self.model.validate()
#        except Exception:                        # noqa: BLE001 — 顯示用，壞了就沒標記
#            return out
#        for issue in issues:
#            nid = getattr(issue, "node_id", None)
#            if not nid:
#                continue
#            prev = out.get(nid)
#            # error 蓋過 warning；同級的取先出現的那則
#            if prev is not None and not (prev[1] == "warning"
#                                         and issue.level == "error"):
#                continue
#            out[nid] = (str(issue.detail or issue.title), str(issue.level))
#        return out
#
#    def _refresh_pipeline(self) -> None:
#        problems = self._node_problems()
#        nodes: List[Dict[str, Any]] = []
#        for nid in self.model.node_order:
#            node = self.model.nodes.get(nid)
#            if node is None:
#                continue
#            step_cls = None
#            try:
#                step_cls = get_step(node.step)
#                label, category = step_cls.label, step_cls.category
#            except KeyError:
#                label, category = node.step, ""
#            # writes 用 kind-aware 版本解析：patch 的 Input 節點因此吐
#            # ["test", "ref"]，畫布上就畫成兩個具名輸出埠（F7-7）。
#            try:
#                writes = list(step_cls.resolve_writes_for_kind(
#                    node.params, self.model.kind))
#            except Exception:              # noqa: BLE001 — 顯示用，壞了就空著
#                writes = []
#            try:
#                reads = list(step_cls.resolve_reads(node.params))
#            except Exception:              # noqa: BLE001
#                reads = []
#            try:
#                # Region 卡不寫影像流，它定義的是具名區域 —— 副標要講得出
#                # 「ref → cell」，否則那張卡在畫布上看起來什麼都不產出。
#                regions_out = list(step_cls.resolve_regions_out(node.params))
#            except Exception:              # noqa: BLE001
#                regions_out = []
#            nodes.append({
#                "node_id": nid,
#                "step_key": node.step,
#                "label": label,
#                "category": category,
#                "enabled": bool(node.enabled),
#                "summary": self._node_summary(node),
#                "writes": writes,
#                "reads": reads,
#                "regions_out": regions_out,
#                "group": step_cls.resolve_group() if step_cls else "",
#                "problem": problems.get(nid, ("", ""))[0],
#                "problem_level": problems.get(nid, ("", "error"))[1],
#            })
#        self.pipeline.set_nodes(nodes, self.model.edges)
#        if self.selected_node not in self.model.nodes:
#            self.selected_node = None
#        self.pipeline.set_selected(self.selected_node)
#        self.pipeline.set_score_summary(self.model.expr, self.model.threshold)
#
#    def _sync_score_widgets(self) -> None:
#        self._syncing = True
#        try:
#            if self.expr_edit.text() != self.model.expr:
#                self.expr_edit.setText(self.model.expr)
#            if float(self.threshold_spin.value()) != float(self.model.threshold):
#                self.threshold_spin.setValue(float(self.model.threshold))
#        finally:
#            self._syncing = False
#        self.pipeline.set_score_summary(self.model.expr, self.model.threshold)
#
#    def _refresh_feature_combo(self) -> None:
#        self._syncing = True
#        try:
#            self.feature_combo.clear()
#            self.feature_combo.addItem(_FEATURE_PLACEHOLDER)
#            for name in self.model.available_features():
#                self.feature_combo.addItem(name)
#            self.feature_combo.setCurrentIndex(0)
#        finally:
#            self._syncing = False
#
#    def _refresh_bin_summary(self, threshold: float) -> None:
#        if not self.trial_scores:
#            self.histogram.set_bin_summary(None)
#            return
#        self.histogram.set_bin_summary(
#            rebin(self.trial_scores, float(threshold), self.model.bins))
#
#    # ==================================================================== #
#    # 卡片庫 / 流程
#    # ==================================================================== #
#    def _on_add_requested(self, step_key: str) -> None:
#        if str(step_key) == _SCORE_LIBRARY_KEY:
#            # 「Score / Bin」不是可增刪的卡片 —— 每條 pipeline 固定有一張，
#            # 點它就是去編輯分數表達式與門檻（三段式的最後一段）。
#            self.show_score_page()
#            self._status("Editing the score / threshold")
#            return
#        # 選著一張卡的時候，新的卡接在它後面、做在**它那條流**上（F7-18）。
#        # 埠上的「+」被拿掉了（永遠掛在那裡太吵，使用者要的是從旁邊的卡片庫加），
#        # 但它做對的那兩件事要留著：接上線，而且接在對的那條流上。
#        # 加完就選取新卡 —— 所以連按三張卡片會長成一條鏈，順序就是按下去的順序。
#        after = self.selected_node if self.selected_node in self.model.nodes else None
#        if after is not None:
#            self.add_card_after(after, str(step_key),
#                                self._primary_stream_of(after))
#            return
#        try:
#            node_id = self.model.add_step(str(step_key))
#        except (KeyError, ParamError) as e:
#            self._status("Could not add card: %s" % e, "error")
#            return
#        self._status("Added “%s”%s" % (node_id, self._unmet_needs(node_id)))
#        self.select_node(node_id)
#
#    def add_card_after(self, node_id: str, step_key: str,
#                       stream: str = "") -> Optional[str]:
#        """把 ``step_key`` 接在 ``node_id`` 後面（順序 + 一條顯式連線）。
#
#        ``stream`` 是新卡要做在哪一條影像流上。**這件事必須傳下去**：接在一張
#        做 ref 的卡後面，結果新卡預設做在 test 上，使用者就得回控制列改參數 ——
#        而那正是他說「變很複雜」的東西。
#        """
#        nid = str(node_id)
#        if nid not in self.model.nodes:
#            return None
#        at = self.model.node_order.index(nid) + 1
#        try:
#            new_id = self.model.add_step(str(step_key), at=at)
#        except (KeyError, ParamError) as e:
#            self._status("Could not add card: %s" % e, "error")
#            return None
#        note = self._point_at_stream(new_id, str(stream)) if stream else ""
#        # 顯式連線：使用者的動作是「接在這張後面」，那條線就該是實線。
#        # （route 相鄰本來就會產生一條虛線，但它表達的是順序，不是這個意圖。）
#        self.model.add_edge(nid, new_id)
#        self._status("Added “%s” after “%s”%s%s"
#                     % (new_id, nid, note, self._unmet_needs(new_id)))
#        self.select_node(new_id)
#        return new_id
#
#    # ---- 「這張卡做在哪一條流上」（F7-18）----------------------------------
#    #: 主要影像流的參數名（依優先順序）。Enhance 卡一律叫 ``target`` 或
#    #: ``source``，而**一張卡只做一條流** —— 要對另一張圖做同一件事就再放一張
#    #: 卡，那才是畫布看得懂的說法。
#    _PRIMARY_PARAMS = ("target", "source")
#
#    def _primary_stream_of(self, node_id: str) -> str:
#        """``node_id`` 這張卡做在哪一條流上（接下去的卡預設跟著它走）。"""
#        node = self.model.nodes.get(str(node_id))
#        if node is None:
#            return ""
#        for name in self._PRIMARY_PARAMS:
#            val = str(node.params.get(name, "") or "")
#            if val:
#                return val
#        try:
#            writes = get_step(node.step).resolve_writes(node.params)
#        except KeyError:                           # pragma: no cover
#            return ""
#        return str(writes[0]) if writes else ""
#
#    def _point_at_stream(self, node_id: str, stream: str) -> str:
#        """把 ``node_id`` 的主要輸入指到 ``stream``（回一句給狀態列的話）。
#
#        這是「用節點表達要對哪一張圖做」的實作點：使用者從 ``ref`` 那顆輸出埠
#        拉一條線過來，講的就是**這張卡做在 ref 上**。以前那句話只能在控制列的
#        下拉裡講，畫布只表達得出先後順序 —— 於是 test 是主角、ref 是附帶。
#        """
#        node = self.model.nodes.get(str(node_id))
#        if node is None or not stream:
#            return ""
#        try:
#            specs = {p.name: p for p in get_step(node.step).params}
#        except KeyError:                       # pragma: no cover
#            return ""
#        for name in self._PRIMARY_PARAMS:
#            spec = specs.get(name)
#            if spec is None or spec.type not in ("image_key", "image_keys"):
#                continue
#            if str(node.params.get(name, "")) == stream:
#                return ""
#            try:
#                self.model.set_param(str(node_id), name, stream)
#            except ParamError:                 # pragma: no cover — 值就是流名
#                return ""
#            return " — “%s” now works on %s" % (node_id, stream)
#        return ""
#
#    def _producers_of(self, stream: str) -> List[str]:
#        """哪些卡片（用預設參數）會產出 ``stream``。"""
#        out: List[str] = []
#        for cls in visible_steps([s.describe() for s in list_steps()]) or []:
#            key = str(cls.get("key", ""))
#            try:
#                step_cls = get_step(key)
#                params = step_cls.validate_params({})
#                writes = step_cls.resolve_writes_for_kind(params, self.model.kind)
#            except Exception:              # noqa: BLE001 — 顯示用
#                continue
#            if stream in writes and step_cls.label:
#                out.append(str(step_cls.label))
#        return out
#
#    def _unmet_needs(self, node_id: str) -> str:
#        """剛加的卡少了什麼上游 —— 講成一句可以照做的話（回傳含前導空白）。
#
#        以前只有卡片庫上一個 ``needs ref_aligned`` 的灰字 badge。對不會寫 code
#        的人那句話沒有動作可做：他不知道 ``ref_aligned`` 是誰產的，也不知道
#        「不然還可以怎麼辦」。最常踩到的就是 Subtract —— 它預設吃對位過的
#        ``ref_aligned``，所以 Load 之後直接放 Subtract 一定缺一張上游。
#        """
#        node = self.model.nodes.get(str(node_id))
#        if node is None:
#            return ""
#        try:
#            step_cls = get_step(node.step)
#            needs = list(step_cls.resolve_reads(node.params))
#        except KeyError:
#            return ""
#        have = set(self.model.available_streams(before_node=str(node_id)))
#        missing = [s for s in needs if s and s not in have]
#        if not missing:
#            return ""
#        bits = []
#        for s in missing:
#            makers = self._producers_of(s)
#            bits.append("“%s” (add %s first)" % (s, " or ".join(makers))
#                        if makers else "“%s”" % s)
#        return (" — but it still needs the image stream %s, or point it at one "
#                "of: %s." % (", ".join(bits), ", ".join(sorted(have)) or "(none)"))
#
#    def _on_node_toggled(self, node_id: str, enabled: bool) -> None:
#        self.model.set_enabled(str(node_id), bool(enabled))
#
#    def _on_move_requested(self, node_id: str, delta: int) -> None:
#        self.model.move(str(node_id), int(delta))
#
#    # ---- 畫布連線（F7-6；F7-18 起帶著影像流）-------------------------------
#    def _on_edge_added(self, src: str, dst: str, stream: str = "") -> None:
#        """拉一條線。會造成循環時 model 回 False —— 那條線就不會出現。
#
#        擋在這裡（而不是等執行時報錯）是刻意的：使用者看到的是「這條線拉不
#        起來」，不是「拉起來之後整條 pipeline 壞掉」。
#
#        ``stream`` 是**線從哪個輸出埠出發**（F7-18）。從 ref 那顆埠拉過去，
#        意思就是「這張卡做在 ref 上」，所以下游那張卡的主要輸入跟著改。
#        以前這件事只能在控制列的下拉裡講，於是同一個動作在畫布上做不完。
#
#        兩個節點之間**已經有線**也照樣要處理那句話：先從 test 拉、再從 ref 拉
#        是很正常的操作（「我改變主意了，這張卡要做在 ref 上」），而以前它只會
#        得到一句「already connected」然後什麼都沒發生 —— 看起來就像畫布不准
#        你碰 ref。
#        """
#        src, dst, stream = str(src), str(dst), str(stream or "")
#        if self.model.has_edge(src, dst):
#            note = self._point_at_stream(dst, stream)
#            self._status(note.lstrip(" —").strip() if note else
#                         "%s → %s is already connected — every image stream "
#                         "they share is already drawn." % (src, dst))
#        elif self.model.add_edge(src, dst):
#            # 影像流在**線真的接起來之後**才改。會成環的那條線沒有落地，
#            # 它不該留下任何痕跡 —— 尤其不是「那張卡安靜地改成做 ref 了」。
#            self._status("Connected %s → %s%s"
#                         % (src, dst, self._point_at_stream(dst, stream)))
#        else:
#            self._status("Cannot connect %s → %s — that would make the "
#                         "pipeline loop back on itself." % (src, dst), "error")
#
#    def _on_edge_removed(self, src: str, dst: str) -> None:
#        if self.model.remove_edge(str(src), str(dst)):
#            self._status("Disconnected %s → %s" % (src, dst))
#
#    def _on_remove_requested(self, node_id: str) -> None:
#        node_id = str(node_id)
#        self.model.remove(node_id)
#        if self.selected_node == node_id:
#            self.selected_node = None
#            self.param_form.set_step(None, {}, [])
#        self._status("Removed “%s”" % node_id)
#
#    def select_node(self, node_id: str) -> bool:
#        """選取一個節點：右邊換成它的參數表單，預覽跑到它為止。"""
#        node_id = str(node_id)
#        node = self.model.nodes.get(node_id)
#        if node is None:
#            self._status("No such step: “%s”." % node_id, "error")
#            return False
#        self.selected_node = node_id
#        self._user_stream = None       # 換節點 → 影像流回到「這個節點的輸出」
#        # 換卡片＝上一段連續調整結束（見 viewmodel 的 coalescing）。不切的話，
#        # 「調 A 卡的 gamma → 換到 B 卡 → 再調回 A 卡的 gamma」會被併成一步。
#        self.model.end_coalescing()
#        self.pipeline.set_selected(node_id)
#        try:
#            describe = get_step(node.step).describe()
#        except KeyError:
#            describe = None
#        streams = self.model.available_streams(before_node=node_id)
#        self.param_form.set_step(describe, node.params, streams)
#        self.stack.setCurrentWidget(self.param_form)
#        self._refresh_region_button()
#        self._install_inspector(node.step)     # 右下角換成這張卡的儀表（F7-17）
#        self._refresh_inspector(self._last_result)
#        self._schedule_preview()
#        return True
#
#    # ==================================================================== #
#    # 主題（F7-2）
#    # ==================================================================== #
#    def toggle_theme(self) -> str:
#        """light ⇄ dark；換完立刻重畫，偏好寫進 QSettings。
#
#        所有顏色都走 ``theme.TOKENS``，但**自繪 widget 是在建構式裡取色的**
#        （直方圖長條、節點卡色條、Gallery chip…），所以換膚之後要叫它們重畫。
#        """
#        order = list(THEMES)
#        try:
#            nxt = order[(order.index(current_theme()) + 1) % len(order)]
#        except ValueError:                  # pragma: no cover — 主題名壞掉
#            nxt = DEFAULT_THEME
#        return self.set_theme(nxt)
#
#    def set_theme(self, name: str) -> str:
#        app = QApplication.instance()
#        applied = apply_theme(app, name) if app is not None else str(name)
#        save_theme(applied)
#        self._repaint_for_theme()
#        self._status("Theme: %s" % applied)
#        return applied
#
#    def _repaint_for_theme(self) -> None:
#        """把在建構式裡吃過 token 的元件重建/重畫一次。"""
#        self.library.set_steps(
#            visible_steps([s.describe() for s in list_steps()])
#            + [_SCORE_LIBRARY_ENTRY])
#        self.library.refresh_colors()
#        self._refresh_pipeline()
#        self.gallery.refresh_styles()
#        for w in (self.histogram, self.image_view, self.verdict,
#                  self.feature_table, self.library, self.pipeline, self.gallery):
#            w.update()
#
#    def show_score_page(self) -> None:
#        """切到分數編輯頁（順便刷新特徵下拉）。"""
#        self._refresh_feature_combo()
#        self._sync_score_widgets()
#        self.stack.setCurrentWidget(self.score_pane)
#
#    def show_param_page(self) -> None:
#        self.stack.setCurrentWidget(self.param_form)
#
#    # ==================================================================== #
#    # 參數編輯
#    # ==================================================================== #
#    def _on_param_edited(self, name: str, value: Any) -> None:
#        """ParamForm 的唯一出口：驗證通過才寫回 model，失敗就把那列變紅字。"""
#        node_id = self.selected_node
#        if node_id is None or node_id not in self.model.nodes:
#            self._status("Select a step in the pipeline before editing parameters.", "error")
#            return
#        try:
#            self.model.set_param(node_id, str(name), value)
#        except ParamError as e:
#            self.param_form.show_error(str(name), str(e))
#            self._status(str(e))
#        else:
#            self.param_form.clear_errors()
#            self._autofill_output_prefix(node_id, str(name), value)
#
#    #: 挑了區域就順手把輸出名填成區域的名字（F7-11）。
#    _PREFIX_SOURCE = "roi"
#
#    def _autofill_output_prefix(self, node_id: str, name: str, value: Any) -> None:
#        """使用者挑了一個區域 → 輸出名還空著的話，就填成那個區域的名字。
#
#        為什麼要自動填
#        --------------
#        「兩張量測卡的特徵會互相蓋掉」是一個**命名空間**的問題，而製程工程師沒有
#        理由要懂那是什麼。但他做的動作已經表達了意圖 —— 他把這張卡指到 `epi`，
#        那結果本來就該叫 `epi_...`。所以由工具把話補完。
#
#        只在**空著**的時候填：使用者自己改過的名字不可以被蓋掉，
#        不然「我明明改了它又跳回去」比沒有這個功能更糟。
#        """
#        if name != self._PREFIX_SOURCE:
#            return
#        node = self.model.nodes.get(node_id)
#        if node is None or "output_prefix" not in node.params:
#            return
#        if str(node.params.get("output_prefix", "") or "").strip():
#            return                       # 使用者已經自己命名過了
#        wanted = str(value or "").strip()
#        if not wanted:
#            return
#        try:
#            self.model.set_param(node_id, "output_prefix", wanted)
#        except ParamError:
#            return                       # 區域名不能當變數名 -> 安靜跳過
#        self.param_form.set_step(
#            get_step(node.step).describe(), node.params,
#            self.model.available_streams(before_node=node_id))
#        self._status("Results from this card will be named “%s_…” so they do "
#                     "not collide with another card measuring a different "
#                     "region." % wanted)
#
#    # ==================================================================== #
#    # 分數編輯
#    # ==================================================================== #
#    def _on_expr_edited(self, text: str) -> None:
#        if self._syncing:
#            return
#        self.model.set_expr(str(text))
#
#    def _on_feature_chosen(self, index: int) -> None:
#        """「插入特徵 ▾」：把特徵名插到表達式的游標位置。"""
#        if self._syncing or int(index) <= 0:
#            return
#        token = self.feature_combo.itemText(int(index))
#        self._syncing = True
#        try:
#            self.feature_combo.setCurrentIndex(0)
#        finally:
#            self._syncing = False
#        if not token:
#            return
#        text = self.expr_edit.text()
#        pos = self.expr_edit.cursorPosition()
#        pos = max(0, min(pos, len(text)))
#        new_text = text[:pos] + token + text[pos:]
#        self._syncing = True
#        try:
#            self.expr_edit.setText(new_text)
#            self.expr_edit.setCursorPosition(pos + len(token))
#        finally:
#            self._syncing = False
#        self.model.set_expr(new_text)
#
#    def _on_threshold_spin(self, value: float) -> None:
#        if self._syncing:
#            return
#        self.model.set_threshold(float(value))
#
#    # ---- 直方圖門檻線 -----------------------------------------------------
#    def _on_threshold_changed(self, value: float) -> None:
#        """拖曳中：**只**重算 bin 數（秒回），絕不寫 model、不重跑。"""
#        self._refresh_bin_summary(float(value))
#        self._status("Threshold %.3g (applied when you release the mouse)" % float(value))
#
#    def _on_threshold_committed(self, value: float) -> None:
#        """放開滑鼠：這時才寫回 model（會觸發刷新與預覽）。"""
#        self.model.set_threshold(float(value))
#        self._status("Threshold set to %.3g" % float(value))
#
#    # ==================================================================== #
#    # 資料集
#    # ==================================================================== #
#    def load_dataset_path(self, path: Any, tiff: Optional[Any] = None,
#                          sync: bool = False) -> bool:
#        """載入 KLARF（``sync=True`` 走同步路徑，給測試 / CLI 用）。"""
#        path = str(path)
#        tiff = None if tiff is None else str(tiff)
#        if not os.path.isfile(path):
#            self._status("File not found: %s" % path)
#            return False
#        if sync:
#            try:
#                ds = DatasetLoadWorker.run_sync(path, tiff)
#            except Exception as e:      # noqa: BLE001 — UI 邊界，一律回報
#                self._status("Could not load dataset: %s: %s" % (type(e).__name__, e), "error")
#                return False
#            return self._on_dataset_loaded(ds)
#        if not self.dataset_worker.start(path, tiff):
#            self._status("A dataset is already loading — please wait.")
#            return False
#        self._progress_busy("Loading %s…" % os.path.basename(path))
#        self._status("Loading: %s" % os.path.basename(path))
#        return True
#
#    def _on_dataset_loaded(self, dataset: Any) -> bool:
#        # F7-1：型別要到載完才知道，所以擋在這裡而不是 load_dataset_path。
#        # 擋下來時**不動既有狀態** —— 使用者手上原本那份資料集還在，
#        # 開錯一個檔不會把他正在調的東西弄丟。
#        kind = getattr(dataset, "kind", None)
#        if not is_supported_kind(kind):
#            self._status(unsupported_kind_message(kind))
#            return False
#
#        self.dataset = dataset
#        items = list(getattr(dataset, "items", []) or [])
#        self.defect_index = 0
#        # 試跑筆數跟著資料集走：對一份 24 顆的 lot 顯示「First 200」只會讓人困惑
#        if items:
#            self.spin_trial_n.setValue(
#                max(self.spin_trial_n.minimum(),
#                    min(DEFAULT_TRIAL_N, len(items))))
#        # 縮圖工只拿得到 defect_id，這張表是它回頭找 DefectItem 的唯一途徑
#        self._items_by_id = {str(getattr(it, "defect_id", "")): it for it in items}
#        # 換資料集 = 舊的結果與縮圖全部作廢
#        self.trial_results = []
#        self.trial_scores = []
#        self._score_filter = None
#        self.gallery.set_items([])
#
#        self._syncing = True
#        try:
#            self.defect_combo.clear()
#            for it in items:
#                self.defect_combo.addItem(str(getattr(it, "defect_id", "?")))
#            if items:
#                self.defect_combo.setCurrentIndex(0)
#        finally:
#            self._syncing = False
#
#        # 空流程時讓 route 型別跟著資料走（載了 recipe 之後就以 recipe 為準）
#        if not self.model.node_order:
#            self.model.kind = str(getattr(dataset, "kind", self.model.kind))
#
#        self._update_defect_label()
#        self._update_action_states()
#        self._progress_done()
#        warn = list(getattr(dataset, "warnings", []) or [])
#        msg = "Loaded %d defects (input type %s)" % (
#            len(items), getattr(dataset, "kind", "?"))
#        if warn:
#            msg += "   ! %s" % warn[0]
#        self._status(msg)
#        if items:
#            self.refresh_preview(force=False)
#        return True
#
#    def _items(self) -> List[Any]:
#        """目前資料集的 defect 清單（沒有資料集就是空的）。"""
#        if not self.dataset:
#            return []
#        return list(getattr(self.dataset, "items", []) or [])
#
#    def _current_item(self) -> Optional[Any]:
#        items = self._items()
#        if not items:
#            return None
#        i = max(0, min(int(self.defect_index), len(items) - 1))
#        self.defect_index = i
#        return items[i]
#
#    def _update_defect_label(self) -> None:
#        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
#        if not items:
#            self.defect_label.setText("(no dataset loaded)")
#            return
#        i = max(0, min(int(self.defect_index), len(items) - 1))
#        self.defect_label.setText(
#            "%s · defect %d / %d" % (getattr(self.dataset, "kind", "?"),
#                                     i + 1, len(items)))
#
#    def set_defect_index(self, index: int) -> bool:
#        """跳到第 ``index`` 顆 defect（超出範圍會夾住）。"""
#        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
#        if not items:
#            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
#            return False
#        i = max(0, min(int(index), len(items) - 1))
#        self.defect_index = i
#        self._syncing = True
#        try:
#            if self.defect_combo.currentIndex() != i:
#                self.defect_combo.setCurrentIndex(i)
#        finally:
#            self._syncing = False
#        self._update_defect_label()
#        self._schedule_preview()
#        return True
#
#    def step_defect(self, delta: int) -> bool:
#        return self.set_defect_index(int(self.defect_index) + int(delta))
#
#    def _on_defect_combo(self, index: int) -> None:
#        if self._syncing or int(index) < 0:
#            return
#        self.set_defect_index(int(index))
#
#    # ==================================================================== #
#    # Recipe
#    # ==================================================================== #
#    def load_recipe_path(self, path: Any, sync: bool = False) -> bool:
#        """載入 recipe JSON：重建 model、重接 listener、刷新所有面板。"""
#        path = str(path)
#        try:
#            recipe = Recipe.load(path)
#        except Exception as e:          # noqa: BLE001 — UI 邊界
#            self._status("Could not load recipe: %s: %s" % (type(e).__name__, e), "error")
#            return False
#        kind = None
#        ds_kind = str(getattr(self.dataset, "kind", "")) if self.dataset else ""
#        if ds_kind and ds_kind in recipe.routes:
#            kind = ds_kind
#        self._apply_model(RecipeModel.from_recipe(recipe, kind=kind))
#        self.recipe_path = path
#        self.setWindowTitle("ADEPT Studio — %s" % self.model.recipe_id)
#        n = len(self.model.node_order)
#        self._status("Loaded recipe “%s” (%d steps, route %s)"
#                     % (self.model.recipe_id, n, self.model.kind))
#        if ds_kind and ds_kind not in recipe.routes:
#            self._status("Loaded recipe “%s”, but it has no '%s' route — "
#                         "preview and trial runs will fail."
#                         % (self.model.recipe_id, ds_kind))
#        self.refresh_preview(sync=sync, force=False)
#        return True
#
#    def _apply_model(self, model: RecipeModel) -> None:
#        """換掉 model 並重接所有顯示（listener 一定要重掛）。"""
#        self.model = model
#        self.model.add_listener(self._on_model_changed)
#        self.selected_node = None
#        self._user_stream = None
#        self.pipeline.set_selected(None)
#        self.param_form.set_step(None, {}, [])
#        self.stack.setCurrentWidget(self.param_form)
#        self._refresh_all()
#
#    def load_template(self) -> bool:
#        """載入內建的 die-to-die 範本；檔案不在就只在狀態列抱怨，不炸。"""
#        path = TEMPLATE_RECIPE
#        if not path.is_file():
#            self._status("Built-in template not found: %s" % path)
#            return False
#        return self.load_recipe_path(str(path))
#
#    def save_recipe_path(self, path: Any) -> bool:
#        """把目前 model 存成 recipe JSON。"""
#        path = str(path)
#        if not self.model.node_order:
#            self._status("The pipeline is empty — nothing to save.")
#            return False
#        try:
#            self.model.to_recipe().save(path)
#        except Exception as e:          # noqa: BLE001 — UI 邊界
#            self._status("Could not save: %s: %s" % (type(e).__name__, e), "error")
#            return False
#        self.recipe_path = path
#        self.model.dirty = False
#        self.model.end_coalescing()      # 存檔＝一段編輯結束（見 viewmodel）
#        self._status("Saved: %s" % path)
#        return True
#
#    # ==================================================================== #
#    # 預覽
#    # ==================================================================== #
#    def _schedule_preview(self) -> None:
#        """排一次去抖動的預覽（300ms 內的連續變動只算最後一次）。"""
#        self._preview_timer.start()
#
#    def _on_preview_timeout(self) -> None:
#        self.refresh_preview(force=False)
#
#    def refresh_preview(self, sync: bool = False, force: bool = True) -> bool:
#        """重算單顆預覽。
#
#        ``force=False`` 時前置條件不滿足只是安靜跳過（去抖動計時器用的路徑，
#        不要一直在狀態列鬼叫）；``force=True`` 會把原因寫到狀態列。
#        """
#        self._preview_timer.stop()
#        # 每要求一次預覽就換一個世代編號。背景那筆算完時如果編號已經不是它
#        # 出發時那個，就代表畫面上的東西比它新 —— 那筆結果直接丟掉。
#        self._preview_epoch += 1
#        if not self.model.node_order:
#            if force:
#                self._status("The pipeline is empty — add the first card from the library.")
#            return False
#        item = self._current_item()
#        if item is None:
#            if force:
#                self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
#            return False
#
#        recipe = self.model.to_recipe()
#        upto = self.selected_node if self.selected_node in self.model.nodes else None
#        if sync:
#            try:
#                result = PreviewWorker.run_sync(recipe, item, self.model.kind,
#                                                upto_node=upto)
#            except Exception as e:      # noqa: BLE001 — UI 邊界
#                self._status("Preview failed: %s: %s" % (type(e).__name__, e), "error")
#                return False
#            self._on_preview_ready(result)
#            return True
#        self._async_epoch = self._preview_epoch
#        self.preview_worker.request(recipe, item, self.model.kind, upto_node=upto)
#        return True
#
#    def _on_async_preview_ready(self, result: Any) -> None:
#        """背景預覽算完。**過期的結果直接丟掉。**
#
#        `PreviewWorker` 只合併「還沒開跑」的請求；已經在跑的那一筆照樣會跑完並
#        發出 ready。所以「先送出一筆背景預覽，接著又跑了一筆同步預覽」的時候，
#        舊的那筆會**後到**，把新的畫面蓋掉 —— 使用者看到的是他剛剛那個動作
#        之前的狀態，而且不會再更新，因為沒有人會再算一次。
#
#        這個順序在實際操作裡並不罕見（點卡片 → 立刻改參數），
#        只是以前的症狀是「影像閃一下」，不容易歸因；投影曲線面板讓它變成
#        「面板空白」，才浮出來。
#        """
#        if getattr(self, "_async_epoch", 0) != self._preview_epoch:
#            return
#        self._on_preview_ready(result)
#
#    def _on_preview_busy(self, busy: bool) -> None:
#        if busy:
#            self._status("Computing preview…")
#
#    def _on_preview_ready(self, result: Any) -> None:
#        self._last_result = result
#        ctx = getattr(result, "context", None)
#        images = dict(getattr(ctx, "images", {}) or {}) if ctx is not None else {}
#        self._preview_images = images
#
#        self._populate_streams(images)
#        self._show_current_stream()
#
#        self._refresh_inspector(result)
#        highlight = self._highlight_features(result)
#        self.feature_table.set_features(getattr(result, "features", {}) or {},
#                                        highlight=highlight)
#        score = getattr(result, "score", None)
#        self.verdict.set_verdict(getattr(result, "bin", None)
#                                 if score is not None else None)
#
#        if not getattr(result, "ok", False):
#            # 失敗照樣把已經算出來的影像留在畫面上（診斷比清空有用）
#            self._status("Preview problem: %s"
#                         % (getattr(result, "error", None) or "unknown error"))
#        elif self.selected_node:
#            self._status("Preview: stopped after “%s” (%d image streams)"
#                         % (self.selected_node, len(images)))
#        else:
#            self._status("Preview done (%d image streams)%s"
#                         % (len(images),
#                            "   score %.4g" % score if score is not None else ""))
#
#    #: 會產生投影曲線的卡片 key（面板只在編輯它的時候出現）。
#    PROFILE_STEP = "roi_profile"
#
#    # ==================================================================== #
#    # 區域跨顆檢視（F7-11）
#    # ==================================================================== #
#    def selected_regions(self) -> List[str]:
#        """選取的節點會定義哪些具名區域（不是 Region 卡就是空的）。"""
#        node = self.model.nodes.get(self.selected_node or "")
#        return regions_of_node(node) if node is not None else []
#
#    #: 需要模板的卡片 key（那張卡的模板只能用這個對話框做出來）。
#    TEMPLATE_STEP = "roi_template"
#
#    def template_build_available(self) -> bool:
#        """選取的卡片需要模板嗎（用明確狀態，不要問 widget 的可見性）。"""
#        node = self.model.nodes.get(self.selected_node or "")
#        return bool(node is not None and node.step == self.TEMPLATE_STEP)
#
#    def _on_param_action(self, param_name: str) -> None:
#        """某個參數說「我的值要用別的方式產生」（目前只有模板）。"""
#        if str(param_name) == "template":
#            self.open_template_dialog()
#
#    def open_template_dialog(self) -> Optional[Any]:
#        """開「從大圖建模板」對話框；接受之後把模板寫回這張卡。"""
#        if not self.template_build_available():
#            self._status("Select a Locate region by template card first.", "error")
#            return None
#        node_id = self.selected_node
#        dlg = TemplateDialog(self)
#        dlg.accepted_template.connect(
#            lambda text, axis, nid=node_id: self._apply_template(nid, text, axis))
#        self.template_dialog = dlg
#        dlg.show()
#        return dlg
#
#    def _apply_template(self, node_id: str, text: str, axis: str) -> None:
#        """把疊好的模板寫進卡片參數（連同它適用的方向）。"""
#        if node_id not in self.model.nodes:
#            return
#        try:
#            self.model.set_param(node_id, "template", str(text))
#            self.model.set_param(node_id, "locate_axis", str(axis))
#        except ParamError as e:
#            self._status("Could not store the template: %s" % e, "error")
#            return
#        node = self.model.nodes[node_id]
#        self.param_form.set_step(
#            get_step(node.step).describe(), node.params,
#            self.model.available_streams(before_node=node_id))
#        self._status("Template stored in this recipe — it repeats along %s. "
#                     "Now mark the region on the cell with the Region "
#                     "left/top/width/height sliders." % axis)
#        self._schedule_preview()
#
#    def region_check_available(self) -> bool:
#        """現在按得下「跨顆檢視」嗎。
#
#        用明確狀態而不是 ``btn.isVisible()`` —— 視窗還沒 show 之前後者恆為
#        False（CLAUDE.md §7 的老坑）。
#        """
#        return bool(self.selected_regions()) and bool(self._items())
#
#    # ---- 右下角：卡片儀表（F7-17）------------------------------------------
#    def show_bottom_page(self, index: int) -> None:
#        """0 = 這張卡的儀表，1 = 特徵表。"""
#        index = 1 if int(index) else 0
#        if index == 0 and self._inspector is None:
#            index = 1          # 這張卡沒有儀表 —— 不要給一片空白
#        self.bottom_stack.setCurrentIndex(index)
#        self.btn_tab_card.setChecked(index == 0)
#        self.btn_tab_features.setChecked(index == 1)
#        self.btn_tab_card.setEnabled(self._inspector is not None)
#
#    def bottom_page(self) -> int:
#        return int(self.bottom_stack.currentIndex())
#
#    def inspector(self) -> Optional[Any]:
#        """目前掛著的卡片儀表（沒有就 None）。"""
#        return self._inspector
#
#    def _install_inspector(self, step_key: str) -> None:
#        """換卡片時換儀表。沒有註冊儀表的卡就只剩特徵表。"""
#        cls = inspector_for(step_key)
#        current = type(self._inspector) if self._inspector is not None else None
#        if cls is not current:
#            if self._inspector is not None:
#                self.inspector_slot.removeWidget(self._inspector)
#                self._inspector.setParent(None)
#                self._inspector.deleteLater()
#                self._inspector = None
#            if cls is not None:
#                self._inspector = cls(self.inspector_host)
#                self.inspector_slot.addWidget(self._inspector)
#            self.btn_tab_card.setText(str(getattr(cls, "title", "Card"))
#                                      if cls is not None else "Card")
#        # **每次都要同步頁面**，不能因為「儀表類別沒變」就跳過：兩張都沒有儀表
#        # 的卡片連續選下去時，類別確實沒變（都是 None），但畫面若停在儀表那一頁
#        # 就是一片空白 —— 而那比原本的特徵表還糟。
#        self.show_bottom_page(0 if cls is not None else 1)
#
#    def _refresh_inspector(self, result: Any = None) -> None:
#        """把三種來源餵給儀表：這張卡的參數、這一顆的結果、整批的結果。"""
#        insp = self._inspector
#        if insp is None:
#            self.inspector_summary.setText("")
#            return
#        node = self.model.nodes.get(self.selected_node or "")
#        one: Dict[str, Any] = {}
#        if result is not None:
#            one = {"features": dict(getattr(result, "features", {}) or {})}
#        # meta 在 **context** 上，不在 result 上（result 只帶 features/score/bin）。
#        ctx = getattr(result, "context", None) if result is not None else None
#        meta = dict(getattr(ctx, "meta", {}) or {})
#        # 「這張卡產出哪些特徵」要問卡片庫（含 output_prefix）—— 儀表只負責畫。
#        feats: List[str] = []
#        if node is not None:
#            try:
#                feats = list(get_step(node.step).resolve_features(node.params))
#            except Exception:              # noqa: BLE001 — 顯示用
#                feats = []
#        insp.set_context(self.selected_node or "",
#                         params=dict(node.params) if node else {},
#                         result=one, batch=self.trial_results, meta=meta,
#                         feature_names=feats)
#        self.inspector_summary.setText(insp.summary())
#
#    def _refresh_region_button(self) -> None:
#        regions = self.selected_regions()
#        has_data = bool(self._items())
#        self.btn_region_check.setVisible(bool(regions))
#        self.btn_region_check.setEnabled(bool(regions) and has_data)
#        if regions and not has_data:
#            self.btn_region_check.setToolTip(
#                "No dataset loaded yet — use “Open KLARF…” first.")
#
#    def open_region_check(self, n: Optional[int] = None,
#                          sync: bool = False) -> bool:
#        """把選取節點定義的區域畫到前 N 顆上。
#
#        為什麼要有這個視窗
#        ------------------
#        區域設定對不對是一個**關於整批**的問題：patch 是以缺陷為中心裁的，
#        所以結構在每張 patch 裡的位置本來就不一樣 —— 在第 1 顆剛好的框，
#        第 50 顆可能整個偏掉。看單顆永遠看不出這件事。
#        """
#        regions = self.selected_regions()
#        if not regions:
#            self._status("Select a card that defines a region first.", "error")
#            return False
#        items = self._items()
#        if not items:
#            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
#            return False
#
#        limit = int(n if n is not None else self.spin_trial_n.value())
#        limit = max(1, min(limit, MAX_CHECK, len(items)))
#        node = self.model.nodes[self.selected_node]
#        source = str(node.params.get("source", "") or "") or None
#        args = (self.model.to_recipe(), items[:limit], self.model.kind,
#                self.selected_node, regions, REGION_THUMB, source)
#
#        if self.region_window is None:
#            self.region_window = RegionCheckWindow(self)
#            self.region_window.defect_activated.connect(self._on_defect_activated)
#
#        if sync:
#            self._apply_region_results(regions,
#                                       RegionCheckWorker.run_sync(*args))
#            return True
#        self._region_regions = regions
#        if not self.region_check_worker.start(*args):
#            self._status("Still checking the previous region — please wait.")
#            return False
#        self._status("Checking “%s” on %d defects…"
#                     % (", ".join(regions), limit))
#        return True
#
#    def _on_region_ready(self, results: Any) -> None:
#        self._apply_region_results(list(getattr(self, "_region_regions", []) or []),
#                                   list(results or []))
#
#    def _apply_region_results(self, regions: Sequence[str],
#                              results: Sequence[Dict[str, Any]]) -> None:
#        if self.region_window is None:
#            self.region_window = RegionCheckWindow(self)
#            self.region_window.defect_activated.connect(self._on_defect_activated)
#        self.region_window.set_results(list(regions), list(results))
#        self.region_window.show()
#        self.region_window.raise_()
#        self._status(self.region_window.summary_text())
#
#    @property
#    def profile_panel(self) -> Any:
#        """投影曲線面板 —— 現在住在 ``ProfileInspector`` 裡面（F7-17）。
#
#        保留這個名字是因為它是「這張卡的面板」的對外身分（測試與狀態列都用
#        它）。選的不是投影定位卡時回一個**空的替身**，這樣呼叫端不必到處
#        寫 ``if is None``。
#        """
#        insp = self._inspector
#        panel = getattr(insp, "panel", None)
#        if panel is not None:
#            return panel
#        if getattr(self, "_no_profile", None) is None:
#            self._no_profile = ProfilePanel(self)
#            self._no_profile.setVisible(False)
#        return self._no_profile
#
#    def profile_panel_visible(self) -> bool:
#        """面板現在開著嗎（用明確狀態，不要問 ``isVisible()``）。"""
#        node = self.model.nodes.get(self.selected_node or "")
#        return bool(node is not None and node.step == self.PROFILE_STEP)
#
#    def _highlight_features(self, result: Any) -> Sequence[str]:
#        """選取節點這一步新增/改值的特徵 → 在特徵表裡標色。"""
#        nid = self.selected_node
#        if not nid:
#            return ()
#        for tr in getattr(result, "traces", []) or []:
#            if getattr(tr, "node_id", None) == nid:
#                return list(getattr(tr, "features_added", {}) or {})
#        return ()
#
#    def _default_stream(self, images: Dict[str, Any]) -> str:
#        """點一張卡時，左邊那張圖預設顯示哪一條流。
#
#        規則是**這張卡的主要輸出**，不是「它寫過的最後一條流」。這兩者以前被
#        當成同一件事（取 ``writes`` 的最後一個），但當時 Enhance 卡的
#        ``resolve_writes`` 是 ``[主流] + 附帶的那一串``，於是預設值一路是那一串
#        的最後一項 —— 點 Normalize 就跳到 ``ref``。並排比對開著、右邊又停在
#        ``ref`` 的時候，畫面就變成左右兩張一模一樣的 ref，每點一張卡都要手動
#        切回來（F7-9 試用回饋 §4）。F7-18 之後一張卡只寫一條流，兩者又合一了，
#        但這條規則仍然是對的（``roi_template`` 這類卡的 writes 不只一項）。
#        """
#        nid = self.selected_node
#        node = self.model.nodes.get(nid) if nid else None
#        if node is not None:
#            for name in self._PRIMARY_PARAMS:
#                val = str(node.params.get(name, "") or "")
#                if val in images:
#                    return val
#            try:
#                writes = get_step(node.step).resolve_writes(node.params)
#            except KeyError:
#                writes = []
#            for w in reversed(list(writes)):
#                if w in images:
#                    return str(w)
#        if "test" in images:
#            return "test"
#        for k in images:
#            return str(k)
#        return ""
#
#    def _populate_streams(self, images: Dict[str, Any]) -> None:
#        """重建影像流下拉；使用者**親手挑過**的那條還在就留著。
#
#        「親手挑過」只認 :meth:`_on_stream_changed`（真的動了下拉）；換節點時
#        會清掉，讓畫面自動跳到新節點的輸出 —— 點卡片就看得到那張圖。
#        """
#        names = sorted(images)
#        want = (self._user_stream if self._user_stream in images
#                else self._default_stream(images))
#        want_b = (self._user_stream_b if self._user_stream_b in images
#                  else self._default_compare_stream(images, want))
#        if want_b == want:
#            # 左右同一條流 = 兩張一模一樣的圖，那是並排唯一沒有意義的狀態。
#            # 使用者親手挑的右邊也讓步 —— 他挑 ref 是為了「跟左邊比」，
#            # 不是為了「看兩次 ref」。
#            want_b = self._default_compare_stream(images, want)
#        self._syncing = True
#        try:
#            self.stream_combo.clear()
#            self.stream_combo.addItems(names)
#            if want in names:
#                self.stream_combo.setCurrentIndex(names.index(want))
#            self.stream_combo_b.clear()
#            self.stream_combo_b.addItems(names)
#            if want_b in names:
#                self.stream_combo_b.setCurrentIndex(names.index(want_b))
#        finally:
#            self._syncing = False
#
#    def _default_compare_stream(self, images: Dict[str, Any], left: str) -> str:
#        """並排的右邊預設放什麼：左邊是 test 就配 ref（反之亦然）。
#
#        並排最常見的用途就是「這張 Enhance 卡有沒有把 test 和 ref 調成不一樣」，
#        所以預設直接給那一對，不要讓使用者每次都自己挑。
#        """
#        pair = {"test": "ref", "ref": "test"}
#        mate = pair.get(str(left))
#        if mate and mate in images:
#            return mate
#        for k in ("ref", "diff", "test"):
#            if k in images and k != left:
#                return k
#        for k in sorted(images):
#            if k != left:
#                return str(k)
#        return str(left)
#
#    def _show_current_stream(self) -> None:
#        self.image_view.set_image(
#            self._preview_images.get(self.stream_combo.currentText()))
#        if self.compare_check.isChecked():
#            self.image_view_b.set_image(
#                self._preview_images.get(self.stream_combo_b.currentText()))
#
#    def _on_stream_changed(self, text: str) -> None:
#        if self._syncing:
#            return
#        self._user_stream = str(text) or None
#        self._show_current_stream()
#
#    def _on_stream_b_changed(self, text: str) -> None:
#        if self._syncing:
#            return
#        self._user_stream_b = str(text) or None
#        self._show_current_stream()
#
#    # ---- 並排比對（F7-8）--------------------------------------------------
#    def set_compare(self, on: bool) -> bool:
#        """開／關並排的第二張圖。回傳最後的狀態。
#
#        **預設是關的**，這是刻意的：F7-5 把 Gallery 與直方圖搬走，就是為了讓
#        右欄的影像變大（使用者原話「影像最好大一點、置中」）。預設並排等於
#        把剛爭取到的寬度再砍一半。真正需要並排的是**調 Enhance 卡的時候**
#        （確認 test 與 ref 被調成一樣），那是一個明確的時機，一次點擊就到。
#
#        兩張圖的縮放與平移連動 —— 沒有連動的並排要使用者自己把兩邊拖到同一個
#        位置才比得起來，那還不如切換一張。
#        """
#        on = bool(on)
#        if self.compare_check.isChecked() != on:
#            self.compare_check.setChecked(on)     # 會再繞回這裡一次
#            return self.compare_check.isChecked()
#        self.image_view_b.setVisible(on)
#        self.stream_combo_b.setVisible(on)
#        self._compare_on = on
#        if on:
#            self._show_current_stream()
#            scale, offset = self.image_view.view_state()
#            self.image_view_b.set_view(scale, offset)
#        else:
#            self.image_view_b.set_image(None)
#        return on
#
#    def compare_enabled(self) -> bool:
#        """並排現在開著嗎。用明確狀態而非 ``isVisible()``（視窗還沒 show 時後者恆假）。"""
#        return bool(self._compare_on)
#
#    def _link_views(self, source: Any, target: Any, scale: float, offset) -> None:
#        """把 ``source`` 的檢視狀態推給 ``target``（單向，避免無限來回）。"""
#        if not self._compare_on or self._view_syncing:
#            return
#        self._view_syncing = True
#        try:
#            target.set_view(scale, offset)
#        finally:
#            self._view_syncing = False
#
#    # ==================================================================== #
#    # 試跑
#    # ==================================================================== #
#    def run_trial(self, n: int, workers: Optional[int] = 1,
#                  sync: bool = False, cache_dir: Optional[Any] = None) -> bool:
#        """跑前 ``n`` 顆並更新直方圖。``sync=True`` 走同步路徑（測試用）。"""
#        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
#        if not items:
#            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
#            return False
#        if not self.model.node_order:
#            self._status("The pipeline is empty — add a card before running.")
#            return False
#
#        # 跑之前先 lint（F7-9）。引擎的契約是「單顆出錯不殺整批」，所以一組接
#        # 錯的卡片以前的下場是**跑完 200 顆、每一顆都失敗**：進度條走完、結果
#        # 是空的、原因埋在每顆的錯誤訊息裡。同一份檢查 CLI 從 M1 就在用了，
#        # 只是 Studio 一直沒接上來。只擋 error，warning 照跑。
#        issues = self.model.validate()
#        problems = [i for i in issues if i.level == "error"]
#        if problems:
#            first = problems[0]
#            more = ("  (and %d more problem%s)"
#                    % (len(problems) - 1, "" if len(problems) == 2 else "s")
#                    if len(problems) > 1 else "")
#            self._status("Cannot run — %s: %s%s"
#                         % (first.title, first.detail, more), "error")
#            return False
#        self._pending_warnings = [i for i in issues if i.level == "warning"]
#
#        limit = max(1, min(int(n), len(items)))
#        recipe = self.model.to_recipe()
#        cdir = None if cache_dir is None else str(cache_dir)
#
#        if sync:
#            t0 = time.time()
#            try:
#                results = TrialWorker.run_sync(
#                    recipe, self.dataset, limit,
#                    workers=int(workers) if workers else 1, cache_dir=cdir)
#            except Exception as e:      # noqa: BLE001 — UI 邊界
#                self._status("Trial run failed: %s: %s" % (type(e).__name__, e), "error")
#                return False
#            self._apply_trial_results(results, time.time() - t0)
#            return True
#
#        self._trial_t0 = time.time()
#        if not self.trial_worker.start(recipe, self.dataset, limit,
#                                       workers=workers, cache_dir=cdir):
#            self._status("A run is already in progress — please wait.")
#            return False
#        self._progress_set(0, limit, "%v / %m defects")
#        self._show_stop(True)
#        self._status("Running: 0 / %d" % limit)
#        return True
#
#    def _on_trial_clicked(self) -> None:
#        self.run_trial(int(self.spin_trial_n.value()), workers=TRIAL_WORKERS,
#                       cache_dir=DEFAULT_CACHE_DIR)
#
#    def _on_full_clicked(self) -> None:
#        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
#        if not items:
#            self._status("No dataset loaded yet — use “Open KLARF…” first.", "error")
#            return
#        self.run_trial(len(items), workers=TRIAL_WORKERS,
#                       cache_dir=DEFAULT_CACHE_DIR)
#
#    def _on_trial_progress(self, done: int, total: int) -> None:
#        self._progress_set(int(done), int(total), "%v / %m defects")
#        self._status("Running: %d / %d" % (int(done), int(total)))
#
#    def _on_trial_done_async(self, results: Any) -> None:
#        self._apply_trial_results(list(results or []),
#                                  time.time() - (self._trial_t0 or time.time()))
#
#    def _apply_trial_results(self, results: Sequence[Dict[str, Any]],
#                             elapsed: float) -> None:
#        results = list(results or [])
#        self._progress_done()
#        self.trial_results = results
#        self.trial_scores = [r["score"] for r in results
#                             if r.get("ok") and r.get("score") is not None]
#        edges, counts = histogram(self.trial_scores)
#        self.histogram.set_data(edges, counts)
#        self.histogram.set_threshold(self.model.threshold)
#        self._refresh_bin_summary(self.model.threshold)
#        self._populate_gallery(results)
#        self._refresh_inspector(self._last_result)   # 儀表吃的是整批（F7-17）
#        self._update_action_states()
#        ok = sum(1 for r in results if r.get("ok"))
#        fail = len(results) - ok
#        # 被按停止的那一批**不能講「finished」**：數字是真的，但它描述的是
#        # 「你叫我停的時候跑到哪裡」，不是整批的結果。差一個字，後面所有
#        # 根據這批數字做的判斷就都建立在錯的前提上。
#        stopped = bool(self.trial_worker.is_aborted())
#        msg = ("%s: %d defects (%d ok, %d failed) in %.1f s"
#               % ("Run stopped" if stopped else "Run finished",
#                  len(results), ok, fail, float(elapsed)))
#        # 跑之前的 lint 警告在這裡才講：跑之前講會被「Running: 3 / 200」洗掉。
#        # 警告不擋執行，但它描述的是「跑得完、數字卻不是你以為的那個」——
#        # 例如兩張量測卡撞名，後面那張把前面那張蓋掉了。
#        warns = list(getattr(self, "_pending_warnings", []) or [])
#        if warns:
#            more = ("  (and %d more warning%s)"
#                    % (len(warns) - 1, "" if len(warns) == 2 else "s")
#                    if len(warns) > 1 else "")
#            msg = "%s  ⚠ %s: %s%s" % (msg, warns[0].title, warns[0].detail, more)
#        self._status(msg)
#        # F7-5：結果一到就把 Results 視窗帶出來 —— 使用者按 Run 想看的就是這個
#        self.results.set_summary(
#            summarize_run(len(results), ok, elapsed, self.trial_scores))
#        self.results.set_export_enabled(bool(results))
#        self.results.status(msg)
#        if results:
#            self.results.present()
#
#    # ==================================================================== #
#    # Gallery（M5）
#    # ==================================================================== #
#    def _populate_gallery(self, results: Sequence[Dict[str, Any]]) -> None:
#        """試跑/全跑結果 → Gallery。縮圖一律先給 ``None``，之後背景補上。
#
#        排序欄位 = ``score`` + 這批結果實際出現過的特徵名（沒跑到的特徵不會
#        出現在下拉裡 —— 使用者只看得到「這一批真的有的東西」）。
#        """
#        results = list(results or [])
#        feats: List[str] = []
#        for r in results:
#            for k in (r.get("features") or {}):
#                if k not in feats:
#                    feats.append(str(k))
#        self.gallery.set_sort_keys(["score"] + sorted(feats))
#        self.gallery.set_items([
#            {
#                "defect_id": str(r.get("defect_id", "")),
#                "ok": bool(r.get("ok", True)),
#                "score": r.get("score"),
#                "bin": r.get("bin"),
#                "features": dict(r.get("features") or {}),
#                "thumb": None,
#            }
#            for r in results
#        ])
#        # 新的一批 = 分數分佈變了：舊的分數篩選一定要清掉，不然使用者會看到
#        # 一個對不上新直方圖的區間（而且 chip 還掛在那裡）。
#        self.gallery.clear_filter()
#        self._score_filter = None
#
#    def show_gallery(self) -> None:
#        """把 Results 視窗叫出來（Gallery 與分數分佈都在那裡）。"""
#        self.results.present()
#
#    def show_preview(self) -> None:
#        """回到主視窗的單顆預覽。"""
#        self.raise_()
#        self.activateWindow()
#
#    def results_visible(self) -> bool:
#        """Results 視窗現在開著嗎（測試用）。"""
#        return bool(self.results.isVisible())
#
#    # ---- 縮圖（永遠不在 GUI 執行緒解碼）------------------------------------
#    def _on_thumbs_requested(self, ids: Any) -> None:
#        self.request_thumbs(list(ids or []))
#
#    def request_thumbs(self, ids: Sequence[str], sync: bool = False) -> int:
#        """做這些 defect 的縮圖。``sync=True`` 直接算完（測試 / headless 用）。
#
#        回傳實際排進去（或同步做好）的張數；認不得的 id 靜靜略過。
#        """
#        jobs = [(str(i), self._items_by_id[str(i)])
#                for i in (ids or []) if str(i) in self._items_by_id]
#        if not jobs:
#            return 0
#        size = int(self.gallery.thumb_size())
#        if sync:
#            mapping = ThumbWorker.run_sync(jobs, size)
#            self._on_thumbs_ready(mapping)
#            return len(mapping)
#        self.thumb_worker.request(jobs, size)
#        return len(jobs)
#
#    def _on_thumbs_ready(self, mapping: Any) -> None:
#        """背景做好的縮圖回到 GUI 執行緒 —— 只有這裡碰 Gallery。"""
#        self.gallery.set_thumbs(dict(mapping or {}))
#
#    # ---- Gallery 的互動 ---------------------------------------------------
#    def _on_defect_activated(self, defect_id: str) -> None:
#        """Gallery 雙擊某顆 → 切回單顆預覽並跳過去。"""
#        did = str(defect_id)
#        items = list(getattr(self.dataset, "items", []) or []) if self.dataset else []
#        index = None
#        for i, it in enumerate(items):
#            if str(getattr(it, "defect_id", "")) == did:
#                index = i
#                break
#        self.show_preview()
#        if index is None:
#            self._status("Defect “%s” is not in the current dataset." % did)
#            return
#        self.set_defect_index(index)
#        self._status("Jumped to defect “%s” (%d / %d)"
#                     % (did, index + 1, len(items)))
#
#    def _on_gallery_selection(self, ids: Any) -> None:
#        self._status("%d selected" % len(list(ids or [])))
#
#    # ---- 直方圖點長條 → Gallery 篩選 --------------------------------------
#    def _on_bar_clicked(self, lo: float, hi: float) -> None:
#        """點一根長條：只看那個分數區間；再點同一根就取消。
#
#        「同一根」的判斷要連 Gallery 目前**真的還在篩**一起看 —— 使用者可能
#        已經按掉 Gallery 上的條件 chip 了，那時候再點同一根當然是重新篩選。
#        """
#        rng = (float(lo), float(hi))
#        if self._score_filter == rng and self.gallery.filter_text():
#            self.gallery.clear_filter()
#            self._score_filter = None
#            self._status("Score filter cleared (showing all %d)"
#                         % self.gallery.displayed_count())
#            return
#        self.gallery.filter_by_score_range(rng[0], rng[1])
#        self._score_filter = rng
#        self.show_gallery()
#        self._status("Filtered to score %.3g–%.3g (%d defects)"
#                     % (rng[0], rng[1], self.gallery.displayed_count()))
#
#    # ==================================================================== #
#    # 輸出（M5）
#    # ==================================================================== #
#    def open_export_dialog(self) -> Optional[Any]:
#        """開輸出精靈；沒有結果就只在狀態列提示（不開空對話框）。"""
#        if not self.trial_results:
#            self._status("No results to export yet — run a trial first.", "error")
#            return None
#        dlg = ExportDialog(
#            self.trial_results,
#            doc=getattr(self.dataset, "klarf", None),
#            dataset=self.dataset,
#            recipe=self.model.to_recipe() if self.model.node_order else None,
#            parent=self)
#        dlg.exported.connect(self._on_exported)
#        self.export_dialog = dlg
#        dlg.show()
#        return dlg
#
#    def _on_exported(self, summary: Any) -> None:
#        outputs = list((summary or {}).get("outputs") or [])
#        self._status("Export finished: %s"
#                     % (", ".join(outputs) if outputs else "(no files)"))
#
#    # ==================================================================== #
#    # 首次開啟導覽 + 範例 recipe 庫（M6）
#    # ==================================================================== #
#    def show_welcome(self, force: bool = False) -> Optional[Any]:
#        """開（或重開）首次導覽。
#
#        ``force=False`` 時尊重「不再顯示」（勾過就回 ``None``）；工具列的
#        「說明」一律 ``force=True``。對話框是**非 modal** 的，所以這個方法
#        永遠會馬上回來 —— 測試可以直接拿回傳值來按鈕。
#        """
#        if not force and welcome_disabled():
#            return None
#        dlg = self.welcome_dialog
#        if dlg is None:
#            dlg = WelcomeDialog(self)
#            dlg.demo_requested.connect(self._on_demo_requested)
#            dlg.open_klarf_requested.connect(self._on_open_klarf)
#            dlg.library_requested.connect(self.open_recipe_library)
#            self.welcome_dialog = dlg
#        dlg.show()
#        dlg.raise_()
#        return dlg
#
#    def open_recipe_library(self) -> Optional[Any]:
#        """開範例 recipe 庫；選了哪份就直接載進流程面板。"""
#        dlg = self.library_dialog
#        if dlg is None:
#            dlg = RecipeLibraryDialog(parent=self)
#            dlg.recipe_chosen.connect(self._on_recipe_chosen)
#            self.library_dialog = dlg
#        else:
#            dlg.reload()
#        if dlg.count() == 0:
#            self._status("No templates found (examples/recipes/ is empty).")
#        dlg.show()
#        dlg.raise_()
#        return dlg
#
#    def _on_recipe_chosen(self, path: str) -> None:
#        self.load_recipe_path(str(path))
#
#    def _on_demo_requested(self) -> None:
#        self.run_demo()
#
#    def run_demo(self, out_dir: Optional[Any] = None, n: int = DEMO_DEFECTS,
#                 sync: bool = True) -> bool:
#        """「用範例資料試一次」的完整動作 —— 這顆鈕是整個產品的入口。
#
#        產合成資料 → 載入資料集 → 載入 die-to-die 範本 → 試跑 → 切到
#        Gallery。做完畫面上就是「有分數分佈的直方圖 + 一整牆縮圖」，
#        使用者不必先懂任何東西。
#
#        產資料那一段會拉進 numpy/tifffile 並寫幾百 KB 的檔，在慢一點的機器上
#        會有一兩秒的停頓 —— 所以整段包在**等待游標**裡，畫面不會像當掉。
#        每一步都自我保護：任何一步失敗只在狀態列說明原因並回 ``False``。
#        """
#        self._status("Preparing sample data…")
#        QApplication.setOverrideCursor(Qt.WaitCursor)
#        try:
#            paths = generate_demo_lot(out_dir, n=int(n))
#        except Exception as e:          # noqa: BLE001 — UI 邊界，一律回報
#            self._status("Could not generate sample data: %s: %s" % (type(e).__name__, e), "error")
#            return False
#        finally:
#            QApplication.restoreOverrideCursor()
#
#        if not self.load_dataset_path(paths["klarf"], sync=True):
#            return False
#        if not self.load_template():
#            return False
#
#        QApplication.setOverrideCursor(Qt.WaitCursor)
#        try:
#            ok = self.run_trial(int(n), workers=1, sync=bool(sync))
#        finally:
#            QApplication.restoreOverrideCursor()
#        if not ok:
#            return False
#
#        self.show_gallery()
#        self._status(
#            "Sample run finished — the histogram below is the score "
#            "distribution (drag the threshold line), and the wall of thumbnails "
#            "is on the right. Next, use “Open KLARF…” to switch to your own data.")
#        return True
#
#    # ==================================================================== #
#    # 對話框（測試不走這條路）
#    # ==================================================================== #
#    def _on_open_klarf(self) -> None:
#        path, _ = QFileDialog.getOpenFileName(
#            self, "Open KLARF", "", "KLARF (*.001 *.klarf *.txt);;All files (*)")
#        if not path:
#            return
#        self.load_dataset_path(path)
#
#    def _on_open_recipe(self) -> None:
#        path, _ = QFileDialog.getOpenFileName(
#            self, "Open Recipe", "", "Recipe JSON (*.json);;All files (*)")
#        if not path:
#            return
#        self.load_recipe_path(path)
#
#    def _on_save_recipe(self) -> bool:
#        """回傳「真的存下去了嗎」—— 關窗前的確認要靠這個答案（F7-16）：
#        使用者在存檔對話框按取消，意思是「先別關」，不是「丟掉」。"""
#        path, _ = QFileDialog.getSaveFileName(
#            self, "Save Recipe", self.recipe_path or "recipe.json",
#            "Recipe JSON (*.json);;All files (*)")
#        if not path:
#            return False
#        return bool(self.save_recipe_path(path))
#
#    # ==================================================================== #
#    # 關窗
#    # ==================================================================== #
#    #: 關窗前要不要問「還沒存」。測試整批把它關掉 —— 一個 modal 對話框會讓
#    #: headless 測試永遠停在那裡（而不是失敗），那種卡住最難查。
#    PROMPT_ON_CLOSE = True
#
#    def unsaved_changes(self) -> bool:
#        """有沒有還沒存的編輯（明確狀態，不要去猜）。"""
#        return bool(self.model.dirty)
#
#    def _ask_unsaved(self) -> str:
#        """問使用者要不要存。回 ``"save"`` / ``"discard"`` / ``"cancel"``。
#
#        單獨一個方法是為了測試接得住 —— 測試要驗的是「三個答案各自會怎樣」，
#        不是「QMessageBox 長什麼樣」。
#        """
#        box = QMessageBox(self)
#        box.setIcon(QMessageBox.Warning)
#        box.setWindowTitle("Unsaved changes")
#        box.setText("This recipe has changes you have not saved.")
#        box.setInformativeText(
#            "A recipe is the whole point of the tuning you just did — closing "
#            "now throws it away.")
#        box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard
#                               | QMessageBox.Cancel)
#        box.setDefaultButton(QMessageBox.Save)
#        answer = box.exec()
#        return {QMessageBox.Save: "save",
#                QMessageBox.Discard: "discard"}.get(answer, "cancel")
#
#    def confirm_close(self) -> bool:
#        """可以關了嗎。存檔失敗（或使用者在存檔對話框按取消）**不算可以關**——
#        那是「我改變主意了」，不是「丟掉吧」。"""
#        if not (self.PROMPT_ON_CLOSE and self.unsaved_changes()):
#            return True
#        answer = self._ask_unsaved()
#        if answer == "cancel":
#            return False
#        if answer == "discard":
#            return True
#        return bool(self._on_save_recipe())
#
#    def closeEvent(self, event) -> None:      # noqa: D102 - Qt hook
#        if not self.confirm_close():
#            event.ignore()
#            return
#        self._preview_timer.stop()
#        for dlg in (self.welcome_dialog, self.library_dialog, self.results):
#            try:
#                if dlg is not None:
#                    dlg.close()
#            except Exception:              # noqa: BLE001 — 關窗不准擋路
#                pass
#        for worker in (self.preview_worker, self.trial_worker,
#                       self.dataset_worker, self.thumb_worker):
#            try:
#                worker.stop()
#            except Exception:              # noqa: BLE001 — 關窗不准擋路
#                pass
#        super().closeEvent(event)
#
#F 6db287925d828cf8eb2da25433b61659dbbfdc71 236 adept/ui/template_dialog.py
## ADEPT Studio — 從大圖建 Golden Cell 模板 (F7-12).
#"""``TemplateDialog`` —— 匯入一張大圖 → 量週期 → 疊出模板 → 存進 recipe。
#
#為什麼這一步一定要有畫面
#------------------------
#模板法整條路唯一會**安靜壞掉**的地方是「週期估錯」：估錯了，疊出來的 cell 會
#糊掉，而糊掉的模板會讓後面每一顆都對錯 —— 但畫面上不會有錯誤訊息，
#只會有一批看起來很正常、其實量錯位置的數字。
#
#所以這個對話框把判斷材料**全部攤開**：量到的週期、疊了幾格、疊出來長什麼樣，
#以及一個銳利度分數（``ghosting_score``，repo 裡本來就有）。使用者不需要懂
#那個分數怎麼算 —— 他只要看得到「疊出來的圖是清楚的還是糊的」。
#
#大圖不進 recipe，模板才進
#-------------------------
#按下「Use this template」寫進 recipe 的是**模板本身**（base64 純文字），
#不是大圖的路徑。recipe 要能寄給別人；存路徑的話，圖被搬走、被換掉、下個月有人
#用了另一張大圖，結果會安靜地變。
#"""
#from __future__ import annotations
#
#from typing import Any, Optional
#
#import numpy as np
#from PySide6.QtCore import QRectF, Qt, Signal
#from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
#from PySide6.QtWidgets import (
#    QDialog,
#    QDialogButtonBox,
#    QFileDialog,
#    QHBoxLayout,
#    QLabel,
#    QPushButton,
#    QVBoxLayout,
#    QWidget,
#)
#
#from adept.core.algo import template as algo_template
#from adept.core.ingest.imageio import load_gray
#
#from .theme import TOKENS
#from .widgets import _qimage_from_uint8
#
#__all__ = ["TemplateDialog", "CellView"]
#
##: 模板預覽最長邊放大到幾 px（一個 cell 通常只有幾十 px，原尺寸看不清楚）。
#_PREVIEW = 260
#
#
#class CellView(QWidget):
#    """把一個 cell 放大顯示，並把使用者標的框畫上去。"""
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self._cell: Optional[np.ndarray] = None
#        self._box = (0.0, 0.0, 1.0, 1.0)
#        self.setMinimumSize(_PREVIEW, 140)
#
#    def set_cell(self, cell: Optional[np.ndarray]) -> None:
#        self._cell = None if cell is None else np.asarray(cell)
#        self.update()
#
#    def set_box(self, norm_rect) -> None:
#        self._box = tuple(float(v) for v in norm_rect)
#        self.update()
#
#    def has_cell(self) -> bool:
#        return self._cell is not None and self._cell.size > 0
#
#    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
#        p = QPainter(self)
#        p.fillRect(self.rect(), QColor(TOKENS["image_backdrop"]))
#        if not self.has_cell():
#            p.setPen(QColor(TOKENS["text_disabled"]))
#            p.drawText(self.rect(), Qt.AlignCenter,
#                       "(no template yet - pick a full-size image)")
#            p.end()
#            return
#
#        cell = self._cell
#        h, w = cell.shape[:2]
#        scale = min(self.width() / float(w), self.height() / float(h))
#        dw, dh = w * scale, h * scale
#        ox, oy = (self.width() - dw) / 2.0, (self.height() - dh) / 2.0
#
#        # 放大時關平滑：SEM 的小圖要看得出方格（同 ImageView 的理由）
#        pm = QPixmap.fromImage(_qimage_from_uint8(cell))
#        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
#        p.drawPixmap(QRectF(ox, oy, dw, dh), pm, QRectF(pm.rect()))
#
#        bx, by, bw, bh = self._box
#        p.setPen(QPen(QColor(TOKENS["accent"]), 2.0))
#        p.setBrush(Qt.NoBrush)
#        p.drawRect(QRectF(ox + bx * dw, oy + by * dh,
#                          max(1.0, bw * dw), max(1.0, bh * dh)))
#        p.end()
#
#
#class TemplateDialog(QDialog):
#    """匯入大圖 → 疊模板 → 確認品質 → 寫回卡片。"""
#
#    accepted_template = Signal(str, str)        # (encoded cell, locate_axis)
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setWindowTitle("Build template from a full-size image")
#        self.resize(560, 520)
#        self.cell: Optional[algo_template.GoldenCell] = None
#        self._source_path = ""
#
#        outer = QVBoxLayout(self)
#        outer.setContentsMargins(12, 12, 12, 12)
#        outer.setSpacing(8)
#
#        intro = QLabel(
#            "Pick one full-size image from the same inspection recipe. The "
#            "repeating cell is measured from it and stored inside your recipe, "
#            "so the recipe stays a single file - the image itself is only "
#            "needed here.", self)
#        intro.setObjectName("paramHint")
#        intro.setWordWrap(True)
#        outer.addWidget(intro)
#
#        row = QHBoxLayout()
#        self.btn_pick = QPushButton("Choose image…", self)
#        self.btn_pick.setObjectName("primary")
#        self.btn_pick.clicked.connect(self._on_pick)
#        row.addWidget(self.btn_pick)
#        self.path_label = QLabel("(no image chosen)", self)
#        self.path_label.setObjectName("paramHint")
#        row.addWidget(self.path_label, 1)
#        outer.addLayout(row)
#
#        self.view = CellView(self)
#        outer.addWidget(self.view, 1)
#
#        self.report = QLabel("", self)
#        self.report.setObjectName("paramHint")
#        self.report.setWordWrap(True)
#        outer.addWidget(self.report)
#
#        self.buttons = QDialogButtonBox(
#            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
#        self.buttons.button(QDialogButtonBox.Ok).setText("Use this template")
#        self.buttons.accepted.connect(self._on_accept)
#        self.buttons.rejected.connect(self.reject)
#        outer.addWidget(self.buttons)
#        self._set_ready(False)
#
#    # ---- 對外（測試也走這條，不必真的開檔案對話框）------------------------
#    def load_image(self, image: Any, name: str = "") -> bool:
#        """吃一張大圖，量週期、疊模板、把證據寫上畫面。"""
#        arr = np.asarray(image)
#        if arr.size == 0:
#            self._fail("that image is empty")
#            return False
#
#        gc = algo_template.build_golden_cell(arr)
#        self.cell = gc
#        self._source_path = str(name or "")
#        self.path_label.setText(self._source_path or "(image)")
#
#        if gc.cell.size == 0:
#            self.view.set_cell(None)
#            self._fail("; ".join(gc.warnings) or "no repeating cell was found")
#            return False
#
#        self.view.set_cell(gc.cell)
#        self.view.set_box((0.0, 0.0, 1.0, 1.0))
#        self._set_ready(True)
#        self.report.setText(self.summary())
#        return True
#
#    def summary(self) -> str:
#        """一行摘要 —— 判斷材料全部攤開（測試也讀這個，不必去讀畫素）。"""
#        gc = self.cell
#        if gc is None or gc.cell.size == 0:
#            return ""
#        axis = {(True, False): "across", (False, True): "down",
#                (True, True): "both ways"}[gc.periodic]
#        bits = ["cell %d x %d px" % (gc.px, gc.py),
#                "repeats %s" % axis,
#                "stacked from %d cells" % gc.n_cells,
#                "sharpness %.0f / 100" % gc.ghosting]
#        if gc.ghosting < 40.0:
#            bits.append("- the stack looks blurred, which usually means the "
#                        "period was measured wrong; a blurred template will "
#                        "mis-place the region on every defect")
#        for w in gc.warnings:
#            if "arbitrary" in w:
#                bits.append("- " + w)
#        return " · ".join(bits)
#
#    def locate_axis(self) -> str:
#        gc = self.cell
#        if gc is None:
#            return "x"
#        return {(True, False): "x", (False, True): "y",
#                (True, True): "both"}.get(gc.periodic, "x")
#
#    def encoded(self) -> str:
#        gc = self.cell
#        return "" if gc is None else algo_template.encode_cell(gc.cell)
#
#    def is_ready(self) -> bool:
#        """按得下「Use this template」嗎（用明確狀態，不要問 widget）。"""
#        return bool(self._ready)
#
#    # ---- 內部 -------------------------------------------------------------
#    def _set_ready(self, ready: bool) -> None:
#        self._ready = bool(ready)
#        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self._ready)
#
#    def _fail(self, why: str) -> None:
#        self._set_ready(False)
#        self.report.setText("Could not build a template: %s." % why)
#
#    def _on_pick(self) -> None:            # pragma: no cover — 需要真的開檔案總管
#        path, _f = QFileDialog.getOpenFileName(
#            self, "Choose a full-size image", "",
#            "Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp);;All files (*)")
#        if not path:
#            return
#        try:
#            img = load_gray(path)
#        except Exception as e:             # noqa: BLE001 — UI 邊界
#            self._fail("%s: %s" % (type(e).__name__, e))
#            return
#        self.load_image(img, path)
#
#    def _on_accept(self) -> None:
#        if not self.is_ready():
#            return
#        self.accepted_template.emit(self.encoded(), self.locate_axis())
#        self.accept()
#
#F ba7b7cf461d0e9837937c1a7bb76d81d39ca300f 722 adept/ui/theme.py
## ADEPT Studio theme — authored 2026-07-28 (M3), repainted 2026-07-28 (F7-2).
## Originally vendored from cell-period-estimator/…/ui/theme.py（GLAS 暖色 token
## 系統 + apply_theme QSS）。F7-2 換掉了整組**顏色值**，但 token 的**鍵名一個都沒改**
##   —— QSS 與所有自繪 widget 都是照鍵名取色，所以換膚不需要動任何呼叫端。
#"""ADEPT Studio 佈景主題 —— 設計 token 的唯一真相來源。
#
#``TOKENS`` 同時餵給 QSS（標準 widget）與自繪 widget（直方圖、節點卡、色條），
#顏色永遠不會兩邊走鐘。
#
#F7-2：為什麼整組換掉
#--------------------
#舊配色是暖奶油底（``#f7f4ef``）+ 琥珀 accent（``#f29f4b``），而且三段式用
#**填滿的彩色底塊**當區塊標題。暖色 + 高飽和 + 大色塊三個加起來，使用者的
#評語是「太像玩具」。
#
#新的目標是 n8n / KLIP 的語言：
#
#* **中性灰階** —— 大面積不帶色相，眼睛不會被背景搶走
#* **全平面** —— 沒有陰影、沒有漸層（n8n 2.0 也是刻意拿掉 3D 陰影的）
#* **顏色只表達語意** —— 段落色、狀態色、accent；裝飾一律不用色
#* **小圓角、細邊框、一致的 4/8px 間距**
#
#亮色與暗色
#----------
#``PALETTES`` 有 ``"light"`` / ``"dark"`` 兩組，鍵名完全相同。
#:func:`set_theme` 就地更新 ``TOKENS``（**不是換掉物件**）——
#因為各模組都是 ``from .theme import TOKENS`` 之後在建構式裡取值，
#就地更新才能讓已經 import 過的模組跟著變。
#
#三段式 segment 色（master plan §5）：
#
#===========  ==========  ==========  ==========================================
#段           前景 token  底色 token  用在哪
#===========  ==========  ==========  ==========================================
#影像 image   seg_image   seg_image_bg  Library 區塊圓點、Pipeline 卡片左側色條
#算法 algo    seg_algo    seg_algo_bg   同上 + 直方圖長條
#ADC  adc     seg_adc     seg_adc_bg    同上 + Score/Bin 尾卡
#===========  ==========  ==========  ==========================================
#
#Qt-QSS 限制備忘：QSS 沒有 ``text-transform`` / ``letter-spacing``；區塊標題
#一律在程式碼裡處理大小寫，顏色與字重才交給 QSS。
#
#本模組不在 import 時碰 Qt（``TOKENS`` 可被 headless 測試直接讀），
#``QColor`` 一律在函式內 lazy import。
#"""
#
#from __future__ import annotations
#
#from string import Template
#from typing import Any, Dict
#
#__all__ = [
#    "TOKENS", "PALETTES", "THEMES", "DEFAULT_THEME", "current_theme",
#    "set_theme", "SEG_LABELS", "seg_hex", "seg_color", "seg_bg",
#    "group_hex", "group_color", "build_stylesheet", "apply_theme",
#]
#
## --------------------------------------------------------------------------- #
## Design tokens
## --------------------------------------------------------------------------- #
##: 亮色（預設）。中性灰階 + 一個克制的藍當 accent。
#_LIGHT: Dict[str, Any] = {
#    # -- backgrounds (low -> high elevation) -------------------------------
#    "bg_page": "#f4f5f7",
#    "bg_panel": "#fafbfc",
#    "bg_surface": "#ffffff",
#    "bg_elevated": "#f7f8fa",
#    "bg_input": "#ffffff",
#    "side_panel": "#fafbfc",
#    "toolbar": "#ffffff",
#    "statusbar": "#f7f8fa",
#    # -- borders ------------------------------------------------------------
#    "border_default": "#e3e6eb",
#    "border_input": "#cbd1d9",
#    "border_hover": "#9aa3ae",
#    "border_focus": "#3574d6",
#    # -- text ---------------------------------------------------------------
#    "text_primary": "#1f2430",
#    "text_secondary": "#5b6472",
#    "text_hint": "#79828f",
#    "text_disabled": "#aeb5bf",
#    # -- accent (restrained blue; KLIP 的視覺語言) ---------------------------
#    "accent": "#3574d6",
#    "accent_hover": "#4a86e2",
#    "accent_active": "#2b5eb0",
#    "accent_bg": "#eaf1fc",
#    "accent_border": "#c2d6f2",
#    # -- selection / hover --------------------------------------------------
#    "selection": "#d5e3f8",
#    "hover_warm": "#f0f2f5",          # 鍵名保留（歷史），已不是暖色
#    "hover_warm_strong": "#e6eaf0",
#    "focus_bg": "#ffffff",
#    # -- semantic -----------------------------------------------------------
#    "success": "#3f9d6b",
#    "success_bg": "#eaf6f0",
#    "success_border": "#b6ddc7",
#    "success_text": "#2f7a52",
#    "danger": "#d05a4c",
#    "danger_bg": "#fdeeeb",
#    "danger_border": "#f0bdb5",
#    "danger_text": "#a83f33",
#    "warning": "#c2871f",
#    "min_accent": "#c2731f",
#    "min_accent_bg": "#fdf3e6",
#    "min_accent_border": "#eed3ad",
#    "min_accent_text": "#8f5615",
#    "max_accent": "#3574d6",
#    "max_accent_bg": "#eaf1fc",
#    "max_accent_border": "#c2d6f2",
#    "max_accent_text": "#2b5eb0",
#    # -- ADEPT 三段式 segment 色（去飽和，只當色條/圓點用）-------------------
#    "seg_image": "#4a7ba7",
#    "seg_algo": "#b0722f",
#    "seg_adc": "#7a68a6",
#    "seg_image_bg": "#eaf0f6",
#    "seg_algo_bg": "#f8f0e5",
#    "seg_adc_bg": "#f0edf6",
#    # -- 流程階段色（F7-9）：六個階段各一個色相（見 group_hex 的說明）--------
#    "stage_input": "#2f8f80",
#    "stage_enhance": "#3f7fbf",
#    "stage_region": "#5f8f3f",
#    "stage_compare": "#b0507f",
#    "stage_measure": "#bf7030",
#    "stage_adc": "#8a5fbf",
#    "seg_disabled": "#c2c7ce",
#    "seg_disabled_bg": "#f0f1f3",
#    # -- 判定 chip（good / bad / neutral）------------------------------------
#    "chip_good_bg": "#eaf6f0",
#    "chip_good_text": "#2f7a52",
#    "chip_good_border": "#b6ddc7",
#    "chip_bad_bg": "#fdeeeb",
#    "chip_bad_text": "#a83f33",
#    "chip_bad_border": "#f0bdb5",
#    "chip_neutral_bg": "#f0f2f5",
#    "chip_neutral_text": "#5b6472",
#    "chip_neutral_border": "#e3e6eb",
#    # -- tooltip (inverted) -------------------------------------------------
#    "tooltip_bg": "#2b303b",
#    "tooltip_text": "#f4f5f7",
#    "tooltip_border": "#1f2430",
#    # -- lists / scrollbars / disabled --------------------------------------
#    "list_bg": "#ffffff",
#    "row_alt": "#fafbfc",
#    "scroll_track": "transparent",
#    "scroll_thumb": "#cbd1d9",
#    "scroll_thumb_hover": "#aeb5bf",
#    "disabled_bg": "#f4f5f7",
#    "disabled_text": "#aeb5bf",
#    "tab_inactive": "transparent",
#    # -- section header tiers ------------------------------------------------
#    "tier1_bg": "transparent",
#    "tier1_text": "#79828f",
#    # -- 影像背景（F7-7）------------------------------------------------------
#    #: **light / dark 兩組刻意填同一個值。**
#    #:
#    #: 這個工具的核心工作是判斷 8-bit 灰階 patch 上的細微差異，而周圍的亮度
#    #: 會偏移人對灰階的感知（同時對比效應）。原本影像底用的是 ``bg_panel``
#    #: （淡色主題下近乎純白），那是最糟的組合：patch 會顯得比實際暗、
#    #: 感知對比被壓縮。影像評估的慣例是中性灰（Photoshop/Lightroom 的深灰、
#    #: 醫療影像 viewer 的黑底），理由就是不要讓背景去偏移判斷。
#    #:
#    #: 所以：**chrome 跟著主題走，影像區不跟。** 換主題時同一張 patch
#    #: 看起來要一樣。
#    "image_backdrop": "#3f4247",
#
#    # -- canvas (F7-6 節點畫布) ----------------------------------------------
#    "canvas_bg": "#f0f1f4",
#    #: F7-8：背景從格線改成點陣之後這個值調深了一階。線鋪滿整片，太深會吵；
#    #: 點只有交會處那一顆，用原本的淺色就直接看不見了。
#    "canvas_grid": "#ced4de",
#    "canvas_edge": "#9aa3ae",
#    "canvas_edge_active": "#3574d6",
#    #: 隱含順序的虛線（F7-18）。以前它是 ``canvas_edge`` 加透明度 —— 同一個
#    #: 顏色淡一點，於是「這條線是我拉的」跟「這條線是排列順序帶來的」看起來
#    #: 只差在深淺，而深淺在畫布上還會被縮放與背景影響。兩者在語意上是兩種
#    #: 東西（一條刪得掉、一條刪不掉），所以給它自己的色相。
#    "canvas_edge_implicit": "#b08a5a",
#    # -- typography ----------------------------------------------------------
#    "font_stack": ("'Segoe UI','PingFang TC','Microsoft JhengHei',"
#                   "'Helvetica Neue',Arial,sans-serif"),
#    "mono_stack": "'Consolas','Courier New',monospace",
#}
#
##: 暗色。n8n 的畫布是深中性色，不是純黑（純黑對比太硬，看久了刺眼）。
#_DARK: Dict[str, Any] = dict(_LIGHT, **{
#    "bg_page": "#191b20",
#    "bg_panel": "#1e2127",
#    "bg_surface": "#23262d",
#    "bg_elevated": "#2a2e36",
#    "bg_input": "#1b1e24",
#    "side_panel": "#1e2127",
#    "toolbar": "#1e2127",
#    "statusbar": "#1b1e24",
#
#    "border_default": "#333842",
#    "border_input": "#3d434f",
#    "border_hover": "#5c6474",
#    "border_focus": "#4b8bf5",
#
#    "text_primary": "#e3e6ec",
#    "text_secondary": "#a3abb8",
#    "text_hint": "#8b93a1",
#    "text_disabled": "#5c6474",
#
#    "accent": "#4b8bf5",
#    "accent_hover": "#639cf8",
#    "accent_active": "#3a76d8",
#    "accent_bg": "#1d2a3f",
#    "accent_border": "#33507d",
#    "selection": "#2b3d5c",
#    "hover_warm": "#282c34",
#    "hover_warm_strong": "#30353f",
#    "focus_bg": "#1b1e24",
#
#    "success": "#54b382",
#    "success_bg": "#1b2b23",
#    "success_border": "#2f5a45",
#    "success_text": "#6ec79a",
#    "danger": "#e07568",
#    "danger_bg": "#2e1e1c",
#    "danger_border": "#5c3630",
#    "danger_text": "#f0958a",
#    "warning": "#d8a145",
#    "min_accent": "#d8934a",
#    "min_accent_bg": "#2b2219",
#    "min_accent_border": "#5a4630",
#    "min_accent_text": "#e0a86a",
#    "max_accent": "#4b8bf5",
#    "max_accent_bg": "#1d2a3f",
#    "max_accent_border": "#33507d",
#    "max_accent_text": "#7aaaf8",
#
#    "seg_image": "#6f9fc8",
#    "seg_algo": "#d1994f",
#    "seg_adc": "#9e8bc8",
#    "seg_image_bg": "#1e2833",
#    "seg_algo_bg": "#2c2519",
#    "seg_adc_bg": "#26222f",
#    # -- 流程階段色（F7-9）---------------------------------------------------
#    "stage_input": "#5cbfae",
#    "stage_enhance": "#6fa6e0",
#    "stage_region": "#93c46a",
#    "stage_compare": "#dd7fac",
#    "stage_measure": "#e0a05c",
#    "stage_adc": "#b48fe0",
#    "seg_disabled": "#4a505c",
#    "seg_disabled_bg": "#22252b",
#
#    "chip_good_bg": "#1b2b23",
#    "chip_good_text": "#6ec79a",
#    "chip_good_border": "#2f5a45",
#    "chip_bad_bg": "#2e1e1c",
#    "chip_bad_text": "#f0958a",
#    "chip_bad_border": "#5c3630",
#    "chip_neutral_bg": "#282c34",
#    "chip_neutral_text": "#a3abb8",
#    "chip_neutral_border": "#333842",
#
#    "tooltip_bg": "#f4f5f7",
#    "tooltip_text": "#1f2430",
#    "tooltip_border": "#cbd1d9",
#
#    "list_bg": "#1b1e24",
#    "row_alt": "#1f2229",
#    "scroll_track": "transparent",
#    "scroll_thumb": "#3d434f",
#    "scroll_thumb_hover": "#5c6474",
#    "disabled_bg": "#22252b",
#    "disabled_text": "#5c6474",
#    "tab_inactive": "transparent",
#
#    "tier1_bg": "transparent",
#    "tier1_text": "#8b93a1",
#
#    "image_backdrop": "#3f4247",     # 與 light 相同 —— 見上面的說明
#    "canvas_bg": "#16181d",
#    "canvas_grid": "#2f3540",
#    "canvas_edge": "#5c6474",
#    "canvas_edge_active": "#4b8bf5",
#    "canvas_edge_implicit": "#a2794a",
#})
#
##: 兩組色盤，鍵名完全一致（測試會逐鍵比對）。
#PALETTES: Dict[str, Dict[str, Any]] = {"light": _LIGHT, "dark": _DARK}
#THEMES = tuple(PALETTES)
#DEFAULT_THEME = "light"
#
##: **活的** token 字典。``set_theme`` 就地更新它（見模組 docstring）。
#TOKENS: Dict[str, Any] = dict(_LIGHT)
#
#_CURRENT = {"name": DEFAULT_THEME}
#
#
#def current_theme() -> str:
#    """目前套用的主題名稱。"""
#    return _CURRENT["name"]
#
#
#def set_theme(name: str) -> str:
#    """切換色盤（**就地**更新 ``TOKENS``），回傳實際套用的名稱。
#
#    不認得的名字退回 :data:`DEFAULT_THEME`，不丟例外 —— 主題壞掉不該讓
#    使用者連視窗都開不起來（鐵則 7 的精神）。
#    """
#    key = str(name or "").strip().lower()
#    if key not in PALETTES:
#        key = DEFAULT_THEME
#    TOKENS.clear()
#    TOKENS.update(PALETTES[key])
#    _CURRENT["name"] = key
#    return key
#
#
## 分類 -> (前景 token, 底色 token)。未知分類退回中性色。
#_SEG_TOKENS = {
#    "image": ("seg_image", "seg_image_bg"),
#    "algo": ("seg_algo", "seg_algo_bg"),
#    "adc": ("seg_adc", "seg_adc_bg"),
#}
#
#SEG_LABELS = {
#    "image": "Image",
#    "algo": "Algorithm",
#    "adc": "ADC Decision",
#}
#
#
#def seg_hex(category: str, bg: bool = False) -> str:
#    """回傳 segment 顏色的 hex 字串（``bg=True`` 取柔和底色）。純字串、免 Qt。"""
#    fg_key, bg_key = _SEG_TOKENS.get(str(category), ("text_secondary", "bg_panel"))
#    return TOKENS[bg_key if bg else fg_key]
#
#
## 流程階段 -> 色彩 token（F7-9）。順序同 ``pipeline/step.py`` 的 ``GROUP_ORDER``。
#_STAGE_TOKENS = {
#    "input": "stage_input",
#    "enhance": "stage_enhance",
#    "region": "stage_region",
#    "compare": "stage_compare",
#    "measure": "stage_measure",
#    "adc": "stage_adc",
#}
#
#
#def group_hex(group: str) -> str:
#    """流程階段 -> 顏色 hex。純字串、免 Qt。
#
#    為什麼階段色不再從 ``seg_hex`` 借（F7-9）
#    ----------------------------------------
#    F7-3 之前這裡是 ``group -> category -> 顏色``，於是六個階段只有三種色：
#    Input／Enhance／Compare 全是藍的。試用回饋原話是「圖示很不錯，但太多都同
#    個顏色」—— 圖示分得出來、顏色分不出來，等於顏色這個維度白給了。
#
#    現在每個階段各有一個色相，但**冷暖仍然對得上三段式**：
#    影像段（Input 藍綠／Enhance 藍／Compare 靛）走冷色、
#    算法段（Region 綠／Measure 橙）與 ADC（紫）維持原本的識別。
#    相鄰的兩階段永遠不同色系，所以在直式 rail 上由上而下掃過去分得開。
#
#    ``seg_hex`` 沒有被取代 —— 需要講「這是哪一段」的地方（首啟導覽的三段說明、
#    直方圖、Score/Bin 尾卡）仍然用它。兩個軸各有各的用途，見 CLAUDE.md §2。
#    """
#    return TOKENS[_STAGE_TOKENS.get(str(group), "stage_enhance")]
#
#
#def group_color(group: str):
#    """:func:`group_hex` 的 ``QColor`` 版。"""
#    from PySide6.QtGui import QColor
#
#    return QColor(group_hex(group))
#
#
#def seg_color(category: str, bg: bool = False):
#    """``"image"``/``"algo"``/``"adc"`` -> ``QColor``（``bg=True`` 取柔和底色）。"""
#    from PySide6.QtGui import QColor
#
#    return QColor(seg_hex(category, bg=bg))
#
#
#def seg_bg(category: str):
#    """``seg_color(category, bg=True)`` 的別名（可讀性糖）。"""
#    return seg_color(category, bg=True)
#
#
## --------------------------------------------------------------------------- #
## QSS
## --------------------------------------------------------------------------- #
#_QSS = Template(r"""
#* {
#    font-family: $font_stack;
#    font-size: 13px;
#    color: $text_primary;
#}
#
#QMainWindow, QWidget, QDialog { background: $bg_page; color: $text_primary; }
#
#/* -- toolbar ---------------------------------------------------------- */
#QToolBar {
#    background: $toolbar;
#    border: 0;
#    border-bottom: 1px solid $border_default;
#    spacing: 6px;
#    padding: 4px 6px;
#}
#/* Toolbar buttons look like buttons, not like a menu bar. Borderless text in
# * a row reads as “File Edit View…”, and a menu bar is something you pull down,
# * not something you press — so the whole strip stopped looking clickable. */
#QToolBar QToolButton {
#    background: $bg_surface;
#    color: $text_primary;
#    border: 1px solid $border_input;
#    border-radius: 6px;
#    padding: 6px 12px;
#    font-weight: 500;
#}
#QToolBar QToolButton:hover { background: $hover_warm; color: $text_primary;
#                             border-color: $border_hover; }
#QToolBar QToolButton:pressed { background: $hover_warm_strong; }
#QToolBar QToolButton:checked {
#    background: $accent_bg; color: $accent_active; border: 1px solid $accent_border;
#}
#QToolBar QToolButton#primary {
#    background: $accent; color: #ffffff; border: 1px solid $accent;
#    padding: 6px 16px; font-weight: 600;
#}
#QToolBar QToolButton#primary:hover { background: $accent_hover; }
#QToolBar QToolButton#primary:pressed { background: $accent_active; }
#QToolBar QToolButton#primary:disabled {
#    background: $disabled_bg; color: $disabled_text; border: 1px solid $border_default;
#}
#QToolBar::separator { background: $border_default; width: 1px; margin: 5px 6px; }
#
#/* -- status bar ------------------------------------------------------- */
#QStatusBar { background: $statusbar; color: $text_secondary;
#             border-top: 1px solid $border_default; }
#/* A refusal must not look like a confirmation (F7-15). The status bar is the
# * only place that says a trial was blocked by lint, or a card could not be
# * added - in the same grey as "Added denoise", that reads as nothing said. */
#QStatusBar[level="error"] { color: $danger_text; font-weight: 600; }
#QStatusBar::item { border: 0; }
#
#/* -- group boxes (section cards) -------------------------------------- */
#QGroupBox {
#    background: $bg_surface;
#    border: 1px solid $border_default;
#    border-radius: 6px;
#    margin-top: 16px;
#    padding: 12px 10px 10px 10px;
#}
#QGroupBox::title {
#    subcontrol-origin: margin;
#    subcontrol-position: top left;
#    left: 2px;
#    top: 1px;
#    padding: 0px 4px;
#    background: transparent;
#    border: 0;
#    color: $tier1_text;
#    font-size: 11px;
#    font-weight: 700;
#}
#
#/* -- push buttons ------------------------------------------------------ */
#QPushButton {
#    background: $bg_input;
#    color: $text_primary;
#    border: 1px solid $border_input;
#    border-radius: 6px;
#    padding: 5px 12px;
#    min-height: 18px;
#    font-weight: 500;
#}
#QPushButton:hover { border-color: $border_hover; background: $hover_warm; }
#QPushButton:pressed { background: $hover_warm_strong; }
#QPushButton:focus { border: 1px solid $border_focus; }
#QPushButton:disabled { background: $disabled_bg; color: $disabled_text;
#                       border-color: $border_default; }
#/* primary action (Run trial / Run all): objectName = "primary" */
#QPushButton#primary {
#    background: $accent; color: #ffffff; border: 1px solid $accent;
#    padding: 6px 18px; font-weight: 600;
#}
#QPushButton#primary:hover { background: $accent_hover; }
#QPushButton#primary:pressed { background: $accent_active; }
#QPushButton#primary:disabled {
#    background: $disabled_bg; color: $disabled_text; border: 1px solid $border_default;
#}
#QPushButton[variant="secondary"] {
#    background: $bg_input; color: $accent_active; border: 1px solid $accent;
#    font-weight: 600;
#}
#QPushButton[variant="secondary"]:hover { background: $accent_bg; }
#QPushButton[variant="secondary"]:pressed { background: $accent_bg;
#                                           border: 1px solid $accent_active; }
#QPushButton[variant="secondary"]:disabled {
#    background: $disabled_bg; color: $disabled_text; border: 1px solid $border_default;
#}
#QPushButton[variant="ghost"] {
#    background: transparent; color: $text_secondary; border: 1px solid transparent;
#}
#QPushButton[variant="ghost"]:hover { background: $hover_warm; color: $text_primary; }
#QPushButton[variant="danger"] {
#    background: $danger_bg; color: $danger_text; border: 1px solid $danger_border;
#    font-weight: 600;
#}
#QPushButton[variant="danger"]:hover { border-color: $danger_text; }
#/* Stop stays visible after it is pressed, disabled, so that "I already asked
# * it to stop" is on screen while the current defects finish. */
#QPushButton[variant="danger"]:disabled {
#    background: $disabled_bg; color: $disabled_text; border-color: $border_default;
#}
#/* small square buttons on cards (up / down / remove / add) */
#QPushButton#cardButton {
#    background: transparent; color: $text_secondary;
#    border: 1px solid transparent; border-radius: 5px;
#    padding: 0px; font-weight: 700; min-height: 20px;
#}
#QPushButton#cardButton:hover { background: $hover_warm_strong; color: $accent_active;
#                               border: 1px solid $accent_border; }
#QPushButton#cardButton:disabled { color: $disabled_text; background: transparent; }
#/* The card / features switch under the image: the selected one has to look
# * selected, or the pair reads as two labels rather than a choice (F7-17). */
#QPushButton#cardButton:checked {
#    background: $accent_bg; color: $accent_active;
#    border: 1px solid $accent_border; font-weight: 600;
#}
#
#/* -- inputs ------------------------------------------------------------ */
#QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
#    background: $bg_input;
#    color: $text_primary;
#    border: 1px solid $border_input;
#    border-radius: 5px;
#    padding: 2px 6px;
#    min-height: 22px;
#    selection-background-color: $selection;
#    selection-color: $text_primary;
#}
#QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {
#    border-color: $border_hover;
#}
#QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
#    border: 1px solid $border_focus; background: $focus_bg;
#}
#QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
#    background: $disabled_bg; color: $disabled_text; border-color: $border_default;
#}
#/* A dropdown must not be pixel-identical to a free-text field.
# *
# * `border: 0` here used to hide the arrow completely: styling this subcontrol
# * hands it to the stylesheet, and a styled drop-down draws no arrow unless the
# * rule also supplies a `down-arrow` image — which this repo cannot ship,
# * because it is text-only (see CLAUDE.md §9.5). Leaving the border unset keeps
# * the subcontrol on the base style, which paints the arrow itself.
# *
# * The visible consequence was that "Match on" (three fixed streams) and "Name
# * this region" (free text) looked exactly the same, so there was no way to
# * tell which fields could be opened and which had to be typed.
# * tests/test_ui_controls_readable.py locks this. */
#QComboBox::drop-down { width: 20px; subcontrol-origin: padding;
#                       subcontrol-position: center right; }
#QComboBox QAbstractItemView {
#    background: $bg_input; border: 1px solid $border_default;
#    selection-background-color: $selection; selection-color: $text_primary;
#    outline: 0;
#}
#QSpinBox::up-button, QSpinBox::down-button,
#QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
#    width: 16px; background: $bg_elevated; border-left: 1px solid $border_default;
#}
#
#/* -- sliders (F7-8) ----------------------------------------------------- *
# * One per bounded parameter. The handle is deliberately larger than Qt's
# * default: the whole point is dragging it while watching the image, and a
# * handle you keep missing is the same as no slider at all.                */
#QSlider { background: transparent; min-height: 22px; }
#QSlider::groove:horizontal {
#    height: 4px; border-radius: 2px;
#    background: $border_default;
#}
#QSlider::sub-page:horizontal {
#    height: 4px; border-radius: 2px; background: $accent;
#}
#QSlider::handle:horizontal {
#    width: 12px; height: 12px; margin: -5px 0; border-radius: 6px;
#    background: $bg_elevated; border: 2px solid $accent;
#}
#QSlider::handle:horizontal:hover { border-color: $accent_active; }
#QSlider::handle:horizontal:pressed { background: $accent; }
#QSlider:disabled::sub-page:horizontal { background: $border_default; }
#QSlider:disabled::handle:horizontal { border-color: $border_default; }
#
#/* -- check boxes ------------------------------------------------------- */
#QCheckBox { background: transparent; spacing: 6px; }
#QCheckBox::indicator {
#    width: 14px; height: 14px;
#    border: 1px solid $border_input; border-radius: 3px; background: $bg_input;
#}
#QCheckBox::indicator:hover { border-color: $border_hover; }
#QCheckBox::indicator:checked { background: $accent; border-color: $accent_active; }
#QCheckBox::indicator:disabled { background: $disabled_bg; border-color: $border_default; }
#QCheckBox:disabled { color: $disabled_text; }
#
#/* -- labels ------------------------------------------------------------ */
#QLabel { background: transparent; color: $text_primary; }
#QLabel:disabled { color: $text_disabled; }
#
#/* -- views / lists / tables -------------------------------------------- */
#QAbstractItemView {
#    background: $list_bg; alternate-background-color: $row_alt;
#    border: 1px solid $border_default; border-radius: 6px;
#    selection-background-color: $selection; selection-color: $text_primary;
#    outline: 0;
#}
#QListView::item, QTreeView::item { padding: 3px 4px; border-radius: 4px; }
#QListView::item:hover, QTreeView::item:hover { background: $hover_warm; }
#QTableView { gridline-color: $border_default; }
#QTableView::item { padding: 2px 6px; }
#QHeaderView { background: $list_bg; }
#QHeaderView::section {
#    background: $bg_elevated; color: $text_secondary; border: 0;
#    border-bottom: 1px solid $border_default; padding: 5px 8px; font-weight: 600;
#}
#
#/* -- scroll area ------------------------------------------------------- */
#QScrollArea { border: 0; background: transparent; }
#QScrollArea > QWidget > QWidget { background: transparent; }
#
#/* -- splitter ---------------------------------------------------------- */
#QSplitter { background: $bg_page; }
#QSplitter::handle { background: $border_default; }
#QSplitter::handle:hover { background: $border_hover; }
#QSplitter::handle:horizontal { width: 1px; }
#QSplitter::handle:vertical { height: 1px; }
#
#/* -- scrollbars -------------------------------------------------------- */
#QScrollBar:vertical { background: $scroll_track; width: 11px; margin: 0; border: 0; }
#QScrollBar::handle:vertical { background: $scroll_thumb; border-radius: 5px;
#                              min-height: 24px; }
#QScrollBar::handle:vertical:hover { background: $scroll_thumb_hover; }
#QScrollBar:horizontal { background: $scroll_track; height: 11px; margin: 0; border: 0; }
#QScrollBar::handle:horizontal { background: $scroll_thumb; border-radius: 5px;
#                                min-width: 24px; }
#QScrollBar::handle:horizontal:hover { background: $scroll_thumb_hover; }
#QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
#QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
#
#/* -- progress bar ------------------------------------------------------ */
#QProgressBar {
#    background: $bg_elevated; border: 1px solid $border_default;
#    border-radius: 5px; text-align: center; min-height: 14px; color: $text_secondary;
#}
#QProgressBar::chunk { background: $accent; border-radius: 5px; }
#
#/* -- tabs -------------------------------------------------------------- */
#QTabWidget::pane { border: 1px solid $border_default; border-radius: 6px;
#                   background: $bg_surface; }
#QTabBar::tab { background: $tab_inactive; color: $text_secondary;
#               padding: 5px 14px; margin-right: 2px;
#               border-top-left-radius: 6px; border-top-right-radius: 6px; }
#QTabBar::tab:selected { background: $bg_surface; color: $accent_active;
#                        font-weight: 700; }
#
#/* -- menus / tooltips -------------------------------------------------- */
#QMenu { background: $bg_surface; border: 1px solid $border_default; padding: 4px; }
#QMenu::item { padding: 4px 18px; border-radius: 4px; }
#QMenu::item:selected { background: $selection; color: $text_primary; }
#QToolTip {
#    background: $tooltip_bg; color: $tooltip_text; border: 1px solid $tooltip_border;
#    padding: 4px 6px;
#}
#
#/* -- Studio-specific object names -------------------------------------- */
#QLabel#paramTitle { color: $text_primary; font-size: 14px; font-weight: 700; }
#QLabel#paramStepHelp { color: $text_secondary; font-size: 11px; }
#QLabel#paramLabel { color: $text_primary; font-weight: 600; }
#QLabel#paramHint { color: $text_hint; font-size: 11px; }
#QLabel#paramHint[error="true"] { color: $danger_text; font-size: 11px; font-weight: 600; }
#QLabel#placeholder { color: $text_disabled; font-size: 12px; }
#QLabel#libEmpty { color: $text_disabled; font-size: 11px; }
#QLabel#nodeLabel { color: $text_primary; font-weight: 700; }
#QLabel#nodeSummary { color: $text_secondary; font-size: 11px; }
#QLabel#scoreSummary { color: $text_secondary; font-size: 11px; }
#""")
#
#
#def build_stylesheet() -> str:
#    """回傳完整 QSS（token 已代入）。"""
#    return _QSS.substitute(TOKENS)
#
#
#def apply_theme(app, theme: str = None) -> str:
#    """把主題（palette + stylesheet）套到 QApplication 上，回傳套用的主題名。
#
#    ``theme=None`` 沿用目前的（預設 light）。傳 ``"dark"`` 就整個介面轉暗 ——
#    因為所有顏色都走 ``TOKENS``，換膚不需要動任何 widget。
#    """
#    from PySide6.QtGui import QColor, QFont, QPalette
#
#    name = set_theme(theme if theme is not None else current_theme())
#    app.setStyle("Fusion")  # 跨平台一致的 QSS 底座
#
#    pal = app.palette()
#    pal.setColor(QPalette.Window, QColor(TOKENS["bg_page"]))
#    pal.setColor(QPalette.Base, QColor(TOKENS["bg_input"]))
#    pal.setColor(QPalette.AlternateBase, QColor(TOKENS["row_alt"]))
#    pal.setColor(QPalette.Text, QColor(TOKENS["text_primary"]))
#    pal.setColor(QPalette.WindowText, QColor(TOKENS["text_primary"]))
#    pal.setColor(QPalette.ButtonText, QColor(TOKENS["text_primary"]))
#    pal.setColor(QPalette.Button, QColor(TOKENS["bg_input"]))
#    pal.setColor(QPalette.Highlight, QColor(TOKENS["selection"]))
#    pal.setColor(QPalette.HighlightedText, QColor(TOKENS["text_primary"]))
#    pal.setColor(QPalette.ToolTipBase, QColor(TOKENS["tooltip_bg"]))
#    pal.setColor(QPalette.ToolTipText, QColor(TOKENS["tooltip_text"]))
#    app.setPalette(pal)
#
#    font = QFont()
#    font.setPointSize(10)
#    app.setFont(font)
#
#    app.setStyleSheet(build_stylesheet())
#    return name
#
#F fd02f73c653fd7aae2756928256e6631a03951bb 418 adept/ui/viewmodel.py
## ADEPT Studio view-model — authored 2026-07-28 (M3). Qt-free（可 headless 測試）.
#"""Studio 的編輯狀態模型：UI 元件只做顯示與轉發，所有 recipe 編輯邏輯集中在這裡。
#
#- ``RecipeModel``：包住一條 route 的可變編輯模型（v1 Studio 一次編一條 route）。
#  add/remove/move/set_param 全部走 ParamSpec 驗證；`to_recipe()` 產出可存檔/可跑的
#  Recipe。任何變更會呼叫 listeners（UI 拿來刷新）。
#- 直方圖/門檻工具函數：`histogram()`、`rebin()` —— 拖門檻線秒回的純計算部分。
#"""
#from __future__ import annotations
#
#import math
#from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
#
#from adept.core.pipeline import (
#    ParamError, Recipe, RecipeNode, ScoreSpec, get_step, validate,
#)
#
#
#class RecipeModel:
#    """單一 route 的 recipe 編輯模型（預設 kind="ebi_patch"）。"""
#
#    def __init__(self, kind: str = "ebi_patch") -> None:
#        self.kind = kind
#        self.recipe_id = "untitled"
#        self.author = ""
#        self.description = ""
#        self.version = 1
#        self.node_order: List[str] = []            # route 順序（= 拓撲順序）
#        self.nodes: Dict[str, RecipeNode] = {}
#        #: 顯式的節點連線（F7-6 畫布）。``node_order`` 仍然是執行順序，
#        #: 但有 edges 時它由拓撲排序算出來，不再是「使用者加卡片的順序」。
#        #: 引擎那邊 ``execution_order`` 本來就是「route 相鄰對 ∪ edges」，
#        #: 所以把 route 寫成拓撲順序與 edges 併存，語意一致且向後相容。
#        self.edges: List[Tuple[str, str]] = []
#        self.expr = "0"
#        self.threshold = 0.0
#        self.bins = {"below": 0, "above": 1}
#        self.dirty = False
#        self._listeners: List[Callable[[], None]] = []
#        #: 復原堆疊（F7-16）。整個編輯狀態的快照，不是「反向操作」——
#        #: recipe 小（幾十個節點、純 JSON 值），存整份既簡單又不會漏掉
#        #: 副作用（``add_edge`` 會重排 ``node_order``、``set_param`` 會連帶
#        #: 補上相依預設值），而反向操作要為每一種變動各寫一次「怎麼倒回去」，
#        #: 每加一個新動作就多一個會忘記的地方。
#        self._undo: List[Dict[str, Any]] = []
#        self._redo: List[Dict[str, Any]] = []
#        #: 「同一個參數連續調整算一次」的鍵（滑桿拖一下會發幾十次 set_param）。
#        self._coalesce: Optional[str] = None
#
#    #: 復原最多記幾步。這是記憶體的保險，不是體驗上的取捨 ——
#    #: 沒有人會連按 60 次 Ctrl+Z，但一個沒有上限的堆疊在長 session 裡會一直長。
#    UNDO_DEPTH = 60
#
#    #: 新 recipe 的起手卡。每一條 pipeline 都得先有影像才有得做，所以空白畫布
#    #: 上第一件事一定是「加 Input」—— 那不是一個選擇，是一個儀式。
#    #: 試用回饋（F7-9）原話：「一開始預設畫布上就應該有 load image 這個節點」。
#    STARTER_STEP = "load_patch"
#
#    @classmethod
#    def starter(cls, kind: str = "ebi_patch") -> "RecipeModel":
#        """開新檔用的模型：畫布上已經放好 Input 卡，而且不算「改過」。
#
#        ``dirty`` 特意還原成 ``False`` —— 使用者什麼都還沒做，關窗時不該被問
#        「要存檔嗎」。
#        """
#        m = cls(kind=kind)
#        try:
#            m.add_step(cls.STARTER_STEP)
#        except KeyError:                 # pragma: no cover — 卡片庫壞了才會發生
#            pass
#        m.dirty = False
#        m.clear_history()      # 起手卡不是「使用者做過的一步」，Ctrl+Z 不該退掉它
#        return m
#
#    # ---- listener ---------------------------------------------------------
#    def add_listener(self, fn: Callable[[], None]) -> None:
#        self._listeners.append(fn)
#
#    def _changed(self) -> None:
#        self.dirty = True
#        for fn in list(self._listeners):
#            fn()
#
#    # ---- 復原 / 重做（F7-16）-----------------------------------------------
#    def snapshot(self) -> Dict[str, Any]:
#        """整個編輯狀態的深拷貝（純 Python 值，可以直接比較）。"""
#        return {
#            "kind": self.kind, "recipe_id": self.recipe_id,
#            "author": self.author, "description": self.description,
#            "version": self.version,
#            "node_order": list(self.node_order),
#            "nodes": {nid: (n.step, dict(n.params), bool(n.enabled))
#                      for nid, n in self.nodes.items()},
#            "edges": [tuple(e) for e in self.edges],
#            "expr": self.expr, "threshold": self.threshold,
#            "bins": dict(self.bins),
#        }
#
#    def restore(self, snap: Dict[str, Any]) -> None:
#        """把狀態換成某一份快照（不發 listener，呼叫端負責）。"""
#        self.kind = snap["kind"]
#        self.recipe_id = snap["recipe_id"]
#        self.author = snap["author"]
#        self.description = snap["description"]
#        self.version = snap["version"]
#        self.node_order = list(snap["node_order"])
#        self.nodes = {nid: RecipeNode(id=nid, step=step, params=dict(params),
#                                      enabled=enabled)
#                      for nid, (step, params, enabled) in snap["nodes"].items()}
#        self.edges = [tuple(e) for e in snap["edges"]]
#        self.expr = snap["expr"]
#        self.threshold = snap["threshold"]
#        self.bins = dict(snap["bins"])
#
#    def _push_undo(self, coalesce: Optional[str] = None) -> None:
#        """在改動**之前**記一步。
#
#        ``coalesce`` 是「這次改的是哪一個東西」。同一個東西連續改（拖滑桿、
#        在輸入框裡打字）只記第一次 —— 不然按一次 Ctrl+Z 只會退回一個畫素，
#        使用者得按四十次才回得到動之前的樣子，那等於沒有復原。
#        """
#        if coalesce is not None and coalesce == self._coalesce and self._undo:
#            return
#        self._coalesce = coalesce
#        self._undo.append(self.snapshot())
#        if len(self._undo) > self.UNDO_DEPTH:
#            self._undo.pop(0)
#        self._redo.clear()
#
#    def end_coalescing(self) -> None:
#        """「這一段連續調整結束了」（換節點、換參數、存檔時呼叫）。"""
#        self._coalesce = None
#
#    def can_undo(self) -> bool:
#        return bool(self._undo)
#
#    def can_redo(self) -> bool:
#        return bool(self._redo)
#
#    def undo(self) -> bool:
#        if not self._undo:
#            return False
#        self._redo.append(self.snapshot())
#        self.restore(self._undo.pop())
#        self.end_coalescing()
#        self._changed()
#        return True
#
#    def redo(self) -> bool:
#        if not self._redo:
#            return False
#        self._undo.append(self.snapshot())
#        self.restore(self._redo.pop())
#        self.end_coalescing()
#        self._changed()
#        return True
#
#    def clear_history(self) -> None:
#        """開新檔／載入檔案之後：在那之前的事情不屬於這一份 recipe。"""
#        self._undo.clear()
#        self._redo.clear()
#        self.end_coalescing()
#
#    # ---- 節點操作 ----------------------------------------------------------
#    def _new_id(self, step_key: str) -> str:
#        base = step_key
#        if base not in self.nodes:
#            return base
#        i = 2
#        while f"{base}{i}" in self.nodes:
#            i += 1
#        return f"{base}{i}"
#
#    def add_step(self, step_key: str, at: Optional[int] = None) -> str:
#        step_cls = get_step(step_key)          # 未知 key 會 raise KeyError
#        self._push_undo()
#        node_id = self._new_id(step_key)
#        params = step_cls.validate_params({})  # 全預設
#        self.nodes[node_id] = RecipeNode(id=node_id, step=step_key, params=params)
#        if at is None:
#            self.node_order.append(node_id)
#        else:
#            self.node_order.insert(max(0, min(at, len(self.node_order))), node_id)
#        self._changed()
#        return node_id
#
#    def remove(self, node_id: str) -> None:
#        if node_id in self.nodes:
#            self._push_undo()
#            del self.nodes[node_id]
#            self.node_order = [n for n in self.node_order if n != node_id]
#            self._changed()
#
#    def move(self, node_id: str, delta: int) -> None:
#        if node_id not in self.node_order or delta == 0:
#            return
#        i = self.node_order.index(node_id)
#        j = max(0, min(len(self.node_order) - 1, i + delta))
#        if i != j:
#            self._push_undo()
#            self.node_order.insert(j, self.node_order.pop(i))
#            self._changed()
#
#    def set_enabled(self, node_id: str, enabled: bool) -> None:
#        node = self.nodes.get(node_id)
#        if node is not None and node.enabled != bool(enabled):
#            self._push_undo()
#            node.enabled = bool(enabled)
#            self._changed()
#
#    def set_param(self, node_id: str, name: str, value: Any) -> None:
#        """設定單一參數；不合法 → raise ParamError（UI 顯示訊息、值不落地）。"""
#        node = self.nodes[node_id]
#        step_cls = get_step(node.step)
#        trial = dict(node.params)
#        trial[name] = value
#        clean = step_cls.validate_params(trial)   # 整組重驗（含相依預設）
#        if clean != node.params:
#            self._push_undo("param:%s:%s" % (node_id, name))
#            node.params = clean
#            self._changed()
#
#    # ---- score ------------------------------------------------------------
#    def set_expr(self, expr: str) -> None:
#        if expr != self.expr:
#            self._push_undo("expr")
#            self.expr = expr
#            self._changed()
#
#    def set_threshold(self, thr: float) -> None:
#        thr = float(thr)
#        if thr != self.threshold:
#            self._push_undo("threshold")
#            self.threshold = thr
#            self._changed()
#
#    # ---- 查詢（給 UI 下拉）--------------------------------------------------
#    def category_of(self, node_id: str) -> str:
#        return get_step(self.nodes[node_id].step).category
#
#    def available_features(self, upto_node: Optional[str] = None) -> List[str]:
#        """route（到 upto_node 為止，含）會產出的特徵名，供表達式下拉。"""
#        feats: List[str] = []
#        for nid in self.node_order:
#            node = self.nodes[nid]
#            if not node.enabled:
#                continue
#            step_cls = get_step(node.step)
#            for f in step_cls.resolve_features(node.params):
#                if f not in feats:
#                    feats.append(f)
#            if nid == upto_node:
#                break
#        return feats
#
#    def available_streams(self, before_node: Optional[str] = None) -> List[str]:
#        """到 before_node（不含）為止累積的影像流名，供 image_key 參數下拉。"""
#        streams: List[str] = []
#        first = True
#        for nid in self.node_order:
#            if nid == before_node:
#                break
#            node = self.nodes[nid]
#            if not node.enabled:
#                continue
#            step_cls = get_step(node.step)
#            if first:
#                ws = step_cls.resolve_writes_for_kind(node.params, self.kind)
#                first = False
#            else:
#                ws = step_cls.resolve_writes(node.params)
#            for w in ws:
#                if w not in streams:
#                    streams.append(w)
#        return streams
#
#    # ---- 連線（F7-6）------------------------------------------------------
#    def _topological_order(self, edges: List[Tuple[str, str]]) -> Optional[List[str]]:
#        """依 edges 的拓撲排序；有循環回 ``None``。
#
#        同層之間**維持目前 ``node_order`` 的相對順序** —— 使用者拉一條線不該
#        讓畫面上其他節點無關地跳動。
#        """
#        rank = {nid: i for i, nid in enumerate(self.node_order)}
#        indeg = {nid: 0 for nid in self.nodes}
#        succ: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
#        for a, b in edges:
#            if a in indeg and b in indeg:
#                succ[a].append(b)
#                indeg[b] += 1
#        ready = sorted([n for n, d in indeg.items() if d == 0],
#                       key=lambda n: rank.get(n, 1 << 30))
#        out: List[str] = []
#        while ready:
#            n = ready.pop(0)
#            out.append(n)
#            for m in succ[n]:
#                indeg[m] -= 1
#                if indeg[m] == 0:
#                    ready.append(m)
#            ready.sort(key=lambda x: rank.get(x, 1 << 30))
#        return out if len(out) == len(self.nodes) else None
#
#    def has_edge(self, src: str, dst: str) -> bool:
#        """這兩個節點之間已經有線了嗎。
#
#        給 UI 分辨「拉不起來（會成環）」與「本來就連著了」用 —— 對使用者來說
#        那是兩件完全不同的事，混成同一句話會讓成功的操作看起來像失敗。
#        """
#        return (str(src), str(dst)) in self.edges
#
#    def add_edge(self, src: str, dst: str) -> bool:
#        """連一條線。會造成循環（或自迴圈／重複）就**不做事並回 False**。"""
#        src, dst = str(src), str(dst)
#        if src == dst or src not in self.nodes or dst not in self.nodes:
#            return False
#        if (src, dst) in self.edges:
#            return False
#        order = self._topological_order(self.edges + [(src, dst)])
#        if order is None:
#            return False                     # 循環 —— 擋在這裡，不讓它進 model
#        self._push_undo()
#        self.edges.append((src, dst))
#        self.node_order = order
#        self._changed()
#        return True
#
#    def remove_edge(self, src: str, dst: str) -> bool:
#        pair = (str(src), str(dst))
#        if pair not in self.edges:
#            return False
#        self._push_undo()
#        self.edges.remove(pair)
#        order = self._topological_order(self.edges)
#        if order is not None:
#            self.node_order = order
#        self._changed()
#        return True
#
#    def edges_of(self, node_id: str) -> List[Tuple[str, str]]:
#        nid = str(node_id)
#        return [e for e in self.edges if nid in e]
#
#    # ---- Recipe 互轉 -------------------------------------------------------
#    def to_recipe(self) -> Recipe:
#        return Recipe(
#            recipe_id=self.recipe_id,
#            routes={self.kind: list(self.node_order)},
#            edges=[list(e) for e in self.edges],
#            nodes={nid: RecipeNode(id=nid, step=n.step, params=dict(n.params),
#                                   enabled=n.enabled)
#                   for nid, n in self.nodes.items()},
#            score=ScoreSpec(expr=self.expr, threshold=self.threshold,
#                            bins=dict(self.bins)),
#            version=self.version, author=self.author, description=self.description,
#        )
#
#    @classmethod
#    def from_recipe(cls, recipe: Recipe, kind: Optional[str] = None) -> "RecipeModel":
#        k = kind or (sorted(recipe.routes)[0] if recipe.routes else "ebi_patch")
#        m = cls(kind=k)
#        m.recipe_id = recipe.recipe_id
#        m.author = recipe.author
#        m.description = recipe.description
#        m.version = recipe.version
#        m.node_order = list(recipe.routes.get(k, []))
#        in_route = set(m.node_order)
#        m.edges = [(str(a), str(b)) for a, b in (recipe.edges or [])
#                   if str(a) in in_route and str(b) in in_route]
#        m.nodes = {nid: RecipeNode(id=nid, step=n.step, params=dict(n.params),
#                                   enabled=n.enabled)
#                   for nid, n in recipe.nodes.items() if nid in set(m.node_order)}
#        m.expr = recipe.score.expr
#        m.threshold = float(recipe.score.threshold)
#        m.bins = dict(recipe.score.bins)
#        m.dirty = False
#        m.clear_history()
#        return m
#
#    def validate(self):
#        return validate(self.to_recipe(), kind=self.kind)
#
#
## ---------------------------------------------------------------------------
## 直方圖 / 門檻工具（純計算；HistogramWidget 與「拖門檻秒回」用）
## ---------------------------------------------------------------------------
#
#def histogram(scores: Sequence[float], n_bins: int = 24,
#              ) -> Tuple[List[float], List[int]]:
#    """回傳 (bin 邊界 n_bins+1 個, 各 bin 計數)。空輸入 → ([0,1], [0])。"""
#    vals = [float(s) for s in scores
#            if s is not None and not (math.isnan(s) or math.isinf(s))]
#    if not vals:
#        return [0.0, 1.0], [0]
#    lo, hi = min(vals), max(vals)
#    if hi <= lo:
#        hi = lo + 1.0
#    width = (hi - lo) / n_bins
#    edges = [lo + i * width for i in range(n_bins + 1)]
#    counts = [0] * n_bins
#    for v in vals:
#        i = min(int((v - lo) / width), n_bins - 1)
#        counts[i] += 1
#    return edges, counts
#
#
#def rebin(scores: Sequence[Optional[float]], threshold: float,
#          bins: Optional[Dict[str, int]] = None) -> Dict[int, int]:
#    """依門檻重算 bin 計數（拖門檻線時即時呼叫；不觸碰影像）。"""
#    bins = bins or {"below": 0, "above": 1}
#    out: Dict[int, int] = {}
#    for s in scores:
#        if s is None or (isinstance(s, float) and (math.isnan(s) or math.isinf(s))):
#            continue
#        b = bins["below"] if float(s) < threshold else bins["above"]
#        out[b] = out.get(b, 0) + 1
#    return out
#
#F 29edfd5ca497a5e9c4db3d03e9b3f4797da551e4 596 adept/ui/welcome.py
## ADEPT Studio 首次開啟導覽 — authored 2026-07-28 (M6-2).
#"""``WelcomeDialog`` 與 ``RecipeLibraryDialog`` —— 產品的「上車處」。
#
#為什麼要有這個檔（推廣鐵則）
#----------------------------
#ADEPT 的存在意義是讓**不會寫 code 的製程／設備工程師**把一個想法變成評分
#演算法。可是第一次打開 Studio 看到的是一條空流程 —— 東西全都在，就是沒有
#入口。這支對話框的唯一任務：**讓一個從沒用過的人，在大約一分鐘內看到一批
#真的算出分數的結果**。
#
#所以它不是一面文字牆，而是三顆「按下去真的會發生事情」的按鈕：
#
#1. **用範例資料試一次** —— 產一批合成資料 → 載入 → 載入 die-to-die 範本 →
#   試跑，最後畫面上是有分數分佈的直方圖與一整牆縮圖。**全產品最重要的一顆鈕。**
#2. **開啟我自己的 KLARF** —— 關掉自己，交給 Studio 的「開啟 KLARF…」。
#3. **看範例 recipe** —— 打開 :class:`RecipeLibraryDialog`（範例 recipe 庫）。
#
#**對話框不自己驅動 app**：三顆鈕都只 emit 訊號，真正的動作由
#:class:`~adept.ui.studio.StudioWindow` 執行。這樣對話框可以單獨測，
#Studio 也可以在沒有對話框的情況下跑同一段流程（``run_demo``）。
#
#「不再顯示」寫進 ``QSettings``（org ``ADEPT`` / app ``Studio``，鍵
#``welcome/skip``）。刻意用 ``IniFormat`` + ``UserScope``：測試只要呼叫
#``QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmpdir)``
#就能把整組設定導到暫存目錄，不會弄髒開發機。
#"""
#from __future__ import annotations
#
#import json
#import os
#from pathlib import Path
#from typing import Any, Dict, List, Optional
#
#from PySide6.QtCore import QSettings, Qt, QUrl, Signal
#from PySide6.QtGui import QDesktopServices
#from PySide6.QtWidgets import (
#    QCheckBox,
#    QDialog,
#    QFrame,
#    QHBoxLayout,
#    QLabel,
#    QListWidget,
#    QListWidgetItem,
#    QPushButton,
#    QSizePolicy,
#    QVBoxLayout,
#    QWidget,
#)
#
#from .scope import recipe_is_supported
#from .theme import SEG_LABELS, TOKENS, seg_hex
#
#__all__ = [
#    "WelcomeDialog", "RecipeLibraryDialog",
#    "SETTINGS_ORG", "SETTINGS_APP", "SKIP_WELCOME_KEY",
#    "app_settings", "welcome_disabled", "set_welcome_disabled",
#    "THEME_KEY", "saved_theme", "save_theme",
#    "RECIPES_DIR", "DOCS_DIR", "list_recipe_files", "read_recipe_info",
#    "quick_reference_pdf",
#]
#
##: repo 根目錄（本檔在 ``<repo>/adept/ui/welcome.py``）。
#_REPO = Path(__file__).resolve().parents[2]
#
##: 範例 recipe 庫的位置（``RecipeLibraryDialog`` 的預設來源）。
#RECIPES_DIR = _REPO / "examples" / "recipes"
#
##: 快速參考卡 PDF 找這個資料夾。
#DOCS_DIR = _REPO / "docs"
#
##: QSettings 座標（三處共用：本檔、Studio、測試）。
#SETTINGS_ORG = "ADEPT"
#SETTINGS_APP = "Studio"
#SKIP_WELCOME_KEY = "welcome/skip"
#
##: 主題偏好（F7-2）。與導覽旗標共用同一組 QSettings。
#THEME_KEY = "ui/theme"
#
##: 三段式的一句話說明（和 CLAUDE.md §2 的心智模型逐字對應）。
#_SEG_LINES = (
#    ("image", "Make images clean and comparable"),
#    ("algo", "Measure numbers from images (quantified evidence)"),
#    ("adc", "Score -> bin -> write back to KLARF"),
#)
#
#_INTRO = (
#    "ADEPT reads the tool's patch / Review SEM images together with their KLARF "
#    "and lets you build a pipeline out of step cards: it scores every defect, "
#    "splits them into bins by a threshold, and writes the result back to KLARF."
#    "\nNo programming needed — you decide what a real defect looks like, and the "
#    "pipeline works it out."
#)
#
#_FOOTER_HINT = ("First time here? Press the button on the left — you will be looking "
#                "at scored results in about a minute.")
#
#
## --------------------------------------------------------------------------- #
## QSettings 小工具
## --------------------------------------------------------------------------- #
#def app_settings() -> QSettings:
#    """Studio 的 ``QSettings``（org ``ADEPT`` / app ``Studio``、INI 格式）。"""
#    return QSettings(QSettings.IniFormat, QSettings.UserScope,
#                     SETTINGS_ORG, SETTINGS_APP)
#
#
#def welcome_disabled() -> bool:
#    """使用者是否勾過「不再顯示」。讀不到／格式怪 → 一律回 False（照樣顯示）。"""
#    value = app_settings().value(SKIP_WELCOME_KEY, False)
#    if isinstance(value, bool):
#        return value
#    return str(value).strip().lower() in ("1", "true", "yes", "on")
#
#
#def saved_theme(default: str = "light") -> str:
#    """使用者上次選的主題（讀不到就回 ``default``）。"""
#    try:
#        return str(app_settings().value(THEME_KEY, default) or default)
#    except Exception:                       # noqa: BLE001 — 設定讀不到不該擋開窗
#        return default
#
#
#def save_theme(name: str) -> None:
#    """記住主題偏好（立刻 sync）。"""
#    st = app_settings()
#    st.setValue(THEME_KEY, str(name))
#    st.sync()
#
#
#def set_welcome_disabled(disabled: bool) -> None:
#    """寫入「不再顯示」旗標（立刻 sync，關窗當掉也不會掉設定）。"""
#    st = app_settings()
#    st.setValue(SKIP_WELCOME_KEY, bool(disabled))
#    st.sync()
#
#
## --------------------------------------------------------------------------- #
## recipe 庫的讀取（全部從 JSON 讀，一個字都不寫死）
## --------------------------------------------------------------------------- #
#def list_recipe_files(directory: Any = None) -> List[Path]:
#    """``examples/recipes/*.json`` 依檔名排序（資料夾不在就回空清單）。"""
#    d = Path(str(directory)) if directory is not None else RECIPES_DIR
#    if not d.is_dir():
#        return []
#    return sorted(d.glob("*.json"))
#
#
#def read_recipe_info(path: Any) -> Dict[str, Any]:
#    """讀一份 recipe JSON → 給庫對話框顯示用的摘要（**不做驗證、不炸**）。
#
#    壞掉的檔案不會讓整個庫開不起來：回傳的 dict 會帶 ``error``，
#    對話框把它顯示成一列紅字，其他 recipe 照常可用（鐵則 7 的精神）。
#    """
#    p = Path(str(path))
#    info: Dict[str, Any] = {
#        "path": str(p), "file": p.name, "recipe_id": p.stem,
#        "description": "", "routes": [], "route_steps": {},
#        "n_steps": 0, "expr": "", "threshold": None, "author": "",
#        "version": None, "error": "",
#    }
#    try:
#        with open(str(p), "r", encoding="utf-8") as f:
#            d = json.load(f)
#        if not isinstance(d, dict):
#            raise ValueError("top level is not a JSON object")
#    except Exception as e:                       # noqa: BLE001 — UI 邊界
#        info["error"] = "%s: %s" % (type(e).__name__, e)
#        return info
#
#    info["recipe_id"] = str(d.get("recipe_id") or p.stem)
#    info["description"] = str(d.get("description") or "")
#    info["author"] = str(d.get("author") or "")
#    info["version"] = d.get("version")
#
#    routes = d.get("routes") or {}
#    if isinstance(routes, dict):
#        info["routes"] = [str(k) for k in routes]
#        info["route_steps"] = {str(k): len(list(v or [])) for k, v in routes.items()}
#    info["n_steps"] = len(dict(d.get("nodes") or {}))
#
#    score = d.get("score") or {}
#    if isinstance(score, dict):
#        info["expr"] = str(score.get("expr") or "")
#        try:
#            info["threshold"] = float(score.get("threshold"))
#        except (TypeError, ValueError):
#            info["threshold"] = None
#    return info
#
#
#def quick_reference_pdf(directory: Any = None) -> Optional[Path]:
#    """``docs/`` 裡的快速參考卡 PDF；找不到回 ``None``（呼叫端必須擋）。
#
#    名字含 quick / reference / 參考 / 卡 的排前面，其餘的 PDF 也接受
#    （廠內可能自己換檔名）。
#    """
#    d = Path(str(directory)) if directory is not None else DOCS_DIR
#    if not d.is_dir():
#        return None
#    pdfs = sorted(d.glob("*.pdf"))
#    if not pdfs:
#        return None
#    for p in pdfs:
#        low = p.name.lower()
#        if any(k in low for k in ("quick", "reference", "quickref", "card")):
#            return p
#    return pdfs[0]
#
#
## --------------------------------------------------------------------------- #
## 三段式視覺（影像 → 算法 → ADC 判定）
## --------------------------------------------------------------------------- #
#class _SegmentStrip(QWidget):
#    """一條「影像 → 算法 → ADC 判定」的彩色說明帶（不用任何圖檔）。
#
#    顏色直接取 :func:`~adept.ui.theme.seg_hex`，和卡片庫區塊標題、Pipeline
#    卡片左側色條是同一組 token —— 使用者在導覽看到的橙色，等一下在畫面上
#    看到的也是同一個橙色。
#    """
#
#    def __init__(self, parent: Optional[QWidget] = None) -> None:
#        super().__init__(parent)
#        lay = QHBoxLayout(self)
#        lay.setContentsMargins(0, 0, 0, 0)
#        lay.setSpacing(6)
#        self.cards: List[QFrame] = []
#        for i, (cat, line) in enumerate(_SEG_LINES):
#            if i:
#                arrow = QLabel("▶", self)
#                arrow.setStyleSheet("color:%s; font-size:15px;"
#                                    % TOKENS["text_hint"])
#                lay.addWidget(arrow, 0)
#            lay.addWidget(self._card(cat, line), 1)
#
#    def _card(self, category: str, line: str) -> QFrame:
#        fg, bg = seg_hex(category), seg_hex(category, bg=True)
#        card = QFrame(self)
#        card.setObjectName("segCard")
#        card.setStyleSheet(
#            "QFrame#segCard { background:%s; border:1px solid %s;"
#            " border-radius:8px; }" % (bg, fg))
#        card.setProperty("category", category)
#        card.setMinimumHeight(58)
#        box = QVBoxLayout(card)
#        box.setContentsMargins(10, 7, 10, 7)
#        box.setSpacing(2)
#
#        title = QLabel(SEG_LABELS[category], card)
#        title.setStyleSheet("color:%s; font-weight:700; font-size:12px;" % fg)
#        body = QLabel(line, card)
#        body.setWordWrap(True)
#        body.setStyleSheet("color:%s; font-size:11px;" % TOKENS["text_secondary"])
#        box.addWidget(title)
#        box.addWidget(body)
#        self.cards.append(card)
#        return card
#
#
## --------------------------------------------------------------------------- #
## 首次開啟導覽
## --------------------------------------------------------------------------- #
#class WelcomeDialog(QDialog):
#    """首次開啟（與工具列「說明」）看到的導覽。
#
#    三顆動作鈕**只發訊號**，實際動作由 Studio 做：
#
#    - ``demo_requested()``       → ``StudioWindow.run_demo()``
#    - ``open_klarf_requested()`` → 「開啟 KLARF…」
#    - ``library_requested()``    → :class:`RecipeLibraryDialog`
#    - ``quickref_requested(str)``→ 已開啟的 PDF 路徑（沒有 PDF 時鈕是停用的）
#
#    測試友善：:meth:`click_demo` / :meth:`click_open` / :meth:`click_library` /
#    :meth:`set_dont_show_again` 都不需要真的滑鼠事件。
#    """
#
#    demo_requested = Signal()
#    open_klarf_requested = Signal()
#    library_requested = Signal()
#    quickref_requested = Signal(str)
#
#    def __init__(self, parent: Optional[QWidget] = None) -> None:
#        super().__init__(parent)
#        self.setWindowTitle("Welcome to ADEPT")
#        self.setModal(False)          # 永遠不擋住主視窗（測試也才不會卡住）
#        self.setMinimumWidth(620)
#
#        root = QVBoxLayout(self)
#        root.setContentsMargins(18, 16, 18, 14)
#        root.setSpacing(12)
#
#        title = QLabel("ADEPT — build your own defect decision pipeline from cards", self)
#        title.setObjectName("paramTitle")
#        root.addWidget(title)
#
#        intro = QLabel(_INTRO, self)
#        intro.setWordWrap(True)
#        intro.setStyleSheet("color:%s;" % TOKENS["text_secondary"])
#        self.intro_label = intro
#        root.addWidget(intro)
#
#        self.segments = _SegmentStrip(self)
#        root.addWidget(self.segments)
#
#        root.addWidget(self._separator())
#
#        # ---- 三顆真的會做事的鈕 ------------------------------------------
#        row = QHBoxLayout()
#        row.setSpacing(8)
#        self.btn_demo = QPushButton("Try it with sample data", self)
#        self.btn_demo.setObjectName("primary")
#        self.btn_demo.setCursor(Qt.PointingHandCursor)
#        self.btn_demo.setToolTip(
#            "Generate synthetic data, load it, apply the die-to-die template and "
#            "trial-run it — you land straight on a score histogram and a wall of "
#            "thumbnails (none of your own files are touched)")
#        self.btn_demo.setMinimumHeight(34)
#        self.btn_demo.clicked.connect(self.click_demo)
#
#        self.btn_open = QPushButton("Open my own KLARF", self)
#        self.btn_open.setCursor(Qt.PointingHandCursor)
#        self.btn_open.setToolTip("Close this window and go straight to picking a KLARF file")
#        self.btn_open.setMinimumHeight(34)
#        self.btn_open.clicked.connect(self.click_open)
#
#        self.btn_library = QPushButton("Browse templates", self)
#        self.btn_library.setCursor(Qt.PointingHandCursor)
#        self.btn_library.setToolTip("Open the template library — every entry is a complete, runnable pipeline")
#        self.btn_library.setMinimumHeight(34)
#        self.btn_library.clicked.connect(self.click_library)
#
#        for b in (self.btn_demo, self.btn_open, self.btn_library):
#            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
#            row.addWidget(b, 1)
#        root.addLayout(row)
#
#        hint = QLabel(_FOOTER_HINT, self)
#        hint.setObjectName("paramHint")
#        hint.setWordWrap(True)
#        root.addWidget(hint)
#
#        root.addWidget(self._separator())
#
#        # ---- 底列：不再顯示 / 快速參考卡 / 關閉 ----------------------------
#        bottom = QHBoxLayout()
#        bottom.setSpacing(8)
#        self.chk_dont_show = QCheckBox("Do not show again", self)
#        self.chk_dont_show.setToolTip(
#            "This window will not open on start-up any more; Help on the toolbar "
#            "always brings it back")
#        self.chk_dont_show.setChecked(welcome_disabled())
#        self.chk_dont_show.toggled.connect(self._on_dont_show_toggled)
#        bottom.addWidget(self.chk_dont_show)
#        bottom.addStretch(1)
#
#        self.quickref_path = quick_reference_pdf()
#        self.btn_quickref = QPushButton("Quick reference card", self)
#        self.btn_quickref.setProperty("variant", "ghost")
#        self.btn_quickref.setCursor(Qt.PointingHandCursor)
#        self.btn_quickref.setStyleSheet(
#            "QPushButton { background:transparent; border:0; color:%s;"
#            " text-decoration:underline; padding:4px 8px; }"
#            "QPushButton:disabled { color:%s; text-decoration:none; }"
#            % (TOKENS["accent_active"], TOKENS["text_disabled"]))
#        if self.quickref_path is None:
#            self.btn_quickref.setEnabled(False)
#            self.btn_quickref.setToolTip(
#                "No quick-reference PDF in docs/ yet — it ships with the "
#                "offline installer.")
#        else:
#            self.btn_quickref.setToolTip("Open with the system PDF viewer: %s"
#                                         % self.quickref_path.name)
#        self.btn_quickref.clicked.connect(self.open_quick_reference)
#        bottom.addWidget(self.btn_quickref)
#
#        self.btn_close = QPushButton("Explore on my own", self)
#        self.btn_close.setCursor(Qt.PointingHandCursor)
#        self.btn_close.setToolTip("Close the tour and go straight to Studio")
#        self.btn_close.clicked.connect(self.close)
#        bottom.addWidget(self.btn_close)
#        root.addLayout(bottom)
#
#    # ---- 小零件 ----------------------------------------------------------
#    def _separator(self) -> QFrame:
#        line = QFrame(self)
#        line.setFrameShape(QFrame.HLine)
#        line.setFixedHeight(1)
#        line.setStyleSheet("background:%s; border:0;" % TOKENS["border_default"])
#        return line
#
#    # ---- 動作（每一顆都可以在測試裡直接呼叫）------------------------------
#    def click_demo(self) -> None:
#        """「用範例資料試一次」：先關掉自己，讓使用者看得到結果。"""
#        self.close()
#        self.demo_requested.emit()
#
#    def click_open(self) -> None:
#        """「開啟我自己的 KLARF」：關掉自己，交給 Studio 的開檔動作。"""
#        self.close()
#        self.open_klarf_requested.emit()
#
#    def click_library(self) -> None:
#        """「看範例 recipe」：打開 recipe 庫（導覽留著，方便再按別的鈕）。"""
#        self.library_requested.emit()
#
#    def set_dont_show_again(self, checked: bool) -> None:
#        """程式化地勾／取消「不再顯示」（會寫進 QSettings）。"""
#        self.chk_dont_show.setChecked(bool(checked))
#
#    def _on_dont_show_toggled(self, checked: bool) -> None:
#        set_welcome_disabled(bool(checked))
#
#    def open_quick_reference(self) -> bool:
#        """開啟快速參考卡 PDF；檔案不在就什麼都不做並回 ``False``。"""
#        path = self.quickref_path
#        if path is None or not os.path.isfile(str(path)):
#            return False
#        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
#        self.quickref_requested.emit(str(path))
#        return True
#
#
## --------------------------------------------------------------------------- #
## 範例 recipe 庫
## --------------------------------------------------------------------------- #
#class RecipeLibraryDialog(QDialog):
#    """範例 recipe 庫：左邊列清單、右邊看細節，雙擊或按「載入」就套用。
#
#    清單上顯示的每一個字（名稱、說明、route、步驟數、分數表達式）**都是從
#    JSON 讀出來的**，沒有任何一份 recipe 被寫死在程式裡 —— 之後往
#    ``examples/recipes/`` 丟一份新的 JSON，這裡就會自己多一列。
#
#    訊號：``recipe_chosen(path)``（雙擊或按「載入」）。
#    """
#
#    recipe_chosen = Signal(str)
#
#    def __init__(self, directory: Any = None,
#                 parent: Optional[QWidget] = None) -> None:
#        super().__init__(parent)
#        self.setWindowTitle("Template library")
#        self.setModal(False)
#        self.setMinimumSize(720, 420)
#        self.directory = Path(str(directory)) if directory is not None else RECIPES_DIR
#
#        root = QVBoxLayout(self)
#        root.setContentsMargins(16, 14, 16, 12)
#        root.setSpacing(10)
#
#        head = QLabel("Pick the one closest to your layer, load it, then tune the "
#                      "parameters — do not start from an empty pipeline.", self)
#        head.setWordWrap(True)
#        head.setStyleSheet("color:%s;" % TOKENS["text_secondary"])
#        root.addWidget(head)
#
#        body = QHBoxLayout()
#        body.setSpacing(10)
#
#        self.list = QListWidget(self)
#        self.list.setMinimumWidth(280)
#        self.list.setAlternatingRowColors(True)
#        self.list.currentRowChanged.connect(self._on_row_changed)
#        self.list.itemDoubleClicked.connect(lambda *_: self.load_selected())
#        body.addWidget(self.list, 2)
#
#        self.detail = QLabel("", self)
#        self.detail.setWordWrap(True)
#        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
#        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
#        self.detail.setStyleSheet(
#            "background:%s; border:1px solid %s; border-radius:8px; padding:10px;"
#            % (TOKENS["bg_surface"], TOKENS["border_default"]))
#        body.addWidget(self.detail, 3)
#        root.addLayout(body, 1)
#
#        bottom = QHBoxLayout()
#        bottom.setSpacing(8)
#        self.path_label = QLabel("", self)
#        self.path_label.setObjectName("paramHint")
#        bottom.addWidget(self.path_label, 1)
#        self.btn_load = QPushButton("Load", self)
#        self.btn_load.setObjectName("primary")
#        self.btn_load.setCursor(Qt.PointingHandCursor)
#        self.btn_load.setToolTip("Load this recipe into the Studio pipeline panel")
#        self.btn_load.clicked.connect(self.load_selected)
#        bottom.addWidget(self.btn_load)
#        self.btn_close = QPushButton("Close", self)
#        self.btn_close.setCursor(Qt.PointingHandCursor)
#        self.btn_close.clicked.connect(self.close)
#        bottom.addWidget(self.btn_close)
#        root.addLayout(bottom)
#
#        self._entries: List[Dict[str, Any]] = []
#        self.reload()
#
#    # ---- 資料 -------------------------------------------------------------
#    def reload(self) -> int:
#        """重讀資料夾並重建清單；回傳有幾份 recipe。"""
#        # F7-1：只列至少有一條「這個 build 跑得動」的 route 的 recipe
#        # （純 rsem 的範本會被濾掉；雙 route 的照列，載進來會走 ebi_patch）。
#        self._entries = [info for info in
#                         (read_recipe_info(p)
#                          for p in list_recipe_files(self.directory))
#                         if recipe_is_supported(info)]
#        self.list.clear()
#        for info in self._entries:
#            item = QListWidgetItem(self._item_text(info))
#            item.setData(Qt.UserRole, info["path"])
#            item.setToolTip(info["description"] or info["error"] or info["file"])
#            if info["error"]:
#                item.setToolTip("This file could not be read: %s" % info["error"])
#            self.list.addItem(item)
#        if self._entries:
#            self.list.setCurrentRow(0)
#        else:
#            self.detail.setText("No recipe JSON in `examples/recipes/` yet.")
#            self.btn_load.setEnabled(False)
#        return len(self._entries)
#
#    def entries(self) -> List[Dict[str, Any]]:
#        """目前列出的 recipe 摘要（測試用；順序與清單一致）。"""
#        return list(self._entries)
#
#    def count(self) -> int:
#        return self.list.count()
#
#    def item_text(self, index: int) -> str:
#        item = self.list.item(int(index))
#        return "" if item is None else str(item.text())
#
#    def path_at(self, index: int) -> str:
#        item = self.list.item(int(index))
#        return "" if item is None else str(item.data(Qt.UserRole))
#
#    def select(self, index: int) -> bool:
#        """選第 ``index`` 列（超出範圍回 False）。"""
#        if not (0 <= int(index) < self.list.count()):
#            return False
#        self.list.setCurrentRow(int(index))
#        return True
#
#    def selected_path(self) -> Optional[str]:
#        row = int(self.list.currentRow())
#        if row < 0:
#            return None
#        return self.path_at(row) or None
#
#    # ---- 顯示 -------------------------------------------------------------
#    @staticmethod
#    def _item_text(info: Dict[str, Any]) -> str:
#        if info["error"]:
#            return "%s\n(unreadable: %s)" % (info["file"], info["error"])
#        routes = ", ".join(info["routes"]) or "(no route)"
#        return "%s\nroute: %s · %d steps" % (
#            info["recipe_id"], routes, int(info["n_steps"]))
#
#    def _on_row_changed(self, row: int) -> None:
#        if not (0 <= int(row) < len(self._entries)):
#            self.detail.setText("")
#            self.path_label.setText("")
#            self.btn_load.setEnabled(False)
#            return
#        info = self._entries[int(row)]
#        self.btn_load.setEnabled(not info["error"])
#        self.path_label.setText(info["path"])
#        self.detail.setText(self._detail_text(info))
#
#    @staticmethod
#    def _detail_text(info: Dict[str, Any]) -> str:
#        if info["error"]:
#            return "This file could not be read:\n%s" % info["error"]
#        lines = [info["description"] or "(this recipe has no description)", ""]
#        for route in info["routes"]:
#            lines.append("• route %s: %d steps"
#                         % (route, int(info["route_steps"].get(route, 0))))
#        lines.append("")
#        lines.append("score = %s" % (info["expr"] or "(no score expression)"))
#        if info["threshold"] is not None:
#            lines.append("threshold = %g (score >= threshold -> bin 1)" % float(info["threshold"]))
#        if info["author"]:
#            lines.append("Author: %s" % info["author"])
#        return "\n".join(lines)
#
#    # ---- 動作 -------------------------------------------------------------
#    def load_selected(self) -> Optional[str]:
#        """發出 ``recipe_chosen(path)`` 並關窗；沒選到／檔案壞掉回 ``None``。"""
#        row = self.list.currentRow()
#        if not (0 <= row < len(self._entries)):
#            return None
#        info = self._entries[row]
#        if info["error"]:
#            return None
#        path = str(info["path"])
#        self.recipe_chosen.emit(path)
#        self.close()
#        return path
#
