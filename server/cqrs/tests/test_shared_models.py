"""Smoke tests for shared.models re-exports."""

from __future__ import annotations

from cqrs.shared import models


def test_shared_models_reexports():
    assert models.MatchCommandModel is not None
    assert models.EventEnvelope is not None
    assert models.RawLogUpload is not None
    assert "MatchCommandModel" in models.__all__
