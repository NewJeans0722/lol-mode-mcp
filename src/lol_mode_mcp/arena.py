"""競技場(Arena)海克斯強化:抓取、雙語索引、模糊搜尋、排版輸出。

資料源:CommunityDragon 整理版 arena JSON(en_us + zh_tw 都抓,
中英文名都能搜)。patch 版本另抓 content-metadata.json 標明,
確保使用者知道資料對應哪個版本。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from . import cache
from .formatting import first_sentence, render_description
from .http_util import fetch_json

logger = logging.getLogger(__name__)

ARENA_URL = "https://raw.communitydragon.org/latest/cdragon/arena/{locale}.json"
META_URL = "https://raw.communitydragon.org/latest/content-metadata.json"

SUPPORTED_LOCALES = {"zh_tw", "en_us"}

# rarity 欄位實測值:0/1/2 對應遊戲內三種稀有度;
# 4 是稜彩道具、鐵砧、特殊獎勵類(神羊喘息、冰霜之錘等),brief 沒提到,
# 實際資料裡有 25 筆,歸類為「特殊」。
RARITY_INFO = {
    0: ("白銀", "Silver", "⚪"),
    1: ("黃金", "Gold", "🟡"),
    2: ("稜彩", "Prismatic", "🌈"),
    4: ("特殊", "Special", "📦"),
}
_TIER_ALIASES = {
    "silver": 0, "白銀": 0, "白银": 0, "银": 0, "銀": 0,
    "gold": 1, "黃金": 1, "黄金": 1, "金": 1,
    "prismatic": 2, "稜彩": 2, "棱彩": 2, "彩": 2,
    "special": 4, "特殊": 4, "道具": 4, "item": 4, "anvil": 4, "鐵砧": 4,
}


@dataclass
class Augment:
    id: int
    api_name: str
    rarity: int
    name_zh: str
    name_en: str
    desc_zh: str  # 已代入數值、清完標籤的純文字
    desc_en: str

    def name(self, locale: str) -> str:
        return self.name_zh if locale == "zh_tw" else self.name_en

    def desc(self, locale: str) -> str:
        return self.desc_zh if locale == "zh_tw" else self.desc_en

    def rarity_label(self, locale: str) -> str:
        zh, en, icon = RARITY_INFO.get(self.rarity, ("未知", "Unknown", "❓"))
        return f"{icon} {zh if locale == 'zh_tw' else en}"


@dataclass
class ArenaData:
    augments: list[Augment]
    patch: str
    by_id: dict[int, Augment] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {a.id: a for a in self.augments}


def _pick_text(raw: dict) -> str:
    """優先用 desc(佔位符與 dataValues 對得上),沒有才退 tooltip。"""
    return raw.get("desc") or raw.get("tooltip") or ""


def _fetch_arena_data() -> ArenaData:
    """抓 en + zh 兩份 JSON 與 patch 版本,以 augment id 合併成雙語索引。"""
    en = fetch_json(ARENA_URL.format(locale="en_us"))
    try:
        zh = fetch_json(ARENA_URL.format(locale="zh_tw"))
    except Exception as exc:  # zh_tw 理論上存在,但 patch 剛更新時可能缺
        logger.warning("zh_tw arena data unavailable, falling back to en_us: %s", exc)
        zh = en

    try:
        meta = fetch_json(META_URL)
        raw_version = str(meta.get("version", "unknown"))
        # 原始格式像 "16.13.7915903+branch...",只留人看得懂的 "16.13"
        m = re.match(r"(\d+\.\d+)", raw_version)
        patch = m.group(1) if m else raw_version
    except Exception as exc:
        logger.warning("content-metadata fetch failed: %s", exc)
        patch = "unknown"

    zh_by_id = {a["id"]: a for a in zh.get("augments", [])}
    augments: list[Augment] = []
    for raw_en in en.get("augments", []):
        raw_zh = zh_by_id.get(raw_en["id"], raw_en)
        dv = raw_en.get("dataValues", {})
        calc = raw_en.get("calculations", {})
        augments.append(Augment(
            id=raw_en["id"],
            api_name=raw_en.get("apiName", ""),
            rarity=raw_en.get("rarity", -1),
            name_en=raw_en.get("name", ""),
            name_zh=raw_zh.get("name", raw_en.get("name", "")),
            desc_en=render_description(_pick_text(raw_en), dv, calc),
            desc_zh=render_description(
                _pick_text(raw_zh), raw_zh.get("dataValues", dv),
                raw_zh.get("calculations", calc)),
        ))
    logger.info("arena data loaded: %d augments, patch %s", len(augments), patch)
    return ArenaData(augments=augments, patch=patch)


def get_arena_data() -> cache.CacheResult:
    return cache.get_cached("arena", _fetch_arena_data)


# ---------------------------------------------------------------- 搜尋

def _norm(s: str) -> str:
    """搜尋用正規化:小寫、去空白與常見符號。"""
    return re.sub(r"[\s'\-_.:,!&]+", "", s.lower())


def score_augment(query: str, aug: Augment) -> float:
    """給一個 0~100 的相似度分數。

    策略(由強到弱):完全同名 > 名字包含關鍵字 > apiName 包含 >
    說明文字包含 > difflib 相似度。中文查詢靠「包含」就很準,
    英文打錯字則靠 difflib 撈回來。
    """
    q = _norm(query)
    if not q:
        return 0.0
    names = [_norm(aug.name_zh), _norm(aug.name_en), _norm(aug.api_name)]
    if q in (names[0], names[1]):
        return 100.0
    if any(q in n for n in names if n):
        return 90.0
    if any(n in q for n in names if len(n) >= 2):
        return 80.0  # 查詢句子裡含有強化名,例如「灼燒煉金那個強化」
    desc_hit = q in _norm(aug.desc_zh) or q in _norm(aug.desc_en)
    fuzz = max(SequenceMatcher(None, q, n).ratio() for n in names if n)
    return max(40.0 if desc_hit else 0.0, fuzz * 75.0)


def search_augments(query: str, augments: list[Augment],
                    limit: int = 5) -> list[tuple[float, Augment]]:
    scored = [(score_augment(query, a), a) for a in augments]
    scored.sort(key=lambda t: (-t[0], t[1].id))
    return [(s, a) for s, a in scored[:limit] if s > 0]


# ---------------------------------------------------------------- 輸出排版

def _source_line(result: cache.CacheResult, patch: str, locale: str) -> str:
    stale = ""
    if result.is_stale:
        stale = ("\n⚠️ 注意:資料更新失敗,以下為上次成功抓取的快取,可能過期。"
                 if locale == "zh_tw" else
                 "\n⚠️ Warning: refresh failed; showing cached data that may be outdated.")
    return (f"📌 資料:patch {patch} · CommunityDragon · 抓取於 {result.fetched_at_str}{stale}"
            if locale == "zh_tw" else
            f"📌 Data: patch {patch} · CommunityDragon · fetched {result.fetched_at_str}{stale}")


def format_augment_detail(aug: Augment, locale: str) -> str:
    other_name = aug.name_en if locale == "zh_tw" else aug.name_zh
    lines = [
        f"{aug.rarity_label(locale)}強化:{aug.name(locale)}({other_name})"
        if locale == "zh_tw" else
        f"{aug.rarity_label(locale)} Augment: {aug.name(locale)} ({other_name})",
        "─" * 30,
        aug.desc(locale) or "(此強化沒有說明文字)",
    ]
    if "?" in aug.desc(locale):
        lines.append("")
        lines.append("ℹ️ 「?」代表該數值由遊戲內即時計算(隨等級/裝備變動),離線資料無法確定。"
                     if locale == "zh_tw" else
                     "ℹ️ '?' marks values computed live in-game; not available offline.")
    return "\n".join(lines)


def do_get_augment(query: str, locale: str = "zh_tw") -> str:
    locale = locale.lower()
    if locale not in SUPPORTED_LOCALES:
        locale = "zh_tw"
    try:
        result = get_arena_data()
    except cache.DataUnavailableError as exc:
        return (f"❌ 查詢失敗:目前無法取得競技場資料(CommunityDragon 連線失敗),"
                f"請稍後再試。技術細節:{exc}")
    data: ArenaData = result.data
    matches = search_augments(query, data.augments)

    if not matches:
        return (f"找不到與「{query}」相關的強化。"
                f"可以試試中文或英文的強化名稱關鍵字,例如「地獄三頭犬」或 Cerberus。\n"
                + _source_line(result, data.patch, locale))

    best_score, best = matches[0]
    if best_score >= 80:
        out = [format_augment_detail(best, locale)]
        # 有其他高分候選時一併提示,避免同名/相近名誤導
        runners = [a for s, a in matches[1:] if s >= 80]
        if runners:
            names = "、".join(f"{a.name(locale)}({a.name_en})" for a in runners)
            out.append(f"\n🔎 其他可能符合:{names}(想看哪個再告訴我)")
        out.append("")
        out.append(_source_line(result, data.patch, locale))
        return "\n".join(out)

    # 沒有高分命中:展示最接近的一筆完整內容,並列出其他候選,
    # 讓一次查詢就有可用的答案,同時不假裝「就是這個」。
    lines = [f"沒有完全符合「{query}」的強化,最接近的是:", "",
             format_augment_detail(best, locale), ""]
    if len(matches) > 1:
        lines.append("🔎 其他候選:")
        for s, a in matches[1:]:
            lines.append(f"- {a.rarity_label(locale)} {a.name(locale)}({a.name_en})"
                         f" — {first_sentence(a.desc(locale))}")
        lines.append("")
    lines.append(_source_line(result, data.patch, locale))
    return "\n".join(lines)


def do_list_augments(tier: str = "all", locale: str = "zh_tw") -> str:
    locale = locale.lower()
    if locale not in SUPPORTED_LOCALES:
        locale = "zh_tw"
    try:
        result = get_arena_data()
    except cache.DataUnavailableError as exc:
        return (f"❌ 查詢失敗:目前無法取得競技場資料(CommunityDragon 連線失敗),"
                f"請稍後再試。技術細節:{exc}")
    data: ArenaData = result.data

    tier_norm = tier.strip().lower()
    if tier_norm in ("all", "全部", ""):
        wanted = None
    elif tier_norm in _TIER_ALIASES:
        wanted = _TIER_ALIASES[tier_norm]
    else:
        return ("無效的稀有度。可用:all / silver(白銀) / gold(黃金) / "
                "prismatic(稜彩) / special(特殊:稜彩道具與鐵砧類)")

    lines: list[str] = []
    for rarity in (2, 1, 0, 4):  # 稜彩最稀有,排前面
        if wanted is not None and rarity != wanted:
            continue
        group = [a for a in data.augments if a.rarity == rarity]
        if not group:
            continue
        zh, en, icon = RARITY_INFO[rarity]
        title = f"{icon} {zh}({en})" if locale == "zh_tw" else f"{icon} {en}"
        lines.append(f"## {title} — {len(group)} 個")
        for a in sorted(group, key=lambda x: x.name(locale)):
            lines.append(f"- **{a.name(locale)}**({a.name_en}):"
                         f"{first_sentence(a.desc(locale))}")
        lines.append("")

    lines.append(_source_line(result, data.patch, locale))
    return "\n".join(lines)
