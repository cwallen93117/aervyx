ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_zone_id VARCHAR(120);

ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_encrypted_api_token TEXT;

ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_record_names JSON;

ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_check_interval_hours INTEGER NOT NULL DEFAULT 12;

ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_last_checked_at TIMESTAMP;

ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_last_public_ip VARCHAR(45);

ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_last_update_result VARCHAR(255);

ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS cloudflare_ddns_last_error TEXT;
