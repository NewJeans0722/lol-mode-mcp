"""patch_notes.py:patch 頁 Arena 段落解析與過濾(離線)。"""

from lol_mode_mcp.patch_notes import (_filter_categories, extract_mode_section,
                                      normalize_patch, parse_mode_changes)

# 注意 '== Arena ===' 是 wiki 上實際出現過的「等號不對稱」寫法,要容錯
PAGE_SAMPLE = """== Items ==
* Something on Summoner's Rift.

== Arena ===
* Augments
** Chroma Flux
*** Autocast Cooldown: 15s ⇒ 10s
** Calculated Risk
*** Disabled.
* Champions
** Elise
*** Passive Damage: 12 - 42 ⇒ 15 - 45
*** Human E Stun Duration: 1.6 - 2.4 ⇒ 1.9 - 2.5
** Gnar
*** W Base Damage: 0 - 40 ⇒ 20 - 60
* Items
** Eclipse
*** Attack Damage: 50 ⇒ 60
* Guests of Honor
** Locke
*** New Guest of Honor.

== Hotfixes ==
* Not arena stuff.
"""


def _cats():
    return parse_mode_changes(extract_mode_section(PAGE_SAMPLE))


def test_normalize_patch():
    assert normalize_patch("26.13") == "V26.13"
    assert normalize_patch("V26.13") == "V26.13"
    assert normalize_patch("26.9") == "V26.09"
    assert normalize_patch("最新") is None


def test_extract_section_tolerates_sloppy_heading():
    sec = extract_mode_section(PAGE_SAMPLE)
    assert "Chroma Flux" in sec
    assert "Summoner's Rift" not in sec     # 前一段不進來
    assert "Not arena stuff" not in sec     # 下一段也不進來


def test_extract_missing_section_returns_none():
    assert extract_mode_section("== Items ==\n* x\n") is None


def test_parse_structure():
    cats = _cats()
    assert [c["category"] for c in cats] == \
        ["Augments", "Champions", "Items", "Guests of Honor"]
    champs = cats[1]
    assert [e["name"] for e in champs["entries"]] == ["Elise", "Gnar"]
    assert champs["entries"][0]["lines"] == [
        "- Passive Damage: 12 - 42 ⇒ 15 - 45",
        "- Human E Stun Duration: 1.6 - 2.4 ⇒ 1.9 - 2.5",
    ]


def test_filter_matches_case_insensitive_terms():
    cats = _cats()
    hit = _filter_categories(cats, {"eclipse"})
    assert len(hit) == 1
    assert hit[0]["category"] == "Items"
    assert hit[0]["entries"][0]["name"] == "Eclipse"


def test_filter_no_match_returns_empty():
    assert _filter_categories(_cats(), {"Rite Of Ruin"}) == []
