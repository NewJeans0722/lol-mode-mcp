"""競技場(Arena)每英雄平衡調整:基礎數值 + 逐技能改動。

兩個資料源(都是 LoL Wiki 的 Lua 模組,經 MediaWiki API 抓 wikitext):
1. Module:ChampionData/data 的 ["ar"] 區塊 —— 基礎數值加減
   (hp_base/hp_lvl/dam_lvl/arm_lvl/as_lvl),沿用 aram.py 的
   parse_champion_mode_data,和 ARAM 共用同一次抓取與快取。
2. Module:MapChanges/data/ar —— 逐技能的文字說明(英文),格式:
       ["Akali Q"] = [=[ * Base damage changed to {{ap|70 to 190}}. ]=]
   分三段(-- Champions / -- Items / -- Runes);wikitext 模板用
   wikitext.clean_wikitext 化簡。條目 key 以「英雄英文顯示名 + 空格 +
   技能代號(Q/W/E/R/I/P)或技能名」組成,對 ddragon 名單做最長前綴
   比對來分組(實測 453/453 條全對得上,唯一例外是 wiki 把
   Nunu & Willump 簡寫成 Nunu,用別名表補)。
"""

from __future__ import annotations

import logging
import re

from . import cache
from .aram import WIKI_API, get_wiki_data
from .champions import (Champion, get_champions, get_spell_names,
                        resolve_champion)
from .http_util import fetch_json
from .translate import translate_lines
from .wikitext import clean_wikitext, translate_annotations_en

logger = logging.getLogger(__name__)

MAPCHANGES_TITLE = "Module:MapChanges/data/ar"

# 基礎數值欄位 → 標籤(值一律是「加減量」,正 = 增益)
AR_STAT_LABELS = {
    "hp_base": "基礎生命值",
    "hp_lvl": "每級生命成長",
    "dam_base": "基礎攻擊力",
    "dam_lvl": "每級攻擊力成長",
    "arm_base": "基礎護甲",
    "arm_lvl": "每級護甲成長",
    "mr_base": "基礎魔法抗性",
    "mr_lvl": "每級魔抗成長",
    "as_lvl": "每級攻擊速度成長(百分點)",
}
AR_STAT_LABELS_EN = {
    "hp_base": "Base health",
    "hp_lvl": "Health growth per level",
    "dam_base": "Base attack damage",
    "dam_lvl": "AD growth per level",
    "arm_base": "Base armor",
    "arm_lvl": "Armor growth per level",
    "mr_base": "Base magic resist",
    "mr_lvl": "MR growth per level",
    "as_lvl": "AS growth per level (percentage points)",
}

# wiki 條目 key 用的英雄名 ≠ ddragon 顯示名時的別名表
_WIKI_NAME_ALIASES = {"Nunu": "Nunu & Willump"}

_ENTRY_RE = re.compile(r'\["([^"]+)"\]\s*=\s*\[=\[(.*?)\]=\]', re.S)


def _clean_entry(raw: str) -> list[str]:
    """一個條目的 wikitext → 逐行純文字(保留 */** 的巢狀縮排)。"""
    lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(\*+)\s*(.*)$", s)
        depth, body = (len(m.group(1)), m.group(2)) if m else (1, s)
        body = clean_wikitext(body)
        if body:
            lines.append("  " * (depth - 1) + "- " + body)
    return lines


def parse_map_changes(lua_text: str) -> dict[str, dict[str, list[str]]]:
    """整份模組 → {"champions"/"items"/"runes": {條目key: [清理後逐行]}}。"""
    markers = [("champions", "-- Champions"), ("items", "-- Items"),
               ("runes", "-- Runes")]
    positions = [(sec, lua_text.find(tag)) for sec, tag in markers]
    result: dict[str, dict[str, list[str]]] = {}
    for i, (sec, start) in enumerate(positions):
        if start < 0:
            result[sec] = {}
            continue
        ends = [p for _, p in positions[i + 1:] if p > start]
        chunk = lua_text[start:min(ends)] if ends else lua_text[start:]
        result[sec] = {key: _clean_entry(body)
                       for key, body in _ENTRY_RE.findall(chunk)}
    return result


def _fetch_map_changes() -> dict:
    raw = fetch_json(WIKI_API, params={
        "action": "query", "prop": "revisions", "rvprop": "content|timestamp",
        "rvslots": "main", "titles": MAPCHANGES_TITLE,
        "format": "json", "formatversion": "2",
    })
    rev = raw["query"]["pages"][0]["revisions"][0]
    sections = parse_map_changes(rev["slots"]["main"]["content"])
    if not sections["champions"]:
        # 解析出 0 筆寧可當失敗(觸發退回舊快取),防 wiki 改版悄悄變空
        raise ValueError("parsed 0 champion entries from MapChanges/data/ar "
                         "— structure may have changed")
    logger.info("map changes parsed: %d champion / %d item / %d rune entries",
                len(sections["champions"]), len(sections["items"]),
                len(sections["runes"]))
    sections["revision_time"] = rev.get("timestamp", "unknown")
    return sections


def get_map_changes() -> cache.CacheResult:
    return cache.get_cached("wiki_mapchanges_ar", _fetch_map_changes)


# ------------------------------------------------------------- 依英雄分組

def _ability_label(rest: str) -> str:
    if not rest:
        return "整體"
    if rest in ("I", "P"):
        return "被動"
    return rest  # Q/W/E/R 或具名技能(如 Nidalee Prowl 的 Prowl)


def group_champion_changes(
    entries: dict[str, list[str]], champs: list[Champion],
) -> dict[str, list[tuple[str, list[str]]]]:
    """{條目key: 行} → {英雄英文名: [(技能標籤, 行), ...]}(保留檔案順序)。"""
    prefix_to_name = {c.name_en: c.name_en for c in champs}
    prefix_to_name.update(_WIKI_NAME_ALIASES)
    prefixes = sorted(prefix_to_name, key=len, reverse=True)  # 最長前綴優先
    grouped: dict[str, list[tuple[str, list[str]]]] = {}
    for key, lines in entries.items():
        for p in prefixes:
            if key == p or key.startswith(p + " "):
                label = _ability_label(key[len(p):].strip())
                grouped.setdefault(prefix_to_name[p], []).append((label, lines))
                break
        else:
            logger.warning("map-changes entry %r matched no champion", key)
    return grouped


# ------------------------------------------------------------- tool 實作

def ability_zh_name(champ_id: str, label: str,
                    spell_names: dict | None) -> str | None:
    """技能標籤(Q/W/E/R/被動/英文技能名)→ 台服技能名;查不到回 None。"""
    info = (spell_names or {}).get(champ_id)
    if not info:
        return None
    if label in ("Q", "W", "E", "R"):
        return info["slots"].get(label)
    if label == "被動":
        return info["slots"].get("P")
    if label == "整體":
        return None
    return info["by_en"].get(label.lower())


def _format_stat(key: str, value: float, locale: str = "zh_tw") -> str:
    if locale == "en_us":
        label = AR_STAT_LABELS_EN.get(key, key)
        icon = "🟢 Buff" if value > 0 else "🔴 Nerf"
    else:
        label = AR_STAT_LABELS.get(key, key)
        icon = "🟢 增益" if value > 0 else "🔴 削弱"
    return f"{icon} {label} {value:+g}"


def do_arena_balance(champion: str, locale: str = "zh_tw") -> str:
    en = locale.strip().lower() == "en_us"
    try:
        champs_result = get_champions()
    except cache.DataUnavailableError as exc:
        return f"❌ 查詢失敗:無法取得英雄名單(Data Dragon 連線失敗)。技術細節:{exc}"
    champ, candidates = resolve_champion(champion, champs_result.data)
    if champ is None:
        if candidates:
            names = "、".join(f"{c.name_zh}({c.name_en})" for c in candidates)
            return f"找不到英雄「{champion}」。你是不是要找:{names}?"
        return f"找不到英雄「{champion}」,請確認名稱(中英文皆可)。"

    # 兩個 wiki 資料源:任一可用就先出結果,各自失敗各自註明
    stats: dict[str, float] | None = None
    abilities: list[tuple[str, list[str]]] = []
    stats_ok = mc_ok = False
    problems: list[str] = []
    stale = False
    revision = "?"

    try:
        wiki_result = get_wiki_data()
        stats = wiki_result.data.get("ar", {}).get(champ.name_en)
        stats_ok = True
        stale = stale or wiki_result.is_stale
    except cache.DataUnavailableError as exc:
        problems.append(f"基礎數值(ChampionData)抓取失敗:{exc}")

    try:
        mc_result = get_map_changes()
        grouped = group_champion_changes(mc_result.data["champions"],
                                         champs_result.data)
        abilities = grouped.get(champ.name_en, [])
        mc_ok = True
        stale = stale or mc_result.is_stale
        revision = mc_result.data["revision_time"]
    except cache.DataUnavailableError as exc:
        problems.append(f"技能調整(MapChanges)抓取失敗:{exc}")

    if not stats_ok and not mc_ok:  # 兩個源都掛
        return ("❌ 查詢失敗:找到英雄 "
                f"{champ.name_zh}({champ.name_en}),但無法取得 LoL Wiki 的"
                f"競技場資料,請稍後再試。技術細節:{'; '.join(problems)}")

    spell_names = None
    if not en:  # 技能台服名(查不到就退回英文,不影響主要內容)
        try:
            spell_names = get_spell_names().data
        except cache.DataUnavailableError as exc:
            logger.warning("spell name map unavailable: %s", exc)

    if en:
        title = f"⚔️ {champ.name_en}({champ.name_zh})"
        lines = [title, "Arena balance changes this patch:", ""]
    else:
        title = f"⚔️ {champ.name_zh}({champ.name_en})"
        if champ.title_zh:
            title += f" — {champ.title_zh}"
        lines = [title, "競技場(Arena)本 patch 平衡調整:", ""]

    if stats:
        lines.append("[Base stats]" if en else "【基礎數值】")
        lines += [_format_stat(k, v, locale) for k, v in stats.items()]
        lines.append("")

    if abilities:
        lines.append("[Ability changes]" if en
                     else "【技能調整】(🔤 = 無把握規則翻譯的句子,保留英文原文)")
        for label, entry_lines in abilities:
            shown = label
            if en:
                shown = {"被動": "Passive", "整體": "General"}.get(label, label)
                entry_lines = [translate_annotations_en(ln) for ln in entry_lines]
            else:
                zh = ability_zh_name(champ.id, label, spell_names)
                if zh:
                    shown = f"{label} {zh}" if label in ("Q", "W", "E", "R", "被動") \
                        else f"{zh}({label})"
                entry_lines = translate_lines(entry_lines)
            lines.append(f"▸ {shown}")
            lines += ["  " + ln for ln in entry_lines]
        lines.append("")

    if not stats and not abilities:
        no_change = ("No Arena-specific balance changes this patch "
                     "(base stats and abilities use standard values)."
                     if en else
                     "本 patch **沒有競技場專屬的平衡調整**(基礎數值與技能"
                     "皆使用一般數值)。")
        lines = [title, no_change, ""]

    if en:
        src = f"📌 Source: LoL Wiki (CC BY-SA) · MapChanges revised {revision}"
        if problems:
            src += "\n⚠️ Partial source failure: " + "; ".join(problems)
        if stale:
            src += "\n⚠️ Refresh failed; showing last cached data (may be outdated)."
    else:
        src = f"📌 資料:LoL Wiki(CC BY-SA)· MapChanges 模組更新於 {revision}"
        if problems:
            src += "\n⚠️ 部分資料源失敗:" + "; ".join(problems)
        if stale:
            src += "\n⚠️ 注意:資料更新失敗,以上為上次成功抓取的快取,可能過期。"
    lines.append(src)
    return "\n".join(lines)
