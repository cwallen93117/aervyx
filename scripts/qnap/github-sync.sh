#!/bin/sh
set -eu

ROOT_DIR="${1:-/share/Container/aervyx}"
REPO_SSH="${REPO_SSH:-git@github.com:cwallen93117/aervyx.git}"
GIT_IMAGE="${GIT_IMAGE:-alpine/git:2.47.2}"
if command -v docker >/dev/null 2>&1; then
  DOCKER_BIN="$(command -v docker)"
else
  DOCKER_BIN="/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker"
fi

mkdir -p "$ROOT_DIR/.ssh"
chmod 700 "$ROOT_DIR/.ssh"

if [ ! -f "$ROOT_DIR/.ssh/known_hosts" ]; then
  "$DOCKER_BIN" run --rm --entrypoint sh -v "$ROOT_DIR/.ssh:/root/.ssh" "$GIT_IMAGE" -lc \
    "mkdir -p /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts"
  chmod 600 "$ROOT_DIR/.ssh/known_hosts"
fi

if [ -d "$ROOT_DIR/app/.git" ]; then
  "$DOCKER_BIN" run --rm \
    -v "$ROOT_DIR/app:/repo" \
    -v "$ROOT_DIR/.ssh:/root/.ssh" \
    "$GIT_IMAGE" \
    -C /repo pull --ff-only origin main
else
  rm -rf "$ROOT_DIR/app"
  "$DOCKER_BIN" run --rm \
    -v "$ROOT_DIR:/work" \
    -v "$ROOT_DIR/.ssh:/root/.ssh" \
    "$GIT_IMAGE" \
    clone "$REPO_SSH" /work/app
fi
