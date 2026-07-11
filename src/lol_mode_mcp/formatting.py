"""把 CommunityDragon 的原始說明文字轉成人類可讀的純文字。

原始資料長這樣(zh_tw 範例):
    "增加<scaleAP>@APAmp*100@%魔攻</scaleAP>。<br><br>..."

要處理三件事:
1. @變數@ 佔位符:值放在 augment 的 dataValues,是長度 7 的陣列。
   實測發現 `desc` 欄位的佔位符和 dataValues 直接對得上
   (例如 APAmp=0.15 → @APAmp*100@ → 15%),而 `tooltip` 欄位
   引用的是遊戲內即時計算值(@f1@ 之類),對不上 —— 所以顯示用 desc。
   **索引語意(2026-07-11 已驗證)**:另有 MaxLevel 欄位(陣列或純量,
   缺=1),index 1..MaxLevel 是第 1..N 星的數值,之後是外插垃圾
   (天界之身 Health=[1000,1000,2000,3000,4000...] MaxLevel=3 →
   星級值 1000/2000/3000);index 0 通常≈1星值但不可靠。
   可升級強化以「/」串接各星級值並在文末註記;MaxLevel=1 而值仍遞增的
   4 個例外(不朽守衛/火狐/重創劇毒/鐵砧賭博 = 隨遊戲內條件成長)
   維持整條相異值串接。
2. `@spell.Augment_{apiName}:{Key}@`:引用(通常是自己的)dataValues,
   以 apiName 對回強化解出。
3. calculations 的 GameCalculation 公式:能離線解的部分解
   (等級內插、屬性加成、層數項),完全解不出退「(依遊戲內數值)」,
   不再出現孤立的「?」。
另外:HTML 風格標籤 <br> 換行、其他標籤(<scaleAP> 等)去殼留字。
"""

from __future__ import annotations

import re
from typing import Any

_TAG_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_ANY = re.compile(r"</?[a-zA-Z][^>]*>")
_PLACEHOLDER = re.compile(r"@([A-Za-z0-9_]+)(?:\*(-?\d+(?:\.\d+)?))?@")
# @spell.Augment_ShadowRunner:MSAmount@ / @spell.Augment_Homeguard:MovementSpeed*100@
_SPELL_REF = re.compile(
    r"@spell\.Augment_([A-Za-z0-9_]+):([A-Za-z0-9_]+)(?:\*(-?\d+(?:\.\d+)?))?@")
_SPRITE = re.compile(r"%i:[A-Za-z0-9_]+%")  # 遊戲內圖示標記,純文字顯示不了
_STRING_REF = re.compile(r"\{\{\s*([A-Za-z0-9_@]+)\s*\}\}")  # 遊戲字串表引用

# {{ ... }} 是遊戲字串表的引用,cdragon 的 arena JSON 沒有展開它們。
# 對照表來源:遊戲字串表(cdragon 只掛 zh_cn,已手工轉繁中並比對
# LoL Wiki 英文版校正);@TeamSize@ 變體連字串表都沒有本文,
# 文字取自 Wiki 描述,標注「數值依隊伍規模而定」。
# key 一律小寫、去掉 @TeamSize@。若 patch 後出現新引用,查法見 NOTES.md。
_STRING_TABLE = {
    "item_keyword_onhit": "攻擊特效",
    "item_grievous_wounds": "重傷(降低治療與生命回復效果)",
    "cherry_spintowin_summary": "你的旋轉類技能獲得@SpinHaste@技能急速,並多造成@SpinDamageAmp*100@%傷害!",
    "cherry_augmentedpower_summary": "你的增幅裝置與裝備造成的傷害提升@DamageAmp@。",
    "cherry_craftingaugmentslot_summary": "解鎖你的第@TooltipSlotToUnlock@個增幅裝置欄位。在@RoundsUntilFreeAugment@回合內,獲得一個白銀階增幅裝置。",
    "cherry_criticalhealing_summary": "你的治療和護盾可以暴擊,造成額外的@CriticalHealCalc@。獲得@CritChance*100@%暴擊機率。",
    "cherry_dawnbringersresolve_summary": "跌到@HealthThreshold*100@%生命值以下時,在@HealDuration@秒內持續治療@HealCalc@。",
    "cherry_dematerialize_summary": "參與擊殺後獲得@AdaptiveForce@適應之力,每回合每位英雄 1 次。",
    "cherry_fruitsofyourlabor_summary": "能量花在你身上的效能提升@AmpAmount*100@%,並且會分享給你的友軍。",
    "cherry_hybrid_summary": "普攻造成傷害後,你的下一個技能傷害提升@AbilityBoost*100@%;技能造成傷害後,你的下一次普攻傷害提升@AttackBoost*100@%。",
    "cherry_orbitallaser_summary": "將召喚師技能「閃現」替換為軌道雷射:延遲後召喚雷射光束,在@GroundDuration@秒內持續造成@DamagetoChampions*100@%最大生命值的真實傷害。",
    "cherry_prismaticegg_summary": "參與擊殺時獲得@KillStackCredit@層,每回合每位英雄僅一次;@RequiredKillCount@層後孵化出稜彩獎勵。",
    "cherry_quest_urfschampion_summary": "需求:參與擊殺@TakedownsNeeded@次。獎勵:金鏟子。",
    "cherry_righteousfury_summary": "治療或護盾會提升你@SpellDamagePerStack*100@%技能傷害,回合內可無限疊加。",
    "cherry_slaparound_summary": "每當你定身或縛地一名敵人,獲得持續到回合結束的@AdaptiveForce@適應之力。",
    "cherry_soulsiphon_summary": "暴擊造成傷害的@HealPercentage*100@%會等額治療你自身。獲得@CritChance*100@%暴擊機率。",
    "cherry_tricksterdemon_summary": "離開隱形狀態時引發爆炸,造成@TotalDamage@魔法傷害;你的複製體和陷阱陣亡時也會觸發相同效果。",
    "cherry_aimforthehead_summary": "你的暴擊機率上限為@CritChanceCeiling*100@%,超出部分以@CritChanceToDamageRatio*100@%的比例轉化為暴擊傷害。",
    "cherry_vengeance_summary": "友軍陣亡後,你在該回合剩餘時間內獲得傷害提升與全能吸血。(數值依隊伍規模而定)",
    "cherry_spiritlink_summary": "你會分擔友軍受到的部分傷害,並依友軍獲得治療量的一部分治療自己。(數值依隊伍規模而定)",
    "cherry_parasiticrelationship_summary": "友軍造成傷害時,治療你其中的一部分。(數值依隊伍規模而定)",
    "cherry_chauffeur_tooltip": "你附身於友軍身上,無法自行移動;你的額外跑速會提供給友軍,並獲得技能急速與額外攻速。(數值依隊伍規模而定)",
}


def _fmt_number(v: float) -> str:
    """0.009999999776 → 0.01、20.0 → 20:先四捨五入再去掉小數尾巴。"""
    rounded = round(v, 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"


def read_max_level(data_values: dict[str, Any]) -> int:
    """dataValues 的 MaxLevel(陣列或純量,缺欄位=1)→ 星級數,夾 1..6。"""
    raw = data_values.get("MaxLevel", 1)
    if isinstance(raw, list):
        raw = raw[0] if raw else 1
    try:
        level = int(raw)
    except (TypeError, ValueError):
        level = 1
    return max(1, min(level, 6))


def _render_values(values: Any, multiplier: float | None,
                   max_level: int = 1) -> str:
    """dataValues 的值 → 顯示字串。

    - 純量:直接顯示。
    - max_level > 1:index 1..max_level 是各星級值(其後為外插垃圾,
      不顯示),相異值照序用 / 串接;全同則單值。
    - max_level == 1:維持「全部相異值 / 串接」——涵蓋 4 個
      「隨遊戲內條件成長」的例外(不朽守衛等,值仍遞增)。
    """
    if not isinstance(values, list):
        values = [values]
    if max_level > 1 and len(values) > max_level:
        values = values[1:max_level + 1]
    if multiplier is not None:
        values = [v * multiplier for v in values]
    seen: list[str] = []
    for v in values:
        s = _fmt_number(v)
        if s not in seen:
            seen.append(s)
    return "/".join(seen)


# GameCalculation 的屬性編號 → 名稱(只列實測遇過且對過 wiki 英文描述的;
# 查不到就用泛稱「屬性」)。9=暴擊機率(暴擊治療)、12=最大生命(巨像勇氣)。
_STAT_NAMES_ZH = {9: "暴擊機率", 12: "最大生命"}
_STAT_NAMES_EN = {9: "crit chance", 12: "max health"}

# 蜂群意識 BeeDamage 的雜湊型別:{ee18a47b} = min/max 區間
_HASH_RANGE_TYPE = "{ee18a47b}"
_HASH_RANGE_MIN, _HASH_RANGE_MAX = "{0589a59c}", "{0b65bc23}"


def _eval_calc(calc: Any, dv_ci: dict[str, Any], max_level: int,
               zh: bool, multiplier: float | None = None) -> str | None:
    """GameCalculation → 顯示字串;整體解不出回 None(上層給替代文字)。

    策略:逐個 mFormulaParts 渲染再串接;「數值主體」在前、
    「隨等級/屬性/層數」的修飾以括號註記附後。任何一個子項
    看不懂就整體放棄(回 None),寧缺勿錯。
    multiplier = 佔位符自帶的 *N(優先於 mDisplayAsPercent)。
    """
    if not isinstance(calc, dict):
        return None
    parts = calc.get("mFormulaParts")
    if not isinstance(parts, list) or not parts:
        return None
    # 佔位符寫明乘數(@X*100@)就用它;否則看公式的 mDisplayAsPercent
    percent = multiplier is None and bool(calc.get("mDisplayAsPercent"))
    mult = multiplier if multiplier is not None else (100.0 if percent else None)

    def render_part(part: Any) -> str | None:
        if not isinstance(part, dict):
            return None
        ptype = part.get("__type", "")
        if ptype == "NamedDataValueCalculationPart" or (
                "mDataValue" in part and set(part) <= {"__type", "mDataValue"}):
            values = dv_ci.get(str(part.get("mDataValue", "")).lower())
            if values is None:
                return None
            out = _render_values(values, mult, max_level)
            return out + "%" if percent else out
        if ptype == "ByCharLevelInterpolationCalculationPart":
            lo, hi = part.get("mStartValue", 0), part.get("mEndValue")
            if hi is None:
                return None
            rng = f"{_fmt_number(lo)}–{_fmt_number(hi)}" + ("%" if percent else "")
            return rng + ("(隨等級)" if zh else " (scales with level)")
        if ptype in ("StatByCoefficientCalculationPart",
                     "StatByNamedDataValueCalculationPart"):
            stat = part.get("mStat", 0)
            name = (_STAT_NAMES_ZH if zh else _STAT_NAMES_EN).get(
                stat, "屬性" if zh else "stats")
            return f"(+隨{name}加成)" if zh else f" (+scales with {name})"
        if ptype == "BuffCounterByCoefficientCalculationPart":
            return "(隨層數成長)" if zh else " (scales with stacks)"
        if ptype == "SumOfSubPartsCalculationPart":
            subs = [render_part(p) for p in part.get("mSubparts", [])]
            if any(s is None for s in subs):
                return None
            return "".join(subs)  # type: ignore[arg-type]
        if ptype == _HASH_RANGE_TYPE:
            lo = dv_ci.get(str(part.get(_HASH_RANGE_MIN, "")).lower())
            hi = dv_ci.get(str(part.get(_HASH_RANGE_MAX, "")).lower())
            if lo is None or hi is None:
                return None
            return (f"{_render_values(lo, mult, max_level)}–"
                    f"{_render_values(hi, mult, max_level)}")
        return None

    rendered = [render_part(p) for p in parts]
    if any(r is None for r in rendered):
        return None
    return "".join(rendered)  # type: ignore[arg-type]


def _resolve_string_refs(text: str) -> str:
    """展開 {{ 字串表引用 }};查無對照的直接移除,不留原始碼給使用者看。"""
    def _sub(m: re.Match[str]) -> str:
        key = m.group(1).replace("@TeamSize@", "").lower()
        return _STRING_TABLE.get(key, "")
    return _STRING_REF.sub(_sub, text)


def render_description(text: str, data_values: dict[str, Any],
                       calculations: dict[str, Any] | None = None,
                       locale: str = "zh_tw", api_name: str = "",
                       peers: dict[str, dict] | None = None) -> str:
    """字串表引用展開 + 佔位符代入 + 標籤清理,回傳純文字說明。

    api_name/peers 給 @spell.Augment_X:Y@ 這種跨引用查表用
    (peers = {apiName 小寫: 該強化的 dataValues},實測 X 都是自己)。
    可升級強化(MaxLevel>1)只顯示各星級值,文末加註記。
    """
    calculations = calculations or {}
    zh = locale != "en_us"
    # 先展開引用:展開出來的文字裡還有 @佔位符@,要走後面的代入
    text = _resolve_string_refs(text)
    # dataValues 的 key 大小寫在不同 augment 間不一致,做個不分大小寫索引
    dv_ci = {k.lower(): v for k, v in data_values.items()}
    max_level = read_max_level(data_values)
    unresolved = "(依遊戲內數值)" if zh else "(computed in-game)"

    def _sub_spell(m: re.Match[str]) -> str:
        ref_api, key, mult = m.group(1), m.group(2), m.group(3)
        multiplier = float(mult) if mult else None
        table = dv_ci
        if ref_api.lower() != api_name.lower():
            peer = (peers or {}).get(ref_api.lower())
            if peer is None:
                return unresolved
            table = {k.lower(): v for k, v in peer.items()}
        values = table.get(key.lower())
        if values is None:
            return unresolved
        return _render_values(values, multiplier, max_level)

    def _sub(m: re.Match[str]) -> str:
        name, mult = m.group(1), m.group(2)
        multiplier = float(mult) if mult else None
        values = dv_ci.get(name.lower())
        if values is not None:
            return _render_values(values, multiplier, max_level)
        # 佔位符指向 calculations 的公式:能解多少算多少
        rendered = _eval_calc(calculations.get(name), dv_ci, max_level, zh,
                              multiplier)
        return rendered if rendered is not None else unresolved

    text = _SPELL_REF.sub(_sub_spell, text)
    text = _PLACEHOLDER.sub(_sub, text)
    text = _TAG_BR.sub("\n", text)
    text = _TAG_ANY.sub("", text)
    text = _SPRITE.sub("", text)
    # 收斂連續空行
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if max_level > 1:
        note = (f"(可升級強化,最高 ★{max_level};斜線數值依序為各星級效果)"
                if zh else
                f"(Upgradable, max ★{max_level}; slashed values are per star level)")
        text += "\n" + note
    return text


def first_sentence(text: str, limit: int = 55) -> str:
    """取說明的第一句(或截斷),給清單用的一行摘要。"""
    text = text.split("\n")[0]
    for sep in ("。", ". "):
        idx = text.find(sep)
        if 0 < idx < limit:
            return text[: idx + 1]
    if len(text) > limit:
        return text[:limit] + "…"
    return text
