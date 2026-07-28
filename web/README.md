# Web Dashboard

Vue 3 single-page application for browsing TF2 match analytics. Reads from the CQRS **query service** (`:8002`) and sends uploads/admin commands to the **command service** (`:8001`).

**Port:** 5173 (dev)  
**Stack:** Vue 3, Vue Router, Pinia, Axios, Tailwind CSS 4, Vite 8, Vitest

## Features

| Route | View | Data source |
|---|---|---|
| `/` | Tournament overview — leaderboard, recent matches | Query |
| `/match/:matchId` | Match detail — per-player stats, class ratings | Query |
| `/match-log/:logId` | Legacy redirect → `/match/:matchId` | — |
| `/player/:steamId` | Player profile — career totals, class splits | Query |
| `/auth/callback` | Steam OAuth code handoff → JWT exchange | Command |
| `/admin/dashboard` | Log upload, logs.tf ingest, tournament admin | Command (admin JWT) |

Global nav search resolves logs.tf IDs, match UUIDs, Steam IDs, and player names via `GET /api/v1/queries/search`.

## Project structure

```text
web/
  src/
    views/           Page components (Tournament, Match, Player, Admin, Auth)
    components/      Reusable UI (MatchSummaryCard, PlayerStatsTable, LogUploadForm, …)
    stores/          Pinia stores (auth, matchQuery, playerQuery, ratingQuery, matchCommand)
    composables/     useCan — RBAC helpers
    utils/           rating.js, steam.js
    api.js           Axios instances for command/query APIs
    router.js        Routes + auth guards
  vite.config.js     Dev proxy to CQRS services
  package.json
```

## Quick start

**With Docker (from repo root):**

```bash
cd server
docker compose up -d --build
python seed_cqrs.py --http
# Web runs at http://localhost:5173 via the web container
```

**Local Vite dev server:**

```bash
cd server
docker compose up -d db rabbitmq command-service query-service
python seed_cqrs.py --http

cd ../web
npm install
npm run dev
```

Open **http://localhost:5173**.

## API integration

The dashboard talks to two backend services. In development, Vite proxies browser requests so the frontend uses same-origin paths:

| Browser path | Proxied to | Service |
|---|---|---|
| `/api/v1/commands/*` | `http://127.0.0.1:8001` | Command |
| `/api/v1/auth/*` | `http://127.0.0.1:8001` | Command |
| `/api/v1/queries/*` | `http://127.0.0.1:8002` | Query |
| `/health` | `http://127.0.0.1:8002` | Query |

Proxy configuration: [vite.config.js](vite.config.js).

### Pinia stores

| Store | Purpose |
|---|---|
| `auth` | JWT storage, Steam login, `/auth/me` bootstrap |
| `matchQuery` | Match list and detail from query service |
| `playerQuery` | Player lifetime stats |
| `ratingQuery` | Benchmarks and leaderboard data |
| `matchCommand` | Log upload and ingest commands (admin) |

## Environment

Create `.env` in this directory to override defaults:

```bash
# Dev proxy targets (default: localhost CQRS ports)
VITE_COMMAND_PROXY_TARGET=http://127.0.0.1:8001
VITE_QUERY_PROXY_TARGET=http://127.0.0.1:8002

# Production: call APIs directly (no Vite proxy)
VITE_COMMAND_BASE_URL=https://api.example.com/api/v1/commands
VITE_QUERY_BASE_URL=https://api.example.com/api/v1/queries
VITE_AUTH_BASE_URL=https://api.example.com/api/v1/auth
```

When running via Docker Compose, proxy targets are set to internal service hostnames (`command-service:8001`, `query-service:8002`).

## Authentication

1. User clicks login → redirect to command service Steam OpenID
2. Steam callback → command service validates, redirects to `/auth/callback?code=…`
3. Frontend POSTs the code to `/api/v1/auth/exchange` and stores the returned JWT in Pinia/localStorage
4. Admin routes (`/admin/dashboard`) require `ADMIN` role
5. Mutating API calls include `Authorization: Bearer <token>`

Bootstrap admins via `BOOTSTRAP_ADMIN_STEAM_IDS` on the command service.

## Build and preview

```bash
npm run build      # output to dist/
npm run preview    # serve production build locally
```

For production deployment, serve `dist/` as static files behind a reverse proxy. Set `VITE_COMMAND_BASE_URL`, `VITE_QUERY_BASE_URL`, and `VITE_AUTH_BASE_URL` at build time to point at public API endpoints.

## Tests

```bash
npm test           # Vitest unit tests
npm run test:watch
```

Test setup: [src/test/setup.js](src/test/setup.js).

Component tests: `LogUploadForm.spec.js`, `MatchSummaryCard.spec.js`, `PlayerStatsTable.spec.js`.

## Related

- [Root README](../README.md)
- [Architecture](../docs/architecture.md)
- [Command service](../server/cqrs/command_service/README.md)
- [Query service](../server/cqrs/query_service/README.md)
