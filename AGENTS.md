# Agent Instructions

## Automatic Staging Push

Charles expects completed changes in this repository to ship from `staging` without an extra reminder.

- After making code or documentation changes, run the appropriate verification for the change.
- Commit the changes you made and push them to `origin/staging` before reporting the task as done, unless Charles explicitly asks to keep the work local or target a different branch.
- Stage only the files and hunks you intentionally changed. Do not include unrelated pre-existing dirty worktree changes.
- If a push, build, test, or deploy trigger fails, debug it and report the blocker clearly instead of leaving the change only local.
- Do not update or promote `main` as part of routine work. Treat `main` as production and change it only when Charles explicitly asks.

## Android App Release Rule

For any Android/mobile app change, the change is not done until all release artifacts and metadata are updated:

- Bump `mobile/pubspec.yaml` version/build.
- Add user-facing entries to both root `CHANGELOG.md` and `mobile/CHANGELOG.md`.
- Build the release APK.
- Confirm the mobile API/endpoints/configuration are correct for the release.
- Upload the APK and release notes to the website app download endpoint.
- Verify the website/app download page shows the new APK and notes.
- If upload or verification needs server access, use SSH before calling it blocked:
  `ssh deploy@192.168.87.94`. Production runs as `aervyx-prod-*` under
  `/srv/aervyx-staging/repo`; the APK volume is available in
  `aervyx-prod-backend-1` at `/app/storage/apks`, with the durable seed under
  `/srv/aervyx-staging/apk-seed`. Do not stop at "no admin token" while this SSH
  path works.

## Repository Notes

- Production deploys from the `main` branch.
- `staging` is the only routine target for completed work.
- `main` should be kept behind or separate from staging work until Charles explicitly asks to promote staging to production.
