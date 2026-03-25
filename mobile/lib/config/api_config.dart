/// Central API configuration for the Aervyx mobile app.
class ApiConfig {
  /// Base URL of the Aervyx backend (no trailing slash).
  ///
  /// Override at startup via environment or build flag:
  ///   flutter run --dart-define=API_BASE_URL=http://192.168.1.50:8000
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000', // Android emulator → host
  );

  // Auth
  static const String loginPath = '/api/auth/login';
  static const String registerPath = '/api/auth/register';
  static const String mePath = '/api/auth/me';

  // Events & tasks
  static const String eventsPath = '/api/events';
  static String tasksPath(int eventId) => '/api/events/$eventId/tasks';

  // Tracking
  static const String trackPositionPath = '/api/track/position';
  static String livePositionsPath(int taskId) => '/api/track/live/$taskId';
  static String positionsHistoryPath(int taskId) =>
      '/api/track/positions/$taskId';
  static const String meshConfigPath = '/api/config/mesh';
}
