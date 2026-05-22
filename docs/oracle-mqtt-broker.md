# Oracle MQTT Broker

Use this when Aervyx needs a publicly reachable private MQTT broker without
opening ports through the home Verizon/Google Wi-Fi routers. The Oracle VM runs
only Mosquitto; Aervyx and Meshtastic radios connect outbound to it.

## Oracle VM

Create an Always Free Ubuntu VM in Oracle Cloud:

- Shape: `VM.Standard.A1.Flex` if available, otherwise an Always Free micro
  instance is enough for Mosquitto.
- Image: Ubuntu.
- Public IPv4: enabled.
- SSH: use your local public key.

In the Oracle VCN security list or network security group, allow:

- TCP `22` from your IP for SSH.
- TCP `1883` from `0.0.0.0/0` for initial MQTT without TLS.

## Install Mosquitto

Copy the installer to the VM and run it:

```bash
scp deploy/mqtt-broker/install-oracle-mosquitto.sh ubuntu@<oracle-public-ip>:/tmp/
ssh ubuntu@<oracle-public-ip>
chmod +x /tmp/install-oracle-mosquitto.sh
MQTT_USER=aervyx-mesh MQTT_PASSWORD='<fleet-password>' /tmp/install-oracle-mosquitto.sh
```

The script:

- installs Mosquitto and client tools;
- creates a password file;
- limits the MQTT user to `msh/#`;
- disables anonymous MQTT;
- listens on TCP `1883`;
- opens `ufw` if it is active.

Oracle's cloud firewall still controls public ingress, so the VCN/NSG rule for
TCP `1883` must exist even if the VM firewall allows the port.

## DNS

In Cloudflare DNS for `aervyx.net`, create:

```text
Type: A
Name: mqtt-staging
IPv4 address: <oracle-public-ip>
Proxy status: DNS only
```

MQTT is raw TCP, so this record must be DNS-only, not proxied.

## Aervyx Settings

After staging is deployed with the remote-broker support, save Admin →
Meshtastic Configuration → MQTT / Mesh as:

```text
Broker mode: Private
MQTT host: mqtt-staging.aervyx.net
MQTT port: 1883
TLS enabled: off
MQTT username: aervyx-mesh
MQTT password: <fleet-password>
Topic prefix: msh
```

Set Broker mode to `Cloud VM broker`. That makes the backend subscribe to the
Admin-configured Oracle broker instead of the internal Docker `mosquitto`
service.

## Tahoe Supreme

Set Tahoe Supreme to:

```text
MQTT enabled: on
Host: mqtt-staging.aervyx.net
Port: 1883
TLS: off
Username: aervyx-mesh
Password: <fleet-password>
Root topic: msh/US
JSON: off
Encryption: off
Primary uplink: enabled
```

## Quick Test

From your workstation:

```powershell
nslookup mqtt-staging.aervyx.net
Test-NetConnection mqtt-staging.aervyx.net -Port 1883
```

From the VM:

```bash
mosquitto_sub -h localhost -p 1883 -u aervyx-mesh -P '<fleet-password>' -t 'msh/#' -v
```
