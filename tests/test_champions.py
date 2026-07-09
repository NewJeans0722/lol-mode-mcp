"""champions.py:英雄名正規化與解析(不需網路)。"""

from lol_mode_mcp.champions import Champion, resolve_champion

CHAMPS = [
    Champion(id="MonkeyKing", name_en="Wukong", name_zh="悟空", title_zh="齊天大聖"),
    Champion(id="Yasuo", name_en="Yasuo", name_zh="犽宿", title_zh="放逐浪人"),
    Champion(id="Yone", name_en="Yone", name_zh="犽凝", title_zh="不滅劍魂"),
    Champion(id="Nunu", name_en="Nunu & Willump", name_zh="努努和威朗普", title_zh="男孩與雪怪"),
]


def test_chinese_exact():
    champ, _ = resolve_champion("悟空", CHAMPS)
    assert champ and champ.id == "MonkeyKing"


def test_english_display_name():
    champ, _ = resolve_champion("wukong", CHAMPS)
    assert champ and champ.id == "MonkeyKing"


def test_ddragon_id_also_works():
    champ, _ = resolve_champion("monkeyking", CHAMPS)
    assert champ and champ.id == "MonkeyKing"


def test_ampersand_and_spaces_normalized():
    champ, _ = resolve_champion("nunu & willump", CHAMPS)
    assert champ and champ.id == "Nunu"


def test_ambiguous_partial_returns_candidates():
    champ, candidates = resolve_champion("犽", CHAMPS)
    assert champ is None
    assert {c.id for c in candidates} == {"Yasuo", "Yone"}


def test_unique_partial_resolves():
    champ, _ = resolve_champion("威朗普", CHAMPS)
    assert champ and champ.id == "Nunu"


def test_total_miss_gives_suggestions():
    champ, candidates = resolve_champion("yasou", CHAMPS)  # 拼錯
    assert champ is None
    assert candidates and candidates[0].id == "Yasuo"
