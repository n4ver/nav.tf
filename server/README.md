# nav.tf — Server

Python backend for nav.tf: **CQRS microservices** (command + query) backed by Postgres and RabbitMQ.

See [Architecture design](../docs/architecture.md) for the full system overview.

## Layout

```text
server/
  cqrs/
    command_service/   Write API, Steam auth, ingest, outbox → RabbitMQ   (:8001)
    query_service/     Event consumer, projections, ratings, read API      (:8002)
    shared/            Contracts, auth, broker, settings used by both
    tests/             pytest suite (+ ensure-test-databases.sh)
  data/                seed_logs_cache.json (sample logs.tf payloads)
  seed/                seed_cqrs.py, build_seed_cache.py, invite.txt
  requirements.txt     runtime dependencies (used by the Docker image)
  requirements-dev.txt runtime + pytest
  pyproject.toml       same dependencies for uv (uv.lock)
  pytest.ini           test + coverage settings (.coveragerc: 80% gate)
```

| Service | Port | Path | README |
|---|---|---|---|
| Command (write) | 8001 | `cqrs/command_service/` | [README](cqrs/command_service/README.md) |
| Query (read) | 8002 | `cqrs/query_service/` | [README](cqrs/query_service/README.md) |

The Docker image is [`deploy/docker/server.Dockerfile`](../deploy/docker/server.Dockerfile), shared by local development and production.

## Run with Docker

The local stack is defined in the root [`compose.yaml`](../compose.yaml). From the repository root:

```bash
cp .env.example .env
docker compose up -d --build                 # db, rabbitmq, services, gateway (:8095), web (:5173)
docker compose --profile seed run --rm seed  # load sample matches
```

Backend only:

```bash
docker compose up -d db rabbitmq command-service query-service
```

| Service | Runs by default | Port | Notes |
|---|---|---|---|
| `db` | Yes | 5432 | Postgres 15; default DB `cqrs_command` |
| `db-init` | Yes | — | One-shot; creates `cqrs_query` and the test databases |
| `rabbitmq` | Yes | 5672, 15672 | AMQP + management UI |
| `command-service` | Yes | 8001 | Write API (mounts `server/cqrs`, auto-reload) |
| `query-service` | Yes | 8002 | Read API + event consumer |
| `gateway` | Yes | 8095 | Nginx, same paths as production Caddy ([`dev/nginx.conf`](../dev/nginx.conf)) |
| `web` | Yes | 5173 | Vite dev server |
| `api-consumer` | Profile `consumer` | 8010 | matcha.tf auto-ingest |
| `seed` | Profile `seed` | — | One-shot seed through the command API |

## Run on the host

Infrastructure from Docker, services from `server/`:

```bash
docker compose up -d db db-init rabbitmq     # repo root

cd server
python -m venv .venv
source .venv/bin/activate                    # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

uvicorn cqrs.command_service.app.main:app --host 127.0.0.1 --port 8001 --reload
uvicorn cqrs.query_service.app.main:app --host 127.0.0.1 --port 8002 --reload
```

The services read configuration from environment variables only; [`../.env.example`](../.env.example) lists them with local defaults. Inside Docker the database host is `db` instead of `127.0.0.1`.

## Seeding

Seed data comes from [data/seed_logs_cache.json](data/seed_logs_cache.json), built from the log IDs in [seed/invite.txt](seed/invite.txt). From `server/`:

```bash
python seed/seed_cqrs.py --http
python seed/seed_cqrs.py --http --reset
python seed/seed_cqrs.py --http --limit 10
```

Rebuild the cache from logs.tf:

```bash
python seed/build_seed_cache.py
python seed/build_seed_cache.py --skip-fetch
```

## Tests

Needs the Docker Postgres (`docker compose up -d db db-init` from the repo root). From `server/`:

```bash
pip install -r requirements-dev.txt
python -m pytest -q             # with coverage (fails under 80%)
python -m pytest -q --no-cov
```

Coverage reports land in `htmlcov/` and `coverage.xml` (both gitignored).

## Related docs

- [Architecture](../docs/architecture.md)
- [CQRS overview](cqrs/README.md)
- [API consumer](../api-consumer/README.md)
- [Web dashboard](../web/README.md)
- [Production deployment](../deploy/README.md)
