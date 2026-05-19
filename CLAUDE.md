# Claude Handoff

## Persistent User Rule

Charles expects completed changes to be committed and pushed to `origin/staging` automatically so they appear on the live staging site. After verification, stage only the files/hunks intentionally changed, commit them, and push to `origin/staging` before saying the task is done unless Charles explicitly asks to keep work local or target another branch.

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

The VM (192.168.87.94, 8 vCPU / 16 GB RAM / 120 GB disk) runs production and staging:

| | Production | Staging |
|---|---|---|
| **Site** | `https://aervyx.net` | `https://staging.aervyx.net` |
| **API** | `https://api.aervyx.net` | `https://api-staging.aervyx.net` |
| **Branch** | `main` | `staging` |
| **Repo path** | `/srv/aervyx-staging/repo` | `/srv/aervyx-staging/staging-repo` |
| **Compose project** | `aervyx-prod` | `aervyx-staging` |
| **Compose file** | `docker-compose.prod.yml` | `docker-compose.prod.yml` |
| **Deploy trigger** | push to `main` | push to `staging` |
| **Access** | public | Cloudflare Access (Charles only) |

### Local dev tools (Charles's desktop)

| Tool | Location | Purpose |
|------|----------|---------|
| Claude Code CLI | system | Primary AI development tool (Pro/Max subscription) |
| gstack | `~/.claude/skills/gstack/` | 35 slash commands: `/ship`, `/qa`, `/review`, `/cso`, `/investigate`, etc. |
| VoltAgent agents | `~/.claude/agents/` | 21 specialist agents including 4 custom Aervyx agents |
| Flutter SDK | system | Mobile development |

- Deploy listener health: `https://deploy.aervyx.net/health`
- The VM is internally named `aervyx-staging` and paths still use that naming.
- Webhook config: `/etc/default/aervyx-staging-webhook` with `BRANCH_MAP` (main + staging)
- Deploy scripts: `deploy/staging/deploy-prod.sh`, `deploy-staging.sh` (both call `deploy-common.sh`)
- Weekly Docker prune cron runs Sundays at 3am
- Database sync: `scripts/sync-db.sh` copies data between environments with optional PII anonymization
- Admin DB export/import: `GET/POST /api/admin/db/export` and `/api/admin/db/import`

### Development workflow
1. Edit code locally with Claude Code CLI + gstack/VoltAgent agents
2. Commit and push to `staging` — no PRs or approvals needed
3. Webhook auto-deploys to `staging.aervyx.net` for review
4. When happy, merge `staging` → `main` → auto-deploys to `aervyx.net`

### Mobile development
Flutter/Android stays on the desktop. Point `api_config.dart` at `https://api-staging.aervyx.net` for the staging backend.

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

On the VM (via Proxmox exec):
```bash
cd /srv/aervyx-staging/repo
docker compose -f docker-compose.prod.yml ps          # prod stack status
docker compose -f docker-compose.prod.yml logs backend --tail 20  # prod backend logs
```

On the desktop (for mobile):
```powershell
cd mobile
flutter pub get
flutter analyze
```

## Main Risks / Gaps

- Mobile + Meshtastic end-to-end behavior still needs real-device validation.
- Some historical docs describe earlier scaffolds rather than the current implementation.
- Some deployment docs still say `staging` or describe draft paths even though the live public deployment now exists.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
