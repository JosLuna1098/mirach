import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// Streams parsed SSE events from GET /events, reconnecting with ?since=N on drop.
///
/// The server emits frames as `data: <json>\n\n`; heartbeats are `:\n\n` (ignored).
/// There are no `id:` frames — we track the event count ourselves.
class SseClient {
  int _since = 0;
  bool _active = false;
  http.Client? _httpClient;

  final StreamController<Map<String, dynamic>> _ctrl =
      StreamController.broadcast();

  Stream<Map<String, dynamic>> get events => _ctrl.stream;
  int get since => _since;

  void connect(String baseUrl, String token) {
    _active = true;
    _since = 0;
    _reconnect(baseUrl, token);
  }

  void reconnectFrom(String baseUrl, String token, int since) {
    _active = true;
    _since = since;
    _reconnect(baseUrl, token);
  }

  void dispose() {
    _active = false;
    _httpClient?.close();
    _httpClient = null;
    _ctrl.close();
  }

  void _reconnect(String baseUrl, String token) async {
    while (_active) {
      _httpClient?.close();
      _httpClient = http.Client();
      try {
        final uri = Uri.parse(
          '$baseUrl/events?token=${Uri.encodeComponent(token)}&since=$_since',
        );
        final request = http.Request('GET', uri);
        final streamed = await _httpClient!.send(request);

        if (streamed.statusCode == 401) {
          _ctrl.addError('invalid_token');
          _active = false;
          return;
        }

        String buf = '';
        await for (final chunk in streamed.stream.transform(utf8.decoder)) {
          if (!_active) return;
          buf += chunk;
          // Process complete SSE frames (terminated by blank line "\n\n")
          while (buf.contains('\n\n')) {
            final idx = buf.indexOf('\n\n');
            final frame = buf.substring(0, idx);
            buf = buf.substring(idx + 2);

            for (final line in frame.split('\n')) {
              if (line.startsWith('data: ')) {
                try {
                  final ev =
                      jsonDecode(line.substring(6)) as Map<String, dynamic>;
                  _since++;
                  _ctrl.add(ev);
                } catch (_) {
                  // skip malformed frame
                }
              }
              // lines starting with ':' are heartbeats — ignore
            }
          }
        }
        // stream ended cleanly — reconnect immediately
      } catch (_) {
        // network error — wait before retry
      }

      if (_active) await Future.delayed(const Duration(seconds: 2));
    }
  }
}
