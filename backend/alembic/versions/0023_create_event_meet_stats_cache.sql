CREATE TABLE IF NOT EXISTS event_meet_stats_cache (
  id SERIAL PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  scope VARCHAR(40) NOT NULL,
  payload_json JSON NOT NULL,
  calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_event_meet_stats_cache_event_scope UNIQUE (event_id, scope)
);

CREATE INDEX IF NOT EXISTS ix_event_meet_stats_cache_event_scope
  ON event_meet_stats_cache (event_id, scope);
