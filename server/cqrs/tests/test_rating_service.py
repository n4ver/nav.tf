"""Unit tests for the CQRS RatingService port (monolith parity)."""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER_ROOT))

from cqrs.shared.rating import (  # noqa: E402
    RatingService,
    class_id_from_name,
    rating_row_from_mapping,
)


def test_feature_columns_match_monolith():
    assert RatingService.FEATURE_COLUMNS == [
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
    assert RatingService.CLASS_WEIGHTS[6]["i"] == 0.80
    assert class_id_from_name("medic") == 6


def test_row_features_and_benchmark_scoring_are_deterministic():
    rows = [
        rating_row_from_mapping(
            {
                "steam_id": "A",
                "class_id": 0,
                "playtime_seconds": 1500,
                "kills": 14,
                "deaths": 4,
                "dpm": 320.0,
                "primary_accuracy": 0.4,
                "damage_dealt": 8000,
                "damage_received": 4000,
                "heals_received": 3000,
                "captures": 2,
            }
        ),
        rating_row_from_mapping(
            {
                "steam_id": "B",
                "class_id": 0,
                "playtime_seconds": 1500,
                "kills": 6,
                "deaths": 10,
                "dpm": 180.0,
                "primary_accuracy": 0.2,
                "damage_dealt": 4500,
                "damage_received": 5200,
                "heals_received": 2800,
                "captures": 0,
            }
        ),
        rating_row_from_mapping(
            {
                "steam_id": "C",
                "class_id": 6,
                "playtime_seconds": 1500,
                "kills": 1,
                "deaths": 3,
                "dpm": 20.0,
                "primary_accuracy": 0.0,
                "damage_dealt": 500,
                "damage_received": 2000,
                "heals_received": 500,
                "captures": 0,
                "healing_done": 18000,
                "ubers": 8,
                "drops": 1,
            }
        ),
    ]

    features = RatingService.row_features(rows[0])
    assert set(RatingService.FEATURE_COLUMNS).issubset(features)
    assert features["objective_per_min"] == features["captures_per_min"]
    assert features["medic_support_impact"] == 0.0

    medic_features = RatingService.row_features(rows[2])
    assert medic_features["healing_done_per_min"] > 0
    assert medic_features["ubers_per_min"] > 0

    benchmarks = RatingService.build_class_benchmarks(rows)
    assert 0 in benchmarks
    assert 6 in benchmarks
    assert "metric_means" in benchmarks[0]
    assert "raw_p05" in benchmarks[0]
    assert benchmarks[0]["sample_size"] == 2

    high = RatingService.score_row(rows[0], benchmarks[0])
    low = RatingService.score_row(rows[1], benchmarks[0])
    assert 0.0 <= low <= 2.0
    assert 0.0 <= high <= 2.0
    assert high >= low

    # Same inputs must reproduce the same rating.
    assert RatingService.score_row(rows[0], benchmarks[0]) == high
