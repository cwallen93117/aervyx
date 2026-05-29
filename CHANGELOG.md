# Aervyx Changelog

All notable user-facing changes to the Aervyx platform are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and releases are dated (calendar-versioned `YYYY.MM.DD`) because Aervyx ships
continuously from `main` rather than tagging semver milestones.

Each dated section covers the PRs merged to `main` (production, `aervyx.net`)
on that day. Staging-only PRs are listed inline where they fed into the same
production release.

- Production: <https://aervyx.net> / <https://api.aervyx.net>
- Staging: <https://staging.aervyx.net> / <https://api-staging.aervyx.net>

## [2026.05.29]

### Added
- **Mobile v0.4.39+56** shows the connected Mesh Radio battery level on the
  mobile home screen and reports the latest received radio battery timestamp
  to the site debug view.

### Changed
- **Mobile v0.4.40+57** removes the redundant "Paired" text from the Mesh
  Radio row when the connected radio already shows a battery badge and green
  status indicator.
- Admin live-tracking debug now labels collapsed user-row battery readings as
  Phone and Tracker when both are present.

### Fixed
- **Mobile v0.4.41+58** sends phone battery level and read time with app
  position uploads, so admin debug phone battery ages no longer reset on every
  GPS point unless the phone battery was sampled again.

## [2026.05.28]

### Fixed
- **Mobile v0.4.35+52** fixes Meshtastic Bluetooth scans so radios without an
  Android Bluetooth platform name still appear in the pairing list.

## [2026.05.27]

### Changed
- **Mobile v0.4.34+51** is the production APK for the staging-to-main promotion and uses the public Aervyx app download page from Settings.

## [2026.05.26]

### Added
- **Mobile v0.4.31+48** adds Map/Satellite selectors and visible scale bars to pilot and driver live maps, makes driver mode a full-screen always-on tracking map, and opens pilot pickup/navigation details from marker bottom sheets.

### Changed
- **Mobile v0.4.32+49** groups the Settings battery controls under Battery Settings and clarifies that critical battery shutdown stops flight recording.
- Mobile profile type changes now use latest-timestamp-wins offline sync, keeping local Pilot/Driver changes pending until they can be reconciled with website settings.
- Pilot live view now shows the active task name as the title and removes the Free flight chip.

### Fixed
- **Mobile v0.4.33+50** fixes Bluetooth auto-reconnect startup when the app has
  no saved reconnect target yet: after login/session restore it now looks for
  system-connected, bonded, or nearby Meshtastic BLE devices and starts the
  reconnect flow without requiring the user to open the Bluetooth pairing list.
- **Meshtastic Provisioner v0.1.5** restores fixed setting labels and makes the profile headings (Pilot, Driver, Driver Wi-Fi, Base Station, and Wired Base Station) editable instead.
- **Meshtastic Provisioner v0.1.4** simplifies the Profile Matrix toolbar to Save, Save As, and Load.
- **Meshtastic Provisioner v0.1.3** keeps Profile Matrix column headings visible while scrolling, lets operators rename setting labels, and loads/reloads a specific saved matrix file instead of merging every candidate overlay.
- **Meshtastic Provisioner v0.1.2** fixes Profile Matrix mouse-wheel scrolling and adds a live current-vs-revised apply review with green OK/red Error readback statuses.

## [2026.05.25]

### Added
- **Mobile v0.4.28+45** adds a Pilot/Driver toggle in Settings, starts driver-mode tracking immediately from the driver pickup screen, relays peer pilot mesh points while publishing the driver's own phone GPS position, and renders driver subjects as car markers across live maps.
- Backend live tracking now treats driver users without linked pilot records as first-class map subjects with stable `subject_key` values and mobile-safe profile preference updates.

### Fixed
- **Mobile v0.4.30+47** points staging builds' in-app "Download latest app" link at the staging download page instead of the production website.
- **Mobile v0.4.29+46** keeps Driver Mode usable when there is no active task, allowing drivers to start tracking and relaying without the pickup screen showing a blocking error.

## [2026.05.24]

### Fixed
- Public Watch Live now opens its live position stream through the direct API
  hostname and uses thread-safe backend fan-out, so map positions can update
  without requiring a page refresh.
- **Mobile v0.4.26+43** removes the signed-in pilot's echoed server marker
  from the mobile live map so only the phone's live GPS dot represents the
  current pilot, and the location button now follows that GPS position until
  the map is moved.

## [2026.05.23]

### Added
- **Mobile v0.4.25+42** keeps the last paired Meshtastic Bluetooth device as
  the auto-reconnect target, restores it on app launch/resume, and keeps trying
  to reconnect through range loss, Bluetooth toggles, screen-off, and app
  runtime recovery until the user explicitly disconnects or forgets the device.
- **Mobile v0.4.24+41** makes the Aervyx app mesh relay the default backhaul
  for pilot and driver radios. Pilot/driver profile pushes now turn radio MQTT
  and MQTT client proxy off, while fixed gateway profiles keep private MQTT for
  Tahoe/RAK-style internet gateways.
- **Mobile v0.4.23+40** adds a Runtime critical-battery shutdown setting
  (default 5%) so the persistent Android runtime can stop Aervyx when the phone
  falls below the configured battery level while not charging. The existing
  tracking battery setting is clarified as a tracking/monitoring guard rather
  than the app-wide persistent-runtime shutdown.
- **Mobile v0.4.22+39** adds an always-on Android foreground runtime that starts
  when the app opens, keeps Aervyx alive through screen-off / waiting-for-takeoff
  states, and stops only from an explicit in-app shutdown action. The Android
  app now declares the required foreground-service, notification, wake-lock, and
  connected-device permissions for the persistent runtime.
- **Meshtastic Provisioner v0.1.1** makes the desktop profile matrix editable
  and saveable, shows MQTT usernames/passwords in the matrix, adds a Wired Base
  Station profile, and replaces the opaque position-flags number with a
  checkbox selector for each position packet field.
- **Meshtastic Provisioner v0.1.0** adds a Windows desktop GUI for scanning all
  COM ports, identifying connected Meshtastic radios, and provisioning devices
  from complete bundled Aervyx profiles. Operators enter only the device name
  and shortname; MQTT, primary-channel PSK, proxy, Wi-Fi, Bluetooth, LoRa,
  position, telemetry, neighbor-info, and store-forward settings come from the
  profile matrix.
- **Admin-only provisioner release hosting** adds private backend endpoints for
  uploading and downloading packaged provisioner builds separately from the
  public Android APK flow.

## [2026.05.22]

### Changed
- **Mobile v0.4.21+38** adds the Meshtastic MQTT client-proxy bridge inside
  Aerox/Aervyx mobile. When a radio has MQTT Client Proxy enabled and is
  connected to the app, the app can publish the radio's proxied MQTT messages
  using the phone's internet connection and forward subscribed MQTT traffic
  back to the radio over the Meshtastic PhoneAPI.

## [2026.04.11]

### Changed
- **LoRa Region is device-specific.** The Region row was removed from the
  admin Meshtastic profile editor and from the backend profile defaults
  (all four roles). Region is no longer carried in the fleet-wide profile
  JSON or pushed by `applyProfile()`. Operators set Region per device on
  the mobile Meshtastic settings screen — same pattern as Wi-Fi
  credentials. This stops a profile push from silencing radios that were
  already on a legal frequency.
- **Mobile Meshtastic settings now require Region.** When Region is unset,
  the screen shows a red banner ("LoRa Region is not set — the radio will
  NOT transmit on the right frequency until you pick a region"), the
  Region row is rendered red, and switching device role / applying a
  profile is blocked with a red snackbar until a region is chosen.

### Fixed
- **Mobile Google sign-in surfaces real errors.** `_handleGoogleSignIn`
  now catches `PlatformException` and prints actionable messages
  (`DEVELOPER_ERROR / SHA-1 not registered in Google Cloud`,
  network errors, etc.) instead of swallowing native Google Play Services
  failures into a generic "Login failed" message. The null-idToken path
  now also explains that the Android OAuth client for this build is
  probably not registered in the Google Cloud project that owns the
  web client ID.

### Added
- **Admin Meshtastic profile editor** now exposes the full ~38 fields per
  profile, grouped to mirror the official Meshtastic Android app: Device,
  Position, LoRa, Power, Bluetooth, Network, Display, and Modules. Each
  row has an inline info popover explaining what the setting does and
  what a sane default looks like (#165).
- **Per-field POSITION packet contents** in the admin Meshtastic table.
  The opaque `position_flags` bitmask is now exposed as ten individual
  toggles under the Position group — Send altitude, altitude MSL,
  geoidal separation, DOP, HDOP/VDOP, satellite count, sequence #,
  timestamp, heading, and speed. Storage and wire format are unchanged
  so existing devices keep working (#166).

### Changed
- **Meshtastic safe BLE defaults.** All four profiles (Pilot, Driver,
  Driver Wi-Fi, Repeater) now ship with `bluetooth_enabled=true` and
  `bluetooth_mode=fixed_pin` (default PIN `123456`). Previously the
  default was `random_pin`, which on a headless device with no display
  could permanently lock admins out — there was no way to read the
  generated PIN. Fixed-PIN is now the default everywhere (#166).
- **Wi-Fi credentials are device-specific, not fleet-wide.** Wi-Fi SSID
  and password are no longer part of the Meshtastic profile defaults
  on the backend, are no longer rendered in the admin profile table,
  and are no longer carried by the mobile `ProfileConfig`. Operators
  set Wi-Fi credentials per device from the Meshtastic settings screen
  on their own phone — the credentials never touch the backend or any
  other device (#166).

## [2026.04.05]

### Added
- **Watch Live** public page now renders full-screen, with the pilot list on
  the left and a "Select a source" dropdown header. SHOW_ALL debug mode
  streams every active device for on-field validation (#123, #124, #126).
- **Google account creation** on both the web sign-up tab and the mobile
  register screen — pilots can create an Aervyx account from their Google
  profile without filling out the form (#128).
- **Pilot linking**: multi-email support, broader auto-match (email →
  alt-emails → comp# → CIVL ID), and a self-service "Pilot Record" claim
  flow in Settings so imported pilots can reclaim their own record (#91).
- **Map overlays**: 2D view now flattens track altitude and the altitude
  picker is gated to 3D mode; overlay controls stay light in dark mode
  (#133, #134).
- **Dashboard Live Tracking** dropdown gained an "All users" option so
  admins can watch every active device in one view (#126).
- **Persistent IGC upload retry queue** so flights queued offline finish
  uploading when the network returns (#87).
- **Auto-upload IGC after landing**, with scoring integration so a flight
  appears in the logbook and the active task as soon as the pilot lands
  (#84).
- **Event and buddy-group visibility controls** for organizers (#85).
- **Dynamic app version** display on the mobile login screen (#81, #114).
- **Participant management**: remove-confirmation dialog, bulk select, and
  denser tables (#97).

### Fixed
- **Logbook IGC download filenames** now preserve the original
  mobile-saved name (e.g. `Charles-2026-04-05-#1.igc`) instead of
  `flight-{id}.igc` (#135).
- **Start-cylinder detection** no longer leaks the epoch SS time when the
  task has no start-window exit; falls back to the pilot's last exit
  instead (#107, #118, #131).
- **Tracking heartbeat** sends positions every 5 s when the pilot is
  stationary; debug mode sends at 1 Hz regardless of GPS movement (#127,
  #129).
- **Meshtastic card** restored on the mobile home screen after being
  removed during Watch Live cleanup (#130).
- **Mobile nav bar insets** applied across every screen so the Android
  gesture bar no longer clips content (#125, v0.2.7).
- **Google sign-in** stability: race conditions, FedCM popup flow, error
  callbacks, and the silent-failure path on login (#88, #90, #92, #93,
  #94, #95, #104).
- **Login UX**: longer timeout, friendly errors, password show/hide
  toggle, network pre-check (#106, #113).
- **Marketing nav** button overlap on mobile, GitHub button made icon-only,
  and hero framing broadened beyond competition-only (#109, #117, #121,
  #122).
- **CSS styling audit**: design-token consolidation, table density,
  critical contrast fixes across the dashboard (#116).
- **Admin Sites database** renamed to "Flying Sites" and event dropdown
  now sorts by date (#111).
- **Mobile API default** pointed at staging so distributed APKs work
  out-of-the-box (#108).
- **PostgreSQL** runtime-schema crash on staging (boolean defaults,
  missing `visibility` column) (#89, #96).
- **Live view center button** position and behaviour (#115).
- **Scoring map** remounts on task switch so bounds refit correctly (#80).

### Changed
- **GAP2021+ scoring**: `leading_weight_factor` now drives non-distance
  weight allocation, matching FAI/AirScore reference (#100, #102, #105).
- **Scoring results** compacted with rank badges and blue IGC buttons;
  status badges, denser overall table, and centered task columns (#82,
  #83).
- **Logo** now replaces the warning triangle on `/app` (#110).
- **Dashboard** design-audit polish: touch targets, empty states (#99).

### Audits
- **FAI competition scoring audit** across 8 reference events (#98).

## [2026.04.02 – 2026.04.03]

### Added
- **Logbook v1** promoted to production: LC computation, audit report
  update, site flight-count rescan (#59, #63, #65).

### Changed
- **Deploy queue** + webhook promotion to production (#43, #56).

## History

For detailed release history see the [git log](https://github.com/cwallen93117/scoring-software-codex/commits/main)
and the [Pull Requests](https://github.com/cwallen93117/scoring-software-codex/pulls?q=is%3Apr+is%3Amerged+base%3Amain) list.

## Keeping This File Current

See [`docs/release-notes-workflow.md`](docs/release-notes-workflow.md) for
the process. In short: after each staging → main promotion, add/update the
`[YYYY.MM.DD]` section for the promotion date, then cut a matching GitHub
Release with the same notes.
