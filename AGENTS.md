# Agent Instructions

## Automatic Main Push

Charles expects completed changes in this repository to ship from `main` without an extra reminder.

- After making code or documentation changes, run the appropriate verification for the change.
- Commit the changes you made and push them to `origin/main` before reporting the task as done, unless Charles explicitly asks to keep the work local or target a different branch.
- Stage only the files and hunks you intentionally changed. Do not include unrelated pre-existing dirty worktree changes.
- If a push, build, test, or deploy trigger fails, debug it and report the blocker clearly instead of leaving the change only local.
- Do not update or promote `staging` as part of routine work. Let `staging` fall behind; it is a backup branch/environment for now and can be refreshed later only when Charles explicitly asks.

## Android App Release Rule

For any Android/mobile app change, the change is not done until all release artifacts and metadata are updated:

- Bump `mobile/pubspec.yaml` version/build.
- Add user-facing entries to both root `CHANGELOG.md` and `mobile/CHANGELOG.md`.
- Build the release APK.
- Confirm the mobile API/endpoints/configuration are correct for the release.
- Upload the APK and release notes to the website app download endpoint.
- Verify the website/app download page shows the new APK and notes.

## Repository Notes

- Production deploys from the `main` branch.
- `main` is the only routine target for completed work.
- `staging` is intentionally allowed to lag behind `main` and should be treated as a backup until Charles asks to refresh it.
