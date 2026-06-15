import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// Thin wrapper around the `record` package for 16 kHz mono WAV capture.
/// Each [start] call writes to a new temp file; [stop] returns its path.
/// [cancel] stops and deletes the file (for slide-to-cancel gesture).
class AudioRecorderService {
  final _recorder = AudioRecorder();

  Future<bool> hasPermission() => _recorder.hasPermission();

  Future<void> start() async {
    final dir = await getTemporaryDirectory();
    final path =
        '${dir.path}/mirach_stt_${DateTime.now().millisecondsSinceEpoch}.wav';
    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: 16000,
        numChannels: 1,
      ),
      path: path,
    );
  }

  Future<String?> stop() => _recorder.stop();

  Future<void> cancel() => _recorder.cancel();

  void dispose() => _recorder.dispose();
}
