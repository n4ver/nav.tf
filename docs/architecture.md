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
- `rating.py` — class rating math (ported from legacy notebook)
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
                    └──► rebuild ratings inline → refresh leaderboard_snapshot_view
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
| `MatchParsed` | Command, api-consumer | Upsert match/player projections; rebuild ratings inline; refresh tournament/event leaderboards |
| `LogEventCreated` | Command | Acknowledgment (query may log; no projection change) |
| `PlayerAliasUpdated` | Command | Update player identity projection |
| `TournamentCreated` / `TournamentUpdated` | Command | Upsert tournament summary |
| `EventCreated` / `EventUpdated` | Command | Upsert event summary |
| `TournamentLinkedToEvent` | Command | Set tournament.event_id; rewrite event tournament list; rebuild event player stats |
| `MatchTournamentAssigned` | Command | Move match to a tournament; recount; refresh leaderboards and event stats |
| `MatchLogIngested` | api-consumer | Audit/provenance (optional) |
| `RatingsRebuildRequested` / `RatingsRebuilt` | Legacy | Kept for in-flight messages only; ratings now rebuild inline on `MatchParsed` |

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

Ratings are **never computed at request time** on the query API. After each `MatchParsed` projection:

1. `PlayerMatchClassStatsProjection` stores per-class stat rows
2. `ProjectionService.rebuild_ratings()` rebuilds `ClassRatingBenchmarkProjection` baselines **in the same handler**
3. `RatingService` (from `query_service/app/rating/service.py`) scores every class row against benchmarks
4. `leaderboard_snapshot_view` is refreshed for tournament leaderboards
5. If the match's tournament is linked to an event, event player stats are rebuilt

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

### Production considerations

- Run command and query as separate containers (already supported)
- Place a reverse proxy in front of web static assets; set `VITE_COMMAND_BASE_URL` and `VITE_QUERY_BASE_URL` to public API URLs (no Vite proxy in prod)
- Set strong `JWT_SECRET` and `SEED_SERVICE_TOKEN`
- Configure `STEAM_API_KEY`, `STEAM_OPENID_REALM`, and `FRONTEND_URL` for production domain
- RabbitMQ should be clustered or managed (AWS MQ, CloudAMQP) for HA
- Postgres: separate connection pools per service; consider read replicas only if query load warrants it (projections are already precomputed)

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
