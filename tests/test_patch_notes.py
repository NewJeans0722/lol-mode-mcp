"""patch_notes.py:patch 頁 Arena 段落解析、過濾與台服名對照(離線)。"""

from lol_mode_mcp.champions import split_ability_names
from lol_mode_mcp.patch_notes import (_filter_categories, _name_key,
                                      extract_mode_section, localize_entry,
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


# ---------------------------------------------------------- 台服名對照

LOC = {
    "champions": {_name_key("Elise"): ("伊莉絲", "http://icon/Elise.png"),
                  _name_key("Kayn"): ("凱隱", "http://icon/Kayn.png")},
    "augments": {_name_key("Hive Mind"): "蜂群意識"},
    "items": {_name_key("Eclipse"): "月蝕"},
}


def test_localize_champion_with_icon():
    assert localize_entry("Elise", "Champions", LOC) == \
        ("伊莉絲", "http://icon/Elise.png")


def test_localize_strips_parenthetical_suffix():
    zh, icon = localize_entry("Kayn (Shadow Assassin)", "Champions", LOC)
    assert zh == "凱隱" and icon


def test_localize_ignores_spacing_differences():
    # wiki 寫 Hivemind,遊戲字串是 Hive Mind
    assert localize_entry("Hivemind", "Augments", LOC) == ("蜂群意識", None)


def test_localize_unknown_category_tries_all_tables():
    assert localize_entry("Eclipse", "Systems", LOC) == ("月蝕", None)


def test_localize_miss_returns_none():
    assert localize_entry("Spellcraft", "Augments", LOC) == (None, None)


def test_split_composite_ability_names():
    # 變形英雄的複合技能名,en 用 "/"、zh 用全形 "/",按位置配對
    assert split_ability_names("Cunning Sweep / Sundering Slam") == \
        ["Cunning Sweep", "Sundering Slam"]
    assert split_ability_names("暗襲/裂斬") == ["暗襲", "裂斬"]
