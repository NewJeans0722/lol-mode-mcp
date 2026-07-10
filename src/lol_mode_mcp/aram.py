"""ARAM 每英雄平衡數值:LoL Wiki 的 Lua 資料模組解析。

為什麼選 MediaWiki API 抓 wikitext 而不是爬渲染頁面:
- Module:ChampionData/data 是一個巨大的 Lua table,結構穩定、
  欄位有名字,用 API 一次抓回全部英雄(一個 request),
  比逐頁爬 HTML 表格穩得多、也對 wiki 伺服器友善。
- Lua table 雖然不是 JSON,但 aram 區塊只有「字串 key = 數字」
  的扁平結構,用 regex 就能可靠取出,不需要完整 Lua parser。

資料樣貌(節錄):
    ["Aatrox"] = {
      ["stats"] = { ...
        ["aram"] = { ["dmg_dealt"] = 1.05, ["dmg_taken"] = 1, },
      }, ...
    }
沒有 aram 區塊 = 該英雄本 patch 無 ARAM 調整(這和「查詢失敗」不同,
tool 回覆會明確區分)。
"""

from __future__ import annotations

import logging
import re

from . import cache
from .champions import get_champions, resolve_champion
from .http_util import fetch_json

logger = logging.getLogger(__name__)

WIKI_API = "https://wiki.leagueoflegends.com/en-us/api.php"
MODULE_TITLE = "Module:ChampionData/data"

# 欄位 → (中文標籤, 呈現方式, 數值越大是否越有利)
# 呈現方式: "mult" = 乘數(1.05 → +5%), "flat" = 直接加減(如技能急速 +20)
FIELD_INFO: dict[str, tuple[str, str, bool]] = {
    "dmg_dealt":      ("造成傷害", "mult", True),
    "dmg_taken":      ("承受傷害", "mult", False),  # 承傷越高越不利
    "healing":        ("治療效果", "mult", True),
    "shielding":      ("護盾效果", "mult", True),
    "ability_haste":  ("技能急速", "flat", True),   # 實測值 ±5~20,是加值
    "total_as":       ("總攻擊速度", "mult", True),
    "tenacity":       ("韌性", "mult", True),        # 實測值 1.1/1.2,是乘數
    "energyregen_mod": ("能量回復", "mult", True),
}
FIELD_LABELS_EN = {
    "dmg_dealt": "Damage Dealt",
    "dmg_taken": "Damage Taken",
    "healing": "Healing",
    "shielding": "Shielding",
    "ability_haste": "Ability Haste",
    "total_as": "Total Attack Speed",
    "tenacity": "Tenacity",
    "energyregen_mod": "Energy Regen",
}


def parse_champion_mode_data(lua_text: str, mode_key: str = "aram") -> dict[str, dict[str, float]]:
    """從 Lua 模組文字取出 {英文英雄名: {欄位: 數值}}。

    英雄區塊以兩格縮排的 ["Name"] = { 開頭;逐一切段後,
    在段內找 ["aram"] = { ... } 的扁平數值。
    """
    headers = list(re.finditer(r'^  \["([^"]+)"\] = \{', lua_text, re.M))
    result: dict[str, dict[str, float]] = {}
    for i, m in enumerate(headers):
        name = m.group(1)
        end = headers[i + 1].start() if i + 1 < len(headers) else len(lua_text)
        block = lua_text[m.end():end]
        mode_m = re.search(r'\["%s"\]\s*=\s*\{(.*?)\}' % re.escape(mode_key),
                           block, re.S)
        if not mode_m:
            continue
        fields = {
            k: float(v)
            for k, v in re.findall(r'\["(\w+)"\]\s*=\s*(-?[\d.]+)', mode_m.group(1))
        }
        if fields:
            result[name] = fields
    return result


def _fetch_wiki_data() -> dict:
    """抓 wikitext 並解析 aram 與 ar(競技場基礎數值)區塊,一次快取兩者。"""
    raw = fetch_json(WIKI_API, params={
        "action": "query", "prop": "revisions", "rvprop": "content|timestamp",
        "rvslots": "main", "titles": MODULE_TITLE,
        "format": "json", "formatversion": "2",
    })
    rev = raw["query"]["pages"][0]["revisions"][0]
    content = rev["slots"]["main"]["content"]
    aram = parse_champion_mode_data(content, "aram")
    if not aram:
        # 結構若大改導致解析出 0 筆,寧可當成失敗(觸發退回舊快取)
        raise ValueError("parsed 0 aram entries from wiki module — structure may have changed")
    # ar 區塊只有 ~45 隻英雄有,0 筆不當失敗(競技場輪替下架時可能真的沒有)
    ar = parse_champion_mode_data(content, "ar")
    logger.info("wiki mode data parsed: %d aram / %d arena champions (revision %s)",
                len(aram), len(ar), rev.get("timestamp", "?"))
    return {"aram": aram, "ar": ar,
            "revision_time": rev.get("timestamp", "unknown")}


def get_wiki_data() -> cache.CacheResult:
    return cache.get_cached("wiki_aram", _fetch_wiki_data)


# ---------------------------------------------------------------- 輸出排版

def _format_field(key: str, value: float) -> str | None:
    label, kind, higher_is_better = FIELD_INFO.get(key, (key, "mult", True))
    if kind == "mult":
        if value == 1:
            return None  # 無調整就不列
        pct = (value - 1) * 100
        delta = f"×{value:g}({pct:+.0f}%)"
        is_buff = (value > 1) == higher_is_better
    else:  # flat
        if value == 0:
            return None
        delta = f"{value:+g}"
        is_buff = (value > 0) == higher_is_better
    icon = "🟢 增益" if is_buff else "🔴 削弱"
    return f"{icon} {label} {delta}"


def do_aram_balance(champion: str) -> str:
    # 第一步:把使用者輸入(中/英/暱稱)對到英雄
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

    # 第二步:查 wiki 的 ARAM 數值
    try:
        wiki_result = get_wiki_data()
    except cache.DataUnavailableError as exc:
        return (f"❌ 查詢失敗:找到英雄 {champ.name_zh}({champ.name_en}),"
                f"但無法取得 LoL Wiki 的 ARAM 資料,請稍後再試。技術細節:{exc}")

    aram: dict[str, dict[str, float]] = wiki_result.data["aram"]
    entry = aram.get(champ.name_en)

    header = f"🏔️ {champ.name_zh}({champ.name_en}){champ.title_zh and ' — ' + champ.title_zh}"
    src = (f"📌 資料:LoL Wiki(CC BY-SA)· 模組更新於 {wiki_result.data['revision_time']}"
           f" · 抓取於 {wiki_result.fetched_at_str}")
    if wiki_result.is_stale:
        src += "\n⚠️ 注意:資料更新失敗,以下為上次成功抓取的快取,可能過期。"

    if entry is None:
        return (f"{header}\n"
                f"本 patch **沒有 ARAM 平衡調整**(全部使用基準值,"
                f"傷害/承傷/治療等皆為 100%)。\n\n{src}")

    lines = [header, "ARAM 平衡調整:", ""]
    shown = [s for key, value in entry.items() if (s := _format_field(key, value))]
    if not shown:
        lines.append("資料中有 ARAM 區塊,但所有數值皆為基準值(無實質調整)。")
    else:
        lines.extend(shown)
    lines += ["", src]
    return "\n".join(lines)


def do_mayhem_balance(champion: str) -> str:
    """ARAM: Mayhem 延伸目標的 stub —— 介面先留好,資料源接上後再實作。"""
    return ("🚧 ARAM: Mayhem 的每英雄數值查詢**暫未支援**。\n"
            "Mayhem 有獨立的一組平衡數值與強化,穩定的結構化資料源"
            "還在評估中(LoL Wiki 的 Mayhem 資料模組)。"
            "目前可以先用 aram_balance 查一般 ARAM 的數值。")
