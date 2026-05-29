-- Track when phone/app live position battery percentage was last read.

ALTER TABLE live_positions
    ADD COLUMN IF NOT EXISTS battery_level_seen_at TIMESTAMPTZ;

UPDATE live_positions
SET battery_level_seen_at = "timestamp"
WHERE battery_level IS NOT NULL
  AND battery_level_seen_at IS NULL;
