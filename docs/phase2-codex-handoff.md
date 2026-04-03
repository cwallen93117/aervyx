# Phase 2 Codex Handoff

> **Partially stale (2026-04-02):** Backend tracking endpoints are implemented and deployed. The live tracking dashboard is integrated into `TaskMap.tsx`. Mobile + Meshtastic field validation remains incomplete. For current deployment details, see `docs/live-deployment-handoff.md`.

This document describes the new Phase 2 backend endpoints, data schemas, and
exactly which existing frontend files a follow-on Codex session should extend
to add the live tracking map and replay system.

---

## SSE Endpoint: Live Positions

**Endpoint:** `GET /api/track/live/{task_id}`

**Auth:** Bearer JWT in `Authorization` header (same as all protected routes).

**Response:** `text/event-stream` with the following event types:

### Event: `snapshot`

Sent once immediately on connection. Contains the current position of every
pilot with an active tracking session for the task.

```
event: snapshot
data: [{"id":"<uuid>","pilot_id":1,"task_id":5,"lat":47.123,"lon":11.456,"alt":1200.0,"speed":42.5,"heading":180.0,"accuracy":3.2,"timestamp":"2026-03-21T14:00:00+00:00","source":"app","device_id":"!a1b2c3","battery_level":85}, ...]
```

### Event: `position`

Sent in real time each time a new position is stored (from the mobile app via
`POST /api/track/position` or from the MQTT gateway).

```
event: position
data: {"id":"<uuid>","pilot_id":1,"task_id":5,"lat":47.124,"lon":11.457,"alt":1210.0,"speed":40.0,"heading":175.0,"accuracy":2.8,"timestamp":"2026-03-21T14:00:05+00:00","source":"app","device_id":null,"battery_level":82}
```

### Keep-alive

A comment line is sent every 30 seconds if no position events are emitted:

```
: keepalive
```

---

## REST Endpoints

### POST /api/track/position

Submit a single position fix from the mobile app.

**Auth:** Bearer JWT.

**Request body:**

```json
{
  "task_id": 5,
  "lat": 47.123,
  "lon": 11.456,
  "alt": 1200.0,
  "speed": 42.5,
  "heading": 180.0,
  "accuracy": 3.2,
  "timestamp": "2026-03-21T14:00:00+00:00",
  "source": "app",
  "device_id": null,
  "battery_level": 85
}
```

Required fields: `task_id`, `lat`, `lon`. All others are optional.

`pilot_id` is resolved automatically from the authenticated user's
`pilot_id` — it is not accepted in the request body.

**Response:** `201 Created` with the stored position object (same shape as SSE
`position` event data).

### GET /api/track/positions/{task_id}

Fetch historical positions for a task.

**Auth:** Bearer JWT.

**Query params:**

| Param      | Type     | Default | Description                        |
|------------|----------|---------|------------------------------------|
| `pilot_id` | int      | null    | Filter to a single pilot           |
| `since`    | datetime | null    | Only positions after this timestamp |
| `limit`    | int      | 5000    | Max rows returned (cap 10000)      |

**Response:** `200 OK` with an array of position objects ordered by timestamp
ascending.

### GET /api/config/mesh

Returns Meshtastic mesh configuration for auto-configuring a mobile client.

**Auth:** Bearer JWT.

**Response:**

```json
{
  "channel_psk": "<base64 or null>",
  "mqtt_host": "mqtt.example.com",
  "mqtt_port": 1883,
  "topic_prefix": "aervyx"
}
```

### POST /api/results/{result_id}/promote

Promote a provisional result to official.

**Auth:** Bearer JWT (admin or organizer role).

**Response:** `200 OK` with the updated `ScoreResultResponse` including
`result_state: "official"`.

---

## Position Schema

All position objects (SSE events, REST responses, history rows) share the
same shape:

```typescript
type Position = {
  id: string;           // UUID
  pilot_id: number | null;
  task_id: number;
  lat: number;          // WGS-84 latitude
  lon: number;          // WGS-84 longitude
  alt: number | null;   // metres above sea level
  speed: number | null; // ground speed (units determined by source)
  heading: number | null; // degrees, 0 = north
  accuracy: number | null; // metres
  timestamp: string;    // ISO-8601 with timezone
  source: string | null;  // "app" | "mqtt_gateway" | other
  device_id: string | null; // Meshtastic node id or device identifier
  battery_level: number | null; // 0-100
};
```

---

## MQTT Position Payload (Meshtastic Gateway)

The MQTT subscriber listens on `aervyx/#`. Position messages must be JSON:

```json
{
  "latitude": 47.123,
  "longitude": 11.456,
  "altitude": 1200.0,
  "speed": 42.5,
  "heading": 180.0,
  "accuracy": 3.2,
  "device_id": "!a1b2c3d4",
  "task_id": 5,
  "pilot_id": 1,
  "battery_level": 85,
  "timestamp": "2026-03-21T14:00:00+00:00"
}
```

Required: `latitude`, `longitude`, `task_id`. All others optional.

Stored with `source = "mqtt_gateway"`.

---

## Existing Files to Extend

### frontend/src/components/TaskMap.tsx

This is the sole MapLibre GL component (~34 KB). It already renders:

- Task turnpoint cylinders and course lines
- Airspace polygons with class-based styling
- 3D track replay with animation controls and altitude visualization
- Three basemap modes (streets, satellite, terrain)

**To add live tracking:**

- Add a new `livePositions` prop accepting an array of `Position` objects.
- Render each pilot's current position as a moving marker (e.g. a
  `maplibregl.Marker` or a GeoJSON point layer with a symbol/circle).
- Optionally draw a fading trail from recent position history.
- Reuse the existing basemap, bounds-fitting, and layer ordering logic.

**Exported types to extend or reference:**

- `MapTurnpoint`, `MapTaskPoint`, `MapAirspaceRegion` — existing data types.
- `TrackCollection` — existing GeoJSON track type; live trails could use the
  same structure.

### frontend/src/app/dashboard/page.tsx

The main dashboard page (~176 KB). It already has:

- A `live_tracking` entry in the `SidebarSection` type (line 10).
- `TaskMap` imported and rendered in the results section.
- `apiFetch<T>(path, token, init)` for authenticated API calls.
- `canManagePlatform` boolean for staff-level UI gating.
- Results state management (`results`, `selectedTaskId`, etc.).

**To add the live tracking view:**

- Implement the `live_tracking` sidebar section (currently defined in the
  type but not rendered).
- Use `EventSource` or a fetch-based SSE reader to connect to
  `GET /api/track/live/{task_id}`.
- Maintain a `Map<number, Position>` keyed by `pilot_id` that updates on
  each `position` SSE event.
- Pass the live positions into `TaskMap` via the new prop.
- Add a pilot list sidebar showing name, altitude, speed, battery, and
  last-seen time for each tracked pilot.

### frontend/src/app/globals.css

All styles live in this single CSS file. Add live-tracking-specific styles
here (marker colours, pilot list panel, status indicators) adjacent to the
existing `.results-*` and `.task-map-*` rule blocks.

### frontend/src/lib/taskOptimization.ts

Task route optimization utilities. No changes needed for live tracking, but
this module is relevant context if the live map needs to show optimized
distance or route overlays alongside live positions.

---

## Database Tables (Phase 2)

### live_positions

| Column        | Type              | Notes                                |
|---------------|-------------------|--------------------------------------|
| id            | UUID PK           | `gen_random_uuid()`                  |
| pilot_id      | FK → pilots       | nullable                             |
| task_id       | FK → tasks        | not null, cascade delete             |
| lat           | double precision  |                                      |
| lon           | double precision  |                                      |
| alt           | real              | nullable                             |
| speed         | real              | nullable                             |
| heading       | real              | nullable                             |
| accuracy      | real              | nullable                             |
| timestamp     | timestamptz       | not null                             |
| source        | varchar(32)       |                                      |
| device_id     | varchar(64)       |                                      |
| battery_level | integer           |                                      |
| created_at    | timestamptz       | default now()                        |

Indexes: `(task_id, timestamp)`, `(task_id, pilot_id, timestamp)`.

### tracking_sessions

| Column         | Type         | Notes                        |
|----------------|--------------|------------------------------|
| id             | UUID PK      | `gen_random_uuid()`          |
| pilot_id       | FK → pilots  | nullable                     |
| task_id        | FK → tasks   | not null, cascade delete     |
| started_at     | timestamptz  | default now()                |
| last_seen_at   | timestamptz  | default now()                |
| is_active      | boolean      | default true                 |
| position_count | integer      | default 0                    |

### score_results (modified)

Added column: `result_state varchar(20) not null default 'official'`.

Values: `provisional` or `official`.
