"""競技場 wiki 補充強化:cdragon arena JSON 缺漏的強化。

背景(2026-07-19 發現,詳見 NOTES.md):cdragon 的 arena JSON 只有
226 筆,LoL Wiki 的 Module:ArenaAugmentData/data 有 255 筆——缺的
包含現役強化(聲望 Fame 解鎖的飯三件套、升級系、隱藏合成系、
停用後重新啟用的雙響炮等)。這裡把 wiki 模組解析出來,
供 arena.py 補進雙語索引(英文原文,台服名靠 data/wiki_aug_zh.json
人工對照,查證過官方繁中 patch notes 才收錄)。

wiki 條目格式(Lua table):
    ["Bread Sandwich"] = {
        ["description"] = "Gain {{sti|{{as|ability haste}}}}. ...",
        ["tier"] = "Prismatic",
        ["level1"] = "{{sti|{{as|200 ability haste}}}}.",
        ["level2"] = "...", ["level3"] = "",
        ["notes"] = [=[ * This augment isn't available ... ]=],
    },
已從遊戲移除的條目 description 內含「Removed since [[Vxx.y]]」,解析時跳過。
"""

from __future__ import annotations

import logging
import re

from . import cache
from .aram import WIKI_API
from .http_util import fetch_json
from .wikitext import clean_wikitext

logger = logging.getLogger(__name__)

WIKI_AUG_TITLE = "Module:ArenaAugmentData/data"

_TIER_TO_RARITY = {"silver": 0, "gold": 1, "prismatic": 2}

_ENTRY_HEAD_RE = re.compile(r'^\t\["(.+?)"\]\s*=\s*\{', re.M)
# 欄位值是 "字串"(含跳脫)或 [=[ 長字串 ]=]
_FIELD_RE = re.compile(
    r'\["(\w+)"\]\s*=\s*(?:"((?:[^"\\]|\\.)*)"|\[=\[(.*?)\]=\])', re.S)


def _clean_rich(text: str) -> str:
    """wiki 的 description/level 欄位 → 純文字(HTML 清單/換行也化簡)。"""
    text = text.replace("\\\"", "\"")
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li[^>]*>", "\n• ", text)
    text = re.sub(r"</?(?:ul|ol|li)[^>]*>", "", text)
    lines = [clean_wikitext(ln) for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _clean_notes(raw: str, max_lines: int = 6) -> str:
    """notes 長字串 → 逐條純文字,太長截斷(細節請讀者查 wiki)。"""
    lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        m = re.match(r"^(\*+)\s*(.*)$", s)
        if not m:
            continue
        body = clean_wikitext(m.group(2))
        if body:
            lines.append("  " * (len(m.group(1)) - 1) + "- " + body)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["- …(其餘細節見 LoL Wiki)"]
    return "\n".join(lines)


def parse_augment_module(lua_text: str) -> dict[str, dict]:
    """整份模組 → {強化英文名: {"description","tier","levels","notes","removed"}}。"""
    heads = list(_ENTRY_HEAD_RE.finditer(lua_text))
    entries: dict[str, dict] = {}
    for i, m in enumerate(heads):
        name = m.group(1)
        end = heads[i + 1].start() if i + 1 < len(heads) else len(lua_text)
        block = lua_text[m.end():end]
        fields: dict[str, str] = {}
        for fm in _FIELD_RE.finditer(block):
            fields[fm.group(1)] = fm.group(2) if fm.group(2) is not None \
                else (fm.group(3) or "")
        desc_raw = fields.get("description", "")
        removed = re.search(r"Removed since \[\[V[\d.]+\]\]", desc_raw)
        levels = [_clean_rich(fields.get(k, ""))
                  for k in ("level1", "level2", "level3")]
        entries[name] = {
            "description": _clean_rich(desc_raw),
            "tier": fields.get("tier", ""),
            "rarity": _TIER_TO_RARITY.get(fields.get("tier", "").lower(), -1),
            "levels": [lv for lv in levels if lv],
            "notes": _clean_notes(fields.get("notes", "")),
            "removed": bool(removed),
        }
    return entries


def _fetch_wiki_augments() -> dict:
    raw = fetch_json(WIKI_API, params={
        "action": "query", "prop": "revisions", "rvprop": "content|timestamp",
        "rvslots": "main", "titles": WIKI_AUG_TITLE,
        "format": "json", "formatversion": "2",
    })
    rev = raw["query"]["pages"][0]["revisions"][0]
    entries = parse_augment_module(rev["slots"]["main"]["content"])
    if len(entries) < 100:
        # 平常 250+ 筆,少太多寧可當失敗(觸發退回舊快取)
        raise ValueError(f"parsed only {len(entries)} entries from "
                         f"{WIKI_AUG_TITLE} — structure may have changed")
    logger.info("wiki augment module parsed: %d entries "
                "(%d marked removed)", len(entries),
                sum(1 for e in entries.values() if e["removed"]))
    return {"entries": entries, "revision_time": rev.get("timestamp", "unknown")}


def get_wiki_augments() -> cache.CacheResult:
    return cache.get_cached("wiki_arena_augments", _fetch_wiki_augments)
