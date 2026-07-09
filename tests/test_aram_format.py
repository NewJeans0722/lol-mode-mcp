"""aram.py:增益/削弱的判定與呈現。"""

from lol_mode_mcp.aram import _format_field


def test_dmg_dealt_above_one_is_buff():
    assert _format_field("dmg_dealt", 1.05).startswith("🟢")


def test_dmg_taken_above_one_is_nerf():
    assert _format_field("dmg_taken", 1.1).startswith("🔴")


def test_dmg_taken_below_one_is_buff():
    assert _format_field("dmg_taken", 0.95).startswith("🟢")


def test_baseline_multiplier_hidden():
    assert _format_field("dmg_dealt", 1.0) is None


def test_ability_haste_is_flat():
    out = _format_field("ability_haste", -20)
    assert out.startswith("🔴") and "-20" in out and "×" not in out


def test_tenacity_is_multiplier():
    out = _format_field("tenacity", 1.2)
    assert out.startswith("🟢") and "×1.2" in out and "+20%" in out


def test_percentage_shown_for_multiplier():
    assert "(+5%)" in _format_field("dmg_dealt", 1.05)
    assert "(-5%)" in _format_field("dmg_taken", 0.95)
