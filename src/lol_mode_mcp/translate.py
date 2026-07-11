"""規則式英→中翻譯:wiki 改動說明的固定句型 + 台服術語對照表。

**不是機器翻譯。** 只翻「句型解析得出來、術語都在表上」的行;
翻不完整的行整行保留英文,由呼叫端加 🔤 標記 —— 寧可看英文原文,
也不要輸出半中半英的難讀句或錯譯(使用者要求正確性優先)。

涵蓋的句型(掃描 MapChanges 與 patch 頁實際內容歸納):
  X changed to Y [from Z].       → X改為 Y(原為 Z)。
  X increased to Y [from Z].     → X提高至 Y(原為 Z)。
  X reduced/decreased to Y ...   → X降低至 Y(原為 Z)。
  Label: A ⇒ B                   → Label:A ⇒ B(Label 逐詞翻)
  Disabled. / New Guest of Honor. 等整句特例
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# 人工校訂的整句對照(Claude 逐句翻譯、隨套件出貨)。
# key = 去除粗斜體標記後的英文原句;wiki 改句子後 miss → 退回規則/🔤。
# (Mayhem 強化說明的整段人工翻譯另存 mayhem_zh.json,以英文強化名為 key,
#  於 mayhem_augments 建檔時套用,不走這裡的整句比對。)
_OVERRIDES_PATH = Path(__file__).resolve().parent / "data" / "mapchanges_zh.json"
_overrides: dict[str, str] | None = None


def _load_overrides() -> dict[str, str]:
    global _overrides
    if _overrides is None:
        try:
            _overrides = json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
        except OSError:
            logger.warning("mapchanges_zh.json missing — no curated overrides")
            _overrides = {}
    return _overrides

# ------------------------------------------------------------ 術語表
# (英文, 台服用語)。比對不分大小寫、長詞優先;英文側是 wiki 慣用寫法。
GLOSSARY: list[tuple[str, str]] = [
    ("of target's maximum health", "(佔目標最大生命)"),
    ("of target's current health", "(佔目標當前生命)"),
    ("of his maximum health", "(佔自身最大生命)"),
    ("of her maximum health", "(佔自身最大生命)"),
    ("base mana regeneration", "基礎魔力回復"),
    ("base health regeneration", "基礎生命回復"),
    ("critical strike chance", "爆擊機率"),
    ("critical strike damage", "爆擊傷害"),
    ("health regeneration", "生命回復"),
    ("mana regeneration", "魔力回復"),
    ("energy restoration", "能量回復"),
    ("magic resistance", "魔法抗性"),
    ("magic resist", "魔法抗性"),
    ("attack damage", "攻擊力"),
    ("ability power", "法術強度"),
    ("ability haste", "技能急速"),
    ("attack speed", "攻擊速度"),
    ("movement speed", "移動速度"),
    ("move speed", "移動速度"),
    ("health growth", "生命成長"),
    ("mana growth", "魔力成長"),
    ("health ratio", "生命係數"),
    ("stun duration", "暈眩時間"),
    ("root duration", "禁錮時間"),
    ("slow resist", "緩速抗性"),
    ("at all ranks", "(全等級)"),
    ("per stack", "每層"),
    ("per second", "每秒"),
    ("per tick", "每跳"),
    ("per cast", "每次施放"),
    ("per round", "每回合"),
    ("per hit", "每次命中"),
    ("per wave", "每波"),
    ("per level", "每級"),
    ("per champion", "每位英雄"),
    ("per target", "每個目標"),
    ("per", "每"),
    ("rounds", "回合"),
    ("round", "回合"),
    ("champions", "英雄"),
    ("champion", "英雄"),
    ("minions", "小兵"),
    ("minion", "小兵"),
    ("monsters", "野怪"),
    ("monster", "野怪"),
    ("targets", "目標"),
    ("target", "目標"),
    ("empowered", "強化"),
    ("enhanced", "強化"),
    ("initial", "初始"),
    ("additional", "額外"),
    ("strength", "強度"),
    ("value", "數值"),
    ("chance", "機率"),
    ("effect", "效果"),
    ("speed", "速度"),
    ("growth", "成長"),
    ("penetration", "穿透"),
    ("resistance", "抗性"),
    ("reduction", "減免"),
    ("restoration", "回復"),
    ("regeneration", "回復"),
    ("cap", "上限"),
    ("capped", "上限"),
    ("missing health", "已損失生命"),
    ("missing", "損失"),
    ("resistances", "抗性"),
    ("turrets", "砲塔"),
    ("turret", "砲塔"),
    ("allies", "友軍"),
    ("ally", "友軍"),
    ("enemies", "敵方"),
    ("enemy", "敵方"),
    ("takedown", "擊殺參與"),
    ("attacks", "攻擊"),
    ("attack", "攻擊"),
    ("active", "主動"),
    ("self", "自身"),
    ("refund", "返還"),
    ("timer", "計時"),
    ("units", "單位"),
    ("stats", "屬性"),
    ("dash", "衝刺"),
    ("final", "最終"),
    ("evolved", "進化後"),
    ("unempowered", "未強化"),
    ("fury", "怒氣"),
    ("tibbers", "提貝爾斯"),
    ("per ability cast", "每次施放技能"),
    ("ability", "技能"),
    ("abilities", "技能"),
    ("casts", "施放"),
    ("cast", "施放"),
    ("resets every round", "每回合重置"),
    ("resets", "重置"),
    ("reset", "重置"),
    ("every", "每"),
    ("marks", "印記"),
    ("mark", "印記"),
    ("darkin", "闇裔"),
    ("of his", "自身"),
    ("of her", "自身"),
    ("of your", "自身"),
    ("above", "高於"),
    ("below", "低於"),
    ("heal over time", "持續治療"),
    ("over time", "隨時間"),
    ("amount", "量"),
    ("daggers", "匕首"),
    ("dagger", "匕首"),
    ("feathers", "羽刃"),
    ("feather", "羽刃"),
    ("recasts", "再施放"),
    ("recast", "再施放"),
    ("meeps", "米普"),
    ("meep", "米普"),  # 巴德的小精靈,台服官方譯名(使用者確認)
    # 巴德的 Chimes:遊戲內文本(ddragon zh_TW)是「編鐘」,
    # 但官方繁中 patch notes 26.13 寫「調和之音」—— 兩個官方來源不一致,
    # 依本專案標準採遊戲內字串。
    ("chimes", "編鐘"),
    ("chime", "編鐘"),
    ("and", "與"),
    ("true damage", "真實傷害"),
    ("magic damage", "魔法傷害"),
    ("physical damage", "物理傷害"),
    ("base damage", "基礎傷害"),
    ("base heal", "基礎治療"),
    ("base shield", "基礎護盾"),
    ("mana cost", "魔力消耗"),
    ("energy cost", "能量消耗"),
    ("cast range", "施放距離"),
    ("damage reduction", "傷害減免"),
    ("damage received", "承受傷害"),
    ("damage dealt", "造成傷害"),
    ("recharge", "充能"),
    ("shield strength", "護盾強度"),
    ("healing", "治療"),
    ("heal", "治療"),
    ("shield", "護盾"),
    ("cooldown", "冷卻時間"),
    ("damage", "傷害"),
    ("maximum", "最大"),
    ("minimum", "最小"),
    ("max", "最大"),
    ("min", "最小"),
    ("bonus", "額外"),
    ("total", "總計"),
    ("base", "基礎"),
    ("health", "生命"),
    ("mana", "魔力"),
    ("energy", "能量"),
    ("armor", "護甲"),
    ("omnivamp", "全能吸血"),
    ("lifesteal", "生命偷取"),
    ("life steal", "生命偷取"),
    ("lethality", "致命性"),
    ("tenacity", "韌性"),
    ("gold", "金幣"),
    ("experience", "經驗值"),
    ("duration", "持續時間"),
    ("threshold", "門檻"),
    ("radius", "半徑"),
    ("range", "範圍"),
    ("ratio", "係數"),
    ("stacks", "層數"),
    ("stack", "層"),
    ("seconds", "秒"),
    ("second", "秒"),
    ("silver", "白銀"),
    ("prismatic", "稜彩"),
    ("tier", "稀有度"),
    ("level", "等級"),
    ("rank", "等級"),
    ("slow", "緩速"),
    ("autocast", "自動施放"),
    ("execution", "處決"),
    ("execute", "處決"),
    ("amp", "增幅"),
    ("passive", "被動"),
    ("recipe", "合成配方"),
    ("revives", "復活次數"),
    ("revive", "復活"),
]
_GLOSS_MAP = {en.lower(): zh for en, zh in GLOSSARY}
_GLOSS_RE = re.compile(
    r"\b(" + "|".join(re.escape(en) for en, _ in
                      sorted(GLOSSARY, key=lambda p: -len(p[0]))) + r")\b",
    re.I)

# 整句特例
_WHOLE_LINE = {
    "disabled.": "已停用。",
    "disabled": "已停用。",
    "new guest of honor.": "新登場貴賓。",
    "removed.": "已移除。",
    "general": "整體",
    "stats": "基礎數值",
}

# 允許殘留的英文 token(不算「沒翻到」):數值單位、鍵位、常見縮寫
_ALLOWED_WORDS = {"ap", "ad", "hp", "ms", "px", "kda", "vs", "aoe", "buff",
                  "nerf", "q", "w", "e", "r", "on", "hit"}

_CJK_SPACE_RE = re.compile(r"(?<=[一-鿿])\s+(?=[一-鿿])")


def _gloss(text: str) -> str:
    out = _GLOSS_RE.sub(lambda m: _GLOSS_MAP[m.group(1).lower()], text)
    return _CJK_SPACE_RE.sub("", out)


def _leftover_words(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z']+", text)
    return [w for w in words if w.lower() not in _ALLOWED_WORDS]


_STRUCTURES = [
    (re.compile(r"^(?P<x>.+?) changed to (?P<y>.+?)(?: from (?P<z>.+?))?\.?$",
                re.I), "改為"),
    (re.compile(r"^(?P<x>.+?) increased to (?P<y>.+?)(?: from (?P<z>.+?))?\.?$",
                re.I), "提高至"),
    (re.compile(r"^(?P<x>.+?) (?:reduced|decreased|lowered) to (?P<y>.+?)"
                r"(?: from (?P<z>.+?))?\.?$", re.I), "降低至"),
]

# 說明句型(Mayhem 圖鑑等):Grants X. / Increases X by Y. / Gain X.
# build 收 {群組名: 已 gloss 的值} dict,回傳中文句。
_DESC_STRUCTURES = [
    (re.compile(r"^(?:Grants?|Gains?) (?P<y>.+?)\.?$", re.I),
     lambda g: f"獲得{g['y']}。"),
    (re.compile(r"^Increases? (?:your )?(?P<x>.+?) by (?P<y>.+?)\.?$", re.I),
     lambda g: f"{g['x']}提高 {g['y']}。"),
    (re.compile(r"^(?:Reduces?|Decreases?) (?:your )?(?P<x>.+?) by (?P<y>.+?)\.?$",
                re.I), lambda g: f"{g['x']}降低 {g['y']}。"),
    (re.compile(r"^Deals? (?P<y>.+?) (?:increased|bonus) damage\.?$", re.I),
     lambda g: f"造成的傷害提高 {g['y']}。"),
]

_ARROW_RE = re.compile(r"^(?P<label>[^:：]+)[:：]\s*(?P<vals>.+⇒.+)$")


def _looks_like_name(text: str) -> bool:
    """短、無數字、不成句 → 視為(技能/物品)名稱行,保留原文不標記。"""
    return (len(text.split()) <= 4 and not re.search(r"\d", text)
            and not text.endswith("."))


def compile_name_map(name_map: dict[str, str]) -> re.Pattern | None:
    """名詞表(小寫 en → 台服名)→ 單一 alternation regex(長詞優先)。"""
    keys = [k for k in name_map if len(k) >= 3]
    if not keys:
        return None
    return re.compile(
        r"\b(" + "|".join(re.escape(k)
                          for k in sorted(keys, key=len, reverse=True)) + r")\b",
        re.I)


def translate_line(text: str, name_map: dict[str, str] | None = None,
                   _name_re: re.Pattern | None = None) -> tuple[str, bool]:
    """一行改動說明 → (中文, 是否完整翻譯)。

    不完整時回傳的第一值仍是「原文」(呼叫端自行加 🔤 標記),
    避免輸出半中半英的句子。name_map(小寫英文名→台服名)給
    技能/物品名稱行用。
    """
    original = text
    plain = text.replace("**", "").replace("*", "").strip()

    if name_map and _name_re is None:
        _name_re = compile_name_map(name_map)

    def _sub_names(s: str) -> str:
        # 句內專有名詞(技能/強化/裝備/英雄名)→ 台服名
        if _name_re is None:
            return s
        return _name_re.sub(lambda m: name_map[m.group(1).lower()], s)

    curated = _load_overrides().get(plain)
    if curated:
        # 人工譯文裡保留的英文專有名詞,執行期換成官方台服名
        return _CJK_SPACE_RE.sub("", _sub_names(curated)), True

    special = _WHOLE_LINE.get(plain.lower())
    if special:
        return special, True

    if name_map:
        hit = name_map.get(plain.lower())
        if hit:
            return f"{hit}({plain})", True
        plain = _sub_names(plain)

    m = _ARROW_RE.match(plain)  # "Label: 15s ⇒ 10s"
    if m:
        label = _gloss(m.group("label"))
        vals = m.group("vals")
        if "稀有度" in label or "tier" in m.group("label").lower():
            # 稀有度語境:Gold 是「黃金」階,不是金幣
            for en, zh in (("Silver", "白銀"), ("Gold", "黃金"),
                           ("Prismatic", "稜彩")):
                vals = re.sub(rf"\b{en}\b", zh, vals, flags=re.I)
        vals = _gloss(vals)
        if not _leftover_words(label) and not _leftover_words(vals):
            return f"{label}:{vals}", True
        return original, False

    for pattern, verb in _STRUCTURES:
        m = pattern.match(plain)
        if not m:
            continue
        x = _gloss(m.group("x"))
        y = _gloss(m.group("y"))
        z = _gloss(m.group("z")) if m.group("z") else None
        parts_ok = not (_leftover_words(x) or _leftover_words(y)
                        or (z and _leftover_words(z)))
        if parts_ok:
            out = f"{x}{verb} {y}"
            if z:
                out += f"(原為 {z})"
            return out + "。", True
        return original, False

    # 說明句型(Grants X. / Increases X by Y. 等,Mayhem 圖鑑用)
    for pattern, build in _DESC_STRUCTURES:
        m = pattern.match(plain)
        if not m:
            continue
        glossed = {k: _gloss(v) for k, v in m.groupdict().items() if v}
        if any(_leftover_words(v) for v in glossed.values()):
            return original, False
        return _CJK_SPACE_RE.sub("", build(glossed)), True

    if _looks_like_name(plain):
        return original, True  # 名稱行:保留原文、不算翻譯失敗

    glossed = _gloss(plain)
    if not _leftover_words(glossed):
        return glossed, True
    return original, False


def translate_lines(lines: list[str], name_map: dict[str, str] | None = None
                    ) -> list[str]:
    """整組行(含 '- ' 前綴與縮排)→ 中文;翻不完整的加 🔤 前綴。"""
    name_re = compile_name_map(name_map) if name_map else None
    out = []
    for line in lines:
        m = re.match(r"^(\s*- )(.*)$", line)
        prefix, body = (m.group(1), m.group(2)) if m else ("", line)
        zh, complete = translate_line(body, name_map, name_re)
        out.append(f"{prefix}{zh}" if complete else f"{prefix}🔤 {body}")
    return out


# 句子切分:句號/驚嘆號/問號 + 空白;不切括號內、不切小數點
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def translate_description(text: str, name_map: dict[str, str] | None = None
                          ) -> tuple[str, bool]:
    """整段說明(可多句)→ (中文, 是否全部翻出)。

    先查整段人工對照;否則逐句翻譯,翻不出的句子保留英文(整段標為
    未完成,呼叫端據此在段末加註「部分未譯」)。段內換行分別處理。
    """
    whole = _load_overrides().get(text.replace("**", "").replace("*", "").strip())
    name_re = compile_name_map(name_map) if name_map else None
    if whole:
        zh = whole
        if name_re is not None:
            zh = name_re.sub(lambda m: name_map[m.group(1).lower()], zh)
        return _CJK_SPACE_RE.sub("", zh), True

    all_complete = True
    out_lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            out_lines.append("")
            continue
        pieces = []
        for sent in _SENTENCE_SPLIT.split(para):
            sent = sent.strip()
            if not sent:
                continue
            zh, ok = translate_line(sent, name_map, name_re)
            all_complete = all_complete and ok
            pieces.append(zh)
        out_lines.append("".join(pieces))
    return "\n".join(out_lines).strip(), all_complete
