"""Unit tests for SRCDS / raw log parsing (command service)."""

from __future__ import annotations

from cqrs.command_service.app.parsers import SrcdsLogParser, parse_srcds_log
from cqrs.shared.steam import canonical_steam_id


def test_parse_kv_format_happy_path():
    raw = (
        "map_name=cp_process_final blu_score=3 red_score=1 duration_seconds=2100 "
        "player steam_id=STEAM_1:1:424242 team=blu class=scout "
        "kills=12 deaths=4 assists=3 dpm=380.5 healing=0 "
        "captures=2 headshots=5 "
        "player steam_id=STEAM_1:1:67890 team=red class=soldier "
        "kills=8 deaths=9 assists=1 dpm=410 healing=0 airshots=3"
    )
    match = parse_srcds_log(raw)

    assert match.map_name == "cp_process_final"
    assert match.blu_score == 3
    assert match.red_score == 1
    assert match.duration_seconds == 2100
    assert len(match.players) == 2

    scout = next(p for p in match.players if p.primary_class == "scout")
    assert scout.steam_id == canonical_steam_id("STEAM_1:1:424242")
    assert scout.team == "blu"
    assert scout.kills == 12
    assert scout.deaths == 4
    assert scout.assists == 3
    assert scout.captures == 2
    assert scout.headshots == 5
    assert scout.class_stats
    assert scout.class_stats[0].class_name == "scout"
    assert scout.class_stats[0].damage_dealt > 0


def test_parse_live_log_format_from_kill_events():
    raw = (
        "Started map cp_badlands\n"
        '"ScoutPlayer<3><STEAM_1:0:11111><Blue>" killed '
        '"SoldierVictim<4><STEAM_1:0:22222><Red>" (headshot)\n'
        '"MedicAssist<5><STEAM_1:0:33333><Blue>" triggered "kill assist"\n'
        '"ScoutPlayer<3><STEAM_1:0:11111><Blue>" changed role to "scout"\n'
        '"SoldierVictim<4><STEAM_1:0:22222><Red>" changed role to "soldier"\n'
        "blu_score=2 red_score=0"
    )
    match = SrcdsLogParser().parse(raw)

    assert match.map_name == "cp_badlands"
    assert match.blu_score == 2
    assert match.red_score == 0
    assert len(match.players) == 3

    killer = next(
        p for p in match.players if p.steam_id == canonical_steam_id("STEAM_1:0:11111")
    )
    assert killer.kills == 1
    assert killer.deaths == 0
    assert killer.team == "blu"
    assert "scout" in killer.classes_played

    victim = next(
        p for p in match.players if p.steam_id == canonical_steam_id("STEAM_1:0:22222")
    )
    assert victim.kills == 0
    assert victim.deaths == 1

    assist = next(
        p for p in match.players if p.steam_id == canonical_steam_id("STEAM_1:0:33333")
    )
    assert assist.assists == 1


def test_parse_defaults_when_fields_missing():
    match = parse_srcds_log(
        "player steam_id=STEAM_1:1:1 team=blu class=scout kills=0 deaths=0 assists=0"
    )

    assert match.map_name == "unknown_map"
    assert match.blu_score == 0
    assert match.red_score == 0
    assert match.duration_seconds == 1800
    assert len(match.players) == 1


def test_parse_multi_class_kv_player_rolls_up_stats():
    raw = (
        "map_name=cp_snakewater blu_score=1 red_score=0 duration_seconds=1200 "
        "player steam_id=STEAM_1:1:999 team=blu class=scout kills=5 deaths=2 assists=1 dpm=300 "
        "player steam_id=STEAM_1:1:999 team=blu class=soldier kills=3 deaths=1 assists=0 dpm=400"
    )
    match = parse_srcds_log(raw)

    assert len(match.players) == 1
    player = match.players[0]
    assert player.kills == 8
    assert player.deaths == 3
    assert player.assists == 1
    assert len(player.class_stats) == 2
    assert {row.class_name for row in player.class_stats} == {"scout", "soldier"}


def test_kill_events_skip_lines_involving_bots():
    """Kill lines where either party is BOT are ignored entirely."""
    raw = (
        '"Player<1><STEAM_1:0:55555><Blue>" killed "BOT<2><BOT><Red>"\n'
        '"BOT<2><BOT><Red>" killed "Player<1><STEAM_1:0:55555><Blue>"'
    )
    match = parse_srcds_log(raw)
    assert match.players == []


def test_kill_events_between_humans_are_parsed():
    raw = (
        '"Attacker<1><STEAM_1:0:55555><Blue>" killed '
        '"Victim<2><STEAM_1:0:66666><Red>" (headshot)\n'
        '"Victim<2><STEAM_1:0:66666><Red>" killed '
        '"Attacker<1><STEAM_1:0:55555><Blue>"'
    )
    match = parse_srcds_log(raw)

    assert len(match.players) == 2
    attacker = next(
        p for p in match.players if p.steam_id == canonical_steam_id("STEAM_1:0:55555")
    )
    victim = next(
        p for p in match.players if p.steam_id == canonical_steam_id("STEAM_1:0:66666")
    )
    assert attacker.kills == 1
    assert attacker.deaths == 1
    assert victim.kills == 1
    assert victim.deaths == 1
