# Claude Handoff Manual

This document explains what has been built so far, how the major customizations work, and which files are the current source of truth after consolidating the active branch into `main`.

## Source Of Truth

- The tracked code on `main` is the current truth.
- The former `codex/logbook-v1` work is now included on `main`, and that branch was removed during cleanup.
- The old `claude/flamboyant-perlman` worktree was historical; it is not the current implementation source.
- The old safe fallback branch was removed during cleanup and preserved only as tag `archive/safe-working-state-2026-03-23`.
- Untracked local artifacts are not part of the product baseline.

If code and docs disagree, trust the code and then update the docs.

## How The System Is Shaped

### Backend

- Stack: FastAPI + SQLAlchemy + PostgreSQL / PostGIS-ready schema
- Entry point: `backend/app/main.py`
- Router families:
  - `auth`
  - `events`
  - `tasks`
  - `uploads`
  - `results`
  - `tracking`
  - `logbook`
  - `sites`
  - `site_settings`
  - `airspace`
  - `turnpoints`
  - `pilots`
  - `public`
- Important service files:
  - `backend/app/services/logbook.py`
  - `backend/app/services/scoring.py`
  - `backend/app/services/tracking.py`

### Frontend

- Stack: Next.js App Router
- Main app shell: `frontend/src/app/dashboard/page.tsx`
- Shared map engine: `frontend/src/components/TaskMap.tsx`
- Dashboard sections:
  - `EventsSection.tsx`
  - `TasksSection.tsx`
  - `ScoringSection.tsx`
  - `LiveTrackingSection.tsx`
  - `LogbookSection.tsx`
  - `SettingsSection.tsx`
  - `AdminSection.tsx`
- Shared styling is centralized heavily in `frontend/src/app/globals.css`

### Mobile

- Stack: Flutter
- Current app entry:
  - `mobile/lib/main.dart`
  - `mobile/lib/app.dart`
- Current source of truth is the actual code under:
  - `mobile/lib/screens/`
  - `mobile/lib/services/`
  - `mobile/lib/models/`
- `mobile/README.md` still describes an older scaffold and should not be treated as fully current.

## Cross-Cutting Product Rules

- Event-scoped admin workflow is central to the dashboard design.
- Role model matters:
  - admin
  - organizer
  - pilot
  - guest / public-safe views
- The same map component is reused across task building, results, replay, live tracking, logbook replay, and admin site preview.
- AirScore concepts are the domain anchor for scoring and workflow naming.
- GUI-heavy frontend changes historically used a Claude advisory lane:
  - see `docs/frontend-gui-review-workflow.md`
- Public deployment now exists as a live VM + Cloudflare setup and should not be treated as draft-only anymore.

## Live Deployment

Status: `Live`

Detailed live deployment handoff:
- `docs/live-deployment-handoff.md`

Current live shape:
- public site:
  - `https://aervyx.net`
- public API:
  - `https://api.aervyx.net`
- public deploy listener:
  - `https://deploy.aervyx.net`
- live branch:
  - `main`

Important caveat:
- the live server still uses internal `staging` names for directories, services, scripts, and container names
- follow `docs/live-deployment-handoff.md` before renaming or “cleaning up” those internals

## Dashboard Surfaces

### Events

Status: `Live`

Purpose:
- Event selection and event-scoped administration

Key behavior:
- Event selection drives downstream task, participant, scoring, and airspace state.
- Participant intake supports:
  - adding existing site users
  - creating new pilots
  - wildcard search with `*`
- Scoring parameters are event-level and were heavily customized for a denser AirScore-style workflow:
  - advanced settings live here, not on Tasks
  - scoring checkboxes render as cleaner row-based controls
  - info popovers explain each scoring field
  - scoring parameters can be loaded from previous meets
- Airspace / restricted-fields setup was compacted into a single upload table with per-row labeling and auto-saved visibility toggles.
- Event action buttons were moved into the event-selection area for a tighter admin workflow.

High-signal files:
- `frontend/src/components/dashboard/EventsSection.tsx`
- `backend/app/routers/events.py`
- `backend/app/routers/airspace.py`

### Tasks

Status: `Live`

Purpose:
- Build and manage event-scoped tasks

Key behavior:
- Tasks are event-scoped and built from selected turnpoints rather than freeform map-only authoring.
- Task selection and publish actions were moved into a top toolbar.
- Publish / unpublish is a single toggle-style workflow.
- Unpublishing a task also clears scored results and related scoring selections.
- Turnpoint tables were repeatedly compacted and rebalanced:
  - per-leg distance column
  - optimized distance display
  - centered headers
  - stable remove-button layout
- Timing controls depend on task type:
  - gates shown only when relevant
  - computed gate times shown inline
- The task-builder map was stabilized so adding a point does not destroy and recreate the map instance.

High-signal files:
- `frontend/src/components/dashboard/TasksSection.tsx`
- `frontend/src/components/TaskMap.tsx`
- `backend/app/routers/tasks.py`

### Scores

Status: `Live`

Purpose:
- Run scoring operations and display results

Key behavior:
- Results and operations were simplified to reduce banner waste and redundant controls.
- Task selection in scoring only offers published tasks.
- Operations supports:
  - bulk and per-pilot IGC upload flows
  - score task
  - delete scored task
  - official / unofficial toggle
- `Score task` can auto-select each pilot's newest IGC when rows are blank.
- `Delete scored task` clears scored outputs and returns file/status selectors to blank.
- Results now differentiate official vs unofficial state consistently:
  - task-day badge
  - overall headers
  - no duplicate unofficial label under pilot names
- Downloads and replay overlays were added to results workflows.

High-signal files:
- `frontend/src/components/dashboard/ScoringSection.tsx`
- `frontend/src/components/dashboard/ScoringOperationsPanel.tsx`
- `backend/app/routers/results.py`
- `backend/app/routers/uploads.py`

### Live Tracking

Status: `Live backend + dashboard`, `Partial end-to-end`

Purpose:
- Show current tracked pilot positions on the shared map

Key behavior:
- Backend exposes:
  - live SSE feed
  - stored task position history
  - Meshtastic mesh configuration endpoint
- MQTT gateway support exists for Meshtastic-originated positions.
- Dashboard has a `live_tracking` section wired into the main page and map stack.
- `TaskMap.tsx` is the rendering anchor for live positions and replay overlays.

Important caution:
- The code path exists, but the full mobile-to-backend-to-dashboard proof is still incomplete.

High-signal files:
- `frontend/src/components/dashboard/LiveTrackingSection.tsx`
- `backend/app/routers/tracking.py`
- `docs/phase2-codex-handoff.md`

### Logbook

Status: `Live`

Purpose:
- Personal pilot-wide flight history, independent from a single event

Key behavior:
- Logbook aggregates:
  - task-uploaded IGCs mirrored into the pilot logbook
  - personal uploaded IGCs
  - manual flights
- Manual flights can later receive an attached IGC and then gain replay / download behavior.
- Statistics are available even for manual flights.
- Replay uses the shared `TaskMap` and now fits to the flight path rather than falling back to a broad U.S. view.
- Logbook replay shows the pilot telemetry card and hides task distance summary cards that do not make sense for a standalone flight.
- Flights can be:
  - starred
  - grouped by collapsible year sections
  - bulk selected and deleted
- Folder scan import can recurse through directories, detect duplicates by hash, and separate imported / skipped / review-needed files.
- Statistics include thermal / glide time.

Current backend stat behavior:
- altitude-based stats prefer pressure altitude when the track has it
- GPS altitude is the fallback when pressure altitude is missing
- climb spikes are filtered through a reusable climb-rate validator

High-signal files:
- `frontend/src/components/dashboard/LogbookSection.tsx`
- `backend/app/routers/logbook.py`
- `backend/app/services/logbook.py`

### Settings

Status: `Live`

Purpose:
- User account settings and unit preferences

Key behavior:
- Unit preferences flow into task distances, replay display, live telemetry, and mobile-facing assumptions.
- Settings page intentionally hides the selected-event header context because it is site-wide rather than event-specific.

High-signal files:
- `frontend/src/components/dashboard/SettingsSection.tsx`
- `backend/app/routers/auth.py`

### Admin

Status: `Live`

Purpose:
- Site-wide platform administration, user management, and site catalog management

Key behavior:
- Admin users can manage site users and site settings.
- Admin page intentionally hides the selected-event header context because it is global, not event-scoped.
- Admin Sites database supports:
  - compact one-row-per-site table
  - city / state editing
  - save / delete controls
  - stored flight count
  - map preview
  - row-click map focus instead of a separate `View map` button
  - preview radius circle driven by `site_match_radius_m`
  - comma formatting for large numeric inputs and counts
- `Scan IGC for new sites` can discover takeoff locations from stored IGC-backed flights.
- `Rescan all flights for site match` now reevaluates all track-backed flights, not just unassigned ones, and recomputes per-site flight counts after the run.
- Admin site settings also hold global map behavior such as pitch cap.

High-signal files:
- `frontend/src/components/dashboard/AdminSection.tsx`
- `backend/app/routers/sites.py`
- `backend/app/routers/site_settings.py`
- `backend/app/services/logbook.py`

## Mobile App

Status: `Substantial implementation`, `Partial field validation`

Purpose:
- Companion app for pilots and drivers
- GPS tracking and local IGC capture
- Meshtastic BLE pairing and configuration
- live-view / driver support

Current shape:
- Current screens:
  - `login_screen.dart`
  - `home_screen.dart`
  - `flights_screen.dart`
  - `flight_detail_screen.dart`
  - `live_view_screen.dart`
  - `driver_home_screen.dart`
  - `ble_pairing_screen.dart`
  - `meshtastic_settings_screen.dart`
  - `settings_screen.dart`

Important implemented behavior:
- Role-aware home flow for pilot vs driver experiences
- Tracking state machine in `tracking_service.dart`
- sport-sensitive takeoff detection
- landing detection with confirm + countdown flow
- monitoring mode for multi-flight / re-launch scenarios
- Android foreground/background tracking support
- local IGC saving and flight browser
- flight detail map view
- live pilot map view
- unit conversion helpers synced with user settings
- driver mode with navigation support
- extensive Meshtastic BLE config flow in `ble_service.dart`, including:
  - config handshake
  - profile presets
  - owner naming
  - Wi-Fi setup
  - LoRa / MQTT settings
  - phone GPS sharing into mesh packets

Important caution:
- This area is larger and more advanced than the old mobile README suggests.
- The repo appears to have significant implementation, but real-device end-to-end proof still needs completion.

High-signal files:
- `mobile/lib/services/tracking_service.dart`
- `mobile/lib/services/ble_service.dart`
- `mobile/lib/screens/home_screen.dart`
- `mobile/lib/screens/meshtastic_settings_screen.dart`

## Backend Behaviors That Matter

### Site Matching

- Saved sites are stored in a dedicated site catalog.
- New track-backed flights can be site-matched from their first recorded point.
- Rescan behavior now:
  - covers all `task_upload` and `app_upload` flights
  - matches nearest active saved site within radius
  - updates `site_id` and `site_name` when a match exists
  - recomputes `flight_count` from current assignments after the run

### Logbook Statistics

- `backend/app/services/logbook.py` derives summary stats from track points.
- Current altitude rule:
  - use pressure altitude if any pressure altitude exists in the track
  - otherwise use GPS altitude
- Climb-rate spikes are filtered by `_validated_climb_rate(...)`.
- A one-off local recalculation script exists in `backend/scripts/recalculate_logbook_stats.py`, but that script is not currently tracked in git and should not be treated as part of the committed baseline unless it is later committed.

### Live Tracking / Meshtastic

- Tracking router and MQTT subscriber support are present in the backend.
- Mesh configuration endpoint exists for the mobile app.
- The current gap is validation, not the absence of core code paths.

## Important Draft / Historical Docs

### Trust As Current Support Docs

- `README.md`
- `docs/architecture.md`
- `docs/request-tracker.md`
- `docs/frontend-gui-review-workflow.md`
- `docs/live-deployment-handoff.md`

### Use With Caution

- `docs/phase2-codex-handoff.md`
  - useful for tracking API shapes
  - partially stale on frontend status because live-tracking UI now exists
- `docs/deployment-staging-proxmox.md`
  - useful for how the VM was originally bootstrapped
  - stale on current hostnames and branch flow
- `docs/deployment-cloudflare-tunnel.md`
  - useful for historical tunnel draft context
  - stale on the current token-managed live connector
- `mobile/README.md`
  - useful for older intent
  - stale on current screen structure and feature breadth

### Historical / Superseded

- `docs/logbook-backend-design.md`
  - planning artifact from before the live pilot logbook landed
- `docs/scoring-software-thread-reconstruction.md`
  - project-memory document, useful for history but not a replacement for reading the current code

## Practical Advice For Follow-On Claude Sessions

- Start from `main`, not from old worktrees or backup branches.
- Read the dashboard page and `TaskMap.tsx` before changing frontend behavior.
- Read `logbook.py` before changing anything related to flights, stats, replay, or site matching.
- Treat mobile work as real but not fully field-proven.
- When older docs mention scaffold-era files like `task_list_screen.dart` or `task_map_screen.dart`, verify against the actual code before assuming they are still the live path.
- Keep global sections such as Admin, Settings, and Logbook site-wide rather than event-scoped in the UI chrome.
