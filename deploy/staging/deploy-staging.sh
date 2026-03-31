#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/srv/aervyx-staging}"
REPO_DIR="${REPO_DIR:-${ROOT_DIR}/repo}"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/logs}"
STATE_DIR="${STATE_DIR:-${ROOT_DIR}/hooks}"
BRANCH="${BRANCH:-staging}"
ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
CLOUDFLARE_CONFIG="${CLOUDFLARE_CONFIG:-deploy/cloudflared/config.yml}"
ENABLE_CLOUDFLARED="${ENABLE_CLOUDFLARED:-1}"
LOCK_FILE="${LOCK_FILE:-${STATE_DIR}/deploy.lock}"

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
log_file="${LOG_DIR}/deploy-${timestamp}.log"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Another staging deployment is already running."
  exit 0
fi

exec > >(tee -a "${log_file}") 2>&1

echo "== Aervyx staging deploy starting =="
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

deployed_sha="$(git rev-parse HEAD)"
printf '%s %s\n' "${timestamp}" "${deployed_sha}" >"${STATE_DIR}/last-deployed.txt"

echo "Deploy complete for ${deployed_sha}"
