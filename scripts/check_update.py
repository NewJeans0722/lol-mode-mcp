"""版本更新自檢:一次跑完,列出新 patch 需要人工處理的所有項目。

用法(在專案根目錄):
    uv run python scripts/check_update.py

新 patch 上線後跑這支,它會抓最新資料並逐項檢查「過往踩過的雷」,
把需要你動手的東西一次列清楚(而不是等使用者一個一個發現)。
綠色 [OK] 免處理;黃色 [需處理] 附上清單。全綠代表這版不用改。

檢查項目(對應 NOTES.md 的歷史問題):
  1. 版本一致性     —— ddragon / cdragon / wiki 是否同一 patch
  2. 競技場強化說明 —— 是否有 ? 未解佔位符或 @ 漏出(formatting bug)
  3. 競技場技能改動 —— MapChanges 有幾行規則翻不出(補 mapchanges_zh.json)
  4. Mayhem 強化說明 —— 幾個未完整中文(補 mayhem_zh.json)
  5. 人工對照時效   —— 對照檔裡有幾條 key 已對不上目前來源(原文改了)
  6. 貴賓/機制提醒  —— 季節輪替型,需人工比對官方 notes
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lol_mode_mcp import cache  # noqa: E402

GREEN, YELLOW, RED, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET} {msg}")


def todo(msg: str, items: list[str] | None = None) -> None:
    print(f"{YELLOW}[需處理]{RESET} {msg}")
    for it in (items or [])[:40]:
        print(f"        - {it}")
    if items and len(items) > 40:
        print(f"        …另有 {len(items) - 40} 項")


def fail(msg: str) -> None:
    print(f"{RED}[錯誤]{RESET} {msg}")


def main() -> int:
    cache.clear()
    need_work = 0

    # 1) 版本一致性 -----------------------------------------------------------
    print("\n== 1. 版本一致性 ==")
    from lol_mode_mcp.http_util import fetch_json
    try:
        ddragon = fetch_json(
            "https://ddragon.leagueoflegends.com/api/versions.json")[0]
        meta = fetch_json(
            "https://raw.communitydragon.org/latest/content-metadata.json")
        cdragon = str(meta.get("version", "?")).split("+")[0]
        patch_pages = fetch_json(
            "https://wiki.leagueoflegends.com/en-us/api.php",
            params={"action": "query", "list": "allpages", "apprefix": "V2",
                    "aplimit": "500", "format": "json", "formatversion": "2"})
        wiki_patches = sorted(
            (p["title"] for p in patch_pages["query"]["allpages"]
             if re.match(r"^V\d\d\.\d\d$", p["title"])), reverse=True)
        dd_minor = ".".join(ddragon.split(".")[:2])
        cd_minor = ".".join(cdragon.split(".")[:2])
        print(f"     ddragon={ddragon}  cdragon={cdragon}  "
              f"wiki 最新={wiki_patches[0]}")
        if dd_minor == cd_minor:
            ok(f"ddragon 與 cdragon 同版({dd_minor})")
        else:
            need_work += 1
            todo(f"ddragon({dd_minor})與 cdragon({cd_minor})版本不一致 —— "
                 "某個來源還沒更新,晚點再跑一次")
    except Exception as exc:  # noqa: BLE001
        fail(f"版本檢查失敗:{exc}")

    # 2) 競技場強化說明:@ 漏出(真 bug)/ 遊戲內即時值(可接受) -------------
    print("\n== 2. 競技場強化說明品質 ==")
    from lol_mode_mcp.arena import get_arena_data
    data = get_arena_data().data
    leaks, ingame = [], []
    for a in data.augments:
        for d in (a.desc_zh, a.desc_en):
            if re.search(r"@[^@\s]{1,60}@", d):
                leaks.append(f"{a.name_zh}({a.name_en})")
                break
        if "(依遊戲內數值)" in a.desc_zh:
            ingame.append(a.name_zh)
    if leaks:
        need_work += 1
        todo(f"{len(leaks)} 個強化 @ 佔位符漏出(formatting.py 要修):", leaks)
    else:
        ok(f"{len(data.augments)} 個競技場強化說明無 @ 漏出")
    if ingame:
        # 官方原文 + 誠實退回,非 bug、翻譯無法補;僅告知
        print(f"     (附註:{len(ingame)} 個含「(依遊戲內數值)」——"
              f"官方原文即為遊戲內即時計算,可接受,不需處理。)")

    # 3) 競技場技能改動:MapChanges 規則翻不出的行 ---------------------------
    print("\n== 3. 競技場逐技能改動翻譯 ==")
    from lol_mode_mcp.arena_balance import (build_entity_name_map,
                                            get_map_changes,
                                            group_champion_changes)
    from lol_mode_mcp.champions import get_champions, get_spell_names
    from lol_mode_mcp.translate import translate_lines
    champs = get_champions().data
    spells = get_spell_names().data
    base = build_entity_name_map()
    grouped = group_champion_changes(get_map_changes().data["champions"], champs)
    by_en = {c.name_en: c for c in champs}
    miss3 = []
    for name_en, entries in grouped.items():
        nm = {**base, **spells.get(by_en[name_en].id, {}).get("by_en", {})}
        for _label, lines in entries:
            for res in translate_lines(lines, nm):
                if "🔤" in res:
                    miss3.append(f"{by_en[name_en].name_zh}:{res[:60]}")
    if miss3:
        need_work += 1
        todo(f"{len(miss3)} 行翻不出(補進 data/mapchanges_zh.json):", miss3)
    else:
        ok("競技場技能改動 100% 可翻")

    # 4) Mayhem 強化說明:未完整中文 ----------------------------------------
    print("\n== 4. ARAM Mayhem 強化說明翻譯 ==")
    from lol_mode_mcp.mayhem_augments import get_mayhem_codex
    codex = get_mayhem_codex().data
    miss4 = [f"{e.get('nameZh') or e['nameEn']}({e['nameEn']})"
             for e in codex if not e["descComplete"]]
    if miss4:
        need_work += 1
        todo(f"{len(miss4)}/{len(codex)} 個未完整中文"
             "(補進 data/mayhem_zh.json,key=英文強化名):", miss4)
    else:
        ok(f"{len(codex)} 個 Mayhem 強化 100% 完整中文")

    # 5) 人工對照時效:key 對不上目前來源 ------------------------------------
    print("\n== 5. 人工對照檔時效 ==")
    import json
    data_dir = Path(__file__).resolve().parent.parent / "src" / "lol_mode_mcp" / "data"
    # mayhem_zh:key 應仍是現存強化英文名
    mzh = json.loads((data_dir / "mayhem_zh.json").read_text(encoding="utf-8"))
    live_names = {e["nameEn"] for e in codex}
    orphan_m = [k for k in mzh if k not in live_names]
    if orphan_m:
        todo(f"mayhem_zh.json 有 {len(orphan_m)} 條 key 已不在強化清單"
             "(強化被移除或改名,可刪):", orphan_m)
    else:
        ok("mayhem_zh.json 的 key 全部對得上目前強化")

    # 6) 貴賓/機制:季節輪替提醒 --------------------------------------------
    print("\n== 6. 機制/貴賓(季節輪替,需人工) ==")
    todo("貴賓名單每個賽季輪替,wiki 表會落後 —— 大改版時請以官方繁中 "
         "notes 的「特別嘉賓」段落核對 data/mode_mechanics.json;"
         "回合獎勵表、Mayhem 進度等也順手比對。")

    # 總結 -------------------------------------------------------------------
    print("\n" + "=" * 50)
    if need_work == 0:
        print(f"{GREEN}資料翻譯類全數就緒,這版不需人工補翻。{RESET}")
        print("(第 6 項的機制/貴賓仍建議大改版時人工掃一眼。)")
    else:
        print(f"{YELLOW}共 {need_work} 類需要人工處理,詳見上方清單。{RESET}")
        print("處理後跑 `uv run pytest -q`,再 commit + push 自動部署。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
