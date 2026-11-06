# TF2 Analytics — Server

Python backend for TF2 Analytics. The stack is **CQRS microservices** (command + query) backed by Postgres and RabbitMQ.

See [Architecture design](../docs/architecture.md) for the full system overview.

Developer tooling (Docker, tests, coverage, seed scripts) lives in **[dev-setup/](dev-setup/README.md)**.

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

This starts Postgres, RabbitMQ, command service, query service, gateway (:8095), and the web dev container.

Minimal backend (no web container):

```bash
docker compose up -d db rabbitmq command-service query-service
python dev-setup/seed/seed_cqrs.py --http
```

## Docker Compose

Canonical file: [dev-setup/docker/docker-compose.yml](dev-setup/docker/docker-compose.yml)  
Root stub: [docker-compose.yml](docker-compose.yml) (includes the dev-setup compose file)

| Service | Always runs | Port | Notes |
|---|---|---|---|
| `db` | Yes | 5432 | Postgres 15; default DB `cqrs_command` |
| `db-init` | Yes | — | One-shot; ensures databases exist on existing volumes |
| `rabbitmq` | Yes | 5672, 15672 | AMQP + management UI |
| `command-service` | Yes | 8001 | Write API |
| `query-service` | Yes | 8002 | Read API + event consumer |
| `gateway` | Yes | 8095 | Nginx API gateway |
| `web` | Yes | 5173 | Vite dev server (mounts `../web`) |
| `api-consumer` | Profile `consumer` | 8010 | External auto-ingest |
| `seed` | Profile `seed` | — | One-shot CQRS seed |

### Profiles

```bash
docker compose --profile consumer up -d api-consumer
docker compose --profile seed run --rm seed
```

## Seeding

Seed data comes from [data/seed_logs_cache.json](data/seed_logs_cache.json), built from log IDs in [dev-setup/seed/invite.txt](dev-setup/seed/invite.txt).

```bash
python dev-setup/seed/seed_cqrs.py --http
python dev-setup/seed/seed_cqrs.py --http --reset
python dev-setup/seed/seed_cqrs.py --http --limit 10
```

Rebuild the cache from logs.tf:

```bash
python dev-setup/seed/build_seed_cache.py
python dev-setup/seed/build_seed_cache.py --skip-fetch
```

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

Copy [dev-setup/env/.env.example](dev-setup/env/.env.example) to `.env` for local overrides.

Inside Docker Compose, database host is `db` instead of `127.0.0.1`.

## Tests

```bash
docker compose up -d db db-init
pip install -r requirements-dev.txt
python -m pytest -c dev-setup/python/pytest.ini cqrs/tests -q
python -m pytest -c dev-setup/python/pytest.ini cqrs/tests -q --no-cov
```

Coverage reports: `dev-setup/python/htmlcov/` (HTML) and `dev-setup/python/coverage.xml` (CI).  
Minimum line coverage: 80% (see [dev-setup/python/.coveragerc](dev-setup/python/.coveragerc)).

Test database init: [cqrs/tests/postgres/](cqrs/tests/postgres/).

## Related docs

- [dev-setup/](dev-setup/README.md) — Docker, pytest, coverage, seed tooling
- [Architecture](../docs/architecture.md)
- [CQRS overview](cqrs/README.md)
- [API consumer](../api-consumer/README.md)
- [Web dashboard](../web/README.md)
