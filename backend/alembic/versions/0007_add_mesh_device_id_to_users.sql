-- Add mesh_device_id column to users table for stationary-node identification.
-- Each stationary Meshtastic relay is represented as a User row with
-- profile_type='stationary_node' and its mesh device ID stored here.
-- The mesh never transmits node-type metadata; role is resolved server-side
-- by joining LivePosition.device_id against users.mesh_device_id.

ALTER TABLE users ADD COLUMN mesh_device_id VARCHAR(80) NULL;

CREATE UNIQUE INDEX uq_users_mesh_device_id ON users (mesh_device_id);
