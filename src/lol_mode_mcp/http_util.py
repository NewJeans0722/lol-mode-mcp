"""共用的 HTTP 抓取:統一 timeout、User-Agent 與錯誤處理。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 對外部服務標明身分是禮貌,也是 LoL Wiki(MediaWiki)API 的建議做法
USER_AGENT = "lol-mode-mcp/0.1 (personal MCP project; github.com/NewJeans0722/lol-mode-mcp)"

TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def fetch_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET 一個 JSON;任何網路/HTTP/解析錯誤都以例外浮出,由快取層決定退回策略。"""
    logger.info("GET %s", url)
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
