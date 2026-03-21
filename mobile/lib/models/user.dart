class User {
  final int id;
  final String username;
  final String fullName;
  final String role;
  final String profileType;
  final int? pilotId;

  const User({
    required this.id,
    required this.username,
    required this.fullName,
    required this.role,
    required this.profileType,
    this.pilotId,
  });

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as int,
        username: json['username'] as String,
        fullName: json['full_name'] as String,
        role: json['role'] as String,
        profileType: json['profile_type'] as String,
        pilotId: json['pilot_id'] as int?,
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
