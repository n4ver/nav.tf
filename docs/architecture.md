# TF2 Analytics — Architecture Design

This document describes the system architecture for TF2 Analytics: a platform that ingests competitive Team Fortress 2 match logs, computes per-class ratings, and serves tournament, match, and player views through a Vue dashboard.

## Design goals

| Goal | Approach |
|---|---|
| Separate read and write concerns | CQRS command/query split with independent Postgres databases |
| Fast dashboard queries | Precomputed read-model projections and leaderboard snapshots |
| Extensible ingestion | Pluggable source adapters (logs.tf, matcha.tf) via command HTTP or event bus |
| Auditability | Raw log events persisted on the write side; integration events on RabbitMQ |
| Admin operations | Steam OpenID + JWT with role-based access on mutating endpoints |

## System context

```text
                         ┌─────────────────────────────────────────────────────────┐
                         │                    External sources                        │
                         │   logs.tf API          matcha.tf API         Steam OpenID  │
                         └────────────┬───────────────────┬─────────────────┬─────────┘
                                      │                   │                 │
                                      ▼                   ▼                 ▼
┌──────────────┐   HTTP read/write   ┌──────────────┐   events   ┌──────────────┐
│  Vue Web     │◄───────────────────►│   Command    │───────────►│   RabbitMQ   │
│  :5173       │                     │   :8001      │            │  tf2-events  │
└──────┬───────┘                     └──────┬───────┘            └──────┬───────┘
       │ HTTP read                        │ write DB                     │ consume
       ▼                                  ▼                              ▼
┌──────────────┐                     ┌──────────────┐            ┌──────────────┐
│   Query      │◄────────────────────│ cqrs_command │            │   Query      │
│   :8002      │      read DB        │  (Postgres)  │            │   consumer   │
└──────────────┘                     └──────────────┘            └──────┬───────┘
       ▲                                                                  │
       │ read DB                                                          ▼
┌──────────────┐                                                   ┌──────────────┐
│ cqrs_query   │◄──────────────────────────────────────────────────│ cqrs_query   │
│  (Postgres)  │         projection upserts                      │  (Postgres)  │
└──────────────┘                                                   └──────────────┘

       ┌──────────────┐
       │ api-consumer │─── publishes MatchParsed directly ─────────► RabbitMQ
       │   :8010      │    (bypasses command write DB)
       └──────────────┘
```

## Service inventory

| Service | Path | Port | Database | Role |
|---|---|---|---|---|
| **Web dashboard** | `web/` | 5173 | — | SPA; proxies to command (writes/auth) and query (reads) |
| **Command service** | `server/cqrs/command_service/` | 8001 | `cqrs_command` | Write model, auth, log ingest, event publish |
| **Query service** | `server/cqrs/query_service/` | 8002 | `cqrs_query` | Read model, projections, leaderboards, search |
| **API consumer** | `api-consumer/` | 8010 | — | External auto-ingest (matcha.tf → logs.tf → RabbitMQ) |

Shared infrastructure runs via `server/dev-setup/docker/docker-compose.yml` (included from `server/docker-compose.yml`): **Postgres 15** (port 5432) and **RabbitMQ 3.11** (AMQP 5672, management UI 15672).

## CQRS boundaries

### Write model (command side)

The command service owns all mutations:

- **Tables:** `raw_log_events`, `users`, `tournaments`, `events`, `outbox_events`
- **Responsibilities:** parse SRCDS text or logs.tf JSON, persist raw events, upsert users/tournaments/events, publish integration events
- **Never exposes:** projection tables or precomputed ratings

### Read model (query side)

The query service owns all reads and projections:

- **Tables:** `match_summary_view`, `player_match_stats_view`, `player_match_class_stats_view`, `player_lifetime_stats_view`, `class_rating_benchmark_view`, `leaderboard_snapshot_view`, `tournament_summary_view`, etc.
- **Responsibilities:** consume events, upsert projections, rebuild ratings, serve HTTP queries
- **Never exposes:** raw log payloads or write-side tables

### Shared code (`server/cqrs/shared/`)

Cross-boundary DTOs and utilities only — no database session imports:

- `events.py` — integration event envelopes
- `schemas.py` — API request/response DTOs
- `broker.py` — RabbitMQ publisher/consumer + in-memory test fallback
- `tf2_classes.py` — TF2 class names/ids shared by parsers and ratings

Rating math lives on the query side in `query_service/app/rating/` (ported from the legacy notebook).
- `auth/` — Steam OpenID, JWT, roles

## Data flow

### Path A — Admin / seed ingest (canonical write path)

```text
Admin upload or seed_cqrs.py
        │
        ▼
POST /api/v1/commands/logs/*  (command :8001)
        │
        ├──► INSERT raw_log_events, tournaments  (cqrs_command)
        │
        └──► PUBLISH MatchParsed, LogEventCreated  (RabbitMQ)
                    │
                    ▼
             Query consumer  (queue: cqrs-query, binding: events.#)
                    │
                    ├──► Upsert match/player projections
                    │
                    └──► request rating rebuild → debounced worker rescores, refreshes leaderboards
                    │
                    ▼
             GET /api/v1/queries/*  (query :8002)  ◄── Web dashboard
```

**Match IDs** are deterministic UUIDv5 values: `uuid5(NAMESPACE_URL, "logs.tf:{logstf_id}")`. The web app accepts legacy `/match-log/:logId` URLs and resolves them via search.

### Path B — API consumer (event-only ingest)

```text
node-cron poll  OR  POST /webhooks/matcha/match
        │
        ▼
MatchaAdapter  →  logs.tf enrichment  →  normalize
        │
        └──► PUBLISH MatchParsed  (RabbitMQ, no command DB write)
                    │
                    └──► Query projections (same as Path A from here)
```

The api-consumer path **intentionally bypasses the command write model**. Match data lands directly in query projections. A secondary `MatchLogIngested` audit event records provenance (`sourceSite`, `correlationId`). Operators who need a full audit trail in `raw_log_events` should ingest via the command service instead.

## Event contract

Exchange: **`tf2-events`** (topic, durable). Queue: **`cqrs-query`** bound to routing key `events.#`.

| Event | Publisher | Consumer action |
|---|---|---|
| `MatchParsed` | Command, api-consumer | Upsert match/player projections; request a coalesced rating rebuild (see [Rating pipeline](#rating-pipeline)) |
| `LogEventCreated` | Command | Acknowledgment (query may log; no projection change) |
| `PlayerAliasUpdated` | Command | Update player identity projection |
| `TournamentCreated` / `TournamentUpdated` | Command | Upsert tournament summary |
| `EventCreated` / `EventUpdated` | Command | Upsert event summary |
| `TournamentLinkedToEvent` | Command | Set tournament.event_id; rewrite event tournament list; rebuild event player stats |
| `MatchTournamentAssigned` | Command | Move match to a tournament; recount; refresh leaderboards and event stats |
| `MatchLogIngested` | api-consumer | Audit/provenance (optional) |
| `RatingsRebuildRequested` / `RatingsRebuilt` | Legacy | Kept for in-flight messages only; treated as a rebuild request |

Event envelope shape (`server/cqrs/shared/events.py`):

```json
{
  "event_id": "uuid",
  "event_type": "MatchParsed",
  "occurred_at": "2026-07-28T00:00:00Z",
  "actor_id": "STEAM_1:0:12345",
  "payload": { "...": "..." }
}
```

Dead-letter exchange **`tf2-events.dlx`** handles exhausted retries from api-consumer (`failed.#` routing keys).

### Delivery guarantees

**Command → broker (transactional outbox).** Events are written to `outbox_events` in the same transaction as the domain change, then relayed by the command service (a post-commit kick plus a background worker).

- A Postgres advisory lock allows one relayer at a time, across workers and replicas.
- Rows publish in `id` (commit) order. If the head row fails or is still backing off, the relay stops, so later events never overtake it.
- Failed publishes retry with exponential backoff (`OUTBOX_RETRY_BASE_MS` doubling up to `OUTBOX_RETRY_MAX_MS`). After `OUTBOX_MAX_ATTEMPTS` the row is marked `failed` so it stops blocking the queue. Rows with an unreadable payload are failed immediately.
- Inspect and recover with `python -m cqrs.command_service.app.outbox_admin status|requeue-failed`.

**Broker → query (idempotent consumer).** Each delivery is handled in one read-DB transaction that first claims its `event_id` in `processed_events`. Only a conflict on that claim counts as a duplicate; any other error rolls back and is retried.

- Retries happen in place, with the message unacked and backoff from `CQRS_CONSUMER_RETRY_BASE_MS` up to `CQRS_CONSUMER_RETRY_MAX_MS`, so order is preserved.
- After `CQRS_CONSUMER_MAX_ATTEMPTS` the message moves to **`cqrs-query.parking`** with `x-error` / `x-attempts` headers instead of being dropped. Malformed messages are parked immediately.
- Infrastructure errors (database or network unreachable) don't count toward that limit. They retry indefinitely with capped backoff, so an outage pauses the queue instead of draining it into parking.
- Replay with `python -m cqrs.query_service.app.parking count|replay`.
- Handlers fail loudly when an event depends on state that is missing. For example, `MatchTournamentAssigned` for an unprojected match fails and ends up parked rather than being acked.

## Authentication and authorization

Steam OpenID login runs on the command service:

1. Browser → `GET /api/v1/auth/steam/login` → redirect to Steam
2. Steam → `GET /api/v1/auth/steam/callback` → validate, upsert `User`, issue JWT
3. Frontend stores JWT; sends `Authorization: Bearer <token>` on mutating requests
4. `GET /api/v1/auth/me` returns current user profile

**Admin-only** endpoints (require `ADMIN` role JWT):

- All `POST/PATCH /api/v1/commands/*` routes
- Web admin nested under `/admin` (ingest, events, tournaments, matches, players)

Bootstrap first admins via `BOOTSTRAP_ADMIN_STEAM_IDS`. Seeding scripts authenticate with `SEED_SERVICE_TOKEN` (must match on command service and seed container).

Query endpoints are **unauthenticated** (public read API).

## Database layout

Single Postgres instance, multiple logical databases:

| Database | Purpose |
|---|---|
| `cqrs_command` | Write model (Postgres default database) |
| `cqrs_query` | Read projections |
| `cqrs_command_test` / `cqrs_query_test` | pytest isolation |

Init scripts: `server/dev-setup/docker/postgres/init-cqrs-databases.sql` (first boot) and `ensure-cqrs-databases.sh` (idempotent via `db-init` service). Test DBs: `server/cqrs/tests/postgres/`.

## Rating pipeline

Ratings are **never computed at request time** on the query API. Class rows are scored against benchmarks computed over *every* class row, so each new match moves every rating. The rebuild is therefore global, but it runs once per burst of events rather than once per event:

1. `MatchParsed` upserts the match, player and class projections (`ratings_ready = false` for that match) and bumps `rating_rebuild_state.request_seq`.
2. The query service's rebuild worker (`query_service/app/rating_rebuild.py`) waits until events have been quiet for `RATING_REBUILD_DEBOUNCE_MS` (default 2 s), or `RATING_REBUILD_MAX_DELAY_MS` (default 30 s) after the first pending request. It then takes an advisory lock and, in one transaction:
   - rebuilds `ClassRatingBenchmarkProjection` and rescores every class, match and lifetime row (`RatingService`, `query_service/app/rating/service.py`)
   - marks the matches that were pending as `ratings_ready = true`
   - refreshes **all** tournament leaderboards and event player stats, since every rating may have changed
3. Steam persona names are resolved after that commit, outside the transaction.

Requests that arrive during a rebuild leave `request_seq > completed_seq`, so another run follows. The web admin already polls `ratings_ready` after an ingest. On startup the worker queues a rebuild if any match is still unrated.

`RATING_REBUILD_MODE=inline` runs the same rebuild synchronously after each event. This is the default with `CQRS_BROKER_MODE=memory`, which tests and the in-process seed use. `deferred` is the default otherwise.

The `RatingsRebuildRequested` / `RatingsRebuilt` events are legacy compatibility only and are no longer published.

## Deployment topology

### Local development (recommended)

```bash
cd server
docker compose up -d db rabbitmq command-service query-service
python dev-setup/seed/seed_cqrs.py --http

cd ../web && npm install && npm run dev
```

Optional external ingest:

```bash
docker compose --profile consumer up -d api-consumer
```

### Docker Compose profiles

| Profile | Services added |
|---|---|
| *(default)* | `db`, `db-init`, `rabbitmq`, `command-service`, `query-service`, `web` |
| `consumer` | `api-consumer` |
| `seed` | One-shot `seed` container |

### Production (Google Cloud)

Production runs the same services on one Compute Engine VM with [`deploy/compose.prod.yml`](../deploy/compose.prod.yml). Caddy terminates TLS and serves the built SPA. It maps `/api/command|auth|query/` to the services' internal `/api/v1/...` routes, mirroring the dev nginx gateway. Postgres and RabbitMQ run as containers on persistent volumes, protected by daily disk snapshots. Only ports 80/443 are public, and SSH goes through IAP only.

GitHub Actions builds the images into Artifact Registry and deploys over IAP using Workload Identity Federation. Secrets live in Secret Manager. With `APP_ENV=production`, the services refuse to start with development secrets or credentials (`server/cqrs/shared/settings.py`).

Setup, operations, cost and teardown are covered in **[deploy/README.md](../deploy/README.md)**.

Known limits of the single-VM setup:
- No HA: one VM, with Postgres and RabbitMQ on the same host. Recovery is by snapshot restore.
- Moving to Cloud SQL, or to a managed or clustered broker, is mostly a matter of changing the database and broker URLs.

## Technology stack

| Layer | Technologies |
|---|---|
| Frontend | Vue 3, Vue Router, Pinia, Axios, Tailwind CSS 4, Vite 8, Vitest |
| Command / Query | Python 3.12, FastAPI, SQLModel, SQLAlchemy 2, asyncpg, aio-pika, PyJWT, httpx |
| API consumer | Node 20, Express, amqplib, node-cron, opossum, pino, Jest |
| Infrastructure | Docker Compose, Postgres 15, RabbitMQ 3.11 |
| Experiments | Jupyter (`classifier/`) |

## Related documentation

- [Root README](../README.md) — quick start
- [Server README](../server/README.md) — Docker, seeding, tests
- [CQRS overview](../server/cqrs/README.md) — shared CQRS docs
- [Command service](../server/cqrs/command_service/README.md)
- [Query service](../server/cqrs/query_service/README.md)
- [Web dashboard](../web/README.md)
- [API consumer](../api-consumer/README.md)
