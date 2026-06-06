# Aervyx.net Cloudflare Tunnel Rollout

This document prepares Aervyx for a future public launch without turning anything on yet.

If you are setting up the Proxmox-hosted staging VM first, use
`docs/deployment-staging-proxmox.md` as the primary runbook.

## Public URL Plan

- `https://aervyx.net` serves the marketing site, login, and dashboard
- `https://car.aervyx.net` serves the same frontend through origin-terminated RSA TLS for vehicle web views that reject Cloudflare Free ECDSA edge certificates
- `https://api.aervyx.net` serves direct backend and mobile API traffic
- browser app traffic should continue to use same-origin `/backend` requests from `aervyx.net`

## Vehicle-Compatible Hostname

`car.aervyx.net` is intentionally DNS-only in Cloudflare. It should point at
the production origin IP and must not be proxied, otherwise Cloudflare Free
Universal SSL will terminate TLS with an ECDSA edge certificate again.

Production starts the `car-tls` Caddy service from `docker-compose.prod.yml`.
Caddy listens on public ports `80` and `443`, obtains a Let's Encrypt RSA
certificate, serves the full certificate chain, and reverse-proxies requests to
the existing `frontend:3000` service.

Cloudflare DNS target:

```text
Type: A
Name: car
IPv4 address: 74.103.142.23
Proxy status: DNS only
```

The origin firewall/router must forward TCP `80` and `443` to the production
host for ACME HTTP validation and HTTPS traffic.

## Drafted Production Artifacts

- `docker-compose.prod.yml`
- `backend/Dockerfile.prod`
- `frontend/Dockerfile.prod`
- `.env.production.example`
- `backend/.env.production.example`
- `frontend/.env.production.example`
- `deploy/cloudflared/config.example.yml`

None of these files activate anything by themselves.

## Production Preparation

1. Copy `.env.production.example` to `.env.production`
2. Copy `backend/.env.production.example` to `backend/.env.production`
3. Copy `frontend/.env.production.example` to `frontend/.env.production`
4. Replace placeholder passwords, secrets, and URLs
5. Copy `deploy/cloudflared/config.example.yml` to `deploy/cloudflared/config.yml`
6. Replace `YOUR-TUNNEL-ID` in `deploy/cloudflared/config.yml`
7. Place the real Cloudflare tunnel credentials JSON beside `config.yml`

## Preflight Commands

Build and validate the production stack without exposing it:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d db backend frontend
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Health checks to run before enabling the tunnel:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml exec backend curl http://localhost:8000/health
docker compose --env-file .env.production -f docker-compose.prod.yml exec frontend wget -qO- http://localhost:3000/login
```

Validate:

- login and registration flow
- dashboard loads through the frontend
- `/backend` rewrite works in production mode
- uploads and downloads still work
- logbook upload/download still work
- live tracking SSE still streams correctly

## Tunnel Activation Steps

Do these only when you are ready to go live:

1. Create the Cloudflare Tunnel in Zero Trust
2. Attach DNS routes for `aervyx.net` and `api.aervyx.net`
3. Confirm `deploy/cloudflared/config.yml` and credentials file match the created tunnel
4. Start the tunnel profile:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml --profile cloudflare up -d
```

5. Validate:
   - `https://aervyx.net`
   - `https://aervyx.net/login`
   - `https://api.aervyx.net/health`
   - authenticated dashboard API calls
   - live tracking event stream

## Rollback

If anything is wrong after enabling public access:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml --profile cloudflare stop cloudflared
```

Then:

1. disable or remove the Cloudflare public hostname routes
2. keep the production app containers running privately if needed
3. continue troubleshooting without public exposure

## Notes

- Cloudflare Access for `/dashboard` or `/admin` is intentionally out of scope for this first rollout.
- `api.aervyx.net` remains available for direct backend/mobile traffic even though the browser app should prefer `/backend`.
- The live tracking endpoint uses `text/event-stream`, so any future proxy changes must preserve SSE behavior and avoid buffering.
