# FlightComp Platform

FlightComp Platform is a self-hosted hang gliding and paragliding competition scoring platform. Phase 1 targets a QNAP NAS deployment through Docker Compose while keeping the codebase friendly to desktop development when needed. The platform is being built as a FastAPI and Next.js application, but it is intentionally aligned with established open-source scoring and viewer projects instead of reinventing the domain from zero.

## Open-Source Reuse Strategy

Phase 1 explicitly evaluates and reuses the following projects where practical:

- AirScore as the primary scoring workflow and competition-domain reference
- IGCWebview2 as a reference for IGC and task visualization behavior
- `igc_lib` as a Python-side reference for IGC parsing and anomaly handling
- `igc-xc-score` as a reusable helper for GeoJSON-oriented track scoring and validation ideas where applicable
- MapLibre GL for the map UI

See [docs/oss-reuse-evaluation.md](docs/oss-reuse-evaluation.md) for the concrete integration plan.

## Repository Layout

- `backend/` FastAPI API, ingest pipeline, scoring services, database models, migrations, and tests
- `frontend/` Next.js TypeScript UI for admin and pilot workflows
- `docs/` product, architecture, OSS reuse, and NAS deployment documentation
- `scripts/` helper scripts for bootstrap and maintenance
- `docker-compose.yml` Compose stack intended for QNAP NAS deployment and optional local development

## Runtime Target

The intended Phase 1 runtime is your NAS, not your desktop. Docker does not need to be installed on this PC for the project structure to be valid. Docker Compose files and service configuration are being prepared so the stack can be deployed on a QNAP NAS that supports containerized workloads.

## Setup Flow

1. Copy `.env.example` to `.env`.
2. Copy `backend/.env.example` to `backend/.env`.
3. Copy `frontend/.env.local.example` to `frontend/.env.local`.
4. Review [docs/deployment-qnap.md](docs/deployment-qnap.md).
5. Deploy the stack with Docker Compose on the NAS.

## Current Status

Phase 1 now includes a working backend scoring API, a Next.js admin and pilot dashboard, MapLibre-based task and track visualization, OSS reuse documentation, and NAS-oriented deployment files.