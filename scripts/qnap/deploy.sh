#!/bin/sh
set -eu

ROOT_DIR="${1:-/share/Container/flightcomp-platform}"

if [ ! -d "$ROOT_DIR/app" ]; then
  echo "Repository not found at $ROOT_DIR/app. Run github-sync.sh first."
  exit 1
fi

cd "$ROOT_DIR/app"

if [ ! -f .env ]; then
  cp .env.example .env
fi

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
fi

if [ ! -f frontend/.env.local ]; then
  cp frontend/.env.local.example frontend/.env.local
fi

docker compose -f docker-compose.qnap.yml up -d --build
