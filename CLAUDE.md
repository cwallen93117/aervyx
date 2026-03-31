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
2. `backend/app/main.py`
3. `frontend/src/app/dashboard/page.tsx`
4. `frontend/src/components/TaskMap.tsx`
5. `backend/app/services/logbook.py`
6. `mobile/lib/main.dart`
7. `mobile/lib/app.dart`
8. `mobile/lib/services/tracking_service.dart`
9. `mobile/lib/services/ble_service.dart`

## Current Product Surfaces

- `Events`: live
- `Tasks`: live
- `Scores`: live
- `Live Tracking`: live in the dashboard and backend, but field validation with mobile / Meshtastic is still partial
- `Logbook`: live
- `Settings`: live
- `Admin`: live
- `Mobile app`: substantial implementation exists, but end-to-end validation is still incomplete
- `Production Cloudflare deploy path`: draft only

## High-Value Repo Facts

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
- `docs/deployment-cloudflare-tunnel.md`
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
- The production deploy path is intentionally draft-only and should not be treated as live infrastructure.
