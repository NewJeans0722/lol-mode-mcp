"""arena.py:強化搜尋命中/未命中(不需網路,用假資料)。"""

from lol_mode_mcp.arena import Augment, score_augment, search_augments


def make(id, name_zh, name_en, api_name, rarity=1, desc_zh="", desc_en=""):
    return Augment(id=id, api_name=api_name, rarity=rarity,
                   name_zh=name_zh, name_en=name_en,
                   desc_zh=desc_zh, desc_en=desc_en)


AUGS = [
    make(1, "地獄三頭犬", "Cerberus", "Cerberus", rarity=2,
         desc_zh="灼燒身邊的敵人。"),
    make(2, "例行熱身", "Warmup Routine", "WarmupRoutine", rarity=0,
         desc_zh="每秒增加傷害。"),
    make(3, "量子計算", "Quantum Computing", "QuantumComputing", rarity=2,
         desc_zh="技能急速加成。"),
]


def test_exact_chinese_name_hits():
    matches = search_augments("地獄三頭犬", AUGS)
    assert matches[0][1].api_name == "Cerberus"
    assert matches[0][0] == 100.0


def test_exact_english_name_case_insensitive():
    matches = search_augments("cerberus", AUGS)
    assert matches[0][1].id == 1 and matches[0][0] == 100.0


def test_partial_chinese_keyword():
    matches = search_augments("熱身", AUGS)
    assert matches[0][1].id == 2 and matches[0][0] >= 90


def test_name_embedded_in_question():
    # 使用者整句丟進來:「例行熱身那個強化在做什麼」
    matches = search_augments("例行熱身那個強化", AUGS)
    assert matches[0][1].id == 2 and matches[0][0] >= 80


def test_desc_keyword_fallback():
    matches = search_augments("灼燒", AUGS)
    assert matches[0][1].id == 1


def test_miss_returns_low_scores():
    assert score_augment("完全無關的字串xyz", AUGS[0]) < 80


def test_typo_english_fuzzy():
    matches = search_augments("cerberos", AUGS)  # 拼錯一個字母
    assert matches[0][1].id == 1
