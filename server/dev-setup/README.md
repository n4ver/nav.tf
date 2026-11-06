# Developer setup for TF2 Analytics (server)

Local development infrastructure, test runners, coverage, Docker, and seed tooling live here.

## Layout

| Path | Purpose |
|---|---|
| [`docker/`](docker/) | `docker-compose.yml`, `Dockerfile`, Nginx gateway, Postgres init |
| [`python/`](python/) | `pytest.ini`, `.coveragerc`, dev Python dependencies |
| [`javascript/`](javascript/) | Shared Jest config for api-consumer |
| [`seed/`](seed/) | `seed_cqrs.py`, `build_seed_cache.py`, `invite.txt` |
| [`env/`](env/) | `.env.example` template |

## Docker

From `server/`:

```bash
docker compose up -d --build
```

This includes `dev-setup/docker/docker-compose.yml` via the root compose stub.

Direct path:

```bash
docker compose -f dev-setup/docker/docker-compose.yml up -d --build
```

Gateway: **http://localhost:8095**

## Tests & coverage

From `server/`:

```bash
docker compose up -d db db-init
pip install -r requirements-dev.txt
python -m pytest -c dev-setup/python/pytest.ini cqrs/tests -q
python -m pytest -c dev-setup/python/pytest.ini cqrs/tests -q --no-cov
```

Coverage output:

- HTML: `dev-setup/python/htmlcov/`
- XML: `dev-setup/python/coverage.xml`

## Seed data

```bash
python dev-setup/seed/build_seed_cache.py
python dev-setup/seed/seed_cqrs.py --http
```

Or via Docker:

```bash
docker compose --profile seed run --rm seed
```

Cache file remains at [`../data/seed_logs_cache.json`](../data/seed_logs_cache.json).

## Environment

Copy [`env/.env.example`](env/.env.example) to `server/.env` for local overrides.
