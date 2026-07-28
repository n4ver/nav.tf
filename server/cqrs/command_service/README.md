# Command Service

FastAPI write-side microservice for TF2 Analytics. Accepts log uploads and admin commands, persists the write model to Postgres, and publishes integration events to RabbitMQ.

**Port:** 8001  
**Database:** `cqrs_command`  
**Entrypoint:** `cqrs.command_service.app.main:app`

## Responsibilities

- Parse SRCDS raw logs and logs.tf JSON into normalized match payloads
- Persist `raw_log_events`, `users`, and `tournaments`
- Publish `MatchParsed` and related integration events
- Steam OpenID authentication and JWT issuance
- Admin-only mutating commands (log ingest, tournament CRUD, player aliases)

The command service **never** serves leaderboard or match detail queries — those belong to the query service.

## API routes

### Authentication (public)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/auth/steam/login` | Redirect to Steam OpenID |
| `GET` | `/api/v1/auth/steam/callback` | Validate Steam assertion, redirect to frontend with one-time code |
| `POST` | `/api/v1/auth/exchange` | Exchange one-time login code for JWT |
| `GET` | `/api/v1/auth/me` | Current user profile (Bearer token required) |

### Commands (ADMIN JWT required)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/commands/logs/upload` | Upload raw SRCDS log text |
| `POST` | `/api/v1/commands/logs/ingest-cached` | Ingest from local seed cache by logs.tf ID |
| `POST` | `/api/v1/commands/logs/ingest-logstf` | Fetch and ingest a logs.tf log by ID |
| `POST` | `/api/v1/commands/players/display-name` | Update player display name |
| `POST` | `/api/v1/commands/tournaments` | Create tournament |
| `PATCH` | `/api/v1/commands/tournaments/{tournament_id}` | Update tournament metadata |

All command endpoints return **202 Accepted** with a job/event reference.

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | `{"status": "ok", "side": "command"}` |

## Write model tables

| Table | Purpose |
|---|---|
| `raw_log_events` | Immutable raw log payloads and parse metadata |
| `users` | Steam users, roles (USER/ADMIN), display names |
| `tournaments` | Tournament records with stable UUID IDs |

## Event publishing

After a log is committed, the service publishes to exchange `tf2-events`:

- **`MatchParsed`** — parsed match, players, class stats, tournament tag
- **`LogEventCreated`** — acknowledgment that the raw row was stored
- **`PlayerAliasUpdated`**, **`TournamentCreated`**, **`TournamentUpdated`** — admin mutations

Routing key format: `events.{EventType}` (e.g. `events.MatchParsed`).

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `CQRS_COMMAND_DATABASE_URL` | `postgresql+asyncpg://user:password@127.0.0.1:5432/cqrs_command` | Write DB |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Event broker |
| `JWT_SECRET` | — | JWT signing (required in prod) |
| `SEED_SERVICE_TOKEN` | — | Allows seed script to bypass admin JWT |
| `FRONTEND_URL` | `http://localhost:5173` | Post-login redirect base |
| `STEAM_OPENID_REALM` | `http://localhost:5173` | Steam OpenID realm |
| `STEAM_OPENID_RETURN_TO` | `http://localhost:5173/api/v1/auth/steam/callback` | Callback URL |
| `STEAM_API_KEY` | — | Steam Web API for persona/avatar |
| `BOOTSTRAP_ADMIN_STEAM_IDS` | — | Comma-separated Steam IDs promoted to ADMIN |
| `SEED_CACHE_PATH` | `server/data/seed_logs_cache.json` | Cached logs for `ingest-cached` |
| `CQRS_BROKER_MODE` | unset | Set to `memory` for tests |

## Run

**Docker:**

```bash
cd server
docker compose up -d command-service
```

**Local:**

```bash
docker compose up -d db rabbitmq
uvicorn cqrs.command_service.app.main:app --host 127.0.0.1 --port 8001 --reload
```

## Examples

Upload raw log (admin token):

```bash
curl -X POST http://127.0.0.1:8001/api/v1/commands/logs/upload \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "log_data": "map_name=cp_process_final blu_score=2 red_score=1 player steam_id=STEAM_1:1:12345 team=blu class=scout kills=10 deaths=5 assists=2 dpm=350 healing=0",
    "timestamp": "2026-07-28T00:00:00Z"
  }'
```

Ingest from seed cache:

```bash
curl -X POST http://127.0.0.1:8001/api/v1/commands/logs/ingest-cached \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"log_id": 4037391, "tournament_id": 2, "section": "R8"}'
```

Service token (seeding):

```bash
curl -X POST http://127.0.0.1:8001/api/v1/commands/logs/ingest-cached \
  -H "Authorization: Bearer $SEED_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"log_id": 4037391}'
```

## Steam OpenID notes

- Use **`http://localhost:5173`** as the browser origin in local dev (not HTTPS on :8001)
- `return_to` must match `STEAM_OPENID_RETURN_TO`
- If Steam redirects to `https://localhost:8001`, you will see SSL errors — the command service is HTTP-only

## Related

- [Query service](../query_service/README.md)
- [CQRS overview](../README.md)
- [Architecture](../../../docs/architecture.md)
