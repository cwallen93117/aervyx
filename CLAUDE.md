# Claude Handoff

This repo's source of truth is the tracked code on `main`.

## What This Repo Is

Aervyx is a hang gliding / paragliding competition platform with:

- a public marketing site at `/`
- login at `/login`
- a role-aware dashboard at `/dashboard`
- a FastAPI backend for auth, events, tasks, uploads, results, tracking, sites, and logbook
- a Flutter mobile app for tracking, flights, driver mode, and Meshtastic setup

## Start Here

Read these first:

1. `README.md`
2. `docs/live-deployment-handoff.md`
3. `backend/app/main.py`
4. `frontend/src/app/dashboard/page.tsx`
5. `frontend/src/components/TaskMap.tsx`
6. `backend/app/services/logbook.py`
7. `mobile/lib/main.dart`
8. `mobile/lib/app.dart`
9. `mobile/lib/services/tracking_service.dart`
10. `mobile/lib/services/ble_service.dart`

## Current Product Surfaces

- `Events`: live
- `Tasks`: live
- `Scores`: live
- `Live Tracking`: live in the dashboard and backend, but field validation with mobile / Meshtastic is still partial
- `Logbook`: live
- `Settings`: live
- `Admin`: live
- `Mobile app`: substantial implementation exists, but end-to-end validation is still incomplete
- `Public deployment`: live on `aervyx.net` / `api.aervyx.net`

## High-Value Repo Facts

- The repo is now consolidated around `main`; the old working branches were cleaned up.
- The old safe fallback branch is preserved only as tag `archive/safe-working-state-2026-03-23`.
- The dashboard is orchestrated from `frontend/src/app/dashboard/page.tsx`.
- `TaskMap.tsx` is the central shared map component for tasks, replay, logbook replay, admin site preview, and live tracking.
- The backend router families live in `backend/app/routers/`.
- `backend/app/services/logbook.py` is a dense service that now covers:
  - logbook sync
  - stat derivation
  - site matching
  - replay-track loading
  - bulk rescan behavior
- The mobile app has moved beyond the older task-list/task-map scaffold. The current source of truth is the code under `mobile/lib/screens/` and `mobile/lib/services/`.

## Live Deployment

Three environments run on the same VM (192.168.87.94):

| | Production | Staging | Alpha |
|---|---|---|---|
| **Site** | `https://aervyx.net` | `https://staging.aervyx.net` | `https://alpha.aervyx.net` |
| **API** | `https://api.aervyx.net` | `https://api-staging.aervyx.net` | `https://api-alpha.aervyx.net` |
| **Branch** | `main` | `staging` | `alpha` |
| **Repo path** | `/srv/aervyx-staging/repo` | `/srv/aervyx-staging/staging-repo` | `/srv/aervyx-staging/alpha-repo` |
| **Compose project** | `aervyx-prod` | `aervyx-staging` | `aervyx-alpha` |
| **Deploy trigger** | push to `main` | push to `staging` | push to `alpha` |
| **Database** | separate volume | separate volume | separate volume |
| **Purpose** | live users | Charles reviews | AI agent preview |

- Deploy listener health: `https://deploy.aervyx.net/health`
- The VM is internally named `aervyx-staging` and paths still use that naming.
- Webhook config: `/etc/default/aervyx-staging-webhook` with `BRANCH_MAP`
- Deploy scripts: `deploy/staging/deploy-prod.sh`, `deploy-staging.sh`, and `deploy-alpha.sh` (all call `deploy-common.sh`)
- Alpha is behind Cloudflare Access (Charles only) — used for AI-generated feature previews
- Database sync: `scripts/sync-db.sh` copies data between environments with optional PII anonymization
- Admin DB export/import: `GET/POST /api/admin/db/export` and `/api/admin/db/import`

### Development workflow
1. Push to `staging` → auto-deploys to `staging.aervyx.net`
2. Test at `staging.aervyx.net`
3. Merge `staging` → `main` → auto-deploys to `aervyx.net`

### AI agent workflow (OpenClaw)
1. OpenClaw runs on separate Proxmox VM (`aervyx-openclaw`), manages Claude + Codex agents
2. Agents push `ai/<slug>` branches → merged into `alpha` → auto-deploys to `alpha.aervyx.net`
3. Charles reviews at `alpha.aervyx.net`, creates PR from `ai/<slug>` → `staging` if approved
4. OpenClaw agents can ONLY push to `ai/*` branches — walled off from staging/main by design

- The current live deployment handoff is:
  - `docs/live-deployment-handoff.md`

## Working Style

- Never ask the user to run commands. Execute everything directly — including SSH, WSL, Docker, deploy scripts, and server management.
- If a command fails, debug and retry. Only involve the user for credentials or physical actions (plugging in a device, opening a browser).
- Always use feature branches. Create PRs targeting `staging` (not `main`) and merge them immediately — no approval needed for staging. Charles reviews on the live staging site.
- Only the `staging` → `main` promotion requires user approval. Never merge to `main` without sign-off.
- When deploying to production, use the Proxmox API (guest agent file-write + exec via stdin) since direct SSH is firewalled.

## Repo Conventions

- AirScore concepts and terminology are the primary domain reference.
- Preserve the event-scoped dashboard workflow unless there is a strong reason to change it.
- For GUI-heavy frontend work, see `docs/frontend-gui-review-workflow.md`.
- If docs and code disagree, prefer the code, then update the docs.
- Treat these as local noise unless a task is explicitly about them:
  - `.codex_tmp/`
  - `.claude/`
  - `backend/flightcomp.db`
  - `mobile/.metadata`
  - `mobile/releases/`
  - `show_emulator.ps1`

## Important Current Behaviors

- `main` already includes the former `codex/logbook-v1` branch work.
- The public GitHub webhook now drives deployments from `main`.
- Logbook climb / altitude stats now prefer pressure altitude when present and fall back to GPS altitude otherwise.
- Logbook climb spikes are filtered through a reusable climb-rate validator.
- Admin site rescan now reevaluates all track-backed flights and recomputes site `flight_count` values.
- Admin, Settings, and Logbook intentionally hide the selected-event header context in the dashboard chrome.
- The frontend Dockerfile now starts the built app instead of running `next dev`.

## Docs To Trust

- `README.md`
- `docs/architecture.md`
- `docs/request-tracker.md`
- `docs/frontend-gui-review-workflow.md`
- `docs/live-deployment-handoff.md`
- `docs/claude-handoff-manual.md`

## Docs To Treat As Historical Or Partial

- `docs/logbook-backend-design.md`
- `docs/scoring-software-thread-reconstruction.md`
- `docs/phase2-codex-handoff.md`
- `mobile/README.md` is partially stale relative to the current mobile app

## Useful Validation Commands

```powershell
git status -sb
```

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

```powershell
cd frontend
npm run build
```

```powershell
cd mobile
flutter pub get
flutter analyze
```

## Main Risks / Gaps

- Mobile + Meshtastic end-to-end behavior still needs real-device validation.
- Some historical docs describe earlier scaffolds rather than the current implementation.
- Some deployment docs still say `staging` or describe draft paths even though the live public deployment now exists.
