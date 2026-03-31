#!/usr/bin/env bash
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
STAGING_ROOT="${STAGING_ROOT:-/srv/aervyx-staging}"
DOCKER_KEYRING="/etc/apt/keyrings/docker.asc"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root."
  exit 1
fi

apt-get update
apt-get install -y \
  ca-certificates \
  curl \
  fail2ban \
  git \
  python3 \
  python3-pip \
  qemu-guest-agent \
  ufw

install -m 0755 -d /etc/apt/keyrings
if [[ ! -f "${DOCKER_KEYRING}" ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o "${DOCKER_KEYRING}"
  chmod a+r "${DOCKER_KEYRING}"
fi

. /etc/os-release
cat >/etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=${DOCKER_KEYRING}] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable
EOF

apt-get update
apt-get install -y \
  containerd.io \
  docker-buildx-plugin \
  docker-ce \
  docker-ce-cli \
  docker-compose-plugin

if ! id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "${DEPLOY_USER}"
fi

usermod -aG docker "${DEPLOY_USER}"

install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${STAGING_ROOT}"
install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${STAGING_ROOT}/repo"
install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${STAGING_ROOT}/logs"
install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${STAGING_ROOT}/backups"
install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${STAGING_ROOT}/hooks"

systemctl enable --now docker
systemctl enable --now qemu-guest-agent
systemctl enable --now fail2ban

ufw allow OpenSSH
ufw --force enable

cat <<EOF
Ubuntu staging bootstrap complete.

Next steps:
1. Clone the repo into ${STAGING_ROOT}/repo as ${DEPLOY_USER}
2. Copy staging env files into place
3. Install the webhook and backup systemd units
4. Create the Cloudflare tunnel and Access policy
EOF
