import 'dart:convert';

import 'package:http/http.dart' as http;

/// Thin HTTP wrapper for all JSON POST endpoints on the Mirach server.
class MirachApi {
  final String baseUrl;
  final String token;

  MirachApi({required this.baseUrl, required this.token});

  Future<Map<String, dynamic>> turn(
    String text, {
    bool interrupt = false,
    bool clearQueue = false,
  }) => _post('/turn', {
    'text': text,
    'interrupt': interrupt,
    'clear_queue': clearQueue,
  });

  Future<Map<String, dynamic>> stop() => _post('/stop', {});

  Future<Map<String, dynamic>> confirm(String toolCallId) =>
      _post('/confirm', {'tool_call_id': toolCallId});

  Future<Map<String, dynamic>> deny(String toolCallId) =>
      _post('/deny', {'tool_call_id': toolCallId});

  Future<Map<String, dynamic>> closeSession() => _post('/close_session', {});

  static Future<String> pair(
    String baseUrl,
    String code, {
    String device = 'mirach-mobile',
  }) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/pair'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'code': code, 'device': device}),
    );
    if (resp.statusCode != 200) {
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      throw Exception(body['error'] ?? 'pair failed (${resp.statusCode})');
    }
    return (jsonDecode(resp.body) as Map<String, dynamic>)['token'] as String;
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    final resp = await http.post(
      Uri.parse('$baseUrl$path'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode(body),
    );
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }
}
