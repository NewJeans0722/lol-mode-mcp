"""競技場逐 patch 改動(相對上一版的 nerf/buff)。

資料源:wiki 各 patch 頁(V26.13 等)的「== Arena ==」段落。
該段落格式很乾淨 —— 三層 bullet:
    * Champions            ← 分類(Augments/Champions/Items/Guests of Honor…)
    ** Elise               ← 條目(英雄/強化/裝備名)
    *** Passive Damage: 12 - 42 ⇒ 15 - 45   ← 改動內容(舊 ⇒ 新)
幾乎沒有模板,少量的交給 wikitext.clean_wikitext。

「最新 patch」的找法:MediaWiki allpages 枚舉 V 開頭頁面,
過濾 ^V\\d\\d\\.\\d\\d$ 取最大(年.次)—— 不從 cdragon 版本推算,
因為 ddragon 主版號(16.x)和 wiki 頁名(V26.x)是兩套編號。
最新頁若還沒有 Arena 段落(patch 日當天可能先建頁),往前找。

刻意不做的事:不自動判定每行是 buff 還是 nerf ——「冷卻 60 ⇒ 15」
是增益還是削弱取決於機制,亂猜會錯,寧可原樣呈現「舊 ⇒ 新」。
"""

from __future__ import annotations

import logging
import re

from . import cache
from .arena import get_arena_data
from .champions import get_champions, resolve_champion
from .http_util import fetch_json
from .translate import translate_lines
from .wikitext import clean_wikitext, translate_annotations_en

logger = logging.getLogger(__name__)

WIKI_API = "https://wiki.leagueoflegends.com/en-us/api.php"

_PATCH_TITLE_RE = re.compile(r"^V(\d{2})\.(\d{2})$")

# 分類的中文對照(wiki 出現過的;沒列到的原樣顯示)
CATEGORY_LABELS = {
    "general": "一般",
    "augments": "強化",
    "champions": "英雄",
    "items": "裝備",
    "guests of honor": "貴賓(Guest of Honor)",
    "anvils": "鐵砧",
    "systems": "系統",
    "summoner spells": "召喚師技能",
    "runes": "符文",
    "monsters": "野怪",
}

# 查詢範圍:patch 頁上的段落。arena/mayhem 是三層 bullet;
# general(一般對戰)是多個段落、以「;{{ci|英雄}}」為條目。
SCOPES = {
    "arena": {"zh": "競技場(Arena)", "en": "Arena"},
    "general": {"zh": "一般對戰(召喚峽谷)", "en": "General (Summoner's Rift)"},
    "mayhem": {"zh": "ARAM: Mayhem", "en": "ARAM: Mayhem"},
}
_GENERAL_SECTIONS = ["Champions", "Items", "Summoner Spells", "Runes", "Monsters"]

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
ITEM_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/{locale}/item.json"
# ARAM: Mayhem 強化的雙語來源(cdragon 遊戲資料;638 筆、ARAM_ 前綴)
CHERRY_AUG_URL = ("https://raw.communitydragon.org/latest/plugins/"
                  "rcp-be-lol-game-data/global/{loc}/v1/cherry-augments.json")


# ------------------------------------------------------------ patch 頁清單

def _fetch_patch_titles() -> list[str]:
    """全部 VYY.MM 形式的 patch 頁,由新到舊。"""
    raw = fetch_json(WIKI_API, params={
        "action": "query", "list": "allpages", "apprefix": "V2",
        "aplimit": "500", "format": "json", "formatversion": "2",
    })
    titles = []
    for p in raw["query"]["allpages"]:
        m = _PATCH_TITLE_RE.match(p["title"])
        if m:
            titles.append((int(m.group(1)), int(m.group(2)), p["title"]))
    if not titles:
        raise ValueError("no VYY.MM patch pages found — wiki naming may have changed")
    titles.sort(reverse=True)
    return [t for _, _, t in titles]


def get_patch_titles() -> cache.CacheResult:
    return cache.get_cached("wiki_patch_titles", _fetch_patch_titles)


def normalize_patch(patch: str) -> str | None:
    """'26.13' / 'V26.13' / '26.13版' → 'V26.13';認不出回 None。"""
    m = re.search(r"(\d{2})\.(\d{1,2})", patch)
    return f"V{m.group(1)}.{int(m.group(2)):02d}" if m else None


# ------------------------------------------------------------ 段落解析

def extract_mode_section(wikitext: str, mode: str = "Arena") -> str | None:
    """取出 '== Arena ==' 到下一個二級標題之間的內容(標題等號數容錯)。"""
    m = re.search(rf"^==+\s*{re.escape(mode)}\s*=+\s*$", wikitext, re.M)
    if not m:
        return None
    rest = wikitext[m.end():]
    nxt = re.search(r"^==[^=]", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def parse_mode_changes(section: str) -> list[dict]:
    """bullet 三層結構 → [{"category", "entries": [{"name", "lines"}]}]。"""
    categories: list[dict] = []
    cat: dict | None = None
    entry: dict | None = None
    for line in section.splitlines():
        m = re.match(r"^(\*+)\s*(.*)", line.strip())
        if not m:
            continue
        depth, body = len(m.group(1)), clean_wikitext(m.group(2))
        if not body:
            continue
        if depth == 1:
            cat = {"category": body, "entries": []}
            categories.append(cat)
            entry = None
        elif depth == 2:
            if cat is None:  # 沒有分類就直接開條目(防禦性)
                cat = {"category": "", "entries": []}
                categories.append(cat)
            entry = {"name": body, "lines": []}
            cat["entries"].append(entry)
        else:
            if entry is None:
                continue  # 沒有條目的三層行,結構異常,略過
            entry["lines"].append("  " * (depth - 3) + "- " + body)
    return categories


def parse_dl_section(section: str) -> list[dict]:
    """一般對戰段落:「;{{ci|英雄}}」開條目、bullet 是改動內容。"""
    entries: list[dict] = []
    cur: dict | None = None
    for line in section.splitlines():
        s = line.strip()
        if s.startswith(";"):
            name = clean_wikitext(s.lstrip(";").strip())
            if name:
                cur = {"name": name, "lines": []}
                entries.append(cur)
            continue
        m = re.match(r"^(\*+)\s*(.*)", s)
        if not m:
            continue
        body = clean_wikitext(m.group(2))
        if not body:
            continue
        if cur is None:
            cur = {"name": "", "lines": []}
            entries.append(cur)
        cur["lines"].append("  " * (len(m.group(1)) - 1) + "- " + body)
    return entries


def _fetch_patch_page(title: str) -> dict:
    """一次抓 patch 頁,三個 scope 一起解析、一起快取。"""
    raw = fetch_json(WIKI_API, params={
        "action": "query", "prop": "revisions", "rvprop": "content|timestamp",
        "rvslots": "main", "titles": title,
        "format": "json", "formatversion": "2",
    })
    page = raw["query"]["pages"][0]
    if "revisions" not in page:
        raise ValueError(f"patch page {title!r} not found")
    content = page["revisions"][0]["slots"]["main"]["content"]

    scopes: dict[str, list[dict]] = {}
    sec = extract_mode_section(content, "Arena")
    scopes["arena"] = parse_mode_changes(sec) if sec else []
    sec = extract_mode_section(content, "ARAM: Mayhem")
    scopes["mayhem"] = parse_mode_changes(sec) if sec else []
    general = []
    for name in _GENERAL_SECTIONS:
        sec = extract_mode_section(content, name)
        if sec:
            entries = parse_dl_section(sec)
            if entries:
                general.append({"category": name, "entries": entries})
    scopes["general"] = general

    logger.info("patch %s parsed: arena %d cats / general %d cats / mayhem %d cats",
                title, len(scopes["arena"]), len(scopes["general"]),
                len(scopes["mayhem"]))
    return {"patch": title, "scopes": scopes}


def get_patch_data(title: str) -> cache.CacheResult:
    return cache.get_cached(f"wiki_patch_{title}",
                            lambda: _fetch_patch_page(title))


# ------------------------------------------------------------ 中文查詢翻譯

def _fetch_item_names() -> dict[str, dict[str, str]]:
    """ddragon item.json → 雙向對照:{zh_to_en, en_to_zh(key 小寫)}。"""
    ver = fetch_json(VERSIONS_URL)[0]
    zh = fetch_json(ITEM_URL.format(ver=ver, locale="zh_TW"))["data"]
    en = fetch_json(ITEM_URL.format(ver=ver, locale="en_US"))["data"]
    zh_to_en: dict[str, str] = {}
    en_to_zh: dict[str, str] = {}
    for iid, item_zh in zh.items():
        item_en = en.get(iid)
        if not item_en or not item_zh.get("name"):
            continue
        zh_to_en[item_zh["name"]] = item_en["name"]
        en_to_zh[item_en["name"].lower()] = item_zh["name"]
    logger.info("item name map loaded: %d items (ddragon %s)", len(zh_to_en), ver)
    return {"zh_to_en": zh_to_en, "en_to_zh": en_to_zh}


def get_item_names() -> cache.CacheResult:
    return cache.get_cached("item_names", _fetch_item_names)


def _fetch_mayhem_augment_names() -> dict[str, str]:
    """cherry-augments.json → {en 名(正規化): 台服名},給 Mayhem scope 用。"""
    en = fetch_json(CHERRY_AUG_URL.format(loc="default"))
    zh = fetch_json(CHERRY_AUG_URL.format(loc="zh_tw"))
    zh_by_id = {a["id"]: a.get("nameTRA", "") for a in zh}
    mapping = {}
    for a in en:
        name_en, name_zh = a.get("nameTRA", ""), zh_by_id.get(a["id"], "")
        if name_en and name_zh:
            mapping[_name_key(name_en)] = name_zh
    logger.info("mayhem augment name map loaded: %d entries", len(mapping))
    return mapping


def get_mayhem_augment_names() -> cache.CacheResult:
    return cache.get_cached("mayhem_augment_names", _fetch_mayhem_augment_names)


def _translate_query(query: str) -> set[str]:
    """中文(或英文)查詢字 → 可能的英文名集合;翻不出就原樣。"""
    terms = {query}
    try:  # 英雄
        champ, _ = resolve_champion(query, get_champions().data)
        if champ:
            terms.add(champ.name_en)
    except cache.DataUnavailableError:
        pass
    try:  # 強化
        hits = [a.name_en for a in get_arena_data().data.augments
                if query == a.name_zh or query == a.name_en
                or (len(query) >= 2 and query in a.name_zh)]
        if len(set(hits)) == 1:
            terms.add(hits[0])
    except cache.DataUnavailableError:
        pass
    try:  # 裝備
        items = get_item_names().data["zh_to_en"]
        hits = [en for zh, en in items.items()
                if query == zh or (len(query) >= 2 and query in zh)]
        if len(set(hits)) == 1:
            terms.add(hits[0])
    except cache.DataUnavailableError:
        pass
    return terms


# ------------------------------------------------------------ 台服名對照
# 條目名(Elise / Eclipse / Buff Buddies)→ 台服官方譯名。
# 來源都是遊戲內字串:英雄與裝備用 ddragon zh_TW、強化用 cdragon zh_tw,
# 不做機器翻譯;查不到就保留英文。

_PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")  # "Kayn (Shadow Assassin)" 的尾註


def _name_key(name: str) -> str:
    """比對用正規化:小寫 + 去掉空白與標點(wiki "Hivemind" ↔ 遊戲 "Hive Mind")。"""
    return re.sub(r"[^0-9a-z]+", "", name.lower())


def _build_localizer() -> dict[str, dict]:
    """三份對照表(key 已正規化);任一來源失敗只影響該類(名字退回英文)。"""
    champs: dict[str, tuple[str, str]] = {}
    try:
        for c in get_champions().data:
            champs[_name_key(c.name_en)] = (c.name_zh, c.icon_url)
        if _name_key("Nunu & Willump") in champs:  # wiki 有時簡寫
            champs.setdefault("nunu", champs[_name_key("Nunu & Willump")])
    except cache.DataUnavailableError:
        pass
    augments: dict[str, str] = {}
    try:
        for a in get_arena_data().data.augments:
            if a.name_en and a.name_zh:
                augments[_name_key(a.name_en)] = a.name_zh
    except cache.DataUnavailableError:
        pass
    items: dict[str, str] = {}
    try:
        items = {_name_key(en): zh
                 for en, zh in get_item_names().data["en_to_zh"].items()}
    except cache.DataUnavailableError:
        pass
    mayhem: dict[str, str] = {}
    try:
        mayhem = get_mayhem_augment_names().data
    except cache.DataUnavailableError:
        pass
    return {"champions": champs, "augments": augments, "items": items,
            "mayhem_augments": mayhem}


# 分類 → 先查哪幾張表(未知分類三張都試)
_CATEGORY_TABLES = {
    "champions": ["champions"],
    "guests of honor": ["champions"],
    "items": ["items"],
    "anvils": ["items"],
    "augments": ["augments", "mayhem_augments"],
    "summoner spells": ["items"],  # 沒有專屬表,裝備表偶爾命中(如 Flash 類)
}


def localize_entry(name: str, category: str,
                   loc: dict[str, dict]) -> tuple[str | None, str | None]:
    """條目名 → (台服名, 英雄圖示 URL);查不到 → (None, None)。"""
    keys = [_name_key(name), _name_key(_PAREN_SUFFIX_RE.sub("", name))]
    for kind in _CATEGORY_TABLES.get(category.lower(),
                                     ["augments", "items", "champions"]):
        table = loc.get(kind, {})
        for key in keys:
            hit = table.get(key)
            if hit:
                if kind == "champions":
                    return hit  # (zh, icon)
                return hit, None
    return None, None


def enrich_categories(categories: list[dict]) -> list[dict]:
    """每個條目補 nameZh、icon、linesEn 與 linesZh(規則式翻譯)。"""
    loc = _build_localizer()
    out = []
    for c in categories:
        entries = []
        for e in c["entries"]:
            zh, icon = localize_entry(e["name"], c["category"], loc)
            entries.append({**e, "nameZh": zh, "icon": icon,
                            "linesEn": [translate_annotations_en(ln)
                                        for ln in e["lines"]],
                            "linesZh": translate_lines(e["lines"])})
        out.append({"category": c["category"], "entries": entries})
    return out


# ------------------------------------------------------------ tool 實作

def _category_label(cat: str) -> str:
    zh = CATEGORY_LABELS.get(cat.lower())
    return f"{zh} {cat}" if zh else cat


def _filter_categories(categories: list[dict], terms: set[str]) -> list[dict]:
    lows = {t.lower() for t in terms}
    out = []
    for c in categories:
        entries = [e for e in c["entries"]
                   if any(t in e["name"].lower() for t in lows)]
        if entries:
            out.append({"category": c["category"], "entries": entries})
    return out


def do_patch_notes(scope: str = "arena", patch: str = "latest",
                   query: str = "", locale: str = "zh_tw") -> str:
    en = locale.strip().lower() == "en_us"
    scope = scope.strip().lower() or "arena"
    if scope not in SCOPES:
        return (f"看不懂 scope「{scope}」,可用:arena(競技場,預設)、"
                f"general(一般對戰)、mayhem(ARAM: Mayhem)。")
    scope_zh = SCOPES[scope]["zh"]
    scope_name = SCOPES[scope]["en"] if en else scope_zh
    try:
        titles: list[str] = get_patch_titles().data
    except cache.DataUnavailableError as exc:
        return f"❌ 查詢失敗:無法取得 patch 頁清單(wiki 連線失敗)。技術細節:{exc}"

    if patch.strip().lower() in ("", "latest", "最新"):
        candidates = titles[:4]  # 最新頁可能還沒有該段落,往前找
    else:
        wanted = normalize_patch(patch)
        if wanted is None:
            return (f"看不懂 patch「{patch}」,請用「26.13」或「V26.13」格式。"
                    f"最近的 patch:{'、'.join(titles[:5])}")
        if wanted not in titles:
            return (f"wiki 上找不到 patch 頁「{wanted}」。"
                    f"最近的 patch:{'、'.join(titles[:5])}")
        candidates = [wanted]

    notes = None
    stale = False
    for title in candidates:
        try:
            result = get_patch_data(title)
        except cache.DataUnavailableError as exc:
            return f"❌ 查詢失敗:無法取得 {title} 的 patch 頁。技術細節:{exc}"
        if result.data["scopes"].get(scope):
            notes = result.data
            stale = result.is_stale
            break
    if notes is None:
        if len(candidates) == 1:
            return (f"📋 {candidates[0]} 的 patch 頁裡**沒有{scope_zh}段落**"
                    f"(該版可能沒有此範圍的改動)。")
        return (f"📋 最近幾版({'、'.join(candidates)})的 patch 頁都沒有"
                f"{scope_zh}段落。")

    categories = notes["scopes"][scope]
    matched_terms: set[str] = set()
    fallback_note = ""
    if query.strip():
        terms = _translate_query(query.strip())
        filtered = _filter_categories(categories, terms)
        if not filtered and len(candidates) > 1:
            # 查最新版沒中:往前幾版找「最近一次改動」
            for title in titles[:8]:
                if title == notes["patch"]:
                    continue
                try:
                    older = get_patch_data(title)
                except cache.DataUnavailableError:
                    break
                hit = _filter_categories(older.data["scopes"].get(scope, []),
                                         terms)
                if hit:
                    fallback_note = (
                        f"No mention of \"{query}\" in {notes['patch']} "
                        f"(latest); showing its most recent change:"
                        if en else
                        f"{notes['patch']}(最新版)沒有提到「{query}」;"
                        f"以下是最近一次改動:")
                    notes, filtered = older.data, hit
                    stale = older.is_stale
                    break
        if not filtered:
            cats = "、".join(_category_label(c["category"]) for c in categories)
            terms_hint = "、".join(sorted(terms - {query.strip()}))
            msg = (f"📋 {notes['patch']} 的{scope_zh}改動裡**沒有提到**「{query}」")
            if terms_hint:
                msg += f"(也試過英文名:{terms_hint})"
            if len(candidates) > 1:
                msg += f",往前 {min(len(titles), 8) - 1} 版也沒有"
            return msg + f"。該版有改動的分類:{cats}。(提示:可不帶 query 看整版改動)"
        categories = filtered
        matched_terms = terms - {query.strip()}

    if en:
        lines = [f"📋 {scope_name} patch changes — {notes['patch']}"]
        if fallback_note:
            lines.insert(0, f"ℹ️ {fallback_note}")
        if query.strip():
            lines.append(f"Showing only entries matching \"{query}\"")
        lines += ["Format: old value ⇒ new value (from the English wiki)", ""]
    else:
        categories = enrich_categories(categories)  # 補台服名 + 規則式翻譯
        lines = [f"📋 {scope_zh} patch 改動 — {notes['patch']}"]
        if fallback_note:
            lines.insert(0, f"ℹ️ {fallback_note}")
        if query.strip():
            shown = f"「{query}」"
            if matched_terms:
                shown += f"(對應英文:{'、'.join(sorted(matched_terms))})"
            lines.append(f"只顯示與 {shown} 相關的條目")
        lines += ["名稱為台服官方譯名;🔤 = 無把握規則翻譯的句子,保留英文原文", ""]

    for c in categories:
        lines.append(c["category"] if en
                     else f"【{_category_label(c['category'])}】")
        for e in c["entries"]:
            name = e["name"]
            if not en and e.get("nameZh"):
                name = f"{e['nameZh']} {e['name']}"
            if en:
                entry_lines = [translate_annotations_en(ln) for ln in e["lines"]]
            else:
                entry_lines = e.get("linesZh") or translate_lines(e["lines"])
            if entry_lines:
                lines.append(f"▸ {name}")
                lines += ["  " + ln for ln in entry_lines]
            else:
                lines.append(f"- {name}")  # 無子項的單行改動
        lines.append("")

    src = ("📌 Source: LoL Wiki (CC BY-SA)" if en
           else "📌 資料:LoL Wiki(CC BY-SA)")
    if patch.strip().lower() in ("", "latest", "最新"):
        others = [t for t in titles[:5] if t != notes["patch"]]
        if others:
            src += (f"\n💡 Older patches via the patch param: {', '.join(others[:3])}"
                    if en else
                    f"\n💡 也可以用 patch 參數查舊版,例如:{'、'.join(others[:3])}")
    if stale:
        src += ("\n⚠️ Refresh failed; showing last cached data (may be outdated)."
                if en else
                "\n⚠️ 注意:資料更新失敗,以上為上次成功抓取的快取,可能過期。")
    lines.append(src)
    return "\n".join(lines)
