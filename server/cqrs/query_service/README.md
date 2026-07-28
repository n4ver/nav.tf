# Query Service

FastAPI read-side microservice for TF2 Analytics. Consumes integration events from RabbitMQ, maintains materialized projections in Postgres, rebuilds class ratings, and serves all public read APIs.

**Port:** 8002  
**Database:** `cqrs_query`  
**Entrypoint:** `cqrs.query_service.app.main:app`

## Responsibilities

- Subscribe to RabbitMQ queue `cqrs-query` (binding `events.#`)
- Upsert read-model projections on `MatchParsed` and related events
- Rebuild class rating benchmarks and leaderboard snapshots
- Expose HTTP queries for matches, players, tournaments, search, and benchmarks

The query service **never** accepts log uploads or admin mutations.

## API routes

All routes are **public** (no authentication).

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/queries/matches` | List matches (`skip`, `limit`, optional `tournament_id`) |
| `GET` | `/api/v1/queries/matches/{match_id}` | Match detail with per-player stats and ratings |
| `GET` | `/api/v1/queries/tournaments` | List tournaments |
| `GET` | `/api/v1/queries/tournaments/{tournament_id}/leaderboard` | Precomputed leaderboard (`class_name`, `limit`) |
| `GET` | `/api/v1/queries/players/{steam_id}/stats` | Player lifetime stats and class breakdown |
| `GET` | `/api/v1/queries/search` | Search by logs.tf ID, match UUID, SteamID, or player name (`q`) |
| `GET` | `/api/v1/queries/benchmarks/class-rating` | Current class rating benchmarks |
| `GET` | `/health` | `{"status": "ok", "side": "query"}` |

## Projection tables

| Table | Source event | Purpose |
|---|---|---|
| `match_summary_view` | `MatchParsed` | Match metadata, scores, map, tournament |
| `player_match_stats_view` | `MatchParsed` | Per-player match totals |
| `player_match_class_stats_view` | `MatchParsed` | Per-class stat rows (rating input) |
| `player_lifetime_stats_view` | `MatchParsed` | Aggregated career totals |
| `class_rating_benchmark_view` | Rating rebuild | Baseline percentiles per class/stat |
| `leaderboard_snapshot_view` | `RatingsRebuilt` | Precomputed tournament leaderboards |
| `tournament_summary_view` | Tournament events | Tournament list metadata |
| `player_identity_projection` | `PlayerAliasUpdated` | Display names |

## Event consumption

On startup, the service starts an async RabbitMQ consumer (`consumer.py`).

**Primary flow:**

```text
MatchParsed
    → upsert match + player projections
    → publish RatingsRebuildRequested (internal)
    → rebuild class_rating_benchmark_view
    → publish RatingsRebuilt
    → refresh leaderboard_snapshot_view
```

**Ingest from api-consumer:** The same `MatchParsed` handler runs whether the event came from the command service or api-consumer. Events from api-consumer skip the command write DB but still populate all projections.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `CQRS_QUERY_DATABASE_URL` | `postgresql+asyncpg://user:password@127.0.0.1:5432/cqrs_query` | Read DB |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Event broker |
| `CQRS_QUERY_QUEUE` | `cqrs-query` | Consumer queue name |
| `CQRS_EXCHANGE_NAME` | `tf2-events` | Must match command publisher |
| `CQRS_BROKER_MODE` | unset | Set to `memory` for tests |

## Run

**Docker:**

```bash
cd server
docker compose up -d query-service
```

**Local:**

```bash
docker compose up -d db rabbitmq
uvicorn cqrs.query_service.app.main:app --host 127.0.0.1 --port 8002 --reload
```

The event consumer starts automatically with the app lifespan. RabbitMQ must be reachable before projections will update.

## Examples

```bash
curl http://127.0.0.1:8002/health

curl "http://127.0.0.1:8002/api/v1/queries/matches?limit=5"

curl http://127.0.0.1:8002/api/v1/queries/matches/<match_uuid>

curl "http://127.0.0.1:8002/api/v1/queries/tournaments/<tournament_uuid>/leaderboard?limit=20"

curl http://127.0.0.1:8002/api/v1/queries/players/STEAM_1:1:12345/stats

curl "http://127.0.0.1:8002/api/v1/queries/search?q=4037391"
```

## Rating pipeline

Ratings are computed during projection rebuild, not on HTTP request:

1. `PlayerMatchClassStatsProjection` stores raw per-class stats from each match
2. `ProjectionService.rebuild_ratings()` recalculates benchmarks in `class_rating_benchmark_view`
3. `RatingService` (`cqrs/shared/rating.py`) scores each row
4. Leaderboard snapshots are refreshed after `RatingsRebuilt`

After seeding, allow a few seconds for the consumer to process events before querying.

## Troubleshooting

| Symptom | Check |
|---|---|
| Empty matches after seed | RabbitMQ running? Query service logs for consumer errors |
| Stale leaderboards | Wait for rating rebuild; check for `RatingsRebuilt` in logs |
| 404 on match UUID | Search by logs.tf ID first — UUIDs are deterministic from log ID |
| Consumer not connecting | `RABBITMQ_URL` and `CQRS_EXCHANGE_NAME` match command service |

## Related

- [Command service](../command_service/README.md)
- [CQRS overview](../README.md)
- [Architecture](../../../docs/architecture.md)
