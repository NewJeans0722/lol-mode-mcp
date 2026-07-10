"""把 CommunityDragon 的原始說明文字轉成人類可讀的純文字。

原始資料長這樣(zh_tw 範例):
    "增加<scaleAP>@APAmp*100@%魔攻</scaleAP>。<br><br>..."

要處理兩件事:
1. @變數@ 佔位符:值放在 augment 的 dataValues,是長度 7 的陣列。
   實測發現 `desc` 欄位的佔位符和 dataValues 直接對得上
   (例如 APAmp=0.15 → @APAmp*100@ → 15%),而 `tooltip` 欄位
   引用的是遊戲內即時計算值(@f1@ 之類),對不上 —— 所以顯示用 desc。
   陣列裡的值若不同(部分強化可升級),把不同的值用「/」串起來,
   例如 "10/20",忠實呈現而不猜哪個 index 才對。
2. HTML 風格標籤:<br> 換行、其他標籤(<scaleAP> 等)去殼留字。
"""

from __future__ import annotations

import re
from typing import Any

_TAG_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_ANY = re.compile(r"</?[a-zA-Z][^>]*>")
_PLACEHOLDER = re.compile(r"@([A-Za-z0-9_]+)(?:\*(-?\d+(?:\.\d+)?))?@")
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


def _render_values(values: list[float], multiplier: float | None) -> str:
    """dataValues 的陣列 → 顯示字串;不同的值用 / 串接(依出現順序去重)。"""
    if multiplier is not None:
        values = [v * multiplier for v in values]
    seen: list[str] = []
    for v in values:
        s = _fmt_number(v)
        if s not in seen:
            seen.append(s)
    return "/".join(seen)


def _calc_lookup(calculations: dict[str, Any], name: str) -> str | None:
    """有些佔位符指向 calculations 區塊,最單純的形態是轉指一個 dataValue。

    例:"APAmpCalcTooltip": {"mFormulaParts": [{"mDataValue": "APAmp"}]}
    更複雜的公式(乘上英雄等級等)無法離線算,回 None 讓上層標記。
    """
    calc = calculations.get(name)
    if not isinstance(calc, dict):
        return None
    parts = calc.get("mFormulaParts")
    if isinstance(parts, list) and len(parts) == 1 and isinstance(parts[0], dict):
        dv = parts[0].get("mDataValue")
        if isinstance(dv, str):
            return dv
    return None


def _resolve_string_refs(text: str) -> str:
    """展開 {{ 字串表引用 }};查無對照的直接移除,不留原始碼給使用者看。"""
    def _sub(m: re.Match[str]) -> str:
        key = m.group(1).replace("@TeamSize@", "").lower()
        return _STRING_TABLE.get(key, "")
    return _STRING_REF.sub(_sub, text)


def render_description(text: str, data_values: dict[str, list[float]],
                       calculations: dict[str, Any] | None = None) -> str:
    """字串表引用展開 + 佔位符代入 + 標籤清理,回傳純文字說明。"""
    calculations = calculations or {}
    # 先展開引用:展開出來的文字裡還有 @佔位符@,要走後面的代入
    text = _resolve_string_refs(text)
    # dataValues 的 key 大小寫在不同 augment 間不一致,做個不分大小寫索引
    dv_ci = {k.lower(): v for k, v in data_values.items()}

    def _sub(m: re.Match[str]) -> str:
        name, mult = m.group(1), m.group(2)
        multiplier = float(mult) if mult else None
        values = dv_ci.get(name.lower())
        if values is None:
            # 試著從 calculations 轉指回 dataValues
            redirect = _calc_lookup(calculations, name)
            if redirect is not None:
                values = dv_ci.get(redirect.lower())
        if values is None:
            return "?"  # 離線解不出來(遊戲內即時值),誠實標記
        return _render_values(list(values), multiplier)

    text = _PLACEHOLDER.sub(_sub, text)
    text = _TAG_BR.sub("\n", text)
    text = _TAG_ANY.sub("", text)
    text = _SPRITE.sub("", text)
    # 收斂連續空行
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
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
