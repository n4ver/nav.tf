# TF2 Analytics — Server

Python backend for TF2 Analytics. The stack is **CQRS microservices** (command + query) backed by Postgres and RabbitMQ.

See [Architecture design](../docs/architecture.md) for the full system overview.

## Services

| Service | Port | Path | README |
|---|---|---|---|
| Command (write) | 8001 | `cqrs/command_service/` | [README](cqrs/command_service/README.md) |
| Query (read) | 8002 | `cqrs/query_service/` | [README](cqrs/query_service/README.md) |

## Quick start

```bash
cd server
docker compose up -d --build
```

This starts Postgres, RabbitMQ, command service, query service, and the web dev container.

Minimal backend (no web container):

```bash
docker compose up -d db rabbitmq command-service query-service
python seed_cqrs.py --http
```

## Docker Compose

File: [docker-compose.yml](docker-compose.yml)

| Service | Always runs | Port | Notes |
|---|---|---|---|
| `db` | Yes | 5432 | Postgres 15; default DB `cqrs_command` |
| `db-init` | Yes | — | One-shot; ensures databases exist on existing volumes |
| `rabbitmq` | Yes | 5672, 15672 | AMQP + management UI |
| `command-service` | Yes | 8001 | Write API |
| `query-service` | Yes | 8002 | Read API + event consumer |
| `web` | Yes | 5173 | Vite dev server (mounts `../web`) |
| `api-consumer` | Profile `consumer` | 8010 | External auto-ingest |
| `seed` | Profile `seed` | — | One-shot CQRS seed |

### Profiles

```bash
# External matcha.tf auto-ingest
docker compose --profile consumer up -d api-consumer

# One-shot seed via Docker
docker compose --profile seed run --rm seed
```

## Seeding

Seed data comes from [data/seed_logs_cache.json](data/seed_logs_cache.json), built from log IDs in [invite.txt](invite.txt).

```bash
python seed_cqrs.py --http              # seed all cached logs
python seed_cqrs.py --http --reset        # truncate CQRS tables, then seed
python seed_cqrs.py --http --limit 10     # seed first 10 logs
```

Rebuild the cache from logs.tf:

```bash
python build_seed_cache.py
python build_seed_cache.py --skip-fetch   # rebuild manifest only
```

Admin auth is required for command endpoints. Docker seeding uses `SEED_SERVICE_TOKEN` (set on both `seed` and `command-service` in compose).

## Local development (host Python)

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

docker compose up -d db rabbitmq

uvicorn cqrs.command_service.app.main:app --host 127.0.0.1 --port 8001 --reload
uvicorn cqrs.query_service.app.main:app --host 127.0.0.1 --port 8002 --reload
```

## Environment

Copy [.env.example](.env.example) for local overrides. Key variables:

| Variable | Service | Purpose |
|---|---|---|
| `CQRS_COMMAND_DATABASE_URL` | Command | Write DB (`cqrs_command`) |
| `CQRS_QUERY_DATABASE_URL` | Query | Read DB (`cqrs_query`) |
| `RABBITMQ_URL` | Command, Query | Event broker |
| `JWT_SECRET` | Command | JWT signing |
| `SEED_SERVICE_TOKEN` | Command, seed | Service auth for seeding |
| `FRONTEND_URL` | Command | Post-login redirect |
| `STEAM_OPENID_*` | Command | Steam OAuth |
| `BOOTSTRAP_ADMIN_STEAM_IDS` | Command | First-admin promotion |
| `STEAM_API_KEY` | Command | Persona/avatar on login |
| `SEED_CACHE_PATH` | Command | Path to seed cache JSON |
| `CQRS_BROKER_MODE=memory` | Tests | In-process broker (no RabbitMQ) |

Inside Docker Compose, database host is `db` instead of `127.0.0.1`.

## Tests

```bash
docker compose up -d db db-init
python -m pytest cqrs/tests -q
```

CQRS tests use `cqrs_command_test` and `cqrs_query_test`.

Test database init: [testing/postgres/](testing/postgres/).

## Utility scripts

| Script | Purpose |
|---|---|
| [seed_cqrs.py](seed_cqrs.py) | Bulk seed via command HTTP or direct in-process |
| [build_seed_cache.py](build_seed_cache.py) | Fetch logs.tf JSON into seed cache |

## Related docs

- [Architecture](../docs/architecture.md)
- [CQRS overview](cqrs/README.md)
- [Monolith migration notes](LEGACY.md)
- [API consumer](../api-consumer/README.md)
- [Web dashboard](../web/README.md)
