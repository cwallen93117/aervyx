# Agent Instructions

## Delivery

- Verify completed changes with the smallest relevant tests and builds.
- Commit only intentional files and push routine work to `origin/staging`.
- Do not promote or modify `main` unless the user explicitly requests a
  production release.
- Preserve unrelated worktree changes.

## Security

- Never commit environment files, credentials, device exports, private keys,
  production data, or workstation-specific paths.
- Use the tracked example files for configuration documentation.

## Mobile Releases

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
