# Aervyx

Aervyx is an open-source hang gliding and paragliding competition platform. It combines event setup, turnpoint and airspace management, task building, IGC ingestion, GAP-style scoring, results, and a public-facing marketing site in one stack.

## What The Codebase Does

- Public marketing landing page at `/`
- Themed auth entry at `/login`
- Protected competition workspace at `/dashboard`
- Admin workflows for events, participants, turnpoints, airspace, tasks, scoring parameters, uploads, and manual scoring runs
- Pilot and public-safe results views with task definitions and task maps
- NAS-oriented deployment flow for QNAP Container Station

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
- `scripts/qnap/` GitHub sync and deploy helpers for the NAS

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

## QNAP / NAS Deployment

The supported NAS flow is:

1. Store the repo under `/share/Container/aervyx`
2. Use `scripts/qnap/github-sync.sh` to clone or pull from GitHub
3. Use `scripts/qnap/deploy.sh` to build and launch the stack

Detailed instructions live in [docs/deployment-qnap.md](docs/deployment-qnap.md).

## Current Runtime Shape

- Landing page is branded as Aervyx
- Login uses the same visual theme as the landing page
- Dashboard bootstraps against the backend API and no longer contains its own fallback login page
- NAS deployment currently targets the private GitHub repository [cwallen93117/aervyx](https://github.com/cwallen93117/aervyx)
