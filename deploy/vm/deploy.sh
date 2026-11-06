#!/usr/bin/env bash
# nav.tf production deploy helper. Runs on the VM as root.
#
#   deploy.sh deploy <image-tag>   install files, render .env, pull, start, verify;
#                                  rolls back to the previous tag if health fails
#   deploy.sh rollback             redeploy the previously deployed tag
#   deploy.sh seed                 one-shot sample data load (97 matches)
#   deploy.sh status               container status and current tag
#   deploy.sh logs [service]       recent logs (also in Cloud Logging)
#   deploy.sh ops <command>        outbox-status | outbox-requeue |
#                                  parking-count | parking-replay | backup
#
# Non-secret config comes from the environment on `deploy` (CI passes it) and is
# persisted to $APP_DIR/config.env for later commands:
#   GCP_PROJECT_ID GCP_REGION DOMAIN ACME_EMAIL
#   BOOTSTRAP_ADMIN_STEAM_IDS API_CONSUMER_POLL_ENABLED (optional)
# Secrets are read from Secret Manager (navtf-*) with the VM service account and
# written to $APP_DIR/.env (mode 600). They never pass through CI.
#
# Testing hooks: APP_DIR, COMPOSE_PROJECT, SECRETS_SOURCE=env (read the secret
# values from the environment), SKIP_REGISTRY_LOGIN=1, SKIP_PULL=1, IMAGE_REGISTRY,
# LOG_DRIVER.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/navtf}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-navtf}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONFIG_KEYS=(GCP_PROJECT_ID GCP_REGION DOMAIN ACME_EMAIL BOOTSTRAP_ADMIN_STEAM_IDS API_CONSUMER_POLL_ENABLED)
# env var name -> Secret Manager secret id
SECRET_MAP=(
  "JWT_SECRET=navtf-jwt-secret"
  "SEED_SERVICE_TOKEN=navtf-seed-token"
  "POSTGRES_PASSWORD=navtf-postgres-password"
  "RABBITMQ_PASSWORD=navtf-rabbitmq-password"
  "WEBHOOK_API_KEY=navtf-webhook-api-key"
  "STEAM_API_KEY=navtf-steam-api-key"
)
OPTIONAL_SECRETS=(STEAM_API_KEY)

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

compose() {
  docker compose --project-name "$COMPOSE_PROJECT" \
    --project-directory "$APP_DIR" \
    -f "$APP_DIR/compose.prod.yml" --env-file "$APP_DIR/.env" "$@"
}

# Reject values that would break the quoted .env format or the shell.
check_value() {
  local key="$1" value="$2"
  if [[ "$value" == *"'"* || "$value" == *$'\n'* ]]; then
    die "$key contains a quote or newline"
  fi
}

install_files() {
  install -d -m 755 "$APP_DIR" "$APP_DIR/postgres" "$APP_DIR/backups"
  if [[ "$SCRIPT_DIR" != "$APP_DIR" ]]; then
    install -m 644 "$SCRIPT_DIR/compose.prod.yml" "$APP_DIR/compose.prod.yml"
    install -m 755 "$SCRIPT_DIR/ensure-cqrs-databases.sh" "$APP_DIR/postgres/ensure-cqrs-databases.sh"
    install -m 755 "$SCRIPT_DIR/deploy.sh" "$APP_DIR/deploy.sh"
  fi
}

save_config() {
  local key tmp
  tmp="$(mktemp "$APP_DIR/.config.XXXXXX")"
  for key in "${CONFIG_KEYS[@]}"; do
    if [[ -n "${!key:-}" ]]; then
      check_value "$key" "${!key}"
      printf "%s='%s'\n" "$key" "${!key}" >>"$tmp"
    fi
  done
  chmod 600 "$tmp"
  mv "$tmp" "$APP_DIR/config.env"
}

load_config() {
  [[ -f "$APP_DIR/config.env" ]] || die "$APP_DIR/config.env missing; run a CI deploy first"
  # shellcheck disable=SC1091
  set -a && source "$APP_DIR/config.env" && set +a
  : "${GCP_PROJECT_ID:?missing}" "${GCP_REGION:?missing}" "${DOMAIN:?missing}" "${ACME_EMAIL:?missing}"
  IMAGE_REGISTRY="${IMAGE_REGISTRY:-${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/navtf}"
}

read_secret() {
  local var="$1" id="$2"
  if [[ "${SECRETS_SOURCE:-gcp}" == "env" ]]; then
    printf '%s' "${!var:-}"
    return
  fi
  gcloud secrets versions access latest --secret="$id" --project="$GCP_PROJECT_ID" 2>/dev/null || true
}

render_env() {
  local tag="$1" tmp entry var id value
  tmp="$(mktemp "$APP_DIR/.env.XXXXXX")"
  chmod 600 "$tmp"
  {
    printf "IMAGE_REGISTRY='%s'\n" "$IMAGE_REGISTRY"
    printf "IMAGE_TAG='%s'\n" "$tag"
    printf "DOMAIN='%s'\nACME_EMAIL='%s'\n" "$DOMAIN" "$ACME_EMAIL"
    printf "BOOTSTRAP_ADMIN_STEAM_IDS='%s'\n" "${BOOTSTRAP_ADMIN_STEAM_IDS:-}"
    printf "API_CONSUMER_POLL_ENABLED='%s'\n" "${API_CONSUMER_POLL_ENABLED:-false}"
    printf "LOG_DRIVER='%s'\n" "${LOG_DRIVER:-gcplogs}"
  } >>"$tmp"
  for entry in "${SECRET_MAP[@]}"; do
    var="${entry%%=*}"
    id="${entry#*=}"
    value="$(read_secret "$var" "$id")"
    if [[ -z "$value" && ! " ${OPTIONAL_SECRETS[*]} " == *" $var "* ]]; then
      rm -f "$tmp"
      die "secret $id is empty or unreadable (run deploy/gcp/bootstrap.sh)"
    fi
    check_value "$var" "$value"
    printf "%s='%s'\n" "$var" "$value" >>"$tmp"
  done
  mv "$tmp" "$APP_DIR/.env"
}

registry_login() {
  [[ "${SKIP_REGISTRY_LOGIN:-0}" == "1" ]] && return
  gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet >/dev/null 2>&1
}

start_stack() {
  local tag="$1"
  render_env "$tag"
  if [[ "${SKIP_PULL:-0}" != "1" ]]; then
    log "pulling images for tag $tag"
    compose pull --quiet || return 1
  fi
  log "starting stack"
  compose up -d --remove-orphans --wait --wait-timeout "$HEALTH_TIMEOUT"
}

check_public_health() {
  # Informational: fails until DNS points at the VM and the certificate is issued.
  if curl -fsS --max-time 10 "https://${DOMAIN}/health" >/dev/null 2>&1; then
    log "public health OK: https://${DOMAIN}/health"
  else
    log "WARNING: https://${DOMAIN}/health not reachable yet (DNS/TLS?). Services are healthy internally."
  fi
}

cmd_deploy() {
  local tag="${1:?usage: deploy.sh deploy <image-tag>}" previous=""
  install_files
  save_config
  load_config
  registry_login
  [[ -f "$APP_DIR/current-tag" ]] && previous="$(cat "$APP_DIR/current-tag")"

  if start_stack "$tag"; then
    if [[ -n "$previous" && "$previous" != "$tag" ]]; then
      printf '%s\n' "$previous" >"$APP_DIR/previous-tag"
    fi
    printf '%s\n' "$tag" >"$APP_DIR/current-tag"
    log "deployed $tag"
    check_public_health
    docker image prune -f --filter "until=168h" >/dev/null || true
    return 0
  fi

  log "deploy of $tag failed health checks"
  compose ps -a >&2 || true
  compose logs --tail 50 command-service query-service >&2 || true
  if [[ -n "$previous" && "$previous" != "$tag" ]]; then
    log "rolling back to $previous"
    start_stack "$previous" || die "rollback to $previous also failed"
    die "deploy of $tag failed; rolled back to $previous"
  fi
  die "deploy of $tag failed and there is no previous tag to roll back to"
}

cmd_rollback() {
  load_config
  registry_login
  [[ -f "$APP_DIR/previous-tag" ]] || die "no previous tag recorded"
  local previous current
  previous="$(cat "$APP_DIR/previous-tag")"
  current="$(cat "$APP_DIR/current-tag" 2>/dev/null || true)"
  start_stack "$previous" || die "rollback to $previous failed"
  printf '%s\n' "$previous" >"$APP_DIR/current-tag"
  [[ -n "$current" ]] && printf '%s\n' "$current" >"$APP_DIR/previous-tag"
  log "rolled back to $previous"
}

cmd_ops() {
  load_config
  case "${1:-}" in
    outbox-status) compose exec -T command-service python -m cqrs.command_service.app.outbox_admin status ;;
    outbox-requeue) compose exec -T command-service python -m cqrs.command_service.app.outbox_admin requeue-failed ;;
    parking-count) compose exec -T query-service python -m cqrs.query_service.app.parking count ;;
    parking-replay) compose exec -T query-service python -m cqrs.query_service.app.parking replay ;;
    backup)
      local out
      out="$APP_DIR/backups/navtf-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
      compose exec -T db pg_dumpall -U navtf | gzip >"$out"
      chmod 600 "$out"
      log "wrote $out"
      ;;
    *) die "unknown ops command '${1:-}' (outbox-status|outbox-requeue|parking-count|parking-replay|backup)" ;;
  esac
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    deploy) cmd_deploy "$@" ;;
    rollback) cmd_rollback ;;
    seed) load_config && compose --profile seed run --rm seed ;;
    status)
      load_config
      log "current tag: $(cat "$APP_DIR/current-tag" 2>/dev/null || echo none)"
      compose ps -a
      ;;
    logs) load_config && compose logs --tail 200 "$@" ;;
    ops) cmd_ops "$@" ;;
    *) sed -n '2,14p' "$0" >&2; exit 2 ;;
  esac
}

main "$@"
