-- Toggle automatic retention deletion of raw live tracking positions.

ALTER TABLE site_settings
    ADD COLUMN IF NOT EXISTS live_position_pruning_enabled BOOLEAN NOT NULL DEFAULT TRUE;
