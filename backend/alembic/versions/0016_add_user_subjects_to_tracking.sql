-- Track live positions and sessions by user as well as pilot.
-- Driver-profile users may not have pilot records, but still need stable
-- live-map identities and task/session ownership.

ALTER TABLE live_positions
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE tracking_sessions
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_live_positions_user_ts
    ON live_positions (user_id, "timestamp");

CREATE INDEX IF NOT EXISTS ix_live_positions_task_user_ts
    ON live_positions (task_id, user_id, "timestamp");

CREATE INDEX IF NOT EXISTS ix_tracking_sessions_user_id
    ON tracking_sessions (user_id);
