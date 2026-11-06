#!/usr/bin/env python3
"""Generate CDM YAML files under cdm/models/ from canonical definitions."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent / "cdm" / "models"


def write_model(name: str, data: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / f"{name}.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)


CLASS_STAT_FIELDS = [
    {"name": "class_name", "type": "string", "required": True},
    {"name": "class_id", "type": "integer", "required": True},
    {"name": "playtime_seconds", "type": "integer", "required": False, "default": 0},
    {"name": "kills", "type": "integer", "required": False, "default": 0},
    {"name": "deaths", "type": "integer", "required": False, "default": 0},
    {"name": "assists", "type": "integer", "required": False, "default": 0},
    {"name": "dpm", "type": "float", "required": False, "default": 0.0},
    {"name": "primary_accuracy", "type": "float", "required": False, "default": 0.0},
    {"name": "damage_dealt", "type": "integer", "required": False, "default": 0},
    {"name": "damage_received", "type": "integer", "required": False, "default": 0},
    {"name": "heals_received", "type": "integer", "required": False, "default": 0},
    {"name": "healing_done", "type": "integer", "required": False, "default": 0},
]


def main() -> None:
    write_model(
        "RawLogUpload",
        {
            "model": "RawLogUpload",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Upload raw SRCDS log text for parsing and ingestion.",
            "fields": [
                {"name": "log_data", "type": "string", "required": True, "description": "Full SRCDS log file contents"},
                {"name": "timestamp", "type": "datetime", "required": False, "description": "Ingest timestamp; defaults to server UTC now"},
                {"name": "tournament_id", "type": "uuid", "required": False, "description": "Optional write-side tournament UUID"},
            ],
        },
    )

    write_model(
        "CachedLogIngest",
        {
            "model": "CachedLogIngest",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Ingest a log from the seed cache or inline JSON payload.",
            "fields": [
                {"name": "log_id", "type": "integer", "required": True, "description": "logs.tf log identifier"},
                {"name": "tournament_id", "type": "integer", "required": True, "description": "Seed catalog tournament id"},
                {"name": "section", "type": "string", "required": False, "default": "unknown", "description": "Seed section label"},
                {"name": "data", "type": "object", "required": False, "description": "Inline logs.tf JSON; loaded from SEED_CACHE_PATH when omitted"},
                {"name": "timestamp", "type": "datetime", "required": False, "description": "Match played timestamp override"},
            ],
        },
    )

    write_model(
        "IngestLogsTfCommand",
        {
            "model": "IngestLogsTfCommand",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Fetch and ingest a log live from the logs.tf API.",
            "fields": [
                {"name": "logstf_id", "type": "integer", "required": True, "constraints": ["gt: 0"], "description": "logs.tf log id"},
                {"name": "tournament_id", "type": "uuid", "required": False, "description": "Optional write-side tournament UUID"},
            ],
        },
    )

    write_model(
        "UpdatePlayerDisplayNameCommand",
        {
            "model": "UpdatePlayerDisplayNameCommand",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Admin command to set a player display alias.",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True, "description": "SteamID2 or SteamID64"},
                {"name": "display_name", "type": "string", "required": True, "constraints": ["min_length: 1", "max_length: 128"]},
            ],
        },
    )

    write_model(
        "CreateTournamentCommand",
        {
            "model": "CreateTournamentCommand",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Create a tournament aggregate on the write side.",
            "fields": [
                {"name": "name", "type": "string", "required": True, "constraints": ["min_length: 1", "max_length: 128"]},
                {"name": "slug", "type": "string", "required": True, "constraints": ["min_length: 1", "max_length: 128"]},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
                {"name": "event_id", "type": "uuid", "required": False},
            ],
        },
    )

    write_model(
        "UpdateTournamentCommand",
        {
            "model": "UpdateTournamentCommand",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Partial update of a tournament aggregate.",
            "fields": [
                {"name": "name", "type": "string", "required": False, "constraints": ["min_length: 1", "max_length: 128"]},
                {"name": "slug", "type": "string", "required": False, "constraints": ["min_length: 1", "max_length: 128"]},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
                {"name": "event_id", "type": "uuid", "required": False},
            ],
        },
    )

    write_model(
        "ClassStatSnapshot",
        {
            "model": "ClassStatSnapshot",
            "kind": "domain",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Per-class stats embedded in MatchParsed integration events.",
            "fields": CLASS_STAT_FIELDS,
        },
    )

    write_model(
        "PlayerStatSnapshot",
        {
            "model": "PlayerStatSnapshot",
            "kind": "domain",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Per-player stats embedded in MatchParsed integration events.",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True},
                {"name": "team", "type": "string", "required": True, "description": "blu or red"},
                {"name": "display_name", "type": "string", "required": False},
                {"name": "classes_played", "type": "array<string>", "required": False, "default": []},
                {"name": "primary_class", "type": "string", "required": False, "default": "unknown"},
                {"name": "playtime_seconds", "type": "integer", "required": False, "default": 0},
                {"name": "kills", "type": "integer", "required": False, "default": 0},
                {"name": "deaths", "type": "integer", "required": False, "default": 0},
                {"name": "assists", "type": "integer", "required": False, "default": 0},
                {"name": "damage_per_minute", "type": "float", "required": False, "default": 0.0},
                {"name": "healing_done", "type": "integer", "required": False, "default": 0},
                {"name": "damage_received", "type": "integer", "required": False, "default": 0},
                {"name": "heals_received", "type": "integer", "required": False, "default": 0},
                {"name": "ubers", "type": "integer", "required": False, "default": 0},
                {"name": "drops", "type": "integer", "required": False, "default": 0},
                {"name": "captures", "type": "integer", "required": False, "default": 0},
                {"name": "headshots", "type": "integer", "required": False, "default": 0},
                {"name": "backstabs", "type": "integer", "required": False, "default": 0},
                {"name": "airshots", "type": "integer", "required": False, "default": 0},
                {"name": "class_stats", "type": "array<ClassStatSnapshot>", "required": False, "default": []},
            ],
            "relationships": [{"field": "class_stats", "target": "ClassStatSnapshot", "cardinality": "1:N"}],
        },
    )

    write_model(
        "MatchCommandModel",
        {
            "model": "MatchCommandModel",
            "kind": "domain",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Normalized match aggregate produced by command-side parsers.",
            "fields": [
                {"name": "match_id", "type": "uuid", "required": True},
                {"name": "map_name", "type": "string", "required": True},
                {"name": "blu_score", "type": "integer", "required": True},
                {"name": "red_score", "type": "integer", "required": True},
                {"name": "duration_seconds", "type": "integer", "required": False, "default": 1800},
                {"name": "players", "type": "array<PlayerStatSnapshot>", "required": False, "default": []},
            ],
            "relationships": [{"field": "players", "target": "PlayerStatSnapshot", "cardinality": "1:N"}],
        },
    )

    write_model(
        "TournamentCommandModel",
        {
            "model": "TournamentCommandModel",
            "kind": "domain",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Tournament metadata tagged onto ingested matches.",
            "fields": [
                {"name": "tournament_id", "type": "uuid", "required": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
                {"name": "event_id", "type": "uuid", "required": False},
            ],
        },
    )

    write_model(
        "AuthUserView",
        {
            "model": "AuthUserView",
            "kind": "auth",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Authenticated user profile returned by GET /api/auth/me.",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True},
                {"name": "display_name", "type": "string", "required": True},
                {"name": "avatar_url", "type": "string", "required": False},
                {"name": "role", "type": "string", "required": True, "description": "player | admin"},
            ],
        },
    )

    write_model(
        "AuthCodeExchangeRequest",
        {
            "model": "AuthCodeExchangeRequest",
            "kind": "auth",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Exchange a one-time login code for a JWT.",
            "fields": [
                {"name": "code", "type": "string", "required": True, "constraints": ["min_length: 1", "max_length: 256"]},
            ],
        },
    )

    write_model(
        "AuthTokenResponse",
        {
            "model": "AuthTokenResponse",
            "kind": "auth",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "JWT bearer token issued after code exchange.",
            "fields": [{"name": "token", "type": "string", "required": True}],
        },
    )

    write_model(
        "MatchSummaryView",
        {
            "model": "MatchSummaryView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Match list row and summary header on match detail.",
            "fields": [
                {"name": "match_id", "type": "uuid", "required": True},
                {"name": "tournament_id", "type": "uuid", "required": False},
                {"name": "source_log_id", "type": "integer", "required": False},
                {"name": "map_name", "type": "string", "required": True},
                {"name": "duration_seconds", "type": "integer", "required": True},
                {"name": "winning_team", "type": "string", "required": True},
                {"name": "blu_score", "type": "integer", "required": False, "default": 0},
                {"name": "red_score", "type": "integer", "required": False, "default": 0},
                {"name": "date_played", "type": "datetime", "required": True},
                {"name": "ratings_ready", "type": "boolean", "required": False, "default": False},
            ],
            "relationships": [{"projection": "MatchSummaryProjection", "mapping": "1:1"}],
        },
    )

    write_model(
        "TournamentSummaryView",
        {
            "model": "TournamentSummaryView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Tournament catalog row.",
            "fields": [
                {"name": "tournament_id", "type": "uuid", "required": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True},
                {"name": "match_count", "type": "integer", "required": True},
                {"name": "started_at", "type": "datetime", "required": False},
                {"name": "event_id", "type": "uuid", "required": False},
            ],
        },
    )

    class_stat_view_fields = CLASS_STAT_FIELDS + [
        {"name": "rating", "type": "float", "required": False, "default": 1.0}
    ]
    write_model(
        "ClassStatView",
        {
            "model": "ClassStatView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Per-class stats on match detail including computed rating.",
            "fields": class_stat_view_fields,
        },
    )

    write_model(
        "PlayerStatsView",
        {
            "model": "PlayerStatsView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Per-player match detail row including class breakdown.",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True},
                {"name": "match_id", "type": "uuid", "required": True},
                {"name": "team", "type": "string", "required": True},
                {"name": "display_name", "type": "string", "required": False},
                {"name": "classes_played", "type": "array<string>", "required": True},
                {"name": "primary_class", "type": "string", "required": False, "default": "unknown"},
                {"name": "playtime_seconds", "type": "integer", "required": False, "default": 0},
                {"name": "kills", "type": "integer", "required": True},
                {"name": "deaths", "type": "integer", "required": True},
                {"name": "assists", "type": "integer", "required": True},
                {"name": "damage_per_minute", "type": "float", "required": True},
                {"name": "healing_done", "type": "integer", "required": True},
                {"name": "damage_received", "type": "integer", "required": False, "default": 0},
                {"name": "heals_received", "type": "integer", "required": False, "default": 0},
                {"name": "ubers", "type": "integer", "required": False, "default": 0},
                {"name": "drops", "type": "integer", "required": False, "default": 0},
                {"name": "captures", "type": "integer", "required": False, "default": 0},
                {"name": "headshots", "type": "integer", "required": False, "default": 0},
                {"name": "backstabs", "type": "integer", "required": False, "default": 0},
                {"name": "airshots", "type": "integer", "required": False, "default": 0},
                {"name": "rating", "type": "float", "required": False, "default": 1.0},
                {"name": "class_stats", "type": "array<ClassStatView>", "required": False, "default": []},
            ],
        },
    )

    write_model(
        "PlayerClassAggregateView",
        {
            "model": "PlayerClassAggregateView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Lifetime per-class aggregate on player profile.",
            "fields": [
                {"name": "class_name", "type": "string", "required": True},
                {"name": "matches_played", "type": "integer", "required": True},
                {"name": "total_kills", "type": "integer", "required": True},
                {"name": "total_deaths", "type": "integer", "required": True},
                {"name": "total_assists", "type": "integer", "required": True},
                {"name": "average_damage_per_minute", "type": "float", "required": True},
                {"name": "total_healing_done", "type": "integer", "required": True},
                {"name": "average_rating", "type": "float", "required": True},
            ],
        },
    )

    write_model(
        "PlayerRecentMatchView",
        {
            "model": "PlayerRecentMatchView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Recent match snippet on player profile.",
            "fields": [
                {"name": "match_id", "type": "uuid", "required": True},
                {"name": "map_name", "type": "string", "required": True},
                {"name": "date_played", "type": "datetime", "required": True},
                {"name": "team", "type": "string", "required": True},
                {"name": "classes_played", "type": "array<string>", "required": False, "default": []},
                {"name": "kills", "type": "integer", "required": True},
                {"name": "deaths", "type": "integer", "required": True},
                {"name": "assists", "type": "integer", "required": True},
                {"name": "damage_per_minute", "type": "float", "required": True},
                {"name": "healing_done", "type": "integer", "required": False, "default": 0},
                {"name": "rating", "type": "float", "required": False, "default": 1.0},
            ],
        },
    )

    write_model(
        "PlayerLifetimeStatsView",
        {
            "model": "PlayerLifetimeStatsView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Full player profile aggregate.",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True},
                {"name": "display_name", "type": "string", "required": False},
                {"name": "matches_played", "type": "integer", "required": True},
                {"name": "total_kills", "type": "integer", "required": True},
                {"name": "total_deaths", "type": "integer", "required": True},
                {"name": "total_assists", "type": "integer", "required": True},
                {"name": "average_damage_per_minute", "type": "float", "required": True},
                {"name": "total_healing_done", "type": "integer", "required": True},
                {"name": "average_rating", "type": "float", "required": False, "default": 1.0},
                {"name": "class_breakdown", "type": "array<PlayerClassAggregateView>", "required": False, "default": []},
                {"name": "recent_matches", "type": "array<PlayerRecentMatchView>", "required": False, "default": []},
            ],
        },
    )

    write_model(
        "LeaderboardEntryView",
        {
            "model": "LeaderboardEntryView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Tournament leaderboard row (all-classes or per-class).",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True},
                {"name": "display_name", "type": "string", "required": False},
                {"name": "matches_played", "type": "integer", "required": True},
                {"name": "total_kills", "type": "integer", "required": True},
                {"name": "total_deaths", "type": "integer", "required": True},
                {"name": "total_assists", "type": "integer", "required": True},
                {"name": "average_damage_per_minute", "type": "float", "required": True},
                {"name": "total_healing_done", "type": "integer", "required": True},
                {"name": "average_rating", "type": "float", "required": True},
                {"name": "primary_class", "type": "string", "required": False, "default": "unknown"},
            ],
        },
    )

    write_model(
        "ClassRatingBenchmarkView",
        {
            "model": "ClassRatingBenchmarkView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Public class rating baseline statistics.",
            "fields": [
                {"name": "class_name", "type": "string", "required": True},
                {"name": "class_id", "type": "integer", "required": True},
                {"name": "sample_size", "type": "integer", "required": True},
                {"name": "avg_rating", "type": "float", "required": True},
                {"name": "std_rating", "type": "float", "required": False, "default": 0.0},
                {"name": "min_rating", "type": "float", "required": True},
                {"name": "max_rating", "type": "float", "required": True},
                {"name": "p50_rating", "type": "float", "required": False, "default": 1.0},
            ],
        },
    )

    write_model(
        "SearchResultView",
        {
            "model": "SearchResultView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Unified search hit for players, matches, or tournaments.",
            "fields": [
                {"name": "kind", "type": "string", "required": True, "description": "player | match | tournament"},
                {"name": "id", "type": "string", "required": True},
                {"name": "label", "type": "string", "required": True},
                {"name": "match_id", "type": "uuid", "required": False},
                {"name": "steam_id", "type": "string", "required": False},
                {"name": "display_name", "type": "string", "required": False},
                {"name": "source_log_id", "type": "integer", "required": False},
            ],
        },
    )

    write_model(
        "MatchDetailView",
        {
            "model": "MatchDetailView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/services.py",
            "description": "Composite match detail response (not a Pydantic model — API envelope).",
            "fields": [
                {"name": "match_summary", "type": "MatchSummaryView", "required": True},
                {"name": "players", "type": "array<PlayerStatsView>", "required": True},
            ],
        },
    )

    write_model(
        "CommandAcceptedResponse",
        {
            "model": "CommandAcceptedResponse",
            "kind": "response",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/services.py",
            "description": "Async command acceptance envelope (HTTP 202).",
            "fields": [
                {"name": "status", "type": "string", "required": True, "enum": ["accepted", "skipped"]},
                {"name": "match_id", "type": "uuid", "required": False, "description": "Present for log ingest commands"},
                {"name": "log_id", "type": "integer", "required": False, "description": "logs.tf source id when applicable"},
                {"name": "steam_id", "type": "string", "required": False, "description": "Present for display-name updates"},
                {"name": "display_name", "type": "string", "required": False},
                {"name": "tournament_id", "type": "uuid", "required": False, "description": "Present for tournament commands"},
                {"name": "name", "type": "string", "required": False},
                {"name": "slug", "type": "string", "required": False},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
            ],
        },
    )

    write_model(
        "EventEnvelope",
        {
            "model": "EventEnvelope",
            "kind": "event",
            "version": "1.0",
            "source": "server/cqrs/shared/events.py",
            "description": "RabbitMQ integration event wrapper. Routing key: events.{event_type}.",
            "fields": [
                {"name": "event_id", "type": "uuid", "required": True},
                {"name": "event_type", "type": "string", "required": True},
                {"name": "occurred_at", "type": "datetime", "required": True},
                {"name": "actor_id", "type": "string", "required": False, "description": "Admin steam_id when applicable"},
                {"name": "payload", "type": "object", "required": True},
            ],
        },
    )

    write_model(
        "MatchParsedPayload",
        {
            "model": "MatchParsedPayload",
            "kind": "event",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/services.py",
            "description": "Payload of MatchParsed event (event_type=MatchParsed).",
            "fields": [
                {"name": "match_id", "type": "uuid", "required": True},
                {"name": "map_name", "type": "string", "required": True},
                {"name": "blu_score", "type": "integer", "required": True},
                {"name": "red_score", "type": "integer", "required": True},
                {"name": "duration_seconds", "type": "integer", "required": True},
                {"name": "players", "type": "array<PlayerStatSnapshot>", "required": True},
                {"name": "date_played", "type": "datetime", "required": True},
                {"name": "tournament", "type": "TournamentCommandModel", "required": True},
                {"name": "source_log_id", "type": "integer", "required": False},
                {"name": "actor_id", "type": "string", "required": False},
            ],
            "relationships": [{"envelope": "EventEnvelope", "event_type": "MatchParsed"}],
        },
    )

    write_model(
        "LogEventCreatedPayload",
        {
            "model": "LogEventCreatedPayload",
            "kind": "event",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/services.py",
            "description": "Payload of LogEventCreated event.",
            "fields": [
                {"name": "match_id", "type": "uuid", "required": True},
                {"name": "source_log_id", "type": "integer", "required": False},
                {"name": "raw_log_persisted", "type": "boolean", "required": True},
                {"name": "actor_id", "type": "string", "required": False},
            ],
        },
    )

    write_model(
        "PlayerAliasUpdatedPayload",
        {
            "model": "PlayerAliasUpdatedPayload",
            "kind": "event",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/services.py",
            "description": "Payload of PlayerAliasUpdated event.",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True},
                {"name": "display_name", "type": "string", "required": True},
            ],
        },
    )

    write_model(
        "TournamentMutationPayload",
        {
            "model": "TournamentMutationPayload",
            "kind": "event",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/services.py",
            "description": "Payload of TournamentCreated and TournamentUpdated events.",
            "fields": [
                {"name": "tournament_id", "type": "uuid", "required": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
                {"name": "event_id", "type": "uuid", "required": False},
            ],
        },
    )

    write_model(
        "RawLogEvent",
        {
            "model": "RawLogEvent",
            "kind": "persistence-write",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/models.py",
            "database": "cqrs_command",
            "table": "raw_log_events",
            "description": "Immutable raw log ingest record.",
            "fields": [
                {"name": "id", "type": "integer", "required": False, "primary_key": True},
                {"name": "source_log_id", "type": "integer", "required": False, "unique": True, "indexed": True},
                {"name": "content_hash", "type": "string", "required": False, "unique": True, "indexed": True},
                {"name": "match_id", "type": "string", "required": True, "unique": True, "indexed": True},
                {"name": "raw_log", "type": "text", "required": True},
                {"name": "map_name", "type": "string", "required": True},
                {"name": "blu_score", "type": "integer", "required": True},
                {"name": "red_score", "type": "integer", "required": True},
                {"name": "timestamp", "type": "datetime", "required": True},
                {"name": "actor_id", "type": "string", "required": False, "indexed": True},
                {"name": "tournament_id", "type": "string", "required": False, "indexed": True},
            ],
        },
    )

    write_model(
        "OutboxEvent",
        {
            "model": "OutboxEvent",
            "kind": "persistence-write",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/models.py",
            "database": "cqrs_command",
            "table": "outbox_events",
            "description": "Transactional outbox row relayed to RabbitMQ.",
            "fields": [
                {"name": "id", "type": "integer", "required": False, "primary_key": True},
                {"name": "event_id", "type": "uuid", "required": True, "unique": True, "indexed": True},
                {"name": "event_type", "type": "string", "required": True, "indexed": True},
                {"name": "payload", "type": "text", "required": True, "description": "JSON-serialized EventEnvelope"},
                {"name": "status", "type": "enum", "required": True, "enum": ["pending", "published", "failed"], "default": "pending"},
                {"name": "created_at", "type": "datetime", "required": True, "indexed": True},
                {"name": "published_at", "type": "datetime", "required": False},
                {"name": "attempts", "type": "integer", "required": True, "default": 0},
                {"name": "last_error", "type": "string", "required": False},
            ],
        },
    )

    write_model(
        "User",
        {
            "model": "User",
            "kind": "persistence-write",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/models.py",
            "database": "cqrs_command",
            "table": "users",
            "description": "Authenticated Steam account on the write side.",
            "fields": [
                {"name": "id", "type": "integer", "required": False, "primary_key": True},
                {"name": "steam_id", "type": "string", "required": True, "unique": True, "indexed": True},
                {"name": "display_name", "type": "string", "required": True, "default": ""},
                {"name": "avatar_url", "type": "string", "required": False},
                {"name": "role", "type": "enum", "required": True, "enum": ["player", "admin"], "default": "player"},
                {"name": "created_at", "type": "datetime", "required": True},
                {"name": "updated_at", "type": "datetime", "required": True},
                {"name": "last_login_at", "type": "datetime", "required": False},
            ],
        },
    )

    write_model(
        "AuthLoginCode",
        {
            "model": "AuthLoginCode",
            "kind": "persistence-write",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/models.py",
            "database": "cqrs_command",
            "table": "auth_login_codes",
            "description": "One-time code exchanged for JWT after Steam OpenID redirect.",
            "fields": [
                {"name": "code", "type": "string", "required": True, "primary_key": True},
                {"name": "token", "type": "string", "required": True},
                {"name": "created_at", "type": "datetime", "required": True},
                {"name": "expires_at", "type": "datetime", "required": True},
                {"name": "used_at", "type": "datetime", "required": False},
            ],
        },
    )

    write_model(
        "TournamentRecord",
        {
            "model": "TournamentRecord",
            "kind": "persistence-write",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/models.py",
            "database": "cqrs_command",
            "table": "tournaments",
            "description": "Write-side tournament aggregate.",
            "fields": [
                {"name": "tournament_id", "type": "string", "required": True, "primary_key": True},
                {"name": "event_id", "type": "string", "required": False, "indexed": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True, "unique": True, "indexed": True},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
                {"name": "created_by", "type": "string", "required": True, "indexed": True},
                {"name": "updated_by", "type": "string", "required": False},
                {"name": "created_at", "type": "datetime", "required": True},
                {"name": "updated_at", "type": "datetime", "required": True},
            ],
        },
    )

    write_model(
        "MatchSummaryProjection",
        {
            "model": "MatchSummaryProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "match_summary_view",
            "description": "Materialized match summary; projected from MatchParsed.",
            "fields": [
                {"name": "match_id", "type": "string", "required": True, "primary_key": True},
                {"name": "tournament_id", "type": "string", "required": False, "indexed": True},
                {"name": "source_log_id", "type": "integer", "required": False, "indexed": True},
                {"name": "map_name", "type": "string", "required": True, "indexed": True},
                {"name": "duration_seconds", "type": "integer", "required": True},
                {"name": "winning_team", "type": "string", "required": True},
                {"name": "date_played", "type": "datetime", "required": True, "indexed": True},
                {"name": "blu_score", "type": "integer", "required": True, "default": 0},
                {"name": "red_score", "type": "integer", "required": True, "default": 0},
                {"name": "ratings_ready", "type": "boolean", "required": True, "default": False},
            ],
            "relationships": [{"view": "MatchSummaryView", "mapping": "1:1"}],
        },
    )

    write_model(
        "TournamentSummaryProjection",
        {
            "model": "TournamentSummaryProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "tournament_summary_view",
            "fields": [
                {"name": "tournament_id", "type": "string", "required": True, "primary_key": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True, "indexed": True},
                {"name": "match_count", "type": "integer", "required": True, "default": 0},
                {"name": "started_at", "type": "datetime", "required": False},
                {"name": "event_id", "type": "string", "required": False, "indexed": True},
            ],
        },
    )

    write_model(
        "PlayerMatchStatsProjection",
        {
            "model": "PlayerMatchStatsProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "player_match_stats_view",
            "fields": [
                {"name": "id", "type": "integer", "required": False, "primary_key": True},
                {"name": "steam_id", "type": "string", "required": True, "indexed": True},
                {"name": "match_id", "type": "string", "required": True, "indexed": True},
                {"name": "team", "type": "string", "required": True},
                {"name": "classes_played", "type": "json", "required": True},
                {"name": "primary_class", "type": "string", "required": True, "default": "unknown", "indexed": True},
                {"name": "playtime_seconds", "type": "integer", "required": True, "default": 0},
                {"name": "kills", "type": "integer", "required": True, "default": 0},
                {"name": "deaths", "type": "integer", "required": True, "default": 0},
                {"name": "assists", "type": "integer", "required": True, "default": 0},
                {"name": "damage_per_minute", "type": "float", "required": True, "default": 0.0},
                {"name": "healing_done", "type": "integer", "required": True, "default": 0},
                {"name": "damage_received", "type": "integer", "required": True, "default": 0},
                {"name": "heals_received", "type": "integer", "required": True, "default": 0},
                {"name": "ubers", "type": "integer", "required": True, "default": 0},
                {"name": "drops", "type": "integer", "required": True, "default": 0},
                {"name": "captures", "type": "integer", "required": True, "default": 0},
                {"name": "headshots", "type": "integer", "required": True, "default": 0},
                {"name": "backstabs", "type": "integer", "required": True, "default": 0},
                {"name": "airshots", "type": "integer", "required": True, "default": 0},
                {"name": "rating", "type": "float", "required": True, "default": 1.0},
            ],
        },
    )

    write_model(
        "PlayerMatchClassStatsProjection",
        {
            "model": "PlayerMatchClassStatsProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "player_match_class_stats_view",
            "constraints": ["unique(steam_id, match_id, class_id)"],
            "fields": [
                {"name": "id", "type": "integer", "required": False, "primary_key": True},
                {"name": "steam_id", "type": "string", "required": True, "indexed": True},
                {"name": "match_id", "type": "string", "required": True, "indexed": True},
                {"name": "tournament_id", "type": "string", "required": False, "indexed": True},
                {"name": "team", "type": "string", "required": True, "default": "unknown"},
                {"name": "class_name", "type": "string", "required": True, "indexed": True},
                {"name": "class_id", "type": "integer", "required": True, "indexed": True},
                {"name": "playtime_seconds", "type": "integer", "required": True, "default": 0},
                {"name": "kills", "type": "integer", "required": True, "default": 0},
                {"name": "deaths", "type": "integer", "required": True, "default": 0},
                {"name": "assists", "type": "integer", "required": True, "default": 0},
                {"name": "dpm", "type": "float", "required": True, "default": 0.0},
                {"name": "primary_accuracy", "type": "float", "required": True, "default": 0.0},
                {"name": "damage_dealt", "type": "integer", "required": True, "default": 0},
                {"name": "damage_received", "type": "integer", "required": True, "default": 0},
                {"name": "heals_received", "type": "integer", "required": True, "default": 0},
                {"name": "healing_done", "type": "integer", "required": True, "default": 0},
                {"name": "rating", "type": "float", "required": True, "default": 1.0},
            ],
        },
    )

    write_model(
        "PlayerLifetimeStatsProjection",
        {
            "model": "PlayerLifetimeStatsProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "player_lifetime_stats_view",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True, "primary_key": True},
                {"name": "matches_played", "type": "integer", "required": True, "default": 0},
                {"name": "total_kills", "type": "integer", "required": True, "default": 0},
                {"name": "total_deaths", "type": "integer", "required": True, "default": 0},
                {"name": "total_assists", "type": "integer", "required": True, "default": 0},
                {"name": "average_damage_per_minute", "type": "float", "required": True, "default": 0.0},
                {"name": "total_healing_done", "type": "integer", "required": True, "default": 0},
                {"name": "average_rating", "type": "float", "required": True, "default": 1.0},
            ],
        },
    )

    write_model(
        "PlayerClassStatsProjection",
        {
            "model": "PlayerClassStatsProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "player_class_stats_view",
            "fields": [
                {"name": "id", "type": "integer", "required": False, "primary_key": True},
                {"name": "steam_id", "type": "string", "required": True, "indexed": True},
                {"name": "class_name", "type": "string", "required": True, "indexed": True},
                {"name": "matches_played", "type": "integer", "required": True, "default": 0},
                {"name": "total_kills", "type": "integer", "required": True, "default": 0},
                {"name": "total_deaths", "type": "integer", "required": True, "default": 0},
                {"name": "total_assists", "type": "integer", "required": True, "default": 0},
                {"name": "average_damage_per_minute", "type": "float", "required": True, "default": 0.0},
                {"name": "total_healing_done", "type": "integer", "required": True, "default": 0},
                {"name": "average_rating", "type": "float", "required": True, "default": 1.0},
            ],
        },
    )

    write_model(
        "ClassRatingBenchmarkProjection",
        {
            "model": "ClassRatingBenchmarkProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "class_rating_benchmark_view",
            "fields": [
                {"name": "class_id", "type": "integer", "required": True, "primary_key": True},
                {"name": "class_name", "type": "string", "required": True, "indexed": True},
                {"name": "sample_size", "type": "integer", "required": True, "default": 0},
                {"name": "raw_p05", "type": "float", "required": True, "default": 0.0},
                {"name": "raw_p95", "type": "float", "required": True, "default": 1.0},
                {"name": "avg_rating", "type": "float", "required": True, "default": 1.0},
                {"name": "std_rating", "type": "float", "required": True, "default": 0.0},
                {"name": "min_rating", "type": "float", "required": True, "default": 0.0},
                {"name": "max_rating", "type": "float", "required": True, "default": 2.0},
                {"name": "p10_rating", "type": "float", "required": True, "default": 0.0},
                {"name": "p25_rating", "type": "float", "required": True, "default": 0.0},
                {"name": "p50_rating", "type": "float", "required": True, "default": 0.0},
                {"name": "p75_rating", "type": "float", "required": True, "default": 0.0},
                {"name": "p90_rating", "type": "float", "required": True, "default": 0.0},
                {"name": "metric_means", "type": "json", "required": True, "default": {}},
                {"name": "metric_stds", "type": "json", "required": True, "default": {}},
                {"name": "updated_at", "type": "datetime", "required": True},
            ],
        },
    )

    write_model(
        "PlayerIdentityProjection",
        {
            "model": "PlayerIdentityProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "player_identity_view",
            "fields": [
                {"name": "steam_id", "type": "string", "required": True, "primary_key": True},
                {"name": "steam_id64", "type": "string", "required": False, "indexed": True},
                {"name": "persona_name", "type": "string", "required": False},
                {"name": "custom_alias", "type": "string", "required": False},
                {"name": "avatar_url", "type": "string", "required": False},
                {"name": "resolved_at", "type": "datetime", "required": False},
                {"name": "resolve_failed", "type": "boolean", "required": True, "default": False},
            ],
        },
    )

    write_model(
        "LeaderboardSnapshotProjection",
        {
            "model": "LeaderboardSnapshotProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "leaderboard_snapshot_view",
            "constraints": ["unique(tournament_id, steam_id, class_name)"],
            "fields": [
                {"name": "id", "type": "integer", "required": False, "primary_key": True},
                {"name": "tournament_id", "type": "string", "required": True, "indexed": True},
                {"name": "steam_id", "type": "string", "required": True, "indexed": True},
                {"name": "class_name", "type": "string", "required": True, "default": "", "description": "Empty string = all-classes aggregate", "indexed": True},
                {"name": "matches_played", "type": "integer", "required": True, "default": 0},
                {"name": "total_kills", "type": "integer", "required": True, "default": 0},
                {"name": "total_deaths", "type": "integer", "required": True, "default": 0},
                {"name": "total_assists", "type": "integer", "required": True, "default": 0},
                {"name": "average_damage_per_minute", "type": "float", "required": True, "default": 0.0},
                {"name": "total_healing_done", "type": "integer", "required": True, "default": 0},
                {"name": "average_rating", "type": "float", "required": True, "default": 1.0},
                {"name": "primary_class", "type": "string", "required": True, "default": "unknown"},
                {"name": "updated_at", "type": "datetime", "required": True},
            ],
        },
    )

    write_model(
        "CreateEventCommand",
        {
            "model": "CreateEventCommand",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Create an event aggregate (season/container for tournaments).",
            "fields": [
                {"name": "name", "type": "string", "required": True, "constraints": ["min_length: 1", "max_length: 128"]},
                {"name": "slug", "type": "string", "required": True, "constraints": ["min_length: 1", "max_length: 128"]},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
            ],
        },
    )

    write_model(
        "UpdateEventCommand",
        {
            "model": "UpdateEventCommand",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Partial update of an event aggregate.",
            "fields": [
                {"name": "name", "type": "string", "required": False, "constraints": ["min_length: 1", "max_length: 128"]},
                {"name": "slug", "type": "string", "required": False, "constraints": ["min_length: 1", "max_length: 128"]},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
            ],
        },
    )

    write_model(
        "LinkTournamentToEventCommand",
        {
            "model": "LinkTournamentToEventCommand",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Link or unlink a tournament to an event. Null event_id unlinks.",
            "fields": [
                {"name": "event_id", "type": "uuid", "required": False},
            ],
        },
    )

    write_model(
        "AssignMatchTournamentCommand",
        {
            "model": "AssignMatchTournamentCommand",
            "kind": "command",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Reassign a match to a tournament.",
            "fields": [
                {"name": "tournament_id", "type": "uuid", "required": True},
            ],
        },
    )

    write_model(
        "EventCommandModel",
        {
            "model": "EventCommandModel",
            "kind": "domain",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Event aggregate payload used inside integration events.",
            "fields": [
                {"name": "event_id", "type": "uuid", "required": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
            ],
        },
    )

    write_model(
        "EventSummaryView",
        {
            "model": "EventSummaryView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Event catalog row.",
            "fields": [
                {"name": "event_id", "type": "uuid", "required": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
                {"name": "tournament_ids", "type": "array<uuid>", "required": False},
                {"name": "tournament_count", "type": "integer", "required": False, "default": 0},
                {"name": "match_count", "type": "integer", "required": False, "default": 0},
            ],
        },
    )

    write_model(
        "EventDetailView",
        {
            "model": "EventDetailView",
            "kind": "view",
            "version": "1.0",
            "source": "server/cqrs/shared/schemas.py",
            "description": "Event detail with nested tournament summaries.",
            "fields": [
                {"name": "event", "type": "EventSummaryView", "required": True},
                {"name": "tournaments", "type": "array<TournamentSummaryView>", "required": True},
            ],
        },
    )

    write_model(
        "EventMutationPayload",
        {
            "model": "EventMutationPayload",
            "kind": "event",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/services.py",
            "description": "Payload of EventCreated and EventUpdated events.",
            "fields": [
                {"name": "event_id", "type": "uuid", "required": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
            ],
        },
    )

    write_model(
        "TournamentLinkedToEventPayload",
        {
            "model": "TournamentLinkedToEventPayload",
            "kind": "event",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/services.py",
            "description": "Payload of TournamentLinkedToEvent. Null event_id means unlink.",
            "fields": [
                {"name": "tournament_id", "type": "uuid", "required": True},
                {"name": "event_id", "type": "uuid", "required": False},
            ],
        },
    )

    write_model(
        "MatchTournamentAssignedPayload",
        {
            "model": "MatchTournamentAssignedPayload",
            "kind": "event",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/services.py",
            "description": "Payload of MatchTournamentAssigned.",
            "fields": [
                {"name": "match_id", "type": "uuid", "required": True},
                {"name": "tournament_id", "type": "uuid", "required": True},
                {"name": "previous_tournament_id", "type": "uuid", "required": False},
            ],
        },
    )

    write_model(
        "EventRecord",
        {
            "model": "EventRecord",
            "kind": "persistence-write",
            "version": "1.0",
            "source": "server/cqrs/command_service/app/models.py",
            "database": "cqrs_command",
            "table": "events",
            "description": "Write-side event aggregate (season/container).",
            "fields": [
                {"name": "event_id", "type": "string", "required": True, "primary_key": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True, "unique": True, "indexed": True},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
                {"name": "created_by", "type": "string", "required": True, "indexed": True},
                {"name": "updated_by", "type": "string", "required": False},
                {"name": "created_at", "type": "datetime", "required": True},
                {"name": "updated_at", "type": "datetime", "required": True},
            ],
        },
    )

    write_model(
        "EventSummaryProjection",
        {
            "model": "EventSummaryProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "event_summary_view",
            "description": "Materialized event catalog; projected from EventCreated/Updated and tournament links.",
            "fields": [
                {"name": "event_id", "type": "string", "required": True, "primary_key": True},
                {"name": "name", "type": "string", "required": True},
                {"name": "slug", "type": "string", "required": True, "indexed": True},
                {"name": "tournaments", "type": "array<string>", "required": False},
                {"name": "started_at", "type": "datetime", "required": False},
                {"name": "start_date", "type": "datetime", "required": False},
                {"name": "end_date", "type": "datetime", "required": False},
            ],
        },
    )

    write_model(
        "EventPlayerStatsProjection",
        {
            "model": "EventPlayerStatsProjection",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "event_player_stats_view",
            "description": "Per-player aggregates across all tournaments in an event.",
            "fields": [
                {"name": "event_id", "type": "string", "required": True, "primary_key": True},
                {"name": "steam_id", "type": "string", "required": True, "primary_key": True, "indexed": True},
                {"name": "classes_played", "type": "array<string>", "required": False},
                {"name": "primary_class", "type": "string", "required": True, "default": "unknown"},
                {"name": "playtime_seconds", "type": "integer", "required": True, "default": 0},
                {"name": "kills", "type": "integer", "required": True, "default": 0},
                {"name": "deaths", "type": "integer", "required": True, "default": 0},
                {"name": "assists", "type": "integer", "required": True, "default": 0},
                {"name": "damage_per_minute", "type": "float", "required": True, "default": 0.0},
                {"name": "healing_done", "type": "integer", "required": True, "default": 0},
                {"name": "rating", "type": "float", "required": True, "default": 1.0},
            ],
        },
    )

    write_model(
        "ProcessedEvent",
        {
            "model": "ProcessedEvent",
            "kind": "persistence-read",
            "version": "1.0",
            "source": "server/cqrs/query_service/app/models.py",
            "database": "cqrs_query",
            "table": "processed_events",
            "description": "Idempotency ledger for integration events applied to read models.",
            "fields": [
                {"name": "event_id", "type": "uuid", "required": True, "primary_key": True},
                {"name": "event_type", "type": "string", "required": True, "indexed": True},
                {"name": "processed_at", "type": "datetime", "required": True},
            ],
        },
    )

    count = len(list(ROOT.glob("*.yaml")))
    print(f"Generated {count} CDM model files in {ROOT}")


if __name__ == "__main__":
    main()
