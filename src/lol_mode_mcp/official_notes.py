"""Riot 官方繁中 patch notes 解析:patch 改動的「正宗台服中文」來源。

wiki 的 patch 頁本來就是轉錄官方 patch notes,所以官方繁中頁面
有同樣內容的 Riot 官方翻譯 —— 中文版直接用它,專有名詞天生全對,
不需要規則式翻譯。英文版仍用 wiki(結構化程度較好)。

頁面是伺服器端渲染(不用跑 JS),內容在 #patch-notes-container:
  <h2>競技場</h2> … <h4>增幅裝置</h4>
  <p><strong>增益麻吉</strong></p><ul><li>改動行…</li></ul>
一般對戰的英雄則是 <h3>巴德</h3> + <h4>技能名</h4> + <li>。
注意:要帶瀏覽器 User-Agent 並跟隨 307 轉址。

slug 規則:26.4 起是 league-of-legends-patch-26-13-notes,
更早是 patch-26-2-notes,兩種都試。
"""

from __future__ import annotations

import html as html_mod
import logging
import re

import httpx

from . import cache

logger = logging.getLogger(__name__)

_BASE = "https://www.leagueoflegends.com/zh-tw/news/game-updates/"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 lol-mode-mcp")

# h2 標題 → scope(其餘 h2 段落如造型/積分對戰忽略)
_H2_SCOPE = [
    ("競技場", "arena"),
    ("大混戰", "mayhem"),
    ("英雄", "general"),
    ("道具", "general"),
    ("符文", "general"),
    ("召喚師技能", "general"),
]

_TOKEN_RE = re.compile(
    r"<(h2|h3|h4)[^>]*>(.*?)</\1>"           # 標題
    r"|<p[^>]*>\s*<strong[^>]*>(.*?)</strong>\s*</p>"  # 條目名(競技場式)
    r"|<li[^>]*>(.*?)</li>",                 # 改動行
    re.S)


def _text(fragment: str) -> str:
    s = re.sub(r"<[^>]+>", "", fragment)
    s = html_mod.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_official_notes(page_html: str) -> dict[str, list[dict]]:
    """整頁 HTML → {"arena"/"general"/"mayhem": [{"category", "entries"}]}。"""
    i = page_html.find("patch-notes-container")
    if i < 0:
        raise ValueError("patch-notes-container not found — page layout changed?")
    body = page_html[i:]

    scopes: dict[str, list[dict]] = {"arena": [], "general": [], "mayhem": []}
    scope: str | None = None
    style: str | None = None   # "flat"=競技場/大混戰(h4=分類);"champ"=一般對戰
    cat: dict | None = None
    entry: dict | None = None

    def new_cat(name: str) -> None:
        nonlocal cat, entry
        cat = {"category": name, "entries": []}
        scopes[scope].append(cat)
        entry = None

    for m in _TOKEN_RE.finditer(body):
        tag, htext, strong, li = m.group(1), m.group(2), m.group(3), m.group(4)
        if tag == "h2":
            text = _text(htext)
            scope = None
            for key, sc in _H2_SCOPE:
                if key in text:
                    scope, style = sc, ("champ" if sc == "general" else "flat")
                    if sc == "general":
                        new_cat(text)  # 英雄/道具 等,h2 本身就是分類
                    break
            continue
        if scope is None:
            continue
        if tag == "h4" and style == "flat":
            new_cat(_text(htext))
        elif tag == "h3" and style == "champ":
            if cat is None:
                new_cat("其他")
            entry = {"name": _text(htext), "lines": []}
            cat["entries"].append(entry)
        elif tag == "h4" and style == "champ":
            if entry is not None:
                entry["lines"].append("- " + _text(htext))
        elif strong is not None and style == "flat":
            if cat is None:
                new_cat("其他")
            entry = {"name": _text(strong), "lines": []}
            cat["entries"].append(entry)
        elif li is not None and entry is not None:
            # champ 式:li 掛在最近的技能(h4)之下縮一層;flat 式不縮
            indent = "  " if (style == "champ" and any(
                ln.startswith("- ") for ln in entry["lines"])) else ""
            entry["lines"].append(f"{indent}- {_text(li)}")
    # 清掉空分類
    for sc in scopes:
        scopes[sc] = [c for c in scopes[sc] if c["entries"]]
    return scopes


def _slug_candidates(title: str) -> list[str]:
    m = re.match(r"V(\d+)\.(\d+)$", title)
    if not m:
        return []
    y, mm = m.group(1), str(int(m.group(2)))  # 26.09 → 26-9
    return [f"league-of-legends-patch-{y}-{mm}-notes",
            f"patch-{y}-{mm}-notes"]


def _fetch_official_zh(title: str) -> dict:
    last_exc: Exception | None = None
    for slug in _slug_candidates(title):
        try:
            r = httpx.get(_BASE + slug, timeout=25, follow_redirects=True,
                          headers={"User-Agent": _UA})
            if r.status_code != 200:
                continue
            scopes = parse_official_notes(r.text)
            if any(scopes.values()):
                logger.info("official zh notes %s: arena %d / general %d / "
                            "mayhem %d categories", title,
                            len(scopes["arena"]), len(scopes["general"]),
                            len(scopes["mayhem"]))
                return {"patch": title, "scopes": scopes}
        except Exception as exc:  # noqa: BLE001 — 逐 slug 嘗試,最後統一報錯
            last_exc = exc
    raise ValueError(f"official zh-tw notes for {title} unavailable"
                     + (f": {last_exc}" if last_exc else ""))


def get_official_zh(title: str) -> cache.CacheResult:
    return cache.get_cached(f"official_zh_{title}",
                            lambda: _fetch_official_zh(title))
