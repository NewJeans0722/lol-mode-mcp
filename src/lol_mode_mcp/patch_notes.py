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
from .wikitext import clean_wikitext

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
}

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
ITEM_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/{locale}/item.json"


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


def _fetch_arena_notes(title: str) -> dict:
    raw = fetch_json(WIKI_API, params={
        "action": "query", "prop": "revisions", "rvprop": "content|timestamp",
        "rvslots": "main", "titles": title,
        "format": "json", "formatversion": "2",
    })
    page = raw["query"]["pages"][0]
    if "revisions" not in page:
        raise ValueError(f"patch page {title!r} not found")
    section = extract_mode_section(page["revisions"][0]["slots"]["main"]["content"])
    categories = parse_mode_changes(section) if section else []
    logger.info("patch %s arena notes: %d categories, %d entries",
                title, len(categories),
                sum(len(c["entries"]) for c in categories))
    return {"patch": title, "categories": categories}


def get_arena_notes(title: str) -> cache.CacheResult:
    return cache.get_cached(f"wiki_patch_arena_{title}",
                            lambda: _fetch_arena_notes(title))


# ------------------------------------------------------------ 中文查詢翻譯

def _fetch_item_names() -> dict[str, str]:
    """ddragon item.json → {zh_TW 名: en 名}(給「殞落之祭」這種查詢用)。"""
    ver = fetch_json(VERSIONS_URL)[0]
    zh = fetch_json(ITEM_URL.format(ver=ver, locale="zh_TW"))["data"]
    en = fetch_json(ITEM_URL.format(ver=ver, locale="en_US"))["data"]
    mapping = {zh[iid]["name"]: en[iid]["name"]
               for iid in zh if iid in en and zh[iid].get("name")}
    logger.info("item name map loaded: %d items (ddragon %s)", len(mapping), ver)
    return mapping


def get_item_names() -> cache.CacheResult:
    return cache.get_cached("item_names", _fetch_item_names)


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
        items = get_item_names().data
        hits = [en for zh, en in items.items()
                if query == zh or (len(query) >= 2 and query in zh)]
        if len(set(hits)) == 1:
            terms.add(hits[0])
    except cache.DataUnavailableError:
        pass
    return terms


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


def do_arena_patch_notes(patch: str = "latest", query: str = "") -> str:
    try:
        titles: list[str] = get_patch_titles().data
    except cache.DataUnavailableError as exc:
        return f"❌ 查詢失敗:無法取得 patch 頁清單(wiki 連線失敗)。技術細節:{exc}"

    if patch.strip().lower() in ("", "latest", "最新"):
        candidates = titles[:4]  # 最新頁可能還沒有 Arena 段落,往前找
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
            result = get_arena_notes(title)
        except cache.DataUnavailableError as exc:
            return f"❌ 查詢失敗:無法取得 {title} 的 patch 頁。技術細節:{exc}"
        if result.data["categories"]:
            notes = result.data
            stale = result.is_stale
            break
    if notes is None:
        if len(candidates) == 1:
            return (f"📋 {candidates[0]} 的 patch 頁裡**沒有競技場(Arena)段落**"
                    f"(該版可能沒有競技場改動)。")
        return (f"📋 最近幾版({'、'.join(candidates)})的 patch 頁都沒有"
                f"競技場(Arena)段落。")

    categories = notes["categories"]
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
                    older = get_arena_notes(title)
                except cache.DataUnavailableError:
                    break
                hit = _filter_categories(older.data["categories"], terms)
                if hit:
                    fallback_note = (f"{notes['patch']}(最新版)沒有提到"
                                     f"「{query}」;以下是最近一次改動:")
                    notes, filtered = older.data, hit
                    stale = older.is_stale
                    break
        if not filtered:
            cats = "、".join(_category_label(c["category"]) for c in categories)
            terms_hint = "、".join(sorted(terms - {query.strip()}))
            msg = (f"📋 {notes['patch']} 的競技場改動裡**沒有提到**「{query}」")
            if terms_hint:
                msg += f"(也試過英文名:{terms_hint})"
            if len(candidates) > 1:
                msg += f",往前 {min(len(titles), 8) - 1} 版也沒有"
            return msg + f"。該版有改動的分類:{cats}。(提示:可不帶 query 看整版改動)"
        categories = filtered
        matched_terms = terms - {query.strip()}

    lines = [f"📋 競技場(Arena)patch 改動 — {notes['patch']}"]
    if fallback_note:
        lines.insert(0, f"ℹ️ {fallback_note}")
    if query.strip():
        shown = f"「{query}」"
        if matched_terms:
            shown += f"(對應英文:{'、'.join(sorted(matched_terms))})"
        lines.append(f"只顯示與 {shown} 相關的條目")
    lines += ["改動格式為「舊值 ⇒ 新值」(取自英文 wiki,術語保留原文)", ""]

    for c in categories:
        lines.append(f"【{_category_label(c['category'])}】")
        for e in c["entries"]:
            if e["lines"]:
                lines.append(f"▸ {e['name']}")
                lines += ["  " + ln for ln in e["lines"]]
            else:
                lines.append(f"- {e['name']}")  # 無子項的單行改動
        lines.append("")

    src = "📌 資料:LoL Wiki(CC BY-SA)"
    if patch.strip().lower() in ("", "latest", "最新"):
        others = [t for t in titles[:5] if t != notes["patch"]]
        src += f"\n💡 也可以用 patch 參數查舊版,例如:{'、'.join(others[:3])}"
    if stale:
        src += "\n⚠️ 注意:資料更新失敗,以上為上次成功抓取的快取,可能過期。"
    lines.append(src)
    return "\n".join(lines)
