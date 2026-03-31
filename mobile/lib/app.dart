import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/driver_home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'services/auth_service.dart';

class AervyxApp extends StatelessWidget {
  const AervyxApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Aervyx',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF00E5FF),
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: const Color(0xFF00E5FF),
        useMaterial3: true,
        brightness: Brightness.dark,
      ),
      home: Consumer<AuthService>(
        builder: (context, auth, _) {
          if (auth.loading) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }
          if (!auth.isLoggedIn) return const LoginScreen();
          // Route by profile type — drivers get a dedicated screen
          if (auth.user?.profileType == 'driver') {
            return const DriverHomeScreen();
          }
          return const HomeScreen();
        },
      ),
    );
  }
}
