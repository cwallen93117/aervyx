# Aervyx Mobile Changelog

## 0.4.40+57 - 2026-05-29

### Changed
- The Mesh Radio row no longer repeats "Paired" when the connected radio
  already shows a battery badge and green status indicator.

## 0.4.39+56 - 2026-05-29

### Added
- The home screen now shows the connected Mesh Radio battery level beside the
  Mesh Radio label and reports the latest received radio battery timestamp to
  the site debug view.

## 0.4.38+55 - 2026-05-28

### Fixed
- Driver mode live maps now always show all active same-day pilot positions,
  include the live pilot count chip, and keep marker tap directions available
  even without an active task assignment.

## 0.4.37+54 - 2026-05-28

### Added
- Live maps now include a north-up button, colored Watch Live-style pilot
  markers, first-name plus last-initial labels, retained same-day last-known
  positions, and marker details with directions in the default map app.

## 0.4.36+53 - 2026-05-28

### Fixed
- The app now keeps the secure refresh token and automatically renews expired
  sessions, so phones stay signed in instead of showing session-expired errors
  after the short-lived access token rolls over.

## 0.4.35+52 - 2026-05-28

### Fixed
- Meshtastic Bluetooth scans now show every UUID-matching radio discovered by
  Android, including devices that do not expose a Bluetooth platform name.

## 0.4.34+51 - 2026-05-27

### Changed
- Production release builds now open the public Aervyx app download page from Settings.

## 0.4.33+50 - 2026-05-26

### Fixed
- Bluetooth auto-reconnect now starts after login or session restore even when there is no saved reconnect target yet.

## 0.4.32+49 - 2026-05-26

### Changed
- Settings now groups Battery Optimization, Tracking and mesh low-battery guard, and Critical battery shutdown under Battery Settings.
- Critical battery shutdown text now clarifies that flight recording stops when the shutdown threshold is reached.

## 0.4.31+48 - 2026-05-26

### Added
- Pilot and driver live maps now include a Map/Satellite selector and visible map scale bar.
- Driver mode now auto-starts tracking and relaying on entry, with a full-screen map, center-on-GPS control, and pilot pickup details from marker bottom sheets.

### Changed
- Pilot live view now uses the active task name as the title and no longer shows the Free flight chip.
- Profile type changes now use timestamp-based offline sync so local driver/pilot changes stay pending instead of rolling back when the device is offline.

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
