#!/usr/bin/env bash
# GCE startup script for the nav.tf VM (Debian 12). Runs as root on every boot;
# idempotent. Installs Docker Engine + the compose plugin and prepares
# /opt/navtf. The stack itself is started by deploy.sh (CI) and then restarted
# by Docker on reboot (restart: unless-stopped).
set -euo pipefail

log() { echo "[navtf-startup] $*"; }

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  log "installing Docker Engine and compose plugin"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -yq ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${codename} stable" \
    >/etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# Default log driver for anything not configured in compose: bounded local files.
# (compose.prod.yml sets gcplogs per service.)
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat >/etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "live-restore": true
}
JSON
  systemctl restart docker || true
fi

systemctl enable --now docker
install -d -m 755 /opt/navtf /opt/navtf/postgres /opt/navtf/backups

# Unattended security updates for the host OS.
if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then
  apt-get install -yq unattended-upgrades
fi

log "ready (docker $(docker --version | awk '{print $3}' | tr -d ,))"
