#!/usr/bin/env bash
# Alpha deploy wrapper — sets alpha-specific vars and calls deploy-common.sh.
set -euo pipefail

export ROOT_DIR="${ROOT_DIR:-/srv/aervyx-staging}"
export REPO_DIR="${REPO_DIR:-${ROOT_DIR}/alpha-repo}"
export BRANCH="${BRANCH:-alpha}"
export ENV_FILE=".env.production"
export DEPLOY_LABEL="alpha"
export ENABLE_CLOUDFLARED="0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/deploy-common.sh"
