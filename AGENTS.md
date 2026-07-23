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

For Android/mobile app changes, bump the app version and build number, update
both changelogs, build the release APK, publish the APK and release notes, and
verify the public download before reporting completion.
