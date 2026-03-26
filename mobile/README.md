# Aervyx Mobile

Flutter companion app for pilots. Authenticates against the existing Aervyx
backend, displays task maps, tracks GPS position in real time, and pairs with
Meshtastic BLE radios.

## Setup

Flutter 3.22+ and Dart 3.4+ are required.

```bash
# Generate platform directories (run once)
flutter create --platforms android,ios --org com.aervyx .

# Install dependencies
flutter pub get

# Run on a connected device / emulator
flutter run

# Override the backend URL (e.g. for a local network host)
flutter run --dart-define=API_BASE_URL=http://192.168.1.50:8000
```

## Project Structure

```
lib/
  main.dart               Entry point, provider setup
  app.dart                MaterialApp with auth gating
  config/
    api_config.dart       Backend URL and endpoint paths
  models/
    user.dart             User / AuthToken
    position.dart         Live position
    task.dart             Event / Task / TaskPoint
    mesh_config.dart      Meshtastic mesh configuration
  services/
    api_service.dart      HTTP + SSE client with JWT auth
    auth_service.dart     Login, register, token persistence
    tracking_service.dart GPS capture + position upload + SSE consumer
    ble_service.dart      Meshtastic BLE scan, pair, config push
  screens/
    login_screen.dart     Email / password login
    task_list_screen.dart Event and task browser
    task_map_screen.dart  flutter_map with task waypoints + live pilots
    ble_pairing_screen.dart  Meshtastic device scan and config push
  widgets/
    tracking_controls.dart  Start/stop tracking panel with status readout
```

## Key Dependencies

- `flutter_map` + `latlong2` — OpenStreetMap tile map
- `geolocator` — high-accuracy GPS with distance filter
- `flutter_blue_plus` — BLE scanning and GATT operations
- `flutter_secure_storage` — encrypted JWT token persistence
- `provider` — state management
- `http` — REST and SSE networking
