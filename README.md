# TF2 Analytics

A full-stack web application for ingesting, analyzing, and visualizing Team Fortress 2 competitive match logs.

Collect log data from sources like [logs.tf](https://logs.tf) and [matcha.tf](https://matcha.tf), compute per-class ratings, and browse tournament leaderboards, match stats, and player careers through a Vue dashboard.

## Architecture

TF2 Analytics uses a **CQRS microservices** architecture:

```text
logproject/
  web/                    Vue dashboard (:5173)
  server/
    cqrs/
      command_service/    Write API + auth (:8001)
      query_service/      Read API + projections (:8002)
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

This starts Postgres, RabbitMQ, command service, query service, and the web dev server.

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
python seed_cqrs.py --http
```

Or via Docker:

```bash
docker compose --profile seed run --rm seed
```

Reset and re-seed:

```bash
python seed_cqrs.py --http --reset
```

Seed data comes from `server/data/seed_logs_cache.json` (built from `invite.txt` via `build_seed_cache.py`).

### 3. Open the dashboard

If not using the Docker web container:

```bash
cd web
npm install
npm run dev
```

Open **http://localhost:5173** and verify:

- **Tournament** — leaderboard and recent matches
- **Match** — per-player stats and class ratings
- **Player** — career totals and class breakdown
- **Nav lookup** — logs.tf ID, match UUID, or SteamID
- **Admin** — `/admin/dashboard` (Steam login + ADMIN role)

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

## Documentation

| Document | Description |
|---|---|
| [Architecture design](docs/architecture.md) | System design, data flows, events, deployment |
| [Server](server/README.md) | Docker Compose, seeding, tests |
| [Command service](server/cqrs/command_service/README.md) | Write API, auth, ingest |
| [Query service](server/cqrs/query_service/README.md) | Read API, projections |
| [Web dashboard](web/README.md) | Frontend routes, proxy, build |
| [API consumer](api-consumer/README.md) | matcha.tf auto-ingest |
| [Monolith migration notes](server/LEGACY.md) | Historical API mapping (monolith removed) |

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
