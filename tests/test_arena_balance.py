"""arena_balance.py:MapChanges 解析、依英雄分組、數值排版(離線)。"""

from lol_mode_mcp.arena_balance import (_format_stat, group_champion_changes,
                                        parse_map_changes)
from lol_mode_mcp.champions import Champion

LUA_SAMPLE = '''return {
-- Champions
    ["Akali Q"] = [=[
    * Base damage changed to {{ap|70 to 190}}.
    * AP ratio changed to {{as|75% AP}}.
    ]=],
    ["Akali W"] = [=[
    * Energy restoration changed to 150.
    ]=],
    ["Nunu Q"] = [=[
    * Heal changed to {{ap|100 to 200}}.
    ]=],
    ["Anivia I"] = [=[
    * Cooldown resets every round.
    ]=],
    ["Azir"] = [=[
    * Soldiers persist between rounds.
    ]=],
    ["Nidalee Prowl"] = [=[
    * Bonus movement speed changed to 30%.
    ]=],
    ["Renata Glasc R"] = [=[
    * Cooldown changed to {{ap|120 to 80}} seconds.
    ** {{sbc|New Effect:}} Now also berserks minions.
    ]=],
-- Items
    ["Dead Man's Plate"] = [=[
    * Momentum stacks twice as fast.
    ]=],
-- Runes
    ["Lethal Tempo"] = [=[
    * ''Obtained from the {{aug|ar|Combo Master}} augment.''
    ]=],
}
'''

CHAMPS = [
    Champion(id="Akali", name_en="Akali", name_zh="阿卡莉", title_zh=""),
    Champion(id="Nunu", name_en="Nunu & Willump", name_zh="努努和威朗普", title_zh=""),
    Champion(id="Anivia", name_en="Anivia", name_zh="艾妮維亞", title_zh=""),
    Champion(id="Azir", name_en="Azir", name_zh="阿祈爾", title_zh=""),
    Champion(id="Nidalee", name_en="Nidalee", name_zh="奈德麗", title_zh=""),
    Champion(id="Renata", name_en="Renata Glasc", name_zh="雷娜妲", title_zh=""),
]


def _grouped():
    sections = parse_map_changes(LUA_SAMPLE)
    return group_champion_changes(sections["champions"], CHAMPS)


def test_sections_split():
    sections = parse_map_changes(LUA_SAMPLE)
    assert "Akali Q" in sections["champions"]
    assert "Dead Man's Plate" in sections["items"]
    assert "Lethal Tempo" in sections["runes"]
    # 段落不互相汙染
    assert "Dead Man's Plate" not in sections["champions"]


def test_entry_lines_cleaned():
    sections = parse_map_changes(LUA_SAMPLE)
    assert sections["champions"]["Akali Q"] == [
        "- Base damage changed to 70−190(隨技能等級).",
        "- AP ratio changed to 75% AP.",
    ]


def test_nested_bullets_indented():
    sections = parse_map_changes(LUA_SAMPLE)
    lines = sections["champions"]["Renata Glasc R"]
    assert lines[1].startswith("  - **New Effect:**")


def test_grouping_by_longest_prefix():
    grouped = _grouped()
    assert [label for label, _ in grouped["Akali"]] == ["Q", "W"]
    assert [label for label, _ in grouped["Renata Glasc"]] == ["R"]


def test_nunu_alias_maps_to_full_name():
    grouped = _grouped()
    assert "Nunu & Willump" in grouped
    assert "Nunu" not in grouped


def test_ability_labels():
    grouped = _grouped()
    assert grouped["Anivia"][0][0] == "被動"      # I → 被動
    assert grouped["Azir"][0][0] == "整體"        # 純英雄名 → 整體
    assert grouped["Nidalee"][0][0] == "Prowl"    # 具名技能原樣


def test_format_stat_buff_and_nerf():
    assert _format_stat("hp_lvl", 2.0) == "🟢 增益 每級生命成長 +2"
    assert _format_stat("hp_lvl", -10.0).startswith("🔴 削弱")
    # 沒列在對照表的欄位退回原始 key,不炸
    assert "mystery" in _format_stat("mystery", 1.0)
