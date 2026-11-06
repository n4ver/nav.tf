"""Build a cached JSON seed file from dev-setup/seed/invite.txt log IDs.

Fetches each log payload from logs.tf and writes server/data/seed_logs_cache.json
for offline database seeding without repeated API calls.

After building the cache, seed the CQRS Postgres databases:

    docker compose up -d db rabbitmq command-service query-service
    python dev-setup/seed/seed_cqrs.py --http
    # or: docker compose --profile seed run --rm seed

Usage:
    cd server
    python dev-setup/seed/build_seed_cache.py
    python dev-setup/seed/build_seed_cache.py --skip-fetch
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEV_SETUP_DIR = Path(__file__).resolve().parent
SERVER_ROOT = DEV_SETUP_DIR.parents[1]
INVITE_FILE = DEV_SETUP_DIR / "invite.txt"
CACHE_FILE = SERVER_ROOT / "data" / "seed_logs_cache.json"
LOGS_TF_API = "https://logs.tf/json"
CACHE_VERSION = 1
FETCH_CONCURRENCY = 2
REQUEST_DELAY_SECONDS = 1.25
MAX_RETRIES = 5

TOURNAMENT_MAP = {
    "invite": 1,
    "qualifiers": 2,
    "R8": 2,
    "R7": 2,
    "R6": 2,
    "R5": 2,
    "R4": 2,
    "R3": 2,
    "R2": 2,
    "R1": 2,
    "main": 3,
}


def parse_invite_entries(filepath: Path) -> list[dict[str, Any]]:
    """Parse invite.txt into log entries with tournament and section metadata."""
    entries: list[dict[str, Any]] = []
    current_tournament = 1
    current_section = "invite"

    for raw_line in filepath.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in TOURNAMENT_MAP:
            current_tournament = TOURNAMENT_MAP[line]
            current_section = line
            continue
        if line.startswith("http://"):
            import re

            match = re.search(r"/ingest/(\d+)", line)
            if match:
                entries.append(
                    {
                        "log_id": int(match.group(1)),
                        "tournament_id": current_tournament,
                        "section": current_section,
                    }
                )
        elif line.isdigit():
            entries.append(
                {
                    "log_id": int(line),
                    "tournament_id": current_tournament,
                    "section": current_section,
                }
            )

    return entries


async def _fetch_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    entry: dict[str, Any],
) -> dict[str, Any]:
    log_id = entry["log_id"]
    async with semaphore:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
                response = await client.get(f"{LOGS_TF_API}/{log_id}")
                if response.status_code == 429:
                    retry_after = float(
                        response.headers.get("Retry-After", min(2**attempt, 30))
                    )
                    await asyncio.sleep(retry_after)
                    continue
                if response.status_code != 200:
                    return {
                        **entry,
                        "fetch_status": "failed",
                        "http_status": response.status_code,
                        "error": f"HTTP {response.status_code}",
                    }
                return {
                    **entry,
                    "fetch_status": "ok",
                    "data": response.json(),
                }
            except Exception as exc:
                if attempt == MAX_RETRIES:
                    return {
                        **entry,
                        "fetch_status": "failed",
                        "error": str(exc),
                    }
                await asyncio.sleep(min(2**attempt, 30))
        return {
            **entry,
            "fetch_status": "failed",
            "http_status": 429,
            "error": "HTTP 429 after retries",
        }


async def fetch_logs(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for entry in entries:
            results.append(await _fetch_one(client, semaphore, entry))
    return results


def build_cache(
    entries: list[dict[str, Any]], fetched: list[dict[str, Any]]
) -> dict[str, Any]:
    ok_logs = [item for item in fetched if item.get("fetch_status") == "ok"]
    failures = [
        {
            "log_id": item["log_id"],
            "tournament_id": item["tournament_id"],
            "section": item["section"],
            "http_status": item.get("http_status"),
            "error": item.get("error", "unknown error"),
        }
        for item in fetched
        if item.get("fetch_status") != "ok"
    ]

    sections: dict[str, int] = {}
    tournaments: dict[str, int] = {}
    for item in ok_logs:
        sections[item["section"]] = sections.get(item["section"], 0) + 1
        tournaments[str(item["tournament_id"])] = (
            tournaments.get(str(item["tournament_id"]), 0) + 1
        )

    return {
        "version": CACHE_VERSION,
        "source_file": str(INVITE_FILE.relative_to(SERVER_ROOT)),
        "generated_at": datetime.now(UTC).isoformat(),
        "api_base": LOGS_TF_API,
        "summary": {
            "requested": len(entries),
            "cached": len(ok_logs),
            "failed": len(failures),
            "by_section": sections,
            "by_tournament_id": tournaments,
        },
        "logs": [
            {
                "log_id": item["log_id"],
                "tournament_id": item["tournament_id"],
                "section": item["section"],
                "data": item["data"],
            }
            for item in ok_logs
        ],
        "failures": failures,
    }


def load_existing_payloads(cache_path: Path) -> dict[int, dict[str, Any]]:
    if not cache_path.exists():
        return {}
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    return {
        item["log_id"]: item["data"]
        for item in payload.get("logs", [])
        if "data" in item
    }


async def main(skip_fetch: bool) -> None:
    if not INVITE_FILE.exists():
        raise SystemExit(f"Missing invite file: {INVITE_FILE}")

    entries = parse_invite_entries(INVITE_FILE)
    if not entries:
        raise SystemExit("No log IDs found in invite.txt")

    existing = load_existing_payloads(CACHE_FILE) if skip_fetch else {}

    if skip_fetch:
        fetched = []
        for entry in entries:
            data = existing.get(entry["log_id"])
            if data is None:
                fetched.append(
                    {
                        **entry,
                        "fetch_status": "failed",
                        "error": "missing from existing cache",
                    }
                )
            else:
                fetched.append({**entry, "fetch_status": "ok", "data": data})
    else:
        existing = load_existing_payloads(CACHE_FILE)
        pending = [entry for entry in entries if entry["log_id"] not in existing]
        print(
            f"Fetching {len(pending)} logs from logs.tf ({len(existing)} already cached) ..."
        )
        fetched_pending = await fetch_logs(pending) if pending else []
        fetched_by_id = {item["log_id"]: item for item in fetched_pending}
        fetched = []
        for entry in entries:
            log_id = entry["log_id"]
            if log_id in existing:
                fetched.append(
                    {**entry, "fetch_status": "ok", "data": existing[log_id]}
                )
                continue
            item = fetched_by_id.get(log_id)
            if item is None:
                fetched.append(
                    {**entry, "fetch_status": "failed", "error": "not fetched"}
                )
            elif item.get("fetch_status") != "ok" and log_id in existing:
                fetched.append(
                    {**entry, "fetch_status": "ok", "data": existing[log_id]}
                )
            else:
                fetched.append(item)

    cache = build_cache(entries, fetched)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    summary = cache["summary"]
    print(f"Wrote {CACHE_FILE}")
    print(
        f"Cached {summary['cached']}/{summary['requested']} logs "
        f"({summary['failed']} failures)"
    )
    if cache["failures"]:
        print("Failures:")
        for failure in cache["failures"]:
            print(f"  - {failure['log_id']}: {failure['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build seed_logs_cache.json from invite.txt"
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Reuse payloads already present in seed_logs_cache.json",
    )
    args = parser.parse_args()
    asyncio.run(main(skip_fetch=args.skip_fetch))
