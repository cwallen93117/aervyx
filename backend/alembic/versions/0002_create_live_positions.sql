-- Phase 2: live_positions table for real-time pilot tracking.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE live_positions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pilot_id      INTEGER REFERENCES pilots(id) ON DELETE SET NULL,
    task_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    lat           DOUBLE PRECISION NOT NULL,
    lon           DOUBLE PRECISION NOT NULL,
    alt           REAL,
    speed         REAL,
    heading       REAL,
    accuracy      REAL,
    "timestamp"   TIMESTAMPTZ NOT NULL,
    source        VARCHAR(32),
    device_id     VARCHAR(64),
    battery_level INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_live_positions_task_ts
    ON live_positions (task_id, "timestamp");

CREATE INDEX ix_live_positions_task_pilot_ts
    ON live_positions (task_id, pilot_id, "timestamp");
