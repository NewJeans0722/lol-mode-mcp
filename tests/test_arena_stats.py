"""arena_stats.py:trim/聚合/tool 輸出(不需網路,用假資料)。"""

import pytest

from lol_mode_mcp import arena_stats
from lol_mode_mcp.arena_stats import (aggregate_stats, do_arena_stats,
                                      trim_match)


# ---------------------------------------------------------------- 假資料

def make_raw(match_id="TW2_1", queue=1700, version="26.14.123.456",
             parts=None):
    """縮小版 Match-V5 回應:16 人、名次 1~8 各兩位。"""
    if parts is None:
        parts = [("Garen", (i // 2) + 1, [101, 202]) for i in range(16)]
    participants = []
    for i, (champ, place, augs) in enumerate(parts):
        p = {"puuid": f"p{i}", "championName": champ, "placement": place,
             "playerSubteamId": (i // 2) + 1}
        for slot, aid in enumerate(augs, 1):
            p[f"playerAugment{slot}"] = aid
        participants.append(p)
    return {"metadata": {"matchId": match_id},
            "info": {"queueId": queue, "gameVersion": version,
                     "gameCreation": 1752700000000, "gameDuration": 1100,
                     "participants": participants}}


AUG_META = {101: {"nameZh": "地獄三頭犬", "nameEn": "Cerberus", "rarity": 2},
            202: {"nameZh": "例行熱身", "nameEn": "Warmup Routine", "rarity": 0}}
CHAMP_META = {"Garen": {"nameZh": "蓋倫", "nameEn": "Garen"},
              "MonkeyKing": {"nameZh": "悟空", "nameEn": "Wukong"}}


# ---------------------------------------------------------------- trim_match

def test_trim_keeps_needed_fields():
    slim = trim_match(make_raw())
    assert slim["matchId"] == "TW2_1"
    assert slim["patch"] == "26.14"
    assert len(slim["participants"]) == 16
    p = slim["participants"][0]
    assert p["championName"] == "Garen" and p["placement"] == 1
    assert p["augments"] == [101, 202]


def test_trim_rejects_non_arena_queue():
    assert trim_match(make_raw(queue=450)) is None


def test_trim_filters_empty_augment_slots():
    parts = [("Garen", (i // 2) + 1, [101, 0, 202, 0]) for i in range(16)]
    slim = trim_match(make_raw(parts=parts))
    assert slim["participants"][0]["augments"] == [101, 202]


def test_trim_accepts_current_1750_queue_18_players():
    # 2026 現行競技場:queue 1750、18 人、6 隊×3 人、名次 1~6(實測)
    parts = [("Garen", (i // 3) + 1, [101]) for i in range(18)]
    slim = trim_match(make_raw(queue=1750, parts=parts))
    assert slim["queue"] == 1750
    assert len(slim["participants"]) == 18
    assert max(p["placement"] for p in slim["participants"]) == 6


def test_trim_rejects_inconsistent_placements():
    # 名次分布不均(有人名次 9 但其他名次都成對)= 資料異常
    parts = [("Garen", 9 if i == 0 else (i // 2) + 1, [101])
             for i in range(16)]
    assert trim_match(make_raw(parts=parts)) is None


def test_trim_rejects_missing_placement():
    raw = make_raw()
    del raw["info"]["participants"][3]["placement"]
    assert trim_match(raw) is None


# ---------------------------------------------------------------- aggregate

def build_matches():
    """兩場已知結果:悟空 1、3 名(拿 101),蓋倫其他名次(拿 202)。"""
    matches = []
    for n, wu_place in enumerate((1, 3)):
        parts = []
        # 悟空佔一格,其餘 15 格由 1~8 名補滿(每名次兩人,扣掉悟空那格)
        filler = [p for p in range(1, 9) for _ in range(2)]
        filler.remove(wu_place)
        parts.append(("MonkeyKing", wu_place, [101]))
        parts += [("Garen", p, [202]) for p in filler]
        matches.append(trim_match(make_raw(match_id=f"TW2_{n}", parts=parts)))
    return matches


def test_aggregate_champion_numbers():
    stats = aggregate_stats(build_matches(), AUG_META, CHAMP_META,
                            min_sample=1, min_pair=1)
    wu = stats["champions"]["MonkeyKing"]
    assert wu["games"] == 2
    assert wu["avgPlace"] == 2.0          # (1+3)/2
    assert wu["firstRate"] == 0.5         # 兩場拿了一次第 1(勝率)
    assert wu["top2Rate"] == 0.5          # 只有第 1 名那場算前二
    assert wu["nameZh"] == "悟空"
    assert wu["topAugments"][0]["id"] == 101


def test_aggregate_augment_numbers():
    stats = aggregate_stats(build_matches(), AUG_META, CHAMP_META,
                            min_sample=1, min_pair=1)
    a = stats["augments"]["101"]
    assert a["games"] == 2 and a["avgPlace"] == 2.0
    assert a["topChamps"][0]["champ"] == "MonkeyKing"
    assert a["nameZh"] == "地獄三頭犬" and a["rarity"] == 2


def test_aggregate_min_pair_threshold_drops_small_pairs():
    stats = aggregate_stats(build_matches(), AUG_META, CHAMP_META,
                            min_sample=1, min_pair=3)
    # 悟空×101 只有 2 場 < 3,不收錄;蓋倫×202 有 30 場,收錄
    assert stats["augments"]["101"]["topChamps"] == []
    assert stats["augments"]["202"]["topChamps"][0]["champ"] == "Garen"


def test_aggregate_low_sample_flag():
    stats = aggregate_stats(build_matches(), AUG_META, CHAMP_META,
                            min_sample=10, min_pair=1)
    assert stats["champions"]["MonkeyKing"]["lowSample"] is True   # 2 場
    assert stats["champions"]["Garen"]["lowSample"] is False       # 30 場


def test_aggregate_baseline_follows_team_count():
    # 基準隨隊伍數變:8 隊 → 4.5/0.25;6 隊(現行 1750)→ 3.5/0.333
    stats = aggregate_stats([trim_match(make_raw())], AUG_META, CHAMP_META,
                            min_sample=1, min_pair=1)
    assert stats["meta"]["baselineAvgPlace"] == 4.5
    assert stats["meta"]["baselineFirstRate"] == 0.125
    assert stats["meta"]["baselineTop2Rate"] == 0.25
    parts18 = [("Garen", (i // 3) + 1, [101]) for i in range(18)]
    stats = aggregate_stats([trim_match(make_raw(queue=1750, parts=parts18))],
                            AUG_META, CHAMP_META, min_sample=1, min_pair=1)
    assert stats["meta"]["baselineAvgPlace"] == 3.5
    assert stats["meta"]["baselineFirstRate"] == round(1 / 6, 3)
    assert stats["meta"]["baselineTop2Rate"] == round(2 / 6, 3)


def test_aggregate_unknown_augment_id_gets_placeholder_name():
    stats = aggregate_stats(build_matches(), {}, CHAMP_META,
                            min_sample=1, min_pair=1)
    assert stats["augments"]["101"]["nameZh"] == "#101"


# ---------------------------------------------------------------- tool 輸出

@pytest.fixture
def offline(monkeypatch):
    """測試不打網路:名稱解析與 patch 檢查全退回統計檔內建資料。"""
    def boom():
        raise RuntimeError("no network in tests")
    monkeypatch.setattr(arena_stats, "get_arena_data", boom)
    monkeypatch.setattr(arena_stats, "get_champions", boom)


@pytest.fixture
def fake_stats(monkeypatch):
    stats = aggregate_stats(build_matches(), AUG_META, CHAMP_META,
                            min_sample=1, min_pair=1)
    stats["meta"]["generated_at"] = "2026-07-17 08:00 UTC"
    stats["meta"]["source"] = "測試資料"
    monkeypatch.setattr(arena_stats, "load_stats", lambda: stats)
    return stats


def test_tool_no_stats_file_shows_setup_hint(monkeypatch, offline):
    monkeypatch.setattr(arena_stats, "load_stats", lambda: None)
    out = do_arena_stats("蓋倫")
    assert "尚未產生統計資料" in out and "crawl_arena.py" in out


def test_tool_champion_query(offline, fake_stats):
    out = do_arena_stats("悟空")
    assert "悟空" in out and "平均名次:2.00" in out
    assert "地獄三頭犬" in out                    # topAugments
    assert "非全服統計" in out                    # 誠實聲明


def test_tool_augment_query(offline, fake_stats):
    out = do_arena_stats("Cerberus")
    assert "地獄三頭犬" in out and "悟空" in out   # topChamps


def test_tool_leaderboard_empty_query(offline, fake_stats):
    out = do_arena_stats("")
    assert "英雄勝率排行" in out and "強化勝率排行" in out
    assert "蓋倫" in out


def test_tool_unknown_query(offline, fake_stats):
    out = do_arena_stats("完全不存在的東西xyz")
    assert "找不到" in out


def test_tool_stale_warning(monkeypatch, fake_stats):
    class FakeResult:
        class data:
            patch = "26.15"
    monkeypatch.setattr(arena_stats, "get_arena_data", lambda: FakeResult())
    monkeypatch.setattr(arena_stats, "get_champions",
                        lambda: (_ for _ in ()).throw(RuntimeError()))
    out = do_arena_stats("悟空")
    assert "26.15" in out and "重新爬取" in out
