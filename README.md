# nav.tf

A full-stack web application for ingesting, analyzing, and visualizing Team Fortress 2 competitive match logs.

Collect log data from sources like [logs.tf](https://logs.tf) and [matcha.tf](https://matcha.tf), compute per-class ratings, and browse tournament leaderboards, match stats, and player careers through a Vue dashboard.

## Architecture

nav.tf uses a **CQRS microservices** architecture:

```text
nav.tf/
  web/                    Vue dashboard (:5173)
  server/
    cqrs/
      command_service/    Write API + auth (:8001)
      query_service/      Read API + projections (:8002)
    dev-setup/            Docker, tests, coverage, seed tooling
  api-consumer/           External auto-ingest (:8010)
  docs/architecture.md    Full architecture design
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
- Node.js 20+ and npm (web dashboard, optional if using Docker web service)
- Python 3.12+ (local seeding, tests)

## Quick start

### 1. Start services

```bash
cd server
docker compose up -d --build
```

This starts Postgres, RabbitMQ, command service, query service, the Nginx gateway (:8095), and the web dev server.

Minimal backend only:

```bash
docker compose up -d db rabbitmq command-service query-service
```

Optional external auto-ingest:

```bash
docker compose --profile consumer up -d api-consumer
```

### 2. Seed sample data

```bash
cd server
python dev-setup/seed/seed_cqrs.py --http
```

Or via Docker:

```bash
docker compose --profile seed run --rm seed
```

Reset and re-seed:

```bash
python dev-setup/seed/seed_cqrs.py --http --reset
```

Seed data comes from `server/data/seed_logs_cache.json` (built from `dev-setup/seed/invite.txt` via `dev-setup/seed/build_seed_cache.py`).

### 3. Open the dashboard

If not using the Docker web container:

```bash
cd web
npm install
npm run dev
```

> If `web/.env` sets `VITE_GATEWAY_PROXY_TARGET=http://127.0.0.1:8095`, the gateway must be running
> (it is not part of the minimal backend above), otherwise API calls return 502. Remove that line to
> proxy straight to the command and query services. See [web/README.md](web/README.md).

Open **http://localhost:5173** and verify:

- **Tournament** — leaderboard and recent matches
- **Match** — per-player stats and class ratings
- **Player** — career totals and class breakdown
- **Nav lookup** — logs.tf ID, match UUID, or SteamID
- **Admin** — `/admin` (Steam login + ADMIN role; ingest, events, tournaments, matches, aliases)

## Local development (host Python)

```bash
cd server
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

docker compose up -d db rabbitmq

uvicorn cqrs.command_service.app.main:app --host 127.0.0.1 --port 8001 --reload
uvicorn cqrs.query_service.app.main:app --host 127.0.0.1 --port 8002 --reload
```

Copy `server/.env.example` for environment overrides.

## Production deployment

Production runs on Google Cloud: one Compute Engine VM running a Docker Compose stack, with Caddy providing automatic HTTPS. GitHub Actions deploys through Artifact Registry and Workload Identity Federation, with secrets in Secret Manager. The setup works with the free-trial credit.

See **[deploy/README.md](deploy/README.md)** for the one-time bootstrap, DNS, GitHub configuration, operations, cost and teardown.

## Documentation

| Document | Description |
|---|---|
| [Architecture design](docs/architecture.md) | System design, data flows, events, deployment |
| [Server](server/README.md) | Docker Compose, seeding, tests |
| [Command service](server/cqrs/command_service/README.md) | Write API, auth, ingest |
| [Query service](server/cqrs/query_service/README.md) | Read API, projections |
| [Web dashboard](web/README.md) | Frontend routes, proxy, build |
| [API consumer](api-consumer/README.md) | matcha.tf auto-ingest |
| [Production deployment](deploy/README.md) | Google Cloud setup, CI/CD, operations |

## Tests

```bash
cd server
docker compose up -d db db-init
python -m pytest cqrs/tests -q
```

```bash
cd web
npm test
```

```bash
cd api-consumer
npm test
```

## Data classifier

Experimental rating work in a Jupyter notebook:

```bash
cd classifier
pip install -r src/requirements-classifier.txt
jupyter notebook src/classifier.ipynb
```

The production rating model lives in `server/cqrs/shared/rating.py`.
