import 'package:flutter/material.dart';

const List<Color> liveTrackColors = [
  Color(0xFF2563EB),
  Color(0xFFDC2626),
  Color(0xFF16A34A),
  Color(0xFF7C3AED),
  Color(0xFFD97706),
  Color(0xFF0891B2),
  Color(0xFFDB2777),
  Color(0xFF65A30D),
  Color(0xFF0F766E),
  Color(0xFFC2410C),
];

String liveShortName(String name) {
  final normalized = name.trim().replaceAll(RegExp(r'\s+'), ' ');
  if (normalized.isEmpty) return 'Tracker';
  final parts = normalized.split(' ');
  if (parts.length == 1) return parts.first;
  final first = parts.first;
  final lastInitial = parts.last.isNotEmpty ? parts.last[0].toUpperCase() : '';
  return lastInitial.isEmpty ? first : '$first $lastInitial.';
}

Color liveColorForSubject(String subjectKey, Iterable<String> orderedKeys) {
  final keys = orderedKeys.toList();
  final index = keys.indexOf(subjectKey);
  return liveTrackColors[(index < 0 ? 0 : index) % liveTrackColors.length];
}

String liveRelativeTime(DateTime value, {DateTime? now}) {
  final age = (now ?? DateTime.now()).difference(value.toLocal());
  if (age.inSeconds < 10) return 'just now';
  if (age.inSeconds < 60) return '${age.inSeconds}s ago';
  if (age.inMinutes < 60) return '${age.inMinutes}m ago';
  return '${age.inHours}h ago';
}

bool isLivePositionStale(DateTime value, {DateTime? now}) {
  return (now ?? DateTime.now()).difference(value.toLocal()).inMinutes >= 5;
}

Uri liveDirectionsGeoUri(double lat, double lon, {String? label}) {
  final encoded = Uri.encodeComponent(
      label?.trim().isNotEmpty == true ? label!.trim() : 'Destination');
  return Uri.parse('geo:$lat,$lon?q=$lat,$lon($encoded)');
}

Uri liveDirectionsWebUri(double lat, double lon) {
  return Uri.https(
      'www.google.com', '/maps/search/', {'api': '1', 'query': '$lat,$lon'});
}

class LiveSubjectMarker extends StatelessWidget {
  final String name;
  final String subjectKey;
  final Iterable<String> orderedSubjectKeys;
  final String? aircraftIcon;
  final String profileType;
  final DateTime lastSeen;
  final double glyphSize;

  const LiveSubjectMarker({
    super.key,
    required this.name,
    required this.subjectKey,
    required this.orderedSubjectKeys,
    required this.profileType,
    required this.lastSeen,
    this.aircraftIcon,
    this.glyphSize = 22,
  });

  @override
  Widget build(BuildContext context) {
    final color = liveColorForSubject(subjectKey, orderedSubjectKeys);
    final stale = isLivePositionStale(lastSeen);
    final markerColor = stale ? color.withAlpha(135) : color;
    final labelColor = stale ? Colors.black54 : Colors.black87;
    return Opacity(
      opacity: stale ? 0.72 : 1,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(5),
            decoration: BoxDecoration(
              color: Colors.white,
              shape: BoxShape.circle,
              border: Border.all(color: markerColor, width: 2),
              boxShadow: [
                BoxShadow(color: Colors.black.withAlpha(40), blurRadius: 3),
              ],
            ),
            child: LiveRoleGlyph(
              profileType: profileType,
              aircraftIcon: aircraftIcon,
              color: markerColor,
              size: glyphSize,
            ),
          ),
          Container(
            constraints: const BoxConstraints(maxWidth: 82),
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
            decoration: BoxDecoration(
              color: Colors.white.withAlpha(stale ? 185 : 220),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              liveShortName(name),
              style: TextStyle(
                fontSize: 9,
                fontWeight: FontWeight.bold,
                color: labelColor,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class LiveRoleGlyph extends StatelessWidget {
  final String profileType;
  final String? aircraftIcon;
  final Color color;
  final double size;

  const LiveRoleGlyph({
    super.key,
    required this.profileType,
    required this.color,
    this.aircraftIcon,
    this.size = 20,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size.square(size),
      painter: _LiveRoleGlyphPainter(
        profileType: profileType,
        aircraftIcon: aircraftIcon,
        color: color,
      ),
    );
  }
}

class _LiveRoleGlyphPainter extends CustomPainter {
  final String profileType;
  final String? aircraftIcon;
  final Color color;

  const _LiveRoleGlyphPainter({
    required this.profileType,
    required this.aircraftIcon,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    final scaleX = size.width / 24;
    final scaleY = size.height / 24;
    canvas.save();
    canvas.scale(scaleX, scaleY);
    canvas.drawPath(_pathForRole(), paint);
    canvas.restore();
  }

  Path _pathForRole() {
    if (profileType == 'driver') return _driverPath();
    if (profileType == 'stationary_node') return _stationaryNodePath();
    switch (aircraftIcon) {
      case 'paraglider':
        return _paragliderPath();
      case 'sailplane':
        return _sailplanePath();
      case 'hang_glider':
      default:
        return _hangGliderPath();
    }
  }

  Path _hangGliderPath() {
    return Path()
      ..moveTo(12, 4)
      ..lineTo(22, 20)
      ..lineTo(12, 16)
      ..lineTo(2, 20)
      ..close();
  }

  Path _paragliderPath() {
    return Path()
      ..moveTo(2, 12)
      ..quadraticBezierTo(12, 4, 22, 12)
      ..lineTo(20, 13)
      ..quadraticBezierTo(12, 6, 4, 13)
      ..close()
      ..addRect(const Rect.fromLTWH(11, 15, 2, 5));
  }

  Path _sailplanePath() {
    return Path()
      ..moveTo(2, 11)
      ..lineTo(11, 11)
      ..lineTo(11, 3)
      ..lineTo(13, 3)
      ..lineTo(13, 11)
      ..lineTo(22, 11)
      ..lineTo(22, 13)
      ..lineTo(13, 13)
      ..lineTo(13, 18)
      ..lineTo(16, 18)
      ..lineTo(16, 20)
      ..lineTo(8, 20)
      ..lineTo(8, 18)
      ..lineTo(11, 18)
      ..lineTo(11, 13)
      ..lineTo(2, 13)
      ..close();
  }

  Path _driverPath() {
    return Path()
      ..moveTo(5, 11)
      ..lineTo(6.5, 6.5)
      ..quadraticBezierTo(7, 5, 8.4, 5)
      ..lineTo(15.6, 5)
      ..quadraticBezierTo(17, 5, 17.5, 6.5)
      ..lineTo(19, 11)
      ..lineTo(20, 11)
      ..quadraticBezierTo(21, 11, 21, 12)
      ..lineTo(21, 16)
      ..quadraticBezierTo(21, 17, 20, 17)
      ..lineTo(19, 17)
      ..lineTo(19, 18)
      ..quadraticBezierTo(19, 19, 18, 19)
      ..lineTo(17, 19)
      ..quadraticBezierTo(16, 19, 16, 18)
      ..lineTo(16, 17)
      ..lineTo(8, 17)
      ..lineTo(8, 18)
      ..quadraticBezierTo(8, 19, 7, 19)
      ..lineTo(6, 19)
      ..quadraticBezierTo(5, 19, 5, 18)
      ..lineTo(5, 17)
      ..lineTo(4, 17)
      ..quadraticBezierTo(3, 17, 3, 16)
      ..lineTo(3, 12)
      ..quadraticBezierTo(3, 11, 4, 11)
      ..close()
      ..addOval(Rect.fromCircle(center: const Offset(7, 14), radius: 1.25))
      ..addOval(Rect.fromCircle(center: const Offset(17, 14), radius: 1.25));
  }

  Path _stationaryNodePath() {
    return Path()
      ..moveTo(12, 2)
      ..lineTo(16, 8)
      ..lineTo(12, 10)
      ..lineTo(8, 8)
      ..close()
      ..addRect(const Rect.fromLTWH(11, 10, 2, 12))
      ..moveTo(5.5, 4.2)
      ..lineTo(6.9, 5.6)
      ..quadraticBezierTo(3.5, 10.6, 6.9, 15.5)
      ..lineTo(5.5, 16.9)
      ..quadraticBezierTo(1, 10.6, 5.5, 4.2)
      ..moveTo(18.5, 4.2)
      ..quadraticBezierTo(23, 10.6, 18.5, 16.9)
      ..lineTo(17.1, 15.5)
      ..quadraticBezierTo(20.5, 10.6, 17.1, 5.6)
      ..close();
  }

  @override
  bool shouldRepaint(covariant _LiveRoleGlyphPainter oldDelegate) {
    return oldDelegate.profileType != profileType ||
        oldDelegate.aircraftIcon != aircraftIcon ||
        oldDelegate.color != color;
  }
}
