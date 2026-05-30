-- Backfill canonical pilot links for user-owned live tracking rows.
--
-- Older app uploads can have user_id populated while pilot_id is NULL. Once a
-- user is linked to a pilot, those rows should share the same canonical live
-- subject so public/admin tracking does not split one person into user and
-- pilot identities.

UPDATE live_positions AS lp
SET pilot_id = u.pilot_id
FROM users AS u
WHERE lp.user_id = u.id
  AND lp.pilot_id IS NULL
  AND u.pilot_id IS NOT NULL
  AND COALESCE(NULLIF(lower(trim(u.profile_type)), ''), 'pilot') <> 'driver';

UPDATE tracking_sessions AS ts
SET pilot_id = u.pilot_id
FROM users AS u
WHERE ts.user_id = u.id
  AND ts.pilot_id IS NULL
  AND u.pilot_id IS NOT NULL
  AND COALESCE(NULLIF(lower(trim(u.profile_type)), ''), 'pilot') <> 'driver';
