-- Add status lifecycle columns to sos_alerts for admin management.
-- Allows admins to acknowledge and resolve SOS alerts, record who resolved them,
-- and attach internal notes.  The status column defaults to 'active' so all
-- existing rows remain in the correct state without a data migration.

ALTER TABLE sos_alerts ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE sos_alerts ADD COLUMN acknowledged_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE sos_alerts ADD COLUMN resolved_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE sos_alerts ADD COLUMN resolved_by VARCHAR(100) NULL;
ALTER TABLE sos_alerts ADD COLUMN notes TEXT NULL;
