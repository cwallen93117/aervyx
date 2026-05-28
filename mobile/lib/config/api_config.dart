/// Central API configuration for the Aervyx mobile app.
///
/// The default points at the public production API so distributed APKs work
/// from the public download page. Developers can override for local or
/// staging work:
///   flutter build apk --dart-define=API_BASE_URL=http://10.0.2.2:8000
///   (Android emulator -> host localhost)
///   flutter build apk --dart-define=API_BASE_URL=http://192.168.87.56:8000
///   (physical phone on the LAN)
///   flutter build apk --dart-define=API_BASE_URL=https://api-staging.aervyx.net
///   (staging API)
class ApiConfig {
  /// Base URL of the Aervyx backend (no trailing slash).
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://api.aervyx.net',
  );

  static String appDownloadPageUrlForBaseUrl(String apiBaseUrl) {
    final trimmed = apiBaseUrl.replaceFirst(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(trimmed);

    switch (uri?.host) {
      case 'api-staging.aervyx.net':
        return 'https://staging.aervyx.net/app';
      case 'api.aervyx.net':
        return 'https://aervyx.net/app';
      default:
        return '$trimmed/api/app/download';
    }
  }

  static String get appDownloadPageUrl => appDownloadPageUrlForBaseUrl(baseUrl);

  // Auth
  static const String loginPath = '/api/auth/login';
  static const String registerPath = '/api/auth/register';
  static const String refreshPath = '/api/auth/refresh';
  static const String mePath = '/api/auth/me';
  static const String googleAuthPath = '/api/auth/google';
  static const String googleClientIdPath = '/api/auth/google-client-id';
  static const String preferencesPath = '/api/auth/preferences';
  static const String meshDeviceRegisterPath = '/api/auth/mesh-device';
  static const String meshDevicesPath = '/api/auth/mesh-devices';

  // Tracking — no task ID needed; backend resolves event from pilot identity
  static const String trackPositionPath = '/api/track/position';

  // Active pilots — latest position for all currently flying pilots
  static const String activePilotsPath = '/api/track/active-pilots';

  // Active task — returns turnpoints if pilot is in an active competition task
  static const String activeTaskPath = '/api/track/active-task';

  // Meshtastic mesh configuration
  static const String meshConfigPath = '/api/config/mesh';
  static const String meshProfilesPath = '/api/config/mesh-profiles';

  // SOS — sent over cellular to the backend
  static const String sosPath = '/api/sos';

  // Flight detection settings — admin-configurable takeoff/landing thresholds
  static const String flightDetectionConfigPath =
      '/api/config/flight-detection';

  // IGC upload — task upload (also syncs to logbook automatically)
  static String taskUploadPath(int taskId) => '/api/tasks/$taskId/uploads';

  // IGC upload — logbook-only upload for free flights
  static const String logbookUploadPath = '/api/logbook/flights/upload';

  // Driver — assigned pilot list for a task
  static String driverAssignedPilotsPath(int taskId) =>
      '/api/driver/assigned-pilots/$taskId';

  // Driver routing — optimized multi-stop pickup route
  static String driverRoutePath(int taskId) => '/api/driver/route/$taskId';

  // Driver position reporting
  static const String driverPositionPath = '/api/driver/position';

  // Driver landings — all pilot landings for a task
  static String driverLandingsPath(int taskId) =>
      '/api/driver/landings/$taskId';

  // Driver pickup — mark pilot as picked up
  static String driverPickupPath(int landingId) =>
      '/api/driver/pickup/$landingId';

  // Driver cancel pickup
  static String driverCancelPickupPath(int landingId) =>
      '/api/driver/cancel-pickup/$landingId';
}
