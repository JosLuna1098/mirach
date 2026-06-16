import 'dart:async';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'mirach_api.dart';
import 'sse_client.dart';

@pragma('vm:entry-point')
void startCallback() {
  FlutterForegroundTask.setTaskHandler(MirachTaskHandler());
}

class MirachTaskHandler extends TaskHandler {
  SseClient? _sse;
  MirachApi? _api;
  StreamSubscription<Map<String, dynamic>>? _sub;
  String? _pendingToolCallId;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    final baseUrl = await FlutterForegroundTask.getData(key: 'base_url') as String?;
    final token = await FlutterForegroundTask.getData(key: 'token') as String?;
    final sinceStr = await FlutterForegroundTask.getData(key: 'since') as String?;
    final since = int.tryParse(sinceStr ?? '0') ?? 0;

    if (baseUrl == null || token == null) return;

    _api = MirachApi(baseUrl: baseUrl, token: token);
    _sse = SseClient();
    _sse!.reconnectFrom(baseUrl, token, since);
    _sub = _sse!.events.listen(
      _handleEvent,
      onError: (e) {
        if (e.toString().contains('invalid_token')) {
          _setError('Token inválido — abre la app para reconectar');
        }
      },
    );
  }

  void _handleEvent(Map<String, dynamic> ev) {
    final type = ev['type'] as String? ?? '';

    // Mirror conversation_screen logic: any event except cost clears active confirm.
    if (_pendingToolCallId != null && type != 'cost') {
      _pendingToolCallId = null;
    }

    switch (type) {
      case 'user_turn':
        _setWorking();
      case 'awaiting_confirmation':
        _pendingToolCallId = ev['tool_call_id'] as String?;
        final toolName = ev['name'] as String? ?? 'herramienta';
        unawaited(
          FlutterForegroundTask.updateService(
            notificationTitle: 'Mirach',
            notificationText: '⚠ Confirmar: $toolName',
            notificationButtons: [
              const NotificationButton(id: 'approve', text: 'Aprobar'),
              const NotificationButton(id: 'deny', text: 'Denegar'),
              const NotificationButton(id: 'stop', text: 'Parar'),
            ],
          ),
        );
      case 'tool_result':
        // After a confirm resolves, show working again until done.
        _setWorking();
      case 'done':
        _setIdle();
      case 'error':
        final raw = ev['message'] as String? ?? 'Error desconocido';
        final msg = raw.length > 60 ? '${raw.substring(0, 57)}…' : raw;
        _setError(msg);
    }
  }

  void _setWorking() {
    unawaited(
      FlutterForegroundTask.updateService(
        notificationTitle: 'Mirach',
        notificationText: 'Mirach está trabajando…',
        notificationButtons: [
          const NotificationButton(id: 'stop', text: 'Parar'),
        ],
      ),
    );
  }

  void _setIdle() {
    unawaited(
      FlutterForegroundTask.updateService(
        notificationTitle: 'Mirach',
        notificationText: 'Toca para volver',
        notificationButtons: [],
      ),
    );
  }

  void _setError(String msg) {
    unawaited(
      FlutterForegroundTask.updateService(
        notificationTitle: '⚠ Mirach — error',
        notificationText: msg,
        notificationButtons: [],
      ),
    );
  }

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {
    await _sub?.cancel();
    _sse?.dispose();
  }

  @override
  void onNotificationButtonPressed(String id) {
    switch (id) {
      case 'approve':
        final tcId = _pendingToolCallId;
        if (tcId != null) {
          _pendingToolCallId = null;
          unawaited(_api!.confirm(tcId));
          _setWorking();
        }
      case 'deny':
        final tcId = _pendingToolCallId;
        if (tcId != null) {
          _pendingToolCallId = null;
          unawaited(_api!.deny(tcId));
          _setIdle();
        }
      case 'stop':
        unawaited(_api!.stop());
        _setIdle();
    }
  }

  @override
  void onNotificationPressed() {
    FlutterForegroundTask.launchApp('/');
  }
}
