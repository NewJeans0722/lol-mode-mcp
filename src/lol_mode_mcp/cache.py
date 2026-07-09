"""In-memory TTL cache with stale-fallback.

為什麼這樣設計:
- MCP server 部署在雲端 serverless 時「不保證跨請求保留狀態」,
  所以快取只是加速器,不是必需品 —— 任何一次請求都能從零重建。
- 過期後重抓失敗時,退回上次成功的快取(stale),並讓呼叫端知道
  資料可能過期,由 tool 在回覆中註明。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 預設 12 小時過期,可用環境變數覆寫(單位:秒)
DEFAULT_TTL_SECONDS = int(os.environ.get("LOL_MCP_CACHE_TTL", 12 * 3600))


class DataUnavailableError(Exception):
    """抓取失敗且沒有任何舊快取可退回。"""


@dataclass
class CacheResult:
    data: Any
    fetched_at: float  # epoch seconds
    is_stale: bool     # True = 這份資料已過期且重抓失敗,僅供退回使用

    @property
    def fetched_at_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(self.fetched_at))


_store: dict[str, tuple[Any, float]] = {}


def get_cached(key: str, fetch_fn: Callable[[], Any],
               ttl: float = DEFAULT_TTL_SECONDS) -> CacheResult:
    """取快取;過期就重抓;重抓失敗退回舊資料(標記 stale)。

    fetch_fn 失敗時必須丟例外(而不是回傳 None),才能觸發退回機制。
    """
    now = time.time()
    entry = _store.get(key)

    if entry is not None and now - entry[1] < ttl:
        return CacheResult(data=entry[0], fetched_at=entry[1], is_stale=False)

    try:
        data = fetch_fn()
    except Exception as exc:
        if entry is not None:
            logger.warning("refresh failed for %r, falling back to stale cache "
                           "(fetched %s ago): %s", key, int(now - entry[1]), exc)
            return CacheResult(data=entry[0], fetched_at=entry[1], is_stale=True)
        logger.error("fetch failed for %r and no cache to fall back to: %s", key, exc)
        raise DataUnavailableError(str(exc)) from exc

    _store[key] = (data, now)
    logger.info("cache refreshed: %r", key)
    return CacheResult(data=data, fetched_at=now, is_stale=False)


def clear() -> None:
    """測試用:清空快取。"""
    _store.clear()
