"""Projection handlers that materialize read models from integration events."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from ...shared.schemas import (
    ClassRatingBenchmarkView,
    ClassStatSnapshot,
    ClassStatView,
    EventDetailView,
    EventSummaryView,
    LeaderboardEntryView,
    MatchSummaryView,
    PlayerClassAggregateView,
    PlayerLifetimeStatsView,
    PlayerRecentMatchView,
    PlayerStatsView,
    SearchResultView,
    TournamentSummaryView,
)
from ...shared.steam import SteamWebApiClient, canonical_steam_id, to_steam_id64
from ...shared.tf2_classes import (
    class_id_from_name,
    class_name_from_id,
    normalize_class_name,
    primary_class,
)
from ...shared.timeutils import parse_utc_naive, utcnow
from ...shared.tournaments import (
    TOURNAMENT_CATALOG,
    VISIBLE_TOURNAMENT_SLUGS,
)
from .models import (
    ClassRatingBenchmarkProjection,
    EventPlayerStatsProjection,
    EventSummaryProjection,
    LeaderboardSnapshotProjection,
    MatchSummaryProjection,
    PlayerClassStatsProjection,
    PlayerIdentityProjection,
    PlayerLifetimeStatsProjection,
    PlayerMatchClassStatsProjection,
    PlayerMatchStatsProjection,
    TournamentSummaryProjection,
)
from .rating import (
    RatingService,
    rating_row_from_mapping,
)


class ProjectionDependencyMissing(RuntimeError):
    """An event refers to read-model state that has not been projected yet."""


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _parse_datetime(value: Any) -> datetime:
    from ...shared.timeutils import parse_utc_naive

    return parse_utc_naive(value)


def _class_snapshots_from_player(
    player: dict[str, Any],
    match_duration_seconds: int,
) -> list[ClassStatSnapshot]:
    """Synthesize ClassStatSnapshot rows when nested class_stats are missing."""
    raw_stats = player.get("class_stats") or []
    if raw_stats:
        snapshots: list[ClassStatSnapshot] = []
        for item in raw_stats:
            if isinstance(item, ClassStatSnapshot):
                snapshots.append(item)
                continue
            class_name = normalize_class_name(
                str(item.get("class_name") or item.get("type") or "unknown")
            )
            class_id = int(
                item.get("class_id")
                if item.get("class_id") is not None
                else class_id_from_name(class_name)
            )
            snapshots.append(
                ClassStatSnapshot(
                    class_name=class_name,
                    class_id=class_id,
                    playtime_seconds=int(item.get("playtime_seconds") or 0),
                    kills=int(item.get("kills") or 0),
                    deaths=int(item.get("deaths") or 0),
                    assists=int(item.get("assists") or 0),
                    dpm=float(item.get("dpm") or item.get("damage_per_minute") or 0.0),
                    primary_accuracy=float(item.get("primary_accuracy") or 0.0),
                    damage_dealt=int(item.get("damage_dealt") or 0),
                    damage_received=int(item.get("damage_received") or 0),
                    heals_received=int(item.get("heals_received") or 0),
                    healing_done=int(item.get("healing_done") or 0),
                )
            )
        return snapshots

    classes_played = list(player.get("classes_played") or [])
    class_name = normalize_class_name(
        player.get("primary_class") or primary_class(classes_played)
    )
    playtime = int(player.get("playtime_seconds") or 0) or match_duration_seconds
    damage_dealt = 0
    dpm = float(player.get("damage_per_minute") or 0.0)
    if playtime > 0 and dpm > 0:
        damage_dealt = round(dpm * (playtime / 60.0))
    is_medic = class_name == "medic"
    return [
        ClassStatSnapshot(
            class_name=class_name,
            class_id=class_id_from_name(class_name),
            playtime_seconds=playtime,
            kills=int(player.get("kills") or 0),
            deaths=int(player.get("deaths") or 0),
            assists=int(player.get("assists") or 0),
            dpm=dpm,
            primary_accuracy=0.0,
            damage_dealt=damage_dealt,
            damage_received=int(player.get("damage_received") or 0),
            heals_received=int(player.get("heals_received") or 0),
            healing_done=int(player.get("healing_done") or 0) if is_medic else 0,
        )
    ]


def _playtime_weighted_rating(rows: list[PlayerMatchClassStatsProjection]) -> float:
    if not rows:
        return 1.0
    total_playtime = sum(max(int(row.playtime_seconds or 0), 0) for row in rows)
    if total_playtime <= 0:
        return round(sum(float(row.rating) for row in rows) / len(rows), 3)
    weighted = sum(
        float(row.rating) * max(int(row.playtime_seconds or 0), 0) for row in rows
    )
    return round(weighted / total_playtime, 3)


class ProjectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _player_id_candidates(raw: str) -> list[str]:
        trimmed = str(raw or "").strip()
        if not trimmed:
            return []
        canonical = canonical_steam_id(trimmed)
        candidates: list[str] = []
        for candidate in (canonical, trimmed):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    async def _resolve_lifetime_stats_row(
        self,
        raw: str,
    ) -> tuple[str, PlayerLifetimeStatsProjection | None]:
        for candidate in self._player_id_candidates(raw):
            row = await self.session.get(PlayerLifetimeStatsProjection, candidate)
            if row is not None:
                return row.steam_id, row
        candidates = self._player_id_candidates(raw)
        return (candidates[0] if candidates else str(raw or "").strip()), None

    async def handle_event(self, event_type: str, envelope: dict[str, Any]) -> None:
        """Project an event into the read model (caller owns the transaction)."""
        payload = envelope.get("payload", envelope)
        if event_type == "MatchParsed":
            await self._project_match_parsed(payload)
            # Ratings, leaderboards, event stats and Steam identities are refreshed
            # by one coalesced rebuild (see rating_rebuild.py), not per event.
            await self.request_rating_rebuild()
        elif event_type in {"RatingsRebuildRequested", "RatingsRebuilt"}:
            # Legacy internal events, kept for in-flight messages only.
            await self.request_rating_rebuild()
        elif event_type == "LogEventCreated":
            # Audit hook — match/player materialization is driven by MatchParsed.
            return
        elif event_type == "PlayerAliasUpdated":
            await self._project_player_alias_updated(payload)
        elif event_type in {"TournamentCreated", "TournamentUpdated"}:
            await self._upsert_tournament(payload, force_visible=True)
        elif event_type in {"EventCreated", "EventUpdated"}:
            await self._upsert_event(payload)
        elif event_type == "TournamentLinkedToEvent":
            await self._apply_tournament_event_link(
                str(payload.get("tournament_id") or ""),
                str(payload["event_id"]) if payload.get("event_id") else None,
            )
        elif event_type == "MatchTournamentAssigned":
            await self._project_match_tournament_assigned(payload)

    async def request_rating_rebuild(self) -> None:
        """Mark ratings stale; the rebuild worker coalesces pending requests."""
        now = utcnow()
        await self.session.execute(
            text(
                """
                INSERT INTO rating_rebuild_state
                    (id, request_seq, completed_seq, pending_since, last_requested_at)
                VALUES (1, 1, 0, :now, :now)
                ON CONFLICT (id) DO UPDATE SET
                    pending_since = CASE
                        WHEN rating_rebuild_state.request_seq
                             <= rating_rebuild_state.completed_seq
                        THEN EXCLUDED.pending_since
                        ELSE COALESCE(
                            rating_rebuild_state.pending_since, EXCLUDED.pending_since
                        )
                    END,
                    request_seq = rating_rebuild_state.request_seq + 1,
                    last_requested_at = EXCLUDED.last_requested_at
                """
            ),
            {"now": now},
        )

    async def pending_rating_match_ids(self, *, limit: int | None = None) -> list[str]:
        stmt = select(MatchSummaryProjection.match_id).where(
            col(MatchSummaryProjection.ratings_ready).is_(False)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return [str(mid) for mid in (await self.session.execute(stmt)).scalars().all()]

    async def mark_ratings_ready(self, match_ids: list[str]) -> None:
        """Flag the given match summaries as rating-complete after a rebuild."""
        ids = list(dict.fromkeys(match_ids))
        for start in range(0, len(ids), 1000):
            await self.session.execute(
                update(MatchSummaryProjection)
                .where(col(MatchSummaryProjection.match_id).in_(ids[start : start + 1000]))
                .values(ratings_ready=True)
            )
        await self.session.flush()

    async def refresh_all_event_player_stats(self) -> None:
        event_ids = (
            (await self.session.execute(select(EventSummaryProjection.event_id)))
            .scalars()
            .all()
        )
        for event_id in event_ids:
            await self._rebuild_event_player_stats(str(event_id))

    async def _upsert_player_identity_bootstrap(
        self,
        steam_id: str,
        display_name: str | None,
    ) -> None:
        canonical = canonical_steam_id(steam_id)
        steam_id64 = to_steam_id64(canonical) or (
            canonical if canonical.isdigit() and len(canonical) == 17 else None
        )
        identity = await self.session.get(PlayerIdentityProjection, canonical)
        if identity is None:
            self.session.add(
                PlayerIdentityProjection(
                    steam_id=canonical,
                    steam_id64=steam_id64,
                    persona_name=display_name,
                    resolved_at=utcnow() if display_name else None,
                    resolve_failed=False,
                )
            )
            await self.session.flush()
            return
        if steam_id64 and not identity.steam_id64:
            identity.steam_id64 = steam_id64
        if display_name and not identity.persona_name:
            identity.persona_name = display_name
            identity.resolved_at = utcnow()
            identity.resolve_failed = False
        await self.session.flush()

    async def resolve_missing_player_identities(
        self,
        *,
        steam_client: SteamWebApiClient | None = None,
        max_age_days: int = 7,
    ) -> None:
        """Resolve persona names via Steam Web API for missing/stale identities."""
        client = steam_client or SteamWebApiClient()
        if not client.enabled:
            return

        identities = (
            (await self.session.execute(select(PlayerIdentityProjection)))
            .scalars()
            .all()
        )
        by_steam = {row.steam_id: row for row in identities}

        lifetime_ids = (
            (await self.session.execute(select(PlayerLifetimeStatsProjection.steam_id)))
            .scalars()
            .all()
        )
        match_ids = (
            (
                await self.session.execute(
                    select(PlayerMatchStatsProjection.steam_id).distinct()
                )
            )
            .scalars()
            .all()
        )
        all_steam_ids = {str(sid) for sid in list(lifetime_ids) + list(match_ids)}

        now = utcnow()
        to_resolve: list[str] = []
        for steam_id in all_steam_ids:
            identity = by_steam.get(steam_id)
            if identity is None:
                self.session.add(
                    PlayerIdentityProjection(
                        steam_id=steam_id,
                        steam_id64=to_steam_id64(steam_id),
                    )
                )
                to_resolve.append(steam_id)
                continue
            stale = identity.resolved_at is None
            if identity.resolved_at is not None:
                age = (now - identity.resolved_at).total_seconds()
                stale = age > max_age_days * 86400
            if not identity.persona_name or stale or identity.resolve_failed:
                to_resolve.append(steam_id)

        await self.session.flush()
        if not to_resolve:
            return

        summaries = await client.get_player_summaries(to_resolve)
        steam64_to_original = {(to_steam_id64(sid) or sid): sid for sid in to_resolve}
        for steam64, summary in summaries.items():
            original = steam64_to_original.get(steam64)
            if not original:
                continue
            identity = await self.session.get(PlayerIdentityProjection, original)
            if identity is None:
                continue
            identity.steam_id64 = steam64
            identity.persona_name = (
                str(summary.get("personaname") or "").strip() or identity.persona_name
            )
            identity.avatar_url = (
                str(summary.get("avatar") or "") or identity.avatar_url
            )
            identity.resolved_at = now
            # custom_alias (admin override) counts as a resolved display name.
            identity.resolve_failed = not bool(
                identity.custom_alias or identity.persona_name
            )

        resolved_64 = set(summaries.keys())
        for steam_id in to_resolve:
            sid64 = to_steam_id64(steam_id) or steam_id
            if sid64 in resolved_64:
                continue
            identity = await self.session.get(PlayerIdentityProjection, steam_id)
            if identity is None:
                continue
            if not identity.persona_name and not identity.custom_alias:
                identity.resolve_failed = True
                identity.resolved_at = now

        await self.session.flush()

    async def _display_names(self, steam_ids: list[str]) -> dict[str, str | None]:
        if not steam_ids:
            return {}
        rows = (
            (
                await self.session.execute(
                    select(PlayerIdentityProjection).where(
                        col(PlayerIdentityProjection.steam_id).in_(list(set(steam_ids)))
                    )
                )
            )
            .scalars()
            .all()
        )
        return {row.steam_id: (row.custom_alias or row.persona_name) for row in rows}

    async def _project_player_alias_updated(self, payload: dict[str, Any]) -> None:
        steam_id = canonical_steam_id(str(payload.get("steam_id") or "").strip())
        display_name = str(payload.get("display_name") or "").strip()
        if not steam_id or not display_name:
            return
        await self._upsert_player_identity_bootstrap(steam_id, display_name)
        identity = await self.session.get(PlayerIdentityProjection, steam_id)
        if identity is None:
            return
        identity.custom_alias = display_name
        identity.resolved_at = utcnow()
        identity.resolve_failed = False
        await self.session.flush()

    async def _project_match_parsed(self, payload: dict[str, Any]) -> None:
        match_id = str(payload["match_id"])
        blu_score = int(payload.get("blu_score", 0))
        red_score = int(payload.get("red_score", 0))
        winning_team = "blu" if blu_score >= red_score else "red"
        date_played = _parse_datetime(payload.get("date_played"))
        tournament = payload.get("tournament") or {}
        tournament_id = (
            str(tournament["tournament_id"])
            if tournament.get("tournament_id")
            else None
        )
        source_log_id = payload.get("source_log_id")
        duration_seconds = int(payload.get("duration_seconds", 1800))

        existing = await self.session.get(MatchSummaryProjection, match_id)
        if existing is None:
            self.session.add(
                MatchSummaryProjection(
                    match_id=match_id,
                    tournament_id=tournament_id,
                    source_log_id=int(source_log_id)
                    if source_log_id is not None
                    else None,
                    map_name=payload.get("map_name", "unknown_map"),
                    duration_seconds=duration_seconds,
                    winning_team=winning_team,
                    date_played=date_played,
                    blu_score=blu_score,
                    red_score=red_score,
                    ratings_ready=False,
                )
            )
        else:
            existing.tournament_id = tournament_id or existing.tournament_id
            if source_log_id is not None:
                existing.source_log_id = int(source_log_id)
            existing.map_name = payload.get("map_name", existing.map_name)
            existing.duration_seconds = duration_seconds
            existing.winning_team = winning_team
            existing.date_played = date_played
            existing.blu_score = blu_score
            existing.red_score = red_score
            existing.ratings_ready = False

        await self.session.flush()

        if tournament:
            await self._upsert_tournament(tournament)

        for player in payload.get("players") or []:
            await self._upsert_player_stats(
                match_id,
                player,
                duration_seconds,
                tournament_id=tournament_id,
            )

    async def _upsert_tournament(
        self,
        tournament: dict[str, Any],
        *,
        force_visible: bool = False,
    ) -> None:
        tournament_id = str(tournament.get("tournament_id") or "default-tournament")
        slug = str(tournament.get("slug") or "")
        if not force_visible and slug and slug not in VISIBLE_TOURNAMENT_SLUGS:
            # Allow updates for tournaments already materialized (admin-created).
            existing_any = await self.session.get(
                TournamentSummaryProjection, tournament_id
            )
            if existing_any is None:
                return

        existing = await self.session.get(TournamentSummaryProjection, tournament_id)
        match_count = (
            await self.session.execute(
                select(func.count())
                .select_from(MatchSummaryProjection)
                .where(MatchSummaryProjection.tournament_id == tournament_id)
            )
        ).scalar_one()

        started_at = (
            _parse_datetime(tournament["start_date"])
            if tournament.get("start_date")
            else None
        )
        if existing is None:
            event_id = (
                str(tournament["event_id"]) if tournament.get("event_id") else None
            )
            self.session.add(
                TournamentSummaryProjection(
                    tournament_id=tournament_id,
                    name=tournament.get("name", "default-tournament"),
                    slug=slug or "default-tournament",
                    match_count=match_count,
                    started_at=started_at,
                    event_id=event_id,
                )
            )
            return

        existing.name = tournament.get("name", existing.name)
        existing.slug = slug or existing.slug
        existing.match_count = match_count
        if started_at and existing.started_at is None:
            existing.started_at = started_at
        if tournament.get("event_id"):
            existing.event_id = str(tournament["event_id"])
        elif "event_id" in tournament and tournament["event_id"] is None:
            existing.event_id = None

    async def _upsert_event(self, payload: dict[str, Any]) -> None:
        event_id = str(payload.get("event_id") or "")
        if not event_id:
            return
        start_date = (
            _parse_datetime(payload["start_date"]) if payload.get("start_date") else None
        )
        end_date = (
            _parse_datetime(payload["end_date"]) if payload.get("end_date") else None
        )
        existing = await self.session.get(EventSummaryProjection, event_id)
        if existing is None:
            self.session.add(
                EventSummaryProjection(
                    event_id=event_id,
                    name=str(payload.get("name") or "Untitled event"),
                    slug=str(payload.get("slug") or event_id),
                    tournaments=[],
                    started_at=start_date,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            await self.session.flush()
            return
        if payload.get("name"):
            existing.name = str(payload["name"])
        if payload.get("slug"):
            existing.slug = str(payload["slug"])
        if "start_date" in payload:
            existing.start_date = start_date
            existing.started_at = start_date
        if "end_date" in payload:
            existing.end_date = end_date
        await self.session.flush()

    async def _apply_tournament_event_link(
        self,
        tournament_id: str,
        event_id: str | None,
    ) -> None:
        if not tournament_id:
            return
        tournament = await self.session.get(TournamentSummaryProjection, tournament_id)
        old_event_id = tournament.event_id if tournament is not None else None
        if tournament is not None:
            tournament.event_id = event_id

        affected = {eid for eid in (old_event_id, event_id) if eid}
        if old_event_id and old_event_id != event_id:
            await self._remove_tournament_from_event(old_event_id, tournament_id)
        if event_id:
            await self._add_tournament_to_event(event_id, tournament_id)
        for affected_id in affected:
            await self._rebuild_event_player_stats(affected_id)
        await self.session.flush()

    async def _add_tournament_to_event(self, event_id: str, tournament_id: str) -> None:
        event = await self.session.get(EventSummaryProjection, event_id)
        if event is None:
            return
        current = [str(tid) for tid in (event.tournaments or [])]
        if tournament_id not in current:
            event.tournaments = [*current, tournament_id]

    async def _remove_tournament_from_event(
        self, event_id: str, tournament_id: str
    ) -> None:
        event = await self.session.get(EventSummaryProjection, event_id)
        if event is None:
            return
        event.tournaments = [
            str(tid) for tid in (event.tournaments or []) if str(tid) != tournament_id
        ]

    async def _refresh_event_for_tournament(self, tournament_id: str | None) -> None:
        if not tournament_id:
            return
        tournament = await self.session.get(TournamentSummaryProjection, tournament_id)
        event_id = tournament.event_id if tournament is not None else None
        if event_id:
            await self._rebuild_event_player_stats(event_id)

    async def _recount_tournament(self, tournament_id: str) -> None:
        if not tournament_id:
            return
        row = await self.session.get(TournamentSummaryProjection, tournament_id)
        if row is None:
            return
        match_count = (
            await self.session.execute(
                select(func.count())
                .select_from(MatchSummaryProjection)
                .where(MatchSummaryProjection.tournament_id == tournament_id)
            )
        ).scalar_one()
        row.match_count = int(match_count or 0)

    async def _rebuild_event_player_stats(self, event_id: str) -> None:
        event = await self.session.get(EventSummaryProjection, event_id)
        if event is None:
            return
        tournament_ids = [str(tid) for tid in (event.tournaments or []) if tid]
        existing_rows = (
            (
                await self.session.execute(
                    select(EventPlayerStatsProjection).where(
                        EventPlayerStatsProjection.event_id == event_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in existing_rows:
            await self.session.delete(row)
        await self.session.flush()

        if not tournament_ids:
            return

        player_rows = (
            (
                await self.session.execute(
                    select(PlayerMatchStatsProjection)
                    .join(
                        MatchSummaryProjection,
                        MatchSummaryProjection.match_id
                        == PlayerMatchStatsProjection.match_id,
                    )
                    .where(
                        col(MatchSummaryProjection.tournament_id).in_(tournament_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        by_player: dict[str, list[PlayerMatchStatsProjection]] = defaultdict(list)
        for row in player_rows:
            by_player[row.steam_id].append(row)

        for steam_id, rows in by_player.items():
            matches_played = len(rows)
            class_counts: dict[str, int] = defaultdict(int)
            classes: list[str] = []
            for row in rows:
                for class_name in row.classes_played or []:
                    if class_name not in classes:
                        classes.append(class_name)
                class_counts[row.primary_class] += 1
            primary = (
                max(class_counts.items(), key=lambda item: item[1])[0]
                if class_counts
                else "unknown"
            )
            playtime = sum(int(row.playtime_seconds or 0) for row in rows)
            self.session.add(
                EventPlayerStatsProjection(
                    event_id=event_id,
                    steam_id=steam_id,
                    classes_played=classes,
                    primary_class=primary,
                    playtime_seconds=playtime,
                    kills=sum(int(row.kills or 0) for row in rows),
                    deaths=sum(int(row.deaths or 0) for row in rows),
                    assists=sum(int(row.assists or 0) for row in rows),
                    damage_per_minute=round(
                        sum(float(row.damage_per_minute or 0) for row in rows)
                        / matches_played,
                        2,
                    )
                    if matches_played
                    else 0.0,
                    healing_done=sum(int(row.healing_done or 0) for row in rows),
                    damage_received=sum(
                        int(row.damage_received or 0) for row in rows
                    ),
                    heals_received=sum(int(row.heals_received or 0) for row in rows),
                    ubers=sum(int(row.ubers or 0) for row in rows),
                    drops=sum(int(row.drops or 0) for row in rows),
                    captures=sum(int(row.captures or 0) for row in rows),
                    headshots=sum(int(row.headshots or 0) for row in rows),
                    backstabs=sum(int(row.backstabs or 0) for row in rows),
                    airshots=sum(int(row.airshots or 0) for row in rows),
                    rating=round(
                        sum(float(row.rating or 1.0) for row in rows) / matches_played,
                        3,
                    )
                    if matches_played
                    else 1.0,
                )
            )
        await self.session.flush()

    async def _project_match_tournament_assigned(self, payload: dict[str, Any]) -> None:
        match_id = str(payload.get("match_id") or "")
        new_tournament_id = str(payload.get("tournament_id") or "")
        if not match_id or not new_tournament_id:
            return
        match = await self.session.get(MatchSummaryProjection, match_id)
        if match is None:
            # The command side only assigns matches it has ingested, so a missing
            # projection means its MatchParsed has not been applied (or was parked).
            # Fail so the broker retries and then parks this event, rather than
            # acking it and silently losing the assignment.
            raise ProjectionDependencyMissing(
                f"MatchTournamentAssigned for unknown match_id={match_id}"
            )
        old_tournament_id = match.tournament_id
        payload_previous = payload.get("previous_tournament_id")
        if payload_previous and not old_tournament_id:
            old_tournament_id = str(payload_previous)
        match.tournament_id = new_tournament_id

        class_rows = (
            (
                await self.session.execute(
                    select(PlayerMatchClassStatsProjection).where(
                        PlayerMatchClassStatsProjection.match_id == match_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in class_rows:
            row.tournament_id = new_tournament_id

        await self.session.flush()
        for tournament_id in {old_tournament_id, new_tournament_id}:
            if tournament_id:
                await self._recount_tournament(str(tournament_id))
                await self.refresh_tournament_leaderboard(str(tournament_id))
                await self._refresh_event_for_tournament(str(tournament_id))

    async def _upsert_player_stats(
        self,
        match_id: str,
        player: dict[str, Any],
        match_duration_seconds: int,
        *,
        tournament_id: str | None,
    ) -> None:
        steam_id = canonical_steam_id(str(player["steam_id"]))
        class_snapshots = _class_snapshots_from_player(player, match_duration_seconds)
        classes_played = [snap.class_name for snap in class_snapshots] or list(
            player.get("classes_played") or []
        )
        if class_snapshots:
            primary = max(
                class_snapshots, key=lambda snap: snap.playtime_seconds
            ).class_name
        else:
            primary = normalize_class_name(
                player.get("primary_class") or primary_class(classes_played)
            )

        playtime = int(player.get("playtime_seconds") or 0)
        if playtime <= 0:
            playtime = (
                sum(snap.playtime_seconds for snap in class_snapshots)
                or match_duration_seconds
            )

        kills = int(player.get("kills", 0))
        deaths = int(player.get("deaths", 0))
        assists = int(player.get("assists", 0))
        dpm = float(player.get("damage_per_minute", 0.0))
        healing = int(player.get("healing_done", 0))
        damage_received = int(player.get("damage_received", 0))
        heals_received = int(player.get("heals_received", 0))
        ubers = int(player.get("ubers", 0))
        drops = int(player.get("drops", 0))
        captures = int(player.get("captures", 0))
        headshots = int(player.get("headshots", 0))
        backstabs = int(player.get("backstabs", 0))
        airshots = int(player.get("airshots", 0))
        team = str(player.get("team", "unknown"))

        statement = select(PlayerMatchStatsProjection).where(
            PlayerMatchStatsProjection.steam_id == steam_id,
            PlayerMatchStatsProjection.match_id == match_id,
        )
        existing = (await self.session.execute(statement)).scalars().first()
        if existing is None:
            self.session.add(
                PlayerMatchStatsProjection(
                    steam_id=steam_id,
                    match_id=match_id,
                    team=team,
                    classes_played=classes_played,
                    primary_class=primary,
                    playtime_seconds=playtime,
                    kills=kills,
                    deaths=deaths,
                    assists=assists,
                    damage_per_minute=dpm,
                    healing_done=healing,
                    damage_received=damage_received,
                    heals_received=heals_received,
                    ubers=ubers,
                    drops=drops,
                    captures=captures,
                    headshots=headshots,
                    backstabs=backstabs,
                    airshots=airshots,
                    rating=1.0,
                )
            )
        else:
            existing.team = team
            existing.classes_played = classes_played
            existing.primary_class = primary
            existing.playtime_seconds = playtime
            existing.kills = kills
            existing.deaths = deaths
            existing.assists = assists
            existing.damage_per_minute = dpm
            existing.healing_done = healing
            existing.damage_received = damage_received
            existing.heals_received = heals_received
            existing.ubers = ubers
            existing.drops = drops
            existing.captures = captures
            existing.headshots = headshots
            existing.backstabs = backstabs
            existing.airshots = airshots

        await self.session.flush()
        await self._upsert_player_identity_bootstrap(
            steam_id=steam_id,
            display_name=(
                str(player["display_name"]).strip()
                if player.get("display_name")
                else None
            ),
        )
        await self._replace_class_rows(
            steam_id=steam_id,
            match_id=match_id,
            tournament_id=tournament_id,
            team=team,
            class_snapshots=class_snapshots,
            match_duration_seconds=match_duration_seconds,
        )
        await self._recompute_lifetime(steam_id)
        await self._recompute_class_stats(steam_id)

    async def _replace_class_rows(
        self,
        *,
        steam_id: str,
        match_id: str,
        tournament_id: str | None,
        team: str,
        class_snapshots: list[ClassStatSnapshot],
        match_duration_seconds: int,
    ) -> None:
        existing_rows = (
            (
                await self.session.execute(
                    select(PlayerMatchClassStatsProjection).where(
                        PlayerMatchClassStatsProjection.steam_id == steam_id,
                        PlayerMatchClassStatsProjection.match_id == match_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in existing_rows:
            await self.session.delete(row)
        await self.session.flush()

        for snap in class_snapshots:
            playtime = int(snap.playtime_seconds or 0) or match_duration_seconds
            class_name = normalize_class_name(snap.class_name)
            class_id = (
                int(snap.class_id)
                if snap.class_id is not None
                else class_id_from_name(class_name)
            )
            self.session.add(
                PlayerMatchClassStatsProjection(
                    steam_id=steam_id,
                    match_id=match_id,
                    tournament_id=tournament_id,
                    team=team,
                    class_name=class_name,
                    class_id=class_id,
                    playtime_seconds=playtime,
                    kills=int(snap.kills or 0),
                    deaths=int(snap.deaths or 0),
                    assists=int(snap.assists or 0),
                    dpm=float(snap.dpm or 0.0),
                    primary_accuracy=float(snap.primary_accuracy or 0.0),
                    damage_dealt=int(snap.damage_dealt or 0),
                    damage_received=int(snap.damage_received or 0),
                    heals_received=int(snap.heals_received or 0),
                    healing_done=int(snap.healing_done or 0),
                    rating=1.0,
                )
            )
        await self.session.flush()

    async def rebuild_ratings(self) -> None:
        """Recompute class benchmarks and apply ratings to all class/match/player rows."""
        class_rows = (
            (await self.session.execute(select(PlayerMatchClassStatsProjection)))
            .scalars()
            .all()
        )
        match_player_rows = (
            (await self.session.execute(select(PlayerMatchStatsProjection)))
            .scalars()
            .all()
        )
        player_by_key = {(row.steam_id, row.match_id): row for row in match_player_rows}

        by_match_player: dict[
            tuple[str, str], list[PlayerMatchClassStatsProjection]
        ] = defaultdict(list)
        for row in class_rows:
            by_match_player[(row.steam_id, row.match_id)].append(row)

        def _rating_captures(row: PlayerMatchClassStatsProjection) -> int:
            group = by_match_player.get((row.steam_id, row.match_id), [])
            if not group:
                return 0
            primary = max(group, key=lambda item: int(item.playtime_seconds or 0))
            if int(row.class_id) != int(primary.class_id):
                return 0
            player = player_by_key.get((row.steam_id, row.match_id))
            if player is None:
                return 0
            return int(getattr(player, "captures", 0) or 0)

        def _rating_medic_ubers(row: PlayerMatchClassStatsProjection) -> int:
            if normalize_class_name(row.class_name) != "medic":
                return 0
            player = player_by_key.get((row.steam_id, row.match_id))
            if player is None:
                return 0
            return int(getattr(player, "ubers", 0) or 0)

        def _rating_medic_drops(row: PlayerMatchClassStatsProjection) -> int:
            if normalize_class_name(row.class_name) != "medic":
                return 0
            player = player_by_key.get((row.steam_id, row.match_id))
            if player is None:
                return 0
            return int(getattr(player, "drops", 0) or 0)

        rating_inputs = [
            rating_row_from_mapping(
                {
                    "class_id": row.class_id,
                    "class_name": row.class_name,
                    "playtime_seconds": row.playtime_seconds,
                    "kills": row.kills,
                    "deaths": row.deaths,
                    "dpm": row.dpm,
                    "primary_accuracy": row.primary_accuracy,
                    "damage_dealt": row.damage_dealt,
                    "damage_received": row.damage_received,
                    "heals_received": row.heals_received,
                    "captures": _rating_captures(row),
                    "healing_done": row.healing_done,
                    "ubers": _rating_medic_ubers(row),
                    "drops": _rating_medic_drops(row),
                    "steam_id": row.steam_id,
                    "match_id": row.match_id,
                }
            )
            for row in class_rows
        ]
        benchmarks = RatingService.build_class_benchmarks(rating_inputs)

        existing_benchmarks = (
            (await self.session.execute(select(ClassRatingBenchmarkProjection)))
            .scalars()
            .all()
        )
        for row in existing_benchmarks:
            if int(row.class_id) not in benchmarks:
                await self.session.delete(row)

        for class_id, payload in benchmarks.items():
            existing = await self.session.get(
                ClassRatingBenchmarkProjection, int(class_id)
            )
            if existing is None:
                self.session.add(
                    ClassRatingBenchmarkProjection(
                        class_id=int(class_id),
                        class_name=payload.get("class_name")
                        or class_name_from_id(int(class_id)),
                        sample_size=int(payload["sample_size"]),
                        raw_p05=float(payload["raw_p05"]),
                        raw_p95=float(payload["raw_p95"]),
                        avg_rating=float(payload["avg_rating"]),
                        std_rating=float(payload["std_rating"]),
                        min_rating=float(payload["min_rating"]),
                        max_rating=float(payload["max_rating"]),
                        p10_rating=float(payload["p10_rating"]),
                        p25_rating=float(payload["p25_rating"]),
                        p50_rating=float(payload["p50_rating"]),
                        p75_rating=float(payload["p75_rating"]),
                        p90_rating=float(payload["p90_rating"]),
                        metric_means=dict(payload.get("metric_means") or {}),
                        metric_stds=dict(payload.get("metric_stds") or {}),
                        updated_at=parse_utc_naive(payload["updated_at"])
                        if payload.get("updated_at")
                        else utcnow(),
                    )
                )
            else:
                existing.class_name = payload.get("class_name") or existing.class_name
                existing.sample_size = int(payload["sample_size"])
                existing.raw_p05 = float(payload["raw_p05"])
                existing.raw_p95 = float(payload["raw_p95"])
                existing.avg_rating = float(payload["avg_rating"])
                existing.std_rating = float(payload["std_rating"])
                existing.min_rating = float(payload["min_rating"])
                existing.max_rating = float(payload["max_rating"])
                existing.p10_rating = float(payload["p10_rating"])
                existing.p25_rating = float(payload["p25_rating"])
                existing.p50_rating = float(payload["p50_rating"])
                existing.p75_rating = float(payload["p75_rating"])
                existing.p90_rating = float(payload["p90_rating"])
                existing.metric_means = dict(payload.get("metric_means") or {})
                existing.metric_stds = dict(payload.get("metric_stds") or {})
                existing.updated_at = (
                    parse_utc_naive(payload["updated_at"])
                    if payload.get("updated_at")
                    else utcnow()
                )

        await self.session.flush()

        for row, rating_input in zip(class_rows, rating_inputs):
            row.rating = RatingService.score_row(
                rating_input,
                benchmarks.get(int(row.class_id)),
            )

        await self.session.flush()

        by_match_player: dict[
            tuple[str, str], list[PlayerMatchClassStatsProjection]
        ] = defaultdict(list)
        for row in class_rows:
            by_match_player[(row.steam_id, row.match_id)].append(row)

        match_rows = (
            (await self.session.execute(select(PlayerMatchStatsProjection)))
            .scalars()
            .all()
        )
        for match_row in match_rows:
            class_group = by_match_player.get(
                (match_row.steam_id, match_row.match_id), []
            )
            match_row.rating = _playtime_weighted_rating(class_group)

        await self.session.flush()

        steam_ids = {row.steam_id for row in match_rows} | {
            row.steam_id for row in class_rows
        }
        for steam_id in steam_ids:
            await self._recompute_lifetime(steam_id)
            await self._recompute_class_stats(steam_id)

    async def _recompute_lifetime(self, steam_id: str) -> None:
        rows = (
            (
                await self.session.execute(
                    select(PlayerMatchStatsProjection).where(
                        PlayerMatchStatsProjection.steam_id == steam_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return

        lifetime = await self.session.get(PlayerLifetimeStatsProjection, steam_id)
        matches_played = len(rows)
        total_kills = sum(row.kills for row in rows)
        total_deaths = sum(row.deaths for row in rows)
        total_assists = sum(row.assists for row in rows)
        total_healing = sum(row.healing_done for row in rows)
        avg_dpm = sum(row.damage_per_minute for row in rows) / matches_played
        avg_rating = sum(row.rating for row in rows) / matches_played

        if lifetime is None:
            self.session.add(
                PlayerLifetimeStatsProjection(
                    steam_id=steam_id,
                    matches_played=matches_played,
                    total_kills=total_kills,
                    total_deaths=total_deaths,
                    total_assists=total_assists,
                    average_damage_per_minute=avg_dpm,
                    total_healing_done=total_healing,
                    average_rating=avg_rating,
                )
            )
            return

        lifetime.matches_played = matches_played
        lifetime.total_kills = total_kills
        lifetime.total_deaths = total_deaths
        lifetime.total_assists = total_assists
        lifetime.average_damage_per_minute = avg_dpm
        lifetime.total_healing_done = total_healing
        lifetime.average_rating = avg_rating

    async def _recompute_class_stats(self, steam_id: str) -> None:
        class_rows = (
            (
                await self.session.execute(
                    select(PlayerMatchClassStatsProjection).where(
                        PlayerMatchClassStatsProjection.steam_id == steam_id
                    )
                )
            )
            .scalars()
            .all()
        )

        existing_rows = (
            (
                await self.session.execute(
                    select(PlayerClassStatsProjection).where(
                        PlayerClassStatsProjection.steam_id == steam_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in existing_rows:
            await self.session.delete(row)
        await self.session.flush()

        by_class: dict[str, list[PlayerMatchClassStatsProjection]] = defaultdict(list)
        for row in class_rows:
            by_class[normalize_class_name(row.class_name)].append(row)

        for class_name, rows in by_class.items():
            matches_played = len({row.match_id for row in rows}) or len(rows)
            total_playtime = sum(max(int(row.playtime_seconds or 0), 0) for row in rows)
            if total_playtime > 0:
                avg_dpm = (
                    sum(
                        float(row.dpm) * max(int(row.playtime_seconds or 0), 0)
                        for row in rows
                    )
                    / total_playtime
                )
                avg_rating = (
                    sum(
                        float(row.rating) * max(int(row.playtime_seconds or 0), 0)
                        for row in rows
                    )
                    / total_playtime
                )
            else:
                avg_dpm = sum(float(row.dpm) for row in rows) / len(rows)
                avg_rating = sum(float(row.rating) for row in rows) / len(rows)

            self.session.add(
                PlayerClassStatsProjection(
                    steam_id=steam_id,
                    class_name=class_name,
                    matches_played=matches_played,
                    total_kills=sum(r.kills for r in rows),
                    total_deaths=sum(r.deaths for r in rows),
                    total_assists=sum(r.assists for r in rows),
                    average_damage_per_minute=avg_dpm,
                    total_healing_done=sum(r.healing_done for r in rows),
                    average_rating=avg_rating,
                )
            )

    async def list_matches(
        self,
        skip: int = 0,
        limit: int = 20,
        tournament_id: str | None = None,
        event_id: str | None = None,
    ) -> list[MatchSummaryView]:
        statement = select(MatchSummaryProjection).order_by(
            col(MatchSummaryProjection.date_played).desc()
        )
        if tournament_id:
            statement = statement.where(
                MatchSummaryProjection.tournament_id == tournament_id
            )
        elif event_id:
            event = await self.session.get(EventSummaryProjection, str(event_id))
            tournament_ids = (
                [str(tid) for tid in (event.tournaments or [])] if event else []
            )
            if not tournament_ids:
                return []
            statement = statement.where(
                col(MatchSummaryProjection.tournament_id).in_(tournament_ids)
            )
        statement = statement.offset(skip).limit(limit)
        rows = (await self.session.execute(statement)).scalars().all()
        return [self._match_summary_view(row) for row in rows]

    def _match_summary_view(self, row: MatchSummaryProjection) -> MatchSummaryView:
        return MatchSummaryView(
            match_id=_as_uuid(row.match_id),
            tournament_id=_as_uuid(row.tournament_id) if row.tournament_id else None,
            source_log_id=row.source_log_id,
            map_name=row.map_name,
            duration_seconds=row.duration_seconds,
            winning_team=row.winning_team,
            blu_score=int(getattr(row, "blu_score", 0) or 0),
            red_score=int(getattr(row, "red_score", 0) or 0),
            date_played=row.date_played,
            ratings_ready=bool(getattr(row, "ratings_ready", False)),
        )

    async def _resolve_match_row(self, match_id: str) -> MatchSummaryProjection | None:
        key = str(match_id or "").strip()
        if not key:
            return None

        row = await self.session.get(MatchSummaryProjection, key)
        if row is not None:
            return row

        if key.isdigit():
            return (
                (
                    await self.session.execute(
                        select(MatchSummaryProjection).where(
                            MatchSummaryProjection.source_log_id == int(key)
                        )
                    )
                )
                .scalars()
                .first()
            )

        return None

    async def get_match(self, match_id: str) -> dict[str, Any] | None:
        row = await self._resolve_match_row(match_id)
        if row is None:
            return None
        resolved_id = str(row.match_id)
        player_rows = (
            (
                await self.session.execute(
                    select(PlayerMatchStatsProjection).where(
                        PlayerMatchStatsProjection.match_id == resolved_id
                    )
                )
            )
            .scalars()
            .all()
        )
        class_rows = (
            (
                await self.session.execute(
                    select(PlayerMatchClassStatsProjection).where(
                        PlayerMatchClassStatsProjection.match_id == resolved_id
                    )
                )
            )
            .scalars()
            .all()
        )
        class_by_steam: dict[str, list[PlayerMatchClassStatsProjection]] = defaultdict(
            list
        )
        for class_row in class_rows:
            class_by_steam[class_row.steam_id].append(class_row)

        names = await self._display_names([player.steam_id for player in player_rows])
        return {
            "match_summary": self._match_summary_view(row),
            "players": [
                self._player_match_view(
                    player,
                    display_name=names.get(player.steam_id),
                    class_rows=class_by_steam.get(player.steam_id, []),
                )
                for player in player_rows
            ],
        }

    def _class_stat_view(self, row: PlayerMatchClassStatsProjection) -> ClassStatView:
        return ClassStatView(
            class_name=row.class_name,
            class_id=int(row.class_id or 0),
            playtime_seconds=int(row.playtime_seconds or 0),
            kills=int(row.kills or 0),
            deaths=int(row.deaths or 0),
            assists=int(row.assists or 0),
            dpm=float(row.dpm or 0.0),
            primary_accuracy=float(row.primary_accuracy or 0.0),
            damage_dealt=int(row.damage_dealt or 0),
            damage_received=int(row.damage_received or 0),
            heals_received=int(row.heals_received or 0),
            healing_done=int(row.healing_done or 0),
            rating=round(float(row.rating or 1.0), 3),
        )

    def _player_match_view(
        self,
        player: PlayerMatchStatsProjection,
        *,
        display_name: str | None,
        class_rows: list[PlayerMatchClassStatsProjection],
    ) -> PlayerStatsView:
        class_stats = [self._class_stat_view(row) for row in class_rows]
        class_stats.sort(key=lambda snap: snap.playtime_seconds, reverse=True)

        # Prefer stored player totals; fall back to class rows for older projections.
        # logs.tf-derived class rows often repeat player-level DT/HR on every class,
        # so use max (not sum) for those.
        damage_received = int(getattr(player, "damage_received", 0) or 0)
        heals_received = int(getattr(player, "heals_received", 0) or 0)
        ubers = int(getattr(player, "ubers", 0) or 0)
        drops = int(getattr(player, "drops", 0) or 0)
        captures = int(getattr(player, "captures", 0) or 0)
        headshots = int(getattr(player, "headshots", 0) or 0)
        backstabs = int(getattr(player, "backstabs", 0) or 0)
        airshots = int(getattr(player, "airshots", 0) or 0)
        if (
            class_rows
            and captures == 0
            and headshots == 0
            and backstabs == 0
            and airshots == 0
        ):
            captures = max(
                (int(getattr(row, "captures", 0) or 0) for row in class_rows), default=0
            )
            headshots = max(
                (int(getattr(row, "headshots", 0) or 0) for row in class_rows),
                default=0,
            )
            backstabs = max(
                (int(getattr(row, "backstabs", 0) or 0) for row in class_rows),
                default=0,
            )
            airshots = max(
                (int(getattr(row, "airshots", 0) or 0) for row in class_rows), default=0
            )
        if (
            class_rows
            and damage_received == 0
            and heals_received == 0
            and ubers == 0
            and drops == 0
        ):
            damage_received = max(
                (int(getattr(row, "damage_received", 0) or 0) for row in class_rows),
                default=0,
            )
            heals_received = max(
                (int(getattr(row, "heals_received", 0) or 0) for row in class_rows),
                default=0,
            )
            ubers = sum(int(getattr(row, "ubers", 0) or 0) for row in class_rows)
            drops = sum(int(getattr(row, "drops", 0) or 0) for row in class_rows)

        return PlayerStatsView(
            steam_id=player.steam_id,
            display_name=display_name,
            match_id=_as_uuid(player.match_id),
            team=player.team,
            classes_played=list(player.classes_played or []),
            primary_class=player.primary_class,
            playtime_seconds=player.playtime_seconds,
            kills=player.kills,
            deaths=player.deaths,
            assists=player.assists,
            damage_per_minute=player.damage_per_minute,
            healing_done=player.healing_done,
            damage_received=damage_received,
            heals_received=heals_received,
            ubers=ubers,
            drops=drops,
            captures=captures,
            headshots=headshots,
            backstabs=backstabs,
            airshots=airshots,
            rating=round(float(player.rating), 3),
            class_stats=class_stats,
        )

    async def list_tournaments(self) -> list[TournamentSummaryView]:
        rows = (
            (await self.session.execute(select(TournamentSummaryProjection)))
            .scalars()
            .all()
        )
        slug_order = {
            meta["slug"]: index
            for index, meta in enumerate(TOURNAMENT_CATALOG.values())
        }
        slug_order.setdefault("default-tournament", len(slug_order))

        def sort_key(row: TournamentSummaryProjection) -> tuple[int, str]:
            return (slug_order.get(row.slug, 10_000), row.name.lower())

        ordered = sorted(rows, key=sort_key)
        return [self._tournament_summary_view(row) for row in ordered]

    def _tournament_summary_view(
        self, row: TournamentSummaryProjection
    ) -> TournamentSummaryView:
        return TournamentSummaryView(
            tournament_id=_as_uuid(row.tournament_id),
            name=row.name,
            slug=row.slug,
            match_count=row.match_count,
            started_at=row.started_at,
            event_id=_as_uuid(row.event_id) if row.event_id else None,
        )

    async def _event_match_count(self, tournament_ids: list[str]) -> int:
        if not tournament_ids:
            return 0
        return int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(MatchSummaryProjection)
                    .where(col(MatchSummaryProjection.tournament_id).in_(tournament_ids))
                )
            ).scalar_one()
            or 0
        )

    async def _event_summary_view(self, row: EventSummaryProjection) -> EventSummaryView:
        tournament_ids = [str(tid) for tid in (row.tournaments or []) if tid]
        uuids: list[UUID] = []
        for tournament_id in tournament_ids:
            try:
                uuids.append(_as_uuid(tournament_id))
            except (TypeError, ValueError):
                continue
        return EventSummaryView(
            event_id=_as_uuid(row.event_id),
            name=row.name,
            slug=row.slug,
            start_date=row.start_date or row.started_at,
            end_date=row.end_date,
            tournament_ids=uuids,
            tournament_count=len(uuids),
            match_count=await self._event_match_count(tournament_ids),
        )

    async def list_events(self) -> list[EventSummaryView]:
        rows = (
            (await self.session.execute(select(EventSummaryProjection))).scalars().all()
        )

        def sort_key(row: EventSummaryProjection) -> tuple[datetime | str, str]:
            start = row.start_date or row.started_at
            return (start or datetime.max, row.name.lower())

        ordered = sorted(rows, key=sort_key)
        return [await self._event_summary_view(row) for row in ordered]

    async def get_event(self, event_id: str) -> EventDetailView | None:
        row = await self.session.get(EventSummaryProjection, str(event_id))
        if row is None:
            return None
        tournament_ids = [str(tid) for tid in (row.tournaments or []) if tid]
        tournaments: list[TournamentSummaryView] = []
        if tournament_ids:
            tournament_rows = (
                (
                    await self.session.execute(
                        select(TournamentSummaryProjection).where(
                            col(TournamentSummaryProjection.tournament_id).in_(
                                tournament_ids
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_id = {item.tournament_id: item for item in tournament_rows}
            tournaments = [
                self._tournament_summary_view(by_id[tid])
                for tid in tournament_ids
                if tid in by_id
            ]
        return EventDetailView(
            event=await self._event_summary_view(row),
            tournaments=tournaments,
        )

    async def get_event_leaderboard(
        self,
        event_id: str,
        class_name: str | None = None,
        limit: int = 50,
    ) -> list[LeaderboardEntryView]:
        row = await self.session.get(EventSummaryProjection, str(event_id))
        if row is None:
            return []
        tournament_ids = [str(tid) for tid in (row.tournaments or []) if tid]
        entries = await self._compute_leaderboard_entries(
            tournament_ids, class_name=class_name
        )
        names = await self._display_names([entry.steam_id for entry in entries])
        for entry in entries:
            entry.display_name = names.get(entry.steam_id) or entry.display_name
        return entries[: max(1, min(limit, 200))]

    async def get_global_leaderboard(
        self,
        class_name: str | None = None,
        limit: int = 50,
    ) -> list[LeaderboardEntryView]:
        """Leaderboard across every tournament (the "all events, all matches" scope)."""
        entries = await self._compute_leaderboard_entries(
            await self._all_tournament_ids(), class_name=class_name
        )
        entries = entries[: max(1, min(limit, 200))]
        names = await self._display_names([entry.steam_id for entry in entries])
        for entry in entries:
            entry.display_name = names.get(entry.steam_id) or entry.display_name
        return entries

    async def _all_tournament_ids(self) -> set[str]:
        class_ids = (
            (
                await self.session.execute(
                    select(PlayerMatchClassStatsProjection.tournament_id)
                    .where(PlayerMatchClassStatsProjection.tournament_id.is_not(None))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        match_ids = (
            (
                await self.session.execute(
                    select(MatchSummaryProjection.tournament_id)
                    .where(MatchSummaryProjection.tournament_id.is_not(None))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        return {str(tid) for tid in list(class_ids) + list(match_ids) if tid}

    async def get_tournament_leaderboard(
        self,
        tournament_id: str,
        class_name: str | None = None,
        limit: int = 50,
    ) -> list[LeaderboardEntryView]:
        snapshot_class = normalize_class_name(class_name) if class_name else ""
        statement = (
            select(LeaderboardSnapshotProjection)
            .where(LeaderboardSnapshotProjection.tournament_id == tournament_id)
            .where(LeaderboardSnapshotProjection.class_name == snapshot_class)
            .order_by(col(LeaderboardSnapshotProjection.average_rating).desc())
            .limit(max(1, min(limit, 200)))
        )
        rows = (await self.session.execute(statement)).scalars().all()
        names = await self._display_names([row.steam_id for row in rows])
        return [
            LeaderboardEntryView(
                steam_id=row.steam_id,
                display_name=names.get(row.steam_id),
                matches_played=row.matches_played,
                total_kills=row.total_kills,
                total_deaths=row.total_deaths,
                total_assists=row.total_assists,
                average_damage_per_minute=row.average_damage_per_minute,
                total_healing_done=row.total_healing_done,
                average_rating=row.average_rating,
                primary_class=row.primary_class,
            )
            for row in rows
        ]

    async def refresh_all_tournament_leaderboards(self) -> None:
        for tournament_id in await self._all_tournament_ids():
            await self.refresh_tournament_leaderboard(tournament_id)

    async def refresh_tournament_leaderboard(self, tournament_id: str) -> None:
        """Recompute and upsert all-classes + per-class leaderboard snapshot rows."""
        now = utcnow()
        all_entries = await self._compute_leaderboard_entries(
            tournament_id, class_name=None
        )
        class_names = (
            (
                await self.session.execute(
                    select(PlayerMatchClassStatsProjection.class_name)
                    .where(
                        PlayerMatchClassStatsProjection.tournament_id == tournament_id
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        partitions: list[tuple[str, list[LeaderboardEntryView]]] = [("", all_entries)]
        for raw_class in class_names:
            normalized = normalize_class_name(str(raw_class))
            partitions.append(
                (
                    normalized,
                    await self._compute_leaderboard_entries(
                        tournament_id, class_name=normalized
                    ),
                )
            )

        existing_rows = (
            (
                await self.session.execute(
                    select(LeaderboardSnapshotProjection).where(
                        LeaderboardSnapshotProjection.tournament_id == tournament_id
                    )
                )
            )
            .scalars()
            .all()
        )
        by_key = {(row.steam_id, row.class_name): row for row in existing_rows}
        seen: set[tuple[str, str]] = set()

        for partition_class, entries in partitions:
            for entry in entries:
                key = (entry.steam_id, partition_class)
                seen.add(key)
                existing = by_key.get(key)
                if existing is None:
                    self.session.add(
                        LeaderboardSnapshotProjection(
                            tournament_id=tournament_id,
                            steam_id=entry.steam_id,
                            class_name=partition_class,
                            matches_played=entry.matches_played,
                            total_kills=entry.total_kills,
                            total_deaths=entry.total_deaths,
                            total_assists=entry.total_assists,
                            average_damage_per_minute=entry.average_damage_per_minute,
                            total_healing_done=entry.total_healing_done,
                            average_rating=entry.average_rating,
                            primary_class=entry.primary_class,
                            updated_at=now,
                        )
                    )
                else:
                    existing.matches_played = entry.matches_played
                    existing.total_kills = entry.total_kills
                    existing.total_deaths = entry.total_deaths
                    existing.total_assists = entry.total_assists
                    existing.average_damage_per_minute = entry.average_damage_per_minute
                    existing.total_healing_done = entry.total_healing_done
                    existing.average_rating = entry.average_rating
                    existing.primary_class = entry.primary_class
                    existing.updated_at = now

        for key, row in by_key.items():
            if key not in seen:
                await self.session.delete(row)
        await self.session.flush()

    async def _compute_leaderboard_entries(
        self,
        tournament_id: str | list[str] | set[str],
        class_name: str | None = None,
    ) -> list[LeaderboardEntryView]:
        tournament_ids = (
            [str(tournament_id)]
            if isinstance(tournament_id, str)
            else [str(tid) for tid in tournament_id if tid]
        )
        if not tournament_ids:
            return []
        # Prefer tournament_id stamped on per-class projection rows.
        class_statement = select(PlayerMatchClassStatsProjection).where(
            col(PlayerMatchClassStatsProjection.tournament_id).in_(tournament_ids)
        )
        if class_name:
            class_statement = class_statement.where(
                PlayerMatchClassStatsProjection.class_name
                == normalize_class_name(class_name)
            )
        class_rows = (await self.session.execute(class_statement)).scalars().all()

        if class_rows:
            by_player: dict[str, list[PlayerMatchClassStatsProjection]] = defaultdict(
                list
            )
            for row in class_rows:
                by_player[row.steam_id].append(row)

            entries: list[LeaderboardEntryView] = []
            for steam_id, player_rows in by_player.items():
                matches_played = len({row.match_id for row in player_rows}) or len(
                    player_rows
                )
                class_counts: dict[str, int] = defaultdict(int)
                for row in player_rows:
                    class_counts[row.class_name] += 1
                top_class = max(class_counts.items(), key=lambda item: item[1])[0]
                total_playtime = sum(
                    max(int(row.playtime_seconds or 0), 0) for row in player_rows
                )
                if total_playtime > 0:
                    avg_dpm = (
                        sum(
                            float(row.dpm) * max(int(row.playtime_seconds or 0), 0)
                            for row in player_rows
                        )
                        / total_playtime
                    )
                    avg_rating = _playtime_weighted_rating(player_rows)
                else:
                    avg_dpm = sum(float(row.dpm) for row in player_rows) / len(
                        player_rows
                    )
                    avg_rating = sum(float(row.rating) for row in player_rows) / len(
                        player_rows
                    )
                entries.append(
                    LeaderboardEntryView(
                        steam_id=steam_id,
                        matches_played=matches_played,
                        total_kills=sum(r.kills for r in player_rows),
                        total_deaths=sum(r.deaths for r in player_rows),
                        total_assists=sum(r.assists for r in player_rows),
                        average_damage_per_minute=round(avg_dpm, 2),
                        total_healing_done=sum(r.healing_done for r in player_rows),
                        average_rating=round(float(avg_rating), 3),
                        primary_class=top_class,
                    )
                )
            entries.sort(key=lambda entry: entry.average_rating, reverse=True)
            return entries

        # Fallback for legacy projections that lack tournament_id on class rows.
        match_ids = (
            (
                await self.session.execute(
                    select(MatchSummaryProjection.match_id).where(
                        col(MatchSummaryProjection.tournament_id).in_(tournament_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        if not match_ids:
            return []

        statement = select(PlayerMatchStatsProjection).where(
            col(PlayerMatchStatsProjection.match_id).in_(list(match_ids))
        )
        if class_name:
            statement = statement.where(
                PlayerMatchStatsProjection.primary_class
                == normalize_class_name(class_name)
            )
        rows = (await self.session.execute(statement)).scalars().all()

        by_player_match: dict[str, list[PlayerMatchStatsProjection]] = defaultdict(list)
        for row in rows:
            by_player_match[row.steam_id].append(row)

        entries = []
        for steam_id, player_rows in by_player_match.items():
            matches_played = len(player_rows)
            class_counts: dict[str, int] = defaultdict(int)
            for row in player_rows:
                class_counts[row.primary_class] += 1
            top_class = max(class_counts.items(), key=lambda item: item[1])[0]
            entries.append(
                LeaderboardEntryView(
                    steam_id=steam_id,
                    matches_played=matches_played,
                    total_kills=sum(r.kills for r in player_rows),
                    total_deaths=sum(r.deaths for r in player_rows),
                    total_assists=sum(r.assists for r in player_rows),
                    average_damage_per_minute=round(
                        sum(r.damage_per_minute for r in player_rows) / matches_played,
                        2,
                    ),
                    total_healing_done=sum(r.healing_done for r in player_rows),
                    average_rating=round(
                        sum(r.rating for r in player_rows) / matches_played, 3
                    ),
                    primary_class=top_class,
                )
            )

        entries.sort(key=lambda entry: entry.average_rating, reverse=True)
        return entries

    async def get_player_recent_matches(
        self,
        steam_id: str,
        limit: int = 10,
    ) -> list[PlayerRecentMatchView]:
        limit = max(1, min(limit, 50))
        resolved_id, _row = await self._resolve_lifetime_stats_row(steam_id)
        candidate_ids = self._player_id_candidates(steam_id) or [resolved_id]
        rows = (
            await self.session.execute(
                select(PlayerMatchStatsProjection, MatchSummaryProjection)
                .join(
                    MatchSummaryProjection,
                    MatchSummaryProjection.match_id
                    == PlayerMatchStatsProjection.match_id,
                )
                .where(col(PlayerMatchStatsProjection.steam_id).in_(candidate_ids))
                .order_by(col(MatchSummaryProjection.date_played).desc())
                .limit(limit)
            )
        ).all()
        return [
            PlayerRecentMatchView(
                match_id=_as_uuid(match_row.match_id),
                map_name=match_row.map_name,
                date_played=match_row.date_played,
                team=player_row.team,
                classes_played=list(player_row.classes_played or []),
                kills=player_row.kills,
                deaths=player_row.deaths,
                assists=player_row.assists,
                damage_per_minute=round(float(player_row.damage_per_minute), 2),
                healing_done=player_row.healing_done,
                rating=round(float(player_row.rating), 3),
            )
            for player_row, match_row in rows
        ]

    async def get_player_stats(self, steam_id: str) -> PlayerLifetimeStatsView:
        resolved_id, row = await self._resolve_lifetime_stats_row(steam_id)
        candidate_ids = self._player_id_candidates(steam_id) or [resolved_id]
        class_rows = (
            (
                await self.session.execute(
                    select(PlayerClassStatsProjection)
                    .where(col(PlayerClassStatsProjection.steam_id).in_(candidate_ids))
                    .order_by(col(PlayerClassStatsProjection.matches_played).desc())
                )
            )
            .scalars()
            .all()
        )
        class_breakdown = [
            PlayerClassAggregateView(
                class_name=item.class_name,
                matches_played=item.matches_played,
                total_kills=item.total_kills,
                total_deaths=item.total_deaths,
                total_assists=item.total_assists,
                average_damage_per_minute=round(
                    float(item.average_damage_per_minute), 2
                ),
                total_healing_done=item.total_healing_done,
                average_rating=round(float(item.average_rating), 3),
            )
            for item in class_rows
        ]
        recent_matches = await self.get_player_recent_matches(resolved_id)
        names = await self._display_names([resolved_id])
        display_name = names.get(resolved_id)

        if row is None:
            return PlayerLifetimeStatsView(
                steam_id=resolved_id,
                display_name=display_name,
                matches_played=0,
                total_kills=0,
                total_deaths=0,
                total_assists=0,
                average_damage_per_minute=0.0,
                total_healing_done=0,
                average_rating=0.0,
                class_breakdown=class_breakdown,
                recent_matches=recent_matches,
            )
        return PlayerLifetimeStatsView(
            steam_id=row.steam_id,
            display_name=display_name,
            matches_played=row.matches_played,
            total_kills=row.total_kills,
            total_deaths=row.total_deaths,
            total_assists=row.total_assists,
            average_damage_per_minute=row.average_damage_per_minute,
            total_healing_done=row.total_healing_done,
            average_rating=round(float(row.average_rating), 3),
            class_breakdown=class_breakdown,
            recent_matches=recent_matches,
        )

    async def list_benchmarks(self) -> list[ClassRatingBenchmarkView]:
        rows = (
            (
                await self.session.execute(
                    select(ClassRatingBenchmarkProjection).order_by(
                        col(ClassRatingBenchmarkProjection.class_id).asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            ClassRatingBenchmarkView(
                class_name=row.class_name,
                class_id=int(row.class_id),
                sample_size=row.sample_size,
                avg_rating=row.avg_rating,
                std_rating=row.std_rating,
                min_rating=row.min_rating,
                max_rating=row.max_rating,
                p50_rating=row.p50_rating,
            )
            for row in rows
        ]

    async def search(self, query: str, limit: int = 20) -> list[SearchResultView]:
        q = query.strip()
        if not q:
            return []

        results: list[SearchResultView] = []
        limit = max(1, min(limit, 50))

        if q.isdigit():
            log_id = int(q)
            match_row = (
                (
                    await self.session.execute(
                        select(MatchSummaryProjection).where(
                            MatchSummaryProjection.source_log_id == log_id
                        )
                    )
                )
                .scalars()
                .first()
            )
            if match_row:
                results.append(
                    SearchResultView(
                        kind="log",
                        id=str(log_id),
                        label=f"logs.tf/{log_id} · {match_row.map_name}",
                        match_id=_as_uuid(match_row.match_id),
                        source_log_id=log_id,
                    )
                )

        match_row = await self.session.get(MatchSummaryProjection, q)
        if match_row:
            results.append(
                SearchResultView(
                    kind="match",
                    id=match_row.match_id,
                    label=f"Match · {match_row.map_name}",
                    match_id=_as_uuid(match_row.match_id),
                    source_log_id=match_row.source_log_id,
                )
            )

        for candidate in self._player_id_candidates(q):
            player_row = await self.session.get(
                PlayerLifetimeStatsProjection, candidate
            )
            if player_row and player_row.matches_played > 0:
                names = await self._display_names([player_row.steam_id])
                display_name = names.get(player_row.steam_id)
                label_name = display_name or player_row.steam_id
                results.append(
                    SearchResultView(
                        kind="player",
                        id=player_row.steam_id,
                        label=f"Player · {label_name} · {player_row.matches_played} matches",
                        steam_id=player_row.steam_id,
                        display_name=display_name,
                    )
                )
                break

        like = f"%{q}%"
        identity_rows = (
            (
                await self.session.execute(
                    select(PlayerIdentityProjection)
                    .where(
                        or_(
                            col(PlayerIdentityProjection.persona_name).ilike(like),
                            col(PlayerIdentityProjection.custom_alias).ilike(like),
                        )
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for identity in identity_rows:
            player_row = await self.session.get(
                PlayerLifetimeStatsProjection, identity.steam_id
            )
            if player_row is None or player_row.matches_played <= 0:
                continue
            display_name = identity.custom_alias or identity.persona_name
            label_name = display_name or player_row.steam_id
            results.append(
                SearchResultView(
                    kind="player",
                    id=player_row.steam_id,
                    label=f"Player · {label_name} · {player_row.matches_played} matches",
                    steam_id=player_row.steam_id,
                    display_name=display_name,
                )
            )

        steam_rows = (
            (
                await self.session.execute(
                    select(PlayerLifetimeStatsProjection)
                    .where(col(PlayerLifetimeStatsProjection.steam_id).like(like))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        names = await self._display_names([row.steam_id for row in steam_rows])
        for row in steam_rows:
            display_name = names.get(row.steam_id)
            label_name = display_name or row.steam_id
            results.append(
                SearchResultView(
                    kind="player",
                    id=row.steam_id,
                    label=f"Player · {label_name} · {row.matches_played} matches",
                    steam_id=row.steam_id,
                    display_name=display_name,
                )
            )

        # Deduplicate by kind+id while preserving order.
        seen: set[tuple[str, str]] = set()
        unique: list[SearchResultView] = []
        for item in results:
            key = (item.kind, item.id)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique[:limit]
