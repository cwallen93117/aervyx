# Aervyx Mobile

Flutter companion app for pilots and drivers. Authenticates against the Aervyx
backend, displays task maps, tracks GPS position in real time, records flights
as IGC files, and pairs with Meshtastic BLE radios for off-grid mesh tracking.

> **Status (2026-04-02):** Substantial implementation exists across all screens and services. End-to-end field validation with physical Meshtastic hardware is still incomplete.

## Setup

Flutter 3.22+ and Dart 3.4+ are required.

```bash
# Install dependencies
flutter pub get

# Run on a connected device / emulator
flutter run

# Override the backend URL (e.g. for a local network host)
flutter run --dart-define=API_BASE_URL=http://192.168.1.50:8000

# Build release APK
flutter build apk --release
```

## Release Rule

Every Android/mobile app change must complete the full release path before it is reported done:

- Bump `mobile/pubspec.yaml` version/build.
- Add user-facing notes to both root `CHANGELOG.md` and `mobile/CHANGELOG.md`.
- Build the release APK.
- Confirm `lib/config/api_config.dart` and any related API/download endpoints are correct for the release.
- Upload the APK and release notes to the website app download endpoint.
- Verify the website app download page shows the new version and notes.

## Project Structure

```
lib/
  main.dart                    Entry point, provider setup
  app.dart                     MaterialApp with auth gating
  config/
    api_config.dart            Backend URL and endpoint paths
  models/
    user.dart                  User / AuthToken
    position.dart              Live position
    task.dart                  Event / Task / TaskPoint
    mesh_config.dart           Meshtastic mesh configuration
  services/
    api_service.dart           HTTP + SSE client with JWT auth
    auth_service.dart          Login, register, token persistence
    tracking_service.dart      GPS capture + position upload + SSE consumer
    ble_service.dart           Meshtastic BLE scan, pair, config push
    background_service.dart    Background GPS tracking when app is minimized
    driver_service.dart        Driver mode: retrieve pilot location for pickup
    igc_service.dart           IGC flight log generation and export
  screens/
    login_screen.dart          Email / password login
    register_screen.dart       New account registration
    home_screen.dart           Main navigation hub after login
    flights_screen.dart        Flight history list with IGC downloads
    flight_detail_screen.dart  Single flight detail view with map and stats
    live_view_screen.dart      Live map showing tracked pilots in real time
    settings_screen.dart       User preferences (units, aircraft icon, etc.)
    driver_home_screen.dart    Driver mode: pilot pickup assistance
    ble_pairing_screen.dart    Meshtastic device scan and config push
    meshtastic_settings_screen.dart  Meshtastic radio configuration
  widgets/
    tracking_controls.dart     Start/stop tracking panel with status readout
```

## Key Dependencies

- `flutter_map` + `latlong2` — OpenStreetMap tile map
- `geolocator` — high-accuracy GPS with distance filter
- `flutter_blue_plus` — BLE scanning and GATT operations
- `flutter_secure_storage` — encrypted JWT token persistence
- `provider` — state management
- `http` — REST and SSE networking
