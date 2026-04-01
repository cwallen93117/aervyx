import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'screens/driver_home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'services/auth_service.dart';
import 'widgets/aervyx_logo.dart';

class AervyxApp extends StatelessWidget {
  const AervyxApp({super.key});

  @override
  Widget build(BuildContext context) {
    // Make the system status bar and nav bar black to match
    SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
      statusBarColor: Colors.black,
      systemNavigationBarColor: Colors.black,
    ));

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
            // Show the logo on black while restoring session — matches login screen
            return const Scaffold(
              backgroundColor: Colors.black,
              body: Center(child: AervyxLogo(size: 80)),
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
