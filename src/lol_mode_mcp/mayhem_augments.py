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


# ------------------------------------------------- 每英雄覆寫(mayhem_balance)
# 來源:wiki「ARAM: Mayhem」頁 List of mode overrides 的 Champions 表
# (tabber 分頁;38 隻英雄,General changes / Abilities changes 兩欄)。
# Mayhem 疊加在一般 ARAM 補正之上,所以查詢時兩層都要給。

MAYHEM_PAGE = "ARAM: Mayhem"


def parse_mayhem_overrides(wikitext: str) -> dict[str, dict]:
    """→ {英雄en: {"general": [行], "abilities": [(技能標籤, [行])]}}。"""
    i = wikitext.find("List of mode overrides")
    if i < 0:
        return {}
    chunk = wikitext[i:]
    j = chunk.find("\nItems=")
    if j > 0:
        chunk = chunk[:j]
    out: dict[str, dict] = {}
    for row in chunk.split("|-"):
        m = re.search(r"\{\{ci\|([^}|]+)", row)
        if not m:
            continue
        name = m.group(1).strip()
        # 儲存格 = 以單一 '|' 開頭的行;第 1 格是英雄名,之後兩格是內容
        cells: list[list[str]] = []
        for line in row.splitlines():
            s = line.strip()
            if s.startswith("|}") or not s:
                continue
            if s.startswith("|") and not s.startswith("|+"):
                cells.append([s.lstrip("|").strip()])
            elif cells:
                cells[-1].append(s)
        entry = {"general": [], "abilities": []}
        for idx, cell in enumerate(cells[1:3]):  # general, abilities
            current: list[str] | None = None
            for raw_line in cell:
                s = raw_line.strip()
                if not s:
                    continue
                bullet = re.match(r"^(\*+)\s*(.*)$", s)
                if bullet:
                    body = clean_wikitext(bullet.group(2))
                    if not body:
                        continue
                    depth = len(bullet.group(1)) - 1
                    line_txt = "  " * depth + "- " + body
                    if idx == 0:
                        entry["general"].append(line_txt)
                    elif current is not None:
                        current.append(line_txt)
                    else:  # abilities 欄裡沒標技能的散行,掛「整體」
                        current = []
                        entry["abilities"].append(("整體", current))
                        current.append(line_txt)
                else:
                    label = clean_wikitext(s)
                    if not label or label.lower() in ("special modifiers",):
                        # General 欄的 'Special modifiers' 小標,略過
                        continue
                    if idx == 1:
                        current = []
                        entry["abilities"].append((label, current))
        if entry["general"] or entry["abilities"]:
            out[name] = entry
    return out


def _fetch_mayhem_overrides() -> dict:
    raw = fetch_json(WIKI_API, params={
        "action": "query", "prop": "revisions", "rvprop": "content|timestamp",
        "rvslots": "main", "titles": MAYHEM_PAGE,
        "format": "json", "formatversion": "2",
    })
    rev = raw["query"]["pages"][0]["revisions"][0]
    overrides = parse_mayhem_overrides(rev["slots"]["main"]["content"])
    if not overrides:
        raise ValueError("parsed 0 mayhem overrides — page structure changed?")
    logger.info("mayhem overrides parsed: %d champions", len(overrides))
    return {"overrides": overrides,
            "revision_time": rev.get("timestamp", "unknown")}


def get_mayhem_overrides() -> cache.CacheResult:
    return cache.get_cached("mayhem_overrides", _fetch_mayhem_overrides)


def do_mayhem_balance(champion: str) -> str:
    from .aram import _format_field, get_wiki_data
    from .arena_balance import ability_zh_name, build_entity_name_map
    from .champions import get_champions, get_spell_names, resolve_champion
    from .translate import translate_lines
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

    lines = [f"{champ.name_zh}({champ.name_en}) — ARAM: Mayhem 平衡"]
    problems: list[str] = []

    try:  # 第一層:一般 ARAM 補正(Mayhem 亦適用)
        aram = get_wiki_data().data["aram"].get(champ.name_en)
        lines.append("")
        lines.append("【一般 ARAM 補正(Mayhem 同樣生效)】")
        if aram:
            shown = [s for k, v in aram.items() if (s := _format_field(k, v))]
            lines += shown or ["- 全部為基準值。"]
        else:
            lines.append("- 本 patch 無 ARAM 個別調整(皆為基準值)。")
    except cache.DataUnavailableError as exc:
        problems.append(f"ARAM 資料抓取失敗:{exc}")

    revision = "?"
    try:  # 第二層:Mayhem 專屬覆寫
        result = get_mayhem_overrides()
        revision = result.data["revision_time"]
        entry = result.data["overrides"].get(champ.name_en)
        try:
            spell_names = get_spell_names().data
        except cache.DataUnavailableError:
            spell_names = None
        name_map = build_entity_name_map(spell_names, champ.id)
        lines.append("")
        lines.append("【Mayhem 專屬覆寫】(🔤 = 無把握規則翻譯,保留英文)")
        if entry is None:
            lines.append("- 沒有此英雄的 Mayhem 專屬覆寫。")
        else:
            for ln in translate_lines(entry["general"], name_map):
                lines.append(ln)
            for label, ab_lines in entry["abilities"]:
                zh = ability_zh_name(champ.id, label, spell_names)
                shown = (f"{label} {zh}" if zh and label in ("Q", "W", "E", "R", "被動")
                         else (f"{zh}({label})" if zh else label))
                lines.append(f"▸ {shown}")
                lines += ["  " + t for t in translate_lines(ab_lines, name_map)]
    except cache.DataUnavailableError as exc:
        problems.append(f"Mayhem 覆寫抓取失敗:{exc}")

    lines.append("")
    src = f"資料來源:LoL Wiki(CC BY-SA)· Mayhem 頁更新於 {revision}"
    if problems:
        src += "\n⚠️ 部分資料源失敗:" + "; ".join(problems)
    lines.append(src)
    return "\n".join(lines)
