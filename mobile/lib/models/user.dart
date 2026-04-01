class User {
  final int id;
  final String username;
  final String fullName;
  final String role;
  final String profileType;
  final int? pilotId;

  // Unit preferences — synced from backend
  final String altitudeUnit; // 'm' or 'ft'
  final String speedUnit; // 'kph', 'mph', 'kts'
  final String distanceUnit; // 'km' or 'mi'
  final String varioUnit; // 'ms' or 'fpm'

  const User({
    required this.id,
    required this.username,
    required this.fullName,
    required this.role,
    required this.profileType,
    this.pilotId,
    this.altitudeUnit = 'ft',
    this.speedUnit = 'kph',
    this.distanceUnit = 'km',
    this.varioUnit = 'fpm',
  });

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as int,
        username: json['username'] as String,
        fullName: json['full_name'] as String,
        role: json['role'] as String,
        profileType: json['profile_type'] as String,
        pilotId: json['pilot_id'] as int?,
        altitudeUnit: json['altitude_unit'] as String? ?? 'ft',
        speedUnit: json['speed_unit'] as String? ?? 'kph',
        distanceUnit: json['distance_unit'] as String? ?? 'km',
        varioUnit: json['vario_unit'] as String? ?? 'fpm',
      );

  /// Serialize to JSON for local caching.
  Map<String, dynamic> toJson() => {
        'id': id,
        'username': username,
        'full_name': fullName,
        'role': role,
        'profile_type': profileType,
        if (pilotId != null) 'pilot_id': pilotId,
        'altitude_unit': altitudeUnit,
        'speed_unit': speedUnit,
        'distance_unit': distanceUnit,
        'vario_unit': varioUnit,
      };

  /// Create a copy with updated unit preferences.
  User copyWith({
    String? altitudeUnit,
    String? speedUnit,
    String? distanceUnit,
    String? varioUnit,
  }) =>
      User(
        id: id,
        username: username,
        fullName: fullName,
        role: role,
        profileType: profileType,
        pilotId: pilotId,
        altitudeUnit: altitudeUnit ?? this.altitudeUnit,
        speedUnit: speedUnit ?? this.speedUnit,
        distanceUnit: distanceUnit ?? this.distanceUnit,
        varioUnit: varioUnit ?? this.varioUnit,
      );
}

class AuthToken {
  final String accessToken;
  final User user;

  const AuthToken({required this.accessToken, required this.user});

  factory AuthToken.fromJson(Map<String, dynamic> json) => AuthToken(
        accessToken: json['access_token'] as String,
        user: User.fromJson(json['user'] as Map<String, dynamic>),
      );
}
