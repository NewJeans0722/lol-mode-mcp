"""競技場對戰爬蟲:從一個 Riot ID 出發,雪球式收集台服競技場場次存 JSONL。

用法(在專案根目錄):
    uv run python scripts/crawl_arena.py "你的名字#TW2" --minutes 30 --max-matches 1000

需要 Riot API key(dev key 每 24h 過期,https://developer.riotgames.com):
    repo 根目錄 .env 寫一行 RIOT_API_KEY=RGAPI-xxxx(已 gitignore),
    或 PowerShell 設 $env:RIOT_API_KEY="RGAPI-xxxx"。

設計重點(詳見 NOTES.md 2026-07-17):
- 限速:固定 1.3 秒/請求 ≈ 92 req/2min,永遠低於 dev key 的
  100 req/2min 與 20 req/s 兩條上限,一行 sleep 解決
- 續跑:啟動時掃輸出檔已抓的 matchId,重跑自動跳過(Ctrl+C 安全)
- 雪球:每場的其他 15 位玩家 PUUID 進佇列,從個人對戰圈往外擴散
- 403(key 過期)→ 提示 regenerate 後乾淨退出,已抓資料都在檔案裡
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lol_mode_mcp.arena_stats import DEFAULT_QUEUE, trim_match  # noqa: E402

# 台服(TW2):帳號查詢走 asia,對戰紀錄走 sea(SEA 區域叢集)
ACCOUNT_URL = "https://asia.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}"
IDS_URL = "https://sea.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
MATCH_URL = "https://sea.api.riotgames.com/lol/match/v5/matches/{mid}"

DEFAULT_OUT = ROOT / "crawl_data" / "arena_matches.jsonl"


class ApiKeyError(Exception):
    """401/403:key 無效或過期。"""


def load_api_key() -> str:
    key = os.environ.get("RIOT_API_KEY", "").strip()
    if not key:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == "RIOT_API_KEY":
                    key = v.strip().strip('"').strip("'")
    if not key:
        raise SystemExit("找不到 RIOT_API_KEY:請在 repo 根目錄 .env 寫 "
                         "RIOT_API_KEY=RGAPI-... 或設環境變數後重跑。")
    return key


class RiotClient:
    """唯一會打 Riot API 的地方:固定間隔限速 + 429/5xx 重試 + 403 明確報錯。"""

    def __init__(self, api_key: str, interval: float = 1.3):
        self.interval = interval
        self.requests = 0
        self._last = 0.0
        self._client = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=10.0),
            headers={"X-Riot-Token": api_key})

    def get(self, url: str, params: dict | None = None):
        for _ in range(6):
            wait = self._last + self.interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.requests += 1
            try:
                resp = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                print(f"  網路錯誤,3 秒後重試:{exc}")
                time.sleep(3)
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code in (401, 403):
                raise ApiKeyError(
                    "API key 無效或已過期(dev key 每 24 小時過期)。\n"
                    "   到 https://developer.riotgames.com 按 Regenerate,"
                    "更新 .env 的 RIOT_API_KEY 後重跑即可續抓。")
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After") or 10)
                print(f"  觸發限速(429),等待 {retry} 秒…")
                time.sleep(retry)
                continue
            print(f"  HTTP {resp.status_code},3 秒後重試")
            time.sleep(3)
        raise SystemExit("連續失敗多次,先停下來;稍後重跑會從斷點繼續。")


def load_progress(path: Path) -> tuple[set[str], list[str]]:
    """續跑:掃輸出檔收集已抓 matchId + 已知玩家 PUUID(壞行直接跳過)。

    PUUID 也要載入,否則重跑時舊場次全被跳過、雪球佇列長不大,
    爬蟲會立刻結束(實測踩過的坑,見 NOTES.md 2026-07-17)。
    掃過 id list 的玩家另記在 visited 檔:續跑時排到佇列尾,
    讓沒掃過的新玩家優先(否則上萬人重掃一輪,新場次等很久才進來)。
    """
    seen: set[str] = set()
    puuids: dict[str, None] = {}  # dict 當有序 set 用,保持發現順序
    if not path.exists():
        return seen, []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if m.get("matchId"):
            seen.add(m["matchId"])
        for p in m.get("participants", []):
            if p.get("puuid"):
                puuids[p["puuid"]] = None
    visited_file = path.with_name("visited_puuids.txt")
    scanned = (set(visited_file.read_text(encoding="utf-8").split())
               if visited_file.exists() else set())
    fresh = [p for p in puuids if p not in scanned]
    return seen, fresh + [p for p in puuids if p in scanned]


def crawl(riot_id: str, out_path: Path, max_matches: int, minutes: float,
          queue: int = DEFAULT_QUEUE, since: str = "") -> int:
    if "#" not in riot_id:
        raise SystemExit('Riot ID 格式是 名字#TAG,例如 "小明#TW2"。')
    name, _, tag = riot_id.partition("#")

    # --since:伺服器端過濾,只回傳該日期(當地時間 00:00)之後的場次,
    # 舊場次連 match id 都不會出現 → 請求全花在當前版本,不浪費配額
    ids_params: dict = {"queue": queue, "count": 100}
    if since:
        t = time.strptime(since, "%Y-%m-%d")
        ids_params["startTime"] = int(time.mktime(t))
        print(f"只抓 {since} 之後的場次(startTime={ids_params['startTime']})")

    client = RiotClient(load_api_key())
    seen, known_puuids = load_progress(out_path)
    if seen:
        print(f"檔案已有 {len(seen)} 場、{len(known_puuids)} 位已知玩家,"
              f"續跑跳過舊場次、從已知玩家繼續擴散。")

    acct = client.get(ACCOUNT_URL.format(name=quote(name), tag=quote(tag)))
    if acct is None:
        raise SystemExit(f"找不到帳號「{riot_id}」,請確認名字#TAG 拼法。")
    print(f"帳號確認:{acct.get('gameName')}#{acct.get('tagLine')}")

    deadline = time.time() + minutes * 60
    start = time.time()
    # ⚠️ 別命名成 queue:會蓋掉同名的 queue id 參數(踩過,deque 被
    # 當成 HTTP query 參數送出去,httpx 炸 "query too long")
    todo: deque[str] = deque([acct["puuid"]] + known_puuids)
    visited: set[str] = set()
    saved = 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = out_path.with_name("visited_puuids.txt").open("a", encoding="utf-8")
    with out_path.open("a", encoding="utf-8") as fh:
        try:
            while todo and saved < max_matches and time.time() < deadline:
                puuid = todo.popleft()
                if puuid in visited:
                    continue
                visited.add(puuid)
                ids = client.get(IDS_URL.format(puuid=puuid),
                                 params=ids_params) or []
                vf.write(puuid + "\n")
                vf.flush()
                for mid in ids:
                    if (mid in seen or saved >= max_matches
                            or time.time() >= deadline):
                        continue
                    raw = client.get(MATCH_URL.format(mid=mid))
                    seen.add(mid)
                    if raw is None:
                        continue
                    slim = trim_match(raw)
                    if slim is None:
                        continue
                    fh.write(json.dumps(slim, ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
                    fh.flush()  # 一場一寫,Ctrl+C 也不掉資料
                    saved += 1
                    for p in slim["participants"]:
                        if p["puuid"] and p["puuid"] not in visited:
                            todo.append(p["puuid"])
                    if saved % 10 == 0:
                        mins = (time.time() - start) / 60
                        print(f"進度:本次 +{saved} 場(檔案共 {len(seen)})"
                              f"|待訪玩家 {len(todo)}|{mins:.1f} 分鐘"
                              f"|{client.requests} 次請求", flush=True)
        except KeyboardInterrupt:
            print("\n手動中斷 —— 已抓的資料都在檔案裡,重跑即續。")
        except ApiKeyError as exc:
            print(f"\n❌ {exc}")

    vf.close()
    mins = (time.time() - start) / 60
    print(f"\n完成:本次新增 {saved} 場,檔案共 {len(seen)} 場"
          f"({out_path}),耗時 {mins:.1f} 分鐘。")
    if saved:
        print("下一步:uv run python scripts/build_arena_stats.py")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="雪球式收集台服競技場場次存 JSONL")
    ap.add_argument("riot_id", help='種子玩家 Riot ID,例如 "小明#TW2"')
    ap.add_argument("--max-matches", type=int, default=2500,
                    help="本次最多新增幾場(預設 2500)")
    ap.add_argument("--minutes", type=float, default=60,
                    help="最多跑幾分鐘(預設 60)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"輸出 JSONL 路徑(預設 {DEFAULT_OUT})")
    ap.add_argument("--queue", type=int, default=DEFAULT_QUEUE,
                    help="queue id:1750=現行競技場(18人,預設)、1700=舊制")
    ap.add_argument("--since", default="",
                    help="只抓此日期後的場次(YYYY-MM-DD,例:patch 上線日),"
                         "配額全花在當前版本")
    args = ap.parse_args()
    return crawl(args.riot_id, args.out, args.max_matches, args.minutes,
                 args.queue, args.since)


if __name__ == "__main__":
    raise SystemExit(main())
