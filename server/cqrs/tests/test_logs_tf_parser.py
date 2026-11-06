"""Unit tests for logs.tf → MatchCommandModel parsing."""

from __future__ import annotations

import json
from pathlib import Path

from cqrs.command_service.app.logs_tf_parser import _primary_accuracy, parse_logs_tf

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "api-consumer"
    / "tests"
    / "fixtures"
    / "logs-tf-4092518.json"
)


def test_primary_accuracy_from_named_weapon_hits_shots():
    acc = _primary_accuracy(
        {
            "type": "scout",
            "weapon": {
                "scattergun": {"shots": 100, "hits": 55, "dmg": 2000},
                "pistol_scout": {"shots": 20, "hits": 5, "dmg": 100},
            },
        }
    )
    # Weighted by shots: (55+5)/(100+20) = 0.5
    assert acc == 0.5


def test_primary_accuracy_ignores_missing_primary_key():
    # Legacy bug looked up weapon.primary.acc which logs.tf never provides.
    acc = _primary_accuracy({"weapon": {"quake_rl": {"shots": 50, "hits": 25}}})
    assert acc == 0.5


def test_parse_logs_tf_reads_player_level_objective_fields():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    match = parse_logs_tf(payload, 4092518)

    with_air = next(p for p in match.players if p.airshots > 0)
    assert with_air.airshots > 0

    with_caps = next(p for p in match.players if p.captures > 0)
    assert with_caps.captures > 0

    with_acc = next(
        p for p in match.players if any(c.primary_accuracy > 0 for c in p.class_stats)
    )
    assert 0 < with_acc.class_stats[0].primary_accuracy <= 1.0

    # Scout with scattergun should get hits/shots accuracy, not 0 from missing weapon.primary.
    scout = next(p for p in match.players if p.display_name == "hezy")
    scout_row = next(c for c in scout.class_stats if c.class_name == "scout")
    assert scout_row.primary_accuracy > 0.5
    assert scout.captures > 0
