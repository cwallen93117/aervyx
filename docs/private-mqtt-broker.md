# Private Meshtastic MQTT Broker

Aervyx includes a Mosquitto container in Docker Compose. The backend should use
the internal Docker listener (`mosquitto:1883`), while Meshtastic devices should
use a public TLS listener such as `mqtt-staging.aervyx.net:8883`.

## VM Setup

1. Point DNS at the VM:
   - staging: `mqtt-staging.aervyx.net`
   - production: `mqtt.aervyx.net`

2. Create VM-managed directories:

```bash
sudo mkdir -p /srv/aervyx-staging/mosquitto/{conf.d,certs,secrets}
sudo chown -R deploy:deploy /srv/aervyx-staging/mosquitto
```

3. Install a public certificate for the MQTT hostname. Copy or symlink the
certificate files to:

```text
/srv/aervyx-staging/mosquitto/certs/fullchain.pem
/srv/aervyx-staging/mosquitto/certs/privkey.pem
```

4. Create the shared fleet password file:

```bash
docker run --rm -it \
  -v /srv/aervyx-staging/mosquitto/secrets:/mosquitto/secrets \
  eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/secrets/passwords aervyx-mesh
```

5. Enable the TLS listener:

```bash
cp /srv/aervyx-staging/staging-repo/mosquitto/config/conf.d/public-tls.conf.example \
  /srv/aervyx-staging/mosquitto/conf.d/public-tls.conf
```

6. Confirm `.env.production` includes:

```bash
MOSQUITTO_EXTRA_CONFIG_DIR=/srv/aervyx-staging/mosquitto/conf.d
MOSQUITTO_CERT_DIR=/srv/aervyx-staging/mosquitto/certs
MOSQUITTO_SECRET_DIR=/srv/aervyx-staging/mosquitto/secrets
```

7. Redeploy staging. Mosquitto should listen internally on `1883` and publicly
on TLS port `8883`.

## Aervyx Settings

In Admin → Meshtastic Configuration → MQTT / Mesh:

- MQTT enabled: on
- Broker mode: Private
- MQTT host: `mqtt-staging.aervyx.net`
- MQTT port: `8883`
- TLS enabled: on
- MQTT username/password: match the fleet credential
- Topic prefix: `msh`
- Channel PSK: blank/default unless using a custom channel PSK

When these settings are saved, the backend reconnects to the internal broker,
and the mobile app will push the external broker settings to Meshtastic radios.

## Validation

Publish a test packet from a configured Meshtastic node and watch:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f mosquitto backend
```

Aervyx stores live map positions only from `POSITION_APP` packets. Map Reporting
is still separate and should not be used as the live tracking source.
