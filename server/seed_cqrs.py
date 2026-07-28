"""Seed CQRS Postgres databases via the command service (HTTP) or in-process handlers.

Default path (Docker / local microservices):
  docker compose up -d db rabbitmq command-service query-service
  python seed_cqrs.py --http
  # or: docker compose --profile seed run --rm seed

Direct path (no HTTP/RabbitMQ; writes Postgres through in-process handlers):
  python seed_cqrs.py --direct
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

CACHE_FILE = SERVER_DIR / "data" / "seed_logs_cache.json"
COMMAND_SERVICE_URL = os.getenv("COMMAND_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/")
QUERY_SERVICE_URL = os.getenv("QUERY_SERVICE_URL", "http://127.0.0.1:8002").rstrip("/")

HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)
MAX_HTTP_RETRIES = 3
PROJECTION_WAIT_SECONDS = 90
SEED_ACTOR_STEAM_ID = os.getenv("SEED_ACTOR_STEAM_ID", "76561198000000000")


def _seed_auth_headers() -> dict[str, str]:
    """Attach admin credentials for protected command endpoints."""
    service_token = os.getenv("SEED_SERVICE_TOKEN", "").strip()
    if service_token:
        return {"Authorization": f"Bearer {service_token}"}

    from cqrs.shared.auth import UserRole, create_access_token

    token = create_access_token(
        steam_id=SEED_ACTOR_STEAM_ID,
        role=UserRole.ADMIN,
        display_name="Seed Bot",
    )
    return {"Authorization": f"Bearer {token}"}


class CommandServiceUnavailable(Exception):
    pass


def _load_logs(cache_path: Path, limit: int | None) -> list[dict]:
    if not cache_path.exists():
        raise SystemExit(
            f"Cache file not found: {cache_path}\n"
            "Build it first with: python build_seed_cache.py"
        )
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    logs = payload.get("logs", [])
    if limit is not None:
        logs = logs[:limit]
    return logs


def _command_database_url() -> str:
    from cqrs.shared.paths import normalize_async_database_url, postgres_url

    return normalize_async_database_url(
        os.getenv(
            "CQRS_COMMAND_DATABASE_URL",
            os.getenv("CQRS_DATABASE_URL", postgres_url("cqrs_command")),
        )
    )


def _query_database_url() -> str:
    from cqrs.shared.paths import normalize_async_database_url, postgres_url

    return normalize_async_database_url(
        os.getenv("CQRS_QUERY_DATABASE_URL", postgres_url("cqrs_query"))
    )


def _describe_backend(url: str) -> str:
    if "@" in url:
        scheme, rest = url.split("://", 1)
        creds, hostpart = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"postgres ({scheme}://{user}:***@{hostpart})"
    return url


async def _truncate_postgres_database(url: str, label: str) -> int:
    """TRUNCATE all public tables. Safe while services are running."""
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' "
                        "ORDER BY tablename"
                    )
                )
            ).all()
            tables = [name for (name,) in rows]
            if not tables:
                print(f"  {label}: no tables yet (services will create schema on startup)")
                return 0
            quoted = ", ".join(f'"{name}"' for name in tables)
            await connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
            print(f"  {label}: truncated {len(tables)} table(s)")
            return len(tables)
    finally:
        await engine.dispose()


async def _reset_cqrs_databases() -> None:
    command_url = _command_database_url()
    query_url = _query_database_url()
    print("Resetting CQRS Postgres databases:")
    print(f"  command -> {_describe_backend(command_url)}")
    print(f"  query   -> {_describe_backend(query_url)}")

    await _truncate_postgres_database(command_url, "cqrs_command")
    await _truncate_postgres_database(query_url, "cqrs_query")


async def _request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, MAX_HTTP_RETRIES + 1):
        try:
            return await client.request(method, url, **kwargs)
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as exc:
            last_error = exc
            if attempt == MAX_HTTP_RETRIES:
                break
            await asyncio.sleep(attempt)
    assert last_error is not None
    raise last_error


async def _verify_command_service(client: httpx.AsyncClient, url: str) -> None:
    health_url = f"{url}/health"
    for _ in range(30):
        try:
            response = await _request_with_retries(client, "GET", health_url)
            if response.status_code != 200:
                await asyncio.sleep(1)
                continue
            payload = response.json()
            if payload.get("side") != "command":
                raise CommandServiceUnavailable(
                    f"{health_url} responded but side={payload.get('side')!r}; expected 'command'. "
                    f"Check COMMAND_SERVICE_URL (currently {url})."
                )
            probe = await _request_with_retries(
                client,
                "POST",
                f"{url}/api/v1/commands/logs/ingest-cached",
                json={"log_id": 1, "tournament_id": 1, "section": "probe"},
                headers=_seed_auth_headers(),
            )
            # Missing cache entry returns 404 from the handler; missing route returns
            # FastAPI's generic {"detail":"Not Found"} with no richer payload shape.
            # Unauthenticated callers get 401/403 once RBAC is enabled.
            if probe.status_code in {401, 403}:
                detail = ""
                try:
                    detail = str(probe.json().get("detail", ""))
                except Exception:  # noqa: BLE001
                    detail = probe.text
                raise CommandServiceUnavailable(
                    f"Command service rejected seed auth (HTTP {probe.status_code}: {detail}). "
                    "Rebuild images (`docker compose build seed command-service`) and ensure "
                    "JWT_SECRET / SEED_SERVICE_TOKEN match between seed and command-service."
                )
            if probe.status_code == 404:
                detail = ""
                try:
                    detail = str(probe.json().get("detail", ""))
                except Exception:  # noqa: BLE001
                    detail = probe.text
                if detail.strip() in {"", "Not Found"}:
                    raise CommandServiceUnavailable(
                        f"Command service at {url} is running old code without "
                        "/api/v1/commands/logs/ingest-cached. Rebuild/restart it, or run:\n"
                        "  python seed_cqrs.py --direct"
                    )
            print(f"Command service ready at {url}")
            return
        except httpx.HTTPError:
            await asyncio.sleep(1)
    raise CommandServiceUnavailable(
        f"Command service not reachable at {health_url}. "
        "Start it with docker compose or:\n"
        "  uvicorn cqrs.command_service.app.main:app --host 127.0.0.1 --port 8001"
    )


async def _verify_query_service(client: httpx.AsyncClient, url: str) -> None:
    health_url = f"{url}/health"
    for _ in range(30):
        try:
            response = await _request_with_retries(client, "GET", health_url)
            if response.status_code == 200 and response.json().get("side") == "query":
                print(f"Query service ready at {url}")
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    raise SystemExit(
        f"Query service not reachable at {health_url}. "
        "Start it with docker compose or:\n"
        "  uvicorn cqrs.query_service.app.main:app --host 127.0.0.1 --port 8002"
    )


async def _count_query_matches_http(client: httpx.AsyncClient) -> int:
    response = await _request_with_retries(
        client,
        "GET",
        f"{QUERY_SERVICE_URL}/api/v1/queries/matches?limit=100",
    )
    response.raise_for_status()
    return len(response.json())


async def _count_query_matches_direct() -> int:
    from cqrs.query_service.app.db import SessionLocal
    from cqrs.query_service.app.models import MatchSummaryProjection
    from sqlmodel import func, select

    async with SessionLocal() as session:
        return (
            await session.execute(select(func.count()).select_from(MatchSummaryProjection))
        ).scalar_one()


async def _query_service_is_running(client: httpx.AsyncClient) -> bool:
    try:
        response = await client.get(f"{QUERY_SERVICE_URL}/health", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


async def _wait_for_query_projections(
    client: httpx.AsyncClient,
    *,
    target: int,
    timeout_seconds: int = PROJECTION_WAIT_SECONDS,
) -> int:
    """Poll query service until projected match count reaches target."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    current = 0
    while asyncio.get_running_loop().time() < deadline:
        current = await _count_query_matches_http(client)
        if current >= target:
            return current
        await asyncio.sleep(0.5)
    return current


async def seed_http(
    cache_path: Path,
    *,
    limit: int | None = None,
    reset: bool = False,
    allow_direct_fallback: bool = True,
) -> None:
    """Seed through command-service HTTP API; query-service projects via RabbitMQ → Postgres."""
    if reset:
        await _reset_cqrs_databases()

    logs = _load_logs(cache_path, limit)
    print(f"HTTP seed target: command={COMMAND_SERVICE_URL} query={QUERY_SERVICE_URL}")
    print(f"Postgres command DB: {_describe_backend(_command_database_url())}")
    print(f"Postgres query DB:   {_describe_backend(_query_database_url())}")

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            await _verify_command_service(client, COMMAND_SERVICE_URL)
        except (CommandServiceUnavailable, httpx.HTTPError) as exc:
            if not allow_direct_fallback:
                raise SystemExit(str(exc)) from exc
            print(str(exc), file=sys.stderr)
            print("\nFalling back to direct in-process CQRS seed ...", file=sys.stderr)
            await seed_direct(cache_path, limit=limit, reset=False, force=True)
            return

        await _verify_query_service(client, QUERY_SERVICE_URL)

        before = await _count_query_matches_http(client)
        print(f"Query matches before seed: {before}")
        print(f"Seeding {len(logs)} cached logs through {COMMAND_SERVICE_URL} ...")

        accepted = 0
        skipped = 0
        failed = 0
        for index, item in enumerate(logs, start=1):
            body = {
                "log_id": item["log_id"],
                "tournament_id": item["tournament_id"],
                "section": item.get("section", "unknown"),
            }
            try:
                response = await _request_with_retries(
                    client,
                    "POST",
                    f"{COMMAND_SERVICE_URL}/api/v1/commands/logs/ingest-cached",
                    json=body,
                    headers=_seed_auth_headers(),
                )
            except httpx.HTTPError as exc:
                failed += 1
                print(f"  failed log {item['log_id']}: {exc}")
                continue

            if response.status_code != 202:
                failed += 1
                print(
                    f"  failed log {item['log_id']}: "
                    f"HTTP {response.status_code} {response.text[:200]}"
                )
                continue

            result = response.json()
            if result.get("status") == "skipped":
                skipped += 1
            else:
                accepted += 1

            if index % 25 == 0 or index == len(logs):
                print(f"  progress {index}/{len(logs)} (accepted={accepted}, skipped={skipped})")

        target = before + accepted
        after = await _wait_for_query_projections(client, target=target)
        print(
            f"CQRS Postgres seed complete: accepted={accepted}, skipped={skipped}, "
            f"failed={failed}, total={len(logs)}"
        )
        print(f"Query matches after seed: {after}")

        if failed > 0 or (after < target and accepted > 0):
            print(
                "Some commands did not project to the query Postgres DB. "
                "Ensure RabbitMQ is healthy, then retry:\n"
                "  python seed_cqrs.py --http\n"
                "or seed in-process:\n"
                "  python seed_cqrs.py --direct --force"
            )
            raise SystemExit(1)


async def seed_direct(
    cache_path: Path,
    *,
    limit: int | None = None,
    reset: bool = False,
    force: bool = False,
) -> None:
    """Seed in-process using CQRS handlers (writes the same Postgres DBs as the services)."""
    if reset:
        await _reset_cqrs_databases()

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        if not force and await _query_service_is_running(client):
            raise SystemExit(
                "Query service is running on port 8002. Prefer HTTP seeding so RabbitMQ "
                "projections stay consistent:\n"
                "  python seed_cqrs.py --http\n"
                "Or pass --force to write Postgres directly while services are up."
            )

    os.environ.setdefault("CQRS_BROKER_MODE", "memory")
    os.environ.setdefault("SEED_CACHE_PATH", str(cache_path.resolve()))

    from cqrs.command_service.app.db import SessionLocal as CommandSessionLocal, init_write_db
    from cqrs.command_service.app.services import CommandService
    from cqrs.query_service.app.consumer import handle_integration_event
    from cqrs.query_service.app.db import init_read_db
    from cqrs.shared.broker import BROKER
    from cqrs.shared.schemas import CachedLogIngest
    from cqrs.shared.seed_cache import clear_seed_cache_index

    clear_seed_cache_index()
    logs = _load_logs(cache_path, limit)
    print(f"Direct seed using Postgres:")
    print(f"  command -> {_describe_backend(_command_database_url())}")
    print(f"  query   -> {_describe_backend(_query_database_url())}")

    await init_write_db()
    await init_read_db()
    BROKER.subscribe(handle_integration_event)

    before = await _count_query_matches_direct()
    print(f"Direct CQRS seed using in-memory broker ({len(logs)} logs)")
    print(f"Query matches before seed: {before}")

    accepted = 0
    skipped = 0
    for index, item in enumerate(logs, start=1):
        payload = CachedLogIngest(
            log_id=item["log_id"],
            tournament_id=item["tournament_id"],
            section=item.get("section", "unknown"),
        )
        async with CommandSessionLocal() as session:
            result = await CommandService(session).ingest_cached_log(
                payload,
                actor_id=SEED_ACTOR_STEAM_ID,
            )
        if result.get("status") == "skipped":
            skipped += 1
        else:
            accepted += 1
        if index % 25 == 0 or index == len(logs):
            print(f"  progress {index}/{len(logs)} (accepted={accepted}, skipped={skipped})")

    after = await _count_query_matches_direct()
    print(f"CQRS direct seed complete: accepted={accepted}, skipped={skipped}, total={len(logs)}")
    print(f"Query matches after seed: {after}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed CQRS Postgres command/query databases from seed_logs_cache.json",
    )
    parser.add_argument("--cache", type=Path, default=CACHE_FILE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="TRUNCATE CQRS Postgres tables before seeding",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--http",
        action="store_true",
        help="Seed via HTTP to command-service (default; requires RabbitMQ for query projection)",
    )
    mode.add_argument(
        "--direct",
        action="store_true",
        help="Seed in-process via CQRS handlers (writes Postgres directly, no RabbitMQ)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow --direct while query-service is running",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not fall back to --direct when command-service is unreachable",
    )
    args = parser.parse_args()

    if args.direct:
        asyncio.run(
            seed_direct(args.cache, limit=args.limit, reset=args.reset, force=args.force)
        )
    else:
        asyncio.run(
            seed_http(
                args.cache,
                limit=args.limit,
                reset=args.reset,
                allow_direct_fallback=not args.no_fallback,
            )
        )


if __name__ == "__main__":
    main()
