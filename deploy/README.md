# Production deployment (Google Cloud)

nav.tf runs in production on **one Compute Engine VM** with a Docker Compose stack, and deploys through **GitHub Actions**.

```text
Internet ─443/80─► caddy ─┬─ SPA (built web app, history-mode fallback)
  (auto-HTTPS)            ├─ /api/command, /api/auth ─► command-service :8001 ─┐
                          └─ /api/query, /health    ─► query-service   :8002 ─┤
                     db (Postgres 15, volume) ◄─────────────────────────────────┤
                     rabbitmq (3.13, volume)  ◄─────────────────────────────────┘
                     api-consumer (internal, polling off by default)
```

Why a VM rather than Cloud Run: the query service holds a RabbitMQ consumer and the rating-rebuild worker, and the command service runs the outbox relay. Both need always-on CPU, and GCP has no managed RabbitMQ.

| Piece | Where |
|---|---|
| Production compose stack | [`compose.prod.yml`](compose.prod.yml) |
| Edge / TLS / routing | [`Caddyfile`](Caddyfile), baked into the `web` image |
| Images | [`docker/server.Dockerfile`](docker/server.Dockerfile), [`docker/web.Dockerfile`](docker/web.Dockerfile), [`../api-consumer/Dockerfile`](../api-consumer/Dockerfile) |
| One-time GCP setup | [`gcp/bootstrap.sh`](gcp/bootstrap.sh), [`gcp/teardown.sh`](gcp/teardown.sh) |
| VM tooling | [`vm/vm-startup.sh`](vm/vm-startup.sh) (Docker install), [`vm/deploy.sh`](vm/deploy.sh) (deploy, rollback, ops) |
| CI/CD | [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml), [`../.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) |

## Cost and the free trial

| Item | Approx. per month |
|---|---|
| e2-medium VM (2 vCPU, 4 GB), us-central1 | ~$25 |
| 30 GB pd-balanced disk + daily snapshots | ~$4 |
| Static IP (in use), Artifact Registry, Secret Manager, logging | ~$1 |

- The **$300 free-trial credit lasts 90 days**, however much is left. When the trial ends, upgrade the billing account to keep the VM running, or run `gcp/teardown.sh`.
- The always-free `e2-micro` (1 GB RAM) is too small for this stack.
- `bootstrap.sh` creates a **$50/month budget** with alerts at 50/90/100%. It's calculated *before* credits, so alerts reflect real usage even while the trial pays for it.

## First-time setup

Prerequisites:
- A GCP project with trial billing enabled.
- A domain whose DNS you control.
- Your SteamID64, so you can become the first admin.

[Cloud Shell](https://shell.cloud.google.com) is the easiest place to run the bootstrap, since it has `gcloud`, `git` and `openssl`.

### 1. Bootstrap the project

```bash
git clone https://github.com/n4ver/logdashboard.git && cd logdashboard
gcloud auth login            # not needed in Cloud Shell
PROJECT_ID=my-navtf-project \
DOMAIN=nav.example.com \
ACME_EMAIL=you@example.com \
BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX \
  ./deploy/gcp/bootstrap.sh
```

Preview the plan first with `DRY_RUN=1`. Re-running the script is safe; existing resources are kept. `gcloud billing accounts list` shows your billing account id.

It creates:
- The Artifact Registry repo `navtf`, keeping the last 10 versions.
- Secret Manager secrets, each a random 64-hex value: JWT secret, seed token, Postgres and RabbitMQ passwords, webhook key. It also creates an empty `navtf-steam-api-key`.
- The VM service account `navtf-vm`, with read access to exactly those secrets and the registry.
- A static IP and firewall rules: 80/443 from anywhere; SSH **only from Google's IAP range**.
- The VM `navtf-prod` (Debian 12, OS Login, Shielded VM) with a daily snapshot schedule (7-day retention).
- Workload Identity Federation, so GitHub Actions in this repo can deploy as `navtf-deployer` **without any keys**.

It prints the static IP and the GitHub variables you need for the next steps.

> The default network's `default-allow-ssh` rule exposes port 22 on every VM to the internet. Deploys go through IAP, so it's safe to delete; the script prints the command.

### 2. DNS

Create an **A record** `nav.example.com → <static IP>`. Caddy obtains the Let's Encrypt certificate automatically on the first request once DNS resolves.

### 3. Steam Web API key (recommended)

Player names are resolved through the Steam Web API. Get a key at <https://steamcommunity.com/dev/apikey> (domain: your `DOMAIN`), then:

```bash
printf %s 'YOUR_KEY' | gcloud secrets versions add navtf-steam-api-key --data-file=- --project=my-navtf-project
```

### 4. GitHub repository variables

Go to **Settings → Secrets and variables → Actions → Variables** and add the values that `bootstrap.sh` printed:

| Variable | Example |
|---|---|
| `GCP_PROJECT_ID` | `my-navtf-project` |
| `GCP_REGION` / `GCP_ZONE` | `us-central1` / `us-central1-a` |
| `GCP_VM_NAME` | `navtf-prod` |
| `GCP_WIF_PROVIDER` | `projects/123…/locations/global/workloadIdentityPools/github/providers/github` |
| `GCP_DEPLOY_SA` | `navtf-deployer@my-navtf-project.iam.gserviceaccount.com` |
| `DOMAIN` | `nav.example.com` |
| `ACME_EMAIL` | `you@example.com` |
| `BOOTSTRAP_ADMIN_STEAM_IDS` | your SteamID64 (comma-separated for several) |
| `API_CONSUMER_POLL_ENABLED` | `false` |

No GitHub *secrets* are needed. Application secrets never leave Secret Manager; the VM reads them itself at deploy time.

To require manual approval for deploys, add reviewers to the `production` environment under **Settings → Environments**.

### 5. Deploy

Merge or push to `main`. **CI** runs the backend, api-consumer and web tests and builds the images. **Deploy** then runs automatically:
1. Builds and pushes `server`, `web` and `api-consumer` images tagged with the commit SHA.
2. Copies `compose.prod.yml` and `deploy.sh` to the VM over IAP.
3. Runs `deploy.sh deploy <sha>`, which:
   - writes `/opt/navtf/.env` (mode 600) from Secret Manager,
   - pulls the images,
   - starts the stack and waits for every health check,
   - **rolls back automatically** to the previous tag if any check fails.

The first deploy can also be started by hand: **Actions → Deploy → Run workflow**.

### 6. Sign in and (optionally) seed

- Open `https://nav.example.com` and sign in with Steam. Accounts listed in `BOOTSTRAP_ADMIN_STEAM_IDS` become admins and can open `/admin`.
- To load the 97 sample matches:

  ```bash
  gcloud compute ssh navtf-prod --zone us-central1-a --tunnel-through-iap -- sudo /opt/navtf/deploy.sh seed
  ```

#### Post-deploy checklist
- [ ] `https://DOMAIN/health` returns `{"status":"ok", …}` with a valid certificate
- [ ] The home page loads, and a deep link (e.g. `/admin`) loads on refresh
- [ ] Steam login returns you to the site, and your account can open `/admin`
- [ ] Ingesting a logs.tf ID in `/admin` shows the match, and its ratings become ready within ~30 s
- [ ] `deploy.sh ops outbox-status` shows `"failed": 0`, and `deploy.sh ops parking-count` shows `0`

## Operations

Run these on the VM. To open a shell:

```bash
gcloud compute ssh navtf-prod --zone us-central1-a --tunnel-through-iap
```

| Task | Command |
|---|---|
| Status / current image tag | `sudo /opt/navtf/deploy.sh status` |
| Recent logs | `sudo /opt/navtf/deploy.sh logs query-service` (all logs are also in **Cloud Logging**: resource *VM Instance*, log `gcplogs-docker-driver`) |
| Roll back to the previous release | `sudo /opt/navtf/deploy.sh rollback`, or **Actions → Deploy → Run workflow** with `image_tag=<older sha>` |
| Outbox health / requeue failed events | `sudo /opt/navtf/deploy.sh ops outbox-status` / `ops outbox-requeue` |
| Parked consumer events | `sudo /opt/navtf/deploy.sh ops parking-count` / `ops parking-replay` |
| Database dump to `/opt/navtf/backups/` | `sudo /opt/navtf/deploy.sh ops backup` |
| Enable matcha.tf auto-ingest | set the GitHub variable `API_CONSUMER_POLL_ENABLED=true` and redeploy |

Delivery guarantees, retries and parking are described in [docs/architecture.md](../docs/architecture.md#delivery-guarantees).

### Backups and restore

- **Daily disk snapshots** (04:00 UTC, kept 7 days) cover everything on the VM, including the Postgres and RabbitMQ volumes.
- **To restore:**
  1. Create a disk from a snapshot: `gcloud compute disks create navtf-restore --source-snapshot=<name> --zone=us-central1-a`.
  2. Stop the VM.
  3. Swap the boot disk (`gcloud compute instances detach-disk` / `attach-disk --boot`).
  4. Start the VM. Docker brings the stack back on boot.
- **Logical dumps:** `ops backup` writes `pg_dumpall` output. Copy it off the VM with `gcloud compute scp --tunnel-through-iap` if you want an off-box copy.

### Rotating a secret

Run `printf %s "$(openssl rand -hex 32)" | gcloud secrets versions add <secret> --data-file=-`, then redeploy.

- **`navtf-jwt-secret`:** signs everyone out.
- **`navtf-postgres-password` or `navtf-rabbitmq-password`:** the existing database and broker volumes keep the *old* credentials. Change them inside the containers first (`ALTER USER navtf PASSWORD …` / `rabbitmqctl change_password navtf …`), then add the new secret version and redeploy.

### Production safety guards

With `APP_ENV=production` (set by `compose.prod.yml`), the services **refuse to start** if:
- the JWT secret is unset, the dev default, or shorter than 32 characters;
- the seed token is the dev default;
- the frontend, Steam realm or Steam return URL isn't `https://`;
- a database or RabbitMQ URL uses the dev credentials (`user:password`, `guest:guest`);
- the in-memory broker is enabled.

FastAPI's `/docs` and `/openapi.json` are disabled unless `API_DOCS_ENABLED=true`. CORS allows only `https://DOMAIN`. See [`server/cqrs/shared/settings.py`](../server/cqrs/shared/settings.py).

## Local production smoke test

You can run the production stack on your own machine with Caddy's internal CA:

```bash
docker build -f deploy/docker/server.Dockerfile -t navtf-local/server:smoke .
docker build -f deploy/docker/web.Dockerfile    -t navtf-local/web:smoke .
docker build -t navtf-local/api-consumer:smoke api-consumer
cat > /tmp/smoke.env <<EOF
DOMAIN=localhost
ACME_EMAIL=ops@example.com
IMAGE_REGISTRY=navtf-local
IMAGE_TAG=smoke
LOG_DRIVER=json-file
POSTGRES_PASSWORD=$(openssl rand -hex 32)
RABBITMQ_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
SEED_SERVICE_TOKEN=$(openssl rand -hex 32)
WEBHOOK_API_KEY=$(openssl rand -hex 32)
EOF
docker compose -p navtf-smoke -f deploy/compose.prod.yml --env-file /tmp/smoke.env up -d --wait
curl -k https://localhost/health
docker compose -p navtf-smoke -f deploy/compose.prod.yml --env-file /tmp/smoke.env run --rm seed
docker compose -p navtf-smoke -f deploy/compose.prod.yml --env-file /tmp/smoke.env down -v
```

## Teardown

```bash
PROJECT_ID=my-navtf-project CONFIRM=my-navtf-project BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX \
  ./deploy/gcp/teardown.sh
```

This deletes the VM (and its data), the IP, firewall rules, registry, secrets, service accounts, the WIF pool and the budget. Automatic snapshots are kept and listed so you can delete them.
