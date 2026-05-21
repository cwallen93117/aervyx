-- Track Meshtastic MQTT packet sightings separately from GPS positions.

CREATE TABLE IF NOT EXISTS mesh_node_statuses (
    id               SERIAL PRIMARY KEY,
    device_id        VARCHAR(80) NOT NULL,
    last_seen_at     TIMESTAMPTZ NOT NULL,
    last_packet_type VARCHAR(40),
    last_source      VARCHAR(32),
    last_gateway_id  VARCHAR(80),
    last_topic       VARCHAR(255),
    packet_count     INTEGER NOT NULL DEFAULT 0,
    battery_level    INTEGER,
    long_name        VARCHAR(160),
    short_name       VARCHAR(40),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_mesh_node_statuses_device_id UNIQUE (device_id)
);

CREATE INDEX IF NOT EXISTS ix_mesh_node_statuses_last_seen_at
    ON mesh_node_statuses (last_seen_at);
