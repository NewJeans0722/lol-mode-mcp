"""模式機制說明:讀 data/mode_mechanics.json 排版成文字。

內容是手工整理的中文摘要(事實來自官方 patch notes 與 wiki),
沒有英文版;機率與英雄限定名單官方未公開,JSON 內有誠實聲明條目。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import cache
from .champions import get_champions

logger = logging.getLogger(__name__)

MECHANICS_PATH = Path(__file__).resolve().parent / "data" / "mode_mechanics.json"

_MODE_ALIASES = {
    "arena": "arena", "競技場": "arena", "cherry": "arena",
    "aram": "aram", "嚎哭深淵": "aram", "深淵": "aram",
    "mayhem": "mayhem", "大混戰": "mayhem", "aram: mayhem": "mayhem",
    "aram_mayhem": "mayhem", "kiwi": "mayhem",
}


def load_mechanics() -> dict:
    return json.loads(MECHANICS_PATH.read_text(encoding="utf-8"))


def _guest_zh(name_en: str) -> str:
    """貴賓英雄的台服名(查不到就英文)。"""
    try:
        for c in get_champions().data:
            if c.name_en == name_en:
                return c.name_zh
    except cache.DataUnavailableError:
        pass
    return name_en


def do_mode_mechanics(mode: str = "arena") -> str:
    key = _MODE_ALIASES.get(mode.strip().lower())
    data = load_mechanics()
    if key is None or key not in data:
        return ("看不懂模式「%s」。可查:arena(競技場)、aram(嚎哭深淵)、"
                "mayhem(ARAM: Mayhem)。" % mode)
    section = data[key]
    phase_label = {0: "任一輪", 1: "第一輪", 2: "第二輪"}
    lines = [f"{section['name_zh']} — 模式機制"]
    for sec in section["sections"]:
        lines += ["", f"【{sec['topic']}】"]
        lines += [f"- {ln}" for ln in sec.get("lines", [])]
        for g in sec.get("guests", []):
            zh = _guest_zh(g["nameEn"])
            lines.append(f"▸ {zh}({g['nameEn']},{phase_label.get(g['phase'], '?')})"
                         f":{g['effect']}")
    lines += ["", f"資料來源:{data['_meta']['sources']};"
                  f"整理於 {data['_meta']['last_reviewed']}"]
    return "\n".join(lines)
