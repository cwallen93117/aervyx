# Logbook Backend Design

> **Historical (2026-04-02):** This document describes an earlier design direction for event-scoped activity logs. The deployed logbook is a personal pilot flight logbook with IGC upload, statistics, site matching, and replay. See `backend/app/services/logbook.py` and `backend/app/routers/logbook.py` for the current implementation.

Last updated: 2026-03-25

This document captures the planned backend shape for the logbook feature without wiring anything into the live app yet.

## Goal

Provide a clean event-scoped logbook that can show an operational record of uploads, task changes, scoring edits, and event-level administrative activity.

The current `AuditLog` trail remains the provenance source. The logbook feature should present a user-facing projection of that activity rather than replacing audit logging.

## Recommended Data Model

Primary projection:

- `LogbookEntry`

Suggested fields:

- `id`
- `event_id`
- `created_at`
- `actor_user_id`
- `action`
- `entity_type`
- `entity_id`
- `task_id` if available
- `pilot_id` if available
- `category`
- `summary`
- `details_json`
- `visibility`
- `source_audit_log_id` if a direct audit link is useful

Recommended visibility values:

- `staff`
- `signed_in`
- `public` only if a future public feed is explicitly needed

## Write Sources

Fan out future writes from the same actions that already create audit records:

- task upload
- task publish / unpublish
- scoring correction / penalty edit
- event updates
- pilot enrollment changes
- airspace and turnpoint changes when they affect event operations

Each logbook write should be event-scoped at the time of the action.

## API Shape

Suggested future endpoints:

- `GET /api/events/{event_id}/logbook`
- `GET /api/events/{event_id}/logbook/{entry_id}`
- `POST /api/events/{event_id}/logbook` for manual notes or staff entries later

Suggested filters:

- time range
- category
- actor
- entity type
- visibility
- task or pilot linkage

## Indexing

Recommended indexes for the eventual table:

- `(event_id, created_at desc)`
- `(event_id, category, created_at desc)`
- `(event_id, visibility, created_at desc)`

## Claude Review Note

Local Claude review suggested that `AuditLog` plus an `event_id` column could be sufficient for a smaller implementation. That remains a useful simplification option, but the current planning direction keeps the user-facing logbook as a dedicated projection so the UI can stay clean and purpose-built.

## Rollout Order

1. finalize the mockups
2. approve the logbook information architecture
3. add the backend projection
4. add read routes
5. wire the dashboard sidebar
6. fan out writes from upload, task, scoring, and event actions
