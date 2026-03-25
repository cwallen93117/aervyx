#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT_IN_WINDOWS="${1:-/mnt/c/Projects/scoring software- codex}"
TARGET_DIR="${2:-$HOME/projects/aervyx}"

sudo apt-get update
sudo apt-get install -y rsync ca-certificates curl git

mkdir -p "$(dirname "$TARGET_DIR")"
mkdir -p "$TARGET_DIR"

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'frontend/.next/' \
  --exclude 'backend/.venv/' \
  --exclude '.codex_tmp/' \
  "$REPO_ROOT_IN_WINDOWS/" "$TARGET_DIR/"

cd "$TARGET_DIR"
[ -f .env ] || cp .env.example .env
[ -f backend/.env ] || cp backend/.env.example backend/.env
[ -f frontend/.env.local ] || cp frontend/.env.local.example frontend/.env.local

docker compose up -d --build

echo ""
echo "Aervyx is starting locally in WSL."
echo "Frontend: http://localhost:3000/login"
echo "Backend:  http://localhost:8000/health"
