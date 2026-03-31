# Aervyx

Aervyx is an open-source hang gliding and paragliding competition platform. It combines event setup, turnpoint and airspace management, task building, IGC ingestion, GAP-style scoring, results, and a public-facing marketing site in one stack.

## What The Codebase Does

- Public marketing landing page at `/`
- Themed auth entry at `/login`
- Protected competition workspace at `/dashboard`
- Admin workflows for events, participants, turnpoints, airspace, tasks, scoring parameters, uploads, and manual scoring runs
- Pilot and public-safe results views with task definitions and task maps

## Stack

- Backend: FastAPI
- Database: PostgreSQL / PostGIS
- Frontend: Next.js App Router
- Mapping: MapLibre GL
- Deployment: Docker Compose

## Key Directories

- `backend/` API, scoring logic, models, routers, tests
- `frontend/` Next.js landing page, login, dashboard, signup endpoint
- `docs/` architecture, deployment, and product notes

## Auth And Routing

- `/` is public
- `/login` is public
- `/dashboard` is protected
- Unauthenticated requests to protected routes are redirected to `/login`
- After successful login, users are redirected into `/dashboard`

## Open-Source Alignment

The platform is intentionally aligned with established free-flight tooling instead of reinventing the domain from scratch.

- AirScore for scoring workflow and competition concepts
- IGCWebview2 as a visualization reference
- `igc_lib` and `igc-xc-score` as parser/scoring references
- MapLibre GL for the map UI

See [docs/oss-reuse-evaluation.md](docs/oss-reuse-evaluation.md) for the current reuse notes.

## Local Development

1. Copy `.env.example` to `.env`
2. Copy `backend/.env.example` to `backend/.env`
3. Copy `frontend/.env.local.example` to `frontend/.env.local`
4. Start the stack with Docker Compose if you want to run locally

## Frontend Review Workflow

Frontend work in this repo can use a dedicated Claude advisory lane:

- workflow note: `docs/frontend-gui-review-workflow.md`
- Windows helper: `scripts/windows/claude-frontend-review.ps1`

The intended pattern is:

- Claude is consulted on frontend asks
- Claude sets the direction for GUI-heavy frontend changes
- Codex remains the implementation owner
- Codex makes the final call only when a hard repo constraint forces an adjustment

## Windows Local Development With WSL2

The preferred Windows setup is:

- WSL2 with Ubuntu 24.04
- Docker Desktop using the WSL 2 backend
- The app repo copied into the Linux filesystem under `~/projects/aervyx`

Bootstrap helpers:

- Windows side: `.\scripts\bootstrap.ps1 -WindowsWsl`
- Post-reboot / post-Ubuntu-init: `.\scripts\windows\finish-local-wsl.ps1`
- Linux side script: `scripts/wsl/bootstrap-aervyx.sh`

After setup completes, local URLs are:

- Frontend: `http://localhost:3000/login`
- Backend health: `http://localhost:8000/health`

## Current Runtime Shape

- Landing page is branded as Aervyx
- Login uses the same visual theme as the landing page
- Dashboard bootstraps against the backend API and no longer contains its own fallback login page

## Production Draft

A draft production deployment path is included for future use with `aervyx.net` and Cloudflare Tunnel.

- production compose stack: `docker-compose.prod.yml`
- production runbook: `docs/deployment-cloudflare-tunnel.md`
- staging Proxmox/Ubuntu runbook: `docs/deployment-staging-proxmox.md`
- Cloudflare tunnel template: `deploy/cloudflared/config.example.yml`

These files are intentionally off by default. They do not enable the tunnel, switch DNS, or expose the app publicly until you create the real credentials and start the production profile yourself.
