-- Add visibility column to events and buddy_groups tables.
-- Events: 'public', 'users', 'participants', 'private'
-- Buddy groups: 'public', 'users', 'buddies', 'private'
-- Default is 'private' (safe default — organizer/owner opts in to sharing).

ALTER TABLE events
    ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'private';

ALTER TABLE buddy_groups
    ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'private';
