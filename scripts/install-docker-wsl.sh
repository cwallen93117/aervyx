#!/bin/bash
set -e

echo "=== Installing Docker Engine in WSL2 ==="

# Remove old packages
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Prerequisites
echo "=== Installing prerequisites ==="
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Docker GPG key
echo "=== Adding Docker GPG key ==="
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Docker repo
echo "=== Adding Docker repository ==="
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
echo "=== Installing Docker Engine ==="
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER

# Start Docker daemon
sudo service docker start

echo "=== Docker installed ==="
docker --version
docker compose version
echo "DONE"
