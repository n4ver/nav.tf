# nav.tf

A full-stack web application for ingesting, analyzing, and visualizing Team Fortress 2 competitive match logs.

Collect log data from sources like [logs.tf](https://logs.tf) and [matcha.tf](https://matcha.tf), compute per-class ratings, and browse tournament leaderboards, match stats, and player careers through a Vue dashboard.

## Repository layout

```text
nav.tf/
  compose.yaml        Local development stack (docker compose, run from here)
  .env.example        Local settings; copy to .env
  web/                Vue dashboard (:5173)
  server/             Python CQRS backend
    cqrs/               command_service (:8001), query_service (:8002), shared, tests
    seed/               Sample-data seeding scripts
    data/               Seed cache (logs.tf payloads)
  api-consumer/       Node matcha.tf → logs.tf auto-ingest (:8010, optional)
  dev/                Local-only config (nginx gateway on :8095)
  deploy/             Production: Dockerfiles, compose.prod.yml, Caddy, GCP scripts
  docs/               Architecture and API specs (OpenAPI, CDM)
```

| Service | Port | Role |
|---|---|---|
| [Command](server/cqrs/command_service/README.md) | 8001 | Log ingest, admin commands, Steam auth, event publish |
| [Query](server/cqrs/query_service/README.md) | 8002 | Projections, leaderboards, player stats, search |
| [Web](web/README.md) | 5173 | Vue SPA (reads query, writes command) |
| [API consumer](api-consumer/README.md) | 8010 | matcha.tf → logs.tf → RabbitMQ (optional) |

Events flow **command → RabbitMQ → query**. Both backend services use separate **PostgreSQL** databases. See [docs/architecture.md](docs/architecture.md) for the full design.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Postgres, RabbitMQ, services)
- Node.js 20+ and npm (web dashboard and api-consumer outside Docker)
- Python 3.13+ (backend tests and seeding outside Docker)

## Quick start

All `docker compose` commands run from the repository root.

### 1. Start services

```bash
cp .env.example .env
docker compose up -d --build
```

This starts Postgres, RabbitMQ, the command and query services, the Nginx gateway (:8095) and the web dev server (:5173).

Backend only:

```bash
docker compose up -d db rabbitmq command-service query-service
```

Optional matcha.tf auto-ingest (also powers Admin → Ingest → matcha.tf):

```bash
docker compose --profile consumer up -d api-consumer
```

### 2. Seed sample data

```bash
docker compose --profile seed run --rm seed
```

Or from the host, with reset:

```bash
cd server
python seed/seed_cqrs.py --http --reset
```

Seed data comes from `server/data/seed_logs_cache.json`, built from `server/seed/invite.txt` by `server/seed/build_seed_cache.py`.

### 3. Open the dashboard

Open **http://localhost:5173** (or the gateway on **http://localhost:8095**). To run Vite on the host instead of the `web` container:

```bash
cd web
npm install
npm run dev
```

> If `web/.env` sets `VITE_GATEWAY_PROXY_TARGET=http://127.0.0.1:8095`, the gateway must be running,
> otherwise API calls return 502. See [web/README.md](web/README.md).

Then check:

- **Home** — leaderboard and recent matches, scoped by event and tournament
- **Match** — per-player stats and class ratings
- **Player** — career totals and class breakdown
- **Search** — logs.tf ID, match UUID, or SteamID
- **Admin** — `/admin` (Steam login + ADMIN role; ingest, events, tournaments, matches, aliases)

To run the Python services on the host, see [server/README.md](server/README.md).

## Tests

```bash
docker compose up -d db db-init          # backend tests need Postgres
cd server && pip install -r requirements-dev.txt && python -m pytest -q
```

```bash
cd web && npm test
```

```bash
cd api-consumer && npm test
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs all three plus a production image build.

## Production deployment

Production runs on Google Cloud: one Compute Engine VM running a Docker Compose stack, with Caddy providing automatic HTTPS. GitHub Actions deploys through Artifact Registry and Workload Identity Federation, with secrets in Secret Manager. The setup works with the free-trial credit.

See **[deploy/README.md](deploy/README.md)** for the one-time bootstrap, DNS, GitHub configuration, operations, cost and teardown.

## Documentation

| Document | Description |
|---|---|
| [Architecture design](docs/architecture.md) | System design, data flows, events, deployment |
| [API spec](docs/specs/openapi.yaml) | OpenAPI for the gateway paths |
| [Server](server/README.md) | Layout, Docker Compose, seeding, tests |
| [Command service](server/cqrs/command_service/README.md) | Write API, auth, ingest |
| [Query service](server/cqrs/query_service/README.md) | Read API, projections, ratings |
| [Web dashboard](web/README.md) | Frontend routes, proxy, build |
| [API consumer](api-consumer/README.md) | matcha.tf auto-ingest |
| [Production deployment](deploy/README.md) | Google Cloud setup, CI/CD, operations |

The rating model lives in `server/cqrs/query_service/app/rating/service.py`.
