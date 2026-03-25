-- Phase 2: tracking_sessions table for per-pilot tracking session state.

CREATE TABLE tracking_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pilot_id        INTEGER REFERENCES pilots(id) ON DELETE SET NULL,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    position_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX ix_tracking_sessions_task_id ON tracking_sessions (task_id);
CREATE INDEX ix_tracking_sessions_pilot_id ON tracking_sessions (pilot_id);
CREATE INDEX ix_tracking_sessions_active ON tracking_sessions (task_id, is_active) WHERE is_active = TRUE;
