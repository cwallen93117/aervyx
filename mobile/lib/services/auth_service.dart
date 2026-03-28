import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/api_config.dart';
import '../models/user.dart';
import 'api_service.dart';

/// Handles login, registration, token persistence, and session state.
class AuthService extends ChangeNotifier {
  final ApiService _api;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  User? _user;
  bool _loading = true;

  User? get user => _user;
  bool get isLoggedIn => _user != null;
  bool get loading => _loading;
  String? get token => _api.token;

  AuthService(this._api);

  /// Try to restore a saved session on app start.
  /// Uses a short timeout so the app never hangs on a white screen.
  Future<void> tryRestoreSession() async {
    _loading = true;
    notifyListeners();

    try {
      final savedToken = await _storage.read(key: 'access_token');
      if (savedToken != null) {
        _api.setToken(savedToken);
        try {
          final json = await _api
              .get(ApiConfig.mePath)
              .timeout(const Duration(seconds: 3));
          _user = User.fromJson(json);
        } catch (_) {
          // Token expired, invalid, or backend unreachable — clear it.
          await _storage.delete(key: 'access_token');
          _api.setToken(null);
        }
      }
    } catch (_) {
      // Secure storage or other init failure — proceed to login screen.
    }

    _loading = false;
    notifyListeners();
  }

  /// Log in with email and password.
  Future<void> login(String email, String password) async {
    final json = await _api.post(ApiConfig.loginPath, body: {
      'username': email.trim(),
      'password': password,
    });
    final auth = AuthToken.fromJson(json);
    _api.setToken(auth.accessToken);
    await _storage.write(key: 'access_token', value: auth.accessToken);
    _user = auth.user;
    notifyListeners();
  }

  /// Register a new pilot account.
  Future<void> register({
    required String firstName,
    required String lastName,
    required String email,
    required String password,
    String? nation,
    String? competitionNumber,
  }) async {
    final json = await _api.post(ApiConfig.registerPath, body: {
      'first_name': firstName.trim(),
      'last_name': lastName.trim(),
      'email': email.trim(),
      'password': password,
      'account_role': 'pilot',
      if (nation != null) 'nation': nation,
      if (competitionNumber != null) 'competition_number': competitionNumber,
    });
    final auth = AuthToken.fromJson(json);
    _api.setToken(auth.accessToken);
    await _storage.write(key: 'access_token', value: auth.accessToken);
    _user = auth.user;
    notifyListeners();
  }

  /// Enter BLE test mode — bypasses login with a local-only user.
  /// Tracking/backend features won't work, but BLE pairing will.
  void enterBleTestMode() {
    _user = const User(
      id: 0,
      username: 'ble-test',
      fullName: 'BLE Test Mode',
      role: 'pilot',
      profileType: 'pilot',
    );
    _loading = false;
    notifyListeners();
  }

  bool get isBleTestMode => _user?.username == 'ble-test';

  /// Log out and clear stored credentials.
  Future<void> logout() async {
    _api.setToken(null);
    _user = null;
    await _storage.delete(key: 'access_token');
    notifyListeners();
  }
}
