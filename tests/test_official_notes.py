"""official_notes.py:官方繁中 patch notes 解析(離線,fixture 仿真實標記)。"""

import pytest

from lol_mode_mcp.official_notes import _slug_candidates, parse_official_notes

PAGE = """<html><body><div id="patch-notes-container">
<h2>版本概要</h2><p>略</p>
<header><h2>英雄</h2></header>
<h3 style="x">巴德</h3>
<h4>旅者引領（被動）</h4>
<ul><li>每個米普傷害：35 ⇒ <strong>30</strong></li></ul>
<h3>布蘭德</h3>
<h4>基礎能力值</h4>
<ul><li>基礎魔力回復：9 ⇒ 11</li></ul>
<header><h2>競技場</h2></header>
<h4 style="y">增幅裝置</h4>
<p><strong style="z">增益麻吉</strong></p>
<ul><li>會被視為燃燒來源。</li></ul>
<p><strong>套娃</strong></p>
<ul><li>等級：金級 → 稜鏡級</li></ul>
<h4>特別嘉賓</h4>
<p><strong>洛克</strong></p>
<ul><li>新登場。</li></ul>
<header><h2>隨機單中：大混戰</h2></header>
<h4>增幅裝置</h4>
<p><strong>大法師</strong></p>
<ul><li>等級：金級 → 稜鏡級</li></ul>
<header><h2>造型</h2></header>
<h4>西域牛仔 洛克</h4>
</div></body></html>"""


@pytest.fixture(scope="module")
def scopes():
    return parse_official_notes(PAGE)


def test_general_champion_structure(scopes):
    champs = scopes["general"][0]
    assert champs["category"] == "英雄"
    bard = champs["entries"][0]
    assert bard["name"] == "巴德"
    assert bard["lines"] == ["- 旅者引領（被動）",
                             "  - 每個米普傷害：35 ⇒ 30"]


def test_arena_flat_structure(scopes):
    cats = {c["category"]: c for c in scopes["arena"]}
    assert set(cats) == {"增幅裝置", "特別嘉賓"}
    assert cats["增幅裝置"]["entries"][0] == \
        {"name": "增益麻吉", "lines": ["- 會被視為燃燒來源。"]}
    assert cats["特別嘉賓"]["entries"][0]["name"] == "洛克"


def test_mayhem_scope(scopes):
    assert scopes["mayhem"][0]["entries"][0]["name"] == "大法師"


def test_cosmetics_section_ignored(scopes):
    all_entries = [e["name"] for sc in scopes.values()
                   for c in sc for e in c["entries"]]
    assert "西域牛仔 洛克" not in all_entries


# 開場白排在自己的 h2 之前,原本會被算成上一個 scope 的最後一筆條目
INTRO_PAGE = """<html><body><div id="patch-notes-container">
<header><h2>隨機單中：大混戰</h2></header>
<h4>增幅裝置</h4>
<p><strong>大法師</strong></p>
<ul><li>等級：金級 → 稜鏡級</li></ul>
<h4>錯誤修正</h4>
<p>競技場愛好者們，歡迎回來！這次我們的重點是強化表現較弱的選項，並調整了幾件增幅裝置。</p>
<header><h2>競技場</h2></header>
<h4>增幅裝置</h4>
<p><strong>雙響炮</strong></p>
<ul><li>移除狀態：停用</li></ul>
</div></body></html>"""


def test_section_intro_paragraph_not_attached_to_previous_scope():
    sc = parse_official_notes(INTRO_PAGE)
    names = [e["name"] for c in sc["mayhem"] for e in c["entries"]]
    assert names == ["大法師"]                      # 開場白不進大混戰
    assert [c["category"] for c in sc["mayhem"]] == ["增幅裝置"]  # 空分類也清掉
    assert sc["arena"][0]["entries"][0]["name"] == "雙響炮"


def test_real_zero_line_entry_kept():
    # 帶「:」的短條目是真的改動(常見於錯誤修正),不可誤刪
    page = INTRO_PAGE.replace(
        "競技場愛好者們，歡迎回來！這次我們的重點是強化表現較弱的選項，並調整了幾件增幅裝置。",
        "錯誤修正：修正了大法師有時不會生效的問題，現已正常運作。")
    sc = parse_official_notes(page)
    names = [e["name"] for c in sc["mayhem"] for e in c["entries"]]
    assert "大法師" in names and len(names) == 2


def test_missing_container_raises():
    with pytest.raises(ValueError):
        parse_official_notes("<html><body>nothing</body></html>")


def test_slug_candidates():
    assert _slug_candidates("V26.13") == [
        "league-of-legends-patch-26-13-notes", "patch-26-13-notes"]
    assert _slug_candidates("V26.09")[0] == "league-of-legends-patch-26-9-notes"
    assert _slug_candidates("latest") == []
