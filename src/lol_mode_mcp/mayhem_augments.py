"""ARAM: Mayhem 強化圖鑑資料。

來源組合(官方沒有含說明的 Mayhem 圖鑑檔,已查證 cdragon 只有
arena/tft;kiwi-hub.json 是空的):
- 名稱/稀有度/圖示:cdragon cherry-augments.json(zh_tw + default,
  官方遊戲字串,ARAM_ 前綴)
- 說明文字:wiki Module:MayhemAugmentData/data(英文 wikitext,
  用 wikitext.clean_wikitext 化簡)——官方未提供中文說明文字,
  故說明保留英文,由 UI 註明。
"""

from __future__ import annotations

import logging
import re

from . import cache
from .http_util import fetch_json
from .patch_notes import CHERRY_AUG_URL, _name_key
from .wikitext import clean_wikitext

logger = logging.getLogger(__name__)

WIKI_API = "https://wiki.leagueoflegends.com/en-us/api.php"
MODULE_TITLE = "Module:MayhemAugmentData/data"
_ASSET_BASE = ("https://raw.communitydragon.org/latest/plugins/"
               "rcp-be-lol-game-data/global/default")

_ENTRY_RE = re.compile(
    r'\[\"([^\"]+)\"\]\s*=\s*\{(.*?)\n\t?\},', re.S)
_FIELD_RE = re.compile(r'\[\"(\w+)\"\]\s*=\s*\"((?:[^\"\\\\]|\\\\.)*)\"')

TIER_INFO = {"silver": "白銀", "gold": "黃金", "prismatic": "稜彩"}


def parse_mayhem_module(lua_text: str) -> list[dict]:
    """Lua 模組 → [{"nameEn", "desc", "tier"}](desc 已清成純文字)。"""
    out = []
    for name, body in _ENTRY_RE.findall(lua_text):
        fields = {k: v for k, v in _FIELD_RE.findall(body)}
        desc = fields.get("description", "")
        desc = desc.replace('\\"', '"').replace("\\n", "\n")
        out.append({
            "nameEn": name,
            "desc": clean_wikitext(desc),
            "tier": fields.get("tier", "").lower(),
        })
    return out


def _icon_url(path: str) -> str:
    prefix = "/lol-game-data/assets/"
    if path.lower().startswith(prefix):
        path = path[len(prefix):]
    return f"{_ASSET_BASE}/{path.lower().lstrip('/')}"


def _fetch_mayhem_codex() -> list[dict]:
    raw = fetch_json(WIKI_API, params={
        "action": "query", "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "titles": MODULE_TITLE,
        "format": "json", "formatversion": "2",
    })
    entries = parse_mayhem_module(
        raw["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"])
    if not entries:
        raise ValueError("parsed 0 mayhem augments — module structure changed?")

    # 官方 zh 名與圖示(cherry-augments,以正規化名對回)
    zh_names: dict[str, str] = {}
    icons: dict[str, str] = {}
    try:
        en_list = fetch_json(CHERRY_AUG_URL.format(loc="default"))
        zh_list = {a["id"]: a for a in fetch_json(CHERRY_AUG_URL.format(loc="zh_tw"))}
        for a in en_list:
            key = _name_key(a.get("nameTRA", ""))
            if not key:
                continue
            zh = zh_list.get(a["id"], {}).get("nameTRA", "")
            if zh:
                zh_names[key] = zh
            icon = a.get("augmentSmallIconPath", "")
            if icon:
                icons[key] = _icon_url(icon)
    except Exception as exc:  # noqa: BLE001 — 名稱對照失敗只影響 zh/圖示
        logger.warning("cherry-augments merge failed: %s", exc)

    for e in entries:
        key = _name_key(e["nameEn"])
        e["nameZh"] = zh_names.get(key)
        e["icon"] = icons.get(key)
    matched = sum(1 for e in entries if e["nameZh"])
    logger.info("mayhem codex: %d augments, %d with zh names",
                len(entries), matched)
    return entries


def get_mayhem_codex() -> cache.CacheResult:
    return cache.get_cached("mayhem_codex", _fetch_mayhem_codex)
