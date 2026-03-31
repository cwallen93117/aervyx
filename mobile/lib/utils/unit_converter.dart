/// Unit conversion and formatting utilities.
///
/// All internal values are metric (metres, m/s). These helpers
/// convert to the user's preferred display unit.
class UnitConverter {
  // ── Altitude ──

  static String formatAltitude(double? metres, String unit) {
    if (metres == null) return '--';
    switch (unit) {
      case 'ft':
        return '${(metres * 3.28084).toStringAsFixed(0)} ft';
      case 'm':
      default:
        return '${metres.toStringAsFixed(0)} m';
    }
  }

  static String altitudeUnitLabel(String unit) {
    switch (unit) {
      case 'ft':
        return 'Feet';
      case 'm':
      default:
        return 'Metres';
    }
  }

  // ── Speed ──

  static String formatSpeed(double? ms, String unit) {
    if (ms == null) return '--';
    switch (unit) {
      case 'mph':
        return '${(ms * 2.23694).toStringAsFixed(1)} mph';
      case 'kts':
        return '${(ms * 1.94384).toStringAsFixed(1)} kts';
      case 'kph':
      default:
        return '${(ms * 3.6).toStringAsFixed(1)} km/h';
    }
  }

  static String speedUnitLabel(String unit) {
    switch (unit) {
      case 'mph':
        return 'Miles/hour';
      case 'kts':
        return 'Knots';
      case 'kph':
      default:
        return 'km/hour';
    }
  }

  // ── Distance ──

  static String formatDistance(double? metres, String unit) {
    if (metres == null) return '--';
    switch (unit) {
      case 'mi':
        final miles = metres / 1609.344;
        if (miles < 0.1) return '${(metres * 3.28084).toStringAsFixed(0)} ft';
        return '${miles.toStringAsFixed(1)} mi';
      case 'km':
      default:
        if (metres < 1000) return '${metres.toStringAsFixed(0)} m';
        return '${(metres / 1000).toStringAsFixed(1)} km';
    }
  }

  static String distanceUnitLabel(String unit) {
    switch (unit) {
      case 'mi':
        return 'Miles';
      case 'km':
      default:
        return 'Kilometres';
    }
  }

  // ── Vario (vertical speed) ──

  static String formatVario(double? ms, String unit) {
    if (ms == null) return '--';
    switch (unit) {
      case 'fpm':
        return '${(ms * 196.85).toStringAsFixed(0)} fpm';
      case 'ms':
      default:
        return '${ms.toStringAsFixed(1)} m/s';
    }
  }

  static String varioUnitLabel(String unit) {
    switch (unit) {
      case 'fpm':
        return 'Feet/min';
      case 'ms':
      default:
        return 'Metres/sec';
    }
  }
}
