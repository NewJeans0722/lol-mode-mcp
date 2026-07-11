"""ARAM: Mayhem 強化圖鑑資料。

來源組合:
- 名稱/稀有度/圖示:cdragon cherry-augments.json(zh_tw + default,
  官方遊戲字串,ARAM_ 前綴)
- 英文說明:wiki Module:MayhemAugmentData/data(Mayhem 專屬、數值正確,
  英文 wikitext 用 wikitext.clean_wikitext 化簡)
- 中文說明(descZh)三層來源,優先序:
  1. 遊戲字串表 zh_tw 的官方說明(cherry_{name}_summary),僅在「無
     @佔位符@」時採用 —— 無佔位符=無數值,故 Arena 版說明對 Mayhem
     也正確,是官方原文最高品質。
  2. 對英文說明跑規則式翻譯(translate.translate_description)。
  3. 都不行 → 保留英文,UI/tool 註明。
  ⚠️ 帶佔位符的官方 zh 需要 Mayhem dataValues(遊戲未提供),硬用
  Arena 數值可能錯,故不採用;那些走第 2/3 層(英文 wiki 數值正確)。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from . import cache
from .formatting import render_description
from .http_util import fetch_json
from .patch_notes import CHERRY_AUG_URL, _name_key
from .wikitext import clean_wikitext

logger = logging.getLogger(__name__)

WIKI_API = "https://wiki.leagueoflegends.com/en-us/api.php"
MODULE_TITLE = "Module:MayhemAugmentData/data"
_ASSET_BASE = ("https://raw.communitydragon.org/latest/plugins/"
               "rcp-be-lol-game-data/global/default")
_STRINGTABLE_URL = ("https://raw.communitydragon.org/latest/game/zh_tw/"
                    "data/menu/en_us/lol.stringtable.json")
_SUMMARY_KEY_RE = re.compile(
    r"^(?:kiwi_aram_|kiwi_|cherry_)([a-z0-9]+)_summary$")

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
        desc = clean_wikitext(desc)
        # clean_wikitext 只處理模板/連結,HTML 標籤在這裡清
        desc = re.sub(r"<br\s*/?>", "\n", desc, flags=re.I)
        desc = re.sub(r"</?[a-zA-Z][^>]*>", "", desc)
        out.append({
            "nameEn": name,
            "desc": desc.strip(),
            "tier": fields.get("tier", "").lower(),
        })
    return out


_CURATED_PATH = Path(__file__).resolve().parent / "data" / "mayhem_zh.json"
_curated: dict[str, str] | None = None


def _load_curated() -> dict[str, str]:
    """人工整段中文翻譯,以英文強化名為 key(穩定,不受 wiki 改字影響)。"""
    global _curated
    if _curated is None:
        try:
            _curated = json.loads(_CURATED_PATH.read_text(encoding="utf-8"))
        except OSError:
            _curated = {}
    return _curated


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

    # 官方 zh 名、圖示、內部名(cherry-augments,以正規化名對回)
    zh_names: dict[str, str] = {}
    icons: dict[str, str] = {}
    base_names: dict[str, str] = {}  # 正規化英文名 → 字串表內部名(去 ARAM_)
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
            nid = a.get("augmentNameId", "")
            if nid:
                base_names[key] = re.sub(r"[^a-z0-9]", "",
                                         nid.replace("ARAM_", "").lower())
    except Exception as exc:  # noqa: BLE001 — 名稱對照失敗只影響 zh/圖示
        logger.warning("cherry-augments merge failed: %s", exc)

    # 官方 zh 說明索引:內部名 → summary 原文(遊戲字串表)
    official: dict[str, str] = {}
    try:
        st = fetch_json(_STRINGTABLE_URL)["entries"]
        for k, v in st.items():
            m = _SUMMARY_KEY_RE.match(k)
            if m:
                official.setdefault(m.group(1), v)
    except Exception as exc:  # noqa: BLE001 — 官方 zh 說明拿不到就走規則翻譯
        logger.warning("stringtable fetch failed: %s", exc)

    from .arena_balance import build_entity_name_map
    from .translate import translate_description
    name_map = build_entity_name_map()
    for e in entries:
        key = _name_key(e["nameEn"])
        e["nameZh"] = zh_names.get(key)
        e["icon"] = icons.get(key)
        if e["nameZh"]:
            name_map[e["nameEn"].lower()] = e["nameZh"]

    curated = _load_curated()  # 人工整段翻譯(以英文強化名為 key)
    n_official = n_rule = n_curated = 0
    for e in entries:
        key = _name_key(e["nameEn"])
        raw_zh = official.get(base_names.get(key, ""))
        if e["nameEn"] in curated:
            e["descZh"] = curated[e["nameEn"]]
            e["descComplete"] = True
            n_curated += 1
        elif raw_zh and "@" not in raw_zh:
            # 官方 zh(無佔位符):清標籤後直接用,最高品質
            e["descZh"] = render_description(raw_zh, {}, locale="zh_tw")
            e["descComplete"] = True
            n_official += 1
        else:
            zh, complete = translate_description(e["desc"], name_map)
            e["descZh"] = zh
            e["descComplete"] = complete
            if complete:
                n_rule += 1
    logger.info("mayhem codex: %d augments, %d zh names, descZh: "
                "%d curated / %d official / %d rule / %d english",
                len(entries), sum(1 for e in entries if e["nameZh"]),
                n_curated, n_official, n_rule,
                len(entries) - n_curated - n_official - n_rule)
    return entries


def get_mayhem_codex() -> cache.CacheResult:
    return cache.get_cached("mayhem_codex", _fetch_mayhem_codex)


# ------------------------------------------------- 圖鑑搜尋(tool 用)
# 與 arena.py 的評分策略一致:同名 100 > 名字包含 90/80 > 說明命中 40
# > difflib。Mayhem 說明只有英文(wiki),輸出會註明。

TIER_LABEL = {"silver": ("⚪", "白銀", "Silver"),
              "gold": ("🟡", "黃金", "Gold"),
              "prismatic": ("🌈", "稜彩", "Prismatic")}


def score_entry(query: str, e: dict) -> float:
    from difflib import SequenceMatcher

    from .arena import _norm
    q = _norm(query)
    if not q:
        return 0.0
    names = [_norm(e.get("nameZh") or ""), _norm(e["nameEn"])]
    if q in names:
        return 100.0
    if any(q in n for n in names if n):
        return 90.0
    if any(n in q for n in names if len(n) >= 2):
        return 80.0
    desc_hit = q in _norm(e["desc"])
    fuzz = max(SequenceMatcher(None, q, n).ratio() for n in names if n)
    return max(40.0 if desc_hit else 0.0, fuzz * 75.0)


def format_mayhem_detail(e: dict, locale: str) -> str:
    icon, zh, en_label = TIER_LABEL.get(e["tier"], ("", "未知", "Unknown"))
    name_zh = e.get("nameZh") or e["nameEn"]
    if locale == "zh_tw":
        head = f"{icon} {zh} Mayhem 強化:{name_zh}({e['nameEn']})"
        body = e.get("descZh") or e["desc"]
        note = ("(部分說明為規則式翻譯,未完整翻出處保留英文;數值以英文 wiki 為準)"
                if not e.get("descComplete") else "")
    else:
        head = f"{icon} {en_label} Mayhem Augment: {e['nameEn']}"
        body = e["desc"]
        note = ""
    lines = [head, "─" * 30, body or "(無說明文字)"]
    if note:
        lines.append(note)
    return "\n".join(lines)


def _mayhem_source(result: cache.CacheResult, locale: str) -> str:
    stale = ""
    if result.is_stale:
        stale = "\n⚠️ 注意:資料更新失敗,以下為快取,可能過期。"
    return (f"資料來源:LoL Wiki(CC BY-SA)+ CommunityDragon · 抓取於 "
            f"{result.fetched_at_str}{stale}")


def do_get_mayhem_augment(query: str, locale: str = "zh_tw") -> str:
    try:
        result = get_mayhem_codex()
    except cache.DataUnavailableError as exc:
        return f"❌ 查詢失敗:無法取得 Mayhem 強化資料。技術細節:{exc}"
    scored = sorted(((score_entry(query, e), e) for e in result.data),
                    key=lambda t: -t[0])
    matches = [(s, e) for s, e in scored[:5] if s > 0]
    if not matches:
        return f"找不到與「{query}」相關的 ARAM Mayhem 強化。"
    best_s, best = matches[0]
    lines = []
    if best_s < 80:
        lines.append(f"沒有完全符合「{query}」的 Mayhem 強化,最接近的是:")
        lines.append("")
    lines.append(format_mayhem_detail(best, locale))
    others = [(s, e) for s, e in matches[1:] if s >= 40]
    if others:
        lines += ["", "其他候選:"]
        for _, e in others:
            lines.append(f"- {e.get('nameZh') or e['nameEn']}({e['nameEn']})")
    # 競技場若有同名強化,提示模式差異
    try:
        from .arena import _norm, get_arena_data
        twin = next((a for a in get_arena_data().data.augments
                     if _norm(a.name_en) == _norm(best["nameEn"])), None)
        if twin:
            lines += ["", f"提示:競技場也有「{twin.name_zh}」,數值/效果可能不同"
                          "(用 mode=\"arena\" 查)。"]
    except cache.DataUnavailableError:
        pass
    lines += ["", _mayhem_source(result, locale)]
    return "\n".join(lines)


def do_list_mayhem_augments(tier: str = "all", locale: str = "zh_tw") -> str:
    from .arena import _TIER_ALIASES
    from .formatting import first_sentence
    try:
        result = get_mayhem_codex()
    except cache.DataUnavailableError as exc:
        return f"❌ 查詢失敗:無法取得 Mayhem 強化資料。技術細節:{exc}"
    slug_by_rarity = {0: "silver", 1: "gold", 2: "prismatic"}
    want = tier.strip().lower()
    want_slug = None
    if want not in ("", "all", "全部"):
        rarity = _TIER_ALIASES.get(want)
        want_slug = slug_by_rarity.get(rarity, want)
    lines = ["ARAM Mayhem 海克斯強化清單",
             "(中文說明優先取官方遊戲字串,其餘規則式翻譯;數值以英文 wiki 為準)", ""]
    for slug in ("silver", "gold", "prismatic"):
        if want_slug and slug != want_slug:
            continue
        group = [e for e in result.data if e["tier"] == slug]
        if not group:
            continue
        icon, zh, _ = TIER_LABEL[slug]
        lines.append(f"## {icon} {zh} — {len(group)} 個")
        for e in sorted(group, key=lambda x: x.get("nameZh") or x["nameEn"]):
            summary = first_sentence(e.get("descZh") or e["desc"])
            lines.append(f"- **{e.get('nameZh') or e['nameEn']}**({e['nameEn']})"
                         f":{summary}")
        lines.append("")
    lines.append(_mayhem_source(result, locale))
    return "\n".join(lines)


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
