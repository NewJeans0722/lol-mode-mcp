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
CHAMPION_FULL_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/{locale}/championFull.json"


@dataclass
class Champion:
    id: str        # ddragon id,例如 "MonkeyKing"
    name_en: str   # 英文顯示名,例如 "Wukong"(= wiki 的 key)
    name_zh: str   # zh_TW 顯示名,例如 "悟空"
    title_zh: str  # 稱號,例如 "齊天大聖"
    icon_url: str = ""  # ddragon 方形頭像(網頁 UI 用)
    tags: tuple = ()    # 職業定位(Fighter/Tank/Mage/Assassin/Marksman/Support)


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
            tags=tuple(c_en.get("tags", [])),
        ))
    logger.info("champion list loaded: %d champions (ddragon %s)", len(champs), ver)
    return champs


def get_champions() -> cache.CacheResult:
    return cache.get_cached("champions", _fetch_champions)


# ---------------------------------------------------- 技能台服名對照
# championFull.json(en_US + zh_TW,各約 2MB)→ 每英雄的技能名對照。
# 變形英雄的技能名是複合字串(en "Cunning Sweep / Sundering Slam"
# ↔ zh「暗襲／裂斬」),兩邊都用斜線切開、按位置配對,
# 讓 wiki 的單一技能名("Sundering Slam")也查得到台服名(「裂斬」)。

def split_ability_names(name: str) -> list[str]:
    return [p.strip() for p in re.split(r"[/／]", name) if p.strip()]


def _fetch_spell_names() -> dict[str, dict]:
    """{champion id: {"slots": {P/Q/W/E/R: 台服名}, "by_en": {en(小寫): 台服名}}}"""
    ver = fetch_json(VERSIONS_URL)[0]
    en = fetch_json(CHAMPION_FULL_URL.format(ver=ver, locale="en_US"))["data"]
    zh = fetch_json(CHAMPION_FULL_URL.format(ver=ver, locale="zh_TW"))["data"]
    out: dict[str, dict] = {}
    for cid, c_en in en.items():
        c_zh = zh.get(cid)
        if not c_zh:
            continue
        pairs = [("P", c_en["passive"]["name"], c_zh["passive"]["name"])]
        pairs += [(slot, s_en["name"], s_zh["name"]) for slot, s_en, s_zh
                  in zip("QWER", c_en["spells"], c_zh["spells"])]
        slots: dict[str, str] = {}
        by_en: dict[str, str] = {}
        for slot, n_en, n_zh in pairs:
            slots[slot] = n_zh
            by_en[n_en.lower()] = n_zh
            ens, zhs = split_ability_names(n_en), split_ability_names(n_zh)
            if len(ens) == len(zhs):
                for e, z in zip(ens, zhs):
                    by_en[e.lower()] = z
        out[cid] = {"slots": slots, "by_en": by_en}
    logger.info("spell name map loaded: %d champions (ddragon %s)", len(out), ver)
    return out


def get_spell_names() -> cache.CacheResult:
    return cache.get_cached("spell_names", _fetch_spell_names)


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
