-- Add user-owned Meshtastic device inventory.
-- users.mesh_device_id remains as a compatibility mirror of each user's
-- active tracking device during the transition.

CREATE TABLE IF NOT EXISTS mesh_devices (
    id            SERIAL PRIMARY KEY,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id     VARCHAR(80) NOT NULL,
    label         VARCHAR(160) NOT NULL,
    purpose       VARCHAR(32) NOT NULL DEFAULT 'tracking',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesh_devices_device_id UNIQUE (device_id)
);

CREATE INDEX IF NOT EXISTS ix_mesh_devices_owner_user_id
    ON mesh_devices (owner_user_id);

CREATE INDEX IF NOT EXISTS ix_mesh_devices_purpose
    ON mesh_devices (purpose);

INSERT INTO mesh_devices (owner_user_id, device_id, label, purpose, is_active)
SELECT id, mesh_device_id, COALESCE(NULLIF(full_name, ''), username), 'tracking', is_active
FROM users
WHERE mesh_device_id IS NOT NULL
  AND mesh_device_id <> ''
ON CONFLICT (device_id) DO NOTHING;
