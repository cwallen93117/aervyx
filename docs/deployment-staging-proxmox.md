# Aervyx Staging Deployment on Proxmox Ubuntu 24.04.4

This runbook turns a Proxmox Ubuntu Server 24.04.4 VM into the staging host for Aervyx.

## Target Shape

- VM role: staging only
- tracked branch: `staging`
- repo location: `/srv/aervyx-staging/repo`
- web hostname: `https://staging.aervyx.net`
- direct API/mobile hostname: `https://api-staging.aervyx.net`
- GitHub webhook hostname: `https://deploy-staging.aervyx.net`

The browser app should continue using same-origin `/backend` requests. The API hostname exists for mobile and direct backend tests.

## VM Baseline

Recommended Proxmox sizing:

- 4 vCPU
- 8 GB RAM
- 80 GB disk
- VirtIO disk/network
- QEMU guest agent enabled
- static DHCP reservation or fixed LAN IP

Install on the VM:

- `qemu-guest-agent`
- `git`
- `curl`
- `ca-certificates`
- Docker
- Docker Compose plugin
- `ufw`
- `fail2ban`

Repo helper:

- `deploy/staging/bootstrap-ubuntu.sh`

## Server Layout

Use these directories:

- `/srv/aervyx-staging/repo`
- `/srv/aervyx-staging/logs`
- `/srv/aervyx-staging/backups`
- `/srv/aervyx-staging/hooks`

Keep secrets only on the VM:

- `/srv/aervyx-staging/repo/.env.production`
- `/srv/aervyx-staging/repo/backend/.env.production`
- `/srv/aervyx-staging/repo/frontend/.env.production`
- `/srv/aervyx-staging/repo/deploy/cloudflared/config.yml`
- Cloudflare tunnel credential JSON beside `config.yml`
- `/etc/default/aervyx-staging-webhook`

## Branch Flow

The staging VM should only deploy `origin/staging`.

Recommended local push pattern:

```powershell
git push origin HEAD:staging
```

That lets you keep developing locally however you want while staging only follows the commit you explicitly promote.

## Initial Server Setup

1. Bootstrap the VM as root:

```bash
sudo bash deploy/staging/bootstrap-ubuntu.sh
```

2. Clone the repo as the deploy user:

```bash
sudo -u deploy git clone https://github.com/cwallen93117/aervyx.git /srv/aervyx-staging/repo
cd /srv/aervyx-staging/repo
sudo -u deploy git fetch origin
sudo -u deploy git checkout -b staging origin/staging
```

3. Copy the staging env examples into place and replace secrets:

- `deploy/staging/examples/root.env.production.example` -> `.env.production`
- `deploy/staging/examples/backend.env.production.example` -> `backend/.env.production`
- `deploy/staging/examples/frontend.env.production.example` -> `frontend/.env.production`

4. Copy the staging tunnel example:

- `deploy/cloudflared/staging.config.example.yml` -> `deploy/cloudflared/config.yml`

Then replace the tunnel ID and place the real credentials JSON beside it.

## Staging Environment Values

Use these hostnames:

- `staging.aervyx.net`
- `api-staging.aervyx.net`
- `deploy-staging.aervyx.net`

Backend env should include:

- `APP_PUBLIC_URL=https://staging.aervyx.net`
- `API_PUBLIC_URL=https://api-staging.aervyx.net`
- `CORS_ORIGINS=["https://staging.aervyx.net","https://api-staging.aervyx.net"]`
- `ALLOWED_HOSTS` updated for staging names

Frontend env should include:

- `NEXT_PUBLIC_API_BASE_URL=/backend`
- `BACKEND_INTERNAL_URL=http://backend:8000`
- `APP_PUBLIC_URL=https://staging.aervyx.net`
- `API_PUBLIC_URL=https://api-staging.aervyx.net`

Root env should include:

- `COMPOSE_PROJECT_NAME=aervyx-staging`
- strong Postgres credentials

## Cloudflare Tunnel and Access

Create a Cloudflare Tunnel and attach DNS routes for:

- `staging.aervyx.net`
- `api-staging.aervyx.net`
- `deploy-staging.aervyx.net`

Protection boundary:

- `staging.aervyx.net`: behind Cloudflare Access
- `api-staging.aervyx.net`: not behind Access
- `deploy-staging.aervyx.net`: not behind Access, but protected by GitHub HMAC validation

Recommended Access policy:

- allow only your email and a small tester list
- apply before the app login page
- keep Aervyx app login enabled as the second layer

## Webhook Auto-Deploy

Install the webhook listener env file:

- copy `deploy/staging/examples/aervyx-staging-webhook.env.example` to `/etc/default/aervyx-staging-webhook`
- replace `WEBHOOK_SECRET`

Install the systemd unit:

```bash
sudo cp deploy/staging/systemd/aervyx-staging-webhook.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aervyx-staging-webhook.service
```

Listener details:

- bind: `0.0.0.0:9100`
- health: `http://127.0.0.1:9100/health`
- webhook path: `/github/deploy-staging`

If you keep `ufw` enabled, allow the Docker bridge subnet to reach port `9100` on the VM so the `cloudflared` container can reach the host-side listener through `host.docker.internal`.

GitHub webhook settings:

- payload URL: `https://deploy-staging.aervyx.net/github/deploy-staging`
- content type: `application/json`
- secret: match `/etc/default/aervyx-staging-webhook`
- event: pushes only

Deploy behavior:

- validates `X-Hub-Signature-256`
- accepts only `refs/heads/staging`
- runs `deploy/staging/deploy-staging.sh`
- writes logs under `/srv/aervyx-staging/logs`

## Deploy Script

Run manually when needed:

```bash
sudo -u deploy /srv/aervyx-staging/repo/deploy/staging/deploy-staging.sh
```

What it does:

1. `git fetch origin`
2. checks out `staging`
3. hard-resets to `origin/staging`
4. rebuilds with `docker compose --env-file .env.production -f docker-compose.prod.yml build`
5. starts `db`, `backend`, and `frontend`
6. starts `cloudflared` when `deploy/cloudflared/config.yml` exists
7. runs backend and frontend health checks
8. records the deployed SHA in `/srv/aervyx-staging/hooks/last-deployed.txt`

For private Meshtastic MQTT setup, see `docs/private-mqtt-broker.md`. The stack
includes Mosquitto by default; public TLS on `8883` is enabled with VM-managed
certificates, credentials, and a listener snippet.

## Backups

Install the backup timer:

```bash
sudo cp deploy/staging/systemd/aervyx-staging-backup.service /etc/systemd/system/
sudo cp deploy/staging/systemd/aervyx-staging-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aervyx-staging-backup.timer
```

Backups created:

- nightly `pg_dump` under `/srv/aervyx-staging/backups/postgres`
- uploads-volume archive under `/srv/aervyx-staging/backups/uploads`

Use Proxmox snapshots before major upgrades or branch jumps.

## Rollback

Rollback path:

1. move `staging` back to a known-good SHA or push an older commit to `origin/staging`
2. rerun `deploy/staging/deploy-staging.sh`

Manual example:

```bash
cd /srv/aervyx-staging/repo
git fetch origin
git checkout staging
git reset --hard <known-good-sha>
sudo -u deploy ./deploy/staging/deploy-staging.sh
```

## Validation Checklist

Private validation before enabling the tunnel:

- `docker compose --env-file .env.production -f docker-compose.prod.yml build`
- `docker compose --env-file .env.production -f docker-compose.prod.yml up -d db backend frontend`
- backend health works privately
- frontend login works privately

Public staging validation after enabling the tunnel:

- `https://staging.aervyx.net` prompts for Cloudflare Access
- login and dashboard load after Access
- `/backend` rewrite works
- `https://api-staging.aervyx.net/health` works
- live tracking SSE is not buffered/broken
- mobile can authenticate against `api-staging.aervyx.net`
- logbook upload/download/replay works
- admin site tools work

Webhook validation:

- pushes to non-`staging` branches do nothing
- pushes to `staging` trigger a deploy
- failed builds do not silently change the last deployed SHA
