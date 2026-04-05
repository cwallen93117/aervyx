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
