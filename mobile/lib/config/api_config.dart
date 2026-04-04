/// Central API configuration for the Aervyx mobile app.
///
/// On a real phone, set the backend URL at build time:
///   flutter build apk --dart-define=API_BASE_URL=http://192.168.87.56:8000
///
/// On the Android emulator, the default 10.0.2.2 routes to host localhost.
class ApiConfig {
  /// Base URL of the Aervyx backend (no trailing slash).
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000', // Android emulator → host
  );

  // Auth
  static const String loginPath = '/api/auth/login';
  static const String registerPath = '/api/auth/register';
  static const String mePath = '/api/auth/me';
  static const String googleAuthPath = '/api/auth/google';
  static const String googleClientIdPath = '/api/auth/google-client-id';

  // Tracking — no task ID needed; backend resolves event from pilot identity
  static const String trackPositionPath = '/api/track/position';

  // Active pilots — latest position for all currently flying pilots
  static const String activePilotsPath = '/api/track/active-pilots';

  // Active task — returns turnpoints if pilot is in an active competition task
  static const String activeTaskPath = '/api/track/active-task';

  // Meshtastic mesh configuration
  static const String meshConfigPath = '/api/config/mesh';

  // SOS — sent over cellular to the backend
  static const String sosPath = '/api/sos';

  // Flight detection settings — admin-configurable takeoff/landing thresholds
  static const String flightDetectionConfigPath = '/api/config/flight-detection';

  // IGC upload — task upload (also syncs to logbook automatically)
  static String taskUploadPath(int taskId) => '/api/tasks/$taskId/uploads';

  // IGC upload — logbook-only upload for free flights
  static const String logbookUploadPath = '/api/logbook/flights/upload';

  // Driver — assigned pilot list for a task
  static String driverAssignedPilotsPath(int taskId) =>
      '/api/driver/assigned-pilots/$taskId';
}
