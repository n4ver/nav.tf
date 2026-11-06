"""Unit tests for seed cache loading."""

from __future__ import annotations

import json

import pytest

from cqrs.shared.seed_cache import (
    clear_seed_cache_index,
    get_cached_log_data,
    seed_cache_path,
)


def test_get_cached_log_data_reads_entry(tmp_path):
    cache_file = tmp_path / "seed_logs_cache.json"
    cache_file.write_text(
        json.dumps({"logs": [{"log_id": 9001, "data": {"info": {"map": "cp_test"}}}]}),
        encoding="utf-8",
    )
    clear_seed_cache_index()

    data = get_cached_log_data(9001, cache_path=cache_file)
    assert data["info"]["map"] == "cp_test"


def test_get_cached_log_data_missing_log_raises(tmp_path):
    cache_file = tmp_path / "seed_logs_cache.json"
    cache_file.write_text(json.dumps({"logs": []}), encoding="utf-8")
    clear_seed_cache_index()

    with pytest.raises(KeyError, match="9002"):
        get_cached_log_data(9002, cache_path=cache_file)


def test_get_cached_log_data_missing_file_raises(tmp_path):
    clear_seed_cache_index()
    missing = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        get_cached_log_data(1, cache_path=missing)


def test_seed_cache_path_honors_relative_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SEED_CACHE_PATH", "custom/cache.json")
    path = seed_cache_path()
    assert path.name == "cache.json"
    assert "custom" in str(path)
