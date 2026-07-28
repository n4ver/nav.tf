# API Consumer

Node.js microservice that discovers TF2 matches from third-party sites, enriches them with logs.tf stats, normalizes the payload, and publishes `MatchParsed` events to the CQRS RabbitMQ bus.

**Port:** 8010  
**Stack:** Node 20, Express, amqplib, node-cron, opossum, pino, Jest

This service is **optional**. Enable it when you want automatic ingestion from matcha.tf without manual admin uploads.

## Role in the architecture

```text
matcha.tf API                    logs.tf API
      │                               │
      ▼                               ▼
 MatchaAdapter ──► LogsTfClient ──► normalize
                                        │
                                        ▼
                              RabbitMQ (tf2-events)
                                        │
                                        ▼
                              Query service projections
```

Unlike the command service ingest path, api-consumer **does not write to `cqrs_command`**. It publishes events directly to RabbitMQ. The query service consumes them and updates read-model projections the same way as command-originated events.

See [Architecture design](../docs/architecture.md) for the dual-ingest rationale.

## Triggers

| Trigger | Mechanism | Endpoint / schedule |
|---|---|---|
| Scheduled poll | node-cron | `POLL_CRON` (default `*/5 * * * *` in Docker) |
| Manual poll | HTTP POST | `POST /admin/poll` |
| Webhook | Express | `POST /webhooks/matcha/match` with `{"matchId": 201}` |

## Ingest flow (matcha.tf)

```text
1. MatchaAdapter.listMatchIds()
     GET /v1/leagues/{leagueId}/matches?divisionId=

2. MatchaAdapter.fetchNormalizedMatch(id)
     GET /v1/matches/{id}  →  extract logs[].logstfId

3. LogsTfClient.fetchNormalized(logstfId)
     GET https://logs.tf/api/v1/log/{id}  →  player/class stats

4. EventPublisher
     events.MatchParsed        → query projections
     events.MatchLogIngested     → audit/provenance
     failed.* (DLX)            → dead-letter on retry exhaustion
```

matcha.tf provides **series metadata and logs.tf links**. Per-player damage, kills, and medic stats come from **logs.tf**.

## Directory layout

```text
api-consumer/
  src/
    adapters/
      LogSourceAdapter.js       Base contract for log sources
      matcha/                   matcha.tf adapter + parser
      logsTf/                   logs.tf enrichment client
    http/resilientClient.js     Rate limit, backoff, circuit breaker
    ingest/                     Pipeline + idempotency
    models/normalized.js        NormalizedTF2Match / PlayerStat DTOs
    rabbitmq/                   amqplib connection + publisher
    triggers/                   node-cron poller + Express webhooks
    config.js
    index.js                    Entry point
  tests/
    fixtures/                   Sample matcha + logs.tf responses
    unit/
```

## Events

Published to exchange **`tf2-events`** (same topology as `server/cqrs/shared/broker.py`):

| Routing key | Purpose |
|---|---|
| `events.MatchParsed` | Drive query projections (required) |
| `events.MatchLogIngested` | Provenance: `sourceSite`, `sourceMatchId`, `ingestedAt`, `correlationId` |
| `failed.*` on DLX `tf2-events.dlx` | Exhausted API/parse failures |

`match_id` is deterministic: `uuid5(NAMESPACE_URL, "logs.tf:{logstfId}")` — identical to the Python command service.

## Configuration

Copy `.env.example` to `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | 8010 | HTTP server port |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Event broker |
| `CQRS_EXCHANGE_NAME` | `tf2-events` | Publish exchange |
| `CQRS_DLX_NAME` | `tf2-events.dlx` | Dead-letter exchange |
| `MATCHA_LEAGUE_ID` | 1 | League to poll |
| `MATCHA_DIVISION_ID` | 1 | Division filter |
| `MATCHA_TOURNAMENT_NAME` | Matcha.tf Minicup Invite | Tournament tag on ingested matches |
| `MATCHA_TOURNAMENT_SLUG` | matcha-tf-minicup-invite | Stable tournament slug |
| `POLL_CRON` | `*/30 * * * *` | Cron schedule (`.env.example`; Docker overrides to `*/5`) |
| `POLL_ENABLED` | false (local) / true (Docker) | Enable scheduled polling |
| `WEBHOOK_ENABLED` | true | Enable webhook HTTP server |
| `HTTP_TIMEOUT_MS` | 15000 | Outbound request timeout |
| `HTTP_MAX_RETRIES` | 4 | Retry count for external APIs |
| `CIRCUIT_ERROR_THRESHOLD` | 50 | Opossum circuit breaker threshold |
| `ACTOR_ID` | api-consumer | Event `actor_id` field |
| `WEBHOOK_API_KEY` | — | **Required** for `POST /admin/poll` and webhook ingest |

Ingested matcha logs are tagged with one tournament so they appear together in the web app tournament dropdown.

## Run locally

```bash
cd api-consumer
cp .env.example .env

# Requires RabbitMQ (from server/docker-compose.yml)
cd ../server && docker compose up -d rabbitmq

cd ../api-consumer
npm install
npm test
npm start
```

## Run with Docker

```bash
cd server
docker compose --profile consumer up -d api-consumer
```

Environment variables are set in [docker-compose.yml](../server/docker-compose.yml).

## HTTP endpoints

```bash
# Trigger webhook ingest for a specific match
curl -X POST http://localhost:8010/webhooks/matcha/match \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_WEBHOOK_API_KEY' \
  -d '{"matchId": 201}'

# Manually run one poll cycle
curl -X POST http://localhost:8010/admin/poll \
  -H 'Authorization: Bearer YOUR_WEBHOOK_API_KEY'
```

## Adding a new log source

1. Implement `LogSourceAdapter` (`listMatchIds`, `fetchNormalizedMatch`).
2. Map site JSON → `createNormalizedMatch(...)` in `models/normalized.js`.
3. Register the adapter in `adapters/index.js`.
4. Add a trigger (cron, webhook, or both) in `triggers/`.

## Tests

```bash
npm test
```

Fixtures in `tests/fixtures/` include real-shaped matcha and logs.tf responses.

## Related

- [Architecture](../docs/architecture.md)
- [Query service](../server/cqrs/query_service/README.md)
- [Server Docker Compose](../server/docker-compose.yml)
