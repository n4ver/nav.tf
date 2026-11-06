# Image for the command and query services (one image, two commands). Production
# (deploy/compose.prod.yml) and local development (compose.yaml) both build it.
# Build from the repo root:
#   docker build -f deploy/docker/server.Dockerfile -t navtf/server .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY server/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY server/cqrs ./cqrs
# Seed tooling + cache for the optional one-shot `seed` compose profile.
COPY server/seed ./seed
COPY server/data/seed_logs_cache.json ./data/seed_logs_cache.json

USER app

EXPOSE 8001 8002
# Overridden per service in deploy/compose.prod.yml.
CMD ["uvicorn", "cqrs.query_service.app.main:app", "--host", "0.0.0.0", "--port", "8002"]
