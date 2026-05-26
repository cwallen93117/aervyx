import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/auth_service.dart';
import 'package:aervyx_mobile/widgets/live_map_style.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _userJson({
  String profileType = 'pilot',
  String profileTypeUpdatedAt = '2026-05-24T12:00:00Z',
}) =>
    {
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

  test('refresh flushes pending profile change before server refresh',
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
  });

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
