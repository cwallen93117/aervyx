# FlightComp Platform

FlightComp Platform is a self-hosted hang gliding and paragliding competition scoring platform. Phase 1 delivers a local-first scoring MVP with a FastAPI backend, PostgreSQL database, Next.js frontend, map-based task building, IGC evidence handling, and results views. Phase 2 features such as live tracking, mobile clients, Meshtastic, and replay are intentionally deferred.

## Repository Layout

- `backend/` FastAPI API, scoring engine, parsers, migrations, seeds, and tests
- `frontend/` Next.js TypeScript app with admin and pilot workflows
- `docs/` product and architecture documentation
- `scripts/` helper scripts for development bootstrap
- `docker-compose.yml` local development stack for web, api, and PostgreSQL

## Quick Start

1. Copy `.env.example` to `.env` and review values.
2. Copy `backend/.env.example` to `backend/.env`.
3. Copy `frontend/.env.local.example` to `frontend/.env.local`.
4. Start the stack with Docker Compose once Docker is installed:
   - `docker compose up --build`
5. Open:
   - Frontend: `http://localhost:3000`
   - API docs: `http://localhost:8000/docs`

## Development Notes

This repository is structured for local development first and later QNAP NAS deployment through Docker Compose. The initial scaffold is intentionally thin; Phase 1 feature implementation fills in the domain logic, data model, scoring workflows, and UI.