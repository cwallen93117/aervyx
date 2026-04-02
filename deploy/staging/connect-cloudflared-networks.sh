#!/usr/bin/env bash
# Connect the cloudflared container to both Docker networks so it can
# route traffic to both the production and staging stacks.
set -euo pipefail

CLOUDFLARED_CONTAINER="${CLOUDFLARED_CONTAINER:-aervyx-cloudflared}"

for network in aervyx-prod_default aervyx-staging_default aervyx-alpha_default; do
  if docker network inspect "${network}" >/dev/null 2>&1; then
    docker network connect "${network}" "${CLOUDFLARED_CONTAINER}" 2>/dev/null \
      && echo "Connected ${CLOUDFLARED_CONTAINER} to ${network}" \
      || echo "${CLOUDFLARED_CONTAINER} already on ${network} (or network not ready)"
  else
    echo "Network ${network} does not exist yet, skipping"
  fi
done
