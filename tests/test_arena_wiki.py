"""arena_wiki.py:wiki 強化模組解析與 arena.py 補充合併(離線)。"""

from lol_mode_mcp.arena import Augment, _wiki_supplement, _norm_name
from lol_mode_mcp.arena_wiki import parse_augment_module

LUA_SAMPLE = '''return {
\t["Bread Sandwich"] = {
\t\t["description"] = "Gain {{sti|{{as|ability haste}}}}. Casting an ability grants you {{sti|{{as|40% \'\'\'bonus\'\'\' movement speed}}}} for 2 seconds.",
\t\t["tier"] = "Prismatic",
\t\t["level1"] = "{{sti|{{as|200 ability haste}}}}.",
\t\t["level2"] = "{{sti|{{as|300 ability haste}}}}.",
\t\t["level3"] = "{{sti|{{as|400 ability haste}}}}.",
\t\t["notes"] = [=[
\t\t* This augment isn't available for choice.
\t\t* Obtained by gathering all three Bread augments.
\t\t]=],
\t},
\t["Rice And Chicken"] = {
\t\t["description"] = "Your champion's first basic ability \'\'(Q)\'\' gains increased damage.<ul><li>50% increased damage.</li><li>30% healing.</li></ul>",
\t\t["tier"] = "Gold",
\t\t["level1"] = "<ul><li>50% increased damage.</li></ul>",
\t\t["level2"] = "",
\t\t["level3"] = "",
\t},
\t["Juice Press"] = {
\t\t["description"] = "Juices are cheaper.<br><br>\'\'Removed since [[V26.09]].\'\'",
\t\t["tier"] = "Silver",
\t\t["level1"] = "",
\t\t["level2"] = "",
\t\t["level3"] = "",
\t},
}'''


def test_parse_fields_and_levels():
    entries = parse_augment_module(LUA_SAMPLE)
    assert set(entries) == {"Bread Sandwich", "Rice And Chicken", "Juice Press"}
    bs = entries["Bread Sandwich"]
    assert bs["rarity"] == 2
    assert len(bs["levels"]) == 3
    assert "200 ability haste" in bs["levels"][0]
    assert "{{" not in bs["description"]
    assert "isn't available" in bs["notes"]


def test_html_list_cleanup():
    entries = parse_augment_module(LUA_SAMPLE)
    rc = entries["Rice And Chicken"]
    assert "<ul>" not in rc["description"] and "<li>" not in rc["description"]
    assert "• 50% increased damage." in rc["description"]
    assert len(rc["levels"]) == 1  # 空 level 要濾掉


def test_removed_flag():
    entries = parse_augment_module(LUA_SAMPLE)
    assert entries["Juice Press"]["removed"] is True
    assert entries["Bread Sandwich"]["removed"] is False


def test_supplement_skips_existing_and_removed(monkeypatch):
    entries = parse_augment_module(LUA_SAMPLE)

    class FakeResult:
        data = {"entries": entries}

    monkeypatch.setattr("lol_mode_mcp.arena_wiki.get_wiki_augments",
                        lambda: FakeResult())
    existing = [Augment(id=1, api_name="BreadSandwich", rarity=2,
                        name_zh="麵包三明治", name_en="Bread Sandwich",
                        desc_zh="", desc_en="")]
    sup = _wiki_supplement(existing)
    names = {a.name_en for a in sup}
    assert "Bread Sandwich" not in names   # cdragon 已有 → 不補
    assert "Juice Press" not in names      # 已移除 → 不補
    assert "Rice And Chicken" in names
    rice = next(a for a in sup if a.name_en == "Rice And Chicken")
    assert rice.source == "wiki"
    assert rice.id < 0                     # 合成 id 不與 cdragon 衝突
    assert rice.note                       # 對照檔:聲望解鎖註記
    assert rice.max_level == 1


def test_norm_name_matching():
    assert _norm_name("Upgrade: Collector") == _norm_name("Upgrade Collector")
