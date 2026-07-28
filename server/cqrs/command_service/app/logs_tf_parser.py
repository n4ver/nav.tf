"""Convert logs.tf JSON payloads into write-side command models."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ...shared.rating import class_id_from_name, normalize_class_name
from ...shared.schemas import ClassStatSnapshot, MatchCommandModel, PlayerStatSnapshot
from ...shared.steam import canonical_steam_id

LOGS_TF_NAMESPACE = NAMESPACE_URL


def _normalize_team(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"blu", "blue"}:
        return "blu"
    if value == "red":
        return "red"
    return value or "unknown"


def _primary_accuracy(class_row: dict[str, Any]) -> float:
    weapon = class_row.get("weapon") or {}
    if isinstance(weapon, dict):
        primary = weapon.get("primary") or {}
        if isinstance(primary, dict):
            return float(primary.get("acc") or 0.0)
    return 0.0


def parse_logs_tf(data: dict[str, Any], log_id: int) -> MatchCommandModel:
    """Map a logs.tf API document to MatchCommandModel."""
    info = data.get("info") or {}
    teams = data.get("teams") or {}
    map_name = info.get("map") or "unknown_map"
    blu_score = int((teams.get("Blue") or {}).get("score", 0))
    red_score = int((teams.get("Red") or {}).get("score", 0))
    duration_seconds = int(data.get("length") or 1800)
    players = _extract_players(data)

    return MatchCommandModel(
        match_id=uuid5(LOGS_TF_NAMESPACE, f"logs.tf:{log_id}"),
        map_name=map_name,
        blu_score=blu_score,
        red_score=red_score,
        duration_seconds=duration_seconds,
        players=players,
    )


def _extract_players(data: dict[str, Any]) -> list[PlayerStatSnapshot]:
    snapshots: list[PlayerStatSnapshot] = []
    names = data.get("names") or {}
    for raw_steam_id, player in (data.get("players") or {}).items():
        steam_id = canonical_steam_id(str(raw_steam_id))
        class_rows = player.get("class_stats") or []
        damage_received = int(player.get("dt") or 0)
        heals_received = int(player.get("hr") or 0)
        healing_done = int(player.get("heal") or 0)
        ubers = int(player.get("ubers") or 0)
        drops = int(player.get("drops") or 0)
        display_name = None
        if isinstance(names, dict):
            raw_name = names.get(raw_steam_id) or names.get(steam_id)
            if raw_name:
                display_name = str(raw_name).strip() or None

        class_stats: list[ClassStatSnapshot] = []
        for row in class_rows:
            class_name = normalize_class_name(str(row.get("type") or "unknown"))
            playtime = int(row.get("total_time") or 0)
            damage_dealt = int(row.get("dmg") or 0)
            dpm = damage_dealt / (playtime / 60) if playtime > 0 else 0.0
            is_medic = class_name == "medic"
            class_stats.append(
                ClassStatSnapshot(
                    class_name=class_name,
                    class_id=class_id_from_name(class_name),
                    playtime_seconds=playtime,
                    kills=int(row.get("kills") or 0),
                    deaths=int(row.get("deaths") or 0),
                    assists=int(row.get("assists") or 0),
                    dpm=round(dpm, 2),
                    primary_accuracy=_primary_accuracy(row),
                    damage_dealt=damage_dealt,
                    # Legacy ingest applies player-level dt/hr onto every class row.
                    damage_received=damage_received,
                    heals_received=heals_received,
                    captures=int(row.get("cpc") or 0),
                    headshots=int(row.get("headshots") or 0),
                    backstabs=int(row.get("backstabs") or 0),
                    airshots=int(row.get("as") or 0),
                    ubers=ubers if is_medic else 0,
                    drops=drops if is_medic else 0,
                    healing_done=healing_done if is_medic else 0,
                )
            )

        classes_played = [item.class_name for item in class_stats]
        total_time = sum(item.playtime_seconds for item in class_stats)
        total_damage = sum(item.damage_dealt for item in class_stats)
        dpm = total_damage / (total_time / 60) if total_time > 0 else 0.0
        primary = "unknown"
        if class_stats:
            primary = max(class_stats, key=lambda item: item.playtime_seconds).class_name
        elif classes_played:
            primary = classes_played[0]

        snapshots.append(
            PlayerStatSnapshot(
                steam_id=steam_id,
                team=_normalize_team(player.get("team", "")),
                display_name=display_name,
                classes_played=classes_played,
                primary_class=primary,
                playtime_seconds=total_time,
                kills=int(player.get("kills") or 0),
                deaths=int(player.get("deaths") or 0),
                assists=int(player.get("assists") or 0),
                damage_per_minute=round(dpm, 2),
                healing_done=healing_done,
                damage_received=damage_received,
                heals_received=heals_received,
                ubers=ubers,
                drops=drops,
                class_stats=class_stats,
            )
        )
    return snapshots
