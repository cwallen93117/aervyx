# Aervyx Mobile Changelog

## 0.4.30+47 - 2026-05-25

### Fixed
- The in-app Download latest app link now opens the staging download page for staging builds instead of sending testers to the production website.

## 0.4.29+46 - 2026-05-25

### Fixed
- Driver mode now stays usable when there is no active task, so drivers can still start tracking and relaying without seeing a blocking error.

## 0.4.28+45 - 2026-05-25

### Added
- Settings now includes a Pilot/Driver profile toggle that syncs with the website profile type.
- Driver mode can start and stop immediate driver position tracking and mesh relaying from the driver pickup screen.

### Changed
- Driver positions render as car markers on mobile maps, while pilot markers remain aircraft-specific.
- Driver tracking skips takeoff and landing detection and does not create IGC flight logs.

## 0.4.27+44 - 2026-05-24

### Changed
- Meshtastic peer positions continue relaying to Aervyx outside active recording, but this device's own mesh position is no longer duplicated through the mesh relay path.
- The tracking low-battery guard now also pauses peer mesh relays at or below the configured battery limit.
