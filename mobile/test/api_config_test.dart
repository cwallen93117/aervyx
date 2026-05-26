import 'package:aervyx_mobile/config/api_config.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('app download page follows the configured API environment', () {
    expect(
      ApiConfig.appDownloadPageUrlForBaseUrl('https://api-staging.aervyx.net'),
      'https://staging.aervyx.net/app',
    );
    expect(
      ApiConfig.appDownloadPageUrlForBaseUrl('https://api.aervyx.net'),
      'https://aervyx.net/app',
    );
    expect(
      ApiConfig.appDownloadPageUrlForBaseUrl('http://192.168.1.10:8000/'),
      'http://192.168.1.10:8000/api/app/download',
    );
  });
}
