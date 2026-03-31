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

- Public site:
  - `https://aervyx.net`
- Public API:
  - `https://api.aervyx.net`
- Public deploy listener health:
  - `https://deploy.aervyx.net/health`
- The live VM is still internally named `aervyx-staging`, and its paths/services still use that naming.
- The live server now deploys from `main`, not from `staging`.
- The current live deployment handoff is:
  - `docs/live-deployment-handoff.md`

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
