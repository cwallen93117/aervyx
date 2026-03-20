# Aervyx Product Requirements

## Product Goal

Deliver a self-hosted scoring MVP for hang gliding and paragliding competitions with a clear upgrade path toward live tracking and mobile tooling in Phase 2.

## Mandatory OSS Reuse

Phase 1 must evaluate and practically reuse strong open-source projects where appropriate instead of rebuilding every subsystem from scratch.

Required evaluation targets:

- AirScore
- IGCWebview2
- igc_lib
- igc-xc-score
- MapLibre GL

The outcome of that evaluation is documented in `docs/oss-reuse-evaluation.md`.

## Phase 1 Scope

- Admin and pilot authentication
- Event management
- Pilot import and maintenance
- Turnpoint upload and validation
- AirScore-aligned task model and map-based task builder
- Scoring configuration with nominal values and penalties
- IGC upload with immutable evidence retention and SHA-256 hashing
- Parsed trackpoint storage separate from original IGC evidence
- Task progress detection, scoring, ranking, and results views
- Audit logging for scoring-relevant actions
- Docker Compose deployment path for QNAP NAS

## Phase 1 Success Conditions

Admin can:

- create and edit events
- import and manage pilots
- upload and search turnpoints
- build and publish tasks on a map
- configure scoring settings
- view task and pilot results

Pilot can:

- log in
- upload an IGC for a task
- review uploaded tracks and results

System can:

- parse IGC files
- preserve original evidence immutably
- store parsed trackpoints separately
- score pilot tracks against a published task
- display tasks, turnpoints, and tracks on a map

## Explicit Phase 2 Deferrals

- Flutter mobile app
- Android and iPhone support
- Live tracking
- Meshtastic integration
- MQTT ingest
- Replay system
- Device linking
- Provisional versus official live scoring
