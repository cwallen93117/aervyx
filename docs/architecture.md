# FlightComp Platform Architecture

## Overview

Phase 1 uses a straightforward three-service architecture:

- Next.js frontend for admin and pilot workflows
- FastAPI backend for APIs, ingest, scoring, and audit logging
- PostgreSQL with PostGIS-ready image for relational and geospatial data

## Key Design Decisions

- Preserve original IGC uploads immutably on disk and store SHA-256 hashes in the database
- Store parsed trackpoints separately from original evidence
- Keep scoring configuration and task definitions extensible through normalized core tables and JSON detail fields where pragmatic
- Build for Docker Compose first so the same topology can move to a QNAP NAS later

## Planned Phase 1 Domains

- Auth and role-based access
- Events and pilots
- Turnpoints and task geometry
- Upload ingestion for turnpoint files and IGC tracks
- Scoring engine and results
- Audit log