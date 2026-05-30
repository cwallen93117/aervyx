-- Mark tasks that should score normally but not count toward competition totals.

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS is_practice BOOLEAN NOT NULL DEFAULT FALSE;
