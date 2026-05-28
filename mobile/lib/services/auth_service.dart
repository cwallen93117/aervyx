import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/api_config.dart';
import '../models/user.dart';
import 'api_service.dart';

/// Handles login, registration, token persistence, and session state.
class AuthService extends ChangeNotifier {
  static const _tokenKey = 'access_token';
  static const _refreshTokenKey = 'refresh_token';
  static const _cachedUserKey = 'cached_user';
  static const _pendingProfileTypeKey = 'pending_profile_type';

  final ApiService _api;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  User? _user;
  bool _loading = true;
  bool _profileTypeSyncPending = false;
  Future<bool>? _refreshFuture;

  User? get user => _user;
  bool get isLoggedIn => _user != null;
  bool get loading => _loading;
  String? get token => _api.token;
  bool get profileTypeSyncPending => _profileTypeSyncPending;

  AuthService(this._api) {
    _api.setAuthRefreshHandler(refreshAccessToken);
  }

  Future<void> _cacheUser(User user) async {
    await _storage.write(key: _cachedUserKey, value: jsonEncode(user.toJson()));
  }

  Future<User?> _readCachedUser() async {
    try {
      final cachedJson = await _storage.read(key: _cachedUserKey);
      if (cachedJson == null) return null;
      return User.fromJson(jsonDecode(cachedJson) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  Future<_PendingProfileType?> _readPendingProfileType() async {
    try {
      final raw = await _storage.read(key: _pendingProfileTypeKey);
      if (raw == null) return null;
      final json = jsonDecode(raw) as Map<String, dynamic>;
      final profileType =
          (json['profile_type'] as String?)?.trim().toLowerCase();
      final updatedAtRaw = json['profile_type_updated_at'] as String?;
      final updatedAt =
          updatedAtRaw == null ? null : DateTime.tryParse(updatedAtRaw);
      if ((profileType != 'pilot' && profileType != 'driver') ||
          updatedAt == null) {
        await _storage.delete(key: _pendingProfileTypeKey);
        return null;
      }
      return _PendingProfileType(profileType!, updatedAt.toUtc());
    } catch (_) {
      await _storage.delete(key: _pendingProfileTypeKey);
      return null;
    }
  }

  Future<void> _writePendingProfileType(
    String profileType,
    DateTime updatedAt,
  ) async {
    await _storage.write(
      key: _pendingProfileTypeKey,
      value: jsonEncode({
        'profile_type': profileType,
        'profile_type_updated_at': updatedAt.toUtc().toIso8601String(),
      }),
    );
    _profileTypeSyncPending = true;
  }

  Future<void> _clearPendingProfileType() async {
    await _storage.delete(key: _pendingProfileTypeKey);
    _profileTypeSyncPending = false;
  }

  Future<void> _refreshPendingProfileFlag() async {
    _profileTypeSyncPending =
        await _storage.read(key: _pendingProfileTypeKey) != null;
  }

  Future<void> _storeAuthToken(AuthToken auth) async {
    _api.setToken(auth.accessToken);
    await _storage.write(key: _tokenKey, value: auth.accessToken);
    if (auth.refreshToken != null && auth.refreshToken!.isNotEmpty) {
      await _storage.write(key: _refreshTokenKey, value: auth.refreshToken);
    }
  }

  Future<void> _clearStoredSession({bool notify = true}) async {
    _api.setToken(null);
    _user = null;
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _refreshTokenKey);
    await _storage.delete(key: _cachedUserKey);
    await _clearPendingProfileType();
    if (notify) notifyListeners();
  }

  /// Exchange the persisted refresh token for a fresh access token.
  Future<bool> refreshAccessToken() {
    return _refreshFuture ??= _refreshAccessToken().whenComplete(() {
      _refreshFuture = null;
    });
  }

  Future<bool> _refreshAccessToken() async {
    final refreshToken = await _storage.read(key: _refreshTokenKey);
    if (refreshToken == null || refreshToken.isEmpty) {
      await _clearStoredSession();
      return false;
    }

    try {
      final json = await _api.post(
        ApiConfig.refreshPath,
        body: {'refresh_token': refreshToken},
      );
      final auth = AuthToken.fromJson(json);
      await _storeAuthToken(auth);
      _user = auth.user;
      await _cacheUser(auth.user);
      notifyListeners();
      return true;
    } on ApiException catch (e) {
      if (e.statusCode == 401 || e.statusCode == 403) {
        await _clearStoredSession();
      }
      return false;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _tryFlushPendingProfileType({
    bool notify = true,
    Duration? timeout,
  }) async {
    if (_user == null || isBleTestMode) return true;
    final pending = await _readPendingProfileType();
    if (pending == null) {
      final changed = _profileTypeSyncPending;
      _profileTypeSyncPending = false;
      if (changed && notify) notifyListeners();
      return true;
    }

    _profileTypeSyncPending = true;
    try {
      final request = _api.patch(ApiConfig.preferencesPath, body: {
        'profile_type': pending.profileType,
        'profile_type_updated_at': pending.updatedAt.toIso8601String(),
      });
      final json =
          timeout == null ? await request : await request.timeout(timeout);
      final serverUser = User.fromJson(json);

      await _clearPendingProfileType();
      _user = serverUser;
      await _cacheUser(serverUser);
      if (notify) notifyListeners();
      return true;
    } catch (_) {
      _profileTypeSyncPending = true;
      if (notify) notifyListeners();
      return false;
    }
  }

  /// Try to restore a saved session on app start.
  /// Uses a short timeout so the app never hangs on a white screen.
  /// When offline, restores from the cached user profile so the pilot
  /// can start tracking immediately without waiting for connectivity.
  Future<void> tryRestoreSession() async {
    _loading = true;
    notifyListeners();

    try {
      final savedToken = await _storage.read(key: _tokenKey);
      final savedRefreshToken = await _storage.read(key: _refreshTokenKey);
      final cachedUser = await _readCachedUser();
      if (savedToken != null || savedRefreshToken != null) {
        _api.setToken(savedToken);
        if (cachedUser != null) {
          _user = cachedUser;
        }
        if (savedToken == null && savedRefreshToken != null) {
          await refreshAccessToken();
        }
        await _refreshPendingProfileFlag();
        if (_profileTypeSyncPending && _user != null) {
          await _tryFlushPendingProfileType(
            notify: false,
            timeout: const Duration(seconds: 3),
          );
        }

        try {
          if (!_profileTypeSyncPending || _user == null) {
            final json = await _api
                .get(ApiConfig.mePath)
                .timeout(const Duration(seconds: 3));
            _user = User.fromJson(json);
            await _cacheUser(_user!);
          }
        } on ApiException catch (e) {
          if (e.statusCode == 401 || e.statusCode == 403) {
            await _clearStoredSession(notify: false);
          } else if (cachedUser != null) {
            _user = cachedUser;
          }
        } catch (_) {
          if (cachedUser != null) {
            _user = cachedUser;
          } else if (savedRefreshToken == null) {
            await _storage.delete(key: _tokenKey);
            _api.setToken(null);
          }
        }
      }
    } catch (_) {
      // Secure storage or other init failure: proceed to login screen.
    }

    _loading = false;
    notifyListeners();
  }

  /// Log in with email and password.
  Future<void> login(String email, String password) async {
    final json = await _api.post(ApiConfig.loginPath, body: {
      'username': email.trim(),
      'password': password,
    }).timeout(const Duration(seconds: 45));
    final auth = AuthToken.fromJson(json);
    await _storeAuthToken(auth);
    await _clearPendingProfileType();
    await _cacheUser(auth.user);
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
    await _storeAuthToken(auth);
    await _clearPendingProfileType();
    _user = auth.user;
    await _cacheUser(auth.user);
    notifyListeners();
  }

  /// Log in with a Google ID token (obtained from google_sign_in package).
  Future<void> loginWithGoogle(String idToken) async {
    final json = await _api.post(ApiConfig.googleAuthPath, body: {
      'credential': idToken,
    });
    final auth = AuthToken.fromJson(json);
    await _storeAuthToken(auth);
    await _clearPendingProfileType();
    _user = auth.user;
    await _cacheUser(auth.user);
    notifyListeners();
  }

  /// Enter BLE test mode: bypasses login with a local-only user.
  /// Tracking/backend features won't work, but BLE pairing will.
  void enterBleTestMode() {
    _user = User(
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
    unawaited(_cacheUser(_user!));
    notifyListeners();

    // Try to sync to backend (fire-and-forget)
    unawaited(_syncUnitsToBackend());
  }

  /// Refresh profile settings from the backend so website changes sync into
  /// the app while preserving offline tolerance.
  Future<void> refreshUserProfile() async {
    if (_user == null || isBleTestMode) return;
    final flushed = await _tryFlushPendingProfileType();
    if (!flushed) return;
    final json = await _api.get(ApiConfig.mePath);
    _user = User.fromJson(json);
    await _cacheUser(_user!);
    notifyListeners();
  }

  /// Update pilot/driver mode through the lightweight mobile preferences API.
  Future<void> updateProfileType(String profileType) async {
    if (_user == null || isBleTestMode) return;
    final normalized = profileType.trim().toLowerCase();
    if (normalized != 'pilot' && normalized != 'driver') {
      throw ArgumentError('profileType must be pilot or driver');
    }

    final updatedAt = DateTime.now().toUtc();
    _user = _user!.copyWith(
      profileType: normalized,
      profileTypeUpdatedAt: updatedAt,
    );
    await _writePendingProfileType(normalized, updatedAt);
    await _cacheUser(_user!);
    notifyListeners();

    await _tryFlushPendingProfileType(
      timeout: const Duration(seconds: 5),
    );
  }

  Future<void> _syncUnitsToBackend() async {
    if (_user == null || isBleTestMode) return;
    try {
      await _api.patch(ApiConfig.preferencesPath, body: {
        'altitude_unit': _user!.altitudeUnit,
        'speed_unit': _user!.speedUnit,
        'distance_unit': _user!.distanceUnit,
        'vario_unit': _user!.varioUnit,
      });
      await _cacheUser(_user!);
    } catch (_) {
      // Backend unreachable: local change is kept.
    }
  }

  /// Log out and clear stored credentials.
  Future<void> logout() async {
    await _clearStoredSession();
  }
}

class _PendingProfileType {
  final String profileType;
  final DateTime updatedAt;

  const _PendingProfileType(this.profileType, this.updatedAt);
}
