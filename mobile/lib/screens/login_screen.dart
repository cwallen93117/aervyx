import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:provider/provider.dart';

import '../config/api_config.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../widgets/aervyx_logo.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailCtl = TextEditingController();
  final _passwordCtl = TextEditingController();
  bool _busy = false;
  bool _showPassword = false;
  String? _error;
  String? _googleClientId;
  // Only hidden when the backend explicitly says Google is not configured (404).
  // Network errors or timeouts leave it visible so the user can still try.
  bool _googleNotConfigured = false;

  @override
  void initState() {
    super.initState();
    _fetchGoogleClientId();
  }

  Future<void> _fetchGoogleClientId() async {
    try {
      final api = context.read<ApiService>();
      final json = await api.get(ApiConfig.googleClientIdPath).timeout(const Duration(seconds: 5));
      if (mounted && json['client_id'] != null) {
        setState(() => _googleClientId = json['client_id'] as String);
      }
    } on ApiException catch (e) {
      // 404 = backend has Google sign-in disabled — definitively hide the button.
      // Any other status code is a server error, not a configuration absence.
      if (e.statusCode == 404 && mounted) {
        setState(() => _googleNotConfigured = true);
      }
    } catch (_) {
      // Network error or timeout — leave button visible; the sign-in flow
      // will retry and surface the error if Google really isn't available.
    }
  }

  Future<void> _handleLogin() async {
    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      await context.read<AuthService>().login(
            _emailCtl.text,
            _passwordCtl.text,
          );
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _handleGoogleSignIn() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      var clientId = _googleClientId;
      if (clientId == null) {
        // Initial fetch failed (e.g. network hiccup) — retry once now.
        final api = context.read<ApiService>();
        final json = await api.get(ApiConfig.googleClientIdPath).timeout(const Duration(seconds: 5));
        clientId = json['client_id'] as String?;
        if (mounted && clientId != null) {
          setState(() => _googleClientId = clientId);
        }
      }
      if (clientId == null) {
        throw Exception('Google sign-in is not available on this server');
      }
      final googleSignIn = GoogleSignIn(serverClientId: clientId);
      final account = await googleSignIn.signIn();
      if (account == null) return; // User cancelled
      final auth = await account.authentication;
      final idToken = auth.idToken;
      if (idToken == null) {
        throw Exception('Failed to get Google ID token');
      }
      await context.read<AuthService>().loginWithGoogle(idToken);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _error = e.statusCode == 404
            ? 'Google sign-in is not available on this server'
            : 'Server error (${e.statusCode})');
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _emailCtl.dispose();
    _passwordCtl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const AervyxLogo(size: 80),
                const SizedBox(height: 8),
                Text(
                  'Pilot Companion',
                  style: TextStyle(fontSize: 14, color: Colors.grey[500]),
                ),
                const SizedBox(height: 40),
                TextField(
                  controller: _emailCtl,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    labelText: 'Email',
                    labelStyle: TextStyle(color: Colors.grey[400]),
                    border: const OutlineInputBorder(),
                    enabledBorder: OutlineInputBorder(
                      borderSide: BorderSide(color: Colors.grey[700]!),
                    ),
                    focusedBorder: const OutlineInputBorder(
                      borderSide: BorderSide(color: AervyxLogo.cyan),
                    ),
                  ),
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _passwordCtl,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    labelText: 'Password',
                    labelStyle: TextStyle(color: Colors.grey[400]),
                    border: const OutlineInputBorder(),
                    enabledBorder: OutlineInputBorder(
                      borderSide: BorderSide(color: Colors.grey[700]!),
                    ),
                    focusedBorder: const OutlineInputBorder(
                      borderSide: BorderSide(color: AervyxLogo.cyan),
                    ),
                    suffixIcon: IconButton(
                      icon: Icon(
                        _showPassword ? Icons.visibility_off : Icons.visibility,
                        color: Colors.grey[500],
                      ),
                      onPressed: () => setState(() => _showPassword = !_showPassword),
                    ),
                  ),
                  obscureText: !_showPassword,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _handleLogin(),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                ],
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _busy ? null : _handleLogin,
                    style: FilledButton.styleFrom(
                      backgroundColor: AervyxLogo.cyan,
                      foregroundColor: Colors.black,
                    ),
                    child: _busy
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.black,
                            ),
                          )
                        : const Text('Log In',
                            style: TextStyle(fontWeight: FontWeight.w600)),
                  ),
                ),
                if (!_googleNotConfigured) ...[
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      const Expanded(child: Divider()),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        child: Text('or', style: TextStyle(color: Colors.grey[500], fontSize: 13)),
                      ),
                      const Expanded(child: Divider()),
                    ],
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _busy ? null : _handleGoogleSignIn,
                      icon: Image.network(
                        'https://developers.google.com/identity/images/g-logo.png',
                        height: 18,
                        width: 18,
                        errorBuilder: (_, __, ___) => const Icon(Icons.login, size: 18),
                      ),
                      label: const Text('Sign in with Google'),
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                TextButton(
                  onPressed: _busy
                      ? null
                      : () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => const RegisterScreen(),
                            ),
                          ),
                  child: Text(
                    'Create Account',
                    style: TextStyle(color: Colors.grey[500]),
                  ),
                ),
                const SizedBox(height: 16),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
