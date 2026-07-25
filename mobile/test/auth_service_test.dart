import 'dart:convert';
import 'dart:io';

import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/models/user.dart';
import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/auth_service.dart';
import 'package:aervyx_mobile/widgets/live_map_style.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:passkeys/authenticator.dart';
import 'package:passkeys/types.dart';

Map<String, dynamic> _userJson({
  String profileType = 'pilot',
  String profileTypeUpdatedAt = '2026-05-24T12:00:00Z',
}) => {
  'id': 7,
  'username': 'pilot@example.com',
  'full_name': 'Pilot User',
  'role': 'pilot',
  'profile_type': profileType,
  'profile_type_updated_at': profileTypeUpdatedAt,
  'pilot_id': 3,
  'altitude_unit': 'ft',
  'speed_unit': 'kph',
  'distance_unit': 'km',
  'vario_unit': 'fpm',
};

class _FakeAuthApiService extends ApiService {
  Object? patchError;
  Map<String, dynamic>? lastPatchBody;
  Map<String, dynamic> meResponse = _userJson();
  Map<String, dynamic> Function(Map<String, dynamic>? body)? patchHandler;

  @override
  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    expect(path, ApiConfig.loginPath);
    return {
      'access_token': 'token',
      'refresh_token': 'refresh-token',
      'user': _userJson(),
    };
  }

  @override
  Future<Map<String, dynamic>> patch(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    expect(path, ApiConfig.preferencesPath);
    lastPatchBody = body;
    if (patchError != null) throw patchError!;
    return patchHandler?.call(body) ?? meResponse;
  }

  @override
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String>? query,
  }) async {
    expect(path, ApiConfig.mePath);
    return meResponse;
  }
}

class _FakePasskeyAuthenticator extends PasskeyAuthenticator {
  AuthenticateRequestType? request;

  @override
  Future<AuthenticateResponseType> authenticate(
    AuthenticateRequestType request,
  ) async {
    this.request = request;
    return const AuthenticateResponseType(
      id: 'credential-id',
      rawId: 'credential-id',
      clientDataJSON: 'client-data',
      authenticatorData: 'authenticator-data',
      signature: 'signature',
      userHandle: 'user-handle',
    );
  }
}

class _FakePasskeyApiService extends ApiService {
  Map<String, dynamic>? verifyBody;

  @override
  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    if (path == ApiConfig.passkeyLoginOptionsPath) {
      return {
        'ceremony_id': 'ceremony',
        'public_key': {
          'rpId': 'staging.aervyx.net',
          'challenge': 'Y2hhbGxlbmdl',
          'userVerification': 'required',
        },
      };
    }
    expect(path, ApiConfig.passkeyLoginVerifyPath);
    verifyBody = body;
    return {
      'access_token': 'passkey-token',
      'refresh_token': 'passkey-refresh',
      'user': _userJson(),
    };
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('offline profile toggle keeps local state and pending sync', () async {
    final api = _FakeAuthApiService();
    final auth = AuthService(api);

    await auth.login('pilot@example.com', 'password');
    api.patchError = Exception('offline');

    await auth.updateProfileType('driver');

    expect(auth.user?.profileType, 'driver');
    expect(auth.profileTypeSyncPending, isTrue);
    expect(api.lastPatchBody?['profile_type'], 'driver');
    expect(api.lastPatchBody?['profile_type_updated_at'], isA<String>());
  });

  test('login stores access and refresh tokens', () async {
    final api = _FakeAuthApiService();
    final auth = AuthService(api);

    await auth.login('pilot@example.com', 'password');

    const storage = FlutterSecureStorage();
    expect(await storage.read(key: 'access_token'), 'token');
    expect(await storage.read(key: 'refresh_token'), 'refresh-token');
  });

  test(
    'passkey login sends WebAuthn JSON and stores existing JWT response',
    () async {
      final api = _FakePasskeyApiService();
      final passkeys = _FakePasskeyAuthenticator();
      final auth = AuthService(api, passkeys: passkeys);

      await auth.loginWithPasskey(preferImmediatelyAvailableCredentials: true);

      expect(passkeys.request?.relyingPartyId, 'staging.aervyx.net');
      expect(passkeys.request?.preferImmediatelyAvailableCredentials, isTrue);
      expect(api.verifyBody?['ceremony_id'], 'ceremony');
      expect(
        (api.verifyBody?['credential'] as Map<String, dynamic>)['id'],
        'credential-id',
      );
      const storage = FlutterSecureStorage();
      expect(await storage.read(key: 'access_token'), 'passkey-token');
      expect(await storage.read(key: 'refresh_token'), 'passkey-refresh');
      expect(auth.user?.username, 'pilot@example.com');
    },
  );

  test(
    'api refreshes and retries once after an unauthorized response',
    () async {
      var meCalls = 0;
      final api = ApiService(
        client: MockClient((request) async {
          if (request.url.path == ApiConfig.mePath) {
            meCalls++;
            if (request.headers['Authorization'] == 'Bearer old-token') {
              return http.Response('{"detail":"Invalid token"}', 401);
            }
            expect(request.headers['Authorization'], 'Bearer new-token');
            return http.Response(jsonEncode(_userJson()), 200);
          }
          return http.Response('not found', 404);
        }),
      );
      api.setToken('old-token');
      api.setAuthRefreshHandler(() async {
        api.setToken('new-token');
        return true;
      });

      final json = await api.get(ApiConfig.mePath);

      expect(User.fromJson(json).username, 'pilot@example.com');
      expect(meCalls, 2);
    },
  );

  test('restore refreshes expired access token and stays logged in', () async {
    const storage = FlutterSecureStorage();
    await storage.write(key: 'access_token', value: 'old-token');
    await storage.write(key: 'refresh_token', value: 'refresh-token');
    await storage.write(key: 'cached_user', value: jsonEncode(_userJson()));

    final api = ApiService(
      client: MockClient((request) async {
        if (request.url.path == ApiConfig.mePath) {
          if (request.headers['Authorization'] == 'Bearer old-token') {
            return http.Response('{"detail":"Invalid token"}', 401);
          }
          expect(request.headers['Authorization'], 'Bearer new-token');
          return http.Response(jsonEncode(_userJson()), 200);
        }
        if (request.url.path == ApiConfig.refreshPath) {
          expect(jsonDecode(request.body)['refresh_token'], 'refresh-token');
          return http.Response(
            jsonEncode({
              'access_token': 'new-token',
              'refresh_token': 'next-refresh-token',
              'user': _userJson(),
            }),
            200,
          );
        }
        return http.Response('not found', 404);
      }),
    );
    final auth = AuthService(api);

    await auth.tryRestoreSession();

    expect(auth.isLoggedIn, isTrue);
    expect(auth.token, 'new-token');
    expect(await storage.read(key: 'access_token'), 'new-token');
    expect(await storage.read(key: 'refresh_token'), 'next-refresh-token');
  });

  test('rejected refresh clears restored session', () async {
    const storage = FlutterSecureStorage();
    await storage.write(key: 'access_token', value: 'old-token');
    await storage.write(key: 'refresh_token', value: 'bad-refresh-token');
    await storage.write(key: 'cached_user', value: jsonEncode(_userJson()));

    final api = ApiService(
      client: MockClient((request) async {
        if (request.url.path == ApiConfig.mePath) {
          return http.Response('{"detail":"Invalid token"}', 401);
        }
        if (request.url.path == ApiConfig.refreshPath) {
          return http.Response(
            '{"detail":"Invalid or expired refresh token"}',
            401,
          );
        }
        return http.Response('not found', 404);
      }),
    );
    final auth = AuthService(api);

    await auth.tryRestoreSession();

    expect(auth.isLoggedIn, isFalse);
    expect(await storage.read(key: 'access_token'), isNull);
    expect(await storage.read(key: 'refresh_token'), isNull);
    expect(await storage.read(key: 'cached_user'), isNull);
  });

  test('offline restore keeps cached user and stored credentials', () async {
    const storage = FlutterSecureStorage();
    await storage.write(key: 'access_token', value: 'saved-token');
    await storage.write(key: 'refresh_token', value: 'refresh-token');
    await storage.write(key: 'cached_user', value: jsonEncode(_userJson()));

    final api = ApiService(
      client: MockClient((_) async => throw const SocketException('offline')),
    );
    final auth = AuthService(api);

    await auth.tryRestoreSession();

    expect(auth.isLoggedIn, isTrue);
    expect(auth.user?.username, 'pilot@example.com');
    expect(await storage.read(key: 'access_token'), 'saved-token');
    expect(await storage.read(key: 'refresh_token'), 'refresh-token');
  });

  test(
    'logout clears tokens, cached user, and pending profile state',
    () async {
      final api = _FakeAuthApiService();
      final auth = AuthService(api);

      await auth.login('pilot@example.com', 'password');
      api.patchError = Exception('offline');
      await auth.updateProfileType('driver');
      await auth.logout();

      const storage = FlutterSecureStorage();
      expect(auth.isLoggedIn, isFalse);
      expect(await storage.read(key: 'access_token'), isNull);
      expect(await storage.read(key: 'refresh_token'), isNull);
      expect(await storage.read(key: 'cached_user'), isNull);
      expect(await storage.read(key: 'pending_profile_type'), isNull);
    },
  );

  test(
    'refresh flushes pending profile change before server refresh',
    () async {
      final api = _FakeAuthApiService();
      final auth = AuthService(api);

      await auth.login('pilot@example.com', 'password');
      api.patchError = Exception('offline');
      await auth.updateProfileType('driver');

      api.patchError = null;
      api.patchHandler = (body) {
        final updatedAt = body!['profile_type_updated_at'] as String;
        api.meResponse = _userJson(
          profileType: 'driver',
          profileTypeUpdatedAt: updatedAt,
        );
        return api.meResponse;
      };

      await auth.refreshUserProfile();

      expect(auth.profileTypeSyncPending, isFalse);
      expect(auth.user?.profileType, 'driver');
    },
  );

  test('stale local profile change adopts newer server profile', () async {
    final api = _FakeAuthApiService();
    final auth = AuthService(api);

    await auth.login('pilot@example.com', 'password');
    api.patchHandler = (_) => _userJson(
      profileType: 'pilot',
      profileTypeUpdatedAt: '2030-01-01T00:00:00Z',
    );

    await auth.updateProfileType('driver');

    expect(auth.profileTypeSyncPending, isFalse);
    expect(auth.user?.profileType, 'pilot');
    expect(auth.user?.profileTypeUpdatedAt.year, 2030);
  });

  test('live map style dropdown options use map and satellite tiles', () {
    expect(LiveMapStyle.map.urlTemplate, contains('openstreetmap'));
    expect(LiveMapStyle.satellite.urlTemplate, contains('World_Imagery'));
  });
}
