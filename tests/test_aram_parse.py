"""aram.py:Lua 模組解析(不需網路,用縮小版的假 wikitext)。"""

from lol_mode_mcp.aram import parse_champion_mode_data

LUA_SAMPLE = '''-- ChampionData
return {
  ["Aatrox"] = {
    ["id"] = 266,
    ["stats"] = {
      ["hp_base"] = 650,
      ["aram"] = {
        ["dmg_dealt"] = 1.05,
        ["dmg_taken"] = 1,
      },
      ["urf"] = {
        ["dmg_dealt"] = 1.15,
      },
    },
  },
  ["Ahri"] = {
    ["id"] = 103,
    ["stats"] = {
      ["hp_base"] = 590,
      ["aram"] = {
        ["dmg_dealt"] = 0.95,
        ["dmg_taken"] = 1.05,
        ["ability_haste"] = 20,
      },
    },
  },
  ["Akali"] = {
    ["id"] = 84,
    ["stats"] = {
      ["hp_base"] = 600,
    },
  },
}
'''


def test_parses_champions_with_aram_block():
    data = parse_champion_mode_data(LUA_SAMPLE, "aram")
    assert set(data) == {"Aatrox", "Ahri"}


def test_values_parsed_correctly():
    data = parse_champion_mode_data(LUA_SAMPLE, "aram")
    assert data["Aatrox"] == {"dmg_dealt": 1.05, "dmg_taken": 1.0}
    assert data["Ahri"]["ability_haste"] == 20.0


def test_champion_without_aram_absent():
    data = parse_champion_mode_data(LUA_SAMPLE, "aram")
    assert "Akali" not in data  # 無調整 ≠ 查詢失敗,由上層區分


def test_does_not_leak_other_modes():
    data = parse_champion_mode_data(LUA_SAMPLE, "aram")
    assert data["Aatrox"]["dmg_dealt"] == 1.05  # 不是 urf 的 1.15
