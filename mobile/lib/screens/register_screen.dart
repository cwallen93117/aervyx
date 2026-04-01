import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/auth_service.dart';
import '../widgets/aervyx_logo.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _firstNameCtl = TextEditingController();
  final _lastNameCtl = TextEditingController();
  final _emailCtl = TextEditingController();
  final _passwordCtl = TextEditingController();
  final _confirmPasswordCtl = TextEditingController();
  final _nationCtl = TextEditingController();
  final _compNumberCtl = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _handleRegister() async {
    // Validate passwords match
    if (_passwordCtl.text != _confirmPasswordCtl.text) {
      setState(() => _error = 'Passwords do not match');
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      await context.read<AuthService>().register(
            firstName: _firstNameCtl.text,
            lastName: _lastNameCtl.text,
            email: _emailCtl.text,
            password: _passwordCtl.text,
            nation:
                _nationCtl.text.trim().isEmpty ? null : _nationCtl.text.trim(),
            competitionNumber: _compNumberCtl.text.trim().isEmpty
                ? null
                : _compNumberCtl.text.trim(),
          );
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _firstNameCtl.dispose();
    _lastNameCtl.dispose();
    _emailCtl.dispose();
    _passwordCtl.dispose();
    _confirmPasswordCtl.dispose();
    _nationCtl.dispose();
    _compNumberCtl.dispose();
    super.dispose();
  }

  InputDecoration _inputDecoration(String label) {
    return InputDecoration(
      labelText: label,
      labelStyle: TextStyle(color: Colors.grey[400]),
      border: const OutlineInputBorder(),
      enabledBorder: OutlineInputBorder(
        borderSide: BorderSide(color: Colors.grey[700]!),
      ),
      focusedBorder: const OutlineInputBorder(
        borderSide: BorderSide(color: AervyxLogo.cyan),
      ),
    );
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
                const AervyxLogo(size: 64),
                const SizedBox(height: 8),
                Text(
                  'Create Pilot Account',
                  style: TextStyle(fontSize: 14, color: Colors.grey[500]),
                ),
                const SizedBox(height: 32),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _firstNameCtl,
                        style: const TextStyle(color: Colors.white),
                        decoration: _inputDecoration('First Name'),
                        textInputAction: TextInputAction.next,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _lastNameCtl,
                        style: const TextStyle(color: Colors.white),
                        decoration: _inputDecoration('Last Name'),
                        textInputAction: TextInputAction.next,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _emailCtl,
                  style: const TextStyle(color: Colors.white),
                  decoration: _inputDecoration('Email'),
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _passwordCtl,
                  style: const TextStyle(color: Colors.white),
                  decoration: _inputDecoration('Password'),
                  obscureText: true,
                  textInputAction: TextInputAction.next,
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _confirmPasswordCtl,
                  style: const TextStyle(color: Colors.white),
                  decoration: _inputDecoration('Confirm Password'),
                  obscureText: true,
                  textInputAction: TextInputAction.next,
                ),
                const SizedBox(height: 24),
                Text(
                  'Optional',
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey[600],
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _nationCtl,
                        style: const TextStyle(color: Colors.white),
                        decoration: _inputDecoration('Nation'),
                        textInputAction: TextInputAction.next,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _compNumberCtl,
                        style: const TextStyle(color: Colors.white),
                        decoration: _inputDecoration('Comp Number'),
                        textInputAction: TextInputAction.done,
                        onSubmitted: (_) => _handleRegister(),
                      ),
                    ),
                  ],
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(_error!,
                      style: const TextStyle(color: Colors.redAccent)),
                ],
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _busy ? null : _handleRegister,
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
                        : const Text('Create Account',
                            style: TextStyle(fontWeight: FontWeight.w600)),
                  ),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: _busy
                      ? null
                      : () => Navigator.of(context).pop(),
                  child: Text(
                    'Back to Login',
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
