import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:permission_handler/permission_handler.dart';

import '../services/audio_recorder.dart';
import '../services/mirach_api.dart';
import '../services/sse_client.dart';
import '../services/tts_service.dart';
import '../services/whisper_service.dart';
import 'pairing_screen.dart';

const _storage = FlutterSecureStorage();

// ── TTS mode ──────────────────────────────────────────────────────────────────

enum _TtsMode { auto, always, never }

// ── Conversation item model ───────────────────────────────────────────────────

enum _ItemKind {
  userTurn,
  userQueued,
  assistantLive,
  assistantVerbose,
  assistantDone,
  toolCall,
  toolResult,
  awaitingConfirmation,
  errorNotice,
}

class _Item {
  _ItemKind kind;
  String text;
  Map<String, dynamic>? args;
  String? toolCallId;
  String? toolName;
  bool isError;
  final Object key = Object();

  _Item({
    required this.kind,
    this.text = '',
    this.args,
    this.toolCallId,
    this.toolName,
    this.isError = false,
  });
}

// ── STT state ─────────────────────────────────────────────────────────────────

enum _SttStatus { init, downloading, loading, ready, recording, transcribing, error }

enum _RecordMode { tap, ptt }

// ── Screen ────────────────────────────────────────────────────────────────────

class ConversationScreen extends StatefulWidget {
  const ConversationScreen({
    super.key,
    required this.baseUrl,
    required this.token,
  });

  final String baseUrl;
  final String token;

  @override
  State<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends State<ConversationScreen> {
  // ── SSE / API ─────────────────────────────────────────────────────────────
  late final MirachApi _api;
  late final SseClient _sse;
  StreamSubscription<Map<String, dynamic>>? _sub;

  final _inputCtrl = TextEditingController();
  final _inputFocusNode = FocusNode();
  final _scrollCtrl = ScrollController();

  final List<_Item> _items = [];
  _Item? _liveItem;
  _Item? _activeConfirm;
  bool _connected = false;
  bool _sending = false;
  bool _verboseOn = false;
  bool _autoSendEnabled = true;
  bool _toolCallsOn = true;
  bool _toolResultsOn = true;

  final Map<String, _Item> _queuedByText = {};

  // ── STT ───────────────────────────────────────────────────────────────────
  final _whisper = WhisperService();
  final _recorder = AudioRecorderService();
  _SttStatus _sttStatus = _SttStatus.init;
  double _downloadProgress = 0;
  Duration _recordDuration = Duration.zero;
  Timer? _recordTimer;
  _RecordMode _recordMode = _RecordMode.tap;

  // ── Auto-send ─────────────────────────────────────────────────────────────
  double _autoSendRemaining = 0;
  Timer? _autoSendTimer;
  // Set to the transcribed text while the countdown runs; cleared on send/cancel.
  String? _pendingVoiceTurnText;

  // ── TTS ───────────────────────────────────────────────────────────────────
  final _tts = TtsService();
  StreamSubscription<bool>? _ttsSub;
  _TtsMode _ttsMode = _TtsMode.auto;
  bool _isSpeaking = false;
  // Voice-origin tracking: matched on the SSE user_turn event.
  String? _lastSentText;
  bool _lastSentWasVoice = false;
  bool _currentTurnIsVoice = false;

  // ── Settings popover ──────────────────────────────────────────────────────
  bool _settingsOpen = false;

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  @override
  void initState() {
    super.initState();
    _api = MirachApi(baseUrl: widget.baseUrl, token: widget.token);
    _sse = SseClient();
    _inputCtrl.addListener(() => setState(() {}));
    _inputFocusNode.addListener(_onFocusChange);
    _loadPrefs();
    _startSse();
    _initStt();
    _initTts();
  }

  @override
  void dispose() {
    _sub?.cancel();
    _sse.dispose();
    _inputCtrl.dispose();
    _inputFocusNode.removeListener(_onFocusChange);
    _inputFocusNode.dispose();
    _scrollCtrl.dispose();
    _recordTimer?.cancel();
    _autoSendTimer?.cancel();
    _recorder.dispose();
    _ttsSub?.cancel();
    _tts.dispose();
    super.dispose();
  }

  @override
  void reassemble() {
    super.reassemble();
    _showAutoSendHint();
  }

  Future<void> _loadPrefs() async {
    final v = await _storage.read(key: 'mirach_verbose');
    final a = await _storage.read(key: 'mirach_autosend');
    final c = await _storage.read(key: 'mirach_toolcalls');
    final r = await _storage.read(key: 'mirach_toolresults');
    final t = await _storage.read(key: 'mirach_tts_mode');
    if (!mounted) return;
    setState(() {
      _verboseOn = v == '1';
      _autoSendEnabled = a != '0';
      _toolCallsOn = c != '0';
      _toolResultsOn = r != '0';
      _ttsMode = switch (t) {
        'always' => _TtsMode.always,
        'never' => _TtsMode.never,
        _ => _TtsMode.auto,
      };
    });
    _showAutoSendHint();
  }

  Future<void> _initTts() async {
    await _tts.init();
    _ttsSub = _tts.speakingStream.listen((speaking) {
      if (mounted) setState(() => _isSpeaking = speaking);
    });
  }

  // ── SSE ───────────────────────────────────────────────────────────────────

  void _startSse() {
    _sub?.cancel();
    _sse.connect(widget.baseUrl, widget.token);
    _sub = _sse.events.listen(
      _handleEvent,
      onError: (e) {
        if (e.toString().contains('invalid_token')) {
          _logout();
        } else {
          setState(() => _connected = false);
        }
      },
    );
    setState(() => _connected = false);
  }

  void _handleEvent(Map<String, dynamic> ev) {
    // These are resolved after setState to avoid calling async in setState.
    bool needsStopTts = false;
    String? pendingTts;

    setState(() {
      _connected = true;
      final type = ev['type'] as String? ?? '';

      if (_activeConfirm != null && type != 'cost') {
        _activeConfirm!.toolCallId = null;
        _activeConfirm = null;
      }

      switch (type) {
        case 'queued':
          _onQueued(ev);
        case 'queue_cleared':
          _onQueueCleared();
        case 'user_turn':
          needsStopTts = true;
          _isSpeaking = false;
          _onUserTurn(ev);
        case 'text_delta':
          _onTextDelta(ev);
        case 'done':
          pendingTts = _handleDone(ev);
        case 'tool_call':
          _onToolCall(ev);
        case 'tool_result':
          _onToolResult(ev);
        case 'awaiting_confirmation':
          _onAwaitingConfirmation(ev);
        case 'error':
          needsStopTts = true;
          _isSpeaking = false;
          _onError(ev);
      }
    });

    if (needsStopTts) unawaited(_tts.stop());
    if (pendingTts != null) unawaited(_tts.speak(pendingTts!));
    _scrollToBottom();
  }

  // ── Event handlers ────────────────────────────────────────────────────────

  void _onQueued(Map<String, dynamic> ev) {
    final text = ev['text'] as String? ?? '';
    final item = _Item(kind: _ItemKind.userQueued, text: text);
    _queuedByText[text] = item;
    _items.add(item);
  }

  void _onQueueCleared() {
    _items.removeWhere((i) => i.kind == _ItemKind.userQueued);
    _queuedByText.clear();
  }

  void _onUserTurn(Map<String, dynamic> ev) {
    _finalizeLive('');
    final text = ev['text'] as String? ?? '';
    // Match to locally-sent turn to determine voice vs text origin.
    if (_lastSentText != null && text == _lastSentText) {
      _currentTurnIsVoice = _lastSentWasVoice;
      _lastSentText = null;
      _lastSentWasVoice = false;
    } else {
      // Turn from another device or a replay — don't auto-read.
      _currentTurnIsVoice = false;
    }
    final queued = _queuedByText.remove(text);
    if (queued != null) {
      queued.kind = _ItemKind.userTurn;
      _items.remove(queued);
      _items.add(queued);
    } else {
      _items.add(_Item(kind: _ItemKind.userTurn, text: text));
    }
  }

  void _onTextDelta(Map<String, dynamic> ev) {
    final delta = ev['delta'] as String? ?? '';
    if (_liveItem == null) {
      _liveItem = _Item(kind: _ItemKind.assistantLive, text: delta);
      _items.add(_liveItem!);
    } else {
      _liveItem!.text += delta;
    }
  }

  // Called inside setState — returns text to speak (or null). Resets voice flag.
  String? _handleDone(Map<String, dynamic> ev) {
    final content = ev['content'] as String? ?? '';
    _finalizeLive(content);
    final shouldSpeak = _computeShouldSpeak(content);
    _currentTurnIsVoice = false;
    return shouldSpeak ? content : null;
  }

  bool _computeShouldSpeak(String content) {
    if (content.isEmpty) return false;
    return switch (_ttsMode) {
      _TtsMode.never => false,
      _TtsMode.always => true,
      _TtsMode.auto => _currentTurnIsVoice,
    };
  }

  void _finalizeLive(String content) {
    final streamed = _liveItem?.text ?? '';
    if (_liveItem != null) {
      _items.remove(_liveItem!);
      _liveItem = null;
    }
    if (streamed.isEmpty && content.isEmpty) return;

    final hadVerbose =
        streamed.isNotEmpty &&
        content.isNotEmpty &&
        streamed.length > content.length * 1.5;
    if (_verboseOn && hadVerbose) {
      _items.add(_Item(kind: _ItemKind.assistantVerbose, text: streamed));
    }

    final finalText = content.isNotEmpty ? content : streamed;
    if (finalText.isNotEmpty) {
      _items.add(_Item(kind: _ItemKind.assistantDone, text: finalText));
    }
  }

  void _onToolCall(Map<String, dynamic> ev) {
    _items.add(
      _Item(
        kind: _ItemKind.toolCall,
        toolName: ev['name'] as String? ?? '',
        args: ev['arguments'] as Map<String, dynamic>?,
        toolCallId: ev['id'] as String?,
      ),
    );
  }

  void _onToolResult(Map<String, dynamic> ev) {
    _items.add(
      _Item(
        kind: _ItemKind.toolResult,
        text: ev['result'] as String? ?? '',
        isError: ev['error'] as bool? ?? false,
      ),
    );
  }

  void _onAwaitingConfirmation(Map<String, dynamic> ev) {
    final item = _Item(
      kind: _ItemKind.awaitingConfirmation,
      toolCallId: ev['tool_call_id'] as String? ?? '',
      toolName: ev['name'] as String? ?? '',
      args: ev['arguments'] as Map<String, dynamic>?,
    );
    _items.add(item);
    _activeConfirm = item;
  }

  void _onError(Map<String, dynamic> ev) {
    _items.add(
      _Item(
        kind: _ItemKind.errorNotice,
        text: ev['message'] as String? ?? 'Unknown error',
      ),
    );
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty || _sending) return;
    // Detect voice origin: a voice turn has its text stored in _pendingVoiceTurnText.
    final isVoice = _pendingVoiceTurnText == text;
    _pendingVoiceTurnText = null;
    _lastSentText = text;
    _lastSentWasVoice = isVoice;
    _inputCtrl.clear();
    setState(() {
      _sending = true;
      _isSpeaking = false; // update UI immediately
    });
    unawaited(_tts.stop()); // local stop only
    try {
      await _api.turn(text);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _stop() async {
    try {
      await _api.stop();
    } catch (_) {}
  }

  Future<void> _confirmAction(String toolCallId, _Item item) async {
    setState(() {
      item.toolCallId = null;
      if (_activeConfirm == item) _activeConfirm = null;
    });
    try {
      await _api.confirm(toolCallId);
    } catch (_) {}
  }

  Future<void> _denyAction(String toolCallId, _Item item) async {
    setState(() {
      item.toolCallId = null;
      if (_activeConfirm == item) _activeConfirm = null;
    });
    try {
      await _api.deny(toolCallId);
    } catch (_) {}
  }

  void _toggleVerbose() {
    setState(() => _verboseOn = !_verboseOn);
    _storage.write(key: 'mirach_verbose', value: _verboseOn ? '1' : '0');
  }

  void _toggleAutoSend() {
    setState(() => _autoSendEnabled = !_autoSendEnabled);
    _storage.write(key: 'mirach_autosend', value: _autoSendEnabled ? '1' : '0');
    if (!_autoSendEnabled && _autoSendRemaining > 0) _cancelAutoSend();
  }

  void _toggleToolCalls() {
    setState(() => _toolCallsOn = !_toolCallsOn);
    _storage.write(key: 'mirach_toolcalls', value: _toolCallsOn ? '1' : '0');
  }

  void _toggleToolResults() {
    setState(() => _toolResultsOn = !_toolResultsOn);
    _storage.write(key: 'mirach_toolresults', value: _toolResultsOn ? '1' : '0');
  }

  void _setTtsMode(_TtsMode mode) {
    setState(() => _ttsMode = mode);
    _storage.write(
      key: 'mirach_tts_mode',
      value: switch (mode) {
        _TtsMode.auto => 'auto',
        _TtsMode.always => 'always',
        _TtsMode.never => 'never',
      },
    );
  }

  void _logout() async {
    await _storage.delete(key: 'mirach_base_url');
    await _storage.delete(key: 'mirach_token');
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const PairingScreen()),
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // ── STT init ──────────────────────────────────────────────────────────────

  Future<void> _initStt() async {
    final cached = await _whisper.isModelCached();
    if (!cached) {
      if (!mounted) return;
      setState(() => _sttStatus = _SttStatus.downloading);
      try {
        await _whisper.downloadModel(
          onProgress: (p) {
            if (mounted) setState(() => _downloadProgress = p);
          },
        );
      } catch (_) {
        if (mounted) setState(() => _sttStatus = _SttStatus.error);
        return;
      }
    }
    if (!mounted) return;
    setState(() => _sttStatus = _SttStatus.loading);
    try {
      final ok = await _whisper.isModelCached();
      setState(() => _sttStatus = ok ? _SttStatus.ready : _SttStatus.error);
    } catch (_) {
      if (mounted) setState(() => _sttStatus = _SttStatus.error);
    }
  }

  // ── Focus / auto-send ─────────────────────────────────────────────────────

  void _onFocusChange() {
    if (_inputFocusNode.hasFocus && _autoSendRemaining > 0) {
      _cancelAutoSend();
    }
  }

  void _startAutoSend(String text) {
    _autoSendTimer?.cancel();
    setState(() => _autoSendRemaining = 2.5);
    _autoSendTimer = Timer.periodic(const Duration(milliseconds: 100), (t) {
      if (!mounted) {
        t.cancel();
        return;
      }
      setState(() {
        _autoSendRemaining = (_autoSendRemaining - 0.1).clamp(0.0, 2.5);
        if (_autoSendRemaining <= 0.05) {
          _autoSendRemaining = 0;
          t.cancel();
          _autoSendTimer = null;
          _send();
        }
      });
    });
  }

  void _cancelAutoSend() {
    _autoSendTimer?.cancel();
    _autoSendTimer = null;
    _pendingVoiceTurnText = null; // cancelled → next send is text origin
    if (mounted) {
      setState(() => _autoSendRemaining = 0);
      FocusScope.of(context).requestFocus(_inputFocusNode);
    }
  }

  void _showAutoSendHint() {
    if (!_autoSendEnabled) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_autoSendEnabled) return;
      final messenger = ScaffoldMessenger.of(context);
      messenger.clearSnackBars();
      messenger.showSnackBar(
        SnackBar(
          content: const Text(
            'Tu mensaje de voz se envía solo tras unos segundos. ¿Prefieres '
            'revisarlo antes? Apaga el envío automático desde el menú ⋮',
            style: TextStyle(color: Color(0xFFe8e8e8)),
          ),
          duration: const Duration(seconds: 5),
          backgroundColor: const Color(0xFF263326),
          behavior: SnackBarBehavior.floating,
          action: SnackBarAction(
            label: 'Entendido',
            textColor: const Color(0xFF4caf50),
            onPressed: () => messenger.hideCurrentSnackBar(),
          ),
        ),
      );
    });
  }

  // ── Mic / recording ───────────────────────────────────────────────────────

  Future<void> _onMicTap() async {
    if (_sttStatus == _SttStatus.ready) {
      _recordMode = _RecordMode.tap;
      await _startRecording();
    } else if (_sttStatus == _SttStatus.recording) {
      await _stopAndTranscribe();
    }
  }

  void _onPttStart() {
    if (_sttStatus != _SttStatus.ready) return;
    _recordMode = _RecordMode.ptt;
    _startRecording();
  }

  void _onPttEnd() {
    if (_recordMode == _RecordMode.ptt && _sttStatus == _SttStatus.recording) {
      _stopAndTranscribe();
    }
  }

  Future<void> _startRecording() async {
    var status = await Permission.microphone.status;
    if (!status.isGranted) {
      final result = await Permission.microphone.request();
      if (!result.isGranted) {
        if (mounted && result.isPermanentlyDenied) _showMicPermissionDialog();
        return;
      }
    }
    if (!mounted) return;
    // Stop any active TTS before recording.
    setState(() {
      _sttStatus = _SttStatus.recording;
      _recordDuration = Duration.zero;
      _isSpeaking = false;
    });
    unawaited(_tts.stop());
    _recordTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _recordDuration += const Duration(seconds: 1));
    });
    try {
      await _recorder.start();
    } catch (_) {
      _recordTimer?.cancel();
      if (mounted) setState(() => _sttStatus = _SttStatus.ready);
    }
  }

  Future<void> _stopAndTranscribe() async {
    _recordTimer?.cancel();
    if (!mounted) return;
    final durationAtStop = _recordDuration;
    setState(() => _sttStatus = _SttStatus.transcribing);

    String? audioPath;
    try {
      audioPath = await _recorder.stop();
      if (audioPath == null) {
        setState(() => _sttStatus = _SttStatus.ready);
        return;
      }
      final text = await _whisper.transcribe(audioPath);
      if (!mounted) return;
      if (text.isNotEmpty) {
        _inputCtrl.text = text;
        _inputCtrl.selection = TextSelection.fromPosition(
          TextPosition(offset: text.length),
        );
        setState(() => _sttStatus = _SttStatus.ready);
        if (_autoSendEnabled) {
          _pendingVoiceTurnText = text; // mark as voice origin for TTS decision
          _startAutoSend(text);
        } else {
          FocusScope.of(context).requestFocus(_inputFocusNode);
        }
      } else {
        setState(() => _sttStatus = _SttStatus.ready);
        if (durationAtStop.inSeconds >= 1) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('No se detectó voz'),
              duration: Duration(seconds: 2),
              backgroundColor: Color(0xFF333333),
            ),
          );
        }
      }
    } catch (_) {
      if (mounted) setState(() => _sttStatus = _SttStatus.ready);
    } finally {
      if (audioPath != null) {
        try {
          File(audioPath).deleteSync();
        } catch (_) {}
      }
    }
  }

  void _showMicPermissionDialog() {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1e1e1e),
        title: const Text('Micrófono', style: TextStyle(color: Color(0xFFe0e0e0))),
        content: const Text(
          'El permiso de micrófono fue denegado permanentemente. '
          'Actívalo en Ajustes para usar la entrada por voz.',
          style: TextStyle(color: Color(0xFFaaaaaa)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar', style: TextStyle(color: Color(0xFF888888))),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              openAppSettings();
            },
            child: const Text('Ajustes', style: TextStyle(color: Color(0xFF4caf50))),
          ),
        ],
      ),
    );
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0f0f0f),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1a1a1a),
        title: Row(
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _connected ? const Color(0xFF4caf50) : const Color(0xFF555555),
              ),
            ),
            const SizedBox(width: 8),
            const Text('Mirach', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: _stop,
            child: const Text('Stop', style: TextStyle(color: Color(0xFFf44336))),
          ),
          IconButton(
            icon: const Icon(Icons.more_vert, color: Color(0xFFcccccc)),
            tooltip: 'Opciones',
            onPressed: () => setState(() => _settingsOpen = !_settingsOpen),
          ),
        ],
      ),
      body: Stack(
        children: [
          Column(
            children: [
              if (_sttStatus == _SttStatus.downloading || _sttStatus == _SttStatus.loading)
                _DownloadBanner(
                  downloading: _sttStatus == _SttStatus.downloading,
                  progress: _downloadProgress,
                ),
              Expanded(
                child: SelectionArea(
                  child: ListView.builder(
                    controller: _scrollCtrl,
                    padding: const EdgeInsets.all(14),
                    itemCount: _items.length,
                    itemBuilder: (ctx, i) => _buildItem(_items[i]),
                  ),
                ),
              ),
              if (_isSpeaking)
                _SpeakingBanner(
                  onStop: () {
                    setState(() => _isSpeaking = false);
                    unawaited(_tts.stop());
                  },
                ),
              _InputBar(
                controller: _inputCtrl,
                focusNode: _inputFocusNode,
                sending: _sending,
                sttStatus: _sttStatus,
                recordDuration: _recordDuration,
                autoSendRemaining: _autoSendRemaining,
                onSend: _send,
                onMicTap: _onMicTap,
                onPttStart: _onPttStart,
                onPttEnd: _onPttEnd,
              ),
            ],
          ),
          // Settings popover overlay
          if (_settingsOpen) ...[
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => setState(() => _settingsOpen = false),
              ),
            ),
            Positioned(
              top: 4,
              right: 4,
              child: _SettingsCard(
                autoSendEnabled: _autoSendEnabled,
                verboseOn: _verboseOn,
                toolCallsOn: _toolCallsOn,
                toolResultsOn: _toolResultsOn,
                ttsMode: _ttsMode,
                onToggleAutoSend: _toggleAutoSend,
                onToggleVerbose: _toggleVerbose,
                onToggleToolCalls: _toggleToolCalls,
                onToggleToolResults: _toggleToolResults,
                onSetTtsMode: _setTtsMode,
                onForget: () {
                  setState(() => _settingsOpen = false);
                  _logout();
                },
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildItem(_Item item) {
    return Padding(
      key: ObjectKey(item.key),
      padding: const EdgeInsets.only(bottom: 8),
      child: switch (item.kind) {
        _ItemKind.userTurn => _UserBubble(text: item.text),
        _ItemKind.userQueued => _UserBubble(text: item.text, queued: true),
        _ItemKind.assistantLive =>
          _verboseOn
              ? _ReasoningBlock(
                  header: '🧠 trabajando…',
                  body: item.text,
                  initiallyExpanded: true,
                  live: true,
                )
              : const _ProcessingBubble(),
        _ItemKind.assistantVerbose => _ReasoningBlock(
          header: '🧠 proceso',
          body: item.text,
          initiallyExpanded: false,
        ),
        _ItemKind.assistantDone => _AssistantBubble(text: item.text),
        _ItemKind.toolCall =>
          _toolCallsOn
              ? _ToolCallCard(name: item.toolName ?? '', args: item.args ?? {})
              : const SizedBox.shrink(),
        _ItemKind.toolResult =>
          _toolResultsOn
              ? _ToolResultCard(result: item.text, isError: item.isError)
              : const SizedBox.shrink(),
        _ItemKind.awaitingConfirmation => _ConfirmCard(
          name: item.toolName ?? '',
          args: item.args ?? {},
          toolCallId: item.toolCallId,
          onConfirm: item.toolCallId != null ? () => _confirmAction(item.toolCallId!, item) : null,
          onDeny: item.toolCallId != null ? () => _denyAction(item.toolCallId!, item) : null,
        ),
        _ItemKind.errorNotice => _ErrorNotice(message: item.text),
      },
    );
  }
}

// ── Settings popover card ─────────────────────────────────────────────────────

class _SettingsCard extends StatelessWidget {
  const _SettingsCard({
    required this.autoSendEnabled,
    required this.verboseOn,
    required this.toolCallsOn,
    required this.toolResultsOn,
    required this.ttsMode,
    required this.onToggleAutoSend,
    required this.onToggleVerbose,
    required this.onToggleToolCalls,
    required this.onToggleToolResults,
    required this.onSetTtsMode,
    required this.onForget,
  });

  final bool autoSendEnabled, verboseOn, toolCallsOn, toolResultsOn;
  final _TtsMode ttsMode;
  final VoidCallback onToggleAutoSend, onToggleVerbose, onToggleToolCalls, onToggleToolResults;
  final ValueChanged<_TtsMode> onSetTtsMode;
  final VoidCallback onForget;

  @override
  Widget build(BuildContext context) {
    // Outer Container: border + shadow only (no color).
    // Inner Material: carries the card color so SwitchListTile ink works correctly.
    return Container(
      width: 272,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF333333)),
        boxShadow: const [
          BoxShadow(color: Colors.black54, blurRadius: 16, offset: Offset(0, 6)),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Material(
          color: const Color(0xFF1e1e1e),
          child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Text(
                'OPCIONES',
                style: TextStyle(
                  color: Color(0xFF666666),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.0,
                ),
              ),
            ),
            _SettingsSwitch(
              label: 'Envío automático de voz',
              value: autoSendEnabled,
              onChanged: (_) => onToggleAutoSend(),
            ),
            _SettingsSwitch(
              label: 'Mostrar razonamiento',
              value: verboseOn,
              onChanged: (_) => onToggleVerbose(),
            ),
            _SettingsSwitch(
              label: 'Mostrar llamadas a herramientas',
              value: toolCallsOn,
              onChanged: (_) => onToggleToolCalls(),
            ),
            _SettingsSwitch(
              label: 'Mostrar resultados de herramientas',
              value: toolResultsOn,
              onChanged: (_) => onToggleToolResults(),
            ),
            const Divider(color: Color(0xFF2a2a2a), height: 1, thickness: 1),
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 10, 16, 4),
              child: Text(
                'Lectura de respuesta',
                style: TextStyle(color: Color(0xFF888888), fontSize: 12),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 2, 12, 12),
              child: Theme(
                data: ThemeData.dark(useMaterial3: true).copyWith(
                  colorScheme: const ColorScheme.dark(
                    primary: Color(0xFF4caf50),
                    onPrimary: Colors.white,
                    secondaryContainer: Color(0xFF1e3a1e),
                    onSecondaryContainer: Color(0xFF4caf50),
                    surface: Color(0xFF252525),
                    onSurface: Color(0xFF999999),
                    outline: Color(0xFF383838),
                  ),
                ),
                child: SegmentedButton<_TtsMode>(
                  segments: const [
                    ButtonSegment(
                      value: _TtsMode.auto,
                      label: Text('Auto', style: TextStyle(fontSize: 12)),
                    ),
                    ButtonSegment(
                      value: _TtsMode.always,
                      label: Text('Siempre', style: TextStyle(fontSize: 12)),
                    ),
                    ButtonSegment(
                      value: _TtsMode.never,
                      label: Text('Nunca', style: TextStyle(fontSize: 12)),
                    ),
                  ],
                  selected: {ttsMode},
                  onSelectionChanged: (s) => onSetTtsMode(s.first),
                  showSelectedIcon: false,
                ),
              ),
            ),
            const Divider(color: Color(0xFF2a2a2a), height: 1, thickness: 1),
            TextButton(
              onPressed: onForget,
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                alignment: Alignment.centerLeft,
                foregroundColor: const Color(0xFFf44336),
                shape: const RoundedRectangleBorder(
                  borderRadius: BorderRadius.only(
                    bottomLeft: Radius.circular(12),
                    bottomRight: Radius.circular(12),
                  ),
                ),
              ),
              child: const Text('Olvidar este dispositivo', style: TextStyle(fontSize: 13)),
            ),
          ],
        ),
      ),
    ));
  }
}

class _SettingsSwitch extends StatelessWidget {
  const _SettingsSwitch({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      dense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
      title: Text(
        label,
        style: const TextStyle(color: Color(0xFFcccccc), fontSize: 13),
      ),
      value: value,
      onChanged: onChanged,
      activeThumbColor: const Color(0xFF4caf50),
      activeTrackColor: const Color(0xFF1a3a1a),
      inactiveThumbColor: const Color(0xFF666666),
      inactiveTrackColor: const Color(0xFF2a2a2a),
    );
  }
}

// ── Speaking banner ───────────────────────────────────────────────────────────

class _SpeakingBanner extends StatelessWidget {
  const _SpeakingBanner({required this.onStop});
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onStop,
      child: Container(
        width: double.infinity,
        color: const Color(0xFF192a19),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: const Row(
          children: [
            Icon(Icons.volume_up_rounded, color: Color(0xFF4caf50), size: 14),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                'Leyendo…  Toca para detener',
                style: TextStyle(color: Color(0xFF4caf50), fontSize: 12),
              ),
            ),
            Icon(Icons.close_rounded, color: Color(0xFF4caf50), size: 14),
          ],
        ),
      ),
    );
  }
}

// ── Bubble / card widgets ─────────────────────────────────────────────────────

class _UserBubble extends StatelessWidget {
  const _UserBubble({required this.text, this.queued = false});
  final String text;
  final bool queued;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 300),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
        decoration: BoxDecoration(
          color: queued ? const Color(0xFF1e2230) : const Color(0xFF1a2740),
          border: Border.all(
            color: queued ? const Color(0xFF4a5570) : const Color(0xFF2c4a7a),
          ),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(
          text,
          style: TextStyle(
            fontSize: 14,
            color: queued ? const Color(0xFF9aa6c0) : const Color(0xFFcfe0ff),
            fontStyle: queued ? FontStyle.italic : FontStyle.normal,
          ),
        ),
      ),
    );
  }
}

class _AssistantBubble extends StatelessWidget {
  const _AssistantBubble({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 320),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
        decoration: BoxDecoration(
          color: const Color(0xFF1e2a1e),
          border: Border.all(color: const Color(0xFF2a3a2a)),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(
          text,
          style: const TextStyle(fontSize: 14, color: Color(0xFFe0e0e0), height: 1.55),
        ),
      ),
    );
  }
}

class _ProcessingBubble extends StatelessWidget {
  const _ProcessingBubble();

  @override
  Widget build(BuildContext context) {
    return const Align(
      alignment: Alignment.centerLeft,
      child: Text(
        'procesando…',
        style: TextStyle(
          color: Color(0xFF888888),
          fontStyle: FontStyle.italic,
          fontSize: 14,
        ),
      ),
    );
  }
}

class _ReasoningBlock extends StatefulWidget {
  const _ReasoningBlock({
    required this.header,
    required this.body,
    required this.initiallyExpanded,
    this.live = false,
  });

  final String header;
  final String body;
  final bool initiallyExpanded;
  final bool live;

  @override
  State<_ReasoningBlock> createState() => _ReasoningBlockState();
}

class _ReasoningBlockState extends State<_ReasoningBlock> {
  late bool _expanded = widget.initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 340),
        decoration: BoxDecoration(
          color: const Color(0xFF161616),
          border: Border.all(
            color: widget.live ? const Color(0xFF4caf50) : const Color(0xFF333333),
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            InkWell(
              onTap: () => setState(() => _expanded = !_expanded),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        widget.header,
                        style: const TextStyle(color: Color(0xFF999999), fontSize: 12),
                      ),
                    ),
                    Icon(
                      _expanded ? Icons.expand_less : Icons.expand_more,
                      size: 18,
                      color: const Color(0xFF999999),
                    ),
                  ],
                ),
              ),
            ),
            if (_expanded && widget.body.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(10, 0, 10, 8),
                child: Text(
                  widget.body,
                  style: const TextStyle(
                    color: Color(0xFF888888),
                    fontFamily: 'monospace',
                    fontSize: 12,
                    height: 1.5,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ToolCallCard extends StatelessWidget {
  const _ToolCallCard({required this.name, required this.args});
  final String name;
  final Map<String, dynamic> args;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF11142a),
        border: Border.all(color: const Color(0xFF252860)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '⚙ $name',
            style: const TextStyle(
              color: Color(0xFF8080e0),
              fontWeight: FontWeight.bold,
              fontFamily: 'monospace',
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            _prettyArgs(args),
            style: const TextStyle(
              color: Color(0xFF6868b8),
              fontFamily: 'monospace',
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }
}

class _ToolResultCard extends StatefulWidget {
  const _ToolResultCard({required this.result, required this.isError});
  final String result;
  final bool isError;

  @override
  State<_ToolResultCard> createState() => _ToolResultCardState();
}

class _ToolResultCardState extends State<_ToolResultCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final accent = widget.isError ? const Color(0xFFf44336) : const Color(0xFF60c060);
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF0f1e10),
        border: Border.all(color: const Color(0xFF1e4020)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.isError ? '✗ error' : '✓ result',
                      style: TextStyle(
                        color: accent,
                        fontWeight: FontWeight.bold,
                        fontFamily: 'monospace',
                        fontSize: 12,
                      ),
                    ),
                  ),
                  Icon(
                    _expanded ? Icons.expand_less : Icons.expand_more,
                    size: 18,
                    color: accent,
                  ),
                ],
              ),
            ),
          ),
          if (_expanded)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
              child: Text(
                widget.result,
                style: TextStyle(
                  color: widget.isError ? const Color(0xFFff8080) : const Color(0xFF4a9a4a),
                  fontFamily: 'monospace',
                  fontSize: 11,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ConfirmCard extends StatelessWidget {
  const _ConfirmCard({
    required this.name,
    required this.args,
    required this.toolCallId,
    required this.onConfirm,
    required this.onDeny,
  });

  final String name;
  final Map<String, dynamic> args;
  final String? toolCallId;
  final VoidCallback? onConfirm;
  final VoidCallback? onDeny;

  @override
  Widget build(BuildContext context) {
    final disabled = toolCallId == null;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1e1200),
        border: Border.all(color: const Color(0xFF4e3000)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            disabled ? '⚠ Confirm: $name (resuelto)' : '⚠ Confirm: $name',
            style: const TextStyle(
              color: Color(0xFFffa030),
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            _prettyArgs(args),
            style: const TextStyle(
              color: Color(0xFFcc8830),
              fontFamily: 'monospace',
              fontSize: 11,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              _ActionBtn(
                label: 'Confirm',
                color: const Color(0xFF2e7d32),
                disabled: disabled,
                onPressed: onConfirm,
              ),
              const SizedBox(width: 8),
              _ActionBtn(
                label: 'Deny',
                color: const Color(0xFFb71c1c),
                disabled: disabled,
                onPressed: onDeny,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ActionBtn extends StatelessWidget {
  const _ActionBtn({
    required this.label,
    required this.color,
    required this.disabled,
    required this.onPressed,
  });

  final String label;
  final Color color;
  final bool disabled;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: disabled ? null : onPressed,
      style: ElevatedButton.styleFrom(
        backgroundColor: color,
        disabledBackgroundColor: color.withAlpha(100),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: Text(label, style: const TextStyle(fontSize: 13)),
    );
  }
}

class _ErrorNotice extends StatelessWidget {
  const _ErrorNotice({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF2a1010),
        border: Border.all(color: const Color(0xFF5a2222)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        '⚠ $message',
        style: const TextStyle(color: Color(0xFFff8080), fontSize: 13),
      ),
    );
  }
}

// ── Download progress banner ──────────────────────────────────────────────────

class _DownloadBanner extends StatelessWidget {
  const _DownloadBanner({required this.downloading, required this.progress});

  final bool downloading;
  final double progress;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: const Color(0xFF151515),
      padding: const EdgeInsets.fromLTRB(14, 6, 14, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            downloading
                ? 'Descargando modelo de voz (${(progress * 100).toStringAsFixed(0)}%)…'
                : 'Cargando modelo de voz…',
            style: const TextStyle(color: Color(0xFF777777), fontSize: 12),
          ),
          const SizedBox(height: 4),
          LinearProgressIndicator(
            value: downloading ? progress : null,
            backgroundColor: const Color(0xFF2a2a2a),
            valueColor: const AlwaysStoppedAnimation(Color(0xFF4caf50)),
            minHeight: 2,
          ),
        ],
      ),
    );
  }
}

// ── Input bar ─────────────────────────────────────────────────────────────────

class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.focusNode,
    required this.sending,
    required this.sttStatus,
    required this.recordDuration,
    required this.autoSendRemaining,
    required this.onSend,
    required this.onMicTap,
    required this.onPttStart,
    required this.onPttEnd,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool sending;
  final _SttStatus sttStatus;
  final Duration recordDuration;
  final double autoSendRemaining;
  final VoidCallback onSend;
  final VoidCallback onMicTap;
  final VoidCallback onPttStart;
  final VoidCallback onPttEnd;

  bool get _isRecording => sttStatus == _SttStatus.recording;
  bool get _isTranscribing => sttStatus == _SttStatus.transcribing;

  @override
  Widget build(BuildContext context) {
    final canSend =
        controller.text.trim().isNotEmpty && !sending && !_isRecording && !_isTranscribing;

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1a1a1a),
        border: Border(top: BorderSide(color: Color(0xFF2a2a2a))),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (autoSendRemaining > 0)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(56, 6, 14, 0),
              child: Row(
                children: [
                  const Icon(Icons.edit, size: 13, color: Color(0xFF4caf50)),
                  const SizedBox(width: 5),
                  Expanded(
                    child: Text(
                      'Enviando en ${autoSendRemaining.toStringAsFixed(1)}s · toca el campo para editar',
                      style: const TextStyle(color: Color(0xFF666666), fontSize: 11),
                    ),
                  ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 8, 14, 14),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                _MicButton(
                  status: sttStatus,
                  onTap: onMicTap,
                  onPttStart: onPttStart,
                  onPttEnd: onPttEnd,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _isRecording
                      ? _RecordingDisplay(duration: recordDuration)
                      : _isTranscribing
                          ? _TranscribingDisplay()
                          : TextField(
                              controller: controller,
                              focusNode: focusNode,
                              style: const TextStyle(color: Color(0xFFe0e0e0), fontSize: 14),
                              onSubmitted: canSend ? (_) => onSend() : null,
                              decoration: InputDecoration(
                                hintText: 'Type a message…',
                                hintStyle: const TextStyle(color: Color(0xFF555555)),
                                filled: true,
                                fillColor: const Color(0xFF252525),
                                contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 13,
                                  vertical: 9,
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide: const BorderSide(color: Color(0xFF383838)),
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide: const BorderSide(color: Color(0xFF4caf50)),
                                ),
                              ),
                            ),
                ),
                const SizedBox(width: 8),
                if (!_isRecording && !_isTranscribing)
                  ElevatedButton(
                    onPressed: canSend ? onSend : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF2e7d32),
                      disabledBackgroundColor: const Color(0xFF1a2a1a),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Text('Send', style: TextStyle(fontSize: 14)),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RecordingDisplay extends StatelessWidget {
  const _RecordingDisplay({required this.duration});
  final Duration duration;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF2a1515),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF5a2222)),
      ),
      child: Row(
        children: [
          const Icon(Icons.circle, color: Color(0xFFef5350), size: 9),
          const SizedBox(width: 7),
          Text(
            _formatDuration(duration),
            style: const TextStyle(color: Color(0xFFe0a0a0), fontSize: 14),
          ),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'Grabando…',
              style: TextStyle(color: Color(0xFF777777), fontSize: 12),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class _TranscribingDisplay extends StatelessWidget {
  const _TranscribingDisplay();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF252525),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF383838)),
      ),
      child: const Row(
        children: [
          SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF4caf50)),
          ),
          SizedBox(width: 9),
          Text(
            'Transcribiendo…',
            style: TextStyle(color: Color(0xFF888888), fontSize: 14),
          ),
        ],
      ),
    );
  }
}

// ── Mic button ────────────────────────────────────────────────────────────────

class _MicButton extends StatefulWidget {
  const _MicButton({
    required this.status,
    required this.onTap,
    required this.onPttStart,
    required this.onPttEnd,
  });

  final _SttStatus status;
  final VoidCallback onTap;
  final VoidCallback onPttStart;
  final VoidCallback onPttEnd;

  @override
  State<_MicButton> createState() => _MicButtonState();
}

class _MicButtonState extends State<_MicButton> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;
  late final Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _scale = Tween<double>(begin: 1.0, end: 1.22).animate(
      CurvedAnimation(parent: _pulse, curve: Curves.easeInOut),
    );
  }

  @override
  void didUpdateWidget(_MicButton old) {
    super.didUpdateWidget(old);
    final recording = widget.status == _SttStatus.recording;
    if (recording && !_pulse.isAnimating) {
      _pulse.repeat(reverse: true);
    } else if (!recording && _pulse.isAnimating) {
      _pulse.stop();
      _pulse.reset();
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final st = widget.status;
    final isRecording = st == _SttStatus.recording;
    final isReady = st == _SttStatus.ready;
    final isBusy =
        st == _SttStatus.loading || st == _SttStatus.transcribing || st == _SttStatus.init;

    final Color bg;
    final Color border;
    final Widget icon;

    if (isRecording) {
      icon = const Icon(Icons.stop_rounded, color: Colors.white, size: 20);
      bg = const Color(0xFFc62828);
      border = const Color(0xFFef5350);
    } else if (isBusy) {
      icon = const SizedBox(
        width: 16,
        height: 16,
        child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF4caf50)),
      );
      bg = const Color(0xFF252525);
      border = const Color(0xFF383838);
    } else if (st == _SttStatus.downloading) {
      icon = const Icon(Icons.downloading, color: Color(0xFF4caf50), size: 20);
      bg = const Color(0xFF252525);
      border = const Color(0xFF383838);
    } else if (isReady) {
      icon = const Icon(Icons.mic, color: Color(0xFF4caf50), size: 20);
      bg = const Color(0xFF252525);
      border = const Color(0xFF383838);
    } else {
      icon = const Icon(Icons.mic_off, color: Color(0xFFf44336), size: 20);
      bg = const Color(0xFF1e1e1e);
      border = const Color(0xFF5a2222);
    }

    Widget btn = Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: bg,
        shape: BoxShape.circle,
        border: Border.all(color: border),
      ),
      child: Center(child: icon),
    );

    if (isRecording) btn = ScaleTransition(scale: _scale, child: btn);

    return GestureDetector(
      onTap: widget.onTap,
      onLongPressStart: (_) => widget.onPttStart(),
      onLongPressEnd: (_) => widget.onPttEnd(),
      child: btn,
    );
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

String _prettyArgs(Map<String, dynamic> args) {
  if (args.isEmpty) return '{}';
  final sb = StringBuffer();
  for (final e in args.entries) {
    sb.writeln('  ${e.key}: ${e.value}');
  }
  return sb.toString().trimRight();
}

String _formatDuration(Duration d) {
  final m = d.inMinutes.remainder(60);
  final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
  return '$m:$s';
}
