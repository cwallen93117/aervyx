# FlightComp Platform Architecture

## Overview

Phase 1 uses a three-service deployment model designed for Docker Compose on a QNAP NAS:

- `frontend`: Next.js application for admin and pilot workflows
- `backend`: FastAPI API for auth, ingest, scoring orchestration, and auditability
- `db`: PostgreSQL database using a PostGIS-ready image for future geospatial expansion

## OSS Alignment

The architecture is intentionally shaped around existing competition scoring software rather than a greenfield domain model.

- AirScore is the primary domain reference for events, tasks, pilot results, scoring configuration, and comp workflow.
- IGCWebview2 informs the viewer behavior for tracks, overlays, and map interactions.
- `igc_lib` informs the Python ingest layer for parsing and anomaly awareness.
- `igc-xc-score` is evaluated as a boundary helper for GeoJSON-centric flight analysis ideas and possible sidecar integration.
- MapLibre GL is the production map framework for the new UI.

## Practical Phase 1 Integration Choice

The implementation will keep FastAPI and Next.js as the core stack, while applying an adapter strategy for OSS reuse:

- Directly adopt AirScore concepts and workflow names in the schema and APIs.
- Reuse MapLibre GL directly in the frontend.
- Reuse ideas, data shapes, and integration patterns from IGCWebview2 for track and task rendering.
- Reuse parsing and validation approaches from Python and JavaScript IGC helpers where practical.
- Avoid a hard dependency on the legacy AirScore runtime in Phase 1 because that would introduce a second, incompatible application stack into the MVP.

## Core Data Domains

- users and roles
- events and event-pilot enrollment
- turnpoint source files and normalized turnpoints
- task definitions and ordered task points
- immutable IGC uploads and parsed trackpoints
- scoring results and summaries
- audit logs

## Integrity Principles

- Original IGC uploads are written once and never silently mutated.
- Every evidence file receives a SHA-256 hash.
- Parsed trackpoints live separately from the original file artifact.
- Scoring operations are logged.
- Task publication is explicit and task geometry can be versioned.

## Deployment Direction

Phase 1 deployment is NAS-first through Docker Compose. Desktop execution is optional for development only and is not assumed to be installed on this machine.