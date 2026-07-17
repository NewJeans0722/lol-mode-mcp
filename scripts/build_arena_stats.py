"""聚合爬蟲資料 → src/lol_mode_mcp/data/arena_stats.json(靜態,免 API key)。

用法(在專案根目錄,先跑過 crawl_arena.py):
    uv run python scripts/build_arena_stats.py
    uv run python scripts/build_arena_stats.py --patch 26.14   # 只算指定 patch

需要網路(抓強化/英雄的中文名對照,免 API key 的既有來源),
但完全不需要 RIOT_API_KEY —— 聚合本身是離線計算。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lol_mode_mcp.arena import get_arena_data  # noqa: E402
from lol_mode_mcp.arena_stats import STATS_PATH, aggregate_stats  # noqa: E402
from lol_mode_mcp.champions import get_champions  # noqa: E402
from lol_mode_mcp.http_util import fetch_json  # noqa: E402
from lol_mode_mcp.patch_notes import CHERRY_AUG_URL  # noqa: E402

DEFAULT_IN = ROOT / "crawl_data" / "arena_matches.jsonl"

_CHERRY_RARITY = {"kSilver": 0, "kGold": 1, "kPrismatic": 2}


def fill_missing_from_cherry(augment_meta: dict, needed: set[int]) -> None:
    """cdragon arena json(226 筆)缺的新強化 id,用 cherry-augments
    (624 筆總目錄,含新制競技場強化)補名稱與稀有度。"""
    missing = needed - set(augment_meta)
    if not missing:
        return
    try:
        en = {a["id"]: a for a in fetch_json(CHERRY_AUG_URL.format(loc="default"))}
        zh = {a["id"]: a for a in fetch_json(CHERRY_AUG_URL.format(loc="zh_tw"))}
    except Exception as exc:
        print(f"⚠️ cherry-augments 補名失敗(統計不受影響,名稱會顯示 #id):{exc}")
        return
    filled = 0
    for aid in missing:
        a_en = en.get(aid)
        if not a_en:
            continue
        augment_meta[aid] = {
            "nameZh": zh.get(aid, {}).get("nameTRA") or a_en.get("nameTRA", ""),
            "nameEn": a_en.get("nameTRA", ""),
            "rarity": _CHERRY_RARITY.get(a_en.get("rarity"), -1),
        }
        filled += 1
    print(f"cherry-augments 補名:{filled}/{len(missing)} 個新強化 id")


def load_matches(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"找不到 {path},請先跑 scripts/crawl_arena.py 收集資料。")
    matches, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            matches.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    if bad:
        print(f"⚠️ 跳過 {bad} 行壞資料(通常是中斷時寫到一半,無礙)")
    return matches


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="聚合競技場場次 → arena_stats.json")
    ap.add_argument("--input", type=Path, default=DEFAULT_IN)
    ap.add_argument("--patch", default="latest",
                    help="latest=只統計資料中最新 patch(預設,使用者只要"
                         "當前版本)、all=全部、或指定版號(例 16.14)")
    ap.add_argument("--queue", default="1750",
                    help="queue 過濾:1750=現行競技場(預設)、1700=舊制、"
                         "all=不過濾(新舊制平衡不同,不建議混)")
    ap.add_argument("--min-sample", type=int, default=30,
                    help="整體樣本低於此標「樣本不足」(預設 30)")
    ap.add_argument("--min-pair", type=int, default=10,
                    help="英雄×強化配對低於此不收錄(預設 10)")
    ap.add_argument("--out", type=Path, default=STATS_PATH)
    args = ap.parse_args()

    matches = load_matches(args.input)
    if args.queue != "all":
        # 早期抓的紀錄沒存 queue 欄位,那批都是舊制 1700
        q = int(args.queue)
        matches = [m for m in matches if m.get("queue", 1700) == q]
    if args.patch == "latest":
        known = {m["patch"] for m in matches if m.get("patch", "") != "unknown"}
        if known:
            latest = max(known, key=lambda p: tuple(map(int, p.split("."))))
            print(f"只統計最新 patch {latest}(--patch all 可統計全部)")
            matches = [m for m in matches if m.get("patch") == latest]
    elif args.patch != "all":
        matches = [m for m in matches if m.get("patch") == args.patch]
    if not matches:
        raise SystemExit("沒有可統計的場次(queue/patch 過濾後為空?)。"
                         "現行競技場是 queue 1750,舊資料要用 --queue 1700。")

    print(f"讀入 {len(matches)} 場,抓取名稱對照…")
    try:
        augment_meta = {a.id: {"nameZh": a.name_zh, "nameEn": a.name_en,
                               "rarity": a.rarity}
                        for a in get_arena_data().data.augments}
        champ_meta = {c.id: {"nameZh": c.name_zh, "nameEn": c.name_en}
                      for c in get_champions().data}
    except Exception as exc:
        raise SystemExit(f"名稱對照抓取失敗(需要網路,不需要 API key):{exc}")

    needed = {aid for m in matches for p in m["participants"]
              for aid in p["augments"]}
    fill_missing_from_cherry(augment_meta, needed)

    stats = aggregate_stats(matches, augment_meta, champ_meta,
                            min_sample=args.min_sample, min_pair=args.min_pair)
    stats["meta"]["generated_at"] = time.strftime("%Y-%m-%d %H:%M UTC",
                                                  time.gmtime())
    stats["meta"]["region"] = "TW2 (SEA)"
    stats["meta"]["queue"] = args.queue
    stats["meta"]["source"] = (f"Riot Match-V5(queue {args.queue});"
                               "雪球取樣自個人對戰圈,非全服統計")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(stats, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    # 數學不變量自檢:名次均勻分布 → 全體平均/前二率必等於基準
    # (基準由隊伍數決定:8 隊 4.5/0.25、9 隊 5.0/0.222)
    base_avg = stats["meta"]["baselineAvgPlace"]
    base_top2 = stats["meta"]["baselineTop2Rate"]
    total = sum(c["games"] for c in stats["champions"].values())
    avg = (sum(c["avgPlace"] * c["games"] for c in stats["champions"].values())
           / total)
    top2 = (sum(c["top2Rate"] * c["games"] for c in stats["champions"].values())
            / total)
    flag = ("" if abs(avg - base_avg) < 0.1 and abs(top2 - base_top2) < 0.02
            else " ⚠️ 偏離基準,資料可能有問題!")
    print(f"自檢:全體平均名次 {avg:.3f}(基準 {base_avg})、"
          f"前二率 {top2:.3f}(基準 {base_top2}){flag}")

    print(f"完成:{stats['meta']['matches']} 場 → "
          f"{len(stats['augments'])} 個強化、{len(stats['champions'])} 隻英雄"
          f" → {args.out}")
    print(f"patch 分布:{stats['meta']['patches']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
