"""translate.py:規則式英→中翻譯(離線)。"""

from lol_mode_mcp.translate import translate_line, translate_lines


def test_changed_to():
    zh, ok = translate_line("Base damage changed to 70−190(隨技能等級).")
    assert ok and zh == "基礎傷害改為 70−190(隨技能等級)。"


def test_changed_to_with_from():
    zh, ok = translate_line("Cooldown changed to 10 seconds from 20.")
    assert ok and zh == "冷卻時間改為 10 秒(原為 20)。"


def test_increased_reduced():
    zh, ok = translate_line("Base mana regeneration increased to 11 from 9.")
    assert ok and zh == "基礎魔力回復提高至 11(原為 9)。"
    zh, ok = translate_line("Health growth reduced to 98 from 104.")
    assert ok and zh == "生命成長降低至 98(原為 104)。"


def test_arrow_label():
    zh, ok = translate_line("Autocast Cooldown: 15s ⇒ 10s")
    assert ok and zh == "自動施放冷卻時間:15s ⇒ 10s"


def test_arrow_tier_context_gold_is_rank_not_currency():
    zh, ok = translate_line("Tier: Gold ⇒ Prismatic")
    assert ok and zh == "稀有度:黃金 ⇒ 稜彩"


def test_whole_line_specials():
    assert translate_line("Disabled.") == ("已停用。", True)
    assert translate_line("New Guest of Honor.") == ("新登場貴賓。", True)


def test_freeform_sentence_not_translated():
    text = "Now counts as a burn source when gaining Red Buff."
    zh, ok = translate_line(text)
    assert not ok and zh == text  # 原文保留,不輸出半中半英


def test_name_line_kept_without_mark():
    zh, ok = translate_line("Calibrum")
    assert ok and zh == "Calibrum"  # 名稱行不算翻譯失敗


def test_name_map_translates_ability_names():
    zh, ok = translate_line("Blood Hunt", {"blood hunt": "血跡獵蹤"})
    assert ok and zh == "血跡獵蹤(Blood Hunt)"


def test_translate_lines_marks_and_keeps_prefix():
    out = translate_lines([
        "- AP ratio changed to 75% AP.",
        "  - Fixed a bug where things break badly sometimes.",
    ])
    assert out[0] == "- AP 係數改為 75% AP。"
    assert out[1].startswith("  - 🔤 Fixed a bug")
