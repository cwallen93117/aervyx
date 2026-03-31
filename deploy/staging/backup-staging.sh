#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/srv/aervyx-staging}"
REPO_DIR="${REPO_DIR:-${ROOT_DIR}/repo}"
BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups}"
ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "${BACKUP_DIR}/postgres" "${BACKUP_DIR}/uploads"

cd "${REPO_DIR}"

set -a
source "${ENV_FILE}"
set +a

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
project_name="${COMPOSE_PROJECT_NAME:-aervyx-staging}"
uploads_volume="${UPLOADS_VOLUME:-${project_name}_backend_uploads}"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T db \
  pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip >"${BACKUP_DIR}/postgres/${project_name}-${timestamp}.sql.gz"

docker run --rm \
  -v "${uploads_volume}:/data:ro" \
  -v "${BACKUP_DIR}/uploads:/backup" \
  alpine:3.20 \
  sh -c "tar czf /backup/${project_name}-${timestamp}-uploads.tgz -C /data ."

find "${BACKUP_DIR}/postgres" -type f -mtime +"${RETENTION_DAYS}" -delete
find "${BACKUP_DIR}/uploads" -type f -mtime +"${RETENTION_DAYS}" -delete

echo "Backups completed at ${timestamp}"
