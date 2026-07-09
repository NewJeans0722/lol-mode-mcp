"""formatting.py:佔位符代入與標籤清理。"""

from lol_mode_mcp.formatting import first_sentence, render_description


def test_simple_placeholder_substitution():
    text = "增加<scaleAP>@APAmp*100@%魔攻</scaleAP>。"
    dv = {"APAmp": [0.15000000596, 0.15000000596]}
    assert render_description(text, dv) == "增加15%魔攻。"


def test_varying_values_joined_with_slash():
    text = "最高可達@MaxStacks@%。"
    dv = {"MaxStacks": [20.0, 20.0, 40.0, 60.0, 60.0]}
    assert render_description(text, dv) == "最高可達20/40/60%。"


def test_negative_multiplier():
    text = "降低@Slow*-100@%攻速。"
    dv = {"Slow": [-0.25]}
    assert render_description(text, dv) == "降低25%攻速。"


def test_case_insensitive_datavalue_lookup():
    assert render_description("@maxlevel@", {"MaxLevel": [2.0]}) == "2"


def test_calculation_redirect():
    calc = {"APAmpCalcTooltip": {"mFormulaParts": [{"mDataValue": "APAmp"}]}}
    dv = {"APAmp": [0.2]}
    assert render_description("@APAmpCalcTooltip*100@%", dv, calc) == "20%"


def test_unresolvable_placeholder_marked():
    assert render_description("目前:@f1@", {}) == "目前:?"


def test_br_and_tags_stripped():
    text = "第一行<br><br><rules>規則文字</rules>"
    assert render_description(text, {}) == "第一行\n\n規則文字"


def test_sprite_markup_removed():
    assert render_description("獲得一件%i:Augment%金色增幅裝置。", {}) == "獲得一件金色增幅裝置。"


def test_first_sentence_chinese():
    assert first_sentence("獲得召喚師技能。之後還有更多。") == "獲得召喚師技能。"


def test_first_sentence_truncation():
    long = "沒有句號" * 30
    out = first_sentence(long)
    assert out.endswith("…") and len(out) <= 60
