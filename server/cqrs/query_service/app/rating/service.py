"""Query-side rating bounded context — z-score math + class benchmarks.

Command service must never import this package. Class name helpers live in
`cqrs.shared.tf2_classes`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

from ....shared.tf2_classes import class_id_from_name, class_name_from_id
from ....shared.timeutils import utcnow


class MatchStatLike(Protocol):
    class_id: int
    playtime: int
    kills: int
    deaths: int
    dpm: float
    primary_accuracy: float
    damage_dealt: int
    damage_received: int
    heals_received: int
    captures: int


class MedicStatLike(Protocol):
    healing_done: int
    ubers: int
    drops: int


@dataclass(frozen=True)
class RatingStatRow:
    """Immutable MatchStat (+ optional medic) row for rating math."""

    class_id: int
    playtime: int
    kills: int
    deaths: int
    dpm: float
    primary_accuracy: float
    damage_dealt: int
    damage_received: int
    heals_received: int
    captures: int
    healing_done: int = 0
    ubers: int = 0
    drops: int = 0
    steam_id: str = ""
    match_id: str = ""


def rating_row_from_mapping(data: Mapping[str, Any]) -> RatingStatRow:
    class_name = data.get("class_name") or data.get("primary_class")
    class_id = data.get("class_id")
    if class_id is None:
        class_id = class_id_from_name(str(class_name) if class_name else None)
    return RatingStatRow(
        class_id=int(class_id),
        playtime=int(data.get("playtime") or data.get("playtime_seconds") or 0),
        kills=int(data.get("kills") or 0),
        deaths=int(data.get("deaths") or 0),
        dpm=float(data.get("dpm") or data.get("damage_per_minute") or 0.0),
        primary_accuracy=float(data.get("primary_accuracy") or 0.0),
        damage_dealt=int(data.get("damage_dealt") or 0),
        damage_received=int(data.get("damage_received") or 0),
        heals_received=int(data.get("heals_received") or 0),
        captures=int(data.get("captures") or 0),
        healing_done=int(data.get("healing_done") or 0),
        ubers=int(data.get("ubers") or 0),
        drops=int(data.get("drops") or 0),
        steam_id=str(data.get("steam_id") or ""),
        match_id=str(data.get("match_id") or ""),
    )


class RatingService:
    """Notebook-aligned z-score rating calculations (monolith port)."""

    FEATURE_COLUMNS: ClassVar[list[str]] = [
        "kills_per_min",
        "deaths_per_min",
        "dpm",
        "primary_accuracy",
        "damage_dealt_per_min",
        "damage_received_per_min",
        "heals_received_per_min",
        "captures_per_min",
        "healing_done_per_min",
        "ubers_per_min",
        "drops_per_min",
        "objective_per_min",
        "damage_efficiency",
        "healing_efficiency",
        "kill_conversion",
        "pressure_resistance",
        "medic_support_impact",
    ]

    IMPACT_WEIGHTS: ClassVar[dict[str, float]] = {
        "z_kills_per_min": 0.26,
        "z_objective_per_min": 0.12,
        "z_damage_efficiency": 0.18,
        "z_healing_efficiency": -0.08,
        "z_kill_conversion": 0.12,
        "z_pressure_resistance": 0.10,
        "z_primary_accuracy": 0.10,
        "z_medic_support_impact": 0.10,
    }

    CLASS_WEIGHTS: ClassVar[dict[int, dict[str, float]]] = {
        0: {"k": 0.30, "d": 0.25, "s": 0.15, "i": 0.30},
        6: {"k": 0.01, "d": 0.01, "s": 0.18, "i": 0.80},
        7: {"k": 0.35, "d": 0.20, "s": 0.10, "i": 0.35},
    }
    DEFAULT_WEIGHTS: ClassVar[dict[str, float]] = {
        "k": 0.25,
        "d": 0.25,
        "s": 0.20,
        "i": 0.30,
    }

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        sorted_vals = sorted(float(v) for v in values)
        idx = q * (len(sorted_vals) - 1)
        lower_idx = int(idx)
        upper_idx = min(lower_idx + 1, len(sorted_vals) - 1)
        frac = idx - lower_idx
        return sorted_vals[lower_idx] * (1 - frac) + sorted_vals[upper_idx] * frac

    @staticmethod
    def _safe_std(values: list[float], mean: float) -> float:
        if len(values) < 2:
            return 0.0
        variance = sum((float(v) - mean) ** 2 for v in values) / float(len(values))
        return variance**0.5

    @staticmethod
    def _safe_ratio(numerator: float, denominator: float) -> float:
        return (
            float(numerator) / float(denominator) if float(denominator) != 0.0 else 0.0
        )

    @staticmethod
    def row_features(row: RatingStatRow) -> dict[str, float]:
        minutes = max(float(row.playtime or 0) / 60.0, 1.0 / 60.0)

        kills_per_min = float(row.kills or 0) / minutes
        deaths_per_min = float(row.deaths or 0) / minutes
        damage_dealt_per_min = float(row.damage_dealt or 0) / minutes
        damage_received_per_min = float(row.damage_received or 0) / minutes
        heals_received_per_min = float(row.heals_received or 0) / minutes
        captures_per_min = float(row.captures or 0) / minutes

        healing_done = float(row.healing_done or 0)
        ubers = float(row.ubers or 0)
        drops = float(row.drops or 0)

        healing_done_per_min = healing_done / minutes
        ubers_per_min = ubers / minutes
        drops_per_min = drops / minutes

        damage_efficiency = RatingService._safe_ratio(
            damage_dealt_per_min, damage_received_per_min
        )
        healing_efficiency = RatingService._safe_ratio(
            damage_received_per_min, heals_received_per_min
        )
        kill_conversion = (
            RatingService._safe_ratio(kills_per_min, damage_dealt_per_min) * 1000.0
        )
        pressure_resistance = -damage_received_per_min

        medic_support_impact = (
            (healing_done_per_min * 0.002)
            + (ubers_per_min * 0.12)
            - (drops_per_min * 0.18)
        )

        return {
            "kills_per_min": kills_per_min,
            "deaths_per_min": deaths_per_min,
            "dpm": float(row.dpm or 0.0),
            "primary_accuracy": float(row.primary_accuracy or 0.0),
            "damage_dealt_per_min": damage_dealt_per_min,
            "damage_received_per_min": damage_received_per_min,
            "heals_received_per_min": heals_received_per_min,
            "captures_per_min": captures_per_min,
            "healing_done_per_min": healing_done_per_min,
            "ubers_per_min": ubers_per_min,
            "drops_per_min": drops_per_min,
            "objective_per_min": captures_per_min,
            "damage_efficiency": damage_efficiency,
            "healing_efficiency": healing_efficiency,
            "kill_conversion": kill_conversion,
            "pressure_resistance": pressure_resistance,
            "medic_support_impact": medic_support_impact,
        }

    @staticmethod
    def _z_score(value: float, mean: float, std: float) -> float:
        if std == 0.0:
            return 0.0
        return (value - mean) / std

    @staticmethod
    def compute_raw_rating(
        class_id: int,
        feature_values: dict[str, float],
        means: dict[str, float],
        stds: dict[str, float],
    ) -> float:
        z: dict[str, float] = {}
        for col in RatingService.FEATURE_COLUMNS:
            z[f"z_{col}"] = RatingService._z_score(
                float(feature_values.get(col, 0.0)),
                float(means.get(col, 0.0)),
                float(stds.get(col, 0.0)),
            )

        z_medic_support_impact = (
            z.get("z_medic_support_impact", 0.0) if class_id == 6 else 0.0
        )
        survival_score = -z.get("z_deaths_per_min", 0.0)

        impact_score = 0.0
        for col, weight in RatingService.IMPACT_WEIGHTS.items():
            impact_score += z.get(col, 0.0) * float(weight)

        weights = RatingService.CLASS_WEIGHTS.get(
            class_id, RatingService.DEFAULT_WEIGHTS
        )
        raw = (
            (z.get("z_kills_per_min", 0.0) * float(weights["k"]))
            + (z.get("z_dpm", 0.0) * float(weights["d"]))
            + (survival_score * float(weights["s"]))
            + (impact_score * float(weights["i"]))
        )

        if class_id == 6:
            raw += z_medic_support_impact * 0.25

        return raw

    @staticmethod
    def normalize_raw_rating(raw_rating: float, p05: float, p95: float) -> float:
        denom = (p95 - p05) if (p95 - p05) != 0.0 else 1.0
        normalized = 0.6 + ((raw_rating - p05) / denom) * 0.8
        return max(0.0, min(2.0, round(normalized, 3)))

    @staticmethod
    def build_class_benchmarks(
        rows: Sequence[RatingStatRow],
    ) -> dict[int, dict[str, Any]]:
        """Recompute per-class baselines from historical MatchStat-equivalent rows."""
        if not rows:
            return {}

        class_feature_rows: dict[int, list[tuple[str, dict[str, float]]]] = defaultdict(
            list
        )
        for row in rows:
            class_feature_rows[int(row.class_id)].append(
                (str(row.steam_id or ""), RatingService.row_features(row))
            )

        benchmarks: dict[int, dict[str, Any]] = {}
        now = utcnow()
        for class_id, entries in class_feature_rows.items():
            feature_means: dict[str, float] = {}
            feature_stds: dict[str, float] = {}

            for col in RatingService.FEATURE_COLUMNS:
                values = [float(feat.get(col, 0.0)) for _pid, feat in entries]
                mean = sum(values) / len(values) if values else 0.0
                std = RatingService._safe_std(values, mean)
                feature_means[col] = float(mean)
                feature_stds[col] = float(std)

            raw_scores: list[float] = []
            player_class_scores: dict[str, list[float]] = defaultdict(list)

            for player_key, features in entries:
                raw = RatingService.compute_raw_rating(
                    class_id, features, feature_means, feature_stds
                )
                raw_scores.append(raw)
                player_class_scores[
                    player_key or f"anon:{len(player_class_scores)}"
                ].append(raw)

            raw_p05 = RatingService._percentile(raw_scores, 0.05)
            raw_p95 = RatingService._percentile(raw_scores, 0.95)

            player_avg_ratings: list[float] = []
            for raw_list in player_class_scores.values():
                normalized = [
                    RatingService.normalize_raw_rating(r, raw_p05, raw_p95)
                    for r in raw_list
                ]
                player_avg_ratings.append(
                    sum(normalized) / len(normalized) if normalized else 1.0
                )

            if player_avg_ratings:
                mean_rating = sum(player_avg_ratings) / len(player_avg_ratings)
                std_rating = RatingService._safe_std(player_avg_ratings, mean_rating)
            else:
                mean_rating = 1.0
                std_rating = 0.0

            benchmarks[class_id] = {
                "class_id": class_id,
                "class_name": class_name_from_id(class_id),
                "sample_size": len(player_avg_ratings),
                "raw_p05": float(raw_p05),
                "raw_p95": float(raw_p95),
                "avg_rating": round(float(mean_rating), 4),
                "std_rating": round(float(std_rating), 4),
                "min_rating": round(min(player_avg_ratings), 4)
                if player_avg_ratings
                else 0.0,
                "max_rating": round(max(player_avg_ratings), 4)
                if player_avg_ratings
                else 0.0,
                "p10_rating": round(
                    RatingService._percentile(player_avg_ratings, 0.10), 4
                ),
                "p25_rating": round(
                    RatingService._percentile(player_avg_ratings, 0.25), 4
                ),
                "p50_rating": round(
                    RatingService._percentile(player_avg_ratings, 0.50), 4
                ),
                "p75_rating": round(
                    RatingService._percentile(player_avg_ratings, 0.75), 4
                ),
                "p90_rating": round(
                    RatingService._percentile(player_avg_ratings, 0.90), 4
                ),
                "metric_means": feature_means,
                "metric_stds": feature_stds,
                "updated_at": now,
            }

        return benchmarks

    @staticmethod
    def score_row(row: RatingStatRow, benchmark: Mapping[str, Any] | None) -> float:
        if not benchmark or int(benchmark.get("sample_size", 0)) < 1:
            return 1.0

        features = RatingService.row_features(row)
        means = dict(benchmark.get("metric_means") or benchmark.get("means") or {})
        stds = dict(benchmark.get("metric_stds") or benchmark.get("stds") or {})
        raw = RatingService.compute_raw_rating(int(row.class_id), features, means, stds)
        return RatingService.normalize_raw_rating(
            raw,
            float(benchmark.get("raw_p05", benchmark.get("p05_raw", 0.0))),
            float(benchmark.get("raw_p95", benchmark.get("p95_raw", 1.0))),
        )

    @staticmethod
    def score_rows(
        rows: Sequence[RatingStatRow],
        benchmark_map: Mapping[int, Mapping[str, Any]],
    ) -> list[float]:
        ratings: list[float] = []
        for row in rows:
            ratings.append(
                RatingService.score_row(row, benchmark_map.get(int(row.class_id)))
            )
        return ratings
