# Logbook Lane

Last updated: 2026-03-25

This document defines the dedicated `Logbook` lane for the scoring software project. It exists to keep logbook work separate from scoring operations, even though the eventual product surfaces will overlap.

## Lane Ownership

The `Logbook` lane owns:

- static logbook mockups and prototype review
- logbook information architecture
- eventual logbook schema and API design
- later frontend integration once the design is approved

The lane does not own unrelated live-app changes unless they are directly needed to support logbook rendering or logbook data capture.

## Current Design Direction

The approved prototype direction is Koifly-inspired:

- table-first
- compact
- white surfaces with subtle blue accents
- minimal decoration
- operational ledger feel rather than a social feed feel

Prototype files live in [docs/mockups](C:\Projects\scoring software- codex\docs\mockups).

## Prototype Deliverables

- [logbook.html](C:\Projects\scoring software- codex\docs\mockups\logbook.html) as the preferred ledger view
- [logbook-split.html](C:\Projects\scoring software- codex\docs\mockups\logbook-split.html) as the alternate split view
- [logbook.css](C:\Projects\scoring software- codex\docs\mockups\logbook.css) as the shared static style sheet

## Future Product Shape

The planned feature is event-scoped:

- every event gets its own logbook view
- entries are sortable and filterable by time, category, actor, and visibility
- uploads, task publishing, scoring edits, and event updates should all appear in the logbook
- existing `AuditLog` records remain the provenance trail behind the user-facing logbook

## Out Of Scope For Now

- no React wiring
- no backend API wiring
- no live dashboard route changes
- no permission model changes beyond the future design notes

## Routing Rule

Any new logbook request should be routed to this lane first. If a request touches scoring or results, the logbook lane still owns it when the requested change is specifically about logbook presentation, logbook records, or logbook UX.
