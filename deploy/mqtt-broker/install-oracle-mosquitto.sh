#!/usr/bin/env bash
set -euo pipefail

MQTT_USER="${MQTT_USER:-aervyx-mesh}"
MQTT_PORT="${MQTT_PORT:-1883}"

if [[ -z "${MQTT_PASSWORD:-}" ]]; then
  read -rsp "MQTT password for ${MQTT_USER}: " MQTT_PASSWORD
  echo
fi

if [[ -z "${MQTT_PASSWORD}" ]]; then
  echo "MQTT_PASSWORD is required." >&2
  exit 1
fi

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y mosquitto mosquitto-clients

sudo install -d -o root -g mosquitto -m 0750 /etc/mosquitto/aervyx
sudo mosquitto_passwd -b -c /etc/mosquitto/aervyx/passwords "${MQTT_USER}" "${MQTT_PASSWORD}"
sudo chown root:mosquitto /etc/mosquitto/aervyx/passwords
sudo chmod 0640 /etc/mosquitto/aervyx/passwords

sudo tee /etc/mosquitto/aervyx/acl >/dev/null <<EOF
user ${MQTT_USER}
topic readwrite msh/#
EOF
sudo chown root:mosquitto /etc/mosquitto/aervyx/acl
sudo chmod 0640 /etc/mosquitto/aervyx/acl

sudo tee /etc/mosquitto/conf.d/aervyx.conf >/dev/null <<EOF
per_listener_settings true

listener ${MQTT_PORT} 0.0.0.0
protocol mqtt
allow_anonymous false
password_file /etc/mosquitto/aervyx/passwords
acl_file /etc/mosquitto/aervyx/acl

persistence true
persistence_location /var/lib/mosquitto/

log_dest file /var/log/mosquitto/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
EOF

sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow "${MQTT_PORT}/tcp"
fi

sudo systemctl --no-pager --full status mosquitto
echo "Mosquitto is configured on TCP ${MQTT_PORT} for user ${MQTT_USER}."
