-- Track when a Meshtastic node battery percentage was last received.

ALTER TABLE mesh_node_statuses
    ADD COLUMN IF NOT EXISTS battery_level_seen_at TIMESTAMPTZ;

UPDATE mesh_node_statuses
SET battery_level_seen_at = last_seen_at
WHERE battery_level IS NOT NULL
  AND battery_level_seen_at IS NULL;
