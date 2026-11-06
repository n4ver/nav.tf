# Production edge image: the built SPA served by Caddy, which also terminates
# TLS and reverse-proxies /api to the services (see deploy/Caddyfile).
# Build from the repo root:
#   docker build -f deploy/docker/web.Dockerfile -t navtf/web .
FROM node:20-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# Same-origin API paths; Caddy maps them to the services.
ENV VITE_COMMAND_BASE_URL=/api/command \
    VITE_QUERY_BASE_URL=/api/query \
    VITE_AUTH_BASE_URL=/api/auth
RUN npm run build

FROM caddy:2.10-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
