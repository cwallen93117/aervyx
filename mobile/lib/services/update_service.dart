import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';

import '../config/api_config.dart';
import 'api_service.dart';

class AppReleaseInfo {
  final String version;
  final int versionCode;
  final String downloadUrl;
  final String releaseNotes;
  final String releaseDate;
  final String minSupportedVersion;
  final int? fileSizeBytes;
  final String currentVersion;
  final int currentVersionCode;

  const AppReleaseInfo({
    required this.version,
    required this.versionCode,
    required this.downloadUrl,
    required this.releaseNotes,
    required this.releaseDate,
    required this.minSupportedVersion,
    required this.currentVersion,
    required this.currentVersionCode,
    this.fileSizeBytes,
  });

  factory AppReleaseInfo.fromJson(
    Map<String, dynamic> json, {
    required String currentVersion,
    required int currentVersionCode,
  }) {
    return AppReleaseInfo(
      version: json['version'] as String? ?? '',
      versionCode: (json['version_code'] as num?)?.toInt() ?? 0,
      downloadUrl: json['download_url'] as String? ??
          '${ApiConfig.baseUrl}${ApiConfig.appDownloadPath}',
      releaseNotes: json['release_notes'] as String? ?? '',
      releaseDate: json['release_date'] as String? ?? '',
      minSupportedVersion: json['min_supported_version'] as String? ?? '',
      fileSizeBytes: (json['file_size_bytes'] as num?)?.toInt(),
      currentVersion: currentVersion,
      currentVersionCode: currentVersionCode,
    );
  }

  bool get isNewerThanCurrent {
    if (_normalizeVersion(version) == _normalizeVersion(currentVersion)) {
      return false;
    }
    return versionCode > currentVersionCode;
  }

  static String _normalizeVersion(String value) {
    final trimmed = value.trim();
    if (trimmed.startsWith('v') || trimmed.startsWith('V')) {
      return trimmed.substring(1).trim();
    }
    return trimmed;
  }
}

class UpdateInstallPermissionException implements Exception {
  const UpdateInstallPermissionException();
}

class UpdateService {
  static const MethodChannel _channel =
      MethodChannel('com.aervyx.aervyx_mobile/app_update');

  final ApiService _api;
  final http.Client _client;

  UpdateService(this._api, {http.Client? client})
      : _client = client ?? http.Client();

  Future<AppReleaseInfo?> checkForUpdate() async {
    final packageInfo = await PackageInfo.fromPlatform();
    final packageBuildNumber = int.tryParse(packageInfo.buildNumber) ?? 0;
    final nativeVersionCode = await _installedVersionCode();
    final currentVersionCode = nativeVersionCode != null
        ? [packageBuildNumber, nativeVersionCode]
            .reduce((a, b) => a > b ? a : b)
        : packageBuildNumber;
    final json = await _api
        .get(ApiConfig.appVersionPath)
        .timeout(const Duration(seconds: 10));
    final release = AppReleaseInfo.fromJson(
      json,
      currentVersion: packageInfo.version,
      currentVersionCode: currentVersionCode,
    );
    return release.isNewerThanCurrent ? release : null;
  }

  Future<void> downloadAndInstall(
    AppReleaseInfo release, {
    void Function(double progress)? onProgress,
  }) async {
    final uri = Uri.parse(release.downloadUrl);
    final request = http.Request('GET', uri);
    final response = await _client.send(request).timeout(
          const Duration(seconds: 20),
        );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(response.statusCode, 'APK download failed');
    }

    final directory = await getTemporaryDirectory();
    final file = File(
      '${directory.path}/aervyx-${release.version}+${release.versionCode}.apk',
    );
    final sink = file.openWrite();
    var received = 0;
    final responseLength = response.contentLength;
    final total = responseLength != null && responseLength > 0
        ? responseLength
        : release.fileSizeBytes;

    try {
      await for (final chunk in response.stream) {
        received += chunk.length;
        sink.add(chunk);
        if (total != null && total > 0) {
          onProgress?.call(received / total);
        }
      }
    } finally {
      await sink.close();
    }

    onProgress?.call(1);
    await installDownloadedApk(file.path);
  }

  static Future<void> installDownloadedApk(String path) async {
    try {
      await _channel.invokeMethod<bool>('installApk', {'path': path});
    } on PlatformException catch (e) {
      if (e.code == 'INSTALL_PERMISSION_REQUIRED') {
        throw const UpdateInstallPermissionException();
      }
      rethrow;
    }
  }

  static Future<void> openInstallPermissionSettings() async {
    await _channel.invokeMethod<bool>('openInstallPermissionSettings');
  }

  static Future<int?> _installedVersionCode() async {
    try {
      final value =
          await _channel.invokeMethod<Object?>('getInstalledVersionCode');
      if (value is int) return value;
      if (value is num) return value.toInt();
      if (value is String) return int.tryParse(value);
    } catch (_) {
      // package_info_plus remains the fallback on platforms without the channel.
    }
    return null;
  }
}
