import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../services/mirach_api.dart';
import '../services/sse_client.dart';
import 'pairing_screen.dart';

const _storage = FlutterSecureStorage();

// ── Conversation item model ───────────────────────────────────────────────────

enum _ItemKind {
  userTurn,
  userQueued,
  assistantLive, // streaming reasoning (expandable) or "procesando…"
  assistantVerbose, // collapsed reasoning kept after the turn finishes
  assistantDone, // clean final answer bubble
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
  // unique key so Flutter can track list items across rebuilds
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
  late final MirachApi _api;
  late final SseClient _sse;
  StreamSubscription<Map<String, dynamic>>? _sub;

  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();

  final List<_Item> _items = [];
  _Item? _liveItem; // the streaming assistant bubble (settled on 'done')
  _Item? _activeConfirm; // the only confirmation that should be actionable
  bool _connected = false;
  bool _sending = false;
  bool _verboseOn = true; // show the model's reasoning stream

  // queued bubbles keyed by text so user_turn can settle them
  final Map<String, _Item> _queuedByText = {};

  @override
  void initState() {
    super.initState();
    _api = MirachApi(baseUrl: widget.baseUrl, token: widget.token);
    _sse = SseClient();
    _inputCtrl.addListener(() => setState(() {}));
    _loadVerbose();
    _startSse();
  }

  @override
  void dispose() {
    _sub?.cancel();
    _sse.dispose();
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadVerbose() async {
    final v = await _storage.read(key: 'mirach_verbose');
    if (mounted && v == '0') setState(() => _verboseOn = false);
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
    setState(() {
      _connected = true;
      final type = ev['type'] as String? ?? '';

      // A confirmation is only actionable while it is the latest activity. Any
      // subsequent event (tool_result, error, done, a new turn, an answer from
      // another device/voice, or replayed history) retires it so its buttons
      // can't be pressed again — fixes "stale buttons after reconnect".
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
          _onUserTurn(ev);
        case 'text_delta':
          _onTextDelta(ev);
        case 'done':
          _onDone(ev);
        case 'tool_call':
          _onToolCall(ev);
        case 'tool_result':
          _onToolResult(ev);
        case 'awaiting_confirmation':
          _onAwaitingConfirmation(ev);
        case 'error':
          _onError(ev);
        // 'cost' intentionally ignored in v1
      }
    });
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
    // Close any open live stream (e.g. an interrupted turn).
    _finalizeLive('');
    final text = ev['text'] as String? ?? '';
    final queued = _queuedByText.remove(text);
    if (queued != null) {
      queued.kind = _ItemKind.userTurn;
      _items.remove(queued);
      _items.add(queued); // re-anchor at bottom so the response follows it
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

  void _onDone(Map<String, dynamic> ev) {
    _finalizeLive(ev['content'] as String? ?? '');
  }

  /// Settle the in-progress live stream into (optionally) a collapsed reasoning
  /// block + a clean answer bubble. Mirrors the widget's onDone logic: the
  /// reasoning is KEPT as a separate block, never replaced by the answer.
  void _finalizeLive(String content) {
    final streamed = _liveItem?.text ?? '';
    if (_liveItem != null) {
      _items.remove(_liveItem!);
      _liveItem = null;
    }
    if (streamed.isEmpty && content.isEmpty) return;

    // If the stream carried noticeably more than the final answer, it contained
    // reasoning/work — keep it available in a collapsed block (verbose only).
    final hadVerbose =
        streamed.isNotEmpty &&
        content.isNotEmpty &&
        streamed.length > content.length * 1.5;
    if (_verboseOn && hadVerbose) {
      _items.add(_Item(kind: _ItemKind.assistantVerbose, text: streamed));
    }

    // Final answer bubble: done.content (clean). On interrupt (empty content)
    // keep whatever streamed so the partial turn stays readable.
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
    _activeConfirm = item; // becomes the live, actionable confirmation
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
    _inputCtrl.clear();
    setState(() => _sending = true);
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
      item.toolCallId = null; // disable buttons immediately
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
                color: _connected
                    ? const Color(0xFF4caf50)
                    : const Color(0xFF555555),
              ),
            ),
            const SizedBox(width: 8),
            const Text(
              'Mirach',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Mostrar razonamiento del modelo',
            onPressed: _toggleVerbose,
            icon: Icon(
              Icons.psychology,
              color: _verboseOn
                  ? const Color(0xFF4caf50)
                  : const Color(0xFF666666),
            ),
          ),
          TextButton(
            onPressed: _stop,
            child: const Text(
              'Stop',
              style: TextStyle(color: Color(0xFFf44336)),
            ),
          ),
          PopupMenuButton<String>(
            onSelected: (v) {
              if (v == 'forget') _logout();
            },
            itemBuilder: (_) => [
              const PopupMenuItem(
                value: 'forget',
                child: Text('Forget this device'),
              ),
            ],
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            // SelectionArea makes every text bubble selectable + copyable
            // (long-press to start a selection); buttons inside still work.
            child: SelectionArea(
              child: ListView.builder(
                controller: _scrollCtrl,
                padding: const EdgeInsets.all(14),
                itemCount: _items.length,
                itemBuilder: (ctx, i) => _buildItem(_items[i]),
              ),
            ),
          ),
          _InputBar(controller: _inputCtrl, sending: _sending, onSend: _send),
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
        _ItemKind.toolCall => _ToolCallCard(
          name: item.toolName ?? '',
          args: item.args ?? {},
        ),
        _ItemKind.toolResult => _ToolResultCard(
          result: item.text,
          isError: item.isError,
        ),
        _ItemKind.awaitingConfirmation => _ConfirmCard(
          name: item.toolName ?? '',
          args: item.args ?? {},
          toolCallId: item.toolCallId,
          onConfirm: item.toolCallId != null
              ? () => _confirmAction(item.toolCallId!, item)
              : null,
          onDeny: item.toolCallId != null
              ? () => _denyAction(item.toolCallId!, item)
              : null,
        ),
        _ItemKind.errorNotice => _ErrorNotice(message: item.text),
      },
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
          style: const TextStyle(
            fontSize: 14,
            color: Color(0xFFe0e0e0),
            height: 1.55,
          ),
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

/// Collapsible reasoning block (the model's working stream), kept separate from
/// the final answer. Tap the header to expand/collapse.
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
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 7,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        widget.header,
                        style: const TextStyle(
                          color: Color(0xFF999999),
                          fontSize: 12,
                        ),
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

class _ToolResultCard extends StatelessWidget {
  const _ToolResultCard({required this.result, required this.isError});
  final String result;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF0f1e10),
        border: Border.all(color: const Color(0xFF1e4020)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            isError ? '✗ error' : '✓ result',
            style: TextStyle(
              color: isError
                  ? const Color(0xFFf44336)
                  : const Color(0xFF60c060),
              fontWeight: FontWeight.bold,
              fontFamily: 'monospace',
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            result,
            style: TextStyle(
              color: isError
                  ? const Color(0xFFff8080)
                  : const Color(0xFF4a9a4a),
              fontFamily: 'monospace',
              fontSize: 11,
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

// ── Input bar ─────────────────────────────────────────────────────────────────

class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.sending,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final canSend = controller.text.trim().isNotEmpty && !sending;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 8, 14, 14),
      decoration: const BoxDecoration(
        color: Color(0xFF1a1a1a),
        border: Border(top: BorderSide(color: Color(0xFF2a2a2a))),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              style: const TextStyle(color: Color(0xFFe0e0e0), fontSize: 14),
              onSubmitted: (_) => onSend(),
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
          ElevatedButton(
            onPressed: canSend ? onSend : null,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF2e7d32),
              disabledBackgroundColor: const Color(0xFF1a2a1a),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            child: const Text('Send', style: TextStyle(fontSize: 14)),
          ),
        ],
      ),
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
