import 'dart:convert';

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
  /// When offline, restores from the cached user profile so the pilot
  /// can start tracking immediately without waiting for connectivity.
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
          // Cache the fresh profile for offline use
          await _storage.write(
              key: 'cached_user', value: jsonEncode(_user!.toJson()));
        } catch (_) {
          // Backend unreachable — try cached profile instead of clearing token.
          // The pilot may be at launch with no cell service.
          final cachedJson = await _storage.read(key: 'cached_user');
          if (cachedJson != null) {
            _user = User.fromJson(
                jsonDecode(cachedJson) as Map<String, dynamic>);
          } else {
            // No cached profile and no backend — clear token, force login
            await _storage.delete(key: 'access_token');
            _api.setToken(null);
          }
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
    }).timeout(const Duration(seconds: 15));
    final auth = AuthToken.fromJson(json);
    _api.setToken(auth.accessToken);
    await _storage.write(key: 'access_token', value: auth.accessToken);
    // Cache profile for offline restarts
    await _storage.write(
        key: 'cached_user', value: jsonEncode(auth.user.toJson()));
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

  /// Log in with a Google ID token (obtained from google_sign_in package).
  Future<void> loginWithGoogle(String idToken) async {
    final json = await _api.post(ApiConfig.googleAuthPath, body: {
      'credential': idToken,
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

  /// Update a unit preference locally and try to sync to backend.
  void updateUnit({
    String? altitudeUnit,
    String? speedUnit,
    String? distanceUnit,
    String? varioUnit,
  }) {
    if (_user == null) return;
    _user = _user!.copyWith(
      altitudeUnit: altitudeUnit,
      speedUnit: speedUnit,
      distanceUnit: distanceUnit,
      varioUnit: varioUnit,
    );
    notifyListeners();

    // Try to sync to backend (fire-and-forget)
    _syncUnitsToBackend();
  }

  Future<void> _syncUnitsToBackend() async {
    if (_user == null || isBleTestMode) return;
    try {
      await _api.patch('/api/auth/settings', body: {
        'altitude_unit': _user!.altitudeUnit,
        'speed_unit': _user!.speedUnit,
        'distance_unit': _user!.distanceUnit,
        'vario_unit': _user!.varioUnit,
      });
    } catch (_) {
      // Backend unreachable — local change is kept
    }
  }

  /// Log out and clear stored credentials.
  Future<void> logout() async {
    _api.setToken(null);
    _user = null;
    await _storage.delete(key: 'access_token');
    await _storage.delete(key: 'cached_user');
    notifyListeners();
  }
}
