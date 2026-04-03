# Scoring Software Thread Reconstruction

> **Historical (2026-04-02):** This document reconstructs the original development thread and project-memory timeline. For current implementation details, see `README.md`, `CLAUDE.md`, or `docs/live-deployment-handoff.md`.

Last updated: 2026-03-25

This document reconstructs the archived `Scoring Software` thread that originally ran with `cwd = C:\Users\Charles\Documents\Playground`, plus the follow-on continuity in the current workspace at [C:\Projects\scoring software- codex](C:\Projects\scoring software- codex).

It is a recovered project-memory document, not a literal chat import. Repeated image-only messages, environment pings, and duplicate asks were collapsed into the higher-signal request history below.

## Recovered Sources

- Parent archived thread:
  - `C:\Users\Charles\.codex\sessions\2026\03\17\rollout-2026-03-17T13-18-28-019cfcce-5af3-7891-b22e-2ec13a8a9050.jsonl`
- Current continuity thread:
  - `C:\Users\Charles\.codex\sessions\2026\03\24\rollout-2026-03-24T20-00-03-019d224a-895c-7813-99f2-856270967cfb.jsonl`
- Archived sub-agent sessions:
  - `019d1d10-fe68-76a2-b6a4-84501e724daa`
  - `019d1d11-1b3d-7300-b2c7-d19116bd07ae`
  - `019d1d11-3847-7890-9040-12144899d393`

## Executive Summary

The project began as a two-phase hang gliding / paragliding scoring platform with a strong Phase 1 focus:

- FastAPI backend
- PostgreSQL
- Next.js frontend
- MapLibre task/results map
- strong alignment with AirScore and related OSS tools

The thread then expanded in five major directions:

1. moving the repo off Google Drive into [C:\Projects\scoring software- codex](C:\Projects\scoring software- codex)
2. replacing placeholder scoring behavior with more AirScore-aligned scoring concepts and parameters
3. reshaping the product UI around event-scoped admin workflows, task planning, and scoring operations
4. adding replay/live-tracking related Phase 2 work earlier than originally planned
5. introducing a Claude-assisted GUI review lane plus HTML preview mockups before large frontend changes

By 2026-03-25, the important repo state was:

- the real project repo lives at [C:\Projects\scoring software- codex](C:\Projects\scoring software- codex)
- `phase2` had been pushed to GitHub
- `phase2` had been merged into `main`
- a temporary safe snapshot still existed as `codex/safe-working-state-2026-03-23`

## Chronological Reconstruction

### 2026-03-17: Bootstrap, GitHub, and scope lock

The original thread started in `C:\Users\Charles\Documents\Playground`, then immediately focused on:

- checking `gh` availability
- creating a private GitHub repo under `cwallen93117`
- bootstrapping a scoring platform called `FlightComp Platform`
- keeping Phase 1 as the immediate build target
- requiring a self-hosted Docker deployment path, not just desktop-local execution

The project direction was then tightened with a mandatory OSS reuse requirement:

- AirScore as the primary scoring/workflow reference
- IGCWebview2 as a track/task viewer reference
- `igclib` / `igc-xc-score` as parser / scoring helper references
- MapLibre GL for map UI

That same day, the workspace was explicitly moved out of Google Drive and into [C:\Projects\scoring software- codex](C:\Projects\scoring software- codex) to avoid sync issues.

### 2026-03-17 to 2026-03-18: Scoring accuracy and deployment planning

The user challenged placeholder scoring and asked why AirScore GAP formulas were not yet in use. This set the long-term direction that scoring must be AirScore-aligned rather than a simple MVP approximation.

In parallel, the deployment path became a first-class requirement:

- push code to GitHub
- have the deployment host pull from GitHub
- verify frontend URL, map rendering, and turnpoint upload behavior on the hosted app

This period also produced deployment artifacts and documentation that were later retired when the hosting direction changed.

### 2026-03-18 to 2026-03-19: Event-scoped admin UI and task builder expansion

The product UI was heavily redirected during this period:

- replace the original Events panel with a persistent left navigation sidebar
- move participants and turnpoint files under the Events surface
- make everything event-scoped so changing the current event updates all dependent views
- add a scoring-parameters card under Events

The task builder was repeatedly refined toward an AirScore-style workflow:

- imported turnpoints should belong to events
- tasks should be built by selecting waypoints, not free-clicking the map
- task rows should support type/radius editing and reordering
- advanced settings should be collapsible
- task types should include AirScore-style variants such as Race to Goal with Gates and Open Distance
- unused fields should gray out based on task type
- total distance and optimized distance should be visible during planning

At the same time, scoring/results UX was simplified:

- scoring page should emphasize task results and overall results rather than a map-heavy layout
- pilot views should be read-only and role-segregated from admin workflows

### 2026-03-19: Data seeding and AirScore / FS parameter parity

The thread then moved into two related data tasks:

- comparing an FS HTML results export against current event scoring settings
- adding missing AirScore/FS-style parameters to the event scoring configuration

The user also requested bulk population for the Highland Challenge / Myles data:

- add pilots from HTML exports into the database
- add event scoring settings from the same source
- populate tasks from attached task HTML files
- avoid pre-populating scoring so uploaded IGCs can be used to test the engine

This is the main origin of the Highland Challenge test data and the push for richer event-level scoring settings.

### 2026-03-19 to 2026-03-23: Replay, scoring operations, and Phase 2 creep

After the Phase 1 admin/task/results surfaces were established, the thread expanded into replay, task-map, and scoring-operations behavior:

- full-screen task planner layout
- track overlay and pilot replay improvements
- adaptive telemetry smoothing concerns
- 2D/3D path visibility experiments
- scoring operations refinements:
  - admin uploads
  - auto-score after uploads or status changes
  - delete/reset behavior
  - publish task / unofficial-to-official flow
  - penalty visibility
  - official-only overall standings

At the repo level, this period also produced the major `phase2` work:

- live tracking backend and frontend scaffolding
- replay page/task-map work
- unit preferences
- true 3D flight-track rendering experiments

### 2026-03-23: Parallel work split and sub-agent execution

The user explicitly approved multi-threaded / multi-agent work and asked for a clean split across independent surfaces. That resulted in:

- a recommended thread split document inside the conversation
- three actual sub-agent runs
- a preserved safe working snapshot branch / worktree

This is also when the user asked to route frontend / GUI-heavy work through Claude review before implementation.

### 2026-03-23 to 2026-03-24: Claude-assisted GUI lane and mockup-led redesign

The workflow was changed so Claude would review all frontend asks, and for major GUI work Claude would effectively choose the preferred direction while Codex remained the implementation owner.

That led to:

- a documented frontend GUI review workflow
- a helper script for Claude CLI review
- HTML preview files for Tasks, Scores, Admin, and compact-form options
- conservative theme and compaction passes across the dashboard

The user then iterated on:

- sidebar sizing / font emphasis
- top-bar compaction
- removing redundant cards
- compacting forms by placing labels to the left or reducing vertical stacking

### 2026-03-25: Recovery, push/merge, and cleanup

In the current thread, the archived work was reconstructed from local session files. The repo state was then normalized:

- `phase2` was pushed to GitHub
- `phase2` was merged into `main`
- the current app at `http://localhost:3000/dashboard` was treated as the most current local state
- the next requested step became: persist the recovered history and clean up the redundant `Playground` location

## Durable Project Constraints Recovered From The Archived Thread

These constraints were repeated often enough that they should still be treated as active unless explicitly changed:

- the authoritative project repo is [C:\Projects\scoring software- codex](C:\Projects\scoring software- codex)
- AirScore is the primary scoring/workflow reference
- practical OSS reuse is preferred over rebuilding from scratch
- a self-hosted deployment path matters, not just desktop-local development
- pilots and admins should not see the same editing capabilities
- results shown to pilots/public should distinguish official from provisional/unofficial states
- GUI-heavy frontend changes should be reviewed with Claude before large implementation passes

## Recovered Sub-Agents

These sub-agent runs were recovered both from the parent session and from their archived session files.

### `019d1d10-fe68-76a2-b6a4-84501e724daa` — Results Portal cleanup

Scope:

- Results Portal task/overall cleanup only
- remove `Live View` and `Replay` from static results
- remove now-unused `/dashboard/live` and `/dashboard/replay` pages
- keep task results read-only and include `Unscored` rows where appropriate

Recovered outcome:

- removed `Live View` and `Replay` from Results Portal task results
- task results include event pilots with `Unscored` rows
- overall results remain official-only
- deleted the now-unused live/replay route pages

Changed files reported by the sub-agent:

- `frontend/src/components/dashboard/ScoringSection.tsx`
- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/app/globals.css`
- `backend/app/routers/results.py`
- `frontend/src/components/dashboard/ScoringOperationsPanel.tsx`

Validation reported:

- `npm run build`
- `python -m compileall backend\app`

### `019d1d11-1b3d-7300-b2c7-d19116bd07ae` — Scoring Operations workflow

Scope:

- admin Scoring Operations flow only
- publish/unofficial-to-official workflow
- footer/button layout
- auto-score behavior after uploads and status changes
- delete/reset edge cases

Recovered outcome:

- `ScoringOperationsPanel` was wired so task-row actions also refresh event summary data
- footer layout was tightened
- upload/status/delete/publish actions were kept aligned with auto-score behavior

Changed files reported by the sub-agent:

- `frontend/src/components/dashboard/ScoringOperationsPanel.tsx`
- `frontend/src/components/dashboard/ScoringSection.tsx`
- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/app/globals.css`

Validation reported:

- `python -m compileall backend\app`
- `npm run build`

### `019d1d11-3847-7890-9040-12144899d393` — Replay / Task Map follow-up

Scope:

- replay bar layout cleanup
- replay/task-map UI polish
- avoid conflicting with current flat-track rendering and telemetry smoothing

Recovered outcome:

- replay bar changed from a full-width overlay to a tighter capped-width strip
- scrubber/time readout and controls were reorganized into a more compact layout

Changed files reported by the sub-agent:

- `frontend/src/components/TaskMap.tsx`
- `frontend/src/app/globals.css`

Validation reported:

- `npm run build`

## Current Continuity In This Thread

The current thread already completed the following recovery / repo-state tasks before this document was written:

- reconstructed the missing-thread situation from repo state
- identified the safe snapshot branch/worktree
- wrote a precise handoff note of finished vs in-progress work
- pushed `phase2` to GitHub
- merged `phase2` into `main`

This reconstruction document and the request tracker are the persistent follow-on memory artifacts requested next.
