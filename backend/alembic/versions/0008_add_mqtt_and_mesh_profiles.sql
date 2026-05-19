-- Add MQTT broker settings and Meshtastic device profiles to site_settings.
-- MQTT columns let the admin choose between the public meshtastic.org broker
-- and a private Mosquitto instance.  mesh_profiles stores the 4 profile presets
-- (pilot, driver, driver_wifi, repeater) as a JSON blob so admins can tweak
-- device configuration from the web dashboard.

ALTER TABLE site_settings ADD COLUMN mqtt_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE site_settings ADD COLUMN mqtt_broker_mode VARCHAR(20) NOT NULL DEFAULT 'public';
ALTER TABLE site_settings ADD COLUMN mqtt_host VARCHAR(255) NULL;
ALTER TABLE site_settings ADD COLUMN mqtt_port INTEGER NOT NULL DEFAULT 1883;
ALTER TABLE site_settings ADD COLUMN mqtt_topic_prefix VARCHAR(80) NOT NULL DEFAULT 'msh';
ALTER TABLE site_settings ADD COLUMN mqtt_channel_psk VARCHAR(255) NULL;
ALTER TABLE site_settings ADD COLUMN mesh_profiles JSON NULL;
