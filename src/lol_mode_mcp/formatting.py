"""把 CommunityDragon 的原始說明文字轉成人類可讀的純文字。

原始資料長這樣(zh_tw 範例):
    "增加<scaleAP>@APAmp*100@%魔攻</scaleAP>。<br><br>..."

要處理兩件事:
1. @變數@ 佔位符:值放在 augment 的 dataValues,是長度 7 的陣列。
   實測發現 `desc` 欄位的佔位符和 dataValues 直接對得上
   (例如 APAmp=0.15 → @APAmp*100@ → 15%),而 `tooltip` 欄位
   引用的是遊戲內即時計算值(@f1@ 之類),對不上 —— 所以顯示用 desc。
   陣列裡的值若不同(部分強化可升級),把不同的值用「/」串起來,
   例如 "10/20",忠實呈現而不猜哪個 index 才對。
2. HTML 風格標籤:<br> 換行、其他標籤(<scaleAP> 等)去殼留字。
"""

from __future__ import annotations

import re
from typing import Any

_TAG_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_ANY = re.compile(r"</?[a-zA-Z][^>]*>")
_PLACEHOLDER = re.compile(r"@([A-Za-z0-9_]+)(?:\*(-?\d+(?:\.\d+)?))?@")
_SPRITE = re.compile(r"%i:[A-Za-z0-9_]+%")  # 遊戲內圖示標記,純文字顯示不了


def _fmt_number(v: float) -> str:
    """0.009999999776 → 0.01、20.0 → 20:先四捨五入再去掉小數尾巴。"""
    rounded = round(v, 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"


def _render_values(values: list[float], multiplier: float | None) -> str:
    """dataValues 的陣列 → 顯示字串;不同的值用 / 串接(依出現順序去重)。"""
    if multiplier is not None:
        values = [v * multiplier for v in values]
    seen: list[str] = []
    for v in values:
        s = _fmt_number(v)
        if s not in seen:
            seen.append(s)
    return "/".join(seen)


def _calc_lookup(calculations: dict[str, Any], name: str) -> str | None:
    """有些佔位符指向 calculations 區塊,最單純的形態是轉指一個 dataValue。

    例:"APAmpCalcTooltip": {"mFormulaParts": [{"mDataValue": "APAmp"}]}
    更複雜的公式(乘上英雄等級等)無法離線算,回 None 讓上層標記。
    """
    calc = calculations.get(name)
    if not isinstance(calc, dict):
        return None
    parts = calc.get("mFormulaParts")
    if isinstance(parts, list) and len(parts) == 1 and isinstance(parts[0], dict):
        dv = parts[0].get("mDataValue")
        if isinstance(dv, str):
            return dv
    return None


def render_description(text: str, data_values: dict[str, list[float]],
                       calculations: dict[str, Any] | None = None) -> str:
    """佔位符代入 + 標籤清理,回傳純文字說明。"""
    calculations = calculations or {}
    # dataValues 的 key 大小寫在不同 augment 間不一致,做個不分大小寫索引
    dv_ci = {k.lower(): v for k, v in data_values.items()}

    def _sub(m: re.Match[str]) -> str:
        name, mult = m.group(1), m.group(2)
        multiplier = float(mult) if mult else None
        values = dv_ci.get(name.lower())
        if values is None:
            # 試著從 calculations 轉指回 dataValues
            redirect = _calc_lookup(calculations, name)
            if redirect is not None:
                values = dv_ci.get(redirect.lower())
        if values is None:
            return "?"  # 離線解不出來(遊戲內即時值),誠實標記
        return _render_values(list(values), multiplier)

    text = _PLACEHOLDER.sub(_sub, text)
    text = _TAG_BR.sub("\n", text)
    text = _TAG_ANY.sub("", text)
    text = _SPRITE.sub("", text)
    # 收斂連續空行
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def first_sentence(text: str, limit: int = 55) -> str:
    """取說明的第一句(或截斷),給清單用的一行摘要。"""
    text = text.split("\n")[0]
    for sep in ("。", ". "):
        idx = text.find(sep)
        if 0 < idx < limit:
            return text[: idx + 1]
    if len(text) > limit:
        return text[:limit] + "…"
    return text
