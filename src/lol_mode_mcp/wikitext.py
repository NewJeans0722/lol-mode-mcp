"""wikitext 模板清理器:把 LoL Wiki 的 {{模板}} 與 [[連結]] 轉成純文字。

不是通用 wikitext parser —— 只覆蓋 Module:MapChanges/data/ar 全檔掃描
實際出現過的模板(ap/as/pp/fd/rd/tip/sbc/ai/ii/aug/g/tt…)。
策略:反覆把「最內層」的 {{...}}(內容已不含大括號者)換成文字,
直到沒有模板為止;巢狀(實測最深約 3 層模板)自然逐層化簡。

模板語意皆查證過原始碼(見 NOTES.md):
- {{ap|A to B}}   隨技能等級變化(ability progression)
- {{pp|A to B}}   隨英雄等級變化
- {{rd|A|B}}      近戰 A / 遠程 B(Template:Range difference)
- {{ft|A|B}}      兩種等價表示法,取第一種(Template:FlipText)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# "A to B"(可帶第三個數字 = 技能等級數,顯示上省略)→ "A − B"
_RANGE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s+to\s+(-?\d+(?:\.\d+)?)(?:\s+\d+)?")


def _fmt_range(value: str) -> str:
    return _RANGE_RE.sub(lambda m: f"{m.group(1)}−{m.group(2)}", value)


# {{tip|縮寫}} 的縮寫 → 中文(只列本資料檔出現過的;沒列到的原樣輸出)
_TIP_LABELS = {
    "er": "效果半徑",
    "dash": "衝刺",
    "blink": "閃現位移",
    "attach": "附著",
    "takedown": "擊殺參與",
    "melee": "近戰",
    "ranged": "遠程",
    "slow": "緩速",
    "slow resist": "緩速抗性",
    "heal": "治療",
    "shield": "護盾",
    "adaptive force": "適應之力",
    "cast instance": "施放判定",
    "critical strike": "爆擊",
    "grievous wounds": "重創(Grievous Wounds)",
}


def _split_top_level(inner: str) -> list[str]:
    """依 '|' 切參數,但不切 [[連結|參數]] 內的管線。"""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    while i < len(inner):
        two = inner[i:i + 2]
        if two == "[[":
            depth += 1
            buf.append(two)
            i += 2
        elif two == "]]":
            depth = max(0, depth - 1)
            buf.append(two)
            i += 2
        elif inner[i] == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(inner[i])
            i += 1
    parts.append("".join(buf))
    return parts


def _split_params(inner: str) -> tuple[str, list[str], dict[str, str]]:
    """'name|a|k=v|b' → (name, [a, b], {k: v})。"""
    parts = _split_top_level(inner)
    name = parts[0].strip().lower()
    pos: list[str] = []
    named: dict[str, str] = {}
    for p in parts[1:]:
        m = re.match(r"^\s*(\w[\w\s-]*?)\s*=\s*(.*)$", p, re.S)
        if m:
            named[m.group(1).strip().lower()] = m.group(2).strip()
        else:
            pos.append(p.strip())
    return name, pos, named


def _eval_product(expr: str, round_to: str | None) -> str:
    """'8*0.667' 這種純乘法式求值(wiki 用它標示衍生數值)。"""
    prod = 1.0
    for factor in expr.split("*"):
        prod *= float(factor)
    prod = round(prod, int(round_to) if round_to else 4)
    return f"{prod:g}"


def _render(name: str, pos: list[str], named: dict[str, str]) -> str:
    p0 = pos[0] if pos else ""

    if name == "ap":  # 隨技能等級
        if re.fullmatch(r"[\d.\s*]+", p0) and "*" in p0:
            return _eval_product(p0, named.get("round"))
        return f"{_fmt_range(p0)}(隨技能等級)"

    if name == "pp":  # 隨英雄等級(或 type= 指定的量)
        value = _fmt_range(re.sub(r"\s+for\s+\d+(?:\.\d+)?\s*$", "", p0))
        key = named.get("key") or named.get("key1") or ""
        if key == "%" and "%" not in value:
            value += "%"
        typ = named.get("type", "").strip()
        return f"{value}(隨 {typ} 變化)" if typ else f"{value}(隨等級)"

    if name == "rd":  # 近戰/遠程各一值
        melee = named.get("melee", p0)
        ranged = named.get("ranged", pos[1] if len(pos) > 1 else "")
        def fmt(v: str) -> str:
            v = _fmt_range(v)
            if named.get("key") == "%" and "%" not in v:
                v += "%"
            return v
        out = f"近戰 {fmt(melee)}/遠程 {fmt(ranged)}"
        if named.get("pp") == "true":
            out += "(隨等級)"
        return out

    if name == "tip":
        label = pos[1] if len(pos) > 1 else p0
        return _TIP_LABELS.get(label.lower(), label)

    if name == "sbc":  # 小型粗體標題(New Effect: 之類)
        return f"**{p0}**"

    if name == "ai":  # {{ai|技能|英雄|顯示名?}}
        return pos[2] if len(pos) > 2 else p0

    if name in ("ii", "iis", "si", "sti"):  # 裝備/召喚師技能/屬性圖示
        return pos[1] if len(pos) > 1 else p0

    if name == "aug":  # {{aug|ar|強化名}}
        return pos[-1] if pos else ""

    if name == "g":
        return f"{p0} 金幣"

    if name == "tt":  # 帶提示文字
        return f"{p0}({pos[1]})" if len(pos) > 1 else p0

    if name == "adaptive":
        return f"{_fmt_range(p0)} 適應之力"

    if name == "bug":
        return "(已知 bug)"

    if name in ("note",) or name.startswith("pending"):
        return ""

    if name in ("as", "fd", "ft", "flip", "ci", "cai", "ui", "nie"):
        return p0

    logger.debug("unknown wikitext template %r, using first param", name)
    return p0


# 清理器產生的中文標注 → 英文(給 locale=en_us 的輸出用)。
# 和上面 _render/_TIP_LABELS 的中文字樣一一對應,改哪邊都要同步。
_EN_FIXED = [
    ("(隨技能等級)", " (scales with skill rank)"),
    ("(隨等級)", " (scales with level)"),
    ("(已知 bug)", " (known bug)"),
    (" 金幣", " gold"),
    (" 適應之力", " adaptive force"),
]
_EN_REGEX = [
    # 注意:_render 的標注用的是半形括號,這裡要跳脫才是字面括號
    (re.compile(r"\(隨 (.+?) 變化\)"), r" (scales with \1)"),
    (re.compile(r"近戰 (.+?)/遠程 "), r"melee \1 / ranged "),
]
_TIP_LABELS_EN = {
    "效果半徑": "effect radius", "衝刺": "dash", "閃現位移": "blink",
    "附著": "attach", "擊殺參與": "takedown", "緩速抗性": "slow resist",
    "緩速": "slow", "治療": "heal", "護盾": "shield",
    "施放判定": "cast instance", "爆擊": "critical strike",
    "重創(Grievous Wounds)": "Grievous Wounds",
}


def translate_annotations_en(text: str) -> str:
    """把 clean_wikitext 加上的中文標注換回英文(其餘內容不動)。"""
    for zh, en in _EN_FIXED:
        text = text.replace(zh, en)
    for pattern, repl in _EN_REGEX:
        text = pattern.sub(repl, text)
    for zh, en in _TIP_LABELS_EN.items():
        text = text.replace(zh, en)
    return text


_TEMPLATE_RE = re.compile(r"\{\{([^{}]*)\}\}")


def clean_wikitext(text: str) -> str:
    """單行 wikitext → 純文字(模板、連結、粗體標記都化簡)。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for _ in range(12):  # 實測巢狀最深 3~4 層,12 次綽綽有餘
        new = _TEMPLATE_RE.sub(
            lambda m: _render(*_split_params(m.group(1))), text)
        if new == text:
            break
        text = new
    text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", text)   # 圖檔連結 → 刪
    text = re.sub(r"\[\[[^\]|]*\|([^\]]+)\]\]", r"\1", text)    # [[頁|字]] → 字
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)             # [[頁]] → 頁
    text = text.replace("'''", "**").replace("''", "*")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([.,;:)])", r"\1", text)  # 模板刪掉後殘留的懸空空白
    return text.strip()
