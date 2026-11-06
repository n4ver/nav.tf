# Web Dashboard

Vue 3 single-page application for browsing TF2 match analytics. Reads from the CQRS **query service** (`:8002`) and sends uploads/admin commands to the **command service** (`:8001`).

**Port:** 5173 (dev)  
**Stack:** Vue 3, Vue Router, Pinia, Axios, Tailwind CSS 4, Vite 8, Vitest

## Features

| Route | View | Data source |
|---|---|---|
| `/` | Home: tournament tabs, class-filterable leaderboard, recent results, tournament facts, class benchmarks. `?tournament=<id>` preselects a tournament | Query |
| `/event/:eventId?` | Event list beside the selected event's tournaments and leaderboard. With no param, opens the first event | Query |
| `/match/:matchId?` | Without an id: paginated results grouped by day. With an id: scorebox (score, map, date, tournament, logs.tf link) and one scoreboard per team with optional per-class stats | Query |
| `/match-log/:logId` | Legacy redirect to `/match/:matchId` | — |
| `/player/:steamId?` | Player profile: headline rating, career stat strip, by-class table, recent matches. With no param, shows a lookup landing | Query |
| `/auth/callback` | Steam OAuth code handoff, then JWT exchange | Command |
| `/admin` | Redirects to `/admin/ingest` (requires `ADMIN`) | — |
| `/admin/ingest` | Raw log upload and logs.tf ingest, with optional target tournament | Command |
| `/admin/events` | Create and rename events | Command |
| `/admin/tournaments` | Create and rename tournaments, link them to events | Command |
| `/admin/matches` | Reassign projected matches to tournaments | Command |
| `/admin/players` | Search players and set display-name aliases | Command |
| `/admin/dashboard` | Legacy redirect to `/admin/ingest` | — |

The top-bar search resolves player names, Steam IDs (any format), logs.tf IDs and match UUIDs via `GET /api/v1/queries/search`, with a client-side fallback for raw IDs.

### Layout and design

The UI follows a function-first, stats-site layout: a dense dark top bar, flat panels with headline bars, compact zebra tables, and the key numbers above the fold.

- `AppShell` contains the sticky `AppTopNav`, the page, and a footer showing API status (one `/health` call per page load). It also has a skip-to-content link.
- `AppTopNav` holds the logo, section links, search and Steam sign-in. Below 1024px the links move into a dropdown menu that closes on Escape or on navigation.
- Ratings are colour-coded numbers: green above 1.15, red below 0.85, plain in between, using `.rating-chip` with `tone-*`. Win/loss scores and `+/-` use the same green and red.
- Tables hide secondary columns on phones (column `hideBelow: 'md'`) and truncate long player names (`truncate: true`), so player, `+/-` and rating stay visible at 375px without sideways scrolling.
- Fonts are the system UI and monospace stacks. Nothing is loaded from Google Fonts.
- Admin pages are nested in `AdminShell`, which provides the section tabs and shows the signed-in identity.

## Project structure

```text
web/
  index.html              App entry (no external fonts)
  src/
    App.vue               Mounts AppShell + RouterView, bootstraps auth
    router.js             Routes + exported `authGuard` (auth / ADMIN checks)
    api.js                Axios clients and typed helpers for command/query/auth APIs
    style.css             Theme tokens + shared utilities (field, btn-primary, btn-ghost,
                          label-caps, focus-ring, data-link, tab, tab-active, rating-chip)
    layouts/
      AppShell.vue        Top nav + main landmark + API status footer
      AdminShell.vue      Admin section tabs and identity line
    components/
      layout/             AppTopNav (links, search, sign-in, mobile menu)
      ui/                 Panel, DataGrid (the sortable table), SkeletonBlock, StateMessage
      stats/              PlayerLeaderboard (class filter + ranked table), PlayerCareerSummary (profile header)
      match/              MatchSummaryCard (scorebox), MatchResultList (results rows)
      admin/              LogUploadForm, LogsTfIngestor
    views/                TournamentView, EventView, MatchStatsView, PlayerStatsView, AuthCallbackView
      admin/              AdminIngestView, AdminEventsView, AdminTournamentsView,
                          AdminMatchesView, AdminPlayersView
    stores/               Pinia stores (see below)
    composables/
      useCan.js           Role-gated UI helper
      useLogIngestion.js  Submit a log, then poll the query side until the projection is ready
    utils/
      format.js           Number/date/duration formatters, TF2 class list, route path helpers
      poll.js             `pollUntil` for read-after-write on admin mutations
      rating.js           0–2 rating band helpers (format, tone, sort)
      steam.js            SteamID2/3/64 conversion, profile URLs, player labels
    test/
      setup.js            Global Vitest setup (Pinia, RouterLink stub)
      helpers.js          `createTestRouter`, `fakeJwt`
  vite.config.js          Dev proxy to CQRS services + Vitest config
```

### UI conventions

- Wrap page sections in `Panel` (`title`, `#actions` slot, and `flush` for edge-to-edge tables or lists).
- Use `DataGrid` for every table. It handles sorting (keyboard-accessible headers with `aria-sort`), loading skeletons, empty messages, overflow and phone column priority. Customise cells with `#cell-<key>` slots.
- Use `MatchResultList` for any list of matches and `PlayerLeaderboard` for any ranked player table, rather than building new ones.
- Every async section handles three states: loading uses `SkeletonBlock`, errors use `<StateMessage tone="error">` (`role="alert"`), and empty results use `<StateMessage>`.
- Style controls with the shared `field`, `btn-primary`, `btn-ghost`, `label-caps`, `tab` and `data-link` utilities instead of copying class strings. Every colour is a theme token in `style.css`.

## Quick start

**With Docker (from repo root):**

```bash
cd server
docker compose up -d --build
python dev-setup/seed/seed_cqrs.py --http
# Web runs at http://localhost:5173 via the web container
```

**Local Vite dev server:**

```bash
cd server
docker compose up -d db rabbitmq command-service query-service
python dev-setup/seed/seed_cqrs.py --http

cd ../web
npm install
npm run dev
```

Open **http://localhost:5173**.

## API integration

The dashboard talks to two backend services. In development, Vite proxies browser requests so the frontend uses same-origin paths:

| Browser path | Proxied to | Service |
|---|---|---|
| `/api/command/*` | `http://127.0.0.1:8001/api/v1/commands` | Command |
| `/api/auth/*` | `http://127.0.0.1:8001/api/v1/auth` | Command |
| `/api/query/*` | `http://127.0.0.1:8002/api/v1/queries` | Query |
| `/health` | `http://127.0.0.1:8002` | Query |

Proxy configuration: [vite.config.js](vite.config.js).

### Pinia stores

| Store | Purpose |
|---|---|
| `auth` | JWT storage, Steam login, `/auth/me` bootstrap, role helpers |
| `matchQuery` | Paginated match list and cached match detail |
| `playerQuery` | Player lifetime stats (cached per SteamID64) |
| `ratingQuery` | Class benchmarks and tournament leaderboards |
| `eventQuery` | Event catalog, event detail (child tournaments), event leaderboards |
| `matchCommand` | Log upload and ingest command state (admin) |

## Environment

Create `.env` in this directory to override defaults:

```bash
# Local dev (default): Vite rewrites /api/command|query|auth → services on :8001/:8002
VITE_COMMAND_PROXY_TARGET=http://127.0.0.1:8001
VITE_QUERY_PROXY_TARGET=http://127.0.0.1:8002

# Optional: route through the Nginx gateway instead (must be running on this host/port)
# VITE_GATEWAY_PROXY_TARGET=http://127.0.0.1:8095

# Production: call APIs directly (no Vite proxy)
VITE_COMMAND_BASE_URL=https://api.example.com/api/command
VITE_QUERY_BASE_URL=https://api.example.com/api/query
VITE_AUTH_BASE_URL=https://api.example.com/api/auth
```

When running the web container via Docker Compose, `VITE_GATEWAY_PROXY_TARGET=http://gateway:80` is set so Vite proxies through the Nginx gateway.

## Authentication

1. User clicks login → redirect to command service Steam OpenID
2. Steam callback → command service validates, redirects to `/auth/callback?code=…`
3. Frontend POSTs the code to `/api/v1/auth/exchange` and stores the returned JWT in Pinia/localStorage
4. Admin routes (`/admin/*`) require `ADMIN` role
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
npm test           # Vitest in watch mode
npm run test:run   # single run (CI)
```

Specs sit next to their source file as `*.spec.js`. They use Vitest, `@vue/test-utils` and `@pinia/testing`, and follow arrange-act-assert. Every network call is mocked with `vi.mock('../api')`, and admin read-after-write polling is mocked through `utils/poll`. Shared setup lives in [src/test/setup.js](src/test/setup.js) and [src/test/helpers.js](src/test/helpers.js).

| Area | Specs |
|---|---|
| Shell | `layouts/AppShell`, `layouts/AdminShell`, `components/layout/AppTopNav` (nav, mobile menu, search routing), `router` (auth guard, route table) |
| Views | `TournamentView`, `EventView`, `MatchStatsView`, `PlayerStatsView`, `AuthCallbackView` |
| Admin | `AdminIngestView`, `AdminEventsView`, `AdminTournamentsView`, `AdminMatchesView`, `AdminPlayersView`, `components/admin/LogUploadForm` |
| Components | `ui/DataGrid`, `stats/PlayerLeaderboard`, `stats/PlayerCareerSummary`, `match/MatchSummaryCard`, `match/MatchResultList` |
| Logic | `composables/useCan`, `utils/format`, `utils/poll`, `utils/rating`, `utils/steam` |

## Related

- [Root README](../README.md)
- [Architecture](../docs/architecture.md)
- [Command service](../server/cqrs/command_service/README.md)
- [Query service](../server/cqrs/query_service/README.md)
