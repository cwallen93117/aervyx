#!/usr/bin/env bash
# Shared deploy logic for both production and staging.
# Do not run directly — use deploy-prod.sh or deploy-staging.sh.
set -euo pipefail

: "${ROOT_DIR:?ROOT_DIR must be set}"
: "${REPO_DIR:?REPO_DIR must be set}"
: "${BRANCH:?BRANCH must be set}"
: "${ENV_FILE:?ENV_FILE must be set}"
: "${DEPLOY_LABEL:?DEPLOY_LABEL must be set}"

LOG_DIR="${LOG_DIR:-${ROOT_DIR}/logs}"
STATE_DIR="${STATE_DIR:-${ROOT_DIR}/hooks}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENABLE_CLOUDFLARED="${ENABLE_CLOUDFLARED:-0}"
CLOUDFLARE_CONFIG="${CLOUDFLARE_CONFIG:-deploy/cloudflared/config.yml}"
LOCK_FILE="${LOCK_FILE:-${STATE_DIR}/deploy-${DEPLOY_LABEL}.lock}"

mkdir -p "${LOG_DIR}" "${STATE_DIR}"

wait_for_command() {
  local name="$1"
  shift
  local attempt
  for attempt in $(seq 1 30); do
    if "$@" >/dev/null 2>&1; then
      echo "${name} health check passed on attempt ${attempt}."
      return 0
    fi
    sleep 2
  done
  echo "${name} health check failed after 30 attempts."
  return 1
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
log_file="${LOG_DIR}/deploy-${DEPLOY_LABEL}-${timestamp}.log"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Another ${DEPLOY_LABEL} deployment is already running."
  exit 0
fi

exec > >(tee -a "${log_file}") 2>&1

echo "== Aervyx ${DEPLOY_LABEL} deploy starting =="
echo "Timestamp: ${timestamp}"
echo "Repo dir: ${REPO_DIR}"
echo "Branch: ${BRANCH}"

cd "${REPO_DIR}"

git fetch origin

if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git checkout "${BRANCH}"
else
  git checkout -b "${BRANCH}" "origin/${BRANCH}"
fi

git reset --hard "origin/${BRANCH}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}"
  exit 1
fi
if [[ ! -f backend/.env.production ]]; then
  echo "Missing backend/.env.production"
  exit 1
fi
if [[ ! -f frontend/.env.production ]]; then
  echo "Missing frontend/.env.production"
  exit 1
fi

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d db backend frontend

if [[ "${ENABLE_CLOUDFLARED}" == "1" && -f "${CLOUDFLARE_CONFIG}" ]]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --profile cloudflare up -d cloudflared
else
  echo "Skipping cloudflared startup."
fi

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps
wait_for_command "backend" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T backend \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()"
wait_for_command "frontend" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T frontend \
  wget -qO- http://127.0.0.1:3000/login >/dev/null

# Connect cloudflared to both docker networks so it can route to both stacks
CONNECT_SCRIPT="${REPO_DIR}/deploy/staging/connect-cloudflared-networks.sh"
if [[ -x "${CONNECT_SCRIPT}" ]]; then
  bash "${CONNECT_SCRIPT}"
fi

deployed_sha="$(git rev-parse HEAD)"
printf '%s %s\n' "${timestamp}" "${deployed_sha}" >"${STATE_DIR}/last-deployed-${DEPLOY_LABEL}.txt"
# Also write to the legacy path for backward compatibility
printf '%s %s\n' "${timestamp}" "${deployed_sha}" >"${STATE_DIR}/last-deployed.txt"

echo "Deploy complete for ${DEPLOY_LABEL} at ${deployed_sha}"
