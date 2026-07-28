#!/bin/bash
set -euo pipefail

export PGHOST="${PGHOST:-db}"
export PGPORT="${PGPORT:-5432}"
export PGPASSWORD="${PGPASSWORD:-$POSTGRES_PASSWORD}"

psql=(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB")

for db in cqrs_command cqrs_query; do
  exists="$("${psql[@]}" -tAc "SELECT 1 FROM pg_database WHERE datname='${db}'")"
  if [[ "$exists" != "1" ]]; then
    echo "Creating database ${db}"
    "${psql[@]}" -c "CREATE DATABASE ${db}"
    "${psql[@]}" -c "GRANT ALL PRIVILEGES ON DATABASE ${db} TO \"${POSTGRES_USER}\""
  else
    echo "Database ${db} already exists"
  fi
done