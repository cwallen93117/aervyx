# QNAP Deployment Notes

## Intent

Phase 1 is being prepared for deployment on a QNAP NAS through Docker Compose. The desktop machine is the authoring environment, not the required runtime host.

## Expected NAS Capabilities

- Container Station or another Docker-compatible runtime on the NAS
- Support for Docker Compose or equivalent stack deployment
- Persistent storage path for PostgreSQL data and uploaded evidence files
- Reverse proxy or port exposure for frontend and backend services

## Planned Stack

- `frontend` on port 3000 internally
- `backend` on port 8000 internally
- `db` on port 5432 internally
- volumes for PostgreSQL data and backend upload storage

## Deployment Shape

1. Copy the repository to the NAS.
2. Create `.env`, `backend/.env`, and `frontend/.env.local` from templates.
3. Configure persistent volume paths suitable for the NAS.
4. Run `docker compose up --build -d` on the NAS.
5. Expose the frontend and backend through the NAS network configuration or reverse proxy.

## Notes

- Docker does not need to be installed on this desktop for the repository to target NAS deployment.
- Local desktop execution remains optional for development convenience only.