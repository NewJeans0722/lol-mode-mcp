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
            zh_champs = {c.name_zh: c for c in get_champions().data}
            categories_zh = [{
                "category": c["category"],
                "entries": [{
                    "name": e["name"],
                    "nameEn": (zh_champs[e["name"]].name_en
                               if e["name"] in zh_champs else None),
                    "icon": (zh_champs[e["name"]].icon_url
                             if e["name"] in zh_champs else None),
                    "lines": e["lines"],
                } for e in c["entries"]],
            } for c in official]
    except Exception as exc:  # noqa: BLE001 — 官方頁失敗不影響主資料
        logger.warning("official zh notes unavailable: %s", exc)

    return {
        "patch": notes["patch"],
        "patches": titles[:16],  # 給下拉選單
        "scope": scope,
        "fetched_at": fetched,
        "stale": stale,
        "categories": enrich_categories(notes["scopes"].get(scope, [])),
        "categoriesZh": categories_zh,
    }


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


# ------------------------------------------------------- 背景原畫(官方)
# 使用者指定的背景英雄;原畫來自 Riot 官方 Data Dragon CDN(和英雄頭像
# 同一來源)。炫彩(如「泳池狂歡 柔依(焰紅)」)沒有獨立原畫(HEAD 403),
# 逐一探測後只收有圖的,所以清單會隨官方出新造型自動更新。

BG_CHAMPIONS = ["Zoe", "Briar"]
_SPLASH_URL = "https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{cid}_{num}.jpg"
_CHAMP_DETAIL_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/zh_TW/champion/{cid}.json"
_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"


def _backgrounds_payload() -> dict:
    import httpx

    from .http_util import fetch_json
    ver = fetch_json(_VERSIONS_URL)[0]
    champions = []
    with httpx.Client(timeout=10) as client:
        for cid in BG_CHAMPIONS:
            data = fetch_json(_CHAMP_DETAIL_URL.format(ver=ver, cid=cid))["data"][cid]
            skins = []
            for s in data["skins"]:
                url = _SPLASH_URL.format(cid=cid, num=s["num"])
                try:
                    if client.head(url).status_code != 200:
                        continue  # 炫彩無獨立原畫
                except httpx.HTTPError:
                    continue
                name = "經典原畫" if s["name"] == "default" else s["name"]
                skins.append({"num": s["num"], "name": name, "url": url})
            champions.append({"id": cid, "name": data["name"], "skins": skins})
    logger.info("backgrounds loaded: %s",
                {c["id"]: len(c["skins"]) for c in champions})
    return {"champions": champions}


async def api_backgrounds(request: Request) -> Response:
    return _cached_json(request, "api_backgrounds", _backgrounds_payload,
                        ttl=12 * 3600)


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
                ("api_backgrounds", _backgrounds_payload)]
    for key, builder in builders:
        try:
            cache.get_cached(key, builder)
            logger.info("warmup ok: %s", key)
        except Exception as exc:  # noqa: BLE001 — 暖身失敗不影響服務
            logger.warning("warmup failed for %s: %s", key, exc)
