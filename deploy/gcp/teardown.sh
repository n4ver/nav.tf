#!/usr/bin/env bash
# Delete everything bootstrap.sh created for nav.tf. DESTRUCTIVE: the VM disk
# (and with it the Postgres data) is deleted. Automatic snapshots are kept (the
# schedule uses keep-auto-snapshots) and listed at the end so you can delete
# or restore them.
#
#   PROJECT_ID=my-proj CONFIRM=my-proj ./deploy/gcp/teardown.sh
#
# Optional: REGION, ZONE, VM_NAME, WIF_POOL, BILLING_ACCOUNT (also deletes navtf-budget).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
if [[ "${CONFIRM:-}" != "$PROJECT_ID" ]]; then
  echo "Refusing to run: set CONFIRM=${PROJECT_ID} to delete nav.tf resources in that project." >&2
  exit 1
fi
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-${REGION}-a}"
VM_NAME="${VM_NAME:-navtf-prod}"
WIF_POOL="${WIF_POOL:-github}"
BILLING_ACCOUNT="${BILLING_ACCOUNT:-}"

g() { gcloud --project="$PROJECT_ID" --quiet "$@"; }
try() { "$@" || echo "  (skipped: $*)"; }

echo "==> VM, IP, firewall, snapshot schedule"
try g compute instances delete "$VM_NAME" --zone="$ZONE"
try g compute addresses delete navtf-ip --region="$REGION"
try g compute firewall-rules delete navtf-allow-web
try g compute firewall-rules delete navtf-allow-iap-ssh
try g compute resource-policies delete navtf-daily-snapshots --region="$REGION"

echo "==> Artifact Registry, secrets"
try g artifacts repositories delete navtf --location="$REGION"
for secret in navtf-jwt-secret navtf-seed-token navtf-postgres-password \
  navtf-rabbitmq-password navtf-webhook-api-key navtf-steam-api-key; do
  try g secrets delete "$secret"
done

echo "==> Workload Identity Federation, service accounts"
try g iam workload-identity-pools delete "$WIF_POOL" --location=global
try g iam service-accounts delete "navtf-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
try g iam service-accounts delete "navtf-vm@${PROJECT_ID}.iam.gserviceaccount.com"

if [[ -n "$BILLING_ACCOUNT" ]]; then
  echo "==> Budget"
  budget="$(gcloud billing budgets list --billing-project="$PROJECT_ID" \
    --billing-account="$BILLING_ACCOUNT" \
    --filter='displayName=navtf-budget' --format='value(name)' 2>/dev/null || true)"
  [[ -n "$budget" ]] && try gcloud billing budgets delete "$budget" \
    --billing-project="$PROJECT_ID" --quiet
fi

echo "==> Remaining snapshots (delete with: gcloud compute snapshots delete NAME --project=${PROJECT_ID})"
g compute snapshots list --filter="sourceDisk~${VM_NAME}" --format='table(name,creationTimestamp,diskSizeGb)' || true
echo "Note: a deleted workload identity pool is kept for 30 days and blocks re-creating"
echo "the same id; bootstrap.sh would need WIF_POOL changed within that window."
