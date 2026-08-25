# 四張 Region 卡收成一張之後，既有測試怎麼指過去（F30，2026-08-25）。
"""``roi_cross`` / ``roi_template`` **不再是卡片**，是 ``roi_reference`` 的兩個
``method``。這一份提供的是「那張舊卡」在新世界的樣子。

**它不是為了少改幾行測試。** 它綁上去的三樣東西 ——``method``、以及舊卡自己的
預設值（``source="ref"``、``roi_out="cross"``、``max_boxes=64``）—— 逐字就是
`recipe._migrate_folded_region_cards` 寫進舊 recipe 的那三樣。所以既有的幾十條
斷言在這裡跑，問的正是**「遷移過去的舊 recipe 行為有沒有變」**，而那是這種合併
唯一真正要證明的事。

合併之後的共用預設**故意跟舊卡不同**（``region`` / ``test`` / 8192）：三支的舊
預設互相衝突，挑任何一個當共用值，另外兩支的舊檔案就會安靜地換一個值跑。
所以遷移把舊值寫進參數裡，而這一份照做。
"""
from __future__ import annotations

from d4t.core.pipeline.step import get_step
from d4t.core.steps.roi_reference import METHOD_PROFILE, METHOD_TEMPLATE

#: 舊卡各自的預設值 —— 跟 `recipe._FOLDED_CARD_OLD_DEFAULTS` 逐字相同。
OLD_DEFAULTS = {
    METHOD_PROFILE: {"source": "ref", "roi_out": "cross", "max_boxes": 64},
    METHOD_TEMPLATE: {"source": "ref", "max_boxes": 8192},
}


def _method_ok(param_dict, method: str) -> bool:
    """這一格屬於這個 method 嗎（其他條件不管）。"""
    from d4t.core.pipeline.step import show_when_conditions
    for name, allowed in show_when_conditions(param_dict.get("show_when")):
        if name == "method":
            return str(method) in {str(v) for v in allowed}
    return True


class BoundRegionCard:
    """``roi_reference`` ＋ 一個綁死的 ``method`` ＋ 那張舊卡的預設值。

    介面跟 `Step` 的類別那一面一樣（``params`` / ``validate_params`` /
    ``resolve_*`` / ``configuration_issues``），而 ``card()`` 會回一個跑得動的
    實例 —— 所以 ``get_step("roi_cross")().run(ctx, p)`` 那種寫法原樣可用。
    """

    def __init__(self, method: str) -> None:
        self.method = str(method)
        self.old_defaults = dict(OLD_DEFAULTS.get(method) or {})

    # ---- 參數 ---------------------------------------------------------------
    def bind(self, params=None) -> dict:
        """一份參數 → 「遷移過去之後」的那一份。"""
        out = dict(self.old_defaults)
        out.update(dict(params or {}))
        out["method"] = self.method
        return out

    @property
    def _card(self):
        return get_step("roi_reference")

    @property
    def params(self):
        return list(self._card.params)

    @property
    def key(self):
        return self._card.key

    @property
    def label(self):
        return self._card.label

    @property
    def help(self):
        return self._card.help

    def validate_params(self, params=None):
        return self._card.validate_params(self.bind(params))

    def resolve_reads(self, params=None):
        return self._card.resolve_reads(self.bind(params))

    def resolve_writes(self, params=None):
        return self._card.resolve_writes(self.bind(params))

    def resolve_regions_out(self, params=None):
        return self._card.resolve_regions_out(self.bind(params))

    def resolve_regions_in(self, params=None):
        return self._card.resolve_regions_in(self.bind(params))

    def resolve_features(self, params=None):
        return self._card.resolve_features(self.bind(params))

    def configuration_issues(self, params=None):
        return self._card.configuration_issues(self.bind(params))

    def describe(self):
        """卡片庫那一份說明。``params`` **只留這個 method 看得到的那幾格** ——
        整張合併卡的 42 格攤出來的話，「Template 有哪些設定」這個問題會拿到一個
        包含直條紋敏感度的答案。"""
        d = dict(self._card.describe())
        bound = self.bind({})
        # **只照 ``method`` 篩**（不是照整組值）。這一支自己的 `show_when`
        # （``directions`` / ``place`` 那些）是**執行期**的規則，由表單依當下的
        # 值決定 —— 在這裡先篩掉的話，那幾列連生都不會生出來，而測試問的
        # 「它現在看不看得到」就永遠是「不存在」。
        kept = []
        for q in d.get("params") or []:
            if not _method_ok(q, self.method):
                continue
            q = dict(q)
            # **這張「舊卡」的預設值就是它自己的那一份**（``method`` 也包含在
            # 內）。表單會用 spec 的預設值補上沒填的格子
            # （`ParamForm.set_step`）—— 拿合併卡的預設的話，整張表會照另一支
            # 的規則顯示，於是 Profile 的每一格都被判定為不該出現。
            if q.get("name") in bound:
                q["default"] = bound[q["name"]]
            kept.append(q)
        d["params"] = kept
        # ``help`` 要是**這一支**的說明。合併卡的 help 講的是四支共通的那句話，
        # 而每一支自己能做什麼住在 ``method`` 那一格的 ``choice_help`` 裡 ——
        # 使用者在畫面上點到那個選項就讀得到，所以那裡才是它的家。
        method_spec = {q["name"]: q for q in d.get("params") or []}.get("method")
        extra = (method_spec or {}).get("choice_help", {}).get(self.method, "")
        d["help"] = ("%s %s" % (d.get("help", ""), extra)).strip()
        return d

    # ---- 跑 -----------------------------------------------------------------
    def __call__(self):
        return _BoundRun(self)


class _BoundRun:
    def __init__(self, bound: BoundRegionCard) -> None:
        self._bound = bound

    def run(self, ctx, params=None):
        return self._bound._card().run(ctx, self._bound.bind(params))

    def describe(self):
        return self._bound.describe()

    def __getattr__(self, name):
        return getattr(self._bound._card(), name)


def profile_card() -> BoundRegionCard:
    """以前的 ``roi_cross``（Profile）。"""
    return BoundRegionCard(METHOD_PROFILE)


def template_card() -> BoundRegionCard:
    """以前的 ``roi_template``（Template）。"""
    return BoundRegionCard(METHOD_TEMPLATE)


def region_card(key: str) -> BoundRegionCard:
    """舊 key → 綁好 method 的那張卡（測試裡取代 ``get_step``）。"""
    return {"roi_cross": profile_card, "roi_template": template_card}[key]()


# --------------------------------------------------------------------------- #
# 在一個 RecipeModel 上加「以前的那張卡」
# --------------------------------------------------------------------------- #
def add_region_step(model, old_key: str, at=None) -> str:
    """``model.add_step("roi_cross")`` 在 F30 之後的寫法。

    加的是 ``roi_reference``，然後把 ``method`` 與那張舊卡的預設值填進去 ——
    **逐字就是 `recipe._migrate_folded_region_cards` 對舊檔案做的事**。

    ⚠ ``add_step`` 會把每一格**輸入**清掉（新卡前後都是空的，F10），所以
    ``source`` 不在這裡填 —— 填了的話畫布上會有一張「有來源、卻沒有線」的卡，
    而那正是 F9 那一串坑的形狀。
    """
    bound = region_card(old_key)
    nid = model.add_step("roi_reference", at) if at is not None \
        else model.add_step("roi_reference")
    inputs = {spec.name for spec in bound.params
              if spec.direction == "in" or spec.type in ("image_key",
                                                         "image_keys",
                                                         "region_key",
                                                         "region_keys")}
    for name, value in bound.bind({}).items():
        if name in inputs:
            continue
        model.set_param(nid, name, value)
    return nid
