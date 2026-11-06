"""SRCDS / TF2 log parsing into write-side command models."""

from __future__ import annotations

import re
from collections import defaultdict
from uuid import uuid4

from ...shared.schemas import ClassStatSnapshot, MatchCommandModel, PlayerStatSnapshot
from ...shared.steam import canonical_steam_id
from ...shared.tf2_classes import class_id_from_name, normalize_class_name

MAP_RE = re.compile(r"(?:map_name|Started map)\s*[= ]\s*(?P<map>\S+)", re.IGNORECASE)
SCORE_RE = re.compile(r"(?P<team>blu|blue|red)_score=(?P<score>\d+)", re.IGNORECASE)
DURATION_RE = re.compile(r"duration(?:_seconds)?=(?P<seconds>\d+)", re.IGNORECASE)
KV_PLAYER_RE = re.compile(
    r"player\s+"
    r"steam_id=(?P<steam_id>\S+)\s+"
    r"team=(?P<team>\S+)\s+"
    r"class=(?P<class>\S+)\s+"
    r"kills=(?P<kills>\d+)\s+"
    r"deaths=(?P<deaths>\d+)\s+"
    r"assists=(?P<assists>\d+)"
    r"(?:\s+dpm=(?P<dpm>[\d.]+))?"
    r"(?:\s+healing=(?P<healing>\d+))?"
    r"(?:\s+damage_dealt=(?P<damage_dealt>\d+))?"
    r"(?:\s+damage_received=(?P<damage_received>\d+))?"
    r"(?:\s+heals_received=(?P<heals_received>\d+))?"
    r"(?:\s+captures=(?P<captures>\d+))?"
    r"(?:\s+primary_accuracy=(?P<primary_accuracy>[\d.]+))?"
    r"(?:\s+headshots=(?P<headshots>\d+))?"
    r"(?:\s+backstabs=(?P<backstabs>\d+))?"
    r"(?:\s+airshots=(?P<airshots>\d+))?"
    r"(?:\s+ubers=(?P<ubers>\d+))?"
    r"(?:\s+drops=(?P<drops>\d+))?",
    re.IGNORECASE,
)
KILL_RE = re.compile(
    r'"[^"]+<(?P<attacker_userid>\d+)><(?P<attacker_steam>[^>]+)><(?P<attacker_team>[^>]*)>"\s+killed\s+'
    r'"[^"]+<(?P<victim_userid>\d+)><(?P<victim_steam>[^>]+)><(?P<victim_team>[^>]*)>"',
    re.IGNORECASE,
)
ASSIST_RE = re.compile(
    r'"[^"]+<\d+><(?P<steam>[^>]+)><(?P<team>[^>]*)>"\s+triggered\s+"kill assist"',
    re.IGNORECASE,
)
CLASS_RE = re.compile(
    r'"[^"]+<\d+><(?P<steam>[^>]+)><(?P<team>[^>]*)>"\s+changed role to\s+"(?P<class>[^"]+)"',
    re.IGNORECASE,
)


def _normalize_team(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"blu", "blue", "team blue"}:
        return "blu"
    if value in {"red", "team red"}:
        return "red"
    return value or "unknown"


def _normalize_steam(raw: str) -> str:
    return canonical_steam_id(raw.strip())


def _synthesize_class_stats(
    player: PlayerStatSnapshot, match_duration: int
) -> list[ClassStatSnapshot]:
    """Build MatchStat-equivalent class rows when nested class_stats are absent."""
    if player.class_stats:
        return list(player.class_stats)

    class_name = normalize_class_name(
        player.primary_class or primary_from_list(player.classes_played)
    )
    playtime = int(player.playtime_seconds or match_duration or 0)
    damage_dealt = (
        round(float(player.damage_per_minute or 0.0) * (playtime / 60.0))
        if playtime
        else 0
    )
    is_medic = class_name == "medic"
    return [
        ClassStatSnapshot(
            class_name=class_name,
            class_id=class_id_from_name(class_name),
            playtime_seconds=playtime,
            kills=player.kills,
            deaths=player.deaths,
            assists=player.assists,
            dpm=float(player.damage_per_minute or 0.0),
            primary_accuracy=0.0,
            damage_dealt=damage_dealt,
            damage_received=int(player.damage_received or 0),
            heals_received=int(player.heals_received or 0),
            healing_done=int(player.healing_done or 0) if is_medic else 0,
        )
    ]


def primary_from_list(classes_played: list[str]) -> str:
    return classes_played[0] if classes_played else "unknown"


class SrcdsLogParser:
    """Parse raw TF2/SRCDS logs into a MatchCommandModel."""

    def parse(self, raw_log: str) -> MatchCommandModel:
        map_name = self._extract_map(raw_log)
        blu_score, red_score = self._extract_scores(raw_log)
        duration = self._extract_duration(raw_log)
        players = self._extract_players(raw_log)
        enriched: list[PlayerStatSnapshot] = []
        for player in players:
            playtime = player.playtime_seconds or duration
            class_stats = _synthesize_class_stats(
                player.model_copy(update={"playtime_seconds": playtime}),
                duration,
            )
            enriched.append(
                player.model_copy(
                    update={
                        "playtime_seconds": playtime,
                        "class_stats": class_stats,
                        "primary_class": class_stats[0].class_name
                        if class_stats
                        else player.primary_class,
                        "classes_played": [row.class_name for row in class_stats]
                        or player.classes_played,
                    }
                )
            )
        return MatchCommandModel(
            match_id=uuid4(),
            map_name=map_name,
            blu_score=blu_score,
            red_score=red_score,
            duration_seconds=duration,
            players=enriched,
        )

    @staticmethod
    def _extract_map(raw_log: str) -> str:
        match = MAP_RE.search(raw_log)
        if not match:
            return "unknown_map"
        return match.group("map").strip("\"'")

    @staticmethod
    def _extract_scores(raw_log: str) -> tuple[int, int]:
        blu_score = 0
        red_score = 0
        for match in SCORE_RE.finditer(raw_log):
            team = _normalize_team(match.group("team"))
            score = int(match.group("score"))
            if team == "blu":
                blu_score = score
            elif team == "red":
                red_score = score
        return blu_score, red_score

    @staticmethod
    def _extract_duration(raw_log: str) -> int:
        match = DURATION_RE.search(raw_log)
        return int(match.group("seconds")) if match else 1800

    def _extract_players(self, raw_log: str) -> list[PlayerStatSnapshot]:
        kv_players = self._extract_kv_players(raw_log)
        if kv_players:
            return kv_players
        return self._extract_live_players(raw_log)

    @staticmethod
    def _extract_kv_players(raw_log: str) -> list[PlayerStatSnapshot]:
        # Keep one row per (steam_id, class) then roll up to player + nested class_stats.
        by_steam: dict[str, list[ClassStatSnapshot]] = defaultdict(list)
        teams: dict[str, str] = {}
        captures_by_steam: dict[str, int] = defaultdict(int)
        headshots_by_steam: dict[str, int] = defaultdict(int)
        backstabs_by_steam: dict[str, int] = defaultdict(int)
        airshots_by_steam: dict[str, int] = defaultdict(int)
        ubers_by_steam: dict[str, int] = defaultdict(int)
        drops_by_steam: dict[str, int] = defaultdict(int)
        for match in KV_PLAYER_RE.finditer(raw_log):
            steam_id = _normalize_steam(match.group("steam_id"))
            class_name = normalize_class_name(match.group("class"))
            teams[steam_id] = _normalize_team(match.group("team"))
            captures_by_steam[steam_id] = max(
                captures_by_steam[steam_id], int(match.group("captures") or 0)
            )
            headshots_by_steam[steam_id] = max(
                headshots_by_steam[steam_id], int(match.group("headshots") or 0)
            )
            backstabs_by_steam[steam_id] = max(
                backstabs_by_steam[steam_id], int(match.group("backstabs") or 0)
            )
            airshots_by_steam[steam_id] = max(
                airshots_by_steam[steam_id], int(match.group("airshots") or 0)
            )
            ubers_by_steam[steam_id] = max(
                ubers_by_steam[steam_id], int(match.group("ubers") or 0)
            )
            drops_by_steam[steam_id] = max(
                drops_by_steam[steam_id], int(match.group("drops") or 0)
            )
            dpm = float(match.group("dpm") or 0.0)
            healing = int(match.group("healing") or 0)
            damage_dealt = int(match.group("damage_dealt") or 0)
            if damage_dealt <= 0 and dpm > 0:
                # Approximate until playtime is known at match level.
                damage_dealt = round(dpm * 30.0)
            is_medic = class_name == "medic"
            by_steam[steam_id].append(
                ClassStatSnapshot(
                    class_name=class_name,
                    class_id=class_id_from_name(class_name),
                    playtime_seconds=0,
                    kills=int(match.group("kills")),
                    deaths=int(match.group("deaths")),
                    assists=int(match.group("assists")),
                    dpm=dpm,
                    primary_accuracy=float(match.group("primary_accuracy") or 0.0),
                    damage_dealt=damage_dealt,
                    damage_received=int(match.group("damage_received") or 0),
                    heals_received=int(match.group("heals_received") or 0),
                    healing_done=healing if is_medic else 0,
                )
            )

        players: list[PlayerStatSnapshot] = []
        for steam_id, class_rows in by_steam.items():
            kills = sum(row.kills for row in class_rows)
            deaths = sum(row.deaths for row in class_rows)
            assists = sum(row.assists for row in class_rows)
            healing = sum(row.healing_done for row in class_rows)
            dpm = max((row.dpm for row in class_rows), default=0.0)
            players.append(
                PlayerStatSnapshot(
                    steam_id=steam_id,
                    team=teams.get(steam_id, "unknown"),
                    classes_played=[row.class_name for row in class_rows],
                    primary_class=class_rows[0].class_name,
                    playtime_seconds=0,
                    kills=kills,
                    deaths=deaths,
                    assists=assists,
                    damage_per_minute=dpm,
                    healing_done=healing,
                    damage_received=max(
                        (row.damage_received for row in class_rows), default=0
                    ),
                    heals_received=max(
                        (row.heals_received for row in class_rows), default=0
                    ),
                    ubers=ubers_by_steam[steam_id],
                    drops=drops_by_steam[steam_id],
                    captures=captures_by_steam[steam_id],
                    headshots=headshots_by_steam[steam_id],
                    backstabs=backstabs_by_steam[steam_id],
                    airshots=airshots_by_steam[steam_id],
                    class_stats=class_rows,
                )
            )
        return players

    @staticmethod
    def _extract_live_players(raw_log: str) -> list[PlayerStatSnapshot]:
        kills: dict[str, int] = defaultdict(int)
        deaths: dict[str, int] = defaultdict(int)
        assists: dict[str, int] = defaultdict(int)
        teams: dict[str, str] = {}
        classes: dict[str, set[str]] = defaultdict(set)

        for match in KILL_RE.finditer(raw_log):
            attacker = _normalize_steam(match.group("attacker_steam"))
            victim = _normalize_steam(match.group("victim_steam"))
            if attacker in {"BOT", "Console", "0"} or victim in {"BOT", "Console", "0"}:
                continue
            kills[attacker] += 1
            deaths[victim] += 1
            teams[attacker] = _normalize_team(match.group("attacker_team"))
            teams[victim] = _normalize_team(match.group("victim_team"))

        for match in ASSIST_RE.finditer(raw_log):
            steam_id = _normalize_steam(match.group("steam"))
            assists[steam_id] += 1
            teams.setdefault(steam_id, _normalize_team(match.group("team")))

        for match in CLASS_RE.finditer(raw_log):
            steam_id = _normalize_steam(match.group("steam"))
            classes[steam_id].add(normalize_class_name(match.group("class")))
            teams.setdefault(steam_id, _normalize_team(match.group("team")))

        steam_ids = set(kills) | set(deaths) | set(assists) | set(classes)
        result: list[PlayerStatSnapshot] = []
        for steam_id in sorted(steam_ids):
            class_list = sorted(classes.get(steam_id) or [])
            result.append(
                PlayerStatSnapshot(
                    steam_id=steam_id,
                    team=teams.get(steam_id, "unknown"),
                    classes_played=class_list,
                    primary_class=class_list[0] if class_list else "unknown",
                    playtime_seconds=0,
                    kills=kills.get(steam_id, 0),
                    deaths=deaths.get(steam_id, 0),
                    assists=assists.get(steam_id, 0),
                )
            )
        return result


def parse_srcds_log(raw_log: str) -> MatchCommandModel:
    return SrcdsLogParser().parse(raw_log)
