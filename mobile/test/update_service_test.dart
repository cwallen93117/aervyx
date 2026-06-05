import 'package:aervyx_mobile/services/update_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  AppReleaseInfo release({
    required String serverVersion,
    required int serverCode,
    required String currentVersion,
    required int currentCode,
  }) {
    return AppReleaseInfo.fromJson(
      {
        'version': serverVersion,
        'version_code': serverCode,
        'download_url': 'https://api.aervyx.net/api/app/download',
        'release_notes': '',
        'release_date': '2026-06-05T00:00:00Z',
        'min_supported_version': '0.1.0',
      },
      currentVersion: currentVersion,
      currentVersionCode: currentCode,
    );
  }

  test('does not prompt when visible app version matches server version', () {
    final info = release(
      serverVersion: '0.4.54',
      serverCode: 71,
      currentVersion: '0.4.54',
      currentCode: 0,
    );

    expect(info.isNewerThanCurrent, isFalse);
  });

  test('ignores leading v when comparing visible versions', () {
    final info = release(
      serverVersion: '0.4.55',
      serverCode: 72,
      currentVersion: 'v0.4.55',
      currentCode: 0,
    );

    expect(info.isNewerThanCurrent, isFalse);
  });

  test('prompts only when server version and build are both newer', () {
    expect(
      release(
        serverVersion: '0.4.55',
        serverCode: 72,
        currentVersion: '0.4.54',
        currentCode: 71,
      ).isNewerThanCurrent,
      isTrue,
    );
    expect(
      release(
        serverVersion: '0.4.53',
        serverCode: 70,
        currentVersion: '0.4.54',
        currentCode: 71,
      ).isNewerThanCurrent,
      isFalse,
    );
  });
}
