# Local Fleet Profile Overlay

Create `aervyx_profiles.local.yaml` in this directory before packaging a fleet
release. This file is intentionally ignored by git because it can contain MQTT,
Wi-Fi, and channel secrets.

Example shape:

```yaml
profiles:
  pilot:
    settings:
      module_config:
        mqtt:
          username: fleet-user
          password: fleet-password
      channel:
        primary:
          psk: default
  driver_wifi:
    settings:
      config:
        network:
          wifi_ssid: event-wifi
          wifi_psk: event-wifi-password
      module_config:
        mqtt:
          username: fleet-user
          password: fleet-password
  base_station:
    settings:
      config:
        network:
          wifi_ssid: event-wifi
          wifi_psk: event-wifi-password
      module_config:
        mqtt:
          username: fleet-user
          password: fleet-password
```

The GUI does not ask operators for these values. If a required placeholder is
still present, applying a profile is blocked before any radio is changed.
