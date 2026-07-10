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


def test_missing_container_raises():
    with pytest.raises(ValueError):
        parse_official_notes("<html><body>nothing</body></html>")


def test_slug_candidates():
    assert _slug_candidates("V26.13") == [
        "league-of-legends-patch-26-13-notes", "patch-26-13-notes"]
    assert _slug_candidates("V26.09")[0] == "league-of-legends-patch-26-9-notes"
    assert _slug_candidates("latest") == []
