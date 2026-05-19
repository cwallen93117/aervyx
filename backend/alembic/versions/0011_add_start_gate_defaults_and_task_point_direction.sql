-- Add event-level Race to Goal gate defaults and explicit task-point direction.

ALTER TABLE events
    ADD COLUMN IF NOT EXISTS default_start_gate_count INTEGER NOT NULL DEFAULT 5;

ALTER TABLE events
    ADD COLUMN IF NOT EXISTS default_start_gate_interval_seconds INTEGER NOT NULL DEFAULT 900;

UPDATE events
SET
    default_start_gate_count = COALESCE(default_start_gate_count, 5),
    default_start_gate_interval_seconds = COALESCE(default_start_gate_interval_seconds, 900);

ALTER TABLE task_points
    ADD COLUMN IF NOT EXISTS direction VARCHAR(10) NOT NULL DEFAULT 'enter';

UPDATE task_points
SET direction = 'exit'
WHERE point_type = 'start'
  AND (direction IS NULL OR direction NOT IN ('enter', 'exit'));

UPDATE task_points
SET direction = 'enter'
WHERE point_type <> 'start'
  AND (direction IS NULL OR direction NOT IN ('enter', 'exit'));

UPDATE tasks
SET task_type = 'race_to_goal_with_gates'
WHERE task_type IS NULL
   OR task_type IN ('race', 'race_to_goal', 'speedrun_interval');

UPDATE tasks
SET task_type = 'elapsed_time'
WHERE task_type = 'speedrun';
