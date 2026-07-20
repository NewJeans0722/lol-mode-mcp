"""網頁查詢介面的 JSON API 與首頁。

和 MCP 的關係:同一個 server、同一份資料快取,只是多開兩種出口 ——
  /            靜態 HTML(海克斯圖鑑 + ARAM 平衡表,前端自己打 API)
  /api/...     JSON API(給網頁的 JavaScript 用)
只在 streamable-http 模式下有作用(stdio 模式沒有 HTTP,自然不掛)。

為什麼把「整理成前端好用的形狀」放在這層:
arena.py / aram.py 專心維護資料本身,這裡才決定網頁要看到什麼欄位,
之後想改 UI 不會動到資料層。
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from . import cache
from .aram import FIELD_INFO, FIELD_LABELS_EN, get_wiki_data
from .arena import RARITY_INFO, get_arena_data
from .arena_balance import (AR_STAT_LABELS, AR_STAT_LABELS_EN,
                            ability_zh_name, build_entity_name_map,
                            get_map_changes, group_champion_changes)
from .champions import get_champions, get_spell_names
from .translate import translate_lines
from .wikitext import translate_annotations_en
from .official_notes import get_official_zh
from .patch_notes import (SCOPES, enrich_categories, get_patch_data,
                          get_patch_titles, normalize_patch)

logger = logging.getLogger(__name__)

_INDEX_PATH = Path(__file__).resolve().parent / "web" / "index.html"

# rarity 數字 → 前端用的 slug
_TIER_SLUG = {0: "silver", 1: "gold", 2: "prismatic", 4: "special"}


# ------------------------------------------------------- 效能:回應層快取
# payload 的「組裝」本身很貴(arena-balance 要對 173 隻英雄跑翻譯與
# 名詞代換,實測 ~6 秒),所以組好的 payload 也進 TTL 快取,
# 之後的請求只剩序列化 + gzip(毫秒級)。

def _cached_json(request: Request, key: str, builder,
                 ttl: float = 3600) -> Response:
    try:
        result = cache.get_cached(key, builder, ttl=ttl)
    except cache.DataUnavailableError as exc:
        return JSONResponse({"error": f"資料源連線失敗:{exc}"}, status_code=503)
    body = json.dumps(result.data, ensure_ascii=False).encode()
    headers = {"Cache-Control": "public, max-age=300"}  # 瀏覽器再快取 5 分鐘
    if len(body) > 10_000 and "gzip" in request.headers.get("accept-encoding", ""):
        body = gzip.compress(body, 6)
        headers["Content-Encoding"] = "gzip"
    return Response(body, media_type="application/json", headers=headers)


async def home(_: Request) -> HTMLResponse:
    try:
        html = _INDEX_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("index.html unreadable: %s", exc)
        return HTMLResponse("<h1>UI 檔案缺失</h1>", status_code=500)
    # 流量統計(GoatCounter):設了環境變數才注入,程式碼不用改
    code = os.environ.get("GOATCOUNTER_CODE", "").strip()
    if code:
        snippet = (f'<script data-goatcounter="https://{code}.goatcounter.com/count" '
                   f'async src="//gc.zgo.at/count.js"></script>')
        html = html.replace("</body>", snippet + "\n</body>")
    return HTMLResponse(html)


def _augments_payload() -> dict:
    result = get_arena_data()
    data = result.data
    return {
        "patch": data.patch,
        "fetched_at": result.fetched_at_str,
        "stale": result.is_stale,
        "augments": [
            {
                "id": a.id,
                "apiName": a.api_name,
                "tier": _TIER_SLUG.get(a.rarity, "unknown"),
                "tierZh": RARITY_INFO.get(a.rarity, ("未知",))[0],
                "nameZh": a.name_zh,
                "nameEn": a.name_en,
                "descZh": a.desc_zh,
                "descEn": a.desc_en,
                "icon": a.icon_url,
                "maxLevel": a.max_level,
                "source": a.source,
                "note": a.note,
            }
            for a in data.augments
        ],
    }


async def api_augments(request: Request) -> Response:
    return _cached_json(request, "api_augments", _augments_payload)


def _arena_balance_payload() -> dict:
    champs = get_champions()
    wiki = get_wiki_data()      # 基礎數值(ar 區塊,與 ARAM 同一次抓取)
    mc = get_map_changes()      # 逐技能調整
    ar = wiki.data.get("ar", {})
    grouped = group_champion_changes(mc.data["champions"], champs.data)
    try:  # 技能台服名:抓不到只影響中文顯示,不擋主資料
        spell_names = get_spell_names().data
    except cache.DataUnavailableError:
        spell_names = None
    base_names = build_entity_name_map()  # 強化/裝備/英雄名(共用)
    def champ_map(cid: str) -> dict[str, str]:
        spells = (spell_names or {}).get(cid, {}).get("by_en", {})
        return {**base_names, **spells}
    payload = {
        "revision_time": mc.data["revision_time"],
        "fetched_at": mc.fetched_at_str,
        "stale": champs.is_stale or wiki.is_stale or mc.is_stale,
        "statLabels": AR_STAT_LABELS,
        "statLabelsEn": AR_STAT_LABELS_EN,
        "champions": [
            {
                "id": c.id,
                "nameZh": c.name_zh,
                "nameEn": c.name_en,
                "titleZh": c.title_zh,
                "icon": c.icon_url,
                "stats": ar.get(c.name_en),                # None = 無基礎數值調整
                "tags": list(c.tags),
                "abilities": [
                    {"label": label,
                     "labelZh": ability_zh_name(c.id, label, spell_names),
                     "lines": translate_lines(lines, champ_map(c.id)),
                     "linesEn": [translate_annotations_en(ln) for ln in lines]}
                    for label, lines in grouped.get(c.name_en, [])
                ],
            }
            for c in sorted(champs.data, key=lambda c: c.name_en)
        ],
    }
    return payload


async def api_arena_balance(request: Request) -> Response:
    return _cached_json(request, "api_arena_balance", _arena_balance_payload)


def _patch_notes_payload(patch: str, scope: str) -> dict:
    """patch 已由 handler 驗證過('latest' 或存在的 VYY.MM)。"""
    titles = get_patch_titles().data
    if patch == "latest":
        candidates = titles[:4]  # 最新頁可能還沒有該段落,往前找
    else:
        candidates = [patch]
    notes, stale, fetched = None, False, ""
    for title in candidates:
        result = get_patch_data(title)
        if result.data["scopes"].get(scope) or title == candidates[-1]:
            notes, stale, fetched = result.data, result.is_stale, result.fetched_at_str
            if result.data["scopes"].get(scope):
                break

    # 中文版:Riot 官方繁中 patch notes 原文(抓不到就 null,前端退回規則翻譯)
    categories_zh = None
    try:
        off = get_official_zh(notes["patch"])
        official = off.data["scopes"].get(scope)
        if official:
            # 官方 notes 的中文名會帶全形括號尾註(慨影(詭影刺客))、
            # 間隔號字元也可能不同(睿娜妲.格萊斯克 vs ‧),正規化後比對
            def _zh_key(name: str) -> str:
                # 間隔號各種寫法(U+FF0E/2027/00B7/30FB/半形點)一律去除
                return re.sub(r"[.．‧·・\s]", "",
                              _PAREN_TAIL.sub("", name))
            zh_champs = {_zh_key(c.name_zh): c for c in get_champions().data}
            def _champ_of(name: str):
                return zh_champs.get(_zh_key(name))
            categories_zh = [{
                "category": c["category"],
                "entries": [{
                    "name": e["name"],
                    "nameEn": (ch.name_en if (ch := _champ_of(e["name"])) else None),
                    "icon": ch.icon_url if ch else None,
                    "lines": e["lines"],
                } for e in c["entries"]],
            } for c in official]
    except Exception as exc:  # noqa: BLE001 — 官方頁失敗不影響主資料
        logger.warning("official zh notes unavailable: %s", exc)

    categories = enrich_categories(notes["scopes"].get(scope, []))
    _attach_entity_icons(categories, categories_zh)  # 強化/裝備圖示
    return {
        "patch": notes["patch"],
        "patches": titles[:16],  # 給下拉選單
        "scope": scope,
        "fetched_at": fetched,
        "stale": stale,
        "categories": categories,
        "categoriesZh": categories_zh,
    }


# 全形/半形括號尾註(如「慨影(詭影刺客)」);全形括號用 unicode 跳脫明確寫
_PAREN_TAIL = re.compile(r"\s*[(（][^)）]*[)）]\s*$")


def _entity_icons() -> tuple[dict, dict]:
    """(en 正規化名→圖示, zh 名→圖示):競技場/Mayhem 強化 + 裝備。"""
    from .mayhem_augments import get_mayhem_codex
    from .patch_notes import _name_key, get_item_names
    en_map: dict[str, str] = {}
    zh_map: dict[str, str] = {}
    try:
        for a in get_arena_data().data.augments:
            if a.icon_url:
                en_map[_name_key(a.name_en)] = a.icon_url
                if a.name_zh:
                    zh_map[a.name_zh] = a.icon_url
    except cache.DataUnavailableError:
        pass
    try:
        for e in get_mayhem_codex().data:
            if e["icon"]:
                en_map.setdefault(_name_key(e["nameEn"]), e["icon"])
                if e["nameZh"]:
                    zh_map.setdefault(e["nameZh"], e["icon"])
    except cache.DataUnavailableError:
        pass
    try:
        items = get_item_names().data
        for k, v in items.get("en_to_icon", {}).items():
            en_map.setdefault(k, v)
        for k, v in items.get("zh_to_icon", {}).items():
            zh_map.setdefault(k, v)
    except cache.DataUnavailableError:
        pass
    return en_map, zh_map


def _attach_entity_icons(categories: list[dict], categories_zh) -> None:
    """Patch 條目補強化/裝備圖示(英雄圖示既有邏輯已處理)。"""
    from .patch_notes import _name_key
    en_map, zh_map = _entity_icons()
    for c in categories or []:
        for e in c["entries"]:
            if not e.get("icon"):
                key = _name_key(_PAREN_TAIL.sub("", e["name"]))
                e["icon"] = en_map.get(key) or (
                    zh_map.get(_PAREN_TAIL.sub("", e["nameZh"]))
                    if e.get("nameZh") else None)
    for c in categories_zh or []:
        for e in c["entries"]:
            if not e.get("icon"):
                base = _PAREN_TAIL.sub("", e["name"]).strip()
                e["icon"] = zh_map.get(base) or zh_map.get(e["name"])


async def api_patch_notes(request: Request) -> Response:
    patch = request.query_params.get("patch", "latest").strip()
    scope = request.query_params.get("scope", "arena").strip().lower()
    if scope not in SCOPES:
        return JSONResponse({"error": f"scope「{scope}」不存在"}, status_code=400)
    if patch.lower() in ("", "latest"):
        patch = "latest"
    else:
        wanted = normalize_patch(patch)
        try:
            titles = get_patch_titles().data
        except cache.DataUnavailableError as exc:
            return JSONResponse({"error": f"資料源連線失敗:{exc}"},
                                status_code=503)
        if wanted is None or wanted not in titles:
            return JSONResponse({"error": f"找不到 patch「{patch}」"},
                                status_code=400)
        patch = wanted
    return _cached_json(request, f"api_patch_{patch}_{scope}",
                        lambda: _patch_notes_payload(patch, scope))


def _aram_payload() -> dict:
    champs = get_champions()
    wiki = get_wiki_data()
    aram = wiki.data["aram"]
    return {
        "revision_time": wiki.data["revision_time"],
        "fetched_at": wiki.fetched_at_str,
        "stale": wiki.is_stale or champs.is_stale,
        "fields": {k: v[0] for k, v in FIELD_INFO.items()},  # 欄位中文標籤
        "fieldsEn": FIELD_LABELS_EN,
        "champions": [
            {
                "id": c.id,
                "nameZh": c.name_zh,
                "nameEn": c.name_en,
                "titleZh": c.title_zh,
                "icon": c.icon_url,
                "tags": list(c.tags),
                "changes": aram.get(c.name_en),  # None = 本 patch 無調整
            }
            for c in sorted(champs.data, key=lambda c: c.name_en)
        ],
    }


async def api_aram(request: Request) -> Response:
    return _cached_json(request, "api_aram", _aram_payload)


def _mayhem_augments_payload() -> dict:
    from .mayhem_augments import _MODULE_META, TIER_INFO, get_mayhem_codex
    result = get_mayhem_codex()
    return {
        "fetched_at": result.fetched_at_str,
        "revised": _MODULE_META.get("revised", "unknown"),
        "stale": result.is_stale,
        "note": "中文說明:官方遊戲字串優先,其餘為人工/規則翻譯;數值以英文 wiki 為準,名稱為台服官方譯名。",
        "augments": [
            {
                "nameEn": e["nameEn"],
                "nameZh": e["nameZh"] or e["nameEn"],
                "tier": e["tier"] or "unknown",
                "tierZh": TIER_INFO.get(e["tier"], "未知"),
                "desc": e["desc"],
                "descZh": e.get("descZh") or e["desc"],
                "descComplete": e.get("descComplete", False),
                "icon": e["icon"] or "",
                "iconSmall": e.get("iconSmall") or "",
            }
            for e in result.data
        ],
    }


async def api_mayhem_augments(request: Request) -> Response:
    return _cached_json(request, "api_mayhem_augments", _mayhem_augments_payload)


def _mechanics_payload() -> dict:
    from .mechanics import load_mechanics
    data = load_mechanics()
    try:  # 貴賓補台服名與頭像
        champs = {c.name_en: c for c in get_champions().data}
    except cache.DataUnavailableError:
        champs = {}
    for sec in data.get("arena", {}).get("sections", []):
        for g in sec.get("guests", []):
            c = champs.get(g["nameEn"])
            g.setdefault("nameZh", c.name_zh if c else g["nameEn"])
            g["icon"] = c.icon_url if c else ""  # 亞塔坎等非英雄查不到,留空
    return data


async def api_mechanics(request: Request) -> Response:
    return _cached_json(request, "api_mechanics", _mechanics_payload)


# ------------------------------------------------------- 背景原畫(官方)
# 使用者指定的背景英雄;原畫來自 Riot 官方 Data Dragon CDN(和英雄頭像
# 同一來源)。炫彩(如「泳池狂歡 柔依(焰紅)」)沒有獨立原畫(HEAD 403),
# 逐一探測後只收有圖的,所以清單會隨官方出新造型自動更新。

BG_CHAMPIONS = ["Zoe", "Briar"]
_SPLASH_URL = "https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{cid}_{num}.jpg"
_CHAMP_DETAIL_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/zh_TW/champion/{cid}.json"
_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"


# 需要翻轉的 skin key(ChampionId_SkinNum):人物靠左，右側面板要翻轉
_FLIP_SKINS = {"Zoe_22", "Briar_20"}

# Zoe:只保留指定 skin; Briar:全部保留(不含 default/0)
_KEEP_SKINS = {
    "Zoe": {0, 1, 9, 22, 43},
    "Briar": None,  # None = 只排除 default(0)
}


def _backgrounds_payload() -> dict:
    import httpx

    from .http_util import fetch_json
    ver = fetch_json(_VERSIONS_URL)[0]
    champions = []
    with httpx.Client(timeout=10) as client:
        for cid in BG_CHAMPIONS:
            data = fetch_json(_CHAMP_DETAIL_URL.format(ver=ver, cid=cid))["data"][cid]
            keep = _KEEP_SKINS.get(cid)
            skins = []
            for s in data["skins"]:
                num = s["num"]
                if keep is not None and num not in keep and not (num == 0 and keep is None):
                    continue
                url = _SPLASH_URL.format(cid=cid, num=num)
                try:
                    if client.head(url).status_code != 200:
                        continue
                except httpx.HTTPError:
                    continue
                name = "經典原畫" if s["name"] == "default" else s["name"]
                key = f"{cid}_{num}"
                skins.append({"num": num, "name": name, "url": url,
                               "flip": key in _FLIP_SKINS})
            champions.append({"id": cid, "name": data["name"], "skins": skins})
    logger.info("backgrounds loaded: %s",
                {c["id"]: len(c["skins"]) for c in champions})
    return {"champions": champions}


async def api_backgrounds(request: Request) -> Response:
    return _cached_json(request, "api_backgrounds", _backgrounds_payload,
                        ttl=12 * 3600)


# ------------------------------------------------------- 競技場統計
# 資料來自本機爬取的 Riot Match-V5 真實對戰(雪球取樣),靜態檔部署,
# 不需要 API key。檔案不存在時回傳空,前端自己隱藏統計分頁。

_STATS_PATH = Path(__file__).resolve().parent / "data" / "arena_stats.json"


def _arena_stats_payload() -> dict:
    from .champions import get_champions
    from .arena import get_arena_data
    try:
        stats = json.loads(_STATS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"available": False}
    # 英雄頭像:統計裡的 championName(如 MonkeyKing) = ddragon id
    try:
        icons = {c.id: c.icon_url for c in get_champions().data}
    except Exception:
        icons = {}
    # 強化圖示(CommunityDragon)
    try:
        aug_icons = {str(a.id): a.icon_url for a in get_arena_data().data.augments}
    except Exception:
        aug_icons = {}
    # 只傳前端需要的欄位:強化勝率排行 + 每卡片 top5 英雄
    augs = []
    for aid, a in stats["augments"].items():
        if a.get("rarity") == 4:  # 特殊類(鐵砧/欄位)跳過
            continue
        tc = a.get("topChamps", [])
        top5 = [{"champ": t["champ"], "nameZh": t["champZh"],
                 "games": t["games"],
                 "firstRate": round(t.get("firstRate", 0), 3),
                 "icon": icons.get(t["champ"], "")}
                for t in tc[:5]]
        augs.append({
            "id": aid,
            "nameZh": a["nameZh"], "nameEn": a["nameEn"],
            "icon": aug_icons.get(aid, ""),
            "rarity": a.get("rarity", -1),
            "games": a["games"],
            "avgPlace": a["avgPlace"],
            "firstRate": a.get("firstRate", 0),
            "top2Rate": a["top2Rate"],
            "lowSample": a.get("lowSample", False),
            "topChamps": top5,
        })
    augs.sort(key=lambda x: (-x.get("firstRate", 0), -x["top2Rate"], -x["games"]))
    # champions sorted by win rate
    champs = []
    for cid, c in stats["champions"].items():
        ta = c.get("topAugments", [])
        top5 = [{"id": t["id"], "nameZh": t["nameZh"],
                 "games": t["games"],
                 "firstRate": round(t.get("firstRate", 0), 3)}
                for t in ta[:5]]
        champs.append({
            "id": cid, "nameZh": c["nameZh"], "nameEn": c["nameEn"],
            "games": c["games"], "avgPlace": c["avgPlace"],
            "firstRate": c.get("firstRate", 0), "top2Rate": c["top2Rate"],
            "lowSample": c.get("lowSample", False),
            "icon": icons.get(cid, ""),
            "topAugments": top5,
        })
    champs.sort(key=lambda x: (-x.get("firstRate", 0), -x["top2Rate"], -x["games"]))
    return {
        "available": True,
        "meta": stats["meta"],
        "augments": augs,
        "champions": champs,
        # per-augment top5 英雄索引(key=augment nameEn,供圖鑑卡片快速查)
        "topHeroes": {a["nameEn"]: a["topChamps"] for a in augs},
    }


async def api_arena_stats(request: Request) -> Response:
    return _cached_json(request, "api_arena_stats", _arena_stats_payload)


def warmup() -> None:
    """啟動時在背景把資料源與 API payload 都先算好,訪客不用等。"""
    builders = [("api_augments", _augments_payload),
                ("api_aram", _aram_payload),
                ("api_arena_balance", _arena_balance_payload),
                ("api_patch_latest_arena",
                 lambda: _patch_notes_payload("latest", "arena")),
                ("api_patch_latest_general",
                 lambda: _patch_notes_payload("latest", "general")),
                ("api_patch_latest_mayhem",
                 lambda: _patch_notes_payload("latest", "mayhem")),
                ("api_backgrounds", _backgrounds_payload),
                ("api_mayhem_augments", _mayhem_augments_payload),
                ("api_mechanics", _mechanics_payload),
                ("api_arena_stats", _arena_stats_payload)]
    for key, builder in builders:
        try:
            cache.get_cached(key, builder)
            logger.info("warmup ok: %s", key)
        except Exception as exc:  # noqa: BLE001 — 暖身失敗不影響服務
            logger.warning("warmup failed for %s: %s", key, exc)
