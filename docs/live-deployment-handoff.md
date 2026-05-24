# Live Deployment Handoff

This document is the current handoff for the live Aervyx deployment.

It describes the production-like VM, the public Cloudflare setup, the deploy flow, and the important internal naming mismatches that a follow-on Claude session must understand before changing infrastructure.

## Public Endpoints

- `https://aervyx.net`
  - public marketing site, login, and dashboard entry
- `https://api.aervyx.net`
  - public direct backend/mobile API hostname
- `https://deploy.aervyx.net/health`
  - public health endpoint for the deploy listener
- GitHub webhook payload URL:
  - `https://deploy.aervyx.net/github/deploy-staging`

The public website is not behind Cloudflare Access.
Authentication is currently the app's own login flow.

## Current Live Branch Flow

- `main` is the production branch.
- `staging` is for pre-production testing.
- The server-side webhook listener is configured to accept both `refs/heads/main` and `refs/heads/staging`.
- The old safe snapshot is preserved as tag:
  - `archive/safe-working-state-2026-03-23`

Current expected workflow:

1. Edit code locally with Claude Code CLI + gstack/VoltAgent agents
2. Commit and push to `staging`
3. Webhook auto-deploys to `staging.aervyx.net` for review
4. When happy, merge `staging` → `main` → auto-deploys to `aervyx.net`

## Infrastructure Shape

### Proxmox Host

- host UI:
  - `https://192.168.87.50:8006`
- node hostname:
  - `pve`

### Ubuntu VM

- VM ID:
  - `100`
- VM name:
  - `aervyx-staging`
- OS:
  - Ubuntu Server `24.04.4 LTS`
- current LAN IP:
  - `192.168.87.94`
- resources:
  - 8 vCPU, 16 GB RAM, 120 GB disk
- Proxmox snapshot:
  - `pre-dev-migration-20260403` (taken before dev migration)

Important:

- The VM and internal paths still use the old `staging` naming.
- Public DNS and deploy behavior are live/final-domain now.
- Do not casually rename the internal `aervyx-staging` paths or services without coordinating all dependent pieces first.

## Server Layout

The live repo and operational files are currently on the VM at:

- prod repo:
  - `/srv/aervyx-staging/repo`
- staging repo:
  - `/srv/aervyx-staging/staging-repo`
- logs:
  - `/srv/aervyx-staging/logs`
- backups:
  - `/srv/aervyx-staging/backups`
- hooks/state:
  - `/srv/aervyx-staging/hooks`

## Runtime Components

### Production Docker Compose Stack

The prod app runs from:

- `/srv/aervyx-staging/repo/docker-compose.prod.yml`

Containers:

- `aervyx-prod-frontend-1`
- `aervyx-prod-backend-1`
- `aervyx-prod-db-1`
- `aervyx-prod-mosquitto-1`

Docker network: `aervyx-prod_default`

### Cloudflare Tunnel Connector

The live tunnel is a remotely managed Cloudflare Tunnel named:

- `aervyx`

The connector is running as a standalone Docker container:

- `aervyx-cloudflared`

It is attached to:

- `aervyx-staging_default`

It is not currently driven by the repo's old `deploy/cloudflared/config.yml` flow.
Instead, it runs from a tunnel token stored on the VM.

Token file location:

- `/srv/aervyx-staging/hooks/cloudflared.env`

Do not commit that file or expose its contents in docs.

### Webhook Listener

The webhook listener is a host-side systemd service:

- `aervyx-staging-webhook.service`

Environment file:

- `/etc/default/aervyx-staging-webhook`

Important current values in that env file:

- `BRANCH=main`
- `DEPLOY_PATH=/github/deploy-staging`

Important mismatch:

- even though the live branch is now `main`, the webhook path still uses:
  - `/github/deploy-staging`

That path is intentionally still in use and is part of the live GitHub webhook configuration.
Do not rename it casually unless you also update GitHub and retest the public webhook path.

### Backups

Nightly backups are enabled through:

- `aervyx-staging-backup.timer`
- `aervyx-staging-backup.service`

Backup script:

- `/srv/aervyx-staging/repo/deploy/staging/backup-staging.sh`

Backup outputs:

- PostgreSQL dumps under:
  - `/srv/aervyx-staging/backups/postgres`
- uploads archives under:
  - `/srv/aervyx-staging/backups/uploads`

## Cloudflare Route Mapping

The Cloudflare Tunnel (id: `129d4665-b4f4-4e03-87c7-c3debbf59eb5`) routes:

Public (no Access gate):
- `aervyx.net` -> `http://aervyx-prod-frontend-1:3000`
- `api.aervyx.net` -> `http://aervyx-prod-backend-1:8000`
- `deploy.aervyx.net` -> `http://host.docker.internal:9100`

Staging (behind Cloudflare Access, Charles's email only):
- `staging.aervyx.net` -> `http://aervyx-staging-frontend-1:3000`
- `api-staging.aervyx.net` -> `http://aervyx-staging-backend-1:8000`

Why these are plain `http://` origins:

- Cloudflare terminates public HTTPS
- the tunnel then forwards internally over private Docker/local networking
- the frontend/backend containers are not serving their own public TLS certificates

## GitHub Webhook

Current live repo webhook target:

- `https://deploy.aervyx.net/github/deploy-staging`

Expected event:

- `push`

Current intended branch behavior:

- pushes to `main` should deploy
- pushes to other branches should be ignored by the listener

## Current Environment Values On The VM

The VM's untracked production env files were updated to the final public hostnames:

- backend:
  - `APP_PUBLIC_URL=https://aervyx.net`
  - `API_PUBLIC_URL=https://api.aervyx.net`
  - `CORS_ORIGINS=["https://aervyx.net","https://api.aervyx.net"]`
  - `ALLOWED_HOSTS` includes `aervyx.net` and `api.aervyx.net`
- frontend:
  - `APP_PUBLIC_URL=https://aervyx.net`
  - `API_PUBLIC_URL=https://api.aervyx.net`
  - `NEXT_PUBLIC_API_BASE_URL=/backend`
  - `NEXT_PUBLIC_STREAM_API_BASE_URL=https://api.aervyx.net`

The browser app keeps ordinary REST calls on same-origin `/backend`, but the
public Watch Live SSE connection uses the direct API hostname so streamed
position events do not pass through the Next.js rewrite layer.

The repo-tracked env examples still describe earlier staging-oriented shapes in places.
For the live server, trust the actual VM env files over older draft docs.

## Deploy Mechanics

The deploy script still lives at:

- `/srv/aervyx-staging/repo/deploy/staging/deploy-staging.sh`

Important:

- the file name still says `staging`
- the live server now uses it for `main` because the webhook service exports `BRANCH=main`

The script currently:

1. fetches `origin`
2. checks out the branch from `BRANCH`
3. hard-resets to `origin/<branch>`
4. rebuilds backend/frontend images
5. starts `db`, `backend`, and `frontend`
6. records the deployed SHA in:
   - `/srv/aervyx-staging/hooks/last-deployed.txt`

Health checks were recently fixed so they match the real container contents and retry during startup.

## Validation That Was Actually Performed

Confirmed during live setup:

- `https://aervyx.net/login` returns `200`
- `https://api.aervyx.net/health` returns `{"status":"ok"}`
- `https://deploy.aervyx.net/health` returns `{"status":"ok"}`
- local signed webhook simulations against the VM succeeded
- the VM fetched and redeployed newer commits correctly
- the live branch switch from `staging` to `main` was tested through the webhook listener path

## Secrets And Sensitive Files

Do not commit or expose:

- `/srv/aervyx-staging/hooks/cloudflared.env`
- `/etc/default/aervyx-staging-webhook`
- `/srv/aervyx-staging/repo/.env.production`
- `/srv/aervyx-staging/repo/backend/.env.production`
- `/srv/aervyx-staging/repo/frontend/.env.production`
Secrets are intentionally server-local now.

## Current Operational Caveats

- Internal names still say `staging` in multiple places even though the public deployment is live/final-domain.
- The public site is not behind Cloudflare Access.
- The app login is the current only user-facing gate.
- The Cloudflare tunnel is live via a token-managed connector container, not the older repo-draft credentials-file model.
- If someone reads `docs/deployment-staging-proxmox.md` or `docs/deployment-cloudflare-tunnel.md` literally, they will be misled in places unless they cross-check this document.
- The alpha stack, OpenClaw workflow, dev stack (hot-reload), code-server, and OpenHands have all been decommissioned and removed.
- Development is done locally with Claude Code CLI, gstack, and VoltAgent agents. Code is pushed to staging for testing.
- The staging stack starts on-demand when pushing to the staging branch.

## What Claude Should Trust First

For deployment/infrastructure questions, trust in this order:

1. this document
2. the actual VM state
3. `CLAUDE.md`
4. `docs/claude-handoff-manual.md`
5. older deployment drafts only as historical context
