#!/usr/bin/env bash
# Production deploy wrapper — sets prod-specific vars and calls deploy-common.sh.
set -euo pipefail

export ROOT_DIR="${ROOT_DIR:-/srv/aervyx-staging}"
export REPO_DIR="${REPO_DIR:-${ROOT_DIR}/repo}"
export BRANCH="main"
export ENV_FILE=".env.production"
export DEPLOY_LABEL="prod"
export ENABLE_CLOUDFLARED="0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/deploy-common.sh"
