"""競技場實戰統計:Riot Match-V5 真實對戰 → 「強化適合誰 / 英雄強度」。

管線三段,各自獨立可重跑(詳見 NOTES.md 2026-07-17):
    scripts/crawl_arena.py       需要 RIOT_API_KEY,雪球爬台服場次存 JSONL
    scripts/build_arena_stats.py 離線聚合,寫 data/arena_stats.json(進 git)
    arena_stats tool             唯讀靜態 JSON,不需要 key(Render 不受影響)

誠實原則(使用者要求正確性優先):
- 雪球取樣自個人對戰圈,不是全服統計,輸出必附聲明
- 配對樣本 < min_pair 直接不收錄(寧缺勿誤導);整體樣本 < min_sample 標警語
- 統計 patch 與現行 patch 不符時標 stale 警告
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path

from .arena import RARITY_INFO, get_arena_data, search_augments
from .champions import get_champions, resolve_champion

logger = logging.getLogger(__name__)

# Match-V5 競技場 queue id:1750 = 2026 現行制(18 人/6 隊×3 人,名次 1~6)、
# 1700 = 舊制(16 人/8 隊×2 人,V26.9 後停用)。ARAM Mayhem 2400 被 Riot 封鎖。
ARENA_QUEUES = {1700, 1750}
DEFAULT_QUEUE = 1750

STATS_PATH = Path(__file__).parent / "data" / "arena_stats.json"


def _baseline_note(stats: dict) -> str:
    """名次均勻分布的數學基準(隊伍數決定),輸出附上讓數字可解讀。"""
    meta = stats["meta"]
    return (f"(全體基準:勝率 {meta.get('baselineFirstRate', 0.125) * 100:.1f}%"
            f" / 前二率 {meta.get('baselineTop2Rate', 0.25) * 100:.1f}%"
            f" / 平均名次 {meta.get('baselineAvgPlace', 4.5):.2f},"
            f"高於基準 = 比平均強)")


def _norm(s: str) -> str:
    return re.sub(r"[\s'\-_.:,!&]+", "", s.lower())


# ---------------------------------------------------------------- 資料精簡

def trim_match(raw: dict) -> dict | None:
    """Match-V5 原始回應 → 只留統計需要的欄位;非競技場或欄位缺損回 None。"""
    info = raw.get("info", {})
    if info.get("queueId") not in ARENA_QUEUES:
        return None
    parts = []
    for p in info.get("participants", []):
        champ = p.get("championName", "")
        # 名次:正式欄位是 placement,舊資料可能只有 subteamPlacement
        place = p.get("placement") or p.get("subteamPlacement") or 0
        if not champ or place < 1:
            return None
        augs = [p.get(f"playerAugment{i}", 0) for i in range(1, 7)]
        parts.append({
            "puuid": p.get("puuid", ""),
            "championName": champ,
            "placement": place,
            "subteam": p.get("playerSubteamId", 0),
            "augments": [a for a in augs if a],  # 0 = 空槽,濾掉
        })
    # 隊制不能寫死(1700 = 16 人/8 隊×2 人;1750 = 18 人/6 隊×3 人),
    # 改由名次分布驗證:每個名次人數相同、名次連續 1~隊數
    if len(parts) < 8:
        return None
    counts = Counter(p["placement"] for p in parts)
    teams = len(counts)
    size = len(parts) // teams
    if (teams * size != len(parts)
            or any(v != size for v in counts.values())
            or max(counts) != teams):
        return None
    version = str(info.get("gameVersion", ""))
    m = re.match(r"(\d+\.\d+)", version)
    return {
        "matchId": raw.get("metadata", {}).get("matchId", ""),
        "queue": info["queueId"],
        "patch": m.group(1) if m else "unknown",
        "gameVersion": version,
        "gameCreation": info.get("gameCreation", 0),
        "gameDuration": info.get("gameDuration", 0),
        "participants": parts,
    }


# ---------------------------------------------------------------- 聚合統計

def _summarize(acc: dict) -> dict:
    g = acc["games"]
    return {"games": g,
            "avgPlace": round(acc["place_sum"] / g, 2),
            "firstRate": round(acc["first"] / g, 3),  # 奪冠率 = 勝率
            "top2Rate": round(acc["top2"] / g, 3)}


def aggregate_stats(matches: list[dict],
                    augment_meta: dict[int, dict],
                    champ_meta: dict[str, dict],
                    min_sample: int = 30, min_pair: int = 10,
                    top_n: int = 5) -> dict:
    """精簡場次 → 統計 JSON 結構。

    augment_meta: {id: {"nameZh", "nameEn", "rarity"}}(來源 arena.get_arena_data)
    champ_meta:   {"MonkeyKing": {"nameZh": "悟空", "nameEn": "Wukong"}}
    """
    def new_acc():
        return {"games": 0, "place_sum": 0, "first": 0, "top2": 0}

    aug_acc: dict[int, dict] = defaultdict(new_acc)
    champ_acc: dict[str, dict] = defaultdict(new_acc)
    pair_acc: dict[tuple[int, str], dict] = defaultdict(new_acc)
    patches: Counter = Counter()
    players = 0
    base_place = 0.0  # 均勻分布期望:每場 (隊數+1)/2
    base_first = 0.0  # 均勻分布期望:每場 1/隊數
    base_top2 = 0.0   # 均勻分布期望:每場 2/隊數

    for m in matches:
        patches[m.get("patch", "unknown")] += 1
        # 隊數 = 最大名次(trim_match 已驗證名次連續且各隊人數相同)
        teams = max(p["placement"] for p in m["participants"])
        for p in m["participants"]:
            players += 1
            base_place += (teams + 1) / 2
            base_first += 1 / teams
            base_top2 += 2 / teams
            place = p["placement"]
            first, top2 = int(place == 1), int(place <= 2)
            for acc in (champ_acc[p["championName"]],):
                acc["games"] += 1
                acc["place_sum"] += place
                acc["first"] += first
                acc["top2"] += top2
            for aid in p["augments"]:
                for acc in (aug_acc[aid], pair_acc[(aid, p["championName"])]):
                    acc["games"] += 1
                    acc["place_sum"] += place
                    acc["first"] += first
                    acc["top2"] += top2

    # 配對樣本 >= min_pair 才收錄,依選取次數(場數)排序 —— 使用者要的是
    # 「誰最常拿」,勝率/名次資料附在旁邊供判讀
    def top_pairs(pairs: list[tuple], meta_fn) -> list[dict]:
        rows = [dict(meta_fn(key), **_summarize(acc))
                for key, acc in pairs if acc["games"] >= min_pair]
        rows.sort(key=lambda r: (-r["games"], r["avgPlace"]))
        return rows[:top_n]

    augments = {}
    for aid, acc in aug_acc.items():
        meta = augment_meta.get(aid, {})
        pairs = [(c, a) for (i, c), a in pair_acc.items() if i == aid]
        augments[str(aid)] = {
            "nameZh": meta.get("nameZh") or f"#{aid}",
            "nameEn": meta.get("nameEn", ""),
            "rarity": meta.get("rarity", -1),
            **_summarize(acc),
            "lowSample": acc["games"] < min_sample,
            "topChamps": top_pairs(
                pairs,
                lambda c: {"champ": c,
                           "champZh": champ_meta.get(c, {}).get("nameZh", c)}),
        }

    champions = {}
    for cid, acc in champ_acc.items():
        meta = champ_meta.get(cid, {})
        pairs = [(i, a) for (i, c), a in pair_acc.items() if c == cid]
        champions[cid] = {
            "nameZh": meta.get("nameZh", cid),
            "nameEn": meta.get("nameEn", cid),
            **_summarize(acc),
            "lowSample": acc["games"] < min_sample,
            "topAugments": top_pairs(
                pairs,
                lambda i: {"id": i,
                           "nameZh": augment_meta.get(i, {}).get("nameZh")
                           or f"#{i}"}),
        }

    return {
        "meta": {
            "matches": len(matches),
            "players": players,
            "patches": dict(patches.most_common()),
            "min_sample": min_sample,
            "min_pair": min_pair,
            "baselineAvgPlace": round(base_place / players, 3) if players else 0,
            "baselineFirstRate": round(base_first / players, 3) if players else 0,
            "baselineTop2Rate": round(base_top2 / players, 3) if players else 0,
        },
        "augments": augments,
        "champions": champions,
    }


# ---------------------------------------------------------------- 讀取與查詢

def load_stats() -> dict | None:
    """讀統計檔;不存在或壞掉回 None(tool 顯示友善提示,不丟例外)。"""
    try:
        return json.loads(STATS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning("arena_stats.json unreadable: %s", exc)
        return None


def _current_patch() -> str | None:
    """現行 patch(cdragon);抓不到(離線)回 None,不擋主功能。"""
    try:
        return get_arena_data().data.patch
    except Exception:
        return None


def _find_champion(query: str, stats: dict) -> str | None:
    """查詢字串 → 英雄 id。先用 ddragon 完整別名解析(離線則跳過),
    再退回統計檔內建名稱的包含比對。"""
    try:
        hit, _ = resolve_champion(query, get_champions().data)
        if hit:
            return hit.id
    except Exception:
        pass
    q = _norm(query)
    if not q:
        return None
    partial = None
    for cid, c in stats["champions"].items():
        names = [_norm(c.get("nameZh", "")), _norm(c.get("nameEn", "")), _norm(cid)]
        if q in names:
            return cid
        if any(q in n for n in names if n):
            partial = partial or cid
    return partial


def _find_augment(query: str, stats: dict) -> str | None:
    """查詢字串 → 強化 id(字串)。先用 arena 模糊搜尋(離線則跳過),
    再退回統計檔內建名稱的包含比對。"""
    try:
        matches = search_augments(query, get_arena_data().data.augments)
        if matches and matches[0][0] >= 80:
            return str(matches[0][1].id)
    except Exception:
        pass
    q = _norm(query)
    if not q:
        return None
    partial = None
    for aid, a in stats["augments"].items():
        names = [_norm(a.get("nameZh", "")), _norm(a.get("nameEn", ""))]
        if q in names:
            return aid
        if any(q in n for n in names if n):
            partial = partial or aid
    return partial


# ---------------------------------------------------------------- 輸出排版

def _rarity_icon(rarity: int) -> str:
    return RARITY_INFO.get(rarity, ("", "", "❓"))[2]


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _low_sample_line(entry: dict, stats: dict) -> str:
    if entry.get("lowSample"):
        return (f"⚠️ 樣本不足(<{stats['meta']['min_sample']} 場),僅供參考\n")
    return ""


def _stale_warning(stats: dict) -> str:
    cur = _current_patch()
    seen = stats["meta"].get("patches", {})
    if cur and seen and cur not in seen:
        newest = next(iter(seen))
        return (f"⚠️ 統計資料來自 patch {newest},目前已是 {cur};"
                f"平衡改動後參考價值下降,建議重新爬取。\n\n")
    return ""


def _source_line(stats: dict) -> str:
    meta = stats["meta"]
    patches = "、".join(f"{p}({n} 場)" for p, n in
                        list(meta.get("patches", {}).items())[:3])
    return ("─" * 30 + "\n"
            f"資料來源:Riot Match-V5 · {meta['matches']} 場台服競技場對戰"
            f" · patch {patches} · 產生於 {meta.get('generated_at', '?')}\n"
            f"📌 雪球取樣自個人對戰圈,非全服統計;"
            f"同組合 <{meta['min_pair']} 場的搭配不收錄。")


def _stat_line(e: dict, noun: str = "場次") -> str:
    return (f"🎮 {noun}:{e['games']} | 🏆 勝率(第1名):{_pct(e.get('firstRate', 0))}"
            f" | 🥈 前二率:{_pct(e['top2Rate'])}"
            f" | 🥇 平均名次:{e['avgPlace']:.2f}")


def _pair_line(i: int, name: str, t: dict, total: int) -> str:
    share = f"(佔 {t['games'] / total * 100:.0f}%)" if total else ""
    return (f" {i}. {name} — 選取 {t['games']} 場{share}"
            f" · 勝率 {_pct(t.get('firstRate', 0))}"
            f" · 平均名次 {t['avgPlace']:.2f}")


def _format_champion(cid: str, stats: dict) -> str:
    c = stats["champions"][cid]
    lines = [f"🏟️ 競技場英雄統計:{c['nameZh']}({c['nameEn']})",
             "─" * 30,
             _stat_line(c),
             _baseline_note(stats)]
    low = _low_sample_line(c, stats)
    if low:
        lines.append(low.rstrip())
    lines.append("")
    if c["topAugments"]:
        lines.append(f"📈 最常選取的強化(選取次數排序,"
                     f"同組合 ≥{stats['meta']['min_pair']} 場):")
        for i, t in enumerate(c["topAugments"], 1):
            icon = _rarity_icon(stats["augments"]
                                .get(str(t["id"]), {}).get("rarity", -1))
            lines.append(_pair_line(i, f"{icon} {t['nameZh']}", t, c["games"]))
    else:
        lines.append(f"📈 樣本不足,尚無可信的強化搭配統計"
                     f"(門檻:同組合 ≥{stats['meta']['min_pair']} 場)。")
    lines += ["", _source_line(stats)]
    return "\n".join(lines)


def _format_augment(aid: str, stats: dict) -> str:
    a = stats["augments"][aid]
    icon = _rarity_icon(a["rarity"])
    lines = [f"{icon} 強化實戰統計:{a['nameZh']}({a['nameEn']})",
             "─" * 30,
             _stat_line(a, noun="出場"),
             _baseline_note(stats)]
    low = _low_sample_line(a, stats)
    if low:
        lines.append(low.rstrip())
    lines.append("")
    if a["topChamps"]:
        lines.append(f"👥 選取率最高的英雄(選取次數排序,"
                     f"同組合 ≥{stats['meta']['min_pair']} 場):")
        for i, t in enumerate(a["topChamps"], 1):
            lines.append(_pair_line(i, f"{t['champZh']}({t['champ']})",
                                    t, a["games"]))
    else:
        lines.append(f"👥 樣本不足,尚無可信的英雄搭配統計"
                     f"(門檻:同組合 ≥{stats['meta']['min_pair']} 場)。")
    lines += ["", _source_line(stats)]
    return "\n".join(lines)


def _leaderboard(stats: dict, which: str, limit: int = 10) -> list[str]:
    """which: "champions" 或 "augments"。勝率(奪冠率)高者在前。"""
    min_sample = stats["meta"]["min_sample"]
    pool = [e for e in stats[which].values() if not e.get("lowSample")]
    if which == "augments":
        # 📦 特殊類(鐵砧/欄位/修復等功能性選項)不是真正的強化,
        # 會洗版排行榜 → 排除;個別查詢仍查得到
        pool = [e for e in pool if e.get("rarity") != 4]
    pool.sort(key=lambda e: (-e.get("firstRate", 0), -e["top2Rate"], -e["games"]))
    title = ("🏆 競技場英雄勝率排行" if which == "champions"
             else "🏆 競技場強化勝率排行(不含鐵砧/道具等特殊類)")
    lines = [f"{title}(勝率 = 第 1 名率,樣本 ≥{min_sample} 場)"]
    if not pool:
        lines.append(f"(還沒有任何項目達到 {min_sample} 場門檻,先多爬一些資料吧)")
        return lines
    for i, e in enumerate(pool[:limit], 1):
        if which == "champions":
            name = f"{e['nameZh']}({e['nameEn']})"
        else:
            name = f"{_rarity_icon(e['rarity'])} {e['nameZh']}"
        lines.append(f" {i:>2}. {name} — 勝率 {_pct(e.get('firstRate', 0))}"
                     f" · 前二率 {_pct(e['top2Rate'])}"
                     f" · 平均名次 {e['avgPlace']:.2f} · {e['games']} 場")
    return lines


_KIND_ALIASES = {
    "champions": "champions", "champion": "champions", "champ": "champions",
    "英雄": "champions", "hero": "champions",
    "augments": "augments", "augment": "augments",
    "強化": "augments", "海克斯": "augments",
}

_NO_DATA_MSG = (
    "📊 尚未產生統計資料(本機功能,需先爬取)。\n"
    "步驟(在專案根目錄,需要 Riot API key 放在 .env):\n"
    "  1. uv run python scripts/crawl_arena.py \"你的名字#TW2\"\n"
    "  2. uv run python scripts/build_arena_stats.py\n"
    "詳見 NOTES.md 2026-07-17 的說明。")


def do_arena_stats(query: str = "", kind: str = "auto") -> str:
    stats = load_stats()
    if stats is None:
        return _NO_DATA_MSG
    kind = _KIND_ALIASES.get(kind.strip().lower(), "auto")
    warn = _stale_warning(stats)

    if not query.strip():
        if kind == "champions":
            body = _leaderboard(stats, "champions")
        elif kind == "augments":
            body = _leaderboard(stats, "augments")
        else:
            body = (_leaderboard(stats, "champions")
                    + [""] + _leaderboard(stats, "augments"))
        return warn + "\n".join(body + ["", _source_line(stats)])

    # 有查詢字串:依 kind 決定順序,auto 先英雄後強化
    if kind in ("auto", "champions"):
        cid = _find_champion(query, stats)
        if cid and cid in stats["champions"]:
            return warn + _format_champion(cid, stats)
        if kind == "champions":
            hint = f"(有解析到英雄「{cid}」但樣本中沒有場次)" if cid else ""
            return (f"找不到英雄「{query}」的統計{hint}。"
                    f"試試中文或英文名,例如「悟空」或 Garen。")
    if kind in ("auto", "augments"):
        aid = _find_augment(query, stats)
        if aid and aid in stats["augments"]:
            return warn + _format_augment(aid, stats)
    return (f"找不到「{query}」對應的英雄或強化統計。\n"
            f"可以:留空 query 看排行榜、或給明確名稱"
            f"(例:「地獄三頭犬」、「蓋倫」、Cerberus、Garen)。")
