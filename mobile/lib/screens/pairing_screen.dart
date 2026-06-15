import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../services/mirach_api.dart';
import 'conversation_screen.dart';

const _storage = FlutterSecureStorage();

class PairingScreen extends StatefulWidget {
  const PairingScreen({super.key});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  final _hostCtrl = TextEditingController(text: '192.168.1.100:7270');
  final _codeCtrl = TextEditingController();
  bool _loading = false;

  @override
  void dispose() {
    _hostCtrl.dispose();
    _codeCtrl.dispose();
    super.dispose();
  }

  Future<void> _pair() async {
    final host = _hostCtrl.text.trim();
    final code = _codeCtrl.text.trim().toUpperCase();
    if (host.isEmpty || code.isEmpty) return;

    setState(() => _loading = true);
    try {
      final baseUrl = host.startsWith('http') ? host : 'http://$host';
      final token = await MirachApi.pair(baseUrl, code);
      await _storage.write(key: 'mirach_base_url', value: baseUrl);
      await _storage.write(key: 'mirach_token', value: token);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) =>
              ConversationScreen(baseUrl: baseUrl, token: token),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Pairing failed: $e'),
          backgroundColor: Colors.red[900],
        ),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0f0f0f),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Mirach',
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              const Text(
                'Enter your PC\'s address and the pairing code\nshown in the daemon logs.',
                style: TextStyle(color: Color(0xFF888888), fontSize: 14),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              _DarkField(
                controller: _hostCtrl,
                label: 'PC address (host:port)',
                hint: '192.168.1.100:7270',
                keyboardType: TextInputType.url,
              ),
              const SizedBox(height: 16),
              _DarkField(
                controller: _codeCtrl,
                label: 'Pairing code',
                hint: 'XXXXXX',
                textCapitalization: TextCapitalization.characters,
                onSubmitted: (_) => _pair(),
              ),
              const SizedBox(height: 28),
              FilledButton(
                onPressed: _loading ? null : _pair,
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF2e7d32),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                child: _loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('Connect', style: TextStyle(fontSize: 16)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DarkField extends StatelessWidget {
  const _DarkField({
    required this.controller,
    required this.label,
    required this.hint,
    this.keyboardType,
    this.textCapitalization = TextCapitalization.none,
    this.onSubmitted,
  });

  final TextEditingController controller;
  final String label;
  final String hint;
  final TextInputType? keyboardType;
  final TextCapitalization textCapitalization;
  final ValueChanged<String>? onSubmitted;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      keyboardType: keyboardType,
      textCapitalization: textCapitalization,
      onSubmitted: onSubmitted,
      style: const TextStyle(color: Color(0xFFe0e0e0)),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        labelStyle: const TextStyle(color: Color(0xFF888888)),
        hintStyle: const TextStyle(color: Color(0xFF555555)),
        filled: true,
        fillColor: const Color(0xFF1a1a1a),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Color(0xFF383838)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Color(0xFF4caf50)),
        ),
      ),
    );
  }
}
