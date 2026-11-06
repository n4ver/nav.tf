# CQRS microservices for TF2 log processing

FastAPI-based CQRS split: a **command service** (write model) and a **query service** (read model / projections). Both persist to **PostgreSQL** via separate databases (`cqrs_command`, `cqrs_query`).

Write sessions and write tables never enter the query API. Read sessions and projection tables never enter the command flow. Only event payloads and shared DTOs cross the boundary.

**Service READMEs:**

- [Command service](command_service/README.md) — write API, auth, ingest
- [Query service](query_service/README.md) — read API, projections, consumer

**System design:** [docs/architecture.md](../../docs/architecture.md)
## Directory structure

```text
cqrs/
  command_service/app/
    auth_service.py    # Steam login upsert + JWT issuance
    db.py              # Write engine / session DI
    dependencies.py    # JWT / Admin RBAC dependencies
    logs_tf_parser.py  # logs.tf JSON -> MatchCommandModel
    main.py            # Write API routes
    models.py          # Write DB tables (RawLogEvent, User, TournamentRecord)
    outbox.py          # Transactional outbox (ordered relay, backoff, requeue)
    outbox_admin.py    # CLI: outbox status / requeue-failed
    outbox_worker.py   # Background outbox relay
    parsers.py         # SRCDS log -> MatchCommandModel
    services.py        # Command handlers
  query_service/app/
    rating/            # Rating service
    consumer.py        # Broker subscriber
    db.py              # Read engine / session DI
    dependencies.py    # Dependencies for query-side
    idempotency.py     # Idempotency handler
    main.py            # Read API routes
    models.py          # Materialized views
    parking.py         # CLI: count / replay parked events
    rating_rebuild.py  # Debounced, coalesced rating rebuild worker
    services.py        # Projection + query handlers
  shared/
    auth/              # Steam OpenID, JWT, UserRole
    broker.py          # RabbitMQ + in-memory fallback
    cors.py            # CORS Middleware
    events.py          # Integration event envelopes
    models.py          # Backwards Compatibility
    paths.py           # CQRS Data helpers
    schemas.py         # Cross-boundary DTOs
    seed_cache.py      # Load local cache for DB seeding
    steam.py           # Steam helpers
    tf2_classes.py     # TF2-specific logic
    timeutils.py       # UTC datetime helpers for Postgres
    tournaments.py     # TODO: Remove
  tests/
```

## Authentication & RBAC

Steam OpenID login lives on the command service:

- `GET /api/v1/auth/steam/login` — redirect to Steam
- `GET /api/v1/auth/steam/callback` — validate assertion, upsert `User`, redirect to frontend with JWT
- `GET /api/v1/auth/me` — current user profile (Bearer token)

Mutating command endpoints require an **ADMIN** JWT (`get_current_admin_user`):

- `POST /api/v1/commands/logs/upload`
- `POST /api/v1/commands/logs/ingest-cached`
- `POST /api/v1/commands/players/display-name`
- `POST /api/v1/commands/tournaments`
- `PATCH /api/v1/commands/tournaments/{tournament_id}`

Set `JWT_SECRET`, `FRONTEND_URL`, `STEAM_OPENID_REALM`, `STEAM_OPENID_RETURN_TO`, optional `BOOTSTRAP_ADMIN_STEAM_IDS`, and `STEAM_API_KEY` (persona/avatar lookup on login).

For local dev, open the site at **`http://localhost:5173`** (not HTTPS). Steam OpenID `return_to` must match that origin — defaults are `http://localhost:5173/api/auth/steam/callback` (Vite proxies `/api/auth` to the command service). If Steam redirects to `https://localhost:8001` you will see `ERR_SSL_PROTOCOL_ERROR` because the command service speaks HTTP only.

**Seeding after auth:** mutating command endpoints require admin credentials. Docker seeding uses a shared `SEED_SERVICE_TOKEN` (must match on `seed` and `command-service`). Rebuild images after auth changes:

```bash
docker compose build seed command-service
docker compose up -d command-service
docker compose --profile seed run --rm seed
```

## Prerequisites

- Python 3.11+
- Docker (Postgres + RabbitMQ) or local equivalents
- Dependencies from [server/requirements.txt](../requirements.txt)

```bash
cd server
python -m pip install -r requirements.txt
python -m pip install pytest
```

## Run with Docker (recommended)

```bash
cd server
docker compose up -d db rabbitmq command-service query-service
```

Postgres credentials: `user` / `password` on port `5432`. The `db-init` service creates `cqrs_command` and `cqrs_query` automatically.

## Run locally

Start Postgres and RabbitMQ first:

```bash
cd server
docker compose up -d db rabbitmq
```

Then run each service:

```bash
uvicorn cqrs.command_service.app.main:app --host 127.0.0.1 --port 8001 --reload
uvicorn cqrs.query_service.app.main:app --host 127.0.0.1 --port 8002 --reload
```

## Environment

| Variable | Purpose | Default |
|---|---|---|
| `CQRS_COMMAND_DATABASE_URL` | Write DB | `postgresql+asyncpg://user:password@127.0.0.1:5432/cqrs_command` |
| `CQRS_QUERY_DATABASE_URL` | Read DB | `postgresql+asyncpg://user:password@127.0.0.1:5432/cqrs_query` |
| `CQRS_POSTGRES_HOST` | Postgres host (URL builder) | `127.0.0.1` |
| `CQRS_POSTGRES_PORT` | Postgres port | `5432` |
| `CQRS_POSTGRES_USER` | Postgres user | `user` |
| `CQRS_POSTGRES_PASSWORD` | Postgres password | `password` |
| `RABBITMQ_URL` | Event broker | `amqp://guest:guest@localhost:5672/` |
| `CQRS_BROKER_MODE` | Set to `memory` for tests / direct seed | unset |
| `SEED_CACHE_PATH` | Path to seed_logs_cache.json | `server/data/seed_logs_cache.json` |

Inside Docker Compose, host is `db` instead of `127.0.0.1`.

Tests use dedicated Postgres databases: `cqrs_command_test` and `cqrs_query_test`.

## API examples

**Command service** (`:8001`):

```bash
# Upload a raw log
curl -X POST http://127.0.0.1:8001/api/v1/commands/logs/upload \
  -H "Content-Type: application/json" \
  -d '{
    "log_data": "map_name=cp_process_final blu_score=2 red_score=1 player steam_id=STEAM_1:1:12345 team=blu class=scout kills=10 deaths=5 assists=2 dpm=350 healing=0",
    "timestamp": "2026-07-28T00:00:00Z"
  }'

# Ingest from seed cache by logs.tf ID
curl -X POST http://127.0.0.1:8001/api/v1/commands/logs/ingest-cached \
  -H "Content-Type: application/json" \
  -d '{"log_id": 4037391, "tournament_id": 2, "section": "R8"}'
```

**Query service** (`:8002`):

```bash
curl http://127.0.0.1:8002/api/v1/queries/matches
curl http://127.0.0.1:8002/api/v1/queries/matches/<match_id>
curl http://127.0.0.1:8002/api/v1/queries/players/STEAM_1:1:12345/stats
curl "http://127.0.0.1:8002/api/v1/queries/tournaments/<tournament_id>/leaderboard"
curl "http://127.0.0.1:8002/api/v1/queries/search?q=4037391"
curl http://127.0.0.1:8002/api/v1/queries/benchmarks/class-rating
curl http://127.0.0.1:8002/health
```

## Seeding Postgres

Seeding sends cached log metadata through the command service. RabbitMQ delivers `MatchParsed` events to the query service, which projects into Postgres.

### HTTP seed (default — matches production flow)

```bash
cd server
docker compose up -d db rabbitmq command-service query-service

python dev-setup/seed/seed_cqrs.py --http              # seed all cached logs
python dev-setup/seed/seed_cqrs.py --http --reset      # truncate tables, then seed
python dev-setup/seed/seed_cqrs.py --http --limit 10   # seed first 10 logs
```

One-shot via Docker:

```bash
docker compose --profile seed run --rm seed
```

With reset:

```bash
docker compose --profile seed run --rm seed \
  python dev-setup/seed/seed_cqrs.py --http --reset --no-fallback
```

### Direct seed (in-process, no RabbitMQ)

Writes to the same Postgres databases through CQRS handlers with an in-memory broker:

```bash
python dev-setup/seed/seed_cqrs.py --direct
python dev-setup/seed/seed_cqrs.py --direct --reset
```

Stop the query service first, or pass `--force` if it is already running.

### Building the seed cache

```bash
python dev-setup/seed/build_seed_cache.py              # fetch from logs.tf + write cache
python dev-setup/seed/build_seed_cache.py --skip-fetch   # rebuild manifest from existing cache
```

Source log IDs come from [invite.txt](../dev-setup/seed/invite.txt).

### Reset behavior

`--reset` runs `TRUNCATE ... RESTART IDENTITY CASCADE` on all tables in `cqrs_command` and `cqrs_query`. This is safe while services are running.

## Rating pipeline

`MatchParsed` player payloads include nested `class_stats` (`ClassStatSnapshot`) with the full MatchStat/MedicStat field set used by the legacy notebook rating model.

On the query side, `PlayerMatchClassStatsProjection` stores per-class rows. Each projection requests a rebuild. The debounced worker in `rating_rebuild.py` then runs `ProjectionService.rebuild_ratings()` once per burst of events: it rebuilds the `ClassRatingBenchmarkProjection` baselines and scores every class row via `query_service/app/rating/RatingService`. Read APIs return precomputed ratings only, and `ratings_ready` is false until the rebuild covering that match finishes. See [docs/architecture.md](../../docs/architecture.md#rating-pipeline).

## Event contract

After a raw log is committed on the write side, the command service publishes:

1. **`MatchParsed`** — parsed match summary, tournament metadata, and player snapshots
2. **`LogEventCreated`** — acknowledgment that the raw log row was persisted

The query consumer listens on queue `cqrs-query` (topic `events.#`) and upserts:

- `match_summary_view`
- `player_match_stats_view`
- `player_match_class_stats_view`
- `player_lifetime_stats_view`
- `class_rating_benchmark_view`

## Tests

```bash
cd server
python -m pytest cqrs/tests -q
```

Tests require Docker Postgres with `cqrs_command_test` and `cqrs_query_test` databases (`docker compose up -d db db-init`).
Test database init scripts are under `server/cqrs/tests/postgres/`.
