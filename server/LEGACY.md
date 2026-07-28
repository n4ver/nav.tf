# Legacy Monolith — Removed

> **Status:** Removed July 2026. The monolith at `server/src/` has been deleted.

The original TF2 Analytics backend was a single FastAPI application on port `:8000` that read and wrote one Postgres database (`tf2_stats`) synchronously, with no event bus, no authentication, and request-time rating computation.

## Replacement services

| Former capability | Use instead | Port |
|---|---|---|
| Log ingest | Command service `POST /api/v1/commands/logs/*` | 8001 |
| Match/player/tournament reads | Query service `GET /api/v1/queries/*` | 8002 |
| Bulk seeding | `seed_cqrs.py --http` | — |

## API migration map

| Legacy endpoint (`:8000`) | CQRS replacement |
|---|---|
| `POST /logs/ingest/{log_id}?tournament_id=` | `POST /api/v1/commands/logs/ingest-logstf` (:8001, admin JWT) |
| `GET /matches` | `GET /api/v1/queries/matches` (:8002) |
| `GET /logs/{id}/stats` | `GET /api/v1/queries/matches/{uuid}` (:8002) |
| `GET /players/{steam_id}/summary` | `GET /api/v1/queries/players/{steam_id}/stats` (:8002) |
| `GET /tournaments/{id}/leaderboard` | `GET /api/v1/queries/tournaments/{uuid}/leaderboard` (:8002) |
| `GET /search` | `GET /api/v1/queries/search?q=` (:8002) |

## What was ported before removal

- **Rating math:** `server/src/services.py` → `server/cqrs/shared/rating.py`
- **Log parsing:** SRCDS and logs.tf parsers → `server/cqrs/command_service/app/parsers.py`, `logs_tf_parser.py`
- **Seed data:** `invite.txt` + `build_seed_cache.py` → `seed_cqrs.py`

## Related

- [Architecture design](../docs/architecture.md)
- [CQRS overview](cqrs/README.md)
