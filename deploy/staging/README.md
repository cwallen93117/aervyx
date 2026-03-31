# Staging Deployment Assets

This folder contains the repo-tracked assets for the Proxmox Ubuntu staging VM.

## Intended Server Layout

- `/srv/aervyx-staging/repo`
- `/srv/aervyx-staging/logs`
- `/srv/aervyx-staging/backups`
- `/srv/aervyx-staging/hooks`

## Main Files

- `bootstrap-ubuntu.sh`
  Installs Docker, Compose, base packages, the deploy user, and the staging directories.
- `deploy-staging.sh`
  Fetches `origin/staging`, fast-forwards the server checkout, rebuilds the stack, and runs health checks.
- `backup-staging.sh`
  Creates `pg_dump` and uploads-volume backups.
- `webhook_listener.py`
  Minimal GitHub webhook listener that validates `X-Hub-Signature-256` and triggers the deploy script.

## Example Config

See `examples/` for:

- staging `.env.production` examples
- webhook listener environment example
- systemd unit examples

## Intended Branch Flow

The staging VM tracks only the `staging` branch.

Recommended local push pattern:

```powershell
git push origin HEAD:staging
```
