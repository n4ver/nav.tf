"""Business logic and database services for TF2 analytics."""

from sqlmodel import Session, select, func, desc, asc
from sqlalchemy import case
from typing import List, Literal, Optional, Dict, Any
from models import Player, MatchStat, Match, Class, MedicStat, Tournament
from schemas import (
    LeaderboardEntryResponse,
    LogStatsResponse,
    LogStatEntry,
    LogStatsSummary,
    MedicStatResponse,
    PlayerSummaryResponse,
    PlayerClassBreakdown,
    PlayerAggregateStats,
    PlayerMatchEntry,
)
import logging

logger = logging.getLogger(__name__)


class LeaderboardService:
    """Service for tournament leaderboard queries."""
    
    @staticmethod
    def build_leaderboard_query(
        db: Session,
        tournament_id: int,
        class_name: str,
        min_playtime_seconds: int = 600,
        limit: int = 10,
    ):
        """Build a leaderboard query for a specific tournament and class."""

        effective_min_playtime = max(min_playtime_seconds, 600)
        
        avg_kills_expr = func.avg(MatchStat.kills).label("avg_kills")
        avg_deaths_expr = func.avg(MatchStat.deaths).label("avg_deaths")
        avg_dpm_expr = func.avg(MatchStat.dpm).label("avg_dpm")
        total_playtime_expr = func.sum(MatchStat.playtime).label("total_playtime")
        avg_heals_expr = func.avg(MatchStat.heals_received).label("avg_heals")
        total_healing_done_expr = func.sum(func.coalesce(MedicStat.healing_done, 0)).label("total_healing_done")
        total_ubers_expr = func.sum(func.coalesce(MedicStat.ubers, 0)).label("total_ubers")
        total_drops_expr = func.sum(func.coalesce(MedicStat.drops, 0)).label("total_drops")
        avg_kad_expr = func.coalesce(
            avg_kills_expr / func.nullif(avg_deaths_expr, 0),
            avg_kills_expr,
        ).label("avg_kad")
        avg_hpm_expr = func.coalesce(
            total_healing_done_expr / func.nullif(total_playtime_expr / 60.0, 0),
            0,
        ).label("avg_hpm")

        minutes_expr = func.nullif(MatchStat.playtime / 60.0, 0)
        kills_pm_expr = func.coalesce(MatchStat.kills / minutes_expr, 0.0)
        deaths_pm_expr = func.coalesce(MatchStat.deaths / minutes_expr, 0.0)
        damage_efficiency_expr = func.coalesce(MatchStat.damage_dealt / func.nullif(MatchStat.damage_received, 0), 0.0)
        healing_efficiency_expr = func.coalesce(MatchStat.damage_received / func.nullif(MatchStat.heals_received, 0), 0.0)

        base_rating_expr = (
            (kills_pm_expr * 0.35)
            + (MatchStat.dpm * 0.0025)
            - (deaths_pm_expr * 0.22)
            + (damage_efficiency_expr * 0.18)
            - (healing_efficiency_expr * 0.08)
        )

        medic_bonus_expr = (
            (func.coalesce(MedicStat.hpm, 0.0) * 0.01)
            + (func.coalesce(MedicStat.ubers, 0) * 0.06)
            - (func.coalesce(MedicStat.drops, 0) * 0.08)
        )

        stat_table = MatchStat.__table__  # type: ignore[attr-defined]
        per_row_rating_expr = case(
            (stat_table.c.class_id == 6, base_rating_expr + medic_bonus_expr),
            else_=base_rating_expr,
        )
        avg_rating_expr = func.avg(per_row_rating_expr).label("avg_rating")

        statement = (
            select(
                Player.last_known_name,
                Player.steamid,
                Class.name,
                avg_kills_expr,
                avg_deaths_expr,
                avg_dpm_expr,
                avg_kad_expr,
                avg_rating_expr,
                total_playtime_expr,
                avg_heals_expr,
                avg_hpm_expr,
                total_ubers_expr,
                total_drops_expr,
            )  # type: ignore
            .join(MatchStat, Player.id == MatchStat.player_id)
            .join(Match, Match.id == MatchStat.match_id)
            .join(Class, Class.id == MatchStat.class_id)
            .outerjoin(MedicStat, MedicStat.matchstat_id == MatchStat.id)
            .where(Match.tournament_id == tournament_id)
            .where(MatchStat.playtime >= effective_min_playtime)
            .where(func.lower(Class.name) == func.lower(class_name))
            .group_by(Player.steamid, Player.last_known_name, Class.id)
            .limit(limit)
        )
        return statement, avg_hpm_expr, avg_dpm_expr, avg_kad_expr, avg_rating_expr, avg_deaths_expr, total_playtime_expr, total_ubers_expr, total_drops_expr

    @staticmethod
    def apply_sorting(
        statement,
        class_name: str,
        sort_by: str = "rating",
        sort_order: str = "desc",
        avg_hpm_expr=None,
        avg_dpm_expr=None,
        avg_kad_expr=None,
        avg_rating_expr=None,
        avg_kills_expr=None,
        avg_deaths_expr=None,
        total_playtime_expr=None,
        total_ubers_expr=None,
        total_drops_expr=None,
    ):
        """Apply appropriate sorting to leaderboard query."""
        direction = asc if sort_order == "asc" else desc

        sort_expr_map = {
            "rating": avg_rating_expr,
            "dpm": avg_dpm_expr,
            "kad": avg_kad_expr,
            "kills": avg_kills_expr,
            "deaths": avg_deaths_expr,
            "playtime": total_playtime_expr,
            "hpm": avg_hpm_expr,
            "ubers": total_ubers_expr,
            "drops": total_drops_expr,
        }
        sort_expr = sort_expr_map.get(sort_by, avg_rating_expr)
        return statement.order_by(direction(sort_expr), desc(total_playtime_expr))

    @staticmethod
    def transform_leaderboard_result(row) -> LeaderboardEntryResponse:
        """Transform database row to LeaderboardEntryResponse."""
        return LeaderboardEntryResponse(  # type: ignore
            name=row.last_known_name,
            steamid=row.steamid,
            class_name=row.name, # type: ignore
            avg_rating=round(float(row.avg_rating), 3),
            avg_dpm=round(float(row.avg_dpm), 2),
            avg_hpm=round(float(row.avg_hpm), 2),
            avg_kad=round(float(row.avg_kad), 2),
            avg_kdr=round(float(row.avg_kad), 2),
            avg_kills=round(float(row.avg_kills), 2),
            avg_deaths=round(float(row.avg_deaths), 2),
            avg_heals=round(float(row.avg_heals), 2),
            total_ubers=int(row.total_ubers) if row.total_ubers else 0,
            total_drops=int(row.total_drops) if row.total_drops else 0,
            playtime_mins=int(row.total_playtime // 60) if row.total_playtime else 0,
        )


class LogService:
    """Service for log statistics queries."""
    
    @staticmethod
    def get_log_stats(db: Session, log_id: int) -> LogStatsResponse:
        """Get all stats for a specific log."""
        match = db.exec(select(Match).where(Match.log_id == log_id)).first()
        if not match:
            raise ValueError(f"Log {log_id} not found")

        statement = (
            select(MatchStat, Player, Class, MedicStat)
            .join(Player, Player.id == MatchStat.player_id)  # type: ignore
            .join(Class, Class.id == MatchStat.class_id)  # type: ignore
            .outerjoin(MedicStat, MedicStat.matchstat_id == MatchStat.id)  # type: ignore
            .where(MatchStat.match_id == match.id)
        )

        rows = db.exec(statement).all()
        entries: List[LogStatEntry] = []
        total_kills = 0
        total_deaths = 0
        total_dpm = 0.0

        for stat, player, player_class, medic in rows:
            total_kills += stat.kills
            total_deaths += stat.deaths
            total_dpm += stat.dpm
            
            medic_data = None
            if medic:
                medic_data = MedicStatResponse(
                    ubers=medic.ubers,
                    drops=medic.drops,
                    healing_done=medic.healing_done,
                    hpm=medic.hpm,
                )
            
            entries.append(
                LogStatEntry(  # type: ignore
                    steamid=player.steamid,
                    player_name=player.last_known_name,
                    class_name=player_class.name, # type: ignore
                    kills=stat.kills,
                    deaths=stat.deaths,
                    dpm=round(stat.dpm, 2),
                    medic=medic_data,
                )
            )

        avg_dpm = round(total_dpm / len(entries), 2) if entries else 0.0

        return LogStatsResponse(
            log_id=match.log_id,
            match_id=match.id,  # type: ignore
            map=match.map,
            tournament_id=match.tournament_id,
            summary=LogStatsSummary(
                entries=len(entries),
                total_kills=total_kills,
                total_deaths=total_deaths,
                avg_dpm=avg_dpm,
            ),
            stats=entries,
        )


class PlayerService:
    """Service for player statistics queries."""

    @staticmethod
    def _safe_per_minute(value: int | float | None, playtime_seconds: int | None) -> float:
        minutes = max((playtime_seconds or 0) / 60.0, 1.0)
        return float(value or 0.0) / minutes

    @staticmethod
    def _safe_ratio(numerator: int | float | None, denominator: int | float | None) -> float:
        denom = float(denominator or 0.0)
        if denom == 0.0:
            return 0.0
        return float(numerator or 0.0) / denom

    @staticmethod
    def _quantile(sorted_vals: list[float], q: float) -> float:
        if not sorted_vals:
            return 0.0
        if len(sorted_vals) == 1:
            return sorted_vals[0]
        idx = q * (len(sorted_vals) - 1)
        lower_idx = int(idx)
        upper_idx = min(lower_idx + 1, len(sorted_vals) - 1)
        frac = idx - lower_idx
        return sorted_vals[lower_idx] * (1 - frac) + sorted_vals[upper_idx] * frac

    @staticmethod
    def _compute_match_rating(stat: MatchStat, medic: Optional[MedicStat]) -> float:
        kills_pm = PlayerService._safe_per_minute(stat.kills, stat.playtime)
        deaths_pm = PlayerService._safe_per_minute(stat.deaths, stat.playtime)
        damage_efficiency = PlayerService._safe_ratio(stat.damage_dealt, stat.damage_received)
        healing_efficiency = PlayerService._safe_ratio(stat.damage_received, stat.heals_received)

        score = (
            (kills_pm * 0.35)
            + (float(stat.dpm or 0.0) * 0.0025)
            - (deaths_pm * 0.22)
            + (damage_efficiency * 0.18)
            - (healing_efficiency * 0.08)
        )

        # Medic rows receive additional support credit from medic-specific stats.
        if stat.class_id == 6 and medic is not None:
            medic_support = (
                float(medic.hpm or 0.0) * 0.01
                + float(medic.ubers or 0) * 0.06
                - float(medic.drops or 0) * 0.08
            )
            score += medic_support

        return score

    @staticmethod
    def _normalize_ratings(raw_scores: list[float]) -> list[float]:
        if not raw_scores:
            return []

        ordered = sorted(raw_scores)
        p05 = PlayerService._quantile(ordered, 0.05)
        p95 = PlayerService._quantile(ordered, 0.95)
        denom = (p95 - p05) if (p95 - p05) != 0 else 1.0

        normalized = [0.6 + ((score - p05) / denom) * 0.8 for score in raw_scores]
        return [round(max(0.0, min(2.0, value)), 3) for value in normalized]
    
    @staticmethod
    def get_player_summary(db: Session, steam_id: str) -> PlayerSummaryResponse:
        """Get aggregate stats for a player across all matches."""
        player = db.exec(select(Player).where(Player.steamid == steam_id)).first()
        if not player:
            raise ValueError(f"Player {steam_id} not found")

        match_rows_query = (
            select(MatchStat, Match, Class, MedicStat)
            .join(Match, Match.id == MatchStat.match_id)  # type: ignore
            .join(Class, Class.id == MatchStat.class_id)  # type: ignore
            .outerjoin(MedicStat, MedicStat.matchstat_id == MatchStat.id)  # type: ignore
            .where(MatchStat.player_id == player.id)
            .order_by(desc(Match.id))
        )
        match_rows = db.exec(match_rows_query).all()

        total_kills = 0
        total_deaths = 0
        total_playtime = 0
        total_dpm = 0.0
        total_damage_dealt = 0
        total_damage_received = 0
        total_heals_received = 0
        match_rating_raw: List[float] = []
        match_entries: List[PlayerMatchEntry] = []

        for stat, match, player_class, medic in match_rows:
            total_kills += int(stat.kills or 0)
            total_deaths += int(stat.deaths or 0)
            total_playtime += int(stat.playtime or 0)
            total_dpm += float(stat.dpm or 0)
            total_damage_dealt += int(stat.damage_dealt or 0)
            total_damage_received += int(stat.damage_received or 0)
            total_heals_received += int(stat.heals_received or 0)
            match_rating_raw.append(PlayerService._compute_match_rating(stat, medic))

            match_entries.append(
                PlayerMatchEntry(
                    match_id=int(match.id or 0),
                    log_id=int(match.log_id or 0),
                    map=match.map,
                    tournament_id=int(match.tournament_id or 0),
                    class_name=player_class.name,
                    team=stat.team,
                    playtime_mins=int((stat.playtime or 0) // 60),
                    kills=int(stat.kills or 0),
                    deaths=int(stat.deaths or 0),
                    dpm=round(float(stat.dpm or 0), 2),
                    damage_dealt=int(stat.damage_dealt or 0),
                    damage_received=int(stat.damage_received or 0),
                    heals_received=int(stat.heals_received or 0),
                    ubers=int(medic.ubers or 0) if medic else 0,
                    drops=int(medic.drops or 0) if medic else 0,
                    hpm=round(float(medic.hpm or 0), 2) if medic else 0.0,
                )
            )

        matches_played = len(match_rows)
        avg_dpm = round(total_dpm / matches_played, 2) if matches_played else 0.0
        avg_kdr = round(total_kills / total_deaths, 2) if total_deaths else round(float(total_kills), 2)
        match_ratings = PlayerService._normalize_ratings(match_rating_raw)
        avg_rating = round(sum(match_ratings) / len(match_ratings), 3) if match_ratings else 0.0

        class_table = Class.__table__  # type: ignore[attr-defined]
        stat_table = MatchStat.__table__  # type: ignore[attr-defined]

        stats_query = (
            select(
                class_table.c.name.label("class_name"),
                func.avg(stat_table.c.dpm).label("avg_dpm"),
                func.sum(stat_table.c.kills).label("sum_kills"),
                func.count(stat_table.c.id).label("matches_played"),
            )
                .select_from(stat_table.join(class_table, class_table.c.id == stat_table.c.class_id))  # type: ignore
            .where(stat_table.c.player_id == player.id)
            .group_by(class_table.c.id, class_table.c.name)
        )
        
        breakdown_rows = db.exec(stats_query).all()

        class_breakdown = [
            PlayerClassBreakdown(
                class_name=class_name,
                avg_dpm=round(float(avg_dpm or 0), 2),
                sum_kills=int(sum_kills or 0),
                matches_played=int(matches_played or 0),
            )
            for class_name, avg_dpm, sum_kills, matches_played in breakdown_rows
        ]

        return PlayerSummaryResponse(
            steamid=steam_id,
            player_name=player.last_known_name,
            aggregate_stats=PlayerAggregateStats(
                matches_played=matches_played,
                avg_rating=avg_rating,
                total_kills=total_kills,
                total_deaths=total_deaths,
                total_playtime_mins=total_playtime // 60,
                avg_dpm=avg_dpm,
                avg_kdr=avg_kdr,
                total_damage_dealt=total_damage_dealt,
                total_damage_received=total_damage_received,
                total_heals_received=total_heals_received,
            ),
            class_breakdown=class_breakdown,
            matches=match_entries,
        )
