# Aervyx Mobile Changelog

## 0.4.27+44 - 2026-05-24

### Changed
- Meshtastic peer positions continue relaying to Aervyx outside active recording, but this device's own mesh position is no longer duplicated through the mesh relay path.
- The tracking low-battery guard now also pauses peer mesh relays at or below the configured battery limit.
