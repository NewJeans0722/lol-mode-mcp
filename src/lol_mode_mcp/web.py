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

import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from . import cache
from .aram import FIELD_INFO, get_wiki_data
from .arena import RARITY_INFO, get_arena_data
from .arena_balance import (AR_STAT_LABELS, get_map_changes,
                            group_champion_changes)
from .champions import get_champions
from .patch_notes import get_arena_notes, get_patch_titles, normalize_patch

logger = logging.getLogger(__name__)

_INDEX_PATH = Path(__file__).resolve().parent / "web" / "index.html"

# rarity 數字 → 前端用的 slug
_TIER_SLUG = {0: "silver", 1: "gold", 2: "prismatic", 4: "special"}


async def home(_: Request) -> HTMLResponse:
    try:
        return HTMLResponse(_INDEX_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.error("index.html unreadable: %s", exc)
        return HTMLResponse("<h1>UI 檔案缺失</h1>", status_code=500)


async def api_augments(_: Request) -> JSONResponse:
    try:
        result = get_arena_data()
    except cache.DataUnavailableError as exc:
        return JSONResponse({"error": f"資料源連線失敗:{exc}"}, status_code=503)
    data = result.data
    payload = {
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
    return JSONResponse(payload)


async def api_arena_balance(_: Request) -> JSONResponse:
    try:
        champs = get_champions()
        wiki = get_wiki_data()      # 基礎數值(ar 區塊,與 ARAM 同一次抓取)
        mc = get_map_changes()      # 逐技能調整
    except cache.DataUnavailableError as exc:
        return JSONResponse({"error": f"資料源連線失敗:{exc}"}, status_code=503)
    ar = wiki.data.get("ar", {})
    grouped = group_champion_changes(mc.data["champions"], champs.data)
    payload = {
        "revision_time": mc.data["revision_time"],
        "fetched_at": mc.fetched_at_str,
        "stale": champs.is_stale or wiki.is_stale or mc.is_stale,
        "statLabels": AR_STAT_LABELS,
        "champions": [
            {
                "id": c.id,
                "nameZh": c.name_zh,
                "nameEn": c.name_en,
                "titleZh": c.title_zh,
                "icon": c.icon_url,
                "stats": ar.get(c.name_en),                # None = 無基礎數值調整
                "abilities": [{"label": label, "lines": lines}
                              for label, lines in grouped.get(c.name_en, [])],
            }
            for c in sorted(champs.data, key=lambda c: c.name_en)
        ],
    }
    return JSONResponse(payload)


async def api_patch_notes(request: Request) -> JSONResponse:
    patch = request.query_params.get("patch", "latest").strip()
    try:
        titles = get_patch_titles().data
        if patch.lower() in ("", "latest"):
            candidates = titles[:4]  # 最新頁可能還沒有 Arena 段落,往前找
        else:
            wanted = normalize_patch(patch)
            if wanted is None or wanted not in titles:
                return JSONResponse({"error": f"找不到 patch「{patch}」"},
                                    status_code=400)
            candidates = [wanted]
        notes, stale, fetched = None, False, ""
        for title in candidates:
            result = get_arena_notes(title)
            if result.data["categories"] or title == candidates[-1]:
                notes, stale, fetched = result.data, result.is_stale, result.fetched_at_str
                if result.data["categories"]:
                    break
    except cache.DataUnavailableError as exc:
        return JSONResponse({"error": f"資料源連線失敗:{exc}"}, status_code=503)
    return JSONResponse({
        "patch": notes["patch"],
        "patches": titles[:16],  # 給下拉選單
        "fetched_at": fetched,
        "stale": stale,
        "categories": notes["categories"],
    })


async def api_aram(_: Request) -> JSONResponse:
    try:
        champs = get_champions()
        wiki = get_wiki_data()
    except cache.DataUnavailableError as exc:
        return JSONResponse({"error": f"資料源連線失敗:{exc}"}, status_code=503)
    aram = wiki.data["aram"]
    payload = {
        "revision_time": wiki.data["revision_time"],
        "fetched_at": wiki.fetched_at_str,
        "stale": wiki.is_stale or champs.is_stale,
        "fields": {k: v[0] for k, v in FIELD_INFO.items()},  # 欄位中文標籤
        "champions": [
            {
                "id": c.id,
                "nameZh": c.name_zh,
                "nameEn": c.name_en,
                "titleZh": c.title_zh,
                "icon": c.icon_url,
                "changes": aram.get(c.name_en),  # None = 本 patch 無調整
            }
            for c in sorted(champs.data, key=lambda c: c.name_en)
        ],
    }
    return JSONResponse(payload)
