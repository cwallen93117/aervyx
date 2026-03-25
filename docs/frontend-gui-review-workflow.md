# Frontend GUI Review Workflow

This repo uses a dedicated Claude advisory lane for frontend work.

## Default Rule

- All frontend asks are eligible for Claude review.
- Codex remains the implementation owner.
- Claude is advisory for non-GUI frontend work.
- Claude sets the direction for GUI-heavy frontend work unless blocked by a hard repo constraint.
- Codex still checks file ownership, performance, and technical fit before integrating the chosen solution.

## When To Use Claude

Use Claude on:

- layout redesigns
- replay/task-map overlay changes
- Scoring Operations visual structure
- admin/settings visual organization
- interaction-heavy frontend changes
- frontend data/state issues where a second opinion could reduce rework

## GUI-Heavy Review Pattern

For larger GUI asks:

1. Send the request to Claude first.
2. Ask for implementation approaches and tradeoffs.
3. Do at least one follow-up iteration if the change is visually significant.
4. Claude chooses the preferred GUI direction.
5. Codex implements and integrates that direction unless a hard repo constraint forces an adjustment.

## Non-GUI Frontend Pattern

For non-GUI frontend asks:

1. Claude can be consulted for a second opinion.
2. Codex chooses the implementation path.
3. Codex implements and integrates the change.

## Thread Ownership

Use these lanes to avoid collisions:

- Task Builder / Planner
  - `frontend/src/components/dashboard/TasksSection.tsx`
  - `frontend/src/components/TaskBuilderMap.tsx`
- Replay / Task Map
  - `frontend/src/components/TaskMap.tsx`
- Scoring Operations
  - `frontend/src/components/dashboard/ScoringOperationsPanel.tsx`
  - write-side scoring/upload APIs
- Results Portal / Overall Results
  - `frontend/src/components/dashboard/ScoringSection.tsx`
  - read-side results queries
- Claude GUI Advisor
  - decision-maker for GUI-heavy frontend direction
  - no primary ownership of shared repo files

## Helper Script

Use the Windows helper when you want a structured Claude advisory pass:

- `scripts/windows/claude-frontend-review.ps1`

Examples:

```powershell
.\scripts\windows\claude-frontend-review.ps1 -Prompt "Review the replay bar layout and suggest a cleaner compact design."
```

```powershell
.\scripts\windows\claude-frontend-review.ps1 -GuiHeavy -Prompt "Recommend the best layout for the Scoring Operations footer buttons and feedback area."
```

```powershell
.\scripts\windows\claude-frontend-review.ps1 -GuiHeavy -Prompt "Suggest a redesign for the task planner fullscreen footer." -Files frontend/src/components/dashboard/TasksSection.tsx,frontend/src/app/globals.css
```

## Output Expectations

Claude should provide:

- recommended approach
- notable alternatives
- repo-aware implementation advice
- risks or tradeoffs

Codex should then summarize:

- what Claude chose
- any repo constraint that required adaptation
- how the chosen direction was implemented
