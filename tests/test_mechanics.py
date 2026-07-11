"""mechanics.py 與 mayhem_augments.py:機制說明與 Mayhem 圖鑑解析(離線)。"""

from lol_mode_mcp.mayhem_augments import parse_mayhem_module
from lol_mode_mcp.mechanics import load_mechanics

LUA = """-- <pre>
return {
\t[\"ADAPt\"] = {
\t\t[\"description\"] = \"Convert '''all''' of your {{as|'''bonus''' attack damage}} into {{as|ability power}}.\",
\t\t[\"tier\"] = \"Silver\",
\t},
\t[\"Blunt Force\"] = {
\t\t[\"description\"] = \"Increases {{as|attack damage}} by {{as|20%|AD}}.\",
\t\t[\"tier\"] = \"Gold\",
\t},
}
"""


def test_mechanics_json_shape():
    data = load_mechanics()
    assert set(data) >= {"arena", "aram", "mayhem", "_meta"}
    arena = data["arena"]
    topics = [s["topic"] for s in arena["sections"]]
    assert any("貴賓" in t for t in topics)
    guests = next(s for s in arena["sections"] if "guests" in s)["guests"]
    assert len(guests) >= 15
    assert all({"nameEn", "phase", "effect"} <= set(g) for g in guests)
    # 誠實聲明必須在
    flat = str(arena["sections"])
    assert "未公開" in flat


def test_mode_mechanics_tool_output():
    # 不打網路:_guest_zh 會退回英文名(get_champions 失敗時),
    # 但這裡只驗排版與內容存在,離線可跑(名單快取通常已存在則更好)
    from lol_mode_mcp.mechanics import do_mode_mechanics
    out = do_mode_mechanics("arena")
    assert "競技場" in out and "【" in out and "資料來源" in out
    assert "未公開" in out
    out2 = do_mode_mechanics("亂打")
    assert "看不懂模式" in out2 and "mayhem" in out2


def test_parse_mayhem_module():
    entries = parse_mayhem_module(LUA)
    assert [e["nameEn"] for e in entries] == ["ADAPt", "Blunt Force"]
    assert entries[0]["tier"] == "silver"
    assert "**bonus** attack damage" in entries[0]["desc"]
    assert "{{" not in entries[0]["desc"]
    assert entries[1]["desc"] == "Increases attack damage by 20%."
