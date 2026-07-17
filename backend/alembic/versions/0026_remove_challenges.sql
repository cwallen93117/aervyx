UPDATE events
SET visibility = 'participants'
WHERE event_kind = 'challenge'
  AND visibility = 'public'
  AND public_listed = FALSE;

DELETE FROM events WHERE event_kind = 'challenge_defaults';

DROP TABLE IF EXISTS event_collaborators;
DROP INDEX IF EXISTS ix_events_event_kind;
DROP INDEX IF EXISTS ix_events_owner_user_id;
DROP INDEX IF EXISTS ix_events_public_slug;

ALTER TABLE events
  DROP COLUMN IF EXISTS event_kind,
  DROP COLUMN IF EXISTS owner_user_id,
  DROP COLUMN IF EXISTS source_buddy_group_id,
  DROP COLUMN IF EXISTS public_slug,
  DROP COLUMN IF EXISTS public_listed;

ALTER TABLE users DROP COLUMN IF EXISTS challenge_settings_json;
