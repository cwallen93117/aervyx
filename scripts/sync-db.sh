#!/usr/bin/env bash
# Sync a PostgreSQL database between Aervyx environments.
#
# Usage:
#   ./scripts/sync-db.sh <source> <target> [--anonymize] [--skip-confirm]
#
# Environments: prod, staging, alpha
#
# Examples:
#   ./scripts/sync-db.sh prod alpha --anonymize      # prod → alpha, redact PII
#   ./scripts/sync-db.sh staging alpha                # staging → alpha
#   ./scripts/sync-db.sh prod staging --anonymize     # prod → staging, redact PII
set -euo pipefail

SOURCE_ENV="${1:-}"
TARGET_ENV="${2:-}"
ANONYMIZE=false
SKIP_CONFIRM=false

shift 2 || true
for arg in "$@"; do
  case "$arg" in
    --anonymize) ANONYMIZE=true ;;
    --skip-confirm) SKIP_CONFIRM=true ;;
    *) echo "Unknown flag: $arg"; exit 1 ;;
  esac
done

if [[ -z "$SOURCE_ENV" || -z "$TARGET_ENV" ]]; then
  echo "Usage: $0 <source> <target> [--anonymize] [--skip-confirm]"
  echo "Environments: prod, staging, alpha"
  exit 1
fi

if [[ "$SOURCE_ENV" == "$TARGET_ENV" ]]; then
  echo "ERROR: Source and target must be different environments."
  exit 1
fi

# Map environment names to compose project names and repo paths.
ROOT_DIR="${ROOT_DIR:-/srv/aervyx-staging}"

declare -A PROJECT_NAMES=( [prod]=aervyx-prod [staging]=aervyx-staging [alpha]=aervyx-alpha )
declare -A REPO_DIRS=( [prod]="${ROOT_DIR}/repo" [staging]="${ROOT_DIR}/staging-repo" [alpha]="${ROOT_DIR}/alpha-repo" )

for env in "$SOURCE_ENV" "$TARGET_ENV"; do
  if [[ -z "${PROJECT_NAMES[$env]:-}" ]]; then
    echo "ERROR: Unknown environment '$env'. Use: prod, staging, alpha"
    exit 1
  fi
done

SOURCE_PROJECT="${PROJECT_NAMES[$SOURCE_ENV]}"
TARGET_PROJECT="${PROJECT_NAMES[$TARGET_ENV]}"
SOURCE_REPO="${REPO_DIRS[$SOURCE_ENV]}"
TARGET_REPO="${REPO_DIRS[$TARGET_ENV]}"

BACKUP_DIR="${ROOT_DIR}/backups/sync"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_FILE="${BACKUP_DIR}/${SOURCE_ENV}-to-${TARGET_ENV}-${TIMESTAMP}.sql.gz"

echo "=== Database Sync: $SOURCE_ENV → $TARGET_ENV ==="
echo "Source project: $SOURCE_PROJECT"
echo "Target project: $TARGET_PROJECT"
echo "Anonymize: $ANONYMIZE"
echo ""

# --- Step 1: Export from source ---
echo "[1/4] Exporting from $SOURCE_ENV..."
cd "$SOURCE_REPO"
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T db \
  pg_dump -U flightcomp flightcomp | gzip > "$DUMP_FILE"

dump_size="$(du -h "$DUMP_FILE" | cut -f1)"
echo "  Exported ($dump_size)"

# --- Step 2: Confirm ---
if [[ "$SKIP_CONFIRM" != "true" ]]; then
  echo ""
  echo "[2/4] About to OVERWRITE $TARGET_ENV database."
  read -rp "  Continue? (y/N): " reply
  if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
  fi
else
  echo "[2/4] Skipping confirmation (--skip-confirm)"
fi

# --- Step 3: Restore to target ---
echo ""
echo "[3/4] Restoring to $TARGET_ENV..."
cd "$TARGET_REPO"
gunzip < "$DUMP_FILE" | docker compose --env-file .env.production -f docker-compose.prod.yml exec -T db \
  psql -U flightcomp -d flightcomp --quiet --single-transaction

echo "  Restored"

# --- Step 4: Anonymize ---
if [[ "$ANONYMIZE" == "true" ]]; then
  echo ""
  echo "[4/4] Anonymizing sensitive data..."
  docker compose --env-file .env.production -f docker-compose.prod.yml exec -T db \
    psql -U flightcomp -d flightcomp --quiet <<'SQL'
BEGIN;

-- Redact user credentials
UPDATE users SET
  password_hash = 'redacted',
  oauth_id = NULL,
  oauth_provider = NULL
WHERE password_hash IS NOT NULL OR oauth_id IS NOT NULL;

-- Anonymize pilot PII
UPDATE pilots SET
  email = 'pilot_' || id || '@test.aervyx.net',
  first_name = 'Pilot',
  last_name = 'P' || id
WHERE email IS NOT NULL;

COMMIT;
SQL
  echo "  Anonymized"
else
  echo "[4/4] Skipping anonymization"
fi

echo ""
echo "=== Sync complete ==="
echo "Backup saved: $DUMP_FILE"
