# QNAP Deployment Notes

## Intent

Phase 1 targets a QNAP NAS running Container Station. The desktop machine is the authoring environment, while the NAS is the runtime host.

## Recommended Runtime

- QNAP TS-262
- Container Station
- Docker Compose V2
- no Docker Desktop required on the development PC

## Deployment Model

This repository supports a QNAP-friendly deployment path that does not require `git` on the NAS host:

1. The NAS stores a GitHub deploy key in `/share/Container/aervyx/.ssh`.
2. A small `alpine/git` container clones or pulls the private GitHub repository into `/share/Container/aervyx/app`.
3. The application stack runs from `docker-compose.qnap.yml`.

## Files Used

- `docker-compose.qnap.yml`
- `backend/Dockerfile.prod`
- `frontend/Dockerfile.prod`
- `scripts/qnap/github-sync.sh`
- `scripts/qnap/deploy.sh`

## First-Time Setup

1. Create `/share/Container/aervyx/.ssh` on the NAS.
2. Generate a GitHub deploy key for the NAS and add the public key to the private repository.
3. Run `scripts/qnap/github-sync.sh` on the NAS to clone the repo using the `alpine/git` container.
4. Create the runtime env files:
   - `.env`
   - `backend/.env`
   - `frontend/.env.local`
5. Run `scripts/qnap/deploy.sh` on the NAS.

## Environment Values

Recommended values for a direct LAN deployment:

- `.env`
  - `BACKEND_PORT=8000`
  - `FRONTEND_PORT=3000`
  - `POSTGRES_PORT=5432`
  - `NEXT_PUBLIC_API_BASE_URL=http://YOUR_NAS_IP:8000`
- `backend/.env`
  - `APP_ENV=production`
  - `APP_SECRET_KEY=<random secret>`
  - `DATABASE_URL=postgresql+psycopg://flightcomp:<password>@db:5432/flightcomp`
  - `CORS_ORIGINS=["http://YOUR_NAS_IP:3000"]`
- `frontend/.env.local`
  - `NEXT_PUBLIC_API_BASE_URL=http://YOUR_NAS_IP:8000`

## Updating from GitHub

After new commits land on `main`, run on the NAS:

```sh
sh /share/Container/aervyx/app/scripts/qnap/github-sync.sh /share/Container/aervyx
sh /share/Container/aervyx/app/scripts/qnap/deploy.sh /share/Container/aervyx
```

## Notes

- Docker does not need to be installed on the desktop machine for NAS deployment.
- The QNAP-specific compose file is production-oriented and avoids the development bind mounts and hot-reload settings.
