#!/usr/bin/env bash
# One-time (idempotent) Google Cloud setup for nav.tf production.
#
# Creates: APIs, Artifact Registry repo, Secret Manager secrets, service
# accounts, static IP, firewall rules, a snapshot schedule, the VM, Workload
# Identity Federation for GitHub Actions, and (optionally) a billing budget.
# Safe to re-run: existing resources are left as they are.
#
# Usage (from the repo root, after `gcloud auth login`):
#   PROJECT_ID=my-proj DOMAIN=nav.example.com ACME_EMAIL=me@example.com \
#     BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX ./deploy/gcp/bootstrap.sh
#
# Optional: REGION (us-central1), ZONE (<region>-a), VM_NAME (navtf-prod),
#   MACHINE_TYPE (e2-medium), DISK_SIZE_GB (30), GITHUB_REPO (n4ver/logdashboard),
#   BUDGET_USD (50), WIF_POOL (github), DRY_RUN=1 (print mutating commands instead of running them).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${DOMAIN:?set DOMAIN (e.g. nav.example.com)}"
: "${ACME_EMAIL:?set ACME_EMAIL (contact address for TLS certificate notices)}"
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-${REGION}-a}"
VM_NAME="${VM_NAME:-navtf-prod}"
MACHINE_TYPE="${MACHINE_TYPE:-e2-medium}"
DISK_SIZE_GB="${DISK_SIZE_GB:-30}"
GITHUB_REPO="${GITHUB_REPO:-n4ver/logdashboard}"
BUDGET_USD="${BUDGET_USD:-50}"
BILLING_ACCOUNT="${BILLING_ACCOUNT:-}"
DRY_RUN="${DRY_RUN:-0}"

AR_REPO=navtf
IP_NAME=navtf-ip
NETWORK_TAG=navtf-web
SNAPSHOT_POLICY=navtf-daily-snapshots
VM_SA_ID=navtf-vm
DEPLOY_SA_ID=navtf-deployer
WIF_POOL="${WIF_POOL:-github}"
WIF_PROVIDER=github
VM_SA="${VM_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA="${DEPLOY_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
GENERATED_SECRETS=(navtf-jwt-secret navtf-seed-token navtf-postgres-password navtf-rabbitmq-password navtf-webhook-api-key)
MANUAL_SECRETS=(navtf-steam-api-key)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STARTUP_SCRIPT="${SCRIPT_DIR}/../vm/vm-startup.sh"

g() { gcloud --project="$PROJECT_ID" --quiet "$@"; }
step() { printf '\n==> %s\n' "$*"; }
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    # stderr, so callers' >/dev/null does not hide the plan.
    {
      printf '  [dry-run] gcloud --project=%s' "$PROJECT_ID"
      printf ' %q' "$@"
      printf '\n'
    } >&2
  elif [[ " $* " == *" add-iam-policy-binding "* ]]; then
    # New service accounts take a few seconds to propagate to IAM.
    local attempt
    for attempt in 1 2 3 4 5 6; do
      g "$@" && return 0
      echo "  IAM binding not accepted yet (attempt ${attempt}/6); retrying in 10s" >&2
      sleep 10
    done
    return 1
  else
    g "$@"
  fi
}
exists() { g "$@" >/dev/null 2>&1; }

step "Project ${PROJECT_ID} (region ${REGION}, zone ${ZONE})"
PROJECT_NUMBER="$(g projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null || echo PROJECT_NUMBER)"

step "Enabling APIs"
apis=(compute.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com iap.googleapis.com
  oslogin.googleapis.com logging.googleapis.com monitoring.googleapis.com
  cloudresourcemanager.googleapis.com)
[[ -n "$BILLING_ACCOUNT" ]] && apis+=(billingbudgets.googleapis.com)
run services enable "${apis[@]}"

step "Artifact Registry repository ${AR_REPO}"
if ! exists artifacts repositories describe "$AR_REPO" --location="$REGION"; then
  run artifacts repositories create "$AR_REPO" --location="$REGION" \
    --repository-format=docker --description="nav.tf container images"
fi
policy_file="$(mktemp)"
trap 'rm -f "$policy_file"' EXIT
cat >"$policy_file" <<'JSON'
[
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 10}},
  {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"olderThan": "2592000s"}}
]
JSON
run artifacts repositories set-cleanup-policies "$AR_REPO" --location="$REGION" \
  --policy="$policy_file" --no-dry-run

step "Secrets"
for secret in "${GENERATED_SECRETS[@]}"; do
  if exists secrets describe "$secret"; then
    echo "  $secret exists (kept)"
  elif [[ "$DRY_RUN" == "1" ]]; then
    echo "  [dry-run] create $secret with a random 64-hex-char value"
  else
    openssl rand -hex 32 | tr -d '\n' |
      g secrets create "$secret" --replication-policy=automatic --data-file=-
  fi
done
for secret in "${MANUAL_SECRETS[@]}"; do
  if ! exists secrets describe "$secret"; then
    run secrets create "$secret" --replication-policy=automatic
  fi
done

step "Service accounts"
if ! exists iam service-accounts describe "$VM_SA"; then
  run iam service-accounts create "$VM_SA_ID" --display-name="nav.tf VM runtime"
fi
if ! exists iam service-accounts describe "$DEPLOY_SA"; then
  run iam service-accounts create "$DEPLOY_SA_ID" --display-name="nav.tf GitHub deployer"
fi
for role in roles/logging.logWriter roles/monitoring.metricWriter; do
  run projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${VM_SA}" \
    --role="$role" --condition=None >/dev/null
done
run artifacts repositories add-iam-policy-binding "$AR_REPO" --location="$REGION" \
  --member="serviceAccount:${VM_SA}" --role=roles/artifactregistry.reader >/dev/null
for secret in "${GENERATED_SECRETS[@]}" "${MANUAL_SECRETS[@]}"; do
  run secrets add-iam-policy-binding "$secret" --member="serviceAccount:${VM_SA}" \
    --role=roles/secretmanager.secretAccessor >/dev/null
done
run artifacts repositories add-iam-policy-binding "$AR_REPO" --location="$REGION" \
  --member="serviceAccount:${DEPLOY_SA}" --role=roles/artifactregistry.writer >/dev/null
for role in roles/compute.osAdminLogin roles/iap.tunnelResourceAccessor roles/compute.viewer; do
  run projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${DEPLOY_SA}" \
    --role="$role" --condition=None >/dev/null
done
# OS Login SSH to a VM that runs as navtf-vm requires actAs on that account.
run iam service-accounts add-iam-policy-binding "$VM_SA" \
  --member="serviceAccount:${DEPLOY_SA}" --role=roles/iam.serviceAccountUser >/dev/null

step "Network: static IP and firewall"
if ! exists compute addresses describe "$IP_NAME" --region="$REGION"; then
  run compute addresses create "$IP_NAME" --region="$REGION" --network-tier=PREMIUM
fi
if ! exists compute firewall-rules describe navtf-allow-web; then
  run compute firewall-rules create navtf-allow-web --network=default --direction=INGRESS \
    --allow=tcp:80,tcp:443,udp:443 --source-ranges=0.0.0.0/0 --target-tags="$NETWORK_TAG"
fi
if ! exists compute firewall-rules describe navtf-allow-iap-ssh; then
  run compute firewall-rules create navtf-allow-iap-ssh --network=default --direction=INGRESS \
    --allow=tcp:22 --source-ranges=35.235.240.0/20 --target-tags="$NETWORK_TAG"
fi
if exists compute firewall-rules describe default-allow-ssh; then
  echo "  NOTE: 'default-allow-ssh' opens port 22 to the internet for every VM in the"
  echo "        default network. SSH here goes through IAP, so you can remove it:"
  echo "        gcloud compute firewall-rules delete default-allow-ssh --project=${PROJECT_ID}"
fi

step "Snapshot schedule ${SNAPSHOT_POLICY} (daily, 7-day retention)"
if ! exists compute resource-policies describe "$SNAPSHOT_POLICY" --region="$REGION"; then
  run compute resource-policies create snapshot-schedule "$SNAPSHOT_POLICY" --region="$REGION" \
    --daily-schedule --start-time=04:00 --max-retention-days=7 \
    --on-source-disk-delete=keep-auto-snapshots
fi

step "VM ${VM_NAME} (${MACHINE_TYPE}, Debian 12, ${DISK_SIZE_GB} GB)"
if ! exists compute instances describe "$VM_NAME" --zone="$ZONE"; then
  run compute instances create "$VM_NAME" --zone="$ZONE" --machine-type="$MACHINE_TYPE" \
    --image-family=debian-12 --image-project=debian-cloud \
    --boot-disk-size="${DISK_SIZE_GB}GB" --boot-disk-type=pd-balanced \
    --address="$IP_NAME" --network-tier=PREMIUM --tags="$NETWORK_TAG" \
    --service-account="$VM_SA" --scopes=cloud-platform \
    --metadata=enable-oslogin=TRUE \
    --metadata-from-file=startup-script="$STARTUP_SCRIPT" \
    --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring
  run compute disks add-resource-policies "$VM_NAME" --zone="$ZONE" \
    --resource-policies="$SNAPSHOT_POLICY"
else
  echo "  exists (kept). Updating its startup script."
  run compute instances add-metadata "$VM_NAME" --zone="$ZONE" \
    --metadata-from-file=startup-script="$STARTUP_SCRIPT"
fi

step "Workload Identity Federation for ${GITHUB_REPO}"
if ! exists iam workload-identity-pools describe "$WIF_POOL" --location=global; then
  run iam workload-identity-pools create "$WIF_POOL" --location=global \
    --display-name="GitHub Actions"
fi
if ! exists iam workload-identity-pools providers describe "$WIF_PROVIDER" \
  --workload-identity-pool="$WIF_POOL" --location=global; then
  run iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
    --workload-identity-pool="$WIF_POOL" --location=global \
    --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'"
fi
run iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}" \
  >/dev/null

if [[ -n "$BILLING_ACCOUNT" ]]; then
  step "Billing budget (\$${BUDGET_USD}, gross of trial credits)"
  # The Budgets API needs a quota project when called with user credentials
  # (--billing-project); without it the call fails with a permission error.
  if gcloud billing budgets list --billing-project="$PROJECT_ID" \
    --billing-account="$BILLING_ACCOUNT" \
    --format='value(displayName)' 2>/dev/null | grep -qx "navtf-budget"; then
    echo "  navtf-budget exists (kept)"
  elif [[ "$DRY_RUN" == "1" ]]; then
    echo "  [dry-run] create budget navtf-budget for ${BUDGET_USD} USD"
  # Exclude credits so alerts reflect real usage while the trial credit pays for it.
  elif ! gcloud billing budgets create --billing-project="$PROJECT_ID" \
    --billing-account="$BILLING_ACCOUNT" \
    --display-name=navtf-budget --budget-amount="${BUDGET_USD}USD" \
    --filter-projects="projects/${PROJECT_ID}" --credit-types-treatment=exclude-all-credits \
    --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0; then
    # Optional step: don't let it hide the next-steps summary below.
    echo "  WARNING: budget not created (see error above). Everything else is set up."
    echo "  Create one later in the console: Billing -> Budgets & alerts."
  fi
fi

IP_ADDRESS="$(g compute addresses describe "$IP_NAME" --region="$REGION" --format='value(address)' 2>/dev/null || echo '<static-ip>')"

cat <<EOF

==> Done. Next steps (details in deploy/README.md):

1. DNS: create an A record   ${DOMAIN}  ->  ${IP_ADDRESS}

2. Steam Web API key (optional but recommended, for player names):
   printf %s 'YOUR_KEY' | gcloud secrets versions add navtf-steam-api-key --data-file=- --project=${PROJECT_ID}

3. GitHub -> Settings -> Secrets and variables -> Actions -> Variables:
   GCP_PROJECT_ID            ${PROJECT_ID}
   GCP_REGION                ${REGION}
   GCP_ZONE                  ${ZONE}
   GCP_VM_NAME               ${VM_NAME}
   GCP_WIF_PROVIDER          projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}
   GCP_DEPLOY_SA             ${DEPLOY_SA}
   DOMAIN                    ${DOMAIN}
   ACME_EMAIL                ${ACME_EMAIL}
   BOOTSTRAP_ADMIN_STEAM_IDS <your SteamID64>
   API_CONSUMER_POLL_ENABLED false

4. Push to main (or run the Deploy workflow manually).
EOF
