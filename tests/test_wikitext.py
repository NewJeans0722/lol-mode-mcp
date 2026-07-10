"""wikitext.py:模板清理器,案例全部取自 MapChanges/data/ar 實際內容。"""

from lol_mode_mcp.wikitext import clean_wikitext, translate_annotations_en


def test_ap_is_per_skill_rank():
    assert clean_wikitext("{{ap|70 to 190}}") == "70−190(隨技能等級)"


def test_ap_with_rank_count_drops_count():
    # 第三個數字是技能等級數(如大絕 3 級),顯示上省略
    assert clean_wikitext("{{ap|50 to 70 3}}") == "50−70(隨技能等級)"


def test_ap_arithmetic_is_evaluated():
    assert clean_wikitext("{{ap|3*0.4}}") == "1.2"
    assert clean_wikitext("{{ap|8*0.667|round=2}}") == "5.34"


def test_as_passthrough():
    assert clean_wikitext("{{as|75% AP}}") == "75% AP"


def test_nested_templates_resolved_inside_out():
    assert clean_wikitext("{{as|{{ap|30 to 55 3}}% AD}}") == \
        "30−55(隨技能等級)% AD"


def test_pp_is_per_level():
    assert clean_wikitext("{{pp|1 to 1.5 for 3|1 to 11}}") == "1−1.5(隨等級)"


def test_pp_with_percent_key_and_type():
    out = clean_wikitext(
        "{{pp|key=%|key1=%|type='''missing''' health|0 to 35 for 11|0 to 100"
        "|formula=0.35% per 1% missing health}}")
    assert "0−35%" in out
    assert "**missing** health" in out


def test_rd_melee_first_ranged_second():
    # Template:Range difference 原始碼查證:第一參數近戰、第二遠程
    assert clean_wikitext("{{rd|8%|5%}}") == "近戰 8%/遠程 5%"


def test_rd_with_pp_and_percent_key():
    out = clean_wikitext("{{rd|13 to 18|8 to 12|pp=true|key=%}}")
    assert out == "近戰 13−18%/遠程 8−12%(隨等級)"


def test_sbc_becomes_bold():
    assert clean_wikitext("{{sbc|New Effect:}}") == "**New Effect:**"


def test_fd_passthrough():
    assert clean_wikitext("{{fd|0.45}}") == "0.45"


def test_tip_known_abbreviation_translated():
    assert clean_wikitext("{{tip|er|icononly=true}} 25") == "效果半徑 25"


def test_tip_unknown_kept_as_is():
    assert clean_wikitext("{{tip|Grievous Wounds}}") == "重創(Grievous Wounds)"


def test_gold_template():
    assert clean_wikitext("{{g|350}}") == "350 金幣"


def test_aug_takes_augment_name():
    assert clean_wikitext("{{aug|ar|Cerberus}}") == "Cerberus"


def test_ai_prefers_display_name():
    assert clean_wikitext("{{ai|Q|Draven|Axe}}") == "Axe"
    assert clean_wikitext("{{ai|Empowered Whiplash|Evelynn}}") == "Empowered Whiplash"


def test_tt_appends_tooltip():
    assert clean_wikitext("{{tt|40%|two instances of 20%}}") == \
        "40%(two instances of 20%)"


def test_adaptive_force():
    assert clean_wikitext("{{adaptive|3 to 5.5}}") == "3−5.5 適應之力"


def test_file_links_removed_other_links_keep_text():
    assert clean_wikitext("[[File:Realm Warp.png]] done") == "done"
    assert clean_wikitext("[[Arena#Power Flowers|Power Flower]]") == "Power Flower"
    assert clean_wikitext("[[on-hit]] effects") == "on-hit effects"


def test_bold_and_italic_markers_converted():
    assert clean_wikitext("'''maximum''' health") == "**maximum** health"
    assert clean_wikitext("''Obtained from x.''") == "*Obtained from x.*"


def test_piped_link_inside_template_param_not_split():
    # Ryze Q 實例:type= 裡有 [[File:...|20px|border]],管線不能當參數分隔
    out = clean_wikitext(
        "{{pp|type=[[File:Realm Warp.png|20px|border]] ''Realm Warp's'' Rank"
        "|key=%|10 to 70 for 4|0 to 3}}")
    assert out.startswith("10−70%")
    assert "Realm Warp's* Rank" in out
    assert "File:" not in out and "20px" not in out


def test_typed_pp_annotation_translates_to_english():
    zh = clean_wikitext("{{pp|type=distance traveled|1.5 to 4.5 for 15|0 to 2800}}")
    assert zh == "1.5−4.5(隨 distance traveled 變化)"
    assert translate_annotations_en(zh) == \
        "1.5−4.5 (scales with distance traveled)"


def test_annotations_translate_back_to_english():
    assert translate_annotations_en("70−190(隨技能等級)") == \
        "70−190 (scales with skill rank)"
    assert translate_annotations_en("1−1.5(隨等級)") == "1−1.5 (scales with level)"
    assert translate_annotations_en("近戰 8%/遠程 5%") == "melee 8% / ranged 5%"
    assert translate_annotations_en("350 金幣") == "350 gold"
    assert translate_annotations_en("效果半徑 25") == "effect radius 25"
    # 英文內容不受影響
    assert translate_annotations_en("Base damage changed to 10.") == \
        "Base damage changed to 10."


def test_full_sentence_from_real_data():
    line = ("Health ratio changed to {{as|{{ap|1 to 2.5}}% of target's "
            "'''maximum''' health|hp}}.")
    assert clean_wikitext(line) == \
        "Health ratio changed to 1−2.5(隨技能等級)% of target's **maximum** health."
