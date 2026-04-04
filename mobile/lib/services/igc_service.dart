import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:intl/intl.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// A single trackpoint recorded during a flight.
class TrackPoint {
  final DateTime time;
  final double lat;
  final double lon;
  final double gpsAlt;
  final double? pressureAlt;
  final double? speed;
  final double? accuracy;

  const TrackPoint({
    required this.time,
    required this.lat,
    required this.lon,
    required this.gpsAlt,
    this.pressureAlt,
    this.speed,
    this.accuracy,
  });
}

/// Saved flight metadata for the flights list.
class SavedFlight {
  final String filename;
  final String filePath;
  final DateTime date;
  final Duration duration;
  final int trackPoints;
  final double? maxAltitude;
  final double? maxSpeed; // m/s

  const SavedFlight({
    required this.filename,
    required this.filePath,
    required this.date,
    required this.duration,
    required this.trackPoints,
    this.maxAltitude,
    this.maxSpeed,
  });
}

/// Service that records trackpoints during a flight, writes IGC files,
/// and manages saved flights on disk.
class IgcService extends ChangeNotifier {
  final List<TrackPoint> _currentTrack = [];
  List<SavedFlight> _savedFlights = [];
  DateTime? _flightStart;
  String _appVersion = '0.0.0';

  List<SavedFlight> get savedFlights => List.unmodifiable(_savedFlights);
  int get currentTrackPointCount => _currentTrack.length;

  IgcService() {
    _loadSavedFlights();
    PackageInfo.fromPlatform().then((info) => _appVersion = info.version);
  }

  /// Record a trackpoint during an active flight.
  void addTrackPoint(Position pos) {
    _flightStart ??= pos.timestamp;
    _currentTrack.add(TrackPoint(
      time: pos.timestamp.toUtc(),
      lat: pos.latitude,
      lon: pos.longitude,
      gpsAlt: pos.altitude,
      speed: pos.speed,
      accuracy: pos.accuracy,
    ));
  }

  /// Save the current flight as an IGC file. Called when tracking stops.
  /// Returns the file path, or null if there were too few points.
  /// [flightNumber] appends a suffix for multi-flight days (e.g., -2, -3).
  Future<String?> saveCurrentFlight({
    String? pilotName,
    int? flightNumber,
  }) async {
    if (_currentTrack.length < 2) {
      // Need at least 2 points for a valid track
      _currentTrack.clear();
      _flightStart = null;
      return null;
    }

    final dir = await _flightsDirectory();
    final startTime = _currentTrack.first.time;
    final dateFmt = DateFormat('yyyy-MM-dd');
    // Filename: FirstName-YYYY-MM-DD-#N.igc
    final firstName = (pilotName ?? 'Pilot').split(' ').first;
    final safeName = firstName
        .replaceAll(RegExp(r'[^\w\-]'), '');
    final flightNum = flightNumber ?? 1;
    final filename = '$safeName-${dateFmt.format(startTime)}-#$flightNum.igc';
    final file = File('${dir.path}/$filename');

    final igcContent = _buildIgcContent(
      pilotName: pilotName ?? 'Aervyx Pilot',
      startTime: startTime,
    );

    await file.writeAsString(igcContent);

    // Calculate flight stats
    double? maxAlt;
    double? maxSpeed;
    for (final tp in _currentTrack) {
      if (maxAlt == null || tp.gpsAlt > maxAlt) maxAlt = tp.gpsAlt;
      if (tp.speed != null && (maxSpeed == null || tp.speed! > maxSpeed)) {
        maxSpeed = tp.speed;
      }
    }

    final flight = SavedFlight(
      filename: filename,
      filePath: file.path,
      date: startTime,
      duration: _currentTrack.last.time.difference(startTime),
      trackPoints: _currentTrack.length,
      maxAltitude: maxAlt,
      maxSpeed: maxSpeed,
    );

    _savedFlights.insert(0, flight);
    _currentTrack.clear();
    _flightStart = null;
    notifyListeners();

    return file.path;
  }

  /// Parse all B-records from an IGC file on disk into TrackPoint objects.
  /// Used for displaying flight tracks on the map.
  static Future<List<TrackPoint>> parseFullTrack(String filePath) async {
    final file = File(filePath);
    if (!await file.exists()) return [];

    final lines = await file.readAsLines();
    DateTime? flightDate;
    final points = <TrackPoint>[];

    for (final line in lines) {
      // Parse date from H-record
      if (line.startsWith('HFDTE') && flightDate == null) {
        final dateStr = line.substring(5).replaceAll('DATE:', '');
        if (dateStr.length >= 6) {
          final dd = int.tryParse(dateStr.substring(0, 2)) ?? 1;
          final mm = int.tryParse(dateStr.substring(2, 4)) ?? 1;
          final yy = int.tryParse(dateStr.substring(4, 6)) ?? 0;
          final yyyy = yy > 80 ? 1900 + yy : 2000 + yy;
          flightDate = DateTime(yyyy, mm, dd);
        }
      }

      // Parse B-records: BHHMMSS DDMMmmmN DDDMMmmmE V PPPPP GGGGG
      if (line.startsWith('B') && line.length >= 35) {
        final hh = int.tryParse(line.substring(1, 3)) ?? 0;
        final mm = int.tryParse(line.substring(3, 5)) ?? 0;
        final ss = int.tryParse(line.substring(5, 7)) ?? 0;

        final lat = _parseIgcLat(line.substring(7, 15));
        final lon = _parseIgcLon(line.substring(15, 24));
        final gpsAlt = double.tryParse(line.substring(30, 35)) ?? 0;
        final pressAlt = double.tryParse(line.substring(25, 30));

        final time = DateTime(
          flightDate?.year ?? 2000,
          flightDate?.month ?? 1,
          flightDate?.day ?? 1,
          hh, mm, ss,
        );

        points.add(TrackPoint(
          time: time,
          lat: lat,
          lon: lon,
          gpsAlt: gpsAlt,
          pressureAlt: pressAlt,
        ));
      }
    }

    return points;
  }

  /// Parse IGC latitude format: DDMMmmmN/S → decimal degrees
  static double _parseIgcLat(String s) {
    if (s.length < 8) return 0;
    final deg = int.tryParse(s.substring(0, 2)) ?? 0;
    final min = int.tryParse(s.substring(2, 4)) ?? 0;
    final minFrac = int.tryParse(s.substring(4, 7)) ?? 0;
    final ns = s[7];
    final decimal = deg + (min + minFrac / 1000.0) / 60.0;
    return ns == 'S' ? -decimal : decimal;
  }

  /// Parse IGC longitude format: DDDMMmmmE/W → decimal degrees
  static double _parseIgcLon(String s) {
    if (s.length < 9) return 0;
    final deg = int.tryParse(s.substring(0, 3)) ?? 0;
    final min = int.tryParse(s.substring(3, 5)) ?? 0;
    final minFrac = int.tryParse(s.substring(5, 8)) ?? 0;
    final ew = s[8];
    final decimal = deg + (min + minFrac / 1000.0) / 60.0;
    return ew == 'W' ? -decimal : decimal;
  }

  /// Discard the current track without saving.
  void discardCurrentTrack() {
    _currentTrack.clear();
    _flightStart = null;
  }

  /// Delete a saved flight from disk.
  Future<void> deleteFlight(SavedFlight flight) async {
    final file = File(flight.filePath);
    if (await file.exists()) {
      await file.delete();
    }
    _savedFlights.remove(flight);
    notifyListeners();
  }

  /// Share an IGC file via the system share sheet.
  Future<void> shareFlight(SavedFlight flight) async {
    await Share.shareXFiles(
      [XFile(flight.filePath)],
      subject: flight.filename,
    );
  }

  /// Load previously saved flights from disk.
  Future<void> _loadSavedFlights() async {
    try {
      final dir = await _flightsDirectory();
      if (!await dir.exists()) return;

      final files = dir
          .listSync()
          .whereType<File>()
          .where((f) => f.path.endsWith('.igc'))
          .toList()
        ..sort((a, b) => b.path.compareTo(a.path)); // newest first

      _savedFlights = [];
      for (final file in files) {
        final parsed = _parseIgcSummary(file);
        if (parsed != null) _savedFlights.add(parsed);
      }
      notifyListeners();
    } catch (_) {
      // First run or no flights yet
    }
  }

  /// Reload from disk (pull-to-refresh).
  Future<void> refresh() async {
    await _loadSavedFlights();
  }

  /// Get the flights storage directory.
  /// Uses external storage so files are visible in the phone's file manager
  /// under Android/data/com.aervyx.aervyx_mobile/files/flights/
  /// Falls back to internal app storage if external isn't available.
  Future<Directory> _flightsDirectory() async {
    Directory? baseDir;
    try {
      baseDir = await getExternalStorageDirectory();
    } catch (_) {
      // External storage unavailable
    }
    baseDir ??= await getApplicationDocumentsDirectory();

    final flightsDir = Directory('${baseDir.path}/flights');
    if (!await flightsDir.exists()) {
      await flightsDir.create(recursive: true);
    }
    return flightsDir;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // IGC File Format
  // ═══════════════════════════════════════════════════════════════════════════

  /// Build a valid IGC file from the current track.
  String _buildIgcContent({
    required String pilotName,
    required DateTime startTime,
  }) {
    final buf = StringBuffer();
    final dateFmt = DateFormat('ddMMyy');

    // ── A-record: Flight Recorder ID ──
    buf.writeln('AXXAERVYX');

    // ── H-records: Header ──
    buf.writeln('HFDTE${dateFmt.format(startTime)}');
    buf.writeln('HFPLTPILOTINCHARGE:$pilotName');
    buf.writeln('HFGTYGLIDERTYPE:');
    buf.writeln('HFGIDGLIDERID:');
    buf.writeln('HFDTMGPSDATUM:WGS84');
    buf.writeln('HFGPSGPS:Smartphone');
    buf.writeln('HFFRSFIRMWAREVERSION:Aervyx $_appVersion');
    buf.writeln('HFRHWHARDWAREVERSION:Smartphone');
    buf.writeln('HFFTYFRTYPE:Aervyx Mobile');

    // ── B-records: Fix records ──
    for (final tp in _currentTrack) {
      buf.writeln(_bRecord(tp));
    }

    return buf.toString();
  }

  /// Format a single B-record (fix) per IGC spec.
  /// B HH MM SS DDMMmmmN DDDMMmmmE V PPPPP GGGGG
  String _bRecord(TrackPoint tp) {
    final t = tp.time;
    final hh = t.hour.toString().padLeft(2, '0');
    final mm = t.minute.toString().padLeft(2, '0');
    final ss = t.second.toString().padLeft(2, '0');

    final lat = _formatLat(tp.lat);
    final lon = _formatLon(tp.lon);

    // Pressure altitude (use 0 if unavailable)
    final pAlt = (tp.pressureAlt ?? 0).round().abs().toString().padLeft(5, '0');
    // GPS altitude
    final gAlt = tp.gpsAlt.round().abs().toString().padLeft(5, '0');

    // V = 'A' means 3D fix valid
    return 'B$hh$mm$ss${lat}${lon}A$pAlt$gAlt';
  }

  /// Format latitude as DDMMmmmN/S (IGC format).
  String _formatLat(double lat) {
    final ns = lat >= 0 ? 'N' : 'S';
    final absLat = lat.abs();
    final deg = absLat.floor();
    final minFloat = (absLat - deg) * 60;
    final minWhole = minFloat.floor();
    final minFrac = ((minFloat - minWhole) * 1000).round();

    return '${deg.toString().padLeft(2, '0')}'
        '${minWhole.toString().padLeft(2, '0')}'
        '${minFrac.toString().padLeft(3, '0')}'
        '$ns';
  }

  /// Format longitude as DDDMMmmmE/W (IGC format).
  String _formatLon(double lon) {
    final ew = lon >= 0 ? 'E' : 'W';
    final absLon = lon.abs();
    final deg = absLon.floor();
    final minFloat = (absLon - deg) * 60;
    final minWhole = minFloat.floor();
    final minFrac = ((minFloat - minWhole) * 1000).round();

    return '${deg.toString().padLeft(3, '0')}'
        '${minWhole.toString().padLeft(2, '0')}'
        '${minFrac.toString().padLeft(3, '0')}'
        '$ew';
  }

  /// Parse basic flight info from an existing IGC file on disk.
  SavedFlight? _parseIgcSummary(File file) {
    try {
      final lines = file.readAsLinesSync();
      final filename = file.path.split(Platform.pathSeparator).last;

      DateTime? firstTime;
      DateTime? lastTime;
      DateTime? flightDate;
      double? maxAlt;
      int bRecords = 0;

      for (final line in lines) {
        // Parse date from H-record
        if (line.startsWith('HFDTE') && flightDate == null) {
          final dateStr = line.substring(5).replaceAll('DATE:', '');
          if (dateStr.length >= 6) {
            final dd = int.tryParse(dateStr.substring(0, 2)) ?? 1;
            final mm = int.tryParse(dateStr.substring(2, 4)) ?? 1;
            final yy = int.tryParse(dateStr.substring(4, 6)) ?? 0;
            final yyyy = yy > 80 ? 1900 + yy : 2000 + yy;
            flightDate = DateTime(yyyy, mm, dd);
          }
        }

        // Parse B-records
        if (line.startsWith('B') && line.length >= 35) {
          bRecords++;
          final hh = int.tryParse(line.substring(1, 3)) ?? 0;
          final mm = int.tryParse(line.substring(3, 5)) ?? 0;
          final ss = int.tryParse(line.substring(5, 7)) ?? 0;
          final fixTime = DateTime(
            flightDate?.year ?? 2000,
            flightDate?.month ?? 1,
            flightDate?.day ?? 1,
            hh, mm, ss,
          );
          firstTime ??= fixTime;
          lastTime = fixTime;

          // GPS altitude is at position 30-35
          final gpsAlt = double.tryParse(line.substring(30, 35));
          if (gpsAlt != null && (maxAlt == null || gpsAlt > maxAlt)) {
            maxAlt = gpsAlt;
          }
        }
      }

      if (bRecords < 2) return null;

      return SavedFlight(
        filename: filename,
        filePath: file.path,
        date: flightDate ?? file.lastModifiedSync(),
        duration: (firstTime != null && lastTime != null)
            ? lastTime.difference(firstTime)
            : Duration.zero,
        trackPoints: bRecords,
        maxAltitude: maxAlt,
      );
    } catch (_) {
      return null;
    }
  }
}
