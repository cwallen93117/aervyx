# Aervyx Mobile Changelog

## 0.4.67+84 - 2026-06-27

### Added
- Swipe navigation now moves between the map, logbook, challenges, and settings
  screens while keeping shutdown out of the swipe flow.

## 0.4.66+83 - 2026-06-26

### Added
- Challenges now include a mobile task builder that loads the challenge waypoint
  file, lets pilots select waypoint markers, edit type/direction/radius/order,
  and saves the task back to the website.

## 0.4.65+82 - 2026-06-26

### Changed
- Meshtastic Bluetooth scans now use the connected device's current short name
  for the saved reconnect target and avoid replaying stale scan results.

## 0.4.64+81 - 2026-06-24

### Changed
- Challenges are now available from the mobile home screen for every signed-in
  profile, including drivers.

## 0.4.63+80 - 2026-06-21

### Added
- Added a native Challenges screen for pilots to create and review one-off XC
  and race-to-goal challenges from the app.

## 0.4.62+79 - 2026-06-21

### Changed
- Driver mode now shows relay time inside the active relay card beside the
  relay status instead of as a separate row below the card.

## 0.4.61+78 - 2026-06-21

### Changed
- Driver mode now hides the Flights/logbook shortcut.
- The driver relay card now includes the active task summary, while the pilot
  relay list is a larger standalone card.
- The driver pilot list now shows altitude, distance remaining around the
  active task to goal, and a directions button for each pilot.

## 0.4.60+77 - 2026-06-12

### Changed
- Driver mode now shows only the live tracking notification while relaying.
- The driver relay card is more compact, removes duplicate server/mesh cards,
  and includes a scrollable pilot relay table.
- Drivers no longer see the Send SOS button, and active pilot SOS alerts now
  surface in the driver app with local Android notifications.

## 0.4.59+76 - 2026-06-12

### Changed
- Flight log book cards now show max climb rate instead of raw track-point
  count.
- Log book altitude, speed, climb-rate, and detail-map readouts now follow the
  units selected in Settings.

## 0.4.58+75 - 2026-06-12

### Changed
- Free-flight GPS logging now uses the same dense GPS settings as event
  tracking.
- Live tracking now builds phone-first merged tracks and uses dashed mesh
  segments only to fill phone reception gaps.
- Driver profiles now enter the standard home screen instead of the dedicated
  driver home route, auto-start relaying, and show relay, mesh, and server
  status instead of a manual start/stop button.

## 0.4.57+74 - 2026-06-12

### Changed
- Settings now defaults Sport type to Hang Glider, saves sport type changes
  across app restarts, and shows matching sport icons in the Sport type and
  Pilot mode rows.
- Added an info dialog explaining that Sport type controls automatic takeoff
  and re-launch detection thresholds.
- Mobile flight-detection settings now read the backend's nested metric
  threshold response, so admin-configured values can override the built-in
  defaults.

## 0.4.56+73 - 2026-06-05

### Fixed
- The update check now treats versions with or without a leading "v" as the
  same version, preventing another false update prompt after installation.
- The update dialog now shows Installed Version and Current Version labels so
  the comparison is clearer.

## 0.4.55+72 - 2026-06-05

### Fixed
- The update check now suppresses prompts when the installed app version text
  already matches the server version, and uses Android's native version code as
  a backup to avoid false update prompts.

## 0.4.54+71 - 2026-06-05

### Fixed
- Meshtastic live-position relay now preserves sequence numbers and uses the
  documented GPS fix timestamp, improving fused live tracks when phone and mesh
  data overlap.

## 0.4.53+70 - 2026-06-05

### Fixed
- The startup update prompt now appears from the app navigator, asks users
  Yes/No whether they want to download the newer version, and shows download
  progress while the APK is retrieved.

## 0.4.52+69 - 2026-06-05

### Fixed
- Meshtastic Bluetooth reconnect now uses an immediate foreground connect when
  pilots tap reconnect or start recording, then falls back to discovery if the
  saved radio cannot be reached directly.
- Start Recording waits briefly for the mesh radio and shows a non-fatal
  warning when reconnect fails while continuing cellular/GPS recording.

## 0.4.51+68 - 2026-06-04

### Fixed
- Foreground-service GPS updates now feed the active IGC recording when the
  foreground location stream goes quiet, keeping tracklogs recording while the
  app is backgrounded or the screen is off.
- Backend-offline upload errors no longer hide an active landing countdown
  message.

## 0.4.50+67 - 2026-06-04

### Fixed
- Completed task flights now upload their IGC tracklogs to task scoring even
  after tracking state is cleared during stop/landing.
- Stale "Backend offline" warnings now clear after the server is reachable
  again.

## 0.4.49+66 - 2026-06-02

### Added
- On first app open, Aervyx now checks the published Android release and shows
  an Update button when a newer APK is available. The button downloads the APK
  and opens Android's installer automatically.

## 0.4.48+65 - 2026-06-02

### Changed
- Starting tracking now force-requests reconnect to the saved Meshtastic
  Bluetooth device when the mesh radio is not already connected.
- Second-flight monitoring now actively polls for fresh low-power GPS fixes so
  re-launch detection is less dependent on platform stream emissions.
- Mesh-sourced pilots on the live map now use dashed marker rings to match the
  website map.

## 0.4.47+64 - 2026-06-01

### Added
- The pilot live map now downloads and displays the active task event's enabled
  airspace and restricted-field overlays alongside the task course.

## 0.4.46+63 - 2026-06-01

### Added
- The pilot live map now draws the active task course with turnpoint cylinders,
  numbered task point markers, and the course line when task-mode tracking is
  active.

## 0.4.45+62 - 2026-06-01

### Changed
- The home screen now shows the active task name above the SOS button while
  tracking, so pilots can confirm task-mode recording is active.

## 0.4.44+61 - 2026-06-01

### Changed
- Normal task-flight IGC recording now logs track points every 0.5 seconds
  while live site uploads keep their existing adaptive cadence.

## 0.4.43+60 - 2026-05-31

### Fixed
- Android relaunch now resumes active tracking after minimizing or closing the
  app outside the in-app Shut Down button, and launcher/notification relaunches
  no longer create duplicate app instances.

## 0.4.42+59 - 2026-05-30

### Changed
- Meshtastic profile saves are temporarily disabled while profile writing is
  paused.

## 0.4.41+58 - 2026-05-29

### Fixed
- Phone app position uploads now include phone battery level and the time the
  battery was read, so admin debug battery ages do not refresh on every GPS
  point unless the phone battery was actually sampled again.

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
