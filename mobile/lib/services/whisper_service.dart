import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:whisper_ggml_plus/whisper_ggml_plus.dart';

const _modelUrl =
    'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin';

/// Wraps whisper_ggml_plus for on-device Spanish transcription.
///
/// Model file (~142 MB) is downloaded once on first use via [downloadModel] and
/// stored at the path returned by [WhisperController.getPath]. Subsequent calls
/// detect the cached file and skip the download.
class WhisperService {
  final _ctrl = WhisperController();
  String? _modelPath;

  Future<String> _getModelPath() async {
    _modelPath ??= await _ctrl.getPath(WhisperModel.base);
    return _modelPath!;
  }

  Future<bool> isModelCached() async {
    final path = await _getModelPath();
    return File(path).existsSync();
  }

  /// Downloads ggml-base (multilingual) with streaming progress.
  /// Uses a .dl temp file and atomically renames on completion.
  Future<void> downloadModel({void Function(double progress)? onProgress}) async {
    final path = await _getModelPath();
    await File(path).parent.create(recursive: true);
    final tmp = File('$path.dl');

    final client = http.Client();
    try {
      final req = http.Request('GET', Uri.parse(_modelUrl));
      final resp = await client.send(req);
      if (resp.statusCode != 200) {
        throw Exception('HTTP ${resp.statusCode}');
      }
      final total = resp.contentLength ?? 0;
      var received = 0;
      final sink = tmp.openWrite();
      await for (final chunk in resp.stream) {
        sink.add(chunk);
        received += chunk.length;
        if (total > 0) onProgress?.call(received / total);
      }
      await sink.close();
      if (await File(path).exists()) await File(path).delete();
      await tmp.rename(path);
    } catch (e) {
      try {
        await tmp.delete();
      } catch (_) {}
      rethrow;
    } finally {
      client.close();
    }
  }

  /// Transcribes a 16 kHz mono WAV file in Spanish.
  Future<String> transcribe(String audioPath) async {
    final result = await _ctrl.transcribe(
      model: WhisperModel.base,
      audioPath: audioPath,
      lang: 'es',
      withTimestamps: false,
      convert: false,
      threads: 4,
    );
    return result?.transcription.text.trim() ?? '';
  }
}
