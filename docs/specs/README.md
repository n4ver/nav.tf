# TF2 Analytics API & CDM Specifications

Contract documentation for the CQRS boundary.

| Artifact | Path | Description |
|----------|------|-------------|
| OpenAPI 3.0 | [`openapi.yaml`](openapi.yaml) | HTTP API exposed via the nginx gateway (`:8095`) |
| CDM index | [`cdm/README.md`](cdm/README.md) | Canonical Data Model catalog — one YAML file per model |

## Gateway vs service paths

The Vue app and Docker stack call the **gateway** paths below. FastAPI services listen on internal paths (shown in `x-internal-path` on each operation).

| Gateway prefix | Upstream | Internal prefix |
|----------------|----------|-----------------|
| `/api/auth/` | command-service:8001 | `/api/v1/auth/` |
| `/api/command/` | command-service:8001 | `/api/v1/commands/` |
| `/api/query/` | query-service:8002 | `/api/v1/queries/` |

## Regenerating CDM files

CDM YAML files under `cdm/models/` are generated from the Python source definitions:

```bash
python docs/specs/generate_cdm.py
```

Run this after changing `shared/schemas.py`, `shared/events.py`, or persistence models.
