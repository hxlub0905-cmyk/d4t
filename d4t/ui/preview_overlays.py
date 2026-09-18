# d4t UI — authored 2026-09-19 (F116 第 1 步之 1c).
"""預覽區：**看哪一條流**，以及**畫在圖上的那幾種東西**。

為什麼自己一個模組（`CLAUDE.md` §4：新的面板一律開新模組，`studio.py` 留給
接線）：這一族裡面是**內容**不是接線 —— 點一張卡時預設顯示哪一條流（規則是
「這張卡的主要輸出」，不是「它寫過的最後一條」）、區域框從 model 推導出來的
那一份、量測標記從跑完的 context 來的那一份、對焦那張圖挑哪一格、兩張圖的
檢視狀態怎麼互相跟。

**區域框與量測標記是兩個來源**（原本那一段的老註解，搬過來仍然成立）：框是從
model 推導的（還沒跑就畫得出來），標記來自跑完的 context —— 不要混。

**行為零改動**（F116 §1）：方法本體逐字搬，只把屬於視窗的 ``self.x`` 換成
``self.w.x``。只有這一塊在讀寫的狀態（``_compare_on``、``_view_syncing``）
跟著行為搬進來；``_user_stream`` / ``_user_stream_b`` 留在視窗 —— 前者在換卡片
時被別段重設（§3-1：被別段也寫的留在視窗），而它們是一對，拆開比留著更難讀。

接線留在 `studio.py`（`_wire_widgets`）—— 這一支只提供 slot（F116 §3-4）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QObject

from d4t.core.pipeline import get_step

if TYPE_CHECKING:                      # 只給型別看：這一支不 import studio
    from .studio import StudioWindow


class PreviewOverlays(QObject):
    """預覽區的影像流選擇與疊加。從 `StudioWindow` 搬來（F116 第 1 步之 1c）。"""

    def __init__(self, win: "StudioWindow") -> None:
        # ⚠ 一定要掛 parent（F116 §7-1）—— 理由見 `gauge_panel.py` 同一行。
        super().__init__(win)
        self.w = win
        self._compare_on = False       # 並排比對開著嗎（F7-8）
        self._view_syncing = False     # 正在把檢視狀態推給另一張圖

    def _default_stream(self, images: Dict[str, Any]) -> str:
        """點一張卡時，左邊那張圖預設顯示哪一條流。

        規則是**這張卡的主要輸出**，不是「它寫過的最後一條流」。這兩者以前被
        當成同一件事（取 ``writes`` 的最後一個），但當時 Enhance 卡的
        ``resolve_writes`` 是 ``[主流] + 附帶的那一串``，於是預設值一路是那一串
        的最後一項 —— 點 Normalize 就跳到 ``ref``。並排比對開著、右邊又停在
        ``ref`` 的時候，畫面就變成左右兩張一模一樣的 ref，每點一張卡都要手動
        切回來（F7-9 試用回饋 §4）。F7-18 之後一張卡只寫一條流，兩者又合一了，
        但這條規則仍然是對的（``roi_template`` 這類卡的 writes 不只一項）。
        """
        # 並排打開時左邊固定從 test 起跳（右邊就是 ref）——「兩張輸入影像」是
        # 並排唯一的用途，而每次點卡片都要重認一次哪邊是哪邊的話，比對就慢了。
        if self._compare_on and "test" in images:
            return "test"
        nid = self.w.selected_node
        node = self.w.model.nodes.get(nid) if nid else None
        if node is not None:
            for name in self.w._PRIMARY_PARAMS:
                # ``streams`` 是**一串**（"test,ref"）—— 整串當流名去比一定
                # 落空，然後就掉到下面的 writes 分支取最後一項，於是點一張
                # 兩條流的 Normalize 會跳到 ref。取第一條才是「這張卡的主流」。
                for val in str(node.params.get(name, "") or "").split(","):
                    val = val.strip()
                    if val in images:
                        return val
            try:
                writes = get_step(node.step).resolve_writes(node.params)
            except KeyError:
                writes = []
            for w in reversed(list(writes)):
                if w in images:
                    return str(w)
        if "test" in images:
            return "test"
        for k in images:
            return str(k)
        return ""

    def _populate_streams(self, images: Dict[str, Any]) -> None:
        """重建影像流下拉；使用者**親手挑過**的那條還在就留著。

        「親手挑過」只認 :meth:`_on_stream_changed`（真的動了下拉）；換節點時
        會清掉，讓畫面自動跳到新節點的輸出 —— 點卡片就看得到那張圖。
        """
        names = sorted(images)
        want = (self.w._user_stream if self.w._user_stream in images
                else self._default_stream(images))
        want_b = (self.w._user_stream_b if self.w._user_stream_b in images
                  else self._default_compare_stream(images, want))
        if want_b == want:
            # 左右同一條流 = 兩張一模一樣的圖，那是並排唯一沒有意義的狀態。
            # 使用者親手挑的右邊也讓步 —— 他挑 ref 是為了「跟左邊比」，
            # 不是為了「看兩次 ref」。
            want_b = self._default_compare_stream(images, want)
        self.w._syncing = True
        try:
            self.w.stream_combo.clear()
            self.w.stream_combo.addItems(names)
            if want in names:
                self.w.stream_combo.setCurrentIndex(names.index(want))
            self.w.stream_combo_b.clear()
            self.w.stream_combo_b.addItems(names)
            if want_b in names:
                self.w.stream_combo_b.setCurrentIndex(names.index(want_b))
        finally:
            self.w._syncing = False

    def _default_compare_stream(self, images: Dict[str, Any], left: str) -> str:
        """並排的右邊預設放什麼：左邊是 test 就配 ref（反之亦然）。

        並排最常見的用途就是「這張 Enhance 卡有沒有把 test 和 ref 調成不一樣」，
        所以預設直接給那一對，不要讓使用者每次都自己挑。
        """
        pair = {"test": "ref", "ref": "test"}
        mate = pair.get(str(left))
        if mate and mate in images:
            return mate
        for k in ("ref", "diff", "test"):
            if k in images and k != left:
                return k
        for k in sorted(images):
            if k != left:
                return str(k)
        return str(left)

    def _show_current_stream(self) -> None:
        self.w.image_view.set_image(
            self.w._preview_images.get(self.w.stream_combo.currentText()))
        if self.w.compare_check.isChecked():
            self.w.image_view_b.set_image(
                self.w._preview_images.get(self.w.stream_combo_b.currentText()))
        self._refresh_region_overlay()

    def region_overlay(self) -> List[Tuple[float, float, float, float]]:
        """**選著的那張卡**牽涉到的框（正規化座標，可能有好幾個）。

        兩種來源，同一個畫法：
        - 這張卡**定義**的區域（``resolve_regions_out``，F7-11 起）——
          調 Region 卡時看框跟著參數動；
        - 這張卡**引用**的區域（``resolve_regions_in``，2026-08-14 使用者
          要求）—— 選 Gray-level stats 那種量測卡時，畫面直接回答
          「我到底在量哪裡」。以前量測卡選起來預覽上什麼都沒有，roi 填錯
          只能用數字猜。

        仍然只畫**選著那張卡**的，不是 context 裡所有的框：一份 recipe 常常
        有好幾張 Region 卡，全部畫出來分不清誰是誰。
        """
        node = self.w.model.nodes.get(self.w.selected_node or "")
        ctx = getattr(getattr(self.w, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return []
        out: List[Tuple[float, float, float, float]] = []
        for name in self._overlay_region_names(node):
            out.extend(tuple(float(v) for v in r)
                       for r in ctx.roi_norm_rects(name))
        return out

    @staticmethod
    def _overlay_region_names(node) -> List[str]:
        """要畫哪幾個區域，**依畫的順序**。

        只有一份：框與框的名字必須走同一個清單，不然顏色會指到錯的區域 ——
        而畫面上沒有任何東西透露那件事。
        """
        try:
            step_cls = get_step(node.step)
            produced = list(step_cls.resolve_regions_out(node.params))
            consumed = list(step_cls.resolve_regions_in(node.params))
        except Exception:  # 顯示用，不能擋畫面
            return []
        names: List[str] = []
        for name in produced:
            # ``_center`` 是同一組框裡的一個，畫兩次只會變成粗一點的線。
            # 它的角色由 focus 表達（見下面），不是多畫一個框。
            # （**引用**的不套這條 —— 量測卡明確指著 ``cross_center`` 時，
            #   那個框就是它在量的地方，當然要畫。）
            if name.endswith("_center") or name in names:
                continue
            names.append(name)
        for name in consumed:
            if name and name not in names:
                names.append(name)
        return names

    def region_overlay_names(self) -> List[str]:
        """每個框屬於哪一個具名區域（跟 :meth:`region_overlay` 等長）。

        分開一支而不是讓 ``region_overlay`` 回 tuple：那一支有測試在比清單，
        而且「框在哪」與「框叫什麼」是兩個問題 —— 疊框只需要前者也還是對的
        （長度對不上時 `ImageView` 就整組不分色，見 `set_overlay`）。
        """
        node = self.w.model.nodes.get(self.w.selected_node or "")
        ctx = getattr(getattr(self.w, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return []
        out: List[str] = []
        for name in self._overlay_region_names(node):
            out.extend([name] * len(ctx.roi_norm_rects(name)))
        return out

    def _refresh_region_overlay(self) -> None:
        """把框疊到預覽影像上。**每次預覽算完都會走這裡**，所以拖參數的時候
        框是跟著動的 —— 那正是這種參數唯一調得動的方式（F7-8）。"""
        boxes = self.region_overlay()
        focus = self._focus_box_index(boxes)
        labels = self.region_overlay_names()
        for view in (self.w.image_view, self.w.image_view_b):
            view.set_overlay(boxes, focus, labels)
        self._refresh_measure_marks()

    def measure_marks(self, stream: Optional[str] = None):
        """選著那張卡要畫的量測標記 ``(lines, points, focus, labels)``（F19）。

        ``stream`` 是**這個 view 現在顯示的那一條流** —— 卡片只交那一條量到的
        （見 `Step.overlay_marks`）。不給就是全部，`measure_marks()` 那樣呼叫的
        既有測試因此不用動。

        資料由**卡片自己**交出來（`Step.overlay_marks`）—— meta 的形狀是那張卡
        的事。這裡只問「現在選著的是誰」，所以整個 Measure 段共用同一條路。

        **跟框不同來源**：框從 model 推導（recipe 說要看哪裡），標記來自
        `_last_result` 的 context（這一顆真的量到了什麼）。混在一起的話，
        「框還在但標記沒了」這個最有用的狀態就講不出來。
        """
        node = self.w.model.nodes.get(self.w.selected_node or "")
        ctx = getattr(getattr(self.w, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return [], [], -1, []
        try:
            lines, points, focus, labels = get_step(node.step).overlay_marks(
                ctx, node.params, stream)
        except Exception:  # 顯示用，不能擋畫面
            return [], [], -1, []
        # ``focus`` 可以是一個 index 或**一串**（一個記號不只一條線 ——
        # GLV 的贏家格是一個 X）。這裡不收窄成 int：收窄過的那一版，X 的第二
        # 條會掉進「不是焦點」那一組，畫出來只剩一條斜線。
        return (list(lines or []), list(points or []), focus,
                [str(v) for v in (labels or [])])

    def heat_tiles(self, stream: Optional[str] = None):
        """選著那張卡要鋪的熱圖 ``(cells, colours, legend)``（F87）。

        跟 :meth:`measure_marks` 一模一樣的形狀 —— 卡片自己交
        （`Step.overlay_heat`），這裡只問「現在選著的是誰、正在看哪一條流」。
        """
        node = self.w.model.nodes.get(self.w.selected_node or "")
        ctx = getattr(getattr(self.w, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return [], [], None
        try:
            cells, colours, legend = get_step(node.step).overlay_heat(
                ctx, node.params, stream)
        except Exception:  # 顯示用，不能擋畫面
            return [], [], None
        return list(cells or []), [str(c) for c in (colours or [])], legend

    def _refresh_measure_marks(self) -> None:
        """**一個 view 一次** —— 兩張圖顯示的可能是不同的流（比對模式）。

        以前這裡取一次就推給兩個 view，於是一張卡在 test 與 ref 上各量一次時，
        兩組線會同時畫在**你正在看的那一張**上，同色、同標籤、分不出來。
        現在各問各的，比對模式因此也才是對的（2026-08-22）。
        """
        for view, combo in ((self.w.image_view, self.w.stream_combo),
                            (self.w.image_view_b, self.w.stream_combo_b)):
            lines, points, focus, labels = self.measure_marks(
                str(combo.currentText() or ""))
            view.set_marks(lines, points, focus, labels,
                           solid=self._marks_solid())
            cells, colours, legend = self.heat_tiles(
                str(combo.currentText() or ""))
            view.set_heat(cells, colours, legend)

    def _marks_solid(self) -> bool:
        """選著那張卡的標記要不要畫滿（`Step.marks_solid`）。

        **那張卡說的，不是這裡猜的** —— 「幾條線算少」是卡片自己才知道的事。
        """
        node = self.w.model.nodes.get(self.w.selected_node or "")
        if node is None:
            return False
        try:
            return bool(getattr(get_step(node.step), "marks_solid", False))
        except Exception:  # 顯示用，不能擋畫面
            return False

    def _focus_box_index(self, boxes: Sequence[Sequence[float]]) -> int:
        """哪一個框要畫成醒目的那一個 —— **卡片真的挑走的那一塊**。

        醒目的那一個的意思一直都是 ``<name>_center``（見
        :meth:`_overlay_region_names` 的註解：「它的角色由 focus 表達」）。
        以前這裡是用「離影像正中心最近」算出來的，而那在 F20 之前跟
        ``_center`` **必定一致** —— 那一版的 `_center` 就是這樣定義的。

        F20（2026-08-22）之後 Region 卡多了一格「哪一塊是缺陷那一塊」，
        選「訊號最強」時 ``_center`` 會落在別的地方。這裡不跟著改的話，
        影像上被畫成醒目的是 A、卡片實際量的是 B —— 而畫面上沒有任何東西
        透露那件事（那正是這個 repo 最怕的那種錯）。

        所以改成**去問 context 那一塊到底是哪一個**，對不上才退回舊規則
        （沒跑過、或那張卡不吐 ``_center``）。
        """
        rects = self._center_rects()
        for i, box in enumerate(boxes):
            if any(all(abs(float(a) - float(b)) < 1e-6 for a, b in zip(box, r))
                   for r in rects):
                return i
        if not self._defines_regions():
            # **量測卡選著的時候不要亂指一個。** 這裡的醒目一直都是
            # ``<name>_center`` 的意思，而那是 **Region 卡**的產物。
            # 量測卡（GLV / CD）只是**引用**別人定義的區域 —— 一個 24 格的
            # 區域被 pooled 成一堆像素時，沒有任何一格是特別的，把離畫面中心
            # 最近的那一格畫成醒目等於在說一件不成立的事。
            # 量測卡要指哪一格，走的是自己的 `overlay_marks`（那才是
            # 「這一顆真的量到了什麼」那條路）。
            return -1
        if not self._picks_a_center():
            # **``pick="none"`` 的 Region 卡也不畫醒目框**（F31 T4）：它明講
            # 「沒有哪一格是缺陷那一塊」，退回「離中心最近」畫一個醒目的，
            # 等於畫布替引擎說了一句它沒說的話。
            return -1
        best, best_d = -1, None
        for i, (nx, ny, nw, nh) in enumerate(boxes):
            d = (nx + nw / 2.0 - 0.5) ** 2 + (ny + nh / 2.0 - 0.5) ** 2
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _defines_regions(self) -> bool:
        """選著的這張卡是不是**定義**區域的那種（Region 卡）。

        引用別人區域的量測卡不算 —— 見 :meth:`_focus_box_index` 的說明。
        """
        node = self.w.model.nodes.get(self.w.selected_node or "")
        if node is None:
            return False
        try:
            return bool(get_step(node.step).resolve_regions_out(node.params))
        except Exception:  # 顯示用，不能擋畫面
            return False

    def _picks_a_center(self) -> bool:
        """這張卡有沒有挑一塊 —— 宣告裡有沒有 ``<name>_center``。

        `pick="none"` 的 Region 卡定義區域但**不挑**，宣告裡因此沒有那個
        名字（`_util.region_family` 的開關）—— 醒目框跟著挑選一起走。
        """
        node = self.w.model.nodes.get(self.w.selected_node or "")
        if node is None:
            return False
        try:
            names = get_step(node.step).resolve_regions_out(node.params)
        except Exception:  # 顯示用，不能擋畫面
            return False
        return any(str(n).endswith("_center") for n in names)

    def _center_rects(self) -> List[Sequence[float]]:
        """這一顆上 ``<name>_center`` 實際落在哪 —— 沒跑過就是空的。"""
        node = self.w.model.nodes.get(self.w.selected_node or "")
        ctx = getattr(getattr(self.w, "_last_result", None), "context", None)
        if node is None or ctx is None:
            return []
        out: List[Sequence[float]] = []
        try:
            names = list(get_step(node.step).resolve_regions_out(node.params))
        except Exception:  # 顯示用，不能擋畫面
            return []
        for name in names:
            if not str(name).endswith("_center"):
                continue
            out.extend(tuple(float(v) for v in r)
                       for r in ctx.roi_norm_rects(name))
        return out

    def _on_stream_changed(self, text: str) -> None:
        if self.w._syncing:
            return
        self.w._user_stream = str(text) or None
        self._show_current_stream()

    def _on_stream_b_changed(self, text: str) -> None:
        if self.w._syncing:
            return
        self.w._user_stream_b = str(text) or None
        self._show_current_stream()

    # ---- 並排比對（F7-8）--------------------------------------------------
    def set_compare(self, on: bool) -> bool:
        """開／關並排的第二張圖。回傳最後的狀態。

        **預設是關的**，這是刻意的：F7-5 把 Gallery 與直方圖搬走，就是為了讓
        右欄的影像變大（使用者原話「影像最好大一點、置中」）。預設並排等於
        把剛爭取到的寬度再砍一半。真正需要並排的是**調 Enhance 卡的時候**
        （確認 test 與 ref 被調成一樣），那是一個明確的時機，一次點擊就到。

        兩張圖的縮放與平移連動 —— 沒有連動的並排要使用者自己把兩邊拖到同一個
        位置才比得起來，那還不如切換一張。
        """
        on = bool(on)
        if self.w.compare_check.isChecked() != on:
            self.w.compare_check.setChecked(on)     # 會再繞回這裡一次
            return self.w.compare_check.isChecked()
        self.w.image_view_b.setVisible(on)
        self.w.stream_combo_b.setVisible(on)
        self._compare_on = on
        if on:
            # 打開的當下重挑一次左右兩條流：預設是 test / ref。手動挑過的
            # (``_user_stream``) 仍然優先 —— 這裡只負責「還沒挑過」的情況。
            self._populate_streams(self.w._preview_images or {})
            self._show_current_stream()
            scale, offset = self.w.image_view.view_state()
            self.w.image_view_b.set_view(scale, offset)
        else:
            self.w.image_view_b.set_image(None)
        # 儀表跟著畫面走：兩張圖 → 兩張直方圖（見 _refresh_inspector）。
        self.w.gauges._refresh_inspector(getattr(self.w, "_last_result", None))
        return on

    def compare_enabled(self) -> bool:
        """並排現在開著嗎。用明確狀態而非 ``isVisible()``（視窗還沒 show 時後者恆假）。"""
        return bool(self._compare_on)

    def _link_views(self, source: Any, target: Any, scale: float, offset) -> None:
        """把 ``source`` 的檢視狀態推給 ``target``（單向，避免無限來回）。"""
        if not self._compare_on or self._view_syncing:
            return
        self._view_syncing = True
        try:
            target.set_view(scale, offset)
        finally:
            self._view_syncing = False
