import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';

/// Thin wrapper around FlutterTts.
/// State changes (started / finished) are broadcast via [speakingStream].
class TtsService {
  final _tts = FlutterTts();
  final _ctrl = StreamController<bool>.broadcast();

  bool _speaking = false;

  Stream<bool> get speakingStream => _ctrl.stream;
  bool get isSpeaking => _speaking;

  Future<void> init() async {
    // Android setLanguage returns >=0 on success (0=lang, 1=country, 2=variant),
    // negative on failure (-1=missing data, -2=not supported).
    final result = await _tts.setLanguage('es-ES');
    if (result is int && result < 0) await _tts.setLanguage('es-US');
    await _tts.setSpeechRate(0.9);
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);

    _tts.setStartHandler(() {
      _speaking = true;
      _ctrl.add(true);
    });
    _tts.setCompletionHandler(() {
      _speaking = false;
      _ctrl.add(false);
    });
    _tts.setCancelHandler(() {
      _speaking = false;
      _ctrl.add(false);
    });
    _tts.setErrorHandler((_) {
      _speaking = false;
      _ctrl.add(false);
    });
  }

  Future<void> speak(String text) async {
    if (text.isEmpty) return;
    await _tts.speak(text);
  }

  Future<void> stop() async => _tts.stop();

  void dispose() {
    unawaited(_tts.stop());
    _ctrl.close();
  }
}
