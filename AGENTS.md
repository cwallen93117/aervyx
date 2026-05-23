# Agent Instructions

## Automatic Staging Push

Charles expects completed changes in this repository to show up on the live staging site without an extra reminder.

- After making code or documentation changes, run the appropriate verification for the change.
- For any mobile app change, bump `mobile/pubspec.yaml` version/build, add a user-facing `CHANGELOG.md` entry, build the release APK for staging, and upload that APK plus release notes to the staging app download endpoint before reporting the task as done.
- Commit the changes you made and push them to `origin/staging` before reporting the task as done, unless Charles explicitly asks to keep the work local or target a different branch.
- Stage only the files and hunks you intentionally changed. Do not include unrelated pre-existing dirty worktree changes.
- If a push, build, test, or deploy trigger fails, debug it and report the blocker clearly instead of leaving the change only local.
- Never promote `staging` to `main` or production without explicit approval.

## Repository Notes

- Staging deploys from the `staging` branch.
- Production deploys from the `main` branch.
- Prefer keeping the current branch aligned with `staging` for routine user-requested changes.
