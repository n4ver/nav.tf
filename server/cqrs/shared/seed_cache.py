"""Load logs.tf payloads from the local seed cache file."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import SERVER_ROOT

DEFAULT_SEED_CACHE_PATH = SERVER_ROOT / "data" / "seed_logs_cache.json"


def seed_cache_path() -> Path:
    configured = os.getenv("SEED_CACHE_PATH")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else SERVER_ROOT / path
    return DEFAULT_SEED_CACHE_PATH


@lru_cache(maxsize=1)
def _load_index(cache_file: str) -> dict[int, dict[str, Any]]:
    path = Path(cache_file)
    if not path.exists():
        raise FileNotFoundError(f"Seed cache not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    index: dict[int, dict[str, Any]] = {}
    for item in payload.get("logs", []):
        index[int(item["log_id"])] = item["data"]
    return index


def get_cached_log_data(
    log_id: int, *, cache_path: Path | None = None
) -> dict[str, Any]:
    path = cache_path or seed_cache_path()
    index = _load_index(str(path.resolve()))
    try:
        return index[log_id]
    except KeyError as exc:
        raise KeyError(f"log_id {log_id} not found in seed cache {path}") from exc


def clear_seed_cache_index() -> None:
    _load_index.cache_clear()
