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
  bool _connected = false;
  http.Client? _httpClient;

  final StreamController<Map<String, dynamic>> _ctrl =
      StreamController.broadcast();
  final StreamController<bool> _connCtrl = StreamController<bool>.broadcast();

  Stream<Map<String, dynamic>> get events => _ctrl.stream;

  /// Emits `true` once the HTTP stream is open, `false` when it drops or errors.
  /// This is the connection's actual state — independent of whether any events
  /// have flowed yet (an idle session emits none until the first turn).
  Stream<bool> get connectionState => _connCtrl.stream;
  bool get isConnected => _connected;
  int get since => _since;

  void _setConnected(bool value) {
    if (_connected == value) return;
    _connected = value;
    if (!_connCtrl.isClosed) _connCtrl.add(value);
  }

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
    _connected = false;
    _httpClient?.close();
    _httpClient = null;
    _ctrl.close();
    _connCtrl.close();
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
          _setConnected(false);
          _ctrl.addError('invalid_token');
          _active = false;
          return;
        }

        // HTTP stream is open — connection is live before any event arrives.
        _setConnected(true);

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
        // network error (e.g. PC server down) — mark offline, then retry.
        _setConnected(false);
      }

      if (_active) await Future.delayed(const Duration(seconds: 2));
    }
  }
}
