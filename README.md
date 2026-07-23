# Aervyx

Aervyx is a self-hosted competition, scoring, and live-tracking platform for
hang gliding and paragliding. It gives organizers one place to run an event and
gives pilots, drivers, and spectators the tools they need before, during, and
after a task.

The hosted service is available at [aervyx.net](https://aervyx.net).

## What Aervyx Does

- Manages events, pilots, flying sites, turnpoints, airspace, tasks, start
  gates, and scoring parameters.
- Imports and validates IGC tracks, calculates GAP-style scores, and publishes
  task and meet results.
- Receives live positions from the Aervyx mobile app and Meshtastic radios over
  MQTT, then displays them on organizer and public maps.
- Provides task maps, flight replay, pilot logbooks, flight statistics, and IGC
  downloads.
- Supports driver pickup workflows, route guidance, weather layers, soaring
  forecasts, and FAA airspace data.
- Includes a Flutter companion app for pilots and drivers, plus a desktop
  Meshtastic provisioning utility.

## Project Status

Aervyx is under active development. The web platform, API, scoring workflow,
public results, logbook, and live-tracking surfaces are implemented. Mobile and
Meshtastic support is substantial, but changes involving radio hardware still
need field validation on real devices.

## Technology

- **API:** Python 3.12, FastAPI, SQLAlchemy
- **Data:** PostgreSQL 16 with PostGIS
- **Web:** Next.js 15, React 19, MapLibre GL, deck.gl
- **Mobile:** Flutter
- **Tracking:** GPS, server-sent events, Meshtastic, MQTT
- **Routing:** Valhalla
- **Local deployment:** Docker Compose

## Repository Layout

- `backend/` — API routers, database models, scoring and tracking services, and
  tests
- `frontend/` — public website, live views, results, and organizer dashboard
- `mobile/` — Android/iOS companion app
- `tools/meshtastic_provisioner/` — desktop radio provisioning utility
- `audit/` — score-comparison and FAI audit tools
- `deploy/` — container and server deployment support
- `docs/` — architecture, integrations, and operating notes

## Run Locally

Docker and Docker Compose are required.

```sh
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
docker compose up --build
```

Then open:

- Web app: <http://localhost:3000>
- API health check: <http://localhost:8000/health>
- API documentation: <http://localhost:8000/docs>

The first Valhalla startup downloads and builds routing data, so it can take
longer than later starts. Change `VALHALLA_TILE_URL` in `.env` if the default
Alps dataset is not appropriate for your region.

## Configuration and Secrets

The tracked `.env.example` files contain development defaults and placeholders.
Copy them to ignored local files before starting the stack.

Never commit:

- `.env`, `.env.production`, or service-specific environment files
- exported Meshtastic device profiles
- MQTT, OAuth, Cloudflare, or FAA credentials
- device private keys, channel keys, precise private locations, or production
  database exports

Production refuses to start with the default `APP_SECRET_KEY`. Generate unique
application and integration keys, use strong database and MQTT credentials, and
set production CORS origins and allowed hosts explicitly.

## Verification

```sh
# Backend
cd backend
python -m pytest

# Frontend
cd frontend
npm ci
npm test
npm run build

# Mobile
cd mobile
flutter pub get
flutter analyze
flutter test
```

See [mobile/README.md](mobile/README.md) for mobile setup and
[docs/architecture.md](docs/architecture.md) for the system architecture.
Third-party adaptations are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
