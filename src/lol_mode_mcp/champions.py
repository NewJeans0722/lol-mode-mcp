"""英雄名字正規化:讓使用者打中文、英文、暱稱拼法都能對到英雄。

資料源:Riot 官方 Data Dragon(en_US + zh_TW 的 champion.json)。
以英雄 id(如 MonkeyKing)為主鍵,合併出:
    id / 英文顯示名(Wukong)/ 中文顯示名(悟空)/ 稱號
LoL Wiki 的資料以「英文顯示名」為 key,所以用英文顯示名當橋樑。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from . import cache
from .http_util import fetch_json

logger = logging.getLogger(__name__)

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
CHAMPION_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/{locale}/champion.json"


@dataclass
class Champion:
    id: str        # ddragon id,例如 "MonkeyKing"
    name_en: str   # 英文顯示名,例如 "Wukong"(= wiki 的 key)
    name_zh: str   # zh_TW 顯示名,例如 "悟空"
    title_zh: str  # 稱號,例如 "齊天大聖"
    icon_url: str = ""  # ddragon 方形頭像(網頁 UI 用)


def _norm(s: str) -> str:
    return re.sub(r"[\s'\-_.:,!&.]+", "", s.lower())


def _fetch_champions() -> list[Champion]:
    versions = fetch_json(VERSIONS_URL)
    ver = versions[0]
    en = fetch_json(CHAMPION_URL.format(ver=ver, locale="en_US"))["data"]
    zh = fetch_json(CHAMPION_URL.format(ver=ver, locale="zh_TW"))["data"]
    champs = []
    for cid, c_en in en.items():
        c_zh = zh.get(cid, c_en)
        champs.append(Champion(
            id=cid,
            name_en=c_en["name"],
            name_zh=c_zh["name"],
            title_zh=c_zh.get("title", ""),
            icon_url=f"https://ddragon.leagueoflegends.com/cdn/{ver}/img/champion/{cid}.png",
        ))
    logger.info("champion list loaded: %d champions (ddragon %s)", len(champs), ver)
    return champs


def get_champions() -> cache.CacheResult:
    return cache.get_cached("champions", _fetch_champions)


def resolve_champion(query: str, champs: list[Champion]) -> tuple[Champion | None, list[Champion]]:
    """回傳 (命中的英雄, 候選清單)。

    命中規則:名字完全一致(中/英/id)> 名字包含查詢字串。
    沒命中時回傳 difflib 最相近的前幾名當候選。
    """
    q = _norm(query)
    if not q:
        return None, []
    for c in champs:
        if q in (_norm(c.name_zh), _norm(c.name_en), _norm(c.id)):
            return c, []
    partial = [c for c in champs
               if q in _norm(c.name_zh) or q in _norm(c.name_en)]
    if len(partial) == 1:
        return partial[0], []
    if partial:
        return None, partial[:5]
    scored = sorted(
        champs,
        key=lambda c: -max(SequenceMatcher(None, q, _norm(c.name_en)).ratio(),
                           SequenceMatcher(None, q, _norm(c.name_zh)).ratio()),
    )
    return None, scored[:5]
