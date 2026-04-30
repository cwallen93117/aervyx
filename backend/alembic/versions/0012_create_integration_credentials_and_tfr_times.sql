-- Add encrypted admin-managed integration credentials and optional TFR timing metadata.

CREATE TABLE IF NOT EXISTS integration_credentials (
    provider VARCHAR(80) PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    base_url VARCHAR(255) NOT NULL DEFAULT 'https://api.faa.gov',
    client_id_header VARCHAR(80) NOT NULL DEFAULT 'client_id',
    client_secret_header VARCHAR(80) NOT NULL DEFAULT 'client_secret',
    encrypted_client_id TEXT,
    encrypted_client_secret TEXT,
    last_tested_at TIMESTAMP WITH TIME ZONE,
    last_test_status VARCHAR(20),
    last_test_message TEXT,
    updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE faa_airspace_features
    ADD COLUMN IF NOT EXISTS notam_id VARCHAR(80);

ALTER TABLE faa_airspace_features
    ADD COLUMN IF NOT EXISTS effective_start TIMESTAMP WITH TIME ZONE;

ALTER TABLE faa_airspace_features
    ADD COLUMN IF NOT EXISTS effective_end TIMESTAMP WITH TIME ZONE;

ALTER TABLE faa_airspace_features
    ADD COLUMN IF NOT EXISTS notice_time TIMESTAMP WITH TIME ZONE;
