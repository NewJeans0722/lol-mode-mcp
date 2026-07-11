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
    assert render_description("@healamount@", {"HealAmount": [30.0]}) == "30"


def test_calculation_redirect():
    calc = {"APAmpCalcTooltip": {"mFormulaParts": [{"mDataValue": "APAmp"}]}}
    dv = {"APAmp": [0.2]}
    assert render_description("@APAmpCalcTooltip*100@%", dv, calc) == "20%"


def test_unresolvable_placeholder_gets_readable_text():
    out = render_description("目前:@f1@", {})
    assert out == "目前:(依遊戲內數值)"
    assert render_description("Now: @f1@", {}, locale="en_us") == \
        "Now: (computed in-game)"


# ---------------------------------------------------------- 星級(MaxLevel)

# 仿「天界之身」實際資料:index1..3 = 各星級,之後是外插垃圾
_CELESTIAL = {
    "Health": [1000.0, 1000.0, 2000.0, 3000.0, 4000.0, 5000.0, 6000.0],
    "DamageReduction": [0.1, 0.1, 0.05, 0.0, 0.0, 0.0, 0.0],
    "MaxLevel": [3.0] * 7,
}


def test_star_levels_slice_out_garbage():
    out = render_description(
        "增加@Health@生命,傷害降低@DamageReduction*100@%。", _CELESTIAL)
    assert "1000/2000/3000" in out and "4000" not in out
    assert "10/5/0%" in out


def test_star_note_appended_and_excluded_from_summary():
    out = render_description("增加@Health@生命。", _CELESTIAL)
    assert "★3" in out
    assert "★" not in first_sentence(out)


def test_equal_star_values_collapse_to_single():
    dv = {"Dmg": [50.0] * 7, "MaxLevel": [2.0] * 7}
    out = render_description("造成@Dmg@傷害。", dv)
    assert "造成50傷害。" in out


def test_maxlevel_scalar_and_missing_and_scalar_values():
    # MaxLevel 是純量、dataValues 值是純量:都不能炸
    assert "7" in render_description("@X@", {"X": 7.0, "MaxLevel": 2})
    # 缺 MaxLevel = 1 星:維持相異值整條串接(不朽守衛型例外)
    out = render_description("@Dmg@", {"Dmg": [-25.0, 75.0, 175.0, 275.0]})
    assert out == "-25/75/175/275"


# ------------------------------------------------------ @spell.Augment_X:Y@

def test_spell_ref_resolves_own_datavalues():
    out = render_description(
        "增加@spell.Augment_ShadowRunner:MSAmount*100@%跑速,持續@spell.Augment_ShadowRunner:BuffDuration@秒。",
        {"MSAmount": [0.4], "BuffDuration": [3.0]},
        api_name="ShadowRunner")
    assert out == "增加40%跑速,持續3秒。"


def test_spell_ref_falls_back_to_peers():
    out = render_description(
        "@spell.Augment_Other:Speed@", {}, api_name="Me",
        peers={"other": {"Speed": [25.0]}})
    assert out == "25"


def test_spell_ref_unknown_gets_readable_text():
    assert render_description("@spell.Augment_Nobody:X@", {}) == "(依遊戲內數值)"


# ------------------------------------------------------- calculations 求值

def test_calc_char_level_interpolation():
    calc = {"TotalShield": {"mFormulaParts": [
        {"__type": "ByCharLevelInterpolationCalculationPart",
         "mStartValue": 100.0, "mEndValue": 300.0},
        {"__type": "StatByNamedDataValueCalculationPart",
         "mDataValue": "HealthScalar", "mStat": 12},
    ]}}
    out = render_description("獲得@TotalShield@護盾。", {}, calc)
    assert "100–300(隨等級)" in out and "最大生命" in out


def test_calc_sum_with_buff_counter():
    calc = {"MaxHealthReduction": {"mFormulaParts": [
        {"__type": "SumOfSubPartsCalculationPart", "mSubparts": [
            {"__type": "NamedDataValueCalculationPart",
             "mDataValue": "HealthReductionPercent"},
            {"__type": "BuffCounterByCoefficientCalculationPart",
             "mBuffName": "{x}", "mCoefficient": 1.0},
        ]}]}}
    out = render_description("@MaxHealthReduction*100@%",
                             {"HealthReductionPercent": [0.05]}, calc)
    assert "5" in out and "隨層數成長" in out


def test_calc_unknown_type_gets_readable_text():
    calc = {"Mystery": {"mFormulaParts": [{"__type": "SomethingNew"}]}}
    assert render_description("@Mystery@", {}, calc) == "(依遊戲內數值)"


def test_br_and_tags_stripped():
    text = "第一行<br><br><rules>規則文字</rules>"
    assert render_description(text, {}) == "第一行\n\n規則文字"


def test_inline_keyword_ref_resolved():
    text = "普攻會朝額外一名目標射出箭矢，並附加{{ Item_Keyword_OnHit }}。"
    assert render_description(text, {}) == "普攻會朝額外一名目標射出箭矢，並附加攻擊特效。"


def test_whole_desc_ref_with_teamsize_variant():
    out = render_description("{{ Cherry_Vengeance@TeamSize@_Summary }}", {})
    assert "友軍陣亡" in out and "{{" not in out


def test_ref_placeholders_still_substituted():
    out = render_description("{{ Cherry_SpinToWin_Summary }}",
                             {"SpinHaste": [20.0], "SpinDamageAmp": [0.12]})
    assert "20" in out and "12%" in out and "@" not in out


def test_unknown_ref_stripped():
    assert render_description("效果{{ Cherry_Unknown_Thing }}結束", {}) == "效果結束"


def test_sprite_markup_removed():
    assert render_description("獲得一件%i:Augment%金色增幅裝置。", {}) == "獲得一件金色增幅裝置。"


def test_first_sentence_chinese():
    assert first_sentence("獲得召喚師技能。之後還有更多。") == "獲得召喚師技能。"


def test_first_sentence_truncation():
    long = "沒有句號" * 30
    out = first_sentence(long)
    assert out.endswith("…") and len(out) <= 60
