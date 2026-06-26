ALTER TABLE users
  ADD COLUMN IF NOT EXISTS challenge_settings_json JSON;

ALTER TABLE events
  ADD COLUMN IF NOT EXISTS event_kind VARCHAR(20) NOT NULL DEFAULT 'competition',
  ADD COLUMN IF NOT EXISTS owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS source_buddy_group_id INTEGER REFERENCES buddy_groups(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS public_slug VARCHAR(80),
  ADD COLUMN IF NOT EXISTS public_listed BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE events SET event_kind = 'competition' WHERE event_kind IS NULL;
UPDATE events SET public_listed = TRUE WHERE public_listed IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ix_events_public_slug ON events(public_slug);
CREATE INDEX IF NOT EXISTS ix_events_event_kind ON events(event_kind);
CREATE INDEX IF NOT EXISTS ix_events_owner_user_id ON events(owner_user_id);

CREATE TABLE IF NOT EXISTS event_collaborators (
  id SERIAL PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL DEFAULT 'editor',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_event_collaborator_event_user UNIQUE (event_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_event_collaborators_event_id ON event_collaborators(event_id);
CREATE INDEX IF NOT EXISTS ix_event_collaborators_user_id ON event_collaborators(user_id);
CREATE INDEX IF NOT EXISTS ix_event_collaborators_event_user ON event_collaborators(event_id, user_id);
